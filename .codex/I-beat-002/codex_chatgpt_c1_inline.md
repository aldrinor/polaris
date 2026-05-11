Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research tirzepatide):
"In SURPASS-2, tirzepatide 10 mg and 15 mg were superior to semaglutide 1 mg for HbA1c and all three tirzepatide doses were superior for weight loss; at 40 weeks, the HbA1c treatment differences versus semaglutide were −0.15%, −0.39%, and −0.45%, and the weight differences were −1.9 kg, −3.6 kg, and −5.5 kg for tirzepatide 5, 10, and 15 mg, respectively."

CITED SOURCE: NEJM Frias et al. 2021 SURPASS-2. https://www.nejm.org/doi/10.1056/NEJMoa2107519

PRIMARY SOURCE GROUND TRUTH (verified from NEJM PubMed PMID 34170647 abstract 2026-05-11):
- HbA1c treatment differences vs semaglutide 1mg at 40 weeks:
  - Tirzepatide 5mg: −0.15% (95% CI −0.28 to −0.03, p=0.02)
  - Tirzepatide 10mg: −0.39% (95% CI −0.51 to −0.26, p<0.001)
  - Tirzepatide 15mg: −0.45% (95% CI −0.57 to −0.32, p<0.001)
- Weight treatment differences vs semaglutide 1mg at 40 weeks:
  - Tirzepatide 5mg: −1.9 kg
  - Tirzepatide 10mg: −3.6 kg
  - Tirzepatide 15mg: −5.5 kg (all P<0.001)
- N=1879, open-label, sponsor Eli Lilly

Output YAML:
```yaml
claim_id: CHATGPT-C1
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
