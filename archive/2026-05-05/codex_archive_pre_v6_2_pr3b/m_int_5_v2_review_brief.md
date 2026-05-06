# Codex round 2 — M-INT-5 v2

## Round-1 close
v1 had 1 HIGH + 1 MEDIUM. Both fixed in v2 (commit 44543fa):

### HIGH: malformed M-INT-4 dict aborted run_one_query (FIXED)
- v1 used `dict["confidence"]` etc. directly in M-INT-4 log
  line at lines 875-878, BEFORE the M-INT-5 try block
- Codex repro: `_classify_scope_with_llm` returns
  `{"verdict": "in_scope"}` (missing other keys) → KeyError →
  outer handler aborts with status=error
- Violates LAW II best-effort telemetry
- v2 fix: `.get()` throughout the M-INT-4 log line; both M-INT-4
  log + M-INT-5 synthesis wrapped in try/except. Defensive
  enum_map.get() with UNCERTAIN fallback if verdict string
  unrecognized.

### MEDIUM: lost original LLM domain tag on UNKNOWN_DOMAIN (FIXED)
- v1 `summary["domain"]` was result.template.domain_id —
  None for non-routed outcomes. The LLM-asserted domain
  ("aerospace") was lost from telemetry.
- v2 fix: added `requested_domain` to the summary dict.
  `_route_query_to_domain` accepts an optional `requested_domain`
  kwarg (default: classification.domain). The sweep wires it
  from the M-INT-4 dict; the routing log line includes both
  `domain` (matched template) and `requested_domain` (LLM-asserted).

## v2 regression tests
4 new:
- test_route_unknown_domain_preserves_original_domain_tag (M repro)
- test_route_routed_domain_matches_requested (M corner)
- test_route_default_requested_domain_from_classification (M default)
- test_run_one_query_survives_malformed_scope_llm_dict (HIGH repro
  with full asyncio.run(run_one_query) under monkeypatched scope_gate
  + retrieval stubs)

## Acceptance bar — re-verify
1. ✅ Imported (substrates)
2. ✅ Invoked (sweep wiring after _classify_scope_with_llm)
3. ✅ Run-log evidence (`[M-INT-5] domain_router:` line, now with
   `requested_domain=...` field)
4. ✅ Rollback flag PG_USE_DOMAIN_ROUTER=0 disables (default 0)
5. ✅ UNCERTAIN-verdict fallback → REJECTED_UNCERTAIN
6. ✅ Failure does NOT raise (per LAW II — HIGH closed)

## Tests
- 11/11 M-INT-5 (7 v1 + 4 v2 regression)
- 67/67 across M-INT-0a..5

Branch: PL-honest-rebuild-phase-1
Commit: 44543fa

## Verdict
GREEN | PARTIAL | BLOCKED
