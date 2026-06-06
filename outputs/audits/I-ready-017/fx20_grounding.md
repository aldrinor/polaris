# FX-20 (#1128) grounding — discovery_funnel requested-vs-actual telemetry

Status: GROUNDED, author next wake (fresh context). Heavy: touches the shared tool_tracer; high
no-fabrication bar (§-1.1: funnel numbers MUST equal raw tool_trace tallies, never defaulted/invented).

## Data model (verified)
The single source of truth is the `ToolTracer` (`src/polaris_graph/telemetry/tool_tracer.py`).
`ToolCall` carries `tool_name`, `status`, `backend_used`, and a free-form `metadata` dict.
`attach_tool_utilization(manifest, run_dir)` (tool_tracer.py:280) is the ONE hook called before EVERY
manifest write (success + all abort/error paths) — it already stamps `manifest['tool_utilization']`
from `tracer.manifest()`. FX-20's `discovery_funnel` rides the SAME hook (flag-gated by
`tool_tracker_enabled()` — byte-identical OFF; benchmark slate forces `PG_ENABLE_TOOL_TRACKER=1`).

## Traced backends + recorded fields (live_retriever `_trace_tool`)
| tool_name | where | requested field | returned field | notes |
|---|---|---|---|---|
| `serper` | live_retriever.py:305-309 | `num_requested` (+`per_page`,`pages_fetched`,`total_budget`,`clamped`) | `result_count` | FX-17 added these |
| `s2` | live_retriever.py:390-393 | (none — emit `null` + `*_source:"unrecorded"`) | `result_count` | |
| `fetch_content` | live_retriever.py:1345/1912/1939 | n/a | use `status` | attempted = count of rows; succeeded = count `status=="ok"` (stub/fail are NOT success) |
| `openalex_search` | **UNTRACED** | — | — | **FX-18 GAP**: domain_backends.openalex_search (:466) never calls `_trace_tool`; FX-18 only bumps `api_calls`. A tracer-only funnel would OMIT openalex = fabrication-by-omission. |

## FX-20 fix scope (author next wake)
1. **Trace openalex** (record-only, faithfulness-safe): at the FX-18 call site
   `live_retriever.py:~2466` (right after `_oa_hits = openalex_search(q, limit=max_s2)`), add
   `_trace_tool("openalex_search", target=q, status="ok", result_count=len(_oa_hits), num_requested=max_s2, backend_used="openalex_works_api")`
   (and a `status="fail"` trace in the existing `except` at :2476). Makes openalex a first-class traced
   backend so the funnel reads it from the same rows.
2. **`ToolTracer.discovery_funnel()`** method: tally per backend from `self._calls` —
   `serper_requested`=Σ metadata.num_requested, `serper_returned`=Σ metadata.result_count;
   `s2_returned`=Σ result_count, `s2_requested`=null (+source marker); `openalex_returned`/`requested`
   from the new rows; `fetch_attempted`=count(fetch_content rows), `fetch_succeeded`=count(status==ok).
   NEVER default an unrecorded count to 0 — emit `null` + a `*_source` marker. Internally consistent:
   `fetch_succeeded <= fetch_attempted`.
3. **Wire into `attach_tool_utilization`**: after the `tool_utilization` block, add
   `manifest['discovery_funnel'] = tracer.discovery_funnel()` (only when `tool_tracker_enabled()`, so
   OFF stays byte-identical). merged/selectable are run-level (not tracer): add them in
   run_honest_sweep_r3.py from `len(retrieval.classified_sources)` (merged) + `urls_selectable`
   (agentic telemetry, manifest already carries it) — real values, with an explicit
   `cap_unreached_reason`/advisory when a configured cap (PG_SWEEP_MAX_SERPER etc.) exceeds the actual.
4. **Smoke** (offline, no network): build synthetic `ToolCall`s via `tracer.record(...)` →
   `discovery_funnel()` returns correct per-backend tallies + consistency (succeeded<=attempted);
   unrecorded s2_requested is `null` not 0; OFF (`PG_ENABLE_TOOL_TRACKER=0`) → no `discovery_funnel`
   key on the manifest (byte-identical).
5. **§-1.1**: on a real micro-run, `manifest.json discovery_funnel` numbers EQUAL the raw
   `tool_trace.jsonl` per-backend tallies (parse the jsonl, sum result_count/num_requested, count
   fetch rows) — zero drift. A configured-high-but-unreached cap carries an explicit advisory.

## Faithfulness
Pure observability. No grounding/strict_verify/4-role/retrieval-behavior change. The new openalex
`_trace_tool` is record-only (cannot alter results). Existing consumers ignore the unknown
`discovery_funnel` key.

## Related follow-up
The openalex-untraced gap (item 1) is itself a small honesty fix that FX-20 absorbs; no separate issue
needed (it's in scope for #1128 — the funnel can't be honest without it).
