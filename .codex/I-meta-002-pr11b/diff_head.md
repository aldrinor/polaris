HARD ITERATION CAP: 5 per document. This is iter 1 of the PR-11b DIFF gate.
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
# Codex DIFF-gate — I-meta-002 PR-11b: robust offline e2e proving all 5 benchmark questions route to their native contracts
Operator's "truly robustly test e2e, confirm wired/functional/good to launch" gate. NO SPEND / NO NETWORK.
Verify the diff (scripts/dr_benchmark/offline_e2e.py + tests/dr_benchmark/test_offline_e2e.py):
- The harness parameterizes over all 5 wired benchmark slugs; slug->domain is READ FROM the real
  SWEEP_QUERIES registration (PR-11), NOT a hardcoded map — so the test actually proves the WIRING.
- Per question: load_scope_template(domain)+load_required_entities(template,slug) resolves NON-EMPTY;
  the production M3a builder closure builds the denominator = exactly that slug's contract entity ids
  (right count 75=6/76=5/78=5/72=7/90=6); a separate test asserts the 5 denominators are PAIRWISE
  DISJOINT (no cross-contamination of contracts between questions).
- Full chain offline: 4-role seam (injected FAKE transport) -> manifest four_role_evaluation +
  non-empty evaluator_agrees (VERIFIED->True/FABRICATED->False) + four_role_claim_audit.json; M4 pathB
  PASS on matching served-meta + fail-closed on wrong-model; external scorer -> scored ledger + summary.
- Socket BLOCKED whole run (a real connection fails the test). HELD release per question is correct
  fail-closed under the fake transport (not a bug).
- FROZEN untouched: claim_audit_scorer.py, runtime lock (NOT promoted), the 5 PR-10 contracts.
- Honest scope (confirm acceptable): this is the OFFLINE WIRING proof, NOT the live canary; legs B(M4
  pin)/C(scorer) use shared synthetic data while per-question variation is in routing+denominator.
## SMOKE
