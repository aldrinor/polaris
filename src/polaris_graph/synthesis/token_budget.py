"""
Token-budget-aware prompt construction for section writing.

Problem: Fixed PG_SECTION_EVIDENCE_TOP_K=30, each piece formatted at ~118
tokens. 30 x 118 = 3,540 tokens regardless of section needs. No priority
ordering.

Solution: TokenBudgetAllocator fills section prompts within explicit token
budgets using tiered formatting:
  - Top 3 (L2): Full statement + 500-char quote + metadata (~118 tokens)
  - Next N (L1): Statement + source_title + verification tag (~30 tokens)
  - Remainder (L0): evidence_id + one-line claim (~15 tokens)

Result: 6,000-token budget holds ~93 evidence vs current 30.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration (LAW VI: from env vars)
PG_SECTION_TOKEN_BUDGET = int(os.getenv("PG_SECTION_TOKEN_BUDGET", "6000"))
PG_EVIDENCE_FORMAT_TOP_FULL = int(os.getenv("PG_EVIDENCE_FORMAT_TOP_FULL", "3"))
PG_EVIDENCE_CANDIDATE_POOL = int(os.getenv("PG_EVIDENCE_CANDIDATE_POOL", "100"))
PG_EVIDENCE_L0_MAX_CHARS = int(os.getenv("PG_EVIDENCE_L0_MAX_CHARS", "100"))
PG_EVIDENCE_L1_MAX_CHARS = int(os.getenv("PG_EVIDENCE_L1_MAX_CHARS", "300"))

# Tier weights for priority scoring
_TIER_WEIGHTS = {"GOLD": 1.0, "SILVER": 0.7, "BRONZE": 0.4}


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Uses chars/3.5 approximation (validated against API usage within 15%).

    Args:
        text: Input text string.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def _compute_priority(ev: dict) -> float:
    """Compute evidence priority score for budget-aware selection.

    Priority = tier_weight * relevance * cross_ref_bonus * corroboration_bonus

    Args:
        ev: Evidence dict.

    Returns:
        Float priority score (higher = more important).
    """
    tier = ev.get("quality_tier", "BRONZE")
    tier_weight = _TIER_WEIGHTS.get(tier, 0.4)
    relevance = ev.get("relevance_score", 0.5)

    # Cross-reference bonus: evidence confirmed by multiple sources
    cross_ref_bonus = 1.2 if ev.get("cross_referenced") else 1.0

    # Corroboration bonus: evidence with multiple supporting sources
    corroborating = ev.get("corroborating_sources", 1) or 1
    corroboration_bonus = min(1.0 + 0.1 * (corroborating - 1), 1.5)

    # Verification bonus: verified evidence gets a boost
    if ev.get("is_faithful") is True:
        verify_bonus = 1.15
    else:
        verify_bonus = 1.0

    return tier_weight * relevance * cross_ref_bonus * corroboration_bonus * verify_bonus


def format_l0(ev: dict) -> str:
    """Ultra-compact format: evidence_id + truncated claim (~15 tokens).

    Args:
        ev: Evidence dict.

    Returns:
        Formatted string.
    """
    eid = ev.get("evidence_id", "?")
    stmt = ev.get("statement", "")[:PG_EVIDENCE_L0_MAX_CHARS]
    return f"[{eid}] {stmt}"


def format_l1(ev: dict) -> str:
    """Compact format: statement + source_title + verification tag (~30 tokens).

    Args:
        ev: Evidence dict.

    Returns:
        Formatted string.
    """
    eid = ev.get("evidence_id", "?")
    stmt = ev.get("statement", "")[:PG_EVIDENCE_L1_MAX_CHARS]
    title = ev.get("source_title", "")[:60]
    year = ev.get("year", "?")

    # Verification tag
    if ev.get("is_faithful") is True:
        tag = "[VERIFIED]"
    else:
        tag = "[UNVERIFIED]"

    # GRADE-PASS: Include certainty rating when available
    grade = ev.get("grade_certainty", "")
    grade_tag = f" [GRADE: {grade}]" if grade else ""

    return (
        f"Evidence ID: {eid} {tag}{grade_tag}\n"
        f"  Statement: {stmt}\n"
        f"  Source: {title} ({year})"
    )


def format_l2(ev: dict) -> str:
    """Full format: statement + 500-char quote + metadata (~118 tokens).

    This is the current full format from _format_evidence_for_writing().

    Args:
        ev: Evidence dict.

    Returns:
        Formatted string.
    """
    eid = ev.get("evidence_id", "?")
    stmt = ev.get("statement", "")
    quote = ev.get("direct_quote", "")
    title = ev.get("source_title", "")
    year = ev.get("year", "?")
    url = ev.get("source_url", "")
    tier = ev.get("quality_tier", "?")
    relevance = ev.get("relevance_score", 0.0)

    # Verification tag
    verification_method = ev.get("verification_method", "")
    if verification_method == "api_error" or verification_method == "":
        tag = "[UNVERIFIED]"
    elif ev.get("is_faithful") is True:
        tag = "[VERIFIED]"
    else:
        tag = "[UNVERIFIED]"

    quote_line = f'  Direct quote: "{quote[:500]}"' if quote else ""

    # GRADE-PASS: Include certainty rating when available
    grade = ev.get("grade_certainty", "")
    grade_tag = f" | GRADE: {grade}" if grade else ""

    return (
        f"Evidence ID: {eid} {tag}\n"
        f"  Statement: {stmt}\n"
        f"{quote_line}\n"
        f"  Source: {title} ({year})\n"
        f"  URL: {url}\n"
        f"  Quality: {tier} | Relevance: {relevance:.2f}{grade_tag}"
    )


class TokenBudgetAllocator:
    """Allocates evidence to fill a token budget with tiered formatting.

    Top-N evidence get full L2 format (with quotes), next batch gets L1
    (compact), remainder gets L0 (ultra-compact). This allows 3x more
    evidence per section while keeping prompts within budget.
    """

    def __init__(
        self,
        token_budget: int = PG_SECTION_TOKEN_BUDGET,
        top_full_count: int = PG_EVIDENCE_FORMAT_TOP_FULL,
    ):
        self.token_budget = token_budget
        self.top_full_count = top_full_count

    def available_evidence_tokens(
        self,
        system_prompt: str,
        user_template: str,
    ) -> int:
        """Compute remaining token budget for evidence after system/user prompts.

        Args:
            system_prompt: The system prompt text.
            user_template: The user prompt template (without evidence block).

        Returns:
            Available tokens for evidence formatting.
        """
        system_tokens = estimate_tokens(system_prompt)
        template_tokens = estimate_tokens(user_template)
        available = self.token_budget - system_tokens - template_tokens
        return max(available, 500)  # Minimum 500 tokens for evidence

    def select_and_format_evidence(
        self,
        evidence: list[dict],
        available_tokens: int,
        section_title: str = "",
    ) -> tuple[str, list[str]]:
        """Select and format evidence within a token budget.

        Evidence is sorted by priority score, then formatted with tiered
        detail levels to maximize the number of pieces within budget:
        - Top N (PG_EVIDENCE_FORMAT_TOP_FULL): Full L2 format
        - Next batch: Compact L1 format
        - Remainder: Ultra-compact L0 format

        Args:
            evidence: Candidate evidence pieces (already filtered by relevance).
            available_tokens: Maximum tokens for the evidence block.
            section_title: Section title for logging.

        Returns:
            (formatted_text, selected_evidence_ids) tuple.
        """
        if not evidence:
            return "No evidence assigned to this section.", []

        # Sort by priority (highest first)
        sorted_evidence = sorted(evidence, key=_compute_priority, reverse=True)

        formatted_lines: list[str] = []
        selected_ids: list[str] = []
        tokens_used = 0
        l2_count = 0
        l1_count = 0
        l0_count = 0

        for ev in sorted_evidence:
            eid = ev.get("evidence_id", "?")

            # Determine format tier based on position
            if l2_count < self.top_full_count:
                formatted = format_l2(ev)
                format_tier = "L2"
            elif tokens_used < available_tokens * 0.6:
                # Use L1 until 60% budget used
                formatted = format_l1(ev)
                format_tier = "L1"
            else:
                # Use L0 for the rest
                formatted = format_l0(ev)
                format_tier = "L0"

            entry_tokens = estimate_tokens(formatted)

            # Check if adding this evidence exceeds budget
            if tokens_used + entry_tokens > available_tokens:
                # Try L0 format as last resort
                if format_tier != "L0":
                    formatted = format_l0(ev)
                    entry_tokens = estimate_tokens(formatted)
                    if tokens_used + entry_tokens > available_tokens:
                        break
                    format_tier = "L0"
                else:
                    break

            formatted_lines.append(formatted)
            selected_ids.append(eid)
            tokens_used += entry_tokens

            if format_tier == "L2":
                l2_count += 1
            elif format_tier == "L1":
                l1_count += 1
            else:
                l0_count += 1

        logger.info(
            "[token_budget] Section '%s': %d evidence in %d tokens "
            "(L2=%d, L1=%d, L0=%d, budget=%d, utilization=%.0f%%)",
            section_title[:50],
            len(selected_ids),
            tokens_used,
            l2_count,
            l1_count,
            l0_count,
            available_tokens,
            (tokens_used / max(available_tokens, 1)) * 100,
        )

        text = "\n\n".join(formatted_lines) if formatted_lines else (
            "No evidence assigned to this section."
        )
        return text, selected_ids
