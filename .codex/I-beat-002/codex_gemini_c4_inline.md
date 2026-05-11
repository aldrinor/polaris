Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research):
"In this population, the highest dose of tirzepatide drove an HbA1c reduction of 2.58% and a massive body weight reduction of 11.7 kg (13.0% of body weight) from a baseline of 90.3 kg."

CITED SOURCE: SURPASS-4 (Del Prato et al. Lancet 2021). https://pubmed.ncbi.nlm.nih.gov/34672967/

PRIMARY SOURCE GROUND TRUTH (verified via PubMed PMID 34672967 abstract 2026-05-11):
- SURPASS-4: tirzepatide vs insulin glargine in T2D with CV risk
- HbA1c reductions at 52 weeks:
  - Tirzepatide 5mg: not specified in abstract preview
  - Tirzepatide 10mg: -2.43% (SD 0.05)
  - Tirzepatide 15mg: -2.58% (SD 0.05) ← MATCHES Gemini's 2.58%
  - Insulin glargine: -1.44% (SD 0.03)
- Treatment differences vs glargine: -0.99% (10mg) and -1.14% (15mg)
- N=2002 randomized; baseline characteristics not in abstract preview
- Weight changes per arm not in abstract preview (likely in full paper)

AUDIT:
1. HbA1c 2.58% at 15mg: VERIFIED EXACT MATCH against Lancet abstract
2. Weight reduction 11.7 kg: not in abstract; plausible for 15mg arm based on other SURPASS data
3. 13.0% of body weight: derived as 11.7/90.3 = 12.96% ≈ 13.0% — math checks
4. Baseline 90.3 kg: not in abstract; this is the population baseline weight, would be in full paper Table 1

Output YAML:
```yaml
claim_id: GEMINI-C4
cited_source_tier: T1
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
