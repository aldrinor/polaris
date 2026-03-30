"""
Section-by-section report writer for polaris graph.

Each section is a separate LLM call, keeping output under 800 words
to stay within the LLM's quality sweet spot.

No single mega-call. No CoT leakage. No post-processing.
"""

import asyncio
import logging
import os
import re
from typing import Optional

import numpy as np

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.schemas import (
    QuestionDecomposition,
    ReportOutline,
    SectionDraft,
    SectionOutlineItem,
)
from src.polaris_graph.state import (
    EvidencePiece,
    MAX_WORDS_PER_SECTION,
    PG_SECTION_CONTINUATION_MAX_TOKENS,
    PG_SECTION_EVIDENCE_TOP_K,
    PG_SECTION_WRITER_MAX_TOKENS,
    PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
    ReportSection,
)
from src.polaris_graph.tracing import get_tracer

logger = logging.getLogger(__name__)

SECTION_SYSTEM_PROMPT = """You are writing one section of a research report. You have {n_evidence} evidence pieces.

GENERATION RULE: Write ONLY from the evidence provided. For every factual claim, cite
the evidence ID immediately after: [CITE:evidence_id]. If you cannot cite a claim, do not write it.

STRUCTURE RULES:
1. If your evidence contains 4+ comparable data points (same measurement, different entities),
   present them as a MARKDOWN TABLE with citations in each cell.
2. If your evidence contains time-series data or trends, describe them quantitatively.
3. End each section with a **Key Findings** subsection: 3-5 cited bullet points summarizing
   the claims a reader should remember from this section.
4. Write analytically: comparisons, trade-offs, implications — not just facts.

CITATION RULES:
5. Every factual claim MUST have [CITE:evidence_id] immediately after.
6. Include exact numbers, dates, measurements from evidence. NEVER invent numbers.
7. STRONGLY prefer evidence marked [VERIFIED] over [UNVERIFIED].
8. Do NOT cite the same source more than 3 times per section. Spread across sources.
9. If you CANNOT cite a number, use qualitative language ("evidence suggests") instead.
10. Use EXACTLY the units from the source. Never convert or paraphrase units.

STYLE RULES:
11. Write in third person, academic register. No meta-commentary or preamble.
12. Use hedging words (may, might, could) ONLY for genuinely uncertain findings. Max 5 per section.
13. Use transition words SPARINGLY — max 1 per 200 words. NEVER start consecutive sentences with them.
14. Do NOT include chain-of-thought, reasoning, or planning text.
15. Do NOT repeat the section title in the content.
16. Do NOT repeat statistics that appeared in previous sections.
17. When citing regulatory thresholds, note when they were established.

LENGTH: Write proportional to evidence depth. {n_evidence} pieces ~ {suggested_words} words.
Do NOT pad beyond what evidence supports. Quality over quantity."""

OUTLINE_SYSTEM_PROMPT = """You are a research report architect. Design report structure FROM evidence, not templates.

Given evidence clusters with viability assessments, create a data-driven outline where:
- Each section EXISTS because evidence supports it (not because a template demands it)
- Section depth is PROPORTIONAL to evidence depth (more evidence = more detailed section)
- Clusters with contradictory evidence get balanced treatment sections
- Clusters assessed as BRIEF become bullet points in an "Additional Findings" section

Requirements:
1. Each section should have a clear, specific title (not generic like "Introduction").
2. Sections should flow logically from background to findings to implications.
3. Evidence will be assigned to sections automatically — focus on designing the best structure.
4. Each section's target_words should be proportional to its evidence: min(200 + n_evidence * 80, 2000).
5. Include a brief abstract (150-250 words) summarizing key findings.
6. For each section, state which cluster numbers it draws from.
7. No two sections should cover the same subtopic. Each section must have a unique analytical angle.
8. The abstract should NOT include specific numeric claims about source counts or evidence quantities.
9. FIX-MP18: The abstract MUST include: (a) scope, (b) exclusions, (c) evidence limitations.
10. If evidence contains comparable data points, note which sections should include TABLES.
11. Do NOT pad. A section with 3 evidence pieces warrants a concise paragraph, not 800 words.

Output format example:
{"title": "Comprehensive Analysis of X: Mechanisms, Impacts, and Regulatory Landscape", "abstract": "This report examines...", "sections": [{"section_id": "s01", "title": "Historical Context and Emergence of X", "description": "Traces the discovery and early research. Covers clusters 1, 2. Contains comparison data suitable for TABLE.", "evidence_ids": [], "target_words": 600, "order": 1}], "total_target_words": 6000}"""


# ---------------------------------------------------------------------------
# FIX-107I: Per-section evidence filtering via embedding similarity
# ---------------------------------------------------------------------------

def _filter_evidence_for_section(
    evidence: list[EvidencePiece],
    section_title: str,
    section_description: str,
    top_k: int = 100,
) -> list[EvidencePiece]:
    """FIX-107I: Filter evidence by embedding similarity to section topic.

    Before writing each section, compute cosine similarity between the
    section topic (title + description) and every evidence statement.
    Return the top_k most similar pieces so the LLM receives focused,
    relevant evidence instead of the full pool.

    Graceful fallback: if embedding fails for any reason, returns the
    full evidence list unchanged (no silent degradation of capability,
    just skips the optimization).

    Args:
        evidence: Full pool of evidence pieces for the section (already
            filtered to outline-assigned IDs).
        section_title: The section's title string.
        section_description: The section's description string.
        top_k: Maximum number of evidence pieces to return.

    Returns:
        Filtered list of at most ``top_k`` evidence pieces, sorted by
        descending similarity to the section topic.
    """
    # If evidence pool is already small enough, skip embedding entirely
    if len(evidence) <= top_k:
        logger.debug(
            "[polaris graph] FIX-107I: Section '%s' has %d evidence (<= top_k=%d), "
            "skipping filtering",
            section_title[:50],
            len(evidence),
            top_k,
        )
        return evidence

    try:
        from src.utils.embedding_service import embed_text, embed_texts
    except ImportError:
        logger.warning(
            "[polaris graph] FIX-107I: embedding_service unavailable, "
            "skipping per-section evidence filtering for '%s'",
            section_title[:50],
        )
        return evidence

    try:
        # Build query from section title + description
        query_text = f"{section_title}. {section_description}"
        query_vec = np.array(embed_text(query_text))

        # Batch-embed all evidence statements
        statements = [e.get("statement", "") for e in evidence]
        statement_vecs = np.array(embed_texts(statements))

        # Cosine similarity (embeddings are pre-normalized -> dot product)
        similarities = statement_vecs @ query_vec

        # Get indices of top_k most similar evidence pieces
        # np.argpartition is O(n) vs O(n log n) for argsort, but we need
        # sorted output for deterministic ordering, so use argsort on the
        # partitioned subset.
        if len(similarities) > top_k:
            top_indices = np.argsort(similarities)[-top_k:][::-1]
        else:
            top_indices = np.argsort(similarities)[::-1]

        filtered = [evidence[i] for i in top_indices]

        # Log the filtering result
        kept_ids = [e.get("evidence_id", "?") for e in filtered]
        min_sim = float(similarities[top_indices[-1]]) if len(top_indices) > 0 else 0.0
        max_sim = float(similarities[top_indices[0]]) if len(top_indices) > 0 else 0.0

        logger.info(
            "[polaris graph] FIX-107I: Section '%s' filtered %d -> %d evidence pieces "
            "(sim range %.3f-%.3f)",
            section_title[:50],
            len(evidence),
            len(filtered),
            min_sim,
            max_sim,
        )

        return filtered

    except Exception as exc:
        # Graceful fallback: return all evidence if embedding fails
        logger.warning(
            "[polaris graph] FIX-107I: Embedding failed for section '%s': %s — "
            "returning all %d evidence pieces unfiltered",
            section_title[:50],
            str(exc)[:200],
            len(evidence),
        )
        return evidence


def _build_comparison_tables(
    section_evidence: list[dict],
) -> str:
    """RC-6: Build pre-formatted markdown tables from comparable_metrics.

    Groups metrics by metric_name across evidence pieces. For groups with
    3+ data points, generates markdown tables with [CITE:evidence_id] in
    the Source column.

    Returns formatted table block string, or empty string if no tables.
    """
    from collections import defaultdict

    # Collect all comparable_metrics from evidence cards
    metric_groups: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for ev in section_evidence:
        metrics = ev.get("comparable_metrics") or []
        ev_id = ev.get("evidence_id", "?")
        for m in metrics:
            if isinstance(m, dict) and m.get("metric_name") and m.get("value") is not None:
                metric_groups[m["metric_name"]].append((m, ev_id))

    if not metric_groups:
        return ""

    tables = []
    for metric_name, entries in sorted(metric_groups.items()):
        if len(entries) < 3:
            continue

        # Build markdown table
        table_lines = [
            f"\n**Comparison: {metric_name.replace('_', ' ').title()}**\n",
            "| Source | Entity | Value | Unit | Condition |",
            "|--------|--------|-------|------|-----------|",
        ]
        for m, ev_id in entries[:15]:  # Cap at 15 rows
            entity = m.get("entity", "")
            value = m.get("value", "")
            unit = m.get("unit", "")
            condition = m.get("condition", "")
            table_lines.append(f"| [CITE:{ev_id}] | {entity} | {value} | {unit} | {condition} |")

        tables.append("\n".join(table_lines))

    if not tables:
        return ""

    return "\n\n".join(tables)


def _format_conflicts_for_prompt(
    evidence_conflicts: list[dict],
    section_evidence_ids: list[str],
) -> str:
    """FIX-ENV4: Format evidence conflicts relevant to a section for inclusion in prompts.

    Filters the global conflict list to only those conflicts where at least
    one evidence piece is assigned to this section. Returns a formatted
    string block for injection into LLM prompts.

    Args:
        evidence_conflicts: Full list of detected conflict dicts.
        section_evidence_ids: Evidence IDs assigned to this section.

    Returns:
        Formatted conflict summary string, or empty string if no relevant conflicts.
    """
    if not evidence_conflicts or not section_evidence_ids:
        return ""

    section_ids = set(section_evidence_ids)
    relevant = []
    for conflict in evidence_conflicts:
        a_id = conflict.get("evidence_a_id", "")
        b_id = conflict.get("evidence_b_id", "")
        if a_id in section_ids or b_id in section_ids:
            relevant.append(conflict)

    if not relevant:
        return ""

    lines = [
        f"\nCONFLICTING EVIDENCE ({len(relevant)} conflicts detected in this section's evidence):",
        "You MUST dedicate at least one full paragraph to each conflict listed below.",
        "Structure: [Position A with citation] vs [Position B with citation].",
        "Then explain which position has stronger evidence and why.",
        "Do NOT merely mention the conflict — ANALYZE it with specific reasoning.",
    ]
    for i, conflict in enumerate(relevant[:5], 1):
        lines.append(
            f"  Conflict {i}: [{conflict.get('evidence_a_id', '?')}] vs [{conflict.get('evidence_b_id', '?')}]"
        )
        lines.append(
            f"    A: {conflict.get('statement_a', '')[:150]}"
        )
        lines.append(
            f"    B: {conflict.get('statement_b', '')[:150]}"
        )
        signals = conflict.get("contradiction_signals", [])
        if signals:
            lines.append(
                f"    Signals: {', '.join(signals[:3])}"
            )

    return "\n".join(lines)


def _summarize_evidence_for_planning(
    clusters: list[dict],
    evidence: list[EvidencePiece],
) -> str:
    """Build a compact evidence summary for question decomposition (RC-3).

    Returns a short text describing what themes and data points are available
    so the decomposition LLM can generate answerable sub-questions.
    """
    lines = [f"Total evidence pieces: {len(evidence)}"]
    gold = sum(1 for e in evidence if e.get("quality_tier") == "GOLD")
    silver = sum(1 for e in evidence if e.get("quality_tier") == "SILVER")
    lines.append(f"Quality: {gold} GOLD, {silver} SILVER, {len(evidence) - gold - silver} BRONZE")

    perspectives: dict[str, int] = {}
    for e in evidence:
        p = e.get("perspective", "Unknown")
        perspectives[p] = perspectives.get(p, 0) + 1
    if perspectives:
        lines.append("Perspectives: " + ", ".join(
            f"{k} ({v})" for k, v in sorted(perspectives.items(), key=lambda x: -x[1])[:6]
        ))

    for i, cl in enumerate(clusters[:12], 1):
        theme = cl.get("theme", cl.get("label", f"Cluster {i}"))
        count = len(cl.get("evidence_ids", []))
        lines.append(f"  Cluster {i}: {theme} ({count} evidence)")

    return "\n".join(lines)


_QUESTION_DECOMPOSITION_SYSTEM = """You are a research strategist. Given a research topic and a summary of evidence collected, decompose the topic into 6-10 sub-questions that a knowledgeable reader would want answered.

Requirements:
- Questions should flow logically: context → mechanisms → effectiveness → comparison → limitations → future
- Each question must be answerable from the evidence (don't ask about things not in the evidence)
- Assign each question an analytical_focus: aggregate, compare, explain, tabulate, or challenge
- Assign depth: 'deep' for the core questions (2-3), 'moderate' for supporting (3-4), 'brief' for peripheral (1-2)
- The set of questions should cover: what, how, how well, compared to what, and what's missing
- Generate a narrative_flow description explaining how the questions build on each other""".strip()


async def _decompose_into_questions(
    client: OpenRouterClient,
    query: str,
    evidence_summary: str,
    storm_perspectives: list[str],
) -> Optional[QuestionDecomposition]:
    """RC-3: Decompose research query into 6-10 sub-questions a reader would ask.

    Returns None on failure so caller can fall back to cluster-based planning.
    """
    perspective_str = ", ".join(storm_perspectives[:8]) if storm_perspectives else "Scientific, Practical"
    prompt = (
        f"Research topic: {query}\n\n"
        f"Evidence available:\n{evidence_summary}\n\n"
        f"Perspectives represented: {perspective_str}\n\n"
        "Decompose this topic into 6-10 sub-questions that a knowledgeable reader "
        "would want answered. Each question should map to a report section."
    )
    try:
        result = await client.generate_structured(
            prompt=prompt,
            schema=QuestionDecomposition,
            system=_QUESTION_DECOMPOSITION_SYSTEM,
            max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
            timeout=300,
        )
        if result and result.questions:
            logger.info(
                "[polaris graph] RC-3: Decomposed query into %d sub-questions",
                len(result.questions),
            )
            return result
        logger.warning("[polaris graph] RC-3: Decomposition returned 0 questions, falling back")
        return None
    except Exception as exc:
        logger.error(
            "[polaris graph] RC-3: Question decomposition failed: %s — falling back",
            str(exc)[:200],
        )
        return None


async def plan_report(
    client: OpenRouterClient,
    query: str,
    evidence: list[EvidencePiece],
    clusters: list[dict],
    quality_metrics: Optional[dict] = None,
    evidence_conflicts: Optional[list[dict]] = None,
    ltm_prior_knowledge: str = "",
) -> ReportOutline:
    """
    Plan the report structure using reasoning mode.

    Returns a detailed outline with evidence assigned to sections.

    FIX-QM27: Uses cluster-based outline prompt instead of listing all evidence.
    With 600+ evidence pieces, the original prompt overwhelmed the model (9K+ input
    tokens + 16K reasoning tokens = no room for JSON output). Now uses clusters
    (which already have evidence assignments) as the primary structure, with a
    compact evidence reference table.

    FIX-ENV4: Accepts evidence_conflicts to inform outline structure. When
    conflicting evidence is detected, the outline prompt instructs the planner
    to dedicate sections or subsections to addressing these disagreements.
    """
    # RC-3: Question-driven planning (when enabled, build outline from sub-questions)
    if os.getenv("PG_V3_QUESTION_PLANNING", "0") == "1":
        from src.polaris_graph.state import STORM_PERSPECTIVES
        evidence_summary = _summarize_evidence_for_planning(clusters, evidence)
        decomposition = await _decompose_into_questions(
            client, query, evidence_summary,
            list(STORM_PERSPECTIVES) if hasattr(STORM_PERSPECTIVES, '__iter__') else [],
        )
        if decomposition and decomposition.questions:
            depth_to_words = {"deep": 1500, "moderate": 800, "brief": 400}
            sections = []
            for i, q in enumerate(decomposition.questions):
                sections.append(SectionOutlineItem(
                    section_id=f"s{i + 1:02d}",
                    title=q.question,
                    description=q.question,
                    analytical_focus=q.analytical_focus,
                    target_words=depth_to_words.get(q.expected_depth, 800),
                    evidence_ids=[],  # Filled by _assign_evidence_to_sections
                    order=i + 1,
                ))
            total_words = sum(s.target_words for s in sections)
            outline = ReportOutline(
                title=f"Research Report: {query}",
                sections=sections,
                total_target_words=total_words,
            )
            # Use existing evidence assignment machinery
            outline = _assign_evidence_to_sections(outline, clusters, evidence)
            outline = _validate_outline_evidence(outline)
            # Trim empty sections (keep at least 3)
            if len(outline.sections) > 3:
                non_empty = [s for s in outline.sections if s.evidence_ids]
                if non_empty and len(non_empty) >= 3:
                    outline.sections = non_empty
                    for idx, s in enumerate(outline.sections):
                        s.order = idx + 1
                    outline.total_target_words = sum(s.target_words for s in outline.sections)
            logger.info(
                "[polaris graph] RC-3: Question-driven outline: %d sections, %d words",
                len(outline.sections), outline.total_target_words,
            )
            return outline
        logger.warning("[polaris graph] RC-3: Question decomposition failed, falling back to cluster planning")

    cluster_detail = _format_cluster_summary(clusters)

    # FIX-303C: Build perspective list for diversity gate
    perspective_set: set[str] = set()
    for e in evidence:
        p = e.get("perspective")
        if p:
            perspective_set.add(p)
    perspective_list = ", ".join(sorted(perspective_set)) if perspective_set else "Scientific"

    gold_count = sum(1 for e in evidence if e.get('quality_tier') == 'GOLD')
    silver_count = sum(1 for e in evidence if e.get('quality_tier') == 'SILVER')

    # FIX-ENV4: Build conflict awareness block for outline prompt
    conflict_block = ""
    if evidence_conflicts:
        conflict_lines = []
        for i, conflict in enumerate(evidence_conflicts[:10], 1):
            conflict_lines.append(
                f"  {i}. [{conflict.get('evidence_a_id', '?')}] vs "
                f"[{conflict.get('evidence_b_id', '?')}] "
                f"(overlap={conflict.get('topic_overlap', 0):.0%}, "
                f"signals: {', '.join(conflict.get('contradiction_signals', [])[:3])})"
            )
        conflict_block = (
            f"\n\nEVIDENCE CONFLICTS DETECTED ({len(evidence_conflicts)} pairs):\n"
            + "\n".join(conflict_lines)
            + "\n\nIMPORTANT: When designing the outline, ensure that sections covering "
            "conflicting evidence explicitly address these disagreements. Dedicate "
            "paragraphs or subsections to comparing conflicting findings rather than "
            "presenting only one side."
        )

    # M-15: Build LTM prior knowledge block
    ltm_block = ""
    if ltm_prior_knowledge:
        ltm_block = (
            f"\n\nPRIOR KNOWLEDGE (from previous research runs):\n"
            f"{ltm_prior_knowledge}\n\n"
            "Consider this prior knowledge when designing the outline. "
            "It may provide additional context or highlight aspects to cover."
        )

    # FIX-056: Cap sections based on evidence count to prevent empty sections.
    # BUG-091: 12-section outline from 5 evidence pieces → 7 sections with 0 evidence.
    # FIX-057: Tighten cap for critically low evidence (<10) — 1 section per piece.
    # T052 root cause: 13-section outline from 3 evidence → 10 sections with 0 evidence.
    max_sections_cap = int(os.getenv("PG_MAX_OUTLINE_SECTIONS", "15"))
    if len(evidence) < 10:
        # Critical evidence starvation: 1 section per evidence piece, minimum 3
        target_sections = max(3, len(evidence))
    else:
        evidence_based_cap = min(max_sections_cap, len(evidence) + 2)
        target_sections = max(3, evidence_based_cap)
    target_words = int(os.getenv('PG_TARGET_TOTAL_WORDS', '8000'))

    prompt = f"""Research question: {query}

Evidence collected: {len(evidence)} pieces (GOLD={gold_count}, SILVER={silver_count})
Perspectives: {perspective_list}

{cluster_detail}
{conflict_block}
{ltm_block}

Design a data-driven report outline where section depth matches evidence depth:
1. Covers ALL aspects of the research question
2. Has {target_sections} sections. Each section's target_words = min(200 + cluster_evidence_count * 80, 2000).
3. Flows logically from background to findings to implications
4. Each section should correspond to one or more clusters — state which cluster numbers it covers
5. Return evidence_ids as empty lists [] — evidence assignment is automated
6. Ensure perspective diversity: sections should draw from multiple perspectives
7. The abstract MUST NOT mention specific counts of sources or evidence
8. If a cluster has fewer than 3 evidence pieces, merge it into an "Additional Findings" section
9. Note which sections should include TABLES (clusters with 4+ comparable data points)"""

    # FIX-QM12: Use PG_SYNTHESIS_STRUCTURED_MAX_TOKENS (16384) instead of
    # PG_SECTION_WRITER_MAX_TOKENS (8192). Reasoning consumes ~6000 tokens,
    # leaving only ~2000 for JSON at 8192, which truncates ReportOutline.
    outline = None
    try:
        outline = await client.generate_structured(
            prompt=prompt,
            schema=ReportOutline,
            system=OUTLINE_SYSTEM_PROMPT,
            max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
            timeout=600,
        )

        # FIX-311: Retry once if outline has 0 sections (Kimi garbage output)
        if len(outline.sections) == 0:
            logger.warning(
                "[polaris graph] FIX-311: Outline returned 0 sections, retrying..."
            )
            outline = await client.generate_structured(
                prompt=prompt,
                schema=ReportOutline,
                system=OUTLINE_SYSTEM_PROMPT,
                max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
                timeout=600,
            )
    except Exception as outline_exc:
        logger.error(
            "[polaris graph] FIX-OUTLINE: Outline generation failed: %s "
            "— using fallback outline",
            str(outline_exc)[:200],
        )
        outline = None

    # FIX-311: Fallback — build outline from clusters if LLM fails or returns 0
    if outline is None or len(outline.sections) == 0:
        logger.warning(
            "[polaris graph] FIX-311: Using fallback outline from %d clusters",
            len(clusters),
        )
        outline = _fallback_outline(query, clusters, evidence)

    # FIX-OUTLINE: Algorithmically assign evidence from clusters to sections
    outline = _assign_evidence_to_sections(outline, clusters, evidence)

    # FIX-A4: Validate and deduplicate evidence assignments across sections
    outline = _validate_outline_evidence(outline)

    # FIX-056: Trim sections with 0 evidence (BUG-091).
    # LLM may generate more sections than evidence can support.
    # Keep at least 3 sections (intro/body/conclusion structure).
    pre_trim = len(outline.sections)
    if pre_trim > 3:
        non_empty = [s for s in outline.sections if s.evidence_ids]
        empty = [s for s in outline.sections if not s.evidence_ids]
        if non_empty and empty:
            outline.sections = non_empty
            # Re-number
            for i, s in enumerate(outline.sections):
                s.order = i + 1
            outline.total_target_words = len(outline.sections) * 800
            logger.info(
                "[polaris graph] FIX-056: Trimmed %d empty sections "
                "(%d → %d sections with evidence)",
                len(empty), pre_trim, len(outline.sections),
            )

    logger.info(
        "[polaris graph] Report outline: %d sections, %d target words, '%s'",
        len(outline.sections),
        outline.total_target_words,
        outline.title,
    )

    return outline


def _assign_evidence_to_sections(
    outline: ReportOutline,
    clusters: list[dict],
    evidence: list[EvidencePiece],
) -> ReportOutline:
    """FIX-OUTLINE: Algorithmically assign evidence from clusters to outline sections.

    Uses word overlap (Jaccard similarity) between section title+description
    and cluster theme+description to find the best cluster->section mapping.
    Each cluster's evidence_ids are assigned to its best-matching section.

    This replaces LLM-based evidence assignment, which was the root cause of
    outline timeouts (forcing the LLM to assign 900+ evidence IDs to sections
    within a structured JSON schema call).
    """
    if not clusters or not outline.sections:
        return outline

    sorted_sections = sorted(outline.sections, key=lambda s: s.order)

    def _word_set(text: str) -> set[str]:
        """Extract meaningful words (>2 chars) as a lowercase set."""
        return {w.lower() for w in text.split() if len(w) > 2}

    # Build cluster word sets from theme + description
    cluster_word_sets = [
        _word_set(f"{c.get('theme', '')} {c.get('description', '')}")
        for c in clusters
    ]

    # Build section word sets from title + description
    section_word_sets = [
        _word_set(f"{s.title} {s.description}")
        for s in sorted_sections
    ]

    # Assign each cluster to its best-matching section
    section_evidence: dict[int, list[str]] = {
        i: [] for i in range(len(sorted_sections))
    }
    assigned_evidence_ids: set[str] = set()

    for ci, cluster in enumerate(clusters):
        c_words = cluster_word_sets[ci]
        best_section_idx = 0
        best_similarity = -1.0

        for si, s_words in enumerate(section_word_sets):
            if not c_words or not s_words:
                continue
            intersection = len(c_words & s_words)
            union = len(c_words | s_words)
            similarity = intersection / union if union > 0 else 0.0
            if similarity > best_similarity:
                best_similarity = similarity
                best_section_idx = si

        ev_ids = cluster.get("evidence_ids", [])
        section_evidence[best_section_idx].extend(ev_ids)
        assigned_evidence_ids.update(ev_ids)

    # FIX-MP6: Assign unassigned evidence to section with lowest count + any overlap.
    # This distributes evidence more evenly (prevents piling on large sections).
    all_evidence_ids = {
        e.get("evidence_id", "") for e in evidence if e.get("evidence_id")
    }
    unassigned = all_evidence_ids - assigned_evidence_ids

    if unassigned:
        ev_map = {e.get("evidence_id", ""): e for e in evidence}
        for eid in unassigned:
            ev = ev_map.get(eid)
            if not ev:
                continue
            stmt_words = _word_set(ev.get("statement", ""))
            if not stmt_words:
                # No words to match — assign to section with fewest evidence
                min_idx = min(section_evidence, key=lambda k: len(section_evidence[k]))
                section_evidence[min_idx].append(eid)
                continue

            # Find all sections with ANY word overlap, pick the one with fewest evidence
            candidates: list[tuple[int, int]] = []  # (section_idx, count)
            for si, s_words in enumerate(section_word_sets):
                if s_words and (stmt_words & s_words):
                    candidates.append((si, len(section_evidence[si])))

            if candidates:
                # Pick section with lowest evidence count (ties: first match)
                best_idx = min(candidates, key=lambda t: t[1])[0]
            else:
                # No overlap at all — fall back to section with fewest evidence
                best_idx = min(section_evidence, key=lambda k: len(section_evidence[k]))

            section_evidence[best_idx].append(eid)

        logger.info(
            "[polaris graph] FIX-MP6: Redistributed %d unassigned evidence pieces "
            "to lowest-count sections with word overlap",
            len(unassigned),
        )

    # FIX-CITE-DIV-1: Cap any single source at max_source_pct of section evidence
    max_source_pct = float(os.getenv("PG_MAX_SOURCE_PCT_PER_SECTION", "0.33"))
    ev_map_for_div = {e.get("evidence_id", ""): e for e in evidence}
    diversity_trimmed = 0
    for si in section_evidence:
        ids = section_evidence[si]
        if len(ids) < 6:
            continue  # Too few to worry about diversity
        # Count evidence per source URL
        source_counts: dict[str, list[str]] = {}
        for eid in ids:
            ev = ev_map_for_div.get(eid, {})
            src_url = ev.get("source_url", "unknown")
            source_counts.setdefault(src_url, []).append(eid)
        max_per_source = max(3, int(len(ids) * max_source_pct))
        trimmed_ids = []
        for src_url, src_ids in source_counts.items():
            if len(src_ids) > max_per_source:
                # Keep highest-relevance evidence from this source
                src_ids_sorted = sorted(
                    src_ids,
                    key=lambda eid: ev_map_for_div.get(eid, {}).get("relevance_score", 0),
                    reverse=True,
                )
                trimmed_ids.extend(src_ids_sorted[:max_per_source])
                diversity_trimmed += len(src_ids) - max_per_source
            else:
                trimmed_ids.extend(src_ids)
        section_evidence[si] = trimmed_ids

    if diversity_trimmed > 0:
        logger.info(
            "[polaris graph] FIX-CITE-DIV-1: Trimmed %d over-represented "
            "source evidence across sections (max %.0f%% per source)",
            diversity_trimmed, max_source_pct * 100,
        )

    # Populate outline sections with assigned evidence
    for si, section in enumerate(sorted_sections):
        section.evidence_ids = section_evidence.get(si, [])

    total_assigned = sum(len(ids) for ids in section_evidence.values())
    logger.info(
        "[polaris graph] FIX-OUTLINE: Algorithmically assigned %d evidence pieces "
        "to %d sections from %d clusters",
        total_assigned,
        len(outline.sections),
        len(clusters),
    )

    return outline


def _validate_outline_evidence(outline: ReportOutline) -> ReportOutline:
    """Deduplicate evidence assignments and ensure minimum per section.

    1. Checks for evidence_ids appearing in more than one section.
       For any duplicates, keeps the evidence in the section where it
       appears first (by section order) and removes from later sections.
    2. FIX-QG1: Ensures every section has >= 3 evidence_ids by
       redistributing from over-assigned sections.
    """
    min_evidence_per_section = int(
        os.getenv("PG_MIN_EVIDENCE_PER_SECTION", "3")
    )

    seen: set[str] = set()
    dedup_count = 0

    sorted_sections = sorted(outline.sections, key=lambda s: s.order)
    for section in sorted_sections:
        unique_ids = []
        for eid in section.evidence_ids:
            if eid in seen:
                dedup_count += 1
            else:
                seen.add(eid)
                unique_ids.append(eid)
        section.evidence_ids = unique_ids

    if dedup_count > 0:
        logger.warning(
            "[polaris graph] FIX-C1: Deduplicated %d cross-section evidence assignments",
            dedup_count,
        )

    # FIX-QG1+STARVATION: Redistribute evidence to starved sections.
    # Old: donor threshold >10 evidence. With 53 evidence / 8 sections = 6.6 avg,
    # NO section had >10 → 3 sections got 0 evidence → empty sections.
    # New: adaptive donor threshold = max(avg+2, min_evidence_per_section+1).
    # Donors keep at least min_evidence_per_section, donate the rest.
    starved = [s for s in sorted_sections if len(s.evidence_ids) < min_evidence_per_section]
    if starved:
        total_ev = sum(len(s.evidence_ids) for s in sorted_sections)
        avg_ev = total_ev / max(len(sorted_sections), 1)
        donor_threshold = max(int(avg_ev) + 2, min_evidence_per_section + 1)
        keep_minimum = min_evidence_per_section  # Donors keep at least this many

        donor_pool: list[str] = []
        for section in sorted_sections:
            if len(section.evidence_ids) > donor_threshold:
                excess = section.evidence_ids[keep_minimum:]
                section.evidence_ids = section.evidence_ids[:keep_minimum]
                donor_pool.extend(excess)

        # Distribute from donor pool to starved sections
        redistributed = 0
        for section in starved:
            needed = min_evidence_per_section - len(section.evidence_ids)
            while needed > 0 and donor_pool:
                section.evidence_ids.append(donor_pool.pop(0))
                needed -= 1
                redistributed += 1

        if redistributed > 0:
            logger.info(
                "[polaris graph] FIX-QG1: Redistributed %d evidence_ids to "
                "%d starved sections (min=%d per section)",
                redistributed,
                len(starved),
                min_evidence_per_section,
            )

        # Log remaining starved sections (couldn't fix)
        still_starved = [
            s for s in sorted_sections
            if len(s.evidence_ids) < min_evidence_per_section
        ]
        if still_starved:
            logger.warning(
                "[polaris graph] FIX-QG1: %d sections still below %d evidence_ids "
                "after redistribution: %s",
                len(still_starved),
                min_evidence_per_section,
                [s.title[:40] for s in still_starved],
            )

    return outline


def _fallback_outline(
    query: str,
    clusters: list[dict],
    evidence: list[EvidencePiece],
) -> ReportOutline:
    """Build a default outline from evidence clusters when LLM fails."""
    sections = []
    for i, cluster in enumerate(clusters):
        # FIX-T5: Use "theme" key (from map-reduce clusters), fall back to "label"
        cluster_label = cluster.get("theme", cluster.get("label", f"Theme {i + 1}"))
        # FIX-T5: Use evidence_ids directly from cluster if available
        evidence_ids = cluster.get("evidence_ids", [])
        # Fallback: match by cluster_id in evidence
        if not evidence_ids:
            evidence_ids = [
                e.get("evidence_id", "") for e in evidence
                if e.get("cluster_id") == cluster.get("cluster_id")
            ]
        # Also try matching by string cluster_id
        if not evidence_ids:
            evidence_ids = [
                e.get("evidence_id", "") for e in evidence
                if str(e.get("cluster_id", "")) == str(cluster.get("cluster_id", ""))
            ]
        # If still empty, assign first N/clusters evidence pieces
        if not evidence_ids and evidence:
            chunk_size = max(1, len(evidence) // max(len(clusters), 1))
            start = i * chunk_size
            evidence_ids = [
                e.get("evidence_id", "")
                for e in evidence[start:start + chunk_size]
            ]
        # FIX-MP9: Build descriptive title — detect generic single-word themes
        # and construct title from top evidence keywords instead.
        _GENERIC_THEMES = {
            "statistic", "finding", "citation", "descriptive", "overview",
            "analysis", "discussion", "conclusion", "results", "methodology",
            "reference", "data", "evidence", "information", "summary",
            "theme", "topic", "section", "category", "cluster",
        }
        desc = cluster.get("description", "")
        # FIX-CITE-3/R2: Strip "Evidence categorized as X" from description —
        # this is the category fallback pattern and produces garbage titles.
        desc = re.sub(r"^Evidence categorized as \w+\s*", "", desc).strip()
        theme_words = cluster_label.strip().split()
        is_generic = (
            len(theme_words) == 1
            and theme_words[0].lower().rstrip("s") in _GENERIC_THEMES
        )

        if is_generic and evidence_ids:
            # Extract top keywords from evidence statements for this cluster.
            # FIX-CITE-3/R2: Use keywords as the FULL title (no desc suffix).
            from collections import Counter
            _stopwords = {
                "the", "and", "for", "that", "this", "with", "from", "are",
                "was", "were", "has", "have", "been", "its", "can", "may",
                "not", "but", "also", "more", "than", "into", "such", "each",
                "will", "about", "which", "their", "other", "these", "some",
            }
            word_counts: Counter = Counter()
            ev_map_local = {e.get("evidence_id", ""): e for e in evidence}
            for eid in evidence_ids:
                ev_item = ev_map_local.get(eid)
                if ev_item:
                    for w in ev_item.get("statement", "").split():
                        wl = w.lower().strip(".,;:()[]\"'")
                        if len(wl) > 3 and wl not in _stopwords:
                            word_counts[wl] += 1
            top_keywords = [w for w, _ in word_counts.most_common(5)]
            if len(top_keywords) >= 3:
                fallback_title = " ".join(top_keywords[:3]).title()
                # FIX-CITE-3/R2: Only append desc if it adds value (non-empty after stripping)
                if desc and len(desc) > 10:
                    fallback_title = f"{fallback_title}: {desc[:50].rstrip('.,; ')}"
            elif desc and len(desc) > 10:
                fallback_title = desc[:80].rstrip(".,; ")
            else:
                fallback_title = f"Analysis of {cluster_label}"
        elif desc and len(desc) > 10 and len(theme_words) <= 2:
            fallback_title = f"{cluster_label}: {desc[:60].rstrip('.,; ')}"
        else:
            fallback_title = cluster_label[:100]
        sections.append(SectionOutlineItem(
            section_id=f"s{i + 1:02d}",
            title=fallback_title,
            description=cluster.get("description", f"Analysis of {cluster_label}"),
            evidence_ids=[eid for eid in evidence_ids if eid],
            target_words=800,
            order=i + 1,
        ))

    title = f"Research Analysis: {query[:80]}"
    abstract = (
        f"This comprehensive research report directly addresses the question: {query[:200]}. "
        f"Drawing on {len(evidence)} evidence pieces from {len(clusters)} thematic areas, "
        f"this analysis examines the key findings, current evidence, and implications "
        f"relevant to this research question."
    )
    return ReportOutline(
        title=title,
        abstract=abstract,
        sections=sections,
        total_target_words=len(sections) * 800,
    )


async def write_section(
    client: OpenRouterClient,
    section: SectionOutlineItem,
    evidence: list[EvidencePiece],
    query: str,
    report_title: str,
    previous_section_summary: str = "",
    full_outline_context: str = "",
    section_position: str = "",
    evidence_conflicts: Optional[list[dict]] = None,
    previously_covered_claims: Optional[list[str]] = None,
    all_evidence: Optional[list[EvidencePiece]] = None,
) -> SectionDraft:
    """
    Write a single report section.

    Uses generate() mode — reasoning OFF, clean prose only.
    Keeps output under 800 words for Kimi quality.

    FIX-107I: Evidence is now pre-filtered by embedding similarity to the
    section topic before being passed to the LLM. The filtering happens in
    write_all_sections() which calls _filter_evidence_for_section() and
    passes only the relevant subset here.

    FIX-ENV4: When evidence_conflicts relevant to this section are detected,
    the prompt includes explicit instructions to address contradictions.
    """
    # FIX-C6+STARVATION: When no evidence assigned, pull from full pool
    # using embedding similarity to section title. Better than returning
    # an empty placeholder that destroys the section.
    if not section.evidence_ids:
        try:
            from src.utils.embedding_service import embed_text, embed_texts
            import numpy as np
            _rescue_pool = all_evidence or evidence
            _all_ev_ids = [e.get("evidence_id", "") for e in _rescue_pool]
            _all_ev_texts = [
                f"{e.get('statement', '')}. {e.get('direct_quote', '')}"
                for e in _rescue_pool
            ]
            _title_vec = np.array(embed_text(section.title))
            _ev_vecs = np.array(embed_texts(_all_ev_texts))
            _sims = _ev_vecs @ _title_vec
            _rescue_threshold = float(os.getenv("PG_EVIDENCE_RESCUE_SIM_THRESHOLD", "0.15"))
            _top_indices = np.argsort(_sims)[-5:][::-1]  # Top 5 by similarity
            _rescued_ids = [_all_ev_ids[i] for i in _top_indices if _sims[i] > _rescue_threshold]
            if _rescued_ids:
                section.evidence_ids = _rescued_ids
                logger.info(
                    "[polaris graph] FIX-C6+STARVATION: Rescued section '%s' "
                    "with %d evidence from global pool (embedding similarity)",
                    section.title[:40], len(_rescued_ids),
                )
        except Exception as _rescue_exc:
            # Keyword fallback when embedding fails (Errno 22, model not loaded)
            _rescue_pool = all_evidence or evidence
            _title_words = set(re.findall(r"\w{4,}", section.title.lower()))
            if _title_words and _rescue_pool:
                _keyword_scored = []
                for _ev in _rescue_pool:
                    _ev_text = (
                        _ev.get("statement", "") + " " + _ev.get("source_title", "")
                    ).lower()
                    _ev_words = set(re.findall(r"\w{4,}", _ev_text))
                    _overlap = len(_title_words & _ev_words)
                    _keyword_scored.append((_overlap, _ev.get("evidence_id", "")))
                _keyword_scored.sort(reverse=True)
                _rescued_ids = [eid for sc, eid in _keyword_scored[:5] if sc > 0]
                if _rescued_ids:
                    section.evidence_ids = _rescued_ids
                    logger.info(
                        "[polaris graph] FIX-C6+STARVATION: Keyword fallback rescued "
                        "section '%s' with %d evidence",
                        section.title[:40], len(_rescued_ids),
                    )
            logger.debug(
                "[polaris graph] FIX-C6+STARVATION: Embedding rescue failed for '%s': %s",
                section.title[:30], str(_rescue_exc)[:100],
            )

    if not section.evidence_ids:
        logger.warning(
            "[polaris graph] FIX-C6: Section '%s' has no evidence_ids — "
            "returning placeholder draft to prevent hallucination",
            section.title,
        )
        return SectionDraft(
            section_id=section.section_id,
            title=section.title,
            content=f"[Section '{section.title}' omitted: no evidence assigned.]",
            claims_made=[],
            evidence_ids=[],
        )

    # Filter evidence assigned to this section
    section_evidence = [
        e for e in evidence if e.get("evidence_id") in section.evidence_ids
    ]

    # FIX-107I: Apply per-section embedding-based evidence filtering.
    # TIER-3 Stage 3: Use wider candidate pool when token budget is enabled.
    _token_budget_enabled = int(os.getenv("PG_SECTION_TOKEN_BUDGET", "6000")) > 0
    _candidate_pool = int(os.getenv("PG_EVIDENCE_CANDIDATE_POOL", "100")) if _token_budget_enabled else PG_SECTION_EVIDENCE_TOP_K
    section_evidence = _filter_evidence_for_section(
        evidence=section_evidence,
        section_title=section.title,
        section_description=section.description,
        top_k=_candidate_pool,
    )

    # Emission 20: Trace section evidence filtering
    tracer = get_tracer()
    if tracer:
        tracer.evidence("synthesize", "section_evidence_filtered", len(section_evidence),
            section_id=section.section_id if hasattr(section, 'section_id') else "",
            title=getattr(section, 'title', '')[:80],
            total_available=len(evidence),
            after_filter=len(section_evidence),
            top_tiers={"GOLD": sum(1 for e in section_evidence if e.get("quality_tier")=="GOLD"),
                       "SILVER": sum(1 for e in section_evidence if e.get("quality_tier")=="SILVER")})

    # FIX-C6: Guard against empty evidence — fail loudly per LAW II
    if not section_evidence:
        logger.error(
            "[polaris graph] FIX-C6: Section '%s' has 0 matching evidence. "
            "Requested IDs: %s, available pool: %d items",
            section.title,
            section.evidence_ids[:5],
            len(evidence),
        )
        raise ValueError(
            f"FIX-C6: Section '{section.title}' has no assigned evidence. "
            f"Cannot write section without evidence (LAW II: no hallucinations)."
        )

    # TIER-3 Stage 3: Token-budget-aware evidence formatting.
    # When PG_SECTION_TOKEN_BUDGET > 0, uses tiered formatting (L0/L1/L2)
    # to fit ~3x more evidence per section within the token budget.
    # When PG_SECTION_TOKEN_BUDGET = 0 (disabled), falls back to legacy format.
    _selected_evidence_ids: list[str] = []
    if _token_budget_enabled:
        try:
            from src.polaris_graph.synthesis.token_budget import TokenBudgetAllocator
            _allocator = TokenBudgetAllocator()
            # Estimate non-evidence prompt tokens for budget calculation
            _available = _allocator.available_evidence_tokens(
                system_prompt=SECTION_SYSTEM_PROMPT[:500],  # Approximate
                user_template="",  # Evidence block is the variable part
            )
            evidence_text, _selected_evidence_ids = _allocator.select_and_format_evidence(
                evidence=section_evidence,
                available_tokens=_available,
                section_title=section.title,
            )
        except Exception as _budget_exc:
            logger.warning(
                "[polaris graph] TIER-3: Token budget failed, falling back to legacy: %s",
                str(_budget_exc)[:200],
            )
            evidence_text = _format_evidence_for_writing(section_evidence)
    else:
        evidence_text = _format_evidence_for_writing(section_evidence)

    context = ""
    if previous_section_summary:
        context = f"\n{previous_section_summary}\n"

    # FIX-304: Build position-aware prompt with full outline context
    outline_block = ""
    if full_outline_context:
        outline_block = f"\nFull report structure:\n{full_outline_context}\n"

    position_block = ""
    if section_position:
        position_block = f"\n{section_position}\n"

    # FIX-ENV4: Build conflict block for this section's evidence
    conflict_block = ""
    if evidence_conflicts:
        conflict_block = _format_conflicts_for_prompt(
            evidence_conflicts=evidence_conflicts,
            section_evidence_ids=section.evidence_ids,
        )

    # RC-5: Corroboration signals (v3 Hybrid)
    corroboration_block = ""
    if os.getenv("PG_V3_SURFACE_ANALYSIS", "0") == "1":
        high_corroboration = [
            e for e in section_evidence
            if e.get("corroborating_sources", 0) >= 3
        ]
        if high_corroboration:
            corroboration_block = "\nWELL-CORROBORATED FINDINGS (supported by 3+ independent sources):\n"
            for e in high_corroboration[:5]:
                corroboration_block += (
                    f"- {e.get('statement', '')[:200]} "
                    f"({e.get('corroborating_sources', 0)} sources) "
                    f"[CITE:{e.get('evidence_id', '?')}]\n"
                )
            corroboration_block += "Emphasize these findings as particularly well-established.\n"


    # NRC-2 + FIX-CITE-3/C1: Build covered claims + statistics block
    covered_block = ""
    if previously_covered_claims:
        # Separate statistics from sentence claims for clearer prompt
        stats = [c for c in previously_covered_claims if c.startswith("STATISTIC:")]
        claims = [c for c in previously_covered_claims if not c.startswith("STATISTIC:")]

        parts = []
        if stats:
            stats_text = ", ".join(s.replace("STATISTIC: ", "") for s in stats[:40])
            parts.append(
                f"STATISTICS ALREADY REPORTED (Do NOT reuse these exact numbers — "
                f"they appeared in earlier sections):\n{stats_text}"
            )
        if claims:
            claims_text = "\n".join(f"- {c}" for c in claims[:20])
            parts.append(
                f"CLAIMS ALREADY COVERED (Do NOT repeat these):\n{claims_text}"
            )
        covered_block = "\n" + "\n\n".join(parts) + "\n"

    # RC-6: Pre-formatted comparison tables (v3 Hybrid)
    table_block = ""
    if os.getenv("PG_V3_COMPARISON_TABLES", "0") == "1":
        tables = _build_comparison_tables(section_evidence)
        if tables:
            table_block = (
                f"\nPRE-FORMATTED COMPARISON TABLES (from structured evidence data):\n"
                f"{tables}\n\n"
                "You MUST incorporate these tables into your section text and discuss "
                "the patterns they reveal.\n"
            )

    prompt = f"""Report title: {report_title}
{position_block}{outline_block}
Section: {section.title}
Section description: {section.description}
Research question: {query}
{context}
Available evidence for this section:
{evidence_text}
{conflict_block}
{corroboration_block}
{covered_block}
{table_block}CRITICAL: This section must directly contribute to answering the research question: {query[:200]}. Every paragraph should connect its findings back to this question.

Write this section. If this is not the first section, begin with a 1-sentence bridge that connects to the previous section's topic. Then proceed with unique analysis. Connect findings to the broader report structure.
Every factual claim MUST include a [CITE:evidence_id] marker referencing the specific evidence piece.
Cite the evidence pieces that directly support your analysis. Prioritize GOLD and SILVER tier evidence. You do NOT need to cite every piece -- quality of argument is more important than exhaustive citation. Omit evidence that would weaken the narrative by being tangential or repetitive.
CITATION DIVERSITY: Do NOT cite the same source more than 3 times in this section. Spread citations across different sources to strengthen the argument with independent corroboration. You MUST cite at least 2 unique sources in this section. If cross-section evidence is provided, use it when relevant but do NOT repeat information covered in adjacent sections.
CROSS-REFERENCES: When referencing other sections of this report, always use the format 'as discussed in [Section Title]' with the exact section title. Never use section numbers (e.g., 'Section 4') and never use colons (e.g., 'discussed in: Limitations').

Target: approximately {min(200 + len(section_evidence) * 80, 2000)} words."""

    # RC-2 (v3 Hybrid): Inject analytical instructions when enabled
    if os.getenv("PG_V3_ANALYTICAL_PROMPT", "0") == "1":
        _analytical_focus = getattr(section, "analytical_focus", "") or ""
        _focus_line = f"\\nANALYTICAL FOCUS: {_analytical_focus}" if _analytical_focus else ""
        prompt += f"""
{_focus_line}
ANALYTICAL INSTRUCTIONS (MANDATORY):
Analyze the evidence to answer: {section.description}
You MUST perform these operations in your writing:
- AGGREGATE: Combine similar findings from multiple sources into synthesized claims (cite all). NEVER list source findings sequentially.
- COMPARE: Explicitly compare how different studies, methods, or conditions produced different results. Use "whereas", "in contrast", "compared to".
- EXPLAIN: For each major finding, explain WHY — what mechanism, what implication.
- TABULATE: When you have 3+ comparable data points, you MUST present a markdown table with citations in each row.
- CHALLENGE: Include at least 1 paragraph acknowledging limitations, contradictions, or gaps.
BANNED: Sequential source summaries ("Study A found... Study B found..."), filler phrases."""

    _n_evidence = len(section_evidence)
    _suggested_words = min(200 + _n_evidence * 80, 2000)

    # RC-2 (v3 Hybrid): Use build_section_writer_prompt when analytical mode enabled
    if os.getenv("PG_V3_ANALYTICAL_PROMPT", "0") == "1":
        from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
        _analytical_focus = getattr(section, "analytical_focus", "") or ""
        system = build_section_writer_prompt(
            n_evidence=_n_evidence,
            suggested_words=_suggested_words,
            analytical_focus=_analytical_focus,
        )
    else:
        system = SECTION_SYSTEM_PROMPT.format(
            n_evidence=_n_evidence,
            suggested_words=_suggested_words,
        )

    # TIER-3 Stage 6: Token accounting — track prompt component sizes
    try:
        from src.polaris_graph.synthesis.token_accounting import (
            PromptTokenAccounting,
            PG_TOKEN_ACCOUNTING_ENABLED,
        )
        if PG_TOKEN_ACCOUNTING_ENABLED:
            _non_evidence_prompt = prompt.replace(evidence_text, "")
            _accounting = PromptTokenAccounting(
                system_prompt=system,
                evidence_block=evidence_text,
                context_block=_non_evidence_prompt,
                evidence_count=len(section_evidence),
                section_title=section.title,
            )
            _accounting.log()
            _accounting.emit_tracer_event()
    except Exception:
        pass  # Non-critical observability

    # Try up to 2 attempts — retry if content comes back empty
    # (can happen when Kimi puts everything in reasoning_content)
    content = ""
    # FIX-CITE-3/GAP-LLM: Use reason() for section writing when enabled.
    # Gives the model explicit reasoning budget to think through evidence
    # before generating prose. Produces deeper analytical output with I²,
    # GRADE ratings, and structured comparisons.
    # TWO-POOL ARCHITECTURE: Use generate() which sends reasoning to Pool 1
    # (logged) and content to Pool 2 (output). GLM-5 with two-pool separation
    # returns ~1300 chars content + ~6000 chars reasoning at max_tokens=16384.
    # Reasoning drives analytical depth; content is clean prose.
    for attempt in range(2):
        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=PG_SECTION_WRITER_MAX_TOKENS,
        )
        content = response.content.strip()
        if content and len(content.split()) >= 50:
            break
        logger.warning(
            "[polaris graph] Section '%s' attempt %d: only %d words, retrying",
            section.title,
            attempt + 1,
            len(content.split()) if content else 0,
        )

    # SF-14: Raise on near-empty sections after 2 attempts
    if not content or len(content.split()) < 50:
        raise RuntimeError(
            f"Section '{section.title}' too short ({len(content.split()) if content else 0} words) "
            f"after 2 attempts"
        )

    # Detect truncation: content doesn't end with sentence-ending punctuation
    if content and not content.rstrip().endswith((".", "?", "!", '"', ")")):
        logger.warning(
            "[polaris graph] Section '%s' appears truncated (%d words), "
            "requesting continuation",
            section.title,
            len(content.split()),
        )
        continuation_prompt = (
            f"Continue writing exactly from where this text was cut off. "
            f"Do NOT repeat any text. Start your response with the next word "
            f"after the cutoff point.\n\n"
            f"Text so far (last 200 chars): ...{content[-200:]}"
        )
        cont_response = await client.generate(
            prompt=continuation_prompt,
            system=system,
            max_tokens=PG_SECTION_CONTINUATION_MAX_TOKENS,  # FIX-C5
            temperature=0.7,
        )
        continuation = cont_response.content.strip()
        if continuation and len(continuation.split()) >= 10:
            content = content + " " + continuation
            logger.info(
                "[polaris graph] Section '%s' continued: +%d words",
                section.title,
                len(continuation.split()),
            )

    # FIX-R2: Detect incomplete numerical claims (sentences ending with comparative
    # words but missing the actual number, e.g., "exceeds," with no threshold).
    _dangling_pattern = re.compile(
        r'(exceeds|reaches|compared to|limit of|threshold of|more than|less than|'
        r'greater than|up to|approximately|roughly|around|about)\s*[,.]?\s*$',
        re.MULTILINE,
    )
    _dangling_match = _dangling_pattern.search(content)
    if _dangling_match:
        logger.warning(
            "[polaris graph] FIX-R2: Dangling numerical claim in '%s': '%s'",
            section.title[:40], _dangling_match.group()[:60],
        )
        # Request LLM to complete the dangling claim
        try:
            _r2_prompt = (
                "The following text ends with an incomplete comparison or threshold. "
                "Complete ONLY the missing number/unit from the evidence provided. "
                "Output the FULL corrected text.\n\n"
                f"Text ending: ...{content[-300:]}\n\n"
                f"Evidence: {evidence_text[:3000]}"
            )
            _r2_resp = await client.generate(
                prompt=_r2_prompt, system=system, max_tokens=PG_SECTION_CONTINUATION_MAX_TOKENS, temperature=0.3,  # FIX-C5
            )
            _r2_fix = _r2_resp.content.strip()
            if _r2_fix and len(_r2_fix.split()) >= 10:
                content = content + " " + _r2_fix
                content = _scrub_cot(content)
        except Exception as _r2_exc:
            logger.debug("[polaris graph] FIX-R2: completion failed: %s", str(_r2_exc)[:100])

    # Defense-in-depth: scrub any CoT that leaked through generate()
    pre_scrub_len = len(content)
    content = _scrub_cot(content)
    post_scrub_len = len(content)
    # COT-5: Log scrubber activation metrics — after COT-1, this should be 0%
    if pre_scrub_len != post_scrub_len:
        logger.warning(
            "[polaris graph] COT-5: _scrub_cot() ACTIVATED on section '%s' "
            "(%d -> %d chars, -%d chars removed). COT-1 may not be fully effective.",
            section.title[:50],
            pre_scrub_len,
            post_scrub_len,
            pre_scrub_len - post_scrub_len,
        )

    # KEY-FINDINGS ENFORCEMENT: Detect missing Key Findings and inject via LLM.
    # The system prompt instructs "End each section with a **Key Findings** subsection"
    # but LLMs frequently skip it. This code-level enforcement guarantees it.
    _kf_enabled = os.getenv("PG_KEY_FINDINGS_ENFORCEMENT", "1") == "1"
    _has_key_findings = bool(re.search(
        r'(\*\*Key Findings\*\*|##+ Key Findings)', content, re.IGNORECASE
    ))
    if _kf_enabled and not _has_key_findings and len(content.split()) >= 100:
        logger.info(
            "[polaris graph] KEY-FIND: Section '%s' missing Key Findings — "
            "generating via separate LLM call",
            section.title[:40],
        )
        try:
            _kf_prompt = (
                f"Based on this section content, write a **Key Findings** subsection "
                f"with 3-5 bullet points. Each bullet MUST include a [CITE:evidence_id] "
                f"marker from the evidence used in this section.\n\n"
                f"SECTION CONTENT:\n{content}\n\n"
                f"Output ONLY the Key Findings block in this exact format:\n"
                f"**Key Findings:**\n"
                f"- Finding 1 [CITE:ev_xxx]\n"
                f"- Finding 2 [CITE:ev_yyy]\n"
                f"- Finding 3 [CITE:ev_zzz]"
            )
            _kf_resp = await client.generate(
                prompt=_kf_prompt,
                system="Extract key findings from the section. Output ONLY the bullet list.",
                max_tokens=1024,
                temperature=0.3,
            )
            _kf_block = _kf_resp.content.strip()
            # Validate: must contain Key Findings and at least 2 bullet points
            _kf_has_header = bool(re.search(r'Key Findings', _kf_block, re.IGNORECASE))
            _kf_bullet_count = len(re.findall(r'^\s*[-*+]\s+', _kf_block, re.MULTILINE))
            if _kf_has_header and _kf_bullet_count >= 2:
                _kf_block = _scrub_cot(_kf_block)
                content = content.rstrip() + "\n\n" + _kf_block
                logger.info(
                    "[polaris graph] KEY-FIND: Injected Key Findings with %d bullets "
                    "into '%s'",
                    _kf_bullet_count,
                    section.title[:40],
                )
            else:
                logger.warning(
                    "[polaris graph] KEY-FIND: Generated block invalid for '%s' "
                    "(header=%s, bullets=%d) — skipping",
                    section.title[:40], _kf_has_header, _kf_bullet_count,
                )
        except Exception as _kf_exc:
            logger.warning(
                "[polaris graph] KEY-FIND: Key Findings generation failed for '%s': %s",
                section.title[:40], str(_kf_exc)[:100],
            )

    # FIX-KF-PRESERVE: Extract Key Findings block BEFORE post-processing.
    # Three LLM rewrites below (hedging, citation density, unit correction) can
    # silently strip Key Findings when they regenerate the section. We preserve
    # the block and re-append after all post-processing completes.
    _kf_preserve_block = ""
    _kf_preserve_match = re.search(
        r'(\n\n\*\*Key Findings:?\*\*\s*\n(?:\s*[-*+]\s+.*\n?)+)',
        content,
        re.IGNORECASE,
    )
    if not _kf_preserve_match:
        _kf_preserve_match = re.search(
            r'(\n\n#{2,4}\s+Key Findings:?\s*\n(?:\s*[-*+]\s+.*\n?)+)',
            content,
            re.IGNORECASE,
        )
    if _kf_preserve_match:
        _kf_preserve_block = _kf_preserve_match.group(1)
        # Remove from content so rewrites don't garble it
        content = content[:_kf_preserve_match.start()] + content[_kf_preserve_match.end():]

    # FIX-047-K10: Post-write hedging enforcement.
    # T047 audit found "may" 25x and "potentially" 17x (section_writer prompt
    # says "max 2 per paragraph" but had no enforcement). Count paragraphs
    # and hedging words; if ratio exceeds threshold, do a revision pass.
    _hedging_max_per_para = int(os.getenv("PG_HEDGING_MAX_PER_PARAGRAPH", "2"))
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    _hedge_pattern = re.compile(
        r"\b(may|might|could|potentially|perhaps|possibly)\b", re.IGNORECASE,
    )
    total_hedges = len(_hedge_pattern.findall(content))
    hedge_limit = max(4, _hedging_max_per_para * len(paragraphs))
    if total_hedges > hedge_limit:
        logger.info(
            "[polaris graph] FIX-047-K10: Section '%s' has %d hedging words "
            "(limit: %d for %d paragraphs). Requesting revision.",
            section.title[:40], total_hedges, hedge_limit, len(paragraphs),
        )
        revision_prompt = (
            f"The following section uses hedging words ({total_hedges} instances of "
            f"'may', 'might', 'could', 'potentially', 'perhaps', 'possibly') "
            f"too frequently. Rewrite it with maximum {_hedging_max_per_para} "
            f"hedging words per paragraph. Use DEFINITIVE language when evidence "
            f"supports the claim. Replace weak hedges like 'may be effective' "
            f"with 'is effective' or 'has demonstrated effectiveness'. "
            f"Keep ALL [CITE:...] markers exactly as they are.\n\n"
            f"Section to revise:\n{content}"
        )
        try:
            revision = await client.generate(
                prompt=revision_prompt,
                system=system,
                max_tokens=PG_SECTION_WRITER_MAX_TOKENS,
                temperature=0.4,
            )
            revised = revision.content.strip()
            revised_hedges = len(_hedge_pattern.findall(revised))
            # Only accept revision if it actually reduced hedging and is substantial
            if revised and len(revised.split()) >= 50 and revised_hedges < total_hedges:
                content = _scrub_cot(revised)
                logger.info(
                    "[polaris graph] FIX-047-K10: Hedging reduced %d -> %d in '%s'",
                    total_hedges, revised_hedges, section.title[:40],
                )
        except Exception as exc:
            logger.warning(
                "[polaris graph] FIX-047-K10: Hedging revision failed for '%s': %s",
                section.title[:40], str(exc)[:100],
            )

    # FIX-R12: Per-section citation density enforcement.
    # Sections with < 0.5 citations per 100 words are essentially uncited prose.
    _r12_min_density = float(os.getenv("PG_MIN_CITATION_DENSITY", "0.5"))
    _r12_word_count = len(content.split())
    _r12_cite_count = content.count("[CITE:")
    _r12_density = (_r12_cite_count / max(_r12_word_count, 1)) * 100
    if _r12_density < _r12_min_density and _r12_word_count > 100 and section_evidence:
        logger.warning(
            "[polaris graph] FIX-R12: Section '%s' under-cited: %.2f citations/100w "
            "(min %.2f). Requesting citation-rich revision.",
            section.title[:40], _r12_density, _r12_min_density,
        )
        try:
            _r12_prompt = (
                f"The following section has too few citations ({_r12_cite_count} citations "
                f"in {_r12_word_count} words = {_r12_density:.1f} per 100 words). "
                f"Rewrite it so that EVERY factual claim has a [CITE:evidence_id] marker. "
                f"Target at least 1 citation per 2 sentences. Keep the same content and length.\n\n"
                f"SECTION:\n{content}\n\n"
                f"AVAILABLE EVIDENCE:\n{evidence_text}"
            )
            _r12_resp = await client.generate(
                prompt=_r12_prompt,
                system=system,
                max_tokens=PG_SECTION_WRITER_MAX_TOKENS,
                temperature=0.4,
            )
            _r12_revised = _r12_resp.content.strip()
            _r12_new_cites = _r12_revised.count("[CITE:")
            if _r12_revised and _r12_new_cites > _r12_cite_count and len(_r12_revised.split()) >= 50:
                content = _scrub_cot(_r12_revised)
                logger.info(
                    "[polaris graph] FIX-R12: Citation density improved %d -> %d in '%s'",
                    _r12_cite_count, _r12_new_cites, section.title[:40],
                )
        except Exception as _r12_exc:
            logger.warning(
                "[polaris graph] FIX-R12: Citation revision failed for '%s': %s",
                section.title[:40], str(_r12_exc)[:100],
            )

    # FIX-R13: Enforce hedging word limit (post-processing, not prompt-only)
    content = _limit_hedging(content)

    # FIX-059-K: Limit transition word density
    content = _limit_transitions(content)

    # FIX-059-L: Break long paragraphs for readability
    content = _break_long_paragraphs(content)

    # FIX-R1: Unit consistency validation + correction
    # When section text contains units NOT found in evidence, trigger LLM rewrite
    # to replace incorrect units with evidence's exact phrasing
    # LAW VI: Unit patterns from config (not hardcoded)
    from src.polaris_graph.config_loader import get_domain_config as _get_sw_cfg
    _sw_unit_cfg = _get_sw_cfg().unit_patterns
    _unit_re_str = _sw_unit_cfg.pattern if _sw_unit_cfg else r"ppt|ppb|mg/L|μg/L"
    _unit_pattern = re.compile(r'(\d+\.?\d*)\s*(' + _unit_re_str + r')')
    _unit_matches = _unit_pattern.findall(content)
    _mismatched_units: list[tuple[str, str]] = []
    if _unit_matches and section_evidence:
        _ev_text = " ".join(
            e.get("direct_quote", "") + " " + e.get("statement", "")
            for e in section_evidence
        )
        for _val, _unit in _unit_matches:
            # Check if this exact value+unit combination appears in evidence
            _val_in_ev = _val in _ev_text
            _unit_in_ev = _unit.lower() in _ev_text.lower()
            if not _val_in_ev and _unit not in ("ppt", "ppb", "parts per trillion", "parts per billion"):
                _mismatched_units.append((_val, _unit))
            elif _val_in_ev and not _unit_in_ev:
                # Value is in evidence but with a DIFFERENT unit
                _mismatched_units.append((_val, _unit))

    if _mismatched_units:
        logger.warning(
            "[polaris graph] FIX-R1: %d unit mismatch(es) detected in '%s': %s. "
            "Triggering LLM correction.",
            len(_mismatched_units),
            section.title[:40],
            ", ".join(f"{v} {u}" for v, u in _mismatched_units[:5]),
        )
        # Build correction prompt with evidence excerpts
        _ev_excerpts = []
        for e in section_evidence[:10]:
            _q = e.get("direct_quote", "")
            _s = e.get("statement", "")
            if any(_val in (_q + " " + _s) for _val, _ in _mismatched_units):
                _ev_excerpts.append(f"- Evidence: {(_q or _s)[:300]}")

        _correction_prompt = (
            "The following section text contains unit measurement errors. "
            "Some numerical values use INCORRECT units that do NOT match the source evidence."
            "\n\nMISMATCHED UNITS (these are WRONG in the text):\n"
            + "\n".join(f"- {v} {u}" for v, u in _mismatched_units[:10])
            + "\n\nEVIDENCE WITH CORRECT UNITS:\n"
            + "\n".join(_ev_excerpts[:10])
            + "\n\nSECTION TEXT:\n" + content
            + "\n\nINSTRUCTION: Return the COMPLETE section text with ONLY the unit errors corrected. "
            "Replace incorrect units with the EXACT units from the evidence. "
            "Do NOT change anything else \u2014 keep all text, citations, and structure identical. "
            "If you cannot determine the correct unit from the evidence, keep the original."
        )
        try:
            _corrected = await client.generate(
                prompt=_correction_prompt,
                system="You are a precise copy editor. Fix ONLY unit measurement errors. Return the complete text.",
                max_tokens=PG_SECTION_CONTINUATION_MAX_TOKENS,  # FIX-C5
                timeout=60,
            )
            if _corrected and len(_corrected.split()) >= len(content.split()) * 0.8:
                # Sanity check: corrected version should be similar length
                content = _corrected
                logger.info(
                    "[polaris graph] FIX-R1: Unit correction applied for '%s'",
                    section.title[:40],
                )
            else:
                logger.warning(
                    "[polaris graph] FIX-R1: Unit correction returned too-short result "
                    "(%d words vs %d original), keeping original",
                    len((_corrected or "").split()), len(content.split()),
                )
        except Exception as _r1_exc:
            logger.warning(
                "[polaris graph] FIX-R1: Unit correction LLM call failed for '%s': %s. "
                "Keeping original text with warning.",
                section.title[:40], str(_r1_exc)[:100],
            )

    # FIX-KF-PRESERVE: Re-append preserved Key Findings after all post-processing
    if _kf_preserve_block:
        # Only re-append if the rewrites didn't somehow regenerate KF
        if not re.search(r'Key Findings', content, re.IGNORECASE):
            content = content.rstrip() + _kf_preserve_block
            logger.info(
                "[polaris graph] FIX-KF-PRESERVE: Re-appended Key Findings to '%s' "
                "after post-processing",
                section.title[:40],
            )

    # Extract claims made (sentences with citations)
    claims = [
        line.strip()
        for line in content.split(".")
        if "[CITE:" in line and len(line.strip()) > 20
    ]

    draft = SectionDraft(
        section_id=section.section_id,
        title=section.title,
        content=content,
        claims_made=claims[:50],  # Cap at 50 claims per section
        evidence_ids=list(section.evidence_ids),  # FIX-039: Propagate from outline
    )

    word_count = len(content.split())
    logger.info(
        "[polaris graph] Section '%s' written: %d words, %d claims",
        section.title,
        word_count,
        len(claims),
    )

    # OBS-6: Trace section write
    tracer = get_tracer()
    if tracer:
        tracer.llm_call(
            "synthesize", "section_write",
            section_id=section.section_id,
            word_count=word_count,
            evidence_count=len(section_evidence),
            title=section.title,
            content=content[:8000],
            model=client.model,
        )

    return draft


async def write_all_sections(
    client: OpenRouterClient,
    outline: ReportOutline,
    evidence: list[EvidencePiece],
    query: str,
    concurrency: int = 4,
    evidence_conflicts: Optional[list[dict]] = None,
    global_assignments: Optional[dict[str, list[str]]] = None,
    cross_section_evidence_ids: Optional[list[str]] = None,
) -> tuple[list[SectionDraft], dict[str, list[str]]]:
    """
    Write all sections with controlled concurrency.

    Sections are written in batches to maintain context flow while
    allowing parallelism within batches.

    FIX-107I: Now returns a tuple of (drafts, section_evidence_map) where
    section_evidence_map maps each section_id to the list of evidence_ids
    that were actually provided to the LLM after per-section filtering.

    FIX-ENV4: Accepts evidence_conflicts and passes them through to
    individual section writers so conflicts are addressed in prose.

    FIX-E: Accepts global_assignments (Pass 1 output) and cross_section_evidence_ids.
    When provided, evidence is assigned by global LLM assignment instead of
    per-section embedding similarity, breaking the evidence isolation problem.

    Returns:
        Tuple of (list of SectionDraft, dict mapping section_id to evidence_id list).
    """
    sorted_sections = sorted(outline.sections, key=lambda s: s.order)
    drafts: list[SectionDraft] = []
    semaphore = asyncio.Semaphore(concurrency)

    # FIX-107I: Track which evidence was provided to each section
    section_evidence_map: dict[str, list[str]] = {}

    # FIX-9: Track citation frequency per source URL for diversity enforcement
    max_citation_freq = int(os.getenv("PG_MAX_CITATION_FREQUENCY", "8"))
    source_citation_count: dict[str, int] = {}  # source_url -> citation count

    # FIX-304: Build full outline context for position awareness
    outline_context = "\n".join(
        f"  {i+1}. {s.title}: {s.description[:80]}"
        for i, s in enumerate(sorted_sections)
    )
    total_sections = len(sorted_sections)

    # FIX-E: Two-path evidence assignment
    # Path A (FIX-E): Use global LLM assignment when available
    # Path B (fallback): Use per-section embedding similarity (FIX-107I/FIX-043C)
    evidence_by_id = {e.get("evidence_id", ""): e for e in evidence}
    cross_section_evidence = [
        evidence_by_id[eid] for eid in (cross_section_evidence_ids or [])
        if eid in evidence_by_id
    ]

    section_filtered_evidence: dict[str, list[EvidencePiece]] = {}

    # FIX-CITE-3/HARD-DEDUP + REDIST: Global evidence dedup for Path A too
    _hard_dedup_a = os.getenv("PG_HARD_EVIDENCE_DEDUP", "1") == "1"
    _globally_claimed_a: set[str] = set()
    _n_sections_a = max(len(sorted_sections), 1)
    _total_evidence_a = len(evidence)
    _fair_share_a = max(
        int(os.getenv("PG_MIN_EVIDENCE_PER_SECTION", "8")),
        int(_total_evidence_a / _n_sections_a * 1.5),
    )

    if global_assignments:
        # FIX-E Path A: Global evidence assignment (breaks section isolation)
        logger.info(
            "[polaris graph] FIX-E: Using global evidence assignment for %d sections "
            "(%d cross-section evidence)",
            len(global_assignments),
            len(cross_section_evidence),
        )
        for section in sorted_sections:
            # Primary evidence: assigned by global LLM pass
            primary_ids = global_assignments.get(section.section_id, [])
            primary_evidence = [
                evidence_by_id[eid] for eid in primary_ids
                if eid in evidence_by_id
            ]

            # Cross-section evidence: visible to all sections
            existing_ids = {e.get("evidence_id") for e in primary_evidence}
            combined = list(primary_evidence)
            for ce in cross_section_evidence:
                if ce.get("evidence_id") not in existing_ids:
                    combined.append(ce)
                    existing_ids.add(ce.get("evidence_id"))

            # If global assignment returned too few, supplement with outline assignment
            if len(combined) < 5:
                for eid in section.evidence_ids:
                    if eid not in existing_ids and eid in evidence_by_id:
                        combined.append(evidence_by_id[eid])
                        existing_ids.add(eid)

            # FIX-CITE-3/HARD-DEDUP: Remove already-claimed evidence (Path A)
            if _hard_dedup_a:
                combined = [
                    e for e in combined
                    if e.get("evidence_id") not in _globally_claimed_a
                ]

            # Final top-k filter — use wider pool when token budget enabled
            # FIX-CITE-3/REDIST: Cap to fair share (Path A)
            _tb_enabled = int(os.getenv("PG_SECTION_TOKEN_BUDGET", "6000")) > 0
            _pool_k = int(os.getenv("PG_EVIDENCE_CANDIDATE_POOL", "100")) if _tb_enabled else PG_SECTION_EVIDENCE_TOP_K
            _effective_k_a = min(_pool_k, _fair_share_a) if _hard_dedup_a else _pool_k
            filtered = _filter_evidence_for_section(
                evidence=combined,
                section_title=section.title,
                section_description=section.description,
                top_k=_effective_k_a,
            )
            section_filtered_evidence[section.section_id] = filtered

            # FIX-CITE-3/HARD-DEDUP: Claim these evidence IDs (Path A)
            if _hard_dedup_a:
                for e in filtered:
                    _globally_claimed_a.add(e.get("evidence_id", ""))

            section_evidence_map[section.section_id] = [
                e.get("evidence_id", "") for e in filtered
            ]
    else:
        # FIX-107I/FIX-043C Path B: Per-section embedding similarity (fallback)
        all_assigned_ids: set[str] = set()
        for section in sorted_sections:
            all_assigned_ids.update(section.evidence_ids)

        unassigned_evidence = [
            e for e in evidence if e.get("evidence_id") not in all_assigned_ids
        ]
        if unassigned_evidence:
            logger.info(
                "[polaris graph] FIX-043C: %d/%d evidence unassigned by outline — "
                "will match to sections by embedding similarity",
                len(unassigned_evidence), len(evidence),
            )

        # FIX-CITE-3/HARD-DEDUP: Track globally claimed evidence IDs.
        # Once an evidence piece is assigned to a section, it is removed
        # from the pool for subsequent sections. This is the deterministic
        # fix for cross-section repetition (GraphRAG pattern).
        #
        # FIX-CITE-3/REDIST: Fair-share cap prevents first-come hoarding.
        # Each section gets at most ceil(total_evidence / num_sections * 1.5)
        # evidence pieces. This ensures later sections have material to work with.
        _hard_dedup = os.getenv("PG_HARD_EVIDENCE_DEDUP", "1") == "1"
        _globally_claimed: set[str] = set()
        _n_sections = max(len(sorted_sections), 1)
        _total_evidence = len(evidence)
        _fair_share = max(
            int(os.getenv("PG_MIN_EVIDENCE_PER_SECTION", "8")),
            int(_total_evidence / _n_sections),
        )
        if _hard_dedup:
            logger.info(
                "[polaris graph] FIX-CITE-3/REDIST: Evidence fair share = %d "
                "(%d evidence / %d sections * 1.5)",
                _fair_share, _total_evidence, _n_sections,
            )

        for section in sorted_sections:
            # First, get outline-assigned evidence
            assigned_evidence = [
                e for e in evidence if e.get("evidence_id") in section.evidence_ids
            ]

            # FIX-CITE-3/HARD-DEDUP: Remove already-claimed evidence
            if _hard_dedup:
                assigned_evidence = [
                    e for e in assigned_evidence
                    if e.get("evidence_id") not in _globally_claimed
                ]

            # FIX-069: When outline assignment is empty or depleted by dedup,
            # pull from the FULL unclaimed pool by embedding similarity.
            # This prevents 14/15 sections getting 0 evidence.
            _min_per_section = int(os.getenv("PG_MIN_EVIDENCE_PER_SECTION", "8"))
            if len(assigned_evidence) < _min_per_section:
                _all_unclaimed = [
                    e for e in evidence
                    if e.get("evidence_id") not in _globally_claimed
                ]
                if _all_unclaimed:
                    bonus_from_pool = _filter_evidence_for_section(
                        evidence=_all_unclaimed,
                        section_title=section.title,
                        section_description=section.description,
                        top_k=_min_per_section,
                    )
                    existing_ids = {e.get("evidence_id") for e in assigned_evidence}
                    for b in bonus_from_pool:
                        if b.get("evidence_id") not in existing_ids:
                            assigned_evidence.append(b)
                        if len(assigned_evidence) >= _min_per_section:
                            break

            # FIX-043C: Also pull in unassigned evidence (supplementary)
            if unassigned_evidence and len(assigned_evidence) < _fair_share:
                _available_unassigned = [
                    e for e in unassigned_evidence
                    if not _hard_dedup or e.get("evidence_id") not in _globally_claimed
                ]
                bonus = _filter_evidence_for_section(
                    evidence=_available_unassigned,
                    section_title=section.title,
                    section_description=section.description,
                    top_k=10,
                )
                existing_ids = {e.get("evidence_id") for e in assigned_evidence}
                for b in bonus:
                    if b.get("evidence_id") not in existing_ids:
                        assigned_evidence.append(b)

            # Then apply embedding-based filtering on the combined pool
            # FIX-CITE-3/REDIST: Cap to fair share to prevent first-come hoarding
            _tb_enabled_b = int(os.getenv("PG_SECTION_TOKEN_BUDGET", "6000")) > 0
            _pool_k_b = int(os.getenv("PG_EVIDENCE_CANDIDATE_POOL", "100")) if _tb_enabled_b else PG_SECTION_EVIDENCE_TOP_K
            _effective_k = min(_pool_k_b, _fair_share) if _hard_dedup else _pool_k_b
            filtered = _filter_evidence_for_section(
                evidence=assigned_evidence,
                section_title=section.title,
                section_description=section.description,
                top_k=_effective_k,
            )
            section_filtered_evidence[section.section_id] = filtered

            # FIX-CITE-3/HARD-DEDUP: Claim these evidence IDs
            if _hard_dedup:
                for e in filtered:
                    _globally_claimed.add(e.get("evidence_id", ""))

            section_evidence_map[section.section_id] = [
                e.get("evidence_id", "") for e in filtered
            ]

    # NRC-2: Track previously covered claims across all sections
    all_covered_claims: list[str] = []

    # FIX-058G: Per-section write timeout to prevent hung LLM calls
    section_write_timeout = int(os.getenv("PG_SECTION_WRITE_TIMEOUT", "300"))

    # FIX-STARVATION: Keep reference to full evidence pool for rescue
    full_evidence_pool = evidence

    async def _write_with_semaphore(
        section: SectionOutlineItem,
        prev_summary: str,
        section_idx: int,
        covered_claims: list[str],
    ) -> SectionDraft:
        async with semaphore:
            filtered_ev = section_filtered_evidence.get(
                section.section_id, []
            )
            filtered_ids = [
                e.get("evidence_id", "") for e in filtered_ev
            ]
            section_copy = SectionOutlineItem(
                section_id=section.section_id,
                title=section.title,
                description=section.description,
                evidence_ids=filtered_ids,
                target_words=section.target_words,
                order=section.order,
            )
            return await asyncio.wait_for(
                write_section(
                    client=client,
                    section=section_copy,
                    evidence=evidence,
                    query=query,
                    report_title=outline.title,
                    previous_section_summary=prev_summary,
                    full_outline_context=outline_context,
                    section_position=f"Section {section_idx + 1} of {total_sections}",
                    evidence_conflicts=evidence_conflicts,
                    previously_covered_claims=covered_claims if covered_claims else None,
                    all_evidence=full_evidence_pool,  # FIX-STARVATION
                ),
                timeout=section_write_timeout,
            )

    # Write in sequential batches of `concurrency` for context flow
    prev_summary = outline.abstract[:200] if outline.abstract else ""

    for i in range(0, len(sorted_sections), concurrency):
        batch = sorted_sections[i : i + concurrency]
        tasks = [
            _write_with_semaphore(section, prev_summary, i + j, list(all_covered_claims))
            for j, section in enumerate(batch)
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # SF-13: Collect failed sections for retry
        failed_sections: list[tuple[int, SectionOutlineItem]] = []
        for idx, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(
                    "[polaris graph] Section write failed: %s",
                    str(result)[:200],
                )
                if idx < len(batch):
                    failed_sections.append((idx, batch[idx]))
                continue
            drafts.append(result)

        # Retry failed sections once
        if failed_sections:
            logger.warning(
                "[polaris graph] Retrying %d failed sections",
                len(failed_sections),
            )
            for _idx, section in failed_sections:
                try:
                    # FIX-107I: Use same pre-filtered evidence for retry
                    filtered_ev = section_filtered_evidence.get(
                        section.section_id, []
                    )
                    filtered_ids = [
                        e.get("evidence_id", "") for e in filtered_ev
                    ]
                    section_copy = SectionOutlineItem(
                        section_id=section.section_id,
                        title=section.title,
                        description=section.description,
                        evidence_ids=filtered_ids,
                        target_words=section.target_words,
                        order=section.order,
                    )
                    retry_result = await asyncio.wait_for(
                        write_section(
                            client=client,
                            section=section_copy,
                            evidence=evidence,
                            query=query,
                            report_title=outline.title,
                            previous_section_summary=prev_summary,
                            full_outline_context=outline_context,
                            section_position=f"Section {i + _idx + 1} of {total_sections}",
                            evidence_conflicts=evidence_conflicts,
                            previously_covered_claims=list(all_covered_claims) if all_covered_claims else None,
                            all_evidence=full_evidence_pool,  # FIX-STARVATION retry path
                        ),
                        timeout=section_write_timeout,
                    )
                    drafts.append(retry_result)
                except Exception as exc:
                    logger.error(
                        "[polaris graph] FIX-H14: Section '%s' failed after retry: "
                        "%s — adding placeholder to preserve report structure",
                        section.title,
                        str(exc)[:200],
                    )
                    # FIX-H14: Add placeholder instead of silently dropping
                    drafts.append(
                        SectionDraft(
                            section_id=section.section_id,
                            title=section.title,
                            content=(
                                f"[Section '{section.title}' could not be generated "
                                f"due to a processing error. The evidence assigned to "
                                f"this section remains available in the bibliography.]"
                            ),
                            claims_made=[],
                            evidence_ids=section.evidence_ids,
                        )
                    )

        # FIX-9: Update per-source citation counts from newly written sections
        for draft in batch_results:
            if isinstance(draft, Exception):
                continue
            # Extract cited evidence IDs from this section
            cited_ids = set(re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", draft.content))
            for eid in cited_ids:
                # Find the source URL for this evidence ID
                ev_match = next(
                    (e for e in evidence if e.get("evidence_id") == eid), None
                )
                if ev_match:
                    src_url = ev_match.get("source_url", "")
                    if src_url:
                        source_citation_count[src_url] = (
                            source_citation_count.get(src_url, 0) + 1
                        )

        # FIX-9: Down-rank over-cited sources for subsequent sections by
        # moving their evidence to the end of the filtered evidence list
        over_cited_urls = {
            url for url, count in source_citation_count.items()
            if count >= max_citation_freq
        }
        if over_cited_urls:
            for sid, filtered_ev in section_filtered_evidence.items():
                # Check if this section hasn't been written yet
                written_ids = {d.section_id for d in drafts}
                if sid in written_ids:
                    continue
                # Partition: non-over-cited first, over-cited last
                primary = [
                    e for e in filtered_ev
                    if e.get("source_url", "") not in over_cited_urls
                ]
                deprioritized = [
                    e for e in filtered_ev
                    if e.get("source_url", "") in over_cited_urls
                ]
                section_filtered_evidence[sid] = primary + deprioritized
            logger.info(
                "[polaris graph] FIX-9: %d sources over-cited (>=%d), "
                "deprioritized for remaining sections",
                len(over_cited_urls),
                max_citation_freq,
            )

        # NRC-2 + FIX-CITE-3/C1: Extract key claims AND specific statistics
        # from newly written sections to prevent cross-section repetition.
        # Focus on concrete data points (numbers with units) which the LLM
        # is most likely to repeat verbatim across sections.
        for draft in batch_results:
            if isinstance(draft, Exception):
                continue
            # Extract sentences with citations as "covered claims"
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', draft.content)
            for sent in sentences:
                if "[CITE:" in sent and len(sent.split()) >= 8:
                    # Truncate to key claim (first 120 chars)
                    claim = sent.strip()[:120]
                    if claim not in all_covered_claims:
                        all_covered_claims.append(claim)

            # FIX-CITE-3/C1: Extract specific statistics (numbers + units/context)
            # These are the data points most likely to be repeated verbatim.
            stats = re.findall(
                r'(\d+[\.\d]*\s*(?:kg|%|mmol|mg|pmol|mmHg|hours?|weeks?|months?'
                r'|years?|participants?|studies|trials?|adults?))',
                draft.content, re.IGNORECASE,
            )
            for stat in stats:
                stat_claim = f"STATISTIC: {stat.strip()}"
                if stat_claim not in all_covered_claims:
                    all_covered_claims.append(stat_claim)

            # Cap to keep prompt manageable
            if len(all_covered_claims) > 150:
                all_covered_claims[:] = all_covered_claims[-150:]

        # FIX-C2: Pass summaries of ALL previous sections, not just the last one
        if drafts:
            prev_summaries = []
            for d in drafts:
                # Truncate each section summary to ~200 chars for token efficiency
                summary_text = d.content[:200].rsplit(" ", 1)[0] + "..."
                prev_summaries.append(f"- '{d.title}': {summary_text}")
            # Cap at ~2000 chars total to keep token cost manageable
            combined = "\n".join(prev_summaries)
            if len(combined) > 2000:
                combined = combined[:2000] + "\n..."
            prev_summary = f"Previously written sections (do NOT repeat their facts or claims):\n{combined}"

    # SF-33: Minimum sections gate — warn if too few sections were written
    if len(sorted_sections) > 0 and len(drafts) < len(sorted_sections) * 0.6:
        logger.error(
            "[polaris graph] Only %d/%d sections written (%.0f%%) — "
            "insufficient for a complete report",
            len(drafts),
            len(sorted_sections),
            (len(drafts) / len(sorted_sections)) * 100,
        )

    logger.info(
        "[polaris graph] Wrote %d/%d sections",
        len(drafts),
        len(sorted_sections),
    )

    return drafts, section_evidence_map


async def expand_thin_sections(
    client: OpenRouterClient,
    thin_sections: list[ReportSection],
    outline: ReportOutline,
    evidence: list[EvidencePiece],
    query: str,
    target_expansion: int = 300,
) -> list[SectionDraft]:
    """
    FIX-310: Expand thin sections by adding content from unused evidence.

    For each thin section, builds a prompt with existing content + evidence
    assigned to that section, asking the LLM to expand with ~300 additional words.

    This is NOT a re-synthesis. Content is only added, never removed.
    Returns updated SectionDraft objects for the expanded sections.
    """
    # Build evidence lookup for efficient filtering
    evidence_map = {e.get("evidence_id", ""): e for e in evidence}

    # Find which evidence IDs are already used across the report
    used_evidence_ids: set[str] = set()
    for s in thin_sections:
        used_evidence_ids.update(s.get("evidence_ids", []))

    expanded_drafts: list[SectionDraft] = []

    for section in thin_sections:
        section_id = section["section_id"]
        existing_content = section["content"]
        existing_words = section["word_count"]

        # Find evidence assigned to this section from the outline
        outline_section = None
        for os_item in outline.sections:
            if os_item.section_id == section_id:
                outline_section = os_item
                break

        if not outline_section:
            continue

        # Get evidence for this section, prioritizing unused pieces
        section_evidence = [
            evidence_map[eid]
            for eid in outline_section.evidence_ids
            if eid in evidence_map
        ]

        # Also find unused evidence from the same cluster/category
        unused_evidence = [
            e for e in evidence
            if e.get("evidence_id") not in used_evidence_ids
            and e.get("relevance_score", 0) >= 0.3
        ]
        # Add top unused evidence (sorted by relevance)
        unused_evidence.sort(key=lambda e: e.get("relevance_score", 0), reverse=True)
        additional = unused_evidence[:10]  # Cap at 10 extra pieces

        all_section_evidence = section_evidence + additional
        # FIX-C6: Guard against empty evidence in expansion
        if not all_section_evidence:
            logger.warning(
                "[polaris graph] FIX-C6: Section '%s' has no evidence for expansion, skipping",
                section.get("title", "?"),
            )
            continue
        evidence_text = _format_evidence_for_writing(all_section_evidence)

        prompt = f"""You are expanding an existing report section with additional detail.

Report section title: {section["title"]}
Research question: {query}

EXISTING CONTENT (DO NOT MODIFY OR REMOVE ANY OF THIS):
---
{existing_content}
---

Additional evidence available for expansion:
{evidence_text}

TASK: Write {target_expansion} additional words to ADD to the end of the existing content above.
Do NOT repeat or rewrite any existing content. Only write NEW paragraphs that expand on the topic.
Every factual claim MUST include a [CITE:evidence_id] marker.
Use transition phrases to connect smoothly to the existing content.
Write in third person, academic register."""

        _exp_n_evidence = len(all_section_evidence)
        _exp_suggested_words = min(200 + _exp_n_evidence * 80, 2000)
        system = SECTION_SYSTEM_PROMPT.format(
            n_evidence=_exp_n_evidence,
            suggested_words=_exp_suggested_words,
        )

        try:
            response = await client.generate(
                prompt=prompt,
                system=system,
                max_tokens=PG_SECTION_CONTINUATION_MAX_TOKENS,  # FIX-C5
                temperature=0.7,
            )
            new_content = response.content.strip()

            if not new_content or len(new_content.split()) < 30:
                logger.warning(
                    "[polaris graph] FIX-310: Expansion too short for '%s' (%d words)",
                    section["title"],
                    len(new_content.split()) if new_content else 0,
                )
                continue

            # Scrub any CoT leakage
            new_content = _scrub_cot(new_content)
            new_content = _clean_artifacts(new_content, section_titles=[section.get("title", "")])  # FIX-059-C + FIX-060-E
            new_content = _limit_transitions(new_content)  # FIX-059-K
            new_content = _break_long_paragraphs(new_content)  # FIX-059-L

            # FIX-059-I (H-05): Lightweight hedging enforcement on expansion content.
            # write_section() enforces hedging via LLM revision but expansion skips it.
            # Apply regex-based reduction: replace weak hedges with definitive language
            # when the sentence has a citation (evidence-backed = no need to hedge).
            _hedge_in_cited = re.compile(
                r'\b(may|might|could|potentially)\b(?=[^.]*\[CITE:)',
                re.IGNORECASE,
            )
            hedge_replacements = {
                "may": "", "might": "", "could": "can",
                "potentially": "",
            }
            def _replace_hedge(m):
                word = m.group(1).lower()
                return hedge_replacements.get(word, m.group(1))
            hedged_content = _hedge_in_cited.sub(_replace_hedge, new_content)
            if hedged_content != new_content:
                hedge_count = len(_hedge_in_cited.findall(new_content))
                logger.debug(
                    "[polaris graph] FIX-059-I: Removed %d hedging words from "
                    "cited claims in expansion of '%s'",
                    hedge_count, section["title"][:40],
                )
                new_content = hedged_content

            # Combine existing + new content
            combined = existing_content.rstrip() + "\n\n" + new_content

            # Extract claims from new content
            claims = [
                line.strip()
                for line in new_content.split(".")
                if "[CITE:" in line and len(line.strip()) > 20
            ]

            # FIX-059-I (H-04): Parse new CITE markers from expansion content
            # and merge into evidence_ids so downstream audit sees all cited evidence
            existing_eids = set(section.get("evidence_ids", []))
            new_cite_ids = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', new_content))
            merged_eids = list(existing_eids | new_cite_ids)
            if new_cite_ids - existing_eids:
                logger.debug(
                    "[polaris graph] FIX-059-I: Expansion added %d new evidence_ids "
                    "to section '%s'",
                    len(new_cite_ids - existing_eids),
                    section["title"][:40],
                )

            expanded = SectionDraft(
                section_id=section_id,
                title=section["title"],
                content=combined,
                claims_made=claims[:50],
                evidence_ids=merged_eids,  # FIX-059-I: Merged existing + new
            )

            new_word_count = len(combined.split())
            logger.info(
                "[polaris graph] FIX-310: Expanded '%s': %d -> %d words (+%d)",
                section["title"],
                existing_words,
                new_word_count,
                new_word_count - existing_words,
            )

            # OBS-6: Trace section expansion
            tracer = get_tracer()
            if tracer:
                tracer.llm_call(
                    "synthesize", "section_expand",
                    section_id=section_id,
                    original_words=existing_words,
                    expanded_words=new_word_count,
                    added_words=new_word_count - existing_words,
                    title=section["title"],
                    content=combined[:8000],
                    model=client.model,
                )

            expanded_drafts.append(expanded)

        except Exception as exc:
            logger.error(
                "[polaris graph] FIX-310: Failed to expand '%s': %s",
                section["title"],
                str(exc)[:200],
            )

    return expanded_drafts


async def revise_section(
    client: OpenRouterClient,
    draft: SectionDraft,
    evidence: list[EvidencePiece],
    query: str,
    report_title: str,
) -> SectionDraft:
    """FIX-S1: Revise a section for quality: strengthen arguments, improve sourcing,
    fix logical flow. Content can be rewritten but core findings must be preserved."""

    # Extract cited evidence IDs from the draft content
    cited_ids = set(re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", draft.content))
    section_evidence = [
        e for e in evidence if e.get("evidence_id") in cited_ids
    ]
    # Also include nearby high-relevance evidence not yet cited
    uncited_high = [
        e for e in evidence
        if e.get("evidence_id") not in cited_ids
        and e.get("relevance_score", 0) >= 0.5
        and e.get("quality_tier") in ("GOLD", "SILVER")
    ][:10]
    all_evidence = section_evidence + uncited_high

    evidence_text = _format_evidence_for_writing(all_evidence)
    draft_word_count = len(draft.content.split())

    prompt = f"""You are a senior research editor revising a report section.

Report title: {report_title}
Research question: {query}
Section title: {draft.title}

CURRENT DRAFT:
{draft.content}

AVAILABLE EVIDENCE (you may cite additional pieces not yet used):
{evidence_text}

REVISION INSTRUCTIONS:
1. Strengthen weak arguments -- every claim must have clear evidence support.
2. Remove redundant or tangential sentences that dilute the section's focus.
3. Ensure logical flow: each paragraph should build on the previous one.
4. Use precise academic language. Replace vague hedging with specific claims.
5. Ensure EVERY factual claim has a [CITE:evidence_id] marker.
6. Preserve the section's core findings and conclusions.
7. Target {draft_word_count} words (same length, better quality).
8. Use transition words SPARINGLY — no more than 1 per 200 words. Vary transitions and do NOT start consecutive sentences with them.
9. Do NOT include any chain-of-thought, reasoning, or planning text."""

    _rev_n_evidence = len(all_evidence)
    _rev_suggested_words = min(200 + _rev_n_evidence * 80, 2000)
    system = SECTION_SYSTEM_PROMPT.format(
        n_evidence=_rev_n_evidence,
        suggested_words=_rev_suggested_words,
    )

    try:
        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=PG_SECTION_WRITER_MAX_TOKENS,
            temperature=0.5,  # Lower temp for revision (more faithful to original)
        )
        revised = response.content.strip()
        revised = _scrub_cot(revised)

        # Safety: only accept revision if it's at least 70% of original length
        revised_words = len(revised.split())
        if revised_words < draft_word_count * 0.7:
            logger.warning(
                "[polaris graph] FIX-S1: Revision of '%s' too short "
                "(%.0f%% of original), keeping draft",
                draft.title,
                (revised_words / max(draft_word_count, 1)) * 100,
            )
            return draft

        claims = [
            line.strip()
            for line in revised.split(".")
            if "[CITE:" in line and len(line.strip()) > 20
        ]

        logger.info(
            "[polaris graph] FIX-S1: Revised '%s': %d -> %d words, %d claims",
            draft.title,
            draft_word_count,
            revised_words,
            len(claims),
        )

        return SectionDraft(
            section_id=draft.section_id,
            title=draft.title,
            content=revised,
            claims_made=claims[:50],
            evidence_ids=draft.evidence_ids,  # FIX-039: Preserve across revision
        )

    except Exception as exc:
        logger.error(
            "[polaris graph] FIX-S1: Revision failed for '%s': %s — keeping draft",
            draft.title,
            str(exc)[:200],
        )
        return draft


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_evidence_summary(evidence: list[EvidencePiece]) -> str:
    """Format evidence for the outliner (compact)."""
    lines = []
    for e in evidence[:200]:  # Cap at 200 for prompt length
        quality = e.get("quality_tier", "?")
        relevance = e.get("relevance_score", 0)
        lines.append(
            f"- [{e.get('evidence_id', '?')}] ({quality}, rel={relevance:.2f}) "
            f"{e.get('statement', '')[:150]}"
        )
    return "\n".join(lines)


def _format_cluster_detail(
    clusters: list[dict], evidence: list[EvidencePiece]
) -> str:
    """FIX-QM27: Format clusters with evidence summaries for compact outline prompt.

    Instead of listing all 600+ evidence pieces individually (~40K chars),
    groups them by cluster with truncated statements (~5-8K chars total).
    This keeps the outline prompt within the model's effective output budget.
    """
    # Build evidence lookup
    ev_map: dict[str, EvidencePiece] = {
        e.get("evidence_id", ""): e for e in evidence
    }

    parts = []
    assigned_ids: set[str] = set()

    # FIX-2: Cap per-cluster evidence display to keep outline prompt compact.
    # With 15 clusters x 850 evidence, old limit of 40/cluster = 30K+ chars
    # causing 3x timeout + fallback. Now configurable, default 10.
    max_outline_ev = int(os.getenv("PG_OUTLINE_EVIDENCE_PER_CLUSTER", "10"))

    for i, c in enumerate(clusters, 1):
        theme = c.get("theme", "Unknown")
        desc = c.get("description", "")[:200]
        ev_ids = c.get("evidence_ids", [])
        strength = c.get("strength", "moderate")

        parts.append(
            f"## Cluster {i}: {theme} ({len(ev_ids)} evidence, strength={strength})"
        )
        parts.append(f"Description: {desc}")

        # FIX-2: Show only top evidence per cluster, prioritizing GOLD/SILVER
        # Sort evidence IDs by quality tier (GOLD first, then SILVER, then BRONZE)
        tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
        sorted_ev_ids = sorted(
            ev_ids,
            key=lambda eid: tier_order.get(
                ev_map.get(eid, {}).get("quality_tier", "BRONZE"), 2
            ),
        )

        shown = 0
        for eid in sorted_ev_ids:
            if shown >= max_outline_ev:
                break
            ev = ev_map.get(eid)
            if ev:
                quality = ev.get("quality_tier", "?")
                stmt = ev.get("statement", "")[:120]
                parts.append(f"  - [{eid}] ({quality}) {stmt}")
                assigned_ids.add(eid)
                shown += 1
        if len(ev_ids) > max_outline_ev:
            parts.append(f"  ... +{len(ev_ids) - shown} more evidence assigned to this cluster")
            assigned_ids.update(ev_ids[max_outline_ev:])

        parts.append("")

    # Show unassigned evidence (not in any cluster) — also capped
    max_unassigned_display = max_outline_ev  # FIX-2: Same cap for unassigned
    unassigned = [
        e for e in evidence
        if e.get("evidence_id", "") not in assigned_ids
    ]
    if unassigned:
        parts.append(f"## Unassigned evidence ({len(unassigned)} pieces)")
        for e in unassigned[:max_unassigned_display]:
            eid = e.get("evidence_id", "?")
            quality = e.get("quality_tier", "?")
            stmt = e.get("statement", "")[:120]
            parts.append(f"  - [{eid}] ({quality}) {stmt}")
        if len(unassigned) > max_unassigned_display:
            parts.append(f"  ... +{len(unassigned) - max_unassigned_display} more")
        parts.append("")

    return "\n".join(parts)


def _format_cluster_summary(clusters: list[dict]) -> str:
    """FIX-OUTLINE: Format clusters as numbered summaries for the outline prompt (~2KB).

    Includes cluster numbers so the LLM can reference which clusters
    each section should draw from (e.g., "Covers clusters 1, 3, 7").
    """
    lines = []
    for i, c in enumerate(clusters, 1):
        n_evidence = len(c.get("evidence_ids", []))
        strength = c.get("strength", "moderate")
        lines.append(
            f"Cluster {i}: '{c.get('theme', '?')}' "
            f"({n_evidence} evidence, strength={strength})\n"
            f"  {c.get('description', '')[:200]}"
        )
    return "\n".join(lines) if lines else "No clusters available."


_COT_LINE_PATTERNS = [
    # Lines starting with planning/reasoning markers
    re.compile(r"(?i)^(let me|i need to|i should|i will|the user wants|thinking).*$", re.MULTILINE),
    re.compile(r"(?i)^(word count|checking|verifying|expanding|let's|ok,|alright,).*$", re.MULTILINE),
    re.compile(r"(?i)^(draft \d|attempt \d|revision|re-?writing|here'?s my).*$", re.MULTILINE),
    re.compile(r"(?i)^(wait,|hmm|note:|caveat:|actually,).*$", re.MULTILINE),
    # Lines containing meta-commentary about writing the section
    re.compile(r"^.*(?:word count|check:? need|that's about \d+ words|approximately \d+ words).*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*(?:need to expand|need a bit more|need more on).*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*(?:this looks to be around|looks to be about).*$", re.MULTILINE | re.IGNORECASE),
    # XML-style tags
    re.compile(r"<think>.*?</think>", re.DOTALL),
    re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL),
    # --- Enhanced patterns for misrouted reasoning_content ---
    # Numbered instructions (echoed system prompt)
    re.compile(r"^\d+\.\s+(?:Write|Every|Use|Include|Target|Maintain|Connect|Do NOT|No chain|Keep)\b.*$", re.MULTILINE | re.IGNORECASE),
    # Evidence ID listings (bullet points with [ev_xxx])
    re.compile(r"^-\s+.*\[ev_[a-f0-9]+.*$", re.MULTILINE),
    # Per-paragraph word count tracking ("Para 1: ~40 words")
    re.compile(r"^(?:Paragraph|Para)\s+\d+:.*\d+\s+words.*$", re.MULTILINE | re.IGNORECASE),
    # Planning headers
    re.compile(r"^(?:Structure of the section|Available evidence|Key requirements|Output format):?.*$", re.MULTILINE | re.IGNORECASE),
    # Planning bullet points
    re.compile(r"^-\s+(?:Not |Keep |Ensure |Make sure|Don't ).*$", re.MULTILINE),
]


def _deduplicate_drafts(text: str) -> str:
    """Detect and remove duplicate drafts in misrouted reasoning_content.

    When reasoning_content is used as content, the LLM often writes
    Draft 1 -> word counts -> Draft 2 (improved). Both drafts share
    near-identical opening sentences. Keep only the LAST draft.
    """
    paragraphs = text.split("\n\n")
    if len(paragraphs) < 4:
        return text

    # Extract first ~60 chars of each paragraph (normalized)
    def _sig(para: str) -> str:
        return re.sub(r"\s+", " ", para.strip()[:60]).lower()

    # Find paragraphs with matching signatures
    sigs: dict[str, list[int]] = {}
    for i, p in enumerate(paragraphs):
        sig = _sig(p)
        if len(sig) < 30:
            continue
        if sig in sigs:
            sigs[sig].append(i)
        else:
            sigs[sig] = [i]

    # If any paragraph appears twice AND they're separated by other content,
    # we likely have multiple drafts. Require the duplicates to be separated
    # by at least 1 intervening paragraph.
    dup_with_gap = False
    for indices in sigs.values():
        if len(indices) > 1 and (indices[-1] - indices[0]) >= 2:
            dup_with_gap = True
            break

    if not dup_with_gap:
        return text

    # Find the boundary: last occurrence of the first duplicated paragraph
    first_dup_sig = None
    for sig, indices in sigs.items():
        if len(indices) > 1:
            first_dup_sig = sig
            break

    if first_dup_sig is None:
        return text

    last_start = sigs[first_dup_sig][-1]

    # Keep everything from the last draft onwards
    deduped = "\n\n".join(paragraphs[last_start:])
    removed_words = len(text.split()) - len(deduped.split())

    if removed_words > 0:
        logger.info(
            "[polaris graph] Draft dedup: removed %d words (earlier draft)",
            removed_words,
        )

    return deduped


def _scrub_cot(text: str) -> str:
    """Remove chain-of-thought leakage from section content."""
    original_len = len(text.split())
    cleaned = text

    # Step 1: Remove duplicate drafts (must come BEFORE line-level scrubbing)
    cleaned = _deduplicate_drafts(cleaned)

    # Step 2: Apply line-level CoT patterns
    for pattern in _COT_LINE_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Remove excessive blank lines created by scrubbing
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    scrubbed_len = len(cleaned.split())
    if scrubbed_len < original_len * 0.3:
        # If scrubbing removed >70% of content, something went wrong —
        # return original to avoid destroying the section
        logger.warning(
            "[polaris graph] CoT scrub removed >70%% (%d->%d words), keeping original",
            original_len,
            scrubbed_len,
        )
        return text

    if scrubbed_len < original_len:
        logger.info(
            "[polaris graph] CoT scrub: %d -> %d words (-%d)",
            original_len,
            scrubbed_len,
            original_len - scrubbed_len,
        )

    return cleaned


def _clean_artifacts(text: str, section_titles: list[str] | None = None) -> str:
    """FIX-059-C: Remove LLM artifacts that leak through generation and post-processing.

    Handles:
    1. Orphan transition fragments (e.g. "Additionally,." left after citation cleanup)
    2. [CROSS-REF:...] markers not resolved during assembly
    3. Section [X]/[Y]/[Z] placeholder references
    4. Title echo (section body starting with its own title)
    5. Markdown headers from expansion output (H-06)
    6. Double spaces and empty lines

    Args:
        text: The section or report text to clean.
        section_titles: Optional list of section titles to detect title echo.

    Returns:
        Cleaned text with artifacts removed.
    """
    if not text or not text.strip():
        return text

    cleaned = text

    # 1. Strip orphan transition fragments: "Additionally,." or "Moreover."
    #    These arise when _inject_transitions() adds a transition word before
    #    a sentence that is later stripped during citation orphan cleanup,
    #    leaving the transition word dangling with only punctuation.
    cleaned = re.sub(
        r'\b(Additionally|Moreover|Furthermore|In addition|Consequently|'
        r'Specifically|Notably|Importantly|Critically|Similarly|Likewise|'
        r'Conversely)[,.]?\.\s*',
        '',
        cleaned,
    )

    # 2. Strip [CROSS-REF:...] markers
    cleaned = re.sub(r'\[CROSS-REF:[^\]]*\]', '', cleaned)

    # 3. Strip Section [X]/[Y]/[Z] placeholder references and clean up
    #    resulting empty sentences
    cleaned = re.sub(r'(?:Section|section)\s+\[[A-Z]\]', '', cleaned)
    # Clean up sentences that became empty after stripping placeholders
    # e.g. "As discussed in ." -> remove entire empty sentence
    cleaned = re.sub(r'(?<=[.!?])\s+[.!?]', '', cleaned)

    # 4. Remove title echo: if body starts with the exact section title
    if section_titles:
        for title in section_titles:
            if not title:
                continue
            # Case-insensitive match at start of text (with optional markdown header)
            pattern = re.compile(
                r'^(?:#{1,4}\s+)?' + re.escape(title) + r'\s*\n?',
                re.IGNORECASE,
            )
            cleaned = pattern.sub('', cleaned, count=1)

    # 5. Strip markdown headers from expansion output (H-06)
    #    Expansion LLM sometimes outputs "## Subsection Title" headers
    cleaned = re.sub(r'^#{1,4}\s+.*$', '', cleaned, flags=re.MULTILINE)

    # 6. Final cleanup: double spaces, excessive blank lines
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if len(cleaned) < len(text.strip()):
        logger.info(
            "[polaris graph] FIX-059-C: _clean_artifacts() removed %d chars",
            len(text.strip()) - len(cleaned),
        )

    return cleaned



def _limit_hedging(text: str) -> str:
    """FIX-R13: Post-processing enforcement of hedging word limits.

    Prompt instructions alone don't reliably limit hedging. This function
    enforces a hard cap by replacing excess hedging words with confident
    alternatives.
    """
    if not text or not text.strip():
        return text

    max_hedging = int(os.getenv("PG_MAX_HEDGING_PER_SECTION", "8"))

    # Pattern matches common hedging words/phrases
    _hedging_pattern = re.compile(
        r'\b(may|might|potentially|possibly|could|perhaps|appears to|seems to)\b',
        re.IGNORECASE,
    )

    matches = list(_hedging_pattern.finditer(text))
    if len(matches) <= max_hedging:
        return text

    # Keep the first max_hedging instances, remove/replace the rest
    excess = matches[max_hedging:]
    # Process in reverse order to preserve string positions
    result = text
    removed = 0
    for match in reversed(excess):
        word = match.group(0).lower()
        start, end = match.start(), match.end()

        if word in ("potentially", "possibly", "perhaps"):
            # Simply remove: "potentially harmful" -> "harmful"
            # Also remove trailing space
            if end < len(result) and result[end] == ' ':
                result = result[:start] + result[end + 1:]
            else:
                result = result[:start] + result[end:]
            removed += 1
        elif word in ("may", "might"):
            # "may cause" -> "causes" (simplified: just remove "may "/"might ")
            if end < len(result) and result[end] == ' ':
                result = result[:start] + result[end + 1:]
            else:
                result = result[:start] + result[end:]
            removed += 1
        elif word == "could":
            # "could affect" -> "can affect"
            result = result[:start] + "can" + result[end:]
            removed += 1
        elif word in ("appears to", "seems to"):
            # Remove entirely
            if end < len(result) and result[end] == ' ':
                result = result[:start] + result[end + 1:]
            else:
                result = result[:start] + result[end:]
            removed += 1

    # Re-capitalize sentence starts that may have been affected
    result = re.sub(r'(\. +)([a-z])', lambda m: m.group(1) + m.group(2).upper(), result)
    # Clean double spaces
    result = re.sub(r'  +', ' ', result)

    if removed > 0:
        logger.info(
            "[polaris graph] FIX-R13: Removed/replaced %d/%d excess hedging words "
            "(max %d per section)",
            removed, len(matches), max_hedging,
        )

    return result


def _limit_transitions(text: str) -> str:
    """FIX-059-K: Limit transition word density to prevent over-saturation.

    LLM writes transitions + post-processor adds more, causing 1 transition
    every 81 words (129 in 10,500 words). This function enforces a cap of
    ~60 per 10,000 words by removing transitions from middle paragraphs
    when density exceeds 1 per 150 words.

    Args:
        text: Section content text.

    Returns:
        Text with transition density capped.
    """
    if not text or not text.strip():
        return text

    # LAW VI: Thresholds from environment
    max_density = float(os.getenv("PG_TRANSITION_MAX_DENSITY", "150"))  # 1 per N words
    cap_per_10k = int(os.getenv("PG_TRANSITION_CAP_PER_10K", "60"))

    _transition_words = [
        "Additionally", "Moreover", "Furthermore", "In addition",
        "Consequently", "Specifically", "Notably", "Importantly",
        "Similarly", "Likewise", "Conversely", "However",
        "Nevertheless", "Nonetheless",
    ]
    _transition_pattern = re.compile(
        r"\b(" + "|".join(_transition_words) + r")\b",
        re.IGNORECASE,
    )

    word_count = len(text.split())
    if word_count == 0:
        return text

    all_matches = list(_transition_pattern.finditer(text))
    total_transitions = len(all_matches)

    if total_transitions == 0:
        return text

    # Check if density exceeds threshold
    density_words_per_transition = word_count / total_transitions
    scaled_cap = max(1, int(cap_per_10k * word_count / 10000))

    if density_words_per_transition >= max_density and total_transitions <= scaled_cap:
        return text  # Already within limits

    # Split into paragraphs; keep first and last paragraph intact
    paragraphs = text.split("\n\n")
    if len(paragraphs) <= 2:
        return text  # Only first/last -- nothing to trim

    target_removals = max(0, total_transitions - scaled_cap)
    if target_removals == 0:
        return text

    removed = 0
    result_paragraphs = []
    for idx, para in enumerate(paragraphs):
        # Keep first and last paragraphs unchanged
        if idx == 0 or idx == len(paragraphs) - 1:
            result_paragraphs.append(para)
            continue

        if removed >= target_removals:
            result_paragraphs.append(para)
            continue

        # Remove transition words at sentence starts in middle paragraphs
        def _strip_transition(match, _para=para):
            nonlocal removed
            if removed >= target_removals:
                return match.group(0)
            # Only strip if transition starts a sentence (preceded by '. ' or start-of-para)
            start = match.start()
            pre = _para[:start].rstrip()
            if not pre or pre.endswith(".") or pre.endswith("?") or pre.endswith("!"):
                removed += 1
                return ""
            return match.group(0)

        cleaned_para = _transition_pattern.sub(_strip_transition, para)
        # Clean up artifacts: leading comma/space, double spaces
        cleaned_para = re.sub(r"^[,\s]+", "", cleaned_para)
        cleaned_para = re.sub(r"(?<=\.)\s+[,]\s+", " ", cleaned_para)
        cleaned_para = re.sub(r"  +", " ", cleaned_para)
        # Re-capitalize first letter after removal if needed
        if cleaned_para and cleaned_para[0].islower():
            cleaned_para = cleaned_para[0].upper() + cleaned_para[1:]
        result_paragraphs.append(cleaned_para)

    result = "\n\n".join(result_paragraphs)

    # FIX-R3: Capitalize sentence starts after transition removal
    # Split by paragraph, check each paragraph's first char
    _r3_paragraphs = result.split("\n\n")
    _r3_fixed = []
    for _r3_p in _r3_paragraphs:
        _r3_p = _r3_p.strip()
        if _r3_p and _r3_p[0].islower():
            _r3_p = _r3_p[0].upper() + _r3_p[1:]
        # Also fix sentence starts within paragraph (after ". ")
        _r3_p = re.sub(r'(\.\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), _r3_p)
        _r3_fixed.append(_r3_p)
    result = "\n\n".join(_r3_fixed)

    if removed > 0:
        logger.info(
            "[polaris graph] FIX-059-K: Removed %d/%d transition words "
            "(density: 1/%.0f words -> 1/%.0f words, cap: %d per 10K)",
            removed,
            total_transitions,
            density_words_per_transition,
            word_count / max(total_transitions - removed, 1),
            scaled_cap,
        )

    return result


def _break_long_paragraphs(text: str) -> str:
    """FIX-059-L: Break excessively long paragraphs for readability.

    Splits any paragraph exceeding 300 words at the nearest sentence boundary
    after approximately 250 words. Uses regex-based sentence splitting to
    avoid adding new dependencies.

    Args:
        text: Section content text.

    Returns:
        Text with long paragraphs broken into smaller ones.
    """
    if not text or not text.strip():
        return text

    # LAW VI: Threshold from environment
    max_paragraph_words = int(os.getenv("PG_MAX_PARAGRAPH_WORDS", "300"))
    split_target_words = int(os.getenv("PG_PARAGRAPH_SPLIT_TARGET", "250"))

    paragraphs = text.split("\n\n")
    result_paragraphs = []
    splits_made = 0

    for para in paragraphs:
        words = para.split()
        if len(words) <= max_paragraph_words:
            result_paragraphs.append(para)
            continue

        # Split at sentence boundaries using regex
        # Handles abbreviations like U.S., Dr., Prof., e.g., i.e. by requiring
        # the period to be followed by a space and an uppercase letter or [
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z\[])', para)

        if len(sentences) <= 1:
            result_paragraphs.append(para)
            continue

        current_chunk: list[str] = []
        current_word_count = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if current_word_count + sent_words > split_target_words and current_chunk:
                result_paragraphs.append(" ".join(current_chunk))
                current_chunk = [sent]
                current_word_count = sent_words
                splits_made += 1
            else:
                current_chunk.append(sent)
                current_word_count += sent_words

        if current_chunk:
            result_paragraphs.append(" ".join(current_chunk))

        # FIX-R5: Clause-level split for chunks still exceeding 300 words
        # After sentence splitting, some chunks may still be too long
        # (e.g., single very long sentences). Split at clause boundaries.
        _r5_final = []
        for _r5_chunk in result_paragraphs[len(result_paragraphs) - splits_made - 1:]:
            if len(_r5_chunk.split()) > max_paragraph_words:
                _r5_clauses = re.split(
                    r'(?<=; )(?=[A-Z])|(?<=, which )|(?<=, and )(?=[A-Z])|(?<=, but )(?=[A-Z])',
                    _r5_chunk,
                )
                if len(_r5_clauses) > 1:
                    _r5_sub_chunk: list[str] = []
                    _r5_sub_wc = 0
                    for _r5_cl in _r5_clauses:
                        _r5_cl_wc = len(_r5_cl.split())
                        if _r5_sub_wc + _r5_cl_wc > split_target_words and _r5_sub_chunk:
                            _r5_final.append("".join(_r5_sub_chunk))
                            _r5_sub_chunk = [_r5_cl]
                            _r5_sub_wc = _r5_cl_wc
                            splits_made += 1
                        else:
                            _r5_sub_chunk.append(_r5_cl)
                            _r5_sub_wc += _r5_cl_wc
                    if _r5_sub_chunk:
                        _r5_final.append("".join(_r5_sub_chunk))
                else:
                    _r5_final.append(_r5_chunk)
            else:
                _r5_final.append(_r5_chunk)
        # Replace the tail of result_paragraphs with clause-split versions
        if _r5_final:
            _r5_start = len(result_paragraphs) - splits_made - 1
            if _r5_start >= 0:
                result_paragraphs = result_paragraphs[:_r5_start] + _r5_final


    result = "\n\n".join(result_paragraphs)

    if splits_made > 0:
        logger.info(
            "[polaris graph] FIX-059-L: Broke %d long paragraph(s) at sentence boundaries",
            splits_made,
        )

    return result


def _format_evidence_for_writing(evidence: list[EvidencePiece]) -> str:
    """Format evidence for section writing (detailed).

    FIX-5: Sorts evidence by tier (GOLD first) then relevance DESC so the
    LLM sees the strongest evidence first and prioritizes it.
    FIX-MP4: Adds [VERIFIED]/[UNVERIFIED] tags based on verification status.
    FIX-MP16: Includes direct_quote to give LLM actual source text for
    tighter claim-evidence coupling (ReClaim-lite approach).
    """
    # FIX-5: Sort by quality tier (GOLD=0, SILVER=1, BRONZE=2) then relevance DESC
    _tier_rank = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
    sorted_evidence = sorted(
        evidence,
        key=lambda e: (
            _tier_rank.get(e.get("quality_tier", "BRONZE"), 2),
            -(e.get("relevance_score", 0.0)),
        ),
    )

    lines = []
    _current_tier = None
    for e in sorted_evidence:
        # FIX-5: Add tier header when tier changes
        _tier = e.get("quality_tier", "BRONZE")
        if _tier != _current_tier:
            _current_tier = _tier
            lines.append(f"--- {_tier} EVIDENCE (sorted by relevance) ---")

        # FIX-MP4: Verification status tag
        verification_method = e.get("verification_method", "")
        if verification_method == "api_error" or verification_method == "":
            verify_tag = "[UNVERIFIED]"
        elif e.get("is_faithful") is True:
            verify_tag = "[VERIFIED]"
        elif e.get("is_faithful") is False:
            verify_tag = "[UNVERIFIED]"
        else:
            verify_tag = "[UNVERIFIED]"

        # FIX-MP16: Include full direct_quote for source grounding
        quote = e.get("direct_quote", "")
        quote_line = f'  Direct quote: "{quote[:500]}"' if quote else ""

        lines.append(
            f"Evidence ID: {e.get('evidence_id', '?')} {verify_tag}\n"
            f"  Statement: {e.get('statement', '')}\n"
            f"{quote_line}\n"
            f"  Source: {e.get('source_title', '')} ({e.get('year', '?')})\n"
            f"  URL: {e.get('source_url', '')}\n"
            f"  Quality: {e.get('quality_tier', '?')} | Relevance: {e.get('relevance_score', 0):.2f}\n"
        )
    return "\n".join(lines) if lines else "No evidence assigned to this section."
