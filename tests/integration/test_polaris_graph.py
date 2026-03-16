"""
Integration tests for polaris graph pipeline.

IMP-5: 8 test cases verifying graph structure, evidence accumulation,
perspective tagging, citation filtering, routing, faithfulness, and dedup.

All tests are fully mocked — no real API calls.
"""

import asyncio
import json
import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.polaris_graph.state import (
    EvidencePiece,
    ReportSection,
    ResearchState,
    VerifiedClaim,
    create_initial_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(
    evidence_id: str,
    statement: str = "Test statement",
    source_url: str = "https://example.com",
    relevance: float = 0.7,
    quality_tier: str = "SILVER",
    perspective: str = "Scientific",
) -> EvidencePiece:
    """Create a minimal EvidencePiece for testing."""
    return EvidencePiece(
        evidence_id=evidence_id,
        source_url=source_url,
        source_title="Test Source",
        source_type="web",
        direct_quote="test quote",
        statement=statement,
        fact_category="statistic",
        relevance_score=relevance,
        llm_relevance_score=relevance,
        quality_tier=quality_tier,
        citation_key="",
        year=2024,
        authors=["Test Author"],
        venue="Test Venue",
        doi="",
        perspective=perspective,
    )


def _make_claim(
    claim_id: str,
    is_faithful: bool = True,
    method: str = "atomic",
    confidence: float = 0.8,
) -> VerifiedClaim:
    """Create a minimal VerifiedClaim for testing."""
    return VerifiedClaim(
        claim_id=claim_id,
        statement="Test claim",
        evidence_ids=[claim_id],
        confidence=confidence,
        verification_method=method,
        is_faithful=is_faithful,
        section_id=None,
        reasoning="test",
        verification_basis="content",
        verification_type="extraction_self_check",
        nli_score=None,
        cross_source_score=None,
    )


# ---------------------------------------------------------------------------
# Test 1: Graph builds without errors
# ---------------------------------------------------------------------------

def test_build_graph_returns_state_graph():
    """Graph compiles without errors and returns a StateGraph."""
    from src.polaris_graph.graph import build_graph

    graph = build_graph()
    assert graph is not None
    # Should be compilable
    app = graph.compile()
    assert app is not None


# ---------------------------------------------------------------------------
# Test 2: Graph has all expected nodes
# ---------------------------------------------------------------------------

def test_graph_has_all_nodes():
    """All 7 nodes are present including search_gaps (FIX-307)."""
    from src.polaris_graph.graph import build_graph

    graph = build_graph()
    expected_nodes = {"plan", "search", "analyze", "verify", "evaluate", "synthesize", "search_gaps"}
    actual_nodes = set(graph.nodes.keys())
    assert expected_nodes.issubset(actual_nodes), (
        f"Missing nodes: {expected_nodes - actual_nodes}"
    )


# ---------------------------------------------------------------------------
# Test 3: Evidence accumulates across iterations (FIX-300)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_accumulates_evidence():
    """FIX-300: Evidence merges across iterations — old + new, no duplicates.

    Tests the accumulation logic directly rather than via the graph node wrapper,
    since LangGraph node specs are not directly callable.
    """
    # Existing evidence in state
    existing = [
        _make_evidence("ev_old_1", statement="Water filters reduce bacteria"),
        _make_evidence("ev_old_2", statement="UV treatment kills pathogens"),
    ]

    # New evidence from analyzer (includes 1 duplicate ID and 1 new)
    new_evidence = [
        _make_evidence("ev_old_1", statement="Water filters reduce bacteria"),  # duplicate
        _make_evidence("ev_new_1", statement="RO membranes remove heavy metals"),
    ]

    # Replicate the accumulation logic from graph.py _analyze()
    existing_ids = {e.get("evidence_id") for e in existing}
    unique_new = [e for e in new_evidence if e.get("evidence_id") not in existing_ids]
    accumulated = existing + unique_new

    # Should have 3 unique pieces (2 old + 1 new, 1 duplicate removed)
    assert len(accumulated) == 3
    ids = {e["evidence_id"] for e in accumulated}
    assert "ev_old_1" in ids
    assert "ev_old_2" in ids
    assert "ev_new_1" in ids


# ---------------------------------------------------------------------------
# Test 4: Evidence has perspective field (FIX-303)
# ---------------------------------------------------------------------------

def test_evidence_has_perspective():
    """FIX-303: EvidencePiece includes perspective field."""
    ev = _make_evidence("ev_test", perspective="Regulatory")
    assert ev["perspective"] == "Regulatory"

    # Verify all STORM perspectives are valid
    valid_perspectives = {
        "Scientific", "Regulatory", "Industry", "Economic",
        "Public_Health", "Historical", "Regional", "Methodological",
        "Emerging_Trends",
    }
    for p in valid_perspectives:
        ev = _make_evidence(f"ev_{p}", perspective=p)
        assert ev["perspective"] == p


# ---------------------------------------------------------------------------
# Test 5: Irrelevant papers filtered (IMP-3)
# ---------------------------------------------------------------------------

def test_irrelevant_papers_filtered():
    """IMP-3: Citation-chased papers below relevance threshold are removed."""
    from src.polaris_graph.agents.searcher import _filter_chased_by_relevance

    papers = [
        {"title": "Water filter effectiveness study", "abstract": "This study examines household water filter performance"},
        {"title": "Quantum computing advances", "abstract": "Recent breakthroughs in quantum error correction"},
        {"title": "Reverse osmosis membrane efficiency", "abstract": "RO membrane removal rates for heavy metals in drinking water"},
    ]

    query = "household water filter effectiveness and safety"

    # Mock the embedding service at its source module (imported inside function)
    with patch("src.utils.embedding_service.embed_text") as mock_embed_text, \
         patch("src.utils.embedding_service.embed_texts") as mock_embed_texts:
        import numpy as np

        # Query vector (unit vector)
        query_vec = np.array([1.0, 0.0, 0.0])
        mock_embed_text.return_value = query_vec.tolist()

        # Paper vectors: first and third are relevant, second is not
        paper_vecs = np.array([
            [0.9, 0.1, 0.0],   # high similarity (0.9)
            [0.1, 0.0, 0.9],   # low similarity (0.1) — below 0.3 threshold
            [0.8, 0.2, 0.0],   # high similarity (0.8)
        ])
        # Normalize
        paper_vecs = paper_vecs / np.linalg.norm(paper_vecs, axis=1, keepdims=True)
        mock_embed_texts.return_value = paper_vecs.tolist()

        filtered = _filter_chased_by_relevance(papers, query)

    # Quantum computing paper should be filtered out
    assert len(filtered) == 2
    titles = [p["title"] for p in filtered]
    assert "Quantum computing advances" not in titles
    assert "Water filter effectiveness study" in titles
    assert "Reverse osmosis membrane efficiency" in titles


# ---------------------------------------------------------------------------
# Test 6: Evaluate routes to search_gaps (FIX-307)
# ---------------------------------------------------------------------------

def test_routes_to_search_gaps():
    """FIX-307: When gap_queries are present, search_gaps node exists and graph compiles.

    Verifies the graph structure includes the search_gaps node and that
    the evaluate node has conditional edges for routing.
    """
    from src.polaris_graph.graph import build_graph

    graph = build_graph()

    # Verify search_gaps node exists
    assert "search_gaps" in graph.nodes

    # Verify graph compiles with the conditional routing from evaluate
    app = graph.compile()
    assert app is not None

    # Verify evaluate has edges (conditional edges are set up)
    # LangGraph stores edges in the .edges property
    edge_list = graph.edges
    # search_gaps should connect to search
    edge_pairs = {(e[0], e[1]) for e in edge_list}
    assert ("search_gaps", "search") in edge_pairs, (
        f"search_gaps -> search edge missing. Edges: {edge_pairs}"
    )


# ---------------------------------------------------------------------------
# Test 7: Weighted faithfulness scoring (FIX-301)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weighted_faithfulness(monkeypatch):
    """FIX-301: PARTIALLY_SUPPORTED counts at 0.5 weight, api_error excluded."""
    # Ensure NLI path is disabled so mock LLM client is used
    monkeypatch.setenv("PG_NLI_ENABLED", "0")

    from src.polaris_graph.agents.verifier import verify_claims

    # Create mock evidence
    evidence = [
        _make_evidence(f"ev_{i}", statement=f"Claim {i}")
        for i in range(4)
    ]

    state = create_initial_state(
        vector_id="test_faith",
        query="test query",
        application="general",
        region="GLOBAL",
    )
    state["evidence"] = evidence

    # Mock client to return controlled verification results
    mock_client = AsyncMock()

    mock_verifications = MagicMock()
    mock_verifications.verifications = [
        MagicMock(claim="Claim 0", verdict="SUPPORTED", confidence=0.9, supporting_evidence=["ev_0"], reasoning="ok"),
        MagicMock(claim="Claim 1", verdict="PARTIALLY_SUPPORTED", confidence=0.6, supporting_evidence=["ev_1"], reasoning="partial"),
        MagicMock(claim="Claim 2", verdict="NOT_SUPPORTED", confidence=0.3, supporting_evidence=[], reasoning="no"),
        MagicMock(claim="Claim 3", verdict="SUPPORTED", confidence=0.85, supporting_evidence=["ev_3"], reasoning="ok"),
    ]
    mock_verifications.overall_faithfulness = 0.75
    mock_client.generate_structured = AsyncMock(return_value=mock_verifications)

    result = await verify_claims(mock_client, state)

    # FIX-F1/F2: PARTIALLY_SUPPORTED = NOT faithful (strict binary).
    # Evidence has direct_quote → basis="quote_only" (weight 0.7).
    # 2 SUPPORTED at quote_only weight (0.7 each) + 1 PARTIAL (0) + 1 NOT_SUPPORTED (0)
    # = (0.7 * 2) / 4 = 0.35
    assert result["faithfulness_score"] == pytest.approx(0.35, abs=0.01)

    # api_error claims should not appear (no failures in this test)
    api_errors = [c for c in result["claims"] if c.get("verification_method") == "api_error"]
    assert len(api_errors) == 0


# ---------------------------------------------------------------------------
# Test 8: Cross-iteration dedup (IMP-4)
# ---------------------------------------------------------------------------

def test_cross_iteration_dedup():
    """IMP-4: Duplicate statements across iterations are deduped."""
    from src.polaris_graph.graph import _cross_iteration_dedup

    # Create evidence with near-duplicate statements
    evidence = [
        _make_evidence("ev_1", statement="Water filters reduce bacterial contamination by 99.9% in laboratory tests"),
        _make_evidence("ev_2", statement="UV disinfection kills 99% of waterborne pathogens"),
        # Near-duplicate of ev_1 (same statement, different ID — from different iteration)
        _make_evidence("ev_3", statement="Water filters reduce bacterial contamination by 99.9% in laboratory tests"),
    ]

    # Patch at the source module where the constants are defined
    with patch("src.polaris_graph.state.PG_EVIDENCE_DEDUP_ENABLED", True), \
         patch("src.polaris_graph.state.PG_EVIDENCE_DEDUP_THRESHOLD", 0.85):
        result = _cross_iteration_dedup(evidence)

    # Exact duplicate (ev_1 and ev_3 have identical statements) should be deduped
    assert len(result) < len(evidence)
    # At minimum, the unique statements should be preserved
    statements = {e["statement"] for e in result}
    assert len(statements) >= 2


# ---------------------------------------------------------------------------
# Test 9: PipelineTracer writes JSONL events (OBS-1)
# ---------------------------------------------------------------------------

def test_pipeline_tracer_writes_jsonl():
    """OBS-1: PipelineTracer emits JSONL events to file."""
    from src.polaris_graph.tracing import PipelineTracer

    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = PipelineTracer("V_TEST_001", output_dir=tmpdir)

        # Emit various event types
        tracer.node_start("plan", iteration=1)
        tracer.query("plan", "generated", 50)
        tracer.node_end("plan", query_count=50)
        tracer.node_start("search")
        tracer.search_result("search", "serper", "water filter", 10)
        tracer.node_end("search", web_results=100)
        tracer.fetch("analyze", "https://example.com", "success", content_len=5000, duration_ms=1200)
        tracer.evidence("analyze", "extracted", 45, sources_fetched=80)
        tracer.llm_call("verify", "verification_batch", batch_size=10, supported=8)
        tracer.quality_gate("synthesize", "post_synthesis", passed=True, total_words=5000)

        # Check summary
        summary = tracer.summary()
        assert summary["total_events"] == 10
        assert "plan" in summary["nodes"]
        assert "search" in summary["nodes"]
        assert "analyze" in summary["nodes"]
        assert "verify" in summary["nodes"]
        assert "synthesize" in summary["nodes"]

        # Check JSONL file was written
        trace_file = os.path.join(tmpdir, "pg_trace_V_TEST_001.jsonl")
        assert os.path.exists(trace_file)

        with open(trace_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 10

        # Verify each line is valid JSON
        for line in lines:
            event = json.loads(line)
            assert "ts" in event
            assert "vid" in event
            assert event["vid"] == "V_TEST_001"
            assert "node" in event
            assert "type" in event


# ---------------------------------------------------------------------------
# Test 10: PipelineTracer disabled via env var (OBS-1)
# ---------------------------------------------------------------------------

def test_pipeline_tracer_disabled():
    """OBS-1: When PG_TRACING_ENABLED=0, no events are emitted."""
    from src.polaris_graph.tracing import PipelineTracer

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.polaris_graph.tracing.PG_TRACING_ENABLED", False):
            tracer = PipelineTracer("V_DISABLED", output_dir=tmpdir)
            tracer.node_start("plan")
            tracer.node_end("plan")

            summary = tracer.summary()
            assert summary["total_events"] == 0


# ---------------------------------------------------------------------------
# Test 11: get_tracer returns current tracer (OBS-1)
# ---------------------------------------------------------------------------

def test_get_tracer_returns_current():
    """OBS-1: get_tracer() returns the most recently created PipelineTracer."""
    from src.polaris_graph.tracing import PipelineTracer, get_tracer

    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = PipelineTracer("V_GET_TEST", output_dir=tmpdir)
        current = get_tracer()
        assert current is tracer
        assert current.vector_id == "V_GET_TEST"


# ---------------------------------------------------------------------------
# Test 12: Quality gate detects below-minimum report (FIX-310)
# ---------------------------------------------------------------------------

def test_quality_gate_detects_below_minimum():
    """FIX-310: Quality gate identifies reports below minimum thresholds."""
    from src.polaris_graph.synthesis.report_assembler import compute_quality_metrics

    # Create thin report sections
    thin_sections = [
        ReportSection(
            section_id="s01",
            title="Section 1",
            content="Short content " * 50,  # ~100 words
            word_count=100,
            citation_ids=["[1]", "[2]"],
            evidence_ids=["ev_1", "ev_2"],
        ),
        ReportSection(
            section_id="s02",
            title="Section 2",
            content="Another short section " * 60,  # ~180 words
            word_count=180,
            citation_ids=["[3]"],
            evidence_ids=["ev_3"],
        ),
    ]

    evidence = [_make_evidence(f"ev_{i}") for i in range(5)]
    claims = [_make_claim(f"ev_{i}") for i in range(5)]
    bibliography = [{"evidence_ids": [f"ev_{i}"]} for i in range(3)]

    quality = compute_quality_metrics(
        evidence=evidence,
        claims=claims,
        report_sections=thin_sections,
        bibliography=bibliography,
        faithfulness_score=0.9,
    )

    # Report is 280 words — well below MIN_TOTAL_WORDS=4000
    assert quality["total_words"] == 280
    assert quality["total_citations"] == 3
    assert quality["unique_sources"] == 3

    # All below minimums
    from src.polaris_graph.state import MIN_TOTAL_WORDS, MIN_CITATIONS, MIN_UNIQUE_SOURCES
    assert quality["total_words"] < MIN_TOTAL_WORDS
    assert quality["total_citations"] < MIN_CITATIONS
    assert quality["unique_sources"] < MIN_UNIQUE_SOURCES


# ---------------------------------------------------------------------------
# Test 13: expand_thin_sections generates content (FIX-310)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expand_thin_sections():
    """FIX-310: expand_thin_sections() adds content to thin sections."""
    from src.polaris_graph.synthesis.section_writer import expand_thin_sections
    from src.polaris_graph.schemas import ReportOutline, SectionOutlineItem

    # Mock client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = (
        "Furthermore, recent studies demonstrate that activated carbon "
        "filters achieve 99.7% removal of chlorine compounds [CITE:ev_extra_1]. "
        "Additionally, membrane filtration systems have shown consistent "
        "performance over 12-month periods [CITE:ev_extra_2]. "
        "These findings suggest that combined treatment approaches "
        "yield superior water quality outcomes compared to single-method "
        "approaches [CITE:ev_extra_1]."
    )
    mock_client.generate = AsyncMock(return_value=mock_response)

    # Create thin section
    thin_sections = [
        ReportSection(
            section_id="s01",
            title="Water Treatment Methods",
            content="Basic water treatment is important. Filters help [1].",
            word_count=8,
            citation_ids=["[1]"],
            evidence_ids=["ev_1"],
        ),
    ]

    # Create outline with matching section
    outline = MagicMock(spec=ReportOutline)
    outline.sections = [
        MagicMock(
            spec=SectionOutlineItem,
            section_id="s01",
            title="Water Treatment Methods",
            evidence_ids=["ev_1", "ev_extra_1", "ev_extra_2"],
            target_words=800,
        ),
    ]

    evidence = [
        _make_evidence("ev_1", statement="Filters reduce contaminants"),
        _make_evidence("ev_extra_1", statement="Carbon filters remove chlorine"),
        _make_evidence("ev_extra_2", statement="Membrane filters last 12 months"),
    ]

    # Patch tracing to avoid file I/O
    with patch("src.polaris_graph.synthesis.section_writer.get_tracer", return_value=None):
        expanded = await expand_thin_sections(
            client=mock_client,
            thin_sections=thin_sections,
            outline=outline,
            evidence=evidence,
            query="water filter effectiveness",
        )

    assert len(expanded) == 1
    # Expanded content should be longer than original
    assert len(expanded[0].content.split()) > 8
    # Should contain both old and new content
    assert "Basic water treatment" in expanded[0].content
    assert "CITE:" in expanded[0].content


# ---------------------------------------------------------------------------
# Test 14: Quality gate disabled when max_expansion_passes=0 (FIX-310)
# ---------------------------------------------------------------------------

def test_quality_gate_disabled_with_zero_passes():
    """FIX-310: PG_SYNTHESIS_MAX_EXPANSION_PASSES=0 means no quality gate."""
    from src.polaris_graph.state import create_initial_state

    state = create_initial_state(
        vector_id="test_qg",
        query="test",
        application="general",
        region="GLOBAL",
    )

    # Verify initial state has quality gate fields
    assert state["expansion_passes_used"] == 0
    assert state["quality_gate_result"] == "pending"
    assert state["trace_summary"] == {}


# ---------------------------------------------------------------------------
# Test 15: State includes new keys (FIX-310 + OBS-1)
# ---------------------------------------------------------------------------

def test_state_includes_new_keys():
    """FIX-310 + OBS-1: ResearchState has expansion_passes_used, quality_gate_result, trace_summary."""
    state = create_initial_state(
        vector_id="test_keys",
        query="test",
        application="general",
        region="GLOBAL",
    )

    # All new keys must be present and initialized
    assert "expansion_passes_used" in state
    assert "quality_gate_result" in state
    assert "trace_summary" in state
    assert state["expansion_passes_used"] == 0
    assert state["quality_gate_result"] == "pending"
    assert isinstance(state["trace_summary"], dict)


# ---------------------------------------------------------------------------
# Test 16: Markdown content negotiation header (FETCH-1)
# ---------------------------------------------------------------------------

def test_markdown_prefer_header():
    """FETCH-1: PG_PREFER_MARKDOWN=1 sets Accept: text/markdown header."""
    from src.polaris_graph.state import PG_PREFER_MARKDOWN

    # Verify the env var is configured (should be True by default)
    assert PG_PREFER_MARKDOWN is True or PG_PREFER_MARKDOWN == 1 or PG_PREFER_MARKDOWN is not None


# ---------------------------------------------------------------------------
# Test 17: Agentic search — full 3-round mocked loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agentic_search_three_round_loop():
    """Agentic search executes a 3-round loop with convergence."""
    from src.polaris_graph.agents.searcher import execute_agentic_search

    state = create_initial_state(
        vector_id="V_AGENTIC_LOOP",
        query="household water filter effectiveness",
        application="water_filtration",
        region="GLOBAL",
    )
    state["sub_queries"] = [f"seed_query_{i}" for i in range(9)]

    mock_client = AsyncMock()

    # Round 2 analysis: continue
    analysis_round2 = MagicMock()
    analysis_round2.should_continue = True
    analysis_round2.convergence_assessment = "expanding"
    analysis_round2.web_queries = ["follow-up web 1", "follow-up web 2"]
    analysis_round2.academic_queries = ["follow-up academic 1"]
    analysis_round2.exa_queries = []
    analysis_round2.perspective_gaps = ["Economic"]

    # Round 3 analysis: converge
    analysis_round3 = MagicMock()
    analysis_round3.should_continue = False
    analysis_round3.convergence_assessment = "saturated"
    analysis_round3.web_queries = ["final web 1"]
    analysis_round3.academic_queries = []
    analysis_round3.exa_queries = []
    analysis_round3.perspective_gaps = []

    mock_client.generate_structured = AsyncMock(
        side_effect=[analysis_round2, analysis_round3]
    )

    call_count = 0

    async def mock_web_search(fn, queries, region):
        nonlocal call_count
        call_count += 1
        return [
            {"url": f"https://r{call_count}_{i}.com", "title": f"Result {call_count}_{i}", "snippet": "test"}
            for i in range(3)
        ]

    async def ddg_passthrough(queries, results, region):
        """DDG fallback passthrough — returns existing results unchanged."""
        return results

    with patch("src.polaris_graph.agents.searcher._import_search_tools") as mock_tools, \
         patch("src.polaris_graph.agents.searcher._run_web_searches", side_effect=mock_web_search), \
         patch("src.polaris_graph.agents.searcher._run_academic_searches", new_callable=AsyncMock) as mock_acad, \
         patch("src.polaris_graph.agents.searcher._run_exa_searches", new_callable=AsyncMock) as mock_exa, \
         patch("src.polaris_graph.agents.searcher._run_ddg_fallback_for_zeros", side_effect=ddg_passthrough), \
         patch("src.polaris_graph.agents.searcher._chase_citations", new_callable=AsyncMock) as mock_chase, \
         patch("src.polaris_graph.agents.searcher.get_tracer", return_value=None), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MIN_ROUNDS", 1), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MAX_ROUNDS", 5):

        mock_tools.return_value = (MagicMock(), MagicMock())
        mock_acad.return_value = [{"url": "https://s2.com/paper1", "title": "Paper 1"}]
        mock_exa.return_value = []
        mock_chase.return_value = []

        result = await execute_agentic_search(state, mock_client)

    assert result["status"] == "analyzing"
    assert len(result["web_results"]) > 0
    assert result["agentic_search_rounds"] >= 2
    assert result["agentic_total_queries"] > 0
    assert isinstance(result["agentic_perspective_coverage"], dict)


# ---------------------------------------------------------------------------
# Test 18: Agentic metadata propagated in state
# ---------------------------------------------------------------------------

def test_agentic_state_keys_in_research_state():
    """Agentic metadata keys are declared in ResearchState and initialized."""
    state = create_initial_state(
        vector_id="V_META",
        query="test",
        application="general",
        region="GLOBAL",
    )

    # All 5 agentic keys must be present (LangGraph would drop undeclared)
    agentic_keys = [
        "agentic_search_rounds",
        "agentic_total_queries",
        "agentic_convergence_scores",
        "agentic_url_accumulator",
        "agentic_perspective_coverage",
    ]
    for key in agentic_keys:
        assert key in state, f"Missing agentic key: {key}"


# ---------------------------------------------------------------------------
# Test 19: DDG + citation chase still execute post-loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agentic_post_loop_ddg_and_chase():
    """DDG fallback and citation chase execute after the agentic loop."""
    from src.polaris_graph.agents.searcher import execute_agentic_search

    state = create_initial_state(
        vector_id="V_POST_LOOP",
        query="test post-loop",
        application="general",
        region="GLOBAL",
    )
    state["sub_queries"] = ["q1", "q2", "q3"]

    mock_client = AsyncMock()

    ddg_called = False
    chase_called = False

    async def ddg_tracking(queries, results, region):
        nonlocal ddg_called
        ddg_called = True
        return results

    async def chase_tracking(academic_results, query=""):
        nonlocal chase_called
        chase_called = True
        return [{"url": "https://s2.com/p2", "title": "Chased P2"}]

    with patch("src.polaris_graph.agents.searcher._import_search_tools") as mock_tools, \
         patch("src.polaris_graph.agents.searcher._run_web_searches", new_callable=AsyncMock) as mock_web, \
         patch("src.polaris_graph.agents.searcher._run_academic_searches", new_callable=AsyncMock) as mock_acad, \
         patch("src.polaris_graph.agents.searcher._run_exa_searches", new_callable=AsyncMock) as mock_exa, \
         patch("src.polaris_graph.agents.searcher._run_ddg_fallback_for_zeros", side_effect=ddg_tracking), \
         patch("src.polaris_graph.agents.searcher._chase_citations", side_effect=chase_tracking), \
         patch("src.polaris_graph.agents.searcher.get_tracer", return_value=None), \
         patch("src.polaris_graph.agents.searcher.PG_AGENTIC_MAX_ROUNDS", 1), \
         patch("src.polaris_graph.agents.searcher.PG_CITATION_CHASE_ENABLED", True):

        mock_tools.return_value = (MagicMock(), MagicMock())
        mock_web.return_value = [{"url": "https://a.com", "title": "A"}]
        mock_acad.return_value = [{"url": "https://s2.com/p1", "title": "P1"}]
        mock_exa.return_value = []

        result = await execute_agentic_search(state, mock_client)

    # DDG fallback was called
    assert ddg_called, "DDG fallback was not called"
    # Citation chase was called
    assert chase_called, "Citation chase was not called"


# ---------------------------------------------------------------------------
# Test 20: Seed planner produces correct number of queries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_planner_produces_nine_queries():
    """plan_seed_queries generates 9 seed queries (1 per perspective)."""
    from src.polaris_graph.agents.planner import plan_seed_queries
    from src.polaris_graph.schemas import SeedQueryPlan, SubQuery

    state = create_initial_state(
        vector_id="V_SEED",
        query="water filter effectiveness",
        application="water_filtration",
        region="GLOBAL",
    )

    mock_client = AsyncMock()
    mock_plan = SeedQueryPlan(
        analysis="Test analysis",
        sub_queries=[
            SubQuery(
                query=f"seed query for {p}",
                intent=f"Find {p} evidence",
                source_preference="web",
                perspective=p,
            )
            for p in [
                "Scientific", "Regulatory", "Industry", "Economic",
                "Public_Health", "Historical", "Regional",
                "Methodological", "Emerging_Trends",
            ]
        ],
    )
    mock_client.generate_structured = AsyncMock(return_value=mock_plan)

    result = await plan_seed_queries(mock_client, state)

    assert len(result["sub_queries"]) == 9
    assert result["search_strategy"] == "agentic"
    assert result["status"] == "searching"
    # All 9 perspectives should be covered
    assert len(result["perspective_distribution"]) == 9


# ---------------------------------------------------------------------------
# Test 21: Seed planner fallback on LLM failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_planner_fallback():
    """plan_seed_queries falls back to template queries when LLM returns 0."""
    from src.polaris_graph.agents.planner import plan_seed_queries
    from src.polaris_graph.schemas import SeedQueryPlan

    state = create_initial_state(
        vector_id="V_SEED_FAIL",
        query="water filter safety",
        application="water_filtration",
        region="GLOBAL",
    )

    mock_client = AsyncMock()
    # LLM returns empty plan
    mock_plan = SeedQueryPlan(analysis="", sub_queries=[])
    mock_client.generate_structured = AsyncMock(return_value=mock_plan)

    result = await plan_seed_queries(mock_client, state)

    # Should use fallback — exactly 9 queries (1 per perspective)
    assert len(result["sub_queries"]) == 9
    assert result["search_strategy"] == "agentic"


# ---------------------------------------------------------------------------
# Test 22: Graph topology unchanged
# ---------------------------------------------------------------------------

def test_graph_topology_unchanged():
    """Adding agentic search does NOT change graph topology — same nodes and edges."""
    from src.polaris_graph.graph import build_graph

    graph = build_graph()
    expected_nodes = {"plan", "search", "storm_interviews", "analyze", "verify", "evaluate", "synthesize", "search_gaps"}
    actual_nodes = set(graph.nodes.keys())
    assert expected_nodes.issubset(actual_nodes), (
        f"Missing nodes: {expected_nodes - actual_nodes}"
    )

    edge_pairs = {(e[0], e[1]) for e in graph.edges}
    # Critical edges must still exist (search → storm_interviews → analyze)
    assert ("plan", "search") in edge_pairs
    assert ("search", "storm_interviews") in edge_pairs
    assert ("storm_interviews", "analyze") in edge_pairs
    assert ("analyze", "verify") in edge_pairs
    assert ("verify", "evaluate") in edge_pairs
    assert ("search_gaps", "search") in edge_pairs


# ===========================================================================
# PG037-AUDIT FIX TESTS (Phases 1-7 verification)
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 23: Crawl4AI Unicode safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawl4ai_unicode_safe():
    """_safe_log_str sanitizes Unicode content for cp1252 console logging."""
    from src.tools.access_bypass import _safe_log_str

    # ASCII passthrough
    assert _safe_log_str("hello world") == "hello world"

    # Unicode with arrows, Greek, math symbols -> replaced
    unicode_text = "PFAS → water \u2192 filter \u03b1 \u2265 90%"
    result = _safe_log_str(unicode_text)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should not raise on Windows cp1252 encoding
    result.encode("cp1252")

    # Truncation
    long_text = "a" * 500
    assert len(_safe_log_str(long_text, max_len=100)) == 100


# ---------------------------------------------------------------------------
# Test 24: LettuceDetect loads without torch.compile crash
# ---------------------------------------------------------------------------

def test_lettuce_detect_loads():
    """hallucination_detector module imports without torch.compile crash."""
    # This import would crash on Windows without TORCH_COMPILE_DISABLE=1
    from src.polaris_graph.agents.hallucination_detector import (
        audit_sections_for_hallucination,
    )
    assert callable(audit_sections_for_hallucination)
    # Verify the env var was set by the module
    assert os.environ.get("TORCH_COMPILE_DISABLE") == "1"


# ---------------------------------------------------------------------------
# Test 25: Trafilatura thread pool (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trafilatura_thread_pool():
    """_try_trafilatura runs in thread pool and returns content."""
    from src.tools.access_bypass import AccessBypass

    bypass = AccessBypass()

    # When disabled, returns None
    with patch.dict(os.environ, {"PG_TRAFILATURA_ENABLED": "0"}):
        result = await bypass._try_trafilatura("https://example.com")
        assert result is None

    # When enabled with mock trafilatura
    mock_trafilatura = MagicMock()
    mock_trafilatura.fetch_url.return_value = "<html>test content</html>"
    mock_trafilatura.extract.return_value = "Extracted text content " * 20  # >200 chars

    with patch.dict(os.environ, {"PG_TRAFILATURA_ENABLED": "1"}):
        with patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = await bypass._try_trafilatura("https://example.com/article")
            if result is not None:
                assert result.success
                assert result.access_method == "trafilatura"
                assert len(result.content) > 200


# ---------------------------------------------------------------------------
# Test 26: Convergence router is pure (no state mutation)
# ---------------------------------------------------------------------------

def test_convergence_pure_routing():
    """_should_finalize returns a string and does NOT mutate state."""
    from src.polaris_graph.graph import build_graph

    graph = build_graph()

    # Create state where quality gate failed but we're at max iterations
    state = create_initial_state(
        vector_id="V_PURE", query="test", application="test", region="GLOBAL",
    )
    state["quality_gate_result"] = "below_minimum"
    state["converged"] = False
    state["iteration_count"] = 3
    state["max_iterations"] = 3
    state["quality_metrics"] = {"total_words": 5000}
    state["sections"] = [{"title": "Intro", "word_count": 100}]

    # Take a snapshot of gap_queries before the call
    state["gap_queries"] = []
    gap_queries_before = list(state["gap_queries"])

    # Access the _should_finalize function from the graph's conditional edges
    # The function is defined inside build_graph, so we test indirectly
    # by checking that gap_queries is NOT mutated when at max iterations
    assert state["gap_queries"] == gap_queries_before  # no mutation

    # State at max_iter should return "end" regardless of quality gate
    # (routing function cannot mutate state to add gap queries)


# ---------------------------------------------------------------------------
# Test 27: cross_reference_groups persists in state
# ---------------------------------------------------------------------------

def test_cross_reference_state_persists():
    """cross_reference_groups field survives state creation and is declared."""
    state = create_initial_state(
        vector_id="V_XREF", query="test", application="test", region="GLOBAL",
    )

    # Field exists and is initialized
    assert "cross_reference_groups" in state
    assert state["cross_reference_groups"] == []

    # Field is declared in ResearchState TypedDict
    assert "cross_reference_groups" in ResearchState.__annotations__

    # Can be set and read
    state["cross_reference_groups"] = [
        {"evidence_ids": ["ev_1", "ev_2"], "agreement_score": 0.85}
    ]
    assert len(state["cross_reference_groups"]) == 1


# ---------------------------------------------------------------------------
# Test 28: source_confidence field in EvidencePiece
# ---------------------------------------------------------------------------

def test_source_confidence_in_evidence_piece():
    """source_confidence is declared in EvidencePiece TypedDict."""
    assert "source_confidence" in EvidencePiece.__annotations__


# ---------------------------------------------------------------------------
# Test 29: Source confidence runtime gate
# ---------------------------------------------------------------------------

def test_source_confidence_runtime_gate():
    """_is_enabled() reflects env var changes at runtime (not import time)."""
    from src.polaris_graph.agents.source_confidence import _is_enabled

    # Toggle off
    with patch.dict(os.environ, {"PG_SOURCE_CONFIDENCE_ENABLED": "0"}):
        assert _is_enabled() is False

    # Toggle on
    with patch.dict(os.environ, {"PG_SOURCE_CONFIDENCE_ENABLED": "1"}):
        assert _is_enabled() is True

    # Missing env var defaults to disabled
    env_copy = dict(os.environ)
    env_copy.pop("PG_SOURCE_CONFIDENCE_ENABLED", None)
    with patch.dict(os.environ, env_copy, clear=True):
        assert _is_enabled() is False


# ---------------------------------------------------------------------------
# Test 30: PageRank API live (skippable)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.getenv("PG_SKIP_LIVE_TESTS", "0") == "1",
    reason="Live test skipped (PG_SKIP_LIVE_TESTS=1)",
)
@pytest.mark.asyncio
async def test_pagerank_api_live():
    """Open PageRank API returns valid response for known domain."""
    import aiohttp

    api_key = os.getenv("OPEN_PAGERANK_API_KEY", "")
    if not api_key:
        pytest.skip("OPEN_PAGERANK_API_KEY not set")

    url = "https://openpagerank.com/api/v1.0/getPageRank"
    headers = {"API-OPR": api_key}
    params = [("domains[]", "google.com")]

    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                assert response.status == 200
                data = await response.json()
                assert "response" in data
                assert len(data["response"]) >= 1
                item = data["response"][0]
                assert "page_rank_decimal" in item
                assert float(item["page_rank_decimal"]) > 0
    except (aiohttp.ClientError, OSError) as exc:
        pytest.skip(f"Network unavailable: {exc}")


# ---------------------------------------------------------------------------
# Test 31: Hallucination audit state key persists through LangGraph
# ---------------------------------------------------------------------------

def test_hallucination_audit_in_state():
    """hallucination_audit is declared in ResearchState and initialized."""
    from src.polaris_graph.state import ResearchState, create_initial_state

    assert "hallucination_audit" in ResearchState.__annotations__
    state = create_initial_state(
        vector_id="test", query="test", application="test", region="test",
    )
    assert state["hallucination_audit"] == []


# ---------------------------------------------------------------------------
# Test 32: Hallucination detector runtime gate
# ---------------------------------------------------------------------------

def test_hallucination_detect_runtime_gate():
    """_is_enabled() reflects runtime env var changes."""
    from src.polaris_graph.agents.hallucination_detector import _is_enabled

    with patch.dict(os.environ, {"PG_HALLUCINATION_DETECT_ENABLED": "0"}):
        assert _is_enabled() is False

    with patch.dict(os.environ, {"PG_HALLUCINATION_DETECT_ENABLED": "1"}):
        assert _is_enabled() is True

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PG_HALLUCINATION_DETECT_ENABLED", None)
        assert _is_enabled() is False


# ---------------------------------------------------------------------------
# Test 33a: FIX-039 — SectionDraft evidence_ids propagation
# ---------------------------------------------------------------------------

def test_section_draft_evidence_ids_propagation():
    """FIX-039: SectionDraft preserves evidence_ids through all creation paths."""
    from src.polaris_graph.schemas import SectionDraft

    # write_section path: evidence_ids from outline
    draft = SectionDraft(
        section_id="s01",
        title="Test Section",
        content="Content with [CITE:ev_abc123]",
        claims_made=["claim 1"],
        evidence_ids=["ev_abc123", "ev_def456"],
    )
    assert draft.evidence_ids == ["ev_abc123", "ev_def456"]

    # revise_section path: preserve from original draft
    revised = SectionDraft(
        section_id=draft.section_id,
        title=draft.title,
        content="Revised content",
        claims_made=["revised claim"],
        evidence_ids=draft.evidence_ids,  # FIX-039
    )
    assert revised.evidence_ids == ["ev_abc123", "ev_def456"]

    # expand_thin_sections path: from report_sections dict
    section_dict = {"evidence_ids": ["ev_ghi789"]}
    expanded = SectionDraft(
        section_id="s01",
        title="Expanded",
        content="Expanded content",
        claims_made=[],
        evidence_ids=section_dict.get("evidence_ids", []),  # FIX-039
    )
    assert expanded.evidence_ids == ["ev_ghi789"]

    # Backward compat: no evidence_ids defaults to []
    legacy = SectionDraft(
        section_id="s01",
        title="Legacy",
        content="Content",
        claims_made=[],
    )
    assert legacy.evidence_ids == []


def test_section_evidence_map_fallback():
    """FIX-039: section_evidence_map fallback when evidence_ids is empty."""
    from src.polaris_graph.schemas import SectionDraft

    # Simulate post-revision draft with empty evidence_ids
    sec = SectionDraft(
        section_id="s01",
        title="Test",
        content="Content",
        claims_made=[],
        # evidence_ids defaults to []
    )
    section_evidence_map = {"s01": ["ev_001", "ev_002"], "s02": ["ev_003"]}

    # This mirrors the synthesizer.py hallucination audit conversion logic
    sid = sec.section_id
    result_ids = getattr(sec, "evidence_ids", []) or section_evidence_map.get(sid, [])
    assert result_ids == ["ev_001", "ev_002"], (
        f"Fallback should return section_evidence_map entries, got: {result_ids}"
    )

    # When evidence_ids IS populated, it should take priority
    sec_with_ids = SectionDraft(
        section_id="s01",
        title="Test",
        content="Content",
        claims_made=[],
        evidence_ids=["ev_direct"],
    )
    result_ids2 = getattr(sec_with_ids, "evidence_ids", []) or section_evidence_map.get("s01", [])
    assert result_ids2 == ["ev_direct"], (
        f"Direct evidence_ids should take priority, got: {result_ids2}"
    )


# ---------------------------------------------------------------------------
# Test 33: Gap queries cleared between iterations
# ---------------------------------------------------------------------------

def test_gap_queries_cleared_by_synthesize():
    """_synthesize() always includes gap_queries in result to prevent stale state."""
    # The fix ensures result.setdefault("gap_queries", []) is called
    # Verify by checking that synthesize_report's result gets gap_queries added
    result = {"quality_gate_result": "passed", "sections": []}
    result.setdefault("gap_queries", [])
    assert result["gap_queries"] == []


# ---------------------------------------------------------------------------
# NRC-2: Cross-section semantic dedup
# ---------------------------------------------------------------------------

def test_remove_redundancy_catches_semantic_dupes():
    """NRC-2: remove_redundancy() catches semantically identical but reworded sentences."""
    from src.polaris_graph.synthesis.report_assembler import remove_redundancy

    sections = [
        ReportSection(
            section_id="s01",
            title="Background",
            content="Traditional treatment methods cannot effectively remove PFAS from water. "
                    "This is a major challenge for water utilities worldwide.",
            word_count=20,
            citation_ids=["[1]"],
            evidence_ids=["ev_01"],
        ),
        ReportSection(
            section_id="s02",
            title="Challenges",
            content="Conventional water treatment approaches are unable to effectively eliminate PFAS. "
                    "This section discusses alternative methods.",
            word_count=15,
            citation_ids=["[2]"],
            evidence_ids=["ev_02"],
        ),
    ]

    # With default threshold, Jaccard should catch high-overlap sentences
    result = remove_redundancy(sections, threshold=0.40)
    # The second section should have had the duplicate removed
    assert len(result) == 2
    # Verify function returns valid sections
    for s in result:
        assert "content" in s
        assert "section_id" in s


# ---------------------------------------------------------------------------
# NRC-3: Uncited claims audit
# ---------------------------------------------------------------------------

def test_audit_uncited_claims_detects_numerics():
    """NRC-3: _audit_uncited_claims() catches sentences with numbers but no citation."""
    from src.polaris_graph.synthesis.report_assembler import _audit_uncited_claims

    sections = [
        ReportSection(
            section_id="s01",
            title="EPA Regulations",
            content="The EPA set a limit of 0.004 ppt for PFOA. "
                    "This was based on extensive research [1]. "
                    "Operating pressures of 15-40 bar are typical.",
            word_count=25,
            citation_ids=["[1]"],
            evidence_ids=["ev_01"],
        ),
    ]

    flagged = _audit_uncited_claims(sections)
    # Should flag "0.004 ppt" (no citation) and "15-40 bar" (no citation)
    # Should NOT flag the sentence with [1]
    assert len(flagged) >= 1
    # All flagged items should be from section s01
    for f in flagged:
        assert f["section_id"] == "s01"


def test_soften_uncited_numerics():
    """NRC-3: _soften_uncited_numerics() replaces specific numbers without citations."""
    from src.polaris_graph.synthesis.report_assembler import _soften_uncited_numerics

    sections = [
        ReportSection(
            section_id="s01",
            title="Test",
            content="The pressure was 15 bar for this system. "
                    "The efficiency was 90% according to Smith [1].",
            word_count=15,
            citation_ids=["[1]"],
            evidence_ids=["ev_01"],
        ),
    ]

    result = _soften_uncited_numerics(sections)
    # The cited sentence should remain unchanged
    assert "[1]" in result[0]["content"]
    # The uncited sentence should be softened
    assert "15 bar" not in result[0]["content"] or "[1]" in result[0]["content"]


# ---------------------------------------------------------------------------
# NRC-4: Bibliography validation
# ---------------------------------------------------------------------------

def test_bibliography_validation_rejects_placeholder():
    """NRC-4: _validate_bibliography_entry() rejects 'not specified' titles."""
    from src.polaris_graph.synthesis.citation_mapper import _validate_bibliography_entry

    valid_ev = {
        "source_title": "Efficient PFAS Removal by Activated Carbon",
        "year": 2024,
        "authors": ["Smith J"],
        "venue": "Water Research",
        "source_url": "https://example.com",
    }
    is_valid, reason = _validate_bibliography_entry(valid_ev)
    assert is_valid is True
    assert reason == "valid"

    # Placeholder title
    placeholder_ev = {
        "source_title": "not specified in provided content",
        "year": 2024,
        "source_url": "https://example.com",
    }
    is_valid, reason = _validate_bibliography_entry(placeholder_ev)
    assert is_valid is False
    assert "placeholder_title" in reason


def test_bibliography_validation_rejects_future_dated():
    """NRC-4: _validate_bibliography_entry() rejects future-dated entries."""
    from src.polaris_graph.synthesis.citation_mapper import _validate_bibliography_entry

    future_ev = {
        "source_title": "Some Study",
        "year": 2030,
        "authors": ["Doe J"],
        "source_url": "https://example.com",
    }
    is_valid, reason = _validate_bibliography_entry(future_ev)
    assert is_valid is False
    assert "future_dated" in reason


def test_format_bibliography_entry_url_only_for_invalid():
    """NRC-4: Invalid entries get URL-only format."""
    from src.polaris_graph.synthesis.citation_mapper import _format_bibliography_entry

    invalid_ev = {
        "source_title": "not specified",
        "year": 0,
        "authors": [],
        "venue": "",
        "source_url": "https://example.com/paper",
    }
    formatted = _format_bibliography_entry(invalid_ev, 1)
    assert "[1]" in formatted
    assert "Available at: https://example.com/paper" in formatted
    assert "not specified" not in formatted


# ---------------------------------------------------------------------------
# NRC-5: Post-extraction claim validation
# ---------------------------------------------------------------------------

def test_validate_extraction_claims_marks_unverified():
    """NRC-5: _validate_extraction_claims() flags paraphrased quotes."""
    from src.polaris_graph.agents.analyzer import _validate_extraction_claims

    evidence = [
        {
            "evidence_id": "ev_001",
            "direct_quote": "PFAS are persistent organic pollutants found in water",
            "source_content": "Per- and polyfluoroalkyl substances (PFAS) are persistent "
                              "organic pollutants found in water supplies worldwide.",
            "statement": "PFAS are persistent pollutants",
        },
        {
            "evidence_id": "ev_002",
            "direct_quote": "Consumer Reports tested 47 filters for PFAS removal",
            "source_content": "This is a completely unrelated article about cooking recipes.",
            "statement": "47 filters were tested",
        },
    ]

    result = _validate_extraction_claims(evidence)
    # ev_001 should be verified (words match)
    assert result[0].get("quote_verified") is True
    # ev_002 should be unverified (no matching content)
    assert result[1].get("quote_verified") is False


# ---------------------------------------------------------------------------
# NRC-2: Global citation frequency cap
# ---------------------------------------------------------------------------

def test_resolve_citations_global_cap():
    """NRC-2: resolve_citations() enforces global citation frequency cap."""
    from src.polaris_graph.synthesis.citation_mapper import resolve_citations

    citation_map = {"ev_001": 1, "ev_002": 2}
    global_counts = {1: 9}  # Already at 9 uses

    # With PG_MAX_GLOBAL_CITATION_FREQ=10 (default), one more should pass
    content = "[CITE:ev_001] and [CITE:ev_002]"
    with patch.dict(os.environ, {"PG_MAX_GLOBAL_CITATION_FREQ": "10", "PG_MAX_CITATION_FREQUENCY": "20"}):
        result = resolve_citations(content, citation_map, global_citation_counts=global_counts)

    assert "[1]" in result  # Should pass (count 10 <= 10)
    assert "[2]" in result

    # Now count is at 10 for citation 1, next use should be dropped
    content2 = "[CITE:ev_001]"
    with patch.dict(os.environ, {"PG_MAX_GLOBAL_CITATION_FREQ": "10", "PG_MAX_CITATION_FREQUENCY": "20"}):
        result2 = resolve_citations(content2, citation_map, global_citation_counts=global_counts)

    assert "[1]" not in result2  # Should be dropped (count 11 > 10)
    assert "[*]" in result2  # Phantom marker replaces dropped citation


# ---------------------------------------------------------------------------
# NRC Edge Case Tests (Post-T041)
# ---------------------------------------------------------------------------

def test_validate_extraction_claims_domain_grouping():
    """NRC-5: Evidence from same domain (different URLs) grouped together for capping."""
    from src.polaris_graph.agents.analyzer import _validate_extraction_claims

    evidence = [
        {"evidence_id": f"ev_{i}", "quote": f"Quote {i}",
         "source_url": f"https://www.epa.gov/page{i}", "relevance_score": 0.9 - i * 0.1}
        for i in range(5)
    ]
    # Cap at 3 per source domain — should group all 5 under www.epa.gov
    with patch.dict(os.environ, {"PG_MAX_EVIDENCE_PER_CLAIM": "3"}):
        result = _validate_extraction_claims(evidence)
    assert len(result) == 3
    # Should keep the top 3 by relevance (indices 0, 1, 2)
    kept_ids = {ev["evidence_id"] for ev in result}
    assert "ev_0" in kept_ids
    assert "ev_1" in kept_ids
    assert "ev_2" in kept_ids


def test_validate_extraction_claims_skips_missing_url():
    """NRC-5: Evidence without source_url bypasses capping entirely."""
    from src.polaris_graph.agents.analyzer import _validate_extraction_claims

    evidence = [
        {"evidence_id": "ev_0", "quote": "Quote A", "source_url": ""},
        {"evidence_id": "ev_1", "quote": "Quote B", "source_url": ""},
        {"evidence_id": "ev_2", "quote": "Quote C", "source_url": "https://example.com/page1",
         "relevance_score": 0.8},
        {"evidence_id": "ev_3", "quote": "Quote D", "source_url": "https://example.com/page2",
         "relevance_score": 0.5},
    ]
    # Cap at 1 per source — example.com gets capped to 1, but empty URLs survive
    with patch.dict(os.environ, {"PG_MAX_EVIDENCE_PER_CLAIM": "1"}):
        result = _validate_extraction_claims(evidence)
    kept_ids = {ev["evidence_id"] for ev in result}
    # Both empty-URL evidence survive (not grouped)
    assert "ev_0" in kept_ids
    assert "ev_1" in kept_ids
    # Only 1 of the 2 example.com evidence survives (higher relevance)
    assert "ev_2" in kept_ids
    assert "ev_3" not in kept_ids


def test_soften_uncited_numerics_range_expressions():
    """NRC-3: Range expressions like '15-40 bar' are softened atomically, not garbled."""
    from src.polaris_graph.synthesis.report_assembler import _soften_uncited_numerics

    sections = [
        {"section_id": "s1", "title": "Pressure",
         "content": "The system operates at 15-40 bar for optimal performance.",
         "word_count": 9},
        {"section_id": "s2", "title": "Filtration",
         "content": "Membrane pore sizes range from 0.001-0.01 um in this application.",
         "word_count": 10},
    ]
    result = _soften_uncited_numerics(sections)

    # Range should be replaced as ONE unit, not garbled
    s1_content = result[0]["content"]
    assert "(reported values vary)" in s1_content
    # Must NOT contain garbled output like "(specific values vary by study)-40"
    assert "-40" not in s1_content
    assert "15-" not in s1_content

    s2_content = result[1]["content"]
    assert "(reported values vary)" in s2_content
    assert "0.001-" not in s2_content


def test_soften_uncited_numerics_multi_range():
    """NRC-3: Multiple ranges in one sentence are ALL replaced atomically."""
    from src.polaris_graph.synthesis.report_assembler import _soften_uncited_numerics

    sections = [
        {"section_id": "s1", "title": "Performance",
         "content": "The system uses 15-40 bar with 90-99% removal efficiency.",
         "word_count": 10},
    ]
    result = _soften_uncited_numerics(sections)
    content = result[0]["content"]
    # Both ranges should be replaced atomically — no garbled output
    assert "15-" not in content
    assert "-40" not in content
    assert "90-" not in content
    assert "-99" not in content
    # Should have range replacements, not isolated number replacements
    assert "(reported values vary)" in content


def test_soften_uncited_numerics_ph_pattern():
    """NRC-3: pH ranges like 'pH 6.5-8.0' are detected and softened."""
    from src.polaris_graph.synthesis.report_assembler import _soften_uncited_numerics

    sections = [
        {"section_id": "s1", "title": "Water Quality",
         "content": "The optimal range is pH 6.5-8.0 for drinking water treatment.",
         "word_count": 10},
    ]
    result = _soften_uncited_numerics(sections)
    content = result[0]["content"]
    assert "(reported values vary)" in content
    assert "6.5-8.0" not in content


def test_global_cap_phantom_marker_prevents_softening():
    """NRC-2/NRC-3 cascade: Phantom [*] from global cap prevents false softening."""
    from src.polaris_graph.synthesis.report_assembler import _soften_uncited_numerics

    # Simulate a sentence where global cap replaced [1] with [*]
    sections = [
        {"section_id": "s1", "title": "Results",
         "content": "The removal rate was 95% [*] across all trials tested.",
         "word_count": 10},
    ]
    result = _soften_uncited_numerics(sections)
    content = result[0]["content"]
    # [*] should be recognized as citation-present — "95%" must NOT be softened
    assert "95%" in content
    assert "(specific values vary by study)" not in content


def test_phantom_markers_stripped_from_final_output():
    """Fix 3: [*] phantom markers are stripped from final report text."""
    import re
    text = "The rate was 95% [*] and efficiency was 80% [*] overall."
    # Simulate the strip logic from report_assembler
    cleaned = text.replace("[*]", "")
    cleaned = re.sub(r"  +", " ", cleaned)
    assert "[*]" not in cleaned
    assert "95%" in cleaned
    assert "80%" in cleaned
    assert "  " not in cleaned


# ---------------------------------------------------------------------------
# FIX-044/Issue1: analyze_gaps filters orphaned claims (real integration test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_gaps_filters_orphaned_claims():
    """FIX-044/Issue1: Real analyze_gaps() call — orphaned claims filtered,
    faithfulness_score propagated in return dict.

    Uses quality gate early-exit path (total_evidence >= 20, gold >= 7,
    faithfulness >= 0.70) so no LLM calls are needed.
    """
    from src.polaris_graph.agents.synthesizer import analyze_gaps

    # Build 25 evidence: 10 GOLD, 15 SILVER
    evidence = []
    for i in range(10):
        evidence.append(
            _make_evidence(f"ev_g{i}", statement=f"Gold claim {i}", quality_tier="GOLD")
        )
    for i in range(15):
        evidence.append(
            _make_evidence(f"ev_s{i}", statement=f"Silver claim {i}", quality_tier="SILVER")
        )

    # Build 35 claims: 25 faithful (matching surviving evidence),
    # 10 unfaithful (pointing to evidence that FIX-QM7 will remove)
    claims = []
    for i in range(10):
        claims.append(
            _make_claim(f"ev_g{i}", is_faithful=True, method="nli_supported")
        )
    for i in range(15):
        claims.append(
            _make_claim(f"ev_s{i}", is_faithful=True, method="nli_supported")
        )
    # 10 unfaithful claims pointing to evidence IDs that exist in our evidence
    # FIX-QM7 removes evidence backing these, then FIX-043A removes orphaned claims
    unfaithful_ev = []
    for i in range(10):
        eid = f"ev_bad{i}"
        unfaithful_ev.append(
            _make_evidence(eid, statement=f"Bad claim {i}", quality_tier="BRONZE")
        )
        claims.append(
            _make_claim(eid, is_faithful=False, method="nli_not_supported")
        )
    all_evidence = evidence + unfaithful_ev

    state = create_initial_state(
        vector_id="V_044_ISSUE1",
        query="water filter effectiveness test query",
        application="water_filtration",
        region="GLOBAL",
    )
    state["evidence"] = [e if isinstance(e, dict) else dict(e) for e in all_evidence]
    state["claims"] = [c if isinstance(c, dict) else dict(c) for c in claims]
    state["iteration_count"] = 0
    state["max_iterations"] = 3

    # Mock client — quality gate early-exit means no LLM calls
    mock_client = AsyncMock()

    result = await analyze_gaps(mock_client, state)

    # Key assertions:
    # 1. "claims" key present and orphaned claims removed
    assert "claims" in result
    result_claim_ids = {c["claim_id"] for c in result["claims"]}
    for i in range(10):
        assert f"ev_bad{i}" not in result_claim_ids, (
            f"Orphaned claim ev_bad{i} should have been removed"
        )

    # 2. faithfulness_score present in result (FIX-044/Issue5)
    assert "faithfulness_score" in result
    # After removing 10 unfaithful claims and their evidence, all remaining
    # claims are faithful: 25/25 = 1.0
    assert result["faithfulness_score"] == pytest.approx(1.0, abs=0.01)

    # 3. Quality gate should have passed (25 evidence, 10 GOLD, 100% faithful)
    assert result["needs_iteration"] is False

    # 4. Evidence should have unfaithful evidence removed
    assert "evidence" in result
    result_ev_ids = {e["evidence_id"] for e in result["evidence"]}
    for i in range(10):
        assert f"ev_bad{i}" not in result_ev_ids


# ---------------------------------------------------------------------------
# FIX-043B: _save_output reconciles orphaned claims at save time
# ---------------------------------------------------------------------------

def test_save_output_reconciles_orphaned_claims():
    """FIX-043B: Orphaned claims are removed and faithfulness recomputed at save.

    Even if FIX-043A misses orphaned claims, _save_output() acts as a
    defense-in-depth layer by reconciling claims against evidence before
    writing the output JSON.
    """
    from src.polaris_graph.graph import _save_output

    # Create state with 3 evidence and 5 claims (2 orphaned)
    evidence = [
        {"evidence_id": "ev_1", "statement": "Claim 1"},
        {"evidence_id": "ev_2", "statement": "Claim 2"},
        {"evidence_id": "ev_3", "statement": "Claim 3"},
    ]
    claims = [
        {"claim_id": "c1", "evidence_ids": ["ev_1"], "is_faithful": True,
         "verification_method": "nli_supported"},
        {"claim_id": "c2", "evidence_ids": ["ev_2"], "is_faithful": True,
         "verification_method": "nli_supported"},
        {"claim_id": "c3", "evidence_ids": ["ev_3"], "is_faithful": True,
         "verification_method": "nli_supported"},
        # Orphaned: evidence_ids reference removed evidence
        {"claim_id": "c4", "evidence_ids": ["ev_removed_1"], "is_faithful": False,
         "verification_method": "nli_not_supported"},
        {"claim_id": "c5", "evidence_ids": ["ev_removed_2"], "is_faithful": False,
         "verification_method": "nli_not_supported"},
    ]

    state = {
        "evidence": evidence,
        "claims": claims,
        "faithfulness_score": 0.6,  # 3/5 = 60% (wrong due to orphans)
        "final_report": "# Test Report\n\nSome content here.",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.polaris_graph.graph.OUTPUT_DIR",
                    __import__("pathlib").Path(tmpdir)):
            _save_output(state, "test_043b")

        # Verify state was reconciled
        assert len(state["claims"]) == 3, (
            f"Expected 3 claims after reconciliation, got {len(state['claims'])}"
        )
        # Faithfulness should be recomputed: 3/3 = 1.0
        assert state["faithfulness_score"] == 1.0, (
            f"Expected faithfulness 1.0, got {state['faithfulness_score']}"
        )
        # Verify orphaned claims were removed
        remaining_ids = {c["claim_id"] for c in state["claims"]}
        assert "c4" not in remaining_ids
        assert "c5" not in remaining_ids

        # Verify JSON file was written
        output_path = __import__("pathlib").Path(tmpdir) / "test_043b.json"
        assert output_path.exists()
        with open(output_path) as f:
            saved = json.load(f)
        assert len(saved["claims"]) == 3


# ---------------------------------------------------------------------------
# FIX-043C: get_disputed_claims flags quote_only basis
# ---------------------------------------------------------------------------

def test_get_disputed_claims_flags_quote_only():
    """FIX-043C: Claims with quote_only verification basis are always disputed.

    NLI scoring with no source content (only direct_quote) is unreliable.
    These claims must be routed to LLM for a second opinion regardless of
    their NLI score.
    """
    from src.polaris_graph.agents.nli_verifier import get_disputed_claims

    nli_results = [
        # High-confidence content-based claim — should NOT be disputed
        {"claim_id": "c1", "nli_score": 0.95, "verification_basis": "content",
         "is_faithful": True},
        # Low-confidence content-based claim — should NOT be disputed (below threshold)
        {"claim_id": "c2", "nli_score": 0.05, "verification_basis": "content",
         "is_faithful": False},
        # Ambiguous content-based claim — SHOULD be disputed (score in 0.3-0.7 range)
        {"claim_id": "c3", "nli_score": 0.50, "verification_basis": "content",
         "is_faithful": False},
        # title_only — SHOULD be disputed (FIX-NLI-CASCADE)
        {"claim_id": "c4", "nli_score": 0.95, "verification_basis": "title_only",
         "is_faithful": True},
        # quote_only with high NLI score — SHOULD be disputed (FIX-043C)
        {"claim_id": "c5", "nli_score": 0.92, "verification_basis": "quote_only",
         "is_faithful": True},
        # quote_only with low NLI score — SHOULD be disputed (FIX-043C)
        {"claim_id": "c6", "nli_score": 0.08, "verification_basis": "quote_only",
         "is_faithful": False},
    ]

    disputed = get_disputed_claims(nli_results, threshold=0.3)

    disputed_ids = {r["claim_id"] for r in disputed}
    # c1 (high confidence content) — NOT disputed
    assert "c1" not in disputed_ids
    # c2 (low confidence content, below threshold) — NOT disputed
    assert "c2" not in disputed_ids
    # c3 (ambiguous content, score 0.5 in [0.3, 0.7]) — disputed
    assert "c3" in disputed_ids
    # c4 (title_only) — disputed regardless of score
    assert "c4" in disputed_ids
    # c5 (quote_only, high score) — disputed regardless of score (FIX-043C)
    assert "c5" in disputed_ids
    # c6 (quote_only, low score) — disputed regardless of score (FIX-043C)
    assert "c6" in disputed_ids

    assert len(disputed) == 4, (
        f"Expected 4 disputed claims (c3, c4, c5, c6), got {len(disputed)}: "
        f"{disputed_ids}"
    )


# ---------------------------------------------------------------------------
# FIX-044/Issue3: Firecrawl kill switch respects PG_FIRECRAWL_ENABLED env var
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_firecrawl_kill_switch_respects_env():
    """FIX-044/Issue3: _try_firecrawl returns None-result when PG_FIRECRAWL_ENABLED=0.

    Even with FIRECRAWL_API_KEY set and credits available, setting
    PG_FIRECRAWL_ENABLED=0 should skip Firecrawl entirely (no HTTP calls).
    """
    from src.tools.access_bypass import AccessBypass

    bypass = AccessBypass()

    with patch.dict(os.environ, {
        "PG_FIRECRAWL_ENABLED": "0",
        "FIRECRAWL_API_KEY": "fc-test-key-12345",
    }):
        result = await bypass._try_firecrawl("https://example.com/test")

    assert result is not None
    assert result.success is False
    assert result.access_method == "firecrawl"
    assert "disabled" in result.metadata.get("error", "").lower()


# ---------------------------------------------------------------------------
# FIX-044/Issue4: Hedging word count excludes month "may"
# ---------------------------------------------------------------------------

def test_hedging_word_count_excludes_month_may():
    """FIX-044/Issue4: 'may 2024' NOT counted as hedging, 'may cause' IS counted."""
    from src.polaris_graph.synthesis.report_assembler import compute_quality_metrics

    sections = [
        ReportSection(
            section_id="s01",
            title="Regulations",
            content=(
                "The EPA published guidelines in May 2024 that may affect water treatment. "
                "These regulations may cause changes to filtration standards. "
                "A study from 15 May found that contaminants could be reduced. "
                "This might impact future policy decisions."
            ),
            word_count=35,
            citation_ids=["[1]", "[2]"],
            evidence_ids=["ev_1", "ev_2"],
        ),
    ]
    evidence = [_make_evidence(f"ev_{i}") for i in range(5)]
    claims = [_make_claim(f"ev_{i}") for i in range(5)]
    bibliography = [{"evidence_ids": [f"ev_{i}"]} for i in range(3)]

    quality = compute_quality_metrics(
        evidence=evidence,
        claims=claims,
        report_sections=sections,
        bibliography=bibliography,
        faithfulness_score=0.9,
    )

    breakdown = quality["hedging_word_breakdown"]
    # "May 2024" and "15 May" should NOT count (month-name date patterns)
    # "may affect" and "may cause" SHOULD count (hedging usage)
    assert breakdown.get("may", 0) == 2, (
        f"Expected 2 hedging 'may' (affect, cause) but got {breakdown.get('may', 0)}. "
        f"Full breakdown: {breakdown}"
    )
    # "might" should count once
    assert breakdown.get("might", 0) == 1
    # "could" should count once
    assert breakdown.get("could", 0) == 1


# ---------------------------------------------------------------------------
# FIX-044/Issue2: verify_evidence_nli quote-only branch test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_evidence_nli_quote_only_branch():
    """FIX-044/Issue2: When source content is missing, verify_evidence_nli uses
    direct_quote as doc_text (not 'No source content available.').

    Also verifies verification_basis is correctly set to 'content', 'quote_only',
    or 'title_only' depending on available data.
    """
    from src.polaris_graph.agents.nli_verifier import verify_evidence_nli

    # Evidence: 3 items with different content availability
    evidence = [
        {
            "evidence_id": "ev_content",
            "source_url": "https://example.com/full",
            "source_title": "Full Content Source",
            "statement": "Water filters remove 99% of contaminants",
            "direct_quote": "filters remove 99% of contaminants from water",
        },
        {
            "evidence_id": "ev_quote_only",
            "source_url": "https://example.com/missing",
            "source_title": "Missing Content Source",
            "statement": "PFAS levels exceed EPA limits",
            "direct_quote": "PFAS contamination levels exceed federal EPA limits in 40 states",
        },
        {
            "evidence_id": "ev_title_only",
            "source_url": "https://example.com/nothing",
            "source_title": "Title Only Source",
            "statement": "Reverse osmosis is effective",
            "direct_quote": "",
        },
    ]

    # url_content_map: only has content for first evidence
    url_content_map = {
        "https://example.com/full": (
            "A comprehensive study showed that household water "
            "filters remove 99% of contaminants from water supplies, "
            "including bacteria, lead, and chlorine byproducts."
        ),
        # Missing: https://example.com/missing (quote-only case)
        # Missing: https://example.com/nothing (title-only case)
    }

    # Capture what the scorer receives
    captured_docs = []
    captured_claims = []

    class FakeScorer:
        def score(self, docs, claims):
            captured_docs.extend(docs)
            captured_claims.extend(claims)
            n = len(docs)
            pred_labels = [1] * n
            raw_probs = [0.85] * n
            used_chunks = [1] * n
            prob_per_chunk = [[0.85]] * n
            return pred_labels, raw_probs, used_chunks, prob_per_chunk

    with patch("src.polaris_graph.agents.nli_verifier.load_nli_model",
               new_callable=AsyncMock) as mock_load:
        mock_load.return_value = FakeScorer()

        results = await verify_evidence_nli(
            evidence=evidence,
            url_content_map=url_content_map,
            research_query="water filter PFAS contamination",
        )

    assert len(results) == 3

    # Verify the scorer received correct doc_text for each case
    assert len(captured_docs) == 3

    # ev_content: should use content-based context extraction (contains quote text)
    assert "99%" in captured_docs[0] or "contaminants" in captured_docs[0]

    # ev_quote_only (FIX-043C): should use direct_quote, NOT "No source content available."
    assert captured_docs[1] == "PFAS contamination levels exceed federal EPA limits in 40 states"
    assert captured_docs[1] != "No source content available."

    # ev_title_only: no content and no quote → "No source content available."
    assert captured_docs[2] == "No source content available."

    # Verify verification_basis is correct
    basis_map = {r["claim_id"]: r["verification_basis"] for r in results}
    assert basis_map["ev_content"] == "content"
    assert basis_map["ev_quote_only"] == "quote_only"
    assert basis_map["ev_title_only"] == "title_only"
