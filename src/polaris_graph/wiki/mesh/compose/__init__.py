"""Mesh compose package — answer composition + artifact rendering."""

from .artifact_directives import render_artifacts
from .composer import ComposeResult, compose_answer

__all__ = [
    "ComposeResult",
    "compose_answer",
    "render_artifacts",
]
