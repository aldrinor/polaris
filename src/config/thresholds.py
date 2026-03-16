"""
POLARIS Threshold Configuration
===============================
Centralized threshold management to eliminate hardcoded magic numbers.

LAW VI: Zero Hard-Coding - All thresholds come from config/thresholds.yaml

Usage:
    from src.config.thresholds import get_threshold, Thresholds

    # Get a single threshold
    threshold = get_threshold("nli.entailment_confidence")

    # Get all thresholds as object
    thresholds = Thresholds.load()
    threshold = thresholds.nli.entailment_confidence
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Path to thresholds config
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
THRESHOLDS_FILE = CONFIG_DIR / "thresholds.yaml"

# Cached thresholds
_thresholds_cache: Optional[Dict[str, Any]] = None


def _load_thresholds() -> Dict[str, Any]:
    """Load thresholds from YAML file."""
    global _thresholds_cache

    if _thresholds_cache is not None:
        return _thresholds_cache

    if not THRESHOLDS_FILE.exists():
        raise FileNotFoundError(
            f"Thresholds config not found: {THRESHOLDS_FILE}\n"
            "Create config/thresholds.yaml with required threshold values."
        )

    with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:
        _thresholds_cache = yaml.safe_load(f)

    logger.debug(f"Loaded thresholds from {THRESHOLDS_FILE}")
    return _thresholds_cache


def get_threshold(key: str, default: Any = None) -> Any:
    """
    Get a threshold value by dotted key path.

    Args:
        key: Dotted path like "nli.entailment_confidence"
        default: Default value if key not found

    Returns:
        Threshold value

    Raises:
        KeyError: If key not found and no default provided

    Example:
        >>> get_threshold("nli.entailment_confidence")
        0.8
        >>> get_threshold("quality_tiers.gold")
        0.85
    """
    thresholds = _load_thresholds()

    parts = key.split(".")
    value = thresholds

    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif default is not None:
            return default
        else:
            raise KeyError(f"Threshold not found: {key}")

    return value


def reload_thresholds() -> None:
    """Force reload of thresholds from file."""
    global _thresholds_cache
    _thresholds_cache = None
    _load_thresholds()


@dataclass
class NLIThresholds:
    """NLI-related thresholds."""
    entailment_confidence: float = 0.8
    contradiction_confidence: float = 0.8
    neutral_confidence: float = 0.65


@dataclass
class ClusteringThresholds:
    """Clustering-related thresholds."""
    similarity: float = 0.4
    overlap: float = 0.3


@dataclass
class VerificationThresholds:
    """Verification-related thresholds."""
    aggregation: float = 0.5


@dataclass
class QualityTierThresholds:
    """Quality tier thresholds."""
    gold: float = 0.85
    silver: float = 0.65
    bronze: float = 0.40


@dataclass
class GatingThresholds:
    """Gating decision thresholds."""
    min_evidence: int = 10
    min_gold_pct: float = 0.20
    min_faithfulness: float = 0.60
    critical_faithfulness: float = 0.30
    min_diversity: int = 3
    convergence: float = 0.02
    high_quality: float = 0.90
    min_coverage: float = 0.60


@dataclass
class ScoringThresholds:
    """Scoring-related thresholds."""
    default_confidence: float = 0.8
    default_quality: float = 0.5
    default_relevance: float = 0.5
    high_relevance: float = 0.8
    high_quality: float = 0.7


@dataclass
class SupervisorThresholds:
    """Supervisor agent thresholds."""
    min_faithfulness: float = 0.7
    min_coverage: float = 0.6


# =============================================================================
# FIX 44-49: SOTA Thresholds (Calibrated via Empirical Testing)
# =============================================================================

@dataclass
class EmbeddingSimilarityThresholds:
    """FIX 44: Embedding-based semantic similarity thresholds."""
    threshold: float = 0.40
    model: str = "all-MiniLM-L6-v2"
    max_matches: int = 3
    fallback_to_word_overlap: bool = True


@dataclass
class LLMFallbackThresholds:
    """FIX 45: LLM fallback for uncertain NLI results."""
    uncertain_low: float = 0.25
    uncertain_high: float = 0.45
    enabled: bool = True
    model_tier: str = "simple"


@dataclass
class QueryValidationThresholds:
    """FIX 46: Query validation thresholds."""
    relevance_threshold: float = 0.30
    min_queries_kept: int = 5
    enabled: bool = True


@dataclass
class RevisionThresholds:
    """FIX 29-30, 32-33, 43: Revision loop thresholds."""
    max_revisions: int = 5
    batch_size: int = 15
    timeout_base_seconds: int = 120
    timeout_per_sentence: int = 5
    timeout_cap_seconds: int = 300
    word_ratio_min: float = 0.70
    cite_ratio_min: float = 0.50
    context_limit_chars: int = 30000


@dataclass
class CrossEncoderThresholds:
    """FIX 40: Cross-encoder thresholds."""
    threshold: float = 0.15
    fallback_count: int = 50
    enabled: bool = True


@dataclass
class AnalystThresholds:
    """FIX 39, 41, 85, 87, W1.3: Analyst thresholds (Operation Unshackle + SOTA updates)."""
    max_results_per_query: int = 15  # FIX 87: Lifted from 5 to 15
    max_results_total: int = 500     # W1.3 SOTA: Lifted from 250 to 500 (match SOTA fetch volume)


@dataclass
class Thresholds:
    """All thresholds as a structured object."""
    nli: NLIThresholds = field(default_factory=NLIThresholds)
    clustering: ClusteringThresholds = field(default_factory=ClusteringThresholds)
    verification: VerificationThresholds = field(default_factory=VerificationThresholds)
    quality_tiers: QualityTierThresholds = field(default_factory=QualityTierThresholds)
    gating: GatingThresholds = field(default_factory=GatingThresholds)
    scoring: ScoringThresholds = field(default_factory=ScoringThresholds)
    supervisor: SupervisorThresholds = field(default_factory=SupervisorThresholds)
    # FIX 44-49: SOTA thresholds
    embedding_similarity: EmbeddingSimilarityThresholds = field(default_factory=EmbeddingSimilarityThresholds)
    llm_fallback: LLMFallbackThresholds = field(default_factory=LLMFallbackThresholds)
    query_validation: QueryValidationThresholds = field(default_factory=QueryValidationThresholds)
    revision: RevisionThresholds = field(default_factory=RevisionThresholds)
    cross_encoder: CrossEncoderThresholds = field(default_factory=CrossEncoderThresholds)
    analyst: AnalystThresholds = field(default_factory=AnalystThresholds)

    @classmethod
    def load(cls) -> "Thresholds":
        """Load thresholds from config file."""
        data = _load_thresholds()

        return cls(
            nli=NLIThresholds(
                entailment_confidence=data.get("nli", {}).get("entailment_confidence", 0.8),
                contradiction_confidence=data.get("nli", {}).get("contradiction_confidence", 0.8),
                neutral_confidence=data.get("nli", {}).get("neutral_confidence", 0.65),
            ),
            clustering=ClusteringThresholds(
                similarity=data.get("clustering", {}).get("similarity", 0.4),
                overlap=data.get("clustering", {}).get("overlap", 0.3),
            ),
            verification=VerificationThresholds(
                aggregation=data.get("verification", {}).get("aggregation", 0.5),
            ),
            quality_tiers=QualityTierThresholds(
                gold=data.get("quality_tiers", {}).get("gold", 0.85),
                silver=data.get("quality_tiers", {}).get("silver", 0.65),
                bronze=data.get("quality_tiers", {}).get("bronze", 0.40),
            ),
            gating=GatingThresholds(
                min_evidence=data.get("gating", {}).get("min_evidence", 10),
                min_gold_pct=data.get("gating", {}).get("min_gold_pct", 0.20),
                min_faithfulness=data.get("gating", {}).get("min_faithfulness", 0.60),
                critical_faithfulness=data.get("gating", {}).get("critical_faithfulness", 0.30),
                min_diversity=data.get("gating", {}).get("min_diversity", 3),
                convergence=data.get("gating", {}).get("convergence", 0.02),
                high_quality=data.get("gating", {}).get("high_quality", 0.90),
                min_coverage=data.get("gating", {}).get("min_coverage", 0.60),
            ),
            scoring=ScoringThresholds(
                default_confidence=data.get("scoring", {}).get("default_confidence", 0.8),
                default_quality=data.get("scoring", {}).get("default_quality", 0.5),
                default_relevance=data.get("scoring", {}).get("default_relevance", 0.5),
                high_relevance=data.get("scoring", {}).get("high_relevance", 0.8),
                high_quality=data.get("scoring", {}).get("high_quality", 0.7),
            ),
            supervisor=SupervisorThresholds(
                min_faithfulness=data.get("supervisor", {}).get("min_faithfulness", 0.7),
                min_coverage=data.get("supervisor", {}).get("min_coverage", 0.6),
            ),
            # FIX 44-49: SOTA thresholds
            embedding_similarity=EmbeddingSimilarityThresholds(
                threshold=data.get("embedding_similarity", {}).get("threshold", 0.40),
                model=data.get("embedding_similarity", {}).get("model", "all-MiniLM-L6-v2"),
                max_matches=data.get("embedding_similarity", {}).get("max_matches", 3),
                fallback_to_word_overlap=data.get("embedding_similarity", {}).get("fallback_to_word_overlap", True),
            ),
            llm_fallback=LLMFallbackThresholds(
                uncertain_low=data.get("llm_fallback", {}).get("uncertain_low", 0.25),
                uncertain_high=data.get("llm_fallback", {}).get("uncertain_high", 0.45),
                enabled=data.get("llm_fallback", {}).get("enabled", True),
                model_tier=data.get("llm_fallback", {}).get("model_tier", "simple"),
            ),
            query_validation=QueryValidationThresholds(
                relevance_threshold=data.get("query_validation", {}).get("relevance_threshold", 0.30),
                min_queries_kept=data.get("query_validation", {}).get("min_queries_kept", 5),
                enabled=data.get("query_validation", {}).get("enabled", True),
            ),
            revision=RevisionThresholds(
                max_revisions=data.get("revision", {}).get("max_revisions", 5),
                batch_size=data.get("revision", {}).get("batch_size", 15),
                timeout_base_seconds=data.get("revision", {}).get("timeout_base_seconds", 120),
                timeout_per_sentence=data.get("revision", {}).get("timeout_per_sentence", 5),
                timeout_cap_seconds=data.get("revision", {}).get("timeout_cap_seconds", 300),
                word_ratio_min=data.get("revision", {}).get("word_ratio_min", 0.70),
                cite_ratio_min=data.get("revision", {}).get("cite_ratio_min", 0.50),
                context_limit_chars=data.get("revision", {}).get("context_limit_chars", 30000),
            ),
            cross_encoder=CrossEncoderThresholds(
                threshold=data.get("cross_encoder", {}).get("threshold", 0.15),
                fallback_count=data.get("cross_encoder", {}).get("fallback_count", 50),
                enabled=data.get("cross_encoder", {}).get("enabled", True),
            ),
            analyst=AnalystThresholds(
                max_results_per_query=data.get("analyst", {}).get("max_results_per_query", 15),
                max_results_total=data.get("analyst", {}).get("max_results_total", 500),
            ),
        )


def validate_thresholds() -> bool:
    """
    Validate that all required thresholds are present and valid.

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    required_keys = [
        "nli.entailment_confidence",
        "nli.contradiction_confidence",
        "nli.neutral_confidence",
        "clustering.similarity",
        "verification.aggregation",
        "quality_tiers.gold",
        "quality_tiers.silver",
        "quality_tiers.bronze",
        "gating.min_evidence",
        "gating.min_gold_pct",
        "gating.min_faithfulness",
        "gating.critical_faithfulness",
        "gating.min_diversity",
        "gating.convergence",
        "gating.high_quality",
        "scoring.default_confidence",
        "scoring.high_relevance",
        "scoring.high_quality",
    ]

    errors = []

    for key in required_keys:
        try:
            value = get_threshold(key)
            # Validate numeric types
            if not isinstance(value, (int, float)):
                errors.append(f"{key}: expected number, got {type(value).__name__}")
        except KeyError:
            errors.append(f"{key}: missing")

    if errors:
        raise ValueError(f"Threshold validation failed:\n" + "\n".join(errors))

    return True
