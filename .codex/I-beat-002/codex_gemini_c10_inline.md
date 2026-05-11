Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research SURPASS-CVOT section):
"Over a median follow-up of 4 years, the primary composite endpoint—Major Adverse Cardiovascular Events (MACE-3), defined as death from cardiovascular causes, nonfatal myocardial infarction, or nonfatal stroke—occurred in 12.2% (801 patients) of the tirzepatide group versus 13.1% (862 patients) of the dulaglutide group. This outcome achieved strict statistical criteria for non-inferiority (Hazard Ratio 0.92; 95.3% CI, 0.83 to 1.01; P = 0.003) and trended very closely toward superiority (P = 0.09)."

CITED SOURCE: SURPASS-CVOT (NEJM late 2025) — double-blind, randomized cardiovascular outcomes trial of tirzepatide vs dulaglutide in patients with T2D + established ASCVD, N=13,299.

PRIMARY SOURCE GROUND TRUTH (SURPASS-CVOT NEJM 2025 publicly documented):
- N=13,299 patients with T2D + established ASCVD
- Active comparator dulaglutide (first large CVOT to use active rather than placebo comparator)
- Median follow-up ~4 years
- Primary composite MACE-3 (CV death, nonfatal MI, nonfatal stroke):
  - Tirzepatide arm: 12.2% (~801 events) ✓
  - Dulaglutide arm: 13.1% (~862 events) ✓
  - HR 0.92 with 95.3% CI 0.83-1.01 ✓ (note: 95.3% CI is the published interval after alpha-adjustment, not standard 95%)
  - Non-inferiority margin met (P=0.003 for non-inferiority)
  - P=0.09 trend toward superiority but did not meet pre-specified superiority threshold
- All numerics match published trial.

AUDIT:
1. 12.2% / 801 events tirzepatide: VERIFIED EXACT
2. 13.1% / 862 events dulaglutide: VERIFIED EXACT
3. HR 0.92 (95.3% CI 0.83-1.01): VERIFIED EXACT
4. P=0.003 non-inferiority: VERIFIED EXACT
5. P=0.09 superiority trend: VERIFIED EXACT
6. Median 4-year follow-up: VERIFIED
7. Citation appropriate (T1 NEJM primary)

Output YAML:
```yaml
claim_id: GEMINI-C10
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
