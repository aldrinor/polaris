"""v3 Phase Boundary Contracts.

These Pydantic models define the EXACT data shape that flows between
each phase of the v3 pipeline. Tests validate these contracts BEFORE
implementation code exists.

Phase flow: SCOPE -> SEARCH -> OUTLINE -> SYNTHESIZE -> ASSEMBLE
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Phase 1: SCOPE output
# ---------------------------------------------------------------------------

class SubQuestion(BaseModel):
    """A single sub-question decomposed from the research query."""

    id: str = Field(description="Unique ID, e.g. 'sq_01'")
    question: str = Field(description="The sub-question text")
    analytical_focus: str = Field(
        description="Primary operation: aggregate|compare|explain|tabulate|challenge",
        default="explain",
    )
    expected_depth: str = Field(
        description="How deep: deep|moderate|brief",
        default="moderate",
    )
    parent_id: Optional[str] = Field(
        description="Parent sub-question ID for DAG structure",
        default=None,
    )

    @field_validator("analytical_focus", mode="before")
    @classmethod
    def validate_focus(cls, v):
        valid = {"aggregate", "compare", "explain", "tabulate", "challenge"}
        if isinstance(v, str) and v.lower().strip() in valid:
            return v.lower().strip()
        return "explain"

    @field_validator("expected_depth", mode="before")
    @classmethod
    def validate_depth(cls, v):
        valid = {"deep", "moderate", "brief"}
        if isinstance(v, str) and v.lower().strip() in valid:
            return v.lower().strip()
        return "moderate"


class SearchQuery(BaseModel):
    """A search query linked to a sub-question."""

    query: str
    sub_question_id: str
    perspective: str = "Scientific"
    source_preference: str = Field(
        description="web|academic|both",
        default="both",
    )


class ScopeOutput(BaseModel):
    """Output of Phase 1: SCOPE. Drives all subsequent phases."""

    sub_questions: list[SubQuestion] = Field(
        description="6-10 sub-questions decomposed from the research query",
    )
    perspectives: list[str] = Field(
        description="5-8 STORM perspectives for diverse evidence collection",
    )
    search_queries: list[SearchQuery] = Field(
        description="3-5 search queries per sub-question",
        default_factory=list,
    )
    complexity: str = Field(
        description="simple|moderate|complex",
        default="moderate",
    )
    estimated_depth: int = Field(
        description="Target evidence count",
        default=200,
    )

    @field_validator("estimated_depth", mode="before")
    @classmethod
    def coerce_estimated_depth(cls, v):
        """LLM returns '200-500' or 'approximately 300' — extract first integer."""
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            import re
            nums = re.findall(r'\d+', v)
            return int(nums[0]) if nums else 200
        return 200

    @model_validator(mode="before")
    @classmethod
    def normalize_scope_fields(cls, data):
        """Handle LLM field name variations for search_queries."""
        if isinstance(data, dict):
            # LLM may use "queries", "search_query_list", etc.
            for alt in ("queries", "search_query_list", "generated_queries"):
                if alt in data and "search_queries" not in data:
                    data["search_queries"] = data.pop(alt)
            # Ensure search_queries exists
            if "search_queries" not in data:
                data["search_queries"] = []
        return data

    @model_validator(mode="after")
    def validate_minimums(self):
        if len(self.sub_questions) < 3:
            raise ValueError(f"Need >= 3 sub-questions, got {len(self.sub_questions)}")
        if len(self.perspectives) < 3:
            raise ValueError(f"Need >= 3 perspectives, got {len(self.perspectives)}")
        # search_queries can be empty — fallback generates them
        return self


# ---------------------------------------------------------------------------
# Phase 2: SEARCH output (per round)
# ---------------------------------------------------------------------------

class Reflection(BaseModel):
    """Tavily pattern: distilled insight from a search round."""

    insight: str = Field(description="Key finding in 1-2 sentences")
    sub_question_id: str = Field(description="Which question this answers")
    evidence_ids: list[str] = Field(
        description="Supporting evidence IDs",
        default_factory=list,
    )
    confidence: float = Field(description="How well-supported (0-1)", default=0.5)


class SearchRoundOutput(BaseModel):
    """Output of one search round in Phase 2."""

    round_number: int
    evidence_ids: list[str] = Field(
        description="IDs of evidence collected this round (content in side-channel)",
    )
    reflections: list[Reflection] = Field(
        description="Distilled insights from this round",
    )
    sources_fetched: int = 0
    convergence_score: float = Field(
        description="0-1, how much new info this round added. >0.85 = saturated",
        default=0.0,
    )
    gaps: list[str] = Field(
        description="Identified knowledge gaps",
        default_factory=list,
    )


# ---------------------------------------------------------------------------
# Phase 3: OUTLINE (living document)
# ---------------------------------------------------------------------------

class OutlineGap(BaseModel):
    """A gap in the outline that needs more evidence."""

    section_id: str
    description: str
    suggested_queries: list[str] = Field(default_factory=list)


class OutlineSection(BaseModel):
    """A single section in the living outline."""

    id: str
    title: str
    sub_question_id: str = Field(description="Which sub-question this answers")
    description: str = ""
    analytical_focus: str = "explain"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Based on evidence depth", default=0.0)
    target_words: int = 800
    cross_refs: list[str] = Field(
        description="Section IDs this references",
        default_factory=list,
    )
    order: int = 0


class LiveOutline(BaseModel):
    """The living outline — evolves with each search round."""

    title: str
    abstract_draft: str = ""
    sections: list[OutlineSection] = Field(default_factory=list)
    version: int = Field(description="Increments on each refinement", default=1)
    gaps: list[OutlineGap] = Field(default_factory=list)
    narrative_flow: str = Field(
        description="How sections connect logically",
        default="",
    )

    @model_validator(mode="after")
    def validate_sections(self):
        if len(self.sections) == 0:
            raise ValueError("Outline must have at least 1 section")
        return self


# ---------------------------------------------------------------------------
# Phase 4: SYNTHESIZE output (per section)
# ---------------------------------------------------------------------------

class VerifiedSectionDraft(BaseModel):
    """Output of write + inline verify + critic for one section."""

    section_id: str
    title: str
    content: str = Field(description="Markdown with [CITE:ev_xxx] tokens")
    evidence_ids_used: list[str] = Field(
        description="Evidence actually cited in this section",
        default_factory=list,
    )
    claims_verified: int = 0
    claims_total: int = 0
    faithfulness_score: float = Field(default=0.0)
    critic_passed: bool = False
    critic_feedback: Optional[str] = None
    revisions: int = Field(description="How many critic rounds (max 2)", default=0)
    word_count: int = 0
    analytical_depth: dict = Field(
        description="Comparison/aggregation/challenge marker counts",
        default_factory=dict,
    )


# ---------------------------------------------------------------------------
# Phase 5: ASSEMBLE output (final result)
# ---------------------------------------------------------------------------

class V3ResultOutput(BaseModel):
    """Output JSON written to outputs/polaris_graph/{vector_id}.json.

    Must contain all fields that live_server.py endpoints read.
    Validated against actual v1 result JSON for compatibility.
    """

    vector_id: str
    original_query: str
    status: str = Field(description="completed|partial|failed")
    final_report: str = Field(description="Full markdown report")
    bibliography: list[dict] = Field(default_factory=list)
    quality_metrics: dict = Field(default_factory=dict)
    sections: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
    iteration_count: int = 0
    timestamps: dict = Field(default_factory=dict)
    trace_summary: dict = Field(default_factory=dict)

    # v3-specific (frontend ignores unknown keys)
    v3_metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trace event contract
# ---------------------------------------------------------------------------

REQUIRED_TRACE_EVENTS = {
    "pipeline_start": ["query", "vector_id"],
    "pipeline_end": ["status", "total_words", "total_citations", "total_cost_usd", "elapsed_seconds"],
    "node_start": ["node"],
    "node_end": ["node"],
}

REQUIRED_EVIDENCE_ACTIONS = {
    "extracted": ["count"],
    "accumulated": ["count"],
    "query_plan": ["queries"],
    "report_outline": ["sections"],
    "report_assembled": ["full_report", "bibliography", "total_citations"],
}

V3_NODE_NAMES = [
    "scope", "v3_search", "v3_storm", "v3_outline",
    "v3_write_section", "v3_critic", "v3_assemble",
]
