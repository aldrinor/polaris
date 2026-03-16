#!/usr/bin/env python3
"""
Unit tests for Clarification Agent.

Tests:
- Output schema validation
- Agent initialization
- Query clarity analysis
- Clarifying question generation
- Query rewriting

Run:
    pytest tests/unit/test_clarification_agent.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.clarification_agent import (
    ClarificationAgent,
    ClarificationOutput,
    ClarifyingQuestion,
    AmbiguityType,
    ClarificationPriority,
)


class TestClarifyingQuestion:
    """Tests for ClarifyingQuestion schema."""

    def test_basic_question(self):
        """Test creating a basic clarifying question."""
        q = ClarifyingQuestion(
            question="What type of water filter are you looking for?",
            ambiguity_type="scope",
            priority="critical",
        )
        assert q.question
        assert q.ambiguity_type == "scope"
        assert q.priority == "critical"
        assert q.options is None

    def test_question_with_options(self):
        """Test creating a question with suggested options."""
        q = ClarifyingQuestion(
            question="What's your geographic focus?",
            ambiguity_type="geographic",
            priority="high",
            options=["North America", "Europe", "Asia-Pacific", "Global"],
        )
        assert len(q.options) == 4
        assert "North America" in q.options

    def test_all_priority_levels(self):
        """Test all priority levels are accepted."""
        priorities = ["critical", "high", "medium", "low"]
        for priority in priorities:
            q = ClarifyingQuestion(
                question="Test",
                ambiguity_type="test",
                priority=priority,
            )
            assert q.priority == priority


class TestClarificationOutput:
    """Tests for ClarificationOutput schema."""

    def test_basic_output(self):
        """Test creating basic clarification output."""
        output = ClarificationOutput(
            needs_clarification=True,
            clarity_score=0.4,
            ambiguity_types=["scope"],
            rewritten_query="Rewritten query",
            research_scope="moderate",
            confidence=0.8,
            reasoning="Test reasoning",
        )
        assert output.needs_clarification is True
        assert output.clarity_score == 0.4
        assert output.rewritten_query == "Rewritten query"

    def test_output_with_questions(self):
        """Test output with clarifying questions."""
        question = ClarifyingQuestion(
            question="Test question",
            ambiguity_type="scope",
            priority="high",
        )
        output = ClarificationOutput(
            needs_clarification=True,
            clarity_score=0.3,
            ambiguity_types=["scope", "context"],
            clarifying_questions=[question],
            rewritten_query="Rewritten",
            research_scope="broad",
            suggested_sub_topics=["topic1", "topic2"],
            confidence=0.7,
            reasoning="Multiple ambiguities detected",
        )
        assert len(output.clarifying_questions) == 1
        assert len(output.suggested_sub_topics) == 2

    def test_clear_query_output(self):
        """Test output for a clear query."""
        output = ClarificationOutput(
            needs_clarification=False,
            clarity_score=0.95,
            ambiguity_types=[],
            clarifying_questions=[],
            rewritten_query="Analyze 2024 water filter market in North America",
            research_scope="narrow",
            suggested_sub_topics=["market size", "trends", "competition"],
            confidence=0.95,
            reasoning="Query is well-defined and specific",
        )
        assert output.needs_clarification is False
        assert output.clarity_score >= 0.9
        assert len(output.clarifying_questions) == 0


class TestAmbiguityType:
    """Tests for AmbiguityType enum."""

    def test_all_ambiguity_types(self):
        """Test all ambiguity types are defined."""
        expected = ["scope", "context", "terminology", "intent",
                    "geographic", "temporal", "quantitative", "none"]
        for type_name in expected:
            assert hasattr(AmbiguityType, type_name.upper())

    def test_enum_values(self):
        """Test enum values match expected strings."""
        assert AmbiguityType.SCOPE.value == "scope"
        assert AmbiguityType.CONTEXT.value == "context"
        assert AmbiguityType.NONE.value == "none"


class TestClarificationPriority:
    """Tests for ClarificationPriority enum."""

    def test_all_priorities(self):
        """Test all priority levels are defined."""
        assert ClarificationPriority.CRITICAL.value == "critical"
        assert ClarificationPriority.HIGH.value == "high"
        assert ClarificationPriority.MEDIUM.value == "medium"
        assert ClarificationPriority.LOW.value == "low"


class TestClarificationAgent:
    """Tests for ClarificationAgent class."""

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        agent = ClarificationAgent()
        assert agent.config.name == "clarification"
        assert agent.config.task_tier == "simple"
        assert agent.clarity_threshold > 0

    def test_system_prompt(self):
        """Test system prompt is well-formed."""
        agent = ClarificationAgent()
        prompt = agent.get_system_prompt()
        assert len(prompt) > 500
        assert "ambiguity" in prompt.lower()
        assert "clarity" in prompt.lower()
        assert "rewrite" in prompt.lower()

    def test_default_output(self):
        """Test default output generation."""
        agent = ClarificationAgent()
        default = agent._default_output("test query")
        assert default.rewritten_query == "test query"
        assert default.needs_clarification is False
        assert default.confidence == 0.3

    @patch.object(ClarificationAgent, 'call_llm_structured')
    def test_process_with_clear_query(self, mock_llm):
        """Test processing with a clear query."""
        mock_llm.return_value = ClarificationOutput(
            needs_clarification=False,
            clarity_score=0.9,
            ambiguity_types=[],
            clarifying_questions=[],
            rewritten_query="Analyze 2024 water filter market",
            research_scope="narrow",
            suggested_sub_topics=[],
            confidence=0.9,
            reasoning="Clear query",
        )

        agent = ClarificationAgent()
        state = {"original_query": "Analyze 2024 water filter market in North America"}
        result = agent.process(state)

        assert result.get("needs_clarification") is False
        assert result.get("clarity_score", 0) >= 0.7

    @patch.object(ClarificationAgent, 'call_llm_structured')
    def test_process_with_ambiguous_query(self, mock_llm):
        """Test processing with an ambiguous query."""
        mock_llm.return_value = ClarificationOutput(
            needs_clarification=True,
            clarity_score=0.3,
            ambiguity_types=["scope", "geographic"],
            clarifying_questions=[
                ClarifyingQuestion(
                    question="What type of filter?",
                    ambiguity_type="scope",
                    priority="critical",
                )
            ],
            rewritten_query="Research water filters",
            research_scope="broad",
            suggested_sub_topics=[],
            confidence=0.7,
            reasoning="Query is too broad",
        )

        agent = ClarificationAgent()
        state = {"original_query": "Tell me about water filters"}
        result = agent.process(state)

        assert result.get("needs_clarification") is True
        assert result.get("clarity_score", 1.0) < 0.5

    @patch.object(ClarificationAgent, 'call_llm_structured')
    def test_process_handles_llm_error(self, mock_llm):
        """Test processing gracefully handles LLM errors."""
        mock_llm.return_value = None

        agent = ClarificationAgent()
        state = {"original_query": "Test query"}
        result = agent.process(state)

        # Should not raise, should use defaults
        assert "clarification_result" in result
        assert result.get("rewritten_query") == "Test query"

    def test_format_questions(self):
        """Test formatting questions for user display."""
        agent = ClarificationAgent()
        state = {
            "clarification_result": {
                "clarifying_questions": [
                    {
                        "question": "What region?",
                        "priority": "critical",
                        "options": ["US", "EU"],
                    },
                    {
                        "question": "What budget?",
                        "priority": "medium",
                        "options": None,
                    },
                ]
            }
        }

        formatted = agent.format_questions_for_user(state)
        assert "1. [CRITICAL] What region?" in formatted
        assert "2. [MEDIUM] What budget?" in formatted
        assert "- US" in formatted

    def test_format_questions_no_questions(self):
        """Test formatting when no questions needed."""
        agent = ClarificationAgent()
        state = {"clarification_result": {"clarifying_questions": []}}

        formatted = agent.format_questions_for_user(state)
        assert "No clarification needed" in formatted


class TestClarificationIntegration:
    """Integration tests for clarification workflow."""

    @patch.object(ClarificationAgent, 'call_llm_structured')
    def test_multi_turn_clarification(self, mock_llm):
        """Test multi-turn clarification with user responses."""
        # First call - needs clarification
        mock_llm.return_value = ClarificationOutput(
            needs_clarification=True,
            clarity_score=0.4,
            ambiguity_types=["scope"],
            clarifying_questions=[
                ClarifyingQuestion(
                    question="What type?",
                    ambiguity_type="scope",
                    priority="critical",
                )
            ],
            rewritten_query="Research water filters",
            research_scope="broad",
            suggested_sub_topics=[],
            confidence=0.7,
            reasoning="Needs scope clarification",
        )

        agent = ClarificationAgent()
        state = {"original_query": "Tell me about filters"}

        # First run - needs clarification
        result1 = agent.process(state)
        assert result1.get("needs_clarification") is True

        # User provides response - now clear
        mock_llm.return_value = ClarificationOutput(
            needs_clarification=False,
            clarity_score=0.85,
            ambiguity_types=[],
            clarifying_questions=[],
            rewritten_query="Research residential water filters for home use",
            research_scope="narrow",
            suggested_sub_topics=["types", "cost"],
            confidence=0.9,
            reasoning="Query clarified after user input",
        )

        result2 = agent.process_user_response(
            result1,
            "What type?",
            "Residential water filters for home use"
        )

        assert result2.get("needs_clarification") is False
        assert len(result2.get("clarification_history", [])) == 1

    def test_self_test_function(self):
        """Test that self-test function passes."""
        from src.agents.clarification_agent import self_test
        assert self_test() is True


class TestClarificationThresholds:
    """Tests for threshold integration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        agent = ClarificationAgent()
        assert agent.clarity_threshold == 0.7
        assert agent.max_questions == 5

    @patch("src.agents.clarification_agent.get_threshold")
    def test_custom_thresholds(self, mock_get_threshold):
        """Test custom threshold values from config."""
        mock_get_threshold.side_effect = lambda key, default: {
            "clarification.clarity_threshold": 0.8,
            "clarification.max_questions": 3,
        }.get(key, default)

        agent = ClarificationAgent()
        assert agent.clarity_threshold == 0.8
        assert agent.max_questions == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
