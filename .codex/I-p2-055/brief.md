# Codex brief — I-p2-055 (#857): Source Review page S-audit

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
/source_review (cred-gated) sits between Intake and Plan; live it 401-redirects without a real JWT.
Audited by rendering locally (seeded session + route-mocked /templates fixture). This was already
the strongest cred-gated page (state-kit states, tier-token dots, exemplary honest framing — shows
the source-set DEFINITION + adequacy bar, NOT a fabricated corpus). Assess-first changes only:
(1) brand-tinted shadow-card + rounded-xl on the question/tier/"how-sources" cards (were flat),
(2) a "Try again" retry on the ErrorState. Preserve the listTemplates fetch, the allow-list, the
honest framing, and the testid.

## Note
Already gated downstream: visual `-i` APPROVE iter-2 (S- / A++ / A+); code diff APPROVE. This brief
records acceptance for the artifact set.
