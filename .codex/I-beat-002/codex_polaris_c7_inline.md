Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide ### Comparative):
"This trial also showed significantly greater weight loss with tirzepatide, with reductions of −7.8 kg, −10.3 kg, and −12.4 kg for the 5 mg, 10 mg, and 15 mg doses, respectively, versus −6.2 kg with semaglutide 1 mg. Consequently, higher percentages of tirzepatide-treated patients achieved weight loss of at least 5% (65-80% vs 54%), 10% (34-57% vs 24%), and 15% (15-36% vs 8%) compared to semaglutide."

CITED [1][9]: SURPASS-2 (NEJM Frias 2021) + MDPI tirzepatide review.

PRIMARY SOURCE GROUND TRUTH:
- SURPASS-2 NEJM abstract reports ONLY weight treatment DIFFERENCES (-1.9, -3.6, -5.5 kg vs semaglutide 1mg).
- Absolute weight values per arm not in NEJM abstract — must come from full paper.
- Different sources report different SURPASS-2 ABSOLUTE values:
  - Efficacy estimand: typically -7.6 kg (5mg), -9.3 kg (10mg), -11.2 kg (15mg) vs -5.7 kg (sema)
  - Treatment-regimen estimand: typically -7.8 kg, -10.3 kg, -12.4 kg vs -6.2 kg
- POLARIS reports -7.8 / -10.3 / -12.4 vs -6.2 — these are the TREATMENT-REGIMEN estimand values
- Derived differences: -1.6 (5mg), -4.1 (10mg), -6.2 (15mg) — close to NEJM TR estimand published diffs
- The "≥5%/10%/15% weight loss" percentage ranges (65-80%/34-57%/15-36% vs 54%/24%/8%) are SURPASS-2 published Table 2 percentages.

AUDIT:
1. Are the absolute weight values consistent with SURPASS-2 treatment-regimen estimand?
2. Are the weight-loss percentage ranges consistent with published SURPASS-2 Table 2?

Output YAML:
```yaml
claim_id: POLARIS-C7
cited_source_tier: T1
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
