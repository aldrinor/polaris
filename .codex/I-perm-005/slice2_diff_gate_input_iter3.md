# Codex DIFF review — I-perm-005 (#1199) SLICE 2 annotator — ITER 3 (confirm completeness fix)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
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

## Your iter-2 P0 (the appended marker perturbs `_sentence_spans` in the completeness scan, so a clean + same-line straddle-tail leaks) — RESOLVED. Verify against the code.

**Fix:** the post-marker `_all_occurrences_labeled` scan is REPLACED by `_claim_fully_pinnable(working, stem_norm)` run BEFORE labeling. It (1) strips ALL `[confidence: ...]` markers locally so segmentation is clean and immune to the marker (even across claims), then (2) runs the redactor's OWN TIER-1 `_redact_sentence` and returns False iff the stem is STILL present after removing every TIER-1-pinnable occurrence. So any non-TIER-1 occurrence (multi-line OR same-line straddle / under-split) makes the claim fail closed BEFORE any marker is appended. This is the exact "pinnable" notion the per-line annotate pass acts on, so a passing claim is fully labelable.

Your exact iter-2 case is now a regression test `test_clean_plus_same_line_straddle_tail_fails_closed` (`claim + " The therapy reversed organ\nfailure in the cohort..."` -> raises). Plus the multi-line straddle test. Run them.

## Re-confirm
- P0-2 still resolved: shared `_prose_stem` unchanged; marker strip local to `_claim_fully_pinnable` + `_annotate_line`. 44 redactor tests pass.
- VERIFIED untouched; non-VERIFIED never ships unlabeled (fail-closed before labeling).
- idempotent (re-run: stripped text -> TIER-1 removes the clean occurrence -> pinnable -> annotate appends nothing since marker present).

## Files (full diff: `.codex/I-perm-005/slice2_codex_diff.patch`)
- `report_redactor.py`: `_claim_fully_pinnable` (pre-pass, marker-stripped, redactor TIER-1); annotate calls it before labeling; `_prose_stem` unchanged.
- `test_report_annotator_iperm005.py`: 9 tests (+2 straddle fail-closed).

## Test evidence: 9 annotator + 44 redactor green.

Confirm the same-line straddle-tail now raises and the redactor is unchanged. Hunt any remaining unlabeled-ship path.
