"""
MoST Peptide Bond: Narrative Flow Optimization.

Creates the backbone narrative structure. Detects dangling connectors,
cross-section repetition, weak transitions, and back-to-back connector
stutters. Provides both auto-fixes and Phase R instructions.
Zero LLM cost (pure embedding + regex computation).

Cost: 0 LLM calls, ~1-2 seconds.
"""

import logging
import os
import re

import numpy as np

from src.polaris_graph.schemas import SectionDraft
from src.utils.embedding_service import embed_texts

logger = logging.getLogger(__name__)

# Thresholds (LAW VI)
_REPEAT_THRESHOLD = float(os.getenv("PG_PEPTIDE_REPEAT_THRESHOLD", "0.80"))
_WEAK_TRANSITION_THRESHOLD = float(os.getenv("PG_PEPTIDE_WEAK_TRANSITION", "0.15"))

# Connectors that should not start a section
# FIX-047-K2: Expanded with contrastive connectors (T047 audit: "In contrast"
# opened Section 3 with nothing to contrast against).
_DANGLING_CONNECTORS = {
    "additionally", "furthermore", "moreover", "consequently",
    "similarly", "likewise", "nevertheless", "nonetheless",
    "indeed", "significantly", "notably",
    # Contrastive connectors (FIX-047-K2)
    "however", "conversely", "yet",
}

# Multi-word dangling connectors checked separately
_DANGLING_PHRASES = [
    "in contrast",
    "on the other hand",
    "on the contrary",
    "as a result",
    "in addition",
    "in particular",
    "for this reason",
]

# FIX-047-K2: Connector categories for back-to-back detection.
# Same-category consecutive connectors create awkward prose even when
# different words (e.g., "Moreover... Furthermore..." are both additive).
_CONNECTOR_CATEGORIES = {
    "additive": {"moreover", "furthermore", "additionally", "similarly",
                 "likewise", "indeed", "significantly", "notably",
                 "in addition"},
    "contrastive": {"however", "nevertheless", "nonetheless", "conversely",
                    "yet", "in contrast", "on the other hand",
                    "on the contrary"},
    "causal": {"therefore", "thus", "consequently", "hence",
               "as a result", "for this reason", "accordingly"},
}

# Build reverse lookup: word -> category
_WORD_TO_CATEGORY: dict[str, str] = {}
for _cat, _words in _CONNECTOR_CATEGORIES.items():
    for _w in _words:
        _WORD_TO_CATEGORY[_w] = _cat

# FIX-047-K2: Include both single-word and multi-word dangling connectors.
_ALL_DANGLING = sorted(
    list(_DANGLING_CONNECTORS) + _DANGLING_PHRASES,
    key=len, reverse=True,  # Longest first for greedy matching
)
_CONNECTOR_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(c) for c in _ALL_DANGLING) + r"),?\s",
    re.IGNORECASE,
)


def analyze_peptide_flow(
    sections: list[SectionDraft],
) -> dict:
    """Run peptide flow analysis on all sections.

    Detects:
    1. Dangling connectors at section starts
    2. Cross-section sentence repetition (embedding similarity)
    3. Weak transitions between adjacent sections
    4. Back-to-back connector stutters within sections

    Args:
        sections: All SectionDraft objects.

    Returns:
        Dict with keys: dangling_connectors, cross_section_repeats,
        weak_transitions, connector_stutters, stats.
    """
    if not sections:
        return _empty_result()

    dangling_connectors = _detect_dangling_connectors(sections)
    connector_stutters = _detect_connector_stutters(sections)
    cross_section_repeats = _detect_cross_section_repeats(sections)
    weak_transitions = _detect_weak_transitions(sections)

    stats = {
        "dangling_connectors": len(dangling_connectors),
        "cross_section_repeats": len(cross_section_repeats),
        "weak_transitions": len(weak_transitions),
        "connector_stutters": len(connector_stutters),
    }

    logger.info(
        "[MoST-Peptide] Flow analysis: %d dangling connectors, "
        "%d cross-section repeats, %d weak transitions, %d connector stutters",
        stats["dangling_connectors"],
        stats["cross_section_repeats"],
        stats["weak_transitions"],
        stats["connector_stutters"],
    )

    return {
        "dangling_connectors": dangling_connectors,
        "cross_section_repeats": cross_section_repeats,
        "weak_transitions": weak_transitions,
        "connector_stutters": connector_stutters,
        "stats": stats,
    }


def apply_auto_fixes(
    sections: list[SectionDraft],
    peptide_result: dict,
) -> list[SectionDraft]:
    """Apply auto-fixes for dangling connectors and connector stutters.

    Args:
        sections: Report sections.
        peptide_result: Output of analyze_peptide_flow().

    Returns:
        Updated sections with auto-fixes applied.
    """
    updated = list(sections)
    fixes_applied = 0

    # Fix dangling connectors at section starts
    dangling = peptide_result.get("dangling_connectors", [])
    if dangling:
        dangling_sids = {d["section_id"] for d in dangling}
        for i, sec in enumerate(updated):
            sid = getattr(sec, "section_id", "")
            if sid not in dangling_sids:
                continue
            content = getattr(sec, "content", "")
            new_content = _CONNECTOR_PATTERN.sub("", content)
            if new_content != content:
                updated[i] = SectionDraft(
                    section_id=sid,
                    title=getattr(sec, "title", ""),
                    content=new_content.strip(),
                    claims_made=getattr(sec, "claims_made", []),
                    evidence_ids=getattr(sec, "evidence_ids", []),
                )
                fixes_applied += 1

    # Fix back-to-back connector stutters
    stutters = peptide_result.get("connector_stutters", [])
    if stutters:
        stutter_sids = {s["section_id"] for s in stutters}
        for i, sec in enumerate(updated):
            sid = getattr(sec, "section_id", "")
            if sid not in stutter_sids:
                continue
            content = getattr(sec, "content", "")
            new_content = _fix_connector_stutters(content)
            if new_content != content:
                updated[i] = SectionDraft(
                    section_id=sid,
                    title=getattr(sec, "title", ""),
                    content=new_content,
                    claims_made=getattr(sec, "claims_made", []),
                    evidence_ids=getattr(sec, "evidence_ids", []),
                )
                fixes_applied += 1

    if fixes_applied > 0:
        logger.info("[MoST-Peptide] Applied %d auto-fixes", fixes_applied)
    return updated


def format_peptide_findings_for_phase_r(
    peptide_result: dict,
    target_section_id: str,
) -> str:
    """Format peptide findings as context for Phase R prompt.

    Args:
        peptide_result: Output of analyze_peptide_flow().
        target_section_id: The section being revised.

    Returns:
        Formatted string for Phase R prompt injection.
    """
    parts = []

    # Cross-section repeats in this section
    repeats = [
        r for r in peptide_result.get("cross_section_repeats", [])
        if target_section_id in r.get("sections", [])
    ]
    if repeats:
        parts.append("REPEATED content (remove from this section, already in others):")
        for r in repeats[:5]:
            home = r.get("recommended_home", "")
            if home != target_section_id:
                parts.append(
                    f"  - \"{r['sentence'][:80]}\" (keep in section {home})"
                )

    # Weak transitions involving this section
    weak = [
        w for w in peptide_result.get("weak_transitions", [])
        if w.get("from_section") == target_section_id
        or w.get("to_section") == target_section_id
    ]
    if weak:
        parts.append("WEAK TRANSITIONS (add connecting language):")
        for w in weak[:2]:
            parts.append(
                f"  - Between section {w['from_section']} and {w['to_section']} "
                f"(connection score: {w.get('score', 0):.2f})"
            )

    return "\n".join(parts) if parts else "No narrative flow issues detected."


def _detect_dangling_connectors(sections: list[SectionDraft]) -> list[dict]:
    """Detect connectors at the start of sections."""
    results = []
    for sec in sections:
        content = getattr(sec, "content", "").strip()
        if not content:
            continue
        first_sentence = content.split(".")[0] if "." in content else content[:200]
        match = _CONNECTOR_PATTERN.match(first_sentence)
        if match:
            results.append({
                "section_id": getattr(sec, "section_id", ""),
                "first_sentence": first_sentence[:100],
                "connector_word": match.group(1),
            })
    return results


def _detect_connector_stutters(sections: list[SectionDraft]) -> list[dict]:
    """Detect back-to-back connectors of the SAME CATEGORY within a section.

    FIX-047-K2: T047 audit found 10 B2B connector pairs like
    "Moreover→Furthermore" (both additive) that the old word_a==word_b
    check missed. Now uses category-based matching: two consecutive
    connectors from the same category (additive, contrastive, causal)
    within 200 chars are flagged.
    """
    results = []
    # Build regex for ALL known connectors (single + multi-word)
    all_connectors = sorted(
        list(_DANGLING_CONNECTORS) + _DANGLING_PHRASES
        + ["therefore", "thus", "hence", "accordingly",
           "in addition", "as a result", "for this reason"],
        key=len, reverse=True,
    )
    connector_re = re.compile(
        r"\b(" + "|".join(re.escape(c) for c in all_connectors) + r")\b",
        re.IGNORECASE,
    )
    for sec in sections:
        content = getattr(sec, "content", "")
        # Find all connector occurrences
        matches = list(connector_re.finditer(content))
        if len(matches) < 2:
            continue

        section_stutters = 0
        for i in range(len(matches) - 1):
            word_a = matches[i].group(1).lower()
            word_b = matches[i + 1].group(1).lower()
            gap = matches[i + 1].start() - matches[i].end()
            if gap >= 200:
                continue

            # FIX-047-K2: Category-based matching — flag same-category pairs
            cat_a = _WORD_TO_CATEGORY.get(word_a, "")
            cat_b = _WORD_TO_CATEGORY.get(word_b, "")
            if cat_a and cat_b and cat_a == cat_b:
                results.append({
                    "section_id": getattr(sec, "section_id", ""),
                    "connector_word": f"{word_a} -> {word_b}",
                    "connector_category": cat_a,
                    "gap_chars": gap,
                })
                section_stutters += 1
                if section_stutters >= 3:
                    break  # Cap at 3 stutters per section
    return results


def _detect_cross_section_repeats(sections: list[SectionDraft]) -> list[dict]:
    """Detect sentences repeated across sections using embedding similarity."""
    if len(sections) < 2:
        return []

    # Extract sentences per section (data-bearing only)
    section_sentences: list[tuple[str, str, str]] = []  # (section_id, sentence, text)
    for sec in sections:
        sid = getattr(sec, "section_id", "")
        content = getattr(sec, "content", "")
        # Simple sentence split
        sentences = re.split(r"(?<=[.!?])\s+", content)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) >= 40:  # Only meaningful sentences
                section_sentences.append((sid, sent[:200], sent))

    if len(section_sentences) < 2:
        return []

    # Limit to avoid embedding too many sentences
    max_sentences = int(os.getenv("PG_PEPTIDE_MAX_SENTENCES", "300"))
    if len(section_sentences) > max_sentences:
        section_sentences = section_sentences[:max_sentences]

    try:
        texts = [s[1] for s in section_sentences]
        vecs = np.array(embed_texts(texts))
        sim = vecs @ vecs.T
    except Exception as exc:
        logger.debug(
            "[MoST-Peptide] Embedding failed for repeat detection: %s",
            str(exc)[:100],
        )
        return []

    repeats: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i in range(len(section_sentences)):
        for j in range(i + 1, len(section_sentences)):
            sid_i = section_sentences[i][0]
            sid_j = section_sentences[j][0]
            if sid_i == sid_j:
                continue  # Same section, skip
            if (i, j) in seen_pairs:
                continue

            if float(sim[i][j]) >= _REPEAT_THRESHOLD:
                seen_pairs.add((i, j))
                # Recommend home = section with longer content
                sec_i_len = len(next(
                    (getattr(s, "content", "") for s in sections
                     if getattr(s, "section_id", "") == sid_i),
                    "",
                ))
                sec_j_len = len(next(
                    (getattr(s, "content", "") for s in sections
                     if getattr(s, "section_id", "") == sid_j),
                    "",
                ))
                recommended_home = sid_i if sec_i_len >= sec_j_len else sid_j

                repeats.append({
                    "sentence": section_sentences[i][1][:100],
                    "sections": [sid_i, sid_j],
                    "similarity": round(float(sim[i][j]), 3),
                    "recommended_home": recommended_home,
                })

    # Cap results
    return repeats[:50]


def _detect_weak_transitions(sections: list[SectionDraft]) -> list[dict]:
    """Check transition strength between adjacent sections."""
    if len(sections) < 2:
        return []

    # Get last paragraph of each section and first paragraph of the next
    transitions = []
    for i in range(len(sections) - 1):
        sec_a = sections[i]
        sec_b = sections[i + 1]
        content_a = getattr(sec_a, "content", "")
        content_b = getattr(sec_b, "content", "")

        # Last ~200 chars of section A, first ~200 chars of section B
        tail_a = content_a[-200:] if len(content_a) > 200 else content_a
        head_b = content_b[:200] if len(content_b) > 200 else content_b

        if tail_a and head_b:
            transitions.append((
                getattr(sec_a, "section_id", ""),
                getattr(sec_b, "section_id", ""),
                tail_a,
                head_b,
            ))

    if not transitions:
        return []

    # Embed tail/head pairs
    all_texts = []
    for _, _, tail, head in transitions:
        all_texts.extend([tail, head])

    try:
        vecs = np.array(embed_texts(all_texts))
    except Exception:
        return []

    weak_transitions = []
    for i, (sid_a, sid_b, _, _) in enumerate(transitions):
        tail_vec = vecs[i * 2]
        head_vec = vecs[i * 2 + 1]
        score = float(np.dot(tail_vec, head_vec))
        if score < _WEAK_TRANSITION_THRESHOLD:
            weak_transitions.append({
                "from_section": sid_a,
                "to_section": sid_b,
                "score": round(score, 3),
            })

    return weak_transitions


def _fix_connector_stutters(content: str) -> str:
    """Remove duplicate connectors within close proximity.

    FIX-059-H: Uses category-based matching consistent with detection
    at _detect_connector_stutters(). Old code used word_a == word_b
    (exact match only), causing 29 category-based stutters to be
    detected but 0 fixed.
    """
    # FIX-059-H: Use ALL connectors (single + multi-word) for matching,
    # consistent with detection regex at _detect_connector_stutters()
    all_connectors = sorted(
        list(_DANGLING_CONNECTORS) + _DANGLING_PHRASES
        + ["therefore", "thus", "hence", "accordingly",
           "in addition", "as a result", "for this reason"],
        key=len, reverse=True,
    )
    connector_re = re.compile(
        r"\b(" + "|".join(re.escape(c) for c in all_connectors) + r")\b",
        re.IGNORECASE,
    )
    matches = list(connector_re.finditer(content))
    if len(matches) < 2:
        return content

    # FIX-059-H: Find back-to-back same-CATEGORY connectors, remove the second
    removals = []
    for i in range(len(matches) - 1):
        word_a = matches[i].group(1).lower()
        word_b = matches[i + 1].group(1).lower()
        gap = matches[i + 1].start() - matches[i].end()
        # FIX-059-H: Category-based matching (was: word_a == word_b)
        cat_a = _WORD_TO_CATEGORY.get(word_a, word_a)
        cat_b = _WORD_TO_CATEGORY.get(word_b, word_b)
        if cat_a == cat_b and gap < 200:
            # Remove the second connector + trailing comma/space
            start = matches[i + 1].start()
            end = matches[i + 1].end()
            # Also remove trailing comma and space
            while end < len(content) and content[end] in ", ":
                end += 1
            removals.append((start, end))

    if not removals:
        return content

    # Apply removals from end to start to preserve indices
    result = content
    for start, end in reversed(removals):
        result = result[:start] + result[end:]
    return result


def _empty_result() -> dict:
    """Return empty peptide result."""
    return {
        "dangling_connectors": [],
        "cross_section_repeats": [],
        "weak_transitions": [],
        "connector_stutters": [],
        "stats": {
            "dangling_connectors": 0,
            "cross_section_repeats": 0,
            "weak_transitions": 0,
            "connector_stutters": 0,
        },
    }
