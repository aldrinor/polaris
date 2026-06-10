"""I-fetch-004 (#1185) — the PAID Zyte fallback is a safe, cost-smart,
genuine last resort wired into `AccessBypass.fetch_with_bypass`.

These tests are fully OFFLINE: the Zyte HTTP call is replaced with a fake
`aiohttp.ClientSession` that records the posted JSON payloads and returns
canned responses. No network, no spend.

Coverage (matches the brief's required assertions):
  (a) ZYTE_API_KEY absent  -> `_try_zyte` is NEVER invoked by
      `fetch_with_bypass`, and the existing `access_method="failed"` total-
      failure result is returned byte-identically (NO-OP safety coupling).
  (b) key present + cheap result usable -> exactly ONE paid call
      (httpResponseBody), NO escalation (the cost guarantee).
  (b') key present + cheap result short -> escalation to browserHtml, the
      JS-rendered result wins.
  (c) Zyte error (HTTP 500 / exception) -> failure AccessResult, never raises.
  (d) hard auth/quota status (401) -> fast failure, NO second paid call.
  (e) paywall stub from Zyte is rejected (faithfulness coupling — scraping
      bypasses bot-blocks, NOT paywalls).
"""

from __future__ import annotations

import base64
import json

import pytest

import src.tools.access_bypass as ab
from src.tools.access_bypass import AccessBypass, AccessResult


# A long, non-paywalled, content-word-rich body well over the 500-char floor.
_GOOD_BODY = (
    "The randomized controlled trial enrolled 1240 participants across "
    "fourteen centers. The primary endpoint of major adverse cardiovascular "
    "events was reduced by 23 percent in the treatment arm relative to "
    "placebo over a median follow-up of 3.2 years. Statistical analysis used "
    "a Cox proportional hazards model. Background, methods, results and "
    "discussion are reported in full below. " * 6
)
_GOOD_HTML = f"<html><body><article><p>{_GOOD_BODY}</p></article></body></html>"

# A short paywall stub — bypasses the bot-block but hits the paywall.
_PAYWALL_HTML = (
    "<html><body><p>To continue reading, subscribe to read the full "
    "article. Members only.</p></body></html>"
)


@pytest.fixture(autouse=True)
def _reset_zyte_module_state(monkeypatch):
    """Module-level breaker + telemetry counters leak across tests; reset them
    so an opened breaker or stale counter from one test cannot silently
    invalidate the next."""
    monkeypatch.setattr(ab, "_zyte_consecutive_failures", 0, raising=False)
    monkeypatch.setattr(ab, "_zyte_circuit_open_until", 0.0, raising=False)
    monkeypatch.setattr(ab, "_zyte_fallback_attempts", 0, raising=False)
    monkeypatch.setattr(ab, "_zyte_fallback_success", 0, raising=False)
    yield


class _FakeResponse:
    def __init__(self, status: int, payload: dict | None, text_body: str = ""):
        self.status = status
        self._payload = payload
        self._text = text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    """Records every POST payload and replays a queue of canned responses."""

    def __init__(self, responses: list[_FakeResponse], recorder: list[dict]):
        self._responses = list(responses)
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, headers=None, auth=None, json=None):  # noqa: A002
        self._recorder.append(dict(json or {}))
        if not self._responses:
            raise AssertionError("more POSTs issued than canned responses")
        return self._responses.pop(0)


def _install_fake_session(monkeypatch, responses, recorder):
    """Patch aiohttp.ClientSession (imported locally inside _try_zyte) to our
    fake. The local `import aiohttp` resolves to the real module, so we patch
    the attribute on that module."""
    import aiohttp

    def _factory(*args, **kwargs):
        return _FakeSession(responses, recorder)

    monkeypatch.setattr(aiohttp, "ClientSession", _factory)


def _cheap_response(html: str) -> _FakeResponse:
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return _FakeResponse(200, {"httpResponseBody": encoded})


def _browser_response(html: str) -> _FakeResponse:
    return _FakeResponse(200, {"browserHtml": html})


# ---------------------------------------------------------------------------
# (a) NO-OP when the key is absent — the safety crux.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_key_absent_zyte_never_called_and_failed_result_returned(monkeypatch):
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    # Sci-Hub stays disabled by default; nothing should reach a paid call.
    monkeypatch.delenv("PG_SCIHUB_ENABLED", raising=False)
    # Firecrawl is gated by `PG_FIRECRAWL_ENABLED=="1" AND FIRECRAWL_API_KEY`
    # (access_bypass.py:1072-1074). An ambient FIRECRAWL_API_KEY on the runner
    # would otherwise schedule a real Firecrawl backend and falsify the
    # no-spend / byte-unchanged free-chain assertion. Close BOTH halves of the
    # guard so hermeticity is robust to any inherited env.
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("PG_FIRECRAWL_ENABLED", "0")

    bypass = AccessBypass(use_archive_org=False, institutional_proxy=None)

    # Force the entire FREE chain to fail so control flow reaches the Zyte
    # call site (which is guarded by `if os.getenv("ZYTE_API_KEY")`).
    async def _fail_concurrent(*a, **k):
        return AccessResult(
            url="x", content="", access_method="crawl4ai",
            legal_alternative=None, success=False, metadata={},
        )

    async def _fail_direct(url):
        return AccessResult(
            url=url, content="", access_method="direct",
            legal_alternative=None, success=False, metadata={"error": "blocked"},
        )

    monkeypatch.setattr(bypass, "_try_crawl4ai", _fail_concurrent)
    monkeypatch.setattr(bypass, "_try_jina_reader", _fail_concurrent)
    monkeypatch.setattr(bypass, "_direct_fetch", _fail_direct)

    # If _try_zyte is ever invoked with the key absent, that's a spend bug.
    async def _boom(url):
        raise AssertionError("_try_zyte must NOT be invoked when key absent")

    monkeypatch.setattr(bypass, "_try_zyte", _boom)

    result = await bypass.fetch_with_bypass("https://example.com/paywalled")

    assert result.success is False
    assert result.access_method == "failed"
    assert result.metadata.get("error") == "All access methods failed"


@pytest.mark.asyncio
async def test_try_zyte_is_pure_noop_helper_when_key_absent(monkeypatch):
    """Calling the helper directly with no key returns a zero-spend failure."""
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    bypass = AccessBypass(use_archive_org=False)

    sentinel = {"posts": 0}
    import aiohttp

    def _factory(*a, **k):
        sentinel["posts"] += 1
        raise AssertionError("no HTTP session should be opened without a key")

    monkeypatch.setattr(aiohttp, "ClientSession", _factory)

    res = await bypass._try_zyte("https://example.com/x")
    assert res.success is False
    assert res.access_method == "zyte"
    assert res.metadata.get("error") == "ZYTE_API_KEY not set"
    assert sentinel["posts"] == 0


# ---------------------------------------------------------------------------
# (b) cheap-first, NO escalation on a good cheap result — the cost guarantee.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cheap_success_makes_exactly_one_call_no_escalation(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    bypass = AccessBypass(use_archive_org=False)

    recorder: list[dict] = []
    _install_fake_session(monkeypatch, [_cheap_response(_GOOD_HTML)], recorder)

    res = await bypass._try_zyte("https://example.com/good")

    assert res.success is True
    assert res.access_method == "zyte"
    assert res.metadata["zyte_mode"] == "httpResponseBody"
    assert res.metadata["escalated"] is False
    # Cost guarantee: exactly ONE paid call, and it was the CHEAP mode.
    assert len(recorder) == 1
    assert recorder[0].get("httpResponseBody") is True
    assert "browserHtml" not in recorder[0]
    assert ab._zyte_fallback_success == 1


# ---------------------------------------------------------------------------
# (b') escalate to browserHtml ONLY when the cheap result is unusable.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_short_cheap_result_escalates_to_browser_html(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    bypass = AccessBypass(use_archive_org=False)

    short_html = "<html><body><p>too short</p></body></html>"
    recorder: list[dict] = []
    _install_fake_session(
        monkeypatch,
        [_cheap_response(short_html), _browser_response(_GOOD_HTML)],
        recorder,
    )

    res = await bypass._try_zyte("https://example.com/js-heavy")

    assert res.success is True
    assert res.metadata["zyte_mode"] == "browserHtml"
    assert res.metadata["escalated"] is True
    # Cheap first, THEN browserHtml — exactly two calls in that order.
    assert len(recorder) == 2
    assert recorder[0].get("httpResponseBody") is True
    assert recorder[1].get("browserHtml") is True


# ---------------------------------------------------------------------------
# (c) Zyte error -> graceful failure, never raises.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_http_500_returns_failure_not_raise(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    bypass = AccessBypass(use_archive_org=False)

    recorder: list[dict] = []
    _install_fake_session(
        monkeypatch, [_FakeResponse(500, None, "server error")], recorder
    )

    res = await bypass._try_zyte("https://example.com/down")
    assert res.success is False
    assert res.metadata.get("status") == 500
    # A non-200 on the cheap call does NOT escalate into a second paid call.
    assert len(recorder) == 1


@pytest.mark.asyncio
async def test_exception_in_session_returns_failure_not_raise(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    bypass = AccessBypass(use_archive_org=False)

    import aiohttp

    def _factory(*a, **k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(aiohttp, "ClientSession", _factory)

    res = await bypass._try_zyte("https://example.com/x")
    assert res.success is False
    assert "network exploded" in res.metadata.get("error", "")


# ---------------------------------------------------------------------------
# (d) hard auth/quota status -> fast failure, NO second paid call.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_401_fails_fast_no_escalation(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "bad-key")
    bypass = AccessBypass(use_archive_org=False)

    recorder: list[dict] = []
    _install_fake_session(
        monkeypatch, [_FakeResponse(401, None, "unauthorized")], recorder
    )

    res = await bypass._try_zyte("https://example.com/x")
    assert res.success is False
    assert res.metadata.get("status") == 401
    assert res.metadata.get("error") == "auth_or_quota"
    # Hard auth error must NOT fire a second (browserHtml) paid call.
    assert len(recorder) == 1


# ---------------------------------------------------------------------------
# (e) a paywall stub from Zyte is rejected (faithfulness coupling).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paywall_stub_is_rejected(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    bypass = AccessBypass(use_archive_org=False)

    recorder: list[dict] = []
    # Both cheap and escalated return the same paywall stub -> terminal fail.
    _install_fake_session(
        monkeypatch,
        [_cheap_response(_PAYWALL_HTML), _browser_response(_PAYWALL_HTML)],
        recorder,
    )

    res = await bypass._try_zyte("https://example.com/paywalled")
    assert res.success is False
    # It escalated (cheap was unusable) but the browserHtml was ALSO a stub.
    assert len(recorder) == 2


# ---------------------------------------------------------------------------
# call-site escalation through the full fetch_with_bypass entry, key present.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_with_bypass_uses_zyte_after_free_chain_fails(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "test-key")
    monkeypatch.delenv("PG_SCIHUB_ENABLED", raising=False)
    # Firecrawl is gated by `PG_FIRECRAWL_ENABLED=="1" AND FIRECRAWL_API_KEY`
    # (access_bypass.py:1072-1074). Neutralize both halves so an ambient
    # FIRECRAWL_API_KEY cannot schedule a real backend and steal the win from
    # Zyte (this test asserts Zyte is reached after the free chain fails).
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("PG_FIRECRAWL_ENABLED", "0")
    bypass = AccessBypass(use_archive_org=False, institutional_proxy=None)

    async def _fail_concurrent(*a, **k):
        return AccessResult(
            url="x", content="", access_method="crawl4ai",
            legal_alternative=None, success=False, metadata={},
        )

    async def _fail_direct(url):
        return AccessResult(
            url=url, content="", access_method="direct",
            legal_alternative=None, success=False, metadata={"error": "blocked"},
        )

    monkeypatch.setattr(bypass, "_try_crawl4ai", _fail_concurrent)
    monkeypatch.setattr(bypass, "_try_jina_reader", _fail_concurrent)
    monkeypatch.setattr(bypass, "_direct_fetch", _fail_direct)

    recorder: list[dict] = []
    _install_fake_session(monkeypatch, [_cheap_response(_GOOD_HTML)], recorder)

    result = await bypass.fetch_with_bypass("https://example.com/needs-zyte")

    assert result.success is True
    assert result.access_method == "zyte"
    assert len(recorder) == 1  # cheap-first, won on the first paid call
