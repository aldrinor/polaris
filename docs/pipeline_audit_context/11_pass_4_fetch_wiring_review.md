# POLARIS full-audit pass 4 — fetch wiring review (BUG-FETCH-R8d)

You are re-auditing POLARIS after pass 3's READY verdict, because a
live smoke run on pipeline A revealed a real-world defect that
pass 3 did not catch: the AccessBypass wiring I committed at
`d81bc8e` was silently broken on Windows.

## Context — what happened

Pass 3 declared READY. The user then ran a live smoke test:

```
python -m scripts.run_honest_sweep_r3 --only clinical_tirzepatide_t2dm \
       --out-root outputs/smoke_retrieve_v2
```

Result: `retrieval.fetched=2 / 20 = 10%` — almost every URL failed.
Status: `abort_corpus_inadequate`. Cost: $0.00.

Root cause diagnosis and fix sequence (commit `81b18de`):

1. **v1** (pre-R8d, historical): live_retriever used only raw `httpx`
   with no `Accept-Encoding` header. Academic sites served brotli-
   compressed content → 19/20 failures.
2. **v2** (commit `d81bc8e`, pass 3's READY state): I wired AccessBypass
   via `asyncio.new_event_loop() + run_until_complete`. This works on
   macOS/Linux but **silently fails on Windows** because `new_event_loop()`
   creates a `SelectorEventLoop` and Playwright/Crawl4AI requires a
   `ProactorEventLoop`. The coroutine at line 289 never got awaited,
   was garbage-collected at line 299 (naive fallback), and stderr
   showed `RuntimeWarning: coroutine 'AccessBypass.fetch_with_bypass'
   was never awaited`.
3. **v3** (experimental, not committed): switched to `asyncio.run()`.
   Primary loop worked (8/9 standalone). But the R-6 expansion pass
   crashed with `RuntimeError: asyncio.run() cannot be called from a
   running event loop` — Crawl4AI leaves background tasks from the
   first call that keep a prior loop "running".
4. **v4** (commit `81b18de`, current): wrap AccessBypass in a dedicated
   daemon thread per URL. Each fetch gets its own `asyncio.run()`
   regardless of whether the caller is sync or inside an event loop.

## Validation I ran

Two live pipeline runs with the threaded wrapper:

| Domain | fetched/20 | adequacy | sections_kept | words | eval_gate | status |
|---|---|---|---|---|---|---|
| clinical_tirzepatide_t2dm | 15 (75%) | proceed 7/7 | 3/4 | 146 | pass | success |
| tech_rag_architectures_2024 | 19 (95%) | proceed 7/7 | 4/4 | 529 | pass | success |

Test suite: `414 passed` (+5 regression tests in
`tests/polaris_graph/test_fetch_access_bypass_wiring.py`).

Artifacts:
- `outputs/smoke_retrieve_v4/clinical/clinical_tirzepatide_t2dm/{manifest.json,report.md}`
- `outputs/smoke_retrieve_v5/tech/tech_rag_architectures_2024/{manifest.json,report.md}`

## Your mandate — critical review

### 1. Is the threaded-bypass pattern correct?

Read `src/polaris_graph/retrieval/live_retriever.py` lines 253-325
(the new `_fetch_content`). Answer:

- Is the threading wrapper thread-safe? AccessBypass instances are
  constructed inside the thread (not shared). Any hidden shared state?
- Is the fallback cascade correct? S2 landing pages skip to
  `("", False)` (not naive fallback), all other failure modes do fall
  back to naive httpx.
- Does `worker.join()` without timeout risk hanging the pipeline if
  Crawl4AI wedges? We don't currently set a timeout — is that a gap?
- What happens if `asyncio.run()` inside the worker thread itself
  tries to invoke `asyncio.get_event_loop()` (Python 3.10+ deprecation)?

### 2. Regressions from the threading change

- `run_live_retrieval` is still sync, so the thread-per-URL pattern
  is a mostly-equivalent refactor from an external perspective.
- But we now spawn 20 threads per primary pass + 15 per expansion.
  Is that memory pressure concerning on Windows where threads cost
  ~1MB each? (Answer: probably fine, but flag it.)
- Crawl4AI browser instances: does each thread spin up a fresh
  Chromium process? If so, the real bottleneck may now be Playwright's
  per-thread browser cold-start, not the event loop.

### 3. Smoke-artifact integrity check

Open the two artifact trees and verify:

- `manifest.json` has `status=success` and `release_allowed=true` in
  both runs
- `manifest.retrieval.{pre_filter, fetched, failed, api_calls}` are
  all populated with ints (no None drift)
- `report.md` has citations `[1]..[N]` resolved to real URLs in
  `bibliography.json` (late-binding)
- `evaluator_rule_checks.json` shows `rule_check_pass_count=13`
- `qwen_judge_output.json` shows no `error` key

### 4. Latent issues you can flag

Anything that would show up if we now ran all 8 queries:

- Generator drops 20 sentences of 24 on clinical — strict_verify is
  very aggressive. Is that a correctness strength or a content-
  starvation risk? (The report still passes eval_gate, but is 146
  words too thin for a "research report"?)
- Clinical kept 3/4 sections (dropped 1). Which section was dropped
  and why (look at the run_log.txt)?
- Pipeline A does not currently use a fetch-level deadline per URL.
  Crawl4AI itself has internal timeouts, but if one URL wedges
  indefinitely, the daemon thread will block `join()` forever. Worth
  adding a thread-join timeout?

### 5. Ready-or-not?

One of:
- **READY-FOR-8-QUERY-SWEEP**: threaded wrapper is sound, smoke
  evidence convincing, any mediums are acceptable.
- **NOT-READY**: something above is a real blocker.
- **CONDITIONAL**: ship only with a specific guardrail (e.g., thread
  join timeout).

## Output

Write to `outputs/codex_findings/full_audit_pass_4/findings.md`
with frontmatter:

```yaml
---
verdict: READY-FOR-8-QUERY-SWEEP | NOT-READY | CONDITIONAL
pass: 4
commit: 81b18de
prior_pass_3_verdict_still_holds: true | false
new_blockers: <int>
new_mediums: <int>
rationale: |
  <2-4 sentence executive summary>
---
```

Followed by:
- `## 1. Threaded-bypass pattern review`
- `## 2. Regression/resource concerns`
- `## 3. Smoke-artifact integrity`
- `## 4. Latent issues`
- `## 5. Final verdict`

## Authentication

OAuth (chatgpt). No API-key burn.

## Expected duration

15-25 minutes.

---

Start:

```
git log --oneline 427b6ff..HEAD | head -10
git show 81b18de --stat
python -m pytest tests/polaris_graph/ -q 2>&1 | tail -3
```

Then walk sections 1-5.
