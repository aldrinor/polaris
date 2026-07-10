"""I-fetch-lock (FETCH SECTION 1) — last-ditch paid-tail retry routing.

On a source the whole cascade would mark ``fetch_failed``,
``AccessBypass._paid_tail_retry`` runs ONE final Zyte (circuit-breaker
BYPASSED) + Archive.org pass, gated default-ON by ``PG_FETCH_PAID_TAIL_RETRY``.
OFF => no network, ``None`` => the caller's failure return is byte-identical.

Offline: every backend helper is stubbed; no network, no live data.
"""

from __future__ import annotations

import pytest

from src.tools.access_bypass import AccessBypass, AccessResult

_URL = "https://example.org/paywalled-article"


def _make_result(
    success: bool, content: str = "", method: str = "zyte"
) -> AccessResult:
    return AccessResult(
        url=_URL,
        content=content,
        access_method=method,
        legal_alternative=None,
        success=success,
        metadata={},
    )


@pytest.mark.asyncio
async def test_paid_tail_flag_on_routes_zyte_with_breaker_bypass(monkeypatch):
    """Flag ON + key present: the paid tail calls Zyte with
    bypass_circuit_breaker=True and returns the recovered content."""
    monkeypatch.setenv("PG_FETCH_PAID_TAIL_RETRY", "1")
    monkeypatch.setenv("ZYTE_API_KEY", "test-key-not-used-offline")

    ab = AccessBypass()
    captured: dict = {}

    async def _fake_zyte(url, *, bypass_circuit_breaker=False):
        captured["bypass"] = bypass_circuit_breaker
        return _make_result(True, content="A real recovered article body. " * 40)

    monkeypatch.setattr(ab, "_try_zyte", _fake_zyte)
    monkeypatch.setattr(ab, "_is_block_page", lambda url, content, st: False)

    result = await ab._paid_tail_retry(_URL, {"seen": False})

    assert result is not None
    assert result.success is True
    assert captured["bypass"] is True, "Zyte must be called with breaker BYPASSED"


@pytest.mark.asyncio
async def test_paid_tail_flag_off_is_byte_identical_noop(monkeypatch):
    """Flag OFF: returns None with ZERO backend calls (byte-identical)."""
    monkeypatch.setenv("PG_FETCH_PAID_TAIL_RETRY", "0")
    monkeypatch.setenv("ZYTE_API_KEY", "test-key-not-used-offline")

    ab = AccessBypass()
    calls = {"zyte": 0, "archive": 0}

    async def _fake_zyte(url, *, bypass_circuit_breaker=False):
        calls["zyte"] += 1
        return _make_result(True, "x" * 5000)

    async def _fake_archive(url):
        calls["archive"] += 1
        return _make_result(True, "x" * 5000, method="archive.org")

    monkeypatch.setattr(ab, "_try_zyte", _fake_zyte)
    monkeypatch.setattr(ab, "_try_archive_org", _fake_archive)

    result = await ab._paid_tail_retry(_URL, {"seen": False})

    assert result is None
    assert calls == {"zyte": 0, "archive": 0}


@pytest.mark.asyncio
async def test_paid_tail_archive_recovers_when_zyte_key_absent(monkeypatch):
    """Flag ON, no Zyte key: Zyte is a strict no-op (never invoked) and
    Archive.org recovers the source."""
    monkeypatch.setenv("PG_FETCH_PAID_TAIL_RETRY", "1")
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)

    ab = AccessBypass()
    zyte_called = {"n": 0}

    async def _fake_zyte(url, *, bypass_circuit_breaker=False):
        zyte_called["n"] += 1
        return _make_result(False)

    async def _fake_archive(url):
        return _make_result(
            True, "Recovered Wayback article body. " * 50, method="archive.org"
        )

    monkeypatch.setattr(ab, "_try_zyte", _fake_zyte)
    monkeypatch.setattr(ab, "_try_archive_org", _fake_archive)
    monkeypatch.setattr(ab, "_is_block_page", lambda url, content, st: False)
    monkeypatch.setattr(ab, "_detect_paywall", lambda content: False)

    result = await ab._paid_tail_retry(_URL, {"seen": False})

    assert result is not None
    assert result.success is True
    assert result.access_method == "archive.org"
    assert zyte_called["n"] == 0, "Zyte must be a strict no-op when key absent"
