Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare Population Subgroups + Long-term Outcomes):
"For working-age Quebecers, this translated to an access advantage; as of 2014, 9.2% of Quebecers aged 55 to 64 reported not filling prescriptions due to cost, compared to 13.9% of similarly aged residents in the rest of Canada."

CITED [4][5]: Pharmacare comparative literature (Morgan et al. CMAJ 2017 + similar).

PRIMARY-SOURCE GROUND TRUTH:
- Morgan et al. CMAJ 2017 reports CCHS 2014 cost-related non-adherence rates by province and age group.
- The 55-64 age group is the standard pre-Medicare-eligibility working-age category in Canadian health surveys.
- Specific 9.2% (Quebec 55-64) vs 13.9% (ROC 55-64) figures should be documented in Morgan 2017.
- This complements the 65+ subgroup (Q5-C5 verified earlier: 6.6% Quebec vs 4.1% ROC).
- The directional finding (Quebec working-age BETTER than ROC on cost-related non-adherence, but Quebec 65+ WORSE) is well-documented.

AUDIT:
1. Are 9.2% and 13.9% specific 2014 cost-related non-adherence rates for 55-64 from Morgan 2017?
2. Reasoning soundness: Quebec working-age advantage from public insurance for low-income + universal coverage.

Output YAML:
```yaml
claim_id: POLARIS-Q5-C13
cited_source_tier: T2_T3
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
