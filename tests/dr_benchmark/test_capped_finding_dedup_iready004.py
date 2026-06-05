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
    assert s.get("PG_CAPPED_FINDING_DEDUP") == "1"
    assert s.get("PG_RELEVANCE_FLOOR") == "0.30"
    # Both flags are REQUIRED by preflight — capped mode cannot be silently off (would regress #1070).
    assert "PG_USE_FINDING_DEDUP" in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert "PG_CAPPED_FINDING_DEDUP" in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
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
    assert os.environ["PG_CAPPED_FINDING_DEDUP"] == "1"


def _set_min_passing_env() -> None:
    """The minimum env for preflight_full_capability to reach the PG_RELEVANCE_FLOOR check."""
    for k, v in {
        "PG_SWEEP_FETCH_CAP": "1000", "PG_SWEEP_MAX_SERPER": "100", "PG_SWEEP_MAX_S2": "100",
        "PG_STORM_ENABLED_IN_BENCHMARK": "1", "PG_SWEEP_EVIDENCE_DEEPENER": "1",
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1", "PG_AGENTIC_SEARCH_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1", "PG_ENABLE_TOOL_TRACKER": "1",
        "PG_USE_FINDING_DEDUP": "1", "PG_CAPPED_FINDING_DEDUP": "1",
        "PG_STRICT_VERIFY_ENTAILMENT": "enforce", "PG_MOST_MAX_EVIDENCE": "800",
        "PG_LIVE_MAX_EV_TO_GEN": "150",
    }.items():
        os.environ[k] = v
    from src.polaris_graph.llm.openrouter_client import set_max_cost_per_run
    set_max_cost_per_run(25.0)


@pytest.mark.parametrize("bad", ["1.5", "0", "-0.2", "abc"])
def test_preflight_rejects_bad_relevance_floor(_env_snapshot, bad):
    # Codex brief P1-2: a malformed/out-of-range floor fails CLOSED before any spend.
    _set_min_passing_env()
    os.environ["PG_RELEVANCE_FLOOR"] = bad
    with pytest.raises(RuntimeError, match="PG_RELEVANCE_FLOOR"):
        preflight_full_capability()


def test_preflight_accepts_valid_relevance_floor(_env_snapshot):
    _set_min_passing_env()
    os.environ["PG_RELEVANCE_FLOOR"] = "0.30"
    preflight_full_capability()   # must not raise


def test_capped_dedup_composition_respects_cap():
    # The run_one_query capped block = dedup_by_finding(floored base) -> select_evidence(top max_rows).
    # Build a deduped pool larger than the cap and assert the tier-balanced top-max_rows truncation
    # keeps the generator pool <= PG_LIVE_MAX_EV_TO_GEN (so #1070's cap is preserved under finding-dedup).
    from src.polaris_graph.authority.data_loader import load_authority_data
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding

    gov = load_authority_data()["psl_gov_suffixes"]
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
    deduped = dedup_by_finding(rows, gov_suffixes=gov).deduped_rows
    assert len(deduped) <= len(rows)   # dedup is collapsing-or-equal (never adds rows)

    max_rows = 5
    sel = select_evidence_for_generation(
        research_question="HbA1c reduction diabetes trial",
        protocol=None,
        classified_sources=[],
        evidence_rows=deduped,
        max_rows=max_rows,
        relevance_floor=None,   # the tier-balanced top-max_rows cap path (NOT the no-cap floor mode)
    )
    assert 0 < len(sel.selected_rows) <= max_rows   # CAP holds — #1070's PG_LIVE_MAX_EV_TO_GEN preserved
