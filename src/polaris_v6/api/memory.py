"""F14 workspace memory HTTP endpoints (Phase 2B Task 2B.6).

I-rdy-012 (#508): the storage backend is now the durable SQLite-backed
`SqliteWorkspaceMemoryStore` — memory survives a process restart, stays
workspace-scoped, and surfaces `derived_from_run_ids` (cited recall). The
HTTP contract is unchanged from the in-memory demo store. The semantic
(Chroma) recall upgrade is tracked separately.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from polaris_v6.memory.schema import (
    MemoryEntry,
    MemoryKind,
    MemoryQuery,
    MemoryRecallResult,
)
from polaris_v6.memory.sqlite_store import SqliteWorkspaceMemoryStore

router = APIRouter(prefix="/workspaces", tags=["memory"])

_store = SqliteWorkspaceMemoryStore()


class RememberRequest(BaseModel):
    """Request body for storing a memory entry.

    Carries the entry `kind`, its `content`, and optional `derived_from_run_ids`
    that provenance-link the memory to the runs it was distilled from.
    """

    kind: MemoryKind
    content: str = Field(..., min_length=4, max_length=4000)
    derived_from_run_ids: list[str] = Field(default_factory=list)


@router.post(
    "/{workspace_id}/memory", response_model=MemoryEntry, status_code=201
)
def remember(workspace_id: str, payload: RememberRequest) -> MemoryEntry:
    """Persist a new memory entry into the given workspace and return it (201)."""
    return _store.remember(
        workspace_id=workspace_id,
        kind=payload.kind,
        content=payload.content,
        derived_from_run_ids=payload.derived_from_run_ids,
    )


class RecallRequest(BaseModel):
    """Request body for recalling workspace memory.

    `query_text` is matched against stored entries; `kinds` optionally restricts
    the search to specific memory kinds, and `top_k` caps the number of results.
    """

    query_text: str = Field(..., min_length=1, max_length=2000)
    kinds: list[MemoryKind] | None = None
    top_k: int = Field(default=5, ge=1, le=50)


@router.post(
    "/{workspace_id}/memory/recall",
    response_model=list[MemoryRecallResult],
)
def recall(workspace_id: str, payload: RecallRequest) -> list[MemoryRecallResult]:
    """Recall the top-k memory entries in a workspace matching the query."""
    return _store.recall(
        MemoryQuery(
            workspace_id=workspace_id,
            query_text=payload.query_text,
            kinds=payload.kinds,
            top_k=payload.top_k,
        )
    )


@router.delete("/{workspace_id}/memory/{entry_id}", status_code=204)
def forget(workspace_id: str, entry_id: str) -> None:
    """Delete a memory entry from a workspace (204 on success).

    Raises HTTPException 404 when no entry with `entry_id` exists in the
    given workspace.
    """
    if not _store.forget(workspace_id=workspace_id, entry_id=entry_id):
        raise HTTPException(
            status_code=404,
            detail=f"entry {entry_id!r} not found in workspace {workspace_id!r}",
        )
    return None


@router.get("/{workspace_id}/memory", response_model=list[MemoryEntry])
def list_workspace(workspace_id: str) -> list[MemoryEntry]:
    """Return all memory entries stored in the given workspace."""
    return _store.list_workspace(workspace_id)
