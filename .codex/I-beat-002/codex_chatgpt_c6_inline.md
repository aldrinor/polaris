Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research):
"In SURPASS-3, tirzepatide was superior to insulin degludec for HbA1c and weight in adults inadequately controlled on metformin; tirzepatide doses reduced HbA1c by 1.93-2.37 percentage points and produced weight loss of 7.5-12.9 kg, while degludec increased weight by about 2.3 kg."

(Note: this is a synthesis of the SURPASS-3 reporting in the ChatGPT DR full text, which includes the trial-table claims.)

CITED SOURCE: SURPASS-3 (Ludvik et al. 2021 Lancet).

PRIMARY SOURCE GROUND TRUTH (SURPASS-3, publicly documented):
- 52-week, double-blind RCT, tirzepatide vs titrated insulin degludec on metformin background
- N=1,444 randomized
- HbA1c reductions (efficacy estimand):
  - Tirzepatide 5mg: -1.93%
  - Tirzepatide 10mg: -2.20%
  - Tirzepatide 15mg: -2.37%
  - Degludec: -1.34%
- Body weight changes:
  - Tirzepatide 5mg: -7.5 kg
  - Tirzepatide 10mg: -10.7 kg
  - Tirzepatide 15mg: -12.9 kg
  - Degludec: +2.3 kg
- All three tirzepatide doses superior to degludec for HbA1c (p<0.001)

AUDIT:
1. HbA1c range "1.93-2.37 percentage points" matches published 1.93%-2.37%
2. Weight range "7.5-12.9 kg" matches published values for 5mg-15mg
3. Degludec weight gain "about 2.3 kg" matches published +2.3 kg
4. Citation appropriate (T1 Lancet primary)

Output YAML:
```yaml
claim_id: CHATGPT-C6
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
