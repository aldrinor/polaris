"""
Unit tests for POLARIS v3 Orchestration State Module.

Tests:
- ResearchState creation and structure
- State serialization and deserialization
- StatePersistence save/load operations
- Edge cases and error handling
"""

import json
import os
import pytest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.state import (
    ResearchState,
    SubQuery,
    SearchResult,
    Evidence,
    Gap,
    VerificationResult,
    QualityMetrics,
    create_initial_state,
    serialize_state,
    deserialize_state,
)
from src.orchestration.persistence import (
    StatePersistence,
    save_state,
    load_state,
    get_persistence,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_state_dir():
    """Create a temporary directory for state persistence tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_state() -> ResearchState:
    """Create a sample ResearchState for testing."""
    return create_initial_state(
        vector_id="TEST_V001",
        query="What are the health effects of microplastics in drinking water?",
        application="Food Contact Materials",
        region="EU",
        stage=5,
        max_iterations=3
    )


@pytest.fixture
def sample_sub_query() -> SubQuery:
    """Create a sample SubQuery for testing."""
    return SubQuery(
        query_id="sq_001",
        query_text="What concentration of microplastics is found in tap water?",
        expected_data_type="statistical",
        priority=1,
        search_keywords=["microplastics", "tap water", "concentration", "ppb"],
        domain_hints=["who.int", "epa.gov"],
        status="pending"
    )


@pytest.fixture
def sample_search_result() -> SearchResult:
    """Create a sample SearchResult for testing."""
    return SearchResult(
        result_id="sr_001",
        url="https://example.com/study",
        title="Microplastics in Drinking Water Study",
        snippet="Study finds average of 10.4 particles per liter...",
        source_type="academic",
        domain="example.com",
        fetch_status="success",
        content="Full content of the study...",
        metadata={"authors": ["Smith", "Jones"], "year": 2024}
    )


@pytest.fixture
def sample_evidence() -> Evidence:
    """Create a sample Evidence for testing."""
    return Evidence(
        evidence_id="ev_001",
        chunk_id="chunk_001",
        source_url="https://example.com/study",
        text="Average microplastic concentration was 10.4 particles per liter.",
        relevance_score=0.9,
        source_quality_score=0.85,
        extraction_method="dense",
        claims=["10.4 particles per liter average"],
        entities=["microplastics", "concentration", "drinking water"]
    )


# =============================================================================
# State Creation Tests
# =============================================================================

class TestStateCreation:
    """Tests for ResearchState creation."""

    def test_create_initial_state_basic(self):
        """Test creating a basic initial state."""
        state = create_initial_state(
            vector_id="V001",
            query="Test query",
            application="Test App",
            region="US",
            stage=1
        )

        assert state["vector_id"] == "V001"
        assert state["original_query"] == "Test query"
        assert state["application"] == "Test App"
        assert state["region"] == "US"
        assert state["stage"] == 1
        assert state["iteration_count"] == 0
        assert state["converged"] is False
        assert isinstance(state["timestamps"], dict)
        assert "created" in state["timestamps"]

    def test_create_initial_state_with_max_iterations(self):
        """Test creating state with custom max iterations."""
        state = create_initial_state(
            vector_id="V002",
            query="Test query",
            application="Test App",
            region="GLOBAL",
            stage=3,
            max_iterations=10
        )

        assert state["max_iterations"] == 10

    def test_create_initial_state_defaults(self):
        """Test that default values are set correctly."""
        state = create_initial_state(
            vector_id="V003",
            query="Test",
            application="App",
            region="EU",
            stage=2
        )

        assert state["sub_queries"] == []
        assert state["search_results"] == []
        assert state["evidence_chain"] == []
        assert state["errors"] == []
        assert state["gaps"] == []
        assert state["max_iterations"] == 5


# =============================================================================
# SubQuery Tests
# =============================================================================

class TestSubQuery:
    """Tests for SubQuery model."""

    def test_sub_query_creation(self, sample_sub_query):
        """Test SubQuery model creation."""
        sq = sample_sub_query
        assert sq.query_id == "sq_001"
        assert sq.expected_data_type == "statistical"
        assert sq.priority == 1
        assert "microplastics" in sq.search_keywords
        assert sq.status == "pending"

    def test_sub_query_dict_conversion(self, sample_sub_query):
        """Test SubQuery converts to dict correctly."""
        sq_dict = sample_sub_query.model_dump()
        assert isinstance(sq_dict, dict)
        assert sq_dict["query_id"] == "sq_001"
        assert isinstance(sq_dict["search_keywords"], list)

    def test_sub_query_priority_validation(self):
        """Test SubQuery priority bounds."""
        # Valid priorities
        for p in [1, 2, 3, 4, 5]:
            sq = SubQuery(
                query_id="test",
                query_text="test",
                expected_data_type="factual",
                priority=p,
                search_keywords=["test"]
            )
            assert sq.priority == p


# =============================================================================
# SearchResult Tests
# =============================================================================

class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self, sample_search_result):
        """Test SearchResult model creation."""
        sr = sample_search_result
        assert sr.result_id == "sr_001"
        assert sr.url == "https://example.com/study"
        assert sr.source_type == "academic"
        assert sr.fetch_status == "success"
        assert sr.content == "Full content of the study..."

    def test_search_result_optional_fields(self):
        """Test SearchResult with minimal fields."""
        sr = SearchResult(
            result_id="sr_002",
            url="https://test.com",
            title="Test",
            snippet="Snippet",
            source_type="news",
            domain="test.com",
            fetch_status="pending"
        )
        assert sr.content is None
        assert sr.metadata == {}


# =============================================================================
# Evidence Tests
# =============================================================================

class TestEvidence:
    """Tests for Evidence model."""

    def test_evidence_creation(self, sample_evidence):
        """Test Evidence model creation."""
        ev = sample_evidence
        assert ev.evidence_id == "ev_001"
        assert "microplastics" in ev.entities
        assert ev.source_quality_score == 0.85

    def test_evidence_scores_in_range(self, sample_evidence):
        """Test evidence scores are valid."""
        ev = sample_evidence
        assert 0.0 <= ev.relevance_score <= 1.0
        assert 0.0 <= ev.source_quality_score <= 1.0


# =============================================================================
# QualityMetrics Tests
# =============================================================================

class TestQualityMetrics:
    """Tests for QualityMetrics model."""

    def test_quality_metrics_creation(self):
        """Test QualityMetrics model creation."""
        qm = QualityMetrics(
            faithfulness=0.85,
            context_precision=0.78,
            answer_relevancy=0.92,
            source_diversity=5,
            claim_coverage=0.80
        )
        assert qm.faithfulness == 0.85
        assert qm.source_diversity == 5

    def test_quality_metrics_bounds(self):
        """Test QualityMetrics score bounds."""
        qm = QualityMetrics(
            faithfulness=0.0,
            context_precision=1.0,
            answer_relevancy=0.5,
            source_diversity=0,
            claim_coverage=0.0
        )
        assert qm.faithfulness == 0.0
        assert qm.context_precision == 1.0


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Tests for state serialization and deserialization."""

    def test_serialize_basic_state(self, sample_state):
        """Test serializing a basic state."""
        serialized = serialize_state(sample_state)
        assert isinstance(serialized, dict)
        assert serialized["vector_id"] == "TEST_V001"
        assert serialized["region"] == "EU"

    def test_serialize_state_with_sub_queries(self, sample_state, sample_sub_query):
        """Test serializing state with sub-queries."""
        sample_state["sub_queries"] = [sample_sub_query]
        serialized = serialize_state(sample_state)

        assert len(serialized["sub_queries"]) == 1
        assert serialized["sub_queries"][0]["query_id"] == "sq_001"

    def test_serialize_state_with_evidence(self, sample_state, sample_evidence):
        """Test serializing state with evidence."""
        sample_state["evidence_chain"] = [sample_evidence]
        serialized = serialize_state(sample_state)

        assert len(serialized["evidence_chain"]) == 1
        assert serialized["evidence_chain"][0]["evidence_id"] == "ev_001"

    def test_deserialize_basic_state(self, sample_state):
        """Test deserializing a basic state."""
        serialized = serialize_state(sample_state)
        deserialized = deserialize_state(serialized)

        assert deserialized["vector_id"] == sample_state["vector_id"]
        assert deserialized["original_query"] == sample_state["original_query"]

    def test_roundtrip_serialization(self, sample_state, sample_sub_query, sample_evidence):
        """Test that serialization is reversible."""
        sample_state["sub_queries"] = [sample_sub_query]
        sample_state["evidence_chain"] = [sample_evidence]

        serialized = serialize_state(sample_state)
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        deserialized = deserialize_state(parsed)

        assert deserialized["vector_id"] == sample_state["vector_id"]
        assert len(deserialized["sub_queries"]) == 1
        assert len(deserialized["evidence_chain"]) == 1

    def test_serialize_with_quality_metrics(self, sample_state):
        """Test serializing state with quality metrics."""
        sample_state["quality_metrics"] = QualityMetrics(
            faithfulness=0.8,
            context_precision=0.7,
            answer_relevancy=0.9,
            source_diversity=3,
            claim_coverage=0.6
        )
        serialized = serialize_state(sample_state)

        assert serialized["quality_metrics"]["faithfulness"] == 0.8


# =============================================================================
# Persistence Tests
# =============================================================================

class TestStatePersistence:
    """Tests for StatePersistence class."""

    def test_persistence_init(self, temp_state_dir):
        """Test StatePersistence initialization."""
        persistence = StatePersistence(temp_state_dir)
        assert persistence.base_dir == Path(temp_state_dir)

    def test_save_and_load_state(self, temp_state_dir, sample_state):
        """Test saving and loading state."""
        persistence = StatePersistence(temp_state_dir)

        # Save
        filepath = persistence.save(sample_state)
        assert os.path.exists(filepath)

        # Load
        loaded = persistence.load("TEST_V001")
        assert loaded is not None
        assert loaded["vector_id"] == "TEST_V001"
        assert loaded["original_query"] == sample_state["original_query"]

    def test_save_with_checkpoint(self, temp_state_dir, sample_state):
        """Test saving with checkpoint name."""
        persistence = StatePersistence(temp_state_dir)

        filepath = persistence.save(sample_state, checkpoint_name="after_triage")
        # Main state file is saved
        assert os.path.exists(filepath)
        # Checkpoint history is also saved
        history = persistence.get_checkpoint_history("TEST_V001")
        assert len(history) >= 1
        assert any("after_triage" in cp["name"] for cp in history)

    def test_exists(self, temp_state_dir, sample_state):
        """Test checking if state exists."""
        persistence = StatePersistence(temp_state_dir)

        assert not persistence.exists("TEST_V001")
        persistence.save(sample_state)
        assert persistence.exists("TEST_V001")

    def test_delete(self, temp_state_dir, sample_state):
        """Test deleting state."""
        persistence = StatePersistence(temp_state_dir)

        persistence.save(sample_state)
        assert persistence.exists("TEST_V001")

        persistence.delete("TEST_V001")
        assert not persistence.exists("TEST_V001")

    def test_list_vectors(self, temp_state_dir):
        """Test listing all vectors."""
        persistence = StatePersistence(temp_state_dir)

        # Create multiple states
        for i in range(3):
            state = create_initial_state(
                vector_id=f"V{i:03d}",
                query=f"Query {i}",
                application="App",
                region="US",
                stage=1
            )
            persistence.save(state)

        vectors = persistence.list_vectors()
        assert len(vectors) == 3
        assert "V000" in vectors
        assert "V001" in vectors
        assert "V002" in vectors

    def test_load_nonexistent(self, temp_state_dir):
        """Test loading a nonexistent state returns None."""
        persistence = StatePersistence(temp_state_dir)
        loaded = persistence.load("NONEXISTENT")
        assert loaded is None

    def test_get_checkpoint_history(self, temp_state_dir, sample_state):
        """Test getting checkpoint history."""
        persistence = StatePersistence(temp_state_dir)

        # Save multiple checkpoints
        persistence.save(sample_state, checkpoint_name="cp1")
        sample_state["iteration_count"] = 1
        persistence.save(sample_state, checkpoint_name="cp2")
        sample_state["iteration_count"] = 2
        persistence.save(sample_state, checkpoint_name="cp3")

        history = persistence.get_checkpoint_history("TEST_V001")
        assert len(history) >= 3


# =============================================================================
# Module-level Function Tests
# =============================================================================

class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_save_state_function(self, temp_state_dir, sample_state):
        """Test save_state module function."""
        # Temporarily override the default persistence
        original_persistence = get_persistence()

        # Use temp dir
        import src.orchestration.persistence as persistence_module
        persistence_module._default_persistence = StatePersistence(temp_state_dir)

        try:
            filepath = save_state(sample_state)
            assert os.path.exists(filepath)
        finally:
            persistence_module._default_persistence = original_persistence

    def test_load_state_function(self, temp_state_dir, sample_state):
        """Test load_state module function."""
        import src.orchestration.persistence as persistence_module
        original_persistence = get_persistence()
        persistence_module._default_persistence = StatePersistence(temp_state_dir)

        try:
            save_state(sample_state)
            loaded = load_state("TEST_V001")
            assert loaded is not None
            assert loaded["vector_id"] == "TEST_V001"
        finally:
            persistence_module._default_persistence = original_persistence


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_state_serialization(self):
        """Test serializing a minimal state."""
        state = create_initial_state(
            vector_id="EMPTY",
            query="",
            application="",
            region="",
            stage=0
        )
        serialized = serialize_state(state)
        assert serialized["vector_id"] == "EMPTY"

    def test_state_with_special_characters(self):
        """Test state with special characters in query."""
        state = create_initial_state(
            vector_id="SPECIAL",
            query="What's the effect of \"quoted\" terms & special <chars>?",
            application="Test's App",
            region="US",
            stage=1
        )
        serialized = serialize_state(state)
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        deserialized = deserialize_state(parsed)

        assert "quoted" in deserialized["original_query"]
        assert "&" in deserialized["original_query"]

    def test_state_with_unicode(self):
        """Test state with unicode characters."""
        state = create_initial_state(
            vector_id="UNICODE",
            query="What are the effects of café culture on health?",
            application="Beverages",
            region="FR",
            stage=1
        )
        serialized = serialize_state(state)
        deserialized = deserialize_state(serialized)

        assert "café" in deserialized["original_query"]

    def test_large_state(self):
        """Test state with many items."""
        state = create_initial_state(
            vector_id="LARGE",
            query="Large state test",
            application="Test",
            region="GLOBAL",
            stage=1
        )

        # Add many sub-queries
        state["sub_queries"] = [
            SubQuery(
                query_id=f"sq_{i:03d}",
                query_text=f"Sub-query {i}",
                expected_data_type="factual",
                priority=1,
                search_keywords=[f"keyword_{i}"]
            )
            for i in range(100)
        ]

        serialized = serialize_state(state)
        deserialized = deserialize_state(serialized)

        assert len(deserialized["sub_queries"]) == 100


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
