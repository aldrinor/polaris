# Codex round 2 — M-D5 phase 2 v2

## Round-1 findings to verify closed

[MEDIUM] verdict normalized via .lower().strip() before any
type check — malformed LLMVerdict(verdict=None) raised raw
AttributeError instead of LLMScopeClassifierError.

v2 fix: `isinstance(llm_out.verdict, str)` check first.
Pinned by `test_non_string_verdict_raises_classifier_error`.

[MEDIUM] bool is subclass of int — confidence=True silently
adapted to 1.0, turning malformed LLM output into high-
confidence IN_SCOPE.

v2 fix: explicit `isinstance(llm_out.confidence, bool)`
rejection BEFORE the int/float check. Pinned by
`test_bool_confidence_rejected` (True + False cases).

Tests: 36/36 passing. Threat model boundaries 2 + 4 updated.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-1 fix integration
- [x/ ] MEDIUM verdict type-checked before normalization
- [x/ ] MEDIUM bool confidence rejected

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
