"""M-D10 phase 1 (bootstrap) freshness-monitor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.freshness_monitor import (
    FreshnessAlert,
    FreshnessAlertStore,
    FreshnessCheckResult,
    FreshnessDetector,
    FreshnessMonitorError,
    FreshnessStatus,
    alert_to_dict,
    check_freshness,
)
from src.polaris_graph.audit_ir.retrieval_cache import (
    RetrievalCacheStore,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubDetector:
    """Test detector that returns a fixed result. Models the
    `FreshnessDetector` protocol."""

    def __init__(self, result: FreshnessCheckResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def detect(self, source_url: str) -> FreshnessCheckResult:
        self.calls.append(source_url)
        return self.result


class FixedClock:
    """Deterministic clock for alert-latency testing."""

    def __init__(self, t: float = 1700000000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> FreshnessAlertStore:
    return FreshnessAlertStore(tmp_path / "freshness.db")


@pytest.fixture
def cache(tmp_path: Path) -> RetrievalCacheStore:
    return RetrievalCacheStore(tmp_path / "cache.db")


# ---------------------------------------------------------------------------
# FreshnessAlertStore.record
# ---------------------------------------------------------------------------


def test_record_unchanged_alert(store: FreshnessAlertStore) -> None:
    alert = store.record(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        status=FreshnessStatus.UNCHANGED,
        details=None,
        new_canonical_url=None,
        fetched_status_code=200,
        checked_at=1700000000.0,
        evicted_cache_key=None,
    )
    assert alert.alert_id != ""
    assert alert.workspace_id == "ws-a"
    assert alert.status == "unchanged"
    assert alert.checked_at == 1700000000.0


def test_record_retracted_alert(store: FreshnessAlertStore) -> None:
    alert = store.record(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        status=FreshnessStatus.RETRACTED,
        details="retraction notice 2026-04-15",
        new_canonical_url=None,
        fetched_status_code=200,
        checked_at=1700000000.0,
        evicted_cache_key="doi:10.1000/foo",
    )
    assert alert.status == "retracted"
    assert alert.details == "retraction notice 2026-04-15"
    assert alert.evicted_cache_key == "doi:10.1000/foo"


def test_record_rejects_non_status(store: FreshnessAlertStore) -> None:
    with pytest.raises(FreshnessMonitorError, match="status"):
        store.record(
            workspace_id="ws-a",
            source_url="x",
            status="retracted",  # type: ignore[arg-type]
            details=None,
            new_canonical_url=None,
            fetched_status_code=None,
            checked_at=0.0,
            evicted_cache_key=None,
        )


def test_record_rejects_empty_workspace(
    store: FreshnessAlertStore,
) -> None:
    with pytest.raises(FreshnessMonitorError, match="workspace_id"):
        store.record(
            workspace_id="",
            source_url="x",
            status=FreshnessStatus.UNCHANGED,
            details=None,
            new_canonical_url=None,
            fetched_status_code=200,
            checked_at=0.0,
            evicted_cache_key=None,
        )


# ---------------------------------------------------------------------------
# FreshnessAlertStore.list_alerts
# ---------------------------------------------------------------------------


def test_list_alerts_empty(store: FreshnessAlertStore) -> None:
    assert store.list_alerts(workspace_id="ws-a") == []


def test_list_alerts_newest_first(
    store: FreshnessAlertStore,
) -> None:
    store.record(
        workspace_id="ws-a", source_url="u1",
        status=FreshnessStatus.UNCHANGED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=100.0, evicted_cache_key=None,
    )
    store.record(
        workspace_id="ws-a", source_url="u2",
        status=FreshnessStatus.RETRACTED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=200.0, evicted_cache_key=None,
    )
    rows = store.list_alerts(workspace_id="ws-a")
    assert len(rows) == 2
    assert rows[0].source_url == "u2"  # newer
    assert rows[1].source_url == "u1"


def test_list_alerts_filter_by_status(
    store: FreshnessAlertStore,
) -> None:
    for s, ts in [
        (FreshnessStatus.UNCHANGED, 100.0),
        (FreshnessStatus.RETRACTED, 200.0),
        (FreshnessStatus.SUPERSEDED, 300.0),
        (FreshnessStatus.UNCHANGED, 400.0),
    ]:
        store.record(
            workspace_id="ws-a", source_url=f"u{ts}",
            status=s, details=None, new_canonical_url=None,
            fetched_status_code=200, checked_at=ts,
            evicted_cache_key=None,
        )
    retracted = store.list_alerts(
        workspace_id="ws-a", status=FreshnessStatus.RETRACTED,
    )
    assert len(retracted) == 1
    assert retracted[0].status == "retracted"


def test_list_alerts_limit(
    store: FreshnessAlertStore,
) -> None:
    for i in range(10):
        store.record(
            workspace_id="ws-a", source_url=f"u{i}",
            status=FreshnessStatus.UNCHANGED, details=None,
            new_canonical_url=None, fetched_status_code=200,
            checked_at=float(i), evicted_cache_key=None,
        )
    assert len(store.list_alerts(workspace_id="ws-a", limit=3)) == 3


def test_list_alerts_rejects_zero_limit(
    store: FreshnessAlertStore,
) -> None:
    with pytest.raises(FreshnessMonitorError, match=">0"):
        store.list_alerts(workspace_id="ws-a", limit=0)


# ---------------------------------------------------------------------------
# FreshnessAlertStore.latest_for_url
# ---------------------------------------------------------------------------


def test_latest_for_url_returns_newest(
    store: FreshnessAlertStore,
) -> None:
    """Multiple checks for the same URL return the most recent."""
    store.record(
        workspace_id="ws-a", source_url="u1",
        status=FreshnessStatus.UNCHANGED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=100.0, evicted_cache_key=None,
    )
    store.record(
        workspace_id="ws-a", source_url="u1",
        status=FreshnessStatus.RETRACTED, details="updated",
        new_canonical_url=None, fetched_status_code=200,
        checked_at=200.0, evicted_cache_key=None,
    )
    latest = store.latest_for_url("ws-a", "u1")
    assert latest is not None
    assert latest.status == "retracted"
    assert latest.checked_at == 200.0


def test_latest_for_url_miss_returns_none(
    store: FreshnessAlertStore,
) -> None:
    assert store.latest_for_url("ws-a", "never") is None


# ---------------------------------------------------------------------------
# Cross-workspace isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation_list(
    store: FreshnessAlertStore,
) -> None:
    store.record(
        workspace_id="ws-a", source_url="u1",
        status=FreshnessStatus.UNCHANGED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=100.0, evicted_cache_key=None,
    )
    store.record(
        workspace_id="ws-b", source_url="u1",
        status=FreshnessStatus.RETRACTED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=200.0, evicted_cache_key=None,
    )
    a_rows = store.list_alerts(workspace_id="ws-a")
    b_rows = store.list_alerts(workspace_id="ws-b")
    assert len(a_rows) == 1 and a_rows[0].status == "unchanged"
    assert len(b_rows) == 1 and b_rows[0].status == "retracted"


def test_workspace_isolation_latest_for_url(
    store: FreshnessAlertStore,
) -> None:
    """Same URL in two workspaces — latest_for_url returns the
    one from the queried workspace, not whichever was newer
    globally."""
    store.record(
        workspace_id="ws-a", source_url="u1",
        status=FreshnessStatus.UNCHANGED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=100.0, evicted_cache_key=None,
    )
    store.record(
        workspace_id="ws-b", source_url="u1",
        status=FreshnessStatus.RETRACTED, details=None,
        new_canonical_url=None, fetched_status_code=200,
        checked_at=999.0, evicted_cache_key=None,
    )
    a_latest = store.latest_for_url("ws-a", "u1")
    assert a_latest is not None
    assert a_latest.status == "unchanged"  # ws-a's 100.0, not ws-b's 999.0


# ---------------------------------------------------------------------------
# CHECK constraint enforces taxonomy at SQL level
# ---------------------------------------------------------------------------


def test_taxonomy_check_constraint(
    store: FreshnessAlertStore,
) -> None:
    """Raw SQL with an invalid status string must fail at the
    DB layer, not silently insert. Defense-in-depth — even if a
    future caller bypasses FreshnessStatus enum, the DB rejects."""
    import sqlite3
    with store._connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO freshness_alerts
                    (alert_id, workspace_id, source_url, status,
                     details, new_canonical_url,
                     fetched_status_code, checked_at,
                     evicted_cache_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "fake-id", "ws-a", "u1", "fabricated_status",
                    None, None, 200, 0.0, None,
                ),
            )


# ---------------------------------------------------------------------------
# count()
# ---------------------------------------------------------------------------


def test_count_all_and_filtered(
    store: FreshnessAlertStore,
) -> None:
    for s in (
        FreshnessStatus.UNCHANGED,
        FreshnessStatus.UNCHANGED,
        FreshnessStatus.RETRACTED,
    ):
        store.record(
            workspace_id="ws-a", source_url="u",
            status=s, details=None, new_canonical_url=None,
            fetched_status_code=200, checked_at=1.0,
            evicted_cache_key=None,
        )
    assert store.count(workspace_id="ws-a") == 3
    assert (
        store.count(workspace_id="ws-a", status=FreshnessStatus.RETRACTED)
        == 1
    )


# ---------------------------------------------------------------------------
# check_freshness coordinator
# ---------------------------------------------------------------------------


def test_check_freshness_records_unchanged_no_evict(
    store: FreshnessAlertStore, cache: RetrievalCacheStore,
) -> None:
    """unchanged status: alert recorded, cache NOT evicted even
    if cache has the entry."""
    cache.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"<html>article</html>",
        content_type="text/html",
        fetch_status_code=200,
    )
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="https://doi.org/10.1000/foo",
            status=FreshnessStatus.UNCHANGED,
            fetched_status_code=200,
        )
    )
    clock = FixedClock(1700000000.0)
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        detector=detector,
        store=store,
        cache=cache,
        clock=clock,
    )
    assert alert.status == "unchanged"
    assert alert.evicted_cache_key is None
    assert alert.checked_at == 1700000000.0
    # Cache still has the entry.
    assert cache.get("ws-a", "https://doi.org/10.1000/foo") is not None


def test_check_freshness_retracted_evicts_cache(
    store: FreshnessAlertStore, cache: RetrievalCacheStore,
) -> None:
    """retracted status: alert recorded AND cache evicted."""
    cache.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"<html>article</html>",
        content_type="text/html",
        fetch_status_code=200,
    )
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="https://doi.org/10.1000/foo",
            status=FreshnessStatus.RETRACTED,
            details="retraction notice 2026-04-15",
            fetched_status_code=200,
        )
    )
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        detector=detector,
        store=store,
        cache=cache,
        clock=FixedClock(),
    )
    assert alert.status == "retracted"
    assert alert.evicted_cache_key == "doi:10.1000/foo"
    # Cache entry is gone.
    assert cache.get("ws-a", "https://doi.org/10.1000/foo") is None


def test_check_freshness_superseded_evicts_cache(
    store: FreshnessAlertStore, cache: RetrievalCacheStore,
) -> None:
    """superseded status: same eviction behavior as retracted."""
    cache.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="10.1000/foo",
            status=FreshnessStatus.SUPERSEDED,
            new_canonical_url="https://doi.org/10.1000/foo-v2",
            fetched_status_code=200,
        )
    )
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        detector=detector,
        store=store,
        cache=cache,
        clock=FixedClock(),
    )
    assert alert.status == "superseded"
    assert alert.evicted_cache_key == "doi:10.1000/foo"
    assert alert.new_canonical_url == "https://doi.org/10.1000/foo-v2"
    assert cache.get("ws-a", "10.1000/foo") is None


def test_check_freshness_unreachable_does_not_evict(
    store: FreshnessAlertStore, cache: RetrievalCacheStore,
) -> None:
    """unreachable status: alert recorded but cache NOT evicted
    (transient outage shouldn't drop a valid cached payload)."""
    cache.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="10.1000/foo",
            status=FreshnessStatus.UNREACHABLE,
            fetched_status_code=503,
        )
    )
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        detector=detector,
        store=store,
        cache=cache,
        clock=FixedClock(),
    )
    assert alert.status == "unreachable"
    assert alert.evicted_cache_key is None
    # Cache entry preserved.
    assert cache.get("ws-a", "10.1000/foo") is not None


def test_check_freshness_no_cache_provided_just_records(
    store: FreshnessAlertStore,
) -> None:
    """If no cache injected, retracted alert is still recorded
    but no eviction attempt happens."""
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="10.1000/foo",
            status=FreshnessStatus.RETRACTED,
            fetched_status_code=200,
        )
    )
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        detector=detector,
        store=store,
        cache=None,
        clock=FixedClock(),
    )
    assert alert.status == "retracted"
    assert alert.evicted_cache_key is None


def test_check_freshness_clock_injected(
    store: FreshnessAlertStore,
) -> None:
    """The clock is the mechanism for alert-latency testing in
    phase 2 — checked_at must reflect the injected clock, not
    wall time."""
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="u",
            status=FreshnessStatus.UNCHANGED,
            fetched_status_code=200,
        )
    )
    clock = FixedClock(1700000123.0)
    alert = check_freshness(
        workspace_id="ws-a",
        source_url="u",
        detector=detector,
        store=store,
        clock=clock,
    )
    assert alert.checked_at == 1700000123.0


def test_check_freshness_detector_protocol_violation(
    store: FreshnessAlertStore,
) -> None:
    """Detectors must return FreshnessCheckResult — anything
    else fails loudly."""
    class BadDetector:
        def detect(self, source_url):
            return {"status": "retracted"}  # wrong shape

    with pytest.raises(FreshnessMonitorError, match="FreshnessCheckResult"):
        check_freshness(
            workspace_id="ws-a",
            source_url="u",
            detector=BadDetector(),  # type: ignore[arg-type]
            store=store,
        )


def test_check_freshness_eviction_error_propagates(
    store: FreshnessAlertStore,
) -> None:
    """If the cache.evict_by_url raises, the monitor must NOT
    silently swallow — caller needs to know cache state is
    unknown."""

    class BrokenCache:
        def evict_by_url(self, workspace_id, source_url):
            raise RuntimeError("cache disk full")

    detector = StubDetector(
        FreshnessCheckResult(
            source_url="10.1000/foo",
            status=FreshnessStatus.RETRACTED,
            fetched_status_code=200,
        )
    )
    with pytest.raises(RuntimeError, match="cache disk full"):
        check_freshness(
            workspace_id="ws-a",
            source_url="10.1000/foo",
            detector=detector,
            store=store,
            cache=BrokenCache(),
        )
    # Crucially, NO alert was recorded — record-after-evict
    # contract means the alert log doesn't claim eviction
    # succeeded when it didn't.
    assert store.count(workspace_id="ws-a") == 0


def test_check_freshness_rejects_empty_workspace(
    store: FreshnessAlertStore,
) -> None:
    detector = StubDetector(
        FreshnessCheckResult(
            source_url="u",
            status=FreshnessStatus.UNCHANGED,
        )
    )
    with pytest.raises(FreshnessMonitorError, match="workspace_id"):
        check_freshness(
            workspace_id="",
            source_url="u",
            detector=detector,
            store=store,
        )


# ---------------------------------------------------------------------------
# Coexists with M-21 + M-D7 in same DB
# ---------------------------------------------------------------------------


def test_coexists_with_m21_and_md7_in_same_db(
    tmp_path: Path,
) -> None:
    """All three Phase D / Phase C audit_ir SQLite stores can
    share a single DB file. Confirms the substrate decision."""
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStore,
    )

    db = tmp_path / "ws.db"
    mem = WorkspaceMemoryStore(db)
    cache = RetrievalCacheStore(db)
    freshness = FreshnessAlertStore(db)

    # All three operate independently.
    mem.append_entry(
        workspace_id="ws-a",
        claim_text="x",
        source_url="https://doi.org/10.1000/foo",
        source_tier="T1",
        source_evidence_id="ev_001",
    )
    cache.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    freshness.record(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        status=FreshnessStatus.UNCHANGED,
        details=None,
        new_canonical_url=None,
        fetched_status_code=200,
        checked_at=1.0,
        evicted_cache_key=None,
    )
    assert len(mem.list_entries(workspace_id="ws-a")) == 1
    assert cache.count("ws-a") == 1
    assert freshness.count(workspace_id="ws-a") == 1


# ---------------------------------------------------------------------------
# Dict serialization
# ---------------------------------------------------------------------------


def test_alert_to_dict_round_trips_shape() -> None:
    alert = FreshnessAlert(
        alert_id="abc-123",
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        status="retracted",
        details="formal retraction",
        new_canonical_url=None,
        fetched_status_code=200,
        checked_at=1700000000.0,
        evicted_cache_key="doi:10.1000/foo",
    )
    d = alert_to_dict(alert)
    assert d["alert_id"] == "abc-123"
    assert d["status"] == "retracted"
    assert d["evicted_cache_key"] == "doi:10.1000/foo"
    assert d["checked_at"] == 1700000000.0
