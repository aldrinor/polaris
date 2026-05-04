"""Scope — clinical question scope discovery + ambiguity detection."""

from polaris_graph.scope.clinical_classifier import (
    classify,
    llm_fallback_classify,
    regex_classify,
    RegexClassifyResult,
)
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
    "RegexClassifyResult",
    "ScopeClass",
    "ScopeClassValue",
    "ScopeDecision",
    "ScopeStatus",
    "assemble_scope_decision",
    "classify",
    "llm_fallback_classify",
    "regex_classify",
]
