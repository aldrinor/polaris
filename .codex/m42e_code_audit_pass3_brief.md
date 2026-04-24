M-42e pass-3 audit. Pass-2 verdict: CONDITIONAL, 0 blockers, 2
mediums. Pass-3 addresses both mediums. Narrow scope — only
review pass-3 diff.

## Pass-2 mediums (what you raised)

1. Non-primary marker coverage not exhaustive. Specifically:
   pharmacokinetic analysis, population pharmacokinetic, modeling
   analysis, model-based analysis, exposure-response analysis would
   still pass.

2. Telemetry overstates reservations when matched > T1 quota.
   `reserved=N` reported matches, not actual reserved rows.

## Pass-3 changes

1. `_M42E_NON_PRIMARY_TITLE_PATTERNS` gains 8 entries:
   - `pharmacokinetic analysis`
   - `population pharmacokinetic`
   - `modeling analysis`
   - `model-based analysis`
   - `exposure-response analysis`
   - `pk analysis`
   - `pd analysis`
   - `pkpd analysis`

2. Telemetry splits `matched=X reserved=Y cap=Z anchors=[...]`.
   Before: `reserved=<match_count>` (ambiguous when quota-trimmed).
   After: `matched=<raw_match_count> reserved=<final_reservation_count>`.

3. Non-regression test: `Primary analysis of SURPASS-2` must NOT
   be rejected (bare `analysis` avoided intentionally).

## Tests added (7 pass-3)

- 5 for new PK/modeling patterns
- 1 non-regression for "primary analysis"
- 1 telemetry verifies matched + reserved both present

## Files

```
src/polaris_graph/retrieval/evidence_selector.py
  - _M42E_NON_PRIMARY_TITLE_PATTERNS (+8 entries)
  - Telemetry note format updated
tests/polaris_graph/test_m42e_primary_trial_floor.py (+7 tests)
```

## What to verify

1. Are the 8 new PK/modeling markers appropriately narrow? The
   non-regression test asserts `Primary analysis of SURPASS-2`
   is still accepted; any other common primary-title phrasing
   to add to the non-regression suite?

2. Is `matched=X reserved=Y` format clear for audit consumers?
   Alternative: `reserved=Y of matched=X`?

## Deliverable

Write `outputs/codex_findings/m42e_code_audit_pass3/findings.md`.
Final verdict READY | CONDITIONAL | BLOCKED. Confirm pass-2
mediums closed.

Under 400 words.
