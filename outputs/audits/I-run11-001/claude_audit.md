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
