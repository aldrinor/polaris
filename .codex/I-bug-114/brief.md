# Codex brief review — I-bug-114 (#551): retrieval hangs when a fetch backend never returns

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return THIS, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

You are reviewing the **brief / acceptance criteria** for GitHub issue #551.

## Codex iter-1 + iter-2 findings — resolutions (scope is now explicit)

- **iter-1 P1** — `wait_for` awaits cancellation cleanup, no hard abandon.
  Accepted. The wrapper no longer uses `wait_for` on a backend at all.
- **iter-2 P1** — a detached task on the retrieval loop is still awaited by
  `asyncio.run`'s `_cancel_all_tasks` at teardown. **Accepted as correct.**
  This brief therefore **explicitly scopes #551 to bounding the *in-flight*
  fetch** — the demo-fatal symptom (the #514 rehearsal's `policy` run froze
  ~30 min *inside retrieval*, never reaching a verdict). The narrower
  residual — a detached backend delaying `asyncio.run` *teardown* after
  artifacts are already written — is **filed as a separate issue #552** and
  is out of scope here (closing it airtight needs daemon-thread / subprocess
  isolation; that is a concurrency-model redesign, not this focused fix).
  This brief does **not** claim "guaranteed hard abandon at process level"
  — it claims "the in-flight concurrent fetch is hard-bounded; a hung
  backend can no longer freeze retrieval mid-run."
- **iter-2 P2** — a detached task's later exception is never retrieved
  (noisy "exception never retrieved"). Resolved: the detached-task
  done-callback both discards the strong ref **and** retrieves the
  exception.

## Issue #551 (I-bug-114) — acceptance, as scoped by this brief

> The **concurrent fetch fan-out** in `fetch_with_bypass` is hard-bounded:
> a single backend that never returns — *including one wedged inside a
> Playwright op* — can no longer freeze retrieval. `fetch_with_bypass`
> proceeds within a bounded wall-clock using the other backends' results.
> A regression test proves it. (The post-artifacts `asyncio.run`-teardown
> edge is #552.)

## Symptom (verified — from the #514 rehearsal live run)

A pipeline-A run hung **indefinitely inside retrieval** — the process
consumed ~40s CPU over 32 min wall, log silent ~30 min after:
```
18:02:28 CRAWL4AI: Fetching https://www.federalregister.gov/documents/2024/05/09/... (timeout=30s)
18:02:28 urllib3 Redirecting ...federalregister.gov... -> https://unblock.federalregister.gov
```
Killed manually; never reached a verdict.

## Root cause (verified — `src/tools/access_bypass.py`)

`AccessBypass.fetch_with_bypass` (line 377) runs the per-backend coroutines
(`_try_crawl4ai`, `_try_jina_reader`, `_try_firecrawl`, optional
`_try_trafilatura`) with `await asyncio.gather(*tasks, return_exceptions=True)`.
`gather` waits for **every** task; there is **no per-backend wall-clock
bound**. One wedged backend (a Playwright op on an anti-bot interstitial)
freezes the whole `gather` forever.

## The fix — a hard-bounded `_bounded_backend` wrapper (in-flight bound)

In `src/tools/access_bypass.py`:

1. **`_backend_fetch_timeout() -> float`** — env `PG_BACKEND_FETCH_TIMEOUT`,
   default `60.0` s. **`_backend_cleanup_grace() -> float`** — env
   `PG_BACKEND_CLEANUP_GRACE`, default `10.0` s. Config-driven (LAW VI).

2. **Module `set` `_DETACHED_BACKEND_TASKS`** + a `_drain_detached(task)`
   done-callback that **discards the ref AND retrieves the exception**
   (`if not task.cancelled(): task.exception()`) — no "exception never
   retrieved" noise.

3. **`_bounded_backend(label, coro, url) -> AccessResult`** — bounded by
   construction at `timeout + grace`, because it uses `asyncio.wait`
   (which **returns after its timeout regardless of task state** — it does
   NOT cancel-and-await like `wait_for`):
   ```python
   async def _bounded_backend(label, coro, url):
       timeout, grace = _backend_fetch_timeout(), _backend_cleanup_grace()
       task = asyncio.ensure_future(coro)
       done, _ = await asyncio.wait({task}, timeout=timeout)
       if task in done:
           exc = task.exception()
           if exc is not None:
               return _backend_failure(label, url, f"{type(exc).__name__}: {exc}")
           return task.result()
       # timed out — cancel, then give cleanup a BOUNDED grace window
       task.cancel()
       done, _ = await asyncio.wait({task}, timeout=grace)   # returns after grace no matter what
       if task in done:
           if not task.cancelled():
               task.exception()  # retrieve, discard
           logger.warning("[ACCESS] backend %s exceeded %.0fs — cancelled (%s)",
                           label, timeout, url[:60])
       else:
           # cleanup itself exceeded grace — detach (ref-kept + exc-drained).
           # Residual: such a task can delay asyncio.run teardown — see #552.
           _DETACHED_BACKEND_TASKS.add(task)
           task.add_done_callback(_drain_detached)
           logger.warning("[ACCESS] backend %s exceeded %.0fs + %.0fs grace — "
                           "detached (%s); see #552", label, timeout, grace, url[:60])
       return _backend_failure(label, url, f"backend_timeout_{timeout:.0f}s")
   ```
   Both `asyncio.wait` calls return after their timeout unconditionally —
   so `_bounded_backend` itself **always returns within `timeout + grace`**,
   regardless of whether the backend coroutine ever finishes. That is the
   hard in-flight bound.

4. **`_backend_failure(label, url, err)`** — tiny helper returning a failure
   `AccessResult(success=False, access_method=label, metadata={"error": err})`.

5. **At the `concurrent_tasks` build site** (lines ~467-481): wrap each
   append — `concurrent_tasks.append(_bounded_backend("crawl4ai",
   self._try_crawl4ai(url), url))`, likewise `jina`, `firecrawl`,
   `trafilatura`.

No post-`gather` change needed: `_bounded_backend` always returns an
`AccessResult` within `timeout + grace`; the existing result loop scores
the `AccessResult` candidates and returns the highest-quality winner; if
all backends fail, `fetch_with_bypass` falls through to its existing
direct-HTTP path. `gather` now completes within `timeout + grace`.

## Explicitly OUT of scope (do NOT block APPROVE on these)

- **The `asyncio.run`-teardown residual** — a detached backend delaying
  loop teardown *after artifacts are written*. Filed as **#552**. Closing
  it airtight needs daemon-thread/subprocess isolation — a concurrency-model
  redesign, deliberately not this focused in-flight fix.
- Guarding `__aenter__`/`_safe_close_crawler` inside `_try_crawl4ai`; the
  broader retrieval-robustness scope (G9, G10).

## Regression test — `tests/` (the access_bypass test module)

Proves the **in-flight** hard bound, including the cancellation-cleanup-hang
class, with no Playwright / no live URL:

- **`test_bounded_backend_returns_within_timeout_plus_grace`**: drive
  `_bounded_backend` with a coroutine that, on `CancelledError`, enters a
  *further* sleep (models a cleanup that hangs during cancellation — the
  class `wait_for` cannot escape). With `PG_BACKEND_FETCH_TIMEOUT` and
  `PG_BACKEND_CLEANUP_GRACE` set low (e.g. 1s / 1s), assert `_bounded_backend`
  returns a failure `AccessResult` (`success is False`, `metadata['error']`
  starts `backend_timeout`) within `timeout + grace + epsilon` wall-clock.
- **`test_fetch_with_bypass_survives_one_hung_backend`**: monkeypatch
  `AccessBypass._try_crawl4ai` to such a hang-on-cancel coroutine and
  `_try_jina_reader` to a fast successful `AccessResult`; with the env
  timeouts low, assert `fetch_with_bypass` returns the jina result within a
  bounded wall-clock.
- Tests set the two env vars via `monkeypatch.setenv`; the hang-on-cancel
  coroutine's secondary sleep is itself bounded (~5s) so event-loop
  teardown stays clean within the test.

## LOC estimate

~45 lines `src/tools/access_bypass.py` (4 helpers + 4 wrapped appends) +
~95 lines test ≈ **~140 LOC**. Under the 200-LOC cap.

## Files I have ALSO checked and they're clean

- `src/tools/access_bypass.py` — `_try_crawl4ai` (629), `_try_jina_reader`,
  `_try_firecrawl`, `_try_trafilatura`; `_safe_close_crawler` (267); the
  post-`gather` result loop (~519) which isinstance-filters + quality-scores
  `AccessResult` candidates.
- Callers of `fetch_with_bypass`: `src/polaris_graph/retrieval/live_retriever.py:864`
  (`await`ed in the retrieval coroutine), `agents/analyzer.py:1575`,
  `agents/searcher.py:1445`, `agents/evidence_deepener.py:926`,
  `retrieval/frame_fetcher.py:694`, `orchestration/graph.py:717` — all
  receive an `AccessResult`; a timed-out backend simply yields no winning
  candidate. No caller change needed.

## Acceptance criteria for the resulting PR

1. `src/tools/access_bypass.py` — every backend in `fetch_with_bypass`'s
   concurrent fan-out is wrapped by `_bounded_backend`, which returns within
   `PG_BACKEND_FETCH_TIMEOUT + PG_BACKEND_CLEANUP_GRACE` (defaults 60s+10s)
   **regardless of backend state** (uses `asyncio.wait`, never `wait_for`,
   on a backend); a timed-out backend logs a warning and yields a failure
   `AccessResult`; a detached task is ref-kept and exception-drained.
2. A regression test proves a backend that hangs *during cancellation
   cleanup* is bounded within `timeout + grace`, and `fetch_with_bypass`
   still returns a fast backend's result.
3. `pytest` for the access_bypass test module passes; no regression.

Return the YAML verdict block only.
