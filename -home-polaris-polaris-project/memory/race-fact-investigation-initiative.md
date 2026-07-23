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

**STATUS 2026-07-23: ALL 4 PHASES COMPLETE** (panel = Sol + Fable; K3 dropped, Moonshot 429-throttled).
Deliverables committed+pushed in docs/race_fact_initiative/ (commit 155e60c0): SCORING_SPEC.md,
COMPETITOR_TEARDOWN.md, PIPELINE_GAP_AUDIT.md (14 unified gaps U1-U14), **MASTER_ACTION_PLAN.md** + all
raw phase1-4 sol/fable verdicts. Every receipt was verified against ground truth each phase.

**The plan both models converged on:** ONE pre-generation `AnalyticalContract` (AC) — built from question +
admitted evidence, consumed by the ACTIVE producer `_compose_section_per_basket` (NOT `_call_section`, the else
branch — a prompt addendum routed only there misses the producer = the proven cause of the measured-flat levers),
audited SEMANTICALLY (proposition entails obligation, NOT section-nonempty; and NOT an NLI model — R2 bans new
entailment machinery per [[no-entailment-ever-rule]]). Champion = mf_baseline 0.5009 (all levers OFF but
PG_RENDER_BLOCKS), the ONLY valid comparator. Critical path U3→U4/U6→U7. 5-rule charter (generalization gate w/
held-out tasks 91+100+{73|51|4}; faithfulness firewall + U1 zero-new-factual-token canary + layout-only render
exception; deterministic-then-3v3-paired measurement gate; shared-contract rule; no-regression gate).

**THE OPEN DECISION for the operator (OQ-0, blocks build):** first-ship wave. Fable (Opus-recommended) =
proven-winner-first, W1 = U1 licensed paragraph-closing inference + U12-lite layout + U14b, AC carrier as
definition-of-done. Sol = governance-foundation-first, W1 = U5+U11+U13+U12. Both reach the same end state; they
differ on sequence. Plus OQ-1 (held-out set), OQ-4 (licensed-inference doctrine sign-off), OQ-5 (probe budget)
also block Wave 1. AWAITING operator sign-off before ANY pipeline code. See [[no-post-generation-fix-rule]],
[[build-all-then-measure-rule]], [[investigate-then-consult]].

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

**INGESTION PROTOCOL (mandatory, every phase, both Sol+Fable):** before each phase, each investigator must
read EVERY line of EVERY prior-phase artifact (each phase's consolidated plan + Sol verdict + Fable verdict,
in docs/race_fact_initiative/) and emit an INGESTION RECEIPT at the top of its verdict — per file: line count +
verbatim FIRST/MID/LAST line. Opus VERIFIES each receipt against the real files; mismatch/missing => reject +
re-run. No skimming. Also: Opus's own consolidation must be LOSSLESS (read every line of both verdicts, preserve
every point, [S]/[F] attributed) — the operator caught Opus compressing/skipping Fable twice; that is the failure
mode to avoid. Snippet at scratchpad/investigators/INGESTION_PROTOCOL.md, prepended to every phase brief.
