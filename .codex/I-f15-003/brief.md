# Codex Brief Review — I-f15-003 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-003 — Bundle preview pane in report header
**Phase:** 1 / **Feature:** F15
**LOC budget:** 150 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-2 verdict consumed

- Iter 2: REQUEST_CHANGES — 0 P0 / 2 P1 / 2 P2.
- P1 #1 (FK validation in build_audit_bundle but NOT in build_manifest_and_files): RESOLVED iter 3 — preview route mirrors the FK checks from `bundle_builder.py:99,104` BEFORE calling `build_manifest_and_files`. Returns `code: "fk_chain_mismatch"` if mismatched. Manifest route validation is now identical to download route validation.
- P1 #2 (Playwright route paths wrong): RESOLVED iter 3 — confirmed via grep. Frontend POSTs to `/api/intake`, `/api/retrieval`, `/api/generation`, `/api/audit-bundle/preview`. Brief fixed.
- P2 #1 (manifest_builder returns dict[str, bytes]): RESOLVED iter 3 — preview summary aggregates from `manifest.files` (list[FileEntry]) NOT from the bytes dict. Verified at `bundle_schema.py:105` (manifest.files exists).
- P2 #2 (bundle_id is preview-only): RESOLVED iter 3 — preview response wraps `manifest.bundle_id` as `preview_bundle_id` (renamed in response to make non-canonical-ness explicit). Component labels it "Preview ID" (not "Bundle ID"). Note in response schema: "preview_bundle_id is non-canonical; the eventual download will mint a fresh uuid4."

## Mission

Component renders a manifest preview pane (file count, total bytes, content_type breakdown, generator_model, polaris_version) BEFORE the user clicks "Download audit bundle." Lets the operator inspect bundle composition without downloading.

## Substrate (HONEST at HEAD — verified iter 3)

- `src/polaris_graph/audit_bundle/manifest_builder.py:82` `build_manifest_and_files(decision, pool, report) -> tuple[BundleManifest, dict[str, bytes]]`. Raises `ValueError` only if `report.pipeline_verdict != "success"`. Does NOT do FK validation.
- `src/polaris_graph/audit_bundle/bundle_builder.py:98-107` does FK validation BEFORE calling `build_manifest_and_files`. Preview route MUST mirror this.
- `src/polaris_graph/audit_bundle/bundle_schema.py:105` `BundleManifest.files: list[FileEntry]` — populated by `build_manifest_and_files`. Summary breakdown uses `manifest.files`.
- `web/lib/api.ts:619` `pipeline_verdict: PipelineVerdict`.
- `web/lib/api.ts:430,527,662` confirms POST routes: `/api/intake`, `/api/retrieval`, `/api/generation`. The `/run` suffix was wrong.
- `web/lib/api.ts:743` `downloadAuditBundle()` and `AuditBundleError` are reusable.
- `web/app/generation/components/generation_runner.tsx:227-288` slot.

## Approach

**Part 1 — Backend preview endpoint** (`src/polaris_graph/api/audit_bundle_route.py` EDIT):
- Add `POST /api/audit-bundle/preview` route.
- Body: `{ decision, pool, report }`.
- FK validation BEFORE `build_manifest_and_files`:
  ```python
  if report.pool_id != pool.pool_id:
      raise HTTPException(400, {"error": True, "code": "fk_chain_mismatch", "message": ...})
  if report.decision_id != decision.decision_id:
      raise HTTPException(400, {"error": True, "code": "fk_chain_mismatch", "message": ...})
  ```
- Calls `build_manifest_and_files(decision, pool, report)` directly. Catches `ValueError` → 400 `{ error: True, code: "verdict_not_success", message: ... }`.
- Aggregates summary from `manifest.files` (list[FileEntry]):
  ```python
  breakdown = {ct: {"count": 0, "bytes": 0} for ct in CONTENT_TYPES}
  for f in manifest.files:
      breakdown[f.content_type]["count"] += 1
      breakdown[f.content_type]["bytes"] += f.size_bytes
  ```
- Returns: `{ "preview_bundle_id": manifest.bundle_id, "generator_model": ..., "polaris_version": ..., "file_count": len(manifest.files), "total_bytes": manifest.total_bytes(), "content_type_breakdown": breakdown }`. NOTE: `preview_bundle_id` is preview-only; download will mint a fresh uuid4.
- LOC: ~50.

**Part 2 — Frontend types + client** (`web/lib/api.ts` EDIT):
- Add `BundlePreviewResponse`, `BundlePreviewByContentType` interfaces.
- Add `previewAuditBundle(decision, pool, report) -> Promise<BundlePreviewResponse>` mirroring `downloadAuditBundle()`'s error path: parse 4xx/5xx body for `{ error: true, code, message }` and throw `AuditBundleError`.
- LOC: ~25.

**Part 3 — Frontend preview pane** (`web/app/generation/components/BundlePreview.tsx` NEW):
- Client component (`"use client"`).
- `useEffect` POSTs to `previewAuditBundle()` when `report.pipeline_verdict === "success"`. Memoized by `report.report_id`.
- Renders `<section data-testid="bundle-preview">` panel with: Preview ID (8-char prefix + "…"), Generator model, POLARIS version, file count, humanized total bytes, and 5-row breakdown table (`<tr data-testid={`bundle-preview-row-${ct}`}>`).
- Loading: `data-testid="bundle-preview-loading"`. Error: `data-testid="bundle-preview-error"` rendering structured `code`.
- LOC: ~70.

**Part 4 — Slot into `generation_runner.tsx`** (EDIT):
- Render `<BundlePreview ... />` above AuditBundleButton when `report.pipeline_verdict === "success"`.
- LOC: ~5.

**Part 5 — Playwright `web/tests/e2e/bundle_preview.spec.ts`** (NEW):
- 2 tests; full chain stubbed via `page.route()`:
  - `**/api/intake` → fulfill with success ScopeDecision (`status: "in_scope"`)
  - `**/api/retrieval` → fulfill with success EvidencePool
  - `**/api/generation` → fulfill with success VerifiedReport (`pipeline_verdict: "success"`)
  - `**/api/audit-bundle/preview` → fulfill with stub manifest+summary (test 1) OR 500 error (test 2)
  - All routes POST-only: `if (route.request().method() !== "POST") return route.continue();`
- Test 1: assert `bundle-preview` panel renders Preview ID, file count, breakdown rows for `scope_decision`, `evidence_pool`, `verified_report`.
- Test 2: assert `bundle-preview-error` testid visible + error code rendered.
- LOC: ~35.

## Acceptance criteria (binding)

1. **`src/polaris_graph/api/audit_bundle_route.py`** EDIT: Add `POST /api/audit-bundle/preview` with FK validation + verdict validation + summary aggregation.
2. **`web/lib/api.ts`** EDIT: Add types + `previewAuditBundle()` mirroring `downloadAuditBundle()`'s error parsing.
3. **`web/app/generation/components/BundlePreview.tsx`** NEW: Client component rendering preview pane.
4. **`web/app/generation/components/generation_runner.tsx`** EDIT: Slot BundlePreview above AuditBundleButton; gates on `report.pipeline_verdict === "success"`.
5. **`web/tests/e2e/bundle_preview.spec.ts`** NEW: 2 Playwright tests stubbing `/api/intake`, `/api/retrieval`, `/api/generation`, `/api/audit-bundle/preview`.

## Planned diff shape

```
src/polaris_graph/api/audit_bundle_route.py        EDIT +50
web/lib/api.ts                                     EDIT +25
web/app/generation/components/BundlePreview.tsx    NEW +70
web/app/generation/components/generation_runner.tsx EDIT +5
web/tests/e2e/bundle_preview.spec.ts               NEW +35
```

LOC: +185 net. Under CHARTER §1 200-cap by 15.

## Out of scope

- Showing manifest signature verification status — preview is unsigned; signing is a separate I-f15-005-adjacent concern.
- Stable bundle_id across preview→download — preview bundle_id is non-canonical; explicitly labeled "Preview ID" in UI to avoid implying it equals the downloaded bundle's bundle_id.
- WCAG full audit of the preview pane → I-f15-003a accessibility follow-up.

## Risks for Codex Red-Team

1. **FK validation mirrors download route exactly.** Brief author commits to copying the two FK assertions from `bundle_builder.py:98-107` into the preview route handler.

2. **`pipeline_verdict` field name confirmed at `web/lib/api.ts:619`.**

3. **Frontend route paths confirmed.** Stubs target `/api/intake`, `/api/retrieval`, `/api/generation`, `/api/audit-bundle/preview` — NOT `/run` suffix.

4. **`build_manifest_and_files` returns `dict[str, bytes]` for content but `manifest.files` is `list[FileEntry]`.** Summary aggregates from `manifest.files`, NOT from the bytes dict.

5. **`preview_bundle_id` is non-canonical.** Preview mints a fresh uuid4 each call (`bundle_schema.py:92`). Response field renamed to `preview_bundle_id` and UI labels "Preview ID" to avoid implying stability.

6. **`previewAuditBundle()` error parsing** mirrors `downloadAuditBundle()` — parses `{ error: true, code, message }` envelope and throws `AuditBundleError`.

7. **`useEffect` re-fetch loop.** Memoized by `report.report_id`; refetches only when report identity changes.

8. **Sovereignty surface.** Preview accepts the same `{ decision, pool, report }` body as the download route. No new external-egress surface.

9. **CHARTER §1 LOC cap.** 185 net. Under 200.

10. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
