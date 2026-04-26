"""Tests for src/polaris_graph/audit_ir/v30_runner.py.

The V30 sweep is real-world expensive (~2h25m, $0.0074, 472 fetches).
We test the runner using a tiny stub script that simulates the V30
phase-log pattern, never the real sweep.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from textwrap import dedent

import pytest

from src.polaris_graph.audit_ir import (
    Job,
    JobControl,
    JobQueue,
    JobWorker,
    register_runner,
)
from src.polaris_graph.audit_ir.v30_runner import (
    V30_PHASES,
    V30JobRunner,
    V30RunnerConfig,
    _PHASE_PCT,
    make_default_v30_runner,
)
from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests


@pytest.fixture(autouse=True)
def _clean_state():
    _reset_runners_for_tests()
    yield
    _reset_runners_for_tests()


# ---------------------------------------------------------------------------
# Phase classification — pure, no subprocess
# ---------------------------------------------------------------------------


def test_classify_phase_recognizes_canonical_lines() -> None:
    cases = [
        ("[2026-04-26 12:00:00] scope_gate: decision=accept", "scope_gate"),
        ("Phase 2: live retrieval starting (476 sources expected)", "retrieval_started"),
        ("Phase 2 complete: 472 fetched / 16 failed", "retrieval_done"),
        ("corpus_adequacy: decision=proceed", "adequacy_gate"),
        ("corpus_approval: approved=True", "approval_gate"),
        ("Phase 3: generation starting", "generation_started"),
        ("Phase 4: strict_verify pass", "strict_verify"),
        ("Phase 5: evaluator_gate=pass", "evaluator_gate"),
        ("V30 Phase 1: M-56 deterministic fetch", "v30_phase1"),
        ("V30 Phase 2: M-58 slot-bound generation", "v30_phase2"),
        ("live_qwen_judge: parse_ok=True", "qwen_judge"),
        ("Wall time: 8696.7 seconds", "complete"),
        ("Random unrelated line", None),
    ]
    for line, expected in cases:
        assert V30JobRunner._classify_phase(line) == expected, line


def test_phase_pct_monotonic() -> None:
    """Progress percentages must increase across phases."""
    pcts = [pct for _, pct, _ in V30_PHASES]
    assert pcts == sorted(pcts)
    assert pcts[0] > 0
    assert pcts[-1] == 100.0


# ---------------------------------------------------------------------------
# Subprocess integration — using a stub script that mimics V30 phase log
# ---------------------------------------------------------------------------


def _write_stub_sweep(tmp_path: Path, exit_code: int = 0, sleep_per_phase: float = 0.05) -> Path:
    """Build a fake sweep script that emits V30 phase markers then exits."""
    out_root_arg = tmp_path / "out"
    script = tmp_path / "stub_sweep.py"
    script.write_text(dedent(f"""
        import argparse, sys, time, os, json
        ap = argparse.ArgumentParser()
        ap.add_argument("--only", required=True)
        ap.add_argument("--out-root", required=True)
        a = ap.parse_args()
        slug = a.only
        out_root = a.out_root
        domain = "stubdomain"
        slug_dir = os.path.join(out_root, domain, slug)
        os.makedirs(slug_dir, exist_ok=True)
        markers = [
            "scope_gate: decision=accept",
            "Phase 2: live retrieval starting",
            "Phase 2 complete",
            "corpus_adequacy: decision=proceed",
            "corpus_approval: approved=True",
            "Phase 3: generation starting",
            "Phase 4: strict_verify pass",
            "Phase 5: evaluator_gate=pass",
            "V30 Phase 1: M-56",
            "V30 Phase 2: M-58",
            "live_qwen_judge: parse_ok=True",
            "Wall time: 1.0 seconds",
        ]
        for m in markers:
            print(m, flush=True)
            time.sleep({sleep_per_phase})
        # Write a stub manifest so artifact resolution succeeds.
        with open(os.path.join(slug_dir, "manifest.json"), "w") as f:
            json.dump({{"run_id": "stub", "slug": slug, "status": "ok"}}, f)
        sys.exit({exit_code})
    """), encoding="utf-8")
    return script


def _make_runner(tmp_path: Path, sweep_script: Path) -> V30JobRunner:
    return V30JobRunner(V30RunnerConfig(
        repo_root=tmp_path,
        sweep_script=sweep_script,
        out_root=tmp_path / "out",
        python_bin=sys.executable,
        poll_interval_s=0.05,
        cancel_grace_s=2.0,
    ))


def test_runner_completes_and_returns_artifact_dir(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite")
    runner = _make_runner(tmp_path, _write_stub_sweep(tmp_path))
    register_runner(runner)

    job = queue.enqueue("v30_clinical", {"slug": "test_slug"})
    worker = JobWorker(queue, poll_interval_s=0.05)
    completed = worker.run_one()

    assert completed is not None
    assert completed.status == "completed", f"got {completed.status}: {completed.error}"
    assert completed.artifact_dir is not None
    artifact_dir = Path(completed.artifact_dir)
    assert artifact_dir.is_dir()
    assert (artifact_dir / "manifest.json").exists()
    assert artifact_dir.name == "test_slug"


def test_runner_emits_progress_checkpoints(tmp_path: Path) -> None:
    """Verify per-phase checkpoints are recorded as the subprocess runs."""
    queue = JobQueue(tmp_path / "jobs.sqlite")
    # Slow phases so we can observe intermediate state
    runner = _make_runner(tmp_path, _write_stub_sweep(tmp_path, sleep_per_phase=0.1))
    register_runner(runner)

    job = queue.enqueue("v30_clinical", {"slug": "test_slug"})

    # Run the worker in a thread so we can observe progress from main.
    captured_pcts: list[float] = []
    captured_phases: list[str] = []

    def _observe() -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            current = queue.get(job.job_id)
            if current is None:
                continue
            if current.checkpoint and current.checkpoint.get("phase") not in captured_phases:
                captured_phases.append(current.checkpoint["phase"])
                captured_pcts.append(current.progress_pct)
            if current.status in {"completed", "cancelled", "failed"}:
                break
            time.sleep(0.02)

    observer = threading.Thread(target=_observe, daemon=True)
    observer.start()

    worker = JobWorker(queue, poll_interval_s=0.02)
    completed = worker.run_one()
    observer.join(timeout=2.0)

    assert completed.status == "completed"
    # Should have observed multiple progress phases
    assert len(captured_phases) >= 3
    # Progress is monotonically increasing
    for a, b in zip(captured_pcts, captured_pcts[1:]):
        assert b >= a, f"non-monotonic: {captured_pcts}"


def test_runner_fails_when_subprocess_exits_nonzero(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite")
    runner = _make_runner(tmp_path, _write_stub_sweep(tmp_path, exit_code=42))
    register_runner(runner)

    queue.enqueue("v30_clinical", {"slug": "fail_slug"})
    worker = JobWorker(queue, poll_interval_s=0.05)
    failed = worker.run_one()

    assert failed.status == "failed"
    assert "rc=42" in (failed.error or "")


def test_runner_fails_when_slug_missing(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite")
    runner = _make_runner(tmp_path, _write_stub_sweep(tmp_path))
    register_runner(runner)

    queue.enqueue("v30_clinical", {})  # no slug
    worker = JobWorker(queue, poll_interval_s=0.05)
    failed = worker.run_one()

    assert failed.status == "failed"
    assert "slug is required" in (failed.error or "")


def test_runner_fails_when_sweep_script_missing(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite")
    bogus = tmp_path / "does_not_exist.py"
    runner = _make_runner(tmp_path, bogus)
    register_runner(runner)

    queue.enqueue("v30_clinical", {"slug": "test"})
    worker = JobWorker(queue, poll_interval_s=0.05)
    failed = worker.run_one()

    assert failed.status == "failed"
    assert "Sweep script missing" in (failed.error or "")


def test_cancel_terminates_subprocess(tmp_path: Path) -> None:
    """When cancel_requested fires, the runner SIGTERMs the subprocess."""
    queue = JobQueue(tmp_path / "jobs.sqlite")
    # Long-running stub so we have time to cancel mid-run.
    runner = _make_runner(tmp_path, _write_stub_sweep(tmp_path, sleep_per_phase=0.5))
    register_runner(runner)

    job = queue.enqueue("v30_clinical", {"slug": "cancel_slug"})

    worker = JobWorker(queue, poll_interval_s=0.02)
    worker.start()
    try:
        # Wait for the worker to claim + start running.
        deadline = time.time() + 5.0
        while time.time() < deadline:
            current = queue.get(job.job_id)
            if current and current.status == "running" and current.progress_pct > 0:
                break
            time.sleep(0.02)
        assert current.status == "running"

        # Cancel and wait for the runner to honor.
        queue.request_cancel(job.job_id)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            current = queue.get(job.job_id)
            if current and current.status == "cancelled":
                break
            time.sleep(0.05)
        assert current.status == "cancelled", f"expected cancelled, got {current.status}"
        # Cancel should have fired BEFORE 100% (subprocess was terminated).
        assert current.progress_pct < 100.0
    finally:
        worker.stop(join_timeout=5.0)


# ---------------------------------------------------------------------------
# Default factory + registration
# ---------------------------------------------------------------------------


def test_make_default_v30_runner_resolves_canonical_paths() -> None:
    runner = make_default_v30_runner()
    assert runner.template_id == "v30_clinical"
    assert runner._config.sweep_script.name == "run_full_scale_v30_phase2.py"
    assert runner._config.out_root.name == "polaris_v30_jobs"


def test_v30_runner_registers_in_inspector_router_listing() -> None:
    """When the inspector router boots, 'v30_clinical' must appear in
    available_templates so the UI can offer it."""
    from src.polaris_graph.audit_ir.inspector_router import _ensure_runners_registered
    _ensure_runners_registered()
    from src.polaris_graph.audit_ir import list_runners
    assert "v30_clinical" in list_runners()
    assert "mock" in list_runners()
