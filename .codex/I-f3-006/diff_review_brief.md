# Codex Diff Review — I-f3-006 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-006 — Frontend per-file parse status (chunks progression)
**Brief:** APPROVED iter 1 (0/0/3P2)
**Canonical-diff-sha256:** `e655d01e0eda44b2f9f392e32b0d4ea7f56b8e58accc767e237f067951fb93fb`
**LOC:** 144 net (under 200-cap by 56)
**Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/lib/api.ts                                          EDIT  +7
web/app/upload/components/upload_drop_zone.tsx          EDIT  +62/-4
web/tests/e2e/upload_parse_status.spec.ts               NEW   +79
```

## What changed

1. `getUpload(document_id)` API client.
2. `UploadDropZone` extension: `parse_status` + `chunk_preview_count` per file. On POST resolution if `parse_status === "queued"`, fire `pollParseStatus()` (10 × 1s cap).
3. UI: stacked rendering — `upload-doc-id` AND `upload-parse-{id}` side by side. Status text: "parsing…", "completed · N chunks", "parse failed".
4. Playwright test: mocks POST returning queued, then GET endpoint multi-call mock simulating progression. Asserts `parsing` → `completed · 3 chunks` transition; verifies polling stops post-completed (call counter ≤3).

## Iter-1 brief P2 advisories addressed

- P2 #1 (chunk_preview is preview, not total): UI text disambiguates ("N chunks so far" vs "N chunks").
- P2 #2 (PDFs stay in parsing… after cap): documented.
- P2 #3 (don't replace upload-doc-id): both rendered side-by-side in flex column.

## Risks for Codex Red-Team

1. **Polling cap (10 × 1s).** Prevents runaway.
2. **Polling stops on non-queued.** Single-shot guard via `if (... !== "queued") return;`.
3. **`upload-doc-id` regression-protected.** Renders alongside parse status (Codex iter-1 P2 #3 fix).
4. **No new package.json dep.**
5. **Test isolation.** Multi-call mock with internal counter; clean per-test state.
6. **Backward-compat with I-f3-005 tests.** New fields optional; uploading→completed transition unchanged.

## Out of scope

- Backend async PDF parser → separate Issue.
- Per-chunk preview text → I-f3-007.

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
