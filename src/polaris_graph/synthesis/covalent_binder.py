"""
MoST Covalent Bond: Claim-Evidence Binding Verification.

Verifies that every claim with a [CITE:ev_xxx] marker is semantically close
to its cited evidence. Identifies weak bonds, broken bonds, missing bonds,
and unbonded claims. Zero LLM cost (pure embedding computation).

Cost: 0 LLM calls, ~2-5 seconds.
"""

import logging
import os
import re

import numpy as np

from src.polaris_graph.schemas import SectionDraft
from src.utils.embedding_service import embed_texts

logger = logging.getLogger(__name__)

# Thresholds from config (LAW VI)
_WEAK_BOND_THRESHOLD = float(os.getenv("PG_COVALENT_WEAK_THRESHOLD", "0.40"))
_BROKEN_BOND_THRESHOLD = float(os.getenv("PG_COVALENT_BROKEN_THRESHOLD", "0.25"))
_MISSING_BOND_THRESHOLD = float(os.getenv("PG_COVALENT_MISSING_THRESHOLD", "0.60"))

# Regex for numeric/named-entity sentences that should have citations
_DATA_PATTERN = re.compile(
    r"\b(?:\d+\.?\d*\s*%|\$\d|USD|EUR|\d+\s*(?:mg|ppm|ppb|ppt|L|gal|m3))\b",
    re.IGNORECASE,
)


def analyze_covalent_bonds(
    sections: list[SectionDraft],
    evidence: list[dict],
) -> dict:
    """Run covalent bond analysis on all sections.

    For each section:
    1. Extract sentences with [CITE:ev_xxx] markers and verify binding
    2. Find data-bearing sentences without citations and check for missing bonds

    Args:
        sections: All SectionDraft objects.
        evidence: Full verified evidence pool.

    Returns:
        Dict with keys: weak_bonds, broken_bonds, missing_bonds,
        unbonded_claims, auto_fixes, stats.
    """
    if not sections or not evidence:
        return _empty_result()

    # Build evidence lookup: evidence_id -> statement
    ev_lookup = {
        e.get("evidence_id", ""): e.get("statement", "")
        for e in evidence
        if e.get("evidence_id") and e.get("statement")
    }

    all_weak: list[dict] = []
    all_broken: list[dict] = []
    all_missing: list[dict] = []
    all_unbonded: list[dict] = []
    auto_fixes: list[dict] = []

    for sec in sections:
        content = getattr(sec, "content", "")
        sid = getattr(sec, "section_id", "")
        if not content:
            continue

        # Split into sentences (simple split, preserving CITE markers)
        sentences = _split_to_sentences(content)

        cited_sentences = []
        uncited_data_sentences = []

        for sent in sentences:
            cite_ids = re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", sent)
            if cite_ids:
                cited_sentences.append((sent, cite_ids))
            elif _DATA_PATTERN.search(sent) and len(sent) > 30:
                uncited_data_sentences.append(sent)

        # Phase 1: Verify cited sentence <-> evidence binding
        if cited_sentences:
            _verify_cited_bonds(
                cited_sentences=cited_sentences,
                ev_lookup=ev_lookup,
                section_id=sid,
                weak_bonds=all_weak,
                broken_bonds=all_broken,
            )

        # Phase 2: Find missing bonds for uncited data sentences
        if uncited_data_sentences and ev_lookup:
            _find_missing_bonds(
                uncited_sentences=uncited_data_sentences,
                evidence=evidence,
                section_id=sid,
                missing_bonds=all_missing,
                unbonded_claims=all_unbonded,
                auto_fixes=auto_fixes,
            )

    stats = {
        "weak_bonds": len(all_weak),
        "broken_bonds": len(all_broken),
        "missing_bonds": len(all_missing),
        "unbonded_claims": len(all_unbonded),
        "auto_fixes": len(auto_fixes),
    }

    logger.info(
        "[MoST-Covalent] Bond analysis: %d weak, %d broken, %d missing, "
        "%d unbonded, %d auto-fixes",
        stats["weak_bonds"],
        stats["broken_bonds"],
        stats["missing_bonds"],
        stats["unbonded_claims"],
        stats["auto_fixes"],
    )

    return {
        "weak_bonds": all_weak,
        "broken_bonds": all_broken,
        "missing_bonds": all_missing,
        "unbonded_claims": all_unbonded,
        "auto_fixes": auto_fixes,
        "stats": stats,
    }


def apply_auto_fixes(
    sections: list[SectionDraft],
    auto_fixes: list[dict],
) -> list[SectionDraft]:
    """Apply auto-fix insertions of missing CITE markers.

    Args:
        sections: Report sections.
        auto_fixes: List of {section_id, sentence, evidence_id, similarity}.

    Returns:
        Updated sections with CITE markers inserted.
    """
    if not auto_fixes:
        return sections

    # Group fixes by section
    fixes_by_section: dict[str, list[dict]] = {}
    for fix in auto_fixes:
        sid = fix.get("section_id", "")
        fixes_by_section.setdefault(sid, []).append(fix)

    updated = list(sections)
    applied = 0
    for i, sec in enumerate(updated):
        sid = getattr(sec, "section_id", "")
        if sid not in fixes_by_section:
            continue

        content = getattr(sec, "content", "")
        for fix in fixes_by_section[sid]:
            sentence = fix["sentence"]
            ev_id = fix["evidence_id"]
            marker = f" [CITE:{ev_id}]"

            # Insert marker at end of sentence (before period)
            if sentence in content and marker not in content:
                # Find sentence and append CITE before terminal punctuation
                idx = content.index(sentence) + len(sentence)
                # Back up past trailing period/space
                insert_at = idx
                while insert_at > 0 and content[insert_at - 1] in ". ":
                    insert_at -= 1
                content = content[:insert_at] + marker + content[insert_at:]
                applied += 1

        if applied > 0:
            from src.polaris_graph.synthesis.section_utils import sync_evidence_ids_from_content
            updated[i] = sync_evidence_ids_from_content(SectionDraft(
                section_id=sid,
                title=getattr(sec, "title", ""),
                content=content,
                claims_made=getattr(sec, "claims_made", []),
                evidence_ids=getattr(sec, "evidence_ids", []),
            ))

    if applied > 0:
        logger.info("[MoST-Covalent] Applied %d auto-fix CITE insertions", applied)
    return updated


def _verify_cited_bonds(
    cited_sentences: list[tuple[str, list[str]]],
    ev_lookup: dict[str, str],
    section_id: str,
    weak_bonds: list[dict],
    broken_bonds: list[dict],
) -> None:
    """Check claim-evidence binding strength for cited sentences."""
    # Collect all (sentence, evidence_id) pairs
    pairs: list[tuple[str, str]] = []
    for sent, cite_ids in cited_sentences:
        for eid in cite_ids:
            if eid in ev_lookup:
                pairs.append((sent, eid))

    if not pairs:
        return

    # Embed sentences and evidence statements in batch
    sent_texts = [p[0][:300] for p in pairs]
    ev_texts = [ev_lookup[p[1]][:300] for p in pairs]

    all_texts = sent_texts + ev_texts
    vecs = np.array(embed_texts(all_texts))
    sent_vecs = vecs[: len(sent_texts)]
    ev_vecs = vecs[len(sent_texts) :]

    # Compute pairwise similarity (diagonal of the matrix)
    for i, (sent, eid) in enumerate(pairs):
        sim = float(np.dot(sent_vecs[i], ev_vecs[i]))
        if sim < _BROKEN_BOND_THRESHOLD:
            broken_bonds.append({
                "section_id": section_id,
                "sentence": sent[:150],
                "evidence_id": eid,
                "similarity": round(sim, 3),
            })
        elif sim < _WEAK_BOND_THRESHOLD:
            weak_bonds.append({
                "section_id": section_id,
                "sentence": sent[:150],
                "evidence_id": eid,
                "similarity": round(sim, 3),
            })


def _find_missing_bonds(
    uncited_sentences: list[str],
    evidence: list[dict],
    section_id: str,
    missing_bonds: list[dict],
    unbonded_claims: list[dict],
    auto_fixes: list[dict],
) -> None:
    """Find evidence matches for uncited data-bearing sentences."""
    ev_with_stmt = [
        e for e in evidence
        if e.get("statement") and e.get("evidence_id")
    ]
    if not ev_with_stmt or not uncited_sentences:
        return

    # Embed uncited sentences + evidence statements
    sent_texts = [s[:300] for s in uncited_sentences]
    ev_texts = [e["statement"][:300] for e in ev_with_stmt]

    all_texts = sent_texts + ev_texts
    vecs = np.array(embed_texts(all_texts))
    sent_vecs = vecs[: len(sent_texts)]
    ev_vecs = vecs[len(sent_texts) :]

    # For each uncited sentence, find best evidence match
    similarity = sent_vecs @ ev_vecs.T

    for i, sent in enumerate(uncited_sentences):
        best_j = int(np.argmax(similarity[i]))
        best_score = float(similarity[i][best_j])
        best_ev = ev_with_stmt[best_j]

        if best_score >= _MISSING_BOND_THRESHOLD:
            entry = {
                "section_id": section_id,
                "sentence": sent[:150],
                "evidence_id": best_ev["evidence_id"],
                "similarity": round(best_score, 3),
            }
            missing_bonds.append(entry)
            auto_fixes.append(entry)
        elif best_score < _BROKEN_BOND_THRESHOLD:
            unbonded_claims.append({
                "section_id": section_id,
                "sentence": sent[:150],
                "best_match_similarity": round(best_score, 3),
            })


def _split_to_sentences(text: str) -> list[str]:
    """Simple sentence splitting that preserves CITE markers."""
    try:
        from src.polaris_graph.synthesis.report_assembler import _split_sentences
        return _split_sentences(text, min_len=20)
    except ImportError:
        # Fallback: split on period-space
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if len(p.strip()) >= 20]


def _empty_result() -> dict:
    """Return empty covalent audit result."""
    return {
        "weak_bonds": [],
        "broken_bonds": [],
        "missing_bonds": [],
        "unbonded_claims": [],
        "auto_fixes": [],
        "stats": {
            "weak_bonds": 0,
            "broken_bonds": 0,
            "missing_bonds": 0,
            "unbonded_claims": 0,
            "auto_fixes": 0,
        },
    }
