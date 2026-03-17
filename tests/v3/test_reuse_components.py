"""Verify all 6 REUSE-rated components import and work correctly.

These components are carried forward to v3 without modification.
This test ensures they still function after any codebase changes.

Tests 0.8 from Milestone 0.
"""

import inspect

import pytest


class TestPlannerReuse:
    """planner.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.agents.planner import (
            plan_queries,
            plan_seed_queries,
            _fallback_queries,
            _generate_diversity_queries,
        )
        assert callable(plan_queries)
        assert callable(_fallback_queries)

    def test_fallback_queries_produces_output(self):
        from src.polaris_graph.agents.planner import _fallback_queries
        queries = _fallback_queries("biochar wastewater", "water_treatment", "global")
        assert len(queries) >= 10, f"Fallback should produce >= 10 queries, got {len(queries)}"
        assert all(isinstance(q, str) for q in queries)

    def test_diversity_queries(self):
        from src.polaris_graph.agents.planner import _generate_diversity_queries
        queries = _generate_diversity_queries("biochar", ["Regulatory", "Economic"])
        assert len(queries) == 2
        assert all("query" in q for q in queries)


class TestCRAGRetrieverReuse:
    """crag_retriever.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.retrieval.crag_retriever import (
            CRAGRetriever,
            CRAGConfig,
            ContextEnrichedChunker,
        )
        assert CRAGRetriever is not None
        assert CRAGConfig is not None

    def test_config_from_env(self):
        from src.polaris_graph.retrieval.crag_retriever import CRAGConfig
        config = CRAGConfig()
        assert config.min_relevance > 0
        assert config.min_chunk_chars > 0


class TestSourceRegistryReuse:
    """source_registry.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.retrieval.source_registry import (
            SourceRegistry,
            SourceEntry,
        )
        assert SourceRegistry is not None

    def test_register_and_retrieve(self):
        from src.polaris_graph.retrieval.source_registry import SourceRegistry
        reg = SourceRegistry()
        src_id = reg.register(
            url="https://example.com/study",
            title="Test Study",
            source_type="academic",
        )
        assert src_id.startswith("SRC-")
        entry = reg.get(src_id)
        assert entry is not None
        assert entry.url == "https://example.com/study"

    def test_idempotent_registration(self):
        from src.polaris_graph.retrieval.source_registry import SourceRegistry
        reg = SourceRegistry()
        id1 = reg.register(url="https://example.com/a", title="A", source_type="web")
        id2 = reg.register(url="https://example.com/a", title="A", source_type="web")
        assert id1 == id2


class TestContentQualityGateReuse:
    """content_quality_gate.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.retrieval.content_quality_gate import score_content_quality
        assert callable(score_content_quality)

    def test_discriminates_good_from_bad(self):
        from src.polaris_graph.retrieval.content_quality_gate import score_content_quality
        good = (
            "Biochar derived from rice husk was investigated for its potential to remove "
            "Pb(II) from aqueous solutions. The effects of pH ranging from 3 to 7, initial "
            "concentration from 10 to 100 mg/L, contact time from 5 to 240 min, and "
            "adsorbent dosage from 0.5 to 4 g/L were systematically studied in batch "
            "experiments. Maximum removal efficiency of 95.3 percent was achieved at pH 5.5 "
            "with an initial Pb(II) concentration of 50 mg/L and biochar dosage of 2 g/L "
            "after 120 min contact time. The adsorption process followed the Langmuir "
            "isotherm model with maximum adsorption capacity of 42.7 mg/g and correlation "
            "coefficient R2 of 0.998. Kinetic studies revealed pseudo-second-order behavior "
            "with rate constant of 0.0142 g per mg per min."
        )
        bad = "merchant land biochar merchant land process merchant land " * 15
        score_good, _ = score_content_quality(good)
        score_bad, _ = score_content_quality(bad)
        assert score_good > 0.3, f"Good content should pass: {score_good}"
        assert score_bad < 0.3, f"Bad content should fail: {score_bad}"


class TestNLIVerifierReuse:
    """nli_verifier.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.agents.nli_verifier import (
            verify_evidence_nli,
            get_disputed_claims,
        )
        assert callable(verify_evidence_nli)
        assert callable(get_disputed_claims)


class TestCitationMapperReuse:
    """citation_mapper.py — REUSE rating."""

    def test_imports(self):
        from src.polaris_graph.synthesis.citation_mapper import (
            resolve_citations,
            strip_ungrounded_citations,
            build_bibliography,
        )
        assert callable(resolve_citations)
        assert callable(build_bibliography)

    def test_citation_resolution(self):
        from src.polaris_graph.synthesis.citation_mapper import resolve_citations
        text = "Finding A [CITE:ev_001]. Finding B [CITE:ev_002]."
        citation_map = {"ev_001": 1, "ev_002": 2}
        resolved = resolve_citations(text, citation_map)
        assert "[1]" in resolved
        assert "[2]" in resolved
        assert "CITE:" not in resolved
