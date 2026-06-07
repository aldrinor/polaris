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
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# I-run11-010 (#1056, S2): minimum direct_quote length (chars) for a frame row to carry a verifiable
# citation span. A METADATA_ONLY row below this is routed to gap disclosure (LAW VI: env-overridable).
_MIN_VERIFIABLE_SPAN_CHARS = int(os.getenv("PG_MIN_VERIFIABLE_SPAN_CHARS", "50"))

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


# I-faith-001 Fix A: failure_reasons prefixes that mark a NUMERIC drop.
# A sentence dropped for one of these reasons is a numeric fabrication
# (a number/integer not present in the cited span) and must NEVER be
# laundered back by the M-69 Fix #4 contract-entity rescue. The rescue
# exists only to undo content-overlap false-drops on verbatim M-58 slot
# prose. `failure_reasons` strings are "reason:entity[:detail]" — Fix D
# appends a ":missing=[...]" detail to the integer reason, so the prefix
# is extracted via split(":", 1)[0] to stay match-safe.
_NUMERIC_DROP_PREFIXES: frozenset[str] = frozenset({
    "number_not_in_any_cited_span",
    "no_integer_overlap_any_cited_span",
})

# I-faith-001 Fix A refinement (Codex gate P1): a deterministic gap-disclosure
# ("<field>: not extractable from available primary content") is an HONEST
# disclosure, never a numeric CLAIM. A digit embedded in the field LABEL
# (e.g. "Baseline HbA1c", "COVID-19", "T2 diabetes") must NOT make it look
# like a numeric fabrication and strip its rescue eligibility -> the honest
# disclosure would vanish from a partially-rendered slot. Such disclosures
# are always rescue-eligible. (Real narrative numeric fabrications are
# already rescue-INELIGIBLE via Fix B's allow_rescue=False narrative stream,
# independent of this guard.)
_GAP_DISCLOSURE_MARKER = "not extractable from available primary content"


def _drop_is_numeric(sv: Any) -> bool:
    """True iff a dropped SentenceVerification failed for a NUMERIC reason
    AND is not a deterministic gap-disclosure.

    Inspects the `failure_reasons` LIST (there is no scalar drop_reason)
    and returns True if ANY reason's prefix (the text before the first
    ':') is a numeric-failure prefix. Used by the M-69 rescue loop to
    exclude numeric fabrications from rescue (I-faith-001 Fix A). Gap-
    disclosure sentences are exempt (Codex P1): an embedded label digit
    must not block their rescue.
    """
    sentence = str(getattr(sv, "sentence", "") or "")
    if _GAP_DISCLOSURE_MARKER in sentence.lower():
        return False
    failure_reasons = getattr(sv, "failure_reasons", None) or []
    return any(
        str(reason).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES
        for reason in failure_reasons
    )


def _verify_one_stream(
    *,
    raw_draft: str,
    evidence_pool: dict[str, dict[str, Any]],
    contract_entity_ids: set[str],
    rewrite_fn: Any,
    strict_verify_fn: Any,
    allow_rescue: bool,
    stream_label: str,
) -> tuple[list[Any], list[Any], list[Any], int, str]:
    """Rewrite + strict-verify ONE provenance stream, optionally applying
    the M-69 contract-entity rescue (I-faith-001 Fix B — stream separation).

    The DETERMINISTIC stream (M-58 / M-70 verbatim-guarded slot prose) is
    rescue-ELIGIBLE: ``allow_rescue=True`` runs the M-69 Fix #4 rescue with
    the Fix A `_drop_is_numeric` guard, restoring content-overlap false-drops
    while never laundering numeric fabrications.

    The NARRATIVE stream (free-form `build_slot_narrative_prompt` LLM
    paragraph) is rescue-INELIGIBLE: ``allow_rescue=False`` keeps EVERY
    dropped sentence dropped, so a narrative sentence that fails
    `verify_sentence_provenance` is never restored. This is the structural
    fix that closes the run-9 leak: the rescue blanket no longer covers the
    fabrication-prone stream.

    Returns:
        kept_sentences:   verified sentences (+ rescued, if allow_rescue)
        rescued:          the rescued SVs (empty when allow_rescue is False)
        dropped_final:    dropped SVs AFTER removing any rescued ones
        total_in:         report.total_in (for the kept/dropped math)
        rewritten_draft:  the span-token-rewritten draft for this stream

    An empty `raw_draft` short-circuits to all-empty results (no rewrite /
    verify call), which is the identical no-op behavior the disabled /
    no-narrative case produced pre-Fix-B.
    """
    if not raw_draft:
        return [], [], [], 0, ""

    # Rewrite citation markers to span tokens (M-63 Fix #3 generalized
    # regex picks up contract entity ids registered into evidence_pool by
    # the integration layer).
    rewritten_draft, _converted, _unverifiable = rewrite_fn(
        raw_draft, evidence_pool,
    )

    # Strict verify — every deterministic sentence is `Field: value [#ev:...]`
    # and the span comes from FrameRow.direct_quote.
    report = strict_verify_fn(rewritten_draft, evidence_pool)
    kept_sentences = list(getattr(report, "kept_sentences", []) or [])
    dropped_sentences = list(getattr(report, "dropped_sentences", []) or [])
    total_in = int(getattr(report, "total_in", 0) or 0)

    rescued: list[Any] = []
    if allow_rescue:
        # M-69 Fix #4 rescue (deterministic stream only). Restore a dropped
        # sentence iff its primary token resolves to a contract entity_id
        # AND it did NOT drop for a numeric reason (Fix A). The legitimate
        # content-overlap "not extractable" gap-disclosures (drop for
        # no_content_word_overlap, not numeric) remain rescue-eligible.
        for sv in dropped_sentences:
            toks = getattr(sv, "tokens", None) or []
            if not (toks and toks[0].evidence_id in contract_entity_ids):
                continue
            if _drop_is_numeric(sv):
                # Numeric fabrication — never rescue.
                continue
            rescued.append(sv)
        if rescued:
            logger.info(
                "[m63] M-69 Fix #4 (%s stream): rescued %d "
                "strict_verify-dropped contract sentences "
                "(M-58 already verified verbatim)",
                stream_label, len(rescued),
            )
            kept_sentences.extend(rescued)

    rescued_ids = {id(sv) for sv in rescued}
    dropped_final = [
        sv for sv in dropped_sentences if id(sv) not in rescued_ids
    ]
    return kept_sentences, rescued, dropped_final, total_in, rewritten_draft


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

    # I-run11-010 (#1056, S2): a METADATA_ONLY frame row with an empty/near-empty direct_quote has no
    # verifiable span to cite — emit an honest all-not_extractable payload (surfaced by M-59 as
    # FAIL_MIN_FIELDS / curator-actionable) WITHOUT calling the LLM on an empty span, so strict_verify
    # is not the ONLY thing standing between an empty authoritatively-cited T1 span and a generated
    # claim. NOT compose_gap_payload — that helper HARD-RAISES on non-gap provenance by design (the
    # M-58 symmetric guard); _build_not_extractable_payload is the sanctioned non-gap skip path. A
    # METADATA_ONLY row that DOES carry a usable quote (>= the verifiable-span floor) still extracts.
    if (
        frame_row.provenance_class == ProvenanceClass.METADATA_ONLY
        and len((frame_row.direct_quote or "").strip()) < _MIN_VERIFIABLE_SPAN_CHARS
    ):
        payload = _build_not_extractable_payload(
            slot, frame_row.entity_id, frame_row, required_fields
        )
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
    #
    # I-faith-001 Fix B (STREAM SEPARATION) + Fix C / regulatory: THREE
    # parallel block lists, one per provenance stream:
    #   - DETERMINISTIC (rescue-ELIGIBLE): the M-58 `render_slot_prose` output.
    #     `parse_slot_fill_response` enforces `value == source_span`, so the
    #     ENTIRE rendered prose is verbatim source text. The M-69 rescue's
    #     premise — undo content-overlap false-drops on legitimately-verbatim
    #     slot prose — holds ONLY for this stream.
    #   - REGULATORY (rescue-INELIGIBLE): the M-70 `render_regulatory_prose`
    #     output. Its parser verbatim-checks ONLY the one `source_span` phrase,
    #     not the LLM-synthesized 50-80 word `value` paragraph — so it has the
    #     SAME fabrication shape as the narrative stream and must NOT be
    #     rescued.
    #   - NARRATIVE (rescue-INELIGIBLE): the free-form
    #     `build_slot_narrative_prompt` LLM paragraph (fabrication-prone — V4
    #     Pro ignored the prompt's "strict_verify will reject hallucinations"
    #     instruction and invented 14%/35%/attrition/CSAT/partial-equilibrium
    #     in run-9).
    # The three streams are verified SEPARATELY downstream so the M-69
    # contract-entity rescue protects ONLY the deterministic stream — the
    # regulatory and narrative sentences must pass `verify_sentence_provenance`
    # on their own with NO rescue. Keeping them split here (rather than tagging
    # a joined draft) means stream origin is DEFINITIONAL — which pass produced
    # the kept sentence — with no fingerprint collision or sentence-split-seam
    # risk.
    raw_body_blocks: list[str] = []           # deterministic stream
    regulatory_body_blocks: list[str] = []    # M-70 regulatory stream
    narrative_body_blocks: list[str] = []     # narrative stream

    for slot in plan.slots:
        if not slot.entity_ids:
            # Defensive: outline compiler shouldn't emit empty slots,
            # but guard anyway.
            continue

        slot_order.append(slot.slot_id)
        slot_subsection[slot.slot_id] = slot.subsection_title
        slot_primary_entity[slot.slot_id] = slot.entity_ids[0]

        # I-faith-001 Fix B / Fix C: per-slot prose split by provenance stream.
        slot_det_prose: list[str] = []       # deterministic (M-58 verbatim)
        slot_reg_prose: list[str] = []       # M-70 regulatory LLM-synthesized
        slot_narrative_prose: list[str] = []  # narrative LLM paragraph
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
            #
            # I-faith-001 Fix C / regulatory classification: M-70
            # `render_regulatory_prose` emits the LLM-SYNTHESIZED
            # `field.value` (a 50-80 word paragraph). Its parser
            # (`parse_regulatory_synthesis_response`) verbatim-checks ONLY the
            # one `source_span` PHRASE against the segment — NOT the whole
            # prose value — so a regulatory paragraph can carry LLM-introduced
            # connective/qualitative content beyond the single verified phrase.
            # That is the SAME fabrication shape as the free-form narrative
            # stream, and UNLIKE the M-58 deterministic stream where
            # `parse_slot_fill_response` enforces `value == source_span` (the
            # entire rendered prose is verbatim source text). The M-69
            # contract-entity rescue's premise — "undo content-overlap
            # false-drops on legitimately-VERBATIM slot prose" — therefore does
            # NOT hold for regulatory prose. Route it to the rescue-INELIGIBLE
            # `slot_reg_prose` stream so a regulatory sentence that fails
            # `verify_sentence_provenance` is never laundered back into `kept`.
            from .regulatory_synthesizer import (
                is_regulatory_entity,
                render_regulatory_prose,
            )
            if is_regulatory_entity(contract_entity):
                # Regulatory stream — rescue-INELIGIBLE (LLM-synthesized prose,
                # only the source_span phrase is verbatim-verified).
                slot_reg_prose.append(render_regulatory_prose(payload))
            else:
                # Deterministic stream: M-58 verbatim-substring-guarded prose
                # (`parse_slot_fill_response` enforces value == source_span).
                # Rescue-eligible.
                slot_det_prose.append(render_slot_prose(payload))

            # v1.1 A.1 option 4c (2026-04-30): two-tier rendering.
            # Append an LLM-generated 200-300w narrative paragraph
            # FROM THE SAME PAYLOAD. Preserves M-58 frame-coverage
            # manifest + audit trail (the deterministic prose
            # above stays intact) AND adds narrative depth to
            # close BEAT-BOTH on narrative_length +
            # contradiction_handling_grammar.
            #
            # Rollback: PG_USE_NARRATIVE_PARAGRAPH=0 disables.
            # Default ON.
            #
            # I-faith-001 Fix B: the narrative paragraph goes into the
            # SEPARATE narrative stream (`slot_narrative_prose`), which is
            # verified with NO M-69 rescue. Pre-Fix-B this prose was joined
            # with the deterministic slot prose before verify, so the
            # contract-entity rescue laundered fabricated narrative sentences
            # (14%/35%/attrition) back into `kept` — the run-9 leak. Now a
            # narrative sentence that fails `verify_sentence_provenance` drops
            # for good and never reaches the rescue loop.
            #
            # v1.1 A.1 4c v3: also enable narrative for regulatory
            # entities — render_regulatory_prose already gives a
            # multi-sentence paragraph but it's still ~80-120 words
            # per slot; competitors integrate regulatory context
            # into 250+ word narrative blocks. Adds the LLM
            # narrative paragraph alongside the existing
            # render_regulatory_prose output (two-tier).
            #
            # Gap payloads still skipped (no extracted fields).
            import os as _os
            narrative_enabled = (
                _os.environ.get("PG_USE_NARRATIVE_PARAGRAPH", "1") != "0"
            )
            has_extracted = any(
                f.status == "extracted" for f in payload.fields
            )
            if narrative_enabled and has_extracted:
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
                            # Narrative stream — rescue-INELIGIBLE (Fix B).
                            slot_narrative_prose.append(narr_text.strip())
                    except Exception as exc:
                        logger.warning(
                            "[m63] narrative-paragraph LLM call "
                            "failed for slot %r: %s",
                            slot.slot_id, exc,
                        )

        if slot_det_prose:
            raw_body_blocks.append(" ".join(slot_det_prose))
        if slot_reg_prose:
            regulatory_body_blocks.append(" ".join(slot_reg_prose))
        if slot_narrative_prose:
            narrative_body_blocks.append(" ".join(slot_narrative_prose))

    # Body-only raw drafts (no `### headings` — they'd poison
    # strict_verify's content-overlap check), ONE PER STREAM.
    # I-faith-001 Fix B / Fix C: the deterministic, regulatory, and narrative
    # prose are kept in separate drafts and verified separately so the M-69
    # rescue can be applied to the deterministic stream ONLY.
    det_raw_draft = " ".join(raw_body_blocks)
    regulatory_raw_draft = " ".join(regulatory_body_blocks)
    narrative_raw_draft = " ".join(narrative_body_blocks)

    contract_entity_ids = set(plan.contract_entities_by_id.keys())

    # ── DETERMINISTIC stream (M-58 verbatim-guarded slot prose) ────────
    # Rescue-ELIGIBLE: the M-69 Fix #4 rescue exists ONLY to undo
    # content-overlap false-drops on legitimately-verbatim slot prose (the
    # SURPASS-5 25K-char regression). `parse_slot_fill_response` enforces
    # `value == source_span`, so the entire rendered prose is verbatim source
    # text. Fix A's `_drop_is_numeric` guard keeps it from laundering numeric
    # fabrications.
    (
        det_kept_sentences,
        det_rescued,
        det_dropped_final,
        det_total_in,
        det_rewritten_draft,
    ) = _verify_one_stream(
        raw_draft=det_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=True,
        stream_label="deterministic",
    )

    # ── REGULATORY stream (M-70 `render_regulatory_prose` LLM synthesis) ─
    # Rescue-INELIGIBLE (Fix C / regulatory classification): the M-70 parser
    # verbatim-checks ONLY the one `source_span` phrase, not the full
    # LLM-synthesized prose value — so a regulatory sentence carries the SAME
    # fabrication risk as the narrative stream. Each regulatory sentence must
    # pass `verify_sentence_provenance` on its own with NO rescue.
    (
        reg_kept_sentences,
        _reg_rescued,  # always empty — rescue disabled for this stream
        reg_dropped_final,
        reg_total_in,
        reg_rewritten_draft,
    ) = _verify_one_stream(
        raw_draft=regulatory_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=False,
        stream_label="regulatory",
    )

    # ── NARRATIVE stream (free-form `build_slot_narrative_prompt` LLM) ──
    # Rescue-INELIGIBLE (Fix B): this is the fabrication-prone stream. Each
    # narrative sentence must pass `verify_sentence_provenance` on its own;
    # any drop (numeric OR qualitative content-overlap) stays dropped. This
    # closes the run-9 leak at the structural level — Fix A alone could not
    # catch the qualitative fabrications (attrition/CSAT/partial-equilibrium)
    # because they carry no fabricated integer.
    (
        narr_kept_sentences,
        _narr_rescued,  # always empty — rescue disabled for this stream
        narr_dropped_final,
        narr_total_in,
        narr_rewritten_draft,
    ) = _verify_one_stream(
        raw_draft=narrative_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=False,
        stream_label="narrative",
    )

    # ── Merge the three streams ────────────────────────────────────────
    # The downstream regroup (~line 700) re-buckets every kept sentence into
    # its originating slot via the first token's evidence_id, so cross-slot
    # ordering is reconstructed regardless of merge order. WITHIN a slot, all
    # deterministic sentences precede regulatory, which precede narrative
    # (pre-Fix-B a multi-entity slot interleaved det(e1),narr(e1),...; now it
    # is det(...),reg(...),narr(...)). This reordering is faithfulness-neutral
    # — the same verified sentences, only the in-slot sequence and citation
    # numbering may shift. Deterministic-first is the intended ordering
    # (verbatim slot facts lead, regulatory + narrative depth follow). A slot
    # is either M-58 OR M-70 per entity, so det and reg do not co-occur for the
    # same entity — only the merge ORDER is defined here, not a mixing rule.
    kept_sentences = (
        det_kept_sentences + reg_kept_sentences + narr_kept_sentences
    )
    rescued = det_rescued  # regulatory + narrative streams contribute no rescues
    # Combined raw + rewritten drafts (telemetry parity with pre-Fix-B).
    raw_draft = " ".join(
        d for d in (det_raw_draft, regulatory_raw_draft, narrative_raw_draft)
        if d
    )
    rewritten_draft = " ".join(
        d for d in (
            det_rewritten_draft, reg_rewritten_draft, narr_rewritten_draft,
        )
        if d
    )
    # Combined dropped list (excludes deterministic rescues by construction).
    dropped_sentences = (
        det_dropped_final + reg_dropped_final + narr_dropped_final
    )
    total_in = det_total_in + reg_total_in + narr_total_in
    kept = len(kept_sentences)
    dropped = total_in - kept

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
    # I-ready-017 FX-07b leg-2 (#1111): attribute DROPPED (strict_verify-failed)
    # sentences to their originating entity via [#ev:entity_id:..] tokens — the
    # SAME extraction used for kept sentences (_prov_re above). Lets the
    # slot_drop_log carry sentences_generated_content = kept + dropped per slot's
    # primary entity, so compose_frame_coverage can distinguish "generated prose
    # all failed strict_verify" (pipeline fault) from "no content attempted"
    # (curator gap). Pure telemetry — no behaviour change.
    from collections import Counter as _Counter
    _dropped_by_entity: _Counter = _Counter()
    for _dsv in dropped_sentences:
        _draw = getattr(_dsv, "sentence", "") or ""
        for _dm in _prov_re.finditer(_draw):
            _dropped_by_entity[_dm.group(1)] += 1

    def _slot_strict_verify_meta(_sid: str, _kept: int) -> dict[str, Any]:
        _eid = slot_primary_entity.get(_sid, "")
        _frow = plan.frame_rows_by_entity.get(_eid) if _eid else None
        _pc = getattr(getattr(_frow, "provenance_class", None), "value", "") if _frow else ""
        return {
            "entity_id": _eid,
            "sentences_kept": _kept,
            "sentences_generated_content": _kept + int(_dropped_by_entity.get(_eid, 0)),
            "provenance_class": _pc,
        }

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
                **_slot_strict_verify_meta(slot_id, len(body_sentences)),
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
                **_slot_strict_verify_meta(slot_id, 0),
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

    # I-gen-005 Step 1.5 iter-2 (Codex P1): populate final per-sentence
    # telemetry fields so verification_details.json reflects contract
    # sections' kept/dropped state.
    #
    # I-faith-001 Fix B: `dropped_sentences` is already
    # `det_dropped_final + narr_dropped_final` — the per-stream helper
    # returns each stream's POST-rescue dropped list, so deterministic
    # rescues are already excluded. The `rescued_ids` filter is therefore
    # a defensive no-op (kept for clarity that rescues are never in the
    # final dropped list).
    rescued_ids = {id(sv) for sv in rescued}
    final_dropped_svs = [
        sv for sv in dropped_sentences if id(sv) not in rescued_ids
    ]
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
        # I-gen-005 Step 1.5 iter-2 (Codex P1 contract_runner:683):
        # final kept + dropped SVs after rescue path. Rescued SVs are
        # in kept_sentences_pre_resolve; non-rescued drops are in
        # dropped_sentences_final. No dedup pass runs on contract
        # sections, so dropped_sentences_dedup_redundant stays empty.
        kept_sentences_pre_resolve=list(kept_sentences),
        dropped_sentences_final=final_dropped_svs,
        # I-ready-017 FX-07b leg-2 (#1111): per-(slot,entity) strict_verify
        # telemetry for the frame_coverage honesty override.
        slot_strict_verify=slot_drop_log,
    )
    return result, payloads


def is_contract_section(plan: Any) -> bool:
    """Duck-typed check: is this a ContractSectionPlanExt?
    Used by orchestration loop to dispatch without importing
    the extended class (keeps generator edit minimal)."""
    return isinstance(plan, ContractSectionPlanExt)
