Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide):
"Significantly more participants in tirzepatide groups achieved HbA1c targets; a total of 82 to 86% of the patients who received tirzepatide and 79% of those who received semaglutide had a decrease in the glycated hemoglobin level to less than 7.0%, and a total of 69 to 80% of the patients who received tirzepatide and 64% of those who received semaglutide had a decrease in the glycated hemoglobin level to 6.5% or less."

CITED [1]: NEJM Frias 2021 SURPASS-2 https://www.nejm.org/doi/10.1056/NEJMoa2107519

PRIMARY SOURCE GROUND TRUTH:
- NEJM PubMed abstract PMID 34170647 does NOT contain HbA1c target attainment percentages — only treatment differences (-0.15%, -0.39%, -0.45% for HbA1c; -1.9, -3.6, -5.5 kg for weight).
- Secondary literature (commonly cited from full Frias et al. paper Table 2) reports:
  - HbA1c <7.0%: 82.4% (5mg), 85.5% (10mg), 86.2% (15mg) tirzepatide; 78.9% semaglutide
  - HbA1c ≤6.5%: 67.9% (5mg), 78.4% (10mg), 80.4% (15mg) tirzepatide; 63.7% semaglutide
- POLARIS reports "82 to 86%" and "79%" for <7%, "69 to 80%" and "64%" for ≤6.5%
- All POLARIS ranges match secondary-literature values closely (82-86 vs 82.4-86.2; 69-80 vs 67.9-80.4)
- Placebo percentages match within rounding

AUDIT: Are POLARIS's range claims consistent with the secondary-literature SURPASS-2 values?

Output YAML:
```yaml
claim_id: POLARIS-C4
cited_source_tier: T1
primary_source_verified: yes_via_secondary
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
