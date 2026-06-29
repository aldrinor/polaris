HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
Front-load ALL real findings. Reserve P0/P1 for real execution risks.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST. Do NOT run pytest. Review ONLY this diff to scripts/dr_benchmark/run_gate_b.py.

CONTEXT: POLARIS Gate-B benchmark harness. A real run aborted pre-spend ($0) when the pre-spend OpenRouter catalog probe got a TRANSIENT HTTP 408 and crashed the whole run (no retry). Separately, the --smoke-scale run-wall (3600) risked guillotining mid-back-half on the first authorized smoke.

TWO CHANGES IN THIS DIFF:
1) `_fetch_openrouter_catalog` (~331): wrap the GET in a bounded retry loop — retry on transient HTTP {408,425,429,500,502,503,504} and on httpx.HTTPError transport faults, with capped exponential backoff (2*2^attempt, cap 30s), PG_PREFLIGHT_CATALOG_RETRIES (default 5). A genuine persistent non-200 / transport fault STILL fails LOUD after the retries. A local `import time` was added (the module has NO top-level `import time`).
2) `_SMOKE_SCALE_OVERRIDES`: raise PG_RUN_WALL_CLOCK_SEC 3600->5400 and add PG_CREDIBILITY_PASS_WALL_S=600 (smoke-only; the full paid slate is untouched).

VERIFY ONLY:
1. RETRY CORRECTNESS: after the loop, `response` is always the OK response on the non-exception path (a transient status on the LAST attempt falls through to the LOUD raise, not a silent `continue`; a transport error on the last attempt raises). No path leaves `response` undefined before `body = response.json()`. The injected MockTransport test client (http_client != None) returns 200 on attempt 0 so behavior is byte-identical for tests. `own_client` is still closed in `finally` exactly once. `time` is in scope (local import). The backoff cannot busy-spin (sleeps only between attempts, not after the last).
2. NO INFINITE LOOP / NO UNBOUNDED SLEEP: attempts are bounded by _catalog_retries (>=1, parse-guarded); total worst-case added latency is acceptable for a pre-spend probe.
3. SMOKE WALL COHERENCE: 5400 keeps seam 1800 < run-wall and retrieval 1200 < run-wall (passes the coherence preflight at ~2424 which is `and not smoke_scale`-exempt anyway); PG_CREDIBILITY_PASS_WALL_S=600 < 5400. Paid slate (PG_RUN_WALL_CLOCK_SEC stays 10800 on the full path) is byte-identical.
4. FAITHFULNESS-NEUTRAL: both changes are pre-spend liveness + timeout-budget only; no faithfulness gate, no spend logic, no model selection touched.
5. NO NEW P0/P1 (undefined name, wrong indentation, double-close, swallowed real error).

If correct, APPROVE. If a real NEW P0/P1, REQUEST_CHANGES with exact file:line.

OUTPUT EXACTLY THIS SCHEMA (LAST line starts with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

=== DIFF ===
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index efb09ee2..24918418 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -339,15 +339,43 @@ def _fetch_openrouter_catalog(http_client: httpx.Client | None = None) -> list[d
     url = f"{openrouter_base_url()}{_OPENROUTER_MODELS_PATH}"
     own_client = http_client is None
     client = http_client or httpx.Client(timeout=_TIMEOUT_SECONDS)
+    # I-deepfix-001 (#1344): the pre-spend catalog probe must ride out a TRANSIENT OpenRouter
+    # hiccup (HTTP 408/425/429/5xx or a connect/read timeout) instead of crashing the whole run to
+    # a $0 abort on a single blip (observed: a lone 408 killed the run before retrieval started).
+    # Bounded retry with capped exponential backoff; a GENUINE persistent failure STILL fails LOUD
+    # (LAW II). Faithfulness-neutral (pre-spend liveness probe only, no spend, no gate touched).
+    # PG_PREFLIGHT_CATALOG_RETRIES (default 5); the injected MockTransport test path returns 200 on
+    # the first attempt so it is byte-identical.
+    import time  # local import — module has no top-level `time` (mirrors the local imports elsewhere)
     try:
-        response = client.get(url, timeout=_TIMEOUT_SECONDS)
+        _catalog_retries = max(1, int(os.getenv("PG_PREFLIGHT_CATALOG_RETRIES", "5")))
+    except (TypeError, ValueError):
+        _catalog_retries = 5
+    _transient_status = {408, 425, 429, 500, 502, 503, 504}
+    try:
+        for _attempt in range(_catalog_retries):
+            try:
+                response = client.get(url, timeout=_TIMEOUT_SECONDS)
+            except httpx.HTTPError as _exc:  # connect / read / pool timeout — transient transport fault
+                if _attempt < _catalog_retries - 1:
+                    time.sleep(min(2.0 * (2 ** _attempt), 30.0))
+                    continue
+                raise RuntimeError(
+                    f"OpenRouter catalog preflight: GET {url} transport error after "
+                    f"{_catalog_retries} attempts: {_exc}"
+                ) from _exc
+            if response.status_code == httpx.codes.OK:
+                break
+            if response.status_code in _transient_status and _attempt < _catalog_retries - 1:
+                time.sleep(min(2.0 * (2 ** _attempt), 30.0))
+                continue
+            raise RuntimeError(
+                f"OpenRouter catalog preflight: GET {url} returned HTTP {response.status_code}"
+                + (f" after {_attempt + 1} attempts" if _attempt else "")
+            )
     finally:
         if own_client:
             client.close()
-    if response.status_code != httpx.codes.OK:
-        raise RuntimeError(
-            f"OpenRouter catalog preflight: GET {url} returned HTTP {response.status_code}"
-        )
     body = response.json()
     data = body.get("data")
     if not isinstance(data, list):
@@ -2266,7 +2294,13 @@ _SMOKE_SCALE_OVERRIDES: dict[str, str] = {
     "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "600",   # per generator call (10 min) — synced to live module below
     "PG_SECTION_WALLCLOCK_SECONDS": "900",       # per section (15 min)
     "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "1800", # 4-role D8 seam (30 min)
-    "PG_RUN_WALL_CLOCK_SEC": "3600",             # OUTER backstop (60 min) — retrieval 1200 + back-half 2400
+    # I-deepfix-001 (#1344) back-half headroom: the first authorized smoke must fit retrieval (1200) +
+    # tiering + adequacy/CRAG + generation + strict_verify + the 4-role seam (1800) inside the run-wall.
+    # 3600 risked guillotining mid-back-half (error_unexpected, no report); 5400 keeps seam 1800 <
+    # run-wall and retrieval 1200 < run-wall (passes the coherence preflight). Also pin the credibility
+    # pass wall coherent with the smoke (the full slate force-exacts 3000, incoherent vs a 5400 run-wall).
+    "PG_RUN_WALL_CLOCK_SEC": "5400",             # OUTER backstop (90 min) — retrieval 1200 + back-half ~4200
+    "PG_CREDIBILITY_PASS_WALL_S": "600",         # smoke credibility-pass wall (10 min) — < run-wall, coherent
     # modest cost cap for a smoke (synced to the live module below)
     "PG_MAX_COST_PER_RUN": "10",
     # CORRECTNESS (not scale-down): the GLM-5.1 Mirror blanks at xhigh effort and STALLS the 4-role
```
