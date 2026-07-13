"""RACE-FLOOR lever 3: tier-first ordering of the writer's prompt menu.

Guards the three ways this can silently go wrong: firing when it should not (default-OFF must be
byte-identical), destroying relevance order within a tier (the sort MUST be stable), and letting an
unranked row outrank a journal article.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    _apply_writer_menu_cap,
    _tier_first_menu,
)


def _rows(*tiers: str) -> list[dict]:
    # ``ord`` is the row's ORIGINAL relevance rank -- what a stable sort must preserve within a tier.
    return [{"ev_id": f"ev_{i}", "tier": t, "ord": i} for i, t in enumerate(tiers)]


def test_default_off_returns_the_same_list_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_WRITER_MENU_TIER_FIRST", raising=False)
    rows = _rows("T4", "T1", "T7")
    assert _tier_first_menu(rows) is rows  # identity, not just equality: no copy, no reorder


@pytest.mark.parametrize("off", ["0", "false", "off", "no", ""])
def test_off_tokens_are_all_no_ops(monkeypatch: pytest.MonkeyPatch, off: str) -> None:
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", off)
    rows = _rows("T4", "T1")
    assert _tier_first_menu(rows) is rows


def test_promotes_journal_tiers_above_the_low_tier_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", "1")
    rows = _rows("T4", "T7", "T1", "T4", "T2")
    assert [r["tier"] for r in _tier_first_menu(rows)] == ["T1", "T2", "T4", "T4", "T7"]


def test_sort_is_stable_within_a_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Relevance order must survive INSIDE a tier -- this raises quality among equals, it does not
    re-rank on quality instead of relevance."""
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", "1")
    rows = _rows("T4", "T4", "T1", "T4")
    out = _tier_first_menu(rows)
    assert [r["ord"] for r in out] == [2, 0, 1, 3]  # T1 first; the three T4s keep 0 < 1 < 3


def test_unknown_and_missing_tiers_sort_last_and_never_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", "1")
    rows = [
        {"ev_id": "a", "tier": "UNKNOWN"},
        {"ev_id": "b"},  # tier key absent entirely
        {"ev_id": "c", "tier": None},
        {"ev_id": "d", "tier": "T2"},
    ]
    assert [r["ev_id"] for r in _tier_first_menu(rows)] == ["d", "a", "b", "c"]


def test_does_not_mutate_the_caller_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", "1")
    rows = _rows("T4", "T1")
    before = list(rows)
    _tier_first_menu(rows)
    assert rows == before  # section.ev_ids / evidence_pool must never be reordered underneath


def test_tier_first_then_cap_fills_the_slots_with_journal_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: the cap takes the HEAD, so ordering must happen BEFORE truncation. Without
    the reorder the two slots go to T4/T7; with it they go to T1/T2."""
    monkeypatch.setenv("PG_WRITER_MENU_TIER_FIRST", "1")
    monkeypatch.setenv("PG_WRITER_TOPN_EV_PER_SECTION", "2")
    rows = _rows("T4", "T7", "T1", "T2")

    capped_only = _apply_writer_menu_cap(rows)
    assert [r["tier"] for r in capped_only] == ["T4", "T7"]  # the defect, reproduced

    ordered_then_capped = _apply_writer_menu_cap(_tier_first_menu(rows))
    assert [r["tier"] for r in ordered_then_capped] == ["T1", "T2"]  # the fix
