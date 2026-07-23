"""Semantic coverage obligations carried from prompt constraints to report assembly."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping, Sequence

from src.polaris_graph.settings import resolve

_OFF = frozenset({"", "0", "false", "no", "off", "disabled"})
_ROLES = ("frame", "mechanism", "cross-context comparison", "synthesis", "implication")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class CoverageObligation:
    concept: str
    role: str
    comparative: bool = False


def enabled() -> bool:
    return (resolve("PG_COVERAGE_OBLIGATIONS") or "").strip().lower() not in _OFF


def _role_for(concept: str, position: int) -> str:
    text = concept.lower()
    if re.search(r"\b(various|across|between|different|multiple)\b", text):
        return "cross-context comparison"
    if re.search(r"\b(mechanism|how|why|driver|pathway|process)\b", text):
        return "mechanism"
    if re.search(r"\b(frame|context|era|revolution|paradigm)\b", text):
        return "frame"
    if re.search(r"\b(implication|recommendation|policy|future|consequence)\b", text):
        return "implication"
    if re.search(r"\b(overall|synthesis|integrat|conclusion)\b", text):
        return "synthesis"
    return _ROLES[position % len(_ROLES)]


def build_obligations(required_coverage: Sequence[str] | None) -> list[CoverageObligation]:
    obligations: list[CoverageObligation] = []
    seen: set[str] = set()
    for position, raw in enumerate(required_coverage or []):
        concept = " ".join(str(raw).split()).strip()
        key = concept.casefold()
        if not concept or key in seen:
            continue
        seen.add(key)
        role = _role_for(concept, position)
        obligations.append(CoverageObligation(
            concept=concept,
            role=role,
            comparative=(role == "cross-context comparison"),
        ))
    return obligations


def thread_obligations(plans: Sequence[Any], obligations: Sequence[CoverageObligation]) -> None:
    """Attach each obligation to an outline focus and repeat the full spine in the conclusion."""
    if not enabled() or not plans or not obligations:
        return
    for position, obligation in enumerate(obligations):
        plan = plans[position % len(plans)]
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
    bodies = [str(getattr(section, "verified_text", "") or "") for section in sections]
    joined = " ".join(bodies).casefold()
    missing: list[dict[str, Any]] = []
    fulfilled: list[dict[str, Any]] = []
    for obligation in obligations:
        tokens = [token.casefold() for token in _WORD_RE.findall(obligation.concept)]
        present = bool(tokens) and all(token in joined for token in tokens)
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


def required_coverage_from(constraints: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(constraints, Mapping):
        return []
    return [str(item) for item in constraints.get("required_coverage", []) if str(item).strip()]
