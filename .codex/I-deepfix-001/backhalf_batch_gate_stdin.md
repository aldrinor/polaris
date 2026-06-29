HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
Front-load ALL real findings. Reserve P0/P1 for real execution risks.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST. Do NOT run pytest. Review ONLY this diff to scripts/dr_benchmark/run_gate_b.py.

CONTEXT: POLARIS Gate-B benchmark harness. A real run aborted pre-spend ($0) when the pre-spend OpenRouter catalog probe got a TRANSIENT HTTP 408 and crashed the whole run (no retry). Separately, the --smoke-scale run-wall (3600) risked guillotining mid-back-half on the first authorized smoke.

TWO CHANGES IN THIS DIFF:
1) `_fetch_openrouter_catalog` (~331): wrap the GET in a bounded retry loop — retry on transient HTTP {408,425,429,500,502,503,504} and on httpx.HTTPError transport faults, with capped exponential backoff (2*2^attempt, cap 30s), PG_PREFLIGHT_CATALOG_RETRIES (default 5). A genuine persistent non-200 / transport fault STILL fails LOUD after the retries. A local `import time` was added (the module has NO top-level `import time`).
2) `_SMOKE_SCALE_OVERRIDES`: raise PG_RUN_WALL_CLOCK_SEC 3600->5400 and add PG_CREDIBILITY_PASS_WALL_S=600 (smoke-only; the full paid slate is untouched).

VERIFY ONLY:
1. RETRY CORRECTNESS: after the loop, `response` is always the OK response on the non-exception path (a transient status on the LAST attempt falls through to the LOUD raise, not a silent `continue`; a transport error on the last attempt raises). No path leaves `response` undefined before `body = response.json()`. The injected MockTransport test client (http_client != None) returns 200 on attempt 0 so behavior is byte-identical for tests. `own_client` is still closed in `finally` exactly once. `time` is in scope (local import). The backoff cannot busy-spin (sleeps only between attempts, not after the last).
2. NO INFINITE LOOP / NO UNBOUNDED SLEEP: attempts are bounded by _catalog_retries (>=1, parse-guarded); total worst-case added latency is acceptable for a pre-spend probe.
3. SMOKE WALL COHERENCE: 5400 keeps seam 1800 < run-wall and retrieval 1200 < run-wall (passes the coherence preflight at ~2424 which is `and not smoke_scale`-exempt anyway); PG_CREDIBILITY_PASS_WALL_S=600 < 5400. Paid slate (PG_RUN_WALL_CLOCK_SEC stays 10800 on the full path) is byte-identical.
4. FAITHFULNESS-NEUTRAL: both changes are pre-spend liveness + timeout-budget only; no faithfulness gate, no spend logic, no model selection touched.
5. NO NEW P0/P1 (undefined name, wrong indentation, double-close, swallowed real error).

If correct, APPROVE. If a real NEW P0/P1, REQUEST_CHANGES with exact file:line.

OUTPUT EXACTLY THIS SCHEMA (LAST line starts with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
