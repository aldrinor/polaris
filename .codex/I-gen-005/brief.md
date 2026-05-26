# I-gen-005 PR #909 — skip atom validation for empty-catalog sections

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- If iter 5 REQUEST_CHANGES, force-APPROVE per §8.3.1.
```

## Scope (1 file, 17 lines)

Closes PR #906 iter-5 P2: skip atom validation when sr.atom_catalog is empty (contract-section path produces empty catalog → strict mode would refuse every claim, false positive storm).

Telemetry: skipped sections get `atom_validation_mode = "skipped_empty_catalog"`.

Default behavior unchanged: PG_ATOM_REFUSAL_MODE=off still skips the whole block.

## Output

```yaml
verdict: APPROVE | REQUEST_CHANGES

skip_on_empty_catalog_correct: YES | NO

telemetry_distinction_correct: YES | NO

novel_p0: []
novel_p1: []
p2: []

approval_to_merge: YES | NO
```

EMIT YAML ONLY.
