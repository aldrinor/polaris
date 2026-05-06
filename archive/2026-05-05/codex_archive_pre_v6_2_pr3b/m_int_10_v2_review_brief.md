# Codex round 2 — M-INT-10 v2

## Round-1 close
v1 had 1 MEDIUM + 1 LOW. v2 fixes:

### MEDIUM (FIXED): Drive-only contract not enforced
- v1: SharePoint URL accepted, mislabeled as connector='google_drive'
- v2:
  - Pydantic model `extra='forbid'` → unknown `connector` field → 422
  - `_validate_drive_folder_id` regex (20-80 chars [A-Za-z0-9_-])
    rejects URLs, paths, short strings at endpoint level → 400

### LOW (FIXED): empty workspace_id query
- v1: ?workspace_id= silently returned 200 with []
- v2:
  - Omitted entirely → 200 + [] (caller intent: "no work")
  - Explicitly empty / whitespace → 400 (caller bug)

## v2 regression tests
4 new (11 total):
- test_register_rejects_non_drive_connector (422 on extras)
- test_register_rejects_url_external_uri (400 on SharePoint URL)
- test_register_rejects_short_external_uri (400 on <20 chars)
- test_list_empty_workspace_id_returns_400 (empty/whitespace → 400)

## Acceptance bar
1. ✅ Imported (substrates)
2. ✅ Invoked (3 endpoints)
3. ✅ Run-log evidence
4. ✅ Rollback flag → 404 for both anon AND auth (deps order)
5. ✅ M-15b authn + role gate (member+ for write)
6. ✅ Org-scoping (cross-org → 404)
7. ✅ NARROW: Drive-only contract enforced at TWO layers
   (Pydantic extra='forbid' + folder-ID regex)

## Tests
- 11/11 M-INT-10
- 101/101 substrate

Branch: PL-honest-rebuild-phase-1
Commit: f49b34b

## Verdict
GREEN | PARTIAL | BLOCKED
