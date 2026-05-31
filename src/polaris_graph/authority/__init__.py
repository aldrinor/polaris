"""Field-agnostic computed source-authority model (Phase 0a, GH #983).

Drop-in behind PG_USE_AUTHORITY_MODEL. All source knowledge lives in versioned
DATA under config/authority/*; this package contains ZERO host/suffix/platform
literals (enforced by the S4-grep test). Explicit exports only (no wildcard).
"""
from __future__ import annotations

from src.polaris_graph.authority.authority_model import score_source_authority
from src.polaris_graph.authority.clinical_view import (
    ClinicalViewInput,
    render_clinical_tier,
)
from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    AuthorityResult,
    AuthoritySignals,
    SourceClass,
)

__all__ = [
    "score_source_authority",
    "render_clinical_tier",
    "ClinicalViewInput",
    "AuthorityResult",
    "AuthoritySignals",
    "AuthorityConfidence",
    "SourceClass",
]
