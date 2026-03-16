"""POLARIS Session Manager — Multi-user research session isolation and history."""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.getenv("POLARIS_SESSIONS_DIR", "state/sessions"))
HISTORY_FILE = Path(os.getenv("POLARIS_HISTORY_FILE", "state/research_history.json"))
MAX_CONCURRENT_RESEARCH = int(os.getenv("POLARIS_MAX_CONCURRENT_RESEARCH", "1"))


@dataclass
class ResearchSession:
    """A research session tied to a specific user."""
    session_id: str
    user_id: str
    query: str
    depth: str
    vector_id: str
    status: str  # queued | running | completed | failed | cancelled
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "query": self.query,
            "depth": self.depth,
            "vector_id": self.vector_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_path": self.result_path,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchSession":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class SessionManager:
    """Manages multi-user research sessions with isolation and queuing."""

    def __init__(self):
        self._sessions: dict[str, ResearchSession] = {}
        self._queue: list[str] = []  # session_ids waiting to run
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def _load_history(self):
        """Load research history from disk."""
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                for s in data.get("sessions", []):
                    session = ResearchSession.from_dict(s)
                    self._sessions[session.session_id] = session
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_history(self):
        """Persist research history."""
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Keep only last 500 sessions
        all_sessions = sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)[:500]
        data = {"sessions": [s.to_dict() for s in all_sessions]}
        HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def create_session(self, user_id: str, query: str, depth: str, vector_id: str) -> ResearchSession:
        """Create a new research session for a user."""
        session = ResearchSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            query=query,
            depth=depth,
            vector_id=vector_id,
            status="queued",
            created_at=time.time(),
        )
        self._sessions[session.session_id] = session
        self._queue.append(session.session_id)
        self._save_history()
        return session

    def get_running_count(self) -> int:
        """Count currently running research sessions."""
        return sum(1 for s in self._sessions.values() if s.status == "running")

    def can_start(self) -> bool:
        """Check if a new research session can start."""
        return self.get_running_count() < MAX_CONCURRENT_RESEARCH

    def mark_running(self, session_id: str):
        """Mark a session as running."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "running"
            s.started_at = time.time()
            if session_id in self._queue:
                self._queue.remove(session_id)
            self._save_history()

    def mark_completed(self, session_id: str, result_path: str):
        """Mark a session as completed."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "completed"
            s.completed_at = time.time()
            s.result_path = result_path
            self._save_history()

    def mark_failed(self, session_id: str, error: str):
        """Mark a session as failed."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "failed"
            s.completed_at = time.time()
            s.error = error[:500]
            self._save_history()

    def mark_cancelled(self, session_id: str):
        """Mark a session as cancelled."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "cancelled"
            s.completed_at = time.time()
            if session_id in self._queue:
                self._queue.remove(session_id)
            self._save_history()

    def get_user_history(self, user_id: str, limit: int = 50) -> list[dict]:
        """Get research history for a specific user."""
        user_sessions = [
            s.to_dict() for s in self._sessions.values()
            if s.user_id == user_id
        ]
        user_sessions.sort(key=lambda x: x["created_at"], reverse=True)
        return user_sessions[:limit]

    def get_session(self, session_id: str) -> Optional[ResearchSession]:
        """Get a specific session."""
        return self._sessions.get(session_id)

    def get_user_session(self, session_id: str, user_id: str) -> Optional[ResearchSession]:
        """Get a session only if it belongs to the specified user."""
        s = self._sessions.get(session_id)
        if s and s.user_id == user_id:
            return s
        return None

    def get_queue_position(self, session_id: str) -> int:
        """Get queue position (-1 if not queued)."""
        try:
            return self._queue.index(session_id)
        except ValueError:
            return -1

    def next_in_queue(self) -> Optional[str]:
        """Get next session_id from queue, or None."""
        return self._queue[0] if self._queue else None
