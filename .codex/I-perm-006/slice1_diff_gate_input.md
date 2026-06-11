# Codex DIFF review — I-perm-006 (#1200) SLICE 1: kill the phantom d8_pending_rewrite block

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Reserve P0/P1 for real execution risks. If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this slice does (one guarded line)
`release_policy.apply_d8_release_policy`: the `d8_pending_rewrite` held_reason append is now gated `if needs_rewrite and not always_release_enabled():`. So under `PG_ALWAYS_RELEASE` it no longer blocks release; `needs_rewrite` stays a pure reporting channel. Flag OFF -> the append still fires (byte-identical).

## Why it is safe (the P0 hunt)
`d8_pending_rewrite` is a PHANTOM: it requires `not rewrite_already_attempted`, and `rewrite_already_attempted` is hardcoded False at every production call site with NO outer loop ever setting it True (grep: `rewrite_already_attempted=True` exists ONLY in tests/). So it blocks a rewrite the architecture never executes. Removing it under always-release does NOT let an UNSUPPORTED/FABRICATED claim ship as bare fact, because:
- FABRICATED still latches (`fabricated_occurrence_latched`) and is a HARD block in `compute_release_outcome` (I-perm-001) — untouched here.
- under always-release, a non-VERIFIED claim ships LABELED via the I-perm-005 annotator (keep+label), not as asserted fact.
- the coverage / S0 gates are unchanged; this only removes the redundant pending_rewrite block.

Verify: (1) flag OFF is byte-identical (the 44 existing release_policy/replay tests pass); (2) flag ON drops ONLY `d8_pending_rewrite` from held_reasons — every OTHER held_reason (coverage, S0-missing, fabricated) is unaffected; (3) `needs_rewrite` is still populated either way (pure reporting). If you find a path where flag-ON lets a claim that should be blocked (e.g. a fabricated or coverage-failing one) release, that is a P0.

## Claims ledger
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | only pending_rewrite is gated by the flag | the single `if needs_rewrite and not always_release_enabled()` line; all other held_reasons unchanged | claims-true |
| C2 | flag OFF byte-identical | `not always_release_enabled()` is True when unset -> append as before; 44 tests pass | claims-true |
| C3 | needs_rewrite still reported | populated above the gate, unchanged | claims-true |
| C4 | FABRICATED/coverage blocks intact | not touched by this diff | claims-true |

## Honest scope note
Minimal functional fix only. The vestigial `rewrite_already_attempted` PARAM threading (sweep_integration/native_gate_b_inputs) + the `multi_section_generator` tighter_retry flag-gate are follow-up cleanup — out of scope here.

## Files (full diff: `.codex/I-perm-006/slice1_codex_diff.patch`)
- `src/polaris_graph/roles/release_policy.py` (the guarded append).
- `tests/roles/test_pending_rewrite_iperm006.py` (2 tests: flag-OFF block / flag-ON no-block).

## Test evidence: 2 new + 44 release_policy/replay (OFF byte-identical) green.

Review the diff. Confirm C2 (OFF byte-identical) + C4 (FABRICATED/coverage blocks intact). Hunt any path where flag-ON releases a claim that should stay blocked.
