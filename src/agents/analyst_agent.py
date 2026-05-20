"""
POLARIS v3 Analyst Agent

Extracts structured information from search results:
- Entity extraction (NER)
- Fact extraction
- Claim identification
- Evidence chain building
- Geographic relevance filtering (BUG-008 FIX)

Uses LLM for intelligent extraction with Pydantic validation.
GPU-accelerated for embeddings and NLI operations.
Depth configuration loaded from .env via DepthConfig (LAW VI: Zero hard-coding).
"""

import logging
import hashlib
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Set
from datetime import datetime, timezone

import yaml
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, SearchResult, Evidence, AtomicFact
try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived
try:
    from src.depth.gpu_config import get_gpu_config, ensure_gpu_memory
except ImportError:
    get_gpu_config = None
    ensure_gpu_memory = None

# v4 Architecture: Import pure functions from functions module
from src.functions.relevance_filter import (
    check_geographic_relevance,
    calculate_source_quality,
    detect_metadata,
    validate_author_field,
    normalize_url_domain,
)
from src.functions.quality_scoring import classify_quality_tier, QualityTier
from src.config.thresholds import get_threshold
from src.orchestration.persistence import save_state

# SOTA Integration: New module imports (Task #21)
from src.utils.content_deduplicator import ContentDeduplicator, DeduplicationConfig
from src.quality import BiasDetector, BiasConfig


logger = logging.getLogger(__name__)


# =============================================================================
# P3.1 GAP FIX: Load Extraction Config
# =============================================================================

def _load_extraction_config() -> dict:
    """
    P3.1 GAP FIX: Load extraction limits from config/settings/extraction.yaml.

    This ensures the extraction limits defined in the config are actually used.
    """
    from pathlib import Path
    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "settings" / "extraction.yaml"

    default_config = {
        "extraction": {
            "entities_per_source": 5,
            "facts_per_source": 10,
            "claims_per_source": 5,
        },
        "content": {
            "max_content_per_source": 8000,
            "max_snippet_length": 500,
        },
        "quality": {
            "min_entity_confidence": 0.6,
            "min_fact_confidence": 0.5,
        }
    }

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    # Merge with defaults
                    for key in loaded:
                        if key in default_config and isinstance(default_config[key], dict):
                            default_config[key].update(loaded[key])
                        else:
                            default_config[key] = loaded[key]
                    logger.debug(f"[P3.1] Loaded extraction config from {config_path}")
        except Exception as e:
            logger.warning(f"[P3.1] Failed to load extraction config: {e}, using defaults")

    return default_config


# Load extraction config at module level
_EXTRACTION_CONFIG = _load_extraction_config()


# =============================================================================
# W3.1 SOTA: Multi-Pass Source Analysis Configuration
# =============================================================================

def _load_multi_pass_config() -> dict:
    """
    W3.1 SOTA: Load multi-pass analysis configuration.

    SOTA systems revisit sources multiple times, extracting different
    information on each pass. This enables deeper evidence extraction.
    """
    from src.config.thresholds import get_threshold

    return {
        "enabled": get_threshold("multi_pass_analysis.enabled", True),
        "max_passes": get_threshold("multi_pass_analysis.max_passes", 2),
        "min_quality_for_pass_2": get_threshold(
            "multi_pass_analysis.pass_2.min_quality_for_pass_2", 0.70
        ),
        "evidence_per_pass": get_threshold("multi_pass_analysis.evidence_per_pass", 15),
        "combine_strategy": get_threshold("multi_pass_analysis.combine_strategy", "merge_dedupe"),
    }


# Load multi-pass config at module level
_MULTI_PASS_CONFIG = _load_multi_pass_config()


def should_perform_second_pass(source_quality: float) -> bool:
    """
    W3.1 SOTA: Determine if source should undergo second extraction pass.

    Only high-quality sources warrant the additional LLM cost of
    multi-pass extraction.
    """
    if not _MULTI_PASS_CONFIG.get("enabled", True):
        return False

    min_quality = _MULTI_PASS_CONFIG.get("min_quality_for_pass_2", 0.70)
    return source_quality >= min_quality


def merge_extraction_results(
    pass_1_results: List[dict],
    pass_2_results: List[dict],
    strategy: str = "merge_dedupe"
) -> List[dict]:
    """
    W3.1 SOTA: Merge results from multiple extraction passes.

    Strategies:
    - merge_dedupe: Combine all results, remove duplicates by content hash
    - prefer_pass_2: Use pass 2 results, fill gaps from pass 1
    - weighted: Weight results based on pass confidence
    """
    if not pass_2_results:
        return pass_1_results

    if strategy == "merge_dedupe":
        seen_hashes = set()
        merged = []

        # Process all results, prefer pass_2 (usually more detailed)
        for result in pass_2_results + pass_1_results:
            # Create content hash for deduplication
            content = result.get("text", "") or result.get("content", "")
            content_hash = hashlib.md5(content[:200].encode()).hexdigest()[:12]

            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                merged.append(result)

        return merged

    elif strategy == "prefer_pass_2":
        # Use pass 2 if available, otherwise pass 1
        return pass_2_results if pass_2_results else pass_1_results

    else:
        # Default: simple concatenation
        return pass_1_results + pass_2_results


# =============================================================================
# P1.1 FIX: Pre-LLM Keyword Relevance Filter
# =============================================================================

def extract_topic_keywords(query: str, min_length: int = 3) -> List[str]:
    """
    Extract keywords from research query for relevance filtering.

    P1.1 FIX: Fast O(1) keyword filter before expensive LLM calls.
    P1.1 GAP FIX: Added domain-specific keyword enhancement.
    See deployment_plan_20260126.md
    """
    # Basic word extraction
    words = query.lower().split()
    keywords = [w.strip('.,!?()[]{}') for w in words if len(w) > min_length]

    # Filter out common stop words
    stop_words = {'what', 'when', 'where', 'which', 'would', 'could', 'should',
                  'about', 'from', 'into', 'with', 'have', 'been', 'this', 'that',
                  'these', 'those', 'their', 'there', 'they', 'will', 'more', 'most',
                  'some', 'such', 'than', 'them', 'then', 'only', 'other', 'also'}
    keywords = [k for k in keywords if k not in stop_words]

    # P1.1 GAP FIX: Add domain-specific keywords based on detected domain
    # This prevents garbage results that don't match the research domain
    domain_keywords = _detect_domain_keywords(query)
    keywords.extend(domain_keywords)

    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords


def _detect_domain_keywords(query: str) -> List[str]:
    """
    P1.1 GAP FIX: Detect research domain and add domain-specific keywords.

    This helps filter out irrelevant results (e.g., Ninjago for water research).
    """
    query_lower = query.lower()

    # Domain keyword mappings
    domain_mappings = {
        # Water/Environmental
        ("water", "filter", "contamination", "drinking", "purification"): [
            "water", "filter", "bacteria", "contamination", "pathogen",
            "purification", "treatment", "quality", "drinking", "safe"
        ],
        # Health/Medical
        ("health", "medical", "disease", "treatment", "patient", "clinical"): [
            "health", "medical", "clinical", "treatment", "patient",
            "disease", "therapy", "diagnosis", "symptoms", "medicine"
        ],
        # Technology
        ("technology", "software", "digital", "computer", "algorithm"): [
            "technology", "software", "system", "digital", "data",
            "algorithm", "computing", "application", "platform"
        ],
        # Energy
        ("energy", "renewable", "solar", "battery", "electricity"): [
            "energy", "power", "renewable", "solar", "efficiency",
            "battery", "electricity", "grid", "sustainable"
        ],
        # Agriculture/Food
        ("agriculture", "food", "crop", "farming", "harvest"): [
            "agriculture", "food", "crop", "farming", "production",
            "yield", "soil", "irrigation", "sustainable"
        ],
        # Materials/Chemistry
        ("material", "chemical", "polymer", "metal", "compound"): [
            "material", "chemical", "polymer", "properties",
            "synthesis", "compound", "molecular", "structure"
        ],
    }

    # Find matching domain
    for domain_triggers, domain_terms in domain_mappings.items():
        if any(trigger in query_lower for trigger in domain_triggers):
            return domain_terms

    # Default: no domain-specific enhancement
    return []


def filter_relevant_by_keywords(
    results: List[Any],
    topic_keywords: List[str],
    min_keyword_matches: int = 0,
) -> List[Any]:
    """
    P1.1 FIX: Fast keyword filter before expensive LLM calls.

    Filters search results that don't contain any topic keywords.
    This prevents garbage like Ninjago/Russian greetings from reaching the LLM.

    FIX-221B: Raised default from 1 to 2 (env configurable).
    min_keyword_matches=1 allowed hospital Legionella papers to match on "water" alone.

    Args:
        results: List of SearchResult objects
        topic_keywords: Keywords extracted from research topic
        min_keyword_matches: Minimum keywords that must match (0 = use env default)

    Returns:
        Filtered list of relevant results
    """
    # FIX-221B: Configurable minimum keyword matches (default 2)
    if min_keyword_matches == 0:
        min_keyword_matches = int(os.environ.get("POLARIS_MIN_KEYWORD_MATCHES", "2"))
    if not topic_keywords:
        return results  # No filtering if no keywords

    relevant = []
    filtered_count = 0

    for r in results:
        # Build text to check from available fields
        if hasattr(r, 'url'):
            text = f"{r.url} {r.title} {r.snippet or ''} {r.content or ''}".lower()
        elif isinstance(r, dict):
            text = f"{r.get('url', '')} {r.get('title', '')} {r.get('snippet', '')} {r.get('content', '')}".lower()
        else:
            text = str(r).lower()

        # Count keyword matches
        matches = sum(1 for kw in topic_keywords if kw.lower() in text)

        if matches >= min_keyword_matches:
            relevant.append(r)
        else:
            filtered_count += 1
            url = r.url if hasattr(r, 'url') else r.get('url', 'unknown') if isinstance(r, dict) else 'unknown'
            logger.debug(f"[KEYWORD-FILTER] Rejected (0/{len(topic_keywords)} matches): {url[:80]}")

    if filtered_count > 0:
        logger.warning(
            f"[KEYWORD-FILTER] Removed {filtered_count}/{len(results)} irrelevant results "
            f"(keywords: {topic_keywords[:5]}...)"
        )

    return relevant


# =============================================================================
# P1.5 GAP FIX: Cross-Encoder Filter BEFORE Content Fetch
# =============================================================================

def cross_encoder_filter_before_fetch(
    results: List[Any],
    query: str,
    min_keep: int = 50,
    max_keep: int = 250
) -> List[Any]:
    """
    P1.5 GAP FIX + FIX 84: Filter search results by cross-encoder BEFORE fetching content.

    This prevents wasting 1+ hour fetching content for irrelevant URLs.
    Uses snippets/titles for scoring since full content isn't fetched yet.

    FIX 84 UPDATE: Uses dynamic filtering instead of static threshold to prevent
    the "Funnel of Death" that rejects 99%+ of content.

    Args:
        results: List of SearchResult objects (with snippets, not full content)
        query: Research query for relevance comparison
        min_keep: Minimum results to keep (evidence floor)
        max_keep: Maximum results to keep

    Returns:
        Filtered list of relevant results worth fetching
    """
    if not results or not query:
        return results

    try:
        from src.functions.relevance_filter import cross_encoder_filter_dynamic_with_metadata
    except ImportError:
        logger.warning("[P1.5] Cross-encoder not available, skipping pre-fetch filter")
        return results

    # Build items for cross-encoder using available text (snippet/title, NOT content)
    items_to_filter = []
    for r in results:
        # Use snippet + title for pre-fetch scoring (content not available yet)
        if hasattr(r, 'snippet'):
            text = f"{r.title or ''} {r.snippet or ''}"
        elif isinstance(r, dict):
            text = f"{r.get('title', '')} {r.get('snippet', '')}"
        else:
            text = str(r)

        if text.strip():
            items_to_filter.append({
                "text": text,
                "_original": r
            })

    if not items_to_filter:
        return results

    # FIX 84: Apply dynamic cross-encoder filter (replaces static threshold)
    try:
        filtered_items = cross_encoder_filter_dynamic_with_metadata(
            query=query,
            items=items_to_filter,
            text_key="text",
            min_keep=min_keep,
            max_keep=max_keep,
            percentile=0.25,
            floor_threshold=0.10
        )

        # Extract original results that passed
        filtered_results = [item["_original"] for item in filtered_items]

        original_count = len(results)
        filtered_count = len(filtered_results)
        removed_count = original_count - filtered_count

        if removed_count > 0:
            logger.info(
                f"[P1.5 + FIX 84] Cross-encoder PRE-FETCH filter: {original_count} -> {filtered_count} "
                f"(dynamic filter, min_keep={min_keep})"
            )

        return filtered_results

    except Exception as e:
        logger.error(f"[P1.5] Cross-encoder pre-fetch filter failed: {e}")
        return results  # Return original on error


# =============================================================================
# BUG-008 FIX: Geographic Filtering for Evidence
# =============================================================================
# NOTE: Geographic filtering functions moved to src/functions/relevance_filter.py
# The check_geographic_relevance() function is now imported from there.
# This follows the v4 "Functional Core, Agentic Shell" architecture.


# =============================================================================
# Extraction Schemas
# =============================================================================

class ExtractedEntity(BaseModel):
    """An extracted named entity."""
    text: str = Field(description="The entity text")
    entity_type: Literal[
        "PERSON", "ORGANIZATION", "LOCATION", "DATE", "QUANTITY",
        "CHEMICAL", "PRODUCT", "REGULATION", "STANDARD", "DISEASE",
        "COMPOUND", "MEASUREMENT", "PERCENTAGE", "MONEY"
    ] = Field(description="Type of entity")
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    confidence: float = Field(description="Confidence score (0.0-1.0)")
    context: str = Field(default="", description="Surrounding context")


class ExtractedFact(BaseModel):
    """An extracted factual statement."""
    fact_text: str = Field(description="The factual statement")
    fact_type: Literal[
        "statistical", "causal", "definitional", "temporal",
        "comparative", "procedural", "regulatory"
    ] = Field(description="Type of fact")
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    confidence: float = Field(description="Confidence in extraction (0.0-1.0)")
    supporting_text: str = Field(description="Original text supporting the fact")
    entities_involved: List[str] = Field(default_factory=list, description="Entities mentioned")


# FIX 97/98: AtomicFact imported from src.orchestration.state
# This ensures single source of truth for the schema used by both
# Analyst (extraction) and Synthesizer (citation-dense report building)


class ExtractedClaim(BaseModel):
    """A verifiable claim extracted from text."""
    claim_text: str = Field(description="The claim statement")
    claim_type: Literal[
        "factual", "causal", "comparative", "predictive", "evaluative"
    ] = Field(description="Type of claim")
    verifiability: Literal["high", "medium", "low"] = Field(
        description="How easily this claim can be verified"
    )
    key_terms: List[str] = Field(default_factory=list, description="Key terms for verification")


class SourceAnalysis(BaseModel):
    """Complete analysis of a single source.

    NOTE: Removed ge/le constraints - Gemini structured output limitations.
    All float scores should be in range 0.0-1.0.

    FIX 97: Added atomic_facts for high citation density extraction.
    The atomic_facts field is the PRIMARY output for citation generation.
    """
    source_url: str = Field(description="URL of the source")
    source_quality: float = Field(description="Estimated source quality (0.0-1.0)")
    relevance_score: float = Field(description="Relevance to research question (0.0-1.0)")
    entities: List[ExtractedEntity] = Field(default_factory=list, description="Extracted entities")
    facts: List[ExtractedFact] = Field(default_factory=list, description="Extracted facts")
    claims: List[ExtractedClaim] = Field(default_factory=list, description="Extracted claims")
    key_findings: List[str] = Field(default_factory=list, description="Main findings")
    limitations: List[str] = Field(default_factory=list, description="Source limitations")
    # FIX 97: Atomic facts for high citation density
    atomic_facts: List[AtomicFact] = Field(
        default_factory=list,
        description="FIX 97: Atomic facts with direct quotes for citation density. Extract 5-15 per source."
    )


class AnalysisOutput(BaseModel):
    """Complete analysis output for all sources."""
    analyses: List[SourceAnalysis] = Field(description="Analysis per source")
    cross_source_entities: List[str] = Field(
        default_factory=list,
        description="Entities mentioned across multiple sources"
    )
    contradictions: List[str] = Field(
        default_factory=list,
        description="Contradictory claims found"
    )
    evidence_summary: str = Field(description="Summary of evidence gathered")


# =============================================================================
# Analyst Agent
# =============================================================================

@register_agent("analyst")
class AnalystAgent(BaseAgent):
    """
    Analyst Agent - Extracts structured information from sources.

    Responsibilities:
    1. Fetch and process source content
    2. Extract named entities (NER)
    3. Extract factual statements
    4. Identify verifiable claims
    5. Build evidence chain
    6. Detect contradictions

    Uses LLM for intelligent, context-aware extraction.
    GPU-accelerated batch processing with configurable depth (LAW VI).
    """

    def __init__(self):
        # Load configurations (LAW VI: Zero hard-coding)
        self.depth_config = get_depth_config()
        self.gpu_config = get_gpu_config()

        # FIX 36 (Gemini Audit): HARDCODE Analyst to "simple" tier (gemini-2.5-flash)
        # Entity extraction works perfectly on Flash with ~95% cost reduction.
        # DO NOT change this to "important" - the Gemini audit found this could
        # accidentally use Pro model ($0.075/1K vs $0.0005/1K = 150x cost).
        config = AgentConfig(
            name="analyst",
            description="Extracts facts, entities, and claims from search results",
            task_tier="simple",  # FIX 36: HARDCODED - DO NOT CHANGE
            temperature=0.0,
            max_tokens=16000,
        )
        super().__init__(config)

        # FIX 53.2: KIMI-AWARE SAFETY LATCH - Use KIMI K2.5 if available, else Gemini Flash
        # Original FIX 53 forced Gemini Flash to prevent cost explosion.
        # FIX 53.2: Now checks for Fireworks/KIMI first (cheaper: $0.60/$3.00 per 1M)
        # Falls back to Gemini Flash ($0.075/1M) if Fireworks unavailable.
        # NEVER uses Gemini Pro ($2.50/1M) for Analyst - that was the original bug.
        from src.config import get_config
        from src.callbacks.cost_tracking_callback import GeminiCostTrackingCallback

        global_config = get_config()

        # Check if KIMI K2.5 via Fireworks is available
        try:
            from langchain_fireworks import ChatFireworks
            fireworks_available = bool(global_config.env.fireworks_api_key)
        except ImportError:
            fireworks_available = False

        if fireworks_available:
            # FIX 53.2: Use KIMI K2.5 for Analyst (cost-effective with thinking mode)
            # I-cd-010 / GH#625: pipeline-C frozen — KIMI K2.5 hardcoding intentional
            # per CLAUDE.md §5 (Carney demo Pipeline-A uses src/polaris_graph/* + OpenRouter V4 Pro).
            model_name = "accounts/fireworks/models/kimi-k2p5"
            self._cost_callback = GeminiCostTrackingCallback(model_name=model_name)

            self.llm = ChatFireworks(
                model=model_name,
                api_key=global_config.env.fireworks_api_key,
                temperature=1.0,  # KIMI K2.5 REQUIRES 1.0 in thinking mode
                max_tokens=4096,  # Fireworks limit without streaming
            )
            self._is_fireworks = True  # FIX 91: Mark as Fireworks for structured output

            logger.info(
                f"[FIX 53.2] ANALYST using KIMI K2.5 via Fireworks "
                f"(cost: $0.60/$3.00 per 1M tokens)"
            )
            actual_model = model_name
        else:
            # Fallback: Use Gemini Flash (still cheap, but not KIMI).
            # I-cd-010 / GH#625: pipeline-C frozen — Gemini fallback per CLAUDE.md §5.
            from langchain_google_genai import ChatGoogleGenerativeAI

            forced_model = "gemini-2.5-flash"
            self._cost_callback = GeminiCostTrackingCallback(model_name=forced_model)
            self.llm = ChatGoogleGenerativeAI(
                model=forced_model,
                temperature=0.0,
                max_output_tokens=16000,
                google_api_key=global_config.env.gemini_api_key,
                thinking={"thinking_budget": 0},
                callbacks=[self._cost_callback],
            )

            logger.warning(
                f"[FIX 53.2] ANALYST fallback to Gemini Flash "
                f"(Fireworks/KIMI unavailable)"
            )
            actual_model = forced_model

        logger.info(
            f"AnalystAgent initialized: device={self.gpu_config.device}, "
            f"evidence_cap={self.depth_config.evidence_extraction.total_evidence_cap}, "
            f"llm_batch_size={self.depth_config.evidence_extraction.llm_batch_size}, "
            f"model={actual_model} (FIX 53.2: KIMI-AWARE)"
        )

    def get_system_prompt(self) -> str:
        # FIX 97: Atomic Fact Extraction prompt for high citation density
        return """You are a Research Analyst specializing in ATOMIC FACT EXTRACTION. Your PRIMARY job is to mine documents for individual, citeable facts.

=== FIX 97: ATOMIC EXTRACTION MODE ===

Your goal is MAXIMUM CITATION DENSITY. Extract 5-15 atomic facts per source.

WHAT IS AN ATOMIC FACT?
An atomic fact is a SINGLE, SPECIFIC, FALSIFIABLE statement that can be cited independently.

GOOD atomic facts (extract these):
- "7.1 million Americans contract waterborne diseases annually"
- "The EPA MCL for lead is 15 ppb"
- "E. coli causes 485,000 deaths from diarrheal diseases per year"
- "NSF/ANSI 53 certification covers lead reduction to below 10 ppb"
- "Legionnaires' disease incidence is 7.0-7.9 cases per 100,000 people"
- "The Safe Drinking Water Act was passed in 1974"

BAD (too general, not atomic):
- "Water contamination is a significant problem" (no specific data)
- "Many pathogens exist in water" (vague)
- "Filters help protect health" (no quantification)

=== EXTRACTION PRIORITIES ===

1. ATOMIC FACTS (PRIMARY - extract 5-15 per source):
   For EACH source, extract every specific:
   - STATISTIC: Numbers, percentages, counts, rates
   - MEASUREMENT: ppb, ppm, CFU/mL, log reduction values
   - DATE/PERIOD: Years, date ranges, "since 1974"
   - NAMED ENTITY: Organization names, pathogen names, chemical names
   - REGULATORY THRESHOLD: EPA limits, WHO guidelines, NSF standards
   - STANDARD REFERENCE: "NSF/ANSI 53", "ISO 22000", "EPA Method 1623"

   For each atomic fact, you MUST provide:
   - statement: The atomic fact itself
   - direct_quote: EXACT verbatim quote from source (in quotation marks)
   - fact_category: One of the categories above
   - atomicity_score: 1.0 if truly atomic, lower if compound
   - entities: Named entities in the fact

2. ENTITIES: Extract named entities with context

3. FACTS: General factual statements (for backward compatibility)

4. CLAIMS: Verifiable claims needing fact-checking

5. SOURCE QUALITY: Assess credibility

=== CRITICAL RULES ===

- MINE, DON'T SUMMARIZE: Extract every citeable fact, not summaries
- DIRECT QUOTES REQUIRED: Every atomic fact needs an exact quote
- QUANTITY OVER BREVITY: More facts = better. Target 5-15 per source.
- PRESERVE SPECIFICITY: "7.1 million" not "millions"
- NO INFERENCE: Only extract what is explicitly stated

=== OUTPUT ===

For each source, provide structured analysis with emphasis on atomic_facts.
The atomic_facts field is your PRIMARY deliverable for citation generation."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Analyze search results and extract evidence.

        Args:
            state: Current research state with search_results

        Returns:
            Updated state with evidence_chain populated
        """
        search_results = state.get("search_results", [])
        original_query = state.get("original_query", "")
        vector_id = state.get("vector_id", "unknown")

        if not search_results:
            logger.warning("No search results to analyze")
            return state

        logger.info(f"Analyzing {len(search_results)} search results")

        # FIX 41 (Gemini Audit #3): Increase Global Cap (Fix Lobotomy)
        # FIX 39 capped total flattened results to 5. This destroyed the report.
        # FIX 85 (Operation Unshackle): Lifted cap from 60 to 250.
        # Gemini DR uses 200+ searches, we need proportional evidence capacity.
        # Target: ~50 queries * 5 results = 250 documents total.
        MAX_RESULTS_TOTAL = 250
        if len(search_results) > MAX_RESULTS_TOTAL:
            # Sort by relevance (if available) or use original order (search ranking)
            if hasattr(search_results[0], 'relevance_score'):
                search_results_sorted = sorted(
                    search_results,
                    key=lambda r: getattr(r, 'relevance_score', 0),
                    reverse=True
                )
            else:
                # Trust search engine ranking - top results are most relevant
                search_results_sorted = search_results

            original_count = len(search_results)
            search_results = search_results_sorted[:MAX_RESULTS_TOTAL]
            logger.info(
                f"[FIX 41] Capped analyst volume: {original_count} -> {len(search_results)} results "
                f"(MAX_RESULTS_TOTAL={MAX_RESULTS_TOTAL})"
            )
            state["analyst_cap_stats"] = {
                "original_count": original_count,
                "capped_count": len(search_results),
                "cap_limit": MAX_RESULTS_TOTAL
            }

        # P1.1 FIX: Pre-LLM Keyword Relevance Filter
        # Filter irrelevant results BEFORE fetching content or calling LLM
        topic_keywords = extract_topic_keywords(original_query)
        if topic_keywords:
            original_count = len(search_results)
            search_results = filter_relevant_by_keywords(search_results, topic_keywords)
            filtered_count = original_count - len(search_results)
            if filtered_count > 0:
                logger.info(f"[P1.1] Keyword filter removed {filtered_count}/{original_count} irrelevant results")
                state["keyword_filter_stats"] = {
                    "original_count": original_count,
                    "filtered_count": len(search_results),
                    "removed_count": filtered_count,
                    "keywords_used": topic_keywords[:10]
                }

        if not search_results:
            logger.warning("No search results after keyword filtering")
            state["error"] = "KEYWORD_FILTER_EMPTY"
            state["error_message"] = "All search results filtered as irrelevant by keyword filter"
            return state

        # NOTE: Cross-encoder filtering is now done in graph.py search_node (orchestration layer)
        # Removed redundant filter here to avoid double-filtering the same results
        # See graph.py line ~260 for the cross-encoder gate at threshold 0.20

        # Clear GPU cache before large operation
        ensure_gpu_memory()

        # Fetch content for sources that need it (only relevant ones now)
        search_results = self._fetch_content(search_results)

        # P2.1 FIX: Checkpoint after content fetch (save 1+ hour of fetch work)
        state["search_results"] = search_results
        save_state(state, f"after_content_fetch_{vector_id}")

        # FIX 15: Preserve existing evidence across iterations (prevent amnesia)
        all_evidence = list(state.get("evidence_chain", []))
        all_entities = list(state.get("entities_extracted", []))
        all_facts = list(state.get("facts_extracted", []))
        existing_count = len(all_evidence)

        # FIX 15: Track already-processed URLs to skip duplicates across iterations
        processed_urls = {e.source_url for e in all_evidence if hasattr(e, "source_url")}
        new_results = [r for r in search_results if getattr(r, "url", "") not in processed_urls]
        skipped_count = len(search_results) - len(new_results)
        if skipped_count > 0:
            logger.info(f"[FIX 15] Skipping {skipped_count} already-processed URLs, {len(new_results)} new to process")
        search_results = new_results

        # SOTA FIX: Track content hashes for deduplication
        seen_content_hashes = {
            hashlib.md5(e.text.strip().lower().encode()).hexdigest()
            for e in all_evidence if hasattr(e, "text")
        }
        duplicate_count = 0

        # Use LLM-optimized batch size from config (LAW VI)
        # NOTE: Do NOT use gpu_config.nli_batch_size - that's for GPU NLI operations
        # LLM batch size must be small to avoid exceeding token limits (128K for GPT-4o)
        batch_size = self.depth_config.evidence_extraction.llm_batch_size
        evidence_cap = self.depth_config.evidence_extraction.total_evidence_cap

        logger.info(f"Processing with llm_batch_size={batch_size}, evidence_cap={evidence_cap}")

        # P1.4 FIX: Circuit breaker tracking
        circuit_breaker_threshold = 50  # First 50 sources
        circuit_breaker_min_extractions = 1  # Must have at least 1 extraction
        total_sources_processed = 0
        batch_index = 0

        for i in range(0, len(search_results), batch_size):
            # Check evidence cap before processing more batches
            if len(all_evidence) >= evidence_cap:
                logger.info(f"Evidence cap reached ({evidence_cap}), stopping extraction")
                break

            # Clear GPU cache between batches for memory efficiency
            if i > 0 and i % (batch_size * 4) == 0:
                ensure_gpu_memory()

            batch = search_results[i:i + batch_size]

            # FIX-124: Build URL -> perspective_origins mapping for STORM traceability
            url_to_perspectives = {}
            # FIX-180A: Build URL -> title mapping for bibliography metadata
            url_to_title = {}
            # FIX-227: Build URL -> authors mapping for bibliography metadata
            url_to_authors = {}
            for result in batch:
                url = getattr(result, 'url', '')
                perspectives = getattr(result, 'perspective_origins', [])
                title = getattr(result, 'title', '')
                metadata = getattr(result, 'metadata', {}) or {}
                authors = metadata.get('authors', [])
                if url and perspectives:
                    url_to_perspectives[url] = perspectives
                if url and title:
                    url_to_title[url] = title
                if url and authors:
                    url_to_authors[url] = authors

            analysis = self._analyze_batch(batch, original_query, state)

            # P1.4 FIX: Circuit breaker check after processing batch
            total_sources_processed += len(batch)
            batch_index += 1

            # Check circuit breaker after first N sources
            if total_sources_processed >= circuit_breaker_threshold and len(all_evidence) < circuit_breaker_min_extractions:
                logger.error(
                    f"[CIRCUIT-BREAKER] First {total_sources_processed} sources yielded "
                    f"{len(all_evidence)} extractions. ABORTING to prevent wasted compute."
                )
                state["error"] = "CIRCUIT_BREAKER_TRIGGERED"
                state["error_message"] = (
                    f"Search quality too low - only {len(all_evidence)} extractions "
                    f"from first {total_sources_processed} sources"
                )
                state["circuit_breaker_stats"] = {
                    "sources_processed": total_sources_processed,
                    "extractions": len(all_evidence),
                    "threshold": circuit_breaker_threshold
                }
                return state

            # Convert to Evidence objects with quality tier classification
            for source_analysis in analysis.analyses:
                # Normalize source_quality to [0, 1] range (LLM may return 0-10 scale)
                if source_analysis.source_quality > 1.0:
                    source_analysis.source_quality = min(source_analysis.source_quality / 10.0, 1.0)
                # FIX 101: Set domain_type at source level (not inside facts loop)
                # This ensures domain_type is available for atomic_facts even if facts list is empty
                domain_lower = source_analysis.source_url.lower()
                if ".gov" in domain_lower:
                    domain_type = "gov"
                elif ".edu" in domain_lower:
                    domain_type = "edu"
                elif ".org" in domain_lower:
                    domain_type = "org"
                elif ".com" in domain_lower:
                    domain_type = "com"
                else:
                    domain_type = "other"

                # FIX-124: Get perspective_origins from URL mapping (MUST be outside facts loop)
                # Bug fix: source_perspectives must be defined before BOTH facts loop AND atomic_facts loop
                source_perspectives = url_to_perspectives.get(source_analysis.source_url, [])

                for j, fact in enumerate(source_analysis.facts):
                    # Check cap within batch
                    if len(all_evidence) >= evidence_cap:
                        break

                    evidence_id = f"ev_{len(all_evidence) + 1:04d}"
                    chunk_id = hashlib.md5(
                        (source_analysis.source_url + fact.fact_text).encode()
                    ).hexdigest()[:12]

                    # SOTA FIX: Detect metadata vs real content
                    is_metadata = Evidence.detect_metadata(fact.supporting_text)
                    if is_metadata:
                        logger.debug(f"Filtered metadata: {fact.supporting_text[:50]}...")
                        continue  # Skip metadata

                    # BUG-008 FIX: Geographic relevance filtering
                    target_region = state.get("region", "GLOBAL")
                    geo_relevant, geo_reason = check_geographic_relevance(
                        text=fact.supporting_text,
                        source_url=source_analysis.source_url,
                        target_region=target_region,
                    )
                    if not geo_relevant:
                        logger.warning(f"[GEO-FILTER] Rejected: {geo_reason}")
                        continue  # Skip geographically irrelevant evidence

                    # SOTA FIX: Content hash deduplication
                    content_hash = hashlib.md5(
                        fact.supporting_text.strip().lower().encode()
                    ).hexdigest()
                    if content_hash in seen_content_hashes:
                        duplicate_count += 1
                        continue  # Skip duplicate content
                    seen_content_hashes.add(content_hash)

                    # SOTA FIX: Classify quality tier
                    quality_tier = Evidence.classify_quality_tier(
                        relevance_score=source_analysis.relevance_score,
                        source_quality_score=source_analysis.source_quality,
                        source_url=source_analysis.source_url,
                    )

                    # domain_type and source_perspectives are now set at source level (FIX 101, FIX-124)

                    evidence = Evidence(
                        evidence_id=evidence_id,
                        chunk_id=chunk_id,
                        source_url=source_analysis.source_url,
                        title=url_to_title.get(source_analysis.source_url, ""),  # FIX-180A
                        text=fact.supporting_text,
                        relevance_score=source_analysis.relevance_score,
                        source_quality_score=source_analysis.source_quality,
                        extraction_method="llm_extraction",
                        claims=[fact.fact_text],
                        entities=fact.entities_involved,
                        quality_tier=quality_tier,
                        is_metadata=False,
                        source_domain_type=domain_type,
                        perspective_origins=source_perspectives,  # FIX-124: STORM traceability
                        authors=url_to_authors.get(source_analysis.source_url, []),  # FIX-227
                    )
                    all_evidence.append(evidence)

                # FIX 97 GHOST WIRING FIX: Create Evidence from atomic_facts
                # Each atomic fact becomes its own Evidence piece with direct quote
                for atomic_fact in source_analysis.atomic_facts:
                    if not atomic_fact.statement or not atomic_fact.direct_quote:
                        continue  # Skip incomplete atomic facts

                    # ==========================================================
                    # FIX 111: Evidence Quality Gating - Filter metadata garbage
                    # ==========================================================
                    # RUN15 had 40% of evidence as metadata (document identifiers,
                    # PDF structure, hosting info). MiniCheck correctly returns
                    # NOT_SUPPORTED for these, causing 100% failure rate.
                    # Filter metadata BEFORE creating evidence to improve S/N ratio.
                    FIX_111_METADATA_PATTERNS = [
                        r"^Document\s+(is|was|uses|contains|has|identifier)",
                        r"(PDF|file|format)\s+(structure|identifier|version|type)",
                        r"hosted\s+on\s+.*\s+domain",
                        r"accessible\s+through",
                        r"^(PURL|identifier|reference\s+number)",
                        r"(corrupted|not\s+readable|failed\s+to\s+parse)",
                        r"^\d+\s+objects?\s+in\s+PDF",
                        r"^Document\s+contains\s+\d+\s+(pages?|objects?)",
                        r"^(National\s+Service\s+Center|NSCEP)",
                        r"^(epa\.gov|nepis\.epa\.gov)\s+domain",
                    ]

                    # FIX-135A: PDF noise CONTENT patterns (not just metadata)
                    # Catches sentences ABOUT PDF corruption that the LLM
                    # writes as if they were research findings.
                    FIX_135_PDF_NOISE_PATTERNS = [
                        r"%PDF-\d",
                        r"corrupted\s+or\s+binary\s+encoded",
                        r"preventing\s+text\s+extraction",
                        r"binary\s+encoded\s+content",
                        r"PDF\s+document\s+(could\s+not|cannot|failed\s+to)",
                        r"text\s+extraction\s+(was\s+not|is\s+not)\s+possible",
                        r"garbled\s+(text|content|output)",
                        r"encoding\s+(error|issue|problem).*PDF",
                        r"unreadable\s+(due\s+to|because)",
                        r"document\s+appears\s+to\s+be\s+(corrupt|damaged|binary)",
                        # FIX-142: Additional PDF noise patterns from gap analysis
                        r"not\s+directly\s+extractable",
                        r"minimal\s+extractable",
                        r"\bcorrupted\b(?!\s+or\s+binary)",
                        r"PDF-\d+\.\d+",
                    ]

                    is_metadata_garbage = any(
                        re.search(pattern, atomic_fact.direct_quote, re.IGNORECASE)
                        for pattern in FIX_111_METADATA_PATTERNS
                    )

                    is_pdf_noise = any(
                        re.search(pattern, atomic_fact.direct_quote, re.IGNORECASE)
                        for pattern in FIX_135_PDF_NOISE_PATTERNS
                    )

                    if is_metadata_garbage:
                        logger.warning(
                            f"[FIX 111] Filtering metadata evidence: "
                            f"{atomic_fact.direct_quote[:60]}..."
                        )
                        continue  # Skip this atomic fact

                    if is_pdf_noise:
                        logger.warning(
                            f"[FIX-135] Filtering PDF noise content: "
                            f"{atomic_fact.direct_quote[:60]}..."
                        )
                        continue  # Skip this atomic fact

                    # Check for duplicates
                    content_hash = hashlib.md5(
                        atomic_fact.direct_quote.strip().lower().encode()
                    ).hexdigest()

                    if content_hash not in seen_content_hashes and len(all_evidence) < evidence_cap:
                        seen_content_hashes.add(content_hash)

                        atomic_ev_id = f"ev_atomic_{hashlib.md5((source_analysis.source_url + atomic_fact.statement).encode()).hexdigest()[:12]}"
                        atomic_chunk_id = f"chunk_atomic_{hashlib.md5(source_analysis.source_url.encode()).hexdigest()[:8]}"

                        # Atomic facts from good sources get GOLD tier
                        atomic_tier = "GOLD" if source_analysis.source_quality >= 0.6 else "SILVER"

                        # FIX 113: Evidence Text Enrichment - Include context
                        # Combine statement + direct quote for better MiniCheck verification
                        enriched_text = f"{atomic_fact.statement}. Source quote: \"{atomic_fact.direct_quote}\""

                        atomic_evidence = Evidence(
                            evidence_id=atomic_ev_id,
                            chunk_id=atomic_chunk_id,
                            source_url=source_analysis.source_url,
                            title=url_to_title.get(source_analysis.source_url, ""),  # FIX-180A
                            text=enriched_text[:2000],  # FIX 113: Use enriched text instead of just quote
                            relevance_score=min(1.0, source_analysis.relevance_score + 0.1),  # Boost atomic facts
                            source_quality_score=source_analysis.source_quality,
                            extraction_method="atomic_fact_extraction",
                            claims=[atomic_fact.statement],  # The atomic statement is the claim
                            entities=atomic_fact.entities,
                            quality_tier=atomic_tier,
                            is_metadata=False,
                            source_domain_type=domain_type,
                            atomic_facts=[atomic_fact],  # Attach the atomic fact to its evidence
                            perspective_origins=source_perspectives,  # FIX-124: STORM traceability
                            authors=url_to_authors.get(source_analysis.source_url, []),  # FIX-227
                        )
                        all_evidence.append(atomic_evidence)
                        logger.info(
                            f"[FIX 97] Created atomic evidence {atomic_ev_id}: "
                            f"{atomic_fact.fact_category} - {atomic_fact.statement[:50]}..."
                        )

                # Collect entities
                for entity in source_analysis.entities:
                    all_entities.append({
                        "text": entity.text,
                        "type": entity.entity_type,
                        "confidence": entity.confidence,
                        "source": source_analysis.source_url,
                    })

                # Collect facts
                for fact in source_analysis.facts:
                    all_facts.append({
                        "text": fact.fact_text,
                        "type": fact.fact_type,
                        "confidence": fact.confidence,
                        "source": source_analysis.source_url,
                    })

            # P2.2 FIX: Checkpoint after each batch (prevent data loss on crash)
            state["evidence_chain"] = all_evidence
            state["entities_extracted"] = all_entities
            state["facts_extracted"] = all_facts
            total_batches = (len(search_results) + batch_size - 1) // batch_size
            save_state(state, f"batch_{batch_index}_of_{total_batches}_{vector_id}")
            logger.info(f"[CHECKPOINT] Saved batch {batch_index}/{total_batches}: {len(all_evidence)} evidence items")

        # =================================================================
        # W3.1 SOTA: Multi-Pass Second Extraction for High-Quality Sources
        # =================================================================
        multi_pass_enabled = _MULTI_PASS_CONFIG.get("enabled", True)
        if multi_pass_enabled:
            min_quality = _MULTI_PASS_CONFIG.get("min_quality_for_pass_2", 0.70)

            # Identify high-quality sources from evidence extracted in first pass
            # Sources that produced high-quality evidence warrant a second pass
            high_quality_urls = set()

            # Include sources that produced GOLD-tier evidence
            for ev in all_evidence:
                if ev.quality_tier == "GOLD":
                    high_quality_urls.add(ev.source_url)

            # Include sources with high quality scores
            for ev in all_evidence:
                if hasattr(ev, 'source_quality_score') and ev.source_quality_score >= min_quality:
                    high_quality_urls.add(ev.source_url)

            # Filter search results to high-quality ones
            high_quality_sources = []
            for result in search_results:
                if getattr(result, 'url', '') in high_quality_urls:
                    high_quality_sources.append(result)

            if high_quality_sources:
                logger.info(
                    f"[W3.1 MULTI-PASS] Starting second pass on {len(high_quality_sources)} "
                    f"high-quality sources"
                )

                # FIX-124: Build URL -> perspective_origins mapping for second pass
                url_to_perspectives_p2 = {}
                # FIX-180A: Build URL -> title mapping for second pass
                url_to_title_p2 = {}
                # FIX-227: Build URL -> authors mapping for second pass
                url_to_authors_p2 = {}
                for result in high_quality_sources:
                    url = getattr(result, 'url', '')
                    perspectives = getattr(result, 'perspective_origins', [])
                    title = getattr(result, 'title', '')
                    metadata = getattr(result, 'metadata', {}) or {}
                    authors = metadata.get('authors', [])
                    if url and perspectives:
                        url_to_perspectives_p2[url] = perspectives
                    if url and title:
                        url_to_title_p2[url] = title
                    if url and authors:
                        url_to_authors_p2[url] = authors

                # Prepare first pass results context
                first_pass_facts = [{"text": f.get("text", "")} for f in all_facts[:20]]

                # Process high-quality sources in batches for second pass
                second_pass_evidence_count = 0
                for i in range(0, len(high_quality_sources), batch_size):
                    hq_batch = high_quality_sources[i:i + batch_size]

                    deep_analysis = self._analyze_batch_deep(
                        hq_batch, original_query, state, first_pass_facts
                    )

                    # Convert second-pass results to evidence
                    for source_analysis in deep_analysis.analyses:
                        # Normalize source_quality to [0, 1] range (LLM may return 0-10 scale)
                        if source_analysis.source_quality > 1.0:
                            source_analysis.source_quality = min(source_analysis.source_quality / 10.0, 1.0)

                        # FIX-124H: Get perspective_origins ONCE per source_analysis (before both inner loops)
                        # This prevents "cannot access local variable 'p2_perspectives'" when facts is empty
                        p2_perspectives = url_to_perspectives_p2.get(source_analysis.source_url, [])

                        for fact in source_analysis.facts:
                            # Check if this is truly new evidence (content-based dedupe)
                            content_hash = hashlib.md5(
                                fact.supporting_text.strip().lower().encode()
                            ).hexdigest()

                            if content_hash not in seen_content_hashes and len(all_evidence) < evidence_cap:
                                seen_content_hashes.add(content_hash)

                                evidence_id = f"ev_{hashlib.md5((source_analysis.source_url + fact.fact_text).encode()).hexdigest()[:12]}_p2"
                                chunk_id = f"chunk_{hashlib.md5(source_analysis.source_url.encode()).hexdigest()[:8]}_p2"

                                # FIX-124H: p2_perspectives now defined at source_analysis level (line ~1092)

                                evidence = Evidence(
                                    evidence_id=evidence_id,
                                    chunk_id=chunk_id,
                                    source_url=source_analysis.source_url,
                                    title=url_to_title_p2.get(source_analysis.source_url, ""),  # FIX-180A
                                    text=fact.supporting_text,
                                    relevance_score=source_analysis.relevance_score,
                                    source_quality_score=source_analysis.source_quality,
                                    extraction_method="llm_extraction_pass_2",
                                    claims=[fact.fact_text],
                                    entities=fact.entities_involved,
                                    quality_tier="GOLD",  # Second-pass from high-quality = GOLD
                                    is_metadata=False,
                                    perspective_origins=p2_perspectives,  # FIX-124: STORM traceability
                                    authors=url_to_authors_p2.get(source_analysis.source_url, []),  # FIX-227
                                )
                                all_evidence.append(evidence)
                                second_pass_evidence_count += 1

                                # Also add to facts
                                all_facts.append({
                                    "text": fact.fact_text,
                                    "type": fact.fact_type,
                                    "confidence": fact.confidence,
                                    "source": source_analysis.source_url,
                                    "extraction_pass": 2,
                                })

                        # FIX 97 GHOST WIRING FIX: Second pass atomic facts
                        for atomic_fact in source_analysis.atomic_facts:
                            if not atomic_fact.statement or not atomic_fact.direct_quote:
                                continue

                            # FIX 111: Apply metadata filter to second pass too
                            FIX_111_METADATA_PATTERNS = [
                                r"^Document\s+(is|was|uses|contains|has|identifier)",
                                r"(PDF|file|format)\s+(structure|identifier|version|type)",
                                r"hosted\s+on\s+.*\s+domain",
                                r"accessible\s+through",
                                r"^(PURL|identifier|reference\s+number)",
                                r"(corrupted|not\s+readable|failed\s+to\s+parse)",
                                r"^\d+\s+objects?\s+in\s+PDF",
                                r"^Document\s+contains\s+\d+\s+(pages?|objects?)",
                                r"^(National\s+Service\s+Center|NSCEP)",
                                r"^(epa\.gov|nepis\.epa\.gov)\s+domain",
                            ]

                            # FIX-135A: PDF noise CONTENT patterns (second pass)
                            FIX_135_PDF_NOISE_PATTERNS = [
                                r"%PDF-\d",
                                r"corrupted\s+or\s+binary\s+encoded",
                                r"preventing\s+text\s+extraction",
                                r"binary\s+encoded\s+content",
                                r"PDF\s+document\s+(could\s+not|cannot|failed\s+to)",
                                r"text\s+extraction\s+(was\s+not|is\s+not)\s+possible",
                                r"garbled\s+(text|content|output)",
                                r"encoding\s+(error|issue|problem).*PDF",
                                r"unreadable\s+(due\s+to|because)",
                                r"document\s+appears\s+to\s+be\s+(corrupt|damaged|binary)",
                                # FIX-142: Additional PDF noise patterns from gap analysis
                                r"not\s+directly\s+extractable",
                                r"minimal\s+extractable",
                                r"\bcorrupted\b(?!\s+or\s+binary)",
                                r"PDF-\d+\.\d+",
                            ]

                            is_metadata_garbage = any(
                                re.search(pattern, atomic_fact.direct_quote, re.IGNORECASE)
                                for pattern in FIX_111_METADATA_PATTERNS
                            )

                            is_pdf_noise = any(
                                re.search(pattern, atomic_fact.direct_quote, re.IGNORECASE)
                                for pattern in FIX_135_PDF_NOISE_PATTERNS
                            )

                            if is_metadata_garbage:
                                logger.warning(
                                    f"[FIX 111 P2] Filtering metadata evidence: "
                                    f"{atomic_fact.direct_quote[:60]}..."
                                )
                                continue

                            if is_pdf_noise:
                                logger.warning(
                                    f"[FIX-135 P2] Filtering PDF noise content: "
                                    f"{atomic_fact.direct_quote[:60]}..."
                                )
                                continue

                            content_hash = hashlib.md5(
                                atomic_fact.direct_quote.strip().lower().encode()
                            ).hexdigest()

                            if content_hash not in seen_content_hashes and len(all_evidence) < evidence_cap:
                                seen_content_hashes.add(content_hash)

                                atomic_ev_id = f"ev_atomic_{hashlib.md5((source_analysis.source_url + atomic_fact.statement).encode()).hexdigest()[:12]}_p2"
                                atomic_chunk_id = f"chunk_atomic_{hashlib.md5(source_analysis.source_url.encode()).hexdigest()[:8]}_p2"

                                # FIX 113: Evidence Text Enrichment - Include context
                                enriched_text = f"{atomic_fact.statement}. Source quote: \"{atomic_fact.direct_quote}\""

                                atomic_evidence = Evidence(
                                    evidence_id=atomic_ev_id,
                                    chunk_id=atomic_chunk_id,
                                    source_url=source_analysis.source_url,
                                    title=url_to_title_p2.get(source_analysis.source_url, ""),  # FIX-180A
                                    text=enriched_text[:2000],  # FIX 113: Use enriched text
                                    relevance_score=min(1.0, source_analysis.relevance_score + 0.15),  # Higher boost for pass 2
                                    source_quality_score=source_analysis.source_quality,
                                    extraction_method="atomic_fact_extraction_pass_2",
                                    claims=[atomic_fact.statement],
                                    entities=atomic_fact.entities,
                                    quality_tier="GOLD",  # Pass 2 atomic = GOLD
                                    is_metadata=False,
                                    atomic_facts=[atomic_fact],
                                    perspective_origins=p2_perspectives,  # FIX-124: STORM traceability
                                    authors=url_to_authors_p2.get(source_analysis.source_url, []),  # FIX-227
                                )
                                all_evidence.append(atomic_evidence)
                                second_pass_evidence_count += 1
                                logger.info(
                                    f"[FIX 97 P2] Atomic evidence {atomic_ev_id}: "
                                    f"{atomic_fact.fact_category} - {atomic_fact.statement[:40]}..."
                                )

                logger.info(
                    f"[W3.1 MULTI-PASS] Second pass complete: {second_pass_evidence_count} "
                    f"new evidence pieces from {len(high_quality_sources)} sources"
                )
                state["multi_pass_stats"] = {
                    "enabled": True,
                    "high_quality_sources": len(high_quality_sources),
                    "second_pass_evidence": second_pass_evidence_count,
                }
            else:
                logger.info("[W3.1 MULTI-PASS] No high-quality sources found for second pass")
                state["multi_pass_stats"] = {
                    "enabled": True,
                    "high_quality_sources": 0,
                    "second_pass_evidence": 0,
                }

        # Update state
        state["evidence_chain"] = all_evidence
        state["entities_extracted"] = all_entities
        state["facts_extracted"] = all_facts

        # ======================================================================
        # FIX-137A: Retroactive Perspective Tagging
        # ======================================================================
        # STORM perspective_origins is only populated for perspective-specific
        # query results. General web search results (85% of evidence) have no
        # tags, making entropy calculation unrepresentative. This step assigns
        # perspectives to untagged evidence via keyword matching.
        self._retroactive_perspective_tag(all_evidence)

        # SOTA FIX: Log quality tier distribution
        tier_counts = {"GOLD": 0, "SILVER": 0, "BRONZE": 0, "UNVERIFIED": 0}
        for ev in all_evidence:
            tier_counts[ev.quality_tier] = tier_counts.get(ev.quality_tier, 0) + 1

        logger.info(
            f"Analysis complete: {len(all_evidence)} evidence pieces, "
            f"{len(all_entities)} entities, {len(all_facts)} facts"
        )
        logger.info(
            f"Quality tier distribution: GOLD={tier_counts['GOLD']}, "
            f"SILVER={tier_counts['SILVER']}, BRONZE={tier_counts['BRONZE']}, "
            f"UNVERIFIED={tier_counts['UNVERIFIED']}"
        )
        logger.info(
            f"Deduplication: {duplicate_count} duplicates filtered, "
            f"{len(seen_content_hashes)} unique content hashes"
        )
        state["quality_tier_distribution"] = tier_counts
        state["duplicate_count"] = duplicate_count

        # ======================================================================
        # SOTA Integration: Advanced Deduplication (Task #21)
        # ======================================================================
        try:
            if all_evidence and len(all_evidence) > 1:
                dedup = ContentDeduplicator()
                # Convert evidence to format expected by deduplicator
                evidence_texts = []
                for ev in all_evidence:
                    ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
                    evidence_texts.append({
                        "id": ev_dict.get("evidence_id", ""),
                        "content": ev_dict.get("text", ""),
                        "metadata": ev_dict,
                    })

                dedup_result = dedup.deduplicate(evidence_texts)
                state["advanced_dedup_stats"] = {
                    "original_count": len(all_evidence),
                    "unique_count": dedup_result.unique_count,
                    "duplicate_count": dedup_result.duplicate_count,
                    "deduplication_ratio": dedup_result.deduplication_ratio,
                }
                logger.info(
                    f"[DEDUP] Advanced deduplication: {len(all_evidence)} -> {dedup_result.unique_count} "
                    f"({dedup_result.deduplication_ratio*100:.1f}% reduction)"
                )
        except Exception as e:
            logger.warning(f"[DEDUP] Advanced deduplication failed: {e}")

        # ======================================================================
        # SOTA Integration: Source Bias Detection (Task #21)
        # ======================================================================
        try:
            if all_evidence:
                bias_detector = BiasDetector()
                # Convert evidence to format expected by bias detector
                evidence_for_bias = []
                for ev in all_evidence:
                    ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
                    evidence_for_bias.append({
                        "source_url": ev_dict.get("source_url", ""),
                        "text": ev_dict.get("text", ""),
                        "title": ev_dict.get("title", ""),
                    })

                bias_report = bias_detector.analyze_sources(evidence_for_bias)
                state["bias_analysis"] = {
                    "is_balanced": bias_report.is_balanced,
                    "balance_score": bias_report.balance_score,
                    "category_distribution": {
                        cat.value: count for cat, count in bias_report.category_distribution.items()
                    },
                    "balance_warning": bias_report.balance_warning,
                    "suggestions": bias_report.balancing_suggestions,
                }
                if not bias_report.is_balanced:
                    logger.warning(f"[BIAS] Unbalanced sources detected: {bias_report.balance_warning}")
                else:
                    logger.info(f"[BIAS] Sources balanced: score={bias_report.balance_score:.2f}")
        except Exception as e:
            logger.warning(f"[BIAS] Bias detection failed: {e}")

        # Enrich with knowledge graph
        state = self._enrich_with_graph(state, all_entities, all_facts)

        return state

    def _retroactive_perspective_tag(self, evidence_list: List[Evidence]) -> None:
        """
        FIX-137A: Assign perspectives to untagged evidence via keyword matching.

        STORM perspective_origins is only populated for perspective-specific query
        results. General web search results (~85% of evidence) have no tags.
        This retroactive tagging improves entropy calculation representativeness.

        Rules:
        - Does NOT override existing STORM tags
        - Marks tagged items with perspective_source="retroactive_keyword" for provenance
        - Modifies evidence objects in-place
        """
        perspective_keywords = {
            "Scientific": [
                "study", "research", "findings", "experiment", "data",
                "analysis", "evidence", "methodology", "peer-reviewed",
                "published", "journal", "laboratory", "clinical",
            ],
            "Regulatory": [
                "regulation", "compliance", "epa", "fda", "standard",
                "guideline", "policy", "enforcement", "mandate", "act",
                "law", "requirement", "permitted", "threshold",
            ],
            "Public_Health": [
                "health", "disease", "risk", "exposure", "epidemiology",
                "mortality", "morbidity", "outbreak", "contamination",
                "toxicity", "carcinogen", "safety", "wellbeing",
            ],
            "Economic": [
                "cost", "price", "market", "economic", "investment",
                "savings", "budget", "affordable", "expense", "revenue",
                "financial", "trade", "industry revenue",
            ],
            "Industry": [
                "manufacturer", "product", "commercial", "brand",
                "technology", "innovation", "patent", "production",
                "supply chain", "vendor", "certification",
            ],
            "Regional": [
                "local", "regional", "community", "municipal", "rural",
                "urban", "geographic", "county", "district", "state-level",
            ],
            "Historical": [
                "history", "historical", "decade", "century", "evolution",
                "timeline", "previously", "originally", "legacy",
            ],
            "Emerging_Trends": [
                "emerging", "novel", "recent", "trend", "future",
                "advancing", "next-generation", "cutting-edge", "latest",
            ],
        }

        tagged_count = 0
        for ev in evidence_list:
            # Access perspective_origins (handle both Pydantic and dict)
            if hasattr(ev, "perspective_origins"):
                existing = ev.perspective_origins or []
            elif isinstance(ev, dict):
                existing = ev.get("perspective_origins", [])
            else:
                continue

            # Skip if already tagged by STORM
            if existing:
                continue

            # Get evidence text for keyword matching
            if hasattr(ev, "text"):
                text = (ev.text or "").lower()
            elif isinstance(ev, dict):
                text = (ev.get("text", "") or "").lower()
            else:
                continue

            if not text:
                continue

            # FIX-165: Get source URL for domain-based tagging
            if hasattr(ev, "source_url"):
                source_url = (ev.source_url or "").lower()
            elif isinstance(ev, dict):
                source_url = (ev.get("source_url", "") or "").lower()
            else:
                source_url = ""

            # Score each perspective by keyword hits
            # FIX-165: Case-insensitive substring matching (already lowercase)
            best_perspective = None
            best_score = 0
            for perspective, keywords in perspective_keywords.items():
                score = sum(1 for kw in keywords if kw in text)
                if score > best_score:
                    best_score = score
                    best_perspective = perspective

            # FIX-165: Domain-based tagging fallback
            if best_score < 1 and source_url:
                domain_perspective_map = {
                    ".edu": "Scientific",
                    ".gov": "Regulatory",
                    "pubmed": "Scientific",
                    "scholar.google": "Scientific",
                    "ncbi.nlm.nih": "Scientific",
                    "who.int": "Public_Health",
                    "cdc.gov": "Public_Health",
                    "epa.gov": "Regulatory",
                    "fda.gov": "Regulatory",
                }
                for domain_key, perspective in domain_perspective_map.items():
                    if domain_key in source_url:
                        best_perspective = perspective
                        best_score = 1  # Domain match counts as 1 hit
                        break

            # FIX-165: Lowered threshold from 2 to 1 keyword hit
            if best_perspective and best_score >= 1:
                if hasattr(ev, "perspective_origins"):
                    ev.perspective_origins = [best_perspective]
                    ev.perspective_source = "retroactive_keyword"
                elif isinstance(ev, dict):
                    ev["perspective_origins"] = [best_perspective]
                    ev["perspective_source"] = "retroactive_keyword"
                tagged_count += 1

        total = len(evidence_list)
        if tagged_count > 0:
            logger.info(
                f"[FIX-165] Retroactive perspective tagging: "
                f"{tagged_count}/{total} evidence items tagged "
                f"({tagged_count/max(total,1)*100:.0f}%)"
            )

    def _enrich_with_graph(
        self,
        state: ResearchState,
        entities: List[Dict[str, Any]],
        facts: List[Dict[str, Any]]
    ) -> ResearchState:
        """
        Enrich entities and facts with knowledge graph.

        - Add extracted entities to the graph
        - Retrieve related entities for context expansion
        - Find relationships between extracted entities
        """
        try:
            from src.graph import (
                get_graph_client,
                extract_entities as graph_extract_entities,
                extract_relationships,
                add_entities_to_graph,
                add_relationships_to_graph,
                get_graph_retriever,
                expand_context,
            )

            client = get_graph_client()
            retriever = get_graph_retriever()

            # Track graph enrichment results
            graph_enrichment = {
                "entities_added": 0,
                "relationships_added": 0,
                "context_expansions": [],
            }

            # Add entities to graph for each fact
            for fact in facts:
                fact_text = fact.get("text", "")
                source_url = fact.get("source", "")

                if not fact_text:
                    continue

                # Generate chunk ID from fact
                chunk_id = hashlib.md5(fact_text.encode()).hexdigest()[:12]

                # Extract entities from fact text
                extraction_result = graph_extract_entities(
                    text=fact_text,
                    chunk_id=chunk_id,
                    source_url=source_url,
                    use_llm=False  # Use patterns only for speed
                )

                # Add to graph
                if extraction_result.entities:
                    count = add_entities_to_graph(extraction_result, client)
                    graph_enrichment["entities_added"] += count

                    # Extract relationships
                    rel_result = extract_relationships(
                        text=fact_text,
                        entities=extraction_result.entities,
                        chunk_id=chunk_id,
                        source_url=source_url,
                        use_llm=False
                    )

                    if rel_result.relationships:
                        rel_count = add_relationships_to_graph(
                            rel_result,
                            extraction_result,
                            client
                        )
                        graph_enrichment["relationships_added"] += rel_count

            # Expand context for key entities
            for entity in entities[:10]:  # Top 10 entities
                entity_text = entity.get("text", "")
                if not entity_text:
                    continue

                # Search for matching entity in graph
                nodes = client.search_nodes(query=entity_text, limit=1)
                if nodes:
                    # Expand context around this entity
                    expansion = expand_context(
                        entity_id=nodes[0].entity_id,
                        graph_retriever=retriever,
                        depth=1,
                        max_neighbors=5
                    )
                    if expansion.get("total_entities", 0) > 1:
                        graph_enrichment["context_expansions"].append({
                            "entity": entity_text,
                            "neighbors": expansion.get("total_entities", 0),
                            "relationships": expansion.get("total_relationships", 0),
                        })

            # Store enrichment results in state
            state["graph_enrichment"] = graph_enrichment

            logger.info(
                f"Graph enrichment: {graph_enrichment['entities_added']} entities, "
                f"{graph_enrichment['relationships_added']} relationships, "
                f"{len(graph_enrichment['context_expansions'])} expansions"
            )

        except ImportError as e:
            logger.warning(f"Graph module not available for enrichment: {e}")
        except Exception as e:
            logger.error(f"Graph enrichment failed: {e}")

        return state

    def _fetch_content(self, search_results: List[SearchResult]) -> List[SearchResult]:
        """
        Fetch full content for search results that need it.

        P2.5 GAP FIX: Uses context manager for proper socket cleanup.
        """
        import requests

        # Get configurable content limit (LAW VI)
        max_content = self.depth_config.evidence_extraction.max_fetch_content

        # P2.5 GAP FIX: Use session with context manager for proper socket cleanup
        # FIX 100: Add progress logging for content fetch phase
        total_to_fetch = len(search_results)
        fetched_count = 0
        success_count = 0
        logger.info(f"[CONTENT-FETCH] Starting content fetch for {total_to_fetch} URLs")

        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "POLARIS Research Bot/1.0"
            })

            for idx, result in enumerate(search_results):
                if result.content:
                    fetched_count += 1
                    success_count += 1
                    continue  # Already has content

                if result.fetch_status == "failed":
                    fetched_count += 1
                    continue  # Don't retry failed fetches

                try:
                    # P2.5: Session automatically manages connection pooling and cleanup
                    response = session.get(result.url, timeout=10)

                    if response.status_code == 200:
                        # Extract text content with configurable limit
                        content = self._extract_text(response.text)
                        result.content = content[:max_content]
                        result.fetch_status = "success"
                        success_count += 1
                    else:
                        result.fetch_status = "failed"

                except Exception as e:
                    logger.warning(f"Failed to fetch {result.url}: {e}")
                    result.fetch_status = "failed"

                fetched_count += 1

                # FIX 100: Log progress every 20 URLs
                if fetched_count % 20 == 0:
                    logger.info(f"[CONTENT-FETCH] Progress: {fetched_count}/{total_to_fetch} URLs ({success_count} success)")

        logger.info(f"[CONTENT-FETCH] Complete: {success_count}/{total_to_fetch} URLs fetched successfully")
        # Session is automatically closed here, all sockets cleaned up
        return search_results

    def _extract_text(self, html: str) -> str:
        """Extract text content from HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text
            text = soup.get_text(separator="\n")

            # Clean up
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            return text

        except ImportError:
            # Fallback: simple regex extraction
            import re
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            return text.strip()

    def _analyze_batch(
        self,
        batch: List[SearchResult],
        original_query: str,
        state: ResearchState
    ) -> AnalysisOutput:
        """Analyze a batch of search results with SOTA-level depth."""
        # Get configurable limits (LAW VI)
        content_limit = self.depth_config.evidence_extraction.content_chunk_size
        max_claims = self.depth_config.evidence_extraction.max_claims

        # P3.1 GAP FIX: Get extraction limits from extraction.yaml config
        extraction_cfg = _EXTRACTION_CONFIG.get("extraction", {})
        entities_per_source = extraction_cfg.get("entities_per_source", 5)
        facts_per_source = extraction_cfg.get("facts_per_source", 10)
        claims_per_source = extraction_cfg.get("claims_per_source", 5)

        logger.debug(
            f"[P3.1] Using extraction limits: entities={entities_per_source}, "
            f"facts={facts_per_source}, claims={claims_per_source}"
        )

        # Build content for analysis
        source_contents = []
        for result in batch:
            content = result.content or result.snippet
            if not content:
                continue

            source_contents.append(f"""
SOURCE: {result.url}
TITLE: {result.title}
TYPE: {result.source_type}
DOMAIN: {result.domain}

CONTENT:
{content[:content_limit]}
""")

        if not source_contents:
            return AnalysisOutput(
                analyses=[],
                cross_source_entities=[],
                contradictions=[],
                evidence_summary="No content available for analysis"
            )

        sources_text = "\n---\n".join(source_contents)

        # P3.1 GAP FIX: Use config values in prompt instead of hardcoded values
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"""Analyze these sources for the research question.

RESEARCH QUESTION: {original_query}

APPLICATION: {state.get('application', 'Unknown')}
REGION: {state.get('region', 'GLOBAL')}

SOURCES:
{sources_text}

EXTRACTION REQUIREMENTS:
- Extract up to {entities_per_source} named entities per source (people, organizations, chemicals, measurements, regulations)
- Extract up to {facts_per_source} factual statements per source with supporting text
- Extract up to {claims_per_source} verifiable claims per source
- Target {max_claims} total claims across all sources
- Provide source quality assessment (0.0-1.0 scale)
- Assess relevance to research question (0.0-1.0 scale)
- Identify contradictions between sources

Focus on the most relevant and verifiable evidence.""")
        ]

        try:
            analysis: AnalysisOutput = self.call_llm_structured(messages, AnalysisOutput)
            # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
            # Without this check, the caller crashes on analysis.analyses when analysis is None
            if analysis is None:
                logger.warning("LLM returned None for batch analysis (timeout or parsing failure), skipping batch")
                return AnalysisOutput(
                    analyses=[],
                    cross_source_entities=[],
                    contradictions=[],
                    evidence_summary="Analysis timed out or failed to parse"
                )
            return analysis
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return AnalysisOutput(
                analyses=[],
                cross_source_entities=[],
                contradictions=[],
                evidence_summary=f"Analysis failed: {str(e)}"
            )

    def _analyze_batch_deep(
        self,
        batch: List[SearchResult],
        original_query: str,
        state: ResearchState,
        first_pass_results: List[dict]
    ) -> AnalysisOutput:
        """
        W3.1 SOTA: Second-pass deep extraction for high-quality sources.

        This method performs deeper analysis focusing on:
        - Supporting evidence for existing claims
        - Counterarguments and contradicting evidence
        - Relationships between entities
        - Statistical data and measurements
        - Methodology and limitations

        Only called for sources that meet the quality threshold.
        """
        if not _MULTI_PASS_CONFIG.get("enabled", True):
            # Return empty if multi-pass disabled
            return AnalysisOutput(
                analyses=[],
                cross_source_entities=[],
                contradictions=[],
                evidence_summary="Multi-pass disabled"
            )

        content_limit = self.depth_config.evidence_extraction.content_chunk_size
        evidence_per_pass = _MULTI_PASS_CONFIG.get("evidence_per_pass", 15)

        # Build content for deep analysis
        source_contents = []
        for result in batch:
            content = result.content or result.snippet
            if not content:
                continue

            source_contents.append(f"""
SOURCE: {result.url}
TITLE: {result.title}
TYPE: {result.source_type}
DOMAIN: {result.domain}

CONTENT:
{content[:content_limit]}
""")

        if not source_contents:
            return AnalysisOutput(
                analyses=[],
                cross_source_entities=[],
                contradictions=[],
                evidence_summary="No content for deep analysis"
            )

        sources_text = "\n---\n".join(source_contents)

        # Build context from first pass results
        first_pass_context = ""
        if first_pass_results:
            facts_summary = [r.get("text", "")[:100] for r in first_pass_results[:10]]
            first_pass_context = f"""

FIRST PASS FINDINGS (for context):
{chr(10).join(f'- {f}' for f in facts_summary if f)}
"""

        # Deep analysis prompt - focus on supporting evidence and relationships
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"""Perform DEEP SECOND-PASS analysis on these sources.

RESEARCH QUESTION: {original_query}

APPLICATION: {state.get('application', 'Unknown')}
REGION: {state.get('region', 'GLOBAL')}
{first_pass_context}
SOURCES:
{sources_text}

SECOND-PASS EXTRACTION (Focus on what first pass might have missed):
1. SUPPORTING EVIDENCE: Find specific data, statistics, or quotes that support the main claims
2. COUNTERARGUMENTS: Identify any contradicting evidence, caveats, or limitations
3. RELATIONSHIPS: Identify connections between entities (e.g., "X causes Y", "A regulates B")
4. METHODOLOGY: Extract study design, sample sizes, confidence intervals if available
5. CONTEXT: Historical context, geographic specifics, regulatory frameworks

Extract up to {evidence_per_pass} deep evidence items per source.
Focus on quantitative data, specific citations, and nuanced findings.""")
        ]

        try:
            analysis: AnalysisOutput = self.call_llm_structured(messages, AnalysisOutput)
            if analysis is None:
                logger.warning("Deep analysis returned None, skipping")
                return AnalysisOutput(
                    analyses=[],
                    cross_source_entities=[],
                    contradictions=[],
                    evidence_summary="Deep analysis timed out"
                )

            logger.info(
                f"[W3.1 MULTI-PASS] Second pass extracted "
                f"{sum(len(a.facts) for a in analysis.analyses)} additional facts"
            )
            return analysis

        except Exception as e:
            logger.error(f"Deep analysis failed: {e}")
            return AnalysisOutput(
                analyses=[],
                cross_source_entities=[],
                contradictions=[],
                evidence_summary=f"Deep analysis failed: {str(e)}"
            )

    def _analyze_multimodal(
        self,
        search_results: List[SearchResult],
        original_query: str
    ) -> Dict[str, Any]:
        """
        Analyze multimodal content (PDFs, images) from search results.

        Uses Gemini vision for image/chart analysis and PDF parsing
        for document extraction.

        Args:
            search_results: Search results that may contain PDFs or images
            original_query: Research question for context

        Returns:
            Dict with multimodal analysis results
        """
        multimodal_results = {
            "pdf_analyses": [],
            "image_analyses": [],
            "extracted_data": [],
        }

        try:
            from src.tools import (
                get_vision_client,
                get_pdf_parser,
                analyze_research_image,
                quick_pdf_extract,
            )

            # Identify multimodal content
            for result in search_results:
                url = result.url.lower()

                # Check for PDFs
                if url.endswith(".pdf"):
                    try:
                        # For remote PDFs, we'd need to download first
                        # For now, log and skip remote PDFs
                        if url.startswith("http"):
                            logger.info(f"Skipping remote PDF: {result.url}")
                            continue

                        pdf_data = quick_pdf_extract(result.url)

                        if "error" not in pdf_data:
                            multimodal_results["pdf_analyses"].append({
                                "url": result.url,
                                "metadata": pdf_data.get("metadata", {}),
                                "table_count": len(pdf_data.get("tables", [])),
                                "text_preview": pdf_data.get("text", "")[:1000],
                                "tables": pdf_data.get("tables", [])[:5],  # Limit tables
                            })

                            # Add tables as extracted data
                            for table in pdf_data.get("tables", [])[:5]:
                                multimodal_results["extracted_data"].append({
                                    "type": "table",
                                    "source": result.url,
                                    "headers": table.get("headers", []),
                                    "row_count": len(table.get("rows", [])),
                                })

                    except Exception as e:
                        logger.warning(f"PDF analysis failed for {result.url}: {e}")

                # Check for images
                elif any(url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    try:
                        # For remote images, we can pass URL to vision client
                        if url.startswith("http"):
                            image_data = analyze_research_image(
                                result.url,
                                context=original_query
                            )

                            if "error" not in image_data.get("general_analysis", {}):
                                multimodal_results["image_analyses"].append({
                                    "url": result.url,
                                    "image_type": image_data.get("image_type", "other"),
                                    "analysis": image_data.get("general_analysis", {}),
                                    "chart_data": image_data.get("chart_data"),
                                    "table_data": image_data.get("table_data"),
                                })

                                # Add chart/table data as extracted data
                                if image_data.get("chart_data"):
                                    multimodal_results["extracted_data"].append({
                                        "type": "chart",
                                        "source": result.url,
                                        "chart_type": image_data["chart_data"].get("chart_type"),
                                        "title": image_data["chart_data"].get("title"),
                                    })

                    except Exception as e:
                        logger.warning(f"Image analysis failed for {result.url}: {e}")

        except ImportError as e:
            logger.warning(f"Multimodal tools not available: {e}")
        except Exception as e:
            logger.error(f"Multimodal analysis failed: {e}")

        logger.info(
            f"Multimodal analysis: {len(multimodal_results['pdf_analyses'])} PDFs, "
            f"{len(multimodal_results['image_analyses'])} images"
        )

        return multimodal_results


# =============================================================================
# Multimodal Analysis Functions
# =============================================================================

def analyze_pdf_source(
    file_path: str,
    query: str,
    extract_tables: bool = True,
    analyze_images: bool = False
) -> Dict[str, Any]:
    """
    Analyze a PDF document for research.

    Args:
        file_path: Path to PDF file
        query: Research question for context
        extract_tables: Whether to extract tables
        analyze_images: Whether to analyze images in PDF

    Returns:
        Analysis results with text, tables, and findings
    """
    try:
        from src.tools import get_pdf_parser, get_vision_client

        parser = get_pdf_parser(use_vision=analyze_images)
        result = parser.parse(
            file_path=file_path,
            extract_images=analyze_images,
            extract_tables=extract_tables,
            analyze_images=analyze_images,
            max_pages=30
        )

        return {
            "file_path": file_path,
            "page_count": result.metadata.page_count,
            "text": result.full_text,
            "tables": [t.model_dump() for p in result.pages for t in p.tables],
            "image_count": result.image_count,
            "metadata": result.metadata.model_dump(),
        }

    except Exception as e:
        logger.error(f"PDF analysis failed: {e}")
        return {"error": str(e)}


def analyze_image_source(
    image_path: str,
    query: str
) -> Dict[str, Any]:
    """
    Analyze an image for research.

    Args:
        image_path: Path or URL to image
        query: Research question for context

    Returns:
        Analysis results with extracted data
    """
    try:
        from src.tools import analyze_research_image

        return analyze_research_image(image_path, context=query)

    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        return {"error": str(e)}


# =============================================================================
# Standalone function
# =============================================================================

def analyze_source(
    url: str,
    content: str,
    query: str
) -> SourceAnalysis:
    """
    Standalone function to analyze a single source.

    Args:
        url: Source URL
        content: Source content
        query: Research question

    Returns:
        SourceAnalysis with extracted information
    """
    from src.orchestration.state import create_initial_state

    state = create_initial_state(
        vector_id="standalone",
        query=query,
        application="unknown",
        region="GLOBAL",
        stage=1
    )

    # Create mock search result
    result = SearchResult(
        result_id="standalone_001",
        url=url,
        title="Standalone Analysis",
        snippet=content[:500],
        source_type="web",
        domain=url.split("/")[2] if "/" in url else url,
        fetch_status="success",
        content=content,
    )

    state["search_results"] = [result]

    agent = AnalystAgent()
    result_state = agent.invoke(state)

    # MED-018, MED-019, MED-020: Default scores from config
    default_confidence = get_threshold("scoring.default_confidence", 0.8)
    default_quality = get_threshold("scoring.default_quality", 0.5)
    default_relevance = get_threshold("scoring.default_relevance", 0.5)

    # Return first analysis if available
    evidence = result_state.get("evidence_chain", [])
    if evidence:
        ev = evidence[0]
        return SourceAnalysis(
            source_url=url,
            source_quality=ev.source_quality_score,
            relevance_score=ev.relevance_score,
            entities=[
                ExtractedEntity(
                    text=e,
                    entity_type="ORGANIZATION",  # Default
                    confidence=default_confidence,
                    context=""
                )
                for e in ev.entities
            ],
            facts=[
                ExtractedFact(
                    fact_text=c,
                    fact_type="factual",
                    confidence=default_confidence,
                    supporting_text=ev.text,
                    entities_involved=[]
                )
                for c in ev.claims
            ],
            claims=[],
            key_findings=ev.claims,
            limitations=[]
        )

    return SourceAnalysis(
        source_url=url,
        source_quality=default_quality,
        relevance_score=default_relevance,
        entities=[],
        facts=[],
        claims=[],
        key_findings=[],
        limitations=["Analysis failed or no content extracted"]
    )
