"""Out-of-scope refusal handling for follow-up runs (I-f11-004).

Heuristic: a follow-up is out-of-scope when zero of its tokens
(case-insensitive, punctuation-stripped) appear in the parent
template's `_`-separated keyword list. MVP debt: single-token templates
over-refuse; LLM-augmented intent matching is post-MVP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from polaris_graph.followup.agent import (
    ComposedQuery,
    FollowUpAgent,
    ParentRunContext,
)


_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class RefusalDecision:
    is_refused: bool
    reason: str | None
    template_keywords: list[str]
    question_overlap: list[str]


def detect_out_of_scope(
    parent_template: str, follow_up: str, *, min_overlap: int = 1
) -> RefusalDecision:
    keywords = [t for t in parent_template.lower().split("_") if t]
    if parent_template == "general":
        return RefusalDecision(False, None, keywords, [])
    words = _PUNCT_RE.sub(" ", follow_up.lower()).split()
    kw_set = set(keywords)
    overlap = [w for w in words if w in kw_set]
    if len(overlap) < min_overlap:
        reason = (
            f"follow-up has {len(overlap)} shared keyword(s) with parent "
            f"template '{parent_template}' (need >= {min_overlap}); out-of-scope"
        )
        return RefusalDecision(True, reason, keywords, overlap)
    return RefusalDecision(False, None, keywords, overlap)


def compose_or_refuse(
    agent: FollowUpAgent, parent: ParentRunContext, follow_up: str
) -> ComposedQuery | RefusalDecision:
    decision = detect_out_of_scope(parent.template, follow_up)
    if decision.is_refused:
        return decision
    return agent.compose(parent, follow_up)
