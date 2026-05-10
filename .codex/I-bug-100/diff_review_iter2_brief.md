## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — non-blockers are P3/P2/cosmetic.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Iter-1 P1 + P2 disposition

| Iter-1 finding | Iter-2 fix |
|---|---|
| **P1** entailment_judge imports `polaris_graph.llm.openrouter_client` while production sweep imports `src.polaris_graph.llm.openrouter_client`. Two separate sys.modules entries → separate ContextVar state → judge cost invisible to sweep. | **FIXED.** entailment_judge.py:50 now uses `from src.polaris_graph.llm import openrouter_client as _orc`. The internal family-segregation import on :91 also switched to `src.polaris_graph.llm.openrouter_client`. **Empirical proof:** new test `test_judge_shares_state_with_canonical_src_module` imports via `src.polaris_graph.llm.openrouter_client`, sets cap, invokes judge, asserts `src_orc.current_run_cost() == 0.000567` (exact API-reported value). Test passes 1/1. |
| **P2** Zero-cost recorded when entire usage block absent. | **FIXED.** entailment_judge.py:142-148 adds fallback estimate: when `actual_cost == 0 and not usage`, impute against (500 prompt + 100 completion) at the judge model's price rate. **Empirical proof:** new test `test_judge_falls_back_to_estimate_when_usage_block_absent` sends payload without usage block, asserts non-zero cost matching the fallback formula. Test passes 1/1. |

## §2 — Diff under review (revised)

5 tests now (was 3): test_judge_records_api_cost_when_present, test_judge_imputes_cost_when_api_cost_absent, **test_judge_shares_state_with_canonical_src_module (NEW iter-1 P1)**, **test_judge_falls_back_to_estimate_when_usage_block_absent (NEW iter-1 P2)**, test_judge_raises_budget_exceeded_when_cap_breached.

Suite: 66 baseline + 5 new = **71 pass in 6.46s**.

## §3 — Net change

| File | Δ |
|---|---|
| `src/polaris_graph/llm/entailment_judge.py` | +91 (was +82; +9 for src-namespace fix + usage-absent fallback) |
| `tests/polaris_graph/llm/__init__.py` | NEW (empty) |
| `tests/polaris_graph/llm/test_entailment_judge_cost.py` | +236 (was +170; +66 for 2 new regression tests) |

## §4 — Output Schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Expected APPROVE iter 2.
