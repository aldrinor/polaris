# FX-20 (#1128) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P2 observability — faithfulness-SAFE. Adds a per-stage `discovery_funnel` to the manifest. Diff:
`.codex/I-ready-017/fx20_codex_diff.patch` (vs FX-19 verified tip `59e13571`, 3 files).

## Bug (observability gap)
On the held drb_72 run, the configured caps were inert but the throttle was MASKED — nothing surfaced
requested-vs-actual per stage. FX-18 also wired `openalex_search` into discovery but NEVER traced it,
so even a tracer-based funnel would silently OMIT OpenAlex (fabrication-by-omission).

## Fix (3 files)
1. **`live_retriever.py`** (FX-18 call site ~2466): record-only `_trace_tool("openalex_search",
   result_count=len(_oa_hits), num_requested=max_s2, backend_used="openalex_works_api")` on success +
   a `status="fail"` trace in the `except`. Makes OpenAlex a first-class traced backend.
2. **`tool_tracer.py`**: new `ToolTracer.discovery_funnel()` tallies per backend FROM `self._calls`
   (the SAME rows as `manifest()`) — serper/s2/openalex → `{calls, returned, requested, *_source}`;
   fetch_content → `{attempted, succeeded}` (succeeded = `status==ok`). An unrecorded count → `None` +
   `*_source:"unrecorded"`, NEVER 0. Booleans excluded from numeric sums. Wired into the existing
   `attach_tool_utilization` hook (called before EVERY manifest write) → `manifest['discovery_funnel']`;
   ADDITIVE + only when `tool_tracker_enabled()` → OFF-mode manifest stays byte-identical.
3. Tests.

## Evidence
- §-1.1 on the REAL held `tool_trace.jsonl`: funnel EQUALS an independent hand tally EXACTLY —
  serper {calls 5, returned 50, requested null}, s2 {calls 5, returned 4, requested null},
  openalex {calls 0, returned null}, fetch {attempted 145, succeeded 74}. `requested=null` is HONEST
  (held trace predates FX-17's `num_requested`); openalex 0 calls is HONEST (predates FX-18). Full
  audit: `outputs/audits/I-ready-017/fx20_s11_audit.md`.
- Offline smoke `test_fx20_discovery_funnel_iready017.py` → 6 passed: per-backend tallies; unrecorded
  → None (not 0); bool metadata excluded; `succeeded<=attempted`; funnel reconciles with `manifest()`
  per-tool ok/total; attach stamps funnel ON / OMITS it OFF (byte-identical).
- Regression: `test_tool_tracer_meta007` 15 + meta007/008 + feature-firing 18 — all green.

## Faithfulness
Pure observability. No grounding / strict_verify / 4-role / retrieval-behavior change. The new openalex
`_trace_tool` is record-only (cannot alter results). The funnel is DERIVED from recorded rows so it
cannot fabricate; unrecorded counts are explicit `null`. No-silent-downgrade-aligned.

## Note (scope honesty)
This funnel covers the tracer-observable discovery+fetch stages. `merged` (post-dedup candidate count)
and `selectable` (post-filter, the FX-15b `urls_selectable` telemetry) are run-level, not tracer-level;
they already appear on the manifest via the corpus distribution + agentic telemetry, so I did NOT
duplicate them into the funnel (avoids a second source that could drift from the corpus block). If you
think the funnel should also carry merged/selectable for one-stop visibility, say so and I'll wire them
from the real run-level values (not recomputed).

## Question
Is the funnel honest (derived from recorded rows, null-for-unrecorded, no fabrication), the openalex
trace correct + record-only, and the OFF-mode byte-identity preserved? Anything blocking APPROVE?
