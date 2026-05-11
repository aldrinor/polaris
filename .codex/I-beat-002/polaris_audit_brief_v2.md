# Codex audit: POLARIS tirzepatide-T2DM line-by-line

Read `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/report.md` body sections (### Efficacy, ### Safety, ### Comparative, ### Mechanism, ### Regulatory, ### Limitations after `## Analyst Synthesis`). SKIP Analyst Synthesis + Methods + Bibliography + V30 sections.

For EACH body sentence with `[N]` markers, check:
1. Is the cited [N] source appropriate tier for the claim type (T1 for trial decimals, SR for pooled estimates)?
2. Do decimals in the sentence match what the cited source publishes?
3. Is the reasoning sound (does claim follow from cited evidence)?

Output ONLY YAML, no prose:

```yaml
verdict: APPROVE | REQUEST_CHANGES
summary:
  total_claims: <N>
  verified: <N>
  partial: <N>
  fabricated: <N>
  unreachable: <N>
fabricated_claims:
  - text: "..."
    cited: [N]
    reason: "..."
top_findings:
  - "..."
```

APPROVE iff 0 fabricated + 0 unreachable.

Bibliography is at `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/bibliography.json` (10 sources).
