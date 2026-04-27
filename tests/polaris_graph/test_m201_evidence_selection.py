"""
BUG-M-201 regression tests: tier-balanced + relevance-ranked evidence
selection for generation.

Pre-fix: evidence_for_gen = evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]
(raw retrieval order). Gates saw 20 sources, generator got 4.
Post-fix (deep-dive R6): `select_evidence_for_generation()` does
deterministic tier+relevance selection and emits telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    EvidenceSelection,
    select_evidence_for_generation,
)


@dataclass
class _FakeSource:
    url: str
    tier: str


def _make_rows(
    n: int,
    tier: str,
    base_url: str,
    topic: str = "semaglutide obesity weight loss",
    start_idx: int = 1,
) -> list[dict]:
    """Build n evidence rows whose quotes mention `topic` so they score."""
    return [
        {
            "evidence_id": f"ev_{tier}_{i+start_idx:03d}",
            "source_url": f"{base_url}/{tier.lower()}/{i+start_idx}",
            "statement": f"Finding {i+start_idx}: {topic} (tier {tier}).",
            "direct_quote": f"Verbatim quote {i+start_idx} discussing {topic}.",
            "tier": tier,
        }
        for i in range(n)
    ]


def _make_sources(rows: list[dict]) -> list[_FakeSource]:
    return [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]


# ─────────────────────────────────────────────────────────────────
# 1. Selection prefers high-tier late-arriving evidence over low-tier prefix
# ─────────────────────────────────────────────────────────────────

def test_m201_generator_selection_not_raw_prefix() -> None:
    """First 20 rows are T7 (low tier), later rows are T1 (high tier).
    Raw-prefix selection would miss the T1 rows; tier-balanced should
    include them."""
    rows = []
    rows.extend(_make_rows(20, "T7", "http://blog.example.com", topic="unrelated filler"))
    rows.extend(_make_rows(5, "T1", "http://nejm.org",
                           topic="semaglutide obesity weight loss"))
    srcs = _make_sources(rows)

    result = select_evidence_for_generation(
        research_question="What is the efficacy of semaglutide for obesity weight loss?",
        protocol={"intervention": "semaglutide", "population": "obesity adults"},
        classified_sources=srcs,
        evidence_rows=rows,
        max_rows=10,
    )
    assert len(result.selected_rows) == 10
    # The selection must include at least one T1 row (high-value late-arriving)
    selected_tiers = {r["tier"] for r in result.selected_rows}
    assert "T1" in selected_tiers, (
        f"Selection must include high-tier late-arriving evidence. "
        f"Got tiers: {selected_tiers}"
    )
    # Full tier counts should reflect the full pool
    assert result.full_counts.get("T1", 0) == 5
    assert result.full_counts.get("T7", 0) == 20


# ─────────────────────────────────────────────────────────────────
# 2. Tier-balance: present high tiers get at least one slot (floor)
# ─────────────────────────────────────────────────────────────────

def test_m201_selection_tier_balances_present_tiers() -> None:
    """Pool has T1, T2, T5 evidence. Even with small max_rows, the
    selection should include at least one T1 if present."""
    rows = []
    rows.extend(_make_rows(1, "T1", "http://nejm.org"))
    rows.extend(_make_rows(1, "T2", "http://bmj.com"))
    rows.extend(_make_rows(20, "T5", "http://gartner.com"))
    srcs = _make_sources(rows)

    result = select_evidence_for_generation(
        research_question="semaglutide obesity",
        protocol={"intervention": "semaglutide"},
        classified_sources=srcs,
        evidence_rows=rows,
        max_rows=5,
    )
    # Present T1 and T2 must each get at least 1 slot.
    assert result.selected_counts.get("T1", 0) >= 1
    assert result.selected_counts.get("T2", 0) >= 1


# ─────────────────────────────────────────────────────────────────
# 3. Deterministic: equal scores → stable order
# ─────────────────────────────────────────────────────────────────

def test_m201_selector_is_stable_for_equal_scores() -> None:
    """With equal lexical relevance, ordering is by (tier_priority,
    -score, original_idx). Repeated calls produce the same result."""
    rows = _make_rows(10, "T3", "http://generic.org",
                      topic="identical content for all")
    srcs = _make_sources(rows)

    r1 = select_evidence_for_generation(
        research_question="identical",
        protocol={},
        classified_sources=srcs,
        evidence_rows=rows,
        max_rows=5,
    )
    r2 = select_evidence_for_generation(
        research_question="identical",
        protocol={},
        classified_sources=srcs,
        evidence_rows=rows,
        max_rows=5,
    )
    assert [r["evidence_id"] for r in r1.selected_rows] == [
        r["evidence_id"] for r in r2.selected_rows
    ]


# ─────────────────────────────────────────────────────────────────
# 4. Classified-source join: missing evidence row for a source OK
# ─────────────────────────────────────────────────────────────────

def test_m201_selection_joins_classified_sources_by_url() -> None:
    """A classified source with no matching evidence_row should
    contribute to corpus distribution (not here, that's a separate
    gate) but NOT crash the selector."""
    rows = _make_rows(5, "T1", "http://nejm.org")
    # Add a classified source whose URL doesn't appear in any evidence row
    srcs = _make_sources(rows) + [
        _FakeSource(url="http://starved-content.example.com", tier="T5"),
    ]
    result = select_evidence_for_generation(
        research_question="test",
        protocol={},
        classified_sources=srcs,
        evidence_rows=rows,
        max_rows=3,
    )
    assert len(result.selected_rows) == 3
    # The starved source should NOT appear in selected (no evidence row)
    selected_urls = {r["source_url"] for r in result.selected_rows}
    assert "http://starved-content.example.com" not in selected_urls


# ─────────────────────────────────────────────────────────────────
# 5. Empty pool / max_rows=0 / all-kept early exit
# ─────────────────────────────────────────────────────────────────

def test_m201_selection_empty_pool_returns_empty() -> None:
    result = select_evidence_for_generation(
        research_question="q",
        protocol={},
        classified_sources=[],
        evidence_rows=[],
        max_rows=20,
    )
    assert result.selected_rows == []
    assert result.dropped_count == 0


def test_m201_selection_max_rows_zero_returns_empty() -> None:
    rows = _make_rows(5, "T1", "http://x")
    result = select_evidence_for_generation(
        research_question="q",
        protocol={},
        classified_sources=_make_sources(rows),
        evidence_rows=rows,
        max_rows=0,
    )
    assert result.selected_rows == []


def test_m201_selection_pool_smaller_than_max_keeps_everything() -> None:
    """When pool <= max_rows, return everything. Still emit telemetry."""
    rows = _make_rows(3, "T2", "http://y")
    result = select_evidence_for_generation(
        research_question="q",
        protocol={},
        classified_sources=_make_sources(rows),
        evidence_rows=rows,
        max_rows=10,
    )
    assert len(result.selected_rows) == 3
    assert result.dropped_count == 0
    # M-26-era triage fix (Codex review): the strategy string was
    # renamed when M-46 ordering landed; assertion was stale.
    # Code at src/polaris_graph/retrieval/evidence_selector.py:583
    # now returns the suffixed version below.
    assert result.selection_strategy == "tier_balanced_v1_all_m46_ordered"


# ─────────────────────────────────────────────────────────────────
# 6. Manifest telemetry shape
# ─────────────────────────────────────────────────────────────────

def test_m201_manifest_records_evidence_selection_telemetry() -> None:
    """EvidenceSelection.to_dict() shape matches what manifest readers expect."""
    rows = _make_rows(10, "T1", "http://x") + _make_rows(10, "T5", "http://y")
    result = select_evidence_for_generation(
        research_question="q",
        protocol={},
        classified_sources=_make_sources(rows),
        evidence_rows=rows,
        max_rows=10,
    )
    d = result.to_dict()
    assert d["evidence_total"] == 20
    assert d["evidence_selected"] == 10
    assert d["selection_strategy"].startswith("tier_balanced_v1")
    assert "full_tier_counts" in d
    assert "selected_tier_counts" in d
    assert d["dropped_count"] == 10


def test_m201_orchestrator_uses_selector_not_prefix_slice() -> None:
    """Source check: run_one_query calls select_evidence_for_generation
    instead of the raw evidence_rows[:max_ev] slice."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    assert "select_evidence_for_generation" in source, (
        "Orchestrator must use tier-balanced selector, not raw prefix slice"
    )
    # The old raw slice should NOT be the source of evidence_for_gen.
    # (It may still appear as a string elsewhere, but the direct
    # assignment `evidence_for_gen = retrieval.evidence_rows[:max_ev]`
    # should be gone.)
    assert "evidence_for_gen = retrieval.evidence_rows[:max_ev]" not in source, (
        "Raw-prefix slice should be replaced by selector call"
    )
