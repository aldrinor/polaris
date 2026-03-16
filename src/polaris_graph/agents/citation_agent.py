"""ARCH-3: Dedicated citation agent for accurate inline citation insertion.

Inspired by Claude Research's architecture — separate citation from prose writing.
Current approach: section_writer writes prose WITH citations in one pass, leading
to citation mismatches (e.g., EPA data attributed to a blog) and citation poverty
(792 words with only 2 citations in Section 8 of PG_TEST_035).

This agent reviews draft prose and inserts citations at correct positions by:
1. Identifying every factual claim in the text
2. Finding the best-matching evidence piece(s) for each claim
3. Inserting [CITE:ev_xxx] citations at the correct position
4. Flagging claims with no matching evidence as [UNSUPPORTED]

OUTPUT FORMAT: [CITE:ev_xxx] — compatible with downstream resolve_citations().
The LLM sees simple [N] labels; we map back to [CITE:ev_xxx] after generation.
"""

import logging
import os
import re
from typing import Any

from src.polaris_graph.llm.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

PG_CITATION_AGENT_ENABLED = os.getenv("PG_CITATION_AGENT_ENABLED", "0") == "1"
PG_CITATION_AGENT_MAX_TOKENS = int(os.getenv("PG_CITATION_AGENT_MAX_TOKENS", "8192"))

CITATION_SYSTEM = """You are a precision citation specialist for academic research reports.
Your ONLY job is to insert inline citations [N] into text.

Rules:
1. Every specific number, date, percentage, finding, or factual claim MUST have a citation.
2. Only cite evidence that DIRECTLY supports the specific claim (not just the topic).
3. Use the format [N] where N is the evidence number from the provided mapping.
4. Do NOT add citations for general knowledge, definitions, or transitional phrases.
5. If a claim has no matching evidence, leave it without a citation (do NOT add [UNSUPPORTED]).
6. Do NOT change any words in the text — only add [N] markers.
7. Place citations immediately after the claim they support, before any punctuation.
8. If multiple evidence pieces support the same claim, cite all: [1][3][7]."""


def _count_citations(text: str) -> int:
    """Count citations in both [CITE:ev_xxx] and [N] formats."""
    cite_format = len(re.findall(r'\[CITE:[^\]]+\]', text))
    num_format = len(re.findall(r'\[\d+\]', text))
    return cite_format + num_format


async def insert_citations(
    client: OpenRouterClient,
    section_text: str,
    evidence_pool: list[dict],
) -> str:
    """Review section text and insert accurate inline citations.

    Uses integer labels [N] for LLM, then maps back to [CITE:ev_xxx] format
    for compatibility with downstream resolve_citations().

    Args:
        client: OpenRouter LLM client.
        section_text: Draft prose text (may have [CITE:ev_xxx] citations).
        evidence_pool: List of evidence dicts relevant to this section.

    Returns:
        Text with inline [CITE:ev_xxx] citations inserted at correct positions.
    """
    if not section_text or not evidence_pool:
        return section_text

    # Strip existing citations from text so agent can re-cite accurately
    clean_text = re.sub(r'\[\d+\]', '', section_text)
    clean_text = re.sub(r'\[CITE:[^\]]*\]', '', clean_text)
    clean_text = re.sub(r'\s{2,}', ' ', clean_text).strip()

    # Build integer_label -> evidence_id mapping
    label_to_eid: dict[int, str] = {}
    evidence_lines = []
    for idx, ev in enumerate(evidence_pool[:50], start=1):  # Cap at 50
        eid = ev.get("evidence_id", "")
        if not eid:
            continue
        label_to_eid[idx] = eid
        statement = ev.get("statement", "")[:200]
        quote = ev.get("direct_quote", "")[:150]
        evidence_lines.append(
            f"[{idx}] {statement}"
            + (f' (quote: "{quote}")' if quote else "")
        )

    if not evidence_lines:
        return section_text

    evidence_block = "\n".join(evidence_lines)

    prompt = (
        f"Insert inline citations [N] into the following academic text.\n\n"
        f"TEXT:\n{clean_text}\n\n"
        f"AVAILABLE EVIDENCE (number -> statement):\n{evidence_block}\n\n"
        f"Return the text with [N] citations inserted. Do not change any words."
    )

    try:
        result = await client.generate(
            prompt=prompt,
            system=CITATION_SYSTEM,
            max_tokens=PG_CITATION_AGENT_MAX_TOKENS,
            temperature=0.2,
            thinking_mode=False,
        )

        cited_text = result.content.strip()

        # Validate: ensure no words were changed (basic check)
        original_words = len(re.sub(r'\[\d+\]', '', clean_text).split())
        result_words = len(re.sub(r'\[\d+\]', '', cited_text).split())

        if abs(original_words - result_words) > original_words * 0.20:
            logger.warning(
                "[polaris graph] ARCH-3: Citation agent changed word count "
                "(%d -> %d, %.1f%% diff) — using original text",
                original_words, result_words,
                abs(original_words - result_words) / max(original_words, 1) * 100,
            )
            return section_text

        # Map [N] back to [CITE:ev_xxx] for downstream resolve_citations()
        def _remap_citation(match: re.Match) -> str:
            num = int(match.group(1))
            eid = label_to_eid.get(num)
            if eid:
                return f"[CITE:{eid}]"
            return match.group(0)  # Keep unknown numbers as-is

        cited_text = re.sub(r'\[(\d+)\]', _remap_citation, cited_text)

        # Count inserted citations
        citation_count = len(re.findall(r'\[CITE:[^\]]+\]', cited_text))
        logger.info(
            "[polaris graph] ARCH-3: Citation agent inserted %d [CITE:ev_xxx] "
            "citations into %d-word section",
            citation_count, original_words,
        )

        return cited_text

    except Exception as exc:
        logger.warning(
            "[polaris graph] ARCH-3: Citation agent failed: %s — using original text",
            str(exc)[:200],
        )
        return section_text


async def recite_all_sections(
    client: OpenRouterClient,
    sections: list[Any],
    evidence: list[dict],
) -> list[Any]:
    """Run citation agent on all sections that need better citations.

    Only re-cites sections with low citation density (< 3 per 500 words).
    Counts both [CITE:ev_xxx] and [N] format citations.
    """
    if not PG_CITATION_AGENT_ENABLED:
        logger.info(
            "[polaris graph] ARCH-3: Citation agent DISABLED (PG_CITATION_AGENT_ENABLED=0). "
            "Sections will use original citations from section_writer.",
        )
        return sections

    import asyncio

    min_citations_per_500w = int(os.getenv("PG_MIN_CITATIONS_PER_500W", "3"))
    tasks = []

    for section in sections:
        text = getattr(section, "content", "") or getattr(section, "text", "")
        word_count = len(text.split())
        citation_count = _count_citations(text)
        expected_min = max(1, (word_count // 500) * min_citations_per_500w)

        if citation_count < expected_min:
            # Filter evidence relevant to this section
            section_id = getattr(section, "section_id", "")
            section_evidence = [
                e for e in evidence
                if e.get("section_id") == section_id
                or not section_id  # Fall back to all evidence if no section_id
            ][:50]

            logger.info(
                "[polaris graph] ARCH-3: Re-citing section '%s' "
                "(%d citations < %d expected, %d words, %d evidence)",
                getattr(section, "title", "?"),
                citation_count, expected_min, word_count, len(section_evidence),
            )

            tasks.append((section, section_evidence))

    if not tasks:
        logger.info(
            "[polaris graph] ARCH-3: All sections have adequate citation density",
        )
        return sections

    # Run citation agent on citation-poor sections concurrently
    sem = asyncio.Semaphore(4)

    async def _recite(section, section_evidence):
        async with sem:
            text = getattr(section, "content", "") or getattr(section, "text", "")
            cited = await insert_citations(client, text, section_evidence)
            if hasattr(section, "content"):
                section.content = cited
            elif hasattr(section, "text"):
                section.text = cited
            return section

    recite_tasks = [_recite(s, ev) for s, ev in tasks]
    await asyncio.gather(*recite_tasks, return_exceptions=True)

    logger.info(
        "[polaris graph] ARCH-3: Re-cited %d/%d sections",
        len(tasks), len(sections),
    )

    return sections
