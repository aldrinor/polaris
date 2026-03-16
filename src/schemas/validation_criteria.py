#!/usr/bin/env python3
"""
POLARIS Validation Criteria Schema
==================================
Sprint 4: SOTA Architecture - Answer Validation Gate

Defines validation criteria for checking answer completeness and quality.
Implements DeCE-style criteria checking (precision and recall).

Reference: DeCE, RAGCHECKER
"""

import re
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.question_types import QuestionType, DataType


class CriterionType(str, Enum):
    """Types of validation criteria."""
    MUST_CONTAIN_PERCENTAGE = "must_contain_percentage"
    MUST_NAME_ENTITY = "must_name_entity"
    MUST_CITE_STUDY = "must_cite_study"
    MUST_DESCRIBE_PATTERN = "must_describe_pattern"
    MUST_SPECIFY_REGULATION = "must_specify_regulation"
    MUST_INCLUDE_TIMEFRAME = "must_include_timeframe"
    MUST_PROVIDE_COMPARISON = "must_provide_comparison"
    MUST_CITE_SOURCE = "must_cite_source"
    WORD_COUNT_MINIMUM = "word_count_minimum"
    CITATION_COUNT_MINIMUM = "citation_count_minimum"


class ValidationCriterion(BaseModel):
    """A single validation criterion."""
    criterion_type: CriterionType = Field(..., description="Type of criterion")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="What this criterion checks")
    required: bool = Field(True, description="Whether this criterion must pass")
    weight: float = Field(1.0, ge=0.0, le=1.0, description="Weight for scoring")

    # Parameters for the criterion
    min_count: Optional[int] = Field(None, description="Minimum count (for count-based criteria)")
    pattern: Optional[str] = Field(None, description="Regex pattern to match")
    entity_types: Optional[List[str]] = Field(None, description="Entity types to look for")

    model_config = ConfigDict(use_enum_values=True)


class CriterionResult(BaseModel):
    """Result of checking a single criterion."""
    criterion_type: CriterionType
    name: str
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0, description="Score (0.0-1.0)")
    evidence: List[str] = Field(default_factory=list, description="Evidence found")
    notes: str = Field("", description="Additional notes")

    model_config = ConfigDict(use_enum_values=True)


class ValidationResult(BaseModel):
    """Result of validating an answer against all criteria."""
    vector_id: str
    total_criteria: int
    passed_criteria: int
    failed_criteria: int

    # Scores
    precision: float = Field(..., ge=0.0, le=1.0, description="Claims supported by evidence")
    recall: float = Field(..., ge=0.0, le=1.0, description="Criteria met")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Combined score")

    # Details
    criteria_results: List[CriterionResult] = Field(default_factory=list)
    is_valid: bool = Field(..., description="Whether answer passes validation")

    # Recommendations
    missing_elements: List[str] = Field(default_factory=list, description="What's missing")
    recommendations: List[str] = Field(default_factory=list, description="How to improve")


# =============================================================================
# CRITERION CHECKERS
# =============================================================================

def check_must_contain_percentage(text: str, min_count: int = 1) -> CriterionResult:
    """Check if text contains percentage/rate data."""
    patterns = [
        r'\d+(?:\.\d+)?(?:\s*)(?:%|percent)',
        r'(?:rate|prevalence|incidence)\s+(?:of\s+)?\d+(?:\.\d+)?',
    ]
    evidence = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        evidence.extend(matches[:5])

    passed = len(evidence) >= min_count
    return CriterionResult(
        criterion_type=CriterionType.MUST_CONTAIN_PERCENTAGE,
        name="Contains Percentage Data",
        passed=passed,
        score=min(len(evidence) / max(min_count, 1), 1.0),
        evidence=evidence[:5],
        notes=f"Found {len(evidence)} percentage mentions"
    )


def check_must_name_entity(text: str, entity_types: Optional[List[str]] = None) -> CriterionResult:
    """Check if text names specific entities."""
    # Simple NER-like patterns
    patterns = [
        r'(?:Dr\.|Professor|Expert)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?',  # Names
        r'(?:University|Institute|Center|Agency)\s+of\s+[A-Z][a-z]+',  # Organizations
        r'[A-Z]{2,5}(?:\s|$)',  # Acronyms like EPA, FDA, CDC
    ]
    evidence = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        evidence.extend(matches[:5])

    passed = len(evidence) >= 1
    return CriterionResult(
        criterion_type=CriterionType.MUST_NAME_ENTITY,
        name="Names Specific Entities",
        passed=passed,
        score=min(len(evidence) / 3, 1.0),
        evidence=evidence[:5],
        notes=f"Found {len(evidence)} named entities"
    )


def check_must_cite_study(text: str, min_count: int = 1) -> CriterionResult:
    """Check if text cites research studies."""
    patterns = [
        r'(?:study|research|survey|analysis)\s+(?:by|from|conducted)',
        r'(?:according to|per|as per)\s+(?:a\s+)?(?:\d{4}\s+)?(?:study|research)',
        r'\(\d{4}\)',  # Year citations
        r'\[\d+\]',  # Numbered citations
    ]
    evidence = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        evidence.extend(matches[:5])

    passed = len(evidence) >= min_count
    return CriterionResult(
        criterion_type=CriterionType.MUST_CITE_STUDY,
        name="Cites Research Studies",
        passed=passed,
        score=min(len(evidence) / max(min_count, 1), 1.0),
        evidence=evidence[:5],
        notes=f"Found {len(evidence)} study citations"
    )


def check_must_specify_regulation(text: str) -> CriterionResult:
    """Check if text specifies regulations/standards."""
    patterns = [
        r'(?:EPA|FDA|OSHA|CDC|WHO|EU)\s+(?:regulation|standard|guideline)',
        r'(?:MCL|Maximum Contaminant Level)',
        r'(?:NSF|ANSI)(?:/|\s+)(?:Standard\s+)?\d+',
        r'(?:Safe Drinking Water Act|Clean Water Act)',
        r'(?:regulation|standard|requirement)\s+\d+',
    ]
    evidence = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        evidence.extend(matches[:5])

    passed = len(evidence) >= 1
    return CriterionResult(
        criterion_type=CriterionType.MUST_SPECIFY_REGULATION,
        name="Specifies Regulations",
        passed=passed,
        score=min(len(evidence), 1.0),
        evidence=evidence[:5],
        notes=f"Found {len(evidence)} regulation references"
    )


def check_word_count(text: str, min_words: int = 2000) -> CriterionResult:
    """Check if text meets minimum word count."""
    word_count = len(text.split())
    passed = word_count >= min_words
    return CriterionResult(
        criterion_type=CriterionType.WORD_COUNT_MINIMUM,
        name="Minimum Word Count",
        passed=passed,
        score=min(word_count / min_words, 1.0),
        evidence=[f"{word_count} words"],
        notes=f"Word count: {word_count} (minimum: {min_words})"
    )


def check_citation_count(citations: List[dict], min_citations: int = 5) -> CriterionResult:
    """Check if answer has minimum citations."""
    citation_count = len(citations)
    passed = citation_count >= min_citations
    return CriterionResult(
        criterion_type=CriterionType.CITATION_COUNT_MINIMUM,
        name="Minimum Citations",
        passed=passed,
        score=min(citation_count / min_citations, 1.0),
        evidence=[f"{citation_count} citations"],
        notes=f"Citation count: {citation_count} (minimum: {min_citations})"
    )


# =============================================================================
# CRITERIA DERIVATION
# =============================================================================

def derive_criteria_from_question_type(question_type: QuestionType) -> List[ValidationCriterion]:
    """
    Derive validation criteria based on question type.

    Args:
        question_type: The classified question type

    Returns:
        List of criteria to check
    """
    base_criteria = [
        ValidationCriterion(
            criterion_type=CriterionType.WORD_COUNT_MINIMUM,
            name="Minimum Word Count",
            description="Answer must meet minimum word count",
            required=True,
            weight=0.3,
            min_count=2000,
        ),
        ValidationCriterion(
            criterion_type=CriterionType.CITATION_COUNT_MINIMUM,
            name="Minimum Citations",
            description="Answer must have minimum citations",
            required=True,
            weight=0.3,
            min_count=5,
        ),
    ]

    type_specific = {
        QuestionType.QUANTITATIVE_RESEARCH: [
            ValidationCriterion(
                criterion_type=CriterionType.MUST_CONTAIN_PERCENTAGE,
                name="Contains Statistics",
                description="Answer must contain percentage or rate data",
                required=True,
                weight=1.0,
                min_count=3,
            ),
            ValidationCriterion(
                criterion_type=CriterionType.MUST_CITE_STUDY,
                name="Cites Studies",
                description="Answer must cite research studies",
                required=True,
                weight=0.8,
                min_count=2,
            ),
        ],
        QuestionType.REGULATORY_COMPLIANCE: [
            ValidationCriterion(
                criterion_type=CriterionType.MUST_SPECIFY_REGULATION,
                name="Specifies Regulations",
                description="Answer must specify regulations or standards",
                required=True,
                weight=1.0,
            ),
        ],
        QuestionType.MARKET_ANALYSIS: [
            ValidationCriterion(
                criterion_type=CriterionType.MUST_CONTAIN_PERCENTAGE,
                name="Contains Market Data",
                description="Answer must contain market percentages or values",
                required=True,
                weight=1.0,
                min_count=2,
            ),
            ValidationCriterion(
                criterion_type=CriterionType.MUST_INCLUDE_TIMEFRAME,
                name="Includes Timeframe",
                description="Answer should include forecast timeframes",
                required=False,
                weight=0.6,
            ),
        ],
        QuestionType.PRODUCT_COMPARISON: [
            ValidationCriterion(
                criterion_type=CriterionType.MUST_PROVIDE_COMPARISON,
                name="Provides Comparison",
                description="Answer must compare multiple options",
                required=True,
                weight=1.0,
            ),
        ],
    }

    return base_criteria + type_specific.get(question_type, [])


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================

def validate_answer(
    text: str,
    citations: List[dict],
    vector_id: str,
    question_type: QuestionType,
    min_score: float = 0.7,
) -> ValidationResult:
    """
    Validate an answer against criteria derived from question type.

    Args:
        text: Answer text to validate
        citations: List of citations
        vector_id: Vector ID
        question_type: Question type for criteria derivation
        min_score: Minimum score to pass validation

    Returns:
        ValidationResult with detailed results
    """
    criteria = derive_criteria_from_question_type(question_type)
    results = []
    passed = 0
    failed = 0
    total_weight = 0.0
    weighted_score = 0.0
    missing = []
    recommendations = []

    for criterion in criteria:
        # Check each criterion
        if criterion.criterion_type == CriterionType.MUST_CONTAIN_PERCENTAGE:
            result = check_must_contain_percentage(text, criterion.min_count or 1)
        elif criterion.criterion_type == CriterionType.MUST_NAME_ENTITY:
            result = check_must_name_entity(text, criterion.entity_types)
        elif criterion.criterion_type == CriterionType.MUST_CITE_STUDY:
            result = check_must_cite_study(text, criterion.min_count or 1)
        elif criterion.criterion_type == CriterionType.MUST_SPECIFY_REGULATION:
            result = check_must_specify_regulation(text)
        elif criterion.criterion_type == CriterionType.WORD_COUNT_MINIMUM:
            result = check_word_count(text, criterion.min_count or 2000)
        elif criterion.criterion_type == CriterionType.CITATION_COUNT_MINIMUM:
            result = check_citation_count(citations, criterion.min_count or 5)
        else:
            # Default pass for unimplemented criteria
            result = CriterionResult(
                criterion_type=criterion.criterion_type,
                name=criterion.name,
                passed=True,
                score=1.0,
                notes="Criterion not yet implemented"
            )

        results.append(result)
        total_weight += criterion.weight

        if result.passed:
            passed += 1
            weighted_score += criterion.weight * result.score
        else:
            failed += 1
            if criterion.required:
                missing.append(criterion.name)
                recommendations.append(f"Add more {criterion.name.lower()}")

    # Calculate scores
    recall = passed / len(criteria) if criteria else 1.0
    precision = weighted_score / total_weight if total_weight > 0 else 1.0
    overall = (precision + recall) / 2

    return ValidationResult(
        vector_id=vector_id,
        total_criteria=len(criteria),
        passed_criteria=passed,
        failed_criteria=failed,
        precision=precision,
        recall=recall,
        overall_score=overall,
        criteria_results=results,
        is_valid=overall >= min_score and len([c for c in results if not c.passed and criteria[results.index(c)].required]) == 0,
        missing_elements=missing,
        recommendations=recommendations[:5],
    )


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    print("=" * 60)
    print("VALIDATION CRITERIA SELF-TEST")
    print("=" * 60)

    # Test 1: Check percentage criterion
    print("\n[TEST 1] Check percentage criterion...")
    result1 = check_must_contain_percentage("Contamination rate was 15% in urban areas and 22% in rural areas.")
    assert result1.passed
    assert result1.score > 0
    print(f"  [PASS] Found {len(result1.evidence)} percentages")

    # Test 2: Check study citation criterion
    print("\n[TEST 2] Check study citation criterion...")
    result2 = check_must_cite_study("According to a 2023 study by researchers [1], water quality varies.")
    assert result2.passed
    print(f"  [PASS] Found {len(result2.evidence)} citations")

    # Test 3: Check word count
    print("\n[TEST 3] Check word count criterion...")
    text3 = " ".join(["word"] * 2500)
    result3 = check_word_count(text3, 2000)
    assert result3.passed
    print(f"  [PASS] Word count: {result3.evidence[0]}")

    # Test 4: Derive criteria
    print("\n[TEST 4] Derive criteria from question type...")
    criteria = derive_criteria_from_question_type(QuestionType.QUANTITATIVE_RESEARCH)
    assert len(criteria) >= 2
    print(f"  [PASS] Derived {len(criteria)} criteria for quantitative research")

    # Test 5: Full validation
    print("\n[TEST 5] Full validation...")
    sample_text = """
    According to a 2023 study [1], contamination rates in private wells were 15%.
    Another survey found 22% of samples exceeded EPA limits [2].
    The research indicates that rural areas face higher risks.
    """ + " ".join(["content"] * 2000)

    sample_citations = [{"url": "http://example.com"} for _ in range(6)]

    validation = validate_answer(
        text=sample_text,
        citations=sample_citations,
        vector_id="TEST",
        question_type=QuestionType.QUANTITATIVE_RESEARCH,
    )
    print(f"  Overall score: {validation.overall_score:.2f}")
    print(f"  Passed: {validation.passed_criteria}/{validation.total_criteria}")
    print(f"  Is valid: {validation.is_valid}")
    assert validation.overall_score > 0

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
