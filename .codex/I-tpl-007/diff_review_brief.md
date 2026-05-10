## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#197 I-tpl-007: Canada-US scope template.

config/scope_templates/canada_us.yaml — 7 inclusion criteria + 4 exclusion + 6 tier-distribution entries (vendor=T5 per global taxonomy). Required jurisdictions: CA, US. Audit emphasis: per-jurisdiction badge + government source pin per sentence per CLAUDE.md §-1.1.

scope_gate.SUPPORTED_DOMAINS adds canada_us. workforce lands with I-tpl-008 next.

YAML safe_load OK.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
