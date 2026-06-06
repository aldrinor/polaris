"""Offline tests for I-ready-017 CANARY-01 (#1108): the behavioral pre-spend canary.

The drb_72 held run's preflight checked CONFIG + the 4 VERIFIER slugs but NOT the searcher/generator
generate_structured call shape (the FX-01-keystone 404 that silently killed discovery) nor a real
1-query search — a dead route was swallowed → a green run on dead discovery. behavioral_canary()
tests BEHAVIOR via real call shapes and FAILS CLOSED before spend.

NO network, NO spend: the probes are injectable, so the canary LOGIC is exercised with faked
alive/dead/empty results. Also pins the Gate-B slate wiring (force-on + required + the live call site).
Hermetic env. Mirrors tests/dr_benchmark/test_slate_cited_span_fx03_iready017.py conventions.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from scripts.dr_benchmark.pathB_run_gate import GateError, behavioral_canary
from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    preflight_full_capability,
)

_FLAG = "PG_BEHAVIORAL_CANARY"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- canary logic
# behavioral_canary is ASYNC (Codex iter-1 P1: awaited from run_gate_b_query's event loop; the
# default structured probe is a coroutine). The injected structured probe must be awaitable; the
# live-search probe stays sync. Each test drives it via asyncio.run.
async def _structured_ok() -> bool:
    return True


async def _structured_dead() -> bool:
    return False


async def _structured_404() -> bool:
    raise GateError("behavioral canary: structured-output probe got NoEndpointError ...")


def test_canary_passes_when_all_probes_alive(capsys):
    os.environ[_FLAG] = "1"
    asyncio.run(behavioral_canary(structured_output_probe=_structured_ok, live_search_probe=lambda: 3))
    assert "BEHAVIORAL_CANARY_OK" in capsys.readouterr().out


def test_canary_off_is_noop_probes_not_called():
    os.environ[_FLAG] = "0"
    called = {"structured": False, "search": False}

    async def _s():
        called["structured"] = True
        return True

    def _q():
        called["search"] = True
        return 3

    asyncio.run(behavioral_canary(structured_output_probe=_s, live_search_probe=_q))
    assert called == {"structured": False, "search": False}, "off must be a no-op (no probe calls)"


def test_canary_fails_closed_on_structured_output_dead():
    os.environ[_FLAG] = "1"
    with pytest.raises(GateError, match="structured-output"):
        asyncio.run(
            behavioral_canary(structured_output_probe=_structured_dead, live_search_probe=lambda: 3)
        )


def test_canary_propagates_structured_404_gateerror():
    """The default probe raises GateError on NoEndpointError (the FX-01-keystone 404 class); the
    canary must propagate it (fail closed), not swallow it."""
    os.environ[_FLAG] = "1"
    with pytest.raises(GateError, match="NoEndpointError"):
        asyncio.run(
            behavioral_canary(structured_output_probe=_structured_404, live_search_probe=lambda: 3)
        )


def test_canary_normalizes_arbitrary_probe_failure_to_gateerror():
    """Codex iter-1 P2: a non-GateError probe exception must normalize to the fail-closed GateError
    contract, not leak as an arbitrary exception."""
    os.environ[_FLAG] = "1"

    async def _boom():
        raise RuntimeError("network exploded")

    with pytest.raises(GateError, match="fail closed"):
        asyncio.run(behavioral_canary(structured_output_probe=_boom, live_search_probe=lambda: 3))


def test_canary_fails_closed_on_zero_live_sources():
    os.environ[_FLAG] = "1"
    with pytest.raises(GateError, match="0 live sources"):
        asyncio.run(
            behavioral_canary(structured_output_probe=_structured_ok, live_search_probe=lambda: 0)
        )


# --------------------------------------------------------------------------- slate wiring
def test_canary_is_in_slate_force_on_and_required():
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_FLAG) == "1"
    assert _FLAG in _BENCHMARK_FORCE_ON_FLAGS
    assert _FLAG in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_canary_force_on_over_preset_zero():
    os.environ[_FLAG] = "0"
    apply_full_capability_benchmark_slate()
    assert os.environ.get(_FLAG) == "1", "PG_BEHAVIORAL_CANARY not force-on over preset 0"


def test_preflight_fails_closed_when_canary_off():
    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ[_FLAG] = "0"
    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert _FLAG in str(exc.value)
