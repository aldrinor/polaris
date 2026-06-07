# I-ready-017 FX-11c (#1136) — DIFF gate (iter 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this implements (#1136 — the 2 accepted P2s YOU raised on FX-11b #1117)
Diff: `.codex/I-ready-017/fx11c_codex_diff.patch` (base HEAD~1..HEAD; 3 files). Cost-accounting ONLY.

(a) `semantic_conflict_detector.py`: moved `append_cost_ledger_row(...)` to BEFORE
`_orc.check_run_budget(0)`. A budget-breaching NLI call is already billed to the accumulator by
`_add_run_cost` above; pre-fix `check_run_budget` raised first, so the breaching call's ledger row
was never written (billed-but-unledgered). Now the row is written first, then the budget check
raises. `BudgetExceededError` still propagates (judge() re-raises it for keep-partial).

(b) `graph.py build_and_run`: added `set_current_run_id(None)` before the failure-return
(`result["status"]="failed"; return result`), so a failed pipeline-B run also clears the ambient run
id (success-return already did). The remaining propagating-exception path is benign on the
per-request pipeline-B path (next build_and_run overwrites) and is documented in the code; a full
try/finally would require re-indenting the ~200-line client block (disproportionate risk for a P2).

## Offline evidence
`pytest tests/polaris_graph/test_fx11b_cost_ledger_iready017.py` -> 6 passed, incl
`test_nli_ledger_row_written_before_budget_breach` (injects a check_run_budget that raises; asserts
the ledger row WAS captured AND BudgetExceededError propagates). Regression:
test_semantic_conflict_detector_iready012 + test_fx11_cost_ledger_iready017 -> 22 passed. py_compile clean.
§-1.1: outputs/audits/I-ready-017/fx11c_s11_audit.md.

## Questions
1. Is (a) correct — the ledger row precedes the budget check, no double-count, BudgetExceededError still propagates?
2. Is (b)'s failure-return reset acceptable (exception path documented-benign), or do you require the full try/finally?
3. Any cost-accounting / correctness gap before APPROVE?
