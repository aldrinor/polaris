"""
POLARIS v3 Iteration Manager

Manages the ReAct loop iteration with:
- Knowledge saturation detection
- Convergence criteria
- Circuit breakers
- Gap filling prioritization

Based on Gemini Deep Research patterns with configurable parameters.
Depth configuration loaded from .env via DepthConfig (LAW VI: Zero hard-coding).
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived
from src.orchestration.stopping_mechanism import SophisticatedStopper, StopReason


logger = logging.getLogger(__name__)

# O3 Parity: Global sophisticated stopper instance
_sophisticated_stopper: Optional[SophisticatedStopper] = None


def get_sophisticated_stopper() -> SophisticatedStopper:
    """Get or create the sophisticated stopper instance."""
    global _sophisticated_stopper
    if _sophisticated_stopper is None:
        _sophisticated_stopper = SophisticatedStopper()
    return _sophisticated_stopper


def reset_sophisticated_stopper():
    """Reset the sophisticated stopper (for testing)."""
    global _sophisticated_stopper
    _sophisticated_stopper = None


# =============================================================================
# Configuration
# =============================================================================

class IterationConfig(BaseModel):
    """Configuration for iteration management.

    SOTA-aligned defaults per DepthConfig (LAW VI: Zero hard-coding).
    """
    # Iteration limits - SOTA: 5-15 iterations for deep research
    min_iterations: int = Field(default=5, description="Minimum iterations before considering convergence (SOTA: 5)")
    max_iterations: int = Field(default=15, description="Hard maximum iterations (SOTA: 15)")

    # Time limits - SOTA: Up to 45 minutes for comprehensive research
    max_execution_minutes: int = Field(default=45, description="Maximum execution time in minutes (SOTA: 45)")

    # Saturation thresholds - SOTA: More aggressive saturation detection
    novelty_threshold: float = Field(default=0.05, description="Minimum novelty to continue (SOTA: 0.05)")
    consecutive_low_novelty: int = Field(default=3, description="Low novelty iterations before stopping (SOTA: 3)")

    # Quality thresholds
    min_faithfulness: float = Field(default=0.70, description="Minimum faithfulness score")
    min_context_precision: float = Field(default=0.60, description="Minimum context precision")
    min_answer_relevancy: float = Field(default=0.70, description="Minimum answer relevancy")

    # Evidence thresholds - SOTA: Higher evidence requirements
    min_evidence_count: int = Field(default=50, description="Minimum evidence pieces (SOTA: 50)")
    min_source_diversity: int = Field(default=10, description="Minimum unique source types (SOTA: 10)")

    # Gap filling
    max_gap_fill_attempts: int = Field(default=5, description="Max attempts to fill same gap (SOTA: 5)")


class ConvergenceReason(str, Enum):
    """Reasons for convergence."""
    MAX_ITERATIONS = "max_iterations_reached"
    MAX_TIME = "max_execution_time_reached"
    KNOWLEDGE_SATURATION = "knowledge_saturation_detected"
    QUALITY_THRESHOLD = "quality_thresholds_met"
    NO_GAPS_REMAINING = "no_gaps_remaining"
    CIRCUIT_BREAKER = "circuit_breaker_triggered"
    MIN_EVIDENCE_MET = "minimum_evidence_collected"


@dataclass
class IterationMetrics:
    """Metrics tracked per iteration."""
    iteration: int
    timestamp: str
    evidence_count: int
    new_evidence_count: int
    novelty_score: float
    faithfulness: float
    context_precision: float
    answer_relevancy: float
    gaps_identified: int
    gaps_filled: int
    source_types: List[str]


@dataclass
class SaturationState:
    """State for knowledge saturation tracking."""
    total_evidence: int = 0
    evidence_hashes: set = field(default_factory=set)
    novelty_history: List[float] = field(default_factory=list)
    consecutive_low_novelty: int = 0
    source_types_seen: set = field(default_factory=set)
    gap_fill_attempts: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# Iteration Manager
# =============================================================================

class IterationManager:
    """
    Manages ReAct loop iteration with saturation detection and convergence.
    """

    def __init__(self, config: Optional[IterationConfig] = None):
        """
        Initialize the iteration manager.

        Args:
            config: Iteration configuration (uses defaults if None)
        """
        self.config = config or IterationConfig()
        self.saturation = SaturationState()
        self.metrics_history: List[IterationMetrics] = []
        self.start_time = datetime.now(timezone.utc)
        self.converged = False
        self.convergence_reason: Optional[ConvergenceReason] = None

    def should_continue(
        self,
        state: Dict[str, Any],
        current_iteration: int
    ) -> Tuple[bool, Optional[ConvergenceReason]]:
        """
        Determine if iteration should continue.

        Args:
            state: Current research state
            current_iteration: Current iteration number

        Returns:
            Tuple of (should_continue, convergence_reason if stopping)
        """
        # =====================================================================
        # O3 PARITY: Use SophisticatedStopper for multi-factor coverage analysis
        # =====================================================================
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 60

        try:
            stopper = get_sophisticated_stopper()
            stop_decision = stopper.should_stop(state, current_iteration, elapsed)

            if stop_decision.should_stop:
                # Map StopReason to ConvergenceReason
                reason_map = {
                    StopReason.COVERAGE_COMPLETE: ConvergenceReason.QUALITY_THRESHOLD,
                    StopReason.QUALITY_THRESHOLD: ConvergenceReason.QUALITY_THRESHOLD,
                    StopReason.NOVELTY_EXHAUSTED: ConvergenceReason.KNOWLEDGE_SATURATION,
                    StopReason.MAX_ITERATIONS: ConvergenceReason.MAX_ITERATIONS,
                    StopReason.TIME_LIMIT: ConvergenceReason.MAX_TIME,
                }
                convergence_reason = reason_map.get(
                    stop_decision.reason,
                    ConvergenceReason.QUALITY_THRESHOLD
                )
                logger.info(
                    f"[O3 PARITY] SophisticatedStopper decided to STOP: "
                    f"reason={stop_decision.reason.value}, "
                    f"coverage={stop_decision.coverage_score:.2%}, "
                    f"reason_detail={stop_decision.reason_detail}"
                )
                return False, convergence_reason
            else:
                logger.info(
                    f"[O3 PARITY] SophisticatedStopper: CONTINUE "
                    f"(coverage={stop_decision.coverage_score:.2%})"
                )
        except Exception as e:
            logger.warning(f"[O3 PARITY] SophisticatedStopper error, falling back: {e}")
            # Fall through to legacy checks

        # =====================================================================
        # LEGACY: Circuit breaker checks (kept as fallback)
        # =====================================================================

        # 1. Max iterations
        if current_iteration >= self.config.max_iterations:
            logger.info(f"Max iterations ({self.config.max_iterations}) reached")
            return False, ConvergenceReason.MAX_ITERATIONS

        # 2. Max execution time
        if elapsed >= self.config.max_execution_minutes:
            logger.info(f"Max execution time ({self.config.max_execution_minutes}m) reached")
            return False, ConvergenceReason.MAX_TIME

        # 3. Minimum iterations not met
        if current_iteration < self.config.min_iterations:
            return True, None

        # Check convergence conditions

        # 4. Quality thresholds met
        # FIX 23 (Gemini Audit FIX 3): Prefer Auditor's measured faithfulness
        # (post_hoc_faithfulness) over Critic's estimate (quality_metrics.faithfulness).
        # Critic's score is an LLM guess (~0.5); Auditor's is a MiniCheck measurement.
        quality = state.get("quality_metrics", {})
        if isinstance(quality, dict):
            faithfulness = quality.get("faithfulness", 0)
            precision = quality.get("context_precision", 0)
            relevancy = quality.get("answer_relevancy", 0)
        else:
            faithfulness = getattr(quality, "faithfulness", 0)
            precision = getattr(quality, "context_precision", 0)
            relevancy = getattr(quality, "answer_relevancy", 0)

        # FIX 23: Override Critic's faithfulness with Auditor's if available
        auditor_faithfulness = state.get("post_hoc_faithfulness", 0)
        if auditor_faithfulness > 0:
            logger.info(
                f"FIX 23: Using Auditor faithfulness ({auditor_faithfulness:.2f}) "
                f"over Critic estimate ({faithfulness:.2f})"
            )
            faithfulness = auditor_faithfulness

        if (faithfulness >= self.config.min_faithfulness and
            precision >= self.config.min_context_precision and
            relevancy >= self.config.min_answer_relevancy):
            logger.info(f"Quality thresholds met: F={faithfulness:.2f}, P={precision:.2f}, R={relevancy:.2f}")
            return False, ConvergenceReason.QUALITY_THRESHOLD

        # 5. Knowledge saturation
        if self.saturation.consecutive_low_novelty >= self.config.consecutive_low_novelty:
            logger.info(f"Knowledge saturation detected after {self.saturation.consecutive_low_novelty} low-novelty iterations")
            return False, ConvergenceReason.KNOWLEDGE_SATURATION

        # 6. No gaps remaining
        gaps = state.get("identified_gaps", [])
        if not gaps and current_iteration >= self.config.min_iterations:
            logger.info("No gaps remaining to fill")
            return False, ConvergenceReason.NO_GAPS_REMAINING

        # Continue iterating
        return True, None

    def update_saturation(
        self,
        state: Dict[str, Any],
        current_iteration: int
    ) -> float:
        """
        Update saturation state and calculate novelty score.

        Args:
            state: Current research state
            current_iteration: Current iteration number

        Returns:
            Novelty score for this iteration
        """
        evidence_chain = state.get("evidence_chain", [])

        # Count new evidence
        new_evidence = 0
        for evidence in evidence_chain:
            # Get evidence ID (Evidence can be Pydantic model or dict)
            if isinstance(evidence, dict):
                eid = evidence.get("evidence_id", "")
            else:
                eid = getattr(evidence, "evidence_id", "")

            if eid and eid not in self.saturation.evidence_hashes:
                self.saturation.evidence_hashes.add(eid)
                new_evidence += 1

                # Track source type
                if isinstance(evidence, dict):
                    source_type = evidence.get("source_type", "unknown")
                else:
                    source_type = getattr(evidence, "source_type", "unknown")
                self.saturation.source_types_seen.add(source_type)

        # Calculate novelty score
        total_evidence = len(evidence_chain)
        if total_evidence == 0:
            novelty = 1.0  # First iteration, all novel
        else:
            novelty = new_evidence / max(total_evidence, 1)

        # Update history
        self.saturation.novelty_history.append(novelty)
        self.saturation.total_evidence = total_evidence

        # Track consecutive low novelty
        if novelty < self.config.novelty_threshold:
            self.saturation.consecutive_low_novelty += 1
            logger.info(f"Low novelty iteration ({novelty:.2f} < {self.config.novelty_threshold}), streak: {self.saturation.consecutive_low_novelty}")
        else:
            self.saturation.consecutive_low_novelty = 0

        # Record metrics
        quality = state.get("quality_metrics", {})
        critic_faithfulness = quality.get("faithfulness", 0) if isinstance(quality, dict) else getattr(quality, "faithfulness", 0)
        # FIX 23: Prefer Auditor's measured faithfulness for metrics
        auditor_faithfulness = state.get("post_hoc_faithfulness", 0)
        recorded_faithfulness = auditor_faithfulness if auditor_faithfulness > 0 else critic_faithfulness

        metrics = IterationMetrics(
            iteration=current_iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_count=total_evidence,
            new_evidence_count=new_evidence,
            novelty_score=novelty,
            faithfulness=recorded_faithfulness,
            context_precision=quality.get("context_precision", 0) if isinstance(quality, dict) else getattr(quality, "context_precision", 0),
            answer_relevancy=quality.get("answer_relevancy", 0) if isinstance(quality, dict) else getattr(quality, "answer_relevancy", 0),
            gaps_identified=len(state.get("identified_gaps", [])),
            gaps_filled=state.get("gaps_filled", 0),
            source_types=list(self.saturation.source_types_seen),
        )
        self.metrics_history.append(metrics)

        logger.info(f"Iteration {current_iteration}: novelty={novelty:.2f}, evidence={total_evidence}, new={new_evidence}")

        return novelty

    def prioritize_gaps(
        self,
        gaps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prioritize gaps for filling based on importance and attempts.

        Args:
            gaps: List of identified gaps

        Returns:
            Sorted list of gaps to address
        """
        scored_gaps = []

        for gap in gaps:
            gap_id = gap.get("gap_id", str(hash(str(gap))))

            # Check if max attempts exceeded
            attempts = self.saturation.gap_fill_attempts.get(gap_id, 0)
            if attempts >= self.config.max_gap_fill_attempts:
                continue  # Skip this gap

            # Score based on severity and attempts
            severity = gap.get("severity", "medium")
            severity_score = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}.get(severity, 0.5)

            # Penalize gaps that have been attempted multiple times
            attempt_penalty = attempts * 0.2

            final_score = severity_score - attempt_penalty

            scored_gaps.append({
                **gap,
                "priority_score": final_score,
                "attempts": attempts
            })

        # Sort by priority score (highest first)
        scored_gaps.sort(key=lambda g: g["priority_score"], reverse=True)

        return scored_gaps

    def record_gap_attempt(self, gap_id: str):
        """Record an attempt to fill a gap."""
        self.saturation.gap_fill_attempts[gap_id] = self.saturation.gap_fill_attempts.get(gap_id, 0) + 1

    def get_iteration_summary(self) -> Dict[str, Any]:
        """Get summary of all iterations."""
        return {
            "total_iterations": len(self.metrics_history),
            "total_evidence": self.saturation.total_evidence,
            "source_types": list(self.saturation.source_types_seen),
            "novelty_trend": self.saturation.novelty_history,
            "converged": self.converged,
            "convergence_reason": self.convergence_reason.value if self.convergence_reason else None,
            "execution_time_minutes": (datetime.now(timezone.utc) - self.start_time).total_seconds() / 60,
            "metrics_history": [
                {
                    "iteration": m.iteration,
                    "evidence_count": m.evidence_count,
                    "novelty_score": m.novelty_score,
                    "faithfulness": m.faithfulness,
                }
                for m in self.metrics_history
            ]
        }

    def mark_converged(self, reason: ConvergenceReason):
        """Mark iteration as converged with reason."""
        self.converged = True
        self.convergence_reason = reason
        logger.info(f"Iteration converged: {reason.value}")


# =============================================================================
# Gap Analysis
# =============================================================================

def analyze_gaps(
    state: Dict[str, Any],
    iteration_manager: IterationManager
) -> Dict[str, Any]:
    """
    Analyze gaps in the current research state.

    Args:
        state: Current research state
        iteration_manager: Iteration manager instance

    Returns:
        Gap analysis with prioritized gaps
    """
    identified_gaps = state.get("identified_gaps", [])
    evidence_chain = state.get("evidence_chain", [])
    sub_queries = state.get("sub_queries", [])

    # Helper to safely get attribute from dict or Pydantic model
    def safe_get(obj, key, default=""):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # Analyze sub-query coverage
    covered_queries = set()
    for evidence in evidence_chain:
        query_id = safe_get(evidence, "sub_query_id", "")
        if query_id:
            covered_queries.add(query_id)

    # Find uncovered sub-queries
    uncovered_queries = []
    for sq in sub_queries:
        query_id = safe_get(sq, "query_id", "")
        if query_id and query_id not in covered_queries:
            uncovered_queries.append({
                "gap_id": f"uncovered_{query_id}",
                "gap_type": "uncovered_query",
                "description": f"Sub-query not covered: {safe_get(sq, 'query_text', '')}",
                "severity": "high",
            })

    # Combine all gaps
    all_gaps = identified_gaps + uncovered_queries

    # Prioritize
    prioritized = iteration_manager.prioritize_gaps(all_gaps)

    return {
        "total_gaps": len(all_gaps),
        "identified_gaps": len(identified_gaps),
        "uncovered_queries": len(uncovered_queries),
        "prioritized_gaps": prioritized[:5],  # Top 5 gaps
        "coverage_ratio": len(covered_queries) / max(len(sub_queries), 1),
    }


# =============================================================================
# Convergence Helpers
# =============================================================================

def check_evidence_sufficiency(
    state: Dict[str, Any],
    config: IterationConfig
) -> Tuple[bool, str]:
    """
    Check if evidence is sufficient.

    Args:
        state: Current research state
        config: Iteration configuration

    Returns:
        Tuple of (is_sufficient, reason)
    """
    evidence_chain = state.get("evidence_chain", [])

    # Check minimum evidence count
    if len(evidence_chain) < config.min_evidence_count:
        return False, f"Insufficient evidence ({len(evidence_chain)} < {config.min_evidence_count})"

    # Check source diversity
    source_types = set()
    for evidence in evidence_chain:
        if isinstance(evidence, dict):
            source_type = evidence.get("source_type", "unknown")
        else:
            source_type = getattr(evidence, "source_type", "unknown")
        source_types.add(source_type)

    if len(source_types) < config.min_source_diversity:
        return False, f"Insufficient source diversity ({len(source_types)} < {config.min_source_diversity})"

    return True, "Evidence sufficient"


def calculate_overall_progress(
    state: Dict[str, Any],
    iteration_manager: IterationManager
) -> float:
    """
    Calculate overall research progress (0-1).

    Args:
        state: Current research state
        iteration_manager: Iteration manager

    Returns:
        Progress score from 0 to 1
    """
    weights = {
        "iteration_progress": 0.2,
        "evidence_progress": 0.3,
        "quality_progress": 0.3,
        "gap_progress": 0.2,
    }

    config = iteration_manager.config
    current_iter = state.get("iteration_count", 0)

    # Iteration progress
    iter_progress = min(current_iter / config.max_iterations, 1.0)

    # Evidence progress
    evidence_count = len(state.get("evidence_chain", []))
    evidence_progress = min(evidence_count / (config.min_evidence_count * 2), 1.0)

    # Quality progress
    quality = state.get("quality_metrics", {})
    if isinstance(quality, dict):
        avg_quality = (
            quality.get("faithfulness", 0) +
            quality.get("context_precision", 0) +
            quality.get("answer_relevancy", 0)
        ) / 3
    else:
        avg_quality = (
            getattr(quality, "faithfulness", 0) +
            getattr(quality, "context_precision", 0) +
            getattr(quality, "answer_relevancy", 0)
        ) / 3
    quality_progress = min(avg_quality / 0.8, 1.0)  # 0.8 is target

    # Gap progress (inverse - fewer gaps = more progress)
    gaps = state.get("identified_gaps", [])
    gap_progress = 1.0 - min(len(gaps) / 10, 1.0)

    # Weighted sum
    progress = (
        weights["iteration_progress"] * iter_progress +
        weights["evidence_progress"] * evidence_progress +
        weights["quality_progress"] * quality_progress +
        weights["gap_progress"] * gap_progress
    )

    return progress


# =============================================================================
# Factory Functions
# =============================================================================

def create_iteration_manager(
    max_iterations: int = None,
    max_execution_minutes: int = None,
    min_faithfulness: float = 0.70
) -> IterationManager:
    """
    Create an iteration manager with custom configuration.

    Uses DepthConfig for defaults if not specified (LAW VI: Zero hard-coding).

    Args:
        max_iterations: Maximum iterations (defaults to DepthConfig)
        max_execution_minutes: Maximum execution time (defaults to DepthConfig)
        min_faithfulness: Minimum faithfulness threshold

    Returns:
        Configured IterationManager
    """
    # Get defaults from DepthConfig (LAW VI)
    depth_config = get_depth_config()
    iteration_cfg = depth_config.iteration

    config = IterationConfig(
        min_iterations=iteration_cfg.min_iterations,
        max_iterations=max_iterations or iteration_cfg.max_iterations,
        max_execution_minutes=max_execution_minutes or iteration_cfg.max_execution_minutes,
        novelty_threshold=iteration_cfg.novelty_threshold,
        consecutive_low_novelty=iteration_cfg.consecutive_low_novelty,
        min_source_diversity=iteration_cfg.min_source_diversity,
        min_faithfulness=min_faithfulness,
    )
    return IterationManager(config)


def create_sota_iteration_manager() -> IterationManager:
    """
    Create an iteration manager with full SOTA configuration.

    Uses all values from DepthConfig for SOTA-level deep research.

    Returns:
        IterationManager configured for SOTA parity
    """
    depth_config = get_depth_config()
    iteration_cfg = depth_config.iteration

    config = IterationConfig(
        min_iterations=iteration_cfg.min_iterations,
        max_iterations=iteration_cfg.max_iterations,
        max_execution_minutes=iteration_cfg.max_execution_minutes,
        novelty_threshold=iteration_cfg.novelty_threshold,
        consecutive_low_novelty=iteration_cfg.consecutive_low_novelty,
        min_source_diversity=iteration_cfg.min_source_diversity,
        min_evidence_count=depth_config.evidence_extraction.min_evidence_chunks,
    )

    logger.info(
        f"Created SOTA iteration manager: "
        f"min_iter={config.min_iterations}, max_iter={config.max_iterations}, "
        f"max_time={config.max_execution_minutes}m, novelty_thr={config.novelty_threshold}"
    )

    return IterationManager(config)
