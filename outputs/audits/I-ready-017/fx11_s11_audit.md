# FX-11 §-1.1 audit — cost_ledger SINGLE canonical accumulator + role rows (I-ready-017 #1116)

**Standard:** §-1.1 structural check on the REAL held drb_72
`outputs/audits/I-ready-017/run_artifacts/cost_ledger.jsonl` (the ledger is run-time
OUTPUT, so the bug is confirmed on the real artifact; the fix is proven by offline smoke +
a parallel-worker repro since a fresh ledger needs a live run).

## The bug, on the real artifact (BUG-10 + BUG-10b)
The held ledger (472 rows) exhibits BOTH defects exactly as the plan stated:
- **BUG-10:** **26 decreasing `cumulative_cost_usd` steps** within `session_id` — the
  cumulative was the per-instance `self.total_cost_usd`, non-monotonic across clients
  sharing a run, and the UI read the per-instance one (under-reports NOW).
- **BUG-10b:** **0 `role:` rows** — `call_types` present are only `entailment_judge` +
  `generate`. The 590 four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger
  rows.

## The fix (iter-2 — single canonical writer)
The issue's literal title is "cost_ledger single canonical accumulator." Iter-2 delivers exactly
that: ONE process-global, RLock-protected, per-session accumulator (`_LEDGER_CUM_BY_SESSION`,
keyed by run id) plus ONE canonical writer `append_cost_ledger_row` that **bumps + appends under
the same lock**.
- **BUG-10:** `cumulative_cost_usd` at every producer is the shared per-session run total
  (inclusive of the current call), resolved with ONE precedence across all writers
  (`self.session_id or ambient run_id`, normalized) so generate + judge + role rows share ONE
  accumulator. `check_run_budget` (the spend gate, on the per-task `current_run_cost()` ContextVar)
  is untouched.
- **BUG-10b:** `RecordingTransport.complete` appends a `role:<role>` row per four-role verifier
  call via the canonical writer (inclusive cumulative). Best-effort — a ledger-write failure never
  breaks the verifier call or the budget check.
- **Codex iter-1 P1 (the blocker):** under the REAL parallel four-role fan-out
  (`sweep_integration`: `ThreadPoolExecutor` + per-worker `contextvars.copy_context()` that
  inherits the run id while each worker resets ONLY its own `_RUN_COST_CTX`), reading cumulative
  from `current_run_cost()` made role-row cumulatives per-worker / non-monotonic. The shared
  accumulator + bump-and-append-under-one-RLock makes the PERSISTED FILE non-decreasing in WRITE
  order regardless of which worker writes.
- **Codex iter-1 P2a:** the blank-verdict retry path (`openrouter_role_transport`) billed the run
  budget but wrote no ledger row → now writes a `role:<role>:blank_attempt` row through the
  canonical writer (ledger total stays == run-budget total).
- **Codex iter-1 P2b:** a genuinely-free call (operator loopback, `free=True`) ledgered a phantom
  paid-rate token estimate → now ledgers 0. The imputation backstop (invariant #6) for *paid* calls
  with no reported cost is untouched.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx11_cost_ledger_iready017.py` → 6 passed:
- **monotonic run-total** (generator): 3 sequential calls → ledger cumulative `[0.5,0.8,1.0]`,
  final == `current_run_cost()`, last cumulative != its own `cost_usd`.
- **role rows inclusive**: two `RecordingTransport.complete` calls → two `role:` rows,
  non-decreasing inclusive cumulative, single session id.
- **P1 parallel repro** (`...monotonic_under_parallel_workers`): replicates `sweep_integration`'s
  EXACT fan-out — 6 ThreadPoolExecutor workers × `copy_context()` × per-worker `reset_run_cost()`,
  30 role rows → cumulative NON-DECREASING **in file write order**, all tagged the ONE shared run
  id, final == the GLOBAL total of every role cost (which per-worker `current_run_cost()` could
  never have shown). This test FAILS on iter-1's `current_run_cost()` cumulative.
- **P2a**: a `role:*:blank_attempt` row is ledgered with the inclusive cumulative.
- **P2b**: a `free=True` call ledgers `cost_usd == 0.0`; control proves a paid call w/o reported
  cost STILL imputes (#6).
- **P2c**: a FORCED real write failure (ledger path traverses through a regular file so
  `.parent.mkdir` raises) → the role call still returns and no partial file is created.
- Regression: `tests/roles/` (437) + `test_entailment_judge_cost` (8) + `test_m206_n301_cost_ledger`
  (10) + sota session_id/`_append_ledger` (3) + `llm/` (11) + loopback regression (12) all pass.

## Faithfulness check
Cost-accounting ONLY. No grounding / strict_verify / 4-role-decision change.
`check_run_budget` (the spend gate) is untouched; the canonical writer only makes the persisted
ledger a single monotonic per-session run total and adds the previously-missing role / blank-attempt
rows.
