"""Intake orchestrator — wires the front half of the research pipeline end-to-end.

Per slice 001 architecture proposal §"Implementation order PR 6". The
function process_intake() is the single entry point that transforms a
raw user-typed string into a ScopeDecision ready for the UI.

Pipeline (deterministic order):

    raw_question (str)
        ↓
    question_normalizer.normalize()
        ↓ NormalizedQuestion (NFC + whitespace + control-stripped + length-bounded)
        ↓
    clinical_classifier.classify()
        ↓ RegexClassifyResult (refused | clinical_* | out_of_scope | uncertain)
        ↓
    [if refused] → assemble_scope_decision(refused=True)
    [if out_of_scope] → assemble_scope_decision(scope_class=out_of_scope, ambiguity=None)
    [if clinical_*]:
        ambiguity_detector_clinical.detect_ambiguity()
            ↓ AmbiguityAxes
            ↓
        assemble_scope_decision(scope_class=..., ambiguity=...)
        ↓
    ScopeDecision

Latency is measured wall-clock (intake → decision) and threaded into
ScopeDecision.latency_ms.

Errors during normalization (QuestionTooShort, QuestionTooLong) are
surfaced as IntakeError with a structured reason so the UI can show
helpful guidance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from polaris_graph.intake.question_normalizer import (
    QuestionTooLong,
    QuestionTooShort,
    normalize,
)
from polaris_graph.scope.ambiguity_detector_clinical import detect_ambiguity
from polaris_graph.scope.clinical_classifier import classify
from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    AmbiguityAxes,
    ScopeDecision,
    assemble_scope_decision,
)


@dataclass(frozen=True)
class IntakeError:
    """Surfaced when the question cannot be processed (e.g., too short/long).

    Not the same as out_of_scope or refused — those are valid ScopeDecisions.
    IntakeError indicates the question never reached the classifier.
    """

    code: str  # 'too_short' | 'too_long' | 'invalid_input'
    message: str  # human-readable for UI
    raw: str  # original user input


def _empty_axes() -> AmbiguityAxes:
    """Default AmbiguityAxes used for refused / out_of_scope paths
    (downstream UI doesn't render the modal in those cases)."""
    blank = AmbiguityAxis(
        axis="population",
        plausible_interpretations=["n/a"],
        needs_clarification=False,
    )
    return AmbiguityAxes(
        population=AmbiguityAxis(
            axis="population", plausible_interpretations=["n/a"], needs_clarification=False
        ),
        intervention=AmbiguityAxis(
            axis="intervention", plausible_interpretations=["n/a"], needs_clarification=False
        ),
        outcome=AmbiguityAxis(
            axis="outcome", plausible_interpretations=["n/a"], needs_clarification=False
        ),
        is_ambiguous=False,
    )


def process_intake(
    raw_question: str,
    *,
    completion_fn: Callable[[str], str] | None = None,
) -> ScopeDecision | IntakeError:
    """Orchestrate the front-half ambiguity-detection pipeline.

    Args:
        raw_question: user-typed input, any string. Will be normalized.
        completion_fn: optional dependency-injectable LLM call for the
                       classifier's LLM fallback layer. Tests pass mocks;
                       production uses the default OpenRouter client.

    Returns:
        ScopeDecision on success (any status: in_scope / out_of_scope /
        ambiguous_needs_clarification / refused).
        IntakeError if the question is malformed (too short, too long,
        or non-string).
    """
    t_start = time.perf_counter()

    # Step 1: normalize
    try:
        normalized = normalize(raw_question)
    except QuestionTooShort:
        return IntakeError(
            code="too_short",
            message="Please enter a longer question (at least 3 characters).",
            raw=raw_question if isinstance(raw_question, str) else "",
        )
    except QuestionTooLong:
        return IntakeError(
            code="too_long",
            message="Question is too long. Please shorten to at most 1000 characters.",
            raw=raw_question if isinstance(raw_question, str) else "",
        )
    except TypeError:
        return IntakeError(
            code="invalid_input",
            message="Question must be a text string.",
            raw=str(raw_question)[:200] if raw_question is not None else "",
        )

    # Step 1.5: I-ready-007 (#1072) input harm-refusal — BEFORE the scope classifier, flag-gated
    # (PG_USE_SAFETY_REFUSAL default OFF -> skipped -> byte-identical). High-precision (explicit harm-
    # intent only, never bare clinical/policy subject) so legitimate research is not over-refused;
    # fails open. Reuses the existing refused-ScopeDecision shape the UI already renders.
    import os as _os

    if _os.getenv("PG_USE_SAFETY_REFUSAL", "0").strip() in ("1", "true", "True"):
        from polaris_graph.nodes.safety_classifier import classify_harm_intent

        _harm = classify_harm_intent(normalized.normalized)
        if _harm.harmful:
            latency = int((time.perf_counter() - t_start) * 1000)
            return assemble_scope_decision(
                scope_class=None,
                ambiguity=None,
                refused=True,
                refusal_reason=f"harm_intent:{_harm.category}",
                latency_ms=latency,
            )

    # Step 2: classify (regex layer + LLM fallback if uncertain)
    classifier_result = classify(
        normalized.normalized,
        completion_fn=completion_fn,
    )

    # Step 3: refused short-circuit
    if classifier_result.refused:
        latency = int((time.perf_counter() - t_start) * 1000)
        return assemble_scope_decision(
            scope_class=None,
            ambiguity=None,
            refused=True,
            refusal_reason="instruction_override_attempt",
            latency_ms=latency,
        )

    # Step 4: out_of_scope path (no ambiguity detection needed)
    if classifier_result.scope_class.value == "out_of_scope":
        latency = int((time.perf_counter() - t_start) * 1000)
        return assemble_scope_decision(
            scope_class=classifier_result.scope_class,
            ambiguity=None,
            latency_ms=latency,
        )

    # Step 5: uncertain after both regex + LLM — surface as out_of_scope
    # rather than guessing. UI shows the standard out-of-scope message.
    if classifier_result.scope_class.value == "uncertain":
        latency = int((time.perf_counter() - t_start) * 1000)
        # Treat uncertain as out_of_scope for slice 1 (graceful fallback —
        # don't pretend to handle questions we couldn't classify)
        from polaris_graph.scope.scope_decision import ScopeClass

        oos_class = ScopeClass(
            value="out_of_scope",
            confidence=classifier_result.scope_class.confidence,
            provenance=classifier_result.scope_class.provenance,
            matched_pattern=None,
        )
        return assemble_scope_decision(
            scope_class=oos_class,
            ambiguity=None,
            latency_ms=latency,
        )

    # Step 6: clinical_* — run ambiguity detection
    axes = detect_ambiguity(normalized.normalized)
    latency = int((time.perf_counter() - t_start) * 1000)
    return assemble_scope_decision(
        scope_class=classifier_result.scope_class,
        ambiguity=axes,
        latency_ms=latency,
    )
