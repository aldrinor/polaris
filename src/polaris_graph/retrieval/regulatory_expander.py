"""M-28 Fix #1 (2026-04-20): regulatory-anchor query expansion.

DR audit pass 7 head-to-head vs ChatGPT DR + Gemini 3.1 Pro DR exposed
that V17 had ZERO regulatory-agency URLs in its bibliography while both
tier-1 competitors cited FDA labels (accessdata.fda.gov), EMA SmPC
(ema.europa.eu), Health Canada monographs (hres.ca), etc. Codex pass 6
independently flagged this when V13 had to fall back to a Facebook post
for the FDA boxed warning because no FDA source was retrieved.

This module adds a small, generalizable expansion step: when the scope
template for the current domain carries a `regulatory_anchors` list,
emit one extra amplified query per anchor of the form
`{base_question} site:{anchor}`. That makes Serper / S2 hit
authoritative governance sources without any hard-coded agency list
in Python — every domain controls its own anchors in its YAML template.

Generalization constraint (user mandate 2026-04-20): fixes must work
beyond the tirzepatide/T2D clinical query. This module:
  - Has ZERO hard-coded domain or agency names.
  - Returns [] when anchors list is missing or empty (backwards compat).
  - Treats `regulatory_anchors` as an arbitrary list of URL hosts;
    the template author chooses (clinical → FDA/EMA, policy →
    Federal Register, due-diligence → SEC, energy → EPA, etc.).

Design:
  - Caller (run_honest_sweep_r3.py) loads the scope template once and
    calls `expand_regulatory_queries(question, domain)` to get the
    extra queries, merges them into the amplified list.
  - The live retriever does not know about regulatory anchors; the
    extra queries travel through as regular amplified queries and go
    through the same scope-validator de-drift + Serper/S2 fanout.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("polaris_graph.regulatory_expander")


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
        # Reject entries that look like full URLs — the Serper `site:`
        # operator expects a host. "https://fda.gov/path" would produce
        # an invalid query. Keep only host-shaped tokens.
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
        anchor. Empty list when the template has no `regulatory_anchors`
        key, an empty list, or when the question is empty/whitespace.

    This function is pure and deterministic — no network, no state.
    """
    base = (question or "").strip()
    if not base:
        return []
    anchors = _extract_anchors(template)
    if not anchors:
        return []
    queries = [f"{base} site:{anchor}" for anchor in anchors]
    logger.info(
        "[regulatory_expander] emitted %d anchor queries for base=%r",
        len(queries), base[:60],
    )
    return queries
