# Codex DIFF review — I-perm-005 (#1199) SLICE 2: annotate_report_against_verdicts (keep + label)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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

## What this slice does
Adds `annotate_report_against_verdicts` to `report_redactor.py` — the always-release sibling of `reconcile_report_against_verdicts`: a non-VERIFIED claim is KEPT + LABELED (confidence marker appended) instead of DELETED. ADDITIVE: the existing redactor is byte-unchanged; nothing calls the annotator yet (the runner call-site flip is the next sub-step). Reuses the redactor's tiered LOCATE.

## Safety properties to verify (P0 class)
1. **VERIFIED untouched + never deletes.** `_annotate_line` byte-preserves every non-matching sentence + its [N] markers; for a matching (non-VERIFIED) sentence it appends ` {marker}` and KEEPS the prose (never `_GAP_REPLACEMENT`). Verify a VERIFIED claim's sentence + citation markers are byte-identical.
2. **Never ships a non-VERIFIED claim UNLABELED.** A present-but-unpinnable claim RAISES (same fail-closed as the redactor); a missing `marker_by_claim[id]` falls back to `_DEFAULT_LOW_MARKER`; a genuinely-absent claim is recorded in `already_absent`. Verify there is no path where a non-VERIFIED claim's prose stays in the report with no marker.
3. **A non-VERIFIED claim can never be labeled high.** The marker is the CALLER's (`claim_labeler.confidence_bucket` returns low/no-source-found for non-VERIFIED); this function only appends the string. Not a regression risk here, but confirm the function never invents a "high" marker.
4. **Idempotent + redactor no-op.** `_prose_stem` now also strips `[confidence: ...]`. Since the redactor runs annotate XOR reconcile (per PG_ALWAYS_RELEASE) and never sees the marker, confirm this strip cannot change redaction behavior (the 44 redactor tests pass). And confirm re-running annotate does not double-append.

If you find a path where a non-VERIFIED claim ships unlabeled, or a VERIFIED sentence/marker is altered, or the `_prose_stem` change alters redaction, that is a P0.

## Claims ledger
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | VERIFIED byte-identical, never deletes | `_annotate_line` keeps prose, appends marker; non-match verbatim | claims-true |
| C2 | non-VERIFIED never unlabeled | present-but-unpinnable raises; missing marker -> _DEFAULT_LOW_MARKER; absent recorded | claims-true |
| C3 | marker is caller's (never high here) | function appends marker_by_claim[id] or low fallback | claims-true |
| C4 | `_prose_stem` strip is redactor no-op | redactor never sees the marker (XOR); 44 redactor tests pass | claims-true |
| C5 | idempotent | `_prose_stem` strips the marker so a re-run matches + does not double-append | claims-true |

## Files (full diff: `.codex/I-perm-005/slice2_codex_diff.patch`)
- `src/polaris_graph/roles/report_redactor.py` (+~110): AnnotationResult/AnnotatedClaim, `_annotate_line`, `annotate_report_against_verdicts`, `_CONFIDENCE_MARKER_RE` + `_prose_stem` strip.
- `tests/roles/test_report_annotator_iperm005.py` (new, 7 tests).

## Test evidence: 7 annotator + 44 redactor (no regression) green.

Review the diff. Confirm C2 (never ships a non-VERIFIED claim unlabeled) + C4 (redactor no-op). Hunt any unlabeled-ship or VERIFIED-mutation path.
