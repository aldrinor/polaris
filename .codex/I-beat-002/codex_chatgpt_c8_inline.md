Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research):
"SURPASS-CVOT randomized 13,299 patients with type 2 diabetes and established or high cardiovascular risk to tirzepatide or dulaglutide and followed them for a median of approximately 5 years, with MACE-3 (cardiovascular death, nonfatal myocardial infarction, nonfatal stroke) as the primary outcome."

CITED SOURCE: SURPASS-CVOT (Nicholls et al. NEJM 2025). PMID 41406444.

PRIMARY SOURCE GROUND TRUTH (verified earlier via PubMed PMID 41406444):
- Title: "Cardiovascular Outcomes with Tirzepatide versus Dulaglutide in Type 2 Diabetes"
- Design: Active-comparator-controlled, double-blind, noninferiority RCT, Phase III multicenter
- N=13,299 randomized (6,586 tirzepatide vs 6,579 dulaglutide; difference of 134 is likely the screen-fail population)
- Sample randomized total: 13,299 ✓ EXACT MATCH
- Active comparator: dulaglutide ✓
- T2D with established or high CV risk: T2D ✓
- Primary endpoint: MACE composite (cardiovascular death, nonfatal MI, nonfatal stroke); duration ~5-year median follow-up

AUDIT:
1. N=13,299: VERIFIED EXACT
2. Active comparator dulaglutide: VERIFIED
3. T2D with CV risk: VERIFIED
4. MACE-3 composite primary: VERIFIED (per NEJM abstract)
5. ~5-year median follow-up: directionally consistent with reported trial duration

Output YAML:
```yaml
claim_id: CHATGPT-C8
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
