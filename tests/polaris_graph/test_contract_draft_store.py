"""Tests for src/polaris_graph/audit_ir/contract_draft_store.py (M-26).

v6 structural refactor: the lifecycle transition surface is now
three hardcoded private helpers (`_perform_submit`,
`_perform_approve`, `_perform_reject`), one per legal edge.
There is no parameterized `_transition_draft` helper. Plus
DB-level CHECK constraints encode the SOC2 audit-trail invariants
so direct SQL UPDATE attempts that violate them fail at the SQL
layer.

Tests are organized:
  - Public-API happy paths
  - Per-clause approval flow
  - The FINAL_PLAN gate (assert_approved_for_send)
  - Cross-tenant isolation
  - Decision audit log
  - Direct-call attacks on the new `_perform_*` helpers
  - Confirmation that the v1..v5 parameterized helper is GONE
  - DB CHECK constraint enforcement
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.contract_draft_store import (
    ClauseDecision,
    ContractApprovalGateError,
    ContractDraft,
    ContractDraftStateError,
    ContractDraftStatus,
    ContractDraftStore,
    ContractKind,
    clause_to_dict,
    draft_to_dict,
)


@pytest.fixture
def store(tmp_path: Path) -> ContractDraftStore:
    return ContractDraftStore(tmp_path / "contracts.sqlite")


def _create_basic(
    store: ContractDraftStore,
    *,
    org_id: str = "org_a",
    submitter: str = "usr_alice",
    audit_run_id: str = "run_v3",
) -> ContractDraft:
    return store.create_draft(
        org_id=org_id, workspace_id="ws_a",
        submitter_user_id=submitter, audit_run_id=audit_run_id,
        kind=ContractKind.MSA,
        title="MSA with Acme Corp",
        counterparty_name="Acme Corp",
    )


def _add_clause(
    store: ContractDraftStore, draft, *,
    title: str = "Limitation of Liability",
    body: str = "Liability is limited to fees paid in the prior 12 months.",
    org_id: str = "org_a",
    evidence_ids: tuple[str, ...] = ("ev_a",),
    claim_ids: tuple[str, ...] = ("c1",),
):
    return store.add_clause(
        draft_id=draft.draft_id, org_id=org_id,
        title=title, body=body,
        evidence_ids=evidence_ids, claim_ids=claim_ids,
    )


# ---------------------------------------------------------------------------
# Draft creation
# ---------------------------------------------------------------------------


def test_create_draft_lands_in_draft_state(store: ContractDraftStore) -> None:
    d = _create_basic(store)
    assert d.draft_id.startswith("ctr_")
    assert d.status == ContractDraftStatus.DRAFT
    assert d.kind == ContractKind.MSA
    assert d.audit_run_id == "run_v3"


def test_create_draft_rejects_empty_audit_run(
    store: ContractDraftStore,
) -> None:
    """Every contract draft must be anchored to a verified audit
    run — that's the back-link the FINAL_PLAN's "semi-automated"
    framing rests on."""
    with pytest.raises(ContractDraftStateError, match="audit_run_id"):
        store.create_draft(
            org_id="org_a", workspace_id="ws_a",
            submitter_user_id="alice", audit_run_id="",
            kind=ContractKind.MSA, title="x",
            counterparty_name="y",
        )


def test_create_draft_rejects_non_enum_kind(
    store: ContractDraftStore,
) -> None:
    with pytest.raises(ContractDraftStateError, match="kind"):
        store.create_draft(
            org_id="org_a", workspace_id="ws_a",
            submitter_user_id="alice", audit_run_id="r",
            kind="msa",  # type: ignore[arg-type]
            title="x", counterparty_name="y",
        )


# ---------------------------------------------------------------------------
# Clause management
# ---------------------------------------------------------------------------


def test_add_clause_succeeds_in_draft_state(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    assert c.clause_id.startswith("cls_")
    assert c.decision == ClauseDecision.PENDING
    assert c.evidence_ids == ("ev_a",)


def test_add_clause_blocked_after_submit(
    store: ContractDraftStore,
) -> None:
    """Adding clauses to an AWAITING_APPROVAL draft would let the
    submitter slip new prose past the reviewer."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="DRAFT state"):
        _add_clause(store, d, title="Backdoor clause")


def test_list_clauses_returns_oldest_first(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c1 = _add_clause(store, d, title="Clause 1")
    c2 = _add_clause(store, d, title="Clause 2")
    c3 = _add_clause(store, d, title="Clause 3")
    listed = store.list_clauses(draft_id=d.draft_id, org_id="org_a")
    assert [c.clause_id for c in listed] == [
        c1.clause_id, c2.clause_id, c3.clause_id,
    ]


# ---------------------------------------------------------------------------
# Submit + decide flow
# ---------------------------------------------------------------------------


def test_submit_requires_at_least_one_clause(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    with pytest.raises(ContractDraftStateError, match="no clauses"):
        store.submit_for_approval(
            draft_id=d.draft_id, org_id="org_a",
            submitter_user_id="usr_alice",
        )


def test_submit_transitions_to_awaiting_approval(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    _add_clause(store, d)
    submitted = store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    assert submitted.status == ContractDraftStatus.AWAITING_APPROVAL
    # Decision metadata stays NULL on a submitted draft (LAW II).
    assert submitted.approved_by is None
    assert submitted.rejected_by is None
    assert submitted.decision_rationale is None
    assert submitted.decided_at is None


def test_decide_clause_blocked_in_draft_state(
    store: ContractDraftStore,
) -> None:
    """Per-clause decisions are only valid AFTER submission for
    approval."""
    d = _create_basic(store)
    c = _add_clause(store, d)
    with pytest.raises(ContractDraftStateError, match="AWAITING_APPROVAL"):
        store.decide_clause(
            clause_id=c.clause_id, org_id="org_a",
            approver_user_id="bob", decision=ClauseDecision.APPROVED,
        )


def test_decide_clause_pending_value_rejected(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="PENDING"):
        store.decide_clause(
            clause_id=c.clause_id, org_id="org_a",
            approver_user_id="bob",
            decision=ClauseDecision.PENDING,
        )


def test_clause_rejection_requires_notes(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="notes"):
        store.decide_clause(
            clause_id=c.clause_id, org_id="org_a",
            approver_user_id="bob",
            decision=ClauseDecision.REJECTED, notes="",
        )


def test_clause_approve_records_decider(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    decided = store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    assert decided.decision == ClauseDecision.APPROVED
    assert decided.decided_by == "bob"
    assert decided.decision_notes == "ok"


# ---------------------------------------------------------------------------
# The FINAL_PLAN gate: mandatory human approval + separation of duties
# ---------------------------------------------------------------------------


def test_approve_draft_requires_all_clauses_approved(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c1 = _add_clause(store, d, title="Clause 1")
    _add_clause(store, d, title="Clause 2")
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    # Approve only one of the two clauses.
    store.decide_clause(
        clause_id=c1.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    # Approving the draft must fail because c2 is still PENDING.
    with pytest.raises(ContractDraftStateError, match="PENDING"):
        store.approve_draft(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="LGTM",
        )


def test_approve_draft_blocked_when_any_clause_rejected(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c1 = _add_clause(store, d, title="Good clause")
    c2 = _add_clause(store, d, title="Bad clause")
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c1.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.decide_clause(
        clause_id=c2.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.REJECTED,
        notes="this clause violates policy",
    )
    with pytest.raises(ContractDraftStateError, match="REJECTED"):
        store.approve_draft(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="LGTM",
        )


def test_approve_draft_separation_of_duties(
    store: ContractDraftStore,
) -> None:
    """A submitter cannot approve their own draft (SOC2: every
    approval needs a second human)."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="usr_alice",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(
        ContractDraftStateError, match="separation of duties",
    ):
        store.approve_draft(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="usr_alice",
            rationale="self-approving",
        )


def test_approve_draft_requires_rationale(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store.approve_draft(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="",
        )


def test_approve_draft_succeeds_with_all_clauses_approved(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    approved = store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob",
        rationale="all clauses reviewed against audit_run run_v3",
    )
    assert approved.status == ContractDraftStatus.APPROVED
    assert approved.approved_by == "bob"
    assert approved.rejected_by is None
    assert approved.decided_at is not None
    assert approved.decision_rationale is not None


def test_reject_draft_requires_rationale(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store.reject_draft(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob", rationale="",
        )


def test_reject_draft_writes_canonical_metadata(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    rejected = store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    assert rejected.status == ContractDraftStatus.REJECTED
    assert rejected.rejected_by == "bob"
    assert rejected.approved_by is None
    assert rejected.decided_at is not None
    assert rejected.decision_rationale == "not a fit"


# ---------------------------------------------------------------------------
# The customer-facing send gate
# ---------------------------------------------------------------------------


def test_assert_approved_for_send_blocks_unapproved(
    store: ContractDraftStore,
) -> None:
    """The FINAL_PLAN gate: only APPROVED drafts may be sent to a
    customer."""
    d = _create_basic(store)
    with pytest.raises(ContractApprovalGateError, match="customer-facing"):
        store.assert_approved_for_send(
            draft_id=d.draft_id, org_id="org_a",
        )


def test_assert_approved_for_send_blocks_awaiting(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractApprovalGateError):
        store.assert_approved_for_send(
            draft_id=d.draft_id, org_id="org_a",
        )


def test_assert_approved_for_send_blocks_rejected(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    with pytest.raises(ContractApprovalGateError):
        store.assert_approved_for_send(
            draft_id=d.draft_id, org_id="org_a",
        )


def test_assert_approved_for_send_passes_when_approved(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    # Must NOT raise.
    out = store.assert_approved_for_send(
        draft_id=d.draft_id, org_id="org_a",
    )
    assert out.status == ContractDraftStatus.APPROVED


def test_assert_approved_for_send_blocks_cross_org(
    store: ContractDraftStore,
) -> None:
    """Cross-org access on the send gate: org_b cannot use org_a's
    APPROVED draft."""
    d = _create_basic(store, org_id="org_a")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="ok",
    )
    with pytest.raises(ContractApprovalGateError, match="not accessible"):
        store.assert_approved_for_send(
            draft_id=d.draft_id, org_id="org_b",
        )


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_get_draft_returns_none_for_wrong_org(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store, org_id="org_a")
    assert store.get_draft(
        draft_id=d.draft_id, org_id="org_b",
    ) is None


def test_add_clause_rejects_cross_org(store: ContractDraftStore) -> None:
    d = _create_basic(store, org_id="org_a")
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store.add_clause(
            draft_id=d.draft_id, org_id="org_b",
            title="hostile clause", body="x",
        )


def test_decide_clause_rejects_cross_org(
    store: ContractDraftStore,
) -> None:
    """Cross-org decide_clause surfaces "not accessible to this
    caller" — same wording as unknown clause_id, no existence
    leak."""
    d = _create_basic(store, org_id="org_a")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store.decide_clause(
            clause_id=c.clause_id, org_id="org_b",
            approver_user_id="attacker",
            decision=ClauseDecision.APPROVED, notes="ok",
        )


def test_list_drafts_for_org_filters_tenant(
    store: ContractDraftStore,
) -> None:
    _create_basic(store, org_id="org_a")
    _create_basic(store, org_id="org_a")
    _create_basic(store, org_id="org_b")
    a = store.list_drafts_for_org(org_id="org_a")
    b = store.list_drafts_for_org(org_id="org_b")
    assert len(a) == 2
    assert len(b) == 1


# ---------------------------------------------------------------------------
# Decision audit log
# ---------------------------------------------------------------------------


def test_decision_log_records_lifecycle(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    log = store.list_decision_log(
        draft_id=d.draft_id, org_id="org_a",
    )
    transitions = [(r["from_state"], r["to_state"]) for r in log]
    assert (None, "draft") in transitions
    assert ("draft", "awaiting_approval") in transitions
    assert ("pending", "approved") in transitions
    assert ("awaiting_approval", "approved") in transitions


def test_decision_log_org_scoped(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store, org_id="org_a")
    cross = store.list_decision_log(
        draft_id=d.draft_id, org_id="org_b",
    )
    assert cross == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_draft_to_dict_round_trips(store: ContractDraftStore) -> None:
    d = _create_basic(store)
    payload = draft_to_dict(d)
    assert payload["draft_id"] == d.draft_id
    assert payload["status"] == "draft"
    assert payload["kind"] == "msa"


def test_clause_to_dict_round_trips(store: ContractDraftStore) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    payload = clause_to_dict(c)
    assert payload["clause_id"] == c.clause_id
    assert payload["evidence_ids"] == ["ev_a"]
    assert payload["decision"] == "pending"


# ---------------------------------------------------------------------------
# Codex M-26 v6 structural refactor: the parameterized helper is GONE
# ---------------------------------------------------------------------------


def test_v6_no_parameterized_transition_helper(
    store: ContractDraftStore,
) -> None:
    """v1..v5 had a parameterized `_transition_draft(to_state,
    from_states, mark_decided, set_approver, set_rejecter)` helper
    that proved to have a combinatorial bypass surface. Each round
    of Codex review found a new (parameter, value) tuple that
    escaped the invariants. v6 eliminates it.

    This test confirms `_transition_draft` is GONE — there is no
    parameterized surface for a malicious caller to exploit. The
    transition surface is now three hardcoded helpers, each
    enforcing exactly one edge of the state machine."""
    assert not hasattr(store, "_transition_draft"), (
        "_transition_draft must not exist in v6 — its parameter "
        "surface was the bypass surface. Use _perform_submit / "
        "_perform_approve / _perform_reject instead."
    )


# ---------------------------------------------------------------------------
# Direct attacks on the new _perform_submit helper
# ---------------------------------------------------------------------------


def test_direct_perform_submit_requires_clauses(
    store: ContractDraftStore,
) -> None:
    """_perform_submit refuses an empty draft. There is no
    parameter that could opt out of this check."""
    d = _create_basic(store)
    with pytest.raises(ContractDraftStateError, match="no clauses"):
        store._perform_submit(
            draft_id=d.draft_id, org_id="org_a",
            submitter_user_id="usr_alice",
        )


def test_direct_perform_submit_blocked_from_awaiting(
    store: ContractDraftStore,
) -> None:
    """_perform_submit only operates on DRAFT. Already-submitted
    drafts cannot be re-submitted."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="DRAFT state"):
        store._perform_submit(
            draft_id=d.draft_id, org_id="org_a",
            submitter_user_id="usr_alice",
        )


def test_direct_perform_submit_blocked_from_terminal(
    store: ContractDraftStore,
) -> None:
    """Terminal states (APPROVED / REJECTED) cannot be revived
    via _perform_submit. There is no `from_states` parameter."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store._perform_reject(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    # Direct attempt to "re-submit" a rejected draft.
    with pytest.raises(ContractDraftStateError, match="DRAFT state"):
        store._perform_submit(
            draft_id=d.draft_id, org_id="org_a",
            submitter_user_id="usr_alice",
        )


def test_direct_perform_submit_does_not_write_decision_metadata(
    store: ContractDraftStore,
) -> None:
    """The Codex M-26 v5 bypass: `_transition_draft(to_state=
    AWAITING_APPROVAL, mark_decided=True, set_approver=True)`
    wrote decision metadata onto a submitted draft. v6 has no
    such parameter — _perform_submit only flips status."""
    d = _create_basic(store)
    _add_clause(store, d)
    submitted = store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    assert submitted.status == ContractDraftStatus.AWAITING_APPROVAL
    assert submitted.approved_by is None
    assert submitted.rejected_by is None
    assert submitted.decision_rationale is None
    assert submitted.decided_at is None


def test_direct_perform_submit_cross_org_uniform_error(
    store: ContractDraftStore,
) -> None:
    """Cross-org and unknown draft_id surface the same error (no
    existence leak)."""
    d = _create_basic(store, org_id="org_a")
    _add_clause(store, d)
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._perform_submit(
            draft_id=d.draft_id, org_id="org_b",
            submitter_user_id="attacker",
        )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._perform_submit(
            draft_id="ctr_phantom", org_id="org_a",
            submitter_user_id="bob",
        )


# ---------------------------------------------------------------------------
# Direct attacks on the new _perform_approve helper
# ---------------------------------------------------------------------------


def test_direct_perform_approve_blocks_pending_clauses(
    store: ContractDraftStore,
) -> None:
    """_perform_approve enforces all-clauses-approved inside
    BEGIN IMMEDIATE."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    # Don't decide the clause — leave PENDING.
    with pytest.raises(ContractDraftStateError, match="PENDING"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob",
            rationale="bypass attempt",
        )


def test_direct_perform_approve_blocks_self_approval(
    store: ContractDraftStore,
) -> None:
    """SOD: submitter cannot self-approve, even via direct call."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(
        ContractDraftStateError, match="separation of duties",
    ):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="usr_alice",  # the submitter!
            rationale="self-approval bypass",
        )


def test_direct_perform_approve_blocks_empty_rationale(
    store: ContractDraftStore,
) -> None:
    """Rationale required even via direct call."""
    d = _create_basic(store)
    c = _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="",
        )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="   ",  # whitespace
        )


def test_direct_perform_approve_blocks_rejected_clause(
    store: ContractDraftStore,
) -> None:
    """The TOCTOU race Codex reproduced: a late
    decide_clause(REJECTED) landing between snapshot and
    transition. v6 re-reads clauses inside the lock."""
    d = _create_basic(store)
    c1 = _add_clause(store, d, title="Good")
    c2 = _add_clause(store, d, title="Bad")
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c1.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.decide_clause(
        clause_id=c2.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.REJECTED,
        notes="violates policy",
    )
    with pytest.raises(ContractDraftStateError, match="REJECTED"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob",
            rationale="bypassing the rejected clause",
        )


def test_direct_perform_approve_only_from_awaiting(
    store: ContractDraftStore,
) -> None:
    """_perform_approve refuses any state other than
    AWAITING_APPROVAL. There is no `from_states` parameter, so
    a caller can't pretend the draft is in AWAITING_APPROVAL when
    it isn't."""
    d = _create_basic(store)
    _add_clause(store, d)
    # Still in DRAFT — never submitted.
    with pytest.raises(ContractDraftStateError, match="AWAITING_APPROVAL"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob", rationale="skip approval queue",
        )


def test_direct_perform_approve_blocked_from_terminal(
    store: ContractDraftStore,
) -> None:
    """Terminal-state revival is structurally impossible: the
    state check rejects anything other than AWAITING_APPROVAL."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store._perform_reject(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    # Now in REJECTED. Try to resurrect to APPROVED.
    with pytest.raises(ContractDraftStateError, match="AWAITING_APPROVAL"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="alice", rationale="resurrect",
        )


def test_direct_perform_approve_cross_org_uniform_error(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store, org_id="org_a")
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_b",
            approver_user_id="attacker",
            rationale="cross-org bypass",
        )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._perform_approve(
            draft_id="ctr_phantom", org_id="org_a",
            approver_user_id="bob",
            rationale="phantom",
        )


def test_direct_perform_approve_writes_canonical_metadata(
    store: ContractDraftStore,
) -> None:
    """Even via direct call, _perform_approve writes the canonical
    APPROVED metadata pattern. There is no parameter to opt out
    of writing approved_by / decided_at / decision_rationale."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    approved = store._perform_approve(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    assert approved.status == ContractDraftStatus.APPROVED
    assert approved.approved_by == "bob"
    assert approved.rejected_by is None  # Mutually exclusive.
    assert approved.decided_at is not None
    assert approved.decision_rationale == "reviewed"


# ---------------------------------------------------------------------------
# Direct attacks on the new _perform_reject helper
# ---------------------------------------------------------------------------


def test_direct_perform_reject_requires_rationale(
    store: ContractDraftStore,
) -> None:
    """SOC2: every rejection has a non-empty rationale."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob", rationale="",
        )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob", rationale="   ",
        )


def test_direct_perform_reject_only_from_awaiting(
    store: ContractDraftStore,
) -> None:
    """_perform_reject refuses any state other than
    AWAITING_APPROVAL — DRAFT, APPROVED, REJECTED all blocked."""
    d = _create_basic(store)
    _add_clause(store, d)
    # In DRAFT.
    with pytest.raises(ContractDraftStateError, match="AWAITING_APPROVAL"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob", rationale="not yet submitted",
        )


def test_direct_perform_reject_blocked_from_terminal(
    store: ContractDraftStore,
) -> None:
    """Already-rejected drafts cannot be re-rejected (no double-
    rejection log entries)."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store._perform_reject(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    with pytest.raises(ContractDraftStateError, match="AWAITING_APPROVAL"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob", rationale="re-reject",
        )


def test_direct_perform_reject_cross_org_uniform_error(
    store: ContractDraftStore,
) -> None:
    d = _create_basic(store, org_id="org_a")
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_b",
            rejecter_user_id="attacker",
            rationale="cross-org",
        )


def test_direct_perform_reject_writes_canonical_metadata(
    store: ContractDraftStore,
) -> None:
    """Even via direct call, _perform_reject writes the canonical
    REJECTED metadata pattern."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    rejected = store._perform_reject(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    assert rejected.status == ContractDraftStatus.REJECTED
    assert rejected.rejected_by == "bob"
    assert rejected.approved_by is None  # Mutually exclusive.
    assert rejected.decided_at is not None
    assert rejected.decision_rationale == "not a fit"


# ---------------------------------------------------------------------------
# Codex M-26 v6 review: rationale validation must catch content-empty
# input (zero-width spaces, Cf chars), not just whitespace.
# ---------------------------------------------------------------------------


def test_perform_approve_rejects_zero_width_space_rationale(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v6: `_perform_approve` re-validated rationale
    with `.strip()`, which only strips whitespace. A rationale of
    "​" (zero-width space) was content-empty but passed
    `not rationale.strip()` because `.strip()` doesn't strip Cf
    characters. v7 routes through `_sanitize_notes`, which does."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob",
            rationale="​",  # zero-width space — content-empty
        )


def test_perform_reject_rejects_zero_width_space_rationale(
    store: ContractDraftStore,
) -> None:
    """Symmetric: `_perform_reject` rejection rationale must also
    use `_sanitize_notes`, not `.strip()`."""
    d = _create_basic(store)
    _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_reject(
            draft_id=d.draft_id, org_id="org_a",
            rejecter_user_id="bob",
            rationale="​‌‍",  # all Cf chars
        )


def test_perform_approve_rejects_unicode_format_only_rationale(
    store: ContractDraftStore,
) -> None:
    """Mixed Cf and whitespace must also be caught."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store._perform_submit(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._perform_approve(
            draft_id=d.draft_id, org_id="org_a",
            approver_user_id="bob",
            rationale=" ​ \t\n",  # whitespace + zero-width space
        )


# ---------------------------------------------------------------------------
# DB CHECK constraint enforcement (defense-in-depth)
#
# Each test sets up state where the SQL trigger PASSES so the CHECK
# constraint can fire on its specific invariant. (Triggers run before
# CHECK in SQLite; if both would catch a bypass, the trigger fires
# first with a different error message.)
# ---------------------------------------------------------------------------


def _approve_all_clauses(store, draft, *, org_id="org_a", approver="bob"):
    """Helper: approve every clause on a draft so the all-clauses-
    approved trigger gate is satisfied."""
    for c in store.list_clauses(draft_id=draft.draft_id, org_id=org_id):
        store.decide_clause(
            clause_id=c.clause_id, org_id=org_id,
            approver_user_id=approver,
            decision=ClauseDecision.APPROVED, notes="ok",
        )


def test_db_check_blocks_approved_with_null_approver(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """LAW II SOC2 invariant: status='approved' with approved_by
    NULL violates the CHECK pattern. We set up all-clauses-approved
    state so the trigger gate passes and CHECK is the active layer."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Trigger requires NEW.approved_by != NEW.submitter_user_id;
        # we set approved_by='bob' (not 'usr_alice'). Trigger passes.
        # CHECK fails because rationale + decided_at are NULL.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_approved_with_empty_string_approver(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex v6 finding: CHECK only enforced IS NOT NULL — empty
    strings passed. v7 adds `length(approved_by) > 0`."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = '', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_approved_with_empty_rationale(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex v6 finding: empty-string decision_rationale must fail."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob', decision_rationale = '', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_approved_with_rejected_by_set(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """The CHECK enforces mutual exclusion: status='approved' with
    rejected_by NOT NULL is illegal."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob', rejected_by = 'bob', "
                "decision_rationale = 'r', decided_at = 0.0 "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_rejected_with_null_rejecter(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Symmetric invariant for REJECTED. Trigger passes for
    AWAITING→REJECTED with no clause requirements; CHECK catches
    NULL rejected_by."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'rejected' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_rejected_with_empty_rejecter(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex v6 finding: empty-string rejected_by must fail."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'rejected', "
                "rejected_by = '', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_draft_with_decision_metadata(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """A draft (not yet submitted) cannot carry decision metadata.
    UPDATE doesn't change status, so trigger doesn't fire — CHECK
    is the active defense."""
    d = _create_basic(store)
    _add_clause(store, d)
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                "UPDATE contract_drafts SET approved_by = 'bob' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_awaiting_with_decision_metadata(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """A submitted (AWAITING_APPROVAL) draft cannot carry decision
    metadata. The exact v5 bypass closed at SQL layer."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                "UPDATE contract_drafts SET approved_by = 'bob', "
                "decision_rationale = 'r', decided_at = 0.0 "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_db_check_blocks_invalid_status_value(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Any non-enum status value is rejected — by trigger
    ("illegal status value") or CHECK (no matching pattern)."""
    d = _create_basic(store)
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'cancelled' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


# ---------------------------------------------------------------------------
# Codex M-26 v7: SQL TRIGGERs encode cross-row invariants
# ---------------------------------------------------------------------------


def test_trigger_blocks_approved_with_pending_clauses(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex M-26 v6 finding: 'direct SQL can write canonical
    APPROVED metadata onto a draft whose clause rows are still
    PENDING; assert_approved_for_send then passes on an unreviewed
    draft.' v7 adds a SQL trigger validating all-clauses-approved
    before status='approved'."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    # Don't approve any clauses — they're still PENDING.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="not approved"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )
    # Crucially: assert_approved_for_send still refuses (the row
    # never landed in APPROVED state).
    with pytest.raises(ContractApprovalGateError):
        store.assert_approved_for_send(
            draft_id=d.draft_id, org_id="org_a",
        )


def test_trigger_blocks_approved_with_rejected_clauses(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Cannot approve a draft with any REJECTED clause."""
    d = _create_basic(store, submitter="usr_alice")
    c1 = _add_clause(store, d, title="Good")
    c2 = _add_clause(store, d, title="Bad")
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.decide_clause(
        clause_id=c1.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.APPROVED, notes="ok",
    )
    store.decide_clause(
        clause_id=c2.clause_id, org_id="org_a",
        approver_user_id="bob",
        decision=ClauseDecision.REJECTED, notes="violates policy",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="not approved"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_skip_to_approved_from_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """State-machine invariant at SQL layer: DRAFT → APPROVED is
    illegal (must go through AWAITING_APPROVAL)."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="awaiting_approval"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'bob', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_revert_awaiting_to_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """No transition into 'draft' is legal — terminal-state revival
    (and rewinding submitted) is blocked at SQL."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="draft"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'draft' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_revive_terminal_to_awaiting(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """REJECTED is terminal: cannot revert to AWAITING_APPROVAL.
    Blocked by either the transition trigger or the row-freeze
    trigger (v9) — whichever fires first. Both prevent the bypass."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE contract_drafts SET status = 'awaiting_approval', "
                "approved_by = NULL, rejected_by = NULL, "
                "decision_rationale = NULL, decided_at = NULL "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_self_approval_via_sql(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """SOD encoded at SQL layer: NEW.approved_by must not equal
    NEW.submitter_user_id."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="usr_alice")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="separation of duties"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'approved', "
                "approved_by = 'usr_alice', decision_rationale = 'r', "
                "decided_at = 0.0 WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_submit_empty_draft_via_sql(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Cannot transition to AWAITING_APPROVAL with zero clauses."""
    d = _create_basic(store)
    # No clauses added.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="empty draft"):
            conn.execute(
                "UPDATE contract_drafts SET status = 'awaiting_approval' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_insert_with_non_draft_status(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Direct SQL INSERT cannot create a row already in non-draft
    status — every draft must start in DRAFT."""
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="draft status"):
            conn.execute(
                "INSERT INTO contract_drafts (draft_id, org_id, "
                "workspace_id, submitter_user_id, audit_run_id, "
                "kind, title, counterparty_name, status, "
                "approved_by, decision_rationale, decided_at, "
                "created_at, updated_at) VALUES "
                "('ctr_evil', 'org_a', 'ws', 'alice', 'r', "
                "'msa', 't', 'cp', 'approved', 'bob', 'r', 0.0, "
                "0.0, 0.0)",
            )


def test_trigger_blocks_clause_modify_on_terminal_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Clauses are frozen after the parent draft reaches terminal
    status. A direct SQL UPDATE flipping a clause from approved to
    rejected after approval is blocked."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    # Draft now APPROVED. Direct SQL flipping the clause to
    # rejected would retroactively change what was reviewed.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "UPDATE contract_clauses SET decision = 'rejected' "
                "WHERE clause_id = ?",
                (c.clause_id,),
            )


def test_trigger_blocks_clause_delete_on_terminal_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Symmetric: clauses can't be deleted after terminal status."""
    d = _create_basic(store, submitter="usr_alice")
    c = _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "DELETE FROM contract_clauses WHERE clause_id = ?",
                (c.clause_id,),
            )


def test_trigger_blocks_clause_insert_on_terminal_draft_approved(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex M-26 v7 finding: 'direct SQL can INSERT a new row
    into contract_clauses after the parent draft is already
    approved. The row lands, list_clauses shows an added pending
    clause, assert_approved_for_send still passes.' v8 adds the
    symmetric BEFORE INSERT trigger."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    # Draft now APPROVED. Direct SQL INSERT of a new clause
    # would let an attacker stuff prose into the contract after
    # human review.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "INSERT INTO contract_clauses (clause_id, draft_id, "
                "title, body, decision, created_at) VALUES "
                "('cls_evil', ?, 'Backdoor', 'malicious', "
                "'pending', 0.0)",
                (d.draft_id,),
            )
    # And the clause list is unchanged.
    clauses = store.list_clauses(draft_id=d.draft_id, org_id="org_a")
    assert all(c.title != "Backdoor" for c in clauses)


def test_trigger_blocks_clause_insert_on_terminal_draft_rejected(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Symmetric: cannot INSERT clauses on a REJECTED draft either."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "INSERT INTO contract_clauses (clause_id, draft_id, "
                "title, body, decision, created_at) VALUES "
                "('cls_evil', ?, 'Late add', 'x', 'pending', 0.0)",
                (d.draft_id,),
            )


# ---------------------------------------------------------------------------
# Codex M-26 v9: tighten clause UPDATE freeze + freeze terminal drafts
# ---------------------------------------------------------------------------


def test_trigger_blocks_clause_move_off_terminal_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex M-26 v8 finding: v8's clause UPDATE freeze only checked
    NEW.draft_id, so direct SQL `UPDATE contract_clauses SET
    draft_id = <non-terminal>` moved a clause OFF a terminal draft.
    list_clauses(terminal_draft) showed the clause missing — i.e.
    the approved contract's clause set was modified after review.
    v9 checks both OLD.draft_id and NEW.draft_id."""
    # Set up: terminal draft (approved) + non-terminal draft.
    d_approved = _create_basic(
        store, submitter="usr_alice", audit_run_id="run_a",
    )
    c = _add_clause(store, d_approved)
    store.submit_for_approval(
        draft_id=d_approved.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d_approved, approver="bob")
    store.approve_draft(
        draft_id=d_approved.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    d_draft = _create_basic(
        store, submitter="usr_alice", audit_run_id="run_b",
    )
    # Direct SQL attempting to move clause off the approved draft.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "UPDATE contract_clauses SET draft_id = ? "
                "WHERE clause_id = ?",
                (d_draft.draft_id, c.clause_id),
            )
    # Clause is still on the approved draft.
    clauses = store.list_clauses(
        draft_id=d_approved.draft_id, org_id="org_a",
    )
    assert any(cc.clause_id == c.clause_id for cc in clauses)


def test_trigger_blocks_clause_move_onto_terminal_draft(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Symmetric: cannot move a clause INTO a terminal draft.
    The OR-check on (OLD, NEW) catches both directions."""
    d_approved = _create_basic(
        store, submitter="usr_alice", audit_run_id="run_a",
    )
    _add_clause(store, d_approved, title="real")
    store.submit_for_approval(
        draft_id=d_approved.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d_approved, approver="bob")
    store.approve_draft(
        draft_id=d_approved.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    d_draft = _create_basic(
        store, submitter="usr_alice", audit_run_id="run_b",
    )
    c_orphan = _add_clause(store, d_draft, title="orphan")
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal draft"):
            conn.execute(
                "UPDATE contract_clauses SET draft_id = ? "
                "WHERE clause_id = ?",
                (d_approved.draft_id, c_orphan.clause_id),
            )


def test_trigger_blocks_terminal_draft_metadata_mutation(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Codex M-26 v8 finding: 'contract_drafts has no terminal-row
    freeze for non-status updates, so direct SQL can mutate
    approved draft metadata (title, counterparty_name, etc.) and
    assert_approved_for_send still passes.' v9 adds a row-freeze
    trigger that fires on ANY update when OLD.status is terminal."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    # Terminal. Try to mutate non-status metadata via direct SQL.
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal contract draft"):
            conn.execute(
                "UPDATE contract_drafts SET title = 'BACKDOOR' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="terminal contract draft"):
            conn.execute(
                "UPDATE contract_drafts SET counterparty_name = 'Different Corp' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="terminal contract draft"):
            conn.execute(
                "UPDATE contract_drafts SET audit_run_id = 'run_xxx' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )
    # Re-read and confirm metadata unchanged.
    d_after = store.get_draft(draft_id=d.draft_id, org_id="org_a")
    assert d_after is not None
    assert d_after.title == "MSA with Acme Corp"
    assert d_after.counterparty_name == "Acme Corp"
    assert d_after.audit_run_id == "run_v3"


def test_trigger_blocks_terminal_draft_metadata_mutation_rejected(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Symmetric: REJECTED is also terminal."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal contract draft"):
            conn.execute(
                "UPDATE contract_drafts SET counterparty_name = 'Other' "
                "WHERE draft_id = ?",
                (d.draft_id,),
            )


def test_trigger_blocks_terminal_draft_delete(
    store: ContractDraftStore,
    tmp_path: Path,
) -> None:
    """Terminal drafts are part of the SOC2 audit trail. Direct SQL
    DELETE on an APPROVED row would erase the audit record."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    _approve_all_clauses(store, d, approver="bob")
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    with sqlite3.connect(tmp_path / "contracts.sqlite") as conn:
        with pytest.raises(sqlite3.IntegrityError, match="terminal contract draft"):
            conn.execute(
                "DELETE FROM contract_drafts WHERE draft_id = ?",
                (d.draft_id,),
            )
