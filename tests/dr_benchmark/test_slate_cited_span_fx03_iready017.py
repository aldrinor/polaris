"""Offline tests for I-ready-017 FX-03 (#1107): PG_GATE_B_CITED_SPAN is ACTIVE on the authoritative
Gate-B launcher.

Codex FX-03 iter-1 continuing-P0: the cited-span windowing fix in roles/native_gate_b_inputs.py
defaults OFF, and run_gate_b.py never activated/preflighted it — so a normal Gate-B run still fed
WHOLE-record evidence to Sentinel/Judge, preserving BUG-02 (out-of-span false-accept). This pins the
wiring: the full-capability slate FORCE-ONs PG_GATE_B_CITED_SPAN over a preset "0", and the
fail-closed preflight raises (aborting BEFORE any spend) if it is off after the slate is applied.

NO network, NO spend. Hermetic: env snapshotted/restored. Mirrors
tests/dr_benchmark/test_slate_readiness_flags_iready016b.py conventions.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_EXACT_FLAGS,
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _BENCHMARK_SPAN_WINDOW_MAX_BYTES,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    load_locked_questions,
    preflight_full_capability,
    run_gate_b_query,
)

_FLAG = "PG_GATE_B_CITED_SPAN"
_WINDOW = "PG_GATE_B_SPAN_WINDOW_BYTES"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def test_cited_span_is_in_slate_force_on_and_required():
    """Static wiring: the flag must be in the slate (="1"), FORCE-ON (operator =0 cannot win), and a
    REQUIRED preflight flag (fail-closed)."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_FLAG) == "1"
    assert _FLAG in _BENCHMARK_FORCE_ON_FLAGS
    assert _FLAG in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_run_gate_b_query_force_ons_cited_span_over_preset_zero(monkeypatch):
    """run_gate_b_query must FORCE PG_GATE_B_CITED_SPAN ON even when the process env presets it to "0"
    (a conservative .env value must NOT restore the whole-doc out-of-span false-accept). run_one_query
    is faked so the real retrieval/generation pipeline (network + spend) never executes."""
    os.environ[_FLAG] = "0"  # preset OFF — the slate/force-on must beat this

    captured = {}

    async def _fake_run_one_query(q, out_root, **kwargs):
        captured["slug"] = q["slug"]
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)

    q = load_locked_questions(("drb_72_ai_labor",))[0]
    summary = asyncio.run(
        run_gate_b_query(q, Path("outputs/__test_unused__"), transport=object())
    )

    assert summary["status"] == "success"
    assert captured["slug"] == "drb_72_ai_labor"  # the recording fake actually ran (preflight passed)
    assert os.environ.get(_FLAG) == "1", "PG_GATE_B_CITED_SPAN not force-on over preset 0"


def test_preflight_fails_closed_when_cited_span_off():
    """Slate applied but PG_GATE_B_CITED_SPAN forced back off -> fail-closed preflight must raise,
    naming the flag, so the whole-doc false-accept can never reach a paid run."""
    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ[_FLAG] = "0"  # the one under test

    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert _FLAG in str(exc.value)


# --------------------------------------------------------------------------- window-size bound
def test_window_bytes_is_force_exact_over_oversized_operator_value():
    """Codex iter-2 P1: an operator/.env oversized window (=999999) must be FORCE-SET back to the
    400-byte policy by the slate — otherwise _cited_window_text expands to the whole record (BUG-02)."""
    assert _WINDOW in _BENCHMARK_FORCE_EXACT_FLAGS
    os.environ[_WINDOW] = "999999"  # operator tries to widen the window to whole-doc
    apply_full_capability_benchmark_slate()
    assert os.environ.get(_WINDOW) == "400", "oversized window was not force-exacted to the policy"


def test_preflight_fails_closed_on_oversized_window():
    """Defense-in-depth: if the cited-span flag is on but the window exceeds the ceiling, the
    fail-closed preflight must raise (a whole-record window can never reach a paid run)."""
    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ[_FLAG] = "1"
    os.environ[_WINDOW] = str(_BENCHMARK_SPAN_WINDOW_MAX_BYTES + 1)  # just over the ceiling

    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert _WINDOW in str(exc.value)
