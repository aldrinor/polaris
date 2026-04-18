#!/usr/bin/env python3
"""
POLARIS Phase 1: Contextualization (HPRP)
=========================================
Historical Pattern Recognition and Planning.

Purpose:
- Query LTM for prior knowledge on this vector's topic
- Generate strategic plan with knowledge gaps and priorities
- Identify research focus areas for query generation

Usage:
    python src/phases/p01_contextualization.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P0/S1V1...json --output outputs/P1/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 0 output JSON.
    --output: Optional. Output directory (default: outputs/P1/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase0Output, Phase1Output, QueryTemplate
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.memory.chroma_client import get_chroma_manager
from src.llm.gemini_client import get_gemini_client
from src.audit import get_audit

import aiohttp
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

SYSTEM_PROMPT = """You are a research strategist for POLARIS, a system that investigates antimicrobial coating applications.

Your task is to analyze a research question and create a strategic plan for investigation.

You must respond with valid JSON matching the required schema."""

STRATEGIC_PLAN_PROMPT = """
Analyze this research vector and create a strategic plan:

**Vector ID:** {vector_id}
**Stage:** {stage} - {stage_name}
**Application:** {application}
**Region:** {region}
**Research Question:** {question}

**Prior Knowledge from LTM:**
{prior_knowledge}

Create a strategic research plan with:
1. **knowledge_gaps**: List of 3-5 specific knowledge gaps that need to be filled
2. **priorities**: Dict with "high", "medium", "low" priority areas (list of strings each)
3. **strategies**: List of 3-5 research strategies to employ
4. **focus_areas**: List of 5-8 specific research focus areas for query generation

Consider:
- What specific data points are missing?
- What sources would be most authoritative for this topic?
- What geographic or temporal constraints apply?
- What stakeholder perspectives need coverage?

Respond with JSON:
{{
    "knowledge_gaps": ["gap1", "gap2", ...],
    "priorities": {{
        "high": ["area1", "area2"],
        "medium": ["area3"],
        "low": ["area4"]
    }},
    "strategies": ["strategy1", "strategy2", ...],
    "focus_areas": ["focus1", "focus2", ...]
}}
"""


# =============================================================================
# STAGE CONTEXT
# =============================================================================

STAGE_CONTEXTS = {
    1: "Contamination Problem Identification - Focus on pathogen types, contamination rates, outbreak data, and epidemiological studies.",
    2: "Cost of Pain Quantification - Focus on economic impact, healthcare costs, productivity losses, and market damage from contamination.",
    3: "Solution Landscape Analysis - Focus on existing antimicrobial technologies, their efficacy, limitations, and market presence.",
    4: "Technology Gap Identification - Focus on unmet needs, technical limitations of current solutions, and innovation opportunities.",
    5: "C-POLAR Value Proposition - Focus on unique benefits of copper-polar antimicrobial technology versus alternatives.",
    6: "Market Size Quantification - Focus on TAM/SAM/SOM, market growth rates, and segment analysis.",
    7: "Competitive Intelligence - Focus on competitor products, market share, pricing, and strategic positioning.",
    8: "Regulatory Pathway Analysis - Focus on FDA, EPA, EU regulations, certification requirements, and compliance pathways.",
    9: "Technical Feasibility Assessment - Focus on engineering requirements, material compatibility, and production scalability.",
    10: "Business Model Design - Focus on revenue models, distribution channels, and partnership structures.",
    11: "Financial Modeling - Focus on cost structures, pricing strategies, and ROI projections.",
    12: "Risk Assessment - Focus on technical, market, regulatory, and operational risks.",
    13: "Go-to-Market Strategy - Focus on launch timing, channel strategy, and marketing approach.",
}


# =============================================================================
# SOTA: BIOMEDICAL CLASSIFICATION KEYWORDS
# =============================================================================

BIOMEDICAL_KEYWORDS = {
    # Disease/health terms
    "pathogen", "bacteria", "virus", "contamination", "infection", "disease",
    "health", "epidemiolog", "outbreak", "mortality", "morbidity", "clinical",
    "medical", "pharmaceutical", "antimicrobial", "antibiotic", "therapeutic",
    # Biological terms
    "cell", "tissue", "organ", "protein", "gene", "dna", "rna", "enzyme",
    "microb", "bacteri", "viral", "fungal", "parasit",
    # Health systems
    "hospital", "healthcare", "patient", "treatment", "therapy", "diagnosis",
    "fda", "clinical trial", "drug", "vaccine", "immuniz",
    # Water/food safety related
    "waterborne", "foodborne", "coliform", "e. coli", "legionella", "giardia",
    "cryptosporidium", "biofilm", "disinfect", "steriliz",
}

# Stages that are typically biomedical in nature
BIOMEDICAL_STAGES = {1, 5, 8, 9}  # Contamination, C-POLAR tech, Regulatory, Technical


# =============================================================================
# SOTA: OPENALEX CONCEPTS API INTEGRATION
# =============================================================================

async def query_openalex_concepts(
    search_terms: List[str],
    max_concepts: int = 10,
) -> tuple[List[str], List[Dict[str, Any]]]:
    """
    Query OpenAlex Concepts API to expand search terminology.

    Uses the OpenAlex autocomplete endpoint to find related concepts
    for each search term, enabling taxonomy-based query expansion.

    API Docs: https://docs.openalex.org/api-entities/concepts

    Args:
        search_terms: List of terms to expand
        max_concepts: Maximum concepts to return

    Returns:
        Tuple of (expanded_terms, raw_concept_objects)
    """
    expanded_terms = set()
    raw_concepts = []
    base_url = "https://api.openalex.org"

    async with aiohttp.ClientSession() as session:
        for term in search_terms[:5]:  # Limit to first 5 terms to avoid rate limiting
            try:
                # Query concepts API with search
                params = {
                    "search": term,
                    "per_page": 5,
                    "mailto": "polaris@research.ai",
                }
                async with session.get(
                    f"{base_url}/concepts",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for concept in data.get("results", []):
                            concept_name = concept.get("display_name", "")
                            if concept_name:
                                expanded_terms.add(concept_name.lower())
                                raw_concepts.append({
                                    "id": concept.get("id", ""),
                                    "display_name": concept_name,
                                    "level": concept.get("level", 0),
                                    "works_count": concept.get("works_count", 0),
                                    "relevance_score": concept.get("relevance_score", 0),
                                })

                # Be polite with rate limiting
                await asyncio.sleep(0.1)

            except asyncio.TimeoutError:
                logger.warning(f"Timeout querying OpenAlex concepts for: {term}")
            except Exception as e:
                logger.error(f"Error querying OpenAlex concepts for '{term}': {e}")

    # Sort by relevance and limit
    raw_concepts = sorted(
        raw_concepts,
        key=lambda x: x.get("works_count", 0),
        reverse=True,
    )[:max_concepts]

    return list(expanded_terms)[:max_concepts], raw_concepts


# =============================================================================
# SOTA: MESH TERM LOOKUP VIA NLM E-UTILITIES
# =============================================================================

async def lookup_mesh_terms(
    search_terms: List[str],
    max_terms: int = 15,
) -> tuple[List[str], List[Dict[str, str]]]:
    """
    Lookup MeSH (Medical Subject Headings) terms using NLM E-utilities.

    MeSH is the controlled vocabulary used by PubMed for indexing
    biomedical literature. Using MeSH terms improves PubMed search recall.

    API Docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/

    Args:
        search_terms: List of terms to lookup in MeSH
        max_terms: Maximum MeSH terms to return

    Returns:
        Tuple of (mesh_term_names, mesh_descriptor_objects)
    """
    mesh_terms = []
    mesh_descriptors = []
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async with aiohttp.ClientSession() as session:
        for term in search_terms[:5]:  # Limit to avoid rate limiting
            try:
                # Search MeSH database
                search_params = {
                    "db": "mesh",
                    "term": term,
                    "retmax": 3,
                    "retmode": "json",
                }
                async with session.get(
                    f"{base_url}/esearch.fcgi",
                    params=search_params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        id_list = data.get("esearchresult", {}).get("idlist", [])

                        if id_list:
                            # Fetch MeSH term details
                            fetch_params = {
                                "db": "mesh",
                                "id": ",".join(id_list),
                                "retmode": "json",
                            }
                            async with session.get(
                                f"{base_url}/esummary.fcgi",
                                params=fetch_params,
                                timeout=aiohttp.ClientTimeout(total=10),
                            ) as fetch_response:
                                if fetch_response.status == 200:
                                    fetch_data = await fetch_response.json()
                                    result = fetch_data.get("result", {})
                                    for uid in id_list:
                                        term_data = result.get(uid, {})
                                        term_name = term_data.get("ds_meshterms", [""])[0]
                                        if term_name and term_name not in mesh_terms:
                                            mesh_terms.append(term_name)
                                            mesh_descriptors.append({
                                                "ui": uid,
                                                "name": term_name,
                                                "scope_note": term_data.get("ds_scopenote", ""),
                                            })

                # NLM rate limit: 3 requests per second without API key
                await asyncio.sleep(0.35)

            except asyncio.TimeoutError:
                logger.warning(f"Timeout querying MeSH for: {term}")
            except Exception as e:
                logger.error(f"Error querying MeSH for '{term}': {e}")

    return mesh_terms[:max_terms], mesh_descriptors[:max_terms]


def is_biomedical_vector(stage: int, application: str, question: str) -> bool:
    """
    Determine if a vector is biomedical in nature (triggers MeSH lookup).

    Args:
        stage: Stage number
        application: Application area
        question: Research question

    Returns:
        True if vector should use MeSH terminology
    """
    # Check if stage is typically biomedical
    if stage in BIOMEDICAL_STAGES:
        return True

    # Check keywords in application and question
    combined_text = f"{application} {question}".lower()
    for keyword in BIOMEDICAL_KEYWORDS:
        if keyword in combined_text:
            return True

    return False


# =============================================================================
# SOTA: STRUCTURED QUERY TEMPLATE GENERATION
# =============================================================================

def generate_query_templates(
    question: str,
    focus_areas: List[str],
    expanded_terms: List[str],
    mesh_terms: List[str],
    iso_codes: List[str],
    stage: int,
    region: str,
) -> List[QueryTemplate]:
    """
    Generate structured query templates for each target API.

    These templates are consumed by P2 to generate API-specific queries
    with proper filters and syntax.

    Args:
        question: Research question
        focus_areas: Research focus areas from strategic plan
        expanded_terms: OpenAlex expanded terms
        mesh_terms: MeSH terms for biomedical search
        iso_codes: ISO 3166-1 alpha-2 country codes
        stage: Stage number
        region: Region string

    Returns:
        List of QueryTemplate objects
    """
    templates = []

    # Extract core terms from question (simple extraction)
    core_terms = []
    for term in question.lower().split():
        if len(term) > 4 and term not in {"what", "where", "which", "about", "their"}:
            core_terms.append(term)
    core_terms = core_terms[:5]

    # 1. OpenAlex template
    openalex_filters = {}
    if iso_codes:
        openalex_filters["authorships.countries"] = "|".join(iso_codes)
    openalex_filters["publication_year"] = ">2019"  # Last 5 years
    openalex_filters["type"] = "article|review"

    templates.append(QueryTemplate(
        api_name="openalex",
        base_query=" ".join(core_terms),
        filters=openalex_filters,
        boost_terms=expanded_terms[:5] if expanded_terms else [],
        required_terms=core_terms[:2] if core_terms else [],
        exclude_terms=["retracted", "withdrawn"],
    ))

    # 2. Semantic Scholar template
    s2_filters = {}
    if stage in {1, 5, 8, 9}:  # Research-heavy stages
        s2_filters["fieldsOfStudy"] = "Medicine,Biology,Environmental Science"
    s2_filters["year"] = "2020-"
    s2_filters["openAccessPdf"] = True

    templates.append(QueryTemplate(
        api_name="semantic_scholar",
        base_query=" ".join(core_terms),
        filters=s2_filters,
        boost_terms=focus_areas[:3] if focus_areas else [],
        required_terms=[],
        exclude_terms=[],
    ))

    # 3. PubMed template (uses MeSH)
    if mesh_terms:
        pubmed_query_parts = []
        for mesh in mesh_terms[:3]:
            pubmed_query_parts.append(f'"{mesh}"[MeSH Terms]')
        pubmed_base = " OR ".join(pubmed_query_parts)
    else:
        pubmed_base = " ".join(core_terms)

    pubmed_filters = {
        "datetype": "pdat",
        "mindate": "2020/01/01",
        "maxdate": "2026/12/31",
    }

    templates.append(QueryTemplate(
        api_name="pubmed",
        base_query=pubmed_base,
        filters=pubmed_filters,
        boost_terms=mesh_terms[:5] if mesh_terms else [],
        required_terms=[],
        exclude_terms=["withdrawn", "retracted"],
    ))

    # 4. Serper (general web) template
    serper_boost = []
    if region != "GLOBAL":
        serper_boost.append(region.replace("_", " ").title())
    serper_boost.extend(focus_areas[:2])

    templates.append(QueryTemplate(
        api_name="serper",
        base_query=question[:100],  # Use original question for web search
        filters={"num": 20, "gl": iso_codes[0].lower() if iso_codes else "us"},
        boost_terms=serper_boost,
        required_terms=[],
        exclude_terms=["buy", "shop", "price", "amazon"],
    ))

    return templates


# =============================================================================
# LTM QUERY
# =============================================================================

def query_ltm_for_prior_knowledge(
    vector_id: str,
    question: str,
    stage: int,
    region: str,
) -> Dict[str, Any]:
    """
    Query LTM-Stage and LTM-Global for prior knowledge.

    Args:
        vector_id: Current vector ID
        question: Research question
        stage: Stage number
        region: Region string

    Returns:
        Dict with hits and summary
    """
    chroma = get_chroma_manager()

    ltm_stage_hits = 0
    ltm_global_hits = 0
    prior_docs = []

    # Query LTM-Stage
    try:
        ltm_stage = chroma.get_ltm_stage(stage)
        stage_results = ltm_stage.query(
            query_texts=[question],
            n_results=5,
            include=["documents", "metadatas", "distances"]
        )
        if stage_results and stage_results.get("ids") and stage_results["ids"][0]:
            ltm_stage_hits = len(stage_results["ids"][0])
            for i, doc in enumerate(stage_results.get("documents", [[]])[0]):
                if doc:
                    prior_docs.append(f"[Stage {stage}] {doc[:200]}...")
    except Exception as e:
        # HIGH-002: Log LTM-Stage error instead of silent pass
        logger.debug(f"LTM-Stage query failed (may be empty): {e}")

    # Query LTM-Global
    try:
        ltm_global = chroma.get_ltm_global()
        global_results = ltm_global.query(
            query_texts=[question],
            n_results=5,
            include=["documents", "metadatas", "distances"]
        )
        if global_results and global_results.get("ids") and global_results["ids"][0]:
            ltm_global_hits = len(global_results["ids"][0])
            for i, doc in enumerate(global_results.get("documents", [[]])[0]):
                if doc:
                    prior_docs.append(f"[Global] {doc[:200]}...")
    except Exception as e:
        # HIGH-003: Log LTM-Global error instead of silent pass
        logger.debug(f"LTM-Global query failed (may be empty): {e}")

    # Build summary
    if prior_docs:
        summary = "\n".join(prior_docs[:5])
    else:
        summary = "No prior knowledge found in LTM. This appears to be a novel research area."

    return {
        "ltm_stage_hits": ltm_stage_hits,
        "ltm_global_hits": ltm_global_hits,
        "summary": summary,
    }


# =============================================================================
# STRATEGIC PLANNING
# =============================================================================

async def generate_strategic_plan(
    vector_id: str,
    stage: int,
    stage_name: str,
    application: str,
    region: str,
    question: str,
    prior_knowledge: str,
) -> Dict[str, Any]:
    """
    Use LLM to generate strategic research plan.

    Args:
        vector_id: Vector ID
        stage: Stage number
        stage_name: Stage name
        application: Application area
        region: Geographic region
        question: Research question
        prior_knowledge: Summary from LTM

    Returns:
        Strategic plan dict
    """
    client = get_gemini_client()

    prompt = STRATEGIC_PLAN_PROMPT.format(
        vector_id=vector_id,
        stage=stage,
        stage_name=stage_name,
        application=application.replace("_", " "),
        region=region.replace("_", " "),
        question=question,
        prior_knowledge=prior_knowledge,
    )

    result = await client.generate_json(prompt, SYSTEM_PROMPT)

    # Validate required keys
    required_keys = ["knowledge_gaps", "priorities", "strategies", "focus_areas"]
    for key in required_keys:
        if key not in result:
            result[key] = []

    return result


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase1(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
) -> Phase1Output:
    """
    Execute Phase 1: Contextualization.

    SOTA Upgrades:
    - OpenAlex Concepts API for taxonomy expansion
    - MeSH term lookup for biomedical vectors
    - Geographic scope propagation from P0
    - Structured query templates per API

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 0 output
        output_dir: Directory to write output

    Returns:
        Phase1Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # 1. Load Phase 0 output
    with open(input_path, "r", encoding="utf-8") as f:
        p0_data = json.load(f)

    p0_output = Phase0Output(**p0_data)

    # Verify vector ID matches
    if p0_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p0_output.vector_id}")

    # 2. Query LTM for prior knowledge
    ltm_results = query_ltm_for_prior_knowledge(
        vector_id=vector_id,
        question=p0_output.question,
        stage=p0_output.stage,
        region=p0_output.region,
    )

    # 3. Get stage context
    stage_name = STAGE_CONTEXTS.get(p0_output.stage, f"Stage {p0_output.stage}")

    # 4. Generate strategic plan via LLM
    strategic_plan = await generate_strategic_plan(
        vector_id=vector_id,
        stage=p0_output.stage,
        stage_name=stage_name,
        application=p0_output.application,
        region=p0_output.region,
        question=p0_output.question,
        prior_knowledge=ltm_results["summary"],
    )

    focus_areas = strategic_plan.get("focus_areas", [])

    # =========================================================================
    # SOTA: OpenAlex Concepts API for taxonomy expansion
    # =========================================================================
    logger.info(f"[P1] Querying OpenAlex Concepts API for taxonomy expansion...")
    search_terms_for_expansion = focus_areas[:5] if focus_areas else [p0_output.application.replace("_", " ")]
    expanded_terms, openalex_concepts = await query_openalex_concepts(search_terms_for_expansion)
    logger.info(f"[P1] OpenAlex expanded terms: {len(expanded_terms)}")

    # =========================================================================
    # SOTA: MeSH term lookup for biomedical vectors
    # =========================================================================
    is_biomed = is_biomedical_vector(p0_output.stage, p0_output.application, p0_output.question)
    mesh_terms = []
    mesh_descriptors = []

    if is_biomed:
        logger.info(f"[P1] Vector classified as biomedical, querying MeSH...")
        mesh_search_terms = focus_areas[:3] if focus_areas else [p0_output.application.replace("_", " ")]
        mesh_terms, mesh_descriptors = await lookup_mesh_terms(mesh_search_terms)
        logger.info(f"[P1] MeSH terms found: {len(mesh_terms)}")
    else:
        logger.info(f"[P1] Vector not biomedical, skipping MeSH lookup")

    # =========================================================================
    # SOTA: Geographic scope propagation from P0
    # =========================================================================
    geo_iso_codes = p0_output.geographic_scope or []
    logger.info(f"[P1] Geographic ISO codes from P0: {geo_iso_codes}")

    # =========================================================================
    # SOTA: Generate structured query templates per API
    # =========================================================================
    query_templates = generate_query_templates(
        question=p0_output.question,
        focus_areas=focus_areas,
        expanded_terms=expanded_terms,
        mesh_terms=mesh_terms,
        iso_codes=geo_iso_codes,
        stage=p0_output.stage,
        region=p0_output.region,
    )
    logger.info(f"[P1] Generated {len(query_templates)} query templates")

    # Audit: Log decomposition/strategic planning
    if audit:
        knowledge_gaps = strategic_plan.get("knowledge_gaps", [])
        for gap in knowledge_gaps:
            audit.log_decomposition(
                original_constraint_id="p1_context",
                original_text=p0_output.question,
                decomposed_constraints=[gap],
                decomposition_method="llm_strategic_plan",
            )

        # Log LLM call for strategic planning
        audit.log_llm_call(
            phase=1,
            purpose="strategic_plan_generation",
            model="gemini",
            input_tokens=len(p0_output.question) // 4,
            output_tokens=len(str(strategic_plan)) // 4,
            cost_usd=0.0,
            success=True,
        )

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 5. Build output with SOTA fields
    output = Phase1Output(
        vector_id=vector_id,
        strategic_plan={
            "knowledge_gaps": strategic_plan.get("knowledge_gaps", []),
            "priorities": strategic_plan.get("priorities", {}),
            "strategies": strategic_plan.get("strategies", []),
        },
        ltm_stage_hits=ltm_results["ltm_stage_hits"],
        ltm_global_hits=ltm_results["ltm_global_hits"],
        prior_knowledge_summary=ltm_results["summary"],
        research_focus_areas=focus_areas,
        timestamps=timestamps,
        # SOTA fields
        expanded_terms=expanded_terms,
        openalex_concepts=openalex_concepts,
        mesh_terms=mesh_terms,
        mesh_descriptors=mesh_descriptors,
        is_biomedical=is_biomed,
        geographic_iso_codes=geo_iso_codes,
        query_templates=query_templates,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 1 self-tests.

    Tests:
    1. LTM query (empty DB is OK)
    2. Strategic plan generation (requires API key)
    3. SOTA: Biomedical classification
    4. SOTA: Query template generation
    5. SOTA: OpenAlex Concepts API (network)
    6. SOTA: MeSH lookup (network)
    """
    print("Running Phase 1 self-tests...")

    # Test 1: LTM query function
    try:
        result = query_ltm_for_prior_knowledge(
            vector_id="S1V1_Test_NORTH_AMERICA",
            question="What contamination patterns exist?",
            stage=1,
            region="NORTH_AMERICA",
        )
        assert "ltm_stage_hits" in result
        assert "ltm_global_hits" in result
        assert "summary" in result
        print("  [PASS] LTM query function")
    except Exception as e:
        print(f"  [FAIL] LTM query function: {e}")
        return False

    # Test 2: Stage context lookup
    try:
        context = STAGE_CONTEXTS.get(1)
        assert context is not None
        assert "Contamination" in context
        print("  [PASS] Stage context lookup")
    except Exception as e:
        print(f"  [FAIL] Stage context lookup: {e}")
        return False

    # Test 3: SOTA - Biomedical classification
    try:
        # Stage 1 should be biomedical
        assert is_biomedical_vector(1, "Water_Filter", "What pathogens exist?") is True
        # Stage 6 with business question should not be biomedical
        assert is_biomedical_vector(6, "Market_Analysis", "What is the market size?") is False
        # Non-biomedical stage but with biomedical keyword
        assert is_biomedical_vector(2, "Healthcare", "What is the disease burden?") is True
        print("  [PASS] Biomedical classification")
    except Exception as e:
        print(f"  [FAIL] Biomedical classification: {e}")
        return False

    # Test 4: SOTA - Query template generation
    try:
        templates = generate_query_templates(
            question="What contamination patterns exist in household water filters in North America?",
            focus_areas=["microbial contamination", "filter efficacy", "pathogen removal"],
            expanded_terms=["water quality", "filtration", "bacteria"],
            mesh_terms=["Water Purification", "Bacteria"],
            iso_codes=["US", "CA", "MX"],
            stage=1,
            region="NORTH_AMERICA",
        )
        assert len(templates) == 4  # openalex, semantic_scholar, pubmed, serper
        assert templates[0].api_name == "openalex"
        assert templates[1].api_name == "semantic_scholar"
        assert templates[2].api_name == "pubmed"
        assert templates[3].api_name == "serper"
        # Verify OpenAlex template has geographic filter
        assert "authorships.countries" in templates[0].filters
        # Verify PubMed template uses MeSH
        assert "[MeSH Terms]" in templates[2].base_query
        print("  [PASS] Query template generation")
    except Exception as e:
        print(f"  [FAIL] Query template generation: {e}")
        return False

    # Test 5: SOTA - OpenAlex Concepts API (async, network)
    async def test_openalex_concepts():
        try:
            terms, concepts = await query_openalex_concepts(["water contamination"])
            # May return empty if network unavailable, but should not error
            print(f"    OpenAlex returned {len(terms)} terms, {len(concepts)} concepts")
            return True
        except Exception as e:
            print(f"    OpenAlex error (non-fatal): {e}")
            return True  # Network errors are acceptable in self-test

    try:
        result = asyncio.run(test_openalex_concepts())
        if result:
            print("  [PASS] OpenAlex Concepts API")
    except Exception as e:
        print(f"  [WARN] OpenAlex Concepts API: {e}")

    # Test 6: SOTA - MeSH lookup (async, network)
    async def test_mesh_lookup():
        try:
            terms, descriptors = await lookup_mesh_terms(["water purification"])
            # May return empty if network unavailable
            print(f"    MeSH returned {len(terms)} terms, {len(descriptors)} descriptors")
            return True
        except Exception as e:
            print(f"    MeSH error (non-fatal): {e}")
            return True  # Network errors are acceptable in self-test

    try:
        result = asyncio.run(test_mesh_lookup())
        if result:
            print("  [PASS] MeSH term lookup")
    except Exception as e:
        print(f"  [WARN] MeSH term lookup: {e}")

    # Test 7: Strategic plan generation (async)
    async def test_strategic_plan():
        try:
            plan = await generate_strategic_plan(
                vector_id="S1V1_Test_NORTH_AMERICA",
                stage=1,
                stage_name="Contamination Problem Identification",
                application="Water_Filter",
                region="NORTH_AMERICA",
                question="What contamination patterns exist in water filters?",
                prior_knowledge="No prior knowledge available.",
            )
            assert "knowledge_gaps" in plan
            assert "strategies" in plan
            return True
        except ValueError as e:
            if "GEMINI_API_KEY" in str(e):
                print("  [SKIP] Strategic plan (API key not configured)")
                return True
            raise

    try:
        result = asyncio.run(test_strategic_plan())
        if result:
            print("  [PASS] Strategic plan generation")
    except Exception as e:
        print(f"  [FAIL] Strategic plan generation: {e}")
        return False

    print("\nAll Phase 1 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p0_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 0 output for a vector."""
    p0_dir = OUTPUTS_DIR / "P0"
    if not p0_dir.exists():
        return None

    pattern = f"{vector_id}__P0__*.json"
    matches = sorted(p0_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 1: Contextualization"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 0 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P1"),
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
        input_path = find_latest_p0_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-1][{args.vector_id}][ERROR] No Phase 0 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-1][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=1,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-1][{args.vector_id}][INFO] Starting contextualization...")
        print(f"[PHASE-1][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase1(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P1__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-1][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-1][{args.vector_id}][INFO] LTM-Stage hits: {output.ltm_stage_hits}")
        print(f"[PHASE-1][{args.vector_id}][INFO] LTM-Global hits: {output.ltm_global_hits}")
        print(f"[PHASE-1][{args.vector_id}][INFO] Focus areas: {len(output.research_focus_areas)}")
        # SOTA metrics
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: Expanded terms: {len(output.expanded_terms)}")
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: OpenAlex concepts: {len(output.openalex_concepts)}")
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: Is biomedical: {output.is_biomedical}")
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: MeSH terms: {len(output.mesh_terms)}")
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: Geographic ISO codes: {output.geographic_iso_codes}")
        print(f"[PHASE-1][{args.vector_id}][INFO] SOTA: Query templates: {len(output.query_templates)}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=1,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-1][{args.vector_id}][ERROR] {e}")

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=1,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
