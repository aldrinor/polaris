"""v2 Section Verifier (Parallel Scoring, Sequential Rewrites).

Verifies section claims against evidence and surgically rewrites
hallucinated passages, with:
- Parallel claim scoring via CoT schema (Fix R5-#4)
- Citation-priority evidence context (Fix R4-#5)
- Sequential surgical rewrites to prevent race conditions (Fix R6-#1)
- Safe fallback on failure (Fix R6-#4)
- TPM throttling (Fix R5-#3)

CRITICAL (Fix R6-#1): Scoring is read-only and can be parallelized.
But rewrites MUST be sequential. If Paragraphs 2 and 5 both need fixing,
parallel rewrites would each receive the same base draft and the last
to finish would overwrite the other's fixes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from src.polaris_graph.retrieval.llm_throttle import throttled_llm_call
from src.polaris_graph.retrieval.verify_context import build_verify_context
from src.polaris_graph.retrieval.verify_schemas import (
    ClaimVerification,
    VERIFY_SYSTEM_PROMPT,
    VERIFY_USER_TEMPLATE,
)
from src.polaris_graph.state import ReportSection

logger = logging.getLogger("polaris_graph")

# Minimum confidence to accept a claim as supported
# V2_E2E_006: 0.6 was too strict (flagged ~60% of claims)
VERIFY_CONFIDENCE_THRESHOLD = float(
    os.getenv("PG_V2_VERIFY_CONFIDENCE", "0.4")
)

# Max claims to verify per section (cost cap)
# V2_E2E_006: 20 claims × 14 sections = 280 scorings, too many
MAX_CLAIMS_PER_SECTION = int(
    os.getenv("PG_V2_MAX_CLAIMS_PER_SECTION", "8")
)

# Max rewrites per section (prevents runaway rewrite loops)
# V2_E2E_006: 170 rewrites in 2h35m, never reached assembly
MAX_REWRITES_PER_SECTION = int(
    os.getenv("PG_V2_MAX_REWRITES_PER_SECTION", "3")
)

# Max tokens for surgical rewrite
REWRITE_MAX_TOKENS = int(os.getenv("PG_V2_REWRITE_MAX_TOKENS", "4096"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def verify_section(
    client: Any,
    section: ReportSection,
    section_evidence: list[dict[str, Any]],
) -> dict[str, ReportSection]:
    """Verify and optionally rewrite a section.

    Fix R6-#4 (Parallel Fallback): Top-level try/except ensures this
    never crashes sibling tasks when called via LangGraph Send.

    Returns:
        dict[section_id, ReportSection] — for merge_sections_reducer.
    """
    try:
        return await _verify_section_inner(client, section, section_evidence)
    except Exception as e:
        logger.error(
            "Verify '%s' failed, returning original: %s",
            section.get("section_id", "?"), str(e)[:200],
        )
        # Fix R6-#4: Return original section unchanged on failure
        return {section["section_id"]: section}


async def _verify_section_inner(
    client: Any,
    section: ReportSection,
    section_evidence: list[dict[str, Any]],
) -> dict[str, ReportSection]:
    """Core verification logic."""
    section_id = section["section_id"]
    content = section["content"]

    # Step 1: Extract verifiable claims from the section
    claims = _extract_claims(content)
    if not claims:
        logger.info("Section '%s': no claims to verify", section.get("title"))
        return {section_id: section}

    # Cap claims to verify (cost control)
    claims_to_verify = claims[:MAX_CLAIMS_PER_SECTION]

    # Step 2: Score ALL claims in parallel (read-only — Fix R6-#1)
    score_tasks = [
        _score_one_claim(client, claim, section_evidence)
        for claim in claims_to_verify
    ]
    results: list[ClaimVerification | None] = await asyncio.gather(
        *score_tasks, return_exceptions=False,
    )

    # Step 3: Identify flagged claims (unsupported or low confidence)
    flagged: list[tuple[str, ClaimVerification]] = []
    supported_count = 0

    for claim, result in zip(claims_to_verify, results):
        if result is None:
            continue
        if result.is_supported and result.confidence >= VERIFY_CONFIDENCE_THRESHOLD:
            supported_count += 1
        else:
            flagged.append((claim, result))

    total = len(claims_to_verify)
    faithfulness = supported_count / total if total > 0 else 1.0
    logger.info(
        "Section '%s': %d/%d claims supported (%.1f%%), %d flagged",
        section.get("title"), supported_count, total,
        faithfulness * 100, len(flagged),
    )

    if not flagged:
        return {section_id: section}

    # Step 4: Apply surgical rewrites SEQUENTIALLY (Fix R6-#1)
    #
    # CRITICAL: We CANNOT parallelize rewrites. If Paragraph 2 and
    # Paragraph 5 both need fixing:
    #   - Parallel: Both receive same base draft → last finisher wins → 50% fix loss
    #   - Sequential: Each rewrite builds on the previous → all fixes preserved
    current_content = content
    rewrites_applied = 0

    for claim_text, verdict in flagged:
        # V2_E2E_006 fix: Cap rewrites per section to prevent runaway loops
        if rewrites_applied >= MAX_REWRITES_PER_SECTION:
            logger.info(
                "Section '%s': hit rewrite cap (%d), skipping %d remaining",
                section.get("title"), MAX_REWRITES_PER_SECTION,
                len(flagged) - rewrites_applied,
            )
            break

        try:
            rewritten = await _surgical_rewrite(
                client,
                current_content,
                claim_text,
                verdict.reasoning,
                section_evidence,
            )
            if rewritten and rewritten != current_content:
                current_content = rewritten
                rewrites_applied += 1
        except Exception as e:
            logger.warning(
                "Rewrite failed for claim in '%s': %s",
                section.get("title"), str(e)[:120],
            )
            # Continue with remaining rewrites — don't abandon all fixes

    if rewrites_applied > 0:
        logger.info(
            "Section '%s': %d/%d rewrites applied",
            section.get("title"), rewrites_applied, len(flagged),
        )

    # Return updated section
    updated: ReportSection = {
        "section_id": section_id,
        "title": section["title"],
        "content": current_content,
        "word_count": len(current_content.split()),
        "citation_ids": section["citation_ids"],
        "evidence_ids": section["evidence_ids"],
    }
    return {section_id: updated}


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

def _extract_claims(content: str) -> list[str]:
    """Extract verifiable claims from section content.

    A "claim" is any sentence that contains a factual assertion
    (typically with a citation marker, number, or specific entity).
    We skip headers, bullet points, and meta-text.
    """
    claims: list[str] = []

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", content)

    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 30:
            continue
        # Skip markdown headers
        if sent.startswith("#"):
            continue
        # Skip bullet-only lines
        if sent.startswith("- ") and len(sent) < 80:
            continue
        # Skip admonition blocks
        if sent.startswith(">"):
            continue
        # A verifiable claim typically has a number, citation, or specific entity
        has_number = bool(re.search(r"\d+\.?\d*\s*(%|mg|kg|kPa|USD|mm|μm|L|m³)", sent))
        has_citation = "[SRC-" in sent or "[CITE:" in sent
        has_entity = bool(re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", sent))

        if has_number or has_citation or has_entity:
            claims.append(sent)

    return claims


# ---------------------------------------------------------------------------
# Claim scoring (parallel-safe, read-only)
# ---------------------------------------------------------------------------

async def _score_one_claim(
    client: Any,
    claim: str,
    section_evidence: list[dict[str, Any]],
) -> ClaimVerification | None:
    """Score a single claim against section evidence.

    Fix R5-#4: Uses ClaimVerification schema to force CoT reasoning
    before the boolean verdict, preventing sycophantic rubber-stamping.

    This function is READ-ONLY — safe to call in parallel.
    """
    try:
        # Fix R4-#5: Citation-priority evidence context
        context = build_verify_context(claim, section_evidence)

        if not context:
            return ClaimVerification(
                reasoning="No evidence available for verification.",
                is_supported=False,
                confidence=0.0,
            )

        prompt = VERIFY_USER_TEMPLATE.format(claim=claim, evidence=context)

        result = await throttled_llm_call(
            client.generate_structured,
            prompt=prompt,
            system=VERIFY_SYSTEM_PROMPT,
            schema=ClaimVerification,
            max_tokens=1024,
        )

        if isinstance(result, ClaimVerification):
            return result
        if isinstance(result, dict):
            return ClaimVerification(**result)
        return None

    except Exception as e:
        logger.debug("Claim scoring failed: %s", str(e)[:120])
        # Score failure = assume unsupported (skeptical default)
        return ClaimVerification(
            reasoning=f"Verification failed: {str(e)[:100]}",
            is_supported=False,
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Surgical rewrite (SEQUENTIAL — Fix R6-#1)
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = """You are a precision editor fixing a single hallucinated claim in a research report.

RULES:
1. You will receive the FULL section text and ONE flagged claim.
2. Find the flagged claim in the text and either:
   a. REMOVE it entirely if no supporting evidence exists
   b. REWRITE it to accurately reflect what the evidence actually says
3. Do NOT change ANY other part of the text. Preserve all formatting, citations, and structure.
4. Output the COMPLETE section text with only the targeted fix applied.
5. If you cannot find the exact claim, return the text unchanged."""

_REWRITE_USER = """SECTION TEXT:
{section_text}

FLAGGED CLAIM:
{claim}

REASON IT WAS FLAGGED:
{reasoning}

AVAILABLE EVIDENCE:
{evidence}

Return the complete section text with ONLY this claim fixed. Do not change anything else."""


async def _surgical_rewrite(
    client: Any,
    section_text: str,
    claim_text: str,
    reasoning: str,
    section_evidence: list[dict[str, Any]],
) -> str:
    """Apply a single surgical rewrite to fix one hallucinated claim.

    Fix R6-#1: This is called SEQUENTIALLY for each flagged claim.
    Each call receives the output of the previous rewrite, ensuring
    all fixes accumulate correctly.
    """
    # Build minimal evidence context for the rewrite
    context = build_verify_context(claim_text, section_evidence, max_tokens=3000)

    prompt = _REWRITE_USER.format(
        section_text=section_text,
        claim=claim_text,
        reasoning=reasoning,
        evidence=context,
    )

    llm_response = await throttled_llm_call(
        client.generate,
        prompt=prompt,
        system=_REWRITE_SYSTEM,
        max_tokens=REWRITE_MAX_TOKENS,
    )

    # Extract text from LLMResponse object
    result = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

    if not result or not result.strip():
        return section_text  # unchanged on empty response

    # Sanity check: rewrite shouldn't be drastically different
    result = result.strip()
    original_words = len(section_text.split())
    rewrite_words = len(result.split())

    if rewrite_words < original_words * 0.5:
        logger.warning(
            "Rewrite shrank section by >50%% (%d -> %d words), rejecting",
            original_words, rewrite_words,
        )
        return section_text

    return result
