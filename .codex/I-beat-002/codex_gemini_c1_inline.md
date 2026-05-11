Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research):
"reductions in HbA1c from a baseline of 7.9% were -1.87% for the 5 mg dose and -1.89% for the 10 mg dose"

CITED SOURCE: SURPASS-1 (Rosenstock et al. Lancet 2021).

PRIMARY SOURCE GROUND TRUTH (verified Lancet PubMed PMID 34186022 abstract 2026-05-11):
- Baseline HbA1c: 7.9% (63 mmol/mol) ✓ EXACT MATCH
- HbA1c reductions at 40 weeks:
  - Tirzepatide 5 mg: -1.87% (20 mmol/mol) ✓ EXACT MATCH
  - Tirzepatide 10 mg: -1.89% (21 mmol/mol) ✓ EXACT MATCH
  - Tirzepatide 15 mg: -2.07% (23 mmol/mol)
  - Placebo: +0.04%
- Sample N=478 (5mg=121, 10mg=121, 15mg=121, placebo=115)

AUDIT: Do the cited decimals (-1.87%, -1.89%, baseline 7.9%) exactly match the Lancet primary source?

Output YAML:
```yaml
claim_id: GEMINI-C1
cited_source_tier: T1
primary_source_verified: yes
decimals_match: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
