# M-44 Pass-3 Code Audit Findings

Verdict: PASS

Scope audited:
- Commit: `6e85312d21a06ff2d21e917fe4a02191d248e8bf`
- Target file: `src/polaris_graph/generator/multi_section_generator.py`
- Regression test: `tests/polaris_graph/test_m44_primary_injection_and_validator.py`
- Pass-2 finding checked: regen replacement comparison used `m44_validator_violations` before it was populated.

## Findings

No blocking findings.

## Audit Notes

1. Fix correctness: OK.
   - `first_pass_violations_by_idx` is populated during the first validator pass, before any regen work starts.
   - The dict is keyed by the same `section_results` index appended to `sections_needing_regen`.
   - The regen pass builds `regen_items` from those indices and uses `asyncio.gather` result ordering, so each `(idx, plan)` is compared with its matching regen result.
   - There is no intervening reordering of `section_results` before replacement.
   - The fallback `get(idx, 0)` is not expected to fire for normal regen candidates because the dict write is adjacent to the `sections_needing_regen.append(idx)` path. If a future edit appends regen indices elsewhere, that fallback would become permissive for a fully resolved regen, but current code does not expose that path.

2. Regen trigger condition: unchanged.
   - Sections still enter `sections_needing_regen` exactly when `_m44_validate_primary_same_sentence(...)` returns one or more violations.
   - Eligibility gates remain the same: skip dropped sections, empty verified text, and non-primary-eligible section titles.

3. Replacement policy: unchanged in behavior, with the pass-2 bug fixed.
   - Current replacement condition remains: replace when regen has strictly fewer violations than the first pass, or when regen has no violations and produced nonzero verified sentences.
   - The meaningful change is the baseline: `orig_viols_count` now comes from the first-pass snapshot instead of the final telemetry accumulator, which is intentionally empty at that decision point.

## Test Evidence

Ran:

```powershell
python -m pytest tests/polaris_graph/test_m44_primary_injection_and_validator.py -q
```

Result: `35 passed`.

Note: direct `pytest ...` failed because `pytest` is not on PATH in this shell; `python -m pytest ...` succeeded. Pytest emitted a cache permission warning for `.pytest_cache`, unrelated to the audited behavior.

## Residual Risk

The new regression test captures the structural comparison semantic with a small dict-level check, not an end-to-end mocked regen flow through `generate_multi_section_report`. Given the localized code shape, this is acceptable for pass-3, but a future higher-fidelity test could mock `_run_section` to prove actual replacement of a section with fewer post-regen M-44 violations.
