"""Tests for src/polaris_graph/audit_ir/security_audit_log.py (M-19)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.security_audit_log import (
    EventSeverity,
    SecurityAuditLog,
    SecurityAuditLogError,
    SecurityEvent,
    SecurityEventType,
    event_to_dict,
)


@pytest.fixture
def log(tmp_path: Path) -> SecurityAuditLog:
    return SecurityAuditLog(tmp_path / "sec.sqlite")


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_record_event_creates_row(log: SecurityAuditLog) -> None:
    e = log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_alice", org_id="org_alpha",
        source_ip="10.0.0.5",
    )
    assert e.event_id.startswith("sec_")
    assert e.event_type == SecurityEventType.AUTH_SUCCEEDED
    assert e.severity == EventSeverity.INFO  # default for AUTH_SUCCEEDED
    assert e.user_id == "usr_alice"
    assert e.org_id == "org_alpha"
    assert e.created_at > 0


def test_record_event_uses_explicit_severity(log: SecurityAuditLog) -> None:
    """Caller can override the default severity (e.g. escalate
    repeated cross-tenant attempts to CRITICAL)."""
    e = log.record_event(
        event_type=SecurityEventType.CROSS_TENANT_DENIED,
        severity=EventSeverity.CRITICAL,
        user_id="usr_attacker", org_id="org_alpha",
    )
    assert e.severity == EventSeverity.CRITICAL


def test_record_event_default_severity_for_failures(
    log: SecurityAuditLog,
) -> None:
    """AUTH_FAILED, CROSS_TENANT_DENIED, PRIVILEGE_ESCALATION_DENIED
    all default to WARN."""
    # AUTH_FAILED is allowed anonymous (the failure means no user).
    e = log.record_event(event_type=SecurityEventType.AUTH_FAILED)
    assert e.severity == EventSeverity.WARN
    # CROSS_TENANT_DENIED + PRIVILEGE_ESCALATION_DENIED REQUIRE
    # attribution per Codex M-19 v2 fix.
    for event_type in (
        SecurityEventType.CROSS_TENANT_DENIED,
        SecurityEventType.PRIVILEGE_ESCALATION_DENIED,
    ):
        e = log.record_event(
            event_type=event_type,
            user_id="usr_x", org_id="org_a",
        )
        assert e.severity == EventSeverity.WARN


def test_record_event_preserves_details(log: SecurityAuditLog) -> None:
    e = log.record_event(
        event_type=SecurityEventType.CROSS_TENANT_DENIED,
        user_id="usr_attacker", org_id="org_a",
        details={"target_org": "org_beta", "resource_id": "ws_x"},
    )
    payload = event_to_dict(e)
    assert payload["details"]["target_org"] == "org_beta"
    assert payload["details"]["resource_id"] == "ws_x"


def test_record_event_handles_unserializable_details(
    log: SecurityAuditLog,
) -> None:
    """A non-JSON-serializable value in details must NOT crash —
    must fall back to a string repr so the event still records."""

    class NotSerializable:
        pass

    e = log.record_event(
        event_type=SecurityEventType.AUTH_FAILED,
        details={"obj": NotSerializable()},
    )
    payload = event_to_dict(e)
    # Either the fallback {"raw": ...} representation or a
    # cleanly-serialized one is acceptable as long as the event
    # was recorded.
    assert "details" in payload


def test_record_event_rejects_non_enum_event_type(
    log: SecurityAuditLog,
) -> None:
    with pytest.raises(SecurityAuditLogError, match="event_type"):
        log.record_event(event_type="not_an_enum")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------------


def test_list_events_returns_newest_first(log: SecurityAuditLog) -> None:
    e1 = log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )
    time.sleep(0.001)
    e2 = log.record_event(
        event_type=SecurityEventType.AUTH_FAILED, org_id="org_a",
    )
    rows = log.list_events(org_id="org_a")
    assert [r.event_id for r in rows] == [e2.event_id, e1.event_id]


def test_list_filters_by_severity(log: SecurityAuditLog) -> None:
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )  # INFO
    log.record_event(
        event_type=SecurityEventType.CROSS_TENANT_DENIED,
        user_id="usr_attacker", org_id="org_a",
    )  # WARN
    log.record_event(
        event_type=SecurityEventType.AUTH_FAILED, org_id="org_a",
    )  # WARN — anonymous OK
    warn_only = log.list_events(
        org_id="org_a", severity=EventSeverity.WARN,
    )
    assert len(warn_only) == 2
    assert all(r.severity == EventSeverity.WARN for r in warn_only)


def test_list_filters_by_event_type(log: SecurityAuditLog) -> None:
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )
    log.record_event(
        event_type=SecurityEventType.AUTH_FAILED, org_id="org_a",
    )
    log.record_event(
        event_type=SecurityEventType.AUTH_FAILED, org_id="org_a",
    )
    failed = log.list_events(
        org_id="org_a", event_type=SecurityEventType.AUTH_FAILED,
    )
    assert len(failed) == 2


def test_list_filters_by_org(log: SecurityAuditLog) -> None:
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_y", org_id="org_b",
    )
    rows_a = log.list_events(org_id="org_a")
    rows_b = log.list_events(org_id="org_b")
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0].org_id == "org_a"
    assert rows_b[0].org_id == "org_b"


def test_list_filters_by_user(log: SecurityAuditLog) -> None:
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="alice", org_id="org_a",
    )
    log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="bob", org_id="org_a",
    )
    alice_rows = log.list_events(user_id="alice")
    assert len(alice_rows) == 1
    assert alice_rows[0].user_id == "alice"


def test_list_time_range_filter(log: SecurityAuditLog) -> None:
    early = log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )
    time.sleep(0.005)
    cutoff = time.time()
    time.sleep(0.005)
    late = log.record_event(
        event_type=SecurityEventType.AUTH_SUCCEEDED,
        user_id="usr_x", org_id="org_a",
    )
    after_cutoff = log.list_events(org_id="org_a", since=cutoff)
    assert len(after_cutoff) == 1
    assert after_cutoff[0].event_id == late.event_id

    before_cutoff = log.list_events(org_id="org_a", until=cutoff)
    assert len(before_cutoff) == 1
    assert before_cutoff[0].event_id == early.event_id


def test_list_limit_caps_results(log: SecurityAuditLog) -> None:
    for _ in range(20):
        log.record_event(
            event_type=SecurityEventType.AUTH_SUCCEEDED,
            user_id="usr_x", org_id="org_a",
        )
    rows = log.list_events(org_id="org_a", limit=5)
    assert len(rows) == 5


def test_list_limit_must_be_in_range(log: SecurityAuditLog) -> None:
    with pytest.raises(SecurityAuditLogError, match="limit"):
        log.list_events(org_id="org_a", limit=0)
    with pytest.raises(SecurityAuditLogError, match="limit"):
        log.list_events(org_id="org_a", limit=10001)


def test_get_event_round_trips(log: SecurityAuditLog) -> None:
    e = log.record_event(
        event_type=SecurityEventType.API_KEY_REVOKED,
        user_id="alice", org_id="org_a",
        details={"key_id": "key_xyz"},
    )
    same = log.get_event(e.event_id)
    assert same is not None
    assert same.event_id == e.event_id


def test_get_event_unknown_returns_none(log: SecurityAuditLog) -> None:
    assert log.get_event("sec_phantom") is None


# ---------------------------------------------------------------------------
# Append-only invariant (no public mutation API)
# ---------------------------------------------------------------------------


def test_log_has_no_update_or_delete_method() -> None:
    """SOC2 procurement requirement: there is no API path that
    mutates an existing event row. Confirm by inspecting the
    public surface."""
    public_methods = {
        name for name in dir(SecurityAuditLog)
        if not name.startswith("_")
    }
    forbidden = {"update_event", "delete_event", "remove_event",
                 "purge", "truncate", "clear"}
    intersection = public_methods & forbidden
    assert intersection == set(), (
        f"SecurityAuditLog must not expose mutation methods; "
        f"found: {intersection}"
    )


def test_source_contains_no_mutation_sql_for_security_events() -> None:
    """Codex M-19 v1 review tightening: the public-surface check
    above can miss a private helper. Also assert at the source
    level that the module contains no UPDATE / DELETE FROM /
    DROP TABLE on the security_events table.

    A future refactor that smuggles in tamper paths would have to
    fight this test, not just rename a method."""
    from pathlib import Path
    src = Path(
        "src/polaris_graph/audit_ir/security_audit_log.py"
    ).read_text(encoding="utf-8")
    forbidden_patterns = (
        "UPDATE security_events",
        "DELETE FROM security_events",
        "DROP TABLE security_events",
        "DROP TABLE IF EXISTS security_events",
        "TRUNCATE security_events",
    )
    for pat in forbidden_patterns:
        assert pat not in src, (
            f"security_audit_log.py contains forbidden mutation "
            f"SQL: {pat!r}"
        )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_membership_added_event_records(log: SecurityAuditLog) -> None:
    """Codex M-19 v1 review fix: membership_added is now a
    first-class event type (covers auth_store add_membership)."""
    e = log.record_event(
        event_type=SecurityEventType.MEMBERSHIP_ADDED,
        user_id="usr_alice", org_id="org_alpha",
        details={
            "added_user_id": "usr_bob",
            "role": "member",
            "actor": "owner_carol",
        },
    )
    assert e.event_type == SecurityEventType.MEMBERSHIP_ADDED
    assert e.severity == EventSeverity.INFO


def test_membership_removed_event_records(log: SecurityAuditLog) -> None:
    e = log.record_event(
        event_type=SecurityEventType.MEMBERSHIP_REMOVED,
        user_id="usr_alice", org_id="org_alpha",
        details={"removed_user_id": "usr_bob"},
    )
    assert e.event_type == SecurityEventType.MEMBERSHIP_REMOVED


def test_authenticated_events_require_attribution(
    log: SecurityAuditLog,
) -> None:
    """Codex M-19 v1 review fix: SOC2 attribution claim must be
    enforced — authenticated events MUST carry user_id + org_id
    or recording fails."""
    # AUTH_SUCCEEDED without user_id must fail.
    with pytest.raises(SecurityAuditLogError, match="user_id"):
        log.record_event(
            event_type=SecurityEventType.AUTH_SUCCEEDED,
            user_id=None, org_id="org_a",
        )
    # AUTH_SUCCEEDED without org_id must fail.
    with pytest.raises(SecurityAuditLogError, match="org_id"):
        log.record_event(
            event_type=SecurityEventType.AUTH_SUCCEEDED,
            user_id="alice", org_id=None,
        )
    # Cross-tenant denied without attribution must fail.
    with pytest.raises(SecurityAuditLogError):
        log.record_event(
            event_type=SecurityEventType.CROSS_TENANT_DENIED,
            user_id="alice", org_id=None,
        )
    # Membership add without attribution must fail.
    with pytest.raises(SecurityAuditLogError):
        log.record_event(
            event_type=SecurityEventType.MEMBERSHIP_ADDED,
            user_id=None, org_id="org_a",
        )


def test_anonymous_auth_failed_is_allowed(
    log: SecurityAuditLog,
) -> None:
    """AUTH_FAILED is the one anonymous-allowed event — by
    definition the failure means no valid user_id was
    established."""
    e = log.record_event(
        event_type=SecurityEventType.AUTH_FAILED,
        user_id=None, org_id=None,
        source_ip="10.0.0.5",
    )
    assert e.severity == EventSeverity.WARN


def test_event_to_dict_unpacks_details(log: SecurityAuditLog) -> None:
    e = log.record_event(
        event_type=SecurityEventType.AUDIT_BUNDLE_EXPORTED,
        user_id="alice", org_id="org_a",
        details={"slug": "x_drug_y", "size_bytes": 12345},
    )
    payload = event_to_dict(e)
    assert payload["event_type"] == "audit_bundle_exported"
    assert payload["severity"] == "info"
    assert payload["details"]["slug"] == "x_drug_y"
    assert payload["details"]["size_bytes"] == 12345
