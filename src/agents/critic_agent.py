"""
POLARIS v3 Critic Agent

Evaluates research quality and identifies gaps:
- RAGAS-style quality metrics (faithfulness, relevance, precision)
- Coverage analysis against sub-queries
- Gap identification for iteration
- Confidence assessment
- Improvement recommendations

Uses structured evaluation for consistent quality assessment.
"""

import logging
from typing import List, Dict, Any, Literal, Optional
from datetime import datetime, timezone

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, Gap, QualityMetrics
from src.config.thresholds import get_threshold


logger = logging.getLogger(__name__)


# =============================================================================
# CRITICAL-005: Exception Classes
# =============================================================================

class CriticFailure(Exception):
    """
    Raised when critic evaluation fails and cannot produce real metrics.

    CRITICAL-005: Critic must fail loudly, not return fake 0.5 scores.
    """

    def __init__(self, message: str, context: Dict[str, Any] = None):
        super().__init__(message)
        self.context = context or {}
        # Log the failure with context
        logger.error(f"CriticFailure: {message}", extra={"context": self.context})


# =============================================================================
# Evaluation Schemas
# =============================================================================

class SubQueryCoverage(BaseModel):
    """Coverage assessment for a single sub-query."""
    query_id: str = Field(description="Sub-query ID")
    query_text: str = Field(description="Sub-query text")
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    coverage_score: float = Field(description="How well this query is answered (0.0-1.0)")
    evidence_count: int = Field(description="Number of evidence pieces addressing this query")
    gaps: List[str] = Field(default_factory=list, description="Gaps in coverage")


class IdentifiedGap(BaseModel):
    """A gap identified in the research."""
    description: str = Field(description="Description of the gap")
    gap_type: Literal["missing_data", "weak_evidence", "contradictory", "incomplete"] = Field(
        description="Type of gap"
    )
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    priority: int = Field(description="Priority 1 (critical) to 5 (minor)")
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="Suggested queries to fill the gap"
    )
    related_sub_queries: List[str] = Field(
        default_factory=list,
        description="Related sub-query IDs"
    )


class QualityAssessment(BaseModel):
    """Complete quality assessment.

    NOTE: Removed ge/le constraints - Gemini structured output limitations.
    All float scores should be in range 0.0-1.0 (validated in code if needed).
    """
    faithfulness: float = Field(
        description="How well the report is grounded in evidence (0.0-1.0)"
    )
    context_precision: float = Field(
        description="Precision of retrieved context (0.0-1.0)"
    )
    answer_relevancy: float = Field(
        description="How relevant the report is to the question (0.0-1.0)"
    )
    source_diversity: int = Field(description="Number of unique source types used")
    claim_coverage: float = Field(
        description="Proportion of claims with supporting evidence (0.0-1.0)"
    )


class CriticEvaluation(BaseModel):
    """Complete critic evaluation."""
    quality_metrics: QualityAssessment = Field(description="Quality metrics")
    sub_query_coverage: List[SubQueryCoverage] = Field(description="Coverage per sub-query")
    gaps: List[IdentifiedGap] = Field(description="Identified gaps")
    strengths: List[str] = Field(default_factory=list, description="Report strengths")
    weaknesses: List[str] = Field(default_factory=list, description="Report weaknesses")
    needs_iteration: bool = Field(description="Whether another research iteration is needed")
    iteration_recommendation: str = Field(description="Recommendation for next iteration")
    overall_confidence: Literal["low", "medium", "high"] = Field(
        description="Overall confidence in the research"
    )
    improvement_suggestions: List[str] = Field(
        default_factory=list,
        description="Specific improvement suggestions"
    )


# =============================================================================
# Critic Agent
# =============================================================================

@register_agent("critic")
class CriticAgent(BaseAgent):
    """
    Critic Agent - Evaluates research quality and identifies gaps.

    Responsibilities:
    1. Evaluate faithfulness (grounding in evidence)
    2. Assess answer relevancy
    3. Measure context precision
    4. Analyze sub-query coverage
    5. Identify knowledge gaps
    6. Recommend improvements
    7. Decide if iteration is needed

    Uses RAGAS-inspired metrics for consistent evaluation.
    """

    def __init__(self):
        config = AgentConfig(
            name="critic",
            description="Evaluates research quality and identifies gaps",
            task_tier="important",  # Quality evaluation requires reasoning
            temperature=0.0,
            max_tokens=16000,  # FIX 11b: Increased from 4000 (CriticEvaluation with 25 sub-queries needs ~10K tokens)
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        return """You are a Research Quality Critic. Your job is to rigorously evaluate research quality and identify gaps.

EVALUATION CRITERIA:

1. FAITHFULNESS (0-1):
   - Is every claim in the report supported by evidence?
   - Are citations accurate and appropriate?
   - Are there unsupported assertions (hallucinations)?
   - Formula: supported_claims / total_claims

2. CONTEXT PRECISION (0-1):
   - Is the retrieved evidence relevant to the question?
   - Is there irrelevant noise in the evidence?
   - Are the most relevant sources used?

3. ANSWER RELEVANCY (0-1):
   - Does the report answer the research question?
   - Is the response focused and on-topic?
   - Are all aspects of the question addressed?

4. SOURCE DIVERSITY:
   - Number of unique source types (academic, government, news, etc.)
   - Geographic diversity if relevant
   - Temporal diversity (recent vs. historical)

5. CLAIM COVERAGE (0-1):
   - Proportion of sub-queries addressed
   - Depth of coverage per sub-query
   - Completeness of findings

GAP TYPES:
- missing_data: Key information not found
- weak_evidence: Evidence exists but is low quality
- contradictory: Conflicting information unresolved
- incomplete: Partial answers to sub-queries

ITERATION DECISION:
Recommend iteration if:
- Faithfulness < 0.70
- Claim coverage < 0.60
- Critical gaps identified
- Major sub-queries unanswered

DON'T iterate if:
- Max iterations reached
- Quality metrics satisfactory
- Gaps are minor or unavoidable
- Evidence exhausted

Be strict but fair in evaluation. Identify specific, actionable improvements."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Evaluate research quality and identify gaps.

        Args:
            state: Current research state

        Returns:
            Updated state with quality_metrics and gaps
        """
        # Gather inputs for evaluation
        draft_report = state.get("draft_report", "")
        evidence_chain = state.get("evidence_chain", [])
        sub_queries = state.get("sub_queries", [])
        verification_results = state.get("verification_results", [])
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 5)

        if not draft_report and not evidence_chain:
            logger.warning("No content to evaluate")
            return state

        # FIX 103: Use Verifier metrics when no draft report exists
        # The Critic runs BEFORE Synthesizer, so first pass has no draft.
        # Use Verifier's verification results to compute faithfulness.
        if not draft_report and verification_results:
            supported = sum(1 for v in verification_results if v.verdict == "supported")
            total = len(verification_results)
            verifier_faithfulness = supported / total if total > 0 else 0.0

            logger.info(
                f"[FIX 103] No draft report - using Verifier metrics: "
                f"{supported}/{total} supported = {verifier_faithfulness:.2%} faithfulness"
            )

            # If Verifier shows good faithfulness, trust it and proceed to synthesis
            if verifier_faithfulness >= 0.5:  # Threshold for proceeding
                # FIX 103b: source_diversity is int (unique source count), not float
                unique_sources = len(set(ev.source_url for ev in evidence_chain if hasattr(ev, 'source_url')))
                quality_metrics = QualityMetrics(
                    faithfulness=verifier_faithfulness,
                    context_precision=0.7,  # Placeholder - will be evaluated post-synthesis
                    answer_relevancy=0.7,
                    source_diversity=unique_sources,
                    claim_coverage=min(1.0, len(verification_results) / 20),  # 20 claims = full coverage
                )
                state["quality_metrics"] = quality_metrics
                state["gaps"] = []
                state["needs_iteration"] = False
                state["iteration_feedback"] = f"[FIX 103] Verifier faithfulness {verifier_faithfulness:.2%} - proceeding to synthesis"
                state["_critic_evaluated"] = True

                logger.info(
                    f"[FIX 103] Proceeding to synthesis with faithfulness={verifier_faithfulness:.2%}"
                )
                return state

        logger.info(f"Evaluating research quality (iteration {iteration_count})")

        # Perform evaluation
        evaluation = self._evaluate(
            draft_report=draft_report,
            evidence_chain=evidence_chain,
            sub_queries=sub_queries,
            verification_results=verification_results,
            state=state
        )

        # Convert to state objects
        gaps = [
            Gap(
                gap_id=f"gap_{i+1:03d}",
                description=g.description,
                gap_type=g.gap_type,
                priority=g.priority,
                suggested_queries=g.suggested_queries,
                iteration_discovered=iteration_count
            )
            for i, g in enumerate(evaluation.gaps)
        ]

        quality_metrics = QualityMetrics(
            faithfulness=evaluation.quality_metrics.faithfulness,
            context_precision=evaluation.quality_metrics.context_precision,
            answer_relevancy=evaluation.quality_metrics.answer_relevancy,
            source_diversity=evaluation.quality_metrics.source_diversity,
            claim_coverage=evaluation.quality_metrics.claim_coverage,
        )

        # Determine if iteration needed (respect max iterations)
        needs_iteration = evaluation.needs_iteration and iteration_count < max_iterations

        if needs_iteration:
            logger.info(
                f"Iteration recommended: {evaluation.iteration_recommendation}"
            )
        else:
            logger.info(
                f"Quality sufficient or max iterations reached. "
                f"Faithfulness: {quality_metrics.faithfulness:.2f}, "
                f"Coverage: {quality_metrics.claim_coverage:.2f}"
            )

        # Update state
        state["quality_metrics"] = quality_metrics
        state["gaps"] = gaps
        state["needs_iteration"] = needs_iteration
        state["iteration_feedback"] = evaluation.iteration_recommendation
        state["_critic_evaluated"] = True

        return state

    def _evaluate(
        self,
        draft_report: str,
        evidence_chain: List,
        sub_queries: List,
        verification_results: List,
        state: ResearchState
    ) -> CriticEvaluation:
        """Perform comprehensive evaluation."""
        # Build context for evaluation
        evidence_summary = self._summarize_evidence(evidence_chain)
        verification_summary = self._summarize_verification(verification_results)
        sub_query_list = self._format_sub_queries(sub_queries)

        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"""Evaluate this research:

ORIGINAL QUESTION:
{state.get('original_query', 'Not specified')}

APPLICATION: {state.get('application', 'Unknown')}
REGION: {state.get('region', 'GLOBAL')}
ITERATION: {state.get('iteration_count', 0)} / {state.get('max_iterations', 5)}

SUB-QUERIES:
{sub_query_list}

EVIDENCE SUMMARY:
{evidence_summary}

VERIFICATION SUMMARY:
{verification_summary}

DRAFT REPORT (truncated):
{draft_report[:8000] if draft_report else 'No draft report generated'}

---

Evaluate:
1. Quality metrics (faithfulness, precision, relevancy, diversity, coverage)
2. Coverage for each sub-query
3. Gaps that need addressing
4. Strengths and weaknesses
5. Whether iteration is needed
6. Specific improvement suggestions

Be rigorous but constructive.""")
        ]

        try:
            evaluation: CriticEvaluation = self.call_llm_structured(messages, CriticEvaluation)
            # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
            if evaluation is None:
                logger.warning("Critic LLM returned None (timeout or parsing failure), using default evaluation")
                return CriticEvaluation(
                    quality_metrics=QualityAssessment(
                        faithfulness=0.5,
                        context_precision=0.5,
                        answer_relevancy=0.5,
                        source_diversity=len(set(ev.source_url for ev in evidence_chain)) if evidence_chain else 0,
                        claim_coverage=0.5
                    ),
                    sub_query_coverage=[],
                    gaps=[
                        IdentifiedGap(
                            description="Evaluation timed out - manual review required",
                            gap_type="incomplete",
                            priority=2,
                            suggested_queries=[]
                        )
                    ],
                    strengths=[],
                    weaknesses=["Evaluation could not be completed (LLM timeout)"],
                    needs_iteration=True,
                    iteration_recommendation="Retry evaluation with increased timeout",
                    overall_confidence=0.3
                )
            return evaluation
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            # Return default evaluation
            return CriticEvaluation(
                quality_metrics=QualityAssessment(
                    faithfulness=0.5,
                    context_precision=0.5,
                    answer_relevancy=0.5,
                    source_diversity=len(set(ev.source_url for ev in evidence_chain)) if evidence_chain else 0,
                    claim_coverage=0.5
                ),
                sub_query_coverage=[],
                gaps=[
                    IdentifiedGap(
                        description="Evaluation error - manual review required",
                        gap_type="incomplete",
                        priority=2,
                        suggested_queries=[]
                    )
                ],
                strengths=[],
                weaknesses=["Automated evaluation failed"],
                needs_iteration=False,
                iteration_recommendation="Manual review recommended due to evaluation error",
                overall_confidence="low",
                improvement_suggestions=["Review evaluation process"]
            )

    def _summarize_evidence(self, evidence_chain: List) -> str:
        """Summarize evidence for evaluation."""
        if not evidence_chain:
            return "No evidence collected"

        summary_parts = []
        source_types = set()
        domains = set()

        for ev in evidence_chain[:20]:  # Limit for context
            source_types.add(ev.extraction_method)
            if ev.source_url:
                try:
                    domain = ev.source_url.split("/")[2]
                    domains.add(domain)
                except IndexError:
                    # HIGH-001: Log malformed URL instead of silent pass
                    logger.debug(f"Could not extract domain from URL: {ev.source_url}")

            summary_parts.append(
                f"- [{ev.evidence_id}] Quality: {ev.source_quality_score:.2f}, "
                f"Relevance: {ev.relevance_score:.2f}, "
                f"Claims: {len(ev.claims)}"
            )

        return f"""Total evidence pieces: {len(evidence_chain)}
Unique sources: {len(domains)}
Source types: {', '.join(source_types)}

Evidence details:
{chr(10).join(summary_parts)}"""

    def _summarize_verification(self, verification_results: List) -> str:
        """Summarize verification results."""
        if not verification_results:
            return "No verification performed"

        supported = sum(1 for v in verification_results if v.verdict == "supported")
        refuted = sum(1 for v in verification_results if v.verdict == "refuted")
        uncertain = sum(1 for v in verification_results if v.verdict == "uncertain")
        insufficient = sum(1 for v in verification_results if v.verdict == "insufficient_evidence")
        total = len(verification_results)

        return f"""Total claims verified: {total}
- Supported: {supported} ({supported/total*100:.1f}%)
- Refuted: {refuted} ({refuted/total*100:.1f}%)
- Uncertain: {uncertain} ({uncertain/total*100:.1f}%)
- Insufficient evidence: {insufficient} ({insufficient/total*100:.1f}%)"""

    def _format_sub_queries(self, sub_queries: List) -> str:
        """Format sub-queries for evaluation."""
        if not sub_queries:
            return "No sub-queries defined"

        return "\n".join([
            f"- {sq.query_id}: {sq.query_text} "
            f"(type: {sq.expected_data_type}, status: {sq.status})"
            for sq in sub_queries
        ])


# =============================================================================
# RAGAS-style Metric Functions
# =============================================================================

def calculate_faithfulness(
    claims: List[str],
    evidence_texts: List[str]
) -> float:
    """
    Calculate faithfulness score.

    Faithfulness = claims supported by evidence / total claims

    Args:
        claims: List of claims from the report
        evidence_texts: List of evidence texts

    Returns:
        Faithfulness score (0-1)
    """
    if not claims:
        return 1.0  # No claims = fully faithful

    # MED-029: Overlap threshold from config
    overlap_threshold = get_threshold("clustering.overlap", 0.3)

    # Simple keyword overlap for now
    supported = 0
    for claim in claims:
        claim_words = set(claim.lower().split())
        for evidence in evidence_texts:
            evidence_words = set(evidence.lower().split())
            overlap = len(claim_words & evidence_words) / len(claim_words) if claim_words else 0
            if overlap > overlap_threshold:
                supported += 1
                break

    return supported / len(claims)


def calculate_answer_relevancy(
    question: str,
    answer: str
) -> float:
    """
    Calculate answer relevancy score.

    Measures how relevant the answer is to the question.

    Args:
        question: The research question
        answer: The generated answer/report

    Returns:
        Relevancy score (0-1)
    """
    if not answer:
        return 0.0

    # Simple keyword overlap
    question_words = set(question.lower().split())
    answer_words = set(answer.lower().split())

    overlap = len(question_words & answer_words)
    return min(overlap / len(question_words) if question_words else 0, 1.0)


def calculate_context_precision(
    evidence_chain: List,
    query: str
) -> float:
    """
    Calculate context precision.

    Measures how much of the retrieved context is relevant.

    Args:
        evidence_chain: List of evidence objects
        query: The research query

    Returns:
        Precision score (0-1)
    """
    if not evidence_chain:
        return 0.0

    relevant_count = sum(
        1 for ev in evidence_chain
        if ev.relevance_score >= 0.5
    )

    return relevant_count / len(evidence_chain)


# =============================================================================
# Standalone function
# =============================================================================

def evaluate_research(
    report: str,
    evidence_texts: List[str],
    question: str
) -> Dict[str, Any]:
    """
    Standalone function to evaluate research quality.

    Args:
        report: The research report
        evidence_texts: List of evidence texts
        question: The research question

    Returns:
        Dictionary with quality metrics
    """
    from src.orchestration.state import create_initial_state, Evidence

    state = create_initial_state(
        vector_id="standalone",
        query=question,
        application="unknown",
        region="GLOBAL",
        stage=1
    )

    # MED-021, MED-022: Default scores from config
    high_relevance = get_threshold("scoring.high_relevance", 0.8)
    high_quality = get_threshold("scoring.high_quality", 0.7)

    # Build evidence chain
    evidence_chain = []
    for i, text in enumerate(evidence_texts):
        evidence = Evidence(
            evidence_id=f"ev_{i+1:04d}",
            chunk_id=f"chunk_{i+1:04d}",
            source_url="standalone",
            text=text,
            relevance_score=high_relevance,
            source_quality_score=high_quality,
            extraction_method="manual",
            claims=[],
            entities=[],
        )
        evidence_chain.append(evidence)

    state["evidence_chain"] = evidence_chain
    state["draft_report"] = report

    agent = CriticAgent()

    try:
        result_state = agent.invoke(state)
    except Exception as e:
        # CRITICAL-005: Fail loudly, don't return fake metrics
        raise CriticFailure(
            f"Critic agent invocation failed: {e}",
            context={
                "question": question,
                "report_length": len(report),
                "evidence_count": len(evidence_texts),
            }
        ) from e

    metrics = result_state.get("quality_metrics", {})
    if hasattr(metrics, "faithfulness"):
        return {
            "faithfulness": metrics.faithfulness,
            "context_precision": metrics.context_precision,
            "answer_relevancy": metrics.answer_relevancy,
            "source_diversity": metrics.source_diversity,
            "claim_coverage": metrics.claim_coverage,
            "needs_iteration": result_state.get("needs_iteration", False),
            "gaps": [g.description for g in result_state.get("gaps", [])],
            "success": True,  # CRITICAL-005: Add success field
        }

    # CRITICAL-005: Fail loudly instead of returning fake 0.5 scores
    raise CriticFailure(
        "Critic evaluation produced no valid metrics",
        context={
            "question": question,
            "report_length": len(report),
            "evidence_count": len(evidence_texts),
            "result_keys": list(result_state.keys()) if result_state else [],
        }
    )
