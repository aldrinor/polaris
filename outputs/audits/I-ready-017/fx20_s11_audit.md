# FX-20 §-1.1 audit — discovery_funnel requested-vs-actual telemetry (#1128)

**Standard:** §-1.1 over the REAL held drb_72 `run_artifacts/tool_trace.jsonl` — the funnel numbers
MUST EQUAL the raw per-backend tallies (no fabricated funnel), and an unrecorded count MUST be `null`
(never a fake 0 that silently under-reports).

## The bug (observability gap)
On the held drb_72 run the configured caps (MAX_SERPER=100 / MAX_S2=100 / FETCH_CAP=1000) were inert
but the throttle was MASKED — nothing on the manifest surfaced requested-vs-actual per stage. FX-18
also wired `openalex_search` into discovery but NEVER traced it, so even a tracer-based funnel would
silently OMIT OpenAlex (fabrication-by-omission).

## The fix
1. **Trace OpenAlex** (`live_retriever.py` FX-18 call site, ~2466): record-only
   `_trace_tool("openalex_search", result_count=len(_oa_hits), num_requested=max_s2, ...)` on success +
   a `status="fail"` trace in the `except`. Makes OpenAlex a first-class traced backend.
2. **`ToolTracer.discovery_funnel()`** (`tool_tracer.py`): tallies per backend FROM `self._calls` (the
   same rows as `manifest()`). serper/s2/openalex → `{calls, returned, requested, *_source}`;
   fetch_content → `{attempted, succeeded}` (succeeded = `status==ok`). An unrecorded count → `None` +
   `*_source:"unrecorded"`, NEVER 0. Booleans (e.g. `clamped=True`) are excluded from numeric sums.
3. **Stamped via the existing `attach_tool_utilization` hook** (called before EVERY manifest write):
   `manifest['discovery_funnel']`. Additive + only when the tracker is ON → OFF-mode manifest stays
   byte-identical.

## §-1.1 — funnel EQUALS raw tallies on the REAL held trace (line-by-line)
Replayed `outputs/audits/I-ready-017/run_artifacts/tool_trace.jsonl` into a fresh tracer; compared
`discovery_funnel()` against an INDEPENDENT hand tally of the same jsonl:

| backend | funnel | independent raw tally | match |
|---|---|---|---|
| serper | calls 5, returned **50**, requested null | calls 5, returned 50, requested None | ✓ |
| s2 | calls 5, returned **4**, requested null | calls 5, returned 4, requested None | ✓ |
| openalex_search | calls 0, returned null | calls 0, returned None | ✓ |
| fetch_content | attempted **145**, succeeded **74** | attempted 145, succeeded 74 | ✓ |

Every figure matches exactly. Cross-checks: serper returned 50 = 5 queries × 10 — consistent with the
FX-17 §-1.1 finding `serper [10,10,10,10,10]`. `requested=null` for serper/s2 is HONEST — the held
trace predates FX-17's `num_requested`; on a fresh post-FX-17/18 run serper carries `num_requested`
and openalex has calls>0, so the funnel grows correctly without fabricating the held-run values.
fetch 74/145 (51%) is exactly the previously-masked funnel attrition this telemetry surfaces.

## Offline smoke (proves the assembler)
`pytest tests/polaris_graph/test_fx20_discovery_funnel_iready017.py` → 6 passed:
per-backend tallies; unrecorded `requested`/`returned` → `None` (not 0); bool metadata excluded from
counts; `fetch_succeeded <= fetch_attempted`; funnel reconciles with `manifest()` per-tool ok/total;
`attach` stamps the funnel when ON and OMITS it (byte-identical) when OFF.
Regression: `test_tool_tracer_meta007` 15, meta007/008 + feature-firing telemetry 18 — all green.

## Faithfulness
Pure observability. No grounding / strict_verify / 4-role / retrieval-behavior change. The new OpenAlex
`_trace_tool` is record-only (cannot alter results). The funnel is DERIVED from recorded rows so it
cannot fabricate; unrecorded counts are explicit `null`. No-silent-downgrade-aligned: a configured cap
that the actual never reaches is now visible per stage.

## Codex diff-gate iter-1 verdict — APPROVE (accept_remaining)
`.codex/I-ready-017/fx20_codex_diff_audit_iter1.txt`: `verdict: APPROVE`, zero P0, zero P1, zero
execution blockers, `convergence_call: accept_remaining`. One accepted observability P2 (documented;
no code change so the APPROVE'd diff stays intact per §8.3.6):
- **OpenAlex internal fail-open masks as `ok, result_count=0`.** `domain_backends.openalex_search()` is
  fail-open by design — on an internal network/API error it returns `[]`, so the new call-site trace
  records `status=ok, result_count=0` (looks like "0 results" rather than "failed"). The added
  `status=fail` trace only catches import/post-processing exceptions at the call site, not errors
  swallowed *inside* `openalex_search`. The funnel figure stays honest (it DID surface 0 usable
  candidates) — the refinement is distinguishing "0 because empty" from "0 because internally failed".
  Out of FX-20's scope (FX-20 = funnel/trace; this is openalex's internal error contract). Captured as
  **follow-up FX-20b** (have `openalex_search` signal failure-vs-empty, or trace from inside it). Not a
  blocker; accepted per Codex `accept_remaining`.
