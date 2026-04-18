"""
BUG-M-206 + BUG-N-301 regression tests:
  M-206: per-run cost ledger copy written to <run_dir>/cost_ledger.jsonl
  N-301: OpenRouterClient picks up ambient run_id when no session_id passed

Pre-fix, logs/pg_cost_ledger.jsonl was a single global append-only file.
Consumers could not correlate a run's cost stream to its run_id without
grepping the whole thing. Pipeline A call sites instantiated
OpenRouterClient without session_id, so ledger entries had empty
session_id fields.

Post-fix (deep-dive R8+R11):
  - set_current_run_id(run_id) at the top of run_one_query threads
    the run_id into every downstream OpenRouterClient via ambient
    state (no signature changes).
  - write_per_run_cost_ledger() filters the global ledger by
    session_id and writes to <run_dir>/cost_ledger.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────
# N-301: ambient run_id
# ─────────────────────────────────────────────────────────────────

def test_n301_openrouter_client_picks_up_ambient_run_id(tmp_path, monkeypatch) -> None:
    """If set_current_run_id(x) is set, a new OpenRouterClient with no
    session_id=... kwarg uses x as its effective session_id."""
    from src.polaris_graph.llm import openrouter_client as mod
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    # Force a fresh API key read (module already loaded)
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", "sk-test")

    mod.set_current_run_id("RUN_XYZ_123")
    try:
        client = mod.OpenRouterClient(model="test/model")
        assert client.usage.session_id == "RUN_XYZ_123"
    finally:
        mod.set_current_run_id(None)


def test_n301_explicit_session_id_wins_over_ambient(monkeypatch) -> None:
    """Explicit session_id=... still wins — ambient is fallback only."""
    from src.polaris_graph.llm import openrouter_client as mod
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", "sk-test")
    mod.set_current_run_id("ambient_run")
    try:
        client = mod.OpenRouterClient(
            model="test/model", session_id="explicit_run",
        )
        assert client.usage.session_id == "explicit_run"
    finally:
        mod.set_current_run_id(None)


def test_n301_no_ambient_no_explicit_yields_empty(monkeypatch) -> None:
    """When neither is set, session_id defaults to empty string
    (prior behavior preserved)."""
    from src.polaris_graph.llm import openrouter_client as mod
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", "sk-test")
    mod.set_current_run_id(None)
    client = mod.OpenRouterClient(model="test/model")
    assert client.usage.session_id == ""


def test_n301_current_run_id_getter() -> None:
    from src.polaris_graph.llm import openrouter_client as mod
    mod.set_current_run_id(None)
    assert mod.current_run_id() is None
    mod.set_current_run_id("RUN_ABC")
    try:
        assert mod.current_run_id() == "RUN_ABC"
    finally:
        mod.set_current_run_id(None)


# ─────────────────────────────────────────────────────────────────
# M-206: per-run ledger copy
# ─────────────────────────────────────────────────────────────────

def test_m206_per_run_ledger_writer_filters_by_session_id(
    tmp_path, monkeypatch,
) -> None:
    """write_per_run_cost_ledger filters the global ledger by session_id
    and writes a per-run copy."""
    from scripts.run_honest_sweep_r3 import write_per_run_cost_ledger

    # Set up a fake global ledger with 3 runs' entries interleaved
    global_ledger = tmp_path / "pg_cost_ledger.jsonl"
    entries = [
        {"session_id": "run_A", "call_type": "planner", "cost_usd": 0.01},
        {"session_id": "run_B", "call_type": "generator", "cost_usd": 0.02},
        {"session_id": "run_A", "call_type": "judge", "cost_usd": 0.005},
        {"session_id": "run_C", "call_type": "planner", "cost_usd": 0.01},
        {"session_id": "run_A", "call_type": "generator", "cost_usd": 0.03},
    ]
    with open(global_ledger, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    monkeypatch.setenv("PG_COST_LEDGER_PATH", str(global_ledger))

    run_dir = tmp_path / "run_A_dir"
    run_dir.mkdir()

    n = write_per_run_cost_ledger(run_dir, "run_A")
    assert n == 3, f"Expected 3 entries for run_A, got {n}"
    out = run_dir / "cost_ledger.jsonl"
    assert out.exists()
    # Only run_A entries should be in the per-run file
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        assert json.loads(line)["session_id"] == "run_A"


def test_m206_per_run_ledger_empty_global_returns_zero(
    tmp_path, monkeypatch,
) -> None:
    """No global ledger yet (fresh install) → write 0 entries, no crash."""
    from scripts.run_honest_sweep_r3 import write_per_run_cost_ledger
    missing = tmp_path / "nothing.jsonl"
    monkeypatch.setenv("PG_COST_LEDGER_PATH", str(missing))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    n = write_per_run_cost_ledger(run_dir, "any_run_id")
    assert n == 0


def test_m206_per_run_ledger_no_matching_entries(
    tmp_path, monkeypatch,
) -> None:
    """Global ledger exists but has no entries for this run_id → writes
    an empty file, no crash."""
    from scripts.run_honest_sweep_r3 import write_per_run_cost_ledger
    global_ledger = tmp_path / "pg_cost_ledger.jsonl"
    global_ledger.write_text(
        json.dumps({"session_id": "other_run", "cost_usd": 0.01}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PG_COST_LEDGER_PATH", str(global_ledger))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    n = write_per_run_cost_ledger(run_dir, "missing_run")
    assert n == 0
    assert (run_dir / "cost_ledger.jsonl").exists()


def test_m206_per_run_ledger_handles_malformed_entries(
    tmp_path, monkeypatch,
) -> None:
    """Malformed lines in the global ledger are skipped, not crash."""
    from scripts.run_honest_sweep_r3 import write_per_run_cost_ledger
    global_ledger = tmp_path / "pg_cost_ledger.jsonl"
    with open(global_ledger, "w", encoding="utf-8") as f:
        f.write(json.dumps({"session_id": "my_run", "cost_usd": 0.01}) + "\n")
        f.write("this is not json\n")
        f.write(json.dumps({"session_id": "my_run", "cost_usd": 0.02}) + "\n")
    monkeypatch.setenv("PG_COST_LEDGER_PATH", str(global_ledger))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    n = write_per_run_cost_ledger(run_dir, "my_run")
    assert n == 2  # malformed line skipped


def test_m206_orchestrator_sets_ambient_run_id() -> None:
    """Source check: run_one_query calls set_current_run_id(run_id)."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    assert "set_current_run_id(run_id)" in source, (
        "Orchestrator must set ambient run_id for cost-ledger tagging"
    )


def test_m206_orchestrator_calls_per_run_ledger_writer() -> None:
    """Source check: write_per_run_cost_ledger is called in the cleanup
    path so abort + error + success paths all emit per-run ledger."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    assert "write_per_run_cost_ledger(run_dir, run_id)" in source, (
        "Orchestrator must write per-run ledger before returning"
    )
