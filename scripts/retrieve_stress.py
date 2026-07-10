#!/usr/bin/env python3
"""S1.b RETRIEVE — real-life LIVE stress battery (box2: real Serper + Semantic Scholar + OpenAlex).

The offline sibling ``scripts/retrieve_selftest.py`` proves the CONSTRUCTED breadth plan + scope
request params with pure logic (no network). This battery proves the SAME production seams against
the LIVE backends and asserts, LINE-BY-LINE over EVERY returned hit (§-1.1, zero sampling), the two
halves of the Design-7 D1-D3 contract:

  A. BREADTH sizes from the user's ask (Design 7 D1, real ``resolve_breadth``):
     an explicit 45-query ask is HONORED and NOT clamped to the legacy hardcode of 35; a WIDE prompt
     directive widens to the WIDE class row (80); a NARROW prompt shrinks below 35. (Deterministic —
     the resolver is a pure function; the budget is a compute-safety CEILING, never a padded target,
     so the LIVE issued-count is NOT force-driven here, §-1.3 day-waster ban.)

  B. SCOPE reaches the LIVE backends, PER LANE, additively (Design 7 D3):
     the SCOPED lane's returned hits are ALL in-window; the untouched BASE lane still returns
     out-of-window hits — that base retention IS the no-drop proof (§-1.3). Asserted per-lane, never
     on the union. Each backend is exercised through its own production scope-param builder
     (``build_s2_scope_params`` / ``build_serper_scope_params`` / ``build_openalex_scope_params``),
     then fired live; every violation records the offending hit row VERBATIM.

Backend field honesty (why each lane asserts what it can PROVE from the live response):
  - Semantic Scholar returns a per-paper ``year``      -> per-hit year window assertion.
  - OpenAlex returns ``publication_year`` / ``language`` / ``authorships`` -> per-hit assertion for
    the date / language / author lanes.
  - Serper organic results carry NO reliable per-hit date/geo/language -> the Serper lane proves the
    scoped params REACH live Serper (well-formed + accepted, additive to the base lane); it does NOT
    fake a per-hit date verdict it cannot ground.

Run:  python scripts/retrieve_stress.py --out outputs/retrieve_stress_i1
Reads SERPER_API_KEY / SEMANTIC_SCHOLAR_API_KEY / PG_OPENALEX_MAILTO from the environment (.env).
Writes per-case ``capture.jsonl`` + ``verdict.json`` under <out>/<case_id>/ and an overall
``summary.json``. Prints a per-case line + a final RETRIEVE_STRESS_RESULT JSON block. Exit 0 iff clean.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── live endpoints (mirrors src/polaris_graph/retrieval/live_retriever.py + domain_backends.py) ──
SERPER_ENDPOINT = "https://google.serper.dev/search"
S2_BULK_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
OPENALEX_WORKS = "https://api.openalex.org/works"
_OPENALEX_SELECT = "id,doi,display_name,publication_year,language,authorships"
_S2_FIELDS = "title,abstract,url,externalIds,year,venue"

HTTP_TIMEOUT = float(os.getenv("PG_LIVE_HTTP_TIMEOUT", "30"))
LEGACY_HARDCODE_QUERY_BUDGET = 35  # the pre-Design-7 fixed default the resolver must NOT clamp to.

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


# ─────────────────────────────────────────────────────────────────────────────
# Live HTTP helpers (fail-loud: an error is reported verbatim, never a silent []).
# ─────────────────────────────────────────────────────────────────────────────
def _get_json(
    url: str, params: dict[str, Any], headers: Optional[dict[str, str]] = None,
    tries: int = 4, base_sleep: float = 2.0,
) -> tuple[Optional[dict[str, Any]], str]:
    """GET JSON with polite backoff on 429/503. Returns (json|None, error_string)."""
    last = ""
    for attempt in range(tries):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.get(url, params=params, headers=headers or {})
            if resp.status_code == 200:
                return resp.json(), ""
            last = f"HTTP {resp.status_code}"
            if resp.status_code in (429, 503):
                time.sleep(base_sleep * (attempt + 1))
                continue
            return None, last
        except Exception as exc:  # noqa: BLE001 — surface the live fault verbatim (LAW II)
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(base_sleep * (attempt + 1))
    return None, last


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str],
    tries: int = 3, base_sleep: float = 2.0,
) -> tuple[Optional[dict[str, Any]], str]:
    last = ""
    for attempt in range(tries):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json(), ""
            last = f"HTTP {resp.status_code}"
            if resp.status_code in (429, 503):
                time.sleep(base_sleep * (attempt + 1))
                continue
            return None, last
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(base_sleep * (attempt + 1))
    return None, last


def _s2_live(query: str, limit: int, scope_params: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Live Semantic Scholar bulk search. Mirrors live_retriever._s2_bulk_search field set +
    scope-param merge; keeps EVERY paper (year assertion needs no fetchable URL). Captures year."""
    headers = {}
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    params: dict[str, Any] = {"query": query, "fields": _S2_FIELDS, "limit": max(1, min(limit, 100))}
    if scope_params:
        for k, v in scope_params.items():
            if v not in (None, ""):
                params[k] = v
    data, err = _get_json(S2_BULK_ENDPOINT, params, headers=headers)
    if data is None:
        return [], err
    rows: list[dict[str, Any]] = []
    for paper in (data.get("data") or []):
        rows.append({
            "url": (paper.get("url") or "") or (paper.get("externalIds") or {}).get("DOI", ""),
            "title": paper.get("title") or "",
            "year": paper.get("year"),
            "venue": paper.get("venue"),
            "paper_id": paper.get("paperId", ""),
        })
    return rows, ""


def _openalex_live(query: str, per_page: int, filter_str: str) -> tuple[list[dict[str, Any]], str]:
    """Live OpenAlex /works search capturing the rich per-work fields the production
    ``openalex_search`` collapses away (language + authorships). ``filter_str`` empty => base lane."""
    params: dict[str, Any] = {"search": query, "per_page": max(1, min(per_page, 200)), "select": _OPENALEX_SELECT}
    if filter_str:
        params["filter"] = filter_str
    mailto = os.getenv("PG_OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    api_key = os.getenv("PG_OPENALEX_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key
    data, err = _get_json(OPENALEX_WORKS, params)
    if data is None:
        return [], err
    rows: list[dict[str, Any]] = []
    for work in (data.get("results") or []):
        authors = [
            (a.get("raw_author_name") or (a.get("author") or {}).get("display_name") or "")
            for a in (work.get("authorships") or [])
        ]
        rows.append({
            "url": work.get("doi") or work.get("id") or "",
            "title": work.get("display_name") or "",
            "year": work.get("publication_year"),
            "language": work.get("language"),
            "authors": [a for a in authors if a],
        })
    return rows, ""


def _serper_live(query: str, num: int, scope_params: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    key = os.getenv("SERPER_API_KEY", "").strip()
    if not key:
        return [], "SERPER_API_KEY missing"
    payload: dict[str, Any] = {"q": query, "num": num}
    if scope_params:
        for k, v in scope_params.items():
            if v not in (None, ""):
                payload[k] = v
    headers = {"X-API-KEY": key, "Content-Type": "application/json"}
    data, err = _post_json(SERPER_ENDPOINT, payload, headers)
    if data is None:
        return [], err
    rows = [
        {"url": it.get("link", ""), "title": it.get("title", ""), "date": it.get("date", "")}
        for it in (data.get("organic") or [])
    ]
    return rows, ""


def _year_of(value: Any) -> Optional[int]:
    """Best-effort integer year from an int, a 'YYYY-..' string, or free text (Serper date)."""
    if isinstance(value, int):
        return value
    m = _YEAR_RE.search(str(value or ""))
    return int(m.group(0)) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# GROUP A — breadth resolver honors the ask (Design 7 D1, real resolve_breadth, deterministic).
# ─────────────────────────────────────────────────────────────────────────────
def case_breadth_explicit_45() -> dict[str, Any]:
    from src.polaris_graph.retrieval.breadth_resolver import resolve_breadth

    question = (
        "Comprehensive, exhaustive systematic review of GLP-1 receptor agonists across all "
        "cardiometabolic outcomes — issue at least 45 sub-queries."
    )
    plan = resolve_breadth(question, run_config={"breadth": {"query_budget": 45}}).to_dict()
    violations: list[dict[str, Any]] = []
    if plan["query_budget"] != 45:
        violations.append({"field": "query_budget", "expected": 45, "got": plan["query_budget"]})
    if not plan["query_budget"] > LEGACY_HARDCODE_QUERY_BUDGET:
        violations.append({"field": "uncapped_gt_35", "expected": ">35 (not clamped to legacy)", "got": plan["query_budget"]})
    if plan["sources"].get("query_budget") != "runconfig":
        violations.append({"field": "source", "expected": "runconfig", "got": plan["sources"].get("query_budget")})
    if plan["breadth_class"] != "WIDE":
        violations.append({"field": "breadth_class", "expected": "WIDE", "got": plan["breadth_class"]})
    return {
        "case": "breadth_explicit_45_uncapped",
        "pass": not violations,
        "expected": "explicit ask query_budget=45 HONORED (source=runconfig), >35 uncapped, class WIDE",
        "got": f"query_budget={plan['query_budget']} source={plan['sources'].get('query_budget')} class={plan['breadth_class']}",
        "violations": violations,
        "capture": [plan],
    }


def case_breadth_wide_prompt() -> dict[str, Any]:
    from src.polaris_graph.retrieval.breadth_resolver import resolve_breadth

    question = "comprehensive systematic review of GLP-1 receptor agonists across cardiometabolic outcomes"
    plan = resolve_breadth(question).to_dict()
    violations: list[dict[str, Any]] = []
    if plan["breadth_class"] != "WIDE":
        violations.append({"field": "breadth_class", "expected": "WIDE", "got": plan["breadth_class"]})
    if plan["query_budget"] != 80:
        violations.append({"field": "query_budget", "expected": 80, "got": plan["query_budget"]})
    if not plan["query_budget"] > LEGACY_HARDCODE_QUERY_BUDGET:
        violations.append({"field": "uncapped_gt_35", "expected": ">35", "got": plan["query_budget"]})
    return {
        "case": "breadth_wide_from_prompt_80",
        "pass": not violations,
        "expected": "WIDE prompt directive -> class WIDE, query_budget=80 (>35, from WIDE class row)",
        "got": f"query_budget={plan['query_budget']} source={plan['sources'].get('query_budget')} class={plan['breadth_class']}",
        "violations": violations,
        "capture": [plan],
    }


def case_breadth_narrow_prompt() -> dict[str, Any]:
    from src.polaris_graph.retrieval.breadth_resolver import resolve_breadth

    question = "Give me a brief overview of S1P receptor modulators in multiple sclerosis"
    plan = resolve_breadth(question).to_dict()
    violations: list[dict[str, Any]] = []
    if plan["breadth_class"] != "NARROW":
        violations.append({"field": "breadth_class", "expected": "NARROW", "got": plan["breadth_class"]})
    if plan["query_budget"] != 15:
        violations.append({"field": "query_budget", "expected": 15, "got": plan["query_budget"]})
    if not plan["query_budget"] < LEGACY_HARDCODE_QUERY_BUDGET:
        violations.append({"field": "shrinks_lt_35", "expected": "<35", "got": plan["query_budget"]})
    return {
        "case": "breadth_narrow_from_prompt_shrinks",
        "pass": not violations,
        "expected": "NARROW prompt directive -> class NARROW, query_budget=15 (<35, ask can shrink too)",
        "got": f"query_budget={plan['query_budget']} source={plan['sources'].get('query_budget')} class={plan['breadth_class']}",
        "violations": violations,
        "capture": [plan],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GROUP B — scope reaches LIVE backends, per-lane, no-drop.
# ─────────────────────────────────────────────────────────────────────────────
def case_s2_year_scope_live() -> dict[str, Any]:
    from src.polaris_graph.retrieval.scope_search_lanes import build_s2_scope_params

    query = "GLP-1 receptor agonist cardiovascular outcomes"
    lo, hi = 2023, 2025
    # The real scope-gate always writes ISO bounds alongside the year bounds (see the
    # scope_dated_geo_lang fixture); ScopeIntent.is_empty() keys off the ISO fields, so both are set.
    scope = {"user_constraints": {
        "date_start_year": lo, "date_end_year": hi,
        "date_start_iso": f"{lo}-01-01", "date_end_iso": f"{hi}-12-31",
    }}
    scoped_params = build_s2_scope_params(scope)  # PG_S2_SCOPE_FILTER=1 set in main()

    violations: list[dict[str, Any]] = []
    if scoped_params.get("year") != f"{lo}-{hi}":
        violations.append({"field": "s2_scope_param", "expected": {"year": f"{lo}-{hi}"}, "got": scoped_params})

    base_rows, base_err = _s2_live(query, limit=50, scope_params=None)
    time.sleep(1.5)
    scoped_rows, scoped_err = _s2_live(query, limit=50, scope_params=scoped_params)

    capture = [{"lane": "base", **r} for r in base_rows] + [{"lane": "scoped_year", **r} for r in scoped_rows]

    if base_err:
        violations.append({"field": "s2_base_call", "expected": "live results", "got": f"error: {base_err}"})
    if scoped_err:
        violations.append({"field": "s2_scoped_call", "expected": "live results", "got": f"error: {scoped_err}"})

    # SCOPED lane: every KNOWN-year hit must be in [lo, hi]; the lane must not be dark.
    scoped_in_window = 0
    for r in scoped_rows:
        yr = _year_of(r.get("year"))
        if yr is None:
            continue
        if yr < lo or yr > hi:
            violations.append({"lane": "scoped_year", "reason": f"year {yr} outside {lo}-{hi}", "hit": r})
        else:
            scoped_in_window += 1
    if scoped_rows and scoped_in_window == 0 and not scoped_err:
        violations.append({"lane": "scoped_year", "reason": "no in-window known-year hit (dark lane)", "hit": None})

    # BASE lane no-drop proof: at least one out-of-window (pre-lo) known-year hit must survive.
    base_out = [r for r in base_rows if (_year_of(r.get("year")) or 9999) < lo]
    if base_rows and not base_out and not base_err:
        violations.append({"lane": "base", "reason": f"base returned NO pre-{lo} hit (no-drop proof failed)", "hit": None})

    got = (
        f"scoped year param={scoped_params.get('year')}; scoped hits={len(scoped_rows)} "
        f"(in-window={scoped_in_window}, out-of-window={sum(1 for r in scoped_rows if (_year_of(r.get('year')) or lo) not in range(lo, hi+1) and _year_of(r.get('year')) is not None)}); "
        f"base hits={len(base_rows)} (pre-{lo}={len(base_out)}, e.g. "
        f"{[_year_of(r.get('year')) for r in base_out[:3]]})"
    )
    return {
        "case": "s2_year_scope_live",
        "pass": not violations,
        "expected": f"S2 scoped year={lo}-{hi}: ALL scoped hits in-window; base retains pre-{lo} hits (no-drop)",
        "got": got,
        "violations": violations,
        "capture": capture,
    }


def case_openalex_date_scope_live() -> dict[str, Any]:
    query = "GLP-1 receptor agonist cardiovascular outcomes"
    lo, hi = 2023, 2025
    filter_str = f"from_publication_date:{lo}-01-01,to_publication_date:{hi}-12-31"

    violations: list[dict[str, Any]] = []
    base_rows, base_err = _openalex_live(query, per_page=50, filter_str="")
    time.sleep(1.0)
    scoped_rows, scoped_err = _openalex_live(query, per_page=50, filter_str=filter_str)

    capture = [{"lane": "base", **r} for r in base_rows] + [{"lane": "scoped_date", **r} for r in scoped_rows]
    if base_err:
        violations.append({"field": "openalex_base_call", "expected": "live results", "got": f"error: {base_err}"})
    if scoped_err:
        violations.append({"field": "openalex_scoped_call", "expected": "live results", "got": f"error: {scoped_err}"})

    scoped_in_window = 0
    for r in scoped_rows:
        yr = _year_of(r.get("year"))
        if yr is None:
            continue
        if yr < lo or yr > hi:
            violations.append({"lane": "scoped_date", "reason": f"year {yr} outside {lo}-{hi}", "hit": r})
        else:
            scoped_in_window += 1
    if scoped_rows and scoped_in_window == 0 and not scoped_err:
        violations.append({"lane": "scoped_date", "reason": "no in-window hit (dark lane)", "hit": None})

    base_out = [r for r in base_rows if (_year_of(r.get("year")) or 9999) < lo]
    if base_rows and not base_out and not base_err:
        violations.append({"lane": "base", "reason": f"base returned NO pre-{lo} hit (no-drop proof failed)", "hit": None})

    got = (
        f"scoped filter={filter_str}; scoped hits={len(scoped_rows)} (in-window={scoped_in_window}); "
        f"base hits={len(base_rows)} (pre-{lo}={len(base_out)}, e.g. {[_year_of(r.get('year')) for r in base_out[:3]]})"
    )
    return {
        "case": "openalex_date_scope_live",
        "pass": not violations,
        "expected": f"OpenAlex scoped {lo}-{hi}: ALL scoped works in-window; base retains pre-{lo} works (no-drop)",
        "got": got,
        "violations": violations,
        "capture": capture,
    }


def case_openalex_language_scope_live() -> dict[str, Any]:
    from src.polaris_graph.retrieval.scope_search_lanes import build_openalex_scope_params

    query = "COVID-19 vaccine effectiveness"
    lang = "fr"
    scope = {"user_constraints": {"language": lang}}
    scoped_params = build_openalex_scope_params(scope)  # PG_OPENALEX_SCOPE_FILTER=1 set in main()

    violations: list[dict[str, Any]] = []
    if scoped_params.get("language") != lang:
        violations.append({"field": "openalex_scope_param", "expected": {"language": lang}, "got": scoped_params})

    filter_str = f"language:{scoped_params.get('language', lang)}"
    base_rows, base_err = _openalex_live(query, per_page=50, filter_str="")
    time.sleep(1.0)
    scoped_rows, scoped_err = _openalex_live(query, per_page=50, filter_str=filter_str)

    capture = [{"lane": "base", **r} for r in base_rows] + [{"lane": "scoped_lang", **r} for r in scoped_rows]
    if base_err:
        violations.append({"field": "openalex_base_call", "expected": "live results", "got": f"error: {base_err}"})
    if scoped_err:
        violations.append({"field": "openalex_scoped_call", "expected": "live results", "got": f"error: {scoped_err}"})

    scoped_hits = 0
    for r in scoped_rows:
        wl = (r.get("language") or "").lower()
        if not wl:
            continue  # null language: cannot prove out-of-scope; not a violation
        if wl != lang:
            violations.append({"lane": "scoped_lang", "reason": f"language {wl!r} != {lang!r}", "hit": r})
        else:
            scoped_hits += 1
    if scoped_rows and scoped_hits == 0 and not scoped_err:
        violations.append({"lane": "scoped_lang", "reason": f"no known-{lang} hit (dark lane)", "hit": None})

    base_non_fr = [r for r in base_rows if (r.get("language") or "").lower() not in ("", lang)]
    if base_rows and not base_non_fr and not base_err:
        violations.append({"lane": "base", "reason": f"base returned NO non-{lang} work (no-drop proof failed)", "hit": None})

    got = (
        f"scoped filter={filter_str}; scoped works={len(scoped_rows)} (lang=={lang}: {scoped_hits}); "
        f"base works={len(base_rows)} (non-{lang}={len(base_non_fr)}, e.g. "
        f"{[r.get('language') for r in base_non_fr[:3]]})"
    )
    return {
        "case": "openalex_language_scope_live",
        "pass": not violations,
        "expected": f"OpenAlex scoped language={lang}: ALL scoped works lang=={lang}; base retains non-{lang} works (no-drop)",
        "got": got,
        "violations": violations,
        "capture": capture,
    }


def case_openalex_author_scope_live() -> dict[str, Any]:
    from src.polaris_graph.retrieval.scope_search_lanes import build_openalex_scope_params

    query = "cardiovascular outcomes"
    surname = "Nissen"
    scope = {"scope_constraints": {"named_include": [{"label": surname, "op": "include"}]}}
    scoped_params = build_openalex_scope_params(scope)  # -> {"authors": ["Nissen"]}

    violations: list[dict[str, Any]] = []
    if scoped_params.get("authors") != [surname]:
        violations.append({"field": "openalex_scope_param", "expected": {"authors": [surname]}, "got": scoped_params})

    names = "|".join(scoped_params.get("authors") or [surname])
    filter_str = f"raw_author_name.search:{names}"
    base_rows, base_err = _openalex_live(query, per_page=50, filter_str="")
    time.sleep(1.0)
    scoped_rows, scoped_err = _openalex_live(query, per_page=50, filter_str=filter_str)

    capture = [{"lane": "base", **r} for r in base_rows] + [{"lane": "scoped_author", **r} for r in scoped_rows]
    if base_err:
        violations.append({"field": "openalex_base_call", "expected": "live results", "got": f"error: {base_err}"})
    if scoped_err:
        violations.append({"field": "openalex_scoped_call", "expected": "live results", "got": f"error: {scoped_err}"})

    low = surname.lower()
    scoped_hits = 0
    for r in scoped_rows:
        author_blob = " ".join(r.get("authors") or []).lower()
        if low in author_blob:
            scoped_hits += 1
        else:
            violations.append({"lane": "scoped_author", "reason": f"no author matching {surname!r}", "hit": r})
    if scoped_rows and scoped_hits == 0 and not scoped_err:
        violations.append({"lane": "scoped_author", "reason": f"no work with a {surname!r} author (dark lane)", "hit": None})

    base_without = [r for r in base_rows if low not in " ".join(r.get("authors") or []).lower()]
    if base_rows and not base_without and not base_err:
        violations.append({"lane": "base", "reason": f"base returned ONLY {surname!r}-authored works (no-drop proof failed)", "hit": None})

    got = (
        f"scoped filter={filter_str}; scoped works={len(scoped_rows)} (with {surname}: {scoped_hits}); "
        f"base works={len(base_rows)} (without {surname}: {len(base_without)})"
    )
    return {
        "case": "openalex_author_scope_live",
        "pass": not violations,
        "expected": f"OpenAlex scoped author={surname}: ALL scoped works list {surname}; base retains non-{surname} works (no-drop)",
        "got": got,
        "violations": violations,
        "capture": capture,
    }


def case_serper_scope_reaches_backend_live() -> dict[str, Any]:
    from src.polaris_graph.retrieval.scope_search_lanes import build_serper_scope_params

    query = "diabetes treatment guidelines"
    scope = {
        "user_constraints": {"date_start_iso": "2023-01-01", "date_end_iso": "2025-12-31", "language": "en"},
        "scope_constraints": {"facets": [
            {"facet_id": "jurisdiction:ca", "dimension": "jurisdiction", "op": "include", "strictness": "weight"},
        ]},
    }
    scoped_params = build_serper_scope_params(scope)  # PG_SERPER_SCOPE_FILTER=1 set in main()

    violations: list[dict[str, Any]] = []
    tbs = str(scoped_params.get("tbs", ""))
    if not (tbs.startswith("cdr:1") and "cd_min:" in tbs and "cd_max:" in tbs):
        violations.append({"field": "serper_tbs", "expected": "cdr:1,cd_min:..,cd_max:..", "got": scoped_params.get("tbs")})
    if scoped_params.get("gl") != "ca":
        violations.append({"field": "serper_gl", "expected": "ca", "got": scoped_params.get("gl")})
    if scoped_params.get("hl") != "en":
        violations.append({"field": "serper_hl", "expected": "en", "got": scoped_params.get("hl")})

    base_rows, base_err = _serper_live(query, num=10, scope_params=None)
    time.sleep(1.0)
    scoped_rows, scoped_err = _serper_live(query, num=10, scope_params=scoped_params)

    capture = [{"lane": "base", **r} for r in base_rows] + [{"lane": "scoped", **r} for r in scoped_rows]

    # Serper key must be live (base lane returns hits) and the scoped params must not ERROR the call.
    if base_err or not base_rows:
        violations.append({"field": "serper_base_call", "expected": ">=1 live result", "got": f"error={base_err!r} hits={len(base_rows)}"})
    if scoped_err:
        violations.append({"field": "serper_scoped_call", "expected": "scoped params accepted (no error)", "got": f"error: {scoped_err}"})

    # Where a scoped organic row DOES carry a parseable date, the year must be >= window floor.
    for r in scoped_rows:
        yr = _year_of(r.get("date"))
        if yr is not None and yr < 2023:
            violations.append({"lane": "scoped", "reason": f"dated {yr} < 2023 window floor", "hit": r})

    got = (
        f"scoped params={{tbs:{scoped_params.get('tbs')}, gl:{scoped_params.get('gl')}, hl:{scoped_params.get('hl')}}}; "
        f"base hits={len(base_rows)}; scoped hits={len(scoped_rows)}; scoped_err={scoped_err!r}"
    )
    return {
        "case": "serper_scope_reaches_backend_live",
        "pass": not violations,
        "expected": "Serper scoped tbs/gl(ca)/hl(en) well-formed + accepted live (additive to base); no per-hit date claim (Serper exposes none)",
        "got": got,
        "violations": violations,
        "capture": capture,
    }


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="S1.b RETRIEVE live stress battery (box2)")
    ap.add_argument("--out", default=str(_REPO_ROOT / "outputs" / "retrieve_stress_i1"))
    args = ap.parse_args()

    # Enable the production scope-param builders (default OFF => byte-identical). We call the real
    # builders so the LIVE lanes are fed EXACTLY the params production would send.
    os.environ["PG_S2_SCOPE_FILTER"] = "1"
    os.environ["PG_SERPER_SCOPE_FILTER"] = "1"
    os.environ["PG_OPENALEX_SCOPE_FILTER"] = "1"

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    cases: list[Callable[[], dict[str, Any]]] = [
        case_breadth_explicit_45,
        case_breadth_wide_prompt,
        case_breadth_narrow_prompt,
        case_s2_year_scope_live,
        case_openalex_date_scope_live,
        case_openalex_language_scope_live,
        case_openalex_author_scope_live,
        case_serper_scope_reaches_backend_live,
    ]

    results: list[dict[str, Any]] = []
    breaks: list[dict[str, Any]] = []
    for fn in cases:
        try:
            res = fn()
        except Exception as exc:  # noqa: BLE001 — a raised case is a FAIL, reported verbatim (LAW II)
            res = {
                "case": fn.__name__, "pass": False,
                "expected": "case runs without raising",
                "got": f"EXCEPTION: {type(exc).__name__}: {exc}",
                "violations": [{"reason": f"EXCEPTION: {type(exc).__name__}: {exc}", "hit": None}],
                "capture": [],
            }
        case_dir = out_root / res["case"]
        case_dir.mkdir(parents=True, exist_ok=True)
        with open(case_dir / "capture.jsonl", "w", encoding="utf-8") as fh:
            for row in res.get("capture", []):
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        verdict = {k: v for k, v in res.items() if k != "capture"}
        (case_dir / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        results.append(verdict)
        status = "PASS" if res["pass"] else "FAIL"
        print(f"[CASE {res['case']}] {status} :: {res['got']}")
        if not res["pass"]:
            # Quote the FIRST concrete violation verbatim for the operator (§-1.1).
            first = res["violations"][0] if res["violations"] else {}
            print(f"        VIOLATION: {json.dumps(first, ensure_ascii=False)}")
            breaks.append({
                "case": res["case"],
                "expected": res["expected"],
                "got": res["got"],
                "quoted_evidence": json.dumps(res["violations"][:3], ensure_ascii=False),
            })

    clean = not breaks
    summary = {
        "iter": 1,
        "clean": clean,
        "total_cases": len(cases),
        "passed": sum(1 for r in results if r["pass"]),
        "breaks": breaks,
        "cases": results,
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== RETRIEVE_STRESS_RESULT ===")
    print(json.dumps({"iter": 1, "clean": clean, "total_cases": len(cases), "passed": summary["passed"], "breaks": breaks}, ensure_ascii=False))
    print("=== END ===")
    print(f"[retrieve_stress] summary -> {out_root / 'summary.json'}  clean={clean}")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
