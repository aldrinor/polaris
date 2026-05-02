M-D2 phase b LLM-augmented inductor review (commit ca4062c).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D2 phase a (keyword stub) is locked. THIS commit ships
phase b: LLMAugmentedInductor that wraps the stub and consults
an LLM classifier on stub-abstain.

Architecture:
  - TemplateAffinityClassifier protocol (slug, confidence, reason)
  - MockTemplateAffinityClassifier (deterministic, broader keywords)
  - OpenRouterTemplateAffinityClassifier (real LLM, $$)
  - LLMAugmentedInductor: base.induce → if accept, return; if
    is_terminal abstain, return; else call LLM; if confidence >=
    floor (0.7), accept LLM slug; else abstain.
  - InductorVerdict.is_terminal (NEW, default False, backward-
    compatible) — keyword stub sets True on disqualifier hits
    so LLM doesn't override domain-specific scope knowledge.

Tests: 58/58 across 3 files. 16 new tests for phase b.

Benchmark on M-D1.5 (43 cases, mock classifier):
  precision=1.000 (was 1.000)
  abstain_recall=0.897 (was 1.000) — 3 false accepts on
    edge cases the mock can't distinguish via keyword overlap
  abstain_precision=1.000 (was 1.000)
  operator_review_load=0.605 (was 0.674) — improvement

The 3 false accepts are clinical-overlay-on-T2DM (amb-06),
hospital-pharmacy-drug-pricing (amb-13), state-vs-federal IRA
(amb-15). Real LLM with scope-aware prompt should recover
abstain_recall.

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Architecture soundness**: is the protocol-based classifier
   pluggable design correct? Any baked-in assumptions that
   would block a fundamentally different M-D2 phase c (e.g.
   embedding similarity)?

2. **is_terminal design**: does propagating "this is a hard
   abstain" from stub to augmenter make sense, or does it leak
   stub-specific concerns into the InductorVerdict abstraction?

3. **Mock classifier coverage tradeoff**: is the 0.897
   abstain_recall acceptable given the mock's role as a test
   fixture? Real LLM is expected to do better — but the
   benchmark claim is anchored to the mock today.

4. **OpenRouter classifier prompt + JSON parsing**: review the
   `_SYSTEM_PROMPT`, `_SLUG_DESCRIPTIONS`, and
   `_parse_classifier_json` for prompt injection risks, JSON
   tolerance, and slug-validation gaps.

5. **Cost / determinism**: temperature=0.0 set for
   reproducibility. Any other hidden non-determinism (e.g.
   asyncio.run() pattern) that could cause flaky CI?

6. **Backward compat**: InductorVerdict gained `is_terminal`
   field. Any callsite that passes positional args could now
   break? (Should be all-keyword.)

## Output

`outputs/codex_findings/md2_llm_review/findings.md`:

```markdown
# Codex review of M-D2 phase b (commit ca4062c)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [architecture concern, if any]
- [is_terminal design concern, if any]
- [mock classifier tradeoff acceptability]
- [OpenRouter prompt / parser issue, if any]
- [non-determinism risk, if any]
- [backward-compat issue, if any]

## Final word
GREEN to lock M-D2 phase b / PARTIAL with edits.
```

Be terse. Under 60 lines.
