#!/usr/bin/env python3
"""
POLARIS Decomposed Query Schema
===============================
Sprint 5: SOTA Architecture - Query Decomposition

Breaks complex questions into data-seeking sub-queries.
Maps each sub-query to expected data types for targeted retrieval.

Reference: Question Decomposition for RAG
"""

import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.question_types import QuestionType, DataType


class QueryPriority(str, Enum):
    """Priority levels for sub-queries."""
    CRITICAL = "critical"   # Must answer for valid response
    HIGH = "high"           # Important for complete answer
    MEDIUM = "medium"       # Adds value but not required
    LOW = "low"             # Nice to have


class SubQuery(BaseModel):
    """A single sub-query decomposed from the main question."""
    query_text: str = Field(..., description="The sub-query text")
    expected_data_type: DataType = Field(..., description="Type of data expected")
    priority: QueryPriority = Field(QueryPriority.MEDIUM, description="Priority level")

    # Search hints
    search_keywords: List[str] = Field(default_factory=list, description="Keywords to include in search")
    search_modifiers: List[str] = Field(default_factory=list, description="Modifiers like 'study', 'data'")
    domain_hints: List[str] = Field(default_factory=list, description="Preferred domains")

    # Metadata
    is_factual: bool = Field(True, description="Whether this seeks factual data")
    requires_recent_data: bool = Field(False, description="Whether data must be recent")

    # STORM Perspective Tracking (FIX-124: Preserve perspective identity)
    # These fields enable true multi-perspective research by tracking which
    # expert perspective generated this query (Stanford STORM methodology)
    perspective_name: Optional[str] = Field(
        None,
        description="STORM perspective that generated this query (e.g., 'Public Health Expert')"
    )
    perspective_id: Optional[str] = Field(
        None,
        description="Unique ID for grouping queries from the same perspective"
    )
    bucket: str = Field(
        "general",
        description="Target search bucket (academic, government, industry, news, general)"
    )

    model_config = ConfigDict(use_enum_values=True)


class DecomposedQuery(BaseModel):
    """A complex question decomposed into sub-queries."""
    original_question: str = Field(..., description="The original question")
    question_type: QuestionType = Field(..., description="Classified question type")

    # Sub-queries
    sub_queries: List[SubQuery] = Field(..., description="Decomposed sub-queries")

    # Generated search queries
    search_queries: List[str] = Field(default_factory=list, description="Final search queries to execute")

    # Metadata
    decomposition_reasoning: str = Field("", description="Why question was decomposed this way")
    estimated_complexity: int = Field(1, ge=1, le=5, description="Complexity score 1-5")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# DECOMPOSITION LOGIC
# =============================================================================

def detect_question_complexity(question: str) -> int:
    """
    Estimate question complexity (1-5).

    Higher complexity means more sub-queries needed.
    """
    complexity = 1

    # Multiple question marks
    if question.count('?') > 1:
        complexity += 1

    # Conjunction words indicating multiple parts
    conjunctions = ['and', 'or', 'as well as', 'along with', 'in addition to']
    for conj in conjunctions:
        if f' {conj} ' in question.lower():
            complexity += 1
            break

    # Comparison indicators
    if any(word in question.lower() for word in ['compare', 'versus', 'vs', 'difference']):
        complexity += 1

    # Multiple data types needed
    data_indicators = {
        'rate': 1, 'percentage': 1, 'statistics': 1,
        'regulation': 1, 'law': 1, 'standard': 1,
        'market': 1, 'growth': 1, 'trend': 1,
    }
    found_types = sum(1 for ind in data_indicators if ind in question.lower())
    if found_types > 1:
        complexity += 1

    return min(complexity, 5)


def decompose_question(
    question: str,
    question_type: QuestionType,
    use_llm: bool = False,
    llm_client: Optional[object] = None,
) -> DecomposedQuery:
    """
    Decompose a complex question into sub-queries.

    Args:
        question: The original research question
        question_type: Classified question type
        use_llm: Whether to use LLM for decomposition
        llm_client: Optional LLM client

    Returns:
        DecomposedQuery with sub-queries
    """
    complexity = detect_question_complexity(question)
    sub_queries = []

    # Type-specific decomposition templates
    if question_type == QuestionType.QUANTITATIVE_RESEARCH:
        # Look for statistics, rates, studies
        sub_queries.extend([
            SubQuery(
                query_text=f"{question} statistics data",
                expected_data_type=DataType.STATISTIC,
                priority=QueryPriority.CRITICAL,
                search_keywords=['statistics', 'data', 'rate', 'prevalence'],
                search_modifiers=['study', 'research', 'survey'],
                domain_hints=['pmc.ncbi.nlm.nih.gov', 'cdc.gov', 'who.int'],
            ),
            SubQuery(
                query_text=f"{question} peer-reviewed study",
                expected_data_type=DataType.STATISTIC,
                priority=QueryPriority.HIGH,
                search_keywords=['peer-reviewed', 'research', 'findings'],
                search_modifiers=['systematic review', 'meta-analysis'],
                domain_hints=['pubmed.ncbi.nlm.nih.gov'],
            ),
        ])

    elif question_type == QuestionType.MARKET_ANALYSIS:
        sub_queries.extend([
            SubQuery(
                query_text=f"{question} market size",
                expected_data_type=DataType.TREND,
                priority=QueryPriority.CRITICAL,
                search_keywords=['market size', 'market value', 'revenue'],
                search_modifiers=['2024', '2025', 'forecast'],
            ),
            SubQuery(
                query_text=f"{question} growth rate CAGR",
                expected_data_type=DataType.TREND,
                priority=QueryPriority.HIGH,
                search_keywords=['growth', 'CAGR', 'forecast'],
                search_modifiers=['industry report', 'market analysis'],
            ),
        ])

    elif question_type == QuestionType.REGULATORY_COMPLIANCE:
        sub_queries.extend([
            SubQuery(
                query_text=f"{question} EPA FDA regulations",
                expected_data_type=DataType.REGULATION,
                priority=QueryPriority.CRITICAL,
                search_keywords=['regulation', 'standard', 'requirement'],
                domain_hints=['epa.gov', 'fda.gov', 'canada.ca'],
            ),
            SubQuery(
                query_text=f"{question} compliance requirements",
                expected_data_type=DataType.REGULATION,
                priority=QueryPriority.HIGH,
                search_keywords=['compliance', 'legal', 'mandatory'],
                search_modifiers=['official', 'government'],
            ),
        ])

    elif question_type == QuestionType.PRODUCT_COMPARISON:
        sub_queries.extend([
            SubQuery(
                query_text=f"{question} comparison review",
                expected_data_type=DataType.COMPARISON,
                priority=QueryPriority.CRITICAL,
                search_keywords=['comparison', 'review', 'vs'],
                search_modifiers=['head to head', 'benchmark'],
            ),
            SubQuery(
                query_text=f"{question} pros cons",
                expected_data_type=DataType.COMPARISON,
                priority=QueryPriority.HIGH,
                search_keywords=['advantages', 'disadvantages', 'pros', 'cons'],
            ),
        ])

    else:
        # Default decomposition
        sub_queries.append(SubQuery(
            query_text=question,
            expected_data_type=DataType.STATISTIC,
            priority=QueryPriority.CRITICAL,
            search_keywords=[],
        ))

    # Generate final search queries
    search_queries = []
    for sq in sub_queries:
        base_query = sq.query_text
        # Add modifiers
        for modifier in sq.search_modifiers[:2]:
            search_queries.append(f"{base_query} {modifier}")
        if not sq.search_modifiers:
            search_queries.append(base_query)

    return DecomposedQuery(
        original_question=question,
        question_type=question_type,
        sub_queries=sub_queries,
        search_queries=search_queries[:10],  # Limit to 10 queries
        decomposition_reasoning=f"Decomposed based on {question_type.value} type with complexity {complexity}",
        estimated_complexity=complexity,
    )


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("DECOMPOSED QUERY SELF-TEST")
    print("=" * 60)

    # Test 1: Complexity detection
    print("\n[TEST 1] Complexity detection...")
    q1 = "What is the contamination rate?"
    c1 = detect_question_complexity(q1)
    assert 1 <= c1 <= 5
    print(f"  [PASS] Simple question complexity: {c1}")

    q2 = "What is the contamination rate and what regulations apply? Also compare filter types."
    c2 = detect_question_complexity(q2)
    assert c2 > c1
    print(f"  [PASS] Complex question complexity: {c2}")

    # Test 2: Quantitative decomposition
    print("\n[TEST 2] Quantitative research decomposition...")
    result2 = decompose_question(
        "What is the E. coli contamination rate in private wells?",
        QuestionType.QUANTITATIVE_RESEARCH,
    )
    assert len(result2.sub_queries) >= 2
    assert len(result2.search_queries) > 0
    print(f"  [PASS] Generated {len(result2.sub_queries)} sub-queries, {len(result2.search_queries)} searches")

    # Test 3: Market decomposition
    print("\n[TEST 3] Market analysis decomposition...")
    result3 = decompose_question(
        "What is the market size for household water filters?",
        QuestionType.MARKET_ANALYSIS,
    )
    assert len(result3.sub_queries) >= 2
    print(f"  [PASS] Generated {len(result3.sub_queries)} sub-queries")

    # Test 4: Regulatory decomposition
    print("\n[TEST 4] Regulatory compliance decomposition...")
    result4 = decompose_question(
        "What EPA regulations apply to water filters?",
        QuestionType.REGULATORY_COMPLIANCE,
    )
    assert any('epa.gov' in sq.domain_hints for sq in result4.sub_queries)
    print(f"  [PASS] Domain hints include EPA")

    # Test 5: Serialization
    print("\n[TEST 5] Serialization...")
    data = result2.model_dump()
    assert 'sub_queries' in data
    assert 'search_queries' in data
    print(f"  [PASS] Serialized to {len(data)} fields")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
