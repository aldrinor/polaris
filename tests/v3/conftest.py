"""v3 test fixtures and mock factories.

Provides deterministic mock LLM responses for each v3 schema type,
enabling $0 tests that validate contracts without API calls.
"""

import json
import os
from typing import Type
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineSection,
    Reflection,
    ScopeOutput,
    SearchQuery,
    SearchRoundOutput,
    SubQuestion,
    V3ResultOutput,
    VerifiedSectionDraft,
)


# ---------------------------------------------------------------------------
# Mock LLM Factory
# ---------------------------------------------------------------------------

# Canned JSON responses for each schema type
CANNED_RESPONSES = {
    "ScopeOutput": {
        "sub_questions": [
            {"id": "sq_01", "question": "What mechanisms drive biochar adsorption of heavy metals?", "analytical_focus": "explain", "expected_depth": "deep"},
            {"id": "sq_02", "question": "How do pyrolysis conditions affect biochar performance?", "analytical_focus": "compare", "expected_depth": "deep"},
            {"id": "sq_03", "question": "What removal efficiencies have been reported across different metals?", "analytical_focus": "aggregate", "expected_depth": "deep"},
            {"id": "sq_04", "question": "How does biochar compare to conventional adsorbents?", "analytical_focus": "tabulate", "expected_depth": "moderate"},
            {"id": "sq_05", "question": "What are the limitations and knowledge gaps?", "analytical_focus": "challenge", "expected_depth": "moderate"},
            {"id": "sq_06", "question": "What are the cost-effectiveness considerations?", "analytical_focus": "compare", "expected_depth": "brief"},
        ],
        "perspectives": ["Scientific", "Engineering", "Environmental", "Economic", "Regulatory"],
        "search_queries": [
            {"query": "biochar heavy metal adsorption mechanisms", "sub_question_id": "sq_01", "perspective": "Scientific", "source_preference": "academic"},
            {"query": "pyrolysis temperature biochar performance", "sub_question_id": "sq_02", "perspective": "Engineering", "source_preference": "both"},
            {"query": "biochar removal efficiency lead cadmium chromium", "sub_question_id": "sq_03", "perspective": "Scientific", "source_preference": "academic"},
            {"query": "biochar vs activated carbon wastewater treatment", "sub_question_id": "sq_04", "perspective": "Engineering", "source_preference": "both"},
            {"query": "biochar wastewater treatment limitations gaps", "sub_question_id": "sq_05", "perspective": "Environmental", "source_preference": "web"},
            {"query": "biochar cost analysis wastewater", "sub_question_id": "sq_06", "perspective": "Economic", "source_preference": "web"},
        ],
        "complexity": "complex",
        "estimated_depth": 300,
    },
    "LiveOutline": {
        "title": "Biochar for Heavy Metal Removal: Mechanisms, Performance, and Outlook",
        "abstract_draft": "This report examines biochar effectiveness for heavy metal removal from wastewater.",
        "sections": [
            {"id": "s01", "title": "Adsorption Mechanisms", "sub_question_id": "sq_01", "description": "Ion exchange, complexation, precipitation", "analytical_focus": "explain", "evidence_ids": ["ev_001", "ev_002", "ev_003"], "confidence": 0.8, "target_words": 1500, "cross_refs": [], "order": 1},
            {"id": "s02", "title": "Pyrolysis Conditions", "sub_question_id": "sq_02", "description": "Temperature, feedstock, residence time effects", "analytical_focus": "compare", "evidence_ids": ["ev_004", "ev_005", "ev_006"], "confidence": 0.7, "target_words": 1200, "cross_refs": ["s01"], "order": 2},
            {"id": "s03", "title": "Removal Efficiencies", "sub_question_id": "sq_03", "description": "Cross-metal, cross-study performance data", "analytical_focus": "aggregate", "evidence_ids": ["ev_007", "ev_008", "ev_009", "ev_010"], "confidence": 0.9, "target_words": 1500, "cross_refs": ["s01", "s02"], "order": 3},
            {"id": "s04", "title": "Comparison with Conventional Adsorbents", "sub_question_id": "sq_04", "description": "Biochar vs activated carbon, zeolite, ion exchange resins", "analytical_focus": "tabulate", "evidence_ids": ["ev_011", "ev_012"], "confidence": 0.6, "target_words": 800, "cross_refs": ["s03"], "order": 4},
            {"id": "s05", "title": "Limitations and Future Directions", "sub_question_id": "sq_05", "description": "Gaps, challenges, scalability issues", "analytical_focus": "challenge", "evidence_ids": ["ev_013", "ev_014"], "confidence": 0.5, "target_words": 600, "cross_refs": ["s03", "s04"], "order": 5},
        ],
        "version": 1,
        "gaps": [],
        "narrative_flow": "Mechanisms -> Conditions -> Performance -> Comparison -> Limitations",
    },
}


class MockLLMClient:
    """Mock OpenRouterClient that returns canned JSON for each schema type."""

    def __init__(self):
        self.calls = []  # Track all calls for assertions
        self.model = "mock/test-model"

    async def generate_structured(self, prompt, schema, system="", **kwargs):
        """Return a pre-built instance of the requested schema."""
        schema_name = schema.__name__
        self.calls.append({
            "method": "generate_structured",
            "schema": schema_name,
            "prompt_length": len(prompt),
        })
        if schema_name in CANNED_RESPONSES:
            return schema.model_validate(CANNED_RESPONSES[schema_name])
        # Default: return an empty instance
        return schema.model_validate({})

    async def generate(self, prompt, system="", **kwargs):
        """Return a mock LLMResponse for prose generation."""
        self.calls.append({
            "method": "generate",
            "prompt_length": len(prompt),
        })
        return MagicMock(
            content="Mock generated content with analysis and [CITE:ev_001] citations.",
            reasoning_content="",
        )

    async def reason(self, prompt, system="", **kwargs):
        """Return a mock LLMResponse for reasoning calls."""
        self.calls.append({
            "method": "reason",
            "prompt_length": len(prompt),
        })
        return MagicMock(
            content="Mock reasoning output.",
            reasoning_content="Mock chain of thought.",
        )


@pytest.fixture
def mock_llm():
    """Provide a mock LLM client that returns canned responses."""
    return MockLLMClient()


@pytest.fixture
def sample_scope_output():
    """A valid ScopeOutput for testing downstream phases."""
    return ScopeOutput.model_validate(CANNED_RESPONSES["ScopeOutput"])


@pytest.fixture
def sample_outline():
    """A valid LiveOutline for testing synthesis."""
    return LiveOutline.model_validate(CANNED_RESPONSES["LiveOutline"])


@pytest.fixture
def sample_evidence_store():
    """Mock evidence store (side-channel, not in state)."""
    return {
        f"ev_{i:03d}": {
            "evidence_id": f"ev_{i:03d}",
            "statement": f"Mock finding #{i} about biochar with specific data point {90 + i}%.",
            "direct_quote": f"The removal efficiency was {90 + i}% under controlled conditions.",
            "source_url": f"https://example.com/source-{i}",
            "source_title": f"Study on Biochar Application {i}",
            "quality_tier": "GOLD" if i <= 5 else ("SILVER" if i <= 10 else "BRONZE"),
            "relevance_score": round(0.9 - i * 0.03, 2),
            "perspective": ["Scientific", "Engineering", "Environmental"][i % 3],
        }
        for i in range(1, 16)
    }


@pytest.fixture
def sample_search_round():
    """A valid SearchRoundOutput for testing outline generation."""
    return SearchRoundOutput(
        round_number=1,
        evidence_ids=[f"ev_{i:03d}" for i in range(1, 11)],
        reflections=[
            Reflection(
                insight="Biochar removal efficiencies range from 67-99% across 12 studies.",
                sub_question_id="sq_03",
                evidence_ids=["ev_007", "ev_008", "ev_009"],
                confidence=0.85,
            ),
            Reflection(
                insight="Pyrolysis temperature is the dominant factor affecting surface area.",
                sub_question_id="sq_02",
                evidence_ids=["ev_004", "ev_005"],
                confidence=0.75,
            ),
        ],
        sources_fetched=15,
        convergence_score=0.3,
        gaps=["No studies on mixed-metal competitive adsorption"],
    )


@pytest.fixture
def sample_verified_sections():
    """List of VerifiedSectionDrafts for testing assembly."""
    return [
        VerifiedSectionDraft(
            section_id=f"s{i:02d}",
            title=f"Section {i}: Test Topic",
            content=f"Analysis of findings from multiple studies [CITE:ev_{i:03d}]. "
                    f"Compared to alternative methods, biochar showed {85 + i}% efficiency [CITE:ev_{i+1:03d}].",
            evidence_ids_used=[f"ev_{i:03d}", f"ev_{i+1:03d}"],
            claims_verified=3,
            claims_total=4,
            faithfulness_score=0.85,
            critic_passed=True,
            revisions=0,
            word_count=200 + i * 50,
            analytical_depth={"comparison_markers": 2, "aggregation_patterns": 1},
        )
        for i in range(1, 6)
    ]


@pytest.fixture
def sample_v3_result(sample_verified_sections, sample_evidence_store):
    """A complete V3ResultOutput matching v1 format."""
    return V3ResultOutput(
        vector_id="V3_TEST_001",
        original_query="effectiveness of biochar for heavy metal removal from wastewater",
        status="completed",
        final_report="# Report\n\n" + "\n\n".join(
            f"## {s.title}\n\n{s.content}" for s in sample_verified_sections
        ),
        bibliography=[
            {"citation_number": i, "title": f"Study {i}", "url": f"https://example.com/{i}"}
            for i in range(1, 6)
        ],
        quality_metrics={
            "faithfulness_pct": 85.0,
            "word_count": 1500,
            "citation_count": 10,
            "sources_used": 5,
        },
        sections=[s.model_dump() for s in sample_verified_sections],
        evidence=list(sample_evidence_store.values()),
        claims=[],
        iteration_count=1,
        timestamps={"started": "2026-03-17T12:00:00", "completed": "2026-03-17T12:30:00"},
        trace_summary={"total_events": 50},
        v3_metadata={"outline_versions": 2, "search_rounds": 3},
    )
