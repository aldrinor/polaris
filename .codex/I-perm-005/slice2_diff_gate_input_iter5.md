# Codex DIFF review — I-perm-005 (#1199) SLICE 2 annotator — ITER 5 (FINAL, confirm idempotence fix)

```
HARD ITERATION CAP: 5 per document. This is iter 5 of 5 — the LAST. If you still REQUEST_CHANGES, the doc is force-APPROVED on remaining non-P0/P1 and residuals become a follow-up Issue. Surface any TRUE P0 now.
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

## Your iter-4 P1 (re-run over already-annotated two-same-line output raised because spans were computed on marker-bearing text) — RESOLVED.

**Fix:** `annotate_report_against_verdicts` now STRIPS all pre-existing `[confidence: ...]` markers from `report_text` at the very top (`report_text = _CONFIDENCE_MARKER_RE.sub("", report_text)`) BEFORE collecting claims or computing any span. So segmentation always runs on marker-free text — a re-run reproduces the same deterministic markers (idempotent), and a fresh report (no markers) is a byte no-op. New regression `test_idempotent_two_same_line_claims_rerun` (annotate twice -> count==2, no raise).

## Full safety contract (all prior fixes intact — confirm)
- Single pass off the unmutated (now marker-free) text -> two same-line claims each labeled (iter-3).
- `_claim_fully_pinnable` (marker-stripped + redactor TIER-1) fails closed on any straddle/under-split BEFORE labeling -> never ships a non-VERIFIED claim unlabeled (iter-1/iter-2).
- shared `_prose_stem` byte-unchanged; marker strip local -> redactor normalization untouched (P0-2). 44 redactor tests pass.
- VERIFIED sentences + [N] markers byte-identical.

## Files (full diff: `.codex/I-perm-005/slice2_codex_diff.patch`)
- `report_redactor.py`: up-front marker pre-strip; single-pass labeling; `_claim_fully_pinnable`; `_prose_stem` unchanged; `_annotate_line` removed.
- `test_report_annotator_iperm005.py`: 11 tests.

## Test evidence: 11 annotator + 44 redactor green.

Confirm idempotence (re-run) + no unlabeled-ship + redactor unchanged. This is the final iteration.
