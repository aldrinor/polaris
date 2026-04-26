V30 FINAL_PLAN pass-4 final GREEN check — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your pass-3 verdict was STILL-PARTIAL with one remaining edit:

> "relabel or remove the Phase B-local `70-110 eng days = 7-11 weeks`
> line so every occurrence states this is the combined Phase A→B
> bundle, not Phase B alone."

You also confirmed: "new issues introduced: none."

The fix has landed in v3 at line 148 of FINAL_PLAN.md. The line now
reads:

> "Pass-2 ETA (Codex review): 70-110 eng days = 7-11 weeks for the
> combined Phase A → B bundle (NOT Phase B alone) for a small strong
> team. Lower range only feasible if wish #1 stays extremely narrow."

## Your job

Final GREEN check. One question only:

Is the 4th edit landed correctly, and is the plan now GREEN?

If yes: GREEN. Ship as canonical jointly-agreed plan.

If no (vanishingly unlikely after 4 passes): list the remaining issue
plainly.

## Output

Write to `outputs/codex_findings/v30_final_plan_pass4/findings.md`:

```markdown
# Codex pass-4 final sign-off on V30 FINAL_PLAN v3

## Verdict
GREEN / STILL-PARTIAL

## Edit verification
- [x/no] 4th edit (Phase B ETA label) integrated correctly

## Final word
Ship as canonical jointly-agreed plan / one more spin needed.
```

Be terse. Under 50 lines. This is final final sign-off. The user has
been asking for joint-agreement confirmation; if you are GREEN, the
answer to "do Claude and Codex both agree?" is YES.
