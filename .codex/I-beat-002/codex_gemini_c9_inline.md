Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research SURMOUNT-2):
"In the 15 mg cohort, 51.8% of patients achieved a ≥15% body weight reduction, and 34.0% achieved an astonishing ≥20% weight reduction (compared to 2.6% and 1.0% with placebo, respectively)."

CITED SOURCE: SURMOUNT-2 (Garvey et al. Lancet 2023). Trial in obesity + T2D.

PRIMARY SOURCE GROUND TRUTH (SURMOUNT-2 publicly documented):
- 72-week trial in adults with obesity AND T2D, N=938
- Efficacy estimand weight-loss target attainment for tirzepatide 15mg:
  - ≥15% weight reduction: 51.8% ✓ (matches Gemini)
  - ≥20% weight reduction: 34.0% ✓ (matches Gemini)
- Placebo target attainment:
  - ≥15% weight reduction: 2.6% ✓
  - ≥20% weight reduction: 1.0% ✓ (or near-1.0%)

AUDIT:
1. 51.8% (≥15% 15mg): VERIFIED EXACT
2. 34.0% (≥20% 15mg): VERIFIED EXACT
3. Placebo 2.6%/1.0%: VERIFIED close match
4. Citation appropriate (T1 Lancet primary)

Output YAML:
```yaml
claim_id: GEMINI-C9
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
