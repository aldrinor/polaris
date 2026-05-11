Read these 4 files only. Audit 5 claims listed below. Output YAML only, no prose.

Files:
- outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/report.md
- outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/bibliography.json
- outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json

Audit only these 5 claims from report.md ### Efficacy section:

C1: "tirzepatide 5 mg (-7.0 kg), 10 mg (-9.6 kg), and 15 mg (-11.2 kg) compared to semaglutide 1 mg (-5.7 kg) at week 40.[1]"
C2: "systematic review and meta-analysis of 14 RCTs involving 14,713 patients[2][3]"
C3: "tirzepatide 15 mg (-14.7%, SE 0.5), followed by the 10 mg dose (-12.8%, SE 0.6), versus placebo (-3.2%, SE 0.5; p<0.001 for all).[4]"
C4: "82 to 86% of the patients who received tirzepatide and 79% of those who received semaglutide had a decrease in the glycated hemoglobin level to less than 7.0%[1]"
C5: "weight loss with tirzepatide ranged from 7.25 kg to 10.36 kg across studies, whether used as monotherapy or add-on therapy.[5]"

For each: check (a) decimals in cited pool span (b) reasoning sound (c) citation appropriate tier.

Output ONLY:
```yaml
verdict: APPROVE | REQUEST_CHANGES
c1: { verdict: V|P|U|F|UR, reason: "..." }
c2: { verdict: V|P|U|F|UR, reason: "..." }
c3: { verdict: V|P|U|F|UR, reason: "..." }
c4: { verdict: V|P|U|F|UR, reason: "..." }
c5: { verdict: V|P|U|F|UR, reason: "..." }
findings: ["...", "..."]
```

APPROVE iff 0 F + 0 UR.
