## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

**GH#196 — I-tpl-006: AI sovereignty scope template.**

New `config/scope_templates/ai_sovereignty.yaml`. Mirrors structure of `policy.yaml` (existing template) — domain, inclusion/exclusion criteria, expected_tier_distribution. Domain-specific content: national AI strategies, regulatory documents (EU AI Act / NIST AI RMF / Canada AIDA), export controls, data-residency, sovereign-cloud frameworks. Required jurisdictions: CA, US, EU, UK. Audit emphasis: per-claim regulatory citation, vendor-claim separation per CLAUDE.md §-1.1.

Net: +~85 lines, single config file. No code change. No tests required (YAML schema validation occurs at corpus-adequacy gate at runtime).

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
