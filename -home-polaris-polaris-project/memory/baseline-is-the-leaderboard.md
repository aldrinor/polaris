---
name: baseline-is-the-leaderboard
description: "Never re-measure our own low score as a \"baseline\"; the comparison point is the benchmark TOP SCORER; improve→run→score→compare-to-leaders→climb"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Operator rule (2026-07-24, sharp correction after a wasted day). **NEVER establish/re-measure "our own baseline"
as a measurement anchor.** Knowing our own low score (~0.50) creates ZERO value — we already know we're behind.

**Why:** the goal is to keep IMPROVING and keep SCORING, higher and higher, until we beat the benchmark's TOP
SCORERS. RACE is already comparative (target/(target+ref) vs the frozen Gemini reference), so our absolute number
is directly comparable to the leaderboard leaders. The baseline/target IS the top scorer (Phase-2 COMPETITOR_TEARDOWN:
Qianfan ~0.61, cellcog ~0.57, the legacy leaders ≥0.58), NOT our own past low score.

**How to apply:** the loop is **improve → run → score → compare to the TOP SCORERS → improve more → climb.**
- Do NOT build a "levers-off baseline" or run per-lever paired 3v3 against our own number (that contradicts
  [[build-all-then-measure-rule]] AND wastes runs). Build the best config, run it, score it, compare to the leaders.
- The first improvement to ship is the proven generator lever: Kimi-K3 (+0.030, [[k3-generator-race-win]]) — NOT
  GLM-5.2 (run_gate_b defaults to glm-5.2; MUST set PG_GENERATOR_MODEL=moonshotai/kimi-k3 + the run_k3.sh routing).
- Then layer the clean levers (MASTER_ACTION_PLAN_V2_CLEAN KEEP set) and keep re-running + scoring to climb.
- What DID carry from the Stage-0 day: the lineage seam (needed so a Gate-B/V30 run answers task-72 for ANY scoring)
  + the clean no-ghost plan + [[ghost-ban-operating-guard]]. What we STOP: self-baselining ceremony.

The mistake origin: the Phase-4 "measurement gate" (Sol+Fable + Opus consolidation) encoded per-lever paired-vs-our-
baseline measurement; Opus over-invested it into a full day of Stage-0 re-baseline infra. Operator caught it: use the
LEADERBOARD as the bar, not ourselves.
