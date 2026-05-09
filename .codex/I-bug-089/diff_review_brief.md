# Codex Diff Review — I-bug-089 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / Get-ChildItem. Diff is below; brief had implementation plan.
```

## Pre-flight

- **Issue:** I-bug-089 — token-budget-aware request shaping + fail-loud on truncated planning.
- **Brief APPROVE'd iter 4** (`.codex/I-bug-089/codex_brief_verdict.txt`). You recommended Option E (hybrid D+C) at `_call`, ~80 LOC.
- **Diff:** `.codex/I-bug-089/codex_diff.patch` (canonical-diff-sha256: `42e904c495f0c5a608d20ad15158912be0cbe944681445bf6f76104d9daac710`).
- **Files changed:**
  - `src/polaris_graph/llm/openrouter_client.py`: 46 LOC src
  - `tests/polaris_graph/test_reasoning_first_token_budget.py`: NEW, 178 LOC tests
- **Total under CHARTER §3 200-LOC src cap.**

## What the diff does

1. **`_REASONING_FIRST_MODELS` registry (3 LOC)** — superset of `_ALWAYS_REASON_MODELS` plus `deepseek/deepseek-v4-pro` and `deepseek/deepseek-v4-flash`.
2. **Option D — reasoning cap in `_call()` body assembly (~14 LOC)** — when calling a model in `_REASONING_FIRST_MODELS` with `reasoning_enabled=False`, set `body["reasoning"]["max_tokens"] = max(int(max_tokens * 0.4), 100)`. Reserves 60% of the budget for content. Caller-passed `reasoning_max_tokens` and `reasoning_exclude` still take precedence.
3. **Option C — fail-loud in I-bug-088 promote branch (~12 LOC)** — at the existing `elif len(reasoning.strip()) >= 100:` branch, before promoting, check `"[#ev:" not in reasoning AND not reasoning.rstrip().endswith((".", "!", "?", '"'))`. If both: raise `RuntimeError("I-bug-089: reasoning-first model X truncated mid-planning... SF-15 fail-loud")`.

## Test surface (matching iter-2 spec)

5 new unit tests in `test_reasoning_first_token_budget.py`:

1. `test_v4_pro_in_reasoning_first_models` — registry membership.
2. `test_glm5_inherited_via_always_reason` — `_REASONING_FIRST_MODELS` superset of `_ALWAYS_REASON_MODELS`.
3. `test_v4_pro_truncated_planning_raises_fail_loud` — pinned RuntimeError on (no `[#ev:]` AND mid-sentence) reasoning.
4. `test_v4_pro_completed_answer_in_reasoning_still_promotes` — regression: legit answer-in-reasoning (with provenance + period) still promotes.
5. `test_v4_pro_provenance_only_promotes_even_if_mid_sentence` — `[#ev:]` presence overrides mid-sentence guard.
6. `test_v4_pro_complete_punct_no_provenance_still_promotes` — completed sentence-end overrides no-provenance guard.

Plus regression: existing 6 I-bug-088 tests in `test_reasoning_first_normalize.py`.

## Local test execution

```
$ python -m pytest tests/polaris_graph/test_reasoning_first_token_budget.py tests/polaris_graph/test_reasoning_first_normalize.py
============================= 12 passed in 6.67s ==============================
```

## Red-team

1. **Both-condition guard** — RuntimeError fires only when BOTH no-provenance AND mid-sentence. Either condition alone is treated as legitimate and promoted (test 5 + test 6 pin this). This avoids false-positive failures on legit edge cases.
2. **Backward compat on GLM-5** — GLM-5 path at `_ALWAYS_REASON_MODELS` branch fires first (same model in both sets). New `_REASONING_FIRST_MODELS` `elif` only runs if not already in `_ALWAYS_REASON_MODELS` AND `reasoning_enabled=False`. GLM-5 unchanged.
3. **Caller override preserved** — if caller passes `reasoning_max_tokens=N`, that wins over the 0.4× cap. Used by tests / callers that want exact control.
4. **0.4 ratio rationale** — Codex iter-2 specified 60% content / 40% reasoning. Magic number documented in code comment, not env-var-gated (structural threshold, not deployment knob).
5. **Two-family invariant unchanged** — no edits to `check_family_segregation` or `_FAMILY_PREFIXES`.
6. **Budget-guard invariant unchanged** — no edits to `_PRICE_TABLE_USD_PER_M` or `_impute_cost_from_tokens`.
7. **§9.4 hygiene clean** — no `try: except: pass`, no `unittest.mock` in src/, no magic numbers without docstring (0.4 has rationale comment), no `time.sleep()`, no TODO.
8. **Existing COT-2 retry path preserved** — sparse reasoning (<100 chars) still triggers retry. Truncated-planning fail-loud only fires when reasoning has >= 100 chars (the I-bug-088 promote branch).

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: []
```
