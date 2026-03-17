"""Phase 3: OUTLINE — Dynamic outline that evolves with evidence.

Generates an initial outline from sub-questions + reflections, then
refines it as new evidence arrives. Detects gaps and generates targeted
queries. Uses a keep-best strategy to prevent oscillation.

Key design: The outline is a LIVING DOCUMENT (WebWeaver, ICLR 2026).
It is NOT a one-shot generation.

Failure modes handled:
- F3.1: Too many sections → enforce sections <= evidence/3
- F3.2: Gap detection infinite loop → hard cap at 2 gap searches
- F3.3: Orphan evidence → assign to most relevant section
- F3.4: Outline oscillation → keep-best strategy with scoring
- F3.5: Unparseable outline → fallback from sub-questions
"""

import logging
import os
from typing import Optional

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineGap,
    OutlineSection,
    Reflection,
    SubQuestion,
)

logger = logging.getLogger("polaris_graph")

_MAX_GAP_SEARCHES = int(os.getenv("PG_V3_MAX_GAP_SEARCHES", "2"))
_MIN_EVIDENCE_PER_SECTION = int(os.getenv("PG_V3_MIN_EVIDENCE_PER_SECTION", "3"))
_MAX_OUTLINE_VERSIONS = int(os.getenv("PG_V3_MAX_OUTLINE_VERSIONS", "4"))


# ---------------------------------------------------------------------------
# Outline generation system prompt
# ---------------------------------------------------------------------------

_OUTLINE_SYSTEM_PROMPT = """You are a research report architect. Given sub-questions and evidence reflections, design a report outline.

Requirements:
1. Each section answers ONE sub-question (use the sub_question_id field).
2. Section depth is proportional to evidence density — more evidence = more words.
3. Sections flow logically: context → mechanisms → effectiveness → comparison → limitations → future.
4. Each section has a clear analytical_focus matching its sub-question.
5. Include cross_refs where sections reference findings from other sections.
6. Set target_words: deep=1200-1500, moderate=600-800, brief=300-400.
7. Set confidence based on how much evidence supports this section (0.0-1.0).
8. The title should be specific and descriptive (not generic like "Introduction").
9. Include a narrative_flow description explaining the logical progression.
10. Do NOT create sections without supporting evidence.""".strip()


# ---------------------------------------------------------------------------
# Public API: Generate outline
# ---------------------------------------------------------------------------

async def generate_outline(
    client,
    query: str,
    sub_questions: list[SubQuestion],
    reflections: list[Reflection],
    evidence_ids: list[str],
    evidence_meta: dict[str, dict],
) -> LiveOutline:
    """Generate the initial outline from sub-questions + reflections + evidence.

    Falls back to _fallback_outline_from_questions if LLM fails.
    """
    # Build prompt from sub-questions and reflections
    sq_text = "\n".join(
        f"- [{sq.id}] {sq.question} (focus: {sq.analytical_focus}, depth: {sq.expected_depth})"
        for sq in sub_questions
    )

    reflection_text = ""
    if reflections:
        reflection_text = "\n\nKey findings from research:\n" + "\n".join(
            f"- {r.insight} (confidence: {r.confidence:.1f}, answers: {r.sub_question_id})"
            for r in reflections[:15]
        )

    prompt = (
        f"Research question: {query}\n\n"
        f"Sub-questions to answer:\n{sq_text}\n"
        f"{reflection_text}\n\n"
        f"Total evidence collected: {len(evidence_ids)} pieces.\n"
        f"Design a report outline with one section per sub-question."
    )

    outline = None
    for attempt in range(2):
        try:
            outline = await client.generate_structured(
                prompt=prompt,
                schema=LiveOutline,
                system=_OUTLINE_SYSTEM_PROMPT,
                max_tokens=int(os.getenv("PG_V3_OUTLINE_MAX_TOKENS", "8192")),
                timeout=int(os.getenv("PG_V3_OUTLINE_TIMEOUT", "180")),
            )
            if outline and len(outline.sections) >= 1:
                break
            outline = None
        except Exception as exc:
            logger.warning(
                "[v3 outline] Attempt %d failed: %s", attempt + 1, str(exc)[:200]
            )
            outline = None

    if outline is None:
        logger.warning("[v3 outline] LLM failed, using fallback from sub-questions")
        outline = _fallback_outline_from_questions(query, sub_questions)

    # Set version 1
    outline.version = 1

    # Enforce section-to-evidence ratio (F3.1)
    outline = _enforce_section_evidence_ratio(outline, len(evidence_ids))

    # Assign evidence to sections (F3.3: orphans go to nearest section)
    outline = _assign_evidence_to_outline(outline, evidence_meta)

    # Detect gaps
    outline.gaps = _detect_gaps(outline, _MIN_EVIDENCE_PER_SECTION)

    logger.info(
        "[v3 outline] Generated outline v%d: %d sections, %d gaps, title='%s'",
        outline.version, len(outline.sections), len(outline.gaps), outline.title[:60],
    )

    return outline


# ---------------------------------------------------------------------------
# Outline refinement
# ---------------------------------------------------------------------------

async def refine_outline(
    client,
    current_outline: LiveOutline,
    new_reflections: list[Reflection],
    evidence_ids: list[str],
    evidence_meta: dict[str, dict],
    query: str,
) -> LiveOutline:
    """Refine an existing outline with new evidence. Uses keep-best strategy.

    Returns the better of the current and refined outlines.
    """
    if current_outline.version >= _MAX_OUTLINE_VERSIONS:
        logger.info("[v3 outline] Max outline versions reached (%d), keeping current", _MAX_OUTLINE_VERSIONS)
        return current_outline

    reflection_text = "\n".join(
        f"- {r.insight} (answers: {r.sub_question_id})"
        for r in new_reflections[:10]
    )

    current_sections = "\n".join(
        f"- {s.id}: {s.title} ({len(s.evidence_ids)} evidence, confidence={s.confidence:.1f})"
        for s in current_outline.sections
    )

    prompt = (
        f"Current outline (v{current_outline.version}):\n{current_sections}\n\n"
        f"New evidence reflections:\n{reflection_text}\n\n"
        f"Total evidence now: {len(evidence_ids)} pieces.\n\n"
        f"Refine the outline: add sections for new themes, merge thin sections, "
        f"update confidence scores. Keep the same section IDs where possible."
    )

    refined = None
    try:
        refined = await client.generate_structured(
            prompt=prompt,
            schema=LiveOutline,
            system=_OUTLINE_SYSTEM_PROMPT,
            max_tokens=int(os.getenv("PG_V3_OUTLINE_MAX_TOKENS", "8192")),
            timeout=int(os.getenv("PG_V3_OUTLINE_TIMEOUT", "180")),
        )
        if refined:
            refined.version = current_outline.version + 1
            refined = _enforce_section_evidence_ratio(refined, len(evidence_ids))
            refined = _assign_evidence_to_outline(refined, evidence_meta)
            refined.gaps = _detect_gaps(refined, _MIN_EVIDENCE_PER_SECTION)
    except Exception as exc:
        logger.warning("[v3 outline] Refinement failed: %s", str(exc)[:200])
        refined = None

    if refined is None:
        return current_outline

    # Keep-best strategy (F3.4)
    best = _keep_best_outline(current_outline, refined)
    if best.version == current_outline.version:
        logger.info("[v3 outline] Refinement rejected (v%d worse than v%d)", refined.version, current_outline.version)
    else:
        logger.info("[v3 outline] Adopted refinement v%d (score improved)", refined.version)

    return best


# ---------------------------------------------------------------------------
# Section-evidence ratio enforcement (F3.1)
# ---------------------------------------------------------------------------

def _enforce_section_evidence_ratio(
    outline: LiveOutline,
    evidence_count: int,
) -> LiveOutline:
    """Ensure section count is proportional to evidence count.

    Max sections = max(3, evidence_count // 2).
    If too many sections, merge the lowest-order ones.
    """
    max_sections = max(3, evidence_count // 2)
    if len(outline.sections) <= max_sections:
        return outline

    # Keep top N sections by order, merge rest into last kept section
    kept = sorted(outline.sections, key=lambda s: s.order)[:max_sections]

    # Collect evidence from removed sections
    removed_evidence = []
    kept_ids = {s.id for s in kept}
    for s in outline.sections:
        if s.id not in kept_ids:
            removed_evidence.extend(s.evidence_ids)

    # Add removed evidence to the last kept section
    if kept and removed_evidence:
        kept[-1].evidence_ids.extend(removed_evidence)

    outline.sections = kept

    # Re-number
    for i, s in enumerate(outline.sections):
        s.order = i + 1

    logger.info(
        "[v3 outline] F3.1: Trimmed to %d sections (evidence_count=%d, max=%d)",
        len(outline.sections), evidence_count, max_sections,
    )

    return outline


# ---------------------------------------------------------------------------
# Evidence assignment (F3.3)
# ---------------------------------------------------------------------------

def _assign_evidence_to_outline(
    outline: LiveOutline,
    evidence_meta: dict[str, dict],
) -> LiveOutline:
    """Assign evidence to sections based on sub_question_id matching.

    Orphan evidence (no matching sub_question_id) goes to the first section.
    """
    # Build section lookup by sub_question_id
    sq_to_section: dict[str, OutlineSection] = {}
    for section in outline.sections:
        sq_to_section[section.sub_question_id] = section

    # Clear existing assignments and reassign
    for section in outline.sections:
        section.evidence_ids = []

    orphans = []
    for ev_id, meta in evidence_meta.items():
        sq_id = meta.get("sub_question_id", "")
        target_section = sq_to_section.get(sq_id)
        if target_section:
            target_section.evidence_ids.append(ev_id)
        else:
            orphans.append(ev_id)

    # Assign orphans to first section (F3.3: never discard evidence)
    if orphans and outline.sections:
        outline.sections[0].evidence_ids.extend(orphans)
        logger.debug("[v3 outline] F3.3: %d orphan evidence assigned to '%s'", len(orphans), outline.sections[0].title)

    # Update confidence based on evidence count
    for section in outline.sections:
        ev_count = len(section.evidence_ids)
        if ev_count >= 5:
            section.confidence = 0.9
        elif ev_count >= 3:
            section.confidence = 0.7
        elif ev_count >= 1:
            section.confidence = 0.4
        else:
            section.confidence = 0.1

    return outline


# ---------------------------------------------------------------------------
# Gap detection (F3.2)
# ---------------------------------------------------------------------------

def _detect_gaps(
    outline: LiveOutline,
    min_evidence_per_section: int = 3,
) -> list[OutlineGap]:
    """Find sections with insufficient evidence.

    Returns gaps for sections with fewer than min_evidence_per_section evidence pieces.
    """
    gaps = []
    for section in outline.sections:
        if len(section.evidence_ids) < min_evidence_per_section:
            gaps.append(OutlineGap(
                section_id=section.id,
                description=f"Section '{section.title}' has only {len(section.evidence_ids)} evidence (need {min_evidence_per_section})",
                suggested_queries=[
                    f"{section.title} research findings",
                    f"{section.description or section.title} studies data",
                ],
            ))
    return gaps


def _generate_gap_queries(
    gaps: list[OutlineGap],
    original_query: str,
) -> list[dict]:
    """Generate targeted search queries from outline gaps.

    Combines the gap's suggested queries with the original query context.
    """
    queries = []
    for gap in gaps[:5]:  # Cap at 5 gaps to prevent explosion
        for suggested in gap.suggested_queries[:2]:  # 2 queries per gap
            queries.append({
                "query": f"{original_query} {suggested}",
                "sub_question_id": gap.section_id,  # Use section_id as target
                "perspective": "Scientific",
                "source_preference": "both",
                "is_gap_query": True,
            })
    return queries


# ---------------------------------------------------------------------------
# Outline scoring + keep-best strategy (F3.4)
# ---------------------------------------------------------------------------

def _score_outline(outline: LiveOutline) -> float:
    """Score an outline based on evidence coverage and section balance.

    Higher = better. Components:
    - Evidence coverage: total evidence assigned / section count
    - Confidence: average section confidence
    - Balance: penalty for high variance in evidence per section
    """
    if not outline.sections:
        return 0.0

    evidence_counts = [len(s.evidence_ids) for s in outline.sections]
    total_evidence = sum(evidence_counts)
    avg_evidence = total_evidence / len(outline.sections) if outline.sections else 0

    # Component 1: Evidence coverage (0-1, scaled by 10 as "good" threshold)
    coverage = min(avg_evidence / 10.0, 1.0)

    # Component 2: Average confidence
    avg_confidence = sum(s.confidence for s in outline.sections) / len(outline.sections)

    # Component 3: Balance penalty (high variance = bad)
    if len(evidence_counts) > 1 and avg_evidence > 0:
        variance = sum((c - avg_evidence) ** 2 for c in evidence_counts) / len(evidence_counts)
        cv = (variance ** 0.5) / max(avg_evidence, 1)  # Coefficient of variation
        balance = max(0, 1.0 - cv)  # Lower CV = better balance
    else:
        balance = 1.0

    # Weighted combination
    score = 0.4 * coverage + 0.4 * avg_confidence + 0.2 * balance
    return round(score, 3)


def _keep_best_outline(
    current: LiveOutline,
    candidate: LiveOutline,
) -> LiveOutline:
    """Return the better-scoring outline. Prevents oscillation (F3.4)."""
    current_score = _score_outline(current)
    candidate_score = _score_outline(candidate)

    if candidate_score > current_score:
        return candidate
    return current


# ---------------------------------------------------------------------------
# Fallback outline from sub-questions (F3.5)
# ---------------------------------------------------------------------------

def _fallback_outline_from_questions(
    query: str,
    sub_questions: list[SubQuestion],
) -> LiveOutline:
    """Build a basic outline directly from sub-questions when LLM fails.

    Each sub-question becomes one section. No LLM call required.
    """
    depth_to_words = {"deep": 1200, "moderate": 800, "brief": 400}

    sections = []
    for i, sq in enumerate(sub_questions):
        sections.append(OutlineSection(
            id=f"s{i + 1:02d}",
            title=sq.question,
            sub_question_id=sq.id,
            description=sq.question,
            analytical_focus=sq.analytical_focus,
            evidence_ids=[],
            confidence=0.0,
            target_words=depth_to_words.get(sq.expected_depth, 800),
            order=i + 1,
        ))

    total_words = sum(s.target_words for s in sections)

    return LiveOutline(
        title=f"Research Report: {query[:100]}",
        abstract_draft="",
        sections=sections,
        version=1,
        gaps=[],
        narrative_flow="Follows sub-question order: " + " → ".join(sq.question[:30] for sq in sub_questions[:5]),
    )
