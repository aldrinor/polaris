# Competitive study — why the DeepResearch-Bench leaders beat us, and what to actually do
Consolidated from two independent web-research studies + tonight's measurement. 2026-07-23.
Leader teardown artifact: https://claude.ai/code/artifact/9c5f1600-733e-4cae-b51b-4cbd4b1b20f3

## The one-sentence answer
We are NOT rubbish — we lose on a SINGLE axis, **Insight**, and we lose it because our writer
**summarizes evidence instead of reasoning over it**. Everything else (citations, readability,
search volume, compose formatting) is either judged-out or already saturated.

## The evidence
1. **RACE ≈ 64% Insight(0.352) + Comprehensiveness(0.292).** Instruction-Following & Readability are
   compressed into a narrow ~44–54 band across the WHOLE field — they separate nobody. Depth/Insight is
   the lowest-scoring, widest-spread dimension (27→48 across models). Leaders score Insight 59–61;
   Western frontier agents (Gemini/OpenAI/Kimi/Doubao) score 42–49. THE GAP IS INSIGHT.
2. **RACE strips citations + reference lists BEFORE judging** (clean_prompt.py). Our ~90% citation
   faithfulness = literally 0 RACE points. (Explains every flat faithfulness/citation lever.)
3. **Retrieval volume is a trap.** Kimi Researcher: 70+ queries, 200+ URLs/report → Insight 42, near
   last. Finding facts ≠ writing depth. Our search stack is NOT the bottleneck.
4. **Test-time scaling saturates ~5–10 rounds** (FS-Researcher 3→10: Insight +2.43, log-shaped). Our
   4-round outline cap is roughly right — the fix is WHAT a round does, not how many.
5. **Model tier is the coarse dominant lever**, largest on Depth (~21 pts). FutureSearch: raw o3+tools
   beats OpenAI's packaged Deep Research — "frontier reasoning matters more than scaffolding." Matches
   our own biggest-ever win: GLM-5.2 → kimi-k3 = +0.030.
6. **HARD CORRECTION — no post-hoc synthesis pass.** "DR Agents are Unreliable at Multi-turn Report
   Revision" (arXiv 2601.13217): post-hoc revision REGRESSES 16–27% of content/citations; agents drop
   material rather than deepen. FS-Researcher single-agent merge = −10.35. => a synthesis/argument pass
   AFTER writing HURTS. This independently re-derives our own [[no-post-generation-fix-rule]]. The
   Insight lever must be PRE-writing: put structure + conflict IN FRONT OF the writer.

## Why our Batch 3 was flat (now explained)
Contradiction mining + relation packs ORGANIZE evidence; they don't make the model REASON. The leaders
change what the writer DOES (apply an analytical framework, adjudicate conflicts, weight sources), not
what it's fed. We kept improving inputs to a summarizing writer.

## What the winners actually do (all PRE-/at-generation — inside our firewall)
- **WebWeaver** (first Insight >50): dynamic outline INTERLEAVED with evidence acquisition;
  hierarchical writing ablation: Insight 42.72 → 50.02.
- **AgentCPM-Report** "Reasoning-Driven Deepening": detects logical gaps / superficial arguments in
  intermediate DRAFTS → triggers MORE TARGETED research on those nodes → Comp +4.30, Insight +4.54.
  (Best published analog to what we should build.)
- **DualGraph** (claim/knowledge graph before writing): Comp +2.09, Insight +2.51.
- **DRAGged into Conflicts** (explicit contradiction reasoning fed to the writer): "significantly
  improves quality." Baidu writer uses AHP-entropy weighting frameworks.

## PRIORITIZED PLAN (measure the ceiling first)
1. **Stronger-reasoning-generator A/B on the section-writer role.** Biggest single mover (+0.02–0.05,
   Depth-weighted). Settles whether further scaffold work is even worth it. A/B kimi-k3 vs a top
   reasoning model on the WRITER role only; same corpus/outline; 3 draws each; same-judge. DECISION:
   model identity change — consult operator/Fable; keep faithfulness off for scoring parity.
2. **Draft-feedback outline deepening (AgentCPM/WebWeaver).** After a first pass, detect thin/listy/
   superficial sections → reopen TARGETED research + outline revision for those nodes → rewrite from the
   enriched KB. PRE-generation, NOT a post-hoc rewrite. +0.02–0.04, Insight-weighted.
3. **Pre-writing structural synthesis.** Feed a claim/knowledge graph + the contradiction-mining output
   as ADJUDICATION PROMPTS into the outline/evidence stage; make the writer reason FROM a pre-structured
   KB. Repurposes Batch 3's miner correctly (input to reasoning, not evidence reshuffling). +0.01–0.03.
4. **Perspective-diverse parallel retrieval (STORM) + audit the scope-gate for OVER-exclusion.**
   Comprehensiveness. +0.01–0.03.
5. **DO NOT** add any post-generation synthesis/revision pass (regresses content; violates our rule).

## Honest ceiling
If the target is ~0.58, a stronger / report-RL'd GENERATOR is very likely required — the frontier
(Step-DR 61, Gemini 63 Insight) got there by improving the MODEL, not the scaffold. Our accessible
scaffold headroom is real but single-digit and lives ENTIRELY in pre-generation deepening + structuring.
So: run lever #1 (generator A/B) FIRST to measure the true ceiling before investing in #2–#4.

## Caveats
- Leaderboard numbers are legacy Gemini-2.5-Pro judge; a parallel GPT-5.5 board exists on a different
  scale. Tonight's judge is the GPT-5.5-era one and drifted ~-0.036 vs our historical 0.5084 baseline.
- Several leaders' internals (Baidu generator, ZTE-Nebula pipeline, Doubao) are unpublished.
