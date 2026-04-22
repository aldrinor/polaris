You are Codex, running step 2b of autoloop V2: **DEEP CONTENT AUDIT**
of POLARIS V27 vs ChatGPT 5.4 Pro DR vs Gemini 3.1 Pro DR on the
tirzepatide/T2D question.

## This is NOT a metadata audit

Do not count URLs, measure word densities, or list dimension verdicts
from file-level stats. That has already been done (see
`outputs/audits/v27/{claude_audit,cross_review,gate_verdict}.md` and
`outputs/codex_findings/dr_output_pass_14_v27/findings.md`).

The user has explicitly asked for a CLAIM-BY-CLAIM audit. Apply:
- **PRISMA 2020** for systematic-review reporting quality
- **AMSTAR-2** for review methodology critical appraisal
- **GRADE** for certainty-of-evidence per claim
- **Clinical-epidemiology judgment** per specific number / dose /
  endpoint / timepoint / comparator

## Your job

For each of the six clinical topics below, read the three reports
side-by-side and identify — with direct quotes and specific line
references:

1. **Which report has the tightest claim frames** (sample size,
   baseline characteristics, comparator, dose, endpoint, timepoint,
   effect estimate + 95% CI or p, intention-to-treat vs per-protocol,
   open-label vs double-blind).
2. **Which report makes claims the evidence doesn't support**
   (embellishment, over-interpretation, comparator-elision, or
   citing meta-analyses for primary-trial claims they shouldn't).
3. **Which report omits material information** that competitors
   include (missing primary trial, missing subgroup, missing
   contradictory evidence, missing uncertainty).
4. **Which report misrepresents regulatory status** (wrong boxed-
   warning scope, wrong indication language, jurisdictional
   conflation).
5. **Which report offers specific numeric anchors** (HbA1c %,
   weight kg, effect sizes, event rates) vs hand-waving prose.

## Topics (read each report for each topic)

### A. SURPASS-2 (tirzepatide vs semaglutide 1 mg — head-to-head)
What N? What doses? What HbA1c deltas vs semaglutide? What weight
deltas? Primary vs secondary endpoints? Time point?

### B. SURPASS-CVOT (MACE non-inferiority vs dulaglutide)
What was the comparator? What was the MACE result? Time point?
Any superiority signal? Did any report claim cardiovascular
superiority when the data shows noninferiority?

### C. SURPASS-4 (high-CV-risk population vs insulin glargine)
104-week durability claim verified? Weight/HbA1c deltas vs
glargine at 104w? Any hypoglycemia reporting?

### D. Mechanism of action (dual GIP/GLP-1 agonism)
Receptor binding specifics (Kd, EC50 if cited)? Hyperinsulinemic
clamp data? Alpha cell vs beta cell effects? Clinical-to-mechanism
link (does any report cite insulin-sensitivity clamp data in humans
with T2D, Thomas 2021 Lancet D&E or similar)?

### E. Regulatory divergence (US vs EU vs UK vs CA)
- US: Mounjaro 2022 T2D + Zepbound 2023 weight-management +
  boxed warning (MTC/MEN2) + KwikPen counterfeit warning.
- EU: EMA Mounjaro pediatric ≥10 yrs T2D indication (novel vs US).
- UK: NICE TA924 T2D access criteria (BMI + ethnic-specific
  thresholds + triple-therapy failure + occupational criteria) +
  NICE TA1026 weight management.
- CA: Health Canada product monograph boxed warning + Canadian
  counterfeit/falsified-product advisories.

Which report names each jurisdiction's specific content vs
which report conflates or generalizes?

### F. Contradictions and uncertainty
Do any reports disclose heterogeneity in weight-loss effect
estimates (1.87% to 95.0% range cited in V27 contradictions.json
for 15mg)? Do any reports explicitly state open-label design
limitations? Do any reports flag Eli Lilly sponsorship bias?

## Format

Write to `outputs/codex_findings/v27_deep_content_audit/findings.md`.
Under 3000 words. Structure:

- Per-topic (A-F) section with:
  - "V27 claim" + quote + citation number
  - "ChatGPT claim" + quote
  - "Gemini claim" + quote
  - Your critical appraisal (PRISMA/AMSTAR-2/GRADE lens)
  - Winner for this topic

- Final aggregate section:
  - Total topics won / tied / lost per report
  - Which report is closest to a systematic-review standard
  - Which report is most clinically-useful for a physician

## Don't

- Don't re-run preservation suite
- Don't cite pipeline status / selector / manifest data — this is a
  CONTENT audit of the reports as clinical documents
- Don't accept either competitor's prose as canonical without
  checking against primary sources when available in the V27
  bibliography (which you have access to)
