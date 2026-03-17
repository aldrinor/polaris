"""v2 Report Assembler (Grounded Bibliography + Outline Pruning).

Assembles the final report from verified sections with:
- Grounded bibliography: ONLY sources actually cited in text (Fix R6-#2)
- Outline pruning: Drop placeholder/failed sections (Fix R6-#5)
- Citation normalization: Split compound citations (Fix R3-#3)
- Sequential numbering: [SRC-NNN] → [1], [2], [3]

CRITICAL (Fix R6-#2 — "Fake Reference" Academic Fraud):
The bibliography must be built from a regex scan of the ACTUAL markdown,
not from the Blueprint's assigned evidence. If the Blueprint assigned 150
sources but LLMs only cited 60, we must NOT include 90 ghost references.
A reader cross-referencing the bibliography against inline citations would
immediately detect the fraud.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Any

from src.polaris_graph.retrieval.citation_normalizer import (
    citation_stats,
    normalize_citations,
    resolve_to_numbers,
)
from src.polaris_graph.retrieval.section_blueprint import (
    EMPTY_SECTION_PLACEHOLDER,
    SectionSpec,
)
from src.polaris_graph.retrieval.source_registry import SourceRegistry
from src.polaris_graph.state import ReportSection

logger = logging.getLogger("polaris_graph")

# Regex for detecting placeholder/failed section content
_PLACEHOLDER_MARKERS = (
    "No reliable evidence was retrieved",  # EMPTY_SECTION_PLACEHOLDER
    "could not be generated due to a processing error",  # _fallback_section
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_report(
    sections: dict[str, ReportSection],
    section_order: list[str],
    registry: SourceRegistry,
    title: str,
    query: str,
) -> tuple[str, dict[str, Any]]:
    """Assemble the final report from verified sections.

    Args:
        sections: Dict of section_id -> ReportSection (from completed_sections).
        section_order: Ordered list of section_ids (from outline).
        registry: Global source registry (for bibliography).
        title: Report title.
        query: Original research query.

    Returns:
        (final_markdown, assembly_stats)
    """
    # Fix R6-#5: Prune placeholder and failed sections
    active_sections, pruned_count = _prune_sections(sections, section_order)

    if not active_sections:
        logger.error("Assembly: ALL sections pruned — no content to assemble")
        return _empty_report(title, query), {"error": "all_sections_pruned"}

    # Build body markdown
    body_parts: list[str] = [f"# {title}\n"]

    for section_id in section_order:
        if section_id not in active_sections:
            continue
        sec = active_sections[section_id]
        # Normalize citations in each section
        content = normalize_citations(sec["content"])
        body_parts.append(f"\n## {sec['title']}\n\n{content}\n")

    body = "\n".join(body_parts)

    # Fix R6-#2: Grounded bibliography (2-pass process)
    #
    # Pass 1: Extract [SRC-NNN] tags the LLM actually printed in the text.
    #          This is the ONLY source of truth for the bibliography.
    #
    # Pass 2: Build a unique, ordered list of these tags, map to [1], [2],
    #          and generate the bibliography strictly from extracted tags.
    cited_src_ids = _extract_cited_sources(body)

    if not cited_src_ids:
        logger.warning("Assembly: 0 citations found in text — bibliography empty")

    # FIX-V2-STATS: Capture citation stats BEFORE resolve_to_numbers()
    # converts [SRC-NNN] → [N]. citation_stats() searches for [SRC-NNN],
    # so it must run on the pre-resolution text.
    pre_resolution_cite_stats = citation_stats(body)

    # Build citation map: SRC-NNN -> sequential number
    citation_map: dict[str, int] = {}
    bibliography_lines: list[str] = []

    for i, src_id in enumerate(cited_src_ids, 1):
        citation_map[src_id] = i
        entry = registry.get(src_id)
        if entry:
            bib_line = _format_bibliography_entry(i, entry)
            bibliography_lines.append(bib_line)
        else:
            logger.warning("Assembly: %s cited in text but not in registry", src_id)
            bibliography_lines.append(f"[{i}] {src_id} — source not found in registry")

    # Replace [SRC-NNN] with [N] in the body
    body = resolve_to_numbers(body, citation_map)

    # Append bibliography
    if bibliography_lines:
        body += "\n\n## References\n\n"
        body += "\n".join(bibliography_lines)
        body += "\n"

    # Compute stats (using pre-resolution citation counts)
    stats = _compute_stats(
        body, sections, active_sections, cited_src_ids,
        pruned_count, pre_resolution_cite_stats,
    )
    logger.info(
        "Assembly complete: %d sections, %d citations, %d unique sources, %d words, %d pruned",
        stats["active_sections"], stats["total_citations"],
        stats["unique_sources"], stats["total_words"], stats["pruned_sections"],
    )

    return body, stats


# ---------------------------------------------------------------------------
# Fix R6-#5: Outline pruning
# ---------------------------------------------------------------------------

def _prune_sections(
    sections: dict[str, ReportSection],
    section_order: list[str],
) -> tuple[dict[str, ReportSection], int]:
    """Remove placeholder and failed sections from the output.

    Fix R6-#5: If search performs poorly and 5/15 sections get the
    placeholder, the final report would be littered with ugly empty
    sections. Gemini just skips them — so do we.

    Returns:
        (active_sections, pruned_count)
    """
    active: dict[str, ReportSection] = {}
    pruned = 0

    for section_id in section_order:
        if section_id not in sections:
            pruned += 1
            continue

        sec = sections[section_id]
        content = sec.get("content", "")

        # Check for placeholder markers
        is_placeholder = any(marker in content for marker in _PLACEHOLDER_MARKERS)

        # Also skip sections with zero meaningful content
        is_empty = len(content.strip()) < 50

        if is_placeholder or is_empty:
            pruned += 1
            logger.info(
                "Assembly: pruned section '%s' (%s)",
                sec.get("title", section_id),
                "placeholder" if is_placeholder else "empty",
            )
            continue

        active[section_id] = sec

    if pruned > 0:
        logger.info(
            "Assembly: pruned %d/%d sections (placeholders/empty)",
            pruned, pruned + len(active),
        )

    return active, pruned


# ---------------------------------------------------------------------------
# Fix R6-#2: Grounded bibliography extraction
# ---------------------------------------------------------------------------

def _extract_cited_sources(text: str) -> list[str]:
    """Extract unique [SRC-NNN] tags from text in order of first appearance.

    Fix R6-#2: This is the ONLY input to bibliography generation.
    Sources assigned by the Blueprint but not actually cited by the LLM
    are intentionally excluded.

    Returns:
        Ordered list of unique SRC-NNN IDs (e.g., ["SRC-001", "SRC-003", "SRC-007"]).
    """
    # Find all SRC-NNN references in order of appearance
    all_refs = re.findall(r"\[SRC-(\d{3})\]", text)

    # Deduplicate while preserving first-appearance order
    seen: set[str] = set()
    unique: list[str] = []
    for ref_num in all_refs:
        src_id = f"SRC-{ref_num}"
        if src_id not in seen:
            seen.add(src_id)
            unique.append(src_id)

    return unique


def _format_bibliography_entry(number: int, entry: Any) -> str:
    """Format a single bibliography entry.

    Args:
        number: Citation number (1-indexed).
        entry: SourceEntry from SourceRegistry.
    """
    parts = [f"[{number}]"]

    # Authors
    if entry.authors:
        if len(entry.authors) <= 3:
            parts.append(", ".join(entry.authors))
        else:
            parts.append(f"{entry.authors[0]} et al.")

    # Year
    if entry.year:
        parts.append(f"({entry.year}).")

    # Title
    parts.append(f'"{entry.title}."')

    # Venue
    if entry.venue:
        parts.append(f"*{entry.venue}*.")

    # DOI or URL
    if entry.doi:
        parts.append(f"DOI: {entry.doi}")
    elif entry.url:
        parts.append(entry.url)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Stats and empty report
# ---------------------------------------------------------------------------

def _compute_stats(
    final_text: str,
    all_sections: dict[str, ReportSection],
    active_sections: dict[str, ReportSection],
    cited_src_ids: list[str],
    pruned_count: int,
    pre_resolution_cite_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Compute assembly statistics for quality tracking.

    FIX-V2-STATS: Uses pre-resolution citation stats (counted before
    [SRC-NNN] → [N] conversion) for accurate citation metrics.
    """
    words = len(final_text.split())

    # Use pre-resolution stats if available (accurate), else fall back
    cite_stats = pre_resolution_cite_stats or citation_stats(final_text)

    return {
        "total_sections": len(all_sections),
        "active_sections": len(active_sections),
        "pruned_sections": pruned_count,
        "total_words": words,
        "total_citations": cite_stats["total_citations"],
        "unique_sources": len(cited_src_ids),
        "uncited_paragraphs": cite_stats["uncited_paragraphs"],
        "total_paragraphs": cite_stats["total_paragraphs"],
        "compound_violations": cite_stats["compound_violations"],
        "citations_per_100_words": round(
            cite_stats["total_citations"] / max(words, 1) * 100, 2
        ),
    }


def _empty_report(title: str, query: str) -> str:
    """Generate a minimal report when all sections are pruned."""
    return (
        f"# {title}\n\n"
        f"> [!WARNING]\n"
        f"> Insufficient evidence was retrieved to generate this report.\n"
        f"> Query: {query}\n"
        f">\n"
        f"> Please try refining the research query or expanding search parameters.\n"
    )
