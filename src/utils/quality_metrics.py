"""
POLARIS Quality Metrics Tracker

SOTA FIX: Issues #41-46 - Quality metrics and real-time tracking.

Tracks:
- Per-iteration quality metrics
- Source diversity scoring
- Geographic coverage
- Confidence intervals
- Real-time progress updates
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


@dataclass
class IterationMetrics:
    """Metrics for a single iteration."""
    iteration: int
    timestamp: str
    evidence_count: int
    new_evidence_count: int
    novelty_score: float
    faithfulness: float
    context_precision: float
    answer_relevancy: float
    source_diversity: int
    quality_tier_distribution: Dict[str, int]


@dataclass
class QualityTracker:
    """
    Tracks quality metrics across iterations.

    SOTA FIX: Issue #41-42 - Real-time quality tracking.
    """
    iterations: List[IterationMetrics] = field(default_factory=list)
    total_evidence: int = 0
    unique_domains: set = field(default_factory=set)
    quality_tier_totals: Dict[str, int] = field(default_factory=lambda: {
        "GOLD": 0, "SILVER": 0, "BRONZE": 0, "UNVERIFIED": 0
    })
    geographic_coverage: Dict[str, int] = field(default_factory=dict)

    def record_iteration(
        self,
        iteration: int,
        evidence_chain: List[Any],
        quality_metrics: Dict[str, float],
    ):
        """Record metrics for an iteration."""
        # Calculate new evidence
        new_evidence = len(evidence_chain) - self.total_evidence
        novelty = new_evidence / max(len(evidence_chain), 1)

        # Update unique domains
        for ev in evidence_chain:
            url = getattr(ev, 'source_url', '') or ev.get('source_url', '') if isinstance(ev, dict) else ''
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    self.unique_domains.add(domain)
                except Exception as e:
                    logger.debug(f"Failed to parse URL from evidence: {e}")

        # Update quality tier distribution
        tier_dist = {"GOLD": 0, "SILVER": 0, "BRONZE": 0, "UNVERIFIED": 0}
        for ev in evidence_chain:
            tier = getattr(ev, 'quality_tier', 'UNVERIFIED') if hasattr(ev, 'quality_tier') else ev.get('quality_tier', 'UNVERIFIED') if isinstance(ev, dict) else 'UNVERIFIED'
            tier_dist[tier] = tier_dist.get(tier, 0) + 1
            self.quality_tier_totals[tier] = self.quality_tier_totals.get(tier, 0) + 1

        # Create iteration metrics
        metrics = IterationMetrics(
            iteration=iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_count=len(evidence_chain),
            new_evidence_count=new_evidence,
            novelty_score=novelty,
            faithfulness=quality_metrics.get("faithfulness", 0.0),
            context_precision=quality_metrics.get("context_precision", 0.0),
            answer_relevancy=quality_metrics.get("answer_relevancy", 0.0),
            source_diversity=len(self.unique_domains),
            quality_tier_distribution=tier_dist,
        )

        self.iterations.append(metrics)
        self.total_evidence = len(evidence_chain)

        logger.info(
            f"Iteration {iteration} metrics: evidence={len(evidence_chain)}, "
            f"novelty={novelty:.2%}, domains={len(self.unique_domains)}, "
            f"faithfulness={quality_metrics.get('faithfulness', 0):.2%}"
        )

        return metrics

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked metrics."""
        if not self.iterations:
            return {"status": "no_iterations"}

        latest = self.iterations[-1]
        first = self.iterations[0]

        return {
            "total_iterations": len(self.iterations),
            "total_evidence": self.total_evidence,
            "source_diversity": len(self.unique_domains),
            "quality_tier_distribution": self.quality_tier_totals,
            "latest_metrics": {
                "faithfulness": latest.faithfulness,
                "context_precision": latest.context_precision,
                "answer_relevancy": latest.answer_relevancy,
            },
            "improvement": {
                "faithfulness_delta": latest.faithfulness - first.faithfulness,
                "evidence_delta": latest.evidence_count - first.evidence_count,
            },
            "convergence": {
                "final_novelty": latest.novelty_score,
                "below_threshold": latest.novelty_score < 0.05,
            },
        }

    def calculate_confidence_interval(self) -> Tuple[float, float]:
        """
        Calculate confidence interval for quality metrics.

        SOTA FIX: Issue #44 - Confidence intervals.

        Returns:
            Tuple of (lower_bound, upper_bound) for faithfulness
        """
        if len(self.iterations) < 2:
            return (0.0, 1.0)

        faithfulness_values = [m.faithfulness for m in self.iterations]

        import statistics
        mean = statistics.mean(faithfulness_values)
        stdev = statistics.stdev(faithfulness_values) if len(faithfulness_values) > 1 else 0

        # 95% confidence interval
        margin = 1.96 * stdev / (len(faithfulness_values) ** 0.5)

        lower = max(0.0, mean - margin)
        upper = min(1.0, mean + margin)

        return (lower, upper)


class SourceDiversityScorer:
    """
    Scores source diversity for research quality.

    SOTA FIX: Issue #45 - Source diversity scoring.
    """

    # Domain type weights
    DOMAIN_WEIGHTS = {
        "gov": 1.5,      # Government sources highest weight
        "edu": 1.4,      # Educational institutions
        "org": 1.2,      # Non-profit organizations
        "com": 1.0,      # Commercial (baseline)
        "news": 1.1,     # News sources
        "academic": 1.5,  # Academic papers
    }

    def __init__(self):
        self.domains_seen = set()
        self.domain_types = defaultdict(int)

    def add_source(self, url: str, source_type: str = "web"):
        """Add a source to tracking."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc

            self.domains_seen.add(domain)

            # Classify domain type
            if ".gov" in domain:
                self.domain_types["gov"] += 1
            elif ".edu" in domain:
                self.domain_types["edu"] += 1
            elif ".org" in domain:
                self.domain_types["org"] += 1
            elif source_type == "academic":
                self.domain_types["academic"] += 1
            else:
                self.domain_types["com"] += 1

        except Exception as e:
            logger.debug(f"Failed to parse URL {url}: {e}")

    def calculate_score(self) -> float:
        """
        Calculate source diversity score.

        Returns:
            Score from 0.0 to 1.0
        """
        if not self.domains_seen:
            return 0.0

        # Base score from unique domains
        domain_count = len(self.domains_seen)
        base_score = min(domain_count / 20, 1.0)  # Max at 20 domains

        # Bonus for domain type diversity
        type_count = len(self.domain_types)
        type_bonus = min(type_count / 5, 0.2)  # Max 0.2 bonus for 5 types

        # Bonus for authoritative sources
        auth_count = self.domain_types.get("gov", 0) + self.domain_types.get("edu", 0) + self.domain_types.get("academic", 0)
        auth_bonus = min(auth_count / 10, 0.2)  # Max 0.2 bonus for 10 auth sources

        total_score = min(base_score + type_bonus + auth_bonus, 1.0)

        return total_score

    def get_report(self) -> Dict[str, Any]:
        """Get diversity report."""
        return {
            "unique_domains": len(self.domains_seen),
            "domain_types": dict(self.domain_types),
            "diversity_score": self.calculate_score(),
            "has_gov_sources": self.domain_types.get("gov", 0) > 0,
            "has_academic_sources": self.domain_types.get("academic", 0) + self.domain_types.get("edu", 0) > 0,
        }


class GeographicCoverageTracker:
    """
    Tracks geographic coverage of evidence.

    SOTA FIX: Issue #46 - Geographic coverage tracking.
    """

    # Region patterns
    REGION_PATTERNS = {
        "NORTH_AMERICA": ["usa", "united states", "canada", "mexico", "american", "us ", "u.s."],
        "EUROPE": ["europe", "european", "eu ", "uk ", "britain", "germany", "france", "spain", "italy"],
        "ASIA_PACIFIC": ["asia", "china", "japan", "korea", "india", "australia", "pacific"],
        "LATIN_AMERICA": ["latin america", "brazil", "argentina", "chile", "colombia"],
        "AFRICA": ["africa", "african", "nigeria", "south africa", "kenya", "egypt"],
        "MIDDLE_EAST": ["middle east", "saudi", "uae", "israel", "iran", "iraq"],
    }

    def __init__(self, target_region: str = "GLOBAL"):
        self.target_region = target_region
        self.region_counts = defaultdict(int)
        self.total_evidence = 0

    def analyze_evidence(self, text: str):
        """Analyze evidence for geographic mentions."""
        self.total_evidence += 1
        text_lower = text.lower()

        for region, patterns in self.REGION_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    self.region_counts[region] += 1
                    break  # Count once per region

    def calculate_coverage_score(self) -> float:
        """
        Calculate geographic coverage score.

        Returns:
            Score from 0.0 to 1.0 based on target region coverage
        """
        if self.total_evidence == 0:
            return 0.0

        if self.target_region == "GLOBAL":
            # For global, reward diverse geographic coverage
            regions_covered = len(self.region_counts)
            return min(regions_covered / 4, 1.0)  # Max at 4 regions
        else:
            # For specific region, reward on-target evidence
            target_count = self.region_counts.get(self.target_region, 0)
            return min(target_count / (self.total_evidence * 0.5), 1.0)

    def get_report(self) -> Dict[str, Any]:
        """Get geographic coverage report."""
        return {
            "target_region": self.target_region,
            "total_evidence_analyzed": self.total_evidence,
            "region_counts": dict(self.region_counts),
            "coverage_score": self.calculate_coverage_score(),
            "on_target_ratio": self.region_counts.get(self.target_region, 0) / max(self.total_evidence, 1),
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_quality_tracker() -> QualityTracker:
    """Create a new quality tracker."""
    return QualityTracker()


def create_diversity_scorer() -> SourceDiversityScorer:
    """Create a new source diversity scorer."""
    return SourceDiversityScorer()


def create_geographic_tracker(target_region: str = "GLOBAL") -> GeographicCoverageTracker:
    """Create a new geographic coverage tracker."""
    return GeographicCoverageTracker(target_region)
