# POLARIS BENCHMARK TARGET — the real scoreboard (from web search 2026-07-11)

## What we must beat
**FS-Researcher** (arXiv:2602.01566, ACL 2026) — "Test-Time Scaling for Long-Horizon Research
Tasks with File-System-Based Agents". A file-system dual-agent (Context Builder + Report Writer)
that scales research BEYOND the context window via a persistent knowledge base. This is the same
thesis as POLARIS (process ALL 329 baskets (current s2s3 iter-7 count; 346 was the stale iter-6 count), not one context window). It claims **SOTA report
quality** across backbones. Code: github.com/Ignoramus0817/FS-Researcher.

## The benchmarks it is scored on (both open-ended report quality)
1. **DeepResearch Bench** (arXiv:2506.11763) — 100 PhD-level research tasks.
   - Scorer: **RACE** — reference-based LLM judge, 4 dimensions with per-task DYNAMIC weights:
     Comprehensiveness, Insight/Depth, Instruction-Following, Readability.
     Compares the target report against a high-quality REFERENCE report.
   - Download: `github.com/Ayanami0730/deep_research_bench` — tasks at
     `data/prompt_data/query.jsonl` (100 tasks); HF dataset `muset-ai/DeepResearch-Bench-Dataset`.
   - Leaderboard (ChatGPT/Gemini deep-research RACE scores) is on HuggingFace.
2. **DeepConsult** — open-ended consulting-style report quality (pairwise/quality judge).
3. (also referenced for the agent side: BrowseComp, BFCL, TAU-Bench, MCP Agent Bench.)

Related: **DeepResearch Bench II** (arXiv:2601.08536) — rubric-from-expert-report diagnosis
(the DRB-II wrapper already stubbed in the compete wheel).

## What this means for POLARIS
- **RACE is the correct instrument** — confirms the compete wheel's direction; DeepTRACE (faithfulness)
  is a SEPARATE, complementary axis, not the mission's quality axis.
- "Beat FS-Researcher" is now RUNNABLE: run POLARIS on the DeepResearch Bench 100 tasks, score with
  RACE against the reference reports, compare to FS-Researcher + the ChatGPT/Gemini leaderboard.
- The two build wheels serve this end:
  - **OUTLINE** → depth + compute-and-prove drives Comprehensiveness + Insight (RACE dims 1-2) and
    the faithfulness moat (DeepTRACE) that frontier products lack.
  - **COMPOSE** → renders all 329 baskets (current s2s3 iter-7 count; 346 was the stale iter-6 count) fast + faithful so nothing is dropped for latency =
    Comprehensiveness + Readability, at full corpus depth.
- Open gap: we still have NO FS-Researcher report artifact locally; the benchmark download closes it
  (we can run POLARIS on the same 100 tasks and score head-to-head).
