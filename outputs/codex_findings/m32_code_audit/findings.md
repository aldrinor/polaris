# M-32 code audit

VERDICT: READY

## Blockers
- none

## Mediums
- none

## Lows / nits
- none

## Notes
Rule #12 in `SECTION_SYSTEM_PROMPT_TEMPLATE` clearly asks for the full first-introduction frame when a named primary study, trial, cohort, experiment, or individually identifiable empirical data source is introduced and the evidence rows carry structured metadata. The rule explicitly includes sample/cohort size, baseline outcome value, comparator/control/background condition, and primary endpoint plus timepoint.

The example template is actionable for a generator model: `[STUDY NAME]`, `[STUDY_DESIGN_SUMMARY]`, `[SAMPLE_SIZE]`, `[OUTCOME]`, `[BASELINE_VALUE]`, `[INTERVENTION]`, `[COMPARATOR]`, `[PRIMARY_ENDPOINT]`, `[TIMEPOINT]`, `[RESULT]`, and `[ev_X]` make the expected sentence structure and citation placement clear.

The rule reads as domain-agnostic. It explicitly covers primary studies, trials, cohorts, experiments, and empirical data sources, and its final sentence names materials papers, cohort studies, and financial filings as non-clinical applications. I found no drug-name hard-codes in rule #12.

The 11 M-32 tests are adequate for this prompt-only change: they verify rule #12 presence, required frame-component terms, placeholder/example coverage, non-clinical generalization, no drug-name hard-coding in the rule segment, and non-regression for M-27 rule #10 and M-29 rule #11. They are static prompt-contract tests, not empirical generation tests, which is appropriate before the V22 sweep.

Non-regression check: rule #10 remains `Multi-source citation (M-27)`, rule #11 remains `Jurisdictional precision (M-29)`, and the template has numbered rules 1 through 12. The full `SECTION_SYSTEM_PROMPT_TEMPLATE` is still reasonable at approximately 1,042 words; rule #12 is approximately 223 words, enough to convey the instruction without making the 12-rule prompt unwieldy.

Verification: `python -m pytest -q tests\polaris_graph\test_m32_claim_frame_prompt.py` passed 11/11, with only a pytest cache warning caused by denied access to `.pytest_cache`.
