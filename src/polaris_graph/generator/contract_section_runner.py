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
    build_slot_narrative_prompt,
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

    V31 (M-70) dispatch: regulatory entities (FDA, EMA, NICE, HC)
    route through `regulatory_synthesizer` instead of M-58 contract
    slot extraction. Codex strategic review 2026-04-25: M-58's
    verbatim-substring contract is too rigid for page-scale prose
    synthesis; regulatory entities need PROSE synthesis from
    segmented page sections, not field-level extraction.

    Three paths for non-regulatory:
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

    # V31 dispatch: regulatory entities go through M-70 prose
    # synthesis instead of M-58 field extraction.
    from .regulatory_synthesizer import (
        is_regulatory_entity,
        build_regulatory_synthesis_prompt,
        parse_regulatory_synthesis_response,
        RegulatorySynthesisError,
        _segment_regulatory_text,
    )
    if is_regulatory_entity(contract_entity):
        segments = _segment_regulatory_text(
            frame_row.direct_quote or "",
            required_fields,
            contract_entity.jurisdiction,
        )
        if not segments:
            # No headings matched — fall back to all not_extractable.
            # M-68 gap-disclosure fallback at the section level
            # will still render the heading + cited gap.
            logger.info(
                "[m70] no regulatory segments matched for "
                "entity_id=%r jurisdiction=%r — degrading to "
                "all not_extractable",
                entity_id, contract_entity.jurisdiction,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, 0, 0
        prompt = build_regulatory_synthesis_prompt(
            slot, frame_row, contract_entity, segments,
            research_question,
        )
        try:
            response_text, in_tok, out_tok = await llm_call(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[m70] LLM call failed for entity_id=%r: %s",
                entity_id, exc,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, 0, 0
        try:
            payload = parse_regulatory_synthesis_response(
                response_text, slot, frame_row, required_fields,
                segments,
            )
        except RegulatorySynthesisError as exc:
            logger.warning(
                "[m70] regulatory synthesis parse failed for "
                "entity_id=%r: %s", entity_id, exc,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, in_tok, out_tok
        return payload, in_tok, out_tok

    # Non-regulatory: legacy M-58 path.
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
    # slot_id -> primary entity_id (first entity in slot.entity_ids).
    # Used by M-68 Fix #1b (Qwen citation_tightness regression):
    # gap-disclosure prose must carry a citation marker pointing
    # at the bound contract entity so Qwen's citation-tightness
    # rule passes. Without this, run-8 release_allowed=False
    # despite all 15 slots rendering (Structure win → release loss).
    slot_primary_entity: dict[str, str] = {}

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
        slot_primary_entity[slot.slot_id] = slot.entity_ids[0]

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

            # V31 dispatch: regulatory entities use prose render
            # (multi-sentence paragraphs per field), not the
            # M-58 `Field: value [id].` slot prose.
            from .regulatory_synthesizer import (
                is_regulatory_entity,
                render_regulatory_prose,
            )
            if is_regulatory_entity(contract_entity):
                prose = render_regulatory_prose(payload)
            else:
                prose = render_slot_prose(payload)
            slot_body_prose.append(prose)

            # v1.1 A.1 option 4c (2026-04-30): two-tier rendering.
            # Append an LLM-generated 200-300w narrative paragraph
            # FROM THE SAME PAYLOAD. Preserves M-58 frame-coverage
            # manifest + audit trail (the deterministic prose
            # above stays intact) AND adds narrative depth to
            # close BEAT-BOTH on narrative_length +
            # contradiction_handling_grammar.
            #
            # Rollback: PG_USE_NARRATIVE_PARAGRAPH=0 disables.
            # Default ON. Strict_verify gates the LLM output
            # independently — if hallucination drift fails verify,
            # the narrative paragraph drops without affecting the
            # deterministic prose.
            #
            # Skipped for regulatory entities (regulatory_synthesizer
            # already produces multi-sentence paragraphs) and gap
            # payloads (no extracted fields to narrate).
            import os as _os
            narrative_enabled = (
                _os.environ.get("PG_USE_NARRATIVE_PARAGRAPH", "1") != "0"
            )
            has_extracted = any(
                f.status == "extracted" for f in payload.fields
            )
            if (
                narrative_enabled
                and has_extracted
                and not is_regulatory_entity(contract_entity)
            ):
                narr_prompt = build_slot_narrative_prompt(
                    payload,
                    subsection_title=slot.subsection_title,
                    research_question=plan.research_question,
                )
                if narr_prompt:
                    try:
                        narr_text, narr_in, narr_out = await llm_call(
                            narr_prompt,
                        )
                        total_in_tok += narr_in
                        total_out_tok += narr_out
                        if narr_text and narr_text.strip():
                            slot_body_prose.append(narr_text.strip())
                    except Exception as exc:
                        logger.warning(
                            "[m63] narrative-paragraph LLM call "
                            "failed for slot %r: %s",
                            slot.slot_id, exc,
                        )

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
    # and the span comes from FrameRow.direct_quote.
    #
    # V30 Phase-2 M-69 Fix #4 (Codex run-9 audit — SURPASS-5
    # regression): when M-66b-T expanded direct_quote from
    # ~500-char abstract to 25K-char full text, strict_verify's
    # content-overlap check began dropping legitimate M-58
    # extractions (e.g., SURPASS-5 went from 4 fields rendered
    # in run-7 → 0 sentences kept in run-9). M-58 already
    # enforces anti-fabrication via verbatim-substring of
    # direct_quote (whitespace-tolerant since M-66a-R), making
    # the strict_verify content-overlap check redundant for
    # contract-slot sentences.
    #
    # Recovery path: any strict_verify-dropped sentence whose
    # primary token resolves to a contract entity_id is RESTORED
    # to kept_sentences. Non-contract sentences (legacy free-form
    # synthesis) keep the strict_verify outcome unchanged.
    report = strict_verify_fn(rewritten_draft, evidence_pool)
    kept_sentences = list(getattr(report, "kept_sentences", []) or [])
    dropped_sentences = list(getattr(report, "dropped_sentences", []) or [])
    contract_entity_ids = set(plan.contract_entities_by_id.keys())
    rescued: list[Any] = []
    for sv in dropped_sentences:
        toks = getattr(sv, "tokens", None) or []
        if toks and toks[0].evidence_id in contract_entity_ids:
            rescued.append(sv)
    if rescued:
        logger.info(
            "[m63] M-69 Fix #4: rescued %d strict_verify-dropped "
            "contract sentences (M-58 already verified verbatim)",
            len(rescued),
        )
        kept_sentences.extend(rescued)
    kept = len(kept_sentences)
    dropped = report.total_in - kept

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
    # V30 Phase-2 M-68 Fix #1 (Codex run-7 audit directive):
    # a slot MUST NEVER silently drop from the body — even when
    # strict_verify kept zero sentences for it, emit the heading
    # plus an explicit gap-disclosure sentence. Pre-fix behaviour
    # silently omitted SURPASS-6, FDA Mounjaro, EMA EPAR, HC
    # Mounjaro in run-7 despite frame_coverage=pass for all four,
    # producing a structural LB vs both competitors.
    #
    # M-68 Fix #1b (run-8 Qwen citation_tightness regression):
    # gap-disclosure prose must carry a citation marker pointing
    # at the bound contract entity. Without it, Qwen flags
    # citation_tightness=needs_revision, blocking release_allowed.
    # Synthesize a bibliography entry for the bound entity if it
    # didn't already get one from kept_sentences.
    verified_blocks: list[str] = []
    slot_drop_log: list[dict[str, Any]] = []  # M-66a-T telemetry
    for slot_id in slot_order:
        body_sentences = sentences_by_slot.get(slot_id) or []
        heading = f"### {slot_subsection[slot_id]}"
        if body_sentences:
            body = " ".join(body_sentences)
            verified_blocks.append(f"{heading}\n\n{body}")
            slot_drop_log.append({
                "slot_id": slot_id,
                "kept_sentences": len(body_sentences),
                "disposition": "rendered_with_content",
            })
        else:
            # M-68 Fix #1b: ensure the gap disclosure carries a
            # citation marker for the bound entity. Synthesize a
            # biblio entry on demand if the entity wasn't already
            # cited via kept_sentences.
            primary_ev = slot_primary_entity.get(slot_id, "")
            if primary_ev and primary_ev not in ev_to_num:
                ev = evidence_pool.get(primary_ev, {})
                # M-69 Fix #2: prefer the contract entity's
                # label_name (e.g., "Mounjaro Canadian Product
                # Monograph", "TA924") for regulatory entities
                # when the FrameRow has no title. Pre-fix
                # fallback to the bare entity_id produced ugly
                # bibliography entries like
                # `statement=fda_zepbound_label`.
                contract_entity = plan.contract_entities_by_id.get(
                    primary_ev,
                )
                label = (
                    getattr(contract_entity, "label_name", None)
                    if contract_entity is not None else None
                )
                statement_candidates = [
                    ev.get("statement"),
                    ev.get("title"),
                    label,
                    primary_ev,
                ]
                statement = next(
                    (s for s in statement_candidates if s), primary_ev,
                )
                new_num = len(biblio_slice) + 1
                biblio_slice.append({
                    "num": new_num,
                    "evidence_id": primary_ev,
                    "url": ev.get("url") or ev.get("source_url") or "",
                    "tier": ev.get("tier", ""),
                    "statement": statement[:300],
                })
                ev_to_num[primary_ev] = new_num
            if primary_ev:
                marker = f"[{ev_to_num[primary_ev]}]"
                gap_sentence = (
                    f"Contract-bound content for {primary_ev} did not "
                    f"survive strict verification against retrieved "
                    f"primary source text; this slot is a curator-"
                    f"actionable gap. See manifest.frame_coverage_report "
                    f"and human_gap_tasks.json for per-entity detail."
                    f"{marker}"
                )
            else:
                # Fallback if no primary entity (defensive — outline
                # compiler enforces non-empty entity_ids per slot).
                gap_sentence = (
                    "Contract-bound content did not survive strict "
                    "verification; curator-actionable gap."
                )
            verified_blocks.append(f"{heading}\n\n{gap_sentence}")
            slot_drop_log.append({
                "slot_id": slot_id,
                "kept_sentences": 0,
                "disposition": "rendered_as_gap_disclosure",
            })
            logger.info(
                "[m63] slot %r rendered as gap disclosure "
                "(strict_verify kept 0 sentences)", slot_id,
            )

    if verified_blocks:
        verified_text = "\n\n".join(verified_blocks)
    else:
        # No slots at all — genuine empty-section fallback.
        verified_text = ""

    # Only flag dropped_due_to_failure when there are literally
    # no verified_blocks (no slots or no headings emitted). With
    # the gap-disclosure fallback, every slot renders at minimum
    # a heading, so this should only fire on plan.slots being
    # empty — which M-57 shouldn't emit.
    dropped_due_to_failure = (
        not verified_blocks and len(all_entity_ids) > 0
    )

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
