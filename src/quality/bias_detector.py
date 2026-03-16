"""
POLARIS Bias Detector
=====================
Detects bias in research sources and ensures balanced viewpoints.

Features:
- Source bias classification (political, corporate, academic)
- Viewpoint diversity tracking
- Balance scoring with threshold warnings
- Suggestions for balancing coverage

Usage:
    from src.quality import BiasDetector, BiasConfig

    detector = BiasDetector()
    report = detector.analyze_sources(evidence_chunks)

    if not report.is_balanced:
        print(f"Warning: {report.balance_warning}")
        for suggestion in report.balancing_suggestions:
            print(f"  - {suggestion}")
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class BiasCategory(str, Enum):
    """Primary bias categories."""
    LEFT_LEANING = "left_leaning"
    CENTER = "center"
    RIGHT_LEANING = "right_leaning"
    CORPORATE = "corporate"
    ACADEMIC = "academic"
    GOVERNMENT = "government"
    NON_PROFIT = "non_profit"
    UNKNOWN = "unknown"


class ViewpointType(str, Enum):
    """Viewpoint types for diversity tracking."""
    PRO = "pro"
    CON = "con"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    TECHNICAL = "technical"


class BiasIndicator(str, Enum):
    """Types of bias indicators."""
    POLITICAL = "political"
    COMMERCIAL = "commercial"
    IDEOLOGICAL = "ideological"
    METHODOLOGICAL = "methodological"
    SELECTION = "selection"


# =============================================================================
# Source Bias Database
# =============================================================================

# Known source bias classifications (expandable)
SOURCE_BIAS_DB: Dict[str, BiasCategory] = {
    # Left-leaning news
    "cnn.com": BiasCategory.LEFT_LEANING,
    "msnbc.com": BiasCategory.LEFT_LEANING,
    "huffpost.com": BiasCategory.LEFT_LEANING,
    "nytimes.com": BiasCategory.LEFT_LEANING,
    "washingtonpost.com": BiasCategory.LEFT_LEANING,
    "theguardian.com": BiasCategory.LEFT_LEANING,
    "vox.com": BiasCategory.LEFT_LEANING,
    "slate.com": BiasCategory.LEFT_LEANING,

    # Center news
    "reuters.com": BiasCategory.CENTER,
    "apnews.com": BiasCategory.CENTER,
    "bbc.com": BiasCategory.CENTER,
    "bbc.co.uk": BiasCategory.CENTER,
    "npr.org": BiasCategory.CENTER,
    "pbs.org": BiasCategory.CENTER,
    "axios.com": BiasCategory.CENTER,
    "thehill.com": BiasCategory.CENTER,

    # Right-leaning news
    "foxnews.com": BiasCategory.RIGHT_LEANING,
    "breitbart.com": BiasCategory.RIGHT_LEANING,
    "dailywire.com": BiasCategory.RIGHT_LEANING,
    "nationalreview.com": BiasCategory.RIGHT_LEANING,
    "washingtontimes.com": BiasCategory.RIGHT_LEANING,
    "nypost.com": BiasCategory.RIGHT_LEANING,

    # Academic
    "nature.com": BiasCategory.ACADEMIC,
    "science.org": BiasCategory.ACADEMIC,
    "sciencedirect.com": BiasCategory.ACADEMIC,
    "springer.com": BiasCategory.ACADEMIC,
    "wiley.com": BiasCategory.ACADEMIC,
    "arxiv.org": BiasCategory.ACADEMIC,
    "pubmed.ncbi.nlm.nih.gov": BiasCategory.ACADEMIC,
    "jstor.org": BiasCategory.ACADEMIC,
    "researchgate.net": BiasCategory.ACADEMIC,
    "semanticscholar.org": BiasCategory.ACADEMIC,

    # Corporate/Tech
    "techcrunch.com": BiasCategory.CORPORATE,
    "wired.com": BiasCategory.CORPORATE,
    "forbes.com": BiasCategory.CORPORATE,
    "businessinsider.com": BiasCategory.CORPORATE,
    "bloomberg.com": BiasCategory.CORPORATE,
    "wsj.com": BiasCategory.CORPORATE,
    "cnbc.com": BiasCategory.CORPORATE,

    # Government
    "gov.uk": BiasCategory.GOVERNMENT,
    ".gov": BiasCategory.GOVERNMENT,
    "europa.eu": BiasCategory.GOVERNMENT,
    "who.int": BiasCategory.GOVERNMENT,
    "un.org": BiasCategory.GOVERNMENT,

    # Non-profit
    "wikipedia.org": BiasCategory.NON_PROFIT,
    "britannica.com": BiasCategory.NON_PROFIT,
}

# Viewpoint indicator keywords
VIEWPOINT_INDICATORS = {
    ViewpointType.PRO: [
        "benefit", "advantage", "positive", "support", "favor",
        "improve", "enhance", "promote", "advocate", "endorse",
        "opportunity", "potential", "promising", "success",
    ],
    ViewpointType.CON: [
        "risk", "danger", "negative", "oppose", "against",
        "harm", "concern", "problem", "issue", "threat",
        "challenge", "limitation", "drawback", "failure",
    ],
    ViewpointType.NEUTRAL: [
        "study", "research", "data", "evidence", "findings",
        "according to", "reported", "analysis", "survey",
    ],
    ViewpointType.TECHNICAL: [
        "specification", "implementation", "algorithm", "method",
        "procedure", "protocol", "technical", "mechanism",
    ],
}


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class BiasConfig:
    """Configuration for bias detection."""

    # Balance thresholds
    min_source_diversity: float = 0.3  # Minimum diversity score (0-1)
    max_single_category_ratio: float = 0.6  # Max ratio from one bias category
    min_viewpoints: int = 2  # Minimum different viewpoints required

    # Weights for balance scoring
    political_weight: float = 0.4
    source_type_weight: float = 0.3
    viewpoint_weight: float = 0.3

    # Detection sensitivity
    detect_political_bias: bool = True
    detect_commercial_bias: bool = True
    require_academic_sources: bool = False
    academic_source_minimum: int = 0

    # Warning thresholds
    warn_on_single_viewpoint: bool = True
    warn_on_political_imbalance: bool = True
    suggest_balancing_sources: bool = True


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SourceBiasProfile:
    """Bias profile for a single source."""
    url: str
    domain: str
    bias_category: BiasCategory
    confidence: float = 0.8  # Confidence in classification
    viewpoint: ViewpointType = ViewpointType.NEUTRAL
    bias_indicators: List[BiasIndicator] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "domain": self.domain,
            "bias_category": self.bias_category.value,
            "confidence": self.confidence,
            "viewpoint": self.viewpoint.value,
            "bias_indicators": [b.value for b in self.bias_indicators],
        }


@dataclass
class ViewpointDistribution:
    """Distribution of viewpoints in content."""
    pro: int = 0
    con: int = 0
    neutral: int = 0
    mixed: int = 0
    technical: int = 0

    @property
    def total(self) -> int:
        return self.pro + self.con + self.neutral + self.mixed + self.technical

    @property
    def diversity_score(self) -> float:
        """Calculate viewpoint diversity (0-1)."""
        if self.total == 0:
            return 0.0

        # Count non-zero viewpoint types
        non_zero = sum([
            1 for v in [self.pro, self.con, self.neutral, self.mixed, self.technical]
            if v > 0
        ])

        # Calculate entropy-based diversity
        proportions = [
            v / self.total for v in
            [self.pro, self.con, self.neutral, self.mixed, self.technical]
            if v > 0
        ]

        # Normalized entropy
        if len(proportions) <= 1:
            return 0.0

        import math
        entropy = -sum(p * math.log2(p) for p in proportions if p > 0)
        max_entropy = math.log2(5)  # 5 viewpoint types

        return entropy / max_entropy

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pro": self.pro,
            "con": self.con,
            "neutral": self.neutral,
            "mixed": self.mixed,
            "technical": self.technical,
            "total": self.total,
            "diversity_score": round(self.diversity_score, 3),
        }


@dataclass
class BiasReport:
    """Complete bias analysis report."""

    # Source analysis
    total_sources: int = 0
    analyzed_sources: int = 0
    source_profiles: List[SourceBiasProfile] = field(default_factory=list)

    # Category distribution
    category_counts: Dict[BiasCategory, int] = field(default_factory=dict)

    # Viewpoint analysis
    viewpoint_distribution: ViewpointDistribution = field(
        default_factory=ViewpointDistribution
    )

    # Balance scores
    political_balance_score: float = 0.5  # 0.5 = perfectly balanced
    source_diversity_score: float = 0.0
    viewpoint_diversity_score: float = 0.0
    overall_balance_score: float = 0.0

    # Warnings and suggestions
    is_balanced: bool = True
    balance_warning: str = ""
    bias_warnings: List[str] = field(default_factory=list)
    balancing_suggestions: List[str] = field(default_factory=list)

    # Dominant bias info
    dominant_category: Optional[BiasCategory] = None
    dominant_viewpoint: Optional[ViewpointType] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_sources": self.total_sources,
            "analyzed_sources": self.analyzed_sources,
            "source_profiles": [s.to_dict() for s in self.source_profiles],
            "category_counts": {k.value: v for k, v in self.category_counts.items()},
            "viewpoint_distribution": self.viewpoint_distribution.to_dict(),
            "political_balance_score": round(self.political_balance_score, 3),
            "source_diversity_score": round(self.source_diversity_score, 3),
            "viewpoint_diversity_score": round(self.viewpoint_diversity_score, 3),
            "overall_balance_score": round(self.overall_balance_score, 3),
            "is_balanced": self.is_balanced,
            "balance_warning": self.balance_warning,
            "bias_warnings": self.bias_warnings,
            "balancing_suggestions": self.balancing_suggestions,
            "dominant_category": self.dominant_category.value if self.dominant_category else None,
            "dominant_viewpoint": self.dominant_viewpoint.value if self.dominant_viewpoint else None,
        }


# =============================================================================
# Bias Detector
# =============================================================================

class BiasDetector:
    """
    Detects bias in research sources and ensures balanced viewpoints.

    Analyzes source diversity, political leaning, and viewpoint coverage
    to identify potential bias and suggest balancing sources.
    """

    def __init__(self, config: Optional[BiasConfig] = None):
        """
        Initialize the bias detector.

        Args:
            config: Bias detection configuration
        """
        self.config = config or BiasConfig()
        self._source_cache: Dict[str, SourceBiasProfile] = {}

    def analyze_sources(
        self,
        evidence_chunks: List[Dict[str, Any]],
        topic: Optional[str] = None,
    ) -> BiasReport:
        """
        Analyze bias in evidence sources.

        Args:
            evidence_chunks: List of evidence chunks with 'url' and 'content'
            topic: Optional topic context for viewpoint analysis

        Returns:
            BiasReport with analysis results
        """
        report = BiasReport(total_sources=len(evidence_chunks))

        if not evidence_chunks:
            report.is_balanced = True
            return report

        # Analyze each source
        for chunk in evidence_chunks:
            url = chunk.get("url", chunk.get("source_url", ""))
            content = chunk.get("content", chunk.get("text", ""))

            if not url:
                continue

            profile = self._analyze_source(url, content)
            report.source_profiles.append(profile)
            report.analyzed_sources += 1

            # Update category counts
            cat = profile.bias_category
            report.category_counts[cat] = report.category_counts.get(cat, 0) + 1

            # Update viewpoint distribution
            self._update_viewpoint_distribution(
                report.viewpoint_distribution,
                profile.viewpoint
            )

        # Calculate balance scores
        self._calculate_balance_scores(report)

        # Generate warnings and suggestions
        self._generate_warnings(report)
        self._generate_suggestions(report)

        return report

    def _analyze_source(self, url: str, content: str) -> SourceBiasProfile:
        """Analyze bias for a single source."""
        # Check cache
        if url in self._source_cache:
            return self._source_cache[url]

        domain = self._extract_domain(url)
        bias_category = self._classify_bias(domain, url)
        viewpoint = self._detect_viewpoint(content)
        indicators = self._detect_bias_indicators(content, domain)

        profile = SourceBiasProfile(
            url=url,
            domain=domain,
            bias_category=bias_category,
            viewpoint=viewpoint,
            bias_indicators=indicators,
        )

        self._source_cache[url] = profile
        return profile

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _classify_bias(self, domain: str, url: str) -> BiasCategory:
        """Classify source bias category."""
        # Check exact domain match
        if domain in SOURCE_BIAS_DB:
            return SOURCE_BIAS_DB[domain]

        # Check subdomain matches
        for known_domain, category in SOURCE_BIAS_DB.items():
            if known_domain.startswith("."):
                # Suffix match (e.g., .gov)
                if domain.endswith(known_domain) or domain.endswith(known_domain[1:]):
                    return category
            elif domain.endswith("." + known_domain):
                return category

        # Academic indicators
        academic_indicators = [".edu", "university", "journal", "academic"]
        if any(ind in domain or ind in url.lower() for ind in academic_indicators):
            return BiasCategory.ACADEMIC

        # Government indicators
        if ".gov" in domain or ".gov." in domain:
            return BiasCategory.GOVERNMENT

        return BiasCategory.UNKNOWN

    def _detect_viewpoint(self, content: str) -> ViewpointType:
        """Detect viewpoint from content."""
        if not content:
            return ViewpointType.NEUTRAL

        content_lower = content.lower()

        # Count viewpoint indicators
        scores = {}
        for viewpoint, keywords in VIEWPOINT_INDICATORS.items():
            count = sum(1 for kw in keywords if kw in content_lower)
            scores[viewpoint] = count

        # Determine dominant viewpoint
        max_score = max(scores.values()) if scores else 0
        if max_score == 0:
            return ViewpointType.NEUTRAL

        # Check for mixed viewpoints
        high_scores = [vp for vp, score in scores.items() if score >= max_score * 0.7]
        if len(high_scores) > 1:
            if ViewpointType.PRO in high_scores and ViewpointType.CON in high_scores:
                return ViewpointType.MIXED

        # Return dominant
        for viewpoint, score in scores.items():
            if score == max_score:
                return viewpoint

        return ViewpointType.NEUTRAL

    def _detect_bias_indicators(
        self,
        content: str,
        domain: str,
    ) -> List[BiasIndicator]:
        """Detect specific bias indicators in content."""
        indicators = []

        if not content:
            return indicators

        content_lower = content.lower()

        # Political bias indicators
        political_terms = [
            "liberal", "conservative", "democrat", "republican",
            "left-wing", "right-wing", "progressive", "traditional",
        ]
        if any(term in content_lower for term in political_terms):
            indicators.append(BiasIndicator.POLITICAL)

        # Commercial bias indicators
        commercial_terms = [
            "buy now", "purchase", "subscribe", "limited offer",
            "sponsored", "advertisement", "affiliate",
        ]
        if any(term in content_lower for term in commercial_terms):
            indicators.append(BiasIndicator.COMMERCIAL)

        # Ideological bias indicators
        ideological_terms = [
            "must believe", "obviously", "clearly wrong", "everyone knows",
            "undeniable", "absolute truth", "only way",
        ]
        if any(term in content_lower for term in ideological_terms):
            indicators.append(BiasIndicator.IDEOLOGICAL)

        return indicators

    def _update_viewpoint_distribution(
        self,
        dist: ViewpointDistribution,
        viewpoint: ViewpointType,
    ) -> None:
        """Update viewpoint distribution counts."""
        if viewpoint == ViewpointType.PRO:
            dist.pro += 1
        elif viewpoint == ViewpointType.CON:
            dist.con += 1
        elif viewpoint == ViewpointType.NEUTRAL:
            dist.neutral += 1
        elif viewpoint == ViewpointType.MIXED:
            dist.mixed += 1
        elif viewpoint == ViewpointType.TECHNICAL:
            dist.technical += 1

    def _calculate_balance_scores(self, report: BiasReport) -> None:
        """Calculate all balance scores."""
        if report.analyzed_sources == 0:
            return

        # Political balance score (0 = all one side, 0.5 = balanced, 1 = all other side)
        left = report.category_counts.get(BiasCategory.LEFT_LEANING, 0)
        right = report.category_counts.get(BiasCategory.RIGHT_LEANING, 0)
        center = report.category_counts.get(BiasCategory.CENTER, 0)

        political_total = left + right + center
        if political_total > 0:
            # Calculate balance: 0.5 is perfect balance
            if left + right > 0:
                balance = right / (left + right)  # 0 = all left, 1 = all right
                # Convert to 0.5-centered score (0.5 = balanced)
                report.political_balance_score = 1 - abs(0.5 - balance) * 2
            else:
                report.political_balance_score = 0.5  # All center = balanced

        # Source diversity score
        unique_categories = len([c for c, count in report.category_counts.items() if count > 0])
        max_categories = len(BiasCategory)
        report.source_diversity_score = unique_categories / max_categories

        # Viewpoint diversity score
        report.viewpoint_diversity_score = report.viewpoint_distribution.diversity_score

        # Overall balance score (weighted)
        report.overall_balance_score = (
            report.political_balance_score * self.config.political_weight +
            report.source_diversity_score * self.config.source_type_weight +
            report.viewpoint_diversity_score * self.config.viewpoint_weight
        )

        # Determine dominant category
        if report.category_counts:
            report.dominant_category = max(
                report.category_counts.keys(),
                key=lambda k: report.category_counts[k]
            )

        # Determine dominant viewpoint
        vd = report.viewpoint_distribution
        viewpoint_counts = {
            ViewpointType.PRO: vd.pro,
            ViewpointType.CON: vd.con,
            ViewpointType.NEUTRAL: vd.neutral,
            ViewpointType.MIXED: vd.mixed,
            ViewpointType.TECHNICAL: vd.technical,
        }
        if any(v > 0 for v in viewpoint_counts.values()):
            report.dominant_viewpoint = max(
                viewpoint_counts.keys(),
                key=lambda k: viewpoint_counts[k]
            )

    def _generate_warnings(self, report: BiasReport) -> None:
        """Generate bias warnings."""
        if report.analyzed_sources == 0:
            return

        # Check for imbalance
        report.is_balanced = True
        warnings = []

        # Check single category dominance
        for category, count in report.category_counts.items():
            ratio = count / report.analyzed_sources
            if ratio > self.config.max_single_category_ratio:
                report.is_balanced = False
                warnings.append(
                    f"Over {int(ratio * 100)}% of sources are from "
                    f"{category.value.replace('_', ' ')} sources"
                )

        # Check political imbalance
        if self.config.warn_on_political_imbalance:
            if report.political_balance_score < 0.3:
                report.is_balanced = False
                left = report.category_counts.get(BiasCategory.LEFT_LEANING, 0)
                right = report.category_counts.get(BiasCategory.RIGHT_LEANING, 0)

                if left > right:
                    warnings.append("Sources lean predominantly left-leaning")
                elif right > left:
                    warnings.append("Sources lean predominantly right-leaning")

        # Check viewpoint diversity
        if self.config.warn_on_single_viewpoint:
            vd = report.viewpoint_distribution
            non_zero_viewpoints = sum([
                1 for v in [vd.pro, vd.con, vd.neutral, vd.mixed, vd.technical]
                if v > 0
            ])
            if non_zero_viewpoints < self.config.min_viewpoints:
                report.is_balanced = False
                warnings.append(
                    f"Only {non_zero_viewpoints} viewpoint type(s) represented "
                    f"(minimum {self.config.min_viewpoints} recommended)"
                )

        # Check source diversity
        if report.source_diversity_score < self.config.min_source_diversity:
            report.is_balanced = False
            warnings.append(
                f"Low source diversity ({report.source_diversity_score:.0%}) - "
                f"consider adding varied source types"
            )

        report.bias_warnings = warnings
        if warnings:
            report.balance_warning = warnings[0]  # Primary warning

    def _generate_suggestions(self, report: BiasReport) -> None:
        """Generate suggestions for balancing sources."""
        if not self.config.suggest_balancing_sources:
            return

        suggestions = []

        # Suggest balancing political sources
        left = report.category_counts.get(BiasCategory.LEFT_LEANING, 0)
        right = report.category_counts.get(BiasCategory.RIGHT_LEANING, 0)
        center = report.category_counts.get(BiasCategory.CENTER, 0)

        if left > right * 2:
            suggestions.append(
                "Add center or right-leaning sources for political balance"
            )
        elif right > left * 2:
            suggestions.append(
                "Add center or left-leaning sources for political balance"
            )

        if center == 0 and (left > 0 or right > 0):
            suggestions.append(
                "Include neutral sources (Reuters, AP News, BBC) for objectivity"
            )

        # Suggest adding academic sources
        academic = report.category_counts.get(BiasCategory.ACADEMIC, 0)
        if (self.config.require_academic_sources and
            academic < self.config.academic_source_minimum):
            suggestions.append(
                f"Add at least {self.config.academic_source_minimum} academic "
                f"sources for credibility"
            )

        # Suggest viewpoint balance
        vd = report.viewpoint_distribution
        if vd.pro > 0 and vd.con == 0:
            suggestions.append(
                "Include sources with critical/opposing viewpoints"
            )
        elif vd.con > 0 and vd.pro == 0:
            suggestions.append(
                "Include sources with supportive/positive viewpoints"
            )

        # Suggest unknown source research
        unknown = report.category_counts.get(BiasCategory.UNKNOWN, 0)
        if unknown > report.analyzed_sources * 0.5:
            suggestions.append(
                "Research bias profiles for unknown sources to improve analysis"
            )

        report.balancing_suggestions = suggestions


# =============================================================================
# Convenience Functions
# =============================================================================

def analyze_source_bias(
    evidence_chunks: List[Dict[str, Any]],
    config: Optional[BiasConfig] = None,
) -> BiasReport:
    """
    Analyze bias in evidence sources.

    Args:
        evidence_chunks: List of evidence chunks
        config: Bias detection configuration

    Returns:
        BiasReport with analysis results
    """
    detector = BiasDetector(config)
    return detector.analyze_sources(evidence_chunks)


def check_balance(
    evidence_chunks: List[Dict[str, Any]],
    threshold: float = 0.4,
) -> Tuple[bool, str]:
    """
    Quick check if sources are balanced.

    Args:
        evidence_chunks: List of evidence chunks
        threshold: Minimum balance score threshold

    Returns:
        Tuple of (is_balanced, warning_message)
    """
    report = analyze_source_bias(evidence_chunks)
    is_balanced = report.overall_balance_score >= threshold
    message = report.balance_warning if not is_balanced else ""
    return is_balanced, message


def get_balancing_suggestions(
    evidence_chunks: List[Dict[str, Any]],
) -> List[str]:
    """
    Get suggestions for balancing sources.

    Args:
        evidence_chunks: List of evidence chunks

    Returns:
        List of balancing suggestions
    """
    report = analyze_source_bias(evidence_chunks)
    return report.balancing_suggestions


def classify_source_bias(url: str) -> BiasCategory:
    """
    Classify bias for a single URL.

    Args:
        url: Source URL

    Returns:
        BiasCategory classification
    """
    detector = BiasDetector()
    profile = detector._analyze_source(url, "")
    return profile.bias_category


# =============================================================================
# Self-Test
# =============================================================================

def self_test() -> bool:
    """Run self-tests for bias detector."""
    print("Running Bias Detector self-tests...")

    # Test data
    test_chunks = [
        {"url": "https://www.nytimes.com/article", "content": "This study shows benefits of the policy."},
        {"url": "https://www.foxnews.com/story", "content": "Critics warn about risks and dangers."},
        {"url": "https://www.reuters.com/news", "content": "According to data, research findings indicate."},
        {"url": "https://www.nature.com/paper", "content": "Technical analysis of the mechanism."},
        {"url": "https://example.com/page", "content": "General information about the topic."},
    ]

    # Test analysis
    detector = BiasDetector()
    report = detector.analyze_sources(test_chunks)

    assert report.total_sources == 5
    assert report.analyzed_sources == 5
    print("  [PASS] Source analysis")

    # Test category detection
    assert BiasCategory.LEFT_LEANING in report.category_counts
    assert BiasCategory.RIGHT_LEANING in report.category_counts
    assert BiasCategory.CENTER in report.category_counts
    assert BiasCategory.ACADEMIC in report.category_counts
    print("  [PASS] Category detection")

    # Test viewpoint detection
    assert report.viewpoint_distribution.total > 0
    print("  [PASS] Viewpoint detection")

    # Test balance scoring
    assert 0 <= report.overall_balance_score <= 1
    print("  [PASS] Balance scoring")

    # Test convenience functions
    is_balanced, _ = check_balance(test_chunks)
    assert isinstance(is_balanced, bool)
    print("  [PASS] check_balance")

    suggestions = get_balancing_suggestions(test_chunks)
    assert isinstance(suggestions, list)
    print("  [PASS] get_balancing_suggestions")

    category = classify_source_bias("https://www.bbc.com/news")
    assert category == BiasCategory.CENTER
    print("  [PASS] classify_source_bias")

    # Test report serialization
    data = report.to_dict()
    assert "overall_balance_score" in data
    print("  [PASS] Report serialization")

    print("\nAll Bias Detector self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
