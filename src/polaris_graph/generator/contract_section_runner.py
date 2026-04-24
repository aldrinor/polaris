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

    In-place mutation. Each synthesized evidence_pool entry carries:
      - evidence_id: entity_id (what the rewriter expects)
      - direct_quote: FrameRow.direct_quote (what strict_verify
        compares against)
      - url: FrameRow.oa_pdf_url or FrameRow.url (for citation
        resolution)
      - title, authors, journal, year: FrameRow metadata
      - v30_frame_row: True (marker for this path)

    Codex M-63 REJECT Medium 3 namespace-collision guard:

    Contract entity ids are validated at M-54 load time to NOT
    match the live-retrieval `^ev_\\d+$` pattern. That's the first
    line of defense. This registration path adds defense-in-depth:
    if the incoming evidence_pool already has a row at this key
    AND that row is NOT a v30_frame_row (i.e., it's a live-
    retrieval or legacy-pipeline row), raise rather than clobber.
    A loud error here beats a silent generator misattribution.
    Pre-existing v30_frame_row entries (e.g., from M-61 curator
    completions) may be overwritten — that's the intended
    curator-supplied wins semantics.
    """
    for row in frame_rows:
        existing = evidence_pool.get(row.entity_id)
        if existing is not None and not existing.get("v30_frame_row"):
            raise ValueError(
                f"evidence_pool collision at entity_id={row.entity_id!r}: "
                f"a non-v30 pool row already occupies this key. Contract "
                f"entity ids must not collide with live-retrieval keys. "
                f"M-54 schema validation should have prevented this; "
                f"loader may be out of sync."
            )
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


def _build_not_extractable_payload(
    slot: ContractSlotPlan,
    entity_id: str,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
) -> SlotFillPayload:
    """Build an all-not_extractable SlotFillPayload for a non-gap
    row where the LLM failed (network error, schema parse error,
    etc.). The payload still cites the bound ev_id so M-59 surfaces
    it as FAIL_MIN_FIELDS (curator-actionable) rather than silently
    dropping the entity.

    Cannot use `compose_gap_payload` — that helper hard-raises on
    non-gap provenance by design (Codex M-58 audit symmetric guard
    against routing bugs).
    """
    from .slot_fill import SlotFieldFill, SlotFillPayload as _SFP
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
    return _SFP(
        slot_id=slot.slot_id,
        entity_id=entity_id,
        subsection_title=slot.subsection_title,
        bound_ev_id=entity_id,
        fields=fills,
        provenance_class=frame_row.provenance_class.value,
    )


async def _fill_one_slot(
    slot: ContractSlotPlan,
    entity_id: str,
    frame_row: FrameRow,
    contract_entity: RequiredEntity,
    research_question: str,
    llm_call: Any,  # async callable(prompt) -> (response_text, in_tok, out_tok)
) -> tuple[SlotFillPayload, int, int]:
    """Produce a SlotFillPayload for one (slot, entity) pair.

    Three paths:
      - gap row (FRAME_GAP_UNRECOVERABLE): `compose_gap_payload`, no LLM call.
      - non-gap row, LLM raises (network / timeout):
        `_build_not_extractable_payload`, fail-loud via M-59 FAIL_MIN_FIELDS.
      - non-gap row, parse raises: `_build_not_extractable_payload`.
      - non-gap row, happy path: `parse_slot_fill_response`.

    Codex M-63 REJECT Blocker 2 fix: non-gap LLM-exception path
    previously called `compose_gap_payload`, which hard-raises on
    non-gap provenance. That turned a planned honest fallback into
    a hard pipeline failure. Now both exception paths route to
    `_build_not_extractable_payload` (see its docstring for rationale).
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
        payload = _build_not_extractable_payload(
            slot, entity_id, frame_row, required_fields,
        )
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
        payload = _build_not_extractable_payload(
            slot, entity_id, frame_row, required_fields,
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

    Legacy-compatible output shape (Codex M-63 REJECT Blocker 3):

    - `verified_text` has `[N]` numbered-citation markers (NOT raw
      `[#ev:...]` span tokens) so report.md renders as a reader
      expects.
    - `biblio_slice` is a populated list of
      {num, evidence_id, url, tier, statement} dicts so the global
      bibliography merge + per-section [N] remap both work.
    - `### {subsection_title}` headings are re-injected AFTER
      strict_verify and citation resolution, grouped by slot, so
      strict_verify never sees heading prose (it would fail the
      content-word overlap check).
    """
    from .provenance_generator import resolve_provenance_to_citations

    payloads: list[SlotFillPayload] = []
    total_in_tok = 0
    total_out_tok = 0
    all_entity_ids: list[str] = []

    # entity_id -> slot_id so kept sentences can be regrouped into
    # slot blocks after strict_verify.
    entity_to_slot_id: dict[str, str] = {}
    # slot_id -> subsection_title + preserve order from outline
    slot_order: list[str] = []
    slot_subsection: dict[str, str] = {}

    # Per-slot raw prose blocks (body-only — no headings) so the
    # text handed to strict_verify has no non-sentence lines.
    raw_body_blocks: list[str] = []

    for slot in plan.slots:
        if not slot.entity_ids:
            # Defensive: outline compiler shouldn't emit empty slots,
            # but guard anyway.
            continue

        slot_order.append(slot.slot_id)
        slot_subsection[slot.slot_id] = slot.subsection_title

        slot_body_prose: list[str] = []
        for entity_id in slot.entity_ids:
            all_entity_ids.append(entity_id)
            entity_to_slot_id[entity_id] = slot.slot_id
            frame_row = plan.frame_rows_by_entity.get(entity_id)
            contract_entity = plan.contract_entities_by_id.get(entity_id)

            if frame_row is None or contract_entity is None:
                # Pipeline fault — shouldn't happen given M-57
                # validates parallelism. Skip silently; M-59 will
                # surface the missing entity as FAIL_MISSING_PAYLOAD.
                logger.warning(
                    "[m63] pipeline fault: entity_id=%r missing "
                    "frame_row=%s or contract_entity=%s",
                    entity_id,
                    frame_row is None,
                    contract_entity is None,
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

            prose = render_slot_prose(payload)
            slot_body_prose.append(prose)

        if slot_body_prose:
            raw_body_blocks.append(" ".join(slot_body_prose))

    # Body-only raw draft (no `### headings` — they'd poison
    # strict_verify's content-overlap check).
    raw_draft = " ".join(raw_body_blocks)

    # Rewrite citation markers to span tokens (M-63 Fix #3
    # generalized regex picks up contract entity ids registered
    # into evidence_pool by the integration layer).
    rewritten_draft, converted, unverifiable = rewrite_fn(
        raw_draft, evidence_pool,
    )

    # Strict verify — every sentence is `Field: value [#ev:...]`
    # and the span comes from FrameRow.direct_quote, so the
    # content-overlap check should trivially pass.
    report = strict_verify_fn(rewritten_draft, evidence_pool)
    kept = report.total_kept
    dropped = report.total_in - kept

    kept_sentences = getattr(report, "kept_sentences", None) or []

    # ── resolve provenance → [N] citations + biblio_slice ──────
    # `resolve_provenance_to_citations` flattens into a single
    # string. We need per-slot grouping AND legacy-shape output,
    # so we call it first to get the resolved body + biblio, then
    # re-thread the resolution through the slot boundaries.
    resolved_body, biblio_slice = resolve_provenance_to_citations(
        kept_sentences, evidence_pool,
    )

    # Build a per-sentence resolved list (parallel to
    # kept_sentences) so we can group by originating slot.
    # Re-do the per-sentence resolution inline — cheap and keeps
    # us in lockstep with `resolve_provenance_to_citations`'s
    # acceptance rules (≥3 content words, ≥15 chars).
    sentences_by_slot: dict[str, list[str]] = {sid: [] for sid in slot_order}
    ev_to_num = {b["evidence_id"]: b["num"] for b in biblio_slice}
    import re as _re
    _prov_re = _re.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")
    for sv in kept_sentences:
        raw = getattr(sv, "sentence", "") or ""
        stripped = _prov_re.sub("", raw).strip()
        stripped = _re.sub(r"\s+([.!?,;])", r"\1", stripped)
        content_w = _re.findall(r"[A-Za-z]+", stripped)
        if len(content_w) < 3 or len(stripped) < 15:
            continue
        # Determine the slot via the first token's ev_id.
        tokens = getattr(sv, "tokens", None) or []
        if not tokens:
            continue
        primary_ev = tokens[0].evidence_id
        slot_id = entity_to_slot_id.get(primary_ev)
        if slot_id is None:
            continue
        # Build citation marker (preserve first-appearance order
        # within the sentence).
        used_nums: list[int] = []
        for tok in tokens:
            n = ev_to_num.get(tok.evidence_id)
            if n is not None and n not in used_nums:
                used_nums.append(n)
        markers = "".join(f"[{n}]" for n in used_nums)
        sentences_by_slot.setdefault(slot_id, []).append(stripped + markers)

    # Emit final verified_text with re-injected headings.
    verified_blocks: list[str] = []
    for slot_id in slot_order:
        body_sentences = sentences_by_slot.get(slot_id) or []
        if not body_sentences:
            continue
        heading = f"### {slot_subsection[slot_id]}"
        body = " ".join(body_sentences)
        verified_blocks.append(f"{heading}\n\n{body}")

    if verified_blocks:
        verified_text = "\n\n".join(verified_blocks)
    elif kept > 0:
        # All sentences verified but none could be grouped (no
        # tokens). Fall back to the flat resolved body so prose
        # isn't lost.
        verified_text = resolved_body
    else:
        verified_text = ""

    dropped_due_to_failure = (kept == 0 and len(all_entity_ids) > 0)

    result = section_result_cls(
        title=plan.title,
        focus=plan.focus,
        ev_ids_assigned=all_entity_ids,
        raw_draft=raw_draft,
        rewritten_draft=rewritten_draft,
        verified_text=verified_text,
        biblio_slice=biblio_slice,
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
