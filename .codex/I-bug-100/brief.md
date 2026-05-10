## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Issue + Acceptance Criteria

**GH#354 — I-bug-100: route entailment-judge calls through OpenRouterClient cost-tracking infrastructure.**

The entailment judge (`polaris_graph.llm.entailment_judge._EntailmentJudge`, extracted in I-bug-099 PR #378) currently uses raw httpx and bypasses `polaris_graph.llm.openrouter_client`'s cost ledger + per-run cost cap. A persistent enforce-mode run accumulates uncounted spend.

**Architectural constraint — async/sync mismatch.** `OpenRouterClient.reason()` / `.generate()` are async. `_EntailmentJudge.judge()` is sync (called from sync `verify_sentence` in the inner verification loop). A full async refactor of strict_verify is out of scope for I-bug-100 (would be its own multi-file change with broad blast radius). Per CLAUDE.md §6.2 anti-degradation: don't bypass; route through the existing **module-level sync primitives** in openrouter_client.

**Acceptance:**
- After every successful entailment judge call, the cost is recorded:
  - `add_run_cost(cost_usd)` updates the ContextVar accumulator (raises `BudgetExceededError` if `PG_MAX_COST_PER_RUN` exceeded).
  - An entry appended to `logs/pg_cost_ledger.jsonl` matching OpenRouterClient's schema (`timestamp`, `run_id`, `task`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `cumulative_cost_usd`).
- Cost is computed from `usage.cost` if OpenRouter returns it; otherwise imputed via `_impute_cost_from_tokens(model, prompt_tokens, completion_tokens)` using the existing `_PRICE_TABLE_USD_PER_M`.
- Family-segregation invariant unchanged (already enforced at construction).
- BudgetExceededError propagates up out of `_EntailmentJudge.judge()` so the sweep aborts cleanly with a clear cause (no fail-open masking the budget breach).
- All 66 existing entailment tests still pass. New unit tests: cost-record-on-success (3 cases: usage.cost present / usage.cost absent imputed / budget-exceeded raises).

## §2 — Proposed Change

| File | Δ | Notes |
|---|---|---|
| `src/polaris_graph/llm/openrouter_client.py` | +~12 lines | Promote 3 private helpers to public-ish (drop leading underscore on names used by entailment_judge): rename `_add_run_cost` → `add_run_cost`, expose `_impute_cost_from_tokens` → `impute_cost_from_tokens`, expose `_LEDGER_PATH` → `LEDGER_PATH`. Keep the private aliases as backwards-compat references for any internal uses. ALTERNATIVELY: leave names as-is and entailment_judge imports them as `from polaris_graph.llm.openrouter_client import _add_run_cost, _impute_cost_from_tokens, _COST_LEDGER_PATH` — same module, single-file inter-private use is acceptable per Python convention for modules in the same package. |
| `src/polaris_graph/llm/entailment_judge.py` | +~50 lines | After successful httpx response: parse `data.get("usage", {})`, extract `prompt_tokens`, `completion_tokens`, optional `cost`. If `cost` present use it; else call `_impute_cost_from_tokens(self._model, prompt_tokens, completion_tokens)`. Call `_add_run_cost(cost_usd)` (raises BudgetExceededError if exceeded). Append a record to `_COST_LEDGER_PATH` (jsonl) matching OpenRouterClient's per-call schema. Tag with `run_id` from `_CURRENT_RUN_ID_CTX.get()` and `task="entailment_judge"`. Wrap in `try/except` so ledger-IO errors don't break the judge call (warn-log only). BudgetExceededError is NOT caught; it must propagate. |
| `tests/polaris_graph/llm/test_entailment_judge_cost.py` | NEW (+~120 lines) | 3 unit tests: (1) usage.cost present → exact value recorded; (2) usage.cost absent → imputed value recorded; (3) BudgetExceededError raised when call would exceed PG_MAX_COST_PER_RUN. Use FakeJudge pattern from existing tests. Verify ledger jsonl line + run-cost contextvar increment. |

**Net: ~+170 lines / 0 deletions.** Well under §3.0 200-LOC cap (the test file is the bulk).

## §3 — Files I have ALSO checked and they're clean

- `src/polaris_graph/generator2/strict_verify.py` — re-exports judge symbols from entailment_judge; this PR doesn't touch the re-export surface. ✓
- `src/polaris_graph/generator/provenance_generator.py` — lazy-imports `_get_judge` from strict_verify (which re-exports from entailment_judge). The cost-recording happens inside `_EntailmentJudge.judge()` regardless of which call path invoked it. ✓
- `src/polaris_graph/llm/openrouter_client.py:109-113` (_add_run_cost), `:160-200` (_check_run_cost_cap_or_raise + impute), `:40` (_COST_LEDGER_PATH), `:121-141` (_PRICE_TABLE_USD_PER_M) — these are the helpers entailment_judge will call. Module-level globals; thread/async safe via ContextVar. ✓
- `tests/polaris_graph/test_provenance_generator_entailment.py`, `tests/polaris_graph/generator2/test_strict_verify_entailment.py`, etc. — they patch `_get_judge` at module level. The patched fake judge returns hardcoded verdicts; doesn't go through real httpx → no cost path triggered. Unchanged. ✓
- `logs/pg_cost_ledger.jsonl` — already exists in production runs; new entries append-only with same schema. ✓

## §4 — Test Strategy

- Smoke baseline (current `polaris` HEAD post-PR-#378): 66 entailment tests pass.
- Post-change: 66 + 3 new = 69 tests pass.
- Manual smoke: assert `logs/pg_cost_ledger.jsonl` contains an entry with `task="entailment_judge"` after a single live judge call (requires PG_STRICT_VERIFY_ENTAILMENT=enforce + OPENROUTER_API_KEY).

## §5 — Output Schema Bound

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §6 — Convergence Hint

The architectural compromise (sync judge + module-level sync helpers, NOT full async refactor) is the practical answer for I-bug-100 in isolation. A future "make strict_verify async" issue can be filed if/when there's pressure to fold the judge into the async OpenRouterClient methods (e.g., I-bug-decompose multi-question pipelines).

Expected APPROVE on iter 1.
