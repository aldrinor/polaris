"""I-bug-114 (#551) — the concurrent fetch fan-out is hard-bounded.

A fetch backend wedged in a Playwright op — including one that hangs *during
cancellation cleanup* (the class `asyncio.wait_for` cannot escape, because it
awaits the cancelled coroutine's cleanup) — must not freeze `asyncio.gather`.
`_bounded_backend` returns within `PG_BACKEND_FETCH_TIMEOUT +
PG_BACKEND_CLEANUP_GRACE` regardless of backend state.

No network, no Playwright: the hang is modelled with `asyncio.sleep`.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.tools.access_bypass import AccessResult, _bounded_backend

_URL = "https://example.gov/anti-bot-interstitial"


async def _hang_through_cancellation() -> AccessResult:
    """A backend wedged in a long op whose cancellation cleanup ALSO hangs —
    the exact class a plain `asyncio.wait_for` wrapper cannot bound."""
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        # Cleanup that itself hangs during cancellation. Bounded at 2s so the
        # test event-loop teardown stays clean; 2s > the 1s cleanup grace, so
        # `_bounded_backend` must detach rather than wait it out.
        await asyncio.sleep(2.0)
        raise


async def _fast_success() -> AccessResult:
    return AccessResult(
        url=_URL,
        content="a real article body",
        access_method="jina_reader",
        legal_alternative=None,
        success=True,
        metadata={},
    )


@pytest.mark.asyncio
async def test_bounded_backend_returns_within_timeout_plus_grace(monkeypatch):
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "1")
    monkeypatch.setenv("PG_BACKEND_CLEANUP_GRACE", "1")

    start = time.monotonic()
    result = await _bounded_backend("crawl4ai", _hang_through_cancellation(), _URL)
    elapsed = time.monotonic() - start

    # Hard bound: returns within timeout + grace + epsilon — not 30 min, and
    # not the 2s secondary cleanup sleep it is detached from.
    assert elapsed < 2.5, f"_bounded_backend took {elapsed:.1f}s — not hard-bounded"
    assert isinstance(result, AccessResult)
    assert result.success is False
    assert result.metadata["error"].startswith("backend_timeout")
    assert result.access_method == "crawl4ai"


@pytest.mark.asyncio
async def test_gather_survives_one_hung_backend(monkeypatch):
    """The exact pattern `fetch_with_bypass` uses — `asyncio.gather` over
    `_bounded_backend`-wrapped backends. One hung backend must not stall it,
    and the fast backend's result must survive."""
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "1")
    monkeypatch.setenv("PG_BACKEND_CLEANUP_GRACE", "1")

    tasks = [
        _bounded_backend("crawl4ai", _hang_through_cancellation(), _URL),
        _bounded_backend("jina_reader", _fast_success(), _URL),
    ]
    start = time.monotonic()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - start

    assert elapsed < 2.5, f"gather took {elapsed:.1f}s — a hung backend froze it"
    successes = [r for r in results if isinstance(r, AccessResult) and r.success]
    assert len(successes) == 1, f"expected 1 successful backend, got {results!r}"
    assert successes[0].access_method == "jina_reader"
    assert successes[0].content == "a real article body"


@pytest.mark.asyncio
async def test_bounded_backend_passes_through_a_fast_success(monkeypatch):
    """A backend that returns quickly is passed through untouched — the
    wrapper does not disturb the happy path."""
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "30")
    monkeypatch.setenv("PG_BACKEND_CLEANUP_GRACE", "10")

    result = await _bounded_backend("jina_reader", _fast_success(), _URL)
    assert result.success is True
    assert result.access_method == "jina_reader"
    assert result.content == "a real article body"


@pytest.mark.asyncio
async def test_bounded_backend_converts_a_raising_backend_to_failure(monkeypatch):
    """A backend that finishes fast but raises is converted to a failure
    AccessResult, not propagated as an exception."""
    monkeypatch.setenv("PG_BACKEND_FETCH_TIMEOUT", "30")

    async def _raises() -> AccessResult:
        raise RuntimeError("backend blew up")

    result = await _bounded_backend("firecrawl", _raises(), _URL)
    assert isinstance(result, AccessResult)
    assert result.success is False
    assert "RuntimeError" in result.metadata["error"]
