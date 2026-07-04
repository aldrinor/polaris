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

from src.polaris_graph.retrieval.saturation import marginal_novelty

logger = logging.getLogger("polaris_graph.ttddr_loop")

# ── stop reasons (module-level constants; allowed per CLAUDE.md §4.1) ──────────
STOP_NO_GAPS = "no_gaps"          # gap_fn found nothing more to close — converged
STOP_MAX_ROUNDS = "max_rounds"    # revision-round count bound hit
STOP_WALL = "wall"                # wall-clock deadline hit
STOP_COST = "cost"                # cumulative-cost budget hit
STOP_SATURATION = "saturation"    # source-yield saturated (marginal novelty < eps)
STOP_DISABLED = "disabled"        # PG_TTDDR_ENABLED off — loop never ran

# ── default-OFF flag idiom (NEW opt-in capability; ON only on an explicit token) ──
_ENV_TTDDR_ENABLED = "PG_TTDDR_ENABLED"
_ENABLE_ON_VALUES = ("1", "true", "yes", "on")

# I4 — source-yield saturation bound. `PG_TTDDR_SATURATION_EPS` is the marginal-
# novelty floor: once a revision round's TARGETED retrieval yields a NEW-source
# fraction below this floor, firing further rounds only re-fetches sources the
# draft already carries, so the loop stops SPENDING on rounds that add no new
# evidence. This is a COMPUTE bound keyed to source yield — it never drops, caps,
# or thins any retrieved source (every retrieved row this round is still folded
# into the draft and still gates through the frozen faithfulness engine
# downstream). It bounds how many MORE rounds run, not how much evidence renders.
_ENV_TTDDR_SATURATION_EPS = "PG_TTDDR_SATURATION_EPS"
_DEFAULT_SATURATION_EPS = 0.05


def ttddr_enabled() -> bool:
    """`PG_TTDDR_ENABLED` — DEFAULT-OFF. ON only on an explicit on token
    ('1'/'true'/'yes'/'on'); unset / empty / anything else -> OFF.

    Default-OFF is correct here: TTD-DR is a brand-new capability wired into no
    existing path, so it must be opt-in for the coverage run and dormant elsewhere.
    """
    return os.environ.get(_ENV_TTDDR_ENABLED, "").strip().lower() in _ENABLE_ON_VALUES


def ttddr_saturation_eps() -> float:
    """`PG_TTDDR_SATURATION_EPS` — the marginal-novelty floor for the source-yield
    saturation bound (I4). Unset / invalid -> `_DEFAULT_SATURATION_EPS` (0.05).

    The value is a FRACTION in [0, 1]: a round whose targeted retrieval brings a
    novel-source fraction below this floor is treated as saturated. A caller wires
    this (with a `rows_of` extractor) so the default TTD-DR run is bounded by
    source yield in addition to rounds/wall/cost. It is a spend bound, never a
    breadth cap — see the module-level note.
    """
    raw = os.environ.get(_ENV_TTDDR_SATURATION_EPS, "").strip()
    if not raw:
        return _DEFAULT_SATURATION_EPS
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_SATURATION_EPS
    # Clamp to a sane fraction; a nonsensical value must not disable the bound.
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


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
    # I4 — source-yield saturation bound (a COMPUTE bound, never a breadth cap).
    # `saturation_eps` is the marginal-novelty floor; `rows_of` maps a round's
    # retrieved evidence to its source rows (each row carrying `source_url`, the
    # live-retriever field). BOTH must be wired for the bound to act — the loop
    # cannot measure source yield without knowing how to read rows out of the
    # injected retrieve_fn's return. When either is None the bound is inert and
    # the loop keeps its rounds/wall/cost/no-gap behaviour unchanged.
    saturation_eps: Optional[float] = None,
    rows_of: Optional[Callable[[Any], Sequence[Any]]] = None,
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
    # I4 — source-yield saturation state. `cumulative_rows` is the running set of
    # source rows seen across all prior rounds (the novelty baseline); it only
    # ACCUMULATES — no row is ever removed, capped, or thinned. `novelty_history`
    # records the per-round novel-source fraction for observability.
    saturation_active = saturation_eps is not None and rows_of is not None
    cumulative_rows: list[Any] = []
    novelty_history: list[float] = []
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
            "novelty_history": novelty_history,
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

        # I4 — measure this round's source yield BEFORE folding its rows into the
        # running baseline: novelty = fraction of THIS round's retrieved sources
        # not already seen in prior rounds. `marginal_novelty` reuses the shared
        # canonical-URL identity (saturation.py -> run_diff), so re-fetched
        # sources collapse and only genuinely-new sources count.
        round_novelty: Optional[float] = None
        if saturation_active:
            this_rows = list(rows_of(evidence) or [])
            round_novelty = marginal_novelty(cumulative_rows, this_rows)
            novelty_history.append(round_novelty)
            # ACCUMULATE only — never drop/cap. Every retrieved row stays in the
            # baseline and is still folded into the draft below.
            cumulative_rows.extend(this_rows)

        # Always fold the retrieved evidence into the draft (consolidate, never
        # drop): even a saturating round's evidence widens the draft's coverage.
        draft = revise_fn(question, draft, gaps, evidence)
        rounds += 1
        gaps_closed += len(gaps)
        gap_history.append(len(gaps))
        _log(f"[ttddr] round={rounds} closed {len(gaps)} gap(s) "
             f"(cumulative gaps_closed={gaps_closed}"
             + (f", novelty={round_novelty:.3f}" if round_novelty is not None else "")
             + ")")

        # I4 — source-yield saturation early exit. Requires a PRIOR round to
        # compare against (rounds >= 2), so the first retrieval never trips it.
        # Once a round's novel-source fraction falls below the floor, further
        # rounds only re-fetch known sources: STOP spending. This bounds compute,
        # not breadth — this round's evidence is already folded in above.
        if saturation_active and rounds >= 2 and round_novelty is not None \
                and round_novelty < saturation_eps:
            _log(f"[ttddr] source yield saturated at round={rounds} "
                 f"(novelty={round_novelty:.3f} < eps={saturation_eps}) "
                 "-> STOP_SATURATION")
            return _finish(STOP_SATURATION)
