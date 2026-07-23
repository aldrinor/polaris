"""Per-evidence prompt allow-lists built only from the supplied evidence.

The generator may cite quantitative values and named entities only when those
surface forms occur in the row it cites.  This module extracts that closed
world before generation.  It is intentionally domain-neutral: names come from
row metadata and generic proper-name/identifier shapes, never from a product,
study-program, venue, or subject-matter dictionary.

The post-generation verifier remains authoritative.  This prompt-time layer
only reduces unsupported invention before verification.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


_MAX_SCAN_CHARS = max(
    1000,
    int(os.getenv("PG_ALLOW_LIST_MAX_SCAN_CHARS", "100000")),
)

# Preserve the source surface form.  The suffix accepts symbols and generic
# written units; it does not enumerate a subject-matter unit vocabulary.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"[-+\u2212]?\d[\d,]*(?:[.]\d+)?"
    r"(?:\s*(?:%|\u2030|\u00d7|"
    r"[A-Za-z\u00b5\u03bc](?:[A-Za-z0-9\u00b5\u03bc/\u00b2\u00b3^.-]*"
    r"[A-Za-z0-9\u00b5\u03bc/\u00b2\u00b3^-])?))?"
    r"(?![A-Za-z0-9_-])"
)

# Generic authored identifiers and proper names.  The identifier branch
# handles names such as DATASET-4 or MODEL-X; the proper-name branch handles
# one-to-four title-cased words.  Candidates are accepted only when copied
# from the current row.
_IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z][A-Z0-9]{2,}(?:[-_][A-Z0-9]+)+|[A-Z]{4,}\d*)\b"
)
_PROPER_NAME_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9'’.-]+"
    r"(?:\s+[A-Z][A-Za-z0-9'’.-]+){0,3}\b"
)

_NAME_METADATA_KEYS = (
    "name",
    "study_name",
    "source_name",
    "program_name",
    "dataset_name",
    "model_name",
    "entity",
    "subject",
    "intervention",
    "comparator",
    "organization",
    "publisher",
    "authors",
)
_TEXT_METADATA_KEYS = (
    "title",
    "source_title",
    "statement",
    "direct_quote",
)


@dataclass
class EvidenceAllowList:
    """Closed-world citable surface forms for one evidence row."""

    evidence_id: str
    numbers: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.numbers or self.names)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _iter_metadata_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_metadata_values(nested)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for nested in value:
            yield from _iter_metadata_values(nested)


def _extract_numbers(text: str) -> list[str]:
    return _ordered_unique(match.group(0).strip() for match in _NUMBER_RE.finditer(text))


def _extract_names(row: Mapping[str, Any], text: str) -> list[str]:
    metadata_names: list[str] = []
    for key in _NAME_METADATA_KEYS:
        metadata_names.extend(_iter_metadata_values(row.get(key)))

    # Titles are evidence, not an ontology.  Generic shapes found there are
    # useful even when the retriever did not populate structured name fields.
    title_text = " ".join(
        str(row.get(key) or "")
        for key in ("title", "source_title", "statement")
    )
    shaped = list(_IDENTIFIER_RE.findall(text))
    shaped.extend(_PROPER_NAME_RE.findall(title_text))

    # A metadata value must itself occur in row text before it becomes citable.
    # This prevents an unrelated shell field from broadening the allow-list.
    copied_metadata = [
        name
        for name in metadata_names
        if str(name or "").strip()
        and str(name).strip().casefold() in text.casefold()
    ]
    return _ordered_unique([*copied_metadata, *shaped])


def build_allow_list_for_evidence(
    evidence_id: str,
    direct_quote: str,
    statement: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceAllowList:
    """Extract one row's allow-list from its own text and metadata."""

    row = dict(metadata or {})
    row.setdefault("direct_quote", direct_quote or "")
    row.setdefault("statement", statement or "")
    text = " ".join(
        str(row.get(key) or "")
        for key in _TEXT_METADATA_KEYS
    ).strip()
    if len(text) > _MAX_SCAN_CHARS:
        text = text[:_MAX_SCAN_CHARS]
    return EvidenceAllowList(
        evidence_id=evidence_id,
        numbers=_extract_numbers(text),
        names=_extract_names(row, text),
    )


def build_allow_lists(
    evidence_subset: list[dict[str, Any]],
) -> dict[str, EvidenceAllowList]:
    """Build allow-lists for all rows that expose at least one surface form."""

    out: dict[str, EvidenceAllowList] = {}
    for row in evidence_subset or []:
        evidence_id = str(row.get("evidence_id") or row.get("id") or "")
        if not evidence_id:
            continue
        allow = build_allow_list_for_evidence(
            evidence_id,
            str(row.get("direct_quote") or ""),
            str(row.get("statement") or ""),
            metadata=row,
        )
        if not allow.is_empty():
            out[evidence_id] = allow
    return out


def _format_capped(values: list[str], cap: int) -> str:
    if not values:
        return "(none)"
    shown = values[:cap]
    extra = len(values) - len(shown)
    rendered = ", ".join(shown)
    if extra > 0:
        rendered += f" (+{extra} more)"
    return rendered


def format_allow_list_for_prompt(
    allow_lists: dict[str, EvidenceAllowList],
    max_numbers_per_ev: int = 15,
    max_names_per_ev: int = 15,
) -> str:
    """Render the evidence-derived constraint block for the writer."""

    if not allow_lists:
        return ""
    lines = [
        "EVIDENCE VALUE ALLOW-LIST (anti-fabrication constraint).",
        "For each evidence ID, cite only the NUMBERS and NAMES copied below "
        "from that row. Do not introduce a number or named entity absent from "
        "the row you cite; omit it or cite a different supporting row.",
    ]
    for evidence_id in sorted(allow_lists):
        allow = allow_lists[evidence_id]
        lines.append(
            f"- {evidence_id}: "
            f"numbers={{{_format_capped(allow.numbers, max_numbers_per_ev)}}} | "
            f"names={{{_format_capped(allow.names, max_names_per_ev)}}}"
        )
    lines.append(
        "Rows not listed here contain no extractable numeric or named surface "
        "forms and may support qualitative claims only."
    )
    return "\n".join(lines)
