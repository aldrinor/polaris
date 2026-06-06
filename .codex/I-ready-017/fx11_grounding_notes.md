# FX-11 (#1116) grounding — cost_ledger monotonic accumulator + role-call rows

INDEP (file-serialized behind FX-01, done). Base = HEAD bot/I-ready-017-faithfulness (FX-10 verified, e63c102b).
NOT faithfulness-invariant — cost accounting only.

## BUG-10 (openrouter_client.py)
- Reorder: `_add_run_cost` (line ~1863) must run BEFORE `usage.record` (~1853) — match the
  judge add-then-write order so the recorded cumulative is INCLUSIVE of this call.
- Change `cumulative_cost_usd` at ALL THREE producers to `round(current_run_cost(), 4)`:
  ~752, ~769, ~1959 (the 3rd feeds the live UI — audit missed it; that's why UI under-reports).
- Leave per-call `cost_usd` as the line item. DO NOT touch `check_run_budget`.
- VERIFY exact lines (file shifted from FX-01/FX-09 edits): grep `_add_run_cost`, `usage.record`,
  `cumulative_cost_usd` in openrouter_client.py before editing.

## BUG-10b (role_pipeline.py:153-176 RecordingTransport.complete — now free; FX-08 dedup deferred to FX-08b)
- AFTER `_add_run_cost` (~:174) append a ledger row mirroring
  `entailment_judge._append_judge_ledger_entry`: `call_type=f'role:{request.role}'`, cost from
  `compute_role_call_cost`, `cumulative_cost_usd` read AFTER the add (inclusive); best-effort write
  (try/except, never crash the role call).
- Read `_append_judge_ledger_entry` in entailment_judge.py for the exact row schema + write path.

## Smoke (offline)
- two clients sharing one run + judge calls + RecordingTransport role calls, tmp ledger:
  every row cumulative_cost_usd within session_id NON-DECREASING; final==current_run_cost();
  generate rows != own cost_usd after >1 call; role rows present call_type^='role:'.

## §-1.1 (new run cost_ledger.jsonl): 0 decreasing steps (was 26/471); final==max==manifest.cost_usd;
role rows count==four_role_role_calls.jsonl rows (was 0); line items reconcile ±rounding.

## Resume: BUG-10 reorder+3 producers first, then BUG-10b role row; smoke; §-1.1 on a real/replayed ledger; ONE gate.

## iter-2 DESIGN (Codex iter-1 RC: 1 P1 + 3 P2) — author next wake (concurrency redesign, do carefully)

### P1 (BLOCKER): role-row cumulative non-monotonic under parallel four-role workers
- ROOT: sweep_integration.py `_compute_one._run` runs each claim in a worker_ctx copy, calls
  `reset_run_cost()` (zeroes the worker's _RUN_COST_CTX), accumulates per-claim, returns
  `(res, current_run_cost())` = per-claim delta; parent re-adds each delta via `_add_run_cost`
  AFTER (~line 355). So role-ledger rows (written INSIDE the worker via RecordingTransport)
  use worker-LOCAL current_run_cost() → per-claim, interleaved, NON-monotonic across 6 workers.
- FIX (the SOTA monotonic-counter primitive): add a PROCESS-GLOBAL, lock-protected, per-SESSION
  ledger accumulator in openrouter_client:
    `_LEDGER_CUM_LOCK = threading.Lock(); _LEDGER_CUM_BY_SESSION: dict[str,float] = {}`
    `def ledger_bump_cumulative(session_id, cost) -> float:` (lock; v=prev+cost; store; return round(v,4))
  Use it for cumulative_cost_usd in ALL THREE ledger writers (keyed by session_id, NOT contextvar):
    1. UsageTracker.record (generate rows) — replace round(current_run_cost(),4) with bump(self.session_id, call_cost).
    2. entailment_judge._append_judge_ledger_entry — replace round(_orc.current_run_cost(),4) with bump(session_id, actual_cost).
    3. role_pipeline RecordingTransport role row — replace round(_orc.current_run_cost(),4) with bump(session_id, _role_cost).
  Monotonic within session_id regardless of worker/thread. session_id is consistent (workers copy parent run_id).
  NOTE the budget GATE still uses current_run_cost() (contextvar) — do NOT change check_run_budget.
  Add a per-session reset hook (clear _LEDGER_CUM_BY_SESSION[sid] in reset_run_cost OR set_current_run_id) so a
  re-used session_id in one process starts fresh — MUST verify this doesn't break across the reset/merge.

### P2a: openrouter_role_transport.py:781 blank-verdict retry adds _add_run_cost but writes NO ledger row.
  Add a best-effort role-ledger row there too (call_type f"role:{request.role}" or "role:retry") so ledger is complete
  AND the ledger accumulator stays consistent with current_run_cost() (keeps §-1.1 final==run-total).

### P2b: loopback_client.py:297 UsageTracker.record without _add_run_cost (not live spend) — soften the safety claim in audit/brief; low priority, no code change required unless trivial.

### P2c: test best-effort write-failure didn't force a failure (mkdir creates parents). Fix: monkeypatch builtins.open (or _orc.open) to raise, assert role call still returns.

### iter-2 §-1.1: real held ledger already proves the bug; add an OFFLINE parallel repro test (2+ ThreadPool workers each via RecordingTransport under copied contexts) asserting role-row cumulative is GLOBALLY non-decreasing within session_id. + keep the monotonic generate-row + best-effort tests.
