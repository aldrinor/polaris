"""Follow-up agent — preserves parent-run context (I-f11-001).

Pure deterministic substrate: no LLM call. LLM-augmented follow-up
disambiguation is follow-up I-f11-002.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParentRunContext:
    """Snapshot of the parent run that a follow-up will inherit from."""

    parent_run_id: str
    template: str
    parent_question: str
    known_evidence_ids: list[str] = field(default_factory=list)
    parent_summary: str | None = None


@dataclass(frozen=True)
class ComposedQuery:
    """A follow-up question composed with parent-run context."""

    effective_question: str
    inherited_template: str
    parent_run_id: str
    inherited_evidence_ids: list[str]


def _dedup_preserve_order(items: list[str]) -> list[str]:
    """Return a fresh list with duplicates removed, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class FollowUpAgent:
    """Compose a follow-up question with parent-run context preserved."""

    def compose(
        self, parent: ParentRunContext, follow_up: str
    ) -> ComposedQuery:
        if not follow_up or not follow_up.strip():
            raise ValueError("follow_up question must be non-blank")
        effective = (
            f"Follow-up to '{parent.parent_question}': {follow_up.strip()}"
        )
        inherited = _dedup_preserve_order(parent.known_evidence_ids)
        return ComposedQuery(
            effective_question=effective,
            inherited_template=parent.template,
            parent_run_id=parent.parent_run_id,
            inherited_evidence_ids=inherited,
        )
