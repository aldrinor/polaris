"""
POLARIS v3 Orchestration Module

LangGraph-based state machine for agentic research workflow.

Components:
- state.py: ResearchState TypedDict definition
- persistence.py: State save/load to JSON
- graph.py: LangGraph state machine
- iteration_manager.py: ReAct loop iteration with saturation detection
- dynamic_replanner.py: Adaptive re-planning based on research findings
- stopping_mechanism.py: Coverage-based stopping mechanism
"""

from .state import ResearchState, create_initial_state, serialize_state, deserialize_state
from .persistence import StatePersistence, save_state, load_state, get_persistence
try:
    from .graph import (
        build_research_graph,
        compile_graph,
        run_research,
        run_research_with_config,
        get_iteration_manager,
        set_iteration_manager,
        # Reasoning features
        get_dynamic_replanner,
        get_sophisticated_stopper,
        get_reasoning_context,
        reset_reasoning_state,
        reset_o3_parity_state,  # Backward compatibility alias
    )
except ImportError:
    # Legacy graph depends on src.formatters which may be archived.
    # Production code uses src.polaris_graph.graph instead.
    pass
try:
    from .iteration_manager import (
        IterationManager,
        IterationConfig,
        ConvergenceReason,
        IterationMetrics,
        SaturationState,
        create_iteration_manager,
        analyze_gaps,
        check_evidence_sufficiency,
        calculate_overall_progress,
    )
except ImportError:
    pass
# Reasoning features
try:
    from .dynamic_replanner import DynamicReplanner, ReplanTrigger, ReplanDecision
    from .stopping_mechanism import SophisticatedStopper, StopReason, StopDecision, should_stop_research
except ImportError:
    pass

__all__ = [
    # State
    "ResearchState",
    "create_initial_state",
    "serialize_state",
    "deserialize_state",
    # Persistence
    "StatePersistence",
    "save_state",
    "load_state",
    "get_persistence",
    # Graph
    "build_research_graph",
    "compile_graph",
    "run_research",
    "run_research_with_config",
    "get_iteration_manager",
    "set_iteration_manager",
    # Iteration Management
    "IterationManager",
    "IterationConfig",
    "ConvergenceReason",
    "IterationMetrics",
    "SaturationState",
    "create_iteration_manager",
    "analyze_gaps",
    "check_evidence_sufficiency",
    "calculate_overall_progress",
    # Reasoning - Dynamic Re-Planning
    "DynamicReplanner",
    "ReplanTrigger",
    "ReplanDecision",
    "get_dynamic_replanner",
    # Reasoning - Sophisticated Stopping
    "SophisticatedStopper",
    "StopReason",
    "StopDecision",
    "should_stop_research",
    "get_sophisticated_stopper",
    # Reasoning - Context Tracking
    "get_reasoning_context",
    "reset_reasoning_state",
    "reset_o3_parity_state",  # Backward compatibility
]
