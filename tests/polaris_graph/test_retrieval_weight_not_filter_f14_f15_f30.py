"""F14 + F15 + F30 (GH #1245) — §-1.3 WEIGHT-NOT-FILTER retrieval cluster.

These tests PROVE the three fixes and that every OFF path stays byte-identical
(the operator-locked hard constraint: strengthen or be byte-identical when the
flag is OFF; DOWN-WEIGHT, never hard-drop; never relax a faithfulness gate).

F14 (P0, D9/D10): a short paywall-shell body that the free chain returns with
    success=True was logged status="ok" — a dead fetch masquerading as a good
    source. The min-body gate makes a sub-floor body a LOUD `stub` (ok=False),
    NOT ok, and the OA resolver gets first chance to upgrade it. The Zyte path
    fails LOUD (not a silent no-op) when the key is missing for a paywalled
    publisher.

F15 (P1, D11): content-starved sources were HARD-DROPPED while the log said
    dropped=0 (dishonest), and a dead URL was refetched ~5.5x. Now: DOWN-WEIGHT
    (keep in the pool at low weight) under the redesign flag, surface the REAL
    drop counts, and a per-URL refetch cap + negative cache so a dead URL is
    fetched at most the cap.

F30 (P3): a source grounded on a repository/landing/abstract page is flagged +
    down-weighted (methods cannot ground on a landing page), not treated as
    full text.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from src.polaris_graph.retrieval import live_retriever
from src.polaris_graph.retrieval import evidence_selector


# ─────────────────────────────────────────────────────────────────────────────
# Fakes mirroring the existing test_fetch_access_bypass_wiring harness.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _FakeAccessResult:
    success: bool = True
    content: str = ""
    access_method: str = "crawl4ai"
    metadata: dict | None = None


class _ShortBodyBypass:
    """AccessBypass that succeeds but returns a SHORT paywall-shell body."""

    def __init__(self, body: str) -> None:
        self._body = body

    async def fetch_with_bypass(self, url, prefer_legal=True):
        return _FakeAccessResult(success=True, content=self._body)


@pytest.fixture(autouse=True)
def _reset_caches():
    live_retriever.reset_refetch_cache()
    yield
    live_retriever.reset_refetch_cache()


def _install_bypass(monkeypatch, bypass_cls_or_obj):
    import src.tools.access_bypass as ab
    if isinstance(bypass_cls_or_obj, type):
        monkeypatch.setattr(ab, "AccessBypass", bypass_cls_or_obj)
    else:
        monkeypatch.setattr(ab, "AccessBypass", lambda: bypass_cls_or_obj)


# ═════════════════════════════════════════════════════════════════════════════
# F14 — paywall-stub min-body gate + Zyte fail-loud
# ═════════════════════════════════════════════════════════════════════════════
def test_f14_paywall_publisher_url_detection():
    assert live_retriever._is_paywall_publisher_url(
        "https://www.sciencedirect.com/science/article/pii/S0000"
    )
    assert live_retriever._is_paywall_publisher_url(
        "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519"
    )
    # A non-paywalled host is NOT flagged.
    assert not live_retriever._is_paywall_publisher_url(
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6490750/"
    )
    assert not live_retriever._is_paywall_publisher_url("")


def test_f14_env_extends_paywall_publisher_hosts(monkeypatch):
    monkeypatch.setenv("PG_PAYWALL_PUBLISHER_HOSTS", "examplepub.com, another.org")
    assert live_retriever._is_paywall_publisher_url("https://examplepub.com/x")
    assert live_retriever._is_paywall_publisher_url("https://www.another.org/y")


def test_f14_short_body_is_stub_not_ok_when_floor_set(monkeypatch):
    """A sub-floor body from a paywalled publisher becomes a LOUD stub (ok=False),
    NOT a silent ok. The content is still returned (for a down-weight consumer)
    but with ok=False + status='stub'."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setenv("PG_FETCH_MIN_BODY_CHARS", "1000")
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")  # no OA upgrade path
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    shell = "Sign in to access this article. " * 5  # ~160 chars, < 1000
    _install_bypass(monkeypatch, _ShortBodyBypass(shell))

    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://www.sciencedirect.com/science/article/pii/S123", max_chars=25000,
    )
    assert ok is False, "short paywall shell must NOT be reported ok=True"
    assert content == live_retriever._strip_html(shell)[:25000]


def test_f14_off_by_default_short_body_stays_ok(monkeypatch):
    """DEFAULT (PG_FETCH_MIN_BODY_CHARS unset => 0 => OFF): a short body stays
    ok=True — byte-identical to pre-F14 behavior (existing wiring tests rely on
    this)."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.delenv("PG_FETCH_MIN_BODY_CHARS", raising=False)
    body = "fake markdown content with real words"  # ~38 chars
    _install_bypass(monkeypatch, _ShortBodyBypass(body))

    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://www.sciencedirect.com/science/article/pii/S123", max_chars=1000,
    )
    assert ok is True
    assert "fake markdown content" in content


def test_f14_oa_resolver_upgrades_short_shell_to_full_text(monkeypatch):
    """When the body is a short shell AND the OA resolver returns a long body,
    the result is the UPGRADED full text with ok=True (not a stub)."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setenv("PG_FETCH_MIN_BODY_CHARS", "1000")
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "1")
    shell = "Abstract only. Purchase to read more. " * 4  # ~150 chars
    _install_bypass(monkeypatch, _ShortBodyBypass(shell))

    full = "Full text recovered via Unpaywall. " * 60  # > 1000 chars

    def _fake_oa(url, extracted_doi, pmid, max_chars):
        return full

    monkeypatch.setattr(live_retriever, "_try_oa_resolution", _fake_oa)

    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://www.nature.com/articles/10.1038/s41586-020-0000-0",
        max_chars=25000,
        doi_hint="10.1038/s41586-020-0000-0",
    )
    assert ok is True
    assert content == full[:25000]


def test_f14_long_body_unaffected_by_floor(monkeypatch):
    """The min-body gate is a CAP-not-target: a long full body is ALWAYS ok,
    even with the floor set (never drops a long body)."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setenv("PG_FETCH_MIN_BODY_CHARS", "1000")
    long_body = "Methods. Results. Conclusion. Real article body. " * 60
    _install_bypass(monkeypatch, _ShortBodyBypass(long_body))

    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://www.thelancet.com/journals/lancet/article", max_chars=25000,
    )
    assert ok is True
    assert "Real article body" in content


def test_f14_access_bypass_paywall_host_detection():
    from src.tools import access_bypass as ab
    assert ab._is_paywall_publisher_host("https://www.sciencedirect.com/x")
    assert ab._is_paywall_publisher_host("https://onlinelibrary.wiley.com/doi/x")
    assert not ab._is_paywall_publisher_host("https://www.who.int/x")
    assert not ab._is_paywall_publisher_host("")


def test_f14_zyte_first_off_by_default_byte_identical(monkeypatch):
    """PG_ZYTE_PAYWALL_FIRST unset => default OFF => the early-Zyte attempt never
    fires (byte-identical). We assert _try_zyte is NOT called early for a
    paywalled host when the flag is off."""
    import asyncio
    from src.tools import access_bypass as ab

    monkeypatch.delenv("PG_ZYTE_PAYWALL_FIRST", raising=False)
    monkeypatch.setenv("ZYTE_API_KEY", "fake-key")
    monkeypatch.setenv("PG_UNPAYWALL_ENABLED", "0")
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "0")
    monkeypatch.setenv("PG_FIRECRAWL_ENABLED", "0")

    bp = ab.AccessBypass()
    zyte_calls = {"n": 0}

    async def _fake_zyte(url):
        zyte_calls["n"] += 1
        return ab.AccessResult(
            url=url, content="", access_method="zyte",
            legal_alternative=None, success=False, metadata={},
        )

    async def _fake_jina(url):
        return ab.AccessResult(
            url=url, content="x" * 5000, access_method="jina_reader",
            legal_alternative=None, success=True, metadata={},
        )

    monkeypatch.setattr(bp, "_try_zyte", _fake_zyte)
    monkeypatch.setattr(bp, "_try_jina_reader", _fake_jina)

    async def _run():
        return await bp.fetch_with_bypass(
            "https://www.sciencedirect.com/science/article/pii/S1"
        )

    res = asyncio.run(_run())
    # Flag OFF: Zyte-first never fired; jina won. (zyte may still be tried at the
    # END of the cascade, but jina succeeds first so it is not reached here.)
    assert res.success is True
    assert zyte_calls["n"] == 0


def test_f14_zyte_first_routes_paywall_publisher_when_enabled(monkeypatch):
    """PG_ZYTE_PAYWALL_FIRST=1 + key present: a paywalled-publisher URL is routed
    to Zyte FIRST (before the free scraper group)."""
    import asyncio
    from src.tools import access_bypass as ab

    monkeypatch.setenv("PG_ZYTE_PAYWALL_FIRST", "1")
    monkeypatch.setenv("ZYTE_API_KEY", "fake-key")
    monkeypatch.setenv("PG_UNPAYWALL_ENABLED", "0")

    bp = ab.AccessBypass()
    order = []

    async def _fake_zyte(url):
        order.append("zyte")
        return ab.AccessResult(
            url=url, content="z" * 6000, access_method="zyte",
            legal_alternative=None, success=True, metadata={},
        )

    async def _fake_jina(url):
        order.append("jina")
        return ab.AccessResult(
            url=url, content="x" * 5000, access_method="jina_reader",
            legal_alternative=None, success=True, metadata={},
        )

    monkeypatch.setattr(bp, "_try_zyte", _fake_zyte)
    monkeypatch.setattr(bp, "_try_jina_reader", _fake_jina)

    async def _run():
        return await bp.fetch_with_bypass(
            "https://www.nejm.org/doi/full/10.1056/NEJMoa1"
        )

    res = asyncio.run(_run())
    assert res.success is True
    assert res.access_method == "zyte"
    assert order and order[0] == "zyte", "Zyte must be tried FIRST for a paywalled publisher"


def test_f14_zyte_first_loud_warning_when_key_missing(monkeypatch, caplog):
    """PG_ZYTE_PAYWALL_FIRST=1 but ZYTE_API_KEY unset: a LOUD warning fires for a
    paywalled publisher (no longer a silent no-op)."""
    import asyncio
    import logging
    from src.tools import access_bypass as ab

    monkeypatch.setenv("PG_ZYTE_PAYWALL_FIRST", "1")
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    monkeypatch.setenv("PG_UNPAYWALL_ENABLED", "0")
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "0")
    monkeypatch.setenv("PG_FIRECRAWL_ENABLED", "0")

    bp = ab.AccessBypass()

    async def _fail_jina(url):
        return ab.AccessResult(
            url=url, content="", access_method="jina_reader",
            legal_alternative=None, success=False, metadata={},
        )

    monkeypatch.setattr(bp, "_try_jina_reader", _fail_jina)

    async def _run():
        with caplog.at_level(logging.WARNING):
            return await bp.fetch_with_bypass(
                "https://www.thelancet.com/journals/lancet/article"
            )

    asyncio.run(_run())
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "ZYTE_API_KEY is" in msgs and "UNSET" in msgs


# ═════════════════════════════════════════════════════════════════════════════
# F15 — per-URL refetch cap + negative cache; honest down-weight
# ═════════════════════════════════════════════════════════════════════════════
def test_f15_dead_url_refetched_at_most_cap_times(monkeypatch):
    """Codex diff-gate P1: the cap is a RETRY BUDGET, not mark-dead-on-first-
    failure. With cap=2 a failing URL is fetched exactly TWICE (two real
    attempts), THEN permanently short-circuited — preserving the retry budget
    the spec requires while killing the ~5.5x re-fetch storm. `refetch_capped`
    is reported ONLY once the cap is the actual reason for the skip."""
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "2")  # read at call time
    live_retriever.reset_refetch_cache()

    calls = {"n": 0}

    def _fake_fetch(url, max_chars):
        calls["n"] += 1
        return ("", False, "", "", "")  # always fails

    monkeypatch.setattr(live_retriever, "_fetch_content", _fake_fetch)

    url = "https://dead.example.com/doi/10.0/x"
    # Attempt 1: real fetch, fails (1/2). NOT yet capped.
    q1, d1 = live_retriever.refetch_for_extraction_with_diagnostics(url)
    assert d1["attempted"] is True
    assert d1["failure_mode"] == "fetch_failed"
    # Attempt 2: real fetch, fails (2/2 => now cap-exhausted, cached).
    q2, d2 = live_retriever.refetch_for_extraction_with_diagnostics(url)
    assert d2["attempted"] is True
    assert d2["failure_mode"] == "fetch_failed"
    # Attempt 3: short-circuit (NO fetch) — cap is the reason.
    q3, d3 = live_retriever.refetch_for_extraction_with_diagnostics(url)
    assert d3["attempted"] is False
    assert d3["failure_mode"] == "refetch_capped"
    # Exactly TWO real fetches across 3 requests (cap honored, not ~5.5x).
    assert calls["n"] == 2


def test_f15_cap_one_means_single_attempt(monkeypatch):
    """cap=1 => exactly one real attempt before the permanent skip."""
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "1")
    live_retriever.reset_refetch_cache()
    calls = {"n": 0}

    def _fake_fetch(url, max_chars):
        calls["n"] += 1
        return ("ab", True, "", "full_text", "")  # 2 chars => thin (a failure)

    monkeypatch.setattr(live_retriever, "_fetch_content", _fake_fetch)
    url = "https://thin.example.com/x"
    live_retriever.refetch_for_extraction_with_diagnostics(url)
    d2 = live_retriever.refetch_for_extraction_with_diagnostics(url)[1]
    assert calls["n"] == 1  # second call short-circuited
    assert d2["failure_mode"] == "refetch_capped"


def test_f15_successful_fetch_does_not_count_toward_cap(monkeypatch):
    """A LIVE URL that returns a usable body is NOT capped — several sections may
    legitimately re-ground a claim on it. The cap counts FAILURES only."""
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "2")
    live_retriever.reset_refetch_cache()
    calls = {"n": 0}
    fat = (
        "SURPASS-2 enrolled 1879 patients with baseline HbA1c 8.28%. "
        "Tirzepatide 15 mg reduced HbA1c by 2.30 pp. Weight loss 11.2 kg. "
    ) * 4  # > 100 chars, eligible

    def _fake_fetch(url, max_chars):
        calls["n"] += 1
        return (fat, True, "title", "full_text", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _fake_fetch)
    url = "https://live.example.com/x"
    for _ in range(4):
        live_retriever.refetch_for_extraction_with_diagnostics(url)
    # All 4 ran a real fetch (a success never counts toward the cap).
    assert calls["n"] == 4


def test_f15_reset_clears_cache(monkeypatch):
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "1")
    live_retriever.reset_refetch_cache()
    url = "https://x.example.com/y"
    live_retriever._refetch_record_failure(url)  # 1 of 1 => capped + cached
    assert live_retriever._refetch_should_skip(url) is True
    live_retriever.reset_refetch_cache()
    assert live_retriever._refetch_should_skip(url) is False


def test_f15_below_cap_failure_not_skipped(monkeypatch):
    """A single recorded failure (below cap) does NOT skip — retry budget kept."""
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "3")
    live_retriever.reset_refetch_cache()
    url = "https://x.example.com/z"
    live_retriever._refetch_record_failure(url)  # 1 of 3
    assert live_retriever._refetch_should_skip(url) is False
    live_retriever._refetch_record_failure(url)  # 2 of 3
    assert live_retriever._refetch_should_skip(url) is False
    live_retriever._refetch_record_failure(url)  # 3 of 3 => capped
    assert live_retriever._refetch_should_skip(url) is True


def test_f15_concurrent_live_url_never_wrongly_skipped(monkeypatch):
    """Codex diff-gate iter-3 P1: a LIVE URL requested by many concurrent callers
    is NEVER wrongly skipped (never suppress a fetch that could succeed). Every
    concurrent caller of a live URL performs a real fetch and gets the quote — a
    success never counts toward the cap, and the skip gates ONLY on settled
    failures, not on in-flight reservations."""
    import threading

    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "2")
    live_retriever.reset_refetch_cache()

    fetch_lock = threading.Lock()
    fetch_count = {"n": 0}
    fat = (
        "SURPASS-2 enrolled 1879 patients with baseline HbA1c 8.28%. "
        "Tirzepatide 15 mg reduced HbA1c by 2.30 pp. Weight loss 11.2 kg. "
    ) * 4  # eligible (> 100 chars)
    start = threading.Barrier(12)
    results: list[str] = []
    results_lock = threading.Lock()

    def _live_fetch(url, max_chars):
        with fetch_lock:
            fetch_count["n"] += 1
        return (fat, True, "title", "full_text", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _live_fetch)
    url = "https://live-concurrent.example.com/x"

    def _worker():
        start.wait()
        q, _d = live_retriever.refetch_for_extraction_with_diagnostics(url)
        with results_lock:
            results.append(q)

    threads = [threading.Thread(target=_worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # ALL 12 concurrent callers fetched the live URL and got a non-empty quote —
    # none was wrongly skipped by an in-flight reservation (iter-3 fix).
    assert fetch_count["n"] == 12
    assert all(q for q in results), "a live-URL caller was wrongly skipped"
    assert live_retriever._refetch_should_skip(url) is False


def test_f15_serial_dead_url_fetched_exactly_cap_times(monkeypatch):
    """In the REAL (serial) call topology, a dead URL is fetched exactly `cap`
    times then permanently short-circuited — the ~5.5x storm is killed."""
    monkeypatch.setenv("PG_REFETCH_PER_URL_CAP", "2")
    live_retriever.reset_refetch_cache()
    calls = {"n": 0}

    def _dead(url, max_chars):
        calls["n"] += 1
        return ("", False, "", "", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _dead)
    url = "https://dead-serial.example.com/x"
    for _ in range(6):  # six serial refetch requests
        live_retriever.refetch_for_extraction_with_diagnostics(url)
    assert calls["n"] == 2  # exactly cap real fetches
    assert live_retriever._refetch_should_skip(url) is True


# ═════════════════════════════════════════════════════════════════════════════
# F30 — landing/abstract-page detection
# ═════════════════════════════════════════════════════════════════════════════
def test_f30_landing_page_markers_detected():
    landing = (
        "URL Source: https://repo.example.org/record/12345\n"
        "## APA Style\nSmith, J. (2020). A study. Journal.\n"
        "Publication status: Published\n"
    )
    assert live_retriever._is_landing_or_abstract_page(landing) is True


def test_f30_full_text_body_not_flagged_as_landing():
    """A long full-text article that merely quotes a marker phrase deep in its
    body is NOT flagged (the marker check is head-only + the body is long)."""
    body = (
        "Introduction. This randomized controlled trial enrolled 1879 patients. "
        "Methods. Results. Discussion. " * 200
        + " (the references list mentions apa style formatting somewhere)"
    )
    assert live_retriever._is_landing_or_abstract_page(body) is False


def test_f30_empty_body_not_landing():
    assert live_retriever._is_landing_or_abstract_page("") is False
    assert live_retriever._is_landing_or_abstract_page(None) is False


# ═════════════════════════════════════════════════════════════════════════════
# F15/F30 selector wiring — retrieval_weight ranks a down-weighted row LAST
# ═════════════════════════════════════════════════════════════════════════════
def test_f15_selector_off_path_ignores_retrieval_weight(monkeypatch):
    """OFF path (PG_SWEEP_CREDIBILITY_REDESIGN unset): a row's retrieval_weight is
    NOT applied to ranking — byte-identical to the prior sort key."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert evidence_selector._credibility_redesign_enabled() is False


def test_f15_selector_down_weights_rank_last_when_redesign_on(monkeypatch):
    """ON path: a row carrying a low retrieval_weight sorts AFTER an equal-
    relevance full-weight row (kept in the pool, ranked last)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    assert evidence_selector._credibility_redesign_enabled() is True

    # scored tuples: (orig_index, relevance, tier, row)
    full_row = {"source_url": "https://a", "authority_score": 1.0}
    starved_row = {
        "source_url": "https://b", "authority_score": 1.0,
        "retrieval_weight": 0.05, "down_weighted": True, "content_starved": True,
    }
    scored = [
        (0, 0.8, "T1", full_row),
        (1, 0.8, "T1", starved_row),
    ]
    sel = evidence_selector._relevance_floor_selection(
        scored=scored,
        relevance_floor=0.5,
        full_counts={"T1": 2},
        primary_trial_anchors=None,
    )
    urls = [r["source_url"] for r in sel.selected_rows]
    # Both kept (weight, not filter), but the down-weighted one ranks LAST.
    assert urls == ["https://a", "https://b"]
    assert sel.dropped_count == 0
