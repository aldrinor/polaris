"""Intake — user-question entry point for the BPEI spine.

Slice 001 introduces:
    - question_normalizer: deterministic pre-processing of raw user input

Subsequent slices add scope/, retrieval/ etc. The intake module owns the
boundary between "raw user typing" and "normalized question that the rest
of the pipeline can reason about."
"""

from polaris_graph.intake.question_normalizer import (
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
