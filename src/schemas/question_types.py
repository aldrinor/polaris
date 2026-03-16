#!/usr/bin/env python3
"""
POLARIS Question Type Classification Schema
============================================
Sprint 2: SOTA Architecture - Dynamic Classification

Defines question types and their associated processing profiles.
Each question type has specific:
- Source priorities (academic vs news vs government)
- Required data types (statistics, regulations, comparisons)
- Validation criteria (what the answer must contain)
- Domain boosts (score adjustments for relevant domains)

Reference: SymRAG, RAGRouter, DSPy Signatures
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class QuestionType(str, Enum):
    """
    Core question types for research vectors.

    Each type has different information needs and source requirements.
    """
    # Quantitative research - needs statistics, rates, measurements
    QUANTITATIVE_RESEARCH = "quantitative_research"

    # Market analysis - needs market size, trends, competitive data
    MARKET_ANALYSIS = "market_analysis"

    # Regulatory compliance - needs laws, standards, requirements
    REGULATORY_COMPLIANCE = "regulatory_compliance"

    # Product comparison - needs feature comparisons, benchmarks
    PRODUCT_COMPARISON = "product_comparison"

    # Qualitative research - needs expert opinions, case studies
    QUALITATIVE_RESEARCH = "qualitative_research"

    # Technical specification - needs technical details, specs
    TECHNICAL_SPECIFICATION = "technical_specification"

    # Unknown/fallback - use default processing
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    """Types of information sources."""
    ACADEMIC = "academic"           # PubMed, journals, research papers
    GOVERNMENT = "government"       # CDC, EPA, FDA, Health Canada
    NEWS = "news"                   # News outlets, press releases
    INDUSTRY = "industry"           # Industry reports, white papers
    GENERAL_WEB = "general_web"     # General websites
    EDUCATIONAL = "educational"     # .edu domains, universities


class DataType(str, Enum):
    """Types of data that can be extracted."""
    STATISTIC = "statistic"         # Numbers, rates, percentages
    REGULATION = "regulation"       # Laws, standards, requirements
    COMPARISON = "comparison"       # Feature/product comparisons
    TREND = "trend"                 # Market/industry trends
    EXPERT_OPINION = "expert_opinion"  # Expert quotes, analysis
    CASE_STUDY = "case_study"       # Real-world examples
    TECHNICAL_SPEC = "technical_spec"  # Technical specifications
    DEFINITION = "definition"       # Definitions, explanations


class DomainBoost(BaseModel):
    """Score adjustment for a specific domain pattern."""
    pattern: str = Field(..., description="Domain pattern (e.g., 'cdc.gov', '*.edu')")
    boost: float = Field(..., description="Score adjustment (-1.0 to +1.0)")
    reason: str = Field("", description="Why this domain is boosted/penalized")


class ValidationCriterion(BaseModel):
    """A criterion that the answer must satisfy."""
    name: str = Field(..., description="Criterion name")
    description: str = Field(..., description="What this criterion checks")
    required: bool = Field(True, description="Whether this criterion is required")
    weight: float = Field(1.0, description="Weight for scoring (0.0-1.0)")


class QuestionTypeProfile(BaseModel):
    """
    Processing profile for a question type.

    Defines how the pipeline should handle questions of this type:
    - What sources to prioritize
    - What data types to extract
    - What validation criteria to apply
    - Domain-specific score adjustments
    """
    question_type: QuestionType = Field(..., description="The question type")
    description: str = Field(..., description="Human-readable description")

    # Source configuration
    source_priorities: List[SourceType] = Field(
        default_factory=lambda: [SourceType.ACADEMIC, SourceType.GOVERNMENT],
        description="Sources in priority order"
    )

    # Data extraction configuration
    required_data_types: List[DataType] = Field(
        default_factory=list,
        description="Data types that must be extracted"
    )
    optional_data_types: List[DataType] = Field(
        default_factory=list,
        description="Data types that are helpful but not required"
    )

    # Validation configuration
    validation_criteria: List[ValidationCriterion] = Field(
        default_factory=list,
        description="Criteria the answer must satisfy"
    )
    min_validation_score: float = Field(
        0.7,
        description="Minimum validation score to pass (0.0-1.0)"
    )

    # Domain scoring
    domain_boosts: List[DomainBoost] = Field(
        default_factory=list,
        description="Domain-specific score adjustments"
    )

    # Query generation hints
    query_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords to add to queries for better results"
    )
    query_modifiers: List[str] = Field(
        default_factory=list,
        description="Modifiers like 'study', 'data', 'statistics'"
    )

    # Output configuration
    min_word_count: int = Field(2000, description="Minimum report word count")
    min_citations: int = Field(5, description="Minimum citation count")
    preferred_citation_types: List[SourceType] = Field(
        default_factory=lambda: [SourceType.ACADEMIC],
        description="Preferred source types for citations"
    )

    model_config = ConfigDict(use_enum_values=True)


class ClassificationResult(BaseModel):
    """Result of question type classification."""
    vector_id: str = Field(..., description="Vector ID that was classified")
    question_text: str = Field(..., description="The research question")

    # Classification result
    question_type: QuestionType = Field(..., description="Primary question type")
    confidence: float = Field(..., description="Classification confidence (0.0-1.0)")
    classification_method: str = Field("keyword", description="Method used: keyword | llm | hybrid")

    # Secondary types (if question spans multiple types)
    secondary_types: List[QuestionType] = Field(
        default_factory=list,
        description="Secondary question types"
    )

    # Reasoning
    reasoning: str = Field("", description="Why this classification was chosen")

    # Keywords detected
    detected_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords that influenced classification"
    )

    # Profile to use
    profile_path: Optional[str] = Field(
        None,
        description="Path to the profile YAML to use"
    )

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# DEFAULT PROFILES (used when YAML not available)
# =============================================================================

DEFAULT_PROFILES: Dict[QuestionType, QuestionTypeProfile] = {
    QuestionType.QUANTITATIVE_RESEARCH: QuestionTypeProfile(
        question_type=QuestionType.QUANTITATIVE_RESEARCH,
        description="Questions requiring statistics, rates, measurements, and numerical data",
        source_priorities=[SourceType.ACADEMIC, SourceType.GOVERNMENT, SourceType.EDUCATIONAL],
        required_data_types=[DataType.STATISTIC],
        optional_data_types=[DataType.TREND, DataType.CASE_STUDY],
        validation_criteria=[
            ValidationCriterion(
                name="has_statistics",
                description="Answer must contain at least one statistic or rate",
                required=True,
                weight=1.0
            ),
            ValidationCriterion(
                name="cites_study",
                description="Answer should cite at least one research study",
                required=False,
                weight=0.8
            ),
        ],
        domain_boosts=[
            DomainBoost(pattern="pmc.ncbi.nlm.nih.gov", boost=0.3, reason="PubMed Central - peer-reviewed"),
            DomainBoost(pattern="pubmed.ncbi.nlm.nih.gov", boost=0.3, reason="PubMed - peer-reviewed"),
            DomainBoost(pattern="cdc.gov", boost=0.2, reason="CDC - authoritative health data"),
            DomainBoost(pattern="who.int", boost=0.2, reason="WHO - authoritative health data"),
        ],
        query_keywords=["study", "research", "data", "statistics", "rate", "prevalence"],
        query_modifiers=["peer-reviewed", "systematic review", "meta-analysis"],
        min_word_count=2500,
        min_citations=8,
    ),

    QuestionType.MARKET_ANALYSIS: QuestionTypeProfile(
        question_type=QuestionType.MARKET_ANALYSIS,
        description="Questions about market size, trends, competitive landscape, and business analysis",
        source_priorities=[SourceType.INDUSTRY, SourceType.NEWS, SourceType.GENERAL_WEB],
        required_data_types=[DataType.TREND, DataType.STATISTIC],
        optional_data_types=[DataType.COMPARISON, DataType.EXPERT_OPINION],
        validation_criteria=[
            ValidationCriterion(
                name="has_market_data",
                description="Answer must contain market size or trend data",
                required=True,
                weight=1.0
            ),
            ValidationCriterion(
                name="has_timeframe",
                description="Data should include timeframe or forecast period",
                required=False,
                weight=0.6
            ),
        ],
        domain_boosts=[
            DomainBoost(pattern="statista.com", boost=0.2, reason="Market research data"),
            DomainBoost(pattern="grandviewresearch.com", boost=0.1, reason="Market reports"),
            DomainBoost(pattern="mordorintelligence.com", boost=0.1, reason="Market intelligence"),
        ],
        query_keywords=["market", "industry", "growth", "forecast", "trend", "CAGR"],
        query_modifiers=["market size", "market share", "industry report"],
        min_word_count=2000,
        min_citations=5,
    ),

    QuestionType.REGULATORY_COMPLIANCE: QuestionTypeProfile(
        question_type=QuestionType.REGULATORY_COMPLIANCE,
        description="Questions about laws, regulations, standards, and compliance requirements",
        source_priorities=[SourceType.GOVERNMENT, SourceType.ACADEMIC, SourceType.INDUSTRY],
        required_data_types=[DataType.REGULATION],
        optional_data_types=[DataType.DEFINITION, DataType.CASE_STUDY],
        validation_criteria=[
            ValidationCriterion(
                name="cites_regulation",
                description="Answer must cite specific regulation or standard",
                required=True,
                weight=1.0
            ),
            ValidationCriterion(
                name="specifies_jurisdiction",
                description="Answer should specify applicable jurisdiction",
                required=False,
                weight=0.7
            ),
        ],
        domain_boosts=[
            DomainBoost(pattern="epa.gov", boost=0.4, reason="EPA - regulatory authority"),
            DomainBoost(pattern="fda.gov", boost=0.4, reason="FDA - regulatory authority"),
            DomainBoost(pattern="canada.ca", boost=0.3, reason="Government of Canada"),
            DomainBoost(pattern="gov.uk", boost=0.3, reason="UK Government"),
            DomainBoost(pattern="europa.eu", boost=0.3, reason="EU official"),
        ],
        query_keywords=["regulation", "standard", "requirement", "compliance", "law", "act"],
        query_modifiers=["official", "legal requirement", "regulatory"],
        min_word_count=2000,
        min_citations=5,
    ),

    QuestionType.PRODUCT_COMPARISON: QuestionTypeProfile(
        question_type=QuestionType.PRODUCT_COMPARISON,
        description="Questions comparing products, technologies, or solutions",
        source_priorities=[SourceType.INDUSTRY, SourceType.ACADEMIC, SourceType.NEWS],
        required_data_types=[DataType.COMPARISON],
        optional_data_types=[DataType.TECHNICAL_SPEC, DataType.EXPERT_OPINION],
        validation_criteria=[
            ValidationCriterion(
                name="compares_options",
                description="Answer must compare at least 2 options",
                required=True,
                weight=1.0
            ),
            ValidationCriterion(
                name="has_criteria",
                description="Comparison should use clear criteria",
                required=False,
                weight=0.6
            ),
        ],
        domain_boosts=[
            DomainBoost(pattern="consumerreports.org", boost=0.2, reason="Consumer testing"),
        ],
        query_keywords=["comparison", "vs", "versus", "compare", "best", "review"],
        query_modifiers=["head-to-head", "benchmark", "comparison test"],
        min_word_count=2000,
        min_citations=5,
    ),

    QuestionType.QUALITATIVE_RESEARCH: QuestionTypeProfile(
        question_type=QuestionType.QUALITATIVE_RESEARCH,
        description="Questions requiring expert opinions, case studies, and qualitative analysis",
        source_priorities=[SourceType.ACADEMIC, SourceType.NEWS, SourceType.INDUSTRY],
        required_data_types=[DataType.EXPERT_OPINION],
        optional_data_types=[DataType.CASE_STUDY, DataType.TREND],
        validation_criteria=[
            ValidationCriterion(
                name="has_expert_input",
                description="Answer should include expert perspectives",
                required=True,
                weight=1.0
            ),
        ],
        domain_boosts=[
            DomainBoost(pattern="*.edu", boost=0.2, reason="Educational institution"),
        ],
        query_keywords=["expert", "opinion", "perspective", "analysis", "insight"],
        query_modifiers=["expert opinion", "thought leader", "industry expert"],
        min_word_count=2000,
        min_citations=5,
    ),

    QuestionType.TECHNICAL_SPECIFICATION: QuestionTypeProfile(
        question_type=QuestionType.TECHNICAL_SPECIFICATION,
        description="Questions about technical details, specifications, and implementation",
        source_priorities=[SourceType.INDUSTRY, SourceType.ACADEMIC, SourceType.GOVERNMENT],
        required_data_types=[DataType.TECHNICAL_SPEC],
        optional_data_types=[DataType.COMPARISON, DataType.DEFINITION],
        validation_criteria=[
            ValidationCriterion(
                name="has_specs",
                description="Answer must include technical specifications",
                required=True,
                weight=1.0
            ),
        ],
        domain_boosts=[],
        query_keywords=["specification", "technical", "how", "mechanism", "process"],
        query_modifiers=["technical specification", "engineering", "design"],
        min_word_count=2000,
        min_citations=5,
    ),

    QuestionType.UNKNOWN: QuestionTypeProfile(
        question_type=QuestionType.UNKNOWN,
        description="Default profile for unclassified questions",
        source_priorities=[SourceType.ACADEMIC, SourceType.GOVERNMENT, SourceType.NEWS],
        required_data_types=[],
        optional_data_types=[DataType.STATISTIC, DataType.EXPERT_OPINION],
        validation_criteria=[],
        domain_boosts=[],
        query_keywords=[],
        query_modifiers=[],
        min_word_count=2000,
        min_citations=5,
    ),
}


def get_profile(question_type: QuestionType) -> QuestionTypeProfile:
    """Get the profile for a question type."""
    return DEFAULT_PROFILES.get(question_type, DEFAULT_PROFILES[QuestionType.UNKNOWN])


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("QUESTION TYPES SCHEMA SELF-TEST")
    print("=" * 60)

    # Test 1: Enum values
    print("\n[TEST 1] QuestionType enum...")
    assert len(QuestionType) == 7
    assert QuestionType.QUANTITATIVE_RESEARCH.value == "quantitative_research"
    print(f"  [PASS] {len(QuestionType)} question types defined")

    # Test 2: Default profiles
    print("\n[TEST 2] Default profiles...")
    for qt in QuestionType:
        profile = get_profile(qt)
        assert profile.question_type == qt
        assert profile.min_word_count >= 2000
        assert profile.min_citations >= 5
    print(f"  [PASS] All {len(QuestionType)} profiles valid")

    # Test 3: Profile serialization
    print("\n[TEST 3] Profile serialization...")
    profile = get_profile(QuestionType.QUANTITATIVE_RESEARCH)
    data = profile.model_dump()
    assert "source_priorities" in data
    assert "validation_criteria" in data
    assert len(data["domain_boosts"]) > 0
    print(f"  [PASS] Profile serializes to {len(data)} fields")

    # Test 4: Classification result
    print("\n[TEST 4] ClassificationResult model...")
    result = ClassificationResult(
        vector_id="S1V1_Test",
        question_text="What is the contamination rate?",
        primary_type=QuestionType.QUANTITATIVE_RESEARCH,
        confidence=0.92,
        reasoning="Contains 'rate' keyword, expects numerical data",
        detected_keywords=["rate", "contamination"],
    )
    assert result.confidence > 0.9
    assert result.primary_type == QuestionType.QUANTITATIVE_RESEARCH
    print(f"  [PASS] ClassificationResult created with confidence {result.confidence}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
