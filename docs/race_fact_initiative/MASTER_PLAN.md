# MASTER PLAN — grounded 4-phase RACE + FACT investigation → proven fix map
2026-07-23. Investigation-only until the final action plan is signed off. No pipeline code before then.

## GOAL (end state)
ONE action plan that maps a **true, smart, generalized, small-test-proven** fix to **every single scored
sub-item of RACE and FACT** — every dimension, every sub-criterion, every weight — with each claim grounded
in a specific cited line (code / paper / competitor report), zero guessing, zero overfit / hardcode /
corner-cutting / adjective / sloppiness.

## THE 3-MODEL PANEL (resolved — no Kimi account needed)
| Model | Harness | Access |
|---|---|---|
| Sol   | Codex CLI (`gpt-5.6-sol`, max reasoning)                          | code + shell + web(curl) + goals |
| K3    | Codex CLI → OpenRouter `moonshotai/kimi-k3` (max reasoning) — PROVEN | code + shell + web(curl) + goals |
| Fable | Claude (Agent model:fable)                                        | code + WebSearch/WebFetch |
Opus (me) = orchestrator + final consolidator, using the goal function to re-read every line of all 3.

K3-via-Codex command (verified working):
  codex exec -c model_providers.openrouter.name="OpenRouter" \
    -c model_providers.openrouter.base_url="https://openrouter.ai/api/v1" \
    -c model_providers.openrouter.env_key="OPENROUTER_API_KEY" \
    -c model_provider="openrouter" -c model="moonshotai/kimi-k3" \
    --dangerously-bypass-approvals-and-sandbox "<goal brief>"

## OPERATING MODEL (every phase is one investigation cycle — never a build)
1. **Opus writes the brief**: very in-depth instruction + full background + exact sources to read line-by-line.
2. **3 models investigate INDEPENDENTLY, in goal mode**, each exhausting itself: read every relevant line,
   no guessing, every claim tied to a cited line. Each returns a VERDICT + PLAN.
3. **Opus consolidates**: goal-reads all 3 verdicts line-by-line, rethinks from scratch, reconciles
   disagreements (consulting a model on any judgment call), writes the phase deliverable.
4. **Operator signs off** → next phase. No later phase starts before the earlier one is locked.

## STANDING RULES (enforced every phase, gated in Phase 4)
- Grounded-in-a-cited-line — no guessing, no adjective claims ("it's better") without evidence.
- Generalized only — no overfit, no hardcode, no magic numbers, no task/domain literals, no corner-cutting.
- Faithfulness engine untouchable. No post-generation content edits (pre-generation fixes only).
- Every eventual fix must be proven by a small isolated test with real score evidence.

---

## PHASE 0 — Infra (task #36) — must land first
- Harden the K3-via-Codex retry path (build on tonight's 429 hardening; add OpenRouter provider-fallback so a
  Moonshot throttle blip can't kill a multi-hour goal). This IS the "fix Kimi Retry".
- 30-second goal-mode check that all three (Sol / K3 / Fable) can: search web, read files line-by-line, hold a goal.
- Deliverable: a one-command launcher per model + confirmation all three are live. NO pipeline code.

## PHASE 1 — Master the scoring (task #37) → SCORING_SPEC.md
Line-by-line over the ENTIRE RACE + FACT systems:
- Sources: third_party/deep_research_bench (criteria_prompt_en.py, clean_prompt.py, extract.py,
  deepresearch_bench_race.py + the FACT scorer, criteria.jsonl for ALL tasks, prompt_data), the paper
  (arXiv 2506.11763), deepresearch-bench.github.io, the HF leaderboard.
- Output: the definitive map of exactly what earns/loses every fraction of a point — all 4 RACE dimensions
  (Comprehensiveness, Insight, Instruction-Following, Readability) with every sub-criterion + weight + the
  dynamic-weighting rules + what the judge actually sees (post-cleaning) + the full FACT citation metric.
- 3 models (goals) → Opus consolidates → SCORING_SPEC.md.

## PHASE 2 — Teardown the top 10 (task #38) → COMPETITOR_TEARDOWN.md
Line-by-line on the top ~10 runners:
- Sources: each system's papers/tech-reports/blogs, and every available REPORT SAMPLE (fetch actual outputs
  for task-72 + peers from the DeepResearch-Bench HF dataset/repo), the leaderboard.
- Output: per-system architecture + what they do right for EACH RACE+FACT sub-item from Phase 1, the concrete
  structure of high-scoring reports, and the recurring cross-system patterns.
- 3 models (goals) → Opus consolidates → COMPETITOR_TEARDOWN.md.

## PHASE 3 — Audit our pipeline (task #39; needs 1+2) → PIPELINE_GAP_AUDIT.md
With Phase 1 (what's scored) + Phase 2 (what winners do), review EVERY section/line of our pipeline
(compose driver, agentic outliner, writer prompts, render, retrieval, scope contract, faithfulness/FACT path)
against each sub-item:
- For each gap: the specific sub-criterion we lose, the evidence (our per-dim scores + report samples), the
  true/smart/GENERALIZED fix (pre-gen, no post-gen, no hardcode), and a small isolated TEST that proves the
  fix contributes score with real evidence (not guessing).
- 3 models (goals) → Opus consolidates → PIPELINE_GAP_AUDIT.md. Design only, NO code changes.

## PHASE 4 — Gate + consolidate (task #40; needs 3) → EXECUTION_CHARTER.md + MASTER_ACTION_PLAN.md
- Define the gating discipline that guarantees generalization with zero overfit/hardcode/corner-cutting, and
  how we stay on it during execution (grounding requirement, small-test-evidence requirement, faithfulness
  untouchable, no-post-gen, Sol/Fable/K3 cross-gate on every fix).
- 3 models (goals) → Opus consolidates → EXECUTION_CHARTER.md.
- Then Opus fuses Phases 1-4 into MASTER_ACTION_PLAN.md: a proven, generalized, tested fix mapped to EACH
  RACE+FACT sub-item, ordered for execution. THIS is the sign-off gate before any build.

---

## DELIVERABLES
Phase 0: launcher + live check · Phase 1: SCORING_SPEC.md · Phase 2: COMPETITOR_TEARDOWN.md ·
Phase 3: PIPELINE_GAP_AUDIT.md · Phase 4: EXECUTION_CHARTER.md + MASTER_ACTION_PLAN.md.

## AFTER APPROVAL (not part of this plan yet)
Execution phase: build each fix behind a flag, small-test it (evidence of score contribution), Sol/Fable/K3
cross-gate, then RACE/FACT re-measure with a same-judge baseline + enough draws to clear the ±0.027 noise.

## KNOWN CONTEXT CARRIED IN (from tonight, all grounded)
- RACE ≈ Insight .32 + Comprehensiveness .29 + IF .25 + Readability .14 (task-72; weights are dynamic/per-task).
- RACE strips citations before judging (clean_prompt.py) → FACT ≠ RACE; faithfulness buys 0 RACE points.
- Judge drift tonight (~-0.036) → only within-judge comparisons valid; historical/leaderboard numbers not comparable.
- Compose-side levers measured FLAT (3 arms indistinguishable). Insight is the leader gap; it lives in the
  writer's reasoning + pre-gen structuring, NOT post-hoc passes (proven to regress) — to be re-verified in Phase 3.
