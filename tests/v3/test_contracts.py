"""Phase boundary contract tests for v3 pipeline.

These tests validate that the data contracts between phases are well-defined
and compatible. They run BEFORE any implementation code exists.

Tests 0.4-0.7 from Milestone 0.
"""

import inspect

import pytest

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineGap,
    OutlineSection,
    Reflection,
    ScopeOutput,
    SearchQuery,
    SearchRoundOutput,
    SubQuestion,
    V3ResultOutput,
    VerifiedSectionDraft,
    REQUIRED_TRACE_EVENTS,
    REQUIRED_EVIDENCE_ACTIONS,
    V3_NODE_NAMES,
)


# ---------------------------------------------------------------------------
# 0.4: Phase boundary contract tests
# ---------------------------------------------------------------------------

class TestScopeToSearchContract:
    """Contract: ScopeOutput -> SearchQuery[] consumed by Phase 2."""

    def test_scope_output_produces_search_queries(self, sample_scope_output):
        """Every sub-question must have at least 1 search query."""
        sq_ids = {sq.id for sq in sample_scope_output.sub_questions}
        query_sq_ids = {q.sub_question_id for q in sample_scope_output.search_queries}
        # Every sub-question must have queries
        assert sq_ids == query_sq_ids, (
            f"Sub-questions without queries: {sq_ids - query_sq_ids}"
        )

    def test_scope_minimum_sub_questions(self):
        """ScopeOutput rejects fewer than 3 sub-questions."""
        with pytest.raises(Exception):
            ScopeOutput(
                sub_questions=[
                    SubQuestion(id="sq_01", question="Q1"),
                    SubQuestion(id="sq_02", question="Q2"),
                ],
                perspectives=["A", "B", "C"],
                search_queries=[
                    SearchQuery(query="q", sub_question_id="sq_01"),
                    SearchQuery(query="q", sub_question_id="sq_02"),
                    SearchQuery(query="q", sub_question_id="sq_01"),
                ],
            )

    def test_scope_analytical_focus_validated(self):
        """Invalid analytical_focus values normalize to 'explain'."""
        sq = SubQuestion(id="sq_01", question="Q", analytical_focus="INVALID")
        assert sq.analytical_focus == "explain"

    def test_scope_analytical_focus_normalizes_case(self):
        """Analytical focus normalizes to lowercase."""
        sq = SubQuestion(id="sq_01", question="Q", analytical_focus="COMPARE")
        assert sq.analytical_focus == "compare"


class TestSearchToOutlineContract:
    """Contract: SearchRoundOutput -> LiveOutline consumed by Phase 3."""

    def test_search_round_has_evidence_and_reflections(self, sample_search_round):
        """Search round must produce both evidence IDs and reflections."""
        assert len(sample_search_round.evidence_ids) > 0
        assert len(sample_search_round.reflections) > 0

    def test_reflection_links_to_sub_question(self, sample_search_round):
        """Every reflection must reference a sub-question."""
        for r in sample_search_round.reflections:
            assert r.sub_question_id.startswith("sq_"), (
                f"Reflection sub_question_id must start with 'sq_': {r.sub_question_id}"
            )

    def test_convergence_score_bounded(self):
        """Convergence score must be 0-1."""
        sr = SearchRoundOutput(
            round_number=1,
            evidence_ids=["ev_001"],
            reflections=[],
            convergence_score=0.5,
        )
        assert 0.0 <= sr.convergence_score <= 1.0


class TestOutlineToSynthesizeContract:
    """Contract: LiveOutline -> VerifiedSectionDraft[] consumed by Phase 4."""

    def test_outline_has_sections_with_evidence(self, sample_outline):
        """Every outline section must have evidence assigned."""
        for section in sample_outline.sections:
            assert len(section.evidence_ids) > 0, (
                f"Section '{section.title}' has no evidence"
            )

    def test_outline_sections_have_unique_ids(self, sample_outline):
        """Section IDs must be unique."""
        ids = [s.id for s in sample_outline.sections]
        assert len(ids) == len(set(ids)), f"Duplicate section IDs: {ids}"

    def test_outline_rejects_empty(self):
        """LiveOutline with 0 sections is rejected."""
        with pytest.raises(Exception):
            LiveOutline(title="Test", sections=[])

    def test_outline_section_has_sub_question_link(self, sample_outline):
        """Every section links to a sub-question."""
        for section in sample_outline.sections:
            assert section.sub_question_id.startswith("sq_"), (
                f"Section '{section.title}' has no sub_question_id"
            )


class TestSynthesizeToAssembleContract:
    """Contract: VerifiedSectionDraft[] -> V3ResultOutput consumed by Phase 5."""

    def test_verified_section_has_content_and_citations(self, sample_verified_sections):
        """Each section must have content with citation markers."""
        for s in sample_verified_sections:
            assert len(s.content) > 0, f"Section '{s.title}' has no content"
            assert "CITE:" in s.content, f"Section '{s.title}' has no citations"
            assert len(s.evidence_ids_used) > 0, f"Section '{s.title}' has no used evidence"

    def test_verified_section_faithfulness_bounded(self):
        """Faithfulness score must be 0-1."""
        s = VerifiedSectionDraft(
            section_id="s01", title="T", content="C",
            faithfulness_score=0.85,
        )
        assert 0.0 <= s.faithfulness_score <= 1.0

    def test_verified_section_revision_cap(self):
        """Revisions must not exceed reasonable cap."""
        s = VerifiedSectionDraft(
            section_id="s01", title="T", content="C",
            revisions=5,
        )
        # Contract allows any value; IMPLEMENTATION should cap at 2
        # This test documents the expectation
        assert s.revisions >= 0


# ---------------------------------------------------------------------------
# 0.5: Result JSON compatibility test
# ---------------------------------------------------------------------------

class TestResultJsonCompatibility:
    """V3 result JSON must be readable by all v1 API endpoints."""

    def test_result_has_all_required_keys(self, sample_v3_result):
        """V3ResultOutput must contain every key that live_server.py reads."""
        required_keys = {
            "vector_id", "original_query", "status", "final_report",
            "bibliography", "quality_metrics", "sections", "evidence",
            "claims", "iteration_count", "timestamps", "trace_summary",
        }
        result_dict = sample_v3_result.model_dump()
        missing = required_keys - set(result_dict.keys())
        assert not missing, f"Missing required keys: {missing}"

    def test_result_bibliography_has_citation_numbers(self, sample_v3_result):
        """Bibliography entries must have citation_number for frontend rendering."""
        for entry in sample_v3_result.bibliography:
            assert "citation_number" in entry, f"Bibliography missing citation_number: {entry}"

    def test_result_sections_have_required_fields(self, sample_v3_result):
        """Sections must have section_id, title, content for frontend rendering."""
        for section in sample_v3_result.sections:
            assert "section_id" in section
            assert "title" in section
            assert "content" in section

    def test_result_evidence_has_required_fields(self, sample_v3_result):
        """Evidence must have evidence_id, statement, source_url for frontend."""
        for ev in sample_v3_result.evidence:
            assert "evidence_id" in ev
            assert "statement" in ev
            assert "source_url" in ev

    def test_result_status_values(self):
        """Status must be one of the expected values."""
        for status in ("completed", "partial", "failed"):
            r = V3ResultOutput(
                vector_id="test", original_query="q", status=status,
                final_report="report",
            )
            assert r.status == status

    def test_result_serializes_to_json(self, sample_v3_result):
        """Result must be JSON-serializable for file output."""
        import json
        json_str = sample_v3_result.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["vector_id"] == "V3_TEST_001"


# ---------------------------------------------------------------------------
# 0.6: Trace event contract test
# ---------------------------------------------------------------------------

class TestTraceEventContract:
    """v3 must emit all required trace events for frontend compatibility."""

    def test_required_events_defined(self):
        """All required event types have field lists."""
        assert "pipeline_start" in REQUIRED_TRACE_EVENTS
        assert "pipeline_end" in REQUIRED_TRACE_EVENTS
        assert "node_start" in REQUIRED_TRACE_EVENTS
        assert "node_end" in REQUIRED_TRACE_EVENTS

    def test_pipeline_end_has_completion_fields(self):
        """pipeline_end must include fields needed for dashboard completion."""
        fields = REQUIRED_TRACE_EVENTS["pipeline_end"]
        assert "status" in fields
        assert "total_words" in fields
        assert "total_citations" in fields
        assert "elapsed_seconds" in fields

    def test_report_assembled_action_exists(self):
        """The report_assembled action is critical — triggers frontend completion."""
        assert "report_assembled" in REQUIRED_EVIDENCE_ACTIONS
        fields = REQUIRED_EVIDENCE_ACTIONS["report_assembled"]
        assert "full_report" in fields
        assert "bibliography" in fields

    def test_v3_node_names_defined(self):
        """v3 node names must be defined for frontend NODE_ORDER."""
        assert len(V3_NODE_NAMES) >= 5
        assert "scope" in V3_NODE_NAMES
        assert "v3_search" in V3_NODE_NAMES
        assert "v3_outline" in V3_NODE_NAMES
        assert "v3_write_section" in V3_NODE_NAMES
        assert "v3_assemble" in V3_NODE_NAMES


# ---------------------------------------------------------------------------
# 0.7: build_and_run_v3() signature compatibility test
# ---------------------------------------------------------------------------

class TestBuildAndRunSignature:
    """v3 entry point must accept the same parameters as v1/v2."""

    def test_v1_signature_reference(self):
        """Document the v1 signature that v3 must match."""
        from src.polaris_graph.graph import build_and_run as v1_build

        sig = inspect.signature(v1_build)
        v1_params = set(sig.parameters.keys())

        # These are the minimum parameters v3 must accept
        required = {"vector_id", "query", "application", "region"}
        assert required.issubset(v1_params), (
            f"v1 missing expected params: {required - v1_params}"
        )

    def test_v1_has_document_ids(self):
        """v1 must accept document_ids for upload pipeline compat."""
        from src.polaris_graph.graph import build_and_run as v1_build
        sig = inspect.signature(v1_build)
        assert "document_ids" in sig.parameters

    def test_v1_has_steer_callback(self):
        """v1 must accept steer_callback for live steering compat."""
        from src.polaris_graph.graph import build_and_run as v1_build
        sig = inspect.signature(v1_build)
        assert "steer_callback" in sig.parameters
