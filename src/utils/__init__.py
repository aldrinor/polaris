"""
POLARIS Utilities Package

Exports utility modules for:
- Quality metrics tracking
- Result caching
- Circuit breakers and graceful degradation
- Source quality assessment
- RAGAS evaluation
"""

from .quality_metrics import (
    QualityTracker,
    SourceDiversityScorer,
    GeographicCoverageTracker,
    IterationMetrics,
    create_quality_tracker,
    create_diversity_scorer,
    create_geographic_tracker,
)

from .result_cache import (
    ResultCache,
    SearchResultCache,
    LLMResponseCache,
    cached,
    parallel_async,
    parallel_sync,
    get_search_cache,
    get_llm_cache,
)

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitOpenError,
    GracefulDegrader,
    HealthMonitor,
    circuit_breaker,
    get_degrader,
    get_health_monitor,
)

__all__ = [
    # Quality Metrics
    "QualityTracker",
    "SourceDiversityScorer",
    "GeographicCoverageTracker",
    "IterationMetrics",
    "create_quality_tracker",
    "create_diversity_scorer",
    "create_geographic_tracker",
    # Caching
    "ResultCache",
    "SearchResultCache",
    "LLMResponseCache",
    "cached",
    "parallel_async",
    "parallel_sync",
    "get_search_cache",
    "get_llm_cache",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitOpenError",
    "GracefulDegrader",
    "HealthMonitor",
    "circuit_breaker",
    "get_degrader",
    "get_health_monitor",
]
