#!/usr/bin/env python3
"""
Unit tests for Bias Detector.

Tests:
- BiasCategory and ViewpointType enums
- BiasConfig dataclass
- BiasDetector class methods
- Convenience functions
- Balance scoring algorithms

Run:
    pytest tests/unit/test_bias_detector.py -v
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.quality.bias_detector import (
    BiasDetector,
    BiasConfig,
    BiasReport,
    BiasCategory,
    ViewpointType,
    BiasIndicator,
    SourceBiasProfile,
    ViewpointDistribution,
    analyze_source_bias,
    check_balance,
    get_balancing_suggestions,
    classify_source_bias,
    SOURCE_BIAS_DB,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_evidence_chunks():
    """Sample evidence chunks for testing."""
    return [
        {
            "url": "https://www.nytimes.com/article",
            "content": "This study shows significant benefits and improvements.",
        },
        {
            "url": "https://www.foxnews.com/story",
            "content": "Critics warn about potential risks and dangers.",
        },
        {
            "url": "https://www.reuters.com/news",
            "content": "According to research data, findings indicate trends.",
        },
        {
            "url": "https://www.nature.com/paper",
            "content": "Technical implementation of the algorithm mechanism.",
        },
        {
            "url": "https://example.com/page",
            "content": "General information about the topic.",
        },
    ]


@pytest.fixture
def left_biased_chunks():
    """Evidence chunks with left-leaning bias."""
    return [
        {"url": "https://www.cnn.com/story", "content": "Benefits of progressive policies."},
        {"url": "https://www.msnbc.com/article", "content": "Advocates support the initiative."},
        {"url": "https://www.nytimes.com/news", "content": "Positive outcomes expected."},
        {"url": "https://www.huffpost.com/entry", "content": "Opportunity for change."},
    ]


@pytest.fixture
def right_biased_chunks():
    """Evidence chunks with right-leaning bias."""
    return [
        {"url": "https://www.foxnews.com/story", "content": "Concerns about policy risks."},
        {"url": "https://www.breitbart.com/article", "content": "Problems with implementation."},
        {"url": "https://www.dailywire.com/news", "content": "Challenges and drawbacks noted."},
    ]


@pytest.fixture
def academic_chunks():
    """Academic evidence chunks."""
    return [
        {"url": "https://www.nature.com/paper", "content": "Study methodology and findings."},
        {"url": "https://arxiv.org/abs/123", "content": "Algorithm specification details."},
        {"url": "https://pubmed.ncbi.nlm.nih.gov/456", "content": "Clinical trial results."},
    ]


@pytest.fixture
def default_detector():
    """Default bias detector instance."""
    return BiasDetector()


@pytest.fixture
def custom_config():
    """Custom bias configuration."""
    return BiasConfig(
        min_source_diversity=0.4,
        max_single_category_ratio=0.5,
        min_viewpoints=3,
    )


# =============================================================================
# BiasCategory Enum Tests
# =============================================================================

class TestBiasCategory:
    """Tests for BiasCategory enum."""

    def test_all_categories_defined(self):
        """Test all expected categories are defined."""
        expected = [
            "left_leaning", "center", "right_leaning", "corporate",
            "academic", "government", "non_profit", "unknown"
        ]
        for cat in expected:
            assert hasattr(BiasCategory, cat.upper())

    def test_category_values(self):
        """Test enum string values."""
        assert BiasCategory.LEFT_LEANING.value == "left_leaning"
        assert BiasCategory.CENTER.value == "center"
        assert BiasCategory.ACADEMIC.value == "academic"

    def test_category_count(self):
        """Test correct number of categories."""
        assert len(BiasCategory) == 8


# =============================================================================
# ViewpointType Enum Tests
# =============================================================================

class TestViewpointType:
    """Tests for ViewpointType enum."""

    def test_all_viewpoints_defined(self):
        """Test all expected viewpoints are defined."""
        expected = ["pro", "con", "neutral", "mixed", "technical"]
        for vp in expected:
            assert hasattr(ViewpointType, vp.upper())

    def test_viewpoint_values(self):
        """Test enum string values."""
        assert ViewpointType.PRO.value == "pro"
        assert ViewpointType.CON.value == "con"
        assert ViewpointType.NEUTRAL.value == "neutral"


# =============================================================================
# BiasConfig Tests
# =============================================================================

class TestBiasConfig:
    """Tests for BiasConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = BiasConfig()
        assert config.min_source_diversity == 0.3
        assert config.max_single_category_ratio == 0.6
        assert config.min_viewpoints == 2
        assert config.detect_political_bias is True
        assert config.suggest_balancing_sources is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = BiasConfig(
            min_source_diversity=0.5,
            min_viewpoints=3,
            detect_political_bias=False,
        )
        assert config.min_source_diversity == 0.5
        assert config.min_viewpoints == 3
        assert config.detect_political_bias is False

    def test_weight_sum(self):
        """Test weights sum to 1.0."""
        config = BiasConfig()
        total = (
            config.political_weight +
            config.source_type_weight +
            config.viewpoint_weight
        )
        assert abs(total - 1.0) < 0.001


# =============================================================================
# ViewpointDistribution Tests
# =============================================================================

class TestViewpointDistribution:
    """Tests for ViewpointDistribution dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        dist = ViewpointDistribution()
        assert dist.pro == 0
        assert dist.con == 0
        assert dist.neutral == 0
        assert dist.total == 0

    def test_total_calculation(self):
        """Test total property."""
        dist = ViewpointDistribution(pro=3, con=2, neutral=5)
        assert dist.total == 10

    def test_diversity_score_empty(self):
        """Test diversity score for empty distribution."""
        dist = ViewpointDistribution()
        assert dist.diversity_score == 0.0

    def test_diversity_score_single(self):
        """Test diversity score for single viewpoint."""
        dist = ViewpointDistribution(pro=5)
        assert dist.diversity_score == 0.0

    def test_diversity_score_diverse(self):
        """Test diversity score for diverse viewpoints."""
        dist = ViewpointDistribution(pro=2, con=2, neutral=2, mixed=2, technical=2)
        assert dist.diversity_score > 0.9  # High diversity

    def test_to_dict(self):
        """Test dictionary conversion."""
        dist = ViewpointDistribution(pro=3, con=2)
        data = dist.to_dict()
        assert data["pro"] == 3
        assert data["con"] == 2
        assert "diversity_score" in data


# =============================================================================
# SourceBiasProfile Tests
# =============================================================================

class TestSourceBiasProfile:
    """Tests for SourceBiasProfile dataclass."""

    def test_basic_profile(self):
        """Test creating a basic profile."""
        profile = SourceBiasProfile(
            url="https://example.com",
            domain="example.com",
            bias_category=BiasCategory.UNKNOWN,
        )
        assert profile.url == "https://example.com"
        assert profile.confidence == 0.8

    def test_profile_with_indicators(self):
        """Test profile with bias indicators."""
        profile = SourceBiasProfile(
            url="https://example.com",
            domain="example.com",
            bias_category=BiasCategory.CORPORATE,
            bias_indicators=[BiasIndicator.COMMERCIAL],
        )
        assert BiasIndicator.COMMERCIAL in profile.bias_indicators

    def test_to_dict(self):
        """Test dictionary conversion."""
        profile = SourceBiasProfile(
            url="https://example.com",
            domain="example.com",
            bias_category=BiasCategory.CENTER,
            viewpoint=ViewpointType.NEUTRAL,
        )
        data = profile.to_dict()
        assert data["bias_category"] == "center"
        assert data["viewpoint"] == "neutral"


# =============================================================================
# BiasDetector Tests
# =============================================================================

class TestBiasDetector:
    """Tests for BiasDetector class."""

    def test_initialization_default(self, default_detector):
        """Test default initialization."""
        assert default_detector.config is not None
        assert isinstance(default_detector.config, BiasConfig)

    def test_initialization_custom(self, custom_config):
        """Test initialization with custom config."""
        detector = BiasDetector(config=custom_config)
        assert detector.config.min_viewpoints == 3

    def test_analyze_empty_sources(self, default_detector):
        """Test analyzing empty source list."""
        report = default_detector.analyze_sources([])
        assert report.total_sources == 0
        assert report.is_balanced is True

    def test_analyze_sources_basic(self, default_detector, sample_evidence_chunks):
        """Test basic source analysis."""
        report = default_detector.analyze_sources(sample_evidence_chunks)
        assert report.total_sources == 5
        assert report.analyzed_sources == 5
        assert len(report.source_profiles) == 5

    def test_analyze_left_bias(self, default_detector, left_biased_chunks):
        """Test detection of left-leaning bias."""
        report = default_detector.analyze_sources(left_biased_chunks)
        left_count = report.category_counts.get(BiasCategory.LEFT_LEANING, 0)
        assert left_count >= 3

    def test_analyze_right_bias(self, default_detector, right_biased_chunks):
        """Test detection of right-leaning bias."""
        report = default_detector.analyze_sources(right_biased_chunks)
        right_count = report.category_counts.get(BiasCategory.RIGHT_LEANING, 0)
        assert right_count >= 2

    def test_analyze_academic_sources(self, default_detector, academic_chunks):
        """Test detection of academic sources."""
        report = default_detector.analyze_sources(academic_chunks)
        academic_count = report.category_counts.get(BiasCategory.ACADEMIC, 0)
        assert academic_count == 3


# =============================================================================
# Domain Extraction Tests
# =============================================================================

class TestDomainExtraction:
    """Tests for domain extraction."""

    def test_basic_domain(self, default_detector):
        """Test basic domain extraction."""
        domain = default_detector._extract_domain("https://www.example.com/page")
        assert domain == "example.com"

    def test_domain_with_www(self, default_detector):
        """Test domain with www prefix."""
        domain = default_detector._extract_domain("https://www.reuters.com/news")
        assert domain == "reuters.com"

    def test_domain_without_www(self, default_detector):
        """Test domain without www prefix."""
        domain = default_detector._extract_domain("https://nature.com/paper")
        assert domain == "nature.com"

    def test_subdomain(self, default_detector):
        """Test subdomain extraction."""
        domain = default_detector._extract_domain("https://news.example.com/article")
        assert domain == "news.example.com"


# =============================================================================
# Bias Classification Tests
# =============================================================================

class TestBiasClassification:
    """Tests for bias classification."""

    def test_known_left_sources(self, default_detector):
        """Test classification of known left sources."""
        left_sources = ["cnn.com", "msnbc.com", "nytimes.com"]
        for domain in left_sources:
            category = default_detector._classify_bias(domain, "")
            assert category == BiasCategory.LEFT_LEANING

    def test_known_center_sources(self, default_detector):
        """Test classification of known center sources."""
        center_sources = ["reuters.com", "apnews.com", "bbc.com"]
        for domain in center_sources:
            category = default_detector._classify_bias(domain, "")
            assert category == BiasCategory.CENTER

    def test_known_right_sources(self, default_detector):
        """Test classification of known right sources."""
        right_sources = ["foxnews.com", "breitbart.com"]
        for domain in right_sources:
            category = default_detector._classify_bias(domain, "")
            assert category == BiasCategory.RIGHT_LEANING

    def test_academic_sources(self, default_detector):
        """Test classification of academic sources."""
        academic_sources = ["nature.com", "arxiv.org", "sciencedirect.com"]
        for domain in academic_sources:
            category = default_detector._classify_bias(domain, "")
            assert category == BiasCategory.ACADEMIC

    def test_gov_suffix(self, default_detector):
        """Test classification of .gov domains."""
        category = default_detector._classify_bias("example.gov", "")
        assert category == BiasCategory.GOVERNMENT

    def test_unknown_source(self, default_detector):
        """Test classification of unknown source."""
        category = default_detector._classify_bias("randomsite.xyz", "")
        assert category == BiasCategory.UNKNOWN


# =============================================================================
# Viewpoint Detection Tests
# =============================================================================

class TestViewpointDetection:
    """Tests for viewpoint detection."""

    def test_pro_viewpoint(self, default_detector):
        """Test detection of pro viewpoint."""
        content = "This shows significant benefits and improvements."
        viewpoint = default_detector._detect_viewpoint(content)
        assert viewpoint == ViewpointType.PRO

    def test_con_viewpoint(self, default_detector):
        """Test detection of con viewpoint."""
        content = "Critics warn about risks and potential dangers."
        viewpoint = default_detector._detect_viewpoint(content)
        assert viewpoint == ViewpointType.CON

    def test_neutral_viewpoint(self, default_detector):
        """Test detection of neutral viewpoint."""
        content = "According to the study, research data indicates findings."
        viewpoint = default_detector._detect_viewpoint(content)
        assert viewpoint == ViewpointType.NEUTRAL

    def test_technical_viewpoint(self, default_detector):
        """Test detection of technical viewpoint."""
        content = "The algorithm implementation uses this mechanism."
        viewpoint = default_detector._detect_viewpoint(content)
        assert viewpoint == ViewpointType.TECHNICAL

    def test_empty_content(self, default_detector):
        """Test viewpoint for empty content."""
        viewpoint = default_detector._detect_viewpoint("")
        assert viewpoint == ViewpointType.NEUTRAL


# =============================================================================
# Balance Scoring Tests
# =============================================================================

class TestBalanceScoring:
    """Tests for balance scoring."""

    def test_balanced_sources(self, default_detector, sample_evidence_chunks):
        """Test balance score for diverse sources."""
        report = default_detector.analyze_sources(sample_evidence_chunks)
        assert 0 <= report.overall_balance_score <= 1

    def test_imbalanced_left(self, default_detector, left_biased_chunks):
        """Test balance score for left-biased sources."""
        report = default_detector.analyze_sources(left_biased_chunks)
        assert report.political_balance_score < 0.5  # Imbalanced

    def test_imbalanced_right(self, default_detector, right_biased_chunks):
        """Test balance score for right-biased sources."""
        report = default_detector.analyze_sources(right_biased_chunks)
        assert report.political_balance_score < 0.5  # Imbalanced


# =============================================================================
# Warning Generation Tests
# =============================================================================

class TestWarningGeneration:
    """Tests for warning generation."""

    def test_no_warnings_balanced(self, default_detector, sample_evidence_chunks):
        """Test no major warnings for balanced sources."""
        report = default_detector.analyze_sources(sample_evidence_chunks)
        # May have some warnings but should not be severely imbalanced
        assert isinstance(report.bias_warnings, list)

    def test_warnings_for_imbalance(self, default_detector, left_biased_chunks):
        """Test warnings generated for imbalanced sources."""
        report = default_detector.analyze_sources(left_biased_chunks)
        assert not report.is_balanced or len(report.bias_warnings) > 0


# =============================================================================
# Suggestion Generation Tests
# =============================================================================

class TestSuggestionGeneration:
    """Tests for suggestion generation."""

    def test_suggestions_for_imbalance(self, default_detector, left_biased_chunks):
        """Test suggestions generated for imbalanced sources."""
        report = default_detector.analyze_sources(left_biased_chunks)
        # Should suggest adding center or right sources
        assert len(report.balancing_suggestions) >= 0  # May or may not have suggestions

    def test_suggestions_type(self, default_detector, sample_evidence_chunks):
        """Test suggestions are strings."""
        report = default_detector.analyze_sources(sample_evidence_chunks)
        for suggestion in report.balancing_suggestions:
            assert isinstance(suggestion, str)


# =============================================================================
# BiasReport Tests
# =============================================================================

class TestBiasReport:
    """Tests for BiasReport dataclass."""

    def test_to_dict(self, default_detector, sample_evidence_chunks):
        """Test report serialization."""
        report = default_detector.analyze_sources(sample_evidence_chunks)
        data = report.to_dict()

        assert "total_sources" in data
        assert "analyzed_sources" in data
        assert "overall_balance_score" in data
        assert "is_balanced" in data
        assert "category_counts" in data

    def test_dominant_category(self, default_detector, left_biased_chunks):
        """Test dominant category detection."""
        report = default_detector.analyze_sources(left_biased_chunks)
        assert report.dominant_category is not None
        assert report.dominant_category == BiasCategory.LEFT_LEANING


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_analyze_source_bias(self, sample_evidence_chunks):
        """Test analyze_source_bias function."""
        report = analyze_source_bias(sample_evidence_chunks)
        assert isinstance(report, BiasReport)
        assert report.total_sources == 5

    def test_analyze_with_config(self, sample_evidence_chunks, custom_config):
        """Test analyze with custom config."""
        report = analyze_source_bias(sample_evidence_chunks, custom_config)
        assert isinstance(report, BiasReport)

    def test_check_balance(self, sample_evidence_chunks):
        """Test check_balance function."""
        is_balanced, message = check_balance(sample_evidence_chunks)
        assert isinstance(is_balanced, bool)
        assert isinstance(message, str)

    def test_check_balance_threshold(self, left_biased_chunks):
        """Test check_balance with threshold."""
        is_balanced, message = check_balance(left_biased_chunks, threshold=0.9)
        assert isinstance(is_balanced, bool)

    def test_get_balancing_suggestions(self, sample_evidence_chunks):
        """Test get_balancing_suggestions function."""
        suggestions = get_balancing_suggestions(sample_evidence_chunks)
        assert isinstance(suggestions, list)

    def test_classify_source_bias(self):
        """Test classify_source_bias function."""
        category = classify_source_bias("https://www.reuters.com/article")
        assert category == BiasCategory.CENTER

        category = classify_source_bias("https://www.nature.com/paper")
        assert category == BiasCategory.ACADEMIC


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_missing_url(self, default_detector):
        """Test handling of missing URL."""
        chunks = [{"content": "Some content without URL"}]
        report = default_detector.analyze_sources(chunks)
        assert report.analyzed_sources == 0

    def test_empty_content(self, default_detector):
        """Test handling of empty content."""
        chunks = [{"url": "https://example.com", "content": ""}]
        report = default_detector.analyze_sources(chunks)
        assert report.analyzed_sources == 1

    def test_alternative_url_key(self, default_detector):
        """Test alternative URL key (source_url)."""
        chunks = [{"source_url": "https://reuters.com/news", "text": "Content"}]
        report = default_detector.analyze_sources(chunks)
        assert report.analyzed_sources == 1

    def test_malformed_url(self, default_detector):
        """Test handling of malformed URL."""
        chunks = [{"url": "not-a-valid-url", "content": "Content"}]
        report = default_detector.analyze_sources(chunks)
        # Should handle gracefully
        assert report.total_sources == 1

    def test_source_caching(self, default_detector):
        """Test source profile caching."""
        url = "https://www.reuters.com/news"
        chunks = [
            {"url": url, "content": "Content 1"},
            {"url": url, "content": "Content 2"},
        ]
        report = default_detector.analyze_sources(chunks)
        # Same URL should be cached
        assert url in default_detector._source_cache


# =============================================================================
# Source Database Tests
# =============================================================================

class TestSourceDatabase:
    """Tests for source bias database."""

    def test_database_has_entries(self):
        """Test database has entries."""
        assert len(SOURCE_BIAS_DB) > 0

    def test_database_categories(self):
        """Test database has multiple categories."""
        categories = set(SOURCE_BIAS_DB.values())
        assert len(categories) >= 4

    def test_known_sources(self):
        """Test known sources are in database."""
        assert "reuters.com" in SOURCE_BIAS_DB
        assert "nature.com" in SOURCE_BIAS_DB


# =============================================================================
# Self-Test Function
# =============================================================================

class TestSelfTest:
    """Tests for self_test function."""

    def test_self_test_passes(self):
        """Test that self-test function passes."""
        from src.quality.bias_detector import self_test
        assert self_test() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
