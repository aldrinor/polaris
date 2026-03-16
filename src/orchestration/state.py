"""
POLARIS v3 Research State Definition

Defines the TypedDict that flows through the LangGraph state machine.
All agents read from and write to this shared state.

Based on OpenAI Deep Research architecture:
- Query decomposition → sub-queries
- Evidence accumulation → knowledge graph
- Iterative refinement → ReAct loop
- Quality gating → verification results
"""

from typing import TypedDict, List, Dict, Optional, Any, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field


# =============================================================================
# Sub-Components (Pydantic models for validation)
# =============================================================================

class SubQuery(BaseModel):
    """A decomposed sub-question from the main research query."""
    query_id: str
    query_text: str
    expected_data_type: str  # factual, statistical, comparative, procedural
    priority: int = Field(ge=1, le=5, default=3)
    search_keywords: List[str] = Field(default_factory=list)
    domain_hints: List[str] = Field(default_factory=list)
    # FIX-124: STORM perspective tracking
    perspective_name: Optional[str] = Field(None, description="STORM perspective (e.g., 'Scientific', 'Regulatory')")
    perspective_id: Optional[str] = Field(None, description="Unique perspective ID for grouping")
    status: Literal["pending", "searching", "complete", "failed"] = "pending"


class SearchResult(BaseModel):
    """A single search result from web or academic search."""
    result_id: str
    url: str
    title: str
    snippet: str
    source_type: Literal["web", "academic", "government", "news"]
    domain: str
    fetch_status: Literal["pending", "success", "failed"] = "pending"
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # FIX-124: STORM perspective tracking
    perspective_origin: Optional[str] = Field(None, description="Perspective that generated this query")
    # FIX-124B: Multi-perspective tracking (same URL found by different perspectives)
    perspective_origins: List[str] = Field(default_factory=list, description="All perspectives that found this URL")


# FIX 98: AtomicFact schema for surgical synthesis (moved from analyst_agent)
class AtomicFact(BaseModel):
    """
    FIX 97/98: An ATOMIC fact - a single, falsifiable statement with direct quote.

    Atomic facts are the building blocks for high-citation-density reports.
    Each atomic fact should be:
    1. A single, specific claim (not a summary)
    2. Directly quotable from the source
    3. Falsifiable (can be verified as true/false)
    4. Contains ONE piece of information (number, date, name, measurement)
    """
    statement: str = Field(description="A single, specific factual statement")
    direct_quote: str = Field(description="EXACT verbatim quote from source")
    fact_category: Literal[
        "statistic", "measurement", "date_time", "named_entity",
        "regulatory_threshold", "standard_reference", "causal_link",
        "comparative", "geographic", "temporal_trend"
    ] = Field(description="Category of atomic fact")
    atomicity_score: float = Field(default=0.8, description="How atomic is this fact (0-1)")
    entities: List[str] = Field(default_factory=list, description="Named entities in fact")


class Evidence(BaseModel):
    """A piece of evidence extracted from a source.

    SOTA FIX: Added quality_tier for GOLD/SILVER/BRONZE classification.
    FIX 98: Added atomic_facts for surgical synthesis.
    FIX-180A: Added title for bibliography metadata enrichment.
    """
    evidence_id: str
    chunk_id: str
    source_url: str
    title: str = ""  # FIX-180A: Source title for bibliography
    text: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    source_quality_score: float = Field(ge=0.0, le=1.0)
    extraction_method: str  # dense, sparse, graph
    claims: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    # SOTA FIX: Quality tier classification
    quality_tier: Literal["GOLD", "SILVER", "BRONZE", "UNVERIFIED"] = "UNVERIFIED"
    is_metadata: bool = False  # Flag for metadata vs content
    citation_count: int = 0  # For academic sources
    source_domain_type: Optional[Literal["gov", "edu", "org", "com", "other"]] = None
    # FIX 98: Atomic facts for surgical synthesis
    atomic_facts: List[AtomicFact] = Field(default_factory=list, description="Atomic facts extracted from this evidence")
    # FIX-124: STORM perspective tracking for balanced synthesis
    perspective_origins: List[str] = Field(default_factory=list, description="STORM perspectives that found this evidence")
    # FIX-227: Author metadata for bibliography
    authors: List[str] = Field(default_factory=list, description="Author names from search results")

    @classmethod
    def classify_quality_tier(
        cls,
        relevance_score: float,
        source_quality_score: float,
        source_url: str,
        citation_count: int = 0,
    ) -> Literal["GOLD", "SILVER", "BRONZE", "UNVERIFIED"]:
        """
        Classify evidence into quality tiers.

        GOLD: High-quality, authoritative sources
        SILVER: Good quality, reliable sources
        BRONZE: Lower quality but still useful
        UNVERIFIED: Needs verification

        Args:
            relevance_score: How relevant the evidence is (0-1)
            source_quality_score: Source reliability (0-1)
            source_url: URL of the source
            citation_count: Citation count for academic sources

        Returns:
            Quality tier classification
        """
        combined_score = (relevance_score + source_quality_score) / 2

        # FIX 25 (Gemini Audit FIX 5): REMOVED domain authority bonus.
        # The +0.1 bonus for .gov/.edu domains was pushing ALL .gov fragments
        # to GOLD tier (0.475 + 0.1 = 0.575 > 0.55 threshold) regardless of
        # content relevance. This created "GOLD garbage" — irrelevant .gov
        # boilerplate classified as high-quality evidence.
        #
        # Quality tier should be determined ONLY by relevance and source quality
        # scores, not by domain heuristics. A .gov cookie notice is not GOLD.

        # Academic citation bonus (capped, evidence-based)
        citation_bonus = min(citation_count / 100, 0.2) if citation_count > 0 else 0

        adjusted_score = combined_score + citation_bonus

        # Thresholds aligned with thresholds.yaml
        if adjusted_score >= 0.55:
            return "GOLD"
        elif adjusted_score >= 0.40:
            return "SILVER"
        elif adjusted_score >= 0.25:
            return "BRONZE"
        else:
            return "UNVERIFIED"

    @classmethod
    def detect_metadata(cls, text: str) -> bool:
        """
        Detect if text is metadata rather than actual content.

        SOTA FIX: Filter out metadata that was incorrectly extracted as evidence.
        BUG-008 FIX: Expanded patterns to catch license text, publication metadata.

        Args:
            text: The evidence text

        Returns:
            True if text appears to be metadata
        """
        import re

        # Common metadata patterns
        metadata_patterns = [
            "cookie", "privacy policy", "terms of service",
            "subscribe", "newsletter", "sign up",
            "copyright", "all rights reserved",
            "login", "register", "account",
            "advertisement", "sponsored",
            "navigation", "menu", "sidebar",
            "social media", "share this", "follow us",
            "contact us", "about us",
            # BUG-008 FIX: License patterns
            "creative commons", "licensed under", "cc by",
            "open access", "this article is licensed",
            "which permits use", "as long as you give",
            "appropriate credit", "provide a link",
            # BUG-008 FIX: Publication/journal metadata
            "author contributions", "authors' contributions",
            "competing interests", "conflict of interest",
            "acknowledgements", "acknowledgments",
            "supplementary material", "supplementary information",
            "data availability", "funding information",
            "received:", "accepted:", "published online",
            "corresponding author", "author information",
            "ethical approval", "informed consent",
        ]

        text_lower = text.lower()

        # Check for metadata patterns
        metadata_count = sum(1 for p in metadata_patterns if p in text_lower)

        # If more than 2 metadata patterns or very short text, flag as metadata
        if metadata_count >= 2:
            return True

        # Short text without substance
        if len(text) < 50 and metadata_count >= 1:
            return True

        # BUG-008 FIX: Detect publication citation format
        # Pattern: "Journal Name. YYYY Mon DD;Vol(Issue):Pages. doi:"
        citation_pattern = re.compile(
            r'\d{4}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2};\d+',
            re.IGNORECASE
        )
        if citation_pattern.search(text_lower):
            return True

        # BUG-008 FIX: Detect DOI-only text
        doi_pattern = re.compile(r'^doi:\s*10\.\d+/\S+$', re.IGNORECASE)
        if doi_pattern.match(text.strip()):
            return True

        # BUG-008 FIX: Detect PMID/PMCID-only text
        pmid_pattern = re.compile(r'^(pmid|pmcid):\s*\d+$', re.IGNORECASE)
        if pmid_pattern.match(text.strip()):
            return True

        return False


class Gap(BaseModel):
    """An identified knowledge gap requiring additional research."""
    gap_id: str
    description: str
    gap_type: Literal["missing_data", "weak_evidence", "contradictory", "incomplete"]
    priority: int = Field(ge=1, le=5, default=3)
    suggested_queries: List[str] = Field(default_factory=list)
    iteration_discovered: int = 1


class VerificationResult(BaseModel):
    """Result of verifying a claim against evidence."""
    claim_id: str
    claim_text: str
    verdict: Literal["supported", "refuted", "uncertain", "insufficient_evidence"]
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)


class QualityMetrics(BaseModel):
    """Quality metrics for the current research state."""
    faithfulness: float = Field(ge=0.0, le=1.0, default=0.0)
    context_precision: float = Field(ge=0.0, le=1.0, default=0.0)
    answer_relevancy: float = Field(ge=0.0, le=1.0, default=0.0)
    source_diversity: int = 0
    claim_coverage: float = Field(ge=0.0, le=1.0, default=0.0)
    iteration_improvement: float = 0.0  # Delta from previous iteration


# =============================================================================
# Main Research State (TypedDict for LangGraph)
# =============================================================================

class ResearchState(TypedDict, total=False):
    """
    The complete state that flows through the LangGraph research workflow.

    This state is:
    - Read by all agents to understand context
    - Written to by agents to record their outputs
    - Persisted between iterations for crash recovery
    - Used for conditional routing decisions

    State Flow:
    1. TRIAGE: Sets query_type, complexity
    2. PLANNER: Sets sub_queries, research_plan
    3. SEARCH: Appends to search_results
    4. ANALYST: Appends to evidence_chain, updates knowledge_graph
    5. VERIFIER: Sets verification_results
    6. CRITIC: Sets gaps, quality_metrics
    7. SYNTHESIZER: Sets draft_report, final_report
    """

    # ===================
    # Input (set at start)
    # ===================
    vector_id: str  # Format: "S{stage}V{num}_{application}_{region}"
    original_query: str  # The research question
    application: str  # Application domain (from work_queue)
    region: str  # Geographic region (from work_queue)
    stage: int  # 1-13

    # ===================
    # Triage Output
    # ===================
    query_type: str  # factual, statistical, comparative, procedural, exploratory, regulatory, market
    complexity: Literal["simple", "moderate", "complex"]
    estimated_sources_needed: int

    # ===================
    # Planner Output
    # ===================
    sub_queries: List[SubQuery]
    research_plan: Dict[str, Any]  # Structured plan with phases
    search_strategy: str  # breadth-first, depth-first, hybrid

    # ===================
    # Search Output
    # ===================
    search_results: List[SearchResult]
    urls_attempted: int
    urls_success: int
    urls_failed: int

    # ===================
    # Analyst Output
    # ===================
    evidence_chain: List[Evidence]
    knowledge_graph: Dict[str, Any]  # Serialized graph representation
    entities_extracted: List[Dict[str, Any]]
    facts_extracted: List[Dict[str, Any]]

    # ===================
    # Verifier Output
    # ===================
    verification_results: List[VerificationResult]
    claims_total: int
    claims_supported: int
    claims_refuted: int
    claims_uncertain: int
    hallucination_rate: float

    # ===================
    # Critic Output
    # ===================
    gaps: List[Gap]
    quality_metrics: QualityMetrics
    needs_iteration: bool
    iteration_feedback: str

    # ===================
    # Synthesizer Output
    # ===================
    draft_report: str
    report_sections: Dict[str, str]
    citations: List[Dict[str, Any]]

    # ===================
    # Auditor Output (FIX 67)
    # ===================
    # FIX 67: These fields were missing from the TypedDict, causing LangGraph
    # to drop them during state merging. Without these definitions, the auditor's
    # 86% faithfulness score never reached finalize_node, resulting in CASE_3.
    audit_result: Dict[str, Any]  # Results from post-hoc verification
    post_hoc_faithfulness: float  # Measured faithfulness score (0.0-1.0)
    sentences_to_revise: List[Dict[str, Any]]  # Unfaithful sentences for revision
    auditor_revision_count: int  # Number of auditor revision loops completed

    # ===================
    # Citation Enrichment (FIX 107)
    # ===================
    # FIX 107: Post-verification citation enrichment to achieve SOTA density.
    # The enricher runs AFTER auditor verifies faithfulness >= 85%, adding
    # citations without modifying text. enrichment_citations tracks IDs for
    # the FIX 107B auditor bypass (skip atomic verification for these).
    enrichment_citations: List[str]  # Citation IDs added by enrichment pass
    enrichment_applied: bool  # Whether enrichment was applied
    enrichment_summary: Dict[str, Any]  # Stats: sentences_enriched, citations_added, etc.

    # ===================
    # Memory Context (FIX 68-70)
    # ===================
    # FIX 68: Memory fields for tri-level memory system integration
    # These enable the "snowball effect" where later vectors benefit from
    # prior research accumulated in LTM-Stage and LTM-Global.
    ltm_stage_context: List[Dict[str, Any]]  # Prior knowledge from LTM-Stage
    ltm_global_context: List[Dict[str, Any]]  # Prior knowledge from LTM-Global
    prior_knowledge_count: int  # Total LTM docs retrieved at vector start
    ltm_stage_promoted: int  # Chunks promoted to LTM-Stage after CASE_1
    ltm_global_promoted: int  # Docs promoted to LTM-Global after CASE_1
    memory_initialized: bool  # Flag indicating memory context was loaded

    # ===================
    # Reasoning Context (OpenAI o3 Parity)
    # ===================
    # These fields enable o3-style continuous reasoning with backtracking.
    # The reasoning_context stores the full serialized ReasoningContext state.
    reasoning_context: Dict[str, Any]  # Serialized ReasoningContext
    reasoning_backtrack_count: int  # Number of backtracks performed
    reasoning_current_branch: str  # Current reasoning branch identifier
    reasoning_dead_ends: List[str]  # Step IDs that led to dead ends

    # ===================
    # Final Output
    # ===================
    final_report: str
    final_word_count: int
    final_citation_count: int
    bibliography: List[Dict[str, Any]]  # FIX 80: Bound citation bibliography
    confidence_band: Literal["low", "medium", "high"]
    gating_case: Literal["CASE_1", "CASE_2", "CASE_3", "CASE_4"]
    # FIX-270: Must be declared or LangGraph drops it during state merging (same as FIX 67)
    perspective_coverage: Dict[str, Any]
    pipeline_faithfulness: float  # FIX-247: Immune faithfulness key
    quality_gates: Dict[str, Any]  # FIX-168: Word count + citation count gates
    citation_orphans: int  # FIX-183E: Count of orphan [N] refs stripped
    # FIX-285: Must be declared or LangGraph drops it during state merge (same as FIX 67/270)
    kimi_fallback_count: int  # Number of times KimiClient fell back to ChatFireworks
    # FIX-291: Must be declared or LangGraph drops it during state merge (same as FIX 67/270)
    iteration_summary: Dict[str, Any]  # Post-invoke iteration summary from graph.py

    # ===================
    # Cite-First Architecture (FIX 117)
    # ===================
    # FIX 117 T3: These fields MUST be declared in the TypedDict or LangGraph
    # will drop them during state merging (same root cause as FIX 67).
    citefirst_stats: Dict[str, Any]  # Synthesis stats: claims_generated, claims_grounded, etc.
    factscore: float  # FactScore-style atomic fraction (0.0-1.0)
    claim_evidence_map: List[Dict[str, Any]]  # Claim-to-evidence mapping for auditor passthrough
    ungroundable_claims: List[Dict[str, Any]]  # Claims that could not be grounded
    faithfulness_history: List[float]  # Per-iteration faithfulness for convergence detection
    convergence_detected: bool  # Whether convergence was detected in revision loop
    revision_stats: Dict[str, Any]  # Per-revision statistics from cite-first revision pass

    # ===================
    # Iteration Control
    # ===================
    iteration_count: int
    max_iterations: int
    converged: bool
    convergence_reason: str

    # ===================
    # Routing (Supervisor Decision)
    # ===================
    _next_agent: str  # Next agent to route to (search, analyst, verifier, etc.)
    _supervisor_reasoning: str  # Reasoning for the routing decision
    status: str  # Current workflow status

    # ===================
    # Metadata
    # ===================
    timestamps: Dict[str, str]
    agent_trace: List[Dict[str, Any]]  # Log of agent actions
    errors: List[Dict[str, Any]]


# =============================================================================
# State Factory Functions
# =============================================================================

def create_initial_state(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int,
    max_iterations: int = 5
) -> ResearchState:
    """
    Create an initial ResearchState for a new research task.

    Args:
        vector_id: Unique identifier for this research vector
        query: The research question to answer
        application: Product category (e.g., "Household_Water_Filter")
        region: Geographic scope (e.g., "NORTH_AMERICA")
        stage: Research stage (1-13)
        max_iterations: Maximum ReAct iterations

    Returns:
        Initialized ResearchState ready for processing
    """
    return ResearchState(
        # Input
        vector_id=vector_id,
        original_query=query,
        application=application,
        region=region,
        stage=stage,

        # Initialize empty collections
        sub_queries=[],
        search_results=[],
        evidence_chain=[],
        knowledge_graph={},
        entities_extracted=[],
        facts_extracted=[],
        verification_results=[],
        gaps=[],
        citations=[],
        report_sections={},
        agent_trace=[],
        errors=[],

        # Initialize counters
        iteration_count=0,
        max_iterations=max_iterations,
        claims_total=0,
        claims_supported=0,
        claims_refuted=0,
        claims_uncertain=0,
        urls_attempted=0,
        urls_success=0,
        urls_failed=0,

        # Initialize flags
        needs_iteration=True,
        converged=False,

        # Initialize metrics
        hallucination_rate=0.0,
        quality_metrics=QualityMetrics(),

        # FIX 68-70: Initialize memory context fields
        ltm_stage_context=[],
        ltm_global_context=[],
        prior_knowledge_count=0,
        ltm_stage_promoted=0,
        ltm_global_promoted=0,
        memory_initialized=False,

        # OpenAI o3 Parity: Initialize reasoning context fields
        reasoning_context={},
        reasoning_backtrack_count=0,
        reasoning_current_branch="main",
        reasoning_dead_ends=[],

        # FIX-292: Explicit initialization (defense-in-depth for FIX-285 state key)
        kimi_fallback_count=0,

        # Timestamps
        timestamps={
            "created": datetime.now(timezone.utc).isoformat(),
        }
    )


def serialize_state(state: ResearchState) -> Dict[str, Any]:
    """Serialize ResearchState to JSON-compatible dict for persistence."""
    result = dict(state)

    # Convert Pydantic models to dicts
    if "sub_queries" in result:
        result["sub_queries"] = [sq.model_dump() if hasattr(sq, "model_dump") else sq for sq in result["sub_queries"]]
    if "search_results" in result:
        result["search_results"] = [sr.model_dump() if hasattr(sr, "model_dump") else sr for sr in result["search_results"]]
    if "evidence_chain" in result:
        result["evidence_chain"] = [e.model_dump() if hasattr(e, "model_dump") else e for e in result["evidence_chain"]]
    if "gaps" in result:
        result["gaps"] = [g.model_dump() if hasattr(g, "model_dump") else g for g in result["gaps"]]
    if "verification_results" in result:
        result["verification_results"] = [v.model_dump() if hasattr(v, "model_dump") else v for v in result["verification_results"]]
    if "quality_metrics" in result and hasattr(result["quality_metrics"], "model_dump"):
        result["quality_metrics"] = result["quality_metrics"].model_dump()

    return result


def deserialize_state(data: Dict[str, Any]) -> ResearchState:
    """Deserialize JSON dict back to ResearchState."""
    # Convert dicts back to Pydantic models
    if "sub_queries" in data:
        data["sub_queries"] = [SubQuery(**sq) if isinstance(sq, dict) else sq for sq in data["sub_queries"]]
    if "search_results" in data:
        data["search_results"] = [SearchResult(**sr) if isinstance(sr, dict) else sr for sr in data["search_results"]]
    if "evidence_chain" in data:
        data["evidence_chain"] = [Evidence(**e) if isinstance(e, dict) else e for e in data["evidence_chain"]]
    if "gaps" in data:
        data["gaps"] = [Gap(**g) if isinstance(g, dict) else g for g in data["gaps"]]
    if "verification_results" in data:
        data["verification_results"] = [VerificationResult(**v) if isinstance(v, dict) else v for v in data["verification_results"]]
    if "quality_metrics" in data and isinstance(data["quality_metrics"], dict):
        data["quality_metrics"] = QualityMetrics(**data["quality_metrics"])

    return ResearchState(**data)
