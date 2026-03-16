"""
POLARIS v3 Triage Agent

Classifies incoming research queries by:
- Query type (factual, statistical, comparative, etc.)
- Complexity (simple, moderate, complex)
- Estimated sources needed

Uses a lightweight model (GPT-4o-mini) for fast classification.
"""

import logging
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState


logger = logging.getLogger(__name__)


# =============================================================================
# Output Schema
# =============================================================================

class TriageOutput(BaseModel):
    """Structured output from Triage agent."""
    query_type: Literal[
        "factual",      # Single facts, definitions
        "statistical",  # Numbers, rates, percentages
        "comparative",  # A vs B analysis
        "procedural",   # How-to, process questions
        "exploratory",  # Open-ended research
        "regulatory",   # Compliance, regulations
        "market"        # Market size, trends
    ] = Field(description="The type of research question")

    complexity: Literal["simple", "moderate", "complex"] = Field(
        description="How complex is this research task"
    )

    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    # Expected range: 5-100 (validated in code if needed)
    estimated_sources_needed: int = Field(
        description="Estimated number of sources needed (5-100 typical range)"
    )

    reasoning: str = Field(
        description="Brief explanation of classification reasoning"
    )


# =============================================================================
# Triage Agent
# =============================================================================

@register_agent("triage")
class TriageAgent(BaseAgent):
    """
    Triage Agent - First agent in the pipeline.

    Responsibilities:
    1. Classify the query type
    2. Assess complexity
    3. Estimate sources needed
    4. Route to appropriate workflow

    Uses GPT-4o-mini for fast, cost-effective classification.
    """

    def __init__(self):
        config = AgentConfig(
            name="triage",
            description="Classifies research queries by type and complexity",
            task_tier="simple",  # Fast classification task
            temperature=0.0,
            max_tokens=500,
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        return """You are a Research Query Triage Specialist. Your job is to analyze incoming research questions and classify them.

QUERY TYPES:
- factual: Questions seeking specific facts, definitions, or descriptions
- statistical: Questions seeking numbers, rates, percentages, or quantitative data
- comparative: Questions comparing two or more items, technologies, or approaches
- procedural: Questions about how something works, processes, or methodologies
- exploratory: Open-ended questions requiring broad investigation
- regulatory: Questions about regulations, compliance, standards, or legal requirements
- market: Questions about market size, trends, growth, or business analysis

COMPLEXITY LEVELS:
- simple: Can be answered with 5-10 high-quality sources, straightforward question
- moderate: Requires 15-30 sources, some nuance or multiple perspectives needed
- complex: Requires 40+ sources, multi-faceted question with many aspects to cover

SOURCE ESTIMATION:
- Consider the breadth of the topic
- Account for need for diverse perspectives
- Factor in geographic scope (regional vs global)
- Consider need for academic vs industry vs government sources

Analyze the query carefully and provide your classification."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Classify the research query.

        Args:
            state: Current research state with original_query

        Returns:
            Updated state with query_type, complexity, estimated_sources_needed
        """
        query = state.get("original_query", "")
        vector_id = state.get("vector_id", "")
        stage = state.get("stage", 1)
        region = state.get("region", "GLOBAL")

        if not query:
            raise ValueError("No query provided in state")

        # Build context for classification
        context = f"""
Vector ID: {vector_id}
Stage: {stage}
Region: {region}

Research Question:
{query}
"""

        # Call LLM with structured output
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=context)
        ]

        result: TriageOutput = self.call_llm_structured(messages, TriageOutput)

        # Update state with classification
        state["query_type"] = result.query_type
        state["complexity"] = result.complexity
        state["estimated_sources_needed"] = result.estimated_sources_needed

        logger.info(
            f"Triage: {vector_id} -> type={result.query_type}, "
            f"complexity={result.complexity}, sources={result.estimated_sources_needed}"
        )

        return state


# =============================================================================
# Standalone function for use without agent framework
# =============================================================================

def triage_query(query: str, vector_id: str = "", stage: int = 1, region: str = "GLOBAL") -> TriageOutput:
    """
    Standalone function to triage a query without full agent framework.

    Args:
        query: Research question
        vector_id: Optional vector ID
        stage: Research stage (1-13)
        region: Geographic scope

    Returns:
        TriageOutput with classification
    """
    from src.orchestration.state import create_initial_state

    # Create minimal state
    state = create_initial_state(
        vector_id=vector_id or "standalone",
        query=query,
        application="unknown",
        region=region,
        stage=stage
    )

    # Run triage
    agent = TriageAgent()
    result_state = agent.invoke(state)

    return TriageOutput(
        query_type=result_state["query_type"],
        complexity=result_state["complexity"],
        estimated_sources_needed=result_state["estimated_sources_needed"],
        reasoning="Classified via TriageAgent"
    )
