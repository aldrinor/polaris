HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — I-beatboth-fix-000 (#1171) RETRIEVAL-BREADTH cluster (BB-001..BB-007)

Review the retrieval-breadth cluster fix (BB-001..BB-007 from outputs/vm_forensic/FIX_DESIGNS.json). Every fix is DISCOVERY-ONLY: candidates still flow through the unchanged fetch -> strict_verify -> entailment-judge/NLI -> 4-role seam chokepoint. None should touch a verification path. Files: scope_query_validator.py (BB-001 containment measure), live_retriever.py (BB-002 serper stop-on-zero-new, BB-004 s2 zero-yield telemetry, BB-007 unpaywall placeholder guard, storm_seed label), domain_backends.py (BB-003 openalex cursor paging), agentic_url_harvester.py (BB-006 harvest_storm_urls), run_honest_sweep_r3.py (BB-005 harvest/fetch decouple, BB-006 STORM ingest + seed lane), run_gate_b.py (slate + force-exact + BB-001 preflight), plus the new offline test file.

## VERIFY (line-by-line, against the staged diff below)

(a) **Every fix is DISCOVERY-ONLY** — strict_verify, the entailment judge/NLI, and the 4-role seam are byte-unchanged. The 10 verification-gate files (provenance_generator.py, entailment_judge.py, nli_verifier.py, strict_verify.py, role_pipeline.py, sentinel_adapter.py, judge_adapter.py, sweep_integration.py, native_gate_b_inputs.py, evaluator_gate.py) are NOT in this diff and are SHA-confirmed byte-identical to baseline. Grep the call sites in the diff: confirm no fix writes into the evidence pool any text other than fetched-then-verified candidate content, and no fix calls into or modifies a verification path.

(b) **Each flag defaults OFF (byte-identical) and the Gate-B slate activates it.** Verify each: PG_SCOPE_SIM_MEASURE default "jaccard" == legacy; PG_AMPLIFIER_SCOPE_FLOOR default 0.15 == legacy; PG_SERPER_STOP_ON_ZERO_NEW default 0 == legacy short-page break; PG_OPENALEX_PER_PAGE default 25 + PG_OPENALEX_MAX_PAGES default 1 == legacy single-page min(limit,25) with NO cursor param sent; PG_AGENTIC_HARVEST_CAP default == fetch cap (no extra harvest); PG_STORM_INGEST_WEB_RESULTS default 0 == no STORM seeds; PG_UNPAYWALL_EMAIL placeholder == resolver no-ops. Then confirm _FULL_CAPABILITY_BENCHMARK_SLATE sets the ON value for each, and the force-exact / force-on sets cover the string/sub-1-float flags (the 0.08 float must NOT int()-truncate to 0 and silently disable the gate).

(c) **BB-006 ingests ONLY STORM web_results/academic_results URLs as candidates, NEVER the synthesized answer/key_findings/snippet (FAITHFULNESS-CRITICAL).** Read harvest_storm_urls in agentic_url_harvester.py line-by-line: confirm it reads ONLY rec["url"] from the web_results/academic_results streams, never answer/key_findings/outline/conversation/snippet text. Confirm the run_honest_sweep_r3.py BB-006 block fetches these URLs via run_live_retrieval(seed_only=True) so they pass through fetch -> strict_verify -> 4-role verbatim like any candidate (empty direct_quote), and that no STORM-synthesized text is merged into evidence. Any path that promotes STORM answer/key_findings into the evidence pool is a P0 fabrication path.

(d) **BB-001 KEEPS the gate (containment measure), does not remove it.** Confirm _containment(|q∩a|/min(|q|,|a|)) still drops genuinely off-anchor queries (the gate is reranking against intent), and the change only stops punishing short on-topic queries by anchor size. A fix that deletes the gate / sets the floor to 0 / always-keeps is a P1.

(e) **Pagination loops (BB-002 serper, BB-003 openalex) terminate correctly (no infinite loop) and dedup.** Serper: bounded by _n_pages; stops on budget met / 0-new-post-dedup / max pages; dedup by url (seen set). OpenAlex: bounded `for _page in range(max_pages)`; breaks on no-data / no-results / no-next-cursor / len>=limit; dedup by work id across pages. Confirm neither can loop forever and neither double-counts.

(f) **The offline smoke actually proves the funnel deltas** (not a tautology / not a string-presence check). Read the new test file: confirm each BB test asserts the actual count delta (containment keeps more than jaccard on a short-query/large-anchor fixture; serper fetches page 2 then stops on zero-new; openalex per_page=200 + cursor accumulates >25; s2 zero-yield surfaced; harvest_storm_urls returns ONLY url and NEVER answer/key_findings text; agentic harvest cap honored with dedup; unpaywall placeholder guard skips/fires), and that the OFF path is asserted byte-identical.

End with 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES' then the schema:

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## STAGED DIFF

```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 0aa0659a..615df1c1 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -565,6 +565,44 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
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
@@ -683,6 +721,12 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
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
@@ -695,6 +739,15 @@ _BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
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
@@ -856,6 +909,32 @@ def preflight_full_capability() -> None:
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
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 71cacd88..ea183737 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1899,6 +1899,10 @@ async def run_one_query(
         "agentic_search", urls_discovered=0, urls_selectable=0,  # FX-15b (#1119): post-filter count
         enabled=_agentic_enabled, firing_status="enabled_not_reached" if _agentic_enabled else "not_enabled",
     )
+    # BB-006 (I-beatboth-fix-000 #1171): the STORM interview-search URLs harvested for the seed lane.
+    # Always defined (default empty) so the post-base-retrieval STORM seed-merge block below is a no-op
+    # when STORM URL ingestion is OFF or STORM did not run — byte-identical OFF.
+    _storm_seed_urls: list[str] = []
     # I-ready-005 (#1076) iter-4 P1-2: the ContextVar publish is GATED on at least one forced-ON
     # benchmark feature and lives INSIDE the outer try below (first statement). When both features
     # are OFF the ContextVar stays None, so _attach_tool_utilization adds no feature keys and the
@@ -2665,6 +2669,29 @@ async def run_one_query(
                 _storm_out.get("storm_conversations", []),
                 cap=int(os.getenv("PG_STORM_MAX_BENCHMARK_QUERIES", "30")),
             )
+            # BB-006 (I-beatboth-fix-000 #1171): ALSO harvest the STORM interview-search-result URLs
+            # (the 478/540 real web URLs in _storm_out['web_results'] + ['academic_results']) as SEED
+            # candidates — previously DISCARDED (only the synthesized interview QUESTIONS were re-used).
+            # URL-ONLY (HARD faithfulness contract): harvest_storm_urls reads only rec['url'], NEVER the
+            # STORM synthesized answer/key_findings/snippet text. The fetched-then-verified seed lane is
+            # built AFTER base retrieval (mirrors the agentic block) so the URLs flow through fetch +
+            # strict_verify + 4-role verbatim like any candidate. Default OFF = byte-identical (no seeds
+            # harvested). The fetch of these seeds is a SEPARATE, BOUNDED lane (PG_STORM_URL_FETCH_CAP)
+            # ADDITIVE to the four-lane budget — surfaced for the operator's ~1000-fetch accounting.
+            if os.getenv("PG_STORM_INGEST_WEB_RESULTS", "0").strip() in ("1", "true", "True"):
+                from src.polaris_graph.retrieval.agentic_url_harvester import (
+                    harvest_storm_urls,
+                )
+                _storm_seed_urls = harvest_storm_urls(
+                    _storm_out,
+                    cap=max(0, int(os.getenv("PG_STORM_URL_CAP", "200"))),
+                )
+                _storm_telemetry["web_result_urls_harvested"] = len(_storm_seed_urls)
+                if _storm_seed_urls:
+                    _log(
+                        f"[storm]       harvested {len(_storm_seed_urls)} interview-search-result "
+                        f"URLs as seed candidates (slug={q['slug']})"
+                    )
             if _storm_questions:
                 _seen_lower = {x.lower() for x in _amplified_effective}
                 _storm_added = [x for x in _storm_questions if x.lower() not in _seen_lower]
@@ -3203,7 +3230,23 @@ async def run_one_query(
             # envelope would breach the cap. This precedes the try, so it PROPAGATES (matches STORM) —
             # the fail-open except below must NEVER swallow a budget abort.
             _ag_check_budget(0)
+            # PG_AGENTIC_BENCHMARK_URL_CAP is the agentic FETCH lane (budget lane 2/4 of the
+            # operator's ~1000-fetch envelope: main 800 + agentic 100 + deepener 60 + R6 40 = 1000).
+            # There is NO global fetch counter — each lane caps independently — and in seed_only mode
+            # `run_live_retrieval` fetches EVERY seed (seeds bypass the fetch_cap rerank-slice), so the
+            # number of seed URLs IS the agentic fetch count. It therefore must NOT be raised above its
+            # budgeted value or the ~1000 total overshoots (operator no-overshoot directive).
             _ag_url_cap = max(0, int(os.getenv("PG_AGENTIC_BENCHMARK_URL_CAP", "100")))
+            # BB-005 (I-beatboth-fix-000 #1171): the agentic loop discovers ~1933 URLs but only the
+            # budgeted _ag_url_cap may be FETCHED. PG_AGENTIC_HARVEST_CAP lets the harvest read MORE
+            # of them for DISCOVERY TELEMETRY (urls_discovered_total below) — proving how many high-
+            # value URLs the recovery surfaced — while the FETCHED set stays truncated to _ag_url_cap
+            # so the fetch budget is untouched. DEFAULT == the fetch cap = byte-identical (no extra
+            # harvest, identical fetch). Telemetry-only widening; faithfulness- AND budget-neutral.
+            _ag_harvest_cap = max(
+                _ag_url_cap,
+                int(os.getenv("PG_AGENTIC_HARVEST_CAP", str(_ag_url_cap))),
+            )
             _ag_urls: list[str] = []
             # Create the client AFTER the budget precheck so a clean envelope-breach abort does not
             # leave an unclosed client.
@@ -3233,16 +3276,28 @@ async def run_one_query(
                     _ag_mod.execute_agentic_search(_ag_state, _ag_client),
                     context=_ag_ctx,
                 )
-                # Harvest URLs ONLY, then DISCARD the full result immediately so no notebook/summary
-                # field is in scope near the merge below (faithfulness defense-in-depth).
-                _ag_urls = harvest_agentic_urls(_ag_result, cap=_ag_url_cap)
+                # BB-005 (#1171): harvest URLs ONLY up to the (>=fetch) DISCOVERY cap, then DISCARD
+                # the full result immediately so no notebook/summary field is in scope near the merge
+                # below (faithfulness defense-in-depth). The discovered set proves recovery breadth;
+                # the FETCHED set is truncated to the budgeted _ag_url_cap just below so the ~1000
+                # fetch envelope is untouched.
+                _ag_discovered = harvest_agentic_urls(_ag_result, cap=_ag_harvest_cap)
                 del _ag_result
+                # FETCH only the budgeted subset (seed_only fetches every seed — cap the SEED list).
+                _ag_urls = _ag_discovered[:_ag_url_cap]
                 _agentic_telemetry.update({
                     "fired": len(_ag_urls) > 0,
                     "urls_discovered": len(_ag_urls),
+                    # BB-005 (#1171): how many URLs the recovery surfaced BEFORE the fetch-budget
+                    # truncation — the discovery-breadth signal (telemetry only; not fetched).
+                    "urls_discovered_total": len(_ag_discovered),
                     "firing_status": "fired" if _ag_urls else "attempted_empty",
                 })
-                _log(f"[agentic]     discovered {len(_ag_urls)} urls (cap={_ag_url_cap})")
+                _log(
+                    f"[agentic]     discovered {len(_ag_discovered)} urls "
+                    f"(harvest_cap={_ag_harvest_cap}); fetching {len(_ag_urls)} "
+                    f"(fetch_cap={_ag_url_cap})"
+                )
             except Exception as _ag_exc:  # noqa: BLE001 — agentic discovery faults never abort the run
                 _log(
                     f"[agentic]     agentic discovery failed: {_ag_exc} — "
@@ -3333,6 +3388,69 @@ async def run_one_query(
                 except Exception as _ag_merge_exc:  # noqa: BLE001 — fail-open
                     _log(f"[agentic]     merge FAILED (fail-open): {_ag_merge_exc}")
 
+        # BB-006 (I-beatboth-fix-000 #1171): STORM interview-search-result URL seed lane. Mirrors the
+        # agentic block EXACTLY (fetch verbatim -> strict_verify -> 4-role -> merge_seed_url_evidence),
+        # placed last so dist/completeness/adequacy already exist for the staged-corpus recompute. The
+        # URLs were harvested URL-ONLY above (no STORM synthesized text). seed_only=True fetches ONLY
+        # these URLs (no Serper/S2 fan-out); the fetch is a BOUNDED lane (PG_STORM_URL_FETCH_CAP),
+        # ADDITIVE to the four-lane budget and surfaced for the operator's ~1000-fetch accounting.
+        # Default OFF (PG_STORM_INGEST_WEB_RESULTS) -> _storm_seed_urls is empty -> this whole block is
+        # a no-op = byte-identical. Fail-open: any error leaves the pre-STORM corpus untouched.
+        if _storm_seed_urls:
+            try:
+                from src.polaris_graph.retrieval.agentic_url_harvester import (
+                    merge_seed_url_evidence,
+                )
+                _storm_fetch_cap = max(0, int(os.getenv("PG_STORM_URL_FETCH_CAP", "60")))
+                _storm_fetch_urls = _storm_seed_urls[:_storm_fetch_cap]
+                if _storm_fetch_urls:
+                    storm_retrieval = run_live_retrieval(
+                        research_question=q["question"],
+                        amplified_queries=[],
+                        protocol=protocol,
+                        fetch_cap=min(len(_storm_fetch_urls), _storm_fetch_cap),
+                        enable_openalex_enrich=True,
+                        # Seed-safe semantic filter (inert for the URL-only seed_only set), exactly as
+                        # the agentic lane: the structural defense is the empty-snippet URL-only seeds.
+                        enable_prefetch_filter=True,
+                        seed_urls=_storm_fetch_urls,
+                        seed_only=True,   # ONLY the STORM URLs — no Serper/S2/domain fan-out
+                        seed_source="storm_seed",
+                        seed_query_origin="storm_seed",
+                    )
+                    _st_sources, _st_rows, _st_acc_src, _st_acc_rows = merge_seed_url_evidence(
+                        retrieval.classified_sources,
+                        retrieval.evidence_rows,
+                        storm_retrieval.classified_sources,
+                        storm_retrieval.evidence_rows,
+                    )
+                    _st_dist = compute_tier_distribution(_st_sources, protocol)
+                    if not _use_research_planner:
+                        _st_completeness = check_completeness(
+                            domain=q["domain"],
+                            research_question=q["question"],
+                            evidence_rows=_st_rows,
+                        )
+                    else:
+                        _st_completeness = completeness
+                    _st_adequacy = assess_corpus_adequacy(
+                        tier_counts=_st_dist.tier_counts,
+                        evidence_row_count=len(_st_rows),
+                        domain=q["domain"],
+                        protocol=protocol,
+                    )
+                    retrieval.classified_sources = _st_sources
+                    retrieval.evidence_rows = _st_rows
+                    dist = _st_dist
+                    completeness = _st_completeness
+                    adequacy = _st_adequacy
+                    _storm_telemetry["web_result_rows_merged"] = _st_acc_rows
+                    _log(f"[storm]       merged +{_st_acc_rows} evidence rows from "
+                         f"+{_st_acc_src} STORM-URL sources (post-chokepoint); "
+                         f"adequacy={adequacy.decision} uncovered={completeness.total_uncovered}")
+            except Exception as _storm_merge_exc:  # noqa: BLE001 — fail-open
+                _log(f"[storm]       STORM-URL merge FAILED (fail-open): {_storm_merge_exc}")
+
         # I-meta-002-q1d (#945): all retrieval (base + R-6 + deepener) is complete here — flush the
         # retrieval_trace.jsonl now so EVERY exit path below (abort_corpus_inadequate, approval-denied,
         # and the success path) ships the full per-call search/fetch trace for line-by-line audit.
diff --git a/src/polaris_graph/retrieval/agentic_url_harvester.py b/src/polaris_graph/retrieval/agentic_url_harvester.py
index d89db9b7..d023a975 100644
--- a/src/polaris_graph/retrieval/agentic_url_harvester.py
+++ b/src/polaris_graph/retrieval/agentic_url_harvester.py
@@ -8,8 +8,11 @@ as a ``direct_quote`` would be a fabrication. So we read ONLY the discovered URL
 URLs are then fetched **verbatim** by ``live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)``
 and verified by strict_verify + the 4-role seam, exactly like the rest of the corpus.
 
-Two pure, stdlib-light functions (no network, no LLM, no new dependency):
+Three pure, stdlib-light functions (no network, no LLM, no new dependency):
 - ``harvest_agentic_urls`` — ordered, canonical-deduped, capped list of discovered URLs (originals).
+- ``harvest_storm_urls`` — BB-006 (#1171): the same URL-ONLY harvest applied to a STORM-interview
+  result's ``web_results`` / ``academic_results`` streams (the 478/540 interview search-result URLs the
+  benchmark previously discarded). NEVER reads STORM's synthesized answer/key_findings/snippet text.
 - ``merge_seed_url_evidence`` — the deepener's dedup-by-URL + global evidence-id renumber core, factored
   out so it is unit-testable (and a future PR can repoint the deepener at it).
 """
@@ -71,6 +74,60 @@ def harvest_agentic_urls(
     return out
 
 
+def harvest_storm_urls(
+    storm_result: dict[str, Any] | None,
+    cap: int = 200,
+) -> list[str]:
+    """BB-006 (I-beatboth-fix-000 #1171): return ONLY the discovered URLs from a STORM
+    ``run_storm_interviews`` result — the EXACT analogue of ``harvest_agentic_urls``.
+
+    STORM grounds its multi-perspective interviews in REAL internet search results. Those
+    URLs (``storm_result["web_results"]`` then ``["academic_results"]``, each a dict with
+    ``url``/``title``/``snippet``) are legitimate candidate sources — but the run previously
+    DISCARDED them, only re-using STORM's synthesized interview QUESTIONS as query strings.
+
+    HARD URL-ONLY CONTRACT (faithfulness): this reads ONLY ``rec["url"]``. It NEVER reads the
+    STORM-synthesized ``answer`` / ``key_findings`` / outline / conversation text, and NEVER
+    the per-record ``snippet`` — promoting any LLM-synthesized STORM text into the evidence
+    pool would be a fabrication path. The harvested URLs are then fetched VERBATIM by
+    ``live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)`` and gated by
+    strict_verify + the 4-role seam exactly like every other candidate (empty direct_quote).
+
+    Order-preserving + DETERMINISTIC; de-duplicates by ``canonical_source_url`` but RETURNS the
+    original fetchable URL. Returns at most ``cap`` URLs. Robust to missing/empty keys (returns
+    ``[]`` rather than raising). ``cap <= 0`` -> ``[]``.
+    """
+    if cap <= 0:
+        return []
+    result = storm_result or {}
+    seen_canonical: set[str] = set()
+    out: list[str] = []
+
+    def _consider(raw: Any) -> None:
+        if len(out) >= cap:
+            return
+        url = (raw or "").strip() if isinstance(raw, str) else ""
+        if not url:
+            return
+        try:
+            key = canonical_source_url(url) or url
+        except Exception:  # noqa: BLE001 — a malformed URL must not abort discovery
+            key = url
+        if key in seen_canonical:
+            return
+        seen_canonical.add(key)
+        out.append(url)
+
+    # Ordered result streams (deterministic). URL key ONLY — never answer/key_findings/snippet.
+    for stream_key in ("web_results", "academic_results"):
+        for rec in result.get(stream_key, []) or []:
+            if len(out) >= cap:
+                return out
+            if isinstance(rec, dict):
+                _consider(rec.get("url"))
+    return out
+
+
 def merge_seed_url_evidence(
     staged_sources: list[Any],
     staged_rows: list[dict[str, Any]],
diff --git a/src/polaris_graph/retrieval/domain_backends.py b/src/polaris_graph/retrieval/domain_backends.py
index bdddb02b..911ab807 100644
--- a/src/polaris_graph/retrieval/domain_backends.py
+++ b/src/polaris_graph/retrieval/domain_backends.py
@@ -473,6 +473,37 @@ def europe_pmc_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[Searc
 # S2 over the sub-queries, so this ADDS non-baseline scholarly-graph breadth.
 
 _OPENALEX_WORKS_SEARCH = "https://api.openalex.org/works"
+# BB-003 (#1171): the OpenAlex API per_page hard maximum (docs.openalex.org paging).
+_OPENALEX_PER_PAGE_MAX = 200
+
+
+def _openalex_per_page(limit: int) -> int:
+    """BB-003 (#1171): per-page size for the OpenAlex /works search.
+
+    Capped at the OpenAlex API maximum (200). DEFAULT 25 (PG_OPENALEX_PER_PAGE
+    unset) = byte-identical to the legacy ``max(1, min(limit, 25))``. The Gate-B
+    slate sets PG_OPENALEX_PER_PAGE=200 so one page covers up to 200 works.
+    A bad value FAILS LOUD (LAW II) rather than silently throttling to a default.
+    """
+    raw = os.getenv("PG_OPENALEX_PER_PAGE", "25").strip()
+    try:
+        cap = int(raw)
+    except ValueError:
+        raise ValueError(f"PG_OPENALEX_PER_PAGE={raw!r} is not an int")
+    cap = max(1, min(cap, _OPENALEX_PER_PAGE_MAX))
+    return max(1, min(limit, cap))
+
+
+def _openalex_max_pages() -> int:
+    """BB-003 (#1171): cursor-page count cap. DEFAULT 1 (PG_OPENALEX_MAX_PAGES
+    unset) = single page = byte-identical OFF. The slate raises it to cover the
+    requested ``limit``. A bad value FAILS LOUD."""
+    raw = os.getenv("PG_OPENALEX_MAX_PAGES", "1").strip()
+    try:
+        pages = int(raw)
+    except ValueError:
+        raise ValueError(f"PG_OPENALEX_MAX_PAGES={raw!r} is not an int")
+    return max(1, pages)
 
 
 def openalex_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]:
@@ -481,42 +512,64 @@ def openalex_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchC
     Emits a resolvable primary-literature URL per work in DOI -> OpenAlex-id
     priority; a work with neither is SKIPPED. Candidates flow through the SAME
     fetch / tier / strict_verify chokepoint as Serper/S2. Fail-open.
+
+    BB-003 (#1171): per_page is raised to min(limit, PG_OPENALEX_PER_PAGE<=200)
+    and the search CURSOR-PAGES (cursor=* -> meta.next_cursor) up to ``limit`` or
+    PG_OPENALEX_MAX_PAGES — the legacy single page of 25 was the #3 breadth
+    chokepoint (env limit=100 reached the adapter but min(limit,25) capped it at
+    25/query). DEFAULT (per_page 25, max_pages 1) = byte-identical single page,
+    no cursor key in the request. Discovery-breadth only; faithfulness-neutral.
     """
     try:
-        data = _http_get_json(
-            _OPENALEX_WORKS_SEARCH,
-            params={
-                "search": query,
-                "per_page": max(1, min(limit, 25)),
-            },
-        )
-        if not data:
-            return []
-        results = data.get("results") or []
+        per_page = _openalex_per_page(limit)
+        max_pages = _openalex_max_pages()
         out: list[SearchCandidate] = []
-        for work in results:
-            doi = str(work.get("doi") or "").strip()
-            oa_id = str(work.get("id") or "").strip()
-            if doi:
-                # OpenAlex DOIs are full URLs (https://doi.org/...).
-                url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
-            elif oa_id:
-                url = oa_id
-            else:
-                continue  # no resolvable id — skip
-            title = str(work.get("display_name") or "").strip()
-            out.append(SearchCandidate(
-                url=url,
-                title=title,
-                snippet="",
-                source="openalex_search",
-                metadata={
-                    "doi": doi or None,
-                    "openalex_id": oa_id or None,
-                    "year": work.get("publication_year"),
-                },
-            ))
-            if len(out) >= limit:
+        seen_ids: set[str] = set()
+        cursor = "*"
+        for _page in range(max_pages):
+            params: dict[str, Any] = {"search": query, "per_page": per_page}
+            # BYTE-IDENTICAL OFF: only add the cursor param when paging is enabled
+            # (max_pages > 1). A single-page run sends the exact legacy params.
+            if max_pages > 1:
+                params["cursor"] = cursor
+            data = _http_get_json(_OPENALEX_WORKS_SEARCH, params=params)
+            if not data:
+                break
+            results = data.get("results") or []
+            if not results:
+                break
+            for work in results:
+                doi = str(work.get("doi") or "").strip()
+                oa_id = str(work.get("id") or "").strip()
+                if doi:
+                    # OpenAlex DOIs are full URLs (https://doi.org/...).
+                    url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
+                elif oa_id:
+                    url = oa_id
+                else:
+                    continue  # no resolvable id — skip
+                # Dedup across pages by the OpenAlex work id (or the url when absent).
+                _dedup_key = oa_id or url
+                if _dedup_key in seen_ids:
+                    continue
+                seen_ids.add(_dedup_key)
+                title = str(work.get("display_name") or "").strip()
+                out.append(SearchCandidate(
+                    url=url,
+                    title=title,
+                    snippet="",
+                    source="openalex_search",
+                    metadata={
+                        "doi": doi or None,
+                        "openalex_id": oa_id or None,
+                        "year": work.get("publication_year"),
+                    },
+                ))
+                if len(out) >= limit:
+                    return out
+            # Advance the cursor; stop when OpenAlex returns no next cursor.
+            cursor = str((data.get("meta") or {}).get("next_cursor") or "").strip()
+            if max_pages == 1 or not cursor:
                 break
         return out
     except Exception as exc:
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index e9218c0c..874d5675 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -279,6 +279,19 @@ def _serper_search(
         _max_pages = 3
     _n_pages = min(_max_pages, -(-_total // per_page))  # ceil(total/per_page)
 
+    # BB-002 (I-beatboth-fix-000 #1171): a sub-`per_page` page-1 count is NOT a reliable
+    # end-of-results signal for an OFFSET-paginated SERP API — Serper routinely returns
+    # 10 organic on page 1 even when page 2 has more, so the legacy `len(items) < per_page`
+    # break short-circuited before page 2 and the PG_SERPER_TOTAL_PER_QUERY budget was never
+    # reached (de-facto 10/query ceiling — chokepoint #4). When PG_SERPER_STOP_ON_ZERO_NEW=1
+    # the loop keeps offset-paging until (a) budget met, (b) a page returns 0 NEW (post-dedup)
+    # items, or (c) PG_SERPER_MAX_PAGES — the only RELIABLE end-of-results signals. DEFAULT OFF
+    # = byte-identical (the legacy short-page break is preserved). Discovery-breadth only; every
+    # new URL flows through the same fetch -> strict_verify -> 4-role chokepoint unchanged.
+    _stop_on_zero_new = os.getenv("PG_SERPER_STOP_ON_ZERO_NEW", "0").strip() in (
+        "1", "true", "True",
+    )
+
     out: list[dict[str, Any]] = []
     seen: set[str] = set()
     _pages_fetched = 0
@@ -310,14 +323,22 @@ def _serper_search(
                 seen.add(u)
                 out.append(it)
                 _new += 1
-        if len(out) >= _total or len(items) < per_page:
-            break  # budget met, or the provider has no more results for this query.
+        if len(out) >= _total:
+            break  # budget met.
+        if _stop_on_zero_new:
+            # BB-002 (#1171): keep paging past a short page; stop only when a page
+            # added 0 NEW (post-dedup) URLs — the reliable end-of-results signal.
+            if _new == 0:
+                break
+        elif len(items) < per_page:
+            break  # legacy (default OFF): short page -> assume no more results.
     _trace_tool(
         "serper", target=query, status="ok" if out or not _last_err else "fail",
         latency_ms=_last_latency, bytes_sent=len(query), bytes_received=_last_bytes,
         backend_used="serper_api_v1", result_count=len(out),
         pages_fetched=_pages_fetched, num_requested=num, per_page=per_page,
         page_max=_SERPER_PAGE_MAX, clamped=_clamped, total_budget=_total,
+        stop_on_zero_new=_stop_on_zero_new,   # BB-002 (#1171): which stop policy ran
     )
     _trace_query("serper", query, [o["url"] for o in out])
     return out
@@ -397,10 +418,22 @@ def _s2_bulk_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
             "year": p.get("year"),
             "venue": p.get("venue"),
         })
+    # BB-004 (I-beatboth-fix-000 #1171): a HTTP-200 that yields ZERO usable papers
+    # (all lacked oa_pdf + DOI, or `data` was empty) is a DEAD-BACKEND signal — the
+    # legacy unconditional status="ok" reported it as success_rate=1.0 and masked the
+    # collapse (15 S2 calls -> 0 results on drb_90 still showed success). LAW II
+    # silent-downgrade fix: trace a DISTINCT "ok_zero" status + zero_yield=True so the
+    # discovery_funnel / run-health surfaces it LOUDLY instead of as a clean success.
+    # Telemetry/loudness ONLY — no evidence or verification path is touched; the
+    # returned list is unchanged (empty), so downstream control flow is identical.
+    _s2_zero_yield = len(out) == 0
     _trace_tool(
-        "s2", target=query, status="ok", latency_ms=_latency_ms,
+        "s2", target=query,
+        status="ok_zero" if _s2_zero_yield else "ok",
+        latency_ms=_latency_ms,
         bytes_received=_resp_content_len(r),
         backend_used="semantic_scholar_api", result_count=len(out),
+        zero_yield=_s2_zero_yield,
     )
     _trace_query("semantic_scholar", query, [o["url"] for o in out])
     return out
@@ -1578,6 +1611,12 @@ def refetch_for_extraction_with_diagnostics(
 #   PG_ENABLE_LIVE_OA_RESOLVER  default "1"  — master on/off switch.
 #   PG_UNPAYWALL_EMAIL          default placeholder — Unpaywall ToS email.
 # ─────────────────────────────────────────────────────────────────────────────
+# BB-007 (I-beatboth-fix-000 #1171): the placeholder Unpaywall email. The OA resolver treats this
+# (or an empty value) as "resolver unavailable" and fails LOUD (traces a distinct signal) rather than
+# issuing a doomed request that Unpaywall ToS rejects/throttles — a hidden cause of the fetch-fail rate.
+_UNPAYWALL_PLACEHOLDER_EMAIL = "polaris@example.org"
+
+
 def _oa_resolver_enabled() -> bool:
     """True iff the live OA resolver is enabled. Off iff the env var is set to
     a recognized falsey value ("0" / "false" / "no"); default ON."""
@@ -1669,7 +1708,26 @@ def _unpaywall_get_oa_urls(doi: str) -> list[str]:
             _parse_unpaywall_response,
         )
 
-        email = os.getenv("PG_UNPAYWALL_EMAIL", "polaris@example.org")
+        # BB-007 (I-beatboth-fix-000 #1171): Unpaywall ToS REQUIRES a real contact email; the
+        # placeholder polaris@example.org is rejected/throttled, so the resolver silently no-ops
+        # (a hidden cause of the 67-72% fetch-fail rate). FAIL LOUD instead of silent: if the email
+        # is the placeholder (or empty), trace a DISTINCT resolver-unavailable signal and return []
+        # without issuing the doomed request. The benchmark slate must supply a REAL PG_UNPAYWALL_EMAIL.
+        email = os.getenv("PG_UNPAYWALL_EMAIL", _UNPAYWALL_PLACEHOLDER_EMAIL).strip()
+        if not email or email.lower() == _UNPAYWALL_PLACEHOLDER_EMAIL:
+            logger.warning(
+                "[live_retriever] OA resolver UNAVAILABLE: PG_UNPAYWALL_EMAIL is the placeholder "
+                "%r — Unpaywall ToS requires a real contact email. Set a real PG_UNPAYWALL_EMAIL "
+                "to enable OA full-text resolution (doi=%s).",
+                _UNPAYWALL_PLACEHOLDER_EMAIL, doi,
+            )
+            _trace_tool(
+                "oa_resolver", target=doi, status="unavailable",
+                backend_used="unpaywall_v2",
+                error="placeholder_unpaywall_email",
+                resolver_unavailable=True,
+            )
+            return []
         endpoint = "https://api.unpaywall.org/v2/" + doi.strip()
         with _httpx.Client(timeout=10.0) as client:
             response = client.get(endpoint, params={"email": email})
@@ -2184,11 +2242,12 @@ def _lexical_relevance_score(candidate: "SearchCandidate", question_tokens: set[
 # lane. `primary_trial_doi` = #817 layer-4 direct primary-trial DOI seeds; `agentic_seed` =
 # agentic-discovered URLs; `deepener_seed` = citation-snowball deepener URLs (Codex iter-1 P1:
 # these are primary-trial-DERIVED but NOT direct DOI seeds, so they must not pollute
-# `primary_trial_doi` telemetry either). ALL are split out and prepended unranked; FX-15b later
-# makes the web-discovered classes droppable via the host-class filter (telemetry-correctness
-# here is the prerequisite).
+# `primary_trial_doi` telemetry either). BB-006 (#1171): `storm_seed` = STORM interview-search-result
+# URLs harvested URL-ONLY (the synthesized STORM text is NEVER ingested). ALL are split out and
+# prepended unranked; FX-15b later makes the web-discovered classes droppable via the host-class
+# filter (telemetry-correctness here is the prerequisite).
 _SEED_SOURCE_LABELS: frozenset[str] = frozenset(
-    {"primary_trial_doi", "agentic_seed", "deepener_seed"}
+    {"primary_trial_doi", "agentic_seed", "deepener_seed", "storm_seed"}
 )
 
 
diff --git a/src/polaris_graph/retrieval/scope_query_validator.py b/src/polaris_graph/retrieval/scope_query_validator.py
index b7255a0f..7e17dcb2 100644
--- a/src/polaris_graph/retrieval/scope_query_validator.py
+++ b/src/polaris_graph/retrieval/scope_query_validator.py
@@ -18,11 +18,20 @@ time is cheaper than fetching and discarding.
 DESIGN:
 - No new LLM call. Uses token overlap with protocol.research_question +
   PICO fields (intervention / population / outcome) as the anchor.
-- Drops any amplified query whose Jaccard similarity with the anchor
-  is below PG_AMPLIFIER_SCOPE_FLOOR (default 0.15).
+- Drops any amplified query whose similarity with the anchor is below
+  PG_AMPLIFIER_SCOPE_FLOOR (default 0.15).
 - ALWAYS keeps the verbatim research_question and direct PICO-term
   queries ("{intervention} {population}") as a safety net.
 - Logs drops so the user can see which amplifier variants were killed.
+
+SIMILARITY MEASURE (BB-001, I-beatboth-fix-000 #1171):
+- PG_SCOPE_SIM_MEASURE selects the measure: `jaccard` (default = byte-identical
+  OFF) or `containment`. Symmetric Jaccard (|q∩a|/|q∪a|) punishes a SHORT
+  on-topic query against a large anchor bag (tiny intersection over a huge
+  union) — the #1 retrieval-breadth chokepoint (40->5 kept on drb_72).
+  Containment/overlap-coefficient (|q∩a|/min(|q|,|a|)) normalises by the
+  smaller set so a short on-topic query clears while genuine drift still fails.
+  The GATE is KEPT either way (rerank against intent); only the measure changes.
 """
 
 from __future__ import annotations
@@ -65,7 +74,7 @@ def _tokenize(text: str) -> set[str]:
 
 
 def _jaccard(a: set[str], b: set[str]) -> float:
-    """Jaccard similarity. Empty a or b -> 0.0."""
+    """Jaccard (symmetric) similarity |a∩b| / |a∪b|. Empty a or b -> 0.0."""
     if not a or not b:
         return 0.0
     union = a | b
@@ -73,6 +82,46 @@ def _jaccard(a: set[str], b: set[str]) -> float:
     return len(inter) / len(union) if union else 0.0
 
 
+def _containment(a: set[str], b: set[str]) -> float:
+    """Containment / overlap-coefficient similarity |a∩b| / min(|a|, |b|).
+
+    BB-001 (I-beatboth-fix-000 #1171): the symmetric Jaccard punishes a SHORT
+    on-topic query against a LARGE anchor bag — a 4-6-token query has a tiny
+    intersection over a huge union, so its sim sits far below the floor and the
+    query is dropped before it ever issues a search (the #1 retrieval-breadth
+    chokepoint: 40->5 kept on drb_72). Containment normalises by the SMALLER set,
+    so a short query whose tokens are all in the anchor scores ~1.0 while a query
+    that drifts off-anchor still scores low — it KEEPS the gate (reranks against
+    intent) rather than removing it. Empty a or b -> 0.0; never raises.
+    """
+    if not a or not b:
+        return 0.0
+    inter = a & b
+    smaller = min(len(a), len(b))
+    return len(inter) / smaller if smaller else 0.0
+
+
+# BB-001 (I-beatboth-fix-000 #1171): the default is `jaccard` so the OFF path is
+# BYTE-IDENTICAL to the pre-fix behaviour; the Gate-B slate sets `containment`.
+_SIM_MEASURES = {"jaccard": _jaccard, "containment": _containment}
+
+
+def _select_sim_measure():
+    """Return the (name, fn) for the configured similarity measure.
+
+    Reads ``PG_SCOPE_SIM_MEASURE`` (default ``jaccard`` = byte-identical OFF).
+    An unrecognised value FAILS LOUD (LAW II) — a typo'd measure must not
+    silently fall back to a different gate behaviour on a paid benchmark run.
+    """
+    raw = os.getenv("PG_SCOPE_SIM_MEASURE", "jaccard").strip().lower()
+    if raw not in _SIM_MEASURES:
+        raise ValueError(
+            f"PG_SCOPE_SIM_MEASURE={raw!r} is not a recognised similarity measure "
+            f"(expected one of {sorted(_SIM_MEASURES)})."
+        )
+    return raw, _SIM_MEASURES[raw]
+
+
 @dataclass
 class ValidationResult:
     """Return value of validate_amplified_queries()."""
@@ -148,6 +197,11 @@ def validate_amplified_queries(
     if floor is None:
         floor = float(os.getenv("PG_AMPLIFIER_SCOPE_FLOOR", "0.15"))
 
+    # BB-001 (#1171): default `jaccard` = byte-identical OFF; the Gate-B slate
+    # sets `containment` so short on-topic queries clear the floor. The gate is
+    # KEPT either way (off-anchor queries still fail) — only the MEASURE changes.
+    sim_name, sim_fn = _select_sim_measure()
+
     anchor_tokens = _build_anchor_tokens(protocol)
     anchor_tokens_sorted = sorted(anchor_tokens)
 
@@ -170,11 +224,17 @@ def validate_amplified_queries(
         if not q_tokens:
             dropped.append((q, 0.0, "empty_after_tokenization"))
             continue
-        sim = _jaccard(q_tokens, anchor_tokens)
+        sim = sim_fn(q_tokens, anchor_tokens)
         if sim >= floor:
             kept.append(q)
         else:
-            dropped.append((q, sim, f"below_scope_floor_{floor:.2f}"))
+            # BB-001 (#1171): on the default jaccard path the reason string is
+            # BYTE-IDENTICAL to the pre-fix value; the measure suffix is added
+            # only when a non-default measure (containment) is active.
+            _reason = f"below_scope_floor_{floor:.2f}"
+            if sim_name != "jaccard":
+                _reason = f"{_reason}_{sim_name}"
+            dropped.append((q, sim, _reason))
 
     # Safety net: always keep the verbatim research_question, even if
     # its own similarity was below floor (happens for very short PICO
@@ -184,8 +244,8 @@ def validate_amplified_queries(
             kept.insert(0, research_question)
 
     logger.info(
-        "[scope_validator] floor=%.2f kept=%d dropped=%d (anchor_tokens=%d)",
-        floor, len(kept), len(dropped), len(anchor_tokens),
+        "[scope_validator] measure=%s floor=%.2f kept=%d dropped=%d (anchor_tokens=%d)",
+        sim_name, floor, len(kept), len(dropped), len(anchor_tokens),
     )
     if dropped:
         sample = dropped[:3]
diff --git a/tests/polaris_graph/test_breadth_collapse_beatboth_fix_000.py b/tests/polaris_graph/test_breadth_collapse_beatboth_fix_000.py
new file mode 100644
index 00000000..f842ef5b
--- /dev/null
+++ b/tests/polaris_graph/test_breadth_collapse_beatboth_fix_000.py
@@ -0,0 +1,481 @@
+"""I-beatboth-fix-000 (#1171) — RETRIEVAL BREADTH-COLLAPSE chain — offline funnel-delta smokes.
+
+Each test asserts ONE sub-fix's discovery-funnel widening AND that the default-OFF path is
+byte-identical. ALL OFFLINE (no network): the HTTP/agentic/STORM seams are stubbed. None of these
+fixes touch strict_verify, the entailment/NLI judge, or the 4-role seam — every test here is purely
+DISCOVERY-breadth (candidates) or telemetry/observability.
+
+  BB-001  scope-validator: containment keeps short on-topic queries that jaccard drops; OFF identical.
+  BB-002  Serper page loop: PG_SERPER_STOP_ON_ZERO_NEW continues past a sub-per_page page; OFF identical.
+  BB-003  OpenAlex search: cursor paging accumulates across pages > the legacy 25; OFF single page.
+  BB-004  Semantic Scholar: a HTTP-200 zero-yield traces a DISTINCT ok_zero/zero_yield (not silent ok).
+  BB-005  agentic harvest: harvest cap decoupled from fetch cap (discovery telemetry only).
+  BB-006  STORM web_results: harvest_storm_urls returns ONLY web_results[*].url, NEVER synthesized text.
+  BB-007  OA resolver: placeholder PG_UNPAYWALL_EMAIL -> resolver-unavailable trace (no silent no-op).
+"""
+from __future__ import annotations
+
+import logging
+
+import pytest
+
+import src.polaris_graph.retrieval.domain_backends as db
+import src.polaris_graph.retrieval.live_retriever as lr
+from src.polaris_graph.retrieval.agentic_url_harvester import (
+    harvest_agentic_urls,
+    harvest_storm_urls,
+)
+from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
+from src.polaris_graph.retrieval.scope_query_validator import (
+    validate_amplified_queries,
+)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-001 — scope-validator containment vs jaccard
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _wide_anchor_protocol() -> dict:
+    """A ~30-token anchor (research_question + PICO) — the size that punishes short
+    on-topic queries under symmetric Jaccard (tiny intersection / huge union)."""
+    return {
+        "research_question": (
+            "To what extent will artificial intelligence and automation technologies "
+            "displace or transform jobs across the labor market over the next decade, "
+            "and what does the empirical economics literature conclude about net "
+            "employment effects and wage polarization in advanced economies?"
+        ),
+        "population": "workers in advanced economies",
+        "intervention": "artificial intelligence automation",
+        "outcome": "employment wages displacement",
+    }
+
+
+# Eight SHORT (4-6 token) on-topic queries — each shares a few anchor terms but its
+# union with the 30-token anchor is huge, so jaccard sits far under any sane floor.
+_SHORT_ONTOPIC = [
+    "automation employment effects",
+    "artificial intelligence labor market",
+    "wage polarization advanced economies",
+    "job displacement automation decade",
+    "net employment effects automation",
+    "labor market transformation technology",
+    "economics literature automation jobs",
+    "ai workers displacement wages",
+]
+
+
+def test_bb001_containment_keeps_short_ontopic_where_jaccard_drops(monkeypatch):
+    """At the legacy code-default floor 0.15 (the forensic's chokepoint: "floor=0.15 kept=5
+    dropped=35"), symmetric jaccard drops the short on-topic queries (all score 0.067-0.143 < 0.15
+    against the 28-token anchor) while containment keeps them. Funnel delta: jaccard <=2 kept,
+    containment >=7 kept — the #1 retrieval-breadth chokepoint widened."""
+    proto = _wide_anchor_protocol()
+    floor = 0.15  # the legacy code default — the exact floor the forensic recorded the collapse at
+
+    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "jaccard")
+    jac = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=floor)
+    # research_question is always prepended (always_keep_anchor); count only the 8 amplified.
+    jac_kept = [q for q in jac.kept if q in _SHORT_ONTOPIC]
+
+    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "containment")
+    con = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=floor)
+    con_kept = [q for q in con.kept if q in _SHORT_ONTOPIC]
+
+    assert len(jac_kept) <= 2, f"jaccard should drop most short on-topic queries, kept {jac_kept}"
+    assert len(con_kept) >= 7, f"containment should keep short on-topic queries, kept {con_kept}"
+
+
+def test_bb001_off_default_is_jaccard_byte_identical(monkeypatch):
+    """Unset PG_SCOPE_SIM_MEASURE == explicit jaccard == legacy behaviour (kept/dropped identical)."""
+    proto = _wide_anchor_protocol()
+    monkeypatch.delenv("PG_SCOPE_SIM_MEASURE", raising=False)
+    default = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=0.08)
+    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "jaccard")
+    explicit = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=0.08)
+    assert default.kept == explicit.kept
+    # OFF reason string carries NO measure suffix (byte-identical legacy reason).
+    assert all(r.startswith("below_scope_floor_") and not r.endswith("jaccard")
+               for _q, _s, r in default.dropped)
+
+
+def test_bb001_containment_still_drops_genuine_drift(monkeypatch):
+    """The gate is KEPT, not removed: off-anchor drift still fails under containment."""
+    proto = _wide_anchor_protocol()
+    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "containment")
+    drift = ["Japan national health insurance elderly care", "blockchain agriculture supply chain"]
+    res = validate_amplified_queries(drift, proto, floor=0.08)
+    dropped_q = [d[0] for d in res.dropped]
+    assert any("Japan" in q for q in dropped_q)
+    assert any("blockchain" in q for q in dropped_q)
+
+
+def test_bb001_unrecognised_measure_fails_loud(monkeypatch):
+    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "cosine")
+    with pytest.raises(ValueError):
+        validate_amplified_queries(["x y z"], _wide_anchor_protocol(), floor=0.08)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-002 — Serper page loop (stop-on-zero-new)
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _install_serper_pages(monkeypatch, pages: dict[int, list[str]]):
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
+def test_bb002_stop_on_zero_new_continues_past_short_page(monkeypatch):
+    """With the flag ON, a sub-per_page page that adds NEW urls does NOT stop the loop."""
+    monkeypatch.setenv("PG_SERPER_STOP_ON_ZERO_NEW", "1")
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
+    # page 1: only 5 urls (< per_page 20) but all NEW -> must continue; page 2: 8 more NEW.
+    calls = _install_serper_pages(monkeypatch, {
+        1: [f"https://x/{i}" for i in range(5)],
+        2: [f"https://x/{i}" for i in range(5, 13)],
+        3: [],  # zero new -> stop
+    })
+    out = lr._serper_search("q", num=20)
+    assert calls == [1, 2, 3], f"expected to page past the short page, got {calls}"
+    assert len(out) == 13
+
+
+def test_bb002_stop_on_zero_new_stops_on_duplicate_page(monkeypatch):
+    """A page that adds 0 NEW (all duplicates) stops the loop even with budget remaining."""
+    monkeypatch.setenv("PG_SERPER_STOP_ON_ZERO_NEW", "1")
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "200")
+    monkeypatch.setenv("PG_SERPER_MAX_PAGES", "5")
+    calls = _install_serper_pages(monkeypatch, {
+        1: [f"https://x/{i}" for i in range(20)],
+        2: [f"https://x/{i}" for i in range(20)],  # all duplicates -> 0 new -> stop
+        3: [f"https://x/{i}" for i in range(40, 60)],  # never reached
+    })
+    out = lr._serper_search("q", num=20)
+    assert calls == [1, 2], f"duplicate page should stop the loop, got {calls}"
+    assert len(out) == 20
+
+
+def test_bb002_off_default_short_page_stops_byte_identical(monkeypatch):
+    """OFF (default): a sub-per_page page-1 stops immediately — the legacy FX-17 behaviour."""
+    monkeypatch.delenv("PG_SERPER_STOP_ON_ZERO_NEW", raising=False)
+    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
+    calls = _install_serper_pages(monkeypatch, {
+        1: [f"https://x/{i}" for i in range(5)],
+        2: [f"https://x/{i}" for i in range(5, 13)],  # would be reached only if the flag were on
+    })
+    out = lr._serper_search("q", num=20)
+    assert calls == [1], f"OFF must stop on the short page (legacy), got {calls}"
+    assert len(out) == 5
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-003 — OpenAlex cursor paging
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _make_oa_works(start: int, n: int) -> list[dict]:
+    return [
+        {"id": f"https://openalex.org/W{i}", "doi": "", "display_name": f"work {i}",
+         "publication_year": 2023}
+        for i in range(start, start + n)
+    ]
+
+
+def test_bb003_cursor_paging_accumulates_past_25(monkeypatch):
+    """With per_page=200 + max_pages>1, the cursor loop accumulates across pages (> the legacy 25)."""
+    monkeypatch.setenv("PG_OPENALEX_PER_PAGE", "200")
+    monkeypatch.setenv("PG_OPENALEX_MAX_PAGES", "3")
+    seen_params: list[dict] = []
+    pages = {
+        "*": {"results": _make_oa_works(0, 200), "meta": {"next_cursor": "c2"}},
+        "c2": {"results": _make_oa_works(200, 200), "meta": {"next_cursor": "c3"}},
+        "c3": {"results": _make_oa_works(400, 50), "meta": {"next_cursor": None}},
+    }
+
+    def _fake_get_json(url, params=None):
+        seen_params.append(dict(params or {}))
+        return pages.get((params or {}).get("cursor"), {"results": [], "meta": {}})
+
+    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
+    # limit=450 so the loop must consume all 3 cursor pages (200+200+50) to accumulate past 25.
+    out = db.openalex_search("automation labor", limit=450)
+    assert len(out) == 450, f"cursor loop should accumulate across pages, got {len(out)}"
+    assert len(out) > 25, "BB-003: must accumulate well past the legacy 25/query single-page cap"
+    # per_page=200 sent (the OpenAlex max), and the cursor param threaded across all 3 pages.
+    assert all(p["per_page"] == 200 for p in seen_params)
+    assert seen_params[0]["cursor"] == "*"
+    assert len(seen_params) == 3
+    assert [p["cursor"] for p in seen_params] == ["*", "c2", "c3"]
+
+
+def test_bb003_off_default_single_page_no_cursor_byte_identical(monkeypatch):
+    """OFF (per_page unset=25, max_pages unset=1): exactly the legacy single 25-cap request, no cursor."""
+    monkeypatch.delenv("PG_OPENALEX_PER_PAGE", raising=False)
+    monkeypatch.delenv("PG_OPENALEX_MAX_PAGES", raising=False)
+    seen_params: list[dict] = []
+
+    def _fake_get_json(url, params=None):
+        seen_params.append(dict(params or {}))
+        return {"results": _make_oa_works(0, 25), "meta": {"next_cursor": "c2"}}
+
+    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
+    out = db.openalex_search("automation labor", limit=100)
+    assert len(seen_params) == 1, "OFF must issue exactly one page"
+    assert "cursor" not in seen_params[0], "OFF request must NOT carry a cursor param (byte-identical)"
+    assert seen_params[0]["per_page"] == 25  # max(1, min(100, 25))
+    assert len(out) == 25
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-004 — Semantic Scholar zero-yield loud signal
+# ─────────────────────────────────────────────────────────────────────────────
+
+class _FakeResp:
+    def __init__(self, status_code, payload):
+        self.status_code = status_code
+        self._payload = payload
+        self.content = b"{}"
+
+    def json(self):
+        return self._payload
+
+
+class _FakeClient:
+    def __init__(self, *a, **k):
+        pass
+
+    def __enter__(self):
+        return self
+
+    def __exit__(self, *a):
+        return False
+
+
+def _install_s2(monkeypatch, payload):
+    traced: list[dict] = []
+
+    def _fake_get(self, url, params=None, headers=None):
+        return _FakeResp(200, payload)
+
+    monkeypatch.setattr(_FakeClient, "get", _fake_get, raising=False)
+    monkeypatch.setattr(lr.httpx, "Client", lambda *a, **k: _FakeClient())
+
+    def _fake_trace(tool_name, **kw):
+        if tool_name == "s2":
+            traced.append({"tool": tool_name, **kw})
+
+    monkeypatch.setattr(lr, "_trace_tool", _fake_trace)
+    monkeypatch.setattr(lr, "_trace_query", lambda *a, **k: None)
+    return traced
+
+
+def test_bb004_zero_yield_traces_distinct_signal(monkeypatch):
+    """A HTTP-200 with 0 usable papers traces status=ok_zero + zero_yield=True (NOT silent ok)."""
+    traced = _install_s2(monkeypatch, {"data": []})
+    out = lr._s2_bulk_search("metformin", limit=12)
+    assert out == []
+    s2_row = traced[-1]
+    assert s2_row["status"] == "ok_zero", f"zero-yield must trace ok_zero, got {s2_row['status']}"
+    assert s2_row["zero_yield"] is True
+    assert s2_row["result_count"] == 0
+
+
+def test_bb004_nonzero_yield_stays_ok(monkeypatch):
+    """A normal yield stays status=ok with zero_yield=False (byte-identical success semantics)."""
+    payload = {"data": [
+        {"title": "p", "abstract": "a", "openAccessPdf": {"url": "https://oa/p.pdf"},
+         "externalIds": {"DOI": "10.1/x"}, "paperId": "P1", "year": 2023, "venue": "v"},
+    ]}
+    traced = _install_s2(monkeypatch, payload)
+    out = lr._s2_bulk_search("metformin", limit=12)
+    assert len(out) == 1
+    s2_row = traced[-1]
+    assert s2_row["status"] == "ok"
+    assert s2_row["zero_yield"] is False
+    assert s2_row["result_count"] == 1
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-005 — agentic harvest cap honored (decoupled from fetch)
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _agentic_result_with(n: int) -> dict:
+    return {"web_results": [{"url": f"https://a/{i}", "title": "t", "snippet": "s"} for i in range(n)]}
+
+
+def test_bb005_harvest_cap_honored_dedup_intact():
+    """harvest_agentic_urls(result_with_1933, cap=800) returns 800 (the raised discovery cap)."""
+    res = _agentic_result_with(1933)
+    out = harvest_agentic_urls(res, cap=800)
+    assert len(out) == 800
+    assert len(set(out)) == 800  # dedup intact
+
+
+def test_bb005_harvest_cap_smaller_than_discovered_truncates():
+    """The fetch cap (100) truncates the harvested set — the budget-respecting fetch subset."""
+    res = _agentic_result_with(1933)
+    out = harvest_agentic_urls(res, cap=100)
+    assert len(out) == 100
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-006 — STORM URL-ONLY harvest (faithfulness contract)
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _storm_out_with(n: int) -> dict:
+    """A STORM result carrying web_results URLs AND synthesized text that must NEVER be harvested."""
+    return {
+        "storm_conversations": [{"q": "interview q", "a": "interview answer text"}],
+        "storm_outline": ["section 1", "section 2"],
+        "web_results": [
+            {"url": f"https://storm/{i}", "title": f"title {i}",
+             "snippet": f"SYNTHESIZED-SNIPPET-{i}-must-not-be-evidence"}
+            for i in range(n)
+        ],
+        "academic_results": [{"url": f"https://storm-ac/{i}", "title": "ac", "snippet": "ac snip"}
+                             for i in range(3)],
+        # synthesized fields that must NEVER appear in the harvest:
+        "answer": "STORM SYNTHESIZED ANSWER — this is a paraphrase and must not be evidence",
+        "key_findings": ["STORM KEY FINDING that is an LLM paraphrase"],
+    }
+
+
+def test_bb006_harvest_storm_urls_returns_only_urls():
+    """harvest_storm_urls returns ONLY web_results/academic_results URLs — never synthesized text."""
+    out = harvest_storm_urls(_storm_out_with(478), cap=200)
+    assert len(out) == 200  # capped
+    # Every returned item is a fetchable URL from the result streams.
+    assert all(u.startswith("https://storm") for u in out)
+    # The HARD contract: no synthesized STORM text leaked into the harvest.
+    blob = " ".join(out)
+    assert "SYNTHESIZED-SNIPPET" not in blob
+    assert "SYNTHESIZED ANSWER" not in blob
+    assert "KEY FINDING" not in blob
+    assert "interview answer" not in blob
+
+
+def test_bb006_harvest_storm_urls_deduped_and_capped():
+    out = harvest_storm_urls(_storm_out_with(50), cap=200)
+    assert len(out) == len(set(out))      # deduped
+    assert len(out) == 53                 # 50 web + 3 academic, all distinct
+
+
+def test_bb006_harvest_storm_urls_empty_safe():
+    assert harvest_storm_urls(None, cap=200) == []
+    assert harvest_storm_urls({}, cap=200) == []
+    assert harvest_storm_urls(_storm_out_with(10), cap=0) == []
+
+
+def test_bb006_storm_snippet_never_becomes_direct_quote():
+    """A STORM seed URL flows as a URL-only candidate: harvest never carries the snippet as a quote.
+
+    (The seed re-fetch makes direct_quote the verbatim FETCHED span; the harvest output is a bare
+    URL string — there is no field through which the synthesized snippet could ride as evidence.)
+    """
+    out = harvest_storm_urls(_storm_out_with(5), cap=200)
+    assert all(isinstance(u, str) and u.startswith("http") for u in out)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB-007 — OA resolver placeholder-email guard
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_bb007_placeholder_email_traces_resolver_unavailable(monkeypatch):
+    """The placeholder PG_UNPAYWALL_EMAIL -> resolver-unavailable trace + [] (no silent no-op)."""
+    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "polaris@example.org")
+    traced: list[dict] = []
+    monkeypatch.setattr(lr, "_trace_tool",
+                        lambda tool, **kw: traced.append({"tool": tool, **kw}))
+
+    def _boom_client(*a, **k):
+        raise AssertionError("Unpaywall must NOT be called with the placeholder email")
+    monkeypatch.setattr(lr.httpx, "Client", _boom_client)
+
+    out = lr._unpaywall_get_oa_urls("10.1056/NEJMoa2307563")
+    assert out == []
+    oa_rows = [t for t in traced if t["tool"] == "oa_resolver"]
+    assert oa_rows, "expected an oa_resolver trace row"
+    assert oa_rows[-1]["status"] == "unavailable"
+    assert oa_rows[-1].get("resolver_unavailable") is True
+    assert oa_rows[-1].get("error") == "placeholder_unpaywall_email"
+
+
+def test_bb007_empty_email_also_unavailable(monkeypatch):
+    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "")
+    monkeypatch.setattr(lr, "_trace_tool", lambda *a, **k: None)
+    monkeypatch.setattr(lr.httpx, "Client",
+                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
+    assert lr._unpaywall_get_oa_urls("10.1/x") == []
+
+
+def test_bb007_real_email_resolves_stubbed(monkeypatch):
+    """A REAL email lets the resolver fire; with a stubbed OA response it returns the OA url(s)."""
+    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "research@polaris-dr.org")
+    monkeypatch.setattr(lr, "_trace_tool", lambda *a, **k: None)
+
+    class _Resp:
+        status_code = 200
+
+        def json(self):
+            return {"is_oa": True, "best_oa_location": {"url_for_pdf": "https://oa/full.pdf"}}
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
+        def get(self, *a, **k):
+            return _Resp()
+
+    monkeypatch.setattr(lr.httpx, "Client", lambda *a, **k: _Client())
+    # Stub the shared parser to the canonical OA-URL shape.
+    import src.polaris_graph.retrieval.frame_fetcher as ff
+    monkeypatch.setattr(
+        ff, "_parse_unpaywall_response",
+        lambda d: {"is_oa": True, "oa_pdf_url": "https://oa/full.pdf", "oa_html_url": ""},
+    )
+    out = lr._unpaywall_get_oa_urls("10.1056/NEJMoa2307563")
+    assert out == ["https://oa/full.pdf"]
+
+
+def test_bb007_openalex_search_doi_threads_to_candidate_metadata(monkeypatch):
+    """BB-007 part-2 regression: an openalex_search candidate WITH a DOI carries it in metadata
+    AND its URL is doi.org — so _candidate_oa_hints + _extract_doi_from_url both surface the DOI to
+    the OA resolver. (A DOI-less work gets an openalex.org/W url with metadata['doi']=None; there is
+    genuinely no DOI to thread, so the resolver correctly cannot fire — not a bug.)"""
+    def _fake_get_json(url, params=None):
+        return {"results": [
+            {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/withdoi",
+             "display_name": "has doi", "publication_year": 2023},
+            {"id": "https://openalex.org/W2", "doi": "", "display_name": "no doi",
+             "publication_year": 2022},
+        ], "meta": {}}
+
+    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
+    monkeypatch.delenv("PG_OPENALEX_PER_PAGE", raising=False)
+    monkeypatch.delenv("PG_OPENALEX_MAX_PAGES", raising=False)
+    out = db.openalex_search("q", limit=10)
+    by_title = {c.title: c for c in out}
+    # WITH-doi candidate: url is doi.org AND metadata carries the DOI -> resolver can fire.
+    with_doi = by_title["has doi"]
+    assert with_doi.url.startswith("https://doi.org/")
+    assert with_doi.metadata["doi"] == "https://doi.org/10.1/withdoi"
+    assert lr._candidate_oa_hints(with_doi.metadata)[0] == "https://doi.org/10.1/withdoi"
+    # NO-doi candidate: openalex.org/W url, metadata doi None -> genuinely no DOI to thread.
+    no_doi = by_title["no doi"]
+    assert no_doi.url.startswith("https://openalex.org/W")
+    assert no_doi.metadata["doi"] is None
+    assert lr._candidate_oa_hints(no_doi.metadata)[0] == ""

```
