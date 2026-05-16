# Codex review iter 3 — I-rdy-002 (#498): Phase 1 gap verification

**Type:** REVIEW, iter 3 of 5. iter1/iter2 = REQUEST_CHANGES (incomplete register coverage). Now every gap-register row has a status.

## §0. Cap directive: front-load all findings. APPROVE iff zero P0 and zero P1.

## §1. iter-2 residual findings, all addressed in `.codex/I-rdy-002/verification_findings.md`
Added rows for the previously-omitted register items:
- P0 Canadian GPU acquisition + dress rehearsal → row added, status BLOCKED-external (not securable by Claude; Vexxhost/ISAIC outreach sent; decision gate 2026-05-24).
- F13 pin replay → row added, status CONFIRMED demo-data-bound (`web/app/pin_replay/` uses DEMO_PIN_REGISTRY).
- P1: 22-type product test matrix (NOT DONE), sovereignty/log-redaction call-site proof (NOT VERIFIED), UI hardening states (NOT VERIFIED), demo logistics/fallback/legal notice (NOT STARTED) → rows added.
- Conclusion rewritten to assert full register coverage with the status breakdown.

## §2. Verify `.codex/I-rdy-002/verification_findings.md`
1. Every P0/P1/P2 row in `state/carney_readiness_gaps_2026_05_15.md` now has a status in the doc.
2. Statuses are accurate.
3. No remaining omission.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
full_register_coverage: yes | no
residual: [...]
verdict_reasoning: <text>
```
