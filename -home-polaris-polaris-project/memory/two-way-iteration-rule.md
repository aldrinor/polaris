---
name: two-way-iteration-rule
description: "Standing rule — the claude-codex-K3 loop is bidirectional; consult with evidence, never gate->obey or silently overrule"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**Standing rule (operator, 2026-07-20): the claude-codex-K3 workflow is a genuine TWO-WAY, evidence-based iteration — not gate->obey.** A gate REJECT is a claim to VERIFY, not an order; my own position is also a claim to test. Decide on **evidence, not authority**.

**Why:** during Step-1 the operator saw me on the verge of unilaterally accepting/deferring based on my own read of Sol's rejections. The infra exists for smooth two-way communication — when I disagree or hit a judgment call, I must engage the models, not obey or overrule them silently.

**How to apply — every time I disagree with a gater, have a concern, or hit diminishing returns:**
1. Pass my reasoning/position back to the model as a **CONSULTATION (explicitly not a pass/fail gate)** so it weighs pros/cons.
2. Lead with my position; invite it to challenge or confirm.
3. **Require EVIDENCE:** name the exact checks/tests/simulations to run; demand quoted command outputs, not opinions.
4. Distinguish **"technically correct per spec" vs "reachable in our data"** — verify reachability with a real test (e.g. grep the actual report), don't assume.
5. Bring the evidence (and where the models agree/differ) to the operator; make the call together with data.

Codified in `gov/agent_iteration_protocol.md` (committed f5f0b1b, gate-inversion) + `~/.govkit/gov/`. Companion: [[background-task-lifecycle-rule]], [[governance-kit-operating-rule]], [[codex-sol-max-reasoning]].
