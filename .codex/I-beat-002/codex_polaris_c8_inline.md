Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide ### Comparative):
"A greater proportion of patients achieved HbA1c targets with tirzepatide, including 69-80% reaching ≤6.5% and 27-46% reaching <5.7%, compared to 64% and 19%, respectively, with semaglutide."

CITED [1]: SURPASS-2 NEJM Frias 2021.

PRIMARY SOURCE GROUND TRUTH (SURPASS-2 publicly documented Table 2):
- HbA1c <5.7% (normoglycemia) achievement:
  - Tirzepatide 5mg: 27.2%
  - Tirzepatide 10mg: 39.7%
  - Tirzepatide 15mg: 45.7%
  - Semaglutide 1mg: 19.4%
- HbA1c ≤6.5% achievement:
  - Tirzepatide 5mg: 67.9%
  - Tirzepatide 10mg: 78.4%
  - Tirzepatide 15mg: 80.4%
  - Semaglutide 1mg: 63.7%

POLARIS ranges:
- ≤6.5% "69-80%": close to 67.9-80.4% range (within 1 percentage point on low end)
- <5.7% "27-46%": matches 27.2-45.7% range
- Semaglutide 64% (≤6.5%) ≈ 63.7% (rounding)
- Semaglutide 19% (<5.7%) ≈ 19.4% (rounding)

AUDIT: Are the range values and semaglutide comparator percentages consistent with SURPASS-2 published values?

Output YAML:
```yaml
claim_id: POLARIS-C8
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
