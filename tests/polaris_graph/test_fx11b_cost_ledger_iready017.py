"""I-ready-017 FX-11b (#1117) — cost-ledger P2 follow-ups of FX-11 (#1116).

Cost-accounting only (no faithfulness path). Covers:
  1. NLI-conflict judge writes a canonical cost-ledger ROW (semantic_conflict_detector).
  3. UsageTracker.total_cost_usd excludes free-call tokens from the imputed fallback.

(Item 2 — graph.py pipeline-B ambient run-id alignment — is a 3-line set/reset in a large
pipeline-B async function; the cost-ledger KEY resolution it fixes is already covered by the
FX-11 ambient-run-id tests, test_m206_n301_cost_ledger.py.)

All offline: no network (httpx post is monkeypatched), no model.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.llm.openrouter_client as orc
from src.polaris_graph.llm.openrouter_client import UsageTracker
from src.polaris_graph.retrieval import semantic_conflict_detector as scd


# ───────────────────────── item 1: NLI-conflict judge ledger row ─────────────────────────
def test_nli_conflict_judge_writes_cost_ledger_row(monkeypatch):
    """The NLI-conflict judge already feeds the run BUDGET (_add_run_cost); FX-11b adds the
    canonical ledger ROW so the persisted ledger total no longer trails the budget total when
    PG_SWEEP_NLI_CONFLICT is on."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(orc, "check_family_segregation", lambda **k: None)
    monkeypatch.setattr(orc, "current_run_id", lambda: "run-xyz")
    monkeypatch.setattr(orc, "_add_run_cost", lambda c: None)
    monkeypatch.setattr(orc, "check_run_budget", lambda c: None)
    captured: list[dict] = []
    monkeypatch.setattr(
        orc, "append_cost_ledger_row",
        lambda **kw: captured.append(kw) or 0.0,
    )

    judge = scd._SemanticContradictionJudge()

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.002},
                "choices": [{"message": {"content": '{"verdict": "CONTRADICT", "confidence": 0.9}'}}],
            }

    monkeypatch.setattr(judge._client, "post", lambda *a, **k: _Resp())

    label, conf = judge.judge("claim a", "claim b")
    assert label == "contradict"
    assert len(captured) == 1, "NLI-conflict judge must write exactly one cost-ledger row"
    row = captured[0]
    assert row["call_type"] == "nli_conflict_judge"
    assert row["session_id"] == "run-xyz"  # ambient run id (matches judge/role writers)
    assert row["cost_usd"] == pytest.approx(0.002)
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 20


def test_nli_conflict_judge_ledger_failure_does_not_abort(monkeypatch):
    """Ledger I/O must never abort conflict detection (best-effort write)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(orc, "check_family_segregation", lambda **k: None)
    monkeypatch.setattr(orc, "current_run_id", lambda: "run-xyz")
    monkeypatch.setattr(orc, "_add_run_cost", lambda c: None)
    monkeypatch.setattr(orc, "check_run_budget", lambda c: None)

    def _boom(**kw):
        raise RuntimeError("ledger disk full")

    monkeypatch.setattr(orc, "append_cost_ledger_row", _boom)
    judge = scd._SemanticContradictionJudge()

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.002},
                "choices": [{"message": {"content": '{"verdict": "NEUTRAL", "confidence": 0.8}'}}],
            }

    monkeypatch.setattr(judge._client, "post", lambda *a, **k: _Resp())
    # Must NOT raise despite the ledger writer blowing up.
    label, conf = judge.judge("a", "b")
    assert label == "neutral"


# ───────────────────────── item 3: free-call token exclusion ─────────────────────────
def test_total_cost_usd_excludes_free_call_tokens():
    """A free call (record(free=True)) ledgers cost 0 and must NOT add a phantom imputed cost to
    the in-memory usage summary, while its tokens ARE still counted for token reporting."""
    ut = UsageTracker(session_id="fx11b-free-test")
    ut.record("paid", input_tokens=1000, output_tokens=1000)
    paid_only = ut.total_cost_usd
    assert paid_only > 0, "a paid call should impute a non-zero cost"

    ut.record("free_loopback", input_tokens=5000, output_tokens=5000, free=True)
    # The free call must NOT increase the imputed cost.
    assert ut.total_cost_usd == pytest.approx(paid_only), (
        "free-call tokens must not feed the imputed total_cost_usd"
    )
    # But tokens ARE still reported (honest token accounting).
    assert ut.total_input_tokens == 6000
    assert ut.total_output_tokens == 6000
    assert ut.total_free_input_tokens == 5000
    assert ut.total_free_output_tokens == 5000


def test_all_free_calls_impute_zero_cost():
    """A tracker of ONLY free calls reports zero imputed cost (the loopback 'operator is free' case)."""
    ut = UsageTracker(session_id="fx11b-allfree-test")
    ut.record("free1", input_tokens=2000, output_tokens=3000, free=True)
    ut.record("free2", input_tokens=1000, output_tokens=1500, free=True)
    assert ut.total_cost_usd == pytest.approx(0.0)
    assert ut.total_input_tokens == 3000  # reporting intact


def test_api_reported_cost_still_wins_over_imputation():
    """The free-token exclusion only touches the imputed fallback; an api-reported cost still
    takes precedence (FX-11b must not regress the paid-cost path)."""
    ut = UsageTracker(session_id="fx11b-api-test")
    ut.record("paid_api", input_tokens=10, output_tokens=10, api_cost=0.5)
    assert ut.total_cost_usd == pytest.approx(0.5)


# ───────────────────────── FX-11c (#1136): ledger row precedes budget check ─────────────────────────
def test_nli_ledger_row_written_before_budget_breach(monkeypatch):
    """FX-11c: a budget-BREACHING NLI call is billed to the run accumulator (_add_run_cost) before
    the budget check; the ledger row must therefore be written BEFORE check_run_budget raises, else
    the breaching call is billed-but-unledgered (ledger < budget — the exact drift FX-11 fixes)."""
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(orc, "check_family_segregation", lambda **k: None)
    monkeypatch.setattr(orc, "current_run_id", lambda: "run-breach")
    monkeypatch.setattr(orc, "_add_run_cost", lambda c: None)

    def _breach(_):
        raise BudgetExceededError("run budget cap reached")

    monkeypatch.setattr(orc, "check_run_budget", _breach)
    captured: list[dict] = []
    monkeypatch.setattr(orc, "append_cost_ledger_row", lambda **kw: captured.append(kw) or 0.0)
    judge = scd._SemanticContradictionJudge()

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "usage": {"prompt_tokens": 50, "completion_tokens": 10, "cost": 0.001},
                "choices": [{"message": {"content": '{"verdict": "CONTRADICT", "confidence": 0.9}'}}],
            }

    monkeypatch.setattr(judge._client, "post", lambda *a, **k: _Resp())
    # The breaching call must re-raise BudgetExceededError (keep-partial caller path)...
    with pytest.raises(BudgetExceededError):
        judge.judge("a", "b")
    # ...AND the ledger row must already have been written (before the budget check raised).
    assert len(captured) == 1, "ledger row must be written BEFORE check_run_budget raises"
    assert captured[0]["call_type"] == "nli_conflict_judge"
    assert captured[0]["cost_usd"] == pytest.approx(0.001)
