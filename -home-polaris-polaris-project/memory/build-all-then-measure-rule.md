---
name: build-all-then-measure-rule
description: "Operator rule: build ALL complementary levers first (each Sol correctness-gated), then run RACE once (3x) — never RACE per single lever"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

For the RACE 4-dimension climb, the operator's STANDING order (given repeatedly, 2026-07-21): **fix EVERYTHING in the plan first, THEN run RACE.** Do NOT run a RACE screen after each individual lever.

**Why (the hard lesson):** the levers are COMPLEMENTARY, not independent. The structure render (L1) exists to UNBLOCK the synthesis tables (L2), which lean on the coverage spine (L3), etc. A single fix measured in isolation gives a near-noise or MISLEADING signal — Sol itself measured L1 alone at only ~0.035 rubric mass and it may even render flat. We already got burned by isolated single-tweak measurements that backfired (marginal-coverage router 0.4738 LOSS; residual-render no-op). A single fix can look like a loss when it is actually a foundation for the others. The only honest measurement is the FULL integrated set scored together (3x for the ceiling), because that is the "max all 4 dimensions together, don't roll one back" goal.

**How to apply:** build each lever via the claude+fork workflow, KEEP the per-lever Sol max-reasoning gate — but that gate is for CORRECTNESS ONLY (byte-identity when off, faithfulness untouched, real bugs like the mid-paragraph-break shift Sol caught in L1), NOT a per-lever score measurement. After ALL levers are built + individually correctness-gated + integrated, run RACE 3x + FACT ONCE on the whole set. If it regresses, THEN bisect.

**Also (behavioral):** when the operator states a decision more than once, COMPLY — do not keep re-litigating it with attribution/discipline arguments. State a disagreement at most once with evidence (two-way iteration), then follow the order. I over-applied one-at-a-time attribution against a twice-given explicit instruction. See [[two-way-iteration-rule]], [[race-scoring-mechanics]], [[investigate-then-consult]].
