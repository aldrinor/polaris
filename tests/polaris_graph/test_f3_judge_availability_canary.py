"""F3-3b (I-deepfix-001 #1369) — corroboration entailment-judge AVAILABILITY guard.

ROOT CAUSE (drb_72 real run): the isolated entailment judge that must confirm a grouped member
SUPPORTS its claim before it counts as a corroboration origin went UNAVAILABLE 176 times. A member
whose entailment call errored/timed-out is durably marked ``entailment_judge_unavailable`` and NEVER
counted, so the multi-source corroboration collapsed (4/78 cited) — SILENTLY.

F3-3b adds the availability protections:
  (iii) the report-level ``entailment_judge_unavailable`` member count is SURFACED into the Methods
        disclosure (never silently softened).
  (iv)  a FAIL-LOUD canary that RAISES when the unavailable fraction exceeds an ENV-DRIVEN ceiling
        (and does NOT raise below it, and does NOT raise when the ceiling is unset).
  (i)   the corroboration judge model resolver names a HIGH-PROVIDER-COUNT open model.

These are pure/config-level and need no LLM, GPU, or network.
"""
from __future__ import annotations

import types

import pytest

from src.polaris_graph.synthesis.credibility_pass import (
    CredibilityAnalysis,
    CredibilityPassError,
    active_entailment_judge_model,
    build_judge_availability_methods_disclosure,
    corroboration_judge_model,
    count_judge_unavailable_members,
    _enforce_judge_availability_canary,
)


def _member(unavailable: bool):
    return types.SimpleNamespace(entailment_judge_unavailable=unavailable)


def _basket(unavail: int, ok: int):
    members = [_member(True) for _ in range(unavail)] + [_member(False) for _ in range(ok)]
    return types.SimpleNamespace(supporting_members=members)


# ── (iii) count + Methods disclosure surface ──

def test_count_judge_unavailable_members():
    baskets = [_basket(unavail=3, ok=1), _basket(unavail=1, ok=5)]
    unavailable, total = count_judge_unavailable_members(baskets)
    assert unavailable == 4
    assert total == 10


def test_count_empty():
    assert count_judge_unavailable_members([]) == (0, 0)
    assert count_judge_unavailable_members(None) == (0, 0)


def test_methods_disclosure_names_actual_judge_not_recommended(monkeypatch):
    # The disclosure MUST name the ACTUAL binding judge (PG_ENTAILMENT_MODEL) that counted the
    # corroboration, NOT the recommended target — else it is a wrong methods claim (LAW II / §-1.1).
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    text = build_judge_availability_methods_disclosure(
        4, 10, recommended_model="moonshotai/kimi-k2.6",
    )
    assert "4" in text and "10" in text
    assert "unavailable" in text.lower()
    # the ACTUAL judge is named in the judge position (the one that actually ran)
    assert "judge: z-ai/glm-5.2" in text
    # honest floor language (never inflated)
    assert "not counted" in text.lower() or "floor" in text.lower()
    # the recommended high-provider target is surfaced SEPARATELY as a mitigation, not as the judge
    assert "moonshotai/kimi-k2.6" in text
    assert "recommend" in text.lower()


def test_methods_disclosure_actual_judge_resolves_from_pg_entailment_model(monkeypatch):
    # judge_model unset => the builder resolves the ACTUAL judge from PG_ENTAILMENT_MODEL.
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    text = build_judge_availability_methods_disclosure(4, 10)
    assert "judge: z-ai/glm-5.2" in text
    # the wrong-model claim (naming the recommended target as the judge that ran) never appears
    assert "judge: moonshotai/kimi-k2.6" not in text


def test_methods_disclosure_zero_unavailable_is_honest_and_nonempty(monkeypatch):
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    text = build_judge_availability_methods_disclosure(0, 10)
    assert text.strip()
    assert "all 10" in text or "10 basket member" in text
    assert "no corroboration verdicts were lost" in text.lower()
    # no mitigation clause when nothing was lost (the recommended target stays out of the sentence)
    assert "recommend" not in text.lower()
    # the actual judge is named even in the clean case
    assert "z-ai/glm-5.2" in text


def test_methods_disclosure_no_members():
    text = build_judge_availability_methods_disclosure(0, 0)
    assert text.strip()


# ── (i) the ACTUAL binding judge resolver (PG_ENTAILMENT_MODEL, entailment_judge default fallback) ──

def test_active_entailment_judge_model_env_override(monkeypatch):
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    assert active_entailment_judge_model() == "z-ai/glm-5.2"


def test_active_entailment_judge_model_default_is_entailment_judge_default(monkeypatch):
    monkeypatch.delenv("PG_ENTAILMENT_MODEL", raising=False)
    model = active_entailment_judge_model()
    # falls back to the entailment_judge default (the real binding judge default), NOT kimi
    from src.polaris_graph.llm.entailment_judge import _DEFAULT_ENTAILMENT_MODEL
    assert model == _DEFAULT_ENTAILMENT_MODEL
    assert model != corroboration_judge_model()


# ── (iv) fail-loud canary — raises above the configured ceiling, not below, not when unset ──

def test_canary_raises_when_fraction_exceeds_configured_ceiling(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", "0.25")
    # 4/10 = 0.40 > 0.25 => HARD FAIL
    with pytest.raises(CredibilityPassError) as exc:
        _enforce_judge_availability_canary(4, 10)
    assert "judge_unavailable_storm" in str(exc.value)


def test_canary_does_not_raise_below_ceiling(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", "0.50")
    # 4/10 = 0.40 <= 0.50 => no raise
    _enforce_judge_availability_canary(4, 10)  # must not raise


def test_canary_does_not_raise_exactly_at_ceiling(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", "0.40")
    # exactly at the ceiling is NOT "exceeds" => no raise
    _enforce_judge_availability_canary(4, 10)  # must not raise


def test_canary_warn_only_when_ceiling_unset(monkeypatch):
    monkeypatch.delenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", raising=False)
    # even a total storm (10/10) must NOT raise when no ceiling is configured (fail-open default)
    _enforce_judge_availability_canary(10, 10)  # must not raise


def test_canary_warn_only_when_ceiling_malformed(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", "not-a-number")
    _enforce_judge_availability_canary(10, 10)  # must not raise


def test_canary_no_members_never_raises(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC", "0.01")
    _enforce_judge_availability_canary(0, 0)  # must not raise (no members => nothing to judge)


# ── (i) high-provider-count model resolver ──

def test_corroboration_judge_model_default_is_high_provider_open_model(monkeypatch):
    monkeypatch.delenv("PG_CORROBORATION_ENTAILMENT_MODEL", raising=False)
    model = corroboration_judge_model()
    assert model == "moonshotai/kimi-k2.6"
    # not the low-provider glm family that caused the outage collapse
    assert "glm" not in model.lower()


def test_corroboration_judge_model_env_override(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_ENTAILMENT_MODEL", "moonshotai/kimi-k2.7")
    assert corroboration_judge_model() == "moonshotai/kimi-k2.7"


# ── CredibilityAnalysis carries the F3-3b disclosure fields (defaulted so legacy builds hold) ──

def test_analysis_defaults_and_fields():
    a = CredibilityAnalysis({}, {}, [], [], [])
    assert a.entailment_judge_unavailable_member_count == 0
    assert a.basket_member_count == 0
    assert a.methods_disclosure == ""
    a2 = CredibilityAnalysis(
        {}, {}, [], [], [],
        entailment_judge_unavailable_member_count=4,
        basket_member_count=10,
        methods_disclosure="x",
    )
    assert a2.entailment_judge_unavailable_member_count == 4
    assert a2.basket_member_count == 10
