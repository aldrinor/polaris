"""Tests for src/polaris_graph/audit_ir/template_classifier.py (M-10)."""

from __future__ import annotations

import pytest

from src.polaris_graph.audit_ir.template_classifier import (
    DEFAULT_FLOOR_HIGH,
    DEFAULT_FLOOR_REVIEW,
    RouterConfig,
    RoutingCandidate,
    RoutingResult,
    RoutingVerdict,
    classify_query,
)


# ---------------------------------------------------------------------------
# Verdict semantics — the Risk #13 mitigation in action
# ---------------------------------------------------------------------------


def test_empty_query_returns_unsupported() -> None:
    """Empty / whitespace-only queries must not throw — they return
    UNSUPPORTED with a helpful rationale so the UI shows the same
    scope-page CTA in every off-scope branch."""
    for q in ["", "   ", "\n\t  "]:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.UNSUPPORTED
        assert r.template_id is None
        assert r.confidence == 0.0
        assert "empty" in r.rationale.lower() or "scope" in r.rationale.lower()


def test_obvious_off_scope_returns_unsupported() -> None:
    """A clearly off-scope question (weather, sports, etc.) must
    not silently route to v30_clinical — that's the Risk #13
    failure mode."""
    for q in [
        "What's the weather today?",
        "Who won the World Series last year?",
        "How do I bake sourdough bread?",
        "Best Italian restaurants in NYC",
    ]:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.UNSUPPORTED, (
            f"off-scope query {q!r} routed as {r.verdict}"
        )


def test_true_positive_clinical_query_routed() -> None:
    """High-confidence clinical drug-condition questions must route
    to v30_clinical."""
    queries = [
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
    ]
    for q in queries:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.ROUTED, (
            f"true-positive query {q!r} routed as {r.verdict} "
            f"(score {r.confidence:.2f}, rationale={r.rationale})"
        )
        assert r.template_id == "v30_clinical"
        assert r.confidence >= DEFAULT_FLOOR_HIGH


def test_medical_but_off_scope_goes_to_operator_review() -> None:
    """Off-scope-but-medical-sounding queries land in OPERATOR_REVIEW,
    not UNSUPPORTED. The operator can then decide whether to attempt
    the audit (since v30_clinical might still cover it after a
    reframe). Validates that medical framing alone isn't enough to
    auto-route."""
    r = classify_query("Treatment options for chronic pain")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"medical-but-off-scope routed as {r.verdict} "
        f"(rationale={r.rationale})"
    )
    assert r.template_id == "v30_clinical"


def test_keyword_only_query_does_not_route_high() -> None:
    """Queries with clinical keywords but no exemplar match (e.g.
    'FDA drug trial') must NOT auto-route — they're too generic to
    guarantee an in-scope audit. Operator review required."""
    r = classify_query("FDA drug trial")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"keyword-only query routed as {r.verdict} "
        f"(rationale={r.rationale})"
    )


# ---------------------------------------------------------------------------
# Score / verdict invariants
# ---------------------------------------------------------------------------


def test_confidence_bounded_in_unit_interval() -> None:
    """Confidence must always be in [0, 1] regardless of input."""
    queries = [
        "",
        "tirzepatide tirzepatide tirzepatide diabetes diabetes diabetes "
        "efficacy efficacy efficacy safety safety",
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "totally unrelated query about nothing in particular",
    ]
    for q in queries:
        r = classify_query(q)
        assert 0.0 <= r.confidence <= 1.0, (
            f"confidence {r.confidence} out of bounds for query {q!r}"
        )
        for c in r.candidates:
            assert 0.0 <= c.score <= 1.0


def test_routing_is_deterministic() -> None:
    """Same query → same verdict + same confidence on every call."""
    q = "What is the efficacy of tirzepatide for type 2 diabetes?"
    r1 = classify_query(q)
    r2 = classify_query(q)
    r3 = classify_query(q)
    assert r1.verdict == r2.verdict == r3.verdict
    assert r1.template_id == r2.template_id == r3.template_id
    assert r1.confidence == r2.confidence == r3.confidence


def test_candidates_sorted_by_score_descending() -> None:
    r = classify_query("Studies on metformin for diabetes")
    scores = [c.score for c in r.candidates]
    assert scores == sorted(scores, reverse=True)


def test_routed_verdict_has_template_id() -> None:
    """Sanity: ROUTED must include a template_id; UNSUPPORTED must not."""
    r_routed = classify_query(
        "What is the efficacy of tirzepatide for type 2 diabetes?"
    )
    assert r_routed.verdict == RoutingVerdict.ROUTED
    assert r_routed.template_id is not None

    r_unsup = classify_query("What's the weather?")
    assert r_unsup.verdict == RoutingVerdict.UNSUPPORTED
    assert r_unsup.template_id is None


def test_rationale_is_human_readable() -> None:
    r = classify_query("tirzepatide for diabetes")
    assert isinstance(r.rationale, str)
    assert len(r.rationale) >= 20
    # Score values should be in the rationale so operators can
    # debug routing decisions from logs.
    assert any(c.isdigit() for c in r.rationale)


# ---------------------------------------------------------------------------
# Threshold env-overrides (LAW VI)
# ---------------------------------------------------------------------------


def test_router_config_from_env_uses_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", raising=False)
    monkeypatch.delenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", raising=False)
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == DEFAULT_FLOOR_HIGH
    assert cfg.floor_review == DEFAULT_FLOOR_REVIEW


def test_router_config_from_env_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "0.80")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "0.20")
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == 0.80
    assert cfg.floor_review == 0.20


def test_router_config_clamps_invalid_floors(monkeypatch) -> None:
    """If review_floor >= high_floor, clamp review to high (so the
    review band collapses but never inverts)."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "0.50")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "0.90")
    cfg = RouterConfig.from_env()
    assert cfg.floor_review <= cfg.floor_high


def test_router_config_handles_garbage_env(monkeypatch) -> None:
    """Garbage env values fall back to defaults rather than crashing."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "not_a_float")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "also_garbage")
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == DEFAULT_FLOOR_HIGH
    assert cfg.floor_review == DEFAULT_FLOOR_REVIEW


def test_threshold_overrides_change_verdict(monkeypatch) -> None:
    """When floor_high is raised above a query's natural score,
    that query downgrades from ROUTED to OPERATOR_REVIEW."""
    q = "What is the efficacy of tirzepatide for type 2 diabetes?"
    natural = classify_query(q)
    assert natural.verdict == RoutingVerdict.ROUTED

    # Raise floor_high above the natural score.
    raised = RouterConfig(floor_high=natural.confidence + 0.05, floor_review=0.20)
    downgraded = classify_query(q, config=raised)
    assert downgraded.verdict == RoutingVerdict.OPERATOR_REVIEW
    assert downgraded.confidence == natural.confidence


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_query_with_only_punctuation_returns_unsupported() -> None:
    r = classify_query("???!!!")
    assert r.verdict == RoutingVerdict.UNSUPPORTED


def test_query_with_html_or_unicode_does_not_crash() -> None:
    """Defensive: garbage input doesn't crash the classifier."""
    weird = [
        "<script>alert('xss')</script>",
        "Café résumé naïve coöperate",
        "数据 关于 药物 治疗",
        "tirzepatide\x00diabetes",
    ]
    for q in weird:
        r = classify_query(q)
        assert isinstance(r, RoutingResult)
        assert isinstance(r.verdict, RoutingVerdict)


def test_candidates_for_unsupported_still_present() -> None:
    """Even when the verdict is UNSUPPORTED, candidates list is
    populated so the UI can show 'closest match' info if useful."""
    r = classify_query("What's the weather?")
    assert len(r.candidates) >= 1
    assert all(isinstance(c, RoutingCandidate) for c in r.candidates)
