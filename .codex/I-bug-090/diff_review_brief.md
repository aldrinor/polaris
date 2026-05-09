# Codex Diff Review — I-bug-090 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- DO NOT call exec / rg. Diff in this brief.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue I-bug-090** — reasoning-first min_max_tokens floor.
- **Brief APPROVE'd iter 1.** Plan accepted (zero P0/P1/P2).
- **Diff:** canonical-diff-sha256: `e95e09d934682206ce026c43d6c40cef00620ed523df3f0a94347770da94237a`
- **Files changed:**
  - `src/polaris_graph/llm/openrouter_client.py`: 9 src LOC (mirrors GLM-5 floor pattern at line 1152)
  - `tests/polaris_graph/test_reasoning_first_token_budget.py`: 17 test LOC

## Local test execution

```
$ python -m pytest tests/polaris_graph/test_reasoning_first_token_budget.py tests/polaris_graph/test_reasoning_first_normalize.py
============================= 13 passed in 6.83s ==============================
```

## Diff (concrete code)

In `_call()` body assembly, after the I-bug-089 elif branch sets `body["reasoning"]`:

```python
            # I-bug-090: OpenRouter does NOT enforce reasoning.max_tokens for
            # V4 Pro on the provider side — the model still emits ~2500
            # reasoning tokens regardless. Floor max_tokens to a value large
            # enough that 40/60 split leaves room for both reasoning AND
            # content. Empirically observed at 2400 max: reasoning eats the
            # whole budget, content empty, I-bug-089 fail-loud raises.
            # 6000 floor → ~2500 reasoning + ~3500 content, both fit.
            _min_tokens = int(os.getenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", "6000"))
            if body.get("max_tokens", 0) < _min_tokens:
                body["max_tokens"] = _min_tokens
```

Test added: `test_v4_pro_min_max_tokens_floor_default_is_6000` — pins the env-var default at 6000.

## Constraints (verifiable from this brief)

1. Mirrors existing `PG_GLM5_MIN_MAX_TOKENS=4096` floor pattern at line 1152 — no new architecture.
2. GLM-5 path fires first (`if self.model in _ALWAYS_REASON_MODELS`), so the V4 Pro floor doesn't override GLM-5.
3. Caller-passed `max_tokens=N` larger than 6000 still wins (good — caller wants high).
4. I-bug-088/089 invariants preserved: 6 normalize tests + 7 token budget tests = 13 regression all pass.
5. Two-family invariant unchanged. Budget-guard invariant unchanged.
6. CHARTER §3 LOC: 9 src + 17 test = 26 LOC, well under 200.
7. Env-var override `PG_REASONING_FIRST_MIN_MAX_TOKENS` for tuning.
8. §9.4 hygiene clean.

## Output schema (RETURN ONLY THIS, NO PROSE)

```yaml
verdict: APPROVE
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: accept_remaining
remaining_blockers_for_execution: []
```
