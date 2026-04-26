"""Tests for src/polaris_graph/audit_ir/loader.py.

Loads the canonical run-14 V30 Phase-2 artifact and verifies the AuditIR
object exposes everything the Evidence Inspector renderers need.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir import (
    AuditIR,
    BibliographyEntry,
    ContradictionCluster,
    FrameCoverageReport,
    RunManifest,
    TierMix,
    load_audit_ir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_14_DIR = (
    REPO_ROOT
    / "outputs"
    / "full_scale_v30_phase2_run14"
    / "clinical"
    / "clinical_tirzepatide_t2dm"
)


@pytest.fixture(scope="module")
def ir() -> AuditIR:
    """Load run-14 once for all tests in this module."""
    return load_audit_ir(RUN_14_DIR)


def test_loader_returns_audit_ir_instance(ir: AuditIR) -> None:
    assert isinstance(ir, AuditIR)
    assert ir.artifact_dir == RUN_14_DIR


def test_manifest_top_level_fields(ir: AuditIR) -> None:
    m = ir.manifest
    assert isinstance(m, RunManifest)
    assert m.run_id == "SWEEP_clinical_clinical_tirzepatide_t2dm_1777170058"
    assert m.slug == "clinical_tirzepatide_t2dm"
    assert m.contradictions_found == 14
    assert m.cost_usd > 0.0
    assert m.cost_usd < m.budget_cap_usd
    assert m.v30_enabled is True
    assert m.evaluator_gate == "pass"
    assert m.release_allowed is True


def test_report_md_loaded(ir: AuditIR) -> None:
    assert isinstance(ir.report_md, str)
    assert len(ir.report_md) > 1000
    assert "[1]" in ir.report_md  # has at least one inline citation


def test_bibliography_loaded(ir: AuditIR) -> None:
    assert len(ir.bibliography) >= 5
    first = ir.bibliography[0]
    assert isinstance(first, BibliographyEntry)
    assert first.num >= 1
    assert first.evidence_id
    assert first.tier in {"T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN"}


def test_bibliography_lookup_by_num(ir: AuditIR) -> None:
    entry = ir.get_bibliography_by_num(1)
    assert entry is not None
    assert entry.num == 1
    assert entry.evidence_id == "surpass_1_primary"


def test_bibliography_lookup_by_evidence_id(ir: AuditIR) -> None:
    entry = ir.get_bibliography_by_evidence_id("surpass_2_primary")
    assert entry is not None
    assert entry.num == 2
    assert "Tirzepatide versus Semaglutide" in entry.statement


def test_bibliography_lookup_misses_return_none(ir: AuditIR) -> None:
    assert ir.get_bibliography_by_num(99999) is None
    assert ir.get_bibliography_by_evidence_id("nonexistent_id") is None


def test_contradictions_loaded(ir: AuditIR) -> None:
    # Manifest claims 14 contradictions; the file should match.
    assert len(ir.contradictions) == 14
    cluster = ir.contradictions[0]
    assert isinstance(cluster, ContradictionCluster)
    assert cluster.cluster_id == 0
    assert cluster.predicate
    assert cluster.absolute_difference >= 0.0
    assert len(cluster.claims) >= 2  # contradiction needs at least 2 claims


def test_contradiction_claims_have_evidence_ids(ir: AuditIR) -> None:
    for cluster in ir.contradictions:
        for claim in cluster.claims:
            assert claim.evidence_id  # every claim must back-link to evidence
            assert claim.source_tier
            assert claim.value is not None


def test_get_contradictions_for_evidence(ir: AuditIR) -> None:
    # ev_001 appears in run-14 contradictions.json
    clusters = ir.get_contradictions_for_evidence("ev_001")
    assert len(clusters) >= 1
    for cluster in clusters:
        assert any(c.evidence_id == "ev_001" for c in cluster.claims)


def test_frame_coverage_loaded(ir: AuditIR) -> None:
    fc = ir.frame_coverage
    assert isinstance(fc, FrameCoverageReport)
    assert fc.pass_count == 14
    assert fc.frame_gap_count >= 0
    assert fc.partial_count >= 0
    assert len(fc.entries) == 15  # run-14 has 15 entities
    assert fc.research_question


def test_frame_coverage_entry_lookup(ir: AuditIR) -> None:
    entry = ir.get_frame_coverage_for_entity("surpass_1_primary")
    assert entry is not None
    assert entry.entity_id == "surpass_1_primary"
    assert entry.entity_type == "pivotal_trial"
    assert entry.doi  # SURPASS-1 has a DOI in run-14
    assert entry.pmid


def test_tier_mix_loaded(ir: AuditIR) -> None:
    tm = ir.tier_mix
    assert isinstance(tm, TierMix)
    assert tm.corpus_count > 0
    # Tier fractions should sum approximately to 1.0
    assert abs(sum(tm.fractions.values()) - 1.0) < 0.01
    assert "T1" in tm.fractions


def test_tier_counts_derive_from_fractions(ir: AuditIR) -> None:
    counts = ir.get_tier_counts()
    assert "T1" in counts
    assert sum(counts.values()) > 0
    # T7 is the largest fraction in run-14 (28.18%)
    assert counts["T7"] > counts["T5"]


def test_loader_fails_loudly_on_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(NotADirectoryError):
        load_audit_ir(missing)


def test_loader_fails_loudly_on_missing_manifest(tmp_path: Path) -> None:
    empty = tmp_path / "empty_run"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        load_audit_ir(empty)


def test_audit_ir_is_frozen(ir: AuditIR) -> None:
    """AuditIR is immutable — renderers can't mutate the canonical IR."""
    with pytest.raises((AttributeError, Exception)):
        ir.run_id = "tampered"  # type: ignore[misc]
