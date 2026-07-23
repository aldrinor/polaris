"""Template-driven primary-source identifier expansion.

The module has no knowledge of topics, study programs, venues, or entity
types.  A scope template supplies identifiers, optional query variants,
direct locators, and relevance labels.  Legacy public names and template
keys remain as compatibility aliases for existing callers.
"""
from __future__ import annotations

import logging
from typing import Any

from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.primary_source_expander")

_CANONICAL_KEYS = {
    "anchors": "per_query_primary_source_anchors",
    "dois": "per_query_primary_source_dois",
    "variants": "per_query_primary_source_variants",
    "scope": "per_query_primary_source_scope",
}
_LEGACY_KEYS = {
    "anchors": "per_query_primary_trial_anchors",
    "dois": "per_query_primary_trial_dois",
    "variants": "per_query_primary_trial_variants",
    "scope": "per_query_trial_population_scope",
}


def _max_anchors() -> int:
    """Return an optional configuration-owned bound; zero means unbounded."""

    raw = resolve("PG_SWEEP_MAX_PRIMARY_SOURCE_ANCHORS")
    if raw is None or not str(raw).strip():
        # Compatibility fallback for existing deployments.
        raw = resolve("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS")
    if raw is None or not str(raw).strip():
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _scoped_value(
    template: dict[str, Any] | None,
    slug: str,
    kind: str,
) -> Any:
    """Read a slug-scoped value, preferring the canonical schema key."""

    if not isinstance(template, dict) or not isinstance(slug, str) or not slug.strip():
        return None
    for key in (_CANONICAL_KEYS[kind], _LEGACY_KEYS[kind]):
        by_slug = template.get(key)
        if isinstance(by_slug, dict) and slug in by_slug:
            return by_slug.get(slug)
    return None


def _valid_anchor(value: Any) -> str:
    """Return a safely quotable identifier, or an empty string."""

    if not isinstance(value, str):
        return ""
    anchor = value.strip()
    if (
        not anchor
        or any(
            char in ('"', "\\") or ord(char) < 32 or ord(char) == 127
            for char in anchor
        )
    ):
        return ""
    return anchor


def _extract_anchors(
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    raw = _scoped_value(template, slug, "anchors")
    if not isinstance(raw, list):
        return []
    anchors: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        anchor = _valid_anchor(entry)
        if anchor and anchor not in seen:
            seen.add(anchor)
            anchors.append(anchor)
    return anchors


def _is_valid_doi(value: str) -> bool:
    """Validate the structural DOI form without a venue allow-list."""

    if not value.startswith("10.") or "/" not in value:
        return False
    prefix, _, suffix = value.partition("/")
    registrant = prefix.removeprefix("10.")
    return (
        registrant.isdigit()
        and 4 <= len(registrant) <= 9
        and bool(suffix)
        and not any(char.isspace() for char in value)
        and '"' not in value
        and "\\" not in value
    )


def expand_primary_source_dois(
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Return configured direct DOI locators for one query scope."""

    raw = _scoped_value(template, slug, "dois")
    if not isinstance(raw, dict):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for doi in raw.values():
        if not isinstance(doi, str):
            continue
        normalized = doi.strip()
        if not _is_valid_doi(normalized):
            continue
        url = f"https://doi.org/{normalized}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def get_primary_source_anchors_for_slug(
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Return cleaned, deduplicated source identifiers for a scope."""

    return _extract_anchors(template, slug)


def _extract_variants(
    template: dict[str, Any] | None,
    slug: str,
) -> dict[str, str]:
    raw = _scoped_value(template, slug, "variants")
    if not isinstance(raw, dict):
        return {}
    variants: dict[str, str] = {}
    for anchor, variant in raw.items():
        clean_anchor = _valid_anchor(anchor)
        if (
            not clean_anchor
            or not isinstance(variant, str)
            or not variant.strip()
            or '"' in variant
        ):
            continue
        variants[clean_anchor] = variant.strip()
    return variants


def get_source_scope_for_slug(
    template: dict[str, Any] | None,
    slug: str,
) -> dict[str, str]:
    """Return evidence-supplied relevance labels keyed by source identifier.

    Labels are normalized for case and carried as written, so each template
    can define its own relevance taxonomy without production-code vocabulary.
    """

    raw = _scoped_value(template, slug, "scope")
    if not isinstance(raw, dict):
        return {}
    labels: dict[str, str] = {}
    for anchor, label in raw.items():
        clean_anchor = _valid_anchor(anchor)
        if not clean_anchor or not isinstance(label, str) or not label.strip():
            continue
        normalized = label.strip().casefold()
        labels[clean_anchor] = normalized
    return labels


def label_rows_with_source_scope(
    rows: list[dict[str, Any]],
    template: dict[str, Any] | None,
    slug: str,
) -> list[dict[str, Any]]:
    """Annotate rows by matching configured identifiers in row metadata."""

    labels = get_source_scope_for_slug(template, slug)
    if not labels or not rows:
        return rows
    lookup = {anchor.casefold(): (anchor, label) for anchor, label in labels.items()}
    for row in rows:
        if not isinstance(row, dict):
            continue
        match: tuple[str, str] | None = None
        for key in ("title", "statement", "source_title", "direct_quote"):
            searchable = str(row.get(key) or "").casefold()
            if not searchable:
                continue
            for anchor_key, anchor_and_label in lookup.items():
                if anchor_key in searchable:
                    match = anchor_and_label
                    break
            if match:
                break
        if not match:
            continue
        anchor, label = match
        row["scope_relationship"] = label
        # Compatibility fields are populated dynamically from template data.
        row["population_scope"] = label
        for configured_label in set(labels.values()):
            row[configured_label] = configured_label == label
        row["_primary_source_anchor_match"] = anchor
        row["_m48_anchor_match"] = anchor
    return rows


def expand_primary_source_queries(
    question: str,
    template: dict[str, Any] | None,
    slug: str,
) -> list[str]:
    """Build identifier-anchored retrieval queries from template metadata."""

    base = str(question or "").strip()
    if not base:
        return []
    anchors = _extract_anchors(template, slug)
    if not anchors:
        return []
    cap = _max_anchors()
    if cap > 0:
        anchors = anchors[:cap]
    variants = _extract_variants(template, slug)
    queries: list[str] = []
    for anchor in anchors:
        queries.append(f'"{anchor}" {base}')
        if variant := variants.get(anchor):
            queries.append(f'"{anchor}" {variant} {base}')
    logger.info(
        "[primary_source_expander] emitted %d query variants for scope=%r",
        len(queries),
        slug,
    )
    return queries


# Compatibility aliases.  New code should use the source-oriented names above.
expand_primary_trial_dois = expand_primary_source_dois
get_primary_trial_anchors_for_slug = get_primary_source_anchors_for_slug
get_trial_population_scope_for_slug = get_source_scope_for_slug
label_rows_with_population_scope = label_rows_with_source_scope
expand_primary_trial_queries = expand_primary_source_queries
