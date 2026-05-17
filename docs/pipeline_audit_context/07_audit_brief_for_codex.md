# POLARIS full-pipeline audit — Codex brief (pass 1: scoping)

You are the independent reviewer for a comprehensive audit of POLARIS.
This is NOT a fix-verification audit (that was rounds 1-5, concluded
2026-04-18 with a READY verdict on the narrow B-1..B-5 scope).

This pass produces a prioritized risk register across ALL 12 pipeline
dimensions. Deep-dive rounds will follow, driven by your prioritization.

## Mandate

Read the pipeline-A code at HEAD (commit `0cf2a65` or later) and
produce a design-level audit covering:

1. Intake & scope gating
2. Retrieval & tiering
3. Contradictions detection
4. Generation (prompts + outline + sections + limitations)
5. Strict verify (light touch — settled in rounds 1-5)
6. Evaluator (both external_evaluator rules and live_judge)
7. Orchestration (`scripts/run_honest_sweep_r3.py`)
8. Budget + cost ledger
9. Observability (JSONL cost ledger, manifest shape, logs)
10. Testing (305 passing; coverage quality; missing integration paths)
11. Pipeline B parity (which invariants are NOT in `live_server.py`)
12. Frozen subsystem disposition (`src/orchestration/`, pipeline C)

For each dimension, produce:
- **Severity**: blocker / medium / minor / info
- **Finding**: what's wrong or risky
- **Evidence**: file:line + quoted code OR reproducer
- **Recommendation**: what a deep-dive round should attempt

## Required output

Write to `outputs/codex_findings/full_audit_pass_1/findings.md` with
this frontmatter:

```yaml
---
verdict: PRIORITIZED | READY | NOT_READY
dimension_summary:
  intake_scope: <severity | "clear">
  retrieval_tiering: <severity | "clear">
  contradictions: <severity | "clear">
  generation: <severity | "clear">
  strict_verify: <severity | "clear">
  evaluator: <severity | "clear">
  orchestration: <severity | "clear">
  budget_cost: <severity | "clear">
  observability: <severity | "clear">
  testing: <severity | "clear">
  pipeline_b_parity: <severity | "clear">
  frozen_c_disposition: <severity | "clear">
total_blockers: <int>
total_mediums: <int>
total_minors: <int>
rationale: |
  <2-4 sentence executive summary>
recommended_deep_dive_order:
  - <dimension name>
  - <dimension name>
  - ...
---
```

Followed by sections:

## Verdict semantics

- `PRIORITIZED` — scoping complete, risks enumerated, deep-dives queued
- `READY` — nothing worth deep-diving (implausible for first pass)
- `NOT_READY` — scoping couldn't complete (some surface was inaccessible
  or the bundle is inadequate)

## Context you have

Bundled in `docs/pipeline_audit_context/`:

- `00_README.md` — how to use this bundle
- `01_three_pipelines_map.md` — file-level map of pipelines A, B, C
- `02_prompt_templates.md` — verbatim LLM prompts
- `03_json_contracts.md` — manifest + output JSON shapes
- `04_sample_run_artifacts.md` — links to representative runs
- `05_known_failure_modes.md` — known gaps and observed issues
- `06_recent_commits.md` — last 50 commits summary
- `07_audit_brief_for_codex.md` — THIS file

Plus direct access to:

- `architecture.md` (rewritten 2026-04-18)
- `README.md` (rewritten 2026-04-18)
- `CLAUDE.md` (operational directives, §9 invariants updated 2026-04-18)
- `docs/file_directory.md`, `docs/runbook.md`, `docs/todo_list.md`
- `docs/live_code_audit.md` + `.json`
- `outputs/codex_findings/round_{1..5}/`
- All source under `src/polaris_graph/`, `scripts/`, `tests/`,
  `config/`, `outputs/honest_sweep_r6_validation/`

## Anti-circle-jerk rules

1. **Read code, not summaries**. When claim X appears in `architecture.md`
   or this bundle, cross-check against the actual code. If the docs lie,
   flag it as a finding.
2. **Prior invariants must actually hold**. If you can construct ANY
   silent-failure input against B-1..B-5 that wasn't covered in rounds
   1-5, re-raise with `severity_reraised: true`.
3. **Don't re-litigate settled issues**. If rounds 1-5 already closed
   a specific vector, don't bring it back unless you have a new
   evasion.
4. **Distinguish design from code**: a design issue (wrong approach)
   carries MORE weight than a code issue (bug). Flag both, but call
   out which is which.
5. **Always check for silent failures first**: the pipeline returning
   `status=success` when it should have returned `abort_*` is always
   a blocker, no matter how subtle.

## What NOT to do

- Do NOT propose code fixes in findings — just identify issues and
  recommend deep-dive directions.
- Do NOT audit pipeline C's internal code — just confirm it's broken
  and frozen (which the bundle documents).
- Do NOT audit pipeline B's JavaScript/HTML UI — focus on the
  Python-level parity gap with pipeline A.
- Do NOT re-run the 305 existing tests — trust that test suite as
  baseline. Instead, identify TESTING GAPS (coverage missing).

## Output location

Write findings to:
```
outputs/codex_findings/full_audit_pass_1/findings.md
```

## Authentication

OAuth (chatgpt). No OpenAI API credit burn.

## Scope bound

Aim to produce the risk register in one pass. If any dimension needs
>200 lines of discussion, defer detail to the deep-dive round and
keep the scoping pass tight (per-dimension: 1-3 blockers/mediums at
most; minors aggregated).

## Expected duration

5-15 minutes for Codex to produce the scoping pass. Deep-dive rounds
(one per prioritized dimension) will be launched separately based on
your recommendation order.

---

Start by:

1. Reading `00_README.md` to orient.
2. Reading `01_three_pipelines_map.md` to build mental model.
3. Opening the top-priority source files flagged in `01`.
4. Cross-checking prompts in `02` against actual source.
5. Inspecting one full sample run in `04` end-to-end.
6. Filling the frontmatter and writing findings per dimension.
