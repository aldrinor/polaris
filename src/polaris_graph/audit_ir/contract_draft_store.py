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

Codex M-26 v6 review (structural refactor): the prior v1..v5
parameterized helper `_transition_draft(to_state, from_states,
mark_decided, set_approver, set_rejecter)` had a combinatorial
bypass surface. Each round of review found a new (parameter,
value) tuple that escaped the invariants. v6 eliminates the
parameter surface entirely:

  - Three concrete private helpers, one per legal transition:
        _perform_submit  : DRAFT → AWAITING_APPROVAL
        _perform_approve : AWAITING_APPROVAL → APPROVED
        _perform_reject  : AWAITING_APPROVAL → REJECTED
    Each is hardcoded for its specific edge — no `to_state`
    parameter, no `from_states` parameter, no bookkeeping flags.
    There is no parameter combination that can produce an illegal
    state because the parameters that would express "illegal
    state" do not exist.

  - DB-level CHECK constraints encode the audit-trail invariants:
        DRAFT             : decision fields all NULL
        AWAITING_APPROVAL : decision fields all NULL
        APPROVED          : approved_by + decision_rationale +
                            decided_at all NOT NULL + non-empty,
                            rejected_by NULL
        REJECTED          : rejected_by + decision_rationale +
                            decided_at all NOT NULL + non-empty,
                            approved_by NULL
    Even direct SQL UPDATE attempts that violate these patterns
    fail at the SQL layer.

Codex M-26 v7 review fix: v6 had three remaining bypasses:
  (a) `_perform_approve` / `_perform_reject` re-validated rationale
      with `.strip()` instead of `_sanitize_notes`, allowing
      content-empty rationales like "​" (zero-width space)
      to pass when called directly.
  (b) DB CHECK only enforced `IS NOT NULL` — direct SQL could
      write `decision_rationale=''` and pass.
  (c) DB CHECK could not express the cross-row invariant
      "all clauses approved before status='approved'", so
      direct SQL UPDATE writing canonical APPROVED metadata
      onto a draft with PENDING clauses was reachable.

v7 closes all three:
  - Helpers route rationale through `_sanitize_notes` (strips
    Cc/Cf categories + whitespace; rejects content-empty input).
  - CHECK adds `length(field) > 0` to all NOT-NULL string fields.
  - SQL TRIGGERs encode cross-row invariants the CHECK cannot:
      * `trg_validate_status_transition`: closed transition table
        + all-clauses-approved + SOD enforced at SQL layer.
      * `trg_validate_status_on_insert`: new rows must start
        in 'draft' status.
      * `trg_freeze_clauses_on_terminal_*`: clauses are immutable
        after the parent draft reaches APPROVED / REJECTED.

Codex M-26 v8 review fix: v7's freeze triggers covered UPDATE
and DELETE on contract_clauses but not INSERT. Direct SQL could
still INSERT a fresh `decision='pending'` clause onto an APPROVED
draft, which `assert_approved_for_send` then passed because it
only checks draft.status. v8 adds the symmetric BEFORE INSERT
trigger so terminal drafts have NO mutable clause surface.

Codex M-26 v9 review fix: v8 had two more bypasses:
  (a) clause UPDATE freeze checked `NEW.draft_id` only — direct
      SQL `UPDATE contract_clauses SET draft_id = <non-terminal>`
      moved a clause OFF a terminal draft. v9 checks BOTH OLD and
      NEW draft_id so the trigger fires when either end touches
      a terminal draft.
  (b) `contract_drafts` row had no terminal-row freeze for non-
      status mutations. Direct SQL could mutate `title`,
      `counterparty_name`, `audit_run_id` etc. on an APPROVED row.
      v9 adds `trg_freeze_drafts_on_terminal` (BEFORE UPDATE) and
      `trg_freeze_drafts_delete_on_terminal` (BEFORE DELETE) so
      terminal rows are fully immutable.

Codex M-26 v10 review fix: v9 had two more bypasses on the clause
substrate during AWAITING_APPROVAL:
  (a) Direct SQL `UPDATE contract_clauses SET decision='approved'`
      bypassed `decide_clause` and left no `decided_by` /
      `decided_at` audit metadata. v10 adds a CHECK on
      contract_clauses binding decision values to their canonical
      audit-trail metadata pattern.
  (b) Clause body/title/evidence_ids could be rewritten via
      direct SQL after a decision was recorded. The shipped
      approved contract could differ from what the clause
      reviewer signed off on. v10 adds `trg_clause_content_immutable`
      so body/title/evidence_ids/claim_ids are frozen from
      INSERT-time onward — only decision metadata can change.

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

    `audit_run_id` is the V30 run this draft is anchored to.
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


# Codex M-26 v6 review fix: encode SOC2 audit-trail invariants as
# DB-level CHECK constraints. Even a direct SQL UPDATE that tries
# to write status='approved' with approved_by=NULL fails at the
# SQL layer. The Python helpers + the DB constraints form a
# defense-in-depth pair: the helpers ensure invariant maintenance
# during normal operation, and the constraints ensure that SQL-
# level mistakes (or future contributors who don't read the docs)
# cannot land an invalid row.
#
# Codex M-26 v7 review fix: v6 CHECK constraints only enforced
# `IS NOT NULL`, allowing direct SQL to write empty-string audit
# fields (e.g. approved_by='', decision_rationale=''). v7 adds
# `length() > 0` checks. Plus v7 adds three SQL TRIGGERs that
# enforce cross-row invariants the CHECK constraint cannot
# express:
#   - state-machine validity (closed transition table at SQL
#     layer): only DRAFT→AWAITING_APPROVAL, AWAITING_APPROVAL→
#     APPROVED, AWAITING_APPROVAL→REJECTED are legal
#   - all-clauses-approved before status='approved'
#   - SOD at SQL layer (approved_by != submitter_user_id)
#   - non-empty clauses before status='awaiting_approval'
#   - clauses immutable after terminal status (no UPDATE/DELETE
#     on contract_clauses when parent draft is APPROVED/REJECTED)
#   - new drafts must start in 'draft' status (no INSERT bypass)
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
    decided_at REAL,
    CHECK (
        (status = 'draft'
            AND approved_by IS NULL
            AND rejected_by IS NULL
            AND decision_rationale IS NULL
            AND decided_at IS NULL)
        OR
        (status = 'awaiting_approval'
            AND approved_by IS NULL
            AND rejected_by IS NULL
            AND decision_rationale IS NULL
            AND decided_at IS NULL)
        OR
        (status = 'approved'
            AND approved_by IS NOT NULL
            AND length(approved_by) > 0
            AND rejected_by IS NULL
            AND decision_rationale IS NOT NULL
            AND length(decision_rationale) > 0
            AND decided_at IS NOT NULL)
        OR
        (status = 'rejected'
            AND approved_by IS NULL
            AND rejected_by IS NOT NULL
            AND length(rejected_by) > 0
            AND decision_rationale IS NOT NULL
            AND length(decision_rationale) > 0
            AND decided_at IS NOT NULL)
    )
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
    FOREIGN KEY (draft_id) REFERENCES contract_drafts(draft_id),
    -- Codex M-26 v10 review fix: clause-decision audit-trail
    -- invariants. Direct SQL UPDATE setting decision='approved'
    -- without decided_by + decided_at violated SOC2 in v9; the
    -- CHECK enforces the canonical pattern per decision value.
    CHECK (
        (decision = 'pending'
            AND decided_by IS NULL
            AND decision_notes IS NULL
            AND decided_at IS NULL)
        OR
        (decision = 'approved'
            AND decided_by IS NOT NULL
            AND length(decided_by) > 0
            AND decided_at IS NOT NULL)
        OR
        (decision = 'rejected'
            AND decided_by IS NOT NULL
            AND length(decided_by) > 0
            AND decided_at IS NOT NULL
            AND decision_notes IS NOT NULL
            AND length(decision_notes) > 0)
    )
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

-- Codex M-26 v15 review fix (post-lock doc audit): the threat-model
-- doc claimed contract_decision_log was append-only "by design". It
-- wasn't — the table had no protective triggers, so direct SQL
-- could UPDATE row attribution or DELETE log entries entirely,
-- eliminating the audit trail that v12/v13 auto-log triggers
-- write. This trio of triggers makes the table truly append-only:
-- INSERTs only (existing auto-log triggers + create_draft).
-- No UPDATE, no DELETE, no truncation via DML.
CREATE TRIGGER IF NOT EXISTS trg_decision_log_no_update
BEFORE UPDATE ON contract_decision_log
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'contract_decision_log is append-only; UPDATE is forbidden (every row is an immutable audit record)');
END;

CREATE TRIGGER IF NOT EXISTS trg_decision_log_no_delete
BEFORE DELETE ON contract_decision_log
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'contract_decision_log is append-only; DELETE is forbidden (the audit trail must survive)');
END;

-- Codex M-26 v17 review fix: the v16 PRAGMA approach only worked
-- for store-owned connections. A direct-SQL attacker opens their
-- own SQLite connection at the default `recursive_triggers = OFF`
-- and uses `INSERT OR REPLACE INTO contract_decision_log
-- (log_id, ...)` to delete-then-insert without firing the
-- BEFORE DELETE trigger.
--
-- This trigger catches the REPLACE attack at the BEFORE INSERT
-- phase (which DOES fire regardless of recursive_triggers state):
-- if NEW.log_id is non-NULL and a row with that log_id already
-- exists, it's an INSERT OR REPLACE and must abort.
--
-- Legitimate INSERT paths (auto-log triggers + create_draft) do
-- NOT specify log_id explicitly (it autoincrements), so the
-- WHEN clause doesn't fire on them. Forged INSERT OR REPLACE
-- with explicit log_id is the specific attack closed.
CREATE TRIGGER IF NOT EXISTS trg_decision_log_no_replace
BEFORE INSERT ON contract_decision_log
FOR EACH ROW
WHEN NEW.log_id IS NOT NULL
     AND EXISTS (
         SELECT 1 FROM contract_decision_log WHERE log_id = NEW.log_id
     )
BEGIN
    SELECT RAISE(ABORT, 'contract_decision_log is append-only; INSERT OR REPLACE on an existing log_id is forbidden (overwrites the audit record)');
END;

-- Codex M-26 v7 review fix: SQL triggers encode the cross-row
-- SOC2 invariants the CHECK constraint cannot express. Even a
-- direct SQL UPDATE that bypasses the Python helpers fails at
-- the SQL layer.

-- Trigger 1: validate state-machine transitions at SQL level.
-- The closed transition table:
--   draft             -> awaiting_approval (with >=1 clause)
--   awaiting_approval -> approved (all clauses approved + SOD)
--   awaiting_approval -> rejected
-- All other (OLD.status, NEW.status) pairs are forbidden,
-- including any transition TO 'draft' (terminal-state revival).
CREATE TRIGGER IF NOT EXISTS trg_validate_status_transition
BEFORE UPDATE OF status ON contract_drafts
FOR EACH ROW
WHEN NEW.status != OLD.status
BEGIN
    SELECT CASE
        WHEN NEW.status = 'draft'
            THEN RAISE(ABORT, 'illegal transition: draft cannot be a target state (no path back to draft)')
        WHEN NEW.status = 'awaiting_approval' AND OLD.status != 'draft'
            THEN RAISE(ABORT, 'illegal transition: awaiting_approval only reachable from draft')
        WHEN NEW.status = 'awaiting_approval' AND NOT EXISTS (
            SELECT 1 FROM contract_clauses WHERE draft_id = NEW.draft_id
        )
            THEN RAISE(ABORT, 'cannot submit empty draft: at least one clause required')
        WHEN NEW.status = 'approved' AND OLD.status != 'awaiting_approval'
            THEN RAISE(ABORT, 'illegal transition: approved only reachable from awaiting_approval')
        WHEN NEW.status = 'approved' AND NOT EXISTS (
            SELECT 1 FROM contract_clauses WHERE draft_id = NEW.draft_id
        )
            THEN RAISE(ABORT, 'cannot approve draft: no clauses')
        WHEN NEW.status = 'approved' AND EXISTS (
            SELECT 1 FROM contract_clauses
            WHERE draft_id = NEW.draft_id AND decision != 'approved'
        )
            THEN RAISE(ABORT, 'cannot approve draft: at least one clause is not approved')
        WHEN NEW.status = 'approved' AND NEW.approved_by = NEW.submitter_user_id
            THEN RAISE(ABORT, 'cannot approve own draft: separation of duties')
        WHEN NEW.status = 'rejected' AND OLD.status != 'awaiting_approval'
            THEN RAISE(ABORT, 'illegal transition: rejected only reachable from awaiting_approval')
        WHEN NEW.status NOT IN ('draft', 'awaiting_approval', 'approved', 'rejected')
            THEN RAISE(ABORT, 'illegal status value')
    END;
END;

-- Trigger 2: new contract drafts must start in 'draft' status.
-- Direct SQL INSERT cannot bypass the lifecycle by inserting a
-- row already in 'approved' (or any non-draft) status.
CREATE TRIGGER IF NOT EXISTS trg_validate_status_on_insert
BEFORE INSERT ON contract_drafts
FOR EACH ROW
WHEN NEW.status != 'draft'
BEGIN
    SELECT RAISE(ABORT, 'new contract drafts must be inserted in draft status');
END;

-- Trigger 3: clauses are frozen once the parent draft reaches a
-- terminal status (APPROVED / REJECTED). After approval, no one
-- can flip a clause from approved to rejected (or vice versa)
-- to retroactively change what was reviewed.
-- Codex M-26 v9 review fix: v8's WHEN clause only checked
-- NEW.draft_id, so `UPDATE contract_clauses SET draft_id = <non-
-- terminal>` could move a clause OFF a terminal draft (OLD points
-- at terminal but NEW doesn't, trigger doesn't fire). v9 checks
-- both OLD and NEW so the trigger fires if EITHER end of the
-- update touches a terminal draft.
--
-- This trigger blocks any UPDATE on terminal-parent clauses —
-- including legitimate-looking decision flips that would happen
-- post-approval. Decision changes during AWAITING_APPROVAL are
-- allowed (decide_clause); this fires only when parent is
-- already terminal.
CREATE TRIGGER IF NOT EXISTS trg_freeze_clauses_on_terminal_update
BEFORE UPDATE ON contract_clauses
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE (draft_id = NEW.draft_id OR draft_id = OLD.draft_id)
      AND status IN ('approved', 'rejected')
)
BEGIN
    SELECT RAISE(ABORT, 'cannot modify clauses on a terminal draft (approved or rejected)');
END;

-- Codex M-26 v11 review fix: v10's freeze triggers only protected
-- the contract_clauses table when the parent draft was in a
-- terminal state (APPROVED/REJECTED). During the AWAITING_APPROVAL
-- window — between submit and final-approve — direct SQL could
-- still INSERT a forged 'decision=approved' clause, DELETE a
-- rejected clause, or move a rejected clause to another non-
-- terminal draft. approve_draft only validates the clauses
-- currently attached, so the bypass passed.
--
-- v11 expands the protection: clauses on a non-DRAFT parent
-- (i.e. submitted, approved, or rejected) cannot be inserted,
-- deleted, or moved. Decision-metadata UPDATEs during
-- AWAITING_APPROVAL remain allowed via decide_clause because
-- that path UPDATEs decision/decided_by/decided_at — never
-- draft_id, never the row's existence.
CREATE TRIGGER IF NOT EXISTS trg_freeze_clauses_after_submit_delete
BEFORE DELETE ON contract_clauses
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE draft_id = OLD.draft_id
      AND status != 'draft'
)
BEGIN
    SELECT RAISE(ABORT, 'cannot delete clauses once parent draft is submitted (status != draft)');
END;

-- Codex M-26 v8 review fix: v7 froze terminal-draft clause UPDATE
-- and DELETE but not INSERT. v8 added the symmetric BEFORE INSERT
-- trigger to fully freeze clauses once the parent draft is
-- terminal: no UPDATE, no DELETE, no INSERT.
--
-- Codex M-26 v11 review fix: v8's INSERT trigger only blocked
-- terminal parents. During AWAITING_APPROVAL, direct SQL could
-- still INSERT a forged 'decision=approved' clause that satisfied
-- the v10 clause CHECK; approve_draft saw a fully-approved
-- clause set and let the draft transition to APPROVED. v11
-- expands the trigger to fire on any non-DRAFT parent.
CREATE TRIGGER IF NOT EXISTS trg_freeze_clauses_after_submit_insert
BEFORE INSERT ON contract_clauses
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE draft_id = NEW.draft_id
      AND status != 'draft'
)
BEGIN
    SELECT RAISE(ABORT, 'cannot insert clauses once parent draft is submitted (status != draft)');
END;

-- Codex M-26 v13 review fix: new clauses must be inserted in
-- the PENDING decision state. The clause CHECK only validates
-- shape (decision='approved' with decided_by/decided_at is a
-- valid row), and the after-submit INSERT freeze only fires on
-- non-draft parents — so direct SQL could INSERT a pre-approved
-- clause into a DRAFT parent. submit_for_approval then sees
-- a clause set that's already all-approved and approve_draft
-- accepts it. v14 closes the gap by requiring INSERT-time
-- decision='pending'; decisions are recorded only via decide_clause.
CREATE TRIGGER IF NOT EXISTS trg_clause_insert_must_be_pending
BEFORE INSERT ON contract_clauses
FOR EACH ROW
WHEN NEW.decision != 'pending'
BEGIN
    SELECT RAISE(ABORT, 'new clauses must be inserted with decision=pending; decisions are recorded via decide_clause');
END;

-- Codex M-26 v11 review fix: clause draft_id moves are blocked
-- when EITHER OLD.draft_id or NEW.draft_id points at a non-DRAFT
-- parent. This closes the v10 bypass where direct SQL could move
-- a rejected clause off an AWAITING_APPROVAL parent into another
-- non-terminal draft.
--
-- The terminal-update trigger (above) already blocks all UPDATEs
-- on terminal-parent clauses including draft_id changes; this
-- trigger fills the AWAITING_APPROVAL gap. Decision-metadata
-- UPDATEs by decide_clause still pass because they don't change
-- draft_id.
CREATE TRIGGER IF NOT EXISTS trg_lock_clause_draft_id_after_submit
BEFORE UPDATE OF draft_id ON contract_clauses
FOR EACH ROW
WHEN OLD.draft_id != NEW.draft_id
     AND EXISTS (
         SELECT 1 FROM contract_drafts
         WHERE (draft_id = OLD.draft_id OR draft_id = NEW.draft_id)
           AND status != 'draft'
     )
BEGIN
    SELECT RAISE(ABORT, 'cannot move clauses to or from a submitted contract (status != draft)');
END;

-- Codex M-26 v9 review fix: v8 didn't freeze contract_drafts
-- rows after terminal status. Direct SQL could mutate `title`,
-- `counterparty_name`, `audit_run_id`, `kind` etc. on an APPROVED
-- draft and `assert_approved_for_send` still passed because it
-- only validates status. Terminal drafts must be FULLY frozen:
-- once a draft is APPROVED or REJECTED, no field on the row can
-- change. The transition trigger handles the status column path;
-- this trigger handles non-status mutation paths.
CREATE TRIGGER IF NOT EXISTS trg_freeze_drafts_on_terminal
BEFORE UPDATE ON contract_drafts
FOR EACH ROW
WHEN OLD.status IN ('approved', 'rejected')
BEGIN
    SELECT RAISE(ABORT, 'cannot modify a terminal contract draft (approved or rejected) — terminal rows are immutable');
END;

-- Symmetric: terminal drafts cannot be deleted either. Once
-- approved, the row is part of the SOC2 audit trail and cannot
-- be erased.
CREATE TRIGGER IF NOT EXISTS trg_freeze_drafts_delete_on_terminal
BEFORE DELETE ON contract_drafts
FOR EACH ROW
WHEN OLD.status IN ('approved', 'rejected')
BEGIN
    SELECT RAISE(ABORT, 'cannot delete a terminal contract draft (approved or rejected)');
END;

-- Codex M-26 v10 review fix: clause body/title/evidence are
-- IMMUTABLE after creation. v9 allowed direct SQL to rewrite a
-- decided clause's body/title between submit and final approval,
-- so the shipped contract differed from what the clause reviewer
-- signed off on. There is no public "edit clause body" API; once
-- a clause is added, only its decision metadata can change (via
-- decide_clause). Body/title/evidence_ids/claim_ids are frozen
-- from INSERT-time onward.
CREATE TRIGGER IF NOT EXISTS trg_clause_content_immutable
BEFORE UPDATE ON contract_clauses
FOR EACH ROW
WHEN NEW.title != OLD.title
     OR NEW.body != OLD.body
     OR NEW.evidence_ids_json != OLD.evidence_ids_json
     OR NEW.claim_ids_json != OLD.claim_ids_json
BEGIN
    SELECT RAISE(ABORT, 'clause title/body/evidence are immutable after creation — only decision metadata may change via decide_clause');
END;

-- Codex M-26 v12 review fix: v11 still allowed direct SQL to
-- mutate clause decision fields without writing a corresponding
-- contract_decision_log row, so a forged decide_clause-equivalent
-- left no audit trail. The CHECK + content-immutability triggers
-- accepted canonical 'approved' metadata so approve_draft saw an
-- all-approved clause set even though no review actually happened.
--
-- v12 closes this with two triggers:
--
-- 1) trg_log_clause_decision_change (AFTER UPDATE): every clause
--    decision change writes a contract_decision_log row
--    automatically. Direct SQL bypassing decide_clause still
--    leaves an audit trail. The legitimate decide_clause path
--    drops its manual log INSERT to avoid duplicates — the
--    trigger is the single source of truth for decision-log
--    rows on clauses.
--
-- 2) trg_block_decision_metadata_drift (BEFORE UPDATE): blocks
--    UPDATEs that change decision metadata (decided_by /
--    decided_at / decision_notes) without changing decision
--    itself. Once a clause's decision is recorded, its
--    attribution is immutable — only re-deciding via decide_clause
--    can change who/when/why.
CREATE TRIGGER IF NOT EXISTS trg_log_clause_decision_change
AFTER UPDATE ON contract_clauses
FOR EACH ROW
WHEN OLD.decision != NEW.decision
BEGIN
    INSERT INTO contract_decision_log (
        draft_id, clause_id, actor_user_id,
        from_state, to_state, rationale, created_at
    ) VALUES (
        NEW.draft_id, NEW.clause_id, NEW.decided_by,
        OLD.decision, NEW.decision, NEW.decision_notes,
        NEW.decided_at
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_block_decision_metadata_drift
BEFORE UPDATE ON contract_clauses
FOR EACH ROW
WHEN OLD.decision = NEW.decision
     AND (
         (OLD.decided_by IS NOT NEW.decided_by
              AND (OLD.decided_by IS NULL OR NEW.decided_by IS NULL
                   OR OLD.decided_by != NEW.decided_by))
         OR (OLD.decided_at IS NOT NEW.decided_at
              AND (OLD.decided_at IS NULL OR NEW.decided_at IS NULL
                   OR OLD.decided_at != NEW.decided_at))
         OR (OLD.decision_notes IS NOT NEW.decision_notes
              AND (OLD.decision_notes IS NULL
                   OR NEW.decision_notes IS NULL
                   OR OLD.decision_notes != NEW.decision_notes))
     )
BEGIN
    SELECT RAISE(ABORT, 'cannot mutate clause decision metadata without a decision change — re-decide via decide_clause to retag attribution');
END;

-- Codex M-26 v13 review fix: symmetric to v12's clause auto-log.
-- v12 closed the audit-trail gap on contract_clauses but left
-- contract_drafts unprotected — direct SQL UPDATE flipping
-- draft status (from awaiting_approval to approved with valid
-- CHECK fields + non-self approver) bypassed `_perform_*`
-- helpers and left no contract_decision_log row for the
-- transition. v13 auto-logs all status transitions on drafts.
--
-- The legitimate `_perform_submit` / `_perform_approve` /
-- `_perform_reject` helpers drop their manual log INSERT (the
-- trigger is now the single source of truth for status-change
-- log rows). create_draft's "created" log entry is independent
-- (an INSERT, not an UPDATE) and stays.
--
-- Actor selection logic mirrors the legitimate flow:
--   awaiting_approval target  -> submitter_user_id
--   approved target           -> approved_by (set in same UPDATE)
--   rejected target           -> rejected_by (set in same UPDATE)
CREATE TRIGGER IF NOT EXISTS trg_log_draft_status_change
AFTER UPDATE OF status ON contract_drafts
FOR EACH ROW
WHEN OLD.status != NEW.status
BEGIN
    INSERT INTO contract_decision_log (
        draft_id, clause_id, actor_user_id,
        from_state, to_state, rationale, created_at
    ) VALUES (
        NEW.draft_id, NULL,
        CASE
            WHEN NEW.status = 'awaiting_approval'
                THEN NEW.submitter_user_id
            WHEN NEW.status = 'approved'
                THEN NEW.approved_by
            WHEN NEW.status = 'rejected'
                THEN NEW.rejected_by
            ELSE NEW.submitter_user_id
        END,
        OLD.status, NEW.status,
        NEW.decision_rationale,
        NEW.updated_at
    );
END;
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ContractDraftStore:
    """SQLite-backed contract-draft registry.

    Authorization posture: the store enforces cross-tenant
    isolation (every read/write is org-scoped), but does NOT
    validate role. The endpoint layer must gate on owner/admin
    role for `submit_for_approval` / `approve_draft` /
    `reject_draft` so a regular member cannot self-approve their
    own contract drafts.

    Codex M-26 v6 review (structural refactor): the lifecycle
    transition surface is now three hardcoded private helpers
    (`_perform_submit`, `_perform_approve`, `_perform_reject`),
    one per legal edge. There is no parameterized helper that
    could be invoked with a malicious (to_state, from_states,
    mark_decided, set_approver, set_rejecter) tuple. Direct
    callers reaching for the underscore-prefixed methods STILL
    cannot violate state-machine invariants, because the legal-
    edge enforcement is hardcoded into each helper rather than
    being a runtime parameter check.
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
        # Codex M-26 v16 review fix: with `recursive_triggers` OFF
        # (SQLite default), `INSERT OR REPLACE` / `REPLACE INTO`
        # deletes + reinserts WITHOUT firing BEFORE DELETE triggers.
        # That bypassed v15's `trg_decision_log_no_delete` and let
        # an attacker rewrite forged log rows via REPLACE. Turning
        # the PRAGMA ON makes the implicit DELETE phase fire the
        # trigger, closing the v15-on-v15 bypass.
        conn.execute("PRAGMA recursive_triggers = ON")
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
                    "SELECT c.*, d.status AS draft_status "
                    "FROM contract_clauses c "
                    "JOIN contract_drafts d ON c.draft_id = d.draft_id "
                    "WHERE c.clause_id = ? AND d.org_id = ?",
                    (clause_id, org_id),
                ).fetchone()
                if clause_row is None:
                    raise ContractDraftStateError(
                        f"clause {clause_id!r} is not accessible "
                        f"to this caller"
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
                # Codex M-26 v12: trg_log_clause_decision_change
                # writes the contract_decision_log row automatically
                # whenever a clause's decision changes. We removed
                # the manual INSERT here so the trigger is the
                # single source of truth — direct-SQL bypasses also
                # auto-log this way, closing the v11 audit-trail
                # gap.
                conn.execute(
                    "UPDATE contract_clauses SET decision = ?, "
                    "decided_by = ?, decision_notes = ?, "
                    "decided_at = ? WHERE clause_id = ?",
                    (
                        decision.value, approver_user_id.strip(),
                        sanitized_notes, now, clause_id,
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
    # Draft lifecycle — public entry points
    # ------------------------------------------------------------------

    def submit_for_approval(
        self, *, draft_id: str, org_id: str, submitter_user_id: str,
    ) -> ContractDraft:
        """Move a DRAFT into AWAITING_APPROVAL. Refuses if the
        draft has zero clauses."""
        return self._perform_submit(
            draft_id=draft_id, org_id=org_id,
            submitter_user_id=submitter_user_id,
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
        return self._perform_approve(
            draft_id=draft_id, org_id=org_id,
            approver_user_id=approver_user_id, rationale=sanitized,
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
                "rejection rationale must be non-empty (LAW II — "
                "every rejection is part of the SOC2 audit trail)"
            )
        return self._perform_reject(
            draft_id=draft_id, org_id=org_id,
            rejecter_user_id=rejecter_user_id, rationale=sanitized,
        )

    # ------------------------------------------------------------------
    # Hardcoded transition helpers (Codex v6 structural refactor)
    # ------------------------------------------------------------------
    #
    # Each `_perform_*` helper enforces ONE specific edge of the
    # state machine. There is no parameter for "which transition"
    # or "which bookkeeping flags" — the helper names ARE the
    # transitions. A direct caller invoking `_perform_approve`
    # cannot, by parameter manipulation, achieve any other edge
    # because the helper only knows how to do its one job.
    #
    # All gate checks (state precondition, SOD, all-clauses-
    # approved, rationale, clause-count) live INSIDE each helper's
    # BEGIN IMMEDIATE so concurrent decide_clause / submit calls
    # cannot create TOCTOU races.

    def _perform_submit(
        self, *, draft_id: str, org_id: str, submitter_user_id: str,
    ) -> ContractDraft:
        """Hardcoded edge: DRAFT → AWAITING_APPROVAL.

        Preconditions enforced inside BEGIN IMMEDIATE:
          - draft accessible to org_id
          - draft.status == DRAFT
          - draft has ≥ 1 clause

        Invariants enforced (also at DB CHECK level):
          - approved_by, rejected_by, decision_rationale,
            decided_at remain NULL.
          - status flips to AWAITING_APPROVAL.

        This helper has NO parameter that could be used to set
        decision metadata on a submitted draft. The v5 bypass
        `_transition_draft(to_state=AWAITING_APPROVAL,
        mark_decided=True, set_approver=True)` is structurally
        impossible here — there is no `mark_decided` or
        `set_approver` parameter.
        """
        if not submitter_user_id.strip():
            raise ContractDraftStateError(
                "submitter_user_id must be non-empty"
            )
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM contract_drafts "
                    "WHERE draft_id = ? AND org_id = ?",
                    (draft_id, org_id),
                ).fetchone()
                if row is None:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is not accessible "
                        f"to this caller"
                    )
                current = ContractDraftStatus(row["status"])
                if current != ContractDraftStatus.DRAFT:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is in state "
                        f"{current.value!r}; submit_for_approval "
                        f"requires DRAFT state"
                    )
                clause_count = conn.execute(
                    "SELECT COUNT(*) AS n FROM contract_clauses "
                    "WHERE draft_id = ?",
                    (draft_id,),
                ).fetchone()
                if int(clause_count["n"]) == 0:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} has no clauses; "
                        f"cannot submit an empty contract for "
                        f"approval"
                    )
                # Codex M-26 v13: trg_log_draft_status_change
                # auto-logs the draft→awaiting_approval transition.
                # Manual INSERT removed to avoid duplicates.
                conn.execute(
                    "UPDATE contract_drafts SET status = ?, "
                    "updated_at = ? WHERE draft_id = ?",
                    (
                        ContractDraftStatus.AWAITING_APPROVAL.value,
                        now, draft_id,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        result = self.get_draft(draft_id=draft_id, org_id=org_id)
        if result is None:
            raise ContractDraftError(
                f"submit succeeded but cannot read back draft "
                f"{draft_id!r}"
            )
        return result

    def _perform_approve(
        self,
        *,
        draft_id: str,
        org_id: str,
        approver_user_id: str,
        rationale: str,
    ) -> ContractDraft:
        """Hardcoded edge: AWAITING_APPROVAL → APPROVED.

        Preconditions enforced inside BEGIN IMMEDIATE:
          - draft accessible to org_id
          - draft.status == AWAITING_APPROVAL
          - approver_user_id != draft.submitter_user_id (SOD)
          - rationale content-non-empty (sanitized via
            `_sanitize_notes`, which strips Cc/Cf and whitespace
            so zero-width-space-only rationales are caught)
          - all clauses APPROVED (no PENDING, no REJECTED)

        Invariants written:
          - status = 'approved'
          - approved_by = approver_user_id
          - decided_at = now
          - decision_rationale = rationale (sanitized)
          - rejected_by = NULL  (mutually exclusive with approved_by)

        DB CHECK constraint + state-transition trigger on
        contract_drafts mirror these invariants — even if this
        Python helper had a bug, an attempted UPDATE that violates
        the canonical APPROVED pattern OR the all-clauses-approved
        invariant would fail at the SQL layer.
        """
        if not approver_user_id.strip():
            raise ContractDraftStateError(
                "approver_user_id must be non-empty"
            )
        # Codex v7 review fix: use _sanitize_notes (strips Unicode
        # Cc/Cf categories + whitespace) instead of `.strip()`.
        # `.strip()` only strips whitespace, so a rationale of
        # "​" (zero-width space) was content-empty but passed
        # `not rationale.strip()`. v7 routes direct-helper callers
        # through the same sanitizer the public entry point uses.
        sanitized_rationale = _sanitize_notes(rationale)
        if sanitized_rationale is None:
            raise ContractDraftStateError(
                "approval rationale must be non-empty (LAW II — "
                "every approval is part of the SOC2 audit trail)"
            )
        rationale = sanitized_rationale
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM contract_drafts "
                    "WHERE draft_id = ? AND org_id = ?",
                    (draft_id, org_id),
                ).fetchone()
                if row is None:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is not accessible "
                        f"to this caller"
                    )
                current = ContractDraftStatus(row["status"])
                if current != ContractDraftStatus.AWAITING_APPROVAL:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is in state "
                        f"{current.value!r}; approve_draft requires "
                        f"AWAITING_APPROVAL state"
                    )
                if row["submitter_user_id"] == approver_user_id.strip():
                    raise ContractDraftStateError(
                        "the contract submitter cannot approve "
                        "their own draft (separation of duties — "
                        "every approval needs a second human "
                        "reviewer)"
                    )
                clause_rows = conn.execute(
                    "SELECT decision FROM contract_clauses "
                    "WHERE draft_id = ?",
                    (draft_id,),
                ).fetchall()
                if not clause_rows:
                    # Should be impossible — _perform_submit refuses
                    # empty drafts. If we land here, something
                    # corrupted the clause table after submit.
                    raise ContractDraftStateError(
                        "cannot approve draft: no clauses (this "
                        "should be impossible — submit_for_approval "
                        "refuses empty drafts)"
                    )
                decisions = {
                    ClauseDecision(r["decision"]) for r in clause_rows
                }
                if ClauseDecision.PENDING in decisions:
                    raise ContractDraftStateError(
                        "cannot approve draft: at least one clause "
                        "is still PENDING; decide every clause "
                        "before approving"
                    )
                if ClauseDecision.REJECTED in decisions:
                    raise ContractDraftStateError(
                        "cannot approve draft: at least one clause "
                        "is REJECTED; remove or replace it before "
                        "approving"
                    )
                # Codex M-26 v13: trg_log_draft_status_change
                # auto-logs the awaiting_approval→approved
                # transition. Manual INSERT removed.
                conn.execute(
                    "UPDATE contract_drafts SET "
                    "status = ?, updated_at = ?, decided_at = ?, "
                    "decision_rationale = ?, "
                    "approved_by = ?, rejected_by = NULL "
                    "WHERE draft_id = ?",
                    (
                        ContractDraftStatus.APPROVED.value,
                        now, now, rationale,
                        approver_user_id.strip(), draft_id,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        result = self.get_draft(draft_id=draft_id, org_id=org_id)
        if result is None:
            raise ContractDraftError(
                f"approve succeeded but cannot read back draft "
                f"{draft_id!r}"
            )
        return result

    def _perform_reject(
        self,
        *,
        draft_id: str,
        org_id: str,
        rejecter_user_id: str,
        rationale: str,
    ) -> ContractDraft:
        """Hardcoded edge: AWAITING_APPROVAL → REJECTED.

        Preconditions enforced inside BEGIN IMMEDIATE:
          - draft accessible to org_id
          - draft.status == AWAITING_APPROVAL
          - rationale content-non-empty (sanitized via
            `_sanitize_notes`)

        Invariants written:
          - status = 'rejected'
          - rejected_by = rejecter_user_id
          - decided_at = now
          - decision_rationale = rationale (sanitized)
          - approved_by = NULL  (mutually exclusive with rejected_by)
        """
        if not rejecter_user_id.strip():
            raise ContractDraftStateError(
                "rejecter_user_id must be non-empty"
            )
        # Codex v7 review fix: use _sanitize_notes (see _perform_approve
        # rationale check for context).
        sanitized_rationale = _sanitize_notes(rationale)
        if sanitized_rationale is None:
            raise ContractDraftStateError(
                "rejection rationale must be non-empty (LAW II — "
                "every rejection is part of the SOC2 audit trail)"
            )
        rationale = sanitized_rationale
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM contract_drafts "
                    "WHERE draft_id = ? AND org_id = ?",
                    (draft_id, org_id),
                ).fetchone()
                if row is None:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is not accessible "
                        f"to this caller"
                    )
                current = ContractDraftStatus(row["status"])
                if current != ContractDraftStatus.AWAITING_APPROVAL:
                    raise ContractDraftStateError(
                        f"draft {draft_id!r} is in state "
                        f"{current.value!r}; reject_draft requires "
                        f"AWAITING_APPROVAL state"
                    )
                # Codex M-26 v13: trg_log_draft_status_change
                # auto-logs the awaiting_approval→rejected
                # transition. Manual INSERT removed.
                conn.execute(
                    "UPDATE contract_drafts SET "
                    "status = ?, updated_at = ?, decided_at = ?, "
                    "decision_rationale = ?, "
                    "rejected_by = ?, approved_by = NULL "
                    "WHERE draft_id = ?",
                    (
                        ContractDraftStatus.REJECTED.value,
                        now, now, rationale,
                        rejecter_user_id.strip(), draft_id,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        result = self.get_draft(draft_id=draft_id, org_id=org_id)
        if result is None:
            raise ContractDraftError(
                f"reject succeeded but cannot read back draft "
                f"{draft_id!r}"
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
