"""I-decompose-001 — Multi-question decomposition (Path G).

Decomposes a complex research question into N coherent sub-questions
that each can be answered independently, then surfaces them for the
retrieval + generator pipeline to handle separately. The final
synthesis layer aggregates the per-sub-question verified prose into
a single answer to the parent question.

Design rationale (Codex strategic-review path G):
- Single complex questions like "How do tirzepatide and semaglutide
  compare in T2DM, considering efficacy, safety, cost, and
  availability?" stress the verifier because each clause has a
  different evidence-pool / sub-claim structure.
- Decomposing into:
    1. tirzepatide vs semaglutide efficacy in T2DM
    2. tirzepatide vs semaglutide safety in T2DM
    3. tirzepatide vs semaglutide cost in T2DM
    4. tirzepatide vs semaglutide availability in T2DM
  lets each sub-question retrieve a focused evidence pool and produces
  per-sub-claim verified spans before the synthesis aggregates.

This module provides the DECOMPOSER (sync helper that produces N
sub-questions). Retrieval orchestration and synthesis aggregation
are concerns of the caller (downstream issues will wire this into
graph_v4).

NOT in scope for I-decompose-001:
- Retrieval orchestration across N sub-questions (separate concern)
- Synthesis aggregation logic (separate concern)
- Live LLM-driven decomposition (this iter ships a heuristic
  decomposer; an LLM-driven version is a separate follow-up that
  would invoke openrouter_client)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Common conjunctive markers that indicate a complex multi-aspect
# question. The decomposer splits on these only when paired with
# indicator words ("considering", "including", "across", "comparing"
# multi-aspect framing).
_ASPECT_MARKERS = (
    "considering",
    "including",
    "with respect to",
    "across",
    "in terms of",
    "regarding",
)

_ASPECT_LIST_RE = re.compile(
    r"\b(?:" + "|".join(_ASPECT_MARKERS) + r")\b\s+(.+)$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class DecomposedQuestion:
    """A single sub-question + provenance back to the parent."""

    parent_question: str
    sub_question: str
    aspect: str  # "efficacy", "safety", "cost", etc.
    index: int  # 0..N-1
    total: int  # N


def decompose(question: str, *, max_sub: int = 6) -> list[DecomposedQuestion]:
    """Decompose `question` into 1..max_sub coherent sub-questions.

    Heuristic: looks for an "aspect-list" tail (`considering A, B, C, D`)
    and splits the list into per-aspect sub-questions. Falls back to
    returning the original question as a single 1-of-1 element if no
    aspect markers found.

    Cap at max_sub to bound retrieval cost. If the parsed list has
    more than max_sub aspects, the last entry becomes "and others"
    and the list is truncated.
    """
    question = (question or "").strip()
    if not question:
        return []

    aspects = _extract_aspect_list(question)
    if not aspects:
        # No decomposition; original question passes through as 1-of-1
        return [DecomposedQuestion(
            parent_question=question,
            sub_question=question,
            aspect="full",
            index=0,
            total=1,
        )]

    base = _strip_aspect_clause(question)
    if len(aspects) > max_sub:
        # Cap to max_sub-1 + "others" bucket
        kept = aspects[: max_sub - 1]
        kept.append("other considerations")
        aspects = kept

    return [
        DecomposedQuestion(
            parent_question=question,
            sub_question=_format_sub_question(base, aspect),
            aspect=aspect,
            index=i,
            total=len(aspects),
        )
        for i, aspect in enumerate(aspects)
    ]


def _extract_aspect_list(question: str) -> list[str]:
    """Return parsed aspect list or empty list if not multi-aspect."""
    match = _ASPECT_LIST_RE.search(question)
    if not match:
        return []
    tail = match.group(1).strip().rstrip("?.").strip()
    # Tail might be "efficacy, safety, cost, and availability"
    # Split on commas + final "and"; normalize.
    pieces = re.split(r",\s*(?:and\s+)?|\s+and\s+", tail)
    aspects = [p.strip().lower().rstrip(".") for p in pieces if p.strip()]
    # Filter junk (single-char artifacts, etc.)
    aspects = [a for a in aspects if len(a) >= 3]
    return aspects


def _strip_aspect_clause(question: str) -> str:
    """Remove the trailing aspect-list clause from the question."""
    return _ASPECT_LIST_RE.sub("", question).strip().rstrip(",").rstrip()


def _format_sub_question(base: str, aspect: str) -> str:
    """Compose a per-aspect sub-question from base + aspect label."""
    base = base.rstrip("?.").strip()
    if aspect == "other considerations":
        return f"{base} — other considerations not covered above?"
    return f"{base} — {aspect}?"
