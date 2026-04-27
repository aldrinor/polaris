# M-26 Contract Drafting — Threat Model & Defense Surface

**Status**: locked 2026-04-27 (Phase C complete)
**Module**: `src/polaris_graph/audit_ir/contract_draft_store.py`
**Tests**: `tests/polaris_graph/test_contract_draft_store.py` (109 tests)

---

## What this document is for

M-26 implements the FINAL_PLAN guarantee that **no contract draft can become customer-facing without human approval**. The substrate (`contract_draft_store.py`) shipped after 13 Codex audit rounds. This document records:

- What the substrate defends against (in scope)
- What it does NOT defend against (out of scope, by design)
- The complete defense-in-depth layering

Future contributors should read this BEFORE proposing changes that claim to "harden" the module further. Many candidate "hardenings" are out-of-scope per the threat model and would add complexity without security benefit.

---

## In-scope threats

The substrate defends against:

**Direct-SQL DML by callers without DDL privileges** on `contract_drafts` and `contract_clauses`:

- `INSERT` of malformed rows (status mismatches, decision-fields drift, pre-approved clauses)
- `UPDATE` that violates state-machine transitions, separation of duties, all-clauses-approved invariant, content immutability, attribution drift, or terminal-row immutability
- `DELETE` of terminal-state rows (audit-trail erasure)
- `UPDATE` that moves clauses across drafts to circumvent the all-clauses-approved gate
- `INSERT/UPDATE` that flips audit metadata (decision, decided_by, decided_at, decision_rationale, approved_by, rejected_by) without writing a `contract_decision_log` entry

These attacks are blocked at the SQL layer regardless of how the caller reached the database (compromised endpoint, internal misuse, etc.).

---

## Out-of-scope threats (by design)

The substrate does NOT defend against:

| Threat | Why out of scope | Defended by |
|---|---|---|
| **DDL operations** (`DROP TRIGGER`, `ALTER TABLE`, `ATTACH DATABASE`) | An attacker with DDL privileges can disable any CHECK or trigger. | OS-level access control on the SQLite file. Encrypted filesystem. Process isolation. |
| **Identity validation** (forged `decided_by`, `approved_by` user-id strings) | The SQL layer cannot validate that a user-id string corresponds to a real user. The substrate ensures every decision change leaves an auditable log row; if the actor string is forged, the forgery is itself in the audit trail. | M-15a auth substrate (orgs/users/roles). Anomaly detection on `contract_decision_log` entries (unknown actors, impossible timestamps, etc.). |
| **File-system tampering** (corrupt or replace the `.sqlite` file) | Attacker has bypassed the application entirely. | OS-level access control. File integrity monitoring. Backup/restore from known-good snapshots. |
| **Transaction-isolation exploits** | SQLite WAL + `BEGIN IMMEDIATE` handle in-process concurrency. Exotic exploits (e.g. concurrent process holding DB read lock during a partial transaction commit) are not addressable from inside the schema. | SQLite engine guarantees + the application's connection lifecycle. |
| **Cross-module data leaks** | M-26 only owns the contract-drafting tables. Joins or data flows into other modules (e.g. exporting an APPROVED draft via the audit bundle) are governed by those modules. | M-15b authz retrofit. M-16 audit bundle export gates. |

When evaluating a proposed "M-26 hardening", check whether the threat falls into one of the rows above. If it does, the right answer is documenting the assumption (or fixing the upstream module), not adding more triggers to `contract_draft_store.py`.

---

## Defense surface — what's actually in the schema

### `contract_drafts` table

| Operation | Defense | What it enforces |
|---|---|---|
| `INSERT` | `trg_validate_status_on_insert` | New rows must start in `'draft'` status |
| `UPDATE OF status` | `trg_validate_status_transition` | Closed transition table: only `(draft → awaiting_approval)`, `(awaiting_approval → approved)`, `(awaiting_approval → rejected)`. Plus all-clauses-approved + non-empty-clauses invariants + separation-of-duties. |
| `UPDATE OF status` (after) | `trg_log_draft_status_change` | Auto-writes `contract_decision_log` row for every status change |
| `UPDATE` (any column, terminal row) | `trg_freeze_drafts_on_terminal` | Approved/rejected rows are fully immutable |
| `DELETE` (terminal row) | `trg_freeze_drafts_delete_on_terminal` | Approved/rejected rows cannot be deleted |
| Per-row | `CHECK` constraint | Status-vs-decision-fields invariants: draft/awaiting_approval → all decision fields NULL; approved → approved_by + rationale + decided_at NOT NULL & non-empty, rejected_by NULL; symmetric for rejected. Mutual exclusion between approved_by and rejected_by. |

### `contract_clauses` table

| Operation | Defense | What it enforces |
|---|---|---|
| `INSERT` | `trg_freeze_clauses_after_submit_insert` | No INSERT once parent draft is submitted (status != `'draft'`) |
| `INSERT` | `trg_clause_insert_must_be_pending` | New clauses must have decision='pending'; decisions are recorded only via `decide_clause` |
| `UPDATE` (terminal parent) | `trg_freeze_clauses_on_terminal_update` | All updates blocked when parent is approved/rejected |
| `UPDATE OF draft_id` (non-draft parent) | `trg_lock_clause_draft_id_after_submit` | Clause can't move into or out of a non-draft parent (checks both OLD.draft_id and NEW.draft_id) |
| `UPDATE` (any column) | `trg_clause_content_immutable` | title/body/evidence_ids/claim_ids are immutable from INSERT-time onward |
| `UPDATE OF decision metadata` (decision unchanged) | `trg_block_decision_metadata_drift` | Cannot rewrite decided_by/decided_at/decision_notes without a real decision change |
| `UPDATE OF decision` (after) | `trg_log_clause_decision_change` | Auto-writes `contract_decision_log` row for every decision change |
| `DELETE` | `trg_freeze_clauses_after_submit_delete` | No DELETE once parent draft is submitted |
| Per-row | `CHECK` constraint | Decision-vs-audit-fields invariants: pending → decided_by/notes/decided_at all NULL; approved → decided_by + decided_at NOT NULL & non-empty; rejected → adds decision_notes NOT NULL & non-empty |

### `contract_decision_log` table (post-lock v15 — Codex doc audit finding; round-2 narrowing)

The original v1-v14 hardening cycle missed this table entirely. The doc claimed it was "append-only by design" but no SQL triggers actually enforced that; direct SQL UPDATE/DELETE on log rows worked, so a forged decision (created via the v11-class direct-SQL clause attack) could be erased after the v12/v13 auto-log triggers wrote the audit entry. The v15 post-lock fix narrows this:

| Operation | Defense | What it enforces |
|---|---|---|
| `INSERT` (append fresh row) | (no schema-level defense) | A direct-SQL caller can append forged log rows. Auto-log triggers + `create_draft` are the only intended write paths, but the schema cannot tell a trigger-driven INSERT from a direct-SQL one. Defense moves to identity validation (M-15a) + anomaly detection on log entries. |
| `INSERT OR REPLACE` / `REPLACE INTO` (overwrite by log_id) | `trg_decision_log_no_replace` | INSERT specifying a `log_id` that already exists raises. v17 fix — works regardless of `recursive_triggers` PRAGMA state. The v16 PRAGMA-on-store-connections approach was insufficient because an attacker opens their own connection at default-OFF; this trigger fires at the BEFORE INSERT phase, which is reached before the recursive-DELETE phase. |
| `UPDATE` | `trg_decision_log_no_update` | All UPDATEs raise; row attribution and content are immutable once written |
| `DELETE` | `trg_decision_log_no_delete` | All DELETEs raise; the audit trail cannot be erased |

**What v17 actually guarantees**: the audit trail is **non-destructible and non-rewritable** (UPDATE+DELETE+REPLACE-by-log_id blocked) but **not unforgeable** (direct INSERT of fresh rows still works). A forged decision via direct SQL on `contract_clauses` or `contract_drafts` writes a tamper-evident log entry naming the forged actor, and that entry cannot be erased, rewritten, or replaced. But an attacker with direct SQL access can also append fabricated log rows that don't correspond to any real state transition — those forgeries are catchable only by anomaly detection (unknown actors, impossible timestamps, log entries without matching `contract_drafts.status` history, etc.).

**Why not a stronger trigger on fresh-row INSERT?** Schema triggers cannot rely on caller-supplied connection state (PRAGMAs, session vars) or caller identity — the attacker controls those on their own connection. Triggers must enforce invariants from durable table state and row content (the NEW row's columns + queries against existing rows in the same database). The `trg_decision_log_no_replace` design works because the invariant ("no overwrite of an existing log_id") is checkable from `NEW.log_id` plus a query against existing log rows — both of which the schema can see deterministically. Distinguishing "legitimate trigger-driven append" from "forged direct INSERT" would require connection authentication or a session-tagged column, which SQLite/Python's per-statement authorizer hooks support but only at the application layer (and would need the application to enforce it on every connection — out of scope for this schema).

### Python layer (defense in depth above SQL)

- **Public API** (`create_draft`, `add_clause`, `decide_clause`, `submit_for_approval`, `approve_draft`, `reject_draft`, `assert_approved_for_send`): validates input, sanitizes via `_sanitize_notes` (strips Cc/Cf categories + whitespace), enforces cross-tenant isolation, dispatches to the appropriate `_perform_*` helper.
- **Hardcoded helpers** (`_perform_submit`, `_perform_approve`, `_perform_reject`): one per legal state-machine edge. No `to_state` parameter, no `from_states` parameter, no bookkeeping flags. The helper name *is* the transition. Eliminates the parameter-combination bypass surface entirely (this was the v6 structural refactor that converged the v1-v5 cycle).

### The FINAL_PLAN gate

- **`assert_approved_for_send`** — the single gate every customer-facing send code path must call before exporting/rendering/sending a draft. Raises `ContractApprovalGateError` if the draft is not in APPROVED state. Cross-org access also raises (no existence leak via different error wording).

---

## How to use this document

**Before adding a new trigger or CHECK to `contract_draft_store.py`:**

1. State the attack you're defending against in 1-2 sentences.
2. Check the in-scope/out-of-scope table above. If out-of-scope, the right fix is in another module or layer — don't add to this file.
3. If in-scope and not already covered, write the test FIRST (a failing direct-SQL repro), then add the defense.
4. Update this doc with the new defense in the appropriate row.

**Before claiming "M-26 has a bug":**

1. Reproduce the attack as a direct-SQL test in `test_contract_draft_store.py`.
2. Confirm it survives all four layers (public API, `_perform_*` helpers, CHECK, triggers).
3. **Test attacks against secondary tables too** — the auto-log triggers write to `contract_decision_log`; that table is itself a defense surface and must be checked. The v15 post-lock find was that the log table was unprotected even though the doc claimed it was append-only.
4. If the attack survives all that, the bug is real and a new revision (v18+) is warranted. Otherwise, the layers caught it — no change needed.

**Audit-trail integrity:**

- Every status/decision change writes a `contract_decision_log` row automatically (via auto-log triggers). Direct-SQL bypasses on contract_drafts/contract_clauses still leave a trace; that trace may have a forged actor string, but anomaly detection on the log + M-15a identity-validation catches forged actors.
- `contract_decision_log` is **non-destructible AND non-rewritable** but not unforgeable: `trg_decision_log_no_update` (v15) + `trg_decision_log_no_delete` (v15) + `trg_decision_log_no_replace` (v17) together block UPDATE, DELETE, and `INSERT OR REPLACE` (which would otherwise overwrite by primary-key conflict). **Direct-SQL INSERT of fresh rows to the log table is NOT schema-blocked** — see the contract_decision_log defense table for the constraint reasoning. Forged INSERTs that don't correspond to real state transitions are catchable only by anomaly detection at the process layer.
- Future contributors writing new audit-log tables should follow the same pattern: UPDATE/DELETE/REPLACE-by-PK blocked at schema level (the v17 BEFORE INSERT trigger pattern), fresh-row INSERT validation deferred to process layer (because SQLite trigger logic must work from durable table state and row content, not caller-controlled connection state or identity).

---

## Review history

13 Codex audit rounds, 14 commits:

- **v1** (DISAGREE): 4 parameter-surface bypasses on `_transition_draft`
- **v2-v5** (PARTIAL × 4): each round closed point bugs in the parameterized helper, each round found a new (parameter, value) tuple
- **v6** (advisor recommendation, structural refactor): replaced `_transition_draft(to_state, from_states, mark_decided, set_approver, set_rejecter)` with three concrete `_perform_*` helpers. Parameter surface eliminated. Plus initial DB CHECK constraints.
- **v7-v14** (PARTIAL × 8): each round closed an additional SQL-layer gap (length checks, OLD vs NEW.draft_id, terminal-row freeze, INSERT/DELETE symmetry, content immutability, decision-metadata drift, auto-log triggers, INSERT-must-be-pending). Each fix legitimate; pattern asymptoting per the second advisor consult.
- **v14** (locked): 109/109 tests, full Phase C suite green, threat-model boundary documented (this file).

The v6 advisor consult and the v12 advisor consult ("you're not converging — you're asymptoting") were the two pivotal decisions that shaped the final substrate.
