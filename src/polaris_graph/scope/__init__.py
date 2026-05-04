"""Scope — clinical question scope discovery + ambiguity detection.

Slice 001 introduces the schemas + types that downstream modules
(clinical_classifier, ambiguity_detector_clinical) populate. The schemas
match the golden test expected_scope_decision shape exactly so CI can
deep-equal compare.

Module layout:
    scope_decision.py        # schemas + assembly helpers (this PR)
    clinical_classifier.py   # PR 3 + 4 (regex + LLM fallback)
    ambiguity_detector_clinical.py  # PR 5
    patterns/                # YAML data files for regex (PR 3)
"""

from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    AmbiguityAxes,
    PicoAxis,
    ScopeClass,
    ScopeClassValue,
    ScopeDecision,
    ScopeStatus,
    assemble_scope_decision,
)

__all__ = [
    "AmbiguityAxis",
    "AmbiguityAxes",
    "PicoAxis",
    "ScopeClass",
    "ScopeClassValue",
    "ScopeDecision",
    "ScopeStatus",
    "assemble_scope_decision",
]
