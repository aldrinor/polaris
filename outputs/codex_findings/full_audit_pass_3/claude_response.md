---
response_to: outputs/codex_findings/full_audit_pass_3/findings.md
status: ready_accepted_with_documented_mediums
verdict_received: READY
blockers: 0
mediums_accepted_as_followup: 2
---

# Claude response to Codex pass 3 — READY confirmed

Codex declared **READY** with zero blockers. Two mediums flagged as
explicitly acceptable-risk for READY, both documented as follow-ups.

## B-102 confirmed substantively closed

Codex verified every item in the substantivity check:

- Signature compatibility with v1/v2/v3: PASS (`inspect.signature` drop-in)
- Pipeline-A delegation: PASS (graph_v4 awaits
  `scripts.run_honest_sweep_r3.run_one_query`, not a local reimpl)
- UI result endpoint: PASS (main result + export paths work)
- Trace events: PASS (pipeline_start/report_assembled/pipeline_end)
- Error path: PASS (exceptions → `error_unexpected` status in taxonomy)
- live_server dispatch: PASS (PG_GRAPH_VERSION default "v4", safe fallback)

## Pass-2 remediations all verified via direct repros

- **B-201 ContextVar**: two-task repro confirmed `[('A', 'A', 1.0),
  ('B', 'B', 10.0)]` — no cross-task stomping
- **M-209 metric binding**: "T-cell count of 500" with
  "http_status: 500" → rejected with `limitations_number_not_in_telemetry:500`
- **N-302 selector cap**: T1/T2/T3/T7 pool + max_rows=2 → 2 rows
  `['T1', 'T2']` (not 3)

## Two accepted mediums (follow-ups, not blockers)

### M-210: UI JSON missing auxiliary-view fields

`graph_v4._adapt_pipeline_a_to_ui_json` emits `vector_id`,
`original_query`, `status`, `release_allowed`, `final_report`,
`bibliography`, `contradictions`, `quality_metrics`, `evaluator_gate`,
`evidence_selection`, `cost_usd`, `budget_cap_usd`, `run_dir`,
`graph_version`, `timestamps`. It does NOT emit v3-era `evidence`,
`sections`, `claims`, `iteration_count`, `trace_summary`,
`smart_art_diagrams`, `evaluator_output`.

**Impact**: citation chain (`/api/research/chain/{vid}/{cite}`),
source preview, and mindmap endpoints degrade to empty/404 for v4
runs. Main report rendering + bibliography work fine (readers use
`.get(...)` defaults).

**Accepted risk for READY**: not a hardening bypass, not a silent
safety failure. Auxiliary UI tabs are optional. Fix is straightforward
(load `live_corpus_dump.json` + selected_evidence into the adapter).

**Follow-up**: add to `docs/todo_list.md` as M-210. Single-session
work (~2-3 hours).

### M-211: SSE trace granularity regression

v4 emits only lifecycle events (`pipeline_start`, `report_assembled`,
`pipeline_end`) around the blocking `run_one_query` call. v3 emitted
per-phase events (search/analyze/write/evaluate). UI users see a
dead period mid-run on long sweeps.

**Impact**: UX observability, not safety. No data-integrity concern.

**Accepted risk for READY**: users still see start + completion +
final artifacts. Fix is to thread a tracer through `run_one_query`
and emit per-phase events.

**Follow-up**: M-211 in todo_list. Multi-step because it requires
refactoring `run_one_query` to accept a tracer (or use the ambient
`_current_tracer` ContextVar that already exists in `tracing.py`).

## Pipeline A + Pipeline B are both RELEASE-READY

- **Pipeline A sweep** (`scripts/run_honest_sweep_r3.py`): ready for
  8-query full-scale validation run. All 20 attack vectors covered,
  396+ regression tests, Codex READY verdict.
- **Pipeline B UI** (`uvicorn scripts.live_server:app`, Docker
  default `serve`): ready via graph_v4. Hardening invariants hold.
  M-210 + M-211 auxiliary UI feature gaps are documented non-blockers.

## What ships

Commits ready for full-scale run:
- `427b6ff` B-102 CLOSED (graph_v4 + custom template + dispatch)
- `[pass2 remediation]` B-201/M-209/N-302
- R1-R12 deep-dive chain (B-100, B-101, M-201..208, N-301 closed)
- 5-round initial audit (B-1..B-5 closed)

Total: 405 tests passing, zero failing, zero xfail.

## Recommendation

Proceed with the 8-query full-scale sweep. Monitor for real-run
defects. File M-210 + M-211 as tracked follow-ups in `docs/todo_list.md`.
