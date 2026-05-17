# Codex DIFF review — I-rdy-019-followup / GH #558: test_matrix.md 4 P2 refinements

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #558 — `git diff origin/polaris...HEAD` excluding
`.codex/I-rdy-019-followup/` and `outputs/audits/I-rdy-019-followup/` (the
canonical diff in `.codex/I-rdy-019-followup/codex_diff.patch`, sha256
trailer). It implements the Codex-APPROVE'd brief
`.codex/I-rdy-019-followup/brief.md` (brief review APPROVE iter 1).

**Doc-only** — markdown edits to one file,
`docs/carney_handover/test_matrix.md`. Zero code, zero behaviour change.

## 2. The diff (1 file)

`docs/carney_handover/test_matrix.md` — the 4 Codex iter-4 P2 refinements:

- **P2-1** §2: `/sentence_hover_test` subroutes spelled as full deployed
  paths (`/sentence_hover_test/coverage`, …), consistent with the
  `/charts_test` list above.
- **P2-2** row 9 §3 J6 bullet: the "cancel in one cancels for both" half is
  tied to the row-12 cancellation gap and marked expected-fail until
  I-rdy-011 (#507) / #539; the "independent updates" half (and the §4 grid
  row-9 J6 `✓`) is unchanged.
- **P2-3** row 15 §3 J9 bullet: the upload-deletion check reworded as a
  known gap (`upload.py` has POST+GET only, no DELETE endpoint).
- **P2-4** rows 19 + 21: §3 `J6 —` → `J6/J7 —`; J7 removed from each
  `**N/A:**` line; §4 grid rows 19 and 21 J7 column `—` → `✓`.

## 3. Verify against the brief

1. The 4 edits are exactly the issue's P2 set — no other matrix content
   changed, no scope creep.
2. §4 grid rows 19 and 21 are still valid 11-J-column tables and now tick
   J5/J6/J7; the §3 N/A lines for those rows no longer list J7 (grid/text
   consistent).
3. P2-2/P2-3 preserve the still-valid half of each bullet (independent
   updates; org-scoping) and only reframe the unimplemented half.
4. P2-1 keeps the 11-route count and matches the deployed
   `web/app/sentence_hover_test/` subdirectory set.

## 4. Files I have ALSO checked and they're clean

- Only `docs/carney_handover/test_matrix.md` is in the canonical diff.
  Pre-existing uncommitted `outputs/honest_sweep_r3/**` working-tree
  changes (present since session start) are unrelated sweep artifacts and
  were deliberately NOT staged.
- `web/app/sentence_hover_test/` + `web/app/charts_test/` confirm the route
  spellings; `src/polaris_v6/api/upload.py` confirms no DELETE endpoint;
  row 12 confirms the cancellation gap P2-2 cross-references.

## 5. Test state

Markdown — no executable smoke. Verification is diff inspection (the 4 edits
= the P2 set; grid stays a valid table).

## 6. Required output schema (§8.3.9)

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
