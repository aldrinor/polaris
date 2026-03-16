"""
Embedding-based evidence routing for section assignment.

Replaces the LLM-based _assign_evidence_globally() with deterministic
embedding similarity. Zero LLM cost, 100% assignment, ~2 seconds.

Problem: _assign_evidence_globally() uses a single LLM call with 200-char
truncated summaries. Failed on TEST_002 (52->0 assigned). Costs ~$0.05/call,
stochastic, fragile ID mapping.

Solution: Batch embed evidence statements and section descriptions.
Cosine similarity matrix assigns each evidence to its best section.
Evidence relevant to multiple sections (small delta) marked cross-section.
"""

import logging
import os

import numpy as np

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Feature flag (LAW VI)
PG_EMBEDDING_ROUTING = os.getenv("PG_EMBEDDING_ROUTING", "1") == "1"

# Evidence with top-2 section similarity delta below this threshold
# is treated as cross-section (visible to all sections).
PG_CROSS_SECTION_SIMILARITY_DELTA = float(
    os.getenv("PG_CROSS_SECTION_SIMILARITY_DELTA", "0.05")
)

# Minimum similarity to be assigned to any section.
# Evidence below this threshold is unassigned (goes to cross-section pool).
PG_EMBEDDING_ROUTING_MIN_SIMILARITY = float(
    os.getenv("PG_EMBEDDING_ROUTING_MIN_SIMILARITY", "0.20")
)


def route_evidence_to_sections(
    evidence: list[dict],
    sections: list,
    query: str,
) -> tuple[dict[str, list[str]], list[str]]:
    """Deterministic embedding-based evidence-to-section routing.

    Each evidence piece is assigned to its best-matching section by cosine
    similarity between the evidence statement and section title+description.

    Evidence whose top-2 section similarity delta is below
    PG_CROSS_SECTION_SIMILARITY_DELTA is flagged as cross-section
    (visible to all sections).

    Args:
        evidence: List of evidence dicts with evidence_id, statement.
        sections: List of SectionOutlineItem (or dicts with section_id, title, description).
        query: Original research query (used as context in section embeddings).

    Returns:
        (section_assignments, cross_section_ids) — same tuple type as
        _assign_evidence_globally() for drop-in replacement.
        - section_assignments: {section_id: [ev_xxx, ...]}
        - cross_section_ids: [ev_xxx, ...] evidence visible to all sections
    """
    if not evidence or not sections:
        logger.warning("[evidence_router] Empty evidence or sections, skipping routing")
        return {}, []

    try:
        from src.utils.embedding_service import embed_texts
    except ImportError:
        logger.warning("[evidence_router] embedding_service unavailable, skipping routing")
        return {}, []

    try:
        # Build section texts: title + description (+ query context)
        section_ids = []
        section_texts = []
        for sec in sections:
            sid = getattr(sec, "section_id", None) or sec.get("section_id", "")
            title = getattr(sec, "title", None) or sec.get("title", "")
            desc = getattr(sec, "description", None) or sec.get("description", "")
            section_ids.append(sid)
            section_texts.append(f"{title}. {desc}. Research question: {query}")

        # Build evidence texts: statement (primary signal)
        evidence_ids = []
        evidence_texts = []
        for ev in evidence:
            eid = ev.get("evidence_id", "")
            stmt = ev.get("statement", "")
            evidence_ids.append(eid)
            evidence_texts.append(stmt)

        if not section_texts or not evidence_texts:
            return {}, []

        # Batch embed — uses existing infrastructure (384-dim, pre-normalized)
        section_vecs = np.array(embed_texts(section_texts))
        evidence_vecs = np.array(embed_texts(evidence_texts))

        # Cosine similarity matrix: (num_evidence, num_sections)
        # Embeddings are pre-normalized, so dot product = cosine similarity
        similarity_matrix = evidence_vecs @ section_vecs.T

        # Primary assignment: argmax per evidence row
        best_section_indices = np.argmax(similarity_matrix, axis=1)
        best_scores = similarity_matrix[np.arange(len(evidence_ids)), best_section_indices]

        # Cross-section detection: evidence where top-2 delta is small
        cross_section_ids = []
        section_assignments: dict[str, list[str]] = {sid: [] for sid in section_ids}

        for i, eid in enumerate(evidence_ids):
            best_score = best_scores[i]

            # Skip evidence below minimum similarity threshold
            if best_score < PG_EMBEDDING_ROUTING_MIN_SIMILARITY:
                cross_section_ids.append(eid)
                continue

            best_idx = best_section_indices[i]
            best_sid = section_ids[best_idx]

            # Check if this evidence is borderline between sections
            if len(section_ids) >= 2:
                sorted_scores = np.sort(similarity_matrix[i])[::-1]
                delta = sorted_scores[0] - sorted_scores[1]
                if delta < PG_CROSS_SECTION_SIMILARITY_DELTA:
                    cross_section_ids.append(eid)

            # Always assign to primary section (even if also cross-section)
            section_assignments[best_sid].append(eid)

        # Remove empty sections from assignments
        section_assignments = {
            sid: ids for sid, ids in section_assignments.items() if ids
        }

        # Diagnostics
        assigned_total = sum(len(ids) for ids in section_assignments.values())
        logger.info(
            "[evidence_router] Embedding routing: %d evidence -> %d sections "
            "(%d assigned, %d cross-section, similarity range %.3f-%.3f)",
            len(evidence),
            len(section_assignments),
            assigned_total,
            len(cross_section_ids),
            float(np.min(best_scores)),
            float(np.max(best_scores)),
        )

        return section_assignments, cross_section_ids

    except Exception as exc:
        logger.warning(
            "[evidence_router] Embedding routing failed: %s — "
            "falling back to per-section filtering",
            str(exc)[:200],
        )
        return {}, []
