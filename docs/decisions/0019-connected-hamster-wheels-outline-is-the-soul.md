# 0019. Report quality is a chain of connected hamster wheels; the outline is the soul

Status: accepted

Date: 2026-07-11

## Context

The first real end-to-end report was usable but ultra-thin: 511 words from about 15 of 323 baskets, versus ChatGPT at 21,881 words and Gemini at 10,539. The structural root was the OUTLINE assigning few baskets, so most baskets fell into one residual section, plus a one-shot compose with no depth loop. FS-Researcher (arXiv 2602.01566) is the model: a Context Builder with a KB bigger than context, plus a section-by-section Report Writer with a gap-driven re-fetch loop (`project_connected_hamster_wheels_beat_sota_2026_07_11.md`, `project_architecture_pivot_fsresearcher_sections_2026_07_10.md`).

## Decision

Treat the pipeline as a chain of per-stage hamster wheels: corpus (S2/S3) → outline (cp4) → compose (cp5) → verify (cp6) → render. Rules:

- Activate one wheel at a time, upstream-first.
- Each wheel has two bars: usable (0 P0) first, then beat-SOTA.
- A validated-better upstream output flows to the downstream wheel.
- Depth is query-adaptive: the section count is set at intake from user intent, never hardcoded.

The outline is the depth bottleneck and the soul of the report. It must be an AGENT with strong tools plus the corpus as its knowledge base; it must generalize across all domains, run agentic compute that is traceable and verified, and loop back to re-fetch when it detects a corpus gap. Keep it simple: "agent + tools + corpus". Anything more elaborate is over-engineering.

## Consequences

- The outline decides how many baskets each section gets, so a thin outline dumps most baskets into one residual section and starves depth. Fixing the outline is the highest-leverage move.
- Activating wheels one at a time, upstream-first, means a downstream wheel is only driven to beat-SOTA once its input is validated-better; do not polish compose on a not-yet-best corpus or outline.
- Benchmark POLARIS the way FS-Researcher benchmarks others (DeepResearch-Bench RACE dimensions), not by word count alone.
- Query-adaptive depth means section count comes from user intent at intake; a hardcoded section count is a regression toward the thin-outline failure.
