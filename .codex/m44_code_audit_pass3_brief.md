M-44 pass-3 audit — closes pass-2 finding #1 (regen comparison bug).

## Pass-2 verdict (commit `6b2f9c9`)

CONDITIONAL. Finding #1 identified: regen replacement criterion
compared against `m44_validator_violations` (which is empty at
regen decision time, only populated AFTER regen). Dead code path;
regens always rejected.

## Pass-3 (commit `6e85312`)

Fix: store per-section first-pass violation counts in
`first_pass_violations_by_idx: dict[int, int]` BEFORE the regen
loop. Compare against that dict at replacement decision.

Code change at `src/polaris_graph/generator/multi_section_generator.py`:

```python
# First validator pass — NEW: record per-section violation count
first_pass_violations_by_idx: dict[int, int] = {}
for idx, sr in enumerate(section_results):
    ...
    viols = _m44_validate_primary_same_sentence(...)
    if viols:
        sections_needing_regen.append(idx)
        first_pass_violations_by_idx[idx] = len(viols)
```

And in regen decision:

```python
orig_viols_count = first_pass_violations_by_idx.get(idx, 0)
if len(new_viols) < orig_viols_count or (
    not new_viols and regen_result.sentences_verified > 0
):
    section_results[idx] = regen_result
```

New test `test_first_pass_violation_count_persists_through_regen`
verifies the structural comparison semantic.

## What to audit

1. **Fix correctness**: does the pass-3 approach correctly preserve
   first-pass counts across regen? Any edge case where the dict
   lookup fails or returns stale data?
2. **Regen trigger condition unchanged**: sections with viols →
   regen (same as pass-2)?
3. **Replacement policy unchanged**: "fewer violations OR all
   resolved + nonzero verified" unchanged per plan?

Write verdict to
`outputs/codex_findings/m44_code_audit_pass3/findings.md`.
