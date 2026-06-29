"""I-deepfix-001 fix-2 (#1344): the SHARED per-question retrieval wall-deadline.

`run_live_retrieval` already ACCEPTS a `retrieval_deadline_monotonic` instant and,
on expiry, hands off the partial corpus with disclosure (proven by
`test_live_retriever_retrieval_wall.py`). The relaunch gap (documented in
`live_retriever.run_live_retrieval`'s own docstring) is the CALLER: `run_one_query`
never passed a SHARED instant, so EACH of its many retrieval lanes (initial /
IterResearch-or-FS / CRAG corrective loop-back / R-6 expansion / deepener / agentic
/ STORM) anchored its OWN fresh `PG_RETRIEVAL_WALL_SECONDS` (30 min) wall. The
forensic run ground for ~57 min in retrieval because each lane reset the clock.

This fix:
  1. adds a pure `_per_question_retrieval_deadline()` helper that reads the NEW
     `PG_RETRIEVAL_QUESTION_WALL_SECONDS` knob and returns an ABSOLUTE
     `time.monotonic()` instant — or `None` when the knob is unset (DEFAULT =>
     byte-identical per-invocation bounding, the proven relaunch behavior);
  2. threads that ONE instant into EVERY `run_live_retrieval(...)` call site inside
     `run_one_query` via `retrieval_deadline_monotonic=...` so all lanes SHARE ONE
     per-question wall.

§-1.3 / faithfulness: this only stops the per-lane CLOCK RESET; it caps no breadth,
drops no source (the existing wall HANDS OFF the partial corpus with disclosure),
and touches no strict_verify / NLI / 4-role / span gate.

Offline: a pure env-read unit test + a static source-wiring assertion (no run, no
network, no GPU).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

import scripts.run_honest_sweep_r3 as sweep

_KNOB = "PG_RETRIEVAL_QUESTION_WALL_SECONDS"
_SWEEP_SRC = Path(sweep.__file__).read_text(encoding="utf-8")


# ── 1. helper unit: unset => None (byte-identical), set => absolute instant ──
def test_question_deadline_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(_KNOB, raising=False)
    assert sweep._per_question_retrieval_deadline() is None


def test_question_deadline_absolute_instant_when_set(monkeypatch) -> None:
    monkeypatch.setenv(_KNOB, "120")
    before = time.monotonic()
    deadline = sweep._per_question_retrieval_deadline()
    after = time.monotonic()
    assert deadline is not None
    # The returned instant is now + 120s (within the call's own wall-clock slack).
    assert before + 120.0 <= deadline <= after + 120.0


@pytest.mark.parametrize("raw", ["abc", "", "0", "-5", "nan", "inf"])
def test_question_deadline_garbage_or_nonpositive_is_none(monkeypatch, raw) -> None:
    """A garbage / non-positive knob disables the shared wall (None) rather than
    yielding a broken deadline — fail-safe to the per-invocation default."""
    monkeypatch.setenv(_KNOB, raw)
    assert sweep._per_question_retrieval_deadline() is None


# ── 2. static wiring: EVERY run_live_retrieval call in run_one_query shares it ──
def _run_one_query_body() -> str:
    """Slice the `run_one_query` coroutine body out of the module source so the
    wiring assertion is scoped to the per-question lanes (not main_async etc.)."""
    start = _SWEEP_SRC.index("async def run_one_query(")
    # run_one_query is followed by the next top-level `async def`/`def` at col 0.
    rest = _SWEEP_SRC[start + 1:]
    m = re.search(r"\n(async def |def )", rest)
    end = (start + 1 + m.start()) if m else len(_SWEEP_SRC)
    return _SWEEP_SRC[start:end]


def test_all_retrieval_calls_in_run_one_query_share_the_deadline() -> None:
    body = _run_one_query_body()
    # Count ACTUAL call sites (an assignment/return invoking the function at line
    # start), NOT prose mentions inside comments/docstrings like
    # "the SAME run_live_retrieval(seed_urls=...) chokepoint".
    call_re = re.compile(r"^\s*(?:\w+ = |return )run_live_retrieval\($", re.MULTILINE)
    n_calls = len(call_re.findall(body))
    n_wired = body.count("retrieval_deadline_monotonic=")
    assert n_calls >= 5, f"expected the multi-lane retrieval calls, found {n_calls}"
    assert n_wired >= n_calls, (
        f"{n_calls} run_live_retrieval call site(s) but only {n_wired} carry "
        "retrieval_deadline_monotonic=; every lane must SHARE the per-question wall"
    )


def test_shared_deadline_is_anchored_once() -> None:
    """The shared instant is computed ONCE per question (a single
    `_per_question_retrieval_deadline()` anchor), not re-read per lane (which would
    reset the clock and defeat the fix)."""
    body = _run_one_query_body()
    assert "_per_question_retrieval_deadline(" in body, (
        "run_one_query must anchor the shared per-question retrieval deadline"
    )
    # Anchored exactly once (one call to the helper), then reused by name.
    assert body.count("_per_question_retrieval_deadline(") == 1
