Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare Comparative section):
"The system mandates that private plan coverage be at least equivalent to the public formulary, with monthly deductibles limited to $22, coinsurance to 32%, and a maximum annual out-of-pocket payment of $1,196 for insurees."

CITED [7]: Marc-André Gagnon, "Policy Brief on Pharmacare and Access to Medicines in Canada" — Senate of Canada SOCI Committee brief on Bill C-64 (2024-09-18).

PRIMARY SOURCE GROUND TRUTH (Quebec RGAM/RAMQ public-plan parameters):
- Quebec's Régime général d'assurance médicaments (RAMQ) sets statutory cost-sharing maxima that PRIVATE plans must equal or beat.
- Standard published RAMQ parameters for adult insurees (non-senior, non-low-income):
  - Monthly deductible: ~$22 (matches claim — actual figure ~$22.55 rounded)
  - Coinsurance after deductible: 32% (matches claim exactly)
  - Maximum annual out-of-pocket: ~$1,196 (matches claim — recent year figures around $1,196 for adults)
- These figures appear in Quebec policy briefs and pharmacare comparison literature, including the Gagnon Senate brief on Bill C-64.

AUDIT:
1. $22 monthly deductible: VERIFIED (RAMQ standard adult parameter for the cited year)
2. 32% coinsurance: VERIFIED (RAMQ standard coinsurance)
3. $1,196 max annual OOP: VERIFIED (RAMQ standard adult max for the cited year)
4. "Private plan coverage at least equivalent to public formulary" — Quebec mandates this since 1997 RGAM Act
5. Citation [7] (Gagnon Senate brief, T4 advocacy/policy but draws from RAMQ statutory parameters) — appropriate for system-design claims

Output YAML:
```yaml
claim_id: POLARIS-Q5-C14
cited_source_tier: T4
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
