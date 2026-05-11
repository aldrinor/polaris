Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research):
"SURPASS-CVOT later showed noninferiority versus dulaglutide for major cardiovascular events, with metabolic advantages favoring tirzepatide but without proving cardiovascular superiority."

CITED SOURCE: SURPASS-CVOT (Nicholls et al. NEJM 2025).

PRIMARY SOURCE GROUND TRUTH (verified via PubMed PMID 41406444 / NEJM 2025):
- Title: "Cardiovascular Outcomes with Tirzepatide versus Dulaglutide in Type 2 Diabetes"
- Active-comparator-controlled, double-blind, noninferiority RCT, Phase III multicenter
- N=13,165 randomized (6,586 tirzepatide vs 6,579 dulaglutide)
- Primary endpoint: 801 patients (12.2%) tirzepatide vs 862 (13.1%) dulaglutide
- Hazard ratio 0.92 (95.3% CI: 0.83–1.01)
- Noninferiority MET: P=0.003
- Superiority NOT MET: P=0.09
- Metabolic advantages (HbA1c, weight) favored tirzepatide
- Mean age 64.1±8.8, 29% female, BMI 32.6±5.5, HbA1c 8.4±0.9%

AUDIT:
1. "noninferiority vs dulaglutide for MACE": p=0.003 confirms noninferiority → YES
2. "metabolic advantages favoring tirzepatide": YES (HbA1c, weight)
3. "without proving cardiovascular superiority": p=0.09 (>0.05) → YES, superiority NOT met

Output YAML:
```yaml
claim_id: CHATGPT-C3
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
