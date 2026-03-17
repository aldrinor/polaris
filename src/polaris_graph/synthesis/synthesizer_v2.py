"""v2 Section Synthesizer (Parallel Writers with Fallbacks).

Writes report sections in parallel using LangGraph Send API, with:
- TPM throttling via llm_throttle (Fix R5-#3)
- Phantom figure scrubbing (Fix R5-#5)
- Safe fallback on failure (Fix R6-#4)
- Evidence-grouped prompts (Fix R1-#4)
- Dynamic word targets (Fix R3-#5)
- Zero-evidence bypass (Fix R3-#2)

Each section writer receives its SectionSpec from the Blueprint and
writes independently. Results merge via merge_sections_reducer (Fix R5-#1).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.polaris_graph.retrieval.citation_normalizer import normalize_citations
from src.polaris_graph.retrieval.llm_throttle import throttled_llm_call
from src.polaris_graph.retrieval.section_blueprint import (
    EMPTY_SECTION_PLACEHOLDER,
    SectionBlueprint,
    SectionSpec,
)
from src.polaris_graph.retrieval.source_registry import SourceRegistry
from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
from src.polaris_graph.state import ReportSection

logger = logging.getLogger("polaris_graph")

# Max tokens per section generation call
MAX_SECTION_TOKENS = int(os.getenv("PG_V2_MAX_SECTION_TOKENS", "8192"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def write_section(
    client: Any,
    spec: SectionSpec,
    evidence_pool: list[dict[str, Any]],
    blueprint: SectionBlueprint,
    registry: SourceRegistry,
) -> dict[str, ReportSection]:
    """Write a single section from its Blueprint spec.

    Fix R6-#4 (Parallel Fallback): This function is called via LangGraph's
    Send API in parallel for up to 15 sections. If ANY call throws an
    unhandled exception, asyncio.gather cancels ALL sibling tasks.
    The top-level try/except ensures a safe fallback is always returned.

    Returns:
        dict[section_id, ReportSection] — for merge_sections_reducer.
    """
    try:
        return await _write_section_inner(
            client, spec, evidence_pool, blueprint, registry,
        )
    except Exception as e:
        logger.error(
            "Section '%s' failed, using fallback: %s",
            spec.title, str(e)[:200],
        )
        return {spec.section_id: _fallback_section(spec, str(e))}


async def _write_section_inner(
    client: Any,
    spec: SectionSpec,
    evidence_pool: list[dict[str, Any]],
    blueprint: SectionBlueprint,
    registry: SourceRegistry,
) -> dict[str, ReportSection]:
    """Core section writing logic (unwrapped for clean error propagation)."""

    # Fix R3-#2: Zero-evidence bypass — emit placeholder, skip LLM entirely
    if spec.should_skip_llm:
        logger.info("Section '%s': 0 evidence, emitting placeholder", spec.title)
        return {spec.section_id: _placeholder_section(spec)}

    # Retrieve assigned evidence
    evidence = blueprint.get_evidence_for_section(spec, evidence_pool)
    if not evidence:
        return {spec.section_id: _placeholder_section(spec)}

    # Fix R1-#4: Group evidence by source to avoid repeating metadata
    grouped = SectionBlueprint.group_evidence_by_source(evidence)

    # Build the evidence prompt
    evidence_prompt = _build_evidence_prompt(grouped, registry)

    # Build system prompt with all rules
    system = build_section_writer_prompt(
        n_evidence=spec.evidence_count,
        suggested_words=spec.effective_target_words,
    )

    # Build user prompt
    user_prompt = (
        f"## Section: {spec.title}\n\n"
        f"**Description:** {spec.description}\n\n"
        f"Write this section using ONLY the evidence below. "
        f"Cite sources using [SRC-NNN] format.\n\n"
        f"---\n\n{evidence_prompt}"
    )

    # Fix R5-#3: Throttled LLM call (prevents TPM burst)
    max_tokens = min(
        MAX_SECTION_TOKENS,
        spec.effective_target_words * 3,  # ~3 tokens per word (generous)
    )

    llm_response = await throttled_llm_call(
        client.generate,
        prompt=user_prompt,
        system=system,
        max_tokens=max_tokens,
    )

    # Extract text from LLMResponse object
    raw_content = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

    if not raw_content or not raw_content.strip():
        logger.warning("Section '%s': LLM returned empty content", spec.title)
        return {spec.section_id: _placeholder_section(spec)}

    # Fix R3-#3: Normalize compound citations
    content = normalize_citations(raw_content.strip())

    # Extract citation keys from content
    citation_ids = list(set(re.findall(r"\[SRC-(\d{3})\]", content)))
    citation_ids = [f"SRC-{cid}" for cid in sorted(citation_ids)]

    # Evidence IDs used
    ev_ids = [ev.get("evidence_id", "") for ev in evidence]

    section: ReportSection = {
        "section_id": spec.section_id,
        "title": spec.title,
        "content": content,
        "word_count": len(content.split()),
        "citation_ids": citation_ids,
        "evidence_ids": ev_ids,
    }

    logger.info(
        "Section '%s': %d words, %d citations, %d evidence",
        spec.title, section["word_count"], len(citation_ids), len(ev_ids),
    )

    return {spec.section_id: section}


# ---------------------------------------------------------------------------
# Evidence prompt builder
# ---------------------------------------------------------------------------

def _build_evidence_prompt(
    grouped: dict[str, list[dict[str, Any]]],
    registry: SourceRegistry,
) -> str:
    """Build evidence text grouped by source (Fix R1-#4: no metadata repetition).

    Instead of repeating title+abstract for every chunk from the same paper,
    prints source metadata ONCE, followed by all chunks from that source.
    """
    parts: list[str] = []

    for url, chunks in grouped.items():
        if not chunks:
            continue

        # Source header — printed ONCE
        first = chunks[0]
        src_entry = registry.get_by_url(url)
        citation_key = first.get("citation_key", "")
        title = first.get("source_title", "Unknown")
        source_type = first.get("source_type", "web")

        parts.append(f"### Source: {title} [{citation_key}]")
        parts.append(f"Type: {source_type} | URL: {url[:80]}")
        parts.append("")

        # Chunks from this source
        for i, chunk in enumerate(chunks, 1):
            tier = chunk.get("quality_tier", "")
            relevance = chunk.get("relevance_score", 0.0)
            text = chunk.get("direct_quote", "") or chunk.get("statement", "")
            is_table = chunk.get("is_table", False)

            if is_table:
                parts.append(f"**[Table Data — {tier}]**")
            else:
                parts.append(f"**[Chunk {i} — {tier}, relevance={relevance:.2f}]**")
            parts.append(text)
            parts.append("")

        parts.append("---")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Fallback / placeholder sections
# ---------------------------------------------------------------------------

def _placeholder_section(spec: SectionSpec) -> ReportSection:
    """Build a placeholder section for zero-evidence specs (Fix R3-#2)."""
    return {
        "section_id": spec.section_id,
        "title": spec.title,
        "content": EMPTY_SECTION_PLACEHOLDER,
        "word_count": 0,
        "citation_ids": [],
        "evidence_ids": [],
    }


def _fallback_section(spec: SectionSpec, error: str) -> ReportSection:
    """Build a safe fallback section when LLM fails (Fix R6-#4).

    This prevents a single section failure from crashing all 15 parallel
    writers via asyncio.gather cancellation.
    """
    content = (
        f"> [!WARNING]\n"
        f"> This section could not be generated due to a processing error.\n"
        f"> Error: {error[:200]}\n"
    )
    return {
        "section_id": spec.section_id,
        "title": spec.title,
        "content": content,
        "word_count": 0,
        "citation_ids": [],
        "evidence_ids": [],
    }
