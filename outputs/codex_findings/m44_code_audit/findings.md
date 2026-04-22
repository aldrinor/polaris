# M-44 Code Audit Verdict

Verdict: CONDITIONAL

No code-level regression blocker found for the narrow injection + validator-helper behavior: the M-44 unit suite passes locally (`python -m pytest -q tests/polaris_graph/test_m44_primary_injection_and_validator.py`, 29 passed; pytest cache warning only).

However, the implementation is not a full match to `outputs/audits/v27/fix_plan_v28.md` M-44 as written. Claude can proceed to M-45 only if V28 explicitly accepts M-44 as "subset injection + validator telemetry" rather than the full scorer/regen enforcement item.

## Findings

1. Conditional plan deviation: validator does not enforce or regenerate.
   - Plan lines 148-156 require a post-generation validator and "Trigger one regen if validator fails; emit `m44_primary_citation_incomplete` telemetry if still missing."
   - Current code records `m44_validator_violations` and logs them only (`src/polaris_graph/generator/multi_section_generator.py:2098-2131`). The violation list is not returned in `MultiSectionResult`, and no regen is attempted.
   - This means the acceptance phrase "generated/validated prose cites the primary when naming SURPASS-2" is only unit-tested at helper level, not enforced in shipped prose.

2. Conditional plan deviation: this is subset injection, not the planned scorer boost.
   - Plan lines 137-147 specify a `+0.3` scorer boost for primary rows when the row anchor matches section focus, followed by cap-aware subset composition.
   - Current code injects primaries after outline planning (`src/polaris_graph/generator/multi_section_generator.py:2053-2081`) and does not change `_select_evidence_for_section` scoring.
   - This may be acceptable as the practical subset intervention, but it is not the scorer change described in the plan.

3. Medium correctness issue: injection is over-broad across eligible sections.
   - `_m44_inject_primaries_into_outline` flattens all detected primary anchors and prepends each one into every primary-eligible section (`src/polaris_graph/generator/multi_section_generator.py:1785-1830`).
   - The plan says to boost when the row's anchor matches the section focus or query terms. Current behavior does not inspect `plan.focus`, section text, or section-specific candidate terms.
   - At cap, this can displace relevant non-primary evidence with unrelated primaries.

4. Low/medium validator edge case: adjacent sentence is only checked forward.
   - `_m44_validate_primary_same_sentence` checks the sentence containing the trial mention and the next sentence only (`src/polaris_graph/generator/multi_section_generator.py:1936-1948`).
   - The plan says "same sentence or immediately adjacent sentence", which also reasonably includes the previous sentence. A primary cite immediately before the trial-name sentence would currently be flagged.

## Requested Checks

- Codex acceptance test: `test_codex_acceptance_primary_prepended_over_derivatives` matches the subset-order part of the requirement. It asserts primary at position 0, preserves derivatives afterward, and checks injection telemetry from the helper.
- Section eligibility: Efficacy, Safety, Comparative, and Weight are covered; Regulatory, Mechanism, and Limitations are excluded. Cardiovascular is not literal, but `SURPASS-CVOT` can be injected into eligible sections because injection is global.
- Validator basics: same-sentence, following adjacent sentence, two-sentence gap, and wrong ev_id cases are covered and pass.
- Word-boundary: `SURPASS-10` not matching `SURPASS-1` is covered and passes.
- Mechanism exclusion: covered and passes.
- Regen: per the checked-in V28 plan, regen is part of M-44. Deferring it to V29 is acceptable only as an explicit scope change; otherwise M-44 is incomplete.
