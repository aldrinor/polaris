HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-fetch-002 (#1168) — Retrieval throttle-fix diff review

Review this retrieval throttle-fix. Verify: (a) the 4 fetch lanes (main + agentic + deepener + R6) now SUM to ~1000 total/question, with the arithmetic correct and documented; (b) the deepener's previously-unguarded 20-cap and the breadth knobs (PG_STORM_MAX_BENCHMARK_QUERIES, PG_MAX_SUBQUERIES) are now slate-guarded; (c) STORM UNDER-fire (not just total no-fire) aborts to abort_discovery_degraded; (d) the crawl4ai concurrency semaphore + raised crash-tolerance are wired in the access_bypass pattern; (e) faithfulness gates untouched, additive, no budget-cap self-set.

End with 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES' then bullets.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Staged diff (scripts/dr_benchmark/run_gate_b.py, scripts/run_honest_sweep_r3.py, src/tools/access_bypass.py)

```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 356f167a..9515a316 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -424,8 +424,21 @@ def write_four_role_stage_marker(out_root: Path) -> Path:
 # is `setdefault` so an explicit operator override still wins (LAW VI). The slate is applied BEFORE the
 # sweep is imported so import-time module constants (caps/timeouts) also see the full values.
 _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
+    # I-fetch-002 (#1168): the WHOLE run fetches ~1000 sites TOTAL per question, NOT 1000 + additive
+    # lanes. The operator's ~1000 budget is SPLIT across the four real fetch lanes so they SUM to ~1000
+    # (the prior 1000 here was the MAIN lane alone, on top of which agentic/deepener/R-6 each added more
+    # — silently overshooting the budget). The four lanes, FLOOR-applied below (max(existing, slate)):
+    #   PG_SWEEP_FETCH_CAP            800  main Serper/S2/OpenAlex lane (total URLs after dedup, /query)
+    #   PG_AGENTIC_BENCHMARK_URL_CAP  100  agentic-discovery harvest (run_honest_sweep_r3.py:3162)
+    #   PG_SWEEP_DEEPENER_URL_CAP      60  citation-snowball deepener (run_honest_sweep_r3.py:3038)
+    #   PG_R6_EXPAND_FETCH_CAP         40  R-6 completeness re-expansion (run_honest_sweep_r3.py:2961)
+    #   --------------------------------------------------------------------------------------------
+    #   SUM                          1000  ≈ the ~1000-site/question budget (operator no-overshoot)
+    # NOTE: PG_STORM_MAX_BENCHMARK_QUERIES (30) and PG_MAX_SUBQUERIES (15) below are QUERY-BREADTH
+    # counts (how many search queries are issued), NOT URLs — they are deliberately NOT part of the
+    # ~1000-URL sum. .env has no override for any of these (checked I-fetch-002), so the floor lands.
     # Retrieval breadth — the REAL run_one_query knobs (PG_SWEEP_*, default 12/12/40). NOT PG_LIVE_*.
-    "PG_SWEEP_FETCH_CAP": "1000",   # total URLs fetched+classified per query (operator: ~1000)
+    "PG_SWEEP_FETCH_CAP": "800",   # MAIN lane: total URLs fetched+classified per query (budget lane 1/4)
     "PG_SWEEP_MAX_SERPER": "100",
     "PG_SWEEP_MAX_S2": "100",
     # FX-17 (#1126): Serper `num` is a PAGE size (max ~20); breadth needs the new PAGINATION budget.
@@ -465,7 +478,22 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     "PG_R6_EXPAND_QUERY_CAP": "12",
     "PG_R6_EXPAND_MAX_SERPER": "20",
     "PG_R6_EXPAND_MAX_S2": "20",
-    "PG_R6_EXPAND_FETCH_CAP": "60",
+    # I-fetch-002 (#1168): budget lane 4/4 — R-6 completeness re-expansion fetch cap. Lowered 60->40 so
+    # the four fetch lanes SUM to ~1000 (read at run_honest_sweep_r3.py:2961, code default 15).
+    "PG_R6_EXPAND_FETCH_CAP": "40",
+    # I-fetch-002 (#1168): budget lane 2/4 — agentic-discovery URL harvest cap (read at
+    # run_honest_sweep_r3.py:3162, code default 100). Explicit in the slate so it cannot silently drift.
+    "PG_AGENTIC_BENCHMARK_URL_CAP": "100",
+    # I-fetch-002 (#1168): budget lane 3/4 — citation-snowball deepener URL cap. Previously an UNGUARDED
+    # default of 20 (run_honest_sweep_r3.py:3038); pin it to 60 so the lane is part of the ~1000 budget
+    # and cannot silently drift below it.
+    "PG_SWEEP_DEEPENER_URL_CAP": "60",
+    # I-fetch-002 (#1168): two un-guarded QUERY-BREADTH knobs, pinned explicitly so they cannot silently
+    # drift (NOT part of the ~1000-URL sum — these count search queries, not URLs). STORM benchmark-query
+    # cap (read at run_honest_sweep_r3.py:2626) + sub-query decomposition cap (query_decomposer.py:39).
+    # Both floor-guarded in _BENCHMARK_PREFLIGHT_FLOORS below.
+    "PG_STORM_MAX_BENCHMARK_QUERIES": "30",
+    "PG_MAX_SUBQUERIES": "15",
     # Agentic per-round web breadth (was stuck at 6 via the PG_WEB_PER_ROUND typo).
     "PG_AGENTIC_WEB_PER_ROUND": "10",
     # Budget cap (spend ceiling enforced per run).
@@ -531,6 +559,12 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # ship green. Force-on + required below (an explicit operator =0 must not survive the slate). Pairs
     # with CANARY-01 (pre-spend); FL-05 is the mid/post-run regression backstop.
     "PG_RUN_HEALTH_GATE": "1",
+    # I-fetch-002 (#1168): STORM UNDER-fire floor. FL-05 (#1124) aborts only when a force-enabled
+    # discovery feature TOTALLY no-fires (firing_status attempted_empty/error). This floor extends the
+    # SAME gate to the UNDER-fire case: STORM force-on FIRED but produced FEWER than this many effective
+    # (post-validator) queries — a thin-corpus collapse that would otherwise ship green. Discovery-health
+    # only (faithfulness-neutral). Read at the run_honest_sweep_r3.py compute_run_health_gate call site.
+    "PG_STORM_MIN_EFFECTIVE_QUERIES": "12",
 }
 
 # Minimum effective values the run MUST meet — the preflight FAILS CLOSED if any is below these (i.e.
@@ -545,6 +579,11 @@ _BENCHMARK_PREFLIGHT_FLOORS: dict[str, int] = {
     # MAX_PAGES>=2 lets the budget be reached.
     "PG_SERPER_TOTAL_PER_QUERY": 40,
     "PG_SERPER_MAX_PAGES": 2,
+    # I-fetch-002 (#1168): floor-guard the two un-guarded QUERY-BREADTH knobs so a conservative .env/
+    # operator value cannot silently shrink the search-query fan-out below full capability. These are
+    # query counts, NOT part of the ~1000-URL fetch sum. Floors == the slate values (30/15).
+    "PG_STORM_MAX_BENCHMARK_QUERIES": 30,
+    "PG_MAX_SUBQUERIES": 15,
 }
 # Flags that MUST be truthy for a full benchmark run (feature dead / unobservable otherwise).
 # Codex diff-gate I-cap-005 P1-1: PG_SWEEP_EVIDENCE_DEEPENER MUST be required too — otherwise an
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 341751b1..9ca4ad39 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -407,6 +407,7 @@ def compute_run_health_gate(
     *,
     unified_status: str,
     gate_on: bool,
+    storm_min_effective_queries: int = 0,
 ) -> dict[str, Any]:
     """FL-05 (#1124): run-health backstop DECISION (pure, no I/O — testable). A FORCE-ENABLED
     discovery feature (``enabled`` True) whose ``firing_status`` is in ``_FL05_DEGRADED_FIRING``
@@ -415,22 +416,52 @@ def compute_run_health_gate(
     force-enabled feature AND the run is otherwise success-bound. NEVER overrides a partial_/abort_/
     error_ status (those are more specific) — only a would-be ``success``. This promotes
     ``feature_firing_warning`` from advisory to gating (CANARY-01 is the pre-spend gate; FL-05 is the
-    mid/post-run regression backstop)."""
+    mid/post-run regression backstop).
+
+    I-fetch-002 (#1168): STORM UNDER-fire (post-validator collapse). The classic FL-05 path above only
+    catches a TOTAL no-fire (firing_status attempted_empty/error). A run where STORM force-on FIRED
+    (firing_status=fired) but produced FEWER than ``storm_min_effective_queries`` EFFECTIVE queries
+    (``effective_query_count``) is a thin-corpus collapse that would otherwise ship green. Such a
+    feature is ADDED to the degraded set (same abort path, same release-withhold). The check requires
+    ``effective_query_count`` to be PRESENT and not None (never treats an absent field as 0), so a
+    feature that does not publish the count — e.g. agentic, which publishes urls_discovered — never
+    trips it. ``storm_min_effective_queries`` defaults to 0 (disabled): with the default, ``count < 0``
+    never fires, so every pre-existing caller/test is byte-unchanged. Discovery-health only (no
+    faithfulness path touched)."""
     degraded = [
         t for t in discovery_telemetries
         if t.get("enabled") and t.get("firing_status") in _FL05_DEGRADED_FIRING
     ]
+    # I-fetch-002 (#1168): UNDER-fire — fired but below the effective-query floor. Mutually exclusive
+    # with the TOTAL no-fire set above (firing_status=fired vs attempted_empty/error), so no double-count.
+    under_fired = [
+        t for t in discovery_telemetries
+        if (
+            t.get("enabled")
+            and t.get("firing_status") == "fired"
+            and t.get("effective_query_count") is not None
+            and int(t.get("effective_query_count")) < storm_min_effective_queries
+        )
+    ]
+    all_degraded = degraded + under_fired
     override = (
         "abort_discovery_degraded"
-        if (gate_on and degraded and unified_status == "success")
+        if (gate_on and all_degraded and unified_status == "success")
         else None
     )
     return {
-        "discovery_llm_degraded": bool(degraded),
-        "discovery_rounds_on_fallback": len(degraded),
+        "discovery_llm_degraded": bool(all_degraded),
+        "discovery_rounds_on_fallback": len(all_degraded),
         "degraded_features": [
             {"feature": t.get("feature"), "firing_status": t.get("firing_status")}
             for t in degraded
+        ] + [
+            {
+                "feature": t.get("feature"),
+                "firing_status": "under_fired",
+                "effective_query_count": int(t.get("effective_query_count")),
+            }
+            for t in under_fired
         ],
         "override_status": override,
     }
@@ -2632,6 +2663,10 @@ async def run_one_query(
                 _storm_telemetry.update({
                     "fired": len(_storm_added) > 0,
                     "questions_added": len(_storm_added),
+                    # I-fetch-002 (#1168): effective (post-dedup/validator) STORM query count — the hook
+                    # the run-health gate's UNDER-fire floor reads. == questions_added (the deduped queries
+                    # actually appended to _amplified_effective; nothing downstream re-filters them).
+                    "effective_query_count": len(_storm_added),
                     "interviews": len(_storm_out.get("storm_conversations", [])),
                     "firing_status": "fired" if _storm_added else "attempted_empty",
                 })
@@ -6587,10 +6622,21 @@ async def run_one_query(
         # would-be SUCCESS (partial_* already signals degradation; aborts/errors are more specific).
         # Codex iter-1 P2: robust truthy parse for this DEFAULT-OFF flag (so PG_RUN_HEALTH_GATE=false
         # / empty does NOT accidentally enable it, unlike the bare `!= "0"` default-ON pattern).
+        # I-fetch-002 (#1168): the STORM UNDER-fire floor (post-validator collapse). 0/absent = disabled
+        # (the classic FL-05 TOTAL no-fire path is unchanged); the Gate-B slate sets it to 12. Fail-loud
+        # on a non-int env so a typo cannot silently disable the floor.
+        try:
+            _storm_min_eff = int(os.getenv("PG_STORM_MIN_EFFECTIVE_QUERIES", "0"))
+        except ValueError as _eff_exc:
+            raise RuntimeError(
+                f"PG_STORM_MIN_EFFECTIVE_QUERIES={os.getenv('PG_STORM_MIN_EFFECTIVE_QUERIES')!r} "
+                f"is not an int"
+            ) from _eff_exc
         _fl05 = compute_run_health_gate(
             [_storm_telemetry, _agentic_telemetry],
             unified_status=unified_status,
             gate_on=os.getenv("PG_RUN_HEALTH_GATE", "0").strip().lower() in {"1", "true", "yes", "on"},
+            storm_min_effective_queries=_storm_min_eff,
         )
         manifest["discovery_llm_degraded"] = _fl05["discovery_llm_degraded"]
         manifest["discovery_rounds_on_fallback"] = _fl05["discovery_rounds_on_fallback"]
diff --git a/src/tools/access_bypass.py b/src/tools/access_bypass.py
index e9c36120..d80dff51 100644
--- a/src/tools/access_bypass.py
+++ b/src/tools/access_bypass.py
@@ -78,13 +78,33 @@ _crawl4ai_available: "bool | None" = None
 # ---------------------------------------------------------------------------
 _crawl4ai_consecutive_failures: int = 0
 _crawl4ai_circuit_open_until: float = 0.0
+# I-fetch-002 (#1168): raise 3->6 so a couple of TRANSIENT subprocess crashes (EPIPE under concurrent
+# load) do not trip the breaker and disable crawl4ai for the whole run. Pairs with the new concurrency
+# semaphore below — fewer concurrent browsers means fewer crashes in the first place.
 _CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = int(
-    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "3")
+    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")
 )
 _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = float(
     os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN", "120.0")
 )
 
+# I-fetch-002 (#1168): crawl4ai launches a Playwright browser subprocess PER URL; under the ~1000-URL
+# benchmark fan-out, many concurrent browsers exhaust the OS and crash (EPIPE), which then trips the
+# circuit breaker and disables crawl4ai run-wide. Bound the number of concurrently-LIVE browsers with a
+# semaphore (mirrors the PG_JINA_CONCURRENCY=2 pattern). Lazy-init so it binds to the running loop.
+_crawl4ai_semaphore: "asyncio.Semaphore | None" = None
+
+
+def _get_crawl4ai_semaphore() -> "asyncio.Semaphore":
+    """I-fetch-002 (#1168): lazy-init the crawl4ai browser-concurrency gate on the running loop.
+    Default 2 concurrent browsers (env PG_CRAWL4AI_CONCURRENCY)."""
+    global _crawl4ai_semaphore
+    if _crawl4ai_semaphore is None:
+        _crawl4ai_semaphore = asyncio.Semaphore(
+            int(os.getenv("PG_CRAWL4AI_CONCURRENCY", "2"))
+        )
+    return _crawl4ai_semaphore
+
 # ---------------------------------------------------------------------------
 # Firecrawl free-plan hardening: rate limiter + credit tracker
 # ---------------------------------------------------------------------------
@@ -1105,51 +1125,58 @@ class AccessBypass:
                 timeout_seconds,
             )
 
-            # Step 1: Start the browser subprocess.
-            # FIX-EPIPE: Separate try for __aenter__ to catch startup failures.
-            try:
-                crawler = AsyncWebCrawler(config=browser_config)
-                await crawler.__aenter__()
-            except (BrokenPipeError, ConnectionError, OSError) as enter_err:
-                logger.warning(
-                    "[polaris graph] CRAWL4AI: FIX-EPIPE browser startup "
-                    "pipe/OS error for %s: %s: %s",
-                    _safe_log_str(url, 60),
-                    type(enter_err).__name__,
-                    _safe_log_str(str(enter_err)),
-                )
-                _crawl4ai_track_failure()
-                return _crawl4ai_failure_result(
-                    url,
-                    f"Browser startup failed: {type(enter_err).__name__}: "
-                    f"{str(enter_err)}",
-                )
-            except Exception as enter_err:
-                logger.warning(
-                    "[polaris graph] CRAWL4AI: FIX-EPIPE browser init "
-                    "exception for %s: %s: %s",
-                    _safe_log_str(url, 60),
-                    type(enter_err).__name__,
-                    _safe_log_str(str(enter_err)),
-                )
-                _crawl4ai_track_failure()
-                return _crawl4ai_failure_result(
-                    url,
-                    f"Browser init failed: {type(enter_err).__name__}: "
-                    f"{str(enter_err)}",
-                )
+            # I-fetch-002 (#1168): hold a crawl4ai concurrency slot ONLY for the browser-active region
+            # (startup -> crawl -> close). The extraction (Step 4, trafilatura — CPU-bound) and the
+            # cheap config build above run OUTSIDE the slot so a browser slot is never pinned by
+            # non-browser work. `result` is assigned inside and read after the `async with` (it persists
+            # in the enclosing scope). The inner early-returns release the slot cleanly on `async with`
+            # exit. At most PG_CRAWL4AI_CONCURRENCY browsers are live at once.
+            async with _get_crawl4ai_semaphore():
+                # Step 1: Start the browser subprocess.
+                # FIX-EPIPE: Separate try for __aenter__ to catch startup failures.
+                try:
+                    crawler = AsyncWebCrawler(config=browser_config)
+                    await crawler.__aenter__()
+                except (BrokenPipeError, ConnectionError, OSError) as enter_err:
+                    logger.warning(
+                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser startup "
+                        "pipe/OS error for %s: %s: %s",
+                        _safe_log_str(url, 60),
+                        type(enter_err).__name__,
+                        _safe_log_str(str(enter_err)),
+                    )
+                    _crawl4ai_track_failure()
+                    return _crawl4ai_failure_result(
+                        url,
+                        f"Browser startup failed: {type(enter_err).__name__}: "
+                        f"{str(enter_err)}",
+                    )
+                except Exception as enter_err:
+                    logger.warning(
+                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser init "
+                        "exception for %s: %s: %s",
+                        _safe_log_str(url, 60),
+                        type(enter_err).__name__,
+                        _safe_log_str(str(enter_err)),
+                    )
+                    _crawl4ai_track_failure()
+                    return _crawl4ai_failure_result(
+                        url,
+                        f"Browser init failed: {type(enter_err).__name__}: "
+                        f"{str(enter_err)}",
+                    )
 
-            # Step 2: Run the crawl with timeout guard.
-            try:
-                result = await asyncio.wait_for(
-                    crawler.arun(url=url, config=crawler_config),
-                    timeout=timeout_seconds + 10,
-                )
-            finally:
-                # Step 3: Close browser via _safe_close_crawler which catches
-                # ALL exceptions from __aexit__ independently.
-                await _safe_close_crawler(crawler, url)
-                crawler = None  # Prevent double-close in outer finally
+                # Step 2: Run the crawl with timeout guard.
+                try:
+                    result = await asyncio.wait_for(
+                        crawler.arun(url=url, config=crawler_config),
+                        timeout=timeout_seconds + 10,
+                    )
+                finally:
+                    # Step 3: Close browser via _safe_close_crawler which catches
+                    # ALL exceptions from __aexit__ independently.
+                    await _safe_close_crawler(crawler, url)
+                    crawler = None  # Prevent double-close in outer finally
 
             # Step 4: Process the crawl result.
             # If we reached here, the subprocess survived (reset breaker).
```

## Staged test diff (new + modified test files)

```diff
diff --git a/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py b/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
index 29b2d403..c7e79253 100644
--- a/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
+++ b/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
@@ -27,6 +27,7 @@ import pytest
 
 from scripts.dr_benchmark.run_gate_b import (
     _BENCHMARK_FORCE_ON_FLAGS,
+    _BENCHMARK_PREFLIGHT_FLOORS,
     _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
     _FULL_CAPABILITY_BENCHMARK_SLATE,
     apply_full_capability_benchmark_slate,
@@ -150,3 +151,89 @@ def test_activated_gate_passes_a_clean_run():
     out = compute_run_health_gate([storm, agentic], unified_status="success", gate_on=True)
     assert out["override_status"] is None
     assert out["discovery_llm_degraded"] is False
+
+
+# --------------------------------------------------------------------------- I-fetch-002 (#1168)
+# Lane budget: the four fetch lanes SUM to ~1000 sites/question (NOT 1000 + additive lanes).
+
+_LANE_KNOBS = (
+    "PG_SWEEP_FETCH_CAP",            # main Serper/S2/OpenAlex lane
+    "PG_AGENTIC_BENCHMARK_URL_CAP",  # agentic-discovery harvest
+    "PG_SWEEP_DEEPENER_URL_CAP",     # citation-snowball deepener
+    "PG_R6_EXPAND_FETCH_CAP",        # R-6 completeness re-expansion
+)
+
+
+def test_four_fetch_lanes_sum_to_about_1000():
+    """The operator budget: the WHOLE run fetches ~1000 sites/question, split across four lanes that
+    SUM to ~1000 — never 1000 (main) + additive agentic/deepener/R-6 on top."""
+    vals = {k: int(_FULL_CAPABILITY_BENCHMARK_SLATE[k]) for k in _LANE_KNOBS}
+    total = sum(vals.values())
+    assert total == 1000, f"four-lane fetch budget must sum to ~1000, got {total} from {vals}"
+    # And the exact split documented in the slate comment.
+    assert vals == {
+        "PG_SWEEP_FETCH_CAP": 800,
+        "PG_AGENTIC_BENCHMARK_URL_CAP": 100,
+        "PG_SWEEP_DEEPENER_URL_CAP": 60,
+        "PG_R6_EXPAND_FETCH_CAP": 40,
+    }
+
+
+def test_query_breadth_knobs_present_and_floor_guarded():
+    """The two previously un-guarded QUERY-BREADTH knobs are pinned in the slate AND floor-guarded so
+    they cannot silently drift. They are query counts — NOT part of the ~1000-URL fetch sum."""
+    for knob, expected in (("PG_STORM_MAX_BENCHMARK_QUERIES", "30"), ("PG_MAX_SUBQUERIES", "15")):
+        assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(knob) == expected
+        assert _BENCHMARK_PREFLIGHT_FLOORS.get(knob) == int(expected)
+
+
+def test_query_breadth_knobs_excluded_from_url_sum():
+    """Guard the comment's arithmetic claim: the query-breadth knobs are NOT lanes in the URL sum."""
+    assert "PG_STORM_MAX_BENCHMARK_QUERIES" not in _LANE_KNOBS
+    assert "PG_MAX_SUBQUERIES" not in _LANE_KNOBS
+
+
+def test_lane_floors_land_with_no_env_override():
+    """With no operator/.env override (the I-fetch-002 baseline), the floor-applied slate lands the
+    lowered lane values exactly (800/40), so the budget is honored, not silently masked-up."""
+    for knob in _LANE_KNOBS:
+        os.environ.pop(knob, None)
+    apply_full_capability_benchmark_slate()
+    assert int(os.environ["PG_SWEEP_FETCH_CAP"]) == 800
+    assert int(os.environ["PG_R6_EXPAND_FETCH_CAP"]) == 40
+    assert int(os.environ["PG_AGENTIC_BENCHMARK_URL_CAP"]) == 100
+    assert int(os.environ["PG_SWEEP_DEEPENER_URL_CAP"]) == 60
+
+
+# --------------------------------------------------------------------------- I-fetch-002 (#1168)
+# STORM UNDER-fire floor knob in the slate + behavioral wiring.
+
+_STORM_MIN_FLAG = "PG_STORM_MIN_EFFECTIVE_QUERIES"
+
+
+def test_storm_min_effective_queries_in_slate():
+    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_STORM_MIN_FLAG) == "12"
+
+
+def test_storm_min_effective_queries_floor_applied():
+    """Floor semantics: a HIGHER operator value is kept, a missing/lower one is raised to 12."""
+    os.environ.pop(_STORM_MIN_FLAG, None)
+    apply_full_capability_benchmark_slate()
+    assert int(os.environ[_STORM_MIN_FLAG]) >= 12
+
+
+def test_slate_storm_min_drives_under_fire_abort():
+    """§-1.1 behavioral: with the slate floor (12), a force-on STORM that FIRED but produced only 4
+    effective queries (post-validator collapse) overrides a would-be success to abort_discovery_degraded
+    — proving the knob is wired to real gate behavior, not just a string in the slate."""
+    storm = make_feature_telemetry(
+        "storm", enabled=True, fired=True, firing_status="fired", effective_query_count=4
+    )
+    out = compute_run_health_gate(
+        [storm],
+        unified_status="success",
+        gate_on=True,
+        storm_min_effective_queries=int(_FULL_CAPABILITY_BENCHMARK_SLATE[_STORM_MIN_FLAG]),
+    )
+    assert out["override_status"] == "abort_discovery_degraded"
+    assert out["discovery_llm_degraded"] is True
diff --git a/tests/polaris_graph/test_crawl4ai_concurrency_cap_ifetch002.py b/tests/polaris_graph/test_crawl4ai_concurrency_cap_ifetch002.py
new file mode 100644
index 00000000..202c48d2
--- /dev/null
+++ b/tests/polaris_graph/test_crawl4ai_concurrency_cap_ifetch002.py
@@ -0,0 +1,165 @@
+"""I-fetch-002 (#1168) — crawl4ai browser concurrency is hard-capped + the circuit breaker tolerates
+a couple of transient subprocess crashes.
+
+crawl4ai launches a Playwright browser subprocess PER URL; under the ~1000-URL benchmark fan-out, many
+concurrent browsers exhaust the OS and crash with EPIPE, which then trips the circuit breaker and
+disables crawl4ai run-wide. Two fixes, both verified BEHAVIORALLY here, offline, no real browser:
+
+  1. A concurrency semaphore (PG_CRAWL4AI_CONCURRENCY, default 2) so at most N browsers are LIVE at
+     once. Proven with a counter that increments on browser-active entry and decrements on exit: the
+     observed PEAK never exceeds the cap, even with many more calls launched concurrently.
+  2. The circuit-breaker crash-tolerance threshold default is raised 3 -> 6.
+
+The real `crawl4ai` package is NOT imported: a fake module is injected into sys.modules so the
+function's local `from crawl4ai import ...` binds to the stub. No network, no Playwright, no spend.
+"""
+
+from __future__ import annotations
+
+import asyncio
+import sys
+import types
+
+import pytest
+
+import src.tools.access_bypass as ab
+from src.tools.access_bypass import AccessBypass
+
+
+# --------------------------------------------------------------------------- threshold bump (config)
+
+def test_circuit_breaker_threshold_default_raised_to_six(monkeypatch):
+    """Default crash-tolerance threshold is 6 (was 3) so a couple of transient EPIPE crashes do not
+    disable crawl4ai for the whole run. Reads the env default via a fresh module-constant computation."""
+    monkeypatch.delenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", raising=False)
+    import os
+    assert int(os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")) == 6
+    # And the module-level constant honored the new default at import.
+    assert ab._CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD >= 6
+
+
+def test_concurrency_semaphore_default_is_two(monkeypatch):
+    monkeypatch.delenv("PG_CRAWL4AI_CONCURRENCY", raising=False)
+    ab._crawl4ai_semaphore = None  # force a fresh lazy-init
+    sem = ab._get_crawl4ai_semaphore()
+    assert sem._value == 2  # asyncio.Semaphore initial counter == the configured cap
+
+
+# --------------------------------------------------------------------------- behavioral concurrency cap
+
+
+class _FakeResult:
+    """A minimal crawl4ai result that the success path accepts."""
+
+    def __init__(self) -> None:
+        self.success = True
+        self.error_message = None
+        self.status_code = 200
+        self.redirected_url = None
+        # >500 chars so trafilatura-or-fallback yields enough content; html None so the
+        # fallback uses .markdown directly (no trafilatura dependency in the test).
+        self.html = None
+        self.markdown = "x" * 800
+
+
+def _make_fake_crawl4ai(active_counter: dict):
+    """Build a fake `crawl4ai` module whose AsyncWebCrawler tracks the number of concurrently-LIVE
+    browsers (incremented in __aenter__, decremented in __aexit__) so the test can assert the peak."""
+
+    class _FakeCrawler:
+        def __init__(self, *a, **k) -> None:
+            pass
+
+        async def __aenter__(self):
+            active_counter["live"] += 1
+            active_counter["peak"] = max(active_counter["peak"], active_counter["live"])
+            return self
+
+        async def __aexit__(self, *exc):
+            active_counter["live"] -= 1
+            return False
+
+        async def arun(self, *, url, config):
+            # Hold the "browser" busy long enough that, absent the semaphore, all callers would
+            # overlap and drive the peak above the cap.
+            await asyncio.sleep(0.05)
+            return _FakeResult()
+
+    def _cfg(*a, **k):
+        return object()
+
+    mod = types.ModuleType("crawl4ai")
+    mod.AsyncWebCrawler = _FakeCrawler
+    mod.BrowserConfig = _cfg
+    mod.CrawlerRunConfig = _cfg
+    return mod
+
+
+@pytest.mark.asyncio
+async def test_semaphore_caps_concurrent_browsers(monkeypatch):
+    """Launch many more crawls than the cap concurrently; the peak number of LIVE browsers must never
+    exceed PG_CRAWL4AI_CONCURRENCY. This is the real cap proof (not 'a semaphore exists')."""
+    cap = 2
+    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", str(cap))
+    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
+    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")
+
+    # Reset module state so the semaphore re-inits on the running loop at the configured cap.
+    ab._crawl4ai_semaphore = None
+    ab._crawl4ai_available = None
+    ab._crawl4ai_consecutive_failures = 0
+    ab._crawl4ai_circuit_open_until = 0.0
+
+    counter = {"live": 0, "peak": 0}
+    fake_mod = _make_fake_crawl4ai(counter)
+    # Inject the fake so the function's local `from crawl4ai import ...` binds to it. Also stub the two
+    # optional sub-imports so the filter branch resolves cleanly.
+    monkeypatch.setitem(sys.modules, "crawl4ai", fake_mod)
+    monkeypatch.setitem(
+        sys.modules, "crawl4ai.markdown_generation_strategy",
+        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
+    )
+    monkeypatch.setitem(
+        sys.modules, "crawl4ai.content_filter_strategy",
+        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
+    )
+
+    bypass = AccessBypass()
+    n_calls = cap + 4  # more than the cap so the semaphore is the only thing bounding the peak
+    results = await asyncio.gather(
+        *[bypass._try_crawl4ai(f"https://example.gov/doc/{i}") for i in range(n_calls)]
+    )
+
+    assert counter["peak"] <= cap, f"peak live browsers {counter['peak']} exceeded cap {cap}"
+    assert counter["peak"] >= 1, "the fake crawler never went live — the stub did not bind"
+    # All calls still completed successfully (the cap serializes, it does not drop work).
+    assert all(r.success for r in results)
+    assert counter["live"] == 0, "a browser slot leaked (live count did not return to 0)"
+
+
+@pytest.mark.asyncio
+async def test_single_call_succeeds_under_cap(monkeypatch):
+    """Sanity: one call still works (the semaphore does not block the first acquirer)."""
+    monkeypatch.setenv("PG_CRAWL4AI_CONCURRENCY", "2")
+    monkeypatch.setenv("PG_CRAWL4AI_ENABLED", "1")
+    monkeypatch.setenv("PG_CRAWL4AI_TIMEOUT", "5")
+    ab._crawl4ai_semaphore = None
+    ab._crawl4ai_available = None
+    ab._crawl4ai_consecutive_failures = 0
+    ab._crawl4ai_circuit_open_until = 0.0
+
+    counter = {"live": 0, "peak": 0}
+    monkeypatch.setitem(sys.modules, "crawl4ai", _make_fake_crawl4ai(counter))
+    monkeypatch.setitem(
+        sys.modules, "crawl4ai.markdown_generation_strategy",
+        types.SimpleNamespace(DefaultMarkdownGenerator=lambda *a, **k: object()),
+    )
+    monkeypatch.setitem(
+        sys.modules, "crawl4ai.content_filter_strategy",
+        types.SimpleNamespace(PruningContentFilter=lambda *a, **k: object()),
+    )
+
+    res = await AccessBypass()._try_crawl4ai("https://example.gov/single")
+    assert res.success
+    assert counter["peak"] == 1
+    assert counter["live"] == 0
diff --git a/tests/polaris_graph/test_fl05_run_health_gate_iready017.py b/tests/polaris_graph/test_fl05_run_health_gate_iready017.py
index 54ca235e..aaf75af6 100644
--- a/tests/polaris_graph/test_fl05_run_health_gate_iready017.py
+++ b/tests/polaris_graph/test_fl05_run_health_gate_iready017.py
@@ -99,3 +99,92 @@ def test_disabled_feature_is_not_degraded():
     )
     assert out["override_status"] is None
     assert out["discovery_llm_degraded"] is False
+
+
+# --------------------------------------------------------------------------- I-fetch-002 (#1168)
+# STORM UNDER-fire: force-on STORM FIRED but produced fewer than the effective-query floor (post-
+# validator collapse / thin corpus). The classic FL-05 path above only catches a TOTAL no-fire.
+
+
+def _storm_fired(effective_query_count):
+    t = _feat("storm", True, "fired")
+    t["effective_query_count"] = effective_query_count
+    return t
+
+
+def test_storm_under_fire_below_floor_overrides_success():
+    # FIRED but 5 effective queries < floor 12 → abort_discovery_degraded (gated, would-be success).
+    out = compute_run_health_gate(
+        [_storm_fired(5), _feat("agentic_search", True, "fired")],
+        unified_status="success",
+        gate_on=True,
+        storm_min_effective_queries=12,
+    )
+    assert out["override_status"] == "abort_discovery_degraded"
+    assert out["discovery_llm_degraded"] is True
+    assert out["discovery_rounds_on_fallback"] == 1
+    assert out["degraded_features"] == [
+        {"feature": "storm", "firing_status": "under_fired", "effective_query_count": 5}
+    ]
+
+
+def test_storm_at_or_above_floor_not_overridden():
+    # 12 effective queries == floor 12 → healthy, no override (>= floor passes).
+    out = compute_run_health_gate(
+        [_storm_fired(12), _feat("agentic_search", True, "fired")],
+        unified_status="success",
+        gate_on=True,
+        storm_min_effective_queries=12,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is False
+
+
+def test_under_fire_floor_default_disabled_is_byte_compatible():
+    # Default floor (0): a FIRED feature with a tiny effective_query_count is NOT flagged, so every
+    # pre-existing caller (which never passes the kwarg) is unchanged. count < 0 never fires.
+    out = compute_run_health_gate(
+        [_storm_fired(1)],
+        unified_status="success",
+        gate_on=True,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is False
+
+
+def test_under_fire_absent_count_never_false_aborts():
+    # A FIRED feature that does NOT publish effective_query_count (e.g. agentic publishes
+    # urls_discovered, not effective_query_count) must NEVER trip the floor — absent != 0.
+    agentic = _feat("agentic_search", True, "fired")  # no effective_query_count key
+    out = compute_run_health_gate(
+        [agentic],
+        unified_status="success",
+        gate_on=True,
+        storm_min_effective_queries=12,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is False
+
+
+def test_under_fire_not_overridden_when_gate_off():
+    # Same as the TOTAL-no-fire path: with the gate off, the under-fire is OBSERVED but never aborts.
+    out = compute_run_health_gate(
+        [_storm_fired(3)],
+        unified_status="success",
+        gate_on=False,
+        storm_min_effective_queries=12,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is True  # surfaced for the operator
+
+
+def test_under_fire_never_overrides_non_success():
+    # Only a would-be success is overridden; a more-specific held/abort status is left alone.
+    out = compute_run_health_gate(
+        [_storm_fired(2)],
+        unified_status="partial_thin_corpus",
+        gate_on=True,
+        storm_min_effective_queries=12,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is True

```
