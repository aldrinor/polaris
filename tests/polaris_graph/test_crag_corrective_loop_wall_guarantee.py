"""I-deepfix-001 U22 (#1344): an INSUFFICIENT CRAG verdict guarantees >= 1
corrective retrieval iteration even when the shared per-question retrieval wall
was already consumed by the upstream lanes.

THE DEFECT (autopsy drb_72 `crag_adequacy_loop.json`):
    initial_sufficient = False        # CRAG graded the corpus insufficient
    loops_fired        = 0            # ... but the corrective loop ran ZERO iters
    stopped_reason     = retrieval_wall
    injected           = 0

The corrective loop's wall-gate broke immediately because the shared
`_question_retrieval_deadline` had already passed (the initial / STORM / deepener
lanes ate the whole wall before adequacy was even graded). Corrective-RAG's whole
point is that a NOT-sufficient corpus gets at least one corrective round, so a
bare wall-break makes CRAG a no-op EXACTLY when it is needed.

THE FIX (pure decision helpers in crag_adequacy_loop):
  * `wall_should_break_corrective_loop(...)` — never break BEFORE the first
    corrective round when the corpus is insufficient (loops_done == 0); honor the
    wall unchanged afterwards (BUG-A bound preserved).
  * `corrective_iter_deadline(...)` — grant that guaranteed first round a bounded
    reserved budget when the shared wall is already exhausted, so it can actually
    fetch instead of short-circuiting.

These are OFFLINE unit tests (pure functions; no GPU / no network / no LLM). The
behavioral core (`test_insufficient_verdict_fires_at_least_one_corrective_iter`)
reproduces the drb_72 scenario against a tiny loop simulator and asserts the
BUGGY gate yields 0 iters while the FIXED gate yields >= 1.

FAITHFULNESS: these are retrieval STOP-decision / budget helpers only. They feed
the UNCHANGED tier classifier + strict_verify / NLI / 4-role / provenance engine
MORE candidates; they never gate a sentence and never relax any faithfulness gate.
"""
from __future__ import annotations

import time

import pytest

from src.polaris_graph.nodes import crag_adequacy_loop as crag


# ── wall_should_break_corrective_loop: the guarantee ─────────────────────────
def test_insufficient_first_iter_does_not_break_even_when_wall_passed() -> None:
    """The KEYSTONE: insufficient corpus + wall already passed + no round yet =>
    do NOT break (the guaranteed first corrective iteration must run). This is the
    exact drb_72 state that no-opped before the fix."""
    assert crag.wall_should_break_corrective_loop(
        sufficient=False, loops_done=0, wall_passed=True
    ) is False


def test_insufficient_first_iter_does_not_break_when_wall_not_passed() -> None:
    """Wall still has budget => obviously keep going (unchanged behaviour)."""
    assert crag.wall_should_break_corrective_loop(
        sufficient=False, loops_done=0, wall_passed=False
    ) is False


def test_insufficient_second_iter_honors_the_wall() -> None:
    """After the one guaranteed round, the wall is honored again => break. The loop
    can never grind unbounded past the wall (BUG-A bound preserved)."""
    assert crag.wall_should_break_corrective_loop(
        sufficient=False, loops_done=1, wall_passed=True
    ) is True


def test_insufficient_second_iter_without_wall_keeps_going() -> None:
    """Second round, wall not passed => no wall reason to break (max_loops still
    bounds it via should_loop_back in the run-script)."""
    assert crag.wall_should_break_corrective_loop(
        sufficient=False, loops_done=1, wall_passed=False
    ) is False


def test_sufficient_corpus_honors_the_wall_on_first_iter() -> None:
    """A sufficient corpus needs no corrective round: the wall decision is honored
    verbatim (the guarantee is ONLY for insufficient corpora)."""
    assert crag.wall_should_break_corrective_loop(
        sufficient=True, loops_done=0, wall_passed=True
    ) is True
    assert crag.wall_should_break_corrective_loop(
        sufficient=True, loops_done=0, wall_passed=False
    ) is False


# ── corrective_iter_deadline: the reserved budget for the guaranteed round ────
def test_deadline_none_when_wall_off() -> None:
    """Wall unset (the default) => None => corrective retrieval unbounded exactly as
    before (byte-identical)."""
    assert crag.corrective_iter_deadline(
        shared_deadline=None, now=time.monotonic(), loops_done=0, sufficient=False
    ) is None


def test_deadline_uses_shared_wall_when_budget_remains() -> None:
    """Shared wall still in the future => use it unchanged (no reserve needed)."""
    now = time.monotonic()
    shared = now + 120.0
    assert crag.corrective_iter_deadline(
        shared_deadline=shared, now=now, loops_done=0, sufficient=False
    ) == shared


def test_deadline_grants_reserved_budget_for_guaranteed_first_round() -> None:
    """Shared wall already passed + insufficient + first round => grant a bounded
    reserved budget strictly in the future so the round can actually fetch (not a
    short-circuit on the exhausted wall)."""
    now = time.monotonic()
    shared = now - 10.0  # wall already passed
    got = crag.corrective_iter_deadline(
        shared_deadline=shared, now=now, loops_done=0, sufficient=False
    )
    assert got is not None
    assert got > now, "the guaranteed first round must get a live (future) deadline"
    assert got == pytest.approx(now + crag.corrective_reserve_seconds())


def test_deadline_no_reserve_after_first_round() -> None:
    """Wall passed but a round already fired => no reserve; the (passed) shared wall
    is returned and the loop-break decision stops the loop anyway."""
    now = time.monotonic()
    shared = now - 10.0
    assert crag.corrective_iter_deadline(
        shared_deadline=shared, now=now, loops_done=1, sufficient=False
    ) == shared


# ── corrective_reserve_seconds: env-driven, bounded, fail-safe ───────────────
def test_reserve_default_is_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(crag.CORRECTIVE_RESERVE_ENV, raising=False)
    assert crag.corrective_reserve_seconds() == crag._DEFAULT_CORRECTIVE_RESERVE_SECONDS
    assert crag.corrective_reserve_seconds() > 0


def test_reserve_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(crag.CORRECTIVE_RESERVE_ENV, "45.5")
    assert crag.corrective_reserve_seconds() == pytest.approx(45.5)


def test_reserve_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(crag.CORRECTIVE_RESERVE_ENV, "not-a-number")
    assert crag.corrective_reserve_seconds() == crag._DEFAULT_CORRECTIVE_RESERVE_SECONDS
    monkeypatch.setenv(crag.CORRECTIVE_RESERVE_ENV, "-5")
    assert crag.corrective_reserve_seconds() == crag._DEFAULT_CORRECTIVE_RESERVE_SECONDS


# ── behavioral reproduction of the drb_72 no-op vs the fix ───────────────────
def _simulate_corrective_loop(*, buggy: bool, wall_passed: bool, insufficient_forever: bool) -> int:
    """Count how many corrective iterations fire under either gate.

    Models the run-script loop shape:
        while should_loop_back(sufficient, loops_done):
            if <wall gate>: break
            ... one corrective retrieval round ...
            loops_done += 1
            <re-grade: still insufficient?>

    `buggy=True`  => the pre-fix gate: break whenever the wall has passed.
    `buggy=False` => the fixed gate: `wall_should_break_corrective_loop(...)`.
    """
    # Force max_loops=1 semantics locally (the production default) without env.
    max_loops = 1
    sufficient = not insufficient_forever
    loops_done = 0
    fired = 0
    while (not sufficient) and loops_done < max_loops:
        if buggy:
            should_break = wall_passed
        else:
            should_break = crag.wall_should_break_corrective_loop(
                sufficient=sufficient, loops_done=loops_done, wall_passed=wall_passed
            )
        if should_break:
            break
        # one corrective round fires
        fired += 1
        loops_done += 1
        # re-grade: for this simulation the corpus stays insufficient (worst case)
        sufficient = not insufficient_forever
    return fired


def test_insufficient_verdict_fires_at_least_one_corrective_iter() -> None:
    """The acceptance behaviour: on an insufficient verdict with the shared wall
    already exhausted, the BUGGY gate fires 0 corrective iters (the drb_72 no-op)
    while the FIXED gate fires exactly 1 (>= 1, bounded)."""
    buggy_iters = _simulate_corrective_loop(
        buggy=True, wall_passed=True, insufficient_forever=True
    )
    fixed_iters = _simulate_corrective_loop(
        buggy=False, wall_passed=True, insufficient_forever=True
    )
    assert buggy_iters == 0, "sanity: the pre-fix gate reproduced the drb_72 no-op"
    assert fixed_iters >= 1, (
        "the fix must fire at least one corrective iteration on an insufficient "
        "verdict even when the shared retrieval wall was exhausted"
    )
    # Bounded: still capped at one round (BUG-A bound), never unbounded.
    assert fixed_iters == 1


def test_fix_is_byte_identical_when_wall_has_budget() -> None:
    """When the wall still has budget, the fixed and buggy gates behave identically
    (the fix only diverges once the wall is exhausted)."""
    for insufficient in (True, False):
        buggy = _simulate_corrective_loop(
            buggy=True, wall_passed=False, insufficient_forever=insufficient
        )
        fixed = _simulate_corrective_loop(
            buggy=False, wall_passed=False, insufficient_forever=insufficient
        )
        assert buggy == fixed
