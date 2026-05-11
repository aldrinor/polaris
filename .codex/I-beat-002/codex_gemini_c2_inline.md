Audit 1 claim. Output YAML only.

CLAIM (Gemini Deep Research):
"Corresponding weight reductions from a baseline of 85.9 kg were -7.0 kg (a 7.9% reduction) for the 5 mg dose and -7.8 kg (a 9.3% reduction) for the 10 mg dose."

CITED SOURCE: SURPASS-1 (Rosenstock et al. Lancet 2021).

PRIMARY SOURCE GROUND TRUTH (verified Lancet PubMed PMID 34186022 abstract 2026-05-11):
- Baseline HbA1c: 7.9%, Baseline BMI: 31.9 kg/m²
- Body weight reductions: "Tirzepatide induced a dose-dependent bodyweight loss ranging from 7.0 to 9.5 kg" (aggregate range across 5/10/15 mg doses)
- Specific per-dose weight values were NOT in the abstract (likely in full paper supplementary)
- N=478 (5mg=121, 10mg=121, 15mg=121, placebo=115)
- Baseline weight 85.9 kg NOT explicitly stated in abstract (might be in full paper baseline characteristics table)

AUDIT:
1. Baseline weight 85.9 kg: not in abstract, plausible for population with mean BMI 31.9
2. Weight reduction range 7.0-9.5 kg per abstract: -7.0 (5mg) and -7.8 (10mg) fall within range
3. 5 mg = -7.0 kg: matches lower bound of abstract range
4. 10 mg = -7.8 kg: within abstract range but specific value not in abstract
5. Percentage reductions (7.9%, 9.3%): derived from -7.0/85.9 ≈ 8.1%, -7.8/85.9 ≈ 9.1% — close to Gemini's 7.9%/9.3%

Output YAML:
```yaml
claim_id: GEMINI-C2
cited_source_tier: T1
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
