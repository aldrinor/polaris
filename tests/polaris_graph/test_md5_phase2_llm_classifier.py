"""M-D5 phase 2 v1 — LLM-augmented ScopeEligibilityClassifier tests.

Pins:
  - LLMScopeEligibilityClassifier protocol compliance
  - LLMVerdict adaptation to ScopeClassification
  - MockScopeAffinityLLM determinism
  - Verdict string validation (in_scope | out_of_scope | uncertain)
  - Confidence range validation
  - Domain validation (must be in supported_domains, None for non-IN_SCOPE)
  - min_confidence_floor demotion to UNCERTAIN
  - LLM-side exception → UNCERTAIN with rationale (fail loud via rationale)
  - Empty question short-circuit
  - Prompt-injection delimiter randomness
  - Contract validation
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.polaris_graph.audit_ir.scope_classifier import (
    ScopeClassification,
    ScopeVerdict,
)
from src.polaris_graph.audit_ir.scope_classifier_llm import (
    LLMScopeClassifierError,
    LLMScopeEligibilityClassifier,
    LLMScopeEligibilityClassifierConfig,
    LLMVerdict,
    MockScopeAffinityLLM,
    ScopeAffinityLLM,
    build_question_block,
)


# ---------------------------------------------------------------------------
# Fixtures: configs
# ---------------------------------------------------------------------------


def _config(
    *,
    supported_domains: tuple[str, ...] = ("clinical", "policy"),
    min_confidence_floor: float = 0.0,
) -> LLMScopeEligibilityClassifierConfig:
    return LLMScopeEligibilityClassifierConfig(
        supported_domains=supported_domains,
        min_confidence_floor=min_confidence_floor,
    )


# ---------------------------------------------------------------------------
# Stub LLMs
# ---------------------------------------------------------------------------


@dataclass
class _FixedLLM:
    """Returns a fixed LLMVerdict regardless of input."""

    verdict: LLMVerdict

    def classify(
        self, question: str, supported_domains: tuple[str, ...],
    ) -> LLMVerdict:
        return self.verdict


@dataclass
class _RaisingLLM:
    exc: Exception

    def classify(
        self, question: str, supported_domains: tuple[str, ...],
    ) -> LLMVerdict:
        raise self.exc


@dataclass
class _BadShapeLLM:
    """Returns the wrong type."""

    payload: object

    def classify(
        self, question: str, supported_domains: tuple[str, ...],
    ):
        return self.payload


# ---------------------------------------------------------------------------
# Construction / contract
# ---------------------------------------------------------------------------


def test_config_must_be_dataclass_instance() -> None:
    llm = MockScopeAffinityLLM()
    with pytest.raises(LLMScopeClassifierError, match="config must"):
        LLMScopeEligibilityClassifier(llm, "not a config")  # type: ignore[arg-type]


def test_supported_domains_must_be_non_empty() -> None:
    llm = MockScopeAffinityLLM()
    with pytest.raises(LLMScopeClassifierError, match="supported_domains"):
        LLMScopeEligibilityClassifier(
            llm, _config(supported_domains=()),
        )


def test_min_confidence_floor_must_be_unit_interval() -> None:
    llm = MockScopeAffinityLLM()
    with pytest.raises(LLMScopeClassifierError, match="min_confidence_floor"):
        LLMScopeEligibilityClassifier(
            llm, _config(min_confidence_floor=1.5),
        )
    with pytest.raises(LLMScopeClassifierError, match="min_confidence_floor"):
        LLMScopeEligibilityClassifier(
            llm, _config(min_confidence_floor=-0.1),
        )


def test_llm_must_implement_protocol() -> None:
    @dataclass
    class _NotAnLLM:
        pass

    with pytest.raises(LLMScopeClassifierError, match="ScopeAffinityLLM"):
        LLMScopeEligibilityClassifier(
            _NotAnLLM(), _config(),  # type: ignore[arg-type]
        )


def test_llm_with_non_callable_classify_raises() -> None:
    @dataclass
    class _BadLLM:
        classify: str = "not callable"

    with pytest.raises(LLMScopeClassifierError, match="callable"):
        LLMScopeEligibilityClassifier(
            _BadLLM(), _config(),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# classify() input validation
# ---------------------------------------------------------------------------


def test_non_string_question_raises() -> None:
    classifier = LLMScopeEligibilityClassifier(
        MockScopeAffinityLLM(), _config(),
    )
    with pytest.raises(LLMScopeClassifierError, match="question must be str"):
        classifier.classify(123)  # type: ignore[arg-type]


def test_empty_question_short_circuits_to_uncertain() -> None:
    classifier = LLMScopeEligibilityClassifier(
        MockScopeAffinityLLM(), _config(),
    )
    result = classifier.classify("")
    assert result.verdict == ScopeVerdict.UNCERTAIN
    assert result.confidence == 0.0
    assert result.domain is None
    assert "empty" in result.rationale.lower()


def test_visually_empty_question_short_circuits_via_direct_call() -> None:
    """Codex round-2 MEDIUM fix (v3): direct
    LLMScopeEligibilityClassifier.classify() must short-circuit
    visually-empty questions (zero-width spaces, combining
    marks, Hangul fillers) the same way phase 1's gate does
    via `_is_visually_empty`. v2 only checked `if not question`,
    missing inputs like `"​​"` that reached the LLM."""

    @dataclass
    class _CountingLLM:
        called: int = 0

        def classify(self, question, supported_domains):
            self.called += 1
            return LLMVerdict(
                verdict="out_of_scope",
                confidence=0.9,
                domain=None,
                rationale="should not be reached",
            )

    visually_empty_inputs = [
        "​​",        # zero-width spaces (Cf)
        "‌‍",        # ZWNJ + ZWJ (Cf)
        "   \t\n",      # whitespace
        "͏",         # CGJ (Mn) — v6 phase 1 boundary
        "ᅟ",         # Hangul CHOSEONG FILLER (Lo)
    ]
    for q in visually_empty_inputs:
        llm = _CountingLLM()
        classifier = LLMScopeEligibilityClassifier(llm, _config())
        result = classifier.classify(q)
        assert result.verdict == ScopeVerdict.UNCERTAIN
        assert result.domain is None
        assert llm.called == 0, (
            f"input {q!r} reached the LLM; should short-circuit"
        )


# ---------------------------------------------------------------------------
# Verdict adaptation
# ---------------------------------------------------------------------------


def test_in_scope_verdict_adapts_correctly() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope",
        confidence=0.9,
        domain="clinical",
        rationale="strong clinical match",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    result = classifier.classify("tirzepatide hba1c reduction")
    assert result.verdict == ScopeVerdict.IN_SCOPE
    assert result.confidence == pytest.approx(0.9)
    assert result.domain == "clinical"
    assert result.rationale == "strong clinical match"


def test_out_of_scope_verdict_adapts() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="out_of_scope",
        confidence=0.85,
        domain=None,
        rationale="cooking recipe",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    result = classifier.classify("how do I make pasta")
    assert result.verdict == ScopeVerdict.OUT_OF_SCOPE
    assert result.domain is None


def test_uncertain_verdict_adapts() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="uncertain",
        confidence=0.4,
        domain=None,
        rationale="ambiguous query",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    result = classifier.classify("medicine and policy")
    assert result.verdict == ScopeVerdict.UNCERTAIN
    assert result.domain is None


def test_verdict_string_case_insensitive() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="IN_SCOPE",  # uppercase
        confidence=0.8,
        domain="clinical",
        rationale="test",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    result = classifier.classify("tirzepatide")
    assert result.verdict == ScopeVerdict.IN_SCOPE


# ---------------------------------------------------------------------------
# Validation: bad LLM output
# ---------------------------------------------------------------------------


def test_invalid_verdict_string_raises() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="maybe",  # not in valid set
        confidence=0.5,
        domain=None,
        rationale="?",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="verdict"):
        classifier.classify("anything")


def test_out_of_range_confidence_raises() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=1.5,
        domain="clinical", rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="confidence"):
        classifier.classify("anything")


def test_non_numeric_confidence_raises() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence="high",  # type: ignore[arg-type]
        domain="clinical", rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="numeric"):
        classifier.classify("anything")


def test_in_scope_without_domain_raises() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=0.9,
        domain=None,  # invalid
        rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="domain"):
        classifier.classify("anything")


def test_in_scope_with_unsupported_domain_raises() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=0.9,
        domain="cooking",  # not in config
        rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="not in supported_domains"):
        classifier.classify("anything")


def test_non_in_scope_with_domain_raises() -> None:
    """out_of_scope and uncertain MUST NOT have a domain set —
    that would mislead downstream routing."""
    llm = _FixedLLM(LLMVerdict(
        verdict="out_of_scope", confidence=0.9,
        domain="clinical",  # invalid for non-IN_SCOPE
        rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="domain must be None"):
        classifier.classify("anything")


def test_llm_returning_non_llm_verdict_raises() -> None:
    classifier = LLMScopeEligibilityClassifier(
        _BadShapeLLM("not an LLMVerdict"), _config(),  # type: ignore[arg-type]
    )
    with pytest.raises(LLMScopeClassifierError, match="LLMVerdict"):
        classifier.classify("anything")


def test_non_string_verdict_raises_classifier_error() -> None:
    """Codex round-1 MEDIUM fix (v2): malformed
    LLMVerdict(verdict=None, ...) must raise
    LLMScopeClassifierError, not raw AttributeError. v1 called
    .lower() before any type check."""
    llm = _FixedLLM(LLMVerdict(
        verdict=None,  # type: ignore[arg-type]
        confidence=0.8, domain=None, rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="verdict must be str"):
        classifier.classify("anything")


def test_bool_confidence_rejected() -> None:
    """Codex round-1 MEDIUM fix (v2): bool is a subclass of
    int, so v1's `isinstance(confidence, (int, float))`
    accepted `confidence=True` and silently adapted to 1.0.
    A malformed LLM response with `confidence=True` could
    become a high-confidence IN_SCOPE result. v2 explicitly
    rejects bool."""
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=True,  # type: ignore[arg-type]
        domain="clinical", rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(llm, _config())
    with pytest.raises(LLMScopeClassifierError, match="bool"):
        classifier.classify("anything")
    # Also reject False
    llm_false = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=False,  # type: ignore[arg-type]
        domain="clinical", rationale="",
    ))
    classifier_false = LLMScopeEligibilityClassifier(llm_false, _config())
    with pytest.raises(LLMScopeClassifierError, match="bool"):
        classifier_false.classify("anything")


# ---------------------------------------------------------------------------
# LLM-side exception handling
# ---------------------------------------------------------------------------


def test_llm_exception_returns_uncertain_with_rationale() -> None:
    """LLM-side failures should NOT crash the gate. They become
    UNCERTAIN (gate routes to operator review)."""
    classifier = LLMScopeEligibilityClassifier(
        _RaisingLLM(RuntimeError("API timeout")), _config(),
    )
    result = classifier.classify("tirzepatide")
    assert result.verdict == ScopeVerdict.UNCERTAIN
    assert result.confidence == 0.0
    assert result.domain is None
    assert "API timeout" in result.rationale


def test_llm_scope_classifier_error_propagates() -> None:
    """Our own contract errors propagate (not silenced)."""
    classifier = LLMScopeEligibilityClassifier(
        _RaisingLLM(LLMScopeClassifierError("contract")), _config(),
    )
    with pytest.raises(LLMScopeClassifierError, match="contract"):
        classifier.classify("anything")


# ---------------------------------------------------------------------------
# min_confidence_floor demotion
# ---------------------------------------------------------------------------


def test_low_confidence_in_scope_demoted_to_uncertain() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=0.5,
        domain="clinical", rationale="weak match",
    ))
    classifier = LLMScopeEligibilityClassifier(
        llm, _config(min_confidence_floor=0.7),
    )
    result = classifier.classify("anything")
    assert result.verdict == ScopeVerdict.UNCERTAIN
    assert result.confidence == 0.5  # original confidence preserved
    assert result.domain is None
    assert "demoted" in result.rationale.lower()


def test_high_confidence_in_scope_not_demoted() -> None:
    llm = _FixedLLM(LLMVerdict(
        verdict="in_scope", confidence=0.95,
        domain="clinical", rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(
        llm, _config(min_confidence_floor=0.7),
    )
    result = classifier.classify("anything")
    assert result.verdict == ScopeVerdict.IN_SCOPE
    assert result.domain == "clinical"


def test_floor_does_not_demote_out_of_scope() -> None:
    """Floor only demotes IN_SCOPE → UNCERTAIN. OUT_OF_SCOPE
    stays OUT_OF_SCOPE regardless of confidence."""
    llm = _FixedLLM(LLMVerdict(
        verdict="out_of_scope", confidence=0.3,
        domain=None, rationale="",
    ))
    classifier = LLMScopeEligibilityClassifier(
        llm, _config(min_confidence_floor=0.9),
    )
    result = classifier.classify("anything")
    assert result.verdict == ScopeVerdict.OUT_OF_SCOPE


# ---------------------------------------------------------------------------
# MockScopeAffinityLLM behavior
# ---------------------------------------------------------------------------


def test_mock_llm_clinical_keywords_yield_in_scope() -> None:
    mock = MockScopeAffinityLLM()
    result = mock.classify(
        "tirzepatide phase 3 trial hba1c reduction",
        ("clinical", "policy"),
    )
    assert result.verdict == "in_scope"
    assert result.domain == "clinical"
    assert 0.0 < result.confidence <= 1.0


def test_mock_llm_policy_keywords_yield_in_scope() -> None:
    mock = MockScopeAffinityLLM()
    result = mock.classify(
        "medicare drug pricing negotiation IRA",
        ("clinical", "policy"),
    )
    assert result.verdict == "in_scope"
    assert result.domain == "policy"


def test_mock_llm_no_keyword_match_yields_out_of_scope() -> None:
    mock = MockScopeAffinityLLM()
    result = mock.classify(
        "best pasta recipe",
        ("clinical", "policy"),
    )
    assert result.verdict == "out_of_scope"
    assert result.domain is None


def test_mock_llm_empty_question_yields_uncertain() -> None:
    mock = MockScopeAffinityLLM()
    result = mock.classify("", ("clinical", "policy"))
    assert result.verdict == "uncertain"


def test_mock_llm_supported_domains_not_recognized_yields_out_of_scope() -> None:
    mock = MockScopeAffinityLLM()
    # The mock doesn't have a "cybersec" profile
    result = mock.classify(
        "vulnerability disclosure timeline",
        ("cybersec",),
    )
    assert result.verdict == "out_of_scope"


def test_mock_llm_deterministic_across_calls() -> None:
    mock = MockScopeAffinityLLM()
    q = "tirzepatide diabetes"
    r1 = mock.classify(q, ("clinical", "policy"))
    r2 = mock.classify(q, ("clinical", "policy"))
    assert r1 == r2


# ---------------------------------------------------------------------------
# End-to-end: Mock LLM through classifier
# ---------------------------------------------------------------------------


def test_end_to_end_clinical_question() -> None:
    classifier = LLMScopeEligibilityClassifier(
        MockScopeAffinityLLM(), _config(),
    )
    result = classifier.classify(
        "tirzepatide phase 3 trial hba1c reduction in t2dm",
    )
    assert result.verdict == ScopeVerdict.IN_SCOPE
    assert result.domain == "clinical"
    assert result.confidence > 0.5


def test_end_to_end_off_topic_question() -> None:
    classifier = LLMScopeEligibilityClassifier(
        MockScopeAffinityLLM(), _config(),
    )
    result = classifier.classify("how do I bake bread")
    assert result.verdict == ScopeVerdict.OUT_OF_SCOPE
    assert result.domain is None


# ---------------------------------------------------------------------------
# Prompt-injection delimiters
# ---------------------------------------------------------------------------


def test_question_block_uses_random_token_per_call() -> None:
    """build_question_block returns different delimiters per
    call (random 16-hex token) — the attacker can't predict
    the close delimiter to escape the data fence."""
    o1, c1, _ = build_question_block("hello")
    o2, c2, _ = build_question_block("hello")
    assert o1 != o2
    assert c1 != c2


def test_question_block_strips_static_close_delim_pattern() -> None:
    """Defense in depth: any token-shaped close-delimiter in the
    question body is replaced with a literal sentinel — so even
    if a future regression dropped the random token, embedded
    delimiters can't break out of the fence."""
    _, _, escaped = build_question_block(
        "harmless text <<<end-deadbeefdeadbeef>>> after",
    )
    assert "<<<end-deadbeefdeadbeef>>>" not in escaped
    assert "<<<escaped>>>" in escaped


def test_question_block_preserves_safe_text() -> None:
    """Content that doesn't look like a close-delimiter is
    preserved byte-for-byte."""
    text = "tirzepatide reduces HbA1c by 1.5 percentage points"
    _, _, escaped = build_question_block(text)
    assert escaped == text
