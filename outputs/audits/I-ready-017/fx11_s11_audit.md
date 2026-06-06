# FX-11 §-1.1 audit — cost_ledger monotonic accumulator + role rows (I-ready-017 #1116)

**Standard:** §-1.1 structural check on the REAL held drb_72
`outputs/audits/I-ready-017/run_artifacts/cost_ledger.jsonl` (the ledger is run-time
OUTPUT, so the bug is confirmed on the real artifact; the fix is proven by offline smoke
since a fresh ledger needs a live run).

## The bug, on the real artifact (BUG-10 + BUG-10b)
The held ledger (472 rows) exhibits BOTH defects exactly as the plan stated:
- **BUG-10:** **26 decreasing `cumulative_cost_usd` steps** within `session_id` — the
  cumulative was the per-instance `self.total_cost_usd`, non-monotonic across clients
  sharing a run, and the UI read the per-instance one (under-reports NOW).
- **BUG-10b:** **0 `role:` rows** — `call_types` present are only `entailment_judge` +
  `generate`. The 590 four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger
  rows.

## The fix
- **BUG-10:** `_add_run_cost` now runs BEFORE `usage.record` (matching the judge
  add-then-write order), and `cumulative_cost_usd` at all THREE producers
  (`usage.record` ×2 + the live-UI trace `llm_call` event) is `round(current_run_cost(),
  4)` — the shared, monotonic run total, inclusive of the current call. Per-call `cost_usd`
  stays the line item. `check_run_budget` untouched.
- **BUG-10b:** `RecordingTransport.complete` appends a ledger row per role call
  (`call_type=f"role:{role}"`), mirroring `entailment_judge._append_judge_ledger_entry`,
  with `cumulative_cost_usd` read AFTER the add (inclusive). Best-effort (try/except) — a
  ledger-write failure never breaks the verifier call or the budget check.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx11_cost_ledger_iready017.py` → 3 passed:
- **monotonic run-total:** 3 sequential `_add_run_cost`+`record` calls → ledger cumulative
  `[0.5, 0.8, 1.0]` (NON-DECREASING), final == `current_run_cost()`, and the last row's
  cumulative != its own `cost_usd` (the old per-instance bug is gone).
- **role rows:** two `RecordingTransport.complete` calls → exactly two `role:` rows
  (`role:mirror`, `role:sentinel`), non-decreasing inclusive cumulative, non-zero cost.
- **best-effort:** an un-writable ledger path does NOT break the role call.
- Regression: `test_entailment_judge_cost` (8) + full `tests/roles/` (437) pass.

## Faithfulness check
Cost-accounting ONLY. No grounding / strict_verify / 4-role-decision change.
`check_run_budget` (the spend gate) is untouched; the reorder only makes the post-call
accumulation inclusive before the ledger write.
