"""WS-15 — TTD-DR coverage loop (Test-Time Diffusion Deep Research). PURE decision logic.

TTD-DR (arXiv:2507.16075, Han et al., Google, 2025 — "Deep Researcher with
Test-Time Diffusion") conceptualises report writing as an iterative *diffusion*:
start from a preliminary DRAFT (an updatable skeleton), then progressively
"denoise" it by cycles of gap-finding -> targeted retrieval -> revision. It is
the mechanism the current DRB-II SOTA uses to lift COVERAGE / recall.

Paper Algorithm 1 (Denoising with Retrieval), verbatim shape:

    R_0 = initial draft
    for t in 1..N:
        Q_t = M_Q(q, R_{t-1})        # next question / coverage gap from the draft
        A_t = M_A(Q_t)               # retrieve an answer for that gap
        R_t = M_R(q, R_{t-1}, Q, A)  # revise (denoise) the draft with A_t
        if exit_loop: break

This module implements that loop with the four model roles INJECTED as callables
(`draft_fn` = the skeleton generator, `gap_fn` = M_Q made explicit as coverage-gap
detection, `retrieve_fn` = M_A, `revise_fn` = M_R). Nothing here constructs an HTTP
client, loads a model, or bills a token: the caller wires the real roles; the tests
wire capture-only fakes. So it is fully OFFLINE-testable and touches no network at
import or test time.

BOUNDS (the paper leaves `exit_loop` implementation-defined; the WS-15 plan
correction makes it a HARD triad so the loop can never run away):
  * `max_rounds`  — bounds the revision-round count (the paper's fixed N). This is
    the GUARANTEED termination backstop — always enforced.
  * `wall_seconds`— wall-clock deadline (monotonic; the clock is injectable so wall
    stops are deterministic offline). `None` disables only this early exit.
  * `cost_budget` — spend gate; the cumulative-cost probe is injected (`cost_fn`),
    so the caller wires the real cost ledger. `None` disables only this early exit.
The loop STOPS on the first of: gap_fn returns no new gaps (converged — the ideal
exit) OR any bound trips.

§-1.3 (WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP): this module ADDS retrieved
evidence and REVISES the draft to widen coverage. It NEVER verifies, drops, caps,
or thins anything. The FROZEN faithfulness engine (strict_verify / provenance /
NLI / 4-role / span-grounding) still gates every revised claim DOWNSTREAM,
unchanged — this orchestrator is upstream of it and touches none of it.

`PG_TTDDR_ENABLED` is DEFAULT-OFF: TTD-DR is a NEW opt-in capability wired into no
existing path, so the whole module stays dormant (never invokes a callable) until
the coverage run explicitly turns it on. When off, `ttddr_refine` short-circuits
and returns the initial draft untouched.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger("polaris_graph.ttddr_loop")

# ── stop reasons (module-level constants; allowed per CLAUDE.md §4.1) ──────────
STOP_NO_GAPS = "no_gaps"          # gap_fn found nothing more to close — converged
STOP_MAX_ROUNDS = "max_rounds"    # revision-round count bound hit
STOP_WALL = "wall"                # wall-clock deadline hit
STOP_COST = "cost"                # cumulative-cost budget hit
STOP_DISABLED = "disabled"        # PG_TTDDR_ENABLED off — loop never ran

# ── default-OFF flag idiom (NEW opt-in capability; ON only on an explicit token) ──
_ENV_TTDDR_ENABLED = "PG_TTDDR_ENABLED"
_ENABLE_ON_VALUES = ("1", "true", "yes", "on")


def ttddr_enabled() -> bool:
    """`PG_TTDDR_ENABLED` — DEFAULT-OFF. ON only on an explicit on token
    ('1'/'true'/'yes'/'on'); unset / empty / anything else -> OFF.

    Default-OFF is correct here: TTD-DR is a brand-new capability wired into no
    existing path, so it must be opt-in for the coverage run and dormant elsewhere.
    """
    return os.environ.get(_ENV_TTDDR_ENABLED, "").strip().lower() in _ENABLE_ON_VALUES


def _as_gap_list(gaps: Any) -> list[Any]:
    """Materialise gap_fn's output to a list; None / falsy -> [] (converged)."""
    if not gaps:
        return []
    return list(gaps)


def ttddr_refine(
    question: str,
    initial_draft: Optional[Any] = None,
    *,
    draft_fn: Optional[Callable[[str], Any]] = None,
    gap_fn: Callable[[str, Any], Sequence[Any]],
    retrieve_fn: Callable[[str, Sequence[Any]], Any],
    revise_fn: Callable[[str, Any, Sequence[Any], Any], Any],
    max_rounds: int,
    # WS-15 P1 fix (Codex waveDE gate): all THREE bounds must be active by DEFAULT. max_rounds is required;
    # wall_seconds + cost_budget now default to real finite ceilings (NOT None), so the default loop is
    # fully bounded on rounds AND wall-clock AND cost. Passing None still explicitly opts a single bound
    # out for a caller that wires its own guard, but a default invocation can never run unbounded.
    wall_seconds: Optional[float] = 1800.0,
    cost_budget: Optional[float] = 50.0,
    clock: Callable[[], float] = time.monotonic,
    cost_fn: Callable[[], float] = lambda: 0.0,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run the bounded TTD-DR denoising-with-retrieval loop (paper Algorithm 1).

    Injected role contracts (the caller wires real models; tests wire fakes):
      * `draft_fn(question) -> draft`                       — the R_0 skeleton, used
        ONLY when `initial_draft` is None.
      * `gap_fn(question, draft) -> Sequence[gap]`          — M_Q as explicit
        coverage-gap detection on the CURRENT draft; empty return == converged.
      * `retrieve_fn(question, gaps) -> evidence`           — M_A, targeted retrieval
        for the detected gaps.
      * `revise_fn(question, draft, gaps, evidence) -> draft` — M_R, denoise/revise
        the draft with the retrieved evidence.

    Bounds (checked at the top of every round, in this priority order):
        wall_seconds -> cost_budget -> max_rounds -> gap detection.
    `max_rounds` is the guaranteed termination backstop and is always enforced;
    `wall_seconds` / `cost_budget` are additional early exits (`None` disables the
    corresponding early exit only).

    Returns:
        {
          "final_draft": Any,      # the last revised draft (R_final)
          "rounds": int,           # revision rounds actually executed
          "gaps_closed": int,      # cumulative count of gaps addressed by a revision
          "stop_reason": str,      # one of the STOP_* constants
          "elapsed_seconds": float,
          "cost_spent": float,
          "gap_history": list[int],# len(gaps) closed per executed round
        }

    This module NEVER verifies: it only orchestrates draft/gap/retrieve/revise. The
    frozen faithfulness engine gates every revised claim downstream, unchanged.
    """
    _log = log or (lambda _m: None)

    # DEFAULT-OFF gate — when off, invoke NO callable and return the draft untouched.
    if not ttddr_enabled():
        _log("[ttddr] PG_TTDDR_ENABLED off — loop skipped")
        return {
            "final_draft": initial_draft,
            "rounds": 0,
            "gaps_closed": 0,
            "stop_reason": STOP_DISABLED,
            "elapsed_seconds": 0.0,
            "cost_spent": 0.0,
            "gap_history": [],
        }

    if initial_draft is None:
        if draft_fn is None:
            raise ValueError(
                "ttddr_refine requires either initial_draft or draft_fn to seed R_0"
            )
        initial_draft = draft_fn(question)

    draft: Any = initial_draft
    rounds = 0
    gaps_closed = 0
    gap_history: list[int] = []
    t0 = clock()
    now = t0
    spent = cost_fn()

    def _finish(reason: str) -> dict:
        return {
            "final_draft": draft,
            "rounds": rounds,
            "gaps_closed": gaps_closed,
            "stop_reason": reason,
            "elapsed_seconds": max(0.0, now - t0),
            "cost_spent": spent,
            "gap_history": gap_history,
        }

    while True:
        now = clock()
        # 1) wall-clock deadline (early exit; None disables).
        if wall_seconds is not None and (now - t0) >= wall_seconds:
            _log(f"[ttddr] wall deadline hit at round={rounds} "
                 f"(elapsed={now - t0:.3f}s >= {wall_seconds}s) -> STOP_WALL")
            return _finish(STOP_WALL)
        # 2) cost budget (early exit; None disables).
        spent = cost_fn()
        if cost_budget is not None and spent >= cost_budget:
            _log(f"[ttddr] cost budget hit at round={rounds} "
                 f"(spent={spent} >= {cost_budget}) -> STOP_COST")
            return _finish(STOP_COST)
        # 3) round-count backstop (always enforced -> guarantees termination).
        if rounds >= max_rounds:
            _log(f"[ttddr] max_rounds hit (rounds={rounds} >= {max_rounds}) "
                 "-> STOP_MAX_ROUNDS")
            return _finish(STOP_MAX_ROUNDS)

        # 4) gap detection on the current draft (M_Q). Empty -> converged.
        gaps = _as_gap_list(gap_fn(question, draft))
        if not gaps:
            _log(f"[ttddr] no residual gaps at round={rounds} -> STOP_NO_GAPS")
            return _finish(STOP_NO_GAPS)

        # Fire one denoising round: targeted retrieve (M_A) then revise (M_R).
        evidence = retrieve_fn(question, gaps)
        draft = revise_fn(question, draft, gaps, evidence)
        rounds += 1
        gaps_closed += len(gaps)
        gap_history.append(len(gaps))
        _log(f"[ttddr] round={rounds} closed {len(gaps)} gap(s) "
             f"(cumulative gaps_closed={gaps_closed})")
