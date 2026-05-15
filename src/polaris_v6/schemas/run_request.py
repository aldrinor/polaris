"""Run-request payload schema (POST /runs body)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TemplateId = Literal[
    "clinical",
    "policy",
    "tech",
    "due_diligence",
    "ai_sovereignty",
    "canada_us",
    "workforce",
    "custom",
]


class RunRequest(BaseModel):
    template: TemplateId = Field(
        ...,
        description="One of the 8 locked templates per docs/blockers.md §10.",
    )
    question: str = Field(
        ...,
        min_length=4,
        max_length=2000,
        description="The research question. F1 scope discovery panel may refine this in Phase 1.",
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional uploaded-document ids. Phase 1 Task 1.3 wires these into "
            "graph_v4 evidence pool (currently ignored at graph_v4.py:149 — "
            "Errata to substrate_audit_2026-05-01.md)."
        ),
    )
