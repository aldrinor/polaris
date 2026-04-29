# Codex round 2 — M-INT-9 v2

## Round-1 close
v1 had 2 MEDIUMs + 1 LOW. All fixed in v2 (commit 87ebd4b):

### MEDIUM 1: viewer could create drafts (FIXED)
- v1 used require_authenticated_caller — accepted any role
- v2 explicit `caller.role in {member, admin, owner}` check
  → viewer attempts return 403 with "viewer" in the detail

### MEDIUM 2: rollback flag didn't work for anonymous (FIXED)
- v1 checked PG_USE_CONTRACT_DRAFT_ENDPOINT inside handler
  body, after auth dependency resolved
- v1 anonymous + flag=0 → 401 (auth challenge), should be 404
- v2 hoists flag check to FastAPI dependency
  `_require_contract_draft_endpoint_enabled` listed in route
  `dependencies=[...]` — runs BEFORE auth dep
- Now anonymous + flag=0 → 404

### LOW: docstring enum values wrong (FIXED)
- v1 docstring: 'drafting / pending_approval'
- Actual enum values: 'draft / awaiting_approval'
- v2 docstring corrected; both 'draft' and 'awaiting_approval'
  query strings now work; the wrong v1-doc 'drafting' value
  returns 400 with the correct list in the error message

## v2 regression tests (4 new, 12 total)
- test_viewer_role_cannot_create_draft (M1 repro)
- test_member_role_can_create_draft (M1 inverse)
- test_disabled_flag_returns_404_for_anonymous (M2 repro)
- test_status_filter_uses_correct_enum_values (LOW)

## Acceptance bar (re-verify all)
1. ✅ Imported (substrates)
2. ✅ Invoked (3 endpoints)
3. ✅ Run-log evidence (201/200/400/403/404)
4. ✅ Rollback flag PG_USE_CONTRACT_DRAFT_ENDPOINT=0 → 404
   (now works for both anonymous AND authenticated)
5. ✅ M-15b authn retrofit
6. ✅ Org-scoping (cross-org GET → 404)
7. ✅ Role gate on writes (viewer → 403, member+ → 201)

## Tests
- 12/12 M-INT-9
- 174/174 across substrate (no regression)

Branch: PL-honest-rebuild-phase-1
Commit: 87ebd4b

## Verdict
GREEN | PARTIAL | BLOCKED
