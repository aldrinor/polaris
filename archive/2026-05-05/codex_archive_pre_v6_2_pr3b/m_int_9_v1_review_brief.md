# Codex round 1 — M-INT-9 v1

## Scope
Wires M-26 substrate (ContractDraftStore + ContractKind +
ContractDraftStatus + draft_to_dict) into inspector_router as
three production endpoints with M-15b authn retrofit + org-scoped
isolation.

## Endpoints
- POST   /api/inspector/contract-drafts (create new draft, 201)
- GET    /api/inspector/contract-drafts (list for caller's org)
- GET    /api/inspector/contract-drafts/{draft_id} (read one)

## Acceptance bar
1. ✅ Imported (ContractDraft, ContractDraftStore, ContractDraftError,
   ContractDraftStateError, ContractDraftStatus, ContractKind,
   draft_to_dict)
2. ✅ Invoked (three endpoints registered)
3. ✅ Run-log evidence (201 on create, 200 on list/get,
   400 on bad kind, 404 on unknown draft, 401/403 unauthn)
4. ✅ Rollback flag PG_USE_CONTRACT_DRAFT_ENDPOINT=0 → 404
5. ✅ M-15b authn retrofit (require_authenticated_caller)
6. ✅ Org-scoping via substrate (cross-org GET returns 404)
7. ✅ Singleton store with _reset helper for tests

## v1 caveats
- Workspace defaults to ws_default_{org_id} for v1. Real workspace
  selection requires Phase F UI (workspace selector + per-workspace
  RBAC), since Caller doesn't carry workspace_id today.
- Default flag PG_USE_CONTRACT_DRAFT_ENDPOINT=1 (feature ships ON,
  same pattern as M-INT-8 — substrate already shipped + tested).

## Tests
- 8/8 M-INT-9 tests pass
- 182/182 across M-INT-9 + contract_draft_store + inspector_router
  substrate (no regression)

Branch: PL-honest-rebuild-phase-1
Commit: 55b99f2

## Verdict
GREEN | PARTIAL | BLOCKED
