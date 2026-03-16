"""
POLARIS Sophisticated Stopping Mechanism - OpenAI o3 Parity

Implements multi-factor coverage-based stopping that considers:
- Evidence coverage (sufficient evidence for each sub-query)
- Source diversity (multiple independent sources)
- Query coverage (all aspects of the question addressed)
- Quality score (faithfulness and accuracy)
- Gap resolution (knowledge gaps being closed)

This replaces simple iteration counting with intelligent stopping
that optimizes for research completeness while avoiding wasted effort.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class StopReason(Enum):
    """Reasons for stopping research."""
    COVERAGE_COMPLETE = "coverage_complete"
    QUALITY_THRESHOLD = "quality_threshold"
    NOVELTY_EXHAUSTED = "novelty_exhausted"
    MAX_ITERATIONS = "max_iterations"
    TIME_LIMIT = "time_limit"
    CONTINUE = "continue"  # Not stopping yet


@dataclass
class StopDecision:
    """Decision about whether to stop research."""
    should_stop: bool
    reason: StopReason
    reason_detail: str
    coverage_score: float  # Overall weighted coverage (0.0-1.0)
    factors: Dict[str, float]  # Individual factor scores
    confidence: float  # Confidence in stop decision


@dataclass
class CoverageFactors:
    """Individual coverage factors."""
    evidence_coverage: float
    source_diversity: float
    query_coverage: float
    quality_score: float
    gap_resolution: float


class SophisticatedStopper:
    """
    Multi-factor stopping mechanism for research quality optimization.

    Calculates a weighted coverage score from multiple factors and
    stops when coverage is sufficient or resources are exhausted.

    Unlike simple iteration limits, this ensures:
    1. Research continues until quality targets are met
    2. Time is not wasted when diminishing returns set in
    3. Hard limits prevent runaway execution
    """

    def __init__(
        self,
        min_coverage: float = 0.85,
        min_quality: float = 0.80,
        novelty_exhaustion: float = 0.05,
        max_iterations: int = 15,
        max_time_minutes: float = 45.0,
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize the stopper with thresholds.

        Args:
            min_coverage: Minimum weighted coverage to stop (default 0.85)
            min_quality: Minimum quality score to stop (default 0.80)
            novelty_exhaustion: Novelty threshold below which = exhausted (default 0.05)
            max_iterations: Hard limit on iterations (default 15)
            max_time_minutes: Hard limit on time (default 45 min)
            weights: Factor weights (must sum to 1.0)
        """
        self.min_coverage = min_coverage
        self.min_quality = min_quality
        self.novelty_exhaustion = novelty_exhaustion
        self.max_iterations = max_iterations
        self.max_time_minutes = max_time_minutes

        # Default weights
        self.weights = weights or {
            "evidence_coverage": 0.25,
            "source_diversity": 0.15,
            "query_coverage": 0.20,
            "quality_score": 0.25,
            "gap_resolution": 0.15,
        }

        # Track novelty for exhaustion detection
        self._novelty_history: List[float] = []
        self._start_time: Optional[float] = None

    def start_timing(self) -> None:
        """Start the timing for time limit tracking."""
        self._start_time = time.time()

    def get_elapsed_minutes(self) -> float:
        """Get elapsed time in minutes."""
        if self._start_time is None:
            return 0.0
        return (time.time() - self._start_time) / 60.0

    def should_stop(
        self,
        state: Dict[str, Any],
        iteration: int,
        elapsed_minutes: Optional[float] = None,
    ) -> StopDecision:
        """
        Determine if research should stop based on multiple factors.

        Args:
            state: Current research state
            iteration: Current iteration number
            elapsed_minutes: Time elapsed (uses internal timer if None)

        Returns:
            StopDecision with recommendation and reasoning
        """
        if elapsed_minutes is None:
            elapsed_minutes = self.get_elapsed_minutes()

        # Calculate all factors
        factors = self._calculate_all_factors(state)

        # Calculate weighted coverage
        coverage_score = self._calculate_weighted_coverage(factors)

        factor_dict = {
            "evidence_coverage": factors.evidence_coverage,
            "source_diversity": factors.source_diversity,
            "query_coverage": factors.query_coverage,
            "quality_score": factors.quality_score,
            "gap_resolution": factors.gap_resolution,
        }

        # Check hard limits first
        if iteration >= self.max_iterations:
            logger.info(
                f"[STOPPING] Max iterations reached ({iteration}/{self.max_iterations}). "
                f"Coverage: {coverage_score:.2%}"
            )
            return StopDecision(
                should_stop=True,
                reason=StopReason.MAX_ITERATIONS,
                reason_detail=f"Reached maximum {self.max_iterations} iterations",
                coverage_score=coverage_score,
                factors=factor_dict,
                confidence=1.0
            )

        if elapsed_minutes >= self.max_time_minutes:
            logger.info(
                f"[STOPPING] Time limit reached ({elapsed_minutes:.1f}/{self.max_time_minutes} min). "
                f"Coverage: {coverage_score:.2%}"
            )
            return StopDecision(
                should_stop=True,
                reason=StopReason.TIME_LIMIT,
                reason_detail=f"Reached {self.max_time_minutes} minute time limit",
                coverage_score=coverage_score,
                factors=factor_dict,
                confidence=1.0
            )

        # Check coverage threshold
        if coverage_score >= self.min_coverage:
            logger.info(
                f"[STOPPING] Coverage complete ({coverage_score:.2%} >= {self.min_coverage:.2%}). "
                f"Iteration {iteration}"
            )
            return StopDecision(
                should_stop=True,
                reason=StopReason.COVERAGE_COMPLETE,
                reason_detail=f"Coverage {coverage_score:.2%} exceeds threshold {self.min_coverage:.2%}",
                coverage_score=coverage_score,
                factors=factor_dict,
                confidence=0.9
            )

        # Check quality threshold (faithfulness)
        if factors.quality_score >= self.min_quality:
            logger.info(
                f"[STOPPING] Quality threshold met ({factors.quality_score:.2%} >= {self.min_quality:.2%}). "
                f"Coverage: {coverage_score:.2%}"
            )
            return StopDecision(
                should_stop=True,
                reason=StopReason.QUALITY_THRESHOLD,
                reason_detail=f"Quality {factors.quality_score:.2%} exceeds threshold {self.min_quality:.2%}",
                coverage_score=coverage_score,
                factors=factor_dict,
                confidence=0.85
            )

        # Check novelty exhaustion
        novelty = self._calculate_novelty(state)
        self._novelty_history.append(novelty)

        if len(self._novelty_history) >= 3:
            recent_novelty = sum(self._novelty_history[-3:]) / 3
            if recent_novelty < self.novelty_exhaustion:
                logger.info(
                    f"[STOPPING] Novelty exhausted ({recent_novelty:.2%} < {self.novelty_exhaustion:.2%}). "
                    f"Coverage: {coverage_score:.2%}"
                )
                return StopDecision(
                    should_stop=True,
                    reason=StopReason.NOVELTY_EXHAUSTED,
                    reason_detail=f"Recent novelty {recent_novelty:.2%} below threshold",
                    coverage_score=coverage_score,
                    factors=factor_dict,
                    confidence=0.75
                )

        # Continue research
        logger.debug(
            f"[STOPPING] Continue (coverage: {coverage_score:.2%}, "
            f"iteration: {iteration}, elapsed: {elapsed_minutes:.1f}min)"
        )
        return StopDecision(
            should_stop=False,
            reason=StopReason.CONTINUE,
            reason_detail=f"Coverage {coverage_score:.2%} below threshold {self.min_coverage:.2%}",
            coverage_score=coverage_score,
            factors=factor_dict,
            confidence=1.0
        )

    def _calculate_all_factors(self, state: Dict[str, Any]) -> CoverageFactors:
        """Calculate all coverage factors from state."""
        return CoverageFactors(
            evidence_coverage=self._calculate_evidence_coverage(state),
            source_diversity=self._calculate_source_diversity(state),
            query_coverage=self._calculate_query_coverage(state),
            quality_score=self._calculate_quality_score(state),
            gap_resolution=self._calculate_gap_resolution(state),
        )

    def _calculate_weighted_coverage(self, factors: CoverageFactors) -> float:
        """Calculate weighted coverage score from individual factors."""
        weighted_sum = (
            factors.evidence_coverage * self.weights["evidence_coverage"] +
            factors.source_diversity * self.weights["source_diversity"] +
            factors.query_coverage * self.weights["query_coverage"] +
            factors.quality_score * self.weights["quality_score"] +
            factors.gap_resolution * self.weights["gap_resolution"]
        )
        return min(max(weighted_sum, 0.0), 1.0)

    def _calculate_evidence_coverage(self, state: Dict[str, Any]) -> float:
        """
        Calculate how well evidence covers the research needs.

        Considers:
        - Number of evidence pieces
        - Quality tier distribution (GOLD/SILVER/BRONZE)
        - Evidence per sub-query
        """
        evidence_chain = state.get("evidence_chain", [])
        sub_queries = state.get("sub_queries", [])

        if not evidence_chain:
            return 0.0

        # Count by quality tier
        gold_count = sum(1 for e in evidence_chain if getattr(e, "quality_tier", "UNVERIFIED") == "GOLD")
        silver_count = sum(1 for e in evidence_chain if getattr(e, "quality_tier", "UNVERIFIED") == "SILVER")
        total_count = len(evidence_chain)

        # Base score from quantity (saturates at 100 pieces)
        quantity_score = min(total_count / 100, 1.0)

        # Quality score (weighted tier counts)
        quality_numerator = gold_count * 1.0 + silver_count * 0.7
        quality_score = min(quality_numerator / max(total_count, 1), 1.0)

        # Coverage per query (if we have sub-queries)
        if sub_queries:
            queries_with_evidence = 0
            for query in sub_queries:
                query_text = getattr(query, "query_text", str(query))
                # Simple check: does any evidence mention keywords from query
                query_words = set(query_text.lower().split())
                for e in evidence_chain:
                    text = getattr(e, "text", str(e)).lower()
                    if len(query_words & set(text.split())) >= 2:
                        queries_with_evidence += 1
                        break
            query_coverage = queries_with_evidence / len(sub_queries)
        else:
            query_coverage = 0.5  # Default if no sub-queries

        # Combine scores
        return 0.4 * quantity_score + 0.3 * quality_score + 0.3 * query_coverage

    def _calculate_source_diversity(self, state: Dict[str, Any]) -> float:
        """
        Calculate source diversity score.

        Considers:
        - Number of unique domains
        - Mix of source types (academic, government, web)
        - Geographic diversity
        """
        evidence_chain = state.get("evidence_chain", [])

        if not evidence_chain:
            return 0.0

        # Extract unique domains
        domains = set()
        source_types = set()

        for e in evidence_chain:
            url = getattr(e, "source_url", "")
            if url:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    domains.add(domain)
                except (ValueError, AttributeError):
                    # Skip malformed URLs silently - expected for some sources
                    continue

            source_type = getattr(e, "extraction_method", "web")
            source_types.add(source_type)

        # Domain diversity (saturates at 20 domains)
        domain_score = min(len(domains) / 20, 1.0)

        # Source type diversity (max 5 types)
        type_score = min(len(source_types) / 5, 1.0)

        return 0.7 * domain_score + 0.3 * type_score

    def _calculate_query_coverage(self, state: Dict[str, Any]) -> float:
        """
        Calculate how well sub-queries have been addressed.

        Considers:
        - Sub-query completion status
        - Evidence relevance to queries
        """
        sub_queries = state.get("sub_queries", [])

        if not sub_queries:
            return 0.5  # Default if no sub-queries defined

        completed = sum(
            1 for q in sub_queries
            if getattr(q, "status", "pending") == "complete"
        )

        return completed / len(sub_queries)

    def _calculate_quality_score(self, state: Dict[str, Any]) -> float:
        """
        Calculate overall quality score.

        Uses faithfulness score from auditor if available,
        otherwise falls back to critic's estimate.
        """
        # Prefer auditor's post-hoc faithfulness (actual measurement)
        post_hoc = state.get("post_hoc_faithfulness", 0.0)
        if post_hoc > 0:
            return post_hoc

        # Fall back to quality metrics
        quality_metrics = state.get("quality_metrics")
        if quality_metrics:
            if hasattr(quality_metrics, "faithfulness"):
                return quality_metrics.faithfulness
            elif isinstance(quality_metrics, dict):
                return quality_metrics.get("faithfulness", 0.0)

        return 0.0

    def _calculate_gap_resolution(self, state: Dict[str, Any]) -> float:
        """
        Calculate how well knowledge gaps have been resolved.

        Considers:
        - Current gap count vs initial
        - Priority of remaining gaps
        """
        gaps = state.get("gaps", [])

        if not gaps:
            return 1.0  # No gaps = fully resolved

        # Count gaps by priority
        high_priority = sum(1 for g in gaps if getattr(g, "priority", 3) <= 2)
        total_gaps = len(gaps)

        # Penalize high-priority gaps more
        if high_priority > 0:
            return max(0.0, 1.0 - (high_priority * 0.2) - (total_gaps * 0.05))

        # Only low-priority gaps remaining
        return max(0.0, 1.0 - (total_gaps * 0.1))

    def _calculate_novelty(self, state: Dict[str, Any]) -> float:
        """
        Calculate novelty of recent evidence/findings.

        Compares current iteration's contributions to previous.
        """
        evidence_chain = state.get("evidence_chain", [])
        iteration_count = state.get("iteration_count", 1)

        if iteration_count <= 1 or not evidence_chain:
            return 1.0  # First iteration is all novel

        # Get evidence from current iteration
        current_evidence = [
            e for e in evidence_chain
            if hasattr(e, "metadata") and
            e.metadata.get("iteration", 0) == iteration_count
        ]

        # If we can't determine iteration, estimate from recent additions
        if not current_evidence:
            # Assume last 20% is from current iteration
            cutoff = int(len(evidence_chain) * 0.8)
            current_evidence = evidence_chain[cutoff:]

        # Novelty = new evidence / total evidence (capped)
        if len(evidence_chain) > 0:
            novelty = len(current_evidence) / len(evidence_chain)
        else:
            novelty = 0.0

        return min(novelty, 1.0)

    @classmethod
    def from_config(cls, config_path: str = "config/settings/thresholds.yaml") -> "SophisticatedStopper":
        """Load stopper configuration from YAML file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            stopping_config = config.get("stopping", {})

            return cls(
                min_coverage=stopping_config.get("min_coverage", 0.85),
                min_quality=stopping_config.get("min_quality", 0.80),
                novelty_exhaustion=stopping_config.get("novelty_exhaustion", 0.05),
                max_iterations=stopping_config.get("max_iterations", 15),
                max_time_minutes=stopping_config.get("max_time_minutes", 45.0),
                weights=stopping_config.get("weights"),
            )
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return cls()
        except (KeyError, TypeError, yaml.YAMLError) as e:
            logger.warning(f"Error loading config: {e}. Using defaults.")
            return cls()


# Convenience function for integration
def should_stop_research(
    state: Dict[str, Any],
    iteration: int,
    elapsed_minutes: float,
    stopper: Optional[SophisticatedStopper] = None,
) -> Tuple[bool, str, float]:
    """
    Convenience function to check if research should stop.

    Args:
        state: Current research state
        iteration: Current iteration number
        elapsed_minutes: Time elapsed in minutes
        stopper: Optional pre-configured stopper (creates from config if None)

    Returns:
        Tuple of (should_stop, reason_detail, coverage_score)
    """
    if stopper is None:
        stopper = SophisticatedStopper.from_config()

    decision = stopper.should_stop(state, iteration, elapsed_minutes)

    return decision.should_stop, decision.reason_detail, decision.coverage_score
