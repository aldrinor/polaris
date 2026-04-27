"""Authentication + authorization middleware (M-15b — Phase C).

Per FINAL_PLAN.md Phase C plan v2: the dominant Phase C risk is
cross-tenant leakage. Every M-1..M-13 endpoint that returns a
workspace-scoped resource MUST gate on workspace ownership.
M-15a built the substrate (orgs, users, memberships, API keys);
M-15b is the retrofit.

Architecture:
  - Authentication: API key bearer token in `Authorization`
    header. The plaintext key is verified via
    AuthStore.verify_api_key, which also caps the effective
    role at the user's CURRENT membership role (M-15a v2 fix —
    demoted users can't ride stale keys).
  - Authorization: per-resource FastAPI dependencies:
      - require_authenticated_caller: 401 if no/invalid auth.
      - require_org_member(org_id): 403 if caller's org !=
        org_id.
      - require_workspace_member(workspace_id): looks up
        workspace.org_id, then require_org_member.
      - require_upload_caller(upload_id): looks up upload's
        workspace → org, then require_org_member.
      - require_job_caller(job_id): looks up job.org_id,
        require_org_member.
  - Per LAW II — fails LOUD on every miss (401/403, never silent
    fallthrough).

Test injection:
  - `_set_auth_store_for_tests(store)` swaps the singleton.
  - For unit tests that don't want to mint real API keys, the
    `X-Polaris-Caller` test-only header lets a test caller
    declare `<org_id>:<user_id>:<role>` directly. This header
    is REJECTED in production via the
    `PG_AUTH_TRUSTED_TEST_HEADER` env flag (default off).

Trust model:
  - Production: only Authorization: Bearer <api_key> works.
  - Tests: set PG_AUTH_TRUSTED_TEST_HEADER=1 and use
    X-Polaris-Caller. Never enable in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, Request

from src.polaris_graph.audit_ir.auth_store import (
    AuthStore,
    CredentialError,
    ROLE_RANK,
    role_geq,
)


# ---------------------------------------------------------------------------
# Caller record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Caller:
    """The authenticated principal making a request.

    Attributes:
      user_id: identity.
      org_id: org scope. EVERY authenticated request is bound to
              one org. Cross-org actions require re-authenticating
              with a key for the target org.
      role: effective role. For API-key callers, this is
            already capped by current membership (M-15a v2).
      via: "api_key" | "test_header" — which path authenticated
           the caller. Production should only ever see "api_key".
    """

    user_id: str
    org_id: str
    role: str
    via: str


# ---------------------------------------------------------------------------
# Auth store singleton (test-injectable)
# ---------------------------------------------------------------------------


_AUTH_STORE: AuthStore | None = None
_AUTH_DB_PATH: Path | None = None


def _default_auth_db_path() -> Path:
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    return REPO_ROOT / "state" / "polaris_auth.sqlite"


def get_auth_store() -> AuthStore:
    global _AUTH_STORE
    if _AUTH_STORE is None:
        _AUTH_STORE = AuthStore(_AUTH_DB_PATH or _default_auth_db_path())
    return _AUTH_STORE


def _set_auth_store_for_tests(store: AuthStore | None) -> None:
    """Test hook. Replace the singleton with a tmp_path store."""
    global _AUTH_STORE
    _AUTH_STORE = store


def _set_auth_db_path_for_tests(path: Path | None) -> None:
    global _AUTH_DB_PATH, _AUTH_STORE
    _AUTH_DB_PATH = path
    _AUTH_STORE = None


# ---------------------------------------------------------------------------
# Trusted test header (PROD: must stay off)
# ---------------------------------------------------------------------------


def _test_header_trusted() -> bool:
    """Read PG_AUTH_TRUSTED_TEST_HEADER at call time. ANY truthy
    value enables the X-Polaris-Caller header. Production MUST
    leave this unset.

    Codex M-15b mandate: this flag is the ONE production trap
    door we accept for testability. Treat any commit that flips
    the default to "on" as a security regression.
    """
    return os.environ.get("PG_AUTH_TRUSTED_TEST_HEADER") not in (
        None, "", "0", "false", "False",
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _resolve_api_key_header(authorization: str | None) -> str | None:
    """Extract the bearer plaintext key from an Authorization
    header. Returns None if absent or malformed."""
    if not authorization:
        return None
    parts = authorization.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    scheme, value = parts[0].lower(), parts[1].strip()
    if scheme != "bearer":
        return None
    return value or None


def _resolve_test_caller(header_value: str | None) -> Caller | None:
    """Decode a `X-Polaris-Caller: <org_id>:<user_id>:<role>`
    header. Only honored if PG_AUTH_TRUSTED_TEST_HEADER is on."""
    if not header_value or not _test_header_trusted():
        return None
    parts = header_value.split(":", 2)
    if len(parts) != 3:
        return None
    org_id, user_id, role = (p.strip() for p in parts)
    if not org_id or not user_id or role not in ROLE_RANK:
        return None
    return Caller(
        user_id=user_id, org_id=org_id, role=role, via="test_header",
    )


async def require_authenticated_caller(
    request: Request,
    authorization: str | None = Header(default=None),
    x_polaris_caller: str | None = Header(default=None),
) -> Caller:
    """FastAPI dependency. Resolves the caller via:
       1. X-Polaris-Caller (only when PG_AUTH_TRUSTED_TEST_HEADER
          is on — for tests).
       2. Authorization: Bearer <api_key> via AuthStore.

    Raises 401 if neither path produces a valid caller.

    Stashes the resolved caller on `request.state.caller` so
    downstream dependencies can read without re-resolving.
    """
    # 1. Test header (only if env-trusted).
    test_caller = _resolve_test_caller(x_polaris_caller)
    if test_caller is not None:
        request.state.caller = test_caller
        return test_caller

    # 2. API key bearer.
    plaintext = _resolve_api_key_header(authorization)
    if plaintext is None:
        raise HTTPException(
            status_code=401, detail="missing or malformed Authorization header"
        )
    store = get_auth_store()
    try:
        api_key = store.verify_api_key(plaintext)
    except CredentialError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    caller = Caller(
        user_id=api_key.user_id, org_id=api_key.org_id,
        role=api_key.role, via="api_key",
    )
    request.state.caller = caller
    return caller


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------


def _require_role(caller: Caller, required: str) -> None:
    if not role_geq(caller.role, required):
        raise HTTPException(
            status_code=403,
            detail=(
                f"caller role {caller.role!r} insufficient; "
                f"required {required!r}"
            ),
        )


def require_org_member_of(
    caller: Caller, target_org_id: str, required_role: str = "viewer",
) -> None:
    """Raise 403 if caller is not a member of `target_org_id` with
    at least `required_role`. Same-org check; cross-org access
    is the dominant Phase C failure mode."""
    if caller.org_id != target_org_id:
        # Returns 403, NOT 404, so we don't leak whether the
        # target org exists. Codex M-15b mandate.
        raise HTTPException(
            status_code=403,
            detail="caller does not belong to the target org",
        )
    _require_role(caller, required_role)


# ---------------------------------------------------------------------------
# Dependencies for path-parameterized resources
# ---------------------------------------------------------------------------


def _lookup_workspace_org(workspace_id: str) -> str | None:
    """Resolve workspace_id → org_id. Returns None if unknown."""
    from src.polaris_graph.audit_ir.inspector_router import (
        get_workspace_store,
    )
    store = get_workspace_store()
    ws = store.get_workspace(workspace_id)
    return ws.org_id if ws else None


def _lookup_upload_org(upload_id: str) -> tuple[str, str] | None:
    """Resolve upload_id → (workspace_id, org_id). None if
    unknown."""
    from src.polaris_graph.audit_ir.inspector_router import (
        get_workspace_store,
    )
    store = get_workspace_store()
    upload = store.get_upload(upload_id)
    if upload is None:
        return None
    ws = store.get_workspace(upload.workspace_id)
    if ws is None:
        return None
    return upload.workspace_id, ws.org_id


def _lookup_job_org(job_id: str) -> str | None:
    """Resolve job_id → org_id. Jobs are tagged at enqueue time
    (M-15b extension to JobQueue). Returns None if unknown."""
    from src.polaris_graph.audit_ir.inspector_router import (
        get_job_queue,
    )
    queue = get_job_queue()
    job = queue.get(job_id)
    if job is None:
        return None
    # `org_id` is a metadata column; older jobs without it
    # (pre-M-15b) raise. New code paths set org_id at enqueue.
    return getattr(job, "org_id", None)


# Note: FastAPI dependencies are module-level functions. We
# build them as small wrappers that call the lookup helpers and
# require_org_member_of.


def make_require_workspace_member(required_role: str = "viewer"):
    """Factory: returns a FastAPI dependency that gates on
    `require_org_member_of(caller, workspace.org_id, required_role)`.
    Use as: `Depends(make_require_workspace_member("admin"))`."""
    async def _dep(
        workspace_id: str,
        caller: Caller = (
            await_authenticated_caller_dep()  # placeholder; see below
        ),
    ) -> Caller:
        ...
    raise NotImplementedError(
        "Use the explicit dependency functions below; FastAPI does "
        "not support nested-Depends factories cleanly."
    )


# Direct dependency functions (FastAPI requires top-level shapes).


async def require_workspace_member_viewer(
    workspace_id: str,
    caller: Caller = ...,  # type: ignore[assignment]
) -> Caller:
    """403 if caller is not a viewer+ in the workspace's org.
    NOT a real factory — see _workspace_dep_with_role below."""
    raise NotImplementedError(
        "Use _workspace_dep_with_role at call site"
    )


def _workspace_dep_with_role(required_role: str):
    """Build a FastAPI-compatible dependency closure. The closure
    takes path param `workspace_id` and the authenticated caller,
    looks up the workspace's org, and checks membership."""
    from fastapi import Depends

    async def _dep(
        workspace_id: str,
        caller: Caller = Depends(require_authenticated_caller),
    ) -> Caller:
        org_id = _lookup_workspace_org(workspace_id)
        if org_id is None:
            # 404 NOT 403 here because workspace existence is
            # observable to any authenticated caller via the
            # workspace creation endpoint — listing your own
            # workspaces is fine. We only hide org membership
            # of OTHER orgs' workspaces, which the require_org
            # _member_of below handles.
            raise HTTPException(
                status_code=404, detail=f"unknown workspace: {workspace_id}",
            )
        require_org_member_of(caller, org_id, required_role)
        return caller

    return _dep


def _upload_dep_with_role(required_role: str):
    from fastapi import Depends

    async def _dep(
        upload_id: str,
        caller: Caller = Depends(require_authenticated_caller),
    ) -> Caller:
        result = _lookup_upload_org(upload_id)
        if result is None:
            raise HTTPException(
                status_code=404, detail=f"unknown upload: {upload_id}",
            )
        _, org_id = result
        require_org_member_of(caller, org_id, required_role)
        return caller

    return _dep


def _job_dep_with_role(required_role: str):
    from fastapi import Depends

    async def _dep(
        job_id: str,
        caller: Caller = Depends(require_authenticated_caller),
    ) -> Caller:
        org_id = _lookup_job_org(job_id)
        if org_id is None:
            raise HTTPException(
                status_code=404, detail=f"unknown job_id: {job_id}",
            )
        require_org_member_of(caller, org_id, required_role)
        return caller

    return _dep


# ---------------------------------------------------------------------------
# Convenience: pre-built dependencies for the most common roles
# ---------------------------------------------------------------------------


require_workspace_viewer = _workspace_dep_with_role("viewer")
require_workspace_member = _workspace_dep_with_role("member")
require_workspace_admin = _workspace_dep_with_role("admin")

require_upload_viewer = _upload_dep_with_role("viewer")
require_upload_member = _upload_dep_with_role("member")

require_job_viewer = _job_dep_with_role("viewer")
require_job_member = _job_dep_with_role("member")
