# Codex Brief Review — I-cj-006 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-006 — Budget cap Crown Jewel test. Scope: `_impute_cost_from_tokens` backstops token-only responses. Acceptance: test green. LOC estimate 70.
- **Substrate today:** `src/polaris_graph/llm/openrouter_client.py::_impute_cost_from_tokens` (lines 141-173):
  - Clamps negative token counts to 0 (defensive against corrupted API response per CLAUDE.md §9.1.6).
  - Returns 0.0 when all token counts are 0.
  - Uses `_PRICE_TABLE_USD_PER_M` lookup (deepseek/qwen/glm/llama/etc.) with `_DEFAULT_PRICE_PER_M = (3.00, 15.00)` Opus-tier fallback.
  - Reasoning tokens bill at output rate.
  - Cost = (input/1M × input_rate) + ((output + reasoning)/1M × output_rate).
- **Honest framing per CLAUDE.md §9.4:** ship `tests/crown_jewels/test_cj_006_budget_imputation.py` that pins CLAUDE.md §9.1.6 ("budget cap holds even without `usage.cost` — `_impute_cost_from_tokens` backstops token-only responses; negative tokens clamp to zero"). Six tests:
  1. Known model (deepseek) — imputes positive cost matching published rates.
  2. Unknown model — uses default Opus-tier fallback ($3 in / $15 out).
  3. Zero tokens → 0.0.
  4. Negative tokens clamp to zero (the critical defense).
  5. Reasoning tokens bill at output rate, not input rate.
  6. Empty model name → uses fallback.

Update `docs/crown_jewels.md` row 6.

## Plan

### `tests/crown_jewels/test_cj_006_budget_imputation.py` (NEW, ~75 LOC, 6 tests)

```python
"""Crown Jewel I-cj-006 — Budget cap holds without usage.cost.

Per CLAUDE.md §9.1.6: when OpenRouter omits usage.cost,
_impute_cost_from_tokens backstops the token-only response so the
budget guard cannot be silently bypassed. Negative tokens clamp to
zero — a corrupted API response cannot produce a negative cost that
would shrink the accumulated run budget.
"""

from __future__ import annotations
from src.polaris_graph.llm.openrouter_client import _impute_cost_from_tokens


def test_cj_006_known_model_imputes_positive_cost() -> None:
    # deepseek/deepseek-v3.2-exp: $0.27 in / $0.38 out per M tokens
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=1_000_000, output_tokens=1_000_000, reasoning_tokens=0,
    )
    assert cost > 0.0
    # Sanity: roughly input_rate + output_rate; deepseek table value is small.
    assert cost < 5.0


def test_cj_006_unknown_model_uses_fallback() -> None:
    # Unknown prefix → default Opus-tier ($3 in / $15 out) per _DEFAULT_PRICE_PER_M
    cost = _impute_cost_from_tokens(
        "unknown-vendor/some-model",
        input_tokens=1_000_000, output_tokens=1_000_000, reasoning_tokens=0,
    )
    # Should be ~$18 (3 + 15) at exactly 1M each.
    assert 17.0 < cost < 19.0


def test_cj_006_zero_tokens_zero_cost() -> None:
    cost = _impute_cost_from_tokens("deepseek/deepseek-v3.2-exp", 0, 0, 0)
    assert cost == 0.0


def test_cj_006_negative_tokens_clamp_to_zero() -> None:
    # Critical defense: negative tokens MUST NOT produce negative cost
    # that silently shrinks the accumulated run budget.
    cost = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=-5_000_000, output_tokens=-3_000_000, reasoning_tokens=-1_000_000,
    )
    assert cost == 0.0


def test_cj_006_reasoning_tokens_bill_at_output_rate() -> None:
    # Reasoning tokens bill at output rate (matches OpenAI/Anthropic practice).
    out_only = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=0, output_tokens=2_000_000, reasoning_tokens=0,
    )
    out_plus_reasoning = _impute_cost_from_tokens(
        "deepseek/deepseek-v3.2-exp",
        input_tokens=0, output_tokens=1_000_000, reasoning_tokens=1_000_000,
    )
    assert abs(out_only - out_plus_reasoning) < 1e-9


def test_cj_006_empty_model_uses_fallback() -> None:
    cost = _impute_cost_from_tokens("", input_tokens=1_000_000, output_tokens=0, reasoning_tokens=0)
    # Default fallback input rate is $3 per M.
    assert 2.5 < cost < 3.5
```

### `docs/crown_jewels.md` (MODIFY)

Update row 6: test path → `tests/crown_jewels/test_cj_006_budget_imputation.py`; bound function → `src/polaris_graph/llm/openrouter_client.py::_impute_cost_from_tokens`.

## Risks for Codex Red-Team

1. **Magic-number sensitivity** — test 2 expects `$17 < cost < $19` for unknown model at 1M+1M tokens × ($3 in + $15 out) = $18. Test 6 expects `$2.50 < cost < $3.50` for 1M input × $3 = $3. Bounds are loose enough to absorb any future re-pricing of `_DEFAULT_PRICE_PER_M` while still catching a regression that would silently zero out the fallback.
2. **Negative-clamp tooth** — test 4 is THE critical Crown Jewel binding: a corrupted response with -5M tokens must produce 0.0, not a negative cost that would silently expand the run budget by reducing accumulated total.
3. **Substrate-honest** — pure-function pinning.
4. **§9.4 hygiene** — clean.
5. **CHARTER §3 LOC cap** — ~75 LOC under 200.

## Acceptance criteria

1. New `tests/crown_jewels/test_cj_006_budget_imputation.py` with 6 tests.
2. `docs/crown_jewels.md` row 6 updated.
3. All 6 tests pass.
4. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-4.

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
