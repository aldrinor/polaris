"""I-ready-004 (#1078) — CAPPED finding-dedup for Gate-B (offline, no model, no spend).

The legacy PG_USE_FINDING_DEDUP relevance-floor mode is NO-CAP (keeps every row >= floor); at ~1000
URLs that bypasses #1070's PG_LIVE_MAX_EV_TO_GEN cap and re-floods the generator (Codex brief P1-1).
The Gate-B slate now turns on CAPPED finding-dedup: dedup near-duplicate findings, THEN enforce the
tier-balanced top-max_ev cap, with a FLOAT-safe PG_RELEVANCE_FLOOR (Codex brief P1-2). These tests
lock the config, the float-safe slate/preflight, and the dedup-then-cap invariant — all offline.
"""
from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    preflight_full_capability,
)


def test_capped_dedup_in_slate_and_required():
    s = _FULL_CAPABILITY_BENCHMARK_SLATE
    assert s.get("PG_USE_FINDING_DEDUP") == "1"
    # I-arch-007 #1264 DORMANT-CAP CLEANUP (operator: ZERO cap; §-1.3 BANNED number-forcing bolt-on):
    # PG_CAPPED_FINDING_DEDUP is now force-EXACT "0" (the re-cap-to-max_ev is GONE, not merely bypassed),
    # so it is NO LONGER required-truthy (a required-truthy flag set to 0 would fail the preflight). The
    # consolidated keep-all floor pool now flows to composition bounded only by the per-section token
    # budget + the UNCHANGED faithfulness gate (CONSOLIDATE-DON'T-DROP). Verified the ONLY consumer is the
    # two run_honest_sweep_r3 re-cap sites, both `and _capped_dedup`-gated, so 0 disables both unconditionally.
    assert s.get("PG_CAPPED_FINDING_DEDUP") == "0"
    assert s.get("PG_RELEVANCE_FLOOR") == "0.30"
    # Finding-dedup itself is still REQUIRED by preflight (consolidates near-dups); the CAP is not.
    assert "PG_USE_FINDING_DEDUP" in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert "PG_CAPPED_FINDING_DEDUP" not in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    # PG_CAPPED_FINDING_DEDUP is now force-EXACT (to "0"), no longer force-ON.
    assert "PG_CAPPED_FINDING_DEDUP" not in _BENCHMARK_FORCE_ON_FLAGS
    # The FLOAT floor must be force-SET (string), NOT int-floored (which would coerce 0.30 -> 0).
    assert "PG_RELEVANCE_FLOOR" in _BENCHMARK_FORCE_ON_FLAGS


@pytest.fixture
def _env_snapshot():
    """Save/restore os.environ around the slate/preflight (which mutate os.environ directly)."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def test_slate_does_not_int_coerce_relevance_floor(_env_snapshot):
    # Codex brief P1-2: the numeric FLOOR path int()-coerces, which would turn 0.30 -> 0 and break
    # parse_relevance_floor. PG_RELEVANCE_FLOOR is force-SET as a string instead.
    os.environ.pop("PG_RELEVANCE_FLOOR", None)
    apply_full_capability_benchmark_slate()
    assert os.environ["PG_RELEVANCE_FLOOR"] == "0.30"   # NOT "0"
    assert os.environ["PG_USE_FINDING_DEDUP"] == "1"
    # I-arch-007 #1264 DORMANT-CAP CLEANUP: the cap is force-EXACT to "0" (ZERO cap; §-1.3).
    assert os.environ["PG_CAPPED_FINDING_DEDUP"] == "0"


def _set_min_passing_env() -> None:
    """The minimum env for preflight_full_capability to reach the PG_RELEVANCE_FLOOR check.

    I-wire-001 (#1296): apply the full slate FIRST so the section-winner flags it now force-sets
    (the 6 wired BOOLEAN winners are preflight-required; the 4 STRING model-selector winners are
    value-equals-asserted) are present — otherwise preflight raises on a winner long before reaching
    the PG_RELEVANCE_FLOOR check this test targets. The explicit overrides below still win (applied
    after) for the flags this test pins.

    I-deepfix-001 (#1344) WINNERS-ONLY PURITY (STALE-BASELINE fix): the slate is now the winners-only
    baseline — it force-EXACTs every killed loser to "0" (STORM core/ingest/outline, agentic, evidence
    -deepener, query-decompose, IterResearch, research-planner). This helper used to RE-ARM three of them
    (PG_STORM_ENABLED_IN_BENCHMARK / PG_SWEEP_EVIDENCE_DEEPENER / PG_AGENTIC_SEARCH_IN_BENCHMARK) to "1"
    AFTER the slate, which now trips the NEW NO-LOSER preflight gate (the _BENCHMARK_PREFLIGHT_REQUIRED_OFF
    _FLAGS loop) LONG BEFORE the PG_RELEVANCE_FLOOR validator this test targets. Those re-arms are DELETED:
    apply_full_capability_benchmark_slate() already zeroes them and that winners-only baseline is exactly
    what the cert run uses. The remaining overrides are NON-losers: capacity floors + the preflight-required
    readiness/faithfulness flags + PG_CAPPED_FINDING_DEDUP. PG_CAPPED_FINDING_DEDUP is force-EXACT "0" in
    the slate (a dormant cap per I-arch-007 #1264, NOT a NO-LOSER-gated flag — it is in neither
    _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS nor the NO-LOSER structural loser list), but the
    PG_RELEVANCE_FLOOR validator (run_gate_b.py:2581) only fires when it is truthy. So this helper sets it
    "1" purely to ARM that validator — the single perturbation this test family protects — without
    violating winners-only purity (it trips no purity gate; verified offline).
    """
    apply_full_capability_benchmark_slate()
    for k, v in {
        "PG_SWEEP_FETCH_CAP": "1000", "PG_SWEEP_MAX_SERPER": "100", "PG_SWEEP_MAX_S2": "100",
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1", "PG_ENABLE_TOOL_TRACKER": "1",
        # I-ready-016b (#1097): the 3 readiness faithfulness flags are now preflight-required.
        "PG_USE_SAFETY_REFUSAL": "1", "PG_SWEEP_NLI_CONFLICT": "1", "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        # PG_USE_FINDING_DEDUP is the surviving WINNER (consolidates near-dups); PG_CAPPED_FINDING_DEDUP="1"
        # is the dormant-cap flag, set here ONLY to arm the PG_RELEVANCE_FLOOR validator (see docstring).
        "PG_USE_FINDING_DEDUP": "1", "PG_CAPPED_FINDING_DEDUP": "1",
        "PG_STRICT_VERIFY_ENTAILMENT": "enforce", "PG_MOST_MAX_EVIDENCE": "800",
        "PG_LIVE_MAX_EV_TO_GEN": "1500", "PG_SWEEP_ANALYST_SYNTHESIS": "0",
    }.items():
        os.environ[k] = v
    from src.polaris_graph.llm.openrouter_client import set_max_cost_per_run
    set_max_cost_per_run(25.0)


@pytest.mark.parametrize("bad", ["1.5", "0", "-0.2", "abc"])
def test_preflight_rejects_bad_relevance_floor(_env_snapshot, bad):
    # Codex brief P1-2: a malformed/out-of-range floor fails CLOSED before any spend.
    _set_min_passing_env()
    os.environ["PG_RELEVANCE_FLOOR"] = bad
    # I-deepfix-001 (#1344): offline=True skips ONLY the WINNER-FIRES W4/W5 GPU-host probes (a no-GPU CI box
    # legitimately has no CUDA) — every STRUCTURAL purity gate + the PG_RELEVANCE_FLOOR validator (which runs
    # BEFORE the W4 probe) stay unconditional, so this still proves the floor fails CLOSED before any spend.
    with pytest.raises(RuntimeError, match="PG_RELEVANCE_FLOOR"):
        preflight_full_capability(offline=True)


def test_preflight_accepts_valid_relevance_floor(_env_snapshot):
    _set_min_passing_env()
    os.environ["PG_RELEVANCE_FLOOR"] = "0.30"
    # I-deepfix-001 (#1344): offline=True (no-GPU CI box) — see the rejects test for the rationale.
    preflight_full_capability(offline=True)   # must not raise


def test_capped_finding_dedup_selection_respects_cap():
    # The shared helper = dedup_by_finding(floored base) -> tier-balanced top-max_ev. It is used by BOTH
    # the initial selection AND the saturation gap-round reselect (Codex diff-gate iter-1 P1-1). Build a
    # base larger than the cap and assert the helper returns <= max_ev (so #1070's cap is preserved
    # under finding-dedup) and is a real EvidenceSelection (so manifest['evidence_selection'] reflects it).
    from scripts.run_honest_sweep_r3 import _capped_finding_dedup_selection

    rows = [
        {
            "evidence_id": f"s{i}",
            "source_url": f"https://a{i}.example.com/x",
            "statement": f"HbA1c reduction was {1.0 + i * 0.01:.2f} percent in trial {i}.",
            "direct_quote": f"HbA1c fell {1.0 + i * 0.01:.2f}% (trial {i}).",
            "selection_relevance": 0.5,
            "authority_score": 1.0,
        }
        for i in range(40)
    ]
    max_ev = 5
    sel = _capped_finding_dedup_selection(
        base_rows=rows,
        classified_sources=[],
        research_question="HbA1c reduction diabetes trial",
        protocol=None,
        primary_trial_anchors=None,
        max_ev=max_ev,
    )
    assert 0 < len(sel.selected_rows) <= max_ev   # CAP holds — #1070's PG_LIVE_MAX_EV_TO_GEN preserved
    assert hasattr(sel, "to_dict")   # a real EvidenceSelection -> manifest telemetry reflects the cap


def test_both_selection_paths_use_capped_helper():
    # Codex diff-gate iter-1 P1-1: the cap must apply on EVERY selection path. Source check — both the
    # initial selection and the saturation gap-round reselect call _capped_finding_dedup_selection, so a
    # future refactor cannot silently re-introduce the uncapped gap-round path.
    import inspect

    import scripts.run_honest_sweep_r3 as sweep

    src = inspect.getsource(sweep.run_one_query)
    # exactly two guarded call sites (initial + gap-round); guard them on the capped flag.
    assert src.count("_capped_finding_dedup_selection(") >= 2
    # the gap-round reselect (_resel) must be re-capped before billing.
    assert "_resel = _capped_finding_dedup_selection(" in src
