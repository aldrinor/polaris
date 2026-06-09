HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution/faithfulness risks; classify non-blockers as P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Output: a final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`, plus a short blockers list.

# Diff review — I-beatboth-429 (#1173): 4-role role transport HTTP 429/503 backoff-retry

## Context
The beat-both 5-question run generated real reports (drb_72 75-verified, drb_75 74-verified sentences) but EVERY question's 4-role seam HELD release on `RoleTransportError: OpenRouter 'judge' returned HTTP 429`. Root cause: `openrouter_role_transport.py` retried ONLY `httpx.TransportError`; a non-200 status (incl 429 rate-limit) raised immediately with no retry. The judge makes one call per claim (~178 for drb_72) → a burst trips OpenRouter's rate limit.

## The change (RESILIENCE ONLY — must be FAIL-CLOSED)
Add bounded exponential-backoff retry on retryable HTTP statuses (default 429, 503) honoring `Retry-After`, env-driven (PG_ROLE_HTTP_RETRY_MAX / _STATUS / _BACKOFF_BASE_SECONDS / _CAP_SECONDS), before the existing non-200 raise. Unit test (8 cases) passes: 429-then-200 → succeeds; always-429 → RoleTransportError after bounded retries (fail-closed).

## VERIFY (be adversarial — this is the FAITHFULNESS-CRITICAL 4-role transport)
1. FAIL-CLOSED preserved: after retries are exhausted (or a non-retryable non-200), the call STILL raises `RoleTransportError` → release HELD. A 429 can NEVER produce a fake/empty/silent verdict or a silent release. Confirm no path swallows the error or returns a default verdict.
2. The verdict-parsing, blank-verdict recovery, budget-cap accounting, and provider-exclusion logic are UNCHANGED (only the HTTP-status retry was added).
3. Backoff is BOUNDED (cannot hang forever) and env-driven (LAW VI, named constants, no magic numbers). Retry-After parsing is safe on a missing/non-numeric header.
4. No new faithfulness weakening anywhere; the 4-role gate's authority is intact.
5. The test genuinely exercises both the success-after-retry and the fail-closed-after-exhaustion paths (not a tautology).

----- BEGIN UNIFIED DIFF UNDER REVIEW -----

diff --git a/src/polaris_graph/roles/openrouter_role_transport.py b/src/polaris_graph/roles/openrouter_role_transport.py
index 25732d4c..ba456cdd 100644
--- a/src/polaris_graph/roles/openrouter_role_transport.py
+++ b/src/polaris_graph/roles/openrouter_role_transport.py
@@ -91,6 +91,7 @@ from __future__ import annotations
 import json
 import logging
 import os
+import time
 
 import httpx
 
@@ -390,6 +391,36 @@ def role_reasoning_enabled(role: str, slug_override: str | None = None) -> bool:
 # cheap 90s shared default (which also governs retrieval/embeddings). Env-overridable (LAW VI).
 _TIMEOUT_SECONDS = int(os.getenv("PG_VERIFIER_LLM_TIMEOUT_SECONDS", "900"))
 
+# I-beatboth-429 (#1173): a per-claim judge burst (~178 calls for drb_72) trips OpenRouter's
+# rate limit on the qwen judge — a 429 (or a transient 503) on a SINGLE role call must NOT hold
+# the 4-role release. Bounded exponential backoff-retry on the retryable HTTP statuses, honoring
+# the `Retry-After` response header, is RESILIENCE ONLY: exhausted retries STILL raise
+# RoleTransportError below -> release HELD (fail-closed; the gate is never weakened). LAW VI:
+# every knob is env-driven (named, no magic numbers), read LAZILY per-call (mirrors the adjacent
+# PG_ROLE_TRANSPORT_RETRIES pattern so an override set after import is honored).
+_ROLE_HTTP_RETRY_MAX_DEFAULT = "5"
+_ROLE_HTTP_RETRY_STATUS_DEFAULT = "429,503"
+_ROLE_HTTP_BACKOFF_BASE_SECONDS_DEFAULT = "2.0"
+_ROLE_HTTP_BACKOFF_CAP_SECONDS_DEFAULT = "60.0"
+
+
+def _parse_retry_after_seconds(value: str | None) -> float | None:
+    """Parse the `Retry-After` header as integer seconds (RFC 9110 delta-seconds form).
+
+    Returns the non-negative float seconds on success, or `None` when the header is absent,
+    empty, or a non-numeric/HTTP-date form — in which case the caller falls back to the capped
+    exponential backoff. We deliberately do NOT parse the HTTP-date form (per the I-beatboth-429
+    spec): any non-integer value is treated as the absent case so a malformed header can never
+    yield a negative or unbounded sleep.
+    """
+    if value is None:
+        return None
+    try:
+        seconds = int(value.strip())
+    except (ValueError, AttributeError):
+        return None
+    return float(seconds) if seconds >= 0 else None
+
 # LAW VI: base URL + key come from the SAME env vars openrouter_client reads (single source of
 # truth). Read lazily (function-level) so import never depends on env presence.
 _BASE_URL_ENV = "OPENROUTER_BASE_URL"
@@ -762,33 +793,89 @@ class OpenRouterRoleTransport:
                 # failure. Retry the POST a bounded number of times (env-driven, LAW VI) before
                 # fail-loud. HTTP-STATUS errors are handled separately below (not retried here).
                 transport_retries = max(0, int(os.getenv("PG_ROLE_TRANSPORT_RETRIES", "2")))
+                # I-beatboth-429 (#1173): rate-limit retry budget is SEPARATE from the
+                # transport-fault budget above (a 429 is not a connection reset). Read lazily so a
+                # monkeypatched env override is honored. The retryable-status set defaults to the
+                # rate-limit (429) + the transient-unavailable (503) statuses.
+                rate_limit_max = max(
+                    0,
+                    int(os.getenv("PG_ROLE_HTTP_RETRY_MAX", _ROLE_HTTP_RETRY_MAX_DEFAULT)),
+                )
+                retryable_statuses = {
+                    int(s)
+                    for s in os.getenv(
+                        "PG_ROLE_HTTP_RETRY_STATUS", _ROLE_HTTP_RETRY_STATUS_DEFAULT
+                    ).split(",")
+                    if s.strip()
+                }
+                backoff_base = float(
+                    os.getenv(
+                        "PG_ROLE_HTTP_BACKOFF_BASE_SECONDS",
+                        _ROLE_HTTP_BACKOFF_BASE_SECONDS_DEFAULT,
+                    )
+                )
+                backoff_cap = float(
+                    os.getenv(
+                        "PG_ROLE_HTTP_BACKOFF_CAP_SECONDS",
+                        _ROLE_HTTP_BACKOFF_CAP_SECONDS_DEFAULT,
+                    )
+                )
+
                 http_response = None
-                for transport_attempt in range(transport_retries + 1):
-                    try:
-                        http_response = self._http_client.post(
-                            url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS
-                        )
-                        break
-                    except httpx.TransportError as exc:
-                        # Codex diff-gate P2: retry ONLY transport-layer faults (connection reset /
-                        # WinError 10054, read/connect timeout, remote-protocol error — all
-                        # httpx.TransportError subclasses). A non-transport httpx error (e.g. an
-                        # HTTPStatusError from a future event hook) is NOT a transient blip and falls
-                        # through to the broad fail-loud handler below instead of being retried.
-                        if transport_attempt < transport_retries:
-                            logger.warning(
-                                "[polaris graph] #1053: %s transport error (attempt %d/%d) at %s: "
-                                "%s — retrying.",
-                                request.role, transport_attempt + 1, transport_retries + 1, url, exc,
+                rate_limit_attempt = 0
+                while True:
+                    http_response = None
+                    for transport_attempt in range(transport_retries + 1):
+                        try:
+                            http_response = self._http_client.post(
+                                url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS
                             )
-                            continue
-                        raise RoleTransportError(
-                            f"OpenRouter {request.role!r} transport error at {url}: {exc}"
-                        ) from exc
-                    except httpx.HTTPError as exc:
-                        raise RoleTransportError(
-                            f"OpenRouter {request.role!r} transport error at {url}: {exc}"
-                        ) from exc
+                            break
+                        except httpx.TransportError as exc:
+                            # Codex diff-gate P2: retry ONLY transport-layer faults (connection reset /
+                            # WinError 10054, read/connect timeout, remote-protocol error — all
+                            # httpx.TransportError subclasses). A non-transport httpx error (e.g. an
+                            # HTTPStatusError from a future event hook) is NOT a transient blip and falls
+                            # through to the broad fail-loud handler below instead of being retried.
+                            if transport_attempt < transport_retries:
+                                logger.warning(
+                                    "[polaris graph] #1053: %s transport error (attempt %d/%d) at %s: "
+                                    "%s — retrying.",
+                                    request.role, transport_attempt + 1, transport_retries + 1, url, exc,
+                                )
+                                continue
+                            raise RoleTransportError(
+                                f"OpenRouter {request.role!r} transport error at {url}: {exc}"
+                            ) from exc
+                        except httpx.HTTPError as exc:
+                            raise RoleTransportError(
+                                f"OpenRouter {request.role!r} transport error at {url}: {exc}"
+                            ) from exc
+
+                    # I-beatboth-429 (#1173): bounded exponential backoff on a RETRYABLE HTTP status
+                    # (429 / 503), honoring `Retry-After`. RESILIENCE ONLY — when the budget is
+                    # exhausted (or the status is NOT retryable) we fall through to the UNCHANGED
+                    # non-200 raise below, which still fires -> release Hwarning: in the working copy of 'tests/polaris_graph/roles/test_role_transport_http_429_retry.py', LF will be replaced by CRLF the next time Git touches it
ELD (fail-closed; the 4-role
+                    # gate is never weakened, no fake verdict is ever returned).
+                    if (
+                        http_response.status_code in retryable_statuses
+                        and rate_limit_attempt < rate_limit_max
+                    ):
+                        delay = _parse_retry_after_seconds(
+                            http_response.headers.get("Retry-After")
+                        )
+                        if delay is None:
+                            delay = min(backoff_cap, backoff_base * (2 ** rate_limit_attempt))
+                        logger.warning(
+                            "[polaris graph] #1173: role %s HTTP %d rate-limited, backing off %.1fs "
+                            "(retry %d/%d) at %s",
+                            request.role, http_response.status_code, delay,
+                            rate_limit_attempt + 1, rate_limit_max, url,
+                        )
+                        time.sleep(delay)
+                        rate_limit_attempt += 1
+                        continue
+                    break
 
                 if http_response.status_code != httpx.codes.OK:
                     raise RoleTransportError(
diff --git a/tests/polaris_graph/roles/test_role_transport_http_429_retry.py b/tests/polaris_graph/roles/test_role_transport_http_429_retry.py
new file mode 100644
index 00000000..7976d7a6
--- /dev/null
+++ b/tests/polaris_graph/roles/test_role_transport_http_429_retry.py
@@ -0,0 +1,205 @@
+"""Tests for the I-beatboth-429 (#1173) HTTP rate-limit backoff-retry on the benchmark-stage
+OpenRouter verifier RoleTransport.
+
+WHY (#1173): the 4-role seam makes one judge call per claim (~178 for drb_72) — a burst that
+trips OpenRouter's rate limit on the qwen judge. Before this fix the per-call retry loop retried
+ONLY `httpx.TransportError` (connection-level), and ANY non-200 status (incl 429) raised
+`RoleTransportError` immediately -> release HELD on a TRANSIENT 429. That systematically held
+beat-both-worthy reports (drb_72 + drb_75, 2/2).
+
+CONTRACT (RESILIENCE ONLY, FAIL-CLOSED — never weakens the gate):
+  (a) a 429-then-200 sequence SUCCEEDS — the role POST is retried after a bounded backoff and the
+      second (200) response's verdict is returned (assert the underlying POST ran >= 2x);
+  (b) an ALWAYS-429 sequence STILL raises `RoleTransportError` after the bounded retries are
+      exhausted (fail-closed — the existing non-200 raise fires -> release HELD, never a fake
+      verdict, never a silent fallback);
+  (c) the `Retry-After` integer-seconds header is honored as the backoff delay when present;
+  (d) the rate-limit retry budget (PG_ROLE_HTTP_RETRY_MAX) is SEPARATE from the transport-fault
+      budget (PG_ROLE_TRANSPORT_RETRIES) — a 429 is not a connection reset.
+
+SPEND-FREE / NO NETWORK: every test injects an `httpx.Client(transport=httpx.MockTransport(...))`
+(same pattern as tests/roles/test_openrouter_role_transport_meta007.py), so there is NO socket /
+NO real LLM / NO spend in any path pytest exercises. `time.sleep` is monkeypatched to a no-op so
+the bounded backoff never actually blocks the test run.
+"""
+
+from __future__ import annotations
+
+import httpx
+import pytest
+
+import src.polaris_graph.roles.openrouter_role_transport as ort
+from src.polaris_graph.roles.openrouter_role_transport import (
+    OpenRouterRoleTransport,
+    _parse_retry_after_seconds,
+)
+from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
+from src.polaris_graph.roles.role_transport import RoleRequest
+
+# Benchmark-stage Judge slug (the effort-ladder reasoning role that takes the per-claim burst).
+_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"
+
+_GOOD_PAYLOAD = {
+    "model": _JUDGE_SLUG,
+    "provider": "DeepInfra",
+    "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
+    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
+}
+
+
+@pytest.fixture(autouse=True)
+def _transport_env(monkeypatch):
+    """Provide the OpenRouter key (LAW VI) and pin SMALL, deterministic rate-limit knobs so the
+    bounded-retry assertions are exact. Also no-op `time.sleep` so the backoff never blocks."""
+    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
+    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
+    # SMALL retry budget so the always-429 case raises quickly and the POST-count math is clean.
+    monkeypatch.setenv("PG_ROLE_HTTP_RETRY_MAX", "2")
+    monkeypatch.setenv("PG_ROLE_HTTP_RETRY_STATUS", "429,503")
+    # Tiny backoff (defense-in-depth; sleep is also no-op'd below).
+    monkeypatch.setenv("PG_ROLE_HTTP_BACKOFF_BASE_SECONDS", "0.01")
+    monkeypatch.setenv("PG_ROLE_HTTP_BACKOFF_CAP_SECONDS", "0.05")
+    # The Judge is the effort-ladder role; keep its blank-retry behavior out of these tests by
+    # only ever returning NON-blank content. No reasoning-effort override needed.
+    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
+    monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)
+    # NO real sleeping — record the delays so the backoff path can be asserted.
+    slept: list[float] = []
+    monkeypatch.setattr(ort.time, "sleep", lambda s: slept.append(s))
+    return slept
+
+
+def _make_transport(handler) -> OpenRouterRoleTransport:
+    """Build the OpenRouter transport with an INJECTED MockTransport client (no network)."""
+    client = httpx.Client(transport=httpx.MockTransport(handler))
+    return OpenRouterRoleTransport(client)
+
+
+def _sequenced_handler(statuses):
+    """A MockTransport handler returning a canned response per call from `statuses`.
+
+    Each entry is either an int status (429/503 -> empty-body rate-limited; 200 -> the good
+    verdict payload) or a `(status, headers)` tuple. After the list is exhausted the LAST entry
+    repeats (so an always-429 list of length 1 stays 429 forever). Records every call.
+    """
+    seen = {"n": 0, "statuses": []}
+
+    def handler(request: httpx.Request) -> httpx.Response:
+        idx = min(seen["n"], len(statuses) - 1)
+        entry = statuses[idx]
+        seen["n"] += 1
+        if isinstance(entry, tuple):
+            status, hdrs = entry
+        else:
+            status, hdrs = entry, {}
+        seen["statuses"].append(status)
+        if status == 200:
+            return httpx.Response(200, json=_GOOD_PAYLOAD)
+        # A rate-limited / unavailable response is NEVER JSON-parsed (we retry before the parse),
+        # so an empty body is realistic and safe.
+        return httpx.Response(status, headers=hdrs, json={})
+
+    return handler, seen
+
+
+# ----------------------------------------------------------------------------------------------
+# (a) 429 -> 200 : the role POST is retried after backoff and SUCCEEDS (retry worked).
+# ----------------------------------------------------------------------------------------------
+def test_http_429_then_200_recovers(_transport_env):
+    slept = _transport_env
+    handler, seen = _sequenced_handler([429, 200])
+    resp = _make_transport(handler).complete(
+        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+    )
+    assert resp.raw_text == "VERIFIED", "the 200 verdict after the 429 retry must be returned"
+    assert seen["n"] >= 2, "the 429 must have been retried (POST issued >= 2x)"
+    assert seen["statuses"][:2] == [429, 200]
+    assert len(slept) == 1, "exactly one backoff sleep before the successful retry"
+    assert slept[0] > 0.0, "the backoff delay must be a positive sleep"
+
+
+def test_http_503_then_200_recovers(_transport_env):
+    # 503 (transient unavailable) is in the default retryable set alongside 429.
+    handler, seen = _sequenced_handler([503, 200])
+    resp = _make_transport(handler).complete(
+        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+    )
+    assert resp.raw_text == "VERIFIED"
+    assert seen["n"] >= 2, "the 503 must have been retried"
+
+
+# ----------------------------------------------------------------------------------------------
+# (b) always-429 : FAIL-CLOSED — RoleTransportError is raised after the bounded retries (HELD).
+# ----------------------------------------------------------------------------------------------
+def test_http_429_always_fails_closed_after_bounded_retries(_transport_env):
+    handler, seen = _sequenced_handler([429])  # length-1 -> repeats 429 forever
+    with pytest.raises(RoleTransportError, match="HTTP 429"):
+        _make_transport(handler).complete(
+            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+        )
+    # PG_ROLE_HTTP_RETRY_MAX=2 -> 1 original POST + 2 bounded retries = 3 POSTs, then HELD.
+    assert seen["n"] == 3, "a persistent 429 must raise after exactly RETRY_MAX bounded retries"
+
+
+def test_http_503_always_fails_closed(_transport_env):
+    handler, seen = _sequenced_handler([503])
+    with pytest.raises(RoleTransportError, match="HTTP 503"):
+        _make_transport(handler).complete(
+            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+        )
+    assert seen["n"] == 3, "a persistent 503 fails closed after the bounded retries"
+
+
+# ----------------------------------------------------------------------------------------------
+# (c) a NON-retryable non-200 status is NOT retried — it fails loud IMMEDIATELY (fail-closed,
+#     no resilience widening to non-rate-limit errors).
+# ----------------------------------------------------------------------------------------------
+def test_non_retryable_status_raises_immediately(_transport_env):
+    # 400 is NOT in the retryable set -> the existing non-200 raise fires on the first response.
+    handler, seen = _sequenced_handler([400, 200])
+    with pytest.raises(RoleTransportError, match="HTTP 400"):
+        _make_transport(handler).complete(
+            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+        )
+    assert seen["n"] == 1, "a non-retryable status must NOT be retried"
+
+
+# ----------------------------------------------------------------------------------------------
+# (d) the `Retry-After` integer-seconds header is honored as the backoff delay.
+# ----------------------------------------------------------------------------------------------
+def test_retry_after_header_is_honored(_transport_env):
+    slept = _transport_env
+    handler, _seen = _sequenced_handler([(429, {"Retry-After": "7"}), 200])
+    resp = _make_transport(handler).complete(
+        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+    )
+    assert resp.raw_text == "VERIFIED"
+    assert slept == [7.0], "an integer Retry-After must override the exponential backoff"
+
+
+def test_retry_after_parse_helper():
+    # Integer seconds -> float; absent / empty / non-numeric / HTTP-date / negative -> None
+    # (the caller then falls back to the capped exponential backoff).
+    assert _parse_retry_after_seconds("0") == 0.0
+    assert _parse_retry_after_seconds("30") == 30.0
+    assert _parse_retry_after_seconds("  5 ") == 5.0
+    assert _parse_retry_after_seconds(None) is None
+    assert _parse_retry_after_seconds("") is None
+    assert _parse_retry_after_seconds("not-a-number") is None
+    assert _parse_retry_after_seconds("Wed, 21 Oct 2025 07:28:00 GMT") is None
+    assert _parse_retry_after_seconds("-3") is None
+
+
+# ----------------------------------------------------------------------------------------------
+# the rate-limit retry budget is SEPARATE from the transport-fault retry budget.
+# ----------------------------------------------------------------------------------------------
+def test_rate_limit_budget_separate_from_transport_budget(_transport_env, monkeypatch):
+    # PG_ROLE_TRANSPORT_RETRIES=0 (zero transport-fault retries) must NOT shrink the rate-limit
+    # budget — a 429 still gets PG_ROLE_HTTP_RETRY_MAX (=2) retries.
+    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "0")
+    handler, seen = _sequenced_handler([429, 429, 200])
+    resp = _make_transport(handler).complete(
+        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
+    )
+    assert resp.raw_text == "VERIFIED"
+    assert seen["n"] == 3, "two 429s retried under the SEPARATE rate-limit budget, then 200"
