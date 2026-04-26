V30 final plan review — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Final consolidation pass. We have produced (in order):

  1. Codex strategic plan `findings.md` → joint commercialization
     plan `JOINT_PLAN.md` (Claude integrated audit-only + Evidence
     Inspector pivot per user mandate "best of the best quality" +
     "biggest impact / differentiation UI")
  2. Codex per-wish deep dive `findings.md` + Codex 35-source primary
     research → joint user-wishlist analysis pass-1 → your PARTIAL
     review with 7 fixes → pass-2 with all 7 fixes integrated
  3. Now: consolidated `FINAL_PLAN.md` at
     `outputs/codex_findings/v30_final_plan/FINAL_PLAN.md`

User's question to Claude: "is this plan both Claude and Codex agree?"

Honest answer per autoloop V2 protocol: NOT YET — your pass-1 review
of `JOINT_ANALYSIS.md` returned PARTIAL with 7 fixes; Claude integrated
all 7 in pass-2 but you have not re-reviewed pass-2, AND you have not
reviewed the consolidated `FINAL_PLAN.md`.

This brief is asking for that final sign-off.

## Your job

Read `outputs/codex_findings/v30_final_plan/FINAL_PLAN.md` end-to-end.
Verdict: GREEN / PARTIAL / DISAGREE.

This is the document we will ship from. If GREEN, we move to Phase A
ticket-level breakdown. If PARTIAL, list specific edits (don't repeat
the previous 7; we integrated those — flag NEW issues if any). If
DISAGREE, surface the structural disagreement clearly.

## Specific things to validate

1. **Did Claude integrate all 7 of your pass-1 fixes correctly?** Spot-check:
   - Wish #1 renamed to "Question-Bound Corpus Brief" (not "Workspace Brief")
   - Wish #2 estimate at 25-40 eng days (not 15-25)
   - Composition section rewritten with audit IR canonical
   - Memory split into session / workspace / global with global quarantined
   - 1-click UX expanded with progressive audit-native surfaces
   - PRD bundle scope at 70-110 eng days = 7-11 weeks
   - Sequencing note about deck beta as better late-B candidate

2. **Audit-lane-only pivot.** Claude cut the dual-lane Preview+Audit
   recommendation per user "best quality" mandate. Does this hold up?
   Or do you see a structural problem with single-lane that the
   progressive in-run surfaces don't solve?

3. **Evidence Inspector as canonical primary renderer.** Pass-2
   integrated this from your review. Does the FINAL_PLAN now treat
   it consistently as the primary renderer (not just another viewer)?

4. **Risk register completeness.** 12 risks listed with prob/impact.
   Anything missing or miscalibrated?

5. **Phase A → B sequencing.** Does it land cleanly? Are there
   dependencies that should block (e.g., is Phase A Evidence Inspector
   really feasible without bounded upload, or do they need to land
   together)?

6. **The "we explicitly refuse to build" list.** Is this list correct,
   or are we refusing something we shouldn't?

7. **Anything Claude missed in this consolidation.**

## What you should output

Write to `outputs/codex_findings/v30_final_plan_review/findings.md`:

```markdown
# Codex final review of V30 FINAL_PLAN

## Verdict
GREEN / PARTIAL / DISAGREE

## Pass-1 fix integration check
For each of the 7 fixes from previous review:
- [x] integrated correctly
- [ ] partial / needs adjustment
- specific edits if any

## Audit-lane-only assessment
Does single-lane hold up under progressive surfaces?

## Evidence Inspector as canonical renderer
Consistently treated?

## Risk register
Missing risks / miscalibrated probabilities?

## Phase sequencing
Dependencies correct? Blockers?

## Refusal list
Correct? Missing items? Items that shouldn't be refused?

## What Claude missed in consolidation
Specific gaps.

## Final verdict
GREEN to ship as the canonical plan / PARTIAL with specific edits
listed / DISAGREE with structural reasoning.
```

Be direct. Under 500 lines. Full xhigh budget. If GREEN, say so plainly
so the user can trust the joint sign-off.
