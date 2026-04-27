"""Tests for src/polaris_graph/audit_ir/private_corpus_sync.py (M-25)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.private_corpus_sync import (
    CorpusSource,
    PrivateCorpusSyncStore,
    SourceConnector,
    SourceStateError,
    SourceStatus,
    SyncBlockedError,
    SyncRun,
    SyncRunStatus,
    source_to_dict,
    sync_run_to_dict,
)


@pytest.fixture
def store(tmp_path: Path) -> PrivateCorpusSyncStore:
    return PrivateCorpusSyncStore(tmp_path / "sync.sqlite")


def _register_basic(
    store: PrivateCorpusSyncStore, *,
    workspace_id: str = "ws_a",
    org_id: str = "org_a",
    connector: SourceConnector = SourceConnector.GOOGLE_DRIVE,
    name: str = "Drive: Clinical Studies",
    external_uri: str = "1AbCdEfGh-folder-id",
    credential_ref: str = "vault://service-accounts/drive-corpus",
) -> CorpusSource:
    return store.register_source(
        workspace_id=workspace_id, org_id=org_id, connector=connector,
        name=name, external_uri=external_uri,
        credential_ref=credential_ref,
    )


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def test_register_creates_pending_source(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    assert s.source_id.startswith("src_")
    assert s.status == SourceStatus.PENDING
    assert s.connector == SourceConnector.GOOGLE_DRIVE
    assert s.approved_by is None
    assert s.revoked_by is None


def test_register_rejects_empty_fields(
    store: PrivateCorpusSyncStore,
) -> None:
    common = dict(
        workspace_id="ws_a", org_id="org_a",
        connector=SourceConnector.SHAREPOINT,
        name="x", external_uri="https://contoso.example",
        credential_ref="vault://x",
    )
    with pytest.raises(SourceStateError, match="workspace_id|org_id"):
        store.register_source(**{**common, "workspace_id": ""})
    with pytest.raises(SourceStateError, match="workspace_id|org_id"):
        store.register_source(**{**common, "org_id": ""})
    with pytest.raises(SourceStateError, match="name"):
        store.register_source(**{**common, "name": "  "})
    with pytest.raises(SourceStateError, match="external_uri"):
        store.register_source(**{**common, "external_uri": ""})
    with pytest.raises(SourceStateError, match="credential_ref"):
        store.register_source(**{**common, "credential_ref": ""})


def test_register_rejects_non_enum_connector(
    store: PrivateCorpusSyncStore,
) -> None:
    with pytest.raises(SourceStateError, match="connector"):
        store.register_source(
            workspace_id="ws", org_id="org", connector="drive",  # type: ignore[arg-type]
            name="x", external_uri="x", credential_ref="vault://x",
        )


# ---------------------------------------------------------------------------
# Defense-in-depth: refuse raw secrets in credential_ref
# ---------------------------------------------------------------------------


def test_register_rejects_jwt_in_credential_ref(
    store: PrivateCorpusSyncStore,
) -> None:
    """credential_ref is meant to be a vault POINTER, not the
    secret itself. v1 rejects common raw-secret shapes as a
    safety net so a misuse of the API doesn't quietly persist
    a credential."""
    fake_jwt = "eyJ" + "a" * 100
    with pytest.raises(SourceStateError, match="raw secret"):
        store.register_source(
            workspace_id="ws_a", org_id="org_a",
            connector=SourceConnector.GOOGLE_DRIVE,
            name="x", external_uri="x", credential_ref=fake_jwt,
        )


def test_register_rejects_aws_key_in_credential_ref(
    store: PrivateCorpusSyncStore,
) -> None:
    with pytest.raises(SourceStateError, match="raw secret"):
        _register_basic(
            store, credential_ref="AKIAIOSFODNN7EXAMPLE",
        )


def test_register_rejects_pem_private_key(
    store: PrivateCorpusSyncStore,
) -> None:
    with pytest.raises(SourceStateError, match="raw secret"):
        _register_basic(
            store,
            credential_ref="-----BEGIN PRIVATE KEY-----\nXXX\n-----END",
        )


def test_register_rejects_github_pat(
    store: PrivateCorpusSyncStore,
) -> None:
    with pytest.raises(SourceStateError, match="raw secret"):
        _register_basic(
            store, credential_ref="ghp_" + "a" * 30,
        )


# ---------------------------------------------------------------------------
# Approval / revocation lifecycle
# ---------------------------------------------------------------------------


def test_approve_pending_source(store: PrivateCorpusSyncStore) -> None:
    s = _register_basic(store)
    approved = store.approve_source(
        source_id=s.source_id, org_id="org_a",
        approver_user_id="usr_admin",
    )
    assert approved.status == SourceStatus.APPROVED
    assert approved.approved_by == "usr_admin"
    assert approved.revoked_by is None


def test_revoke_approved_source(store: PrivateCorpusSyncStore) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a",
        approver_user_id="alice",
    )
    revoked = store.revoke_source(
        source_id=s.source_id, org_id="org_a",
        revoker_user_id="alice",
    )
    assert revoked.status == SourceStatus.REVOKED
    assert revoked.revoked_by == "alice"


def test_revoke_then_re_approve(store: PrivateCorpusSyncStore) -> None:
    """Lifecycle: pending → approved → revoked → approved.
    Re-approval clears the revoked_by flag."""
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    store.revoke_source(
        source_id=s.source_id, org_id="org_a", revoker_user_id="alice",
    )
    re_approved = store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="bob",
    )
    assert re_approved.status == SourceStatus.APPROVED
    assert re_approved.approved_by == "bob"
    assert re_approved.revoked_by is None


def test_approve_rejects_already_approved(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    with pytest.raises(SourceStateError, match="state 'approved'"):
        store.approve_source(
            source_id=s.source_id, org_id="org_a",
            approver_user_id="alice",
        )


def test_revoke_rejects_already_revoked(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    store.revoke_source(
        source_id=s.source_id, org_id="org_a", revoker_user_id="alice",
    )
    with pytest.raises(SourceStateError, match="state 'revoked'"):
        store.revoke_source(
            source_id=s.source_id, org_id="org_a",
            revoker_user_id="alice",
        )


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_get_source_returns_none_for_wrong_org(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store, org_id="org_a")
    assert store.get_source(
        source_id=s.source_id, org_id="org_b",
    ) is None


def test_approve_rejects_wrong_org(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store, org_id="org_a")
    with pytest.raises(SourceStateError, match="different org"):
        store.approve_source(
            source_id=s.source_id, org_id="org_b",
            approver_user_id="bob",
        )


def test_list_sources_for_workspace_is_org_scoped(
    store: PrivateCorpusSyncStore,
) -> None:
    """Two orgs both have workspaces with the SAME workspace_id
    string — list_sources_for_workspace must NOT bleed."""
    _register_basic(store, workspace_id="ws_dup", org_id="org_a")
    _register_basic(store, workspace_id="ws_dup", org_id="org_b")
    a = store.list_sources_for_workspace(
        workspace_id="ws_dup", org_id="org_a",
    )
    b = store.list_sources_for_workspace(
        workspace_id="ws_dup", org_id="org_b",
    )
    assert len(a) == 1
    assert len(b) == 1
    assert a[0].org_id == "org_a"
    assert b[0].org_id == "org_b"


def test_record_sync_run_rejects_wrong_org(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store, org_id="org_a")
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    with pytest.raises(SourceStateError, match="not accessible"):
        store.record_sync_run(
            source_id=s.source_id, org_id="org_b",
            triggered_by_user_id="attacker",
            status=SyncRunStatus.SUCCEEDED,
        )


# ---------------------------------------------------------------------------
# Approval gate — sync only allowed when APPROVED
# ---------------------------------------------------------------------------


def test_sync_blocked_for_pending_source(
    store: PrivateCorpusSyncStore,
) -> None:
    """FINAL_PLAN: 'approved-only, NOT broad connector parity'.
    A PENDING source cannot sync."""
    s = _register_basic(store)
    with pytest.raises(SyncBlockedError, match="pending|approved"):
        store.record_sync_run(
            source_id=s.source_id, org_id="org_a",
            triggered_by_user_id="alice",
            status=SyncRunStatus.SUCCEEDED,
        )


def test_sync_blocked_for_revoked_source(
    store: PrivateCorpusSyncStore,
) -> None:
    """A REVOKED source cannot sync — even though it was once
    approved, the operator's revocation gates further activity."""
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    store.revoke_source(
        source_id=s.source_id, org_id="org_a", revoker_user_id="alice",
    )
    with pytest.raises(SyncBlockedError, match="revoked|approved"):
        store.record_sync_run(
            source_id=s.source_id, org_id="org_a",
            triggered_by_user_id="alice",
            status=SyncRunStatus.SUCCEEDED,
        )


def test_sync_succeeds_for_approved_source(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    run = store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice",
        status=SyncRunStatus.SUCCEEDED,
        doc_count=42, bytes_synced=12345,
    )
    assert run.status == SyncRunStatus.SUCCEEDED
    assert run.doc_count == 42
    assert run.bytes_synced == 12345


def test_sync_history_preserved_after_revocation(
    store: PrivateCorpusSyncStore,
) -> None:
    """An operator revokes a source — past sync history must be
    preserved (append-only log for invoicing / audit)."""
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice",
        status=SyncRunStatus.SUCCEEDED, doc_count=10,
    )
    store.revoke_source(
        source_id=s.source_id, org_id="org_a", revoker_user_id="alice",
    )
    runs = store.list_sync_runs(
        source_id=s.source_id, org_id="org_a",
    )
    assert len(runs) == 1


# ---------------------------------------------------------------------------
# list_sync_runs
# ---------------------------------------------------------------------------


def test_list_sync_runs_returns_newest_first(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    r1 = store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice", status=SyncRunStatus.SUCCEEDED,
    )
    import time as _time
    _time.sleep(0.001)
    r2 = store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice", status=SyncRunStatus.FAILED,
        error_message="HTTP 503",
    )
    runs = store.list_sync_runs(
        source_id=s.source_id, org_id="org_a",
    )
    assert [r.sync_run_id for r in runs] == [r2.sync_run_id, r1.sync_run_id]


def test_list_sync_runs_cross_org_returns_empty(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store, org_id="org_a")
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice", status=SyncRunStatus.SUCCEEDED,
    )
    cross = store.list_sync_runs(
        source_id=s.source_id, org_id="org_b",
    )
    assert cross == []


def test_list_sync_runs_limit_validation(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    with pytest.raises(SourceStateError, match="limit"):
        store.list_sync_runs(
            source_id=s.source_id, org_id="org_a", limit=0,
        )
    with pytest.raises(SourceStateError, match="limit"):
        store.list_sync_runs(
            source_id=s.source_id, org_id="org_a", limit=1001,
        )


def test_record_sync_run_atomic_check_and_insert(
    store: PrivateCorpusSyncStore,
) -> None:
    """Codex M-25 v1: approval check and insert ran in two
    separate connections, so a concurrent revoke could let a
    sync row land for a now-revoked source. v2 wraps the whole
    operation in BEGIN IMMEDIATE.

    This test simulates the race deterministically by revoking
    the source AFTER the test asserts approval but BEFORE
    record_sync_run executes (impossible to reproduce exactly,
    so we verify the insert refuses post-revocation as a sanity
    check on the atomic re-read pattern)."""
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    # First sync succeeds.
    store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice",
        status=SyncRunStatus.SUCCEEDED,
    )
    # Operator revokes between syncs.
    store.revoke_source(
        source_id=s.source_id, org_id="org_a", revoker_user_id="alice",
    )
    # Second sync attempted post-revoke must be refused — v2's
    # atomic re-read inside BEGIN IMMEDIATE catches the new
    # state.
    with pytest.raises(SyncBlockedError, match="revoked|approved"):
        store.record_sync_run(
            source_id=s.source_id, org_id="org_a",
            triggered_by_user_id="alice",
            status=SyncRunStatus.SUCCEEDED,
        )
    # And no second row landed.
    runs = store.list_sync_runs(
        source_id=s.source_id, org_id="org_a",
    )
    assert len(runs) == 1


@pytest.mark.parametrize("secret", [
    # Slack tokens
    "xoxb-1234567890-abc",
    "xoxp-1234-abcd",
    "xoxa-token",
    "xapp-1-abc",
    # Google API key
    "AIzaSyD" + "x" * 35,
    # Google OAuth tokens
    "ya29.A0ARrdaM-token",
    "1//0gAbcdefghij",
    # Azure connection strings
    "DefaultEndpointsProtocol=https;AccountKey=abc",
    "Endpoint=sb://x;SharedAccessKey=def",
    "https://x.blob.core.windows.net/?SharedAccessSignature=abc",
    # GitHub fine-grained PAT
    "github_pat_" + "x" * 30,
    # OpenSSH / EC private keys
    "-----BEGIN OPENSSH PRIVATE KEY-----\nXXX",
    "-----BEGIN EC PRIVATE KEY-----\nXXX",
])
def test_register_rejects_codex_m25_secret_patterns(
    store: PrivateCorpusSyncStore, secret: str,
) -> None:
    """Codex M-25 v1 review additions: Slack, Google API/OAuth,
    Azure, GitHub fine-grained PAT, OpenSSH/EC private keys."""
    with pytest.raises(SourceStateError, match="raw secret"):
        _register_basic(store, credential_ref=secret)


def test_record_sync_run_rejects_negative_counts(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    with pytest.raises(SourceStateError, match=">= 0"):
        store.record_sync_run(
            source_id=s.source_id, org_id="org_a",
            triggered_by_user_id="alice",
            status=SyncRunStatus.SUCCEEDED,
            doc_count=-1,
        )


# ---------------------------------------------------------------------------
# Status filter
# ---------------------------------------------------------------------------


def test_list_sources_status_filter(
    store: PrivateCorpusSyncStore,
) -> None:
    s_pending = _register_basic(
        store, workspace_id="ws_a", name="Pending source",
    )
    s_approved = _register_basic(
        store, workspace_id="ws_a", name="Approved source",
    )
    store.approve_source(
        source_id=s_approved.source_id, org_id="org_a",
        approver_user_id="alice",
    )
    pending_only = store.list_sources_for_workspace(
        workspace_id="ws_a", org_id="org_a",
        status=SourceStatus.PENDING,
    )
    assert len(pending_only) == 1
    assert pending_only[0].source_id == s_pending.source_id


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_source_to_dict_round_trips(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    d = source_to_dict(s)
    assert d["source_id"] == s.source_id
    assert d["status"] == "pending"
    assert d["connector"] == "google_drive"


def test_sync_run_to_dict_round_trips(
    store: PrivateCorpusSyncStore,
) -> None:
    s = _register_basic(store)
    store.approve_source(
        source_id=s.source_id, org_id="org_a", approver_user_id="alice",
    )
    r = store.record_sync_run(
        source_id=s.source_id, org_id="org_a",
        triggered_by_user_id="alice",
        status=SyncRunStatus.PARTIAL,
        doc_count=5, bytes_synced=1024,
        error_message="3 of 8 docs failed",
    )
    d = sync_run_to_dict(r)
    assert d["status"] == "partial"
    assert d["doc_count"] == 5
    assert d["error_message"] == "3 of 8 docs failed"
