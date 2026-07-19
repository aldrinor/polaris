"""Template registry — loads + validates per-template JSON content."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "v6_templates"

SourceTier = Literal["T1", "T2", "T3"]


class FrameDefinition(BaseModel):
    """One report frame, identified by ``frame_id`` and its display ``frame_name``."""

    frame_id: str
    frame_name: str


class TemplateContent(BaseModel):
    """One template's validated content: identity, source tiers, frame manifest, and examples."""

    template_id: str
    template_name: str
    summary: str = Field(..., min_length=20)
    primary_domains: list[str] = Field(..., min_length=1)
    source_tiers: dict[SourceTier, list[str]]
    min_sources_per_tier: dict[SourceTier, int]
    frame_manifest: list[FrameDefinition] = Field(..., min_length=2)
    refusal_patterns: list[str] = Field(default_factory=list)
    sample_questions: list[str] = Field(..., min_length=2)
    out_of_scope_examples: list[str] = Field(default_factory=list)


def load_template(template_id: str) -> TemplateContent:
    """Load and validate one template's JSON content by id.

    Args:
        template_id: Template id; resolves to ``<TEMPLATES_DIR>/<id>.json``.

    Returns:
        The parsed, schema-validated ``TemplateContent``.

    Raises:
        FileNotFoundError: If no JSON file exists for ``template_id``.
        pydantic.ValidationError: If the file's contents fail schema validation.
    """
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Template content not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TemplateContent.model_validate(payload)


def list_template_ids() -> list[str]:
    """Return the sorted ids of all template JSON files on disk.

    Returns:
        Sorted template ids (JSON file stems); empty if the templates directory
        does not exist.
    """
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))
