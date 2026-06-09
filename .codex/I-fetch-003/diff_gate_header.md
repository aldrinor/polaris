HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output the §8.3.9 schema and a FINAL single line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Diff review I-fetch-003 (#1175): fetch-starvation fix, BRIEF APPROVED iter-3. VERIFY adversarially (retrieval throughput only — faithfulness gates untouched): (1) deadline is START-anchored + MONOTONIC; not-yet-started never TIMEOUT; harvest wait ALWAYS bounded (never timeout=None); a task is TIMEOUT iff IT exceeded its own budget. (2) round-robin submit-by-backend defeats worker-slot hoarding; result indexing maps back to the ORIGINAL index correctly. (3) backend_id=host gives per-host semaphores; per-host limit + max_workers env-overridable + named constants, no magic numbers. (4) new diag fields do NOT widen api_calls dict; existing parallel_fetch_* fields unchanged. (5) fail-closed + no faithfulness weakening. (6) the offline tests genuinely exercise the slow-sibling, own-budget-timeout, cross-host-concurrency, AND adversarial same-host-prefix-hoarding cases (not tautological). Output the §8.3.9 schema + a final 'verdict:' line.
