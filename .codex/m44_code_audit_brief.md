M-44 audit — third of 7 V28 bundle items. Narrow scope.

## Commit

`747b602` PL: M-44 — scorer/subset primary boost + same-sentence validator

## Plan reference

`outputs/audits/v27/fix_plan_v28.md` M-44 (pass-2). Codex pass-2 verbatim:

> "Before prompting, section evidence selection must boost M-42e
> primary rows for Efficacy, Comparative, Safety, Weight Loss, and
> Cardiovascular sections when the row's anchor matches the section
> focus or query terms. The generator validator then enforces
> citation for section-relevant primary rows."

And verbatim test requirement:

> "Given a section subset candidate pool containing SURPASS-2
> primary, SURPASS-2 post-hoc, and a meta-analysis, the
> selected/prompted subset includes the primary ahead of
> derivatives, and the generated/validated prose cites the primary
> when naming SURPASS-2."

And verbatim validator scope:

> "For each named trial mentioned in the section, if a matching
> M-42e primary ev_id is present in the section subset, that
> primary ev_id must be cited in the same sentence or immediately
> adjacent sentence."

## What changed

`src/polaris_graph/generator/multi_section_generator.py`:
- `_M44_PRIMARY_ELIGIBLE_SECTIONS` set (efficacy, safety, comparative,
  dose response, population subgroups, long-term outcomes).
- `_m44_section_is_primary_eligible(title)` accepts literal set +
  weight/obesity/adipose/bmi tokens.
- `_m44_detect_primary_ev_ids(evidence_pool, anchors)` returns
  dict[anchor → list[ev_id]] using `_m42e_detect_primary_for_anchor`
  from the selector.
- `_m44_inject_primaries_into_outline(plans, primaries, max_cap=20)`
  prepends primary ev_ids into eligible sections. Swap at cap.
- `_m44_find_trial_mentions(text, anchors)` word-boundary regex match.
- `_m44_sentence_spans(text)` simple `.!?` splitter.
- `_m44_validate_primary_same_sentence(text, primaries, biblio)`
  returns list of violations.

In `generate_multi_section_report`:
- After outline parse: call `_m44_detect_primary_ev_ids` +
  `_m44_inject_primaries_into_outline`. Log injected/swapped counts.
- After per-section generation: call
  `_m44_validate_primary_same_sentence` on each primary-eligible
  section's verified_text; accumulate violations into
  `m44_validator_violations` list (telemetry only for V28).

## Test coverage

`tests/polaris_graph/test_m44_primary_injection_and_validator.py`
— 29 tests. 231/231 regression across M-32/35/41/42/43/44/46/48.

## What to audit

1. **Codex acceptance test**: does
   `test_codex_acceptance_primary_prepended_over_derivatives` match
   your verbatim requirement? Primary at position 0, derivatives
   follow, injection telemetry recorded.
2. **Section eligibility**: per your plan, Efficacy/Safety/
   Comparative/Weight get injection; Regulatory/Mechanism/
   Limitations excluded. Does my set match?
3. **Validator correctness**:
   - Same-sentence match → pass ✓
   - Adjacent-sentence match → pass ✓ (per your verbatim)
   - Two-sentence gap → fail ✓
   - Wrong ev_id cited → fail ✓
4. **Word-boundary**: `SURPASS-10` must not match `SURPASS-1` anchor.
   Tested — PASS.
5. **Mechanism section excluded** (M-47 handles mechanism cites).
   Tested — PASS.
6. **Regen not implemented**: I explicitly deferred regen on
   validator failure to V29 scope (requires _run_section refactor).
   The injection step + telemetry is the V28 intervention. Is this
   acceptable per the plan, or does V28 require regen to ship?

## Output

Write verdict to `outputs/codex_findings/m44_code_audit/findings.md`.
READY | CONDITIONAL | BLOCKED. On READY/CONDITIONAL-no-blockers:
Claude proceeds to M-45 (refetch diagnostics + targeted acquisition).
