# Codex round 2 — M-INT-4 v2

## Round-1 close
v1 had 2 Codex-found MEDIUMs. Both fixed in v2 (commit 31a3cb3):

### MEDIUM 1: domain leak on non-IN_SCOPE verdicts (FIXED)
- v1 `_parse_scope_llm_json` preserved `domain="clinical"`
  even when verdict was "out_of_scope" or "uncertain"
- Adapter `LLMScopeEligibilityClassifier.classify` (line 458)
  hard-fails on this shape with "domain must be None"
- Sweep helper caught the exception → dropped telemetry → no
  per-run `[M-INT-4] scope_llm` line
- v2 fix: parser strips `domain=None` when `raw_verdict != "in_scope"`
  at scope_classifier_llm.py:705-706 (just before LLMVerdict construction)

### MEDIUM 2: bool confidence bypass (FIXED)
- v1 `float(raw_conf)` turned JSON `true` into `1.0`
- Adapter has bool guard at line 428 but parser had already coerced
- Malformed `{"confidence": true}` became perfect-confidence telemetry
- v2 fix: explicit `isinstance(raw_conf, bool) → 0.0` BEFORE float coercion
  at scope_classifier_llm.py:687-689

## v2 regression tests
5 new tests:
- test_parse_strips_domain_when_verdict_not_in_scope (M1 repro)
- test_parse_strips_domain_when_verdict_uncertain (M1 corner)
- test_parse_rejects_bool_confidence (M2 repro)
- test_parse_rejects_false_confidence_via_bool_guard (M2 corner)
- test_parse_invalid_verdict_string_strips_domain (M1 + invalid-verdict
  intersection)

## Acceptance bar (re-verify all)
1. ✅ Imported (`OpenRouterScopeAffinityLLM`,
   `LLMScopeEligibilityClassifier`, `LLMScopeEligibilityClassifierConfig`,
   `LLMVerdict`)
2. ✅ Invoked (`_classify_scope_with_llm` from run_one_query
   alongside run_scope_gate)
3. ✅ Run-log evidence (per-run `[M-INT-4] scope_llm: verdict=...`)
4. ✅ Rollback flag PG_USE_LLM_SCOPE=0 disables (default 0)
5. ✅ Failure does NOT raise (per LAW II)
6. ✅ Adapter-contract preserved by parser (M1 + M2 closed)

## Tests
- 11/11 M-INT-4 (6 v1 + 5 v2 regression) pass
- 70/70 M-D5 substrate tests still green

Branch: PL-honest-rebuild-phase-1
Commit: 31a3cb3

## Verdict
GREEN | PARTIAL | BLOCKED
