"""M-58 (2026-04-23): V30 slot-bound generator (structured-first).

V30 Report Contract Architecture Layer 4a. Codex plan pass-1 rev #1
(structured-first over prose-first):

  "change the slot-bound generation contract from paragraph-only
   to structured-first. Each slot should emit a machine-readable
   payload for every required field: field_name, status
   (extracted | not_extractable | gap_unrecoverable), value,
   bound_ev_id, source_span. Then render prose from that payload."

This reverses V28/V29's "narrate then inspect" failure mode. With
structured-first: the LLM emits a JSON payload binding each
required field to a source_span in the bound direct_quote. M-59
validates the payload, not free prose. Prose is rendered from the
payload by deterministic code — no LLM creativity at rendering.

## Split of responsibilities

  M-58 (this module):       prompt construction, response parsing,
                            prose rendering — all PURE functions.
                            No LLM calls. No network.
  Integration layer:        one LLM call per slot using the M-58
                            prompt + json-mode schema, consumed by
                            M-58 parser. Lives in multi_section_generator
                            when M-58 integration lands (V30 sweep).
  M-59:                     validates SlotFillPayload per contract.

## Gap handling

When the FrameRow is FRAME_GAP_UNRECOVERABLE, `compose_gap_payload`
emits a payload with `status="gap_unrecoverable"` for every
required field — WITHOUT any LLM call. `render_slot_prose` on
that payload emits the M-60 explicit gap sentence template. No
silent omission.

## Entity-type-agnostic (Codex rev #7)

M-58 does NOT branch on entity_type. It reads required_fields
from the contract and asks the LLM to extract each one from
direct_quote. Works for pivotal_trial, mechanism_primary,
regulatory, statute, dft_primary — any type with a
direct_quote and required_fields.

## Determinism

`build_slot_fill_prompt` and `render_slot_prose` are pure
functions. `parse_slot_fill_response` is pure given valid JSON.
Same inputs → same outputs. The LLM response itself is not
deterministic, but M-58 captures it and renders deterministically
from the payload so downstream layers see byte-identical prose.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from ..nodes.contract_outline import ContractSlotPlan
from ..retrieval.frame_fetcher import FrameRow, ProvenanceClass


# ─────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────
FieldStatus = Literal["extracted", "not_extractable", "gap_unrecoverable"]


@dataclass(frozen=True)
class SlotFieldFill:
    """One required-field outcome for a slot. Produced by the LLM
    JSON response (extracted / not_extractable) or by the gap-
    composer (gap_unrecoverable)."""

    field_name: str
    status: FieldStatus
    value: str | None         # None when status != extracted
    bound_ev_id: str
    source_span: str | None   # substring-of-direct_quote; None when not_extractable


@dataclass(frozen=True)
class SlotFillPayload:
    """Structured fill for one slot. Consumed by M-59 validator and
    M-58 prose renderer."""

    slot_id: str
    entity_id: str
    subsection_title: str
    bound_ev_id: str
    fields: tuple[SlotFieldFill, ...]
    # Provenance class carried through so M-60 manifest rendering
    # knows the source quality per slot.
    provenance_class: str

    def fields_by_name(self) -> dict[str, SlotFieldFill]:
        return {f.field_name: f for f in self.fields}

    def completion_count(self) -> int:
        """Count of fields with status='extracted'. Used by M-59 to
        check against `min_fields_for_completion`."""
        return sum(1 for f in self.fields if f.status == "extracted")


class SlotFillParseError(ValueError):
    """LLM response could not be parsed into a SlotFillPayload."""


def _value_supported_by_span(
    value: str, source_span: str, direct_quote: str,
) -> bool:
    """Codex M-58 audit Blocker fix (pass 1 → pass 4):

    pass-1: added a value-support check (not just span-in-quote).
    pass-2: dropped the direct_quote + token-overlap fallback
            (accepted span='5 mg' + value='10 mg').
    pass-3: dropped lowercase from normalization (accepted
            span='5 M' + value='5 m' — molar vs meter).
    pass-4: replaced raw substring with "not-extended-by-word-char"
            lookaround match (raw substring accepted span='15 mg'
            + value='5 mg' and span='1879' + value='879' — partial
            numerics). Uses `(?<!\\w)needle(?!\\w)` rather than
            `\\b` so values with non-word edges (e.g. '-0.47%')
            still match cleanly.

    Final policy — not-extended-by-word-char containment with
    whitespace-only normalization:

      1. `value` appears in `source_span` AND is not extended into
         a larger word on either side. "5 mg" in "(5 mg) weekly"
         matches; "5 mg" in "15 mg" does not.
      2. whitespace-collapsed `value` appears in whitespace-
         collapsed `source_span` under the same rule.
         Accommodates LLM whitespace/tab variation only.

    Rejected:
      - case drift (pass-3)
      - substring-inside-word drift (pass-4)
      - direct_quote fallback (pass-2)

    Narrow residual (documented, not fixed at M-58): if the SAME
    exact value string appears multiple times in `source_span`
    with different semantics (e.g. two "5 mg" mentions — one
    initial, one maintenance dose), M-58 cannot disambiguate
    which mention the field referred to. M-59 or the contract
    prompt itself would need to encode that distinction.

    `direct_quote` parameter retained for future document-scope
    checks, currently unused.
    """
    if not value or not source_span:
        return False
    if _word_bounded_in(value, source_span):
        return True
    if _word_bounded_in(
        _normalize_for_span_check(value),
        _normalize_for_span_check(source_span),
    ):
        return True
    return False


def _normalize_for_span_check(s: str) -> str:
    """Whitespace-collapse ONLY. No lowercasing (pass-3). Case-
    sensitive scientific tokens (HbA1c, 5 M vs 5 m, Ca2+) must
    survive the normalization."""
    return " ".join(s.split())


def _word_bounded_in(needle: str, haystack: str) -> bool:
    """True when `needle` appears in `haystack` and is NOT extended
    into a larger word on either side.

    Uses negative lookaround `(?<!\\w)` + `(?!\\w)` rather than
    `\\b`. The difference matters for values whose edge characters
    are non-word (e.g. "-0.47%"): `\\b` would reject them because
    it needs a word char adjacent to the boundary, while
    lookaround correctly accepts them since the rule is "not
    extended by a word char".

    Rejects pass-4 exploits:
      - needle="5 mg",  haystack="15 mg"   → False ("1" before "5" is \\w)
      - needle="879",   haystack="1879"    → False ("1" before "8" is \\w)
      - needle="5 mg",  haystack="5 mgg"   → False ("g" after "g" is \\w)

    Accepts legitimate matches:
      - needle="1879",  haystack="N=1879"  → True  ("=" not \\w; edge after)
      - needle="5 mg",  haystack="(5 mg)"  → True
      - needle="-0.47%",haystack="-0.47%"  → True  (both edges at string-edge)
      - needle="HbA1c", haystack="Baseline HbA1c was" → True

    Empty needle returns False. Anchored regex with re.UNICODE so
    non-ASCII word characters (e.g. 'é') are treated correctly.
    """
    if not needle:
        return False
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.UNICODE) is not None


# ─────────────────────────────────────────────────────────────────────
# Prompt construction
# ─────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are filling a SPECIFIC SLOT in a structured clinical report.\n"
    "Your ONLY job: for each required field, either extract the value "
    "from the direct_quote below or mark it not_extractable.\n"
    "You MUST NOT invent facts. You MUST NOT cite anything other than "
    "the bound evidence. You MUST return the JSON schema exactly."
)


def build_slot_fill_prompt(
    slot_plan: ContractSlotPlan,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
    research_question: str,
) -> str:
    """Compose the LLM prompt for one slot.

    The prompt is a single string containing system directives, the
    bound evidence, the required fields list, and an exact JSON
    schema the LLM must return. Pure function; byte-identical
    output given same inputs.

    Raises:
        ValueError: when called with a FRAME_GAP_UNRECOVERABLE
            row. Gaps are handled by `compose_gap_payload`, not the
            LLM path — calling this function for a gap row is a
            bug, not a silent pass-through.
    """
    if frame_row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        raise ValueError(
            f"build_slot_fill_prompt called for gap row "
            f"entity_id={frame_row.entity_id!r}; use compose_gap_payload "
            f"for gap slots"
        )
    if not required_fields:
        raise ValueError(
            f"slot {slot_plan.slot_id!r} has empty required_fields; "
            f"contract invariant violated"
        )

    bound_ev_id = frame_row.entity_id
    fields_bullets = "\n".join(
        f"  - {fname}" for fname in required_fields
    )

    # Deterministic JSON schema the LLM must return. We enumerate
    # status values + require all required_fields present in the
    # output array.
    schema_example = {
        "fields": [
            {
                "field_name": "<one of the required fields>",
                "status": "extracted | not_extractable",
                "value": "<the extracted value as a string, or null>",
                "source_span": (
                    "<verbatim substring of direct_quote that backs "
                    "the value, or null>"
                ),
            }
        ]
    }

    prompt = (
        f"{_SYSTEM_PROMPT}\n"
        f"\n"
        f"=== CONTEXT ===\n"
        f"RESEARCH_QUESTION: {research_question}\n"
        f"SECTION: {slot_plan.section}\n"
        f"SUBSECTION: {slot_plan.subsection_title}\n"
        f"\n"
        f"=== BOUND EVIDENCE ===\n"
        f"BOUND_EV_ID: {bound_ev_id}\n"
        f"PROVENANCE: {frame_row.provenance_class.value}\n"
        f"ENTITY_TYPE: {frame_row.entity_type}\n"
        f"DIRECT_QUOTE:\n"
        f"<<<\n{frame_row.direct_quote}\n>>>\n"
        f"\n"
        f"=== REQUIRED FIELDS ===\n"
        f"For EACH of the following required fields, either extract "
        f"its value verbatim from DIRECT_QUOTE and report the exact "
        f"substring used (source_span), OR mark status=not_extractable "
        f"with value=null and source_span=null.\n"
        f"{fields_bullets}\n"
        f"\n"
        f"=== OUTPUT CONTRACT ===\n"
        f"Return ONLY a JSON object matching this schema (one entry "
        f"per required field, in the same order):\n"
        f"{json.dumps(schema_example, indent=2)}\n"
        f"\n"
        f"RULES:\n"
        f"1. Every required field MUST appear in fields[] exactly once.\n"
        f"2. status MUST be one of: extracted | not_extractable.\n"
        f"3. source_span MUST be a verbatim substring of DIRECT_QUOTE "
        f"when status=extracted.\n"
        f"4. Do NOT add fields outside the required list.\n"
        f"5. Do NOT cite anything other than {bound_ev_id}.\n"
        f"6. If DIRECT_QUOTE does not state a field, use "
        f"status=not_extractable. Do NOT guess. Do NOT infer.\n"
    )
    return prompt


# ─────────────────────────────────────────────────────────────────────
# Response parsing
# ─────────────────────────────────────────────────────────────────────
def parse_slot_fill_response(
    response_text: str,
    slot_plan: ContractSlotPlan,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
) -> SlotFillPayload:
    """Parse the LLM JSON response into a SlotFillPayload.

    Pure function. The LLM is expected to return either:
      - A raw JSON object matching the build_slot_fill_prompt schema, or
      - A JSON object wrapped in ```json ... ``` fences (common
        LLM behavior; we strip the fences).

    Raises:
        SlotFillParseError: when the response is malformed, when
            required fields are missing, when status values are
            invalid, or when source_span is not a substring of
            direct_quote (anti-fabrication check).
    """
    if not isinstance(response_text, str):
        raise SlotFillParseError(
            f"response must be str, got {type(response_text).__name__}"
        )

    raw = response_text.strip()
    if raw.startswith("```"):
        # Strip fence: ```json\n...\n``` or ```\n...\n```
        lines = raw.splitlines()
        # Drop first and last line
        if len(lines) < 2:
            raise SlotFillParseError(
                "fenced response truncated"
            )
        raw = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SlotFillParseError(
            f"invalid JSON: {exc.msg} at pos {exc.pos}"
        ) from exc

    if not isinstance(data, dict):
        raise SlotFillParseError(
            f"response root must be object, got {type(data).__name__}"
        )
    fields_raw = data.get("fields")
    if not isinstance(fields_raw, list):
        raise SlotFillParseError(
            f"'fields' must be list, got {type(fields_raw).__name__}"
        )

    bound_ev_id = frame_row.entity_id
    direct_quote = frame_row.direct_quote or ""

    # Build by name for alignment to required_fields
    by_name: dict[str, dict] = {}
    for i, f in enumerate(fields_raw):
        if not isinstance(f, dict):
            raise SlotFillParseError(
                f"fields[{i}] must be object, got {type(f).__name__}"
            )
        fname = f.get("field_name")
        if not isinstance(fname, str) or not fname.strip():
            raise SlotFillParseError(
                f"fields[{i}].field_name must be non-empty string"
            )
        if fname in by_name:
            raise SlotFillParseError(
                f"fields[{i}].field_name={fname!r} duplicated"
            )
        by_name[fname] = f

    # Every required field must appear exactly once
    missing = set(required_fields) - set(by_name)
    if missing:
        raise SlotFillParseError(
            f"missing required fields: {sorted(missing)}"
        )
    extras = set(by_name) - set(required_fields)
    if extras:
        raise SlotFillParseError(
            f"unexpected extra fields: {sorted(extras)}"
        )

    # Build SlotFieldFill tuple in required_fields order
    fills: list[SlotFieldFill] = []
    for fname in required_fields:
        f = by_name[fname]
        status = f.get("status")
        if status not in ("extracted", "not_extractable"):
            raise SlotFillParseError(
                f"fields[{fname!r}].status must be extracted or "
                f"not_extractable, got {status!r}"
            )
        value = f.get("value")
        source_span = f.get("source_span")

        if status == "extracted":
            if not isinstance(value, str) or not value.strip():
                raise SlotFillParseError(
                    f"fields[{fname!r}].value must be non-empty "
                    f"string when status=extracted"
                )
            if not isinstance(source_span, str) or not source_span.strip():
                raise SlotFillParseError(
                    f"fields[{fname!r}].source_span must be non-empty "
                    f"string when status=extracted"
                )
            if source_span not in direct_quote:
                raise SlotFillParseError(
                    f"fields[{fname!r}].source_span is not a verbatim "
                    f"substring of direct_quote (anti-fabrication "
                    f"check 1 failed)"
                )
            # Codex M-58 audit Blocker (pass 1→3 tightening).
            # Extracted `value` must be supported by `source_span`
            # itself, not just appear somewhere in direct_quote.
            # Final policy (pass-3): strict verbatim-in-span OR
            # whitespace-collapsed verbatim-in-span. No lowercase
            # (pass-3 caught `5 M` vs `5 m` unit-case exploit).
            # No direct_quote fallback (pass-2 caught
            # `span="5 mg" + value="10 mg"` misbinding exploit).
            # See _value_supported_by_span docstring for the full
            # three-pass history.
            if not _value_supported_by_span(value, source_span, direct_quote):
                raise SlotFillParseError(
                    f"fields[{fname!r}].value={value!r} is not "
                    f"supported by source_span={source_span!r}; "
                    f"extracted values must be verbatim from the "
                    f"span (anti-fabrication check 2 failed)"
                )
        else:
            # not_extractable
            if value is not None:
                raise SlotFillParseError(
                    f"fields[{fname!r}].value must be null when "
                    f"status=not_extractable; got {value!r}"
                )
            if source_span is not None:
                raise SlotFillParseError(
                    f"fields[{fname!r}].source_span must be null when "
                    f"status=not_extractable; got {source_span!r}"
                )

        fills.append(SlotFieldFill(
            field_name=fname,
            status=status,  # type: ignore[arg-type]
            value=value if status == "extracted" else None,
            bound_ev_id=bound_ev_id,
            source_span=source_span if status == "extracted" else None,
        ))

    return SlotFillPayload(
        slot_id=slot_plan.slot_id,
        entity_id=bound_ev_id,
        subsection_title=slot_plan.subsection_title,
        bound_ev_id=bound_ev_id,
        fields=tuple(fills),
        provenance_class=frame_row.provenance_class.value,
    )


# ─────────────────────────────────────────────────────────────────────
# Gap payload
# ─────────────────────────────────────────────────────────────────────
def compose_gap_payload(
    slot_plan: ContractSlotPlan,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
) -> SlotFillPayload:
    """Compose a SlotFillPayload for a gap slot WITHOUT calling the
    LLM. Every required field is status=gap_unrecoverable.

    Used when frame_row.provenance_class == FRAME_GAP_UNRECOVERABLE.
    M-60 manifest consumes this to emit the explicit gap sentence.

    Codex M-58 audit Medium fix: symmetric guard with
    build_slot_fill_prompt. A misrouted non-gap row converted to
    all-gap would silently erase retrievable evidence, which is
    worse than a hard failure. Route via the LLM path for non-gap
    rows; raise here so routing bugs surface.
    """
    if frame_row.provenance_class != ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        raise ValueError(
            f"compose_gap_payload called for non-gap row "
            f"entity_id={frame_row.entity_id!r} with provenance="
            f"{frame_row.provenance_class.value!r}; use "
            f"build_slot_fill_prompt + parse_slot_fill_response "
            f"for non-gap rows"
        )
    bound_ev_id = frame_row.entity_id
    fills = tuple(
        SlotFieldFill(
            field_name=fname,
            status="gap_unrecoverable",
            value=None,
            bound_ev_id=bound_ev_id,
            source_span=None,
        )
        for fname in required_fields
    )
    return SlotFillPayload(
        slot_id=slot_plan.slot_id,
        entity_id=bound_ev_id,
        subsection_title=slot_plan.subsection_title,
        bound_ev_id=bound_ev_id,
        fields=fills,
        provenance_class=frame_row.provenance_class.value,
    )


# ─────────────────────────────────────────────────────────────────────
# Prose rendering (deterministic)
# ─────────────────────────────────────────────────────────────────────
_NOT_EXTRACTABLE_PHRASE = "not extractable from available primary content"
# NOTE: the gap-prose template below is a STOPGAP owned by M-58 until
# M-60 ships. Codex M-58 audit Nit: surface-language policy belongs
# in M-60 (the manifest/report-surface layer). When M-60 lands it
# should either pass a `gap_template` parameter to render_slot_prose
# or subclass the renderer. Until then this string lives here so the
# pipeline has an honest failure sentence today.
_GAP_PHRASE = (
    "Primary publication was not retrievable from open-access, "
    "abstract, or metadata sources. All required fields are "
    "unavailable for this entity."
)


def render_slot_prose(payload: SlotFillPayload) -> str:
    """Render the SlotFillPayload into a deterministic prose
    paragraph with [ev_id] citations.

    Format:
      "<subsection header>: <field1 statement>[bound_ev_id].
       <field2 statement>[bound_ev_id]. ..."

    Same payload → byte-identical prose. No LLM, no randomness.

    Gap slot (all fields gap_unrecoverable): emits the explicit
    M-60 gap sentence with the bound_ev_id flagged.
    """
    bound = payload.bound_ev_id
    subsection = payload.subsection_title
    all_gap = all(
        f.status == "gap_unrecoverable" for f in payload.fields
    )
    if all_gap:
        return f"{subsection}: {_GAP_PHRASE} [{bound}]"

    sentences: list[str] = []
    for field in payload.fields:
        if field.status == "extracted":
            # "<field_name> = <value>" phrased as short sentence.
            sentences.append(
                f"{field.field_name}: {field.value}. [{bound}]"
            )
        elif field.status == "not_extractable":
            sentences.append(
                f"{field.field_name}: {_NOT_EXTRACTABLE_PHRASE}. [{bound}]"
            )
        else:  # gap_unrecoverable mixed into partial slot — unusual
               # but handled.
            sentences.append(
                f"{field.field_name}: "
                f"primary source unavailable. [{bound}]"
            )
    body = " ".join(sentences)
    return f"{subsection}: {body}"
