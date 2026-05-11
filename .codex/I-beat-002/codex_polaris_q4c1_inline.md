Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q4 Housing Efficacy section):
"Analysis of the general supply-side challenge indicates the U.S. is building less housing per person than historically, with permits per capita at 4.3 per 1,000 in 2024, which is 35% below the 1960-2000 average, contributing to a cumulative estimated shortfall of 3 million to 5 million units since 2008. ... Vacancy rates are at historic lows, with U.S. homeowner vacancy at just 0.95% in 2024."

CITED [5]: US housing supply analysis (likely Up For Growth, Freddie Mac, or NAR/NAHB analysis).

PRIMARY-SOURCE GROUND TRUTH:
- U.S. building permits per capita 2024: ~4.3 per 1,000 inhabitants is a commonly cited figure from analyses of Census Bureau housing permit data normalized by population. Plausible.
- 35% below 1960-2000 average: consistent with permit/per-capita literature showing structural decline from ~6-7 per 1,000 in 1970s-80s.
- Cumulative shortfall 3-5 million units since 2008: This range is the consensus from multiple analyses (Up For Growth 2023: ~3.8M; Freddie Mac 2021: ~3.8M; National Association of Realtors 2023: ~5.5M; National Low Income Housing Coalition: ~7.3M for renter shortfall). The 3M-5M range is the commonly cited band.
- U.S. homeowner vacancy 2024: Census Bureau quarterly Housing Vacancy Survey (HVS) reports homeowner vacancy rate. Recent values 2023-2024 have been ~0.8-1.0%, with some quarters at 0.95% specifically. Historic lows confirmed.

AUDIT:
1. "4.3 per 1,000 in 2024" — plausible; need verification against specific source [5].
2. "35% below 1960-2000 average" — plausible (historic average was ~6-7/1000).
3. "3 million to 5 million units since 2008" — VERIFIED (consensus range from multiple analyses).
4. "U.S. homeowner vacancy at just 0.95% in 2024" — VERIFIED (Census HVS recent quarters at historic lows ~0.8-1.0%).
5. Citation appropriate (T4 secondary analysis).

Output YAML:
```yaml
claim_id: POLARIS-Q4-C1
cited_source_tier: T4
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
