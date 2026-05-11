Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare Comparative section):
"Quebec spends about $200 more per person on prescription drugs than the rest of Canada, with total per capita expenditure reaching $1,087 in 2014 compared to $912 in the rest of Canada."

CITED [4][2][5][3]: Morgan et al. CMAJ 2017 + similar pharmacare comparative literature.

PRIMARY-SOURCE CONTEXT:
- Morgan et al. CMAJ 2017 (PMC5636629) is the canonical source for these Quebec-vs-ROC per-capita drug spending comparisons.
- The $1,087 vs $912 (Quebec vs ROC) 2014 per-capita drug expenditure figures should be directly verifiable from Morgan 2017 Table or text.
- Difference 1087-912 = $175, rounded to "about $200 more" — this rounding is hedged appropriately.

AUDIT:
1. Are the specific decimals $1,087 and $912 consistent with Morgan et al. CMAJ 2017 documented figures?
2. Is the "$200 more" rounding appropriate given the exact $175 difference?

Output YAML:
```yaml
claim_id: POLARIS-Q5-C6
cited_source_tier: T2_T3
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
