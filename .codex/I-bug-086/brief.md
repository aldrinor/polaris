# Codex Brief Review — I-bug-086 (ITER 2 of 5) — verdict-only

## Iter 1 outcome (captured in iter_1.txt:3880-3936)

Codex empirically verified:
- 32 tests pass with `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro` (test_external_evaluator + test_cj_001 + test_cj_006 + test_b4)
- `family_from_model('deepseek/deepseek-v4-pro')` returns `'deepseek'`
- `check_family_segregation('deepseek/deepseek-v4-pro', 'qwen/qwen3-8b')` returns `('deepseek', 'qwen')` — invariant holds

Codex never reached a verdict block (ran out of run-loop budget on shell-syntax exploration). All substantive review work is in iter_1.

## Iter 2 ask: verdict-only

Do NOT run more pytest. Tests already verified pass per iter 1. Just confirm the brief Plan section is correct + emit the verdict. Plan steps 1-7 are unchanged from iter 1.

---



```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-bug-086 — DeepSeek V4 Pro generator-default swap (OpenRouter path). User directive 2026-05-08: "V4 Pro" after I confirmed `deepseek/deepseek-v4-pro` is on OpenRouter (released 2026-04-24, MIT license, 1.05M context, $0.435 in / $0.87 out per M tokens).
- **Hardware path (I-phase0-006) remains user-blocked** — this Issue ships ONLY the OpenRouter-side model swap. Sovereign V4 hosting on OVH H200 is a separate Issue still pending procurement.
- **Two-family invariant verified:** `deepseek/deepseek-v4-pro` matches the existing `_FAMILY_PREFIXES["deepseek"]` prefix `("deepseek/", "deepseek-ai/")`. Family stays "deepseek". Evaluator stays `qwen/qwen3-8b` ("qwen" family). `check_family_segregation` passes.
- **Substrate today:**
  - `src/polaris_graph/llm/openrouter_client.py:240-243` defines `PG_GENERATOR_MODEL` env-var default (currently `deepseek/deepseek-v3.2-exp`).
  - `_PRICE_TABLE_USD_PER_M` (line 121-136) uses generic `"deepseek/"` prefix at $0.27/$0.38. V4 Pro is more expensive ($0.435/$0.87); generic price under-imputes by ~2× and weakens the budget guard. Need V4-specific entries inserted BEFORE the generic `"deepseek/"` line (dict iteration order = insertion order, first-match-wins per line 166-169).
  - `.env.example:59,67` carries the V3.2 default.
  - `src/polaris_graph/llm/openrouter_client.py:202` (rationale doc) and `:336` (error-msg recommended pair) reference V3.2.
  - `src/polaris_graph/evaluator/external_evaluator.py:30` doc comment.
- **Substrate-honest framing:** swap is a config-default change. Existing CJ-001 (two-family) and CJ-006 (budget cap) tests still hold (they pin invariants, not specific model versions). Existing tests that assert `"deepseek/deepseek-v3.2-exp"` literally (test_b4, test_audit_ir_loader, test_external_evaluator, test_cj_001/006) reference the old default as a fixture string; they continue to pass because the *invariant under test* is unchanged. They become slightly stale but are not broken.

## Plan

### `src/polaris_graph/llm/openrouter_client.py` (MODIFY)

1. Insert V4-specific price entries BEFORE the generic `"deepseek/"` line (line ~123):
```python
_PRICE_TABLE_USD_PER_M: dict[str, tuple[float, float]] = {
    # model prefix  :  (input $/M, output $/M)
    # IMPORTANT: longer prefixes first (dict insertion order = iteration
    # order, first-match-wins per _impute_cost_from_tokens line 166).
    "deepseek/deepseek-v4-pro":   (0.435, 0.87),
    "deepseek/deepseek-v4-flash": (0.14, 0.28),
    "deepseek/":                  (0.27, 0.38),
    ...
```

2. Update `PG_GENERATOR_MODEL` default at line ~240-243:
```python
PG_GENERATOR_MODEL = os.getenv(
    "PG_GENERATOR_MODEL",
    "deepseek/deepseek-v4-pro",
)
```

3. Update rationale doc-comment around line 202 — replace V3.2 paragraph with V4 Pro note (released 2026-04-24, 1.05M context, MIT license, OpenRouter path; sovereign V4 hosting still pending I-phase0-006 hardware decision).

4. Update error-msg recommended pair at line ~336: `deepseek/deepseek-v4-pro (generator) + qwen/qwen3-8b (evaluator)`.

### `src/polaris_graph/evaluator/external_evaluator.py` (MODIFY)

5. Line 30 doc comment: `PG_GENERATOR_MODEL (default deepseek/deepseek-v4-pro)`.

### `.env.example` (MODIFY)

6. Lines 59 + 67: change `deepseek/deepseek-v3.2-exp` → `deepseek/deepseek-v4-pro`.

### Tests

7. **NEW** `tests/polaris_graph/test_deepseek_v4_pricing.py` (~30 LOC, 3 tests):
   - V4 Pro price imputation matches $0.435/$0.87 (NOT the generic $0.27/$0.38).
   - V4 Flash price imputation matches $0.14/$0.28.
   - V4 Pro family resolves to "deepseek" so `check_family_segregation` against `qwen/qwen3-8b` passes.

### Existing tests (NO CHANGE)

8. CJ-001 (`test_cj_001_two_family_segregation.py`): still passes — uses `"deepseek/deepseek-v3.2-exp"` as a fixture string testing the family-segregation logic. Logic unchanged; old model name still resolves to "deepseek" family.
9. CJ-006 (`test_cj_006_budget_imputation.py`): still passes — uses `"deepseek/deepseek-v3.2-exp"` to test budget logic at $0.27/$0.38 generic prefix. Logic unchanged.
10. Other tests referencing v3.2-exp string remain stale-but-passing fixtures. Cleanup is a separate doc-hygiene Issue.

## Risks for Codex Red-Team

1. **Price-table ordering** — Python dicts preserve insertion order; iteration in `_impute_cost_from_tokens:166-169` is first-match-wins. V4-specific entries MUST be before the generic `"deepseek/"` entry. Test 1 in the new test file pins this.
2. **Two-family invariant preserved** — V4 Pro starts with `"deepseek/"` so `family_from_model` returns `"deepseek"`, identical to V3.2. Evaluator stays Qwen. Test 3 in new file pins this.
3. **Cost guard tightened, not weakened** — V4 Pro is MORE expensive than V3.2 generic price. The new specific entry tightens the budget guard (imputes higher cost → triggers `BudgetExceededError` sooner). No silent budget shrink.
4. **No live API call** — this is a default-string change. No re-run of BEAT-BOTH benchmark in this PR (that's a separate cost-bearing operation requiring user $ approval).
5. **§9.4 hygiene** — clean.
6. **CHARTER §3 LOC cap** — ~40 LOC (price table + default + 4 doc-string updates + .env.example + new test file). Under 200.

## Acceptance criteria

1. `_PRICE_TABLE_USD_PER_M` has V4 Pro + V4 Flash entries inserted BEFORE generic `"deepseek/"` line.
2. `PG_GENERATOR_MODEL` default changed to `deepseek/deepseek-v4-pro`.
3. `.env.example` updated.
4. Doc comments + error msg updated.
5. New `tests/polaris_graph/test_deepseek_v4_pricing.py` with 3 tests passes.
6. Existing tests still pass (no break).
7. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-7.

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
