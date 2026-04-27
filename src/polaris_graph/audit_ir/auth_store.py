"""Auth substrate (M-15a — Phase C).

Per FINAL_PLAN.md Phase C deliverable #6: organization-level
RBAC + workspace isolation + billing + quotas. M-15a is the
SUBSTRATE — orgs / users / roles / memberships / API keys.
M-15b (separate milestone) does the endpoint-level authz
retrofit.

Out of scope for M-15a:
  - Endpoint-level enforcement (that's M-15b).
  - SSO / OAuth / SAML (Phase D).
  - Password reset flows (Phase D).
  - Email verification / 2FA (Phase D).

Trust model:
  - org: top-level tenant. All workspaces belong to an org.
  - user: identity. Belongs to one or more orgs via memberships.
  - role: "owner" | "admin" | "member" | "viewer". Higher roles
    subsume lower roles (owner > admin > member > viewer).
  - api_key: machine-to-machine credential, scoped to an org +
    user + (optional) role. Stored as bcrypt hash.

Mirrors M-11 workspace_store patterns:
  - SQLite WAL mode, FK on, per-call connections.
  - `BEGIN IMMEDIATE` transactions for atomic state changes
    (e.g. avoid duplicate-membership races).
  - Frozen dataclass records, store-owned mutators returning new
    snapshots.

Per LAW II — fails LOUD (raises) on:
  - duplicate email / org slug
  - unknown role / role demotion that orphans last owner
  - invalid bcrypt / mismatched API key

Per LAW VI — env-configurable:
  - `PG_BCRYPT_ROUNDS` (default 12)
  - `PG_API_KEY_PREFIX` (default "polaris_")
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import bcrypt


# ---------------------------------------------------------------------------
# Constants + env
# ---------------------------------------------------------------------------


# Roles in priority order (higher index = more privilege).
ROLES: tuple[str, ...] = ("viewer", "member", "admin", "owner")
ROLE_RANK: dict[str, int] = {r: i for i, r in enumerate(ROLES)}

DEFAULT_BCRYPT_ROUNDS = 12
DEFAULT_API_KEY_PREFIX = "polaris_"


def _bcrypt_rounds() -> int:
    """Read PG_BCRYPT_ROUNDS at call time (LAW VI). Garbage values
    fall back to default."""
    raw = os.environ.get("PG_BCRYPT_ROUNDS")
    if raw is None:
        return DEFAULT_BCRYPT_ROUNDS
    try:
        return max(4, min(15, int(raw)))  # bcrypt safe range
    except ValueError:
        return DEFAULT_BCRYPT_ROUNDS


def _api_key_prefix() -> str:
    return os.environ.get("PG_API_KEY_PREFIX", DEFAULT_API_KEY_PREFIX)


# Email regex: pragmatic (rejects obviously malformed, doesn't
# claim full RFC 5322 compliance).
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# Codex M-15a v2 review fix: precomputed dummy bcrypt hash at the
# SAME cost as the production hash (PG_BCRYPT_ROUNDS, default 12)
# so verify_password's unknown-email path takes the same time as
# the known-email path. v1 used cost-4 for the dummy → ~80x faster
# than known-email cost-12 → existence leaked via timing.
#
# The dummy hash is computed lazily per-process. Tests that use
# low cost (e.g. PG_BCRYPT_ROUNDS=4) will see the dummy match the
# test cost on first call.
_DUMMY_HASH_CACHE: dict[int, bytes] = {}


def _dummy_hash_for_current_cost() -> bytes:
    rounds = _bcrypt_rounds()
    cached = _DUMMY_HASH_CACHE.get(rounds)
    if cached is None:
        cached = bcrypt.hashpw(b"dummy_pw", bcrypt.gensalt(rounds=rounds))
        _DUMMY_HASH_CACHE[rounds] = cached
    return cached

# Org slug: lowercase letters, digits, hyphen. 2-64 chars (must
# start AND end with alphanumeric, hyphens only in the middle).
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AuthStoreError(Exception):
    """Base error for auth_store."""


class DuplicateError(AuthStoreError):
    """Raised on duplicate email / org slug / membership."""


class NotFoundError(AuthStoreError):
    """Raised on lookup of a non-existent record."""


class InvalidRoleError(AuthStoreError):
    """Raised on unknown role string OR a role transition that
    would orphan the last owner of an org."""


class CredentialError(AuthStoreError):
    """Raised on invalid password / API key verification."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Org:
    org_id: str
    slug: str  # URL-safe identifier
    name: str  # human-readable
    created_at: float


@dataclass(frozen=True)
class User:
    user_id: str
    email: str  # lowercased, unique
    display_name: str
    created_at: float
    # NOTE: password_hash is stored on the row but never returned
    # to callers. Use `verify_password()` to check.


@dataclass(frozen=True)
class Membership:
    """A user's role within an org. Composite-key
    (org_id, user_id). One row per (org, user) pair."""

    org_id: str
    user_id: str
    role: str  # one of ROLES
    created_at: float


@dataclass(frozen=True)
class ApiKey:
    """A machine-to-machine credential. The plaintext key is shown
    EXACTLY ONCE at creation; only the bcrypt hash is stored.

    Attributes:
      key_id: short prefix ID for log lines + UI display.
      org_id, user_id: scope.
      role: cap on the effective role for this key.
      label: human-readable description (rotation hygiene).
      last_used_at: updated on verify_api_key calls.
      created_at: creation timestamp.
      revoked_at: None unless revoked.
    """

    key_id: str
    org_id: str
    user_id: str
    role: str
    label: str
    last_used_at: float | None
    created_at: float
    revoked_at: float | None


def org_to_dict(o: Org) -> dict[str, Any]:
    return {
        "org_id": o.org_id, "slug": o.slug,
        "name": o.name, "created_at": o.created_at,
    }


def user_to_dict(u: User) -> dict[str, Any]:
    return {
        "user_id": u.user_id, "email": u.email,
        "display_name": u.display_name, "created_at": u.created_at,
    }


def membership_to_dict(m: Membership) -> dict[str, Any]:
    return {
        "org_id": m.org_id, "user_id": m.user_id,
        "role": m.role, "created_at": m.created_at,
    }


def api_key_to_dict(k: ApiKey) -> dict[str, Any]:
    return {
        "key_id": k.key_id, "org_id": k.org_id,
        "user_id": k.user_id, "role": k.role,
        "label": k.label, "last_used_at": k.last_used_at,
        "created_at": k.created_at, "revoked_at": k.revoked_at,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    org_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (org_id, user_id),
    FOREIGN KEY (org_id) REFERENCES orgs(org_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    label TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    last_used_at REAL,
    created_at REAL NOT NULL,
    revoked_at REAL,
    FOREIGN KEY (org_id) REFERENCES orgs(org_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id, revoked_at);
"""


# ---------------------------------------------------------------------------
# AuthStore
# ---------------------------------------------------------------------------


class AuthStore:
    """SQLite-backed auth substrate.

    Per-call connections (matches M-8 JobQueue / M-11
    workspace_store patterns). WAL for concurrent reads. FKs
    enabled.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Orgs
    # ------------------------------------------------------------------

    def create_org(self, slug: str, name: str) -> Org:
        if not _SLUG_RE.match(slug):
            raise AuthStoreError(
                f"invalid org slug: {slug!r}; must match {_SLUG_RE.pattern}"
            )
        if not name or not name.strip():
            raise AuthStoreError("org name must be non-empty")
        org_id = f"org_{uuid.uuid4().hex[:12]}"
        now = time.time()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO orgs (org_id, slug, name, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (org_id, slug, name.strip(), now),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"org slug already in use: {slug!r}") from exc
        return Org(org_id=org_id, slug=slug, name=name.strip(), created_at=now)

    def get_org(self, org_id: str) -> Org | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orgs WHERE org_id = ?", (org_id,),
            ).fetchone()
        return _row_to_org(row) if row else None

    def get_org_by_slug(self, slug: str) -> Org | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orgs WHERE slug = ?", (slug,),
            ).fetchone()
        return _row_to_org(row) if row else None

    def list_orgs(self) -> list[Org]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orgs ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_org(r) for r in rows]

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def create_user(
        self, email: str, display_name: str, password: str,
    ) -> User:
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise AuthStoreError(f"invalid email format: {email!r}")
        if not display_name or not display_name.strip():
            raise AuthStoreError("display_name must be non-empty")
        if not password or len(password) < 8:
            raise AuthStoreError("password must be at least 8 characters")
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = time.time()
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=_bcrypt_rounds())
        ).decode("utf-8")
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, email, display_name, "
                    "password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, email, display_name.strip(), password_hash, now),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"email already in use: {email!r}") from exc
        return User(
            user_id=user_id, email=email,
            display_name=display_name.strip(), created_at=now,
        )

    def get_user(self, user_id: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.strip().lower(),),
            ).fetchone()
        return _row_to_user(row) if row else None

    def verify_password(self, email: str, password: str) -> User:
        """Constant-time password verification. Raises
        CredentialError on any failure (unknown user OR wrong
        password) so a caller cannot distinguish via timing.

        Codex M-15a v2 review fix: the unknown-email path now uses
        a precomputed dummy hash at the SAME bcrypt cost as the
        production hash. v1 used cost-4 dummy → ~80x faster than
        the known-email cost-12 path → existence leaked via
        timing. v2 always checkpw() against a same-cost dummy.
        """
        email = email.strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, email, display_name, password_hash, "
                "created_at FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row is None:
            # Always run bcrypt.checkpw against a SAME-COST dummy
            # hash so unknown-email and wrong-password paths take
            # the same time.
            bcrypt.checkpw(
                password.encode("utf-8"), _dummy_hash_for_current_cost(),
            )
            raise CredentialError("invalid email or password")
        if not bcrypt.checkpw(
            password.encode("utf-8"), row["password_hash"].encode("utf-8")
        ):
            raise CredentialError("invalid email or password")
        return _row_to_user(row)

    # ------------------------------------------------------------------
    # Memberships
    # ------------------------------------------------------------------

    def add_membership(
        self, org_id: str, user_id: str, role: str,
    ) -> Membership:
        if role not in ROLE_RANK:
            raise InvalidRoleError(
                f"unknown role: {role!r}; must be one of {ROLES}"
            )
        with self._connect() as conn:
            # Verify both entities exist via FK; otherwise
            # IntegrityError below.
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Existence checks first for cleaner error messages.
                org_exists = conn.execute(
                    "SELECT 1 FROM orgs WHERE org_id = ?", (org_id,),
                ).fetchone()
                if org_exists is None:
                    conn.execute("ROLLBACK")
                    raise NotFoundError(f"unknown org: {org_id}")
                user_exists = conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (user_id,),
                ).fetchone()
                if user_exists is None:
                    conn.execute("ROLLBACK")
                    raise NotFoundError(f"unknown user: {user_id}")
                now = time.time()
                try:
                    conn.execute(
                        "INSERT INTO memberships (org_id, user_id, "
                        "role, created_at) VALUES (?, ?, ?, ?)",
                        (org_id, user_id, role, now),
                    )
                except sqlite3.IntegrityError as exc:
                    conn.execute("ROLLBACK")
                    raise DuplicateError(
                        f"user {user_id} already a member of org {org_id}"
                    ) from exc
                conn.execute("COMMIT")
            except (NotFoundError, DuplicateError, InvalidRoleError):
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return Membership(
            org_id=org_id, user_id=user_id, role=role, created_at=now,
        )

    def get_membership(
        self, org_id: str, user_id: str,
    ) -> Membership | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memberships WHERE org_id = ? AND user_id = ?",
                (org_id, user_id),
            ).fetchone()
        return _row_to_membership(row) if row else None

    def list_memberships_for_org(self, org_id: str) -> list[Membership]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memberships WHERE org_id = ? "
                "ORDER BY created_at ASC",
                (org_id,),
            ).fetchall()
        return [_row_to_membership(r) for r in rows]

    def list_memberships_for_user(self, user_id: str) -> list[Membership]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memberships WHERE user_id = ? "
                "ORDER BY created_at ASC",
                (user_id,),
            ).fetchall()
        return [_row_to_membership(r) for r in rows]

    def update_membership_role(
        self, org_id: str, user_id: str, new_role: str,
    ) -> Membership:
        if new_role not in ROLE_RANK:
            raise InvalidRoleError(
                f"unknown role: {new_role!r}; must be one of {ROLES}"
            )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM memberships "
                    "WHERE org_id = ? AND user_id = ?",
                    (org_id, user_id),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise NotFoundError(
                        f"no membership for org {org_id} + user {user_id}"
                    )
                old_role = row["role"]
                # Last-owner protection: demoting the last owner
                # leaves the org with no owner. Block.
                if old_role == "owner" and new_role != "owner":
                    owner_count = conn.execute(
                        "SELECT COUNT(*) FROM memberships "
                        "WHERE org_id = ? AND role = 'owner'",
                        (org_id,),
                    ).fetchone()[0]
                    if owner_count <= 1:
                        conn.execute("ROLLBACK")
                        raise InvalidRoleError(
                            f"cannot demote last owner of org {org_id}"
                        )
                conn.execute(
                    "UPDATE memberships SET role = ? "
                    "WHERE org_id = ? AND user_id = ?",
                    (new_role, org_id, user_id),
                )
                conn.execute("COMMIT")
            except (NotFoundError, InvalidRoleError):
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return Membership(
            org_id=org_id, user_id=user_id, role=new_role,
            created_at=row["created_at"],
        )

    def remove_membership(self, org_id: str, user_id: str) -> None:
        """Remove a user from an org. Same last-owner protection
        as update_membership_role."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT role FROM memberships "
                    "WHERE org_id = ? AND user_id = ?",
                    (org_id, user_id),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise NotFoundError(
                        f"no membership for org {org_id} + user {user_id}"
                    )
                if row["role"] == "owner":
                    owner_count = conn.execute(
                        "SELECT COUNT(*) FROM memberships "
                        "WHERE org_id = ? AND role = 'owner'",
                        (org_id,),
                    ).fetchone()[0]
                    if owner_count <= 1:
                        conn.execute("ROLLBACK")
                        raise InvalidRoleError(
                            f"cannot remove last owner of org {org_id}"
                        )
                conn.execute(
                    "DELETE FROM memberships "
                    "WHERE org_id = ? AND user_id = ?",
                    (org_id, user_id),
                )
                conn.execute("COMMIT")
            except (NotFoundError, InvalidRoleError):
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------------
    # API keys
    # ------------------------------------------------------------------

    def create_api_key(
        self, org_id: str, user_id: str, role: str, label: str,
    ) -> tuple[ApiKey, str]:
        """Create a new API key. Returns (ApiKey record, plaintext
        key). The plaintext is shown EXACTLY ONCE — caller must
        display + discard. Storage is bcrypt hash only.

        Validation:
          - role must be a known role.
          - role must NOT exceed the user's current membership
            role (an admin can't mint an owner-scoped key).
          - org + user must have an active membership.

        Codex M-15a v2 review fix: membership read + key insert
        now happen inside ONE BEGIN IMMEDIATE transaction on a
        single connection. v1 split the operations across two
        connections (get_membership + INSERT), creating a TOCTOU
        window where a concurrent demotion/removal could land
        between the check and the insert.
        """
        if role not in ROLE_RANK:
            raise InvalidRoleError(
                f"unknown role: {role!r}; must be one of {ROLES}"
            )
        if not label or not label.strip():
            raise AuthStoreError("api key label must be non-empty")

        # Compute the bcrypt hash OUTSIDE the transaction (it's
        # CPU-bound and slow at production cost; we don't want to
        # hold the SQLite write lock during it).
        key_id = f"akid_{uuid.uuid4().hex[:10]}"
        plaintext = f"{_api_key_prefix()}{secrets.token_urlsafe(32)}"
        key_hash = bcrypt.hashpw(
            plaintext.encode("utf-8"),
            bcrypt.gensalt(rounds=_bcrypt_rounds()),
        ).decode("utf-8")
        now = time.time()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT role FROM memberships "
                    "WHERE org_id = ? AND user_id = ?",
                    (org_id, user_id),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise NotFoundError(
                        f"user {user_id} has no membership in org {org_id}"
                    )
                membership_role = row["role"]
                if ROLE_RANK[role] > ROLE_RANK[membership_role]:
                    conn.execute("ROLLBACK")
                    raise InvalidRoleError(
                        f"requested role {role!r} exceeds user's "
                        f"membership role {membership_role!r}"
                    )
                conn.execute(
                    "INSERT INTO api_keys (key_id, org_id, user_id, role, "
                    "label, key_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (key_id, org_id, user_id, role, label.strip(),
                     key_hash, now),
                )
                conn.execute("COMMIT")
            except (NotFoundError, InvalidRoleError):
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise

        record = ApiKey(
            key_id=key_id, org_id=org_id, user_id=user_id,
            role=role, label=label.strip(),
            last_used_at=None, created_at=now, revoked_at=None,
        )
        return record, plaintext

    def list_api_keys_for_org(self, org_id: str) -> list[ApiKey]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE org_id = ? "
                "ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
        return [_row_to_api_key(r) for r in rows]

    def verify_api_key(self, plaintext: str) -> ApiKey:
        """Verify an inbound API key and return its ApiKey record
        with the EFFECTIVE role.

        Codex M-15a v2 review fix: the returned `role` is capped
        by the user's CURRENT membership role at verification
        time, not the role stored at issuance. v1 returned the
        issuance-time role, which let a demoted/removed user
        keep elevated machine access via stale keys. v2:
          - If no current membership exists for (key.org_id,
            key.user_id), raise CredentialError (key is "valid"
            but the principal no longer belongs to the org).
          - Otherwise return ApiKey with role = min(stored role,
            current membership role).

        Raises CredentialError if the key is unknown / revoked /
        wrong format / membership absent.

        Linear bcrypt scan over non-revoked rows; Phase D adds a
        prefix index for O(1) lookup. Updates last_used_at on
        success.
        """
        if not plaintext or not plaintext.startswith(_api_key_prefix()):
            raise CredentialError("invalid api key format")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE revoked_at IS NULL"
            ).fetchall()
            for row in rows:
                if bcrypt.checkpw(
                    plaintext.encode("utf-8"),
                    row["key_hash"].encode("utf-8"),
                ):
                    # Codex M-15a v2: re-resolve membership and
                    # cap effective role.
                    membership_row = conn.execute(
                        "SELECT role FROM memberships "
                        "WHERE org_id = ? AND user_id = ?",
                        (row["org_id"], row["user_id"]),
                    ).fetchone()
                    if membership_row is None:
                        # User is no longer a member. Key is
                        # effectively dead — fail loud.
                        raise CredentialError(
                            "api key principal no longer has membership"
                        )
                    membership_role = membership_row["role"]
                    stored_role = row["role"]
                    # Effective role = min of stored vs current.
                    if ROLE_RANK[membership_role] < ROLE_RANK[stored_role]:
                        effective_role = membership_role
                    else:
                        effective_role = stored_role
                    # Update last_used_at.
                    now = time.time()
                    conn.execute(
                        "UPDATE api_keys SET last_used_at = ? "
                        "WHERE key_id = ?",
                        (now, row["key_id"]),
                    )
                    return _row_to_api_key(
                        row,
                        last_used_override=now,
                        role_override=effective_role,
                    )
        raise CredentialError("invalid api key")

    def revoke_api_key(self, key_id: str) -> ApiKey:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_id = ?", (key_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"unknown api key: {key_id}")
            if row["revoked_at"] is not None:
                # Idempotent — return existing record.
                return _row_to_api_key(row)
            now = time.time()
            conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE key_id = ?",
                (now, key_id),
            )
        return _row_to_api_key(row, revoked_at_override=now)


# ---------------------------------------------------------------------------
# Internal row converters
# ---------------------------------------------------------------------------


def _row_to_org(row: sqlite3.Row) -> Org:
    return Org(
        org_id=row["org_id"], slug=row["slug"],
        name=row["name"], created_at=row["created_at"],
    )


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        user_id=row["user_id"], email=row["email"],
        display_name=row["display_name"],
        created_at=row["created_at"],
    )


def _row_to_membership(row: sqlite3.Row) -> Membership:
    return Membership(
        org_id=row["org_id"], user_id=row["user_id"],
        role=row["role"], created_at=row["created_at"],
    )


def _row_to_api_key(
    row: sqlite3.Row,
    last_used_override: float | None = None,
    revoked_at_override: float | None = None,
    role_override: str | None = None,
) -> ApiKey:
    """Codex M-15a v2 review fix: `role_override` lets
    verify_api_key() return the EFFECTIVE role (capped by current
    membership) rather than the issuance-time stored role."""
    return ApiKey(
        key_id=row["key_id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        role=role_override if role_override is not None else row["role"],
        label=row["label"],
        last_used_at=last_used_override
        if last_used_override is not None else row["last_used_at"],
        created_at=row["created_at"],
        revoked_at=revoked_at_override
        if revoked_at_override is not None else row["revoked_at"],
    )


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------


def role_geq(actual: str, required: str) -> bool:
    """Return True if `actual` has at least the privilege of
    `required`. Used by the M-15b authz retrofit to gate
    endpoints."""
    if actual not in ROLE_RANK:
        return False
    if required not in ROLE_RANK:
        return False
    return ROLE_RANK[actual] >= ROLE_RANK[required]
