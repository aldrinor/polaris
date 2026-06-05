"""Offline tests for the I-ready-016b (#1097) readiness faithfulness flags in the Gate-B slate.

NO network, NO spend anywhere. Covers:
  * run_gate_b_query FORCE-ONs the three readiness faithfulness flags
    (PG_USE_SAFETY_REFUSAL / PG_SWEEP_NLI_CONFLICT / PG_SWEEP_TABLE_CELL_VERIFY) even when the
    process env presets them to "0" — a conservative .env=0 must NOT win (operator no-downgrade);
  * the fail-closed preflight raises RuntimeError (aborting BEFORE any spend) naming a flag if any of
    the three is off AFTER the slate is applied.

These flags only ADD a faithfulness layer (safety-refusal classifier / NLI semantic-conflict /
table-cell numeric verify) — a gate is only ever STRENGTHENED here, never weakened.

Hermetic: env is snapshotted/restored (the _isolate_env autouse fixture) so a forced flag does not
leak into sibling tests. Mirrors tests/dr_benchmark/test_run_gate_b_cli.py conventions.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    apply_full_capability_benchmark_slate,
    load_locked_questions,
    main,  # imported for parity with the sibling CLI test module conventions
    preflight_full_capability,
    run_gate_b_query,
)

# The three readiness faithfulness flags activated by I-ready-016b (#1097).
_READINESS_FLAGS = (
    "PG_USE_SAFETY_REFUSAL",
    "PG_SWEEP_NLI_CONFLICT",
    "PG_SWEEP_TABLE_CELL_VERIFY",
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so a forced readiness flag (or the
    full-capability slate) does not leak into sibling tests."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- force-on

def test_run_gate_b_query_force_ons_readiness_flags_over_preset_zero(monkeypatch):
    """run_gate_b_query must FORCE the three readiness faithfulness flags ON even when the process env
    presets them to "0" (a conservative .env value must NOT win — operator no-downgrade directive).
    run_one_query is monkeypatched to a recording async fake so the real retrieval/generation pipeline
    (network + spend) never executes; an injected fake transport means no real transport is built."""
    # Preset all three OFF in the process env — the slate/force-on must beat this.
    for flag in _READINESS_FLAGS:
        os.environ[flag] = "0"

    captured = {}

    async def _fake_run_one_query(q, out_root, **kwargs):
        captured["q"] = q
        captured["kwargs"] = kwargs
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)

    q = load_locked_questions(("drb_72_ai_labor",))[0]
    fake_transport = object()  # never invoked — run_one_query is faked
    summary = asyncio.run(
        run_gate_b_query(q, Path("outputs/__test_unused__"), transport=fake_transport)
    )

    assert summary["status"] == "success"
    # The recording fake actually ran (proves run_gate_b_query reached the force-on lines + preflight).
    assert captured["q"]["slug"] == "drb_72_ai_labor"
    # Force-on beat the preset "0" for all three readiness faithfulness flags.
    for flag in _READINESS_FLAGS:
        assert os.environ.get(flag) == "1", f"{flag} not force-on over preset 0"


# --------------------------------------------------------------------------- fail-closed preflight

@pytest.mark.parametrize("off_flag", _READINESS_FLAGS)
def test_preflight_fails_closed_when_a_readiness_flag_is_off(off_flag):
    """With the full-capability slate applied but ONE readiness flag forced back off, the fail-closed
    preflight must raise RuntimeError naming that flag — so a silently-downgraded faithfulness layer can
    never reach a paid run. Apply the slate first (matches the run order), then turn the one flag off."""
    apply_full_capability_benchmark_slate()
    # run_gate_b_query (not the slate) sets the feature flags the preflight requires, so satisfy EVERY
    # required flag here to isolate the failure to off_flag — otherwise the preflight trips on the first
    # unset required flag (e.g. PG_DEPTH_ANNOTATION_IN_BENCHMARK) instead of the readiness flag under test.
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    # The binding-verifier enforce mode is also required by the preflight (set by the slate to "enforce",
    # but make it explicit so this test stays independent of slate ordering).
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    # Now turn OFF only the readiness flag under test — the preflight must name exactly it.
    os.environ[off_flag] = "0"

    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert off_flag in str(exc.value)
