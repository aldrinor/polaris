V30 sweep integration audit — pass 4.

**Skip git status.** Three files only.

## Context

Pass-3 found four new heuristic issues in
`_entity_cited_in_legacy`. After three rounds of tightening
each surfacing new false-passes, commit `4918bf3` takes a
structural change instead of another patch:

**Pass-4 scope narrow**: Phase-1 stops claiming report-coverage.
Verdicts now reflect ONLY M-56 retrieval success. A mandatory
warning is emitted on every V30 run so manifest readers can't
mistake a PASS for "generator cited this entity".

What's ignored:
- `_entity_cited_in_legacy` → no-op stub returning False.
- `_word_bounded_search` + regex cache → deleted (unused).
- Legacy cross-check heuristics → removed entirely.
- `legacy_report_text` + `legacy_bibliography` params → marked
  DEPRECATED, values ignored, retained for call-site backwards
  compat.

What Phase-1 claims:
- gap row → FAIL_MIN_FIELDS (curator-actionable)
- non-gap row → PASS (retrieval only)
- Mandatory warning: `phase1_retrieval_coverage_only` emitted
  every run.

## What to verify

Files (commit `4918bf3`):

1. `src/polaris_graph/v30_sweep_integration.py` — simplified
   `_synthesize_phase1_validation` + stub
   `_entity_cited_in_legacy`.
2. `scripts/run_honest_sweep_r3.py` — dropped report.md +
   bibliography read block.
3. `tests/polaris_graph/test_v30_sweep_integration.py` —
   18 tests (realigned to retrieval-coverage semantics).

## Questions

1. **Scope narrow honesty**: does Phase-1 now avoid overclaiming?
   The mandatory warning + renamed verdict semantics should
   prevent any caller from reading PASS as "cited in report".
2. **Warning visibility**: the warning goes into
   `manifest.v30_warnings[]`. Is that the right surface, or
   should it also go into the Methods disclosure prose
   appended to report.md?
3. **Deprecation stub**: `_entity_cited_in_legacy` always
   returns False now. Any test or caller that relies on a True
   return would break loudly. Acceptable deprecation path?
4. **Lost functionality**: Pass-3 found real false-negatives
   too (case-sensitive DOI matching). Those are moot now since
   no cross-check happens. Does anyone lose a legitimate
   capability with this scope change?
5. **Path to honest report-coverage**: the commit message
   points to Phase 2 (M-58 + M-59 integration) as where true
   report-coverage will come from. That's where every slot has
   a SlotFillPayload with verified citation tokens (no
   heuristic). Agree with that plan?
6. **Fourth-round adversarial**:
   - Can manifest output still be misread as overclaiming?
   - Any remaining path where phase-1 says PASS but the gap is
     actually in retrieval (e.g. M-56 returns a row with empty
     direct_quote but provenance_class != FRAME_GAP_UNRECOVERABLE)?
   - Does the mandatory warning survive JSON serialization?

## Output

Write to
`outputs/codex_findings/v30_sweep_integration_audit/pass4_findings.md`.

Format:
```markdown
# Codex V30 sweep integration audit — pass 4

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Scope narrow verification
<verified / still overclaims>

## Residual concerns
<anything>

## Next
On APPROVED / CONDITIONAL-no-blockers: sweep integration is
ready for Phase-1 live-run exercise. On anything else: Claude
iterates.
```

Keep under 60 lines. If APPROVED, task #28 moves to the actual
live-run sweep with PG_V30_ENABLED=1.
