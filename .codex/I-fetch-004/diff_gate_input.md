HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex DIFF gate — I-fetch-004 (#1185): operator-authorized PAID Zyte fetch fallback

You are reviewing a code DIFF (not a plan). Output the §8.3.9 schema and end with a final `verdict:` line.

## Output schema (BIND TO THIS — loose prose is rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

The CI gate parses the LAST `verdict:` line of this file. Emit exactly one final `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.

## What this change is

I-fetch-004 wires an **operator-authorized PAID Zyte fetch fallback** into `AccessBypass.fetch_with_bypass` (`src/tools/access_bypass.py`) as the genuine **last resort**, after the entire FREE chain has failed.

- Operator-authorized. Validated by the author 6/6 on real failing clinical URLs; cost measured ~$0.0017/request.
- **Env-gated NO-OP** when `ZYTE_API_KEY` is absent — the call site guards on the key, so `_try_zyte` is never invoked on un-keyed runs; the helper itself also returns a zero-spend failure if called keyless (double-safe).
- **Cheap-first then escalate:** the cheap `httpResponseBody` Zyte mode is tried first; the pricier JS-rendering `browserHtml` mode runs ONLY when the cheap result is unusable (None / too short / paywalled). A hard auth/quota status (401/402/403/429) returns fast WITHOUT a second paid call.
- **Faithfulness-UNAFFECTED:** Zyte only RETRIEVES raw HTML. The retrieved bytes are routed through the SAME `safe_trafilatura_extract` extractor every other backend uses, then `_strip_navigation_boilerplate`, then a paywall + min-length gate, and on success flow into the normal evidence pool which still passes the downstream `strict_verify` + 4-role gates. No faithfulness gate is bypassed.
- Smoke: 9/9 offline tests pass (`tests/polaris_graph/test_zyte_fallback.py`), including `zyte_recovered=true` and `free_chain_unaffected=true` (key-absent path returns the byte-identical `access_method="failed"` total-failure result).

## VERIFY THESE FIVE SAFETY COUPLINGS line-by-line against the diff below

1. **`ZYTE_API_KEY` absent → byte-identical free-chain behavior + ZERO spend.** Confirm the call site (`access_bypass.py` ~L1236) only enters the Zyte block when `os.getenv("ZYTE_API_KEY")` is truthy, that nothing else changed on the keyless path, and that the helper opens NO HTTP session without a key. This is THE safety crux. The test `test_key_absent_zyte_never_called_and_failed_result_returned` asserts `_try_zyte` is never invoked and the result is unchanged (`access_method="failed"`, `error="All access methods failed"`).
2. **Zyte runs ONLY after the free chain fails — last resort, not a replacement.** Confirm the call site sits AFTER the optional Sci-Hub block and immediately BEFORE the total-failure `return`, so no free method is skipped or displaced. Confirm the free methods (direct / concurrent group / Archive.org / proxy / timeout-retry / Sci-Hub) are untouched.
3. **No faithfulness bypass — Zyte content flows through the SAME downstream gates.** Confirm the retrieved HTML goes through `safe_trafilatura_extract` (same extractor as siblings), `_strip_navigation_boilerplate`, and is rejected unless it clears `_detect_paywall` AND the `_ZYTE_MIN_CONTENT_CHARS` floor. Confirm there is no path that returns Zyte content as `success=True` while skipping the paywall/length gate. Note the issue's premise: scraping bypasses bot-blocks, NOT paywalls — so a paywall stub remains possible and MUST be rejected (`test_paywall_stub_is_rejected`).
4. **Errors return a failure AccessResult gracefully — no crash, per-call timeout.** Confirm every error branch (non-200, 401/402/403/429, exception) returns a failure `AccessResult` (never raises into the fetch loop), that a per-call `aiohttp.ClientTimeout(total=_ZYTE_TIMEOUT)` bounds both requests, and that a hard auth/quota status does NOT fire the second (browserHtml) paid call. Confirm the circuit breaker (`_zyte_consecutive_failures` / `_zyte_circuit_open_until`) prevents N doomed paid calls on a ~1000-URL run and mirrors the existing firecrawl/jina breaker.
5. **No magic numbers (LAW VI).** Confirm every threshold is env-overridable: `_ZYTE_TIMEOUT` (`PG_ZYTE_TIMEOUT`), `_ZYTE_MIN_CONTENT_CHARS` (`PG_ZYTE_MIN_CONTENT_CHARS`), `_ZYTE_API_ENDPOINT` (`PG_ZYTE_API_ENDPOINT`), and that the breaker reuses the existing `_CIRCUIT_BREAKER_THRESHOLD` / `_CIRCUIT_BREAKER_COOLDOWN` constants. The `content[:50000]` truncation and the `[:200]`/`[:120]` log clamps are the only literals — judge whether any rises to a real P0/P1 (the author's view: log clamps + the 50k content cap mirror existing sibling backends and are not tunable thresholds).

Also check generally: counter/global handling (no `UnboundLocalError` on the `+= 1` lines — confirm the `global` declarations cover every reassigned name), success resets `_zyte_consecutive_failures` to 0, telemetry counters are incremented correctly, and the diff does not regress any sibling backend.

## Files the author ALSO checked and reports clean

- Helper dependencies all pre-exist in the same module: `safe_trafilatura_extract` (def L318), `_strip_navigation_boilerplate` (def L501), `_detect_paywall` (method L2969), `_NO_BROTLI_HEADERS` (L54), `_safe_log_str` (L36), `_time_module` (`import time as _time_module` L28).
- No other call sites of `_try_zyte` outside `fetch_with_bypass`; no sibling backend touched.
- `tests/polaris_graph/test_zyte_fallback.py` is the only test file; 9/9 pass offline with a fake `aiohttp.ClientSession` (no network, no spend).

NOTE ON THE DIFF BELOW: the new test file `tests/polaris_graph/test_zyte_fallback.py` is currently UNTRACKED (a new file), so `git diff` shows only the `src/tools/access_bypass.py` modification. The full test source is pasted in the APPENDIX after the diff so you can review test coverage in the same pass.

---

## DIFF (`git --no-pager diff -- src/tools/access_bypass.py tests/`)

```diff
diff --git a/src/tools/access_bypass.py b/src/tools/access_bypass.py
index cddb8407..9b30c20f 100644
--- a/src/tools/access_bypass.py
+++ b/src/tools/access_bypass.py
@@ -62,10 +62,32 @@ _jina_consecutive_failures: int = 0
 _jina_circuit_open_until: float = 0.0
 _firecrawl_consecutive_failures: int = 0
 _firecrawl_circuit_open_until: float = 0.0
+# I-fetch-004 (#1185): circuit breaker for the PAID Zyte fallback. Mirrors the
+# firecrawl/jina breaker so a Zyte outage cannot fire N doomed PAID calls on a
+# ~1000-URL run. Shares the same threshold/cooldown constants below.
+_zyte_consecutive_failures: int = 0
+_zyte_circuit_open_until: float = 0.0
 # FIX-G: Raised defaults — threshold 5→8, cooldown 60→120s for transient tolerance
 _CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("PG_CIRCUIT_BREAKER_THRESHOLD", "8"))
 _CIRCUIT_BREAKER_COOLDOWN = float(os.getenv("PG_CIRCUIT_BREAKER_COOLDOWN", "120.0"))
 
+# I-fetch-004 (#1185): Zyte paid-fallback telemetry + tunables (LAW VI — no
+# hard-coded thresholds; every knob is env-overridable). These counters are
+# separate from the circuit-breaker failure counter above: attempts/successes
+# track usage, the breaker tracks consecutive failures.
+_zyte_fallback_attempts: int = 0
+_zyte_fallback_success: int = 0
+# Per-call HTTP timeout for both the cheap (httpResponseBody) and escalated
+# (browserHtml) Zyte requests.
+_ZYTE_TIMEOUT = float(os.getenv("PG_ZYTE_TIMEOUT", "60.0"))
+# Minimum usable-content length. Shared by the escalation trigger (a cheap
+# result shorter than this escalates to browserHtml) and the final success
+# gate (content shorter than this is rejected). Mirrors the 500-char floor used
+# by the PDF/crawl4ai paths.
+_ZYTE_MIN_CONTENT_CHARS = int(os.getenv("PG_ZYTE_MIN_CONTENT_CHARS", "500"))
+# Zyte API endpoint (override only for testing against a mock server).
+_ZYTE_API_ENDPOINT = os.getenv("PG_ZYTE_API_ENDPOINT", "https://api.zyte.com/v1/extract")
+
 # ---------------------------------------------------------------------------
 # Crawl4AI availability flag (set on first import attempt)
 # ---------------------------------------------------------------------------
@@ -1200,6 +1222,25 @@ class AccessBypass:
                 scihub_result.content = _strip_navigation_boilerplate(scihub_result.content)
                 return scihub_result
 
+        # I-fetch-004 (#1185): PAID Zyte fallback — the genuine LAST resort,
+        # ONLY after the entire FREE chain (PDF/Unpaywall/PMC-BioC -> concurrent
+        # quality-scored group -> direct -> Archive.org -> proxy -> timeout-retry
+        # -> Sci-Hub) has failed. STRICT NO-OP: when ZYTE_API_KEY is absent the
+        # helper is never even invoked, so behaviour here is byte-identical to
+        # before (zero spend, zero risk on un-keyed runs). Zyte only RETRIEVES
+        # raw content; the returned text still flows through the SAME extractor
+        # and the downstream strict_verify / 4-role faithfulness gates — no gate
+        # is bypassed. _try_zyte strips boilerplate internally and only returns
+        # success on non-paywalled content above the min-length floor, so there
+        # is no extra strip needed at this call site.
+        if os.getenv("ZYTE_API_KEY"):
+            logger.info(
+                "[ACCESS] I-fetch-004: Trying Zyte paid fallback for %s", url[:60]
+            )
+            zyte_result = await self._try_zyte(url)
+            if zyte_result.success:
+                return zyte_result
+
         # SF-40: Log total failure at WARNING (was completely silent)
         logger.warning("[ACCESS] ALL access methods exhausted for %s", url[:80])
         return AccessResult(
@@ -1937,6 +1978,268 @@ class AccessBypass:
             metadata={"error": "Unexpected loop exit"},
         )
 
+    async def _try_zyte(self, url: str) -> AccessResult:
+        """I-fetch-004 (#1185): PAID Zyte fallback — the genuine last resort.
+
+        Called by `fetch_with_bypass` ONLY after the entire free chain
+        (direct -> concurrent quality-scored group -> Archive.org -> proxy ->
+        timeout-retry -> Sci-Hub) has failed.
+
+        Safety couplings (all required):
+          - ENV-GATED: with ZYTE_API_KEY absent this is a complete NO-OP that
+            returns a failure AccessResult and spends nothing. The call site
+            also guards on the key, so the helper is never even invoked on
+            un-keyed runs (double-safe — behaviour byte-identical to before).
+          - COST-SMART: tries the cheap httpResponseBody mode first and
+            escalates to the pricier JS-rendering browserHtml mode ONLY when
+            the cheap result is unusable (empty / short / paywalled). A hard
+            auth/quota error (401/402/429) returns fast WITHOUT a second paid
+            call.
+          - CIRCUIT BREAKER: after N consecutive failures the breaker opens for
+            a cooldown so a Zyte outage cannot fire N doomed PAID calls on a
+            ~1000-URL run.
+          - FAITHFULNESS-UNAFFECTED: Zyte only RETRIEVES raw HTML; it is routed
+            through the SAME `safe_trafilatura_extract` extractor every other
+            backend uses, then through the downstream strict_verify / 4-role
+            gates. No faithfulness gate is bypassed. The issue notes scraping
+            bypasses bot-blocks, NOT paywalls — so a paywall stub remains a
+            live possibility and is rejected by `_detect_paywall` before any
+            success is returned.
+
+        Zyte API (docs.zyte.com): POST https://api.zyte.com/v1/extract, HTTP
+        Basic auth with the API key as username and an EMPTY password.
+        httpResponseBody is BASE64-encoded; browserHtml is a plain HTML string.
+        """
+        import aiohttp
+        import base64
+
+        # Telemetry + breaker globals. Declared together so the `+= 1` lines
+        # below do not raise UnboundLocalError.
+        global _zyte_consecutive_failures, _zyte_circuit_open_until
+        global _zyte_fallback_attempts, _zyte_fallback_success
+
+        # ENV-GATE (strict NO-OP, zero spend when the key is absent).
+        key = os.getenv("ZYTE_API_KEY")
+        if not key:
+            return AccessResult(
+                url=url,
+                content="",
+                access_method="zyte",
+                legal_alternative=None,
+                success=False,
+                metadata={"error": "ZYTE_API_KEY not set"},
+            )
+
+        # CIRCUIT BREAKER: skip (no paid call) while open.
+        now = _time_module.time()
+        if _zyte_circuit_open_until > now:
+            remaining = _zyte_circuit_open_until - now
+            logger.debug(
+                "[ACCESS] Zyte circuit breaker OPEN for %s (%.0fs remaining)",
+                url[:60], remaining,
+            )
+            return AccessResult(
+                url=url,
+                content="",
+                access_method="zyte",
+                legal_alternative=None,
+                success=False,
+                metadata={
+                    "error": "circuit_breaker_open",
+                    "cooldown_remaining": remaining,
+                },
+            )
+
+        def _record_failure() -> None:
+            """Increment the breaker and open it at threshold."""
+            global _zyte_consecutive_failures, _zyte_circuit_open_until
+            _zyte_consecutive_failures += 1
+            if _zyte_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
+                _zyte_circuit_open_until = (
+                    _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
+                )
+                logger.warning(
+                    "[ACCESS] Zyte circuit breaker OPENED after %d consecutive "
+                    "failures (cooldown %.0fs)",
+                    _zyte_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
+                )
+
+        def _is_usable(text: "str | None") -> bool:
+            """Usable = extracted, long enough, and not a paywall stub."""
+            if not text or len(text) < _ZYTE_MIN_CONTENT_CHARS:
+                return False
+            if self._detect_paywall(text):
+                return False
+            return True
+
+        timeout = aiohttp.ClientTimeout(total=_ZYTE_TIMEOUT)
+        headers = {**_NO_BROTLI_HEADERS, "Content-Type": "application/json"}
+        auth = aiohttp.BasicAuth(key, "")
+
+        _zyte_fallback_attempts += 1
+
+        try:
+            async with aiohttp.ClientSession(timeout=timeout) as session:
+                # (1) CHEAP mode: httpResponseBody (base64-encoded).
+                async with session.post(
+                    _ZYTE_API_ENDPOINT,
+                    headers=headers,
+                    auth=auth,
+                    json={"url": url, "httpResponseBody": True},
+                ) as resp:
+                    status = resp.status
+                    # DIFFERENTIATED hard-error handling: auth/quota/rate-limit
+                    # return fast and count toward the breaker — do NOT escalate
+                    # a hard error into a second paid call.
+                    if status in (401, 402, 403, 429):
+                        body = (await resp.text())[:200]
+                        logger.warning(
+                            "[ACCESS] Zyte cheap request returned %d for %s: %s",
+                            status, url[:60], _safe_log_str(body, 120),
+                        )
+                        _record_failure()
+                        return AccessResult(
+                            url=url, content="", access_method="zyte",
+                            legal_alternative=None, success=False,
+                            metadata={"status": status, "error": "auth_or_quota"},
+                        )
+                    if status != 200:
+                        logger.warning(
+                            "[ACCESS] Zyte cheap request returned status %d for %s",
+                            status, url[:60],
+                        )
+                        _record_failure()
+                        return AccessResult(
+                            url=url, content="", access_method="zyte",
+                            legal_alternative=None, success=False,
+                            metadata={"status": status},
+                        )
+                    data = await resp.json()
+
+                encoded = (data or {}).get("httpResponseBody")
+                cheap_text: "str | None" = None
+                if encoded:
+                    html = base64.b64decode(encoded).decode(
+                        "utf-8", errors="replace"
+                    )
+                    cheap_text = safe_trafilatura_extract(
+                        html,
+                        include_tables=True,
+                        include_links=False,
+                        output_format="txt",
+                    )
+
+                used_text = cheap_text
+                mode = "httpResponseBody"
+                escalated = False
+
+                # (2) ESCALATE to browserHtml ONLY when the cheap result is
+                # unusable (None / too short / paywalled). browserHtml is the
+                # pricier JS-rendering, ban-solving mode.
+                if not _is_usable(cheap_text):
+                    escalated = True
+                    mode = "browserHtml"
+                    async with session.post(
+                        _ZYTE_API_ENDPOINT,
+                        headers=headers,
+                        auth=auth,
+                        json={"url": url, "browserHtml": True},
+                    ) as resp2:
+                        status2 = resp2.status
+                        if status2 in (401, 402, 403, 429):
+                            body2 = (await resp2.text())[:200]
+                            logger.warning(
+                                "[ACCESS] Zyte browserHtml returned %d for %s: %s",
+                                status2, url[:60], _safe_log_str(body2, 120),
+                            )
+                            _record_failure()
+                            return AccessResult(
+                                url=url, content="", access_method="zyte",
+                                legal_alternative=None, success=False,
+                                metadata={"status": status2, "error": "auth_or_quota"},
+                            )
+                        if status2 != 200:
+                            logger.warning(
+                                "[ACCESS] Zyte browserHtml returned status %d for %s",
+                                status2, url[:60],
+                            )
+                            _record_failure()
+                            return AccessResult(
+                                url=url, content="", access_method="zyte",
+                                legal_alternative=None, success=False,
+                                metadata={"status": status2},
+                            )
+                        data2 = await resp2.json()
+                    browser_html = (data2 or {}).get("browserHtml")
+                    used_text = None
+                    if browser_html:
+                        used_text = safe_trafilatura_extract(
+                            browser_html,
+                            include_tables=True,
+                            include_links=False,
+                            output_format="txt",
+                        )
+
+            # POST-PROCESSING CONSISTENCY: strip boilerplate (every sibling
+            # return does this) then gate on paywall + min-length so a stub
+            # can never pollute the evidence pool.
+            content = _strip_navigation_boilerplate(used_text or "")
+            if (
+                content
+                and len(content) >= _ZYTE_MIN_CONTENT_CHARS
+                and not self._detect_paywall(content)
+            ):
+                _zyte_consecutive_failures = 0
+                _zyte_fallback_success += 1
+                logger.info(
+                    "[ACCESS] Zyte succeeded for %s (%d chars, mode=%s, "
+                    "escalated=%s, attempts=%d, successes=%d)",
+                    url[:60], len(content), mode, escalated,
+                    _zyte_fallback_attempts, _zyte_fallback_success,
+                )
+                return AccessResult(
+                    url=url,
+                    content=content[:50000],
+                    access_method="zyte",
+                    legal_alternative=None,
+                    success=True,
+                    metadata={
+                        "content_length": len(content),
+                        "zyte_mode": mode,
+                        "escalated": escalated,
+                    },
+                )
+
+            # Unusable (short / paywalled / empty) — terminal failure, no
+            # further escalation.
+            _record_failure()
+            logger.info(
+                "[ACCESS] Zyte produced unusable content for %s "
+                "(mode=%s, escalated=%s)",
+                url[:60], mode, escalated,
+            )
+            return AccessResult(
+                url=url, content="", access_method="zyte",
+                legal_alternative=None, success=False,
+                metadata={
+                    "error": "unusable_content",
+                    "zyte_mode": mode,
+                    "escalated": escalated,
+                },
+            )
+
+        except Exception as e:
+            # Never crash the fetch loop — any error returns a failure result.
+            _record_failure()
+            logger.warning(
+                "[ACCESS] Zyte failed for %s: %s", url[:80], str(e)[:150],
+            )
+            return AccessResult(
+                url=url, content="", access_method="zyte",
+                legal_alternative=None, success=False,
+                metadata={"error": str(e)[:200]},
+            )
+
     async def _try_firecrawl(self, url: str) -> AccessResult:
         """
         FIX-D2 Hardened: Firecrawl with rate limiting, credit tracking,

```

---

## APPENDIX — new (untracked) test file `tests/polaris_graph/test_zyte_fallback.py`

```python
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

```
