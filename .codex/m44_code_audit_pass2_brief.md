M-44 pass-2 audit — closes pass-1 CONDITIONAL findings.

## Pass-1 findings (commit `747b602`)

1. Validator didn't regen (plan required regen + telemetry).
2. Implementation is subset injection, not scorer boost.
3. Injection over-broad across eligible sections.
4. Validator only checked forward adjacent sentence, not previous.

## Pass-2 changes (commit `6b2f9c9`)

**Finding #1 (regen)**: Implemented. After first validator pass,
sections with violations get a regen with augmented focus containing
"REQUIRED: cite [primary_ev_id_1], [ev_id_2] in the same sentence
or immediately adjacent sentence as the trial name." Regen replaces
original if it has fewer violations or if passing + nonzero verified
sentences. Remaining violations after regen emit
`m44_primary_citation_incomplete` telemetry (in
`MultiSectionResult.m44_validator_violations`).

**Finding #3 (over-broad injection)**: Implemented per-anchor
section-affinity. `_m44_anchor_category()` returns
`_cardiovascular` / `_weight` / `_general`.
`_M44_ANCHOR_SECTION_AFFINITY` maps each category to section titles:
- `_cardiovascular`: {safety, long-term outcomes}
- `_weight`: {efficacy, population subgroups, long-term outcomes}
- `_general`: {efficacy, comparative, safety, dose response,
  population subgroups, long-term outcomes}

`_m44_section_matches_anchor()` checks both title and focus.
Focus-based fallback catches `cardiovascular`/`mace`/`cvot` tokens
for CV anchors and `weight`/`obesity`/`bmi` for weight anchors.

**Finding #4 (previous sentence)**: Validator now checks
same + previous + next sentence windows. Test
`test_primary_cited_in_previous_sentence_passes` verifies.

**Finding #2 (scorer vs injection)**: Not implemented. Architectural
deviation acknowledged. The "scorer" would require the outline
planner (LLM) to expose a rankable candidate list, which the current
planner doesn't produce — it emits final ev_ids per section directly.
Adding a scorer would require restructuring the planner call as a
two-pass (candidate → score → pick). V28 scope doesn't include that
refactor. Injection achieves the functional outcome. I'd like your
acceptance of this scope note for M-44.

## Files changed

- `src/polaris_graph/generator/multi_section_generator.py`
  - Added `_M44_ANCHOR_SECTION_AFFINITY`, `_m44_anchor_category`,
    `_m44_section_matches_anchor`.
  - Rewrote `_m44_inject_primaries_into_outline` to use affinity
    check.
  - Extended `_m44_validate_primary_same_sentence` to check
    prev + same + next sentence (was same + next only).
  - Inserted regen loop in `generate_multi_section_report` with
    two validator passes (before regen, after regen).

- `tests/polaris_graph/test_m44_primary_injection_and_validator.py`
  - 4 new tests for section-focus affinity.
  - 1 new test for previous-sentence check.
  - 1 existing test updated to reflect new affinity semantics.

## Test run

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m44_primary_injection_and_validator.py -q` — 34 passed (was 29 pre-pass-2).

Full M-series regression: 247/247.

## Your pass-2 task

Verify pass-2 addresses findings #1, #3, #4 fully. Acceptance of
finding #2 scope note (injection instead of scorer) is a yes/no —
if no, state what scorer refactor you'd require in M-44 pass-3.

Write verdict to
`outputs/codex_findings/m44_code_audit_pass2/findings.md`.
