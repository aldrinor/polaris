You are auditing 1 specific claim from Gemini Deep Research. Output YAML only.

CLAIM (from Gemini DR tirzepatide report):
"the standard American Diabetes Association (ADA) target of HbA1c <7.0% was 81.8% for the 5 mg cohort, 84.5% for the 10 mg cohort, and 78.3% for the 15 mg cohort, compared to only 23.0% for the placebo group"

CITED SOURCE: SURPASS-1 (Rosenstock et al. 2021 Lancet).

PUBLISHED PRIMARY SOURCE GROUND TRUTH (from Lancet PubMed PMID 34186022 abstract, verified 2026-05-11):
- "Tirzepatide (all doses combined): 87-92% achieved HbA1c <7.0%"
- "Placebo: 20% achieved HbA1c <7.0%"
- Sample N=478 (5mg n=121, 10mg n=121, 15mg n=121, placebo n=115)
- Baseline HbA1c 7.9%, BMI 31.9
- Per-dose HbA1c <7.0% percentages NOT reported in PubMed abstract.

YOUR AUDIT:
1. Compare Gemini's per-dose percentages (81.8/84.5/78.3) to published abstract range (87-92%).
2. Compare Gemini's placebo (23.0%) to published placebo (20%).
3. Determine if Gemini's specific values are supported by the published Lancet abstract.
4. Note: per-dose breakdowns might be in full paper supplementary tables (not in abstract).

Output YAML:
```yaml
claim_id: GEMINI-C3
cited_source_tier: T1
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
