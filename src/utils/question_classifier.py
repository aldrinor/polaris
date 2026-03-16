#!/usr/bin/env python3
"""
POLARIS Question Classifier Utility
===================================
Sprint 2: SOTA Architecture - Dynamic Classification

Classifies research questions into question types to load appropriate
processing profiles. Uses keyword matching with optional LLM enhancement.

This is a UTILITY module - can be imported by any phase without violating
phase isolation (LAW VII).

Reference: SymRAG, RAGRouter, DSPy Signatures
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.question_types import (
    QuestionType,
    ClassificationResult,
    DEFAULT_PROFILES,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# KEYWORD PATTERNS FOR CLASSIFICATION
# =============================================================================

# Keywords that indicate question type
CLASSIFICATION_KEYWORDS: Dict[QuestionType, List[str]] = {
    QuestionType.QUANTITATIVE_RESEARCH: [
        "rate", "rates", "percentage", "percent", "%",
        "prevalence", "incidence", "frequency",
        "statistics", "statistical", "data",
        "how many", "how much", "number of",
        "measurement", "measure", "level", "levels",
        "concentration", "contamination", "amount",
        "study", "studies", "research", "survey",
        "correlation", "trend", "pattern",
    ],
    QuestionType.MARKET_ANALYSIS: [
        "market", "industry", "sector",
        "growth", "forecast", "projection",
        "revenue", "sales", "demand",
        "competitive", "competition", "competitor",
        "share", "size", "value",
        "cagr", "trend", "emerging",
        "consumer", "customer", "buyer",
    ],
    QuestionType.REGULATORY_COMPLIANCE: [
        "regulation", "regulatory", "regulated",
        "compliance", "compliant", "comply",
        "law", "legal", "legislation",
        "standard", "standards", "requirement",
        "guideline", "guidelines", "policy",
        "permit", "license", "certification",
        "epa", "fda", "osha", "usda",
        "act", "code", "statute",
    ],
    QuestionType.PRODUCT_COMPARISON: [
        "compare", "comparison", "comparing",
        "versus", "vs", "vs.",
        "difference", "differences", "differ",
        "better", "best", "worst",
        "advantage", "disadvantage",
        "pros", "cons", "tradeoff",
        "alternative", "alternatives",
        "review", "reviews", "rating",
    ],
    QuestionType.QUALITATIVE_RESEARCH: [
        "opinion", "opinions", "perspective",
        "experience", "experiences", "perception",
        "attitude", "attitudes", "belief",
        "interview", "focus group", "case study",
        "qualitative", "exploratory",
        "why", "how do people", "what do people think",
        "behavior", "behaviour", "motivation",
        "think", "feel", "perceive", "view",
        "consumer", "consumers", "user", "users",
        "feedback", "sentiment", "satisfaction",
    ],
    QuestionType.TECHNICAL_SPECIFICATION: [
        "specification", "specifications", "spec",
        "technical", "technology", "mechanism",
        "how does", "how it works", "process",
        "design", "architecture", "implementation",
        "performance", "efficiency", "capacity",
        "feature", "features", "capability",
        "protocol", "method", "technique",
    ],
}

# Phrases that strongly indicate type (higher weight)
STRONG_INDICATORS: Dict[QuestionType, List[str]] = {
    QuestionType.QUANTITATIVE_RESEARCH: [
        "contamination rate", "infection rate", "prevalence rate",
        "what percentage", "how prevalent", "statistical analysis",
        "peer-reviewed study", "research study", "scientific data",
    ],
    QuestionType.MARKET_ANALYSIS: [
        "market size", "market share", "market growth",
        "industry analysis", "competitive landscape",
        "market forecast", "market trend",
    ],
    QuestionType.REGULATORY_COMPLIANCE: [
        "regulatory requirement", "compliance requirement",
        "legal requirement", "what regulations",
        "must comply", "regulatory framework",
    ],
    QuestionType.PRODUCT_COMPARISON: [
        "compare products", "product comparison",
        "which is better", "best option",
        "pros and cons", "head to head",
    ],
    QuestionType.QUALITATIVE_RESEARCH: [
        "expert opinion", "consumer perception",
        "user experience", "case studies",
        "what do consumers think", "what do people think",
        "how do consumers feel", "consumer attitudes",
    ],
    QuestionType.TECHNICAL_SPECIFICATION: [
        "technical specification", "how does it work",
        "technical requirements", "system design",
    ],
}


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_by_keywords(question: str) -> Tuple[QuestionType, float, List[str]]:
    """
    Classify question type using keyword matching.

    Args:
        question: The research question text

    Returns:
        Tuple of (question_type, confidence, detected_keywords)
    """
    question_lower = question.lower()
    scores: Dict[QuestionType, float] = {qt: 0.0 for qt in QuestionType if qt != QuestionType.UNKNOWN}
    detected: Dict[QuestionType, List[str]] = {qt: [] for qt in QuestionType if qt != QuestionType.UNKNOWN}

    # Check strong indicators first (weight = 3)
    for qt, indicators in STRONG_INDICATORS.items():
        for indicator in indicators:
            if indicator in question_lower:
                scores[qt] += 3.0
                detected[qt].append(indicator)

    # Check regular keywords (weight = 1)
    for qt, keywords in CLASSIFICATION_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary matching for single words
            if len(keyword.split()) == 1:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, question_lower):
                    scores[qt] += 1.0
                    if keyword not in detected[qt]:
                        detected[qt].append(keyword)
            else:
                if keyword in question_lower:
                    scores[qt] += 1.5  # Multi-word phrases slightly higher
                    if keyword not in detected[qt]:
                        detected[qt].append(keyword)

    # Find best match
    if not any(scores.values()):
        return QuestionType.UNKNOWN, 0.0, []

    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    # Calculate confidence based on score and gap to second best
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) > 1 and sorted_scores[1] > 0:
        gap = (best_score - sorted_scores[1]) / best_score
        confidence = min(0.5 + (gap * 0.3) + (min(best_score, 10) / 20), 0.95)
    else:
        confidence = min(0.4 + (min(best_score, 10) / 25), 0.85)

    return best_type, confidence, detected[best_type]


def classify_with_llm(
    question: str,
    vector_id: str,
    llm_client: Optional[object] = None,
) -> Tuple[QuestionType, float, str]:
    """
    Classify question type using LLM.

    Args:
        question: The research question text
        vector_id: Vector ID for context
        llm_client: Optional LLM client (Gemini)

    Returns:
        Tuple of (question_type, confidence, reasoning)
    """
    if llm_client is None:
        # Try to get Gemini client
        try:
            from src.llm import get_gemini_client
            llm_client = get_gemini_client()
        except Exception as e:
            logger.warning(f"Could not initialize LLM client: {e}")
            return QuestionType.UNKNOWN, 0.0, "LLM unavailable"

    # Build classification prompt
    type_descriptions = "\n".join([
        f"- {qt.value}: {DEFAULT_PROFILES[qt].description}"
        for qt in QuestionType if qt != QuestionType.UNKNOWN
    ])

    prompt = f"""Classify this research question into exactly ONE of the following types:

{type_descriptions}

Research Question: {question}

Respond in this exact JSON format:
{{
    "question_type": "<type_value>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Only output valid JSON, nothing else."""

    try:
        response = llm_client.generate_content(prompt)
        response_text = response.text.strip()

        # Parse JSON response
        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)

        result = json.loads(response_text)

        question_type = QuestionType(result.get("question_type", "unknown"))
        confidence = float(result.get("confidence", 0.5))
        reasoning = result.get("reasoning", "")

        return question_type, min(confidence, 0.98), reasoning

    except Exception as e:
        logger.warning(f"LLM classification failed: {e}")
        return QuestionType.UNKNOWN, 0.0, f"LLM error: {str(e)}"


def classify_question(
    question: str,
    vector_id: str = "UNKNOWN",
    use_llm: bool = False,
    llm_client: Optional[object] = None,
) -> ClassificationResult:
    """
    Classify a research question into a question type.

    This is the main entry point for classification. Uses keyword matching
    by default, with optional LLM enhancement for ambiguous cases.

    Args:
        question: The research question text
        vector_id: Vector ID for logging
        use_llm: Whether to use LLM classification (default False for speed)
        llm_client: Optional pre-initialized LLM client

    Returns:
        ClassificationResult with classification details
    """
    # First, try keyword classification (fast, always available)
    keyword_type, keyword_conf, keywords = classify_by_keywords(question)

    # Determine classification method
    classification_method = "keyword"

    # If keyword confidence is high enough, use it
    if keyword_conf >= 0.75 or not use_llm:
        return ClassificationResult(
            vector_id=vector_id,
            question_text=question,
            question_type=keyword_type,
            confidence=keyword_conf,
            classification_method=classification_method,
            reasoning=f"Keyword-based classification. Detected: {', '.join(keywords)}",
            detected_keywords=keywords,
        )

    # Try LLM classification for better accuracy
    llm_type, llm_conf, llm_reasoning = classify_with_llm(question, vector_id, llm_client)

    if llm_conf > 0:
        # If LLM and keyword agree, boost confidence
        if llm_type == keyword_type and keyword_conf > 0.3:
            final_conf = min((llm_conf + keyword_conf) / 1.5, 0.98)
            classification_method = "hybrid"
            return ClassificationResult(
                vector_id=vector_id,
                question_text=question,
                question_type=llm_type,
                confidence=final_conf,
                classification_method=classification_method,
                reasoning=f"LLM+Keyword agreement: {llm_reasoning}",
                detected_keywords=keywords,
            )

        # Use LLM if confident
        if llm_conf >= 0.6:
            classification_method = "llm"
            return ClassificationResult(
                vector_id=vector_id,
                question_text=question,
                question_type=llm_type,
                confidence=llm_conf,
                classification_method=classification_method,
                secondary_types=[keyword_type] if keyword_type != llm_type and keyword_conf > 0.3 else [],
                reasoning=llm_reasoning,
                detected_keywords=keywords,
            )

    # Fall back to keyword classification
    if keyword_conf > 0:
        return ClassificationResult(
            vector_id=vector_id,
            question_text=question,
            question_type=keyword_type,
            confidence=keyword_conf,
            classification_method=classification_method,
            reasoning=f"Keyword-based (LLM unavailable/low confidence). Detected: {', '.join(keywords)}",
            detected_keywords=keywords,
        )

    # Ultimate fallback
    return ClassificationResult(
        vector_id=vector_id,
        question_text=question,
        question_type=QuestionType.UNKNOWN,
        confidence=0.0,
        classification_method="none",
        reasoning="Could not classify question type",
        detected_keywords=[],
    )


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("QUESTION CLASSIFIER SELF-TEST")
    print("=" * 60)

    # Test cases
    test_cases = [
        ("What is the contamination rate of E. coli in drinking water?", QuestionType.QUANTITATIVE_RESEARCH),
        ("What is the market size for water filters in North America?", QuestionType.MARKET_ANALYSIS),
        ("What EPA regulations apply to household water filters?", QuestionType.REGULATORY_COMPLIANCE),
        ("Compare reverse osmosis vs activated carbon filters", QuestionType.PRODUCT_COMPARISON),
        ("What do consumers think about water filter effectiveness?", QuestionType.QUALITATIVE_RESEARCH),
        ("How does reverse osmosis filtration work?", QuestionType.TECHNICAL_SPECIFICATION),
    ]

    passed = 0
    for question, expected_type in test_cases:
        result = classify_question(
            question=question,
            vector_id="TEST",
            use_llm=False,  # Keyword-only for deterministic testing
        )
        # Handle both enum and string (model_config with use_enum_values=True)
        result_type_str = result.question_type if isinstance(result.question_type, str) else result.question_type.value
        expected_type_str = expected_type.value
        status = "PASS" if result_type_str == expected_type_str else "FAIL"
        if status == "PASS":
            passed += 1
        print(f"\n[{status}] {expected_type_str}")
        print(f"  Q: {question[:60]}...")
        print(f"  Got: {result_type_str} (conf={result.confidence:.2f})")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(test_cases)} tests passed")
    print("=" * 60)

    if passed < len(test_cases):
        sys.exit(1)
