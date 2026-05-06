M-1 Audit Graph IR loader v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your v2 verdict was STILL-PARTIAL with one remaining edit:

> "methods/provenance bundle completeness: materially better, but not
> fully integrated. evaluator_gate.reasons, rule_blockers, v30_warnings,
> and retrieval counts are now in IR; model/version provenance still is
> not, despite being present in artifact-side provenance files."

That gap is closed in v3. New types loaded from runtime artifacts:

- **ModelProvenance** (from evaluator_rule_checks.json + qwen_judge_output.json):
  generator_family/model, evaluator_family/model, judge_model,
  judge_parse_ok, judge_input_tokens, judge_output_tokens,
  contradictions_disclosed, contradictions_missing, rule_checks
- **RuleCheck**: item_id, name, passed, details (PT01..PT13 in run-14)
- **ProtocolMetadata** (from protocol.json): research_question,
  created_at_iso/unix, scope_decision, expected_tier_distribution
- **TierExpectation**: tier, min_fraction, max_fraction, rationale
  (enables View 5 expected-vs-actual tier comparison)

These files are OPTIONAL (loader returns None on legacy runs that
predate them). Run-14 has all three.

Tests: 42 -> 49. New tests verify:
- Two-family invariant (generator=deepseek, evaluator=qwen)
- Judge model + token counts
- 13 rule checks loaded
- 14 contradictions disclosed
- Protocol research question + created_at + scope_decision
- Expected tier distribution (>=5 tiers)
- Loader handles legacy runs without these files (returns None)

## Your job

Final GREEN check on M-1. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Quick verification:
- Is the model/version provenance gap closed?
- Any new issues introduced by the additions?
- Is M-1 now ready as the foundation for M-2/M-3/M-4/M-5/M-6/M-7?

## Output

Write to `outputs/codex_findings/m1_v3_review/findings.md`:

```markdown
# Codex final review of M-1 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Edit verification
- [x/no] ModelProvenance integrated correctly
- [x/no] ProtocolMetadata integrated correctly
- [x/no] Optional-loading semantics for legacy runs

## New issues introduced
none / list

## M-1 foundation readiness
Are all 5 Inspector views unblocked at the IR layer?

## Final word
GREEN to lock M-1 and proceed to M-2 / STILL-PARTIAL with edits / DISAGREE.
```

Be terse. Under 150 lines. This is the final foundation check.
