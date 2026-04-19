---
verdict: CONDITIONAL
pass: 4
commit: 81b18de
prior_pass_3_verdict_still_holds: false
new_blockers: 0
new_mediums: 4
rationale: |
  The threaded AccessBypass wrapper addresses the Windows SelectorEventLoop/Playwright failure and the fetch-specific regression tests pass. I would not mark this ready unconditionally because _fetch_content waits on worker.join() with no deadline, so a wedged browser startup or cleanup can still hang an 8-query sweep indefinitely. The smoke evidence is directionally strong for retrieval, but weaker than claimed: the tech artifact has 12/13 evaluator rules passing, not 13/13.
---

## 1. Threaded-bypass pattern review

The wrapper in `src/polaris_graph/retrieval/live_retriever.py:254-337` is the right shape for the Windows event-loop bug: each URL constructs `AccessBypass()` inside a fresh daemon thread and runs `fetch_with_bypass()` under `asyncio.run()` in that thread (`live_retriever.py:293-304`). The five regressions in `tests/polaris_graph/test_fetch_access_bypass_wiring.py` cover sync invocation, invocation from an existing async context, exception fallback, S2 no-fallback behavior, and the `PG_DISABLE_ACCESS_BYPASS` opt-out; they pass locally (`5 passed`).

There is hidden shared provider state outside the per-thread `AccessBypass` instance. `src/tools/access_bypass.py` has module-level Jina, Firecrawl, and Crawl4AI circuit breaker/counter state (`_jina_semaphore`, `_jina_consecutive_failures`, `_firecrawl_last_request_time`, `_crawl4ai_available`, etc. at lines 55-80 and 92-93). This is acceptable for the current sequential fetch loop in `run_live_retrieval()` (`live_retriever.py:607-613`) but is not a fully thread-safe design if future work makes multiple `_fetch_content()` calls concurrently.

The fallback cascade in `_fetch_content()` is mostly correct for the documented policy. Import failure and worker exceptions fall back to naive httpx (`live_retriever.py:277-284`, `306-318`). S2 landing pages return `success=False` from `AccessBypass.fetch_with_bypass()` (`access_bypass.py:331-340`), and the wrapper returns `("", False)` without naive fallback (`live_retriever.py:321-328`), matching the regression at `test_fetch_access_bypass_wiring.py:120-145`.

The main correctness gap is the unbounded `worker.join()` at `live_retriever.py:304`. AccessBypass has many internal timeouts, including Crawl4AI `wait_for(..., timeout=timeout_seconds + 10)` (`access_bypass.py:673-678`) and aiohttp timeouts, but not every failure mode is covered: browser startup (`__aenter__`), browser cleanup (`__aexit__`), imports, native extension work, or subprocess wedges can still block the worker. Reproducer outline: monkeypatch `src.tools.access_bypass.AccessBypass.fetch_with_bypass` to `async def` await an unset `asyncio.Event()`, call `_fetch_content()`, and it never returns because the caller joins without a timeout.

`asyncio.get_event_loop()` calls inside AccessBypass are not an immediate Python 3.10+ problem in this path because the observed calls are inside coroutines already running under `asyncio.run()` (`access_bypass.py:965`, `1014`). A third-party library calling `get_event_loop()` in the worker thread before `asyncio.run()` establishes a running loop would still be risky, but I did not find that pattern in the local wrapper or `AccessBypass.__init__()`.

## 2. Regression/resource concerns

The brief says this spawns 20 threads per primary pass plus 15 per expansion. In the current implementation that is sequential, not concurrent: `run_live_retrieval()` loops candidates and calls `_fetch_content()` one URL at a time (`live_retriever.py:607-613`). So the Windows stack reservation concern is low for today; the process creates many short-lived threads over a run, but does not hold 20 or 35 worker stacks at once.

The real resource cost is browser cold-start. `AccessBypass._try_crawl4ai()` creates a fresh `AsyncWebCrawler` and enters it for each URL (`access_bypass.py:641-643`), so successful Crawl4AI attempts can imply repeated Chromium/Playwright startup and teardown. The smoke timings, 171.0s for clinical and 139.9s for tech retrieval, are consistent with this being a throughput bottleneck.

The module-level provider state would become a race if a future async refactor runs multiple `_fetch_content()` calls concurrently. The most concrete example is `_jina_semaphore`: it is lazily created as a module-level `asyncio.Semaphore` (`access_bypass.py:1088-1094`). With the current sequential loop it is unlikely to bind across contended event loops; with true concurrent worker threads it can become loop-affine under contention or race during initialization.

## 3. Smoke-artifact integrity

Both smoke manifests report `status: success` and `release_allowed: true`. Clinical retrieval is populated as `pre_filter=300`, `fetched=15`, `failed=5`, with api call subcounts all integers. Tech retrieval is populated as `pre_filter=46`, `fetched=19`, `failed=1`, with api call subcounts all integers. I saw no `None` drift in these retrieval fields.

Late-bound citations are resolved. Clinical `report.md` cites `[1]..[4]`, and `bibliography.json` contains four numbered entries with real URLs. Tech `report.md` cites `[1]..[12]`, and `bibliography.json` contains twelve numbered entries with real URLs. Both `qwen_judge_output.json` files have no top-level `error` key and have `parse_ok: true`.

The rule-check claim in the brief is not accurate for both runs. Clinical has 13/13 rule checks passing. Tech has `evaluator_rule_pass: 12`, `evaluator_rule_fail: 1` in `manifest.json`, and `evaluator_rule_checks.json` marks PT13 false for unhedged "best" language. `run_log.txt` also reports `rule_checks=12/13 pass`. The eval gate still passed, but the smoke evidence is weaker than "13/13 in both runs."

The mandated full test command did not reproduce the commit message's suite result in this working tree: `python -m pytest tests/polaris_graph/ -q` ended with `2 failed, 389 passed, 3 warnings, 23 errors`. The fetch-specific regression file passed, so I do not count this as a fetch-wiring blocker, but the broad suite is not clean in the current local state.

## 4. Latent issues

Medium 1: add a fetch-level deadline around the worker thread. A practical guardrail is `worker.join(timeout)` with a configured timeout slightly above the AccessBypass worst-case path, then return `("", False)` or naive fallback with a clear `fetch_timeout` log if the worker is still alive. Because the thread is daemonized, this will let the pipeline move on rather than hanging the sweep forever.

Medium 2: the clinical report is content-starved. The generator verified only 4 sentences and dropped 20, keeping 3 of 4 outline sections with only 146 words. The missing outline section is `Comparative`: it appears in `manifest.json` under `generator.outline_sections`, but there is no `### Comparative` section in `report.md`. This strict verification is a hallucination-control strength, but it is also a research-report thinness risk.

Medium 3: the tech smoke has a passed release gate despite a failed rule check. PT13 failed on unhedged "best" language, yet `evaluator_gate.release_allowed` remains true. That may be intentional if PT13 is non-blocking, but the audit claim should not cite 13/13 rule checks for this run.

Medium 4: the tier distributions in both smoke runs have material deviations. Clinical is 40% T7 and tech is 70% T4, both recorded as `material_deviation: true`. This does not undercut the fetch wiring fix, but it does mean an 8-query sweep should be read as a pipeline reliability sweep, not as proof that output quality is consistently high.

## 5. Final verdict

CONDITIONAL.

The threaded wrapper is a sound fix for the specific Windows event-loop failure and the two live smokes show a major retrieval improvement over 2/20. I would run the 8-query sweep only after adding a fetch-level worker join timeout or with an explicit external watchdog around the sweep command. Without that guardrail, one wedged Crawl4AI/Playwright worker can still block the pipeline indefinitely.
