Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide-T2DM report):
"A separate systematic review and meta-analysis of 14 RCTs involving 14,713 patients confirmed that tirzepatide significantly reduced HbA1c levels and body weight compared to placebo, GLP-1 receptor agonists, and insulin."

CITED [2] and [3]: Liu et al. 2025, Pharmaceuticals (Basel). https://pubmed.ncbi.nlm.nih.gov/40430487/ (BOTH bibliography entries [2] and [3] point to the SAME URL — citation duplication.)

PRIMARY SOURCE GROUND TRUTH (from PubMed abstract, verified 2026-05-11):
- "Fourteen RCTs involving 14,713 patients were included"
- Comparators: "placebo, GLP-1 receptor agonists (GLP-1 RAs), and insulin"
- PROSPERO registered (CRD42021283449)
- Cochrane RoB 2 used
- Outcomes: ≥5%, ≥10%, ≥15% weight loss; HbA1c; waist circumference; blood pressure; AE rates
- Effect sizes NOT in abstract (require full paper)

AUDIT:
1. Verify "14 RCTs" claim against abstract
2. Verify "14,713 patients" against abstract
3. Verify "placebo, GLP-1 RAs, insulin" comparators against abstract
4. Verify qualitative claim "significantly reduced HbA1c and body weight"
5. Note duplicate-citation bug: [2] and [3] = same source

Output YAML:
```yaml
claim_id: POLARIS-C2
cited_source_tier: T1
primary_source_verified: yes
duplicate_citation_bug: yes_or_no
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
