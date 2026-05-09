# Claude architect audit — I-bug-089

## Scope vs brief
- Codex iter-4 APPROVE'd Option E (hybrid D+C) at openrouter_client._call, ~80 LOC.
- Implemented as 3 changes:
  1. `_REASONING_FIRST_MODELS` registry (3 LOC).
  2. Reasoning cap in `_call()` body assembly when `reasoning_enabled=False` for V4 Pro/Flash and GLM-5 family (~14 LOC). Sets `reasoning.max_tokens = max(int(max_tokens * 0.4), 100)`.
  3. Fail-loud check in I-bug-088 promote branch (~12 LOC). Raises RuntimeError when reasoning lacks `[#ev:]` markers AND ends mid-sentence — caller can retry with bigger budget instead of accepting the planning prelude.

## §9.4 hygiene
- No `try: except: pass`.
- No `unittest.mock` imports in `src/`.
- 0.4 ratio has docstring rationale (40% reasoning / 60% content reserve, per Codex iter-2 spec).
- Both-condition fail-loud guard preserves I-bug-088 promote path on legit answers (regression tests pin this).

## CHARTER §3 LOC
- 46 src LOC well under 200 cap.
- 178 test LOC (cap counts src not tests).

## Test execution evidence
```
$ python -m pytest tests/polaris_graph/test_reasoning_first_token_budget.py tests/polaris_graph/test_reasoning_first_normalize.py
12 passed in 6.67s
```

## Verdict
APPROVE.
