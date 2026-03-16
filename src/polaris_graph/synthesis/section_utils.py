"""
Shared section utilities for the synthesis pipeline.

Provides helpers used across multiple MoST phases (Phase R, Phase E,
Safety Net) to maintain section data consistency.
"""

import re

from src.polaris_graph.schemas import SectionDraft


def sync_evidence_ids_from_content(section: SectionDraft) -> SectionDraft:
    """Rebuild evidence_ids from actual [CITE:ev_xxx] markers in content.

    M-01: Fixes 3x underreporting where evidence_ids field (40 unique, 16.5%)
    diverges from actual CITE markers in content (121 unique, 49.8%).

    Args:
        section: A SectionDraft whose evidence_ids may be stale.

    Returns:
        A new SectionDraft with evidence_ids matching actual content citations.
        If no CITE markers found, returns the section unchanged.
    """
    content = getattr(section, "content", "")
    actual_cites = list(set(re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", content)))
    if not actual_cites:
        return section
    return SectionDraft(
        section_id=getattr(section, "section_id", ""),
        title=getattr(section, "title", ""),
        content=content,
        claims_made=getattr(section, "claims_made", []),
        evidence_ids=actual_cites,
    )
