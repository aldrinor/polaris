"""Customer support flow (M-24 — Phase C).

Per FINAL_PLAN Phase C deliverable #10:
  Customer support flow.

Minimum viable customer-support surface: a ticket queue scoped
to org_id with status transitions (OPEN → IN_PROGRESS → RESOLVED
or → CLOSED), category metadata so support staff can route, and
back-link fields so a ticket can reference a specific
audit-run / review / workspace.

Scope of v1:
  - Ticket creation by any authenticated org member (the user
    facing the issue).
  - Status transitions by support_agent role only.
  - Append-only message thread (no edits, no deletions of past
    messages — supports the SOC2 audit-log claim around customer
    interactions).
  - Org-scoped reads + writes; cross-tenant access surfaces 403.

Out of scope for v1:
  - Email integration / SLA timers / auto-escalation.
  - Slack / PagerDuty hooks.
  - Knowledge-base search.

LAW VII compliance: stdlib + audit_ir/loader. The endpoint that
wires this in is added separately.
"""

from __future__ import annotations

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


class TicketStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketCategory(Enum):
    """Closed enum so support staff can filter the queue.

    BILLING covers plan / quota / invoice questions.
    AUDIT covers V30-pipeline issues (broken refs, missing
      contradictions, etc.).
    INTEGRATION covers SSO / API key / webhook configuration.
    DATA_REQUEST covers GDPR / SOC2 / data-export requests.
    OTHER is the fallback.
    """

    BILLING = "billing"
    AUDIT = "audit"
    INTEGRATION = "integration"
    DATA_REQUEST = "data_request"
    OTHER = "other"


class TicketPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


_TERMINAL_STATES: frozenset[TicketStatus] = frozenset({
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SupportTicketError(Exception):
    """Base error for support-ticket operations."""


class SupportTicketStateError(SupportTicketError):
    """Invalid input or state transition."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupportTicket:
    """One customer-support ticket.

    Optional `related_*` back-links let a ticket reference an
    audit-run / review / workspace so support staff have direct
    inspection paths.
    """

    ticket_id: str
    org_id: str
    submitter_user_id: str
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    assigned_to: str | None
    related_run_slug: str | None
    related_review_id: str | None
    related_workspace_id: str | None
    created_at: float
    updated_at: float
    resolved_at: float | None


@dataclass(frozen=True)
class SupportMessage:
    """Append-only thread message on a ticket."""

    message_id: str
    ticket_id: str
    author_user_id: str
    body: str
    created_at: float


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    submitter_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    assigned_to TEXT,
    related_run_slug TEXT,
    related_review_id TEXT,
    related_workspace_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    resolved_at REAL
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_org_status
    ON support_tickets(org_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_support_tickets_assignee
    ON support_tickets(assigned_to, status);

CREATE TABLE IF NOT EXISTS support_messages (
    message_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_support_messages_ticket_created
    ON support_messages(ticket_id, created_at);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SupportTicketStore:
    """SQLite-backed support-ticket queue.

    Per-call connections (matches the rest of the audit_ir
    pattern). WAL mode + foreign keys + BEGIN IMMEDIATE on
    transitions.
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
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def open_ticket(
        self,
        *,
        org_id: str,
        submitter_user_id: str,
        title: str,
        description: str,
        category: TicketCategory,
        priority: TicketPriority = TicketPriority.NORMAL,
        related_run_slug: str | None = None,
        related_review_id: str | None = None,
        related_workspace_id: str | None = None,
    ) -> SupportTicket:
        """Open a new ticket. The body of `description` may grow
        via append_message later; this call is for the initial
        problem statement."""
        if not org_id.strip():
            raise SupportTicketStateError("org_id must be non-empty")
        if not submitter_user_id.strip():
            raise SupportTicketStateError(
                "submitter_user_id must be non-empty"
            )
        if not title.strip():
            raise SupportTicketStateError("title must be non-empty")
        if not description.strip():
            raise SupportTicketStateError(
                "description must be non-empty so support has "
                "context to triage"
            )
        if not isinstance(category, TicketCategory):
            raise SupportTicketStateError(
                f"category must be TicketCategory, got {category!r}"
            )
        if not isinstance(priority, TicketPriority):
            raise SupportTicketStateError(
                f"priority must be TicketPriority, got {priority!r}"
            )
        ticket_id = f"sup_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO support_tickets (ticket_id, org_id, "
                "submitter_user_id, title, description, category, "
                "priority, status, related_run_slug, related_review_id, "
                "related_workspace_id, created_at, updated_at) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id, org_id.strip(), submitter_user_id.strip(),
                    title.strip(), description.strip(),
                    category.value, priority.value,
                    TicketStatus.OPEN.value,
                    related_run_slug, related_review_id,
                    related_workspace_id, now, now,
                ),
            )
        return SupportTicket(
            ticket_id=ticket_id, org_id=org_id.strip(),
            submitter_user_id=submitter_user_id.strip(),
            title=title.strip(), description=description.strip(),
            category=category, priority=priority,
            status=TicketStatus.OPEN, assigned_to=None,
            related_run_slug=related_run_slug,
            related_review_id=related_review_id,
            related_workspace_id=related_workspace_id,
            created_at=now, updated_at=now, resolved_at=None,
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def assign(
        self, *, ticket_id: str, org_id: str,
        agent_user_id: str,
    ) -> SupportTicket:
        """Assign a ticket to a support agent. Transitions OPEN →
        IN_PROGRESS. Already-IN_PROGRESS tickets can be reassigned
        to a different agent without re-transitioning."""
        return self._mutate(
            ticket_id=ticket_id, org_id=org_id,
            agent_user_id=agent_user_id,
            allowed_from=(
                TicketStatus.OPEN, TicketStatus.IN_PROGRESS,
            ),
            new_status=TicketStatus.IN_PROGRESS,
            assign_to=agent_user_id,
        )

    def resolve(
        self, *, ticket_id: str, org_id: str,
        agent_user_id: str,
    ) -> SupportTicket:
        """Mark a ticket resolved. Terminal state.

        Codex M-24 v1 review fix: resolve() requires IN_PROGRESS,
        NOT OPEN. v1 allowed OPEN -> RESOLVED which bypassed the
        assign() step and left `assigned_to=None`.

        Codex M-24 v2 review fix: resolve() ALSO requires
        assigned_to to be non-None. Without this, the bypass
        OPEN -> close() -> reopen() -> resolve() still produced
        a RESOLVED ticket with assigned_to=None (because reopen()
        doesn't re-assign and resolve() only checked status).
        v3 makes resolve() self-validate the assignee invariant.
        Operators wanting to close-without-assigning use close()
        instead, which permits OPEN as a from-state for won't-fix /
        duplicate scenarios.
        """
        return self._mutate(
            ticket_id=ticket_id, org_id=org_id,
            agent_user_id=agent_user_id,
            allowed_from=(TicketStatus.IN_PROGRESS,),
            new_status=TicketStatus.RESOLVED,
            mark_resolved=True,
            require_assignee=True,
        )

    def close(
        self, *, ticket_id: str, org_id: str,
        agent_user_id: str,
    ) -> SupportTicket:
        """Close a ticket. Either resolved-and-closed (final) or
        won't-fix / duplicate-style closures."""
        return self._mutate(
            ticket_id=ticket_id, org_id=org_id,
            agent_user_id=agent_user_id,
            allowed_from=(
                TicketStatus.OPEN, TicketStatus.IN_PROGRESS,
                TicketStatus.RESOLVED,
            ),
            new_status=TicketStatus.CLOSED,
            mark_resolved=True,
        )

    def reopen(
        self, *, ticket_id: str, org_id: str,
        agent_user_id: str,
    ) -> SupportTicket:
        """Re-open a RESOLVED or CLOSED ticket. Transitions back
        to IN_PROGRESS so the agent can keep working it."""
        return self._mutate(
            ticket_id=ticket_id, org_id=org_id,
            agent_user_id=agent_user_id,
            allowed_from=(
                TicketStatus.RESOLVED, TicketStatus.CLOSED,
            ),
            new_status=TicketStatus.IN_PROGRESS,
            clear_resolved=True,
        )

    def _mutate(
        self,
        *,
        ticket_id: str,
        org_id: str,
        agent_user_id: str,
        allowed_from: tuple[TicketStatus, ...],
        new_status: TicketStatus,
        assign_to: str | None = None,
        mark_resolved: bool = False,
        clear_resolved: bool = False,
        require_assignee: bool = False,
    ) -> SupportTicket:
        if not agent_user_id.strip():
            raise SupportTicketStateError(
                "agent_user_id must be non-empty"
            )
        from_values = tuple(s.value for s in allowed_from)
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM support_tickets WHERE ticket_id = ?",
                    (ticket_id,),
                ).fetchone()
                if row is None:
                    raise SupportTicketStateError(
                        f"ticket {ticket_id!r} not found"
                    )
                if row["org_id"] != org_id:
                    # Same posture as review_store: don't pretend
                    # the ticket doesn't exist; the router converts
                    # this to 403.
                    raise SupportTicketStateError(
                        f"ticket {ticket_id!r} belongs to a "
                        f"different org"
                    )
                current = TicketStatus(row["status"])
                if current not in allowed_from:
                    raise SupportTicketStateError(
                        f"ticket {ticket_id!r} is in state "
                        f"{current.value!r}; expected one of "
                        f"{from_values} to transition to "
                        f"{new_status.value!r}"
                    )
                # Codex M-24 v2 review fix: resolve() must verify
                # the ticket has an assignee. Catches the
                # OPEN -> close() -> reopen() -> resolve() backdoor
                # where reopen() restores IN_PROGRESS without
                # re-assigning.
                if require_assignee and not row["assigned_to"]:
                    raise SupportTicketStateError(
                        f"ticket {ticket_id!r} has no assignee; "
                        f"cannot transition to {new_status.value!r} "
                        f"without an assignee — call assign() first"
                    )

                set_parts = ["status = ?", "updated_at = ?"]
                params: list[Any] = [new_status.value, now]
                if assign_to is not None:
                    set_parts.append("assigned_to = ?")
                    params.append(assign_to.strip())
                if mark_resolved:
                    set_parts.append("resolved_at = ?")
                    params.append(now)
                if clear_resolved:
                    set_parts.append("resolved_at = NULL")
                params.append(ticket_id)
                conn.execute(
                    f"UPDATE support_tickets SET {', '.join(set_parts)} "
                    f"WHERE ticket_id = ?",
                    params,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        ticket = self.get_ticket(ticket_id=ticket_id, org_id=org_id)
        if ticket is None:  # defensive
            raise SupportTicketError(
                f"transitioned ticket {ticket_id!r} but cannot read it back"
            )
        return ticket

    # ------------------------------------------------------------------
    # Messages (append-only thread)
    # ------------------------------------------------------------------

    def append_message(
        self,
        *,
        ticket_id: str,
        org_id: str,
        author_user_id: str,
        body: str,
    ) -> SupportMessage:
        """Append a message to the ticket thread. Cross-org
        access raises so a foreign tenant cannot inject messages
        into another org's tickets."""
        if not author_user_id.strip():
            raise SupportTicketStateError(
                "author_user_id must be non-empty"
            )
        if not body.strip():
            raise SupportTicketStateError(
                "body must be non-empty"
            )
        # Verify the ticket exists in this org first.
        ticket = self.get_ticket(ticket_id=ticket_id, org_id=org_id)
        if ticket is None:
            raise SupportTicketStateError(
                f"ticket {ticket_id!r} is not accessible to this caller"
            )
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO support_messages (message_id, "
                "ticket_id, author_user_id, body, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    message_id, ticket_id, author_user_id.strip(),
                    body.strip(), now,
                ),
            )
            # Bump the ticket's updated_at so the queue surfaces
            # the most-recently-active tickets first.
            conn.execute(
                "UPDATE support_tickets SET updated_at = ? "
                "WHERE ticket_id = ?",
                (now, ticket_id),
            )
        return SupportMessage(
            message_id=message_id, ticket_id=ticket_id,
            author_user_id=author_user_id.strip(),
            body=body.strip(), created_at=now,
        )

    def list_messages(
        self, *, ticket_id: str, org_id: str,
    ) -> list[SupportMessage]:
        """Read the full thread for a ticket, oldest-first. Empty
        list if the ticket doesn't belong to org_id (no existence
        leak — same as review_store.list_transitions)."""
        ticket = self.get_ticket(ticket_id=ticket_id, org_id=org_id)
        if ticket is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM support_messages WHERE ticket_id = ? "
                "ORDER BY created_at ASC",
                (ticket_id,),
            ).fetchall()
        return [
            SupportMessage(
                message_id=r["message_id"],
                ticket_id=r["ticket_id"],
                author_user_id=r["author_user_id"],
                body=r["body"],
                created_at=float(r["created_at"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def get_ticket(
        self, *, ticket_id: str, org_id: str,
    ) -> SupportTicket | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM support_tickets "
                "WHERE ticket_id = ? AND org_id = ?",
                (ticket_id, org_id),
            ).fetchone()
        if row is None:
            return None
        return _row_to_ticket(row)

    def list_by_org(
        self,
        *,
        org_id: str,
        status: TicketStatus | None = None,
        category: TicketCategory | None = None,
        assigned_to: str | None = None,
    ) -> list[SupportTicket]:
        clauses = ["org_id = ?"]
        params: list[Any] = [org_id]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if category is not None:
            clauses.append("category = ?")
            params.append(category.value)
        if assigned_to is not None:
            clauses.append("assigned_to = ?")
            params.append(assigned_to)
        sql = (
            f"SELECT * FROM support_tickets WHERE "
            f"{' AND '.join(clauses)} ORDER BY updated_at DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_ticket(r) for r in rows]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def ticket_to_dict(t: SupportTicket) -> dict[str, Any]:
    return {
        "ticket_id": t.ticket_id,
        "org_id": t.org_id,
        "submitter_user_id": t.submitter_user_id,
        "title": t.title,
        "description": t.description,
        "category": t.category.value,
        "priority": t.priority.value,
        "status": t.status.value,
        "assigned_to": t.assigned_to,
        "related_run_slug": t.related_run_slug,
        "related_review_id": t.related_review_id,
        "related_workspace_id": t.related_workspace_id,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "resolved_at": t.resolved_at,
    }


def message_to_dict(m: SupportMessage) -> dict[str, Any]:
    return {
        "message_id": m.message_id,
        "ticket_id": m.ticket_id,
        "author_user_id": m.author_user_id,
        "body": m.body,
        "created_at": m.created_at,
    }


# ---------------------------------------------------------------------------
# Row → object converter
# ---------------------------------------------------------------------------


def _row_to_ticket(row: sqlite3.Row) -> SupportTicket:
    return SupportTicket(
        ticket_id=row["ticket_id"],
        org_id=row["org_id"],
        submitter_user_id=row["submitter_user_id"],
        title=row["title"],
        description=row["description"],
        category=TicketCategory(row["category"]),
        priority=TicketPriority(row["priority"]),
        status=TicketStatus(row["status"]),
        assigned_to=row["assigned_to"],
        related_run_slug=row["related_run_slug"],
        related_review_id=row["related_review_id"],
        related_workspace_id=row["related_workspace_id"],
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        resolved_at=(
            float(row["resolved_at"]) if row["resolved_at"] is not None
            else None
        ),
    )
