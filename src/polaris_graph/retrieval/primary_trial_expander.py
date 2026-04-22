"""M-35 (2026-04-21): primary-trial-name query expansion.

Companion to `regulatory_expander` (M-28). Where M-28 adds
`{question} site:{anchor_host}` queries from a per-domain anchor list,
M-35 adds `"{anchor_trial}" {question}` queries from a per-SLUG anchor
list. Trial names are query-specific (tirzepatide's pivotals differ
from metformin's) so they live per-sweep-slug rather than per-domain.

The Codex DR pass-11 gap #1 on V23: "Replace the citation mix with
primary SURPASS-1..SURPASS-6, SURPASS-CVOT, SURMOUNT-2/4 trial papers
as first-class sources." V23's corpus had 62 rows mentioning those
trial names but mostly conference abstracts and post-hoc pooled
analyses — the NEJM/Lancet primaries for SURPASS-1/2/3 and SURMOUNT-1
were missing. Targeted `"SURPASS-1" {question}` queries surface the
primary trial publication directly.

Design invariants (same discipline as M-28):
  - Zero trial names, zero drug names, zero domain terms in this
    module. All such content lives in YAML templates.
  - Template-driven: the caller chooses the anchors per sweep slug
    by writing them into the template. This module has no baked-in
    knowledge of SURPASS, SURMOUNT, or any other trial name.
  - Backwards-compatible: missing key / empty dict / slug not found
    all return an empty list, so the expander is safe to call
    unconditionally.

Template schema (in `config/scope_templates/{domain}.yaml`):

    per_query_primary_trial_anchors:
      clinical_tirzepatide_t2dm:
        - SURPASS-1
        - SURPASS-2
        - ...

Design:
  - Caller (sweep orchestrator) loads the scope template once and
    calls `expand_primary_trial_queries(question, template, slug)`.
  - Extra queries merge into the amplified list and travel through
    the same scope-validator de-drift + Serper/S2 fanout as every
    other amplified query.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("polaris_graph.primary_trial_expander")


# PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS: soft upper bound on how many
# anchor queries this function will emit from a single slug. Defaults
# to 15 (larger than M-28's 10 because drug-pivotal programs can have
# 6-8 trials). Set to 0 to disable the cap.
_DEFAULT_MAX_ANCHORS = 15


def _max_anchors() -> int:
    """Read the max-anchor cap from env each call (so a test can
    monkey-patch without importing a module-level constant)."""
    raw = os.getenv("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS")
    if raw is None:
        return _DEFAULT_MAX_ANCHORS
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ANCHORS
    return max(0, val)


def _extract_anchors(
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Pull the trial-name anchors for a given sweep `slug` out of a
    loaded scope template.

    Returns an empty list for:
      - missing template
      - missing `per_query_primary_trial_anchors` key
      - malformed (non-dict) value
      - slug not present in the dict
      - empty list for the slug
      - non-list value for the slug

    Trims whitespace, skips non-string entries and empties. Rejects
    entries containing whitespace (a trial name with spaces would
    produce a malformed quoted query).
    """
    if not isinstance(template, dict):
        return []
    if not isinstance(slug, str) or not slug.strip():
        return []
    by_slug = template.get("per_query_primary_trial_anchors")
    if not isinstance(by_slug, dict):
        return []
    raw = by_slug.get(slug)
    if not isinstance(raw, list):
        return []
    anchors: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        # Reject entries containing ANY whitespace (not just literal
        # space — tabs / newlines / vertical-tab / form-feed /
        # carriage-return would all break the outer `"{anchor}"`
        # quoting downstream) or a double quote (ASCII U+0022 would
        # break the outer quoting directly) or a backslash (could
        # survive as `"BAD\" q` and escape-eat the closing quote in
        # some downstream search-query parsers). M-35 pass-2 (Codex
        # blocker): `str.strip()` removes leading/trailing whitespace
        # but NOT interior whitespace, so `"BAD\tENTRY"` would pass
        # the pre-pass-2 `" " in stripped` check. isspace() closes
        # that.
        if (
            not stripped
            or any(ch.isspace() for ch in stripped)
            or '"' in stripped
            or "\\" in stripped
        ):
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


def get_primary_trial_anchors_for_slug(
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """M-42e (2026-04-22): public accessor for the raw anchor list
    for a given sweep slug. Used by the evidence selector to apply
    a T1 primary-paper floor. Same validation rules as `_extract_anchors`
    — returns cleaned, deduplicated anchors or empty list."""
    return _extract_anchors(template, slug)


def expand_primary_trial_queries(
    question: str,
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Return `"{anchor}" {question}` queries for a given sweep slug.

    Args:
        question: the user's research question (or any base query text).
        template: the loaded scope template dict (or None if none set).
        slug: the sweep slug used to key into
            `per_query_primary_trial_anchors`.

    Returns:
        A list of `"{anchor}" {question}` strings, one per configured
        anchor (up to `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS`). Empty
        list when the template has no anchors for this slug, or when
        the question is empty/whitespace.

    This function is pure and deterministic — no network, no state.
    """
    base = (question or "").strip()
    if not base:
        return []
    anchors = _extract_anchors(template, slug)
    if not anchors:
        return []
    cap = _max_anchors()
    if cap > 0 and len(anchors) > cap:
        logger.info(
            "[primary_trial_expander] slug=%r has %d anchors; capped "
            "to %d via PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS",
            slug, len(anchors), cap,
        )
        anchors = anchors[:cap]
    queries = [f'"{anchor}" {base}' for anchor in anchors]
    logger.info(
        "[primary_trial_expander] emitted %d anchor queries for "
        "slug=%r base=%r", len(queries), slug, base[:60],
    )
    return queries
