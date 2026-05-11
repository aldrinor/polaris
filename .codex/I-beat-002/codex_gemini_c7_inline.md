Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research):
"Participants utilizing the efficacy estimand achieved a staggering [weight reduction]: -15.0% (5 mg), -19.5% (10 mg), and -20.9% (15 mg), compared to -3.1% in placebo."

(Note: this is the SURMOUNT-1 efficacy estimand weight reduction reporting.)

CITED SOURCE: SURMOUNT-1 (Jastreboff et al. NEJM 2022).

PRIMARY SOURCE GROUND TRUTH (SURMOUNT-1 publicly documented):
- 72-week trial, adults with BMI ≥30 or ≥27 with weight-related complications, WITHOUT T2D
- N=2,539 randomized
- Efficacy estimand mean percentage weight change at 72 weeks:
  - Tirzepatide 5mg: -15.0% ✓
  - Tirzepatide 10mg: -19.5% ✓
  - Tirzepatide 15mg: -20.9% ✓
  - Placebo: -3.1% ✓
- All comparisons P<0.001

AUDIT:
1. All four decimal values (-15.0/-19.5/-20.9/-3.1) match published SURMOUNT-1 efficacy estimand
2. Cited source is correct (NEJM Jastreboff 2022)

Output YAML:
```yaml
claim_id: GEMINI-C7
cited_source_tier: T1
primary_source_verified: yes
decimals_match: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
