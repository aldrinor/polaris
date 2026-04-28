"""M-D10 (Phase D): Citation freshness monitoring — bootstrap.

Per FINAL_PLAN M-D10 + Phase D milestones plan: detect when
cited DOIs/PMIDs are retracted, expressions of concern issued,
or guidance documents superseded. Pairs with M-D7's
`RetrievalCacheStore.evict_by_url` so that detected stale
sources flush from cache automatically.

Phase 1 ships **detector contract + alerts substrate**:
  - FreshnessDetector protocol (caller injects real Crossref /
    PubMed / retraction-watch implementations)
  - FreshnessAlertStore extending M-21 SQLite substrate (one
    extra `freshness_alerts` table)
  - check_freshness() coordinator: runs detector, records the
    check, optionally evicts from M-D7 cache

Phase 2 (deferred):
  - Real Crossref `update-policy` integration
  - Real PubMed retraction-status integration
  - Polling daemon (watches a workspace's cited URLs on a
    schedule)
  - Operator notification callbacks (writes into M-23 review
    queue when alert lands)
  - Empirical alert-latency ≤ 24h acceptance test

## Status taxonomy

The detector returns one of four discrete outcomes:

  - `unchanged`: source still authoritative; no alert needed.
    Recorded as a heartbeat but doesn't trigger eviction.
  - `superseded`: a newer canonical version exists (e.g.
    Crossref `update-policy` indicates an updated DOI). Alert
    + evict cache.
  - `retracted`: source has been formally retracted or has an
    expression of concern. Alert + evict cache. Operator
    review required for any audit referencing this source.
  - `unreachable`: source returned 4xx/5xx or timed out. Alert
    + DO NOT evict cache (a temporary outage shouldn't drop a
    valid cached payload). Phase 2 daemon would retry-with-
    backoff before treating as superseded/retracted.

## Why pluggable detector

The real detection logic depends on source-specific protocols
(Crossref, PubMed, retraction watch). Phase 1 establishes the
contract so phase 2 can plug in concrete implementations
without rewriting the alert-recording substrate.

For testing, callers inject a deterministic stub detector. For
production, callers will inject a real fetcher-backed detector
in phase 2.

## Pin coupling

Freshness alert state is workspace-scoped, NOT in
`ModelPin.retrieval_source_versions` (which is run-scoped).
Same boundary as M-D7's cache state. See
`docs/md10_phase1_threat_model.md` for the full boundary.

## What "alert" means in phase 1

Record-only. A FreshnessAlert lands in the
`freshness_alerts` table and is queryable via
`list_alerts(workspace_id, status=...)`. Phase 2 adds the
notification callback into M-23 review queue.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FreshnessMonitorError(Exception):
    """Raised on schema/state violations."""


# ---------------------------------------------------------------------------
# Status taxonomy
# ---------------------------------------------------------------------------


class FreshnessStatus(Enum):
    """Closed taxonomy of detector verdicts.

    `unchanged`: source still authoritative; alert recorded as
       heartbeat but no eviction.
    `superseded`: newer canonical version exists; alert +
       evict.
    `retracted`: formal retraction or expression of concern;
       alert + evict; operator review needed.
    `unreachable`: 4xx/5xx or timeout; alert recorded but cache
       NOT evicted (transient outage doesn't justify dropping
       a valid cached payload). Phase 2 daemon will
       retry-with-backoff.
    """

    UNCHANGED = "unchanged"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    UNREACHABLE = "unreachable"


# Statuses that trigger cache eviction.
_EVICTING_STATUSES = frozenset({
    FreshnessStatus.SUPERSEDED,
    FreshnessStatus.RETRACTED,
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessCheckResult:
    """One detector verdict for one source URL.

    Detector returns this; the monitor coordinator persists it
    via FreshnessAlertStore.
    """

    source_url: str
    status: FreshnessStatus
    details: str | None = None
    new_canonical_url: str | None = None
    fetched_status_code: int | None = None


@dataclass(frozen=True)
class FreshnessAlert:
    """One recorded freshness check.

    `alert_id` is a UUID4 string.
    `checked_at` is the unix timestamp when the detector ran
    (NOT a wall-clock call; injected via the monitor's clock so
    tests can pin time).
    `evicted_cache_key` is set if the monitor invalidated the
    M-D7 cache as part of recording this alert. None if cache
    not provided or status didn't trigger eviction.
    """

    alert_id: str
    workspace_id: str
    source_url: str
    status: str  # FreshnessStatus.value
    details: str | None
    new_canonical_url: str | None
    fetched_status_code: int | None
    checked_at: float
    evicted_cache_key: str | None


def alert_to_dict(alert: FreshnessAlert) -> dict[str, Any]:
    """JSON-safe dict representation."""
    return {
        "alert_id": alert.alert_id,
        "workspace_id": alert.workspace_id,
        "source_url": alert.source_url,
        "status": alert.status,
        "details": alert.details,
        "new_canonical_url": alert.new_canonical_url,
        "fetched_status_code": alert.fetched_status_code,
        "checked_at": alert.checked_at,
        "evicted_cache_key": alert.evicted_cache_key,
    }


# ---------------------------------------------------------------------------
# Detector protocol
# ---------------------------------------------------------------------------


class FreshnessDetector(Protocol):
    """Pluggable detector. Phase 1 ships only the contract;
    callers inject real Crossref / PubMed / retraction-watch
    implementations or test stubs.

    A detector is stateless from the monitor's point of view —
    each `detect()` call is independent. Detector implementations
    may internally cache fetched-recently signals; that's their
    concern.
    """

    def detect(self, source_url: str) -> FreshnessCheckResult:
        """Classify the current freshness of `source_url`."""
        ...


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS freshness_alerts (
    alert_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    new_canonical_url TEXT,
    fetched_status_code INTEGER,
    checked_at REAL NOT NULL,
    evicted_cache_key TEXT,
    CHECK (status IN ('unchanged', 'superseded', 'retracted',
                      'unreachable'))
);

CREATE INDEX IF NOT EXISTS idx_freshness_ws_checked
    ON freshness_alerts(workspace_id, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_freshness_ws_status
    ON freshness_alerts(workspace_id, status);

-- Latest-per-URL queries (e.g. "is this DOI currently
-- flagged?") need an indexed scan by (workspace, url, time).
CREATE INDEX IF NOT EXISTS idx_freshness_ws_url_checked
    ON freshness_alerts(workspace_id, source_url, checked_at DESC);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class FreshnessAlertStore:
    """SQLite-backed alert log, per-workspace isolated.

    Pattern matches M-21 / M-D7: per-call WAL connections from a
    Path. Cross-workspace isolation: every read/write requires
    workspace_id; same DB file as workspace_memory + retrieval
    cache.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def record(
        self,
        *,
        workspace_id: str,
        source_url: str,
        status: FreshnessStatus,
        details: str | None,
        new_canonical_url: str | None,
        fetched_status_code: int | None,
        checked_at: float,
        evicted_cache_key: str | None,
    ) -> FreshnessAlert:
        """Persist one alert. Returns the saved record."""
        if not workspace_id or not workspace_id.strip():
            raise FreshnessMonitorError(
                "workspace_id must be non-empty"
            )
        if not source_url or not source_url.strip():
            raise FreshnessMonitorError(
                "source_url must be non-empty"
            )
        if not isinstance(status, FreshnessStatus):
            raise FreshnessMonitorError(
                f"status must be FreshnessStatus, "
                f"got {type(status).__name__}"
            )
        ws = workspace_id.strip()
        url = source_url.strip()
        alert_id = str(uuid.uuid4())

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO freshness_alerts
                    (alert_id, workspace_id, source_url, status,
                     details, new_canonical_url,
                     fetched_status_code, checked_at,
                     evicted_cache_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (alert_id, ws, url, status.value, details,
                 new_canonical_url, fetched_status_code,
                 checked_at, evicted_cache_key),
            )
        return FreshnessAlert(
            alert_id=alert_id,
            workspace_id=ws,
            source_url=url,
            status=status.value,
            details=details,
            new_canonical_url=new_canonical_url,
            fetched_status_code=fetched_status_code,
            checked_at=checked_at,
            evicted_cache_key=evicted_cache_key,
        )

    def list_alerts(
        self,
        *,
        workspace_id: str,
        status: FreshnessStatus | None = None,
        limit: int = 100,
    ) -> list[FreshnessAlert]:
        """Query alerts for a workspace, newest first.

        `status` filter narrows to one taxonomy value.
        `limit` defaults to 100; pass a larger value if needed.
        Cross-workspace isolation: only returns rows for the
        passed workspace_id.
        """
        if not workspace_id or not workspace_id.strip():
            raise FreshnessMonitorError(
                "workspace_id must be non-empty"
            )
        if limit <= 0:
            raise FreshnessMonitorError("limit must be >0")

        sql = (
            "SELECT * FROM freshness_alerts "
            "WHERE workspace_id=? "
        )
        params: list[Any] = [workspace_id.strip()]
        if status is not None:
            if not isinstance(status, FreshnessStatus):
                raise FreshnessMonitorError(
                    "status filter must be FreshnessStatus"
                )
            sql += "AND status=? "
            params.append(status.value)
        sql += "ORDER BY checked_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_alert(r) for r in rows]

    def latest_for_url(
        self, workspace_id: str, source_url: str
    ) -> FreshnessAlert | None:
        """Newest alert for one source URL in this workspace.
        Returns None if no alerts recorded for this URL."""
        if not workspace_id or not workspace_id.strip():
            raise FreshnessMonitorError(
                "workspace_id must be non-empty"
            )
        if not source_url or not source_url.strip():
            raise FreshnessMonitorError(
                "source_url must be non-empty"
            )
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM freshness_alerts "
                "WHERE workspace_id=? AND source_url=? "
                "ORDER BY checked_at DESC LIMIT 1",
                (workspace_id.strip(), source_url.strip()),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_alert(row)

    def count(
        self,
        *,
        workspace_id: str,
        status: FreshnessStatus | None = None,
    ) -> int:
        """Total alerts (optionally filtered by status)."""
        if not workspace_id or not workspace_id.strip():
            raise FreshnessMonitorError(
                "workspace_id must be non-empty"
            )
        sql = (
            "SELECT COUNT(*) FROM freshness_alerts "
            "WHERE workspace_id=?"
        )
        params: list[Any] = [workspace_id.strip()]
        if status is not None:
            if not isinstance(status, FreshnessStatus):
                raise FreshnessMonitorError(
                    "status filter must be FreshnessStatus"
                )
            sql += " AND status=?"
            params.append(status.value)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


def check_freshness(
    *,
    workspace_id: str,
    source_url: str,
    detector: FreshnessDetector,
    store: FreshnessAlertStore,
    cache: Any | None = None,
    clock: Callable[[], float] = time.time,
) -> FreshnessAlert:
    """Run one freshness check end-to-end.

    Steps:
      1. detector.detect(source_url) → FreshnessCheckResult
      2. If result.status in {SUPERSEDED, RETRACTED} AND cache
         provided, call cache.evict_by_url(workspace_id, url).
         Capture the cache_key that was evicted (if any).
      3. store.record(...) the alert with the eviction outcome.
      4. Return the persisted FreshnessAlert.

    `cache` is `RetrievalCacheStore | None`; typed as Any here
    to avoid a hard import-time coupling — phase 1 can be tested
    with a pure stub.

    `clock` is a `() -> float` callable. Tests inject a fixed
    clock to assert alert-latency semantics deterministically.
    """
    if not workspace_id or not workspace_id.strip():
        raise FreshnessMonitorError("workspace_id must be non-empty")
    if not source_url or not source_url.strip():
        raise FreshnessMonitorError("source_url must be non-empty")
    if detector is None:
        raise FreshnessMonitorError("detector must be provided")
    if store is None:
        raise FreshnessMonitorError("store must be provided")

    result = detector.detect(source_url)
    if not isinstance(result, FreshnessCheckResult):
        raise FreshnessMonitorError(
            f"detector must return FreshnessCheckResult, "
            f"got {type(result).__name__}"
        )

    evicted_key: str | None = None
    if cache is not None and result.status in _EVICTING_STATUSES:
        from src.polaris_graph.audit_ir.retrieval_cache import (
            make_cache_key,
        )
        try:
            cache_key = make_cache_key(source_url)
        except Exception:
            # If the URL can't be canonicalized into a cache key,
            # we still record the alert but skip eviction.
            cache_key = None
        if cache_key is not None:
            try:
                if cache.evict_by_url(workspace_id, source_url):
                    evicted_key = cache_key
            except Exception:
                # Eviction failure must not silently swallow the
                # alert; re-raise so the caller knows the cache
                # is in an unknown state.
                raise

    return store.record(
        workspace_id=workspace_id,
        source_url=source_url,
        status=result.status,
        details=result.details,
        new_canonical_url=result.new_canonical_url,
        fetched_status_code=result.fetched_status_code,
        checked_at=clock(),
        evicted_cache_key=evicted_key,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_alert(row: sqlite3.Row) -> FreshnessAlert:
    return FreshnessAlert(
        alert_id=row["alert_id"],
        workspace_id=row["workspace_id"],
        source_url=row["source_url"],
        status=row["status"],
        details=row["details"],
        new_canonical_url=row["new_canonical_url"],
        fetched_status_code=row["fetched_status_code"],
        checked_at=row["checked_at"],
        evicted_cache_key=row["evicted_cache_key"],
    )
