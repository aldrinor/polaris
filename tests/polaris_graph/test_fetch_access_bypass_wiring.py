"""BUG-FETCH-R8d: confirm _fetch_content routes through AccessBypass
correctly from both sync and async calling contexts, and that a
failure inside AccessBypass falls back to the naive httpx path
rather than raising.

History of the bug:
- v1 (pre-2026-04-18): live_retriever used only httpx with no
  Accept-Encoding header — 19/20 fetches failed on academic
  sites that served brotli-compressed content.
- v2: wired AccessBypass via asyncio.new_event_loop() +
  run_until_complete. Primary path worked intermittently but
  expansion phase crashed with "asyncio.run() cannot be called
  from a running event loop" because Crawl4AI leaves background
  tasks that keep the loop marked running.
- v3 (current): wrap AccessBypass in a dedicated daemon thread so
  each fetch gets an isolated event loop; safe from any calling
  context.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import patch

from src.polaris_graph.retrieval import live_retriever


@dataclass
class _FakeAccessResult:
    success: bool = True
    content: str = "fake markdown content with real words"
    access_method: str = "crawl4ai"
    metadata: dict | None = None


class _FakeBypass:
    async def fetch_with_bypass(self, url, prefer_legal=True):
        return _FakeAccessResult()


class _FailingBypass:
    async def fetch_with_bypass(self, url, prefer_legal=True):
        raise RuntimeError("simulated crawl4ai failure")


class _EmptyBypass:
    async def fetch_with_bypass(self, url, prefer_legal=True):
        return _FakeAccessResult(
            success=False,
            content="",
            access_method="skipped_s2_landing",
            metadata={"reason": "S2 landing pages have no content"},
        )


def test_fetch_content_uses_access_bypass_from_sync_context(monkeypatch):
    """Sync caller → fetch_content should return (content, True)."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")

    import src.tools.access_bypass as ab
    monkeypatch.setattr(ab, "AccessBypass", _FakeBypass)

    content, ok = live_retriever._fetch_content(
        "https://example.com/paper", max_chars=1000,
    )

    assert ok is True
    assert "fake markdown content" in content


def test_fetch_content_works_from_async_context(monkeypatch):
    """Async caller → fetch_content must not raise
    'asyncio.run() cannot be called from a running event loop'.
    This is the regression we saw in smoke v3 after switching from
    run_until_complete to asyncio.run without the thread wrapper.
    """
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")

    import src.tools.access_bypass as ab
    monkeypatch.setattr(ab, "AccessBypass", _FakeBypass)

    async def _caller():
        return live_retriever._fetch_content(
            "https://example.com/paper", max_chars=1000,
        )

    content, ok = asyncio.run(_caller())
    assert ok is True
    assert "fake markdown content" in content


def test_fetch_content_falls_back_on_bypass_exception(monkeypatch):
    """When AccessBypass raises inside the thread, the fallback
    httpx path is invoked rather than the exception propagating."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")

    import src.tools.access_bypass as ab
    monkeypatch.setattr(ab, "AccessBypass", _FailingBypass)

    called = {"n": 0}

    def _fake_naive(url, max_chars):
        called["n"] += 1
        return "naive fallback content", True

    monkeypatch.setattr(
        live_retriever, "_fetch_content_httpx_naive", _fake_naive,
    )

    content, ok = live_retriever._fetch_content(
        "https://example.com/paper", max_chars=1000,
    )

    assert ok is True
    assert content == "naive fallback content"
    assert called["n"] == 1


def test_fetch_content_returns_empty_on_skipped_s2_landing(monkeypatch):
    """S2 landing pages are deliberately skipped by AccessBypass.
    The wrapper should return ('', False) without falling back to
    the naive path — naive would just get the same paywalled HTML."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")

    import src.tools.access_bypass as ab
    monkeypatch.setattr(ab, "AccessBypass", _EmptyBypass)

    naive_called = {"n": 0}

    def _fake_naive(url, max_chars):
        naive_called["n"] += 1
        return "naive got through anyway", True

    monkeypatch.setattr(
        live_retriever, "_fetch_content_httpx_naive", _fake_naive,
    )

    content, ok = live_retriever._fetch_content(
        "https://www.semanticscholar.org/paper/abc", max_chars=1000,
    )

    assert ok is False
    assert content == ""
    assert naive_called["n"] == 0, "S2 skip must not trigger naive fallback"


def test_fetch_content_honors_disable_env(monkeypatch):
    """PG_DISABLE_ACCESS_BYPASS=1 must bypass AccessBypass entirely
    and go directly to the naive httpx path (useful when Playwright
    is unavailable)."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "1")

    def _fake_naive(url, max_chars):
        return "naive path content", True

    monkeypatch.setattr(
        live_retriever, "_fetch_content_httpx_naive", _fake_naive,
    )

    # Even if AccessBypass would succeed, the env opt-out must win.
    import src.tools.access_bypass as ab
    monkeypatch.setattr(ab, "AccessBypass", _FakeBypass)

    content, ok = live_retriever._fetch_content(
        "https://example.com/paper", max_chars=1000,
    )

    assert ok is True
    assert content == "naive path content"
