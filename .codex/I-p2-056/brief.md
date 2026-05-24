# Codex brief — I-p2-056 (#859): Plan review page S-audit

HARD ITERATION CAP: 5. iter 1. APPROVE iff the plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context + plan
/plan (cred-gated) is the run-start surface (intake → plan → run); on mount it re-runs the full
intake gate, Start is enabled only for in_scope + disambiguation-resolved. Audited by rendering
locally (seeded session + route-mocked intake fixture). The page was recent (#754) + strong.
Assess-first changes only: (1) shadow-card + rounded-xl on the question + step cards, (2) tone the
4 step icons to muted (brand reserved for the Start button). Preserve the gate flow + testids +
honest framing.

## Note
Already gated downstream: visual `-i` APPROVE iter-1 (A/A/A/A-); code diff APPROVE. This brief
records acceptance for the artifact set.
