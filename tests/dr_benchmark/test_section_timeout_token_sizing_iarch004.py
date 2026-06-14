"""I-arch-004 A2 (#1248) — section timeout + token-budget sizing (offline, no network).

The drb_72 run died when the SMOKE wall-clock (600s) killed the V30 narrative DeepSeek ``generate()``
mid-stream x2. The real Gate-B slate did not set ``PG_SECTION_WALLCLOCK_SECONDS`` /
``PG_GENERATOR_LLM_TIMEOUT_SECONDS`` / ``PG_SECTION_MAX_TOKENS`` at all, so a real run got the stale
module defaults (wall-clock OFF -> hang-forever; generator timeout 1800s sized for the old 16384
ceiling; section budget 16384). These tests prove the slate now floors all three to the data-grounded
values, FLOOR semantics keep a higher operator value, and preflight FAILS CLOSED on the smoke value.
"""

from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark import run_gate_b as g
from src.polaris_graph.llm import openrouter_client as _oc

_KEYS = ("PG_SECTION_MAX_TOKENS", "PG_GENERATOR_LLM_TIMEOUT_SECONDS", "PG_SECTION_WALLCLOCK_SECONDS")
_REQ_FLAGS = ("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "PG_AGENTIC_SEARCH_IN_BENCHMARK",
              "PG_NLI_IN_BENCHMARK", "PG_USE_SAFETY_REFUSAL", "PG_SWEEP_NLI_CONFLICT",
              "PG_SWEEP_TABLE_CELL_VERIFY")


@pytest.fixture(autouse=True)
def _restore_live_generator_timeout():
    """I-arch-005 B24 (#1257): every test here either calls the Gate-B slate (which syncs the
    LIVE generator-timeout module-global UP to 6500s via set_generator_timeout_seconds) or mutates
    it directly. With the B24 module default now 600s, leaving the global at 6500 leaks a stale-high
    value into ordering-sensitive siblings (e.g. test_lane_section_arch005_section_wallclock_default_on
    asserts wall(1800) > live-generator-timeout). Save + restore the live constant around EVERY test
    so this file is order-independent regardless of the module default."""
    _orig = _oc.get_generator_timeout_seconds()
    yield
    _oc.set_generator_timeout_seconds(_orig)


def _clear():
    for k in _KEYS:
        os.environ.pop(k, None)


def test_slate_floors_section_timeout_and_token_budget():
    _clear()
    g.apply_full_capability_benchmark_slate()
    assert int(os.getenv("PG_SECTION_MAX_TOKENS")) >= 64000
    assert int(os.getenv("PG_GENERATOR_LLM_TIMEOUT_SECONDS")) >= 6500
    assert int(os.getenv("PG_SECTION_WALLCLOCK_SECONDS")) >= 9000
    _clear()


def test_slate_raises_the_smoke_wallclock(monkeypatch):
    # the exact killer: PG_SECTION_WALLCLOCK_SECONDS=600 (smoke) must be raised to the >=9000 floor.
    _clear()
    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "600")
    g.apply_full_capability_benchmark_slate()
    assert int(os.getenv("PG_SECTION_WALLCLOCK_SECONDS")) >= 9000
    _clear()


def test_slate_keeps_higher_operator_value(monkeypatch):
    _clear()
    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "20000")  # operator wants longer
    g.apply_full_capability_benchmark_slate()
    assert int(os.getenv("PG_SECTION_WALLCLOCK_SECONDS")) == 20000  # no downgrade
    _clear()


def test_preflight_fails_closed_on_smoke_wallclock(monkeypatch):
    _clear()
    g.apply_full_capability_benchmark_slate()
    for f in _REQ_FLAGS:
        monkeypatch.setenv(f, "1")
    g.preflight_full_capability()  # full slate passes
    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "600")  # the drb_72 killer
    with pytest.raises(RuntimeError):
        g.preflight_full_capability()
    _clear()


def test_preflight_fails_closed_on_stale_section_budget(monkeypatch):
    _clear()
    g.apply_full_capability_benchmark_slate()
    for f in _REQ_FLAGS:
        monkeypatch.setenv(f, "1")
    g.preflight_full_capability()
    monkeypatch.setenv("PG_SECTION_MAX_TOKENS", "16384")  # the stale shadow default
    with pytest.raises(RuntimeError):
        g.preflight_full_capability()
    _clear()


def test_generator_timeout_wired_into_import_const_floors():
    # The generator timeout is read at import (before the slate), so a stale .env would freeze it.
    # The import-time-constant floor must guard it fail-loud.
    floors = {attr: floor for _, attr, floor in g._BENCHMARK_IMPORT_TIME_CONSTANT_FLOORS}
    assert floors.get("GENERATOR_TIMEOUT_SECONDS", 0) >= 6500


def test_slate_syncs_live_generator_timeout_constant(monkeypatch):
    # Codex A2-gate iter-1 P1: a stale low PG_GENERATOR_LLM_TIMEOUT_SECONDS frozen at openrouter_client
    # import must NOT survive as the live constant — the slate calls set_generator_timeout_seconds().
    from src.polaris_graph.llm import openrouter_client as oc

    _clear()
    monkeypatch.setenv("PG_GENERATOR_LLM_TIMEOUT_SECONDS", "600")  # the stale-low class
    oc.set_generator_timeout_seconds(600)  # simulate the frozen import-time constant
    g.apply_full_capability_benchmark_slate()
    assert oc.get_generator_timeout_seconds() >= 6500  # the LIVE constant was synced, not just env
    # (the autouse _restore_live_generator_timeout fixture restores the original live value)
    _clear()


def test_preflight_catches_stale_live_generator_timeout(monkeypatch):
    # Codex A2-gate iter-1 P1: preflight must read the LIVE constant, not just env — env=6500 but a
    # frozen live constant of 600 must still FAIL CLOSED.
    from src.polaris_graph.llm import openrouter_client as oc

    _clear()
    g.apply_full_capability_benchmark_slate()
    for f in _REQ_FLAGS:
        monkeypatch.setenv(f, "1")
    g.preflight_full_capability()  # passes with the synced constant
    oc.set_generator_timeout_seconds(600)  # frozen-stale constant despite env=6500
    with pytest.raises(RuntimeError):
        g.preflight_full_capability()
    # (the autouse _restore_live_generator_timeout fixture restores the original live value)
    _clear()
