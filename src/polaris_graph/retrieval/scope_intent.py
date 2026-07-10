"""Shared scope-intent normalizer for S1.b RETRIEVE (Design 7 D2 + D3).

The scope-gate already parses the prompt into ``UserConstraints`` + ``ScopeConstraints`` and
writes their ``to_dict()`` forms into ``protocol['user_constraints']`` / ``protocol['scope_constraints']``
(see ``intake_constraint_extractor.py`` + ``scope_gate.py``). This module reads those blocks and
produces ONE flat :class:`ScopeIntent` that both scope consumers share:
  - D2 (``scope_directives.py``)  -> the SCOPE DIRECTIVES text block in the qgen prompts.
  - D3 (``scope_search_lanes.py``) -> the additive scoped backend request params.

FAIL-OPEN (master §1.7, doc 07 D2/D3): a thin, malformed, or ABSENT scope block yields an empty
:class:`ScopeIntent` (``is_empty()`` True). No scope stated => no directives, no scoped lanes —
today's behavior byte-identical. This module NEVER raises on a caller's protocol and NEVER drops
a source; it only surfaces the user's EXPLICIT constraints for additive discovery + disclosure.

§-1.3: the user's explicit scope is the user's own constraint (distinct from credibility
weighting). This module reads it; enforcement (weight/mask/disclose) stays downstream in
``constraint_enforcement.py`` — nothing here filters, drops, or caps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.scope_intent")


@dataclass
class ScopeIntent:
    """Flat, normalized user scope. Every field optional; all-empty => no scope stated."""

    date_start_iso: Optional[str] = None      # 'YYYY-MM-DD' floor  (from UserConstraints)
    date_end_iso: Optional[str] = None        # 'YYYY-MM' or 'YYYY-MM-DD' ceiling
    date_start_year: Optional[int] = None
    date_end_year: Optional[int] = None
    language: Optional[str] = None            # ISO code, e.g. 'en', 'zh'
    geographies: list[str] = field(default_factory=list)   # ISO country codes (jurisdiction/geography facets)
    source_types: list[str] = field(default_factory=list)  # facet_ids on dimension source_type (op include/prefer)
    peer_reviewed_only: bool = False          # a peer_reviewed_journal include/prefer facet is present
    authors: list[str] = field(default_factory=list)       # named-include labels that look like authors
    named_includes: list[str] = field(default_factory=list)  # all named-include labels (for the directive block)

    def is_empty(self) -> bool:
        return not (
            self.date_start_iso or self.date_end_iso or self.language
            or self.geographies or self.source_types or self.peer_reviewed_only
            or self.authors or self.named_includes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "date_start_iso": self.date_start_iso,
            "date_end_iso": self.date_end_iso,
            "date_start_year": self.date_start_year,
            "date_end_year": self.date_end_year,
            "language": self.language,
            "geographies": list(self.geographies),
            "source_types": list(self.source_types),
            "peer_reviewed_only": self.peer_reviewed_only,
            "authors": list(self.authors),
            "named_includes": list(self.named_includes),
        }


# Named-include labels that carry one of these nouns are treated as SOURCE/ORG pins, not authors,
# so a "papers by <Person>" author lane is not accidentally fed an organisation name.
_ORG_NOUNS: tuple[str, ...] = (
    "journal", "review", "association", "society", "institute", "agency", "administration",
    "organization", "organisation", "committee", "council", "ministry", "department",
    "database", "registry", "press", "times", "post", "news", "report",
)


def _facet_country(facet_id: str) -> Optional[str]:
    """Pull an ISO country code out of a jurisdiction/geography facet_id, e.g.
    'jurisdiction:us' -> 'us', 'jurisdiction:EU' -> 'eu'. Returns None when the facet_id
    carries no ':<code>' suffix (a source-type facet)."""
    if ":" in facet_id:
        code = facet_id.split(":", 1)[1].strip().lower()
        # ISO-3166 alpha-2 (or the 'eu' bloc); anything longer is not a country lane.
        if code and 2 <= len(code) <= 3 and code.isalpha():
            return code
    return None


def build_scope_intent(
    user_constraints: Optional[dict],
    scope_constraints: Optional[dict],
) -> ScopeIntent:
    """Normalize the two protocol scope blocks into one :class:`ScopeIntent`. Fail-open: any
    missing/oddly-typed field is skipped, never raised on."""
    intent = ScopeIntent()
    uc = user_constraints if isinstance(user_constraints, dict) else {}
    sc = scope_constraints if isinstance(scope_constraints, dict) else {}

    try:
        intent.date_start_iso = uc.get("date_start_iso")
        intent.date_end_iso = uc.get("date_end_iso")
        intent.date_start_year = uc.get("date_start_year")
        intent.date_end_year = uc.get("date_end_year")
        lang = uc.get("language")
        if isinstance(lang, str) and lang.strip():
            intent.language = lang.strip().lower()
    except Exception:  # noqa: BLE001 — fail-open: a broken UserConstraints block => no date/lang scope
        logger.debug("[scope_intent] user_constraints parse fell open", exc_info=True)

    try:
        for facet in sc.get("facets", []) or []:
            if not isinstance(facet, dict):
                continue
            op = str(facet.get("op", "")).lower()
            # Only INCLUDE / PREFER facets ADD a scoped discovery lane. An EXCLUDE facet is a
            # demote handled downstream (constraint_enforcement) — never a search lane here.
            if op not in ("include", "prefer"):
                continue
            fid = str(facet.get("facet_id", ""))
            dim = str(facet.get("dimension", "")).lower()
            country = _facet_country(fid)
            if dim in ("jurisdiction", "geography") and country:
                if country not in intent.geographies:
                    intent.geographies.append(country)
            elif dim == "source_type" and fid:
                if fid not in intent.source_types:
                    intent.source_types.append(fid)
                if fid == "peer_reviewed_journal":
                    intent.peer_reviewed_only = True
    except Exception:  # noqa: BLE001 — fail-open on a malformed facets list
        logger.debug("[scope_intent] scope_constraints facets parse fell open", exc_info=True)

    try:
        for named in sc.get("named_include", []) or []:
            if not isinstance(named, dict):
                continue
            label = str(named.get("label", "")).strip()
            if not label:
                continue
            if label not in intent.named_includes:
                intent.named_includes.append(label)
            low = label.lower()
            if not any(noun in low for noun in _ORG_NOUNS):
                if label not in intent.authors:
                    intent.authors.append(label)
    except Exception:  # noqa: BLE001 — fail-open on a malformed named_include list
        logger.debug("[scope_intent] named_include parse fell open", exc_info=True)

    return intent


def build_scope_intent_from_protocol(protocol: Optional[dict]) -> ScopeIntent:
    """Convenience: read both scope blocks straight off a protocol dict (spine-side callers)."""
    if not isinstance(protocol, dict):
        return ScopeIntent()
    return build_scope_intent(protocol.get("user_constraints"), protocol.get("scope_constraints"))
