# Codex round 2 — M-D10 phase 2 v2 (commit ee227b7)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md10_phase2_freshness_aggregates.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/freshness_aggregates.py`
  - `tests/polaris_graph/test_md10_phase2_freshness_aggregates.py`
  - `docs/md10_phase2_threat_model.md`
- DO NOT run Python verification scripts that print Unicode

## Round-1 findings to verify closed

You returned PARTIAL on v1 (commit dbe24ea) with 3 findings:

**[HIGH]** `_list_window` silently truncated at `_MAX_LIMIT`.
v2 fix: pre-flight `store.count(workspace_id) > _MAX_LIMIT`
gate raises `FreshnessAggregatesError`. Pinned by
`test_oversize_workspace_raises_rather_than_truncating` (with
monkeypatched _MAX_LIMIT=2 and 3 alerts, expects raise) and
`test_under_cap_workspace_does_not_raise` (at-cap is OK).

**[MEDIUM]** Schema-drift validation ran AFTER latest-per-source
dedup, masking unknown OLDER statuses in latest-mode.
v2 fix: validate full windowed set BEFORE dedup. Pinned by
`test_unknown_status_raises_in_default_mode` (+ ditto for
latest-mode).

**[LOW]** Tests didn't pin schema-drift defense.
v2 fix: 2 new tests via `_DriftStore` subclass that overrides
`list_alerts` to inject `status="future_unknown_status"`.

## What v2 changed (concrete diff)

```python
# v2: pre-flight count gate (closes HIGH)
total_in_workspace = store.count(workspace_id=workspace_id)
if total_in_workspace > _MAX_LIMIT:
    raise FreshnessAggregatesError(
        f"workspace {workspace_id!r} has {total_in_workspace} "
        f"freshness alerts, exceeding _MAX_LIMIT={_MAX_LIMIT}. ..."
    )

# v2: validate windowed set BEFORE dedup (closes MEDIUM)
_known_statuses = frozenset({...})
for alert in windowed:
    if alert.status not in _known_statuses:
        raise FreshnessAggregatesError(
            f"unknown status {alert.status!r} for alert "
            f"{alert.alert_id} — store may have schema drift"
        )

if only_latest_per_source:
    latest_per_key = {}
    for alert in windowed:
        if alert.cache_key not in latest_per_key:
            latest_per_key[alert.cache_key] = alert
    counted_alerts = list(latest_per_key.values())
else:
    counted_alerts = windowed

# Then count per status (no validation here — already done)
counts = {...}
for alert in counted_alerts:
    counts[alert.status] += 1
```

## Convergence note

If round 2 finds another edge in the same predicate (e.g. a
new edge in `_list_window` count gate or schema-drift
validation), that's still convergence — fix it.

If round 2 reaches for an entirely new probe surface, flag
explicitly.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-1 fix integration
- [x/ ] HIGH _list_window count gate fails loud
- [x/ ] MEDIUM schema-drift validates BEFORE dedup
- [x/ ] LOW tests cover schema-drift in both modes

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
