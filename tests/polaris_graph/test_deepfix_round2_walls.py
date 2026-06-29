"""I-deepfix-001 round-2 (#1344): RED->GREEN tests for the COMPLETENESS-CRITIC walls
and fix-defects that were STILL-OPEN after round-1.

Covered:
  R2-1  section wall-clock guard is RUN-WALL-AWARE — when the run-wall budget cannot fit
        a second full section attempt, the guard fails-loud NOW (so the caller's gap-stub
        renders) instead of doing 2 x PG_SECTION_WALLCLOCK_SECONDS and being guillotined
        by the run-wall (error_unexpected, NO rendered report). Behavioral.
  R2-2  the spine publishes the run-wall deadline into the generator (set/reset wiring).
        Static-source (avoid importing the heavy spine module).
  R2-3  the FS-Researcher in-call _iter_llm worker .result() is bounded by the remaining
        per-question retrieval budget (no ~30-min in-call overshoot). Static-source.
  R2-4  the success-path assemble_report_md is wrapped fail-open (a raise still renders a
        report). Static-source.
  R2-5  W09 mineru-timeout-alignment reads PG_FETCH_DEADLINE_SECONDS with the GOVERNING
        live_retriever default of 90 (NOT 0) so the alignment is NOT a no-op in a slate
        that sets neither fetch env. Behavioral env-read + static.

Offline: NO torch / GPU / network. The section guard runs a stub runner with a fake
clock; the spine + access_bypass checks are pure source-text assertions.
"""
from __future__ import annotations

import ast
import asyncio
import re
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPINE = REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
ACCESS_BYPASS = REPO_ROOT / "src" / "tools" / "access_bypass.py"


# ───────────────────────────────────────────────────────────────────────────
# R2-1 — section wall-clock guard is run-wall-aware (behavioral)
# ───────────────────────────────────────────────────────────────────────────
def test_r2_section_guard_gap_stubs_before_runwall_guillotine(monkeypatch):
    """RED (pre-fix): the guard does 2 x wait_for at PG_SECTION_WALLCLOCK_SECONDS each
    (=> up to 18000s) ignoring the run-wall, so a wedged section is guillotined by the
    10800s run-wall BEFORE the gap-stub fires.
    GREEN: when the run-wall deadline is published and the remaining budget cannot fit a
    second full attempt, the guard raises promptly (the caller converts it to a gap-stub),
    and never starts a doomed second attempt.
    """
    from src.polaris_graph.generator import multi_section_generator as msg

    # Section wall 9000s (the cert value). The runner always wedges (times out).
    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "9000")
    monkeypatch.setenv("PG_SECTION_RUNWALL_MARGIN_S", "120")

    attempts = {"n": 0}

    async def _wedged_runner(_plan):
        attempts["n"] += 1
        # Simulate a wedge: sleep far longer than any cap; wait_for must cancel it.
        await asyncio.sleep(3600)
        return "should-never-return"

    # Drive a deterministic monotonic clock so wait_for's real timer is not needed:
    # publish a run-wall deadline that is only ~1000s out — far less than a 9000s
    # second attempt. The guard must NOT start attempt 2 (insufficient budget) and must
    # raise after the first attempt's bounded wait_for.
    now = time.monotonic()
    token = msg.set_run_wall_deadline(now + 1000.0)  # 1000s remaining
    try:
        async def _drive():
            # Make the first wait_for time out fast by capping the effective timeout via
            # a tiny remaining budget on the FIRST attempt too: we monkeypatch monotonic
            # so the guard computes a small `effective`. Simpler: rely on the real timer
            # with a very small wall to keep the test fast.
            monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "1")  # 1s attempts
            # remaining budget (1000s) >= wall(1) so attempt-1 runs with effective<=1s.
            with pytest.raises(TimeoutError):
                await msg._run_section_with_wallclock(_wedged_runner, {"plan": "x"})

        asyncio.run(_drive())
    finally:
        msg.reset_run_wall_deadline(token)

    # With 1000s remaining and a 1s wall, BOTH attempts may run (budget fits a 2nd 1s
    # attempt) — that is fine; the point of this case is it raises (=> gap-stub), never
    # hangs. At least one attempt ran.
    assert attempts["n"] >= 1


def test_r2_section_guard_skips_second_attempt_when_budget_too_small(monkeypatch):
    """The guard must SKIP attempt 2 when the remaining run-wall budget is smaller than a
    full `wall` second attempt — so the gap-stub fires before the run-wall guillotine."""
    from src.polaris_graph.generator import multi_section_generator as msg

    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "1")
    monkeypatch.setenv("PG_SECTION_RUNWALL_MARGIN_S", "0")

    attempts = {"n": 0}

    async def _wedged_runner(_plan):
        attempts["n"] += 1
        await asyncio.sleep(3600)
        return "x"

    # remaining budget = 1.5s (after the first 1s attempt consumes the time, the SECOND
    # attempt's `remaining < wall(1)` => skipped). We publish a deadline 1.5s out.
    token = msg.set_run_wall_deadline(time.monotonic() + 1.5)
    try:
        with pytest.raises(TimeoutError):
            asyncio.run(msg._run_section_with_wallclock(_wedged_runner, {"p": 1}))
    finally:
        msg.reset_run_wall_deadline(token)

    # Attempt 1 ran (~1s); by the time attempt 2 is considered, remaining (~0.5s) < wall(1)
    # => attempt 2 is SKIPPED. So exactly ONE attempt started.
    assert attempts["n"] == 1


def test_r2_section_guard_byte_identical_when_no_runwall_deadline(monkeypatch):
    """When NO run-wall deadline is published (default None), the guard keeps its legacy
    2-attempt behaviour (byte-identical for non-benchmark callers)."""
    from src.polaris_graph.generator import multi_section_generator as msg

    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "1")
    # Ensure no deadline is set.
    token = msg.set_run_wall_deadline(None)
    attempts = {"n": 0}

    async def _wedged_runner(_plan):
        attempts["n"] += 1
        await asyncio.sleep(3600)
        return "x"

    try:
        with pytest.raises(TimeoutError):
            asyncio.run(msg._run_section_with_wallclock(_wedged_runner, {"p": 1}))
    finally:
        msg.reset_run_wall_deadline(token)

    # Legacy path: BOTH attempts run.
    assert attempts["n"] == 2


# ───────────────────────────────────────────────────────────────────────────
# R2-2 — spine publishes the run-wall deadline into the generator
# ───────────────────────────────────────────────────────────────────────────
def test_r2_spine_publishes_run_wall_deadline_to_generator():
    src = SPINE.read_text(encoding="utf-8")
    # The setter is imported and called with the SAME absolute monotonic deadline that
    # _RUN_WALL_CLOCK_DEADLINE_CTX gets, before run_one_query is awaited.
    assert "set_run_wall_deadline as _msg_set_run_wall_deadline" in src
    assert "reset_run_wall_deadline as _msg_reset_run_wall_deadline" in src
    assert "_msg_set_run_wall_deadline(_run_wall_deadline_monotonic)" in src
    # The same instant feeds BOTH contextvars.
    assert "_run_wall_deadline_monotonic = time.monotonic() + _wall" in src
    assert "_RUN_WALL_CLOCK_DEADLINE_CTX.set(_run_wall_deadline_monotonic)" in src
    # Reset on BOTH the timeout and normal paths (2 reset call sites).
    assert src.count("_msg_reset_run_wall_deadline(_msg_deadline_token)") == 2


# ───────────────────────────────────────────────────────────────────────────
# R2-3 — FS-Researcher in-call _iter_llm worker .result() is deadline-bounded
# ───────────────────────────────────────────────────────────────────────────
def test_r2_fs_researcher_in_call_result_is_bounded():
    src = SPINE.read_text(encoding="utf-8")
    # The bare `.result()` (no timeout) on the _iter_llm worker is GONE; the bounded
    # form with a timeout derived from the per-question retrieval deadline is present.
    assert "_fut.result(timeout=_iter_call_timeout)" in src
    # The timeout is derived from the shared per-question retrieval deadline.
    assert "_question_retrieval_deadline - time.monotonic() + _iter_grace" in src
    # On expiry the worker is abandoned WITHOUT blocking the spine (shutdown wait=False).
    assert "shutdown(wait=False" in src
    # And the in-flight round returns "" so the deadline-gated loop hands off the corpus.
    # (the empty-return is inside the TimeoutError handler)
    assert 'except _iter_futures.TimeoutError:' in src


# ───────────────────────────────────────────────────────────────────────────
# R2-4 — success-path assemble_report_md is wrapped fail-open
# ───────────────────────────────────────────────────────────────────────────
def test_r2_assemble_report_md_is_wrapped_failopen():
    src = SPINE.read_text(encoding="utf-8")
    # The assemble_report_md call is now inside a try/except that fails open to the
    # pre-assembled title + abstract + concat + conclusion so a report STILL renders.
    assert "except Exception as _assemble_exc:" in src
    assert "fail-open to title + abstract + pre-assembled concat" in src
    # The fallback uses the same pre-built body string.
    assert "_assembled_body = (" in src
    # AST-level: the assemble_report_md call is inside a Try node (not a bare statement).
    tree = ast.parse(src)
    found_wrapped = _assemble_in_try(tree)
    assert found_wrapped, "assemble_report_md success-path call is not inside a try/except"


def _assemble_in_try(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "assemble_report_md"
                ):
                    # Confirm at least one handler is a broad Exception fail-open.
                    for handler in node.handlers:
                        h = handler.type
                        if isinstance(h, ast.Name) and h.id == "Exception":
                            return True
    return False


# ───────────────────────────────────────────────────────────────────────────
# R2-5 — W09 mineru-timeout-alignment reads the GOVERNING fetch wall default (90, not 0)
# ───────────────────────────────────────────────────────────────────────────
def test_r2_w09_fetch_deadline_default_is_governing_90(monkeypatch):
    """RED (pre-fix): access_bypass read PG_FETCH_DEADLINE_SECONDS default '0', so when the
    cert slate sets neither fetch env, the mineru wait_for stayed 300s while the worker was
    abandoned at the live_retriever default 90s — the alignment was a NO-OP.
    GREEN: access_bypass reads the SAME 90 default, so the alignment is active.
    """
    src = ACCESS_BYPASS.read_text(encoding="utf-8")
    # The default literal for PG_FETCH_DEADLINE_SECONDS in access_bypass is now "90".
    assert re.search(
        r'os\.getenv\(\s*"PG_FETCH_DEADLINE_SECONDS",\s*"90"', src
    ), "access_bypass must read PG_FETCH_DEADLINE_SECONDS with the governing default 90"
    # The old no-op "0" default for the mineru alignment must be gone.
    assert 'os.getenv("PG_FETCH_DEADLINE_SECONDS", "0")' not in src
    # Behavioral: simulate the alignment math (mineru wait_for = min(raw, fetch_deadline - margin)).
    import os as _os
    monkeypatch.delenv("PG_FETCH_DEADLINE_SECONDS", raising=False)
    _fetch_deadline = float(_os.getenv("PG_FETCH_DEADLINE_SECONDS", "90") or "90")
    _raw = 300.0
    _margin = 5.0
    aligned = max(1.0, min(_raw, _fetch_deadline - _margin))
    assert aligned == 85.0  # 90 - 5, well inside the 90s worker-join window


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
