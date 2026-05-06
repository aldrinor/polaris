# M-INT-9 v2 — Codex round-2 GREEN

## Codex verdict (verbatim)
> No new defects found in 87ebd4b.
>
> MEDIUM 1 is fixed: POST now enforces caller.role in
> {member, admin, owner}. Manual probe with viewer →
> 403 with "viewer" in detail. member and admin both 201.
>
> MEDIUM 2 is fixed: all three routes carry the feature-flag
> dependency. Route introspection showed
> ['_require_contract_draft_endpoint_enabled',
>  'require_authenticated_caller'], and a minimal probe
> executed only the first dependency. Flag 0 + anonymous → 404;
> flag 0 + authenticated → 404.
>
> LOW is fixed. List endpoint docstring matches real enum;
> runtime behavior correct.
>
> No extra /contract-drafts write endpoints exist.
> Cross-org GET returns 404.
>
> Compensated for sandbox tmpdir issues by directly
> invoking all 12 test functions; all 12/12 passed.
>
> VERDICT: GREEN

## Round summary
- R1: 2 MEDIUM (viewer-can-write, anonymous-401-on-rollback)
       + 1 LOW (wrong enum docstring)
- R2: GREEN (all 3 closed)

## Acceptance bar — ALL met
1. ✅ Imported (substrates)
2. ✅ Invoked (3 endpoints with correct dep ordering)
3. ✅ Run-log evidence
4. ✅ Rollback flag (404 for both anonymous AND authenticated)
5. ✅ M-15b authn retrofit
6. ✅ Org-scoping (cross-org → 404)
7. ✅ Role gate on writes (viewer → 403, member+ → 201)

## Tests
- 12/12 M-INT-9 (Codex independently verified by direct invocation)
- 174/174 substrate green

Branch: PL-honest-rebuild-phase-1
Commit: 87ebd4b

## Verdict
**GREEN — M-INT-9 LOCKED. Proceeding to M-INT-10.**
