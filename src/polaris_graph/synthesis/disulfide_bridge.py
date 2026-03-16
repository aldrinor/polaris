"""
MoST Disulfide Bond: Cross-Section Source Consistency.

Same source cited in multiple sections must not contradict itself.
Builds a source-section citation graph and verifies structural consistency.
Zero LLM cost (pure embedding computation).

Cost: 0 LLM calls, ~2-3 seconds.
"""

import logging
import os
import re
from collections import defaultdict

import numpy as np

from src.polaris_graph.schemas import SectionDraft
from src.utils.embedding_service import embed_texts

logger = logging.getLogger(__name__)

# Thresholds (LAW VI)
_CONTRADICTION_THRESHOLD = float(os.getenv("PG_DISULFIDE_CONTRADICTION_THRESHOLD", "0.30"))
_REDUNDANCY_THRESHOLD = float(os.getenv("PG_DISULFIDE_REDUNDANCY_THRESHOLD", "0.85"))


def analyze_disulfide_bridges(
    sections: list[SectionDraft],
    evidence: list[dict],
) -> dict:
    """Run disulfide bridge analysis: check same-source cross-section consistency.

    Builds source-section citation graph. For sources cited in 2+ sections,
    extracts claims from each section and checks for contradictions and
    verbatim redundancies.

    Args:
        sections: All SectionDraft objects.
        evidence: Full verified evidence pool.

    Returns:
        Dict with keys: consistent_bridges, contradictions, redundancies, stats.
    """
    if not sections or not evidence:
        return _empty_result()

    # Build evidence lookup: evidence_id -> evidence dict
    ev_lookup = {
        e.get("evidence_id", ""): e
        for e in evidence
        if e.get("evidence_id")
    }

    # Build source-section citation graph
    # source_url -> {section_id -> [(evidence_id, statement_in_context)]}
    source_sections: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for sec in sections:
        sid = getattr(sec, "section_id", "")
        content = getattr(sec, "content", "")
        cited_ids = set(re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", content))

        for eid in cited_ids:
            ev = ev_lookup.get(eid)
            if not ev:
                continue
            source_url = ev.get("source_url", "")
            if not source_url:
                continue
            statement = ev.get("statement", "")
            source_sections[source_url][sid].append((eid, statement))

    # Filter to sources cited in 2+ sections
    multi_section_sources = {
        url: sections_map
        for url, sections_map in source_sections.items()
        if len(sections_map) >= 2
    }

    if not multi_section_sources:
        return _empty_result()

    contradictions: list[dict] = []
    redundancies: list[dict] = []
    consistent_bridges: list[dict] = []

    for source_url, sections_map in multi_section_sources.items():
        # Collect all (section_id, evidence_id, statement) tuples
        all_claims: list[tuple[str, str, str]] = []
        for sid, items in sections_map.items():
            for eid, stmt in items:
                if stmt:
                    all_claims.append((sid, eid, stmt))

        if len(all_claims) < 2:
            continue

        # Embed all claims from this source
        claim_texts = [c[2][:200] for c in all_claims]
        try:
            vecs = np.array(embed_texts(claim_texts))
            sim = vecs @ vecs.T
        except Exception as exc:
            logger.debug(
                "[MoST-Disulfide] Embedding failed for source '%s': %s",
                source_url[:60],
                str(exc)[:100],
            )
            continue

        # Compare pairwise across different sections
        found_issue = False
        for i in range(len(all_claims)):
            for j in range(i + 1, len(all_claims)):
                sid_i, eid_i, stmt_i = all_claims[i]
                sid_j, eid_j, stmt_j = all_claims[j]

                # Only compare across different sections
                if sid_i == sid_j:
                    continue

                pair_sim = float(sim[i][j])

                if pair_sim >= _REDUNDANCY_THRESHOLD:
                    redundancies.append({
                        "source_url": source_url[:100],
                        "section_a": sid_i,
                        "section_b": sid_j,
                        "evidence_a": eid_i,
                        "evidence_b": eid_j,
                        "claim_a": stmt_i[:120],
                        "claim_b": stmt_j[:120],
                        "similarity": round(pair_sim, 3),
                    })
                    found_issue = True
                elif pair_sim < _CONTRADICTION_THRESHOLD:
                    contradictions.append({
                        "source_url": source_url[:100],
                        "section_a": sid_i,
                        "section_b": sid_j,
                        "evidence_a": eid_i,
                        "evidence_b": eid_j,
                        "claim_a": stmt_i[:120],
                        "claim_b": stmt_j[:120],
                        "similarity": round(pair_sim, 3),
                    })
                    found_issue = True

        if not found_issue:
            consistent_bridges.append({
                "source_url": source_url[:100],
                "sections": list(sections_map.keys()),
                "claim_count": len(all_claims),
            })

    stats = {
        "multi_section_sources": len(multi_section_sources),
        "contradictions": len(contradictions),
        "redundancies": len(redundancies),
        "consistent_bridges": len(consistent_bridges),
    }

    logger.info(
        "[MoST-Disulfide] Bridge analysis: %d multi-section sources, "
        "%d contradictions, %d redundancies, %d consistent",
        stats["multi_section_sources"],
        stats["contradictions"],
        stats["redundancies"],
        stats["consistent_bridges"],
    )

    return {
        "consistent_bridges": consistent_bridges,
        "contradictions": contradictions,
        "redundancies": redundancies,
        "stats": stats,
    }


def format_disulfide_findings_for_phase_r(
    disulfide_result: dict,
    target_section_id: str,
) -> str:
    """Format disulfide findings as context for Phase R prompt.

    Args:
        disulfide_result: Output of analyze_disulfide_bridges().
        target_section_id: The section being revised.

    Returns:
        Formatted string for Phase R prompt injection.
    """
    contradictions = disulfide_result.get("contradictions", [])
    redundancies = disulfide_result.get("redundancies", [])

    relevant_contradictions = [
        c for c in contradictions
        if c["section_a"] == target_section_id or c["section_b"] == target_section_id
    ]
    relevant_redundancies = [
        r for r in redundancies
        if r["section_a"] == target_section_id or r["section_b"] == target_section_id
    ]

    parts = []
    if relevant_contradictions:
        parts.append("Same-source CONTRADICTIONS (must resolve):")
        for c in relevant_contradictions[:3]:
            other = c["section_b"] if c["section_a"] == target_section_id else c["section_a"]
            parts.append(
                f"  - Source: {c['source_url'][:60]}"
            )
            parts.append(f"    This section: \"{c['claim_a'][:80]}\"")
            parts.append(f"    Section {other}: \"{c['claim_b'][:80]}\"")
            parts.append(f"    Similarity: {c['similarity']} (LOW = likely contradiction)")

    if relevant_redundancies:
        parts.append("Same-source REDUNDANCIES (consolidate):")
        for r in relevant_redundancies[:3]:
            other = r["section_b"] if r["section_a"] == target_section_id else r["section_a"]
            parts.append(
                f"  - \"{r['claim_a'][:80]}\" repeated in section {other}"
            )

    return "\n".join(parts) if parts else "No cross-section source issues detected."


def _empty_result() -> dict:
    """Return empty disulfide result."""
    return {
        "consistent_bridges": [],
        "contradictions": [],
        "redundancies": [],
        "stats": {
            "multi_section_sources": 0,
            "contradictions": 0,
            "redundancies": 0,
            "consistent_bridges": 0,
        },
    }
