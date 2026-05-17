# Claude architect audit — I-bug-115 / GH #554

**Branch:** `bot/I-bug-115-corpus-assembly-timeout`
**Commit 1:** `10ab7d26`
**Canonical diff:** `.codex/I-bug-115/codex_diff.patch` — sha256 `fe3d1803cfd775f80bc48d98bcf0e505d9dee7e561fe9e3e52348fdc851e9b81`
**Diff:** 2 files, +257 / -3 (`live_retriever.py` +106/-3 = 109-line production CODE diff; `test_post_fetch_loop_timeout.py` +151 new test).

## What the diff does

Resolves GH #554 — `run_live_retrieval`'s synchronous post-`parallel_fetch`
candidate loop hangs indefinitely when `_openalex_enrich` wedges (httpx bounds
each request *phase*, not total request time). Three layers, all in
`src/polaris_graph/retrieval/live_retriever.py`:

1. **`_bounded_openalex_enrich(url, title, stats=None)`** — runs `_openalex_enrich`
   in a `daemon=True` thread; `worker.join(timeout=PG_OPENALEX_ENRICH_DEADLINE)`
   (default 45 s). On timeout: increment `stats["enrich_timeouts"]`, log loud,
   return `{}`, abandon the daemon thread. Mirrors the proven `_fetch_content`
   daemon-thread pattern (lines ~860-893). The call site at the loop
   (`oa = _openalex_enrich(...)`) is swapped to this wrapper.
2. **Overall loop budget** — `_loop_deadline = time.monotonic() + PG_POST_FETCH_LOOP_BUDGET`
   (default 900 s) computed before the loop; checked at the top of each
   iteration; on exceed → log loud + `break`, so `run_live_retrieval` returns
   with whatever was classified (a terminal verdict, never a hang).
3. **Per-candidate progress logging** — `logger.info` at the loop top with
   `i+1/len(candidates)` + truncated URL.
4. **Fail-fast** — after `PG_OPENALEX_ENRICH_FAILFAST` (default 3) enrich
   timeouts in a run, `_enrich_disabled` is set and the loop stops attempting
   enrichment — prevents abandoned daemon threads from accumulating when
   OpenAlex is degraded for the whole run (Codex brief P2-2).

`_env_float` / `_env_int` helpers read the three knobs with safe positive
fallbacks (LAW VI — no hardcode; mirrors `PG_FETCH_DEADLINE_SECONDS`).

## Self-audit against the brief's acceptance (line-by-line)

| Acceptance criterion | Verdict | Evidence |
|---|---|---|
| Post-fetch loop honours a hard wall-clock bound (per-candidate + overall) | VERIFIED | Layer 1 bounds each enrich call; Layer 2 bounds the aggregate loop. |
| A wedged enrich is abandoned, candidate still classified, run reaches terminal verdict | VERIFIED | `_bounded_openalex_enrich` returns `{}`; the loop continues to `classify_source_tier` + `classified_sources.append`; test 4 asserts `classified_sources` non-empty after every enrich wedges. |
| Regression test exercises a hung step and asserts the run is bounded | VERIFIED | `test_run_live_retrieval_bounded_when_openalex_wedges` — `_openalex_enrich` → `time.sleep(3600)`, asserts `run_live_retrieval` returns < 15 s. `test_bounded_openalex_enrich_returns_within_deadline` — direct unit proof. |
| `pytest` green / no regression | VERIFIED (scoped) | 5/5 new tests pass; **197/197** tests pass across all 12 test files importing `live_retriever`/`run_live_retrieval` (the exact blast radius of a 3-edit additive change to that file). Full `tests/polaris_graph/` collects 4619 tests with `PYTHONPATH='src;.'`; 1 pre-existing collection error (`test_demo_smoke.py` — `static_accounts.yaml not found`, an auth-substrate env dependency, unrelated to `live_retriever`). |
| ≤200-LOC isolated CODE diff | VERIFIED | Production code diff = 109 lines in one file; under cap. Test file (151 lines) is test code. |
| LAW VI — no hardcode | VERIFIED | All 3 thresholds via `os.getenv` + `_env_float`/`_env_int` with documented defaults. |

## Risk assessment

- **Daemon-thread leak on timeout** — an abandoned enrich thread holds an
  `httpx.Client` until it eventually completes or the process exits. Same
  tradeoff `_fetch_content` already makes (lines ~885-887). Layer-4 fail-fast
  caps the count per run. LOW.
- **Behaviour change on the happy path** — when `_openalex_enrich` returns
  fast, `_bounded_openalex_enrich` passes the result through unchanged
  (test 2). The only added cost is one short-lived thread spawn per candidate
  (~ms). NEGLIGIBLE.
- **`run_live_retrieval` signature / return type** — unchanged. Callers
  (`run_honest_sweep_r3.py`, `run_live_honest_cycle.py`,
  `v28_retrieval_preflight.py`) are unaffected.
- **`_openalex_enrich` itself** — not modified; `test_m12_pass12` (display_name
  preservation) still passes.

## Diagnosis honesty (carried from brief, Codex-APPROVE'd iter 1)

Locus (post-fetch loop) is log-proven; nature (I/O block) is CPU-proven
(43 s process CPU ≈ the docling 43.22 s conversion, ~0 after). `_openalex_enrich`
identified as the loop's only I/O by elimination. The live faulthandler repro
completed cleanly (OpenAlex responsive that run) — the transient was not
stack-frozen; the fix is mechanism-agnostic (a wall-clock bound holds
regardless of what wedges inside the call).

**Verdict: ready for Codex diff review.**
