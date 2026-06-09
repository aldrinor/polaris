HARD ITERATION CAP 5, iter 3 of 5. APPROVE iff zero NOVEL/continuing P0 and zero P1; final 'verdict:' line + §8.3.9 schema.

ITER-3 CHANGELOG: closed your iter-2 pre-loop-abandonment P1 — a per-worker abandoned threading.Event is set on outer-join timeout; the worker checks it AFTER acquiring the inflight semaphore + BEFORE starting AccessBypass, releasing the semaphore and returning without a stale fetch/browser spawn. Combined with the existing post-loop cancel teardown, both abandonment windows release resources.

VERIFY:
(1) pre-loop abandonment no longer starts a stale bypass fetch;
(2) semaphore not leaked;
(3) non-hang preserved;
(4) faithfulness untouched;
(5) the new test genuinely exercises the blocked-on-semaphore abandonment (not tautological).

Output schema (machine-parseable, last line must be the verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Front-load ALL real findings in iter 1-now. No drip-feeding. Same quality bar regardless of iteration. Don't pick bone from egg — reserve P0/P1 for real execution risks; classify cosmetic as P3/P2. The diff for the two files (src/polaris_graph/retrieval/live_retriever.py and the new tests/polaris_graph/test_lane_a_fetch_stability_bb5.py) follows.

--- DIFF BELOW ---

diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 9e9867e7..8e3cc297 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -113,6 +113,18 @@ _FETCH_SUCCESS_RATE_WARN_FLOOR = float(
     os.getenv("PG_LIVE_FETCH_SUCCESS_RATE_WARN_FLOOR", "0.5")
 )
 
+# BB5-C05 (#1177): "fetched-200-but-empty-extract" thresholds. A fetch counts
+# as this DISTINCT bucket when the backend returned a non-trivial raw body
+# (>= _EXTRACT_NONEMPTY_RAW_FLOOR chars) yet the extractor chain (trafilatura →
+# readability → regex) yielded fewer than _EXTRACT_EMPTY_FLOOR usable chars.
+# Named constants (LAW VI — no magic numbers); env-overridable.
+_EXTRACT_NONEMPTY_RAW_FLOOR = int(
+    os.getenv("PG_FETCH_NONEMPTY_RAW_FLOOR", "200")
+)
+_EXTRACT_EMPTY_FLOOR = int(
+    os.getenv("PG_FETCH_EMPTY_EXTRACT_FLOOR", "50")
+)
+
 
 @dataclass
 class LiveRetrievalResult:
@@ -1338,18 +1350,76 @@ def _extract_jsonld_blocks(raw_html: str) -> str:
         return ""
 
 
+def _readability_extract(html: str) -> str:
+    """BB5-C05 (#1177): readability-lxml fallback extractor. trafilatura returns
+    empty trees on 30-50% of fetched pages; readability's article-detection
+    recovers many of them. Guarded import (skip-with-log when the optional dep
+    is absent — never break `_strip_html`). Returns extracted plain text or ""."""
+    if not html:
+        return ""
+    try:
+        from readability import Document  # type: ignore
+    except ImportError:
+        logger.debug(
+            "[live_retriever] BB5-C05 readability-lxml not installed — "
+            "skipping fallback extractor"
+        )
+        return ""
+    try:
+        summary_html = Document(html).summary(html_partial=True)
+    except Exception as exc:  # noqa: BLE001 — readability runs lxml; a parse
+        # error must never break the strip path. (A C-level SIGSEGV would still
+        # escape, but readability only runs AFTER trafilatura already declined,
+        # and on the SAME doc that passed the trafilatura size gate.)
+        logger.debug(
+            "[live_retriever] BB5-C05 readability extract error (%s)",
+            type(exc).__name__,
+        )
+        return ""
+    # readability returns cleaned HTML — strip residual tags to plain text.
+    no_tags = re.sub(r"<[^>]+>", " ", summary_html or "")
+    no_tags = re.sub(r"\s+", " ", no_tags)
+    return no_tags.strip()
+
+
 def _strip_html(html: str) -> str:
-    """Extract visible text from HTML via basic regex (trafilatura if available), then APPEND table-aware
-    linearized rows (#954) so result-table cells survive with their column headers regardless of how the
-    base extractor flattened the tables. Default-ON; PG_FETCH_TABLE_LINEARIZE=0 disables the append."""
+    """Extract visible text from HTML via trafilatura (BB5-S03 SIGSEGV-guarded),
+    then a readability-lxml fallback (BB5-C05), then a regex fallback, then APPEND
+    table-aware linearized rows (#954) so result-table cells survive with their
+    column headers regardless of how the base extractor flattened the tables.
+    Default-ON; PG_FETCH_TABLE_LINEARIZE=0 disables the append."""
     base = ""
+    # BB5-S03 (#1177): route trafilatura through the SIGSEGV-mitigated shared
+    # guard (size-bounds the HTML; optional subprocess containment) instead of a
+    # bare `trafilatura.extract` under `except Exception: pass` — a libxml2
+    # C-crash on a pathological doc is NOT a catchable Python exception.
     try:
-        import trafilatura  # type: ignore
-        extracted = trafilatura.extract(html) or ""
+        from src.tools.access_bypass import safe_trafilatura_extract
+        extracted = safe_trafilatura_extract(html) or ""
         if extracted:
             base = extracted
-    except Exception:
+    except Exception:  # noqa: BLE001 — import/guard failure must never break strip
         pass
+    if not base:
+        # BB5-C05 (#1177): trafilatura returned an empty tree — try the
+        # readability-lxml article extractor before the last-resort regex strip.
+        #
+        # BB5-S03 iter-2 (#1177, Codex P1-S03): readability-lxml ALSO parses via
+        # lxml/libxml2 — the SAME C-crash surface trafilatura was size-gated away
+        # from. An oversized/suspect doc that skipped trafilatura must therefore
+        # ALSO skip readability and go straight to the regex strip, or it just
+        # re-enters libxml2 by another door (same SIGSEGV risk). Gate on the
+        # SHARED size predicate. Import the FUNCTION (not the constant value) so
+        # the deploy-slate PG_TRAFILATURA_MAX_HTML_CHARS override + test monkey-
+        # patch are read at call time, keeping ONE source of truth for the bound.
+        _extract_safe = True
+        try:
+            from src.tools.access_bypass import _html_is_extract_safe
+            _extract_safe = _html_is_extract_safe(html)
+        except Exception:  # noqa: BLE001 — import/guard failure must never break strip
+            _extract_safe = True
+        if _extract_safe:
+            base = _readability_extract(html)
     if not base:
         # Fallback: strip tags + collapse whitespace
         no_tags = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
@@ -1405,6 +1475,34 @@ def _fetch_content_httpx_naive(
         # Diff-gate P1-C: capture raw ld+json BEFORE _strip_html removes <script>.
         jsonld = _extract_jsonld_blocks(raw)
         content = _strip_html(raw)[:max_chars]
+        # BB5-C05 iter-2 (#1177, Codex P2): mirror the parallel/AccessBypass
+        # path's "fetched-200-but-empty-extract" bucket on the NAIVE/DIRECT path
+        # too. A real 200 body (>= _EXTRACT_NONEMPTY_RAW_FLOOR raw chars) whose
+        # extractor chain (trafilatura → readability → regex) collapses below
+        # _EXTRACT_EMPTY_FLOOR usable chars is the SAME distinct failure class
+        # here as there — previously this naive path swallowed it silently as a
+        # generic empty fetch. Surface it as its own auditable telemetry bucket.
+        # Telemetry-only: the returned tuple is unchanged (control flow is byte-
+        # identical). Reuses the existing floors — no new constants.
+        if len(raw) >= _EXTRACT_NONEMPTY_RAW_FLOOR and len(content) < _EXTRACT_EMPTY_FLOOR:
+            logger.info(
+                "[live_retriever] fetched_200_but_empty_extract %s "
+                "(method=httpx_naive raw_chars=%d extracted_chars=%d)",
+                url[:80], len(raw), len(content),
+            )
+            # BB5-C05 iter-2 (#1177, Codex P2 reconcile): record ONLY the keyed
+            # _m45 reason here — NOT a second _trace_tool. The production naive
+            # path is reached via `_fallback_naive_fetch`, which already emits the
+            # SINGLE per-fetch `_trace_tool` (ok/fail) for this call; adding an
+            # `empty_extract` _trace_tool too would double-record one fetch into
+            # two contradictory buckets (empty_extract AND fail), whereas the
+            # parallel path emits exactly one. The _m45 reason is keyed by URL +
+            # last-write-wins, so it carries the distinct empty-extract signal
+            # without duplicating the trace. (Direct callers of this function —
+            # e.g. the M-45 diagnostics refetch — still get the _m45 reason.)
+            _m45_record_fetch_telemetry(
+                url, "httpx_naive", "fetched_200_but_empty_extract",
+            )
         return content, bool(content), extracted_title, body_type, jsonld
     except Exception as exc:
         logger.debug(
@@ -1915,16 +2013,91 @@ def _fetch_content(
     # async context (expansion path runs inside a live loop). Crawl4AI
     # leaves background tasks that make subsequent asyncio.run() in the
     # same thread fail with "cannot be called from a running event loop".
+    #
+    # BB5-S02 (#1177): import the cross-thread in-flight bound + leak gauge +
+    # the wedged-task-draining runner. The bound is acquired INSIDE the worker
+    # (so an abandoned worker holds its slot until it truly terminates) and
+    # released in the worker's OWN finally — never in the outer join path
+    # (releasing on abandonment over-releases; not releasing leaks the slot).
+    from src.tools.access_bypass import (
+        _get_bypass_inflight_semaphore,
+        polaris_asyncio_run,
+        record_bypass_leaked_worker,
+    )
     result_holder: dict[str, Any] = {}
+    _inflight_sem = _get_bypass_inflight_semaphore()
+    # BB5-S02 iter-3 (#1177, Codex P1 continuing): a per-worker ABANDONED flag.
+    # The outer join-timeout path SETS it; the worker CHECKS it twice — (a)
+    # immediately after acquiring the in-flight slot (closes the
+    # blocked-on-semaphore window: a worker that timed out while STILL queued on
+    # `_inflight_sem.acquire()` must NOT proceed to run AccessBypass / spawn a
+    # browser once the slot finally frees) and (b) right after publishing its
+    # loop (closes the narrow TOCTOU between passing check (a) and the outer path
+    # reading a not-yet-published loop). Under the GIL the handshake is closed:
+    # worker = publish-loop-then-check-flag; outer = set-flag-then-read-loop.
+    _abandoned = threading.Event()
 
     def _bypass_worker() -> None:
+        # BB5-S02: acquire a cross-thread in-flight slot. Bounds the number of
+        # concurrently-LIVE bypass workers (each may hold a browser subprocess)
+        # across all per-thread event loops — `_get_crawl4ai_semaphore` cannot,
+        # being lazy-bound to THIS thread's fresh loop only.
+        _inflight_sem.acquire()
         try:
+            # BB5-S02 iter-3 (#1177, Codex P1 continuing): if this worker was
+            # abandoned (outer join timed out) WHILE it was blocked here on
+            # `acquire()`, bail BEFORE constructing AccessBypass / publishing a
+            # loop / spawning a browser. The outer path could not cancel us (no
+            # loop was ever published), so the worker itself must self-abort —
+            # otherwise a stale fetch starts AFTER its caller already fell back,
+            # consuming a slot + browser resources. `return` here lets the
+            # existing `finally` perform the single in-flight-slot release (do
+            # NOT release explicitly — a BoundedSemaphore double-release raises).
+            if _abandoned.is_set():
+                return
             bypass = AccessBypass()
-            result_holder["value"] = asyncio.run(
-                bypass.fetch_with_bypass(url, prefer_legal=True)
+
+            async def _capture_loop_and_fetch() -> Any:
+                # BB5-S02 iter-2 (#1177, Codex P1-S02): publish THIS worker's
+                # running loop into the shared holder as the FIRST awaited step,
+                # BEFORE the (potentially wedging) fetch. The outer join path
+                # reads this loop to actively signal teardown on abandonment.
+                # Capturing here — inside the coro rather than by changing
+                # polaris_asyncio_run — keeps the drain-runner's signature (and
+                # its spy test) untouched.
+                result_holder["loop"] = asyncio.get_running_loop()
+                # BB5-S02 iter-3 (#1177): second abandonment check, AFTER the
+                # loop is published. Closes the TOCTOU where the worker passed
+                # the post-acquire check, then the outer path timed out and read
+                # `loop` as None (not yet published) → no teardown was sent.
+                # Raising CancelledError (vs returning) matches the worker's
+                # existing `except asyncio.CancelledError` handler and skips the
+                # fetch entirely, so no stale browser op starts.
+                if _abandoned.is_set():
+                    raise asyncio.CancelledError(
+                        "bypass worker abandoned before fetch start"
+                    )
+                return await bypass.fetch_with_bypass(url, prefer_legal=True)
+
+            # BB5-S02: polaris_asyncio_run (vs bare asyncio.run) force-drains
+            # wedged detached Playwright fetch tasks BEFORE the loop's
+            # cancel-all phase, so the loop teardown cannot hang on an
+            # un-cancellable browser op — closing the orphan-subprocess window
+            # for a worker that DOES eventually return.
+            result_holder["value"] = polaris_asyncio_run(_capture_loop_and_fetch())
+        except asyncio.CancelledError:
+            # BB5-S02 iter-2: the outer join path actively cancelled this loop's
+            # tasks on abandonment (active teardown). CancelledError is a
+            # BaseException — NOT caught by `except Exception` — so catch it
+            # explicitly here, or it escapes the daemon thread as a noisy
+            # traceback. The slot still releases in the finally below.
+            result_holder["error"] = result_holder.get("error") or RuntimeError(
+                "bypass worker cancelled on abandonment teardown"
             )
         except Exception as exc:  # noqa: BLE001
             result_holder["error"] = exc
+        finally:
+            _inflight_sem.release()
 
     worker = threading.Thread(target=_bypass_worker, daemon=True)
     worker.start()
@@ -1940,11 +2113,64 @@ def _fetch_content(
         deadline = 90.0
     worker.join(timeout=deadline if deadline > 0 else None)
     if worker.is_alive():
+        # BB5-S02 iter-3 (#1177, Codex P1 continuing): SET the abandoned flag
+        # FIRST — before the gauge/log/loop-read — so a worker about to wake
+        # from a blocked `_inflight_sem.acquire()` (or about to publish its
+        # loop) observes the abandonment ASAP and self-aborts WITHOUT starting
+        # AccessBypass. This closes the pre-loop window the active loop-cancel
+        # teardown below cannot reach (that teardown needs a published loop;
+        # a still-queued worker has none). The two mechanisms compose: this
+        # flag covers the never-started (pre-loop) case; the loop cancel below
+        # covers the in-flight (post-loop) case.
+        _abandoned.set()
+        # BB5-S02 (#1177): the worker is ABANDONED (still alive past the join
+        # deadline) — it holds its in-flight slot + possibly a live browser
+        # subprocess until it finally terminates. Record the leak gauge so the
+        # accumulated-orphan-subprocess signal is auditable (was silent before).
+        _leaked = record_bypass_leaked_worker()
         logger.warning(
             "[live_retriever] AccessBypass timed out after %.0fs for %s "
-            "— falling back to naive httpx (thread will continue as daemon)",
-            deadline, url[:80],
+            "— falling back to naive httpx (thread abandoned as daemon; "
+            "leaked_bypass_workers=%d)",
+            deadline, url[:80], _leaked,
         )
+        # BB5-S02 iter-2 (#1177, Codex P1-S02): the previous code only RECORDED
+        # the abandonment (gauge) — it never FORCED the wedged worker to release
+        # its browser. Here we ACTIVELY signal teardown: cancel every task on the
+        # abandoned worker's event loop. The fetch coro was created via
+        # `loop.create_task` inside polaris_asyncio_run, so cancelling it injects
+        # CancelledError at the wedged `await`, which runs _try_crawl4ai's
+        # `finally: await _safe_close_crawler(...)` — closing the Crawl4AI/
+        # Playwright browser context instead of orphaning it. `call_soon_thread-
+        # safe` is the ONLY thread-safe way to touch another loop; `all_tasks`
+        # then runs IN that loop thread where it is safe. Fire-and-forget — we do
+        # NOT join the worker, preserving the non-hang property of this fallback.
+        #
+        # Honest limitation (mirrors the trafilatura SIGSEGV mitigation note): a
+        # worker wedged in a synchronous C-level Playwright call observes the
+        # cancellation only when it next yields to its loop. This is inherent to
+        # cooperative cancellation and cannot be engineered past in-process; the
+        # signal is still sent so a cancellable wait tears down promptly.
+        _abandoned_loop = result_holder.get("loop")
+        if _abandoned_loop is not None:
+            try:
+                if not _abandoned_loop.is_closed():
+                    def _cancel_all_on_abandoned_loop(
+                        _loop: Any = _abandoned_loop,
+                    ) -> None:
+                        try:
+                            for _task in asyncio.all_tasks(_loop):
+                                _task.cancel()
+                        except Exception:  # noqa: BLE001 — best-effort teardown
+                            pass
+
+                    _abandoned_loop.call_soon_threadsafe(
+                        _cancel_all_on_abandoned_loop
+                    )
+            except RuntimeError:
+                # Loop closed/finished racing with the cancel request — the
+                # worker already returned on its own; nothing to tear down.
+                pass
         # M-45 pass-2: record AccessBypass timeout so diagnostics can
         # distinguish timeout from backend refusal.
         _m45_record_fetch_telemetry(
@@ -2054,6 +2280,30 @@ def _fetch_content(
     # cleaned text). _strip_html is a safety net for direct-HTTP path
     # which returns raw HTML.
     content = _strip_html(result.content)[:max_chars]
+    # BB5-C05 (#1177): "fetched-200-but-empty-extract" — the backend fetched
+    # real content (success + non-empty result.content) yet the extractor chain
+    # (trafilatura → readability → regex) collapsed it below the usable floor.
+    # This is a DISTINCT failure class from a network miss / paywall stub, and
+    # was previously swallowed silently (counted as a generic miss). Surface it
+    # as its own telemetry bucket so it is auditable, not silent.
+    _raw_len = len(result.content or "")
+    if _raw_len >= _EXTRACT_NONEMPTY_RAW_FLOOR and len(content) < _EXTRACT_EMPTY_FLOOR:
+        logger.info(
+            "[live_retriever] fetched_200_but_empty_extract %s "
+            "(method=%s raw_chars=%d extracted_chars=%d)",
+            url[:80], method, _raw_len, len(content),
+        )
+        _m45_record_fetch_telemetry(
+            url, method, "fetched_200_but_empty_extract",
+        )
+        _trace_tool(
+            "fetch_content", target=url, status="empty_extract",
+            latency_ms=(time.time() - _t0) * 1000.0,
+            backend_used=method, bytes_received=len(content),
+            content_length=len(content),
+            error="fetched_200_but_empty_extract",
+        )
+        return content, bool(content), extracted_title, body_type, jsonld
     logger.info(
         "[live_retriever] fetch_ok %s (method=%s chars=%d)",
         url[:80], method, len(content),
@@ -2898,6 +3148,16 @@ def run_live_retrieval(
         api_calls["parallel_fetch_timeout_count"] = (
             parallel_report.timeout_count
         )
+        # BB5-S02 (#1177): surface the leaked-bypass-worker gauge (abandoned
+        # in-flight workers that may hold orphan browser subprocesses) into the
+        # manifest so the resource-leak signal is auditable, not log-only.
+        try:
+            from src.tools.access_bypass import bypass_leaked_worker_count
+            api_calls["bypass_leaked_worker_count"] = (
+                bypass_leaked_worker_count()
+            )
+        except Exception:  # noqa: BLE001 — telemetry only; never break fetch
+            pass
         logger.info(
             "[live_retriever] M-INT-1 parallel_fetch: %d success, "
             "%d errored, %d timeout (max_workers=%d, "
diff --git a/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py b/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py
new file mode 100644
index 00000000..d66688a8
--- /dev/null
+++ b/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py
@@ -0,0 +1,791 @@
+"""Lane A — fetch/stability fixes for beat-both run 5 (#1177).
+
+OFFLINE deterministic coverage (no network, no spend, no real browser) for:
+
+  - BB5-S02 — abandoned-bypass-worker teardown: a cross-THREAD BoundedSemaphore
+    bounds concurrently-LIVE bypass workers across their independent per-thread
+    event loops; the slot is released in the worker's OWN finally (never the
+    outer join path); an abandoned worker increments a leaked-worker gauge; the
+    bound never deadlocks the sweep; `_bypass_worker` runs under the
+    wedged-task-draining `polaris_asyncio_run`.
+
+  - BB5-S03 — SIGSEGV-mitigated trafilatura: the shared `safe_trafilatura_extract`
+    guard size-bounds the HTML (an oversized/suspect doc skips libxml2 and
+    returns None → caller's regex fallback), never raises, and the optional
+    subprocess path contains a SIGSEGV-class child crash (returns None).
+
+  - BB5-C05 — extractor fallback chain + distinct telemetry: `_strip_html` falls
+    back to readability-lxml when trafilatura returns an empty tree; a fetch that
+    returns a real 200 body but whose extractor chain collapses below the floor
+    is surfaced as the DISTINCT "fetched_200_but_empty_extract" telemetry bucket
+    (not a silent generic miss).
+
+All tests monkeypatch the network/extractor boundary; none hit the wire.
+"""
+
+from __future__ import annotations
+
+import threading
+import time
+from dataclasses import dataclass
+from typing import Any
+
+import pytest
+
+import src.tools.access_bypass as ab
+from src.polaris_graph.retrieval import live_retriever
+
+
+# ---------------------------------------------------------------------------
+# Fakes
+# ---------------------------------------------------------------------------
+
+
+@dataclass
+class _FakeAccessResult:
+    success: bool = True
+    content: str = "fake markdown content with real research words here"
+    access_method: str = "crawl4ai"
+    metadata: dict | None = None
+
+
+@pytest.fixture(autouse=True)
+def _reset_bypass_leak_state():
+    """Isolate the module-level S02 gauge + semaphore between tests."""
+    ab.reset_bypass_leak_state()
+    yield
+    ab.reset_bypass_leak_state()
+
+
+# ---------------------------------------------------------------------------
+# BB5-S02 — cross-thread in-flight bound + leak gauge
+# ---------------------------------------------------------------------------
+
+
+def test_inflight_semaphore_is_cross_thread_bounded_semaphore(monkeypatch):
+    """The in-flight bound is a threading.BoundedSemaphore (NOT asyncio) sized
+    from PG_BYPASS_MAX_INFLIGHT — it must bound worker THREADS across loops."""
+    monkeypatch.setenv("PG_BYPASS_MAX_INFLIGHT", "3")
+    ab.reset_bypass_leak_state()  # force re-read of the env knob
+    sem = ab._get_bypass_inflight_semaphore()
+    assert isinstance(sem, threading.BoundedSemaphore)
+    # Acquire up to the limit; the 4th non-blocking acquire must fail.
+    assert sem.acquire(blocking=False) is True
+    assert sem.acquire(blocking=False) is True
+    assert sem.acquire(blocking=False) is True
+    assert sem.acquire(blocking=False) is False
+    sem.release()
+    sem.release()
+    sem.release()
+
+
+def test_malformed_inflight_env_falls_back_to_default(monkeypatch):
+    """A bad PG_BYPASS_MAX_INFLIGHT must NOT disable the bound (would re-open
+    the abandoned-fleet leak) — it falls back to the named default."""
+    for bad in ("not-an-int", "0", "-5", ""):
+        monkeypatch.setenv("PG_BYPASS_MAX_INFLIGHT", bad)
+        ab.reset_bypass_leak_state()
+        sem = ab._get_bypass_inflight_semaphore()
+        # Default limit acquirable exactly _BYPASS_INFLIGHT_DEFAULT_LIMIT times.
+        got = 0
+        while sem.acquire(blocking=False):
+            got += 1
+            if got > ab._BYPASS_INFLIGHT_DEFAULT_LIMIT + 5:
+                break
+        assert got == ab._BYPASS_INFLIGHT_DEFAULT_LIMIT
+        for _ in range(got):
+            sem.release()
+
+
+def test_leaked_worker_gauge_increments_and_reads(monkeypatch):
+    """record_bypass_leaked_worker bumps the auditable orphan-subprocess gauge;
+    bypass_leaked_worker_count reads it; reset clears it."""
+    assert ab.bypass_leaked_worker_count() == 0
+    assert ab.record_bypass_leaked_worker() == 1
+    assert ab.record_bypass_leaked_worker() == 2
+    assert ab.bypass_leaked_worker_count() == 2
+    ab.reset_bypass_leak_state()
+    assert ab.bypass_leaked_worker_count() == 0
+
+
+def test_abandoned_worker_increments_leak_gauge(monkeypatch):
+    """A bypass worker that out-runs the join deadline is abandoned → the leak
+    gauge increments AND the call falls back to naive httpx (does not hang)."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    # Tiny join deadline so the slow worker is guaranteed to be abandoned.
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "0.3")
+
+    class _SlowBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            import asyncio
+            await asyncio.sleep(5.0)  # outlives the 0.3s join deadline
+            return _FakeAccessResult()
+
+    monkeypatch.setattr(ab, "AccessBypass", _SlowBypass)
+    # Make the naive fallback deterministic + offline.
+    monkeypatch.setattr(
+        live_retriever, "_fallback_naive_fetch",
+        lambda url, mc, t0, reason: ("", False, "", "", ""),
+    )
+
+    assert ab.bypass_leaked_worker_count() == 0
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/slow", max_chars=1000,
+    )
+    assert ok is False  # fell back to the (stubbed) naive path
+    assert ab.bypass_leaked_worker_count() == 1
+
+
+def test_abandoned_worker_actively_torn_down(monkeypatch):
+    """BB5-S02 iter-2 (Codex P1-S02): on outer-join timeout the abandoned
+    worker's loop tasks are ACTIVELY cancelled (not merely counted) — the
+    injected CancelledError reaches the wedged fetch's `finally`, which is where
+    the real cascade closes the Crawl4AI/Playwright browser. We prove the
+    teardown signal lands by asserting the fetch coro's `finally` runs."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "0.3")  # force abandonment
+
+    torn = threading.Event()
+
+    class _WedgedThenTornBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            import asyncio as _aio
+            try:
+                # Outlives the 0.3s join deadline -> abandoned. A cancellable
+                # await (stand-in for crawler.arun) so the teardown cancel is
+                # observed, mirroring _safe_close_crawler running in the real
+                # _try_crawl4ai `finally`.
+                await _aio.sleep(10.0)
+                return _FakeAccessResult()
+            finally:
+                # This is the real-pipeline browser-close site analogue: it runs
+                # ONLY because the abandonment path injected a cancellation.
+                torn.set()
+
+    monkeypatch.setattr(ab, "AccessBypass", _WedgedThenTornBypass)
+    monkeypatch.setattr(
+        live_retriever, "_fallback_naive_fetch",
+        lambda url, mc, t0, reason: ("", False, "", "", ""),
+    )
+
+    assert ab.bypass_leaked_worker_count() == 0
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/wedged", max_chars=1000,
+    )
+    # The call returned promptly via the naive fallback (no hang)...
+    assert ok is False
+    assert ab.bypass_leaked_worker_count() == 1
+    # ...and the abandoned worker's fetch coro was actively torn down: its
+    # `finally` (the browser-close site) ran because of the injected cancel.
+    assert torn.wait(timeout=5.0), (
+        "abandonment must ACTIVELY cancel the wedged worker's loop tasks so the "
+        "fetch `finally` (browser teardown) runs — not merely count the leak"
+    )
+
+
+def test_abandonment_with_no_captured_loop_does_not_crash(monkeypatch):
+    """BB5-S02 iter-2 guard: if the worker was abandoned before publishing its
+    loop (race), the teardown branch degrades to the iter-1 behavior (gauge +
+    naive fallback) without raising."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "0.2")
+
+    # polaris_asyncio_run that never publishes a loop and just blocks the worker
+    # past the deadline (simulating the pre-loop-capture race window).
+    def _blocking_runner(coro):
+        coro.close()  # avoid 'never awaited' warning; we don't run the coro
+        time.sleep(2.0)
+        return _FakeAccessResult()
+
+    monkeypatch.setattr(ab, "polaris_asyncio_run", _blocking_runner)
+
+    class _AnyBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            return _FakeAccessResult()
+
+    monkeypatch.setattr(ab, "AccessBypass", _AnyBypass)
+    monkeypatch.setattr(
+        live_retriever, "_fallback_naive_fetch",
+        lambda url, mc, t0, reason: ("", False, "", "", ""),
+    )
+
+    # Must not raise even though result_holder['loop'] was never set.
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/race", max_chars=1000,
+    )
+    assert ok is False
+    assert ab.bypass_leaked_worker_count() == 1
+
+
+def test_abandoned_while_blocked_on_slot_never_starts_fetch(monkeypatch):
+    """BB5-S02 iter-3 (#1177, Codex P1 continuing): a worker that times out
+    (outer join) WHILE STILL BLOCKED on `_inflight_sem.acquire()` — before any
+    loop is published — must NOT run AccessBypass once the slot finally frees.
+    Otherwise a stale fetch starts AFTER its caller already fell back, consuming
+    a bypass slot + browser resources.
+
+    Determinism: a HOLDER thread occupies the only slot (limit=1) so the worker
+    is guaranteed to block on acquire; the outer join (0.2s) times out and the
+    call falls back. We then release the holder and PROVE the abandoned worker
+    woke, checked the flag, and released WITHOUT fetching — by re-acquiring the
+    singleton semaphore (positive sync), then asserting the fetch fn was never
+    called and the slot is not leaked.
+    """
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "0.2")  # force abandonment
+    monkeypatch.setenv("PG_BYPASS_MAX_INFLIGHT", "1")  # single slot → contention
+    ab.reset_bypass_leak_state()  # force re-read of the limit-1 env knob
+
+    sem = ab._get_bypass_inflight_semaphore()
+    assert isinstance(sem, threading.BoundedSemaphore)
+
+    holder_acquired = threading.Event()
+    holder_release = threading.Event()
+
+    def _holder():
+        sem.acquire()  # occupy the only in-flight slot
+        holder_acquired.set()
+        holder_release.wait(timeout=10.0)
+        sem.release()
+
+    holder = threading.Thread(target=_holder, daemon=True)
+    holder.start()
+    assert holder_acquired.wait(timeout=5.0), "holder must take the only slot"
+
+    fetch_started = threading.Event()
+    # Discriminator for Codex's LITERAL wording ("CHECKS the abandoned flag —
+    # if set ... returns WITHOUT running the bypass fetch / no browser spawn",
+    # i.e. BEFORE starting AccessBypass). The browser/Playwright subprocess is
+    # spawned INSIDE fetch_with_bypass (AccessBypass.__init__ only builds regex
+    # lists), so "AccessBypass never CONSTRUCTED for the abandoned worker"
+    # proves the post-acquire check (#1) bailed before reaching `AccessBypass()`
+    # — not merely that the fetch coro was skipped further downstream.
+    constructed = {"n": 0}
+
+    class _NeverShouldRunBypass:
+        def __init__(self, *a, **k):
+            constructed["n"] += 1
+
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            # If the abandoned worker reaches here, the fix failed: a stale
+            # fetch started after the caller already fell back.
+            fetch_started.set()
+            return _FakeAccessResult()
+
+    monkeypatch.setattr(ab, "AccessBypass", _NeverShouldRunBypass)
+    monkeypatch.setattr(
+        live_retriever, "_fallback_naive_fetch",
+        lambda url, mc, t0, reason: ("", False, "", "", ""),
+    )
+
+    assert ab.bypass_leaked_worker_count() == 0
+    # The bypass worker blocks on acquire (slot held); outer join times out at
+    # 0.2s → records the leak + falls back to the (stubbed) naive path. No loop
+    # was ever published, so the active loop-cancel teardown is a no-op here —
+    # this exercises the pre-loop self-abort flag, not the post-loop cancel.
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/blocked-then-abandoned", max_chars=1000,
+    )
+    assert ok is False  # caller already fell back
+    assert ab.bypass_leaked_worker_count() == 1  # alive-past-deadline gauge fired
+    assert not fetch_started.is_set()  # worker still queued, fetch not yet run
+
+    # Release the holder so the abandoned worker's `acquire()` returns. With the
+    # fix, it then sees the abandoned flag and releases WITHOUT fetching.
+    holder_release.set()
+
+    # Positive sync proof: re-acquiring the singleton slot succeeds ONLY after
+    # the worker (FIFO-ahead on the Condition) acquired → checked flag → bailed →
+    # released. If the worker had instead run the fetch (bug) it would still hold
+    # the slot far longer; the bail path releases it immediately.
+    assert sem.acquire(timeout=5.0), (
+        "abandoned worker must self-abort and RELEASE its slot after waking from "
+        "acquire — the slot must not be leaked"
+    )
+    sem.release()
+
+    # The abandoned worker NEVER started its AccessBypass fetch.
+    assert not fetch_started.is_set(), (
+        "a worker abandoned while blocked on the in-flight slot must NOT start "
+        "its AccessBypass fetch after the slot frees (no stale fetch, no browser)"
+    )
+    # ...and the post-acquire check (#1) bailed BEFORE constructing AccessBypass
+    # (Codex's literal "BEFORE starting AccessBypass") — so no browser-bearing
+    # object was even instantiated for the abandoned worker.
+    assert constructed["n"] == 0, (
+        "the abandoned worker must self-abort at the post-acquire flag check, "
+        "BEFORE constructing AccessBypass (no browser-bearing object created)"
+    )
+
+
+def test_bypass_worker_uses_polaris_asyncio_run(monkeypatch):
+    """BB5-S02: the worker must run under polaris_asyncio_run (wedged-task
+    drain), NOT bare asyncio.run — assert the drain-runner is invoked."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "30")
+
+    called = {"polaris_run": 0}
+    real_runner = ab.polaris_asyncio_run
+
+    def _spy_runner(coro):
+        called["polaris_run"] += 1
+        return real_runner(coro)
+
+    monkeypatch.setattr(ab, "polaris_asyncio_run", _spy_runner)
+
+    class _FastBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            return _FakeAccessResult()
+
+    monkeypatch.setattr(ab, "AccessBypass", _FastBypass)
+
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/fast", max_chars=1000,
+    )
+    assert ok is True
+    assert "fake markdown content" in content
+    assert called["polaris_run"] == 1
+
+
+def test_inflight_bound_does_not_deadlock_under_contention(monkeypatch):
+    """No-deadlock property: with the slot limit far BELOW the number of
+    workers, every worker still eventually acquires + releases (the inner
+    wall-clock guarantees termination) — the batch drains in bounded time."""
+    monkeypatch.setenv("PG_BYPASS_MAX_INFLIGHT", "2")
+    ab.reset_bypass_leak_state()
+    sem = ab._get_bypass_inflight_semaphore()
+
+    live_peak = {"max": 0}
+    live_now = {"n": 0}
+    lock = threading.Lock()
+    done = {"n": 0}
+
+    def _worker():
+        sem.acquire()
+        try:
+            with lock:
+                live_now["n"] += 1
+                live_peak["max"] = max(live_peak["max"], live_now["n"])
+            time.sleep(0.02)  # simulate in-flight fetch
+        finally:
+            with lock:
+                live_now["n"] -= 1
+                done["n"] += 1
+            sem.release()
+
+    threads = [threading.Thread(target=_worker) for _ in range(20)]
+    start = time.monotonic()
+    for t in threads:
+        t.start()
+    for t in threads:
+        t.join(timeout=10.0)
+    elapsed = time.monotonic() - start
+
+    assert done["n"] == 20, "every worker must finish (no deadlock)"
+    assert live_peak["max"] <= 2, "in-flight concurrency must respect the bound"
+    assert elapsed < 10.0
+
+
+# ---------------------------------------------------------------------------
+# BB5-S03 — SIGSEGV-mitigated trafilatura guard
+# ---------------------------------------------------------------------------
+
+
+def test_safe_trafilatura_skips_oversized_html(monkeypatch):
+    """An oversized doc (over the size gate) must bypass libxml2 entirely →
+    returns None so the caller uses its regex fallback. Asserts trafilatura is
+    never even called for the oversized input. (The char-cap is a module-level
+    deploy-slate constant read at import, so patch it directly here.)"""
+    monkeypatch.setattr(ab, "_TRAFILATURA_MAX_HTML_CHARS", 1000)
+    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
+
+    # If trafilatura WERE called we'd see this flag flip.
+    import trafilatura
+    called = {"n": 0}
+    monkeypatch.setattr(
+        trafilatura, "extract",
+        lambda *a, **k: (called.__setitem__("n", called["n"] + 1) or "x"),
+    )
+
+    oversized = "<p>" + ("x" * 5000) + "</p>"
+    assert ab.safe_trafilatura_extract(oversized) is None
+    assert called["n"] == 0, "oversized HTML must never reach libxml2"
+
+
+def test_safe_trafilatura_in_process_returns_extracted(monkeypatch):
+    """In-process path returns trafilatura's text when the doc is within the
+    size gate (default 3M chars) and extraction succeeds."""
+    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
+    import trafilatura
+    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: "clean body text")
+    assert ab.safe_trafilatura_extract("<p>hi</p>") == "clean body text"
+
+
+def test_safe_trafilatura_never_raises_on_python_error(monkeypatch):
+    """A Python-level extract error returns None (regex fallback), never raises."""
+    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
+    import trafilatura
+
+    def _boom(*a, **k):
+        raise ValueError("malformed doc")
+
+    monkeypatch.setattr(trafilatura, "extract", _boom)
+    assert ab.safe_trafilatura_extract("<p>hi</p>") is None
+
+
+def test_safe_trafilatura_subprocess_contains_sigsegv(monkeypatch):
+    """The optional subprocess path contains a SIGSEGV-class child crash: a
+    negative/non-zero return code → None (caller falls back), sweep survives."""
+    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
+
+    @dataclass
+    class _CrashedProc:
+        returncode: int = -11  # SIGSEGV == exit 139
+        stdout: str = ""
+        stderr: str = ""
+
+    import subprocess
+    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CrashedProc())
+    # Must not raise; returns None so the caller uses its regex fallback.
+    assert ab.safe_trafilatura_extract("<p>pathological</p>") is None
+
+
+def test_safe_trafilatura_subprocess_timeout_returns_none(monkeypatch):
+    """A subprocess timeout is contained (None), never propagated."""
+    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
+    import subprocess
+
+    def _timeout(*a, **k):
+        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
+
+    monkeypatch.setattr(subprocess, "run", _timeout)
+    assert ab.safe_trafilatura_extract("<p>slow</p>") is None
+
+
+# ---------------------------------------------------------------------------
+# BB5-C05 — extractor fallback chain + distinct telemetry
+# ---------------------------------------------------------------------------
+
+
+def test_strip_html_falls_back_to_readability(monkeypatch):
+    """When trafilatura returns empty, _strip_html tries readability-lxml before
+    the last-resort regex strip."""
+    # safe_trafilatura_extract returns None (empty tree).
+    monkeypatch.setattr(ab, "safe_trafilatura_extract", lambda *a, **k: None)
+    monkeypatch.setattr(
+        live_retriever, "_readability_extract",
+        lambda html: "readability recovered article body",
+    )
+    # Disable table append so we read the base extractor result directly.
+    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
+    out = live_retriever._strip_html("<html><body><p>x</p></body></html>")
+    assert out == "readability recovered article body"
+
+
+def test_oversized_html_skips_readability_goes_to_regex(monkeypatch):
+    """BB5-S03 iter-2 (Codex P1-S03): readability-lxml ALSO parses via lxml —
+    the SAME libxml2 SIGSEGV surface trafilatura was size-gated away from. An
+    oversized doc (over the shared size bound) that skipped trafilatura must
+    ALSO skip readability and go straight to the regex strip. Asserts
+    _readability_extract is NEVER called for oversized input, and the regex
+    fallback still recovers visible text."""
+    # Shrink the shared size bound so our small doc counts as "oversized". The
+    # gate reads this module global at call time (the function, not a frozen
+    # constant value, is imported by _strip_html).
+    monkeypatch.setattr(ab, "_TRAFILATURA_MAX_HTML_CHARS", 1000)
+    # trafilatura is size-skipped (None) for the oversized doc.
+    monkeypatch.setattr(ab, "safe_trafilatura_extract", lambda *a, **k: None)
+    # readability MUST NOT be reached — flip a flag if it ever is.
+    called = {"readability": 0}
+    monkeypatch.setattr(
+        live_retriever, "_readability_extract",
+        lambda html: (called.__setitem__("readability", called["readability"] + 1)
+                      or "readability SHOULD NOT have run"),
+    )
+    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
+
+    oversized = "<html><body><p>regex visible words survive here</p>" + (
+        "<span>x</span>" * 500
+    ) + "</body></html>"
+    assert len(oversized) > 1000  # over the (shrunk) size bound
+    out = live_retriever._strip_html(oversized)
+    assert called["readability"] == 0, (
+        "oversized HTML must NEVER reach readability-lxml (same libxml2 crash "
+        "surface as trafilatura)"
+    )
+    assert "regex visible words survive here" in out, (
+        "the regex strip is the only safe extractor for oversized HTML"
+    )
+
+
+def test_under_size_html_still_uses_readability(monkeypatch):
+    """BB5-S03 iter-2 guard: a doc WITHIN the size bound still gets the
+    readability fallback when trafilatura declines — the size gate must not
+    over-fire and starve healthy docs of the readability recovery path."""
+    monkeypatch.setattr(ab, "_TRAFILATURA_MAX_HTML_CHARS", 3_000_000)
+    monkeypatch.setattr(ab, "safe_trafilatura_extract", lambda *a, **k: None)
+    monkeypatch.setattr(
+        live_retriever, "_readability_extract",
+        lambda html: "readability recovered article body",
+    )
+    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
+    out = live_retriever._strip_html("<html><body><p>small</p></body></html>")
+    assert out == "readability recovered article body"
+
+
+def test_strip_html_regex_last_resort_when_both_empty(monkeypatch):
+    """When trafilatura AND readability both yield nothing, the regex strip is
+    the final fallback (never returns empty for real tag soup)."""
+    monkeypatch.setattr(ab, "safe_trafilatura_extract", lambda *a, **k: None)
+    monkeypatch.setattr(live_retriever, "_readability_extract", lambda html: "")
+    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
+    out = live_retriever._strip_html(
+        "<html><body><p>plain visible words survive</p></body></html>"
+    )
+    assert "plain visible words survive" in out
+
+
+def test_readability_extract_missing_dep_is_skip_not_crash(monkeypatch):
+    """A missing readability-lxml dep logs + returns '' — never breaks strip."""
+    import builtins
+    real_import = builtins.__import__
+
+    def _no_readability(name, *args, **kwargs):
+        if name == "readability":
+            raise ImportError("readability-lxml not installed")
+        return real_import(name, *args, **kwargs)
+
+    monkeypatch.setattr(builtins, "__import__", _no_readability)
+    assert live_retriever._readability_extract("<p>x</p>") == ""
+
+
+def test_fetched_200_but_empty_extract_distinct_telemetry(monkeypatch):
+    """BB5-C05: a real 200 body that the extractor chain collapses below the
+    floor is surfaced as the DISTINCT 'fetched_200_but_empty_extract' bucket,
+    not a silent generic miss."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "30")
+    monkeypatch.setenv("PG_FETCH_NONEMPTY_RAW_FLOOR", "200")
+    monkeypatch.setenv("PG_FETCH_EMPTY_EXTRACT_FLOOR", "50")
+
+    # Backend returns a big raw body...
+    big_raw = "<html>" + ("<div></div>" * 500) + "</html>"
+
+    class _BigEmptyBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            return _FakeAccessResult(success=True, content=big_raw)
+
+    monkeypatch.setattr(ab, "AccessBypass", _BigEmptyBypass)
+    # ...but the extractor chain yields nothing usable.
+    monkeypatch.setattr(live_retriever, "_strip_html", lambda c: "")
+
+    captured = {}
+    monkeypatch.setattr(
+        live_retriever, "_m45_record_fetch_telemetry",
+        lambda url, method, failure_reason="": captured.__setitem__(
+            "reason", failure_reason
+        ),
+    )
+
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/empty-extract", max_chars=25000,
+    )
+    assert len(big_raw) >= 200
+    assert content == ""
+    assert ok is False
+    assert captured.get("reason") == "fetched_200_but_empty_extract"
+
+
+def test_naive_path_also_surfaces_empty_extract_bucket(monkeypatch):
+    """BB5-C05 iter-2 (Codex P2): the empty-extract telemetry bucket fires on
+    the NAIVE/DIRECT fetch path too (not only the parallel/AccessBypass path).
+    A real 200 body whose extractor chain collapses below the floor must be the
+    distinct 'fetched_200_but_empty_extract' bucket here as well."""
+    monkeypatch.setenv("PG_FETCH_NONEMPTY_RAW_FLOOR", "200")
+    monkeypatch.setenv("PG_FETCH_EMPTY_EXTRACT_FLOOR", "50")
+    monkeypatch.setattr(live_retriever, "_EXTRACT_NONEMPTY_RAW_FLOOR", 200)
+    monkeypatch.setattr(live_retriever, "_EXTRACT_EMPTY_FLOOR", 50)
+
+    big_raw = "<html>" + ("<div></div>" * 500) + "</html>"
+
+    class _Resp:
+        status_code = 200
+        headers = {"content-type": "text/html"}
+        text = big_raw
+        content = big_raw.encode()
+
+    class _Client:
+        def __init__(self, *a, **k):
+            pass
+
+        def __enter__(self):
+            return self
+
+        def __exit__(self, *a):
+            return False
+
+        def get(self, url):
+            return _Resp()
+
+    monkeypatch.setattr(live_retriever.httpx, "Client", _Client)
+    # Extractor chain collapses to empty for this raw body.
+    monkeypatch.setattr(live_retriever, "_strip_html", lambda c: "")
+
+    captured = {"reason": None}
+    monkeypatch.setattr(
+        live_retriever, "_m45_record_fetch_telemetry",
+        lambda url, method, failure_reason="": captured.__setitem__(
+            "reason", failure_reason
+        ),
+    )
+
+    content, ok, _t, _b, _j = live_retriever._fetch_content_httpx_naive(
+        "https://example.com/naive-empty", max_chars=25000,
+    )
+    assert len(big_raw) >= 200
+    assert content == ""
+    assert ok is False
+    assert captured["reason"] == "fetched_200_but_empty_extract"
+
+
+def test_naive_empty_extract_no_contradictory_double_trace(monkeypatch):
+    """BB5-C05 iter-2 (Codex P2 reconcile): a naive empty-extract fetch routed
+    through the PRODUCTION wrapper (`_fallback_naive_fetch`) must emit exactly
+    ONE `_trace_tool` record for the fetch — NOT both an `empty_extract` (from
+    the naive function) AND a `fail` (from the wrapper). The distinct bucket is
+    carried by the keyed `_m45` reason; the trace must not be double-recorded
+    with contradictory statuses (mirroring the parallel path's single trace)."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "1")  # force the naive path
+    monkeypatch.setattr(live_retriever, "_EXTRACT_NONEMPTY_RAW_FLOOR", 200)
+    monkeypatch.setattr(live_retriever, "_EXTRACT_EMPTY_FLOOR", 50)
+
+    big_raw = "<html>" + ("<div></div>" * 500) + "</html>"
+
+    class _Resp:
+        status_code = 200
+        headers = {"content-type": "text/html"}
+        text = big_raw
+        content = big_raw.encode()
+
+    class _Client:
+        def __init__(self, *a, **k):
+            pass
+
+        def __enter__(self):
+            return self
+
+        def __exit__(self, *a):
+            return False
+
+        def get(self, url):
+            return _Resp()
+
+    monkeypatch.setattr(live_retriever.httpx, "Client", _Client)
+    monkeypatch.setattr(live_retriever, "_strip_html", lambda c: "")
+
+    # Capture every _trace_tool emission for the fetch_content tool.
+    traces: list[dict[str, Any]] = []
+    monkeypatch.setattr(
+        live_retriever, "_trace_tool",
+        lambda tool, **kw: traces.append({"tool": tool, **kw}),
+    )
+    m45_reasons: list[str] = []
+    monkeypatch.setattr(
+        live_retriever, "_m45_record_fetch_telemetry",
+        lambda url, method, failure_reason="": m45_reasons.append(failure_reason),
+    )
+
+    # _fetch_content (the production entry) routes the PG_DISABLE_ACCESS_BYPASS=1
+    # case through _fallback_naive_fetch, which is where the single trace lives.
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/naive-empty-prod", max_chars=25000,
+    )
+    assert ok is False
+    assert content == ""
+    fetch_traces = [t for t in traces if t["tool"] == "fetch_content"]
+    # Exactly one trace for this fetch — no empty_extract + fail double-record.
+    assert len(fetch_traces) == 1, (
+        f"expected exactly one fetch_content trace, got {len(fetch_traces)}: "
+        f"{[t.get('status') for t in fetch_traces]}"
+    )
+    # The distinct empty-extract signal is still carried by the keyed _m45 reason.
+    assert "fetched_200_but_empty_extract" in m45_reasons
+
+
+def test_naive_path_healthy_fetch_not_flagged_empty(monkeypatch):
+    """BB5-C05 iter-2 guard: a healthy naive fetch (real extracted body) is NOT
+    mislabelled as the empty-extract bucket on the direct path."""
+    big_raw = "<html><body>" + ("<p>real body words </p>" * 80) + "</body></html>"
+
+    class _Resp:
+        status_code = 200
+        headers = {"content-type": "text/html"}
+        text = big_raw
+        content = big_raw.encode()
+
+    class _Client:
+        def __init__(self, *a, **k):
+            pass
+
+        def __enter__(self):
+            return self
+
+        def __exit__(self, *a):
+            return False
+
+        def get(self, url):
+            return _Resp()
+
+    monkeypatch.setattr(live_retriever.httpx, "Client", _Client)
+    monkeypatch.setattr(
+        live_retriever, "_strip_html",
+        lambda c: "real extracted body well over the empty floor " * 5,
+    )
+
+    captured = {"reason": "SENTINEL"}
+    monkeypatch.setattr(
+        live_retriever, "_m45_record_fetch_telemetry",
+        lambda url, method, failure_reason="": captured.__setitem__(
+            "reason", failure_reason
+        ),
+    )
+
+    content, ok, _t, _b, _j = live_retriever._fetch_content_httpx_naive(
+        "https://example.com/naive-good", max_chars=25000,
+    )
+    assert ok is True
+    # The empty-extract telemetry must NOT have fired on a healthy body.
+    assert captured["reason"] == "SENTINEL"
+
+
+def test_normal_fetch_not_flagged_as_empty_extract(monkeypatch):
+    """A healthy fetch (real extracted body) is NOT mislabelled as the empty
+    bucket — guards against a false-positive on the new branch."""
+    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
+    monkeypatch.setenv("PG_FETCH_DEADLINE_SECONDS", "30")
+
+    class _GoodBypass:
+        async def fetch_with_bypass(self, url, prefer_legal=True):
+            return _FakeAccessResult(
+                success=True, content="<p>" + ("real body text " * 50) + "</p>"
+            )
+
+    monkeypatch.setattr(ab, "AccessBypass", _GoodBypass)
+    monkeypatch.setattr(
+        live_retriever, "_strip_html",
+        lambda c: "real extracted body well over the empty floor " * 5,
+    )
+
+    captured = {"reason": None}
+    monkeypatch.setattr(
+        live_retriever, "_m45_record_fetch_telemetry",
+        lambda url, method, failure_reason="": captured.__setitem__(
+            "reason", failure_reason
+        ),
+    )
+
+    content, ok, _t, _b, _j = live_retriever._fetch_content(
+        "https://example.com/good", max_chars=25000,
+    )
+    assert ok is True
+    assert captured["reason"] == ""  # the OK telemetry path, not empty-extract
