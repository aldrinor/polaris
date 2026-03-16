"""
POLARIS Search Module
=====================
Search engine integrations for federated search execution.
Includes SOTA query amplification and Serper deep integration.
"""

from src.search.engines import (
    SearchEngine,
    SerperEngine,
    PubMedEngine,
    SemanticScholarEngine,
    OpenAlexEngine,
    get_search_engines,
)

try:
    from src.search.query_amplifier import (
        QueryAmplifier,
        AmplificationResult,
        amplify_query,
        amplify_queries,
        count_amplification_factor,
    )
except ImportError:
    pass  # Legacy dependency (src.depth) may be archived

from src.search.serper_client import (
    SerperClient,
    SerperResult,
    SerperStats,
    get_serper_client,
)

from src.search.fan_out_executor import (
    FanOutExecutor,
    SearchResult,
    FanOutStats,
    CircuitBreaker,
    execute_fan_out,
    calculate_expected_results,
)

__all__ = [
    # Engines
    "SearchEngine",
    "SerperEngine",
    "PubMedEngine",
    "SemanticScholarEngine",
    "OpenAlexEngine",
    "get_search_engines",
    # Query Amplification (SOTA)
    "QueryAmplifier",
    "AmplificationResult",
    "amplify_query",
    "amplify_queries",
    "count_amplification_factor",
    # Serper Client (SOTA)
    "SerperClient",
    "SerperResult",
    "SerperStats",
    "get_serper_client",
    # Fan-Out Executor (SOTA)
    "FanOutExecutor",
    "SearchResult",
    "FanOutStats",
    "CircuitBreaker",
    "execute_fan_out",
    "calculate_expected_results",
]
