"""Tests for src/polaris_graph/audit_ir/auth_store.py (M-15a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.auth_store import (
    ROLES,
    ROLE_RANK,
    AuthStore,
    AuthStoreError,
    CredentialError,
    DuplicateError,
    InvalidRoleError,
    NotFoundError,
    role_geq,
)


@pytest.fixture
def store(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "auth.sqlite")


# ---------------------------------------------------------------------------
# Orgs
# ---------------------------------------------------------------------------


def test_create_org(store: AuthStore) -> None:
    org = store.create_org("acme", "Acme Corp")
    assert org.org_id.startswith("org_")
    assert org.slug == "acme"
    assert org.name == "Acme Corp"
    assert org.created_at > 0


def test_create_org_rejects_invalid_slug(store: AuthStore) -> None:
    for bad in ("Ac me", "ACME", "ac-", "-ac", "a", ""):
        with pytest.raises(AuthStoreError, match="invalid org slug"):
            store.create_org(bad, "x")


def test_create_org_rejects_empty_name(store: AuthStore) -> None:
    with pytest.raises(AuthStoreError, match="non-empty"):
        store.create_org("acme", "")
    with pytest.raises(AuthStoreError, match="non-empty"):
        store.create_org("acme", "   ")


def test_create_org_duplicate_slug(store: AuthStore) -> None:
    store.create_org("acme", "Acme")
    with pytest.raises(DuplicateError, match="already in use"):
        store.create_org("acme", "Acme 2")


def test_get_org_by_slug_and_id(store: AuthStore) -> None:
    org = store.create_org("acme", "Acme")
    assert store.get_org(org.org_id) == org
    assert store.get_org_by_slug("acme") == org
    assert store.get_org("nonexistent") is None
    assert store.get_org_by_slug("nope") is None


def test_list_orgs_recent_first(store: AuthStore) -> None:
    a = store.create_org("aa", "A")
    b = store.create_org("bb", "B")
    listed = store.list_orgs()
    assert [o.org_id for o in listed][:2] == [b.org_id, a.org_id]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_create_user(store: AuthStore) -> None:
    user = store.create_user("u@example.com", "U Person", "password1234")
    assert user.user_id.startswith("usr_")
    assert user.email == "u@example.com"
    assert user.display_name == "U Person"


def test_create_user_normalizes_email_case(store: AuthStore) -> None:
    user = store.create_user("MIXED@Example.com", "M", "password1234")
    assert user.email == "mixed@example.com"


def test_create_user_rejects_invalid_email(store: AuthStore) -> None:
    for bad in ("not-an-email", "@example.com", "user@", "user@x"):
        with pytest.raises(AuthStoreError, match="invalid email"):
            store.create_user(bad, "x", "password1234")


def test_create_user_rejects_short_password(store: AuthStore) -> None:
    with pytest.raises(AuthStoreError, match="at least 8"):
        store.create_user("u@example.com", "U", "short")


def test_create_user_duplicate_email(store: AuthStore) -> None:
    store.create_user("u@example.com", "U", "password1234")
    with pytest.raises(DuplicateError, match="already in use"):
        store.create_user("U@EXAMPLE.com", "U2", "password5678")


def test_verify_password_success(store: AuthStore) -> None:
    user = store.create_user("u@example.com", "U", "secretpass123")
    verified = store.verify_password("u@example.com", "secretpass123")
    assert verified.user_id == user.user_id


def test_verify_password_wrong_password(store: AuthStore) -> None:
    store.create_user("u@example.com", "U", "secretpass123")
    with pytest.raises(CredentialError, match="invalid email or password"):
        store.verify_password("u@example.com", "wrongpass123")


def test_verify_password_unknown_user_raises_credential_error(store: AuthStore) -> None:
    """Per LAW II + timing-safety: unknown email returns same error
    as wrong password (no existence-leak via error string)."""
    with pytest.raises(CredentialError, match="invalid email or password"):
        store.verify_password("nobody@example.com", "anypass1234")


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------


def _make_org_user(store: AuthStore) -> tuple[str, str]:
    org = store.create_org("acme", "Acme")
    user = store.create_user("u@example.com", "U", "password1234")
    return org.org_id, user.user_id


def test_add_membership(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    m = store.add_membership(org_id, user_id, "owner")
    assert m.org_id == org_id
    assert m.user_id == user_id
    assert m.role == "owner"


def test_add_membership_unknown_org(store: AuthStore) -> None:
    user = store.create_user("u@example.com", "U", "password1234")
    with pytest.raises(NotFoundError, match="unknown org"):
        store.add_membership("org_nope", user.user_id, "member")


def test_add_membership_unknown_user(store: AuthStore) -> None:
    org = store.create_org("acme", "Acme")
    with pytest.raises(NotFoundError, match="unknown user"):
        store.add_membership(org.org_id, "usr_nope", "member")


def test_add_membership_unknown_role(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    with pytest.raises(InvalidRoleError, match="unknown role"):
        store.add_membership(org_id, user_id, "superadmin")


def test_add_membership_duplicate(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(DuplicateError, match="already a member"):
        store.add_membership(org_id, user_id, "admin")


def test_get_membership(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    m = store.get_membership(org_id, user_id)
    assert m is not None
    assert m.role == "owner"
    assert store.get_membership(org_id, "usr_other") is None


def test_list_memberships_for_org_and_user(store: AuthStore) -> None:
    org_a = store.create_org("aa", "A")
    org_b = store.create_org("bb", "B")
    user_1 = store.create_user("u1@example.com", "U1", "password1234")
    user_2 = store.create_user("u2@example.com", "U2", "password1234")
    store.add_membership(org_a.org_id, user_1.user_id, "owner")
    store.add_membership(org_a.org_id, user_2.user_id, "member")
    store.add_membership(org_b.org_id, user_1.user_id, "viewer")

    a_members = store.list_memberships_for_org(org_a.org_id)
    assert {m.user_id for m in a_members} == {user_1.user_id, user_2.user_id}

    u1_orgs = store.list_memberships_for_user(user_1.user_id)
    assert {m.org_id for m in u1_orgs} == {org_a.org_id, org_b.org_id}


def test_update_membership_role(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    other = store.create_user("u2@example.com", "U2", "password1234")
    store.add_membership(org_id, other.user_id, "member")
    m = store.update_membership_role(org_id, other.user_id, "admin")
    assert m.role == "admin"


def test_update_membership_role_unknown(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    with pytest.raises(NotFoundError, match="no membership"):
        store.update_membership_role(org_id, user_id, "member")


def test_update_membership_role_unknown_role(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(InvalidRoleError, match="unknown role"):
        store.update_membership_role(org_id, user_id, "superadmin")


def test_update_membership_role_blocks_last_owner_demotion(store: AuthStore) -> None:
    """LAW II: an org without an owner is a permission-graveyard.
    Demoting the LAST owner must fail loud."""
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(InvalidRoleError, match="last owner"):
        store.update_membership_role(org_id, user_id, "admin")


def test_update_membership_role_allows_demotion_when_other_owner_exists(
    store: AuthStore,
) -> None:
    org_id, user_id = _make_org_user(store)
    other = store.create_user("u2@example.com", "U2", "password1234")
    store.add_membership(org_id, user_id, "owner")
    store.add_membership(org_id, other.user_id, "owner")
    # Now there are two owners, demoting one is allowed.
    m = store.update_membership_role(org_id, user_id, "admin")
    assert m.role == "admin"


def test_remove_membership(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    other = store.create_user("u2@example.com", "U2", "password1234")
    store.add_membership(org_id, other.user_id, "admin")
    store.remove_membership(org_id, other.user_id)
    assert store.get_membership(org_id, other.user_id) is None


def test_remove_membership_blocks_last_owner(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(InvalidRoleError, match="last owner"):
        store.remove_membership(org_id, user_id)


def test_remove_membership_unknown(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    with pytest.raises(NotFoundError, match="no membership"):
        store.remove_membership(org_id, user_id)


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def test_create_api_key_returns_plaintext_once(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    record, plaintext = store.create_api_key(
        org_id, user_id, "admin", "ci pipeline",
    )
    assert record.role == "admin"
    assert record.label == "ci pipeline"
    assert record.revoked_at is None
    assert plaintext.startswith("polaris_")
    # Plaintext should be substantial entropy.
    assert len(plaintext) > 40


def test_create_api_key_role_capped_at_membership(store: AuthStore) -> None:
    """An admin can't mint an owner-scoped key. LAW II — fails
    LOUD instead of silently downgrading."""
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "admin")
    with pytest.raises(InvalidRoleError, match="exceeds user's membership"):
        store.create_api_key(org_id, user_id, "owner", "exploit")


def test_create_api_key_unknown_role(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(InvalidRoleError, match="unknown role"):
        store.create_api_key(org_id, user_id, "superadmin", "label")


def test_create_api_key_no_membership(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    # No membership added.
    with pytest.raises(NotFoundError, match="no membership"):
        store.create_api_key(org_id, user_id, "admin", "label")


def test_create_api_key_empty_label(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    with pytest.raises(AuthStoreError, match="non-empty"):
        store.create_api_key(org_id, user_id, "admin", "")


def test_verify_api_key_success(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    record, plaintext = store.create_api_key(
        org_id, user_id, "admin", "ci",
    )
    verified = store.verify_api_key(plaintext)
    assert verified.key_id == record.key_id
    assert verified.last_used_at is not None


def test_verify_api_key_wrong_key(store: AuthStore) -> None:
    with pytest.raises(CredentialError, match="invalid api key"):
        store.verify_api_key("polaris_totally_made_up")


def test_verify_api_key_invalid_format(store: AuthStore) -> None:
    with pytest.raises(CredentialError, match="invalid api key format"):
        store.verify_api_key("not-a-key")
    with pytest.raises(CredentialError, match="invalid api key format"):
        store.verify_api_key("")


def test_verify_api_key_revoked(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    record, plaintext = store.create_api_key(
        org_id, user_id, "admin", "ci",
    )
    store.revoke_api_key(record.key_id)
    with pytest.raises(CredentialError, match="invalid api key"):
        store.verify_api_key(plaintext)


def test_revoke_api_key_idempotent(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    record, _ = store.create_api_key(org_id, user_id, "admin", "ci")
    revoked = store.revoke_api_key(record.key_id)
    assert revoked.revoked_at is not None
    # Second revoke returns same record.
    revoked2 = store.revoke_api_key(record.key_id)
    assert revoked2.revoked_at == revoked.revoked_at


def test_revoke_unknown_api_key(store: AuthStore) -> None:
    with pytest.raises(NotFoundError, match="unknown api key"):
        store.revoke_api_key("akid_nope")


def test_list_api_keys_for_org(store: AuthStore) -> None:
    org_id, user_id = _make_org_user(store)
    store.add_membership(org_id, user_id, "owner")
    store.create_api_key(org_id, user_id, "admin", "ci-1")
    store.create_api_key(org_id, user_id, "viewer", "ci-2")
    keys = store.list_api_keys_for_org(org_id)
    assert {k.label for k in keys} == {"ci-1", "ci-2"}


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------


def test_role_rank_ordering() -> None:
    assert ROLE_RANK["owner"] > ROLE_RANK["admin"]
    assert ROLE_RANK["admin"] > ROLE_RANK["member"]
    assert ROLE_RANK["member"] > ROLE_RANK["viewer"]


def test_role_geq() -> None:
    assert role_geq("owner", "viewer") is True
    assert role_geq("admin", "admin") is True
    assert role_geq("viewer", "member") is False
    assert role_geq("member", "owner") is False
    assert role_geq("nope", "viewer") is False
    assert role_geq("viewer", "nope") is False


def test_roles_tuple_complete() -> None:
    assert set(ROLES) == {"owner", "admin", "member", "viewer"}


# ---------------------------------------------------------------------------
# Codex M-15a v2 review regressions
# ---------------------------------------------------------------------------


def test_verify_api_key_caps_role_at_current_membership(store: AuthStore) -> None:
    """Codex M-15a v1 bug: API key minted as owner; user later
    demoted to admin. v1 verify_api_key returned role='owner'
    (stale issuance-time value). v2 caps the effective role at
    the user's CURRENT membership role."""
    org = store.create_org("acme", "Acme")
    user = store.create_user("u@example.com", "U", "password1234")
    other = store.create_user("o@example.com", "O", "password1234")
    store.add_membership(org.org_id, user.org_id if False else user.user_id, "owner")
    store.add_membership(org.org_id, other.user_id, "owner")
    # Mint owner-scoped key.
    record, plaintext = store.create_api_key(
        org.org_id, user.user_id, "owner", "ci",
    )
    # Now demote user to admin (other owner exists, so allowed).
    store.update_membership_role(org.org_id, user.user_id, "admin")
    # Verifying the key should return EFFECTIVE role 'admin', not
    # the stale stored 'owner'.
    verified = store.verify_api_key(plaintext)
    assert verified.role == "admin", (
        f"v2 must cap effective role at current membership; "
        f"got {verified.role}"
    )


def test_verify_api_key_caps_at_member_role_after_demote(store: AuthStore) -> None:
    """Same as above but demoting from admin to member."""
    org = store.create_org("acme", "Acme")
    owner = store.create_user("o@example.com", "O", "password1234")
    user = store.create_user("u@example.com", "U", "password1234")
    store.add_membership(org.org_id, owner.user_id, "owner")
    store.add_membership(org.org_id, user.user_id, "admin")
    record, plaintext = store.create_api_key(
        org.org_id, user.user_id, "admin", "ci",
    )
    store.update_membership_role(org.org_id, user.user_id, "member")
    verified = store.verify_api_key(plaintext)
    assert verified.role == "member"


def test_verify_api_key_fails_after_membership_removed(store: AuthStore) -> None:
    """Codex M-15a v1 bug: removed user keeps usable API keys.
    v2: if the principal has no current membership, fail loud."""
    org = store.create_org("acme", "Acme")
    owner = store.create_user("o@example.com", "O", "password1234")
    user = store.create_user("u@example.com", "U", "password1234")
    store.add_membership(org.org_id, owner.user_id, "owner")
    store.add_membership(org.org_id, user.user_id, "admin")
    _, plaintext = store.create_api_key(
        org.org_id, user.user_id, "admin", "ci",
    )
    # Now remove user's membership (owner remains; allowed).
    store.remove_membership(org.org_id, user.user_id)
    with pytest.raises(CredentialError, match="no longer has membership"):
        store.verify_api_key(plaintext)


def test_verify_api_key_does_not_upgrade_role(store: AuthStore) -> None:
    """If user was promoted AFTER key issuance, the key's stored
    role still caps the effective role (key's `min(stored,
    current)` logic). I.e. promoting a user does NOT silently
    promote pre-existing keys."""
    org = store.create_org("acme", "Acme")
    user = store.create_user("u@example.com", "U", "password1234")
    store.add_membership(org.org_id, user.user_id, "admin")
    _, plaintext = store.create_api_key(
        org.org_id, user.user_id, "member", "old key",
    )
    # Promote user to owner.
    store.update_membership_role(org.org_id, user.user_id, "owner")
    # Key was minted as 'member'; effective role = min(member, owner) = member.
    verified = store.verify_api_key(plaintext)
    assert verified.role == "member"


def test_create_api_key_atomic_with_membership_check(store: AuthStore) -> None:
    """Codex M-15a v2 review fix: membership check + key insert
    happen in one BEGIN IMMEDIATE transaction. Hard to simulate
    the race in a single-threaded test, but we can verify that
    the transaction is real by ensuring NotFoundError is raised
    cleanly when the membership doesn't exist BEFORE the call."""
    org = store.create_org("acme", "Acme")
    user = store.create_user("u@example.com", "U", "password1234")
    # No membership added.
    with pytest.raises(NotFoundError, match="no membership"):
        store.create_api_key(org.org_id, user.user_id, "admin", "ci")
    # Verify no orphaned api_keys row was inserted.
    keys = store.list_api_keys_for_org(org.org_id)
    assert keys == []


def test_verify_password_unknown_email_uses_production_cost(
    store: AuthStore, monkeypatch,
) -> None:
    """Codex M-15a v2 review fix: unknown-email path now uses a
    precomputed dummy hash at PRODUCTION-equivalent bcrypt cost.
    v1 used cost-4, leaking existence via timing. We can't measure
    timing reliably in a test, but we CAN assert the dummy hash
    cache is populated at the current cost after a verify call."""
    from src.polaris_graph.audit_ir.auth_store import (
        _DUMMY_HASH_CACHE,
        _bcrypt_rounds,
    )
    # Reset cache to ensure clean assertion.
    _DUMMY_HASH_CACHE.clear()
    # Trigger the unknown-email path.
    with pytest.raises(CredentialError):
        store.verify_password("never_seen@example.com", "anypass1234")
    # The cache should now contain a hash at the current bcrypt
    # cost.
    expected_cost = _bcrypt_rounds()
    assert expected_cost in _DUMMY_HASH_CACHE
    # The hash should be a real bcrypt hash at the expected cost
    # (bcrypt encodes cost in the prefix: $2b$<cost>$...)
    cached = _DUMMY_HASH_CACHE[expected_cost].decode("utf-8")
    assert cached.startswith(f"$2b${expected_cost:02d}$"), (
        f"dummy hash cost mismatch: {cached[:10]} expected $2b${expected_cost:02d}$"
    )
