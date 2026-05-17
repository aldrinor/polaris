# Codex DIFF review — I-bug-115 / GH #554: wall-clock-bound the post-retrieval candidate loop

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

The **code diff** for GH #554. The brief was APPROVE'd by you at iter 1
(`.codex/I-bug-115/codex_brief_verdict.txt` — diagnosis sound, daemon-thread
bound is the right mechanism, defaults reasonable; 2 P2s, both folded in).

- **Diff to review:** `.codex/I-bug-115/codex_diff.patch`
  — canonical-diff-sha256 `fe3d1803cfd775f80bc48d98bcf0e505d9dee7e561fe9e3e52348fdc851e9b81`
  (trailer line; sha is over the patch body above it).
- **Brief (design + diagnosis):** `.codex/I-bug-115/brief.md`
- **Claude architect audit:** `outputs/audits/I-bug-115/claude_audit.md`
- **Scope:** 2 files, +257 / -3. `src/polaris_graph/retrieval/live_retriever.py`
  (+106/-3, 109-line production CODE diff); `tests/polaris_graph/test_post_fetch_loop_timeout.py`
  (+151, new).

## 1. What changed

`run_live_retrieval`'s synchronous post-`parallel_fetch` candidate loop could
hang indefinitely on a wedged `_openalex_enrich` call (httpx bounds each
request *phase*, not total request time). Fix — `live_retriever.py` only:

- **`_env_float` / `_env_int`** — positive-numeric env-knob helpers with safe
  fallbacks (LAW VI).
- **`_bounded_openalex_enrich(url, title, stats=None)`** — runs `_openalex_enrich`
  in a `daemon=True` thread; `worker.join(timeout=PG_OPENALEX_ENRICH_DEADLINE)`
  (default 45 s). On timeout: `stats["enrich_timeouts"] += 1`, warn-log, return
  `{}`, abandon the daemon thread. On raise: debug-log, return `{}`. On success:
  pass the dict through. Reuses the `_fetch_content` daemon-thread+bounded-join
  pattern (same file, ~lines 860-893).
- **Loop call-site swap** — `oa = _openalex_enrich(...)` → `_bounded_openalex_enrich(...)`,
  guarded by `enable_openalex_enrich and not _enrich_disabled`.
- **Fail-fast** — after `PG_OPENALEX_ENRICH_FAILFAST` (default 3) enrich
  timeouts, `_enrich_disabled = True`; the loop stops attempting enrichment
  (prevents abandoned daemon threads accumulating — your brief P2-2).
- **Overall loop budget** — `_loop_deadline = time.monotonic() + PG_POST_FETCH_LOOP_BUDGET`
  (default 900 s); checked at the top of each iteration; on exceed → warn-log +
  `break` (`run_live_retrieval` returns with what was classified).
- **Per-candidate progress logging** — `logger.info` at the loop top.

## 2. Verification done

- `tests/polaris_graph/test_post_fetch_loop_timeout.py` — **5/5 pass** (7.3 s):
  bounded-enrich hang→`{}`; success pass-through; raise→`{}`;
  `run_live_retrieval` bounded when every enrich wedges; loop-budget break
  (deterministic per your brief P2-1 — real 0.3 s per-candidate delay).
- **197/197 pass** across all 12 test files importing `live_retriever` /
  `run_live_retrieval` (the exact blast radius of a 3-edit additive change).
- Full `tests/polaris_graph/` collects **4619 tests** (`PYTHONPATH='src;.'`); 1
  pre-existing collection error (`test_demo_smoke.py` — missing
  `static_accounts.yaml`, an auth-substrate env dependency unrelated to this
  change).

## 3. Red-Team checklist — please verify

1. **Wall-clock bound is real** — does `_bounded_openalex_enrich` actually
   return within `PG_OPENALEX_ENRICH_DEADLINE` when `_openalex_enrich` never
   returns? (daemon thread + `join(timeout=)` — the join returns; the thread is
   abandoned; is anything still awaited?)
2. **Fail-fast counter** — `_enrich_stats["enrich_timeouts"]` is incremented by
   the wrapper and read by the loop. Off-by-one / threshold-comparison correct?
   Does `_enrich_disabled` correctly skip enrichment for ALL remaining
   candidates once tripped?
3. **Loop budget** — checked at iteration top, BEFORE the per-candidate work.
   Does the run still reach a terminal verdict (return `LiveRetrievalResult`)
   after a `break`? Are partially-processed candidates consistent (no
   half-populated `classified_sources` / `evidence_rows`)?
4. **Happy path undisturbed** — a fast `_openalex_enrich` result must pass
   through `_bounded_openalex_enrich` unchanged (no dropped fields). Confirm.
5. **No regression** — `_openalex_enrich` itself is untouched; the call site is
   the only behavioural change. Any caller / test that depends on synchronous
   timing or the exact call?
6. **LAW VI / hygiene** — 3 env knobs, no magic numbers, no `except: pass`,
   no silent downgrade (timeouts are logged loud at WARNING).
7. **Tests genuinely exercise the hang** — do tests 1 & 4 actually model an
   unbounded hang (`time.sleep(3600)`), and would they FAIL against the
   pre-fix code? Is test 5's loop-budget break deterministic?

## 4. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
