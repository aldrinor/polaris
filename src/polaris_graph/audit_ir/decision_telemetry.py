"""M-D3 (Phase D): Induction → operator-review telemetry — bootstrap.

Per FINAL_PLAN M-D3 + Phase D milestones plan: record every
contract induction and (per advisor watch-out) every scope-gate
decision, paired with the curator's action when it ships through
M-23 review queue. The data substrate is the **calibration input
for M-D4** (auto-trust gate), which is calendar-blocked on ≥6
months of M-D3 telemetry.

Phase 1 ships **telemetry substrate only**. Trust-gate logic is
deferred to M-D4. Recorded confidences are uncalibrated by
design — calibration is precisely what M-D4 will use this data
for. Anyone using M-D3 telemetry to gate live audits before
M-D4 ships is misusing the substrate.

## Why a generic DecisionKind discriminator

Per advisor: `M-D3 sits under M-D2 inductor, but M-D5 also sits
under M-D20 router with classifier above. Two ways to handle:
(a) generic enough record shape from v1 (preferred — decision_kind
discriminator), or (b) document explicitly that M-D3 phase 1
records only induction decisions and scope-gate decisions are
M-D3 phase 2.`

Option (a) — `decision_kind: DecisionKind = induction | scope_gate`
adds one column and avoids a forced phase 2 just to add scope-
gate fields when M-D5 phase 2 ships.

## Coupling to M-21 / M-23

Same SQLite per-workspace substrate as M-21 / M-D7 / M-D10.
One extra `decision_records` table. The M-23 review queue closes
contract reviews; when that happens, callers update the matching
`DecisionRecord.curator_action` via `update_curator_action()`.
M-D3 does NOT re-implement the queue; it records what happens
*after* the queue closes.

## What's in the record

For both induction and scope_gate kinds:
  - `proposed_payload`: what the system suggested (contract dict
    for induction; GatedMatchResult action+template_id+rationale
    for scope_gate)
  - `proposed_confidence`: classifier/inductor self-reported
    confidence in [0, 1]
  - `curator_action`: accepted_as_proposed / modified / overridden
    / rejected / pending
  - `final_payload`: what shipped (or None if pending/rejected)
  - `diff_payload`: structural diff between proposed + final (None
    when curator_action == accepted_as_proposed)
  - `actor_user_id`: who made the curator decision (None for
    pending; required for non-pending actions)
  - `notes`: curator's free-text rationale

## What's NOT in phase 1

- Trust-gate logic ("if this template_class has ≥95% acceptance
  rate over 6mo, auto-confirm"). That's M-D4.
- Live calibration of inductor/classifier confidence. Phase 1
  records uncalibrated values; calibration is M-D4's job.
- Cross-workspace aggregation. Each workspace has its own DB
  file; aggregation queries are deferred to M-D4 / M-D13.
- Real-time alerts on drift. M-D10 covers freshness alerts;
  decision-drift alerts are M-D4 territory.
- Notification callbacks (email curator when their review queue
  has waiting items). M-23 ships its own notifications; M-D3
  is record-only.

See `docs/md3_phase1_threat_model.md` for the full boundary set.
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
# Errors
# ---------------------------------------------------------------------------


class DecisionTelemetryError(Exception):
    """Raised on schema/state violations."""


class DecisionTelemetryStateError(DecisionTelemetryError):
    """Raised when an invalid state transition is attempted (e.g. updating
    a non-existent record, or moving from a terminal action)."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DecisionKind(str, Enum):
    """Closed taxonomy of decision sources.

    Generic discriminator (advisor watch-out): `M-D3 records
    induction decisions today; M-D5's gate decisions land here too
    once phase 2 of M-D5 ships a concrete classifier. Generic
    record shape avoids a forced phase 2 to add scope-gate columns.`
    """

    INDUCTION = "induction"
    SCOPE_GATE = "scope_gate"


class CuratorAction(str, Enum):
    """What a human curator did with the system's proposal.

    `pending` is the initial state on `record_decision`. Once a
    curator transitions through M-23, callers update via
    `update_curator_action()` to one of the four terminal states.

    Terminal states (no further transitions allowed):
      - `accepted_as_proposed`: curator shipped exactly what the
        system suggested. No diff.
      - `modified`: curator shipped a modified version. `diff_payload`
        captures the change.
      - `overridden`: curator chose a different decision entirely
        (e.g. system suggested ROUTE, curator forced REJECT via
        the operator-override path).
      - `rejected`: curator rejected the run entirely; nothing
        shipped to the user.
    """

    PENDING = "pending"
    ACCEPTED_AS_PROPOSED = "accepted_as_proposed"
    MODIFIED = "modified"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"


_TERMINAL_ACTIONS: frozenset[CuratorAction] = frozenset({
    CuratorAction.ACCEPTED_AS_PROPOSED,
    CuratorAction.MODIFIED,
    CuratorAction.OVERRIDDEN,
    CuratorAction.REJECTED,
})


def _validate_terminal_args(
    curator_action: CuratorAction,
    actor_user_id: str,
    final_payload: dict[str, Any] | None,
    diff_payload: dict[str, Any] | None,
) -> None:
    """Codex round-1 MED fix (v2): centralized cross-action invariant
    enforcement, called by update_curator_action() before any DB
    mutation. Every terminal-action invariant lives here so the
    contract is auditable in one place.

    Invariants enforced:
      - curator_action MUST be a CuratorAction enum value (not a string)
      - curator_action MUST NOT be PENDING (this is a transition to
        terminal, not a re-entry)
      - actor_user_id MUST be non-empty for any terminal action
      - REJECTED: final_payload + diff_payload MUST both be None
      - ACCEPTED_AS_PROPOSED: final_payload required (= proposed),
        diff_payload MUST be None
      - MODIFIED / OVERRIDDEN: final_payload required, diff_payload
        is optional but expected
    """
    if not isinstance(curator_action, CuratorAction):
        raise DecisionTelemetryError(
            f"curator_action must be CuratorAction, got "
            f"{type(curator_action).__name__}"
        )
    if curator_action == CuratorAction.PENDING:
        raise DecisionTelemetryError(
            "update_curator_action cannot transition to PENDING"
        )
    if not actor_user_id:
        raise DecisionTelemetryError(
            "actor_user_id required for terminal curator actions"
        )
    if curator_action == CuratorAction.REJECTED:
        if final_payload is not None:
            raise DecisionTelemetryError(
                "final_payload must be None for rejected action"
            )
        if diff_payload is not None:
            raise DecisionTelemetryError(
                "diff_payload must be None for rejected action"
            )
        return
    if curator_action == CuratorAction.ACCEPTED_AS_PROPOSED:
        if diff_payload is not None:
            raise DecisionTelemetryError(
                "diff_payload must be None for accepted_as_proposed "
                "(no diff exists when curator accepts as-is)"
            )
        if final_payload is None:
            raise DecisionTelemetryError(
                "final_payload required for accepted_as_proposed; "
                "should equal proposed_payload"
            )
        return
    # MODIFIED or OVERRIDDEN
    if final_payload is None:
        raise DecisionTelemetryError(
            f"final_payload required for {curator_action.value}"
        )


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionRecord:
    """One induction or scope-gate decision.

    `proposed_payload` is JSON-serializable and represents whatever
    the system suggested:
      - induction kind: induced contract dict
      - scope_gate kind: GatedMatchResult-shaped dict
        (action + template_id + threshold + rationale + ...)

    `proposed_confidence` is in [0, 1] — uncalibrated. See
    threat-model boundary 2.

    `final_payload` is None until the curator transitions to a
    terminal action. For `accepted_as_proposed`, equals
    `proposed_payload`. For `modified` / `overridden`, captures
    what shipped. For `rejected`, equals None (nothing shipped).

    `diff_payload` is None when no diff applies (pending,
    accepted_as_proposed, rejected). For `modified` / `overridden`,
    a JSON dict capturing the structural delta the curator made.
    """

    record_id: str
    workspace_id: str
    decision_kind: DecisionKind
    query: str
    proposed_payload: dict[str, Any]
    proposed_confidence: float
    curator_action: CuratorAction
    final_payload: dict[str, Any] | None
    diff_payload: dict[str, Any] | None
    actor_user_id: str | None
    notes: str | None
    created_at: float
    decided_at: float | None


def decision_to_dict(record: DecisionRecord) -> dict[str, Any]:
    """JSON-safe dict for transport / logging."""
    return {
        "record_id": record.record_id,
        "workspace_id": record.workspace_id,
        "decision_kind": record.decision_kind.value,
        "query": record.query,
        "proposed_payload": record.proposed_payload,
        "proposed_confidence": record.proposed_confidence,
        "curator_action": record.curator_action.value,
        "final_payload": record.final_payload,
        "diff_payload": record.diff_payload,
        "actor_user_id": record.actor_user_id,
        "notes": record.notes,
        "created_at": record.created_at,
        "decided_at": record.decided_at,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_VALID_KINDS = ", ".join(f"'{k.value}'" for k in DecisionKind)
_VALID_ACTIONS = ", ".join(f"'{a.value}'" for a in CuratorAction)


_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS decision_records (
    record_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    decision_kind TEXT NOT NULL CHECK (decision_kind IN ({_VALID_KINDS})),
    query TEXT NOT NULL,
    proposed_payload_json TEXT NOT NULL,
    proposed_confidence REAL NOT NULL CHECK (
        proposed_confidence >= 0.0 AND proposed_confidence <= 1.0
    ),
    curator_action TEXT NOT NULL CHECK (curator_action IN ({_VALID_ACTIONS})),
    final_payload_json TEXT,
    diff_payload_json TEXT,
    actor_user_id TEXT,
    notes TEXT,
    created_at REAL NOT NULL,
    decided_at REAL
);

CREATE INDEX IF NOT EXISTS idx_decision_records_ws_kind
    ON decision_records(workspace_id, decision_kind);
CREATE INDEX IF NOT EXISTS idx_decision_records_ws_action
    ON decision_records(workspace_id, curator_action);
CREATE INDEX IF NOT EXISTS idx_decision_records_ws_created
    ON decision_records(workspace_id, created_at);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class DecisionRecordStore:
    """Per-workspace SQLite-backed decision telemetry store.

    Same per-call WAL-connection pattern as M-21 / M-D7 / M-D10 —
    each public method opens its own connection, executes its
    transaction, and closes. Avoids cross-thread connection sharing
    issues.

    Schema is idempotent; multiple `__init__` calls on the same
    `db_path` are safe. The schema also coexists with M-21
    workspace memory + M-D7 retrieval cache + M-D10 freshness
    alerts in the same file (different table names; no FK cross-
    references).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._db_path),
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    def record_decision(
        self,
        *,
        workspace_id: str,
        decision_kind: DecisionKind,
        query: str,
        proposed_payload: dict[str, Any],
        proposed_confidence: float,
        clock: float | None = None,
    ) -> DecisionRecord:
        """Record a fresh decision in PENDING state.

        Args:
          workspace_id: scope tenancy.
          decision_kind: induction | scope_gate.
          query: free-text user query.
          proposed_payload: JSON-serializable system proposal.
          proposed_confidence: in [0, 1].
          clock: optional override for tests.

        Returns:
          The newly-recorded DecisionRecord (curator_action=PENDING,
          decided_at=None, final_payload=None, diff_payload=None).

        Raises:
          DecisionTelemetryError: invalid confidence, unserializable
          payload, or empty workspace_id / query.
        """
        if not workspace_id:
            raise DecisionTelemetryError("workspace_id must be non-empty")
        if not query:
            raise DecisionTelemetryError("query must be non-empty")
        if not isinstance(decision_kind, DecisionKind):
            raise DecisionTelemetryError(
                f"decision_kind must be DecisionKind, got "
                f"{type(decision_kind).__name__}"
            )
        if not 0.0 <= proposed_confidence <= 1.0:
            raise DecisionTelemetryError(
                f"proposed_confidence {proposed_confidence} outside [0, 1]"
            )
        try:
            payload_json = json.dumps(proposed_payload, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise DecisionTelemetryError(
                f"proposed_payload not JSON-serializable: {exc}"
            ) from exc

        record_id = str(uuid.uuid4())
        now = clock if clock is not None else time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO decision_records (
                    record_id, workspace_id, decision_kind, query,
                    proposed_payload_json, proposed_confidence,
                    curator_action, final_payload_json, diff_payload_json,
                    actor_user_id, notes, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL)
                """,
                (
                    record_id,
                    workspace_id,
                    decision_kind.value,
                    query,
                    payload_json,
                    proposed_confidence,
                    CuratorAction.PENDING.value,
                    now,
                ),
            )
        finally:
            conn.close()

        return DecisionRecord(
            record_id=record_id,
            workspace_id=workspace_id,
            decision_kind=decision_kind,
            query=query,
            proposed_payload=proposed_payload,
            proposed_confidence=proposed_confidence,
            curator_action=CuratorAction.PENDING,
            final_payload=None,
            diff_payload=None,
            actor_user_id=None,
            notes=None,
            created_at=now,
            decided_at=None,
        )

    def update_curator_action(
        self,
        record_id: str,
        *,
        workspace_id: str,
        curator_action: CuratorAction,
        actor_user_id: str,
        final_payload: dict[str, Any] | None = None,
        diff_payload: dict[str, Any] | None = None,
        notes: str | None = None,
        clock: float | None = None,
    ) -> DecisionRecord:
        """Transition a PENDING record to a terminal curator action.

        Args:
          record_id: record to update.
          workspace_id: scoping field. v2: required, matched against
            the row's stored workspace_id. Raises
            DecisionTelemetryStateError if (record_id, workspace_id)
            does not exist — protecting against cross-workspace
            transitions even if a caller knows another workspace's
            record_id.
          curator_action: terminal action (NOT pending).
          actor_user_id: required for terminal actions.
          final_payload: required for accepted_as_proposed / modified /
            overridden; must be None for rejected.
          diff_payload: optional structural diff. Must be None for
            accepted_as_proposed and rejected; expected for
            modified / overridden.
          notes: optional curator rationale.
          clock: optional override for tests.

        Raises:
          DecisionTelemetryStateError: record not found in workspace,
            already terminal, invalid transition.
          DecisionTelemetryError: validation failure on
            curator_action / final_payload / diff_payload (see
            _validate_terminal_args).
        """
        if not workspace_id:
            raise DecisionTelemetryError("workspace_id must be non-empty")
        # All cross-action invariants centralized in
        # _validate_terminal_args (Codex round-1 MED fix v2).
        _validate_terminal_args(
            curator_action, actor_user_id, final_payload, diff_payload,
        )

        try:
            final_json = (
                json.dumps(final_payload, sort_keys=True)
                if final_payload is not None
                else None
            )
            diff_json = (
                json.dumps(diff_payload, sort_keys=True)
                if diff_payload is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise DecisionTelemetryError(
                f"payload not JSON-serializable: {exc}"
            ) from exc

        now = clock if clock is not None else time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT curator_action FROM decision_records
                 WHERE record_id = ? AND workspace_id = ?
                """,
                (record_id, workspace_id),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise DecisionTelemetryStateError(
                    f"record_id {record_id!r} not found in workspace "
                    f"{workspace_id!r}"
                )
            existing_action = CuratorAction(row["curator_action"])
            if existing_action in _TERMINAL_ACTIONS:
                conn.execute("ROLLBACK")
                raise DecisionTelemetryStateError(
                    f"record_id {record_id!r} already terminal "
                    f"({existing_action.value}); transitions are "
                    f"forbidden — record a new decision instead"
                )
            conn.execute(
                """
                UPDATE decision_records
                   SET curator_action = ?,
                       actor_user_id = ?,
                       final_payload_json = ?,
                       diff_payload_json = ?,
                       notes = ?,
                       decided_at = ?
                 WHERE record_id = ? AND workspace_id = ?
                """,
                (
                    curator_action.value,
                    actor_user_id,
                    final_json,
                    diff_json,
                    notes,
                    now,
                    record_id,
                    workspace_id,
                ),
            )
            conn.execute("COMMIT")
        except DecisionTelemetryError:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        return self._must_get(record_id, workspace_id)

    def get(
        self, record_id: str, *, workspace_id: str,
    ) -> DecisionRecord | None:
        """Fetch a record by id within the given workspace.

        Codex round-1 MED fix (v2): `workspace_id` is required and
        the query filters on both columns. Without this, a caller
        with a record_id from another workspace could read across
        workspace boundaries — even though record_id is a UUID4,
        the M-D7 / M-D10 pattern is to require workspace_id
        explicitly so cross-workspace access is never possible
        through the public API.

        Returns None if no record matches `(record_id, workspace_id)`.
        Raises DecisionTelemetryError on empty workspace_id.
        """
        if not workspace_id:
            raise DecisionTelemetryError("workspace_id must be non-empty")
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM decision_records
                 WHERE record_id = ? AND workspace_id = ?
                """,
                (record_id, workspace_id),
            ).fetchone()
            return _row_to_record(row) if row is not None else None
        finally:
            conn.close()

    def _must_get(
        self, record_id: str, workspace_id: str,
    ) -> DecisionRecord:
        record = self.get(record_id, workspace_id=workspace_id)
        if record is None:
            raise DecisionTelemetryStateError(
                f"record_id {record_id!r} not found post-update "
                f"(workspace {workspace_id!r})"
            )
        return record

    def list_for_workspace(
        self,
        workspace_id: str,
        *,
        decision_kind: DecisionKind | None = None,
        curator_action: CuratorAction | None = None,
        limit: int | None = None,
    ) -> list[DecisionRecord]:
        """List records for a workspace, optionally filtered.

        Records returned ordered by `created_at DESC` (most recent first).
        `limit` caps the result count.
        """
        if not workspace_id:
            raise DecisionTelemetryError("workspace_id must be non-empty")
        clauses = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        if decision_kind is not None:
            clauses.append("decision_kind = ?")
            params.append(decision_kind.value)
        if curator_action is not None:
            clauses.append("curator_action = ?")
            params.append(curator_action.value)
        sql = (
            "SELECT * FROM decision_records "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC"
        )
        if limit is not None:
            if limit < 0:
                raise DecisionTelemetryError("limit must be non-negative")
            sql += f" LIMIT {int(limit)}"

        conn = self._connect()
        try:
            return [
                _row_to_record(row)
                for row in conn.execute(sql, params).fetchall()
            ]
        finally:
            conn.close()

    def count_for_workspace(
        self,
        workspace_id: str,
        *,
        decision_kind: DecisionKind | None = None,
        curator_action: CuratorAction | None = None,
    ) -> int:
        """Count matching records — cheap aggregate without
        materializing the full list. Useful for M-D4 calibration
        queries (e.g. 'how many accepted_as_proposed inductions for
        this workspace over the last 6mo')."""
        if not workspace_id:
            raise DecisionTelemetryError("workspace_id must be non-empty")
        clauses = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        if decision_kind is not None:
            clauses.append("decision_kind = ?")
            params.append(decision_kind.value)
        if curator_action is not None:
            clauses.append("curator_action = ?")
            params.append(curator_action.value)
        sql = (
            f"SELECT COUNT(*) AS c FROM decision_records "
            f"WHERE {' AND '.join(clauses)}"
        )
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return int(row["c"])
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> DecisionRecord:
    proposed = json.loads(row["proposed_payload_json"])
    final_raw = row["final_payload_json"]
    final = json.loads(final_raw) if final_raw is not None else None
    diff_raw = row["diff_payload_json"]
    diff = json.loads(diff_raw) if diff_raw is not None else None
    return DecisionRecord(
        record_id=row["record_id"],
        workspace_id=row["workspace_id"],
        decision_kind=DecisionKind(row["decision_kind"]),
        query=row["query"],
        proposed_payload=proposed,
        proposed_confidence=float(row["proposed_confidence"]),
        curator_action=CuratorAction(row["curator_action"]),
        final_payload=final,
        diff_payload=diff,
        actor_user_id=row["actor_user_id"],
        notes=row["notes"],
        created_at=float(row["created_at"]),
        decided_at=(
            float(row["decided_at"]) if row["decided_at"] is not None else None
        ),
    )


__all__ = [
    "CuratorAction",
    "DecisionKind",
    "DecisionRecord",
    "DecisionRecordStore",
    "DecisionTelemetryError",
    "DecisionTelemetryStateError",
    "decision_to_dict",
]
