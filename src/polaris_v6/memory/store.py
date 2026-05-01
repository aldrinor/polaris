"""In-memory workspace memory store (Phase 2B substrate).

Phase 2B production swap: replace `_recall_by_keyword` with Chroma
semantic recall once the v6 cluster is live. The interface stays
stable so callers don't change.

Per CLAUDE.md security posture: workspace_id MUST be normalized
identically on write and read; mismatch is a P0 governance issue
(per `.codex/REVIEW_BRIEF_FORMAT_v2.md` example).
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

from polaris_v6.memory.schema import (
    MemoryEntry,
    MemoryKind,
    MemoryQuery,
    MemoryRecallResult,
)


def _normalize_workspace_id(raw: str) -> str:
    return raw.strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Counter[str]:
    return Counter(_TOKEN_RE.findall(text.lower()))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class WorkspaceMemoryStore:
    """In-memory implementation. Production swaps for Chroma in Phase 2B."""

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    def remember(
        self,
        *,
        workspace_id: str,
        kind: MemoryKind,
        content: str,
        derived_from_run_ids: list[str] | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            entry_id=uuid.uuid4().hex,
            workspace_id=_normalize_workspace_id(workspace_id),
            kind=kind,
            content=content,
            created_at=_now_iso(),
            derived_from_run_ids=derived_from_run_ids or [],
        )
        self._entries[entry.entry_id] = entry
        return entry

    def recall(self, query: MemoryQuery) -> list[MemoryRecallResult]:
        ws_norm = _normalize_workspace_id(query.workspace_id)
        candidates = [
            e
            for e in self._entries.values()
            if e.workspace_id == ws_norm
            and (query.kinds is None or e.kind in query.kinds)
        ]
        if not candidates:
            return []
        q_tokens = _tokens(query.query_text)
        scored = [
            MemoryRecallResult(entry=e, score=_cosine(q_tokens, _tokens(e.content)))
            for e in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        for r in scored[: query.top_k]:
            r.entry.use_count += 1
            r.entry.last_used_at = _now_iso()
        return scored[: query.top_k]

    def forget(self, *, workspace_id: str, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        if entry.workspace_id != _normalize_workspace_id(workspace_id):
            return False
        del self._entries[entry_id]
        return True

    def list_workspace(self, workspace_id: str) -> list[MemoryEntry]:
        ws_norm = _normalize_workspace_id(workspace_id)
        return [e for e in self._entries.values() if e.workspace_id == ws_norm]
