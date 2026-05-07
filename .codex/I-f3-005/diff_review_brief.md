# Codex Diff Review — I-f3-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-005 — frontend drag-drop upload zone
**Brief:** APPROVED iter 2 (iter1 REQ_CH 50MB backend mismatch → iter2 APPROVE 0/0/1P2 stale-text-only)
**Canonical-diff-sha256:** `87e11d29210961875ee346838aa6d588f4f040f5031d2041dd8a2e3037efd53f`
**LOC:** 258 net — **OVER CHARTER §1 200-cap by 58. Explicit exemption ask below.**

## CHARTER §1 LOC-cap exemption ask

Same structural case as I-f2-008 (Codex granted exemption). Binding multi-scenario test coverage requires this LOC after Prettier reflow. Codex iter-1 P2 #2 explicitly said "trim implementation/tests instead of removing that scenario" — all 3 scenarios preserved.

**Ask:** APPROVE despite 258 LOC. If denied → split into I-f3-005a (backend + page + single-file test) + I-f3-005b (multi + oversize). Total LOC unchanged.

## Files

```
src/polaris_v6/api/upload.py                          EDIT  +1/-1 (25→50MB)
web/app/upload/page.tsx                               NEW   +29
web/app/upload/components/upload_drop_zone.tsx        NEW   +135
web/tests/e2e/upload_dropzone.spec.ts                 NEW   +93
```

## What changed

1. `upload.py:34` `MAX_BYTES` 25→50MB.
2. `/upload` route page.tsx with metadata + UploadDropZone client child.
3. `UploadDropZone`: native HTML5 dragover/drop on zone div; 3-tier validation (extension, size, upload); per-file `uploading|completed|error` status with `data-status` attr + `data-testid="upload-doc-id"` on success.
4. 3 Playwright tests using `page.route("**/upload", ...)` POST-only mock with backend-origin glob (iter-1 P2 #1 fix). Synthetic DragEvent + DataTransfer + 51MB Uint8Array.

## Iter-2 brief P2 advisory addressed

P2 (stale risk-register text): N/A — final brief has updated LOC + scope notes.

## Risks for Codex Red-Team

1. **LOC-cap exemption.** See ask above.
2. **Backend gate matches frontend gate** — defense in depth.
3. **POST-only mock** — non-POST requests (page nav) fall through.
4. **Synthetic 51MB Uint8Array.** ~50MB heap during the oversize test; acceptable.
5. **No new package.json dep.**
6. **Accessibility** via role + tabIndex + keyboard handler.
7. **`uploadDocument` from `@/lib/api`** — existing; no API change.
8. **Backend `MAX_BYTES`** also affects every other route consuming this constant (none others currently per grep).

## Out of scope

- Per-file parse status (queued → parsing → completed) → I-f3-006.
- Doc preview with chunk highlights → I-f3-007.

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
