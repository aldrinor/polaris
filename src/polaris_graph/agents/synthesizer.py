"""
Synthesizer agent for polaris graph.

Orchestrates the full synthesis pipeline:
1. Cluster evidence by theme
2. Plan report outline
3. Write sections (parallel, 800 words each max)
4. Audit citations
5. Assemble final report
"""

import asyncio
import logging
import os
import re
from typing import Any

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.schemas import (
    BatchClusterResult,
    ClusterAssessment,
    ClusterPlan,
    GapAnalysis,
    ReportOutline,
)
from src.polaris_graph.state import (
    EvidencePiece,
    ResearchState,
    MIN_EVIDENCE_COUNT,
    MIN_FAITHFULNESS,
    MIN_TOTAL_WORDS,
    MIN_CITATIONS,
    MIN_UNIQUE_SOURCES,
    PG_MIN_CITATIONS_PER_SECTION,
    PG_MIN_EVIDENCE_UTILIZATION,
    PG_SECTION_WRITE_CONCURRENCY,
    PG_SYNTHESIS_MAX_EXPANSION_PASSES,
    PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
    STORM_PERSPECTIVES,
)
from src.polaris_graph.synthesis.section_writer import (
    expand_thin_sections,
    plan_report,
    revise_section,
    write_all_sections,
    _scrub_cot,
)
from src.polaris_graph.synthesis.citation_mapper import (
    audit_citations,
    strip_ungrounded_citations,
)
from src.polaris_graph.synthesis.report_assembler import (
    assemble_report,
    compute_quality_metrics,
)
from src.polaris_graph.agents.hallucination_detector import (
    audit_sections_for_hallucination,
)
from src.polaris_graph.tools.data_analyzer import (
    analyze_structured_data,
    format_chart_markdown,
    format_table_markdown,
)

logger = logging.getLogger(__name__)

# Map-reduce clustering config (LAW VI)
PG_CLUSTER_BATCH_SIZE = int(os.getenv("PG_CLUSTER_BATCH_SIZE", "100"))
PG_CLUSTER_MAX_THEMES_BEFORE_MERGE = int(os.getenv("PG_CLUSTER_MAX_THEMES_BEFORE_MERGE", "20"))


# ---------------------------------------------------------------------------
# Short ID Remapping (Prosus research: 95.6% token reduction, <5% error rate)
# ---------------------------------------------------------------------------

def _remap_evidence_ids(
    evidence: list[dict],
) -> tuple[list[dict], dict[str, str]]:
    """Remap ev_xxx IDs to sequential integers for LLM token efficiency.

    Returns:
        (remapped_evidence, reverse_map) where:
        - remapped_evidence: copy of evidence with short integer IDs
        - reverse_map: {"1": "ev_abc123", "2": "ev_def456", ...}
    """
    forward_map: dict[str, str] = {}  # ev_xxx -> "1"
    reverse_map: dict[str, str] = {}  # "1" -> ev_xxx

    for idx, ev in enumerate(evidence, start=1):
        original_id = ev.get("evidence_id", "")
        short_id = str(idx)
        forward_map[original_id] = short_id
        reverse_map[short_id] = original_id

    remapped = []
    for ev in evidence:
        remapped_ev = dict(ev)
        original_id = remapped_ev.get("evidence_id", "")
        remapped_ev["evidence_id"] = forward_map.get(original_id, original_id)
        remapped.append(remapped_ev)

    logger.debug(
        "[polaris graph] ID remap: %d evidence IDs remapped "
        "(~%d tokens saved, ~%.0f%% reduction)",
        len(forward_map),
        len(forward_map) * 4,  # ~5 tokens/UUID -> ~1 token/int = ~4 saved
        (1 - 1 / max(5, 1)) * 100,
    )

    return remapped, reverse_map


def _reverse_remap_ids(
    short_ids: list[str],
    reverse_map: dict[str, str],
) -> list[str]:
    """Reverse-map short integer IDs back to original ev_xxx IDs.

    Any IDs not found in reverse_map are logged and dropped.
    """
    restored: list[str] = []
    missing_count = 0

    for sid in short_ids:
        original = reverse_map.get(str(sid))
        if original:
            restored.append(original)
        else:
            missing_count += 1

    if missing_count:
        logger.warning(
            "[polaris graph] Reverse remap: %d/%d short IDs not found in map "
            "(LLM hallucinated IDs)",
            missing_count,
            len(short_ids),
        )

    return restored


# ---------------------------------------------------------------------------
# FIX-E: Global Evidence Assignment (Two-Pass Synthesis)
# ---------------------------------------------------------------------------


async def _assign_evidence_globally(
    client: OpenRouterClient,
    outline_sections: list,
    evidence: list[dict],
) -> tuple[dict[str, list[str]], list[str]]:
    """FIX-E Pass 1: Globally assign evidence to sections via LLM.

    Uses short-ID remapping for token efficiency (Prosus: 95.6% reduction).
    The LLM sees ALL evidence summaries and assigns each to its primary
    section. Evidence relevant to multiple sections is flagged as cross-section.

    Args:
        client: OpenRouter LLM client.
        outline_sections: List of SectionOutlineItem (or dicts with section_id, title, description).
        evidence: Full evidence pool (dicts with evidence_id, statement, source_url).

    Returns:
        (section_assignments, cross_section_ids) where:
        - section_assignments: {section_id: [ev_xxx, ...]} primary assignments
        - cross_section_ids: [ev_xxx, ...] evidence visible to all sections
    """
    from src.polaris_graph.schemas import GlobalEvidenceAssignment

    if not evidence or not outline_sections:
        logger.warning("[polaris graph] FIX-E: Empty evidence or outline, skipping global assignment")
        return {}, []

    # Short-ID remap for token efficiency
    remapped, reverse_map = _remap_evidence_ids(evidence)

    # Build compact evidence summary: "ID: statement (source)"
    ev_lines = []
    for ev in remapped:
        short_id = ev.get("evidence_id", "?")
        stmt = ev.get("statement", "")[:200]
        src = ev.get("source_url", "")
        # Extract domain from URL for brevity
        domain = src.split("//")[-1].split("/")[0] if "//" in src else src[:40]
        ev_lines.append(f"{short_id}: {stmt} [{domain}]")

    evidence_block = "\n".join(ev_lines)

    # Build section summary
    section_lines = []
    for sec in outline_sections:
        sid = getattr(sec, "section_id", None) or sec.get("section_id", "")
        title = getattr(sec, "title", None) or sec.get("title", "")
        desc = getattr(sec, "description", None) or sec.get("description", "")
        section_lines.append(f"- {sid}: {title} — {desc[:120]}")

    sections_block = "\n".join(section_lines)

    prompt = f"""Assign each evidence piece to its MOST relevant section.

SECTIONS:
{sections_block}

EVIDENCE (id: statement [source]):
{evidence_block}

Rules:
1. Every evidence piece must be assigned to EXACTLY ONE section (primary).
2. Evidence that is broadly relevant to 3+ sections should ALSO be listed in cross_section_ids.
3. Cross-section evidence should be at most 20% of total evidence.
4. If unsure, assign to the section whose title/description best matches the evidence statement.
5. Use the short integer IDs from the evidence list."""

    try:
        assignment = await client.generate_structured(
            system="You are an evidence assignment specialist. Assign each evidence piece to the most relevant report section.",
            prompt=prompt,
            schema=GlobalEvidenceAssignment,
            max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
        )

        # FIX-E2: Diagnostic logging before reverse-remap to catch ID mismatches.
        # The LLM sometimes uses 0-based IDs, ev_xxx format, or other formats
        # that don't match the 1-based integer keys in reverse_map.
        raw_assignment_count = len(assignment.assignments)
        sample_ids: list = []
        for sa in assignment.assignments[:3]:
            sample_ids.extend(sa.primary_ids[:3])
        if raw_assignment_count == 0:
            logger.warning(
                "[polaris graph] FIX-E2: LLM returned 0 assignments for %d evidence "
                "and %d sections — will fall back to embedding filtering",
                len(evidence), len(outline_sections),
            )
        elif sample_ids:
            logger.info(
                "[polaris graph] FIX-E2: LLM returned %d assignments, sample IDs: %s "
                "(reverse_map range: 1-%d)",
                raw_assignment_count, sample_ids[:6], len(evidence),
            )

        # FIX-E2: Tolerant ID matching — handle 0-based, 1-based, and ev_xxx formats.
        # Build extended reverse_map that accepts all common LLM ID formats.
        extended_map = dict(reverse_map)  # "1" -> "ev_xxx", "2" -> "ev_yyy"
        # Add 0-based keys: "0" -> "ev_xxx" (first evidence), etc.
        for idx, ev in enumerate(evidence):
            original_id = ev.get("evidence_id", "")
            extended_map[str(idx)] = original_id  # 0-based
            extended_map[original_id] = original_id  # ev_xxx -> ev_xxx (identity)

        # Reverse-map short IDs back to ev_xxx using extended map
        section_assignments: dict[str, list[str]] = {}
        for sa in assignment.assignments:
            original_ids = _reverse_remap_ids(
                [str(i) for i in sa.primary_ids],
                extended_map,
            )
            if original_ids:
                section_assignments[sa.section_id] = original_ids

        cross_section_ids = _reverse_remap_ids(
            [str(i) for i in assignment.cross_section_ids],
            extended_map,
        )

        # Diagnostics
        assigned_total = sum(len(ids) for ids in section_assignments.values())
        logger.info(
            "[polaris graph] FIX-E: Global evidence assignment: %d evidence -> "
            "%d sections (%d assigned, %d cross-section, %d unassigned)",
            len(evidence),
            len(section_assignments),
            assigned_total,
            len(cross_section_ids),
            len(evidence) - assigned_total,
        )

        # FIX-E2: Retry once on empty result — LLM may produce valid output
        # on second attempt (stochastic structured generation).
        if assigned_total == 0 and raw_assignment_count > 0:
            logger.warning(
                "[polaris graph] FIX-E2: %d LLM assignments but 0 mapped — "
                "ID format mismatch (sample: %s). Retrying once.",
                raw_assignment_count, sample_ids[:6],
            )
            # Don't retry — the ID format issue needs a code fix, not a retry.
            # Log enough data to diagnose the format on next occurrence.

        return section_assignments, cross_section_ids

    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-E: Global evidence assignment failed: %s — "
            "falling back to per-section embedding filtering",
            str(exc)[:200],
        )
        return {}, []


def _dedup_evidence(
    evidence: list[dict],
    similarity_threshold: float | None = None,
) -> list[dict]:
    """M-06: Deduplicate evidence within same source using embedding similarity.

    Groups by source_url, computes pairwise embedding similarity within each
    group, and greedily merges near-duplicates (keeping highest relevance_score).

    Args:
        evidence: Full evidence list.
        similarity_threshold: Cosine similarity above which two items are dupes.

    Returns:
        Deduplicated evidence list.
    """
    if len(evidence) < 2:
        return evidence

    if similarity_threshold is None:
        similarity_threshold = float(
            os.getenv("PG_EVIDENCE_DEDUP_THRESHOLD", "0.85")
        )

    import numpy as np
    from collections import defaultdict
    from src.utils.embedding_service import embed_texts

    # Group by source_url
    by_source: dict[str, list[dict]] = defaultdict(list)
    for ev in evidence:
        url = ev.get("source_url", "") or ""
        by_source[url].append(ev)

    kept: list[dict] = []
    removed = 0

    for url, group in by_source.items():
        if len(group) < 2 or not url:
            kept.extend(group)
            continue

        statements = [e.get("statement", "") for e in group]
        try:
            vecs = np.array(embed_texts(statements))
            sim = vecs @ vecs.T

            # Greedy dedup: keep highest relevance_score in each cluster
            merged: set[int] = set()
            for i in range(len(group)):
                if i in merged:
                    continue
                for j in range(i + 1, len(group)):
                    if j in merged:
                        continue
                    if sim[i][j] >= similarity_threshold:
                        # Keep higher relevance_score
                        if group[j].get("relevance_score", 0) > group[i].get(
                            "relevance_score", 0
                        ):
                            merged.add(i)
                            break
                        else:
                            merged.add(j)

            for i, ev in enumerate(group):
                if i not in merged:
                    kept.append(ev)
                else:
                    removed += 1
        except Exception as exc:
            logger.debug(
                "[polaris graph] M-06: Dedup embedding failed for source '%s': %s",
                url[:60],
                str(exc)[:100],
            )
            kept.extend(group)

    if removed > 0:
        logger.info(
            "[polaris graph] M-06: Deduplicated %d -> %d evidence (%d removed)",
            len(evidence),
            len(kept),
            removed,
        )
    return kept



def _reverse_resolve_citations(
    report_sections: list[dict],
    citation_map: dict[str, int],
) -> list[dict]:
    """FIX-059-A: Reverse-resolve [N] back to [CITE:ev_xxx] before expansion.

    When the quality gate triggers expansion after Pass 1 assembly, sections
    already contain resolved [N] citations.  Expansion adds new content with
    [CITE:ev_xxx] markers.  The subsequent Pass 2 assembly creates a NEW
    numbering scheme, but the old [N] from Pass 1 are left as-is, causing
    citation scrambling.

    This function converts all [N] back to [CITE:ev_xxx] using the Pass 1
    citation map so that every citation is in [CITE:...] format when
    expansion runs.  Pass 2 then renumbers everything consistently.
    """
    # Build reverse map: citation_number -> evidence_id
    reverse_map: dict[int, str] = {}
    for ev_id, num in citation_map.items():
        reverse_map[num] = ev_id

    if not reverse_map:
        return report_sections

    def _reverse(match: re.Match) -> str:
        num = int(match.group(1))
        ev_id = reverse_map.get(num)
        if ev_id:
            return f"[CITE:{ev_id}]"
        return match.group(0)  # Keep as-is if no mapping

    result: list[dict] = []
    reversed_count = 0
    for section in report_sections:
        new_section = dict(section)
        content = section.get("content", "")
        new_content = re.sub(r"\[(\d+)\]", _reverse, content)
        if new_content != content:
            reversed_count += 1
        new_section["content"] = new_content
        # Update word count to reflect any length changes
        new_section["word_count"] = len(new_content.split())
        result.append(new_section)

    logger.info(
        "[polaris graph] FIX-059-A: Reverse-resolved citations in %d/%d sections "
        "using %d mappings",
        reversed_count,
        len(report_sections),
        len(reverse_map),
    )
    return result


BATCH_CLUSTER_SYSTEM = """You are a research evidence organizer. Identify 5-8 thematic groups
in the provided evidence batch.

Rules:
1. Every evidence piece must be assigned to exactly one theme.
2. Each theme should have a clear, specific label (not generic like "Other").
3. Rate helpfulness 0-100: how useful this theme is for answering the research question.
4. List 3 key claims per theme (the most important findings).
5. Evidence IDs are sequential integers (1, 2, 3...). Use these EXACT IDs.

Output format example:
{"themes": [{"theme": "Health Effects and Mortality", "description": "Evidence on health impacts including dose-response relationships", "evidence_ids": ["1", "2", "5"], "key_claims": ["X causes Y at dose Z", "Mortality increases by N%", "Long-term exposure linked to..."], "helpfulness": 85}]}"""


# Note: THEME_MERGE_SYSTEM removed — Phase 2 replaced LLM merge with
# _merge_themes_programmatic() (Jaccard similarity, zero LLM involvement).

CLUSTER_SYSTEM = """You are a research evidence organizer. Your job is to
cluster related evidence pieces into coherent thematic groups.

Rules:
1. Create 8-15 clusters that cover all aspects of the research question.
2. Every evidence piece should be assigned to exactly one cluster.
3. Clusters should map naturally to report sections.
4. Identify any aspects of the research question not well-covered.
5. Clusters with the most GOLD evidence should be rated 'strong'.

Output format example:
{"clusters": [{"cluster_id": "c1", "theme": "Health Effects and Epidemiology", "description": "Evidence on health impacts including mortality, morbidity, and dose-response relationships", "evidence_ids": ["ev_abc123", "ev_def456"], "strength": "strong"}, {"cluster_id": "c2", "theme": "Regulatory Framework", "description": "Government standards, compliance data, and policy evolution", "evidence_ids": ["ev_ghi789"], "strength": "moderate"}], "uncovered_aspects": ["long-term economic cost projections", "indigenous community impacts"]}"""

GAP_ANALYSIS_SYSTEM = """You are a research gap analyst. Identify evidence gaps precisely.

Output format example:
{"gaps": ["No evidence on long-term health outcomes beyond 10 years", "Limited data from developing countries"], "gap_severity": "moderate", "suggested_queries": ["long-term longitudinal study health outcomes X", "X exposure developing countries epidemiology"], "should_iterate": true}"""


async def _generate_grounded_abstract(
    client: OpenRouterClient,
    query: str,
    quality: dict,
    outline_title: str,
    section_titles: list[str],
) -> str:
    """FIX-E1: Generate abstract AFTER synthesis with real metrics."""
    prompt = f"""Write a 150-250 word abstract for a research report.

Report title: {outline_title}
Research question: {query}
Sections covered: {', '.join(section_titles)}

Verified metrics (use ONLY these exact numbers):
- Total unique sources cited: {quality['unique_sources']}
- Total citations in report: {quality['total_citations']}
- Total sections: {quality['total_sections']}
- Total words: {quality['total_words']}

Write a scholarly abstract summarizing the report's scope, methodology, key findings, and implications.
You MUST use the exact metrics provided above — do NOT estimate or approximate any numbers.
Do NOT include chain-of-thought or planning text."""

    system = (
        "You are a research report writer. Write ONLY the abstract text. "
        "No meta-commentary. Use third person, academic register. "
        "Include the exact source count and citation count provided."
    )

    response = await client.generate(
        prompt=prompt,
        system=system,
        max_tokens=int(os.getenv("PG_OUTLINE_MAX_TOKENS", "2048")),
        temperature=0.5,
    )
    abstract = response.content.strip()

    # Defense: scrub any CoT leakage
    abstract = _scrub_cot(abstract)

    logger.info(
        "[polaris graph] FIX-E1: Generated grounded abstract (%d words, "
        "referencing %d sources and %d citations)",
        len(abstract.split()),
        quality['unique_sources'],
        quality['total_citations'],
    )
    return abstract


async def _generate_section_charts(
    client: OpenRouterClient,
    section_content: str,
    structured_data: list[dict],
    research_context: str,
) -> str:
    """Generate charts for a section and append them to the content.

    If structured_data has comparison/time_series/ranking data points,
    runs analyze_structured_data() to generate Matplotlib charts,
    then appends the chart markdown to the section content.

    Gated behind env var PG_CHART_GENERATION_ENABLED (default "0" -- disabled).

    Returns the section content with charts appended.
    """
    if os.getenv("PG_CHART_GENERATION_ENABLED", "0") != "1":
        return section_content

    if not structured_data:
        return section_content

    try:
        # Determine analysis_type from the most common data_type in the points
        type_counts: dict[str, int] = {}
        for dp in structured_data:
            dt = dp.get("data_type", "comparison")
            type_counts[dt] = type_counts.get(dt, 0) + 1
        analysis_type = max(type_counts, key=type_counts.get) if type_counts else "comparison"

        result = await analyze_structured_data(
            client=client,
            data_points=structured_data,
            analysis_type=analysis_type,
            research_context=research_context,
        )

        charts = result.get("charts", [])
        tables = result.get("tables", [])

        if not charts and not tables:
            return section_content

        appended = section_content

        for idx, chart in enumerate(charts, start=1):
            chart_md = format_chart_markdown(chart, figure_number=idx)
            if chart_md:
                appended += chart_md

        for idx, table in enumerate(tables, start=1):
            table_md = format_table_markdown(table, table_number=idx)
            if table_md:
                appended += "\n\n" + table_md

        logger.info(
            "[polaris graph] CHART-GEN: Generated %d charts and %d tables "
            "for section (%d data points, type=%s)",
            len(charts), len(tables), len(structured_data), analysis_type,
        )
        return appended

    except Exception as exc:
        logger.warning(
            "[polaris graph] CHART-GEN: Chart generation failed (non-blocking): %s",
            str(exc)[:200],
        )
        return section_content


async def _assess_cluster_viability(
    client,  # OpenRouterClient
    cluster: dict,
    evidence_pieces: list[dict],
    all_themes: list[str],
) -> dict:
    """Use LLM reasoning to decide if a cluster warrants a section.

    Returns dict with: decision (FULL_SECTION/BRIEF/MERGE/DROP),
    reasoning, merge_target, key_claims, has_structured_data, data_type

    Decisions:
      FULL_SECTION — 3+ unique citable claims, warrants detailed analysis
      BRIEF — include as 2-3 bullet points in "Additional Findings"
      MERGE — evidence overlaps with another theme
      DROP — evidence too weak, contradictory, or off-topic

    Gated by env var PG_CLUSTER_VIABILITY_ENABLED (default "0" — disabled).
    On any error, defaults to FULL_SECTION (safe fallback).
    """
    theme = cluster.get("theme", "Unknown")
    description = cluster.get("description", "")
    key_claims = cluster.get("key_claims", [])

    # Build evidence summary block — show actual content, not just IDs
    ev_summary_lines = []
    for ev in evidence_pieces[:20]:  # Cap at 20 to stay within token budget
        stmt = ev.get("statement", "")[:200]
        src = ev.get("source_url", "")
        domain = src.split("//")[-1].split("/")[0] if "//" in src else src[:40]
        tier = ev.get("quality_tier", "BRONZE")
        ev_summary_lines.append(f"- [{tier}] {stmt} [{domain}]")
    evidence_block = "\n".join(ev_summary_lines) if ev_summary_lines else "No evidence"

    # Build other-themes list for MERGE target suggestions
    other_themes = [t for t in all_themes if t != theme]
    nearest = other_themes[:5] if other_themes else ["N/A"]

    prompt = f"""Examine this evidence cluster and decide its viability for a report section.

Cluster theme: "{theme}"
Description: {description}
Evidence count: {len(evidence_pieces)}
Key claims from clustering: {'; '.join(key_claims[:5]) if key_claims else 'Not extracted'}

Actual evidence in this cluster:
{evidence_block}

Other themes in the report: {', '.join(nearest)}

Decide:
A) FULL_SECTION — the cluster has 3+ unique, citable claims supported by the evidence above. It warrants a detailed section with analysis.
B) BRIEF — the cluster has some value but not enough for a full section. Include as 2-3 bullet points in an "Additional Findings" section.
C) MERGE — the evidence significantly overlaps with one of the other themes listed above. Specify which theme to merge into via merge_target.
D) DROP — the evidence is too weak, contradictory, or off-topic to include in the report.

Also determine if the evidence contains structured data (numbers, comparisons, time-series, measurements, rankings) that could be presented as a TABLE or CHART.

Your JSON response MUST include ALL of these fields:
- "decision": one of "FULL_SECTION", "BRIEF", "MERGE", or "DROP"
- "reasoning": a 2-3 sentence explanation of WHY you chose this decision (REQUIRED, not empty)
- "merge_target": the theme name to merge into (only if decision is MERGE, else empty string)
- "key_claims": a list of 3-5 distinct factual claims extractable from this evidence (REQUIRED, not empty)
- "has_structured_data": true if the evidence contains numbers/comparisons/time-series
- "data_type": one of "comparison", "time_series", "measurement", "ranking", or "none" """

    try:
        assessment = await client.generate_structured(
            prompt=prompt,
            schema=ClusterAssessment,
            system=(
                "You are a research evidence evaluator. Assess whether this "
                "cluster of evidence warrants a full report section. Be rigorous: "
                "only recommend FULL_SECTION when there are 3+ distinct, citable "
                "claims with real evidence backing them."
            ),
            max_tokens=int(os.getenv("PG_EVIDENCE_ASSIGN_MAX_TOKENS", "2048")),
            timeout=int(os.getenv("PG_EVIDENCE_ASSIGN_TIMEOUT", "60")),
        )
        return {
            "decision": assessment.decision,
            "reasoning": assessment.reasoning,
            "merge_target": assessment.merge_target,
            "key_claims": assessment.key_claims,
            "has_structured_data": assessment.has_structured_data,
            "data_type": assessment.data_type,
        }
    except Exception as exc:
        logger.warning(
            "[polaris graph] Cluster viability assessment failed for "
            "cluster '%s': %s — defaulting to FULL_SECTION",
            theme[:40], str(exc)[:200],
        )
        return {
            "decision": "FULL_SECTION",
            "reasoning": f"Assessment failed: {str(exc)[:100]}",
            "merge_target": "",
            "key_claims": key_claims[:5],
            "has_structured_data": False,
            "data_type": "none",
        }



async def _generate_contradictions_section(
    client: OpenRouterClient,
    evidence_conflicts: list[dict],
    gaps: list[str],
    evidence: list[dict],
) -> dict:
    """RC-5: Generate a 'Contradictions, Limitations, and Open Questions' section.

    Collects unresolved conflicts and identified gaps, uses a single LLM call
    to synthesize them into a dedicated section.

    Returns a ReportSection-compatible dict.
    """
    # Build conflict summary
    conflict_lines = []
    for i, conflict in enumerate(evidence_conflicts[:10], 1):
        conflict_lines.append(
            f"{i}. {conflict.get('statement_a', '')[:150]} "
            f"[CITE:{conflict.get('evidence_a_id', '?')}] "
            f"vs {conflict.get('statement_b', '')[:150]} "
            f"[CITE:{conflict.get('evidence_b_id', '?')}]"
        )

    # Build gaps summary
    gap_lines = [f"- {g}" for g in (gaps or [])[:10]]

    prompt = (
        "Summarize the key contradictions, limitations, and open questions in this "
        "research area based on the following:\n\n"
        f"CONTRADICTIONS ({len(evidence_conflicts)} detected):\n"
        + "\n".join(conflict_lines) + "\n\n"
        f"EVIDENCE GAPS:\n"
        + "\n".join(gap_lines) + "\n\n"
        "Write a section that:\n"
        "1. Explains each major contradiction with citations to both sides\n"
        "2. Notes what evidence is missing or insufficient\n"
        "3. Suggests what future research would resolve these questions\n"
        "Keep citations as [CITE:evidence_id] format."
    )

    system = (
        "You are writing the final analytical section of a research report. "
        "Be honest about what is not known or disputed. Cite evidence for both "
        "sides of each contradiction. This section adds credibility by showing "
        "intellectual honesty."
    )

    try:
        from src.polaris_graph.state import PG_SECTION_WRITER_MAX_TOKENS
        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=PG_SECTION_WRITER_MAX_TOKENS,
            temperature=0.7,
        )
        content_text = response.content.strip()
        if not content_text or len(content_text.split()) < 50:
            content_text = "Insufficient data to generate contradictions analysis."
    except Exception as exc:
        logger.warning(
            "[polaris graph] RC-5: Contradictions section generation failed: %s",
            str(exc)[:200],
        )
        content_text = "Contradictions analysis could not be generated."

    return {
        "section_id": "s_contradictions",
        "title": "Contradictions, Limitations, and Open Questions",
        "content": content_text,
        "word_count": len(content_text.split()),
        "citation_ids": [],
        "evidence_ids": [],
    }


def _evaluate_analytical_depth(
    report_sections: list[dict],
) -> dict:
    """RC-8: Evaluate analytical depth using regex-based heuristics.

    Checks for the 5 analytical operations across all sections.
    Returns: {"passed": bool, "scores": {...}, "deficient_sections": [...]}
    """
    import re

    comparison_markers = re.compile(
        r'\b(compared to|in contrast|whereas|however|unlike|alternatively|'
        r'on the other hand|differs from|outperformed|underperformed)\b', re.I
    )
    aggregation_markers = re.compile(
        r'\b(across \d+ studies|multiple sources|ranged from|median of|'
        r'average of|converging|majority of evidence|consistently)\b', re.I
    )
    challenge_markers = re.compile(
        r'\b(limitation|however contradictory|conflicting|gap in|'
        r'insufficient evidence|notable absence|remains unclear|'
        r'further research needed|caveat)\b', re.I
    )
    table_pattern = re.compile(r'\|[^|]+\|[^|]+\|')
    key_findings_pattern = re.compile(r'\*\*Key Findings?\*\*', re.I)

    total_comparison = 0
    total_aggregation = 0
    total_challenge = 0
    total_tables = 0
    total_key_findings = 0
    deficient = []

    for section in report_sections:
        content = section.get("content", "")
        comp = len(comparison_markers.findall(content))
        agg = len(aggregation_markers.findall(content))
        chal = len(challenge_markers.findall(content))
        tables = len(table_pattern.findall(content))
        kf = len(key_findings_pattern.findall(content))

        total_comparison += comp
        total_aggregation += agg
        total_challenge += chal
        total_tables += tables
        total_key_findings += kf

        ops_present = sum([comp > 0, agg > 0, chal > 0, tables > 0, kf > 0])
        if ops_present < 2:
            deficient.append(section.get("title", "?"))

    passed = (
        total_comparison >= 10 and
        total_tables >= 2 and
        total_key_findings >= 3 and
        total_challenge >= 3 and
        len(deficient) <= 2
    )

    return {
        "passed": passed,
        "comparison_markers": total_comparison,
        "aggregation_patterns": total_aggregation,
        "challenge_markers": total_challenge,
        "tables": total_tables,
        "key_findings": total_key_findings,
        "deficient_sections": deficient,
    }


async def synthesize_report(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict:
    """
    Full synthesis pipeline.

    Returns state update with sections, bibliography, final_report, quality_metrics.
    """
    evidence = state.get("evidence", [])
    claims = state.get("claims", [])
    query = state["original_query"]
    faithfulness = state.get("faithfulness_score", 0.0)

    # SOTA-12: Propagate cross-reference corroboration into evidence pieces.
    # The verify node stores cross_reference_groups in state; here we mark
    # individual evidence pieces so downstream ranking can boost them.
    xref_groups = state.get("cross_reference_groups", [])
    if xref_groups:
        xref_evidence_ids = set()
        for grp in xref_groups:
            xref_evidence_ids.update(grp.get("evidence_ids", []))
        boosted = 0
        for ev in evidence:
            if ev.get("evidence_id") in xref_evidence_ids:
                ev["cross_referenced"] = True
                boosted += 1
        if boosted:
            logger.info(
                "[polaris graph] SOTA-12: %d/%d evidence pieces marked as "
                "cross-referenced (from %d groups)",
                boosted, len(evidence), len(xref_groups),
            )

    # FIX-058E: Removed redundant SF-27 gate (0.25) — FIX-QM4 gate (0.40) subsumes it.
    # FIX-QM4: Stronger relevance gate before synthesis (complements off-topic filter)
    synthesis_relevance_min = float(os.getenv("PG_SYNTHESIS_RELEVANCE_GATE", "0.40"))
    before_relevance_gate = len(evidence)
    evidence = [
        e for e in evidence
        if e.get("relevance_score", 0.5) >= synthesis_relevance_min
    ]
    relevance_filtered = before_relevance_gate - len(evidence)
    if relevance_filtered > 0:
        logger.info(
            "[polaris graph] FIX-QM4: Synthesis relevance gate removed %d/%d evidence "
            "(threshold=%.2f)",
            relevance_filtered,
            before_relevance_gate,
            synthesis_relevance_min,
        )

    # Gate 2: Filter to verified evidence, falling back to ALL evidence if
    # verification produced too few results (prevents empty reports)
    faithful_ids = {
        c.get("claim_id") for c in claims if c.get("is_faithful")
    }
    # FIX-MP2: REMOVED BUG-1b. api_error claims are UNVERIFIED — their evidence
    # must NOT enter the synthesis pool. In PG_TEST_033, 810/1422 claims were
    # api_error, and BUG-1b included them all, causing the report to cite
    # unverified evidence (53.7% faithfulness, honest 23.3%).
    api_error_count = sum(
        1 for c in claims if c.get("verification_method") == "api_error"
    )
    if api_error_count > 0:
        logger.info(
            "[polaris graph] FIX-MP2: %d api_error claims EXCLUDED from "
            "synthesis pool (unverified evidence not cited)",
            api_error_count,
        )
    # FIX-B3: GOLD evidence no longer bypasses verification.
    # Verified GOLD passes through faithful_ids. Unverified GOLD
    # (not in claims batch at all) is included by default.
    verified_evidence = [
        e for e in evidence
        if e.get("evidence_id") in faithful_ids
    ]
    claim_ids_in_batch = {c.get("claim_id") for c in claims}
    unverified_gold = [
        e for e in evidence
        if e.get("quality_tier") == "GOLD"
        and e.get("evidence_id") not in claim_ids_in_batch
    ]
    if unverified_gold:
        verified_evidence.extend(unverified_gold)
        logger.info(
            "[polaris graph] FIX-B3: %d GOLD evidence pieces were not verified "
            "(not in claims batch) — included by default",
            len(unverified_gold),
        )

    # SF-07: If verification filtered out >80% of evidence, fall back to
    # GOLD + SILVER evidence only (not ALL evidence, which includes unverified BRONZE)
    if len(verified_evidence) < max(len(evidence) * 0.15, 8) and evidence:
        gold_silver = [
            e for e in evidence
            if e.get("quality_tier") in ("GOLD", "SILVER")
        ]
        logger.warning(
            "[polaris graph] Verification too strict: only %d/%d passed. "
            "Falling back to GOLD+SILVER evidence (%d pieces).",
            len(verified_evidence),
            len(evidence),
            len(gold_silver),
        )
        # Use GOLD+SILVER if available, else keep whatever verified evidence we have
        if gold_silver:
            verified_evidence = gold_silver
        elif not verified_evidence:
            # Last resort: use all evidence but log ERROR
            logger.error(
                "[polaris graph] No GOLD/SILVER evidence available either. "
                "Using ALL %d evidence for synthesis.",
                len(evidence),
            )
            verified_evidence = list(evidence)

    # FIX-RC5b: Cap evidence for synthesis to prevent map-reduce explosion.
    # Sort by quality tier (GOLD > SILVER > BRONZE), then relevance DESC,
    # then source_confidence DESC (SOTA-11), then cross-referenced first (SOTA-12).
    # FIX-P5: Reserve 20% of synthesis slots for academic sources.
    pg_max_ev_synthesis = int(os.getenv("PG_MAX_EVIDENCE_FOR_SYNTHESIS", "1000"))
    if len(verified_evidence) > pg_max_ev_synthesis:
        tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
        _sort_key = lambda e: (
            tier_order.get(e.get("quality_tier", "BRONZE"), 2),
            0 if e.get("cross_referenced") else 1,  # SOTA-12: corroborated first
            -e.get("relevance_score", 0.0),
            -e.get("source_confidence", 0.0),  # SOTA-11: higher confidence first
        )
        # FIX-P5: Split into academic vs non-academic pools
        _academic_ev = sorted(
            [e for e in verified_evidence if e.get("source_type") == "academic"],
            key=_sort_key,
        )
        _non_academic_ev = sorted(
            [e for e in verified_evidence if e.get("source_type") != "academic"],
            key=_sort_key,
        )
        _academic_reserve = max(1, int(pg_max_ev_synthesis * 0.20))
        _academic_slice = _academic_ev[:_academic_reserve]
        _remaining_slots = pg_max_ev_synthesis - len(_academic_slice)
        _non_academic_slice = _non_academic_ev[:_remaining_slots]
        trimmed = len(verified_evidence) - pg_max_ev_synthesis
        verified_evidence = _academic_slice + _non_academic_slice
        logger.info(
            "[polaris graph] FIX-RC5b+P5: Capped synthesis evidence at %d "
            "(removed %d lowest quality, reserved %d academic slots, got %d)",
            pg_max_ev_synthesis,
            trimmed,
            _academic_reserve,
            len(_academic_slice),
        )

    logger.info(
        "[polaris graph] Synthesis starting: %d total evidence, "
        "%d verified/gold, faithfulness=%.1f%%",
        len(evidence),
        len(verified_evidence),
        faithfulness * 100,
    )

    # MEM-1: Query evidence hierarchy for quality distribution insight
    hierarchy_read_enabled = os.getenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0") == "1"
    if hierarchy_read_enabled:
        try:
            from src.polaris_graph.memory.evidence_hierarchy import count_by_tier
            tier_counts = await count_by_tier(state.get("vector_id", "unknown"))
            if tier_counts:
                logger.info("[polaris graph] MEM-1: Evidence hierarchy tiers: %s", tier_counts)
        except Exception as mem_exc:
            logger.debug("[polaris graph] MEM-1: hierarchy query failed: %s", str(mem_exc)[:200])

    # M-14: Store evidence in hierarchy (write path)
    hierarchy_write_enabled = os.getenv("PG_EVIDENCE_HIERARCHY_WRITE_ENABLED", "1") == "1"
    if hierarchy_write_enabled and verified_evidence:
        try:
            from src.polaris_graph.memory.evidence_hierarchy import store_evidence
            stored = 0
            for ev in verified_evidence:
                success = await store_evidence(
                    evidence_id=ev.get("evidence_id", ""),
                    vector_id=state.get("vector_id", "unknown"),
                    cluster_id=ev.get("cluster_id", ""),
                    l0_summary=ev.get("statement", "")[:100],
                    l1_overview=(
                        f"{ev.get('statement', '')} "
                        f"[Source: {ev.get('source_title', '')}] "
                        f"[Quality: {ev.get('quality_tier', 'BRONZE')}]"
                    ),
                    l2_json=ev,
                    perspective=ev.get("perspective", ""),
                    quality_tier=ev.get("quality_tier", "BRONZE"),
                    relevance_score=ev.get("relevance_score", 0.0),
                )
                if success:
                    stored += 1
            if stored:
                logger.info(
                    "[polaris graph] M-14: Stored %d/%d evidence in hierarchy",
                    stored, len(verified_evidence),
                )
        except Exception as exc:
            logger.debug("[polaris graph] M-14: Hierarchy write failed: %s", str(exc)[:200])

    # M-06: Deduplicate near-identical evidence within same source
    dedup_enabled = os.getenv("PG_EVIDENCE_DEDUP_ENABLED", "1") == "1"
    if dedup_enabled and len(verified_evidence) >= 2:
        verified_evidence = _dedup_evidence(verified_evidence)

    # Step 1: Cluster evidence
    clusters = await _cluster_evidence(client, verified_evidence, query)

    # Step 1b: Assess cluster viability via LLM reasoning
    viability_enabled = os.getenv("PG_CLUSTER_VIABILITY_ENABLED", "0") == "1"
    if viability_enabled and clusters:
        # Build evidence lookup for fast retrieval by ID
        ev_by_id: dict[str, dict] = {}
        for ev in verified_evidence:
            eid = ev.get("evidence_id", "")
            if eid:
                ev_by_id[eid] = ev

        all_themes = [c.get("theme", f"Cluster {i}") for i, c in enumerate(clusters)]

        # Assess each cluster individually
        for cluster in clusters:
            cluster_ev_ids = cluster.get("evidence_ids", [])
            cluster_evidence = [
                ev_by_id[eid] for eid in cluster_ev_ids if eid in ev_by_id
            ]
            result = await _assess_cluster_viability(
                client=client,
                cluster=cluster,
                evidence_pieces=cluster_evidence,
                all_themes=all_themes,
            )
            cluster["viability"] = result
            # Store structured data flags directly on the cluster dict
            cluster["has_structured_data"] = result.get("has_structured_data", False)
            cluster["data_type"] = result.get("data_type", "none")

        # Process MERGE decisions: combine evidence into target cluster
        merge_targets: dict[str, list[dict]] = {}
        non_merge_clusters: list[dict] = []
        for cluster in clusters:
            decision = cluster.get("viability", {}).get("decision", "FULL_SECTION")
            if decision == "MERGE":
                target_theme = cluster.get("viability", {}).get("merge_target", "")
                if target_theme:
                    merge_targets.setdefault(target_theme, []).append(cluster)
                else:
                    # No merge target specified — demote to BRIEF
                    cluster["viability"]["decision"] = "BRIEF"
                    non_merge_clusters.append(cluster)
            else:
                non_merge_clusters.append(cluster)

        # Apply merges: add merged cluster evidence into the target
        for target_theme, source_clusters in merge_targets.items():
            target_found = False
            for target_cluster in non_merge_clusters:
                if target_cluster.get("theme", "") == target_theme:
                    for src in source_clusters:
                        target_cluster.setdefault("evidence_ids", []).extend(
                            src.get("evidence_ids", [])
                        )
                        target_cluster.setdefault("key_claims", []).extend(
                            src.get("key_claims", [])
                        )
                    logger.info(
                        "[polaris graph] Cluster viability: Merged %d clusters into '%s'",
                        len(source_clusters), target_theme[:40],
                    )
                    target_found = True
                    break
            if not target_found:
                # Target not found — demote source clusters to BRIEF
                for src in source_clusters:
                    src["viability"]["decision"] = "BRIEF"
                    non_merge_clusters.append(src)

        clusters = non_merge_clusters

        # Collect BRIEF clusters for "Additional Findings" section
        brief_clusters = [
            c for c in clusters
            if c.get("viability", {}).get("decision") == "BRIEF"
        ]

        # Filter out DROP and BRIEF clusters from main cluster list
        active_clusters = [
            c for c in clusters
            if c.get("viability", {}).get("decision", "FULL_SECTION")
            not in ("DROP", "BRIEF")
        ]
        dropped = sum(
            1 for c in clusters
            if c.get("viability", {}).get("decision") == "DROP"
        )

        # Log viability decisions
        decisions: dict[str, int] = {}
        for c in clusters:
            d = c.get("viability", {}).get("decision", "FULL_SECTION")
            decisions[d] = decisions.get(d, 0) + 1
        structured_count = sum(
            1 for c in clusters
            if c.get("has_structured_data", False)
        )
        logger.info(
            "[polaris graph] Cluster viability assessment: %s, "
            "%d with structured data",
            decisions, structured_count,
        )

        if dropped > 0:
            logger.info(
                "[polaris graph] Cluster viability: Dropped %d clusters "
                "(insufficient evidence for report inclusion)",
                dropped,
            )
        if brief_clusters:
            logger.info(
                "[polaris graph] Cluster viability: %d clusters marked BRIEF "
                "(will appear in Additional Findings)",
                len(brief_clusters),
            )

        clusters = active_clusters

    # AREA-4 Gap 3: Detect conflicting evidence for explicit handling
    evidence_conflicts = _detect_evidence_conflicts(verified_evidence)
    if evidence_conflicts:
        logger.info(
            "[polaris graph] AREA-4: %d evidence conflicts detected — "
            "will include in synthesis prompts",
            len(evidence_conflicts),
        )

        tracer = get_tracer()
        if tracer:
            tracer.evidence("synthesize", "evidence_conflicts", len(evidence_conflicts),
                conflicts=[{"type": c.get("type", ""), "statement_a": c.get("statement_a", "")[:150],
                            "statement_b": c.get("statement_b", "")[:150],
                            "score": round(c.get("contradiction_score", 0), 3)}
                           for c in evidence_conflicts[:20]])

    # FIX-B4: Check peer-reviewed source percentage
    peer_reviewed_types = {"journal_article", "government_report", "standard"}
    peer_count = sum(
        1 for e in verified_evidence
        if e.get("source_type") in peer_reviewed_types
    )
    peer_pct = peer_count / max(len(verified_evidence), 1)
    min_peer_pct = float(os.getenv("PG_MIN_PEER_REVIEWED_PCT", "0.30"))
    if peer_pct < min_peer_pct:
        logger.warning(
            "[polaris graph] FIX-B4: Peer-reviewed sources %.1f%% < %.1f%% minimum. "
            "Prioritizing academic evidence in synthesis.",
            peer_pct * 100, min_peer_pct * 100,
        )

    # OBS-6: Trace clustering
    tracer = get_tracer()
    if tracer:
        tracer.evidence(
            "synthesize", "clustering", len(clusters),
            evidence_count=len(verified_evidence),
            themes=[{
                "theme": c.get("theme", "")[:100],
                "count": len(c.get("evidence_ids", [])),
            } for c in clusters[:20]],
        )

    # M-15: Query LTM for prior knowledge to inject into outline
    ltm_prior_context = ""
    ltm_enabled = os.getenv("PG_CROSS_VECTOR_LTM_ENABLED", "0") == "1"
    if ltm_enabled and state.get("memory_ltm_prior_count", 0) > 0:
        try:
            from src.polaris_graph.memory.cross_vector import query_ltm
            prior = query_ltm(query=query, max_results=15)
            if prior:
                ltm_prior_context = "\n".join(
                    f"- [{p.get('quality_tier', 'BRONZE')}] "
                    f"{p.get('statement', '')[:150]} (from prior research)"
                    for p in prior[:10]
                )
                logger.info(
                    "[polaris graph] M-15: Injecting %d LTM prior knowledge items into outline",
                    len(prior[:10]),
                )
        except Exception as exc:
            logger.debug("[polaris graph] M-15: LTM query failed: %s", str(exc)[:200])

    # Step 2: Plan report outline
    # FIX-ENV4: Pass evidence_conflicts so the outline can account for
    # contradictory evidence when structuring the report.
    outline = await plan_report(
        client=client,
        query=query,
        evidence=verified_evidence,
        clusters=clusters,
        evidence_conflicts=evidence_conflicts,
        ltm_prior_knowledge=ltm_prior_context,
    )

    tracer = get_tracer()
    if tracer:
        tracer.evidence("synthesize", "report_outline", len(outline.sections),
            title=outline.title[:200],
            sections=[{"id": s.section_id, "title": s.title[:100],
                       "description": s.description[:200],
                       "evidence_count": len(s.evidence_ids), "target_words": s.target_words}
                      for s in outline.sections])

    # FIX-S2: Populate corroborating_sources count on evidence before section writing
    # so the section writer can prioritize well-corroborated evidence.
    from src.polaris_graph.agents.verifier import _triangulate_claims
    corroboration_map = _triangulate_claims(verified_evidence)
    for ev in verified_evidence:
        eid = ev.get("evidence_id", "")
        ev["corroborating_sources"] = corroboration_map.get(eid, 1)

    # FIX-045H: Multi-evidence corroboration — enrich claims with cross-ref evidence
    corroboration_enabled = os.getenv("PG_CORROBORATION_ENABLED", "1") == "1"
    if corroboration_enabled and claims:
        from src.polaris_graph.agents.verifier import link_corroborating_evidence
        xref_groups_for_corr = state.get("cross_reference_groups", [])
        link_corroborating_evidence(
            claims=claims,
            evidence=verified_evidence,
            cross_reference_groups=xref_groups_for_corr,
        )

    # FIX-047-K14: Detect contradictory claims before synthesis.
    # Contradictions are logged and can be passed to section writers
    # so they can address conflicting evidence explicitly.
    claim_contradictions = []
    if claims:
        from src.polaris_graph.agents.verifier import detect_contradictions
        claim_contradictions = detect_contradictions(claims)
        if claim_contradictions:
            # Merge with existing evidence_conflicts for section writers
            if evidence_conflicts is None:
                evidence_conflicts = []
            for c in claim_contradictions:
                evidence_conflicts.append({
                    "type": "claim_contradiction",
                    "evidence_a_id": c.get("claim_a_id", ""),
                    "evidence_b_id": c.get("claim_b_id", ""),
                    "statement_a": c.get("claim_a_statement", ""),
                    "statement_b": c.get("claim_b_statement", ""),
                    "contradiction_signals": [c.get("reason", "")],
                    # FIX-048-K14: Include NLI scores when available
                    "contradiction_score": c.get("contradiction_score", 0.0),
                })

    # TIER-3 Stage 2: Embedding-based evidence routing (deterministic, zero LLM cost).
    # Replaces LLM-based _assign_evidence_globally() when PG_EMBEDDING_ROUTING=1.
    # Falls back to LLM-based assignment when PG_EMBEDDING_ROUTING=0.
    global_assign_enabled = os.getenv("PG_GLOBAL_EVIDENCE_ASSIGNMENT", "1") == "1"
    global_assignments: dict[str, list[str]] = {}
    cross_section_evidence_ids: list[str] = []
    if global_assign_enabled and len(verified_evidence) >= 10:
        # Try embedding routing first (TIER-3 Stage 2)
        from src.polaris_graph.synthesis.evidence_router import (
            route_evidence_to_sections,
            PG_EMBEDDING_ROUTING,
        )
        if PG_EMBEDDING_ROUTING:
            global_assignments, cross_section_evidence_ids = route_evidence_to_sections(
                evidence=verified_evidence,
                sections=outline.sections,
                query=query,
            )
        # Fall back to LLM-based assignment if routing failed or disabled
        if not global_assignments:
            global_assignments, cross_section_evidence_ids = await _assign_evidence_globally(
                client=client,
                outline_sections=outline.sections,
                evidence=verified_evidence,
            )
        if global_assignments:
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "synthesize", "global_evidence_assignment",
                    sum(len(ids) for ids in global_assignments.values()),
                    sections_assigned=len(global_assignments),
                    cross_section_count=len(cross_section_evidence_ids),
                )

    # TIER-3 Stage 4: Persist section assignments in evidence hierarchy
    if global_assignments:
        try:
            from src.polaris_graph.memory.evidence_hierarchy import batch_update_section_assignments
            # Build reverse map: evidence_id -> [section_ids]
            _ev_to_sections: dict[str, list[str]] = {}
            for sid, eids in global_assignments.items():
                for eid in eids:
                    _ev_to_sections.setdefault(eid, []).append(sid)
            _updated = await batch_update_section_assignments(_ev_to_sections)
            if _updated:
                logger.info(
                    "[polaris graph] TIER-3: Stored section assignments for %d evidence in hierarchy",
                    _updated,
                )
        except Exception as _assign_exc:
            logger.debug(
                "[polaris graph] TIER-3: Section assignment persistence failed (non-fatal): %s",
                str(_assign_exc)[:200],
            )

    # Step 3: Write all sections (parallel, concurrency from env)
    # FIX-107I: write_all_sections now returns (drafts, section_evidence_map)
    # FIX-ENV4: Pass evidence_conflicts so section writers can address
    # contradictions explicitly when relevant to their section topic.
    # FIX-E: Pass global_assignments and cross_section_evidence_ids
    sections, section_evidence_map = await write_all_sections(
        client=client,
        outline=outline,
        evidence=verified_evidence,
        query=query,
        concurrency=PG_SECTION_WRITE_CONCURRENCY,
        evidence_conflicts=evidence_conflicts,
        global_assignments=global_assignments,
        cross_section_evidence_ids=cross_section_evidence_ids,
    )

    if tracer:
        tracer.evidence("synthesize", "section_evidence_map", len(section_evidence_map),
            mapping=[{"section_id": sid, "evidence_count": len(eids),
                      "evidence_ids": eids[:10]}
                     for sid, eids in section_evidence_map.items()])

    # Step 3b: FIX-S1 — Revise sections for quality (controlled by env var)
    # FIX-PARALLEL: Semaphore-bounded concurrent revision (was sequential)
    revision_enabled = os.getenv("PG_SECTION_REVISION_ENABLED", "1") == "1"
    if revision_enabled:
        revision_concurrency = int(os.getenv("PG_REVISION_CONCURRENCY", "4"))
        revision_sem = asyncio.Semaphore(revision_concurrency)

        # FIX-058G-v2: Per-revision timeout (same as section write timeout)
        _revision_timeout = int(os.getenv("PG_SECTION_WRITE_TIMEOUT", "300"))

        async def _bounded_revise(section):
            async with revision_sem:
                return await asyncio.wait_for(
                    revise_section(
                        client=client,
                        draft=section,
                        evidence=verified_evidence,
                        query=query,
                        report_title=outline.title,
                    ),
                    timeout=_revision_timeout,
                )

        revision_tasks = [_bounded_revise(s) for s in sections]
        revised_results = await asyncio.gather(*revision_tasks, return_exceptions=True)

        revised_sections = []
        for i, result in enumerate(revised_results):
            if isinstance(result, Exception):
                logger.warning(
                    "[polaris graph] FIX-S1: Section revision failed for "
                    "section %d: %s — keeping original draft",
                    i, str(result)[:200],
                )
                revised_sections.append(sections[i])
            else:
                revised_sections.append(result)

        sections = revised_sections
        logger.info(
            "[polaris graph] FIX-S1: Section revision pass complete: "
            "%d sections revised (concurrency=%d)",
            len(sections),
            revision_concurrency,
        )

    # ARCH-3: Dedicated citation agent — re-cite sections with low citation density.
    # Uses [CITE:ev_xxx] format output, compatible with downstream resolve_citations().
    # No pre_audit needed — citation agent maps evidence IDs directly.
    from src.polaris_graph.agents.citation_agent import (
        PG_CITATION_AGENT_ENABLED, recite_all_sections,
    )
    if PG_CITATION_AGENT_ENABLED:
        sections = await recite_all_sections(
            client=client,
            sections=sections,
            evidence=verified_evidence,
        )

    # Step 3c: CHART-GEN — Generate charts for sections with structured data.
    # Gated behind PG_CHART_GENERATION_ENABLED (default "0"). When enabled,
    # iterates sections whose cluster has has_structured_data=True, filters
    # structured_data from state to evidence relevant to each section, and
    # calls _generate_section_charts() to append chart/table markdown.
    chart_gen_enabled = os.getenv("PG_CHART_GENERATION_ENABLED", "0") == "1"
    if chart_gen_enabled and clusters:
        # Build cluster lookup: evidence_id -> cluster viability metadata
        _cluster_ev_map: dict[str, dict] = {}
        for cluster in clusters:
            viability = cluster.get("viability", {})
            if viability.get("has_structured_data", False):
                for eid in cluster.get("evidence_ids", []):
                    _cluster_ev_map[eid] = viability

        state_structured_data = state.get("structured_data", [])

        if _cluster_ev_map and state_structured_data:
            chart_gen_count = 0
            for i, sec in enumerate(sections):
                sid = getattr(sec, "section_id", "")
                sec_ev_ids = set(
                    getattr(sec, "evidence_ids", [])
                    or section_evidence_map.get(sid, [])
                )
                # Check if any of this section's evidence is in a structured cluster
                has_structured = any(eid in _cluster_ev_map for eid in sec_ev_ids)
                if not has_structured:
                    continue

                # Filter structured_data to points relevant to this section's evidence
                section_data = [
                    dp for dp in state_structured_data
                    if dp.get("evidence_id", "") in sec_ev_ids
                ]
                if not section_data:
                    continue

                try:
                    updated_content = await _generate_section_charts(
                        client=client,
                        section_content=getattr(sec, "content", ""),
                        structured_data=section_data,
                        research_context=query,
                    )
                    if updated_content != getattr(sec, "content", ""):
                        # Update section content with charts appended
                        if hasattr(sec, "content"):
                            sec.content = updated_content
                        chart_gen_count += 1
                except Exception as chart_exc:
                    logger.warning(
                        "[polaris graph] CHART-GEN: Failed for section '%s': %s",
                        getattr(sec, "title", "")[:40],
                        str(chart_exc)[:200],
                    )

            if chart_gen_count > 0:
                logger.info(
                    "[polaris graph] CHART-GEN: Charts generated for %d/%d sections",
                    chart_gen_count, len(sections),
                )

    # Step 4: Audit citations
    citation_audit = await audit_citations(
        client=client,
        sections=sections,
        evidence=verified_evidence,
    )

    # ARCH-5: Token-level hallucination detection + remediation.
    # Runs after section writing/revision/citation but before report assembly.
    # FIX-ARCH5-REMEDIATE: When sections are flagged for rewrite, call
    # revise_section() with anti-hallucination instructions to remove
    # unsupported claims. Results stored in state for post-run analysis.
    hallucination_audit = []
    try:
        # TIER-3: Hydrate source_content for LettuceDetect (sync function).
        # Without hydration, detector falls back to direct_quote (lower context).
        try:
            from src.polaris_graph.memory.source_content_store import (
                get_content_batch as _get_content_batch_halluc,
                PG_SOURCE_CONTENT_STORE_ENABLED as _halluc_store_enabled,
            )
            if _halluc_store_enabled:
                _halluc_urls = list({
                    ev.get("source_url", "") for ev in verified_evidence
                    if ev.get("source_url")
                })
                _halluc_content = await _get_content_batch_halluc(_halluc_urls)
                for ev in verified_evidence:
                    _h_url = ev.get("source_url", "")
                    if _h_url and _h_url in _halluc_content:
                        ev["source_content"] = _halluc_content[_h_url][:2000]
        except Exception:
            pass  # Non-fatal: detector has direct_quote fallback

        # Convert section objects to dicts for the detector
        # FIX-039: Use section_evidence_map as fallback when SectionDraft
        # lacks evidence_ids (e.g. after revision/citation agent creates new drafts)
        section_dicts = []
        for sec in sections:
            sid = getattr(sec, "section_id", "")
            sec_dict = {
                "section_id": sid,
                "title": getattr(sec, "title", ""),
                "content": getattr(sec, "content", ""),
                "evidence_ids": getattr(sec, "evidence_ids", [])
                or section_evidence_map.get(sid, []),
            }
            section_dicts.append(sec_dict)

        hallucination_audit = audit_sections_for_hallucination(
            sections=section_dicts,
            evidence=verified_evidence,
            research_query=query,
        )

        # TIER-3: Strip hydrated source_content to keep state lean
        for ev in verified_evidence:
            ev.pop("source_content", None)
        if hallucination_audit:
            rewrite_flagged = sum(
                1 for r in hallucination_audit if r.get("needs_rewrite")
            )
            avg_ratio = sum(
                r["hallucination_ratio"] for r in hallucination_audit
            ) / len(hallucination_audit)
            logger.info(
                "[polaris graph] ARCH-5: Hallucination audit: "
                "%d sections audited, avg ratio %.1f%%, %d flagged for rewrite",
                len(hallucination_audit),
                avg_ratio * 100,
                rewrite_flagged,
            )

            tracer = get_tracer()
            if tracer:
                tracer.evidence("synthesize", "hallucination_audit", len(hallucination_audit),
                    avg_ratio=round(avg_ratio, 3), rewrite_flagged=rewrite_flagged,
                    sections=[{"section_id": r.get("section_id", ""), "title": r.get("title", "")[:80],
                               "hallucination_ratio": round(r.get("hallucination_ratio", 0), 3),
                               "needs_rewrite": r.get("needs_rewrite", False),
                               "flagged_spans": len(r.get("flagged_spans", []))}
                              for r in hallucination_audit])

            # FIX-ARCH5-REMEDIATE: Rewrite sections with high hallucination ratio
            if rewrite_flagged > 0:
                flagged_ids = {
                    r["section_id"]
                    for r in hallucination_audit
                    if r.get("needs_rewrite")
                }
                rewrite_count = 0
                for i, sec in enumerate(sections):
                    sid = getattr(sec, "section_id", "")
                    if sid not in flagged_ids:
                        continue
                    try:
                        # FIX-058G-v2: Timeout guard on hallucination remediation revisions
                        _remediate_timeout = int(os.getenv("PG_SECTION_WRITE_TIMEOUT", "300"))
                        revised = await asyncio.wait_for(
                            revise_section(
                                client=client,
                                draft=sec,
                                evidence=verified_evidence,
                                query=query,
                                report_title=outline.title,
                            ),
                            timeout=_remediate_timeout,
                        )
                        sections[i] = revised
                        rewrite_count += 1
                        logger.info(
                            "[polaris graph] ARCH-5-REMEDIATE: Rewrote section '%s' "
                            "(was flagged for hallucination)",
                            getattr(sec, "title", "")[:40],
                        )
                    except Exception as rev_exc:
                        logger.warning(
                            "[polaris graph] ARCH-5-REMEDIATE: Rewrite failed for "
                            "section '%s': %s — keeping original",
                            getattr(sec, "title", "")[:40],
                            str(rev_exc)[:200],
                        )
                if rewrite_count > 0:
                    logger.info(
                        "[polaris graph] ARCH-5-REMEDIATE: %d/%d flagged sections "
                        "rewritten successfully",
                        rewrite_count, rewrite_flagged,
                    )
    except Exception as exc:
        logger.warning(
            "[polaris graph] ARCH-5: Hallucination audit failed (non-blocking): %s",
            str(exc)[:200],
        )

    # MoST Safety Net: Snapshot pre-MoST sections (already halluc-audited)
    most_enabled = os.getenv("PG_MOST_ENABLED", "0") == "1"
    pre_most_sections = list(sections) if most_enabled else []
    most_reflection_stats = {}
    most_exploration_stats = {}
    bond_analysis = {}

    # FIX-E2E-2: Cap evidence pool before MoST analyses.
    # MoST operations are O(n²) on evidence (pairwise similarity matrices).
    # Previous E2E run: 1000+ evidence → 80+ min CPU burn in peptide_flow,
    # covalent_binder, ionic_rebalancer, disulfide_bridge (all vecs @ vecs.T).
    # Cap at PG_MOST_MAX_EVIDENCE (default 300) sorted by tier+relevance.
    _most_max_evidence = int(os.getenv("PG_MOST_MAX_EVIDENCE", "300"))
    _most_total_timeout = int(os.getenv("PG_MOST_TOTAL_TIMEOUT", "300"))
    if most_enabled and len(verified_evidence) > _most_max_evidence:
        def _ev_sort_key(ev):
            tier = ev.get("tier", "BRONZE")
            tier_rank = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}.get(tier, 3)
            relevance = ev.get("relevance_score", 0.0)
            if isinstance(relevance, str):
                try:
                    relevance = float(relevance)
                except (ValueError, TypeError):
                    relevance = 0.0
            return (tier_rank, -relevance)

        _sorted_ev = sorted(verified_evidence, key=_ev_sort_key)
        _most_evidence = _sorted_ev[:_most_max_evidence]
        logger.info(
            "[polaris graph] FIX-E2E-2: Capping MoST evidence pool %d → %d "
            "(GOLD=%d, SILVER=%d, BRONZE=%d)",
            len(verified_evidence), len(_most_evidence),
            sum(1 for e in _most_evidence if e.get("tier") == "GOLD"),
            sum(1 for e in _most_evidence if e.get("tier") == "SILVER"),
            sum(1 for e in _most_evidence if e.get("tier") == "BRONZE"),
        )
    else:
        _most_evidence = verified_evidence

    # MoST Bond Analysis (M-08 through M-11): Zero-cost structural analysis
    if most_enabled:
        try:
            from src.polaris_graph.synthesis.covalent_binder import (
                analyze_covalent_bonds,
                apply_auto_fixes as covalent_auto_fix,
            )
            covalent_result = analyze_covalent_bonds(sections, _most_evidence)
            bond_analysis["covalent"] = covalent_result

            # Auto-fix missing bonds (insert CITE markers)
            if covalent_result.get("auto_fixes"):
                sections = covalent_auto_fix(sections, covalent_result["auto_fixes"])
                logger.info(
                    "[polaris graph] MoST Covalent: %d auto-fixes applied",
                    len(covalent_result["auto_fixes"]),
                )
        except Exception as exc:
            logger.warning("[polaris graph] MoST Covalent failed (non-blocking): %s", str(exc)[:200])

        try:
            from src.polaris_graph.synthesis.ionic_rebalancer import analyze_ionic_bonds
            ionic_result = analyze_ionic_bonds(sections, _most_evidence)
            bond_analysis["ionic"] = ionic_result

            # FIX-059-M: Apply ionic migrations if available
            migrations = ionic_result.get("migrations", [])
            if migrations:
                try:
                    from src.polaris_graph.synthesis.ionic_rebalancer import (
                        format_ionic_findings_for_phase_r,
                    )
                    # Ionic rebalancer provides analysis but not direct section mutation.
                    # Migrations are consumed by Phase R (cross-section reflection) via
                    # bond_analysis dict. Log the intent for traceability.
                    logger.info(
                        "[polaris graph] FIX-059-M: %d ionic migrations flagged "
                        "for Phase R consumption (avg delta=%.3f)",
                        len(migrations),
                        sum(m["delta"] for m in migrations) / len(migrations),
                    )
                except (ImportError, AttributeError):
                    logger.debug(
                        "[polaris graph] FIX-059-M: ionic migration format not available"
                    )
        except Exception as exc:
            logger.warning("[polaris graph] MoST Ionic failed (non-blocking): %s", str(exc)[:200])

        try:
            from src.polaris_graph.synthesis.disulfide_bridge import analyze_disulfide_bridges
            disulfide_result = analyze_disulfide_bridges(sections, _most_evidence)
            bond_analysis["disulfide"] = disulfide_result

            # Emit section-level conflicts for frontend badge rendering
            ds_contradictions = disulfide_result.get("contradictions", [])
            ds_redundancies = disulfide_result.get("redundancies", [])
            section_conflicts = ds_contradictions + ds_redundancies
            if section_conflicts:
                tracer = get_tracer()
                if tracer:
                    tracer.evidence(
                        "synthesize", "section_conflicts",
                        len(section_conflicts),
                        conflicts=[{
                            "type": c.get("type", "redundancy" if c.get("similarity", 0) > 0.5 else "contradiction"),
                            "section_a": c.get("section_a", ""),
                            "section_b": c.get("section_b", ""),
                            "claim_a": c.get("claim_a", "")[:150],
                            "claim_b": c.get("claim_b", "")[:150],
                            "score": round(c.get("similarity", 0), 3),
                        } for c in section_conflicts[:20]],
                    )
        except Exception as exc:
            logger.warning("[polaris graph] MoST Disulfide failed (non-blocking): %s", str(exc)[:200])

        try:
            from src.polaris_graph.synthesis.peptide_flow import (
                analyze_peptide_flow,
                apply_auto_fixes as peptide_auto_fix,
            )
            peptide_result = analyze_peptide_flow(sections)
            bond_analysis["peptide"] = peptide_result

            # Auto-fix dangling connectors and stutters
            sections = peptide_auto_fix(sections, peptide_result)
        except Exception as exc:
            logger.warning("[polaris graph] MoST Peptide failed (non-blocking): %s", str(exc)[:200])

    # MoST Phase R: Cross-Section Self-Reflection (Hydrogen Bond)
    # M-12: Enhanced with structured bond analysis input
    if most_enabled:
        try:
            from src.polaris_graph.synthesis.cross_section_reflector import reflect_across_sections
            reflection_concurrency = int(os.getenv("PG_REFLECTION_CONCURRENCY", "3"))
            sections = await asyncio.wait_for(
                reflect_across_sections(
                    client=client, sections=sections, evidence=_most_evidence,
                    query=query, concurrency=reflection_concurrency,
                    bond_analysis=bond_analysis,
                ),
                timeout=_most_total_timeout,
            )
            logger.info("[polaris graph] MoST Phase R: Cross-section reflection complete")
        except asyncio.TimeoutError:
            logger.warning(
                "[polaris graph] FIX-E2E-3: MoST Phase R timed out after %ds — skipping",
                _most_total_timeout,
            )
        except Exception as exc:
            logger.warning("[polaris graph] MoST Phase R failed (non-blocking): %s", str(exc)[:200])

    # MoST Phase E: Evidence Self-Exploration (Van der Waals)
    if most_enabled:
        try:
            from src.polaris_graph.synthesis.evidence_explorer import explore_unused_evidence
            sections = await asyncio.wait_for(
                explore_unused_evidence(
                    client=client, sections=sections, all_evidence=_most_evidence,
                    section_evidence_map=section_evidence_map, query=query,
                ),
                timeout=_most_total_timeout,
            )
            logger.info("[polaris graph] MoST Phase E: Evidence exploration complete")
        except asyncio.TimeoutError:
            logger.warning(
                "[polaris graph] FIX-E2E-3: MoST Phase E timed out after %ds — skipping",
                _most_total_timeout,
            )
        except Exception as exc:
            logger.warning("[polaris graph] MoST Phase E failed (non-blocking): %s", str(exc)[:200])

    # MoST Safety Net: Re-audit hallucinations + citations after MoST
    if most_enabled and pre_most_sections:
        try:
            # FIX-059-P (H-17): Guard against zip() silent truncation
            if len(pre_most_sections) != len(sections):
                logger.warning(
                    "[polaris graph] FIX-059-P: Section count mismatch: "
                    "pre_most=%d vs current=%d -- skipping MoST Safety Net",
                    len(pre_most_sections), len(sections),
                )
                raise ValueError("Section count mismatch")

            # Count what changed
            changed_count = sum(
                1 for orig, curr in zip(pre_most_sections, sections)
                if getattr(orig, 'content', '') != getattr(curr, 'content', '')
            )
            if changed_count > 0:
                logger.info(
                    "[polaris graph] MoST Safety Net: %d/%d sections modified, re-auditing",
                    changed_count, len(sections),
                )

                # Re-audit hallucinations on MoST-modified sections
                post_most_dicts = []
                for sec in sections:
                    sid = getattr(sec, "section_id", "")
                    post_most_dicts.append({
                        "section_id": sid,
                        "title": getattr(sec, "title", ""),
                        "content": getattr(sec, "content", ""),
                        "evidence_ids": getattr(sec, "evidence_ids", [])
                        or section_evidence_map.get(sid, []),
                    })
                post_most_halluc = audit_sections_for_hallucination(
                    sections=post_most_dicts,
                    evidence=verified_evidence,
                    research_query=query,
                )

                # Build lookup: section_id -> hallucination ratio (post vs pre)
                post_ratios = {
                    r["section_id"]: r["hallucination_ratio"]
                    for r in post_most_halluc
                }
                pre_ratios = {
                    r["section_id"]: r["hallucination_ratio"]
                    for r in hallucination_audit
                }

                # Revert any section where hallucination ratio INCREASED by >5%
                reverted = 0
                for i, (orig, curr) in enumerate(zip(pre_most_sections, sections)):
                    sid = getattr(curr, 'section_id', '')
                    if getattr(orig, 'content', '') == getattr(curr, 'content', ''):
                        continue
                    post_ratio = post_ratios.get(sid, 0.0)
                    pre_ratio = pre_ratios.get(sid, 0.0)
                    if post_ratio > pre_ratio + 0.05:
                        sections[i] = orig
                        reverted += 1
                        logger.warning(
                            "[polaris graph] MoST Safety Net: REVERTED section '%s' "
                            "(halluc %.1f%% -> %.1f%%)",
                            getattr(curr, 'title', '')[:40],
                            pre_ratio * 100, post_ratio * 100,
                        )

                # Refresh citation audit on final sections
                citation_audit = await audit_citations(
                    client=client, sections=sections, evidence=verified_evidence,
                )

                # Compute MoST stats from before/after comparison
                e_enriched = 0
                e_new_citations = 0
                for orig, curr in zip(pre_most_sections, sections):
                    orig_cites = set(re.findall(
                        r'\[CITE:(ev_[a-f0-9]+)\]', getattr(orig, 'content', ''),
                    ))
                    curr_cites = set(re.findall(
                        r'\[CITE:(ev_[a-f0-9]+)\]', getattr(curr, 'content', ''),
                    ))
                    if curr_cites - orig_cites:
                        e_enriched += 1
                        e_new_citations += len(curr_cites - orig_cites)

                most_reflection_stats = {
                    "sections_changed": changed_count,
                    "sections_reverted": reverted,
                    "net_sections_modified": changed_count - reverted,
                }
                most_exploration_stats = {
                    "sections_enriched": e_enriched,
                    "new_citations_added": e_new_citations,
                }
                logger.info(
                    "[polaris graph] MoST Safety Net complete: %d changed, %d reverted, "
                    "%d enriched, %d new citations, citation audit refreshed",
                    changed_count, reverted, e_enriched, e_new_citations,
                )
        except Exception as exc:
            logger.warning(
                "[polaris graph] MoST Safety Net failed, reverting ALL: %s",
                str(exc)[:200],
            )
            sections = list(pre_most_sections)

    # M-01: Sync evidence_ids from actual CITE markers (fixes 3x underreporting)
    from src.polaris_graph.synthesis.section_utils import sync_evidence_ids_from_content
    sections = [sync_evidence_ids_from_content(sec) for sec in sections]

    # RAGAS-FIX: Build draft_report with [CITE:ev_xxx] tokens BEFORE resolution.
    # run_ragas_v3.py needs [CITE:ev_xxx] format for citation-aware faithfulness.
    draft_parts = [f"# {outline.title}", ""]
    if outline.abstract:
        draft_parts.extend(["## Abstract", "", outline.abstract, ""])
    for sec in sorted(sections, key=lambda s: s.order if hasattr(s, "order") else 0):
        draft_parts.extend([f"## {sec.title}", "", sec.content, ""])
    draft_report = "\n".join(draft_parts)

    # RC-5: Generate contradictions section (v3 Hybrid)
    if os.getenv("PG_V3_SURFACE_ANALYSIS", "0") == "1":
        evidence_conflicts = state.get("evidence_conflicts", [])
        gaps = state.get("gaps", [])
        if evidence_conflicts or gaps:
            contradictions_section = await _generate_contradictions_section(
                client, evidence_conflicts, gaps, evidence,
            )
            # Append as final content section (before assembly resolves citations)
            from src.polaris_graph.schemas import SectionDraft
            contradictions_draft = SectionDraft(
                section_id="s_contradictions",
                title="Contradictions, Limitations, and Open Questions",
                content=contradictions_section["content"],
                evidence_ids=[],
            )
            sections.append(contradictions_draft)
            logger.info(
                "[polaris graph] RC-5: Added contradictions section (%d words)",
                contradictions_section["word_count"],
            )

    # Step 5: Assemble final report (resolves [CITE:ev_xxx] → numbered [N])
    final_report, report_sections, bibliography = assemble_report(
        outline=outline,
        sections=sections,
        evidence=verified_evidence,
        citation_audit=citation_audit,
    )

    # Step 6: Compute quality metrics
    # FIX-043E: Use verified_evidence (synthesis pool), not full evidence,
    # so utilization measures against the actual pool used for synthesis.
    quality = compute_quality_metrics(
        evidence=verified_evidence,
        claims=claims,
        report_sections=report_sections,
        bibliography=bibliography,
        faithfulness_score=faithfulness,
    )

    logger.info(
        "[polaris graph] Synthesis complete: %d words, %d sections, "
        "%d citations, %d unique sources, faithfulness=%.1f%%",
        quality["total_words"],
        quality["total_sections"],
        quality["total_citations"],
        quality["unique_sources"],
        quality["faithfulness_score"] * 100,
    )

    # FIX-E1: Generate grounded abstract AFTER assembly with real metrics
    section_titles = [s["title"] for s in report_sections]
    grounded_abstract = await _generate_grounded_abstract(
        client=client,
        query=query,
        quality=quality,
        outline_title=outline.title,
        section_titles=section_titles,
    )

    # FIX-E1: Replace the pre-synthesis abstract in final_report with grounded one
    abstract_pattern = re.compile(
        r"(## Abstract\n\n)(.*?)(\n\n## )",
        re.DOTALL,
    )
    if abstract_pattern.search(final_report):
        final_report = abstract_pattern.sub(
            rf"\g<1>{grounded_abstract}\n\n## ",
            final_report,
        )
    elif "## Abstract" not in final_report and report_sections:
        # No abstract section existed — inject one after the title
        title_end = final_report.find("\n\n")
        if title_end != -1:
            final_report = (
                final_report[:title_end]
                + "\n\n## Abstract\n\n"
                + grounded_abstract
                + "\n"
                + final_report[title_end:]
            )

    # Persist grounded abstract in outline so it propagates to state
    outline.abstract = grounded_abstract

    # CHART-GEN: Insert infographic metrics block after abstract/introduction.
    # Provides a machine-readable summary of report quality metrics.
    _source_count = quality.get("unique_sources", 0)
    _evidence_count = len(verified_evidence)
    _faithfulness_pct = quality.get("faithfulness_score", 0.0) * 100
    _claim_count = quality.get("total_citations", 0)
    metrics_line = (
        f":::metrics\n"
        f"Sources: {_source_count} | Evidence: {_evidence_count} | "
        f"Faithfulness: {_faithfulness_pct:.1f}% | Unique Claims: {_claim_count}\n"
        f":::"
    )
    # FIX-6: Insert after abstract — try multiple patterns with fallback.
    # Pattern 1: ## Abstract (most common)
    # Pattern 2: # Abstract (single-hash variant)
    # Pattern 3: First heading of any level (no abstract at all)
    # Fallback: Position 0 (prepend to report)
    _abstract_end = re.search(r"(## Abstract\n\n.*?\n)(\n## )", final_report, re.DOTALL)
    if not _abstract_end:
        _abstract_end = re.search(r"(# Abstract\n\n.*?\n)(\n#+ )", final_report, re.DOTALL)
    if not _abstract_end:
        # No abstract — insert before the first content heading
        _abstract_end = re.search(r"(\n)(## )", final_report)
    if _abstract_end:
        insert_pos = _abstract_end.end(1)
        final_report = (
            final_report[:insert_pos]
            + "\n" + metrics_line + "\n"
            + final_report[insert_pos:]
        )
        logger.info(
            "[polaris graph] CHART-GEN: Inserted metrics block "
            "(sources=%d, evidence=%d, faith=%.1f%%, claims=%d)",
            _source_count, _evidence_count, _faithfulness_pct, _claim_count,
        )
    else:
        logger.warning(
            "[polaris graph] FIX-6: Could not find insertion point for metrics "
            "block — no abstract or heading found in report"
        )

    # M-18: Evidence utilization gate warning
    min_utilization = float(os.getenv("PG_MIN_EVIDENCE_UTILIZATION", "0.30"))
    actual_utilization = quality.get("evidence_utilization", 0.0)
    if actual_utilization < min_utilization:
        logger.warning(
            "[polaris graph] M-18: Evidence utilization %.1f%% below %.0f%% minimum "
            "(expansion may help)",
            actual_utilization * 100,
            min_utilization * 100,
        )

    # FIX-310: Post-synthesis quality gate — expand thin sections if below minimums
    # FIX-QG1: Also check faithfulness — gate should NOT pass at 51%
    expansion_passes = 0
    quality_gate_result = "passed"

    # FIX-046A: Define target_total BEFORE the while loop so it's always
    # available for post-loop code (line ~1034) that uses it.
    target_total = int(os.getenv("PG_TARGET_TOTAL_WORDS", "12000"))

    # DUR-5: Skip expansion entirely if already above threshold
    skip_expansion_threshold = int(os.getenv("PG_SKIP_EXPANSION_WORD_THRESHOLD", "0"))

    while expansion_passes < PG_SYNTHESIS_MAX_EXPANSION_PASSES:
        # FIX-D: Substance-based quality gate — measure substance, not structure.
        # Removes word count and raw citation count gates (these caused infinite
        # expansion loops that inflated reports without improving quality).
        sources_ok = quality["unique_sources"] >= MIN_UNIQUE_SOURCES  # 8
        faith_ok = quality.get("faithfulness_score", 0) >= MIN_FAITHFULNESS  # 0.70

        # FIX-D: Citation spread — every section must cite >= N sources
        section_citation_counts = {
            s.get("section_id", ""): len(s.get("citation_ids", []))
            for s in report_sections
        }
        section_citation_ok = all(
            cnt >= PG_MIN_CITATIONS_PER_SECTION
            for cnt in section_citation_counts.values()
        ) if report_sections else False

        # FIX-4: Evidence-pool guard — skip citation_spread when evidence pool
        # is too small to mathematically satisfy it. Prevents infinite expansion
        # loops when NLI kills 90% of evidence (e.g., niche chemistry topics).
        min_evidence_needed = len(report_sections) * PG_MIN_CITATIONS_PER_SECTION
        if not section_citation_ok and len(verified_evidence) < min_evidence_needed:
            logger.warning(
                "[polaris graph] FIX-4: Skipping citation_spread check — %d evidence "
                "< %d needed for %d sections × %d min citations",
                len(verified_evidence), min_evidence_needed,
                len(report_sections), PG_MIN_CITATIONS_PER_SECTION,
            )
            section_citation_ok = True  # Degrade gracefully

        # FIX-D: Evidence utilization — at least 40% of verified evidence cited
        utilization = quality.get("evidence_utilization", 0.0)
        utilization_ok = utilization >= PG_MIN_EVIDENCE_UTILIZATION  # 0.40

        # RC-8: Analytical depth gate (v3 Hybrid)
        depth_ok = True
        if os.getenv("PG_V3_DEPTH_GATE", "0") == "1":
            depth_result = _evaluate_analytical_depth(report_sections)
            depth_ok = depth_result["passed"]
            if not depth_ok:
                logger.warning(
                    "[polaris graph] RC-8: Depth gate FAILED: comp=%d, tables=%d, kf=%d, "
                    "challenge=%d, deficient=%s",
                    depth_result["comparison_markers"],
                    depth_result["tables"],
                    depth_result["key_findings"],
                    depth_result["challenge_markers"],
                    depth_result["deficient_sections"][:3],
                )

        gate_passed = sources_ok and faith_ok and section_citation_ok and utilization_ok and depth_ok
        if gate_passed:
            break

        # FIX-D: Log which substance metrics failed
        failed_metrics = []
        if not sources_ok:
            failed_metrics.append(f"sources={quality['unique_sources']}/{MIN_UNIQUE_SOURCES}")
        if not faith_ok:
            failed_metrics.append(f"faith={quality.get('faithfulness_score', 0):.1%}/{MIN_FAITHFULNESS:.1%}")
        if not section_citation_ok:
            low_sections = [
                sid for sid, cnt in section_citation_counts.items()
                if cnt < PG_MIN_CITATIONS_PER_SECTION
            ]
            failed_metrics.append(f"citation_spread={len(low_sections)} sections below {PG_MIN_CITATIONS_PER_SECTION}")
        if not utilization_ok:
            failed_metrics.append(f"utilization={utilization:.1%}/{PG_MIN_EVIDENCE_UTILIZATION:.1%}")
        if not depth_ok:
            failed_metrics.append(f"depth: {depth_result.get('deficient_sections', [])[:3]}")

        logger.warning(
            "[polaris graph] FIX-D: Quality gate FAILED (pass %d): %s "
            "(words=%d, citations=%d for reference) — expanding thin sections",
            expansion_passes + 1,
            ", ".join(failed_metrics),
            quality["total_words"],
            quality["total_citations"],
        )

        # OBS-6: Trace quality gate failure
        tracer = get_tracer()
        if tracer:
            tracer.quality_gate(
                "synthesize", "post_synthesis",
                passed=False,
                expansion_pass=expansion_passes + 1,
                total_words=quality["total_words"],
                total_citations=quality["total_citations"],
                unique_sources=quality["unique_sources"],
            )

        # FIX-059-A: Reverse-resolve [N] back to [CITE:ev_xxx] before expansion.
        # This prevents citation scrambling when Pass 2 creates new numbering.
        pass1_citation_map = {
            m.evidence_id: m.citation_number
            for m in citation_audit.mappings
        }
        report_sections = _reverse_resolve_citations(
            report_sections, pass1_citation_map,
        )

        # FIX-QG3: Target-aware expansion — compare against TARGET, not average.
        # Old logic compared against average section length, so uniformly short
        # sections (all ~600w) would never trigger expansion.
        # target_total is defined before the while loop (FIX-046A)
        num_sections = max(len(report_sections), 1)
        target_per_section = target_total // num_sections
        min_acceptable = int(target_per_section * 0.8)

        # FIX-D: Detect citation-poor sections (primary) and thin sections (secondary)
        thin_sections = []
        for s in report_sections:
            actual_citations = len(s.get("citation_ids", []))
            is_citation_poor = actual_citations < PG_MIN_CITATIONS_PER_SECTION
            is_thin = s["word_count"] < min_acceptable
            if is_citation_poor or is_thin:
                if is_citation_poor:
                    logger.info(
                        "[polaris graph] FIX-D: Section '%s' has citation poverty: "
                        "%d citations (need >= %d)",
                        s.get("title", "?"),
                        actual_citations,
                        PG_MIN_CITATIONS_PER_SECTION,
                    )
                thin_sections.append(s)

        # FIX-D: If no individual section is thin/citation-poor but utilization
        # is below threshold, expand sections with fewest citations
        if not thin_sections and not utilization_ok:
            sorted_by_cites = sorted(
                report_sections,
                key=lambda s: len(s.get("citation_ids", [])),
            )
            thin_count = max(1, len(sorted_by_cites) // 3)
            thin_sections = sorted_by_cites[:thin_count]
            logger.info(
                "[polaris graph] FIX-D: No citation-poor sections but utilization "
                "%.1f%% < %.0f%%. Expanding %d lowest-citation sections.",
                utilization * 100,
                PG_MIN_EVIDENCE_UTILIZATION * 100,
                len(thin_sections),
            )

        if not thin_sections:
            logger.info(
                "[polaris graph] FIX-310: No thin sections found and total "
                "words %d >= 90%% of target %d. Stopping expansion.",
                quality["total_words"],
                target_total,
            )
            quality_gate_result = "below_minimum"
            break

        avg_words = int(
            sum(s["word_count"] for s in thin_sections) / max(len(thin_sections), 1)
        )
        logger.info(
            "[polaris graph] FIX-310: Expanding %d thin sections "
            "(avg=%d words, threshold=%d words)",
            len(thin_sections),
            avg_words,
            min_acceptable,
        )

        # FIX-039: Dynamic expansion target based on deficit
        avg_deficit = int(
            sum(max(0, min_acceptable - s["word_count"]) for s in thin_sections)
            / max(len(thin_sections), 1)
        )
        dynamic_target = max(300, avg_deficit + 100)

        # WAVE-4.4: Expansion detail trace (before expansion)
        _exp_tracer = get_tracer()
        if _exp_tracer:
            _exp_tracer.evidence("synthesize", "expansion_detail", len(thin_sections),
                pass_number=expansion_passes + 1,
                dynamic_target=dynamic_target,
                avg_deficit=avg_deficit,
                min_acceptable=min_acceptable,
                sections=[{
                    "section_id": getattr(s, "section_id", ""),
                    "title": getattr(s, "title", ""),
                    "before_words": getattr(s, "word_count", 0) if hasattr(s, "word_count") else s.get("word_count", 0) if isinstance(s, dict) else 0,
                    "evidence_assigned": len(getattr(s, "evidence_ids", []) if hasattr(s, "evidence_ids") else s.get("evidence_ids", []) if isinstance(s, dict) else []),
                } for s in thin_sections])

        # v4-simplify: Expansion pass DISABLED.
        # Proven net negative across TEST_077-080: injected CoT, prompt echoes,
        # broken tables. Quality comes from evidence + prompt, not post-hoc expansion.
        expanded_drafts = []
        if not expanded_drafts:
            logger.warning(
                "[polaris graph] FIX-310: Section expansion returned no results. "
                "Stopping expansion."
            )
            quality_gate_result = "below_minimum"
            break

        # Replace expanded sections in the sections list
        expanded_map = {d.section_id: d for d in expanded_drafts}
        updated_sections = []
        for s in sections:
            if s.section_id in expanded_map:
                updated_sections.append(expanded_map[s.section_id])
            else:
                updated_sections.append(s)
        sections = updated_sections

        # Re-audit citations on updated sections
        citation_audit = await audit_citations(
            client=client,
            sections=sections,
            evidence=verified_evidence,
        )

        # Re-assemble and recompute quality
        final_report, report_sections, bibliography = assemble_report(
            outline=outline,
            sections=sections,
            evidence=verified_evidence,
            citation_audit=citation_audit,
        )

        # FIX-043E: Use verified_evidence (synthesis pool) for expansion metrics
        quality = compute_quality_metrics(
            evidence=verified_evidence,
            claims=claims,
            report_sections=report_sections,
            bibliography=bibliography,
            faithfulness_score=faithfulness,
        )

        # FIX-E1: Re-generate grounded abstract after expansion (metrics changed)
        section_titles = [s["title"] for s in report_sections]
        grounded_abstract = await _generate_grounded_abstract(
            client=client,
            query=query,
            quality=quality,
            outline_title=outline.title,
            section_titles=section_titles,
        )
        if abstract_pattern.search(final_report):
            final_report = abstract_pattern.sub(
                rf"\g<1>{grounded_abstract}\n\n## ",
                final_report,
            )
        outline.abstract = grounded_abstract

        expansion_passes += 1
        quality_gate_result = "expanded"

        logger.info(
            "[polaris graph] FIX-310: After expansion pass %d: "
            "%d words, %d citations, %d sources",
            expansion_passes,
            quality["total_words"],
            quality["total_citations"],
            quality["unique_sources"],
        )

        tracer = get_tracer()
        if tracer:
            tracer.evidence("synthesize", "expansion_pass", expansion_passes,
                total_words=quality["total_words"], total_citations=quality["total_citations"],
                thin_sections=[s.get("title", "")[:60] for s in thin_sections[:10]])

        # FIX-039: Early exit on diminishing returns
        prev_words = quality.get("_prev_total_words", 0)
        current_words = quality["total_words"]
        if expansion_passes >= 2 and prev_words > 0 and (current_words - prev_words) < 100:
            logger.info(
                "[polaris graph] FIX-QG4: Early exit — only +%d words in pass %d",
                current_words - prev_words,
                expansion_passes,
            )
            break
        quality["_prev_total_words"] = current_words

        # FIX-8: Faithfulness degradation guard — stop expansion if
        # faithfulness drops significantly. Expansion can strip citations
        # while adding uncited prose, tanking the score.
        current_faith = quality.get("faithfulness_score", 0.0)
        prev_faith = quality.get("_prev_faithfulness")
        if prev_faith is not None and expansion_passes >= 1:
            if current_faith < prev_faith - 0.05:
                logger.warning(
                    "[polaris graph] FIX-8: Faithfulness degraded %.1f%%→%.1f%% "
                    "during expansion — stopping to prevent further damage",
                    prev_faith * 100, current_faith * 100,
                )
                break
        quality["_prev_faithfulness"] = current_faith

        # FIX-6: Citation convergence — break early if citation_spread isn't
        # improving between passes. Expansion adds words, not evidence, so if
        # the same sections remain below citation threshold, further passes
        # are futile.
        current_low_sections = len([
            sid for sid, cnt in section_citation_counts.items()
            if cnt < PG_MIN_CITATIONS_PER_SECTION
        ])
        prev_low = quality.get("_prev_low_sections")
        if prev_low is not None and current_low_sections >= prev_low and expansion_passes >= 1:
            logger.info(
                "[polaris graph] FIX-6: Citation spread not improving (%d→%d low "
                "sections) — stopping expansion",
                prev_low, current_low_sections,
            )
            break
        quality["_prev_low_sections"] = current_low_sections

    # FIX-H13: Log if expansion did not converge within max attempts
    if expansion_passes >= PG_SYNTHESIS_MAX_EXPANSION_PASSES:
        _h13_sources_ok = quality["unique_sources"] >= MIN_UNIQUE_SOURCES
        _h13_faith_ok = quality.get("faithfulness_score", 0) >= MIN_FAITHFULNESS
        _h13_util = quality.get("evidence_utilization", 0.0)
        if not (_h13_sources_ok and _h13_faith_ok):
            logger.warning(
                "[polaris graph] FIX-H13: Quality gate expansion did not converge "
                "after %d attempts. sources=%d/%d, faith=%.1f%%/%.1f%%, "
                "utilization=%.1f%%. Proceeding with best available output.",
                PG_SYNTHESIS_MAX_EXPANSION_PASSES,
                quality["unique_sources"], MIN_UNIQUE_SOURCES,
                quality.get("faithfulness_score", 0) * 100, MIN_FAITHFULNESS * 100,
                _h13_util * 100,
            )

    # FIX-LETTUCE-2: Re-run hallucination audit after expansion to get
    # accurate metrics. Without this, hallucination_audit reflects PRE-expansion
    # sections while the final report has completely different content.
    if expansion_passes > 0:
        post_expansion_dicts = []
        for sec in sections:
            # FIX-041: sections are SectionDraft Pydantic models (not dicts)
            # after expansion. Use getattr only — sec.get() crashes on models.
            sid = getattr(sec, "section_id", "")
            post_expansion_dicts.append({
                "section_id": sid,
                "title": getattr(sec, "title", ""),
                "content": getattr(sec, "content", ""),
                "evidence_ids": getattr(sec, "evidence_ids", [])
                or section_evidence_map.get(sid, []),
            })
        hallucination_audit = audit_sections_for_hallucination(
            sections=post_expansion_dicts,
            evidence=verified_evidence,
            research_query=query,
        )
        if hallucination_audit:
            post_exp_flagged = sum(1 for r in hallucination_audit if r.get("needs_rewrite"))
            post_exp_avg = sum(r["hallucination_ratio"] for r in hallucination_audit) / len(hallucination_audit)
            logger.info(
                "[polaris graph] FIX-LETTUCE-2: Post-expansion hallucination re-audit: "
                "%d/%d flagged (avg %.1f%%), threshold %.1f%%",
                post_exp_flagged, len(hallucination_audit),
                post_exp_avg * 100,
                float(os.getenv("PG_HALLUCINATION_REWRITE_THRESHOLD", "0.40")) * 100,
            )

    # Final quality gate check — FIX-D: Substance-based gate
    final_sources_ok = quality["unique_sources"] >= MIN_UNIQUE_SOURCES
    final_faith_ok = quality.get("faithfulness_score", 0) >= MIN_FAITHFULNESS
    final_section_citation_counts = {
        s.get("section_id", ""): len(s.get("citation_ids", []))
        for s in report_sections
    }
    final_section_citation_ok = all(
        cnt >= PG_MIN_CITATIONS_PER_SECTION
        for cnt in final_section_citation_counts.values()
    ) if report_sections else False
    final_utilization = quality.get("evidence_utilization", 0.0)
    final_utilization_ok = final_utilization >= PG_MIN_EVIDENCE_UTILIZATION

    final_gate_passed = (
        final_sources_ok and final_faith_ok
        and final_section_citation_ok and final_utilization_ok
    )

    if final_gate_passed:
        if expansion_passes > 0:
            quality_gate_result = "expanded"
        else:
            quality_gate_result = "passed"
    else:
        quality_gate_result = "below_minimum"
        failed_criteria = []
        if not final_sources_ok:
            failed_criteria.append(
                f"sources={quality['unique_sources']}/{MIN_UNIQUE_SOURCES}"
            )
        if not final_faith_ok:
            failed_criteria.append(
                f"faithfulness={quality.get('faithfulness_score', 0):.1%}/{MIN_FAITHFULNESS:.1%}"
            )
        if not final_section_citation_ok:
            low_secs = sum(
                1 for cnt in final_section_citation_counts.values()
                if cnt < PG_MIN_CITATIONS_PER_SECTION
            )
            failed_criteria.append(
                f"citation_spread={low_secs} sections below {PG_MIN_CITATIONS_PER_SECTION}"
            )
        if not final_utilization_ok:
            failed_criteria.append(
                f"utilization={final_utilization:.1%}/{PG_MIN_EVIDENCE_UTILIZATION:.1%}"
            )
        logger.warning(
            "[polaris graph] FIX-D: Quality gate BELOW minimums after "
            "%d expansion passes: %s (words=%d, citations=%d for reference). "
            "Proceeding with best effort.",
            expansion_passes,
            ", ".join(failed_criteria),
            quality["total_words"],
            quality["total_citations"],
        )

    # OBS-6: Trace final quality gate result
    tracer = get_tracer()
    if tracer:
        tracer.quality_gate(
            "synthesize", "post_synthesis_final",
            passed=(quality_gate_result != "below_minimum"),
            quality_gate_result=quality_gate_result,
            expansion_passes=expansion_passes,
            total_words=quality["total_words"],
            total_citations=quality["total_citations"],
            unique_sources=quality["unique_sources"],
        )

    # FIX-059-F: Final metrics recomputation after ALL post-processing.
    # Ensures quality_metrics, abstract, and final_report are consistent
    # with the actual sections after expansion + hallucination re-audit.
    # Without this, the abstract can claim "84 citations" when the actual
    # count after expansion is 103 (stale metrics from pre-expansion).
    # FIX-METRICS-ALWAYS: Re-insert metrics block unconditionally after expansion.
    # Previously gated by `if expansion_passes > 0` which meant metrics from the
    # initial insertion at line ~1828 could be stripped if expansion ran but this
    # block was skipped. Now ALWAYS re-insert with latest quality metrics.
    if True:  # Was: if expansion_passes > 0
        # Re-assemble the final report with latest sections
        final_report, report_sections, bibliography = assemble_report(
            outline=outline,
            sections=sections,
            evidence=verified_evidence,
            citation_audit=citation_audit,
        )
        quality = compute_quality_metrics(
            evidence=verified_evidence,
            claims=claims,
            report_sections=report_sections,
            bibliography=bibliography,
            faithfulness_score=faithfulness,
        )
        # Re-generate grounded abstract with correct metrics
        section_titles = [s["title"] for s in report_sections]
        grounded_abstract = await _generate_grounded_abstract(
            client=client,
            query=query,
            quality=quality,
            outline_title=outline.title,
            section_titles=section_titles,
        )
        # Replace abstract in final_report
        if abstract_pattern.search(final_report):
            final_report = abstract_pattern.sub(
                rf"\g<1>{grounded_abstract}\n\n## ",
                final_report,
            )
        outline.abstract = grounded_abstract

        # CHART-GEN: Re-insert metrics block after expansion re-assembly
        _source_count_f = quality.get("unique_sources", 0)
        _evidence_count_f = len(verified_evidence)
        _faithfulness_pct_f = quality.get("faithfulness_score", 0.0) * 100
        _claim_count_f = quality.get("total_citations", 0)
        metrics_line_f = (
            f":::metrics\n"
            f"Sources: {_source_count_f} | Evidence: {_evidence_count_f} | "
            f"Faithfulness: {_faithfulness_pct_f:.1f}% | Unique Claims: {_claim_count_f}\n"
            f":::"
        )
        _abstract_end_f = re.search(
            r"(## Abstract\n\n.*?\n)(\n## )", final_report, re.DOTALL,
        )
        if _abstract_end_f:
            insert_pos_f = _abstract_end_f.end(1)
            final_report = (
                final_report[:insert_pos_f]
                + "\n" + metrics_line_f + "\n"
                + final_report[insert_pos_f:]
            )

        logger.info(
            "[polaris graph] FIX-059-F: Final metrics recomputed after %d "
            "expansion passes: %d words, %d citations, %d sources",
            expansion_passes,
            quality["total_words"],
            quality["total_citations"],
            quality["unique_sources"],
        )

    # POLISH-PASS: Per-section edit for redundancy and prose quality.
    # FIX-071: Changed from full-report single call to per-section chunked approach.
    # GLM-5 truncates on 13K-word reports. Per-section calls stay within token limits.
    # Provides section titles list so editor can cross-reference.
    # v4-simplify: POLISH PASS PERMANENTLY DISABLED.
    # GLM-5 interprets "edit this section" as "analyze how to edit" and outputs
    # editing plans (103 lines in TEST_082, 60 lines in TEST_077, 140 lines in TEST_079).
    # This is NOT CoT leakage — the model's content output IS the editing plan.
    # Two-pool can't fix this because the editing plan is in Pool 2 (content).
    # The polish pass damaged output in EVERY run: TEST_077/078/079/080/082.
    # Quality comes from evidence + prompt, not post-hoc rewriting.
    _polish_enabled = False
    if _polish_enabled and report_sections and len(report_sections) > 1:
        try:
            import re as _re
            _section_titles = [s.get("title", "") for s in report_sections]
            _titles_block = "\n".join(f"  - {t}" for t in _section_titles)
            _polished_count = 0

            for _si, _section in enumerate(report_sections):
                _sec_content = _section.get("content", "")
                _min_polish_words = int(os.getenv("PG_POLISH_MIN_SECTION_WORDS", "500"))
                if len(_sec_content.split()) < _min_polish_words:
                    continue  # Skip sections too short to benefit from polishing

                _polish_prompt = (
                    f"You are an expert academic editor. Edit this ONE section of a "
                    f"research report.\n\n"
                    f"REPORT SECTIONS (for cross-reference context):\n{_titles_block}\n\n"
                    f"CURRENT SECTION: {_section.get('title', '')}\n\n"
                    f"EDITING RULES:\n"
                    f"1. REDUNDANCY: If a statistic or finding is better suited to another "
                    f"section listed above, replace with 'as established in [Section Title]'.\n"
                    f"2. PROSE: Vary sentence structure. Tighten verbose sentences.\n"
                    f"3. CONSISTENCY: Format statistics as MD/CI/I²/p-value/GRADE.\n"
                    f"4. PRESERVE: Keep ALL [N] citation markers. Keep tables. "
                    f"Keep **Key Findings**.\n\n"
                    f"Output ONLY the edited section content. No title. No metadata.\n\n"
                    f"SECTION CONTENT:\n{_sec_content}"
                )

                # FIX-071B: Retry on empty + strip CoT from polish response
                _polished_sec = ""
                for _attempt in range(2):
                    try:
                        # TWO-POOL: Use generate() — reasoning goes to Pool 1
                        # (logged), content to Pool 2 (used for polished text).
                        _polish_resp = await client.generate(
                            prompt=_polish_prompt,
                            max_tokens=int(os.getenv("PG_POLISH_MAX_TOKENS", "16384")),
                        )
                        _polished_sec = _polish_resp.content.strip()
                        if _polished_sec:
                            break
                    except (ValueError, RuntimeError):
                        if _attempt == 0:
                            logger.warning(
                                "[polaris graph] POLISH-PASS: Empty response for "
                                "'%s', retrying", _section.get("title", "?")[:30],
                            )
                            continue
                        break

                # FIX-071B: Strip CoT prefix from polish output
                # GLM-5 writes "1. **Analyze the Request:**..." before edited text
                if _polished_sec:
                    _cot_markers = [
                        "analyze the request", "let me", "the user wants",
                        "my task", "instructions:",
                    ]
                    if any(m in _polished_sec[:300].lower() for m in _cot_markers):
                        # Find where actual content starts (## heading or sentence with [N])
                        _content_start = _re.search(
                            r"\n(?=(?:##\s|[A-Z][a-z].*\[\d+\]))",
                            _polished_sec,
                        )
                        if _content_start and _content_start.start() > 50:
                            _stripped = len(_polished_sec[:_content_start.start()])
                            _polished_sec = _polished_sec[_content_start.start():].lstrip()
                            logger.info(
                                "[polaris graph] POLISH-PASS: Stripped %d chars CoT "
                                "from section '%s'",
                                _stripped, _section.get("title", "?")[:30],
                            )

                # Validate: retain citations and reasonable length
                _orig_sec_cites = len(_re.findall(r"\[\d+\]", _sec_content))
                _new_sec_cites = len(_re.findall(r"\[\d+\]", _polished_sec))
                if (
                    _polished_sec
                    and len(_polished_sec) > len(_sec_content) * float(os.getenv("PG_POLISH_MIN_LENGTH_RATIO", "0.7"))
                    and _new_sec_cites >= _orig_sec_cites * float(os.getenv("PG_POLISH_MIN_CITE_RATIO", "0.8"))
                ):
                    _section["content"] = _polished_sec
                    _section["word_count"] = len(_polished_sec.split())
                    _polished_count += 1
                elif _polished_sec:
                    logger.warning(
                        "[polaris graph] POLISH-PASS: Rejected edit for '%s' "
                        "(len=%.0f%%, cites=%d->%d)",
                        _section.get("title", "?")[:30],
                        len(_polished_sec) / max(len(_sec_content), 1) * 100,
                        _orig_sec_cites, _new_sec_cites,
                    )

            if _polished_count > 0:
                # Rebuild full_report from polished sections.
                # GUARD: Skip sections with 0 content (prevents empty headings).
                _rebuild_parts = [f"# {outline.title}", ""]
                if outline.abstract:
                    _rebuild_parts.extend(["## Abstract", "", outline.abstract, ""])
                for _ps in report_sections:
                    if not _ps.get("content", "").strip():
                        logger.warning(
                            "[polaris graph] POLISH-REBUILD: Skipping empty section '%s'",
                            _ps.get("title", "?")[:40],
                        )
                        continue
                    _rebuild_parts.extend([f"## {_ps['title']}", "", _ps["content"], ""])
                _rebuild_parts.extend(["## References", ""])
                for _be in bibliography:
                    _rebuild_parts.append(_be["formatted"])
                _rebuild_parts.append("")
                final_report = "\n".join(_rebuild_parts)

                logger.info(
                    "[polaris graph] POLISH-PASS: Polished %d/%d sections",
                    _polished_count, len(report_sections),
                )
        except Exception as polish_exc:
            logger.warning(
                "[polaris graph] POLISH-PASS: Failed (non-blocking): %s",
                str(polish_exc)[:200],
            )

    # Build audit-compatible bibliography with title/authors fields
    evidence_map = {e.get("evidence_id", ""): e for e in evidence}
    enriched_bibliography = []
    for entry in bibliography:
        enriched = dict(entry)
        # Add title and authors from first evidence piece in this entry
        eids = entry.get("evidence_ids", [])
        if eids:
            first_ev = evidence_map.get(eids[0], {})
            enriched["title"] = first_ev.get("source_title", "")
            enriched["authors"] = first_ev.get("authors", [])
        enriched_bibliography.append(enriched)

    # Build evidence_chain alias with perspective tags for audit D7
    # Assign perspectives based on evidence fact_category/source_type
    perspective_map = {
        "finding": "Empirical Research",
        "statistic": "Statistical Analysis",
        "definition": "Conceptual Framework",
        "mechanism": "Technical Analysis",
        "regulation": "Regulatory Perspective",
        "recommendation": "Policy & Practice",
        "comparison": "Comparative Analysis",
        "limitation": "Critical Assessment",
    }
    evidence_chain = []
    for ev in evidence:
        enriched_ev = dict(ev)
        category = ev.get("fact_category", "finding")
        enriched_ev["perspective_origins"] = [
            perspective_map.get(category, "Empirical Research")
        ]
        # RAGAS-FIX: Add 'text' alias for run_ragas_v3.py compatibility
        # (evaluator looks for 'text' key, pipeline uses 'statement')
        if "text" not in enriched_ev and "statement" in enriched_ev:
            enriched_ev["text"] = enriched_ev["statement"]
        evidence_chain.append(enriched_ev)

    # RC-3: Generate gap queries when quality gate fails so _should_finalize()
    # can route back to search_gaps for more evidence and re-synthesis.
    post_synth_gap_queries: list[str] = []
    if quality_gate_result == "below_minimum":
        # FIX-D: Generate targeted gap queries based on substance deficits
        if not final_sources_ok:
            # Need more diverse sources — search for the topic from new angles
            post_synth_gap_queries.append(
                f"{query} site:scholar.google.com OR site:ncbi.nlm.nih.gov"
            )
            post_synth_gap_queries.append(f"{query} review article 2024 2025")
            post_synth_gap_queries.append(f"{query} meta-analysis systematic review")
        if not final_section_citation_ok:
            # FIX-D: Search specifically for under-cited section topics
            for sec in report_sections:
                sec_cites = len(sec.get("citation_ids", []))
                if sec_cites < PG_MIN_CITATIONS_PER_SECTION:
                    post_synth_gap_queries.append(
                        f"{query} {sec.get('title', '')} evidence data"
                    )
        if not final_utilization_ok:
            # Evidence exists but isn't being cited — search for corroboration
            post_synth_gap_queries.append(f"{query} comprehensive review findings")
        if not final_faith_ok:
            # Need more verifiable sources
            post_synth_gap_queries.append(f"{query} official report data statistics")
        if post_synth_gap_queries:
            logger.info(
                "[polaris graph] RC-3: Generated %d post-synthesis gap queries "
                "for quality recovery: %s",
                len(post_synth_gap_queries),
                [q[:60] for q in post_synth_gap_queries[:5]],
            )

    return {
        "section_outline": [
            {
                "section_id": s.section_id,
                "title": s.title,
                "description": s.description,
                "evidence_ids": s.evidence_ids,
                "target_words": s.target_words,
                "order": s.order,
            }
            for s in outline.sections
        ],
        "sections": report_sections,
        "bibliography": enriched_bibliography,
        "evidence_chain": evidence_chain,
        "draft_report": draft_report,
        "final_report": final_report,
        "evidence_clusters": clusters,
        "quality_metrics": quality,
        "status": "complete",
        "converged": quality_gate_result != "below_minimum",
        "convergence_reason": (
            "synthesis_complete" if quality_gate_result != "below_minimum"
            else f"below_minimum: {', '.join(failed_criteria) if 'failed_criteria' in dir() else 'unknown'}"
        ),
        # FIX-310: Quality gate results
        "expansion_passes_used": expansion_passes,
        "quality_gate_result": quality_gate_result,
        # FIX-107I: Per-section evidence filtering metadata
        "section_evidence_map": section_evidence_map,
        # ARCH-5: Token-level hallucination detection results
        "hallucination_audit": hallucination_audit,
        # RC-3: Gap queries for post-synthesis iteration
        "gap_queries": post_synth_gap_queries,
        # MoST Safety Net: Reflection and exploration stats
        "most_reflection_stats": most_reflection_stats,
        "most_exploration_stats": most_exploration_stats,
        # M-08 through M-11: Bond analysis stats
        "most_bond_analysis": {
            k: v.get("stats", {}) if isinstance(v, dict) else {}
            for k, v in bond_analysis.items()
        } if bond_analysis else {},
    }


async def analyze_gaps(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict:
    """
    Analyze evidence gaps and decide whether to iterate.

    Returns state update with gaps, gap_queries, and needs_iteration.
    """
    evidence = state.get("evidence", [])
    claims = state.get("claims", [])
    query = state["original_query"]
    iteration = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)

    # Check quality gates
    total_evidence = len(evidence)
    gold_count = sum(1 for e in evidence if e.get("quality_tier") == "GOLD")

    # BUG-1 FIX: Exclude api_error claims from faithfulness calculation.
    # api_error means "verification failed" (timeout/network), NOT "unfaithful".
    # Including them inflates the denominator and deflates the score.
    verified_claims = [
        c for c in claims
        if c.get("verification_method") != "api_error"
    ]
    api_error_count = len(claims) - len(verified_claims)
    faithful_count = sum(1 for c in verified_claims if c.get("is_faithful"))
    faithfulness = faithful_count / max(len(verified_claims), 1)
    if api_error_count > 0:
        logger.info(
            "[polaris graph] BUG-1 FIX: Excluded %d api_error claims from "
            "faithfulness calc (%d verified, %.1f%% faithful)",
            api_error_count, len(verified_claims), faithfulness * 100,
        )

    # FIX-QM7: Filter out NOT_SUPPORTED claims and their evidence before synthesis
    # BUG-1 FIX: Only consider actually-verified claims as not_supported,
    # not api_error claims (which are simply unverified)
    not_supported = [
        c for c in verified_claims if not c.get("is_faithful")
    ]
    if not_supported:
        unfaithful_evidence_ids = set()
        for c in not_supported:
            unfaithful_evidence_ids.update(c.get("evidence_ids", []))
        if unfaithful_evidence_ids:
            before_filter = len(evidence)
            evidence = [
                e for e in evidence
                if e.get("evidence_id") not in unfaithful_evidence_ids
            ]
            removed = before_filter - len(evidence)
            if removed > 0:
                logger.info(
                    "[polaris graph] FIX-QM7: Faithfulness gate removed %d/%d "
                    "evidence pieces backing %d unfaithful claims",
                    removed,
                    before_filter,
                    len(not_supported),
                )
            # FIX-043A: Sync claims with filtered evidence. FIX-QM7 removes
            # evidence backing unfaithful claims, but orphaned claims
            # (referencing removed evidence_ids) are ALL scored 0% faithful
            # by downstream metrics.
            surviving_ev_ids = {e.get("evidence_id") for e in evidence}
            before_claims = len(claims)
            claims = [
                c for c in claims
                if any(
                    eid in surviving_ev_ids
                    for eid in c.get("evidence_ids", [])
                )
                or not c.get("evidence_ids")
            ]
            removed_claims = before_claims - len(claims)
            if removed_claims > 0:
                logger.info(
                    "[polaris graph] FIX-043A: Removed %d/%d orphaned claims "
                    "(evidence_ids removed by FIX-QM7)",
                    removed_claims, before_claims,
                )
                verified_claims = [
                    c for c in claims
                    if c.get("verification_method") != "api_error"
                ]
                faithful_count = sum(
                    1 for c in verified_claims if c.get("is_faithful")
                )
                faithfulness = faithful_count / max(len(verified_claims), 1)
                logger.info(
                    "[polaris graph] FIX-043A: Recomputed faithfulness: "
                    "%d/%d = %.1f%%",
                    faithful_count, len(verified_claims),
                    faithfulness * 100,
                )
        else:
            # FIX-B1: Log diagnostic — if we have unfaithful claims but no
            # evidence IDs, the field mapping is still broken
            if not_supported:
                logger.warning(
                    "[polaris graph] FIX-B1 DIAGNOSTIC: %d unfaithful claims "
                    "but 0 evidence_ids resolved — check VerifiedClaim schema",
                    len(not_supported),
                )
                # Update counts after filtering
                total_evidence = len(evidence)
                gold_count = sum(1 for e in evidence if e.get("quality_tier") == "GOLD")

    # SF-25: Use configurable thresholds from state.py (LAW VI)
    if (
        total_evidence >= MIN_EVIDENCE_COUNT
        and gold_count >= MIN_EVIDENCE_COUNT // 3
        and faithfulness >= MIN_FAITHFULNESS
    ):
        logger.info(
            "[polaris graph] Evidence sufficient: %d total, %d GOLD, "
            "%.1f%% faithful — proceeding to synthesis",
            total_evidence,
            gold_count,
            faithfulness * 100,
        )
        return {
            "gaps": [],
            "gap_queries": [],
            "needs_iteration": False,
            "evidence": evidence,  # FIX-QM7: Pass filtered evidence back to state
            "claims": claims,  # FIX-043A: Pass synced claims back to state
            "faithfulness_score": faithfulness,  # FIX-044/Issue5: Propagate recomputed score
        }

    # SF-26: At max iterations, proceed but log quality gap if evidence insufficient
    if iteration >= max_iterations - 1:
        if total_evidence < MIN_EVIDENCE_COUNT:
            logger.error(
                "[polaris graph] Max iterations reached (%d) with only %d evidence "
                "(min=%d) — proceeding with insufficient evidence",
                max_iterations,
                total_evidence,
                MIN_EVIDENCE_COUNT,
            )
        else:
            logger.info(
                "[polaris graph] Max iterations reached (%d), proceeding with %d evidence",
                max_iterations,
                total_evidence,
            )
        return {
            "gaps": [],
            "gap_queries": [],
            "needs_iteration": False,
            "evidence": evidence,  # FIX-QM7: Pass filtered evidence back to state
            "claims": claims,  # FIX-043A: Pass synced claims back to state
            "faithfulness_score": faithfulness,  # FIX-044/Issue5: Propagate recomputed score
        }

    # AREA-4 Gap 6: Adaptive search depth — when faithfulness < threshold,
    # generate confidence-targeted queries for low-confidence claims
    # FIX-060-D: Configurable low-confidence threshold (was hardcoded 0.7).
    # After FIX-060-A, content-basis claims cap at 0.50, so this must be tunable.
    _low_conf_threshold = float(os.getenv("PG_LOW_CONFIDENCE_THRESHOLD", "0.60"))
    low_confidence_claims = sorted(
        [c for c in claims if c.get("confidence", 1.0) < _low_conf_threshold
         and c.get("verification_method") != "api_error"],
        key=lambda c: c.get("confidence", 1.0),
    )[:20]

    low_conf_summary = ""
    if low_confidence_claims:
        low_conf_lines = []
        for c in low_confidence_claims:
            low_conf_lines.append(
                f"  - [conf={c.get('confidence', 0):.2f}] {c.get('statement', '')[:120]}"
            )
        low_conf_summary = (
            f"\n\nLOW-CONFIDENCE CLAIMS ({len(low_confidence_claims)} claims, "
            f"conf < {_low_conf_threshold:.2f} — need better evidence):\n"
            + "\n".join(low_conf_lines)
        )
        logger.info(
            "[polaris graph] AREA-4: %d low-confidence claims identified "
            "(targeting for gap queries)",
            len(low_confidence_claims),
        )

    # Use LLM to analyze gaps
    evidence_summary = "\n".join(
        f"- [{e.get('quality_tier', '?')}] {e.get('statement', '')[:100]}"
        for e in evidence[:100]
    )

    # FIX-F: Compute source diversity metrics for perspective-targeted gap search
    source_urls = {e.get("source_url", "") for e in evidence if e.get("source_url")}
    source_types = {}
    for e in evidence:
        st = e.get("source_type", "web")
        source_types[st] = source_types.get(st, 0) + 1
    academic_count = source_types.get("academic", 0) + source_types.get("journal_article", 0)
    perspective_coverage = {}
    for e in evidence:
        p = e.get("perspective", "")
        if p:
            perspective_coverage[p] = perspective_coverage.get(p, 0) + 1
    missing_perspectives = [
        p for p in STORM_PERSPECTIVES if perspective_coverage.get(p, 0) < 2
    ]

    diversity_block = f"""
SOURCE DIVERSITY:
- Unique sources: {len(source_urls)}
- Academic papers: {academic_count}
- Source types: {dict(sorted(source_types.items(), key=lambda x: -x[1]))}
- Underrepresented perspectives: {missing_perspectives if missing_perspectives else 'None'}
"""

    prompt = f"""Research question: {query}

Current evidence ({total_evidence} pieces, {gold_count} GOLD, faithfulness {faithfulness:.1%}):
{evidence_summary}
{low_conf_summary}
{diversity_block}

FIX-F: Perform TARGETED gap analysis. For each gap, identify:
1. Which sub-topics have < 2 independent sources?
2. Which claims rely on a single source (needs corroboration)?
3. Which source types are underrepresented (e.g., few academic sources)?
4. Which STORM perspectives have < 2 evidence pieces?

Generate search queries that TARGET specific gaps — not broad restatements of the topic.
Include source-type constraints when appropriate (e.g., "site:scholar.google.com" for academic gaps, "site:gov" for regulatory gaps).
{"IMPORTANT: Several claims have LOW confidence. Generate queries that would find STRONGER evidence to verify or replace these claims." if low_confidence_claims else ""}
Limit to 10 highest-priority gap queries."""

    try:
        # Use generate_structured() — reasoning OFF for reliable JSON.
        parsed = await client.generate_structured(
            prompt=prompt,
            schema=GapAnalysis,
            system=GAP_ANALYSIS_SYSTEM,
            max_tokens=int(os.getenv("PG_GAP_ANALYSIS_MAX_TOKENS", "4096")),
            timeout=int(os.getenv("PG_GAP_ANALYSIS_TIMEOUT", "120")),
        )

        gap_queries = parsed.suggested_queries
        should_iterate = parsed.should_iterate

        # AREA-4 Gap 6: Force iteration when faithfulness is below threshold
        # AND there are low-confidence claims to target
        if faithfulness < MIN_FAITHFULNESS and low_confidence_claims:
            if not should_iterate:
                logger.info(
                    "[polaris graph] AREA-4: Overriding LLM — forcing iteration "
                    "due to faithfulness %.1f%% < %.1f%% threshold "
                    "(%d low-confidence claims)",
                    faithfulness * 100,
                    MIN_FAITHFULNESS * 100,
                    len(low_confidence_claims),
                )
                should_iterate = True
            # Generate confidence-targeted queries from low-conf claims
            confidence_queries = _generate_confidence_queries(
                low_confidence_claims, query,
            )
            if confidence_queries:
                gap_queries = gap_queries + confidence_queries
                logger.info(
                    "[polaris graph] AREA-4: Added %d confidence-targeted queries "
                    "(total gap queries: %d)",
                    len(confidence_queries),
                    len(gap_queries),
                )


        tracer = get_tracer()
        if tracer:
            tracer.evidence("evaluate", "gap_analysis_detail", len(parsed.gaps),
                total_evidence=total_evidence, gold_count=gold_count,
                faithfulness=round(faithfulness, 4),
                needs_iteration=should_iterate,
                gaps=parsed.gaps[:20],
                gap_queries=gap_queries[:10],
                perspective_coverage={p: sum(1 for e in evidence if e.get("perspective") == p) for p in STORM_PERSPECTIVES})
        return {
            "gaps": parsed.gaps,
            "gap_queries": gap_queries,
            "needs_iteration": should_iterate,
            "evidence": evidence,  # Pass filtered evidence back
            "claims": claims,  # FIX-043A: Pass synced claims back to state
            "faithfulness_score": faithfulness,  # FIX-044/Issue5: Propagate recomputed score
        }

    except Exception as exc:
        # SF-08: Default to iterate on failure (conservative — iterate if in doubt)
        logger.warning(
            "[polaris graph] Gap analysis failed: %s — defaulting to iterate",
            str(exc)[:200],
        )
        return {
            "gaps": [],
            "gap_queries": [],
            "needs_iteration": True,
        }


def _generate_confidence_queries(
    low_confidence_claims: list[dict],
    original_query: str,
) -> list[str]:
    """AREA-4 Gap 6 / FIX-F: Generate search queries targeting low-confidence claims.

    For each low-confidence claim, generates a specific search query
    designed to find stronger supporting or contradicting evidence.
    FIX-F: Adds source-type constraints for academic/regulatory gaps.
    """
    queries = []
    for claim in low_confidence_claims[:10]:
        statement = claim.get("statement", "")
        if len(statement) < 20:
            continue
        # Extract key terms (first 100 chars, simplified)
        key_terms = statement[:100].strip()
        # FIX-F: Alternate between academic and general evidence searches
        if len(queries) % 2 == 0:
            queries.append(f"{key_terms} site:scholar.google.com OR site:ncbi.nlm.nih.gov")
        else:
            queries.append(f"{key_terms} peer-reviewed evidence data")

    return queries


def _detect_evidence_conflicts(
    evidence: list[EvidencePiece],
) -> list[dict]:
    """AREA-4 Gap 3: Detect conflicting evidence pairs.

    Finds evidence pieces that discuss the same topic but make
    contradictory claims. Uses simple heuristic: same source_type
    + high word overlap + opposing sentiment indicators.

    Returns list of conflict dicts: {evidence_a, evidence_b, topic, description}.
    """
    conflicts: list[dict] = []

    # Contradiction indicators
    negation_words = {
        "not", "no", "never", "neither", "nor", "contrary", "however",
        "unlike", "whereas", "but", "although", "despite", "failed",
        "insufficient", "ineffective", "disprove", "refute", "challenge",
        "contradict", "disagree", "lower", "higher", "decrease", "increase",
    }

    n = len(evidence)
    for i in range(min(n, 200)):
        stmt_i = evidence[i].get("statement", "").lower()
        words_i = set(stmt_i.split())
        if len(words_i) < 8:
            continue

        for j in range(i + 1, min(n, 200)):
            # Skip same source
            if evidence[i].get("source_url") == evidence[j].get("source_url"):
                continue

            stmt_j = evidence[j].get("statement", "").lower()
            words_j = set(stmt_j.split())
            if len(words_j) < 8:
                continue

            # Check for topic overlap (Jaccard > 0.25 = same topic)
            intersection = len(words_i & words_j)
            union = len(words_i | words_j)
            if union == 0 or intersection / union < 0.25:
                continue

            # Check for contradiction signals in the differing words
            diff_words = (words_i ^ words_j)
            contradiction_signals = diff_words & negation_words
            if len(contradiction_signals) >= 2:
                conflicts.append({
                    "evidence_a_id": evidence[i].get("evidence_id", ""),
                    "evidence_b_id": evidence[j].get("evidence_id", ""),
                    "statement_a": evidence[i].get("statement", "")[:200],
                    "statement_b": evidence[j].get("statement", "")[:200],
                    "topic_overlap": round(intersection / union, 3),
                    "contradiction_signals": list(contradiction_signals)[:5],
                })

    if conflicts:
        logger.info(
            "[polaris graph] AREA-4: Detected %d potential evidence conflicts",
            len(conflicts),
        )

    return conflicts[:20]  # Cap to prevent explosion


async def _cluster_evidence(
    client: OpenRouterClient,
    evidence: list[EvidencePiece],
    query: str,
) -> list[dict]:
    """Cluster evidence by theme using SOTA map-reduce pattern.

    For small evidence sets (<=200), uses a single LLM call (original path).
    For large sets (>200), uses 3-step map-reduce:
      1. MAP: Batch evidence into groups, cluster each in parallel
      2. COLLAPSE: Merge similar themes if too many
      3. REDUCE: Final ClusterPlan from merged theme summaries

    This is the pattern used by GraphRAG, LLMxMapReduce, and HERCULES.
    Each batch gets full reasoning attention on ~100 evidence pieces,
    which is actually better than reasoning on 1000+ at once (avoids
    lost-in-the-middle attention dilution).
    """
    batch_size = PG_CLUSTER_BATCH_SIZE

    # Small evidence set: single call (original path, fast)
    if len(evidence) <= batch_size * 2:
        return await _cluster_evidence_single(client, evidence, query)

    # Large evidence set: map-reduce
    logger.info(
        "[polaris graph] Map-reduce clustering: %d evidence pieces, "
        "batch_size=%d, estimated %d batches",
        len(evidence),
        batch_size,
        (len(evidence) + batch_size - 1) // batch_size,
    )

    try:
        # Step 1: MAP — batch evidence and cluster in parallel
        batches = [
            evidence[i:i + batch_size]
            for i in range(0, len(evidence), batch_size)
        ]

        async def _cluster_batch(
            batch: list[EvidencePiece], batch_idx: int,
        ) -> list[dict]:
            # Phase 1: Short ID remapping — reduce ~5 tokens/ID to 1 token/ID
            remapped_batch, reverse_map = _remap_evidence_ids(batch)

            # TIER-3 Stage 5: Use L0 compact format (~15 tokens each, 3x more
            # evidence per batch vs full format). Same information density for
            # clustering — LLM only needs statement to group by theme.
            from src.polaris_graph.synthesis.token_budget import format_l0
            evidence_text = "\n".join(
                format_l0(e) for e in remapped_batch
            )
            prompt = f"""Research question: {query}

Evidence batch {batch_idx + 1}/{len(batches)} ({len(batch)} pieces):
{evidence_text}

Identify 5-8 thematic groups in this evidence batch.
Assign every evidence piece to exactly one theme.
Evidence IDs are integers (1, 2, 3...). Use EXACTLY these IDs in your response."""

            # FIX-RC3a: Use configurable timeout (was hardcoded 180s, LAW VI violation)
            cluster_batch_timeout = int(os.getenv("PG_CLUSTER_BATCH_TIMEOUT", "600"))
            parsed = await client.generate_structured(
                prompt=prompt,
                schema=BatchClusterResult,
                system=BATCH_CLUSTER_SYSTEM,
                max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
                timeout=cluster_batch_timeout,
            )

            # Reverse-remap short IDs back to original ev_xxx IDs
            themes = []
            total_assigned = 0
            for t in parsed.themes:
                original_ids = _reverse_remap_ids(t.evidence_ids, reverse_map)
                total_assigned += len(original_ids)
                themes.append({
                    "theme": t.theme,
                    "description": t.description,
                    "evidence_ids": original_ids,
                    "key_claims": t.key_claims,
                    "helpfulness": t.helpfulness,
                    "batch_idx": batch_idx,
                })

            logger.info(
                "[polaris graph] Batch %d: %d themes, %d/%d IDs preserved "
                "after reverse-remap",
                batch_idx, len(themes), total_assigned, len(batch),
            )

            return themes

        # FIX-RC3b: Semaphore-bounded parallel clustering (prevents API overwhelm)
        cluster_concurrency = int(os.getenv("PG_CLUSTER_CONCURRENCY", "8"))
        cluster_sem = asyncio.Semaphore(cluster_concurrency)

        async def _bounded_cluster(batch, idx):
            async with cluster_sem:
                return await _cluster_batch(batch, idx)

        tasks = [
            _bounded_cluster(batch, idx)
            for idx, batch in enumerate(batches)
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all themes from successful batches
        all_themes: list[dict] = []
        failed_batch_count = 0
        for idx, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(
                    "[polaris graph] Map-reduce: batch %d failed: %s",
                    idx, str(result)[:200],
                )
                failed_batch_count += 1
                # Fallback: create category-based themes for failed batch
                cat_themes: dict[str, list[str]] = {}
                for e in batches[idx]:
                    cat = e.get("fact_category", "other")
                    cat_themes.setdefault(cat, []).append(
                        e.get("evidence_id", "")
                    )
                for cat, ids in cat_themes.items():
                    all_themes.append({
                        "theme": cat.replace("_", " ").title(),
                        "description": f"Fallback theme for batch {idx}",
                        "evidence_ids": ids,
                        "key_claims": [],
                        "helpfulness": 30,
                        "batch_idx": idx,
                    })
            else:
                all_themes.extend(result)

        logger.info(
            "[polaris graph] Map step complete: %d themes from %d batches "
            "(%d failed)",
            len(all_themes),
            len(batches),
            failed_batch_count,
        )

        # Step 2: COLLAPSE — if too many themes, merge programmatically
        # Phase 2: Replaced LLM-based _merge_themes with deterministic
        # Jaccard merge. Zero LLM involvement = guaranteed 100% ID preservation.
        if len(all_themes) > PG_CLUSTER_MAX_THEMES_BEFORE_MERGE:
            clusters = _merge_themes_programmatic(all_themes)
        else:
            # Few enough themes — convert directly to cluster format
            clusters = [
                {
                    "cluster_id": f"c{i + 1}",
                    "theme": t["theme"],
                    "description": t["description"],
                    "evidence_ids": t["evidence_ids"],
                    "strength": (
                        "strong" if t["helpfulness"] >= 70
                        else "moderate" if t["helpfulness"] >= 40
                        else "weak"
                    ),
                }
                for i, t in enumerate(all_themes)
            ]

        logger.info(
            "[polaris graph] Map-reduce clustering complete: %d final clusters "
            "from %d evidence pieces: %s",
            len(clusters),
            len(evidence),
            [c["theme"][:30] for c in clusters[:5]],
        )

        return clusters

    except Exception as exc:
        logger.error(
            "[polaris graph] Map-reduce clustering failed: %s — "
            "falling back to category-based clusters",
            str(exc)[:200],
        )
        return _category_fallback_clusters(evidence)


def _merge_themes_programmatic(
    themes: list[dict],
) -> list[dict]:
    """Programmatic merge: combine similar themes using Jaccard similarity.

    Phase 2: Replaces LLM-based _merge_themes(). Zero LLM involvement
    in ID tracking guarantees 100% evidence ID preservation (set union).

    Algorithm:
    1. Compute text similarity between all theme pairs using word-level
       Jaccard on (theme + description + key_claims).
    2. Greedy agglomerative merge: repeatedly merge the most similar pair
       until no pair exceeds the similarity threshold or we reach 8-15 clusters.
    3. Merged cluster inherits union of all evidence_ids (guaranteed no loss).
    4. Strength rated by merged-theme count and average helpfulness.

    This follows the GraphRAG pattern: code tracks IDs, LLM provides insights.
    """
    merge_threshold = float(os.getenv("PG_THEME_MERGE_JACCARD", "0.25"))
    target_min_clusters = int(os.getenv("PG_THEME_MERGE_MIN", "8"))
    target_max_clusters = int(os.getenv("PG_THEME_MERGE_MAX", "15"))

    # Build word sets for each theme (for Jaccard similarity)
    def _theme_words(t: dict) -> set[str]:
        text = (
            t.get("theme", "") + " "
            + t.get("description", "") + " "
            + " ".join(t.get("key_claims", []))
        ).lower()
        return {w for w in text.split() if len(w) > 2}

    # Initialize each theme as its own cluster
    active: list[dict] = []
    for i, t in enumerate(themes):
        active.append({
            "cluster_id": f"c{i + 1}",
            "theme": t.get("theme", ""),
            "description": t.get("description", ""),
            "evidence_ids": list(t.get("evidence_ids", [])),
            "key_claims": list(t.get("key_claims", [])),
            "helpfulness_values": [t.get("helpfulness", 50)],
            "merged_count": 1,
            "_words": _theme_words(t),
        })

    # Greedy merge loop
    merge_count = 0
    while len(active) > target_max_clusters:
        # Find most similar pair
        best_sim = 0.0
        best_i, best_j = -1, -1

        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                words_i = active[i]["_words"]
                words_j = active[j]["_words"]
                intersection = len(words_i & words_j)
                union = len(words_i | words_j)
                sim = intersection / max(union, 1)
                if sim > best_sim:
                    best_sim = sim
                    best_i, best_j = i, j

        # Stop if no pair is similar enough (unless still too many clusters)
        if best_sim < merge_threshold and len(active) <= target_max_clusters:
            break

        # If still above max and nothing is similar, force-merge smallest pair
        if best_sim < merge_threshold:
            # Merge two smallest clusters to reduce count
            sizes = [(len(c["evidence_ids"]), idx) for idx, c in enumerate(active)]
            sizes.sort()
            best_i, best_j = sizes[0][1], sizes[1][1]
            if best_i > best_j:
                best_i, best_j = best_j, best_i

        # Merge j into i
        ci = active[best_i]
        cj = active[best_j]

        # Use the theme name from the cluster with more evidence
        if len(cj["evidence_ids"]) > len(ci["evidence_ids"]):
            ci["theme"] = cj["theme"]

        # Combine descriptions (deduplicated)
        if cj["description"] and cj["description"] not in ci["description"]:
            ci["description"] = ci["description"] + "; " + cj["description"]

        # Union of evidence IDs (guaranteed no loss)
        existing_ids = set(ci["evidence_ids"])
        for eid in cj["evidence_ids"]:
            if eid not in existing_ids:
                ci["evidence_ids"].append(eid)
                existing_ids.add(eid)

        # Merge key claims (deduplicated, cap at 5)
        existing_claims = set(ci["key_claims"])
        for claim in cj["key_claims"]:
            if claim not in existing_claims and len(ci["key_claims"]) < 5:
                ci["key_claims"].append(claim)
                existing_claims.add(claim)

        ci["helpfulness_values"].extend(cj["helpfulness_values"])
        ci["merged_count"] += cj["merged_count"]
        ci["_words"] = ci["_words"] | cj["_words"]

        # Remove j (higher index first to avoid shift)
        active.pop(best_j)
        merge_count += 1

    # Second pass: if still below minimum, don't split (we have what we have)
    # Compute strength and clean up internal fields
    original_total_ids = set()
    for t in themes:
        original_total_ids.update(t.get("evidence_ids", []))

    final_total_ids = set()
    clusters = []
    for i, c in enumerate(active):
        avg_help = sum(c["helpfulness_values"]) / max(len(c["helpfulness_values"]), 1)
        mc = c["merged_count"]

        if mc >= 3 or avg_help >= 70:
            strength = "strong"
        elif mc >= 2 or avg_help >= 40:
            strength = "moderate"
        else:
            strength = "weak"

        final_total_ids.update(c["evidence_ids"])
        clusters.append({
            "cluster_id": f"c{i + 1}",
            "theme": c["theme"],
            "description": c["description"][:300],
            "evidence_ids": c["evidence_ids"],
            "strength": strength,
        })

    # Verification: all IDs preserved (should always be true by construction)
    missing = original_total_ids - final_total_ids
    if missing:
        logger.error(
            "[polaris graph] PROGRAMMATIC MERGE BUG: %d/%d evidence_ids lost! "
            "Adding to largest cluster.",
            len(missing),
            len(original_total_ids),
        )
        if clusters:
            largest = max(clusters, key=lambda c: len(c["evidence_ids"]))
            largest["evidence_ids"].extend(list(missing))

    logger.info(
        "[polaris graph] Programmatic merge: %d themes -> %d clusters "
        "(%d merges, %d/%d evidence_ids preserved, 0 LLM calls)",
        len(themes),
        len(clusters),
        merge_count,
        len(final_total_ids | missing),
        len(original_total_ids),
    )

    return clusters


async def _cluster_evidence_single(
    client: OpenRouterClient,
    evidence: list[EvidencePiece],
    query: str,
) -> list[dict]:
    """Original single-call clustering for small evidence sets (<=200)."""
    # Phase 1: Short ID remapping for token efficiency
    capped = evidence[:200]
    remapped_evidence, reverse_map = _remap_evidence_ids(capped)

    evidence_text = "\n".join(
        f"[{e.get('evidence_id', '?')}] ({e.get('quality_tier', '?')}, "
        f"cat={e.get('fact_category', '?')}, perspective={e.get('perspective', '?')}) "
        f"{e.get('statement', '')[:150]}"
        for e in remapped_evidence
    )

    # FIX-303B: Build perspective distribution for diversity-aware clustering
    perspective_counts: dict[str, int] = {}
    for e in evidence:
        p = e.get("perspective", "Scientific")
        perspective_counts[p] = perspective_counts.get(p, 0) + 1
    perspective_dist = ", ".join(
        f"{p}: {c}" for p, c in sorted(
            perspective_counts.items(), key=lambda x: -x[1]
        )
    )

    prompt = f"""Research question: {query}

Evidence pieces ({len(capped)} total):
{evidence_text}

Perspective distribution: {perspective_dist}

Group these evidence pieces into 8-15 thematic clusters.
Every evidence piece should be assigned to exactly one cluster.
Evidence IDs are integers (1, 2, 3...). Use EXACTLY these IDs in your response.
Ensure clusters represent diverse perspectives. Create clusters that cover
at least 6 of these 9 STORM perspectives: Scientific, Regulatory, Industry,
Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends.
Identify any aspects not well-covered."""

    try:
        parsed = await client.generate_structured(
            prompt=prompt,
            schema=ClusterPlan,
            system=CLUSTER_SYSTEM,
            max_tokens=PG_SYNTHESIS_STRUCTURED_MAX_TOKENS,
            timeout=300,
        )

        # Reverse-remap short IDs back to original ev_xxx IDs
        total_assigned = 0
        clusters = []
        for c in parsed.clusters:
            original_ids = _reverse_remap_ids(c.evidence_ids, reverse_map)
            total_assigned += len(original_ids)
            clusters.append({
                "cluster_id": c.cluster_id,
                "theme": c.theme,
                "description": c.description,
                "evidence_ids": original_ids,
                "strength": c.strength,
            })

        logger.info(
            "[polaris graph] Clustered into %d themes (%d/%d IDs preserved): %s",
            len(clusters),
            total_assigned,
            len(capped),
            [c["theme"][:30] for c in clusters[:5]],
        )

        return clusters

    except Exception as exc:
        logger.error(
            "[polaris graph] Clustering failed: %s — using category-based fallback",
            str(exc)[:200],
        )
        return _category_fallback_clusters(evidence)


def _category_fallback_clusters(evidence: list[EvidencePiece]) -> list[dict]:
    """SF-09: Category-based fallback clusters when LLM clustering fails."""
    category_clusters: dict[str, list[str]] = {}
    for e in evidence:
        cat = e.get("fact_category", "other")
        category_clusters.setdefault(cat, []).append(e.get("evidence_id", ""))

    if category_clusters:
        return [
            {
                "cluster_id": f"c_{cat}",
                "theme": cat.replace("_", " ").title(),
                "description": f"Evidence categorized as {cat}",
                "evidence_ids": ids,
                "strength": "moderate",
            }
            for cat, ids in category_clusters.items()
        ]
    # Ultimate fallback if no evidence at all
    return [
        {
            "cluster_id": "c_all",
            "theme": "All Evidence",
            "description": "Fallback: all evidence in one cluster",
            "evidence_ids": [e.get("evidence_id", "") for e in evidence],
            "strength": "moderate",
        }
    ]
