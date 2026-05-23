# Codex DIFF review — I-bug-776 (#817): afib primary-trial anchors. Iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `6353dbc299481de41409ba47c27300fcc98f34ff8d89b6dda9b7d9864e579606`. Config-only (config/scope_templates/clinical.yaml,
+~14 lines). Implements YOUR decision b1. MERGE AUTHORIZED if mergeable + APPROVE
iff zero P0/P1.

## What (your b1 decision)
Added `per_query_primary_trial_anchors[clinical_afib_anticoagulation]` +
`per_query_primary_trial_variants[...]` for the four landmark NOAC-vs-warfarin
pivotal RCTs:
- ARISTOTLE (Granger, NEJM 2011, apixaban vs warfarin)
- ROCKET-AF (Patel, NEJM 2011, rivaroxaban vs warfarin)
- RE-LY (Connolly, NEJM 2009, dabigatran vs warfarin)
- ENGAGE-AF-TIMI-48 (Giugliano, NEJM 2013, edoxaban vs warfarin)
These are THE four trials every NVAF anticoagulation guideline (ESC/ACC-AHA) is
built on — molecule+indication-specific (apixaban/rivaroxaban/dabigatran/
edoxaban for NVAF), no company-wide stuffing. Slug-scoped (no global fallback).
NO clinical.json adequacy change (per your guardrail).

## Trial-fact accuracy (LAW II — real data only)
Verify the trial→drug→author→journal facts: ARISTOTLE=apixaban/Granger/NEJM2011;
ROCKET-AF=rivaroxaban/Patel/NEJM2011; RE-LY=dabigatran/Connolly/NEJM2009;
ENGAGE-AF-TIMI-48=edoxaban/Giugliano/NEJM2013. These are landmark + universally
cited; flag any inaccuracy.

## Smoke evidence
expand_primary_trial_queries(afib_question, template, 'clinical_afib_anticoagulation')
emits 8 queries (4 anchors x bare+variant); no-anchor slug ('tech_rag...') -> 0
(negative check); tirzepatide anchors intact.

## Guardrails honored (your decision)
- Slug-scoped only, no global fallback.
- Anchors are trial+drug+condition specific (ROCKET-AF/ARISTOTLE etc. are
  unambiguous AF-anticoagulation trial acronyms).
- No clinical.json T1>=3 relaxation.
- M-35 counts a row as T1 only if the retrieved source is a primary trial
  (downstream tiering unchanged).

## Review focus
1. Trial-fact accuracy (any wrong drug/author/journal/year)?
2. Any anchor ambiguous/off-topic (would retrieve reviews not primaries)?
3. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
