"""Lossless source-metadata plumbing for narrative attribution."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from src.polaris_graph.settings import resolve


_ON = frozenset({"1", "true", "yes", "on", "enabled"})
_YEAR_RE = re.compile(r"\b(?:19|20|21)\d{2}\b")


def narrative_attribution_enabled() -> bool:
    """Central kill-switch; default OFF."""

    return resolve("PG_NARRATIVE_ATTRIBUTION").strip().lower() in _ON


def _mapping(row: Any) -> Mapping[str, Any]:
    return row if isinstance(row, Mapping) else {}


def _first(row: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, "", [], {}):
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        for name in names:
            value = metadata.get(name)
            if value not in (None, "", [], {}):
                return value
    return None


def _person_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(
            value.get("display_name") or value.get("name") or value.get("full_name") or ""
        ).strip()
    return str(value or "").strip()


def _authors(row: Mapping[str, Any]) -> str:
    value = _first(row, ("authors", "author", "creators", "creator"))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        names = [_person_text(item) for item in value]
        return ", ".join(name for name in names if name)
    return _person_text(value)


def _venue(row: Mapping[str, Any]) -> str:
    value = _first(
        row,
        ("venue", "journal", "publication", "publisher", "source_name", "repository", "site_name"),
    )
    if isinstance(value, Mapping):
        value = value.get("display_name") or value.get("name") or value.get("title")
    return str(value or "").strip()


def _year(row: Mapping[str, Any]) -> str:
    value = _first(
        row,
        ("year", "publication_year", "pub_date", "publication_date", "published", "date"),
    )
    match = _YEAR_RE.search(str(value or ""))
    return match.group(0) if match else ""


def _prominence(row: Mapping[str, Any]) -> float:
    for name in (
        "composition_weight", "credibility_weight", "authority_score",
        "content_relevance_weight", "selection_relevance", "relevance_weight",
    ):
        value = row.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, min(1.0, float(value)))
    return 1.0


def source_attribution_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only metadata actually present on one evidence row."""

    record = {
        "evidence_id": str(row.get("evidence_id") or ""),
        "author": _authors(row),
        "venue": _venue(row),
        "year": _year(row),
        "prominence_weight": _prominence(row),
    }
    record["available_fields"] = [
        key for key in ("author", "venue", "year") if record[key]
    ]
    return record


def format_source_attribution_metadata(row: Mapping[str, Any]) -> str:
    """Writer metadata line; missing fields are omitted rather than invented."""

    record = source_attribution_record(row)
    fields = [f"evidence_id={record['evidence_id']}"]
    fields.extend(
        f"{key}={record[key]}" for key in ("author", "venue", "year") if record[key]
    )
    fields.append(f"prominence_weight={record['prominence_weight']:.6f}")
    return "source_metadata: " + "; ".join(fields)


def build_attribution_coverage(evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Coverage ledger proving every evidence row entered the metadata pack."""

    records = [source_attribution_record(_mapping(row)) for row in (evidence_rows or [])]
    return {
        "input_count": len(evidence_rows or []),
        "packed_count": len(records),
        "missing_metadata_count": sum(1 for record in records if not record["available_fields"]),
        "records": records,
    }
