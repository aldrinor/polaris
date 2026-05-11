Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide-T2DM report):
"That trial also reported the greatest bodyweight reduction at week 72 with tirzepatide 15 mg (-14.7%, SE 0.5), followed by the 10 mg dose (-12.8%, SE 0.6), versus placebo (-3.2%, SE 0.5; p<0.001 for all)."

CITED SOURCE [4]: "Once-weekly tirzepatide significantly improves weight and glycemic control..."
URL: https://www.2minutemedicine.com/once-weekly-tirzepatide-significantly-improves-weight-and-glycemic-control-in-patients-with-with-obesity-and-type-2-diabetes/

PRIMARY-SOURCE CONTEXT:
- The underlying trial is SURMOUNT-2 (Garvey et al. Lancet 2023): 72-week trial in obesity + T2D, N=938.
- Published Lancet SURMOUNT-2 numbers: tirzepatide 15mg −15.7%, 10mg −13.4%, placebo −3.3% mean weight change at week 72.
- POLARIS's cited [4] is a tertiary commentary site (2minutemedicine.com), NOT the primary Lancet paper. Tier T4.

POLARIS values vs published Lancet:
- 15mg: POLARIS −14.7% vs Lancet −15.7% (off 1.0 pp)
- 10mg: POLARIS −12.8% vs Lancet −13.4% (off 0.6 pp)
- Placebo: POLARIS −3.2% vs Lancet −3.3% (off 0.1 pp)

YOUR AUDIT:
1. Does POLARIS cite the appropriate primary source (T1 Lancet) or a tertiary T4 commentary?
2. Do POLARIS's specific decimals match the published Lancet primary source?
3. Citation appropriateness per §-1.1 (T1 primary trial papers preferred for trial-specific decimals)?

Output YAML:
```yaml
claim_id: POLARIS-C3
cited_source_tier: T4
citation_appropriate: yes_partial_or_no
decimals_match_primary: yes_partial_or_no
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
