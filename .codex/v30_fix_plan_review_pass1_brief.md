You are Codex, step 6 of autoloop V2 — reviewing Claude's V30 fix plan.

## Context

User picked **Path A + B** (Report Contract Architecture + hybrid
human/licensed completion) per
`outputs/audits/v29/true_root_cause_cross_review.md`. Your sharper
framing ("Report Contract: required entities + required fields +
required rendering slots + required evidence binding; from
`retrieve then narrate` to `instantiate report schema then fill it`")
is the architectural basis.

V28 + V29 both landed 3 BB + 0 BO + 4 LB cross-reviewed. Custody
bundle was Codex-READY but dimensional outcome didn't move.
Falsifies custody-only as root cause. Both auditors agreed: the
report-contract architecture is the non-band-aid fix.

## Your responsibility

Read Claude's draft plan at `outputs/audits/v29/fix_plan_v30.md`.
Evaluate each of M-54 through M-62 against the V2 §5 schema:
causal_stage / prior_mechanism_gap / preservation_risks /
acceptance_criteria / test_coverage / classification.

Answer the 5 self-critical questions Claude surfaced:
1. Is M-54+M-55+M-56 ordering correct, or should M-56 lead?
2. M-58 slot-bound prompt: one-row-one-slot strict, or allow
   enrichment-row references?
3. M-61 fraud risk: is `consent_proof` string sufficient for
   human-curated quote provenance?
4. M-62 non-clinical template: materials vs policy vs ML?
5. Frame-element cost concern for 16 deterministic fetches + 16
   slot-bound generator calls per sweep?

## Output format

Write verdict to
`outputs/codex_findings/v30_fix_plan_review_pass1/findings.md`.

Structure:
- **Verdict**: APPROVED | CONDITIONAL | REJECT
- **Per-item verdicts**: M-54/55/56/57/58/59/60/61/62
- **Specific revisions required** (if CONDITIONAL/REJECT)
- **Answers to Claude's 5 self-critical questions**
- **Completeness review**: anything Claude missed?
  Particularly: does M-61 correctly protect against fraudulent
  human completion? Does M-60's gap language format meet your
  honesty-under-failure standard?
- **Implementation order confirmation**

## V2 protocol notes

- Plan review ping-pong budget: up to 3 passes per §7 #11.
  V30 = pass-1. Budget intact.
- On APPROVED / CONDITIONAL-no-blockers: Claude begins M-54
  implementation immediately per user's "follow tightly" +
  "execute" directives.
- On REJECT: PushNotification to user.

## Strategic continuity

Remember from your V29 true-root-cause brief
(`outputs/codex_findings/v29_true_root_cause/findings.md`):

- "the missing layer is a query-specific report contract"
- "every slot MUST exist in output even if partially empty"
- "`strict_verify` remains strict, but the output contract changes
  from omission to explicit insufficiency"
- "16 engineering days credible for a production-quality first cut"
- "the strongest non-band-aid alternative is hybrid: frame-first
  autonomous pipeline plus optional licensed/human evidence
  completion"

Does Claude's V30 fix plan match that framing? Call out any drift.

## Specific blockers to evaluate

1. **Layer 4 clarity**: the plan has M-58 (slot-bound prompts),
   M-59 (slot-completion validator), M-60 (gap reporting), M-61
   (human completion) all at Layer 4. Is the layering right, or
   should some of these be Layer 5?

2. **M-61 provenance integrity**: operator enters a quote claiming
   to be from a licensed source. strict_verify passes because it
   matches itself. Is there a stronger provenance guarantee we
   should require? E.g. source PDF hash + retention requirement?

3. **M-60 gap-language template**: Claude proposed verbatim
   "SURPASS-4 primary publication was not retrievable...". Is
   that the right level of explicitness, or should it carry more
   structural metadata (failure_reason, retrieval_attempt_log)?

4. **Regression test for architecture-not-hardcoding**: M-62 is
   listed as preservation_guard. Is that sufficient, or should
   additional tests verify that frame_compiler handles arbitrary
   entity types (not just pivotal_trial / mechanism_primary /
   regulatory)?

5. **Scope gate**: is 12-16 days across 9 items realistic, or
   would you add days to any specific item?
