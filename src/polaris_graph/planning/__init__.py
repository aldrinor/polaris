"""Field-agnostic research-planning package (I-meta-005 Phase 1, #985).

Houses the question-shaped research planner that — behind the
`PG_USE_RESEARCH_PLANNER` flag — replaces the clinical-only PICO + clause-split
+ `_ALLOWED_SECTIONS` decomposition path with a field-invariant frame,
faceted sub-queries, and an archetype-tagged section outline.

This is a SHADOW build: nothing here runs unless the on-flag is set AND the
caller explicitly threads the plan through. OFF behavior is byte-identical to
the legacy path. The single Writer call is an injected callable — the package
NEVER constructs an `OpenRouterClient` or a live HTTP client, so build + smoke
are spend-free.
"""

from __future__ import annotations

from src.polaris_graph.planning.research_planner import (
    DEFAULT_MAX_SUBQUERIES,
    MIN_SUBQUERIES,
    PlannerError,
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
    plan_research,
    serialize_plan_canonical,
)

__all__ = [
    "DEFAULT_MAX_SUBQUERIES",
    "MIN_SUBQUERIES",
    "PlannerError",
    "ResearchFrame",
    "ResearchPlan",
    "SectionOutlineItem",
    "plan_research",
    "serialize_plan_canonical",
]
