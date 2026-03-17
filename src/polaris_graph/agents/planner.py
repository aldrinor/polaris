"""
Query planner agent for polaris graph.

Uses STORM multi-perspective methodology to produce diverse sub-queries
across 9 research perspectives for comprehensive evidence gathering.
"""

import logging
import os
from collections import Counter

from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.schemas import QueryPlan, SeedQueryPlan
from src.polaris_graph.state import (
    ResearchState,
    QUERIES_PER_VECTOR,
    STORM_PERSPECTIVES,
    QUERIES_PER_PERSPECTIVE,
    PG_AGENTIC_SEED_QUERIES,
)

logger = logging.getLogger(__name__)

# FIX-054: Configurable planner timeout (BUG-089).
# T052: All 3 SeedQueryPlan attempts timed out at 120s each.
# require_parameters=true may route to slower providers.
PG_PLANNER_TIMEOUT = int(os.getenv("PG_PLANNER_TIMEOUT", "180"))

# FIX-C9: Configurable fallback query count (LAW VI: no hardcoded counts).
PG_FALLBACK_QUERY_COUNT = int(os.getenv("PG_FALLBACK_QUERY_COUNT", "22"))

_PERSPECTIVE_QUERY_TEMPLATES = {
    "Regulatory": "{topic} government regulations standards compliance requirements",
    "Economic": "{topic} cost-effectiveness economic analysis market size investment",
    "Industry": "{topic} industrial application case study pilot plant scale-up deployment",
    "Public_Health": "{topic} health impact risk assessment epidemiology safety",
    "Historical": "{topic} historical development evolution timeline milestones origin",
    "Regional": "{topic} regional differences geographic variation country comparison",
    "Emerging_Trends": "{topic} recent advances novel approaches 2024 2025 breakthrough innovation",
    "Methodological": "{topic} methodology experimental design measurement technique protocol",
}


def _generate_diversity_queries(
    query: str,
    underrepresented: list[str],
) -> list[dict]:
    """RC-7: Generate targeted queries for underrepresented perspectives.

    Returns list of SubQuery-compatible dicts.
    """
    queries = []
    for perspective in underrepresented[:4]:  # Cap at 4 extra perspectives
        template = _PERSPECTIVE_QUERY_TEMPLATES.get(perspective)
        if template:
            queries.append({
                "query": template.format(topic=query[:100]),
                "intent": f"Fill gap in {perspective} perspective",
                "source_preference": "both",
                "perspective": perspective,
            })

    if queries:
        logger.info(
            "[polaris graph] RC-7: Generated %d diversity queries for perspectives: %s",
            len(queries),
            [q["perspective"] for q in queries],
        )

    return queries



# Build perspective description block dynamically from STORM_PERSPECTIVES
_PERSPECTIVE_DESCRIPTIONS = {
    "Scientific": "mechanisms, dose-response, empirical data, laboratory findings, systematic reviews",
    "Regulatory": "standards, compliance, policy frameworks, government guidelines, legal requirements",
    "Industry": "products, specifications, market data, manufacturer testing, industry reports",
    "Economic": "costs, cost-benefit analysis, market analysis, economic impact, pricing data",
    "Public_Health": "epidemiology, health outcomes, risk assessment, population-level data",
    "Historical": "development timeline, evolution of knowledge, landmark studies, foundational works",
    "Regional": "geographic variations, local data, country-specific regulations, regional case studies",
    "Methodological": "measurement protocols, study design, analytical methods, quality assurance",
    "Emerging_Trends": "innovations, future directions, emerging technologies, recent breakthroughs",
}

_PERSPECTIVE_BLOCK = "\n".join(
    f"- {p}: {_PERSPECTIVE_DESCRIPTIONS.get(p, 'general research')}"
    for p in STORM_PERSPECTIVES
)

PLANNER_SYSTEM = f"""You are a SOTA research query planner using the STORM multi-perspective methodology.
Your job is to decompose a research question into {QUERIES_PER_VECTOR}+ diverse, specific sub-queries
that maximize evidence coverage across web, academic, and government sources.

STORM METHODOLOGY — Generate {QUERIES_PER_PERSPECTIVE} queries per perspective:
{_PERSPECTIVE_BLOCK}

Rules:
1. Generate {QUERIES_PER_VECTOR} sub-queries minimum, covering ALL {len(STORM_PERSPECTIVES)} perspectives.
2. Each query MUST have a "perspective" field matching one of the perspectives above.
3. Include queries targeting:
   - Systematic reviews and meta-analyses (highest quality evidence)
   - Government reports and regulatory documents
   - Peer-reviewed journal articles
   - Industry standards and specifications (ISO, ANSI, IEC, etc.)
   - Real-world case studies and field data
   - Recent publications (2023-2026)
   - Seminal/foundational works
4. Vary query specificity: some broad (context), some narrow (specific data points).
5. For 'academic' source_preference queries, use precise technical terminology.
6. For 'web' queries, use more natural language to capture diverse sources.
7. Do NOT include domain-specific jargon unrelated to the research question.

Output format example:
{{"analysis": "The question requires evidence on mechanisms, regulations, and impacts", "search_strategy": "broad", "sub_queries": [{{"query": "systematic review meta-analysis [TOPIC]", "intent": "Find synthesized evidence", "source_preference": "academic", "perspective": "Scientific"}}, {{"query": "EPA WHO regulations [TOPIC] standards 2024", "intent": "Current regulatory framework", "source_preference": "web", "perspective": "Regulatory"}}], "key_concepts": ["concept A", "concept B"], "expected_source_types": ["journal", "government", "industry"], "perspective_coverage": {{"Scientific": 6, "Regulatory": 6}}}}"""


async def plan_queries(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict:
    """
    Plan research queries using STORM multi-perspective methodology.

    Returns state update with sub_queries, search_strategy, and perspective_distribution.
    """
    query = state["original_query"]
    application = state["application"]
    region = state["region"]
    iteration = state["iteration_count"]

    gaps_context = ""
    if state.get("gaps"):
        gaps_context = (
            f"\n\nPrevious iteration identified these evidence gaps:\n"
            + "\n".join(f"- {g}" for g in state["gaps"])
            + "\n\nPrioritize queries that fill these gaps."
        )

    # Sprint 1B: Inject LTM prior knowledge so planner targets gaps, not duplications
    prior_context = ""
    ltm_priors = state.get("memory_ltm_priors", [])
    if ltm_priors:
        prior_lines = []
        for p in ltm_priors[:10]:
            stmt = p.get("statement", "")[:120]
            tier = p.get("quality_tier", "")
            src_vec = p.get("vector_id", "")[:30]
            prior_lines.append(f"- [{tier}] {stmt} (from {src_vec})")
        prior_context = (
            "\n\nPRIOR KNOWLEDGE (from previous research — target gaps, not duplications):\n"
            + "\n".join(prior_lines)
            + "\n\nWe already know the above. Focus queries on uncovered aspects "
            "and perspectives not represented in prior knowledge."
        )
        logger.info(
            "[polaris graph] Sprint 1B: Injecting %d LTM priors into planner",
            len(ltm_priors),
        )

    # G3: Inject uploaded documents as GOLD sources for targeted queries
    uploaded_docs_context = ""
    uploaded_docs = state.get("uploaded_documents", [])
    if uploaded_docs:
        doc_lines = []
        for doc in uploaded_docs[:10]:
            fname = doc.get("filename", "unknown")
            preview = doc.get("content_preview", "")[:200]
            doc_lines.append(f"- [GOLD SOURCE] {fname}: {preview}")
        uploaded_docs_context = (
            "\n\nUPLOADED CORPORATE DOCUMENTS (GOLD tier -- treat as primary evidence):\n"
            + "\n".join(doc_lines)
            + "\n\nInclude queries that specifically extract claims from these GOLD documents."
        )
        logger.info(
            "[polaris graph] G3: Injecting %d uploaded documents into planner",
            len(uploaded_docs),
        )

    # A7.4: Retrieve human overrides to avoid repeating corrected mistakes
    override_context = ""
    try:
        from src.polaris_graph.memory.cross_vector import query_human_overrides
        overrides = query_human_overrides(query=query, k=10)
        if overrides:
            override_lines = []
            for o in overrides[:5]:
                ctx = o.get("context", "")[:200]
                otype = o.get("override_type", "unknown")
                override_lines.append(f"- Previous correction ({otype}): {ctx}")
            override_context = (
                "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
                + "\n".join(override_lines)
            )
            logger.info(
                "[polaris graph] A7.4: Injecting %d human overrides into planner",
                len(overrides),
            )
    except Exception as ho_exc:
        logger.debug("[polaris graph] A7.4: Override retrieval failed (non-blocking): %s", str(ho_exc)[:100])

    # Campaign Control Center: inject research brief for domain context
    research_brief_context = ""
    brief = state.get("research_brief", "")
    if brief.strip():
        research_brief_context = (
            f"\n\nRESEARCH BRIEF (domain context -- use to guide query generation):\n"
            f"{brief[:2000]}\n"
        )

    prompt = f"""Research question: {query}
Application domain: {application}
Geographic focus: {region}
Iteration: {iteration + 1}
{gaps_context}{prior_context}{uploaded_docs_context}{override_context}{research_brief_context}

Generate a comprehensive STORM query plan with {QUERIES_PER_VECTOR}+ sub-queries
covering all {len(STORM_PERSPECTIVES)} perspectives ({QUERIES_PER_PERSPECTIVE} per perspective).
Ensure every perspective is represented for maximum evidence diversity."""

    # Use generate_structured() — reasoning OFF for reliable JSON.
    # reason() + schema causes Kimi to put JSON in reasoning_content,
    # which breaks parsing. generate_structured() reliably produces JSON.
    plan = await client.generate_structured(
        prompt=prompt,
        schema=QueryPlan,
        system=PLANNER_SYSTEM,
        max_tokens=8192,
        timeout=PG_PLANNER_TIMEOUT,
    )

    sub_queries = [sq.query for sq in plan.sub_queries]

    # Fallback: if LLM returned 0 queries (transient API issue),
    # generate basic queries from the research question
    if not sub_queries:
        logger.warning(
            "[polaris graph] Planner returned 0 queries — using fallback"
        )
        sub_queries = _fallback_queries(query, application, region)

    # Compute perspective distribution from plan
    perspective_dist = Counter(
        sq.perspective for sq in plan.sub_queries
    )

    # Log perspective coverage
    covered = [p for p in STORM_PERSPECTIVES if perspective_dist.get(p, 0) > 0]
    missing = [p for p in STORM_PERSPECTIVES if perspective_dist.get(p, 0) == 0]

    logger.info(
        "[polaris graph] STORM Planner: %d queries, strategy=%s, "
        "perspectives=%d/%d covered, concepts=%s",
        len(sub_queries),
        plan.search_strategy,
        len(covered),
        len(STORM_PERSPECTIVES),
        plan.key_concepts[:5],
    )
    if missing:
        logger.warning(
            "[polaris graph] Missing perspectives: %s",
            missing,
        )

    tracer = get_tracer()
    if tracer:
        tracer.evidence("plan", "query_plan", len(sub_queries),
            search_strategy=plan.search_strategy,
            key_concepts=plan.key_concepts[:10],
            perspective_distribution=dict(perspective_dist),
            covered_perspectives=covered,
            missing_perspectives=missing,
            queries=[{"query": sq.query, "perspective": sq.perspective,
                      "intent": sq.intent, "source_preference": sq.source_preference}
                     for sq in plan.sub_queries])

    # RC-7: Source diversity — add targeted queries for underrepresented perspectives
    if os.getenv("PG_V3_SOURCE_DIVERSITY", "0") == "1":
        try:
            from src.polaris_graph.agents.searcher import _compute_perspective_distribution
            current_evidence = state.get("evidence", [])
            if current_evidence:
                distribution, underrepresented = _compute_perspective_distribution(current_evidence)
                if underrepresented:
                    diversity_queries = _generate_diversity_queries(query, underrepresented)
                    for dq in diversity_queries:
                        sub_queries.append(dq["query"])
                    if diversity_queries:
                        logger.info(
                            "[polaris graph] RC-7: Appended %d diversity queries to fill perspective gaps",
                            len(diversity_queries),
                        )
        except Exception as exc:
            logger.warning("[polaris graph] RC-7: Diversity query generation failed: %s", str(exc)[:200])


    return {
        "sub_queries": sub_queries,
        "search_strategy": plan.search_strategy,
        "perspective_distribution": dict(perspective_dist),
        "status": "searching",
    }


SEED_PLANNER_SYSTEM = f"""You are a SOTA research query planner using the STORM multi-perspective methodology.
Your job is to generate exactly {PG_AGENTIC_SEED_QUERIES} seed queries — ONE query per perspective.
Each query should be the single most important search for that perspective.

STORM PERSPECTIVES (generate exactly 1 query per perspective):
{_PERSPECTIVE_BLOCK}

Rules:
1. Generate exactly {PG_AGENTIC_SEED_QUERIES} queries — one per perspective.
2. Each query MUST have a "perspective" field matching one of the perspectives above.
3. Each query should be the most impactful, highest-value search for its perspective.
4. Use "source_preference" to indicate the best source type:
   - "academic" for Scientific, Methodological, Historical (precise terminology)
   - "web" for Industry, Economic, Regional, Emerging_Trends (natural language)
   - "both" for Regulatory, Public_Health
5. These are SEED queries — an agentic loop will generate follow-up queries based on results.
   Focus on breadth across perspectives, not depth within any single perspective.

Output format: {{"analysis": "Brief analysis", "sub_queries": [{{"query": "...", "intent": "...", "source_preference": "academic", "perspective": "Scientific"}}, ...]}}"""


async def plan_seed_queries(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict:
    """
    Plan seed queries for the agentic search loop.

    Generates exactly 9 seed queries (1 per STORM perspective) instead of 50+.
    The agentic loop will generate follow-up queries informed by results.

    Returns state update with sub_queries, search_strategy, and perspective_distribution.
    """
    query = state["original_query"]
    application = state["application"]
    region = state["region"]

    # M-16: Inject learned strategies from session feedback memory
    strategy_block = ""
    best_strategies = state.get("memory_best_strategies", [])
    if best_strategies:
        strategy_lines = []
        for s in best_strategies[:5]:
            strategy_lines.append(
                f"- '{s.get('query_text', '')[:80]}' ({s.get('search_type', 'web')}) -> "
                f"{s.get('total_evidence', 0)} evidence, relevance {s.get('avg_relevance', 0):.2f}"
            )
        strategy_block = (
            "\n\nLEARNED STRATEGIES (from previous successful searches):\n"
            + "\n".join(strategy_lines)
            + "\n\nUse these as inspiration for effective query patterns."
        )
        logger.info(
            "[polaris graph] M-16: Injecting %d learned strategies into seed planner",
            len(best_strategies[:5]),
        )

    # Sprint 1B: Inject LTM prior knowledge into seed planner
    prior_context = ""
    ltm_priors = state.get("memory_ltm_priors", [])
    if ltm_priors:
        prior_lines = []
        for p in ltm_priors[:10]:
            stmt = p.get("statement", "")[:120]
            tier = p.get("quality_tier", "")
            prior_lines.append(f"- [{tier}] {stmt}")
        prior_context = (
            "\n\nPRIOR KNOWLEDGE (from previous research — target gaps, not duplications):\n"
            + "\n".join(prior_lines)
            + "\n\nWe already know the above. Focus seed queries on uncovered aspects."
        )
        logger.info(
            "[polaris graph] Sprint 1B: Injecting %d LTM priors into seed planner",
            len(ltm_priors),
        )

    # A7.4: Retrieve human overrides to avoid repeating corrected mistakes
    override_context = ""
    try:
        from src.polaris_graph.memory.cross_vector import query_human_overrides
        overrides = query_human_overrides(query=query, k=10)
        if overrides:
            override_lines = []
            for o in overrides[:5]:
                ctx = o.get("context", "")[:200]
                otype = o.get("override_type", "unknown")
                override_lines.append(f"- Previous correction ({otype}): {ctx}")
            override_context = (
                "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
                + "\n".join(override_lines)
            )
            logger.info(
                "[polaris graph] A7.4: Injecting %d human overrides into seed planner",
                len(overrides),
            )
    except Exception as ho_exc:
        logger.debug("[polaris graph] A7.4: Override retrieval failed (non-blocking): %s", str(ho_exc)[:100])

    # Campaign Control Center: inject research brief for domain context
    seed_brief_context = ""
    seed_brief = state.get("research_brief", "")
    if seed_brief.strip():
        seed_brief_context = (
            f"\n\nRESEARCH BRIEF (domain context -- use to guide query generation):\n"
            f"{seed_brief[:2000]}\n"
        )

    prompt = f"""Research question: {query}
Application domain: {application}
Geographic focus: {region}
{strategy_block}{prior_context}{override_context}{seed_brief_context}

Generate exactly {PG_AGENTIC_SEED_QUERIES} seed queries — one per STORM perspective.
Each query should be the single most important search for its perspective.
These seeds will feed an agentic search loop that generates follow-up queries based on results."""

    # FIX-059-J: 3x retry with exponential backoff for seed planner.
    # T058 had only 10 queries (fallback) because single LLM call failed.
    import asyncio as _asyncio
    _seed_max_retries = 3
    _seed_backoff = [1, 3, 9]  # seconds
    plan = None
    sub_queries = []
    for _attempt in range(_seed_max_retries):
        try:
            plan = await client.generate_structured(
                prompt=prompt,
                schema=SeedQueryPlan,
                system=SEED_PLANNER_SYSTEM,
                max_tokens=4096,
                timeout=PG_PLANNER_TIMEOUT,
            )
            sub_queries = [sq.query for sq in plan.sub_queries]
            if sub_queries:
                break  # Success
            logger.warning(
                "[polaris graph] FIX-059-J: Seed planner returned 0 queries "
                "(attempt %d/%d)",
                _attempt + 1, _seed_max_retries,
            )
        except Exception as plan_exc:
            logger.warning(
                "[polaris graph] FIX-059-J: Seed planner attempt %d/%d failed: %s",
                _attempt + 1, _seed_max_retries, str(plan_exc)[:200],
            )
            plan = None
            sub_queries = []
        if _attempt < _seed_max_retries - 1:
            await _asyncio.sleep(_seed_backoff[_attempt])
    if not sub_queries:
        logger.error(
            "[polaris graph] FIX-059-J: Seed planner failed after %d attempts "
            "— using fallback queries",
            _seed_max_retries,
        )

    # Fallback: if LLM returned 0 queries or failed entirely, generate basic
    # 1-per-perspective fallback so the pipeline can proceed
    if not sub_queries:
        logger.warning(
            "[polaris graph] Seed planner returned 0 queries — using fallback"
        )
        sub_queries = _seed_fallback_queries(query, application, region)

    # Compute perspective distribution
    perspective_dist = Counter(
        sq.perspective for sq in (plan.sub_queries if plan else [])
    )

    covered = [p for p in STORM_PERSPECTIVES if perspective_dist.get(p, 0) > 0]

    logger.info(
        "[polaris graph] Seed Planner: %d queries, perspectives=%d/%d covered "
        "(agentic loop will expand)",
        len(sub_queries),
        len(covered),
        len(STORM_PERSPECTIVES),
    )

    tracer = get_tracer()
    if tracer:
        tracer.evidence("plan", "seed_query_plan", len(sub_queries),
            search_strategy="agentic",
            key_concepts=[],
            perspective_distribution=dict(perspective_dist),
            covered_perspectives=covered,
            missing_perspectives=[p for p in STORM_PERSPECTIVES if perspective_dist.get(p, 0) == 0],
            retry_attempts=_attempt + 1 if plan else _seed_max_retries,
            queries=[{"query": sq.query, "perspective": sq.perspective,
                      "intent": sq.intent, "source_preference": sq.source_preference}
                     for sq in (plan.sub_queries if plan else [])])

    return {
        "sub_queries": sub_queries,
        "search_strategy": "agentic",
        "perspective_distribution": dict(perspective_dist),
        "status": "searching",
    }


def _seed_fallback_queries(query: str, application: str, region: str) -> list[str]:
    """Generate fallback queries from STORM perspectives when LLM seed planner fails.

    FIX-C9: Capped to PG_AGENTIC_SEED_QUERIES (LAW VI). Generates one per
    perspective, then truncates to the configured seed query count.
    """
    templates = {
        "Scientific": f"systematic review {application} meta-analysis",
        "Regulatory": f"{application} regulatory framework {region} standards",
        "Industry": f"{application} industry report market data specifications",
        "Economic": f"{application} cost-benefit analysis economic impact",
        "Public_Health": f"{application} health outcomes epidemiology risk assessment",
        "Historical": f"{application} history development timeline foundational research",
        "Regional": f"{application} {region} case study regional data",
        "Methodological": f"{application} measurement protocol analytical methods",
        "Emerging_Trends": f"{application} innovation emerging technology 2025 2026",
    }
    all_queries = [templates.get(p, query) for p in STORM_PERSPECTIVES]
    return all_queries[:PG_AGENTIC_SEED_QUERIES]


def _fallback_queries(query: str, application: str, region: str) -> list[str]:
    """Generate generic topic-agnostic fallback queries when LLM planner fails.

    Uses {application}, {region}, and {query} parameters to construct
    diverse queries across all STORM perspectives. No domain-specific
    assumptions (LAW VI compliance).

    FIX-C9: Count configurable via PG_FALLBACK_QUERY_COUNT env var.
    """
    all_queries = [
        # Original query (always first)
        query,
        # Scientific
        f"systematic review {application} meta-analysis",
        f"{application} mechanisms empirical evidence",
        f"{application} dose-response relationship studies",
        f"{application} laboratory findings peer-reviewed",
        # Regulatory
        f"{application} regulatory framework {region}",
        f"{application} compliance standards guidelines",
        f"{application} government policy regulations 2024 2025",
        # Industry
        f"{application} industry report market data",
        f"{application} product specifications testing",
        f"{application} manufacturer standards ISO ANSI",
        # Economic
        f"{application} cost-benefit analysis economic impact",
        f"{application} market size pricing data {region}",
        # Public Health
        f"{application} health outcomes epidemiology",
        f"{application} risk assessment population study",
        # Historical
        f"{application} history development timeline",
        f"{application} foundational research seminal study",
        # Regional
        f"{application} {region} case study local data",
        f"{application} geographic variations regional differences",
        # Methodological
        f"{application} measurement protocol study design",
        f"{application} quality assurance analytical methods",
        # Emerging Trends
        f"{application} innovation emerging technology 2025 2026",
        f"{application} future directions research trends",
    ]
    # FIX-C9: Truncate to configured count
    return all_queries[:PG_FALLBACK_QUERY_COUNT]
