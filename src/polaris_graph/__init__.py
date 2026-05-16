"""
polaris graph — clean-room research pipeline.

Uses OpenRouter for LLM calls (pipeline-A generator DeepSeek V4 Pro, evaluator Gemma 4 31B).
Reuses battle-tested search/fetch infrastructure from src/tools/.
"""

__all__ = [
    "run_research",
]


async def run_research(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = 30,
):
    """Entry point for polaris graph research pipeline.

    Routes to v3/v2/v1 based on PG_GRAPH_VERSION env var.
    """
    import os
    graph_version = os.getenv("PG_GRAPH_VERSION", "v1")
    if graph_version == "v3":
        from src.polaris_graph.graph_v3 import build_and_run_v3 as build_and_run
    else:
        from src.polaris_graph.graph import build_and_run

    return await build_and_run(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
        stage=stage,
        max_iterations=max_iterations,
        max_execution_minutes=max_execution_minutes,
    )
