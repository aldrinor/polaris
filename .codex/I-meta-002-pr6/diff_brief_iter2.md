# Codex DIFF-gate — I-meta-002 sub-PR-6 — iter 2 of 5

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## What changed since your iter-1 diff review
Your iter-1 verdict was REQUEST_CHANGES, zero P0, ONE P1 (the lethal one) + three P2.

**P1 (LETHAL — coverage numerator trusted from caller). FIXED.** In `sweep_integration.run_four_role_evaluation`:
- A non-empty incoming `coverage_ledger.covered_element_ids` now FAILS LOUD (`ValueError`): the
  numerator must be empty on input.
- The numerator is rebuilt in a FRESH `internal_ledger` (denominator = the caller's canonical
  `required_element_ids`; covered = empty) and credited ONLY from VERIFIED final verdicts.
- `apply_d8_release_policy` and `coverage_fraction` now use `internal_ledger`, never the caller's.
- Regression `test_prefilled_coverage_ledger_rejected`: a prefilled ledger + Sentinel-UNGROUNDED +
  Judge VERIFIED -> ValueError (cannot ride pre-credited coverage; cannot release). The existing
  `test_sentinel_ungrounded_claim_cannot_release` (empty incoming ledger) still holds: downgrade to
  UNSUPPORTED -> credits nothing -> below threshold -> D8 holds.

**P2-a (Gate-A check (d) bypassed the transport). FIXED.** `check_role_contracts` now routes all
three fixtures THROUGH the mock `_GateAMockTransport` + the real adapters (`run_sentinel`,
`run_judge`, `run_mirror`) — Sentinel yes=UNGROUNDED, Judge off-enum -> JudgeEnumError, Mirror
two-pass grounded round-trip binds and returns a 2-record list. It is now the fixture-through-
transport check the brief required.

**P2-b (coverage check didn't reject extra pins). FIXED.** `check_frozen_lock_coverage` now asserts
the pinned role set is EXACTLY {generator, mirror, sentinel, judge} (fails on missing OR extra).

**P2-c (evaluator_agrees writeback) — intentionally deferred, honest.** `run_one_query` works with
`multi_section_generator.SectionResult`/`SentenceVerification`, NOT `clinical_generator.VerifiedSentence`;
manufacturing VerifiedSentence there would be fake wiring (LAW II). The branch surfaces
`final_verdicts` (keyed by claim_id) in the manifest and exports `evaluator_agrees_from_verdict`;
the actual writeback belongs at the `clinical_generator` Gate-B assembly point (with its own test).
This matches the approved scope split (sweep surgery minimal; Gate-B does the live assembly).

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 294 passed, 0 failed.
- `verify_lock --consistency` -> exit 0.
- `python -m scripts.dr_benchmark.gate_a_dry_run` -> OVERALL PASS (no-spend, offline): pytest_suites,
  lock_consistency, frozen_lock_coverage (exactly 4 roles + all-distinct families), role_contracts
  (via transport). Lock NOT promoted (status pending). Cheap probes default-OFF.
- Frozen scorer + runtime lock + canonical pipeline untouched.

## Review ask
Confirm the coverage numerator can no longer be pre-credited (a Sentinel-UNGROUNDED claim can never
ride prefilled coverage to release), the Gate-A checks are now transport-exercised + exact-4-role,
and nothing in this PR can cause real spend or promote the lock. APPROVE iff zero P0/P1.

## DIFF (full sub-PR-6 diff, fixes included)
