"""POLARIS Authentication Manager — JWT-based auth with SSO support."""

import os
import hashlib
import hmac
import json
import time
import uuid
import base64
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# --- Configuration from environment (LAW VI) ---
AUTH_ENABLED = os.getenv("POLARIS_AUTH_ENABLED", "0") == "1"
AUTH_SECRET_KEY = os.getenv("POLARIS_AUTH_SECRET", "polaris-dev-secret-change-in-production")
AUTH_TOKEN_EXPIRY = int(os.getenv("POLARIS_AUTH_TOKEN_EXPIRY_HOURS", "24"))
AUTH_PROVIDER = os.getenv("POLARIS_AUTH_PROVIDER", "local")  # local | okta | azure_ad | google
AUTH_SSO_CLIENT_ID = os.getenv("POLARIS_SSO_CLIENT_ID", "")
AUTH_SSO_CLIENT_SECRET = os.getenv("POLARIS_SSO_CLIENT_SECRET", "")
AUTH_SSO_ISSUER_URL = os.getenv("POLARIS_SSO_ISSUER_URL", "")
USERS_FILE = Path(os.getenv("POLARIS_USERS_FILE", "state/users.json"))


class Role(str, Enum):
    """RBAC roles for POLARIS users."""
    RESEARCHER = "researcher"   # Can start research, view results
    MANAGER = "manager"         # Can review all results, export reports
    ADMIN = "admin"             # Can configure settings, manage users
    AUDITOR = "auditor"         # Read-only access to traces and audit logs


# Role hierarchy: higher roles inherit lower role permissions
ROLE_HIERARCHY = {
    Role.AUDITOR: {Role.AUDITOR},
    Role.RESEARCHER: {Role.RESEARCHER},
    Role.MANAGER: {Role.MANAGER, Role.RESEARCHER},
    Role.ADMIN: {Role.ADMIN, Role.MANAGER, Role.RESEARCHER, Role.AUDITOR},
}

# Endpoint-level permissions
ENDPOINT_PERMISSIONS = {
    "start_research": {Role.RESEARCHER, Role.MANAGER, Role.ADMIN},
    "cancel_research": {Role.RESEARCHER, Role.MANAGER, Role.ADMIN},
    "view_status": {Role.RESEARCHER, Role.MANAGER, Role.ADMIN, Role.AUDITOR},
    "view_result": {Role.RESEARCHER, Role.MANAGER, Role.ADMIN, Role.AUDITOR},
    "export_pdf": {Role.MANAGER, Role.ADMIN},
    "view_trace": {Role.AUDITOR, Role.ADMIN},
    "view_cost": {Role.MANAGER, Role.ADMIN, Role.AUDITOR},
    "manage_users": {Role.ADMIN},
    "view_health": {Role.ADMIN, Role.AUDITOR},
    "view_dashboard": {Role.RESEARCHER, Role.MANAGER, Role.ADMIN, Role.AUDITOR},
}


@dataclass
class User:
    """User record."""
    user_id: str
    username: str
    email: str
    role: Role
    password_hash: str = ""
    created_at: float = 0.0
    last_login: float = 0.0
    is_active: bool = True
    sso_provider: str = ""
    sso_subject: str = ""

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "is_active": self.is_active,
            "sso_provider": self.sso_provider,
            "sso_subject": self.sso_subject,
            "password_hash": self.password_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "User":
        return cls(
            user_id=d["user_id"],
            username=d["username"],
            email=d["email"],
            role=Role(d["role"]),
            password_hash=d.get("password_hash", ""),
            created_at=d.get("created_at", 0.0),
            last_login=d.get("last_login", 0.0),
            is_active=d.get("is_active", True),
            sso_provider=d.get("sso_provider", ""),
            sso_subject=d.get("sso_subject", ""),
        )


@dataclass
class TokenPayload:
    """JWT-like token payload (simple HMAC-based for now)."""
    user_id: str
    username: str
    role: str
    issued_at: float
    expires_at: float


class AuthManager:
    """Manages user authentication, token creation/validation, and RBAC."""

    def __init__(self):
        self._users: dict[str, User] = {}
        self._load_users()
        self._ensure_default_admin()

    def _load_users(self):
        """Load users from persistent storage."""
        if USERS_FILE.exists():
            try:
                data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
                for u in data.get("users", []):
                    user = User.from_dict(u)
                    self._users[user.user_id] = user
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[AUTH] Warning: Failed to load users file: {e}")

    def _save_users(self):
        """Persist users to file."""
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"users": [u.to_dict() for u in self._users.values()]}
        USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _ensure_default_admin(self):
        """Create default admin if no users exist."""
        if not self._users:
            admin_password = os.getenv("POLARIS_ADMIN_PASSWORD", "admin")
            admin = User(
                user_id=str(uuid.uuid4()),
                username="admin",
                email="admin@polaris.local",
                role=Role.ADMIN,
                password_hash=self._hash_password(admin_password),
                created_at=time.time(),
                is_active=True,
            )
            self._users[admin.user_id] = admin
            self._save_users()

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash password with salt using SHA-256."""
        salt = os.getenv("POLARIS_AUTH_SALT", "polaris-salt")
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/password. Returns User or None."""
        password_hash = self._hash_password(password)
        for user in self._users.values():
            if user.username == username and user.password_hash == password_hash and user.is_active:
                user.last_login = time.time()
                self._save_users()
                return user
        return None

    def create_token(self, user: User) -> str:
        """Create a signed token for the user."""
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "iat": time.time(),
            "exp": time.time() + (AUTH_TOKEN_EXPIRY * 3600),
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
        signature = hmac.new(AUTH_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        return f"{payload_b64}.{signature}"

    def validate_token(self, token: str) -> Optional[TokenPayload]:
        """Validate token and return payload. Returns None if invalid."""
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            payload_b64, signature = parts
            expected_sig = hmac.new(AUTH_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_sig):
                return None
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            if payload["exp"] < time.time():
                return None
            return TokenPayload(
                user_id=payload["user_id"],
                username=payload["username"],
                role=payload["role"],
                issued_at=payload["iat"],
                expires_at=payload["exp"],
            )
        except Exception:
            return None

    def check_permission(self, role: Role, action: str) -> bool:
        """Check if a role has permission for an action."""
        allowed_roles = ENDPOINT_PERMISSIONS.get(action, set())
        effective_roles = ROLE_HIERARCHY.get(role, {role})
        return bool(effective_roles & allowed_roles)

    def create_user(self, username: str, email: str, password: str, role: Role) -> User:
        """Create a new user."""
        for u in self._users.values():
            if u.username == username:
                raise ValueError(f"Username '{username}' already exists")
            if u.email == email:
                raise ValueError(f"Email '{email}' already exists")
        user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            email=email,
            role=role,
            password_hash=self._hash_password(password),
            created_at=time.time(),
            is_active=True,
        )
        self._users[user.user_id] = user
        self._save_users()
        return user

    def list_users(self) -> list[dict]:
        """List all users (without password hashes)."""
        result = []
        for u in self._users.values():
            d = u.to_dict()
            del d["password_hash"]
            result.append(d)
        return result

    def update_user_role(self, user_id: str, new_role: Role) -> Optional[User]:
        """Update a user's role."""
        user = self._users.get(user_id)
        if user:
            user.role = new_role
            self._save_users()
        return user

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account."""
        user = self._users.get(user_id)
        if user:
            user.is_active = False
            self._save_users()
            return True
        return False

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self._users.get(user_id)
