"""
POLARIS v3 Clarification Agent
==============================
Pre-research clarification agent that validates user intent BEFORE
expensive research operations begin.

This agent:
1. Analyzes queries for ambiguity, missing context, or vague terms
2. Generates targeted clarifying questions when needed
3. Rewrites queries to be more specific and actionable
4. Tracks clarification history for multi-turn interactions

Key Features:
- Smart ambiguity detection (technical jargon, vague scope, missing context)
- Question prioritization (most critical clarifications first)
- Query rewriting with specificity enhancement
- Automatic bypass for clear, well-formed queries

Usage:
    from src.agents.clarification_agent import ClarificationAgent

    agent = ClarificationAgent()
    result = agent.run(state)

    if result.needs_clarification:
        # Ask user for clarification
        print(result.clarifying_questions)
    else:
        # Proceed with research using rewritten query
        proceed_with(result.rewritten_query)
"""

import logging
from typing import List, Literal, Optional
from enum import Enum

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState
from src.config.thresholds import get_threshold

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class AmbiguityType(str, Enum):
    """Types of ambiguity detected in queries."""
    SCOPE = "scope"  # Too broad or undefined scope
    CONTEXT = "context"  # Missing contextual information
    TERMINOLOGY = "terminology"  # Ambiguous technical terms
    INTENT = "intent"  # Unclear research goal
    GEOGRAPHIC = "geographic"  # Missing geographic scope
    TEMPORAL = "temporal"  # Missing time frame
    QUANTITATIVE = "quantitative"  # Unclear metrics/quantities
    NONE = "none"  # No ambiguity detected


class ClarificationPriority(str, Enum):
    """Priority levels for clarifying questions."""
    CRITICAL = "critical"  # Must clarify before proceeding
    HIGH = "high"  # Strongly recommended
    MEDIUM = "medium"  # Would improve results
    LOW = "low"  # Nice to have


# =============================================================================
# Output Schemas
# =============================================================================

class ClarifyingQuestion(BaseModel):
    """A single clarifying question to ask the user."""
    question: str = Field(description="The clarifying question to ask")
    ambiguity_type: str = Field(description="Type of ambiguity this addresses")
    priority: str = Field(description="Priority: critical, high, medium, or low")
    options: Optional[List[str]] = Field(
        default=None,
        description="Optional list of suggested answers"
    )


class ClarificationOutput(BaseModel):
    """Structured output from the Clarification agent."""

    needs_clarification: bool = Field(
        description="Whether clarification is needed before proceeding"
    )

    clarity_score: float = Field(
        description="Query clarity score from 0.0 (very ambiguous) to 1.0 (crystal clear)"
    )

    ambiguity_types: List[str] = Field(
        description="Types of ambiguity detected in the query"
    )

    clarifying_questions: List[ClarifyingQuestion] = Field(
        default_factory=list,
        description="List of clarifying questions to ask (if needed)"
    )

    rewritten_query: str = Field(
        description="The query rewritten for maximum clarity and specificity"
    )

    research_scope: str = Field(
        description="Inferred research scope (narrow, moderate, broad)"
    )

    suggested_sub_topics: List[str] = Field(
        default_factory=list,
        description="Suggested sub-topics to cover in the research"
    )

    confidence: float = Field(
        description="Agent's confidence in its analysis (0.0 to 1.0)"
    )

    reasoning: str = Field(
        description="Explanation of the clarification analysis"
    )


# =============================================================================
# Clarification Agent
# =============================================================================

@register_agent("clarification")
class ClarificationAgent(BaseAgent):
    """
    Clarification Agent - Pre-research query validation.

    Responsibilities:
    1. Detect ambiguity in research queries
    2. Generate clarifying questions when needed
    3. Rewrite queries for specificity
    4. Prevent expensive research on unclear queries

    Benefits:
    - Reduces wasted API costs on poorly-defined queries
    - Improves research quality through focused queries
    - Better alignment with user intent
    - Faster time-to-value

    Configuration:
    - clarity_threshold: Minimum clarity score to proceed without clarification
    - max_questions: Maximum number of clarifying questions to generate
    - auto_bypass: Skip clarification for high-confidence queries
    """

    # Default thresholds (overridden by config if available)
    DEFAULT_CLARITY_THRESHOLD = 0.7
    DEFAULT_MAX_QUESTIONS = 5

    def __init__(self):
        config = AgentConfig(
            name="clarification",
            description="Pre-research query validation and clarification",
            task_tier="simple",  # Fast classification task
            temperature=0.2,  # Low temperature for consistent analysis
            max_tokens=1500,
        )
        super().__init__(config)

        # Load thresholds from config
        self.clarity_threshold = get_threshold(
            "clarification.clarity_threshold",
            self.DEFAULT_CLARITY_THRESHOLD
        )
        self.max_questions = get_threshold(
            "clarification.max_questions",
            self.DEFAULT_MAX_QUESTIONS
        )

    def get_system_prompt(self) -> str:
        return """You are a Research Query Clarification Specialist. Your job is to analyze incoming research queries and determine if they need clarification before expensive research begins.

YOUR GOALS:
1. Detect ambiguity, vagueness, or missing context in queries
2. Generate targeted clarifying questions when needed
3. Rewrite queries to be specific and actionable
4. Help users articulate exactly what they want to research

AMBIGUITY TYPES TO CHECK:
- SCOPE: Is the query too broad or undefined? (e.g., "research AI" vs "research AI applications in healthcare")
- CONTEXT: Is important context missing? (e.g., "best practices" without specifying the domain)
- TERMINOLOGY: Are there ambiguous technical terms? (e.g., "cloud" could mean weather or computing)
- INTENT: Is the research goal unclear? (e.g., informational vs decision-making)
- GEOGRAPHIC: Is geographic scope missing when relevant? (e.g., "market size" without region)
- TEMPORAL: Is time frame missing when relevant? (e.g., "trends" without period)
- QUANTITATIVE: Are metrics/quantities unclear? (e.g., "significant impact" without definition)

PRIORITY LEVELS FOR QUESTIONS:
- CRITICAL: Without this, research would go in wrong direction
- HIGH: Strongly recommended for quality results
- MEDIUM: Would improve specificity and relevance
- LOW: Nice to have, minor refinement

CLARITY SCORING GUIDE:
- 0.0-0.3: Very ambiguous, multiple interpretations, must clarify
- 0.3-0.5: Somewhat ambiguous, clarification recommended
- 0.5-0.7: Mostly clear, minor clarifications would help
- 0.7-0.9: Clear query, can proceed without clarification
- 0.9-1.0: Crystal clear, specific, well-defined query

QUERY REWRITING PRINCIPLES:
1. Add specificity without changing intent
2. Explicit scope when implied
3. Define time frames when temporal context matters
4. Specify geographic scope when relevant
5. Clarify technical terms with domain context
6. Keep the essence of the original question

EXAMPLES:

Query: "What are the best water filters?"
Ambiguities: scope (home/industrial?), geographic (which market?), criteria (best = cheapest/most effective?)
Clarity: 0.35
Needs clarification: Yes
Questions:
1. [CRITICAL] Are you looking for home/household or industrial water filters?
2. [HIGH] What's your geographic region (for availability and regulations)?
3. [MEDIUM] What's most important: cost, effectiveness, or ease of use?

Query: "Analyze the market size for residential water filtration systems in North America for 2024"
Clarity: 0.92
Needs clarification: No
Rewritten: "Analyze the 2024 market size for residential water filtration systems in North America, including revenue, volume, and growth trends by segment"

Query: "Tell me about blockchain"
Ambiguities: scope (very broad), intent (learn basics? investment? implementation?)
Clarity: 0.2
Needs clarification: Yes
Questions:
1. [CRITICAL] What aspect of blockchain interests you: the technology, applications, investments, or development?
2. [CRITICAL] What's your current knowledge level: beginner, intermediate, or expert?
3. [HIGH] Do you have a specific use case or industry in mind?

ALWAYS provide a rewritten query, even if clarification is needed. The rewritten version should reflect your best interpretation given the ambiguity."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Analyze query and determine if clarification is needed.

        Args:
            state: Current research state with query

        Returns:
            Updated state with clarification results
        """
        logger.info("[CLARIFICATION] Analyzing query for ambiguity...")

        # Extract query from state
        query = state.get("original_query", state.get("query", ""))

        if not query:
            logger.warning("[CLARIFICATION] No query found in state")
            return state

        # Check for prior clarification history
        clarification_history = state.get("clarification_history", [])

        # Build context message
        context_parts = [f"Research Query: {query}"]

        if clarification_history:
            context_parts.append("\nPrevious Clarifications:")
            for entry in clarification_history[-3:]:  # Last 3 clarifications
                context_parts.append(f"- Q: {entry.get('question', '')}")
                context_parts.append(f"  A: {entry.get('answer', '')}")

        context_message = "\n".join(context_parts)

        # Call LLM with structured output
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=context_message),
        ]

        try:
            result: ClarificationOutput = self.call_llm_structured(
                messages=messages,
                output_schema=ClarificationOutput,
            )

            if result is None:
                logger.warning("[CLARIFICATION] LLM returned None, using defaults")
                result = self._default_output(query)

        except Exception as e:
            logger.error(f"[CLARIFICATION] Error calling LLM: {e}")
            result = self._default_output(query)

        # Apply threshold override
        if result.clarity_score >= self.clarity_threshold:
            result.needs_clarification = False
            logger.info(
                f"[CLARIFICATION] Query is clear (score={result.clarity_score:.2f}), "
                "proceeding without clarification"
            )
        else:
            # Limit number of questions
            if len(result.clarifying_questions) > self.max_questions:
                result.clarifying_questions = result.clarifying_questions[:self.max_questions]

            logger.info(
                f"[CLARIFICATION] Query needs clarification "
                f"(score={result.clarity_score:.2f}, "
                f"questions={len(result.clarifying_questions)})"
            )

        # Update state
        state["clarification_result"] = result.model_dump()
        state["needs_clarification"] = result.needs_clarification
        state["rewritten_query"] = result.rewritten_query
        state["clarity_score"] = result.clarity_score

        # Log for debugging
        logger.info(f"[CLARIFICATION] Clarity score: {result.clarity_score:.2f}")
        logger.info(f"[CLARIFICATION] Needs clarification: {result.needs_clarification}")
        logger.info(f"[CLARIFICATION] Rewritten query: {result.rewritten_query[:100]}...")

        return state

    def _default_output(self, query: str) -> ClarificationOutput:
        """Return default output when LLM fails."""
        return ClarificationOutput(
            needs_clarification=False,
            clarity_score=0.5,
            ambiguity_types=["unknown"],
            clarifying_questions=[],
            rewritten_query=query,
            research_scope="moderate",
            suggested_sub_topics=[],
            confidence=0.3,
            reasoning="Using default output due to LLM error",
        )

    def process_user_response(
        self,
        state: ResearchState,
        question: str,
        answer: str,
    ) -> ResearchState:
        """
        Process a user's response to a clarifying question.

        Args:
            state: Current research state
            question: The clarifying question that was asked
            answer: User's response

        Returns:
            Updated state with clarification recorded
        """
        # Add to clarification history
        clarification_history = state.get("clarification_history", [])
        clarification_history.append({
            "question": question,
            "answer": answer,
        })
        state["clarification_history"] = clarification_history

        # Re-analyze with new context
        return self.process(state)

    def format_questions_for_user(self, state: ResearchState) -> str:
        """
        Format clarifying questions for display to user.

        Args:
            state: Research state with clarification results

        Returns:
            Formatted string of questions
        """
        result = state.get("clarification_result", {})
        questions = result.get("clarifying_questions", [])

        if not questions:
            return "No clarification needed."

        lines = ["Before starting research, I'd like to clarify a few things:\n"]

        for i, q in enumerate(questions, 1):
            priority = q.get("priority", "medium").upper()
            question_text = q.get("question", "")
            options = q.get("options", [])

            lines.append(f"{i}. [{priority}] {question_text}")

            if options:
                for opt in options:
                    lines.append(f"   - {opt}")

        lines.append("\nPlease provide your answers to help focus the research.")

        return "\n".join(lines)


# =============================================================================
# Standalone Functions
# =============================================================================

def analyze_query_clarity(query: str) -> ClarificationOutput:
    """
    Analyze a query's clarity without full agent setup.

    Args:
        query: The research query to analyze

    Returns:
        ClarificationOutput with analysis results
    """
    agent = ClarificationAgent()
    state = {"original_query": query}
    updated_state = agent.process(state)
    return ClarificationOutput(**updated_state.get("clarification_result", {}))


def needs_clarification(query: str) -> bool:
    """
    Quick check if a query needs clarification.

    Args:
        query: The research query to check

    Returns:
        True if clarification is recommended
    """
    result = analyze_query_clarity(query)
    return result.needs_clarification


def rewrite_query(query: str) -> str:
    """
    Rewrite a query for maximum specificity.

    Args:
        query: The original query

    Returns:
        Rewritten, more specific query
    """
    result = analyze_query_clarity(query)
    return result.rewritten_query


# =============================================================================
# Self-Test
# =============================================================================

def self_test() -> bool:
    """Run self-tests for Clarification agent."""
    print("Running Clarification Agent self-tests...")

    # Test output schemas
    question = ClarifyingQuestion(
        question="What type of water filter?",
        ambiguity_type="scope",
        priority="critical",
        options=["Home/residential", "Industrial", "Portable/travel"],
    )
    assert question.question
    assert question.priority == "critical"
    print("  [PASS] ClarifyingQuestion schema")

    output = ClarificationOutput(
        needs_clarification=True,
        clarity_score=0.4,
        ambiguity_types=["scope", "geographic"],
        clarifying_questions=[question],
        rewritten_query="Research residential water filters for home use",
        research_scope="moderate",
        suggested_sub_topics=["filter types", "price comparison"],
        confidence=0.8,
        reasoning="Query lacks specificity about filter type and region",
    )
    assert output.needs_clarification
    assert len(output.clarifying_questions) == 1
    print("  [PASS] ClarificationOutput schema")

    # Test agent instantiation
    agent = ClarificationAgent()
    assert agent.config.name == "clarification"
    print("  [PASS] Agent instantiation")

    # Test default output
    default = agent._default_output("test query")
    assert default.rewritten_query == "test query"
    assert default.confidence == 0.3
    print("  [PASS] Default output generation")

    print("\nAll Clarification Agent self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
