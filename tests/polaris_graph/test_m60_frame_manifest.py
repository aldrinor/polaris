"""M-60 tests: V30 explicit gap reporting + manifest.

Layer 4c. Consumes M-55 CompiledFrame + M-57 ContractOutline +
M-56 FrameRows + M-59 ValidationReport. Produces FrameCoverageReport
for manifest.json plus Methods-section disclosure + M-61 task list.

Codex plan review #4: every incomplete slot must carry structured
metadata (slot_id, entity_id, status, failure_reason,
retrieval_attempt_log, available_artifacts, human_completion_eligible).

All tests pure — no LLM, no network.

Covers:
1. all-pass happy path: manifest has pass_count == total, no gaps.
2. gap slot emits structured entry with failure_reason + attempt log.
3. partial slot flagged as human_completion_eligible.
4. available_artifacts derivation (oa_url / abstract / metadata).
5. to_manifest_dict serializable.
6. Methods disclosure prose for 0-gap, partial-only, gap-present cases.
7. M-61 human_gap_tasks compose from coverage.
8. Entity-type-agnostic (statute, dft_primary).
9. Deterministic.
10. Backward-compat: missing FrameRow defensive fallback.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator.frame_manifest import (
    FrameCoverageReport,
    SlotCoverageEntry,
    compose_frame_coverage,
    compose_human_completion_tasks,
    compose_methods_disclosure,
)
from src.polaris_graph.generator.slot_fill import (
    SlotFieldFill,
    SlotFillPayload,
)
from src.polaris_graph.generator.slot_validator import (
    EntityValidation,
    SlotAggregateVerdict,
    ValidationReport,
    ValidationVerdict,
)
from src.polaris_graph.nodes.contract_outline import (
    ContractOutline,
    ContractSectionPlan,
    ContractSlotPlan,
)
from src.polaris_graph.nodes.frame_compiler import (
    CompiledFrame,
    EvidenceBinding,
)
from src.polaris_graph.nodes.report_contract import (
    RenderingSlot,
    ReportContract,
    RequiredEntity,
)
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow,
    ProvenanceClass,
    RetrievalAttempt,
    RetrievalTiming,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture builders
# ─────────────────────────────────────────────────────────────────────
def _make_row(
    entity_id: str = "e1",
    provenance: ProvenanceClass = ProvenanceClass.ABSTRACT_ONLY,
    attempts: tuple[RetrievalAttempt, ...] = (),
    failure_reason: str | None = None,
    has_oa: bool = False,
    has_abstract: bool = True,
    has_metadata: bool = True,
    entity_type: str = "pivotal_trial",
    slot: str = "s1",
) -> FrameRow:
    return FrameRow(
        entity_id=entity_id,
        entity_type=entity_type,
        rendering_slot=slot,
        provenance_class=provenance,
        direct_quote="abstract text here" if has_abstract else "",
        quote_source="crossref_abstract" if has_abstract else "none",
        doi="10.1/x" if has_metadata else None,
        pmid="12345" if has_metadata else None,
        oa_pdf_url="https://oa.example/x.pdf" if has_oa else None,
        url=None,
        title="Test title" if has_metadata else None,
        authors=("Smith J",),
        journal="Test J",
        year=2024,
        failure_reason=failure_reason,
        retrieval_attempts=attempts,
        retrieval_timings=(),
    )


def _make_binding(
    entity_id: str = "e1",
    slot: str = "s1",
    etype: str = "pivotal_trial",
) -> EvidenceBinding:
    return EvidenceBinding(
        entity_id=entity_id,
        entity_type=etype,
        primary_identifier="doi:10.1/x",
        secondary_identifiers=(),
        rendering_slot=slot,
        required_fields=("N", "primary_endpoint"),
        min_fields_for_completion=1,
    )


def _make_compiled_frame(
    bindings: tuple[EvidenceBinding, ...],
) -> CompiledFrame:
    # Minimal contract matching bindings
    entities = tuple(
        RequiredEntity(
            id=b.entity_id,
            type=b.entity_type,
            required_fields=b.required_fields,
            min_fields_for_completion=b.min_fields_for_completion,
            rendering_slot=b.rendering_slot,
        )
        for b in bindings
    )
    slot_ids = sorted({b.rendering_slot for b in bindings})
    slots = tuple(
        RenderingSlot(
            id=sid, section="Efficacy",
            subsection_title=f"Subsection {sid}",
            ordering=i + 1, required=True,
        )
        for i, sid in enumerate(slot_ids)
    )
    contract = ReportContract(
        slug="test",
        schema_version="v30.1",
        required_entities=entities,
        rendering_slots=slots,
        section_order=("Efficacy",),
    )
    return CompiledFrame(
        slug="test",
        schema_version="v30.1",
        research_question="what's the evidence?",
        contract=contract,
        evidence_bindings=bindings,
        ordered_entity_ids=tuple(b.entity_id for b in bindings),
        warnings=(),
    )


def _make_outline(cf: CompiledFrame) -> ContractOutline:
    by_slot: dict[str, list[str]] = {}
    for b in cf.evidence_bindings:
        by_slot.setdefault(b.rendering_slot, []).append(b.entity_id)

    slots: list[ContractSlotPlan] = []
    slot_by_id = cf.contract.slots_by_id()
    for slot_id, eids in by_slot.items():
        slot = slot_by_id[slot_id]
        slots.append(ContractSlotPlan(
            slot_id=slot_id,
            section=slot.section,
            subsection_title=slot.subsection_title,
            ordering=slot.ordering,
            entity_ids=tuple(eids),
            provenance_classes=tuple("abstract_only" for _ in eids),
            is_gap=False,
            is_partial=False,
        ))
    sec = ContractSectionPlan(
        section="Efficacy",
        section_ordering_index=0,
        slots=tuple(slots),
        focus="test",
    )
    return ContractOutline(
        research_question="q",
        schema_version="v30.1",
        sections=(sec,),
    )


def _make_validation(
    entity_verdicts: list[tuple[str, str, ValidationVerdict]],
) -> ValidationReport:
    """Minimal ValidationReport from (slot_id, entity_id, verdict) tuples."""
    entity_validations = tuple(
        EntityValidation(
            slot_id=sid,
            entity_id=eid,
            is_gap=(v == ValidationVerdict.PASS
                    and "gap" in eid.lower()),
            required_min_fields=1,
            observed_completion_count=1 if v == ValidationVerdict.PASS else 0,
            bound_ev_id_present_in_prose=(v == ValidationVerdict.PASS),
            verdict=v,
            reason=f"{eid}: {v.value}",
        )
        for sid, eid, v in entity_verdicts
    )
    # Aggregate by slot
    slots: dict[str, list[EntityValidation]] = {}
    for ev in entity_validations:
        slots.setdefault(ev.slot_id, []).append(ev)
    slot_verdicts = tuple(
        SlotAggregateVerdict(
            slot_id=sid,
            entity_verdicts=tuple(slots[sid]),
            overall=(
                ValidationVerdict.PASS
                if all(e.verdict == ValidationVerdict.PASS for e in slots[sid])
                else slots[sid][0].verdict
            ),
            reason=f"slot {sid} aggregate",
        )
        for sid in slots
    )
    return ValidationReport(
        entity_validations=entity_validations,
        slot_verdicts=slot_verdicts,
    )


# ─────────────────────────────────────────────────────────────────────
# (1) All-pass happy path
# ─────────────────────────────────────────────────────────────────────
class TestAllPass:
    def test_all_pass_coverage_report(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.PASS),
        ])
        coverage = compose_frame_coverage(
            cf, outline, rows, validation,
        )
        assert coverage.total_entities == 1
        assert coverage.pass_count == 1
        assert coverage.frame_gap_count == 0
        assert coverage.partial_count == 0
        assert len(coverage.entries) == 1
        assert coverage.entries[0].status == "pass"
        assert coverage.entries[0].human_completion_eligible is False


# ─────────────────────────────────────────────────────────────────────
# (2) Gap slot emits structured metadata
# ─────────────────────────────────────────────────────────────────────
class TestGapStructuredMetadata:
    def test_gap_entry_has_all_required_fields(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        attempts = (
            RetrievalAttempt(
                source="crossref", url="https://api.crossref.org/works/10.1/x",
                attempt_index=1, http_status=404, outcome="not_found",
            ),
            RetrievalAttempt(
                source="unpaywall", url="https://api.unpaywall.org/v2/10.1/x",
                attempt_index=1, http_status=404, outcome="not_found",
            ),
        )
        rows = (_make_row(
            provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            attempts=attempts,
            failure_reason="all sources failed",
            has_oa=False, has_abstract=False, has_metadata=False,
        ),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.PASS),  # gap with marker = PASS
        ])
        # Override the is_gap flag; validator treats PASS with gap
        # provenance as expected
        coverage = compose_frame_coverage(
            cf, outline, rows, validation,
        )
        entry = coverage.entries[0]
        assert entry.slot_id == "s1"
        assert entry.entity_id == "e1"
        assert entry.status == "pass"
        assert entry.provenance_class == "frame_gap_unrecoverable"
        assert entry.failure_reason == "all sources failed"
        # retrieval_attempt_log: one dict per HTTP attempt (Codex
        # M-56 audit Blocker 2 fix)
        assert len(entry.retrieval_attempt_log) == 2
        assert entry.retrieval_attempt_log[0]["source"] == "crossref"
        assert entry.retrieval_attempt_log[0]["attempt_index"] == 1
        assert entry.retrieval_attempt_log[0]["outcome"] == "not_found"
        # Available artifacts: empty when no metadata either
        assert entry.available_artifacts == []
        # Gap is human_completion_eligible
        assert entry.human_completion_eligible is True
        assert coverage.frame_gap_count == 1


# ─────────────────────────────────────────────────────────────────────
# (3) Partial slot flagged eligible
# ─────────────────────────────────────────────────────────────────────
class TestPartialSlot:
    def test_partial_slot_eligible_for_human_completion(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(),)  # abstract_only, not a gap row
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.FAIL_MIN_FIELDS),
        ])
        coverage = compose_frame_coverage(
            cf, outline, rows, validation,
        )
        entry = coverage.entries[0]
        assert entry.status == "fail_min_fields"
        assert entry.human_completion_eligible is True
        assert coverage.partial_count == 1
        assert coverage.pass_count == 0


# ─────────────────────────────────────────────────────────────────────
# (4) Available artifacts derivation
# ─────────────────────────────────────────────────────────────────────
class TestAvailableArtifacts:
    def test_oa_abstract_and_metadata(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(
            provenance=ProvenanceClass.OPEN_ACCESS,
            has_oa=True, has_abstract=True, has_metadata=True,
        ),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.PASS),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        artifacts = coverage.entries[0].available_artifacts
        assert "oa_url" in artifacts
        assert "crossref_abstract" in artifacts
        assert "crossref_metadata" in artifacts
        assert "doi" in artifacts
        assert "pmid" in artifacts

    def test_metadata_only_artifacts(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(
            provenance=ProvenanceClass.METADATA_ONLY,
            has_oa=False, has_abstract=False, has_metadata=True,
        ),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.FAIL_MIN_FIELDS),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        artifacts = coverage.entries[0].available_artifacts
        assert "oa_url" not in artifacts
        assert "crossref_metadata" in artifacts
        assert "doi" in artifacts


# ─────────────────────────────────────────────────────────────────────
# (5) to_manifest_dict serializable
# ─────────────────────────────────────────────────────────────────────
class TestManifestSerialization:
    def test_coverage_dict_round_trips_through_json(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.PASS),
        ])
        coverage = compose_frame_coverage(
            cf, outline, rows, validation,
        )
        d = coverage.to_manifest_dict()
        # Full JSON serializability check
        j = json.dumps(d)
        back = json.loads(j)
        assert back["research_question"] == "what's the evidence?"
        assert back["total_entities"] == 1
        assert back["pass_count"] == 1
        assert isinstance(back["entries"], list)
        assert back["entries"][0]["slot_id"] == "s1"
        assert back["entries"][0]["entity_id"] == "e1"


# ─────────────────────────────────────────────────────────────────────
# (6) Methods disclosure prose
# ─────────────────────────────────────────────────────────────────────
class TestMethodsDisclosure:
    def _coverage(
        self, pass_count: int, partial: int, gaps: int,
    ) -> FrameCoverageReport:
        total = pass_count + partial + gaps
        return FrameCoverageReport(
            research_question="q",
            schema_version="v30.1",
            total_slots=total,
            total_entities=total,
            frame_gap_count=gaps,
            partial_count=partial,
            pass_count=pass_count,
            by_status={},
            entries=(),
        )

    def test_all_pass_disclosure(self) -> None:
        text = compose_methods_disclosure(
            self._coverage(pass_count=3, partial=0, gaps=0),
        )
        assert "all 3" in text
        assert "gap" not in text.lower() or "gap slots" not in text

    def test_gaps_present_disclosure(self) -> None:
        text = compose_methods_disclosure(
            self._coverage(pass_count=8, partial=1, gaps=2),
        )
        assert "Fully populated: 8" in text
        assert "Partial coverage" in text and "1" in text
        assert "Unretrievable" in text and "2" in text
        assert "manifest.json" in text


# ─────────────────────────────────────────────────────────────────────
# (7) M-61 human_gap_tasks composition
# ─────────────────────────────────────────────────────────────────────
class TestHumanCompletionTasks:
    def test_tasks_only_for_eligible_entries(self) -> None:
        cf = _make_compiled_frame((
            _make_binding(entity_id="pass1", slot="s1"),
            _make_binding(entity_id="gap1", slot="s2"),
        ))
        outline = _make_outline(cf)
        rows = (
            _make_row(entity_id="pass1", slot="s1"),
            _make_row(
                entity_id="gap1", slot="s2",
                provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
                failure_reason="paywalled",
                has_oa=False, has_abstract=False, has_metadata=False,
            ),
        )
        validation = _make_validation([
            ("s1", "pass1", ValidationVerdict.PASS),
            ("s2", "gap1", ValidationVerdict.PASS),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        tasks = compose_human_completion_tasks(coverage)
        # Only gap1 is eligible
        assert len(tasks) == 1
        assert tasks[0]["entity_id"] == "gap1"
        assert tasks[0]["failure_reason"] == "paywalled"
        assert "operator to provide" in tasks[0]["needs"]

    def test_tasks_serializable(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(
            provenance=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            failure_reason="x",
        ),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.FAIL_GAP_NO_LANGUAGE),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        tasks = compose_human_completion_tasks(coverage)
        # Must JSON-serialize cleanly
        json.dumps(tasks)


# ─────────────────────────────────────────────────────────────────────
# (8) Entity-type-agnostic
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    def test_statute_and_dft_types_work(self) -> None:
        cf = _make_compiled_frame((
            _make_binding(entity_id="stat1", slot="s1", etype="statute"),
            _make_binding(entity_id="dft1", slot="s2", etype="dft_primary"),
        ))
        outline = _make_outline(cf)
        rows = (
            _make_row(entity_id="stat1", slot="s1", entity_type="statute"),
            _make_row(entity_id="dft1", slot="s2", entity_type="dft_primary"),
        )
        validation = _make_validation([
            ("s1", "stat1", ValidationVerdict.PASS),
            ("s2", "dft1", ValidationVerdict.PASS),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        assert coverage.total_entities == 2
        assert coverage.pass_count == 2


# ─────────────────────────────────────────────────────────────────────
# (9) Deterministic
# ─────────────────────────────────────────────────────────────────────
class TestDeterministic:
    def test_same_inputs_yield_same_coverage(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows = (_make_row(),)
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.PASS),
        ])
        c1 = compose_frame_coverage(cf, outline, rows, validation)
        c2 = compose_frame_coverage(cf, outline, rows, validation)
        assert c1 == c2


# ─────────────────────────────────────────────────────────────────────
# (10) Missing FrameRow defensive fallback
# ─────────────────────────────────────────────────────────────────────
class TestMissingFrameRowDefensive:
    def test_missing_row_produces_empty_entry(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        # Intentionally no rows
        rows: tuple[FrameRow, ...] = ()
        validation = _make_validation([
            ("s1", "e1", ValidationVerdict.FAIL_MISSING_PAYLOAD),
        ])
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        entry = coverage.entries[0]
        assert entry.provenance_class == "frame_gap_unrecoverable"
        # When validator has a reason, it wins; the "FrameRow missing"
        # default only fires if validator_reason is empty too.
        assert entry.failure_reason  # non-None, non-empty
        assert entry.human_completion_eligible is True
        assert coverage.frame_gap_count == 1

    def test_missing_row_and_no_validator_reason_falls_back(self) -> None:
        cf = _make_compiled_frame((_make_binding(),))
        outline = _make_outline(cf)
        rows: tuple[FrameRow, ...] = ()
        # Empty validation report — no verdict for (s1, e1)
        validation = ValidationReport(
            entity_validations=(),
            slot_verdicts=(),
        )
        coverage = compose_frame_coverage(cf, outline, rows, validation)
        entry = coverage.entries[0]
        # Default status when no verdict in report
        assert entry.status == "fail_missing_payload"
        # When there's no validator_reason AND no row, the composite
        # helper emits the hardcoded pipeline-crossed-wires message.
        assert "FrameRow missing" in entry.failure_reason
