# Codex review — I-rdy-002 (#498): Phase 1 gap verification

**Type:** REVIEW of a verification deliverable. Highest-quality standard.

## §0. Cap directive
HARD ITERATION CAP: 5, this is iter 1. Front-load ALL findings now. APPROVE
iff zero P0 and zero P1. "Don't pick bone from egg" — reserve P0/P1 for real
defects in the verification.

## §1. Context
I-rdy-002 (#498) is Phase 1 of the Carney demo execution plan: verify each gap
in `state/carney_readiness_gaps_2026_05_15.md` against the live deployed
system, marking each CONFIRMED-BROKEN vs WORKS-UNTESTED vs PARTIAL.

Deliverable to review: `.codex/I-rdy-002/verification_findings.md`.

## §2. What to verify
1. Are the verdicts accurate? Spot-check the claims against the repo:
   - Auth CONFIRMED-BROKEN — check `web/app/sign-in/page.tsx` (disabled placeholder?) and `web/lib/api.ts` (any `Authorization` header injection?).
   - Worker document_ids CONFIRMED-BROKEN — check `src/polaris_v6/queue/` + `src/polaris_v6/api/runs.py` for `document_ids` handling.
   - cancel/resume PARTIAL — check `src/polaris_v6/queue/actors.py`.
   - F14 memory PARTIAL — check `src/polaris_v6/memory/`.
2. Did the verification MISS any gap from the gap register that should have been checked?
3. Is the "rich-UI gaps need a completed run / test LLM" conclusion sound, or could those have been verified another way?
4. Any verdict that is over- or under-stated.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
verdict_inaccuracies: [...]
gaps_not_verified_that_should_be: [...]
verdict_reasoning: <text>
```
