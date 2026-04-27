"""Tests for src/polaris_graph/audit_ir/support_ticket_store.py (M-24)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.support_ticket_store import (
    SupportTicket,
    SupportTicketStateError,
    SupportTicketStore,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    message_to_dict,
    ticket_to_dict,
)


@pytest.fixture
def store(tmp_path: Path) -> SupportTicketStore:
    return SupportTicketStore(tmp_path / "support.sqlite")


def _open_basic(
    store: SupportTicketStore, *,
    org_id: str = "org_a",
    submitter: str = "usr_alice",
    title: str = "Audit bundle missing contradictions",
    description: str = "The audit bundle for run_id=run_v3 has zero contradictions but the inspector shows 2.",
    category: TicketCategory = TicketCategory.AUDIT,
    related_run_slug: str | None = None,
) -> SupportTicket:
    return store.open_ticket(
        org_id=org_id, submitter_user_id=submitter, title=title,
        description=description, category=category,
        related_run_slug=related_run_slug,
    )


# ---------------------------------------------------------------------------
# Open + validation
# ---------------------------------------------------------------------------


def test_open_ticket_creates_row(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    assert t.ticket_id.startswith("sup_")
    assert t.status == TicketStatus.OPEN
    assert t.priority == TicketPriority.NORMAL
    assert t.assigned_to is None
    assert t.created_at > 0


def test_open_ticket_with_back_links(store: SupportTicketStore) -> None:
    t = store.open_ticket(
        org_id="org_a", submitter_user_id="alice",
        title="x", description="y",
        category=TicketCategory.AUDIT,
        related_run_slug="x_drug_y",
        related_review_id="rev_abc",
        related_workspace_id="ws_xyz",
    )
    assert t.related_run_slug == "x_drug_y"
    assert t.related_review_id == "rev_abc"
    assert t.related_workspace_id == "ws_xyz"


def test_open_ticket_rejects_empty_fields(
    store: SupportTicketStore,
) -> None:
    common = dict(
        org_id="org_a", submitter_user_id="alice",
        title="t", description="d",
        category=TicketCategory.OTHER,
    )
    with pytest.raises(SupportTicketStateError, match="org_id"):
        store.open_ticket(**{**common, "org_id": ""})
    with pytest.raises(SupportTicketStateError, match="submitter"):
        store.open_ticket(**{**common, "submitter_user_id": ""})
    with pytest.raises(SupportTicketStateError, match="title"):
        store.open_ticket(**{**common, "title": ""})
    with pytest.raises(SupportTicketStateError, match="description"):
        store.open_ticket(**{**common, "description": ""})


def test_open_ticket_rejects_non_enum_category(
    store: SupportTicketStore,
) -> None:
    with pytest.raises(SupportTicketStateError, match="category"):
        store.open_ticket(
            org_id="o", submitter_user_id="u", title="t",
            description="d", category="audit",  # type: ignore[arg-type]
        )


def test_open_ticket_rejects_non_enum_priority(
    store: SupportTicketStore,
) -> None:
    with pytest.raises(SupportTicketStateError, match="priority"):
        store.open_ticket(
            org_id="o", submitter_user_id="u", title="t",
            description="d", category=TicketCategory.OTHER,
            priority="urgent",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def test_assign_transitions_open_to_in_progress(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store)
    assigned = store.assign(
        ticket_id=t.ticket_id, org_id="org_a",
        agent_user_id="usr_support_carol",
    )
    assert assigned.status == TicketStatus.IN_PROGRESS
    assert assigned.assigned_to == "usr_support_carol"


def test_reassign_does_not_re_transition_status(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store)
    store.assign(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    reassigned = store.assign(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="bob",
    )
    assert reassigned.assigned_to == "bob"
    assert reassigned.status == TicketStatus.IN_PROGRESS


def test_resolve_marks_resolved(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    store.assign(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    resolved = store.resolve(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    assert resolved.status == TicketStatus.RESOLVED
    assert resolved.resolved_at is not None


def test_close_marks_closed(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    closed = store.close(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    assert closed.status == TicketStatus.CLOSED
    assert closed.resolved_at is not None


def test_reopen_clears_resolved_at(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    store.resolve(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    reopened = store.reopen(
        ticket_id=t.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    assert reopened.status == TicketStatus.IN_PROGRESS
    assert reopened.resolved_at is None


def test_reopen_invalid_from_open(store: SupportTicketStore) -> None:
    """OPEN tickets can't be reopened — only RESOLVED or CLOSED can."""
    t = _open_basic(store)
    with pytest.raises(SupportTicketStateError, match="state 'open'"):
        store.reopen(
            ticket_id=t.ticket_id, org_id="org_a",
            agent_user_id="alice",
        )


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_get_returns_none_for_wrong_org(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store, org_id="org_a")
    assert store.get_ticket(ticket_id=t.ticket_id, org_id="org_b") is None


def test_assign_rejects_wrong_org(store: SupportTicketStore) -> None:
    t = _open_basic(store, org_id="org_a")
    with pytest.raises(SupportTicketStateError, match="different org"):
        store.assign(
            ticket_id=t.ticket_id, org_id="org_b",
            agent_user_id="bob",
        )


def test_list_by_org_filters_tenant(store: SupportTicketStore) -> None:
    _open_basic(store, org_id="org_a", title="a-1")
    _open_basic(store, org_id="org_a", title="a-2")
    _open_basic(store, org_id="org_b", title="b-1")
    assert len(store.list_by_org(org_id="org_a")) == 2
    assert len(store.list_by_org(org_id="org_b")) == 1


def test_list_by_org_status_filter(store: SupportTicketStore) -> None:
    open_t = _open_basic(store, org_id="org_a", title="open")
    closed_t = _open_basic(store, org_id="org_a", title="closed")
    store.close(
        ticket_id=closed_t.ticket_id, org_id="org_a",
        agent_user_id="alice",
    )
    open_only = store.list_by_org(
        org_id="org_a", status=TicketStatus.OPEN,
    )
    assert len(open_only) == 1
    assert open_only[0].ticket_id == open_t.ticket_id


def test_list_by_org_category_filter(store: SupportTicketStore) -> None:
    _open_basic(store, org_id="org_a", category=TicketCategory.AUDIT)
    _open_basic(store, org_id="org_a", category=TicketCategory.BILLING)
    audits = store.list_by_org(
        org_id="org_a", category=TicketCategory.AUDIT,
    )
    assert len(audits) == 1
    assert audits[0].category == TicketCategory.AUDIT


def test_list_by_org_assignee_filter(store: SupportTicketStore) -> None:
    t1 = _open_basic(store, org_id="org_a")
    t2 = _open_basic(store, org_id="org_a")
    store.assign(
        ticket_id=t1.ticket_id, org_id="org_a", agent_user_id="alice",
    )
    alice_q = store.list_by_org(org_id="org_a", assigned_to="alice")
    assert len(alice_q) == 1
    assert alice_q[0].ticket_id == t1.ticket_id


# ---------------------------------------------------------------------------
# Append-only message thread
# ---------------------------------------------------------------------------


def test_append_message_creates_row(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    msg = store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="Following up here.",
    )
    assert msg.message_id.startswith("msg_")
    assert msg.body == "Following up here."


def test_append_message_rejects_cross_org(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store, org_id="org_a")
    with pytest.raises(SupportTicketStateError, match="not accessible"):
        store.append_message(
            ticket_id=t.ticket_id, org_id="org_b",
            author_user_id="attacker", body="hi",
        )


def test_append_message_rejects_empty_body(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store)
    with pytest.raises(SupportTicketStateError, match="body"):
        store.append_message(
            ticket_id=t.ticket_id, org_id="org_a",
            author_user_id="alice", body="   ",
        )


def test_list_messages_returns_oldest_first(
    store: SupportTicketStore,
) -> None:
    t = _open_basic(store)
    m1 = store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="first",
    )
    m2 = store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="second",
    )
    msgs = store.list_messages(
        ticket_id=t.ticket_id, org_id="org_a",
    )
    assert [m.message_id for m in msgs] == [m1.message_id, m2.message_id]


def test_list_messages_cross_org_returns_empty(
    store: SupportTicketStore,
) -> None:
    """Codex-style cross-tenant smoke: org_b cannot see org_a's
    message thread."""
    t = _open_basic(store, org_id="org_a")
    store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="private",
    )
    cross = store.list_messages(
        ticket_id=t.ticket_id, org_id="org_b",
    )
    assert cross == []


def test_append_message_bumps_ticket_updated_at(
    store: SupportTicketStore,
) -> None:
    """A new message bumps the ticket's updated_at so the queue
    surfaces most-recently-active first."""
    t = _open_basic(store)
    pre = t.updated_at
    import time as _time
    _time.sleep(0.005)
    store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="new",
    )
    later = store.get_ticket(ticket_id=t.ticket_id, org_id="org_a")
    assert later is not None
    assert later.updated_at > pre


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_ticket_to_dict_round_trips(store: SupportTicketStore) -> None:
    t = _open_basic(store, related_run_slug="x_drug_y")
    d = ticket_to_dict(t)
    assert d["ticket_id"] == t.ticket_id
    assert d["status"] == "open"
    assert d["category"] == "audit"
    assert d["priority"] == "normal"
    assert d["related_run_slug"] == "x_drug_y"


def test_message_to_dict_round_trips(store: SupportTicketStore) -> None:
    t = _open_basic(store)
    m = store.append_message(
        ticket_id=t.ticket_id, org_id="org_a",
        author_user_id="alice", body="x",
    )
    d = message_to_dict(m)
    assert d["message_id"] == m.message_id
    assert d["body"] == "x"
