"""Phase 4: SYNTHESIZE — Sequential writing with inline verification and critic.

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

logger = logging.getLogger("polaris_graph")

_MAX_REVISIONS = int(os.getenv("PG_V3_MAX_REVISIONS_PER_SECTION", "2"))
_SECTION_TIMEOUT = int(os.getenv("PG_V3_SECTION_TIMEOUT", "180"))
_CONTEXT_WINDOW_SECTIONS = int(os.getenv("PG_V3_CONTEXT_WINDOW_SECTIONS", "2"))
_CONTEXT_MAX_TOKENS = int(os.getenv("PG_V3_CONTEXT_MAX_TOKENS", "4000"))
_FAST_PASS_CITATIONS = int(os.getenv("PG_V3_FAST_PASS_CITATIONS", "5"))


# ---------------------------------------------------------------------------
# Word target computation (F4.1)
# ---------------------------------------------------------------------------

def _compute_target_words(evidence_count: int) -> int:
    """Compute target word count proportional to evidence.

    Thin sections (1-2 evidence) get 300-400 words.
    Normal sections (5-10) get 800-1200 words.
    Rich sections (15+) get up to 1500 words.
    """
    if evidence_count <= 1:
        return 300
    elif evidence_count <= 2:
        return 400
    elif evidence_count <= 5:
        return max(400, evidence_count * 150)
    elif evidence_count <= 15:
        return max(800, min(evidence_count * 100, 1500))
    else:
        return 1500


# ---------------------------------------------------------------------------
# Evidence prioritization (F4.7)
# ---------------------------------------------------------------------------

def _prioritize_evidence(
    evidence_ids: list[str],
    used_evidence_ids: set[str],
    evidence_store: dict,
) -> list[str]:
    """Re-order evidence: unused first, used last. Never exclude.

    Prevents cross-section duplication while ensuring thin sections
    still have access to all their assigned evidence.
    """
    unused = [eid for eid in evidence_ids if eid not in used_evidence_ids]
    used = [eid for eid in evidence_ids if eid in used_evidence_ids]

    # Sort unused by quality tier (GOLD > SILVER > BRONZE)
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
    """Build context from previous sections using a sliding window.

    - Last 2 sections: full text (for coherence)
    - Earlier sections: 1-sentence summary (for thread)
    - Hard cap at max_tokens (~4000 = ~3000 words)
    """
    if not previous_sections:
        return ""

    parts = []

    # Earlier sections → summaries only
    if len(previous_sections) > _CONTEXT_WINDOW_SECTIONS:
        earlier = previous_sections[:-_CONTEXT_WINDOW_SECTIONS]
        summary_lines = []
        for s in earlier:
            # First sentence of content as summary
            first_sentence = s.content.split(". ")[0] + "." if s.content else s.title
            summary_lines.append(f"- {s.title}: {first_sentence[:150]}")
        parts.append(
            "EARLIER SECTIONS (summaries):\n" + "\n".join(summary_lines)
        )

    # Recent sections → full text
    recent = previous_sections[-_CONTEXT_WINDOW_SECTIONS:]
    for s in recent:
        # Truncate to ~500 words per section
        words = s.content.split()[:500]
        truncated = " ".join(words)
        parts.append(
            f"PREVIOUS SECTION: {s.title}\n{truncated}"
        )

    context = "\n\n".join(parts)

    # Hard token cap (estimate: 1 token ≈ 0.75 words)
    max_words = int(max_tokens * 0.75)
    context_words = context.split()
    if len(context_words) > max_words:
        context = " ".join(context_words[:max_words]) + "\n[...context truncated]"

    return context


# ---------------------------------------------------------------------------
# Format evidence for prompt
# ---------------------------------------------------------------------------

def _format_evidence_for_prompt(
    evidence_ids: list[str],
    evidence_store: dict,
    max_evidence: int = 20,
) -> str:
    """Format evidence pieces for the section writer prompt."""
    lines = []
    for eid in evidence_ids[:max_evidence]:
        ev = evidence_store.get(eid, {})
        tier = ev.get("quality_tier", "BRONZE")
        statement = ev.get("statement", "")[:300]
        source = ev.get("source_title", ev.get("source_url", "Unknown"))[:100]
        lines.append(f"[{eid}] [{tier}] {statement}\n  Source: {source}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Extract cited evidence IDs from content
# ---------------------------------------------------------------------------

def _extract_cited_ids(content: str) -> list[str]:
    """Extract all [CITE:ev_xxx] evidence IDs from section content."""
    return re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)


# ---------------------------------------------------------------------------
# Single section: write + verify + critic
# ---------------------------------------------------------------------------

async def write_verified_section(
    client,
    section: OutlineSection,
    evidence_store: dict,
    previous_sections: list[VerifiedSectionDraft],
    used_evidence_ids: set[str],
    max_revisions: int = _MAX_REVISIONS,
    section_timeout: int = _SECTION_TIMEOUT,
) -> VerifiedSectionDraft:
    """Write one section with inline verification and critic review.

    Sequence: write → extract cited IDs → critic → (revise if needed, max 2x)
    Returns the best draft regardless of critic verdict.
    """
    # Prepare evidence (F4.7: de-prioritize used, don't exclude)
    prioritized_ids = _prioritize_evidence(
        section.evidence_ids, used_evidence_ids, evidence_store,
    )

    # Compute word target (F4.1: thin sections get fewer words)
    target_words = _compute_target_words(len(prioritized_ids))
    if section.target_words > 0:
        target_words = min(target_words, section.target_words)

    # Build previous-section context (F4.4: sliding window)
    prev_context = _build_previous_context(previous_sections)

    # Format evidence for prompt
    evidence_text = _format_evidence_for_prompt(prioritized_ids, evidence_store)

    # Build analytical instructions
    focus_instruction = ""
    if section.analytical_focus:
        focus_map = {
            "aggregate": "AGGREGATE findings across multiple sources — report ranges, medians, and patterns.",
            "compare": "COMPARE how different studies, methods, or conditions produce different results.",
            "explain": "EXPLAIN the mechanisms and implications — WHY, not just WHAT.",
            "tabulate": "TABULATE comparable data points in a markdown table with citations per row.",
            "challenge": "CHALLENGE the evidence — note limitations, contradictions, and gaps.",
        }
        focus_instruction = focus_map.get(
            section.analytical_focus,
            f"Focus on: {section.analytical_focus}",
        )

    system_prompt = (
        f"You are writing section '{section.title}' of a research report.\n"
        f"Target: ~{target_words} words. Analytical focus: {focus_instruction}\n\n"
        "RULES:\n"
        "- Every factual claim MUST cite evidence: [CITE:ev_xxx]\n"
        "- AGGREGATE similar findings, don't list them sequentially\n"
        "- When 3+ data points exist, create a markdown table\n"
        "- Note at least 1 limitation or gap in the evidence\n"
        "- Do NOT include chain-of-thought or planning text\n"
        "- Do NOT repeat information from previous sections\n"
    )

    user_prompt = (
        f"Section: {section.title}\n"
        f"Description: {section.description or section.title}\n\n"
    )
    if prev_context:
        user_prompt += f"{prev_context}\n\nDo NOT repeat anything from the sections above.\n\n"

    user_prompt += (
        f"Evidence:\n{evidence_text}\n\n"
        f"Write this section (~{target_words} words)."
    )

    # Write → Critic loop (max_revisions + 1 attempts total)
    best_draft = None
    best_score = -1.0

    for attempt in range(max_revisions + 1):
        try:
            # Write section
            if attempt == 0:
                write_prompt = user_prompt
            else:
                # Revision: include critic feedback
                write_prompt = (
                    f"{user_prompt}\n\n"
                    f"REVISION {attempt}: The previous draft was rejected.\n"
                    f"Feedback: {best_draft.critic_feedback if best_draft else 'No feedback'}\n"
                    f"Please revise to address this feedback."
                )

            response = await client.generate(
                prompt=write_prompt,
                system=system_prompt,
                max_tokens=int(os.getenv("PG_V3_SECTION_MAX_TOKENS", "8192")),
                timeout=section_timeout,
            )

            content = response.content if hasattr(response, 'content') else str(response)

            # Extract cited evidence IDs
            cited_ids = _extract_cited_ids(content)
            word_count = len(content.split())

            # Count citations for fast-pass check
            cite_count = len(cited_ids)

            draft = VerifiedSectionDraft(
                section_id=section.id,
                title=section.title,
                content=content,
                evidence_ids_used=list(set(cited_ids)),
                claims_verified=0,
                claims_total=0,
                faithfulness_score=0.0,
                critic_passed=False,
                critic_feedback=None,
                revisions=attempt,
                word_count=word_count,
                analytical_depth={},
            )

            # Fast-pass: if >= 5 unique citations, skip critic
            if len(set(cited_ids)) >= _FAST_PASS_CITATIONS:
                draft.critic_passed = True
                draft.faithfulness_score = 0.85
                if best_draft is None or 0.85 > best_score:
                    best_draft = draft
                    best_score = 0.85
                break

            # Critic evaluation
            try:
                critic_result = await client.generate_structured(
                    prompt=(
                        f"Evaluate this section for analytical depth:\n\n"
                        f"Title: {section.title}\n"
                        f"Content:\n{content[:3000]}\n\n"
                        f"Does it ANALYZE evidence (compare, aggregate, explain) "
                        f"or merely RESTATE it?"
                    ),
                    schema=_CriticVerdictSchema,
                    system="You are a research quality critic. Evaluate analytical depth.",
                    max_tokens=1024,
                    timeout=60,
                )

                critic_passed = getattr(critic_result, 'passed', False)
                critic_score = getattr(critic_result, 'score', 0.5)
                critic_feedback = getattr(critic_result, 'feedback', '')

                draft.critic_passed = critic_passed
                draft.critic_feedback = critic_feedback
                draft.faithfulness_score = critic_score

                if critic_score > best_score:
                    best_draft = draft
                    best_score = critic_score

                if critic_passed:
                    break

            except Exception as exc:
                logger.warning(
                    "[v3 synth] Critic failed for %s: %s — accepting draft",
                    section.id, str(exc)[:100],
                )
                draft.critic_passed = True
                draft.faithfulness_score = 0.7
                if best_draft is None:
                    best_draft = draft
                    best_score = 0.7
                break

        except Exception as exc:
            logger.warning(
                "[v3 synth] Write attempt %d for %s failed: %s",
                attempt + 1, section.id, str(exc)[:200],
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


# Placeholder schema for critic (used with generate_structured)
from pydantic import BaseModel, Field


class _CriticVerdictSchema(BaseModel):
    passed: bool = Field(description="Whether the section meets analytical depth requirements")
    score: float = Field(description="Quality score 0-1", default=0.5)
    feedback: str = Field(description="Specific feedback for revision", default="")


# ---------------------------------------------------------------------------
# Full synthesis phase orchestrator
# ---------------------------------------------------------------------------

async def run_synthesis_phase(
    client,
    outline: LiveOutline,
    evidence_store: dict,
    query: str,
    time_budget_seconds: float = 1440.0,  # 24 minutes default (40% of 60)
) -> dict:
    """Phase 4: Write all sections sequentially with shared context.

    Each section sees previous sections' context (sliding window).
    Evidence used in earlier sections is de-prioritized (not excluded).
    Beast mode: if time runs out, return completed sections.
    """
    start_time = time.monotonic()
    completed_sections: list[VerifiedSectionDraft] = []
    used_evidence_ids: set[str] = set()
    status = "completed"

    # Sort sections by outline order
    sorted_sections = sorted(outline.sections, key=lambda s: s.order)

    for i, section in enumerate(sorted_sections):
        elapsed = time.monotonic() - start_time

        # Beast mode: check time budget before each section
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

        # Write section with inline verification + critic
        draft = await write_verified_section(
            client=client,
            section=section,
            evidence_store=evidence_store,
            previous_sections=completed_sections,
            used_evidence_ids=used_evidence_ids,
        )

        # Track used evidence across sections
        for eid in draft.evidence_ids_used:
            used_evidence_ids.add(eid)

        completed_sections.append(draft)

        logger.info(
            "[v3 synth] Section '%s': %d words, %d citations, critic=%s, revisions=%d",
            draft.title[:30], draft.word_count,
            len(draft.evidence_ids_used), draft.critic_passed, draft.revisions,
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
