# Codex round 1 — M-INT-10 v1

## Scope
Wires M-25 substrate (PrivateCorpusSyncStore + SourceConnector +
SourceStatus + source_to_dict) into inspector_router as three
production endpoints with M-15b authn retrofit + role gate +
narrow Drive-only scope per FINAL_PLAN.

## Endpoints
- POST /api/inspector/private-corpus-sources (register, 201)
- GET  /api/inspector/private-corpus-sources?workspace_id=... (list)
- GET  /api/inspector/private-corpus-sources/{source_id}

## Acceptance bar
1. ✅ Imported (CorpusSource, PrivateCorpusSyncStore,
   PrivateCorpusSyncError, SourceConnector, SourceStateError,
   SourceStatus, source_to_dict)
2. ✅ Invoked (3 endpoints registered)
3. ✅ Run-log evidence (201/200/400/403/404)
4. ✅ Rollback flag PG_USE_DRIVE_CONNECTOR_ENDPOINT=0 → 404
5. ✅ M-15b authn retrofit + role gate (member+ for write)
6. ✅ Org-scoping (cross-org → 404)
7. ✅ NARROW: connector hardcoded GOOGLE_DRIVE — no `connector`
   field in request body, callers cannot register SharePoint/
   Confluence

## v1 caveats
- Approve/revoke endpoints NOT shipped in v1 (admin-only writes
  deferred to Phase F UI). v1 is read-mostly + register-only.
- Default flag PG_USE_DRIVE_CONNECTOR_ENDPOINT=1 (substrate
  already shipped + tested — same pattern as M-INT-8/9).

## Tests
- 8/8 M-INT-10 tests pass
- 101/101 across inspector_router + private_corpus_sync substrate

Branch: PL-honest-rebuild-phase-1
Commit: 1f574cc

## Verdict
GREEN | PARTIAL | BLOCKED
