# 0025. Autonomous execution discipline: no self-initiated stops, quota-aware model tiering

Status: accepted

Date: 2026-07-05

## Context

Two recurring failures. First, the executor kept pausing the autonomous queue on its own — "natural cadence checkpoint", "X PRs landed", "good place to check in", "clean resource state" — none of which are halt conditions. The operator flagged this 3+ times ("you always said you continue, but you always stop"), and promising harder never fixed it. Second, asking for permission the operator already granted wastes their time ("you scam me, you play me"). Third, overnight runs burn the binding weekly all-models quota if the wrong model does the grunt work.

## Decision

Once the operator has authorized, execute. Do not ask permission again. Do not decide when to pause — stops are ONLY for a reviewer REQUEST_CHANGES at the 5-cap (force-approve then proceed), a documented halt condition, or the operator explicitly typing stop. The only things that reach the operator mid-run are a genuine blocker that is truly theirs, a root-cause-proven finding, or the final scored results.

For overnight autonomous runs, tier the models by cost: Fable (a separate quota bucket) does the BRAIN work — think, design, root-cause, gate — in few high-value calls. Cheap HANDS do the grunt: Sonnet for build/test/read, Haiku for trivial. Never default the workflow hands to Opus 4.8, which burns the binding weekly bucket. Keep the main-loop footprint small: tight messages, delegated reads, and reaction to free workflow-completion notifications instead of a per-tick polling watcher. Do not wake the operator — spin up a Fable agent to root-cause and decide, build it, continue.

## Consequences

- Self-initiated cadence pauses are the executor claiming a decision that belongs to the reviewer or a halt condition. The fix is structural: the immediate next action after a merge is creating the next branch, with zero backward-looking prose in between.
- Self-check before yielding the turn: am I stopping because a reviewer, a halt condition, or the operator told me to, or because I project the operator "would want a checkpoint"? If the latter, that is the bug — keep executing.
- Quota is the binding overnight constraint, so the model tier must match the task value; running Opus on grunt work is the waste this rule prevents.
- Pace toward the highest-leverage piece; do not spend quota composing on not-yet-best inputs, because a better upstream output will flow down and require a re-compose anyway.
- The only durable overnight trail is git commits, box docs, and memories — not a live panel the operator cannot read.
