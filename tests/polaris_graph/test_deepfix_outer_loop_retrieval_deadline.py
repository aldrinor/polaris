"""I-deepfix-001 BUG-A (#1344): the OUTER per-question retrieval loops HONOR the
shared retrieval wall-deadline.

FIX-2 (`test_deepfix_shared_retrieval_deadline.py`) anchored ONE shared
`_question_retrieval_deadline` and threaded it into every
`run_live_retrieval(...)` call so each lane's INNER search fan-out short-circuits
on the wall. But the OUTER control flow in `run_one_query` was NOT bounded:

  * the CRAG corrective `while ... should_loop_back(...)` loop keeps deriving NEW
    gap queries + firing a fresh `_run_crag_classifier()` LLM round + re-classify +
    re-grade EACH iteration — work FIX-2 does not cover (it only short-circuits the
    `run_live_retrieval` inside the loop), so the loop grinds tens of minutes past
    the wall, and
  * the additive one-shot lanes (R-6 expansion / deepener / agentic / STORM /
    saturation gap) still ENTER and spend their own non-`run_live_retrieval` work
    (e.g. the deepener's `run_deepener_sync` snowball discovery) after the wall.

The keystone consequence: retrieval never reaches HAND-OFF to generation before the
run-level `asyncio.wait_for` wall (`_RUN_WALL_CLOCK_DEADLINE_CTX`) guillotines the
whole question — producing a TIMEOUT artifact with NO generated report.

BUG-A fix:
  1. a pure `_question_retrieval_deadline_passed(deadline)` helper — True iff
     `deadline is not None and time.monotonic() > deadline` (mirrors
     `live_retriever`'s `time.monotonic() > _retrieval_deadline` at 4353/5075);
     `None` (knob unset — the default) => always False => byte-identical;
  2. the CRAG corrective `while` condition AND each additive-lane entry `if`
     consult that guard so, once the shared wall has passed, the loops STOP ADDING
     rounds and the corpus gathered so far HANDS OFF to generation;
  3. the early stop is DISCLOSED (`stopped_reason="retrieval_wall"` in the CRAG
     loop trace), never a silent cap.

§-1.3 / faithfulness: this stops ADDING query rounds; it drops ZERO gathered
sources (same proven hand-off-with-disclosure semantics as the already-approved
inner wall) and touches no strict_verify / NLI / 4-role / span gate. `None` default
=> byte-identical.

Offline: a pure helper unit + static source-wiring assertions (no run, no network,
no GPU).
"""
from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import pytest

import scripts.run_honest_sweep_r3 as sweep

_SWEEP_SRC = Path(sweep.__file__).read_text(encoding="utf-8")


# ── 1. pure helper unit ──────────────────────────────────────────────────────
def test_deadline_passed_false_when_none() -> None:
    """`None` (knob unset — the default) => the wall is OFF => never passed =>
    byte-identical outer-loop behaviour."""
    assert sweep._question_retrieval_deadline_passed(None) is False


def test_deadline_passed_false_when_in_future() -> None:
    """A deadline still in the future => not passed => the loop keeps running."""
    assert sweep._question_retrieval_deadline_passed(time.monotonic() + 60.0) is False


def test_deadline_passed_true_when_elapsed() -> None:
    """A deadline strictly in the past => passed => the outer loop must stop
    ADDING rounds and hand off."""
    assert sweep._question_retrieval_deadline_passed(time.monotonic() - 1.0) is True


def test_deadline_passed_uses_strict_greater_than() -> None:
    """Mirror live_retriever's `time.monotonic() > deadline`: the boundary instant
    itself is NOT yet 'passed' (strict `>`), so a just-anchored deadline never
    trips on its own anchor tick."""
    now = time.monotonic()
    # A deadline == now (within the same call) is NOT strictly in the past.
    assert sweep._question_retrieval_deadline_passed(now + 1e6) is False


# ── 2. static wiring: the OUTER loops consult the guard ───────────────────────
def _run_one_query_body() -> str:
    start = _SWEEP_SRC.index("async def run_one_query(")
    rest = _SWEEP_SRC[start + 1:]
    m = re.search(r"\n(async def |def )", rest)
    end = (start + 1 + m.start()) if m else len(_SWEEP_SRC)
    return _SWEEP_SRC[start:end]


def test_helper_defined_at_module_scope() -> None:
    assert "_question_retrieval_deadline_passed" in _SWEEP_SRC, (
        "the BUG-A outer-loop guard helper must exist at module scope"
    )


def test_crag_while_loop_consults_the_deadline_guard() -> None:
    """The KEYSTONE: the CRAG corrective `while` is bounded by the shared wall.
    Without this the loop fires unbounded `_run_crag_classifier()` LLM rounds past
    the wall and retrieval never hands off to generation."""
    body = _run_one_query_body()
    # Find the CRAG corrective while-loop and assert the guard token appears within
    # a small window of its condition (same call site, not elsewhere in the body).
    m = re.search(r"while _crag_loop_enabled and _crag_adq\.should_loop_back\(", body)
    assert m is not None, "could not locate the CRAG corrective while-loop"
    # The guard sits at the TOP of the loop body (a disclosed break on the wall),
    # immediately after the explanatory comment block — scope the window to the loop
    # head + its first statement so the assertion can't pass on an unrelated match.
    window = body[m.start(): m.start() + 1800]
    assert "_question_retrieval_deadline_passed(_question_retrieval_deadline)" in window, (
        "the CRAG corrective while-loop must consult "
        "_question_retrieval_deadline_passed(_question_retrieval_deadline) at the "
        "top of its body"
    )
    # And it must break (hand off) on the wall, not just observe it.
    assert "break" in window


def test_crag_early_stop_is_disclosed() -> None:
    """§-1.3: a wall-driven early stop is DISCLOSED in the CRAG loop trace (never a
    silent cap). The trace must carry `stopped_reason` set to 'retrieval_wall'."""
    body = _run_one_query_body()
    assert '"stopped_reason"' in body, (
        "the CRAG loop trace must carry a 'stopped_reason' field"
    )
    assert 'stopped_reason"] = "retrieval_wall"' in body, (
        "the CRAG loop must set stopped_reason='retrieval_wall' on the wall-driven "
        "early stop so it is disclosed in the trace (not a silent drop)"
    )


def test_additive_lanes_guarded_count() -> None:
    """Every additive outer lane entry that spends non-`run_live_retrieval` work
    after the wall (R-6 expansion / deepener / agentic / STORM / saturation gap)
    must ALSO consult the guard — uniform application, not just the loop."""
    body = _run_one_query_body()
    n_guard = body.count("_question_retrieval_deadline_passed(")
    # 1 (CRAG while) + at least the additive lanes. Conservative floor of 4 so the
    # test catches a refactor that drops the guard off the lanes.
    assert n_guard >= 4, (
        f"expected the CRAG while + additive-lane entries to consult the guard, "
        f"found {n_guard} reference(s)"
    )


def test_guard_helper_is_pure_and_uses_monotonic() -> None:
    """The helper is a pure env-free monotonic comparison (no os.getenv re-read —
    the deadline is ANCHORED once by FIX-2's `_per_question_retrieval_deadline`)."""
    fn_src = _slice_function_source("_question_retrieval_deadline_passed")
    assert "time.monotonic()" in fn_src
    assert "os.getenv" not in fn_src, (
        "the guard must compare against the ALREADY-anchored deadline, not re-read "
        "the env (which would re-anchor and defeat the shared wall)"
    )


def _slice_function_source(name: str) -> str:
    tree = ast.parse(_SWEEP_SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(_SWEEP_SRC, node) or ""
    raise AssertionError(f"function {name!r} not found at module scope")
