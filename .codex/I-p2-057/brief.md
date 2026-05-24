# Codex brief — I-p2-057 (#861): Run progress page S-audit

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
/runs/[runId] (cred-gated) is the live-run surface (final leg of Plan→Run→Compare). Audited by
rendering locally (seeded session + a mocked EventSource emitting canned SSE events + route-mocked
getRun). The run_progress component was already exemplary. Assess-first changes: (1) done stage
chip + retrieval ✓ brand-red → --verified green; (2) shadow-card + rounded-xl on stage/counter/
actions cards; (3) actions-card heading off jargon + branched by verdict, gating the "verified
result" copy + follow-up panel on pipeline_status (not lifecycle 'completed', which abort_* runs
also have — §9.1). Preserve the stage-state machine + SSE flow + testids.

## Note
Already gated downstream: visual `-i` APPROVE iter-2 (all states A); code diff APPROVE iter-4 (the
pipeline-status honesty fix landed). This brief records acceptance for the artifact set.
