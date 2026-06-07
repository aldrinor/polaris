# §-1.1 audit — FX-11c (#1136): cost-ledger edge-path completeness

Cost-accounting only (no faithfulness path). Two Codex-accepted P2s from FX-11b (#1117).

## (a) NLI ledger row precedes the budget check
The NLI-conflict judge bills the run accumulator via `_orc._add_run_cost(actual_cost)` and then
`_orc.check_run_budget(0)` (raises `BudgetExceededError` on a breach). Pre-FX-11c the ledger row was
written AFTER `check_run_budget`, so a breaching call was billed to the accumulator but its ledger
row never written → ledger total < budget total for that call (the exact drift FX-11/FX-11b fix).
FIX: the `append_cost_ledger_row` call now precedes `check_run_budget`. Test
`test_nli_ledger_row_written_before_budget_breach` injects a `check_run_budget` that raises and
asserts (1) the ledger row WAS captured and (2) `BudgetExceededError` still propagates (keep-partial).

## (b) graph.py ambient run-id reset on the failure-return
`build_and_run` set `set_current_run_id(vector_id)` on client entry and reset it on the success
return; the failure-return (`result["status"]="failed"; return result`) did not reset it. FIX: added
`set_current_run_id(None)` before the failure-return too, so a failed pipeline-B run does not leak
vector_id into unrelated ambient cost code. The propagating-exception path is benign (per-request
pipeline-B; the next `build_and_run` overwrites the ambient id) and documented.

## Faithfulness
None touched. Pure cost-ledger accounting + ambient-key hygiene.

## Offline evidence
`pytest test_fx11b_cost_ledger_iready017.py` → 6 passed (incl the FX-11c breach test) +
`test_semantic_conflict_detector_iready012 + test_fx11_cost_ledger_iready017` green. py_compile clean.
