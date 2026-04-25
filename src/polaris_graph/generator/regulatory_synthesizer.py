"""V31 — M-70 regulatory synthesizer.

Codex strategic review (2026-04-25, Claude+Codex agreed proposal):
M-58's verbatim-substring contract is too rigid for page-scale
prose synthesis from regulatory pages (FDA labels, EMA EPARs, NICE
TAs, HC monographs). Run-9..run-11 saw 5 of 6 regulatory subsections
render as `not_extractable` stubs even with M-66a-R whitespace
tolerance + M-66b-T full-text fetch.

Root cause: regulatory pages have heterogeneous structure (HTML nav
+ boilerplate + actual content). Field-level verbatim extraction
demanded by M-58 doesn't cleanly hit `Indications: <prose>` style
templates. Prose SYNTHESIS is the right primitive, not field
extraction.

## Pipeline

For each regulatory entity (FDA / EMA / NICE / HC):

  1. SEGMENT — split fetched 25K-char direct_quote into sections
     keyed by jurisdiction-specific headings:
       - FDA labels: "INDICATIONS AND USAGE", "BOXED WARNING",
         "CONTRAINDICATIONS", "WARNINGS AND PRECAUTIONS",
         "DOSAGE AND ADMINISTRATION"
       - EMA EPARs: "Indications", "Contraindications",
         "Special warnings", "Posology", "Adverse reactions"
       - NICE TAs: "Recommendations", "Specialist services",
         "Managed access", "Commercial arrangement"
       - HC monographs: "INDICATIONS", "SERIOUS WARNINGS",
         "CONTRAINDICATIONS", "DOSAGE AND ADMINISTRATION"

  2. SELECT — for each target required_field (e.g. `boxed_warning`,
     `indications`), pick the relevant segment via heading match.

  3. SYNTHESIZE — call the LLM with the selected segment +
     synthesis prompt asking for 2-4 prose sentences that
     summarize the field's content, citing only verbatim phrases
     from the segment.

  4. VERIFY — pass the synthesized sentences through
     whitespace-tolerant strict_verify against the segment.
     Sentences that don't verify get dropped; if all drop, fall
     back to explicit gap language.

## Why a separate module from M-58

- M-58 is FIELD extraction with verbatim-substring anti-fabrication.
  Regulatory entities need PROSE synthesis (multi-clause sentences
  mixing extracted facts + connective language).

- M-58 caps `direct_quote` at the entity level; a regulatory page
  needs SUBSECTION-level segmentation before extraction.

- M-58 verifies each field's source_span against the WHOLE
  direct_quote; regulatory synthesis verifies each sentence
  against a NARROWER segment (lower false-positive rate).

## Output shape

Same SlotFillPayload as M-58, so M-63 dispatch + M-59 validation
treat the output identically. Difference is in the rendering
path: `render_regulatory_prose` emits 2-4 sentence paragraphs
per subsection instead of `Field: value [id].` slot prose.

## Codex pass-1 review pending

Before integration, this module's design needs Codex review for:
  - segmentation correctness (regulatory heading regex coverage)
  - LLM prompt anti-fabrication discipline
  - fallback path correctness when no segment matches
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ..nodes.contract_outline import ContractSlotPlan
from ..nodes.report_contract import RequiredEntity
from ..retrieval.frame_fetcher import FrameRow
from .slot_fill import (
    SlotFieldFill,
    SlotFillPayload,
    _whitespace_tolerant_substring,
)

logger = logging.getLogger("polaris_graph.regulatory_synthesizer")


# ─────────────────────────────────────────────────────────────────────
# Heading taxonomy
# ─────────────────────────────────────────────────────────────────────
# Map jurisdiction → ordered list of heading patterns. Each pattern
# is a regex matched case-insensitively. The first pattern in the
# list that matches a heading line in direct_quote wins for that
# subsection.
#
# Patterns are designed to be DEFENSIVE — match the canonical
# heading + common variants seen in FDA/EMA/NICE/HC pages, but
# avoid matching prose mentions of the same words.
_FDA_HEADINGS: dict[str, tuple[str, ...]] = {
    "indications": (
        r"^\s*1\s+INDICATIONS\s+AND\s+USAGE\s*$",
        r"^\s*INDICATIONS\s+AND\s+USAGE\s*$",
        r"^\s*\*+\s*Indications\s+and\s+Usage\s*\*+\s*$",
    ),
    "boxed_warning": (
        r"^\s*WARNING\s*:\s*RISK\s+OF\s+THYROID",
        r"^\s*BOXED\s+WARNING\s*$",
        r"^\s*WARNING\s*:",
    ),
    "contraindications": (
        r"^\s*4\s+CONTRAINDICATIONS\s*$",
        r"^\s*CONTRAINDICATIONS\s*$",
    ),
    "warnings_and_precautions": (
        r"^\s*5\s+WARNINGS\s+AND\s+PRECAUTIONS\s*$",
        r"^\s*WARNINGS\s+AND\s+PRECAUTIONS\s*$",
    ),
    "dosing": (
        r"^\s*2\s+DOSAGE\s+AND\s+ADMINISTRATION\s*$",
        r"^\s*DOSAGE\s+AND\s+ADMINISTRATION\s*$",
        r"^\s*DOSING\s+INFORMATION\s*$",
    ),
    "bmi_thresholds": (
        r"BMI\s+(?:of\s+)?(?:>=|≥|greater\s+than\s+or\s+equal)",
        r"body\s+mass\s+index",
    ),
}

_EMA_HEADINGS: dict[str, tuple[str, ...]] = {
    "indications": (
        r"^\s*Therapeutic\s+indication[s]?\s*$",
        r"^\s*4\.1\.?\s+Therapeutic\s+indication",
    ),
    "contraindications": (
        r"^\s*4\.3\.?\s+Contraindication",
        r"^\s*Contraindication[s]?\s*$",
    ),
    "additional_monitoring": (
        r"additional\s+monitoring",
        r"^\s*Black\s+symbol",
    ),
    "pediatric_indication": (
        r"paediatric\s+(?:population|use)",
        r"pediatric\s+(?:population|use)",
        r"adolescents?\s+aged\s+\d+",
    ),
    "osa_extension": (
        r"obstructive\s+sleep\s+apno?ea",
        r"\bOSA\b",
    ),
}

_NICE_HEADINGS: dict[str, tuple[str, ...]] = {
    "triple_therapy_criteria": (
        r"triple\s+therapy",
        r"third[- ]line",
    ),
    "bmi_threshold": (
        r"BMI\s+(?:of\s+)?(?:>=|≥|greater)",
        r"body\s+mass\s+index",
    ),
    "ethnic_adjusted_thresholds": (
        r"ethnicity[- ]adjusted",
        r"south[- ]asian",
    ),
    "occupational_implications": (
        r"occupation[a-z]*\s+implication",
    ),
    "commercial_arrangement": (
        r"commercial\s+(?:access\s+)?(?:agreement|arrangement)",
        r"patient\s+access\s+scheme",
    ),
    "indication": (
        r"^\s*Recommendation[s]?\s*$",
        r"is\s+recommended\s+as\s+an\s+option",
    ),
    "managed_access_agreement": (
        r"managed\s+access\s+agreement",
    ),
    "specialist_services_requirement": (
        r"specialist\s+(?:weight\s+management\s+)?service",
    ),
}

_HC_HEADINGS: dict[str, tuple[str, ...]] = {
    "indications": (
        r"^\s*1\s+INDICATIONS\s*$",
        r"^\s*INDICATIONS\s*$",
    ),
    "serious_warnings_box": (
        r"^\s*2\s+(?:SERIOUS\s+WARNINGS|CONTRAINDICATIONS)",
        r"SERIOUS\s+WARNINGS\s+AND\s+PRECAUTIONS\s+BOX",
    ),
    "contraindications": (
        r"^\s*3\s+CONTRAINDICATIONS\s*$",
        r"^\s*CONTRAINDICATIONS\s*$",
    ),
    "dosing": (
        r"^\s*4\s+DOSAGE\s+AND\s+ADMINISTRATION\s*$",
        r"^\s*DOSAGE\s+AND\s+ADMINISTRATION\s*$",
    ),
}


def _heading_table_for_jurisdiction(
    jurisdiction: str | None,
) -> dict[str, tuple[str, ...]]:
    if not jurisdiction:
        return {}
    j = jurisdiction.upper()
    return {
        "FDA": _FDA_HEADINGS,
        "EMA": _EMA_HEADINGS,
        "NICE": _NICE_HEADINGS,
        "HC": _HC_HEADINGS,
    }.get(j, {})


# ─────────────────────────────────────────────────────────────────────
# Segmentation
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Segment:
    """One labeled prose chunk extracted from a regulatory page."""
    field_name: str  # one of the entity's required_fields
    text: str        # the prose chunk that matched the heading


def _segment_regulatory_text(
    direct_quote: str,
    required_fields: tuple[str, ...],
    jurisdiction: str | None,
    *,
    max_chars_per_segment: int = 2000,
) -> dict[str, _Segment]:
    """Return field_name -> _Segment for each required_field whose
    heading matched somewhere in `direct_quote`.

    Segmentation strategy: for each field, find the FIRST line in
    direct_quote that matches one of the field's heading patterns,
    then take the next `max_chars_per_segment` characters as the
    segment body. Skip fields whose heading doesn't match.

    `jurisdiction` selects which heading table to use (FDA/EMA/NICE/HC).
    """
    if not direct_quote:
        return {}
    table = _heading_table_for_jurisdiction(jurisdiction)
    if not table:
        return {}

    segments: dict[str, _Segment] = {}
    lines = direct_quote.split("\n")
    for fname in required_fields:
        patterns = table.get(fname)
        if not patterns:
            continue
        compiled = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns
        ]
        # Find the first matching line index.
        match_idx: int | None = None
        for i, line in enumerate(lines):
            if any(c.search(line) for c in compiled):
                match_idx = i
                break
        if match_idx is None:
            continue
        # Take the matched line + next ~30 lines, capped at max chars.
        chunk_lines = lines[match_idx:match_idx + 30]
        chunk = "\n".join(chunk_lines)[:max_chars_per_segment]
        if chunk.strip():
            segments[fname] = _Segment(field_name=fname, text=chunk)
    return segments


# ─────────────────────────────────────────────────────────────────────
# Synthesis prompt
# ─────────────────────────────────────────────────────────────────────
def build_regulatory_synthesis_prompt(
    slot_plan: ContractSlotPlan,
    frame_row: FrameRow,
    contract_entity: RequiredEntity,
    field_segments: dict[str, _Segment],
    research_question: str,
) -> str:
    """Compose the LLM prompt for regulatory synthesis.

    Asks the LLM to emit 2-4 prose sentences PER FIELD, each
    sentence quoting verbatim phrases from the matched segment.
    Output JSON shape mirrors M-58 SlotFillPayload but `value` is
    a multi-sentence prose string instead of a single phrase.
    """
    bound_ev_id = frame_row.entity_id
    label = contract_entity.label_name or contract_entity.id
    juris = contract_entity.jurisdiction or "regulatory authority"

    bullets = []
    for fname, seg in field_segments.items():
        bullets.append(
            f"\n  --- field={fname} ---\n  SEGMENT TEXT:\n  <<<\n{seg.text}\n  >>>"
        )

    prompt = (
        "You are a regulatory affairs writer summarizing official "
        f"{juris} label content for the entity {label!r}.\n"
        "\n"
        "RESEARCH QUESTION (for reader context): "
        f"{research_question}\n"
        "\n"
        "For each FIELD below, write 2-4 short prose sentences "
        "(50-80 words total per field) that summarize the SEGMENT TEXT. "
        "EVERY phrase you write that conveys a substantive fact MUST "
        "appear verbatim in the segment text — you may add connective "
        "words like 'The label states that' or 'According to the EPAR' "
        "but the substantive content must be lifted from the segment.\n"
        "\n"
        "If the segment text does NOT contain enough information to "
        "write 2 substantive sentences for a field, mark that field "
        "as not_extractable.\n"
        "\n"
        f"BOUND_EV_ID: {bound_ev_id} (cite this id; do NOT cite anything else)\n"
        f"{''.join(bullets)}\n"
        "\n"
        "Return ONLY JSON in this exact shape:\n"
        '{\n'
        '  "fields": [\n'
        '    {\n'
        '      "field_name": "<exact field name from the list above>",\n'
        '      "status": "extracted | not_extractable",\n'
        '      "value": "<2-4 sentence prose paragraph, or null when not_extractable>",\n'
        '      "source_span": "<verbatim quote of the longest substantive phrase from the segment, or null>"\n'
        '    }\n'
        '  ]\n'
        '}\n'
        "\n"
        "Rules:\n"
        "1. Output ONE entry per field listed above, in the same order.\n"
        "2. status MUST be `extracted` or `not_extractable` (no other values).\n"
        "3. When extracted: value is a 50-80 word paragraph; source_span "
        "is the longest substantive phrase you used, taken verbatim from "
        "the segment.\n"
        "4. When not_extractable: value=null, source_span=null.\n"
        "5. Do not invent facts. Do not cite anything other than "
        f"{bound_ev_id}.\n"
    )
    return prompt


# ─────────────────────────────────────────────────────────────────────
# Response parsing + verification
# ─────────────────────────────────────────────────────────────────────
class RegulatorySynthesisError(Exception):
    """Raised when the LLM response cannot be parsed at all."""


def parse_regulatory_synthesis_response(
    response_text: str,
    slot_plan: ContractSlotPlan,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
    field_segments: dict[str, _Segment],
) -> SlotFillPayload:
    """Parse LLM JSON → SlotFillPayload with whitespace-tolerant
    verification of each prose value against its source segment.

    Surgical-degrade discipline (matches M-69 Fix #5): per-field
    failures downgrade the single field to not_extractable instead
    of nuking the whole payload.
    """
    import json
    if not isinstance(response_text, str):
        raise RegulatorySynthesisError(
            f"response must be str, got {type(response_text).__name__}"
        )

    raw = response_text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2:
            raw = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegulatorySynthesisError(
            f"invalid JSON: {exc.msg} at pos {exc.pos}"
        ) from exc

    if not isinstance(data, dict):
        raise RegulatorySynthesisError(
            f"response root must be object, got {type(data).__name__}"
        )
    fields_raw = data.get("fields")
    if not isinstance(fields_raw, list):
        raise RegulatorySynthesisError(
            f"'fields' must be list, got {type(fields_raw).__name__}"
        )

    by_name: dict[str, dict] = {}
    for f in fields_raw:
        if not isinstance(f, dict):
            continue
        fname = f.get("field_name")
        if isinstance(fname, str) and fname.strip():
            by_name[fname] = f

    bound_ev_id = frame_row.entity_id
    fills: list[SlotFieldFill] = []
    for fname in required_fields:
        f = by_name.get(fname)
        # Missing field — not_extractable.
        if f is None:
            fills.append(SlotFieldFill(
                field_name=fname,
                status="not_extractable",
                value=None,
                bound_ev_id=bound_ev_id,
                source_span=None,
            ))
            continue

        status = f.get("status")
        if status not in ("extracted", "not_extractable"):
            # Treat invalid status as not_extractable (surgical degrade).
            logger.warning(
                "[m70] field %r has invalid status %r; "
                "downgrading to not_extractable", fname, status,
            )
            fills.append(SlotFieldFill(
                field_name=fname, status="not_extractable",
                value=None, bound_ev_id=bound_ev_id, source_span=None,
            ))
            continue

        if status == "not_extractable":
            fills.append(SlotFieldFill(
                field_name=fname, status="not_extractable",
                value=None, bound_ev_id=bound_ev_id, source_span=None,
            ))
            continue

        # status == "extracted" — verify source_span against segment.
        value = f.get("value")
        source_span = f.get("source_span")

        if not isinstance(value, str) or not value.strip():
            logger.warning(
                "[m70] field %r missing value; downgrading", fname,
            )
            fills.append(SlotFieldFill(
                field_name=fname, status="not_extractable",
                value=None, bound_ev_id=bound_ev_id, source_span=None,
            ))
            continue
        if not isinstance(source_span, str) or not source_span.strip():
            logger.warning(
                "[m70] field %r missing source_span; downgrading", fname,
            )
            fills.append(SlotFieldFill(
                field_name=fname, status="not_extractable",
                value=None, bound_ev_id=bound_ev_id, source_span=None,
            ))
            continue

        # Verify source_span appears verbatim in the segment.
        seg = field_segments.get(fname)
        if seg is None or not _whitespace_tolerant_substring(
            source_span, seg.text,
        ):
            logger.warning(
                "[m70] field %r source_span not in segment; "
                "downgrading to not_extractable", fname,
            )
            fills.append(SlotFieldFill(
                field_name=fname, status="not_extractable",
                value=None, bound_ev_id=bound_ev_id, source_span=None,
            ))
            continue

        # Passed verification — keep the prose value.
        fills.append(SlotFieldFill(
            field_name=fname,
            status="extracted",
            value=value,
            bound_ev_id=bound_ev_id,
            source_span=source_span,
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
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────
def is_regulatory_entity(contract_entity: RequiredEntity) -> bool:
    """True if the entity should be routed through M-70 instead of M-58."""
    return contract_entity.type == "regulatory"


def render_regulatory_prose(payload: SlotFillPayload) -> str:
    """Render a regulatory SlotFillPayload as a multi-paragraph block.

    Each extracted field becomes its own paragraph, prefixed by the
    Title-Cased field label. Not_extractable fields are skipped
    (regulatory subsections are MORE useful as a partial paragraph
    set than as a full `Field: not extractable` stub list).

    If ALL fields are not_extractable, returns empty string — caller
    handles the gap-disclosure fallback (same surface as M-58).
    """
    sentences: list[str] = []
    for field in payload.fields:
        bound = field.bound_ev_id or payload.bound_ev_id
        if field.status == "extracted" and field.value:
            label = field.field_name.replace("_", " ")
            label = label[:1].upper() + label[1:] if label else label
            value = field.value.rstrip(".").rstrip()
            sentences.append(f"{label}. {value} [{bound}].")
        # not_extractable + gap_unrecoverable: skip; gap-disclosure
        # fallback at section level handles them.
    return " ".join(sentences)
