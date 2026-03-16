"""
POLARIS v3 Supervisor Agent

Coordinates the multi-agent workflow:
- Decides which agent to invoke next
- Monitors overall progress
- Handles iteration decisions
- Manages state transitions

This agent acts as the "brain" of the ReAct loop.
"""

import logging
from typing import Literal, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState


logger = logging.getLogger(__name__)


# =============================================================================
# Output Schemas
# =============================================================================

class NextAction(BaseModel):
    """Decision about next action in the workflow."""
    # SPRINT 1 FIX: Removed "verifier" - verification now happens post-synthesis via auditor
    next_agent: Literal[
        "search",       # Execute searches for sub-queries
        "analyst",      # Analyze and extract from search results
        "synthesizer",  # Generate report sections
        "critic",       # Evaluate quality and find gaps
        "planner",      # Re-plan based on gaps (iteration)
        "finalize",     # Finalize and package report
        "halt"          # Stop due to error or max iterations
    ] = Field(description="Which agent to invoke next")

    reasoning: str = Field(description="Why this agent should be next")

    priority_tasks: List[str] = Field(
        default_factory=list,
        description="Specific tasks for the next agent"
    )

    should_iterate: bool = Field(
        default=False,
        description="Whether another research iteration is needed"
    )


class ProgressAssessment(BaseModel):
    """Assessment of current research progress."""
    evidence_sufficiency: Literal["insufficient", "partial", "sufficient"] = Field(
        description="How sufficient is the current evidence"
    )

    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    claim_coverage: float = Field(
        description="Proportion of query aspects covered (0.0-1.0)"
    )

    quality_assessment: Literal["low", "medium", "high"] = Field(
        description="Overall quality of current state"
    )

    blockers: List[str] = Field(
        default_factory=list,
        description="Any issues blocking progress"
    )

    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations for improvement"
    )


# =============================================================================
# Supervisor Agent
# =============================================================================

@register_agent("supervisor")
class SupervisorAgent(BaseAgent):
    """
    Supervisor Agent - Orchestrates the research workflow.

    Responsibilities:
    1. Assess current state and progress
    2. Decide which agent to invoke next
    3. Determine if iteration is needed
    4. Handle edge cases and errors
    5. Enforce quality gates

    This is the central coordinator in the multi-agent system.
    """

    def __init__(self):
        config = AgentConfig(
            name="supervisor",
            description="Coordinates multi-agent research workflow",
            task_tier="important",  # Critical workflow coordination
            temperature=0.0,
            max_tokens=1000,
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        return """You are the Research Supervisor coordinating a multi-agent research system. Your job is to decide the next action based on the current state.

WORKFLOW STAGES (SPRINT 2 Architecture):
1. TRIAGE → PLANNER → SEARCH → ANALYST → CRITIC
2. If CRITIC finds gaps → back to PLANNER for iteration
3. When quality sufficient → SYNTHESIZER → (auditor verifies post-synthesis) → FINALIZE

AGENT RESPONSIBILITIES:
- search: Execute web/academic searches based on sub-queries
- analyst: Extract facts, entities, and evidence from search results
- synthesizer: Generate report sections from filtered GOLD/SILVER evidence
- critic: Evaluate quality, identify gaps, assess evidence sufficiency
- planner: Create/revise sub-queries (used in iterations)
- finalize: Package final report with citations

NOTE: Verification happens POST-SYNTHESIS via the auditor node (not pre-synthesis).
The auditor checks generated claims against cited evidence for faithfulness.

DECISION CRITERIA:
1. If no sub_queries exist → need planner
2. If sub_queries pending and no search_results → need search
3. If search_results exist but no evidence_chain → need analyst
4. If evidence_chain exists but not evaluated → need critic
5. If critic finds gaps AND iterations < max → iterate (planner)
6. If quality sufficient OR max iterations → synthesizer then finalize
7. If errors or blockers → halt

ITERATION POLICY:
- Max 5 iterations by default
- Iterate if: faithfulness < 0.7, gaps found, claim_coverage < 0.6
- Don't iterate if: converged, quality high, max iterations reached

Analyze the state carefully and make the optimal routing decision."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Decide next action based on current state.

        Args:
            state: Current research state

        Returns:
            Updated state with routing decision
        """
        # Build state summary for LLM
        state_summary = self._build_state_summary(state)

        # Get routing decision
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"Current State:\n{state_summary}\n\nWhat should be the next action?")
        ]

        decision: NextAction = self.call_llm_structured(messages, NextAction)

        # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
        if decision is None:
            logger.warning("Supervisor LLM returned None (timeout), defaulting to synthesizer")
            state["_next_agent"] = "synthesizer"
            state["_supervisor_reasoning"] = "Supervisor timed out - proceeding to synthesis"
            state["needs_iteration"] = False
            return state

        # Update state with decision
        state["_next_agent"] = decision.next_agent
        state["_supervisor_reasoning"] = decision.reasoning
        state["needs_iteration"] = decision.should_iterate

        # Log decision
        logger.info(
            f"Supervisor: {state.get('vector_id')} -> next={decision.next_agent}, "
            f"iterate={decision.should_iterate}"
        )

        return state

    def _build_state_summary(self, state: ResearchState) -> str:
        """Build a summary of current state for LLM."""
        sub_queries = state.get("sub_queries", [])
        search_results = state.get("search_results", [])
        evidence_chain = state.get("evidence_chain", [])
        verification_results = state.get("verification_results", [])
        gaps = state.get("gaps", [])
        quality_metrics = state.get("quality_metrics", {})

        # Count statuses
        pending_queries = sum(1 for sq in sub_queries if getattr(sq, 'status', 'pending') == 'pending')
        complete_queries = len(sub_queries) - pending_queries

        summary = f"""
Vector ID: {state.get('vector_id', 'unknown')}
Iteration: {state.get('iteration_count', 0)} / {state.get('max_iterations', 5)}
Converged: {state.get('converged', False)}

SUB-QUERIES:
- Total: {len(sub_queries)}
- Pending: {pending_queries}
- Complete: {complete_queries}

SEARCH RESULTS:
- URLs attempted: {state.get('urls_attempted', 0)}
- URLs success: {state.get('urls_success', 0)}
- Total results: {len(search_results)}

EVIDENCE:
- Evidence pieces: {len(evidence_chain)}
- Entities extracted: {len(state.get('entities_extracted', []))}
- Facts extracted: {len(state.get('facts_extracted', []))}

VERIFICATION:
- Claims total: {state.get('claims_total', 0)}
- Claims supported: {state.get('claims_supported', 0)}
- Claims refuted: {state.get('claims_refuted', 0)}
- Hallucination rate: {state.get('hallucination_rate', 0):.2%}

QUALITY METRICS:
- Faithfulness: {quality_metrics.get('faithfulness', 0) if isinstance(quality_metrics, dict) else getattr(quality_metrics, 'faithfulness', 0):.2f}
- Context precision: {quality_metrics.get('context_precision', 0) if isinstance(quality_metrics, dict) else getattr(quality_metrics, 'context_precision', 0):.2f}
- Answer relevancy: {quality_metrics.get('answer_relevancy', 0) if isinstance(quality_metrics, dict) else getattr(quality_metrics, 'answer_relevancy', 0):.2f}

GAPS IDENTIFIED: {len(gaps)}

DRAFT REPORT: {'Yes' if state.get('draft_report') else 'No'}
FINAL REPORT: {'Yes' if state.get('final_report') else 'No'}

ERRORS: {len(state.get('errors', []))}
"""
        return summary

    def assess_progress(self, state: ResearchState) -> ProgressAssessment:
        """
        Assess current research progress.

        Args:
            state: Current research state

        Returns:
            ProgressAssessment with detailed evaluation
        """
        messages = [
            SystemMessage(content="""Assess the research progress based on the current state.
Consider:
- Is there enough evidence to answer the question?
- What proportion of the query aspects are covered?
- What is the overall quality?
- Are there any blockers?"""),
            HumanMessage(content=self._build_state_summary(state))
        ]

        return self.call_llm_structured(messages, ProgressAssessment)


# =============================================================================
# Routing Logic (Pure functions for LangGraph edges)
# =============================================================================

def get_next_agent(state: ResearchState) -> str:
    """
    Determine next agent based on state.

    This is a pure function used by LangGraph conditional edges.
    Returns the name of the next node to execute.

    SPRINT 2: Removed verifier from routing - verification now happens
    post-synthesis via the auditor node in the graph.
    """
    # Check for explicit routing from supervisor
    if "_next_agent" in state:
        return state["_next_agent"]

    # Fallback logic if supervisor hasn't run
    sub_queries = state.get("sub_queries", [])
    search_results = state.get("search_results", [])
    evidence_chain = state.get("evidence_chain", [])
    draft_report = state.get("draft_report", "")
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 5)

    # Decision tree (SPRINT 2: verifier removed, auditor handles post-synthesis)
    if not sub_queries:
        return "planner"

    if not search_results:
        return "search"

    if not evidence_chain:
        return "analyst"

    # Skip verifier - go directly to critic for quality assessment
    if not state.get("_critic_evaluated", False):
        return "critic"

    # Check if iteration needed
    if state.get("needs_iteration", False) and iteration_count < max_iterations:
        return "planner"

    if not draft_report:
        return "synthesizer"

    return "finalize"


def should_continue(state: ResearchState) -> bool:
    """Check if workflow should continue or halt."""
    # Halt conditions
    if state.get("converged", False):
        return False

    if state.get("final_report"):
        return False

    if len(state.get("errors", [])) > 3:
        return False

    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 5)
    if iteration_count >= max_iterations and state.get("draft_report"):
        return False

    return True
