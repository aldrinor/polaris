## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#396 I-doc-002: blocked-on-user-action tracker doc.

`docs/blocked/blocked_on_user_action_tracker.md`: single comprehensive tracker for 11 GitHub issues blocked on user procurement / hardware / final-phase: I-phase0-003/005/006/007/008/009/010, I-sov-001/002/003/004, I-buf-001, I-hand-001/002/003.

Each section: needed-from-user / already-scaffolded-by-Claude / exit-criteria. Eliminates the need for synthetic placeholder PRs on each blocked issue.

Closes I-doc-002 (#396). Each blocked issue receives a comment pointing to this tracker as the canonical source-of-truth (separate gh issue comment workflow).

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
