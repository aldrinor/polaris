# M-46 Code Audit Verdict

Verdict: READY

No blocking findings.

Scope audited:
- Commit `e6fd147`
- `src/polaris_graph/retrieval/evidence_selector.py`
- `tests/polaris_graph/test_m46_selector_no_bypass.py`
- Plan reference `outputs/audits/v27/fix_plan_v28.md` M-46 pass-2

## Findings

### 1. Priority-class ordering

PASS.

The short-pool path now routes `len(scored) <= max_rows` through
`_m46_short_pool_ordered_selection()` instead of returning input order.
The local `_priority_class()` maps:
- `0`: M-42e primary rows
- `1`: M-42c mechanism rows
- `2`: M-42d Health Canada quota rows
- `3`: everything else

The final sort key is:

```python
(_priority_class(item), _TIER_PRIORITY.get(item[2], 9), -item[1], item[0])
```

This satisfies the acceptance requirement that reserved primary,
mechanism, and regulatory quota rows appear before derivative/rest rows,
with deterministic tie-breaking by tier priority, score, and original
index.

### 2. Floor detection consistency

PASS.

M-42e:
- Uses `_m42e_detect_primary_for_anchor()`.
- Restricts matches to T1, matching the main branch contract.
- Enforces `_M42E_PRIMARY_FLOOR_CAP == 6`.

M-42c:
- Uses `_m42c_row_is_mechanism_rich()`.
- Fires only when `len(mech_pool) >= _M42C_MECHANISM_FLOOR_MIN_POOL_ROWS`
  (`4`).
- Reserves up to `_M42C_MECHANISM_FLOOR_SLOTS` (`3`) across T1/T2 rows.

M-42d:
- Uses `_row_jurisdiction()`.
- Uses `_m42d_hc_quota()`, so `PG_M41D_HC_QUOTA` behavior remains
  env-aware.
- Emits HC expansion only when extra HC rows are actually reserved.

Non-blocking nuance: the short-pool helper computes M-42e before M-42c
and avoids double-counting a primary row as a mechanism reservation.
The truncating branch computes M-42c before M-42e and can include an
overlapping row in both internal sets before later de-duping selection.
This can change the M-42c `reserved=` count in contrived overlap cases,
but the short-pool behavior is conservative and does not violate the
M-46 acceptance criteria.

### 3. Telemetry notes

PASS.

The floor telemetry note formats match the main branch:
- `m42e_primary_floor matched=... reserved=... cap=... anchors=...`
- `m42c_mechanism_floor pool_mech_rows=... reserved=... slots=...`
- `m42d_hc_quota_expand hc_pool=... reserved=... extras_added=... quota=...`

The short-pool path also keeps the legacy `pool_size<=max_rows (N/M)`
signal and adds `m46_short_pool_ordered_selection`. That extra note is
acceptable because the strategy label also intentionally changes to
`tier_balanced_v1_all_m46_ordered` for audit visibility.

### 4. Truncating branch

PASS.

The existing `pool > max_rows` branch remains in place and still emits
the established M-42 telemetry. The M-46 test suite includes a
truncating-path regression test, and the broader adjacent selector tests
passed.

### 5. Edge cases

PASS.

Reviewed cases:
- Empty pool: returns no rows, no drops, deterministic notes.
- Single row: stable ordering and counts.
- All-same-tier rows: deterministic score/index ordering.
- Empty or absent anchors: no M-42e telemetry.
- Tier-priority and score ties: original index breaks ties.

## Verification

Ran:

```powershell
python -m pytest tests/polaris_graph/test_m46_selector_no_bypass.py -q
python -m pytest tests/polaris_graph/test_m42c_mechanism_floor_and_prompt.py tests/polaris_graph/test_m42d_hc_quota_expansion.py tests/polaris_graph/test_m42e_primary_trial_floor.py tests/polaris_graph/test_m46_selector_no_bypass.py -q
```

Results:
- M-46 focused suite: 9 passed.
- Adjacent selector suite: 71 passed.
- Only warning: pytest could not write `.pytest_cache` due local
  permission restrictions; this does not affect test execution.

Claude can proceed to M-44.
