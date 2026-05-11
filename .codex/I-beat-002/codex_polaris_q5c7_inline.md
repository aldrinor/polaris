Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare):
"with 8.8% of Quebec adults reporting skipping prescriptions due to cost in 2016 compared to 10.7% in the rest of Canada, this rate remains higher than in most comparator countries, where rates are 6% or less."

CITED [4][5]: Morgan et al. CMAJ 2017 + similar pharmacare comparative literature.

PRIMARY-SOURCE CONTEXT:
- Morgan et al. CMAJ 2017 (PMC5636629) reports Canadian Community Health Survey (CCHS) 2016 cost-related non-adherence rates
- Quebec adults 8.8% vs ROC 10.7% in 2016 — these specific decimals should be in Morgan 2017
- "<6%" international comparator from Commonwealth Fund or similar international surveys
- Directional finding (Quebec better than ROC for working-age, but both worse than international peers) is well-documented

AUDIT:
1. Are 8.8% and 10.7% specific 2016 cost-related non-adherence rates from Morgan 2017?
2. Is the "<6% in comparator countries" claim sourced appropriately?

Output YAML:
```yaml
claim_id: POLARIS-Q5-C7
cited_source_tier: T2_T3
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
