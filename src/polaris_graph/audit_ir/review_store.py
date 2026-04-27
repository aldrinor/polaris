"""Review queue store (M-23 — Phase C).

SQLite-backed registry for human-review items over completed audit
runs. Mirrors the WorkspaceStore + JobQueue pattern (per-call
connections, WAL mode, BEGIN IMMEDIATE for state transitions).

Per FINAL_PLAN Phase C deliverable #8:
  Human review queue with annotation + approval + version diff
  for each run.

Lifecycle state machine:

    PENDING ──claim()──▶ IN_REVIEW ──approve()────▶ APPROVED
                              │ ──reject()─────▶ REJECTED
                              └ ──request_changes()─▶ NEEDS_CHANGES

NEEDS_CHANGES does NOT loop back into PENDING for the same review.
A new audit run produces a new ReviewItem at version=N+1, linked
to the prior via `prior_review_id`. The diff between consecutive
versions is computed by re-using M-16's `diff_runs`.

LAW VII compliance: this module imports only from `loader` and
`auth_store` (and stdlib). No reach-back into runner or generator
code. The endpoint that wires the store into FastAPI lives in
`inspector_router.py` and pulls the auth dependencies from
`auth_middleware`.
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
# Enumerations + data classes
# ---------------------------------------------------------------------------


class ReviewStatus(Enum):
    """Lifecycle states for a ReviewItem.

    Stable string values so external consumers (UI, audit trail)
    can compare without importing the enum.
    """

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


# Terminal states — once a ReviewItem reaches one of these, it
# cannot transition back. Re-review is a NEW item at version=N+1.
_TERMINAL_STATES: frozenset[ReviewStatus] = frozenset({
    ReviewStatus.APPROVED,
    ReviewStatus.REJECTED,
    ReviewStatus.NEEDS_CHANGES,
})


class ReviewStoreError(Exception):
    """Base error for review store operations."""


class ReviewStateError(ReviewStoreError):
    """An invalid state transition was attempted (e.g. approving a
    PENDING review instead of claiming first)."""


@dataclass(frozen=True)
class ReviewItem:
    """One audit-bundle review item.

    Cross-tenant isolation: `org_id` is the gating field — list +
    get endpoints filter on it; transition endpoints validate the
    caller's org_id matches before mutating.
    """

    review_id: str
    org_id: str
    run_slug: str
    run_id: str
    status: ReviewStatus
    assigned_to: str | None  # user_id (None until claimed)
    decided_by: str | None  # user_id (None until decided)
    notes: str | None
    version: int
    prior_review_id: str | None
    created_at: float
    updated_at: float
    decided_at: float | None


def review_to_dict(item: ReviewItem) -> dict[str, Any]:
    """Serialize a ReviewItem for JSON transport."""
    return {
        "review_id": item.review_id,
        "org_id": item.org_id,
        "run_slug": item.run_slug,
        "run_id": item.run_id,
        "status": item.status.value,
        "assigned_to": item.assigned_to,
        "decided_by": item.decided_by,
        "notes": item.notes,
        "version": item.version,
        "prior_review_id": item.prior_review_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "decided_at": item.decided_at,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    run_slug TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_to TEXT,
    decided_by TEXT,
    notes TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    prior_review_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    decided_at REAL,
    FOREIGN KEY (prior_review_id) REFERENCES reviews(review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_org_status
    ON reviews(org_id, status);
CREATE INDEX IF NOT EXISTS idx_reviews_run_slug
    ON reviews(org_id, run_slug, version);
CREATE INDEX IF NOT EXISTS idx_reviews_assigned
    ON reviews(org_id, assigned_to, status);

-- Append-only transition audit log. Every state change appends
-- one row so the customer-facing audit bundle can show "who
-- approved this and when" without reconstructing from updated_at.
CREATE TABLE IF NOT EXISTS review_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    notes TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (review_id) REFERENCES reviews(review_id)
);

CREATE INDEX IF NOT EXISTS idx_review_transitions_review
    ON review_transitions(review_id, created_at);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ReviewStore:
    """SQLite-backed review queue.

    Per-call connections (matches WorkspaceStore + JobQueue
    pattern). WAL journal mode for concurrent readers. Foreign
    keys enforced. Every mutating call uses BEGIN IMMEDIATE so
    racing claim() calls serialize.
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

    def enqueue(
        self,
        *,
        org_id: str,
        run_slug: str,
        run_id: str,
        prior_review_id: str | None = None,
    ) -> ReviewItem:
        """Enqueue a run for human review.

        If `prior_review_id` is provided, the new item's version =
        prior.version + 1 and prior.run_slug must match (a re-review
        of the same audit shape). The prior item must be in
        NEEDS_CHANGES — re-reviewing an APPROVED or REJECTED item
        is a workflow error.
        """
        if not org_id.strip() or not run_slug.strip() or not run_id.strip():
            raise ReviewStateError(
                "org_id, run_slug, and run_id must all be non-empty"
            )
        # Codex M-23 v1 review fix: do all prior_review_id
        # validation INSIDE the BEGIN IMMEDIATE so a cross-org
        # probe can't distinguish "does not exist" from "belongs
        # to different org" from "wrong state". A foreign caller
        # gets a single uniform 403-style error regardless of
        # which constraint fails.
        review_id = f"rev_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = 1
                prior_id: str | None = None
                if prior_review_id is not None:
                    row = conn.execute(
                        "SELECT * FROM reviews WHERE review_id = ? "
                        "AND org_id = ?",
                        (prior_review_id, org_id),
                    ).fetchone()
                    # Codex M-23 v1 fix: org-scoped lookup. An
                    # unknown OR cross-org prior_review_id surfaces
                    # the same generic error — no existence-leak
                    # probe is possible.
                    if row is None:
                        raise ReviewStateError(
                            f"prior_review_id {prior_review_id!r} is "
                            f"not accessible to this caller"
                        )
                    prior_status = ReviewStatus(row["status"])
                    if prior_status != ReviewStatus.NEEDS_CHANGES:
                        raise ReviewStateError(
                            f"cannot re-enqueue against prior review "
                            f"{prior_review_id!r} in state "
                            f"{prior_status.value!r}; only NEEDS_CHANGES "
                            f"priors may chain"
                        )
                    if row["run_slug"] != run_slug:
                        raise ReviewStateError(
                            f"prior review {prior_review_id!r} has "
                            f"run_slug {row['run_slug']!r}; new review "
                            f"run_slug must match (got {run_slug!r})"
                        )
                    # Codex M-23 v1 fix: enforce single-child chain.
                    # Without this, multiple v2 siblings can be
                    # enqueued against the same v1 prior, all with
                    # the same version number. Atomic check inside
                    # BEGIN IMMEDIATE so two racing enqueues serialize.
                    sibling = conn.execute(
                        "SELECT review_id FROM reviews WHERE "
                        "prior_review_id = ? AND org_id = ?",
                        (prior_review_id, org_id),
                    ).fetchone()
                    if sibling is not None:
                        raise ReviewStateError(
                            f"prior_review_id {prior_review_id!r} "
                            f"already has a chained review "
                            f"({sibling['review_id']!r}); a single "
                            f"prior may only chain to one child"
                        )
                    version = int(row["version"]) + 1
                    prior_id = prior_review_id

                conn.execute(
                    "INSERT INTO reviews (review_id, org_id, run_slug, "
                    "run_id, status, version, prior_review_id, "
                    "created_at, updated_at) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id, org_id.strip(), run_slug.strip(),
                        run_id.strip(), ReviewStatus.PENDING.value,
                        version, prior_id, now, now,
                    ),
                )
                conn.execute(
                    "INSERT INTO review_transitions "
                    "(review_id, from_status, to_status, "
                    "actor_user_id, notes, created_at) "
                    "VALUES (?, NULL, ?, ?, ?, ?)",
                    (
                        review_id, ReviewStatus.PENDING.value,
                        "system", "enqueued", now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return ReviewItem(
            review_id=review_id, org_id=org_id.strip(),
            run_slug=run_slug.strip(), run_id=run_id.strip(),
            status=ReviewStatus.PENDING,
            assigned_to=None, decided_by=None, notes=None,
            version=version, prior_review_id=prior_id,
            created_at=now, updated_at=now, decided_at=None,
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def claim(
        self, *, review_id: str, org_id: str, user_id: str,
    ) -> ReviewItem:
        """Claim a PENDING review; transition to IN_REVIEW."""
        return self._transition(
            review_id=review_id,
            org_id=org_id,
            user_id=user_id,
            from_states=(ReviewStatus.PENDING,),
            to_state=ReviewStatus.IN_REVIEW,
            assign_to_user=True,
        )

    def approve(
        self, *, review_id: str, org_id: str, user_id: str,
        notes: str | None = None,
    ) -> ReviewItem:
        """Approve an IN_REVIEW item; terminal APPROVED state.
        Codex M-23 v1 review fix: only the assignee may decide."""
        return self._transition(
            review_id=review_id, org_id=org_id, user_id=user_id,
            from_states=(ReviewStatus.IN_REVIEW,),
            to_state=ReviewStatus.APPROVED, decide=True, notes=notes,
            assignee_only=True,
        )

    def reject(
        self, *, review_id: str, org_id: str, user_id: str,
        notes: str | None = None,
    ) -> ReviewItem:
        """Reject an IN_REVIEW item; terminal REJECTED state.
        Codex M-23 v1 review fix: only the assignee may decide."""
        return self._transition(
            review_id=review_id, org_id=org_id, user_id=user_id,
            from_states=(ReviewStatus.IN_REVIEW,),
            to_state=ReviewStatus.REJECTED, decide=True, notes=notes,
            assignee_only=True,
        )

    def request_changes(
        self, *, review_id: str, org_id: str, user_id: str,
        notes: str | None = None,
    ) -> ReviewItem:
        """Decide IN_REVIEW → NEEDS_CHANGES. Operator should
        re-run the audit and call `enqueue(prior_review_id=...)`
        to create a fresh review at version=N+1.

        Codex M-23 v1 review fix: only the assignee may decide.
        """
        return self._transition(
            review_id=review_id, org_id=org_id, user_id=user_id,
            from_states=(ReviewStatus.IN_REVIEW,),
            to_state=ReviewStatus.NEEDS_CHANGES,
            decide=True, notes=notes,
            assignee_only=True,
        )

    def _transition(
        self,
        *,
        review_id: str,
        org_id: str,
        user_id: str,
        from_states: tuple[ReviewStatus, ...],
        to_state: ReviewStatus,
        assign_to_user: bool = False,
        decide: bool = False,
        notes: str | None = None,
        assignee_only: bool = False,
    ) -> ReviewItem:
        if not user_id.strip():
            raise ReviewStateError("user_id must be non-empty")
        # Codex M-23 v1 review fix: notes sanitization. v1 only
        # checked notes.strip() for non-emptiness, which let
        # zero-width spaces (​) and control characters
        # through. v2 strips ALL Unicode whitespace + non-print
        # control characters, then re-checks emptiness.
        sanitized_notes = _sanitize_notes(notes)
        # If notes were SUPPLIED (non-None input) but sanitized to
        # None, the caller submitted zero-width/control-only content
        # masquerading as justification. Surface that as an error
        # for the rejected/needs_changes branches where notes are
        # required by the API contract.
        if (
            decide
            and to_state in (ReviewStatus.REJECTED,
                             ReviewStatus.NEEDS_CHANGES)
            and sanitized_notes is None
        ):
            raise ReviewStateError(
                f"decision {to_state.value!r} requires non-empty "
                f"notes with at least one printable content "
                f"character (zero-width spaces and control chars "
                f"do not count)"
            )
        from_values = tuple(s.value for s in from_states)
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM reviews WHERE review_id = ?",
                    (review_id,),
                ).fetchone()
                if row is None:
                    raise ReviewStateError(
                        f"review {review_id!r} not found"
                    )
                if row["org_id"] != org_id:
                    # Don't leak existence — but also don't pretend
                    # not to exist; the router converts this to 403.
                    raise ReviewStateError(
                        f"review {review_id!r} belongs to a "
                        f"different org"
                    )
                current = ReviewStatus(row["status"])
                if current not in from_states:
                    raise ReviewStateError(
                        f"review {review_id!r} is in state "
                        f"{current.value!r}; expected one of "
                        f"{from_values} to transition to "
                        f"{to_state.value!r}"
                    )
                # Codex M-23 v1 review fix: assignee-only decision.
                # Without this, a same-org member who didn't claim
                # the review can still approve/reject it. v2 enforces
                # exclusive ownership: the assignee_to user is the
                # only one who can decide.
                if assignee_only:
                    assigned = row["assigned_to"]
                    if assigned and assigned != user_id.strip():
                        raise ReviewStateError(
                            f"review {review_id!r} is assigned to "
                            f"{assigned!r}; only the assignee may "
                            f"decide on it"
                        )

                set_parts = ["status = ?", "updated_at = ?"]
                params: list[Any] = [to_state.value, now]
                if assign_to_user:
                    set_parts.append("assigned_to = ?")
                    params.append(user_id.strip())
                if decide:
                    set_parts.append("decided_by = ?")
                    set_parts.append("decided_at = ?")
                    set_parts.append("notes = ?")
                    params.extend([
                        user_id.strip(), now, sanitized_notes,
                    ])
                params.append(review_id)
                conn.execute(
                    f"UPDATE reviews SET {', '.join(set_parts)} "
                    f"WHERE review_id = ?",
                    params,
                )
                conn.execute(
                    "INSERT INTO review_transitions "
                    "(review_id, from_status, to_status, "
                    "actor_user_id, notes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        review_id, current.value, to_state.value,
                        user_id.strip(),
                        sanitized_notes, now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        result = self.get(review_id=review_id, org_id=org_id)
        if result is None:  # defensive — should be impossible after commit
            raise ReviewStoreError(
                f"transitioned review {review_id!r} but cannot read it back"
            )
        return result

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(
        self, *, review_id: str, org_id: str,
    ) -> ReviewItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE review_id = ? AND org_id = ?",
                (review_id, org_id),
            ).fetchone()
        if row is None:
            return None
        return _row_to_review_item(row)

    def list_by_org(
        self,
        *,
        org_id: str,
        status: ReviewStatus | None = None,
    ) -> list[ReviewItem]:
        if status is None:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM reviews WHERE org_id = ? "
                    "ORDER BY updated_at DESC",
                    (org_id,),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM reviews WHERE org_id = ? AND status = ? "
                    "ORDER BY updated_at DESC",
                    (org_id, status.value),
                ).fetchall()
        return [_row_to_review_item(r) for r in rows]

    def list_chain_for_run(
        self, *, org_id: str, run_slug: str,
    ) -> list[ReviewItem]:
        """All reviews for a given run_slug, ordered oldest-first
        by version. Used to render the version-diff timeline."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE org_id = ? AND run_slug = ? "
                "ORDER BY version ASC, created_at ASC",
                (org_id, run_slug),
            ).fetchall()
        return [_row_to_review_item(r) for r in rows]

    def list_transitions(
        self, *, review_id: str, org_id: str,
    ) -> list[dict[str, Any]]:
        """Append-only audit log for one review item. Empty list
        if the item doesn't exist or belongs to a different org."""
        # Org check first, then fetch transitions.
        owner = self.get(review_id=review_id, org_id=org_id)
        if owner is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_transitions WHERE review_id = ? "
                "ORDER BY created_at ASC",
                (review_id,),
            ).fetchall()
        return [
            {
                "transition_id": r["transition_id"],
                "review_id": r["review_id"],
                "from_status": r["from_status"],
                "to_status": r["to_status"],
                "actor_user_id": r["actor_user_id"],
                "notes": r["notes"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Row → object converters
# ---------------------------------------------------------------------------


def _sanitize_notes(notes: str | None) -> str | None:
    """Codex M-23 v1 review fix: strip control characters and
    zero-width spaces before evaluating emptiness.

    v1 used `(notes or "").strip()` which only filters ASCII
    whitespace (`\\t\\n\\v\\f\\r ` plus regular space). Zero-
    width-only or control-char-only `notes` slipped through as
    "non-empty", letting a reviewer reject without justification
    via `\"\\u200b\"` (zero-width space) or `\"\\u0000\"` (null).

    Strategy: drop characters in Unicode categories `Cc` (control)
    and `Cf` (format/zero-width) AND ASCII whitespace. The remainder
    must be non-empty for the notes to count.
    """
    import unicodedata
    if notes is None:
        return None
    cleaned_chars = []
    for ch in notes:
        cat = unicodedata.category(ch)
        if cat.startswith(("Cc", "Cf")):
            continue
        if ch.isspace():
            continue
        cleaned_chars.append(ch)
    if not cleaned_chars:
        return None
    # Keep the original text for storage (so reviewers see what
    # they wrote, including legitimate whitespace), but only return
    # it if the sanitization left a non-empty content footprint.
    return notes.strip() or None


def _row_to_review_item(row: sqlite3.Row) -> ReviewItem:
    return ReviewItem(
        review_id=row["review_id"],
        org_id=row["org_id"],
        run_slug=row["run_slug"],
        run_id=row["run_id"],
        status=ReviewStatus(row["status"]),
        assigned_to=row["assigned_to"],
        decided_by=row["decided_by"],
        notes=row["notes"],
        version=int(row["version"]),
        prior_review_id=row["prior_review_id"],
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        decided_at=(
            float(row["decided_at"]) if row["decided_at"] is not None else None
        ),
    )
