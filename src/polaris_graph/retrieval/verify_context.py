"""Verification Context Builder (Fix R4-#5).

When verifying a claim against section evidence, the verifier must:
1. Not exceed the LLM's context window (many models hard-cap at 8K tokens)
2. Prioritize the CITED source — if a claim cites [SRC-005], that evidence
   MUST be at the top of the verification prompt to survive any truncation

Without this, sending 15 chunks (~15,000 tokens) to an 8K-context model
silently truncates the prompt, and the evidence for the cited source lands
in the truncated tail. The model never sees it, falsely flags the claim
as UNSUPPORTED, triggering unnecessary rewrites that degrade the report.

Usage:
    from src.polaris_graph.retrieval.verify_context import build_verify_context

    context_text = build_verify_context(
        claim="The membrane achieved 99.2% E. coli removal [SRC-005]",
        section_evidence=evidence_list,
        max_tokens=6000,
    )
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("polaris_graph")

# Max tokens for verification context — must fit in model's context window
# with room for the claim, system prompt, and response
VERIFY_MAX_TOKENS = int(os.getenv("PG_VERIFY_MAX_TOKENS", "6000"))

# Chars per token estimate (conservative)
_CHARS_PER_TOKEN = 4

# Regex to extract SRC-NNN citation keys from a claim
_CITE_RE = re.compile(r"\[SRC-(\d{3})\]")

# Regex to extract legacy [CITE:ev_xxx] markers
_LEGACY_CITE_RE = re.compile(r"\[CITE:([^\]]+)\]")


def build_verify_context(
    claim: str,
    section_evidence: list[dict[str, Any]],
    max_tokens: int = VERIFY_MAX_TOKENS,
) -> str:
    """Build a verification context with citation-priority ordering.

    Fix R4-#5: Ensures the cited source's evidence is FIRST in the context,
    guaranteeing it survives any model truncation. Remaining evidence fills
    the budget in relevance-descending order.

    Args:
        claim: The claim text, possibly containing [SRC-NNN] or [CITE:id] markers.
        section_evidence: List of EvidencePiece-compatible dicts for the section.
        max_tokens: Maximum tokens for the full context string.

    Returns:
        Formatted verification context string, ready for LLM prompt injection.
    """
    if not section_evidence:
        return ""

    max_chars = max_tokens * _CHARS_PER_TOKEN

    # Step 1: Identify cited sources from the claim
    cited_src_keys = set(_CITE_RE.findall(claim))
    cited_src_keys = {f"SRC-{k}" for k in cited_src_keys}

    cited_ev_ids = set(_LEGACY_CITE_RE.findall(claim))

    # Step 2: Partition evidence into cited (priority) and remaining
    cited_evidence: list[dict[str, Any]] = []
    remaining_evidence: list[dict[str, Any]] = []

    for ev in section_evidence:
        ev_citation_key = ev.get("citation_key", "")
        ev_id = ev.get("evidence_id", "")

        if ev_citation_key in cited_src_keys or ev_id in cited_ev_ids:
            cited_evidence.append(ev)
        else:
            remaining_evidence.append(ev)

    # Step 3: Sort remaining by relevance (highest first)
    remaining_evidence.sort(
        key=lambda e: e.get("relevance_score", 0.0),
        reverse=True,
    )

    # Step 4: Build context string with budget tracking
    parts: list[str] = []
    chars_used = 0

    # Priority block: cited evidence FIRST
    if cited_evidence:
        parts.append("=== CITED EVIDENCE (verify claim against these first) ===")
        chars_used += 60

        for ev in cited_evidence:
            block = _format_evidence_block(ev)
            if chars_used + len(block) > max_chars:
                # Even cited evidence must respect the budget
                # but we always include at least one cited piece
                if not any("CITED" in p for p in parts[1:]):
                    parts.append(block)
                    chars_used += len(block)
                break
            parts.append(block)
            chars_used += len(block)

    # Fill remaining budget with other evidence
    if remaining_evidence:
        parts.append("\n=== SUPPORTING EVIDENCE ===")
        chars_used += 30

        for ev in remaining_evidence:
            block = _format_evidence_block(ev)
            if chars_used + len(block) > max_chars:
                break
            parts.append(block)
            chars_used += len(block)

    context = "\n".join(parts)

    # Log stats for debugging
    total_available = len(section_evidence)
    included = context.count("[SRC-") + context.count("Evidence ID:")
    if total_available > 0 and included < total_available:
        logger.debug(
            "Verify context: %d/%d evidence included (budget %d tokens, %d cited priority)",
            included, total_available, max_tokens, len(cited_evidence),
        )

    return context


def _format_evidence_block(ev: dict[str, Any]) -> str:
    """Format a single evidence piece for the verification prompt."""
    citation_key = ev.get("citation_key", "")
    ev_id = ev.get("evidence_id", "")
    source_title = ev.get("source_title", "Unknown")
    content = ev.get("direct_quote", "") or ev.get("statement", "")
    relevance = ev.get("relevance_score", 0.0)
    tier = ev.get("quality_tier", "")

    header = f"\n--- Evidence ID: {ev_id}"
    if citation_key:
        header += f" [{citation_key}]"
    if tier:
        header += f" ({tier})"
    header += f" ---\nSource: {source_title}\n"

    return f"{header}{content}\n"
