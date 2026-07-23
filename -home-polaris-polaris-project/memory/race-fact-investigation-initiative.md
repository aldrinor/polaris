---
name: race-fact-investigation-initiative
description: 4-phase grounded 3-model investigation to map proven fixes to every RACE+FACT sub-item; key findings + the codex-drives-kimi rig
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Initiative (2026-07-23): a **grounded, line-by-line, no-guessing** 4-phase investigation to map a
true/generalized/small-test-proven fix to **every scored sub-item of RACE and FACT**. Plan + docs live in
repo `docs/race_fact_initiative/` (branch `fix/race-batch1-evidence-substrate`). Tasks #36-#40.

**Operating model** — each phase = one cycle: Opus writes a deep brief → **3 models investigate
independently in GOAL mode** (max reasoning, web+code, every claim tied to a cited line) → each returns a
verdict+plan → **Opus consolidates** (re-reads all 3 line-by-line) → operator signs off → next phase.
Phases: P0 infra → P1 SCORING_SPEC (RACE+FACT line-by-line) → P2 COMPETITOR_TEARDOWN (top-10) →
P3 PIPELINE_GAP_AUDIT (our gaps+fix+test) → P4 EXECUTION_CHARTER + MASTER_ACTION_PLAN (sign-off gate). NO
pipeline code until MASTER_ACTION_PLAN approved.

**The 3-model panel (no Kimi account needed):** Sol = Codex CLI (gpt-5.6-sol, max). K3 = **Codex CLI driving
OpenRouter `moonshotai/kimi-k3`** — PROVEN working: `codex exec -c model_providers.openrouter.base_url=
"https://openrouter.ai/api/v1" -c model_providers.openrouter.env_key=OPENROUTER_API_KEY -c
model_provider=openrouter -c model=moonshotai/kimi-k3`. Fable = Claude Agent(model:fable). Opus consolidates.
Codex goals feature is live (~/.codex/goals_1.sqlite). "Fix Kimi Retry" = harden that codex-drives-k3 path.

**Grounded findings so far (to re-verify in the phases):**
- RACE ≈ Insight .32 / Comprehensiveness .29 / IF .25 / Readability .14 (task-72; weights are DYNAMIC per task).
- RACE **strips citations before judging** (clean_prompt.py) → FACT ≠ RACE; ~90% faithfulness buys 0 RACE points. See [[no-post-generation-fix-rule]].
- Compose-side levers measured FLAT: 3 arms indistinguishable (max 0.4933 / full 0.4966 / baseline 0.5009, all within ±0.014 noise, tonight's judge). The gap to leaders (~0.58) is **Insight**, which lives in the writer's reasoning + pre-gen structuring — NOT post-hoc passes (proven to regress 16-27%).
- **Judge drift**: tonight's gpt-5.5 judge scored a stored champion report 0.4718 (vs ~0.508 historical) → only WITHIN-judge comparisons valid; leaderboard/historical numbers NOT comparable; "beat everyone" not defensible tonight.
- Readability decomposes into 7 sub-criteria (task-72 criteria.jsonl): L1 prose .2, S1 structure/roadmap .2, S2 paragraph cohesion .15, P1 synthesis clarity .15, D1 data-as-tables .1, F1 formatting .1, A1 term-defs .1. Tables/formatting = only D1+F1 = 20%; our reports have 615-word wall-of-text paragraphs (worst loss) + no tables + weak roadmap.
- RACE noise floor: ±0.027 draw-to-draw on Readability; baseline_triple says gain is real only if replicated mean clears ~+0.014. Fix the measurement harness to always run a same-judge baseline + enough draws.
