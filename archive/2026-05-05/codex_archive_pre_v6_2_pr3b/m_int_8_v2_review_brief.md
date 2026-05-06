# Codex round 2 — M-INT-8 v2

## Round-1 close
v1 had 1 MEDIUM + 1 LOW. v2:

### MEDIUM (cross-org authz): DOCUMENTED, deferred to system-wide milestone
- Codex confirmed: "this is the wider system pattern, not
  introduced by this router wrapper". Same pattern on
  get_run, get_audit_bundle, get_report_markdown, etc. —
  none enforce run-level org authz. Several don't even require
  authentication.
- Fixing requires:
  1. Adding org_id to RunSummary (registry schema migration)
  2. Updating 5+ run-* endpoints
  3. Backfilling org_id on existing artifacts
- Tracked for Phase F / M-PROD-1 (SOC2 dry-run scope).
  M-INT-8 ships AT PARITY with existing pattern.
- Documented inline at the M-INT-8 endpoint header.

### LOW (test coverage): FIXED
- v1 tests allowed 500 on the happy path (canonical IR may
  not exist in test env), didn't explicitly force 422/500.
- v2 adds 4 explicit error-path tests:
  - test_slide_deck_empty_report_returns_422
  - test_slide_deck_html_empty_report_returns_422
  - test_slide_deck_ir_load_failure_returns_500
  - test_slide_deck_build_failure_returns_500
- Each uses a synthetic AuditIR built via _build_minimal_audit_ir
  helper (sentences_verified=0) or monkeypatches load_audit_ir/
  build_slide_deck to raise.

## Acceptance bar
1. ✅ Imported (substrates)
2. ✅ Invoked (endpoints registered)
3. ✅ Run-log evidence (200/404/422/500 explicitly tested)
4. ✅ Rollback flag PG_USE_SLIDE_DECK_ENDPOINT=0 → 404
5. ✅ M-15b authn retrofit
6. ✅ 422 for empty report (explicit test)
7. ✅ 500 for IR load failure (explicit test)
8. ✅ 500 for build failure (explicit test)

## Tests
- 11/11 M-INT-8 (7 v1 + 4 v2 error-path)
- 87/87 across slide_deck + inspector_router substrate

Branch: PL-honest-rebuild-phase-1
Commit: bd40be0

## Verdict
GREEN | PARTIAL | BLOCKED
