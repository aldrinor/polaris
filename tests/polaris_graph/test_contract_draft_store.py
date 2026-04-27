"""Tests for src/polaris_graph/audit_ir/contract_draft_store.py (M-26)."""

from __future__ import annotations

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
    c2 = _add_clause(store, d, title="Clause 2")
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
    """Codex M-26 v1 fix: cross-org decide_clause now surfaces
    "not accessible to this caller" — same wording as unknown
    clause_id, no existence leak."""
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


# ---------------------------------------------------------------------------
# Codex M-26 v1 review fixes
# ---------------------------------------------------------------------------


def test_direct_transition_draft_call_cannot_bypass_gate(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v1: `_transition_draft` is callable from outside
    the class (Python's _ prefix is convention only). v1 placed
    the gate checks in approve_draft only, so a malicious caller
    invoking `store._transition_draft(to_state=APPROVED, ...)`
    flipped the draft to APPROVED bypassing all-clauses-approved,
    SOD, and rationale.

    v2 moves all gate checks INTO _transition_draft inside the
    BEGIN IMMEDIATE so direct-call bypasses fail."""
    d = _create_basic(store, submitter="usr_alice")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    # Don't decide the clause — leave PENDING.
    # Direct call must fail because clauses aren't all approved.
    with pytest.raises(ContractDraftStateError, match="PENDING"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="usr_attacker",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="bypass attempt", mark_decided=True,
            set_approver=True,
        )


def test_direct_transition_draft_blocks_self_approval(
    store: ContractDraftStore,
) -> None:
    """Direct _transition_draft call with submitter==approver
    must fail SOD even though approve_draft isn't dispatching."""
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
    with pytest.raises(
        ContractDraftStateError, match="separation of duties",
    ):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="usr_alice",  # the submitter!
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="self-approval bypass attempt",
            mark_decided=True, set_approver=True,
        )


def test_direct_transition_draft_blocks_empty_rationale(
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
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale=None,  # bypass attempt
            mark_decided=True, set_approver=True,
        )


def test_direct_transition_draft_blocks_rejected_clause(
    store: ContractDraftStore,
) -> None:
    """The TOCTOU race Codex reproduced: a late
    decide_clause(REJECTED) landing between snapshot and
    transition. v2 re-reads clauses inside the lock so REJECTED
    clauses are caught."""
    d = _create_basic(store)
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
        decision=ClauseDecision.REJECTED,
        notes="violates policy",
    )
    # Even direct _transition_draft call must catch the REJECTED
    # clause inside its own lock.
    with pytest.raises(ContractDraftStateError, match="REJECTED"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="bypassing the rejected clause",
            mark_decided=True, set_approver=True,
        )


def test_cross_org_transition_draft_uniform_error(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v1: cross-org access on _transition_draft used
    to disclose existence via different error wording. v2 unifies
    to "not accessible to this caller"."""
    d = _create_basic(store, org_id="org_a")
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_b",  # cross-org
            actor_user_id="attacker",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="cross-org bypass",
            mark_decided=True, set_approver=True,
        )
    # Same wording for genuinely unknown draft_id.
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store._transition_draft(
            draft_id="ctr_phantom", org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="phantom",
            mark_decided=True, set_approver=True,
        )


def test_cross_org_decide_clause_uniform_error(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v1: decide_clause loaded by clause_id first then
    checked org afterward. v2 uses an org-scoped JOIN so cross-
    org and unknown clause_id surface as the same error."""
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
    with pytest.raises(ContractDraftStateError, match="not accessible"):
        store.decide_clause(
            clause_id="cls_phantom", org_id="org_a",
            approver_user_id="bob",
            decision=ClauseDecision.APPROVED, notes="ok",
        )


# ---------------------------------------------------------------------------
# Codex M-26 v2 review fixes
# ---------------------------------------------------------------------------


def test_direct_transition_cannot_resurrect_rejected_to_approved(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v2: caller-supplied from_states could let a
    direct caller pass `from_states=(REJECTED,)` and resurrect a
    terminal-rejected draft to APPROVED. v3 ignores caller-supplied
    from_states for APPROVED/REJECTED transitions and enforces
    AWAITING_APPROVAL as the canonical from-state."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    # Land the draft in REJECTED (terminal).
    store.reject_draft(
        draft_id=d.draft_id, org_id="org_a",
        rejecter_user_id="bob", rationale="not a fit",
    )
    snap = store.get_draft(draft_id=d.draft_id, org_id="org_a")
    assert snap is not None
    assert snap.status == ContractDraftStatus.REJECTED

    # Direct call passing from_states=(REJECTED,) must still fail
    # because v3 forces from_states=(AWAITING_APPROVAL,) for an
    # APPROVED transition.
    with pytest.raises(ContractDraftStateError, match="awaiting_approval"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.REJECTED,),  # bypass attempt
            to_state=ContractDraftStatus.APPROVED,
            rationale="resurrecting rejected",
            mark_decided=True, set_approver=True,
        )


def test_direct_transition_cannot_approve_with_mark_decided_false(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v2: passing mark_decided=False / set_approver=False
    on an APPROVED transition would leave status=approved with
    approved_by=NULL, decided_at=NULL, rationale=NULL. v3 ignores
    caller-supplied bookkeeping flags and forces canonical values
    for terminal transitions."""
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
    # Direct call with mark_decided=False, set_approver=False
    # should NOT produce a NULL-bookkeeping APPROVED row.
    approved = store._transition_draft(
        draft_id=d.draft_id, org_id="org_a",
        actor_user_id="bob",
        from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
        to_state=ContractDraftStatus.APPROVED,
        rationale="reviewed",
        mark_decided=False,  # bypass attempt
        set_approver=False,  # bypass attempt
    )
    # Despite caller passing False, the row is fully populated.
    assert approved.status == ContractDraftStatus.APPROVED
    assert approved.approved_by == "bob"
    assert approved.decided_at is not None
    assert approved.decision_rationale == "reviewed"


def test_direct_transition_cannot_reject_without_bookkeeping(
    store: ContractDraftStore,
) -> None:
    """Symmetric to the APPROVED case: a direct caller passing
    mark_decided=False / set_rejecter=False on a REJECTED
    transition cannot produce a NULL-bookkeeping rejection row."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    rejected = store._transition_draft(
        draft_id=d.draft_id, org_id="org_a",
        actor_user_id="bob",
        from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
        to_state=ContractDraftStatus.REJECTED,
        rationale="not a fit",
        mark_decided=False,  # bypass attempt
        set_rejecter=False,  # bypass attempt
    )
    assert rejected.status == ContractDraftStatus.REJECTED
    assert rejected.rejected_by == "bob"
    assert rejected.decided_at is not None
    assert rejected.decision_rationale == "not a fit"


# ---------------------------------------------------------------------------
# Codex M-26 v3 review fixes
# ---------------------------------------------------------------------------


def test_direct_transition_cannot_revive_rejected_to_awaiting(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v3: v3 forced from_states=(AWAITING_APPROVAL,)
    only when to_state is APPROVED/REJECTED. A direct caller
    could still pass `to_state=AWAITING_APPROVAL,
    from_states=(REJECTED,)` to revive a terminal-rejected
    draft. v4 forbids ANY transition out of terminal states."""
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
    snap = store.get_draft(draft_id=d.draft_id, org_id="org_a")
    assert snap is not None
    assert snap.status == ContractDraftStatus.REJECTED

    # Direct call attempting to revive REJECTED → AWAITING_APPROVAL.
    with pytest.raises(ContractDraftStateError, match="terminal"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.REJECTED,),
            to_state=ContractDraftStatus.AWAITING_APPROVAL,
        )


def test_direct_transition_cannot_revive_approved_to_draft(
    store: ContractDraftStore,
) -> None:
    """Symmetric: APPROVED is also terminal."""
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
    store.approve_draft(
        draft_id=d.draft_id, org_id="org_a",
        approver_user_id="bob", rationale="reviewed",
    )
    with pytest.raises(ContractDraftStateError, match="terminal"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.APPROVED,),
            to_state=ContractDraftStatus.DRAFT,
        )


def test_direct_transition_reject_requires_rationale(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v3: v3 only enforced rationale-required for
    APPROVED. A direct REJECTED transition with rationale=None
    or "" produced status=rejected, decision_rationale=NULL —
    a SOC2 audit-trail violation. v4 enforces rationale for
    REJECTED inside _transition_draft as well."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.REJECTED,
            rationale=None,  # bypass attempt
        )
    with pytest.raises(ContractDraftStateError, match="rationale"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.REJECTED,
            rationale="   ",  # whitespace only
        )


# ---------------------------------------------------------------------------
# Codex M-26 v4 review fixes
# ---------------------------------------------------------------------------


def test_direct_transition_cannot_revert_awaiting_to_draft(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v4: AWAITING_APPROVAL → DRAFT was a non-terminal
    edge that v4 didn't catch (terminal-from check excluded it).
    v5 enforces a closed transition table; reverting a submitted
    draft is not a legal edge."""
    d = _create_basic(store)
    _add_clause(store, d)
    store.submit_for_approval(
        draft_id=d.draft_id, org_id="org_a",
        submitter_user_id="usr_alice",
    )
    with pytest.raises(ContractDraftStateError, match="not a valid"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="alice",
            from_states=(ContractDraftStatus.AWAITING_APPROVAL,),
            to_state=ContractDraftStatus.DRAFT,
        )


def test_direct_transition_cannot_skip_approval_queue(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v4: DRAFT → APPROVED would skip the approval
    queue entirely. v5 blocks this — when to_state is APPROVED,
    v3's from_states-forcing already set from_states to
    (AWAITING_APPROVAL,), so the current=DRAFT check fires before
    we even reach the transition-table check. Either error
    indicates the bypass is closed."""
    d = _create_basic(store)
    _add_clause(store, d)
    # Draft is in DRAFT state. Skip approval queue entirely.
    with pytest.raises(
        ContractDraftStateError, match="awaiting_approval|not a valid",
    ):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="bob",
            from_states=(ContractDraftStatus.DRAFT,),
            to_state=ContractDraftStatus.APPROVED,
            rationale="bypass approval queue",
        )


def test_direct_transition_submit_requires_clauses(
    store: ContractDraftStore,
) -> None:
    """Codex M-26 v4: a direct call to _transition_draft(
    to_state=AWAITING_APPROVAL) bypassed the public
    submit_for_approval's "no clauses → reject" check. v5
    enforces it inside the lock for ANY caller."""
    d = _create_basic(store)
    # No clauses added.
    with pytest.raises(ContractDraftStateError, match="no clauses"):
        store._transition_draft(
            draft_id=d.draft_id, org_id="org_a",
            actor_user_id="alice",
            from_states=(ContractDraftStatus.DRAFT,),
            to_state=ContractDraftStatus.AWAITING_APPROVAL,
        )


def test_clause_to_dict_round_trips(store: ContractDraftStore) -> None:
    d = _create_basic(store)
    c = _add_clause(store, d)
    payload = clause_to_dict(c)
    assert payload["clause_id"] == c.clause_id
    assert payload["evidence_ids"] == ["ev_a"]
    assert payload["decision"] == "pending"
