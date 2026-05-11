Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research):
"In SURPASS-1, tirzepatide produced up to 9.5 kg weight loss, roughly 11.0% of body weight."

CITED SOURCE: SURPASS-1 (Rosenstock et al. Lancet 2021).

PRIMARY SOURCE GROUND TRUTH (verified Lancet PubMed PMID 34186022 abstract 2026-05-11):
- "Tirzepatide induced a dose-dependent bodyweight loss ranging from 7.0 to 9.5 kg"
- Baseline HbA1c: 7.9%, baseline BMI: 31.9 kg/m²
- Baseline weight not in abstract; for population with BMI 31.9, mean weight likely ~85-90 kg
- 9.5 kg / 85 kg = 11.2%; 9.5/90 = 10.6% — both close to ChatGPT's claimed 11.0%
- N=478

AUDIT:
1. "up to 9.5 kg weight loss" — matches upper bound of Lancet abstract range exactly
2. "roughly 11.0% of body weight" — hedged with "roughly", math reasonable for typical baseline weight in this population
3. Citation appropriate (T1 Lancet primary).

Output YAML:
```yaml
claim_id: CHATGPT-C5
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
