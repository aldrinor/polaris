# Effective two-way iteration with the gater models (Sol / codex + K3)

The claude-codex-K3 workflow is **NOT one-directional** (they gate, Opus obeys). It is a genuine
**two-way, evidence-based iteration**. A gate REJECT is a *claim to be verified*, not an order; Opus's
own position is also a claim to be tested. Decisions are made on **evidence, not authority**.

## The loop
1. Opus implements + tests.
2. Sol (codex) and K3 gate / review.
3. When Opus **disagrees** with a verdict, has a **concern**, or the gate hits a **judgment call / diminishing
   returns**: Opus does NOT silently obey, and does NOT silently overrule. Opus **passes its reasoning back to
   the gater as a CONSULTATION** (explicitly not a pass/fail gate), states its point plainly, and asks the
   model to:
   - deeply weigh the **pros and cons**,
   - **VERIFY the facts with EVIDENCE** — run small tests / simulations / greps on the actual code and
     artifacts, and **quote the command outputs**, not opinions,
   - propose the best path (confirm, refute, or a cleaner alternative).
4. Converge on the evidence-based truth; bring the evidence (and where the models agree/differ) to the operator.

## How to apply — every time
- **Frame it as a CONSULTATION, not a gate,** so the model weighs pros/cons instead of just pass/fail.
- **Lead with your own position and reasoning,** and invite the model to challenge or confirm it.
- **Require evidence:** name the specific checks/tests/simulations to run; demand quoted outputs.
- **Distinguish "technically correct per spec" from "reachable in our data"** — verify reachability with a
  real test (e.g. grep the actual report), don't assume.
- **A REJECT is not the end of the conversation.** If it's technically-correct-but-unreachable, or a
  judgment call, say so and consult — don't grind blindly or cave blindly.
- **Bring data to the operator** and make the call together.

This is what the govkit exists for: smooth, evidence-based communication among Opus, Sol, and K3 — not blind
obedience in either direction. Companion rule: `background_task_discipline.md`.
