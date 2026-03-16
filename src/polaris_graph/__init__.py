"""
polaris graph — clean-room research pipeline.

Uses Kimi K2.5 1T via OpenRouter for all LLM calls.
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
    """Entry point for polaris graph research pipeline."""
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
