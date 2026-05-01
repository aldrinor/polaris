"""Workspace memory schema — what gets persisted across runs in a workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MemoryKind = Literal[
    "user_preference",
    "domain_assumption",
    "prior_run_summary",
    "rejected_source",
    "preferred_source",
]


class MemoryEntry(BaseModel):
    """A single workspace-scoped memory entry."""

    entry_id: str
    workspace_id: str
    kind: MemoryKind
    content: str = Field(..., min_length=4, max_length=4000)
    embedding_vector: list[float] | None = Field(
        default=None,
        description="Optional vector for semantic recall. Phase 2B fills via Chroma.",
    )
    created_at: str
    last_used_at: str | None = None
    use_count: int = Field(default=0, ge=0)
    derived_from_run_ids: list[str] = Field(default_factory=list)


class MemoryQuery(BaseModel):
    """A semantic-recall query."""

    workspace_id: str
    query_text: str = Field(..., min_length=1, max_length=2000)
    kinds: list[MemoryKind] | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryRecallResult(BaseModel):
    """Result of a recall query."""

    entry: MemoryEntry
    score: float = Field(..., ge=0.0, le=1.0)
