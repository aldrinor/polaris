"""
MoST Ionic Bond: Evidence-Section Affinity Rebalancing.

Checks if evidence pieces are cited in the section where they have highest
semantic affinity. Evidence "attracted" more strongly to a different section
than where it currently resides should migrate. Zero LLM cost.

Cost: 0 LLM calls, ~3-5 seconds.
"""

import logging
import os
import re

import numpy as np

from src.polaris_graph.schemas import SectionDraft
from src.utils.embedding_service import embed_texts

logger = logging.getLogger(__name__)

# Minimum affinity delta to recommend migration (LAW VI)
_MIN_AFFINITY_DELTA = float(os.getenv("PG_IONIC_MIN_DELTA", "0.15"))


def analyze_ionic_bonds(
    sections: list[SectionDraft],
    evidence: list[dict],
) -> dict:
    """Run ionic bond analysis: check evidence-section affinity.

    For each section, collect cited evidence, compute embedding similarity
    against ALL sections. Flag evidence where affinity to another section
    exceeds current section by > delta.

    Args:
        sections: All SectionDraft objects.
        evidence: Full verified evidence pool.

    Returns:
        Dict with keys: migrations, confirmed, stats.
    """
    if len(sections) < 2 or not evidence:
        return {"migrations": [], "confirmed": [], "stats": {"migrations": 0, "confirmed": 0}}

    # Build evidence lookup
    ev_lookup = {
        e.get("evidence_id", ""): e
        for e in evidence
        if e.get("evidence_id") and e.get("statement")
    }

    # Build section texts for embedding
    sec_texts = []
    sec_ids = []
    sec_id_to_idx = {}
    for i, sec in enumerate(sections):
        sid = getattr(sec, "section_id", "")
        title = getattr(sec, "title", "")
        content = getattr(sec, "content", "")[:500]
        sec_texts.append(f"{title} {content}")
        sec_ids.append(sid)
        sec_id_to_idx[sid] = i

    # Embed section texts
    sec_vecs = np.array(embed_texts(sec_texts))

    # Collect all cited evidence per section
    section_evidence: dict[str, list[str]] = {}
    for sec in sections:
        sid = getattr(sec, "section_id", "")
        content = getattr(sec, "content", "")
        cited = re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", content)
        section_evidence[sid] = list(set(cited))

    # Collect all unique evidence IDs to analyze
    all_cited_eids = set()
    for eids in section_evidence.values():
        all_cited_eids.update(eids)

    ev_items = [
        (eid, ev_lookup[eid])
        for eid in all_cited_eids
        if eid in ev_lookup
    ]

    if not ev_items:
        return {"migrations": [], "confirmed": [], "stats": {"migrations": 0, "confirmed": 0}}

    # Embed evidence statements
    ev_texts = [e["statement"][:200] for _, e in ev_items]
    ev_vecs = np.array(embed_texts(ev_texts))

    # Compute evidence x section similarity
    similarity = ev_vecs @ sec_vecs.T

    migrations: list[dict] = []
    confirmed: list[str] = []

    for i, (eid, ev) in enumerate(ev_items):
        # Find which section currently cites this evidence
        current_sections = [
            sid for sid, eids in section_evidence.items()
            if eid in eids
        ]

        for current_sid in current_sections:
            current_idx = sec_id_to_idx.get(current_sid)
            if current_idx is None:
                continue

            current_affinity = float(similarity[i][current_idx])
            best_idx = int(np.argmax(similarity[i]))
            best_affinity = float(similarity[i][best_idx])
            best_sid = sec_ids[best_idx]

            delta = best_affinity - current_affinity
            if best_sid != current_sid and delta >= _MIN_AFFINITY_DELTA:
                migrations.append({
                    "evidence_id": eid,
                    "from_section": current_sid,
                    "to_section": best_sid,
                    "current_affinity": round(current_affinity, 3),
                    "best_affinity": round(best_affinity, 3),
                    "delta": round(delta, 3),
                })
            else:
                confirmed.append(eid)

    stats = {
        "migrations": len(migrations),
        "confirmed": len(confirmed),
        "total_analyzed": len(ev_items),
    }

    logger.info(
        "[MoST-Ionic] Affinity analysis: %d migrations flagged, "
        "%d confirmed in place (out of %d evidence)",
        stats["migrations"],
        stats["confirmed"],
        stats["total_analyzed"],
    )

    return {
        "migrations": migrations,
        "confirmed": confirmed,
        "stats": stats,
    }


def format_ionic_findings_for_phase_r(
    ionic_result: dict,
    target_section_id: str,
) -> str:
    """Format ionic findings as context for Phase R prompt.

    Args:
        ionic_result: Output of analyze_ionic_bonds().
        target_section_id: The section being revised.

    Returns:
        Formatted string for Phase R prompt injection.
    """
    migrations = ionic_result.get("migrations", [])
    if not migrations:
        return "No evidence misplacements detected."

    # Evidence that should LEAVE this section
    outgoing = [
        m for m in migrations
        if m["from_section"] == target_section_id
    ]
    # Evidence that should ARRIVE in this section
    incoming = [
        m for m in migrations
        if m["to_section"] == target_section_id
    ]

    parts = []
    if outgoing:
        parts.append("Evidence that belongs in OTHER sections (consider removing):")
        for m in outgoing[:3]:
            parts.append(
                f"  - {m['evidence_id']} -> better fit in section {m['to_section']} "
                f"(delta={m['delta']:.2f})"
            )
    if incoming:
        parts.append("Evidence from OTHER sections that belongs HERE (consider adding):")
        for m in incoming[:3]:
            parts.append(
                f"  - {m['evidence_id']} from section {m['from_section']} "
                f"(delta={m['delta']:.2f})"
            )

    return "\n".join(parts) if parts else "No evidence misplacements detected."
