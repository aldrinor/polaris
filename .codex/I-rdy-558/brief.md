# Codex BRIEF review — I-rdy-019-followup / GH #558: test_matrix.md 4 P2 refinements

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The diff review later verifies the
applied edits. The working tree is intentionally unmodified at this stage.

## 1. Issue

GH #558 (I-rdy-019-followup) — Codex diff review of #515 APPROVE'd
`docs/carney_handover/test_matrix.md` at iter 4 with 4 non-blocking P2
accuracy refinements (`accept_remaining`). This issue applies those 4 P2s.

**Doc-only** — markdown edits to one file, `docs/carney_handover/test_matrix.md`.
Zero code, zero behaviour change.

## 2. The 4 edits (each verified against the running system)

### P2-1 — §2 `/sentence_hover_test` subroute spelling (lines 80-83)

The subroutes are listed as bare `/coverage`, `/evaluator_edge`, … ; the
deployed URLs are `/sentence_hover_test/coverage`, etc. Normalize to full
paths like the `/charts_test` list directly above (lines 77-79 already use
`/charts_test/click_through` etc.).

**Verified:** `web/app/sentence_hover_test/` contains exactly the 10
subdirectories `coverage`, `evaluator_edge`, `evidence_tooltip`,
`evidence_tooltip_edges`, `follow_up_append`, `memory_cite`, `perf`,
`split_screen`, `stress`, `two_run_picker` → deployed routes are
`/sentence_hover_test/<sub>`.

### P2-2 — row 9 (Multi-tab safety) §3 J6 bullet (lines 175-176)

The J6 "cancel in one cancels for both" check is not tied to the row-12
cancellation expected-fail. Row 12 already documents that `/runs/<runId>`
Cancel is `disabled` and no cancel endpoint exists → the multi-tab
cancel-propagation half is also currently expected-fail. Reword the J6
bullet to state the cancel-propagation half depends on cancellation
(row 12) and is expected-fail until I-rdy-011 (#507) / #539. The
"independent updates" half still applies, so the §4 grid row-9 J6 `✓`
is unchanged — §3 text only.

### P2-3 — row 15 (Tenant isolation) §3 J9 bullet (line 249)

The bullet assigns "deletion removes file + chunks + embeddings" to J9, but
`src/polaris_v6/api/upload.py` has no DELETE endpoint — reword the deletion
half as a target / known gap (expected-fail), not a runnable check.

**Verified:** `upload.py` exposes `@router.post("")` (line 53) +
`@router.get("/{document_id}")` (line 108) only — no DELETE route.

### P2-4 — rows 19 (LLM quality) + 21 (Anti-sycophancy) — J7 grid + §3

The §3 text maps "the completed run's report" check to J6 and lists J7 in
the N/A line, but J7 IS the completed-run view of the same `/runs/<runId>`
route — the finished report's quality is verified at J7. Fix:
- §3 rows 19 + 21: change the `J6 —` completed-report bullet to `J6/J7 —`
  (matching the existing `J6/J7` pairing style at row 18 line 278), and
  remove `J7` from each row's `**N/A:**` line.
- §4 grid: row 19 and row 21 — change the J7 column from `—` to `✓`.

The grid and §3 text stay mutually consistent (no silent grid/text mismatch).

## 3. Files I have ALSO checked and they're clean

- `docs/carney_handover/test_matrix.md` is the only file edited — a
  standalone handover doc; nothing imports or generates it.
- `web/app/charts_test/` confirms the §2 `/charts_test` list (lines 77-79)
  is already full-path — P2-1 makes `/sentence_hover_test` consistent with it.
- Row 12 (lines 203-214) already states the cancellation gap that P2-2
  cross-references — the reword points at an existing, accurate row.
- §4 grid rows 19/21 currently show J7 `—`; no other row/column is touched.

## 4. Test / smoke

Markdown — no executable smoke. Verification = visual diff: the 4 edits are
exactly the P2 set; the §4 grid stays a valid 11-column table; §3 N/A lines
for rows 19/21 no longer list J7.

## 5. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
