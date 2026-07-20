"""M-28 Fix #1 (2026-04-20): authoritative-source query expansion.

Generalizable abstraction: scope templates carry an optional list of
host-shaped strings under `regulatory_anchors`. When present, the
expander emits one extra amplified query per anchor of the form
`{base_question} site:{anchor}`. When absent / empty / malformed,
the expander returns an empty list. The template is the ONLY place
the host list lives; this module has no baked-in host knowledge and
no baked-in query-domain knowledge. It treats anchors as opaque
host-shaped tokens.

Design invariants:
  - Zero host names, zero domain names, zero jurisdictional terms
    anywhere in this module. All such content lives in YAML templates
    and in test fixtures. A repository-level test
    (`test_m28_regulatory_expander_no_hardcoded_hosts`) asserts this
    at CI time so future edits cannot slip in a hard-code by accident.
  - Template-driven: the caller chooses the anchors per domain by
    writing them into the template. Every domain supported by the
    scope_templates/ directory uses the same expander code.
  - Backwards-compatible: missing list / empty list / malformed
    entries all return an empty list, so the expander is safe to call
    unconditionally.

Design:
  - Caller (sweep orchestrator) loads the scope template once and
    calls `expand_regulatory_queries(question, template)` to get the
    extra queries, merges them into the amplified list.
  - The live retriever does not know about the anchor concept; the
    extra queries travel through as regular amplified queries and go
    through the same scope-validator de-drift + Serper/S2 fanout.
"""
from __future__ import annotations

import logging
import os
from typing import Any
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.regulatory_expander")


# PG_SWEEP_MAX_REGULATORY_ANCHORS: soft upper bound on how many anchor
# queries this function will emit from a single template. A template
# with more anchors still loads fine; the expander just truncates
# emission to the cap. Set to 0 to disable the cap.
#
# M-43 (2026-04-22): raised default 10 -> 12 after a prior retrieval
# sweep silently truncated the final anchor in an 11-entry template,
# dropping downstream bibliography coverage to zero for that
# jurisdiction. 12 fits the current template with one future-addition
# headroom. Extra retrieval cost per run: ~2 queries, negligible.
_DEFAULT_MAX_ANCHORS = 12


def _max_anchors() -> int:
    """Read the max-anchor cap from env each call (so a test can monkey-
    patch without importing a module-level constant)."""
    raw = resolve("PG_SWEEP_MAX_REGULATORY_ANCHORS")
    if raw is None:
        return _DEFAULT_MAX_ANCHORS
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ANCHORS
    return max(0, val)


def _extract_anchors(template: dict[str, Any] | None) -> list[str]:
    """Pull the `regulatory_anchors` list from a loaded scope template.

    Returns an empty list for missing / malformed / empty configuration.
    Trims whitespace, skips non-string entries and empties.
    """
    if not isinstance(template, dict):
        return []
    raw = template.get("regulatory_anchors")
    if not isinstance(raw, list):
        return []
    anchors: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip().lower()
        # Reject entries that look like full URLs — the `site:` search
        # operator expects a host. A full URL with a path would produce
        # an invalid query. Keep only host-shaped tokens. Also reject
        # entries containing whitespace.
        if not stripped or "/" in stripped or " " in stripped:
            continue
        anchors.append(stripped)
    # Deduplicate while preserving declared order.
    seen: set[str] = set()
    unique: list[str] = []
    for a in anchors:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


def expand_regulatory_queries(
    question: str,
    template: dict[str, Any] | None,
) -> list[str]:
    """Return `site:{anchor}` queries derived from the scope template.

    Args:
        question: the user's research question (or any base query text).
        template: the loaded scope template dict (or None if none set).

    Returns:
        A list of `{question} site:{anchor}` strings, one per configured
        anchor (up to `PG_SWEEP_MAX_REGULATORY_ANCHORS` entries). Empty
        list when the template has no `regulatory_anchors` key, an
        empty list, or when the question is empty/whitespace.

    This function is pure and deterministic — no network, no state.
    """
    base = (question or "").strip()
    if not base:
        return []
    anchors = _extract_anchors(template)
    if not anchors:
        return []
    cap = _max_anchors()
    if cap > 0 and len(anchors) > cap:
        logger.info(
            "[regulatory_expander] template has %d anchors; capped to %d "
            "via PG_SWEEP_MAX_REGULATORY_ANCHORS",
            len(anchors), cap,
        )
        anchors = anchors[:cap]
    queries = [f"{base} site:{anchor}" for anchor in anchors]
    logger.info(
        "[regulatory_expander] emitted %d anchor queries for base=%r",
        len(queries), base[:60],
    )
    return queries
