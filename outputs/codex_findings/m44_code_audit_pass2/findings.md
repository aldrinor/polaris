# M-44 Pass-2 Code Audit

Verdict: CONDITIONAL.

Pass-2 closes findings #3 and #4. Finding #1 is implemented in structure, but not fully correct because the regen replacement criterion does not actually compare against the first validator pass. Finding #2 scope note is accepted for M-44: I do not require a planner/scorer refactor in pass-3 if the injection path preserves the functional behavior.

## Findings

1. `src/polaris_graph/generator/multi_section_generator.py:2363` - The regen replacement logic never sees the first-pass violation count, so `len(new_viols) < orig_viols_count` is effectively dead. `m44_validator_violations` is initialized empty at line 2281, first-pass violations are used only to append section indexes at lines 2290-2296, and the list is not populated until the final validator pass at line 2379. As a result, `orig_viols_count` is always 0 during regen comparison, and a regen with fewer-but-nonzero violations is rejected even though the pass-2 contract says to replace when it has fewer violations. Store first-pass violations per section, or store `{idx/title: viols}` before regen and compare against that count.

## Finding Closure

- Finding #1, validator regen: PARTIAL. Regen is attempted after the first validator pass, the focus hint includes required primary ev_ids, and remaining violations are emitted in `MultiSectionResult.m44_validator_violations`. The replacement policy is incomplete because the fewer-violations path is broken as described above.
- Finding #3, over-broad injection: CLOSED. `_m44_anchor_category`, `_M44_ANCHOR_SECTION_AFFINITY`, and `_m44_section_matches_anchor` constrain injection by anchor category and section title/focus, with tests covering CVOT, SURMOUNT, general SURPASS, and skipped-affinity logging.
- Finding #4, previous sentence: CLOSED. `_m44_validate_primary_same_sentence` now checks same, previous, and next sentence windows, and `test_primary_cited_in_previous_sentence_passes` covers the missing previous-sentence case.
- Finding #2, scorer vs injection: ACCEPTED SCOPE NOTE. No pass-3 scorer refactor required for M-44 unless the project wants to change the planner architecture separately.

## Verification

Ran:

```bash
PYTHONPATH=src python -m pytest tests/polaris_graph/test_m44_primary_injection_and_validator.py -q
```

Result: 34 passed, with one pytest cache warning from denied `.pytest_cache` write access.
