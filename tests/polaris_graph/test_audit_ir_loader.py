"""Tests for src/polaris_graph/audit_ir/loader.py.

Loads the canonical run-14 V30 Phase-2 artifact and verifies the AuditIR
object exposes everything the Evidence Inspector renderers need.

Codex M-1 review (PARTIAL → 8 fixes integrated): each Codex finding has
a dedicated test asserting the fix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir import (
    IR_SCHEMA_VERSION,
    AuditIR,
    AuditIRSchemaError,
    BibliographyEntry,
    ContradictionCluster,
    EvaluatorGate,
    EvidenceSpanToken,
    FrameCoverageReport,
    ModelProvenance,
    ProtocolMetadata,
    ReportSection,
    ReportSentence,
    RetrievalAttempt,
    RetrievalStats,
    RuleCheck,
    RunManifest,
    TierExpectation,
    TierMix,
    VerifiedReport,
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
    return load_audit_ir(RUN_14_DIR)


# ---------------------------------------------------------------------------
# Top-level + schema versioning (Codex fix #6)
# ---------------------------------------------------------------------------


def test_loader_returns_audit_ir_instance(ir: AuditIR) -> None:
    assert isinstance(ir, AuditIR)
    assert ir.artifact_dir == RUN_14_DIR


def test_ir_schema_version_present(ir: AuditIR) -> None:
    """Codex fix #6: top-level IR versioning so V31/V32/V34 can evolve safely."""
    assert ir.ir_schema_version == IR_SCHEMA_VERSION
    assert ir.ir_schema_version  # non-empty


# ---------------------------------------------------------------------------
# Manifest (Codex fix #2: completeness, fix #4: evaluator gate richness)
# ---------------------------------------------------------------------------


def test_manifest_top_level_fields(ir: AuditIR) -> None:
    m = ir.manifest
    assert isinstance(m, RunManifest)
    assert m.run_id == "SWEEP_clinical_clinical_tirzepatide_t2dm_1777170058"
    assert m.slug == "clinical_tirzepatide_t2dm"
    assert m.contradictions_found == 14
    assert m.cost_usd > 0.0
    assert m.cost_usd < m.budget_cap_usd
    assert m.v30_enabled is True
    assert m.release_allowed is True


def test_completeness_percent_correctly_parsed(ir: AuditIR) -> None:
    """Codex fix #2: run-14 has 7/7 covered_fraction=1.0, must read as 100.0%.

    The pre-fix code looked for `covered_topics` / `total_topics` keys that
    don't exist in V30 manifests, silently returning 0.0.
    """
    assert ir.manifest.completeness_percent == 100.0


def test_evaluator_gate_is_rich_object(ir: AuditIR) -> None:
    """Codex fix #4: evaluator_gate must preserve reasons + rule_blockers."""
    gate = ir.manifest.evaluator_gate
    assert isinstance(gate, EvaluatorGate)
    assert gate.gate_class == "pass"
    assert gate.release_allowed is True
    # run-14 has one advisory reason
    assert len(gate.reasons) >= 1
    assert "advisory_pt13_unhedged_superlatives" in gate.reasons
    assert isinstance(gate.rule_blockers, tuple)
    assert isinstance(gate.qwen_critical_axes, tuple)


def test_v30_warnings_preserved(ir: AuditIR) -> None:
    """Codex fix #4: v30_warnings must be preserved (frame-coverage semantics)."""
    assert len(ir.manifest.v30_warnings) >= 1
    assert any(
        "phase1_retrieval_coverage_only" in w for w in ir.manifest.v30_warnings
    )


def test_retrieval_stats_present(ir: AuditIR) -> None:
    """Codex fix #4: retrieval stats (counts) must be captured."""
    stats = ir.manifest.retrieval_stats
    assert isinstance(stats, RetrievalStats)
    assert stats.pre_filter > 0
    assert stats.fetched > 0
    # run-14 has openalex/s2/serper providers
    assert "openalex" in stats.by_provider
    assert stats.by_provider["openalex"] > 0


# ---------------------------------------------------------------------------
# Report markdown
# ---------------------------------------------------------------------------


def test_report_md_loaded(ir: AuditIR) -> None:
    assert isinstance(ir.report_md, str)
    assert len(ir.report_md) > 1000
    assert "[1]" in ir.report_md  # has at least one inline citation


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Contradictions (Codex fix #5: severity, relative_difference, subject, action)
# ---------------------------------------------------------------------------


def test_contradictions_loaded(ir: AuditIR) -> None:
    assert len(ir.contradictions) == 14
    cluster = ir.contradictions[0]
    assert isinstance(cluster, ContradictionCluster)
    assert cluster.cluster_id == 0
    assert cluster.predicate
    assert cluster.absolute_difference >= 0.0
    assert len(cluster.claims) >= 2


def test_contradiction_cluster_metadata_preserved(ir: AuditIR) -> None:
    """Codex fix #5: severity, relative_difference, subject, recommended_action."""
    cluster = ir.contradictions[0]
    assert cluster.severity in {"low", "medium", "high", "critical", "unknown"}
    # run-14 first cluster is 'high' severity
    assert cluster.severity == "high"
    assert cluster.subject == "tirzepatide"
    assert cluster.relative_difference > 0.0
    assert "Disclose both values" in cluster.recommended_action


def test_contradiction_claims_have_evidence_ids(ir: AuditIR) -> None:
    for cluster in ir.contradictions:
        for claim in cluster.claims:
            assert claim.evidence_id
            assert claim.source_tier
            assert claim.value is not None


def test_get_contradictions_for_evidence(ir: AuditIR) -> None:
    clusters = ir.get_contradictions_for_evidence("ev_001")
    assert len(clusters) >= 1
    for cluster in clusters:
        assert any(c.evidence_id == "ev_001" for c in cluster.claims)


# ---------------------------------------------------------------------------
# Frame coverage (Codex fix #5: section, slot_id, subsection_title, etc.)
# ---------------------------------------------------------------------------


def test_frame_coverage_loaded(ir: AuditIR) -> None:
    fc = ir.frame_coverage
    assert isinstance(fc, FrameCoverageReport)
    assert fc.pass_count == 14
    assert fc.frame_gap_count >= 0
    assert fc.partial_count >= 0
    assert len(fc.entries) == 15
    assert fc.research_question


def test_frame_coverage_semantics_warning_preserved(ir: AuditIR) -> None:
    """Codex fix #5: V30 retrieval-coverage caveat must be on the report."""
    assert ir.frame_coverage.semantics_warning is not None
    assert "phase1_retrieval_coverage_only" in ir.frame_coverage.semantics_warning


def test_frame_coverage_entry_metadata_preserved(ir: AuditIR) -> None:
    """Codex fix #5: section, slot_id, subsection_title, min_fields, human_curated."""
    entry = ir.get_frame_coverage_for_entity("surpass_1_primary")
    assert entry is not None
    assert entry.section == "Efficacy"
    assert entry.slot_id == "efficacy_surpass_1"
    assert "SURPASS-1" in entry.subsection_title
    assert entry.min_fields_for_completion > 0
    # run-14 surpass_1 has no human-curated provenance
    assert entry.human_curated_provenance is None


def test_frame_coverage_retrieval_attempts_typed(ir: AuditIR) -> None:
    """Codex fix #3: retrieval_attempt_log entries are frozen RetrievalAttempt objects."""
    entry = ir.get_frame_coverage_for_entity("surpass_1_primary")
    assert entry is not None
    assert len(entry.retrieval_attempt_log) > 0
    for attempt in entry.retrieval_attempt_log:
        assert isinstance(attempt, RetrievalAttempt)
        assert attempt.source
        assert attempt.outcome


# ---------------------------------------------------------------------------
# Tier mix
# ---------------------------------------------------------------------------


def test_tier_mix_loaded(ir: AuditIR) -> None:
    tm = ir.tier_mix
    assert isinstance(tm, TierMix)
    assert tm.corpus_count > 0
    assert abs(sum(tm.fractions.values()) - 1.0) < 0.01
    assert "T1" in tm.fractions


def test_tier_counts_derive_from_fractions(ir: AuditIR) -> None:
    counts = ir.get_tier_counts()
    assert "T1" in counts
    assert sum(counts.values()) > 0
    assert counts["T7"] > counts["T5"]


# ---------------------------------------------------------------------------
# Verified report (Codex fix #1: verification_details.json must be loaded)
# ---------------------------------------------------------------------------


def test_verified_report_loaded(ir: AuditIR) -> None:
    """Codex fix #1: verification_details.json was not loaded — M-3 was blocked."""
    vr = ir.verified_report
    assert isinstance(vr, VerifiedReport)
    assert len(vr.sections) == 6  # run-14 has 6 sections
    assert vr.sentences_verified == 98
    assert vr.sentences_dropped == 51
    assert sum(vr.drop_reason_counts.values()) > 0


def test_verified_report_section_structure(ir: AuditIR) -> None:
    section = ir.verified_report.sections[0]
    assert isinstance(section, ReportSection)
    assert section.title
    assert section.kept_count >= 0
    assert section.dropped_count >= 0
    assert len(section.sentences) == section.kept_count + section.dropped_count


def test_verified_report_sentences_have_tokens(ir: AuditIR) -> None:
    """View 1 prerequisite: every sentence must have evidence span tokens."""
    found_with_tokens = 0
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            assert isinstance(sentence, ReportSentence)
            assert sentence.claim_id
            for token in sentence.tokens:
                assert isinstance(token, EvidenceSpanToken)
                assert token.evidence_id
                assert token.start <= token.end
            if sentence.tokens:
                found_with_tokens += 1
    assert found_with_tokens > 0


def test_get_sentence_by_claim_id(ir: AuditIR) -> None:
    """View 1 prerequisite: stable claim_id lookup must work."""
    section = ir.verified_report.sections[0]
    if section.sentences:
        first = section.sentences[0]
        sentence = ir.get_sentence_by_claim_id(first.claim_id)
        assert sentence is not None
        assert sentence.claim_id == first.claim_id


def test_get_evidence_spans_for_claim(ir: AuditIR) -> None:
    """View 1 prerequisite: claim_id -> evidence span tokens lookup."""
    # find any claim with at least one token
    found = False
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            if sentence.tokens:
                spans = ir.get_evidence_spans_for_claim(sentence.claim_id)
                assert len(spans) == len(sentence.tokens)
                found = True
                break
        if found:
            break
    assert found


def test_dropped_sentences_have_failure_reasons(ir: AuditIR) -> None:
    """Dropped sentences must surface why they failed (Inspector view 1 disclosure)."""
    dropped_with_reasons = 0
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            if not sentence.is_verified and sentence.failure_reasons:
                dropped_with_reasons += 1
    assert dropped_with_reasons > 0


def test_get_sentence_by_unknown_claim_id_returns_none(ir: AuditIR) -> None:
    assert ir.get_sentence_by_claim_id("nonexistent:kept:9999") is None


# ---------------------------------------------------------------------------
# Deep immutability (Codex fix #3)
# ---------------------------------------------------------------------------


def test_audit_ir_top_level_frozen(ir: AuditIR) -> None:
    with pytest.raises((AttributeError, Exception)):
        ir.run_id = "tampered"  # type: ignore[misc]


def test_tier_mix_fractions_is_read_only(ir: AuditIR) -> None:
    """Codex fix #3: nested dicts must not be mutable through the IR."""
    with pytest.raises(TypeError):
        ir.tier_mix.fractions["T1"] = 99.9  # type: ignore[index]


def test_drop_reason_counts_is_read_only(ir: AuditIR) -> None:
    with pytest.raises(TypeError):
        ir.verified_report.drop_reason_counts["fake"] = 1  # type: ignore[index]


def test_retrieval_stats_by_provider_is_read_only(ir: AuditIR) -> None:
    if ir.manifest.retrieval_stats is not None:
        with pytest.raises(TypeError):
            ir.manifest.retrieval_stats.by_provider["x"] = 1  # type: ignore[index]


# ---------------------------------------------------------------------------
# Fail-loud semantics (Codex fix #4)
# ---------------------------------------------------------------------------


def test_loader_fails_loudly_on_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(NotADirectoryError):
        load_audit_ir(missing)


def test_loader_fails_loudly_on_missing_manifest(tmp_path: Path) -> None:
    empty = tmp_path / "empty_run"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        load_audit_ir(empty)


def _scaffold_minimal_run(base: Path) -> Path:
    """Build a minimal-but-valid run dir for negative tests."""
    run = base / "run"
    run.mkdir()
    (run / "report.md").write_text("# stub", encoding="utf-8")
    (run / "bibliography.json").write_text("[]", encoding="utf-8")
    (run / "contradictions.json").write_text("[]", encoding="utf-8")
    (run / "verification_details.json").write_text(
        json.dumps({"sections": [], "totals": {}, "drop_reason_counts": {}}),
        encoding="utf-8",
    )
    minimal_manifest = {
        "run_id": "stub",
        "slug": "stub",
        "status": "ok",
        "question": "stub",
        "protocol_sha256": "0",
        "evaluator_gate": {"gate_class": "pass", "release_allowed": True},
        "completeness": {"covered_fraction": 1.0},
        "frame_coverage_report": {
            "by_status": {"pass": 0},
            "entries": [],
        },
        "corpus": {"tier_fractions": {"T1": 1.0}, "count": 1},
    }
    (run / "manifest.json").write_text(json.dumps(minimal_manifest), encoding="utf-8")
    return run


def test_minimal_valid_run_loads(tmp_path: Path) -> None:
    """Sanity check: minimal-but-valid scaffold loads without error."""
    run = _scaffold_minimal_run(tmp_path)
    ir = load_audit_ir(run)
    assert ir.run_id == "stub"


def test_loader_fails_loudly_on_missing_frame_coverage(tmp_path: Path) -> None:
    """Codex fix #4: missing required schema block must raise, not zero-fill."""
    run = _scaffold_minimal_run(tmp_path)
    manifest = json.loads((run / "manifest.json").read_text())
    del manifest["frame_coverage_report"]
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AuditIRSchemaError, match="frame_coverage_report"):
        load_audit_ir(run)


def test_loader_fails_loudly_on_missing_corpus_tier_fractions(tmp_path: Path) -> None:
    run = _scaffold_minimal_run(tmp_path)
    manifest = json.loads((run / "manifest.json").read_text())
    del manifest["corpus"]
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AuditIRSchemaError, match="corpus"):
        load_audit_ir(run)


def test_loader_fails_loudly_on_missing_evaluator_gate(tmp_path: Path) -> None:
    run = _scaffold_minimal_run(tmp_path)
    manifest = json.loads((run / "manifest.json").read_text())
    del manifest["evaluator_gate"]
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AuditIRSchemaError, match="evaluator_gate"):
        load_audit_ir(run)


def test_loader_fails_loudly_on_contradiction_with_too_few_claims(tmp_path: Path) -> None:
    """A contradiction cluster needs >= 2 claims; otherwise it's not a contradiction."""
    run = _scaffold_minimal_run(tmp_path)
    bad = [
        {
            "predicate": "x",
            "claims": [
                {"evidence_id": "ev_1", "predicate": "x", "value": 1.0}
            ],
        }
    ]
    (run / "contradictions.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AuditIRSchemaError, match=">=2"):
        load_audit_ir(run)


def test_loader_fails_loudly_on_contradiction_claim_missing_evidence_id(tmp_path: Path) -> None:
    run = _scaffold_minimal_run(tmp_path)
    bad = [
        {
            "predicate": "x",
            "claims": [
                {"predicate": "x", "value": 1.0},
                {"predicate": "x", "value": 2.0},
            ],
        }
    ]
    (run / "contradictions.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AuditIRSchemaError, match="evidence_id"):
        load_audit_ir(run)


def test_loader_fails_loudly_on_missing_verification_details(tmp_path: Path) -> None:
    run = _scaffold_minimal_run(tmp_path)
    (run / "verification_details.json").unlink()
    with pytest.raises(FileNotFoundError, match="verification_details"):
        load_audit_ir(run)


# ---------------------------------------------------------------------------
# Model provenance + Protocol metadata (Codex M-1 v2 review fix: View 4 prereq)
# ---------------------------------------------------------------------------


def test_model_provenance_loaded(ir: AuditIR) -> None:
    """Codex M-1 v2 fix: model/version provenance must be on the canonical IR."""
    mp = ir.model_provenance
    assert isinstance(mp, ModelProvenance)
    # Run-14 used deepseek generator and qwen evaluator (two-family invariant)
    assert mp.generator_family == "deepseek"
    assert mp.generator_model == "deepseek/deepseek-v3.2-exp"
    assert mp.evaluator_family == "qwen"
    assert mp.evaluator_model == "qwen/qwen3-8b"
    # Two-family invariant: generator and evaluator must be from different lineages
    assert mp.generator_family != mp.evaluator_family


def test_model_provenance_judge_metadata(ir: AuditIR) -> None:
    mp = ir.model_provenance
    assert mp is not None
    assert mp.judge_model == "qwen/qwen3-8b"
    assert mp.judge_parse_ok is True
    assert mp.judge_input_tokens > 0
    assert mp.judge_output_tokens > 0


def test_model_provenance_rule_checks(ir: AuditIR) -> None:
    """Run-14 has 13 rule checks; Inspector View 4 surfaces pass/fail per rule."""
    mp = ir.model_provenance
    assert mp is not None
    assert len(mp.rule_checks) >= 12  # run-14 has 13 rule checks
    for rc in mp.rule_checks:
        assert isinstance(rc, RuleCheck)
        assert rc.item_id  # PT01..PT13 in run-14
        assert rc.name


def test_model_provenance_contradictions_disclosed(ir: AuditIR) -> None:
    mp = ir.model_provenance
    assert mp is not None
    # Run-14 disclosed all 14 contradictions
    assert mp.contradictions_disclosed == 14
    assert isinstance(mp.contradictions_missing, tuple)


def test_protocol_metadata_loaded(ir: AuditIR) -> None:
    """Protocol metadata enables expected-vs-actual tier comparison in View 5."""
    proto = ir.protocol
    assert isinstance(proto, ProtocolMetadata)
    assert "tirzepatide" in proto.research_question.lower()
    assert proto.created_at_iso  # ISO timestamp string
    assert proto.created_at_unix > 0
    assert proto.scope_decision  # e.g. "scope_accepted"


def test_protocol_expected_tier_distribution(ir: AuditIR) -> None:
    proto = ir.protocol
    assert proto is not None
    assert len(proto.expected_tier_distribution) >= 5  # T1..T5+ at minimum
    for exp in proto.expected_tier_distribution:
        assert isinstance(exp, TierExpectation)
        assert exp.tier
        assert 0.0 <= exp.min_fraction <= exp.max_fraction <= 1.0


def test_model_provenance_optional_for_legacy_runs(tmp_path: Path) -> None:
    """Loader must not require model-provenance files (some legacy runs lack them)."""
    run = _scaffold_minimal_run(tmp_path)
    # No evaluator_rule_checks.json or qwen_judge_output.json or protocol.json
    ir = load_audit_ir(run)
    assert ir.model_provenance is None
    assert ir.protocol is None


def test_partial_model_provenance_fails_loud(tmp_path: Path) -> None:
    """Codex M-1 v3 edge case: if exactly ONE of the provenance files is present,
    fail loud rather than zero-fill the missing half."""
    run = _scaffold_minimal_run(tmp_path)
    (run / "evaluator_rule_checks.json").write_text(
        json.dumps({"generator_family": "x", "generator_model": "y"}),
        encoding="utf-8",
    )
    # qwen_judge_output.json deliberately absent
    with pytest.raises(AuditIRSchemaError, match="Partial model provenance"):
        load_audit_ir(run)


def test_partial_model_provenance_fails_loud_other_direction(tmp_path: Path) -> None:
    run = _scaffold_minimal_run(tmp_path)
    (run / "qwen_judge_output.json").write_text(
        json.dumps({"model": "x", "parse_ok": True}),
        encoding="utf-8",
    )
    # evaluator_rule_checks.json deliberately absent
    with pytest.raises(AuditIRSchemaError, match="Partial model provenance"):
        load_audit_ir(run)
