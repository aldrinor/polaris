"""
MoST Phase E: Evidence Self-Exploration (Van der Waals Bond).

Implements the self-exploration bond from "The Molecular Structure of Thought"
(arXiv 2601.06002). Redistributes unused evidence to sections that could benefit,
bridging distant concept clusters.

Cost: ~1 LLM call per enriched section (~3-5 calls, ~$0.004-0.009, ~1-3 min)
"""

import asyncio
import logging
import os
import re
from typing import Any

from src.polaris_graph.schemas import SectionDraft

logger = logging.getLogger(__name__)


async def explore_unused_evidence(
    client,
    sections: list[SectionDraft],
    all_evidence: list[dict],
    section_evidence_map: dict[str, list[str]],
    query: str,
) -> list[SectionDraft]:
    """Redistribute unused evidence to sections that could benefit.

    Finds evidence not cited in any section, matches to best sections
    via content similarity, enriches affected sections with new sentences.

    Args:
        client: OpenRouter LLM client.
        sections: All SectionDraft objects.
        all_evidence: Full verified evidence pool.
        section_evidence_map: Map of section_id -> evidence_id list.
        query: Original research query.

    Returns:
        Updated list of SectionDraft (some enriched with new evidence).
    """
    if not sections or not all_evidence:
        return sections

    threshold = float(os.getenv("PG_EXPLORE_SIMILARITY_THRESHOLD", "0.55"))
    max_per_section = int(os.getenv("PG_EXPLORE_MAX_NEW_PER_SECTION", "5"))

    # Step 1: Find unused evidence
    unused = _find_unused_evidence(sections, all_evidence)
    if not unused:
        logger.info("[MoST-E] All evidence is cited, skipping exploration")
        return sections

    logger.info(
        "[MoST-E] Found %d unused evidence pieces out of %d total",
        len(unused), len(all_evidence),
    )

    # Step 2: Match unused evidence to sections by content similarity
    matches = _match_evidence_to_sections(
        unused=unused,
        sections=sections,
        threshold=threshold,
        max_per_section=max_per_section,
    )

    if not matches:
        logger.info("[MoST-E] No good matches found above threshold %.2f", threshold)
        return sections

    # Step 3: Enrich sections that received matches
    results = list(sections)
    enriched_count = 0
    total_redistributed = 0

    for i, sec in enumerate(sections):
        sid = getattr(sec, 'section_id', '')
        new_ev = matches.get(sid, [])
        if not new_ev:
            continue

        try:
            enriched = await _enrich_section(client, sec, new_ev, query)
            if enriched is not None:
                # CASE_2 guard: reject if enriched is shorter than original
                orig_words = len(getattr(sec, 'content', '').split())
                enriched_words = len(getattr(enriched, 'content', '').split())
                if enriched_words >= orig_words:
                    results[i] = enriched
                    enriched_count += 1
                    total_redistributed += len(new_ev)
                    logger.info(
                        "[MoST-E] Enriched section '%s' with %d new evidence (%d -> %d words)",
                        getattr(sec, 'title', '')[:40],
                        len(new_ev),
                        orig_words,
                        enriched_words,
                    )
                else:
                    logger.warning(
                        "[MoST-E] Enrichment shortened section '%s' (%d -> %d words), keeping original",
                        getattr(sec, 'title', '')[:40], orig_words, enriched_words,
                    )
        except Exception as exc:
            logger.warning(
                "[MoST-E] Enrichment failed for section '%s': %s",
                getattr(sec, 'title', '')[:40], str(exc)[:200],
            )

    logger.info(
        "[MoST-E] Exploration complete: %d sections enriched, %d evidence redistributed",
        enriched_count, total_redistributed,
    )
    return results


def _find_unused_evidence(
    sections: list[SectionDraft],
    all_evidence: list[dict],
) -> list[dict]:
    """Collect evidence pieces not cited in any section.

    Scans all [CITE:ev_xxx] markers across all section content.
    Returns evidence pieces not found in any citation, sorted by
    relevance_score descending.

    Args:
        sections: All report sections.
        all_evidence: Full evidence pool.

    Returns:
        List of unused evidence dicts, sorted by relevance.
    """
    # Collect all cited evidence IDs across all sections
    cited_ids = set()
    for sec in sections:
        content = getattr(sec, 'content', '')
        found = re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)
        cited_ids.update(found)

    # Filter to unused, sorted by relevance
    unused = [
        e for e in all_evidence
        if e.get("evidence_id", "") not in cited_ids
    ]
    unused.sort(key=lambda e: e.get("relevance_score", 0.0), reverse=True)
    return unused


def _match_evidence_to_sections(
    unused: list[dict],
    sections: list[SectionDraft],
    threshold: float = 0.55,
    max_per_section: int = 5,
) -> dict[str, list[dict]]:
    """M-02: Match unused evidence to best-fit sections via embedding cosine.

    Replaces Jaccard word-overlap (max ~0.08 for 20-word evidence vs 70-word
    section text, making threshold 0.45 impossible). Uses embedding cosine
    similarity which operates in semantic space.

    Args:
        unused: Unused evidence pieces.
        sections: All report sections.
        threshold: Minimum cosine similarity (default 0.55).
        max_per_section: Max new evidence per section.

    Returns:
        Dict mapping section_id -> list of matched evidence dicts.
    """
    if not unused or not sections:
        return {}

    import numpy as np
    from src.utils.embedding_service import embed_texts

    # Build texts for embedding
    ev_texts = []
    ev_filtered = []
    for e in unused:
        stmt = e.get("statement", "")
        if stmt:
            ev_texts.append(stmt[:200])
            ev_filtered.append(e)

    sec_texts = []
    sec_ids = []
    for sec in sections:
        title = getattr(sec, "title", "")
        content = getattr(sec, "content", "")[:500]
        sec_texts.append(f"{title} {content}")
        sec_ids.append(getattr(sec, "section_id", ""))

    if not ev_texts or not sec_texts:
        return {}

    # Embed all texts in one batch
    all_texts = ev_texts + sec_texts
    embeddings = np.array(embed_texts(all_texts))
    ev_vecs = embeddings[: len(ev_texts)]
    sec_vecs = embeddings[len(ev_texts) :]

    # Cosine similarity matrix (evidence x sections)
    # Embeddings are already L2-normalized by embedding_service
    similarity = ev_vecs @ sec_vecs.T

    matches: dict[str, list[dict]] = {}
    for i, ev in enumerate(ev_filtered):
        best_j = int(np.argmax(similarity[i]))
        best_score = float(similarity[i][best_j])
        if best_score >= threshold:
            sid = sec_ids[best_j]
            existing = matches.setdefault(sid, [])
            if len(existing) < max_per_section:
                existing.append(ev)

    logger.info(
        "[MoST-E] Embedding matching: %d evidence -> %d sections matched "
        "(threshold=%.2f)",
        len(ev_filtered),
        sum(len(v) for v in matches.values()),
        threshold,
    )
    return matches


async def _enrich_section(
    client,
    section: SectionDraft,
    new_evidence: list[dict],
    query: str,
) -> SectionDraft | None:
    """Enrich a section with newly matched evidence.

    Asks LLM to integrate 1-2 sentences per evidence piece at the most
    relevant location. All inserted sentences MUST have [CITE:evidence_id].

    Args:
        client: OpenRouter LLM client.
        section: Section to enrich.
        new_evidence: Evidence pieces to integrate.
        query: Research query for context.

    Returns:
        Enriched SectionDraft, or None if enrichment fails.
    """
    # Format new evidence for prompt
    ev_formatted = []
    for ev in new_evidence[:5]:  # Cap at 5 per section
        ev_id = ev.get("evidence_id", "")
        statement = ev.get("statement", "")[:200]
        source = ev.get("source_title", "") or ev.get("source_url", "")[:50]
        ev_formatted.append(f"- [{ev_id}] {statement} (Source: {source})")

    prompt = (
        "You are enriching a research section with additional evidence.\n\n"
        f"RESEARCH QUESTION: {query}\n\n"
        f"SECTION: {getattr(section, 'title', '')}\n"
        f"{getattr(section, 'content', '')}\n\n"
        "NEW EVIDENCE TO INTEGRATE:\n"
        + "\n".join(ev_formatted)
        + "\n\nTASK: Add 1-2 sentences per evidence piece at the most relevant location.\n"
        "RULES:\n"
        "- Use [CITE:evidence_id] for ALL new claims (e.g., [CITE:ev_abc123])\n"
        "- Do NOT rewrite or remove existing content\n"
        "- Do NOT change existing [CITE:] markers\n"
        "- Maintain academic tone\n"
        "- Output the COMPLETE revised section content only (no title)\n"
    )

    try:
        resp = await client.generate(
            prompt, max_tokens=int(os.getenv("PG_EVIDENCE_ENRICH_MAX_TOKENS", "8192")),
        )
        content = getattr(resp, 'content', '') or ''
        if not content or len(content) < 50:
            return None

        # Verify new citations were actually added
        new_ev_ids = {ev.get("evidence_id", "") for ev in new_evidence}
        found_new = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)) & new_ev_ids
        if not found_new:
            logger.warning(
                "[MoST-E] LLM did not add any [CITE:] markers for new evidence in '%s'",
                getattr(section, 'title', '')[:40],
            )
            return None

        # M-01: Sync evidence_ids from actual CITE markers in enriched content
        from src.polaris_graph.synthesis.section_utils import sync_evidence_ids_from_content
        return sync_evidence_ids_from_content(SectionDraft(
            section_id=getattr(section, 'section_id', ''),
            title=getattr(section, 'title', ''),
            content=content,
            claims_made=getattr(section, 'claims_made', []),
            evidence_ids=getattr(section, 'evidence_ids', []),
        ))
    except Exception as exc:
        logger.warning(
            "[MoST-E] Enrichment LLM call failed for '%s': %s",
            getattr(section, 'title', '')[:40], str(exc)[:200],
        )
        return None
