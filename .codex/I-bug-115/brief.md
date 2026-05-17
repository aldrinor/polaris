# Codex BRIEF review — I-bug-115 / GH #554: post-retrieval candidate loop hangs (no per-candidate wall-clock bound)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

This is a **brief review** — judge whether the planned fix correctly and completely
resolves GH #554, whether the acceptance criteria are right, and whether the diagnosis
is sound. You are NOT reviewing a diff yet (that is the next gate).

GH #554 — pipeline-A: a live research run hangs indefinitely in the post-retrieval
candidate-processing loop, before reaching any terminal verdict. Surfaced by the #514
OpenRouter-rehearsal `policy` prompt (2026-05-17), on a `polaris` that already includes
the #551 retrieval fan-out timeout fix. **Demo-fatal**: a single query hangs the whole
run before generation.

## 1. Diagnosis — stated with explicit confidence levels

I instrumented + reproduced per the operator's "stack-dump / instrument / reproduce"
directive. Findings, by confidence tier:

**PROVEN (rehearsal log `.codex/I-rdy-018/_live_run2.log`):** the hang is *inside*
`run_live_retrieval`'s post-`parallel_fetch` per-candidate loop
(`src/polaris_graph/retrieval/live_retriever.py:1309-1415`). The policy run's log:
```
21:36:01 [live_retriever] M-INT-1 parallel_fetch: 20 success, 0 errored, 0 timeout
21:36:02 docling ... Finished converting document tmpb29rmf_z.pdf in 43.22 sec.
21:36:04 [live_retriever] skipping content-starved evidence for '...WP202502.pdf'
21:36:07 [live_retriever] skipping content-starved evidence for '...tandfonline.com...'
<LOG DEAD-ENDS — process killed ~31 min later>
```
`parallel_fetch` returned (line 1300 log fired). The loop then printed two
"skipping content-starved" lines — that log statement is `live_retriever.py:1399-1402`,
*inside* the loop. No `[retrieval]` line ever followed (`run_honest_sweep_r3.py:1448`,
emitted only *after* `run_live_retrieval` returns). Therefore `run_live_retrieval` never
returned: it wedged in the loop, on a candidate at index ≥ 3.

**PROVEN (CPU evidence):** the hang is an **I/O block, not compute**. #554 records the
killed process used "~43 s CPU over 31 min wall". The docling line above shows a single
PDF conversion took **43.22 s** — i.e. essentially *all* the process's CPU was the
legitimate docling OCR during `parallel_fetch`; for the ~31 min after `21:36:07` the
process burned ≈0 CPU. A compute hang (regex catastrophic backtracking, an embedding
model) would peg a core. This was a thread blocked on a socket/lock.

**RULED OUT — #554's own hypothesis (`sentence-transformers` corpus-assembly compute):**
the embedding-based off-topic filter is the only `sentence-transformers` path here, and
it is **disabled** — `run_honest_sweep_r3.py:1444` passes `enable_prefetch_filter=False`.
There is no embedding/chunking compute stage between `parallel_fetch` and the loop.

**ESTABLISHED BY ELIMINATION (code-read):** within the loop body (1309-1415), the only
operation that can block on I/O is `_openalex_enrich` (`live_retriever.py:1332`, defined
at :517 — it does `httpx.Client(...).get()`). Every other per-candidate operation is
confirmed pure-CPU with bounded, simple (non-backtracking) regexes:
`fetched_side.get()` (dict lookup); `_openalex_enrich`; `_domain_of`;
`_extract_title_from_content` (regex on `content[:4000]` slices); `classify_source_tier`
(`tier_classifier.py` — rule engine, imports only stdlib, no `httpx`/`requests`/ML);
`is_content_starved`; `_build_provenance_quote` (linear `re` scan). Given locus (loop)
+ nature (I/O block), `_openalex_enrich` is the hang.

**NOT STACK-CAPTURED — honest limit:** I ran a `faulthandler`-armed live reproduction
of the policy retrieval (`scripts/_repro_554.py`, throwaway). `run_live_retrieval`
**returned cleanly in 89 s** (12 sources) — OpenAlex was responsive that run, so the
hang did not recur. The `faulthandler` dump confirmed docling OCR is the heavy-CPU path
and that the function returns normally when OpenAlex responds. The specific transient
trigger inside `_openalex_enrich` (slow response / continuous byte-trickle / DNS stall)
is therefore inferred, not stack-frozen. The repro logs are committed under
`.codex/I-bug-115/_repro_*.log` as evidence.

**Mechanism (the `httpx` subtlety):** `_openalex_enrich` uses
`httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT)` where `DEFAULT_HTTP_TIMEOUT=20.0` (a bare
float → `connect=read=write=pool=20s`). `httpx` has **no total-request timeout**: the
`read` timeout fires only when *no* byte arrives for 20 s. A fully-stalled response IS
caught at 20 s — but a response that trickles bytes < 20 s apart indefinitely
(slowloris pattern), or a wedge in a code path the phase timeouts don't cover, is never
bounded. The synchronous loop has **no per-candidate wall-clock guard**, so one wedged
`_openalex_enrich` hangs the entire run with no terminal verdict.

## 2. Planned fix

`src/polaris_graph/retrieval/live_retriever.py` only. Three layers — the fix is
**mechanism-agnostic**: it bounds the call by wall-clock regardless of what wedges
inside it.

**Layer 1 (primary) — wall-clock-bound `_openalex_enrich`.** Add
`_bounded_openalex_enrich(url, title)` that runs `_openalex_enrich` in a `daemon=True`
thread with a bounded `worker.join(timeout=deadline)` — the **exact pattern already
proven in this file** for the fetch backend (`_fetch_content`, lines 860-893). If the
worker is still alive past the deadline: log loud, abandon the daemon thread, return
`{}`. OpenAlex enrichment is *optional* — the classifier degrades gracefully to
title/content signals without it (it is already wrapped in `if enable_openalex_enrich:`
and `_openalex_enrich` itself returns `{}` on any failure). Swap the call site
`live_retriever.py:1332` to the bounded wrapper. Deadline env knob
`PG_OPENALEX_ENRICH_DEADLINE` (default `45.0` s = 2× the 20 s httpx phase timeout, which
covers the legitimate DOI-lookup + title-search-fallback double request, + margin).

**Layer 2 (defense-in-depth) — overall post-fetch-loop wall-clock budget.** Env knob
`PG_POST_FETCH_LOOP_BUDGET` (default `900.0` s). Compute `_loop_deadline` before the
loop; at the *top* of each iteration, if `time.monotonic() > _loop_deadline`, log loud
and `break` — `run_live_retrieval` then returns with whatever was classified so far, so
the run always reaches a terminal verdict. (Layer 1 already bounds each iteration; Layer
2 backstops the aggregate and any future loop addition. It does NOT interrupt a hang
*inside* an iteration — that is Layer 1's job — which is why both layers exist.)

**Layer 3 (operability) — per-candidate progress logging.** One `logger.info` at the
loop top recording `i+1/len(candidates)` + truncated URL. So that if anything in the
loop is ever slow again, the log pins the exact candidate — no more black-box hang.

**Honest fail-safe (state explicitly):** if the diagnosis is wrong in a way the
elimination missed, Layer 3's per-candidate log guarantees the *next* rehearsal run
produces a *diagnostic* hang (logs name the wedged candidate), not another black box;
and Layer 2 still drives the run to a terminal verdict for any future loop body.

**Zero-hardcode (LAW VI):** both deadlines via `os.getenv` with module-level
helper functions and a safe numeric fallback (mirrors `PG_FETCH_DEADLINE_SECONDS` at
`live_retriever.py:878`). No magic numbers.

Out of scope (deliberately, to keep the diff tight): `_serper_search` /
`_s2_bulk_search` (`httpx.Client` at `live_retriever.py:92,127`) share the same
"float timeout, no total bound" shape, but they run *before* `parallel_fetch`, are not
the #554 hang locus, and bounding them is a distinct change. Noted as a candidate
follow-up issue; NOT fixed here.

## 3. Tests (new file `tests/polaris_graph/test_post_fetch_loop_timeout.py`)

Modelled on the #551 regression test `tests/polaris_graph/test_access_bypass_backend_timeout.py`.
No network, no real OpenAlex — the hang is modelled with `time.sleep` /
`monkeypatch`.

1. `test_bounded_openalex_enrich_returns_within_deadline` — monkeypatch the inner
   `_openalex_enrich` to `time.sleep(3600)`; `PG_OPENALEX_ENRICH_DEADLINE=1`; assert
   `_bounded_openalex_enrich` returns `{}` within ~1.5 s wall-clock.
2. `test_bounded_openalex_enrich_passes_through_success` — monkeypatch inner to return
   a populated dict fast; assert the dict passes through untouched.
3. `test_bounded_openalex_enrich_converts_raise_to_empty` — monkeypatch inner to raise;
   assert `{}` returned, not propagated.
4. `test_run_live_retrieval_bounded_when_openalex_wedges` — stub `_serper_search`/
   `_s2_bulk_search` to return a few fake candidates + stub the fetch so each has
   content; monkeypatch `_openalex_enrich` to hang; `PG_OPENALEX_ENRICH_DEADLINE=1`;
   assert `run_live_retrieval` returns within bounded wall-clock AND
   `classified_sources` is non-empty (candidates still tier-classified without
   enrichment — the run reaches a terminal verdict).
5. `test_post_fetch_loop_budget_breaks_the_loop` — `PG_POST_FETCH_LOOP_BUDGET` set
   tiny; with several candidates, assert the loop breaks early and `run_live_retrieval`
   returns rather than processing all candidates.

Plus: full `pytest tests/polaris_graph/` must stay green —
`test_m12_pass12_primary_study_signal.py` (tests `_openalex_enrich` display_name
preservation — untouched, only a wrapper is added) and
`test_m_int_1_parallel_fetch_integration.py` (uses `enable_openalex_enrich=False`).

## 4. Files I have ALSO checked and they are clean

- **`_openalex_enrich` call sites** — `grep -rn _openalex_enrich src/ scripts/ tests/`:
  the only *direct* call is `live_retriever.py:1332` (the loop). `run_honest_sweep_r3.py:1443,1615`,
  `run_live_honest_cycle.py:136`, `v28_retrieval_preflight.py:123` pass
  `enable_openalex_enrich=True` as a `run_live_retrieval` *parameter* — they do not call
  `_openalex_enrich` directly; the wrapper swap is internal to `run_live_retrieval` and
  transparent to them.
- **`run_honest_sweep_r3.py:1436-1530`** (driver, `run_live_retrieval` call → `[corpus]`
  write) — pure CPU between the call and `live_corpus_dump.json`; not a hang site.
- **`classify_source_tier` (`tier_classifier.py:921`)** — rule engine; module imports
  only `logging`/`re`/`dataclasses`/`enum`/`typing`/`urllib.parse`; no network/ML.
- **Loop CPU helpers** `_domain_of`, `_extract_title_from_content`,
  `is_content_starved`, `_build_provenance_quote` — scanned: no I/O, no `while`, simple
  bounded regexes (no catastrophic-backtracking shape).
- **`_fetch_content` (`live_retriever.py:814-915`)** — already wall-clock-bounded by the
  `PG_FETCH_DEADLINE_SECONDS` daemon-thread join (the pattern Layer 1 reuses); the #551
  fix bounds the fetch fan-out. Not re-touched.
- **`scripts/_repro_554.py`** — throwaway diagnostic harness, deleted before commit 1;
  never committed to `src/`.

## 5. Acceptance criteria (GH #554)

- Post-retrieval candidate loop honours a hard wall-clock bound — per-candidate
  (Layer 1) and overall (Layer 2); a wedged `_openalex_enrich` is abandoned, the
  candidate is still classified, and the run reaches a terminal verdict. ✔ planned
- A regression test exercises a hung enrich call and asserts the run is bounded. ✔ test 4
- `pytest tests/polaris_graph/` green; ≤200-LOC diff; LAW VI (no hardcode). ✔ planned
- Codex APPROVE on brief, then on diff.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

### Specific questions for the reviewer
1. Is the diagnosis sound — locus (loop, log-proven), nature (I/O, CPU-proven),
   `_openalex_enrich` by elimination — and is the "not stack-captured" honesty
   adequate, or do you require a second probabilistic live repro before APPROVE?
2. Is the daemon-thread + bounded-join pattern (reused verbatim from `_fetch_content`)
   the right bound here, vs. e.g. switching `_openalex_enrich` to an explicit
   `httpx.Timeout` — given that no `httpx` timeout config bounds *total* request time?
3. Are `PG_OPENALEX_ENRICH_DEADLINE=45 s` and `PG_POST_FETCH_LOOP_BUDGET=900 s`
   reasonable defaults?
4. Is Layer 2 worth its ~6 lines given Layer 1 already bounds each iteration, or is
   it scope creep?
