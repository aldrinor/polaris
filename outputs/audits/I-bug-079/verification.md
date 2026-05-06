# I-bug-079 Verification

The Issue's binding requirements are already satisfied at HEAD (polaris branch, post-I-f2-008 merge).

## Fix in place

`src/polaris_graph/scope/clinical_classifier.py:214-243` — `_default_llm_completion`:
- Lazy-imports `asyncio` + `OpenRouterClient`.
- Lines 228-237: `asyncio.get_running_loop()` detection; raises RuntimeError when invoked from a running event loop.
- Lines 239-243: `asyncio.run(client.generate(prompt=prompt, temperature=0.0, max_tokens=200))`; returns `result.content` (or `str(result)` fallback).

## Regression tests (5/5 PASS)

Reproducible invocation (PYTHONPATH=src required):

```
cd C:\POLARIS
$env:PYTHONPATH = "src"
python -m pytest tests/polaris_graph/scope/test_default_llm_completion_async_fix.py -v
```

Output:
```
collected 5 items

tests/polaris_graph/scope/test_default_llm_completion_async_fix.py::test_default_llm_completion_awaits_async_generate PASSED [ 20%]
tests/polaris_graph/scope/test_default_llm_completion_async_fix.py::test_default_llm_completion_inside_running_loop_raises PASSED [ 40%]
tests/polaris_graph/scope/test_default_llm_completion_async_fix.py::test_llm_fallback_classify_returns_efficacy_when_llm_works PASSED [ 60%]
tests/polaris_graph/scope/test_default_llm_completion_async_fix.py::test_llm_fallback_returns_uncertain_when_client_construction_fails PASSED [ 80%]
tests/polaris_graph/scope/test_default_llm_completion_async_fix.py::test_default_llm_completion_passes_kwargs_to_generate PASSED [100%]

============================== 5 passed in 4.14s ==============================
```

## Real-key smoke test status

**WAIVED — user-driven follow-up.** The breakdown's "smoke test under real key returns scope_class=clinical_efficacy" requires `OPENROUTER_API_KEY` and a live network call. Per CLAUDE.md §8.4 (resource discipline) + cost concerns, autonomous Issue work does not run real-key smokes. The unit-level test `test_llm_fallback_classify_returns_efficacy_when_llm_works` (test #3 above) covers the same code path with a stubbed `completion_fn` returning a canned `clinical_efficacy` JSON response — this is NOT an equivalent substitute for the real-key smoke; it's a complementary unit-level guard. The real-key smoke is the user's prerogative to run when desired.

## Verdict

The bug is fixed; regression tests are green; the real-key smoke is a user-driven follow-up. APPROVE.
