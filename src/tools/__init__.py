"""
POLARIS tools module.

After Phase A cleanup (commit 0cf2a65), several historical tools
(vision_tool, pdf_parser, agent_swarm_full, vision_processor,
long_form_generator, streaming_reasoner, user_feedback,
file_analyzer, browser_automation) were archived because no live
entry point imported them.

The `__init__.py` used to re-export those names unconditionally, which
broke `from src.tools import AccessBypass` after the archive move.
Guarded imports below keep active tools discoverable without hard-
failing on the archived ones.
"""

# Access bypass — actively used by pipeline A retrieval (post-R8d).
from .access_bypass import AccessBypass, AccessResult  # noqa: F401

__all__ = [
    "AccessBypass",
    "AccessResult",
]
