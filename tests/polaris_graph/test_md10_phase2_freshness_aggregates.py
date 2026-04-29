"""M-D10 phase 2 v1 — freshness aggregation tests.

Pins:
  - compute_freshness_aggregates pure derivation contract
  - 5-status taxonomy counted exactly
  - Time window inclusive on both bounds
  - only_latest_per_source rollup semantics
  - Workspace isolation (via M-D10 phase 1 store query)
  - evicting_count = superseded + retracted + expression_of_concern
  - unique_source_count over windowed set
  - Empty store / no-match window edge cases
  - Schema-drift defense (unknown status raises)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.freshness_aggregates import (
    FreshnessAggregates,
    FreshnessAggregatesError,
    compute_freshness_aggregates,
)
from src.polaris_graph.audit_ir.freshness_monitor import (
    FreshnessAlertStore,
    FreshnessStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> FreshnessAlertStore:
    return FreshnessAlertStore(tmp_path / "freshness.sqlite")


def _record(
    store: FreshnessAlertStore,
    *,
    workspace_id: str = "ws1",
    source_url: str = "https://example.com/paper",
    status: FreshnessStatus = FreshnessStatus.UNCHANGED,
    checked_at: float = 1000.0,
) -> None:
    store.record(
        workspace_id=workspace_id,
        source_url=source_url,
        status=status,
        details=None,
        new_canonical_url=None,
        fetched_status_code=200 if status == FreshnessStatus.UNCHANGED else None,
        checked_at=checked_at,
        evicted_cache_key=None,
    )


# ---------------------------------------------------------------------------
# Empty / contract validation
# ---------------------------------------------------------------------------


def test_empty_store_returns_zero_counts(store: FreshnessAlertStore) -> None:
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.total_alerts == 0
    assert agg.unchanged_count == 0
    assert agg.superseded_count == 0
    assert agg.retracted_count == 0
    assert agg.expression_of_concern_count == 0
    assert agg.unreachable_count == 0
    assert agg.evicting_count == 0
    assert agg.unique_source_count == 0


def test_workspace_id_required(store: FreshnessAlertStore) -> None:
    with pytest.raises(FreshnessAggregatesError, match="workspace_id"):
        compute_freshness_aggregates(store, "")
    with pytest.raises(FreshnessAggregatesError, match="workspace_id"):
        compute_freshness_aggregates(store, "   ")


def test_workspace_id_stripped(store: FreshnessAlertStore) -> None:
    _record(store)
    agg = compute_freshness_aggregates(store, "  ws1  ")
    assert agg.workspace_id == "ws1"
    assert agg.total_alerts == 1


def test_non_store_argument_raises(store: FreshnessAlertStore) -> None:
    with pytest.raises(FreshnessAggregatesError, match="store must"):
        compute_freshness_aggregates("not a store", "ws1")  # type: ignore[arg-type]


def test_invalid_window_raises(store: FreshnessAlertStore) -> None:
    with pytest.raises(FreshnessAggregatesError, match="must be <= until"):
        compute_freshness_aggregates(store, "ws1", since=2000.0, until=1000.0)


# ---------------------------------------------------------------------------
# Status taxonomy counting
# ---------------------------------------------------------------------------


def test_each_status_counted_exactly(store: FreshnessAlertStore) -> None:
    _record(store, source_url="https://a.com", status=FreshnessStatus.UNCHANGED)
    _record(store, source_url="https://b.com", status=FreshnessStatus.SUPERSEDED)
    _record(store, source_url="https://c.com", status=FreshnessStatus.RETRACTED)
    _record(store, source_url="https://d.com",
            status=FreshnessStatus.EXPRESSION_OF_CONCERN)
    _record(store, source_url="https://e.com", status=FreshnessStatus.UNREACHABLE)
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.total_alerts == 5
    assert agg.unchanged_count == 1
    assert agg.superseded_count == 1
    assert agg.retracted_count == 1
    assert agg.expression_of_concern_count == 1
    assert agg.unreachable_count == 1


def test_evicting_count_sums_three_statuses(
    store: FreshnessAlertStore,
) -> None:
    """evicting_count = superseded + retracted + expression_of_concern."""
    _record(store, source_url="https://a.com", status=FreshnessStatus.SUPERSEDED)
    _record(store, source_url="https://b.com", status=FreshnessStatus.SUPERSEDED)
    _record(store, source_url="https://c.com", status=FreshnessStatus.RETRACTED)
    _record(store, source_url="https://d.com",
            status=FreshnessStatus.EXPRESSION_OF_CONCERN)
    _record(store, source_url="https://e.com", status=FreshnessStatus.UNCHANGED)
    _record(store, source_url="https://f.com", status=FreshnessStatus.UNREACHABLE)
    agg = compute_freshness_aggregates(store, "ws1")
    # 2 superseded + 1 retracted + 1 EoC = 4
    assert agg.evicting_count == 4


def test_unchanged_and_unreachable_not_evicting(
    store: FreshnessAlertStore,
) -> None:
    _record(store, source_url="https://a.com", status=FreshnessStatus.UNCHANGED)
    _record(store, source_url="https://b.com", status=FreshnessStatus.UNREACHABLE)
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.evicting_count == 0


# ---------------------------------------------------------------------------
# only_latest_per_source rollup
# ---------------------------------------------------------------------------


def test_latest_per_source_dedups_same_url(
    store: FreshnessAlertStore,
) -> None:
    """Same source URL checked 3 times. Latest mode keeps 1."""
    url = "https://example.com/paper"
    _record(store, source_url=url, status=FreshnessStatus.UNCHANGED, checked_at=1000.0)
    _record(store, source_url=url, status=FreshnessStatus.UNCHANGED, checked_at=2000.0)
    _record(store, source_url=url, status=FreshnessStatus.RETRACTED, checked_at=3000.0)

    # all alerts: 3 total
    agg_all = compute_freshness_aggregates(store, "ws1")
    assert agg_all.total_alerts == 3
    assert agg_all.unique_source_count == 1

    # latest only: 1 total, the retraction wins (newest)
    agg_latest = compute_freshness_aggregates(
        store, "ws1", only_latest_per_source=True,
    )
    assert agg_latest.total_alerts == 1
    assert agg_latest.retracted_count == 1
    assert agg_latest.unchanged_count == 0
    assert agg_latest.unique_source_count == 1


def test_latest_per_source_with_canonical_dedup(
    store: FreshnessAlertStore,
) -> None:
    """Two URL forms canonicalize to the same cache_key — they
    dedup in latest-mode regardless of which raw URL was cited."""
    # M-D10 phase 1 dedups on canonical cache_key. DOI vs https://doi.org/...
    # canonicalize identically. We test by recording the same raw URL twice
    # (guaranteed same canonical key).
    url = "https://example.com/paper"
    _record(store, source_url=url, status=FreshnessStatus.SUPERSEDED, checked_at=1000.0)
    _record(store, source_url=url, status=FreshnessStatus.SUPERSEDED, checked_at=2000.0)
    agg_latest = compute_freshness_aggregates(
        store, "ws1", only_latest_per_source=True,
    )
    assert agg_latest.total_alerts == 1


def test_latest_per_source_preserves_distinct_sources(
    store: FreshnessAlertStore,
) -> None:
    """Different sources don't dedup — each gets its own latest."""
    _record(store, source_url="https://a.com", status=FreshnessStatus.UNCHANGED)
    _record(store, source_url="https://b.com", status=FreshnessStatus.SUPERSEDED)
    _record(store, source_url="https://c.com", status=FreshnessStatus.RETRACTED)
    agg = compute_freshness_aggregates(
        store, "ws1", only_latest_per_source=True,
    )
    assert agg.total_alerts == 3
    assert agg.unique_source_count == 3


def test_only_latest_flag_echoed_in_aggregates(
    store: FreshnessAlertStore,
) -> None:
    agg_default = compute_freshness_aggregates(store, "ws1")
    assert agg_default.only_latest_per_source is False
    agg_latest = compute_freshness_aggregates(
        store, "ws1", only_latest_per_source=True,
    )
    assert agg_latest.only_latest_per_source is True


# ---------------------------------------------------------------------------
# Time-window filter
# ---------------------------------------------------------------------------


def test_since_filter_excludes_older(store: FreshnessAlertStore) -> None:
    _record(store, source_url="https://old.com",
            status=FreshnessStatus.UNCHANGED, checked_at=1000.0)
    _record(store, source_url="https://new.com",
            status=FreshnessStatus.UNCHANGED, checked_at=2000.0)
    agg = compute_freshness_aggregates(store, "ws1", since=1500.0)
    assert agg.total_alerts == 1
    assert agg.window_start == 1500.0


def test_until_filter_excludes_newer(store: FreshnessAlertStore) -> None:
    _record(store, source_url="https://old.com",
            status=FreshnessStatus.UNCHANGED, checked_at=1000.0)
    _record(store, source_url="https://new.com",
            status=FreshnessStatus.UNCHANGED, checked_at=2000.0)
    agg = compute_freshness_aggregates(store, "ws1", until=1500.0)
    assert agg.total_alerts == 1


def test_window_inclusive_at_boundary(store: FreshnessAlertStore) -> None:
    _record(store, source_url="https://x.com",
            status=FreshnessStatus.UNCHANGED, checked_at=1500.0)
    agg = compute_freshness_aggregates(
        store, "ws1", since=1500.0, until=1500.0,
    )
    assert agg.total_alerts == 1


def test_window_with_no_matches(store: FreshnessAlertStore) -> None:
    _record(store, checked_at=1000.0)
    agg = compute_freshness_aggregates(
        store, "ws1", since=2000.0, until=3000.0,
    )
    assert agg.total_alerts == 0


def test_open_window_includes_all(store: FreshnessAlertStore) -> None:
    for ts in (1000.0, 2000.0, 3000.0):
        _record(store, source_url=f"https://{ts}.com", checked_at=ts)
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.total_alerts == 3
    assert agg.window_start is None
    assert agg.window_end is None


# ---------------------------------------------------------------------------
# Window + latest interaction
# ---------------------------------------------------------------------------


def test_latest_per_source_within_window(store: FreshnessAlertStore) -> None:
    """latest-per-source rollup applies AFTER window filter.
    A retraction outside the window is NOT the latest for the
    purposes of an in-window query."""
    url = "https://x.com"
    _record(store, source_url=url, status=FreshnessStatus.UNCHANGED, checked_at=1000.0)
    _record(store, source_url=url, status=FreshnessStatus.UNCHANGED, checked_at=1500.0)
    # Retraction outside the window — should NOT dominate
    _record(store, source_url=url, status=FreshnessStatus.RETRACTED, checked_at=3000.0)
    agg = compute_freshness_aggregates(
        store, "ws1", since=1000.0, until=2000.0,
        only_latest_per_source=True,
    )
    assert agg.total_alerts == 1
    # Latest IN-WINDOW is the 1500.0 unchanged
    assert agg.unchanged_count == 1
    assert agg.retracted_count == 0


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation(store: FreshnessAlertStore) -> None:
    _record(store, workspace_id="ws_a", source_url="https://a.com",
            status=FreshnessStatus.RETRACTED)
    _record(store, workspace_id="ws_b", source_url="https://b.com",
            status=FreshnessStatus.UNCHANGED)
    agg_a = compute_freshness_aggregates(store, "ws_a")
    assert agg_a.total_alerts == 1
    assert agg_a.retracted_count == 1
    assert agg_a.unchanged_count == 0
    agg_b = compute_freshness_aggregates(store, "ws_b")
    assert agg_b.total_alerts == 1
    assert agg_b.unchanged_count == 1
    assert agg_b.retracted_count == 0


# ---------------------------------------------------------------------------
# unique_source_count
# ---------------------------------------------------------------------------


def test_unique_source_count_with_repeats(store: FreshnessAlertStore) -> None:
    """3 alerts on URL A + 2 alerts on URL B = 5 alerts, 2 unique sources."""
    for ts in (1000.0, 2000.0, 3000.0):
        _record(store, source_url="https://a.com", checked_at=ts)
    for ts in (1000.0, 2000.0):
        _record(store, source_url="https://b.com", checked_at=ts)
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.total_alerts == 5
    assert agg.unique_source_count == 2


def test_unique_source_count_after_window_filter(
    store: FreshnessAlertStore,
) -> None:
    """unique_source_count is computed over the WINDOWED set,
    not the whole store."""
    _record(store, source_url="https://a.com", checked_at=500.0)
    _record(store, source_url="https://b.com", checked_at=1500.0)
    _record(store, source_url="https://c.com", checked_at=2500.0)
    agg = compute_freshness_aggregates(
        store, "ws1", since=1000.0, until=2000.0,
    )
    assert agg.total_alerts == 1
    assert agg.unique_source_count == 1  # only b.com in window


# ---------------------------------------------------------------------------
# Counts sum invariant
# ---------------------------------------------------------------------------


def test_oversize_workspace_raises_rather_than_truncating(
    store: FreshnessAlertStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 HIGH fix (v2): when a workspace exceeds
    `_MAX_LIMIT`, the aggregator raises rather than silently
    returning the newest cap-many alerts and undercounting
    older in-window rows.

    v1 passed `limit=_MAX_LIMIT` to `list_alerts`, which the
    phase 1 store honors as "newest cap-many". A workspace
    with more than cap alerts had its older history silently
    dropped from the aggregate.
    """
    # Force a tiny cap to make the test cheap.
    import src.polaris_graph.audit_ir.freshness_aggregates as fa
    monkeypatch.setattr(fa, "_MAX_LIMIT", 2)
    # Insert 3 alerts (> cap of 2)
    for ts in (1000.0, 2000.0, 3000.0):
        _record(store, source_url=f"https://x{ts}.com", checked_at=ts)
    with pytest.raises(FreshnessAggregatesError, match="exceeding _MAX_LIMIT"):
        compute_freshness_aggregates(store, "ws1")


def test_under_cap_workspace_does_not_raise(
    store: FreshnessAlertStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At-cap is OK; over-cap raises. Pin the boundary."""
    import src.polaris_graph.audit_ir.freshness_aggregates as fa
    monkeypatch.setattr(fa, "_MAX_LIMIT", 2)
    for ts in (1000.0, 2000.0):
        _record(store, source_url=f"https://x{ts}.com", checked_at=ts)
    # Exactly at cap — should not raise
    agg = compute_freshness_aggregates(store, "ws1")
    assert agg.total_alerts == 2


def test_unknown_status_raises_in_default_mode(
    store: FreshnessAlertStore,
) -> None:
    """Codex round-1 LOW fix (v2): the schema-drift defense
    boundary documented as 'unknown status raises' was
    untested. This pins the all-alerts mode case."""

    class _DriftStore(FreshnessAlertStore):
        """Subclass override that returns an alert with a
        bogus status to simulate phase 1 schema drift (e.g. a
        future status added to the SQL CHECK without
        updating the aggregator)."""

        def list_alerts(self, *, workspace_id, status=None, limit=100):
            real = super().list_alerts(
                workspace_id=workspace_id, status=status, limit=limit,
            )
            if not real:
                return real
            from dataclasses import replace
            # Bogus the first one
            return [replace(real[0], status="future_unknown_status")] + real[1:]

    drift_store = _DriftStore(store._db_path)
    _record(drift_store, source_url="https://x.com")
    with pytest.raises(FreshnessAggregatesError, match="unknown status"):
        compute_freshness_aggregates(drift_store, "ws1")


def test_unknown_status_raises_in_latest_mode_too(
    store: FreshnessAlertStore,
) -> None:
    """Codex round-1 MEDIUM fix (v2): in latest-per-source
    mode, an unknown OLDER status for a cache_key was masked
    by a newer known status (the dedup ran first, then the
    drift check on the deduped list — so the older unknown
    was dropped silently). v2 runs schema-drift validation
    against the full windowed set BEFORE dedup."""

    class _DriftStore(FreshnessAlertStore):
        def list_alerts(self, *, workspace_id, status=None, limit=100):
            real = super().list_alerts(
                workspace_id=workspace_id, status=status, limit=limit,
            )
            if not real:
                return real
            # Two alerts on the same cache_key. The newer (first
            # in DESC order) keeps its real status; the older
            # has a bogus status. In latest-mode, dedup would
            # drop the older one — but v2 validates first.
            from dataclasses import replace
            if len(real) >= 2:
                return [
                    real[0],
                    replace(real[1], status="future_unknown_status"),
                ] + real[2:]
            return real

    drift_store = _DriftStore(store._db_path)
    url = "https://x.com"
    _record(drift_store, source_url=url, checked_at=1000.0)
    _record(drift_store, source_url=url, checked_at=2000.0)
    # latest-mode would dedup to 1 alert (the newest, status OK)
    # but v2 validates the full windowed set first, so it MUST
    # see the older bogus status and raise.
    with pytest.raises(FreshnessAggregatesError, match="unknown status"):
        compute_freshness_aggregates(
            drift_store, "ws1", only_latest_per_source=True,
        )


def test_status_counts_sum_to_total(store: FreshnessAlertStore) -> None:
    _record(store, source_url="https://a.com", status=FreshnessStatus.UNCHANGED)
    _record(store, source_url="https://b.com", status=FreshnessStatus.SUPERSEDED)
    _record(store, source_url="https://c.com", status=FreshnessStatus.RETRACTED)
    _record(store, source_url="https://d.com",
            status=FreshnessStatus.EXPRESSION_OF_CONCERN)
    _record(store, source_url="https://e.com", status=FreshnessStatus.UNREACHABLE)
    agg = compute_freshness_aggregates(store, "ws1")
    assert (
        agg.unchanged_count + agg.superseded_count + agg.retracted_count
        + agg.expression_of_concern_count + agg.unreachable_count
        == agg.total_alerts
    )
