#!/usr/bin/env python3
"""
POLARIS Phase 0: Question Type Classification
==============================================
Sprint 2: SOTA Architecture - Dynamic Classification

Classifies research vectors into question types to load appropriate
processing profiles. Uses LLM-based classification with keyword detection
as fallback.

Usage:
    python -m src.phases.p00_classification --vector-id S1V1_Example

Input: Vector from work queue (question text)
Output: outputs/P0/{vector_id}__P0__{timestamp}.json

Reference: SymRAG, RAGRouter, DSPy Signatures
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.question_types import (
    QuestionType,
    QuestionTypeProfile,
    ClassificationResult,
    get_profile,
    DEFAULT_PROFILES,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
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


def run_phase(
    vector_id: str,
    question: str,
    use_llm: bool = True,
    llm_client: Optional[object] = None,
) -> ClassificationResult:
    """
    Run Phase 0: Question Type Classification.

    Args:
        vector_id: Vector ID
        question: Research question text
        use_llm: Whether to use LLM classification
        llm_client: Optional pre-initialized LLM client

    Returns:
        ClassificationResult with classification details
    """
    logger.info(f"[P0] Classifying vector: {vector_id}")

    # First, try keyword classification (fast, always available)
    keyword_type, keyword_conf, keywords = classify_by_keywords(question)
    logger.info(f"[P0] Keyword classification: {keyword_type.value} (conf={keyword_conf:.2f})")

    # If keyword confidence is high enough, use it
    if keyword_conf >= 0.75:
        return ClassificationResult(
            vector_id=vector_id,
            question_text=question,
            primary_type=keyword_type,
            confidence=keyword_conf,
            reasoning=f"Keyword-based classification. Detected: {', '.join(keywords)}",
            detected_keywords=keywords,
        )

    # Try LLM classification for better accuracy
    if use_llm:
        llm_type, llm_conf, llm_reasoning = classify_with_llm(question, vector_id, llm_client)

        if llm_conf > 0:
            logger.info(f"[P0] LLM classification: {llm_type.value} (conf={llm_conf:.2f})")

            # If LLM and keyword agree, boost confidence
            if llm_type == keyword_type and keyword_conf > 0.3:
                final_conf = min((llm_conf + keyword_conf) / 1.5, 0.98)
                return ClassificationResult(
                    vector_id=vector_id,
                    question_text=question,
                    primary_type=llm_type,
                    confidence=final_conf,
                    reasoning=f"LLM+Keyword agreement: {llm_reasoning}",
                    detected_keywords=keywords,
                )

            # Use LLM if confident
            if llm_conf >= 0.6:
                return ClassificationResult(
                    vector_id=vector_id,
                    question_text=question,
                    primary_type=llm_type,
                    confidence=llm_conf,
                    secondary_types=[keyword_type] if keyword_type != llm_type and keyword_conf > 0.3 else [],
                    reasoning=llm_reasoning,
                    detected_keywords=keywords,
                )

    # Fall back to keyword classification
    if keyword_conf > 0:
        return ClassificationResult(
            vector_id=vector_id,
            question_text=question,
            primary_type=keyword_type,
            confidence=keyword_conf,
            reasoning=f"Keyword-based (LLM unavailable/low confidence). Detected: {', '.join(keywords)}",
            detected_keywords=keywords,
        )

    # Ultimate fallback
    return ClassificationResult(
        vector_id=vector_id,
        question_text=question,
        primary_type=QuestionType.UNKNOWN,
        confidence=0.0,
        reasoning="Could not classify question type",
        detected_keywords=[],
    )


def save_output(result: ClassificationResult, output_dir: Path) -> Path:
    """Save classification result to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{result.vector_id}__P0__{timestamp}.json"
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)

    logger.info(f"[P0] Saved output: {output_path}")
    return output_path


def load_vector_question(vector_id: str) -> str:
    """Load the research question for a vector from work queue."""
    work_queue_path = PROJECT_ROOT / "state" / "work_queue.json"

    if not work_queue_path.exists():
        raise FileNotFoundError(f"Work queue not found: {work_queue_path}")

    with open(work_queue_path, "r", encoding="utf-8") as f:
        work_queue = json.load(f)

    for vector in work_queue.get("vectors", []):
        if vector.get("vector_id") == vector_id:
            return vector.get("question", vector.get("research_question", ""))

    raise ValueError(f"Vector not found in work queue: {vector_id}")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="POLARIS Phase 0: Question Type Classification")
    parser.add_argument("--vector-id", required=True, help="Vector ID to classify")
    parser.add_argument("--question", help="Question text (optional, loads from work queue if not provided)")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM classification")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "P0"), help="Output directory")
    args = parser.parse_args()

    # Get question
    if args.question:
        question = args.question
    else:
        question = load_vector_question(args.vector_id)

    if not question:
        logger.error(f"No question found for vector: {args.vector_id}")
        sys.exit(1)

    # Run classification
    result = run_phase(
        vector_id=args.vector_id,
        question=question,
        use_llm=not args.no_llm,
    )

    # Save output
    output_path = save_output(result, Path(args.output_dir))

    # Print summary
    print(f"\n{'='*60}")
    print(f"PHASE 0: CLASSIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"Vector: {result.vector_id}")
    print(f"Question: {result.question_text[:80]}...")
    print(f"Type: {result.primary_type}")
    print(f"Confidence: {result.confidence:.2%}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Keywords: {', '.join(result.detected_keywords)}")
    print(f"Output: {output_path}")
    print(f"{'='*60}")


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    # Check if running as CLI or self-test
    if len(sys.argv) > 1 and sys.argv[1] != "--self-test":
        main()
    else:
        print("=" * 60)
        print("P00 CLASSIFICATION SELF-TEST")
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
            result = run_phase(
                vector_id="TEST",
                question=question,
                use_llm=False,  # Keyword-only for deterministic testing
            )
            status = "PASS" if result.primary_type == expected_type else "FAIL"
            if status == "PASS":
                passed += 1
            print(f"\n[{status}] {expected_type.value}")
            print(f"  Q: {question[:60]}...")
            print(f"  Got: {result.primary_type} (conf={result.confidence:.2f})")

        print(f"\n{'='*60}")
        print(f"RESULTS: {passed}/{len(test_cases)} tests passed")
        print("=" * 60)

        if passed < len(test_cases):
            sys.exit(1)
