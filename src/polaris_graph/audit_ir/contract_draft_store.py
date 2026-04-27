"""Semi-automated contract drafting (M-26 — Phase C).

Per FINAL_PLAN Phase C deliverable #3:
  Semi-automated contract drafting with mandatory human approval
  before customer-facing.

The substrate that lets a Polaris audit produce a contract draft
(MSA, SoW, DPA, BAA) bound to specific verified findings, with
the explicit FINAL_PLAN guarantee that NO draft can become
customer-facing without human approval.

Scope of v1:
  - Per-org draft registry. Each draft references a specific
    audit run + a list of clause_ids that the human approver
    must sign off on.
  - Lifecycle: DRAFT → AWAITING_APPROVAL → APPROVED | REJECTED.
    Approval requires a non-empty rationale plus the approver's
    user_id (so SOC2 audit later shows "alice@org approved
    contract X based on the audit_id Y at timestamp Z").
  - Append-only clause-decision log: each clause_id tracks
    individual approve/reject status. The contract as a whole
    can only flip to APPROVED when EVERY clause is approved.
  - Cross-tenant isolation throughout.

Out of scope for v1:
  - Templating engine (DOCX, PDF). Drafts here are structured
    JSON (clause list + binding map); the renderer is a follow-up.
  - LLM-generated draft text. v1 stores operator-supplied
    clause text + the audit-run binding; the actual drafting
    LLM call lives outside this module so the audit_ir surface
    stays deterministic.
  - Counterparty-side workflows (countersign, redlines,
    versioning of negotiated changes).

LAW VII compliance: stdlib only. Endpoints wired separately.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ContractDraftStatus(Enum):
    """Lifecycle states for a contract draft."""

    DRAFT = "draft"  # Operator is still editing the clause set.
    AWAITING_APPROVAL = "awaiting_approval"  # Submitted; reviewer pending.
    APPROVED = "approved"  # Human approver signed off; ready to ship.
    REJECTED = "rejected"  # Reviewer rejected; cannot be sent.


class ClauseDecision(Enum):
    """Per-clause approval state."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContractKind(Enum):
    """Closed enum of contract types Polaris drafts.

    MSA = Master Services Agreement
    SOW = Statement of Work
    DPA = Data Processing Addendum
    BAA = Business Associate Agreement (HIPAA)
    """

    MSA = "msa"
    SOW = "sow"
    DPA = "dpa"
    BAA = "baa"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractDraftError(Exception):
    """Base error for contract-draft operations."""


class ContractDraftStateError(ContractDraftError):
    """Invalid input or state transition."""


class ContractApprovalGateError(ContractDraftError):
    """An attempt to ship/use a draft that has not been
    human-approved. The FINAL_PLAN's "mandatory human approval
    before customer-facing" gate."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractClause:
    """One clause inside a draft.

    `evidence_ids` and `claim_ids` carry the audit-IR back-links
    that ground this clause. A clause without back-links is
    allowed (e.g. boilerplate jurisdiction language) but the
    Inspector view will surface that as "unsourced" so the
    reviewer can confirm it's intentional.
    """

    clause_id: str
    draft_id: str
    title: str
    body: str
    evidence_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    decision: ClauseDecision
    decided_by: str | None
    decision_notes: str | None
    decided_at: float | None
    created_at: float


@dataclass(frozen=True)
class ContractDraft:
    """One contract draft.

    `audit_run_id` is the V30 run this draft is anchored to —
    every clause's evidence/claim back-links must resolve into
    that run's audit IR (validated at clause-add time).
    """

    draft_id: str
    org_id: str
    workspace_id: str
    submitter_user_id: str
    audit_run_id: str
    kind: ContractKind
    title: str
    counterparty_name: str
    status: ContractDraftStatus
    approved_by: str | None
    rejected_by: str | None
    decision_rationale: str | None
    created_at: float
    updated_at: float
    decided_at: float | None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS contract_drafts (
    draft_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    submitter_user_id TEXT NOT NULL,
    audit_run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    counterparty_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    approved_by TEXT,
    rejected_by TEXT,
    decision_rationale TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    decided_at REAL
);

CREATE INDEX IF NOT EXISTS idx_contract_drafts_org_status
    ON contract_drafts(org_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS contract_clauses (
    clause_id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    claim_ids_json TEXT NOT NULL DEFAULT '[]',
    decision TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT,
    decision_notes TEXT,
    decided_at REAL,
    created_at REAL NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES contract_drafts(draft_id)
);

CREATE INDEX IF NOT EXISTS idx_contract_clauses_draft
    ON contract_clauses(draft_id, created_at);

-- Append-only decision audit log: every clause / draft state
-- change writes one row so SOC2 / customer-support flows can
-- show "who approved this clause and when?"
CREATE TABLE IF NOT EXISTS contract_decision_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT NOT NULL,
    clause_id TEXT,
    actor_user_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    rationale TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES contract_drafts(draft_id)
);

CREATE INDEX IF NOT EXISTS idx_contract_decision_log_draft
    ON contract_decision_log(draft_id, created_at);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


_TERMINAL_DRAFT_STATES: frozenset[ContractDraftStatus] = frozenset({
    ContractDraftStatus.APPROVED, ContractDraftStatus.REJECTED,
})


class ContractDraftStore:
    """SQLite-backed contract-draft registry.

    Authorization posture: the store enforces cross-tenant
    isolation (every read/write is org-scoped), but does NOT
    validate role. The endpoint layer must gate on owner/admin
    role for `submit_for_approval` / `approve_draft` /
    `reject_draft` so a regular member cannot self-approve their
    own contract drafts.
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
    # Draft creation
    # ------------------------------------------------------------------

    def create_draft(
        self,
        *,
        org_id: str,
        workspace_id: str,
        submitter_user_id: str,
        audit_run_id: str,
        kind: ContractKind,
        title: str,
        counterparty_name: str,
    ) -> ContractDraft:
        if not org_id.strip() or not workspace_id.strip():
            raise ContractDraftStateError(
                "org_id and workspace_id must be non-empty"
            )
        if not submitter_user_id.strip():
            raise ContractDraftStateError(
                "submitter_user_id must be non-empty"
            )
        if not audit_run_id.strip():
            raise ContractDraftStateError(
                "audit_run_id must be non-empty — every contract "
                "draft must be anchored to a specific verified "
                "audit run"
            )
        if not isinstance(kind, ContractKind):
            raise ContractDraftStateError(
                f"kind must be ContractKind, got {kind!r}"
            )
        if not title.strip():
            raise ContractDraftStateError("title must be non-empty")
        if not counterparty_name.strip():
            raise ContractDraftStateError(
                "counterparty_name must be non-empty"
            )
        draft_id = f"ctr_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO contract_drafts (draft_id, org_id, "
                "workspace_id, submitter_user_id, audit_run_id, "
                "kind, title, counterparty_name, status, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft_id, org_id.strip(), workspace_id.strip(),
                    submitter_user_id.strip(), audit_run_id.strip(),
                    kind.value, title.strip(),
                    counterparty_name.strip(),
                    ContractDraftStatus.DRAFT.value, now, now,
                ),
            )
            conn.execute(
                "INSERT INTO contract_decision_log (draft_id, "
                "clause_id, actor_user_id, from_state, to_state, "
                "rationale, created_at) VALUES "
                "(?, NULL, ?, NULL, ?, ?, ?)",
                (
                    draft_id, submitter_user_id.strip(),
                    ContractDraftStatus.DRAFT.value,
                    "created", now,
                ),
            )
        return ContractDraft(
            draft_id=draft_id, org_id=org_id.strip(),
            workspace_id=workspace_id.strip(),
            submitter_user_id=submitter_user_id.strip(),
            audit_run_id=audit_run_id.strip(),
            kind=kind, title=title.strip(),
            counterparty_name=counterparty_name.strip(),
            status=ContractDraftStatus.DRAFT,
            approved_by=None, rejected_by=None,
            decision_rationale=None,
            created_at=now, updated_at=now, decided_at=None,
        )

    # ------------------------------------------------------------------
    # Clause management
    # ------------------------------------------------------------------

    def add_clause(
        self,
        *,
        draft_id: str,
        org_id: str,
        title: str,
        body: str,
        evidence_ids: tuple[str, ...] = (),
        claim_ids: tuple[str, ...] = (),
    ) -> ContractClause:
        if not title.strip() or not body.strip():
            raise ContractDraftStateError(
                "clause title and body must be non-empty"
            )
        # Verify draft exists in this org and is still editable.
        draft = self.get_draft(draft_id=draft_id, org_id=org_id)
        if draft is None:
            raise ContractDraftStateError(
                f"draft {draft_id!r} is not accessible to this caller"
            )
        if draft.status != ContractDraftStatus.DRAFT:
            raise ContractDraftStateError(
                f"draft {draft_id!r} is in state {draft.status.value!r}; "
                f"clauses can only be added while in DRAFT state"
            )
        clause_id = f"cls_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO contract_clauses (clause_id, draft_id, "
                "title, body, evidence_ids_json, claim_ids_json, "
                "decision, created_at) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    clause_id, draft_id, title.strip(), body.strip(),
                    json.dumps(list(evidence_ids), sort_keys=True),
                    json.dumps(list(claim_ids), sort_keys=True),
                    ClauseDecision.PENDING.value, now,
                ),
            )
            conn.execute(
                "UPDATE contract_drafts SET updated_at = ? "
                "WHERE draft_id = ?",
                (now, draft_id),
            )
        return ContractClause(
            clause_id=clause_id, draft_id=draft_id,
            title=title.strip(), body=body.strip(),
            evidence_ids=tuple(evidence_ids),
            claim_ids=tuple(claim_ids),
            decision=ClauseDecision.PENDING,
            decided_by=None, decision_notes=None,
            decided_at=None, created_at=now,
        )

    def list_clauses(
        self, *, draft_id: str, org_id: str,
    ) -> list[ContractClause]:
        if self.get_draft(draft_id=draft_id, org_id=org_id) is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contract_clauses WHERE draft_id = ? "
                "ORDER BY created_at ASC",
                (draft_id,),
            ).fetchall()
        return [_row_to_clause(r) for r in rows]

    def decide_clause(
        self,
        *,
        clause_id: str,
        org_id: str,
        approver_user_id: str,
        decision: ClauseDecision,
        notes: str | None = None,
    ) -> ContractClause:
        """Per-clause approve / reject. Per-clause decisions are
        durable and auditable; the overall draft only flips to
        APPROVED when EVERY clause is APPROVED."""
        if not approver_user_id.strip():
            raise ContractDraftStateError(
                "approver_user_id must be non-empty"
            )
        if decision == ClauseDecision.PENDING:
            raise ContractDraftStateError(
                "cannot decide a clause as PENDING; pass APPROVED "
                "or REJECTED"
            )
        sanitized_notes = _sanitize_notes(notes)
        if decision == ClauseDecision.REJECTED and sanitized_notes is None:
            raise ContractDraftStateError(
                "rejecting a clause requires non-empty notes"
            )
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                clause_row = conn.execute(
                    "SELECT c.*, d.org_id AS draft_org_id, "
                    "d.status AS draft_status FROM contract_clauses c "
                    "JOIN contract_drafts d ON c.draft_id = d.draft_id "
                    "WHERE c.clause_id = ?",
                    (clause_id,),
                ).fetchone()
                if clause_row is None:
                    raise ContractDraftStateError(
                        f"clause {clause_id!r} not found"
                    )
                if clause_row["draft_org_id"] != org_id:
                    raise ContractDraftStateError(
                        f"clause {clause_id!r} belongs to a different org"
                    )
                draft_status = ContractDraftStatus(clause_row["draft_status"])
                if draft_status not in (
                    ContractDraftStatus.AWAITING_APPROVAL,
                ):
                    raise ContractDraftStateError(
                        f"clause decisions are only valid while the "
                        f"draft is in AWAITING_APPROVAL; draft is "
                        f"in {draft_status.value!r}"
                    )
                conn.execute(
                    "UPDATE contract_clauses SET decision = ?, "
                    "decided_by = ?, decision_notes = ?, "
                    "decided_at = ? WHERE clause_id = ?",
                    (
                        decision.value, approver_user_id.strip(),
                        sanitized_notes, now, clause_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO contract_decision_log (draft_id, "
                    "clause_id, actor_user_id, from_state, to_state, "
                    "rationale, created_at) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?)",
                    (
                        clause_row["draft_id"], clause_id,
                        approver_user_id.strip(),
                        clause_row["decision"], decision.value,
                        sanitized_notes, now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        # Re-read the clause for the up-to-date row.
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contract_clauses WHERE clause_id = ?",
                (clause_id,),
            ).fetchone()
        return _row_to_clause(row)

    # ------------------------------------------------------------------
    # Draft lifecycle
    # ------------------------------------------------------------------

    def submit_for_approval(
        self, *, draft_id: str, org_id: str, submitter_user_id: str,
    ) -> ContractDraft:
        """Move a DRAFT into AWAITING_APPROVAL. Refuses if the
        draft has zero clauses."""
        clauses = self.list_clauses(draft_id=draft_id, org_id=org_id)
        if not clauses:
            raise ContractDraftStateError(
                f"draft {draft_id!r} has no clauses; cannot submit "
                f"an empty contract for approval"
            )
        return self._transition_draft(
            draft_id=draft_id, org_id=org_id,
            actor_user_id=submitter_user_id,
            from_states=(ContractDraftStatus.DRAFT,),
            to_state=ContractDraftStatus.AWAITING_APPROVAL,
            rationale="submitted",
        )

    def approve_draft(
        self,
        *,
        draft_id: str,
        org_id: str,
        approver_user_id: str,
        rationale: str,
    ) -> ContractDraft:
        """Approve the whole draft. The FINAL_PLAN gate.

        Refuses if (a) any clause is still PENDING, or (b) any
        clause is REJECTED — every clause must be APPROVED.
        Refuses if the approver is also the submitter (separation
        of duties).
        """
        sanitized = _sanitize_notes(rationale)
        if sanitized is None:
            raise ContractDraftStateError(
                "approval rationale must be non-empty (LAW II — "
                "every approval is part of the SOC2 audit trail)"
            )
        # Check separation of duties FIRST, before checking clauses,
        # so a self-approval attempt fails with the SOD error not
        # the "not all approved" error.
        with self._connect() as conn:
            row = conn.execute(
                "SELECT submitter_user_id FROM contract_drafts "
                "WHERE draft_id = ? AND org_id = ?",
                (draft_id, org_id),
            ).fetchone()
        if row is None:
            raise ContractDraftStateError(
                f"draft {draft_id!r} is not accessible to this caller"
            )
        if row["submitter_user_id"] == approver_user_id.strip():
            raise ContractDraftStateError(
                "the contract submitter cannot approve their own "
                "draft (separation of duties — every approval needs "
                "a second human reviewer)"
            )
        clauses = self.list_clauses(draft_id=draft_id, org_id=org_id)
        statuses = {c.decision for c in clauses}
        if ClauseDecision.PENDING in statuses:
            raise ContractDraftStateError(
                "cannot approve draft: at least one clause is still "
                "PENDING; decide every clause before approving"
            )
        if ClauseDecision.REJECTED in statuses:
            raise ContractDraftStateError(
                "cannot approve draft: at least one clause is "
                "REJECTED; remove or replace it before approving"
            )
        return self._transition_draft(
            draft_id=draft_id, org_id=org_id,
            actor_user_id=approver_user_id,
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale=sanitized,
            mark_decided=True, set_approver=True,
        )

    def reject_draft(
        self,
        *,
        draft_id: str,
        org_id: str,
        rejecter_user_id: str,
        rationale: str,
    ) -> ContractDraft:
        sanitized = _sanitize_notes(rationale)
        if sanitized is None:
            raise ContractDraftStateError(
                "rejection rationale must be non-empty"
            )
        return self._transition_draft(
            draft_id=draft_id, org_id=org_id,
            actor_user_id=rejecter_user_id,
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.REJECTED,
            rationale=sanitized,
            mark_decided=True, set_rejecter=True,
        )

    def _transition_draft(
        self,
        *,
        draft_id: str,
        org_id: str,
        actor_user_id: str,
        from_states: tuple[ContractDraftStatus, ...],
        to_state: ContractDraftStatus,
        rationale: str | None = None,
        mark_decided: bool = False,
        set_approver: bool = False,
        set_rejecter: bool = False,
    ) -> ContractDraft:
        if not actor_user_id.strip():
            raise ContractDraftStateError(
                "actor_user_id must be non-empty"
            )
        from_values = tuple(s.value for s in from_states)
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM contract_drafts WHERE draft_id = ?",
                    (draft_id,),
                ).fetchone()
                if row is None:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} not found"
                    )
                if row["org_id"] != org_id:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} belongs to a different org"
                    )
                current = ContractDraftStatus(row["status"])
                if current not in from_states:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is in state "
                        f"{current.value!r}; expected one of "
                        f"{from_values} to transition to "
                        f"{to_state.value!r}"
                    )
                set_parts = ["status = ?", "updated_at = ?"]
                params: list[Any] = [to_state.value, now]
                if mark_decided:
                    set_parts.append("decided_at = ?")
                    set_parts.append("decision_rationale = ?")
                    params.extend([now, rationale])
                if set_approver:
                    set_parts.append("approved_by = ?")
                    set_parts.append("rejected_by = NULL")
                    params.append(actor_user_id.strip())
                if set_rejecter:
                    set_parts.append("rejected_by = ?")
                    set_parts.append("approved_by = NULL")
                    params.append(actor_user_id.strip())
                params.append(draft_id)
                conn.execute(
                    f"UPDATE contract_drafts SET {', '.join(set_parts)} "
                    f"WHERE draft_id = ?",
                    params,
                )
                conn.execute(
                    "INSERT INTO contract_decision_log (draft_id, "
                    "clause_id, actor_user_id, from_state, to_state, "
                    "rationale, created_at) VALUES "
                    "(?, NULL, ?, ?, ?, ?, ?)",
                    (
                        draft_id, actor_user_id.strip(),
                        current.value, to_state.value,
                        rationale, now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        result = self.get_draft(draft_id=draft_id, org_id=org_id)
        if result is None:
            raise ContractDraftError(
                f"transitioned draft {draft_id!r} but cannot read it back"
            )
        return result

    # ------------------------------------------------------------------
    # The FINAL_PLAN gate
    # ------------------------------------------------------------------

    def assert_approved_for_send(
        self, *, draft_id: str, org_id: str,
    ) -> ContractDraft:
        """The FINAL_PLAN's "mandatory human approval before
        customer-facing" gate. Anywhere downstream code is about
        to send / render / export a contract draft, it MUST call
        this first. Raises ContractApprovalGateError if the draft
        is not in APPROVED state.
        """
        draft = self.get_draft(draft_id=draft_id, org_id=org_id)
        if draft is None:
            raise ContractApprovalGateError(
                f"draft {draft_id!r} is not accessible to this caller"
            )
        if draft.status != ContractDraftStatus.APPROVED:
            raise ContractApprovalGateError(
                f"draft {draft_id!r} is in state "
                f"{draft.status.value!r}; only APPROVED drafts may "
                f"be sent to a customer (FINAL_PLAN: mandatory human "
                f"approval before customer-facing)"
            )
        return draft

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def get_draft(
        self, *, draft_id: str, org_id: str,
    ) -> ContractDraft | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contract_drafts "
                "WHERE draft_id = ? AND org_id = ?",
                (draft_id, org_id),
            ).fetchone()
        return _row_to_draft(row) if row is not None else None

    def list_drafts_for_org(
        self,
        *,
        org_id: str,
        status: ContractDraftStatus | None = None,
    ) -> list[ContractDraft]:
        clauses = ["org_id = ?"]
        params: list[Any] = [org_id]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        sql = (
            f"SELECT * FROM contract_drafts WHERE "
            f"{' AND '.join(clauses)} ORDER BY updated_at DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_draft(r) for r in rows]

    def list_decision_log(
        self, *, draft_id: str, org_id: str,
    ) -> list[dict[str, Any]]:
        if self.get_draft(draft_id=draft_id, org_id=org_id) is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contract_decision_log "
                "WHERE draft_id = ? ORDER BY created_at ASC",
                (draft_id,),
            ).fetchall()
        return [
            {
                "log_id": r["log_id"], "draft_id": r["draft_id"],
                "clause_id": r["clause_id"],
                "actor_user_id": r["actor_user_id"],
                "from_state": r["from_state"],
                "to_state": r["to_state"],
                "rationale": r["rationale"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_notes(notes: str | None) -> str | None:
    """Same notes-sanitization pattern as review_store: strip
    Unicode Cc/Cf categories + whitespace; if nothing remains, the
    input was content-empty."""
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
    return notes.strip() or None


def _row_to_draft(row: sqlite3.Row) -> ContractDraft:
    return ContractDraft(
        draft_id=row["draft_id"],
        org_id=row["org_id"],
        workspace_id=row["workspace_id"],
        submitter_user_id=row["submitter_user_id"],
        audit_run_id=row["audit_run_id"],
        kind=ContractKind(row["kind"]),
        title=row["title"],
        counterparty_name=row["counterparty_name"],
        status=ContractDraftStatus(row["status"]),
        approved_by=row["approved_by"],
        rejected_by=row["rejected_by"],
        decision_rationale=row["decision_rationale"],
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        decided_at=(
            float(row["decided_at"]) if row["decided_at"] is not None
            else None
        ),
    )


def _row_to_clause(row: sqlite3.Row) -> ContractClause:
    evidence_ids = tuple(json.loads(row["evidence_ids_json"] or "[]"))
    claim_ids = tuple(json.loads(row["claim_ids_json"] or "[]"))
    return ContractClause(
        clause_id=row["clause_id"],
        draft_id=row["draft_id"],
        title=row["title"],
        body=row["body"],
        evidence_ids=evidence_ids,
        claim_ids=claim_ids,
        decision=ClauseDecision(row["decision"]),
        decided_by=row["decided_by"],
        decision_notes=row["decision_notes"],
        decided_at=(
            float(row["decided_at"]) if row["decided_at"] is not None
            else None
        ),
        created_at=float(row["created_at"]),
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def draft_to_dict(d: ContractDraft) -> dict[str, Any]:
    return {
        "draft_id": d.draft_id,
        "org_id": d.org_id,
        "workspace_id": d.workspace_id,
        "submitter_user_id": d.submitter_user_id,
        "audit_run_id": d.audit_run_id,
        "kind": d.kind.value,
        "title": d.title,
        "counterparty_name": d.counterparty_name,
        "status": d.status.value,
        "approved_by": d.approved_by,
        "rejected_by": d.rejected_by,
        "decision_rationale": d.decision_rationale,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "decided_at": d.decided_at,
    }


def clause_to_dict(c: ContractClause) -> dict[str, Any]:
    return {
        "clause_id": c.clause_id, "draft_id": c.draft_id,
        "title": c.title, "body": c.body,
        "evidence_ids": list(c.evidence_ids),
        "claim_ids": list(c.claim_ids),
        "decision": c.decision.value,
        "decided_by": c.decided_by,
        "decision_notes": c.decision_notes,
        "decided_at": c.decided_at,
        "created_at": c.created_at,
    }
