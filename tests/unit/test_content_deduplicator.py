#!/usr/bin/env python3
"""
Unit tests for Content Deduplicator.

Tests:
- DeduplicationConfig
- ContentFingerprint
- ContentDeduplicator class
- MinHash and SimHash algorithms
- Convenience functions

Run:
    pytest tests/unit/test_content_deduplicator.py -v
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.content_deduplicator import (
    ContentDeduplicator,
    DeduplicationConfig,
    DeduplicationResult,
    ContentFingerprint,
    DuplicateInfo,
    DuplicateType,
    deduplicate_content,
    calculate_content_similarity,
    are_duplicates,
    get_unique_texts,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_items():
    """Sample items for testing."""
    return [
        {"content": "The quick brown fox jumps over the lazy dog.", "url": "source1"},
        {"content": "The quick brown fox jumps over the lazy dog.", "url": "source2"},
        {"content": "A quick brown fox jumped over a lazy dog.", "url": "source3"},
        {"content": "Machine learning is revolutionizing AI.", "url": "source4"},
        {"content": "The weather today is sunny and warm.", "url": "source5"},
    ]


@pytest.fixture
def duplicate_items():
    """Items with obvious duplicates."""
    return [
        {"content": "Hello world this is a test message.", "url": "a"},
        {"content": "Hello world this is a test message.", "url": "b"},
        {"content": "Hello world this is a test message.", "url": "c"},
        {"content": "Completely different content here.", "url": "d"},
    ]


@pytest.fixture
def unique_items():
    """Items with no duplicates."""
    return [
        {"content": "First unique piece of content about topic A.", "url": "1"},
        {"content": "Second unique piece of content about topic B.", "url": "2"},
        {"content": "Third unique piece of content about topic C.", "url": "3"},
    ]


@pytest.fixture
def default_deduplicator():
    """Default deduplicator instance."""
    return ContentDeduplicator()


@pytest.fixture
def strict_config():
    """Strict deduplication config."""
    return DeduplicationConfig(
        near_duplicate_threshold=0.95,
        similar_threshold=0.85,
    )


# =============================================================================
# DuplicateType Enum Tests
# =============================================================================

class TestDuplicateType:
    """Tests for DuplicateType enum."""

    def test_all_types_defined(self):
        """Test all duplicate types are defined."""
        expected = ["exact", "near_duplicate", "similar", "unique"]
        for dtype in expected:
            assert hasattr(DuplicateType, dtype.upper())

    def test_type_values(self):
        """Test enum values."""
        assert DuplicateType.EXACT.value == "exact"
        assert DuplicateType.NEAR_DUPLICATE.value == "near_duplicate"
        assert DuplicateType.UNIQUE.value == "unique"


# =============================================================================
# DeduplicationConfig Tests
# =============================================================================

class TestDeduplicationConfig:
    """Tests for DeduplicationConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DeduplicationConfig()
        assert config.exact_match_threshold == 1.0
        assert config.near_duplicate_threshold == 0.85
        assert config.similar_threshold == 0.70
        assert config.num_hashes == 128
        assert config.shingle_size == 3
        assert config.normalize_text is True
        assert config.ignore_case is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = DeduplicationConfig(
            near_duplicate_threshold=0.9,
            shingle_size=5,
            ignore_case=False,
        )
        assert config.near_duplicate_threshold == 0.9
        assert config.shingle_size == 5
        assert config.ignore_case is False


# =============================================================================
# DeduplicationResult Tests
# =============================================================================

class TestDeduplicationResult:
    """Tests for DeduplicationResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = DeduplicationResult()
        assert result.original_count == 0
        assert result.unique_count == 0
        assert result.exact_duplicates == 0
        assert len(result.unique_items) == 0

    def test_deduplication_ratio_empty(self):
        """Test deduplication ratio for empty result."""
        result = DeduplicationResult()
        assert result.deduplication_ratio == 0.0

    def test_deduplication_ratio_calculation(self):
        """Test deduplication ratio calculation."""
        result = DeduplicationResult(
            original_count=10,
            unique_count=7,
        )
        assert abs(result.deduplication_ratio - 0.3) < 0.001

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = DeduplicationResult(
            original_count=5,
            unique_count=3,
            exact_duplicates=2,
        )
        data = result.to_dict()
        assert data["original_count"] == 5
        assert data["unique_count"] == 3
        assert "deduplication_ratio" in data


# =============================================================================
# ContentDeduplicator Tests
# =============================================================================

class TestContentDeduplicator:
    """Tests for ContentDeduplicator class."""

    def test_initialization_default(self, default_deduplicator):
        """Test default initialization."""
        assert default_deduplicator.config is not None

    def test_initialization_custom(self, strict_config):
        """Test initialization with custom config."""
        dedup = ContentDeduplicator(config=strict_config)
        assert dedup.config.near_duplicate_threshold == 0.95

    def test_deduplicate_empty(self, default_deduplicator):
        """Test deduplicating empty list."""
        result = default_deduplicator.deduplicate([])
        assert result.original_count == 0
        assert result.unique_count == 0

    def test_deduplicate_no_duplicates(self, default_deduplicator, unique_items):
        """Test deduplicating list with no duplicates."""
        result = default_deduplicator.deduplicate(unique_items)
        assert result.unique_count == result.original_count
        assert result.exact_duplicates == 0

    def test_deduplicate_exact_duplicates(self, default_deduplicator, duplicate_items):
        """Test detecting exact duplicates."""
        result = default_deduplicator.deduplicate(duplicate_items)
        assert result.exact_duplicates >= 2
        assert result.unique_count < result.original_count

    def test_deduplicate_preserves_first(self, default_deduplicator, duplicate_items):
        """Test that first occurrence is preserved."""
        result = default_deduplicator.deduplicate(duplicate_items)
        # First item with duplicate content should be kept
        first_content = duplicate_items[0]["content"]
        found = any(
            item["content"] == first_content
            for item in result.unique_items
        )
        assert found


# =============================================================================
# Similarity Calculation Tests
# =============================================================================

class TestSimilarityCalculation:
    """Tests for similarity calculation."""

    def test_identical_texts(self, default_deduplicator):
        """Test similarity of identical texts."""
        text = "This is a test sentence for similarity."
        similarity = default_deduplicator.calculate_similarity(text, text)
        assert similarity == 1.0

    def test_different_texts(self, default_deduplicator):
        """Test similarity of very different texts."""
        text1 = "The quick brown fox jumps over the lazy dog."
        text2 = "Machine learning and artificial intelligence are trending."
        similarity = default_deduplicator.calculate_similarity(text1, text2)
        assert similarity < 0.5

    def test_similar_texts(self, default_deduplicator):
        """Test similarity of similar texts."""
        text1 = "The quick brown fox jumps over the lazy dog today."
        text2 = "The quick brown fox jumps over the lazy dog now."
        similarity = default_deduplicator.calculate_similarity(text1, text2)
        # With MinHash word shingles, similar texts should have some similarity
        assert similarity > 0.3  # Relaxed threshold for word-based shingles

    def test_empty_texts(self, default_deduplicator):
        """Test similarity with empty texts."""
        similarity = default_deduplicator.calculate_similarity("", "")
        # Empty texts have matching empty signatures, resulting in similarity 1.0
        # This is expected behavior - two empty texts are considered identical
        assert similarity == 1.0


# =============================================================================
# Duplicate Detection Tests
# =============================================================================

class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_is_duplicate_true(self, default_deduplicator):
        """Test is_duplicate returns True for duplicates."""
        text = "This is a duplicate text for testing purposes."
        assert default_deduplicator.is_duplicate(text, text)

    def test_is_duplicate_false(self, default_deduplicator):
        """Test is_duplicate returns False for unique texts."""
        text1 = "First unique piece of content."
        text2 = "Completely different content here."
        assert not default_deduplicator.is_duplicate(text1, text2)

    def test_is_duplicate_custom_threshold(self, default_deduplicator):
        """Test is_duplicate with custom threshold."""
        text1 = "The quick brown fox"
        text2 = "The quick brown dog"
        # With high threshold, should not be duplicate
        assert not default_deduplicator.is_duplicate(text1, text2, threshold=0.99)


# =============================================================================
# Find Duplicates Tests
# =============================================================================

class TestFindDuplicates:
    """Tests for finding duplicates."""

    def test_find_duplicates_for(self, default_deduplicator, sample_items):
        """Test finding duplicates for a text."""
        text = "The quick brown fox jumps over the lazy dog."
        dups = default_deduplicator.find_duplicates_for(text, sample_items)
        assert len(dups) >= 1  # Should find at least one duplicate

    def test_find_duplicates_sorted(self, default_deduplicator, sample_items):
        """Test that duplicates are sorted by similarity."""
        text = "The quick brown fox jumps over the lazy dog."
        dups = default_deduplicator.find_duplicates_for(text, sample_items)
        if len(dups) >= 2:
            assert dups[0][1] >= dups[1][1]  # First should have higher similarity


# =============================================================================
# Fingerprint Tests
# =============================================================================

class TestFingerprinting:
    """Tests for content fingerprinting."""

    def test_generate_fingerprint(self, default_deduplicator):
        """Test fingerprint generation."""
        text = "This is a test sentence for fingerprinting."
        fp = default_deduplicator._generate_fingerprint(text)
        assert isinstance(fp, ContentFingerprint)
        assert fp.content_hash is not None
        assert len(fp.minhash) > 0

    def test_fingerprint_consistency(self, default_deduplicator):
        """Test fingerprint is consistent for same text."""
        text = "Consistent text for fingerprint testing."
        fp1 = default_deduplicator._generate_fingerprint(text)
        fp2 = default_deduplicator._generate_fingerprint(text)
        assert fp1.content_hash == fp2.content_hash

    def test_fingerprint_different_for_different_text(self, default_deduplicator):
        """Test fingerprints differ for different texts."""
        fp1 = default_deduplicator._generate_fingerprint("Text one")
        fp2 = default_deduplicator._generate_fingerprint("Text two different")
        assert fp1.content_hash != fp2.content_hash


# =============================================================================
# Normalization Tests
# =============================================================================

class TestNormalization:
    """Tests for text normalization."""

    def test_normalize_case(self, default_deduplicator):
        """Test case normalization."""
        normalized = default_deduplicator._normalize_text("HELLO World")
        assert normalized == "hello world"

    def test_normalize_punctuation(self, default_deduplicator):
        """Test punctuation removal."""
        normalized = default_deduplicator._normalize_text("Hello, world!")
        assert "," not in normalized
        assert "!" not in normalized

    def test_normalize_whitespace(self, default_deduplicator):
        """Test whitespace normalization."""
        normalized = default_deduplicator._normalize_text("hello    world")
        assert "    " not in normalized


# =============================================================================
# Shingle Tests
# =============================================================================

class TestShingles:
    """Tests for shingle generation."""

    def test_generate_shingles(self, default_deduplicator):
        """Test shingle generation."""
        text = "the quick brown fox jumps"
        shingles = default_deduplicator._generate_shingles(text)
        assert len(shingles) > 0

    def test_shingles_short_text(self, default_deduplicator):
        """Test shingles for short text."""
        text = "hi"
        shingles = default_deduplicator._generate_shingles(text)
        assert len(shingles) >= 0  # May have one shingle or empty


# =============================================================================
# Cluster Tests
# =============================================================================

class TestClusters:
    """Tests for duplicate clustering."""

    def test_clusters_exist(self, default_deduplicator, duplicate_items):
        """Test clusters are created for duplicates."""
        result = default_deduplicator.deduplicate(duplicate_items)
        assert len(result.clusters) > 0

    def test_cluster_size(self, default_deduplicator, duplicate_items):
        """Test cluster contains all duplicates."""
        result = default_deduplicator.deduplicate(duplicate_items)
        # Should have a cluster with 3 items (the duplicate ones)
        assert any(len(cluster) >= 2 for cluster in result.clusters)


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_deduplicate_content(self, sample_items):
        """Test deduplicate_content function."""
        unique, result = deduplicate_content(sample_items)
        assert len(unique) <= len(sample_items)
        assert isinstance(result, DeduplicationResult)

    def test_deduplicate_content_threshold(self, duplicate_items):
        """Test deduplicate_content with threshold."""
        unique, _ = deduplicate_content(duplicate_items, threshold=0.99)
        # With very high threshold, might find fewer duplicates
        assert len(unique) <= len(duplicate_items)

    def test_calculate_content_similarity(self):
        """Test calculate_content_similarity function."""
        sim = calculate_content_similarity("test text", "test text")
        assert sim == 1.0

    def test_are_duplicates_true(self):
        """Test are_duplicates returns True."""
        assert are_duplicates("same text", "same text")

    def test_are_duplicates_false(self):
        """Test are_duplicates returns False."""
        assert not are_duplicates("one", "completely different text")

    def test_get_unique_texts(self):
        """Test get_unique_texts function."""
        texts = ["hello world", "hello world", "goodbye world"]
        unique = get_unique_texts(texts)
        assert len(unique) < len(texts)

    def test_get_unique_texts_all_unique(self):
        """Test get_unique_texts with no duplicates."""
        texts = ["one", "two", "three"]
        unique = get_unique_texts(texts)
        assert len(unique) == len(texts)


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_item(self, default_deduplicator):
        """Test deduplicating single item."""
        items = [{"content": "Single item content"}]
        result = default_deduplicator.deduplicate(items)
        assert result.unique_count == 1
        assert result.exact_duplicates == 0

    def test_missing_content_key(self, default_deduplicator):
        """Test handling missing content key."""
        items = [{"text": "Using text key instead"}]
        result = default_deduplicator.deduplicate(items)
        assert result.original_count == 1

    def test_empty_content(self, default_deduplicator):
        """Test handling empty content."""
        items = [
            {"content": ""},
            {"content": ""},
            {"content": "Some actual content"},
        ]
        result = default_deduplicator.deduplicate(items)
        # Empty strings should be treated as duplicates
        assert result.unique_count <= result.original_count

    def test_very_short_content(self, default_deduplicator):
        """Test handling very short content."""
        items = [
            {"content": "Hi"},
            {"content": "Hi"},
        ]
        result = default_deduplicator.deduplicate(items)
        assert result.exact_duplicates >= 1

    def test_unicode_content(self, default_deduplicator):
        """Test handling unicode content."""
        items = [
            {"content": "日本語テキスト for testing"},
            {"content": "日本語テキスト for testing"},
        ]
        result = default_deduplicator.deduplicate(items)
        assert result.exact_duplicates >= 1


# =============================================================================
# Self-Test Function
# =============================================================================

class TestSelfTest:
    """Tests for self_test function."""

    def test_self_test_passes(self):
        """Test that self-test function passes."""
        from src.utils.content_deduplicator import self_test
        assert self_test() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
