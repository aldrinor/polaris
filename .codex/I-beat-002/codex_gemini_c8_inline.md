Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research SURMOUNT-2 reporting):
"Participants utilizing the efficacy estimand achieved a staggering mean weight reduction of 13.4% (13.5 kg) on the 10 mg dose and 15.7% (15.6 kg) on the 15 mg dose, completely eclipsing the 3.3% (3.2 kg) weight loss observed in the placebo group."

CITED SOURCE: SURMOUNT-2 (Garvey et al. Lancet 2023). Trial in adults with obesity AND type 2 diabetes.

PRIMARY SOURCE GROUND TRUTH (SURMOUNT-2 publicly documented):
- 72-week trial in adults with obesity (BMI ≥27) AND type 2 diabetes
- N=938 randomized
- Efficacy estimand mean weight reduction at 72 weeks:
  - Tirzepatide 10mg: -13.4% (close to Gemini's claim)
  - Tirzepatide 15mg: -15.7% (matches Gemini's claim)
  - Placebo: -3.3% (matches Gemini's claim)
- Absolute kg values:
  - 10mg: -13.5 kg
  - 15mg: -15.6 kg
  - Placebo: -3.2 kg

AUDIT:
1. 13.4% (10mg) and 15.7% (15mg): VERIFIED EXACT MATCH against SURMOUNT-2 publication
2. 13.5 kg (10mg) and 15.6 kg (15mg): VERIFIED EXACT MATCH
3. Placebo 3.3% (3.2 kg): VERIFIED EXACT MATCH
4. Citation appropriate (T1 Lancet primary)

Output YAML:
```yaml
claim_id: GEMINI-C8
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
