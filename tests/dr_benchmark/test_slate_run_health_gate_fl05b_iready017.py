"""I-ready-017 FL-05b (#1137) — offline tests for activating the FL-05 (#1124) run-health backstop
in the Gate-B full-capability slate.

NO network, NO spend. Covers:
  * the slate FORCE-ONs PG_RUN_HEALTH_GATE even when the process env presets it to "0"
    (a conservative .env=0 must NOT win — operator no-downgrade directive);
  * the fail-closed preflight raises RuntimeError naming PG_RUN_HEALTH_GATE if it is off after the
    slate is applied (a paid run can never start with the backstop silently disabled);
  * BEHAVIORAL (§-1.1): the activated flag actually changes compute_run_health_gate's decision — a
    would-be-SUCCESS run whose force-enabled STORM did NOT fire (firing_status=attempted_empty)
    overrides to abort_discovery_degraded ONLY when the gate is on; an already-held status is
    untouched. This proves the activation is wired to real behavior, not just a string in a set.

FL-05 only PROMOTES the existing advisory firing-warning to a gating abort of a would-be success — it
never weakens a faithfulness gate (strict_verify / provenance / 4-role / two-family all unchanged).

Hermetic: env snapshotted/restored so a forced flag does not leak into sibling tests.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_FLOORS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    load_locked_questions,
    preflight_full_capability,
    run_gate_b_query,
)
from scripts.run_honest_sweep_r3 import compute_run_health_gate, make_feature_telemetry

_FLAG = "PG_RUN_HEALTH_GATE"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- presence in the slate

def test_run_health_gate_in_slate_force_on_and_required():
    """FL-05b wires the flag into all three structures (the activation contract)."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_FLAG) == "1"
    assert _FLAG in _BENCHMARK_FORCE_ON_FLAGS
    assert _FLAG in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


# --------------------------------------------------------------------------- force-on over preset 0

def test_slate_force_ons_run_health_gate_over_preset_zero():
    """An explicit PG_RUN_HEALTH_GATE=0 in the process env must NOT survive the slate (the I-cap-005
    P1-1 force-on pattern: a conservative operator value cannot silently disable the backstop)."""
    os.environ[_FLAG] = "0"
    apply_full_capability_benchmark_slate()
    assert os.environ.get(_FLAG) == "1", "slate must force PG_RUN_HEALTH_GATE on over preset 0"


def test_run_gate_b_query_force_ons_run_health_gate(monkeypatch):
    """End-to-end through run_gate_b_query (run_one_query faked — no pipeline, no spend): the flag is on
    after the query path applies the slate."""
    os.environ[_FLAG] = "0"

    async def _fake_run_one_query(q, out_root, **kwargs):
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)
    q = load_locked_questions(("drb_72_ai_labor",))[0]
    summary = asyncio.run(
        run_gate_b_query(q, Path("outputs/__test_unused__"), transport=object())
    )
    assert summary["status"] == "success"
    assert os.environ.get(_FLAG) == "1", "run_gate_b_query must force PG_RUN_HEALTH_GATE on"


# --------------------------------------------------------------------------- fail-closed preflight

def test_preflight_fails_closed_when_run_health_gate_off():
    """Slate applied but the backstop forced back off → preflight must raise naming the flag, aborting
    BEFORE any spend. Satisfy every OTHER required flag so the failure isolates to PG_RUN_HEALTH_GATE."""
    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ[_FLAG] = "0"  # the one under test

    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert _FLAG in str(exc.value)


# --------------------------------------------------------------------------- §-1.1 behavioral proof

def _degraded_success_telemetries():
    """A force-enabled STORM that did NOT fire (silent fallback to the Serper/S2 baseline) + an
    agentic feature that fired fine — the exact 2026-06-05 drb_72 smoke shape."""
    storm = make_feature_telemetry("storm", enabled=True, fired=False, firing_status="attempted_empty")
    agentic = make_feature_telemetry("agentic", enabled=True, fired=True, firing_status="fired")
    return [storm, agentic]


def test_activated_gate_aborts_would_be_success_degraded_run():
    """With the gate ON (as the slate sets it), a would-be-SUCCESS run whose force-enabled STORM did not
    fire overrides to abort_discovery_degraded. This is the backfire-guard the activation buys."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(), unified_status="success", gate_on=True
    )
    assert out["override_status"] == "abort_discovery_degraded"
    assert out["discovery_llm_degraded"] is True
    assert out["discovery_rounds_on_fallback"] == 1


def test_gate_off_ships_degraded_run_as_success():
    """The pre-FL-05b default: with the gate OFF, the SAME degraded run still ships as success (the
    silent downgrade FL-05b closes). Observability fields still surface, but no override."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(), unified_status="success", gate_on=False
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is True  # surfaced even when not gating


def test_activated_gate_never_overrides_an_already_held_status():
    """FL-05 only overrides a would-be SUCCESS. The 2026-06-05 smoke ended abort_four_role_release_held
    (D8 gate already held) — FL-05b must NOT touch that (no double-abort / status clobber)."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(),
        unified_status="abort_four_role_release_held",
        gate_on=True,
    )
    assert out["override_status"] is None


def test_activated_gate_passes_a_clean_run():
    """All force-enabled discovery features fired → no override even with the gate on (no false abort)."""
    storm = make_feature_telemetry("storm", enabled=True, fired=True, firing_status="fired")
    agentic = make_feature_telemetry("agentic", enabled=True, fired=True, firing_status="fired")
    out = compute_run_health_gate([storm, agentic], unified_status="success", gate_on=True)
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False


# --------------------------------------------------------------------------- I-fetch-002 (#1168)
# Lane budget: the four fetch lanes SUM to ~1000 sites/question (NOT 1000 + additive lanes).

_LANE_KNOBS = (
    "PG_SWEEP_FETCH_CAP",            # main Serper/S2/OpenAlex lane
    "PG_AGENTIC_BENCHMARK_URL_CAP",  # agentic-discovery harvest
    "PG_SWEEP_DEEPENER_URL_CAP",     # citation-snowball deepener
    "PG_R6_EXPAND_FETCH_CAP",        # R-6 completeness re-expansion
    "PG_STORM_URL_FETCH_CAP",        # STORM web-results seed lane (I-beatboth-fix-000 BB-006)
)


def test_four_fetch_lanes_sum_to_about_1000():
    """The operator budget: the WHOLE run fetches ~1000 sites/question, split across the fetch lanes
    that SUM to ~1000 — never 1000 (main) + additive lanes on top. I-beatboth-fix-000 (Codex P1)
    trimmed the main lane 800->740 to ABSORB the new STORM web-results seed lane (BB-006) so the total
    stays at the hard 1000 envelope (no ~1060 overshoot)."""
    vals = {k: int(_FULL_CAPABILITY_BENCHMARK_SLATE[k]) for k in _LANE_KNOBS}
    total = sum(vals.values())
    assert total == 1000, f"fetch budget must sum to ~1000, got {total} from {vals}"
    # And the exact split documented in the slate comment.
    assert vals == {
        "PG_SWEEP_FETCH_CAP": 740,
        "PG_AGENTIC_BENCHMARK_URL_CAP": 100,
        "PG_SWEEP_DEEPENER_URL_CAP": 60,
        "PG_R6_EXPAND_FETCH_CAP": 40,
        "PG_STORM_URL_FETCH_CAP": 60,
    }


def test_query_breadth_knobs_present_and_floor_guarded():
    """The surviving QUERY-BREADTH knob (PG_MAX_SUBQUERIES, the legacy-decompose count) is pinned in the
    slate AND floor-guarded so it cannot silently drift. It is a query count — NOT part of the ~1000-URL
    fetch sum.

    I-deepfix-001 (#1344) PURITY: PG_STORM_MAX_BENCHMARK_QUERIES is a KILLED-loser knob — STORM is dead.
    It is force-EXACT "0" in the slate and its floor is REMOVED (a 30-query floor would re-introduce a
    STORM knob; the NO-LOSER preflight gate A.2 asserts the floor is gone)."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_MAX_SUBQUERIES") == "15"
    assert _BENCHMARK_PREFLIGHT_FLOORS.get("PG_MAX_SUBQUERIES") == 15
    # STORM query cap: killed loser → slate "0", and NOT floor-guarded (the floor was removed with STORM).
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_STORM_MAX_BENCHMARK_QUERIES") == "0"
    assert "PG_STORM_MAX_BENCHMARK_QUERIES" not in _BENCHMARK_PREFLIGHT_FLOORS


def test_query_breadth_knobs_excluded_from_url_sum():
    """Guard the comment's arithmetic claim: the query-breadth knobs are NOT lanes in the URL sum."""
    assert "PG_STORM_MAX_BENCHMARK_QUERIES" not in _LANE_KNOBS
    assert "PG_MAX_SUBQUERIES" not in _LANE_KNOBS


def test_lane_floors_land_with_no_env_override():
    """With no operator/.env override (the I-fetch-002 baseline), the floor-applied slate lands the
    lowered lane values exactly (800/40), so the budget is honored, not silently masked-up."""
    for knob in _LANE_KNOBS:
        os.environ.pop(knob, None)
    apply_full_capability_benchmark_slate()
    assert int(os.environ["PG_SWEEP_FETCH_CAP"]) == 740
    assert int(os.environ["PG_R6_EXPAND_FETCH_CAP"]) == 40
    assert int(os.environ["PG_AGENTIC_BENCHMARK_URL_CAP"]) == 100
    assert int(os.environ["PG_SWEEP_DEEPENER_URL_CAP"]) == 60
    assert int(os.environ["PG_STORM_URL_FETCH_CAP"]) == 60


# --------------------------------------------------------------------------- I-fetch-002 (#1168)
# STORM UNDER-fire floor knob in the slate + behavioral wiring.

_STORM_MIN_FLAG = "PG_STORM_MIN_EFFECTIVE_QUERIES"


def test_storm_min_effective_queries_in_slate():
    """I-deepfix-001 (#1344) PURITY: STORM is a killed loser — its under-fire floor is neutralized to "0"
    in the slate (was "12"). A non-zero floor would let the run-health gate emit abort_discovery_degraded
    when the (correctly dead) STORM does not fire — the INVERTED-mandate self-abort the purity build kills.
    The NO-LOSER preflight gate A.3 asserts this value resolves to 0."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_STORM_MIN_FLAG) == "0"


def test_storm_min_effective_queries_neutralized_no_floor():
    """I-deepfix-001 (#1344) PURITY: STORM is dead, so its under-fire floor is REMOVED from
    _BENCHMARK_PREFLIGHT_FLOORS and the slate resolves the flag to "0" with no operator preset (no
    floor raises it up — a non-zero floor would re-introduce a STORM knob)."""
    assert _STORM_MIN_FLAG not in _BENCHMARK_PREFLIGHT_FLOORS
    os.environ.pop(_STORM_MIN_FLAG, None)
    apply_full_capability_benchmark_slate()
    assert int(os.environ[_STORM_MIN_FLAG]) == 0


def test_slate_storm_min_under_fire_abort_neutralized():
    """§-1.1 behavioral: I-deepfix-001 (#1344) PURITY neutralizes the STORM under-fire floor to "0", so
    feeding the slate value to compute_run_health_gate can NEVER emit abort_discovery_degraded on a STORM
    telemetry — proving the INVERTED-mandate self-abort is wired OFF, not just a "0" string in the slate.
    (With floor 0, `effective_query_count < 0` is never true, so the under-fire branch cannot fire even
    on the old collapse shape of 4 effective queries.)"""
    storm = make_feature_telemetry(
        "storm", enabled=True, fired=True, firing_status="fired", effective_query_count=4
    )
    out = compute_run_health_gate(
        [storm],
        unified_status="success",
        gate_on=True,
        storm_min_effective_queries=int(_FULL_CAPABILITY_BENCHMARK_SLATE[_STORM_MIN_FLAG]),
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False
