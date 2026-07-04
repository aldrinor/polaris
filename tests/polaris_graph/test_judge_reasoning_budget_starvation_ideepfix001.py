"""I-deepfix-001 — judge reasoning-budget anti-starvation (§9.1.8).

Root: a reasoning model emits its internal reasoning burst FIRST, from the SAME ``max_tokens`` budget as
the answer. GLM IGNORES ``reasoning.effort``, so a provider that runs reasoning long can consume the whole
budget and return EMPTY ``message.content`` (finish_reason=``length``) — the operator's live probe proved
this on ``z-ai/glm-5.2`` (max_tokens=20 -> content=None). The fix gives every GLM-family side judge a
NUMERIC ``reasoning.max_tokens`` cap STRICTLY BELOW the total ``max_tokens`` (the proven D8-Mirror bound),
so the verdict always keeps content headroom.

These tests are OFFLINE / $0 / no GPU / no network — a fake httpx transport SIMULATES the operator's exact
failure: a worst-case reasoning provider consumes ``reasoning.max_tokens`` if the body caps it, else the
WHOLE ``max_tokens`` budget. Under that simulation:

  * the PRIOR shape ``reasoning:{effort:...}`` (no numeric cap) -> reasoning eats the budget -> EMPTY   (RED)
  * the FIXED shape ``reasoning:{max_tokens: cap}`` (cap << max_tokens) -> headroom -> real JSON content (GREEN)

Both assertions pass in CI; TOGETHER they prove the numeric cap is load-bearing (RED baseline vs GREEN fix).
NO ``unittest.mock`` (CLAUDE.md §9.4).
"""
from __future__ import annotations

import json

import pytest

import src.polaris_graph.llm.openrouter_client as orc
from src.polaris_graph.llm import judge_reasoning_block as jrb
from src.polaris_graph.authority import credibility_judge_caller as cjc


# ── PART A — the shared reasoning-block helper invariant ─────────────────────────────────────────────


def test_glm_gets_numeric_reasoning_cap_below_total():
    block = jrb.build_judge_reasoning_block("z-ai/glm-5.2", "high", 131072)
    assert "max_tokens" in block, "a glm judge must get a NUMERIC reasoning cap, not an ignored effort tier"
    assert "effort" not in block
    # the structural invariant: reasoning_cap << total so the verdict always keeps content headroom.
    assert block["max_tokens"] < 131072
    assert block["max_tokens"] >= 1024


def test_non_glm_keeps_effort_shape_byte_identical():
    # the kimi-k2.6 entailment override (and any other non-glm judge) is UNCHANGED.
    assert jrb.build_judge_reasoning_block("moonshotai/kimi-k2.6", "high", 131072) == {"effort": "high"}
    assert jrb.build_judge_reasoning_block("deepseek/deepseek-v4-pro", "xhigh", 8000) == {"effort": "xhigh"}


def test_reasoning_cap_keeps_content_floor_even_at_small_budget():
    # even a small total budget keeps >= content_floor for the verdict (env default floor 4000).
    block = jrb.build_judge_reasoning_block("z-ai/glm-5.2", "high", 6000)
    assert block["max_tokens"] <= 6000 - 4000  # >= 4000 tokens left for the JSON verdict
    assert block["max_tokens"] >= 1024


def test_reasoning_cap_env_overridable(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_REASONING_MAX_TOKENS", "12000")
    monkeypatch.setenv("PG_JUDGE_REASONING_CONTENT_FLOOR", "8000")
    block = jrb.build_judge_reasoning_block("z-ai/glm-5.2", "high", 131072)
    assert block == {"max_tokens": 12000}  # env cap, well below the 131072-8000 headroom


def test_reasoning_cap_strictly_below_total_at_starved_budget():
    """Codex diff-gate iter1 P1: at a total BELOW the content floor + cap floor (e.g. the old 256-token
    relevance starvation config, or an env-lowered 256 entailment/conflict total) the cap must stay
    STRICTLY below the total so reasoning can never eat the whole budget. The prior 1024 hard floor
    INVERTED here (1024 >= 256), re-opening the blank-verdict path."""
    for total in (256, 300, 512, 1024, 2000):
        block = jrb.build_judge_reasoning_block("z-ai/glm-5.2", "high", total)
        cap = block["max_tokens"]
        assert cap < total, f"reasoning cap {cap} must be strictly below total {total} (never eat the budget)"
        assert cap >= 1, f"reasoning cap {cap} must stay positive at total {total}"
        assert total - cap >= 1, f"no content headroom left at total {total} (cap {cap})"


def test_reasoning_cap_never_inverts_across_the_boundary():
    """Sweep the boundary between the starved and healthy regimes: the numeric cap is ALWAYS strictly
    below the total, so ``reasoning.max_tokens < max_tokens`` holds for every real budget a judge uses."""
    for total in (64, 200, 4000, 4001, 5023, 5024, 5025, 8000, 131072):
        cap = jrb.reasoning_cap_for(total)
        assert cap < total, f"cap {cap} inverted at total {total}"


def test_is_glm_slug_detection():
    assert jrb.is_glm_slug("z-ai/glm-5.2")
    assert jrb.is_glm_slug("zhipuai/glm-4.6")
    assert not jrb.is_glm_slug("moonshotai/kimi-k2.6")
    assert not jrb.is_glm_slug("minimax/minimax-m2")
    assert not jrb.is_glm_slug(None)


# ── PART B — the PRODUCTION credibility-judge caller, RED baseline vs GREEN fix ───────────────────────


_GOOD_JSON = json.dumps(
    {"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok", "signals_cited": []}
)
_CONTENT_FLOOR_FOR_STUB = 1000  # the fake needs at least this much room after reasoning to emit content


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _StarvationFakeClient:
    """A reasoning-model provider that runs reasoning to its bound: ``reasoning.max_tokens`` if the body
    caps it, else the WHOLE ``max_tokens`` budget (the operator's failure). Content lands ONLY if the
    budget minus that reasoning allocation leaves room — i.e. only when a numeric reasoning cap exists.

    Subclasses override ``_GOOD_CONTENT`` to return a body-appropriate verdict (credibility JSON vs the
    relevance ``label`` JSON)."""

    _GOOD_CONTENT = _GOOD_JSON

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        return None

    def post(self, endpoint, headers=None, json=None):
        body = json or {}
        reasoning = body.get("reasoning") or {}
        max_tokens = int(body.get("max_tokens") or 0)
        if "max_tokens" in reasoning:
            reasoning_budget = int(reasoning["max_tokens"])
        else:
            reasoning_budget = max_tokens  # effort-only / no numeric cap -> reasoning eats the WHOLE budget
        content_room = max_tokens - reasoning_budget
        if content_room >= _CONTENT_FLOOR_FOR_STUB:
            content, finish = self._GOOD_CONTENT, "stop"
        else:
            content, finish = "", "length"  # STARVED: reasoning consumed the budget, verdict never lands
        return _FakeResp(
            {
                "choices": [{"message": {"content": content}, "finish_reason": finish}],
                "usage": {"cost": 0.0001, "prompt_tokens": 10, "completion_tokens": 20},
            }
        )


@pytest.fixture()
def _cred_env(monkeypatch):
    """Two-family segregation + single-attempt + a fake transport so the production caller runs offline."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-offline")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_RETRIES", "0")  # deterministic single attempt
    monkeypatch.setenv("PG_ROLE_ALLOW_FALLBACKS", "1")       # free-route: no provider-pin lookup needed
    # generator must be a DIFFERENT family than the glm credibility judge (two-family invariant).
    monkeypatch.setattr(orc, "PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro", raising=False)
    import httpx
    monkeypatch.setattr(httpx, "Client", _StarvationFakeClient)
    orc.reset_run_cost()
    yield
    orc.reset_run_cost()


def test_production_credibility_judge_gets_nonempty_content_with_numeric_cap(_cred_env):
    """GREEN: the SHIPPING credibility-judge caller builds a body with a numeric reasoning cap, so the
    simulated worst-case reasoning provider returns real JSON content (never blank)."""
    call_llm = cjc.make_openrouter_credibility_caller(model="z-ai/glm-5.2")
    out = call_llm("score this source")
    assert out.strip(), "the production credibility judge STARVED to empty content — the §9.1.8 bug"
    parsed = json.loads(out)
    assert parsed["reliability_score"] == 0.8


def test_effort_only_shape_would_starve_to_empty_red_baseline(_cred_env, monkeypatch):
    """RED baseline: force the PRIOR ``reasoning:{effort:...}`` shape (no numeric cap) and the SAME
    provider blanks — proving the numeric cap in the GREEN test above is load-bearing, not cosmetic."""
    monkeypatch.setattr(
        cjc, "_build_reasoning_block", lambda model, effort, max_tokens: {"effort": effort}
    )
    call_llm = cjc.make_openrouter_credibility_caller(model="z-ai/glm-5.2")
    out = call_llm("score this source")
    assert out.strip() == "", "expected the effort-only body to STARVE (RED baseline for the fix)"


# ── PART C — the PRODUCTION W2 content-relevance judge (the 4th glm judge), RED vs GREEN ──────────────
# Codex diff-gate iter1 P0#1: the W2 content-relevance escalation is DEFAULT-ON (run_gate_b force-enables
# it) and escalates ambiguous passages to generator/relevance_judge.py's glm-5.2 judge, which the prior
# diff never touched — its OLD default max_tokens=256 + reasoning:{effort} starved to blank on every run.

from src.polaris_graph.generator import relevance_judge as rjmod  # noqa: E402

# A REAL verdict distinct from the always-release SUPPORTED fail-default, so a blanked call (coerced to
# SUPPORTED) is DISTINGUISHABLE from a real landed verdict.
_GOOD_RELEVANCE_JSON = json.dumps({"label": "INSUFFICIENT", "reason": "topical-but-off-relation"})


class _RelevanceStarvationFakeClient(_StarvationFakeClient):
    _GOOD_CONTENT = _GOOD_RELEVANCE_JSON


@pytest.fixture()
def _rel_env(monkeypatch):
    """Two-family segregation (generator deepseek vs glm judge) + a fake transport so the production W2
    relevance judge runs offline. Uses the new 131072 default (PG_RELEVANCE_MAX_TOKENS unset)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-offline")
    monkeypatch.delenv("PG_RELEVANCE_MAX_TOKENS", raising=False)        # exercise the new real-budget default
    monkeypatch.delenv("PG_RELEVANCE_ALLOW_SAME_FAMILY", raising=False)  # keep the two-family guard ON
    monkeypatch.setattr(orc, "PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro", raising=False)
    import httpx
    monkeypatch.setattr(httpx, "Client", _RelevanceStarvationFakeClient)
    rjmod.reset_judge_singleton()
    orc.reset_run_cost()
    yield
    rjmod.reset_judge_singleton()
    orc.reset_run_cost()


def test_production_content_relevance_judge_lands_real_verdict_with_numeric_cap(_rel_env):
    """GREEN: the SHIPPING W2 content-relevance judge builds a body with a numeric reasoning cap + a real
    131072 budget, so the simulated worst-case reasoning provider returns the REAL verdict — the off-topic
    passage is correctly labeled INSUFFICIENT (demoted), NOT silently kept via the always-release default."""
    judge = rjmod.make_content_relevance_judge()
    label, reason = judge.judge("what is the maple-syrup export volume?", "an unrelated cookie banner")
    assert label == rjmod.LABEL_INSUFFICIENT, (
        "the W2 relevance judge STARVED — a real INSUFFICIENT verdict was lost and coerced to SUPPORTED "
        f"(always-release), keeping an off-topic passage at full weight. Got ({label!r}, {reason!r})."
    )
    assert not reason.startswith("judge_error"), "expected a REAL parsed verdict, not the fail-to-keep path"


def test_content_relevance_effort_only_shape_starves_to_keep_default_red_baseline(_rel_env, monkeypatch):
    """RED baseline: force the PRIOR ``reasoning:{effort:...}`` shape and the SAME provider blanks — the
    real INSUFFICIENT verdict is LOST and the judge falls back to SUPPORTED (a MISSED demotion: off-topic
    junk kept at full weight). Proves the numeric cap in the GREEN test above is load-bearing."""
    monkeypatch.setattr(
        rjmod, "_build_reasoning_block", lambda model, effort, max_tokens: {"effort": effort}
    )
    judge = rjmod.make_content_relevance_judge()
    label, reason = judge.judge("what is the maple-syrup export volume?", "an unrelated cookie banner")
    assert label == rjmod.LABEL_SUPPORTED, "expected the effort-only body to blank -> always-release SUPPORTED"
    assert reason.startswith("judge_error"), "the blanked verdict must surface as a judge_error keep (RED baseline)"


# ── PART D — the W2 escalation must FAIL-CLOSED on a per-run BUDGET breach ────────────────────────────
# Codex diff-gate iter2 P1: relevance_judge.py books the judge spend then re-raises BudgetExceededError on
# a PG_MAX_COST_PER_RUN breach, but the DEFAULT-ON W2 escalation worker (_resolve_ambiguous._one) caught a
# GENERIC Exception and converted it to an always-release full-weight keep — so a cap breach on the live
# content-relevance path was silently swallowed instead of aborting. score_passages must PROPAGATE the
# BudgetExceededError (fail-closed) while STILL keeping the passage on any non-budget transport fault
# (§-1.3 weight-not-filter: a runtime blip never demotes/drops; only a real cap breach aborts).

from src.polaris_graph.retrieval import content_relevance_judge as crj  # noqa: E402
from src.polaris_graph.llm.openrouter_client import BudgetExceededError  # noqa: E402


def _ambiguous_reranker(pairs):
    """One reranker score per window, parked in the ambiguous band [low, high) so every passage is
    escalated to the injected GLM judge (the path that books spend + can breach the budget)."""
    return [0.30 for _ in pairs]


def test_w2_escalation_budget_breach_fails_closed_ideepfix001():
    """GREEN (fix): when the escalation GLM judge raises BudgetExceededError (a PG_MAX_COST_PER_RUN
    breach), score_passages PROPAGATES it (fail-closed abort) instead of masking it as an always-release
    escalated_keep. RED before the fix: the broad ``except Exception`` swallowed it and returned a report
    full of full-weight keeps, so a cap breach on the default-on W2 path never aborted."""
    def _budget_breaching_judge(question, span):
        raise BudgetExceededError("PG_MAX_COST_PER_RUN breached mid-escalation")

    passages = [(0, "http://example/a", "a short ambiguous body about something")]
    with pytest.raises(BudgetExceededError):
        crj.score_passages(
            "what is the maple-syrup export volume?",
            passages,
            glm_judge_fn=_budget_breaching_judge,
            reranker_predict_fn=_ambiguous_reranker,
        )


def test_w2_escalation_non_budget_fault_still_keeps_always_release_ideepfix001():
    """Faithfulness-neutral guard: a NON-budget transport/parse fault in the escalation judge must STILL
    keep the passage at full weight (always-release, §-1.3) — the fail-closed change is narrow to
    BudgetExceededError only and does NOT start dropping/demoting sources on a runtime blip."""
    def _transport_blip_judge(question, span):
        raise RuntimeError("transient upstream 502")

    passages = [(0, "http://example/b", "a short ambiguous body about something")]
    report = crj.score_passages(
        "what is the maple-syrup export volume?",
        passages,
        glm_judge_fn=_transport_blip_judge,
        reranker_predict_fn=_ambiguous_reranker,
    )
    verdict = report.by_idx()[0]
    assert verdict.label == crj.LABEL_ESCALATED_KEEP, (
        "a non-budget escalation fault must KEEP the passage (always-release), not demote/drop it"
    )
    assert verdict.weight == 1.0, "always-release keep must stay at FULL weight on a non-budget fault"
