# §-1.1 audit — FX-11b (#1117): cost-ledger P2 follow-ups

**Scope:** cost-accounting ONLY (no faithfulness / strict_verify / provenance / 4-role path —
the issue itself states "Cost-accounting only; no faithfulness path"). §-1.1 grounds each of the
3 P2s against the REAL held drb_72 cost ledger + the mechanism + offline tests.

## Item 1 — NLI-conflict judge ledger row (semantic_conflict_detector.py)

CLAIM: the NLI-conflict judge adds its spend to the run BUDGET (`_add_run_cost`) but writes NO
cost-ledger row, so a run with `PG_SWEEP_NLI_CONFLICT` enabled has a persisted ledger total below
the run-budget total.

EVIDENCE (held `outputs/audits/I-ready-017/run_artifacts/cost_ledger.jsonl`): 472 rows, call_type
counts `{generate: 31, entailment_judge: 441}` — **zero `nli_conflict_judge` rows**. The held run
ran with NLI-conflict OFF, so no NLI spend occurred; but the structural gap is real — there is no
`nli_conflict_judge` writer in the codebase, so ANY run with the flag ON would feed the budget
without a matching ledger row (ledger total < budget total).

FIX (verified): after `_add_run_cost` + `check_run_budget`, the detector now calls the canonical
`append_cost_ledger_row(session_id=current_run_id(), call_type="nli_conflict_judge", ...)` — the
SAME writer + ambient-run-id key the judge/role writers use, so all rows of one run share one
accumulator. It bumps the ledger accumulator (NOT `_RUN_COST_CTX`), so the budget is not
double-counted. Best-effort (ledger I/O never aborts detection). Tests
`test_nli_conflict_judge_writes_cost_ledger_row` (row written with correct call_type/session_id/cost)
+ `test_nli_conflict_judge_ledger_failure_does_not_abort`.

## Item 3 — free-call tokens excluded from imputed cost (openrouter_client.py)

CLAIM: `UsageTracker.total_cost_usd` imputes cost from `total_input/output_tokens`, which include
free-call tokens, so a `record(free=True)` call (which correctly ledgers cost 0) still shows a
phantom imputed cost in the in-memory usage summary.

EVIDENCE: `record(free=True)` sets `call_cost=0` (ledger row 0) but added the free tokens to
`total_input/output_tokens`, which feed the `total_cost_usd` token-imputed branch — a phantom cost.

FIX (verified): free-call tokens are accumulated in `total_free_input/output_tokens`;
`total_cost_usd` imputes over PAID tokens only (`total_* - total_free_*`). Free tokens are still
counted in `total_input/output_tokens` for honest token REPORTING — only the COST imputation
excludes them. The api-reported-cost branch is unchanged (still wins). Tests
`test_total_cost_usd_excludes_free_call_tokens`, `test_all_free_calls_impute_zero_cost`,
`test_api_reported_cost_still_wins_over_imputation`.

## Item 2 — pipeline-B ambient run-id alignment (graph.py)

CLAIM: `graph.py` constructs the generator client with `session_id=vector_id` while judge/role
writers key on the ambient run id (`current_run_id()`); if the pipeline-B path runs without
`set_current_run_id(vector_id)`, generator rows and judge/role rows land in DIFFERENT accumulator
keys. (Pipeline A / benchmark is SAFE — `run_honest_sweep_r3.py:1590` sets it.)

FIX (verified): `graph.build_and_run` now calls `set_current_run_id(vector_id)` on entering the
client block and `set_current_run_id(None)` after the run completes. The ambient-run-id KEY
resolution this aligns is already regression-covered by `test_m206_n301_cost_ledger.py` (the
`self.session_id or ambient run_id` precedence). graph.py is a large pipeline-B async function not
exercised by an offline unit harness; the 3-line set/reset is straightforward and the keying it
fixes is the same one those tests cover.

## Faithfulness
No faithfulness path touched. No strict_verify / provenance token / 4-role / two-family change.
Pure cost-ledger accounting (ledger total == budget total; no phantom free cost; consistent
accumulator key on pipeline B).

## Offline evidence
`pytest test_fx11b_cost_ledger_iready017.py` -> 5 passed. Regression: `test_fx11_cost_ledger_iready017
+ test_m206_n301_cost_ledger + test_entailment_judge_cost + test_semantic_conflict_detector_iready012`
-> 40 passed (no regression). py_compile clean on all 3 touched source files.
