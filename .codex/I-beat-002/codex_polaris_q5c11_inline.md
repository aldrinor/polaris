Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare ### Efficacy / Comparative):
"An analysis of hypothetical patient scenarios found that for a higher-income resident with a low medication burden, out-of-pocket costs ranged from $250 to $2100 across provinces, while for a lower-income resident with the same burden, costs ranged from $0 to $700."

CITED [1]: Hypothetical patient scenario analysis from Canadian pharmacare comparative literature.

PRIMARY-SOURCE CONTEXT:
- The hypothetical-patient-scenario methodology comparing provincial drug coverage costs is documented in multiple Canadian pharmacare studies (Morgan, Daw, etc.)
- The specific income-stratified ranges ($250-$2100 for higher-income / $0-$700 for lower-income) reflect provincial-formulary heterogeneity
- These figures should be traceable to a specific provincial pharmacare comparison study

AUDIT:
1. Is the hypothetical-patient-scenario methodology consistent with documented Canadian pharmacare comparative studies?
2. Are the specific range values ($250-$2100, $0-$700) consistent with provincial drug-coverage analyses?

Output YAML:
```yaml
claim_id: POLARIS-Q5-C11
cited_source_tier: T2_T3
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
