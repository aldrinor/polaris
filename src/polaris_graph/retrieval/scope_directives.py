"""Design 7 D2 — scope flows into QUERY GENERATION as a STRUCTURED directives block.

Today the FS-Researcher qgen prompts see only the raw question text; the parsed scope (date
window, geography, source types, language, named pins/authors) reaches query wording only
implicitly, via the whole-question scope anchor. This module renders the parsed scope into a
compact, explicit "SCOPE DIRECTIVES" block that is APPENDED to the TOC prompt, the facet-planner
prompt, and the per-todo query-derivation prompt, so the generated queries CARRY the scope
("... randomized trials Europe 2019..2023") instead of hoping the LLM keeps it.

FAIL-OPEN (doc 07 D2): any scope-block build error, or an empty scope, yields "" — the caller
appends nothing and the prompt is byte-identical to today's. Wiring flag ``PG_SCOPE_TO_QGEN``
(default OFF). §-1.3: this only STEERS discovery toward the user's own stated scope; it removes
nothing and it is not a filter.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

from src.polaris_graph.retrieval.scope_intent import ScopeIntent, build_scope_intent

logger = logging.getLogger("polaris_graph.scope_directives")

# The marker line the block always opens with — the qgen harness / self-test asserts its presence,
# and a monitor can grep it to confirm the D2 lane fired (structural, §-1.3).
SCOPE_DIRECTIVES_HEADER = "SCOPE DIRECTIVES (constrain every generated query to ALL of these):"


def scope_to_qgen_enabled() -> bool:
    """True iff scope directives should be woven into the qgen prompts (default OFF => today's)."""
    return os.getenv("PG_SCOPE_TO_QGEN", "0").strip() in ("1", "true", "True")


def _coerce_intent(scope: Union[ScopeIntent, dict, None]) -> Optional[ScopeIntent]:
    """Accept a ready ScopeIntent, a protocol-shaped scope dict, or the two raw blocks."""
    if scope is None:
        return None
    if isinstance(scope, ScopeIntent):
        return scope
    if isinstance(scope, dict):
        # A protocol slice {'user_constraints':..., 'scope_constraints':...} or the raw blocks.
        if "user_constraints" in scope or "scope_constraints" in scope:
            return build_scope_intent(scope.get("user_constraints"), scope.get("scope_constraints"))
        # Already a flat ScopeIntent-shaped dict.
        return build_scope_intent(scope, scope)
    return None


def build_scope_directives_block(scope: Union[ScopeIntent, dict, None]) -> str:
    """Render the SCOPE DIRECTIVES text block from parsed scope. Returns "" when scope is empty
    or when the flag is OFF (fail-open, byte-identical prompts). Never raises."""
    if not scope_to_qgen_enabled():
        return ""
    try:
        intent = _coerce_intent(scope)
        if intent is None or intent.is_empty():
            return ""

        lines: list[str] = []
        # Date window.
        if intent.date_start_iso or intent.date_end_iso:
            lo = intent.date_start_iso or "(no floor)"
            hi = intent.date_end_iso or "(no ceiling)"
            lines.append(f"- Publication window: {lo} to {hi}. Prefer sources inside it.")
        # Geography / jurisdiction.
        if intent.geographies:
            geos = ", ".join(g.upper() for g in intent.geographies)
            lines.append(f"- Geography / jurisdiction: {geos}. Favor sources from these regions.")
        # Language.
        if intent.language:
            lines.append(f"- Language: {intent.language}. Include native-language queries where relevant.")
        # Source types / peer-review.
        if intent.peer_reviewed_only:
            lines.append("- Source type: peer-reviewed journal articles preferred.")
        other_types = [t for t in intent.source_types if t != "peer_reviewed_journal"]
        if other_types:
            pretty = ", ".join(t.replace("_", " ") for t in other_types)
            lines.append(f"- Source type: {pretty}.")
        # Named sources / authors.
        if intent.authors:
            lines.append(f"- Named authors/sources to target: {', '.join(intent.authors)}.")
        extra_named = [n for n in intent.named_includes if n not in intent.authors]
        if extra_named:
            lines.append(f"- Named sources to include: {', '.join(extra_named)}.")

        if not lines:
            return ""
        return SCOPE_DIRECTIVES_HEADER + "\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001 — fail-open: a render fault => no block, today's prompt
        logger.debug("[scope_directives] block build fell open (empty block)", exc_info=True)
        return ""


def append_scope_directives(prompt: str, scope: Union[ScopeIntent, dict, None]) -> str:
    """Append the SCOPE DIRECTIVES block to a qgen prompt (no-op when empty/flag-OFF)."""
    block = build_scope_directives_block(scope)
    if not block:
        return prompt
    return prompt + "\n\n" + block
