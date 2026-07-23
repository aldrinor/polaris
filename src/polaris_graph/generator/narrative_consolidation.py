"""Pre-generation narrative guidance for section writers."""
from __future__ import annotations

from typing import Any, Sequence

NARRATIVE_GUIDANCE = (
    "Use cohesive scholarly prose. For adjacent cited findings, explicitly explain with their "
    "citations why they agree, differ, or alter the interpretation of one another; emphasize the key finding or "
    "term with Markdown bold; describe evidence limitations through publication type, "
    "representativeness, and risk of bias rather than implementation vocabulary."
)


def thread_narrative_guidance(plans: Sequence[Any]) -> None:
    """Ask the verified writer for cited relational transitions before generation."""
    for plan in plans:
        plan.focus = f"{plan.focus.rstrip()} {NARRATIVE_GUIDANCE}"
