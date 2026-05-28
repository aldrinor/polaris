# Competitor DR outputs — storage manifest (I-safety-002b / #925)

**Received** 2026-05-28 from operator. Two frontier DR systems, full/max power, on the 5 LOCKED
golden DRB-EN questions (#75/#76/#78/#72/#90). Raw files stored on disk under
`outputs/dr_benchmark/external_outputs/<system>/Q##_<slug>.md` (outputs/ is gitignored — durable on
this machine + the VM; hashes below make the audit reproducible). Frozen answer key:
`gold_rubrics_pathB.md` (freeze_pin.txt). **Stored BEFORE viewing did NOT happen for the rubric —
the rubric was frozen first, so pre-registration holds; these outputs are now fair to audit.**

## System attribution (evidence-based)
- **GPT 5.5 Pro Extended Thinking DR** = the generic `deep-research-report*.md` exports. Evidence:
  OpenAI's `citeturn<n>search<m>` / `turn<n>view<m>` inline citation markers throughout.
- **Gemini 3.1 Pro DR** = the descriptively-titled files. Evidence: descriptive report titles +
  numbered/superscript citation style (no `citeturn` markers).

## Mapping + integrity (SHA256 prefix, word count)
| Question | System | stored path | words | sha256[:16] |
|----------|--------|-------------|-------|-------------|
| #75 metal ions/CVD | GPT 5.5 Pro | gpt_5_5_pro/Q75_metal_ions_cvd.md | 5334 | 7600287463CCA640 |
| #76 gut microbiota | GPT 5.5 Pro | gpt_5_5_pro/Q76_gut_microbiota.md | 4902 | 180EEB12CF03BADF |
| #78 parkinsons/DBS | GPT 5.5 Pro | gpt_5_5_pro/Q78_parkinsons_dbs.md | 4221 | F88B8855A57B0D6D |
| #72 AI labor | GPT 5.5 Pro | gpt_5_5_pro/Q72_ai_labor.md | 4775 | 09B2471244D18EBB |
| #90 ADAS liability | GPT 5.5 Pro | gpt_5_5_pro/Q90_adas_liability.md | 5750 | A76950A96DC1BDA6 |
| #75 metal ions/CVD | Gemini 3.1 Pro | gemini_3_1_pro/Q75_metal_ions_cvd.md | 8621 | B441495DDD84014E |
| #76 gut microbiota | Gemini 3.1 Pro | gemini_3_1_pro/Q76_gut_microbiota.md | 8059 | 7053A036E6823539 |
| #78 parkinsons/DBS | Gemini 3.1 Pro | gemini_3_1_pro/Q78_parkinsons_dbs.md | 6253 | 94E126BD377E973D |
| #72 AI labor | Gemini 3.1 Pro | gemini_3_1_pro/Q72_ai_labor.md | 7957 | 740CDDA30B9ACB27 |
| #90 ADAS liability | Gemini 3.1 Pro | gemini_3_1_pro/Q90_adas_liability.md | 6635 | 80D4F606998CCF72 |

## Scoring discipline (binding, §-1.1)
- Length is NOT quality. Gemini ~+60% words vs GPT — irrelevant to the verdict. Score per-claim
  faithfulness (claim → fetched cited source → VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE)
  + pre-registered gold-rubric coverage (≥0.70). Identical scoring for POLARIS, GPT, Gemini.
- Report clinical-3 (#75/#76/#78) and overall-5 SEPARATELY. Honest label per golden_questions_locked.md.
- Dual audit: Claude arm + Codex arm independently, reconciled. Cap 5 Codex iters/document.

## STATUS — what exists vs what's pending
- **Competitor side: RECEIVED + stored (10/10).** Ready for §-1.1 audit.
- **POLARIS side: NOT YET RUN on these 5 questions.** The repo's existing honest_sweep outputs are the
  OLD homegrown questions, not the golden 5. POLARIS must run them at FULL POWER through the
  pathB_run_gate. Blocked on: gate-wiring (PR-1 in Codex diff audit; PR-2 runner lifecycle; PR-3
  scoring) → then the operator-authorized full-power runs.
- **Side-by-side requires the POLARIS side.** Until POLARIS output exists, the competitor §-1.1 audit
  can proceed (Claude arm), but the head-to-head verdict cannot be finalized.

## FULL/MAX POWER mandate (operator 2026-05-28) — POLARIS run config
When POLARIS runs, search + fetch + tools + OpenRouter must be FULL/MAX power (no half-measures, no
silent degradation). The pathB_run_gate ENFORCES this; the runner sets:
- PG_SWEEP_MAX_SERPER=50, PG_SWEEP_MAX_S2=50, PG_SWEEP_FETCH_CAP=500, PG_LIVE_MAX_EV_TO_GEN=300
- PG_V30_ENABLED=1, PG_V30_PHASE2_ENABLED=1, PG_MAX_COST_PER_RUN=40
- OPENROUTER_ALLOW_FALLBACKS=false (gate: fatal if true) + OPENROUTER_PROVIDER_ORDER singleton
- generator deepseek/deepseek-v4-pro, evaluator google/gemma-4-31b-it (two-family)
- retrieval reachability enforced at preflight (serper + semantic_scholar live ping); assert_post_run
  confirms both backends were ACTUALLY attempted (no half-ass "key present but never called").
