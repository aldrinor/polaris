"""v3 Pipeline State — Decomposed, lightweight, OOM-safe.

Key design: Evidence content is stored OUTSIDE this state in a
side-channel dict (evidence_store). State carries only evidence IDs
and lightweight metadata. This prevents LangGraph serialization OOM
at >1000 evidence pieces (P0 risk CC.7).

v1 state.py had 67 fields in one monolithic TypedDict.
v3 state has ~25 fields organized by phase.
"""

from typing import TypedDict


class V3State(TypedDict):
    """LangGraph state for the v3 pipeline.

    ALL fields must be declared here — LangGraph silently drops
    undeclared keys during state merging (lesson #10 from MEMORY.md).
    """

    # --- Identity (immutable after init) ---
    vector_id: str
    original_query: str
    application: str
    region: str

    # --- Phase 1: SCOPE output ---
    sub_questions: list[dict]    # SubQuestion dicts
    perspectives: list[str]
    search_queries: list[dict]   # SearchQuery dicts
    complexity: str              # simple | moderate | complex

    # --- Phase 2: SEARCH output (accumulated across rounds) ---
    evidence_ids: list[str]      # IDs only — content in evidence_store
    evidence_meta: dict[str, dict]  # {ev_id: {tier, score, source_url}}
    reflections: list[dict]      # Reflection dicts
    search_rounds_completed: int
    convergence_score: float

    # --- Phase 3: OUTLINE (versioned) ---
    outline: dict                # LiveOutline as dict
    outline_version: int
    gaps: list[dict]             # OutlineGap dicts
    gap_searches_done: int

    # --- Phase 3.5: ANALYSIS (ReAct agent results) ---
    analysis_entries: list[dict]    # AnalysisEntry dicts with provenance

    # --- Phase 4: SYNTHESIZE (accumulated per section) ---
    completed_sections: list[dict]  # VerifiedSectionDraft dicts
    used_evidence_ids: list[str]    # Can't use set in TypedDict

    # --- Phase 5: ASSEMBLE ---
    final_report: str
    bibliography: list[dict]
    quality_metrics: dict

    # --- Control ---
    status: str                  # running | completed | partial | failed
    research_brief: str          # Campaign Control Center context


def create_v3_state(
    vector_id: str,
    query: str,
    application: str = "",
    region: str = "",
    research_brief: str = "",
) -> V3State:
    """Create initial v3 state with safe defaults for all fields."""
    return V3State(
        # Identity
        vector_id=vector_id,
        original_query=query,
        application=application,
        region=region,
        # Phase 1
        sub_questions=[],
        perspectives=[],
        search_queries=[],
        complexity="moderate",
        # Phase 2
        evidence_ids=[],
        evidence_meta={},
        reflections=[],
        search_rounds_completed=0,
        convergence_score=0.0,
        # Phase 3
        outline={},
        outline_version=0,
        gaps=[],
        gap_searches_done=0,
        # Phase 3.5
        analysis_entries=[],
        # Phase 4
        completed_sections=[],
        used_evidence_ids=[],
        # Phase 5
        final_report="",
        bibliography=[],
        quality_metrics={},
        # Control
        status="running",
        research_brief=research_brief,
    )
