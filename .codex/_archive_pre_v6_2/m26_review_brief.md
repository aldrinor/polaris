M-26 v1 (semi-automated contract drafting) — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-26 ships the semi-automated contract drafting substrate per
FINAL_PLAN Phase C deliverable #3:
  Semi-automated contract drafting with mandatory human approval
  before customer-facing.

Out of scope for v1: templating engine (DOCX/PDF render),
LLM-generated draft text, counterparty workflows. v1 is the
storage substrate + the FINAL_PLAN gate.

## What changed in v1 (commit 7e0a4ee)

New module: `src/polaris_graph/audit_ir/contract_draft_store.py`

Tables: contract_drafts, contract_clauses, contract_decision_log.
Closed enums: ContractDraftStatus / ClauseDecision / ContractKind.

State machine:
  DRAFT --add_clause()--> DRAFT
  DRAFT --submit_for_approval()--> AWAITING_APPROVAL
  AWAITING_APPROVAL --decide_clause()--> AWAITING_APPROVAL
                   --approve_draft()--> APPROVED
                   --reject_draft()--> REJECTED

approve_draft enforcement:
  - Every clause must be APPROVED (no PENDING / REJECTED)
  - Submitter cannot approve their own draft (separation of
    duties — every approval needs a second human)
  - Rationale required (LAW II — SOC2 audit trail)
  - Clause REJECT requires non-empty notes

THE FINAL_PLAN GATE:
  assert_approved_for_send(draft_id, org_id) raises
  ContractApprovalGateError unless draft is APPROVED. Every
  downstream code path that sends/exports/renders a contract
  MUST call this first. v1 surfaces it; the renderer + delivery
  code is wired separately.

Cross-tenant invariants enforced throughout:
  - Every method takes org_id and SQL-filters on it
  - Cross-org reads return None / [] (no existence leak)
  - Cross-org writes raise

Tests (31): creation, clause management, submit + decide flow,
FINAL_PLAN approval gate, customer-facing send gate (5 tests
including cross-org), cross-tenant isolation, decision audit
log, serialization.

## Your job

Verdict on M-26 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **Approval-gate bypass.** Can a draft reach APPROVED status
   via any path other than approve_draft()? Can
   assert_approved_for_send pass on a non-APPROVED draft?
2. **Separation-of-duties bypass.** Can the submitter
   eventually approve via re-creation, multi-account games,
   etc.? My read: store enforces submitter != approver per draft;
   org-level prevention of one-person-orgs is the endpoint's
   job.
3. **Clause-rejection drift.** Can a draft reach APPROVED with
   a REJECTED clause if the rejection was already overruled
   somewhere? My read: no — approve_draft re-reads all clauses
   and refuses if ANY are REJECTED.
4. **Decision-log integrity.** No public delete path. Source
   contains no UPDATE/DELETE on contract_decision_log. Confirm?
5. **Audit-IR back-link integrity.** evidence_ids/claim_ids are
   stored as JSON-encoded TEXT, not foreign keys. A draft can
   reference non-existent IDs. Defensible (denormalized for
   ergonomics) or should we validate at clause-add time? My
   read: defer to the runner integration in M-26 v2 — the
   storage layer doesn't have the audit_run_id loaded.
6. **Anything else worth flagging before M-26 locks.**

If GREEN, M-26 v1 substrate locks. The renderer + LLM drafter
ship in v2.

## Output

Write to `outputs/codex_findings/m26_review/findings.md`:

```markdown
# Codex review of M-26 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Approval gate
- [defensible / list bypass paths]

## Separation of duties
- [defensible / list bypass paths]

## Clause-rejection drift
- [defensible / list issues]

## Final word
GREEN to lock M-26 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
