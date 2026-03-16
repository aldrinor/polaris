"""
POLARIS v3 Agents Module (Legacy)

Multi-agent architecture for agentic research workflow.
Production code uses src.polaris_graph instead.

Imports are lazy-guarded because archived dependencies
(src.callbacks, src.formatters, src.depth) may be missing.
"""

try:
    from .base_agent import BaseAgent, AgentConfig, register_agent, get_agent_class, list_agents
except ImportError:
    pass

try:
    from .triage_agent import TriageAgent
    from .planner_agent import PlannerAgent
    from .supervisor_agent import SupervisorAgent
    from .search_agent import SearchAgent
    from .analyst_agent import AnalystAgent
    from .verifier_agent import VerifierAgent
    from .synthesizer_agent import SynthesizerAgent
    from .citefirst_synthesizer import CitefirstSynthesizer
    from .critic_agent import CriticAgent
    from .auditor_agent import AuditorAgent
    from .clarification_agent import ClarificationAgent
except ImportError:
    pass

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "register_agent",
    "get_agent_class",
    "list_agents",
    "TriageAgent",
    "PlannerAgent",
    "SupervisorAgent",
    "SearchAgent",
    "AnalystAgent",
    "VerifierAgent",
    "SynthesizerAgent",
    "CitefirstSynthesizer",
    "CriticAgent",
    "AuditorAgent",
    "ClarificationAgent",
]
