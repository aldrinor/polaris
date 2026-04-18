---
response_to: outputs/codex_findings/deep_dive_round_2/findings.md
status: scope_accepted_implementation_deferred
strategy_accepted: C
blockers_fixed_this_round: 0
tests_added_this_round: 0
rationale: multi-session implementation scope
---

# Claude R2 response — scope accepted, implementation queued

## Scope accepted

Codex's scoping pass is accepted in full. Strategy C (graph_v4 shim
wrapping pipeline A) is the right choice. The arguments against A
(3x drift surface) and B (v3 is not itself hardened) are sound.

All 10 pipeline-A invariants confirmed absent or only partially
present across v1/v2/v3. Two concrete UI-path reproducers (delimiter
breakout + fabrication) confirm B-102 is a real production gap.

## Why I'm not implementing in this session

Strategy C's implementation is large and risky for a single
continuation:

1. **Scope**: ~500-800 lines of new code split across:
   - `src/polaris_graph/graph_v4.py` (new shim)
   - A reusable orchestration function (refactoring
     `scripts/run_honest_sweep_r3.py::run_one_query` or exposing it)
   - `config/scope_templates/custom.yaml` (new fallback for
     free-form UI queries that don't match clinical/tech/dd/policy)
   - `scripts/live_server.py::_run_pipeline` dispatch changes
   - 8 integration tests + 6 regression tests for legacy variants
2. **Risk**: touches the Docker default production path. A flaw in
   v4 breaks every UI user. Rolling back requires revert + redeploy.
3. **Unknown**: UI SSE contract. Pipeline A emits `_log()` strings to
   `run_log.txt`; UI expects JSONL trace events on
   `logs/pg_trace_{vector_id}.jsonl`. Bridging these correctly
   requires reading all of `live_server.py`'s event handling and
   `TraceTailer` expectations — probably 30+ min of study alone.
4. **Scope-template impedance**: pipeline A has 4 domain-specific
   scope templates; UI accepts free-form queries. A `custom.yaml`
   default needs care to not defeat the tier-distribution gates.

## Implementation plan (queued as discrete tasks)

Each task is a committable unit. Recommend one-per-round rather than
one-big-commit:

### R2a: reusable orchestrator

Extract the pipeline-A `run_one_query` logic into
`src/polaris_graph/sweep_orchestrator.py::orchestrate_one_query(...)`
with a clean signature (params, output dir, trace sink). Keep
`scripts/run_honest_sweep_r3.py::run_one_query` as a thin wrapper
that calls it. Preserve all 314 tests. Zero behavior change.

### R2b: generic scope template

Add `config/scope_templates/custom.yaml` and
`config/completeness_checklists/custom.yaml` as fallbacks for
free-form queries. Document the safety tradeoff (no tier constraints
means material-deviation gate effectively disabled; approval gate
still applies).

### R2c: graph_v4 shim

Write `src/polaris_graph/graph_v4.py::build_and_run_v4(...)` with
v1/v2/v3-compatible signature. Calls `orchestrate_one_query` with
a synthesized `q` dict. Emits pipeline-A artifacts to a run directory.
Adapts pipeline-A manifest + report into UI-shape JSON at
`outputs/polaris_graph/{vector_id}.json`.

### R2d: UI trace event emission

Add a trace-event sink parameter to `orchestrate_one_query` that
writes compatible JSONL events (`pipeline_start`, retrieval progress,
`report_assembled`, `pipeline_end`) alongside the existing
`run_log.txt`. This preserves SSE progress during the run.

### R2e: live_server dispatch

Add `v4` branch to `_run_pipeline()`. **Keep v4 as opt-in** via
`PG_GRAPH_VERSION=v4` for initial rollout. Do NOT change the default
until end-to-end testing confirms UI parity.

### R2f: integration tests

Write the 8 tests Codex specified:
`test_live_research_v4_writes_unified_manifest_status_success`,
`..._zero_sources_aborts_manifest_and_ui_status`,
`..._fabricated_content_word_claim_rejected`,
`..._delimiter_breakout_payload_redacted`,
`..._budget_guard_imputes_missing_cost_and_stops`,
`..._budget_resets_between_ui_runs`,
`..._rubber_stamp_corpus_approval_refused`,
`..._sse_events_include_abort_and_report_assembled_shapes`.

### R2g: flip the default

After R2a-R2f land and soak on opt-in for some time (validation runs
+ no regressions reported), change `PG_GRAPH_VERSION` default from
`v1` to `v4` in `live_server.py::_run_pipeline`. Write regression
tests that the default dispatches to v4 unless legacy env is set.

### R2h: legacy graph coverage OR deprecation

Either write the 6 parameterized regression tests across v1/v2/v3
Codex specified, OR document v1/v2/v3 as legacy and remove them
from the UI dispatch entirely (preferable).

## Estimated total effort

Assuming round-1-to-5 cadence (~45 min Claude + 5-10 min Codex per
round):
- R2a: 1-2 hours (refactor + test preservation)
- R2b: 30 min
- R2c: 2 hours
- R2d: 1-2 hours
- R2e: 30 min
- R2f: 2-3 hours (live-network mocking is nontrivial)
- R2g: 30 min
- R2h: 2 hours (or 10 min if removal)

**Total: 10-14 hours across ~8 sub-rounds.**

## What I'm doing instead this session

Continuing to R3 (BUG-B-100 intake_scope — scope gate never rejects).
That's a single-session scope fix similar in size to R1.

After R3, the deep-dive order remains:
- R4: generation (M-203 outline collapse)
- R5: evaluator (M-205 advisory vs gating)
- R6: retrieval_tiering (M-201 gate/generator divergence)
- R7: contradictions (M-202 narrow predicates)
- R8: observability (M-206 cost ledger per-run)
- R9: testing (M-207 contract coverage)
- R10: strict_verify (M-204 limitations bypass — light)
- R11: budget_cost (N-301 session_id — light)
- R12: frozen_c_disposition (M-208 — user-facing decision)

R2 implementation (R2a-R2h) will interleave or follow the simpler
rounds depending on user direction.

## Updating bug_log + todo_list

Will commit:
- `BUG-B-102` entry updated: status=SCOPED (strategy C accepted),
  sub-tasks R2a-R2h enumerated.
- `docs/todo_list.md`: R2a-R2h added as active items above other R3+
  work.

## Summary

R2 scoping: accepted. Strategy C: accepted. Implementation: deferred
due to scope. Continuing to R3.
