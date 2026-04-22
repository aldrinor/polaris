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


def _extract_variants(
    template: dict[str, Any] | None,
    slug: str,
) -> dict[str, str]:
    """M-48 (2026-04-22): pull per-anchor first-author + journal variant
    strings for a given sweep slug.

    Schema:
        per_query_primary_trial_variants:
          <slug>:
            <anchor>: <free-text variant>

    Returns an empty dict for:
      - missing template
      - missing `per_query_primary_trial_variants` key
      - malformed (non-dict) value at any level
      - slug not present
      - variant value not a string
      - variant string contains ANY whitespace-only content or is empty

    The variant string is used as-is (wrapped in the outer query with
    the base question appended). Example:
        anchor = "SURPASS-2"
        variant = "Frías NEJM tirzepatide semaglutide"
        emitted query = `"SURPASS-2" Frías NEJM tirzepatide semaglutide {question}`
    """
    if not isinstance(template, dict):
        return {}
    if not isinstance(slug, str) or not slug.strip():
        return {}
    by_slug = template.get("per_query_primary_trial_variants")
    if not isinstance(by_slug, dict):
        return {}
    raw = by_slug.get(slug)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for anchor, variant in raw.items():
        if not isinstance(anchor, str) or not isinstance(variant, str):
            continue
        a = anchor.strip()
        v = variant.strip()
        # Reject anchor with interior whitespace / double quote /
        # backslash (same invariant as _extract_anchors) and reject
        # variant containing a double quote that would break the
        # outer `"{anchor}"` quoting.
        if (
            not a or any(ch.isspace() for ch in a)
            or '"' in a or "\\" in a
        ):
            continue
        if not v or '"' in v:
            continue
        out[a] = v
    return out


def get_trial_population_scope_for_slug(
    template: dict[str, Any] | None,
    slug: str,
) -> dict[str, str]:
    """M-48 (2026-04-22): public accessor for the per-anchor population-
    scope labels.

    Schema:
        per_query_trial_population_scope:
          <slug>:
            <anchor>: "direct" | "indirect_for_t2d" | "indirect"

    Used by `label_rows_with_population_scope` to tag evidence rows
    after retrieval. Missing entry → row stays unlabeled
    (generator treats as "direct" by default).
    """
    if not isinstance(template, dict):
        return {}
    if not isinstance(slug, str) or not slug.strip():
        return {}
    by_slug = template.get("per_query_trial_population_scope")
    if not isinstance(by_slug, dict):
        return {}
    raw = by_slug.get(slug)
    if not isinstance(raw, dict):
        return {}
    valid_labels = {"direct", "indirect_for_t2d", "indirect"}
    out: dict[str, str] = {}
    for anchor, label in raw.items():
        if not isinstance(anchor, str) or not isinstance(label, str):
            continue
        a = anchor.strip()
        l_ = label.strip().lower()
        if not a or any(ch.isspace() for ch in a):
            continue
        if l_ not in valid_labels:
            continue
        out[a] = l_
    return out


def label_rows_with_population_scope(
    rows: list[dict[str, Any]],
    template: dict[str, Any] | None,
    slug: str,
) -> list[dict[str, Any]]:
    """M-48 (2026-04-22): annotate evidence rows with population-scope
    metadata derived from per-anchor labels.

    For each row, scan title for any configured anchor token (case-
    insensitive substring match). If match found, add keys:
      - `population_scope`: one of "direct" / "indirect_for_t2d" /
        "indirect"
      - `indirect_for_t2d`: bool (True iff label == indirect_for_t2d)

    Rows with no anchor match are unchanged. This function mutates
    rows in place AND returns the list (convenience).

    Example usage in the sweep orchestrator, after `retrieval.evidence_rows`
    is populated:

        rows = label_rows_with_population_scope(
            retrieval.evidence_rows, template, slug
        )
    """
    labels = get_trial_population_scope_for_slug(template, slug)
    if not labels or not rows:
        return rows
    # Build case-insensitive lookup: {anchor_lower: (anchor_original, label)}
    lookup = {a.lower(): (a, l_) for a, l_ in labels.items()}
    for row in rows:
        if not isinstance(row, dict):
            continue
        # M-48 pass-2 (Codex blocker): live retriever rows populate
        # `statement` with the candidate title (not `title`). Read
        # from title / statement / source_title in that order so the
        # labeler works on both live rows and fixture rows.
        title = ""
        for key in ("title", "statement", "source_title"):
            v = row.get(key)
            if isinstance(v, str) and v:
                title = v
                break
        title_l = title.lower()
        for anchor_l, (_anchor, label) in lookup.items():
            if anchor_l in title_l:
                row["population_scope"] = label
                row["indirect_for_t2d"] = (label == "indirect_for_t2d")
                row["_m48_anchor_match"] = _anchor
                break
    return rows


def expand_primary_trial_queries(
    question: str,
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Return anchor + variant queries for a given sweep slug.

    For each configured anchor:
      - emits `"{anchor}" {question}` (original M-35 form)
      - IF the anchor has a variant in `per_query_primary_trial_variants`,
        also emits `"{anchor}" {variant} {question}` (M-48 form)

    The variant query carries first-author surname + target journal to
    raise primary-publication landing probability. V27 hit 4/11 primary
    trials with anchor-only queries; M-48 aims for ≥9/11.

    Args:
        question: the user's research question (or any base query text).
        template: the loaded scope template dict (or None if none set).
        slug: the sweep slug used to key into
            `per_query_primary_trial_anchors` and
            `per_query_primary_trial_variants`.

    Returns:
        A list of query strings; order is `[anchor1, anchor1_variant,
        anchor2, anchor2_variant, ...]` for anchors with variants, else
        `[anchor1, anchor2, ...]`. Total capped by
        `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS` applied to the ANCHOR count
        (variants do not count against the cap so that capped runs
        retain their variant queries).

    Pure and deterministic — no network, no state.
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
    variants = _extract_variants(template, slug)
    queries: list[str] = []
    variant_count = 0
    for anchor in anchors:
        queries.append(f'"{anchor}" {base}')
        variant = variants.get(anchor)
        if variant:
            queries.append(f'"{anchor}" {variant} {base}')
            variant_count += 1
    logger.info(
        "[primary_trial_expander] emitted %d queries (%d anchors + "
        "%d variants) for slug=%r base=%r",
        len(queries), len(anchors), variant_count, slug, base[:60],
    )
    return queries
