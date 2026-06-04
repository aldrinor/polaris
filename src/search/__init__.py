"""
POLARIS Search Module
=====================
Search engine integrations for federated search execution.
Includes SOTA query amplification and Serper deep integration.
"""

# I-cap-004 (#1068): `src.search.engines` was removed in a repo cleanup but this unguarded import
# remained, making the entire `src.search` package un-importable. That silently broke
# `src.agents.search_agent` (which imports `src.search.query_amplifier`), which the benchmark's STORM
# AND agentic features reach into via `searcher._import_search_tools` -> both fell open / never fired.
# These engine symbols are DEAD (used nowhere in src/polaris_graph or scripts). Guard like the
# query_amplifier import below so the package stays importable.
try:
    from src.search.engines import (
        SearchEngine,
        SerperEngine,
        PubMedEngine,
        SemanticScholarEngine,
        OpenAlexEngine,
        get_search_engines,
    )
except ImportError:
    pass  # engines module archived in cleanup; symbols unused by the active pipeline

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

# I-cap-004 (#1068): `src.search.fan_out_executor` was ALSO removed in the cleanup but left unguarded
# here (same class of bug as engines above). Its symbols are unused by the active pipeline
# (src.agents.search_agent only needs query_amplifier + serper_client, both present). Guard it so the
# `src.search` package imports cleanly and the STORM + agentic search tools actually resolve.
try:
    from src.search.fan_out_executor import (
        FanOutExecutor,
        SearchResult,
        FanOutStats,
        CircuitBreaker,
        execute_fan_out,
        calculate_expected_results,
    )
except ImportError:
    pass  # fan_out_executor module archived in cleanup; symbols unused by the active pipeline

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
