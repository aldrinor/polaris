# POLARIS full-pipeline audit context bundle

**Purpose**: this directory is the context handed to Codex for the
full-pipeline audit that supersedes the narrow 5-round B-1..B-5 audit.

**Date**: 2026-04-18.
**Audit mode**: comprehensive / design-level. NOT a fix-verification
audit — that was rounds 1-5.

## What's in this bundle

| File | Purpose |
|------|---------|
| `00_README.md` | This file — how to use the bundle |
| `01_three_pipelines_map.md` | File-level map of pipelines A, B, C |
| `02_prompt_templates.md` | Extracted LLM prompts (generator, outline, limitations, evaluator) |
| `03_json_contracts.md` | Manifest + output JSON shapes |
| `04_sample_run_artifacts.md` | Links to representative outputs/honest_sweep_r6_validation/ runs |
| `05_known_failure_modes.md` | Failure patterns observed during 5-round audit |
| `06_recent_commits.md` | Last 50 commits with one-line descriptions |
| `07_audit_brief_for_codex.md` | The actual brief Codex will receive |

## How to use this for the audit

1. Codex reads `07_audit_brief_for_codex.md` as its mandate.
2. Codex traverses files 01-06 to build a mental model.
3. Codex also has read access to `architecture.md`, `README.md`,
   `docs/file_directory.md`, `docs/runbook.md`, `docs/live_code_audit.md`,
   and all `outputs/codex_findings/round_{1..5}/`.
4. Codex produces a **risk register** in
   `outputs/codex_findings/full_audit_pass_1/findings.md` organized
   by dimension (retrieval, generation, verification, orchestration,
   prompts, gates, budget, observability, testing, frozen subsystems,
   pipeline-B parity, security).
5. Each finding has: severity (blocker / medium / minor), file:line,
   reproducer if applicable, recommendation.

## Dimensions to audit (12)

1. **Intake & scope gating** — `scope_gate.py`, `scope_query_validator.py`
2. **Retrieval & tiering** — `live_retriever.py`, `tier_classifier.py`,
   `domain_backends.py`, `prefetch_offtopic_filter.py`
3. **Contradictions** — `contradiction_detector.py`
4. **Generation (prompts + outline + sections)** — `multi_section_generator.py`,
   `live_deepseek_generator.py`, `provenance_generator.py` wrap + helpers
5. **Strict verify** — `provenance_generator.verify_sentence_provenance`,
   `strict_verify` (already probed in rounds 1-5, light touch)
6. **Evaluator** — `external_evaluator.py`, `live_qwen_judge.py`
7. **Orchestration** — `scripts/run_honest_sweep_r3.py`
8. **Budget + cost ledger** — `openrouter_client.check_run_budget`,
   `_impute_cost_from_tokens`
9. **Observability** — JSONL cost ledger, session log, bug log,
   manifest.json shape
10. **Testing** — 305 tests, coverage quality, missing integration paths
11. **Pipeline B parity** — which pipeline-A invariants (strict_verify,
    corpus approval, delimiter sanitization) are NOT enforced in
    `scripts/live_server.py` + `graph{,_v2,_v3}.py`
12. **Frozen subsystem disposition** — `src/orchestration/`, pipeline C,
    broken Docker `research` subcommand

## Anti-circle-jerk rules

Same as rounds 1-5:

- Read code at HEAD (commit `0cf2a65` or later), not this bundle's
  summaries
- If a prior "verified closed" invariant is actually still broken,
  re-raise with `severity_reraised: true`
- `READY` for the full pipeline requires zero blockers across ALL 12
  dimensions plus ≤5 mediums with explicit acceptable-risk rationale
- Silent failure mode = NOT_READY

## Authentication

OAuth (chatgpt). No OpenAI API credit burn.

## What Codex should NOT do

- Do not propose fixes — only identify issues and recommend directions
- Do not review pipeline C code for quality beyond confirming the
  Docker `research` subcommand is broken and the subsystem is frozen
- Do not re-litigate B-1..B-5 (settled in rounds 1-5) unless a new
  evasion vector is found

## What Codex SHOULD do

- Produce a prioritized risk register
- Flag anything that could cause a silent production failure
- Surface design-level issues (not just code-level)
- Note which findings would become blockers at full scale (10x the
  current 8-query sweep)
- Identify which dimensions need deep-dive follow-up rounds
