"""
Cloud storage provider integrations (Google Drive, OneDrive, Dropbox).

OAuth2-based browsing and file import for NotebookLM-style cloud sources.
Providers authenticate via popup OAuth flow, store tokens in a local JSON file,
and expose list_folder() / download_file() for the live_server endpoints.

Zero new dependencies beyond httpx (already in requirements).
"""

import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("cloud_providers")

# ---------------------------------------------------------------------------
# Token Store — persists OAuth2 tokens to disk (LAW VI)
# ---------------------------------------------------------------------------
_TOKEN_PATH = Path(os.getenv(
    "POLARIS_CLOUD_TOKEN_PATH",
    "state/cloud_tokens.json",
))


class CloudTokenStore:
    """Read/write OAuth2 tokens to a local JSON file."""

    def __init__(self, path: Path = _TOKEN_PATH) -> None:
        self._path = path

    def _read_all(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_all(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

    def get(self, provider: str) -> Optional[dict[str, Any]]:
        return self._read_all().get(provider)

    def save(self, provider: str, token_data: dict[str, Any]) -> None:
        all_tokens = self._read_all()
        all_tokens[provider] = token_data
        self._write_all(all_tokens)

    def delete(self, provider: str) -> None:
        all_tokens = self._read_all()
        all_tokens.pop(provider, None)
        self._write_all(all_tokens)

    def is_connected(self, provider: str) -> bool:
        token = self.get(provider)
        return token is not None and bool(token.get("access_token"))


# Shared instance
_token_store = CloudTokenStore()

# CSRF state tokens (in-memory, valid for 10 minutes)
_pending_states: dict[str, float] = {}


def _generate_state() -> str:
    """Generate a CSRF state token and store it with expiry."""
    state = secrets.token_urlsafe(32)
    _pending_states[state] = time.time() + 600  # 10 min
    # Prune expired
    now = time.time()
    expired = [k for k, v in _pending_states.items() if v < now]
    for k in expired:
        _pending_states.pop(k, None)
    return state


def _validate_state(state: str) -> bool:
    """Validate and consume a CSRF state token."""
    expiry = _pending_states.pop(state, None)
    if expiry is None:
        return False
    return time.time() < expiry


# ---------------------------------------------------------------------------
# Base CloudProvider
# ---------------------------------------------------------------------------
class CloudProvider:
    """Abstract base for OAuth2 cloud storage providers."""

    PROVIDER_ID: str = ""
    AUTH_URL: str = ""
    TOKEN_URL: str = ""
    SCOPES: str = ""
    CLIENT_ID_ENV: str = ""
    CLIENT_SECRET_ENV: str = ""

    def __init__(self, token_store: CloudTokenStore) -> None:
        self._store = token_store

    @property
    def client_id(self) -> str:
        return os.getenv(self.CLIENT_ID_ENV, "")

    @property
    def client_secret(self) -> str:
        return os.getenv(self.CLIENT_SECRET_ENV, "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def is_connected(self) -> bool:
        return self._store.is_connected(self.PROVIDER_ID)

    def get_authorize_url(self, redirect_uri: str) -> str:
        """Build the OAuth2 authorization URL."""
        state = _generate_state()
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        query = "&".join(f"{k}={httpx.URL('', params={k: v}).params[k]}"
                         for k, v in params.items() if v)
        return f"{self.AUTH_URL}?{query}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        token_data = {
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": time.time() + data.get("expires_in", 3600),
            "scope": data.get("scope", self.SCOPES),
        }
        self._store.save(self.PROVIDER_ID, token_data)
        return token_data

    def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if expired."""
        token_data = self._store.get(self.PROVIDER_ID)
        if not token_data:
            raise PermissionError(f"{self.PROVIDER_ID} not connected")
        if time.time() > token_data.get("expires_at", 0) - 60:
            refresh = token_data.get("refresh_token", "")
            if not refresh:
                raise PermissionError(f"{self.PROVIDER_ID} token expired, no refresh token")
            token_data = self._refresh_token(refresh)
        return token_data["access_token"]

    def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Use refresh_token to get a new access_token."""
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        token_data = {
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": time.time() + data.get("expires_in", 3600),
            "scope": data.get("scope", self.SCOPES),
        }
        self._store.save(self.PROVIDER_ID, token_data)
        return token_data

    def _api_get(self, url: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Authenticated JSON GET request."""
        token = self._get_access_token()
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()

    def _api_get_bytes(self, url: str, headers: Optional[dict] = None) -> bytes:
        """Authenticated binary GET request (file downloads)."""
        token = self._get_access_token()
        req_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            req_headers.update(headers)
        resp = httpx.get(
            url,
            headers=req_headers,
            timeout=120.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content

    def _api_post(self, url: str, json_data: Optional[dict] = None,
                  headers: Optional[dict] = None) -> httpx.Response:
        """Authenticated POST request."""
        token = self._get_access_token()
        req_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            req_headers.update(headers)
        resp = httpx.post(
            url,
            json=json_data,
            headers=req_headers,
            timeout=120.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp

    def list_folder(self, folder_id: Optional[str] = None) -> dict[str, Any]:
        """List folder contents. Returns {items: [...], breadcrumb: [...]}."""
        raise NotImplementedError

    def download_file(self, file_id: str, mime_type: str = "") -> tuple[str, bytes]:
        """Download a file. Returns (filename, bytes)."""
        raise NotImplementedError

    def disconnect(self) -> None:
        """Remove stored tokens for this provider."""
        self._store.delete(self.PROVIDER_ID)


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------
class GoogleDriveProvider(CloudProvider):
    """Google Drive via Drive API v3."""

    PROVIDER_ID = "google_drive"
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPES = "https://www.googleapis.com/auth/drive.readonly"
    CLIENT_ID_ENV = "GOOGLE_DRIVE_CLIENT_ID"
    CLIENT_SECRET_ENV = "GOOGLE_DRIVE_CLIENT_SECRET"

    _DRIVE_API = "https://www.googleapis.com/drive/v3"

    # Google Workspace MIME types → export targets
    _EXPORT_MIMES: dict[str, str] = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "text/plain",
    }

    def list_folder(self, folder_id: Optional[str] = None) -> dict[str, Any]:
        fid = folder_id or "root"
        query = f"'{fid}' in parents and trashed = false"
        fields = "files(id,name,mimeType,size,modifiedTime,parents)"
        data = self._api_get(
            f"{self._DRIVE_API}/files",
            params={"q": query, "fields": fields, "pageSize": "100",
                    "orderBy": "folder,name"},
        )
        items = []
        for f in data.get("files", []):
            is_folder = f.get("mimeType") == "application/vnd.google-apps.folder"
            items.append({
                "id": f["id"],
                "name": f["name"],
                "is_folder": is_folder,
                "size": int(f.get("size", 0)) if not is_folder else 0,
                "mime_type": f.get("mimeType", ""),
                "modified": f.get("modifiedTime", ""),
            })
        breadcrumb = self._build_breadcrumb(fid)
        return {"items": items, "breadcrumb": breadcrumb}

    def _build_breadcrumb(self, folder_id: str) -> list[dict[str, str]]:
        """Walk parent chain to build folder path."""
        crumbs: list[dict[str, str]] = []
        current = folder_id
        seen: set[str] = set()
        while current and current != "root" and current not in seen:
            seen.add(current)
            try:
                meta = self._api_get(
                    f"{self._DRIVE_API}/files/{current}",
                    params={"fields": "id,name,parents"},
                )
                crumbs.insert(0, {"id": meta["id"], "name": meta.get("name", "")})
                parents = meta.get("parents", [])
                current = parents[0] if parents else None
            except Exception:
                break
        crumbs.insert(0, {"id": "root", "name": "My Drive"})
        return crumbs

    def download_file(self, file_id: str, mime_type: str = "") -> tuple[str, bytes]:
        # Get file metadata
        meta = self._api_get(
            f"{self._DRIVE_API}/files/{file_id}",
            params={"fields": "id,name,mimeType,size"},
        )
        name = meta.get("name", file_id)
        file_mime = meta.get("mimeType", mime_type)

        # Google Workspace docs: export
        export_mime = self._EXPORT_MIMES.get(file_mime)
        if export_mime:
            content = self._api_get_bytes(
                f"{self._DRIVE_API}/files/{file_id}/export",
                headers={"Accept": export_mime},
            )
            # Add appropriate extension
            if export_mime == "text/plain" and not name.endswith(".txt"):
                name += ".txt"
            elif export_mime == "text/csv" and not name.endswith(".csv"):
                name += ".csv"
            return name, content

        # Regular files: direct download
        content = self._api_get_bytes(
            f"{self._DRIVE_API}/files/{file_id}?alt=media",
        )
        return name, content


# ---------------------------------------------------------------------------
# OneDrive (Microsoft Graph)
# ---------------------------------------------------------------------------
class OneDriveProvider(CloudProvider):
    """OneDrive via Microsoft Graph API."""

    PROVIDER_ID = "onedrive"
    AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    SCOPES = "Files.Read offline_access"
    CLIENT_ID_ENV = "ONEDRIVE_CLIENT_ID"
    CLIENT_SECRET_ENV = "ONEDRIVE_CLIENT_SECRET"

    _GRAPH_API = "https://graph.microsoft.com/v1.0"

    def list_folder(self, folder_id: Optional[str] = None) -> dict[str, Any]:
        if folder_id and folder_id != "root":
            url = f"{self._GRAPH_API}/me/drive/items/{folder_id}/children"
        else:
            url = f"{self._GRAPH_API}/me/drive/root/children"
            folder_id = "root"

        data = self._api_get(url, params={
            "$select": "id,name,size,lastModifiedDateTime,folder,file",
            "$top": "100",
            "$orderby": "name",
        })

        items = []
        for item in data.get("value", []):
            is_folder = "folder" in item
            items.append({
                "id": item["id"],
                "name": item["name"],
                "is_folder": is_folder,
                "size": item.get("size", 0) if not is_folder else 0,
                "mime_type": item.get("file", {}).get("mimeType", ""),
                "modified": item.get("lastModifiedDateTime", ""),
            })
        breadcrumb = self._build_breadcrumb(folder_id)
        return {"items": items, "breadcrumb": breadcrumb}

    def _build_breadcrumb(self, folder_id: str) -> list[dict[str, str]]:
        crumbs = [{"id": "root", "name": "OneDrive"}]
        if folder_id and folder_id != "root":
            try:
                meta = self._api_get(
                    f"{self._GRAPH_API}/me/drive/items/{folder_id}",
                    params={"$select": "id,name,parentReference"},
                )
                # Build path from parentReference
                parent_path = meta.get("parentReference", {}).get("path", "")
                if parent_path:
                    # Path looks like /drive/root:/folder1/folder2
                    parts = parent_path.split("root:")[-1].strip("/").split("/")
                    for part in parts:
                        if part:
                            crumbs.append({"id": "", "name": part})
                crumbs.append({"id": meta["id"], "name": meta.get("name", "")})
            except Exception:
                pass
        return crumbs

    def download_file(self, file_id: str, mime_type: str = "") -> tuple[str, bytes]:
        # Get metadata
        meta = self._api_get(
            f"{self._GRAPH_API}/me/drive/items/{file_id}",
            params={"$select": "id,name,size,@microsoft.graph.downloadUrl"},
        )
        name = meta.get("name", file_id)
        download_url = meta.get("@microsoft.graph.downloadUrl", "")

        if download_url:
            # Direct download (no auth needed for this pre-signed URL)
            resp = httpx.get(download_url, timeout=120.0, follow_redirects=True)
            resp.raise_for_status()
            return name, resp.content

        # Fallback: use content endpoint
        content = self._api_get_bytes(
            f"{self._GRAPH_API}/me/drive/items/{file_id}/content",
        )
        return name, content


# ---------------------------------------------------------------------------
# Dropbox
# ---------------------------------------------------------------------------
class DropboxProvider(CloudProvider):
    """Dropbox via Dropbox API v2."""

    PROVIDER_ID = "dropbox"
    AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
    TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
    SCOPES = ""  # Dropbox uses app permissions, not scopes
    CLIENT_ID_ENV = "DROPBOX_CLIENT_ID"
    CLIENT_SECRET_ENV = "DROPBOX_CLIENT_SECRET"

    def get_authorize_url(self, redirect_uri: str) -> str:
        """Dropbox uses token_access_type instead of access_type."""
        state = _generate_state()
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "token_access_type": "offline",
        }
        query = "&".join(f"{k}={httpx.URL('', params={k: v}).params[k]}"
                         for k, v in params.items() if v)
        return f"{self.AUTH_URL}?{query}"

    def list_folder(self, folder_id: Optional[str] = None) -> dict[str, Any]:
        path = folder_id if folder_id else ""
        resp = self._api_post(
            "https://api.dropboxapi.com/2/files/list_folder",
            json_data={"path": path, "limit": 100},
        )
        data = resp.json()

        items = []
        for entry in data.get("entries", []):
            is_folder = entry.get(".tag") == "folder"
            items.append({
                "id": entry.get("path_lower", entry.get("id", "")),
                "name": entry.get("name", ""),
                "is_folder": is_folder,
                "size": entry.get("size", 0) if not is_folder else 0,
                "mime_type": "",
                "modified": entry.get("server_modified", ""),
            })

        # Build breadcrumb from path
        breadcrumb = [{"id": "", "name": "Dropbox"}]
        if path:
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current += f"/{part}"
                breadcrumb.append({"id": current, "name": part})

        return {"items": items, "breadcrumb": breadcrumb}

    def download_file(self, file_id: str, mime_type: str = "") -> tuple[str, bytes]:
        token = self._get_access_token()
        api_arg = json.dumps({"path": file_id})
        resp = httpx.post(
            "https://content.dropboxapi.com/2/files/download",
            headers={
                "Authorization": f"Bearer {token}",
                "Dropbox-API-Arg": api_arg,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        # Filename from Dropbox-API-Result header or path
        name = file_id.rsplit("/", 1)[-1] if "/" in file_id else file_id
        try:
            result_header = resp.headers.get("dropbox-api-result", "{}")
            result = json.loads(result_header)
            name = result.get("name", name)
        except (json.JSONDecodeError, AttributeError):
            pass
        return name, resp.content


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------
cloud_provider_registry: dict[str, CloudProvider] = {
    "google_drive": GoogleDriveProvider(_token_store),
    "onedrive": OneDriveProvider(_token_store),
    "dropbox": DropboxProvider(_token_store),
}


def validate_state(state: str) -> bool:
    """Validate a CSRF state token (exposed for use by live_server)."""
    return _validate_state(state)


def get_cloud_status() -> dict[str, dict[str, bool]]:
    """Return configured/connected status for all providers."""
    status = {}
    for provider_id, provider in cloud_provider_registry.items():
        status[provider_id] = {
            "configured": provider.is_configured,
            "connected": provider.is_connected,
        }
    return status
