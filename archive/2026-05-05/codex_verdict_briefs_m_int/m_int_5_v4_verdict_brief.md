# M-INT-5 v4 — Codex round-4 GREEN

## Codex verdict (verbatim)
> No findings.
>
> The strengthened stub now matches the production
> `LiveRetrievalResult` shape exactly. Both regressions use
> that full shape and both now assert `status != "error"`.
> I checked the real `run_one_query` path... the stub supplies
> all of them. I did not find any still-missing top-level field.
>
> I executed those two regression bodies directly against
> manually created scratch directories, and both passed and
> returned `status='fail_no_sources'`, which is the expected
> non-`error` outcome matching the round-3 probe.
>
> VERDICT: GREEN

## Round summary
- Round 1: 1 HIGH (KeyError abort) + 1 MEDIUM (lost domain tag)
- Round 2: 1 HIGH (helper raise still escaped) + 1 MEDIUM (test stub async vs sync)
- Round 3: 1 MEDIUM (test stub shape didn't match LiveRetrievalResult)
- Round 4: GREEN (no findings)

## Final state
- 12/12 M-INT-5 tests pass with strengthened assertions
- Codex independently verified both regressions pass with `status='fail_no_sources'`
- 68/68 across M-INT-0a..5

## Acceptance bar — ALL met
1. ✅ Imported (DomainTemplate, DomainTemplateRegistry, DomainAdapter,
   RoutingResult, RoutingOutcome, route_to_domain)
2. ✅ Invoked (`_route_query_to_domain` from sweep)
3. ✅ Run-log evidence (`[M-INT-5] domain_router:` line)
4. ✅ Rollback flag PG_USE_DOMAIN_ROUTER=0 disables (default 0)
5. ✅ UNCERTAIN-verdict fallback → REJECTED_UNCERTAIN
6. ✅ LAW II (failure does NOT raise) — defense-in-depth via:
   - helper internal try/except (round-1)
   - dict-shape defensive .get() (round-1 HIGH fix)
   - sweep outer try/except wrap (round-2 HIGH fix)
   - shape-compatible test stub (round-3 MEDIUM fix)
7. ✅ Unknown-domain → UNKNOWN_DOMAIN with requested_domain preserved

Branch: PL-honest-rebuild-phase-1
Commit: 438b699

## Verdict
**GREEN — M-INT-5 LOCKED. Proceeding to M-INT-6.**
