"""Instruction understanding — parse buried constraints out of a task prompt.

This package is standalone (no wiring into the driver / generator yet). It
exposes :func:`extract_constraints`, an adversarial LLM pass that mines a
free-text task prompt for the concrete deliverable constraints an author must
honor (source types, languages, recency, required coverage, exclusions,
format, length, tone) — including rules phrased mid-sentence or as soft asides.
"""

from src.polaris_graph.instruction.constraint_extractor import (
    Constraints,
    extract_constraints,
    parse_constraints_json,
)
from src.polaris_graph.instruction.source_eligibility import (
    classify_source,
    filter_eligible,
)

__all__ = [
    "Constraints",
    "extract_constraints",
    "parse_constraints_json",
    "classify_source",
    "filter_eligible",
]
