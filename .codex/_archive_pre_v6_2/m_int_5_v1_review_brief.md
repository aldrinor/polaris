# Codex round 1 — M-INT-5 v1

## Scope
Wires M-D6 phase 1 substrate (DomainTemplate + DomainTemplateRegistry +
DomainAdapter Protocol + route_to_domain) into the sweep telemetry flow.

After M-INT-4 LLM scope verdict, sweep:
1. Reconstructs ScopeClassification from the dict
2. Calls _route_query_to_domain(classification)
3. Logs `[M-INT-5] domain_router: outcome=... domain=... adapters=...`

## Acceptance bar
1. ✅ Imported (DomainTemplate, DomainTemplateRegistry, DomainAdapter,
   RoutingResult, RoutingOutcome, route_to_domain)
2. ✅ Invoked (`_route_query_to_domain` from sweep after _classify_scope_with_llm)
3. ✅ Run-log evidence (`[M-INT-5] domain_router:` line)
4. ✅ Rollback flag PG_USE_DOMAIN_ROUTER=0 disables (default 0)
5. ✅ UNCERTAIN-verdict fallback → REJECTED_UNCERTAIN, not raise
6. ✅ Failure does NOT raise (LAW II)
7. ✅ Unknown-domain → UNKNOWN_DOMAIN outcome (in_scope verdict
   with domain not in registry)

## v1 caveat
- _StubCrossrefAdapter / _StubPubmedAdapter are STUB implementations
  (just adapter_id). Real Crossref/PubMed HTTP fetcher wiring is Phase F.
  Substrate import + invocation + RoutingResult shape demonstrated.
- Default registry has clinical + policy. Config-driven loading is Phase F.

## Tests
- 7/7 M-INT-5 tests pass
- 63/63 across M-INT-0a..5

Branch: PL-honest-rebuild-phase-1
Commit: 4d4adfd

## Verdict
GREEN | PARTIAL | BLOCKED
