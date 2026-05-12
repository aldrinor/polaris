"""API — public entry points for the research pipeline.

Slice 001: intake.py orchestrates intake → classify → ambiguity → decision.
Slice 002+: retrieval, generator, audit endpoints will live here.
"""

from polaris_graph.api.intake import (
    IntakeError,
    process_intake,
)

__all__ = [
    "IntakeError",
    "process_intake",
]
