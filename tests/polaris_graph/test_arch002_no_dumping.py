"""I-arch-002 (#1246) — WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP (CLAUDE.md §-1.3).

P-W1 acceptance: under the master redesign flag PG_SWEEP_CREDIBILITY_REDESIGN the
relevance "floor" stops HARD-DROPPING below-floor rows — every scored row is KEPT
carrying its relevance as the surfaced ``selection_relevance`` weight (the live
236/589 cut is exactly this floor). Flag OFF => the exact legacy ``>= floor`` cut =>
byte-identical. The faithfulness engine is untouched (selection only ever SUBTRACTS
before generation; keeping MORE rows cannot fabricate).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
)


@dataclass
class _FakeSource:
    url: str
    tier: str


def _rows(n: int, tier: str, base: str, topic: str, start: int = 1) -> list[dict]:
    return [
        {
            "evidence_id": f"ev_{tier}_{i + start:03d}",
            "source_url": f"{base}/{tier}/{i + start}",
            "statement": f"Finding {i + start}: {topic}.",
            "direct_quote": f"Verbatim {i + start} discussing {topic}.",
            "tier": tier,
        }
        for i in range(n)
    ]


def _srcs(rows: list[dict]) -> list[_FakeSource]:
    return [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]


_QUESTION = "What is the efficacy of semaglutide for obesity weight loss in adults?"


def _mixed_rows() -> list[dict]:
    """5 on-topic rows (above floor) + 8 off-topic rows (below floor)."""
    rows: list[dict] = []
    rows += _rows(
        5, "T1", "http://nejm.org",
        "semaglutide obesity weight loss adults efficacy trial",
    )
    rows += _rows(
        8, "T5", "http://blog.example.com",
        "unrelated quantum astronomy nebula filler text", start=100,
    )
    return rows


def _select(rows: list[dict]):
    return select_evidence_for_generation(
        research_question=_QUESTION,
        protocol={"intervention": "semaglutide", "population": "obesity adults"},
        classified_sources=_srcs(rows),
        evidence_rows=rows,
        max_rows=1000,          # high — isolate the FLOOR, not the cap
        relevance_floor=0.30,   # not-None => the floor branch (the 236/589 cut)
    )


def test_arch002_floor_off_drops_below_floor(monkeypatch) -> None:
    """Flag OFF (default): the legacy floor HARD-DROPS the off-topic below-floor
    rows. This is the live dumping behavior."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    rows = _mixed_rows()
    res = _select(rows)
    assert res.dropped_count > 0, "legacy floor must drop the off-topic rows"
    assert len(res.selected_rows) < len(rows)


def test_arch002_floor_on_keeps_all_as_weight(monkeypatch) -> None:
    """Flag ON: WEIGHT-don't-FILTER — every row is KEPT, none dropped at the floor,
    each carrying its relevance score as the surfaced ``selection_relevance`` weight."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    rows = _mixed_rows()
    res = _select(rows)
    assert res.dropped_count == 0, "redesign: the floor must not hard-drop any row"
    assert len(res.selected_rows) == len(rows), "every fetched row must flow through"
    assert all("selection_relevance" in r for r in res.selected_rows), (
        "kept rows must carry the relevance weight surface"
    )
