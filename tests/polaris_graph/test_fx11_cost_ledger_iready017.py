"""FX-11 (I-ready-017 #1116): cost_ledger SINGLE canonical accumulator + role-call rows.

BUG-10: cumulative_cost_usd was the per-instance total (non-monotonic across clients sharing a
run; the UI under-reported). Now every writer (generator / judge / role / blank-retry) routes the
SAME process-global, lock-protected, per-session accumulator (`_LEDGER_CUM_BY_SESSION`), keyed by
the run id, so cumulative is a single rising run total.
BUG-10b: the four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger rows;
RecordingTransport now appends one inclusive row per role call.
Codex iter-1 P1: under the parallel four-role ThreadPoolExecutor workers (each copy_context() —
inheriting the run id — and reset their OWN `_RUN_COST_CTX`), reading cumulative from
`current_run_cost()` made role-row cumulatives per-worker / non-monotonic. The shared accumulator
(bump + file append under ONE RLock) makes the PERSISTED FILE non-decreasing in write order.
Codex iter-1 P2a: the blank-verdict retry path billed the run budget but wrote no ledger row.
Codex iter-1 P2b: a genuinely-free call (operator loopback) ledgered a phantom paid-rate estimate.
Codex iter-1 P2c: the best-effort write-failure test never actually forced a failure.

Cost-accounting only — no faithfulness/strict_verify/4-role-decision change. Offline, no network.
"""
from __future__ import annotations

import concurrent.futures
import contextvars
import json

import pytest

from src.polaris_graph.llm import openrouter_client as orc
from src.polaris_graph.llm.openrouter_client import (
    UsageTracker,
    _add_run_cost,
    current_run_cost,
    reset_ledger_cumulative,
    reset_run_cost,
    set_current_run_id,
)
from src.polaris_graph.roles.role_pipeline import RecordingTransport
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

_SID = "FX11_TEST"


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    p = tmp_path / "cost_ledger.jsonl"
    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", p)
    reset_run_cost()
    # The accumulator is PROCESS-GLOBAL and persists across tests; reset it so a re-used run id
    # starts fresh (production run ids are unique per run and never need this).
    reset_ledger_cumulative(_SID)
    set_current_run_id(_SID)
    try:
        yield p
    finally:
        reset_run_cost()
        reset_ledger_cumulative(_SID)
        set_current_run_id(None)


def _rows(p):
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


class _FakeTransport:
    def complete(self, request: RoleRequest) -> RoleResponse:
        return RoleResponse(
            raw_text="ok",
            served_model=request.model_slug,
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


def test_bug10_cumulative_is_monotonic_run_total(tmp_ledger):
    usage = UsageTracker(session_id=_SID)
    # Simulate the reordered real path: _add_run_cost BEFORE record, once per call.
    for cost in (0.5, 0.3, 0.2):
        _add_run_cost(cost)
        usage.record(call_type="generate", input_tokens=10, output_tokens=5, api_cost=cost)
    rows = [r for r in _rows(tmp_ledger) if r.get("session_id") == _SID]
    cums = [r["cumulative_cost_usd"] for r in rows]
    assert cums == sorted(cums), f"cumulative must be NON-DECREASING, got {cums}"
    assert cums == [0.5, 0.8, 1.0]
    assert abs(cums[-1] - round(current_run_cost(), 4)) < 1e-9, "final == run total"
    # generate rows no longer equal their OWN cost after >1 call (the old per-instance bug)
    assert rows[-1]["cumulative_cost_usd"] != rows[-1]["cost_usd"]


def test_bug10b_role_call_writes_inclusive_ledger_row(tmp_ledger):
    rt = RecordingTransport(_FakeTransport())
    rt.complete(RoleRequest(role="mirror", model_slug="z-ai/glm-5.1"))
    rt.complete(RoleRequest(role="sentinel", model_slug="minimax/minimax-m2"))
    role_rows = [r for r in _rows(tmp_ledger) if str(r.get("call_type", "")).startswith("role:")]
    assert len(role_rows) == 2, "each four-role verifier call must write ONE ledger row"
    assert {r["call_type"] for r in role_rows} == {"role:mirror", "role:sentinel"}
    cums = [r["cumulative_cost_usd"] for r in role_rows]
    assert cums == sorted(cums), "role-row cumulative must be NON-DECREASING"
    assert abs(cums[-1] - round(current_run_cost(), 4)) < 1e-9, "inclusive of both calls"
    assert role_rows[0]["cost_usd"] > 0, "non-zero role cost (floor guarantees > 0)"
    assert {r["session_id"] for r in role_rows} == {_SID}


def test_bug10b_role_cumulative_monotonic_under_parallel_workers(tmp_ledger):
    """Codex iter-1 P1 repro: replicate sweep_integration's EXACT fan-out —
    ThreadPoolExecutor + a per-worker contextvars.copy_context() snapshot (which INHERITS
    `_CURRENT_RUN_ID_CTX` = the run id), each worker reset_run_cost()-ing ONLY its own copy.
    With the OLD cumulative = current_run_cost(), each worker's run-cost restarts at 0, so the
    interleaved role rows are per-worker / NON-monotonic. The shared per-session accumulator (bump
    + append under one RLock) keeps every persisted role row's cumulative non-decreasing in WRITE
    order and tagged with the ONE shared run id.
    """
    n_workers, calls_per_worker = 6, 5

    def _worker(_widx):
        reset_run_cost()  # zero ONLY this context copy's _RUN_COST_CTX (mirrors sweep_integration)
        rt = RecordingTransport(_FakeTransport())
        for _ in range(calls_per_worker):
            rt.complete(RoleRequest(role="mirror", model_slug="z-ai/glm-5.1"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [
            pool.submit(contextvars.copy_context().run, _worker, w) for w in range(n_workers)
        ]
        for f in futs:
            f.result()

    role_rows = [r for r in _rows(tmp_ledger) if str(r.get("call_type", "")).startswith("role:")]
    assert len(role_rows) == n_workers * calls_per_worker
    # ALL rows belong to the ONE shared (inherited) run id — NOT per-worker / "no_run_id".
    assert {r["session_id"] for r in role_rows} == {_SID}
    cums = [r["cumulative_cost_usd"] for r in role_rows]
    assert cums == sorted(cums), (
        f"GLOBAL role-row cumulative must be NON-DECREASING in file order under parallel "
        f"workers, got {cums}"
    )
    # Final cumulative == the GLOBAL total of every role cost (per-worker current_run_cost() —
    # the old approach — could only ever have shown one worker's share).
    total = sum(r["cost_usd"] for r in role_rows)
    assert abs(cums[-1] - round(total, 4)) < 1e-3
    assert cums[-1] > role_rows[0]["cost_usd"], "the global total exceeds any single call's cost"


def test_p2a_blank_attempt_costs_are_ledgered(tmp_ledger):
    """P2a: the blank-verdict retry path adds run-budget cost; it must also write a ledger row so
    the persisted total stays == the run-budget total. We exercise the canonical writer directly
    with the same call_type the retry path uses (the live retry path needs a real HTTP 200 blank).
    """
    before = round(current_run_cost(), 4)
    cum = orc.append_cost_ledger_row(
        session_id=orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
        call_type="role:mirror:blank_attempt",
        cost_usd=0.0123,
        input_tokens=80,
        output_tokens=0,
    )
    rows = [r for r in _rows(tmp_ledger) if r.get("call_type") == "role:mirror:blank_attempt"]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 0.0123
    assert abs(rows[0]["cumulative_cost_usd"] - cum) < 1e-9
    # The writer bumps the LEDGER accumulator (not _RUN_COST_CTX — the retry path calls
    # _add_run_cost separately), so current_run_cost is unchanged by the writer alone.
    assert round(current_run_cost(), 4) == before


def test_p2b_free_call_ledgers_zero_not_phantom_estimate(tmp_ledger):
    """P2b: a free call (operator loopback passes free=True) must ledger cost 0, NOT a phantom
    paid-rate token estimate; and it must not advance the cumulative."""
    usage = UsageTracker(session_id=_SID)
    usage.record(call_type="loopback", input_tokens=5000, output_tokens=5000, api_cost=0.0, free=True)
    rows = [r for r in _rows(tmp_ledger) if r.get("call_type") == "loopback"]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 0.0, "free call must ledger 0, not a token-based estimate"
    assert rows[0]["cumulative_cost_usd"] == 0.0
    # Control: the SAME tokens WITHOUT free=True DO get the imputation backstop (invariant #6).
    usage.record(call_type="paid_no_cost", input_tokens=5000, output_tokens=5000, api_cost=0.0)
    paid = [r for r in _rows(tmp_ledger) if r.get("call_type") == "paid_no_cost"]
    assert paid and paid[0]["cost_usd"] > 0.0, "paid call w/o reported cost still imputes (#6)"


def test_p2c_ledger_write_failure_never_breaks_role_call(tmp_path, monkeypatch):
    """P2c: FORCE a real write failure (point the ledger UNDER an existing file so .parent.mkdir
    raises), then prove the role call still returns and no partial row is persisted."""
    reset_run_cost()
    reset_ledger_cumulative(_SID)
    set_current_run_id(_SID)
    blocker = tmp_path / "blocker_is_a_file"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "sub" / "cost_ledger.jsonl"  # parent path traverses through a FILE
    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", bad)
    try:
        rt = RecordingTransport(_FakeTransport())
        resp = rt.complete(RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b"))
        assert resp.raw_text == "ok", "best-effort ledger failure must NOT break the role call"
        assert not bad.exists(), "no ledger file should have been created on the bad path"
    finally:
        reset_run_cost()
        reset_ledger_cumulative(_SID)
        set_current_run_id(None)
