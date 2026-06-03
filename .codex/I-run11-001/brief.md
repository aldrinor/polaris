```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-run11-001 — Parallelize the 4-role per-claim loop (Path B SAFE concurrency)

GitHub Issue: #1042. This brief covers the DIFF for #1042.

## Output schema (required)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context / why

`run_four_role_evaluation` (`src/polaris_graph/roles/sweep_integration.py`) runs the per-claim
Mirror -> Sentinel -> Judge pipeline SEQUENTIALLY. At the benchmark stage (xhigh reasoning,
minutes/claim) the seam does not finish within the run-time budget; run 10 died on exactly this
operational failure mode. Codex chose Path B (`.codex/I-run11-seam/codex_decision.txt`):
parallelize the per-claim COMPUTE, keep all reduction + persistence deterministic on the parent
thread in input order. The naive-B trap Codex flagged is "assume `copy_context` makes
`_RUN_COST_CTX` shared; it does not." This diff does NOT make that mistake.

## Verified ground truth (so you VERIFY, not discover)

1. `run_claim_pipeline` (role_pipeline.py:282) constructs a FRESH `RecordingTransport(transport)`
   per claim -> per-claim records are isolated; no shared mutable record list across claims.
2. Cost accounting lives INSIDE `RecordingTransport.complete()` (role_pipeline.py:174-175):
   `_orc._add_run_cost(compute_role_call_cost(...))` then `_orc.check_run_budget(0)`.
   `_RUN_COST_CTX` is a `contextvars.ContextVar[float]` (openrouter_client.py:88). In a worker
   thread under `copy_context()`, the ContextVar is ISOLATED — the worker's spend does NOT
   converge into the parent counter. Therefore the worker resets its own counter
   (`reset_run_cost()`), runs the pipeline, and returns `current_run_cost()` as the per-claim
   delta; the PARENT re-adds the delta (`_add_run_cost`) and enforces the cap
   (`check_run_budget(0)`) on the SINGLE parent counter holding `generator_spend + verifier_spend`.
3. The per-claim reduction makes NO LLM call: `d8_rows.append(result.d8_row)`;
   `all_records.extend(result.records)`; `final_verdicts[claim_id]=result.final_verdict`;
   build `role_call_log` from `result.records`; on VERIFIED ->
   `internal_ledger.covered_element_ids.update(claim.covered_element_ids)`; `kg_store.write_claim(...)`.
4. Reasoning sink (`_REASONING_SINK_CTX` / `_capture_reasoning_trace`, openrouter_client.py:116-188)
   is touched ONLY by the GENERATOR path (`OpenRouterClient.generate`/`reason`). The verifier
   transports (`OpenRouterRoleTransport`, `OpenAICompatibleRoleTransport`) POST via httpx directly
   and NEVER call `set_reasoning_sink`/`_capture_reasoning_trace`. So the reasoning sink needs NO
   per-worker isolation. (Verified by grep: no reasoning-sink symbol appears in roles/.)
5. pathB capture `_SINK` (pathB_capture.py:48) is a ContextVar holding a REFERENCE to a SHARED
   list (docstring L45-47: shared by design so child-task appends land at the parent for the M4
   served==pinned gate). `copy_context()` shares the list BY REFERENCE; `list.append` is
   GIL-atomic; the M4 consumer (`scripts/dr_benchmark/pathB_run_gate.py`) uses `call_id` only as
   an error-message LABEL, never as a join/order key. So the sink is left SHARED, NOT isolated —
   isolating it per worker would DROP every verifier capture from the parent gate. The only race
   is `call_id=f"{role}-{len(sink)}"` producing non-unique suffixes, which is observational.
6. The deterministic audit ordering that matters (`four_role_role_calls.jsonl`) is built on the
   PARENT thread from `result.records` IN CLAIM ORDER — NOT from the pathB capture sink. So
   `role_call_log` order is deterministic regardless of capture call_id collisions.

## The change

File: `src/polaris_graph/roles/sweep_integration.py` only (+ a new test file).

1. Add stdlib imports `concurrent.futures`, `contextvars`, `os`; import the openrouter_client
   cost functions (`reset_run_cost`, `current_run_cost`, `_add_run_cost`, `check_run_budget`,
   `BudgetExceededError`).
2. Module config: `_CLAIM_WORKERS = max(1, int(os.getenv("PG_FOUR_ROLE_CLAIM_WORKERS", "6")))`.
3. `_compute_one(idx, claim)`: `ctx = contextvars.copy_context()`; inside `ctx.run`:
   `reset_run_cost()`, run `run_claim_pipeline(...)`, return `(idx, result, current_run_cost())`.
4. Compute dispatch: if `_CLAIM_WORKERS == 1` or `len(claims) <= 1` -> SEQUENTIAL, calling
   `run_claim_pipeline` DIRECTLY (NO reset/add — byte-equivalent to today; the live per-call
   budget inside RecordingTransport is preserved). Else `ThreadPoolExecutor(max_workers=...)`,
   submit all, collect via `as_completed`, store by INDEX into `computed[idx]`. A worker
   exception PROPAGATES (fail closed; no `except: pass`).
5. Reduce on the parent in input order via `zip(claims, computed)`:
   - PARALLEL path only: `_add_run_cost(delta)` then `check_run_budget(0)` (parent enforces the
     cap; `BudgetExceededError` propagates to the existing abort path — never caught here).
   - Same byte-identical reduction (d8_rows, all_records, final_verdicts, role_call_log,
     coverage-on-VERIFIED, kg_store.write_claim).
   - INCREMENTAL `four_role_role_calls.jsonl` write after EACH claim is reduced (whole file
     rewritten in claim order — monitorable mid-run); keep the existing final write (idempotent).
6. `kg_store.write_claim` stays PARENT-only inside the same `try/finally` that closes kg_store.
   `BudgetExceededError` from the parent `check_run_budget` is fine inside the try/finally — the
   finally closes kg_store and the error propagates.

## Iter-2 changes (Codex diff-gate iter-1 REQUEST_CHANGES → applied)

Codex iter-1 (`codex_diff_audit.txt`) returned REQUEST_CHANGES with 2 P1 + 3 P2. All applied in
`sweep_integration.py` (`_compute_claim_results` + the reduction loop in `run_four_role_evaluation`):

1. **P1.2 (CRITICAL — context copied in the wrong thread):** `copy_context()` was taken INSIDE the
   worker, snapshotting the worker's EMPTY default context, so the parent Path-B capture sink
   (`pathB_capture._SINK` / `_ROLE`, registered by `pathB_runner.gate_around_question` on the PARENT)
   was ABSENT in workers and verifier capture no-oped (post-run completeness fails when workers>1).
   FIX: the per-claim snapshot is now taken ON THE PARENT at submit —
   `pool.submit(_compute_one, idx, claim, contextvars.copy_context())`. Each claim gets its OWN copy;
   the worker calls `worker_ctx.run(_run)`; inside `_run`, `reset_run_cost()` isolates THIS claim's
   cost in the copied ctx, then `run_claim_pipeline(...)`, then returns `current_run_cost()`.
2. **P1.1 (budget enforced too late):** the parallel branch no longer drains-all-then-charges. It now
   iterates `as_completed`; per completed future `_add_run_cost(delta)` + `check_run_budget(0)`, so a
   cap breach raises after only ~(workers-in-flight) claims have spent, not all N. On
   `BudgetExceededError` / any worker exception the pool is `shutdown(wait=False, cancel_futures=True)`
   then re-raised (P2.2 cancel-on-fail). The pool is managed MANUALLY (try/except/finally), NOT `with`.
   The now-duplicated cost re-add was REMOVED from the reduction loop (it would double-count);
   `cost_delta` is kept in the returned tuple for audit only. Reduction stays parent-only, input-order,
   for d8_rows / all_records / final_verdicts / role_call_log / coverage / kg / incremental-log only.
3. **P2.3 (mid-compute monitorability):** the `as_completed` loop writes
   `run_dir/four_role_compute_progress.json` = `{"done": k, "total": n}` after each completion (parent
   only) so a hung COMPUTE is visible on disk during compute.
4. **P2.1 (aborted-run cost under-accounting):** documented as parity with the seam-timeout wrapper
   (`run_honest_sweep_r3.py` ~L4587-4596) — a worker's partial spend on an aborted run is not
   reconciled; fail-closed termination outranks exact accounting. Not over-engineered.

Two tests ADDED to `tests/roles/test_seam_parallel.py`: `test_pathb_sink_visible_in_workers` (proves
P1.2 — parent sink receives ALL workers' captures; FAILS with copy_context inside the worker) and
`test_cap_trip_is_bounded_in_flight` (proves P1.1 — a cumulative cap trip runs a bounded prefix, not
all N; FAILS with the old drain-all behavior). Existing 6 kept green → 8/8; `tests/roles/` 310/310.

## Acceptance criteria (tests in tests/roles/test_seam_parallel.py)

- (a) output order (final_verdicts iteration / d8_rows / role_call_log) == INPUT order regardless
  of completion order. Fake transport sleeps INVERSELY to index (claim 0 longest) with workers >=
  len(claims) so completion order reverses input order; assert input order preserved.
- (b) parallel total cost == sequential total cost AND the SAME `PG_MAX_COST_PER_RUN` cap trips
  (`BudgetExceededError`) at the same accumulated spend. Tipping cost is on the LAST pipeline call
  of the tripping claim (Judge runs last) so sequential mid-claim trip and parallel boundary trip
  fire at the same total = sum(1..K).
- (c) coverage credited ONLY on VERIFIED.
- (d) role_call_log complete (one block of records per claim, in order).
- (e) `PG_FOUR_ROLE_CLAIM_WORKERS=1` path matches the multi-worker result.

## Constraints (HARD)

- Do NOT change `run_claim_pipeline` or `RecordingTransport`, D8 policy, coverage math, or KG store.
- Sequential path (`PG_FOUR_ROLE_CLAIM_WORKERS=1`) byte-equivalent to today.
- No `except: pass`. Fail closed on any worker error.
- LAW VI: worker count from env only.

## Files I have ALSO checked and they're clean

- `src/polaris_graph/roles/role_pipeline.py` — RecordingTransport per-claim fresh; cost chokepoint
  unchanged; NOT modified.
- `src/polaris_graph/roles/role_transport.py` — data contracts; NOT modified.
- `src/polaris_graph/roles/openrouter_role_transport.py` + `openai_compatible_transport.py` —
  verifier transports; do NOT touch the reasoning sink; NOT modified.
- `src/polaris_graph/llm/openrouter_client.py` — cost ContextVars + reasoning sink; verified
  semantics; NOT modified.
- `src/polaris_graph/benchmark/pathB_capture.py` — shared-by-design `_SINK`; NOT modified.
- `scripts/dr_benchmark/run_gate_b.py`, `scripts/run_honest_sweep_r3.py`,
  `scripts/dr_benchmark/offline_e2e.py` — seam consumers; depend only on the unchanged
  `FourRoleEvaluationResult` fields + the unchanged `four_role_role_calls.jsonl`; NOT modified.
- `scripts/dr_benchmark/pathB_run_gate.py` — M4 consumer; uses `call_id` as an error label only.
- `tests/roles/test_sweep_integration.py`, `tests/roles/test_four_role_budget_cap.py`,
  `tests/dr_benchmark/test_gate_b_seam.py` — existing 4-role suites; must still pass unchanged.
