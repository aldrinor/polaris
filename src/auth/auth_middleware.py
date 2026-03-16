"""POLARIS Auth Middleware — FastAPI dependencies for authentication and RBAC."""

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.auth_manager import (
    AUTH_ENABLED,
    AuthManager,
    Role,
    TokenPayload,
)

# Singleton auth manager
_auth_manager: Optional[AuthManager] = None

def get_auth_manager() -> AuthManager:
    """Get or create the singleton AuthManager."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenPayload]:
    """Extract and validate user from Authorization header.

    When auth is disabled, returns None (all requests allowed).
    When auth is enabled, requires valid Bearer token.
    """
    if not AUTH_ENABLED:
        return None

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    auth_mgr = get_auth_manager()
    payload = auth_mgr.validate_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


def require_role(*roles: Role):
    """Dependency that checks if the current user has one of the required roles.

    Usage:
        @app.get("/admin", dependencies=[Depends(require_role(Role.ADMIN))])
    """
    async def _check_role(
        user: Optional[TokenPayload] = Depends(get_current_user),
    ):
        if not AUTH_ENABLED:
            return  # Auth disabled, skip check
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_role = Role(user.role)
        auth_mgr = get_auth_manager()
        for role in roles:
            if auth_mgr.check_permission(user_role, role.value):
                return
        # Check direct role match
        if user_role in roles:
            return
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required: {[r.value for r in roles]}",
        )
    return _check_role


def require_action(action: str):
    """Dependency that checks if the current user can perform a specific action.

    Usage:
        @app.post("/api/research", dependencies=[Depends(require_action("start_research"))])
    """
    async def _check_action(
        user: Optional[TokenPayload] = Depends(get_current_user),
    ):
        if not AUTH_ENABLED:
            return  # Auth disabled, skip check
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        auth_mgr = get_auth_manager()
        user_role = Role(user.role)
        if not auth_mgr.check_permission(user_role, action):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied for action: {action}",
            )
    return _check_action
