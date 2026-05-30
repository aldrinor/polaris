"""
polaris graph — clean-room research pipeline.

Runs the LOCKED 4-role architecture per
``config/architecture/polaris_runtime_lock.yaml`` (I-meta-001 #933):
Generator (DeepSeek V4 Pro, OpenRouter) + Mirror (Cohere Command A+) +
Sentinel (IBM Granite Guardian 4.1 8B) + Judge (Qwen3.6-35B-A3B), plus the
deterministic python validators and the §-1.1 Codex audit layer. Family
segregation is enforced two ways: the legacy pairwise generator/evaluator
check ``openrouter_client.check_family_segregation`` (the two-family
invariant of CLAUDE.md §9.1), and the 4-role all-distinct-lineage check
``validate_role_families`` (Mirror, Sentinel, and Judge must each be a
distinct family from the Generator and from each other).
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
