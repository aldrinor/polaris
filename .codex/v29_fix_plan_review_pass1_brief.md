You are Codex, step 6 of autoloop V2 — reviewing Claude's V29 fix plan.

## Context

V28 closed 2026-04-22 with cross-reviewed 3 BB + 0 BO + 4 LB (NOT
SHIPPABLE). §7 triggers #7 + #10 fired. User surfaced, reviewed
both auditors' strategic briefs, approved **Strategy β** — a
convergent 4-cycle architectural roadmap documented at
`outputs/audits/v28/strategic_cross_review.md`.

V29 is cycle 1 of 4. Scope is narrow per your lower-verdict-controls
discipline: selector custody + generator injection + per-anchor
telemetry ONLY. No cosmetic fixes (trial table), no M-47 relaxation,
no two-stage rewrite, no prompt rewrites.

## Your responsibility

Read Claude's draft plan at `outputs/audits/v28/fix_plan_v29.md`.
Evaluate each item against the V2 §5 schema:

- causal_stage populated and at earliest preventable point?
- prior_mechanism_gap evidence-backed (reference V28 artifacts)?
- preservation_risks stated and mitigated?
- acceptance_criteria measurable (specific fixture outcomes)?
- test_coverage real (not just "write tests")?
- classification root_cause / preservation_guard / band_aid
  justified?

Then answer the 5 self-critical questions Claude surfaced in the
plan's "Questions for Codex plan review" section:

1. M-51 cap mechanics — fixed at 11 or configurable env knob?
2. M-52 ev_id collision strategy — prefix `ev_from_corpus_` or
   preserve existing evidence_id?
3. M-53 quote-adequacy threshold — 100 chars (M-42b parity) or
   higher (e.g. 500 for full-frame extraction)?
4. M-51 backward-compat test explicit fixture?
5. V29 scope confirmation — defer trial-table / M-47 / two-stage /
   mechanism extraction to V30/V31?

## Output format

Write verdict to
`outputs/codex_findings/v29_fix_plan_review_pass1/findings.md`.

Structure (per prior pattern — V28 pass-2 template at
`outputs/codex_findings/v28_fix_plan_review_pass2/findings.md`):

- **Verdict**: APPROVED | CONDITIONAL | REJECT
- **Per-item verdicts** table M-51 / M-52 / M-53
  each with root_cause_approved | preservation_guard_approved |
  needs_revision | reject
- **Specific revisions required** if CONDITIONAL/REJECT
- **Answers to Claude's 5 self-critical questions**
- **Completeness review** — anything Claude missed that would
  block V29 from lifting Dims 1/4/5?
- **Implementation order confirmation or revision**

## V2 protocol notes

- Plan review ping-pong budget: up to 3 passes per §7 #11.
  V29 is pass-1. Budget intact.
- On APPROVED or CONDITIONAL-no-blockers: Claude begins M-51
  implementation immediately without further user check-in (per
  user's "follow tightly" directive and V2 autonomous-launch rule).
- On REJECT: Claude surfaces to user via PushNotification.

## Strategic continuity

Remember from your V28 strategic brief
(`outputs/codex_findings/v28_strategic_path/findings.md`):

- V29 should be "first architectural slice of β, not a narrow patch"
- "Do not spend V29 on table cosmetics, mechanism relaxation, or
  broad prompt rewrites"
- "If SURPASS-4 and SURPASS-CVOT are already in live_corpus and
  still absent from the report after V29, the architecture is
  failing at the exact custody boundary that must be fixed before
  7/7 is credible"

Does Claude's fix plan match that scope? Call out any deviation.
