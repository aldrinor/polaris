"""FX-11 (I-ready-017): cost_ledger single canonical accumulator + role-call rows.

BUG-10: cumulative_cost_usd was the per-instance total (non-monotonic across clients
sharing a run, under-reported the UI). Now it is the shared, monotonic run total
(current_run_cost(), inclusive — _add_run_cost runs before usage.record).
BUG-10b: the four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger rows;
RecordingTransport now appends one row per role call.

Cost-accounting only — no faithfulness/strict_verify/4-role-decision change. Offline,
no network: a tmp ledger + direct UsageTracker.record + a fake RoleTransport.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.llm import openrouter_client as orc
from src.polaris_graph.llm.openrouter_client import (
    UsageTracker,
    _add_run_cost,
    current_run_cost,
    reset_run_cost,
    set_current_run_id,
)
from src.polaris_graph.roles.role_pipeline import RecordingTransport
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    p = tmp_path / "cost_ledger.jsonl"
    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", p)
    reset_run_cost()
    set_current_run_id("FX11_TEST")
    try:
        yield p
    finally:
        reset_run_cost()
        set_current_run_id(None)


def _rows(p):
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_bug10_cumulative_is_monotonic_run_total(tmp_ledger):
    usage = UsageTracker(session_id="FX11_TEST")
    # Simulate the reordered real path: _add_run_cost BEFORE record, once per call.
    for cost in (0.5, 0.3, 0.2):
        _add_run_cost(cost)
        usage.record(call_type="generate", input_tokens=10, output_tokens=5, api_cost=cost)
    rows = [r for r in _rows(tmp_ledger) if r.get("session_id") == "FX11_TEST"]
    cums = [r["cumulative_cost_usd"] for r in rows]
    assert cums == sorted(cums), f"cumulative must be NON-DECREASING, got {cums}"
    assert abs(cums[-1] - round(current_run_cost(), 4)) < 1e-9, "final == run total"
    assert abs(cums[-1] - 1.0) < 1e-9
    # generate rows no longer equal their OWN cost after >1 call (the old per-instance bug)
    assert rows[-1]["cumulative_cost_usd"] != rows[-1]["cost_usd"]


class _FakeTransport:
    def complete(self, request: RoleRequest) -> RoleResponse:
        return RoleResponse(
            raw_text="ok",
            served_model=request.model_slug,
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


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


def test_bug10b_ledger_write_failure_never_breaks_role_call(tmp_path, monkeypatch):
    # Point the ledger at an un-writable path; the role call must STILL succeed (best-effort).
    reset_run_cost()
    set_current_run_id("FX11_TEST")
    bad = tmp_path / "nonexistent_dir_seg" / "x" / "cost_ledger.jsonl"
    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", bad)
    monkeypatch.setattr(
        orc, "_impute_cost_from_tokens", lambda *a, **k: 0.001, raising=False,
    )
    rt = RecordingTransport(_FakeTransport())
    # Even if the write path were to fail, complete() must return the response.
    resp = rt.complete(RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b"))
    assert resp.raw_text == "ok"
    reset_run_cost()
    set_current_run_id(None)
