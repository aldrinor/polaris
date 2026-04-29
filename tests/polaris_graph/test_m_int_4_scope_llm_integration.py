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
