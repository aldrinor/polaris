M-D5 phase 1 v2 review (commit ab49015).

**Skip git status.** Codex at gpt-5.4 + xhigh. Use
`python -m pytest -q tests\polaris_graph\test_md5_scope_classifier.py`
not bare `pytest`.

## Context

Round 1 (commit a29a77f): GREEN with 2 LOW findings.

Round 2 closes both:

1. **[LOW] empty-query classifier-invocation hardening** —
   gate now short-circuits empty/whitespace input BEFORE
   invoking classifier. Sentinel ScopeClassification
   (UNCERTAIN @ 0.0, "Empty query — classifier not invoked")
   returned in OPERATOR_REVIEW result. Mirrors M-20 router's
   empty-query handling end-to-end. New tests pin
   classifier.called == False for both "" and "   \n\t ".

2. **[LOW] test pin tightening** —
   - test_in_scope_with_router_unsupported_returns_operator_review
     no longer conditional. Forces UNSUPPORTED via
     floor_review=0.99 + RouterConfig pass-through, then asserts
     OPERATOR_REVIEW + "disagree" rationale unconditionally.
   - test_classifier_returns_wrong_verdict_type_raises renamed to
     test_classifier_returns_classification_with_non_enum_verdict_raises.
     Constructs a real ScopeClassification via __new__ +
     object.__setattr__ with str verdict (not enum) to exercise
     the verdict-enum guard distinctly from the type guard.

3. **Threat model boundary 7** added documenting the
   short-circuit contract.

## Tests

27 passing (was 24; +3):
  - test_empty_query_short_circuits_classifier_invocation
  - test_whitespace_only_query_short_circuits_classifier_invocation
  - test_classifier_returns_classification_with_non_enum_verdict_raises

## Your job

GREEN-LOCK or PARTIAL.

1. **Round-1 fix integration**:
   - [ ] empty-query short-circuit truly bypasses classifier.classify
   - [ ] sentinel ScopeClassification preserves uniform result shape
   - [ ] test_in_scope_with_router_unsupported pins UNSUPPORTED
     branch unconditionally (not `if router.verdict == ...`)
   - [ ] non-enum verdict test exercises the actual enum guard
   - [ ] threat-model boundary 7 matches code

2. **Stop criterion**: GREEN-lock if remaining findings are
   doc nits or follow-ups. PARTIAL only if you find:
     (a) Short-circuit can be bypassed (e.g. unicode whitespace)
     (b) Sentinel introduces a new contract violation
     (c) Test pin still has a hole
     (d) New regression introduced

3. **Phase-2 readiness**: same as round 1.

## Output

`outputs/codex_findings/md5_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D5 phase 1 v2 (commit ab49015)

## Verdict
GREEN

## Round-1 fix integration
- [x/no] empty-query short-circuits classifier invocation
- [x/no] sentinel preserves uniform result shape
- [x/no] router-unsupported branch pinned unconditionally
- [x/no] non-enum verdict guard exercised distinctly
- [x/no] threat-model boundary 7 matches code

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D5 phase 1.
```

Be terse. Under 30 lines.
