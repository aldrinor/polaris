"""M-D10 phase 2 v1 (Phase D): Citation freshness aggregation.

M-D10 phase 1 (`freshness_monitor.py`, commit a85812f) shipped
the per-workspace SQLite FreshnessAlertStore + 5-status taxonomy
(unchanged/superseded/retracted/expression_of_concern/unreachable)
+ M-D7 cache eviction integration.

Phase 2 v1 layers **aggregation queries** on top: per-workspace
counts by FreshnessStatus over a time window, plus
**latest-status-per-source** rollups for the V19+ live audit
("how many of the cited sources in this report have been
retracted since they were cached?").

Pure substrate on top of the M-D10 phase 1 store.

## Why this milestone matters

V19+ live audit consumes BEAT-BOTH dimension scores. One
deferred dimension is "regulatory_freshness" — citation
quality should degrade as cited sources get retracted /
superseded after the report ships. Phase 2 v1 ships the
aggregation primitive needed to compute that signal:
**per-workspace-window snapshot of the freshness landscape**.

It also enables operational dashboards: "this workspace has
8 retractions in the last 30 days" — surfacing systemic
citation-quality issues before users encounter them.

## What v1 ships

  - `FreshnessAggregates` dataclass — counts per status +
    latest-status-per-source rollup
  - `compute_freshness_aggregates(store, workspace_id, *,
    since, until, only_latest_per_source)` — pure derivation
    backed by M-D10 phase 1 store query API

## Substrate boundary

Imports `freshness_monitor` (FreshnessAlert, FreshnessStatus,
FreshnessAlertStore, FreshnessMonitorError) only. No new DB
schema or SQL paths; reuses the phase 1 store's `list_alerts`.
No LLM, no HTTP, no live detector calls.

See `docs/md10_phase2_threat_model.md` for boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.polaris_graph.audit_ir.freshness_monitor import (
    FreshnessAlert,
    FreshnessAlertStore,
    FreshnessMonitorError,
    FreshnessStatus,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FreshnessAggregatesError(ValueError):
    """Raised on contract violations — invalid window, etc."""


# ---------------------------------------------------------------------------
# Aggregates dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessAggregates:
    """Per-window freshness aggregates for one workspace.

    `total_alerts` is total alerts in the window (when
    `only_latest_per_source=False`) OR the count of unique
    cache_keys with at least one alert in the window (when
    `only_latest_per_source=True`).

    Per-status counts (`unchanged_count` ... `unreachable_count`)
    sum to `total_alerts` exactly.

    `evicting_count` is the sum of the 3 evicting statuses
    (superseded + retracted + expression_of_concern). These are
    the statuses that triggered (or would have triggered) cache
    eviction in M-D10 phase 1 — operational dashboards should
    surface this as the "citations that became unsafe to cite".

    `unique_source_count` is the number of distinct cache_keys
    seen in the window. When `only_latest_per_source=False`,
    this can be < total_alerts (multiple alerts per source
    over time). When `only_latest_per_source=True`,
    `unique_source_count == total_alerts`.

    `window_start` / `window_end` are UNIX epoch floats (same
    convention as `FreshnessAlert.checked_at`). `None` means
    open on that end.

    `only_latest_per_source` echoes the query mode (True =
    one-alert-per-cache_key rollup; False = all alerts).
    """

    workspace_id: str
    window_start: float | None
    window_end: float | None
    only_latest_per_source: bool
    total_alerts: int
    unchanged_count: int
    superseded_count: int
    retracted_count: int
    expression_of_concern_count: int
    unreachable_count: int
    evicting_count: int
    unique_source_count: int


# ---------------------------------------------------------------------------
# Internal: list-with-window helper
# ---------------------------------------------------------------------------


# Hard cap for list_alerts() pagination — phase 1 defaults to 100
# but we need the full window. SQLite can handle 1M+ rows; this
# cap is just to avoid OOM on a misconfigured store. Callers
# who legitimately have >1M alerts in one window are doing
# something pathological.
_MAX_LIMIT = 1_000_000


def _list_window(
    store: FreshnessAlertStore,
    workspace_id: str,
    since: float | None,
    until: float | None,
) -> list[FreshnessAlert]:
    """Pull all alerts for a workspace, then filter by time
    window in Python. Mirrors the M-D3 phase 2 pattern (no new
    SQL paths, defer query optimization to v2 if needed)."""
    all_alerts = store.list_alerts(
        workspace_id=workspace_id, limit=_MAX_LIMIT,
    )
    if since is None and until is None:
        return all_alerts
    filtered = []
    for alert in all_alerts:
        if since is not None and alert.checked_at < since:
            continue
        if until is not None and alert.checked_at > until:
            continue
        filtered.append(alert)
    return filtered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_freshness_aggregates(
    store: FreshnessAlertStore,
    workspace_id: str,
    *,
    since: float | None = None,
    until: float | None = None,
    only_latest_per_source: bool = False,
) -> FreshnessAggregates:
    """Compute freshness aggregates for `workspace_id`.

    `since` / `until` are UNIX epoch floats (matching
    `FreshnessAlert.checked_at`). Both bounds inclusive. Either
    can be None for an open window.

    `only_latest_per_source=True` rolls up to one alert per
    cache_key (the newest alert in the window for that
    cache_key) before counting. This answers "how many distinct
    cited sources are currently in each status?" — the right
    question for V19+ live audit's "report freshness" signal.

    `only_latest_per_source=False` (default) counts every alert
    in the window. This answers "what's the recent freshness-
    check activity?" — the right question for operational
    dashboards.

    Pure derivation backed by `store.list_alerts` (M-D10 phase 1
    query API). No new SQL paths; window filter + dedup happen
    in Python. v2 may add SQL-side aggregation if record counts
    grow.
    """
    if not isinstance(store, FreshnessAlertStore):
        raise FreshnessAggregatesError(
            f"store must be FreshnessAlertStore, got "
            f"{type(store).__name__}"
        )
    if not workspace_id or not workspace_id.strip():
        raise FreshnessAggregatesError("workspace_id must be non-empty")
    if since is not None and until is not None and since > until:
        raise FreshnessAggregatesError(
            f"since ({since}) must be <= until ({until})"
        )

    ws = workspace_id.strip()

    # Pull the window via the phase 1 store API.
    try:
        windowed = _list_window(store, ws, since, until)
    except FreshnessMonitorError as exc:
        # Re-wrap so callers get FreshnessAggregatesError on
        # contract issues (the underlying phase 1 store can
        # raise on empty workspace_id, which we already
        # validated above — but defensive in case phase 1
        # adds new validations).
        raise FreshnessAggregatesError(str(exc)) from exc

    # Compute unique source count over the windowed set
    # regardless of mode (it's a useful aggregate either way).
    unique_keys = {a.cache_key for a in windowed}
    unique_source_count = len(unique_keys)

    if only_latest_per_source:
        # The phase 1 store returns alerts ordered by
        # checked_at DESC. So the first alert per cache_key in
        # the iteration is the latest. Build a dict keyed by
        # cache_key, first wins.
        latest_per_key: dict[str, FreshnessAlert] = {}
        for alert in windowed:
            if alert.cache_key not in latest_per_key:
                latest_per_key[alert.cache_key] = alert
        counted_alerts = list(latest_per_key.values())
    else:
        counted_alerts = windowed

    counts = {
        FreshnessStatus.UNCHANGED.value: 0,
        FreshnessStatus.SUPERSEDED.value: 0,
        FreshnessStatus.RETRACTED.value: 0,
        FreshnessStatus.EXPRESSION_OF_CONCERN.value: 0,
        FreshnessStatus.UNREACHABLE.value: 0,
    }
    for alert in counted_alerts:
        # alert.status is the FreshnessStatus.value string per
        # phase 1 schema; defensive against unknown values.
        if alert.status not in counts:
            raise FreshnessAggregatesError(
                f"unknown status {alert.status!r} for alert "
                f"{alert.alert_id} — store may have schema drift"
            )
        counts[alert.status] += 1

    total_alerts = sum(counts.values())
    evicting = (
        counts[FreshnessStatus.SUPERSEDED.value]
        + counts[FreshnessStatus.RETRACTED.value]
        + counts[FreshnessStatus.EXPRESSION_OF_CONCERN.value]
    )

    return FreshnessAggregates(
        workspace_id=ws,
        window_start=since,
        window_end=until,
        only_latest_per_source=only_latest_per_source,
        total_alerts=total_alerts,
        unchanged_count=counts[FreshnessStatus.UNCHANGED.value],
        superseded_count=counts[FreshnessStatus.SUPERSEDED.value],
        retracted_count=counts[FreshnessStatus.RETRACTED.value],
        expression_of_concern_count=counts[
            FreshnessStatus.EXPRESSION_OF_CONCERN.value
        ],
        unreachable_count=counts[FreshnessStatus.UNREACHABLE.value],
        evicting_count=evicting,
        unique_source_count=unique_source_count,
    )
