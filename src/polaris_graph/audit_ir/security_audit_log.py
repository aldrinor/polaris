"""Security audit log (M-19 — Phase C).

Per FINAL_PLAN Phase C deliverable #9:
  Pilot-grade SOC2 readiness (procurement-friendly, not formally
  certified).

The minimum viable security audit log a procurement reviewer wants
to see:
  - Every authenticated action attributed to a user_id + org_id
  - Every authentication failure recorded with reason + IP/UA
  - Every cross-tenant access attempt recorded as a WARN-level
    security event (not silently 403'd)
  - Append-only storage with timestamps
  - Hard-delete impossible from the API surface (only via
    operator + tested data-retention policy — out of scope for v1)

This module ships ONLY the storage + recording surface. Wiring
into auth_middleware happens in a follow-up (so the auth
substrate ships unmodified for now). Procurement reviewers
typically ask "show me the security event schema and a query
that returns recent failed-login events" — that's what M-19 v1
satisfies.

LAW VII compliance: this module imports only from stdlib and
does not reach back into runner / generator / API routing.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SecurityEventType(Enum):
    """Stable string-valued event-type codes.

    SOC2 procurement reviewers expect a closed enum here so they
    can write "tell me when {AUTH_FAILED, CROSS_TENANT_DENIED,
    PRIVILEGE_ESCALATION_ATTEMPT} happens" without inspecting
    free-form text.
    """

    AUTH_SUCCEEDED = "auth_succeeded"
    AUTH_FAILED = "auth_failed"
    CROSS_TENANT_DENIED = "cross_tenant_denied"
    PRIVILEGE_ESCALATION_DENIED = "privilege_escalation_denied"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    USER_ROLE_CHANGED = "user_role_changed"
    # Codex M-19 v1 review fix: access-grant/revoke must be a
    # first-class event for SOC2 procurement. role-change alone
    # doesn't cover the "user added to / removed from an org"
    # surface (auth_store's add_membership / remove_membership).
    MEMBERSHIP_ADDED = "membership_added"
    MEMBERSHIP_REMOVED = "membership_removed"
    DATA_DELETED = "data_deleted"
    AUDIT_BUNDLE_EXPORTED = "audit_bundle_exported"


class EventSeverity(Enum):
    """Severity for triage. INFO is the default for SUCCEEDED
    events; WARN is the default for failed-auth and denial
    events; CRITICAL is reserved for events the operator must
    review immediately (e.g. repeated cross-tenant denials from
    the same caller, treated as an attack signal in Phase D)."""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityEvent:
    """One security audit-log row.

    `details_json` carries event-specific structured data
    (request path, resource_id, denial reason, etc.) as a JSON-
    encoded string so the schema stays stable while individual
    event types add fields over time.
    """

    event_id: str
    event_type: SecurityEventType
    severity: EventSeverity
    user_id: str | None
    org_id: str | None
    source_ip: str | None
    user_agent: str | None
    request_method: str | None
    request_path: str | None
    details_json: str
    created_at: float


def event_to_dict(event: SecurityEvent) -> dict[str, Any]:
    """Serialize a SecurityEvent for JSON transport."""
    try:
        details = json.loads(event.details_json) if event.details_json else {}
    except json.JSONDecodeError:
        details = {"raw": event.details_json}
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "user_id": event.user_id,
        "org_id": event.org_id,
        "source_ip": event.source_ip,
        "user_agent": event.user_agent,
        "request_method": event.request_method,
        "request_path": event.request_path,
        "details": details,
        "created_at": event.created_at,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    user_id TEXT,
    org_id TEXT,
    source_ip TEXT,
    user_agent TEXT,
    request_method TEXT,
    request_path TEXT,
    details_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- The two queries SOC2 reviewers run:
--   1) "all WARN/CRITICAL events in the last 24h" — uses
--      idx_security_events_severity_created
--   2) "all events for org X in date range" — uses
--      idx_security_events_org_created
CREATE INDEX IF NOT EXISTS idx_security_events_severity_created
    ON security_events(severity, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_events_org_created
    ON security_events(org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_events_user_created
    ON security_events(user_id, created_at DESC);
"""


# ---------------------------------------------------------------------------
# Default severity by event type
# ---------------------------------------------------------------------------


_DEFAULT_SEVERITY: dict[SecurityEventType, EventSeverity] = {
    SecurityEventType.AUTH_SUCCEEDED: EventSeverity.INFO,
    SecurityEventType.AUTH_FAILED: EventSeverity.WARN,
    SecurityEventType.CROSS_TENANT_DENIED: EventSeverity.WARN,
    SecurityEventType.PRIVILEGE_ESCALATION_DENIED: EventSeverity.WARN,
    SecurityEventType.API_KEY_CREATED: EventSeverity.INFO,
    SecurityEventType.API_KEY_REVOKED: EventSeverity.INFO,
    SecurityEventType.USER_ROLE_CHANGED: EventSeverity.INFO,
    SecurityEventType.MEMBERSHIP_ADDED: EventSeverity.INFO,
    SecurityEventType.MEMBERSHIP_REMOVED: EventSeverity.INFO,
    SecurityEventType.DATA_DELETED: EventSeverity.INFO,
    SecurityEventType.AUDIT_BUNDLE_EXPORTED: EventSeverity.INFO,
}


# Codex M-19 v1 review fix: events that REQUIRE attribution.
# Anonymous AUTH_FAILED is OK (the failure is the point — there
# may not be a valid user_id), but SUCCESS / cross-tenant /
# privilege-escalation / membership / data-deletion / export
# events must carry both user_id AND org_id to satisfy "every
# authenticated action attributed to user_id + org_id."
_REQUIRES_ATTRIBUTION: frozenset[SecurityEventType] = frozenset({
    SecurityEventType.AUTH_SUCCEEDED,
    SecurityEventType.CROSS_TENANT_DENIED,
    SecurityEventType.PRIVILEGE_ESCALATION_DENIED,
    SecurityEventType.API_KEY_CREATED,
    SecurityEventType.API_KEY_REVOKED,
    SecurityEventType.USER_ROLE_CHANGED,
    SecurityEventType.MEMBERSHIP_ADDED,
    SecurityEventType.MEMBERSHIP_REMOVED,
    SecurityEventType.DATA_DELETED,
    SecurityEventType.AUDIT_BUNDLE_EXPORTED,
})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SecurityAuditLogError(Exception):
    """Raised on validation failures."""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SecurityAuditLog:
    """SQLite-backed append-only security event store.

    Per-call connections (matches WorkspaceStore + JobQueue +
    ReviewStore + WorkspaceMemoryStore pattern). WAL mode for
    concurrent reads.

    LAW II / SOC2 expectation: NO public mutation API beyond
    `record_event`. There is no `update_event` and no
    `delete_event`. Customers asking "can someone tamper with the
    audit log via the API?" must be able to read the source code
    and confirm "no — there's only `record_event`."
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Append (the only mutation surface)
    # ------------------------------------------------------------------

    def record_event(
        self,
        *,
        event_type: SecurityEventType,
        severity: EventSeverity | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SecurityEvent:
        """Append one event.

        `severity` defaults from `_DEFAULT_SEVERITY` if not
        explicitly passed. `details` is encoded as JSON; a non-
        serializable value falls back to `{"raw": str(...)}` so
        we never silently drop information.
        """
        if not isinstance(event_type, SecurityEventType):
            raise SecurityAuditLogError(
                f"event_type must be SecurityEventType, got {event_type!r}"
            )
        if severity is None:
            severity = _DEFAULT_SEVERITY[event_type]
        if not isinstance(severity, EventSeverity):
            raise SecurityAuditLogError(
                f"severity must be EventSeverity, got {severity!r}"
            )
        # Codex M-19 v1 review fix: enforce attribution for
        # event types where "who did this?" is the whole point.
        # Anonymous AUTH_FAILED is fine (no valid user yet); other
        # event types MUST carry both user_id and org_id or the
        # SOC2 attribution claim is hollow.
        if event_type in _REQUIRES_ATTRIBUTION:
            if not user_id or not user_id.strip():
                raise SecurityAuditLogError(
                    f"event_type {event_type.value!r} requires "
                    f"user_id attribution; got {user_id!r}"
                )
            if not org_id or not org_id.strip():
                raise SecurityAuditLogError(
                    f"event_type {event_type.value!r} requires "
                    f"org_id attribution; got {org_id!r}"
                )

        try:
            details_json = json.dumps(details or {}, sort_keys=True)
        except (TypeError, ValueError):
            details_json = json.dumps(
                {"raw": str(details)}, sort_keys=True,
            )

        event_id = f"sec_{uuid.uuid4().hex[:16]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO security_events (event_id, event_type, "
                "severity, user_id, org_id, source_ip, user_agent, "
                "request_method, request_path, details_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id, event_type.value, severity.value,
                    user_id, org_id, source_ip, user_agent,
                    request_method, request_path, details_json, now,
                ),
            )
        return SecurityEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            org_id=org_id,
            source_ip=source_ip,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            details_json=details_json,
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_events(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        severity: EventSeverity | None = None,
        event_type: SecurityEventType | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 1000,
    ) -> list[SecurityEvent]:
        """Query the log with optional filters.

        At least one of {org_id, user_id} should be passed for the
        SOC2 "tell me events for tenant X" use case. Unconditional
        queries (no org_id, no user_id) are allowed for platform-
        admin paths, but the caller is responsible for gating that
        privilege.
        """
        if limit < 1 or limit > 10000:
            raise SecurityAuditLogError(
                f"limit must be in [1, 10000]; got {limit}"
            )
        clauses: list[str] = []
        params: list[Any] = []
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity.value)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if until is not None:
            clauses.append("created_at <= ?")
            params.append(until)

        sql = "SELECT * FROM security_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_event(self, event_id: str) -> SecurityEvent | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM security_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return _row_to_event(row) if row is not None else None


# ---------------------------------------------------------------------------
# Row → object converter
# ---------------------------------------------------------------------------


def _row_to_event(row: sqlite3.Row) -> SecurityEvent:
    return SecurityEvent(
        event_id=row["event_id"],
        event_type=SecurityEventType(row["event_type"]),
        severity=EventSeverity(row["severity"]),
        user_id=row["user_id"],
        org_id=row["org_id"],
        source_ip=row["source_ip"],
        user_agent=row["user_agent"],
        request_method=row["request_method"],
        request_path=row["request_path"],
        details_json=row["details_json"] or "{}",
        created_at=float(row["created_at"]),
    )
