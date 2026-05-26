# I-gen-005 PR #907 — gaps.json sidecar writer

## §8.3.1 cap (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0/P1.
```

## Scope (1 file, 34 lines)

Closes PR #906 Codex iter-5 P2: write_gaps_sidecar production caller.

After report.md + bibliography.json write for each query:
1. Collect SectionValidationResult from multi.sections
2. If non-empty, call write_gaps_sidecar(run_dir, document_id, results)
3. Log + fail-soft

## Default behavior unchanged

PG_ATOM_REFUSAL_MODE=off (default) → atom_validation_result is None on every section → _section_val_results empty → no gaps.json. Zero behavior change.

## Canonical diff hash

SHA256: `b7ff37cc21d1fe0f7b0d1be197f791e3770a31a0b2081900af752c9360945f60`

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

default_off_zero_behavior_change: YES | NO

fail_soft_correct: YES | NO

novel_p0: []
novel_p1: []
p2: []

approval_to_merge: YES | NO
```

EMIT YAML ONLY.
