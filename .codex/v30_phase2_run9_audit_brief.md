V30 Phase-2 run-9 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md`
(2,812 words, 24 `###` subsections — highest yet).

## Context

Run-9 is the architectural completion of M-68 (drop-on-verify
gap-disclosure fallback) + M-68 Fix #1b (gap-disclosure citation
markers). All 15 contract slots now render with citations.

Run history scoreboard:

| Run | status | release | qwen verdicts | slots rendered |
|-----|--------|---------|----------------|----------------|
| 7   | success | True | 2G+2A+1NR | 11/15 (4 silent drops) |
| 8   | partial_qwen_advisory | False | 3G+2NR | 15/15 (gap disclosures uncited) |
| 9   | partial_qwen_advisory | False | 1G+1A+3NR | 15/15 (gap disclosures cited) |

Run-9 Qwen detail (verbatim):
- citation_tightness: needs_revision — "Multiple sections lack
  citations for key claims (e.g., SURPASS-1 baseline HbA1c).
  Some citations reference curator-actionable gaps rather than
  valid sources."
- hedging_appropriateness: needs_revision — "Numerous numeric
  discrepancies (weight loss across dosages) presented without
  hedging."
- completeness: needs_revision — "Major evidence gaps exist
  (SURPASS-5/6/CVOT primary data missing)."

## Tension to resolve

Per Codex's run-7 audit (`outputs/codex_findings/v30_phase2_run7_audit/findings.md:83`):
> A heading-with-gap statement is acceptable disclosure; silent
> loss of a manifest-passed subsection is not. Because run-7
> still silently loses SURPASS-6, FDA Mounjaro, EMA, and Health
> Canada, this remains a structural loss against both comparators.

Run-9 honored that doctrine — every slot now renders with a
citation marker. But Qwen's `release_allowed` rule disagrees: it
prefers silent drops (run-7 release=True) over honest gap
disclosures (run-9 release=False).

This is a **doctrine conflict** between PRISMA-style transparency
and Qwen's release gate. Both Claude and Codex agreed in run-7
that the PRISMA principle should win.

## Audit ask

Apply the same 7-dimension framework as run-7 audit:

1. Citations — primary-trial publications, ETD+CI+P, correct
   bindings, citation density on REAL claims (not gap disclosures)
2. Regulatory — substantive FDA + EMA + NICE + HC content
3. Jurisdiction — US + EU + UK + Canada coverage breadth
4. Claim-frames — PICO, dose stratification, uncertainty language
5. Structure — section order, ALL slots rendered, table integrity
6. Contradictions — tier-labeled explicit disclosure
7. Narrative depth — synthesis beyond extraction

For each: V30 BEAT_BOTH | BEAT_ONE | LOSE_BOTH | TIE.

## Specific reconciliation questions

1. **Structure dimension**: run-9 renders all 15 slots vs run-7's
   11. Is this a Structure BO or BB lift?

2. **Release-gate doctrine**: run-9 release_allowed=False but
   PRISMA-correct. Run-7 release_allowed=True but PRISMA-wrong
   (silent drops). Which gets the higher BEAT-BOTH score?

3. **Qwen completeness=needs_revision** — fair criticism (gap
   disclosures DO indicate primary-data missing) or unfair (V30
   honestly discloses what's missing while competitors paper
   over)?

4. **Trade-off framing**: should ship/checkpoint gate include
   release_allowed? Or is the 7-dim BB/BO/LB count the
   sufficient ship criterion?

5. **Net progress vs run-7**: BB count delta? Did anything
   regress, or did all dimensions stay or improve?

## Output

Write to `outputs/codex_findings/v30_phase2_run9_audit/findings.md`.

```markdown
# Codex V30 Phase-2 run-9 audit

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Net progress vs run-7: <BB+/-, BO+/-, LB+/->
- Regressions: <none | list>

## Doctrine call

<answer to question 2: release_allowed=False with full slot
rendering vs True with silent drops>

## 7-dimension analysis

<per-dim with line refs>

## Reconciliation with run-7 + run-8 trajectory

<are we ahead, behind, or stuck>

## Recommended action

<SHIP | CHECKPOINT-and-escalate-M-69 | ITERATE-with-narrow-fix-list>
```

Under 350 lines. Full xhigh budget.
