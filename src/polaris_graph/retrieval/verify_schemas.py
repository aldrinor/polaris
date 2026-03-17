"""Verification Schemas (Fix R5-#4 — Verifier Sycophancy Loophole).

Standard instruction-tuned LLMs suffer from "affirmative bias" (sycophancy).
A simple prompt like "Is this claim supported? YES/NO" returns YES >90% of
the time if the claim sounds scientifically plausible, effectively rubber-
stamping hallucinations.

Fix: Force Chain-of-Thought via structured output. The model MUST generate
`reasoning` tokens BEFORE the boolean `is_supported` verdict. This grounds
the decision in actual evidence analysis, drastically reducing false positives.

Usage:
    from src.polaris_graph.retrieval.verify_schemas import (
        ClaimVerification,
        VERIFY_SYSTEM_PROMPT,
        VERIFY_USER_TEMPLATE,
    )

    result = await client.generate_structured(
        prompt=VERIFY_USER_TEMPLATE.format(claim=claim, evidence=context),
        system=VERIFY_SYSTEM_PROMPT,
        schema=ClaimVerification,
    )
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimVerification(BaseModel):
    """Structured output for claim verification.

    Fix R5-#4: Forces Chain-of-Thought by requiring `reasoning` BEFORE
    the boolean verdict. The model must articulate WHY a claim is or
    isn't supported, preventing sycophantic auto-approval.
    """

    reasoning: str = Field(
        description=(
            "Step-by-step analysis comparing the claim to the provided evidence. "
            "You MUST: (1) identify the specific fact in the claim, (2) search "
            "for supporting evidence in the provided text, (3) quote the exact "
            "passage that supports or contradicts the claim, (4) note if the "
            "evidence is partial, ambiguous, or absent. Be skeptical — do not "
            "assume support just because the claim sounds plausible."
        ),
    )
    is_supported: bool = Field(
        description=(
            "True ONLY if the evidence contains a specific passage that directly "
            "supports the factual claim. False if: the evidence is ambiguous, "
            "partially related, discusses a different context, or is absent. "
            "When in doubt, return False."
        ),
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the verdict (0.0 = pure guess, 1.0 = exact quote match). "
            "High confidence requires an exact or near-exact passage in the evidence."
        ),
    )
    supporting_quote: str = Field(
        default="",
        description=(
            "The exact passage from the evidence that supports the claim. "
            "Empty string if is_supported is False."
        ),
    )


# ---------------------------------------------------------------------------
# Verification prompts (anti-sycophancy, evidence-grounded)
# ---------------------------------------------------------------------------

VERIFY_SYSTEM_PROMPT = """You are a SKEPTICAL fact-checker verifying claims against provided evidence.

Your job is to determine if a specific claim is DIRECTLY SUPPORTED by the evidence text.

CRITICAL RULES:
1. A claim is SUPPORTED only if the evidence contains a specific passage that states or directly implies the same fact.
2. A claim is NOT SUPPORTED if:
   - The evidence discusses a related but different topic
   - The evidence mentions the same subject but with different values/conclusions
   - The evidence is ambiguous or could be interpreted multiple ways
   - You cannot find a specific passage to quote
3. Do NOT assume support based on:
   - The claim sounding scientifically plausible
   - The evidence being about the same general topic
   - Your own knowledge (you may ONLY use the provided evidence)
4. You MUST quote the exact supporting passage if you mark is_supported=True.
5. If no exact passage exists, is_supported MUST be False.

Think step by step. Be rigorous. False negatives are less harmful than false positives."""

VERIFY_USER_TEMPLATE = """CLAIM TO VERIFY:
{claim}

EVIDENCE:
{evidence}

Analyze the evidence step by step. Is this specific claim directly supported by the evidence above?"""
