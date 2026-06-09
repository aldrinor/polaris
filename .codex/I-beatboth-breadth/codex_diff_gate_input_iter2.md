## I-beatboth-fix-000 breadth cluster — DIFF gate ITER 2 (iter-1 P1 fixed)
HARD ITERATION CAP: 5. iter 2 of 5. APPROVE iff zero novel P0, zero continuing P0, zero P1.
Iter-1 verdict REQUEST_CHANGES, one P1: STORM URL seed lane (60) pushed total fetch to ~1060, breaking the hard 1000 envelope. FIX: main lane PG_SWEEP_FETCH_CAP trimmed 800->740 to ABSORB the STORM 60 lane -> 740+100(agentic)+60(deepener)+40(R6)+60(STORM)=1000 exactly. The #1168 four-lane-sum test updated to the new 5-lane arithmetic (still ==1000). All P2 (BB-005 run-level smoke coverage) accept-remaining. strict_verify/4-role still byte-unchanged (SHA256 baseline). Verify the 1000 envelope holds and nothing else regressed.
DIFF:
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 0aa0659a..88f43f82 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -428,17 +428,20 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # lanes. The operator's ~1000 budget is SPLIT across the four real fetch lanes so they SUM to ~1000
     # (the prior 1000 here was the MAIN lane alone, on top of which agentic/deepener/R-6 each added more
     # — silently overshooting the budget). The four lanes, FLOOR-applied below (max(existing, slate)):
-    #   PG_SWEEP_FETCH_CAP            800  main Serper/S2/OpenAlex lane (total URLs after dedup, /query)
+    #   PG_SWEEP_FETCH_CAP            740  main Serper/S2/OpenAlex lane (total URLs after dedup, /query)
     #   PG_AGENTIC_BENCHMARK_URL_CAP  100  agentic-discovery harvest (run_honest_sweep_r3.py:3162)
     #   PG_SWEEP_DEEPENER_URL_CAP      60  citation-snowball deepener (run_honest_sweep_r3.py:3038)
     #   PG_R6_EXPAND_FETCH_CAP         40  R-6 completeness re-expansion (run_honest_sweep_r3.py:2961)
+    #   PG_STORM_URL_FETCH_CAP         60  STORM web-results seed lane (I-beatboth-fix-000 BB-006)
     #   --------------------------------------------------------------------------------------------
-    #   SUM                          1000  ≈ the ~1000-site/question budget (operator no-overshoot)
+    #   SUM                          1000  ≈ the ~1000-site/question budget (operator no-overshoot).
+    #   I-beatboth-fix-000 (Codex P1): main lane trimmed 800->740 to ABSORB the new STORM seed lane so
+    #   the total fetch stays at the hard 1000 envelope (no ~1060 overshoot).
     # NOTE: PG_STORM_MAX_BENCHMARK_QUERIES (30) and PG_MAX_SUBQUERIES (15) below are QUERY-BREADTH
     # counts (how many search queries are issued), NOT URLs — they are deliberately NOT part of the
     # ~1000-URL sum. .env has no override for any of these (checked I-fetch-002), so the floor lands.
     # Retrieval breadth — the REAL run_one_query knobs (PG_SWEEP_*, default 12/12/40). NOT PG_LIVE_*.
-    "PG_SWEEP_FETCH_CAP": "800",   # MAIN lane: total URLs fetched+classified per query (budget lane 1/4)
+    "PG_SWEEP_FETCH_CAP": "740",   # MAIN lane: total URLs/query (lane 1/4); 800->740 to absorb STORM seed lane (1000 total)
     "PG_SWEEP_MAX_SERPER": "100",
     "PG_SWEEP_MAX_S2": "100",
     # FX-17 (#1126): Serper `num` is a PAGE size (max ~20); breadth needs the new PAGINATION budget.
@@ -565,6 +568,44 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # (post-validator) queries — a thin-corpus collapse that would otherwise ship green. Discovery-health
     # only (faithfulness-neutral). Read at the run_honest_sweep_r3.py compute_run_health_gate call site.
     "PG_STORM_MIN_EFFECTIVE_QUERIES": "12",
+    # ─────────────────────────────────────────────────────────────────────────────────────────────
+    # I-beatboth-fix-000 (#1171) RETRIEVAL-BREADTH cluster — widen DISCOVERY (candidates), NEVER raise
+    # total FETCH. Every value below is DISCOVERY/telemetry/observability; the four FETCH lanes
+    # (main 800 + agentic 100 + deepener 60 + R6 40 = 1000) are UNCHANGED, so the operator ~1000-fetch
+    # no-overshoot envelope holds. All seven fixes are faithfulness-NEUTRAL (no strict_verify / NLI /
+    # 4-role / provenance path touched). Several keys are STRING- or sub-1-FLOAT-valued and MUST ride
+    # the force-exact path (the numeric FLOOR path would int()-truncate 0.08 -> 0, disabling the gate,
+    # or crash on float("containment")) — they are listed in _BENCHMARK_FORCE_EXACT_FLAGS below.
+    #
+    # BB-001: the scope-validator floor + similarity measure. Symmetric Jaccard punishes short on-topic
+    # queries against a 28-40-token anchor (the #1 chokepoint: 40->5 kept). containment (|q∩a|/min) +
+    # a researched 0.08 floor keep short on-topic queries while still failing genuine drift (gate KEPT).
+    "PG_AMPLIFIER_SCOPE_FLOOR": "0.08",
+    "PG_SCOPE_SIM_MEASURE": "containment",
+    # BB-002: Serper keeps offset-paging past a sub-per_page page (the unreliable end-of-results signal)
+    # until budget / 0-new / PG_SERPER_MAX_PAGES. Discovery only — main-lane FETCH stays capped at 800.
+    "PG_SERPER_STOP_ON_ZERO_NEW": "1",
+    # BB-003: OpenAlex /works search at per_page=200 (API max) + cursor paging to cover PG_SWEEP_MAX_S2.
+    # MAX_S2=100 fits in ONE 200-page, but allow 2 cursor pages as headroom (still discovery, not fetch).
+    "PG_OPENALEX_PER_PAGE": "200",
+    "PG_OPENALEX_MAX_PAGES": "2",
+    # BB-005: harvest MORE of the ~1933 agentic-discovered URLs for DISCOVERY TELEMETRY
+    # (urls_discovered_total) WITHOUT raising the agentic FETCH lane — the fetched subset stays
+    # truncated to PG_AGENTIC_BENCHMARK_URL_CAP=100 (budget lane 2/4). Telemetry-only widening.
+    "PG_AGENTIC_HARVEST_CAP": "800",
+    # BB-006: ingest the STORM interview-search-result URLs (478/540 real web URLs previously discarded)
+    # as URL-ONLY seed candidates (the synthesized STORM answer/key_findings text is NEVER ingested).
+    # PG_STORM_URL_CAP bounds the harvest; PG_STORM_URL_FETCH_CAP (60) bounds the SEPARATE ADDITIVE
+    # STORM fetch lane — disclosed for the operator's ~1000-fetch accounting (this is the one fix that
+    # adds fetch beyond the four lanes; bounded small and surfaced, not silently overshooting).
+    "PG_STORM_INGEST_WEB_RESULTS": "1",
+    "PG_STORM_URL_CAP": "200",
+    "PG_STORM_URL_FETCH_CAP": "60",
+    # BB-007: a REAL Unpaywall contact email so the (default-ON) OA resolver actually fires — the
+    # placeholder polaris@example.org is treated as resolver-UNAVAILABLE (fail-loud) by the resolver,
+    # a hidden cause of the 67-72% fetch-fail rate. Real DOI-keyed OA full-text upgrades no_content stubs.
+    "PG_UNPAYWALL_EMAIL": "research@polaris-dr.org",
+    # ─────────────────────────────────────────────────────────────────────────────────────────────
     # I-cred-006b (#1170): REPLACE the corpus-level tier-COUNT / material-deviation REFUSAL with PROCEED
     # + a credibility-weighted disclosure (operator directive 2026-06-08: "we shall NOT have gate here,
     # we shall WEIGHT the source"). The drb_72 dry-run aborted abort_corpus_approval_denied because 50%
@@ -683,6 +724,12 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
     # PG_SWEEP_WEIGHTED_CORPUS_GATE=0 cannot survive the setdefault slate and silently restore the
     # §-1.1-banned tier-count corpus REFUSAL on the paid beat-both run (the I-cap-005 P1-1 pattern).
     "PG_SWEEP_WEIGHTED_CORPUS_GATE",
+    # I-beatboth-fix-000 (#1171): force-on the two breadth feature flags so an explicit operator =0
+    # cannot survive the setdefault slate and silently restore the breadth-collapse behaviour.
+    # BB-002: keep Serper offset-paging past short pages (else the de-facto 10/query ceiling returns).
+    "PG_SERPER_STOP_ON_ZERO_NEW",
+    # BB-006: ingest the STORM interview-search-result URLs as URL-only seed candidates.
+    "PG_STORM_INGEST_WEB_RESULTS",
 })
 
 # Flags/modes that the benchmark slate force-sets to a specific value that is
@@ -695,6 +742,15 @@ _BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
     # 999999 survives the slate, the PG_GATE_B_CITED_SPAN preflight still passes, and _cited_window_text
     # expands to effectively the whole record — re-opening BUG-02 whole-doc evidence with the flag ON.
     "PG_GATE_B_SPAN_WINDOW_BYTES",
+    # I-beatboth-fix-000 (#1171): these three are STRING- or sub-1-FLOAT-valued and MUST be force-EXACT
+    # — the numeric FLOOR path (str(int(max(...)))) would int()-truncate PG_AMPLIFIER_SCOPE_FLOOR=0.08
+    # to "0" (SILENTLY DISABLING the scope gate — sim>=0 always true) and crash on
+    # float("containment") / float("research@..."). Force-exact sets the literal slate value.
+    # BB-001: the researched containment-scale floor (0.08) + the containment similarity measure.
+    "PG_AMPLIFIER_SCOPE_FLOOR",
+    "PG_SCOPE_SIM_MEASURE",
+    # BB-007: the real Unpaywall contact email (placeholder => resolver fails loud + no-ops).
+    "PG_UNPAYWALL_EMAIL",
 })
 
 # I-ready-017 FX-03 (#1107) Codex iter-2 P1: hard CEILING on the cited-span window (defense-in-depth on
@@ -856,6 +912,32 @@ def preflight_full_capability() -> None:
                 f"benchmark preflight FAILED: {_floor_exc} — capped finding-dedup needs a parseable "
                 f"PG_RELEVANCE_FLOOR in (0.0, 1.0] before the run."
             )
+    # I-beatboth-fix-000 BB-001 (#1171): PG_AMPLIFIER_SCOPE_FLOOR is a sub-1 FLOAT — the numeric-FLOOR
+    # slate path would int()-truncate 0.08 -> 0 and SILENTLY DISABLE the scope gate (sim >= 0 always
+    # true). It rides _BENCHMARK_FORCE_EXACT_FLAGS, but validate the EFFECTIVE value here so a regression
+    # (or a stray operator override that the force-exact ever stops covering) fails CLOSED rather than
+    # shipping the gate disabled. Must be a float in (0.0, 1.0].
+    try:
+        _floor = float(os.getenv("PG_AMPLIFIER_SCOPE_FLOOR", "0.15"))
+    except ValueError:
+        raise RuntimeError(
+            "benchmark preflight FAILED: PG_AMPLIFIER_SCOPE_FLOOR="
+            f"{os.getenv('PG_AMPLIFIER_SCOPE_FLOOR')!r} is not a float."
+        )
+    if not (0.0 < _floor <= 1.0):
+        raise RuntimeError(
+            f"benchmark preflight FAILED: PG_AMPLIFIER_SCOPE_FLOOR={_floor} is outside (0.0, 1.0] — "
+            f"a 0 floor DISABLES the scope gate (drops nothing); a >1 floor drops every query."
+        )
+    # I-beatboth-fix-000 BB-001 (#1171): the similarity MEASURE must be a recognised value — a typo'd
+    # measure would otherwise fail loud only mid-run inside validate_amplified_queries. Validate the
+    # canonical set here so it fails CLOSED before any spend.
+    _measure = os.getenv("PG_SCOPE_SIM_MEASURE", "jaccard").strip().lower()
+    if _measure not in ("jaccard", "containment"):
+        raise RuntimeError(
+            f"benchmark preflight FAILED: PG_SCOPE_SIM_MEASURE={_measure!r} is not a recognised "
+            f"similarity measure (expected 'jaccard' or 'containment')."
+        )
 
 
 def preflight_import_time_constants() -> None:
diff --git a/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py b/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
index c7e79253..fe28e2e5 100644
--- a/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
+++ b/tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py
@@ -161,21 +161,25 @@ _LANE_KNOBS = (
     "PG_AGENTIC_BENCHMARK_URL_CAP",  # agentic-discovery harvest
     "PG_SWEEP_DEEPENER_URL_CAP",     # citation-snowball deepener
     "PG_R6_EXPAND_FETCH_CAP",        # R-6 completeness re-expansion
+    "PG_STORM_URL_FETCH_CAP",        # STORM web-results seed lane (I-beatboth-fix-000 BB-006)
 )
 
 
 def test_four_fetch_lanes_sum_to_about_1000():
-    """The operator budget: the WHOLE run fetches ~1000 sites/question, split across four lanes that
-    SUM to ~1000 — never 1000 (main) + additive agentic/deepener/R-6 on top."""
+    """The operator budget: the WHOLE run fetches ~1000 sites/question, split across the fetch lanes
+    that SUM to ~1000 — never 1000 (main) + additive lanes on top. I-beatboth-fix-000 (Codex P1)
+    trimmed the main lane 800->740 to ABSORB the new STORM web-results seed lane (BB-006) so the total
+    stays at the hard 1000 envelope (no ~1060 overshoot)."""
     vals = {k: int(_FULL_CAPABILITY_BENCHMARK_SLATE[k]) for k in _LANE_KNOBS}
     total = sum(vals.values())
-    assert total == 1000, f"four-lane fetch budget must sum to ~1000, got {total} from {vals}"
+    assert total == 1000, f"fetch budget must sum to ~1000, got {total} from {vals}"
     # And the exact split documented in the slate comment.
     assert vals == {
-        "PG_SWEEP_FETCH_CAP": 800,
+        "PG_SWEEP_FETCH_CAP": 740,
         "PG_AGENTIC_BENCHMARK_URL_CAP": 100,
         "PG_SWEEP_DEEPENER_URL_CAP": 60,
         "PG_R6_EXPAND_FETCH_CAP": 40,
+        "PG_STORM_URL_FETCH_CAP": 60,
     }
 
 
@@ -199,10 +203,11 @@ def test_lane_floors_land_with_no_env_override():
     for knob in _LANE_KNOBS:
         os.environ.pop(knob, None)
     apply_full_capability_benchmark_slate()
-    assert int(os.environ["PG_SWEEP_FETCH_CAP"]) == 800
+    assert int(os.environ["PG_SWEEP_FETCH_CAP"]) == 740
     assert int(os.environ["PG_R6_EXPAND_FETCH_CAP"]) == 40
     assert int(os.environ["PG_AGENTIC_BENCHMARK_URL_CAP"]) == 100
     assert int(os.environ["PG_SWEEP_DEEPENER_URL_CAP"]) == 60
+    assert int(os.environ["PG_STORM_URL_FETCH_CAP"]) == 60
 
 
 # --------------------------------------------------------------------------- I-fetch-002 (#1168)
```
