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
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
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


# ---------------------------------------------------------------------------
# P-W4gen — generator per-section ROW cap (PG_MAX_EV_PER_SECTION) dissolves to a
# serialized CHARACTER budget under the redesign flag. OFF keeps the literal 30-row
# clamp byte-for-byte; ON lets a section carry MORE than 30 rows when the budget allows.
# ---------------------------------------------------------------------------

from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _build_deterministic_fallback_outline,
)


def _pool(n: int) -> list[dict]:
    """n short clinical-ish evidence rows (small serialized length so a generous char
    budget never trims them)."""
    return [
        {
            "evidence_id": f"ev_{i:03d}",
            "title": f"Trial {i} of semaglutide efficacy",
            "statement": f"Finding {i}: semaglutide reduced weight.",
            "direct_quote": f"Row {i}: semaglutide produced weight loss.",
            "tier": "T1",
        }
        for i in range(n)
    ]


def test_arch002_per_section_cap_off_holds_at_30(monkeypatch) -> None:
    """Legacy escape hatch (PG_GEN_ROW_CAPS=1): the per-section ROW cap holds at
    PG_MAX_EV_PER_SECTION=30. With 120 rows round-robin across 3 sections (40 each), each
    section is clamped to exactly 30 — the legacy FILTER-AND-CAP behavior, byte-identical.

    I-arch-005 B2/B3 (#1257): the char-budget path is now the DEFAULT for every caller, so
    the legacy row cap only fires under the explicit escape hatch (the cert preflight FAILS
    on it). This test opts into that legacy path to keep its byte-identical regression
    coverage; the new default (budget) is asserted by test_arch005_per_section_budget_*."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")  # restore the legacy row cap
    plans = _build_deterministic_fallback_outline(_pool(120), domain="clinical")
    assert plans, "fallback outline should build 3 sections from 120 rows"
    assert all(len(p.ev_ids) == 30 for p in plans), (
        f"escape-hatch: every section must be clamped to 30 rows; got "
        f"{[len(p.ev_ids) for p in plans]}"
    )


def test_arch002_per_section_cap_on_exceeds_30_by_char_budget(monkeypatch) -> None:
    """Flag ON: the ROW cap dissolves into a CHARACTER budget. With 120 short rows
    round-robin across 3 sections (40 each) and a generous char budget, a section now
    carries MORE than 30 rows — all 40 flow through (CONSOLIDATE-keep-all)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    monkeypatch.delenv("PG_SECTION_EV_CHAR_BUDGET", raising=False)  # default ~120K chars
    plans = _build_deterministic_fallback_outline(_pool(120), domain="clinical")
    assert plans, "fallback outline should build 3 sections from 120 rows"
    assert any(len(p.ev_ids) > 30 for p in plans), (
        f"ON: at least one section must exceed the legacy 30-row cap under the char "
        f"budget; got {[len(p.ev_ids) for p in plans]}"
    )
    # All 40 round-robin rows per section fit the generous default budget.
    assert all(len(p.ev_ids) == 40 for p in plans), (
        f"ON: every short row must flow through (no row drop); got "
        f"{[len(p.ev_ids) for p in plans]}"
    )


def test_arch002_per_section_char_budget_trims_by_chars_not_rows(monkeypatch) -> None:
    """Flag ON with a TIGHT char budget: the section keeps rows until the char budget
    is reached — a COUNT, not a fixed row cap. Proves the bound is characters."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    pool = _pool(120)
    # Each row serializes to len(statement)+len(direct_quote). Measure row 0 and set a
    # budget that admits ~5 rows, proving char-budget trimming (not the 30-row cap).
    per_row = len(pool[0]["statement"]) + len(pool[0]["direct_quote"])
    monkeypatch.setenv("PG_SECTION_EV_CHAR_BUDGET", str(per_row * 5))
    plans = _build_deterministic_fallback_outline(pool, domain="clinical")
    assert plans
    # Char-bounded: well under both the 40 round-robin rows and the legacy 30 cap.
    assert all(2 <= len(p.ev_ids) <= 7 for p in plans), (
        f"tight char budget must trim by chars (~5 rows), not the row cap; got "
        f"{[len(p.ev_ids) for p in plans]}"
    )


# ---------------------------------------------------------------------------
# P-W2scope (Codex Slice-A P1) — the three #1244 scope gates WEIGHT/CLUSTER under
# the flag instead of DROPPING. OFF keeps the exact prior drop (byte-identical).
# ---------------------------------------------------------------------------

from src.polaris_graph.retrieval.evidence_selector import (  # noqa: E402
    _apply_scope_denylist,
    prefer_journal_over_arxiv,
)


def _scored_pair():
    return [
        (0, 0.50, "T1", {"source_url": "https://nejm.org/x"}),
        (1, 0.40, "T5", {"source_url": "https://facebook.com/y"}),
    ]


def test_arch002_denylist_off_drops(monkeypatch) -> None:
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_SCOPE_DENYLIST_DOMAINS", "facebook.com")
    kept, n_dropped, _ = _apply_scope_denylist(_scored_pair(), None)
    assert n_dropped == 1 and len(kept) == 1


def test_arch002_denylist_on_keeps_with_weight(monkeypatch) -> None:
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.setenv("PG_SCOPE_DENYLIST_DOMAINS", "facebook.com")
    kept, n_dropped, _ = _apply_scope_denylist(_scored_pair(), None)
    assert n_dropped == 0 and len(kept) == 2
    fb = [it for it in kept if "facebook" in it[3]["source_url"]][0]
    assert fb[3].get("scope_denylist_demoted") is True
    assert fb[3].get("credibility_class") == "low_denylist"


def _twin_rows():
    return [
        {"source_url": "https://doi.org/10.1/x", "title": "Trial X primary results"},
        {"source_url": "https://arxiv.org/abs/1", "title": "Trial X primary results"},
    ]


def test_arch002_prefer_journal_off_drops_twin(monkeypatch) -> None:
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    kept, n_dropped, _ = prefer_journal_over_arxiv(_twin_rows())
    assert n_dropped == 1 and len(kept) == 1


def test_arch002_prefer_journal_on_keeps_both_versions(monkeypatch) -> None:
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    kept, n_dropped, _ = prefer_journal_over_arxiv(_twin_rows())
    assert n_dropped == 0 and len(kept) == 2
    arx = [r for r in kept if "arxiv" in r["source_url"]][0]
    assert arx.get("arxiv_journal_twin") is True
