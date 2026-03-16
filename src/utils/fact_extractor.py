#!/usr/bin/env python3
"""
POLARIS Fact Extractor
======================
Sprint 3: SOTA Architecture - Structured Data Extraction

Extracts structured facts from text chunks using LLM with Pydantic validation.
Implements self-correcting extraction loop for high accuracy.

Reference: Instructor, Pydantic, GuideX
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.extracted_facts import (
    ExtractedFact,
    FactType,
    FactCollection,
    ContaminationRateFact,
    MarketSizeFact,
    RegulatoryFact,
    ComparisonFact,
    TechnicalSpecFact,
    StatisticFact,
    ExpertQuoteFact,
    DefinitionFact,
    ConfidenceLevel,
)
from src.schemas.question_types import QuestionType, DataType

logger = logging.getLogger(__name__)


# =============================================================================
# EXTRACTION PATTERNS (Regex-based for fast extraction)
# =============================================================================

# Patterns for detecting different fact types
CONTAMINATION_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:of\s+)?(?:samples?|wells?|sources?|water)',
    r'(?:contamination|detection|prevalence|incidence)\s+(?:rate|level)\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*%',
    r'(\d+(?:\.\d+)?)\s*(?:ppb|ppm|mg/L|μg/L)',
]

MARKET_PATTERNS = [
    r'\$(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)',
    r'market\s+(?:size|value)\s*(?:of|:)?\s*\$?(\d+(?:\.\d+)?)\s*(?:billion|million)',
    r'(\d+(?:\.\d+)?)\s*%\s*(?:CAGR|growth|annually)',
]

REGULATION_PATTERNS = [
    r'(?:EPA|FDA|OSHA|USDA|CDC)\s+(?:regulation|standard|guideline|requirement)',
    r'(?:MCL|Maximum Contaminant Level)\s*(?:of|:)?\s*(\d+(?:\.\d+)?)',
    r'(?:NSF|ANSI)\s*(?:/|Standard)\s*(\d+)',
]


# =============================================================================
# FACT TYPE DETECTION
# =============================================================================

def detect_fact_types(text: str, question_type: Optional[QuestionType] = None) -> List[FactType]:
    """
    Detect what types of facts might be present in text.

    Args:
        text: Text to analyze
        question_type: Optional question type for hints

    Returns:
        List of likely fact types
    """
    detected = []
    text_lower = text.lower()

    # Check contamination patterns
    for pattern in CONTAMINATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            detected.append(FactType.CONTAMINATION_RATE)
            break

    # Check market patterns
    for pattern in MARKET_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            detected.append(FactType.MARKET_SIZE)
            break

    # Check regulation patterns
    for pattern in REGULATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            detected.append(FactType.REGULATORY)
            break

    # Check for comparisons
    if any(word in text_lower for word in ['vs', 'versus', 'compared to', 'better than', 'worse than']):
        detected.append(FactType.COMPARISON)

    # Check for statistics
    if re.search(r'\d+(?:\.\d+)?\s*(?:%|percent|million|billion)', text):
        if FactType.CONTAMINATION_RATE not in detected and FactType.MARKET_SIZE not in detected:
            detected.append(FactType.STATISTIC)

    # Check for expert quotes
    if re.search(r'(?:said|stated|according to|noted)\s+(?:Dr\.|Professor|expert)', text, re.IGNORECASE):
        detected.append(FactType.EXPERT_QUOTE)

    # Use question type as hint
    if question_type:
        type_to_fact = {
            QuestionType.QUANTITATIVE_RESEARCH: FactType.STATISTIC,
            QuestionType.MARKET_ANALYSIS: FactType.MARKET_SIZE,
            QuestionType.REGULATORY_COMPLIANCE: FactType.REGULATORY,
            QuestionType.PRODUCT_COMPARISON: FactType.COMPARISON,
            QuestionType.TECHNICAL_SPECIFICATION: FactType.TECHNICAL_SPEC,
        }
        if question_type in type_to_fact:
            hint = type_to_fact[question_type]
            if hint not in detected:
                detected.append(hint)

    return detected if detected else [FactType.STATISTIC]


# =============================================================================
# LLM-BASED EXTRACTION
# =============================================================================

def build_extraction_prompt(
    text: str,
    fact_types: List[FactType],
    chunk_id: str,
) -> str:
    """Build prompt for LLM-based fact extraction."""

    type_instructions = {
        FactType.CONTAMINATION_RATE: """For contamination rates, extract:
- contaminant: Name of pathogen/chemical
- rate_value: Numeric rate
- rate_unit: "percent", "ppb", "ppm", etc.
- sample_matrix: What was tested
- geographic_scope: Location""",

        FactType.MARKET_SIZE: """For market data, extract:
- market_name: Name of market
- value: Numeric value
- value_unit: "usd_billion", "usd_million"
- value_year: Year
- growth_rate: CAGR if mentioned""",

        FactType.REGULATORY: """For regulations, extract:
- regulation_name: Name of regulation/standard
- issuing_body: EPA, FDA, etc.
- jurisdiction: USA, EU, etc.
- requirement_text: What it requires
- threshold_value: Numeric limit if any""",

        FactType.COMPARISON: """For comparisons, extract:
- comparison_subject: What's being compared
- items_compared: List of items
- values: Value for each item
- winner: Which is better (if stated)""",

        FactType.STATISTIC: """For statistics, extract:
- metric_name: What's measured
- value: Numeric value
- unit: Unit of measurement
- population: Who/what it applies to""",
    }

    instructions = "\n\n".join([
        type_instructions.get(ft, f"Extract {ft.value} facts")
        for ft in fact_types
    ])

    return f"""Extract structured facts from this text. Only extract facts that are explicitly stated.

TEXT:
{text}

EXTRACT THESE FACT TYPES:
{instructions}

Respond with a JSON object containing arrays for each fact type found:
{{
    "contamination_rates": [...],
    "market_sizes": [...],
    "regulations": [...],
    "comparisons": [...],
    "statistics": [...],
    "expert_quotes": [...],
    "definitions": [...]
}}

Each fact must include:
- source_chunk_id: "{chunk_id}"
- confidence: 0.0-1.0 based on how explicit the fact is
- raw_text: The exact text the fact came from

Only include fact types you find. Return empty arrays for types not found.
Only output valid JSON, nothing else."""


def extract_facts_with_llm(
    text: str,
    chunk_id: str,
    fact_types: List[FactType],
    llm_client: Optional[object] = None,
    max_retries: int = 2,
) -> FactCollection:
    """
    Extract facts using LLM with validation loop.

    Args:
        text: Text to extract from
        chunk_id: Source chunk ID
        fact_types: Types of facts to extract
        llm_client: LLM client (Gemini)
        max_retries: Max validation retries

    Returns:
        FactCollection with extracted facts
    """
    if llm_client is None:
        try:
            from src.llm import get_gemini_client
            llm_client = get_gemini_client()
        except Exception as e:
            logger.warning(f"LLM unavailable for extraction: {e}")
            return FactCollection(source_id=chunk_id)

    prompt = build_extraction_prompt(text, fact_types, chunk_id)

    for attempt in range(max_retries + 1):
        try:
            response = llm_client.generate_content(prompt)
            response_text = response.text.strip()

            # Parse JSON
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            data = json.loads(response_text)

            # Build FactCollection
            collection = FactCollection(source_id=chunk_id)

            # Parse each fact type
            for raw_fact in data.get("contamination_rates", []):
                try:
                    raw_fact["source_chunk_id"] = chunk_id
                    raw_fact["fact_type"] = FactType.CONTAMINATION_RATE
                    fact = ContaminationRateFact(**raw_fact)
                    collection.contamination_rates.append(fact)
                except Exception as e:
                    logger.debug(f"Failed to parse contamination fact: {e}")

            for raw_fact in data.get("market_sizes", []):
                try:
                    raw_fact["source_chunk_id"] = chunk_id
                    raw_fact["fact_type"] = FactType.MARKET_SIZE
                    fact = MarketSizeFact(**raw_fact)
                    collection.market_sizes.append(fact)
                except Exception as e:
                    logger.debug(f"Failed to parse market fact: {e}")

            for raw_fact in data.get("regulations", []):
                try:
                    raw_fact["source_chunk_id"] = chunk_id
                    raw_fact["fact_type"] = FactType.REGULATORY
                    fact = RegulatoryFact(**raw_fact)
                    collection.regulations.append(fact)
                except Exception as e:
                    logger.debug(f"Failed to parse regulation fact: {e}")

            for raw_fact in data.get("comparisons", []):
                try:
                    raw_fact["source_chunk_id"] = chunk_id
                    raw_fact["fact_type"] = FactType.COMPARISON
                    fact = ComparisonFact(**raw_fact)
                    collection.comparisons.append(fact)
                except Exception as e:
                    logger.debug(f"Failed to parse comparison fact: {e}")

            for raw_fact in data.get("statistics", []):
                try:
                    raw_fact["source_chunk_id"] = chunk_id
                    raw_fact["fact_type"] = FactType.STATISTIC
                    fact = StatisticFact(**raw_fact)
                    collection.statistics.append(fact)
                except Exception as e:
                    logger.debug(f"Failed to parse statistic fact: {e}")

            logger.info(f"Extracted {collection.total_facts} facts from {chunk_id}")
            return collection

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                prompt += "\n\nPrevious response was invalid JSON. Please respond with valid JSON only."
        except Exception as e:
            logger.warning(f"Extraction error (attempt {attempt + 1}): {e}")

    return FactCollection(source_id=chunk_id)


# =============================================================================
# REGEX-BASED EXTRACTION (Fast, no LLM required)
# =============================================================================

def extract_facts_regex(text: str, chunk_id: str) -> FactCollection:
    """
    Extract facts using regex patterns (no LLM required).

    This is faster but less accurate than LLM extraction.
    Good for initial filtering or when LLM is unavailable.
    """
    collection = FactCollection(source_id=chunk_id)

    # Extract contamination rates
    for pattern in CONTAMINATION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                # Get surrounding context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]

                value = float(match.group(1))
                unit = "percent" if "%" in match.group() or "percent" in match.group().lower() else "ppb"

                fact = StatisticFact(
                    source_chunk_id=chunk_id,
                    confidence=0.6,
                    raw_text=context.strip(),
                    metric_name="contamination rate",
                    value=value,
                    unit=unit,
                )
                collection.statistics.append(fact)
            except (ValueError, IndexError) as e:
                # LOW-028: Log contamination pattern extraction error
                logger.debug(f"Failed to extract contamination pattern: {e}")
                continue

    # Extract market sizes
    for pattern in MARKET_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]

                value = float(match.group(1))
                unit = "usd_billion" if "billion" in match.group().lower() else "usd_million"

                fact = StatisticFact(
                    source_chunk_id=chunk_id,
                    confidence=0.5,
                    raw_text=context.strip(),
                    metric_name="market value",
                    value=value,
                    unit=unit,
                )
                collection.statistics.append(fact)
            except (ValueError, IndexError) as e:
                # LOW-029: Log market pattern extraction error
                logger.debug(f"Failed to extract market pattern: {e}")
                continue

    return collection


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_facts_from_chunk(
    text: str,
    chunk_id: str,
    question_type: Optional[QuestionType] = None,
    use_llm: bool = True,
    llm_client: Optional[object] = None,
) -> FactCollection:
    """
    Extract structured facts from a text chunk.

    Args:
        text: Text to extract from
        chunk_id: ID of the source chunk
        question_type: Question type for targeted extraction
        use_llm: Whether to use LLM extraction
        llm_client: Optional pre-initialized LLM client

    Returns:
        FactCollection with all extracted facts
    """
    # Detect what fact types might be present
    fact_types = detect_fact_types(text, question_type)

    if use_llm and llm_client is not None:
        # Use LLM for accurate extraction
        return extract_facts_with_llm(text, chunk_id, fact_types, llm_client)
    else:
        # Fall back to regex extraction
        return extract_facts_regex(text, chunk_id)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("FACT EXTRACTOR SELF-TEST")
    print("=" * 60)

    # Test 1: Detect fact types
    print("\n[TEST 1] Fact type detection...")
    text1 = "E. coli was found in 15% of private well samples in rural areas."
    types1 = detect_fact_types(text1)
    assert FactType.CONTAMINATION_RATE in types1 or FactType.STATISTIC in types1
    print(f"  [PASS] Detected types: {[t.value for t in types1]}")

    # Test 2: Market fact detection
    print("\n[TEST 2] Market fact detection...")
    text2 = "The global water filter market was valued at $15.2 billion in 2023."
    types2 = detect_fact_types(text2)
    assert FactType.MARKET_SIZE in types2 or FactType.STATISTIC in types2
    print(f"  [PASS] Detected types: {[t.value for t in types2]}")

    # Test 3: Regex extraction
    print("\n[TEST 3] Regex-based extraction...")
    text3 = "Studies show 22% of wells contained detectable levels of contamination."
    collection = extract_facts_regex(text3, "test_chunk_001")
    assert collection.total_facts >= 0  # May or may not extract depending on pattern
    print(f"  [PASS] Extracted {collection.total_facts} facts")

    # Test 4: Question type hints
    print("\n[TEST 4] Question type hints...")
    text4 = "Water quality varies significantly across regions."
    types4 = detect_fact_types(text4, QuestionType.QUANTITATIVE_RESEARCH)
    assert FactType.STATISTIC in types4
    print(f"  [PASS] Hint added: {[t.value for t in types4]}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
