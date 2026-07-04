"""Wave-B WS-2 (I-deepfix-001 #1344) — the winner slate on the PAID run path.

BEHAVIORAL, fixture-driven, OFFLINE (no model / GPU / network / spend). Two surfaces under test:

  1. ``scripts/run_honest_sweep_r3.py`` — the paid launcher's flag-resolution function
     ``apply_winner_slate_on_paid_path`` must force every confirmed default-OFF WINNER flag
     ``"1"`` under the default-ON kill-switch, and be a BYTE-IDENTICAL no-op when the kill-switch is
     OFF. We do NOT import run_honest_sweep_r3 (it pulls torch / sentence-transformers / live_retriever
     at module import). Instead we AST-extract ONLY the WS-2 constants + two functions from the real
     source and exec them in an isolated namespace with just ``os`` — a real test of the real code.

  2. ``scripts/operational_readiness_preflight.py`` — ``check_d1_paid_path_winner_slate`` must RED-fail
     a paid launch whose EFFECTIVE winner slate is not fully ON, and PASS when every flag is ``"1"``.
     The preflight module is stdlib-only at import (its heavy ``run_gate_b`` import lives inside
     functions), so it imports safely offline.

§-1.3: every flag is a WEIGHT / CONSOLIDATE knob (merge-only consolidation, additive cross-source
synthesis, within-basket qualifier elaboration, facet-routed enrichment placement, uncapped breadth
surface through the UNCHANGED strict_verify). None drops a source or adds a cap. The frozen
faithfulness engine is not touched by this workstream.
"""

from __future__ import annotations

import ast
import contextlib
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.operational_readiness_preflight as op  # noqa: E402

_LAUNCHER = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"

_EXPECTED_FLAGS = (
    "PG_CONSOLIDATION_NLI",
    "PG_CONSOLIDATION_NLI_PROSE",
    "PG_CROSS_SOURCE_SYNTHESIS",
    "PG_BREADTH_ENRICHMENT_ENABLED",
    # I-deepfix-001 Wave-2 DEPTH (D1/D4) additions to the paid slate.
    "PG_QUALIFIER_ELABORATION",
    "PG_ENRICHMENT_FACET_ROUTE",
)
_KILL_SWITCH = "PG_APPLY_WINNER_SLATE_ON_PAID_PATH"

# The WS-2 names to lift out of the launcher source (constants + the two functions).
_WANTED = {
    "_WINNER_SLATE_ON_PAID_PATH_ENV",
    "_PAID_PATH_WINNER_FLAGS",
    "winner_slate_on_paid_path_enabled",
    "apply_winner_slate_on_paid_path",
}


def _load_winner_slate_ns() -> dict:
    """Extract ONLY the WS-2 winner-slate definitions from the real launcher source and exec them in
    an isolated namespace holding just ``os``. This tests the ACTUAL source (a rename/edit is picked
    up) without importing the heavy module."""
    src = _LAUNCHER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    segments: list[str] = []
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
        if name in _WANTED:
            seg = ast.get_source_segment(src, node)
            if seg is not None:
                segments.append(seg)
    ns: dict = {"os": os}
    # Trusted first-party source, offline; the segments are in source (dependency) order.
    exec("\n\n".join(segments), ns)  # noqa: S102
    return ns


@contextlib.contextmanager
def _isolated_env(**overrides: str):
    """Snapshot + restore the WS-2 keys so a test's os.environ mutation never leaks."""
    keys = list(_EXPECTED_FLAGS) + [_KILL_SWITCH]
    snapshot = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    for k, v in overrides.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k in keys:
            if snapshot[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = snapshot[k]


# ---------------------------------------------------------------------------------------------
# 1. Launcher-side: apply_winner_slate_on_paid_path
# ---------------------------------------------------------------------------------------------

def test_launcher_slate_names_are_the_winners() -> None:
    ns = _load_winner_slate_ns()
    assert tuple(ns["_PAID_PATH_WINNER_FLAGS"]) == _EXPECTED_FLAGS
    assert ns["_WINNER_SLATE_ON_PAID_PATH_ENV"] == _KILL_SWITCH


def test_apply_sets_all_flags_when_killswitch_default() -> None:
    ns = _load_winner_slate_ns()
    with _isolated_env():  # kill-switch unset -> default ON; all winner flags unset
        applied = ns["apply_winner_slate_on_paid_path"]()
        assert applied == {f: "1" for f in _EXPECTED_FLAGS}
        for f in _EXPECTED_FLAGS:
            assert os.environ[f] == "1", f"{f} not force-set to '1'"


def test_apply_sets_all_flags_when_killswitch_explicit_on() -> None:
    ns = _load_winner_slate_ns()
    with _isolated_env(**{_KILL_SWITCH: "1"}):
        applied = ns["apply_winner_slate_on_paid_path"]()
        assert applied == {f: "1" for f in _EXPECTED_FLAGS}


def test_killswitch_off_is_byte_identical_noop() -> None:
    ns = _load_winner_slate_ns()
    # Seed a prior OFF on one flag + an unset on another to prove NOTHING is touched.
    with _isolated_env(**{_KILL_SWITCH: "0", "PG_CONSOLIDATION_NLI": "0"}):
        before = dict(os.environ)
        applied = ns["apply_winner_slate_on_paid_path"]()
        assert applied == {}
        assert dict(os.environ) == before  # byte-identical revert
        assert os.environ["PG_CONSOLIDATION_NLI"] == "0"  # NOT flipped to "1"
        assert "PG_BREADTH_ENRICHMENT_ENABLED" not in os.environ  # stayed unset


def test_killswitch_parse_matches_default_on_convention() -> None:
    ns = _load_winner_slate_ns()
    enabled = ns["winner_slate_on_paid_path_enabled"]
    for off_value in ("0", "false", "off", "no", "OFF", "False"):
        with _isolated_env(**{_KILL_SWITCH: off_value}):
            assert enabled() is False, f"{off_value!r} should disable the slate"
    for on_value in ("1", "true", "on", "yes"):
        with _isolated_env(**{_KILL_SWITCH: on_value}):
            assert enabled() is True, f"{on_value!r} should enable the slate"
    with _isolated_env():  # unset -> default ON
        assert enabled() is True


# ---------------------------------------------------------------------------------------------
# 2. Preflight-side: check_d1_paid_path_winner_slate (RED-gate a slate-OFF paid launch)
# ---------------------------------------------------------------------------------------------

def _flag_checks(results) -> list:
    return [r for r in results if r.check_id.startswith("D-1.paid_path.PG_")]


def test_preflight_red_when_all_winner_flags_off() -> None:
    # kill-switch OFF (auto-apply disabled) + all winner flags unset -> the paid run would ship the
    # slate OFF. Every winner-flag check RED-fails.
    env = {_KILL_SWITCH: "0"}
    results = op.check_d1_paid_path_winner_slate(env)
    flag_checks = _flag_checks(results)
    assert len(flag_checks) == len(_EXPECTED_FLAGS)
    assert all(r.is_red for r in flag_checks)
    assert [r.check_id for r in flag_checks] == [f"D-1.paid_path.{f}" for f in _EXPECTED_FLAGS]


def test_preflight_red_on_single_winner_flag_off() -> None:
    # Hand-set every winner flag ON except BREADTH, kill-switch OFF -> only BREADTH RED-fails.
    env = {_KILL_SWITCH: "0"}
    env.update({f: "1" for f in _EXPECTED_FLAGS})
    env["PG_BREADTH_ENRICHMENT_ENABLED"] = "0"  # the one that is OFF
    results = op.check_d1_paid_path_winner_slate(env)
    reds = [r for r in results if r.is_red and r.check_id.startswith("D-1.paid_path.PG_")]
    assert [r.check_id for r in reds] == ["D-1.paid_path.PG_BREADTH_ENRICHMENT_ENABLED"]


def test_preflight_green_when_all_flags_on() -> None:
    # Even with the auto-apply kill-switch OFF, a hand-set full slate PASSES.
    env = {_KILL_SWITCH: "0"}
    env.update({f: "1" for f in _EXPECTED_FLAGS})
    results = op.check_d1_paid_path_winner_slate(env)
    assert all(r.status == op.GREEN for r in _flag_checks(results))
    assert not any(r.is_red for r in results)  # incl. the launcher-applies gate


def test_preflight_green_when_killswitch_on_forces_flags() -> None:
    # The legitimate WS-2 launch: kill-switch default ON, flags unset -> the launcher force-sets them,
    # so the effective slate is fully ON. Must NOT false-RED.
    env: dict = {}
    results = op.check_d1_paid_path_winner_slate(env)
    assert all(r.status == op.GREEN for r in _flag_checks(results))


def test_preflight_launcher_applies_gate_is_wired_green() -> None:
    # The AST gate: run_honest_sweep_r3.main_async ACTUALLY calls apply_winner_slate_on_paid_path.
    results = op.check_d1_paid_path_winner_slate({})
    gate = [r for r in results if r.check_id == "D-1.paid_path.launcher_applies"]
    assert len(gate) == 1
    assert gate[0].status == op.GREEN


def test_preflight_wired_into_run_static_checks() -> None:
    # The new check is actually part of the static suite (not defined-but-unwired).
    import inspect

    src = inspect.getsource(op.run_static_checks)
    assert "check_d1_paid_path_winner_slate" in src
