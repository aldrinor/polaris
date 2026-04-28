"""M-D5 (Phase D) — Confidence-gated template matching.

Sits **above** M-20 (`template_classifier.classify_query`). M-20
routes by lexical match (curated keyword catalog + Jaccard); M-D5
adds a pluggable second-opinion `ScopeEligibilityClassifier`
that judges whether the question is in scope for the system at
all, regardless of which curated template lexically wins.

Why a second opinion: M-20's keyword/Jaccard scoring is fast and
deterministic but can rule a question routed-eligible on shallow
overlap. M-D5 lets the operator (or, in phase 2, an LLM-augmented
classifier) overrule that with a higher-confidence judgment.

Phase 1 ships **gating logic + protocol only**:
  - `ScopeVerdict` enum: `in_scope | out_of_scope | uncertain`
  - `ScopeEligibilityClassifier` Protocol — pluggable like
    `FreshnessDetector` (M-D10) and `TemplateAffinityClassifier`
    (M-D2 phase b)
  - `confidence_gated_match()` — wraps M-20 router, applies
    classifier verdict + confidence threshold gate, returns
    a single combined `GatedMatchResult`

Phase 2 (deferred):
  - Concrete classifier implementations (regex-anchor fallback,
    LLM-augmented classifier reusing M-D2 phase b infrastructure)
  - Domain adapters paired with M-D6 cross-domain templates
  - Optional `gate_decisions` telemetry table (deferred until
    M-D3 telemetry surfaces the need)

## Gate logic (per advisor)

```
if classifier.confidence < threshold:    → operator_review (classifier uncertain)
if classifier.verdict == out_of_scope:   → reject (classifier overrides router)
if classifier.verdict == uncertain:      → operator_review (classifier flagged uncertain)
if classifier.verdict == in_scope:
    match router.verdict:
        ROUTED            → route
        OPERATOR_REVIEW   → operator_review (router uncertain)
        UNSUPPORTED       → operator_review (router/classifier disagree)
```

The threshold gates the **classifier's confidence in its own
verdict**, not the router's score. M-20 already has its own
score thresholds (`floor_high`, `floor_review`); duplicating
that check here would either be redundant or silently raise
M-20's gates. Default 0.70 is stricter than M-20's 0.55 floor —
the classifier is the *second* opinion, so we require higher
confidence before acting on its verdict.

See `docs/md5_phase1_threat_model.md` for boundaries.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.polaris_graph.audit_ir.template_classifier import (
    RouterConfig,
    RoutingResult,
    RoutingVerdict,
    classify_query,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScopeClassifierError(Exception):
    """Raised on protocol-contract violations or invalid configuration."""


# ---------------------------------------------------------------------------
# Threshold defaults (env-overridable, per LAW VI)
# ---------------------------------------------------------------------------


# Default 0.70 — stricter than M-20's 0.55 floor_high. Rationale: M-D5
# acts as a second opinion above M-20, so we require higher confidence
# before taking the classifier's verdict at face value. A classifier
# emitting a verdict at 0.50 confidence is not a strong-enough signal
# to override M-20; surface to operator.
DEFAULT_CONFIDENCE_THRESHOLD = 0.70


def _read_threshold_from_env() -> float:
    raw = os.environ.get("PG_SCOPE_GATE_CONFIDENCE_THRESHOLD")
    if raw is None or raw == "":
        return DEFAULT_CONFIDENCE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CONFIDENCE_THRESHOLD
    return max(0.0, min(1.0, value))


def _is_visually_empty(text: str) -> bool:
    """Codex round-2 PARTIAL fix: detect visually-empty input
    including Unicode format characters that `str.strip()` misses.

    Python's `str.strip()` only removes characters where
    `str.isspace()` returns True (Zs/Zl/Zp/whitespace controls).
    It does NOT remove Cf (format) characters: `​` (zero-
    width space), `‌` (ZWNJ), `‍` (ZWJ), `⁠`
    (word joiner), `﻿` (BOM). These render as nothing but
    leave a non-empty string after strip — letting a query like
    `"​​"` bypass the v2 short-circuit and reach the
    classifier.

    Treat any string composed entirely of whitespace + Cf
    + Cc (control) + invisible characters as visually empty.
    """
    if not text:
        return True
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        # Cf = Format, Cc = Control, Cn = Unassigned, Co = Private Use.
        # Any of these are non-rendering / non-content.
        if category in ("Cf", "Cc", "Cn", "Co"):
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Verdict + classification dataclasses
# ---------------------------------------------------------------------------


class ScopeVerdict(str, Enum):
    """Closed taxonomy of scope-eligibility judgments.

    `in_scope`: the classifier is confident the question falls within
       the supported audit domains.
    `out_of_scope`: the classifier is confident the question is
       outside the supported domains. Overrides router routing.
    `uncertain`: the classifier itself cannot decide (multi-domain
       overlap, ambiguous intent). Distinct from low-confidence:
       a classifier may be highly confident the question IS uncertain
       (e.g. a confidently-multi-domain query). The gate treats it
       the same as low confidence — operator review — but the
       rationale differs.
    """

    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ScopeClassification:
    """One classifier verdict for one question.

    `verdict`: closed enum (see `ScopeVerdict`).
    `confidence`: classifier's confidence in the returned verdict,
       in [0, 1]. Subject to per-classifier calibration — see
       phase 1 threat model boundary 2.
    `domain`: optional metadata tag (e.g. "clinical", "policy",
       "drug_class") so callers can route in-scope questions to the
       right domain adapter. Phase 2 + M-D6 will use this.
       NOT part of the verdict semantics; never gates routing.
    `rationale`: human-readable explanation surfaced to operators
       on the review queue.
    """

    verdict: ScopeVerdict
    confidence: float
    domain: str | None
    rationale: str


# ---------------------------------------------------------------------------
# Protocol (caller injects)
# ---------------------------------------------------------------------------


class ScopeEligibilityClassifier(Protocol):
    """Pluggable scope-eligibility classifier.

    Phase 1 ships the protocol only — concrete implementations land
    in phase 2 (alongside M-D6 cross-domain adapters and the M-D2
    phase b LLM-augmented variant).

    Implementers MUST:
      - Return a `ScopeClassification` for any non-empty `question`.
      - Confidence MUST be in [0, 1]. Out-of-range values raise
        `ScopeClassifierError` at gate time.
      - Be deterministic for unit-test purposes (production LLM-
        augmented impls may relax this; document the threshold).

    Implementers MUST NOT:
      - Mutate global state.
      - Call the M-20 router themselves (the gate composes them).
    """

    def classify(self, question: str) -> ScopeClassification:
        ...


# ---------------------------------------------------------------------------
# Gated-match action + result
# ---------------------------------------------------------------------------


class GatedAction(str, Enum):
    """Terminal action emitted by `confidence_gated_match`.

    `route`: classifier and router both green-light. Caller may
       enqueue the audit using `result.template_id`.
    `operator_review`: classifier or router (or both) hesitates.
       Caller MUST surface to operator review queue with the
       rationale; operator can override.
    `reject`: classifier confidently flagged out-of-scope. Caller
       MUST NOT auto-enqueue; rationale should suggest scope page.
       Phase 1 boundary: this is a SOFT reject (operator can still
       force-enqueue via M-23 review queue) — the gate is fail-
       closed, not a hard block.
    """

    ROUTE = "route"
    OPERATOR_REVIEW = "operator_review"
    REJECT = "reject"


@dataclass(frozen=True)
class GatedMatchResult:
    """Combined verdict from `confidence_gated_match`.

    `action`: terminal gate action (see `GatedAction`).
    `template_id`: top-1 router template if the gate is willing to
       point at one (route or operator_review). None for reject.
    `router_result`: full M-20 result preserved for telemetry +
       operator-review UI rendering (drug hits, candidates, etc.).
    `classification`: full classifier output preserved for the same
       reasons.
    `threshold`: the confidence threshold actually applied (after
       env override + clamping). Recorded for debuggability.
    `rationale`: combined operator-readable explanation referencing
       both router and classifier.
    """

    action: GatedAction
    template_id: str | None
    router_result: RoutingResult
    classification: ScopeClassification
    threshold: float
    rationale: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def confidence_gated_match(
    question: str,
    *,
    classifier: ScopeEligibilityClassifier,
    threshold: float | None = None,
    router_config: RouterConfig | None = None,
) -> GatedMatchResult:
    """Run M-20 router and classifier; return combined gated verdict.

    Args:
      question: free-text user query.
      classifier: caller-injected scope-eligibility classifier.
      threshold: classifier-confidence floor in [0, 1]. If None,
        reads `PG_SCOPE_GATE_CONFIDENCE_THRESHOLD` (default 0.70).
        Out-of-range values clamp to [0, 1] (matching the M-20
        env-config pattern).
      router_config: optional override for M-20 router thresholds.
        If None, M-20 reads its own env vars.

    Returns:
      `GatedMatchResult` with terminal `action`, surfaced template
      (when applicable), and combined rationale.

    Raises:
      ScopeClassifierError: if the classifier returns a confidence
        outside [0, 1] or a verdict not in `ScopeVerdict`. These
        are protocol violations — fail loudly per LAW II.
    """
    if threshold is None:
        applied_threshold = _read_threshold_from_env()
    else:
        applied_threshold = max(0.0, min(1.0, float(threshold)))

    router_result = classify_query(question, config=router_config)

    # Codex round-1 LOW fix (v2): short-circuit on empty/whitespace
    # input before invoking the classifier. The classifier protocol
    # does NOT guarantee output for empty questions, and a phase 2
    # classifier may legitimately raise on empty input. M-20 router
    # already returns `UNSUPPORTED` here with a useful rationale —
    # mirror that into a gated `operator_review` so the empty-query
    # contract holds end-to-end.
    #
    # Codex round-2 PARTIAL fix (v3): use `_is_visually_empty` instead
    # of `str.strip()`. `strip()` doesn't remove Cf (zero-width space,
    # ZWNJ, BOM, word joiner) or Cc (control) characters, so a query
    # like `"​​"` (3× zero-width space) was reaching the
    # classifier despite being visually empty.
    if _is_visually_empty(question):
        sentinel = ScopeClassification(
            verdict=ScopeVerdict.UNCERTAIN,
            confidence=0.0,
            domain=None,
            rationale=(
                "Empty query — classifier not invoked; "
                "see scope page for supported question shapes."
            ),
        )
        return GatedMatchResult(
            action=GatedAction.OPERATOR_REVIEW,
            template_id=None,
            router_result=router_result,
            classification=sentinel,
            threshold=applied_threshold,
            rationale=(
                "Empty query short-circuit: classifier not invoked. "
                f"Router rationale: {router_result.rationale}"
            ),
        )

    classification = classifier.classify(question)

    if not isinstance(classification, ScopeClassification):
        raise ScopeClassifierError(
            f"classifier returned {type(classification).__name__}; "
            f"must return ScopeClassification"
        )
    if not isinstance(classification.verdict, ScopeVerdict):
        raise ScopeClassifierError(
            f"classifier verdict {classification.verdict!r} not in "
            f"ScopeVerdict enum"
        )
    if not 0.0 <= classification.confidence <= 1.0:
        raise ScopeClassifierError(
            f"classifier confidence {classification.confidence} "
            f"outside [0, 1]"
        )

    if classification.confidence < applied_threshold:
        action = GatedAction.OPERATOR_REVIEW
        rationale = (
            f"Classifier confidence {classification.confidence:.2f} "
            f"below threshold {applied_threshold:.2f}; defer to "
            f"operator review. Classifier rationale: "
            f"{classification.rationale}"
        )
        return GatedMatchResult(
            action=action,
            template_id=router_result.template_id,
            router_result=router_result,
            classification=classification,
            threshold=applied_threshold,
            rationale=rationale,
        )

    if classification.verdict == ScopeVerdict.OUT_OF_SCOPE:
        rationale = (
            f"Classifier flagged out-of-scope at confidence "
            f"{classification.confidence:.2f}: "
            f"{classification.rationale}. "
            f"Soft reject — operator may force-enqueue via review "
            f"queue if classifier is wrong."
        )
        return GatedMatchResult(
            action=GatedAction.REJECT,
            template_id=None,
            router_result=router_result,
            classification=classification,
            threshold=applied_threshold,
            rationale=rationale,
        )

    if classification.verdict == ScopeVerdict.UNCERTAIN:
        rationale = (
            f"Classifier flagged uncertain at confidence "
            f"{classification.confidence:.2f}: "
            f"{classification.rationale}. "
            f"Operator must scope before audit launches."
        )
        return GatedMatchResult(
            action=GatedAction.OPERATOR_REVIEW,
            template_id=router_result.template_id,
            router_result=router_result,
            classification=classification,
            threshold=applied_threshold,
            rationale=rationale,
        )

    if router_result.verdict == RoutingVerdict.ROUTED:
        rationale = (
            f"Classifier in-scope (confidence "
            f"{classification.confidence:.2f}) and router routed "
            f"'{router_result.template_id}' "
            f"(score {router_result.confidence:.2f}). Auto-enqueue eligible."
        )
        return GatedMatchResult(
            action=GatedAction.ROUTE,
            template_id=router_result.template_id,
            router_result=router_result,
            classification=classification,
            threshold=applied_threshold,
            rationale=rationale,
        )

    if router_result.verdict == RoutingVerdict.OPERATOR_REVIEW:
        rationale = (
            f"Classifier in-scope (confidence "
            f"{classification.confidence:.2f}) but router uncertain: "
            f"{router_result.rationale}"
        )
        return GatedMatchResult(
            action=GatedAction.OPERATOR_REVIEW,
            template_id=router_result.template_id,
            router_result=router_result,
            classification=classification,
            threshold=applied_threshold,
            rationale=rationale,
        )

    rationale = (
        f"Classifier in-scope (confidence "
        f"{classification.confidence:.2f}) but router did not match "
        f"any supported template: {router_result.rationale} "
        f"Surface to operator — classifier and router disagree."
    )
    return GatedMatchResult(
        action=GatedAction.OPERATOR_REVIEW,
        template_id=None,
        router_result=router_result,
        classification=classification,
        threshold=applied_threshold,
        rationale=rationale,
    )


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "GatedAction",
    "GatedMatchResult",
    "ScopeClassification",
    "ScopeClassifierError",
    "ScopeEligibilityClassifier",
    "ScopeVerdict",
    "confidence_gated_match",
]
