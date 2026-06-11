# Codex DIFF review — I-perm-005 (#1199) SLICE 2 annotator — ITER 2 (confirm P0-1 + P0-2 fix)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Reserve P0/P1 for real execution risks. If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Your iter-1 verdict was REQUEST_CHANGES with TWO P0s. Both fixed. Verify against the code.

### P0-1 (RESOLVED): partial label — a clean hit suppressed the raise for a straddling unlabeled occurrence
Fix: the `labeled_any` check is replaced by `_all_occurrences_labeled(working, stem_norm, marker)`. It BLANKS every LABELED sentence (matches stem after a LOCAL marker strip AND carries the marker), then returns False if the stem STILL appears in the marker-stripped line-join projection of the remainder — so a boundary-straddling occurrence (not pinned to any single sentence) is detected EVEN WHEN another occurrence WAS labeled. A pinned-but-unlabeled sentence returns False immediately. New regression test `test_partial_label_with_straddling_occurrence_fails_closed` (one clean + one cross-line occurrence -> raises).

### P0-2 (RESOLVED): the shared `_prose_stem` marker-strip altered redaction
Fix: `_prose_stem` is REVERTED (strips only provenance tokens + numbered markers, as before — byte-unchanged). The `[confidence: ...]` strip now happens LOCALLY inside `_annotate_line` and `_all_occurrences_labeled` (annotator path only), so a literal `[confidence: ...]` in report/audit text can never change the redactor's normalization or cause cross-claim mis-redaction. The 44 redactor tests pass unchanged.

## Re-confirm the unchanged safety contract
- C1: `_annotate_line` keeps the matching sentence + appends the marker; non-matching sentences + [N] markers byte-identical (VERIFIED untouched).
- C2 (now via the completeness check): never ships a non-VERIFIED claim unlabeled — pinned-unlabeled or straddle -> raise.
- C5: idempotent (local strip; re-run appends no second marker, no raise).

## Files (full diff: `.codex/I-perm-005/slice2_codex_diff.patch`)
- `src/polaris_graph/roles/report_redactor.py`: `_prose_stem` reverted; `_annotate_line` local strip; new `_all_occurrences_labeled`; `annotate_report_against_verdicts` uses it.
- `tests/roles/test_report_annotator_iperm005.py`: +1 straddle-leak regression (8 total).

## Test evidence: 8 annotator (incl. straddle-leak fail-closed + idempotent) + 44 redactor (byte-identical) green.

Confirm P0-1 (partial-label straddle now raises) + P0-2 (redactor normalization unchanged). Hunt any remaining unlabeled-ship path.
