V30 Phase-2 fix plan — Codex pass-2 review.

## Context

Pass-1 verdict: CONDITIONAL with 6 revisions. Claude wove all
6 into the plan at `outputs/audits/v30_phase2/fix_plan_phase2.md`.

Revisions summary (full table in the plan's "Codex pass-1
revisions" appendix):

1. **rev #1 citation-id mismatch**: M-63 fix #3 registers
   FrameRows into evidence_pool keyed by entity_id; rewriter
   pattern generalized or alias-layered.
2. **rev #2 sentence format**: M-63 fix #4 patches
   render_slot_prose to emit `value [id].` (period AFTER
   citation) so strict_verify's sentence splitter keeps the
   binding. Gap phrase template updates too.
3. **rev #3 output grain**: SECTION-level SectionResult; slots
   aggregate into sections; subsection_titles become `###`
   headings inside section prose.
4. **rev #4 M-41c preservation**: trial short-names ONLY in
   `### subsection_title` heading; body sentences use
   field:value format. M-41c is no-op-by-construction.
5. **rev #5 transition semantics**: keep
   `frame_coverage_report` key + add
   `coverage_semantics` field + add one-cycle
   `v30_phase2_transition` informational warning (replaces
   `phase1_retrieval_coverage_only`).
6. **rev #6 M-65 gate**: target-dimension requirement — at
   least one of {Claim Frames, Structural Depth} must move
   OFF LOSE_BOTH.

## Your responsibility

Read the revised plan. Verify all 6 revisions are addressed as
authored. Check for new issues introduced by the revisions.

## Specific blockers to evaluate

1. **Citation path choice**: Claude's M-63 fix #3 says
   "generalize rewrite pattern OR add alias layer; implementation
   will choose whichever is smaller diff after reading the
   actual rewriter". Is this "decide-later" acceptable, or should
   the plan commit to one path now?

2. **Sentence format change cascades**: M-63 fix #4 patches
   render_slot_prose format. The M-58 unit tests already lock
   in the current `value. [id]` format across 44 cases. Does
   the plan need to enumerate which M-58 tests must update, or
   is "all M-58 prose tests update" sufficient?

3. **M-41c-by-construction argument**: M-63 fix #6 claims
   "body sentences use field:value format with no trial name
   → M-41c is no-op-by-construction". Is that actually true
   for every required_field, or are there cases where the
   required_field name ITSELF (e.g. `etd_with_uncertainty`)
   when emitted as body prose fails M-41c's filter?

4. **ContractSectionPlanExt**: plan adds it as a new dataclass
   via `SectionPlan` inheritance. Can SectionPlan be inherited
   (is it a `@dataclass`, not frozen)? If yes, fine. If no,
   revise to standalone type + conversion method.

5. **Transition marker ergonomics**: `coverage_semantics =
   "phase2_report_coverage_via_m58_slot_bound_generation"` is
   long. Keep as-is for clarity, or shorten to
   `"phase2_report_coverage"` (Phase-1 would have been
   `"phase1_retrieval_coverage"`)?

## Output

Write verdict to
`outputs/codex_findings/v30_phase2_plan_review_pass1/pass2_findings.md`.

Structure:
- **Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL | REJECT
- **Revision-by-revision check**: each of 6 rev items.
- **New issues (if any)**: that the revisions introduced.
- **Implementation greenlight**: if APPROVED or
  CONDITIONAL-no-blockers, Claude auto-runs M-63.

Keep under 100 lines. gpt-5.4 xhigh.
