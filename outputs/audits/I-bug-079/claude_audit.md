# Claude Architect Audit — I-bug-079 (verification-only)

**Branch:** bot/I-bug-079
**LOC:** 0 net source-code changes (verification artifacts only).
**Tests:** 5/5 PASS via `PYTHONPATH=src python -m pytest tests/polaris_graph/scope/test_default_llm_completion_async_fix.py -v`.

## Files

```
.codex/I-bug-079/brief.md, codex_brief_verdict.txt, codex_diff.patch, codex_diff_audit.txt    NEW (codex-excluded)
outputs/audits/I-bug-079/verification.md      NEW (audit-excluded)
outputs/audits/I-bug-079/claude_audit.md      NEW (audit-excluded; this file)
```

## Iter-1 brief P1 fixes

- **P1 #1 (artifacts missing at HEAD when brief filed):** ADDRESSED. `outputs/audits/I-bug-079/verification.md` and this `claude_audit.md` are now in place.
- **P1 #2 (pytest command needs PYTHONPATH=src):** ADDRESSED. `verification.md` records the exact reproducible invocation `PYTHONPATH=src python -m pytest ... -v` with full output.
- **P2 #1 (real-key smoke not equivalent substitute):** ADDRESSED. `verification.md` explicitly labels the real-key smoke as "WAIVED — user-driven follow-up" and the unit-level test as "complementary, NOT equivalent substitute".

## Architecture review

The bug fix at `src/polaris_graph/scope/clinical_classifier.py:214-243` correctly:
1. Detects a running event loop via `asyncio.get_running_loop()` (lines 228-237).
2. Raises RuntimeError when called from async context (lines 232-237).
3. Drives `OpenRouterClient.generate` via `asyncio.run` on the no-loop branch (lines 239-242).
4. Returns `result.content` (or `str(result)` fallback) (line 243).

The 5 regression tests in `tests/polaris_graph/scope/test_default_llm_completion_async_fix.py` cover:
1. Async generate is awaited (mock returning canned LLMResponse).
2. RuntimeError raises inside `asyncio.run()`.
3. End-to-end `llm_fallback_classify` returns `clinical_efficacy` with stub.
4. Returns `uncertain` on client construction failure (no API key).
5. kwargs (`temperature`, `max_tokens`) passed through to `generate`.

## Verdict

APPROVE for Codex diff review.
