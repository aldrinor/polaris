You are auditing M-29 (jurisdictional-precision prompt rule) as a
code review BEFORE V19 full-scale sweep runs. This is a code audit,
not a DR content audit.

## Context

Codex DR audit pass 9 verdict on V18: MATERIAL-GAPS. V18 has 33/35
citations FAITHFUL, 12/12 regulatory citations verified, but one
sentence ("A key safety warning from both agencies is a boxed warning
for risk of thyroid C-cell tumors...") overclaims jurisdictional
equivalence while citing only FDA labels. EMA SmPC does not have
that formal contraindication framing.

## What M-29 does

Adds rule #11 to SECTION_SYSTEM_PROMPT_TEMPLATE in
`src/polaris_graph/generator/multi_section_generator.py`. The rule
tells the generator to attribute multi-jurisdiction regulatory
claims to their specific jurisdiction, with a placeholder "Jurisdiction
A / B" example (not hard-coded to FDA/EMA). Forbids generic plurals.

Claude claims:
- No hard-coded agency names in the rule block itself.
- Rule uses placeholder "Jurisdiction A / Jurisdiction B" wording.
- Rule enumerates banned phrases: "both agencies", "all regulators",
  "authorities generally", "regulators require", "jurisdictions
  mandate".
- 8 unit tests cover rule presence + generalization constraints.
- Total tests: 707 (699 pre-M-29 + 8 new).

## Your task

1. **Read the rule block**. Confirm the rule text actually conveys
   the intended constraint and is domain-agnostic. Look for any
   leaked agency names inside the rule block (FDA, EMA, Health Canada,
   NICE, SEC, FTC, etc.) — these would break generalization.

2. **Confirm the tests are real tests, not tautologies.** Specifically:
   - `test_rule_uses_placeholder_jurisdictions_not_real_agencies`
     extracts the rule block and checks for forbidden terms. Verify
     the extraction logic is correct (uses `find("Jurisdictional
     precision")` and bounds the rule block before the next major
     heading). If the extraction is wrong, the test passes trivially.

3. **Consider: could a future prompt edit introduce FDA/EMA/etc.
   into the rule block and still pass the test?** If yes, the
   generalization-guard test is weak. Suggest strengthening.

4. **Regression risk.** Rule #11 adds ~170 words to the section
   system prompt. Risk: prompt now longer; could the additional
   instruction distract the LLM from rules #1-10, causing section
   writing regressions (e.g., lower citation density, missing
   numbers)? This is speculative but worth flagging.

5. **Runtime verifier deferred.** Claude noted M-29b (runtime
   verifier for generic-plural-with-single-jurisdiction patterns)
   is deferred pending V19 result. Do you agree with the order, or
   should M-29b land before V19? Rationale for your position.

6. **Generalization cross-domain check.** Imagine the pipeline
   answers a policy query ("What do FDA and EMA say about AI-enabled
   medical devices?") or a DD query ("What do SEC and FTC say about
   Novo Nordisk?"). Does M-29 help those queries too, or only the
   clinical tirzepatide one?

## Verdict format

Write to `outputs/codex_findings/m29_code_audit/findings.md`:

```
---
audit_type: code_review_pre_sweep
fix: M-29 (jurisdictional-precision prompt rule)
commit_range: <latest_commit>..HEAD
verdict: READY | CONDITIONAL | NOT_READY
blockers: <int>
mediums: <int>
---
```

Verdict rules:
- READY: no blockers, ≤2 mediums with documented mitigations.
- CONDITIONAL: zero blockers but ≥3 mediums.
- NOT_READY: any blocker.

Final verdict sentence: "M-29 may / may not proceed to V19 sweep."

If READY, Claude launches V19 immediately.
