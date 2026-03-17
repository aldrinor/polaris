"""Phase 1: SCOPE — Query decomposition, perspective discovery, query generation.

Decomposes a research query into 6-10 sub-questions, discovers diverse
perspectives, and generates targeted search queries per sub-question.

This runs BEFORE any search — questions drive evidence collection.

Failure modes handled:
- F1.1: LLM returns 0 sub-questions → fallback to template queries
- F1.2: Degenerate decomposition → diversity gate detects + regenerates
- F1.3: Vague query → complexity classifier reduces depth
- F1.4: Factual question → simple classification, low depth
- F1.5: Unparseable JSON → retry + fallback
"""

import asyncio
import logging
import os
from typing import Optional

from src.polaris_graph.contracts_v3 import (
    ScopeOutput,
    SearchQuery,
    SubQuestion,
)

logger = logging.getLogger("polaris_graph")

# Maximum LLM attempts before fallback (F1.1, F1.5)
_MAX_SCOPE_RETRIES = 2

# Diversity gate threshold — cosine similarity above this = too similar (F1.2)
_DIVERSITY_SIMILARITY_THRESHOLD = float(
    os.getenv("PG_V3_SCOPE_DIVERSITY_THRESHOLD", "0.85")
)

# Minimum distinct analytical focuses required (F1.2)
_MIN_DISTINCT_FOCUSES = 3


# ---------------------------------------------------------------------------
# Decomposition system prompt
# ---------------------------------------------------------------------------

_SCOPE_SYSTEM_PROMPT = """You are a research strategist. Given a research topic, decompose it into 6-10 sub-questions that a knowledgeable reader would want answered.

Requirements:
- Questions should flow logically: context → mechanisms → effectiveness → comparison → limitations → future
- Each question must target a DIFFERENT aspect of the topic — no paraphrasing
- Assign each question an analytical_focus from: aggregate, compare, explain, tabulate, challenge
- Assign depth: 'deep' for core questions (2-3), 'moderate' for supporting (3-4), 'brief' for peripheral (1-2)
- The set of questions should cover: what, how, how well, compared to what, and what's missing
- At least 3 different analytical_focus values must be represented
- Generate a narrative_flow description explaining how questions build on each other

Also provide:
- 5-8 diverse perspectives (e.g., Scientific, Engineering, Economic, Regulatory, Environmental)
- 3-5 search queries per sub-question, each tagged with sub_question_id, perspective, and source_preference (web|academic|both)
- A complexity classification: 'simple' (factual/narrow), 'moderate' (multi-faceted), 'complex' (broad/deep)
- An estimated_depth (target evidence count): simple=30-50, moderate=100-200, complex=200-500""".strip()


# ---------------------------------------------------------------------------
# Perspective templates (from STORM, used in fallback)
# ---------------------------------------------------------------------------

_DEFAULT_PERSPECTIVES = [
    "Scientific",
    "Engineering",
    "Environmental",
    "Economic",
    "Regulatory",
    "Public_Health",
    "Industry",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_scope(
    client,
    query: str,
    application: str = "",
    region: str = "",
    research_brief: str = "",
    ltm_priors: Optional[list[str]] = None,
) -> ScopeOutput:
    """Phase 1: Decompose query into sub-questions and search queries.

    Args:
        client: OpenRouterClient (or mock).
        query: The research query.
        application: Domain context (e.g., "water_treatment").
        region: Geographic context (e.g., "global").
        research_brief: Optional domain context from Campaign Control Center.
        ltm_priors: Optional list of prior findings from LTM memory.

    Returns:
        ScopeOutput with sub-questions, perspectives, and search queries.
        Always returns a valid ScopeOutput — falls back to templates on failure.
    """
    # Build the decomposition prompt
    context_parts = [f"Research topic: {query}"]
    if application:
        context_parts.append(f"Application domain: {application}")
    if region:
        context_parts.append(f"Geographic scope: {region}")
    if research_brief:
        context_parts.append(f"Research brief: {research_brief[:500]}")
    if ltm_priors:
        prior_text = "\n".join(f"- {p}" for p in ltm_priors[:5])
        context_parts.append(f"Prior findings from previous research:\n{prior_text}")

    prompt = "\n".join(context_parts)

    # Attempt LLM decomposition with retries (F1.1, F1.5)
    scope_output = None
    for attempt in range(_MAX_SCOPE_RETRIES):
        try:
            scope_output = await client.generate_structured(
                prompt=prompt,
                schema=ScopeOutput,
                system=_SCOPE_SYSTEM_PROMPT,
                max_tokens=int(os.getenv("PG_V3_SCOPE_MAX_TOKENS", "8192")),
                timeout=int(os.getenv("PG_V3_SCOPE_TIMEOUT", "120")),
            )
            if scope_output and len(scope_output.sub_questions) >= 3:
                break
            logger.warning(
                "[v3 scope] Attempt %d: got %d sub-questions (need >= 3), retrying",
                attempt + 1,
                len(scope_output.sub_questions) if scope_output else 0,
            )
            scope_output = None
        except Exception as exc:
            logger.warning(
                "[v3 scope] Attempt %d failed: %s",
                attempt + 1,
                str(exc)[:200],
            )
            scope_output = None

    # F1.2: Check diversity if LLM succeeded
    if scope_output is not None:
        is_diverse = await _check_question_diversity(scope_output.sub_questions)
        if not is_diverse:
            logger.warning(
                "[v3 scope] Sub-questions failed diversity gate, regenerating with diversity instruction"
            )
            # One more attempt with explicit diversity instruction
            try:
                scope_output = await client.generate_structured(
                    prompt=prompt + "\n\nCRITICAL: Each sub-question MUST address a DIFFERENT aspect. "
                    "Do NOT paraphrase the same question. Cover: mechanisms, conditions, "
                    "effectiveness, comparison, limitations, economics.",
                    schema=ScopeOutput,
                    system=_SCOPE_SYSTEM_PROMPT,
                    max_tokens=int(os.getenv("PG_V3_SCOPE_MAX_TOKENS", "8192")),
                    timeout=int(os.getenv("PG_V3_SCOPE_TIMEOUT", "120")),
                )
                if not scope_output or len(scope_output.sub_questions) < 3:
                    scope_output = None
            except Exception:
                scope_output = None

    # Fallback: template-based decomposition (F1.1, F1.5)
    if scope_output is None:
        logger.warning("[v3 scope] All LLM attempts failed, using template fallback")
        scope_output = _fallback_scope(query, application, region)

    logger.info(
        "[v3 scope] Decomposed '%s' into %d sub-questions, %d perspectives, %d queries (complexity=%s)",
        query[:60],
        len(scope_output.sub_questions),
        len(scope_output.perspectives),
        len(scope_output.search_queries),
        scope_output.complexity,
    )

    return scope_output


# ---------------------------------------------------------------------------
# Diversity gate (F1.2)
# ---------------------------------------------------------------------------

async def _check_question_diversity(
    questions: list[SubQuestion],
) -> bool:
    """Check that sub-questions are genuinely diverse, not paraphrases.

    Uses two signals:
    1. Analytical focus variety (must have >= 3 distinct focuses)
    2. Word overlap (Jaccard similarity — cheap, no embedding needed)

    Returns True if questions are sufficiently diverse.
    """
    if len(questions) < 3:
        return False

    # Signal 1: Analytical focus variety
    focuses = {q.analytical_focus for q in questions}
    if len(focuses) < _MIN_DISTINCT_FOCUSES:
        logger.debug(
            "[v3 scope] Diversity fail: only %d distinct focuses (%s)",
            len(focuses), focuses,
        )
        return False

    # Signal 2: Jaccard word overlap between all pairs
    # If >50% of pairs have Jaccard > 0.6, questions are too similar
    high_overlap_count = 0
    total_pairs = 0

    for i in range(len(questions)):
        words_i = set(questions[i].question.lower().split())
        for j in range(i + 1, len(questions)):
            words_j = set(questions[j].question.lower().split())
            intersection = words_i & words_j
            union = words_i | words_j
            jaccard = len(intersection) / max(len(union), 1)
            total_pairs += 1
            if jaccard > 0.6:
                high_overlap_count += 1

    if total_pairs > 0 and high_overlap_count / total_pairs > 0.5:
        logger.debug(
            "[v3 scope] Diversity fail: %d/%d pairs have Jaccard > 0.6",
            high_overlap_count, total_pairs,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# Template fallback (F1.1, F1.5)
# ---------------------------------------------------------------------------

def _fallback_scope(
    query: str,
    application: str = "",
    region: str = "",
) -> ScopeOutput:
    """Generate a template-based ScopeOutput when LLM fails.

    Produces 6 standard sub-questions covering the canonical research
    structure: what, how, how well, compared to what, limitations, future.
    """
    topic = query.strip()
    app_suffix = f" in {application}" if application else ""
    region_suffix = f" ({region})" if region else ""

    sub_questions = [
        SubQuestion(
            id="sq_01",
            question=f"What are the fundamental mechanisms of {topic}{app_suffix}?",
            analytical_focus="explain",
            expected_depth="deep",
        ),
        SubQuestion(
            id="sq_02",
            question=f"What conditions and parameters affect the performance of {topic}?",
            analytical_focus="compare",
            expected_depth="deep",
        ),
        SubQuestion(
            id="sq_03",
            question=f"What quantitative effectiveness has been reported for {topic}{region_suffix}?",
            analytical_focus="aggregate",
            expected_depth="deep",
        ),
        SubQuestion(
            id="sq_04",
            question=f"How does {topic} compare to alternative approaches?",
            analytical_focus="tabulate",
            expected_depth="moderate",
        ),
        SubQuestion(
            id="sq_05",
            question=f"What are the known limitations and knowledge gaps in {topic}?",
            analytical_focus="challenge",
            expected_depth="moderate",
        ),
        SubQuestion(
            id="sq_06",
            question=f"What are the cost-effectiveness and practical considerations for {topic}?",
            analytical_focus="compare",
            expected_depth="brief",
        ),
    ]

    perspectives = _DEFAULT_PERSPECTIVES[:5]

    # Generate search queries using the existing fallback function
    try:
        from src.polaris_graph.agents.planner import _fallback_queries
        raw_queries = _fallback_queries(query, application, region)
    except Exception:
        # Absolute last resort: simple template queries
        raw_queries = [
            f"{topic} mechanisms",
            f"{topic} effectiveness results",
            f"{topic} comparison alternatives",
            f"{topic} limitations challenges",
            f"{topic} cost analysis",
            f"{topic} recent research 2024 2025",
        ]

    # Distribute queries across sub-questions
    search_queries = []
    for i, raw_q in enumerate(raw_queries[:18]):  # Cap at 3 per sub-question
        sq_idx = i % len(sub_questions)
        sq_id = sub_questions[sq_idx].id
        perspective = perspectives[i % len(perspectives)]
        search_queries.append(SearchQuery(
            query=raw_q,
            sub_question_id=sq_id,
            perspective=perspective,
            source_preference="both" if i % 3 != 2 else "academic",
        ))

    return ScopeOutput(
        sub_questions=sub_questions,
        perspectives=perspectives,
        search_queries=search_queries,
        complexity="moderate",
        estimated_depth=200,
    )
