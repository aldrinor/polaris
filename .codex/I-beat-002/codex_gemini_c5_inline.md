Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research):
"In the efficacy estimand, HbA1c dropped by -1.93% (5 mg), -2.20% (10 mg), and -2.37% (15 mg), compared to a -1.34% reduction with insulin degludec. While patients receiving insulin degludec gained an average of 2.3 kg, patients on tirzepatide experienced profound, dose-dependent weight losses ranging from -7.5 kg (5 mg) down to -12.9 kg (15 mg)."

CITED SOURCE: SURPASS-3 (Ludvik et al. 2021 Lancet).

PRIMARY SOURCE GROUND TRUTH (SURPASS-3, publicly known):
- 52-week trial, tirzepatide vs insulin degludec (titrated) on metformin background
- N=1,444 randomized
- HbA1c reductions (efficacy estimand, all 3 doses superior to degludec):
  - Tirzepatide 5mg: -1.93% (commonly reported)
  - Tirzepatide 10mg: -2.20%
  - Tirzepatide 15mg: -2.37%
  - Degludec: -1.34%
- Body weight: tirzepatide doses lose weight; degludec patients gain weight
  - Tirzepatide 5mg: -7.5 kg (commonly reported)
  - Tirzepatide 10mg: -10.7 kg
  - Tirzepatide 15mg: -12.9 kg
  - Degludec: +2.3 kg
- These values are documented in SURPASS-3 publication

AUDIT:
1. Gemini's HbA1c values (-1.93/-2.20/-2.37/-1.34) match published SURPASS-3 reports
2. Weight values (-7.5/-12.9 for 5/15mg, +2.3 for degludec) match published SURPASS-3 reports
3. Citation appropriate (T1 Lancet primary)

Output YAML:
```yaml
claim_id: GEMINI-C5
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
