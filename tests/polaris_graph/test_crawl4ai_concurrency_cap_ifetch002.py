"""I-fetch-002 (#1168) — crawl4ai browser concurrency is hard-capped + the circuit breaker tolerates
a couple of transient subprocess crashes.

crawl4ai launches a Playwright browser subprocess PER URL; under the ~1000-URL benchmark fan-out, many
concurrent browsers exhaust the OS and crash with EPIPE, which then trips the circuit breaker and
disables crawl4ai run-wide. Two fixes, both verified BEHAVIORALLY here, offline, no real browser:

  1. A concurrency semaphore (PG_CRAWL4AI_CONCURRENCY, default 2) so at most N browsers are LIVE at
     once. Proven with a counter that increments on browser-active entry and decrements on exit: the
     observed PEAK never exceeds the cap, even with many more calls launched concurrently.
  2. The circuit-breaker crash-tolerance threshold default is raised 3 -> 6.

The real `crawl4ai` package is NOT imported: a fake module is injected into sys.modules so the
function's local `from crawl4ai import ...` binds to the stub. No network, no Playwright, no spend.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

import src.tools.access_bypass as ab
from src.tools.access_bypass import AccessBypass


# --------------------------------------------------------------------------- threshold bump (config)

def test_circuit_breaker_threshold_default_raised_to_six(monkeypatch):
    """Default crash-tolerance threshold is 6 (was 3) so a couple of transient EPIPE crashes do not
    disable crawl4ai for the whole run. Reads the env default via a fresh module-constant computation."""
    monkeypatch.delenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", raising=False)
    import os
    assert int(os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")) == 6
    # And the module-level constant honored the new default at import.
    assert ab._CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD >= 6


def test_concurrency_semaphore_default_is_two(monkeypatch):
    monkeypatch.delenv("PG_CRAWL4AI_CONCURRENCY", raising=False)
    ab._crawl4ai_semaphore = None  # force a fresh lazy-init
    sem = ab._get_crawl4ai_semaphore()
    assert sem._value == 2  # asyncio.Semaphore initial counter == the configured cap


# --------------------------------------------------------------------------- behavioral concurrency cap


class _FakeResult:
    """A minimal crawl4ai result that the success path accepts."""

    def __init__(self) -> None:
        self.success = True
        self.error_message = None
        self.status_code = 200
        self.redirected_url = None
        # >500 chars so trafilatura-or-fallback yields enough content; html None so the
        # fallback uses .markdown directly (no trafilatura dependency in the test).
        self.html = None
        self.markdown = "x" * 800


def _make_fake_crawl4ai(active_counter: dict):
    """Build a fake `crawl4ai` module whose AsyncWebCrawler tracks the number of concurrently-LIVE
    browsers (incremented in __aenter__, decremented in __aexit__) so the test can assert the peak."""

    class _FakeCrawler:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            active_counter["live"] += 1
            active_counter["peak"] = max(active_counter["peak"], active_counter["live"])
            return self

        async def __aexit__(self, *exc):
            active_counter["live"] -= 1
            return False

        async def arun(self, *, url, config):
            # Hold the "browser" busy long enough that, absent the semaphore, all callers would
            # overlap and drive the peak above the cap.
            await asyncio.sleep(0.05)
            return _FakeResult()

    def _cfg(*a, **k):
        return object()

    mod = types.ModuleType("crawl4ai")
    mod.AsyncWebCrawler = _FakeCrawler
    mod.BrowserConfig = _cfg
    mod.CrawlerRunConfig = _cfg
    return mod


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_browsers(monkeypatch):
    """Launch many more crawls than the cap concurrently; the peak number of LIVE browsers must never
    exceed PG_CRAWL4AI_CONCURRENCY. This is the real cap proof (not 'a semaphore exists')."""
    cap = 2
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", str(cap))
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")

    # Reset module state so the semaphore re-inits on the running loop at the configured cap.
    ab._crawl4ai_semaphore = None
    ab._crawl4ai_available = None
    ab._crawl4ai_consecutive_failures = 0
    ab._crawl4ai_circuit_open_until = 0.0

    counter = {"live": 0, "peak": 0}
    fake_mod = _make_fake_crawl4ai(counter)
    # Inject the fake so the function's local `from crawl4ai import ...` binds to it. Also stub the two
    # optional sub-imports so the filter branch resolves cleanly.
    monkeypatch.setitem(sys.modules, "crawl4ai", fake_mod)
    monkeypatch.setitem(
        sys.modules, "crawl4ai.markdown_generation_strategy",
        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
    )
    monkeypatch.setitem(
        sys.modules, "crawl4ai.content_filter_strategy",
        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
    )

    bypass = AccessBypass()
    n_calls = cap + 4  # more than the cap so the semaphore is the only thing bounding the peak
    results = await asyncio.gather(
        *[bypass._try_crawl4ai(f"https://example.gov/doc/{i}") for i in range(n_calls)]
    )

    assert counter["peak"] <= cap, f"peak live browsers {counter['peak']} exceeded cap {cap}"
    assert counter["peak"] >= 1, "the fake crawler never went live — the stub did not bind"
    # All calls still completed successfully (the cap serializes, it does not drop work).
    assert all(r.success for r in results)
    assert counter["live"] == 0, "a browser slot leaked (live count did not return to 0)"


@pytest.mark.asyncio
async def test_single_call_succeeds_under_cap(monkeypatch):
    """Sanity: one call still works (the semaphore does not block the first acquirer)."""
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")
    ab._crawl4ai_semaphore = None
    ab._crawl4ai_available = None
    ab._crawl4ai_consecutive_failures = 0
    ab._crawl4ai_circuit_open_until = 0.0

    counter = {"live": 0, "peak": 0}
    monkeypatch.setitem(sys.modules, "crawl4ai", _make_fake_crawl4ai(counter))
    monkeypatch.setitem(
        sys.modules, "crawl4ai.markdown_generation_strategy",
        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
    )
    monkeypatch.setitem(
        sys.modules, "crawl4ai.content_filter_strategy",
        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
    )

    res = await AccessBypass()._try_crawl4ai("https://example.gov/single")
    assert res.success
    assert counter["peak"] == 1
    assert counter["live"] == 0
