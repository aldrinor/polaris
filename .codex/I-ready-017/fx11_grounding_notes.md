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
