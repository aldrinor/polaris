"""Need-type router — I-meta-005 Phase 2 (#986).

`route_needs_to_adapters(frame)` reads the planner frame's field-agnostic
`evidence_needs` + normalized `jurisdictions` and returns the deduped union of
discovery adapters for those needs. NO `if domain ==` — the frame carries no
domain; routing is keyed only on the declared need + extracted jurisdiction.

Fallback (brief §2.3): an EMPTY `evidence_needs` (older legacy plan) routes to
the safe generic set {primary_literature, open_web} — NEVER to a domain. A
MALFORMED evidence_need / jurisdiction SHAPE is a fail-loud `MalformedPlanError`
(validated UP-FRONT, brief §2.4 P2-note-1), NOT a fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from src.polaris_graph.discovery.source_adapter_registry import (
    DiscoveryAdapter,
    SourceAdapterRegistry,
)
from src.polaris_graph.planning.research_planner import (
    MalformedPlanError,
    ResearchFrame,
    validate_evidence_needs,
    validate_jurisdiction_shapes,
)

logger = logging.getLogger("polaris_graph.need_type_router")

# Safe generic fallback for an EMPTY evidence_needs (brief §2.3). NEVER a domain.
_EMPTY_NEEDS_FALLBACK: tuple[str, ...] = ("primary_literature", "open_web")


def validate_frame_needs(frame: ResearchFrame) -> tuple[list[str], list[str]]:
    """Validate the frame's `evidence_needs` + `jurisdictions` UP-FRONT and
    return the normalized (needs, jurisdictions). Raises `MalformedPlanError`
    on a malformed need value OR a malformed jurisdiction SHAPE — the live seam
    calls this BEFORE any discovery (incl. core Serper/S2) so a malformed frame
    fails loud without spending (brief §2.4 P2-note-1).

    A valid-shape-but-unknown jurisdiction code passes here (membership is the
    scope loader's non-fatal concern). An EMPTY `evidence_needs` passes (the
    router applies the safe generic fallback) — only a MALFORMED value raises.
    """
    needs = validate_evidence_needs(list(getattr(frame, "evidence_needs", []) or []))
    jurisdictions = validate_jurisdiction_shapes(
        list(getattr(frame, "jurisdictions", []) or [])
    )
    return needs, jurisdictions


def route_needs_to_adapters(
    frame: ResearchFrame,
    *,
    registry: SourceAdapterRegistry | None = None,
) -> list[DiscoveryAdapter]:
    """Return the deduped union of discovery adapters for the frame's declared
    needs, scoped to its jurisdictions. NO domain consulted.

    - Validates needs + jurisdiction SHAPE UP-FRONT (raises MalformedPlanError).
    - EMPTY needs -> {primary_literature, open_web} safe generic fallback.
    - Dedupes adapters by (name) so a need overlap (e.g. news_press + open_web
      both yielding `serper`) selects each adapter once.
    """
    if registry is None:
        registry = SourceAdapterRegistry()

    needs, jurisdictions = validate_frame_needs(frame)
    if not needs:
        logger.info(
            "[need_type_router] empty evidence_needs -> safe generic fallback "
            "%s (NOT a domain)", list(_EMPTY_NEEDS_FALLBACK),
        )
        needs = list(_EMPTY_NEEDS_FALLBACK)

    selected: list[DiscoveryAdapter] = []
    seen_names: set[str] = set()
    for need in needs:
        for adapter in registry.adapters_for_need(need, jurisdictions=jurisdictions):
            if adapter.name in seen_names:
                continue
            seen_names.add(adapter.name)
            selected.append(adapter)
    return selected
