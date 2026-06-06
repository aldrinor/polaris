# FX-17 (#1126) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P2 discovery-breadth — faithfulness-SAFE (adds candidates; all pass the same fetch/tier/strict_verify/
4-role gates). Default byte-identical (single page). Diff: `.codex/I-ready-017/fx17_codex_diff.patch`
(vs FX-13 verified tip `5004b5a6`).

## Bug — confirmed §-1.1 on the REAL held trace
`_serper_search` did `min(num, 20)` SILENTLY (PG_SWEEP_MAX_SERPER=100 floored to a 20-item page) and
never paginated. Held drb_72 serper return_counts: **[10, 10, 10, 10, 10]** (uniform, single page; the
100 cap was inert + lying). Full §-1.1: `outputs/audits/I-ready-017/fx17_s11_audit.md`.

## Fix
1. **Visible clamp**: WARNING + clamp telemetry (`clamped/num_requested/per_page/page_max`) when
   `num > _SERPER_PAGE_MAX (20)`.
2. **Pagination**: new `_serper_fetch_page(query, per_page, page, headers)` helper (byte-identical
   payload when page==1 — no `page` key); `_serper_search` loops pages, dedups via `seen`, up to
   `PG_SERPER_TOTAL_PER_QUERY` (default = per_page → ONE page → byte-identical), bounded by
   `PG_SERPER_MAX_PAGES` (default 3), early-stop when a page returns < per_page. Aggregate trace adds
   `pages_fetched`/`total_budget`.
3. Query-variant count stays the env-tuned breadth knob (config; no code change).

## Evidence
- §-1.1 held trace: serper [10,10,10,10,10] — above.
- Offline smoke `test_fx17_serper_pagination_iready017.py` → 5 passed: default single page (no
  pagination); num=100 → WARNING + still single page on default; budget=40 → pages 1+2 accumulate +
  **dedup** (overlapping URL → 39 unique); short page → early-stop; `PG_SERPER_MAX_PAGES=2` cap
  respected over a budget of 200.
- Regression: `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) green.

## Decisions made (please confirm)
- **Default = one page (byte-identical):** `PG_SERPER_TOTAL_PER_QUERY` unset → total = per_page → 1
  page; page-1 payload has no `page` key (identical to the legacy request). The clamp WARNING still
  fires on the default path when num>20 (the intended honesty fix — it's a log, not a result change).
  Acceptable?
- **Bounds:** `PG_SERPER_MAX_PAGES` default 3 + total-URL budget + early-stop keep added Serper calls
  small. OK?

## Question
Is the pagination correct (dedup, early-stop, max-pages, byte-identical default) and the clamp now
honestly surfaced? Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-13 verified tip 5004b5a6)
```diff
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index ffb1bddb..33e4f8b4 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -200,6 +200,37 @@ def _resp_content_len(resp: Any) -> int:
 # ─────────────────────────────────────────────────────────────────────────────
 
 
+# FX-17 (#1126): Serper `num` is a PAGE size (provider max ~20); large result sets need the `page`
+# param (pagination). The old code silently floored `num` to 20 with no warning and never paginated.
+_SERPER_PAGE_MAX = 20
+
+
+def _serper_fetch_page(
+    query: str, per_page: int, page: int, headers: dict[str, str]
+) -> tuple[list[dict[str, Any]], bool, float, int, str]:
+    """FX-17 (#1126): fetch ONE Serper page. Returns (items, ok, latency_ms, resp_bytes, error).
+    Byte-identical to the legacy single call when page==1 (no `page` key in the payload)."""
+    payload: dict[str, Any] = {"q": query, "num": per_page}
+    if page > 1:
+        payload["page"] = page
+    _t0 = time.time()
+    try:
+        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
+            r = c.post(SERPER_ENDPOINT, json=payload, headers=headers)
+        _latency_ms = (time.time() - _t0) * 1000.0
+        if r.status_code != 200:
+            return [], False, _latency_ms, _resp_content_len(r), f"HTTP {r.status_code}"
+        organic = (r.json().get("organic", []) or [])
+        items = [
+            {"url": it.get("link", ""), "title": it.get("title", ""),
+             "snippet": it.get("snippet", ""), "source": "serper"}
+            for it in organic
+        ]
+        return items, True, _latency_ms, _resp_content_len(r), ""
+    except Exception as exc:
+        return [], False, (time.time() - _t0) * 1000.0, 0, str(exc)
+
+
 def _serper_search(query: str, num: int = 10) -> list[dict[str, Any]]:
     api_key = os.getenv("SERPER_API_KEY", "").strip()
     if not api_key:
@@ -214,51 +245,63 @@ def _serper_search(query: str, num: int = 10) -> list[dict[str, Any]]:
     except Exception:
         pass
     headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
-    payload = {"q": query, "num": max(1, min(num, 20))}
-    # I-meta-007b: wall-clock for the tool tracer (record-only).
-    _t0 = time.time()
-    _bytes_sent = len(str(payload))
+    per_page = max(1, min(num, _SERPER_PAGE_MAX))
+    # FX-17 (#1126): make the silent clamp VISIBLE — the inert PG_SWEEP_MAX_SERPER=100 used to floor
+    # to 20 with no signal. Surface it loudly so the requested-vs-served gap stops lying.
+    _clamped = num > _SERPER_PAGE_MAX
+    if _clamped:
+        logger.warning(
+            "[live_retriever] Serper num=%d exceeds the page max %d — clamping per-page to %d and "
+            "paginating to the PG_SERPER_TOTAL_PER_QUERY budget.", num, _SERPER_PAGE_MAX, per_page,
+        )
+    # FX-17 (#1126): total-URL budget across pages. DEFAULT = one page (per_page) -> byte-identical to
+    # the legacy single call; the benchmark slate raises PG_SERPER_TOTAL_PER_QUERY. Page count is
+    # bounded by PG_SERPER_MAX_PAGES (small) and early-stops when a page returns < per_page.
     try:
-        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
-            r = c.post(SERPER_ENDPOINT, json=payload, headers=headers)
-        _latency_ms = (time.time() - _t0) * 1000.0
-        if r.status_code != 200:
+        _total = max(per_page, int(os.getenv("PG_SERPER_TOTAL_PER_QUERY", str(per_page))))
+    except ValueError:
+        _total = per_page
+    try:
+        _max_pages = max(1, int(os.getenv("PG_SERPER_MAX_PAGES", "3")))
+    except ValueError:
+        _max_pages = 3
+    _n_pages = min(_max_pages, -(-_total // per_page))  # ceil(total/per_page)
+
+    out: list[dict[str, Any]] = []
+    seen: set[str] = set()
+    _pages_fetched = 0
+    _last_latency = 0.0
+    _last_bytes = 0
+    _last_err = ""
+    for _page in range(1, _n_pages + 1):
+        items, ok, _last_latency, _last_bytes, _last_err = _serper_fetch_page(
+            query, per_page, _page, headers
+        )
+        if not ok:
             _trace_tool(
-                "serper", target=query, status="fail", latency_ms=_latency_ms,
-                bytes_sent=_bytes_sent,
-                bytes_received=_resp_content_len(r),
-                backend_used="serper_api_v1", error=f"HTTP {r.status_code}",
+                "serper", target=query, status="fail", latency_ms=_last_latency,
+                bytes_sent=len(query), bytes_received=_last_bytes,
+                backend_used="serper_api_v1", error=_last_err, page=_page,
             )
-            logger.warning(
-                "[live_retriever] Serper returned %s for %r",
-                r.status_code, query[:60],
-            )
-            _trace_query("serper", query, [])
-            return []
-        data = r.json()
-    except Exception as exc:
-        _trace_tool(
-            "serper", target=query, status="fail",
-            latency_ms=(time.time() - _t0) * 1000.0, bytes_sent=_bytes_sent,
-            backend_used="serper_api_v1", error=str(exc),
-        )
-        logger.warning("[live_retriever] Serper exception: %s", exc)
-        _trace_query("serper", query, [])
-        return []
-    organic = data.get("organic", []) or []
-    out: list[dict[str, Any]] = []
-    for item in organic:
-        out.append({
-            "url": item.get("link", ""),
-            "title": item.get("title", ""),
-            "snippet": item.get("snippet", ""),
-            "source": "serper",
-        })
+            logger.warning("[live_retriever] Serper page %d failed for %r: %s",
+                           _page, query[:60], _last_err)
+            break  # fail-open: keep pages already accumulated; do not discard.
+        _pages_fetched += 1
+        _new = 0
+        for it in items:
+            u = it.get("url", "")
+            if u and u not in seen:
+                seen.add(u)
+                out.append(it)
+                _new += 1
+        if len(out) >= _total or len(items) < per_page:
+            break  # budget met, or the provider has no more results for this query.
     _trace_tool(
-        "serper", target=query, status="ok", latency_ms=_latency_ms,
-        bytes_sent=_bytes_sent,
-        bytes_received=_resp_content_len(r),
+        "serper", target=query, status="ok" if out or not _last_err else "fail",
+        latency_ms=_last_latency, bytes_sent=len(query), bytes_received=_last_bytes,
         backend_used="serper_api_v1", result_count=len(out),
+        pages_fetched=_pages_fetched, num_requested=num, per_page=per_page,
+        page_max=_SERPER_PAGE_MAX, clamped=_clamped, total_budget=_total,
     )
     _trace_query("serper", query, [o["url"] for o in out])
     return out
diff --git a/tests/polaris_graph/test_fx17_serper_pagination_iready017.py b/tests/polaris_graph/test_fx17_serper_pagination_iready017.py
new file mode 100644
index 00000000..e0ec48f9
--- /dev/null
+++ b/tests/polaris_graph/test_fx17_serper_pagination_iready017.py
@@ -0,0 +1,75 @@
+"""FX-17 (I-ready-017 #1126): Serper visible clamp + pagination to a total-URL budget.
+
+The old `_serper_search` silently floored `num` to 20 (no warning) and never paginated. FX-17 makes
+the clamp loud and adds `page`-param pagination up to `PG_SERPER_TOTAL_PER_QUERY` (default = one page
+= byte-identical), bounded by `PG_SERPER_MAX_PAGES`, early-stopping on a short page. Discovery-breadth
+only — all new URLs pass the same downstream gates. Offline (page helper mocked), no network.
+"""
+from __future__ import annotations
+
+import logging
+
+import src.polaris_graph.retrieval.live_retriever as lr
+
+
+def _install_pages(monkeypatch, pages: dict[int, list[str]]):
+    """Mock `_serper_fetch_page` to return synthetic items per page; record requested pages."""
+    calls: list[int] = []
+
+    def _fake(query, per_page, page, headers):
+        calls.append(page)
+        urls = pages.get(page, [])
+        items = [{"url": u, "title": "t", "snippet": "s", "source": "serper"} for u in urls]
+        return items, True, 1.0, 100, ""
+
+    monkeypatch.setattr(lr, "_serper_fetch_page", _fake)
+    monkeypatch.setenv("SERPER_API_KEY", "test-key")
+    return calls
+
+
+def test_default_single_page_byte_identical(monkeypatch):
+    monkeypatch.delenv("PG_SERPER_TOTAL_PER_QUERY", raising=False)
+    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(10)]})
+    out = lr._serper_search("q", num=10)
+    assert calls == [1]                      # exactly one page, no pagination by default
+    assert len(out) == 10
+
+
+def test_num_over_page_max_warns_and_clamps(monkeypatch, caplog):
+    monkeypatch.delenv("PG_SERPER_TOTAL_PER_QUERY", raising=False)
+    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(20)]})
+    with caplog.at_level(logging.WARNING):
+        out = lr._serper_search("q", num=100)   # 100 > page max 20
+    assert any("exceeds the page max" in r.message for r in caplog.records)
+    assert calls == [1]                       # default budget = per_page (20) -> still 1 page
+    assert len(out) == 20
+
+
+def test_pagination_accumulates_and_dedups(monkeypatch):
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "40")
+    p1 = [f"https://x/{i}" for i in range(20)]
+    p2 = [f"https://x/{i}" for i in range(19, 39)]  # one URL (x/19) overlaps p1
+    calls = _install_pages(monkeypatch, {1: p1, 2: p2})
+    out = lr._serper_search("q", num=20)
+    assert calls == [1, 2]                     # paginated to the budget
+    urls = [o["url"] for o in out]
+    assert len(urls) == len(set(urls))         # deduped
+    assert len(out) == 39                       # 20 + 20 - 1 overlap
+
+
+def test_early_stop_on_short_page(monkeypatch):
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
+    calls = _install_pages(monkeypatch, {1: [f"https://x/{i}" for i in range(5)]})  # < per_page
+    out = lr._serper_search("q", num=20)
+    assert calls == [1]                        # short page -> no further pages
+    assert len(out) == 5
+
+
+def test_max_pages_cap_respected(monkeypatch):
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "200")
+    monkeypatch.setenv("PG_SERPER_MAX_PAGES", "2")
+    pages = {p: [f"https://x/{p}-{i}" for i in range(20)] for p in range(1, 6)}
+    calls = _install_pages(monkeypatch, pages)
+    out = lr._serper_search("q", num=20)
+    assert calls == [1, 2]                      # capped at PG_SERPER_MAX_PAGES even though budget=200
+    assert len(out) == 40
```
