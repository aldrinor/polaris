You are auditing M-46 — second of 7 V28 bundle items. Narrow scope.

## Commit

`e6fd147` (bundled with M-48 pass-2; M-46-specific changes are the
new `_m46_short_pool_ordered_selection` helper + the early-exit
rewrite at line ~449 of evidence_selector.py).

## Plan reference

`outputs/audits/v27/fix_plan_v28.md` M-46 (pass-2 revised per your
pass-1 review). Your verbatim revision was:

> "When floor inputs are configured (primary_trial_anchors,
> mechanism rows, jurisdiction quotas), the selector must still
> compute floor reservations, ranking, and telemetry even if
> len(scored) <= max_rows; it may return all rows only after
> applying a deterministic priority ordering and emitting floor
> notes."

Your verbatim acceptance criterion:

> "With a fixture where pool_size <= max_rows, selector notes still
> include applicable m42e_primary_floor, m42c_mechanism_floor, and
> m42d_hc_quota_expand, and selected row ordering places reserved
> primary/mechanism/regulatory rows before derivative rows."

## What changed

In `src/polaris_graph/retrieval/evidence_selector.py`:

1. Old early-exit path (line ~449): returned `evidence_rows` as-is
   with `notes=["pool_size<=max_rows (N/M)"]` and no floor telemetry.
2. New early-exit path: calls `_m46_short_pool_ordered_selection()`
   which re-uses the module-level floor-detection predicates
   (`_m42e_detect_primary_for_anchor`, `_m42c_row_is_mechanism_rich`,
   `_row_jurisdiction`) to compute M-42e/c/d reservations, then
   returns a priority-ordered `selected_rows` with full telemetry
   notes.

Priority classes:
- class 0: M-42e primary
- class 1: M-42c mechanism
- class 2: M-42d HC (jurisdiction-expansion)
- class 3: rest

Within same class: by (tier_priority, -score, index) — deterministic.

Strategy label changes to `tier_balanced_v1_all_m46_ordered` so
audits can tell the short-pool path does priority work now.

## Test coverage

`tests/polaris_graph/test_m46_selector_no_bypass.py` — 9 tests:
- pool_smaller_than_max_rows_still_emits_m42e_note (your acceptance)
- all_rows_kept_in_short_pool
- primary_ordered_before_derivatives (your acceptance ordering)
- mechanism_rows_ordered_after_primaries (priority class chain)
- hc_expansion_telemetry_in_short_pool
- backwards_compat_no_anchors_no_notes
- m46_ordered_strategy_label
- truncating_path_still_works (no regression on main branch)
- deterministic_ordering

## What to audit

1. **Priority-class ordering**: does the _priority_class function
   produce your verbatim spec: reserved primary/mechanism/regulatory
   BEFORE derivatives?
2. **Floor detection consistency**: does the short-pool path compute
   floors the same way as the main branch? Specifically:
   - M-42e cap = 6 primaries maximum?
   - M-42c triggers only when ≥4 mechanism rows in pool?
   - M-42d HC quota uses `_m42d_hc_quota()` env-aware?
3. **Telemetry notes**: identical format to the main branch?
4. **Does the main branch still work** on truncating runs (pool >
   max_rows)? The refactor didn't break it?
5. **Edge cases**: empty pool, single row, all-same-tier, anchors
   list empty, tier-priority ties?

Write verdict to `outputs/codex_findings/m46_code_audit/findings.md`.
On READY or CONDITIONAL-no-blockers, Claude proceeds to M-44
(scorer/subset primary boost — third in your implementation order).
