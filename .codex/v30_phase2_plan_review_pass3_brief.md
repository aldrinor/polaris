V30 Phase-2 fix plan — Codex pass-3 review.

## Context

Pass-2 verdict: CONDITIONAL. Four issues blocked greenlight:
- Stale pass-1 bullets contradicted pass-1 revisions in
  preservation_risks, Acceptance, and Self-critical sections.
- `render_slot_prose` body-only change not explicit.
- Citation path still said "generalize OR alias".
- M-41c "skip" language contradicted "no-op by construction".
- Acceptance still said "1 SectionResult per slot".

Commit (not committed yet, plan file updated in place)
reconciles all four:
- Preservation-risks bullet 2 rewritten to say "no-op by
  construction", no sentinel.
- Preservation-risks bullet 3 rewritten to COMMIT to generalizing
  the regex (not alias).
- Acceptance #1 corrected to "1 SectionResult per CONTRACT
  SECTION (3 for clinical)".
- `render_slot_prose` body-only change specified in
  Acceptance fix #2 ("function is modified to return body-only
  prose (no inline {subsection_title}: prefix)").
- Self-critical questions marked CLOSED with Codex pass-1 Q&A
  accepted as-authored.
- `coverage_semantics` enum values shortened to
  `phase1_retrieval_coverage` / `phase2_report_coverage`.
- Test coverage table lists each of the 10 M-63 tests +
  identifies the M-58/M-59 fixture files that need updating.
- Codex pass-1 revisions table updated with pass-2 clarifications.

## What to verify

Read the revised plan at
`outputs/audits/v30_phase2/fix_plan_phase2.md`.

Check each pass-2 finding is resolved:

1. ✓ Stale "skip M-41c" language (pass-2 finding 4) — should be
   gone; only "no-op by construction" remains.
2. ✓ Stale "1 SectionResult per slot" in Acceptance (pass-2
   finding 3) — should now say "per CONTRACT SECTION".
3. ✓ `render_slot_prose` body-only change explicit (pass-2 new
   issue #1) — should be in Acceptance fix #2.
4. ✓ Citation path committed to generalize (pass-2 finding 1) —
   should NOT say "alias OR generalize"; should pick generalize.
5. ✓ Self-critical Q1 "skip M-41c" reopening — should be CLOSED
   with pass-1 Q&A accepted.
6. ✓ `ContractSectionPlanExt` vs `ContractSectionPlan`: should
   be named distinct from M-57's existing `ContractSectionPlan`
   or framed as an adapter.
7. ✓ `coverage_semantics` enum shortened.

## Output

Write to
`outputs/codex_findings/v30_phase2_plan_review_pass1/pass3_findings.md`.

Format:
```
Verdict: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL | REJECT
<per-finding check>
<residual concerns>
<Implementation greenlight: yes/no>
```

Keep under 80 lines. If APPROVED or CONDITIONAL-no-blockers,
Claude auto-runs M-63 immediately.
