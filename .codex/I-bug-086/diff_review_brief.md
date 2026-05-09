# Codex Diff Review — I-bug-086 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-bug-086 — DeepSeek V4 Pro generator default swap. Brief APPROVE'd iter 2 (zero P0/P1, one non-blocking P2 about stale fixture strings in unrelated tests).
- **Diff:** `.codex/I-bug-086/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - `src/polaris_graph/llm/openrouter_client.py` — V4 Pro/Flash price entries, default model, doc-comment, error-msg recommended pair
  - `src/polaris_graph/evaluator/external_evaluator.py` — doc comment
  - `.env.example` — PG_GENERATOR_MODEL + OPENROUTER_DEFAULT_MODEL
  - NEW `tests/polaris_graph/test_deepseek_v4_pricing.py` (3 tests)

## Acceptance criteria (verified locally)

1. ✅ V4 Pro/Flash price entries inserted BEFORE `"deepseek/"` generic.
2. ✅ `PG_GENERATOR_MODEL` default → `deepseek/deepseek-v4-pro`.
3. ✅ `.env.example` updated.
4. ✅ Doc comments + error msg updated.
5. ✅ 3 new pricing/family tests pass.
6. ✅ Existing tests still pass (22/22 incl. test_b4 + CJ-001 + CJ-006).
7. ✅ ~50 LOC under 200.

## Red-team checklist

1. **Price-table ordering correctness** — V4-specific entries are at indices 0-1 (insertion order), generic `"deepseek/"` is index 2. `_impute_cost_from_tokens` iterates dict and breaks on first `startswith` match. Test 1 + 2 in new file pin this.
2. **Two-family invariant preserved** — V4 Pro family = "deepseek". Evaluator stays `qwen/qwen3-8b`. `check_family_segregation` returns `("deepseek", "qwen")`. Test 3 in new file pins this.
3. **No live API call** — config-default change only. No BEAT-BOTH benchmark re-run in this PR (separate cost-bearing operation).
4. **§9.4 hygiene** — clean.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
