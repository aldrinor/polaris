HARD ITERATION CAP: 5 per document. This is iter 1 of the PR-11 DIFF gate.
- APPROVE iff zero P0 and zero P1.
## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
# Codex DIFF-gate — I-meta-002 PR-11 (#937): wire 5 benchmark questions runtime routing to native contracts
You APPROVED the brief. NO SPEND / NO NETWORK. Verify the diff:
- drb_72_ai_labor domain "custom" -> "workforce" (only the domain key + comment; question text/amplified set untouched).
- 4 new SWEEP_QUERIES entries (drb_75/76/78 -> clinical, drb_90 -> policy): slug EXACTLY equals the frozen
  per_query_report_contract key; LOCKED question text verbatim; NO amplified/seed field (no-network registration stubs).
- The new test asserts per-slug: SWEEP_QUERIES entry+domain, and load_scope_template(domain)+load_required_entities(
  template,slug) resolves NON-EMPTY (contract reachable at runtime), AND a wrong slug fails closed (raises).
- FROZEN PR-10 contracts untouched (no per_query_report_contract content change); claim_audit_scorer.py + runtime lock untouched (lock NOT promoted).
- Confirm: no field in the 4 new entries triggers a live fetch/spend at import/registration; a routing typo fail-closes (cannot silently skip the 4-role gate).
## SMOKE
