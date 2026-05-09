# Codex Diff Review — I-bug-087 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-bug-087 — Default evaluator → Gemma 4 31B (Apache 2.0, 30.7B dense, 256K context, released 2026-04-02). Brief APPROVE'd iter 2 (incorporates P1 budget-imputation fix from iter 1).
- **Diff:** `.codex/I-bug-087/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed (per brief plan):**
  - `src/polaris_graph/llm/openrouter_client.py`:
    - `_PRICE_TABLE_USD_PER_M`: `"google/gemma-4-31b-it": (0.13, 0.38)` inserted BEFORE generic `"google/gemma"` (P1 fix from iter 1)
    - `PG_EVALUATOR_MODEL` default → `google/gemma-4-31b-it`
    - Rationale doc-comment updated for new default
    - Error-msg recommended pair → V4 Pro + Gemma 4 31B
  - `src/polaris_graph/evaluator/external_evaluator.py`: doc comment updated
  - `src/polaris_graph/evaluator/__init__.py`: package docstring updated
  - `src/polaris_graph/evaluator/live_qwen_judge.py`: module docstring updated (model name no longer hardcoded; reads PG_EVALUATOR_MODEL at runtime; module name retained for backward compat)
  - `.env.example`: `PG_EVALUATOR_MODEL` → `google/gemma-4-31b-it`
  - NEW `tests/polaris_graph/test_gemma_4_evaluator.py` (3 tests)

## Acceptance criteria (verified locally — 25/25 pass)

1. ✅ Gemma 4 31B specific price entry inserted BEFORE generic `"google/gemma"`.
2. ✅ `PG_EVALUATOR_MODEL` default → `google/gemma-4-31b-it`.
3. ✅ `.env.example` updated.
4. ✅ Doc comments + error msg + evaluator __init__ + live_qwen_judge docstring updated (P2 fold-in from iter 1).
5. ✅ 3 new Gemma evaluator tests pass.
6. ✅ Existing tests still pass (5 CJ-001 + 6 CJ-006 + 8 test_b4 + 3 V4 pricing = 22 regression tests).
7. ✅ ~70 LOC under 200.

## Red-team checklist

1. **Two-family invariant preserved** — Gemma 4 31B family resolves to "gemma" via existing prefix `("google/gemma", "google/gemma-", "gemma/")`; DeepSeek V4 Pro family is "deepseek". Test 2 in new file pins `check_family_segregation("deepseek/deepseek-v4-pro", "google/gemma-4-31b-it") == ("deepseek", "gemma")`.
2. **Budget-guard invariant preserved** — Gemma 4 31B specific entry inserted FIRST so first-match-wins picks the specific rate ($0.13/$0.38), not the generic `"google/gemma"` rate ($0.05/$0.30). Test 3 pins this. Without the specific entry, the budget guard would silently under-impute (Codex iter-1 P1 catch).
3. **No live API call** — config-default change + doc-comment hygiene only.
4. **Backward compat** — predecessor Qwen3-8B retained on OpenRouter; switch back via `PG_EVALUATOR_MODEL=qwen/qwen3-8b` in `.env`.
5. **§9.4 hygiene** — clean.

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
