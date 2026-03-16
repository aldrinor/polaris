"""POLARIS Auth Routes — Login, logout, user management endpoints."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.auth.auth_manager import AUTH_ENABLED, Role
from src.auth.auth_middleware import (
    get_auth_manager,
    get_current_user,
    require_action,
    require_role,
    TokenPayload,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    expires_in_hours: int


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=8, max_length=200)
    role: str = Field(default="researcher", pattern="^(researcher|manager|admin|auditor)$")


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(researcher|manager|admin|auditor)$")


@router.get("/status")
async def auth_status():
    """Check if authentication is enabled."""
    return {
        "auth_enabled": AUTH_ENABLED,
        "provider": os.getenv("POLARIS_AUTH_PROVIDER", "local"),
    }


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate and receive a token."""
    if not AUTH_ENABLED:
        raise HTTPException(400, "Authentication is disabled. Set POLARIS_AUTH_ENABLED=1 to enable.")

    auth_mgr = get_auth_manager()
    user = auth_mgr.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(401, "Invalid username or password")

    token = auth_mgr.create_token(user)
    token_expiry = int(os.getenv("POLARIS_AUTH_TOKEN_EXPIRY_HOURS", "24"))
    return LoginResponse(
        token=token,
        username=user.username,
        role=user.role.value,
        expires_in_hours=token_expiry,
    )


@router.get("/me")
async def get_me(user: Optional[TokenPayload] = Depends(get_current_user)):
    """Get current user info."""
    if not AUTH_ENABLED:
        return {"auth_enabled": False, "message": "Auth disabled, all access granted"}
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
    }


@router.post("/users", dependencies=[Depends(require_action("manage_users"))])
async def create_user(body: CreateUserRequest):
    """Create a new user (admin only)."""
    auth_mgr = get_auth_manager()
    try:
        user = auth_mgr.create_user(
            username=body.username,
            email=body.email,
            password=body.password,
            role=Role(body.role),
        )
        return {"user_id": user.user_id, "username": user.username, "role": user.role.value}
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/users", dependencies=[Depends(require_action("manage_users"))])
async def list_users():
    """List all users (admin only)."""
    auth_mgr = get_auth_manager()
    return {"users": auth_mgr.list_users()}


@router.patch("/users/{user_id}/role", dependencies=[Depends(require_action("manage_users"))])
async def update_role(user_id: str, body: UpdateRoleRequest):
    """Update a user's role (admin only)."""
    auth_mgr = get_auth_manager()
    user = auth_mgr.update_user_role(user_id, Role(body.role))
    if user is None:
        raise HTTPException(404, "User not found")
    return {"user_id": user.user_id, "role": user.role.value}


@router.delete("/users/{user_id}", dependencies=[Depends(require_action("manage_users"))])
async def deactivate_user(user_id: str):
    """Deactivate a user (admin only)."""
    auth_mgr = get_auth_manager()
    if not auth_mgr.deactivate_user(user_id):
        raise HTTPException(404, "User not found")
    return {"status": "deactivated", "user_id": user_id}
