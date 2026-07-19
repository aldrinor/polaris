#!/usr/bin/env python3
"""Phase 0A-5 — graph-selector replay fixtures (the "before" for v1/v2/v3).

Plan V4 §0A-5: *Characterize all 3 graph selectors on fixed inputs as replay
fixtures.* This harness pins each routed graph version's conditional-edge
**selector** (the pure state -> edge-name decision function that LangGraph calls
at a conditional edge) to a byte-identical golden fixture:

    tests/oracle/graph_fixtures/graph_selector_fixtures.json

These fixtures are the deterministic "before" baseline that Phase 3C's
per-selector compatibility matrix ("Nothing in graph*.py deleted until (1)
per-selector compatibility matrix on the 0A-5 fixtures ...") will replay the
"after" against. They exercise the routing logic ONLY — no LLM, no network, no
browser — so they are cheap, fully offline, and reproducible.

Selectors pinned
----------------
* v1 (``src/polaris_graph/graph.py``) — ``_should_iterate`` and
  ``_should_finalize``. These are **nested closures** defined inside
  ``build_graph()`` and are NOT importable at module level; they are recovered
  from the compiled ``StateGraph.branches[node][name].path.func`` (the real
  production closure, not a re-implementation).
* v2 (``src/polaris_graph/graph_v2.py``) — ``route_after_crag`` (module-level,
  importable).
* v3 (``src/polaris_graph/graph_v3.py``) — ``_should_search_gaps`` (module-level,
  importable).

Determinism note (why each fixture carries a pinned ``env`` slice)
------------------------------------------------------------------
``_should_iterate`` (v1) reads several env vars **at call time**
(``PG_FAST_EXIT_FAITHFULNESS/EVIDENCE_COUNT/UNIQUE_SOURCES``,
``PG_FAITH_ITERATE_THRESHOLD``, ``PG_FAITH_MIN_EVIDENCE_FOR_SKIP``). Those
thresholds MOVE the selected branch (verified empirically), so replay is only
byte-identical when they are pinned. Each fixture therefore records the exact
env slice it was captured under; replay sets that slice before calling the
selector. ``route_after_crag`` (v2) and ``_should_search_gaps`` (v3) instead
read module-level constants (``PG_V2_MAX_ITERATIONS`` / ``PG_V3_MAX_GAP_SEARCHES``)
that are frozen at import; each fixture records the observed constant value for
provenance and the harness asserts it still matches on replay.

Modes
-----
* ``--mode record``  — capture selector outputs under the pinned inputs and
  (re)write the golden fixture JSON. Fails if any recorded output would change
  an existing golden without ``--force`` (record is meant to be run once, at
  baseline).
* ``--mode replay``  — DEFAULT. Recover each selector, replay every fixture
  case, and assert the returned edge string is byte-identical to the golden.
  Exit 0 on full match; exit 3 on any mismatch (a real routing regression).

The fixture JSON is emitted with ``sort_keys=True`` + ``indent=2`` + trailing
newline so it is byte-stable across record runs on any machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
_GOLDEN = _HERE / "graph_selector_fixtures.json"

# Repo root = .../<repo>/tests/oracle/graph_fixtures -> up 3.
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Selector recovery — each returns a pure (state) -> edge-name callable that IS
# the production selector (recovered, never re-implemented).
# ---------------------------------------------------------------------------
def _recover_v1_selectors() -> dict[str, Callable[[dict], str]]:
    """v1 selectors are closures inside build_graph(); pull them from the
    compiled graph's conditional-edge branch table."""
    from src.polaris_graph.graph import build_graph

    g = build_graph()
    return {
        "_should_iterate": g.branches["evaluate"]["_should_iterate"].path.func,
        "_should_finalize": g.branches["synthesize"]["_should_finalize"].path.func,
    }


def _recover_v2_selectors() -> dict[str, Callable[[dict], str]]:
    from src.polaris_graph.graph_v2 import route_after_crag

    return {"route_after_crag": route_after_crag}


def _recover_v3_selectors() -> dict[str, Callable[[dict], str]]:
    from src.polaris_graph.graph_v3 import _should_search_gaps

    return {"_should_search_gaps": _should_search_gaps}


def _observed_constants() -> dict[str, int]:
    from src.polaris_graph.graph_v2 import MAX_ITERATIONS
    from src.polaris_graph.graph_v3 import _MAX_GAP_SEARCHES

    return {
        "PG_V2_MAX_ITERATIONS": int(MAX_ITERATIONS),
        "PG_V3_MAX_GAP_SEARCHES": int(_MAX_GAP_SEARCHES),
    }


def _all_selectors() -> dict[str, dict[str, Callable[[dict], str]]]:
    return {
        "v1": _recover_v1_selectors(),
        "v2": _recover_v2_selectors(),
        "v3": _recover_v3_selectors(),
    }


# ---------------------------------------------------------------------------
# The pinned fixture cases. Each case: {name, env, state, }; expected is filled
# in by record mode. Env is a slice of os.environ pinned for that case (only
# the vars the selector actually reads at call time).
# ---------------------------------------------------------------------------
# Default env slice that reproduces the shipped selector thresholds. Recording
# under an explicit slice (rather than inheriting an ambient shell) is what
# makes v1 replay byte-identical regardless of machine.
_V1_DEFAULT_ENV = {
    "PG_FAST_EXIT_FAITHFULNESS": "0.85",
    "PG_FAST_EXIT_EVIDENCE_COUNT": "200",
    "PG_FAST_EXIT_UNIQUE_SOURCES": "15",
    "PG_FAITH_ITERATE_THRESHOLD": "0.75",
    "PG_FAITH_MIN_EVIDENCE_FOR_SKIP": "500",
}


def _evidence(n: int, unique_sources: int | None = None) -> list[dict]:
    """Build n evidence dicts. If unique_sources given, cap distinct URLs."""
    if unique_sources is None:
        unique_sources = n
    out = []
    for i in range(n):
        out.append({"source_url": f"https://ex.test/s{i % max(unique_sources, 1)}"})
    return out


def _cases() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        "v1": {
            "_should_iterate": [
                {
                    "name": "missing_needs_iteration_defaults_synthesize",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {},
                },
                {
                    "name": "needs_iteration_false_synthesize",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {"needs_iteration": False},
                },
                {
                    "name": "fast_exit_all_three_signals_synthesize",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {
                        "needs_iteration": True,
                        "faithfulness_score": 0.9,
                        "evidence": _evidence(210, unique_sources=20),
                        "iteration_count": 0,
                        "max_iterations": 3,
                    },
                },
                {
                    "name": "fix_loop_faith_and_evidence_synthesize",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {
                        "needs_iteration": True,
                        "faithfulness_score": 0.8,
                        "evidence": _evidence(500, unique_sources=3),
                        "iteration_count": 0,
                        "max_iterations": 3,
                    },
                },
                {
                    "name": "iterate_to_plan_no_gap_queries",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {
                        "needs_iteration": True,
                        "iteration_count": 0,
                        "max_iterations": 3,
                        "faithfulness_score": 0.4,
                        "evidence": _evidence(10),
                    },
                },
                {
                    "name": "iterate_to_search_gaps_with_gap_queries",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {
                        "needs_iteration": True,
                        "iteration_count": 0,
                        "max_iterations": 3,
                        "gap_queries": ["gap one", "gap two"],
                        "faithfulness_score": 0.4,
                        "evidence": _evidence(10),
                    },
                },
                {
                    "name": "at_max_iterations_synthesize",
                    "env": dict(_V1_DEFAULT_ENV),
                    "state": {
                        "needs_iteration": True,
                        "iteration_count": 3,
                        "max_iterations": 3,
                        "faithfulness_score": 0.4,
                        "evidence": _evidence(10),
                    },
                },
            ],
            "_should_finalize": [
                {
                    "name": "converged_end",
                    "env": {},
                    "state": {"converged": True},
                },
                {
                    "name": "quality_passed_end",
                    "env": {},
                    "state": {"converged": False, "quality_gate_result": "passed"},
                },
                {
                    "name": "below_min_with_gap_queries_search_gaps",
                    "env": {},
                    "state": {
                        "converged": False,
                        "quality_gate_result": "below_minimum",
                        "iteration_count": 0,
                        "max_iterations": 3,
                        "gap_queries": ["q1"],
                    },
                },
                {
                    "name": "below_min_no_gap_queries_end",
                    "env": {},
                    "state": {
                        "converged": False,
                        "quality_gate_result": "below_minimum",
                        "iteration_count": 0,
                        "max_iterations": 3,
                    },
                },
                {
                    "name": "below_min_at_max_iterations_end",
                    "env": {},
                    "state": {
                        "converged": False,
                        "quality_gate_result": "below_minimum",
                        "iteration_count": 3,
                        "max_iterations": 3,
                        "gap_queries": ["q1"],
                    },
                },
            ],
        },
        "v2": {
            "route_after_crag": [
                {
                    "name": "correct_plan_outline",
                    "env": {},
                    "state": {"crag_gate": "CORRECT", "iteration_count": 0},
                },
                {
                    "name": "ambiguous_under_max_replan",
                    "env": {},
                    "state": {"crag_gate": "AMBIGUOUS", "iteration_count": 0},
                },
                {
                    "name": "ambiguous_at_max_plan_outline",
                    "env": {},
                    "state": {"crag_gate": "AMBIGUOUS", "iteration_count": 3},
                },
                {
                    "name": "incorrect_under_max_replan",
                    "env": {},
                    "state": {"crag_gate": "INCORRECT", "iteration_count": 0},
                },
                {
                    "name": "incorrect_at_max_plan_outline",
                    "env": {},
                    "state": {"crag_gate": "INCORRECT", "iteration_count": 3},
                },
                {
                    "name": "missing_gate_defaults_incorrect_replan",
                    "env": {},
                    "state": {"iteration_count": 0},
                },
            ],
        },
        "v3": {
            "_should_search_gaps": [
                {
                    "name": "status_not_running_write_section",
                    "env": {},
                    "state": {"status": "complete", "gaps": ["g"], "gap_searches_done": 0},
                },
                {
                    "name": "gaps_under_cap_search",
                    "env": {},
                    "state": {"status": "running", "gaps": ["g1", "g2"], "gap_searches_done": 0},
                },
                {
                    "name": "gaps_at_cap_write_section",
                    "env": {},
                    "state": {"status": "running", "gaps": ["g1"], "gap_searches_done": 2},
                },
                {
                    "name": "no_gaps_write_section",
                    "env": {},
                    "state": {"status": "running", "gaps": [], "gap_searches_done": 0},
                },
                {
                    "name": "default_status_running_no_gaps_write_section",
                    "env": {},
                    "state": {"gaps": [], "gap_searches_done": 0},
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Env pinning
# ---------------------------------------------------------------------------
class _pinned_env:
    """Context manager: set exactly the given env slice, restore on exit."""

    def __init__(self, slice_: dict[str, str]):
        self._slice = slice_
        self._saved: dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self._slice.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, old in self._saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        return False


def _run_case(fn: Callable[[dict], str], case: dict[str, Any]) -> str:
    with _pinned_env(case.get("env", {})):
        return fn(dict(case["state"]))


# ---------------------------------------------------------------------------
# Record / replay
# ---------------------------------------------------------------------------
def _build_golden() -> dict[str, Any]:
    selectors = _all_selectors()
    cases = _cases()
    out: dict[str, Any] = {
        "schema": "polaris.graph_selector_fixtures/v1",
        "description": (
            "Phase 0A-5 replay fixtures for the 3 routed graph selectors "
            "(v1/v2/v3). Each case pins input state (+ any env the selector "
            "reads at call time) to the edge-name the production selector "
            "returns. Baseline 'before' for the Phase 3C compatibility matrix."
        ),
        "constants": _observed_constants(),
        "selectors": {},
    }
    for version in ("v1", "v2", "v3"):
        out["selectors"][version] = {}
        for sel_name, sel_cases in cases[version].items():
            fn = selectors[version][sel_name]
            recorded = []
            for case in sel_cases:
                expected = _run_case(fn, case)
                recorded.append(
                    {
                        "name": case["name"],
                        "env": case.get("env", {}),
                        "state": case["state"],
                        "expected_edge": expected,
                    }
                )
            out["selectors"][version][sel_name] = recorded
    return out


def _dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def record(force: bool) -> int:
    golden = _build_golden()
    text = _dumps(golden)
    if _GOLDEN.exists() and not force:
        existing = _GOLDEN.read_text(encoding="utf-8")
        if existing != text:
            sys.stderr.write(
                "REFUSING to overwrite existing golden with a DIFFERENT recording "
                "without --force. This is a routing change — investigate.\n"
            )
            return 3
    _GOLDEN.write_text(text, encoding="utf-8")
    n = sum(
        len(cases)
        for ver in golden["selectors"].values()
        for cases in ver.values()
    )
    print(f"[record] wrote {n} selector fixtures across v1/v2/v3 -> {_GOLDEN.name}")
    return 0


def replay() -> int:
    if not _GOLDEN.exists():
        sys.stderr.write(f"golden fixture missing: {_GOLDEN}\n")
        return 3
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))

    # Constants must still match what the fixtures were captured under.
    now = _observed_constants()
    mismatches: list[str] = []
    for k, v in golden.get("constants", {}).items():
        if now.get(k) != v:
            mismatches.append(f"constant {k}: golden={v} now={now.get(k)}")

    selectors = _all_selectors()
    checked = 0
    for version, sels in golden["selectors"].items():
        for sel_name, cases in sels.items():
            fn = selectors[version][sel_name]
            for case in cases:
                got = _run_case(fn, case)
                checked += 1
                if got != case["expected_edge"]:
                    mismatches.append(
                        f"{version}.{sel_name}[{case['name']}]: "
                        f"golden={case['expected_edge']!r} got={got!r}"
                    )

    if mismatches:
        sys.stderr.write("SELECTOR REPLAY MISMATCH (routing regression):\n")
        for m in mismatches:
            sys.stderr.write(f"  - {m}\n")
        return 3
    print(f"[replay] all {checked} selector fixtures BYTE-IDENTICAL to golden (v1/v2/v3)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("record", "replay"), default="replay")
    ap.add_argument("--force", action="store_true", help="record: overwrite differing golden")
    args = ap.parse_args(argv)
    if args.mode == "record":
        return record(force=args.force)
    return replay()


if __name__ == "__main__":
    raise SystemExit(main())
