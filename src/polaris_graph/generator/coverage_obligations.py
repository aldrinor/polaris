"""Semantic coverage obligations carried from prompt constraints to report assembly."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Callable, Mapping, Sequence

from src.polaris_graph.settings import resolve

_OFF = frozenset({"", "0", "false", "no", "off", "disabled"})
@dataclass
class CoverageObligation:
    concept: str
    role: str
    comparative: bool = False
    bound_section: str = ""
    binding_method: str = ""


def enabled() -> bool:
    return (resolve("PG_COVERAGE_OBLIGATIONS") or "").strip().lower() not in _OFF


def build_obligations(
    required_coverage: Sequence[str | Mapping[str, Any]] | None,
) -> list[CoverageObligation]:
    """Build obligations from semantic extractor output without language regexes."""
    obligations: list[CoverageObligation] = []
    seen: set[str] = set()
    for raw in required_coverage or []:
        if isinstance(raw, Mapping):
            concept = " ".join(str(raw.get("concept") or "").split()).strip()
            role = " ".join(str(raw.get("role") or "coverage").split()).strip()
            comparative = bool(raw.get("comparative", False))
        else:
            concept = " ".join(str(raw).split()).strip()
            role = "coverage"
            comparative = False
        key = concept.casefold()
        if not concept or key in seen:
            continue
        seen.add(key)
        obligations.append(CoverageObligation(
            concept=concept,
            role=role or "coverage",
            comparative=comparative,
        ))
    return obligations


def _character_ngrams(text: str) -> set[str]:
    normalized = " ".join(text.casefold().split())
    return {
        normalized[index:index + 3]
        for index in range(max(0, len(normalized) - 2))
        if not normalized[index:index + 3].isspace()
    }


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _obligation_targets(
    plans: Sequence[Any],
    obligations: Sequence[CoverageObligation],
    embedding_fn: Callable[[list[str]], Sequence[Sequence[float]]] | None,
) -> tuple[list[Any], str]:
    plan_texts = [
        f"{getattr(plan, 'title', '')}. {getattr(plan, 'focus', '')}"
        for plan in plans
    ]
    concepts = [obligation.concept for obligation in obligations]
    if embedding_fn is not None:
        vectors = list(embedding_fn([*concepts, *plan_texts]))
        if len(vectors) != len(concepts) + len(plan_texts):
            raise ValueError("coverage obligation embedding count mismatch")
        concept_vectors = vectors[:len(concepts)]
        plan_vectors = vectors[len(concepts):]
        return [
            plans[max(
                range(len(plans)),
                key=lambda index: _cosine(concept_vector, plan_vectors[index]),
            )]
            for concept_vector in concept_vectors
        ], "embedding"

    # Dependency-free multilingual fallback: Unicode character n-gram affinity.
    # The binding method is surfaced in telemetry rather than silently claiming
    # semantic-model matching.
    plan_grams = [_character_ngrams(text) for text in plan_texts]
    return [
        plans[max(
            range(len(plans)),
            key=lambda index: len(_character_ngrams(concept) & plan_grams[index]),
        )]
        for concept in concepts
    ], "unicode_ngram"


def thread_obligations(
    plans: Sequence[Any],
    obligations: Sequence[CoverageObligation],
    *,
    embedding_fn: Callable[[list[str]], Sequence[Sequence[float]]] | None = None,
) -> None:
    """Attach each obligation to its closest section and carry its binding."""
    if not enabled() or not plans or not obligations:
        return
    targets, binding_method = _obligation_targets(plans, obligations, embedding_fn)
    for obligation, plan in zip(obligations, targets):
        obligation.bound_section = str(getattr(plan, "title", "") or "")
        obligation.binding_method = binding_method
        direction = (
            "make at least one explicit comparison across contexts (regions, industries, populations, or periods)"
            if obligation.comparative else f"treat it analytically as a {obligation.role}"
        )
        plan.focus = (
            f"{plan.focus.rstrip()} Coverage obligation: connect {obligation.concept!r} to the cited "
            f"evidence and {direction}."
        )
    conclusion = next(
        (plan for plan in reversed(plans) if re.search(r"conclu|synth|implication", plan.title, re.I)),
        plans[-1],
    )
    spine = "; ".join(f"{item.concept} ({item.role})" for item in obligations)
    conclusion.focus = (
        f"{conclusion.focus.rstrip()} In the closing synthesis, reconnect the supported findings to "
        f"these prompt obligations: {spine}."
    )


def audit_fulfillment(
    obligations: Sequence[CoverageObligation],
    sections: Sequence[Any],
) -> dict[str, Any]:
    sections_by_title = {
        str(getattr(section, "title", "") or ""): section
        for section in sections
    }
    missing: list[dict[str, Any]] = []
    fulfilled: list[dict[str, Any]] = []
    for obligation in obligations:
        section = sections_by_title.get(obligation.bound_section)
        present = bool(
            section is not None
            and str(getattr(section, "verified_text", "") or "").strip()
            and not bool(getattr(section, "dropped_due_to_failure", False))
        )
        record = asdict(obligation)
        (fulfilled if present else missing).append(record)
    return {"fulfilled": fulfilled, "missing": missing}


def render_sections_preserving_outline(
    outline: Sequence[Any],
    sections: Sequence[Any],
) -> tuple[list[str], list[str]]:
    """Render generated sections unchanged and report missing planned sections as telemetry."""
    remaining = list(sections)
    rendered: list[str] = []
    disclosed: list[str] = []
    for plan in outline:
        match = next((section for section in remaining if section.title == plan.title), None)
        if match is not None:
            remaining.remove(match)
        if match is not None and not match.dropped_due_to_failure and match.verified_text:
            rendered.append(f"## {match.title}\n\n{match.verified_text}")
            continue
        disclosed.append(str(getattr(plan, "title", "") or "Planned section"))
    for section in remaining:
        if not section.dropped_due_to_failure and section.verified_text:
            rendered.append(f"## {section.title}\n\n{section.verified_text}")
    return rendered, disclosed


def required_coverage_from(
    constraints: Mapping[str, Any] | None,
) -> list[str | Mapping[str, Any]]:
    if not isinstance(constraints, Mapping):
        return []
    roles = {
        str(item.get("concept") or "").casefold(): item
        for item in (constraints.get("coverage_roles") or [])
        if isinstance(item, Mapping) and str(item.get("concept") or "").strip()
    }
    output: list[str | Mapping[str, Any]] = []
    for item in constraints.get("required_coverage", []):
        concept = " ".join(str(item).split()).strip()
        if not concept:
            continue
        output.append(roles.get(concept.casefold(), concept))
    return output
