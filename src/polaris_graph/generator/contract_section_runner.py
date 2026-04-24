"""V30 Phase-2 M-63 — contract-driven section runner.

Replaces legacy per-section LLM prompts with M-58 slot-bound
prose for entities that have a FrameRow. Returns the same
`SectionResult` shape as legacy `_run_section` so downstream
assembly is unchanged.

## Architecture (per Phase-2 plan M-63 Fix #1)

- SECTION-level SectionResult, NOT slot-level. Each contract
  section (Efficacy, Mechanism, Regulatory for clinical)
  becomes ONE SectionResult whose verified_text concatenates
  `### {subsection_title}` headings + M-58 body prose per
  slot.
- Multi-entity slots render N blocks, each with its own
  `[bound_ev_id]` citation.
- Gap rows skip the LLM via `compose_gap_payload`.
- Non-gap rows call `build_slot_fill_prompt` → LLM → JSON →
  `parse_slot_fill_response` (raises on fabrication).
- Contract entity ids are registered into `evidence_pool` keyed
  by entity_id so the generalized citation-rewrite regex
  (M-63 Fix #3) resolves `[surpass_2_primary]` markers.

## Dispatch

`ContractSectionPlanExt` subclasses `SectionPlan`. When the
legacy orchestration loop sees an instance, it calls
`_run_contract_section(plan, ...)` instead of the legacy
`_run_section`. This is how `generate_multi_section_report`
routes contract vs legacy prose.

## No legacy overlap

- M-41c (under-framed trial sentences) is no-op by construction:
  body sentences carry `field: value [id].` format, no trial
  short-names. M-41c keys on short-names.
- M-44 (primary-citation validator) passes trivially: every
  sentence cites the bound ev_id.
- M-50 per-trial subsection generator is SKIPPED for entities
  whose anchor maps to a contract slot (integration layer
  enforces this).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..nodes.contract_outline import ContractSectionPlan, ContractSlotPlan
from ..nodes.report_contract import RequiredEntity
from ..retrieval.frame_fetcher import FrameRow, ProvenanceClass
from .slot_fill import (
    SlotFillParseError,
    SlotFillPayload,
    build_slot_fill_prompt,
    compose_gap_payload,
    parse_slot_fill_response,
    render_slot_prose,
)

if TYPE_CHECKING:
    from .multi_section_generator import SectionPlan, SectionResult

logger = logging.getLogger("polaris_graph.contract_section_runner")


@dataclass
class ContractSectionPlanExt:
    """Extended section plan carrying the contract info needed
    to dispatch to `_run_contract_section`. Mirrors
    `SectionPlan`'s public fields so existing orchestration
    code treats it as a drop-in via duck-typing.

    Codex pass-1 Q2 answer: dedicated dispatch type, not a
    sentinel field on legacy `SectionPlan`. This preserves
    contract invariants (slots, frame_rows_by_entity,
    contract_entities_by_id) explicitly.

    Named distinct from M-57's `ContractSectionPlan` per Codex
    pass-2 new issue #3.
    """

    title: str                              # SectionPlan field
    focus: str                              # SectionPlan field
    ev_ids: list[str]                       # SectionPlan field
    # M-63 additions:
    slots: tuple[ContractSlotPlan, ...]
    frame_rows_by_entity: dict[str, FrameRow]
    contract_entities_by_id: dict[str, RequiredEntity]
    research_question: str


def register_frame_rows_into_evidence_pool(
    evidence_pool: dict[str, dict[str, Any]],
    frame_rows: tuple[FrameRow, ...],
) -> None:
    """Register each FrameRow into `evidence_pool` keyed by
    entity_id so the generalized citation-rewrite regex
    (M-63 Fix #3) can resolve `[entity_id]` markers via
    `evidence_pool.get(entity_id)`.

    In-place mutation. Does NOT overwrite existing keys unless
    they're duplicates (M-61 curator-supplied row would land
    here too and we want it to win over any pre-existing stale
    entry keyed by the same entity_id).

    Each synthesized evidence_pool entry carries:
      - evidence_id: entity_id (what the rewriter expects)
      - direct_quote: FrameRow.direct_quote (what strict_verify
        compares against)
      - url: FrameRow.oa_pdf_url or FrameRow.url (for citation
        resolution)
      - title, authors, journal, year: FrameRow metadata
    """
    for row in frame_rows:
        evidence_pool[row.entity_id] = {
            "evidence_id": row.entity_id,
            "direct_quote": row.direct_quote or "",
            "url": row.oa_pdf_url or row.url or "",
            "title": row.title or "",
            "authors": list(row.authors),
            "journal": row.journal or "",
            "year": row.year,
            "doi": row.doi or "",
            "pmid": row.pmid or "",
            "provenance_class": row.provenance_class.value,
            # V30 phase-2 marker
            "v30_frame_row": True,
            "v30_entity_id": row.entity_id,
        }


async def _fill_one_slot(
    slot: ContractSlotPlan,
    entity_id: str,
    frame_row: FrameRow,
    contract_entity: RequiredEntity,
    research_question: str,
    llm_call: Any,  # async callable(prompt) -> (response_text, in_tok, out_tok)
) -> tuple[SlotFillPayload, int, int]:
    """Produce a SlotFillPayload for one (slot, entity) pair.

    Gap rows skip the LLM. Non-gap rows call the LLM via the
    injected `llm_call` closure (so the integration layer
    controls model + temperature + token limits) and parse
    the response.
    """
    required_fields = tuple(contract_entity.required_fields)

    if frame_row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        payload = compose_gap_payload(slot, frame_row, required_fields)
        return payload, 0, 0

    prompt = build_slot_fill_prompt(
        slot, frame_row, required_fields, research_question,
    )
    try:
        response_text, in_tok, out_tok = await llm_call(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[m63] LLM call failed for entity_id=%r slot_id=%r: %s",
            entity_id, slot.slot_id, exc,
        )
        # Fall back to a gap payload so the slot still renders
        # honest content. Strict_verify downstream will drop
        # nothing; M-59 will flag the entity as FAIL_MIN_FIELDS.
        payload = compose_gap_payload(slot, frame_row, required_fields)
        return payload, 0, 0

    try:
        payload = parse_slot_fill_response(
            response_text, slot, frame_row, required_fields,
        )
    except SlotFillParseError as exc:
        logger.warning(
            "[m63] slot-fill parse failed for entity_id=%r: %s",
            entity_id, exc,
        )
        # Build an all-not_extractable payload so the entity
        # shows up in M-60 coverage as a curator-actionable
        # FAIL_MIN_FIELDS, not silently dropped. Can't use
        # `compose_gap_payload` because this isn't a retrieval
        # gap — it's a parse failure on retrieved content.
        from .slot_fill import SlotFieldFill, SlotFillPayload
        fills = tuple(
            SlotFieldFill(
                field_name=fname,
                status="not_extractable",
                value=None,
                bound_ev_id=entity_id,
                source_span=None,
            )
            for fname in required_fields
        )
        payload = SlotFillPayload(
            slot_id=slot.slot_id,
            entity_id=entity_id,
            subsection_title=slot.subsection_title,
            bound_ev_id=entity_id,
            fields=fills,
            provenance_class=frame_row.provenance_class.value,
        )
        return payload, in_tok, out_tok

    return payload, in_tok, out_tok


async def run_contract_section(
    plan: ContractSectionPlanExt,
    evidence_pool: dict[str, dict[str, Any]],
    *,
    llm_call: Any,
    section_result_cls: Any,  # SectionResult class (injected to avoid
                               # circular import)
    strict_verify_fn: Any,     # strict_verify callable (injected)
    rewrite_fn: Any,           # _rewrite_draft_with_spans (injected)
) -> tuple[Any, list[SlotFillPayload]]:
    """Run one contract SECTION. Returns (SectionResult,
    list[SlotFillPayload]). The payloads are threaded back to
    M-64 for real M-59 validation at sweep integration time.

    Legacy assembly code gets a SectionResult with the same
    shape it expects: title / focus / ev_ids_assigned /
    verified_text / biblio_slice / sentence counts / tokens /
    error.
    """
    slot_results: list[str] = []
    payloads: list[SlotFillPayload] = []
    total_in_tok = 0
    total_out_tok = 0
    all_entity_ids: list[str] = []

    for slot in plan.slots:
        if not slot.entity_ids:
            # Defensive: outline compiler shouldn't emit empty slots,
            # but guard anyway.
            continue

        slot_header = f"### {slot.subsection_title}\n\n"
        slot_body_blocks: list[str] = []

        for entity_id in slot.entity_ids:
            all_entity_ids.append(entity_id)
            frame_row = plan.frame_rows_by_entity.get(entity_id)
            contract_entity = plan.contract_entities_by_id.get(entity_id)

            if frame_row is None or contract_entity is None:
                # Pipeline fault — shouldn't happen given M-57
                # validates parallelism. Emit an explicit note.
                slot_body_blocks.append(
                    f"Entity {entity_id!r} frame row or contract "
                    f"entity missing; pipeline fault. Skipping."
                )
                continue

            payload, in_tok, out_tok = await _fill_one_slot(
                slot=slot,
                entity_id=entity_id,
                frame_row=frame_row,
                contract_entity=contract_entity,
                research_question=plan.research_question,
                llm_call=llm_call,
            )
            total_in_tok += in_tok
            total_out_tok += out_tok
            payloads.append(payload)

            # Body prose (M-58 body-only format)
            prose = render_slot_prose(payload)
            slot_body_blocks.append(prose)

        slot_results.append(slot_header + "\n\n".join(slot_body_blocks))

    # Concatenate all slot blocks into one section body
    raw_draft = "\n\n".join(slot_results)

    # Rewrite citation markers to span tokens (M-63 Fix #3
    # generalized regex picks up contract entity ids)
    rewritten_draft, converted, unverifiable = rewrite_fn(
        raw_draft, evidence_pool,
    )

    # Strict verify: keeps only sentences that match their bound
    # evidence. Because M-58 prose is verbatim from direct_quote
    # and M-63 pre-registered FrameRows into evidence_pool, every
    # sentence should pass.
    report = strict_verify_fn(rewritten_draft, evidence_pool)
    kept = report.total_kept
    dropped = report.total_in - kept

    # Reassemble verified text from kept sentences
    kept_sentences = getattr(report, "kept_sentences", None) or []
    verified_text_parts: list[str] = []
    for sv in kept_sentences:
        # SentenceVerification has a .text (or similar) attribute
        text = getattr(sv, "text", None) or getattr(sv, "sentence", None) or str(sv)
        verified_text_parts.append(text)
    # If we lost track of structure, fall back to the rewritten
    # draft verbatim (kept_fraction=100% is the typical path).
    if verified_text_parts:
        verified_text = " ".join(verified_text_parts)
    else:
        verified_text = rewritten_draft if kept > 0 else ""

    dropped_due_to_failure = (kept == 0 and len(all_entity_ids) > 0)

    result = section_result_cls(
        title=plan.title,
        focus=plan.focus,
        ev_ids_assigned=all_entity_ids,
        raw_draft=raw_draft,
        rewritten_draft=rewritten_draft,
        verified_text=verified_text,
        biblio_slice=[],  # biblio is built globally by caller
        sentences_verified=kept,
        sentences_dropped=dropped,
        regen_attempted=False,  # M-63 doesn't regenerate — M-58
                                # fabrication check is per-field
        dropped_due_to_failure=dropped_due_to_failure,
        input_tokens=total_in_tok,
        output_tokens=total_out_tok,
        error="" if kept > 0 else "no_sentences_verified",
    )
    return result, payloads


def is_contract_section(plan: Any) -> bool:
    """Duck-typed check: is this a ContractSectionPlanExt?
    Used by orchestration loop to dispatch without importing
    the extended class (keeps generator edit minimal)."""
    return isinstance(plan, ContractSectionPlanExt)
