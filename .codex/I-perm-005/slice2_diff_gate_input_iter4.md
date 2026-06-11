# Codex DIFF review — I-perm-005 (#1199) SLICE 2 annotator — ITER 4 (confirm single-pass fix)

```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
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

## Your iter-3 P0 (claim A's marker perturbs claim B's same-line segmentation in the LABELING pass; B ships unlabeled but recorded annotated) — RESOLVED. Verify against the code.

**Fix:** the per-claim sequential `_annotate_line` mutation is REPLACED by a SINGLE labeling pass. (1) All non-VERIFIED claims are collected (validate + presence + `_claim_fully_pinnable`) into `claims`. (2) ONE pass over the ORIGINAL `report_text` lines: for each `_sentence_spans(line)` span (spans read off the UNMUTATED original line — never a marker-mutated one), the sentence is matched marker-stripped against each claim's stem and labeled once with the first match. So two same-line claims each get their own marker; no appended marker can perturb another claim's span. (3) Defensive: a collected (pinnable) claim that matched no sentence in the pass fails closed. `_annotate_line` is deleted (dead).

Your exact iter-3 repro is now a regression test `test_two_same_line_non_verified_claims_both_labeled` (two same-line UNSUPPORTED claims -> `count("[confidence:") == 2`, annotated_count 2). Run it.

## Re-confirm
- Both straddle fail-closed tests still pass (multi-line + same-line tail).
- VERIFIED byte-identical; non-VERIFIED never unlabeled.
- P0-2 still resolved: shared `_prose_stem` unchanged; marker strip local. 44 redactor tests pass.
- idempotent (marker-stripped match + append-only-if-absent).

## Files (full diff: `.codex/I-perm-005/slice2_codex_diff.patch`)
- `report_redactor.py`: single-pass `annotate_report_against_verdicts`; `_claim_fully_pinnable` pre-check; `_annotate_line` removed; `_prose_stem` unchanged.
- `test_report_annotator_iperm005.py`: 10 tests (+ two-same-line-claims).

## Test evidence: 10 annotator + 44 redactor green.

Confirm two same-line claims both get markers and no unlabeled-ship path remains.
