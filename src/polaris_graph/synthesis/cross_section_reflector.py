"""
MoST Phase R: Cross-Section Self-Reflection (Hydrogen Bond).

Implements the self-reflection bond from "The Molecular Structure of Thought"
(arXiv 2601.06002). Each section reflects on other sections to detect
contradictions, redundancy, and missed cross-references.

Cost: ~1 LLM call per section (~15 calls, ~$0.008, ~2-3 min at concurrency=3)
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

from src.polaris_graph.schemas import SectionDraft

logger = logging.getLogger(__name__)


async def reflect_across_sections(
    client,
    sections: list[SectionDraft],
    evidence: list[dict],
    query: str,
    concurrency: int = 3,
    bond_analysis: dict | None = None,
) -> list[SectionDraft]:
    """Run cross-section reflection on all sections.

    M-12: Enhanced with structured bond analysis input. When bond_analysis
    is provided, feeds covalent/ionic/disulfide/peptide findings into
    the revision prompt for targeted, evidence-based edits.

    Guard: If revised section word count < 80% or > 130% of original,
    keep original (prevents CASE_2 regression or data loss).

    Args:
        client: OpenRouter LLM client.
        sections: All SectionDraft objects.
        evidence: Verified evidence list.
        query: Original research query.
        concurrency: Max parallel reflection calls.
        bond_analysis: Optional dict with covalent/ionic/disulfide/peptide results.

    Returns:
        Updated list of SectionDraft objects (some may be revised).
    """
    if len(sections) < 2:
        logger.info("[MoST-R] Only %d section(s), skipping reflection", len(sections))
        return sections

    max_context = int(os.getenv("PG_REFLECTION_MAX_CONTEXT", "4"))

    # Build evidence map: section_id -> list of evidence_ids cited
    section_evidence_map = {}
    for sec in sections:
        cited = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', getattr(sec, 'content', '')))
        section_evidence_map[getattr(sec, 'section_id', '')] = cited

    # Build index map: section_id -> position in list (for adjacency)
    section_index_map = {}
    for i, sec in enumerate(sections):
        section_index_map[getattr(sec, 'section_id', '')] = i

    semaphore = asyncio.Semaphore(concurrency)
    results = list(sections)  # Shallow copy

    async def _reflect_one(idx: int, sec: SectionDraft) -> tuple[int, SectionDraft | None]:
        async with semaphore:
            try:
                context = _build_reflection_context(
                    target=sec,
                    target_index=idx,
                    all_sections=sections,
                    section_evidence_map=section_evidence_map,
                    section_index_map=section_index_map,
                    max_context=max_context,
                )
                if not context:
                    return idx, None

                # M-12: Build structural analysis context from bond analysis
                structural_context = _build_bond_context(
                    bond_analysis, getattr(sec, 'section_id', '')
                )

                prompt = (
                    "You are a research report editor performing cross-section quality review.\n\n"
                    f"RESEARCH QUESTION: {query}\n\n"
                    f"TARGET SECTION: {getattr(sec, 'title', '')}\n"
                    f"{getattr(sec, 'content', '')[:3000]}\n\n"
                    f"RELATED SECTIONS:\n{context}\n\n"
                )
                if structural_context:
                    prompt += f"STRUCTURAL ANALYSIS (from automated bond verification):\n{structural_context}\n\n"
                prompt += (
                    "Analyze the target section against the related sections"
                    + (" and structural analysis" if structural_context else "") + ":\n"
                    "1. CONTRADICTIONS: Claims in target that conflict with related sections\n"
                    "2. REDUNDANCIES: Statistics/findings already covered in related sections\n"
                    "3. CROSS_REFERENCES: Connections that should be made explicit\n\n"
                    "Output JSON:\n"
                    '{"contradictions": [{"claim": "...", "conflicts_with": "...", "resolution": "..."}], '
                    '"redundancies": [{"claim": "...", "already_in": "..."}], '
                    '"cross_references": [{"from_claim": "...", "relates_to_section": "...", "connection": "..."}], '
                    '"revision_needed": true/false}'
                )

                resp = await client.generate(
                    prompt, max_tokens=int(os.getenv("PG_REFLECTOR_MAX_TOKENS", "8192")),
                )
                content = getattr(resp, 'content', '') or ''

                # Parse JSON from response
                reflection = _parse_reflection_json(content)
                if not reflection or not reflection.get("revision_needed", False):
                    return idx, None

                contradictions = _detect_contradictions(reflection)
                if not contradictions and not reflection.get("redundancies") and not reflection.get("cross_references"):
                    return idx, None

                # Revise the section (M-13: targeted revision with bond context)
                revised = await _revise_with_reflection(
                    client, sec, reflection, evidence, bond_analysis,
                )
                if revised is None:
                    return idx, None

                # M-03: CASE_2 guard: reject if revised text is <80% or >130% of original
                orig_words = len(getattr(sec, 'content', '').split())
                revised_words = len(getattr(revised, 'content', '').split())
                if orig_words > 0 and (
                    revised_words < orig_words * 0.8
                    or revised_words > orig_words * 1.3
                ):
                    logger.warning(
                        "[MoST-R] CASE_2 guard: section '%s' revision out of bounds "
                        "(%d -> %d words, %.0f%%), keeping original",
                        getattr(sec, 'title', '')[:40],
                        orig_words, revised_words,
                        (revised_words / orig_words) * 100,
                    )
                    return idx, None

                logger.info(
                    "[MoST-R] Revised section '%s': %d contradictions, %d redundancies, %d cross-refs",
                    getattr(sec, 'title', '')[:40],
                    len(reflection.get("contradictions", [])),
                    len(reflection.get("redundancies", [])),
                    len(reflection.get("cross_references", [])),
                )
                return idx, revised

            except Exception as exc:
                logger.warning(
                    "[MoST-R] Reflection failed for section '%s': %s",
                    getattr(sec, 'title', '')[:40], str(exc)[:200],
                )
                return idx, None

    tasks = [_reflect_one(i, sec) for i, sec in enumerate(sections)]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    revised_count = 0
    for result in completed:
        if isinstance(result, Exception):
            continue
        idx, revised_sec = result
        if revised_sec is not None:
            results[idx] = revised_sec
            revised_count += 1

    logger.info("[MoST-R] Reflection complete: %d/%d sections revised", revised_count, len(sections))
    return results


def _build_reflection_context(
    target: SectionDraft,
    target_index: int,
    all_sections: list[SectionDraft],
    section_evidence_map: dict[str, set],
    section_index_map: dict[str, int],
    max_context: int = 4,
) -> str:
    """Select most relevant other sections as reflection context.

    Relevance criteria:
    1. Evidence overlap (Jaccard similarity on evidence_id sets)
    2. Adjacency (immediately before/after in report order)

    Args:
        target: The section being reflected on.
        target_index: Position of target in the sections list.
        all_sections: All sections in the report.
        section_evidence_map: Map of section_id -> set of cited evidence IDs.
        section_index_map: Map of section_id -> list index position.
        max_context: Maximum context sections to include.

    Returns:
        Formatted string with related section titles + first 500 chars of content.
    """
    target_id = getattr(target, 'section_id', '')
    target_evidence = section_evidence_map.get(target_id, set())

    # Score other sections
    scored = []
    for sec in all_sections:
        sid = getattr(sec, 'section_id', '')
        if sid == target_id:
            continue

        score = 0.0
        sec_evidence = section_evidence_map.get(sid, set())

        # Jaccard similarity on evidence
        if target_evidence and sec_evidence:
            intersection = len(target_evidence & sec_evidence)
            union = len(target_evidence | sec_evidence)
            if union > 0:
                score += (intersection / union) * 2.0  # Weight evidence overlap heavily

        # Adjacency bonus (use list index position, not schema order field)
        sec_index = section_index_map.get(sid, -1)
        if sec_index >= 0 and abs(sec_index - target_index) <= 1:
            score += 1.0  # Adjacent sections get bonus

        scored.append((sec, score))

    # Sort by score descending, take top max_context
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[:max_context]

    if not selected:
        return ""

    parts = []
    for sec, score in selected:
        title = getattr(sec, 'title', 'Untitled')
        content = getattr(sec, 'content', '')[:500]
        parts.append(f"### {title}\n{content}\n")

    return "\n".join(parts)


def _detect_contradictions(reflection: dict) -> list[dict]:
    """Parse contradictions from reflection LLM output.

    Args:
        reflection: Parsed JSON dict from LLM.

    Returns:
        List of contradiction dicts with keys: claim, conflicts_with, resolution.
    """
    contradictions = reflection.get("contradictions", [])
    if not isinstance(contradictions, list):
        return []
    return [
        c for c in contradictions
        if isinstance(c, dict) and c.get("claim")
    ]


def _parse_reflection_json(content: str) -> dict | None:
    """Extract and parse JSON from LLM response content."""
    if not content:
        return None
    # Try direct parse
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass
    # Try extracting from code fence
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # Try finding first { ... }
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def _revise_with_reflection(
    client,
    section: SectionDraft,
    reflection: dict,
    evidence: list[dict],
    bond_analysis: dict | None = None,
) -> SectionDraft | None:
    """M-13: Revise a single section based on reflection + bond findings.

    Uses targeted edit instructions from structural bond analysis
    plus LLM reflection to make precise, evidence-based edits.

    Args:
        client: OpenRouter LLM client.
        section: The section to revise.
        reflection: Parsed reflection results.
        evidence: Available evidence for citations.
        bond_analysis: Optional bond analysis results for targeted edits.

    Returns:
        Revised SectionDraft, or None if revision fails.
    """
    contradictions = reflection.get("contradictions", [])
    redundancies = reflection.get("redundancies", [])
    cross_refs = reflection.get("cross_references", [])

    instructions = []
    if contradictions:
        for c in contradictions[:3]:
            instructions.append(
                f"- RESOLVE contradiction: '{c.get('claim', '')[:100]}' "
                f"conflicts with '{c.get('conflicts_with', '')[:100]}'. "
                f"Resolution: {c.get('resolution', 'align with strongest evidence')[:100]}"
            )
    if redundancies:
        for r in redundancies[:3]:
            instructions.append(
                f"- REMOVE redundancy: '{r.get('claim', '')[:100]}' "
                f"already covered in '{r.get('already_in', '')[:50]}'"
            )
    if cross_refs:
        for cr in cross_refs[:3]:
            instructions.append(
                f"- ADD cross-reference: '{cr.get('from_claim', '')[:100]}' "
                f"relates to section '{cr.get('relates_to_section', '')[:50]}'"
            )

    if not instructions:
        return None

    prompt = (
        "Revise the following research section based on cross-section reflection.\n\n"
        f"SECTION TITLE: {getattr(section, 'title', '')}\n"
        f"CURRENT CONTENT:\n{getattr(section, 'content', '')}\n\n"
        "REVISION INSTRUCTIONS:\n"
        + "\n".join(instructions)
        + "\n\nIMPORTANT RULES:\n"
        "- Keep ALL existing [CITE:ev_xxx] markers\n"
        "- Do NOT remove content that is not explicitly redundant\n"
        "- Do NOT add new claims without [CITE:evidence_id] markers\n"
        "- CRITICAL: Preserve ALL specific numbers, dollar amounts, percentages, and quantities exactly as written\n"
        "- Do NOT paraphrase or omit any numerical data points\n"
        "- Do NOT remove sentences that contain specific dollar amounts or statistics\n"
        "- Maintain the same academic tone and depth\n"
        "- Output ONLY the revised section content (no title, no metadata)\n"
    )

    try:
        resp = await client.generate(
            prompt, max_tokens=int(os.getenv("PG_REDUNDANCY_REWRITE_MAX_TOKENS", "8192")),
        )
        revised_content = getattr(resp, 'content', '') or ''
        if not revised_content or len(revised_content) < 50:
            return None

        # M-01: Sync evidence_ids from actual CITE markers in revised content
        from src.polaris_graph.synthesis.section_utils import sync_evidence_ids_from_content
        return sync_evidence_ids_from_content(SectionDraft(
            section_id=getattr(section, 'section_id', ''),
            title=getattr(section, 'title', ''),
            content=revised_content,
            claims_made=getattr(section, 'claims_made', []),
            evidence_ids=getattr(section, 'evidence_ids', []),
        ))
    except Exception as exc:
        logger.warning(
            "[MoST-R] Revision LLM call failed for '%s': %s",
            getattr(section, 'title', '')[:40], str(exc)[:200],
        )
        return None


def _build_bond_context(
    bond_analysis: dict | None,
    section_id: str,
) -> str:
    """M-12: Build structural analysis context from bond results.

    Formats findings from all 4 bond types for injection into
    the Phase R reflection prompt.

    Args:
        bond_analysis: Dict with covalent/ionic/disulfide/peptide results.
        section_id: The section being revised.

    Returns:
        Formatted structural analysis string, or empty string.
    """
    if not bond_analysis:
        return ""

    parts = []

    # Covalent findings
    covalent = bond_analysis.get("covalent", {})
    if covalent:
        weak = [b for b in covalent.get("weak_bonds", []) if b.get("section_id") == section_id]
        broken = [b for b in covalent.get("broken_bonds", []) if b.get("section_id") == section_id]
        if weak or broken:
            parts.append("CLAIM-EVIDENCE BINDING:")
            for b in broken[:3]:
                parts.append(
                    f"  - BROKEN: \"{b['sentence'][:60]}\" cites {b['evidence_id']} "
                    f"(similarity={b['similarity']} — likely misattributed)"
                )
            for b in weak[:3]:
                parts.append(
                    f"  - WEAK: \"{b['sentence'][:60]}\" cites {b['evidence_id']} "
                    f"(similarity={b['similarity']})"
                )

    # Ionic findings
    ionic = bond_analysis.get("ionic", {})
    if ionic:
        try:
            from src.polaris_graph.synthesis.ionic_rebalancer import (
                format_ionic_findings_for_phase_r,
            )
            ionic_text = format_ionic_findings_for_phase_r(ionic, section_id)
            if ionic_text and "No evidence" not in ionic_text:
                parts.append(f"EVIDENCE PLACEMENT:\n{ionic_text}")
        except ImportError:
            pass

    # Disulfide findings
    disulfide = bond_analysis.get("disulfide", {})
    if disulfide:
        try:
            from src.polaris_graph.synthesis.disulfide_bridge import (
                format_disulfide_findings_for_phase_r,
            )
            disulfide_text = format_disulfide_findings_for_phase_r(disulfide, section_id)
            if disulfide_text and "No cross-section" not in disulfide_text:
                parts.append(f"SOURCE CONSISTENCY:\n{disulfide_text}")
        except ImportError:
            pass

    # Peptide findings
    peptide = bond_analysis.get("peptide", {})
    if peptide:
        try:
            from src.polaris_graph.synthesis.narrative_flow_analyzer import (
                format_peptide_findings_for_phase_r,
            )
            peptide_text = format_peptide_findings_for_phase_r(peptide, section_id)
            if peptide_text and "No narrative" not in peptide_text:
                parts.append(f"NARRATIVE FLOW:\n{peptide_text}")
        except ImportError:
            pass

    return "\n\n".join(parts)
