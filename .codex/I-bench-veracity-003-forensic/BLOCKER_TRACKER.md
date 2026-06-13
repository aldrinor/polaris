# POLARIS pipeline blocker tracker (drb_72 dual forensic, 2026-06-12)

Source: Codex forensic `.codex/I-bench-veracity-003-forensic/all_blockers_codex.txt` (12 blockers,
0 P0-corruption). Claude cross-check (Workflow wqft41ato) pending — reconcile + dedupe on landing.
Standard per operator: each blocker FOUND -> FIXED -> UNIT-TESTED -> A/B-PROVEN gone, dual-verified,
BEFORE the full Q1 sweep. Faithfulness gates (strict_verify/NLI/4-role) NEVER relaxed by any fix.

## Status legend: OPEN / FIXING / FIXED / PROVEN

| # | Blocker | Sev | Status | Fix | Test |
|---|---------|-----|--------|-----|------|
| 1 | Crawl4AI cross-loop semaphore (553 EPIPE fetch fails) — access_bypass.py:118/132/1393 | P1 | OPEN | per-loop semaphore (or drop global, use threading.BoundedSemaphore) | multi-event-loop fetch test + re-run: fails ~553->~0 |
| 2 | Corpus-quality readiness gate FAILS OPEN (skewed mix accepted as sweep-ready) — run_honest_sweep_r3.py:4412 | P1 | OPEN | benchmark mode: abort/operator-override on material tier deviation; keep disclosure but not sweep-ready | skewed corpus -> must stop; good -> pass |
| 3 | Quantified-analysis silent NO-OP (1636 numbers, no spec, returns None) — run_honest_sweep_r3.py:6069/6114, quantified_analysis.py:368 | P1 | OPEN | typed statuses (declined/empty_transport/parse_error) + retry + readiness fail if force-on & empty | run w/ numbers -> output or loud reason; forced+empty -> fail |
| 4 | Planner OFF -> breadth knobs dead code | P1 | FIXED (PR-2) | _augment_legacy_section_breadth in legacy path (21->29) | 15 unit tests + live A/B; ADD canary: fail run if breadth < target |
| 5 | Relevance floor over-cuts (589->353) + hides as dropped=0 — evidence_selector.py:1311/1340 | P1 | OPEN | report real drops; per-facet/embedding relevance; preserve anchors; per-tier tune | re-run: honest drop count + fewer good cut |
| 6 | 150-source outline menu cap — multi_section_generator.py:89/1313 | P2 | MITIGATED | opened to 360 in max run | 150 vs 360 sensitivity run + menu-coverage-vs-cited log |
| 7 | V30 contract 7-source ceiling + required-entity lane merged 0 — run_honest_sweep_r3.py:4921, required_entity_retrieval.py:70/90 | P1 | OPEN | widen contract retrieval/backfill per entity; canonicalize DOI/URL; log why-not-merged; strict slot verify unchanged | re-run: more contract sources + fewer gaps |
| 8 | Empty URLs in final bibliography — run_honest_sweep_r3.py:4925, multi_section_generator.py:3838 | P1 | OPEN | require URL/DOI locator for cited entries or emit non-cited gap | re-run: 0 cited entries with blank URL |
| 9 | 4-role blank-verdict stall (slow) + manifest can mark success pre-D8 — openrouter_role_transport.py:696/976 | P1 | OPEN | preflight structured-output providers; bound blank retries; success impossible until D8 done | re-run: faster audit + no success w/o D8 |
| 10 | V30 Phase-2 broad-except silently falls back to legacy — run_honest_sweep_r3.py:5050 | P2 | OPEN | benchmark mode: V30 failure fatal unless explicitly disabled | force contract error -> must stop |
| 11 | Completeness 0/0 passes vacuously — completeness_checker.py:52/87, evaluator_gate.py:190 | P1 | OPEN | require measured coverage denominator (planner facets/checklist); 0/0 = not-ready | empty checklist -> not-ready; real -> measured |
| 12 | Required-entity lane additive/under-cap (12 entities/3 URLs) — required_entity_retrieval.py:70/90 | P2 | OPEN | (folds into #7) raise caps + readiness-fail if enabled-but-0-merged-with-gaps | re-run: lane merges or fails loudly |

## TOP-3 to fix before the full sweep (Codex): #1 Crawl4AI, #2+#11 corpus-skew/completeness fail-open, #3 quantified no-op.

## HEALTHY — do NOT touch
strict_verify drops, contract gap disclosures, fact-dedup rewrites dropped by strict_verify,
finding-dedup distinct=23 (numeric-claim grouping, NOT a source-breadth drop), Serper page clamping.

## Sequence: finish breadth A/B (prove >=30+) -> reconcile Claude cross-check -> fix TIER-1 (#1,#2,#3,#11)
one at a time with proof -> then breadth guards (#4 canary, #5, #6) -> cleanliness/reliability
(#7,#8,#9,#10,#12) -> only then full Q1 sweep. Each: GitHub issue -> fix -> unit test -> A/B re-run proof.

## GitHub issues (created 2026-06-12): I-pipe-001..018 = #1226..#1243
## Claude cross-check ADDED (beyond Codex): I-pipe-004 (off-topic ev_412 in MY fix), I-pipe-005 (constraint-as-query), I-pipe-006 (marquee anchors 0 prose), I-pipe-007 (span over-concentration 18-19x). CORRECTION: runs were NOT noZyte (Zyte active 160 fetches).
## Remediation: parallel Claude+Codex Workflow, file-disjoint groups, faithfulness gates LOCKED, then ONE consolidated drb_72 A/B proving: breadth >=40, 0 off-topic, marquee present, D8 finishes, no fail-open.
