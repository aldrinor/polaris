You are auditing M-38 (claim-frame hard constraint rule #12b) as
a code review. Narrow scope.

## Scope discipline

Audit ONLY the M-38 diff. One change to
`SECTION_SYSTEM_PROMPT_TEMPLATE` (new rule #12b inserted between
rule #12 and the EVIDENCE TIER DISCIPLINE block) plus 14 unit tests.

## Context

### V23 gap (Codex DR pass-11 gap #3)

> "Convert efficacy and safety claims into trial-framed statements:
> trial name, N, baseline HbA1c/weight/BMI or population, comparator,
> dose, endpoint, timepoint, effect size, and uncertainty where
> available."

V23 Claim-frames = LOSE_BOTH. Rule #12 (M-32) already asked for
full frames but was often ignored; V23 had sentences like
"SURPASS-2 showed that tirzepatide reduced HbA1c more than
semaglutide [ev_042]" — names trial with 1 frame element.

### M-38 fix

Rule #12b added. Key properties:
- Hard floor: >=3 of {N, baseline, comparator, dose, endpoint,
  timepoint, effect size with uncertainty}.
- If <3 available, the sentence must drop the short-name
  attribution and use generic phrasing ("one phase-3 RCT ...").
- Placeholders only in examples (no real drug names).
- Generalizes: mentions materials-science and cohort-study
  equivalents.

### Bug caught by smoke test during development

First M-38 draft used literal `{...}` curly braces for the
frame-element enumeration. `str.format(title=..., focus=...)`
misparsed them as format placeholders and raised KeyError at
runtime. Unit tests alone missed this — they read the template
string directly. The LLM smoke test surfaced it in the first
call. Pass-2 of the commit:
- Converted `{frame_element_list}` to semicolon-delimited text.
- Added `TestM38PromptFormattability::test_template_format_succeeds`
  so future edits reintroducing curly-braces fail in CI.

### Smoke test evidence (committed in commit message)

DeepSeek V3.2-exp on minimal SURPASS-2 + NMA evidence subset.
Output first sentence has all 7 frame elements. Second sentence
uses generic phrasing for the NMA source.

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - rule #12b inserted between rule #12 (M-32) and the EVIDENCE
    TIER DISCIPLINE block.
tests/polaris_graph/test_m38_trial_framed_claims.py (NEW, 14 tests)
```

Do NOT read:
- archive/, outputs/ (except outputs/_m38_smoke2.txt if curious)
- competitor PDFs, loopback/
- earlier M-NN test files that have the `from polaris_graph.`
  import bug (pre-existing orthogonal issue)

## What to verify

1. **Format safety**. Does the rule body contain any `{...}`
   literal that would break `.format(title=..., focus=...)`?
   My test `test_template_format_succeeds` guards against this,
   but audit the rule text for other format-string hazards
   (unmatched braces, `%`-style format specifiers, newlines that
   could be construed as directives).

2. **Generalization discipline**. The rule names clinical examples
   (phase-3 RCT, GLP-1, tirzepatide in the BAD-example rewrite
   for illustration — but the BAD-example text uses [STUDY NAME]
   / [INTERVENTION] placeholders). Is the rule body sufficiently
   domain-agnostic? Compare against the pre-existing M-32 test
   `test_no_drug_name_hardcoded` which scans the combined #12+#12b
   segment. The full-suite test (156/156 pass) implies it holds,
   but eyeball the rule for drift.

3. **Rule interaction**. Rules #12 (M-32) and #12b (M-38) are meant
   to read as a COMPOUND constraint — #12 asks for the full frame
   when metadata is available; #12b adds the hard floor and the
   "drop the name" fallback. Does the combined reading produce
   contradictions? (I don't think so — #12 says "if metadata carries
   frame elements, emit them"; #12b says "if cited evidence doesn't
   support >=3 frame elements, don't name the study." Same
   direction, different contrapositives.)

4. **False positives**. Could a sentence that names a FAMOUS or
   "foundational" study that everyone assumes everyone knows —
   e.g., "the Framingham cohort" — fail #12b even though the
   cited evidence doesn't re-state N and baseline because they're
   assumed? The rule would require dropping the name, producing
   "a prospective cohort of middle-aged adults [ev_X]" which
   loses information. Is this an acceptable trade-off or a
   regression risk?

5. **Prompt length**. Rule #12b is ~1500 chars. The full
   SECTION_SYSTEM_PROMPT_TEMPLATE is now ~12K chars. DeepSeek
   V3.2-exp has 128K context; plenty of room, no concern. But
   flag if you see the prompt approaching any model's tighter
   limits.

6. **Smoke-test evidence**. The commit message claims the pass-2
   smoke test output contains 7 frame elements in the SURPASS-2
   sentence. Outputs/_m38_smoke2.txt has the raw LLM response —
   if worth checking, read it and verify the claim.

## What counts as a blocker vs medium

- **BLOCKER**: a format-string hazard in the rule body; a
  prompt-parser edge case (e.g., unescaped delimiter that matches
  <<<evidence:...>>> detection); a contradiction with rule #12 that
  makes the combined reading ambiguous.
- **MEDIUM**: tighter examples; additional generalization domains
  (policy, finance); a deterministic post-check proposal to
  complement the prompt rule.
- **LOW**: wording, comment clarity.

## Deliverable

Write `outputs/codex_findings/m38_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-sentence note on whether the compound #12+#12b reads as a
  coherent pair.
