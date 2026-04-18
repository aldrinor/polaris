"""
polaris graph state definition.

Clean TypedDict for LangGraph. Every field declared — no silent drops.
Maxed out for SOTA deep research quality.
"""

import os
from datetime import datetime, timezone
from typing import Any, Optional
from typing_extensions import TypedDict

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration — from .env, maxed out for deep research
# ---------------------------------------------------------------------------

# Search
QUERIES_PER_VECTOR = int(os.getenv("PG_QUERIES_PER_VECTOR", "50"))
WEB_RESULTS_PER_QUERY = int(os.getenv("PG_WEB_RESULTS_PER_QUERY", "20"))
ACADEMIC_RESULTS_PER_QUERY = int(os.getenv("PG_ACADEMIC_RESULTS_PER_QUERY", "10"))
WEB_CONCURRENCY = int(os.getenv("PG_WEB_CONCURRENCY", "20"))
ACADEMIC_CONCURRENCY = int(os.getenv("PG_ACADEMIC_CONCURRENCY", "1"))
MAX_SOURCES_TO_ANALYZE = int(os.getenv("PG_MAX_SOURCES_TO_ANALYZE", "300"))
MAX_ACADEMIC_PAGES = int(os.getenv("PG_MAX_ACADEMIC_PAGES", "5"))

# Quality gates
MIN_EVIDENCE_COUNT = int(os.getenv("PG_MIN_EVIDENCE_COUNT", "20"))
MIN_FAITHFULNESS = float(os.getenv("PG_MIN_FAITHFULNESS", "0.70"))
# W3.2: Iteration-decision threshold is stricter than the final quality gate.
# If faithfulness is between MIN_FAITHFULNESS and CONVERGENCE_MIN_FAITHFULNESS
# we keep iterating; the final gate still uses MIN_FAITHFULNESS.
CONVERGENCE_MIN_FAITHFULNESS = float(
    os.getenv("PG_CONVERGENCE_MIN_FAITHFULNESS", "0.80")
)
MAX_ITERATIONS = int(os.getenv("PG_MAX_ITERATIONS", "3"))
MAX_EXECUTION_MINUTES = int(os.getenv("PG_MAX_EXECUTION_MINUTES", "60"))

# Synthesis — maxed out
MAX_SECTIONS = int(os.getenv("PG_MAX_SECTIONS", "15"))
MAX_WORDS_PER_SECTION = int(os.getenv("PG_MAX_WORDS_PER_SECTION", "2000"))
# GEMINI-ARCH: MIN_TOTAL_WORDS set to 0 (advisory). Quality emerges from evidence
# density, not word count targets. Sections are as long as their evidence supports.
MIN_TOTAL_WORDS = int(os.getenv("PG_MIN_TOTAL_WORDS", "0"))
TARGET_TOTAL_WORDS = int(os.getenv("PG_TARGET_TOTAL_WORDS", "8000"))
MIN_CITATIONS = int(os.getenv("PG_MIN_CITATIONS", "30"))
MIN_UNIQUE_SOURCES = int(os.getenv("PG_MIN_UNIQUE_SOURCES", "8"))

# Verification — verify ALL claims, no sampling
VERIFY_ALL_CLAIMS = True
MIN_CLAIM_CONFIDENCE = float(os.getenv("PG_MIN_CLAIM_CONFIDENCE", "0.60"))

# STORM multi-perspective query planning (Change 1)
STORM_PERSPECTIVES = [
    "Scientific",
    "Regulatory",
    "Industry",
    "Economic",
    "Public_Health",
    "Historical",
    "Regional",
    "Methodological",
    "Emerging_Trends",
]
QUERIES_PER_PERSPECTIVE = int(os.getenv("PG_QUERIES_PER_PERSPECTIVE", "6"))

# Query amplification (Change 2)
PG_AMPLIFICATION_ENABLED = os.getenv("PG_AMPLIFICATION_ENABLED", "1") == "1"
PG_AMPLIFICATION_VARIANTS = int(os.getenv("PG_AMPLIFICATION_VARIANTS", "3"))

# Academic search caps (Change 4)
PG_ACADEMIC_QUERY_CAP = int(os.getenv("PG_ACADEMIC_QUERY_CAP", "50"))
PG_MAX_TOTAL_ACADEMIC = int(os.getenv("PG_MAX_TOTAL_ACADEMIC", "500"))

# Content pipeline (Change 3)
PG_MAX_CONTENT_LENGTH = int(os.getenv("PG_MAX_CONTENT_LENGTH", "30000"))
PG_CONTENT_PER_SOURCE = int(os.getenv("PG_CONTENT_PER_SOURCE", "25000"))
PG_MIN_CONTENT_LENGTH = int(os.getenv("PG_MIN_CONTENT_LENGTH", "200"))
PG_ANALYSIS_CONCURRENCY = int(os.getenv("PG_ANALYSIS_CONCURRENCY", "12"))
PG_ANALYSIS_BATCH_SIZE = int(os.getenv("PG_ANALYSIS_BATCH_SIZE", "1"))
PG_ANALYSIS_BATCH_TIMEOUT = float(os.getenv("PG_ANALYSIS_BATCH_TIMEOUT", "240.0"))
PG_FETCH_CONCURRENCY = int(os.getenv("PG_FETCH_CONCURRENCY", "5"))

# Verification/synthesis concurrency (Change 4)
PG_VERIFY_BATCH_SIZE = int(os.getenv("PG_VERIFY_BATCH_SIZE", "10"))
PG_VERIFY_CONCURRENCY = int(os.getenv("PG_VERIFY_CONCURRENCY", "20"))
PG_VERIFY_GATHER_TIMEOUT = int(os.getenv("PG_VERIFY_GATHER_TIMEOUT", "1800"))
PG_SECTION_WRITE_CONCURRENCY = int(os.getenv("PG_SECTION_WRITE_CONCURRENCY", "1"))
# GEMINI-ARCH: Qwen3.5-Plus supports 65K output. 16384 gives rich sections
# with tables + charts + key findings without truncation.
PG_SECTION_WRITER_MAX_TOKENS = int(os.getenv("PG_SECTION_WRITER_MAX_TOKENS", "16384"))
# FIX-C5: Secondary token budget for continuation/correction calls
# GEMINI-ARCH: Increased from 4096 to 8192 for Qwen3.5-Plus capacity.
PG_SECTION_CONTINUATION_MAX_TOKENS = int(os.getenv("PG_SECTION_CONTINUATION_MAX_TOKENS", "8192"))

# FIX-QM12: Separate token budget for synthesis structured calls (ClusterPlan,
# ReportOutline, GapAnalysis). These use reasoning_enabled=True which consumes
# ~6000 tokens for CoT, leaving only ~2000 for JSON at 8192. 16384 gives room.
PG_SYNTHESIS_STRUCTURED_MAX_TOKENS = int(os.getenv("PG_SYNTHESIS_STRUCTURED_MAX_TOKENS", "16384"))

# Evidence deduplication (Change 5)
PG_EVIDENCE_DEDUP_ENABLED = os.getenv("PG_EVIDENCE_DEDUP_ENABLED", "1") == "1"
PG_EVIDENCE_DEDUP_THRESHOLD = float(os.getenv("PG_EVIDENCE_DEDUP_THRESHOLD", "0.85"))

# FIX-306: Citation chasing (snowball search)
PG_CITATION_CHASE_ENABLED = os.getenv("PG_CITATION_CHASE_ENABLED", "1") == "1"
PG_CITATION_CHASE_MAX = int(os.getenv("PG_CITATION_CHASE_MAX", "10"))

# FIX-301: Strict verification toggle
PG_STRICT_VERIFICATION = os.getenv("PG_STRICT_VERIFICATION", "1") == "1"

# IMP-1: Verifier content cap (pass source content for real verification)
PG_VERIFIER_CONTENT_CAP = int(os.getenv("PG_VERIFIER_CONTENT_CAP", "25000"))

# BUG-092: Cross-source NLI pair cap. Prevents O(n^2) scaling by selecting
# top-N pairs by relevance score. At 33 pairs = 1380s; default 50 keeps
# cross-source verification under ~2100s while covering highest-relevance pairs.
PG_MAX_CROSS_SOURCE_PAIRS = int(os.getenv("PG_MAX_CROSS_SOURCE_PAIRS", "50"))

# BUG-092: Triangulation / corroboration / contradiction O(n^2) scaling caps.
# Cap evidence pool before O(n^2) Jaccard loops. Sorted by tier+relevance, top N.
PG_MAX_TRIANGULATE_EVIDENCE = int(os.getenv("PG_MAX_TRIANGULATE_EVIDENCE", "500"))
PG_MAX_CORROBORATION_EVIDENCE = int(os.getenv("PG_MAX_CORROBORATION_EVIDENCE", "500"))
PG_MAX_CONTRADICTION_PAIRS = int(os.getenv("PG_MAX_CONTRADICTION_PAIRS", "1000"))

# IMP-3: Citation chase relevance filter (embedding similarity threshold)
PG_CITATION_CHASE_MIN_RELEVANCE = float(os.getenv("PG_CITATION_CHASE_MIN_RELEVANCE", "0.3"))

# FIX-045H: Multi-evidence corroboration
PG_CORROBORATION_ENABLED = os.getenv("PG_CORROBORATION_ENABLED", "1") == "1"
PG_CORROBORATION_MAX_PER_CLAIM = int(os.getenv("PG_CORROBORATION_MAX_PER_CLAIM", "5"))
PG_CORROBORATION_JACCARD_THRESHOLD = float(os.getenv("PG_CORROBORATION_JACCARD_THRESHOLD", "0.35"))

# FIX-D: Substance-based quality gate — citation spread per section
PG_MIN_CITATIONS_PER_SECTION = int(os.getenv("PG_MIN_CITATIONS_PER_SECTION", "2"))

# FIX-D: Substance-based quality gate — evidence utilization floor
PG_MIN_EVIDENCE_UTILIZATION = float(os.getenv("PG_MIN_EVIDENCE_UTILIZATION", "0.40"))

# FIX-310: Post-synthesis quality gate (max expansion passes, 0=disabled)
PG_SYNTHESIS_MAX_EXPANSION_PASSES = int(os.getenv("PG_SYNTHESIS_MAX_EXPANSION_PASSES", "2"))

# OBS-1: Pipeline tracing (1=enabled, 0=disabled)
PG_TRACING_ENABLED = os.getenv("PG_TRACING_ENABLED", "1") == "1"

# FETCH-1: Prefer markdown content negotiation (1=enabled, 0=disabled)
PG_PREFER_MARKDOWN = os.getenv("PG_PREFER_MARKDOWN", "1") == "1"

# SOTA Sprint: Source quality controls
PG_SOURCE_AUTHORITY_ENABLED = os.getenv("PG_SOURCE_AUTHORITY_ENABLED", "1") == "1"
# HONEST-REBUILD Phase 2d: raise off-topic threshold 0.15 -> 0.35.
# PG_LB_SA_02_CONTENT_AUDIT Section E-03 found that threshold=0.15 let
# evidence with near-zero semantic similarity to the research question
# leak into the synthesis corpus. The legacy "risk-axis retain below
# threshold" path pinned the floor at 0.15 even when the main filter
# was raised, which defeated every tightening attempt. Phase 2d raises
# the main threshold to 0.35 AND the risk-axis floor to 0.20 so risk
# evidence must still be at least weakly on-topic.
PG_OFFTOPIC_THRESHOLD = float(os.getenv("PG_OFFTOPIC_THRESHOLD", "0.35"))
PG_OFFTOPIC_RISK_FLOOR = float(os.getenv("PG_OFFTOPIC_RISK_FLOOR", "0.20"))
# Pre-fetch filter: when we have search-result snippets but haven't
# fetched full content yet, a looser threshold is appropriate because
# snippets are short. Still tighter than the legacy 0.15.
PG_OFFTOPIC_PREFETCH_THRESHOLD = float(
    os.getenv("PG_OFFTOPIC_PREFETCH_THRESHOLD", "0.25")
)
PG_MIN_PEER_REVIEWED_PCT = float(os.getenv("PG_MIN_PEER_REVIEWED_PCT", "0.30"))

# SOTA Sprint: Jina Reader + Firecrawl fetch (D1/D2)
PG_JINA_ENABLED = os.getenv("PG_JINA_ENABLED", "1") == "1"
PG_FIRECRAWL_ENABLED = os.getenv("PG_FIRECRAWL_ENABLED", "1") == "1"

# SOTA Sprint: Exa neural search (A5)
PG_EXA_ENABLED = os.getenv("PG_EXA_ENABLED", "1") == "1"

# Exa API production config (FIX-A5 overhaul)
PG_EXA_QUERIES_PER_VECTOR = int(os.getenv("PG_EXA_QUERIES_PER_VECTOR", "5"))
PG_EXA_RESULTS_PER_QUERY = int(os.getenv("PG_EXA_RESULTS_PER_QUERY", "10"))
PG_EXA_SEARCH_TYPE = os.getenv("PG_EXA_SEARCH_TYPE", "auto")
PG_EXA_CATEGORY = os.getenv("PG_EXA_CATEGORY", "research paper")
PG_EXA_EXCLUDE_DOMAINS = [
    d.strip()
    for d in os.getenv(
        "PG_EXA_EXCLUDE_DOMAINS",
        "pinterest.com,quora.com,reddit.com,facebook.com,twitter.com",
    ).split(",")
    if d.strip()
]
PG_EXA_HIGHLIGHTS_SENTENCES = int(os.getenv("PG_EXA_HIGHLIGHTS_SENTENCES", "2"))
PG_EXA_HIGHLIGHTS_PER_URL = int(os.getenv("PG_EXA_HIGHLIGHTS_PER_URL", "2"))
PG_EXA_BUDGET_USD = float(os.getenv("PG_EXA_BUDGET_USD", "20.0"))
PG_EXA_COST_PER_SEARCH = float(os.getenv("PG_EXA_COST_PER_SEARCH", "0.005"))
PG_EXA_COST_PER_CONTENT = float(os.getenv("PG_EXA_COST_PER_CONTENT", "0.001"))

# Firecrawl free-plan hardening
FIRECRAWL_MIN_INTERVAL_SECONDS = float(os.getenv("FIRECRAWL_MIN_INTERVAL_SECONDS", "6.0"))
FIRECRAWL_MONTHLY_QUOTA = int(os.getenv("FIRECRAWL_MONTHLY_QUOTA", "500"))
FIRECRAWL_WARN_THRESHOLD_PCT = float(os.getenv("FIRECRAWL_WARN_THRESHOLD_PCT", "0.80"))

# Adaptive search rounds (Serper STORM/Gemini-style)
PG_ADAPTIVE_SEARCH_ENABLED = os.getenv("PG_ADAPTIVE_SEARCH_ENABLED", "1") == "1"
PG_SEARCH_ROUNDS = int(os.getenv("PG_SEARCH_ROUNDS", "3"))
PG_INITIAL_QUERY_PCT = float(os.getenv("PG_INITIAL_QUERY_PCT", "0.30"))
PG_REFINEMENT_QUERIES = int(os.getenv("PG_REFINEMENT_QUERIES", "10"))
PG_REFINER_MAX_TOKENS = int(os.getenv("PG_REFINER_MAX_TOKENS", "4096"))

# Agentic search loop (Gemini-style deep research)
PG_AGENTIC_SEARCH_ENABLED = os.getenv("PG_AGENTIC_SEARCH_ENABLED", "0") == "1"
PG_AGENTIC_MAX_ROUNDS = int(os.getenv("PG_AGENTIC_MAX_ROUNDS", "12"))
PG_AGENTIC_MAX_QUERIES = int(os.getenv("PG_AGENTIC_MAX_QUERIES", "160"))
PG_AGENTIC_MAX_TIME_SECONDS = int(os.getenv("PG_AGENTIC_MAX_TIME_SECONDS", "1800"))
PG_AGENTIC_SEED_QUERIES = int(os.getenv("PG_AGENTIC_SEED_QUERIES", "9"))
PG_AGENTIC_QUERIES_PER_ROUND = int(os.getenv("PG_AGENTIC_QUERIES_PER_ROUND", "8"))
PG_AGENTIC_WEB_PER_ROUND = int(os.getenv("PG_WEB_PER_ROUND", "6"))
PG_AGENTIC_ACADEMIC_PER_ROUND = int(os.getenv("PG_AGENTIC_ACADEMIC_PER_ROUND", "2"))
PG_AGENTIC_EXA_PER_ROUND = int(os.getenv("PG_AGENTIC_EXA_PER_ROUND", "1"))
PG_AGENTIC_CONVERGENCE_URL_OVERLAP = float(os.getenv("PG_AGENTIC_CONVERGENCE_URL_OVERLAP", "0.40"))
PG_AGENTIC_CONVERGENCE_THEME_SATURATION = float(os.getenv("PG_AGENTIC_CONVERGENCE_THEME_SATURATION", "0.80"))
PG_AGENTIC_CONVERGENCE_WINDOW = int(os.getenv("PG_AGENTIC_CONVERGENCE_WINDOW", "3"))
PG_AGENTIC_MIN_ROUNDS = int(os.getenv("PG_AGENTIC_MIN_ROUNDS", "5"))
PG_AGENTIC_REFINER_MAX_TOKENS = int(os.getenv("PG_AGENTIC_REFINER_MAX_TOKENS", "4096"))

# Agentic search Phase 2: Content-aware search
PG_AGENTIC_CONTENT_READING_ENABLED = os.getenv("PG_AGENTIC_CONTENT_READING_ENABLED", "1") == "1"
PG_AGENTIC_PAGES_PER_ROUND = int(os.getenv("PG_AGENTIC_PAGES_PER_ROUND", "3"))
PG_AGENTIC_FETCH_TIMEOUT = float(os.getenv("PG_AGENTIC_FETCH_TIMEOUT", "15.0"))
PG_AGENTIC_PAGE_CONTENT_CAP = int(os.getenv("PG_AGENTIC_PAGE_CONTENT_CAP", "5000"))
PG_AGENTIC_SUMMARY_MAX_TOKENS = int(os.getenv("PG_AGENTIC_SUMMARY_MAX_TOKENS", "2048"))
PG_AGENTIC_MAX_NOTEBOOK_ENTRIES = int(os.getenv("PG_AGENTIC_MAX_NOTEBOOK_ENTRIES", "30"))
PG_AGENTIC_KNOWLEDGE_SATURATION_PAGES = int(os.getenv("PG_AGENTIC_KNOWLEDGE_SATURATION_PAGES", "15"))
PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND = int(os.getenv("PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND", "1"))
PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT = int(os.getenv("PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT", "3"))
# FIX-055: Per-call timeout for LLM analysis in agentic loop (prevents hung HTTP).
# BUG-090: LLM sometimes returns prose instead of JSON for AgenticRoundAnalysis.
# Increased from 120s to 300s to give structured output more time.
PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS", "300"))

# AREA-2: Paywall domain fetch blocklist (don't attempt fetch, use snippet)
PG_PAYWALL_DOMAINS = frozenset(
    d.strip()
    for d in os.getenv(
        "PG_PAYWALL_DOMAINS",
        "sciencedirect.com,springer.com,wiley.com,acm.org,tandfonline.com,"
        "ieee.org,sagepub.com,emerald.com,degruyter.com,cambridge.org",
    ).split(",")
    if d.strip()
)
PG_MIN_CONTENT_LENGTH_ACADEMIC = int(os.getenv("PG_MIN_CONTENT_LENGTH_ACADEMIC", "100"))

# AREA-8: Budget guard — skip expensive nodes when budget low
PG_BUDGET_GUARD_USD = float(os.getenv("PG_BUDGET_GUARD_USD", "150.0"))

# AREA-4: Per-section evidence filtering top-k
# GEMINI-ARCH: Qwen3.5-Plus 1M context fits 100 evidence pieces (~50K tokens)
# easily. More evidence = better citation decisions by the model.
PG_SECTION_EVIDENCE_TOP_K = int(os.getenv("PG_SECTION_EVIDENCE_TOP_K", "100"))

# TIER-3 Stage 3: Token-budget-aware evidence selection
PG_SECTION_TOKEN_BUDGET = int(os.getenv("PG_SECTION_TOKEN_BUDGET", "6000"))
PG_EVIDENCE_FORMAT_TOP_FULL = int(os.getenv("PG_EVIDENCE_FORMAT_TOP_FULL", "3"))
PG_EVIDENCE_CANDIDATE_POOL = int(os.getenv("PG_EVIDENCE_CANDIDATE_POOL", "100"))


# ---------------------------------------------------------------------------
# Evidence types
# ---------------------------------------------------------------------------

class EvidencePiece(TypedDict):
    """Single piece of evidence extracted from a source."""

    evidence_id: str
    source_url: str
    source_title: str
    source_type: str  # "web", "academic", "pdf"
    direct_quote: str
    statement: str
    fact_category: str
    relevance_score: float
    llm_relevance_score: Optional[float]  # IMP-2: Original LLM-assigned score (preserved for debugging)
    quality_tier: str  # "GOLD", "SILVER", "BRONZE"
    citation_key: str  # For bibliography
    year: Optional[int]
    authors: Optional[list[str]]
    venue: Optional[str]
    doi: Optional[str]
    perspective: Optional[str]  # FIX-303: STORM perspective tag
    corroborating_sources: Optional[int]  # FIX-S2: count of independent sources with similar claims
    source_confidence: float  # SOTA-11: Composite confidence score (0.0-1.0)
    nli_self_check_score: Optional[float]  # FIX-051: NLI verification score (0.0-1.0), set by verify node
    quote_substance: Optional[float]  # FIX-051: Quote content density (0.0-1.0), set by analyzer
    tier_composite_score: Optional[float]  # FIX-051: K-signal composite score, set by analyzer
    quote_char_start: Optional[int]  # A1.3: Character offset where direct_quote begins in source content
    quote_char_end: Optional[int]  # A1.3: Character offset where direct_quote ends in source content
    # RC-1 (v3 Hybrid): Evidence card metadata (populated by post-extraction enrichment)
    methodology: Optional[str]  # How the finding was obtained
    conditions: Optional[str]  # Experimental/study parameters
    limitations: Optional[str]  # Known limitations of this finding
    strength_signals: Optional[list[str]]  # "peer_reviewed", "large_sample", "replicated"
    comparable_metrics: Optional[list[dict]]  # [{metric_name, value, unit, condition, entity}]


class VerifiedClaim(TypedDict):
    """A claim that has been verified against evidence."""

    claim_id: str
    statement: str
    evidence_ids: list[str]
    confidence: float
    verification_method: str  # "atomic", "partial", "not_supported", "api_error"
    is_faithful: Optional[bool]  # None = unverified (api_error), not unfaithful
    section_id: Optional[str]
    reasoning: str  # FIX-B2: LLM's verification reasoning
    verification_basis: str  # FIX-B2: "content", "quote_only", "title_only"
    verification_type: str  # FIX-047-K4: "extraction_self_check" or "independent_cross_source"
    nli_score: Optional[float]  # FIX-051c: NLI probability (0.0-1.0), set by nli_verifier
    cross_source_score: Optional[float]  # FIX-051c: Independent cross-source NLI score
    verdict: str  # FIX-B4: Human-readable verdict ("SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "NO_VERDICT")
    source_url: str  # FIX-B5: URL of the source that was verified against
    direct_quote: str  # FIX-B5: The direct quote from evidence used for verification


class SectionOutline(TypedDict):
    """Outline for a report section."""

    section_id: str
    title: str
    description: str
    search_keywords: str  # Fix R2-#5: domain-specific routing keywords for blueprint
    evidence_ids: list[str]
    target_words: int
    order: int


class ReportSection(TypedDict):
    """A completed report section."""

    section_id: str
    title: str
    content: str
    word_count: int
    citation_ids: list[str]
    evidence_ids: list[str]


# ---------------------------------------------------------------------------
# v2 State Reducers (Fix R5-#1 — State Reducer Race Condition)
# ---------------------------------------------------------------------------
#
# When LangGraph runs 15 parallel Section Writer nodes via `Send`, their
# outputs are aggregated using "reducer" functions. If we use the default
# list reducer (operator.add) for sections, a downstream verifier rewrite
# of Section 3 will APPEND a second copy instead of overwriting the original.
# Result: 16 sections, two Section 3s, self-contradictory report.
#
# Fix: Use a dict[str, ReportSection] keyed by section_id with a merge
# reducer. Verifier rewrites cleanly overwrite the existing entry.
#
# Usage in v2 graph StateGraph:
#     from typing import Annotated
#     class ResearchStateV2(TypedDict):
#         completed_sections: Annotated[
#             dict[str, ReportSection], merge_sections_reducer
#         ]
# ---------------------------------------------------------------------------

def merge_sections_reducer(
    existing: dict[str, "ReportSection"],
    update: dict[str, "ReportSection"],
) -> dict[str, "ReportSection"]:
    """Merge section dicts — updates overwrite existing entries by section_id.

    Fix R5-#1: Safe for both parallel section writers (initial write) and
    sequential verifier rewrites (overwrite). Never duplicates sections.

    Args:
        existing: Current sections in state (may be empty on first call).
        update: New or rewritten sections from a node.

    Returns:
        Merged dict with all sections.
    """
    merged = dict(existing) if existing else {}
    if update:
        merged.update(update)
    return merged


def merge_evidence_reducer(
    existing: list[dict[str, Any]],
    update: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge evidence lists, deduplicating by evidence_id.

    Prevents duplicate evidence when multiple search iterations add
    overlapping results.
    """
    if not update:
        return existing or []
    if not existing:
        return list(update)

    seen_ids = {e.get("evidence_id") for e in existing}
    merged = list(existing)
    for ev in update:
        ev_id = ev.get("evidence_id")
        if ev_id not in seen_ids:
            merged.append(ev)
            seen_ids.add(ev_id)
    return merged


def replace_reducer(existing: Any, update: Any) -> Any:
    """Simple replacement reducer — latest value wins.

    Use for fields like final_report, draft_report, quality_metrics
    where the latest node output completely replaces the previous value.
    """
    return update if update is not None else existing


class BibliographyEntry(TypedDict):
    """A single bibliography entry."""

    citation_key: str
    formatted: str  # Full APA/Chicago citation string
    citation_number: int  # FIX-B6: Numeric citation number for cross-referencing
    url: str
    title: str  # FIX-FORMAT-2: Separate title field for audit D6 scoring
    source_type: str
    evidence_ids: list[str]


class QualityMetrics(TypedDict):
    """Quality metrics for the research output."""

    total_evidence: int
    gold_evidence: int
    silver_evidence: int
    total_claims: int
    verified_claims: int
    faithfulness_score: float
    total_words: int
    total_sections: int
    total_citations: int
    unique_sources: int
    coverage_score: float  # How well evidence covers the query
    coherence_score: float  # Inter-section coherence


# ---------------------------------------------------------------------------
# Graph State — every field declared, LangGraph won't drop any
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    """
    Complete state for the polaris graph pipeline.

    Every field MUST be declared here. LangGraph silently drops
    undeclared keys during state merging.
    """

    # Identity
    vector_id: str
    original_query: str
    application: str
    region: str
    stage: int

    # Search planning
    sub_queries: list[str]
    search_strategy: str  # "broad", "deep", "academic_focus"
    perspective_distribution: dict[str, int]  # STORM: queries per perspective

    # Raw search results
    web_results: list[dict[str, Any]]
    academic_results: list[dict[str, Any]]
    fetched_content: list[dict[str, Any]]

    # Evidence (extracted and quality-scored)
    evidence: list[EvidencePiece]
    evidence_clusters: list[dict[str, Any]]

    # Verification
    claims: list[VerifiedClaim]
    faithfulness_score: float

    # Gaps identified
    gaps: list[str]
    gap_queries: list[str]  # Additional queries to fill gaps

    # Synthesis
    section_outline: list[SectionOutline]
    sections: list[ReportSection]                        # v1: list-based (single synthesize node)
    completed_sections: dict[str, ReportSection]         # v2 (Fix R5-#1): dict-based for parallel writers
    bibliography: list[BibliographyEntry]
    evidence_chain: list[dict[str, Any]]  # Audit-compatible evidence with perspectives
    draft_report: str  # RAGAS-FIX: Pre-citation-resolution report with [CITE:ev_xxx] tokens
    final_report: str

    # Quality
    quality_metrics: Optional[QualityMetrics]

    # Iteration control
    iteration_count: int
    max_iterations: int
    max_execution_minutes: int
    needs_iteration: bool
    converged: bool
    convergence_reason: Optional[str]

    # Pipeline status
    status: str  # "planning", "searching", "analyzing", "verifying", "synthesizing", "complete", "failed"
    error: Optional[str]
    timestamps: dict[str, str]

    # LLM usage tracking
    llm_usage: dict[str, Any]

    # FIX-310: Quality gate
    expansion_passes_used: int
    quality_gate_result: str  # "passed", "expanded", "below_minimum"

    # OBS-1: Pipeline tracing
    trace_summary: dict[str, Any]

    # Agentic search loop state
    agentic_search_rounds: int
    agentic_total_queries: int
    agentic_convergence_scores: list[dict[str, Any]]
    agentic_url_accumulator: list[str]
    agentic_perspective_coverage: dict[str, int]

    # Agentic Phase 2: Content-aware search state
    agentic_research_notebook: list[dict[str, Any]]
    agentic_pages_fetched_count: int
    agentic_knowledge_gaps: list[str]

    # AREA-3: STORM interview state
    storm_conversations: list[dict[str, Any]]
    storm_outline: list[dict[str, Any]]

    # AREA-4: Per-section evidence filtering metadata
    section_evidence_map: dict[str, list[str]]

    # AREA-5: Memory system metadata
    content_cache_hits: int
    search_cache_hits: int

    # SOTA-12: Cross-reference groups (embedding-based corroboration)
    cross_reference_groups: list  # [{evidence_ids: [...], agreement_score: float}, ...]

    # ARCH-5: Token-level hallucination detection results
    hallucination_audit: list  # [{section_id, title, hallucination_ratio, needs_rewrite}, ...]

    # MoST: Molecular Structure of Thought metadata
    most_reflection_stats: dict[str, Any]  # {contradictions_found, redundancies_removed, cross_refs_added}
    most_exploration_stats: dict[str, Any]  # {unused_count, redistributed, sections_enriched}
    most_bond_analysis: dict[str, Any]  # M-19: {covalent: {stats}, ionic: {stats}, disulfide: {stats}, peptide: {stats}}

    # Memory system metadata (expanded)
    memory_perspective_gaps: list[str]
    memory_best_strategies: list[dict]
    memory_ltm_prior_count: int
    memory_ltm_priors: list[dict]  # Sprint 1B: actual LTM prior knowledge items
    uploaded_documents: list[dict]  # A7.2: [{doc_id, filename, content_preview, chunk_count}]

    # A5: Smart art diagrams (Mermaid.js code per section)
    smart_art_diagrams: dict[str, str]  # {section_id: mermaid_code_string}

    # GEMINI-ARCH: Structured data points extracted during analysis (for tables/charts)
    structured_data: list[dict[str, Any]]

    # Campaign Control Center: domain context injected into planner
    research_brief: str

    # RC-3 (v3 Hybrid): Question-driven report planning
    question_decomposition: list[dict]

    # RC-7 (v3 Hybrid): Perspective diversity tracking
    perspective_entropy: float

    # Evidence deepening loop (closes Gemini/ChatGPT gap)
    deepened_papers: list[dict[str, Any]]  # Papers found by deepener
    deepener_stats: dict[str, Any]  # Deepening operation statistics


def create_initial_state(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int = 1,
    max_iterations: int = MAX_ITERATIONS,
    max_execution_minutes: int = MAX_EXECUTION_MINUTES,
) -> ResearchState:
    """Create a fresh initial state with all fields initialized."""
    now = datetime.now(timezone.utc).isoformat()
    return ResearchState(
        # Identity
        vector_id=vector_id,
        original_query=query,
        application=application,
        region=region,
        stage=stage,
        # Search planning
        sub_queries=[],
        search_strategy="broad",
        perspective_distribution={},
        # Raw results
        web_results=[],
        academic_results=[],
        fetched_content=[],
        # Evidence
        evidence=[],
        evidence_clusters=[],
        # Verification — SF-31: sentinel -1.0 = "not computed" (distinct from "all unfaithful")
        claims=[],
        faithfulness_score=-1.0,
        # Gaps
        gaps=[],
        gap_queries=[],
        # Synthesis
        section_outline=[],
        sections=[],
        completed_sections={},  # v2 (Fix R5-#1): dict-based for parallel writers
        bibliography=[],
        evidence_chain=[],  # SF-57: Initialize evidence_chain to prevent KeyError
        draft_report="",  # RAGAS-FIX: Pre-citation-resolution report
        final_report="",
        # Quality
        quality_metrics=None,
        # Iteration
        iteration_count=0,
        max_iterations=max_iterations,
        max_execution_minutes=max_execution_minutes,
        needs_iteration=True,
        converged=False,
        convergence_reason=None,
        # Status
        status="planning",
        error=None,
        timestamps={"created": now},
        # LLM usage
        llm_usage={},
        # FIX-310: Quality gate
        expansion_passes_used=0,
        quality_gate_result="pending",
        # OBS-1: Pipeline tracing
        trace_summary={},
        # Agentic search loop
        agentic_search_rounds=0,
        agentic_total_queries=0,
        agentic_convergence_scores=[],
        agentic_url_accumulator=[],
        agentic_perspective_coverage={},
        # Agentic Phase 2: Content-aware search
        agentic_research_notebook=[],
        agentic_pages_fetched_count=0,
        agentic_knowledge_gaps=[],
        # AREA-3: STORM interview state
        storm_conversations=[],
        storm_outline=[],
        # AREA-4: Per-section evidence filtering
        section_evidence_map={},
        # AREA-5: Memory system
        content_cache_hits=0,
        search_cache_hits=0,
        # SOTA-12: Cross-reference groups
        cross_reference_groups=[],
        # ARCH-5: Hallucination detection results
        hallucination_audit=[],
        # MoST: Molecular Structure of Thought
        most_reflection_stats={},
        most_exploration_stats={},
        most_bond_analysis={},
        # Memory system metadata (expanded)
        memory_perspective_gaps=[],
        memory_best_strategies=[],
        memory_ltm_prior_count=0,
        memory_ltm_priors=[],
        uploaded_documents=[],
        # A5: Smart art diagrams
        smart_art_diagrams={},
        # GEMINI-ARCH: Structured data points
        structured_data=[],
        # Campaign Control Center: research brief
        research_brief="",
        # RC-3 (v3 Hybrid): Question-driven report planning
        question_decomposition=[],
        # RC-7 (v3 Hybrid): Perspective diversity tracking
        perspective_entropy=0.0,
        # Evidence deepening loop
        deepened_papers=[],
        deepener_stats={},
    )
