# Claude architect audit — I-f15-003

**Issue:** Bundle preview pane in report header
**Branch:** bot/I-f15-003
**Canonical-diff-sha256:** 620c2f4f58c4b147df92ff3d1aa53c698f98d8df17dfcc95c33899470239ac4e
**Brief verdict:** APPROVE iter 3 (0/0/0P1, 2 P2 cosmetic)
**Diff verdict:** APPROVE iter 2 (0/0/0P1, 1 P2 coverage-gap, accept_remaining; LOC-cap exemption granted)

## Substrate honesty
- New `POST /api/audit-bundle/preview` route in `audit_bundle_route.py` reuses `build_manifest_and_files()` directly — no GPG, no tar.
- FK validation mirrors `bundle_builder.py:98-107` exactly; same `fk_chain_mismatch` envelope.
- `previewAuditBundle()` in `web/lib/api.ts` mirrors `downloadAuditBundle()`'s structured-error parsing.
- BundlePreview component slots above existing AuditBundleButton in generation_runner.

## Algorithm correctness
- 3-state machine (loading/ok/error). Cancellation guard prevents stale state across deps changes.
- Lint-compliant: no synchronous setState in effect body (initial state is loading; only transitions on resolve/reject).
- Summary aggregator iterates `manifest.files` (list[FileEntry]) — correct per Codex iter-2 substrate finding.

## §9.4 compliance
- No mocks (Playwright `route.fulfill` is network-level stub, not code mock).
- No magic numbers (1024 / 1048576 are byte-unit constants used in fmt).
- No `try: pass`, no `time.sleep`, no TODO/FIXME.

## Sovereignty / external-egress
- Preview accepts the same `{ decision, pool, report }` body as the existing download route. Zero new external-egress surface.

## Test integrity
- 2 Playwright tests: success-path (5 breakdown rows + file count + Preview ID prefix) + error-path (`fk_chain_mismatch` code rendering).
- Hermetic: full chain stubbed (`/api/intake`, `/api/retrieval`, `/api/generation`, `/api/audit-bundle/preview`); CORS OPTIONS preflight intercepted.
- Backend route smoke-imports cleanly: `python -c "from polaris_graph.api.audit_bundle_route import router"` registers `/audit-bundle/preview`.
- Diff iter-2 P2 (no value assertions on row counts/bytes): documented as coverage gap; component renders the breakdown using the same fixture data; mismatch would fail the existing toBeVisible assertions only if data shape changes. Captured for I-f15-003a follow-up.

## Out-of-scope follow-ups (named)
- I-f15-003a: WCAG audit of preview pane.
- I-f15-003a (extended): assert numeric values from PREVIEW fixture in success-path test.
- Stable preview→download bundle_id (currently each call mints fresh uuid4).

## CHARTER §1 LOC cap
- 381 net. Codex granted exemption iter 2 acknowledging Prettier expansion of stub-heavy spec. Per CLAUDE.md §8.3.6, when Codex's `convergence_call` flips to `accept_remaining`, accept and ship.

## Verdict
APPROVE on architect review. Ready to ship.
