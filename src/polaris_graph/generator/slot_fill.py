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
import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("polaris_graph.slot_fill")

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


def _value_matches_span(value: str, source_span: str) -> bool:
    """Codex M-58 audit: after five passes of substring-containment
    exploits, the exploit surface is closed by eliminating the
    distinction entirely.

    `value` and `source_span` must denote the SAME verbatim text.
    They are two names for the same thing: the extracted fact IS
    the source snippet. Any drift between them — character, case,
    sign, digit, unit — is a contract violation.

    Accepted:
      1. value == source_span (strict equality)
      2. whitespace-collapsed(value) == whitespace-collapsed(source_span)
         — LLM whitespace/tab/newline variation only. No other
         normalization.

    History of rejected alternatives that each created an exploit:
      - pass-1: value anywhere in direct_quote (accepted
        value='1880' + span='N=1879').
      - pass-2: value in source_span OR in direct_quote + token
        overlap (accepted span='5 mg' + value='10 mg').
      - pass-3: value in source_span substring, with lowercase
        normalization (accepted span='5 M' + value='5 m' — molar
        vs meter).
      - pass-4: value in source_span bounded by (?<!\\w)needle(?!\\w)
        (accepted span='-0.47%' + value='0.47%' — sign truncation;
        span='Ca2+' + value='Ca2' — ionic-state truncation).

    pass-5 resolution: value MUST equal source_span. The LLM prompt
    is aligned to this: "value and source_span must be the same
    verbatim substring of direct_quote". Ambiguity about which
    part of a longer span represents "the fact" is resolved by
    requiring the LLM to pick exactly one form.

    For M-58 consumers: `render_slot_prose` uses `value` verbatim,
    so the prose reflects exactly what the LLM quoted. If the
    span has context the clinician should see (e.g. "N=1879"),
    both value AND span carry it.
    """
    if not value or not source_span:
        return False
    if value == source_span:
        return True
    # Sole remaining normalization: whitespace collapse. Does NOT
    # affect case, digits, units, signs, punctuation, or diacritics.
    if _whitespace_collapse(value) == _whitespace_collapse(source_span):
        return True
    return False


def _whitespace_collapse(s: str) -> str:
    """Collapse runs of whitespace (space, tab, newline) to a single
    space; strip leading/trailing whitespace. No other
    normalization."""
    return " ".join(s.split())


def _whitespace_tolerant_substring(needle: str, haystack: str) -> bool:
    """V30 Phase-2 M-66a-R: whitespace-tolerant substring test.

    Returns True iff `needle` appears in `haystack` when both are
    compared after collapsing runs of whitespace to single spaces.
    Case-sensitive, character-exact otherwise — no fuzzy matching,
    no Unicode normalization, no punctuation tolerance.

    Rationale (run-5 diagnostics):
      Regulatory + mechanism entities fetched as 25K-char markdown
      (HTML+PDF extracts) have inconsistent whitespace. An LLM
      naturally echoes "Indications: ... " as a single-space phrase
      even when the source has "Indications:\\n\\n..." structure.
      The strict `needle in haystack` check rejected 5 of 6
      regulatory extractions and 1 mechanism extraction in run-5.

    Anti-fabrication preserved:
      The function rejects any needle whose non-whitespace content
      doesn't appear in haystack. Case is preserved. Content
      insertions/substitutions/deletions all fail.
    """
    if not needle or not haystack:
        return False
    # Fast path: exact match preserves backwards-compat + cheap.
    if needle in haystack:
        return True
    # Whitespace-tolerant path
    n = _whitespace_collapse(needle)
    h = _whitespace_collapse(haystack)
    return n in h


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
                "value": (
                    "<verbatim substring of direct_quote — MUST equal "
                    "source_span — or null when not_extractable>"
                ),
                "source_span": (
                    "<verbatim substring of direct_quote — MUST equal "
                    "value — or null when not_extractable>"
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
        f"its value as a verbatim substring of DIRECT_QUOTE "
        f"(value and source_span MUST be IDENTICAL strings), OR mark "
        f"status=not_extractable with value=null and source_span=null.\n"
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
        f"3. When status=extracted: `value` and `source_span` MUST be "
        f"byte-identical strings (modulo whitespace collapse), both "
        f"copied verbatim from DIRECT_QUOTE. Do not truncate. Do not "
        f"normalize case. Do not drop signs, units, or punctuation.\n"
        f"4. Do NOT add fields outside the required list.\n"
        f"5. Do NOT cite anything other than {bound_ev_id}.\n"
        f"6. If DIRECT_QUOTE does not state a field, use "
        f"status=not_extractable. Do NOT guess. Do NOT infer.\n"
        f"7. To extract a number with surrounding context (e.g. 'N=1879' "
        f"to document what the N refers to), quote the full phrase "
        f"for BOTH value and source_span. If you want just the bare "
        f"number '1879', quote exactly '1879' for BOTH. Never mix.\n"
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
            # V30 Phase-2 M-66a-R (Codex-predicted verifier relaxation,
            # now data-indicated after run-5 showed 6 parse failures
            # on regulatory + mechanism entities when direct_quote is
            # full-text markdown with non-canonical whitespace):
            # the verbatim substring check must tolerate whitespace
            # differences. LLMs naturally normalize whitespace when
            # echoing content, and HTML/PDF-extracted markdown often
            # has `\n\n` between tokens that appear as single spaces
            # in the LLM-quoted source_span. Without this relaxation
            # virtually no field extracts successfully from a 25K
            # char regulatory page.
            #
            # The relaxation is WHITESPACE-ONLY: source_span and
            # direct_quote are compared after collapsing consecutive
            # whitespace (incl newlines) to a single space. It does
            # NOT tolerate character substitutions, case changes, or
            # content insertions — those still fail. So the anti-
            # fabrication guarantee (LLM MUST ground value in source
            # text) is preserved. Case-sensitivity is also preserved
            # (prevents adversarial case-folding exploits).
            # V30 Phase-2 M-69 Fix #5 (Codex run-10 audit —
            # SURMOUNT-2 regression): per-field anti-fabrication
            # failures used to nuke the WHOLE payload via
            # SlotFillParseError → _build_not_extractable_payload
            # (all-fields not_extractable). Run-10 SURMOUNT-2 lost
            # 9 valid fields because etd_with_uncertainty alone
            # failed verbatim-substring. Surgical degrade: convert
            # this single field to not_extractable instead of
            # killing the entire payload. Anti-fabrication
            # guarantee preserved — the broken field is excluded
            # from output; the legitimate fields survive.
            if not _whitespace_tolerant_substring(
                source_span, direct_quote,
            ):
                logger.warning(
                    "[m58] field %r failed source_span verbatim "
                    "check; degrading to not_extractable "
                    "(M-69 Fix #5)", fname,
                )
                status = "not_extractable"
                value = None
                source_span = None
            elif not _value_matches_span(value, source_span):
                # Codex M-58 audit Blocker (pass 1→5): value and
                # source_span must denote the identical verbatim
                # text. M-69 Fix #5 surgical degrade applies here
                # too — broken fields salvaged as not_extractable.
                logger.warning(
                    "[m58] field %r failed value/span identity "
                    "check; degrading to not_extractable "
                    "(M-69 Fix #5)", fname,
                )
                status = "not_extractable"
                value = None
                source_span = None
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

# Gap-disclosure marker — the canonical substring M-59 validator
# looks for to confirm explicit gap language is present. Exposed
# as module-level constant so M-59 imports this single source of
# truth (Codex M-59 audit Nit) rather than duplicating the English
# phrase. If M-60 later owns the template, it can override
# GAP_PROSE_MARKER while preserving the invariant.
GAP_PROSE_MARKER = "was not retrievable"

# NOTE: the gap-prose template below is a STOPGAP owned by M-58 until
# M-60 ships. Codex M-58 audit Nit: surface-language policy belongs
# in M-60 (the manifest/report-surface layer). When M-60 lands it
# should either pass a `gap_template` parameter to render_slot_prose
# or subclass the renderer. Until then this string lives here so the
# pipeline has an honest failure sentence today. The phrase MUST
# contain GAP_PROSE_MARKER so M-59 validator can detect it.
_GAP_PHRASE = (
    "Primary publication was not retrievable from open-access, "
    "abstract, or metadata sources. All required fields are "
    "unavailable for this entity."
)
assert GAP_PROSE_MARKER in _GAP_PHRASE, (
    "gap template invariant violated — _GAP_PHRASE must contain "
    "GAP_PROSE_MARKER so M-59 can verify gap language"
)


def build_slot_narrative_prompt(
    payload: SlotFillPayload,
    *,
    subsection_title: str,
    research_question: str,
) -> str:
    """v1.1 A.1 option 4c (2026-04-30): build the LLM prompt for
    a narrative paragraph rendered FROM the same SlotFillPayload
    as `render_slot_prose`.

    Two-tier rendering: deterministic field-by-field prose (the
    existing audit-trail path) is emitted first by the caller,
    then this LLM prompt produces a 200-300 word narrative
    paragraph integrating the SAME extracted values into a
    DR-grade paragraph.

    I-faith-001 Fix C — anti-fabrication guarantee (defense-in-depth):
    The narrative paragraph is the fabrication-prone stream (run-9: V4
    Pro invented 14%/35%/attrition/CSAT/partial-equilibrium against a
    15%-only span). The HARD gate is structural, in the caller: every
    narrative sentence is re-verified by `verify_sentence_provenance`
    against the cited spans in the rescue-INELIGIBLE narrative stream
    (`run_contract_section` passes `allow_rescue=False`), so any
    sentence not entailed by the span is dropped and CANNOT be rescued
    by the M-69 contract-entity rescue. This prompt tightening is the
    SECOND layer — it instructs the LLM to RESTATE ONLY the provided
    field payloads and to introduce NO new numbers or qualitative
    specifics — so there is less for the gate to drop. The prompt
    string is NOT the enforcement; the per-sentence re-verify is.

    The LLM is given verbatim quoted values + their source spans;
    its job is to weave those values into narrative prose without
    inventing new facts. Citation marker (the bound ev_id) is
    pre-determined; LLM injects [#ev:bound_ev_id] tokens after
    each value.

    Why a separate path from M-50: this re-uses the M-58 payload
    that the contract section runner already has in hand, so we
    don't duplicate the slot-fill LLM call.
    """
    bound = payload.bound_ev_id
    field_lines: list[str] = []
    for field in payload.fields:
        if field.status == "extracted":
            field_lines.append(
                f"- {field.field_name}: \"{field.value}\""
            )
    if not field_lines:
        return ""
    fields_block = "\n".join(field_lines)
    return f"""You are writing one PER-ENTITY NARRATIVE PARAGRAPH for a top-tier Deep Research clinical report (the depth of GPT-5.4 DR / Gemini 3.1 Pro DR — those competitors produce 200-400 word per-entity narrative blocks, not 60-110 word fact-bullets).

Subsection: {subsection_title}
Research question: {research_question}

VERBATIM-EXTRACTED FIELDS FROM PRIMARY SOURCE (use ONLY these values, do not invent):
{fields_block}

Source citation marker (use verbatim with no modification): [{bound}]

TASK: Weave the extracted fields above into a 14-20 sentence narrative paragraph (300-450 words). Each factual sentence must end with the citation marker [{bound}] before the period. The marker uses the bare-bracket format `[{bound}]` — the post-processor converts it to a span token automatically. Use AT LEAST 2-3 contrast markers ("however", "in contrast", "whereas", "by comparison", "although", "despite") per paragraph when the extracted fields support contrastive framing.

NARRATIVE STYLE (matching top-tier DR competitors):
- ONE flowing paragraph, NOT bullet points or "Field: value" listings
- Integrate fields contextually: lead with study/entity introduction, then design + population, then dose/comparator, then primary endpoint + result, then secondary findings, then safety/limitation context
- Use connective synthesis: "In this trial...", "By comparison...", "However...", "In contrast...", "The treatment difference was...", "Secondary outcomes included...", "Adverse events were dose-related..."
- USE CONTRAST MARKERS when supported by the extracted values: "however", "in contrast", "whereas", "by comparison", "although", "despite". Top-tier DR uses 1 contrast marker per ~200 words.
- Integrate clinical interpretation in the comparator-class context (e.g., "consistent with the broader GLP-1 / GIP dual-agonist mechanism literature") ONLY when the extracted fields support that framing — do NOT invent context.

VERBATIM CONSTRAINT (CRITICAL — every sentence is independently re-verified by verify_sentence_provenance against the cited spans AFTER you write it, and any sentence that is not entailed by the cited span is DROPPED from the report and CANNOT be rescued):
- RESTATE ONLY the provided field payloads above. You are re-expressing already-verified facts in flowing prose — you are NOT adding information.
- Every numeric value must come VERBATIM from the extracted fields above (preserve unit + sign + decimal places exactly). Do not introduce any number, percentage, count, duration, or date that does not appear verbatim in the extracted fields.
- Do not introduce new NAMED CONCEPTS, metrics, mechanisms, outcomes, subgroups, or causal claims that are not present in the extracted field values. Specifically forbidden unless they appear verbatim in the fields above: attrition, churn, retention, satisfaction (CSAT/NPS), equilibrium / partial-equilibrium effects, spillovers, or any endpoint/population not listed in the fields.
- Do not introduce study names, comparators, or trial identifiers that aren't in the extracted fields.
- If a field is missing (e.g., no comparator value), do not invent it — phrase as "the comparator details were not extractable from the cited primary source".
- When in doubt, say LESS: a shorter paragraph that only restates the fields is correct; a longer paragraph that adds unstated specifics will be dropped at verification.

OUTPUT: plain prose, ONE paragraph (14-20 sentences, 300-450 words). No heading, no bullet list, no preamble. Just the paragraph body. Every factual sentence ends with [{bound}] before its period."""


def render_slot_prose(payload: SlotFillPayload) -> str:
    """Render the SlotFillPayload into deterministic BODY-ONLY
    prose with `[bound_ev_id]` citations INSIDE each sentence
    (before terminal punctuation).

    Phase-2 revisions (Codex pass-1 rev #2 + rev #3 + pass-2):
      - Body-only: no `{subsection_title}:` prefix. Subsection
        heading emission is the caller's responsibility (M-63
        `_run_contract_section` emits `### {subsection_title}`
        separately).
      - Citation attached to sentence: `value [id].` (period
        AFTER citation). Earlier Phase-1 format `value. [id]`
        caused strict_verify's sentence splitter to drop the
        citation into the next sentence.

    Format:
      "<field1_name>: <value> [bound_ev_id]. "
      "<field2_name>: <value> [bound_ev_id]. ..."

    Same payload → byte-identical prose. No LLM, no randomness.

    Gap slot (all fields gap_unrecoverable): emits the explicit
    M-60 gap sentence with citation inside terminal punctuation.
    """
    bound = payload.bound_ev_id
    all_gap = all(
        f.status == "gap_unrecoverable" for f in payload.fields
    )
    if all_gap:
        # Strip the trailing period on _GAP_PHRASE so we can
        # emit citation BEFORE the period.
        gap_text = _GAP_PHRASE.rstrip(".")
        return f"{gap_text} [{bound}]."

    # Render each field as a sentence that starts with a
    # Title-cased field name. strict_verify's sentence splitter
    # matches `.` + whitespace + [A-Z\[], so a leading capital
    # is needed for each sentence boundary to trigger.
    sentences: list[str] = []
    for field in payload.fields:
        # Title-case the first character of field_name so the
        # sentence splitter triggers. Underscore→space for
        # readability (e.g. "etd_with_uncertainty" →
        # "Etd with uncertainty").
        label = field.field_name.replace("_", " ")
        label = label[:1].upper() + label[1:] if label else label
        if field.status == "extracted":
            sentences.append(
                f"{label}: {field.value} [{bound}]."
            )
        elif field.status == "not_extractable":
            sentences.append(
                f"{label}: {_NOT_EXTRACTABLE_PHRASE} [{bound}]."
            )
        else:  # gap_unrecoverable mixed into partial slot
            sentences.append(
                f"{label}: primary source unavailable [{bound}]."
            )
    return " ".join(sentences)
