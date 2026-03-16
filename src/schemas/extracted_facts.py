#!/usr/bin/env python3
"""
POLARIS Extracted Facts Schema
==============================
Sprint 3: SOTA Architecture - Structured Data Extraction

Defines Pydantic models for structured facts extracted from text.
These models enable type-safe extraction and validation of specific
data types like statistics, regulations, and comparisons.

Reference: Instructor, Pydantic, GuideX
"""

from datetime import date
from enum import Enum
from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator


class FactType(str, Enum):
    """Types of extractable facts."""
    CONTAMINATION_RATE = "contamination_rate"
    MARKET_SIZE = "market_size"
    REGULATORY = "regulatory"
    COMPARISON = "comparison"
    TECHNICAL_SPEC = "technical_spec"
    STATISTIC = "statistic"
    EXPERT_QUOTE = "expert_quote"
    DEFINITION = "definition"


class ConfidenceLevel(str, Enum):
    """Confidence levels for extracted facts."""
    HIGH = "high"       # Direct quote with clear attribution
    MEDIUM = "medium"   # Inference from context
    LOW = "low"         # Uncertain or partial information


# =============================================================================
# BASE FACT MODEL
# =============================================================================

class ExtractedFact(BaseModel):
    """
    Base model for all extracted facts.

    All fact types inherit from this and add type-specific fields.
    """
    fact_type: FactType = Field(..., description="Type of fact")
    source_chunk_id: str = Field(..., description="ID of source chunk")
    source_url: Optional[str] = Field(None, description="Source URL")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    confidence_level: ConfidenceLevel = Field(ConfidenceLevel.MEDIUM, description="Confidence category")
    raw_text: str = Field(..., description="Original text the fact was extracted from")

    # Geographic and temporal scope
    geographic_scope: Optional[str] = Field(None, description="Geographic region (e.g., 'USA', 'North America')")
    temporal_scope: Optional[str] = Field(None, description="Time period (e.g., '2023', '2020-2024')")

    # Validation
    is_verified: bool = Field(False, description="Whether fact has been verified")
    verification_notes: Optional[str] = Field(None, description="Notes from verification")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# CONTAMINATION RATE FACT
# =============================================================================

class ContaminationRateFact(ExtractedFact):
    """
    Fact about contamination rates (pathogens, chemicals, etc.).

    Examples:
    - "E. coli contamination rate of 15% in private wells"
    - "Lead levels exceeded 15 ppb in 22% of samples"
    """
    fact_type: Literal[FactType.CONTAMINATION_RATE] = FactType.CONTAMINATION_RATE

    # What is contaminated
    contaminant: str = Field(..., description="Name of contaminant (e.g., 'E. coli', 'lead', 'arsenic')")
    contaminant_type: Literal["pathogen", "chemical", "physical", "other"] = Field(
        "other", description="Category of contaminant"
    )

    # The rate/level
    rate_value: float = Field(..., description="Numeric value of the rate")
    rate_unit: Literal["percent", "per_100k", "per_million", "ppb", "ppm", "mg_l", "count", "other"] = Field(
        "percent", description="Unit of measurement"
    )

    # Context
    sample_matrix: Optional[str] = Field(None, description="What was sampled (e.g., 'drinking water', 'private wells')")
    sample_size: Optional[int] = Field(None, description="Number of samples tested")
    detection_method: Optional[str] = Field(None, description="How contamination was detected")

    # Source study
    study_year: Optional[int] = Field(None, description="Year of study")
    study_type: Optional[str] = Field(None, description="Type of study (e.g., 'survey', 'cohort')")


# =============================================================================
# MARKET SIZE FACT
# =============================================================================

class MarketSizeFact(ExtractedFact):
    """
    Fact about market size, growth, or economic data.

    Examples:
    - "Global water filter market size was $15.2 billion in 2023"
    - "Market expected to grow at 8.5% CAGR from 2024-2030"
    """
    fact_type: Literal[FactType.MARKET_SIZE] = FactType.MARKET_SIZE

    # Market identification
    market_name: str = Field(..., description="Name of the market (e.g., 'household water filters')")
    market_segment: Optional[str] = Field(None, description="Specific segment (e.g., 'reverse osmosis')")

    # Value
    value: float = Field(..., description="Market value")
    value_unit: Literal["usd_billion", "usd_million", "usd_thousand", "eur_billion", "other"] = Field(
        "usd_billion", description="Currency and scale"
    )
    value_year: int = Field(..., description="Year the value applies to")

    # Growth data
    growth_rate: Optional[float] = Field(None, description="Growth rate (e.g., CAGR)")
    growth_rate_type: Literal["cagr", "yoy", "total", "other"] = Field("cagr", description="Type of growth rate")
    forecast_start_year: Optional[int] = Field(None, description="Start year of forecast period")
    forecast_end_year: Optional[int] = Field(None, description="End year of forecast period")


# =============================================================================
# REGULATORY FACT
# =============================================================================

class RegulatoryFact(ExtractedFact):
    """
    Fact about regulations, standards, or legal requirements.

    Examples:
    - "EPA MCL for lead in drinking water is 15 ppb"
    - "NSF/ANSI Standard 53 certifies filters for lead reduction"
    """
    fact_type: Literal[FactType.REGULATORY] = FactType.REGULATORY

    # Regulation identification
    regulation_name: str = Field(..., description="Name of regulation/standard")
    regulation_type: Literal["law", "standard", "guideline", "requirement", "other"] = Field(
        "regulation", description="Type of regulation"
    )
    issuing_body: str = Field(..., description="Who issued it (e.g., 'EPA', 'FDA', 'NSF')")

    # Jurisdiction
    jurisdiction: str = Field(..., description="Where it applies (e.g., 'USA', 'California', 'EU')")
    jurisdiction_level: Literal["federal", "state", "local", "international", "other"] = Field(
        "federal", description="Level of jurisdiction"
    )

    # Requirement details
    requirement_text: str = Field(..., description="What the regulation requires")
    threshold_value: Optional[float] = Field(None, description="Numeric threshold if applicable")
    threshold_unit: Optional[str] = Field(None, description="Unit for threshold")

    # Effective dates
    effective_date: Optional[str] = Field(None, description="When regulation took effect")
    compliance_deadline: Optional[str] = Field(None, description="Deadline for compliance")


# =============================================================================
# COMPARISON FACT
# =============================================================================

class ComparisonFact(ExtractedFact):
    """
    Fact comparing two or more items.

    Examples:
    - "RO filters remove 99% of lead vs 95% for carbon filters"
    - "Filter A costs $200 vs Filter B at $150"
    """
    fact_type: Literal[FactType.COMPARISON] = FactType.COMPARISON

    # What's being compared
    comparison_subject: str = Field(..., description="What aspect is being compared (e.g., 'lead removal', 'cost')")
    items_compared: List[str] = Field(..., min_length=2, description="Items being compared")

    # Comparison values
    values: Dict[str, Union[float, str]] = Field(..., description="Value for each item")
    value_unit: Optional[str] = Field(None, description="Unit of measurement")

    # Winner/conclusion
    winner: Optional[str] = Field(None, description="Item that performs better (if applicable)")
    comparison_basis: Optional[str] = Field(None, description="Basis for comparison")


# =============================================================================
# TECHNICAL SPECIFICATION FACT
# =============================================================================

class TechnicalSpecFact(ExtractedFact):
    """
    Fact about technical specifications.

    Examples:
    - "Flow rate: 0.5 gallons per minute"
    - "Filter pore size: 0.2 microns"
    """
    fact_type: Literal[FactType.TECHNICAL_SPEC] = FactType.TECHNICAL_SPEC

    # What the spec is for
    subject: str = Field(..., description="What the spec describes (e.g., 'RO membrane')")
    specification_name: str = Field(..., description="Name of specification (e.g., 'flow rate')")

    # Value
    value: Union[float, str] = Field(..., description="Specification value")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    # Range (if applicable)
    min_value: Optional[float] = Field(None, description="Minimum value")
    max_value: Optional[float] = Field(None, description="Maximum value")

    # Context
    conditions: Optional[str] = Field(None, description="Conditions under which spec applies")


# =============================================================================
# STATISTIC FACT (GENERIC)
# =============================================================================

class StatisticFact(ExtractedFact):
    """
    Generic statistic that doesn't fit other categories.

    Examples:
    - "43 million Americans rely on private wells"
    - "Average household uses 80-100 gallons of water per day"
    """
    fact_type: Literal[FactType.STATISTIC] = FactType.STATISTIC

    # The statistic
    metric_name: str = Field(..., description="What is being measured")
    value: Union[float, str] = Field(..., description="The value")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    # Context
    population: Optional[str] = Field(None, description="Population the statistic applies to")
    data_source: Optional[str] = Field(None, description="Original data source")


# =============================================================================
# EXPERT QUOTE FACT
# =============================================================================

class ExpertQuoteFact(ExtractedFact):
    """
    Quote or opinion from an expert.

    Examples:
    - "Dr. Smith stated: 'Regular filter replacement is critical'"
    """
    fact_type: Literal[FactType.EXPERT_QUOTE] = FactType.EXPERT_QUOTE

    # The expert
    expert_name: str = Field(..., description="Name of the expert")
    expert_title: Optional[str] = Field(None, description="Title/position")
    expert_affiliation: Optional[str] = Field(None, description="Organization")

    # The quote
    quote_text: str = Field(..., description="The actual quote")
    is_direct_quote: bool = Field(True, description="Whether this is a direct quote")

    # Topic
    topic: str = Field(..., description="Topic the quote addresses")


# =============================================================================
# DEFINITION FACT
# =============================================================================

class DefinitionFact(ExtractedFact):
    """
    Definition or explanation of a term.

    Examples:
    - "Turbidity: a measure of water clarity"
    """
    fact_type: Literal[FactType.DEFINITION] = FactType.DEFINITION

    term: str = Field(..., description="Term being defined")
    definition: str = Field(..., description="The definition")
    context: Optional[str] = Field(None, description="Context in which term is used")


# =============================================================================
# FACT COLLECTION
# =============================================================================

class FactCollection(BaseModel):
    """Collection of extracted facts from a chunk or document."""
    source_id: str = Field(..., description="ID of the source (chunk_id or document_id)")
    source_url: Optional[str] = Field(None, description="Source URL")

    # All facts
    contamination_rates: List[ContaminationRateFact] = Field(default_factory=list)
    market_sizes: List[MarketSizeFact] = Field(default_factory=list)
    regulations: List[RegulatoryFact] = Field(default_factory=list)
    comparisons: List[ComparisonFact] = Field(default_factory=list)
    technical_specs: List[TechnicalSpecFact] = Field(default_factory=list)
    statistics: List[StatisticFact] = Field(default_factory=list)
    expert_quotes: List[ExpertQuoteFact] = Field(default_factory=list)
    definitions: List[DefinitionFact] = Field(default_factory=list)

    # Metadata
    extraction_timestamp: Optional[str] = Field(None, description="When facts were extracted")
    extractor_version: str = Field("1.0", description="Version of extractor used")

    @property
    def total_facts(self) -> int:
        """Total number of facts in collection."""
        return (
            len(self.contamination_rates) +
            len(self.market_sizes) +
            len(self.regulations) +
            len(self.comparisons) +
            len(self.technical_specs) +
            len(self.statistics) +
            len(self.expert_quotes) +
            len(self.definitions)
        )

    def all_facts(self) -> List[ExtractedFact]:
        """Get all facts as a flat list."""
        return (
            self.contamination_rates +
            self.market_sizes +
            self.regulations +
            self.comparisons +
            self.technical_specs +
            self.statistics +
            self.expert_quotes +
            self.definitions
        )


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EXTRACTED FACTS SCHEMA SELF-TEST")
    print("=" * 60)

    # Test 1: ContaminationRateFact
    print("\n[TEST 1] ContaminationRateFact...")
    fact1 = ContaminationRateFact(
        source_chunk_id="chunk_001",
        confidence=0.9,
        raw_text="E. coli was detected in 15% of private well samples",
        contaminant="E. coli",
        contaminant_type="pathogen",
        rate_value=15.0,
        rate_unit="percent",
        sample_matrix="private wells",
        sample_size=500,
        geographic_scope="USA",
    )
    assert fact1.fact_type == FactType.CONTAMINATION_RATE
    assert fact1.rate_value == 15.0
    print(f"  [PASS] Created fact: {fact1.contaminant} at {fact1.rate_value}%")

    # Test 2: MarketSizeFact
    print("\n[TEST 2] MarketSizeFact...")
    fact2 = MarketSizeFact(
        source_chunk_id="chunk_002",
        confidence=0.85,
        raw_text="The global water filter market was $15.2B in 2023",
        market_name="household water filters",
        value=15.2,
        value_unit="usd_billion",
        value_year=2023,
        growth_rate=8.5,
        forecast_end_year=2030,
    )
    assert fact2.value == 15.2
    print(f"  [PASS] Created fact: ${fact2.value}B market")

    # Test 3: RegulatoryFact
    print("\n[TEST 3] RegulatoryFact...")
    fact3 = RegulatoryFact(
        source_chunk_id="chunk_003",
        confidence=0.95,
        raw_text="EPA MCL for lead is 15 ppb",
        regulation_name="Safe Drinking Water Act - Lead MCL",
        regulation_type="standard",
        issuing_body="EPA",
        jurisdiction="USA",
        requirement_text="Maximum Contaminant Level for lead",
        threshold_value=15.0,
        threshold_unit="ppb",
    )
    assert fact3.threshold_value == 15.0
    print(f"  [PASS] Created fact: {fact3.regulation_name}")

    # Test 4: ComparisonFact
    print("\n[TEST 4] ComparisonFact...")
    fact4 = ComparisonFact(
        source_chunk_id="chunk_004",
        confidence=0.8,
        raw_text="RO removes 99% of lead vs 95% for carbon",
        comparison_subject="lead removal efficiency",
        items_compared=["RO filter", "Carbon filter"],
        values={"RO filter": 99.0, "Carbon filter": 95.0},
        value_unit="percent",
        winner="RO filter",
    )
    assert len(fact4.items_compared) == 2
    print(f"  [PASS] Created comparison: {fact4.items_compared}")

    # Test 5: FactCollection
    print("\n[TEST 5] FactCollection...")
    collection = FactCollection(
        source_id="doc_001",
        contamination_rates=[fact1],
        market_sizes=[fact2],
        regulations=[fact3],
        comparisons=[fact4],
    )
    assert collection.total_facts == 4
    print(f"  [PASS] Collection has {collection.total_facts} facts")

    # Test 6: Serialization
    print("\n[TEST 6] Serialization...")
    data = fact1.model_dump()
    assert "contaminant" in data
    assert data["fact_type"] == "contamination_rate"
    print(f"  [PASS] Fact serializes to {len(data)} fields")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
