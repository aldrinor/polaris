---
audit_type: code_review_pre_sweep
fix: M-29 (jurisdictional-precision prompt rule)
commit_range: c7f4235df66dd808a0c2d18500de2cc001f998d2..HEAD
verdict: READY
blockers: 0
mediums: 2
---

## Scope

Reviewed M-29 as a code audit before the V19 sweep, focused on the prompt-template change and its unit-test guardrails rather than DR content correctness.

Reviewed files:

- `src/polaris_graph/generator/multi_section_generator.py`
- `tests/polaris_graph/test_m29_jurisdictional_precision.py`

Verification run:

- `PYTHONPATH=src python -m pytest tests\polaris_graph\test_m29_jurisdictional_precision.py -q`
- Result: 8 collected, 8 passed.

Note: plain `pytest` is not on PATH in this shell, and `python -m pytest` needs `PYTHONPATH=src` for this repo layout.

## Findings

### No blockers

M-29 implements the intended prompt constraint. Rule #11 tells the generator to attribute regulatory, standards-setting, or governance assertions to the specific jurisdiction/source that supports them, and to avoid collapsing evidence into generic plural language unless each referenced jurisdiction is cited in the same sentence.

The rule block is domain-agnostic in the implementation reviewed. It uses `Jurisdiction A` / `Jurisdiction B` placeholders and does not leak hard-coded agency or product names such as FDA, EMA, Health Canada, NICE, SEC, FTC, Mounjaro, or tirzepatide inside the rule text.

The banned generic-plural phrases claimed by Claude are present: `both agencies`, `all regulators`, `authorities generally`, `regulators require`, and `jurisdictions mandate`.

The rule is not limited to the V18 tirzepatide defect. It explicitly covers regulatory, standards-setting, governance, countries, agencies, courts, and rulemaking bodies. That should help cross-domain prompts such as FDA/EMA policy synthesis on AI-enabled medical devices and SEC/FTC due-diligence synthesis, because the same failure mode is unsupported equivalence across authorities. The clinical boxed-warning example is specific in shape, but not hard-coded to a named clinical product or regulator.

### Medium 1: generalization guard is useful but not exhaustive

`test_rule_uses_placeholder_jurisdictions_not_real_agencies` is a real test, not a tautology. It extracts a slice of `SECTION_SYSTEM_PROMPT_TEMPLATE` from the first `11.` through `EVIDENCE TIER DISCIPLINE`, then checks that forbidden domain-specific terms are absent from that slice.

The extraction is mostly correct for the current prompt layout, but it differs from the audit brief's expected description: it anchors on `find("11.")`, not `find("Jurisdictional precision")`. In the current template this still captures the M-29 rule correctly. However, it is a brittle structural assumption if future prompt edits renumber rules, add another `11.` earlier, or move the M-29 rule under a different heading.

A future prompt edit could still introduce domain-specific leakage and pass if the leakage uses an unlisted or case-varied form, for example `fda`, `Food and Drug Administration`, `European Medicines Agency`, `MHRA`, `PMDA`, `CMS`, `DOJ`, `CFTC`, `EPA`, or `ECHA`. The current term list catches the common FDA/EMA uppercase case but is not a comprehensive agency-name detector.

Suggested strengthening:

- Extract the rule with a regex anchored to the named rule header, e.g. `r"\n11\. \*\*Jurisdictional precision.*?(?=\n\n[A-Z][A-Z ]+:|\n\d+\. |\Z)"` with DOTALL, or assert the extracted block itself contains `Jurisdictional precision`.
- Normalize case before leak checks.
- Expand aliases to include full agency names and common non-clinical agencies.
- Add a negative fixture-style assertion that injecting `FDA`, `Food and Drug Administration`, and `fda` into the extracted rule block would fail the helper used by the test.

Mitigation for V19: this weakness is in future-edit protection, not in the current M-29 prompt text. It does not block the sweep.

### Medium 2: prompt-length regression risk should be measured in V19

Rule #11 adds a substantial instruction to an already dense section prompt. The risk is speculative but real: extra prompt surface can distract the model from rules #1-10, especially citation density, numeric precision, and every-sentence citation requirements.

Mitigation for V19: compare M-29 outputs against V18 on mechanical metrics that rules #1-10 are meant to protect:

- sentence-level citation coverage
- distinct evidence IDs per section
- citation density per sentence
- numeric claim preservation
- source-tier discipline for clinical claims
- trial-primary-source behavior for named-trial claims

This is monitoring risk rather than a pre-sweep blocker.

## Runtime Verifier Order

I agree with deferring M-29b until after V19. The prompt rule is narrow and directly addresses the known defect, while a runtime verifier for generic plurals with single-jurisdiction evidence is likely to need careful tuning to avoid false positives on legitimate same-sentence multi-source claims. V19 should provide empirical evidence on whether the prompt-only fix is sufficient and what patterns the verifier must catch.

If V19 still shows generic plural claims supported by only one jurisdiction, M-29b should land before the next full sweep, using the observed failures as fixtures.

## Verdict

READY: no blockers, two medium risks with documented mitigations.

M-29 may proceed to V19 sweep.
