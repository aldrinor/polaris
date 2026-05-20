# Codex diff — I-cd-031 (#621) — demo journey

Canonical-diff-sha256: `f3bdd982a31c551f5f3a04cfee8c674429e0567b7eee2d1c9fadce01588fbb82`.

## Diff summary
- `web/tests/e2e/demo_journey.spec.ts` NEW — 2 tests:
  - End-to-end: home click clinical card → /intake?template=clinical → /dashboard → /inspector/v1-canonical-success → asserts inspector view + family-segregation copy.
  - Cross-route nav parity: header count + Primary nav links on each of the 4 journey routes.
- `web_ci.yml` binding step.

The "run" middle of the journey (Dashboard submit → real pipeline-A run → /runs/[runId] → /inspector/[runId]) is hardware-bound (sovereign GPU); the journey pivots at /dashboard to the canonical fixture which IS the frozen I-A-02b acceptance contract.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
