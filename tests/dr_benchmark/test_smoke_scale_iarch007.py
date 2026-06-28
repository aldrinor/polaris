"""I-arch-007 --smoke-scale flag: small-scale FAST benchmark mode for run_gate_b.py.

Locks the contract: smoke_scale=True force-shrinks INPUT breadth + timeout backstops (bypassing the
~1000-URL FLOOR) for a ~15-20 min plumbing run; smoke_scale=False is byte-identical to a full run;
and the override touches NO faithfulness gate / the A20 funnel / the 4-role seam activation.
"""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _restore_env():
    """apply_full_capability_benchmark_slate() mutates os.environ DIRECTLY (it is the production slate),
    so snapshot + restore the whole environment around each test — otherwise the smoke values
    (e.g. PG_PREFLIGHT_MIN_BREADTH=10) leak into sibling dr_benchmark tests run in the same process."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture
def gate_b():
    return importlib.import_module("scripts.dr_benchmark.run_gate_b")


def test_smoke_scale_on_forces_small_breadth_and_coherent_timeouts(gate_b, monkeypatch):
    # a clean low baseline so the FLOOR would raise UP — the smoke override must beat the floor
    for k in ("PG_SWEEP_FETCH_CAP", "PG_RUN_WALL_CLOCK_SEC", "PG_MAX_SUBQUERIES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "40")

    gate_b.apply_full_capability_benchmark_slate(smoke_scale=True)

    # input breadth shrunk (the 5 fetch lanes + query counts)
    assert os.environ["PG_SWEEP_FETCH_CAP"] == "20"
    assert os.environ["PG_SWEEP_DEEPENER_URL_CAP"] == "5"
    assert os.environ["PG_MAX_SUBQUERIES"] == "4"
    # I-deepfix-001 (#1344) PURITY: STORM is a killed loser — its smoke under-fire floor is neutralized
    # to "0" (full-slate is also "0"), so the smoke can never re-introduce a non-zero STORM knob that the
    # SLATE-PURITY gate would reject (and the run-health under-fire abort can never trip on the absent STORM).
    assert os.environ["PG_STORM_MIN_EFFECTIVE_QUERIES"] == "0"
    # the super-heavy preflight breadth floor must drop (default 100) or it aborts before the sweep
    assert os.environ["PG_PREFLIGHT_MIN_BREADTH"] == "10"
    assert os.environ["PG_STORM_PERSPECTIVES_COUNT"] == "3"
    assert os.environ["PG_MAX_COST_PER_RUN"] == "10"  # synced to the live module too
    # things the smoke DEPENDS on (must be present): A20 funnel OPEN (slate, untouched),
    # reasoning effort medium (mirror blanks at xhigh), forensic capture on
    assert os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] == "1"
    assert os.environ["PG_FOUR_ROLE_REASONING_EFFORT"] == "medium"
    assert os.environ["PG_CAPTURE_RAW_LLM_IO"] == "1"
    # timeout hierarchy strictly increasing: per-call < generator < section < seam < run-wall
    vals = [
        int(os.environ[k])
        for k in (
            "PG_VERIFIER_LLM_TIMEOUT_SECONDS",
            "PG_GENERATOR_LLM_TIMEOUT_SECONDS",
            "PG_SECTION_WALLCLOCK_SECONDS",
            "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS",
            "PG_RUN_WALL_CLOCK_SEC",
        )
    ]
    assert vals == sorted(vals) and len(set(vals)) == len(vals), f"incoherent hierarchy: {vals}"


def test_smoke_scale_off_is_full_breadth_byte_identical(gate_b, monkeypatch):
    monkeypatch.delenv("PG_SWEEP_FETCH_CAP", raising=False)
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "40")
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    # default OFF: the full-capability FLOOR lands (~1000-URL budget), NOT the smoke value
    assert os.environ["PG_SWEEP_FETCH_CAP"] == "740"


_CAPACITY_FLOOR_MARKERS = ("SILENTLY THROTTLED", "silently throttling", "< full-capability floor",
                           "< $", "GENERATOR_TIMEOUT_SECONDS=")


def test_preflight_smoke_skips_capacity_floors_only(gate_b, monkeypatch):
    """smoke_scale=True must NOT trip the CAPACITY floors (breadth/cost/timeout) — they are
    deliberately small for a smoke — while smoke_scale=False DOES (a full run with throttled values is
    the ~40-URL bug). The faithfulness/feature checks are unconditional (a bare unit env without the
    box .env still trips one of those AFTER the capacity floors — which itself proves the floors were
    skipped, since the smoke run reached past them)."""
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "40")
    # The F07 binding-faithfulness gate (assert_faithfulness_slate_or_fail) runs BEFORE the capacity
    # floors and is a no-op UNLESS PG_BENCHMARK_STRICT_GATES is truthy — but it then requires the matched
    # set (PG_SWEEP_NLI_CONFLICT truthy + PG_STRICT_VERIFY_ENTAILMENT=enforce). A sibling test can leak
    # PG_BENCHMARK_STRICT_GATES=1 with PG_SWEEP_NLI_CONFLICT='' into the process env, which would make F07
    # raise FIRST and mask the CAPACITY-floor error this test is isolating. run_gate_b_query always sets
    # these three together for a real run, so mirror that here: set the consistent F07 slate so the gate
    # PASSES and the throttle below reaches the capacity floor for the right reason (leak-robust baseline).
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=True)
    # full mode: the smoke breadth/cost/timeout values trip a CAPACITY floor
    with pytest.raises(RuntimeError) as full_exc:
        gate_b.preflight_full_capability(smoke_scale=False)
    assert any(m in str(full_exc.value) for m in _CAPACITY_FLOOR_MARKERS), \
        f"full-mode preflight did not trip a capacity floor (got: {full_exc.value})"
    # smoke mode: it must get PAST every capacity floor (it may still require a box-.env feature flag,
    # but it must NOT fail for a capacity-floor reason)
    try:
        gate_b.preflight_full_capability(smoke_scale=True)
    except RuntimeError as smoke_exc:
        assert not any(m in str(smoke_exc) for m in _CAPACITY_FLOOR_MARKERS), \
            f"smoke preflight still tripped a capacity floor: {smoke_exc}"


def test_smoke_defrosts_4role_transport_effort_and_timeout(gate_b, monkeypatch):
    """The 4-role transport freezes reasoning effort + per-call timeout at import; the slate must sync
    the smoke values to the live module globals (else the mirror runs xhigh and blanks/stalls)."""
    import importlib
    rt = importlib.import_module("src.polaris_graph.roles.openrouter_role_transport")
    monkeypatch.setenv("PG_MAX_COST_PER_RUN", "40")
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=True)
    assert rt._REASONING_EFFORT == "medium", "smoke reasoning effort did not reach the transport global"
    assert rt._TIMEOUT_SECONDS == 300, "smoke verifier timeout did not reach the transport global"
    # the ladder must re-derive off the new effort (MAX-first), not the frozen xhigh
    assert rt._VERIFIER_EFFORT_LADDER[0] == "medium"


def test_smoke_override_touches_no_faithfulness_gate_or_funnel(gate_b):
    overrides = gate_b._SMOKE_SCALE_OVERRIDES
    # the funnel flag + 4-role activation must NOT be in the override (they live in the slate / the
    # enable_four_role_mode() call — the smoke must never disable or alter them)
    assert "PG_SWEEP_CREDIBILITY_REDESIGN" not in overrides
    assert "PG_FOUR_ROLE_MODE" not in overrides
    # no strict_verify / NLI / entailment THRESHOLD or section-fraction gate is shrunk
    for key in overrides:
        for banned in ("STRICT_VERIFY", "NLI_CONFLICT", "ENTAILMENT_THRESHOLD",
                       "MIN_VERIFIED_SECTION_FRACTION", "PROVENANCE_MIN"):
            assert banned not in key, f"smoke override touches a faithfulness gate: {key}"
