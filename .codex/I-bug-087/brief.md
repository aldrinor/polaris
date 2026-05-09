# Codex Brief Review — I-bug-087 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 (budget-imputation undercharges Gemma 4 default)**: existing `"google/gemma"` generic prefix at $0.05/$0.30 would under-impute against the actual Gemma 4 31B OpenRouter rate ($0.13/$0.38). This violates the file's documented invariant that the fallback should over-charge, not under-charge — under-imputing weakens the budget guard. Iter 2 adds a model-specific `"google/gemma-4-31b-it"` entry inserted BEFORE the generic `"google/gemma"` line in `_PRICE_TABLE_USD_PER_M` (same pattern as I-bug-086 V4 Pro/Flash entries). New cost test asserts the rate-specific imputed value, not just `> 0`.
- **P2 (stale Qwen docstrings)**: also updates `src/polaris_graph/evaluator/live_qwen_judge.py:1` module docstring + `src/polaris_graph/evaluator/__init__.py` to honestly state the new default. Cleanup-class change, non-blocking but folded in to keep doc layer honest.



```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-bug-087 — Default evaluator → `google/gemma-4-31b-it` (released 2026-04-02, 30.7B dense, 256K context, Apache 2.0). User directive 2026-05-08 after open-weight evaluator survey: "OK" to Gemma 4 31B. Generator stays `deepseek/deepseek-v4-pro` (just shipped in I-bug-086).
- **Two-family invariant verified:** `google/gemma-4-31b-it` matches existing `_FAMILY_PREFIXES["gemma"]` prefix `("google/gemma", "google/gemma-", "gemma/")`. Family resolves to `"gemma"`. Generator family is `"deepseek"`. `check_family_segregation` returns `("deepseek", "gemma")` — passes.
- **Substrate today:**
  - `src/polaris_graph/llm/openrouter_client.py:251` — `PG_EVALUATOR_MODEL` env-var default (currently `qwen/qwen3-8b`).
  - `:219` rationale doc-comment, `:343` error-msg recommended pair.
  - `_PRICE_TABLE_USD_PER_M` (line 134) has generic `"google/gemma"` prefix at $0.05/$0.30 — UNDER-imputes Gemma 4 31B's actual OpenRouter rate ($0.13/$0.38) per Codex iter-1 P1. Need specific entry inserted BEFORE generic line so budget-guard invariant (fallback should over-, not under-charge) holds.
  - `.env.example:60` carries the Qwen default.
  - `src/polaris_graph/evaluator/external_evaluator.py:29` doc comment.
- **Honest framing per CLAUDE.md §9.4:** evaluator default-string change. Two-family invariant preserved. Existing tests that reference `qwen/qwen3-8b` literally (test_b4, test_external_evaluator, test_cj_001/006) test invariants not the specific evaluator string and continue to pass. Stale fixture strings are non-blocking; cleanup is a separate doc-hygiene Issue.

## Plan

### `src/polaris_graph/llm/openrouter_client.py` (MODIFY)

1a. Insert Gemma 4 31B specific price entry BEFORE generic `"google/gemma"` line in `_PRICE_TABLE_USD_PER_M` (same first-match-wins pattern as I-bug-086):
```python
"google/gemma-4-31b-it": (0.13, 0.38),
"google/gemma":          (0.05, 0.30),
```

1b. `PG_EVALUATOR_MODEL` default at line ~251:
```python
PG_EVALUATOR_MODEL = os.getenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")
```

2. Update rationale doc-comment around line ~219 — replace Qwen 3-8B paragraph with Gemma 4 31B note (released 2026-04-02, 30.7B dense not MoE, 256K context, Apache 2.0, Google family separates from DeepSeek lineage; aligns with documented Phase-4 plan).

3. Update error-msg recommended pair at line ~343:
   `deepseek/deepseek-v4-pro (generator) + google/gemma-4-31b-it (evaluator)`.

### `src/polaris_graph/evaluator/external_evaluator.py` (MODIFY)

4. Line 29 doc comment: `Uses PG_EVALUATOR_MODEL (default google/gemma-4-31b-it) against PG_GENERATOR_MODEL (default deepseek/deepseek-v4-pro).`

### `src/polaris_graph/evaluator/live_qwen_judge.py` + `__init__.py` (MODIFY — P2 fold-in)

4b. Update module docstrings to reflect that the default evaluator is now Gemma 4 31B; live_qwen_judge.py remains the implementation entry point but the model is no longer Qwen by default. Note backward-compat: if `PG_EVALUATOR_MODEL=qwen/qwen3-8b` is set in `.env`, behavior reverts to Qwen and the live_qwen_judge name becomes accurate again.

### `.env.example` (MODIFY)

5. Line 60: change `qwen/qwen3-8b` → `google/gemma-4-31b-it`.

### Tests

6. **NEW** `tests/polaris_graph/test_gemma_4_evaluator.py` (~40 LOC, 3 tests):
   - `family_from_model("google/gemma-4-31b-it")` returns `"gemma"`.
   - `check_family_segregation("deepseek/deepseek-v4-pro", "google/gemma-4-31b-it")` returns `("deepseek", "gemma")` — passes.
   - `_impute_cost_from_tokens("google/gemma-4-31b-it", 1_000_000, 1_000_000, 0)` returns the model-specific rate sum (`0.13 + 0.38 = 0.51`), NOT the generic `"google/gemma"` rate sum (`0.05 + 0.30 = 0.35`). Pins that the specific entry wins over the generic — same first-match-wins ordering pattern as I-bug-086 V4 Pro/Flash entries.

### Existing tests (NO CHANGE)

7. CJ-001 / CJ-006 / test_b4 / test_external_evaluator continue to use `qwen/qwen3-8b` as fixture strings; they test invariants not specific evaluator. Stale-but-passing.

## Risks for Codex Red-Team

1. **Two-family invariant** — `google/gemma-4-31b-it` matches existing `"google/gemma"` prefix in `_FAMILY_PREFIXES["gemma"]`. Generator `deepseek/deepseek-v4-pro` matches `"deepseek/"` in `_FAMILY_PREFIXES["deepseek"]`. Different families. Test 2 in new file pins this.
2. **Substrate-honest** — pure default-string change. No new functionality. Aligns with documented Phase-4 plan target (which always specified Gemma 4 31B as the eventual evaluator).
3. **No live API call in this PR** — config-default change. Live re-benchmark is a separate operation.
4. **§9.4 hygiene** — clean.
5. **CHARTER §3 LOC cap** — ~25 LOC under 200.

## Acceptance criteria

1. `PG_EVALUATOR_MODEL` default → `google/gemma-4-31b-it`.
2. `.env.example` updated.
3. Doc comments + error msg updated.
4. New `tests/polaris_graph/test_gemma_4_evaluator.py` with 3 tests passes.
5. Existing tests still pass (no break).
6. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-6.

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
