#!/usr/bin/env python3
"""RECENCY — the frontier the citation graph cannot reach, searched BY DATE.  (Sol plan 4, item 3.)

THE GAP THIS CLOSES
───────────────────────────────────────────────────────────────────────────────────────────────────
Our retrieval is BACKWARD: it looks a work up by DOI and walks its references and citers. Sol:

    "'Just search by date' is correct because BACKWARD CITATION EXPANSION SYSTEMATICALLY MISSES RECENT
     WORK: recent papers have not accumulated references or citations."

Our corpus ends in 2023. The generative-AI turn is 2023-2025 and the citation graph literally cannot
reach it — the edges do not exist yet. So this module does the one thing the graph can't: it issues
DIRECT, DATE-WINDOWED queries and SORTS THEM BY DATE, never by citation count.

TWO INDEPENDENT LANES
───────────────────────────────────────────────────────────────────────────────────────────────────
  FOUNDATION — seminal theories, landmark methods, long-run evidence. Found by citation weight /
               relevance, NO date window, and NO recency penalty for age. A 1979 theorem is not stale.
  FRONTIER   — explicit publication-date windows, searched directly and SORTED BY the DATE FIELD,
               never by citation count. For task 72 the frontier begins at the generative-AI boundary
               and sweeps OVERLAPPING bands: since 2023 | last 24 months | last 12 months |
               accepted/online-ahead-of-print | newly-indexed-since-last-run.

WHERE THE INSIGHT LIVES (and where it does NOT)
───────────────────────────────────────────────────────────────────────────────────────────────────
Every window, every boundary date, every per-database date field, and the whole claim->recency policy
live in config/authority/recency_frontier_profile.yaml — DATA. This file contains NO topic gate, NO
regex over a question, and NO domain date. It cannot tell you that AI=2023 or that migraine needs a
trial-completion window; it can only ask the profile. A new domain is a new registry row, never an
edit here (LAW: generality is a DATA edit).

RECENCY IS CLAIM-SPECIFIC
───────────────────────────────────────────────────────────────────────────────────────────────────
The claim's `claim_kind` (carried on the contract, not sniffed here) selects a policy row:
  * a foundational theory  -> foundation lane only, no age penalty;
  * a current adoption rate -> frontier, keyed on publication/online/indexed dates;
  * a clinical conclusion  -> frontier keyed on publication + trial-completion + registry + results
                              dates, PLUS a corrections/retractions pull;
  * a current statute      -> frontier keyed on the EFFECTIVE text and SUBSEQUENT TREATMENT — the
                              newest commentary is explicitly NOT a substitute for the in-force law;
  * a thin-evidence claim  -> a date-windowed search that returns nothing licenses "the recent
                              literature does not settle this", and NEVER "the field proves no effect".

DATE FIELDS ARE NOT INTERCHANGEABLE
───────────────────────────────────────────────────────────────────────────────────────────────────
publication vs online vs accepted vs posted vs registration vs indexed vs updated vs trial-completion
are SEPARATE fields (Crossref exposes them as separate filters). The registry maps each database to
ONLY the date-types it truly exposes; a band that keys on a field a database lacks is emitted as
UNSUPPORTED with a reason — it is never silently re-pointed at a different date.

THE PROBE CANNOT CONCLUDE
───────────────────────────────────────────────────────────────────────────────────────────────────
Every network touch goes through acquisition.Acquirer, which emits OBSERVATIONS, never statuses. A
frontier band that returns nothing becomes the sentence "no recent eligible evidence located" ONLY
when event_ledger.derive_coverage_status reduces the cell to SEARCHED_NONE (the adapters answered and
were empty). A THROTTLED / BLOCKED band is SEARCH_FAILED and licenses NO absence — a fact about our
request rate must never be written to disk as a fact about the recent literature.

    python3 scripts/recency.py            # build + print the bands for task 72 and a clinical question
    python3 scripts/recency.py --probe    # additionally run the frontier bands live (uses Acquirer)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import MAILTO, Acquirer, open_ledger          # noqa: E402  THE ONE DOOR TO THE NETWORK
from event_ledger import SEARCHED_NONE, derive_coverage_status  # noqa: E402

DEFAULT_PROFILE = ROOT / 'config' / 'authority' / 'recency_frontier_profile.yaml'


class RecencyProfileError(RuntimeError):
    """A missing / empty / malformed recency profile. FAIL LOUD — never a silent default (LAW II)."""


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# THE PROFILE — versioned DATA, loaded fail-loud
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def load_profile(path: str | Path | None = None) -> dict:
    """Load + validate the recency profile. Overridable via POLARIS_RECENCY_PROFILE (tests, LAW VI)."""
    p = Path(path or os.getenv('POLARIS_RECENCY_PROFILE') or DEFAULT_PROFILE)
    if not p.exists() or p.stat().st_size == 0:
        raise RecencyProfileError(f'recency profile missing/empty: {p}')
    try:
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
    except yaml.YAMLError as e:
        raise RecencyProfileError(f'recency profile unparseable: {p}: {e}') from e
    if not isinstance(data, dict):
        raise RecencyProfileError(f'recency profile is not a mapping: {p}')
    for k in ('bands', 'frontier_boundaries', 'databases', 'claim_recency_policy'):
        if not data.get(k):
            raise RecencyProfileError(f'recency profile missing required section {k!r}: {p}')
    return data


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# DATES — small pure helpers
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _as_date(v: Any) -> dt.date:
    """Parse 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD' (or pass a date through)."""
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise RecencyProfileError(f'unparseable date {v!r}')


def _minus_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 - months
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day to the last valid day of the target month
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30,
            31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# THE CLAIM-SPECIFIC ASK
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class RecencyNeed:
    """What a single claim needs from recency. Derived from the research contract / claim — NOT sniffed
    from the question by this module. `claim_kind` and `boundary` are KEYS into the profile."""
    claim_kind: str
    subject_terms: list[str]
    as_of: dt.date
    boundary: str | None = None            # key into profile['frontier_boundaries']
    last_run: dt.date | None = None        # anchors the 'newly-indexed-since-last-run' band
    unit: str = ''                         # ledger unit / coverage-cell name for the probe
    target_id: str = ''                    # legal: the authority whose subsequent treatment we track

    def query_string(self) -> str:
        return ' '.join(t for t in self.subject_terms if t).strip()


@dataclass
class FrontierBand:
    key: str
    label: str
    date_types: list[str]
    since: dt.date | None
    until: dt.date | None
    note: str = ''

    def window_prose(self) -> str:
        if self.since and self.until:
            return f'{self.since.isoformat()} .. {self.until.isoformat()}'
        if self.since:
            return f'since {self.since.isoformat()}'
        return 'open window'


@dataclass
class DatabaseQuery:
    database: str
    band: str
    date_type: str
    supported: bool
    url: str = ''
    date_field: str = ''
    sort: str | None = None
    note: str = ''


@dataclass
class FoundationQuery:
    database: str
    url: str
    sort: str
    note: str = ''


@dataclass
class RecencyPlan:
    need: RecencyNeed
    policy: dict
    lanes: list[str]
    foundation: list[FoundationQuery]
    frontier_bands: list[FrontierBand]
    frontier_queries: list[DatabaseQuery]
    content_filters: list[str]
    on_empty_template: str


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# LANE PLANNING
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _policy_for(need: RecencyNeed, profile: dict) -> dict:
    pol = profile['claim_recency_policy'].get(need.claim_kind)
    if not pol:
        known = ', '.join(sorted(profile['claim_recency_policy']))
        raise RecencyProfileError(
            f'unknown claim_kind {need.claim_kind!r}; the profile defines: {known}. '
            f'Add a policy ROW — do not special-case it in code.')
    if pol.get('boundary_required') and not need.boundary:
        raise RecencyProfileError(
            f'claim_kind {need.claim_kind!r} requires a frontier boundary, but the need names none. '
            f'The contract must supply one of: {", ".join(sorted(profile["frontier_boundaries"]))}.')
    if need.boundary and need.boundary not in profile['frontier_boundaries']:
        raise RecencyProfileError(f'unknown frontier boundary {need.boundary!r}')
    return pol


def resolve_bands(need: RecencyNeed, profile: dict) -> list[FrontierBand]:
    """Turn the profile's RELATIVE bands into CONCRETE date windows for THIS claim.

    A band runs only if it keys on a date-type this claim's policy asks for (claim-specific). Any
    policy date-type that no named band covers (a clinical trial-completion window, a legal
    effective-date window) gets a synthesized default band from the profile — still data, never a
    hardcoded window here.
    """
    pol = _policy_for(need, profile)
    wanted: list[str] = list(pol.get('date_types') or [])
    if not wanted:
        return []                                     # foundation-only claim: no frontier bands at all

    boundary_since = (_as_date(profile['frontier_boundaries'][need.boundary]['since'])
                      if need.boundary else None)

    def _window(kind: str, months: int | None) -> tuple[dt.date | None, dt.date | None, str]:
        if kind == 'since_boundary':
            if not boundary_since:
                return None, None, 'no frontier boundary named; band skipped'
            return boundary_since, need.as_of, ''
        if kind == 'relative_months':
            return _minus_months(need.as_of, int(months or 0)), need.as_of, ''
        if kind == 'since_last_run':
            if not need.last_run:
                return None, None, 'no prior run recorded; incremental band skipped'
            return need.last_run, need.as_of, ''
        return None, None, f'unknown window kind {kind!r}'

    out: list[FrontierBand] = []
    covered: set[str] = set()
    for b in profile['bands']:
        types = [t for t in (b.get('date_types') or []) if t in wanted]
        if not types:
            continue
        w = b.get('window') or {}
        since, until, why = _window(w.get('kind', ''), w.get('months'))
        if since is None and until is None and why:
            out.append(FrontierBand(b['key'], b['label'], types, None, None, note=why))
            covered.update(types)
            continue
        out.append(FrontierBand(b['key'], b['label'], types, since, until))
        covered.update(types)

    # synthesize a default window for any wanted date-type no named band covered
    missing = [t for t in wanted if t not in covered]
    if missing:
        if boundary_since:
            since, until = boundary_since, need.as_of
            lbl = 'since the frontier boundary (default window)'
        else:
            months = int(profile.get('default_frontier_months', 24))
            since, until = _minus_months(need.as_of, months), need.as_of
            lbl = f'last {months} months (default window)'
        out.append(FrontierBand('frontier_default', lbl, missing, since, until,
                                note='claim date-types not covered by a named band'))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# PER-DATABASE URL DRIVERS — the code knows each API's URL GRAMMAR; the DATE FIELD is read from data
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _d_iso(d: dt.date) -> str:      return d.isoformat()
def _d_slash(d: dt.date) -> str:    return d.strftime('%Y/%m/%d')
def _d_stamp(d: dt.date, end: bool) -> str:  return d.strftime('%Y%m%d') + ('2359' if end else '0000')


def _build_crossref(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    filt = [f"{fields['from']}:{_d_iso(since)}"]
    if until:
        filt.append(f"{fields['until']}:{_d_iso(until)}")
    params = {'query': q, 'filter': ','.join(filt), 'sort': fields['sort'], 'order': 'desc',
              'rows': db.get('rows', 40)}
    if db.get('mailto'):
        params['mailto'] = MAILTO
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['from'], fields['sort']


def _build_openalex(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    filt = [f"{fields['from']}:{_d_iso(since)}"]
    if until:
        filt.append(f"{fields['until']}:{_d_iso(until)}")
    filt.append(f'default.search:{q}')
    params = {'filter': ','.join(filt), 'per-page': db.get('rows', 40)}
    if fields.get('sort'):
        params['sort'] = fields['sort']
    if db.get('mailto'):
        params['mailto'] = MAILTO
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['from'], fields.get('sort')


def _build_pubmed(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    term = q + (f' {content_frag}' if content_frag else '')
    params = {'db': 'pubmed', 'term': term, 'datetype': fields['datetype'],
              'mindate': _d_slash(since), 'maxdate': _d_slash(until or since),
              'sort': fields['sort'], 'retmax': db.get('rows', 40), 'retmode': 'json'}
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['datetype'], fields['sort']


def _build_europepmc(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    rng = f"{fields['field']}:[{_d_iso(since)} TO {_d_iso(until or since)}]"
    query = f'{q} AND ({rng})' + (f' {content_frag}' if content_frag else '')
    params = {'query': query, 'sort': fields['sort'], 'format': 'json',
              'pageSize': db.get('rows', 40)}
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['field'], fields['sort']


def _build_arxiv(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    rng = f"{fields['field']}:[{_d_stamp(since, False)} TO {_d_stamp(until or since, True)}]"
    sq = f'(all:{q}) AND {rng}'
    params = {'search_query': sq, 'sortBy': fields['sort'], 'sortOrder': 'descending',
              'max_results': db.get('rows', 40)}
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['field'], fields['sort']


def _build_clinicaltrials(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    rng = f"RANGE[{_d_iso(since)},{_d_iso(until) if until else 'MAX'}]"
    params = {'query.term': q, 'filter.advanced': f"AREA[{fields['area']}]{rng}",
              'sort': fields['sort'], 'pageSize': db.get('rows', 40)}
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['area'], fields['sort']


def _build_courtlistener(db, fields, q, since, until, content_frag, target_id='') -> tuple[str, str, str | None]:
    if fields.get('mode') == 'cites':
        # SUBSEQUENT TREATMENT: later opinions that CITE the target, decided after the window start.
        query = f'cites:({target_id or "<TARGET_OPINION_ID>"}) {q}'.strip()
    else:
        query = q
    params = {'q': query, fields['from']: _d_iso(since), 'order_by': fields['sort'], 'type': 'o'}
    if until:
        params[fields['until']] = _d_iso(until)
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields.get('from', 'filed_after'), fields['sort']


def _build_govinfo(db, fields, q, since, until, content_frag) -> tuple[str, str, str | None]:
    # A statute has no publication window that answers "what does the law say now". Return the
    # in-force text ordered by currency; this is NOT the newest commentary. (The govinfo api_key is
    # attached at call time by the Acquirer, not printed into this URL.)
    params = {'query': q, 'offsetMark': '*', 'pageSize': db.get('rows', 40)}
    return f"{db['base']}?{urllib.parse.urlencode(params)}", fields['currency'], fields['sort']


_DRIVERS = {
    'crossref_filter': _build_crossref,
    'openalex_filter': _build_openalex,
    'pubmed_eutils': _build_pubmed,
    'europepmc_lucene': _build_europepmc,
    'arxiv_range': _build_arxiv,
    'clinicaltrials_area': _build_clinicaltrials,
    'courtlistener_filed': _build_courtlistener,
    'govinfo_currency': _build_govinfo,
    'semanticscholar_bulk': None,   # handled inline (its param shape differs)
}


def _build_one(db_name: str, db: dict, date_type: str, band: FrontierBand, need: RecencyNeed,
               content_frag: str) -> DatabaseQuery:
    fields = (db.get('date_fields') or {}).get(date_type)
    if not fields:
        exposes = ', '.join(sorted((db.get('date_fields') or {}))) or '(none)'
        return DatabaseQuery(
            db_name, band.key, date_type, supported=False,
            note=f'{db_name} does not expose a {date_type!r} date field (it exposes: {exposes}); '
                 f'NOT substituting another date — the fields are not interchangeable')
    if band.since is None:
        return DatabaseQuery(db_name, band.key, date_type, supported=False,
                             note=band.note or 'no window')

    style = db['style']
    q = need.query_string()
    since, until = band.since, band.until

    if style == 'semanticscholar_bulk':
        yr = f'{since.year}:{until.year}' if until else f'{since.year}:'
        params = {'query': q, fields['from_year']: yr, 'sort': fields['sort'],
                  'fields': 'title,year,publicationDate,externalIds'}
        url = f"{db['base']}?{urllib.parse.urlencode(params)}"
        return DatabaseQuery(db_name, band.key, date_type, True, url,
                             fields['from_year'], fields['sort'],
                             note='bulk endpoint only — the plain /search endpoint sorts by relevance/'
                                  'citation and must not be used for a frontier band')

    driver = _DRIVERS.get(style)
    if driver is None:
        return DatabaseQuery(db_name, band.key, date_type, False, note=f'no driver for style {style!r}')
    if style == 'courtlistener_filed':
        url, dfield, sort = driver(db, fields, q, since, until, content_frag, need.target_id)
    else:
        url, dfield, sort = driver(db, fields, q, since, until, content_frag)

    # THE FRONTIER LANE REFUSES CITATION SORT. This is the invariant, enforced against the data.
    note = ''
    cit = db.get('citation_sort')
    if sort and cit and str(sort).split(':')[0] == str(cit).split(':')[0]:
        return DatabaseQuery(db_name, band.key, date_type, False,
                             note=f'REFUSED: {db_name} sort {sort!r} is the citation sort — the '
                                  f'frontier lane sorts by date, never by citation count')
    if sort is None:
        note = (f'{db_name} filters on {dfield!r} but cannot sort by it; results come in the API date '
                f'order (still a date order, never citation order)')
    return DatabaseQuery(db_name, band.key, date_type, True, url, dfield, sort, note=note)


def build_frontier_queries(need: RecencyNeed, profile: dict,
                           bands: list[FrontierBand] | None = None) -> list[DatabaseQuery]:
    """One concrete query per (band x date-type x database), using each database's CORRECT date field.

    A database that lacks a band's date-type yields an UNSUPPORTED row with a reason (never a silent
    substitution). A sort that equals the database's citation sort is REFUSED outright.
    """
    pol = _policy_for(need, profile)
    bands = bands if bands is not None else resolve_bands(need, profile)
    wanted = set(pol.get('date_types') or [])
    dbs: list[str] = list(pol.get('databases') or [])
    want_content = list(pol.get('content_filters') or [])

    out: list[DatabaseQuery] = []
    for band in bands:
        for date_type in band.date_types:
            if date_type not in wanted:
                continue
            for db_name in dbs:
                db = profile['databases'].get(db_name)
                if not db:
                    out.append(DatabaseQuery(db_name, band.key, date_type, False,
                                             note=f'no database row {db_name!r} in profile'))
                    continue
                # The MAIN evidence query carries NO content fragment — ANDing corrections/retractions
                # into it would narrow the recent-trials search to only retractions.
                out.append(_build_one(db_name, db, date_type, band, need, ''))

    # DEDICATED content-class sweeps (e.g. corrections/retractions). Run over the SAME publication
    # window as a SEPARATE query, so the claim's "also pull corrections/retractions" AUGMENTS the
    # evidence base rather than shrinking the main search to it. (A superseded clinical conclusion must
    # be catchable; that is what this sweep is for.)
    for c in want_content:
        for band in bands:
            if band.since is None or 'published' not in [t for t in band.date_types if t in wanted]:
                continue
            for db_name in dbs:
                db = profile['databases'].get(db_name) or {}
                frag = (db.get('content_filters') or {}).get(c)
                if not frag:
                    continue
                q = _build_one(db_name, db, 'published', band, need, frag)
                q.date_type = f'published|{c}'
                if q.supported:
                    q.note = (f'dedicated {c} sweep over the same window'
                              + (f'; {q.note}' if q.note else ''))
                out.append(q)
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# FOUNDATION LANE — no date window, no age penalty
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def build_foundation_queries(need: RecencyNeed, profile: dict) -> list[FoundationQuery]:
    """Landmark discovery. NO date filter, sorted by citation weight / relevance. Age is NOT penalized.

    Only runs when the claim's policy includes the foundation lane. Note this is the ONE place a
    citation sort is CORRECT — a landmark IS the highly-cited work — which is exactly why the frontier
    lane, whose whole job is to find work that has not yet BEEN cited, must never use it.
    """
    pol = _policy_for(need, profile)
    if 'foundation' not in (pol.get('lanes') or []):
        return []
    q = need.query_string()
    out: list[FoundationQuery] = []
    for db_name in (pol.get('databases') or []):
        db = profile['databases'].get(db_name) or {}
        style = db.get('style', '')
        cit = db.get('citation_sort')
        if style == 'crossref_filter':
            sort = cit or 'relevance'
            url = f"{db['base']}?" + urllib.parse.urlencode(
                {'query': q, 'sort': sort, 'order': 'desc', 'rows': db.get('rows', 40),
                 **({'mailto': MAILTO} if db.get('mailto') else {})})
        elif style == 'openalex_filter':
            sort = f'{cit}:desc' if cit else 'relevance_score:desc'
            url = f"{db['base']}?" + urllib.parse.urlencode(
                {'filter': f'default.search:{q}', 'sort': sort, 'per-page': db.get('rows', 40),
                 **({'mailto': MAILTO} if db.get('mailto') else {})})
        elif style == 'semanticscholar_bulk':
            sort = cit or 'relevance'
            url = f"{db['base']}?" + urllib.parse.urlencode(
                {'query': q, 'sort': sort, 'fields': 'title,year,citationCount,externalIds'})
        else:
            # a non-scholarly backend (a trials registry, a court API) is not a foundation source
            continue
        out.append(FoundationQuery(db_name, url, sort,
                                   note='no date window; age carries no penalty (foundation lane)'))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# THE PLAN
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def plan(need: RecencyNeed, profile: dict | None = None) -> RecencyPlan:
    profile = profile if profile is not None else load_profile()
    pol = _policy_for(need, profile)
    bands = resolve_bands(need, profile)
    on_empty = (pol.get('on_empty') or
                'no recent eligible evidence located in {window}; a scoped absence, not a disproof')
    return RecencyPlan(
        need=need, policy=pol, lanes=list(pol.get('lanes') or []),
        foundation=build_foundation_queries(need, profile),
        frontier_bands=bands,
        frontier_queries=build_frontier_queries(need, profile, bands),
        content_filters=list(pol.get('content_filters') or []),
        on_empty_template=on_empty)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# THE PROBE — uses acquisition.Acquirer and CANNOT conclude
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

class FrontierProbe:
    """Runs the frontier bands through THE ONE DOOR (acquisition.Acquirer). It records observations and
    defers every conclusion to the ledger's reducer — it never reads a None as 'no recent evidence'."""

    def __init__(self, acq: Acquirer, profile: dict):
        self.acq = acq
        self.profile = profile

    def run(self, plan_: RecencyPlan, *, max_queries: int | None = None) -> dict:
        """Execute the supported frontier queries. Returns a per-band summary. NOTHING here concludes
        absence: a band that returns zero results emits NO candidate, so the reducer can later see an
        adequately-routed, empty cell (SEARCHED_NONE) — while a THROTTLED band stays SEARCH_FAILED."""
        unit = plan_.need.unit or f'recency:{plan_.need.claim_kind}'
        supported = [q for q in plan_.frontier_queries if q.supported]
        if max_queries:
            supported = supported[:max_queries]
        # ROUTE_PLANNED names the adapters we are ABOUT to try, so route completion is meaningful.
        adapters = [f'{q.database}:{q.band}:{q.date_type}' for q in supported]
        self.acq.plan_route(unit, adapters, lane='frontier', claim_kind=plan_.need.claim_kind)
        results = []
        for q in supported:
            adapter = f'{q.database}:{q.band}:{q.date_type}'
            resp, body = self.acq.get_json(unit, adapter, q.url)
            n = _result_count(self.profile['databases'].get(q.database, {}), body) if resp.ok else None
            if resp.ok and n:
                # a real hit becomes a CANDIDATE — evidence identification, still not a conclusion
                self.acq.candidate(unit, adapter, q.url, n_results=n, date_type=q.date_type,
                                   band=q.band, sort=q.sort)
            results.append({'adapter': adapter, 'ok': resp.ok, 'outcome': resp.outcome,
                            'http_status': resp.http_status, 'n_results': n})
        return {'unit': unit, 'n_queries': len(supported), 'results': results}

    def absence_is_licensed(self, need: RecencyNeed, on_empty_template: str) -> tuple[bool, str]:
        """Ask THE REDUCER whether this cell licenses a scoped-absence sentence. Only SEARCHED_NONE
        does. THROTTLED/BLOCKED reduce to SEARCH_FAILED and license nothing — the acquisition invariant
        carried all the way to the sentence."""
        unit = need.unit or f'recency:{need.claim_kind}'
        status, info = derive_coverage_status(self.acq.ledger, unit)
        if status == SEARCHED_NONE:
            return True, on_empty_template
        return False, (f'no absence sentence: coverage is {status} — {info.get("reason", "")}. '
                       f'A fact about our search is not a fact about the recent literature.')


def _result_count(db: dict, body: Any) -> int:
    """Read the hit count by walking the database's DATA-declared `count_path` through the JSON body.

    There is NO per-source branch here: a new database contributes its own count_path in the profile
    and the probe reads it. This is only ever used to decide whether to emit a CANDIDATE; it is never
    the basis of an absence conclusion — that is the reducer's job, over the ledger."""
    path = (db or {}).get('count_path')
    if not path or not isinstance(body, (dict, list)):
        return 0
    cur: Any = body
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return 0
    try:
        return int(cur)
    except (TypeError, ValueError):
        return 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# DEMO / __main__  —  build the bands and PRINT them
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _print_plan(title: str, need: RecencyNeed, profile: dict) -> RecencyPlan:
    p = plan(need, profile)
    print('\n' + '=' * 100)
    print(title)
    print('=' * 100)
    print(f'  claim_kind : {need.claim_kind}   lanes: {", ".join(p.lanes)}   '
          f'penalize_age: {p.policy.get("penalize_age")}')
    if need.boundary:
        b = profile['frontier_boundaries'][need.boundary]
        print(f'  boundary   : {need.boundary} = {b["since"]}  ({b["label"]})')
    print(f'  as_of      : {need.as_of.isoformat()}'
          + (f'   last_run: {need.last_run.isoformat()}' if need.last_run else ''))
    print(f'  terms      : {need.query_string()}')
    if p.content_filters:
        print(f'  content    : also pulls {", ".join(p.content_filters)}')

    if 'foundation' in p.lanes:
        print('\n  FOUNDATION LANE  (no date window; age NOT penalized; citation/relevance sort is correct here)')
        for fq in p.foundation:
            print(f'    - {fq.database:16s} sort={fq.sort}')
            print(f'        {fq.url}')

    if 'frontier' in p.lanes:
        print('\n  FRONTIER LANE  (direct date windows, SORTED BY DATE, never by citation count)')
        print('    overlapping bands:')
        for band in p.frontier_bands:
            tag = f'  [{band.note}]' if band.note else ''
            print(f'      * {band.key:30s} {band.label:52s} {band.window_prose()}{tag}')
            print(f'          keys on date-type(s): {", ".join(band.date_types)}')
        print('\n    concrete queries (by band):')
        cur = None
        for q in p.frontier_queries:
            if q.band != cur:
                cur = q.band
                print(f'      --- band: {cur} ---')
            if q.supported:
                print(f'        [{q.database}/{q.date_type}] date_field={q.date_field} sort={q.sort}')
                print(f'            {q.url}')
                if q.note:
                    print(f'            note: {q.note}')
            else:
                print(f'        [{q.database}/{q.date_type}] UNSUPPORTED — {q.note}')

    print('\n  THIN-EVIDENCE BEHAVIOUR (a band that ADEQUATELY returns nothing):')
    print(f'    -> "{p.on_empty_template.format(window="the searched window")}"')
    print('    (emitted ONLY when the ledger reduces the cell to SEARCHED_NONE; a THROTTLED/BLOCKED')
    print('     band is SEARCH_FAILED and licenses no absence — the acquisition invariant, carried through.)')
    return p


def _demo(profile: dict, as_of: dt.date, run_probe: bool) -> None:
    last_run = _minus_months(as_of, 6)

    # ── TASK 72: AI's restructuring impact on the labor market — a CURRENT-STATE claim. ──
    # claim_kind + boundary come from the contract, not from a regex here. The generative-AI turn is a
    # DATA row (frontier_boundaries.generative_ai_turn); the code never learns that AI began in 2023.
    task72 = RecencyNeed(
        claim_kind='current_adoption_rate',
        subject_terms=['artificial intelligence', 'labor market', 'employment', 'automation',
                       'Fourth Industrial Revolution', 'generative AI'],
        as_of=as_of, boundary='generative_ai_turn', last_run=last_run,
        unit='task72:ai_labor:frontier')
    p72 = _print_plan('TASK 72  —  literature review: AI restructuring of the labor market', task72, profile)

    # ── CLINICAL: is high-dose aspirin effective for migraine in adults? (benchmark Q01) ──
    clinical = RecencyNeed(
        claim_kind='clinical_conclusion',
        subject_terms=['high-dose aspirin', 'migraine', 'adults'],
        as_of=as_of, boundary=None, last_run=last_run,
        unit='clinical:aspirin_migraine:frontier')
    _print_plan('CLINICAL  —  high-dose aspirin for migraine in adults (publication + trial-completion '
                '+ registry + corrections/retractions)', clinical, profile)

    # ── LEGAL (generality is not optional): current EFFECTIVE text + subsequent treatment. ──
    legal = RecencyNeed(
        claim_kind='statute_current_text',
        subject_terms=['Section 230', 'Communications Decency Act', 'platform liability'],
        as_of=as_of, boundary=None, last_run=last_run,
        unit='legal:section230:frontier', target_id='')
    _print_plan('LEGAL  —  current text of a statute + how it has since been treated (NOT the newest '
                'commentary)', legal, profile)

    # ── THIN-EVIDENCE claim kind (a claim where "does not settle this" is the correct PASS). ──
    thin = RecencyNeed(
        claim_kind='thin_evidence_current',
        subject_terms=['tirzepatide', 'Parkinson disease', 'motor outcomes'],
        as_of=as_of, boundary=None, last_run=last_run,
        unit='thin:tirzepatide_parkinsons:frontier')
    _print_plan('THIN-EVIDENCE  —  a question the recent literature may simply not settle', thin, profile)

    if run_probe:
        print('\n' + '#' * 100)
        print('# LIVE FRONTIER PROBE (task 72) — through acquisition.Acquirer; it records, it never concludes')
        print('#' * 100)
        acq = Acquirer('recency', ledger=open_ledger())
        probe = FrontierProbe(acq, profile)
        summary = probe.run(p72, max_queries=3)
        print(json.dumps(summary, indent=1, default=str))
        licensed, sentence = probe.absence_is_licensed(task72, p72.on_empty_template)
        print(f'\n  absence licensed? {licensed}')
        print(f'  -> {sentence.format(window="since 2023")}' if licensed else f'  -> {sentence}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default=None, help='override the recency profile path')
    ap.add_argument('--as-of', default=None, help='run date YYYY-MM-DD (default: today)')
    ap.add_argument('--probe', action='store_true',
                    help='additionally run the task-72 frontier bands LIVE via acquisition.Acquirer')
    a = ap.parse_args(argv)

    profile = load_profile(a.profile)
    as_of = _as_date(a.as_of) if a.as_of else dt.date.today()
    print(f'recency profile: schema {profile.get("schema_version")}   as_of={as_of.isoformat()}')
    _demo(profile, as_of, a.probe)
    print('\n' + '-' * 100)
    print('BUILT: two lanes (FOUNDATION: no age penalty; FRONTIER: date-windowed, date-sorted, never '
          'citation-sorted).')
    print('ALL windows / boundaries / date-fields / claim policy live in '
          'config/authority/recency_frontier_profile.yaml — a new domain is a DATA row, not a code edit.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
