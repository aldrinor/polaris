"""M-D5 phase 2 v1 (Phase D): LLM-augmented ScopeEligibilityClassifier.

M-D5 phase 1 (`scope_classifier.py`, commit 13a4c21 + v6
460234a) shipped the `ScopeEligibilityClassifier` Protocol +
`confidence_gated_match` orchestration. Phase 2 ships the
**concrete LLM-augmented classifier** that fills that
Protocol slot.

Pattern mirrors M-D2 phase b (`auto_induction/llm_inductor.py`):
  - Pluggable LLM seam (`ScopeAffinityLLM` Protocol)
  - `MockScopeAffinityLLM` for deterministic unit tests
  - Prompt-injection defense via per-call random delimiters
  - Concrete `LLMScopeEligibilityClassifier` that implements
    `ScopeEligibilityClassifier` (phase 1 Protocol)

This unblocks M-D6 (cross-domain templates), which needs a
working classifier to route queries to domain adapters.

## What v1 ships

  - `ScopeAffinityLLM` Protocol — single-method seam
  - `LLMVerdict` dataclass — LLM's raw output
  - `MockScopeAffinityLLM` — deterministic keyword-based mock
  - `LLMScopeEligibilityClassifier` — implements phase 1's
    `ScopeEligibilityClassifier` Protocol; converts LLMVerdict
    into ScopeClassification

## Substrate boundary

Imports `scope_classifier` (phase 1 contracts) + stdlib only.
No OpenRouter coupling — production wiring uses M-D2 phase b's
existing OpenRouterClient infrastructure (deferred to v2).

See `docs/md5_phase2_threat_model.md` for boundaries.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Protocol

from src.polaris_graph.audit_ir.scope_classifier import (
    ScopeClassification,
    ScopeClassifierError,
    ScopeVerdict,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMScopeClassifierError(ScopeClassifierError):
    """Raised on contract violations specific to the LLM-
    augmented classifier (e.g. malformed LLMVerdict from the
    LLM seam, missing supported domains)."""


# ---------------------------------------------------------------------------
# LLM verdict + Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMVerdict:
    """Raw LLM output before adapting to ScopeClassification.

    `verdict` mirrors `ScopeVerdict` (in_scope / out_of_scope /
    uncertain) but as a string so the LLM seam doesn't need to
    import the phase 1 enum.
    `confidence`: classifier's own confidence in the verdict,
    in [0, 1]. Out-of-range values raise at adaptation time.
    `domain`: optional domain tag for routing (e.g. "clinical",
    "policy"). None when verdict != IN_SCOPE.
    `rationale`: human-readable explanation.
    """

    verdict: str
    confidence: float
    domain: str | None
    rationale: str


class ScopeAffinityLLM(Protocol):
    """Pluggable LLM seam for scope eligibility classification.

    Implementers MUST:
      - Return an `LLMVerdict` for any non-empty `question`.
      - `verdict` MUST be one of "in_scope" | "out_of_scope" |
        "uncertain" (case-insensitive at adapter time).
      - `confidence` MUST be in [0, 1].
      - Honor `supported_domains` — if the LLM judges the
        question to be in some domain NOT in the supported set,
        the verdict should be `out_of_scope` (with rationale
        explaining why), not `in_scope` with a non-supported
        domain.

    Implementers MAY:
      - Be non-deterministic (production LLM calls).
      - Make HTTP/network calls. Test impls (`MockScopeAffinityLLM`)
        are deterministic.

    Implementers MUST NOT:
      - Mutate global state.
      - Block indefinitely (caller wraps with timeout if
        backend doesn't enforce one).
    """

    def classify(
        self,
        question: str,
        supported_domains: tuple[str, ...],
    ) -> LLMVerdict:
        ...


# ---------------------------------------------------------------------------
# Mock LLM (deterministic; used by unit tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DomainProfile:
    """Keyword profile per domain — broader than M-20 router's
    strict keywords, simulating LLM semantic match."""

    domain: str
    keywords: tuple[str, ...]


# Default mock profiles. Callers can pass a custom list to
# MockScopeAffinityLLM via the `profiles` arg if their tests
# need different domains.
_DEFAULT_MOCK_PROFILES: tuple[_DomainProfile, ...] = (
    _DomainProfile(
        domain="clinical",
        keywords=(
            "tirzepatide", "mounjaro", "zepbound", "ozempic",
            "wegovy", "semaglutide", "liraglutide",
            "glp-1", "glp1", "incretin", "diabetes", "t2dm",
            "hba1c", "a1c", "glycemic", "weight loss",
            "trial", "phase 3", "rct", "clinical",
        ),
    ),
    _DomainProfile(
        domain="policy",
        keywords=(
            "medicare", "part d", "part b", "cms", "ira",
            "drug price", "drug pricing", "negotiation",
            "rebate", "formulary", "pbm",
            "policy", "regulation", "rule",
        ),
    ),
)


class MockScopeAffinityLLM:
    """Deterministic, rule-based LLM mock for offline unit tests.

    Same question → same LLMVerdict. Uses keyword-profile
    scoring against the supported_domains the caller passes.
    """

    def __init__(
        self,
        profiles: tuple[_DomainProfile, ...] = _DEFAULT_MOCK_PROFILES,
    ) -> None:
        self._profiles = profiles

    def classify(
        self,
        question: str,
        supported_domains: tuple[str, ...],
    ) -> LLMVerdict:
        if not question:
            return LLMVerdict(
                verdict="uncertain",
                confidence=0.0,
                domain=None,
                rationale="empty question",
            )

        ql = question.lower()
        candidates = {
            p.domain: p
            for p in self._profiles
            if p.domain in supported_domains
        }
        if not candidates:
            return LLMVerdict(
                verdict="out_of_scope",
                confidence=0.7,
                domain=None,
                rationale=(
                    "no supported domain matches mock profiles "
                    f"(supported={supported_domains})"
                ),
            )

        scored: list[tuple[str, int, float]] = []
        for domain, profile in candidates.items():
            count = sum(1 for kw in profile.keywords if kw in ql)
            ratio = (
                count / len(profile.keywords)
                if profile.keywords else 0.0
            )
            scored.append((domain, count, ratio))
        scored.sort(key=lambda x: x[1], reverse=True)
        best_domain, best_count, best_ratio = scored[0]
        second_count = scored[1][1] if len(scored) > 1 else 0
        margin = best_count - second_count

        if best_count == 0:
            return LLMVerdict(
                verdict="out_of_scope",
                confidence=0.6,
                domain=None,
                rationale="no domain keyword matched in question",
            )

        if margin < 1:
            # Multiple domains tie — uncertain.
            return LLMVerdict(
                verdict="uncertain",
                confidence=min(1.0, best_ratio),
                domain=None,
                rationale=(
                    f"margin {margin} too small "
                    f"(top: {best_domain}, count={best_count})"
                ),
            )

        # Confidence = clamp((count + 2*margin) / 10, 0, 1).
        # Same heuristic as M-D2 phase b's mock.
        confidence = min(1.0, (best_count + 2 * margin) / 10.0)
        return LLMVerdict(
            verdict="in_scope",
            confidence=confidence,
            domain=best_domain,
            rationale=(
                f"matched {best_count} {best_domain} keywords "
                f"with margin {margin} over second-best"
            ),
        )


# ---------------------------------------------------------------------------
# Prompt-injection defense (mirrors M-D2 phase b)
# ---------------------------------------------------------------------------


def build_question_block(question: str) -> tuple[str, str, str]:
    """Build a delimited question block resistant to prompt-
    injection breakout via embedded delimiters.

    Mirrors `auto_induction.llm_inductor._build_query_block`:
    per-call random 16-hex token, plus defense-in-depth
    sub-stripping of any token-shaped substring in the
    question body.

    Returns (open_delim, close_delim, escaped_question).
    """
    token = secrets.token_hex(16)
    open_delim = f"<<<question-{token}>>>"
    close_delim = f"<<<end-{token}>>>"
    escaped = re.sub(
        r"<<<end-?[a-f0-9]*>>>", "<<<escaped>>>", question,
    )
    return open_delim, close_delim, escaped


# ---------------------------------------------------------------------------
# LLM-augmented ScopeEligibilityClassifier
# ---------------------------------------------------------------------------


_VALID_VERDICT_STRINGS = frozenset({
    "in_scope", "out_of_scope", "uncertain",
})


@dataclass(frozen=True)
class LLMScopeEligibilityClassifierConfig:
    """Configuration for the LLM-augmented classifier.

    `supported_domains`: closed taxonomy of domains the system
    can route to. The LLM is told which are supported via the
    classify() arg; verdicts naming an UNSUPPORTED domain
    raise `LLMScopeClassifierError` at adapt time per the
    Protocol contract.

    `min_confidence_floor`: out-of-band confidence floor below
    which we force the verdict to UNCERTAIN regardless of the
    LLM's stated confidence. Default 0.0 (disabled — let the
    M-D5 phase 1 gate do the gating). Operators can tighten
    if they want this classifier to abstain more aggressively
    than the gate's threshold (PG_SCOPE_GATE_CONFIDENCE_THRESHOLD).
    """

    supported_domains: tuple[str, ...]
    min_confidence_floor: float = 0.0


class LLMScopeEligibilityClassifier:
    """Concrete `ScopeEligibilityClassifier` (phase 1 Protocol).

    Wraps a `ScopeAffinityLLM` (production: OpenRouter-backed;
    tests: `MockScopeAffinityLLM`) and adapts its `LLMVerdict`
    output to phase 1's `ScopeClassification` shape.

    Protocol compliance: `classify(question) ->
    ScopeClassification`. Phase 1's gate composes this
    classifier with the M-20 router via
    `confidence_gated_match`.
    """

    def __init__(
        self,
        llm: ScopeAffinityLLM,
        config: LLMScopeEligibilityClassifierConfig,
    ) -> None:
        if not isinstance(config, LLMScopeEligibilityClassifierConfig):
            raise LLMScopeClassifierError(
                f"config must be LLMScopeEligibilityClassifierConfig, "
                f"got {type(config).__name__}"
            )
        if not config.supported_domains:
            raise LLMScopeClassifierError(
                "supported_domains must be non-empty"
            )
        if not 0.0 <= config.min_confidence_floor <= 1.0:
            raise LLMScopeClassifierError(
                f"min_confidence_floor {config.min_confidence_floor} "
                "outside [0, 1]"
            )
        if llm is None or not hasattr(llm, "classify") or not callable(
            getattr(llm, "classify")
        ):
            raise LLMScopeClassifierError(
                "llm must implement the ScopeAffinityLLM Protocol "
                "(must have a callable `classify(question, "
                "supported_domains) -> LLMVerdict` method)"
            )
        self._llm = llm
        self._config = config

    def classify(self, question: str) -> ScopeClassification:
        if not isinstance(question, str):
            raise LLMScopeClassifierError(
                f"question must be str, got {type(question).__name__}"
            )

        # Phase 1 already short-circuits empty / visually-empty
        # questions before reaching the classifier (per
        # `confidence_gated_match`). Defensive check here for
        # callers invoking us directly outside the gate.
        if not question:
            return ScopeClassification(
                verdict=ScopeVerdict.UNCERTAIN,
                confidence=0.0,
                domain=None,
                rationale="empty question",
            )

        try:
            llm_out = self._llm.classify(
                question, self._config.supported_domains,
            )
        except LLMScopeClassifierError:
            # Our own contract errors propagate.
            raise
        except Exception as exc:  # noqa: BLE001
            # Any LLM-side failure becomes UNCERTAIN with a
            # rationale — the gate then routes to operator
            # review. Fail loudly via rationale, not via raise.
            return ScopeClassification(
                verdict=ScopeVerdict.UNCERTAIN,
                confidence=0.0,
                domain=None,
                rationale=f"LLM call failed: {exc!s}",
            )

        if not isinstance(llm_out, LLMVerdict):
            raise LLMScopeClassifierError(
                f"LLM returned {type(llm_out).__name__}, "
                "expected LLMVerdict"
            )

        # Validate verdict string.
        verdict_str = llm_out.verdict.lower().strip()
        if verdict_str not in _VALID_VERDICT_STRINGS:
            raise LLMScopeClassifierError(
                f"LLM returned verdict {llm_out.verdict!r}, "
                f"expected one of {sorted(_VALID_VERDICT_STRINGS)}"
            )

        # Validate confidence range.
        if not isinstance(llm_out.confidence, (int, float)):
            raise LLMScopeClassifierError(
                f"LLM confidence must be numeric, got "
                f"{type(llm_out.confidence).__name__}"
            )
        if not 0.0 <= float(llm_out.confidence) <= 1.0:
            raise LLMScopeClassifierError(
                f"LLM confidence {llm_out.confidence} outside [0, 1]"
            )

        # Validate domain (when in_scope).
        domain = llm_out.domain
        if verdict_str == "in_scope":
            if domain is None:
                raise LLMScopeClassifierError(
                    "LLM returned in_scope verdict but domain=None"
                )
            if domain not in self._config.supported_domains:
                raise LLMScopeClassifierError(
                    f"LLM returned in_scope domain {domain!r} "
                    f"not in supported_domains "
                    f"{self._config.supported_domains}"
                )
        else:
            # For out_of_scope / uncertain, domain MUST be None
            # (anything else is misleading for downstream routing).
            if domain is not None:
                raise LLMScopeClassifierError(
                    f"LLM returned non-IN_SCOPE verdict "
                    f"({verdict_str}) but domain={domain!r}; "
                    "domain must be None unless verdict is in_scope"
                )

        # Apply min_confidence_floor: low-confidence in_scope
        # verdicts are forced to UNCERTAIN so the gate can
        # send them to operator review.
        confidence = float(llm_out.confidence)
        if (
            verdict_str == "in_scope"
            and confidence < self._config.min_confidence_floor
        ):
            return ScopeClassification(
                verdict=ScopeVerdict.UNCERTAIN,
                confidence=confidence,
                domain=None,
                rationale=(
                    f"LLM verdict in_scope demoted to uncertain: "
                    f"confidence {confidence:.3f} < floor "
                    f"{self._config.min_confidence_floor:.3f}. "
                    f"Original rationale: {llm_out.rationale}"
                ),
            )

        # Map string back to ScopeVerdict enum.
        verdict_enum = {
            "in_scope": ScopeVerdict.IN_SCOPE,
            "out_of_scope": ScopeVerdict.OUT_OF_SCOPE,
            "uncertain": ScopeVerdict.UNCERTAIN,
        }[verdict_str]

        return ScopeClassification(
            verdict=verdict_enum,
            confidence=confidence,
            domain=domain,
            rationale=llm_out.rationale,
        )
