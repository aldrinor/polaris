"""FX-17 (I-ready-017 #1126): Serper visible clamp + pagination to a total-URL budget.

The old `_serper_search` silently floored `num` to 20 (no warning) and never paginated. FX-17 makes
the clamp loud and adds `page`-param pagination up to `PG_SERPER_TOTAL_PER_QUERY` (default = one page
= byte-identical), bounded by `PG_SERPER_MAX_PAGES`, early-stopping on a short page. Discovery-breadth
only — all new URLs pass the same downstream gates. Offline (page helper mocked), no network.
"""
from __future__ import annotations

import logging

import src.polaris_graph.retrieval.live_retriever as lr


def _install_pages(monkeypatch, pages: dict[int, list[str]]):
    """Mock `_serper_fetch_page` to return synthetic items per page; record requested pages."""
    calls: list[int] = []

    def _fake(query, per_page, page, headers):
        calls.append(page)
        urls = pages.get(page, [])
        items = [{"url": u, "title": "t", "snippet": "s", "source": "serper"} for u in urls]
        return items, True, 1.0, 100, ""

    monkeypatch.setattr(lr, "_serper_fetch_page", _fake)
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    return calls


def test_default_single_page_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_SERPER_TOTAL_PER_QUERY", raising=False)
    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(10)]})
    out = lr._serper_search("q", num=10)
    assert calls == [1]                      # exactly one page, no pagination by default
    assert len(out) == 10


def test_num_over_page_max_warns_and_clamps(monkeypatch, caplog):
    monkeypatch.delenv("PG_SERPER_TOTAL_PER_QUERY", raising=False)
    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(20)]})
    with caplog.at_level(logging.WARNING):
        out = lr._serper_search("q", num=100)   # 100 > page max 20
    assert any("exceeds the page max" in r.message for r in caplog.records)
    assert calls == [1]                       # default budget = per_page (20) -> still 1 page
    assert len(out) == 20


def test_pagination_accumulates_and_dedups(monkeypatch):
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "40")
    p1 = [f"https://x/{i}" for i in range(20)]
    p2 = [f"https://x/{i}" for i in range(19, 39)]  # one URL (x/19) overlaps p1
    calls = _install_pages(monkeypatch, {1: p1, 2: p2})
    out = lr._serper_search("q", num=20)
    assert calls == [1, 2]                     # paginated to the budget
    urls = [o["url"] for o in out]
    assert len(urls) == len(set(urls))         # deduped
    assert len(out) == 39                       # 20 + 20 - 1 overlap


def test_early_stop_on_short_page(monkeypatch):
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(5)]})  # < per_page
    out = lr._serper_search("q", num=20)
    assert calls == [1]                        # short page -> no further pages
    assert len(out) == 5


def test_max_pages_cap_respected(monkeypatch):
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "200")
    monkeypatch.setenv("PG_SERPER_MAX_PAGES", "2")
    pages = {p: [f"https://x/{p}-{i}" for i in range(20)] for p in range(1, 6)}
    calls = _install_pages(monkeypatch, pages)
    out = lr._serper_search("q", num=20)
    assert calls == [1, 2]                      # capped at PG_SERPER_MAX_PAGES even though budget=200
    assert len(out) == 40


def test_api_calls_counts_each_page_not_each_query(monkeypatch):
    """FX-17 iter-2 P2 fix: api_calls['serper'] must count EACH HTTP page, not once per query."""
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "40")
    p1 = [f"https://x/{i}" for i in range(20)]
    p2 = [f"https://x/{i}" for i in range(20, 40)]
    _install_pages(monkeypatch, {1: p1, 2: p2})
    api_calls = {"serper": 0}
    lr._serper_search("q", num=20, api_calls=api_calls)
    assert api_calls["serper"] == 2             # two pages fetched -> two API calls counted


def test_api_calls_none_is_safe(monkeypatch):
    """Passing api_calls=None (default) must not raise — back-compat for non-tracking callers."""
    _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(10)]})
    out = lr._serper_search("q", num=10)        # no api_calls kwarg
    assert len(out) == 10
