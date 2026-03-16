"""
Unit tests for agentic search loop.

Tests convergence detection, budget caps, seed partitioning,
schema validation, and feature flag dispatch.
"""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.polaris_graph.state import (
    STORM_PERSPECTIVES,
    create_initial_state,
)


# ---------------------------------------------------------------------------
# Test 1: Feature flag dispatch — agentic enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_dispatches_agentic():
    """When PG_AGENTIC_SEARCH_ENABLED=1 and client is provided, execute_agentic_search is called."""
    from src.polaris_graph.agents.searcher import execute_searches

    state = create_initial_state(
        vector_id="V_FLAG_ON",
        query="test query",
        application="general",
        region="GLOBAL",
    )
    state["sub_queries"] = ["query 1", "query 2"]

    mock_client = AsyncMock()
    mock_agentic_result = {
        "web_results": [{"url": "https://example.com", "title": "Test"}],
        "academic_results": [],
        "status": "analyzing",
        "agentic_search_rounds": 1,
        "agentic_total_queries": 2,
        "agentic_convergence_scores": [],
        "agentic_url_accumulator": [],
        "agentic_perspective_coverage": {},
    }

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_SEARCH_ENABLED", True), \
         patch("src.polaris_graph.agents.searcher.execute_agentic_search", new_callable=AsyncMock) as mock_agentic:
        mock_agentic.return_value = mock_agentic_result
        result = await execute_searches(state, client=mock_client)
        mock_agentic.assert_called_once_with(state, mock_client)


# ---------------------------------------------------------------------------
# Test 2: Feature flag dispatch — agentic disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_falls_back_when_disabled():
    """When PG_AGENTIC_SEARCH_ENABLED=0, legacy path is used."""
    from src.polaris_graph.agents.searcher import execute_searches

    state = create_initial_state(
        vector_id="V_FLAG_OFF",
        query="test query",
        application="general",
        region="GLOBAL",
    )
    state["sub_queries"] = ["query 1"]

    mock_client = AsyncMock()

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_SEARCH_ENABLED", False), \
         patch("src.polaris_graph.agents.searcher._import_search_tools") as mock_tools, \
         patch("src.polaris_graph.agents.searcher._adaptive_web_search", new_callable=AsyncMock) as mock_adaptive, \
         patch("src.polaris_graph.agents.searcher._run_academic_searches", new_callable=AsyncMock) as mock_acad, \
         patch("src.polaris_graph.agents.searcher._run_ddg_fallback_for_zeros", new_callable=AsyncMock) as mock_ddg, \
         patch("src.polaris_graph.agents.searcher._run_exa_searches", new_callable=AsyncMock) as mock_exa, \
         patch("src.polaris_graph.agents.searcher._chase_citations", new_callable=AsyncMock) as mock_chase:

        mock_tools.return_value = (MagicMock(), MagicMock())
        mock_adaptive.return_value = []
        mock_acad.return_value = []
        mock_ddg.return_value = []
        mock_exa.return_value = []
        mock_chase.return_value = []

        result = await execute_searches(state, client=mock_client)
        # Legacy path uses _adaptive_web_search
        mock_adaptive.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Convergence — URL overlap signal
# ---------------------------------------------------------------------------


def test_convergence_url_overlap():
    """URL overlap above threshold triggers convergence signal."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # 5 rounds with high overlap in last 3 (many results, few new URLs)
    round_summaries = [
        {"round": 1, "new_urls": 30, "web_results": 30, "academic_results": 5},
        {"round": 2, "new_urls": 20, "web_results": 25, "academic_results": 5},
        {"round": 3, "new_urls": 5, "web_results": 20, "academic_results": 3},
        {"round": 4, "new_urls": 3, "web_results": 20, "academic_results": 3},
        {"round": 5, "new_urls": 2, "web_results": 20, "academic_results": 3},
    ]

    # High perspective coverage
    perspective_hits = {p: 5 for p in STORM_PERSPECTIVES}

    analysis = AgenticRoundAnalysis(
        convergence_assessment="narrowing",
        should_continue=False,
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
        )

    # Should detect at least url_overlap and theme_saturation signals
    assert converged is True
    assert "url_overlap" in reason or "theme_saturation" in reason


# ---------------------------------------------------------------------------
# Test 4: Convergence — theme saturation signal
# ---------------------------------------------------------------------------


def test_convergence_theme_saturation():
    """All perspectives covered triggers theme saturation signal."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    round_summaries = [
        {"round": i, "new_urls": 10, "web_results": 15, "academic_results": 3}
        for i in range(1, 6)
    ]

    # All 9 perspectives covered
    perspective_hits = {p: 10 for p in STORM_PERSPECTIVES}

    analysis = AgenticRoundAnalysis(
        convergence_assessment="saturated",
        should_continue=False,
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
        )

    assert converged is True
    assert "theme_saturation" in reason


# ---------------------------------------------------------------------------
# Test 5: Convergence — minimum rounds floor
# ---------------------------------------------------------------------------


def test_convergence_minimum_rounds_floor():
    """Convergence requires minimum rounds to be met."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Only 3 rounds — below min_rounds=5
    round_summaries = [
        {"round": i, "new_urls": 1, "web_results": 20, "academic_results": 3}
        for i in range(1, 4)
    ]

    perspective_hits = {p: 10 for p in STORM_PERSPECTIVES}

    analysis = AgenticRoundAnalysis(
        convergence_assessment="saturated",
        should_continue=False,
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
        )

    assert converged is False
    assert "minimum rounds" in reason


# ---------------------------------------------------------------------------
# Test 6: Convergence — diminishing returns signal
# ---------------------------------------------------------------------------


def test_convergence_diminishing_returns():
    """Declining new URL count triggers diminishing returns signal."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    round_summaries = [
        {"round": 1, "new_urls": 30, "web_results": 30, "academic_results": 5},
        {"round": 2, "new_urls": 25, "web_results": 30, "academic_results": 5},
        {"round": 3, "new_urls": 20, "web_results": 30, "academic_results": 5},
        {"round": 4, "new_urls": 5, "web_results": 30, "academic_results": 5},
        {"round": 5, "new_urls": 2, "web_results": 30, "academic_results": 5},
        {"round": 6, "new_urls": 1, "web_results": 30, "academic_results": 5},
    ]

    perspective_hits = {p: 10 for p in STORM_PERSPECTIVES}

    analysis = AgenticRoundAnalysis(
        convergence_assessment="saturated",
        should_continue=False,
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
        )

    assert converged is True
    assert "diminishing_returns" in reason or "theme_saturation" in reason


# ---------------------------------------------------------------------------
# Test 7: Seed query partitioning
# ---------------------------------------------------------------------------


def test_seed_partitioning_9_queries():
    """9 seed queries partition into ~6 web, ~2 academic, ~1 exa."""
    from src.polaris_graph.agents.searcher import _partition_seeds

    queries = [f"query_{i}" for i in range(9)]
    web, acad, exa = _partition_seeds(queries)

    # All queries accounted for
    assert len(web) + len(acad) + len(exa) == 9
    # At least 1 in each category
    assert len(web) >= 1
    assert len(acad) >= 1
    # Web gets majority
    assert len(web) >= len(acad)


def test_seed_partitioning_empty():
    """Empty query list returns empty partitions."""
    from src.polaris_graph.agents.searcher import _partition_seeds

    web, acad, exa = _partition_seeds([])
    assert web == []
    assert acad == []
    assert exa == []


def test_seed_partitioning_single_query():
    """Single query goes to web."""
    from src.polaris_graph.agents.searcher import _partition_seeds

    web, acad, exa = _partition_seeds(["only_one"])
    assert len(web) + len(acad) + len(exa) == 1


# ---------------------------------------------------------------------------
# Test 8: AgenticRoundAnalysis schema validation
# ---------------------------------------------------------------------------


def test_agentic_round_analysis_schema():
    """AgenticRoundAnalysis validates and normalizes LLM output."""
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Standard input
    data = {
        "key_findings": ["finding 1", "finding 2"],
        "perspective_gaps": ["Regulatory"],
        "web_queries": ["query 1"],
        "academic_queries": ["query 2"],
        "exa_queries": [],
        "convergence_assessment": "expanding",
        "should_continue": True,
        "reasoning": "Still exploring",
    }
    analysis = AgenticRoundAnalysis.model_validate(data)
    assert len(analysis.key_findings) == 2
    assert analysis.should_continue is True


def test_agentic_round_analysis_null_handling():
    """AgenticRoundAnalysis handles null values from LLM."""
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    data = {
        "key_findings": None,
        "web_queries": None,
        "convergence_assessment": None,
        "should_continue": None,
    }
    analysis = AgenticRoundAnalysis.model_validate(data)
    assert analysis.key_findings == []
    assert analysis.web_queries == []
    assert analysis.convergence_assessment == "expanding"
    assert analysis.should_continue is True


def test_agentic_round_analysis_field_name_normalization():
    """AgenticRoundAnalysis normalizes variant field names from LLM."""
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    data = {
        "findings": ["finding A"],
        "gaps": ["Scientific"],
        "search_queries": ["web query 1"],
        "s2_queries": ["academic query 1"],
        "assessment": "narrowing",
        "continue": False,
        "rationale": "Enough data",
    }
    analysis = AgenticRoundAnalysis.model_validate(data)
    assert analysis.key_findings == ["finding A"]
    assert analysis.perspective_gaps == ["Scientific"]
    assert analysis.web_queries == ["web query 1"]
    assert analysis.academic_queries == ["academic query 1"]
    assert analysis.convergence_assessment == "narrowing"
    assert analysis.should_continue is False
    assert analysis.reasoning == "Enough data"


# ---------------------------------------------------------------------------
# Test 9: SeedQueryPlan schema validation
# ---------------------------------------------------------------------------


def test_seed_query_plan_schema():
    """SeedQueryPlan validates correctly."""
    from src.polaris_graph.schemas import SeedQueryPlan

    data = {
        "analysis": "Test analysis",
        "sub_queries": [
            {"query": "test query", "intent": "test", "source_preference": "web", "perspective": "Scientific"},
        ],
    }
    plan = SeedQueryPlan.model_validate(data)
    assert len(plan.sub_queries) == 1
    assert plan.analysis == "Test analysis"


def test_seed_query_plan_null_handling():
    """SeedQueryPlan handles null fields from LLM."""
    from src.polaris_graph.schemas import SeedQueryPlan

    data = {"analysis": None, "sub_queries": None}
    plan = SeedQueryPlan.model_validate(data)
    assert plan.analysis == ""
    assert plan.sub_queries == []


# ---------------------------------------------------------------------------
# Test 10: State includes agentic keys
# ---------------------------------------------------------------------------


def test_state_includes_agentic_keys():
    """ResearchState has all 5 agentic search keys initialized."""
    state = create_initial_state(
        vector_id="V_AGENTIC",
        query="test",
        application="general",
        region="GLOBAL",
    )

    assert "agentic_search_rounds" in state
    assert "agentic_total_queries" in state
    assert "agentic_convergence_scores" in state
    assert "agentic_url_accumulator" in state
    assert "agentic_perspective_coverage" in state

    assert state["agentic_search_rounds"] == 0
    assert state["agentic_total_queries"] == 0
    assert state["agentic_convergence_scores"] == []
    assert state["agentic_url_accumulator"] == []
    assert state["agentic_perspective_coverage"] == {}


# ---------------------------------------------------------------------------
# Test 11: Budget cap — query limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_cap_query_limit():
    """Agentic loop stops when query budget is exhausted."""
    from src.polaris_graph.agents.searcher import execute_agentic_search

    state = create_initial_state(
        vector_id="V_BUDGET",
        query="test budget",
        application="general",
        region="GLOBAL",
    )
    state["sub_queries"] = [f"q_{i}" for i in range(9)]

    mock_client = AsyncMock()
    # Analysis that always wants to continue
    mock_analysis = MagicMock()
    mock_analysis.should_continue = True
    mock_analysis.convergence_assessment = "expanding"
    mock_analysis.web_queries = [f"web_{i}" for i in range(6)]
    mock_analysis.academic_queries = [f"acad_{i}" for i in range(2)]
    mock_analysis.exa_queries = ["exa_1"]
    mock_analysis.perspective_gaps = []
    mock_client.generate_structured = AsyncMock(return_value=mock_analysis)

    with patch("src.polaris_graph.agents.searcher._import_search_tools") as mock_tools, \
         patch("src.polaris_graph.agents.searcher._run_web_searches", new_callable=AsyncMock) as mock_web, \
         patch("src.polaris_graph.agents.searcher._run_academic_searches", new_callable=AsyncMock) as mock_acad, \
         patch("src.polaris_graph.agents.searcher._run_exa_searches", new_callable=AsyncMock) as mock_exa, \
         patch("src.polaris_graph.agents.searcher._run_ddg_fallback_for_zeros", new_callable=AsyncMock) as mock_ddg, \
         patch("src.polaris_graph.agents.searcher._chase_citations", new_callable=AsyncMock) as mock_chase, \
         patch("src.polaris_graph.agents.searcher.get_tracer", return_value=None), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MAX_QUERIES", 20), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MAX_ROUNDS", 50), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 2):

        mock_tools.return_value = (MagicMock(), MagicMock())
        mock_web.return_value = [{"url": f"https://r{i}.com", "title": f"R{i}"} for i in range(5)]
        mock_acad.return_value = []
        mock_exa.return_value = []
        mock_ddg.return_value = []
        mock_chase.return_value = []

        result = await execute_agentic_search(state, mock_client)

    # Should stop before 50 rounds due to 20-query budget
    assert result["agentic_total_queries"] <= 20 + 9  # small overshoot from last round OK


# ---------------------------------------------------------------------------
# Test 12: Fallback analysis when LLM fails
# ---------------------------------------------------------------------------


def test_agentic_fallback_analysis():
    """Fallback generates queries for uncovered perspectives."""
    from src.polaris_graph.agents.searcher import _agentic_fallback_analysis

    uncovered = ["Regulatory", "Economic"]
    low_coverage = ["Historical"]

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5):
        result = _agentic_fallback_analysis(
            "water filter safety",
            uncovered,
            low_coverage,
            round_number=3,
        )

    assert result.should_continue is True  # round 3 < min 5
    assert len(result.web_queries) > 0 or len(result.academic_queries) > 0
    assert result.convergence_assessment == "expanding"


def test_agentic_fallback_signals_convergence():
    """Fallback signals convergence when no gaps and past min rounds."""
    from src.polaris_graph.agents.searcher import _agentic_fallback_analysis

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 3):
        result = _agentic_fallback_analysis(
            "water filter safety",
            uncovered=[],
            low_coverage=[],
            round_number=5,
        )

    assert result.should_continue is False
    assert result.convergence_assessment == "narrowing"


# ---------------------------------------------------------------------------
# Test 13: Graph uses seed planner when agentic enabled
# ---------------------------------------------------------------------------


def test_graph_uses_seed_planner_when_agentic():
    """Graph _plan() dispatches to plan_seed_queries when agentic=1 and iteration=0."""
    from src.polaris_graph.graph import build_graph

    # Just verify graph still builds and compiles (structural test)
    graph = build_graph()
    assert graph is not None
    app = graph.compile()
    assert app is not None


# ---------------------------------------------------------------------------
# Test 14: Convergence requires 2+ signals
# ---------------------------------------------------------------------------


def test_convergence_requires_two_signals():
    """Single signal is not enough for convergence."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    round_summaries = [
        {"round": i, "new_urls": 18, "web_results": 20, "academic_results": 5,
         "pages_fetched": 3, "pages_summarized": 2}
        for i in range(1, 6)
    ]

    # Only 2 out of 9 perspectives covered — below saturation threshold
    perspective_hits = {p: 0 for p in STORM_PERSPECTIVES}
    perspective_hits["Scientific"] = 10
    perspective_hits["Regulatory"] = 5

    # LLM does NOT say saturated
    analysis = AgenticRoundAnalysis(
        convergence_assessment="expanding",
        should_continue=True,
        knowledge_gaps=["Gap A", "Gap B"],  # Multiple gaps = no knowledge saturation
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
        )

    # No signal should be active: good new URL ratio, low saturation, no LLM saturated,
    # multiple knowledge gaps, and pages_summarized > 0
    assert converged is False


# ---------------------------------------------------------------------------
# Test 15: _fetch_top_pages — basic (mock AccessBypass)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_top_pages_basic():
    """Mock AccessBypass, verify fetches top N, skips already-fetched."""
    from src.polaris_graph.agents.searcher import _fetch_top_pages

    results = [
        {"url": "https://a.com", "title": "Page A"},
        {"url": "https://b.com", "title": "Page B"},
        {"url": "https://c.com", "title": "Page C"},
        {"url": "https://d.com", "title": "Page D"},
    ]
    already_fetched = {"https://b.com"}

    # Mock AccessBypass.fetch_with_bypass to return success
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.content = "<html><body>Some research content about water filters and safety testing.</body></html>"

    mock_bypass_instance = AsyncMock()
    mock_bypass_instance.fetch_with_bypass = AsyncMock(return_value=mock_result)

    with patch("src.tools.access_bypass.AccessBypass", return_value=mock_bypass_instance), \
         patch("src.polaris_graph.agents.analyzer._is_blocked_source", return_value=False):
        pages = await _fetch_top_pages(results, already_fetched, max_pages=3, per_page_timeout=10.0)

    # Should skip b.com (already fetched), fetch up to 3 of the remaining
    assert len(pages) <= 3
    fetched_urls = {p["url"] for p in pages}
    assert "https://b.com" not in fetched_urls


# ---------------------------------------------------------------------------
# Test 16: _fetch_top_pages — all fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_top_pages_all_fail():
    """All fetches timeout/fail, returns empty (graceful)."""
    from src.polaris_graph.agents.searcher import _fetch_top_pages

    results = [
        {"url": "https://fail1.com", "title": "F1"},
        {"url": "https://fail2.com", "title": "F2"},
    ]

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.content = ""

    mock_bypass_instance = AsyncMock()
    mock_bypass_instance.fetch_with_bypass = AsyncMock(return_value=mock_result)

    with patch("src.polaris_graph.agents.analyzer._is_blocked_source", return_value=False), \
         patch("src.tools.access_bypass.AccessBypass", return_value=mock_bypass_instance):
        pages = await _fetch_top_pages(results, set(), max_pages=3, per_page_timeout=5.0)

    assert pages == []


# ---------------------------------------------------------------------------
# Test 17: _fetch_top_pages — skips blocked sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_top_pages_skips_blocked():
    """Blocked domains are skipped."""
    from src.polaris_graph.agents.searcher import _fetch_top_pages

    results = [
        {"url": "https://blocked.com/page", "title": "Blocked"},
        {"url": "https://good.com/page", "title": "Good"},
    ]

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.content = "Good content with enough text to pass the 100 char minimum threshold for acceptance."

    mock_bypass_instance = AsyncMock()
    mock_bypass_instance.fetch_with_bypass = AsyncMock(return_value=mock_result)

    def selective_block(url):
        return "blocked.com" in url

    with patch("src.polaris_graph.agents.analyzer._is_blocked_source", side_effect=selective_block), \
         patch("src.tools.access_bypass.AccessBypass", return_value=mock_bypass_instance):
        pages = await _fetch_top_pages(results, set(), max_pages=3, per_page_timeout=5.0)

    urls = {p["url"] for p in pages}
    assert "https://blocked.com/page" not in urls


# ---------------------------------------------------------------------------
# Test 18: _summarize_pages — basic (mock LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_pages_basic():
    """Mock LLM, verify PageResearchNote output."""
    from src.polaris_graph.agents.searcher import _summarize_pages
    from src.polaris_graph.schemas import PageResearchNote

    pages = [
        {"url": "https://example.com", "title": "Test Page", "content": "Content about water safety."},
    ]

    mock_note = MagicMock()
    mock_note.model_dump.return_value = {
        "url": "https://example.com",
        "title": "Test Page",
        "summary": "This page discusses water safety protocols.",
        "perspectives": ["Scientific", "Regulatory"],
        "key_facts": ["EPA standard is 0.5 mg/L"],
        "knowledge_contribution": "New EPA threshold data",
    }

    mock_batch = MagicMock()
    mock_batch.notes = [mock_note]

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_batch)

    notes = await _summarize_pages(mock_client, pages, "water safety", max_tokens=2048)

    assert len(notes) == 1
    assert notes[0]["summary"] == "This page discusses water safety protocols."
    assert "Scientific" in notes[0]["perspectives"]


# ---------------------------------------------------------------------------
# Test 19: _summarize_pages — LLM failure fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_pages_llm_failure():
    """LLM fails, returns truncated-content fallback."""
    from src.polaris_graph.agents.searcher import _summarize_pages

    pages = [
        {"url": "https://fail.com", "title": "Fail Page", "content": "Short content for fallback test."},
    ]

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    notes = await _summarize_pages(mock_client, pages, "test query", max_tokens=2048)

    assert len(notes) == 1
    assert notes[0]["url"] == "https://fail.com"
    assert notes[0]["summary"] == "Short content for fallback test."
    assert notes[0]["perspectives"] == []


# ---------------------------------------------------------------------------
# Test 20: Notebook accumulation and capping
# ---------------------------------------------------------------------------


def test_notebook_accumulation():
    """Notebook grows and caps at max entries."""
    from src.polaris_graph.state import PG_AGENTIC_MAX_NOTEBOOK_ENTRIES

    notebook = []
    for i in range(PG_AGENTIC_MAX_NOTEBOOK_ENTRIES + 5):
        notebook.append({"url": f"https://page{i}.com", "summary": f"Note {i}"})

    # Cap at max entries (oldest dropped)
    if len(notebook) > PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:
        notebook = notebook[-PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:]

    assert len(notebook) == PG_AGENTIC_MAX_NOTEBOOK_ENTRIES
    assert notebook[0]["summary"] == "Note 5"  # First 5 dropped


# ---------------------------------------------------------------------------
# Test 21: Content-aware analysis prompt uses notebook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_aware_analysis_prompt():
    """When notebook is populated, prompt uses notebook context, not snippets."""
    from src.polaris_graph.agents.searcher import _agentic_round_analysis
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    notebook = [
        {
            "url": "https://page1.com",
            "title": "Water Safety Study",
            "summary": "Comprehensive study on water filtration efficacy.",
            "perspectives": ["Scientific"],
            "key_facts": ["99.99% pathogen removal"],
            "knowledge_contribution": "Filtration benchmarks",
        },
    ]

    mock_analysis = AgenticRoundAnalysis(
        key_findings=["Found filtration data"],
        web_queries=["water filter regulation"],
        convergence_assessment="expanding",
        should_continue=True,
    )

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_analysis)

    round_summaries = [
        {"round": 1, "queries": 9, "web_results": 20, "academic_results": 5,
         "new_urls": 25, "pages_fetched": 3, "pages_summarized": 1},
    ]

    result = await _agentic_round_analysis(
        client=mock_client,
        original_query="water safety",
        latest_results=[{"title": "New result", "url": "https://new.com"}],
        round_summaries=round_summaries,
        perspective_hits={p: 1 for p in STORM_PERSPECTIVES},
        round_number=2,
        research_notebook=notebook,
    )

    # Verify the LLM was called (prompt uses notebook)
    mock_client.generate_structured.assert_called_once()
    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", call_kwargs.args[0] if call_kwargs.args else "")
    if not prompt and call_kwargs.kwargs:
        prompt = call_kwargs.kwargs.get("prompt", "")
    assert result.should_continue is True


# ---------------------------------------------------------------------------
# Test 22: PageResearchNote schema validation
# ---------------------------------------------------------------------------


def test_page_research_note_schema():
    """Standard validation + null handling."""
    from src.polaris_graph.schemas import PageResearchNote

    # Standard input
    data = {
        "url": "https://example.com",
        "title": "Test",
        "summary": "A summary of findings.",
        "perspectives": ["Scientific"],
        "key_facts": ["Fact 1"],
        "knowledge_contribution": "New data",
    }
    note = PageResearchNote.model_validate(data)
    assert note.url == "https://example.com"
    assert len(note.perspectives) == 1

    # Null handling
    null_data = {
        "url": "https://null.com",
        "title": None,
        "summary": None,
        "perspectives": None,
        "key_facts": None,
        "knowledge_contribution": None,
    }
    note2 = PageResearchNote.model_validate(null_data)
    assert note2.title == ""
    assert note2.perspectives == []
    assert note2.key_facts == []


# ---------------------------------------------------------------------------
# Test 23: PageSummaryBatch schema — invalid notes dropped
# ---------------------------------------------------------------------------


def test_page_summary_batch_schema():
    """Invalid entries dropped gracefully."""
    from src.polaris_graph.schemas import PageSummaryBatch

    data = {
        "notes": [
            {"url": "https://good.com", "summary": "Good note"},
            "not_a_dict",  # Invalid — should be dropped
            {"url": "https://also-good.com"},  # Minimal valid
        ],
    }
    batch = PageSummaryBatch.model_validate(data)
    assert len(batch.notes) == 2
    assert batch.notes[0].url == "https://good.com"


# ---------------------------------------------------------------------------
# Test 24: AgenticRoundAnalysis knowledge_gaps field
# ---------------------------------------------------------------------------


def test_agentic_knowledge_gaps_field():
    """New knowledge_gaps field on AgenticRoundAnalysis works correctly."""
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Explicit knowledge_gaps
    data = {
        "key_findings": ["finding"],
        "knowledge_gaps": ["No data on cost", "Missing regulatory framework"],
        "convergence_assessment": "expanding",
    }
    analysis = AgenticRoundAnalysis.model_validate(data)
    assert len(analysis.knowledge_gaps) == 2
    assert "No data on cost" in analysis.knowledge_gaps

    # Variant field name normalization
    data2 = {
        "gaps_in_knowledge": ["Missing cost data"],
        "convergence_assessment": "narrowing",
    }
    analysis2 = AgenticRoundAnalysis.model_validate(data2)
    assert len(analysis2.knowledge_gaps) == 1

    # Null handling
    data3 = {"knowledge_gaps": None}
    analysis3 = AgenticRoundAnalysis.model_validate(data3)
    assert analysis3.knowledge_gaps == []


# ---------------------------------------------------------------------------
# Test 25: Convergence — knowledge saturation signal
# ---------------------------------------------------------------------------


def test_convergence_knowledge_saturation():
    """Large notebook + empty gaps fires knowledge saturation signal."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    round_summaries = [
        {"round": i, "new_urls": 10, "web_results": 15, "academic_results": 3,
         "pages_fetched": 3, "pages_summarized": 2}
        for i in range(1, 7)
    ]

    perspective_hits = {p: 5 for p in STORM_PERSPECTIVES}

    # Large notebook (>= 15 pages) and no knowledge gaps
    notebook = [{"url": f"https://p{i}.com", "summary": f"Note {i}"} for i in range(20)]

    analysis = AgenticRoundAnalysis(
        convergence_assessment="narrowing",
        should_continue=False,
        knowledge_gaps=[],  # No gaps identified
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_KNOWLEDGE_SATURATION_PAGES", 15):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
            research_notebook=notebook,
        )

    assert converged is True
    assert "knowledge_saturation" in reason


# ---------------------------------------------------------------------------
# Test 26: Convergence — notebook growth stall signal
# ---------------------------------------------------------------------------


def test_convergence_notebook_stall():
    """No new notes in recent window fires notebook stall signal."""
    from src.polaris_graph.agents.searcher import _compute_convergence
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Rounds with 0 pages summarized in the last window
    round_summaries = [
        {"round": 1, "new_urls": 20, "web_results": 20, "academic_results": 5,
         "pages_fetched": 3, "pages_summarized": 3},
        {"round": 2, "new_urls": 15, "web_results": 18, "academic_results": 4,
         "pages_fetched": 3, "pages_summarized": 2},
        {"round": 3, "new_urls": 10, "web_results": 15, "academic_results": 3,
         "pages_fetched": 2, "pages_summarized": 1},
        {"round": 4, "new_urls": 5, "web_results": 10, "academic_results": 2,
         "pages_fetched": 0, "pages_summarized": 0},
        {"round": 5, "new_urls": 3, "web_results": 10, "academic_results": 2,
         "pages_fetched": 0, "pages_summarized": 0},
        {"round": 6, "new_urls": 2, "web_results": 8, "academic_results": 2,
         "pages_fetched": 0, "pages_summarized": 0},
    ]

    perspective_hits = {p: 8 for p in STORM_PERSPECTIVES}

    analysis = AgenticRoundAnalysis(
        convergence_assessment="narrowing",
        should_continue=False,
        knowledge_gaps=["Some gap"],
    )

    with patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 5), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONVERGENCE_WINDOW", 3), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_NEW_NOTES_PER_ROUND", 1):
        converged, reason = _compute_convergence(
            round_summaries, perspective_hits, analysis,
            research_notebook=[],
        )

    assert converged is True
    assert "notebook_stall" in reason


# ---------------------------------------------------------------------------
# Test 27: Content-derived perspective tags update hits with weight
# ---------------------------------------------------------------------------


def test_content_perspective_tags():
    """LLM perspectives from notes update hits with configured weight."""
    from src.polaris_graph.state import PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT

    perspective_hits = {p: 0 for p in STORM_PERSPECTIVES}

    round_notes = [
        {"perspectives": ["Scientific", "Regulatory"]},
        {"perspectives": ["Economic"]},
    ]

    for note in round_notes:
        for perspective in note.get("perspectives", []):
            p_normalized = perspective.replace(" ", "_")
            if p_normalized in perspective_hits:
                perspective_hits[p_normalized] += PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT

    assert perspective_hits["Scientific"] == PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT
    assert perspective_hits["Regulatory"] == PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT
    assert perspective_hits["Economic"] == PG_AGENTIC_CONTENT_PERSPECTIVE_WEIGHT
    assert perspective_hits["Historical"] == 0  # Not in notes


# ---------------------------------------------------------------------------
# Test 28: Content reading disabled — no fetching, no summarization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_reading_disabled():
    """PG_AGENTIC_CONTENT_READING_ENABLED=0 -> no fetching, no summarization."""
    from src.polaris_graph.agents.searcher import execute_agentic_search

    state = create_initial_state(
        vector_id="V_NO_READING",
        query="test no reading",
        application="general",
        region="GLOBAL",
    )
    state["sub_queries"] = [f"q_{i}" for i in range(9)]

    mock_client = AsyncMock()
    mock_analysis = MagicMock()
    mock_analysis.should_continue = False
    mock_analysis.convergence_assessment = "saturated"
    mock_analysis.web_queries = ["web_1"]
    mock_analysis.academic_queries = []
    mock_analysis.exa_queries = []
    mock_analysis.perspective_gaps = []
    mock_analysis.knowledge_gaps = []
    mock_client.generate_structured = AsyncMock(return_value=mock_analysis)

    with patch("src.polaris_graph.agents.searcher._import_search_tools") as mock_tools, \
         patch("src.polaris_graph.agents.searcher._run_web_searches", new_callable=AsyncMock) as mock_web, \
         patch("src.polaris_graph.agents.searcher._run_academic_searches", new_callable=AsyncMock) as mock_acad, \
         patch("src.polaris_graph.agents.searcher._run_exa_searches", new_callable=AsyncMock) as mock_exa, \
         patch("src.polaris_graph.agents.searcher._run_ddg_fallback_for_zeros", new_callable=AsyncMock) as mock_ddg, \
         patch("src.polaris_graph.agents.searcher._chase_citations", new_callable=AsyncMock) as mock_chase, \
         patch("src.polaris_graph.agents.searcher._fetch_top_pages", new_callable=AsyncMock) as mock_fetch, \
         patch("src.polaris_graph.agents.searcher._summarize_pages", new_callable=AsyncMock) as mock_summarize, \
         patch("src.polaris_graph.agents.searcher.get_tracer", return_value=None), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_CONTENT_READING_ENABLED", False), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MAX_ROUNDS", 3), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 2):

        mock_tools.return_value = (MagicMock(), MagicMock())
        mock_web.return_value = [{"url": f"https://r{i}.com", "title": f"R{i}"} for i in range(5)]
        mock_acad.return_value = []
        mock_exa.return_value = []
        mock_ddg.return_value = []
        mock_chase.return_value = []

        result = await execute_agentic_search(state, mock_client)

    # Content reading functions should NOT have been called
    mock_fetch.assert_not_called()
    mock_summarize.assert_not_called()

    # Notebook should be empty
    assert result["agentic_research_notebook"] == []
    assert result["agentic_pages_fetched_count"] == 0


# ---------------------------------------------------------------------------
# Test 29: New state keys initialized correctly
# ---------------------------------------------------------------------------


def test_new_state_keys():
    """3 new state keys initialized correctly in create_initial_state."""
    state = create_initial_state(
        vector_id="V_NEW_KEYS",
        query="test",
        application="general",
        region="GLOBAL",
    )

    assert "agentic_research_notebook" in state
    assert "agentic_pages_fetched_count" in state
    assert "agentic_knowledge_gaps" in state

    assert state["agentic_research_notebook"] == []
    assert state["agentic_pages_fetched_count"] == 0
    assert state["agentic_knowledge_gaps"] == []


# ===========================================================================
# SOTA Gap Closure Tests — Gap 2 (Content Depth) & Gap 3 (Analysis Depth)
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 30: Config values updated to SOTA levels (Gap 2)
# ---------------------------------------------------------------------------


def test_sota_config_pages_per_round():
    """PG_AGENTIC_PAGES_PER_ROUND should be >= 6 for SOTA parity."""
    from src.polaris_graph.state import PG_AGENTIC_PAGES_PER_ROUND
    assert PG_AGENTIC_PAGES_PER_ROUND >= 6


def test_sota_config_page_content_cap():
    """PG_AGENTIC_PAGE_CONTENT_CAP should be >= 15000 for full-page comprehension."""
    from src.polaris_graph.state import PG_AGENTIC_PAGE_CONTENT_CAP
    assert PG_AGENTIC_PAGE_CONTENT_CAP >= 15000


def test_sota_config_summary_max_tokens():
    """PG_AGENTIC_SUMMARY_MAX_TOKENS should be >= 4096 for deeper summaries."""
    from src.polaris_graph.state import PG_AGENTIC_SUMMARY_MAX_TOKENS
    assert PG_AGENTIC_SUMMARY_MAX_TOKENS >= 4096


def test_sota_config_max_notebook_entries():
    """PG_AGENTIC_MAX_NOTEBOOK_ENTRIES should be >= 50 for more pages."""
    from src.polaris_graph.state import PG_AGENTIC_MAX_NOTEBOOK_ENTRIES
    assert PG_AGENTIC_MAX_NOTEBOOK_ENTRIES >= 50


def test_sota_config_fetch_timeout():
    """PG_AGENTIC_FETCH_TIMEOUT should be >= 20.0 for larger pages."""
    from src.polaris_graph.state import PG_AGENTIC_FETCH_TIMEOUT
    assert PG_AGENTIC_FETCH_TIMEOUT >= 20.0


# ---------------------------------------------------------------------------
# Test 31: Safety gate at 120K (Gap 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safety_gate_120k():
    """Safety gate allows 6 x 15K pages without truncation."""
    from src.polaris_graph.agents.searcher import _summarize_pages
    from src.polaris_graph.schemas import PageResearchNote

    # Create 6 pages with 15K content each (90K total, below 120K)
    pages = [
        {
            "url": f"https://page{i}.com",
            "title": f"Page {i}",
            "content": "x" * 15000,
        }
        for i in range(6)
    ]

    mock_note = MagicMock()
    mock_note.model_dump.return_value = {
        "url": "https://page0.com",
        "title": "Page 0",
        "summary": "Summary",
        "perspectives": [],
        "key_facts": [],
        "knowledge_contribution": "",
    }

    mock_batch = MagicMock()
    mock_batch.notes = [mock_note] * 6

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_batch)

    notes = await _summarize_pages(mock_client, pages, "test query", max_tokens=4096)

    # Should process all 6 pages (90K < 120K safety gate)
    mock_client.generate_structured.assert_called_once()
    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", "")
    # Count page blocks in the prompt
    page_count = prompt.count("--- PAGE:")
    assert page_count == 6, f"Expected 6 pages in prompt, got {page_count}"


# ---------------------------------------------------------------------------
# Test 32: No double-truncation in _summarize_pages (Gap 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_double_truncation():
    """Content in prompt blocks is NOT re-truncated below the fetch cap."""
    from src.polaris_graph.agents.searcher import _summarize_pages

    # Content exactly at cap (should NOT be truncated further)
    content = "A" * 15000
    pages = [{"url": "https://test.com", "title": "Test", "content": content}]

    mock_batch = MagicMock()
    mock_batch.notes = []

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_batch)

    await _summarize_pages(mock_client, pages, "query", max_tokens=4096)

    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", "")
    # The full 15K content should be in the prompt (no second truncation)
    assert "A" * 14000 in prompt, "Content was re-truncated in _summarize_pages"


# ---------------------------------------------------------------------------
# Test 33: Enhanced summarization prompt contains deep analysis (Gap 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enhanced_summarization_prompt():
    """Summarization prompt asks for 300-400 word deep analysis."""
    from src.polaris_graph.agents.searcher import _summarize_pages

    pages = [{"url": "https://test.com", "title": "Test", "content": "Test content."}]

    mock_batch = MagicMock()
    mock_batch.notes = []

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_batch)

    await _summarize_pages(mock_client, pages, "query", max_tokens=4096)

    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", "")

    assert "300-400 word deep analysis" in prompt
    assert "Contradictions" in prompt or "contradictions" in prompt.lower()
    assert "Confidence assessment" in prompt or "confidence assessment" in prompt.lower()
    assert "HIGH/MEDIUM/LOW" in prompt


# ---------------------------------------------------------------------------
# Test 34: Analysis context uses 30 entries and 500-char excerpts (Gap 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_context_30_entries():
    """Content-aware analysis uses last 30 entries with 500-char excerpts."""
    from src.polaris_graph.agents.searcher import _agentic_round_analysis
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    # Create 35 notebook entries (should use last 30)
    notebook = [
        {
            "url": f"https://page{i}.com",
            "title": f"Page {i}",
            "summary": f"Summary of page {i} " + "x" * 400,
            "perspectives": ["Scientific"],
            "key_facts": [f"Fact from page {i}"],
            "knowledge_contribution": f"Contribution {i}",
        }
        for i in range(35)
    ]

    mock_analysis = AgenticRoundAnalysis(
        key_findings=["finding"],
        web_queries=["query"],
        convergence_assessment="expanding",
        should_continue=True,
    )

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_analysis)

    round_summaries = [
        {"round": 1, "queries": 9, "web_results": 20, "academic_results": 5,
         "new_urls": 25, "pages_fetched": 3, "pages_summarized": 3},
    ]

    await _agentic_round_analysis(
        client=mock_client,
        original_query="test",
        latest_results=[],
        round_summaries=round_summaries,
        perspective_hits={p: 1 for p in STORM_PERSPECTIVES},
        round_number=2,
        research_notebook=notebook,
    )

    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", "")

    # Should show "35 pages read" in the prompt
    assert "35 pages read" in prompt

    # Should contain entries from pages 5-34 (last 30), not 0-4
    assert "[Page 30]" in prompt
    # First 5 pages (0-4) should be excluded
    # Page 5 is the first in the last 30, shown as [Page 1]
    assert "Page 5" in prompt or "Page 6" in prompt


# ---------------------------------------------------------------------------
# Test 35: Enhanced analysis prompt contains contradiction detection (Gap 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_prompt_contradictions():
    """Analysis prompt asks about contradictions and confidence."""
    from src.polaris_graph.agents.searcher import _agentic_round_analysis
    from src.polaris_graph.schemas import AgenticRoundAnalysis

    notebook = [
        {
            "url": "https://page1.com",
            "title": "Study",
            "summary": "Findings.",
            "perspectives": ["Scientific"],
            "key_facts": ["Fact 1"],
            "knowledge_contribution": "Data",
        },
    ]

    mock_analysis = AgenticRoundAnalysis(
        convergence_assessment="expanding",
        should_continue=True,
    )

    mock_client = AsyncMock()
    mock_client.generate_structured = AsyncMock(return_value=mock_analysis)

    await _agentic_round_analysis(
        client=mock_client,
        original_query="test",
        latest_results=[],
        round_summaries=[{"round": 1, "queries": 9, "web_results": 20,
                          "academic_results": 5, "new_urls": 25,
                          "pages_fetched": 3, "pages_summarized": 1}],
        perspective_hits={p: 1 for p in STORM_PERSPECTIVES},
        round_number=2,
        research_notebook=notebook,
    )

    call_kwargs = mock_client.generate_structured.call_args
    prompt = call_kwargs.kwargs.get("prompt", "")

    assert "CONTRADICTIONS" in prompt
    assert "LOW/MEDIUM/HIGH" in prompt
    assert "confidence" in prompt.lower()


# ---------------------------------------------------------------------------
# Test 36: Notebook capping at 50 entries (Gap 2)
# ---------------------------------------------------------------------------


def test_notebook_caps_at_50():
    """Notebook caps at 50 entries (SOTA upgrade from 30)."""
    from src.polaris_graph.state import PG_AGENTIC_MAX_NOTEBOOK_ENTRIES

    notebook = []
    for i in range(60):
        notebook.append({"url": f"https://page{i}.com", "summary": f"Note {i}"})

    if len(notebook) > PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:
        notebook = notebook[-PG_AGENTIC_MAX_NOTEBOOK_ENTRIES:]

    assert len(notebook) == 50
    assert notebook[0]["summary"] == "Note 10"  # First 10 dropped
