"""Tests for src/polaris_graph/audit_ir/regression_alerts.py (M-18)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.loader import (
    AdequacyGate,
    AuditIR,
    BibliographyEntry,
    ContradictionClaim,
    ContradictionCluster,
    EvaluatorGate,
    EvidenceSpanToken,
    FrameCoverageReport,
    IR_SCHEMA_VERSION,
    ReportSection,
    ReportSentence,
    RunManifest,
    TierMix,
    VerifiedReport,
)
from src.polaris_graph.audit_ir.regression_alerts import (
    AlertCode,
    AlertSeverity,
    RegressionAlert,
    RegressionReport,
    alert_to_dict,
    detect_regressions,
    report_to_dict,
)


# ---------------------------------------------------------------------------
# Synthetic IR builder — extends the run-diff/citation-health pattern
# with manifest fields the regression checker needs (release_allowed,
# gate_class, cost_usd, adequacy decision).
# ---------------------------------------------------------------------------


def _make_ir(
    *,
    slug: str = "x_drug_y_disease",
    run_id: str = "run_a",
    sentences: list[ReportSentence] | None = None,
    bibliography: tuple[BibliographyEntry, ...] = (),
    contradictions: tuple[ContradictionCluster, ...] = (),
    tier_fractions: dict[str, float] | None = None,
    release_allowed: bool = True,
    gate_class: str = "pass",
    cost_usd: float = 0.10,
    adequacy_decision: str | None = "pass",
) -> AuditIR:
    sentences = sentences or []
    n_kept = sum(1 for s in sentences if s.is_verified)
    n_dropped = sum(1 for s in sentences if not s.is_verified)
    sections = (ReportSection(
        title="Findings",
        kept_count=n_kept, dropped_count=n_dropped,
        total_in=len(sentences), dropped_due_to_failure=n_dropped,
        sentences=tuple(sentences),
    ),)
    verified = VerifiedReport(
        sections=sections,
        sentences_verified=n_kept,
        sentences_dropped=n_dropped,
        drop_reason_counts={},
    )
    fractions = tier_fractions or {"T1": 0.6, "T2": 0.3, "T3": 0.1}
    tier_mix = TierMix(
        fractions=fractions, corpus_count=len(bibliography),
        approved=True, material_deviation=False,
    )
    eg = EvaluatorGate(
        gate_class=gate_class, release_allowed=release_allowed,
        reasons=(), rule_blockers=(), qwen_critical_axes=(),
        qwen_parse_ok=True,
    )
    manifest = RunManifest(
        run_id=run_id, slug=slug, status="success", question="q",
        protocol_sha256="0" * 64, cost_usd=cost_usd, budget_cap_usd=10.0,
        word_count=0, sentences_verified=n_kept, sentences_dropped=n_dropped,
        contradictions_found=len(contradictions),
        completeness_percent=100.0,
        evaluator_gate=eg, release_allowed=release_allowed,
        v30_enabled=True, v30_warnings=(), retrieval_stats=None,
    )
    frame_coverage = FrameCoverageReport(
        pass_count=0, partial_count=0, frame_gap_count=0,
        pipeline_fault_count=0, total_entities=0, total_slots=0,
        research_question="q", schema_version="1.0",
        semantics_warning=None, entries=(),
    )
    adequacy = None
    if adequacy_decision is not None:
        adequacy = AdequacyGate(
            decision=adequacy_decision,
            findings_ok=10, findings_total=10,
            critical_count=0,
        )
    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION, run_id=run_id,
        artifact_dir=Path("/tmp"), report_md="", manifest=manifest,
        bibliography=bibliography, contradictions=contradictions,
        frame_coverage=frame_coverage, tier_mix=tier_mix,
        verified_report=verified, model_provenance=None,
        protocol=None, adequacy=adequacy, corpus_approval=None,
    )


def _sentence(claim_id: str, text: str = "claim",
              tokens: tuple[EvidenceSpanToken, ...] = (),
              *, is_verified: bool = True) -> ReportSentence:
    if not tokens:
        tokens = (EvidenceSpanToken(evidence_id="ev_a", start=0, end=10),)
    return ReportSentence(
        claim_id=claim_id, section="findings", text=text,
        tokens=tokens, is_verified=is_verified, failure_reasons=(),
    )


def _bib(num: int, eid: str, tier: str = "T1") -> BibliographyEntry:
    return BibliographyEntry(
        num=num, evidence_id=eid, statement="ok", tier=tier,
        url=f"https://example.com/{eid}",
    )


def _cluster(subject: str, predicate: str,
             severity: str = "medium") -> ContradictionCluster:
    return ContradictionCluster(
        cluster_id=1, subject=subject, predicate=predicate,
        severity=severity, absolute_difference=0.0,
        relative_difference=0.0, recommended_action="",
        claims=(
            ContradictionClaim(
                evidence_id="ev_a", subject=subject, predicate=predicate,
                arm="", dose="", value=0.0, unit="",
                source_tier="T1", source_url="", context_snippet="",
                endpoint_phrase="",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Sanity baseline
# ---------------------------------------------------------------------------


def test_identical_runs_produce_no_alerts() -> None:
    """Two identical runs must yield zero alerts and worst='ok'."""
    bib = (_bib(1, "ev_a"), _bib(2, "ev_b"))
    sentences = [_sentence("c1"), _sentence("c2")]
    ir = _make_ir(bibliography=bib, sentences=sentences, run_id="x")
    report = detect_regressions(ir, ir)
    assert report.alerts == ()
    assert report.summary.worst_severity == "ok"
    assert report.summary.critical_count == 0
    assert report.summary.high_count == 0


def test_slug_mismatch_raises() -> None:
    ir_a = _make_ir(slug="drug_a_disease")
    ir_b = _make_ir(slug="drug_b_disease")
    with pytest.raises(ValueError, match="same slug"):
        detect_regressions(ir_a, ir_b)


# ---------------------------------------------------------------------------
# CRITICAL alerts
# ---------------------------------------------------------------------------


def test_release_allowed_flip_is_critical() -> None:
    """release_allowed True (a) → False (b) is a CRITICAL flip."""
    ir_a = _make_ir(release_allowed=True, run_id="a")
    ir_b = _make_ir(release_allowed=False, gate_class="fail", run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.RELEASE_NOT_ALLOWED in codes
    rel_alert = next(
        a for a in report.alerts
        if a.code == AlertCode.RELEASE_NOT_ALLOWED
    )
    assert rel_alert.severity == AlertSeverity.CRITICAL
    assert report.summary.worst_severity == "critical"


def test_release_allowed_flip_b_to_a_does_not_alert() -> None:
    """A run that goes from blocked-to-allowed is an improvement,
    not a regression."""
    ir_a = _make_ir(release_allowed=False, gate_class="fail", run_id="a")
    ir_b = _make_ir(release_allowed=True, gate_class="pass", run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.RELEASE_NOT_ALLOWED not in codes


def test_evaluator_gate_pass_to_fail_is_critical() -> None:
    ir_a = _make_ir(gate_class="pass", run_id="a")
    ir_b = _make_ir(gate_class="fail", run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.EVALUATOR_GATE_DOWNGRADE in codes
    gate_alert = next(
        a for a in report.alerts
        if a.code == AlertCode.EVALUATOR_GATE_DOWNGRADE
    )
    assert gate_alert.severity == AlertSeverity.CRITICAL


def test_adequacy_pass_to_fail_is_critical() -> None:
    ir_a = _make_ir(adequacy_decision="pass", run_id="a")
    ir_b = _make_ir(adequacy_decision="fail", run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.ADEQUACY_REGRESSION in codes


def test_verified_drop_50pct_is_critical() -> None:
    """A 50%+ drop in verified-sentence count is CRITICAL."""
    sentences_a = [_sentence(f"c{i}") for i in range(10)]
    sentences_b = [_sentence(f"c{i}") for i in range(4)]  # 60% drop
    ir_a = _make_ir(sentences=sentences_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    drop_alerts = [
        a for a in report.alerts if a.code == AlertCode.VERIFIED_DROP
    ]
    assert len(drop_alerts) == 1
    assert drop_alerts[0].severity == AlertSeverity.CRITICAL


# ---------------------------------------------------------------------------
# HIGH alerts
# ---------------------------------------------------------------------------


def test_verified_drop_25pct_is_high() -> None:
    """25% drop sits between MEDIUM and CRITICAL → HIGH."""
    sentences_a = [_sentence(f"c{i}") for i in range(20)]
    sentences_b = [_sentence(f"c{i}") for i in range(15)]  # 25% drop
    ir_a = _make_ir(sentences=sentences_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    drop_alerts = [
        a for a in report.alerts if a.code == AlertCode.VERIFIED_DROP
    ]
    assert len(drop_alerts) == 1
    assert drop_alerts[0].severity == AlertSeverity.HIGH


def test_citation_drop_50pct_is_high() -> None:
    bib_a = tuple(_bib(i, f"ev_{i}") for i in range(1, 11))  # 10 entries
    bib_b = tuple(_bib(i, f"ev_{i}") for i in range(1, 5))   # 4 entries
    sentences_a = [_sentence(f"c{i}",
                              tokens=(EvidenceSpanToken(f"ev_{i}", 0, 10),))
                   for i in range(1, 11)]
    sentences_b = [_sentence(f"c{i}",
                              tokens=(EvidenceSpanToken(f"ev_{i}", 0, 10),))
                   for i in range(1, 5)]
    ir_a = _make_ir(bibliography=bib_a, sentences=sentences_a, run_id="a")
    ir_b = _make_ir(bibliography=bib_b, sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    cit_alerts = [a for a in report.alerts
                  if a.code == AlertCode.CITATION_DROP]
    assert len(cit_alerts) == 1
    assert cit_alerts[0].severity == AlertSeverity.HIGH


def test_new_high_severity_contradiction_is_high() -> None:
    ir_a = _make_ir(contradictions=(), run_id="a")
    ir_b = _make_ir(
        contradictions=(_cluster("dose", "endpoint", severity="high"),),
        run_id="b",
    )
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.NEW_HIGH_SEVERITY_CONTRADICTION in codes
    new_contra = next(
        a for a in report.alerts
        if a.code == AlertCode.NEW_HIGH_SEVERITY_CONTRADICTION
    )
    assert new_contra.severity == AlertSeverity.HIGH


def test_cost_spike_3x_is_high() -> None:
    ir_a = _make_ir(cost_usd=0.10, run_id="a")
    ir_b = _make_ir(cost_usd=0.40, run_id="b")  # 4x
    report = detect_regressions(ir_a, ir_b)
    cost_alerts = [a for a in report.alerts
                   if a.code == AlertCode.COST_SPIKE]
    assert len(cost_alerts) == 1
    assert cost_alerts[0].severity == AlertSeverity.HIGH


# ---------------------------------------------------------------------------
# MEDIUM alerts
# ---------------------------------------------------------------------------


def test_citation_drop_25pct_is_medium() -> None:
    bib_a = tuple(_bib(i, f"ev_{i}") for i in range(1, 21))  # 20
    bib_b = tuple(_bib(i, f"ev_{i}") for i in range(1, 16))  # 15 (25% drop)
    ir_a = _make_ir(bibliography=bib_a, run_id="a")
    ir_b = _make_ir(bibliography=bib_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    cit_alerts = [a for a in report.alerts
                  if a.code == AlertCode.CITATION_DROP]
    assert len(cit_alerts) == 1
    assert cit_alerts[0].severity == AlertSeverity.MEDIUM


def test_new_medium_severity_contradiction_is_medium() -> None:
    ir_a = _make_ir(contradictions=(), run_id="a")
    ir_b = _make_ir(
        contradictions=(_cluster("dose", "endpoint", severity="medium"),),
        run_id="b",
    )
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.NEW_CONTRADICTION in codes
    new_contra = next(
        a for a in report.alerts
        if a.code == AlertCode.NEW_CONTRADICTION
    )
    assert new_contra.severity == AlertSeverity.MEDIUM


def test_cost_spike_2x_is_medium() -> None:
    ir_a = _make_ir(cost_usd=0.10, run_id="a")
    ir_b = _make_ir(cost_usd=0.20, run_id="b")  # 2x
    report = detect_regressions(ir_a, ir_b)
    cost_alerts = [a for a in report.alerts
                   if a.code == AlertCode.COST_SPIKE]
    assert len(cost_alerts) == 1
    assert cost_alerts[0].severity == AlertSeverity.MEDIUM


def test_tier_downgrade_15pp_is_medium() -> None:
    """T1+T2 dropped from 90% to 75% (15pp drop) → MEDIUM."""
    ir_a = _make_ir(
        tier_fractions={"T1": 0.6, "T2": 0.3, "T3": 0.1},
        run_id="a",
    )
    ir_b = _make_ir(
        tier_fractions={"T1": 0.5, "T2": 0.25, "T3": 0.25},  # T1+T2=0.75
        run_id="b",
    )
    report = detect_regressions(ir_a, ir_b)
    tier_alerts = [a for a in report.alerts
                   if a.code == AlertCode.TIER_DOWNGRADE]
    assert len(tier_alerts) == 1
    assert tier_alerts[0].severity == AlertSeverity.MEDIUM


def test_tier_downgrade_35pp_is_high() -> None:
    """T1+T2 dropped from 90% to 50% (40pp drop) → HIGH."""
    ir_a = _make_ir(
        tier_fractions={"T1": 0.6, "T2": 0.3, "T3": 0.1},
        run_id="a",
    )
    ir_b = _make_ir(
        tier_fractions={"T1": 0.3, "T2": 0.2, "T3": 0.5},  # T1+T2=0.5
        run_id="b",
    )
    report = detect_regressions(ir_a, ir_b)
    tier_alerts = [a for a in report.alerts
                   if a.code == AlertCode.TIER_DOWNGRADE]
    assert len(tier_alerts) == 1
    assert tier_alerts[0].severity == AlertSeverity.HIGH


# ---------------------------------------------------------------------------
# Threshold edges + env override
# ---------------------------------------------------------------------------


def test_below_threshold_does_not_alert() -> None:
    """A 15% drop is BELOW the default 20% threshold → no alert."""
    sentences_a = [_sentence(f"c{i}") for i in range(20)]
    sentences_b = [_sentence(f"c{i}") for i in range(17)]  # 15% drop
    ir_a = _make_ir(sentences=sentences_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.VERIFIED_DROP not in codes


def test_verified_drop_threshold_env_overridable(monkeypatch) -> None:
    """LAW VI: tightening the threshold via env makes a smaller drop
    surface."""
    monkeypatch.setenv("PG_REGRESSION_VERIFIED_DROP_PCT", "0.05")
    sentences_a = [_sentence(f"c{i}") for i in range(20)]
    sentences_b = [_sentence(f"c{i}") for i in range(18)]  # 10% drop
    ir_a = _make_ir(sentences=sentences_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    assert AlertCode.VERIFIED_DROP in codes


def test_garbage_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("PG_REGRESSION_VERIFIED_DROP_PCT", "not_a_float")
    sentences_a = [_sentence(f"c{i}") for i in range(10)]
    sentences_b = [_sentence(f"c{i}") for i in range(8)]  # 20%
    ir_a = _make_ir(sentences=sentences_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    codes = {a.code for a in report.alerts}
    # Default threshold 0.20; 20% drop hits exactly → HIGH
    assert AlertCode.VERIFIED_DROP in codes


# ---------------------------------------------------------------------------
# Compound severity (worst-severity selection)
# ---------------------------------------------------------------------------


def test_critical_dominates_lower_severities() -> None:
    """When a run produces alerts at multiple severities, summary
    must report the WORST level (not the count or the most common)."""
    sentences_a = [_sentence(f"c{i}") for i in range(10)]
    sentences_b = [_sentence(f"c{i}") for i in range(4)]  # 60% drop CRITICAL
    bib_a = tuple(_bib(i, f"ev_{i}") for i in range(1, 21))
    bib_b = tuple(_bib(i, f"ev_{i}") for i in range(1, 16))  # 25% drop MEDIUM
    ir_a = _make_ir(sentences=sentences_a, bibliography=bib_a, run_id="a")
    ir_b = _make_ir(sentences=sentences_b, bibliography=bib_b, run_id="b")
    report = detect_regressions(ir_a, ir_b)
    assert report.summary.worst_severity == "critical"
    assert report.summary.critical_count >= 1
    assert report.summary.medium_count >= 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_alert_to_dict_round_trip() -> None:
    alert = RegressionAlert(
        severity=AlertSeverity.HIGH,
        code=AlertCode.VERIFIED_DROP,
        message="x",
        a_value=20, b_value=10, threshold=0.20,
    )
    d = alert_to_dict(alert)
    assert d["severity"] == "high"
    assert d["code"] == "verified_drop"
    assert d["a_value"] == 20
    assert d["b_value"] == 10
    assert d["threshold"] == 0.20


def test_report_to_dict_serializes_summary_and_alerts() -> None:
    ir_a = _make_ir(release_allowed=True, run_id="a")
    ir_b = _make_ir(release_allowed=False, gate_class="fail", run_id="b")
    report = detect_regressions(ir_a, ir_b)
    d = report_to_dict(report)
    assert d["a_run_id"] == "a"
    assert d["b_run_id"] == "b"
    assert d["slug"] == "x_drug_y_disease"
    assert isinstance(d["alerts"], list)
    assert d["summary"]["worst_severity"] == "critical"


# ---------------------------------------------------------------------------
# HTTP endpoint integration
# ---------------------------------------------------------------------------


def test_regression_endpoint_returns_404_for_unknown_slug() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.polaris_graph.audit_ir.inspector_router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.get(
        "/api/inspector/runs/regression",
        params={"slug": "missing_a", "baseline_slug": "missing_b"},
    )
    assert res.status_code == 404


def test_regression_endpoint_does_not_route_to_slug_dynamic() -> None:
    """Critical M-16-style ordering check: /runs/regression must NOT
    be matched as /runs/{slug} with slug='regression'. Without the
    pre-{slug} registration, FastAPI would return 404 with detail
    'Unknown run slug: regression' instead of asking for params."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.polaris_graph.audit_ir.inspector_router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Hit /runs/regression with NO baseline_slug param. If the route
    # is correctly registered, FastAPI returns 422 (missing required
    # query param). If it's mis-routed to /runs/{slug}, it returns
    # 404 (or 200 with a stub response).
    res = client.get("/api/inspector/runs/regression")
    assert res.status_code == 422, (
        f"expected 422 for missing baseline_slug, got {res.status_code}; "
        f"this likely means the route is being matched as /runs/{{slug}} "
        f"with slug='regression'. body: {res.json()}"
    )
