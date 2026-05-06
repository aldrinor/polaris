# Codex round 1 — M-INT-11 v1 (FINAL M-INT)

## Scope
FINAL integration milestone before LIVE/PROD phases. Wires
M-24 substrate (SupportTicketStore + TicketCategory +
TicketPriority + TicketStatus + ticket_to_dict) into
inspector_router as three production endpoints.

## Endpoints
- POST /api/inspector/support-tickets (open, 201)
- GET  /api/inspector/support-tickets[?status=...] (list)
- GET  /api/inspector/support-tickets/{ticket_id}

## Acceptance bar
1. ✅ Imported (substrates)
2. ✅ Invoked (3 endpoints)
3. ✅ Run-log evidence (201/200/400/403/404)
4. ✅ Rollback flag PG_USE_SUPPORT_TICKET_ENDPOINT=0 → 404
5. ✅ M-15b authn + role gate (member+ for write)
6. ✅ Org-scoping (cross-org → 404)
7. ✅ Closed enums for category + priority
8. ✅ Pydantic extra='forbid'

## v1 caveats
- Only open + read shipped. Assignment/resolve/close/message-append
  are admin-only flows deferred to Phase F UI.
- Default flag PG_USE_SUPPORT_TICKET_ENDPOINT=1 (substrate already
  shipped + tested).

## Tests
- 8/8 M-INT-11 tests pass
- 87/87 across substrate

Branch: PL-honest-rebuild-phase-1
Commit: a78bd2e

## Verdict
GREEN | PARTIAL | BLOCKED
