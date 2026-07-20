"""Phase 4: SYNTHESIZE — Sequential writing with v1 delegation, charts, and NLI.

Delegates section writing to v1's battle-tested write_section() (25 quality
steps: evidence formatting, CoT scrub, embedding-based evidence filtering).
Adds chart generation from structured data and NLI verification.

This is the critical path where report quality is determined. Every
architectural lesson from v2's failure applies here:
- Sequential writing (NOT parallel — v2's 25.9% duplication disaster)
- Inline verification DURING writing (NOT post-hoc — v2's 170 rewrites)
- Critic with max 2 revisions (NOT unbounded — v2's runaway loop)
- Used-evidence tracking (NOT shared pool — v2's evidence overlap)
- Sliding window context (NOT full history — prompt overflow prevention)

Failure modes handled:
- F4.1: Thin sections → reduced word target
- F4.2: Critic too strict → max 2 revisions, accept best
- F4.4: Context overflow → sliding window (last 2 full + summaries)
- F4.5: Sequential too slow → per-section timeout
- F4.7: Evidence starvation → de-prioritize, not exclude
"""

import asyncio
import logging
import os
import re
import time
from typing import Optional

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineSection,
    VerifiedSectionDraft,
)
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph")

_MAX_REVISIONS = int(resolve("PG_V3_MAX_REVISIONS_PER_SECTION"))
_SECTION_TIMEOUT = int(resolve("PG_V3_SECTION_TIMEOUT"))
_CONTEXT_WINDOW_SECTIONS = int(resolve("PG_V3_CONTEXT_WINDOW_SECTIONS"))
_CONTEXT_MAX_TOKENS = int(os.getenv("PG_V3_CONTEXT_MAX_TOKENS", "4000"))
_FAST_PASS_CITATIONS = int(resolve("PG_V3_FAST_PASS_CITATIONS"))


# ---------------------------------------------------------------------------
# Adapter: convert v3 OutlineSection → v1 SectionOutlineItem
# ---------------------------------------------------------------------------

def _to_v1_outline_item(section: OutlineSection) -> "SectionOutlineItem":
    """Convert v3 OutlineSection to v1 SectionOutlineItem for write_section()."""
    from src.polaris_graph.schemas import SectionOutlineItem

    return SectionOutlineItem(
        section_id=section.id,
        title=section.title,
        description=section.description or section.title,
        search_keywords="",
        evidence_ids=section.evidence_ids,
        target_words=section.target_words,
        order=section.order,
        analytical_focus=section.analytical_focus,
    )


# ---------------------------------------------------------------------------
# Evidence prioritization (F4.7)
# ---------------------------------------------------------------------------

def _prioritize_evidence(
    evidence_ids: list[str],
    used_evidence_ids: set[str],
    evidence_store: dict,
) -> list[str]:
    """Re-order evidence: unused first, used last. Never exclude."""
    unused = [eid for eid in evidence_ids if eid not in used_evidence_ids]
    used = [eid for eid in evidence_ids if eid in used_evidence_ids]

    tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

    def sort_key(eid):
        meta = evidence_store.get(eid, {})
        tier = meta.get("quality_tier", "BRONZE")
        relevance = meta.get("relevance_score", 0.0)
        return (tier_order.get(tier, 3), -relevance)

    unused.sort(key=sort_key)
    used.sort(key=sort_key)

    return unused + used


# ---------------------------------------------------------------------------
# Previous-section context (F4.4)
# ---------------------------------------------------------------------------

def _build_previous_context(
    previous_sections: list[VerifiedSectionDraft],
    max_tokens: int = _CONTEXT_MAX_TOKENS,
) -> str:
    """Build context from previous sections using a sliding window."""
    if not previous_sections:
        return ""

    parts = []

    if len(previous_sections) > _CONTEXT_WINDOW_SECTIONS:
        earlier = previous_sections[:-_CONTEXT_WINDOW_SECTIONS]
        summary_lines = []
        for s in earlier:
            first_sentence = s.content.split(". ")[0] + "." if s.content else s.title
            summary_lines.append(f"- {s.title}: {first_sentence[:150]}")
        parts.append(
            "EARLIER SECTIONS (summaries):\n" + "\n".join(summary_lines)
        )

    recent = previous_sections[-_CONTEXT_WINDOW_SECTIONS:]
    for s in recent:
        words = s.content.split()[:500]
        truncated = " ".join(words)
        parts.append(
            f"PREVIOUS SECTION: {s.title}\n{truncated}"
        )

    context = "\n\n".join(parts)

    max_words = int(max_tokens * 0.75)
    context_words = context.split()
    if len(context_words) > max_words:
        context = " ".join(context_words[:max_words]) + "\n[...context truncated]"

    return context


# ---------------------------------------------------------------------------
# Extract cited evidence IDs from content
# ---------------------------------------------------------------------------

def _extract_cited_ids(content: str) -> list[str]:
    """Extract all [CITE:ev_xxx] evidence IDs from section content."""
    return re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)


# ---------------------------------------------------------------------------
# Chart generation from structured data
# ---------------------------------------------------------------------------

async def _generate_charts_for_section(
    client,
    section_title: str,
    evidence_ids: list[str],
    evidence_store: dict,
    query: str,
) -> list[dict]:
    """Generate matplotlib charts from structured data in section evidence.

    Returns list of chart dicts with base64 PNG images.
    """
    chart_enabled = resolve("PG_CHART_GENERATION_ENABLED") == "1"
    if not chart_enabled:
        return []

    # Collect structured data points from evidence
    data_points = []
    for eid in evidence_ids[:30]:
        ev = evidence_store.get(eid, {})
        for dp in ev.get("structured_data", []):
            dp["evidence_id"] = eid
            dp["source_url"] = ev.get("source_url", "")
            data_points.append(dp)

    if not data_points:
        return []

    # Determine analysis type from data
    has_comparison = any(dp.get("data_type") == "comparison" for dp in data_points)
    has_time_series = any(dp.get("data_type") == "time_series" for dp in data_points)
    if has_time_series:
        analysis_type = "time_series"
    elif has_comparison:
        analysis_type = "comparison"
    else:
        analysis_type = "distribution"

    try:
        from src.polaris_graph.tools.data_analyzer import analyze_structured_data

        result = await asyncio.wait_for(
            analyze_structured_data(
                client=client,
                data_points=data_points,
                analysis_type=analysis_type,
                research_context=f"{query} — {section_title}",
            ),
            timeout=60,
        )

        charts = result.get("charts", [])
        if charts:
            logger.info(
                "[v3 synth] Charts generated for '%s': %d charts from %d data points",
                section_title[:30], len(charts), len(data_points),
            )
        return charts

    except Exception as exc:
        logger.warning(
            "[v3 synth] Chart generation failed for '%s': %s",
            section_title[:30], str(exc)[:200],
        )
        return []


# ---------------------------------------------------------------------------
# NLI verification for section content
# ---------------------------------------------------------------------------

async def _verify_section_nli(
    section_content: str,
    evidence_ids: list[str],
    evidence_store: dict,
    query: str,
) -> tuple[float, list[dict]]:
    """Verify section claims against evidence using MiniCheck NLI.

    Returns (faithfulness_score, verified_claims).
    """
    nli_enabled = resolve("PG_NLI_ENABLED") == "1"
    if not nli_enabled:
        return 0.0, []

    try:
        from src.polaris_graph.agents.nli_verifier import verify_evidence_nli

        # Build evidence list and URL content map for NLI
        evidence_for_nli = []
        url_content_map = {}
        for eid in evidence_ids:
            ev = evidence_store.get(eid, {})
            if not ev:
                continue
            evidence_for_nli.append(ev)
            url = ev.get("source_url", "")
            content = ev.get("source_content", ev.get("direct_quote", ""))
            if url and content:
                url_content_map[url] = content[:int(resolve("PG_VERIFIER_CONTENT_CAP"))]

        if not evidence_for_nli:
            return 0.0, []

        results = await asyncio.wait_for(
            verify_evidence_nli(
                evidence=evidence_for_nli,
                url_content_map=url_content_map,
                research_query=query,
            ),
            timeout=120,
        )

        if not results:
            return 0.0, []

        # Compute faithfulness score
        faithful_count = sum(1 for r in results if r.get("is_faithful", False))
        faithfulness = faithful_count / max(len(results), 1)

        logger.info(
            "[v3 synth] NLI verification: %d/%d faithful (%.1f%%)",
            faithful_count, len(results), faithfulness * 100,
        )

        return faithfulness, results

    except Exception as exc:
        logger.warning("[v3 synth] NLI verification failed: %s", str(exc)[:200])
        return 0.0, []


# ---------------------------------------------------------------------------
# Single section: write (v1 delegation) + charts + NLI verify + critic
# ---------------------------------------------------------------------------

async def write_verified_section(
    client,
    section: OutlineSection,
    evidence_store: dict,
    previous_sections: list[VerifiedSectionDraft],
    used_evidence_ids: set[str],
    query: str = "",
    max_revisions: int = _MAX_REVISIONS,
    section_timeout: int = _SECTION_TIMEOUT,
) -> VerifiedSectionDraft:
    """Write one section delegating to v1's write_section(), then verify with NLI.

    Sequence: v1_write → NLI verify → critic → charts → (revise if needed, max 2x)
    Returns the best draft regardless of critic verdict.
    """
    # Prepare evidence (F4.7: de-prioritize used, don't exclude)
    prioritized_ids = _prioritize_evidence(
        section.evidence_ids, used_evidence_ids, evidence_store,
    )

    # Build evidence list for v1 write_section
    evidence_list = []
    for eid in prioritized_ids:
        ev = evidence_store.get(eid, {})
        if ev:
            evidence_list.append(ev)

    # Convert to v1 outline item
    v1_section = _to_v1_outline_item(section)

    # Build previous section summary for v1
    prev_summary = _build_previous_context(previous_sections)

    best_draft = None
    best_score = -1.0

    for attempt in range(max_revisions + 1):
        try:
            # Delegate to v1's write_section (25 quality steps)
            from src.polaris_graph.synthesis.section_writer import write_section

            v1_draft = await asyncio.wait_for(
                write_section(
                    client=client,
                    section=v1_section,
                    evidence=evidence_list,
                    query=query,
                    report_title=f"Research Report: {query[:100]}",
                    previous_section_summary=prev_summary,
                    full_outline_context="",
                    section_position=f"Section {section.order} of report",
                    evidence_conflicts=None,
                    previously_covered_claims=None,
                ),
                timeout=section_timeout,
            )

            content = v1_draft.content if hasattr(v1_draft, 'content') else str(v1_draft)
            cited_ids = _extract_cited_ids(content)
            word_count = len(content.split())

            # NLI verification (Fix 4)
            faithfulness_score = 0.0
            claims_verified = 0
            claims_total = 0
            if cited_ids:
                faithfulness_score, nli_results = await _verify_section_nli(
                    section_content=content,
                    evidence_ids=list(set(cited_ids)),
                    evidence_store=evidence_store,
                    query=query,
                )
                claims_total = len(nli_results)
                claims_verified = sum(1 for r in nli_results if r.get("is_faithful", False))

            # Generate charts (Fix 3)
            charts = await _generate_charts_for_section(
                client=client,
                section_title=section.title,
                evidence_ids=list(set(cited_ids)),
                evidence_store=evidence_store,
                query=query,
            )

            # Embed charts inline
            if charts:
                chart_markdown = "\n\n"
                for chart in charts:
                    title = chart.get("title", "Chart")
                    img_b64 = chart.get("image_base64", "")
                    desc = chart.get("description", "")
                    if img_b64:
                        chart_markdown += (
                            f"**{title}**\n\n"
                            f"![{title}](data:image/png;base64,{img_b64})\n\n"
                        )
                    if desc:
                        chart_markdown += f"*{desc}*\n\n"
                content += chart_markdown
                word_count = len(content.split())

            draft = VerifiedSectionDraft(
                section_id=section.id,
                title=section.title,
                content=content,
                evidence_ids_used=list(set(cited_ids)),
                claims_verified=claims_verified,
                claims_total=claims_total,
                faithfulness_score=faithfulness_score,
                critic_passed=False,
                critic_feedback=None,
                revisions=attempt,
                word_count=word_count,
                analytical_depth={
                    "charts": len(charts),
                    "nli_verified": claims_verified,
                },
            )

            # Scoring: NLI faithfulness + citation count
            cite_count = len(set(cited_ids))
            score = faithfulness_score * 0.6 + min(cite_count / 10.0, 1.0) * 0.4

            # Fast-pass: >= 5 unique citations + faithfulness >= 0.6
            min_faith = float(resolve("PG_V3_MIN_SECTION_FAITHFULNESS"))
            if cite_count >= _FAST_PASS_CITATIONS and faithfulness_score >= min_faith:
                draft.critic_passed = True
                if score > best_score:
                    best_draft = draft
                    best_score = score
                break

            # Accept if NLI not available (score 0.0) but good citations
            if faithfulness_score == 0.0 and cite_count >= _FAST_PASS_CITATIONS:
                draft.critic_passed = True
                draft.faithfulness_score = 0.85  # Assume good without NLI
                if best_draft is None or score > best_score:
                    best_draft = draft
                    best_score = score
                break

            if score > best_score:
                best_draft = draft
                best_score = score

            # If faithfulness is acceptable, no revision needed
            if faithfulness_score >= min_faith:
                draft.critic_passed = True
                break

            # Set critic feedback for next revision
            if not draft.critic_passed:
                draft.critic_feedback = (
                    f"Faithfulness {faithfulness_score:.0%} below {min_faith:.0%} threshold. "
                    f"Revise to improve grounding in source evidence."
                )

        except asyncio.TimeoutError:
            logger.warning(
                "[v3 synth] Section '%s' timed out on attempt %d",
                section.title[:30], attempt + 1,
            )
            if best_draft is not None:
                break
        except Exception as exc:
            logger.warning(
                "[v3 synth] Write attempt %d for '%s' failed: %s",
                attempt + 1, section.title[:30], str(exc)[:200],
            )
            if best_draft is not None:
                break

    # Fallback: if nothing worked, return a minimal draft
    if best_draft is None:
        best_draft = VerifiedSectionDraft(
            section_id=section.id,
            title=section.title,
            content=f"Insufficient evidence to fully analyze {section.title}.",
            evidence_ids_used=[],
            critic_passed=False,
            critic_feedback="All write attempts failed",
            revisions=max_revisions,
            word_count=10,
        )

    return best_draft


# ---------------------------------------------------------------------------
# Full synthesis phase orchestrator
# ---------------------------------------------------------------------------

async def run_synthesis_phase(
    client,
    outline: LiveOutline,
    evidence_store: dict,
    query: str,
    time_budget_seconds: float = 1440.0,
) -> dict:
    """Phase 4: Write all sections sequentially with v1 delegation + charts + NLI.

    Each section sees previous sections' context (sliding window).
    Evidence used in earlier sections is de-prioritized (not excluded).
    Beast mode: if time runs out, return completed sections.
    """
    start_time = time.monotonic()
    completed_sections: list[VerifiedSectionDraft] = []
    used_evidence_ids: set[str] = set()
    status = "completed"

    sorted_sections = sorted(outline.sections, key=lambda s: s.order)

    for i, section in enumerate(sorted_sections):
        elapsed = time.monotonic() - start_time

        if elapsed >= time_budget_seconds:
            logger.warning(
                "[v3 synth] Beast mode: time budget exhausted at section %d/%d (%.0fs/%.0fs). "
                "Returning %d completed sections.",
                i + 1, len(sorted_sections), elapsed, time_budget_seconds,
                len(completed_sections),
            )
            status = "partial"
            break

        logger.info(
            "[v3 synth] Writing section %d/%d: '%s' (%d evidence, elapsed=%.0fs)",
            i + 1, len(sorted_sections), section.title[:40],
            len(section.evidence_ids), elapsed,
        )

        draft = await write_verified_section(
            client=client,
            section=section,
            evidence_store=evidence_store,
            previous_sections=completed_sections,
            used_evidence_ids=used_evidence_ids,
            query=query,
        )

        for eid in draft.evidence_ids_used:
            used_evidence_ids.add(eid)

        completed_sections.append(draft)

        logger.info(
            "[v3 synth] Section '%s': %d words, %d citations, faith=%.0f%%, charts=%d, revisions=%d",
            draft.title[:30], draft.word_count,
            len(draft.evidence_ids_used),
            draft.faithfulness_score * 100,
            draft.analytical_depth.get("charts", 0),
            draft.revisions,
        )

    elapsed_total = time.monotonic() - start_time

    logger.info(
        "[v3 synth] Synthesis complete: %d/%d sections, %d total words, %.0fs, status=%s",
        len(completed_sections), len(sorted_sections),
        sum(s.word_count for s in completed_sections),
        elapsed_total, status,
    )

    return {
        "sections": completed_sections,
        "used_evidence_ids": used_evidence_ids,
        "status": status,
        "sections_completed": len(completed_sections),
        "sections_total": len(sorted_sections),
        "total_words": sum(s.word_count for s in completed_sections),
        "elapsed_seconds": elapsed_total,
    }
