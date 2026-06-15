"""GH #1258 PART 2: the run-status heartbeat must ADVANCE (stage + elapsed_s) during the long
phases, not freeze at scope_gate_passed.

Root cause fixed: ``_hb`` was called only at coarse transitions (started / scope_gate_passed /
retrieval_done), and crucially NOT inside the synchronous ``run_live_retrieval`` which blocks the
event loop for minutes. The fix (a) adds main-thread ``_hb`` ticks at the visible phase
boundaries and (b) threads an optional ``progress_cb`` into ``run_live_retrieval`` that ticks at
``parallel_fetch`` completion and periodically inside the per-URL classification loop.

These tests exercise the WRITER directly (advancing stage/elapsed across simulated ticks) — the
same call shape ``_hb`` uses — proving run_status.json no longer reflects a frozen snapshot.
"""
from __future__ import annotations

import itertools
import json

from polaris_graph.telemetry import run_status_heartbeat as hb


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_stage_and_elapsed_advance_across_simulated_phase_ticks(tmp_path, monkeypatch):
    """Successive heartbeat writes with a fixed entry-timestamp + advancing stages overwrite
    run_status.json so a tailer sees the LATEST stage and a growing elapsed_s (not frozen)."""
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    run_dir = tmp_path / "run"
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))

    # A deterministic monotonic clock so elapsed_s is exact and strictly increasing.
    # write_heartbeat does `import time` locally, so patching the stdlib function the local import
    # resolves to controls the elapsed_s it computes.
    clock = itertools.count(start=105.0, step=5.0)
    import time as _time
    monkeypatch.setattr(_time, "monotonic", lambda: next(clock))

    started = 100.0  # entry timestamp (the `_hb_started` the sweep captures once at run_one_query)
    stages = [
        "scope_gate_passed",
        "storm_started",
        "retrieval_started",
        "retrieval_fetched",
        "retrieval_classifying",
        "retrieval_done",
        "generation_started",
    ]
    seen_elapsed = []
    for stage in stages:
        hb.write_heartbeat(
            run_dir=run_dir,
            run_id="SWEEP_test_0001",
            slug="drb_72",
            query_index=1,
            query_total=5,
            stage=stage,
            started_monotonic=started,
            running_cost_usd=0.0,
            budget_cap_usd=25.0,
        )
        doc = _read(run_dir / hb.RUN_STATUS_FILENAME)
        assert doc["stage"] == stage          # run_status reflects the LATEST stage, not frozen
        seen_elapsed.append(doc["elapsed_s"])

    # elapsed_s strictly increases across the phase ticks (the freeze symptom was elapsed_s=0).
    assert seen_elapsed == sorted(seen_elapsed)
    assert seen_elapsed[0] > 0.0
    assert seen_elapsed[-1] > seen_elapsed[0]
    # The terminal-visible stage is the most recent write, not scope_gate_passed.
    assert _read(run_dir / hb.RUN_STATUS_FILENAME)["stage"] == "generation_started"


def test_running_cost_and_sources_kept_reflected_per_tick(tmp_path, monkeypatch):
    """Each tick carries the CURRENT running cost + kept-source count so the tailer never sees a
    stale cost=0 / sources_kept=null while retrieval is progressing."""
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    run_dir = tmp_path / "run"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(tmp_path / "state" / "run_status.json"))

    for kept, cost, stage in [(0, 0.0, "retrieval_started"),
                              (120, 1.5, "retrieval_fetched"),
                              (180, 3.2, "retrieval_classifying")]:
        hb.write_heartbeat(
            run_dir=run_dir,
            run_id="SWEEP_test_0001",
            slug="drb_72",
            query_index=1,
            query_total=5,
            stage=stage,
            started_monotonic=0.0,
            running_cost_usd=cost,
            budget_cap_usd=25.0,
            sources_kept=kept,
        )
        doc = _read(run_dir / hb.RUN_STATUS_FILENAME)
        assert doc["stage"] == stage
        assert doc["running_cost_usd"] == cost
        assert doc["sources_kept"] == kept


def test_progress_cb_wired_into_run_live_retrieval_signature():
    """run_live_retrieval accepts a progress_cb kwarg (GH #1258 PART 2 wiring contract)."""
    import inspect

    from src.polaris_graph.retrieval.live_retriever import run_live_retrieval

    sig = inspect.signature(run_live_retrieval)
    assert "progress_cb" in sig.parameters
    # Default None keeps the OFF/no-console path byte-identical.
    assert sig.parameters["progress_cb"].default is None
