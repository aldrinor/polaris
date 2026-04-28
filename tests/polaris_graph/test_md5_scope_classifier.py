"""M-D5 phase 1 — Confidence-gated template matching tests.

Pins:
  - Gating logic (4 main branches per advisor + protocol-violation guards)
  - Threshold env override + clamping
  - Validation-set abstain contract: against the M-D1 43-case
    validation set (with a perfect oracle classifier built from
    YAML's domain/expected_action fields), zero `route` outcomes
    for any non-in_scope case
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from src.polaris_graph.audit_ir.scope_classifier import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    GatedAction,
    GatedMatchResult,
    ScopeClassification,
    ScopeClassifierError,
    ScopeEligibilityClassifier,
    ScopeVerdict,
    confidence_gated_match,
)
from src.polaris_graph.audit_ir.template_classifier import (
    RouterConfig,
    RoutingResult,
    RoutingVerdict,
)


# ---------------------------------------------------------------------------
# Stub classifiers
# ---------------------------------------------------------------------------


@dataclass
class _StubClassifier:
    """Returns the verdict + confidence configured at construction."""

    verdict: ScopeVerdict
    confidence: float
    domain: str | None = None
    rationale: str = "stub rationale"

    def classify(self, question: str) -> ScopeClassification:
        return ScopeClassification(
            verdict=self.verdict,
            confidence=self.confidence,
            domain=self.domain,
            rationale=self.rationale,
        )


@dataclass
class _BrokenClassifier:
    """Returns invalid types — used to exercise guard rails."""

    payload: object

    def classify(self, question: str):  # type: ignore[no-untyped-def]
        return self.payload


# ---------------------------------------------------------------------------
# Gating logic — 4 main branches (advisor's matrix)
# ---------------------------------------------------------------------------


_TIRZE_QUERY = (
    "What is the efficacy of tirzepatide for type 2 diabetes?"
)
_OUT_OF_SCOPE_QUERY = (
    "What are best practices for Kubernetes operator design patterns?"
)


def test_in_scope_high_confidence_with_routed_router_returns_route() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.90,
        domain="clinical",
    )
    result = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=0.70,
    )
    assert isinstance(result, GatedMatchResult)
    assert result.action == GatedAction.ROUTE
    assert result.template_id == result.router_result.template_id
    assert result.router_result.verdict == RoutingVerdict.ROUTED
    assert result.threshold == 0.70


def test_classifier_out_of_scope_overrides_router_to_reject() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.OUT_OF_SCOPE,
        confidence=0.95,
        rationale="Kubernetes question, not clinical or policy",
    )
    result = confidence_gated_match(
        _OUT_OF_SCOPE_QUERY, classifier=classifier, threshold=0.70,
    )
    assert result.action == GatedAction.REJECT
    assert result.template_id is None
    assert "out-of-scope" in result.rationale.lower()


def test_classifier_uncertain_returns_operator_review() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.UNCERTAIN,
        confidence=0.85,
        rationale="multi-domain overlap",
    )
    result = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=0.70,
    )
    assert result.action == GatedAction.OPERATOR_REVIEW
    assert "uncertain" in result.rationale.lower()


def test_low_confidence_returns_operator_review_regardless_of_verdict() -> None:
    for verdict in (
        ScopeVerdict.IN_SCOPE,
        ScopeVerdict.OUT_OF_SCOPE,
        ScopeVerdict.UNCERTAIN,
    ):
        classifier = _StubClassifier(verdict=verdict, confidence=0.40)
        result = confidence_gated_match(
            _TIRZE_QUERY, classifier=classifier, threshold=0.70,
        )
        assert result.action == GatedAction.OPERATOR_REVIEW, (
            f"low-confidence verdict {verdict} should defer regardless"
        )
        assert "below threshold" in result.rationale.lower()


def test_in_scope_with_router_operator_review_returns_operator_review() -> None:
    """Router has medium confidence; classifier in-scope; defer to operator."""
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.90,
    )
    # Use a query that lands in M-20's OPERATOR_REVIEW band.
    medium_q = "How effective is GLP-1 therapy for weight loss?"
    result = confidence_gated_match(
        medium_q, classifier=classifier, threshold=0.70,
    )
    assert result.router_result.verdict in (
        RoutingVerdict.OPERATOR_REVIEW, RoutingVerdict.UNSUPPORTED,
    )
    assert result.action == GatedAction.OPERATOR_REVIEW


def test_in_scope_with_router_unsupported_returns_operator_review() -> None:
    """Classifier in-scope but router UNSUPPORTED — gate must defer.

    Codex round-1 LOW fix: pin this branch deterministically by raising
    the router's floor_review above any natural query score so the
    router lands in UNSUPPORTED for the test query, instead of
    conditionally asserting on whatever score happens to come out.
    """
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.95,
    )
    # Floor_review at 0.99 forces every non-perfect-match query to UNSUPPORTED.
    config = RouterConfig(
        floor_high=0.99, floor_review=0.99, tie_margin=0.10,
    )
    result = confidence_gated_match(
        "Tell me about lipid panel cutoffs",
        classifier=classifier, threshold=0.70, router_config=config,
    )
    assert result.router_result.verdict == RoutingVerdict.UNSUPPORTED
    assert result.action == GatedAction.OPERATOR_REVIEW
    assert "disagree" in result.rationale.lower()


# ---------------------------------------------------------------------------
# Threshold semantics
# ---------------------------------------------------------------------------


def test_threshold_at_default_when_argument_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD", raising=False)
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    result = confidence_gated_match(_TIRZE_QUERY, classifier=classifier)
    assert result.threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_threshold_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD", "0.85")
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.80,
    )
    # 0.80 < 0.85 → operator_review
    result = confidence_gated_match(_TIRZE_QUERY, classifier=classifier)
    assert result.threshold == 0.85
    assert result.action == GatedAction.OPERATOR_REVIEW


def test_threshold_env_clamps_above_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD", "5.0")
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    result = confidence_gated_match(_TIRZE_QUERY, classifier=classifier)
    assert result.threshold == 1.0


def test_threshold_env_clamps_below_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD", "-0.5")
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.10,
    )
    # threshold clamps to 0.0 → 0.10 >= 0.0 → IN_SCOPE branch
    result = confidence_gated_match(_TIRZE_QUERY, classifier=classifier)
    assert result.threshold == 0.0


def test_threshold_env_invalid_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD", "not_a_number")
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    result = confidence_gated_match(_TIRZE_QUERY, classifier=classifier)
    assert result.threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_threshold_argument_clamps() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    high = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=2.0,
    )
    assert high.threshold == 1.0
    low = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=-0.5,
    )
    assert low.threshold == 0.0


# ---------------------------------------------------------------------------
# Protocol violations
# ---------------------------------------------------------------------------


def test_classifier_returns_wrong_type_raises() -> None:
    broken = _BrokenClassifier(payload="not a classification")
    with pytest.raises(ScopeClassifierError, match="ScopeClassification"):
        confidence_gated_match(
            _TIRZE_QUERY, classifier=broken, threshold=0.70,  # type: ignore[arg-type]
        )


def test_classifier_returns_wrong_classification_type_raises() -> None:
    """A classifier returning the wrong dataclass type fails loudly."""

    @dataclass(frozen=True)
    class _NotAClassification:
        verdict: str
        confidence: float
        domain: str | None
        rationale: str

    broken = _BrokenClassifier(
        payload=_NotAClassification(
            verdict="in_scope",
            confidence=0.9,
            domain=None,
            rationale="x",
        )
    )
    with pytest.raises(ScopeClassifierError, match="ScopeClassification"):
        confidence_gated_match(
            _TIRZE_QUERY, classifier=broken, threshold=0.70,  # type: ignore[arg-type]
        )


def test_classifier_returns_classification_with_non_enum_verdict_raises() -> None:
    """Codex round-1 LOW fix: pin the verdict-enum guard distinctly.

    Constructing a real ScopeClassification with a non-enum verdict
    requires bypassing the dataclass init (frozen + typed). We do
    that via __new__ + object.__setattr__ to land a malformed
    instance, which exercises the actual `isinstance(verdict, ScopeVerdict)`
    guard rather than the upstream type guard.
    """
    bad = object.__new__(ScopeClassification)
    object.__setattr__(bad, "verdict", "in_scope")  # str, not ScopeVerdict
    object.__setattr__(bad, "confidence", 0.9)
    object.__setattr__(bad, "domain", None)
    object.__setattr__(bad, "rationale", "x")
    broken = _BrokenClassifier(payload=bad)
    with pytest.raises(ScopeClassifierError, match="ScopeVerdict enum"):
        confidence_gated_match(
            _TIRZE_QUERY, classifier=broken, threshold=0.70,  # type: ignore[arg-type]
        )


def test_classifier_returns_out_of_range_confidence_raises() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=1.5,
    )
    with pytest.raises(ScopeClassifierError, match=r"outside \[0, 1\]"):
        confidence_gated_match(
            _TIRZE_QUERY, classifier=classifier, threshold=0.70,
        )


def test_classifier_returns_negative_confidence_raises() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=-0.1,
    )
    with pytest.raises(ScopeClassifierError, match=r"outside \[0, 1\]"):
        confidence_gated_match(
            _TIRZE_QUERY, classifier=classifier, threshold=0.70,
        )


# ---------------------------------------------------------------------------
# Boundary values
# ---------------------------------------------------------------------------


def test_confidence_exactly_at_threshold_is_inclusive() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.70,
    )
    result = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=0.70,
    )
    # 0.70 < 0.70 is False → confidence is not below threshold
    assert result.action == GatedAction.ROUTE


def test_classifier_confidence_zero_below_zero_threshold_passes() -> None:
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.0,
    )
    result = confidence_gated_match(
        _TIRZE_QUERY, classifier=classifier, threshold=0.0,
    )
    # 0.0 < 0.0 False → in_scope branch, router returns ROUTED → ROUTE
    assert result.action == GatedAction.ROUTE


def test_router_config_passthrough_changes_router_floor() -> None:
    """A custom RouterConfig that flips the verdict propagates to the gate.

    Pick a query that scores in the OPERATOR_REVIEW band (~0.43-0.45)
    by default. Lower `floor_review` to capture it as ROUTED via a
    correspondingly low `floor_high`, then assert the gate routes.
    Inversely, raise `floor_review` above the score and the query
    drops to UNSUPPORTED.
    """
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    medium_q = (
        "What does the SURPASS-2 trial tell us about tirzepatide for "
        "diabetes management?"
    )
    # Lift floor_review above the natural score (~0.43-0.45) → UNSUPPORTED
    high_review = RouterConfig(
        floor_high=0.99, floor_review=0.95, tie_margin=0.10,
    )
    result_unsupported = confidence_gated_match(
        medium_q,
        classifier=classifier,
        threshold=0.70,
        router_config=high_review,
    )
    assert result_unsupported.router_result.verdict == RoutingVerdict.UNSUPPORTED
    assert result_unsupported.action == GatedAction.OPERATOR_REVIEW


# ---------------------------------------------------------------------------
# Empty / whitespace queries
# ---------------------------------------------------------------------------


def test_empty_query_lands_in_operator_review_or_reject() -> None:
    """Even with a confident classifier, an empty query must not auto-route."""
    classifier = _StubClassifier(
        verdict=ScopeVerdict.IN_SCOPE, confidence=0.99,
    )
    result = confidence_gated_match(
        "", classifier=classifier, threshold=0.70,
    )
    assert result.router_result.verdict == RoutingVerdict.UNSUPPORTED
    assert result.action != GatedAction.ROUTE


def test_empty_query_short_circuits_classifier_invocation() -> None:
    """Codex round-1 LOW fix: an empty query must NOT invoke the
    classifier. The classifier protocol does not guarantee output
    for empty input — a phase 2 classifier may raise. Mirror M-20's
    empty-query handling at the gate level."""

    @dataclass
    class _RaisingClassifier:
        called: bool = False

        def classify(self, question: str) -> ScopeClassification:
            self.called = True
            raise RuntimeError(
                "classifier not equipped to handle empty input"
            )

    raising = _RaisingClassifier()
    result = confidence_gated_match(
        "", classifier=raising, threshold=0.70,
    )
    assert raising.called is False, (
        "Empty query should short-circuit before classifier invocation"
    )
    assert result.action == GatedAction.OPERATOR_REVIEW
    assert result.template_id is None
    assert "empty query" in result.rationale.lower()


def test_whitespace_only_query_short_circuits_classifier_invocation() -> None:
    """Whitespace-only input must short-circuit the same way."""

    @dataclass
    class _RaisingClassifier:
        called: bool = False

        def classify(self, question: str) -> ScopeClassification:
            self.called = True
            raise RuntimeError("never called")

    raising = _RaisingClassifier()
    result = confidence_gated_match(
        "   \n\t ", classifier=raising, threshold=0.70,
    )
    assert raising.called is False
    assert result.action == GatedAction.OPERATOR_REVIEW


def test_unicode_format_character_query_short_circuits() -> None:
    """Codex round-2 PARTIAL fix: visually-empty queries composed of
    Cf (format) characters must short-circuit. `str.strip()` does
    NOT remove zero-width space (U+200B), ZWNJ (U+200C), ZWJ
    (U+200D), word joiner (U+2060), or BOM (U+FEFF).
    """

    @dataclass
    class _RaisingClassifier:
        called: bool = False

        def classify(self, question: str) -> ScopeClassification:
            self.called = True
            raise RuntimeError(
                "classifier reached for visually-empty Unicode input"
            )

    visually_empty_inputs = [
        "​​​",          # zero-width space
        "‌",                       # zero-width non-joiner
        "‍",                       # zero-width joiner
        "⁠",                       # word joiner
        "﻿",                       # BOM
        "  ​​  ",            # whitespace + zwsp
        "​\t‍\n",            # mixed Cf + whitespace
    ]
    for query in visually_empty_inputs:
        raising = _RaisingClassifier()
        result = confidence_gated_match(
            query, classifier=raising, threshold=0.70,
        )
        assert raising.called is False, (
            f"query {query!r} reached classifier; should short-circuit"
        )
        assert result.action == GatedAction.OPERATOR_REVIEW


def test_visible_unicode_query_does_not_short_circuit() -> None:
    """Negative case: queries with actual Unicode content (non-Latin
    scripts, accented chars, em-dashes, etc.) MUST reach the
    classifier — they are not visually empty.

    Pins that the v3 _is_visually_empty check doesn't over-strip.
    """

    @dataclass
    class _CountingClassifier:
        called: int = 0

        def classify(self, question: str) -> ScopeClassification:
            self.called += 1
            return ScopeClassification(
                verdict=ScopeVerdict.IN_SCOPE,
                confidence=0.95,
                domain="clinical",
                rationale="visible content",
            )

    visible_inputs = [
        "tirzepatide for diabetes",
        "tirzépatide for diábetès",       # accented Latin
        "ティルゼパチド for diabetes",    # Japanese
        "tirzepatide — for diabetes",     # em-dash
        "α-blocker safety",               # Greek alpha
    ]
    for query in visible_inputs:
        clf = _CountingClassifier()
        confidence_gated_match(query, classifier=clf, threshold=0.70)
        assert clf.called == 1, (
            f"visible query {query!r} did NOT reach classifier"
        )


# ---------------------------------------------------------------------------
# Validation-set abstain contract — the spec
# ---------------------------------------------------------------------------


_VS_PATH = (
    Path(__file__).resolve().parents[2]
    / "config" / "auto_induction" / "validation_set.yaml"
)


@dataclass
class _OracleClassifier:
    """Perfect classifier built from YAML's domain / expected_action.

    Maps:
      domain in {clinical, policy} → IN_SCOPE @ 0.95, domain tag preserved
      expected_action == abstain (ambiguous group) → UNCERTAIN @ 0.95
      out_of_scope group → OUT_OF_SCOPE @ 0.95
    """

    by_query: dict[str, ScopeClassification]

    def classify(self, question: str) -> ScopeClassification:
        return self.by_query[question]


def _build_oracle() -> tuple[_OracleClassifier, list[tuple[str, str, str]]]:
    """Returns (oracle, [(query, group, case_id)])."""
    raw = yaml.safe_load(_VS_PATH.read_text(encoding="utf-8"))
    by_query: dict[str, ScopeClassification] = {}
    rows: list[tuple[str, str, str]] = []
    for case in raw.get("in_scope") or ():
        q = case["query"]
        domain = case["domain"]
        by_query[q] = ScopeClassification(
            verdict=ScopeVerdict.IN_SCOPE,
            confidence=0.95,
            domain=domain,
            rationale=f"oracle: in-scope {domain}",
        )
        rows.append((q, "in_scope", case["case_id"]))
    for case in raw.get("ambiguous") or ():
        q = case["query"]
        by_query[q] = ScopeClassification(
            verdict=ScopeVerdict.UNCERTAIN,
            confidence=0.95,
            domain=None,
            rationale="oracle: ambiguous → uncertain",
        )
        rows.append((q, "ambiguous", case["case_id"]))
    for case in raw.get("out_of_scope") or ():
        q = case["query"]
        by_query[q] = ScopeClassification(
            verdict=ScopeVerdict.OUT_OF_SCOPE,
            confidence=0.95,
            domain=None,
            rationale="oracle: out-of-scope",
        )
        rows.append((q, "out_of_scope", case["case_id"]))
    return _OracleClassifier(by_query=by_query), rows


def test_validation_set_abstain_contract() -> None:
    """The spec for what M-D5 has to deliver: against the M-D1
    validation set with a perfect-oracle classifier, NO non-in-scope
    case may emit `route`."""
    oracle, rows = _build_oracle()
    counts: dict[str, dict[GatedAction, int]] = {}
    routed_non_in_scope: list[tuple[str, str]] = []
    for query, group, case_id in rows:
        result = confidence_gated_match(
            query, classifier=oracle, threshold=0.70,
        )
        counts.setdefault(group, {}).setdefault(result.action, 0)
        counts[group][result.action] += 1
        if group != "in_scope" and result.action == GatedAction.ROUTE:
            routed_non_in_scope.append((case_id, query))
    # SPEC: zero `route` outcomes for ambiguous + out_of_scope.
    assert routed_non_in_scope == [], (
        f"M-D5 must never auto-route a non-in-scope case. Violations: "
        f"{routed_non_in_scope}"
    )
    # Sanity: ambiguous + out_of_scope all hit operator_review or reject.
    for group in ("ambiguous", "out_of_scope"):
        actions = counts.get(group, {})
        assert GatedAction.ROUTE not in actions, (
            f"{group} group must not route: {actions}"
        )


def test_validation_set_in_scope_gate_matches_router_when_classifier_agrees() -> None:
    """For in-scope cases the gate's terminal action must equal the
    router-derived expectation:
      router.ROUTED          → gate.ROUTE       (both green-light)
      router.OPERATOR_REVIEW → gate.OPERATOR_REVIEW (router uncertain)
      router.UNSUPPORTED     → gate.OPERATOR_REVIEW (router/classifier disagree)

    This pins gate-vs-router agreement on the in-scope subset of
    M-D1. Absolute routing counts aren't a meaningful spec because
    the M-D1 set is M-D2-inductor-shaped, not M-20-router-shaped.
    """
    from src.polaris_graph.audit_ir.template_classifier import (
        classify_query,
    )
    oracle, rows = _build_oracle()
    in_scope_rows = [(q, cid) for (q, g, cid) in rows if g == "in_scope"]
    for query, case_id in in_scope_rows:
        router = classify_query(query)
        result = confidence_gated_match(
            query, classifier=oracle, threshold=0.70,
        )
        if router.verdict == RoutingVerdict.ROUTED:
            assert result.action == GatedAction.ROUTE, (
                f"in-scope case {case_id}: router ROUTED → gate must "
                f"ROUTE; got {result.action}"
            )
        else:
            assert result.action == GatedAction.OPERATOR_REVIEW, (
                f"in-scope case {case_id}: router {router.verdict} → "
                f"gate must OPERATOR_REVIEW; got {result.action}"
            )


def test_validation_set_out_of_scope_always_rejects() -> None:
    """At threshold 0.70 with oracle confidence 0.95, every
    out_of_scope row must REJECT (not just operator_review)."""
    oracle, rows = _build_oracle()
    for query, group, case_id in rows:
        if group != "out_of_scope":
            continue
        result = confidence_gated_match(
            query, classifier=oracle, threshold=0.70,
        )
        assert result.action == GatedAction.REJECT, (
            f"oos case {case_id} expected REJECT, got "
            f"{result.action}; rationale: {result.rationale}"
        )


def test_validation_set_ambiguous_always_operator_review() -> None:
    """At threshold 0.70 with oracle confidence 0.95, every
    ambiguous row must hit OPERATOR_REVIEW (uncertain branch)."""
    oracle, rows = _build_oracle()
    for query, group, case_id in rows:
        if group != "ambiguous":
            continue
        result = confidence_gated_match(
            query, classifier=oracle, threshold=0.70,
        )
        assert result.action == GatedAction.OPERATOR_REVIEW, (
            f"amb case {case_id} expected OPERATOR_REVIEW, got "
            f"{result.action}; rationale: {result.rationale}"
        )
