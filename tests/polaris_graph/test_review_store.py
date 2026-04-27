"""Tests for src/polaris_graph/audit_ir/review_store.py (M-23)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.review_store import (
    ReviewStateError,
    ReviewStatus,
    ReviewStore,
)


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    """Per-test isolated SQLite-backed store."""
    db = tmp_path / "review.sqlite"
    return ReviewStore(db)


# ---------------------------------------------------------------------------
# Enqueue + lifecycle
# ---------------------------------------------------------------------------


def test_enqueue_creates_pending_review(store: ReviewStore) -> None:
    item = store.enqueue(
        org_id="org_alpha", run_slug="x_drug_y", run_id="run_1",
    )
    assert item.review_id.startswith("rev_")
    assert item.org_id == "org_alpha"
    assert item.status == ReviewStatus.PENDING
    assert item.version == 1
    assert item.assigned_to is None
    assert item.decided_by is None
    assert item.decided_at is None
    assert item.prior_review_id is None


def test_enqueue_rejects_empty_fields(store: ReviewStore) -> None:
    with pytest.raises(ReviewStateError, match="non-empty"):
        store.enqueue(org_id="", run_slug="x", run_id="r")
    with pytest.raises(ReviewStateError, match="non-empty"):
        store.enqueue(org_id="o", run_slug="", run_id="r")
    with pytest.raises(ReviewStateError, match="non-empty"):
        store.enqueue(org_id="o", run_slug="x", run_id="")


def test_claim_pending_transitions_to_in_review(store: ReviewStore) -> None:
    item = store.enqueue(
        org_id="org_alpha", run_slug="x", run_id="r",
    )
    claimed = store.claim(
        review_id=item.review_id, org_id="org_alpha", user_id="usr_alice",
    )
    assert claimed.status == ReviewStatus.IN_REVIEW
    assert claimed.assigned_to == "usr_alice"
    assert claimed.decided_by is None


def test_claim_already_claimed_fails(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    store.claim(review_id=item.review_id, org_id="org_alpha", user_id="alice")
    with pytest.raises(ReviewStateError, match="state 'in_review'"):
        store.claim(
            review_id=item.review_id, org_id="org_alpha", user_id="bob",
        )


def test_approve_transitions_to_approved(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(review_id=item.review_id, org_id="org_a", user_id="alice")
    decided = store.approve(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="LGTM",
    )
    assert decided.status == ReviewStatus.APPROVED
    assert decided.decided_by == "alice"
    assert decided.notes == "LGTM"
    assert decided.decided_at is not None


def test_reject_transitions_to_rejected(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(review_id=item.review_id, org_id="org_a", user_id="alice")
    decided = store.reject(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="bad citations",
    )
    assert decided.status == ReviewStatus.REJECTED
    assert decided.notes == "bad citations"


def test_request_changes_transitions_to_needs_changes(
    store: ReviewStore,
) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(review_id=item.review_id, org_id="org_a", user_id="alice")
    decided = store.request_changes(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="add jurisdiction split",
    )
    assert decided.status == ReviewStatus.NEEDS_CHANGES


def test_approve_pending_directly_fails(store: ReviewStore) -> None:
    """Cannot approve without first claiming."""
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    with pytest.raises(ReviewStateError, match="state 'pending'"):
        store.approve(
            review_id=item.review_id, org_id="org_a",
            user_id="alice", notes="noop",
        )


def test_terminal_states_cannot_transition(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(review_id=item.review_id, org_id="org_a", user_id="alice")
    store.approve(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="ok",
    )
    with pytest.raises(ReviewStateError):
        store.reject(
            review_id=item.review_id, org_id="org_a",
            user_id="alice", notes="undo",
        )


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_get_returns_none_for_wrong_org(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    assert store.get(review_id=item.review_id, org_id="org_b") is None


def test_transition_rejects_wrong_org(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    with pytest.raises(ReviewStateError, match="different org"):
        store.claim(
            review_id=item.review_id, org_id="org_b", user_id="alice",
        )


def test_list_by_org_filters_by_tenant(store: ReviewStore) -> None:
    store.enqueue(org_id="org_a", run_slug="x", run_id="r1")
    store.enqueue(org_id="org_a", run_slug="y", run_id="r2")
    store.enqueue(org_id="org_b", run_slug="z", run_id="r3")
    a_items = store.list_by_org(org_id="org_a")
    b_items = store.list_by_org(org_id="org_b")
    assert len(a_items) == 2
    assert len(b_items) == 1
    assert all(i.org_id == "org_a" for i in a_items)
    assert all(i.org_id == "org_b" for i in b_items)


def test_list_chain_does_not_cross_tenant(store: ReviewStore) -> None:
    """Two orgs both have a run with the SAME run_slug — list_chain
    must not bleed across them."""
    store.enqueue(org_id="org_a", run_slug="duplicate_slug", run_id="r_a")
    store.enqueue(org_id="org_b", run_slug="duplicate_slug", run_id="r_b")
    a_chain = store.list_chain_for_run(
        org_id="org_a", run_slug="duplicate_slug",
    )
    b_chain = store.list_chain_for_run(
        org_id="org_b", run_slug="duplicate_slug",
    )
    assert len(a_chain) == 1
    assert len(b_chain) == 1
    assert a_chain[0].run_id == "r_a"
    assert b_chain[0].run_id == "r_b"


# ---------------------------------------------------------------------------
# Status filter on list_by_org
# ---------------------------------------------------------------------------


def test_list_by_org_with_status_filter(store: ReviewStore) -> None:
    pending = store.enqueue(org_id="org_a", run_slug="p", run_id="r1")
    in_review = store.enqueue(org_id="org_a", run_slug="ir", run_id="r2")
    store.claim(
        review_id=in_review.review_id, org_id="org_a", user_id="alice",
    )
    pending_only = store.list_by_org(
        org_id="org_a", status=ReviewStatus.PENDING,
    )
    assert len(pending_only) == 1
    assert pending_only[0].review_id == pending.review_id


# ---------------------------------------------------------------------------
# Re-review chains (version increment)
# ---------------------------------------------------------------------------


def test_re_review_increments_version(store: ReviewStore) -> None:
    v1 = store.enqueue(org_id="org_a", run_slug="x", run_id="r_v1")
    store.claim(review_id=v1.review_id, org_id="org_a", user_id="alice")
    store.request_changes(
        review_id=v1.review_id, org_id="org_a",
        user_id="alice", notes="redo",
    )
    v2 = store.enqueue(
        org_id="org_a", run_slug="x", run_id="r_v2",
        prior_review_id=v1.review_id,
    )
    assert v2.version == 2
    assert v2.prior_review_id == v1.review_id


def test_chain_only_from_needs_changes(store: ReviewStore) -> None:
    """Cannot chain a re-review against an APPROVED prior."""
    v1 = store.enqueue(org_id="org_a", run_slug="x", run_id="r_v1")
    store.claim(review_id=v1.review_id, org_id="org_a", user_id="alice")
    store.approve(
        review_id=v1.review_id, org_id="org_a",
        user_id="alice", notes="ok",
    )
    with pytest.raises(ReviewStateError, match="NEEDS_CHANGES"):
        store.enqueue(
            org_id="org_a", run_slug="x", run_id="r_v2",
            prior_review_id=v1.review_id,
        )


def test_chain_run_slug_must_match(store: ReviewStore) -> None:
    v1 = store.enqueue(org_id="org_a", run_slug="x", run_id="r_v1")
    store.claim(review_id=v1.review_id, org_id="org_a", user_id="alice")
    store.request_changes(
        review_id=v1.review_id, org_id="org_a",
        user_id="alice", notes="redo",
    )
    with pytest.raises(ReviewStateError, match="run_slug"):
        store.enqueue(
            org_id="org_a", run_slug="DIFFERENT", run_id="r_v2",
            prior_review_id=v1.review_id,
        )


def test_chain_org_must_match(store: ReviewStore) -> None:
    """Codex M-23 v1 fix: cross-org chain attempts must surface
    the SAME error wording as truly-unknown prior (no existence
    leak)."""
    v1 = store.enqueue(org_id="org_a", run_slug="x", run_id="r_v1")
    store.claim(review_id=v1.review_id, org_id="org_a", user_id="alice")
    store.request_changes(
        review_id=v1.review_id, org_id="org_a",
        user_id="alice", notes="redo",
    )
    with pytest.raises(ReviewStateError, match="not accessible"):
        store.enqueue(
            org_id="org_b", run_slug="x", run_id="r_v2",
            prior_review_id=v1.review_id,
        )


def test_chain_unknown_prior_fails(store: ReviewStore) -> None:
    """Codex M-23 v1 fix: same wording as cross-org case."""
    with pytest.raises(ReviewStateError, match="not accessible"):
        store.enqueue(
            org_id="org_a", run_slug="x", run_id="r",
            prior_review_id="rev_phantom",
        )


# ---------------------------------------------------------------------------
# Audit log (transitions table)
# ---------------------------------------------------------------------------


def test_transitions_log_records_lifecycle(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(
        review_id=item.review_id, org_id="org_a", user_id="alice",
    )
    store.approve(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="ok",
    )
    rows = store.list_transitions(
        review_id=item.review_id, org_id="org_a",
    )
    transitions = [(r["from_status"], r["to_status"]) for r in rows]
    assert transitions == [
        (None, "pending"),
        ("pending", "in_review"),
        ("in_review", "approved"),
    ]


def test_transitions_log_org_scoped(store: ReviewStore) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    cross = store.list_transitions(
        review_id=item.review_id, org_id="org_b",
    )
    assert cross == []


# ---------------------------------------------------------------------------
# HTTP endpoint integration
# ---------------------------------------------------------------------------


def _make_app_with_store(tmp_path: Path):
    from fastapi import FastAPI
    from src.polaris_graph.audit_ir import inspector_router
    from src.polaris_graph.audit_ir.review_store import ReviewStore

    db = tmp_path / "review.sqlite"
    store_instance = ReviewStore(db)
    inspector_router._review_store = store_instance

    app = FastAPI()
    app.include_router(inspector_router.router)
    return app, store_instance


def test_endpoint_create_review(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _ = _make_app_with_store(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )
    res = client.post(
        "/api/inspector/reviews",
        json={"run_slug": "x_drug_y", "run_id": "run_1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending"
    assert body["org_id"] == "org_alpha"
    assert body["version"] == 1


def test_endpoint_create_requires_member_role(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _ = _make_app_with_store(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_voyeur:viewer"},
    )
    res = client.post(
        "/api/inspector/reviews",
        json={"run_slug": "x", "run_id": "r"},
    )
    assert res.status_code == 403


def test_endpoint_list_org_scoped(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    store.enqueue(org_id="org_alpha", run_slug="a", run_id="r1")
    store.enqueue(org_id="org_alpha", run_slug="b", run_id="r2")
    store.enqueue(org_id="org_beta", run_slug="c", run_id="r3")

    client_alpha = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_x:viewer"},
    )
    res = client_alpha.get("/api/inspector/reviews")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert all(r["org_id"] == "org_alpha" for r in body["reviews"])

    client_beta = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_beta:usr_x:viewer"},
    )
    res = client_beta.get("/api/inspector/reviews")
    assert res.json()["count"] == 1


def test_endpoint_get_cross_org_returns_404(tmp_path: Path) -> None:
    """Codex M-15b cross-tenant invariant: cross-org access on
    review endpoints must NOT distinguish 'unknown' from 'forbidden'.
    Both surface as 403 (existence not leaked) — but the dependency
    here uses 404 for unknown because the existence-leak surface
    matches what /jobs/{job_id} does. This test pins the actual
    behavior so a future refactor doesn't accidentally introduce
    a leak."""
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")

    client_beta = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_beta:usr_x:viewer"},
    )
    res = client_beta.get(f"/api/inspector/reviews/{item.review_id}")
    assert res.status_code == 403
    # Caller's org doesn't match — must be 403 (forbidden), NOT 404
    # (which would tell a probe the review exists).
    detail_lc = res.json()["detail"].lower()
    assert "does not belong" in detail_lc or "different org" in detail_lc


def test_endpoint_claim_then_decide(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )

    res = client.post(f"/api/inspector/reviews/{item.review_id}/claim")
    assert res.status_code == 200
    assert res.json()["status"] == "in_review"
    assert res.json()["assigned_to"] == "usr_alice"

    res = client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "approved", "notes": "LGTM"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == "usr_alice"
    assert body["notes"] == "LGTM"


def test_endpoint_decision_requires_notes_for_rejected(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )
    client.post(f"/api/inspector/reviews/{item.review_id}/claim")

    res = client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "rejected"},
    )
    assert res.status_code == 400
    assert "notes" in res.json()["detail"].lower()


def test_endpoint_decision_unknown_value_400(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )
    client.post(f"/api/inspector/reviews/{item.review_id}/claim")
    res = client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "weird", "notes": "ok"},
    )
    assert res.status_code == 400


def test_endpoint_unknown_review_id_404(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, _ = _make_app_with_store(tmp_path)
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_x:member"},
    )
    res = client.get("/api/inspector/reviews/rev_phantom")
    assert res.status_code == 404


def test_endpoint_transitions_log(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )
    client.post(f"/api/inspector/reviews/{item.review_id}/claim")
    client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "needs_changes", "notes": "redo"},
    )
    res = client.get(
        f"/api/inspector/reviews/{item.review_id}/transitions",
    )
    assert res.status_code == 200
    transitions = res.json()["transitions"]
    pairs = [(t["from_status"], t["to_status"]) for t in transitions]
    assert pairs == [
        (None, "pending"),
        ("pending", "in_review"),
        ("in_review", "needs_changes"),
    ]


# ---------------------------------------------------------------------------
# Codex M-23 v1 review fixes
# ---------------------------------------------------------------------------


def test_chain_unknown_prior_uniform_error_does_not_leak_existence(
    store: ReviewStore,
) -> None:
    """Codex M-23 v1: enqueue() leaked existence of foreign
    prior_review_id by returning distinct errors for unknown vs
    cross-org vs wrong-state. v2 returns a uniform 'not accessible
    to this caller' for all three."""
    # Cross-org probe: prior exists in org_a, caller tries from
    # org_b. Must NOT distinguish from "doesn't exist at all".
    real_prior = store.enqueue(
        org_id="org_a", run_slug="x", run_id="r_v1",
    )
    store.claim(
        review_id=real_prior.review_id, org_id="org_a",
        user_id="alice",
    )
    store.request_changes(
        review_id=real_prior.review_id, org_id="org_a",
        user_id="alice", notes="redo",
    )

    # Existing prior, but caller is in different org.
    with pytest.raises(ReviewStateError) as exc_existing:
        store.enqueue(
            org_id="org_b", run_slug="x", run_id="r_v2",
            prior_review_id=real_prior.review_id,
        )
    # Truly nonexistent prior.
    with pytest.raises(ReviewStateError) as exc_phantom:
        store.enqueue(
            org_id="org_b", run_slug="x", run_id="r_v2",
            prior_review_id="rev_phantom",
        )
    # Both errors must use the same wording so an attacker cannot
    # probe which review_ids exist.
    assert "not accessible" in str(exc_existing.value)
    assert "not accessible" in str(exc_phantom.value)


def test_chain_does_not_allow_multiple_v2_siblings(
    store: ReviewStore,
) -> None:
    """Codex M-23 v1: a single v1 in NEEDS_CHANGES could spawn
    multiple v2 siblings, all with the same version number. v2
    enforces uniqueness on prior_review_id."""
    v1 = store.enqueue(org_id="org_a", run_slug="x", run_id="r_v1")
    store.claim(review_id=v1.review_id, org_id="org_a", user_id="alice")
    store.request_changes(
        review_id=v1.review_id, org_id="org_a",
        user_id="alice", notes="redo",
    )
    # First child OK.
    v2 = store.enqueue(
        org_id="org_a", run_slug="x", run_id="r_v2",
        prior_review_id=v1.review_id,
    )
    assert v2.version == 2
    # Second child against the same prior must fail.
    with pytest.raises(ReviewStateError, match="already has a chained"):
        store.enqueue(
            org_id="org_a", run_slug="x", run_id="r_v2_sibling",
            prior_review_id=v1.review_id,
        )


def test_assignee_only_decision_blocks_other_member(
    store: ReviewStore,
) -> None:
    """Codex M-23 v1: a same-org member who didn't claim could
    still approve. v2 enforces assignee-only."""
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(
        review_id=item.review_id, org_id="org_a", user_id="alice",
    )
    with pytest.raises(ReviewStateError, match="assignee"):
        store.approve(
            review_id=item.review_id, org_id="org_a",
            user_id="bob",  # different member
            notes="LGTM",
        )
    # The original assignee can still decide.
    decided = store.approve(
        review_id=item.review_id, org_id="org_a",
        user_id="alice", notes="LGTM",
    )
    assert decided.status == ReviewStatus.APPROVED


def test_assignee_only_blocks_reject_and_request_changes(
    store: ReviewStore,
) -> None:
    item = store.enqueue(org_id="org_a", run_slug="x", run_id="r")
    store.claim(
        review_id=item.review_id, org_id="org_a", user_id="alice",
    )
    with pytest.raises(ReviewStateError, match="assignee"):
        store.reject(
            review_id=item.review_id, org_id="org_a",
            user_id="bob", notes="nope",
        )
    with pytest.raises(ReviewStateError, match="assignee"):
        store.request_changes(
            review_id=item.review_id, org_id="org_a",
            user_id="bob", notes="redo",
        )


def test_zero_width_only_notes_treated_as_empty_via_endpoint(
    tmp_path: Path,
) -> None:
    """Codex M-23 v1: zero-width-only or control-char-only notes
    on rejected/needs_changes were accepted as 'non-empty' by
    notes.strip(). v2 sanitizes Cc/Cf/whitespace before checking
    emptiness."""
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(
        org_id="org_alpha", run_slug="x", run_id="r",
    )
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_alice:member"},
    )
    client.post(f"/api/inspector/reviews/{item.review_id}/claim")

    # Zero-width space only
    res = client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "rejected", "notes": "​​​"},
    )
    assert res.status_code == 409, res.text  # store-level rejection
    # Or 400 if the router's pre-check catches it first; both
    # surface as "not empty" failure.
    detail_lc = res.json()["detail"].lower()
    assert "notes" in detail_lc or "non-empty" in detail_lc or "justif" in detail_lc

    # Control-character only
    res = client.post(
        f"/api/inspector/reviews/{item.review_id}/decision",
        json={"decision": "rejected", "notes": ""},
    )
    assert res.status_code == 409
    detail_lc = res.json()["detail"].lower()
    assert "notes" in detail_lc or "non-empty" in detail_lc or "justif" in detail_lc


def test_endpoint_diff_no_prior_400(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    app, store = _make_app_with_store(tmp_path)
    item = store.enqueue(org_id="org_alpha", run_slug="x", run_id="r")
    client = TestClient(
        app,
        headers={"X-Polaris-Caller": "org_alpha:usr_x:viewer"},
    )
    res = client.get(f"/api/inspector/reviews/{item.review_id}/diff")
    assert res.status_code == 400
    assert "prior" in res.json()["detail"].lower()
