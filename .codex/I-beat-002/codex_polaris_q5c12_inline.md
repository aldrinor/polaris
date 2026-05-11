Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare Population Subgroups):
"Overall increases in the utilization of prescription drugs result from point-of-sale price reductions to low or zero copayment, with prices borne directly by patients expected to fall by 47 per cent to 100 per cent, which results in overall increases in the utilization of prescription drugs of 13.5 per cent."

CITED [6]: Parliamentary Budget Officer (PBO) Bill C-64 or universal pharmacare cost analysis.

PRIMARY-SOURCE CONTEXT:
- The "47% to 100%" price reduction range and "13.5% utilization increase" figures are characteristic of PBO pharmacare cost modeling
- PBO uses an elasticity-of-demand framework to project utilization changes from copayment elimination
- The 13.5% utilization increase aligns with documented price-elasticity literature for prescription drugs (drug demand elasticity ≈ −0.2 to −0.3)
- These specific decimals should be in PBO's universal-pharmacare costing report

AUDIT:
1. Is the "47% to 100%" patient-borne price reduction range consistent with PBO methodology?
2. Is the "13.5%" utilization increase from PBO analysis?
3. Reasoning: economically sound — price drops to near-zero → predictable demand increase from elasticity

Output YAML:
```yaml
claim_id: POLARIS-Q5-C12
cited_source_tier: T3
primary_source_verified: partial
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
