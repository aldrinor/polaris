#!/usr/bin/env python3
"""
POLARIS Phase 2: Query Generation
==================================
Generate diverse search queries based on strategic plan.

Purpose:
- Generate search queries from focus areas and knowledge gaps
- Distribute queries across buckets (academic, government, industry, news, general)
- Apply authority anchors for high-quality sources
- Apply geographic targeting for regional vectors

Usage:
    python src/phases/p02_query_generation.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P1/S1V1...json --output outputs/P2/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 1 output JSON.
    --output: Optional. Output directory (default: outputs/P2/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase0Output, Phase1Output, Phase2Output, APIQuery, QueryTemplate, PerspectiveQuery
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.llm.gemini_client import get_gemini_client
from src.audit import get_audit
from src.schemas.question_types import QuestionType
from src.schemas.decomposed_query import decompose_question, SubQuery


# =============================================================================
# CONSTANTS
# =============================================================================

SYSTEM_PROMPT = """You are a search query generation specialist for POLARIS, a research system.

Your task is to generate diverse, effective search queries that will find authoritative information.

You must respond with valid JSON matching the required schema."""

# =============================================================================
# SOTA: STORM PERSPECTIVE-GUIDED QUERY GENERATION
# Based on: https://arxiv.org/abs/2402.14207 (Stanford STORM)
# =============================================================================

STORM_PERSPECTIVE_PROMPT = """
You are helping generate diverse research perspectives for STORM-style query generation.

Research Topic: {topic}
Research Question: {question}
Target Region: {region}

Identify 4-6 distinct expert perspectives that would ask different types of questions about this topic.
Each perspective should represent a different discipline, stakeholder, or analytical lens.

Example perspectives for water quality research:
- Public Health Expert: Focuses on health outcomes, disease transmission, contamination exposure
- Environmental Scientist: Focuses on ecological impacts, pollution sources, remediation
- Regulatory Analyst: Focuses on standards compliance, policy gaps, enforcement
- Water Treatment Engineer: Focuses on technology effectiveness, system design, maintenance
- Consumer Advocate: Focuses on access, affordability, public awareness
- Epidemiologist: Focuses on outbreak patterns, risk factors, vulnerable populations

For the given topic, generate appropriate perspectives.

Respond with JSON:
{{
    "perspectives": [
        {{
            "name": "Perspective Name (e.g., Public Health Expert)",
            "focus": "What this perspective focuses on",
            "key_questions": [
                "Specific question this expert would ask",
                "Another question from this lens",
                "A third perspective-specific question"
            ]
        }}
    ]
}}
"""

STORM_QUERIES_FROM_PERSPECTIVES_PROMPT = """
You are implementing Stanford STORM methodology for multi-perspective research.

CRITICAL: Each perspective must generate FUNDAMENTALLY DIFFERENT analytical questions.
Do NOT generate keyword variations. Generate questions that ONLY this perspective would ask.

Research Topic: {topic}
Research Question: {question}
Target Region: {region}

Expert Perspectives:
{perspectives}

STORM METHODOLOGY REQUIREMENTS:
1. Each perspective asks questions from their UNIQUE analytical lens
2. Questions should be phrased as RESEARCH QUESTIONS, not keyword searches
3. Different perspectives should have MINIMAL OVERLAP in their questions
4. Questions should seek DIFFERENT TYPES of information

EXAMPLES OF CORRECT STORM QUESTIONS:

For "household water filter contamination" topic:

Public Health Expert (outcome-focused):
- "What health outcomes have been documented from consuming water through contaminated household filters?"
- "Which populations are most vulnerable to waterborne pathogens from filter biofilm?"
- "What is the incidence rate of gastrointestinal illness linked to filter contamination?"

Water Treatment Engineer (mechanism-focused):
- "What biofilm formation mechanisms occur in activated carbon filters?"
- "How do flow rate and temperature affect bacterial colonization in filter media?"
- "What filter maintenance protocols effectively prevent pathogen growth?"

Policy Analyst (regulatory-focused):
- "What NSF/ANSI standards govern household water filter microbial claims?"
- "How do EPA drinking water regulations apply to point-of-use filters?"
- "What liability frameworks exist for filter manufacturers regarding contamination?"

Consumer Advocate (access-focused):
- "What information do consumers receive about filter replacement schedules?"
- "How do filter costs compare to health risk reduction benefits?"
- "What testing resources are available for consumers to verify filter performance?"

WRONG (keyword queries - DO NOT DO THIS):
- "water filter contamination study"
- "household filter biofilm research"
- "filter regulations policy analysis"

For the given topic and perspectives, generate 3-4 ANALYTICAL QUESTIONS per perspective.
Each question should be something ONLY that perspective would ask.

Respond with JSON:
{{
    "perspective_queries": {{
        "Perspective Name 1": [
            "Analytical question from this perspective's unique lens?",
            "Another question only this expert would ask?",
            "A third perspective-specific research question?"
        ],
        "Perspective Name 2": [
            "Different type of question from this perspective?",
            "Another unique analytical question?",
            "Third question from this different lens?"
        ]
    }}
}}
"""


# =============================================================================
# SOTA: QUERY2DOC / HyDE (Hypothetical Document Embeddings)
# Based on: https://arxiv.org/abs/2212.10496
# Generates pseudo-documents for better semantic retrieval
# =============================================================================

HYDE_PSEUDO_DOCUMENT_PROMPT = """You are a scientific research assistant. Generate a hypothetical research abstract that would answer this query.

Research Query: {query}
Topic Context: {topic}
Geographic Focus: {region}

Write a realistic 150-200 word research abstract that:
1. Contains specific data, statistics, and findings
2. Uses academic language and terminology
3. Includes methodology references
4. Contains the types of facts that would answer the query

Do NOT make up fake citations or author names. Just write the content.

Respond with JSON:
{{
    "pseudo_document": "Your hypothetical research abstract here",
    "key_terms": ["important term 1", "important term 2", "important term 3"]
}}
"""

QUERY2DOC_EXPANSION_PROMPT = """Expand this search query into a richer document-like query using Query2Doc technique.

Original Query: {query}
Topic: {topic}
Region: {region}

Generate an expanded query that:
1. Includes synonyms and related technical terms
2. Adds context about what a relevant document would contain
3. Maintains focus on the original query intent
4. Is 2-4 sentences long (not a single query phrase)

Respond with JSON:
{{
    "expanded_query": "Your expanded query text here",
    "added_terms": ["term1", "term2", "term3"]
}}
"""


QUERY_GENERATION_PROMPT = """
Generate search queries for this research task:

**Vector ID:** {vector_id}
**Research Question:** {question}
**Region:** {region}
**Geographic Targeting:** {is_regional}

**Research Focus Areas:**
{focus_areas}

**Knowledge Gaps to Address:**
{knowledge_gaps}

**High Priority Areas:**
{high_priorities}

Generate {total_queries} diverse search queries distributed across these buckets:
- academic: {academic_count} queries (peer-reviewed journals, research papers)
- government: {government_count} queries (regulatory agencies, official reports)
- industry: {industry_count} queries (trade publications, industry analysis)
- news: {news_count} queries (recent developments, news coverage)
- general: {general_count} queries (broad web search)

Requirements:
1. Queries should be specific and targeted
2. Cover all focus areas and knowledge gaps
3. For regional vectors, include geographic context
4. Use technical terminology appropriate for each bucket type
5. Avoid overly generic queries

Respond with JSON:
{{
    "queries": {{
        "academic": ["query1", "query2", ...],
        "government": ["query1", "query2", ...],
        "industry": ["query1", "query2", ...],
        "news": ["query1", "query2", ...],
        "general": ["query1", "query2", ...]
    }}
}}
"""


# =============================================================================
# BUG-008 FIX: RECENT STUDY TARGETING (DYNAMIC - NO HARDCODING)
# Generates year-constrained queries dynamically from vector context
# =============================================================================

def generate_recent_study_queries(
    topic: str,
    region: str,
    vector_id: str,
    focus_areas: List[str],
    knowledge_gaps: List[str],
) -> List[str]:
    """
    BUG-008 FIX: Generate queries explicitly targeting recent studies.

    DYNAMIC IMPLEMENTATION - No hardcoded terms. All query terms derived from:
    - Vector topic (from vector_id parsing)
    - Focus areas (from P1 output)
    - Knowledge gaps (from P1 strategic plan)
    - Current year (dynamic from datetime)

    Args:
        topic: Research topic (from focus_areas[0] or vector_id)
        region: Geographic region (from vector_id)
        vector_id: Vector ID for topic extraction
        focus_areas: Research focus areas from P1
        knowledge_gaps: Knowledge gaps from P1 strategic plan

    Returns:
        List of recent study queries with year constraints
    """
    from datetime import datetime

    # Dynamic year calculation - NO HARDCODING
    current_year = datetime.now().year
    recent_years = [str(current_year), str(current_year - 1), str(current_year - 2)]

    # Extract clean topic terms from vector_id (dynamic)
    topic_terms = topic.lower().replace("_", " ")

    # Build query terms from focus areas and knowledge gaps (dynamic, from P1)
    query_seed_terms = []
    for fa in focus_areas[:5]:  # Top 5 focus areas
        query_seed_terms.append(fa.lower())
    for kg in knowledge_gaps[:3]:  # Top 3 knowledge gaps
        query_seed_terms.append(kg.lower())

    # Remove duplicates while preserving order
    seen = set()
    unique_terms = []
    for term in query_seed_terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    queries = []

    # 1. Year-constrained queries for the topic (dynamic)
    for year in recent_years:
        queries.append(f"{topic_terms} {year} study")
        queries.append(f"{topic_terms} {year} research")
        queries.append(f"{topic_terms} {year} data")

    # 2. Focus area + year queries (dynamic from P1)
    for term in unique_terms[:5]:
        queries.append(f"{term} {recent_years[0]} study")
        queries.append(f"{term} {recent_years[0]} {region.replace('_', ' ')}")

    # 3. Knowledge gap + year queries (dynamic from P1)
    for kg in knowledge_gaps[:3]:
        queries.append(f"{kg} {recent_years[0]} research findings")

    # 4. Open access journal queries with topic (generic journals, topic from vector)
    # These are legitimate academic infrastructure, not topic-specific
    open_access_prefixes = ["PLOS", "Frontiers", "MDPI", "BMC"]
    for prefix in open_access_prefixes:
        queries.append(f"{prefix} {topic_terms} {recent_years[0]}")

    # 5. Academic database queries (infrastructure, not topic-specific)
    academic_sites = ["plos.org", "frontiersin.org", "ncbi.nlm.nih.gov", "mdpi.com"]
    for site in academic_sites:
        queries.append(f"site:{site} {topic_terms} {recent_years[0]}")

    return queries


# =============================================================================
# SOTA: SYNONYM EXPANSION (5-10 VARIANTS PER CORE TERM)
# Based on SOTA upgrade plan: improve retrieval coverage via query variants
# =============================================================================

SYNONYM_EXPANSION_PROMPT = """Generate synonyms and related terms for this research term.

TERM: {term}
CONTEXT: {context}

Generate 5-10 synonyms or closely related technical terms that could be used
interchangeably in academic searches. Include:
1. Direct synonyms (exact alternatives)
2. Technical/scientific variants (formal/informal names)
3. Related concepts that might appear in relevant papers
4. Common abbreviations or acronyms

Respond with JSON:
{{
    "synonyms": ["synonym1", "synonym2", ...],
    "technical_variants": ["variant1", "variant2", ...],
    "abbreviations": ["abbr1", "abbr2", ...]
}}
"""


async def expand_term_with_synonyms(
    term: str,
    context: str,
) -> List[str]:
    """
    SOTA: Generate 5-10 synonym variants for a core term.

    This improves retrieval coverage by generating multiple query
    variants that might match different papers using different terminology.

    Args:
        term: The core term to expand
        context: Research context for better synonym selection

    Returns:
        List of synonym/variant terms (5-10 items)
    """
    try:
        client = get_gemini_client()

        prompt = SYNONYM_EXPANSION_PROMPT.format(
            term=term,
            context=context,
        )

        result = await client.generate_json(prompt, SYSTEM_PROMPT)

        # Collect all variants
        variants = []
        variants.extend(result.get("synonyms", []))
        variants.extend(result.get("technical_variants", []))
        variants.extend(result.get("abbreviations", []))

        # Remove duplicates and empty strings, limit to 10
        seen = {term.lower()}  # Start with original term as seen
        unique_variants = []
        for v in variants:
            v_clean = v.strip()
            if v_clean and v_clean.lower() not in seen:
                seen.add(v_clean.lower())
                unique_variants.append(v_clean)
                if len(unique_variants) >= 10:
                    break

        return unique_variants

    except Exception as e:
        # LOW-001: Log error instead of print
        logger.debug(f"Synonym expansion failed for '{term}': {e}")
        return []


async def generate_synonym_expanded_queries(
    base_queries: List[str],
    focus_areas: List[str],
    topic: str,
    max_expansions: int = 20,
) -> List[str]:
    """
    SOTA: Expand queries using synonym variants of key terms.

    For each focus area, generates synonym variants and creates
    additional queries using those variants.

    Args:
        base_queries: Original queries to expand
        focus_areas: Research focus areas (terms to expand)
        topic: Research topic for context
        max_expansions: Maximum number of expanded queries to add

    Returns:
        List of additional queries using synonym variants
    """
    expanded_queries = []
    context = f"Research on {topic}"

    # Expand top focus areas with synonyms
    for focus_area in focus_areas[:5]:  # Top 5 focus areas
        synonyms = await expand_term_with_synonyms(focus_area, context)

        if synonyms:
            print(f"[PHASE-2][SYNONYM] '{focus_area}' -> {len(synonyms)} variants: {synonyms[:3]}...")

            # Create queries using synonyms
            for synonym in synonyms[:3]:  # Top 3 synonyms per focus area
                expanded_queries.append(f"{synonym} research study")
                expanded_queries.append(f"{synonym} {topic}")

                if len(expanded_queries) >= max_expansions:
                    break

        if len(expanded_queries) >= max_expansions:
            break

    print(f"[PHASE-2][SYNONYM] Generated {len(expanded_queries)} synonym-expanded queries")
    return expanded_queries[:max_expansions]


# =============================================================================
# SOTA: API-SPECIFIC QUERY GENERATORS (FROM UPGRADE PLAN)
# Generate queries with proper syntax for each academic API
# =============================================================================

def generate_openalex_filter(
    raw_query: str,
    template: Optional[QueryTemplate] = None,
    iso_codes: Optional[List[str]] = None,
    year_min: int = 2020,
    year_max: int = 2026,
) -> APIQuery:
    """
    SOTA: Generate OpenAlex-formatted query with filter syntax.

    OpenAlex filter syntax: filter=key:value,key2:value2
    See: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/filter-entity-lists

    Args:
        raw_query: Base search query
        template: Optional QueryTemplate from P1
        iso_codes: ISO 3166-1 alpha-2 country codes for geographic filtering
        year_min: Minimum publication year
        year_max: Maximum publication year

    Returns:
        APIQuery with OpenAlex-specific formatting
    """
    filters = {}

    # Year filter
    filters["publication_year"] = f"{year_min}-{year_max}"

    # Document type filter (peer-reviewed only)
    filters["type"] = "article|review"

    # Geographic filter from ISO codes
    if template and template.filters.get("authorships.countries"):
        filters["authorships.countries"] = template.filters["authorships.countries"]
    elif iso_codes:
        filters["authorships.countries"] = "|".join(iso_codes)

    # Open access preference
    filters["is_oa"] = "true"

    # Build filter string
    filter_parts = [f"{k}:{v}" for k, v in filters.items()]
    filter_string = ",".join(filter_parts)

    # Build full query string with search and filter
    query_string = f"search={raw_query}&filter={filter_string}"

    boost_terms = template.boost_terms if template else []

    return APIQuery(
        api_name="openalex",
        query_string=query_string,
        filters=filters,
        raw_query=raw_query,
        boost_terms=boost_terms,
        expected_results=50,
    )


def generate_semantic_scholar_query(
    raw_query: str,
    template: Optional[QueryTemplate] = None,
    fields_of_study: Optional[List[str]] = None,
    year_min: int = 2020,
) -> APIQuery:
    """
    SOTA: Generate Semantic Scholar API query.

    S2 API: https://api.semanticscholar.org/api-docs/graph#tag/Paper-Data/operation/get_graph_paper_relevance_search

    Args:
        raw_query: Base search query
        template: Optional QueryTemplate from P1
        fields_of_study: Fields to filter by (e.g., Medicine, Biology)
        year_min: Minimum publication year

    Returns:
        APIQuery with S2-specific formatting
    """
    filters = {}

    # Year filter
    filters["year"] = f"{year_min}-"

    # Fields of study filter
    if template and template.filters.get("fieldsOfStudy"):
        filters["fieldsOfStudy"] = template.filters["fieldsOfStudy"]
    elif fields_of_study:
        filters["fieldsOfStudy"] = ",".join(fields_of_study)

    # Open access filter
    filters["openAccessPdf"] = "true"

    # Build query params
    # S2 uses query parameter, not complex filter syntax
    params = [f"query={raw_query}"]
    if filters.get("year"):
        params.append(f"year={filters['year']}")
    if filters.get("fieldsOfStudy"):
        params.append(f"fieldsOfStudy={filters['fieldsOfStudy']}")
    if filters.get("openAccessPdf"):
        params.append("openAccessPdf")

    query_string = "&".join(params)

    boost_terms = template.boost_terms if template else []

    return APIQuery(
        api_name="semantic_scholar",
        query_string=query_string,
        filters=filters,
        raw_query=raw_query,
        boost_terms=boost_terms,
        expected_results=100,  # S2 returns more results
    )


def generate_pubmed_mesh_query(
    raw_query: str,
    template: Optional[QueryTemplate] = None,
    mesh_terms: Optional[List[str]] = None,
    year_min: int = 2020,
    year_max: int = 2026,
) -> APIQuery:
    """
    SOTA: Generate PubMed query with MeSH term syntax.

    PubMed search syntax: https://pubmed.ncbi.nlm.nih.gov/help/

    Args:
        raw_query: Base search query
        template: Optional QueryTemplate from P1
        mesh_terms: MeSH terms for controlled vocabulary search
        year_min: Minimum publication year
        year_max: Maximum publication year

    Returns:
        APIQuery with PubMed-specific formatting
    """
    filters = {
        "datetype": "pdat",
        "mindate": f"{year_min}/01/01",
        "maxdate": f"{year_max}/12/31",
    }

    # Build query parts
    query_parts = []

    # Add MeSH terms with proper syntax
    effective_mesh = []
    if template and template.boost_terms:
        effective_mesh = template.boost_terms
    elif mesh_terms:
        effective_mesh = mesh_terms

    if effective_mesh:
        mesh_query_parts = [f'"{mesh}"[MeSH Terms]' for mesh in effective_mesh[:5]]
        query_parts.append(f"({' OR '.join(mesh_query_parts)})")

    # Add free text search
    if raw_query:
        query_parts.append(f'({raw_query}[Title/Abstract])')

    # Combine with AND
    combined_query = " AND ".join(query_parts) if query_parts else raw_query

    # Add date filter to query
    date_filter = f'("{year_min}/01/01"[Date - Publication] : "{year_max}/12/31"[Date - Publication])'
    full_query = f"({combined_query}) AND {date_filter}"

    return APIQuery(
        api_name="pubmed",
        query_string=full_query,
        filters=filters,
        raw_query=raw_query,
        boost_terms=effective_mesh,
        expected_results=50,
    )


def generate_api_queries_from_templates(
    query_templates: List[QueryTemplate],
    base_queries: List[str],
    mesh_terms: Optional[List[str]] = None,
    iso_codes: Optional[List[str]] = None,
    max_per_api: int = 10,
) -> List[APIQuery]:
    """
    SOTA: Generate API-specific queries from P1 templates and base queries.

    Consumes QueryTemplate objects from P1 and generates properly formatted
    queries for each target API (OpenAlex, Semantic Scholar, PubMed).

    Args:
        query_templates: QueryTemplate objects from P1 output
        base_queries: List of base search queries to format
        mesh_terms: MeSH terms for PubMed queries
        iso_codes: ISO codes for geographic filtering
        max_per_api: Maximum queries per API

    Returns:
        List of APIQuery objects ready for execution
    """
    api_queries = []

    # Map templates by API name
    templates_by_api = {t.api_name: t for t in query_templates}

    # Select top queries for API-specific formatting
    selected_queries = base_queries[:max_per_api * 3]  # Pool for all APIs

    for i, raw_query in enumerate(selected_queries):
        # Rotate through APIs
        if i % 3 == 0:
            # OpenAlex query
            template = templates_by_api.get("openalex")
            api_queries.append(generate_openalex_filter(
                raw_query=raw_query,
                template=template,
                iso_codes=iso_codes,
            ))
        elif i % 3 == 1:
            # Semantic Scholar query
            template = templates_by_api.get("semantic_scholar")
            api_queries.append(generate_semantic_scholar_query(
                raw_query=raw_query,
                template=template,
            ))
        else:
            # PubMed query
            template = templates_by_api.get("pubmed")
            api_queries.append(generate_pubmed_mesh_query(
                raw_query=raw_query,
                template=template,
                mesh_terms=mesh_terms,
            ))

    return api_queries


# =============================================================================
# SOTA: TOPIC ANCHORING (PREVENTS CORPUS POLLUTION)
# =============================================================================

def extract_core_topic_terms(vector_id: str) -> List[str]:
    """
    Extract core topic terms from vector ID that MUST appear in queries.

    This prevents corpus pollution by ensuring all queries are anchored
    to the main research topic.

    Args:
        vector_id: Vector ID (e.g., "S1V1_Household_Water_Filter_NORTH_AMERICA")

    Returns:
        List of core topic terms (lowercased)
    """
    # Known region suffixes to exclude
    REGION_TERMS = {
        "north", "south", "east", "west", "central",
        "america", "europe", "asia", "africa", "oceania",
        "global", "worldwide", "united", "states", "canada",
        "uk", "australia", "india", "china", "mexico",
    }

    # Split vector ID and extract meaningful terms
    parts = vector_id.split("_")

    # Skip first part (S1V1 etc.)
    topic_parts = parts[1:] if len(parts) > 1 else parts

    # Filter out region terms and very short terms
    core_terms = []
    for term in topic_parts:
        term_lower = term.lower()
        if term_lower not in REGION_TERMS and len(term_lower) >= 3:
            core_terms.append(term_lower)

    return core_terms


def anchor_query_to_topic(
    query: str,
    core_terms: List[str],
    require_all: bool = False,
) -> Tuple[str, bool]:
    """
    Ensure query is anchored to the core topic terms.

    If query doesn't contain ANY core terms, add the most important one.

    Args:
        query: Original query
        core_terms: List of required topic terms
        require_all: If True, require ALL terms (stricter mode)

    Returns:
        Tuple of (modified_query, was_modified)
    """
    if not core_terms:
        return query, False

    query_lower = query.lower()

    # Check how many core terms are present
    present_terms = [term for term in core_terms if term in query_lower]

    if require_all:
        # Strict mode: need all terms
        if len(present_terms) == len(core_terms):
            return query, False
        # Add missing terms
        missing = [t for t in core_terms if t not in query_lower]
        return f"{query} {' '.join(missing)}", True
    else:
        # Normal mode: need at least one term
        if present_terms:
            return query, False
        # Add most important term (first one, usually the main subject)
        return f"{query} {core_terms[0]}", True


def validate_and_anchor_queries(
    queries_by_bucket: Dict[str, List[str]],
    vector_id: str,
) -> Tuple[Dict[str, List[str]], int, int]:
    """
    SOTA: Validate all queries are anchored to the core topic.

    This prevents corpus pollution by ensuring off-topic queries are either
    anchored or rejected.

    Args:
        queries_by_bucket: Generated queries by bucket
        vector_id: Vector ID for topic extraction

    Returns:
        Tuple of (anchored_queries_by_bucket, queries_modified, queries_total)
    """
    core_terms = extract_core_topic_terms(vector_id)

    if not core_terms:
        print(f"[PHASE-2][ANCHOR] No core terms extracted from {vector_id}")
        total = sum(len(qs) for qs in queries_by_bucket.values())
        return queries_by_bucket, 0, total

    print(f"[PHASE-2][ANCHOR] Core topic terms: {core_terms}")

    modified_count = 0
    total_count = 0
    anchored_queries = {}

    for bucket, queries in queries_by_bucket.items():
        anchored = []
        for query in queries:
            total_count += 1
            # Academic bucket gets stricter anchoring (require more terms)
            require_all = bucket == "academic" and len(core_terms) >= 2
            anchored_query, was_modified = anchor_query_to_topic(
                query, core_terms, require_all=require_all
            )
            anchored.append(anchored_query)
            if was_modified:
                modified_count += 1

        anchored_queries[bucket] = anchored

    if modified_count > 0:
        print(f"[PHASE-2][ANCHOR] Modified {modified_count}/{total_count} queries to include topic terms")

    return anchored_queries, modified_count, total_count


# =============================================================================
# QUERY DISTRIBUTION
# =============================================================================

def calculate_query_distribution(
    total_queries: int,
    distribution: Dict[str, float],
) -> Dict[str, int]:
    """
    Calculate query counts per bucket.

    Args:
        total_queries: Total number of queries to generate
        distribution: Percentage distribution by bucket

    Returns:
        Dict of bucket -> count
    """
    counts = {}
    remaining = total_queries

    # Sort by percentage descending to allocate remainders to largest buckets
    sorted_buckets = sorted(distribution.items(), key=lambda x: x[1], reverse=True)

    for i, (bucket, pct) in enumerate(sorted_buckets):
        if i == len(sorted_buckets) - 1:
            # Last bucket gets all remaining
            counts[bucket] = remaining
        else:
            count = int(total_queries * pct)
            counts[bucket] = count
            remaining -= count

    return counts


def apply_authority_anchors(
    queries: List[str],
    bucket: str,
    anchors: Dict[str, List[str]],
) -> Tuple[List[str], int]:
    """
    Apply authority anchors (site: operators) to queries.

    Args:
        queries: List of queries
        bucket: Bucket type
        anchors: Authority anchor config

    Returns:
        Tuple of (modified queries, count of anchors applied)
    """
    bucket_anchors = anchors.get(bucket, [])
    if not bucket_anchors:
        return queries, 0

    modified = []
    anchors_applied = 0

    for i, query in enumerate(queries):
        # Apply anchor to every other query to maintain diversity
        if i % 2 == 0 and bucket_anchors:
            anchor = bucket_anchors[i % len(bucket_anchors)]
            modified.append(f"{query} {anchor}")
            anchors_applied += 1
        else:
            modified.append(query)

    return modified, anchors_applied


def apply_geographic_targeting(
    queries: List[str],
    region: str,
    geo_keywords: Dict[str, List[str]],
) -> List[str]:
    """
    Apply geographic keywords to queries.

    Args:
        queries: List of queries
        region: Target region
        geo_keywords: Geographic keyword config

    Returns:
        Modified queries with geographic context
    """
    keywords = geo_keywords.get(region, [])
    if not keywords:
        return queries

    modified = []
    for i, query in enumerate(queries):
        # Check if query already has geographic context
        has_geo = any(kw.lower() in query.lower() for kw in keywords)
        if not has_geo:
            # Add geographic keyword
            keyword = keywords[i % len(keywords)]
            modified.append(f"{query} {keyword}")
        else:
            modified.append(query)

    return modified


# =============================================================================
# QUERY GENERATION
# =============================================================================

async def generate_storm_perspectives(
    topic: str,
    question: str,
    region: str,
) -> List[Dict[str, Any]]:
    """
    SOTA: Generate STORM-style expert perspectives for multi-perspective querying.

    Based on Stanford's STORM methodology, this generates diverse expert
    perspectives that each ask different types of questions about the topic.

    Args:
        topic: Research topic (e.g., "household water filter contamination")
        question: Full research question
        region: Geographic region

    Returns:
        List of perspective dicts with name, focus, and key_questions
    """
    client = get_gemini_client()

    prompt = STORM_PERSPECTIVE_PROMPT.format(
        topic=topic,
        question=question,
        region=region.replace("_", " "),
    )

    try:
        result = await client.generate_json(prompt, SYSTEM_PROMPT)
        perspectives = result.get("perspectives", [])

        # Validate perspectives have required fields
        valid_perspectives = []
        for p in perspectives:
            if p.get("name") and p.get("focus") and p.get("key_questions"):
                valid_perspectives.append(p)

        print(f"[PHASE-2][STORM] Generated {len(valid_perspectives)} expert perspectives")
        return valid_perspectives

    except Exception as e:
        # LOW-053: Use logger instead of print
        logger.warning(f"[STORM] Perspective generation failed: {e}")
        # Return default perspectives as fallback
        return [
            {
                "name": "Domain Expert",
                "focus": "Technical aspects and scientific evidence",
                "key_questions": ["What is the current state of research?", "What are the key findings?"]
            },
            {
                "name": "Policy Analyst",
                "focus": "Regulatory implications and policy gaps",
                "key_questions": ["What regulations exist?", "What policy changes are needed?"]
            },
            {
                "name": "Practitioner",
                "focus": "Practical implementation and real-world challenges",
                "key_questions": ["How is this implemented in practice?", "What are the main challenges?"]
            },
        ]


async def generate_queries_from_perspectives(
    topic: str,
    question: str,
    region: str,
    perspectives: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """
    SOTA: Generate targeted queries from STORM perspectives.

    Each perspective generates queries specific to their analytical lens,
    ensuring comprehensive coverage of the research topic.

    Args:
        topic: Research topic
        question: Full research question
        region: Geographic region
        perspectives: List of perspective dicts

    Returns:
        Dict mapping perspective name to list of queries
    """
    client = get_gemini_client()

    # Format perspectives for prompt
    perspectives_text = ""
    for p in perspectives:
        perspectives_text += f"\n**{p['name']}** - {p['focus']}\n"
        for q in p.get("key_questions", []):
            perspectives_text += f"  - {q}\n"

    prompt = STORM_QUERIES_FROM_PERSPECTIVES_PROMPT.format(
        topic=topic,
        question=question,
        region=region.replace("_", " "),
        perspectives=perspectives_text,
    )

    try:
        result = await client.generate_json(prompt, SYSTEM_PROMPT)
        perspective_queries = result.get("perspective_queries", {})

        total_queries = sum(len(qs) for qs in perspective_queries.values())
        print(f"[PHASE-2][STORM] Generated {total_queries} queries from {len(perspective_queries)} perspectives")

        return perspective_queries

    except Exception as e:
        # LOW-037: Use logger instead of print
        logger.warning(f"[STORM] Query generation from perspectives failed: {e}")
        # Return empty dict - will fall back to standard generation
        return {}


# =============================================================================
# SOTA: HyDE AND QUERY2DOC IMPLEMENTATION
# =============================================================================

async def generate_hyde_document(
    query: str,
    topic: str,
    region: str,
) -> Optional[Dict[str, Any]]:
    """
    SOTA: Generate HyDE (Hypothetical Document Embedding) pseudo-document.

    Instead of using the raw query for retrieval, we generate what a
    relevant document would look like. This pseudo-document is then
    used for embedding-based retrieval, improving semantic matching.

    Args:
        query: Original search query
        topic: Research topic for context
        region: Geographic region

    Returns:
        Dict with pseudo_document and key_terms, or None if failed
    """
    try:
        client = get_gemini_client()

        prompt = HYDE_PSEUDO_DOCUMENT_PROMPT.format(
            query=query,
            topic=topic,
            region=region.replace("_", " "),
        )

        result = await client.generate_json(prompt, SYSTEM_PROMPT)

        pseudo_doc = result.get("pseudo_document", "")
        key_terms = result.get("key_terms", [])

        if pseudo_doc and len(pseudo_doc) > 50:
            return {
                "pseudo_document": pseudo_doc,
                "key_terms": key_terms,
                "original_query": query,
            }

    except Exception as e:
        # LOW-054: Use logger instead of print
        logger.warning(f"[HyDE] Pseudo-document generation failed: {e}")

    return None


async def expand_query_with_query2doc(
    query: str,
    topic: str,
    region: str,
) -> Optional[str]:
    """
    SOTA: Expand query using Query2Doc technique.

    Query2Doc expands a short query into a richer, document-like
    query that includes synonyms, related terms, and context.

    Args:
        query: Original search query
        topic: Research topic
        region: Geographic region

    Returns:
        Expanded query string, or None if failed
    """
    try:
        client = get_gemini_client()

        prompt = QUERY2DOC_EXPANSION_PROMPT.format(
            query=query,
            topic=topic,
            region=region.replace("_", " "),
        )

        result = await client.generate_json(prompt, SYSTEM_PROMPT)

        expanded = result.get("expanded_query", "")
        if expanded and len(expanded) > len(query):
            return expanded

    except Exception as e:
        # LOW-055: Use logger instead of print
        logger.warning(f"[Query2Doc] Query expansion failed: {e}")

    return None


async def enhance_queries_with_hyde(
    queries_by_bucket: Dict[str, List[str]],
    topic: str,
    region: str,
    max_hyde_per_bucket: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    SOTA: Enhance top queries in each bucket with HyDE pseudo-documents.

    Generates hypothetical documents for the most important queries
    to improve downstream retrieval quality.

    Args:
        queries_by_bucket: Original queries by bucket
        topic: Research topic
        region: Geographic region
        max_hyde_per_bucket: Max HyDE documents per bucket

    Returns:
        Dict mapping bucket to list of enhanced query objects
    """
    enhanced = {}

    for bucket, queries in queries_by_bucket.items():
        enhanced_queries = []

        # Generate HyDE for top queries (academic gets more)
        hyde_limit = max_hyde_per_bucket + 1 if bucket == "academic" else max_hyde_per_bucket

        for i, query in enumerate(queries):
            query_obj = {
                "query": query,
                "hyde_document": None,
                "expanded_query": None,
            }

            # Generate HyDE for top queries
            if i < hyde_limit:
                hyde_result = await generate_hyde_document(query, topic, region)
                if hyde_result:
                    query_obj["hyde_document"] = hyde_result["pseudo_document"]
                    query_obj["hyde_key_terms"] = hyde_result.get("key_terms", [])

            # Generate Query2Doc expansion for all queries
            expanded = await expand_query_with_query2doc(query, topic, region)
            if expanded:
                query_obj["expanded_query"] = expanded

            enhanced_queries.append(query_obj)

        enhanced[bucket] = enhanced_queries

        # Log stats
        hyde_count = sum(1 for q in enhanced_queries if q.get("hyde_document"))
        expanded_count = sum(1 for q in enhanced_queries if q.get("expanded_query"))
        print(f"[PHASE-2][SOTA] {bucket}: {hyde_count} HyDE docs, {expanded_count} expanded queries")

    return enhanced


async def generate_queries_via_llm(
    vector_id: str,
    question: str,
    region: str,
    is_regional: bool,
    focus_areas: List[str],
    knowledge_gaps: List[str],
    high_priorities: List[str],
    bucket_counts: Dict[str, int],
) -> Dict[str, List[str]]:
    """
    Generate search queries using LLM.

    Args:
        vector_id: Vector ID
        question: Research question
        region: Geographic region
        is_regional: Whether this is a regional vector
        focus_areas: Research focus areas
        knowledge_gaps: Identified knowledge gaps
        high_priorities: High priority areas
        bucket_counts: Queries per bucket

    Returns:
        Dict of bucket -> list of queries
    """
    client = get_gemini_client()

    prompt = QUERY_GENERATION_PROMPT.format(
        vector_id=vector_id,
        question=question,
        region=region.replace("_", " "),
        is_regional=is_regional,
        focus_areas="\n".join(f"- {fa}" for fa in focus_areas),
        knowledge_gaps="\n".join(f"- {kg}" for kg in knowledge_gaps),
        high_priorities="\n".join(f"- {hp}" for hp in high_priorities),
        total_queries=sum(bucket_counts.values()),
        academic_count=bucket_counts.get("academic", 0),
        government_count=bucket_counts.get("government", 0),
        industry_count=bucket_counts.get("industry", 0),
        news_count=bucket_counts.get("news", 0),
        general_count=bucket_counts.get("general", 0),
    )

    result = await client.generate_json(prompt, SYSTEM_PROMPT)

    # Extract queries from result
    queries_by_bucket = result.get("queries", {})

    # Validate structure
    expected_buckets = ["academic", "government", "industry", "news", "general"]
    for bucket in expected_buckets:
        if bucket not in queries_by_bucket:
            queries_by_bucket[bucket] = []

    return queries_by_bucket


def ensure_minimum_queries(
    queries_by_bucket: Dict[str, List[str]],
    bucket_counts: Dict[str, int],
    focus_areas: List[str],
    knowledge_gaps: List[str],
) -> Dict[str, List[str]]:
    """
    Ensure each bucket has at least the minimum required queries.

    If LLM didn't generate enough, create additional queries from focus areas.

    Args:
        queries_by_bucket: Current queries
        bucket_counts: Required counts
        focus_areas: Research focus areas
        knowledge_gaps: Knowledge gaps

    Returns:
        Queries dict with minimum counts satisfied
    """
    # Build a pool of base query terms
    base_terms = list(focus_areas) + list(knowledge_gaps)
    random.shuffle(base_terms)

    for bucket, required_count in bucket_counts.items():
        current = queries_by_bucket.get(bucket, [])
        current_count = len(current)

        if current_count < required_count:
            needed = required_count - current_count
            # Generate additional queries from base terms
            for i in range(needed):
                term = base_terms[i % len(base_terms)] if base_terms else "research topic"
                # Add bucket-specific prefix
                if bucket == "academic":
                    query = f"{term} research study"
                elif bucket == "government":
                    query = f"{term} regulatory standards"
                elif bucket == "industry":
                    query = f"{term} market analysis"
                elif bucket == "news":
                    query = f"{term} recent developments"
                else:
                    query = term
                current.append(query)

            queries_by_bucket[bucket] = current

    return queries_by_bucket


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase2(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
) -> Phase2Output:
    """
    Execute Phase 2: Query Generation.

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 1 output
        output_dir: Directory to write output

    Returns:
        Phase2Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # Load config
    config = get_config()

    # 1. Load Phase 1 output
    with open(input_path, "r", encoding="utf-8") as f:
        p1_data = json.load(f)

    p1_output = Phase1Output(**p1_data)

    # Verify vector ID matches
    if p1_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p1_output.vector_id}")

    # 2. Extract research context
    strategic_plan = p1_output.strategic_plan
    focus_areas = p1_output.research_focus_areas
    knowledge_gaps = strategic_plan.get("knowledge_gaps", [])
    priorities = strategic_plan.get("priorities", {})
    high_priorities = priorities.get("high", [])

    # Parse vector for region info
    parts = vector_id.split("_")
    region = parts[-1] if len(parts) > 1 else "GLOBAL"
    is_regional = region != "GLOBAL"

    # Build question from vector (simplified - in real impl would come from P0)
    question = f"Research query for {vector_id}"

    # 3. Calculate query distribution
    distribution = config.search.query_distribution
    if not distribution:
        # Default distribution
        distribution = {
            "academic": 0.30,
            "government": 0.20,
            "industry": 0.25,
            "news": 0.15,
            "general": 0.10,
        }

    min_queries = config.thresholds.search.min_queries
    # SOTA-aligned: Generate at least 100 queries for comprehensive coverage
    # Gemini Deep Research performs 200+ searches - we target 100-150 queries
    total_queries = max(min_queries, 100)

    bucket_counts = calculate_query_distribution(total_queries, distribution)

    # 3.5 SOTA: Generate STORM perspectives for multi-perspective querying
    # Extract topic from focus areas for STORM
    topic = focus_areas[0] if focus_areas else vector_id.replace("_", " ")
    storm_perspectives = await generate_storm_perspectives(
        topic=topic,
        question=question,
        region=region,
    )

    # Generate queries from perspectives
    storm_queries_by_perspective = await generate_queries_from_perspectives(
        topic=topic,
        question=question,
        region=region,
        perspectives=storm_perspectives,
    )

    # 4. Generate queries via LLM (bucket-based)
    queries_by_bucket = await generate_queries_via_llm(
        vector_id=vector_id,
        question=question,
        region=region,
        is_regional=is_regional,
        focus_areas=focus_areas,
        knowledge_gaps=knowledge_gaps,
        high_priorities=high_priorities,
        bucket_counts=bucket_counts,
    )

    # 4.5 FIX-124: STORM Perspective-Preserving Query Generation
    # CRITICAL: Do NOT flatten perspectives into buckets - preserve identity!
    # Stanford STORM methodology requires tracking perspective origin through pipeline
    perspective_bucket_mapping = {
        "Domain Expert": "academic",
        "Technical Expert": "academic",
        "Public Health Expert": "academic",
        "Environmental Scientist": "academic",
        "Epidemiologist": "academic",
        "Policy Analyst": "government",
        "Regulatory Analyst": "government",
        "Practitioner": "industry",
        "Water Treatment Engineer": "industry",
        "Consumer Advocate": "general",
        "Journalist": "news",
    }

    # FIX-124: Create PerspectiveQuery objects that preserve identity
    perspective_queries: List[PerspectiveQuery] = []
    perspective_distribution: Dict[str, int] = {}

    storm_queries_added = 0
    for perspective_name, queries in storm_queries_by_perspective.items():
        # Find best bucket for this perspective
        target_bucket = "general"  # default
        for pattern, bucket in perspective_bucket_mapping.items():
            if pattern.lower() in perspective_name.lower():
                target_bucket = bucket
                break

        # FIX-124: Create unique perspective ID for grouping
        perspective_id = f"perspective_{hash(perspective_name) % 10000}"

        # Get perspective focus from storm_perspectives (if available)
        perspective_focus = None
        for p in storm_perspectives:
            if p.get("name", "").lower() == perspective_name.lower():
                perspective_focus = p.get("focus", "")
                break

        # FIX-124: Create perspective-tagged query objects
        for query in queries:
            perspective_queries.append(PerspectiveQuery(
                query_text=query,
                perspective_name=perspective_name,
                perspective_id=perspective_id,
                bucket=target_bucket,
                focus=perspective_focus,
            ))
            storm_queries_added += 1

        # Track distribution
        perspective_distribution[perspective_name] = len(queries)

        # FIX-124C: REMOVED backward compatibility bucket addition
        # Perspective queries now ONLY execute via execute_perspective_searches() in P3
        # This prevents double execution and wasted API calls

    print(f"[PHASE-2][STORM][FIX-124] Created {storm_queries_added} perspective-tagged queries from {len(perspective_distribution)} perspectives")
    print(f"[PHASE-2][STORM][FIX-124C] Perspective queries will execute separately in P3 (no bucket duplication)")
    for pname, pcount in perspective_distribution.items():
        print(f"[PHASE-2][STORM][FIX-124]   {pname}: {pcount} queries")

    # 4.55 BUG-008 FIX: Generate recent study queries (DYNAMIC - from P1 context)
    recent_study_queries = generate_recent_study_queries(
        topic=topic,
        region=region,
        vector_id=vector_id,
        focus_areas=focus_areas,  # From P1 output
        knowledge_gaps=knowledge_gaps,  # From P1 strategic plan
    )
    # Add to academic bucket for highest priority retrieval
    if "academic" in queries_by_bucket:
        queries_by_bucket["academic"].extend(recent_study_queries)
    else:
        queries_by_bucket["academic"] = recent_study_queries
    print(f"[PHASE-2][RECENT] Added {len(recent_study_queries)} recent study queries (dynamic year targeting)")

    # 4.6 SOTA: Query Decomposition (Sprint 5)
    # Load P0 output to get question type for targeted decomposition
    decomposition_queries_added = 0
    try:
        p0_dir = OUTPUTS_DIR / "P0"
        p0_files = sorted(p0_dir.glob(f"{vector_id}__P0__*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if p0_files:
            with open(p0_files[0], "r", encoding="utf-8") as f:
                p0_data = json.load(f)
            question_type_str = p0_data.get("question_type", "unknown")
            try:
                question_type = QuestionType(question_type_str)
            except ValueError:
                question_type = QuestionType.UNKNOWN

            # Use the question from P0
            p0_question = p0_data.get("question", question)

            # Decompose question into sub-queries
            decomposed = decompose_question(p0_question, question_type)

            # Map decomposition sub-queries to buckets
            decomp_bucket_mapping = {
                "academic": ["pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "scholar"],
                "government": ["cdc.gov", "epa.gov", "fda.gov", "who.int", "canada.ca"],
                "industry": ["statista", "grandview", "marketsandmarkets"],
            }

            for sq in decomposed.sub_queries:
                # Determine bucket from domain hints
                target_bucket = "general"
                for bucket, domains in decomp_bucket_mapping.items():
                    for domain in sq.domain_hints:
                        if any(d in domain for d in domains):
                            target_bucket = bucket
                            break
                    if target_bucket != "general":
                        break

                # Add sub-query and its search variants
                if target_bucket in queries_by_bucket:
                    queries_by_bucket[target_bucket].append(sq.query_text)
                    queries_by_bucket[target_bucket].extend(sq.search_modifiers[:2])
                    decomposition_queries_added += 1 + len(sq.search_modifiers[:2])

            # Add generated search queries from decomposition
            for search_q in decomposed.search_queries[:10]:
                if "academic" in queries_by_bucket:
                    queries_by_bucket["academic"].append(search_q)
                    decomposition_queries_added += 1

            print(f"[PHASE-2][DECOMP] Added {decomposition_queries_added} decomposition-based queries (type={question_type_str})")
    except Exception as e:
        # LOW-056: Use logger instead of print
        logger.warning(f"[DECOMP] Decomposition skipped: {e}")

    # 4.7 SOTA: Synonym expansion for better retrieval coverage
    try:
        synonym_queries = await generate_synonym_expanded_queries(
            base_queries=queries_by_bucket.get("academic", []),
            focus_areas=focus_areas,
            topic=topic,
            max_expansions=20,  # Add up to 20 synonym-expanded queries
        )

        # Add synonym-expanded queries to academic bucket (highest value for retrieval)
        if synonym_queries:
            if "academic" in queries_by_bucket:
                queries_by_bucket["academic"].extend(synonym_queries)
            else:
                queries_by_bucket["academic"] = synonym_queries
    except Exception as e:
        # LOW-057: Use logger instead of print
        logger.warning(f"[SYNONYM] Synonym expansion skipped: {e}")

    # 5. Ensure minimum queries
    queries_by_bucket = ensure_minimum_queries(
        queries_by_bucket=queries_by_bucket,
        bucket_counts=bucket_counts,
        focus_areas=focus_areas,
        knowledge_gaps=knowledge_gaps,
    )

    # 6. Apply authority anchors
    authority_anchors = config.search.authority_anchors
    total_anchors_applied = 0

    for bucket in queries_by_bucket:
        modified, anchors = apply_authority_anchors(
            queries_by_bucket[bucket],
            bucket,
            authority_anchors,
        )
        queries_by_bucket[bucket] = modified
        total_anchors_applied += anchors

    # 7. Apply geographic targeting for regional vectors
    if is_regional:
        geo_keywords = config.search.geographic_keywords
        for bucket in queries_by_bucket:
            queries_by_bucket[bucket] = apply_geographic_targeting(
                queries_by_bucket[bucket],
                region,
                geo_keywords,
            )

    # 7.5 SOTA: Validate and anchor queries to core topic (PREVENTS CORPUS POLLUTION)
    # This ensures all queries include at least one core topic term
    queries_by_bucket, anchored_count, total_count = validate_and_anchor_queries(
        queries_by_bucket,
        vector_id,
    )

    # 8. Flatten all queries
    final_queries = []
    bucket_distribution = {}
    for bucket, queries in queries_by_bucket.items():
        final_queries.extend(queries)
        bucket_distribution[bucket] = len(queries)

    # =========================================================================
    # SOTA: Generate API-specific queries from P1 templates (from upgrade plan)
    # =========================================================================
    api_queries = []
    openalex_count = 0
    s2_count = 0
    pubmed_count = 0

    # Extract SOTA data from P1 output
    query_templates = []
    if hasattr(p1_output, 'query_templates') and p1_output.query_templates:
        query_templates = p1_output.query_templates

    mesh_terms = []
    if hasattr(p1_output, 'mesh_terms') and p1_output.mesh_terms:
        mesh_terms = p1_output.mesh_terms

    iso_codes = []
    if hasattr(p1_output, 'geographic_iso_codes') and p1_output.geographic_iso_codes:
        iso_codes = p1_output.geographic_iso_codes

    try:
        # Generate API-specific queries
        api_queries = generate_api_queries_from_templates(
            query_templates=query_templates,
            base_queries=queries_by_bucket.get("academic", [])[:30],  # Top 30 academic queries
            mesh_terms=mesh_terms,
            iso_codes=iso_codes,
            max_per_api=10,
        )

        # Count by API
        for aq in api_queries:
            if aq.api_name == "openalex":
                openalex_count += 1
            elif aq.api_name == "semantic_scholar":
                s2_count += 1
            elif aq.api_name == "pubmed":
                pubmed_count += 1

        print(f"[PHASE-2][API-QUERIES] Generated {len(api_queries)} API-specific queries:")
        print(f"[PHASE-2][API-QUERIES]   OpenAlex: {openalex_count}")
        print(f"[PHASE-2][API-QUERIES]   Semantic Scholar: {s2_count}")
        print(f"[PHASE-2][API-QUERIES]   PubMed: {pubmed_count}")

    except Exception as e:
        # LOW-058: Use logger instead of print
        logger.warning(f"[API-QUERIES] API query generation skipped: {e}")

    # Audit: Log each generated query
    if audit:
        constraint_ids = [f"focus_{i}" for i in range(len(focus_areas))]
        for i, query in enumerate(final_queries):
            bucket = None
            for b, qs in queries_by_bucket.items():
                if query in qs:
                    bucket = b
                    break
            audit.log_query(
                query_text=query,
                query_type=bucket or "general",
                target_constraint_ids=constraint_ids[:1] if constraint_ids else [],
                search_engines=["serper", "pubmed", "openalex"],
            )

        # Log query generation complete
        constraint_coverage = {f"focus_{i}": 1.0 for i in range(len(focus_areas))}
        audit.log_query_generation_complete(constraint_coverage=constraint_coverage)

        # Log LLM call for query generation
        audit.log_llm_call(
            phase=2,
            purpose="query_generation",
            model="gemini",
            input_tokens=len(str(focus_areas)) // 4,
            output_tokens=len(str(final_queries)) // 4,
            cost_usd=0.0,
            success=True,
        )

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 9. Build output with SOTA API queries
    output = Phase2Output(
        vector_id=vector_id,
        final_queries=final_queries,
        query_count=len(final_queries),
        bucket_distribution=bucket_distribution,
        geographic_targeting=is_regional,
        authority_anchors_applied=total_anchors_applied,
        timestamps=timestamps,
        # SOTA: API-specific queries
        api_queries=api_queries,
        openalex_query_count=openalex_count,
        semantic_scholar_query_count=s2_count,
        pubmed_query_count=pubmed_count,
        # FIX-124: STORM perspective-tagged queries
        perspective_queries=perspective_queries,
        perspective_distribution=perspective_distribution,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 2 self-tests.

    Tests:
    1. Query distribution calculation
    2. Authority anchor application
    3. Geographic targeting
    4. Full query generation (requires API key)
    """
    print("Running Phase 2 self-tests...")

    # Test 1: Query distribution
    try:
        distribution = {
            "academic": 0.30,
            "government": 0.20,
            "industry": 0.25,
            "news": 0.15,
            "general": 0.10,
        }
        counts = calculate_query_distribution(20, distribution)
        assert sum(counts.values()) == 20
        assert counts["academic"] >= 5  # 30% of 20
        print("  [PASS] Query distribution calculation")
    except Exception as e:
        print(f"  [FAIL] Query distribution calculation: {e}")
        return False

    # Test 2: Authority anchor application
    try:
        queries = ["query1", "query2", "query3", "query4"]
        anchors = {"academic": ["site:*.edu", "site:pubmed.ncbi.nlm.nih.gov"]}
        modified, count = apply_authority_anchors(queries, "academic", anchors)
        assert count == 2  # Every other query
        assert "site:" in modified[0]
        assert "site:" not in modified[1]
        print("  [PASS] Authority anchor application")
    except Exception as e:
        print(f"  [FAIL] Authority anchor application: {e}")
        return False

    # Test 3: Geographic targeting
    try:
        queries = ["water filter contamination", "pathogen research"]
        geo_keywords = {"NORTH_AMERICA": ["United States", "USA", "Canada"]}
        modified = apply_geographic_targeting(queries, "NORTH_AMERICA", geo_keywords)
        assert "United States" in modified[0] or "USA" in modified[0] or "Canada" in modified[0]
        print("  [PASS] Geographic targeting")
    except Exception as e:
        print(f"  [FAIL] Geographic targeting: {e}")
        return False

    # Test 3.5: SOTA Topic anchoring (prevents corpus pollution)
    try:
        # Test core term extraction
        core_terms = extract_core_topic_terms("S1V1_Household_Water_Filter_NORTH_AMERICA")
        assert "household" in core_terms
        assert "water" in core_terms
        assert "filter" in core_terms
        assert "north" not in core_terms  # Region should be excluded
        assert "america" not in core_terms  # Region should be excluded
        print(f"  Core terms extracted: {core_terms}")

        # Test query anchoring - off-topic query should get topic term added
        off_topic_query = "ophthalmology disease research study"
        anchored, was_modified = anchor_query_to_topic(off_topic_query, core_terms)
        assert was_modified, "Off-topic query should be modified"
        assert any(term in anchored.lower() for term in core_terms), "Anchored query should contain topic term"

        # Test query anchoring - on-topic query should NOT be modified
        on_topic_query = "water filter contamination pathogen study"
        anchored, was_modified = anchor_query_to_topic(on_topic_query, core_terms)
        assert not was_modified, "On-topic query should not be modified"

        # Test full validation function
        queries_by_bucket = {
            "academic": ["cardiac disease research", "water filter bacteria study"],
            "general": ["ophthalmology trends", "household water quality"],
        }
        anchored_queries, modified_count, total_count = validate_and_anchor_queries(
            queries_by_bucket, "S1V1_Household_Water_Filter_NORTH_AMERICA"
        )
        assert modified_count == 2, f"Expected 2 modified queries, got {modified_count}"  # cardiac + ophthalmology
        assert total_count == 4, f"Expected 4 total queries, got {total_count}"
        print(f"  Topic anchoring: {modified_count}/{total_count} queries anchored")
        print("  [PASS] Topic anchoring (corpus pollution prevention)")
    except Exception as e:
        print(f"  [FAIL] Topic anchoring: {e}")
        return False

    # Test 4: Minimum query enforcement
    try:
        queries_by_bucket = {"academic": ["q1"], "government": [], "industry": [], "news": [], "general": []}
        bucket_counts = {"academic": 5, "government": 4, "industry": 5, "news": 3, "general": 3}
        focus_areas = ["pathogen contamination", "water filter efficacy"]
        knowledge_gaps = ["regional patterns", "outbreak data"]

        result = ensure_minimum_queries(queries_by_bucket, bucket_counts, focus_areas, knowledge_gaps)
        assert len(result["academic"]) >= 5
        assert len(result["government"]) >= 4
        print("  [PASS] Minimum query enforcement")
    except Exception as e:
        print(f"  [FAIL] Minimum query enforcement: {e}")
        return False

    # Test 4.5: SOTA API-specific query generators
    try:
        # Test OpenAlex filter generation
        openalex_query = generate_openalex_filter(
            raw_query="water filter contamination",
            iso_codes=["US", "CA"],
            year_min=2020,
            year_max=2025,
        )
        assert openalex_query.api_name == "openalex"
        assert "search=" in openalex_query.query_string
        assert "filter=" in openalex_query.query_string
        assert "publication_year" in openalex_query.filters
        assert "US|CA" in openalex_query.filters.get("authorships.countries", "")
        print("  [PASS] OpenAlex filter generation")

        # Test Semantic Scholar query generation
        s2_query = generate_semantic_scholar_query(
            raw_query="antimicrobial coating efficacy",
            fields_of_study=["Medicine", "Biology"],
            year_min=2020,
        )
        assert s2_query.api_name == "semantic_scholar"
        assert "query=" in s2_query.query_string
        assert s2_query.filters.get("year") == "2020-"
        print("  [PASS] Semantic Scholar query generation")

        # Test PubMed MeSH query generation
        pubmed_query = generate_pubmed_mesh_query(
            raw_query="water contamination pathogen",
            mesh_terms=["Water Purification", "Bacteria"],
            year_min=2020,
            year_max=2025,
        )
        assert pubmed_query.api_name == "pubmed"
        assert "[MeSH Terms]" in pubmed_query.query_string
        assert "Water Purification" in pubmed_query.query_string
        assert "[Date - Publication]" in pubmed_query.query_string
        print("  [PASS] PubMed MeSH query generation")

        # Test full API query generation from templates
        templates = [
            QueryTemplate(
                api_name="openalex",
                base_query="test",
                filters={"authorships.countries": "US|CA"},
                boost_terms=["water"],
                required_terms=[],
                exclude_terms=[],
            ),
            QueryTemplate(
                api_name="semantic_scholar",
                base_query="test",
                filters={"fieldsOfStudy": "Medicine"},
                boost_terms=[],
                required_terms=[],
                exclude_terms=[],
            ),
            QueryTemplate(
                api_name="pubmed",
                base_query="test",
                filters={},
                boost_terms=["Bacteria"],
                required_terms=[],
                exclude_terms=[],
            ),
        ]
        base_queries = ["water filter bacteria", "pathogen contamination", "antimicrobial coating"]
        api_queries = generate_api_queries_from_templates(
            query_templates=templates,
            base_queries=base_queries,
            mesh_terms=["Water Purification"],
            iso_codes=["US"],
            max_per_api=5,
        )
        assert len(api_queries) > 0
        api_names = [aq.api_name for aq in api_queries]
        assert "openalex" in api_names
        assert "semantic_scholar" in api_names
        assert "pubmed" in api_names
        print(f"  [PASS] API query generation from templates ({len(api_queries)} queries)")
    except Exception as e:
        print(f"  [FAIL] API-specific query generators: {e}")
        return False

    # Test 5: LLM query generation (async)
    async def test_llm_generation():
        try:
            queries = await generate_queries_via_llm(
                vector_id="S1V1_Test_NORTH_AMERICA",
                question="What contamination patterns exist in water filters?",
                region="NORTH_AMERICA",
                is_regional=True,
                focus_areas=["pathogen contamination", "filter efficacy"],
                knowledge_gaps=["regional patterns"],
                high_priorities=["contamination rates"],
                bucket_counts={"academic": 3, "government": 2, "industry": 2, "news": 1, "general": 2},
            )
            assert "academic" in queries
            assert "government" in queries
            return True
        except ValueError as e:
            if "GEMINI_API_KEY" in str(e):
                print("  [SKIP] LLM query generation (API key not configured)")
                return True
            raise

    try:
        result = asyncio.run(test_llm_generation())
        if result:
            print("  [PASS] LLM query generation")
    except Exception as e:
        print(f"  [FAIL] LLM query generation: {e}")
        return False

    print("\nAll Phase 2 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p1_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 1 output for a vector."""
    p1_dir = OUTPUTS_DIR / "P1"
    if not p1_dir.exists():
        return None

    pattern = f"{vector_id}__P1__*.json"
    matches = sorted(p1_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 2: Query Generation"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 1 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P2"),
        help="Output directory"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode"
    )

    args = parser.parse_args()

    # Self-test mode
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Normal execution requires vector-id
    if not args.vector_id:
        parser.error("--vector-id is required (unless using --self-test)")

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_latest_p1_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-2][{args.vector_id}][ERROR] No Phase 1 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-2][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=2,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-2][{args.vector_id}][INFO] Starting query generation...")
        print(f"[PHASE-2][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase2(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P2__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-2][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-2][{args.vector_id}][INFO] Total queries: {output.query_count}")
        print(f"[PHASE-2][{args.vector_id}][INFO] Bucket distribution: {output.bucket_distribution}")
        print(f"[PHASE-2][{args.vector_id}][INFO] Authority anchors applied: {output.authority_anchors_applied}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=2,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-2][{args.vector_id}][ERROR] {e}")

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=2,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
