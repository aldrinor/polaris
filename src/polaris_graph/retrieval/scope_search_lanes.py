"""Design 7 D3 — scope flows into ALL backend filters as ADDITIVE scoped lanes.

Today only OpenAlex gets a native scope filter (the date lane, ``PG_OPENALEX_DATE_FILTER``).
Serper receives ``{q, num, page}`` only; S2 receives ``{query, fields, limit}`` only — no date,
geography, language, or source-type parameter reaches them. This module builds the scoped request
params for each backend so the caller can issue ONE EXTRA scoped call ALONGSIDE the untouched base
call (mirroring the proven OpenAlex date-lane union pattern):

  - Serper  : ``tbs=cdr:1,cd_min:..,cd_max:..`` (date) + ``gl=<country>`` (geo) + ``hl=<lang>``.
  - S2      : ``year=YYYY-YYYY`` (date) + ``publicationTypes=JournalArticle`` (peer-review, SCOPED
              lane only — journal-only stays DORMANT as a global drop per operator veto).
  - OpenAlex: ``language:<code>`` + ``author.id``/``author`` (beyond the existing date lane).

§-1.3 discipline (binding for D1-D3): the user's EXPLICIT scope is a user-requested constraint,
distinct from credibility weighting. Search-side, a scoped lane may only ADD in-scope discovery —
NEVER remove the base lane, never drop a source. Post-retrieval enforcement stays exactly the
existing weight/mask/disclose (``constraint_enforcement.py``). No lane may be tuned to hit a
breadth number (the day-waster ban). Every builder is PURE (no network) and FAIL-OPEN: an empty
scope, a disabled flag, or a build fault returns ``{}`` (no scoped lane => byte-identical).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Union

from src.polaris_graph.retrieval.scope_intent import ScopeIntent, build_scope_intent

logger = logging.getLogger("polaris_graph.scope_search_lanes")


def serper_scope_filter_enabled() -> bool:
    """PG_SERPER_SCOPE_FILTER (default OFF => no scoped Serper lane => byte-identical)."""
    return os.getenv("PG_SERPER_SCOPE_FILTER", "0").strip() in ("1", "true", "True")


def s2_scope_filter_enabled() -> bool:
    """PG_S2_SCOPE_FILTER (default OFF)."""
    return os.getenv("PG_S2_SCOPE_FILTER", "0").strip() in ("1", "true", "True")


def openalex_scope_filter_enabled() -> bool:
    """PG_OPENALEX_SCOPE_FILTER (default OFF); the legacy PG_OPENALEX_DATE_FILTER alias is honored
    by the live-retriever seam so the existing date lane keeps working under the old name."""
    return os.getenv("PG_OPENALEX_SCOPE_FILTER", "0").strip() in ("1", "true", "True")


def _coerce_intent(scope: Union[ScopeIntent, dict, None]) -> Optional[ScopeIntent]:
    if scope is None:
        return None
    if isinstance(scope, ScopeIntent):
        return scope
    if isinstance(scope, dict):
        if "user_constraints" in scope or "scope_constraints" in scope:
            return build_scope_intent(scope.get("user_constraints"), scope.get("scope_constraints"))
        return build_scope_intent(scope, scope)
    return None


def _iso_to_serper_date(iso: Optional[str], *, end: bool) -> Optional[str]:
    """Convert an ISO date bound ('YYYY', 'YYYY-MM', 'YYYY-MM-DD') to Serper `tbs` MM/DD/YYYY.
    An end bound with only a year/month expands to the widest day in the period (fail-open: any
    parse fault returns None => that bound is simply omitted from tbs)."""
    if not iso:
        return None
    try:
        parts = str(iso).split("-")
        y = int(parts[0])
        mo = int(parts[1]) if len(parts) > 1 else (12 if end else 1)
        if len(parts) > 2:
            d = int(parts[2])
        else:
            d = 1 if not end else (31 if mo in (1, 3, 5, 7, 8, 10, 12) else 30 if mo != 2 else 28)
        return f"{mo:02d}/{d:02d}/{y:04d}"
    except (ValueError, IndexError):
        return None


def build_serper_scope_params(scope: Union[ScopeIntent, dict, None]) -> dict[str, Any]:
    """Serper scoped params: ``tbs`` (date), ``gl`` (geography), ``hl`` (language). Returns {}
    when the flag is OFF or scope is empty (fail-open, no scoped lane)."""
    if not serper_scope_filter_enabled():
        return {}
    try:
        intent = _coerce_intent(scope)
        if intent is None or intent.is_empty():
            return {}
        params: dict[str, Any] = {}
        cd_min = _iso_to_serper_date(intent.date_start_iso, end=False)
        cd_max = _iso_to_serper_date(intent.date_end_iso, end=True)
        if cd_min or cd_max:
            tbs = "cdr:1"
            if cd_min:
                tbs += f",cd_min:{cd_min}"
            if cd_max:
                tbs += f",cd_max:{cd_max}"
            params["tbs"] = tbs
        if intent.geographies:
            params["gl"] = intent.geographies[0].lower()  # Serper takes ONE country code
        if intent.language:
            params["hl"] = intent.language.lower()
        return params
    except Exception:  # noqa: BLE001 — fail-open: no scoped Serper lane on a build fault
        logger.debug("[scope_search_lanes] serper scope params fell open", exc_info=True)
        return {}


def build_s2_scope_params(scope: Union[ScopeIntent, dict, None]) -> dict[str, Any]:
    """Semantic Scholar scoped params: ``year`` (YYYY / YYYY-YYYY / YYYY- / -YYYY) and
    ``publicationTypes`` (JournalArticle) on the SCOPED lane only. Returns {} when OFF/empty."""
    if not s2_scope_filter_enabled():
        return {}
    try:
        intent = _coerce_intent(scope)
        if intent is None or intent.is_empty():
            return {}
        params: dict[str, Any] = {}
        lo, hi = intent.date_start_year, intent.date_end_year
        if isinstance(lo, int) and isinstance(hi, int):
            params["year"] = f"{lo}-{hi}" if lo != hi else str(lo)
        elif isinstance(lo, int):
            params["year"] = f"{lo}-"
        elif isinstance(hi, int):
            params["year"] = f"-{hi}"
        if intent.peer_reviewed_only:
            # SCOPED lane ONLY — journal-only stays a DORMANT global drop per operator veto;
            # this merely ADDS a JournalArticle-typed discovery lane, drops nothing (§-1.3).
            params["publicationTypes"] = "JournalArticle"
        return params
    except Exception:  # noqa: BLE001 — fail-open
        logger.debug("[scope_search_lanes] s2 scope params fell open", exc_info=True)
        return {}


def build_openalex_scope_params(scope: Union[ScopeIntent, dict, None]) -> dict[str, Any]:
    """OpenAlex scoped params BEYOND the existing date lane: ``language`` (ISO code) and
    ``author`` (named-author labels). Date stays on the existing from_date/to_date lane; this
    adds the non-date dimensions. Returns {} when OFF/empty (fail-open)."""
    if not openalex_scope_filter_enabled():
        return {}
    try:
        intent = _coerce_intent(scope)
        if intent is None or intent.is_empty():
            return {}
        params: dict[str, Any] = {}
        if intent.language:
            params["language"] = intent.language.lower()
        if intent.authors:
            params["authors"] = list(intent.authors)
        return params
    except Exception:  # noqa: BLE001 — fail-open
        logger.debug("[scope_search_lanes] openalex scope params fell open", exc_info=True)
        return {}
