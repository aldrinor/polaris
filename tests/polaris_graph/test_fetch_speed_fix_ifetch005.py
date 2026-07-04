"""I-fetch-005 (fetch-speed, #1344) — offline unit tests for the four faithfulness-NEUTRAL,
§-1.3-safe transport-layer fetch-speed fixes.

Coverage:
  FIX 1 — crawl4ai circuit breaker HALF-OPEN recovery: opens after N consecutive failures,
          admits exactly ONE single-flight probe after the cooldown, a probe SUCCESS closes
          the breaker, a probe FAILURE re-opens with EXPONENTIAL backoff, a swarm of concurrent
          in-flight failures cannot re-inflate the backoff generation, and the finally backstop
          always releases the probe slot (never a permanent latch). Plus a behavioral
          ``_try_crawl4ai`` proof that a broken browser opens the breaker and a recovered browser
          closes it via the half-open probe (fake crawl4ai module — no real browser / network).
  FIX 2 — terminal hard-block (akamai_access_denied) FAST-SKIP: a terminal class is cached, a
          NON-terminal challenge class is NOT cached, ``fetch_with_bypass`` short-circuits a
          cached url with NO network call, and the skipped source is RETAINED (success=False,
          empty content = an unfetched source kept at ZERO weight downstream), NEVER dropped.
          Detector-OFF path is byte-identical (never populates, never short-circuits).
  FIX 4 — credibility LLM-tiering per-call timeout: a single HUNG tiering call is cut off after
          PG_TIER_LLM_PER_CALL_SECONDS (fails OPEN to the deterministic rules-floor WEIGHT, never
          a drop) instead of pinning the batch for the whole batch wall.

OFFLINE + spend-free: no real crawl4ai / Playwright / browser / network / LLM. The crawl4ai
package is stubbed via sys.modules; the tiering caller is a plain injected callable. NO
``unittest.mock`` (CLAUDE.md §9.4). Faithfulness-NEUTRAL: nothing here touches strict_verify /
NLI / D8 / provenance / span-grounding.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
import time
import types

import pytest

import src.tools.access_bypass as ab
from src.tools.access_bypass import AccessBypass
from src.polaris_graph.retrieval.credibility_llm_tiering import (
    classify_sources_llm_tiering,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
)


@contextlib.contextmanager
def _env(**overrides: str):
    """Set env vars for the block, restoring prior values on exit (hermetic under pytest AND a
    direct ``python file.py`` run)."""
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        yield
    finally:
        for k, prior in saved.items():
            if prior is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior


# ═════════════════════════════════════════════════════════════════════════════
# FIX 1 — crawl4ai circuit breaker HALF-OPEN recovery (pure state-machine).
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def _breaker(monkeypatch):
    """Reset breaker state + pin deterministic constants; restore on exit."""
    saved = (
        ab._CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD,
        ab._CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN,
        ab._CRAWL4AI_CIRCUIT_BREAKER_BACKOFF,
        ab._CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN,
    )
    ab.reset_crawl4ai_breaker_state()
    ab._CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = 3
    ab._CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = 100.0
    ab._CRAWL4AI_CIRCUIT_BREAKER_BACKOFF = 2.0
    ab._CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN = 600.0
    try:
        yield
    finally:
        (
            ab._CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD,
            ab._CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN,
            ab._CRAWL4AI_CIRCUIT_BREAKER_BACKOFF,
            ab._CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN,
        ) = saved
        ab.reset_crawl4ai_breaker_state()


def test_breaker_starts_closed(_breaker):
    decision, _ = ab._crawl4ai_breaker_admit()
    assert decision == "closed"


def test_breaker_opens_only_at_threshold(_breaker):
    # 2 failures (threshold 3) -> still closed.
    ab._crawl4ai_track_failure()
    ab._crawl4ai_track_failure()
    assert ab._crawl4ai_breaker_admit()[0] == "closed"
    # 3rd failure -> OPEN, generation 1, cooldown == base.
    ab._crawl4ai_track_failure()
    decision, remaining = ab._crawl4ai_breaker_admit()
    assert decision == "open"
    assert ab._crawl4ai_open_generation == 1
    assert 90.0 < remaining <= 100.0  # ~base cooldown, minus tiny elapsed


def test_half_open_single_flight_probe_after_cooldown(_breaker):
    # Open the breaker, then force the cooldown to have elapsed.
    for _ in range(3):
        ab._crawl4ai_track_failure()
    ab._crawl4ai_circuit_open_until = time.time() - 1.0  # cooldown elapsed
    # Exactly ONE caller becomes the probe; a concurrent second caller stays OPEN.
    first, _ = ab._crawl4ai_breaker_admit()
    second, _ = ab._crawl4ai_breaker_admit()
    assert first == "probe"
    assert second == "open"
    assert ab._crawl4ai_half_open_probe_active is True


def test_probe_success_closes_breaker(_breaker):
    for _ in range(3):
        ab._crawl4ai_track_failure()
    ab._crawl4ai_circuit_open_until = time.time() - 1.0
    assert ab._crawl4ai_breaker_admit()[0] == "probe"
    ab._crawl4ai_breaker_on_success()
    assert ab._crawl4ai_breaker_admit()[0] == "closed"
    assert ab._crawl4ai_consecutive_failures == 0
    assert ab._crawl4ai_circuit_open_until == 0.0
    assert ab._crawl4ai_half_open_probe_active is False
    assert ab._crawl4ai_open_generation == 0


def test_probe_failure_reopens_with_exponential_backoff(_breaker):
    for _ in range(3):
        ab._crawl4ai_track_failure()
    assert ab._crawl4ai_open_generation == 1
    # Cooldown elapses -> a probe is granted -> the probe FAILS (track_failure from the
    # elapsed-open window) -> re-open at generation 2 with base*backoff cooldown.
    ab._crawl4ai_circuit_open_until = time.time() - 1.0
    assert ab._crawl4ai_breaker_admit()[0] == "probe"
    ab._crawl4ai_track_failure()          # probe failure path
    ab._crawl4ai_breaker_finalize_probe()  # finally backstop (idempotent here)
    assert ab._crawl4ai_open_generation == 2
    decision, remaining = ab._crawl4ai_breaker_admit()
    assert decision == "open"
    # base 100 * backoff 2 == 200s.
    assert 190.0 < remaining <= 200.0
    assert ab._crawl4ai_half_open_probe_active is False


def test_finalize_probe_backstop_reopens_on_neutral_exit(_breaker):
    """A probe that resolves via NEITHER success nor a tracked failure (a neutral exit:
    RuntimeError / crawl-returned-False / timeout) must still release the slot AND re-open with
    backoff — never leave the breaker wedged in the elapsed-open window."""
    for _ in range(3):
        ab._crawl4ai_track_failure()
    ab._crawl4ai_circuit_open_until = time.time() - 1.0
    assert ab._crawl4ai_breaker_admit()[0] == "probe"
    # Neither on_success nor track_failure ran — only the finally backstop.
    ab._crawl4ai_breaker_finalize_probe()
    assert ab._crawl4ai_half_open_probe_active is False
    assert ab._crawl4ai_open_generation == 2  # re-opened with the next backoff generation
    assert ab._crawl4ai_breaker_admit()[0] == "open"


def test_swarm_of_concurrent_failures_does_not_inflate_generation(_breaker):
    """The post-open SWARM (concurrent in-flight failures arriving AFTER the breaker is already
    open) must NOT bump the backoff generation or reset the cooldown — the single open transition
    already armed it. This is the fix for the observed 'OPENED after 16 consecutive failures'
    latch where a swarm inflated the counter."""
    for _ in range(3):
        ab._crawl4ai_track_failure()  # opens at generation 1
    open_until = ab._crawl4ai_circuit_open_until
    for _ in range(13):
        ab._crawl4ai_track_failure()  # 13 concurrent in-flight failures while OPEN
    assert ab._crawl4ai_open_generation == 1
    assert ab._crawl4ai_circuit_open_until == open_until  # cooldown NOT reset by the swarm


def test_backed_off_cooldown_math_and_cap(_breaker):
    # base 100, backoff 2, max 600.
    assert ab._crawl4ai_backed_off_cooldown(1) == 100.0
    assert ab._crawl4ai_backed_off_cooldown(2) == 200.0
    assert ab._crawl4ai_backed_off_cooldown(3) == 400.0
    assert ab._crawl4ai_backed_off_cooldown(4) == 600.0  # 800 capped at 600
    assert ab._crawl4ai_backed_off_cooldown(9) == 600.0  # cap holds
    # BACKOFF <= 1.0 -> constant BASE cooldown (legacy shape).
    ab._CRAWL4AI_CIRCUIT_BREAKER_BACKOFF = 1.0
    assert ab._crawl4ai_backed_off_cooldown(5) == 100.0


# ── FIX 1 behavioral: _try_crawl4ai opens on a broken browser, recovers via a probe. ─────────

class _RecoverableResult:
    def __init__(self) -> None:
        self.success = True
        self.error_message = None
        self.status_code = 200
        self.redirected_url = None
        self.html = None
        self.markdown = "x" * 800


def _make_fake_crawl4ai(state: dict):
    """Fake crawl4ai module whose browser __aenter__ RAISES while ``state['broken']`` is True
    (simulating the missing-OS-lib browser-init failure on Box B) and succeeds once recovered.
    ``state['launches']`` counts successful browser launches."""

    class _FakeCrawler:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            if state["broken"]:
                raise RuntimeError("browser init failed: missing libnss3.so (fake)")
            state["launches"] += 1
            return self

        async def __aexit__(self, *exc):
            return False

        async def arun(self, *, url, config):
            return _RecoverableResult()

    mod = types.ModuleType("crawl4ai")
    mod.AsyncWebCrawler = _FakeCrawler
    mod.BrowserConfig = lambda *a, **k: object()
    mod.CrawlerRunConfig = lambda *a, **k: object()
    return mod


@pytest.mark.asyncio
async def test_try_crawl4ai_opens_on_broken_browser_then_recovers_via_probe(_breaker, monkeypatch):
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")
    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")
    ab._crawl4ai_semaphore = None
    ab._crawl4ai_available = None

    state = {"broken": True, "launches": 0}
    monkeypatch.setitem(sys.modules, "crawl4ai", _make_fake_crawl4ai(state))
    monkeypatch.setitem(
        sys.modules, "crawl4ai.markdown_generation_strategy",
        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
    )
    monkeypatch.setitem(
        sys.modules, "crawl4ai.content_filter_strategy",
        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
    )
    bypass = AccessBypass()

    # 3 failures (threshold 3) -> broken browser trips the breaker OPEN.
    for i in range(3):
        r = await bypass._try_crawl4ai(f"https://example.gov/broken/{i}")
        assert not r.success
    assert ab._crawl4ai_breaker_admit()[0] == "open"

    # While OPEN, a call is SKIPPED with no browser launch.
    r_open = await bypass._try_crawl4ai("https://example.gov/skipped")
    assert not r_open.success
    assert "circuit_breaker_open" in (r_open.metadata or {}).get("error", "")

    # Cooldown elapses + the browser recovers -> the single half-open probe launches ONE browser
    # and SUCCEEDS -> the breaker CLOSES.
    ab._crawl4ai_circuit_open_until = time.time() - 1.0
    state["broken"] = False
    r_probe = await bypass._try_crawl4ai("https://example.gov/recovered")
    assert r_probe.success, r_probe.metadata
    assert state["launches"] == 1  # exactly one browser launch on the probe
    assert ab._crawl4ai_breaker_admit()[0] == "closed"
    assert ab._crawl4ai_half_open_probe_active is False


@pytest.mark.asyncio
async def test_try_crawl4ai_probe_failure_releases_slot_and_reopens(_breaker, monkeypatch):
    """A half-open probe against a STILL-broken browser must fail, release the single-flight slot
    (no permanent latch), and re-open with backoff — never leave the breaker stuck 'probe in
    flight'."""
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")
    ab._crawl4ai_semaphore = None
    ab._crawl4ai_available = None
    state = {"broken": True, "launches": 0}
    monkeypatch.setitem(sys.modules, "crawl4ai", _make_fake_crawl4ai(state))
    monkeypatch.setitem(
        sys.modules, "crawl4ai.markdown_generation_strategy",
        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
    )
    monkeypatch.setitem(
        sys.modules, "crawl4ai.content_filter_strategy",
        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
    )
    bypass = AccessBypass()
    for i in range(3):
        await bypass._try_crawl4ai(f"https://example.gov/broken/{i}")
    assert ab._crawl4ai_open_generation == 1

    ab._crawl4ai_circuit_open_until = time.time() - 1.0  # cooldown elapsed -> next call = probe
    r = await bypass._try_crawl4ai("https://example.gov/still-broken")
    assert not r.success
    # Slot released (not wedged) and re-opened with the next backoff generation.
    assert ab._crawl4ai_half_open_probe_active is False
    assert ab._crawl4ai_open_generation == 2
    assert ab._crawl4ai_breaker_admit()[0] == "open"


# ═════════════════════════════════════════════════════════════════════════════
# FIX 2 — terminal hard-block (akamai_access_denied) FAST-SKIP.
# ═════════════════════════════════════════════════════════════════════════════

_AKAMAI_BODY = "<html><body>Access Denied — reference errors.edgesuite.net</body></html>"
_CLOUDFLARE_BODY = "<html><head><script>window._cf_chl_opt={};</script></head><body></body></html>"


@pytest.fixture()
def _terminal_cache():
    ab.reset_terminal_block_cache()
    try:
        yield
    finally:
        ab.reset_terminal_block_cache()


def test_is_block_page_caches_terminal_akamai_class(_terminal_cache):
    with _env(PG_BLOCK_PAGE_DETECTOR="1", PG_TERMINAL_BLOCK_FASTSKIP="1"):
        bypass = AccessBypass()
        url = "https://blocked.example.com/hard"
        flagged = bypass._is_block_page(url, _AKAMAI_BODY, {"seen": False})
    assert flagged is True
    assert ab.is_terminal_blocked(url) is True


def test_non_terminal_challenge_class_not_cached(_terminal_cache):
    """A JS/challenge WALL (cloudflare_challenge) is NOT terminal — a browser-rendering backend can
    still pass it — so it must NOT be cached as a terminal block (§-1.3: never suppress a fetch
    that could succeed)."""
    with _env(PG_BLOCK_PAGE_DETECTOR="1", PG_TERMINAL_BLOCK_FASTSKIP="1"):
        bypass = AccessBypass()
        url = "https://challenge.example.com/js"
        flagged = bypass._is_block_page(url, _CLOUDFLARE_BODY, {"seen": False})
    assert flagged is True  # it IS a block page (re-routed)
    assert ab.is_terminal_blocked(url) is False  # but NOT terminal-cached


def test_detector_off_never_populates_terminal_cache(_terminal_cache):
    with _env(PG_BLOCK_PAGE_DETECTOR="0", PG_TERMINAL_BLOCK_FASTSKIP="1"):
        bypass = AccessBypass()
        url = "https://blocked.example.com/off"
        flagged = bypass._is_block_page(url, _AKAMAI_BODY, {"seen": False})
    assert flagged is False  # detector OFF -> no-op
    assert ab.is_terminal_blocked(url) is False


@pytest.mark.asyncio
async def test_fetch_with_bypass_short_circuits_terminal_url_no_network(_terminal_cache):
    """A url previously flagged terminal short-circuits the WHOLE cascade with NO network call.
    §-1.3: the source is RETAINED (success=False + empty content = an unfetched source kept at
    ZERO weight downstream), NEVER dropped/raised."""
    url = "https://blocked.example.com/hard"
    ab._record_terminal_block(url)
    with _env(PG_BLOCK_PAGE_DETECTOR="1", PG_TERMINAL_BLOCK_FASTSKIP="1"):
        bypass = AccessBypass()
        result = await bypass.fetch_with_bypass(url)
    assert result.success is False
    assert result.content == ""  # retained-but-unfetched (zero weight), not fabricated
    assert result.access_method == "terminal_block_skipped"
    assert (result.metadata or {}).get("reason") == "akamai_access_denied"


def test_terminal_fastskip_killswitch_off_does_not_populate(_terminal_cache):
    """PG_TERMINAL_BLOCK_FASTSKIP=0 reverts to re-walking the cascade (never caches), even with the
    detector ON — a clean rollback."""
    with _env(PG_BLOCK_PAGE_DETECTOR="1", PG_TERMINAL_BLOCK_FASTSKIP="0"):
        bypass = AccessBypass()
        url = "https://blocked.example.com/killswitch"
        bypass._is_block_page(url, _AKAMAI_BODY, {"seen": False})
    assert ab.is_terminal_blocked(url) is False


def test_reset_terminal_block_cache_clears(_terminal_cache):
    ab._record_terminal_block("https://x.example.com/a")
    assert ab.is_terminal_blocked("https://x.example.com/a") is True
    ab.reset_terminal_block_cache()
    assert ab.is_terminal_blocked("https://x.example.com/a") is False


# ═════════════════════════════════════════════════════════════════════════════
# FIX 4 — credibility LLM-tiering PER-CALL timeout (fail-open to the rules-floor WEIGHT).
# ═════════════════════════════════════════════════════════════════════════════

def _sources(n: int, *, slow_index: int) -> list[ClassificationSignals]:
    out: list[ClassificationSignals] = []
    for i in range(n):
        marker = "slow" if i == slow_index else "fast"
        out.append(
            ClassificationSignals(
                url=f"https://example.com/{marker}/tier-T4/src-{i}",
                title=f"Source {i}",
                fetched_content_length=5000,
            )
        )
    return out


class _StragglerCaller:
    """Fast for every source except the one whose URL carries ``/slow/`` — that one HANGS long
    enough to exceed the per-call timeout (a wedged tiering socket)."""

    def __init__(self, *, slow_sleep: float) -> None:
        self.slow_sleep = slow_sleep

    def __call__(self, prompt: str) -> str:
        if "/slow/" in prompt:
            time.sleep(self.slow_sleep)
        return '{"tier": "T4", "rationale": "encoded T4"}'


def test_per_call_timeout_cuts_hung_straggler_fast_not_batch_wall():
    """A SINGLE hung tiering call is cut off after PG_TIER_LLM_PER_CALL_SECONDS — the batch returns
    quickly (well under the 600s batch wall) with the straggler at the deterministic rules-floor
    (present, NOT dropped — §-1.3)."""
    n = 8
    slow_index = n - 1
    caller = _StragglerCaller(slow_sleep=5.0)  # far longer than the tiny per-call cutoff
    sources = _sources(n, slow_index=slow_index)
    with _env(
        PG_TIER_LLM_PARALLEL="1",
        PG_TIER_REQUIRE_VENUE_CORROBORATION="0",
        PG_TIER_LLM_DEGRADE_AFTER="0",          # isolate the per-call path from the breaker
        PG_TIER_LLM_BATCH_WALL_SECONDS="600",    # generous batch wall so ONLY the per-call cutoff binds
        PG_TIER_LLM_PER_CALL_SECONDS="0.4",      # tiny per-call cutoff
    ):
        t0 = time.monotonic()
        result = classify_sources_llm_tiering(sources, call_llm=caller, max_workers=n)
        elapsed = time.monotonic() - t0

    # Returned FAST — bounded by the per-call cutoff, NOT the 5s straggler or the 600s wall.
    assert elapsed < 2.5, f"batch took {elapsed:.2f}s — per-call cutoff did not bind"
    # No drop: every source present (§-1.3).
    assert len(result) == n
    # The fast sources were tiered via the LLM leg; the hung straggler kept its rules-floor WEIGHT.
    straggler = result[slow_index]
    assert straggler.matched_rules != ["llm_tiering"]
    assert isinstance(straggler.tier, TierLevel)  # a real fallback tier, NOT dropped/None
    for i in range(n):
        if i == slow_index:
            continue
        assert result[i].matched_rules == ["llm_tiering"], (i, result[i].matched_rules)
    # Honest status: 7 via GLM, 1 at the rules-floor -> partial (never a false 'tiered_via_glm').
    status = result.tiering_status
    assert status["total"] == n
    assert status["llm_success_count"] == n - 1
    assert status["rules_floor_count"] == 1
    assert status["tiering_mode"] == "partial"


def test_per_call_disabled_falls_back_to_batch_wall_semantics():
    """PG_TIER_LLM_PER_CALL_SECONDS<=0 disables the per-call cutoff: the tail is bounded only by the
    (tight, via caller-deadline) batch wall — legacy behavior, straggler still kept at the floor."""
    n = 6
    slow_index = n - 1
    caller = _StragglerCaller(slow_sleep=2.0)
    sources = _sources(n, slow_index=slow_index)
    with _env(
        PG_TIER_LLM_PARALLEL="1",
        PG_TIER_REQUIRE_VENUE_CORROBORATION="0",
        PG_TIER_LLM_DEGRADE_AFTER="0",
        PG_TIER_LLM_BATCH_WALL_SECONDS="600",
        PG_TIER_LLM_PER_CALL_SECONDS="0",  # disabled
    ):
        result = classify_sources_llm_tiering(
            sources, call_llm=caller, max_workers=n,
            deadline_monotonic=time.monotonic() + 0.3,  # tight wall bounds the tail instead
        )
    assert len(result) == n
    assert result[slow_index].matched_rules != ["llm_tiering"]  # straggler at rules-floor, not dropped
    assert result[slow_index].tier is not None


# ═════════════════════════════════════════════════════════════════════════════
# ITER-2 P1 — malformed PG_CRAWL4AI_TIMEOUT must NOT leak the half-open probe slot.
# ═════════════════════════════════════════════════════════════════════════════

def test_crawl4ai_timeout_seconds_defensive_parse(_breaker):
    """The timeout parse never raises: a valid value passes through; malformed / empty /
    non-positive values fall back to 30s. (The prior bare ``int(os.getenv(...))`` raised
    ValueError on a malformed value BETWEEN the breaker admit and the try/finally that
    releases the probe slot — leaking the slot forever.)"""
    with _env(PG_CRAWL4AI_TIMEOUT="45"):
        assert ab._crawl4ai_timeout_seconds() == 45
    with _env(PG_CRAWL4AI_TIMEOUT="not-an-int"):
        assert ab._crawl4ai_timeout_seconds() == 30
    with _env(PG_CRAWL4AI_TIMEOUT="   "):
        assert ab._crawl4ai_timeout_seconds() == 30
    with _env(PG_CRAWL4AI_TIMEOUT="0"):
        assert ab._crawl4ai_timeout_seconds() == 30   # non-positive clamps to 30
    with _env(PG_CRAWL4AI_TIMEOUT="-5"):
        assert ab._crawl4ai_timeout_seconds() == 30
    saved = os.environ.pop("PG_CRAWL4AI_TIMEOUT", None)
    try:
        assert ab._crawl4ai_timeout_seconds() == 30   # unset -> default 30
    finally:
        if saved is not None:
            os.environ["PG_CRAWL4AI_TIMEOUT"] = saved


@pytest.mark.asyncio
async def test_malformed_timeout_does_not_leak_probe_slot(_breaker, monkeypatch):
    """ITER-2 P1 behavioural: with the breaker OPEN, the cooldown elapsed, and a MALFORMED
    PG_CRAWL4AI_TIMEOUT, the next call becomes the single-flight half-open probe. It must (a)
    NOT raise out of the "NEVER raises" method, and (b) NOT leave the probe slot wedged True.
    Here the browser is broken, so the probe fails and the slot is released via the backstop."""
    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "garbage-not-int")  # would raise pre-fix
    ab._crawl4ai_semaphore = None
    ab._crawl4ai_available = None
    state = {"broken": True, "launches": 0}
    monkeypatch.setitem(sys.modules, "crawl4ai", _make_fake_crawl4ai(state))
    monkeypatch.setitem(
        sys.modules, "crawl4ai.markdown_generation_strategy",
        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
    )
    monkeypatch.setitem(
        sys.modules, "crawl4ai.content_filter_strategy",
        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
    )
    bypass = AccessBypass()
    for i in range(3):
        await bypass._try_crawl4ai(f"https://example.gov/broken/{i}")
    assert ab._crawl4ai_breaker_admit()[0] == "open"

    ab._crawl4ai_circuit_open_until = time.time() - 1.0  # cooldown elapsed -> next call = probe
    # Must NOT raise despite the malformed timeout, and must NOT leak the probe slot.
    r = await bypass._try_crawl4ai("https://example.gov/probe-malformed-timeout")
    assert not r.success
    assert ab._crawl4ai_half_open_probe_active is False   # slot released, not wedged
    assert ab._crawl4ai_breaker_admit()[0] == "open"       # re-opened with backoff, recoverable


# ═════════════════════════════════════════════════════════════════════════════
# ITER-2 Fable — stale terminal-block cache cleared on a later clean cascade hop.
# ═════════════════════════════════════════════════════════════════════════════

def test_terminal_cache_cleared_when_later_cascade_hop_succeeds(_terminal_cache):
    """Fable: a url flagged TERMINAL by an EARLY cascade hop (direct hit akamai_access_denied)
    but then fetched cleanly by a LATER hop (archive.org) in the SAME cascade must NOT remain
    cached — otherwise a later fetch of this provably-fetchable url wrongly fast-skips straight
    to failure. `_finalize_clean_fetch` discards the url on any clean success. Faithfulness-
    neutral: the result passes through unchanged; only a stale PERFORMANCE cache entry is cleared."""
    with _env(PG_BLOCK_PAGE_DETECTOR="1", PG_TERMINAL_BLOCK_FASTSKIP="1"):
        bypass = AccessBypass()
        url = "https://recoverable.example.com/doc"
        # 1. direct hop hits akamai_access_denied -> terminal cache populated mid-cascade.
        assert bypass._is_block_page(url, _AKAMAI_BODY, {"seen": False}) is True
        assert ab.is_terminal_blocked(url) is True
        # 2. archive.org hop returns clean content for the SAME url -> finalize clears the
        #    now-stale terminal entry (all fetch helpers preserve the original url on result.url).
        archive_result = ab.AccessResult(
            url=url, content="x" * 4000, access_method="archive.org",
            legal_alternative="https://web.archive.org/…", success=True, metadata={},
        )
        returned = bypass._finalize_clean_fetch(archive_result, {"seen": True})
    assert returned is archive_result             # pure passthrough (faithfulness-neutral)
    assert ab.is_terminal_blocked(url) is False    # the STALE terminal entry is discarded


def test_finalize_clean_fetch_discard_is_idempotent(_terminal_cache):
    """Discarding a url that was never terminal-cached is a safe no-op (idempotent)."""
    bypass = AccessBypass()
    url = "https://never-blocked.example.com/x"
    result = ab.AccessResult(
        url=url, content="y" * 3000, access_method="direct",
        legal_alternative=None, success=True, metadata={},
    )
    # Not cached -> discard-on-success is a no-op, still not blocked, result unchanged.
    assert ab.is_terminal_blocked(url) is False
    assert bypass._finalize_clean_fetch(result, {"seen": False}) is result
    assert ab.is_terminal_blocked(url) is False


if __name__ == "__main__":  # pragma: no cover — direct-run convenience
    sys.exit(pytest.main([__file__, "-v"]))
