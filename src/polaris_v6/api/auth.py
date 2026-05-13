"""I-carney-004 — static-accounts auth + HS256 JWT.

Pattern (Carney-demo scope):
- Operator-curated YAML at `${POLARIS_STATIC_ACCOUNTS_PATH:-/app/config/static_accounts.yaml}`
  with bcrypt-hashed passwords + role.
- POST /auth/login → 12-hour HS256 JWT signed with POLARIS_JWT_SECRET.
- `require_auth` FastAPI dependency injects on all routes except an allowlist
  (/health, /transparency*, /auth/login).

LAW II: missing POLARIS_JWT_SECRET at app startup → fail-loud RuntimeError.
Never silently allow unauthenticated traffic.

Phase-2: replace with Cognito/Okta when the demo gives way to long-term use.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 12

# Paths exempt from auth — health probes + reviewer-visible transparency.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/transparency",
    "/auth/login",
    "/docs",       # FastAPI's own OpenAPI UI
    "/redoc",
    "/openapi.json",
)

DEFAULT_ACCOUNTS_PATH = "/app/config/static_accounts.yaml"

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in: int  # seconds


class User(BaseModel):
    username: str
    role: str


def _load_accounts() -> list[dict[str, Any]]:
    """Read the static-accounts YAML. Raises RuntimeError if missing.

    LAW II: never silently default to an empty account list (which would
    behave as 'allow nobody' but the operator would not realize the file
    was missing).
    """
    path = Path(os.environ.get("POLARIS_STATIC_ACCOUNTS_PATH", DEFAULT_ACCOUNTS_PATH))
    if not path.exists():
        raise RuntimeError(
            f"static_accounts.yaml not found at {path}. Set "
            "POLARIS_STATIC_ACCOUNTS_PATH or mount the file. The application "
            "refuses to start without the auth substrate (LAW II)."
        )
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict) or not isinstance(body.get("accounts"), list):
        raise RuntimeError(f"static_accounts.yaml at {path} must have top-level 'accounts' list")
    return body["accounts"]


def _jwt_secret() -> str:
    secret = os.environ.get("POLARIS_JWT_SECRET", "").strip()
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "POLARIS_JWT_SECRET env var missing or too short (<32 chars). "
            "Application refuses to issue tokens with a weak/missing key (LAW II). "
            "Set via AWS Secrets Manager → cloud-init → .env per I-carney-004."
        )
    return secret


def verify_app_startup() -> None:
    """Called at FastAPI app create_app() time. Fail loud if auth substrate
    is misconfigured. Per LAW II, we never start an auth-gated app with a
    broken auth gate.

    Skipped when POLARIS_AUTH_DISABLED=1 (Phase-0 demo + tests).
    """
    if os.environ.get("POLARIS_AUTH_DISABLED", "") == "1":
        return
    _jwt_secret()
    _load_accounts()  # raises if YAML missing or malformed


def issue_token(username: str, role: str) -> tuple[str, int]:
    """Returns (jwt, expires_in_seconds)."""
    expires_in = JWT_EXPIRY_HOURS * 3600
    payload = {
        "sub": username,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def _path_is_public(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


async def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> User | None:
    """Global FastAPI dependency. None on public paths; raises 401 otherwise.

    Phase-0 demo: POLARIS_AUTH_DISABLED=1 short-circuits to None (auth off).
    """
    if os.environ.get("POLARIS_AUTH_DISABLED", "") == "1":
        return None
    if _path_is_public(request.url.path):
        return None
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_bearer_token", "message": "Authorization: Bearer <jwt> required"},
        )
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": str(exc)},
        ) from exc
    return User(username=payload["sub"], role=payload.get("role", "reviewer"))


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    accounts = _load_accounts()
    for account in accounts:
        if account.get("username") == payload.username:
            hashed = account.get("password_bcrypt", "")
            if hashed and _pwd_ctx.verify(payload.password, hashed):
                token, exp_in = issue_token(payload.username, account.get("role", "reviewer"))
                return LoginResponse(
                    access_token=token,
                    role=account.get("role", "reviewer"),
                    expires_in=exp_in,
                )
            break
    # Constant-time-ish failure shape (don't leak whether username exists).
    raise HTTPException(
        status_code=401,
        detail={"error": "invalid_credentials"},
    )


def generate_strong_secret(n_bytes: int = 48) -> str:
    """Helper for operator scripts: 64-char URL-safe random secret."""
    return secrets.token_urlsafe(n_bytes)
