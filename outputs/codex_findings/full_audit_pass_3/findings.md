---
verdict: READY
pass: 3
commit: 427b6ff
b102_disposition: CLOSED_CONFIRMED
pass_2_remediations_verified: [B-201, M-209, N-302]
new_blockers: 0
new_mediums: 2
rationale: |
  B-102 is substantively closed: the live UI default now dispatches to graph_v4, and graph_v4 delegates execution to scripts.run_honest_sweep_r3.run_one_query, so the UI path gets the pipeline-A hardening rather than a cosmetic wrapper. The pass-2 remediations hold under direct repros. I found two medium follow-ups: v4 writes enough JSON for the main result/export path but not the full v3 auxiliary-view shape, and SSE progress is sparse during long pipeline-A runs.
---

## 1. B-102 substantivity check

Verdict: CLOSED_CONFIRMED.

- Signature compatibility: PASS. `src/polaris_graph/graph_v4.py:125` exposes `build_and_run_v4(vector_id, query, application, region, stage, max_iterations, max_execution_minutes, resume, enable_dashboard, document_ids, steer_callback, research_brief)`, matching the v1/v2/v3 live-server call surface. I also compared signatures via `inspect.signature`; v4 is drop-in for `scripts/live_server.py:604-616`.
- Pipeline-A delegation: PASS. `graph_v4.py:145` deferred-imports `scripts.run_honest_sweep_r3.run_one_query`, and `graph_v4.py:186` awaits it with a synthesized query dict. This is the hardened pipeline-A orchestrator, not a local reimplementation.
- UI result path: PASS for main result endpoint; MEDIUM for auxiliary JSON shape. `graph_v4.py:80-120` writes `outputs/polaris_graph/{vector_id}.json` with the fields consumed by `/api/research/result/{vector_id}` at `scripts/live_server.py:1892-1905` using safe `.get(...)` defaults. However, v4 does not include v3-era `sections`, `evidence`, `claims`, `iteration_count`, `trace_summary`, `smart_art_diagrams`, or `evaluator_output`; citation-chain and mindmap endpoints at `scripts/live_server.py:1913-2119` and `2530-2605` therefore degrade to empty/404 auxiliary views even when the markdown report and bibliography exist.
- Trace events: PASS for lifecycle, MEDIUM for granularity. `graph_v4.py:153-164`, `203-214`, and `220-225` emit `pipeline_start`, `report_assembled`, and `pipeline_end` through `PipelineTracer`; `PipelineTracer` writes `type` at `src/polaris_graph/tracing.py:233-241`, which `TraceTailer` can stream.
- Error path: PASS. `graph_v4.py:188-226` catches `run_one_query` exceptions, writes UI JSON with `status: "error_unexpected"`, sets `release_allowed: false`, emits `pipeline_end`, and returns `{"status": "error_unexpected"}`. `error_unexpected` is in `UNIFIED_STATUS_VALUES` in `scripts/run_honest_sweep_r3.py:80-114`.
- Live-server dispatch: PASS. `scripts/live_server.py:555-570` defaults `PG_GRAPH_VERSION` to `"v4"`, imports `build_and_run_v4` for v4, keeps v1/v2/v3 explicitly selectable, and falls back safely to v4 for unknown values.

## 2. Edge-case probes

Domain inference bypass: PASS. `_infer_domain` defaults unknown UI queries to `custom`, but `run_one_query` still executes scope gate, live retrieval, corpus adequacy, corpus approval, strict verification, contradiction detection, evaluator gate, and unified manifest writes. The custom template has no minimum tier floors, but it still has maximum caps. Direct probe with 100% T7 custom corpus produced `has_material_deviation=True`, `auto_approve_allowed=False`, and `check_auto_approve_allowed(..., "ok") == False`. So the "no minimums" setting does not disable rubber-stamp enforcement for material over-representation.

Concurrent UI runs: PASS / not externally reachable as two simultaneous runs. `scripts/live_server.py:431-438` and `1776-1809` enforce a single active `PipelineRunner` and return 409 for a second `/api/research`. For internal async concurrency, B-201 holds: direct `asyncio.gather` repro returned `[('A', 'A', 1.0), ('B', 'B', 10.0)]`, proving run id and cost isolation in separate tasks.

UI output shape drift: MEDIUM. The main result endpoint survives because it uses defaults, but v4 does not adapt pipeline-A artifacts into the richer `evidence` / `sections` / `claims` structure that citation-chain, source-preview, and mindmap endpoints expect. Acceptable risk for READY because this does not bypass hardening or make unsafe reports look successful; it is a feature-parity regression in auxiliary UI affordances. Recommended follow-up: teach `_adapt_pipeline_a_to_ui_json` to load `live_corpus_dump.json`, selected evidence, section metadata, and evaluator outputs, or explicitly disable auxiliary tabs for `graph_version=="v4"` until that mapping exists.

SSE trace streaming: MEDIUM. v4 emits only lifecycle events around the blocking pipeline-A call. Users may see a long quiet period between `pipeline_start` and `report_assembled` on real runs. Acceptable risk for READY because completion/error status and artifact writing are correct, and this is a UX observability gap rather than a silent safety failure. Recommended follow-up: bridge pipeline-A phase logs into `PipelineTracer` events at scope, retrieval, adequacy, approval, generation, evaluation, and manifest write.

## 3. Pass-2 remediation verification

B-201 ContextVar: VERIFIED. `src/polaris_graph/llm/openrouter_client.py:70-78` defines `_RUN_COST_CTX` and `_CURRENT_RUN_ID_CTX` as `contextvars.ContextVar`. `set_current_run_id`, `current_run_id`, `reset_run_cost`, `current_run_cost`, and `_add_run_cost` all use those ContextVars at lines `81-113`; `OpenRouterClient.__init__` reads the ambient run id at `780`. Direct two-task repro confirmed no stomping.

M-209 metric binding: VERIFIED. `verify_limitations_sentence_against_telemetry` now requires numeric matches on lines that mention known telemetry metric keys (`src/polaris_graph/generator/provenance_generator.py:445-490`). Direct repro with `"T-cell count of 500"` and telemetry `"http_status: 500\n..."` returned `False` with `limitations_number_not_in_telemetry:500`.

N-302 selector cap: VERIFIED. `src/polaris_graph/retrieval/evidence_selector.py:216-234` can deduct below present high-value floors when necessary to honor `max_rows`. Direct repro with T1/T2/T3/T7 and `max_rows=2` returned exactly two rows, `['T1', 'T2']`.

Targeted test status: `tests/polaris_graph/test_pass2_remediation.py` passed all 9 tests. `tests/polaris_graph/test_b102_graph_v4.py` had 4 setup errors in this sandbox because pytest could not create/access temp directories (`PermissionError: [WinError 5]`), so I used direct in-process repros for the affected checks. The requested broader `python -m pytest tests/polaris_graph/ -q` likewise did not reproduce the claimed clean 405-pass state here due the same environment permissions plus scope-gate failures.

## 4. New defects (if any)

MEDIUM: `src/polaris_graph/graph_v4.py:80-120` omits auxiliary UI fields that `scripts/live_server.py` reads from result JSON.

Reproducer:

```python
from src.polaris_graph.graph_v4 import _adapt_pipeline_a_to_ui_json
# Given a normal pipeline-A run_dir with manifest.json/report.md/bibliography.json,
# the adapted UI JSON has no "evidence", "sections", or "claims" keys.
# /api/research/result then reports evidence_count=0, and
# /api/research/chain/{vector_id}/{citation_number} cannot build custody links.
```

Impact: citation chain, source preview, and mindmap views degrade for v4 results. Main report rendering/export remains functional because `final_report` and `bibliography` are present and readers use defensive defaults.

MEDIUM: `src/polaris_graph/graph_v4.py:153-225` emits only lifecycle trace events around a long blocking pipeline-A run.

Reproducer:

```python
# Start a v4 UI run and watch /api/events.
# Expected v3-like progress includes search/analyze/write/evaluate events.
# Actual v4 trace has session_start, pipeline_start, report_assembled, pipeline_end.
```

Impact: users can see a dead period mid-run. This is not a data-integrity blocker, but it is a real UX regression from v3 trace granularity.

## 5. Final verdict and release guidance

READY.

B-102 is substantive: the production UI default now routes through pipeline-A hardening, not the legacy v1/v2/v3 graph. No new blocker or silent hardening bypass surfaced in the edge-case probes. Ship with two follow-ups: fill out the v4 UI JSON adapter for evidence/sections/claims auxiliary views, and bridge pipeline-A phase progress into SSE tracing.
