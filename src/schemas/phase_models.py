"""
POLARIS Phase Models - The Law
==============================
Pydantic schemas for all 13 pipeline phases.
These schemas are the contract between phases.
If a phase output doesn't validate, the phase has FAILED.

Usage:
    from src.schemas.phase_models import Phase0Output, Phase1Output, ...
"""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class PhaseStatus(str, Enum):
    """Status of a phase execution."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GatingCase(str, Enum):
    """Gating decision cases."""
    CASE_1 = "CASE_1"  # Sufficient evidence, high confidence -> Finalize
    CASE_2 = "CASE_2"  # Partial evidence -> Iterate
    CASE_3 = "CASE_3"  # Insufficient evidence -> Gap report
    CASE_4 = "CASE_4"  # Critical failure -> Escalate


class RelevanceTier(str, Enum):
    """Relevance tier for filtered chunks."""
    GOLD = "gold"      # >= 0.70 fused score
    SILVER = "silver"  # 0.55-0.69
    BRONZE = "bronze"  # 0.40-0.54
    REJECTED = "rejected"  # < 0.40


class ConfidenceBand(str, Enum):
    """Confidence level bands."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OutputType(str, Enum):
    """Type of final output."""
    ANSWER = "answer"
    GAP_REPORT = "gap_report"
    FAILURE_REPORT = "failure_report"


class ChallengeType(str, Enum):
    """Type of adversarial challenge."""
    FACTUAL = "FACTUAL"
    EVIDENCE = "EVIDENCE"
    METHODOLOGY = "METHODOLOGY"
    COMPLETENESS = "COMPLETENESS"
    CONTRADICTION = "CONTRADICTION"


class AssessmentType(str, Enum):
    """Assessment of claim support."""
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNCERTAIN = "UNCERTAIN"
    REFUTED = "REFUTED"
    NO_EVIDENCE = "NO_EVIDENCE"


class VerificationStatus(str, Enum):
    """Verification status for claims/citations."""
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


# =============================================================================
# COMMON MODELS
# =============================================================================

class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: Optional[str] = None


class Citation(BaseModel):
    """Citation reference."""
    number: int = Field(..., description="Sequential citation number [1], [2], etc.")
    evidence_id: str = Field(..., description="Internal chunk ID")
    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Document title")
    domain: str = Field(..., description="Source domain e.g. nature.com")
    author: Optional[str] = None
    date: Optional[str] = None
    doi: Optional[str] = None
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to claim")
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class Claim(BaseModel):
    """Extracted claim with evidence."""
    claim_id: str
    text: str = Field(..., description="The claim statement")
    claim_type: str = Field(..., description="factual, statistical, comparative, causal")
    evidence_ids: List[str] = Field(default_factory=list)
    primary_source_url: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    geographic_scope: Optional[str] = None
    temporal_scope: Optional[str] = None


class SearchResult(BaseModel):
    """Single search result."""
    url: str
    title: str
    snippet: str
    source_engine: str = Field(..., description="serper, pubmed, semantic_scholar, etc.")
    rank: int
    fetch_status: Optional[str] = None
    content: Optional[str] = None
    content_length: Optional[int] = None
    fetch_method: Optional[str] = None
    # SOTA: DOI and author extraction for academic sources
    doi: Optional[str] = Field(None, description="DOI if available (e.g., 10.1021/acs.est.5b00716)")
    authors: Optional[List[str]] = Field(None, description="Author name(s) extracted from content")
    # SOTA: Source-level geographic metadata for API-based filtering
    author_countries: Optional[List[str]] = Field(
        None, description="ISO 3166-1 alpha-2 country codes from author affiliations (from OpenAlex)"
    )
    publication_year: Optional[int] = Field(None, description="Publication year for recency filtering")
    citation_count: Optional[int] = Field(None, description="Citation count for impact filtering")
    # FIX-124: STORM Perspective Tracking
    # Preserves which expert perspective generated the query that found this result
    perspective_origin: Optional[str] = Field(
        None,
        description="STORM perspective that generated the query finding this result (e.g., 'Public Health Expert')"
    )
    # FIX-124B: Multiple perspective attribution after deduplication
    # When same URL found by multiple perspectives, all are preserved here
    perspective_origins: List[str] = Field(
        default_factory=list,
        description="All STORM perspectives that found this result (merged during deduplication)"
    )


class ChunkMetadata(BaseModel):
    """Metadata for indexed chunk."""
    chunk_id: str
    source_url: str
    source_title: str
    source_domain: str
    fetch_timestamp: str
    content_hash: str
    geographic_scope: List[str] = Field(default_factory=list)
    relevance_tier: RelevanceTier
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


# =============================================================================
# PHASE 0: INITIALIZATION & NOVELTY CHECK
# =============================================================================

class Phase0Input(BaseModel):
    """Input for Phase 0."""
    vector_id: str = Field(..., description="e.g. S1V1_Household_Water_Filter_NORTH_AMERICA")
    application: str
    region: str
    stage: int = Field(..., ge=1, le=13)


class Phase0Output(BaseModel):
    """Output from Phase 0: Initialization & Novelty Check."""
    vector_id: str
    status: str = Field(..., description="proceed | duplicate | near_duplicate")
    fingerprint: str = Field(..., description="SHA256 hash of vector question")
    vwm_collection: str = Field(..., description="ChromaDB collection name")
    peer_vector_id: Optional[str] = Field(None, description="If duplicate detected")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamps: Dict[str, str] = Field(default_factory=dict)

    # Parsed vector components
    stage: int
    application: str
    region: str
    question: str
    is_regional: bool

    # SOTA: Question Type Classification (Sprint 2)
    question_type: Optional[str] = Field(None, description="Classified question type from P00")
    question_type_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    classification_method: Optional[str] = Field(None, description="keyword | llm | hybrid")

    # SOTA: PICO Framework Extraction (from upgrade plan)
    pico_population: Optional[str] = Field(None, description="Target population/setting (e.g., 'households', 'private wells')")
    pico_intervention: Optional[str] = Field(None, description="Intervention being studied (e.g., 'water filter', 'C-POLAR coating')")
    pico_comparison: Optional[str] = Field(None, description="Comparison group/alternative (e.g., 'untreated water', 'UV treatment')")
    pico_outcome: Optional[str] = Field(None, description="Expected outcomes (e.g., 'contamination rates', 'pathogen reduction')")

    # SOTA: Geographic Scope Extraction (from upgrade plan)
    geographic_scope: Optional[List[str]] = Field(
        None,
        description="Expected geographic scope as ISO 3166-1 alpha-2 codes (e.g., ['US', 'CA', 'MX'])"
    )
    geographic_keywords: Optional[List[str]] = Field(
        None,
        description="Geographic keywords for search targeting (e.g., ['United States', 'Canada', 'Mexico'])"
    )


# =============================================================================
# PHASE 1: CONTEXTUALIZATION
# =============================================================================

class QueryTemplate(BaseModel):
    """Structured query template for API-specific query generation in P2."""
    api_name: str = Field(..., description="openalex | semantic_scholar | pubmed | serper")
    base_query: str = Field(..., description="Base search query string")
    filters: Dict[str, Any] = Field(default_factory=dict, description="API-specific filters")
    boost_terms: List[str] = Field(default_factory=list, description="Terms to boost in ranking")
    required_terms: List[str] = Field(default_factory=list, description="Terms that must be present")
    exclude_terms: List[str] = Field(default_factory=list, description="Terms to exclude")


class Phase1Output(BaseModel):
    """Output from Phase 1: Contextualization (HPRP from LTM)."""
    vector_id: str
    strategic_plan: Dict[str, Any] = Field(
        ...,
        description="Contains knowledge_gaps, priorities, strategies"
    )
    ltm_stage_hits: int = Field(..., ge=0)
    ltm_global_hits: int = Field(..., ge=0)
    prior_knowledge_summary: str
    research_focus_areas: List[str] = Field(default_factory=list)
    timestamps: Dict[str, str] = Field(default_factory=dict)

    # SOTA: OpenAlex Concepts API taxonomy expansion (from upgrade plan)
    expanded_terms: List[str] = Field(
        default_factory=list,
        description="Expanded search terms from OpenAlex Concepts API"
    )
    openalex_concepts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Raw OpenAlex concept objects with IDs and scores"
    )

    # SOTA: MeSH term lookup for biomedical vectors (from upgrade plan)
    mesh_terms: List[str] = Field(
        default_factory=list,
        description="MeSH (Medical Subject Headings) terms for biomedical search"
    )
    mesh_descriptors: List[Dict[str, str]] = Field(
        default_factory=list,
        description="MeSH descriptor objects with UI, name, and tree numbers"
    )
    is_biomedical: bool = Field(
        default=False,
        description="Whether vector is classified as biomedical (triggers MeSH lookup)"
    )

    # SOTA: Geographic scope from P0 (propagated for query generation)
    geographic_iso_codes: List[str] = Field(
        default_factory=list,
        description="ISO 3166-1 alpha-2 codes from P0 geographic_scope"
    )

    # SOTA: Structured query templates per API (from upgrade plan)
    query_templates: List[QueryTemplate] = Field(
        default_factory=list,
        description="Pre-built query templates for each target API"
    )


# =============================================================================
# PHASE 2: QUERY GENERATION
# =============================================================================

class PerspectiveQuery(BaseModel):
    """FIX-124: STORM perspective-tagged query for multi-perspective research.

    Stanford STORM methodology requires preserving perspective identity throughout
    the pipeline to ensure true multi-perspective coverage verification.
    """
    query_text: str = Field(..., description="The search query text")
    perspective_name: str = Field(..., description="STORM perspective (e.g., 'Public Health Expert')")
    perspective_id: str = Field(..., description="Unique ID for grouping (e.g., 'perspective_1234')")
    bucket: str = Field("general", description="Target bucket (academic, government, industry, news, general)")
    focus: Optional[str] = Field(None, description="What this perspective focuses on")


class APIQuery(BaseModel):
    """SOTA: Structured query for a specific academic API."""
    api_name: str = Field(..., description="openalex | semantic_scholar | pubmed | serper")
    query_string: str = Field(..., description="Formatted query string for the API")
    filters: Dict[str, Any] = Field(default_factory=dict, description="API-specific filter parameters")
    raw_query: str = Field(..., description="Original query before API-specific formatting")
    boost_terms: List[str] = Field(default_factory=list, description="Terms to boost in ranking")
    expected_results: int = Field(default=25, ge=1, description="Expected number of results")


class Phase2Output(BaseModel):
    """Output from Phase 2: Query Generation."""
    vector_id: str
    final_queries: List[str] = Field(..., min_length=1, description="Minimum 20 queries")
    query_count: int = Field(..., ge=1)
    bucket_distribution: Dict[str, int] = Field(
        ...,
        description="academic, government, industry, news, general counts"
    )
    geographic_targeting: bool
    authority_anchors_applied: int = Field(..., ge=0)
    timestamps: Dict[str, str] = Field(default_factory=dict)

    # SOTA: API-specific structured queries (from upgrade plan)
    api_queries: List[APIQuery] = Field(
        default_factory=list,
        description="Structured queries formatted for each academic API"
    )
    openalex_query_count: int = Field(default=0, ge=0, description="Number of OpenAlex queries generated")
    semantic_scholar_query_count: int = Field(default=0, ge=0, description="Number of S2 queries generated")
    pubmed_query_count: int = Field(default=0, ge=0, description="Number of PubMed queries generated")

    # FIX-124: STORM Perspective-tagged queries (Stanford STORM methodology)
    # These preserve perspective identity for true multi-perspective research
    perspective_queries: List[PerspectiveQuery] = Field(
        default_factory=list,
        description="STORM perspective-tagged queries with preserved identity"
    )
    perspective_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of queries per STORM perspective"
    )

    @field_validator('final_queries')
    @classmethod
    def validate_query_count(cls, v):
        if len(v) < 20:
            raise ValueError(f"Must have at least 20 queries, got {len(v)}")
        return v


# =============================================================================
# PHASE 3: SEARCH EXECUTION
# =============================================================================

class Phase3Output(BaseModel):
    """Output from Phase 3: Search Execution (Federated Multi-Engine)."""
    vector_id: str
    search_results: List[SearchResult] = Field(default_factory=list)
    urls_attempted: int = Field(..., ge=0)
    urls_success: int = Field(..., ge=0)
    urls_failed: int = Field(..., ge=0)
    content_by_engine: Dict[str, int] = Field(default_factory=dict)
    total_content_chars: int = Field(..., ge=0)
    fetch_methods: Dict[str, int] = Field(
        default_factory=dict,
        description="requests/playwright/archive counts"
    )
    timestamps: Dict[str, str] = Field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.urls_attempted == 0:
            return 0.0
        return self.urls_success / self.urls_attempted


# =============================================================================
# PHASE 4: RELEVANCE FILTERING (TWO-STAGE IsREL)
# =============================================================================

class Phase4Output(BaseModel):
    """Output from Phase 4: Relevance Filtering."""
    vector_id: str
    # URL fetching statistics
    urls_attempted: int = Field(default=0, ge=0, description="Total URLs attempted to fetch")
    urls_successful: int = Field(default=0, ge=0, description="URLs successfully fetched")
    urls_failed: int = Field(default=0, ge=0, description="URLs that failed to fetch")
    fetch_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    fetch_methods: Dict[str, int] = Field(
        default_factory=dict,
        description="Count by fetch method (requests, academic_api, pdf, etc.)"
    )
    # Chunk statistics
    chunks_input: int = Field(..., ge=0)
    chunks_passed: int = Field(..., ge=0)
    chunks_rejected: int = Field(..., ge=0)
    # SOTA: Corpus quality metrics
    off_topic_rejected: int = Field(
        default=0,
        ge=0,
        description="Chunks rejected by hard minimum relevance threshold (corpus pollution)"
    )
    corpus_relevance_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Percentage of chunks that passed minimum relevance (1.0 = clean corpus)"
    )
    tier_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="gold/silver/bronze/rejected counts"
    )
    relevance_scores: List[float] = Field(default_factory=list)
    filtered_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    timestamps: Dict[str, str] = Field(default_factory=dict)


# =============================================================================
# PHASE 5: VWM INDEXING
# =============================================================================

class Phase5Output(BaseModel):
    """Output from Phase 5: VWM Indexing (Semantic Chunking + Embedding)."""
    vector_id: str
    chunks_indexed: int = Field(..., ge=0)
    vwm_collection_size: int = Field(..., ge=0)
    embeddings_generated: int = Field(..., ge=0)
    gpu_used: bool
    ltm_promotions: int = Field(..., ge=0, description="Chunks promoted to LTM-Stage")
    chunking_template: str = Field(..., description="research_paper/technical_report/news_article")
    timestamps: Dict[str, str] = Field(default_factory=dict)


# =============================================================================
# PHASE 6: NLI INTEGRITY
# =============================================================================

class ContradictionDetail(BaseModel):
    """Details of a detected contradiction."""
    chunk_a_id: str
    chunk_b_id: str
    chunk_a_text: str
    chunk_b_text: str
    contradiction_score: float = Field(..., ge=0.0, le=1.0)
    explanation: Optional[str] = None
    # SOTA: Per-class confidence breakdown for transparency
    confidence_breakdown: Optional[Dict[str, float]] = Field(
        default=None,
        description="SciFact confidence scores: supports, refutes, not_enough_info"
    )


class Phase6Output(BaseModel):
    """Output from Phase 6: NLI Integrity (Contradiction Detection)."""
    vector_id: str
    pairs_checked: int = Field(..., ge=0)
    contradictions_found: int = Field(..., ge=0)
    integrity_score: float = Field(..., ge=0.0, le=1.0)
    contradiction_details: List[ContradictionDetail] = Field(default_factory=list)
    status: str = Field(..., description="pass | warn | fail")
    timestamps: Dict[str, str] = Field(default_factory=dict)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v not in ('pass', 'warn', 'fail'):
            raise ValueError(f"Status must be pass/warn/fail, got {v}")
        return v


# =============================================================================
# PHASE 7: DUAL RAG ANALYSIS
# =============================================================================

class Phase7Output(BaseModel):
    """Output from Phase 7: Dual RAG Analysis (Evidence-Grounded Synthesis)."""
    vector_id: str
    analysis_text: str = Field(..., min_length=1)
    thinking_process: str = Field(..., description="LLM reasoning trace")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    chunks_used: int = Field(..., ge=0)
    citation_tokens: List[str] = Field(
        default_factory=list,
        description="[CITE:xyz] markers in text"
    )
    token_usage: Dict[str, int] = Field(default_factory=dict)
    timestamps: Dict[str, str] = Field(default_factory=dict)


# =============================================================================
# PHASE 8: ADVERSARIAL QA
# =============================================================================

class AdversarialQA(BaseModel):
    """Individual adversarial question-answer pair."""
    question_id: str
    question: str
    target_claim: str
    challenge_type: str  # ChallengeType enum value
    evidence_count: int = Field(default=0, ge=0)
    answer: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    resolved: bool = False
    assessment: str = "UNCERTAIN"  # AssessmentType enum value
    supporting_chunks: List[str] = Field(default_factory=list)
    remaining_gaps: str = ""
    gap_type: Optional[str] = None


class Phase9Output(BaseModel):
    """Output from Phase 9: Adversarial QA (Stress Testing Claims)."""
    vector_id: str
    phase: str = "P9"
    timestamp_start: str
    timestamp_end: str
    p7_file: str
    research_objective: str
    qa_results: List[AdversarialQA] = Field(default_factory=list)
    gaps: List[Dict[str, Any]] = Field(default_factory=list)
    total_questions: int = Field(default=0, ge=0)
    resolved_count: int = Field(default=0, ge=0)
    unresolved_count: int = Field(default=0, ge=0)
    resolution_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    gap_type_distribution: Dict[str, int] = Field(default_factory=dict)
    timestamps: Dict[str, str] = Field(default_factory=dict)  # Legacy compatibility

    # SOTA signal_novelty metric for knowledge saturation detection
    # Measures how much new information this iteration provides vs. previous iterations
    signal_novelty: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Proportion of new evidence chunks not seen in previous iterations (1.0 = all new)"
    )
    unique_chunks_this_iteration: int = Field(
        default=0, ge=0,
        description="Number of unique evidence chunks retrieved in this iteration"
    )
    cumulative_unique_chunks: int = Field(
        default=0, ge=0,
        description="Total unique evidence chunks seen across all iterations"
    )
    new_chunks_count: int = Field(
        default=0, ge=0,
        description="Number of chunks in this iteration not seen before"
    )

    # SOTA: LLM-as-Judge rubric evaluation scores (1-5 scale)
    rubric_comprehensiveness: Optional[int] = Field(
        None, ge=1, le=5,
        description="Coverage of all required aspects (1=poor, 5=complete)"
    )
    rubric_objectivity: Optional[int] = Field(
        None, ge=1, le=5,
        description="Neutral, scientific tone without bias (1=biased, 5=objective)"
    )
    rubric_coherence: Optional[int] = Field(
        None, ge=1, le=5,
        description="Logical flow and organization (1=disorganized, 5=well-structured)"
    )
    rubric_evidence_support: Optional[int] = Field(
        None, ge=1, le=5,
        description="Claims backed by citations (1=unsupported, 5=fully cited)"
    )
    rubric_overall: Optional[float] = Field(
        None, ge=1.0, le=5.0,
        description="Average of all rubric dimensions"
    )
    rubric_needs_revision: bool = Field(
        False,
        description="True if any rubric dimension < 3 (requires refinement)"
    )
    rubric_feedback: Optional[str] = Field(
        None,
        description="LLM judge feedback on areas needing improvement"
    )


# =============================================================================
# PHASE 10: GATING LOGIC
# =============================================================================

class Phase10Output(BaseModel):
    """Output from Phase 10: Gating Logic (CASE 1/2/3/4 Decision)."""
    vector_id: str
    gating_case: GatingCase
    justification: str = Field(..., min_length=1)
    next_action: str = Field(..., description="What to do next based on case")
    sufficiency_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    integrity_score: float = Field(..., ge=0.0, le=1.0)
    iteration_count: int = Field(default=1, ge=1)
    timestamps: Dict[str, str] = Field(default_factory=dict)

    # SOTA: RAGAS metrics for claim verification and answer quality
    validation_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Combined validation score (RAGAS + rule-based)")
    faithfulness_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="RAGAS faithfulness - claim verification rate")
    context_precision: Optional[float] = Field(None, ge=0.0, le=1.0, description="RAGAS context precision")
    context_recall: Optional[float] = Field(None, ge=0.0, le=1.0, description="RAGAS context recall")
    answer_relevancy: Optional[float] = Field(None, ge=0.0, le=1.0, description="RAGAS answer relevancy")
    claims_verified: Optional[int] = Field(None, ge=0, description="Number of claims verified against context")
    claims_total: Optional[int] = Field(None, ge=0, description="Total claims in answer")
    quality_tier: Optional[str] = Field(None, description="RAGAS quality tier (gold/silver/bronze/poor)")
    ragas_available: bool = Field(False, description="Whether RAGAS evaluation was performed")


# =============================================================================
# PHASE 11: KNOWLEDGE INTEGRATION
# =============================================================================

class Phase11Output(BaseModel):
    """Output from Phase 11: Knowledge Integration (LTM Promotion)."""
    vector_id: str
    ltm_global_updated: bool
    claims_persisted: int = Field(..., ge=0)
    cross_references: List[str] = Field(default_factory=list)
    archive_path: str
    gating_case: GatingCase = Field(..., description="Must be CASE_1 for LTM update")
    timestamps: Dict[str, str] = Field(default_factory=dict)


# =============================================================================
# PHASE 12: RESEARCH PACKAGING
# =============================================================================

class Phase12Output(BaseModel):
    """Output from Phase 12: Research Packaging (Final Report Assembly)."""
    vector_id: str
    output_type: OutputType
    report_text: str = Field(..., min_length=1)
    word_count: int = Field(..., ge=0)
    citations: List[Citation] = Field(default_factory=list)
    citation_count: int = Field(..., ge=0)
    confidence_band: ConfidenceBand
    verified_claims: List[Claim] = Field(default_factory=list)
    timestamps: Dict[str, str] = Field(default_factory=dict)

    @field_validator('word_count')
    @classmethod
    def validate_word_count(cls, v, info):
        # Only enforce for answer type, not gap reports
        # Threshold reduced to 500 for initial web data quality
        if info.data.get('output_type') == OutputType.ANSWER and v < 500:
            raise ValueError(f"Answer reports must have >= 500 words, got {v}")
        return v

    @field_validator('citation_count')
    @classmethod
    def validate_citation_count(cls, v, info):
        if info.data.get('output_type') == OutputType.ANSWER and v < 5:
            raise ValueError(f"Answer reports must have >= 5 citations, got {v}")
        return v


# =============================================================================
# PHASE 13: NARRATIVE SYNTHESIS
# =============================================================================

class Phase13Output(BaseModel):
    """Output from Phase 13: Narrative Synthesis (Cross-Vector Integration)."""
    vector_id: str
    stage: int = Field(..., ge=1, le=13)
    stage_summary: str = Field(..., description="Executive summary for the stage")
    cross_vector_patterns: List[str] = Field(default_factory=list)
    key_themes: List[str] = Field(default_factory=list)
    vectors_integrated: List[str] = Field(default_factory=list)
    next_stage_inputs: Dict[str, Any] = Field(default_factory=dict)
    timestamps: Dict[str, str] = Field(default_factory=dict)


# =============================================================================
# LEDGER ENTRY
# =============================================================================

class LedgerEntry(BaseModel):
    """Entry in progress_ledger.jsonl."""
    ts: str = Field(..., description="ISO-8601 timestamp")
    vector_id: str
    phase: int = Field(..., ge=0, le=13)
    status: PhaseStatus
    attempt: int = Field(..., ge=1)
    input_paths: List[str] = Field(default_factory=list)
    output_path: Optional[str] = None
    sha256_input: Optional[str] = None
    sha256_output: Optional[str] = None
    runtime_sec: Optional[float] = None
    notes: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# RESEARCH REPORT (FINAL OUTPUT)
# =============================================================================

class ResearchReport(BaseModel):
    """Complete research report for a vector."""
    # Identity
    vector_id: str
    stage: int = Field(..., ge=1, le=13)
    application: str
    region: str

    # Output
    output_type: OutputType
    answer: str = Field(..., description="Full report text")
    word_count: int

    # Citations
    citations: List[Citation] = Field(default_factory=list)
    citation_count: int

    # Quality
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    sufficiency_score: float = Field(..., ge=0.0, le=1.0)
    integrity_score: float = Field(..., ge=0.0, le=1.0)
    quality_gate_passed: bool

    # Verification
    verified_claims: List[Claim] = Field(default_factory=list)
    claims_total: int = Field(..., ge=0)
    claims_verified: int = Field(..., ge=0)
    claims_failed: int = Field(..., ge=0)

    # Execution
    gating_case: GatingCase
    execution_time_seconds: float = Field(..., ge=0.0)
    retrieval_iterations: int = Field(..., ge=1)
    sources_fetched: int = Field(..., ge=0)
    sources_used: int = Field(..., ge=0)

    # Provenance
    phase_outputs: Dict[int, str] = Field(
        default_factory=dict,
        description="Map of phase number to output file path"
    )


# =============================================================================
# VECTOR DEFINITION
# =============================================================================

class Vector(BaseModel):
    """Vector definition from vector library."""
    id: str = Field(..., description="S1V1_Household_Water_Filter_NORTH_AMERICA")
    stage: int = Field(..., ge=1, le=13)
    stage_name: str
    vector_number: int = Field(..., ge=1)
    question: str = Field(..., description="Full question text")
    question_template: str = Field(..., description="Template with {application} {region}")
    application: str
    region: str = Field(..., description="NORTH_AMERICA | EUROPE | ASIA_PACIFIC | GLOBAL")
    is_regional: bool
    chunking_template: str = Field(..., description="research_paper | technical_report | news_article")


# =============================================================================
# WORK QUEUE
# =============================================================================

class WorkQueueItem(BaseModel):
    """Single item in work queue."""
    vector_id: str
    stage: int
    application: str
    region: str
    status: str = Field(default="pending", description="pending | running | completed | failed")


class WorkQueue(BaseModel):
    """Full work queue."""
    total_vectors: int = Field(..., description="Must be 175")
    vectors: List[WorkQueueItem]

    @field_validator('total_vectors')
    @classmethod
    def validate_total(cls, v):
        if v != 175:
            raise ValueError(f"Work queue must have exactly 175 vectors, got {v}")
        return v

    @field_validator('vectors')
    @classmethod
    def validate_vector_count(cls, v, info):
        expected = info.data.get('total_vectors', 175)
        if len(v) != expected:
            raise ValueError(f"Vector list length {len(v)} != total_vectors {expected}")
        return v


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "PhaseStatus",
    "GatingCase",
    "RelevanceTier",
    "ConfidenceBand",
    "OutputType",
    "VerificationStatus",

    # Common models
    "Citation",
    "Claim",
    "SearchResult",
    "ChunkMetadata",

    # Phase outputs
    "Phase0Input",
    "Phase0Output",
    "QueryTemplate",
    "Phase1Output",
    "APIQuery",
    "Phase2Output",
    "Phase3Output",
    "Phase4Output",
    "Phase5Output",
    "Phase6Output",
    "Phase7Output",
    "AdversarialQA",
    "ChallengeType",
    "AssessmentType",
    "Phase9Output",
    "Phase10Output",
    "Phase11Output",
    "Phase12Output",
    "Phase13Output",

    # Other models
    "LedgerEntry",
    "ResearchReport",
    "Vector",
    "WorkQueueItem",
    "WorkQueue",
]
