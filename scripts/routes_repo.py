#!/usr/bin/env python3
"""ROUTES_REPO — THE THREE REPOSITORY AGGREGATORS: CORE, OpenAIRE Graph v3, Zenodo.

    Sol V9 §1: "Repository adapters only discover DocumentCandidate records."
    Sol V9 §2: the three biggest unbuilt lanes. Gross forecast 60-140 / 45-110 / 5-20.

WHAT AN ADAPTER IN HERE IS ALLOWED TO SAY

  It may say: I ASKED THIS BACKEND THIS EXACT QUESTION, AND IT HANDED ME THESE URLS.

  It may not say: this is the full text, this is the version of record, this is the same work, this is
  admissible, there is no free copy. Not one of those sentences is expressible through this module's
  API, and that is not a convention — `DocumentCandidate` has no field to hold them, `Ledger.emit`
  rejects the words, and the reducers that DO decide read the BYTES, which an adapter never touches.

  So the strongest thing that can be wrong here is a BAD LEAD. A bad lead is fetched, hashed, profiled,
  and thrown out by a reducer. A bad CONCLUSION is a citation in the report.

THE THREE SILENT FAILURES THAT ARE ALREADY REAL, PROBED LIVE ON 2026-07-14

  1. CORE RETURNS 401 (`api.core.ac.uk/v3/search/works`, key from CORE_API_KEY in .env).
     The entire lane's largest forecast — 60-140 documents — is behind a credential that our own
     configuration has and the server rejects. THE ONLY WRONG MOVE IS TO CALL THAT AN ABSENCE.
     `preflight()` marks the route UNAVAILABLE and `resolve()` refuses to run it; the 401 lands on the
     ledger as BLOCKED, which `source_router.classify_discovery_outcome` reduces to ACCESS_DENIED, and
     `licenses_absence()` refuses to license "we did not locate an accessible copy" while one is in the
     set. The literature is UNEXAMINED. It is not empty. Those are different sentences and this module
     can only write the second one by first fixing the key.

  2. ZENODO'S CONCEPT DOI SILENTLY RESOLVES TO A DIFFERENT WORK'S DOI.
     `GET /api/records/1215934` — the CONCEPT record id — returns HTTP 200 and a record whose `doi` is
     `10.5281/zenodo.1424505`. We asked for one identifier and were handed another, with a 200 and no
     warning. So this module NEVER dereferences a concept record id, queries `conceptdoi:` as its own
     fielded probe, and when the version DOI comes back it records the SUBSTITUTION as an observation
     on the candidate — the concept DOI is never allowed to stand as the version's identity.

  3. ZENODO'S RELATION SEARCH RETURNS WORKS THAT MERELY *CITE* THE DOI.
     `related.identifier:"10.1038/s41586-021-03819-2"` (AlphaFold) returns `10.5281/zenodo.7865494` —
     a training-materials deposit whose relation is `cites`, carrying `Event metadata.pdf` and `Index
     of training materials.pdf`. Admit it and those two PDFs are filed as the AlphaFold paper. The
     relation whitelist in `source_routes.yaml` (`resolver.relations.identity`) is the only thing
     between us and that, and it is DATA, so it can be audited without reading Python.

  And one more the shape of the code forbids outright: A RECORD'S FILES ARE NEVER CONCATENATED. Each
  file is its own candidate with its own bytes and its own hash. Joining a manuscript to its appendix
  and its README manufactures a document that never existed — and it would profile as complete.

WHY THERE IS NO REPOSITORY'S NAME BELOW THE DATA LAYER

  Sol V9 §6: "Adding GovInfo, EUR-Lex, CourtListener, or another repository should normally mean adding
  ROWS." Endpoints, auth profiles, query forms, response selectors, artifact-type declarations,
  relation whitelists and rate budgets are all rows in `config/source_routes.yaml`. What is code here is
  the three GENERIC things a repository resolver does: fill an exact-identifier query, walk a response
  for candidate URLs, and prove the record it walked is about the identifier we asked for. A fourth
  repository of the same wire protocol is a row and zero lines of Python.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import source_router as SR                                                   # noqa: E402
from acquisition import (                                                    # noqa: E402
    ACCESS_DENIED, AUTH_FAILED, Acquirer, BACKEND_FAILED, DEFERRED, DocumentCandidate,
    NEVER_AN_ABSENCE, NOT_INDEXED, RESPONDED, Response, ResolveContext, THROTTLED,
)
from event_ledger import EventKind                                           # noqa: E402

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE ROUTE STATE VOCABULARY — every word is about US OR THE BACKEND. None is about the literature.
#
# It is acquisition's transport vocabulary, REUSED, not restated: AUTH_FAILED / ACCESS_DENIED /
# THROTTLED / BACKEND_FAILED / DEFERRED all mean here exactly what they mean at the socket, and
# `NEVER_AN_ABSENCE` is imported rather than re-typed — a second copy of that list is a second place
# for one of these words to quietly go missing from it.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#: The backend answered our exact-identifier question. ONLY this state can support "this backend does
#: not hold a copy" downstream — and even then only through the ledger reducer, never from here.
ANSWERED    = 'ANSWERED'
#: We never asked: no credential configured, no resolver row, or preflight already found the key
#: rejected. THE ROUTE DID NOT LOOK.
UNAVAILABLE = 'UNAVAILABLE'

#: The states in which this route HAS NOT LOOKED AT THE LITERATURE. Reading absence off any of them is
#: the founding bug of this codebase, restated at the route layer.
NOT_AN_OBSERVATION_OF_THE_WORLD = frozenset(set(NEVER_AN_ABSENCE) | {UNAVAILABLE})


@dataclass(frozen=True)
class RouteResult:
    """What ONE route did for ONE work. Candidates are LEADS; `state` is about the route, not the world."""
    adapter_id: str
    work_id: str
    state: str
    candidates: tuple[DocumentCandidate, ...] = ()
    basis: str = ''
    #: UNIQUE records the backend showed us (a record returned by two query forms is ONE record — a
    #: ladder that counts it twice reports a coverage it does not have).
    records_seen: int = 0
    #: the HTTP status behind a non-ANSWERED state, so a skipped unit can carry the real 401
    http_status: int | None = None
    #: every record/URL we THREW AWAY and why — the audit trail for a whitelist that is doing real work
    rejected: tuple[dict, ...] = ()
    #: per-candidate observations too specific for the schema (file size, checksum, declared type)
    candidate_obs: dict = field(default_factory=dict)
    #: OAI identifiers harvested for the institutional OAI-PMH lane (Sol V9 §2)
    oai_ids: tuple[str, ...] = ()

    @property
    def answered(self) -> bool:
        """Did this backend actually examine our question? If False, NOTHING here is evidence of absence."""
        return self.state == ANSWERED


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CREDENTIALS — read, never logged
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _dotenv(name: str) -> str:
    """The operator keeps keys in `.env`, not the process environment. Read it; never emit it."""
    p = ROOT / '.env'
    if not p.exists():
        return ''
    for line in p.read_text(errors='ignore').splitlines():
        if line.startswith(f'{name}='):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def credential(route: SR.Route) -> str:
    auth = (route.resolver or {}).get('auth') or {}
    env = auth.get('key_env') or ''
    return (os.environ.get(env, '') or _dotenv(env)) if env else ''


def _auth_headers(route: SR.Route) -> dict:
    auth = (route.resolver or {}).get('auth') or {}
    key = credential(route)
    if not key or auth.get('scheme') != 'bearer':
        return {}
    return {'Authorization': f'Bearer {key}'}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE GENERIC SELECTOR ENGINE — dotted paths with `[]`. It knows no repository's field names.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def pluck(obj: Any, path: str) -> list:
    """Every value at `path`. `a.b[].c` walks INTO the list at `b`. Missing -> [] (never an exception,
    and never a claim that the field's absence means anything)."""
    cur: list = [obj]
    for part in (path or '').split('.'):
        if not part:
            continue
        explode = part.endswith('[]')
        key = part[:-2] if explode else part
        nxt: list = []
        for o in cur:
            if isinstance(o, dict):
                v = o.get(key)
            else:
                continue
            if v is None:
                continue
            if explode and isinstance(v, list):
                nxt.extend(v)
            else:
                nxt.append(v)
        cur = nxt
    return [c for c in cur if c is not None]


def _flatten(vals: list) -> list:
    """One level of list-in-list, flattened.

    A DEFENCE AGAINST A SILENT MISCONFIGURATION, not a convenience. `metadata.related_identifiers`
    (no `[]`) plucks THE LIST ITSELF, not its members — so the relation matcher iterated over one
    object that was not a dict, found no relations, and refused every record it was shown, with the
    message "the record does not name this DOI in any relation". It was WRONG and it looked RIGHT: the
    trap test still passed, because the record it was supposed to refuse was refused. A whitelist that
    rejects everything is not a whitelist, and a route that yields nothing reads downstream exactly like
    a literature that contains nothing. This flattens, and `_match_relation` raises on an empty
    whitelist, so that failure has to be loud in both directions.
    """
    out: list = []
    for v in vals:
        out.extend(v) if isinstance(v, list) else out.append(v)
    return out


def pluck_one(obj: Any, path: str) -> Any:
    v = pluck(obj, path)
    return v[0] if v else None


def pluck_first(obj: Any, paths: Iterable[str]) -> str:
    """The first non-empty scalar across several candidate paths. Observation only."""
    for p in paths or ():
        for v in pluck(obj, p):
            if isinstance(v, (str, int, float)) and str(v).strip():
                return str(v).strip()
    return ''


def pluck_all(obj: Any, paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    for p in paths or ():
        for v in pluck(obj, p):
            if isinstance(v, (str, int, float)) and str(v).strip():
                out.append(str(v).strip())
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# IDENTIFIER NORMALISATION — the join key. If this is sloppy, EVERY identity check downstream is.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_DOI_RE = re.compile(r'10\.\d{4,9}/\S+', re.I)


def norm_doi(s: str) -> str:
    """`https://doi.org/10.1038/X` and `doi:10.1038/x` and `10.1038/X` are ONE identifier."""
    if not s:
        return ''
    s = str(s).strip().lower()
    for pre in ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'doi:', 'info:doi/'):
        if s.startswith(pre):
            s = s[len(pre):]
    m = _DOI_RE.search(s)
    return (m.group(0) if m else s).rstrip('.').strip()


def doi_of(ctx: ResolveContext) -> str:
    for i in ctx.identifiers:
        d = norm_doi(i)
        if d.startswith('10.'):
            return d
    return ''


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE THREE MATCH PRIMITIVES — "is this record ABOUT the identifier I asked for?"
#
# These are protocol primitives, not repository knowledge. Any repository can say (a) I AM that id,
# (b) I am an ALIAS of that id and my real id is this other one, (c) I have a RELATION to that id. The
# third is the dangerous one: `cites` is a relation, and a citing work is not the work.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _match_self(record: dict, want: str, res: dict, q: dict) -> tuple[bool, dict, str]:
    ids = [norm_doi(x) for x in pluck_all(record, (res.get('identity') or {}).get('doi_paths', []))]
    if want in ids:
        return True, {}, ''
    return False, {}, (f'the record the backend returned carries {ids[:3] or "no DOI"} — the identifier '
                       f'asked for was {want}. A record about another work cannot lead to this one.')


def _match_alias(record: dict, want: str, res: dict, q: dict) -> tuple[bool, dict, str]:
    """The id we asked for is an ALIAS (Zenodo: a CONCEPT DOI). The record's own id is something ELSE —
    and that substitution is the finding, not a detail. It rides on the candidate forever."""
    alias_path = (q.get('match') or {}).get('alias_path') or ''
    self_path = (q.get('match') or {}).get('self_path') or ''
    alias = norm_doi(pluck_first(record, [alias_path]))
    own = norm_doi(pluck_first(record, [self_path]))
    if alias != want:
        return False, {}, (f'the alias identifier on the record is {alias or "absent"}, not the {want} '
                           f'we asked for')
    obs = {'identifier_asked': want, 'identifier_the_record_carries': own,
           'identifier_substitution': 'alias',
           'note': ('the backend answered an ALIAS identifier with a record carrying a DIFFERENT '
                    'identifier; both are recorded and the asked-for one is not treated as the '
                    'record\'s own')}
    return True, obs, ''


def _match_relation(record: dict, want: str, res: dict, q: dict) -> tuple[bool, dict, str]:
    """The id appears in the record's RELATIONS. Only a relation asserting the record IS the work may
    pass — the whitelist is `resolver.relations.identity`, in the YAML, where it can be audited."""
    m = q.get('match') or {}
    allow = {str(r).lower().replace('_', '') for r in
             ((res.get('relations') or {}).get('identity') or [])}
    if not allow:
        # A RELATION QUERY WITH AN EMPTY WHITELIST ADMITS NOTHING — and a route that admits nothing is
        # indistinguishable, from the outside, from a literature that contains nothing. That is the bug
        # this project is made of, so it is a CONFIGURATION ERROR and it is loud.
        raise ValueError(f'query form {q.get("id")!r} matches by RELATION but `resolver.relations.'
                         f'identity` is empty — every record would be refused, and a route that refuses '
                         f'everything looks exactly like an empty literature.')
    rels = _flatten(pluck(record, m.get('list_path') or ''))
    seen: list[str] = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        ident = norm_doi(str(r.get(m.get('id_field') or 'identifier') or ''))
        rel = str(r.get(m.get('rel_field') or 'relation') or '').lower().replace('_', '')
        if ident != want:
            continue
        seen.append(rel)
        if rel in allow:
            return True, {'relation_to_asked_identifier': rel}, ''
    if seen:
        return False, {}, (f'the record names {want}, but its relation to it is {seen} — not one of the '
                           f'identity relations {sorted(allow)}. A deposit that CITES a paper is not '
                           f'that paper; its files are its own.')
    return False, {}, f'the record does not name {want} in any relation'


_MATCHERS = {'self_identifier': _match_self, 'alias_identifier': _match_alias, 'relation': _match_relation}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MEDIA HINTS — a HINT. The reducer reads the bytes; nothing here is allowed to be believed.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_EXT_MEDIA = {'pdf': 'pdf', 'xml': 'xml', 'nxml': 'xml', 'html': 'html', 'htm': 'html', 'txt': 'text',
              'json': 'data', 'csv': 'data', 'tsv': 'data', 'zip': 'archive', 'tar': 'archive',
              'gz': 'archive', 'docx': 'document', 'doc': 'document', 'ppt': 'slides', 'pptx': 'slides'}


#: Hosts that RESOLVE an identifier rather than serve a document. A link to one of them is a link to a
#: publisher's landing page — the exact bytes that profiled as a 535-word "document" and got stamped
#: FULLTEXT. `doi.org` and `dx.doi.org` are the same resolver and must read the same. (An `openAccessRoute`
#: of `hybrid` and an `accessRight: OPEN` sit on the AlphaFold record whose ONLY graph URL is one of these.)
_RESOLVER_HOSTS = ('doi.org', 'dx.doi.org', 'hdl.handle.net')


def media_hint_for(url: str, name: str = '') -> str:
    p = urllib.parse.urlparse(url or '')
    ext = (Path(p.path).suffix or Path(name or '').suffix).lstrip('.').lower()
    if ext in _EXT_MEDIA:
        return _EXT_MEDIA[ext]
    if (p.netloc or '').lower().lstrip('www.') in _RESOLVER_HOSTS:
        return 'landing'          # a DOI link is a LANDING PAGE, whatever `accessRight: OPEN` says
    return 'unknown'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# PREFLIGHT — Sol V9 §2, verbatim: "PREFLIGHT MUST MARK THE ROUTE UNAVAILABLE rather than conclude
# that content is absent." (401 -> AUTH_FAILED, never "no OA copy exists.")
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: A route found unavailable STAYS unavailable for the process. Sol V9 §7: "Circuit-break on repeated
#: 401/403/429/5xx." Re-probing a rejected key 2,490 times is not diligence, it is a denial of service
#: we perform on ourselves — and every one of those 401s would be a fresh chance for some future reducer
#: to read the empty result set as an absence.
_CIRCUIT: dict[str, RouteResult] = {}


def preflight(acq: Acquirer, table: SR.RouteTable, adapter_id: str, *,
              probe_doi: str = '10.1038/s41586-021-03819-2') -> RouteResult:
    """Can this route run AT ALL? -> a RouteResult that is never a statement about the literature."""
    if adapter_id in _CIRCUIT:
        return _CIRCUIT[adapter_id]
    route = table.by_id(adapter_id)
    if route is None or not route.resolver:
        r = RouteResult(adapter_id, '', UNAVAILABLE, basis='no resolver row in source_routes.yaml')
        _CIRCUIT[adapter_id] = r
        return r

    auth = (route.resolver.get('auth') or {})
    if auth.get('required') and not credential(route):
        r = RouteResult(adapter_id, '', UNAVAILABLE,
                        basis=(f'{auth.get("key_env")} is not configured. THE ROUTE NEVER RAN — this is a '
                               f'fact about our configuration, and the literature behind it is unexamined.'))
        _CIRCUIT[adapter_id] = r
        return r

    # A LIVE credential check. One request, on a DOI we do not care about, so that the 401 lands HERE —
    # on a probe — and not 2,490 times inside a harvest whose empty results someone will later read.
    q = (route.resolver.get('queries') or [{}])[0]
    url = _fill(q, probe_doi, limit=1)
    resp = acq.get(f'preflight:{adapter_id}', adapter_id, url, tries=1,
                   headers=_auth_headers(route), probe='credential')
    state, basis = _state_of(resp, route)
    if state == ANSWERED:
        r = RouteResult(adapter_id, '', ANSWERED, basis='the backend accepted our credential and answered')
    else:
        r = RouteResult(adapter_id, '', state, basis=basis, http_status=resp.http_status)
        _CIRCUIT[adapter_id] = r       # only FAILURE is sticky: a working route is re-checked cheaply
    return r


def _state_of(resp: Response, route: SR.Route) -> tuple[str, str]:
    """The transport outcome, as a fact about the ROUTE. The 401 branch is the one that matters."""
    if resp.outcome == AUTH_FAILED:
        env = ((route.resolver or {}).get('auth') or {}).get('key_env') or 'the credential'
        return AUTH_FAILED, (
            f'HTTP 401 — {env} was REJECTED by the backend. THE ROUTE IS UNAVAILABLE AND THE LITERATURE '
            f'BEHIND IT IS UNEXAMINED. This is a fact about our key. It is not, and can never be reduced '
            f'to, "no open copy of this work exists": we did not look. (Sol V9 §2.)')
    if resp.outcome == ACCESS_DENIED:
        return ACCESS_DENIED, f'HTTP {resp.http_status} — a fact about ENTITLEMENT at this backend'
    if resp.outcome == THROTTLED:
        return THROTTLED, (f'HTTP {resp.http_status} — a fact about OUR REQUEST RATE. Deferred, '
                           f'not concluded.')
    if resp.outcome == DEFERRED:
        return DEFERRED, ('OUR OWN governor stopped us before the request left the process — the budget '
                          'is spent, and a budget stop is not an evidence gap')
    if resp.outcome == NOT_INDEXED:
        return ANSWERED, 'HTTP 404 — the backend answered: this identifier is not in ITS index'
    if resp.outcome == BACKEND_FAILED:
        return BACKEND_FAILED, f'no readable answer ({resp.transport_error}) — we never heard back'
    if resp.outcome == RESPONDED:
        return ANSWERED, ''
    return BACKEND_FAILED, f'unrecognised transport outcome {resp.outcome!r}'


#: URL PARAMETERS THAT MEAN "MATCH THIS ANYWHERE". An identifier dropped into one of these is not a
#: lookup, it is a full-text search for a string that happens to be a DOI — and Zenodo answers it with
#: 5,723,169 hits whose first row is an unrelated dataset. This is a fact about HTTP query conventions,
#: not about any one repository, which is why it is a constant here and not a row in the YAML.
FREE_TEXT_PARAMS = ('q', 'query', 'keywords', 'search', 'text', 'term', 'title')


def _fill(q: dict, doi: str, limit: int = 10) -> str:
    """Build ONE exact-identifier query URL from a data row.

    THE UNSCOPED-QUERY REFUSAL. An identifier must land in a slot that MEANS "this identifier". There
    are exactly two such slots, and this accepts both:

      * a FIELDED expression in a free-text parameter — Zenodo/CORE: `q=doi:"10.x/y"`;
      * a dedicated IDENTIFIER PARAMETER — OpenAIRE Graph v3: `?pid=10.x/y`.

    What it refuses is the third shape: a bare identifier in a free-text parameter (`q=10.x/y`,
    `keywords=10.x/y` — which is what the LEGACY OpenAIRE endpoint this row replaced actually did).
    That is a lexical search for a string, and a lexical search is how a query for one DOI comes home
    with somebody else's paper. It is a CONFIGURATION ERROR and it dies loudly, at build time, rather
    than quietly returning five million candidates at 3am.
    """
    expr = str(q.get('q') or '')
    url_t = str(q.get('url') or '')

    if q.get('accepts') == 'doi':
        fielded = bool(re.match(r'^\s*[a-z_.]+\s*:', expr, re.I))
        if not fielded:
            # the identifier is bare — so the URL slot it lands in must itself be identifier-scoped
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url_t).query, keep_blank_values=True)
            slots = [p for p, vals in qs.items()
                     if any('{q}' in v or '{doi}' in v for v in vals)]
            free = [p for p in slots if p.lower() in FREE_TEXT_PARAMS]
            if free or not slots:
                raise ValueError(
                    f'query form {q.get("id")!r} puts a bare identifier into '
                    f'{free or "no identifiable parameter"} — that is a FREE-TEXT SEARCH for a string '
                    f'that happens to be a DOI, not a lookup of it. Give the expression a `field:` '
                    f'prefix, or bind the identifier to an identifier-scoped parameter (e.g. `pid=`).')

    expr = expr.replace('{doi}', doi)
    return (url_t
            .replace('{q}', urllib.parse.quote(expr or doi, safe=''))
            .replace('{doi}', urllib.parse.quote(doi, safe=''))
            .replace('{limit}', str(limit)))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE ONE RESOLVER. Three routes, one function: the differences between them are ROWS.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def resolve(acq: Acquirer, table: SR.RouteTable, adapter_id: str, ctx: ResolveContext, *,
            limit: int = 10) -> RouteResult:
    """Ask ONE repository about ONE work. -> candidates + a route state. NEVER a document, never a
    version, never an admissibility. The bytes are somebody else's job and so is every verdict on them.
    """
    route = table.by_id(adapter_id)
    if route is None or not route.resolver:
        return RouteResult(adapter_id, ctx.work_id, UNAVAILABLE, basis='no resolver row for this adapter')

    pre = preflight(acq, table, adapter_id)
    if not pre.answered:
        # THE POINT OF THE WHOLE MODULE. We return ZERO candidates and a state that says WHY — and the
        # `answered=False` on it is what stops a downstream reducer from reading those zero candidates
        # as "this work has no open copy". Zero candidates from a route that never ran is not a finding.
        #
        # AND THE UNIT'S LEDGER MUST SAY SO TOO. The adversary caught this: returning early wrote NOTHING
        # against the work, so `classify_discovery_outcome(unit, 'core')` reduced to NO_ATTEMPT — "this
        # route was never tried". True, but it is the WRONG TRUE THING. It says we did not look; it does
        # not say WE CANNOT LOOK BECAUSE OUR KEY IS DEAD. `licenses_absence` refuses both, so nothing was
        # unsafe — but the run could not tell "fix the credential" from "we have not got to it yet", and
        # the 401 that made a whole 60-140-document lane unreachable would have been invisible in the
        # per-unit record. So the route's own terminal outcome is stamped on every unit it skips.
        _record_skip(acq, ctx.work_id, adapter_id, pre)
        return RouteResult(adapter_id, ctx.work_id, pre.state, basis=pre.basis,
                           http_status=pre.http_status)

    res = route.resolver
    doi = doi_of(ctx)
    if not doi:
        return RouteResult(adapter_id, ctx.work_id, UNAVAILABLE,
                           basis='no DOI on the resolve context — these three routes resolve by exact '
                                 'identifier, and a title search cannot establish identity (Sol V9 §3)')

    acq.plan_route(ctx.work_id, [adapter_id], resolver_row=res.get('kind'), identifier_used=doi)

    cands: list[DocumentCandidate] = []
    rejected: list[dict] = []
    obs_by_cid: dict = {}
    oai_ids: list[str] = []
    seen_records: set[str] = set()
    states: list[str] = []
    bases: list[str] = []
    seen_urls: set[str] = set()

    for q in (res.get('queries') or []):
        if q.get('accepts') != 'doi':
            continue
        url = _fill(q, doi, limit=limit)
        resp = acq.get(ctx.work_id, adapter_id, url, tries=2, headers=_auth_headers(route),
                       query_form=str(q.get('id') or ''), identifier_used=doi)
        state, basis = _state_of(resp, route)
        states.append(state)
        if basis:
            bases.append(f'[{q.get("id")}] {basis}')
        if state != ANSWERED or not resp.ok:
            continue

        body = resp.json()
        if body is None:
            states[-1] = BACKEND_FAILED
            bases.append(f'[{q.get("id")}] the backend answered with a body we could not parse as JSON — '
                         f'we did not receive an answer we can read')
            continue

        records = [r for r in pluck(body, str(res.get('records') or '')) if isinstance(r, dict)]

        for rec in records:
            # ONE RECORD, however many query forms return it. Zenodo's three probes routinely surface the
            # same deposit; counting it once per probe would inflate the ladder's "records examined" by
            # 3x and make a route look like it searched three times as much literature as it did.
            #
            # IT IS COUNTED ONCE AND EVALUATED EVERY TIME, and the difference matters: the three query
            # forms carry three DIFFERENT identity semantics (self / alias / relation), so a record that
            # fails to prove itself under one may legitimately prove itself under another. Skipping the
            # match on a record we have merely SEEN before would let the first form's verdict silently
            # veto the other two. Candidates are deduplicated separately, on the URL.
            seen_records.add(str(pluck_first(rec, ['doi', 'id', 'objectIdentifier'])
                                 or json.dumps(rec, sort_keys=True)[:200]))

            matcher = _MATCHERS.get(str((q.get('match') or {}).get('kind') or 'self_identifier'))
            ok, match_obs, why = matcher(rec, doi, res, q)
            if not ok:
                rejected.append({'query_form': q.get('id'), 'record_title': str(pluck_first(
                    rec, [(res.get('identity') or {}).get('title_path', '')]))[:120], 'why': why})
                continue

            # THE RAW METADATA GOES TO THE BLOB STORE, NOT THE LEDGER. It is evidence — the record we
            # actually saw, hashed — and it is also arbitrary text from the world, which is exactly what
            # must never be pasted into an append-only log that a reducer reads.
            meta_blob, meta_sha = acq.blobs.put_text(json.dumps(rec, sort_keys=True))

            declared = _declared_artifact(rec, res)
            record_url = pluck_first(rec, ['links.self_html', 'links.self', 'id'])
            base_obs = {**match_obs, **declared,
                        'raw_metadata_hash': meta_sha}

            for sel in (res.get('selectors') or []):
                for url_, extra in _urls_from_selector(rec, sel):
                    if not url_ or url_ in seen_urls:
                        continue      # several instances naming ONE file are ONE candidate (Sol V9 §2)
                    seen_urls.add(url_)
                    # `from_url` / `from_filename` / an absent hint all mean DERIVE IT. A row must not be
                    # able to ASSERT `pdf` — the hint is a guess from a file extension either way, and
                    # the bytes are what decide. (This is why a `.pdf` URL and a doi.org landing page
                    # both arrive here as candidates and neither arrives as a document.)
                    hint = str(sel.get('media_hint') or '')
                    if hint in ('from_url', 'from_filename', 'unknown', ''):
                        hint = media_hint_for(url_, extra.get('file_name', ''))
                    extra = {**extra, **_url_identifier_conflict(url_, doi)}
                    cid = acq.candidate(
                        ctx.work_id, adapter_id, url_,
                        resolver_request_id=resp.request_id,
                        identifier_used=doi, query_form=str(q.get('id') or ''),
                        media_hint=hint, origin=str(sel.get('origin') or ''),
                        version_hint=pluck_first(rec, res.get('version_hint_paths', [])),
                        license_observation=pluck_first(rec, res.get('license_paths', [])),
                        access_observation=pluck_first(rec, res.get('access_paths', [])),
                        raw_metadata_blob_id=meta_blob,
                        **{k: v for k, v in {**base_obs, **extra}.items() if k != 'file_name'})
                    cands.append(DocumentCandidate(
                        candidate_id=cid, work_id=ctx.work_id, discovered_by_route=adapter_id,
                        resolver_request_id=resp.request_id, identifier_used=doi,
                        retrieval_url=url_, repository_record_url=str(record_url or ''),
                        media_hint=str(hint or 'unknown'),
                        version_hint=pluck_first(rec, res.get('version_hint_paths', [])),
                        license_observation=pluck_first(rec, res.get('license_paths', [])),
                        raw_metadata_blob_id=meta_blob, raw_metadata_hash=meta_sha))
                    obs_by_cid[cid] = {**base_obs, **extra, 'media_hint': hint, 'url': url_}

            oai_ids.extend(pluck_all(rec, res.get('oai_id_paths', [])))

    state = _worst(states)
    return RouteResult(
        adapter_id, ctx.work_id, state, tuple(cands),
        basis='; '.join(bases) or ('the backend answered our exact-identifier query'
                                   + ('' if cands else ' and proposed no candidate URL for it — a fact '
                                      'about THIS backend\'s holdings, not about the literature')),
        records_seen=len(seen_records), rejected=tuple(rejected), candidate_obs=obs_by_cid,
        oai_ids=tuple(dict.fromkeys(oai_ids)))


def _record_skip(acq: Acquirer, unit: str, adapter_id: str, pre: RouteResult) -> None:
    """Stamp a route's own unavailability onto a work it therefore could not examine.

    These are OBSERVATIONS about the ROUTE, replayed onto the unit: they carry the http_status the
    backend actually gave us and the request that got it. The reducer (`_transport_outcome`) reads
    EventKind.BLOCKED -> ACCESS_DENIED and EventKind.THROTTLED -> THROTTLED, and `licenses_absence`
    refuses an absence while either is in the set. Which is the whole point: the work is UNEXAMINED by
    this route, the ledger says so, and nothing downstream can mistake that for an empty literature.
    """
    acq.ledger.emit(unit, EventKind.ROUTE_PLANNED, 'routes_repo',
                    adapters=[adapter_id], route_state=pre.state)
    rid = f'{adapter_id}#skipped'
    kind = (EventKind.THROTTLED if pre.state == THROTTLED else
            EventKind.BLOCKED if pre.state in (AUTH_FAILED, ACCESS_DENIED, UNAVAILABLE) else
            EventKind.RESPONSE_RECEIVED)
    payload: dict = {'adapter': adapter_id, 'request_id': rid, 'route_state': pre.state,
                     'preflight': True}
    if pre.http_status:
        payload['http_status'] = pre.http_status
    if kind == EventKind.RESPONSE_RECEIVED:
        payload['transport_error'] = pre.state       # BACKEND_FAILED: never got a readable answer
    acq.ledger.emit(unit, kind, 'routes_repo', **payload)


def _worst(states: list[str]) -> str:
    """WORST-FIRST, and deliberately so. If one of three query forms was throttled and two answered
    empty, THE ROUTE WAS THROTTLED. Letting the two clean empties outvote the 429 is precisely how a
    fact about our request rate becomes a fact about the world."""
    if not states:
        return BACKEND_FAILED
    for s in (AUTH_FAILED, THROTTLED, DEFERRED, ACCESS_DENIED, BACKEND_FAILED, UNAVAILABLE):
        if s in states:
            return s
    return ANSWERED


def _declared_artifact(rec: dict, res: dict) -> dict:
    """WHAT THE DEPOSITOR SAID THIS IS. `artifact_declaration` is a quotation, and `declares_article` is
    whether that quotation is one the contract could read as an article AT ALL — never whether the bytes
    are one. Sol V9 §2: "Artifact type must stay EXPLICIT — a dataset or supplement is NOT an article."
    """
    at = res.get('artifact_types') or {}
    if not at.get('path'):
        return {}
    node = pluck_one(rec, at['path'])
    if isinstance(node, dict):
        kind = str(node.get('type') or '')
        sub = str(node.get('subtype') or '')
    else:
        kind, sub = str(node or ''), ''
    decl = f'{kind}/{sub}' if sub else kind
    allow = {str(a).lower() for a in (at.get('article_declarations') or [])}
    return {'artifact_declaration': decl,
            'declares_article': bool(decl.lower() in allow)}


def _urls_from_selector(rec: dict, sel: dict) -> list[tuple[str, dict]]:
    """One selector row -> (url, observations). Handles the three shapes a repository ever uses: a bare
    URL string, a list of objects with a URL field, and INLINE TEXT that arrived with the metadata."""
    path = str(sel.get('path') or '')
    where = sel.get('where') or {}
    out: list[tuple[str, dict]] = []

    for v in pluck(rec, path):
        if isinstance(v, str):
            if sel.get('inline'):
                # CORE'S `fullText`. THE TEXT IS ALREADY IN OUR HANDS — but it is DERIVED TEXT, extracted
                # by somebody else's OCR/parser, and Sol V9 §2 is explicit that it is "NOT automatically
                # a complete PDF equivalent". So it does not become a manifestation here: it becomes a
                # candidate whose bytes are already stored, addressed BY THEIR HASH, for the executor to
                # profile like any other bytes. It gets no shortcut past the completeness reducer.
                out.append((f'inline:{path}', {'inline_text_chars': len(v)}))
            else:
                out.append((v, {}))
            continue
        if isinstance(v, dict):
            if where and any(str(v.get(k, '')).lower() != str(w).lower() for k, w in where.items()):
                continue
            url = pluck_first(v, [str(sel.get('url_field') or 'url')])
            if not url:
                continue
            extra: dict = {}
            if sel.get('name_field'):
                extra['file_name'] = pluck_first(v, [str(sel['name_field'])])
            if sel.get('size_field'):
                sz = pluck_one(v, str(sel['size_field']))
                if isinstance(sz, (int, float)):
                    extra['file_bytes'] = int(sz)
            if sel.get('checksum_field'):
                extra['file_checksum'] = pluck_first(v, [str(sel['checksum_field'])])
            out.append((url, extra))
    return out


def _url_identifier_conflict(url: str, want: str) -> dict:
    """Does this candidate URL RESOLVE A DIFFERENT IDENTIFIER than the one we asked for?

    FOUND IN THE LIVE PROBE, NOT IMAGINED: asked OpenAIRE for `10.52214/jla.v49i1.14439`, and among the
    instance URLs of the record it returned was `https://doi.org/10.52214/jla.v49i1.14420` — a landing
    page for A DIFFERENT ARTICLE in the same issue. The record's `pids` DID carry our DOI, so the
    identity check passed; it is one of its INSTANCES that points somewhere else.

    THIS IS AN OBSERVATION AND NOT A REJECTION, and the restraint is deliberate. Identity is decided
    from the BYTES (Sol V9 §5), and an adapter that starts throwing away leads on a URL-string heuristic
    is the "too aggressive" reducer Sol warns about in the same section — it would silently narrow the
    corpus and call it precision. So we fetch it, and the byte-derived identity reducer rules
    DIFFERENT_WORK with the document in hand. We simply refuse to be surprised: the conflict is on the
    candidate, before a single byte is spent.
    """
    m = _DOI_RE.search(urllib.parse.unquote(url or ''))
    if not m:
        return {}
    in_url = norm_doi(m.group(0))
    if in_url and want and in_url != want:
        return {'url_names_a_different_identifier': in_url}
    return {}


def reset_circuit() -> None:
    """Tests only. A run does not get to forget that a key was rejected."""
    _CIRCUIT.clear()


if __name__ == '__main__':
    print(__doc__)
    print('This module is a library. Its invariants are attacked by:  '
          'python3 scripts/test_routes_repo_attacks.py')
    print('Live probes on real candidate DOIs:                        '
          'python3 scripts/probe_routes_repo_live.py')
