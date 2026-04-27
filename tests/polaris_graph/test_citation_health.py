"""Tests for src/polaris_graph/audit_ir/citation_health.py (M-17)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.citation_health import (
    CitationHealthIssue,
    CitationHealthReport,
    CitationIssueCode,
    IssueSeverity,
    check_citation_health,
    issue_to_dict,
    report_to_dict,
)
from src.polaris_graph.audit_ir.loader import (
    AuditIR,
    BibliographyEntry,
    EvidenceSpanToken,
    ReportSection,
    ReportSentence,
    VerifiedReport,
    load_audit_ir,
)


# ---------------------------------------------------------------------------
# Synthetic IR builder — same pattern used by test_run_diff.py
# ---------------------------------------------------------------------------


def _make_minimal_ir(
    *,
    slug: str = "x_drug_y_disease",
    run_id: str = "run_a",
    sentences: list[ReportSentence] | None = None,
    bibliography: tuple[BibliographyEntry, ...] = (),
    tier_fractions: dict[str, float] | None = None,
) -> AuditIR:
    """Minimum-viable AuditIR for citation-health tests."""
    from src.polaris_graph.audit_ir.loader import (
        EvaluatorGate,
        FrameCoverageReport,
        IR_SCHEMA_VERSION,
        RunManifest,
        TierMix,
    )
    sentences = sentences or []
    n_kept = sum(1 for s in sentences if s.is_verified)
    n_dropped = sum(1 for s in sentences if not s.is_verified)
    sections = (ReportSection(
        title="Findings",
        kept_count=n_kept,
        dropped_count=n_dropped,
        total_in=len(sentences),
        dropped_due_to_failure=n_dropped,
        sentences=tuple(sentences),
    ),)
    verified = VerifiedReport(
        sections=sections,
        sentences_verified=n_kept,
        sentences_dropped=n_dropped,
        drop_reason_counts={},
    )
    fractions = tier_fractions or {"T1": 1.0}
    tier_mix = TierMix(
        fractions=fractions, corpus_count=len(bibliography),
        approved=True, material_deviation=False,
    )
    eg = EvaluatorGate(
        gate_class="pass", release_allowed=True, reasons=(),
        rule_blockers=(), qwen_critical_axes=(), qwen_parse_ok=True,
    )
    manifest = RunManifest(
        run_id=run_id, slug=slug, status="success", question="q",
        protocol_sha256="0" * 64, cost_usd=0.0, budget_cap_usd=10.0,
        word_count=0, sentences_verified=n_kept, sentences_dropped=n_dropped,
        contradictions_found=0, completeness_percent=100.0,
        evaluator_gate=eg, release_allowed=True, v30_enabled=True,
        v30_warnings=(), retrieval_stats=None,
    )
    frame_coverage = FrameCoverageReport(
        pass_count=0, partial_count=0, frame_gap_count=0,
        pipeline_fault_count=0, total_entities=0, total_slots=0,
        research_question="q", schema_version="1.0",
        semantics_warning=None, entries=(),
    )
    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION, run_id=run_id,
        artifact_dir=Path("/tmp"), report_md="", manifest=manifest,
        bibliography=bibliography, contradictions=(),
        frame_coverage=frame_coverage, tier_mix=tier_mix,
        verified_report=verified, model_provenance=None,
        protocol=None, adequacy=None, corpus_approval=None,
    )


def _sentence(
    claim_id: str,
    text: str,
    tokens: tuple[EvidenceSpanToken, ...] = (),
    *,
    is_verified: bool = True,
    section: str = "findings",
) -> ReportSentence:
    return ReportSentence(
        claim_id=claim_id, section=section, text=text,
        tokens=tokens, is_verified=is_verified, failure_reasons=(),
    )


def _bib(
    num: int,
    eid: str,
    statement: str = "valid statement",
    tier: str = "T1",
    url: str = "https://example.com",
) -> BibliographyEntry:
    return BibliographyEntry(
        num=num, evidence_id=eid, statement=statement, tier=tier, url=url,
    )


def _tok(eid: str, start: int = 0, end: int = 100) -> EvidenceSpanToken:
    return EvidenceSpanToken(evidence_id=eid, start=start, end=end)


# ---------------------------------------------------------------------------
# Healthy baseline
# ---------------------------------------------------------------------------


def test_healthy_ir_returns_green_status() -> None:
    """A well-formed IR — every sentence's tokens resolve in
    bibliography, no duplicates, no invalid spans — must come back
    green with no issues."""
    bib = (_bib(1, "ev_a"), _bib(2, "ev_b"))
    sentences = [
        _sentence("c1", "claim a", tokens=(_tok("ev_a", 0, 50),)),
        _sentence("c2", "claim b", tokens=(_tok("ev_b", 0, 50),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    assert report.summary.overall_status == "green"
    assert report.summary.error_count == 0
    assert report.summary.warning_count == 0
    assert report.issues == ()


# ---------------------------------------------------------------------------
# ERROR cases (drive overall_status → red)
# ---------------------------------------------------------------------------


def test_broken_ref_surfaces_as_error() -> None:
    """A token cites an evidence_id with no matching bibliography
    entry. This is a citation-graph integrity bug and must be ERROR
    — the rendered report has a citation that doesn't ground."""
    bib = (_bib(1, "ev_real"),)
    sentences = [
        _sentence("c1", "phantom citation",
                  tokens=(_tok("ev_phantom", 0, 50),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    assert report.summary.overall_status == "red"
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.BROKEN_REF in codes
    broken = next(i for i in report.issues
                  if i.code == CitationIssueCode.BROKEN_REF)
    assert broken.severity == IssueSeverity.ERROR
    assert broken.evidence_id == "ev_phantom"
    assert broken.claim_id == "c1"


def test_invalid_span_negative_start_surfaces_as_error() -> None:
    bib = (_bib(1, "ev_a"),)
    sentences = [
        _sentence("c1", "negative span",
                  tokens=(_tok("ev_a", start=-1, end=50),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.INVALID_SPAN in codes
    assert report.summary.overall_status == "red"


def test_invalid_span_end_le_start_surfaces_as_error() -> None:
    bib = (_bib(1, "ev_a"),)
    sentences = [
        _sentence("c1", "zero-length",
                  tokens=(_tok("ev_a", start=10, end=10),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.INVALID_SPAN in codes


def test_invalid_tier_surfaces_as_error() -> None:
    """Tier values must be one of T1..T7 or UNKNOWN. Anything else
    means the IR's tier-mix accounting is broken."""
    bib = (_bib(1, "ev_a", tier="bronze"),)
    sentences = [_sentence("c1", "fine claim",
                           tokens=(_tok("ev_a", 0, 50),))]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.INVALID_TIER in codes
    assert report.summary.overall_status == "red"


def test_extended_v30_tiers_pass_validation() -> None:
    """T5/T6/T7 + UNKNOWN are valid V30 tiers and must NOT trigger
    INVALID_TIER. Codex M-16 v2 review surfaced that real V30 runs
    use the extended set; M-17 must respect that."""
    bib = (
        _bib(1, "ev_a", tier="T5"),
        _bib(2, "ev_b", tier="T6"),
        _bib(3, "ev_c", tier="T7"),
        _bib(4, "ev_d", tier="UNKNOWN"),
    )
    sentences = [
        _sentence(f"c{i}", "claim",
                  tokens=(_tok(eid, 0, 50),))
        for i, eid in enumerate(("ev_a", "ev_b", "ev_c", "ev_d"), start=1)
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.INVALID_TIER not in codes


def test_duplicate_evidence_id_surfaces_as_error() -> None:
    """Two bibliography entries with the same evidence_id break the
    one-to-one ev_id ↔ source mapping — every renderer assumes
    that mapping, so this is ERROR."""
    bib = (_bib(1, "ev_dup"), _bib(2, "ev_dup", statement="other"))
    ir = _make_minimal_ir(bibliography=bib, sentences=[])
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.DUPLICATE_EVIDENCE_ID in codes
    assert report.summary.overall_status == "red"


def test_duplicate_bib_num_surfaces_as_error() -> None:
    """Two entries with the same num [N] would break the
    [N] → source UI navigation."""
    bib = (_bib(1, "ev_a"), _bib(1, "ev_b"))
    ir = _make_minimal_ir(bibliography=bib, sentences=[])
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.DUPLICATE_BIB_NUM in codes


def test_non_positive_bib_num_surfaces_as_error() -> None:
    bib = (_bib(0, "ev_a"),)
    ir = _make_minimal_ir(bibliography=bib, sentences=[])
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.NON_POSITIVE_BIB_NUM in codes


def test_empty_statement_surfaces_as_error() -> None:
    bib = (_bib(1, "ev_a", statement="   "),)
    ir = _make_minimal_ir(bibliography=bib, sentences=[])
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.EMPTY_STATEMENT in codes


def test_verified_sentence_no_tokens_surfaces_as_error() -> None:
    """A verified sentence with empty tokens means strict_verify
    let something through that shouldn't have rendered. ERROR."""
    bib = ()
    sentences = [_sentence("c1", "kept but no tokens", tokens=())]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.VERIFIED_NO_TOKENS in codes
    assert report.summary.overall_status == "red"


def test_dropped_sentence_with_no_tokens_does_not_surface() -> None:
    """Dropped sentences (is_verified=False) are explicitly NOT
    part of the rendered citation graph and don't get health-checked."""
    bib = (_bib(1, "ev_a"),)
    sentences = [
        _sentence("c1", "kept", tokens=(_tok("ev_a", 0, 50),)),
        _sentence("c2", "dropped", tokens=(), is_verified=False),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    assert report.summary.overall_status == "green"
    assert report.issues == ()


# ---------------------------------------------------------------------------
# WARNING cases (drive overall_status → yellow if no errors)
# ---------------------------------------------------------------------------


def test_orphan_bibliography_entry_surfaces_as_warning() -> None:
    """A bibliography entry never cited by a verified sentence
    should be flagged for reviewer attention but doesn't block."""
    bib = (_bib(1, "ev_used"), _bib(2, "ev_orphan"))
    sentences = [
        _sentence("c1", "claim", tokens=(_tok("ev_used", 0, 50),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.ORPHAN_EVIDENCE in codes
    orphan = next(i for i in report.issues
                  if i.code == CitationIssueCode.ORPHAN_EVIDENCE)
    assert orphan.severity == IssueSeverity.WARNING
    assert orphan.evidence_id == "ev_orphan"
    # No errors — so status is yellow not red.
    assert report.summary.overall_status == "yellow"


def test_empty_url_surfaces_as_warning() -> None:
    bib = (_bib(1, "ev_a", url=""),)
    sentences = [_sentence("c1", "claim",
                           tokens=(_tok("ev_a", 0, 50),))]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    codes = {i.code for i in report.issues}
    assert CitationIssueCode.EMPTY_URL in codes
    empty_url = next(i for i in report.issues
                     if i.code == CitationIssueCode.EMPTY_URL)
    assert empty_url.severity == IssueSeverity.WARNING


# ---------------------------------------------------------------------------
# Severity mixing — error wins over warning
# ---------------------------------------------------------------------------


def test_error_dominates_warning_in_overall_status() -> None:
    """When both ERROR and WARNING surface, status must be red, not
    yellow. ERROR is the gating signal."""
    bib = (_bib(1, "ev_used"), _bib(2, "ev_orphan", url=""))
    sentences = [
        _sentence("c1", "broken", tokens=(_tok("ev_phantom", 0, 50),)),
    ]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    assert report.summary.overall_status == "red"
    assert report.summary.error_count >= 1
    assert report.summary.warning_count >= 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_issue_to_dict_round_trip() -> None:
    issue = CitationHealthIssue(
        severity=IssueSeverity.ERROR,
        code=CitationIssueCode.BROKEN_REF,
        message="example",
        evidence_id="ev_x",
        bib_num=42,
        section_title="Findings",
        claim_id="c1",
    )
    d = issue_to_dict(issue)
    assert d["severity"] == "error"
    assert d["code"] == "broken_ref"
    assert d["message"] == "example"
    assert d["evidence_id"] == "ev_x"
    assert d["bib_num"] == 42
    assert d["section_title"] == "Findings"
    assert d["claim_id"] == "c1"


def test_report_to_dict_serializes_summary_and_issues() -> None:
    bib = (_bib(1, "ev_a"),)
    sentences = [_sentence("c1", "claim",
                           tokens=(_tok("ev_a", 0, 50),))]
    ir = _make_minimal_ir(bibliography=bib, sentences=sentences)
    report = check_citation_health(ir)
    d = report_to_dict(report)
    assert d["summary"]["overall_status"] == "green"
    assert d["summary"]["error_count"] == 0
    assert d["summary"]["warning_count"] == 0
    assert d["summary"]["info_count"] == 0
    assert d["summary"]["total_evidence"] == 1
    assert d["issues"] == []


# ---------------------------------------------------------------------------
# Real-data sanity check (run-14 if available)
# ---------------------------------------------------------------------------


def _run14_artifact_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return (
        repo_root / "outputs" / "full_scale_v30_phase2_run14"
        / "clinical" / "clinical_tirzepatide_t2dm"
    )


def test_real_run14_loads_and_health_checks() -> None:
    """Smoke test against a real V30 run. Verifies the loader →
    health-check pipeline doesn't throw on production-shape data
    and returns a well-formed report.

    Note: M-17 v1 surfaced two broken refs and two orphans on
    run-14 (ev_162/ev_185 cited but not in bibliography; canonical
    handles hc_mounjaro_monograph/surpass_cvot_primary in
    bibliography but never cited). The mismatch is a real V30
    bibliography-normalization defect — M-17 catching it is the
    point of this milestone, not a regression of it. The defect
    is tracked separately for V30 bibliography fix work; this
    test only asserts that the health-check runs cleanly."""
    artifact_dir = _run14_artifact_dir()
    if not (artifact_dir / "manifest.json").exists():
        pytest.skip("run-14 artifacts not available")
    ir = load_audit_ir(artifact_dir)
    report = check_citation_health(ir)
    assert isinstance(report, CitationHealthReport)
    assert report.summary.overall_status in {"green", "yellow", "red"}
    assert report.summary.total_evidence == len(ir.bibliography)
    # Sanity: counts add up.
    assert (
        report.summary.error_count
        + report.summary.warning_count
        + report.summary.info_count
        == len(report.issues)
    )


# ---------------------------------------------------------------------------
# HTTP endpoint integration
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_404_for_unknown_slug() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.polaris_graph.audit_ir.inspector_router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.get("/api/inspector/runs/does_not_exist/health")
    assert res.status_code == 404
    assert "Unknown run slug" in res.json()["detail"]


def test_health_endpoint_returns_200_for_real_run() -> None:
    """Smoke: hit the live endpoint against run-14 if available."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.polaris_graph.audit_ir.inspector_router import (
        router,
        find_run_by_slug,
    )

    artifact_dir = _run14_artifact_dir()
    if not (artifact_dir / "manifest.json").exists():
        pytest.skip("run-14 artifacts not available")

    # Use the slug the run is mounted under by find_run_by_slug.
    ir = load_audit_ir(artifact_dir)
    slug = ir.manifest.slug
    if find_run_by_slug(slug) is None:
        pytest.skip(f"run {slug} not registered with router")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.get(f"/api/inspector/runs/{slug}/health")
    assert res.status_code == 200
    body = res.json()
    assert "summary" in body
    assert body["summary"]["overall_status"] in {"green", "yellow", "red"}
    assert "issues" in body
    assert isinstance(body["issues"], list)
