# I-run11-001 (#1042) — Claude architect line-by-line audit

Diff: `src/polaris_graph/roles/sweep_integration.py` (+ new `tests/roles/test_seam_parallel.py`).
Design: Codex Path-B SAFE (`.codex/I-run11-seam/codex_decision.txt`). Brief: `.codex/I-run11-001/brief.md`.

Audited against the FIVE acceptance criteria + the HARD constraints. Each verdict cites the exact
code span (file:line) that establishes it.

## Constraint audit (HARD)

- **Do NOT change `run_claim_pipeline` / `RecordingTransport` / D8 / coverage / KG.** VERIFIED.
  The diff touches `sweep_integration.py` ONLY. `git diff --stat` shows no edit to `role_pipeline.py`,
  `release_policy.py`, `verified_claim_graph.py`, or any transport. The reduction body
  (sweep_integration.py:434-487) is byte-identical to the pre-#1042 loop except the two added lines
  (cost re-add guard 430-432, incremental log write 456).
- **Sequential path byte-equivalent.** VERIFIED. `_CLAIM_WORKERS == 1 or n <= 1` (sweep_integration.py:270)
  calls `run_claim_pipeline` DIRECTLY (272-282) with NO copied context and NO `reset_run_cost`, so
  `RecordingTransport.complete()` enforces the live per-call budget on the parent counter EXACTLY as
  before, and returns `cost_delta=None` (283) so the parent reduction does NOT re-add (430). Proven
  empirically: the entire existing 34-test 4-role suite passes with `PG_FOUR_ROLE_CLAIM_WORKERS=1`.
- **No `except: pass`; fail closed.** VERIFIED. The parallel collector uses `future.result()` (293),
  which RE-RAISES any worker exception; there is no `try/except` around it. The only `try/finally`
  (419/489) has NO `except` — it closes kg_store then the error propagates. A dropped future fails
  loud via the `RuntimeError` guard (297-302). Grep of the diff for `except` returns only the
  pre-existing `mirror_result is not None` ternaries (no new exception handling).
- **LAW VI: worker count from env only.** VERIFIED. `_CLAIM_WORKERS = max(1, int(os.getenv(
  "PG_FOUR_ROLE_CLAIM_WORKERS", "6")))` (sweep_integration.py:~85). No other tunable is hard-coded;
  `PG_MAX_COST_PER_RUN` is unchanged.

## Acceptance-criteria audit

### (a) output order == INPUT order regardless of completion order — VERIFIED
- Compute collects results BY INDEX into `computed[idx]` (sweep_integration.py:294); `as_completed`
  drives ONLY the index assignment, never any reduction.
- Reduction iterates `zip(claims, computed)` (423) — strictly input order. `final_verdicts`
  (dict, insertion-ordered), `d8_rows` (append, 434), `all_records` (extend, 435), `role_call_log`
  (append, 441) all follow that order.
- Test `test_output_order_is_input_order_under_reversed_completion`: 4 workers, claim-0 sleeps
  LONGEST (delay `0.05*(n-i)`) so completion order REVERSES input order; asserts `final_verdicts`
  keys == input order AND the role-call log's per-claim blocks are contiguous and in input order
  (`groupby` block-id check). PASS.

### (b) parallel total cost == sequential total cost AND same cap trip — VERIFIED (split across two tests)
- Cost re-add: parent `_add_run_cost(cost_delta)` + `check_run_budget(0)` (431-432), gated on
  `cost_delta is not None` (430) so the sequential path (already accounted) is never double-counted.
- `test_parallel_cost_equals_sequential_cost_under_cap`: no cap pressure, 3 claims each with a modest
  Judge usage; asserts the TOTAL accounted spend is identical (`approx rel=1e-9`) between workers=1
  and workers=4 — proves no double-count and no drop. PASS.
- `test_parallel_and_sequential_trip_cap_at_same_total`: n=2, cap 0.20, parent pre-seed 0.10, tipping
  Judge usage on the LAST claim's LAST call. Sequential trips LIVE at claim-1's Judge; parallel trips
  at claim-1's parent boundary; both report 0.23881 (`approx rel=1e-9`). The tip on the tripping
  claim's last call is what makes the totals equal — the exact "mid-claim spread" trap is avoided.
  PASS.
- HONEST SCOPE (stated in the test docstring): criterion (b)'s "same accumulated spend at the trip"
  holds for the scenario where each claim is individually under the cap AND the tip is on the
  tripping claim's last call. The general parallel path can overspend by up to ~(workers-1) in-flight
  claims before the parent aborts — Codex Path-B risk #5, the accepted tradeoff (the sequential path
  has no such window). Not claimed tighter than the design provides.
- SECOND enforcement point documented honestly: `test_single_claim_over_cap_trips_in_worker_fail_closed`
  proves that when a SINGLE claim's own cost exceeds the full cap, its worker trips LIVE inside
  RecordingTransport (reset-context baseline 0) and raises before returning — fail-closed; asserts it
  RAISES but does NOT assert an equal parent total (the parent stays at the pre-seed). PASS.

### (c) coverage credited ONLY on VERIFIED — VERIFIED
- `if result.final_verdict == _VERDICT_VERIFIED: internal_ledger.covered_element_ids.update(...)`
  (sweep_integration.py:461-462) — byte-identical to the original; runs on the parent, in input order.
- `test_coverage_credit_only_on_verified_parallel`: claim-0 VERIFIED, claim-1 Sentinel-UNGROUNDED ->
  UNSUPPORTED; asserts only elem-0 credited (fraction 0.5), release held, and the KG persists both
  rows in input order with only the VERIFIED row reusable. PASS.

### (d) role_call_log complete (one block per claim, in order) — VERIFIED
- The log is built from `result.records` per claim in the reduction loop (440-450), so every served
  completion (Mirror x2, Sentinel, Judge == 4 records/claim on the happy path) is captured in input
  order. Written via `_write_role_call_log` incrementally after each claim (456) AND finally (496) —
  both calls share the SAME serialization (`ensure_ascii=False, sort_keys=True`), so the incremental
  partial file is a prefix of the final file (idempotent same-content rewrite).
- Asserted in `test_output_order_...` (4 records/claim, contiguous non-interleaving blocks) and
  byte-equality of the seq vs par logs in `test_sequential_path_matches_multi_worker`. PASS.

### (e) PG_FOUR_ROLE_CLAIM_WORKERS=1 result == multi-worker result — VERIFIED
- `test_sequential_path_matches_multi_worker`: 3 claims, mixed verdicts (claim-1 -> UNSUPPORTED);
  asserts workers=1 and workers=4 produce identical `final_verdicts`, identical `gaps` (dataclass
  ==), identical `release_allowed`, identical `coverage_fraction`, AND byte-identical role-call logs.
  PASS.
- Reinforced: the entire existing 34-test 4-role suite passes under BOTH `PG_FOUR_ROLE_CLAIM_WORKERS=1`
  and the default 6.

## Thread-safety audit (the spec's verification ask)

- **Cost ContextVar** (`_RUN_COST_CTX`): isolated per worker via `contextvars.copy_context()` +
  `reset_run_cost()` (sweep_integration.py:246/251); the parent re-adds the per-claim delta and
  enforces the cap on the single parent counter. This is the Codex naive-B trap ("assume copy_context
  makes _RUN_COST_CTX shared; it does not") handled correctly.
- **Reasoning sink** (`_REASONING_SINK_CTX` / `_capture_reasoning_trace`): VERIFIED NOT touched by the
  verifier path. The role transports (`OpenRouterRoleTransport`, `OpenAICompatibleRoleTransport`) POST
  via httpx and never call `set_reasoning_sink`/`_capture_reasoning_trace` (that is the generator's
  `OpenRouterClient.generate`/`reason` path). Grep of `src/polaris_graph/roles/` for any reasoning-sink
  symbol returns nothing. So NO per-worker sink isolation is needed; none was added (keeps the code
  honest/minimal).
- **pathB capture `_SINK`** (pathB_capture.py:48): a ContextVar holding a SHARED list by design
  (docstring L45-47). `copy_context()` shares the list BY REFERENCE; `list.append` is GIL-atomic; the
  M4 consumer (`scripts/dr_benchmark/pathB_run_gate.py`) uses `call_id` only as an error-message
  LABEL (verified: lines 562/565/582/.../625 are all f-string error contexts), never a join/order key.
  So `_SINK` is left SHARED, NOT isolated — isolating it per worker would DROP every verifier capture
  from the parent gate. The `_ROLE` tag IS correctly isolated for free by copy_context (each worker's
  `llm_role(role)` set lands in its own copied context), preventing cross-claim role-tag contamination.

## Test execution evidence

- New suite `tests/roles/test_seam_parallel.py`: 6/6 PASS.
- Existing 4-role suites (`test_sweep_integration.py` 17, `test_four_role_budget_cap.py` 9,
  `test_role_pipeline.py` 10): 36/36 PASS.
- Full `tests/roles/` + `tests/dr_benchmark/test_gate_b_seam.py`: 316/316 PASS.
- `tests/roles/test_sweep_integration.py + test_four_role_budget_cap.py + test_gate_b_seam.py` with
  `PG_FOUR_ROLE_CLAIM_WORKERS=1`: 34/34 PASS (sequential path unaffected).
- `py_compile` on both changed files: OK.

## Verdict

The diff implements the EXACT Path-B SAFE spec with no design improvisation. All five acceptance
criteria are verified by code-span + a passing deterministic test; the sequential path is empirically
byte-equivalent; the reasoning sink correctly needed no isolation; the pathB sink is correctly left
shared. The one honest scope statement (criterion (b)'s same-total claim holds for under-cap claims
with the tip on the tripping claim's last call; the general path has the accepted ~(workers-1)
in-flight overspend window, Codex risk #5) is documented in both the test and this audit. No P0/P1
self-identified.

---

## Iter-2 fixes (Codex diff-gate iter-1 REQUEST_CHANGES → applied)

Codex iter-1 (`.codex/I-run11-001/codex_diff_audit.txt`) returned REQUEST_CHANGES with two P1 and
three P2. All five are now fixed in `sweep_integration.py`. Line references below are post-fix.

### P1.2 (CRITICAL) — copy_context was taken in the WRONG thread → parent Path-B sink absent in workers — FIXED + VERIFIED

- **Root cause (iter-1):** `_compute_one` called `contextvars.copy_context()` INSIDE the worker
  thread, so it snapshotted the worker's EMPTY default context. The parent `_PATHB_SINK` / `_PATHB_ROLE`
  (registered by `pathB_runner.gate_around_question` → `register_pathB_capture()` on the PARENT) was
  ABSENT in workers; `capture_llm_call` reads `_SINK.get()` → None → no-op, so verifier capture was
  lost and the M4 post-run completeness gate would fail when `workers>1`.
- **Fix:** the per-claim context snapshot is now taken ON THE PARENT THREAD at submit time —
  `pool.submit(_compute_one, idx, claim, contextvars.copy_context())` (sweep_integration.py:323). Each
  claim gets its OWN copy (never one shared copy across concurrent workers). The worker calls
  `worker_ctx.run(_run)` (line 279); inside `_run`, `reset_run_cost()` (line 264) zeroes ONLY this
  copy's `_RUN_COST_CTX` while leaving the parent's `_SINK`/`_ROLE` references (carried by the same
  copy) intact, so verifier captures land at the parent sink. `_compute_one(idx, claim, worker_ctx)`
  takes the context as a parameter (line 255).
- **Verification that the parent `_SINK` is captured:** `pathB_capture._SINK` (pathB_capture.py:48) is a
  `ContextVar` holding a REFERENCE to a list set by `register_pathB_capture()` on the parent. A
  `copy_context()` taken on the parent AFTER that `set([])` captures the SAME list object by reference;
  `worker_ctx.run(_run)` executes the verifier calls under that snapshot, so `capture_llm_call`'s
  `_SINK.get()` returns the parent's list and `list.append` (GIL-atomic) is visible at the parent. New
  test `test_pathb_sink_visible_in_workers` registers the sink on the parent exactly as `pathB_runner`
  does, runs the seam with 4 workers + a transport that emits captureable calls, and asserts the PARENT
  sink received ALL `n*4` captures across all three verifier roles. Proven regression-catching: with
  `copy_context()` reverted INSIDE the worker the test FAILS with "parent sink saw 0 captures, expected
  16"; with the fix it PASSES (16/16, all roles, served-identity metadata present).

### P1.1 — budget enforced too late (drain-all then re-add) → cap could be exceeded by ALL claims — FIXED + VERIFIED

- **Root cause (iter-1):** the parallel branch submitted AND drained ALL futures, THEN the reduction
  loop re-added cost. An early cumulative cap trip still let every claim run and spend.
- **Fix:** the cap is now enforced DURING compute. The `as_completed` loop (sweep_integration.py:326)
  re-adds each completed claim's `delta` to the single parent counter (`_add_run_cost(delta)`, line 334)
  and re-checks immediately (`check_run_budget(0)`, line 335). On a breach (or any worker exception via
  `future.result()`) the `except BaseException` arm calls `pool.shutdown(wait=False, cancel_futures=True)`
  (line 349) to cancel still-queued claims, then re-raises — bounding overspend to the workers in flight
  at the breach (~workers-1). The pool is managed MANUALLY (`pool = ThreadPoolExecutor(...)` line 320 +
  `try/except/finally`), NOT via `with` (whose `__exit__` waits for all). The **now-duplicated** cost
  re-add was REMOVED from `run_four_role_evaluation`'s reduction loop — the loop head is now
  `for claim, (result, _cost_delta) in zip(claims, computed):` (line 493) with the `_add_run_cost` /
  `check_run_budget` block deleted; `_cost_delta` is retained in the tuple for audit but NOT re-added
  (re-adding would double-count). The reduction stays parent-only, input-order, for d8_rows /
  all_records / final_verdicts / role_call_log / coverage / kg_store.write_claim / incremental-log only.
- **Bounded in-flight — VERIFIED:** new test `test_cap_trip_is_bounded_in_flight` runs 12 claims, each
  individually under the cap, with `workers=2` and a per-claim delay so workers advance in bounded
  waves. The cumulative cap (0.30) crosses after ~3 claims' deltas are re-added; the test asserts
  `ran < n` AND `ran <= 3 + 2*workers`. Proven regression-catching: with the old drain-all behavior
  re-simulated the test FAILS with "ran 12/12 claims"; with the fix it PASSES (a small bounded prefix).

### P2.3 — mid-compute monitorability — FIXED

- The `as_completed` loop writes `run_dir/four_role_compute_progress.json` = `{"done": k, "total": n}`
  after each completion (sweep_integration.py:340, constant `FOUR_ROLE_COMPUTE_PROGRESS_FILENAME` at
  line 92). Parent-only write. This makes a hung COMPUTE visible on disk DURING compute, before the
  role_call_log (which only grows in the later parent-only reduction) exists.

### P2.2 — cancel-on-fail — FIXED

- The manual `except BaseException` arm (sweep_integration.py:343) calls
  `pool.shutdown(wait=False, cancel_futures=True)` (line 349) before re-raising, so a worker failure or
  cap breach cancels pending claims instead of waiting for the whole pool to drain.

### P2.1 — aborted-run cost under-accounting — DOCUMENTED (parity, not over-engineered)

- A one-line/paragraph comment at the head of the parallel block (sweep_integration.py:~313) notes that
  on a worker exception the worker's partial paid spend lives in the worker's isolated copied context
  and is NOT reconciled into the parent counter — the SAME accepted tradeoff the seam-timeout wrapper
  documents (run_honest_sweep_r3.py ~L4587-4596: in-flight verifier cost on the held/aborted path is not
  reconciled; prompt fail-closed termination outranks exact accounting on an already-aborted run,
  operator-authorized spend). Not over-engineered with a holder list — the fail-closed propagation stays
  simple.

### Iter-2 test execution evidence

- `tests/roles/test_seam_parallel.py`: **8/8 PASS** (the original 6 + the 2 new iter-2 tests).
- `tests/roles/` full regression: **310/310 PASS**.
- Both new tests proven to FAIL on a re-simulated regression (P1.2: 0/16 captures; P1.1: 12/12 ran) and
  PASS with the fix — no assertion was relaxed.
- `py_compile src/polaris_graph/roles/sweep_integration.py`: OK.

Constraints held: sequential fast path (`PG_FOUR_ROLE_CLAIM_WORKERS=1` / single claim) byte-equivalent
(lines 285-298, unchanged); no `except: pass` (the `except BaseException` re-raises); fail closed; LAW
VI env-only. D8 policy / KG / coverage / sequential byte-equivalence unchanged.

---

## Iter-3 follow-up — P1 regression (FileNotFoundError) + P2 observability

**P1 (REGRESSION introduced in iter-2 by the P2.3 progress write):** `_compute_claim_results` runs BEFORE `VerifiedClaimGraphStore(run_dir=...)`, which is historically the first thing that created `run_dir`. The iter-2 parallel progress write (`run_dir/four_role_compute_progress.json`) therefore raised `FileNotFoundError` for callers that pass a not-yet-created `run_dir` — confirmed at `scripts/dr_benchmark/offline_e2e.py:344` (via `run_four_role_seam`) and `tests/dr_benchmark/test_offline_e2e.py:376` (`run_dir=tmp_path/"run"`, no mkdir). VERIFIED against `src/polaris_graph/memory/verified_claim_graph.py:129` — the store does `resolved.parent.mkdir(parents=True, exist_ok=True)` where `resolved.parent == run_dir`, i.e. the store WAS the dir creator. FIX: `run_dir.mkdir(parents=True, exist_ok=True)` once at the TOP of the parallel branch (before the pool), idempotent with the later store. Sequential fast path unchanged (no mkdir, writes no progress file) — byte-equivalence preserved.

**P2 (observability):** progress marker was written AFTER `check_run_budget(0)`, so a budget-breaching completed claim never appeared in the progress file. FIX: write `{done, total}` BEFORE the `_add_run_cost`+`check_run_budget(0)` enforcement so the just-completed (incl. breaching) claim is on disk before a possible `BudgetExceededError` raises.

**Test execution evidence (iter-3):**
- Added `test_parallel_run_dir_created_when_missing` to `tests/roles/test_seam_parallel.py`.
- `tests/roles/test_seam_parallel.py`: **9/9 PASS** (8 prior + 1 new).
- `tests/dr_benchmark/test_offline_e2e.py`: **13/13 PASS** (exercises the real not-yet-created-run_dir caller).
- New test proven regression-catching: with the source fix stashed it FAILS at `sweep_integration.py:340` `progress_path.write_text` -> `FileNotFoundError`; PASSES with the fix. No assertion relaxed.
- `py_compile src/polaris_graph/roles/sweep_integration.py tests/roles/test_seam_parallel.py`: OK.

Constraints held: sequential fast path byte-equivalent (no mkdir, no progress write); no `except: pass`; determinism + parent-only reduction + cost/KG semantics unchanged; LAW VI env-only.
