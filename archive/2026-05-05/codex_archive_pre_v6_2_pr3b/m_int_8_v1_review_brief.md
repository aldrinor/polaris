# Codex round 1 — M-INT-8 v1

## Scope
Wires M-22 substrate (build_slide_deck + deck_to_dict +
render_deck_html) into inspector_router as two production
endpoints with M-15b authn retrofit.

## Endpoints
- GET /api/inspector/runs/{slug}/slide-deck → JSON deck dict
- GET /api/inspector/runs/{slug}/slide-deck.html → rendered HTML

## Acceptance bar
1. ✅ Imported (build_slide_deck, deck_to_dict, render_deck_html,
   SlideDeckError, SlideDeckEmptyReportError)
2. ✅ Invoked (two new endpoints in inspector_router)
3. ✅ Run-log evidence (200 returns deck, 404/422/500 on errors)
4. ✅ Rollback flag PG_USE_SLIDE_DECK_ENDPOINT=0 → 404
5. ✅ M-15b authz retrofit (require_authenticated_caller dep)
6. ✅ 404 for unknown slug
7. ✅ 422 for empty-report (SlideDeckEmptyReportError)
8. ✅ 500 for IR-load or build failure

## v1 caveat
- Default flag PG_USE_SLIDE_DECK_ENDPOINT=1 (feature ships ON
  — pattern departs from M-INT-4..7 which default 0). Rationale:
  M-22 substrate already shipped + tested; the endpoint is just
  a router wrapper, not a new computation path. Set to 0 for
  emergency rollback.

## Tests
- 7/7 M-INT-8 tests pass
- 87/87 across slide_deck + inspector_router substrate (no regression)

Branch: PL-honest-rebuild-phase-1
Commit: d9fa5b0

## Verdict
GREEN | PARTIAL | BLOCKED
