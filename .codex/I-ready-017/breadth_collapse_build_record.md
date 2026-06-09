# I-beatboth-fix-000 (#1171) RETRIEVAL-BREADTH cluster — BUILD RECORD (offline, no spend)

Branch: bot/I-ready-017-faithfulness. ONE coherent change. All DISCOVERY-only, default-OFF
byte-identical, Gate-B slate activates each. NO commit (per task).

## Files changed (6 + 1 new test)
- src/polaris_graph/retrieval/scope_query_validator.py  (BB-001 containment measure)
- src/polaris_graph/retrieval/live_retriever.py          (BB-002 serper stop-on-zero-new; BB-004 s2 zero-yield; BB-007 unpaywall placeholder guard; storm_seed label)
- src/polaris_graph/retrieval/domain_backends.py         (BB-003 openalex cursor paging)
- src/polaris_graph/retrieval/agentic_url_harvester.py   (BB-006 harvest_storm_urls)
- scripts/run_honest_sweep_r3.py                         (BB-005 harvest/fetch decouple; BB-006 STORM ingest + seed lane)
- scripts/dr_benchmark/run_gate_b.py                     (slate + force-exact + BB-001 preflight)
- tests/polaris_graph/test_breadth_collapse_beatboth_fix_000.py (NEW, 21 offline smokes)

## Smoke: 21 new pass; 90 touched-module existing pass; 391 (new+dr_benchmark) pass; 10/10 faithfulness files byte-unchanged.

## Key honesty corrections vs the design (recorded, not hidden)
- BB-005: PG_AGENTIC_BENCHMARK_URL_CAP is BOTH the discovery harvest cap AND the agentic FETCH lane
  (run_honest_sweep_r3.py:3284), and in seed_only mode run_live_retrieval fetches EVERY seed. So a
  slate bump to 800 would overshoot the operator <=1000 fetch envelope (main 800 + agentic 100 +
  deepener 60 + R6 40 = 1000). FIX: decouple — new PG_AGENTIC_HARVEST_CAP widens DISCOVERY TELEMETRY
  (urls_discovered_total) only; fetch stays truncated to the budgeted PG_AGENTIC_BENCHMARK_URL_CAP=100.
- BB-006: the STORM fetch is a SEPARATE lane ADDITIVE to the four-lane budget; bounded by
  PG_STORM_URL_FETCH_CAP=60 and disclosed for operator accounting (not silently overshooting).
- BB-007 part-2 (thread the OpenAlex DOI): ALREADY wired (live_retriever.py:2752 _candidate_oa_hints
  threads metadata['doi'] -> doi_hint for every candidate). A DOI-bearing openalex work already gets a
  doi.org URL + metadata doi; a DOI-less work has no DOI to thread. So part-2 is a regression TEST, not
  new code. The real BB-007 code = the placeholder-email guard (part-1).
- BB-001 slate float-truncation trap: PG_AMPLIFIER_SCOPE_FLOOR=0.08 through the numeric FLOOR path
  int()-truncates to 0 (sim>=0 always true -> gate DISABLED). FIX: force-exact + a (0,1] preflight.
