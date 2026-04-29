"""M-INT-4 — OpenRouter ScopeAffinityLLM in production scope-gate path.

Acceptance bar:
  1. Imported (`OpenRouterScopeAffinityLLM`, `LLMScopeEligibilityClassifier`,
     `LLMVerdict`)
  2. Invoked from sweep run path (telemetry alongside template-driven
     scope_gate)
  3. Run-log evidence (sweep_scope_llm_summary or per-run
     [M-INT-4] scope_llm log)
  4. PG_USE_LLM_SCOPE=0 disables (returns None / does not call LLM)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_scope_llm_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "OpenRouterScopeAffinityLLM")
    assert hasattr(sweep, "LLMScopeEligibilityClassifier")
    assert hasattr(sweep, "LLMScopeEligibilityClassifierConfig")
    assert hasattr(sweep, "LLMVerdict")
    assert hasattr(sweep, "_classify_scope_with_llm")


def test_classify_scope_with_llm_returns_verdict_with_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_LLM_SCOPE", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        MockScopeAffinityLLM,
    )
    monkeypatch.setattr(
        sweep, "_build_scope_llm", lambda: MockScopeAffinityLLM(),
    )

    summary = sweep._classify_scope_with_llm(
        question="What is the cardiovascular efficacy of tirzepatide?",
        domain="clinical",
    )
    assert summary is not None
    assert "verdict" in summary
    assert summary["verdict"] in {"in_scope", "out_of_scope", "uncertain"}
    assert "confidence" in summary
    assert 0.0 <= summary["confidence"] <= 1.0


def test_disabled_flag_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_LLM_SCOPE", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._classify_scope_with_llm(
        question="Some clinical question",
        domain="clinical",
    )
    assert summary is None


def test_empty_question_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_LLM_SCOPE", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._classify_scope_with_llm(
        question="",
        domain="clinical",
    )
    assert summary is None


def test_scope_llm_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II — best-effort telemetry must not gate the sweep."""
    monkeypatch.setenv("PG_USE_LLM_SCOPE", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    class _BrokenLLM:
        def classify(self, question, supported_domains):
            raise RuntimeError("simulated LLM outage")

    monkeypatch.setattr(sweep, "_build_scope_llm", lambda: _BrokenLLM())

    # Should not raise; the LLM-failure path inside
    # LLMScopeEligibilityClassifier converts to UNCERTAIN.
    summary = sweep._classify_scope_with_llm(
        question="What is X?",
        domain="clinical",
    )
    assert summary is not None
    assert summary["verdict"] in {"in_scope", "out_of_scope", "uncertain"}


def test_openrouter_scope_llm_implements_protocol() -> None:
    """OpenRouterScopeAffinityLLM should satisfy the Protocol shape
    (have a classify method) without instantiation if API key absent."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        OpenRouterScopeAffinityLLM,
        ScopeAffinityLLM,
    )
    assert hasattr(OpenRouterScopeAffinityLLM, "classify")
    # Cannot instantiate without OPENROUTER_API_KEY in CI; the
    # Protocol check is structural and verified on use.


# ---------------------------------------------------------------------------
# Codex round-1 MEDIUM fixes (v2) — _parse_scope_llm_json regressions
# ---------------------------------------------------------------------------


def test_parse_strips_domain_when_verdict_not_in_scope() -> None:
    """Codex round-1 medium 1: parser must strip domain when
    verdict is not in_scope, otherwise the adapter raises
    'domain must be None for non-IN_SCOPE' and telemetry is lost."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"out_of_scope","confidence":0.8,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "out_of_scope"
    assert verdict.domain is None  # stripped per adapter contract


def test_parse_strips_domain_when_verdict_uncertain() -> None:
    """Same medium 1 — verdict=uncertain must strip domain too."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"uncertain","confidence":0.4,'
        '"domain":"policy","rationale":"borderline"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.domain is None


def test_parse_rejects_bool_confidence() -> None:
    """Codex round-1 medium 2: JSON `true` becomes Python bool
    `True`, and `float(True)` is `1.0`. Without explicit bool
    guard, malformed `{"confidence": true}` becomes a perfect-
    confidence verdict. v2 explicitly falls back to 0.0."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":true,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.confidence == 0.0  # NOT 1.0


def test_parse_rejects_false_confidence_via_bool_guard() -> None:
    """Same medium 2 — `false` should also be rejected (not become 0.0
    via float coercion silently — explicit fallback path)."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":false,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.confidence == 0.0


def test_parse_invalid_verdict_string_strips_domain() -> None:
    """Codex round-1 medium 1 corner: invalid verdict ("bogus")
    coerces to "uncertain", and uncertain must have domain=None."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"bogus","confidence":0.7,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.domain is None  # coerced to uncertain → domain stripped


# ---------------------------------------------------------------------------
# Codex round-2 MEDIUM fixes (v3) — incomplete domain check + NaN/inf bypass
# ---------------------------------------------------------------------------


def test_parse_in_scope_with_null_domain_coerces_to_uncertain() -> None:
    """Codex round-2 medium 3: in_scope with domain=null violated
    adapter contract (in_scope MUST have a domain). v2 only stripped
    domain on non-in_scope verdicts; v3 coerces in_scope+None to
    UNCERTAIN so the malformed-output fallback stays consistent."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":0.8,'
        '"domain":null,"rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"  # NOT in_scope
    assert verdict.domain is None


def test_parse_in_scope_missing_domain_field_coerces_to_uncertain() -> None:
    """Same medium 3 corner: domain key entirely missing."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = '{"verdict":"in_scope","confidence":0.8,"rationale":"x"}'
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.domain is None


def test_parse_rejects_nan_confidence() -> None:
    """Codex round-2 medium 4: float('NaN') is nan, and
    min(1.0, nan) returns 1.0 because nan comparisons are always
    False. v2's bool guard didn't catch this. v3 rejects
    non-finite via math.isfinite()."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    # JSON has no NaN literal; emit it manually as Python value
    # via json.loads tolerance? Use Python literal in raw string —
    # standard JSON rejects NaN, but some LLMs emit it.
    raw = '{"verdict":"in_scope","confidence":NaN,"domain":"clinical"}'
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    # confidence MUST be 0.0 not 1.0
    assert verdict.confidence == 0.0


def test_parse_rejects_inf_confidence_via_string() -> None:
    """Same medium 4: '1e309' parses to inf in Python; min(1.0, inf)
    is 1.0. v3 rejects via isfinite check."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    # If LLM returns confidence as string "1e309", parser may try
    # float() in fallback path. Test the direct float-coercion path.
    raw = '{"verdict":"in_scope","confidence":"1e309","domain":"clinical"}'
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.confidence == 0.0


def test_parse_in_scope_with_unsupported_domain_still_coerces() -> None:
    """v2 fix preserved: unsupported domain → out_of_scope."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":0.9,'
        '"domain":"cooking","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "out_of_scope"
    assert verdict.domain is None


# ---------------------------------------------------------------------------
# Codex round-3 LOW fix (v4) — malformed confidence MUST also flip verdict
# ---------------------------------------------------------------------------


def test_parse_negative_confidence_coerces_verdict_to_uncertain() -> None:
    """Codex round-3 LOW: -0.25 was clamped to 0.0 but verdict
    stayed in_scope. Now any out-of-range confidence flips to uncertain."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":-0.25,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.confidence == 0.0
    assert verdict.domain is None  # uncertain → domain stripped


def test_parse_above_one_confidence_coerces_verdict() -> None:
    """Codex round-3 LOW corner: 2.0 was clamped to 1.0 but
    verdict stayed in_scope. v4 treats >1.0 as malformed too."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":2.0,'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.confidence == 1.0  # clamped, BUT verdict flipped


def test_parse_list_confidence_coerces_verdict() -> None:
    """Codex round-3 LOW: float([]) raises TypeError, fallback
    to 0.0. v3 kept verdict=in_scope. v4 flips to uncertain."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":[],'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.confidence == 0.0


def test_parse_dict_confidence_coerces_verdict() -> None:
    """Codex round-3 LOW corner: same for dict shape."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":{},'
        '"domain":"clinical","rationale":"x"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "uncertain"
    assert verdict.confidence == 0.0


def test_parse_legit_zero_confidence_keeps_verdict() -> None:
    """Regression check: confidence=0.0 (legit low) is NOT
    malformed — it's just low confidence. Verdict must
    survive."""
    from src.polaris_graph.audit_ir.scope_classifier_llm import (
        _parse_scope_llm_json,
    )
    raw = (
        '{"verdict":"in_scope","confidence":0.0,'
        '"domain":"clinical","rationale":"low confidence"}'
    )
    verdict = _parse_scope_llm_json(raw, ("clinical", "policy"))
    assert verdict.verdict == "in_scope"  # NOT flipped to uncertain
    assert verdict.confidence == 0.0
    assert verdict.domain == "clinical"
