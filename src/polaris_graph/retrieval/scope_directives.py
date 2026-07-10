"""S1.b scope -> query WORDING + scope -> backend FILTERS (Design 7 D2 + D3, ruling R11).

PURE + fail-open. Consumes the two scope DICTS the scope gate writes into protocol.json —
``protocol["user_constraints"]`` (``UserConstraints.to_dict()``) and
``protocol["scope_constraints"]`` (``ScopeConstraints.to_dict()``) — and produces:

  * D2: ``scope_directives_block(...)`` — the compact "SCOPE DIRECTIVES" text appended to the
    qgen TOC / facet-planner / per-todo prompts so a generated query CARRIES the user's scope
    ("... randomized trials Europe 2019..2023") instead of hoping the LLM keeps it.
  * D3: ``serper_scope_params`` / ``s2_scope_params`` / ``openalex_scope_params`` — the ADDITIVE
    scoped-lane parameters for each search backend (an EXTRA in-scope discovery call beside the
    untouched base call; §-1.3: adds discovery, drops nothing; the base lane always still fires).

Backend parameter formats are from the live API docs (LAW III, verified 2026-07):
  * Serper (google.serper.dev): JSON body keys ``tbs=cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY``
    (custom date range), ``gl=<iso2 country, lower>``, ``hl=<iso2 language>``.
  * Semantic Scholar bulk /paper/search: ``year=YYYY-YYYY`` (or ``YYYY-`` / ``-YYYY``) +
    ``publicationTypes`` enum (``JournalArticle`` on the scoped peer-reviewed lane only — the
    global journal-only DROP stays DORMANT per operator veto; this only ADDS a discovery lane).
  * OpenAlex /works: ``filter=language:<code>`` and ``filter=author.id:<Axxxx>`` (id only, when a
    named-include source carries a resolved OpenAlex author id; a bare name is left to the D2
    query wording, never guessed into a filter).

Every function returns an EMPTY value ("" / {}) on any fault or when no scope is present — so an
empty-scope run and a flag-OFF run are byte-identical. The activation-marker helpers emit the
existing ``[activation] `` prefix so a dark scoped lane is detectable in the forensic buffer.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.scope_directives")

_INCLUDE_OPS = ("include", "prefer")
_GEO_DIMS = ("geography", "jurisdiction")


# ─────────────────────────────────────────────────────────────────────────────
# small pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _iso_parts(iso: Optional[str]) -> Optional[tuple[int, int, int]]:
    """Split a ``UserConstraints`` ISO bound ('YYYY-MM-DD' | 'YYYY-MM' | 'YYYY') into
    (year, month, day). A month-only bound yields day 0 (caller decides floor/ceiling). None on
    an empty/unparseable value."""
    s = (iso or "").strip()
    if not s:
        return None
    parts = s.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) >= 2 else 0
        day = int(parts[2]) if len(parts) >= 3 else 0
        return year, month, day
    except (ValueError, IndexError):
        return None


def _iso_to_mdy(iso: Optional[str], *, ceiling: bool) -> Optional[str]:
    """A ``UserConstraints`` ISO bound -> Serper ``MM/DD/YYYY``. A month-precision CEILING snaps to
    that month's last day; a month-precision FLOOR to the first; a year-only bound to 12/31 or
    01/01. None on an empty/unparseable bound (pure; ``calendar`` is stdlib)."""
    parts = _iso_parts(iso)
    if parts is None:
        return None
    year, month, day = parts
    try:
        if month == 0:
            month, day = (12, 31) if ceiling else (1, 1)
        elif day == 0:
            if ceiling:
                import calendar  # noqa: PLC0415
                day = calendar.monthrange(year, month)[1]
            else:
                day = 1
        return f"{month:02d}/{day:02d}/{year:04d}"
    except (ValueError, IndexError):
        return None


def _iso2(value: Optional[str]) -> Optional[str]:
    """A clean 2-letter code from a facet_id fragment ('jurisdiction:US' -> 'US', 'US' -> 'US').
    None when no bare 2-letter code is derivable (we never guess a country from a free-text
    region — that stays D2 wording only)."""
    s = (value or "").strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return None


def _facets(scope_constraints: Optional[dict]) -> list[dict[str, Any]]:
    sc = _as_dict(scope_constraints)
    facets = sc.get("facets")
    return [f for f in facets if isinstance(f, dict)] if isinstance(facets, list) else []


def _first_geo_iso2(scope_constraints: Optional[dict]) -> Optional[str]:
    for f in _facets(scope_constraints):
        if f.get("dimension") in _GEO_DIMS and f.get("op") in _INCLUDE_OPS:
            iso = _iso2(f.get("facet_id"))
            if iso:
                return iso
    return None


def _wants_peer_reviewed(scope_constraints: Optional[dict]) -> bool:
    for f in _facets(scope_constraints):
        if f.get("dimension") == "source_type" and f.get("op") in _INCLUDE_OPS:
            if str(f.get("facet_id", "")).strip().lower() == "peer_reviewed_journal":
                return True
    return False


def _language(user_constraints: Optional[dict], scope_constraints: Optional[dict]) -> Optional[str]:
    uc = _as_dict(user_constraints)
    lang = uc.get("language")
    if isinstance(lang, str) and lang.strip():
        return lang.strip().lower()
    for f in _facets(scope_constraints):
        if f.get("dimension") == "language" and f.get("op") in _INCLUDE_OPS:
            code = _iso2(f.get("facet_id"))
            if code:
                return code.lower()
    return None


def _named_includes(scope_constraints: Optional[dict]) -> list[dict[str, Any]]:
    sc = _as_dict(scope_constraints)
    ni = sc.get("named_include")
    return [n for n in ni if isinstance(n, dict)] if isinstance(ni, list) else []


# ─────────────────────────────────────────────────────────────────────────────
# D2 — scope -> query wording
# ─────────────────────────────────────────────────────────────────────────────


def scope_directives_block(
    user_constraints: Optional[dict],
    scope_constraints: Optional[dict],
) -> str:
    """Build the compact SCOPE DIRECTIVES block appended to the qgen prompts (Design 7 D2). Empty
    string when no scope is present => byte-identical prompts. Fail-open (any fault => "")."""
    try:
        lines: list[str] = []
        uc = _as_dict(user_constraints)

        start_iso, end_iso = uc.get("date_start_iso"), uc.get("date_end_iso")
        if start_iso or end_iso:
            lo = str(start_iso) if start_iso else "(open)"
            hi = str(end_iso) if end_iso else "(open)"
            lines.append(f"- Publication window: {lo} to {hi} (stay inside it; do not cite outside).")

        lang = _language(user_constraints, scope_constraints)
        if lang:
            lines.append(f"- Language: prefer {lang} sources.")

        geo_terms: list[str] = []
        source_terms: list[str] = []
        for f in _facets(scope_constraints):
            if f.get("op") not in _INCLUDE_OPS:
                continue
            fid = str(f.get("facet_id", "")).strip()
            if not fid:
                continue
            if f.get("dimension") in _GEO_DIMS:
                geo_terms.append(fid)
            elif f.get("dimension") == "source_type":
                source_terms.append(fid)
        if geo_terms:
            lines.append("- Geography / jurisdiction: " + ", ".join(sorted(set(geo_terms))) + ".")
        if source_terms:
            lines.append("- Source type: " + ", ".join(sorted(set(source_terms))) + ".")

        includes = [str(n.get("label", "")).strip() for n in _named_includes(scope_constraints)]
        includes = [x for x in includes if x]
        if includes:
            lines.append("- Named sources to include: " + ", ".join(includes) + ".")

        if not lines:
            return ""
        return (
            "SCOPE DIRECTIVES (carry EVERY applicable one into each query; never contradict them):\n"
            + "\n".join(lines)
        )
    except Exception as exc:  # noqa: BLE001 — fail-open: no scope block, legacy prompt stands
        logger.warning("[scope_directives] block build failed (%s); using legacy prompt", exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# D3 — scope -> backend filters (ADDITIVE scoped-lane params)
# ─────────────────────────────────────────────────────────────────────────────


def serper_scope_params(
    user_constraints: Optional[dict],
    scope_constraints: Optional[dict],
) -> dict[str, str]:
    """Serper scoped-lane JSON body params: ``tbs`` (custom date range), ``gl`` (country), ``hl``
    (language). Empty dict when no applicable scope => the caller fires no extra lane. Fail-open."""
    try:
        params: dict[str, str] = {}
        uc = _as_dict(user_constraints)
        cd_min = _iso_to_mdy(uc.get("date_start_iso"), ceiling=False)
        cd_max = _iso_to_mdy(uc.get("date_end_iso"), ceiling=True)
        if cd_min or cd_max:
            tbs = "cdr:1"
            if cd_min:
                tbs += f",cd_min:{cd_min}"
            if cd_max:
                tbs += f",cd_max:{cd_max}"
            params["tbs"] = tbs
        geo = _first_geo_iso2(scope_constraints)
        if geo:
            params["gl"] = geo.lower()
        lang = _language(user_constraints, scope_constraints)
        if lang:
            params["hl"] = lang
        return params
    except Exception as exc:  # noqa: BLE001
        logger.warning("[scope_directives] serper params failed (%s); scoped Serper lane idle", exc)
        return {}


def s2_scope_params(
    user_constraints: Optional[dict],
    scope_constraints: Optional[dict],
) -> dict[str, str]:
    """Semantic Scholar scoped-lane params: ``year`` (YYYY-YYYY / YYYY- / -YYYY) and
    ``publicationTypes=JournalArticle`` ONLY when the user asked for peer-reviewed sources (scoped
    discovery lane; the global journal-only DROP stays dormant). Empty dict => no extra lane."""
    try:
        params: dict[str, str] = {}
        uc = _as_dict(user_constraints)
        ys, ye = uc.get("date_start_year"), uc.get("date_end_year")
        lo = str(ys) if isinstance(ys, int) else ""
        hi = str(ye) if isinstance(ye, int) else ""
        if lo and hi:
            params["year"] = f"{lo}-{hi}"
        elif lo:
            params["year"] = f"{lo}-"
        elif hi:
            params["year"] = f"-{hi}"
        if _wants_peer_reviewed(scope_constraints):
            params["publicationTypes"] = "JournalArticle"
        return params
    except Exception as exc:  # noqa: BLE001
        logger.warning("[scope_directives] s2 params failed (%s); scoped S2 lane idle", exc)
        return {}


def openalex_scope_params(
    user_constraints: Optional[dict],
    scope_constraints: Optional[dict],
) -> dict[str, str]:
    """OpenAlex scoped-lane filter fragments BEYOND the existing date lane: ``language`` (ISO code)
    and ``author`` (an OpenAlex author id ``Axxxx`` from a named-include's identity — never a bare
    name; name resolution stays D2 wording). Empty dict => no extra language/author scoping."""
    try:
        params: dict[str, str] = {}
        lang = _language(user_constraints, scope_constraints)
        if lang:
            params["language"] = lang
        for n in _named_includes(scope_constraints):
            identity = _as_dict(n.get("identity"))
            aid = (
                identity.get("openalex_author_id")
                or identity.get("author_id")
                or identity.get("openalex_id")
            )
            if isinstance(aid, str) and aid.strip().upper().startswith("A"):
                params["author"] = aid.strip()
                break
        return params
    except Exception as exc:  # noqa: BLE001
        logger.warning("[scope_directives] openalex params failed (%s); scoped OpenAlex extras idle", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# activation markers (forensic anti-dark; pure strings)
# ─────────────────────────────────────────────────────────────────────────────


def activation_marker(lane: str, params: dict[str, str]) -> str:
    """``[activation]`` line for a scoped backend lane: fired (with the params) or eligible-idle."""
    if params:
        keys = ",".join(sorted(params.keys()))
        return f"[activation] scope_{lane}: fired ({keys})"
    return f"[activation] scope_{lane}: eligible_no_scope (flag on; no applicable scope this query)"
