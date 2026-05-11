Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide ### Safety):
"Gastrointestinal adverse events are the most common treatment-emergent adverse effects with tirzepatide and are typically mild-to-moderate in severity."

CITED [4]: 2minutemedicine.com commentary (T4)
CITED [7]: Long-term safety paper (pubmed.ncbi.nlm.nih.gov/40926359/) (T1)
CITED [8]: Nature article post-lifestyle intervention (T4)

PRIMARY-SOURCE CONTEXT:
- This is a well-established clinical pattern across ALL major tirzepatide RCTs (SURPASS-1 through 6 + SURMOUNT-1/2/3).
- GI AEs (nausea, vomiting, diarrhea) are consistently the most common AEs in every tirzepatide trial.
- They are reported as "mild-to-moderate in severity" in NEJM/Lancet/JAMA SURPASS publications.
- No specific decimals to verify; this is a qualitative class claim.

AUDIT:
1. Citation mix: [4] T4 + [7] T1 + [8] T4. T1 source [7] alone is sufficient for this claim. T4 sources are non-additive.
2. Reasoning: well-supported clinical class pattern, GRADE HIGH certainty.
3. Verdict: claim is consistent with the established tirzepatide safety profile across all published RCTs.

Output YAML:
```yaml
claim_id: POLARIS-C5
cited_source_tier: T1+T4_mixed
citation_appropriate: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
