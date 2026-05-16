# Codex review iter 4 — I-rdy-002 (#498): Phase 1 gap verification

**Type:** REVIEW, iter 4 of 5. iter3 = REQUEST_CHANGES (1 P1: 2 P2 register rows missing).

## §0. Cap directive: front-load. APPROVE iff zero P0 and zero P1.

## §1. iter-3 residual addressed in `.codex/I-rdy-002/verification_findings.md`
Added the 2 missing P2 register rows:
- "(P2) Visual design system + route consistency" → NOT STARTED.
- "(P2) Scaffold / demo-data copy on user-visible pages" → CONFIRMED PRESENT (sign-in "Phase 0 scaffold", pin_replay DEMO_PIN_REGISTRY).
Every P0/P1/P2 row in `state/carney_readiness_gaps_2026_05_15.md` now has an explicit status row.

## §2. Verify: every register row has a status; statuses accurate; no remaining omission.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
full_register_coverage: yes | no
residual: [...]
verdict_reasoning: <text>
```
