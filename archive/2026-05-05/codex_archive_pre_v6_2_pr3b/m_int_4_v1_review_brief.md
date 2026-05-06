# Codex round 1 — M-INT-4 v1

## Scope
M-D5 phase 2 substrate (LLMScopeEligibilityClassifier + ScopeAffinityLLM Protocol)
+ NEW production-class OpenRouterScopeAffinityLLM wired into sweep telemetry path.

## Acceptance bar
1. ✅ Imported (`OpenRouterScopeAffinityLLM`, `LLMScopeEligibilityClassifier`,
   `LLMScopeEligibilityClassifierConfig`, `LLMVerdict`)
2. ✅ Invoked (`_classify_scope_with_llm` from run_one_query
   alongside run_scope_gate)
3. ✅ Run-log evidence (per-run `[M-INT-4] scope_llm: verdict=... confidence=...`)
4. ✅ Rollback flag PG_USE_LLM_SCOPE=0 disables (default 0)
5. ✅ Failure does NOT raise (per LAW II)

## Production class details
- Lazy-imports OpenRouterClient (no httpx pull-in until used)
- Per-call random 16-hex delimiter for prompt-injection defense
- Worker-thread isolation pattern from auto_induction.llm_inductor:
  parent contextvars copied to worker, cost ContextVar delta
  written back to parent on success AND failure (so
  PG_MAX_COST_PER_RUN budget cap accumulates LLM cost even on retry-bill paths)
- Strict JSON parser with UNCERTAIN fallback on malformed output
- Unsupported domain returned by LLM → coerced to out_of_scope
  per Protocol contract

## v1 caveat
- Telemetry only — does NOT gate retrieval. Real LLM-driven scope
  rejection is deferred to a later integration (Phase E2 / E4
  hardening) once we have prod monitoring on the LLM verdict
  vs template gate disagreement rate.
- Default rollback flag PG_USE_LLM_SCOPE=0 — keeps existing
  behavior unchanged for production sweeps. Set to 1 explicitly
  to enable.

## Tests
- 6/6 M-INT-4 tests pass
- 41/41 across M-INT-0a..M-INT-4
- 70/70 M-D5 substrate tests still green

Branch: PL-honest-rebuild-phase-1
Commit: e1d9bca

## Verdict
GREEN | PARTIAL | BLOCKED
