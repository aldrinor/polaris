"""Tests for src/polaris_graph/audit_ir/run_diff.py (M-16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import replace

import pytest

from src.polaris_graph.audit_ir.loader import (
    AuditIR,
    BibliographyEntry,
    ContradictionCluster,
    ReportSection,
    ReportSentence,
    RunManifest,
    TierMix,
    VerifiedReport,
    load_audit_ir,
)
from src.polaris_graph.audit_ir.run_diff import (
    ClaimDelta,
    ContradictionDelta,
    EvidenceDelta,
    RunDiff,
    TierMixShift,
    diff_runs,
    diff_to_dict,
    is_material,
)


# ---------------------------------------------------------------------------
# Real-data baseline: load run-14 and diff it against itself
# ---------------------------------------------------------------------------


def _run14_artifact_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return (
        repo_root / "outputs" / "full_scale_v30_phase2_run14"
        / "clinical" / "clinical_tirzepatide_t2dm"
    )


def test_self_diff_is_empty() -> None:
    """A run diffed against itself produces no deltas."""
    artifact_dir = _run14_artifact_dir()
    if not (artifact_dir / "manifest.json").exists():
        pytest.skip("run-14 artifacts not available")
    ir = load_audit_ir(artifact_dir)
    d = diff_runs(ir, ir)
    assert d.claim_deltas == ()
    assert d.evidence_deltas == ()
    assert d.contradiction_deltas == ()
    assert d.tier_shifts == ()
    assert d.slug == ir.manifest.slug
    assert d.a_run_id == d.b_run_id == ir.manifest.run_id
    assert is_material(d) is False


def test_self_diff_serializes() -> None:
    artifact_dir = _run14_artifact_dir()
    if not (artifact_dir / "manifest.json").exists():
        pytest.skip("run-14 artifacts not available")
    ir = load_audit_ir(artifact_dir)
    d = diff_runs(ir, ir)
    j = diff_to_dict(d)
    assert j["slug"] == ir.manifest.slug
    assert j["claim_deltas"] == []
    assert j["evidence_deltas"] == []
    assert j["contradiction_deltas"] == []
    assert j["tier_shifts"] == []


# ---------------------------------------------------------------------------
# Synthetic AuditIRs to test specific diff cases
# ---------------------------------------------------------------------------


def _make_minimal_ir(
    *,
    slug: str = "x_drug_y_disease",
    run_id: str = "run_a",
    sentences: list[ReportSentence] | None = None,
    bibliography: tuple[BibliographyEntry, ...] = (),
    contradictions: tuple[ContradictionCluster, ...] = (),
    tier_fractions: dict[str, float] | None = None,
) -> AuditIR:
    """Build a minimum-viable AuditIR for diff tests. Most fields
    not needed by diff are filled with defaults."""
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
    fractions = tier_fractions or {
        "tier1": 0.4, "tier2": 0.3, "tier3": 0.2, "tier4": 0.1,
    }
    tier_mix = TierMix(
        fractions=fractions,
        corpus_count=100,
        approved=True,
        material_deviation=False,
    )
    # Minimal RunManifest; many fields are required by the
    # dataclass but not by diff.
    from src.polaris_graph.audit_ir.loader import EvaluatorGate
    eg = EvaluatorGate(
        gate_class="pass",
        release_allowed=True,
        reasons=(),
        rule_blockers=(),
        qwen_critical_axes=(),
        qwen_parse_ok=True,
    )
    manifest = RunManifest(
        run_id=run_id,
        slug=slug,
        status="success",
        question="q",
        protocol_sha256="0" * 64,
        cost_usd=0.0,
        budget_cap_usd=10.0,
        word_count=0,
        sentences_verified=0,
        sentences_dropped=0,
        contradictions_found=len(contradictions),
        completeness_percent=100.0,
        evaluator_gate=eg,
        release_allowed=True,
        v30_enabled=True,
        v30_warnings=(),
        retrieval_stats=None,
    )
    from src.polaris_graph.audit_ir.loader import (
        FrameCoverageReport,
        IR_SCHEMA_VERSION,
    )
    frame_coverage = FrameCoverageReport(
        pass_count=0, partial_count=0, frame_gap_count=0,
        pipeline_fault_count=0, total_entities=0, total_slots=0,
        research_question="q", schema_version="1.0",
        semantics_warning=None, entries=(),
    )
    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION,
        run_id=run_id,
        artifact_dir=Path("/tmp"),
        report_md="",
        manifest=manifest,
        bibliography=bibliography,
        contradictions=contradictions,
        frame_coverage=frame_coverage,
        tier_mix=tier_mix,
        verified_report=verified,
        model_provenance=None,
        protocol=None,
        adequacy=None,
        corpus_approval=None,
    )


def _sentence(claim_id: str, text: str, *,
              section: str = "findings", is_verified: bool = True) -> ReportSentence:
    return ReportSentence(
        claim_id=claim_id, section=section, text=text,
        tokens=(), is_verified=is_verified, failure_reasons=(),
    )


def _bib(num: int, eid: str, statement: str, tier: str = "tier1",
         url: str = "https://example.com") -> BibliographyEntry:
    return BibliographyEntry(
        num=num, evidence_id=eid, statement=statement, tier=tier, url=url,
    )


def _cluster(cluster_id: int, subject: str, predicate: str,
             severity: str = "medium") -> ContradictionCluster:
    return ContradictionCluster(
        cluster_id=cluster_id, subject=subject, predicate=predicate,
        severity=severity, absolute_difference=0.0, relative_difference=0.0,
        recommended_action="", claims=(),
    )


# ---------------------------------------------------------------------------
# Slug mismatch
# ---------------------------------------------------------------------------


def test_diff_runs_slug_mismatch_raises() -> None:
    ir_a = _make_minimal_ir(slug="alpha_x")
    ir_b = _make_minimal_ir(slug="beta_y")
    with pytest.raises(ValueError, match="slug mismatch"):
        diff_runs(ir_a, ir_b)


# ---------------------------------------------------------------------------
# Claim deltas
# ---------------------------------------------------------------------------


def test_added_claim_surfaces_in_diff() -> None:
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "Tirzepatide is effective."),
    ])
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "Tirzepatide is effective."),
        _sentence("findings:verified:1", "Common adverse events include nausea."),
    ])
    d = diff_runs(ir_a, ir_b)
    assert len(d.claim_deltas) == 1
    delta = d.claim_deltas[0]
    assert delta.direction == "added"
    assert "nausea" in delta.text


def test_removed_claim_surfaces_in_diff() -> None:
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "First claim."),
        _sentence("findings:verified:1", "Second claim."),
    ])
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "First claim."),
    ])
    d = diff_runs(ir_a, ir_b)
    assert len(d.claim_deltas) == 1
    assert d.claim_deltas[0].direction == "removed"
    assert "Second claim" in d.claim_deltas[0].text


def test_unchanged_claims_do_not_surface() -> None:
    common = [
        _sentence("findings:verified:0", "Same claim."),
        _sentence("findings:verified:1", "Another claim."),
    ]
    ir_a = _make_minimal_ir(sentences=common)
    ir_b = _make_minimal_ir(sentences=common)
    d = diff_runs(ir_a, ir_b)
    assert d.claim_deltas == ()


def test_whitespace_only_change_is_noise_not_material() -> None:
    """Codex M-16 v2 review fix: claims keyed by stable
    content handle (section + normalized text). Whitespace
    differences in the same claim normalize away → no delta."""
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "tirzepatide   is effective"),
    ])
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:9", "tirzepatide is effective"),
    ])
    d = diff_runs(ir_a, ir_b)
    # Same content, different run-local idx → no delta.
    assert d.claim_deltas == ()


def test_claim_idx_renumber_does_not_surface() -> None:
    """Codex M-16 v2 review regression: claim_id was run-local
    `<section>:<status>:<idx>`. Re-running the audit could shift
    idx and produce false add/remove deltas. v2 keys by stable
    content handle (section + normalized text)."""
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "Claim A."),
        _sentence("findings:verified:1", "Claim B."),
    ])
    # Same two claims in B but with shifted idx (re-run reorder).
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:5", "Claim B."),  # was idx 1
        _sentence("findings:verified:7", "Claim A."),  # was idx 0
    ])
    d = diff_runs(ir_a, ir_b)
    assert d.claim_deltas == (), (
        "claim_id idx renumber must not surface as a delta"
    )


# ---------------------------------------------------------------------------
# Evidence deltas
# ---------------------------------------------------------------------------


def test_added_evidence_surfaces() -> None:
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_x", "Smith 2023", url="https://example.com/smith"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_x", "Smith 2023", url="https://example.com/smith"),
        _bib(2, "ev_y", "Jones 2024", url="https://example.com/jones"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert len(d.evidence_deltas) == 1
    assert d.evidence_deltas[0].direction == "added"
    assert "Jones" in d.evidence_deltas[0].statement


def test_removed_evidence_surfaces() -> None:
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_x", "Smith 2023", url="https://example.com/smith"),
        _bib(2, "ev_y", "Jones 2024", url="https://example.com/jones"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_x", "Smith 2023", url="https://example.com/smith"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert len(d.evidence_deltas) == 1
    assert d.evidence_deltas[0].direction == "removed"
    assert "Jones" in d.evidence_deltas[0].statement


def test_evidence_id_renumber_does_not_surface() -> None:
    """Codex M-16 v2 review regression: evidence_id is run-local
    sequential. Re-runs of the same retrieval may produce ev_001
    in one run and ev_017 in another for the same source. v2
    keys evidence by canonical-source handle (DOI / PMID /
    normalized URL / statement) so renumbering doesn't produce
    false add/remove deltas."""
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_001", "Smith 2023", url="https://example.com/smith"),
        _bib(2, "ev_002", "Jones 2024", url="https://example.com/jones"),
    ))
    # Same two sources, different run-local ev_ids.
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_017", "Jones 2024", url="https://example.com/jones"),
        _bib(2, "ev_018", "Smith 2023", url="https://example.com/smith"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.evidence_deltas == (), (
        "evidence_id renumber must not surface as a delta"
    )


def test_evidence_doi_collapses_url_variants() -> None:
    """Same DOI, different URL strings → same source → no delta."""
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_a", "Trial 2023 (doi 10.1056/NEJMoa2107931)",
             url="https://www.example.com/trial?utm_source=x"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_b", "Trial 2023 (doi 10.1056/NEJMoa2107931)",
             url="http://example.com/trial/"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.evidence_deltas == ()


def test_evidence_normalized_url_collapses_tracking_params() -> None:
    """Same URL with/without UTM params → same source → no delta."""
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_a", "Smith 2023",
             url="https://www.example.com/study/abc?utm_source=mail&utm_campaign=x"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_b", "Smith 2023",
             url="http://example.com/study/abc/"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.evidence_deltas == ()


def test_evidence_url_with_tracking_param_alongside_real_param() -> None:
    """Codex M-16 v2 review regression: v2 regex consumed
    `?utm_source=x` but left `&id=1` orphaned. v3 uses
    urllib.parse so `?utm_source=x&id=1` and `?id=1` normalize
    identically."""
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_a", "Smith 2023",
             url="https://example.com/path?utm_source=mail&id=1"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_b", "Smith 2023",
             url="https://example.com/path?id=1"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.evidence_deltas == (), (
        "tracking param removal must preserve real query params"
    )


def test_evidence_url_query_param_order_does_not_matter() -> None:
    """Param order should be canonicalized so `?a=1&b=2` and
    `?b=2&a=1` collapse to the same key."""
    ir_a = _make_minimal_ir(bibliography=(
        _bib(1, "ev_a", "Smith 2023",
             url="https://example.com/path?a=1&b=2"),
    ))
    ir_b = _make_minimal_ir(bibliography=(
        _bib(1, "ev_b", "Smith 2023",
             url="https://example.com/path?b=2&a=1"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.evidence_deltas == ()


# ---------------------------------------------------------------------------
# Contradiction deltas
# ---------------------------------------------------------------------------


def test_resolved_contradiction_surfaces_as_removed() -> None:
    ir_a = _make_minimal_ir(contradictions=(
        _cluster(1, "tirzepatide_efficacy", "endpoint_p_value"),
    ))
    ir_b = _make_minimal_ir(contradictions=())
    d = diff_runs(ir_a, ir_b)
    assert len(d.contradiction_deltas) == 1
    assert d.contradiction_deltas[0].direction == "removed"
    assert d.contradiction_deltas[0].subject == "tirzepatide_efficacy"


def test_new_contradiction_surfaces_as_added() -> None:
    ir_a = _make_minimal_ir(contradictions=())
    ir_b = _make_minimal_ir(contradictions=(
        _cluster(1, "tirzepatide_safety", "ae_rate"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert len(d.contradiction_deltas) == 1
    assert d.contradiction_deltas[0].direction == "added"


def test_contradiction_cluster_id_renumber_does_not_surface() -> None:
    """Codex M-16 invariant: cluster_id is per-run (re-runs
    re-number it). The stable handle is (subject, predicate)."""
    ir_a = _make_minimal_ir(contradictions=(
        _cluster(1, "x_efficacy", "primary_endpoint"),
        _cluster(2, "x_safety", "ae_rate"),
    ))
    # Same two clusters in B but with different cluster_ids.
    ir_b = _make_minimal_ir(contradictions=(
        _cluster(7, "x_safety", "ae_rate"),
        _cluster(8, "x_efficacy", "primary_endpoint"),
    ))
    d = diff_runs(ir_a, ir_b)
    assert d.contradiction_deltas == (), (
        "cluster_id renumber must not surface as a delta"
    )


# ---------------------------------------------------------------------------
# Tier mix shifts
# ---------------------------------------------------------------------------


def test_tier_shift_uses_real_v30_tier_keys() -> None:
    """Codex M-16 v2 review fix: real V30 manifests use T1..T7 +
    UNKNOWN, not tier1..tier4. v1 hardcoded the wrong keys and
    silently missed every tier shift on real data."""
    ir_a = _make_minimal_ir(tier_fractions={
        "T1": 0.50, "T2": 0.30, "T3": 0.10, "T4": 0.10,
    })
    ir_b = _make_minimal_ir(tier_fractions={
        "T1": 0.20, "T2": 0.30, "T3": 0.40, "T4": 0.10,
    })
    d = diff_runs(ir_a, ir_b)
    surfaced = {s.tier for s in d.tier_shifts}
    assert "T1" in surfaced
    assert "T3" in surfaced
    assert "T2" not in surfaced  # unchanged


def test_tier_shift_below_threshold_does_not_surface() -> None:
    ir_a = _make_minimal_ir(tier_fractions={
        "T1": 0.40, "T2": 0.30, "T3": 0.20, "T4": 0.10,
    })
    ir_b = _make_minimal_ir(tier_fractions={
        "T1": 0.42, "T2": 0.28, "T3": 0.20, "T4": 0.10,
    })
    # Default threshold 10pp; 2pp shift is below.
    d = diff_runs(ir_a, ir_b)
    assert d.tier_shifts == ()


def test_tier_shift_threshold_env_overridable(monkeypatch) -> None:
    monkeypatch.setenv("PG_RUN_DIFF_TIER_PP", "1.0")
    ir_a = _make_minimal_ir(tier_fractions={
        "T1": 0.40, "T2": 0.30, "T3": 0.20, "T4": 0.10,
    })
    ir_b = _make_minimal_ir(tier_fractions={
        "T1": 0.42, "T2": 0.28, "T3": 0.20, "T4": 0.10,
    })
    d = diff_runs(ir_a, ir_b)
    surfaced = {s.tier for s in d.tier_shifts}
    assert "T1" in surfaced
    assert "T2" in surfaced


def test_tier_shift_with_extended_keys() -> None:
    """V30 sometimes emits T5/T6/T7 + UNKNOWN. Diff must support
    arbitrary tier labels."""
    ir_a = _make_minimal_ir(tier_fractions={
        "T1": 0.30, "T5": 0.30, "T7": 0.30, "UNKNOWN": 0.10,
    })
    ir_b = _make_minimal_ir(tier_fractions={
        "T1": 0.30, "T5": 0.10, "T7": 0.50, "UNKNOWN": 0.10,
    })
    d = diff_runs(ir_a, ir_b)
    surfaced = {s.tier for s in d.tier_shifts}
    assert "T5" in surfaced
    assert "T7" in surfaced


# ---------------------------------------------------------------------------
# is_material
# ---------------------------------------------------------------------------


def test_is_material_false_when_no_deltas() -> None:
    d = RunDiff(a_run_id="a", b_run_id="b", slug="x")
    assert is_material(d) is False


def test_is_material_true_when_any_delta() -> None:
    d_with_claim = RunDiff(
        a_run_id="a", b_run_id="b", slug="x",
        claim_deltas=(ClaimDelta(
            direction="added", claim_id="c", section="s",
            text="t", is_verified=True,
        ),),
    )
    assert is_material(d_with_claim) is True


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


def test_diff_to_dict_round_trip() -> None:
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "claim a"),
    ])
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "claim a"),
        _sentence("findings:verified:1", "claim b"),
    ])
    d = diff_runs(ir_a, ir_b)
    j = diff_to_dict(d)
    assert isinstance(j, dict)
    assert j["slug"] == "x_drug_y_disease"
    assert len(j["claim_deltas"]) == 1
    assert j["claim_deltas"][0]["direction"] == "added"
    assert j["claim_deltas"][0]["claim_id"] == "findings:verified:1"


# ---------------------------------------------------------------------------
# Determinism — same input, same output
# ---------------------------------------------------------------------------


def test_run_diff_endpoint_route_order(tmp_path) -> None:
    """Codex M-16 v2 review regression: the /api/inspector/runs/
    diff endpoint MUST be declared before /api/inspector/runs/
    {slug}, otherwise FastAPI's path matching treats "diff" as a
    slug and 404s. v1 had this exact bug — the endpoint was
    unreachable. v2 moved it above."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.polaris_graph.audit_ir.inspector_router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    # Hit the /diff endpoint with two unknown slugs. Should
    # return 404 with detail starting "unknown run slug" — NOT
    # routed to /runs/{slug}=diff.
    resp = client.get(
        "/api/inspector/runs/diff?a_slug=does_not_exist_a&b_slug=does_not_exist_b"
    )
    # 404 with "unknown run slug: does_not_exist_a" → endpoint
    # reached. If route order is broken, we'd see "Unknown run
    # slug: diff" instead.
    assert resp.status_code == 404
    detail = resp.json().get("detail", "")
    assert "does_not_exist_a" in detail or "does_not_exist_b" in detail, (
        f"endpoint not reached; got detail={detail!r}"
    )
    assert "diff" not in detail or "does_not_exist" in detail


def test_diff_is_deterministic() -> None:
    ir_a = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "x"),
        _sentence("findings:verified:1", "y"),
    ])
    ir_b = _make_minimal_ir(sentences=[
        _sentence("findings:verified:0", "x"),
        _sentence("findings:verified:2", "z"),
    ])
    d1 = diff_runs(ir_a, ir_b)
    d2 = diff_runs(ir_a, ir_b)
    assert d1 == d2
