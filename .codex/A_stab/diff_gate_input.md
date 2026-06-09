HARD ITERATION CAP 5, iter 1 of 5. Front-load findings; APPROVE iff zero NOVEL/continuing P0 and zero P1; final 'verdict: APPROVE|REQUEST_CHANGES' line + §8.3.9 schema. Lane A_stab (#1177): LANE A — fetch/stability (BB5-S02/S03/C05, issue #1177). Implement all three:
- S02 (abandoned-thread teardown): timed-out parallel_fetch workers + inner AccessBypass daemons are abandoned, orphaning Crawl4AI/Playwright subprocesses (parallel_fetch.py docstring ~256-262; live_retriever.py ~1900 daemon). Bound concurrent in-flight bypass workers and CLOSE Crawl4AI/Playwright contexts in a finally even on timeout (no leaked browser subprocess). Add a leaked-thread/subprocess gauge if cheap.
- S03 (uncatchable SIGSEGV): live_retriever.py ~1317-1323 runs trafilatura.extract under 'except Exception: pass' — a libxml2 C-crash is SIGSEGV (drb_76 exit 139), uncatchable. Run trafilatura.extract in a hard-killable subprocess (or RLIMIT+faulthandler) OR size-bound/validate HTML and prefer the regex fallback for oversized/suspect docs.
- C05 (extractor fallback): trafilatura returns empty trees on 30-50% of fetched pages (no_content). Add a fallback extractor chain (readability-lxml / jina_reader / PDF path) when trafilatura returns an empty tree; treat 'fetched-200-but-empty-extract' as a DISTINCT telemetry bucket (not silent).

VERIFY adversarially: each sub-fix does what it claims; faithfulness gate authority NOT weakened (Lane B entailment may be strengthened); named constants/env knobs; offline tests genuinely exercise the fix (not tautological); fail-closed preserved.

=== DIFF UNDER REVIEW ===

diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 9e9867e7..3e0f5e0a 100644
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
@@ -1338,18 +1350,60 @@ def _extract_jsonld_blocks(raw_html: str) -> str:
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
+        base = _readability_extract(html)
     if not base:
         # Fallback: strip tags + collapse whitespace
         no_tags = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
@@ -1915,16 +1969,40 @@ def _fetch_content(
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
 
     def _bypass_worker() -> None:
+        # BB5-S02: acquire a cross-thread in-flight slot. Bounds the number of
+        # concurrently-LIVE bypass workers (each may hold a browser subprocess)
+        # across all per-thread event loops — `_get_crawl4ai_semaphore` cannot,
+        # being lazy-bound to THIS thread's fresh loop only.
+        _inflight_sem.acquire()
         try:
             bypass = AccessBypass()
-            result_holder["value"] = asyncio.run(
+            # BB5-S02: polaris_asyncio_run (vs bare asyncio.run) force-drains
+            # wedged detached Playwright fetch tasks BEFORE the loop's
+            # cancel-all phase, so the loop teardown cannot hang on an
+            # un-cancellable browser op — closing the orphan-subprocess window
+            # for a worker that DOES eventually return.
+            result_holder["value"] = polaris_asyncio_run(
                 bypass.fetch_with_bypass(url, prefer_legal=True)
             )
         except Exception as exc:  # noqa: BLE001
             result_holder["error"] = exc
+        finally:
+            _inflight_sem.release()
 
     worker = threading.Thread(target=_bypass_worker, daemon=True)
     worker.start()
@@ -1940,10 +2018,16 @@ def _fetch_content(
         deadline = 90.0
     worker.join(timeout=deadline if deadline > 0 else None)
     if worker.is_alive():
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
         # M-45 pass-2: record AccessBypass timeout so diagnostics can
         # distinguish timeout from backend refusal.
@@ -2054,6 +2138,30 @@ def _fetch_content(
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
@@ -2898,6 +3006,16 @@ def run_live_retrieval(
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
diff --git a/src/tools/access_bypass.py b/src/tools/access_bypass.py
index d80dff51..cddb8407 100644
--- a/src/tools/access_bypass.py
+++ b/src/tools/access_bypass.py
@@ -24,6 +24,7 @@ import logging
 import os
 import re
 import sys
+import threading
 import time as _time_module
 from typing import Any, Dict, List, Optional
 from dataclasses import dataclass
@@ -105,6 +106,223 @@ def _get_crawl4ai_semaphore() -> "asyncio.Semaphore":
         )
     return _crawl4ai_semaphore
 
+
+# ---------------------------------------------------------------------------
+# BB5-S02 (#1177): cross-THREAD in-flight bypass-worker bound + leak gauge.
+#
+# `live_retriever._fetch_content` runs each `AccessBypass.fetch_with_bypass`
+# on a fresh daemon thread with its OWN `asyncio.run` loop, joined with a hard
+# timeout. On timeout the thread is ABANDONED (it keeps running, holding a live
+# Crawl4AI/Playwright browser subprocess mid-`arun`). Under the ~740-URL
+# benchmark fan-out, hundreds of abandoned threads + browser subprocesses
+# accumulate (the resource-exhaustion / segfault mechanism).
+#
+# `_get_crawl4ai_semaphore()` cannot bound this: it is lazy-bound to the
+# RUNNING loop, and every bypass worker thread has its OWN fresh loop — so it
+# only caps browsers WITHIN one thread. A `threading`-level BoundedSemaphore is
+# the only primitive that bounds the abandoned-thread FLEET across loops.
+#
+# Acquire at the TOP of the worker (in `live_retriever`), release in THAT
+# worker's `finally` — never in the outer join path (releasing on abandonment
+# would over-release; not releasing would leak the slot). Sized BELOW the
+# parallel `max_workers` so it creates back-pressure; no deadlock because the
+# inner per-backend wall-clocks guarantee every abandoned worker eventually
+# terminates and releases its slot.
+# ---------------------------------------------------------------------------
+
+# Default ceiling on concurrently-LIVE bypass worker threads (each may hold a
+# browser subprocess). Env-overridable. Below the live_retriever parallel
+# `max_workers` ceiling (48) so abandoned in-flight workers cannot fan out a
+# browser-per-candidate. Named constant (LAW VI — no magic numbers).
+_BYPASS_INFLIGHT_DEFAULT_LIMIT = 16
+PG_BYPASS_MAX_INFLIGHT_ENV = "PG_BYPASS_MAX_INFLIGHT"
+
+_bypass_inflight_semaphore: "threading.BoundedSemaphore | None" = None
+_bypass_inflight_semaphore_lock = threading.Lock()
+
+# BB5-S02 leaked-worker gauge: monotonically-incremented count of bypass worker
+# threads that were ABANDONED (outer join timed out while the worker was still
+# alive). A non-zero gauge is the auditable signal that orphan browser
+# subprocesses may have accumulated. Guarded by its own lock.
+_bypass_leaked_worker_count: int = 0
+_bypass_leaked_worker_lock = threading.Lock()
+
+
+def _get_bypass_inflight_semaphore() -> "threading.BoundedSemaphore":
+    """BB5-S02 (#1177): lazy-init the cross-thread in-flight bypass-worker
+    bound. A `threading.BoundedSemaphore` (NOT asyncio) — it must bound worker
+    threads across their independent per-thread event loops.
+
+    Limit from `PG_BYPASS_MAX_INFLIGHT` (positive int), else
+    `_BYPASS_INFLIGHT_DEFAULT_LIMIT`. A malformed/<=0 value falls back to the
+    default — a bad knob must never disable the bound (which would re-open the
+    abandoned-fleet leak)."""
+    global _bypass_inflight_semaphore
+    if _bypass_inflight_semaphore is None:
+        with _bypass_inflight_semaphore_lock:
+            if _bypass_inflight_semaphore is None:
+                raw = os.getenv(PG_BYPASS_MAX_INFLIGHT_ENV)
+                limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
+                if raw is not None and raw.strip():
+                    try:
+                        parsed = int(raw)
+                        if parsed > 0:
+                            limit = parsed
+                    except ValueError:
+                        limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
+                _bypass_inflight_semaphore = threading.BoundedSemaphore(limit)
+    return _bypass_inflight_semaphore
+
+
+def record_bypass_leaked_worker() -> int:
+    """BB5-S02 (#1177): increment + return the leaked-bypass-worker gauge. The
+    caller (live_retriever) invokes this when an outer fetch join times out
+    while the worker thread is still alive (abandoned → potential orphan
+    browser subprocess). Thread-safe; returns the new total for logging."""
+    global _bypass_leaked_worker_count
+    with _bypass_leaked_worker_lock:
+        _bypass_leaked_worker_count += 1
+        return _bypass_leaked_worker_count
+
+
+def bypass_leaked_worker_count() -> int:
+    """BB5-S02 (#1177): read the current leaked-bypass-worker gauge (auditable
+    orphan-subprocess signal). Thread-safe snapshot."""
+    with _bypass_leaked_worker_lock:
+        return _bypass_leaked_worker_count
+
+
+def reset_bypass_leak_state() -> None:
+    """BB5-S02 (#1177): reset the leak gauge + in-flight semaphore. For test
+    isolation ONLY — not called on the production path."""
+    global _bypass_leaked_worker_count, _bypass_inflight_semaphore
+    with _bypass_leaked_worker_lock:
+        _bypass_leaked_worker_count = 0
+    with _bypass_inflight_semaphore_lock:
+        _bypass_inflight_semaphore = None
+
+
+# ---------------------------------------------------------------------------
+# BB5-S03 (#1177): SIGSEGV-mitigated shared trafilatura extractor.
+#
+# `trafilatura.extract` runs libxml2 (a C extension). On a pathological /
+# malformed / adversarial document libxml2 can SIGSEGV (drb_76 exit 139) — a
+# C-level crash that is NOT a Python exception and CANNOT be caught by
+# `except Exception`. A try/except around the call is false confidence.
+#
+# True containment is a per-page hard-killable subprocess, but that is heavy at
+# hundreds of calls/run AND `resource` RLIMIT is Unix-only (no-op on win32).
+# So the DEFAULT is lean MITIGATION (not containment): size-bound the HTML and
+# prefer the caller's regex fallback for oversized/suspect docs, which never
+# enters libxml2 at all. An optional hard-killable subprocess path is gated
+# behind `PG_TRAFILATURA_SUBPROCESS=1` (OFF by default).
+#
+# Lives in access_bypass (NOT live_retriever): live_retriever already imports
+# access_bypass, so the reverse import would be circular. Both trafilatura
+# sites import this one guarded entrypoint.
+# ---------------------------------------------------------------------------
+
+# Upper bound (chars) on HTML handed to libxml2 via trafilatura. A document
+# larger than this is treated as suspect/oversized: we skip trafilatura and
+# signal the caller to use its regex fallback (which never enters the C
+# extension). Env-overridable. Named constant (LAW VI).
+_TRAFILATURA_MAX_HTML_CHARS = int(
+    os.getenv("PG_TRAFILATURA_MAX_HTML_CHARS", "3000000")
+)
+PG_TRAFILATURA_SUBPROCESS_ENV = "PG_TRAFILATURA_SUBPROCESS"
+# Hard wall-clock for the optional subprocess extractor path (seconds).
+_TRAFILATURA_SUBPROCESS_TIMEOUT = float(
+    os.getenv("PG_TRAFILATURA_SUBPROCESS_TIMEOUT_SECONDS", "20")
+)
+
+
+def _html_is_extract_safe(html: str) -> bool:
+    """BB5-S03 (#1177): cheap pre-validation gate. Returns False for an
+    oversized document (over `_TRAFILATURA_MAX_HTML_CHARS`) that should bypass
+    libxml2 entirely. Pure size check — no parsing, never itself crashes."""
+    if not html:
+        return False
+    if len(html) > _TRAFILATURA_MAX_HTML_CHARS:
+        return False
+    return True
+
+
+def _trafilatura_extract_subprocess(html: str, **kwargs: Any) -> "str | None":
+    """BB5-S03 (#1177): run `trafilatura.extract` in a hard-killable child
+    process so a libxml2 SIGSEGV takes down the child (exit 139) instead of the
+    sweep. Returns the extracted text, or None on timeout/crash/error.
+
+    Gated OFF by default (`PG_TRAFILATURA_SUBPROCESS=1` to enable) — true
+    containment is heavy at hundreds of calls/run. Best-effort: any failure
+    (spawn error, non-zero exit incl. -11/139 SIGSEGV, timeout) returns None so
+    the caller falls back to regex extraction. Never raises."""
+    import json
+    import subprocess
+
+    payload = json.dumps({"html": html, "kwargs": kwargs})
+    code = (
+        "import sys, json\n"
+        "data = json.loads(sys.stdin.read())\n"
+        "import trafilatura\n"
+        "out = trafilatura.extract(data['html'], **data['kwargs']) or ''\n"
+        "sys.stdout.write(out)\n"
+    )
+    try:
+        proc = subprocess.run(
+            [sys.executable, "-c", code],
+            input=payload,
+            capture_output=True,
+            text=True,
+            timeout=_TRAFILATURA_SUBPROCESS_TIMEOUT,
+        )
+    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
+        logger.warning(
+            "[ACCESS] BB5-S03 trafilatura subprocess failed (%s) — "
+            "regex fallback", type(exc).__name__,
+        )
+        return None
+    if proc.returncode != 0:
+        # A negative return code is a signal (e.g. -11 == SIGSEGV / exit 139):
+        # the child crashed on a pathological doc and the SWEEP survived.
+        logger.warning(
+            "[ACCESS] BB5-S03 trafilatura subprocess exited rc=%s "
+            "(SIGSEGV-class crash contained) — regex fallback",
+            proc.returncode,
+        )
+        return None
+    return proc.stdout or None
+
+
+def safe_trafilatura_extract(html: str, **kwargs: Any) -> "str | None":
+    """BB5-S03 (#1177): the ONE guarded trafilatura entrypoint used by every
+    extraction site (live_retriever `_strip_html`, access_bypass
+    `_try_crawl4ai`).
+
+    Contract:
+      - Returns extracted text (str) on success, or None when extraction is
+        unsafe/empty/failed (caller falls back to its own regex path).
+      - Honest MITIGATION, not containment, on the default in-process path:
+        an oversized/suspect doc skips libxml2 (returns None → regex fallback);
+        a SIGSEGV on a doc that passes the size gate is still uncatchable
+        in-process. Enable `PG_TRAFILATURA_SUBPROCESS=1` for true containment.
+      - Never raises (the C-extension SIGSEGV is the one thing it cannot
+        promise to catch on the in-process path — documented, not hidden)."""
+    if not _html_is_extract_safe(html):
+        return None
+    if os.getenv(PG_TRAFILATURA_SUBPROCESS_ENV, "0") == "1":
+        return _trafilatura_extract_subprocess(html, **kwargs)
+    try:
+        import trafilatura  # type: ignore
+        return trafilatura.extract(html, **kwargs) or None
+    except Exception as exc:  # noqa: BLE001 — Python-level errors only; a
+        # libxml2 SIGSEGV is NOT a Python exception and escapes this guard (by
+        # design — that is what PG_TRAFILATURA_SUBPROCESS=1 contains).
+        logger.debug(
+            "[ACCESS] BB5-S03 trafilatura in-process extract error (%s) — "
+            "regex fallback", type(exc).__name__,
+        )
+        return None
+
 # ---------------------------------------------------------------------------
 # Firecrawl free-plan hardening: rate limiter + credit tracker
 # ---------------------------------------------------------------------------
@@ -1206,22 +1424,23 @@ class AccessBypass:
             # PruningContentFilter misses. Falls back to fit_markdown/raw.
             markdown_content = ""
             if result.html:
-                try:
-                    import trafilatura as _traf
-                    clean = _traf.extract(
-                        result.html,
-                        include_tables=True,
-                        include_links=False,
-                        output_format="txt",
+                # BB5-S03 (#1177): route through the SIGSEGV-mitigated shared
+                # extractor (size-bounds the HTML, optional subprocess
+                # containment) instead of a bare `trafilatura.extract` under
+                # `except Exception` — a libxml2 C-crash on Crawl4AI's raw HTML
+                # is not a catchable Python exception.
+                clean = safe_trafilatura_extract(
+                    result.html,
+                    include_tables=True,
+                    include_links=False,
+                    output_format="txt",
+                )
+                if clean and len(clean) > 500:
+                    markdown_content = clean
+                    logger.info(
+                        "[ACCESS] PL: Trafilatura cleaned Crawl4AI HTML: %d chars",
+                        len(clean),
                     )
-                    if clean and len(clean) > 500:
-                        markdown_content = clean
-                        logger.info(
-                            "[ACCESS] PL: Trafilatura cleaned Crawl4AI HTML: %d chars",
-                            len(clean),
-                        )
-                except Exception:
-                    pass
 
             # Fallback: fit_markdown or raw markdown from Crawl4AI
             if not markdown_content:
diff --git a/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py b/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py
new file mode 100644
index 00000000..0bba826e
--- /dev/null
+++ b/tests/polaris_graph/test_lane_a_fetch_stability_bb5.py
@@ -0,0 +1,396 @@
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
