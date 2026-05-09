# Claude architect audit — I-bug-088

## Scope vs brief
- Architectural recommendation from iter-1 verdict (Option 5 + Option 3 hybrid, response-shape-centric) implemented as the minimal-viable change.
- New branch in `generate()` recovery path: `elif len(result.reasoning.strip()) >= 100` promotes raw reasoning to content for non-`_ALWAYS_REASON_MODELS` models that emit reasoning-only output (V4 Pro shape).
- Same fall-through replicated inside the COT-2 retry path so a retry that comes back reasoning-only also resolves cleanly.
- 6 unit tests added pinning the public-method invariant + 4 regression cases.
- Follow-on cleanups (helper extraction, registry deletion, FIX-GLM5-COT regex deletion) explicitly DEFERRED per iter-1 verdict's `follow_on_cleanups` list.

## §9.4 hygiene
- No `try: except: pass`.
- No `unittest.mock` imports in `src/`.
- No magic numbers — 100-char threshold has docstring rationale (matches existing FIX-GLM5-COT logic).
- No `time.sleep()`.
- No TODO/FIXME/XXX.
- Tests use `unittest.mock` only in `tests/` (allowed).

## CHARTER §3 LOC
- ~49 src LOC under 200 cap.

## Test execution evidence
```
tests/polaris_graph/test_reasoning_first_normalize.py — 6/6 PASSED
tests/polaris_graph/test_gemma_4_evaluator.py + test_deepseek_v4_pricing.py — 12/12 PASSED total
```

## Verdict
APPROVE.
