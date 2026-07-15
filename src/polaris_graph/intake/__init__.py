"""Intake — user-question entry point for the research pipeline.

Slice 001 introduces:
    - question_normalizer: deterministic pre-processing of raw user input

Subsequent slices add scope/, retrieval/ etc. The intake module owns the
boundary between "raw user typing" and "normalized question that the rest
of the pipeline can reason about."
"""

# feat/intake-contract (2026-07-15): relative import so the package resolves under
# BOTH the `src.polaris_graph.intake.*` and `polaris_graph.intake.*` prefixes
# (the prior absolute `polaris_graph.intake...` import required `src` on sys.path
# and left the package un-importable via the `src.` prefix every other subpackage
# uses). Behavior-preserving: identical symbols are re-exported.
from .question_normalizer import (
    NormalizedQuestion,
    QuestionTooLong,
    QuestionTooShort,
    normalize,
)

__all__ = [
    "NormalizedQuestion",
    "QuestionTooLong",
    "QuestionTooShort",
    "normalize",
]
