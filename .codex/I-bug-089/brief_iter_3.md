# Codex Brief — I-bug-089 (ITER 3 of 5) — implementation-plan APPROVE check

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1 against THIS plan.
```

## Iter-2 outcome

You recommended **Option E (hybrid D + C) at `openrouter_client._call`, ~80 LOC**:
> "Hybrid D + C is the correct fix because it prevents the starvation path first by reserving budget for content, then preserves the budget-guard invariant if OpenRouter or a model still returns truncated planning."

Test surface you specified:
1. `reasoning_cap_sent_for_reasoning_first_when_reasoning_disabled`
2. `truncated_reasoning_without_provenance_fails_loud`
3. `capped_reasoning_answer_still_promotes_without_regressing_i_bug_088`

## Implementation plan (specific, ready to code)

### Change 1 — Option D: reserve content budget at `_call()` body assembly

In `_build_request_body()` (where the request body is constructed in `_call`), when:
- `model in _REASONING_FIRST_MODELS` (NEW set: includes `_ALWAYS_REASON_MODELS` ∪ `{deepseek/deepseek-v4-pro, deepseek/deepseek-v4-flash}`)
- AND `reasoning_enabled=False`
- AND `reasoning.max_tokens` not already set

Add to body:
```python
body["reasoning"] = {
    "exclude": False,
    "max_tokens": max(int(max_tokens * 0.4), 100),  # reserve 60% for content
}
```

This forces OpenRouter to cap reasoning at 40% of total budget so 60% remains for content.

### Change 2 — Option C: fail-loud in I-bug-088 branch on planning-only output

At `openrouter_client.py:1922` (post-PR-339 I-bug-088 branch). BEFORE promoting reasoning to content, check:
- `"[#ev:" not in result.reasoning` (no provenance marker found anywhere)
- AND `not result.reasoning.rstrip().endswith((".", "!", "?", '"'))` (mid-sentence truncation)

If BOTH conditions: raise `RuntimeError(f"V4 Pro / reasoning-first model {self.model} truncated mid-planning. content empty, reasoning has {len(result.reasoning)} chars but no provenance markers and ends mid-sentence — increase max_tokens budget. SF-15 fail-loud.")`. The caller (multi_section_generator) catches this and either retries with bigger budget or surfaces failure.

If EITHER condition fails (e.g. reasoning has `[#ev:` markers or ends in punctuation), keep existing I-bug-088 promotion behavior — that's the legitimate "answer in reasoning" case.

### Change 3 — `_REASONING_FIRST_MODELS` registry

Add a new module-level frozenset that's the union of `_ALWAYS_REASON_MODELS` plus the explicit DeepSeek V4 family models. Used only by the new `_call()` request-body code path. Does NOT replace `_ALWAYS_REASON_MODELS` (which is used by recovery code). Conservative: keeps two registries semantically distinct.

```python
_REASONING_FIRST_MODELS = frozenset({
    *_ALWAYS_REASON_MODELS,
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
})
```

### Test surface (matches your iter-2 spec)

1. `test_reasoning_cap_sent_for_reasoning_first_when_reasoning_disabled` — assert request body includes `reasoning.max_tokens = max_tokens * 0.4` for `deepseek/deepseek-v4-pro` model with `reasoning_enabled=False`.
2. `test_truncated_reasoning_without_provenance_fails_loud` — mock V4 Pro returning content="" + reasoning=900 chars (no `[#ev:` and ends "Let's now write" without period) → assert RuntimeError raised.
3. `test_capped_reasoning_answer_still_promotes_without_regressing_i_bug_088` — mock V4 Pro returning content="" + reasoning=300 chars containing `[#ev:ev_001:0-50]` and ending "...HbA1c reduction." → assert content == reasoning (I-bug-088 promote path preserved).
4. Regression: existing 6 I-bug-088 unit tests in `test_reasoning_first_normalize.py` must still pass.

### LOC budget

- 3 src LOC: `_REASONING_FIRST_MODELS` definition
- ~15 src LOC: reasoning_cap injection in body assembly
- ~12 src LOC: fail-loud check in I-bug-088 branch
- ~50 test LOC: 3 new unit tests
- Total: ~80 LOC src + tests, under CHARTER §3 200 cap.

## Acceptance criteria

- All existing I-bug-088 tests pass (regression).
- 3 new I-bug-089 tests pass.
- §9.4 hygiene clean.
- Two-family invariant + budget-guard invariant unchanged.
- Live V4 Pro probe call no longer empties content (validate with the existing `scripts/pg_smoke_v4_pro_reasoning_first.py`).

## What I want from you, immediately

Return ONLY the verdict block. APPROVE if the plan above resolves the token-starvation root cause without regressing I-bug-088. REQUEST_CHANGES with specific P0/P1 blockers if not.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [list]
continuing_p0: [list]
p1: [list]
p2: [list]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [list]
```
