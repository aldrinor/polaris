"""Instruction understanding — parse buried constraints out of a task prompt.

This package is standalone (no wiring into the driver / generator). It exposes
:func:`extract_constraints`, an adversarial LLM pass that mines a free-text task
prompt for the concrete deliverable constraints an author must honor (source
types, languages, recency, required coverage, exclusions, format, length, tone)
— including rules phrased mid-sentence or as soft asides.

S0 port note
------------
Only the validated rule-reader (``constraint_extractor``) is ported into the
champion tree. The ``source_eligibility`` module (``classify_source`` /
``filter_eligible``) from branch ``round1-if-compiler`` is *deliberately NOT*
ported: it is the compose-time filter of a frozen corpus (the banned 997->131
post-fetch anti-pattern). The rule-reader here is a pure candidate source that
flows into the candidate adapter; it never filters retrieved evidence.
"""

from src.polaris_graph.instruction.constraint_extractor import (
    Constraints,
    extract_constraints,
    extract_constraints_async,
    parse_constraints_json,
)

__all__ = [
    "Constraints",
    "extract_constraints",
    "extract_constraints_async",
    "parse_constraints_json",
]
