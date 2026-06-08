HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (bind to this):

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# I-preflight-002 (#1169) — DIFF REVIEW

Review this preflight upgrade that adds a RETRIEVAL-BREADTH fail-closed assertion (one real query must return >= PG_PREFLIGHT_MIN_BREADTH=100 candidate URLs, else GateError — the throttle-regression tripwire) + a STORM-fired assertion.

Verify:
- (a) both are dependency-injected with real defaults so the offline smoke drives the dead->GateError leaf with NO network;
- (b) gated by PG_SUPER_HEAVY_PREFLIGHT, live-path only;
- (c) fail-CLOSED (GateError) before spend;
- (d) binding strict_verify/4-role untouched;
- (e) the breadth threshold logic is correct (40 fails, hundreds passes).

End with 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES' then bullets.

---

## STAGED DIFF

```diff
diff --git a/scripts/dr_benchmark/super_heavy_preflight.py b/scripts/dr_benchmark/super_heavy_preflight.py
index fa775c2b..1dc1e076 100644
--- a/scripts/dr_benchmark/super_heavy_preflight.py
+++ b/scripts/dr_benchmark/super_heavy_preflight.py
@@ -21,8 +21,20 @@ and fails CLOSED (raises ``GateError``) before any token is spent:
          (make_openrouter_credibility_caller) on PG_CREDIBILITY_JUDGE_MODEL, but ONLY when the
          credibility redesign is active in this run (PG_SWEEP_CREDIBILITY_REDESIGN) — probe-alive
          must match production activation.
-  3. STORM/discovery is non-empty — a real, minimal STORM persona-discovery call returns >0 personas
-     (the discovery generate_structured path the drb_72 collapse silently killed).
+  3. STORM/discovery is non-empty — a real, minimal STORM persona-discovery call returns
+     >= PG_PREFLIGHT_MIN_STORM_PERSONAS personas (default 2 for the cheap probe). The discovery
+     generate_structured path the drb_72 collapse silently killed.
+  3b. RETRIEVAL BREADTH goes WIDE (I-preflight-002 #1169) — ONE real query through the PRODUCTION
+     discovery functions (`_serper_search` + `_s2_bulk_search`, the EXACT functions run_one_query drives
+     via run_live_retrieval) with the run's ACTUAL breadth budget (PG_SWEEP_MAX_SERPER /
+     PG_SWEEP_MAX_S2 + the PG_SERPER_TOTAL_PER_QUERY pagination budget — the LIVE PG_SWEEP_* knobs, NOT
+     the dead PG_LIVE_* names) returns >= PG_PREFLIGHT_MIN_BREADTH (default 100) UNIQUE candidate URLs.
+     If a silent throttle regression dropped the run back to ~40 URLs / single-page Serper, the union
+     collapses well below 100 -> GateError. This is the single most important new check: it proves the
+     1000-budget/STORM-wide path is ACTIVE, not silently throttled (the I-cap-005 / FX-17 throttle
+     class). It is the BEHAVIORAL counterpart to the config-level `_BENCHMARK_PREFLIGHT_FLOORS` floor in
+     run_gate_b — complementary defense-in-depth (real query + real count vs config-flag value), not a
+     duplicate. Cheap: TWO search-API calls (no fetch, no LLM generation, no classification spend).
   4. Playwright/chromium present on the run host — reuse the FX-16 fail-closed probe
      (pg_preflight.test_chromium_browser_available); FAIL -> GateError. HOST-LOCAL only (a local PASS
      does not prove the VM; the VM-side chromium install is FX-16's operator-gated step).
@@ -53,6 +65,21 @@ _CREDIBILITY_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
 # OFF tokens — identical to the runner's read (run_honest_sweep_r3.py:4711).
 _CREDIBILITY_OFF_TOKENS = ("", "0", "false", "off", "no")
 
+# I-preflight-002 (#1169) RETRIEVAL-BREADTH probe floor (LAW VI, env-overridable). The single real
+# query through the production discovery functions must return at least this many UNIQUE candidate URLs,
+# or a silent throttle regression (the run dropping back to ~40 URLs / single-page Serper) has occurred.
+# 100 is the wide-run floor: at the benchmark slate (PG_SWEEP_MAX_SERPER=100 / PG_SWEEP_MAX_S2=100 /
+# PG_SERPER_TOTAL_PER_QUERY=60) the serper(paginated ~60) + S2(~100) union clears 100 with margin, while
+# a throttled config (e.g. PG_SWEEP_MAX_S2=12, single-page Serper ~20) collapses the union to ~30-40.
+# UNCALIBRATED offline — may need tuning against the first real wide run (see I-preflight-002 caveats).
+_PREFLIGHT_MIN_BREADTH = int(os.getenv("PG_PREFLIGHT_MIN_BREADTH", "100"))
+
+# I-preflight-002 (#1169) STORM-FIRED floor (LAW VI, env-overridable). The cheap STORM probe requests
+# target_count=2 personas; require at least this many to fire. Default 2 — the probe is intentionally
+# cheap (the breadth probe is the real wide-run signal), so the STORM floor only proves the
+# persona-discovery generate_structured path produces its requested minimum, not a large count.
+_PREFLIGHT_MIN_STORM_PERSONAS = int(os.getenv("PG_PREFLIGHT_MIN_STORM_PERSONAS", "2"))
+
 
 def credibility_redesign_active() -> bool:
     """True iff the credibility-redesign pass is active for this run (matches the runner's read)."""
@@ -302,6 +329,49 @@ async def _default_storm_probe() -> int:
         await client.close()
 
 
+def _default_breadth_probe() -> int:
+    """I-preflight-002 (#1169): run ONE real query through the PRODUCTION discovery functions and return
+    the count of UNIQUE candidate URLs. This is the THROTTLE-REGRESSION signal — a wide run returns
+    >= _PREFLIGHT_MIN_BREADTH; a silently-throttled run (back to ~40 URLs / single-page Serper) returns
+    far fewer.
+
+    REUSES the EXACT production discovery functions the run drives — ``_serper_search`` and
+    ``_s2_bulk_search`` (the same functions ``run_one_query`` calls via ``run_live_retrieval``), with the
+    run's ACTUAL breadth budget read from the LIVE PG_SWEEP_* knobs (NOT the dead PG_LIVE_*-keyed
+    ``DEFAULT_MAX_SERPER`` / ``DEFAULT_MAX_S2`` module constants, default 20 — keying off those would
+    false-FAIL every wide run). Mirrors run_honest_sweep_r3.py:2271-2272 EXACTLY:
+      - serper: ``num = PG_SWEEP_MAX_SERPER`` (default 12). ``_serper_search`` internally honors the
+        ``PG_SERPER_TOTAL_PER_QUERY`` pagination budget from env, so passing the slate's MAX_SERPER
+        reflects the wide config automatically.
+      - S2: ``limit = PG_SWEEP_MAX_S2`` (default 12). ``_s2_bulk_search`` clamps to min(limit, 100).
+
+    NO fetch, NO LLM generation, NO classification: TWO search-API calls only (the canary already does
+    one serper call). Returns the size of the UNIONED unique-URL set across both backends; the caller
+    fails closed if it is below ``_PREFLIGHT_MIN_BREADTH``."""
+    from src.polaris_graph.retrieval.live_retriever import (
+        _s2_bulk_search,
+        _serper_search,
+    )
+
+    # Mirror run_honest_sweep_r3.py:2271-2272 — the LIVE breadth knobs, with the runner's defaults.
+    max_serper = int(os.getenv("PG_SWEEP_MAX_SERPER", "12"))
+    max_s2 = int(os.getenv("PG_SWEEP_MAX_S2", "12"))
+    # The same high-volume probe query the canary's live-search probe uses (proves the THROTTLE CONFIG is
+    # wide; it does not assert the run's actual question yields this many — that is the run's own corpus).
+    query = "metformin efficacy in type 2 diabetes"
+
+    urls: set[str] = set()
+    for hit in _serper_search(query, num=max_serper):
+        u = hit.get("url", "")
+        if u:
+            urls.add(u)
+    for hit in _s2_bulk_search(query, limit=max_s2):
+        u = hit.get("url", "")
+        if u:
+            urls.add(u)
+    return len(urls)
+
+
 async def _default_chromium_probe() -> None:
     """Reuse the FX-16 host-local fail-closed chromium probe (pg_preflight). FAIL -> GateError. A SKIP
     (DRY mode, or intentionally-disabled cascade) is treated per its reason: an intentionally-disabled
@@ -371,6 +441,7 @@ async def super_heavy_preflight(
     verifier_slug_probe: Callable[[], Mapping[str, str]] = _default_verifier_slug_probe,
     credibility_judge_probe: Callable[[], str | None] = _default_credibility_judge_probe,
     storm_probe: Callable[[], Awaitable[int]] = _default_storm_probe,
+    breadth_probe: Callable[[], int] = _default_breadth_probe,
     chromium_probe: Callable[[], Awaitable[None]] = _default_chromium_probe,
     false_alarm_asserts: Callable[[], list[str]] = _default_false_alarm_asserts,
 ) -> dict:
@@ -389,7 +460,11 @@ async def super_heavy_preflight(
       4. generator slug alive (generate_structured on PG_GENERATOR_MODEL).
       5. every verifier slug alive in its production call shape (mode-aware resolution).
       6. credibility judge slug alive (only when the redesign is active this run).
-      7. STORM/discovery non-empty (a real minimal persona-discovery call returns >0).
+      7. STORM/discovery fired (a real minimal persona-discovery call returns
+         >= PG_PREFLIGHT_MIN_STORM_PERSONAS).
+      8. retrieval breadth goes WIDE (I-preflight-002 #1169) — ONE real query through the production
+         discovery functions returns >= PG_PREFLIGHT_MIN_BREADTH unique candidate URLs (the
+         single most important new check: it proves the wide path is active, not silently throttled).
     """
     summary: dict = {}
 
@@ -476,12 +551,32 @@ async def super_heavy_preflight(
             f"super-heavy preflight: STORM discovery probe failed ({type(exc).__name__}: {exc}) — fail "
             f"closed BEFORE spend."
         )
-    if n_personas <= 0:
+    if n_personas < _PREFLIGHT_MIN_STORM_PERSONAS:
         raise GateError(
-            "super-heavy preflight: STORM persona-discovery returned 0 personas — discovery is degraded "
-            "(the drb_72 silent-collapse class). Aborting BEFORE spend."
+            f"super-heavy preflight: STORM persona-discovery returned {n_personas} personas "
+            f"(< {_PREFLIGHT_MIN_STORM_PERSONAS} required) — discovery is degraded (the drb_72 "
+            f"silent-collapse class). Aborting BEFORE spend."
         )
     summary["storm_personas"] = n_personas
 
+    # 8. retrieval breadth goes WIDE (I-preflight-002 #1169) — the throttle-regression signal --------
+    try:
+        n_candidates = breadth_probe()
+    except GateError:
+        raise
+    except Exception as exc:
+        raise GateError(
+            f"super-heavy preflight: retrieval-breadth probe failed ({type(exc).__name__}: {exc}) — "
+            f"fail closed BEFORE spend."
+        )
+    if n_candidates < _PREFLIGHT_MIN_BREADTH:
+        raise GateError(
+            f"super-heavy preflight: ONE real query through the production discovery path returned "
+            f"{n_candidates} unique candidate URLs (< {_PREFLIGHT_MIN_BREADTH} required) — the run is "
+            f"SILENTLY THROTTLED back to a narrow corpus (the ~40-URL / single-page-Serper regression "
+            f"class). The 1000-budget/STORM-wide path is NOT active. Aborting BEFORE spend."
+        )
+    summary["retrieval_breadth"] = n_candidates
+
     print("SUPER_HEAVY_PREFLIGHT_OK", flush=True)
     return summary
diff --git a/tests/dr_benchmark/test_super_heavy_preflight_icred013.py b/tests/dr_benchmark/test_super_heavy_preflight_icred013.py
index 87c703c5..ae404d4e 100644
--- a/tests/dr_benchmark/test_super_heavy_preflight_icred013.py
+++ b/tests/dr_benchmark/test_super_heavy_preflight_icred013.py
@@ -17,6 +17,8 @@ import pytest
 from scripts.dr_benchmark.pathB_run_gate import GateError
 from scripts.dr_benchmark.super_heavy_preflight import (
     _CREDIBILITY_REDESIGN_FLAG,
+    _PREFLIGHT_MIN_BREADTH,
+    _PREFLIGHT_MIN_STORM_PERSONAS,
     credibility_redesign_active,
     super_heavy_preflight,
 )
@@ -57,6 +59,10 @@ async def _storm_ok() -> int:
     return 2
 
 
+def _breadth_ok() -> int:
+    return 140  # the wide-run union (serper ~60 + S2 ~100, de-duped) clears the default floor of 100
+
+
 async def _chromium_ok() -> None:
     return None
 
@@ -72,6 +78,7 @@ def _all_green_kwargs(**overrides):
         verifier_slug_probe=_verifiers_ok,
         credibility_judge_probe=_cred_inactive,
         storm_probe=_storm_ok,
+        breadth_probe=_breadth_ok,
         chromium_probe=_chromium_ok,
         false_alarm_asserts=_false_alarms_ok,
     )
@@ -90,6 +97,7 @@ def test_super_heavy_preflight_all_green_returns_summary(capsys):
     assert summary["verifier_slugs_alive"]["sentinel"] == "minimax/minimax-m2"
     assert summary["credibility_judge"] == "inactive_this_run"
     assert summary["storm_personas"] == 2
+    assert summary["retrieval_breadth"] == 140
 
 
 def test_super_heavy_preflight_reports_active_credibility_slug():
@@ -186,6 +194,56 @@ def test_normalizes_arbitrary_storm_failure_to_gateerror():
         asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_boom)))
 
 
+def test_fails_closed_when_storm_under_threshold():
+    """I-preflight-002 (#1169): STORM returning FEWER than PG_PREFLIGHT_MIN_STORM_PERSONAS (default 2)
+    fails closed — not only the empty (0) case. A 1-persona return is under the cheap-probe floor."""
+    assert _PREFLIGHT_MIN_STORM_PERSONAS == 2  # the cheap-probe default
+
+    async def _storm_under() -> int:
+        return 1
+
+    with pytest.raises(GateError, match=r"1 personas \(< 2 required\)"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_under)))
+
+
+# --------------------------------------------------------------------------- I-preflight-002 BREADTH
+def test_fails_closed_when_breadth_too_low():
+    """I-preflight-002 (#1169) THE most important new check: a narrow candidate-URL count (the silent
+    ~40-URL / single-page-Serper throttle regression) fails closed BEFORE spend."""
+    def _breadth_throttled() -> int:
+        return 38  # the ~40-URL throttle-regression signal — below the default floor of 100
+
+    with pytest.raises(GateError, match=r"SILENTLY THROTTLED|unique candidate URLs"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(breadth_probe=_breadth_throttled)))
+
+
+def test_breadth_ok_passes():
+    """A wide-run breadth count (>= PG_PREFLIGHT_MIN_BREADTH) passes and is recorded in the summary."""
+    def _breadth_wide() -> int:
+        return _PREFLIGHT_MIN_BREADTH + 25
+
+    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs(breadth_probe=_breadth_wide)))
+    assert summary["retrieval_breadth"] == _PREFLIGHT_MIN_BREADTH + 25
+
+
+def test_breadth_exactly_at_floor_passes():
+    """Boundary: breadth EXACTLY at the floor passes (>= floor, not strictly greater)."""
+    def _breadth_at_floor() -> int:
+        return _PREFLIGHT_MIN_BREADTH
+
+    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs(breadth_probe=_breadth_at_floor)))
+    assert summary["retrieval_breadth"] == _PREFLIGHT_MIN_BREADTH
+
+
+def test_normalizes_arbitrary_breadth_failure_to_gateerror():
+    """A non-GateError breadth-probe exception is normalized to a fail-closed GateError."""
+    def _breadth_boom() -> int:
+        raise RuntimeError("serper exploded")
+
+    with pytest.raises(GateError, match="fail closed"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(breadth_probe=_breadth_boom)))
+
+
 # --------------------------------------------------------------------------- credibility-activation read
 def test_credibility_redesign_active_matches_runner_off_tokens():
     for off in ("", "0", "false", "off", "no", "FALSE", " Off "):
@@ -265,6 +323,46 @@ def test_default_credibility_probe_noop_when_redesign_off():
     assert m._default_credibility_judge_probe() is None
 
 
+def test_default_breadth_probe_unions_serper_and_s2_and_reads_live_knobs(monkeypatch):
+    """I-preflight-002 (#1169): the REAL _default_breadth_probe reuses the PRODUCTION discovery
+    functions (_serper_search + _s2_bulk_search), UNIONS+de-dups their URLs, and reads the LIVE
+    PG_SWEEP_MAX_SERPER / PG_SWEEP_MAX_S2 knobs (the run's real breadth budget) — NOT the dead
+    PG_LIVE_*-keyed module defaults. The two search functions are faked, so NO network."""
+    import src.polaris_graph.retrieval.live_retriever as lr
+
+    seen_serper_num: dict[str, int] = {}
+    seen_s2_limit: dict[str, int] = {}
+
+    def _fake_serper(query, num=10, api_calls=None):
+        seen_serper_num["num"] = num
+        return [{"url": f"https://serper/{i}"} for i in range(60)]
+
+    def _fake_s2(query, limit=20):
+        seen_s2_limit["limit"] = limit
+        # 100 S2 URLs, the last 10 DUPLICATE serper URLs to prove de-dup (union, not sum).
+        s2 = [{"url": f"https://s2/{i}"} for i in range(90)]
+        s2 += [{"url": f"https://serper/{i}"} for i in range(10)]
+        return s2
+
+    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
+    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)
+    # The LIVE breadth knobs (the slate values) — must be the ones read.
+    os.environ["PG_SWEEP_MAX_SERPER"] = "100"
+    os.environ["PG_SWEEP_MAX_S2"] = "100"
+    # The DEAD PG_LIVE_* names must NOT be read; set them absurdly low to prove they are ignored.
+    os.environ["PG_LIVE_MAX_SERPER"] = "3"
+    os.environ["PG_LIVE_MAX_S2"] = "3"
+
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    n = m._default_breadth_probe()
+
+    # union of 60 serper + 90 unique s2 (10 s2 duplicated serper) = 150 unique
+    assert n == 150
+    # read the LIVE knobs, not the dead defaults
+    assert seen_serper_num["num"] == 100
+    assert seen_s2_limit["limit"] == 100
+
+
 # --------------------------------------------------------------------------- slate wiring
 def test_super_heavy_preflight_is_in_slate_force_on_and_required():
     """The super-heavy preflight must be force-on + required in the benchmark slate, so a paid run can

```
