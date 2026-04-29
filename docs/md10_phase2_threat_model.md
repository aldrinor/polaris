# M-D10 phase 2 v1 — citation freshness aggregation boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/freshness_aggregates.py`
**Tests:** `tests/polaris_graph/test_md10_phase2_freshness_aggregates.py` (22 passing)
**Pairs with:** M-D10 phase 1 (`freshness_monitor.py`, commit a85812f).
**Substrate:** stdlib + `freshness_monitor` only.

---

## Scope

M-D10 phase 1 ships per-workspace SQLite FreshnessAlertStore +
5-status taxonomy + M-D7 cache eviction integration + 3
record-level query APIs (list_alerts, latest_for_url, count).

Phase 2 v1 layers **aggregation queries** on top: per-workspace
counts by FreshnessStatus over a time window, plus
**latest-status-per-source** rollups for V19+ live audit
("how many of the cited sources in this report have been
retracted since they were cached?").

Pure substrate. Mirrors the M-D3 phase 2 v1 pattern: aggregate
on top of an existing v1 store query API, no new SQL paths.

---

## v1 boundaries

### 1. Pure substrate — no I/O beyond M-D10 phase 1 store

`freshness_aggregates.py` imports stdlib + `freshness_monitor`
only. No new SQL paths or schema changes. The aggregation is
computed in Python over the alert list returned by
`store.list_alerts(limit=_MAX_LIMIT)`.

This trades query efficiency for code simplicity at v1; v2
may add a SQL-side `GROUP BY status` query if performance
demands. Hard cap of 1M alerts per workspace (defensive
upper bound — operationally, one workspace with 1M+
freshness alerts is doing something pathological).

### 2. only_latest_per_source rollup is a query MODE, not a default

Two distinct questions need different aggregates:
  - **Operational dashboards**: "what's the recent freshness-
    check activity?" — count every alert in the window
    (`only_latest_per_source=False`, default)
  - **Report freshness signal**: "how many distinct cited
    sources are currently in each status?" — roll up to one
    alert per cache_key (`only_latest_per_source=True`)

The default is False because operational dashboards are the
common case and "how many of these checks happened" is the
literal interpretation. V19+ live audit will explicitly opt
into latest-mode for the report-freshness BEAT-BOTH dimension.

**Mitigation**: tests pin both modes
(`test_latest_per_source_dedups_same_url`,
`test_latest_per_source_with_canonical_dedup`,
`test_latest_per_source_within_window`).

### 3. Latest-mode rollup happens AFTER window filter

A retraction outside the window is NOT the latest for the
purposes of an in-window query. The window filter is applied
first; latest-per-source rollup operates on the windowed set.

This matters for V19+ live audit: "what was the citation's
status as of the report shipping date?" should ignore
retractions that happened later. The caller passes
`until=report_ship_date` and gets the latest in-window
status.

**Mitigation**: `test_latest_per_source_within_window` pins
this — a retraction at t=3000 is NOT counted in a
since/until=1000-2000 query, even though it's the absolute-
latest status for that source.

### 4. Time window inclusive on both bounds

`since` and `until` are UNIX epoch floats matching
`FreshnessAlert.checked_at`. A record exactly at the
boundary is included. `since == until` selects records
captured exactly at that instant.

Same convention as M-D3 phase 2 v1 + standard SQL BETWEEN
semantics.

**Mitigation**: `test_window_inclusive_at_boundary` +
`test_invalid_window_raises`.

### 5. evicting_count = superseded + retracted + expression_of_concern

The 3 statuses that triggered (or would have triggered)
M-D7 cache eviction in phase 1's `_EVICTING_STATUSES`
frozenset. Surfacing this as a single aggregate makes the
"how many cited sources became unsafe to cite?" question
trivial for operational dashboards.

`unchanged` and `unreachable` are explicitly NOT evicting:
unchanged is heartbeat (source still authoritative),
unreachable is transient transport failure (per M-D10 phase
1 boundary — not a content-freshness signal).

**Mitigation**: `test_evicting_count_sums_three_statuses` +
`test_unchanged_and_unreachable_not_evicting`.

### 6. unique_source_count tracks distinct cache_keys in the window

Computed over the windowed set, NOT the full store. So a
since/until query reports "how many unique sources were
checked in this window", not "how many unique sources have
EVER been checked in this workspace".

Useful as a denominator for retraction-rate questions ("of
the 50 distinct sources we checked this month, how many
were retracted?").

**Mitigation**: `test_unique_source_count_with_repeats` +
`test_unique_source_count_after_window_filter`.

### 7. Schema-drift defense

The aggregator iterates alerts and dispatches on
`alert.status` (the FreshnessStatus.value string per phase 1
schema). An unknown status string raises
`FreshnessAggregatesError` with the alert_id — surfacing
schema drift loudly per LAW II rather than silently
miscounting.

This protects against future M-D10 phase 1 schema bumps
that add new status values without updating the aggregator.
The phase 1 SQL CHECK constraint also rejects unknown
statuses at INSERT time, but defense in depth is cheap.

---

## v1 NON-goals (defer to v2)

  - **No SQL-side aggregation**: substrate uses Python loop
    over `list_alerts`. v2 may add `GROUP BY status` if
    performance demands.
  - **No multi-workspace aggregation**: caller iterates
    workspaces themselves.
  - **No time-bucketed / rolling-window aggregates**: only
    point-in-time `since/until` windows. v2 may add bucketed
    variants for trending dashboards.
  - **No status-change events**: phase 2 v1 doesn't surface
    "URL X went from unchanged to retracted between two
    snapshots". That's a diff-of-aggregates operation a
    caller composes from two `compute_freshness_aggregates`
    calls. M-D11 phase 2 v2 (pin trends) provides the
    drift-event pattern if needed.
  - **No detector-source breakdown**: aggregator doesn't
    know which detector emitted each alert (FreshnessAlert
    doesn't carry that field). If V19+ wants per-detector
    rate (Crossref vs PubMed), phase 1 schema needs a
    `detector_id` column first.
  - **No alert / notification glue**: aggregates are
    returned as data; emitting alerts on rate thresholds is
    operational dashboards' territory.

---

## Codex review trail

Round-1 brief incoming. Tool hints:
- Use `python -m pytest -q tests\polaris_graph\test_md10_phase2_freshness_aggregates.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode —
  Windows sandbox uses cp1252 (this has caused 7+ Codex
  review cutoffs this session)
- 22 tests pin all 7 boundaries

Targeted at 1-2 round convergence per the M-D3 phase 2 v1 +
M-D11 phase 2 v2 v1 patterns (substrate aggregation work
with v1-shipped threat-model docs converges fast).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (SQL-side
aggregation, multi-workspace, time-bucketed, detector
breakdown) tracked separately.
