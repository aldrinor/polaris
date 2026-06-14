# Codex BLANK-SLATE chokepoint hunt — h4_resilience_cost

HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings in iter 1. Same quality bar regardless of iteration. Do not pick bone from egg — reserve P0/P1 for real execution/quality/faithfulness risks; classify minor as P2/P3.

## Context
POLARIS deep-research pipeline; repo root = current dir (C:\POLARIS). LIVE RUN PATH = scripts/run_honest_sweep_r3.py + scripts/dr_benchmark/run_gate_b.py and everything they import (generator/multi_section_generator, generator/provenance_generator, roles/*, authority/*, retrieval/*, agents/*, llm/openrouter_client). UI (web/**), frozen legacy (src/orchestration/**), tests = OUT OF SCOPE. A 3-hour validation run just DIED at status=error_unexpected (a report section exceeded a 600s wall-clock twice + the section gathers lack return_exceptions=True so one slow section cancels all siblings and crashes the whole run). Operator directives: timeouts UNLIMITED-with-watchdog OR 1.5x realistic generate time (sized off the 64000-token section budget); EVERY tunable param must be a PG_ .env var (hardcoding is "super lethal"); the pipeline MUST have CHECKPOINTS (carry DATA not VERDICTS; always re-run faithfulness gates on resume); faithfulness gates (strict_verify/NLI/4-role) are NEVER relaxed. Locked models: generator=deepseek/deepseek-v4-pro, mirror=z-ai/glm-5.1, sentinel=minimax/minimax-m2, judge=qwen/qwen3.6-35b-a3b.

## YOUR LENS
Resilience, idempotency & cost/efficiency. Find where a transient error becomes fatal (no retry/fallback), non-idempotent steps that can't be safely re-run, missing partial-failure handling, wasteful duplicate LLM calls or re-fetches, expensive work done before a cheap gate that could short-circuit it, cost-cap interactions, and any place the pipeline spends time/money it doesn't need to.

## TASK — BLANK SLATE
You are deliberately given NO prior findings list. Independently hunt the LIVE run path line-by-line through YOUR LENS and report EVERY chokepoint you find — anything that hurts throughput, quality, completion, faithfulness, breadth, or cost. Read the actual code (file:line); do not guess. Hunt specifically for things a checklist-driven auditor would NOT think to look for. Be exhaustive within your lens.

## Output schema (YAML, required):
```yaml
findings:
  - {location: "file:line", what: "", why_it_chokes: "", fix: "", severity: "P0|P1|P2|P3", should_be_env: "PG_NAME or n/a"}
top_3_surprises: ["the chokepoints you think a checklist-driven auditor would most likely MISS"]
notes: ""
```
