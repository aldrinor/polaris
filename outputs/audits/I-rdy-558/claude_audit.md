# Claude architect audit — I-rdy-019-followup (#558)

**Issue:** GH #558 — apply 4 Codex iter-4 P2 accuracy refinements to
`docs/carney_handover/test_matrix.md`.
**Branch:** `bot/I-rdy-019-followup-test-matrix`
**Commit 1 (doc):** `33572936`
**Brief:** `.codex/I-rdy-019-followup/brief.md` — Codex APPROVE iter 1 (0 P0/P1/P2).

## 1. What shipped

Doc-only — 4 markdown edits to `docs/carney_handover/test_matrix.md`. Zero
code, zero behaviour change.

| P2 | Edit | Verified against |
|---|---|---|
| P2-1 | §2 `/sentence_hover_test` subroutes → full deployed paths (`/sentence_hover_test/coverage`, …) | `web/app/sentence_hover_test/` — the 10 subdirs `coverage / evaluator_edge / evidence_tooltip / evidence_tooltip_edges / follow_up_append / memory_cite / perf / split_screen / stress / two_run_picker` exist. |
| P2-2 | row 9 §3 J6 bullet — the "cancel in one cancels for both" half flagged expected-fail, cross-referencing the row-12 cancellation gap | row 12 (lines 203-214) already documents `/runs/<runId>` Cancel `disabled` + no cancel endpoint. |
| P2-3 | row 15 §3 J9 bullet — the upload-deletion check reworded as a known gap (expected-fail) | `src/polaris_v6/api/upload.py` — `@router.post("")` + `@router.get("/{document_id}")` only; no DELETE route. |
| P2-4 | rows 19 + 21 — §3 `J6 —` → `J6/J7 —`, J7 removed from each `**N/A:**` line, §4 grid J7 column `—` → `✓` | J7 is the completed-run view of `/runs/<runId>` where the finished report's quality is verified; the `J6/J7` pairing matches the existing style at row 18. |

## 2. Per-finding verification

- **VERIFIED — P2-1:** the §2 `/sentence_hover_test` list now uses full paths
  consistent with the `/charts_test` list above it; the 11-route count
  ((1 root + 10 subroutes)) is unchanged and matches `web/app/`.
- **VERIFIED — P2-2:** the row-9 J6 bullet's "independent updates" half is
  preserved (the §4 grid row-9 J6 `✓` is unchanged — multi-tab safety does
  apply); only the cancel-propagation half is now marked expected-fail with
  an explicit row-12 / I-rdy-011 (#507) / #539 cross-reference.
- **VERIFIED — P2-3:** the row-15 J9 bullet's org-scoping half is preserved;
  only the deletion half is reworded as a known gap.
- **VERIFIED — P2-4 grid/text consistency:** §4 grid rows 19 and 21 now show
  J7 `✓` (verified: `| 19 | … | — | — | — | — | ✓ | ✓ | ✓ | — | — | — | — |`
  — 11 J-columns, J5/J6/J7 ticked); the §3 N/A lines for both rows no longer
  list J7. No silent grid/text mismatch.

## 3. Test / smoke

Markdown — no executable smoke. Verified by diff inspection: `git diff
--stat` shows `test_matrix.md` 27+/11-; the §4 grid rows stay valid
11-column tables; the 4 edits are exactly the P2 set, nothing else in the
matrix touched.

## 4. Scope + residuals

- Only `docs/carney_handover/test_matrix.md` is committed. (Pre-existing
  uncommitted `outputs/honest_sweep_r3/**` working-tree modifications,
  present since session start, are unrelated sweep artifacts — explicitly
  NOT staged.)
- The matrix is a standalone handover doc; nothing imports or generates it.

## 5. Verdict

Implementation complete, faithful to the iter-1 APPROVE'd brief; all 4 P2s
applied, grid and §3 text mutually consistent. Ready for Codex diff review.
