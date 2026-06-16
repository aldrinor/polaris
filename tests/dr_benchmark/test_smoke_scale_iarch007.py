"""I-arch-007 --smoke-scale flag: small-scale FAST benchmark mode for run_gate_b.py.

Locks the contract: smoke_scale=True force-shrinks INPUT breadth + timeout backstops (bypassing the
~1000-URL FLOOR) for a ~15-20 min plumbing run; smoke_scale=False is byte-identical to a full run;
and the override touches NO faithfulness gate / the A20 funnel / the 4-role seam activation.
"""
from __future__ import annotations

import importlib
import os

import pytest


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
