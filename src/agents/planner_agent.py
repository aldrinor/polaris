"""
POLARIS v3 Planner Agent

Decomposes complex research queries into:
- Sub-questions for targeted search
- Research plan with phases
- Search strategy (breadth-first, depth-first, hybrid)

Based on STORM (Stanford) perspective-guided approach.
"""

import logging
from typing import List, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, SubQuery
try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived

# SOTA Integration: Multi-language support (Task #21)
from src.utils.language_handler import LanguageHandler, Language

# FIX-124C: Topic anchoring to prevent corpus pollution
from src.utils.query_utils import extract_core_topic_terms, validate_query_relevance


logger = logging.getLogger(__name__)


# =============================================================================
# Output Schemas
# =============================================================================

class SubQueryPlan(BaseModel):
    """A single sub-query in the research plan."""
    query_text: str = Field(description="The sub-question to answer")
    expected_data_type: Literal["factual", "statistical", "comparative", "procedural"] = Field(
        description="Type of data expected"
    )
    # NOTE: Removed ge/le constraints - Gemini structured output can't handle them
    # Validation: priority should be 1-5 (enforced in code, not schema)
    priority: int = Field(description="Priority 1 (highest) to 5 (lowest)")
    search_keywords: List[str] = Field(description="Keywords for search queries")
    domain_hints: List[str] = Field(
        default_factory=list,
        description="Suggested domains (e.g., cdc.gov, pubmed)"
    )
    # FIX-124: STORM perspective tracking
    perspective_name: str = Field(
        default="General",
        description="STORM perspective that generated this query (Scientific, Regulatory, Industry, Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends)"
    )


class ResearchPlan(BaseModel):
    """Complete research plan from Planner agent."""
    # NOTE: Removed min_length/max_length constraints - Gemini structured output
    # can't handle complex constraints on nested lists. Validation done in code.
    # Target: 5-50 sub-queries for comprehensive coverage
    sub_queries: List[SubQueryPlan] = Field(
        description="Sub-questions to answer (target: 20-50 for deep research)"
    )
    search_strategy: Literal["breadth_first", "depth_first", "hybrid"] = Field(
        description="Overall search strategy"
    )
    key_entities: List[str] = Field(
        description="Key entities/concepts to track"
    )
    potential_sources: List[str] = Field(
        description="Types of sources to prioritize"
    )
    reasoning: str = Field(
        description="Explanation of research approach"
    )


# =============================================================================
# Planner Agent
# =============================================================================

@register_agent("planner")
class PlannerAgent(BaseAgent):
    """
    Planner Agent - Decomposes queries into research plans.

    Responsibilities:
    1. Break complex query into sub-questions
    2. Assign priorities and data types
    3. Identify key entities to track
    4. Recommend search strategy
    5. Suggest source types

    Uses STORM-inspired perspective approach for comprehensive coverage.
    Depth configuration loaded from .env via DepthConfig (LAW VI: Zero hard-coding).
    """

    def __init__(self):
        # Load depth configuration from .env (LAW VI)
        self.depth_config = get_depth_config()

        config = AgentConfig(
            name="planner",
            description="Decomposes research queries into actionable sub-questions",
            task_tier="important",  # Complex reasoning for query decomposition
            temperature=0.1,
            max_tokens=8000,
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        # Get target query count from depth config
        target_queries = self.depth_config.query_generation.top_queries_limit

        return f"""You are a Research Planning Specialist using the STORM methodology. Your job is to decompose complex research questions into actionable sub-questions.

SOTA DEEP RESEARCH REQUIREMENTS:
- Generate 20-30 comprehensive sub-questions for thorough coverage
- Target: {target_queries} total queries after amplification
- Cover key perspectives efficiently - keep search_keywords to 3-5 terms per query

STORM APPROACH:
Generate sub-questions from multiple expert perspectives to ensure comprehensive coverage.
CRITICAL: You MUST specify which perspective generated each sub-query using the perspective_name field.

STORM PERSPECTIVES (you MUST use these exact names):
- Scientific: What does the research literature say? (peer-reviewed studies, experiments)
- Regulatory: What regulations and standards apply? (laws, compliance, agencies)
- Industry: What are current practices and solutions? (manufacturers, products, best practices)
- Economic: What are the costs and market factors? (pricing, market size, ROI)
- Public_Health: What are the health implications? (disease burden, risk factors, outcomes)
- Historical: How has this evolved over time? (timeline, milestones, changes)
- Regional: How does this vary by geography? (local factors, regional differences)
- Methodological: What research methods are used? (measurement, testing, protocols)
- Emerging_Trends: What are future directions? (innovations, forecasts, emerging tech)

FIX-124: STORM PERSPECTIVE TRACKING REQUIREMENT
FOR EACH SUB-QUERY, YOU MUST SPECIFY:
- query_text: The specific ANALYTICAL research question (NOT a keyword query)
- perspective_name: Which STORM perspective generated this query (use exact names above)
- expected_data_type: What type of data this will return
- search_keywords: 3-5 key terms for search

IMPORTANT: Generate ANALYTICAL QUESTIONS, not keyword queries:
- WRONG: "water filter contamination study" (keyword query)
- RIGHT: "What health outcomes have been documented from contaminated water filters?" (analytical question)

SUB-QUERY GUIDELINES:
1. Each sub-query should be specific and answerable
2. Assign clear data types (factual, statistical, comparative, procedural)
3. Prioritize: 1=critical for main question, 5=nice-to-have context
4. Include specific search keywords (3-5 per query)
5. Suggest authoritative domains when relevant
6. CRITICAL: Tag each query with its perspective_name

SEARCH STRATEGIES:
- breadth_first: Start wide, gather many sources, then deep-dive (best for exploratory)
- depth_first: Start with key sources, follow citations (best for technical)
- hybrid: Parallel broad and deep searches (best for complex topics)

SOURCE TYPES:
- academic: Peer-reviewed journals, systematic reviews
- government: CDC, EPA, FDA, regulatory agencies
- industry: Trade publications, manufacturer data
- news: Recent developments, case studies
- standards: ISO, ASTM, industry standards

Create a comprehensive research plan that will THOROUGHLY address the question. Generate 20-30 sub-queries with concise keywords. CRITICAL: Always include search_strategy, key_entities, potential_sources, reasoning, AND perspective_name for each sub-query."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Create research plan from query.

        SOTA GAP-DRIVEN ITERATION:
        - First iteration: Generate comprehensive sub-queries from original query
        - Subsequent iterations: Use gaps from critic to generate TARGETED queries

        Args:
            state: Current research state

        Returns:
            Updated state with sub_queries, research_plan, search_strategy
        """
        query = state.get("original_query", "")
        vector_id = state.get("vector_id", "")
        query_type = state.get("query_type", "exploratory")
        complexity = state.get("complexity", "moderate")
        region = state.get("region", "GLOBAL")
        stage = state.get("stage", 1)
        iteration_count = state.get("iteration_count", 0)

        if not query:
            raise ValueError("No query provided in state")

        # ======================================================================
        # SOTA Integration: Multi-Language Query Handling (Task #21)
        # ======================================================================
        try:
            lang_handler = LanguageHandler()
            lang_result = lang_handler.detect_language(query)

            state["query_language"] = {
                "detected": lang_result.detected_language.value,
                "confidence": lang_result.confidence,
                "is_english": lang_result.detected_language == Language.ENGLISH,
            }

            if lang_result.detected_language != Language.ENGLISH and lang_result.confidence > 0.7:
                # Translate query to English for processing
                translation = lang_handler.translate_to_english(query, lang_result.detected_language)
                if translation.success:
                    logger.info(
                        f"[LANG] Translated query from {lang_result.detected_language.value} to English: "
                        f"'{query[:50]}...' -> '{translation.translated_text[:50]}...'"
                    )
                    # Store original and use translated for planning
                    state["original_query_language"] = lang_result.detected_language.value
                    state["original_query_native"] = query
                    query = translation.translated_text
                    state["original_query"] = query  # Update for downstream processing
            else:
                logger.debug(f"[LANG] Query language: {lang_result.detected_language.value} (confidence: {lang_result.confidence:.2f})")
        except Exception as e:
            logger.warning(f"[LANG] Language detection failed: {e}")

        # SOTA FIX: Check if this is a gap-filling iteration
        gaps = state.get("gaps", [])
        gap_analysis = state.get("gap_analysis", {})
        iteration_feedback = state.get("iteration_feedback", "")

        # If gaps exist from critic, use gap-driven planning
        if gaps and iteration_count > 0:
            return self._process_gap_driven(state, query, vector_id, gaps, gap_analysis, iteration_feedback)

        # First iteration: Full planning from original query
        return self._process_initial_planning(state, query, vector_id, query_type, complexity, region, stage)

    def _process_gap_driven(
        self,
        state: ResearchState,
        query: str,
        vector_id: str,
        gaps: List,
        gap_analysis: dict,
        iteration_feedback: str
    ) -> ResearchState:
        """
        Gap-driven planning for iterations after the first.

        SOTA PATTERN: Use suggested_queries from gaps instead of regenerating from scratch.
        This is how Gemini Deep Research, STORM, and Perplexity iterate.
        """
        # Collect suggested queries from gaps
        gap_queries = []
        for gap in gaps:
            # Handle both dict and Pydantic model
            if isinstance(gap, dict):
                suggested = gap.get("suggested_queries", [])
                gap_desc = gap.get("description", "")
                gap_priority = gap.get("priority", 3)
            else:
                suggested = getattr(gap, "suggested_queries", [])
                gap_desc = getattr(gap, "description", "")
                gap_priority = getattr(gap, "priority", 3)

            for sq_text in suggested:
                gap_queries.append({
                    "query_text": sq_text,
                    "source_gap": gap_desc,
                    "priority": gap_priority
                })

        # Also check prioritized_gaps from gap_analysis
        prioritized_gaps = gap_analysis.get("prioritized_gaps", [])
        for pg in prioritized_gaps[:5]:  # Top 5 prioritized gaps
            gap_desc = pg.get("description", "")
            # If no suggested queries, create one from description
            if gap_desc and not any(gq["source_gap"] == gap_desc for gq in gap_queries):
                gap_queries.append({
                    "query_text": f"{query} {gap_desc}",
                    "source_gap": gap_desc,
                    "priority": pg.get("priority", 3)
                })

        if not gap_queries:
            # No gap queries found, fall back to LLM-based gap query generation
            logger.warning(f"No suggested_queries in gaps, using LLM to generate gap-filling queries")
            return self._generate_gap_queries_via_llm(state, query, vector_id, gaps, iteration_feedback)

        # Convert gap queries to SubQuery objects
        sub_queries = []
        existing_ids = {sq.query_id for sq in state.get("sub_queries", []) if hasattr(sq, "query_id")}

        for i, gq in enumerate(gap_queries):
            query_id = f"gap_{i+1:03d}"
            # Avoid duplicates
            if query_id in existing_ids:
                query_id = f"gap_{i+1:03d}_iter{state.get('iteration_count', 0)}"

            # FIX-124: Gap-filling queries are tagged as "Gap_Filling" perspective
            sub_query = SubQuery(
                query_id=query_id,
                query_text=gq["query_text"],
                expected_data_type="factual",  # Gap-filling is usually factual
                priority=gq["priority"],
                search_keywords=gq["query_text"].split()[:10],  # Extract keywords
                domain_hints=[],
                perspective_name="Gap_Filling",  # FIX-124: STORM perspective for gap queries
                perspective_id=f"perspective_gap_{i+1:04d}",  # FIX-124: Unique gap perspective ID
                status="pending"
            )
            sub_queries.append(sub_query)

        # APPEND to existing queries (don't replace)
        existing_queries = state.get("sub_queries", [])
        all_queries = list(existing_queries) + sub_queries

        # Update state
        state["sub_queries"] = all_queries
        state["search_strategy"] = "depth_first"  # Gap-filling is depth-first
        state["research_plan"] = {
            "key_entities": state.get("research_plan", {}).get("key_entities", []),
            "potential_sources": state.get("research_plan", {}).get("potential_sources", []),
            "reasoning": f"Gap-driven iteration: targeting {len(sub_queries)} gaps identified by critic",
            "sub_query_count": len(all_queries),
            "gap_query_count": len(sub_queries),
            "iteration_type": "gap_driven"
        }

        logger.info(
            f"Planner (GAP-DRIVEN): {vector_id} -> {len(sub_queries)} gap-filling queries "
            f"(total: {len(all_queries)}), gaps addressed: {len(gaps)}"
        )

        return state

    def _generate_gap_queries_via_llm(
        self,
        state: ResearchState,
        query: str,
        vector_id: str,
        gaps: List,
        iteration_feedback: str
    ) -> ResearchState:
        """
        Generate gap-filling queries using LLM when suggested_queries not available.
        """
        # Format gaps for LLM
        gap_descriptions = []
        for gap in gaps[:10]:  # Limit to top 10 gaps
            if isinstance(gap, dict):
                desc = gap.get("description", "")
                gap_type = gap.get("gap_type", "unknown")
            else:
                desc = getattr(gap, "description", "")
                gap_type = getattr(gap, "gap_type", "unknown")
            if desc:
                gap_descriptions.append(f"- [{gap_type}] {desc}")

        gap_text = "\n".join(gap_descriptions) if gap_descriptions else "No specific gaps identified"

        context = f"""
Original Research Question: {query}

ITERATION MODE: You are in gap-filling iteration. The critic has identified these gaps:

{gap_text}

Critic's recommendation: {iteration_feedback}

Generate 5-15 TARGETED sub-questions that specifically address these gaps.
Do NOT regenerate general questions - focus ONLY on filling the identified gaps.
"""

        messages = [
            SystemMessage(content=self._get_gap_filling_prompt()),
            HumanMessage(content=context)
        ]

        plan: ResearchPlan = self.call_llm_structured(messages, ResearchPlan)

        # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
        if plan is None:
            logger.warning("Planner LLM returned None (timeout or parsing failure), returning empty gap-filling plan")
            return state

        # Convert to SubQuery objects
        # FIX-124: LLM gap queries preserve perspective from LLM response
        sub_queries = []
        for i, sq in enumerate(plan.sub_queries):
            perspective_name = getattr(sq, 'perspective_name', 'Gap_Filling') or 'Gap_Filling'
            sub_query = SubQuery(
                query_id=f"gap_llm_{i+1:03d}",
                query_text=sq.query_text,
                expected_data_type=sq.expected_data_type,
                priority=sq.priority,
                search_keywords=sq.search_keywords,
                domain_hints=sq.domain_hints,
                perspective_name=perspective_name,  # FIX-124: STORM perspective
                perspective_id=f"perspective_gap_llm_{i+1:04d}",  # FIX-124: Unique perspective ID
                status="pending"
            )
            sub_queries.append(sub_query)

        # APPEND to existing queries
        existing_queries = state.get("sub_queries", [])
        all_queries = list(existing_queries) + sub_queries

        state["sub_queries"] = all_queries
        state["search_strategy"] = "depth_first"
        state["research_plan"] = {
            "key_entities": state.get("research_plan", {}).get("key_entities", []),
            "potential_sources": state.get("research_plan", {}).get("potential_sources", []),
            "reasoning": f"LLM-generated gap-filling: {len(sub_queries)} queries for {len(gaps)} gaps",
            "sub_query_count": len(all_queries),
            "gap_query_count": len(sub_queries),
            "iteration_type": "gap_driven_llm"
        }

        logger.info(
            f"Planner (GAP-LLM): {vector_id} -> {len(sub_queries)} gap queries generated via LLM"
        )

        return state

    def _validate_queries(
        self,
        original_query: str,
        sub_queries: List[SubQuery],
        vector_id: str = ""
    ) -> List[SubQuery]:
        """FIX 46 + FIX-124C: Validate sub-queries against original research question.

        Filters out queries that are off-topic or unlikely to contribute
        to answering the original research question.

        Uses:
        1. FIX-124C: Topic anchoring (core terms from vector_id)
        2. FIX 46: Embedding similarity
        """
        import os
        if os.environ.get("POLARIS_SKIP_QUERY_VALIDATION", "0") == "1":
            return sub_queries

        # FIX-124C: Extract core topic terms for anchoring validation
        core_terms = extract_core_topic_terms(vector_id) if vector_id else []
        if not core_terms:
            # Fallback to extracting from original query
            from src.utils.query_utils import extract_core_topic_from_query
            core_terms = extract_core_topic_from_query(original_query)

        if core_terms:
            # First pass: filter by topic relevance
            topic_validated = []
            topic_rejected = 0
            for sq in sub_queries:
                is_relevant, score = validate_query_relevance(sq.query_text, core_terms)
                if is_relevant or score >= 0.1:  # Keep if any overlap
                    topic_validated.append(sq)
                else:
                    topic_rejected += 1

            if topic_rejected > 0:
                logger.info(
                    f"[FIX-124C] Topic anchoring: rejected {topic_rejected}/{len(sub_queries)} off-topic queries "
                    f"(core terms: {core_terms[:3]})"
                )
            sub_queries = topic_validated if topic_validated else sub_queries  # Don't filter all

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            # Lazy-load model
            if not hasattr(self, '_embed_model'):
                self._embed_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("[FIX 46] Loaded sentence-transformers for query validation")

            # Encode original query
            query_embedding = self._embed_model.encode(original_query, convert_to_numpy=True)
            query_norm = query_embedding / np.linalg.norm(query_embedding)

            # Encode sub-queries
            sub_query_texts = [sq.query_text for sq in sub_queries]
            sub_embeddings = self._embed_model.encode(sub_query_texts, convert_to_numpy=True)
            sub_norms = sub_embeddings / np.linalg.norm(sub_embeddings, axis=1, keepdims=True)

            # Compute similarities
            similarities = np.dot(sub_norms, query_norm)

            # Filter queries with similarity >= 0.3 (reasonably related)
            RELEVANCE_THRESHOLD = 0.3
            validated = []
            for i, sq in enumerate(sub_queries):
                if similarities[i] >= RELEVANCE_THRESHOLD:
                    validated.append(sq)
                else:
                    logger.debug(f"[FIX 46] Filtered off-topic query (sim={similarities[i]:.2f}): {sq.query_text[:50]}...")

            # Ensure we keep at least 5 queries (avoid over-filtering)
            if len(validated) < 5 and len(sub_queries) >= 5:
                # Sort by similarity and keep top 5
                sorted_indices = np.argsort(similarities)[::-1]
                validated = [sub_queries[i] for i in sorted_indices[:max(5, len(validated))]]
                logger.warning(f"[FIX 46] Over-filtered, keeping top {len(validated)} queries by similarity")

            return validated

        except ImportError:
            logger.warning("[FIX 46] sentence-transformers not installed, skipping query validation")
            return sub_queries
        except Exception as e:
            logger.warning(f"[FIX 46] Query validation failed: {e}, returning all queries")
            return sub_queries

    def _get_gap_filling_prompt(self) -> str:
        """System prompt for gap-filling mode."""
        return """You are a Research Gap Analyst. Your job is to generate TARGETED queries that fill specific gaps in research coverage.

CRITICAL: This is GAP-FILLING mode, not initial planning.
- Do NOT generate broad exploratory questions
- Do NOT repeat questions that have already been researched
- ONLY generate questions that directly address the identified gaps

For each gap:
1. Understand what information is missing
2. Generate 1-3 specific queries to find that information
3. Use precise search terms that will find the missing data

Generate queries that are:
- Highly specific to the gap
- Likely to find authoritative sources
- Different from previous queries (avoid duplication)

Target: 5-15 gap-filling queries total."""

    def _process_initial_planning(
        self,
        state: ResearchState,
        query: str,
        vector_id: str,
        query_type: str,
        complexity: str,
        region: str,
        stage: int
    ) -> ResearchState:
        """
        Initial planning for first iteration - comprehensive query decomposition.

        FIX 72: Now includes LTM context to avoid re-researching known topics.
        """
        # FIX 72: Build prior knowledge context from LTM
        prior_knowledge = ""
        ltm_stage_context = state.get("ltm_stage_context", [])
        ltm_global_context = state.get("ltm_global_context", [])

        if ltm_stage_context or ltm_global_context:
            prior_knowledge = "\n## PRIOR KNOWLEDGE (Already researched - DO NOT re-research these topics):\n"

            # Add stage-level context (same topic, same region)
            for i, doc in enumerate(ltm_stage_context[:5]):
                content = doc.get("text", doc.get("content", ""))[:300]
                if content:
                    prior_knowledge += f"  {i+1}. [Stage {stage}] {content}...\n"

            # Add global context (cross-stage insights)
            for i, doc in enumerate(ltm_global_context[:3]):
                content = doc.get("content", doc.get("text", ""))[:200]
                if content:
                    prior_knowledge += f"  {i+6}. [Global] {content}...\n"

            prior_knowledge += "\nFocus on GAPS in the above knowledge. Generate queries for what is NOT covered.\n"
            logger.info(
                f"[FIX 72] Planner received {len(ltm_stage_context)} stage + "
                f"{len(ltm_global_context)} global prior knowledge items"
            )

        # Build context
        context = f"""
Research Question: {query}

Context:
- Vector ID: {vector_id}
- Query Type: {query_type}
- Complexity: {complexity}
- Geographic Scope: {region}
- Research Stage: {stage}
{prior_knowledge}
Create a detailed research plan with sub-questions that will comprehensively answer this question.
If prior knowledge is provided, focus on GAPS and NEW angles not already covered.
"""

        # Call LLM with structured output
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=context)
        ]

        plan: ResearchPlan = self.call_llm_structured(messages, ResearchPlan)

        # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
        if plan is None:
            logger.warning("Planner LLM returned None (timeout or parsing failure), returning empty plan")
            return state

        # Convert to SubQuery objects
        # FIX-124: Track perspective distribution for logging
        perspective_counts = {}
        sub_queries = []
        for i, sq in enumerate(plan.sub_queries):
            # FIX-124: Generate perspective ID from perspective name
            perspective_name = getattr(sq, 'perspective_name', 'General') or 'General'
            perspective_id = f"perspective_{hash(perspective_name) % 10000:04d}"

            # Track perspective distribution
            perspective_counts[perspective_name] = perspective_counts.get(perspective_name, 0) + 1

            sub_query = SubQuery(
                query_id=f"sq_{i+1:03d}",
                query_text=sq.query_text,
                expected_data_type=sq.expected_data_type,
                priority=sq.priority,
                search_keywords=sq.search_keywords,
                domain_hints=sq.domain_hints,
                perspective_name=perspective_name,  # FIX-124: STORM perspective
                perspective_id=perspective_id,  # FIX-124: STORM perspective ID
                status="pending"
            )
            sub_queries.append(sub_query)

        # FIX-124: Log perspective distribution
        if perspective_counts:
            dist_str = ", ".join(f"{k}={v}" for k, v in sorted(perspective_counts.items()))
            logger.info(f"[FIX-124] Perspective distribution: {dist_str}")

        # FIX 46 + FIX-124C: Query validation loop - filter out off-topic queries
        validated_queries = self._validate_queries(query, sub_queries, vector_id=vector_id)
        if len(validated_queries) < len(sub_queries):
            logger.info(
                f"[FIX 46] Query validation: {len(sub_queries)} -> {len(validated_queries)} queries "
                f"(filtered {len(sub_queries) - len(validated_queries)} off-topic)"
            )
            state["query_validation_stats"] = {
                "original_count": len(sub_queries),
                "validated_count": len(validated_queries),
                "filtered_count": len(sub_queries) - len(validated_queries)
            }
        sub_queries = validated_queries

        # Update state
        state["sub_queries"] = sub_queries
        state["search_strategy"] = plan.search_strategy
        state["research_plan"] = {
            "key_entities": plan.key_entities,
            "potential_sources": plan.potential_sources,
            "reasoning": plan.reasoning,
            "sub_query_count": len(sub_queries),
            "iteration_type": "initial"
        }

        logger.info(
            f"Planner (INITIAL): {vector_id} -> {len(sub_queries)} sub-queries, "
            f"strategy={plan.search_strategy}"
        )

        return state


# =============================================================================
# Standalone function
# =============================================================================

def plan_research(
    query: str,
    query_type: str = "exploratory",
    complexity: str = "moderate",
    region: str = "GLOBAL"
) -> ResearchPlan:
    """
    Standalone function to create research plan.

    Args:
        query: Research question
        query_type: Type of query
        complexity: Complexity level
        region: Geographic scope

    Returns:
        ResearchPlan with sub-queries
    """
    from src.orchestration.state import create_initial_state

    state = create_initial_state(
        vector_id="standalone",
        query=query,
        application="unknown",
        region=region,
        stage=1
    )
    state["query_type"] = query_type
    state["complexity"] = complexity

    agent = PlannerAgent()
    result_state = agent.invoke(state)

    return ResearchPlan(
        sub_queries=[
            SubQueryPlan(
                query_text=sq.query_text,
                expected_data_type=sq.expected_data_type,
                priority=sq.priority,
                search_keywords=sq.search_keywords,
                domain_hints=sq.domain_hints
            )
            for sq in result_state["sub_queries"]
        ],
        search_strategy=result_state["search_strategy"],
        key_entities=result_state["research_plan"]["key_entities"],
        potential_sources=result_state["research_plan"]["potential_sources"],
        reasoning=result_state["research_plan"]["reasoning"]
    )
