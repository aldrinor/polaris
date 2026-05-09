# Codex Diff Review — I-bug-089 (ITER 2 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Iter 1 truncated mid-output (no verdict block produced).
- DO NOT narrate. DO NOT call exec / rg. Read diff, return ONLY yaml verdict.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue I-bug-089** — token-budget-aware request shaping + fail-loud on truncated planning.
- **Brief APPROVE'd iter 4.** Implementation plan was reviewed and accepted (zero P0/P1/P2).
- **Diff:** `.codex/I-bug-089/codex_diff.patch` (canonical-diff-sha256: `42e904c495f0c5a608d20ad15158912be0cbe944681445bf6f76104d9daac710`).

## Diff summary (verbatim from local pytest)

```
$ python -m pytest tests/polaris_graph/test_reasoning_first_token_budget.py tests/polaris_graph/test_reasoning_first_normalize.py
============================= 12 passed in 6.67s ==============================
```

## Diff content (3 changes, ~46 src LOC + 178 test LOC)

**Change 1**: `_REASONING_FIRST_MODELS` registry, superset of `_ALWAYS_REASON_MODELS` plus V4 Pro/Flash.

**Change 2**: in `_call()` body assembly, after the existing `elif reasoning_enabled:` branch, add:
```python
elif self.model in _REASONING_FIRST_MODELS:
    reasoning_dict = {"exclude": False}
    if reasoning_exclude is not None:
        reasoning_dict["exclude"] = reasoning_exclude
    if reasoning_max_tokens is not None:
        reasoning_dict["max_tokens"] = reasoning_max_tokens
    else:
        reasoning_dict["max_tokens"] = max(int(max_tokens * 0.4), 100)
    body["reasoning"] = reasoning_dict
```

**Change 3**: in I-bug-088's `elif len(reasoning.strip()) >= 100:` branch (post-PR-339), BEFORE the LLMResponse construction, add:
```python
_reasoning_clean = result.reasoning.rstrip()
if (
    "[#ev:" not in result.reasoning
    and not _reasoning_clean.endswith((".", "!", "?", '"'))
):
    self.usage.total_errors += 1
    raise RuntimeError(
        f"I-bug-089: reasoning-first model {self.model} truncated mid-planning. "
        f"content empty, reasoning has {len(result.reasoning)} chars but "
        f"no [#ev:] markers and ends mid-sentence — increase max_tokens "
        f"budget. SF-15 fail-loud."
    )
```

**6 unit tests added** in `tests/polaris_graph/test_reasoning_first_token_budget.py`. **Existing 6 I-bug-088 tests** in `test_reasoning_first_normalize.py` pass without change.

## Constraints (verifiable from diff)

1. Two-family invariant: not touched (`check_family_segregation` unchanged).
2. Budget-guard invariant: not touched (`_PRICE_TABLE_USD_PER_M` unchanged).
3. CHARTER §3 LOC: 46 src LOC, under 200 cap.
4. §9.4 hygiene: no `try: except: pass`, no `unittest.mock` in src/, magic 0.4 has docstring.
5. GLM-5 backward compat: `_ALWAYS_REASON_MODELS` branch fires before new `_REASONING_FIRST_MODELS` `elif`, so GLM-5 path is unchanged.
6. Caller override preserved: `reasoning_max_tokens=N` from caller wins over the 0.4× cap.
7. Both-condition guard: RuntimeError fires only when BOTH no-`[#ev:]` AND mid-sentence. Either alone is treated as legit (regression tests pin this).

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

If APPROVE, copy this verdict block as your output verbatim. If REQUEST_CHANGES, return the same schema with the actual P0/P1 blockers listed (one sentence each).
