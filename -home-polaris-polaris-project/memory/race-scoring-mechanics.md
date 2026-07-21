---
name: race-scoring-mechanics
description: "How DeepResearch Bench RACE actually scores (comparative, prose-only, per-task weights) + the consolidated 4-dim action plan"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-21 — 3-model audit (Sol max + Fable + K3) of the k3_b1_run champion (RACE 0.5084). All verified in third_party/deep_research_bench.**

**How RACE scores (load-bearing, corrected an earlier mistaken plan):**
1. COMPARATIVE, not absolute: dim score = target/(target+reference) (deepresearch_bench_race.py:155). We lose where the fixed reference report beats us.
2. The judge reads BODY PROSE ONLY. A cleaner (prompt/clean_prompt.py, utils/clean_article.py) DELETES the entire reference list and every inline [N] marker BEFORE judging (verified on cleaned artifact k3b1race_r1.jsonl: zero markers, refs gone, paragraphs preserved). => **Editing the bibliography is ~ZERO for RACE — it only helps the separate FACT score.** Fable's "drop 41 orphan refs" free win was a mirage FOR RACE. The IF fix must be UPSTREAM (evidence->prose), because the judge sees words like "the working-paper version..." (report.md:19) and "only 4% of sources are T1" (report.md:39).
3. Dimension weights are JUDGE-ASSIGNED PER TASK (data/criteria_data/criteria.jsonl id 72): **Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14.** Readability is our lowest SCORE (0.457) but LOWEST WEIGHT — it must rise as a co-benefit, never the primary target (that's the operator's roll-back trap, literally the weight math).

**Rubric mass reachable per joint lever:** cross-study/cross-industry synthesis 0.190 (all 4 dims) > coverage spine (4IR+scope+AI/GenAI) 0.115 > upstream journal-source routing 0.106 > paragraph/formatting render 0.035.

**Consolidated 6-step plan (committed: docs/race_4dim_action_plan.md, commit b294cb89 on branch fix/race-batch1-evidence-substrate, GitHub aldrinor/deep-cove-research):** 1 structure-preserving render (safe enabler, flag PG_RENDER_BLOCKS) -> 2 typed cross-study comparison tables (biggest lever, reuse verified-prose table gen multi_section_generator.py:7170, reuse-[N]-only :3524) -> 3 coverage spine (clause ledger planning/clause_ledger.py:487) -> 4 upstream journal/English routing+backfill (HARDEST; re-extract+re-verify, citation_reanchor.py:90 needs literal-span, "primary" admits preprints; no-rollback-or-dont-ship) -> 5 cross-section consolidation (PG_ANTI_RESTATEMENT skipped under strict-off, multi_section_generator.py:11594) -> 6 limitations register + bibliography (biblio=FACT only). Order disagreement: Sol wants #4 first (rubric-mass); I sequence it after #2 (bigger + safer). Each central-config-gated default-off, Sol-max gated, 3x RACE A/B (judge noise ~+-0.007, IF ranged 0.4943-0.5079 across champion draws), faithfulness untouched.

**Verified gaps:** every section = one <=1214w paragraph (0 tables/bullets/bold; flatten at provenance_generator.py:5121, whitespace collapse :715); "4IR" 4x intro/0x elsewhere; industries named but never compared; corpus_rq="Generative AI" but task="AI" broadly (over-centers LLM evidence); one Arabic citation, language metadata fails-open.

**RACE render seam gotcha:** PG_SECTION_STRUCTURE (writer-side ###/table variant, multi_section_generator.py:3855) exists but conflicts with base/retry/user prompts that still demand a single paragraph — do NOT enable it alone (ships worse). Lever 1 uses a paragraphs-ONLY rule-7 variant instead. See [[race-climb-ladder-and-architecture]], [[k3-generator-race-win]].
