#!/usr/bin/env python3
"""SOURCE ROUTER — CAPABILITY-BASED, DATA-DRIVEN, OA-FIRST DISCOVERY (Sol plan 4, item 2).

THE STRATEGY THIS CHANGES
-------------------------
The old strategy was "pick the canonical (usually paywalled) work, then chase a free copy of it." It
had a 19% hit rate because it started from the version we were LEAST likely to be able to read. This
router inverts it: OA-FIRST DISCOVERY, then VERSION PURSUIT. We enumerate what is openly readable
first (DOAJ / PMC / Europe PMC / OpenAlex / CORE / OpenAIRE), resolve identity and the full set of
locations (Crossref / OpenAlex / Unpaywall — never trusting their version label), and only then pursue
the specific citable expression the plan's policy requires.

WHAT MAKES IT GENERAL (and not the tell we keep failing)
--------------------------------------------------------
It does NOT ask an LLM to remember that economists use NBER or clinicians use PubMed. That knowledge is
a hardcoded topic gate — the exact defect this project keeps shipping. Here the knowledge lives in
`config/source_routes.yaml` as ONE ROW PER ROUTE, keyed by the EVIDENCE CAPABILITY (role) the route
supplies. This file is a GENERIC engine over that table:

    contract  --(role_requirements table)-->  REQUIRED evidence roles
    required roles  --SET COVER over routes[*].evidence_roles-->  the routes that FIRE

There is no adapter name and no topic word in this module. Adding a domain that these adapters already
serve — a new jurisdiction's courts, a new preprint server, a new registry — is a NEW ROW in the YAML
and ZERO lines of Python. That is the standing order: a domain change is a DATA edit, never a code edit.

On a CLINICAL question it fires PubMed/PMC/Europe PMC/ClinicalTrials.gov and NOT NBER. On a LEGAL
question it fires GovInfo/EUR-Lex/CourtListener/SSRN and NOT NBER. On a THIN-EVIDENCE question it fires
the OA-first backbone, finds nothing, and — only if every applicable route genuinely ANSWERED — lets
the honest answer be "the literature we can reach does not settle this."

FIRING IS NOT CITABILITY
------------------------
Whether a route FIRES (does the plan need its capability?) is a different decision from whether what it
returns is CITABLE (does the plan's source_policy permit that expression?). Under a journal-only policy,
arXiv and NBER still FIRE — for discovery and version pursuit — but their preprint/working-paper
expressions are NOT citable; we use them to locate the underlying study and pursue its journal Version
of Record. This module reports both, per route, and never collapses them.

EVERY LIVE ATTEMPT GOES THROUGH acquisition.Acquirer
----------------------------------------------------
So every attempt lands on the append-only event ledger and the distinct outcomes stay distinct:

    FETCHED | NOT_FOUND | ACCESS_DENIED | THROTTLED | TRANSIENT_ERROR | LANDING_PAGE | ABSTRACT_ONLY |
    WRONG_WORK | CORRUPT_EXTRACTION

and — critically — the discovery outcome is DERIVED by a reducer over the ledger, never asserted by a
fetcher. Only NOT_FOUND, across every applicable route that genuinely answered, supports "we did not
locate an accessible copy." A 429 (THROTTLED) never does, and neither does a 403 (ACCESS_DENIED): those
are facts about OUR request and OUR entitlement, not about the world.

Run it:
    python3 scripts/source_router.py                 # dry-runs (task 72, clinical, legal, thin) + outcome demo
    python3 scripts/source_router.py --live          # + a handful of real probes through Acquirer
    python3 scripts/source_router.py --routes         # print the route table as loaded
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

# ── THE INTEGRITY LAYER. We reuse it; we do not re-implement any of it. ──────────────────────────────
from event_ledger import (  # noqa: E402
    EventKind, Ledger, observe_text,
    derive_content_profile, derive_semantic_binding,
    C_FULLTEXT, C_ABSTRACT, C_CITATION, C_NOT_DOC, C_UNREADABLE, DIFFERENT_WORK,
)
import provenance  # noqa: E402  (SourcePolicy + the named admissibility policies)

ROUTES_YAML = ROOT / 'config' / 'source_routes.yaml'


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# THE DISCOVERY-OUTCOME VOCABULARY — nine facts about a RETRIEVAL, none of them a fact about the world.
# They are DERIVED from the ledger below; a route may never set one.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
FETCHED            = 'FETCHED'             # a complete, readable document, and it IS the work we asked for
NOT_FOUND          = 'NOT_FOUND'           # the backend answered, and holds no accessible copy (404 / citation-only)
ACCESS_DENIED      = 'ACCESS_DENIED'       # 401/402/403/451 — a fact about ENTITLEMENT
THROTTLED          = 'THROTTLED'           # 429/503 — a fact about OUR REQUEST RATE. NEVER an absence.
TRANSIENT_ERROR    = 'TRANSIENT_ERROR'     # timeout / DNS / reset / 5xx / a hang — we never got an answer
LANDING_PAGE       = 'LANDING_PAGE'        # bytes that are a web page ABOUT the document, not the document
ABSTRACT_ONLY      = 'ABSTRACT_ONLY'       # a fragment of the article, not the article
WRONG_WORK         = 'WRONG_WORK'          # a complete document — of somebody else's paper
CORRUPT_EXTRACTION = 'CORRUPT_EXTRACTION'  # bytes we could not decode (a PDF of pure (cid:NN) glyphs)
NO_ATTEMPT         = 'NO_ATTEMPT'          # this route was never tried for this unit (not an outcome, a gap)

#: The outcomes that mean "we HELD something" — presence, never absence.
_HELD = {FETCHED, ABSTRACT_ONLY, LANDING_PAGE, WRONG_WORK, CORRUPT_EXTRACTION}
#: The outcomes that are a fact about US, not the literature — they forbid an absence statement.
_OUR_FAULT = {THROTTLED, ACCESS_DENIED, TRANSIENT_ERROR}

#: content class -> discovery outcome, once the transport RESPONDED and a manifestation was recorded.
_CLASS_TO_OUTCOME = {
    C_FULLTEXT: FETCHED,
    C_ABSTRACT: ABSTRACT_ONLY,
    C_CITATION: NOT_FOUND,       # a citation stub is not an accessible copy
    C_NOT_DOC: LANDING_PAGE,
    C_UNREADABLE: CORRUPT_EXTRACTION,
}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# THE ROUTE TABLE — loaded from data, never written in code.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Route:
    adapter_id: str
    evidence_roles: tuple[str, ...]
    document_types: tuple[str, ...]
    jurisdiction_coverage: tuple[str, ...]
    query_dialects: tuple[str, ...]
    identifier_types: tuple[str, ...]
    version_resolvers: tuple[str, ...]
    rate_policy: dict
    coverage_note: str
    endpoints: dict
    discovery_via: tuple[str, ...] = ()
    scope_ref: dict | None = None

    @property
    def is_evidence_route(self) -> bool:
        """Does this route hand back a CITABLE document (vs. pure index/identity/location infrastructure)?"""
        return 'fetch.oa_fulltext' in self.evidence_roles or \
            any(r.startswith('evidence.') for r in self.evidence_roles)


@dataclass
class RouteTable:
    roles: dict[str, str]
    role_requirements: list[dict]
    jurisdiction_lexicon: dict[str, str]
    routes: list[Route]
    mailto: str
    registry_version: str = ''

    def by_id(self, adapter_id: str) -> Route | None:
        return next((r for r in self.routes if r.adapter_id == adapter_id), None)

    def validate(self) -> list[str]:
        """Every role a route supplies OR a requirement demands must be DEFINED. A dangling role would
        silently route nothing (or require the impossible), and print as an evidence gap. That is the
        failure mode this whole project exists to prevent, so the table refuses to load with one."""
        problems: list[str] = []
        defined = set(self.roles)
        for r in self.routes:
            for role in r.evidence_roles:
                if role not in defined:
                    problems.append(f'route {r.adapter_id!r} supplies undefined role {role!r}')
        for rr in self.role_requirements:
            if rr.get('role') not in defined:
                problems.append(f'role_requirement references undefined role {rr.get("role")!r}')
        return problems


def load_table(path: Path | str = ROUTES_YAML) -> RouteTable:
    import os
    raw = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    routes = []
    for row in raw.get('routes', []):
        routes.append(Route(
            adapter_id=row['adapter_id'],
            evidence_roles=tuple(row.get('evidence_roles', [])),
            document_types=tuple(row.get('document_types', [])),
            jurisdiction_coverage=tuple(row.get('jurisdiction_coverage', ['ANY'])),
            query_dialects=tuple(row.get('query_dialects', [])),
            identifier_types=tuple(row.get('identifier_types', [])),
            version_resolvers=tuple(row.get('version_resolvers', [])),
            rate_policy=dict(row.get('rate_policy', {})),
            coverage_note=(row.get('coverage_note', '') or '').strip(),
            endpoints=dict(row.get('endpoints', {}) or {}),
            discovery_via=tuple(row.get('discovery_via', []) or []),
            scope_ref=row.get('scope_ref'),
        ))
    mailto_env = raw.get('mailto_env', 'POLARIS_MAILTO')
    table = RouteTable(
        roles=dict(raw.get('roles', {})),
        role_requirements=list(raw.get('role_requirements', [])),
        jurisdiction_lexicon={str(k).lower(): v for k, v in (raw.get('jurisdiction_lexicon', {}) or {}).items()},
        routes=routes,
        mailto=os.environ.get(mailto_env, 'aldrin.or@c-polarbiotech.com'),
        registry_version=str(raw.get('registry_version', '')),
    )
    problems = table.validate()
    if problems:
        raise ValueError('source_routes.yaml is internally inconsistent:\n  ' + '\n  '.join(problems))
    return table


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# CONTRACT -> REQUIRED ROLES — a generic match of DATA tokens against the plan's own vocabulary.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def _get(contract: Any, name: str, default=None):
    """Read a field from a research_contract.Contract OR a plain dict. The router accepts either, so it
    can be exercised without importing the compiler."""
    if isinstance(contract, dict):
        return contract.get(name, default)
    return getattr(contract, name, default)


def _term_forms(terms: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for t in terms or []:
        if isinstance(t, dict):
            out.append(str(t.get('label', '')))
            out.extend(str(a) for a in t.get('aliases', []) or [])
        else:
            out.append(str(getattr(t, 'label', '') or ''))
            out.extend(str(a) for a in getattr(t, 'aliases', []) or [])
    return out


def routing_text(contract: Any) -> str:
    """THE PLAN'S OWN VOCABULARY, assembled into one lowercased blob for the trigger matcher.

    It is deliberately WIDE: the question and review subject (present even in a degraded, no-LLM
    contract), plus every structured field a full contract carries — method designs, unit levels,
    concepts and their surface aliases, framing devices, the subject axis, outcome dimensions,
    geographies and the genre. The richer the contract, the sharper the routing; but the question alone
    is enough to route, so an offline contract still works.
    """
    bits: list[str] = [
        str(_get(contract, 'question', '') or ''),
        str(_get(contract, 'review_subject', '') or ''),
        str(_get(contract, 'title', '') or ''),
        str(_get(contract, 'genre', '') or ''),
    ]
    bits += [str(x) for x in (_get(contract, 'method_designs', []) or [])]
    bits += [str(x) for x in (_get(contract, 'unit_levels', []) or [])]
    bits += [str(x) for x in (_get(contract, 'geographies', []) or [])]
    bits += [str(x) for x in (_get(contract, 'time_horizons', []) or [])]
    bits += [str(x) for x in (_get(contract, 'evidence_tuple', []) or [])]
    bits += _term_forms(_get(contract, 'core_concepts', []))
    bits += _term_forms(_get(contract, 'framing_devices', []))
    bits += _term_forms(_get(contract, 'outcome_dimensions', []))
    ax = _get(contract, 'subject_axis', None)
    if ax is not None:
        bits.append(str(_get(ax, 'name', '') or ''))
        bits += _term_forms(_get(ax, 'values', []))
    # a journal-only / peer-reviewed policy is itself a signal that peer-reviewed indices are wanted.
    sp = _get(contract, 'source_policy', None)
    if sp is not None:
        if _get(sp, 'peer_reviewed_only', False):
            bits.append('peer-reviewed journal articles')
        bits += [str(x) for x in (_get(sp, 'question_evidence', []) or [])]
    return re.sub(r'\s+', ' ', ' '.join(bits)).lower()


def _contains(text: str, token: str) -> bool:
    """Whole-word / whole-phrase containment. `wage` matches "wage" but not "wager"; "labor market"
    matches the phrase. The boundary is non-alphanumeric on both sides, so dotted forms like "u.s."
    match too. This is the ONLY pattern logic in the module, and it is topic-agnostic."""
    tok = re.sub(r'\s+', ' ', token.strip().lower())
    if not tok:
        return False
    return re.search(rf'(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])', text) is not None


def required_roles(table: RouteTable, contract: Any) -> dict[str, str]:
    """The evidence roles this plan REQUIRES -> {role: basis}. `default: true` rules are the OA-first
    backbone (always required). The rest fire when the plan's routing text contains a trigger token."""
    text = routing_text(contract)
    out: dict[str, str] = {}
    for rule in table.role_requirements:
        role = rule.get('role')
        if rule.get('default'):
            out[role] = 'OA-first backbone (every scholarly plan needs it)'
            continue
        for tok in rule.get('any_of', []) or []:
            if _contains(text, tok):
                out[role] = f'plan vocabulary contains {tok!r}'
                break
    return out


def detect_jurisdictions(table: RouteTable, contract: Any) -> dict[str, str]:
    """{ISO code: the phrase that implied it}. Empty => the plan named no forum, and jurisdiction-scoped
    routes fire broadly (we do not know where to look, so we look everywhere applicable)."""
    text = routing_text(contract)
    found: dict[str, str] = {}
    for phrase, code in table.jurisdiction_lexicon.items():
        if _contains(text, phrase):
            found.setdefault(code, phrase)
    return found


def admissibility_policy(contract: Any) -> provenance.SourcePolicy:
    """WHICH EXPRESSION KINDS this answer may CITE — the plan's source_policy, made mechanical against
    provenance's version taxonomy. This is the axis that turns arXiv/NBER into discovery-only under a
    journal-only instruction, without stopping them from firing."""
    sp = _get(contract, 'source_policy', None)
    if sp is None or not _get(sp, 'peer_reviewed_only', False):
        return provenance.ANY_VERSION
    excluded = {str(x).lower() for x in (_get(sp, 'excluded_types', []) or [])}
    kinds = ['journal_version']
    if not any('proceeding' in e for e in excluded):
        kinds.append('proceedings_version')
    name = 'journal_articles_only' if kinds == ['journal_version'] else 'peer_reviewed'
    return provenance.SourcePolicy(name, tuple(kinds))


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# THE SET COVER — fire EVERY route that covers a required role, subject to the jurisdiction gate.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class FiredRoute:
    route: Route
    covered_roles: tuple[str, ...]     # the required roles THIS route supplies
    kind: str                          # 'evidence' | 'infrastructure'
    admissibility: str                 # 'citable' | 'discovery_only' | 'infrastructure'
    admissibility_reason: str = ''

    @property
    def adapter_id(self) -> str:
        return self.route.adapter_id


@dataclass
class RoutingPlan:
    required: dict[str, str]
    jurisdictions: dict[str, str]
    policy: provenance.SourcePolicy
    fired: list[FiredRoute]
    jurisdiction_filtered: list[tuple[Route, str]]   # (route, reason) — supplied a role but wrong forum
    uncovered_roles: dict[str, str]                  # required role -> basis, with NO route to serve it
    per_role: dict[str, list[str]]                   # required role -> [adapter_ids covering it]

    def fired_ids(self) -> list[str]:
        return [f.adapter_id for f in self.fired]

    def fires(self, adapter_id: str) -> bool:
        return any(f.adapter_id == adapter_id for f in self.fired)


def _jurisdiction_ok(route: Route, jurisdictions: dict[str, str]) -> tuple[bool, str]:
    cov = set(route.jurisdiction_coverage)
    if 'ANY' in cov:
        return True, ''
    if not jurisdictions:
        return True, ''                      # no forum named -> fire broadly
    hit = cov & set(jurisdictions)
    if hit:
        return True, f'jurisdiction match {sorted(hit)}'
    return False, (f'covers {sorted(cov)} but the plan is scoped to {sorted(jurisdictions)} '
                   f'— wrong forum, not fired')


def route(table: RouteTable, contract: Any) -> RoutingPlan:
    """The whole routing decision. Pure over (table, contract): no network, deterministic, testable."""
    required = required_roles(table, contract)
    jurisdictions = detect_jurisdictions(table, contract)
    policy = admissibility_policy(contract)
    permitted = set(policy.permitted_expression_kinds)

    fired: list[FiredRoute] = []
    filtered: list[tuple[Route, str]] = []
    per_role: dict[str, list[str]] = {r: [] for r in required}

    for r in table.routes:
        covered = tuple(role for role in r.evidence_roles if role in required)
        if not covered:
            continue                          # this route serves nothing the plan needs
        ok, why = _jurisdiction_ok(r, jurisdictions)
        if not ok:
            filtered.append((r, why))
            continue

        if r.is_evidence_route:
            citable = [dt for dt in r.document_types if dt in permitted]
            if citable:
                adm, reason = 'citable', f'yields {citable} — permitted by {policy.name}'
            else:
                adm, reason = 'discovery_only', (
                    f'yields {list(r.document_types)}; {policy.name} permits only '
                    f'{sorted(permitted)} — fires for DISCOVERY / version pursuit, output not citable')
            kind = 'evidence'
        else:
            adm, reason, kind = 'infrastructure', 'index / identity / location resolver', 'infrastructure'

        fired.append(FiredRoute(r, covered, kind, adm, reason))
        for role in covered:
            per_role[role].append(r.adapter_id)

    uncovered = {role: basis for role, basis in required.items() if not per_role.get(role)}
    return RoutingPlan(required, jurisdictions, policy, fired, filtered, uncovered, per_role)


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# THE DISCOVERY-OUTCOME REDUCER — over the ledger. A route never says how it did; the ledger does.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

_REQUEST_KINDS = (EventKind.BACKEND_ATTEMPTED, EventKind.RESPONSE_RECEIVED,
                  EventKind.THROTTLED, EventKind.BLOCKED)
#: worst-first: any throttle/denial/error on an applicable request forbids reading absence off the rest.
_TRANSPORT_PRECEDENCE = (THROTTLED, ACCESS_DENIED, TRANSIENT_ERROR, 'RESPONDED', NOT_FOUND)


def _transport_outcome(events: list, adapter: str) -> str:
    """One adapter's transport-level result, read from the FINAL terminal event of each of its requests
    (so a 429-then-200 reads RESPONDED, not THROTTLED — the backoff worked). Distinguishes THROTTLED
    (429/503) from TRANSIENT_ERROR (timeout/5xx/hang), which the coarser event_ledger reducer folds
    together as BACKEND_FAILED but the discovery vocabulary must keep apart."""
    reqs: dict[str, list] = {}
    for e in events:
        if e.payload.get('adapter') != adapter or e.kind not in _REQUEST_KINDS:
            continue
        if 'derived_by' in e.payload:
            continue
        reqs.setdefault(str(e.payload.get('request_id') or ''), []).append(e)
    if not reqs:
        return NO_ATTEMPT

    per: list[str] = []
    for _rid, evs in reqs.items():
        terminal = [e for e in evs if e.kind in (EventKind.RESPONSE_RECEIVED,
                                                  EventKind.THROTTLED, EventKind.BLOCKED)]
        if not terminal:
            per.append(TRANSIENT_ERROR)       # attempted, never came back — a HANG, not a gap
            continue
        e = terminal[-1]
        code = e.payload.get('http_status')
        if e.kind == EventKind.THROTTLED or code in (429, 503):
            per.append(THROTTLED)
        elif e.kind == EventKind.BLOCKED or code in (401, 402, 403, 451):
            per.append(ACCESS_DENIED)
        elif code == 404:
            per.append(NOT_FOUND)
        elif e.payload.get('transport_error'):
            per.append(TRANSIENT_ERROR)
        else:
            per.append('RESPONDED')
    for o in _TRANSPORT_PRECEDENCE:
        if o in per:
            return o
    return TRANSIENT_ERROR


def _content_outcome(events: list) -> tuple[str, str]:
    """When the transport RESPONDED, WHAT DID WE ACTUALLY GET? Derived from the SAME reducers the rest
    of the pipeline uses, so this module cannot disagree with the corpus about what a document is."""
    mans = [e for e in events
            if e.kind == EventKind.MANIFESTATION_FETCHED and 'derived_by' not in e.payload]
    if not mans:
        return NOT_FOUND, ('the backend answered but no document was fetched — an index/identity probe, '
                           'or a search that located no accessible copy')
    binding, binfo = derive_semantic_binding(events)
    if binding == DIFFERENT_WORK:
        return WRONG_WORK, binfo.get('reason', 'the fetched document is a different work')
    cls, info = derive_content_profile(events)
    return _CLASS_TO_OUTCOME.get(cls, NOT_FOUND), info.get('reason', '')


def classify_discovery_outcome(ledger: Ledger, unit: str, adapter: str) -> tuple[str, str]:
    """(outcome, basis) for one route's attempt to ACQUIRE A DOCUMENT for `unit`. Reduces over the
    ledger; asserts nothing. This is the function the pipeline calls to learn a route's honest result."""
    events = ledger.events(unit)
    t = _transport_outcome(events, adapter)
    if t == NO_ATTEMPT:
        return NO_ATTEMPT, 'this route was never attempted for this unit'
    if t != 'RESPONDED':
        basis = {
            THROTTLED: 'HTTP 429/503 — a fact about OUR REQUEST RATE, never about the literature',
            ACCESS_DENIED: 'HTTP 401/402/403/451 — a fact about ENTITLEMENT, never about the literature',
            NOT_FOUND: 'HTTP 404 — this backend does not index it (a fact about THEIR INDEX)',
            TRANSIENT_ERROR: 'timeout / DNS / reset / 5xx / hang — we never got an answer',
        }[t]
        return t, basis
    return _content_outcome(events)


def licenses_absence(outcomes: Iterable[str]) -> tuple[bool, str]:
    """May we write "we did not locate an accessible copy" given these per-route outcomes?

    ONLY if every applicable route genuinely ANSWERED and none held a copy — i.e. the set is exactly
    {NOT_FOUND}. One THROTTLED, one ACCESS_DENIED, one TRANSIENT_ERROR, and the honest answer is
    SEARCH_FAILED: we do not know. This is the seven-way distinction of event_ledger, at the discovery
    layer: a 429 is not evidence of absence, and it never becomes one.
    """
    s = set(outcomes)
    if not s:
        return False, 'no applicable route was attempted — we never looked'
    if NO_ATTEMPT in s:
        return False, ('an applicable route was never attempted — the search is INCOMPLETE '
                       '(event_ledger: UNSEARCHED), which is not an absence')
    blockers = s & _OUR_FAULT
    if blockers:
        return False, (f'{sorted(blockers)} occurred — a fact about OUR request/entitlement, not the '
                       f'literature. Absence is NOT licensed; the honest status is SEARCH_FAILED')
    if FETCHED in s:
        return False, 'a copy was FETCHED — the claim here is PRESENCE, not absence'
    held = s & _HELD
    if held:
        return False, (f'we held a non-document ({sorted(held)}) — an abstract/landing page/wrong work '
                       f'is not a clean absence; pursue those before concluding')
    if s == {NOT_FOUND}:
        return True, ('every applicable route genuinely answered and none held an accessible copy — '
                      '"we did not locate an accessible copy" is licensed (event_ledger: SEARCHED_NONE)')
    return False, f'ambiguous outcome set {sorted(s)} — not a clean absence'


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# THE LIVE DRIVER — builds a query URL from the route and fires it THROUGH acquisition.Acquirer.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def build_probe_url(route_: Route, table: RouteTable, *, kind: str = 'search',
                    query: str = '', doi: str = '', limit: int = 3, **extra) -> str | None:
    """Fill a route's endpoint template. Returns None if the route has no such endpoint (many
    separate-work routes are discovery_via another route and have no direct search API)."""
    tmpl = (route_.endpoints or {}).get(kind)
    if not tmpl:
        return None
    params = {
        'query': urllib.parse.quote(query or ''),
        'doi': urllib.parse.quote(doi or '', safe=''),
        'mailto': urllib.parse.quote(table.mailto, safe='@.'),
        'limit': str(limit),
        **{k: urllib.parse.quote(str(v), safe='') for k, v in extra.items()},
    }
    try:
        return tmpl.format(**params)
    except KeyError:
        return None                          # template needs a param we do not have (e.g. an api key)


def _count_candidates(payload: Any) -> int | None:
    """Best-effort candidate count across the OA APIs' differing envelopes. Informational only."""
    if not isinstance(payload, dict):
        return None
    for path in (('meta', 'count'), ('hitCount',)):
        node = payload
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if isinstance(node, int):
            return node
    for k in ('results', 'records', 'studies', 'data'):
        v = payload.get(k)
        if isinstance(v, list):
            return len(v)
    msg = payload.get('message')
    if isinstance(msg, dict) and isinstance(msg.get('items'), list):
        return len(msg['items'])
    rl = payload.get('resultList')
    if isinstance(rl, dict) and isinstance(rl.get('result'), list):
        return len(rl['result'])
    return None


def live_index_probe(acq, table: RouteTable, route_: Route, unit: str, *,
                     query: str = '', doi: str = '', limit: int = 2) -> dict:
    """Fire ONE index/identity probe through Acquirer and report the TRANSPORT-level discovery outcome.

    This proves the wiring: the attempt is on the ledger, and the outcome is DERIVED from it (THROTTLED
    stays THROTTLED, a 404 stays NOT_FOUND). It is NOT a document fetch, so it never yields FETCHED —
    the document-level outcomes are exercised by the deterministic reducer demo. Kept to a handful, at
    Acquirer's per-host spacing, per Sol's "prove routing with a dry run + a few live probes."
    """
    kind = 'search' if 'search' in route_.endpoints else ('identity' if 'identity' in route_.endpoints else None)
    if not kind:
        return {'adapter': route_.adapter_id, 'skipped': 'no direct search/identity endpoint (discovery_via another route)'}
    url = build_probe_url(route_, table, kind=kind, query=query, doi=doi, limit=limit)
    if not url:
        return {'adapter': route_.adapter_id, 'skipped': 'endpoint needs an API key / param we do not hold'}
    r, payload = acq.get_json(unit, route_.adapter_id, url, tries=2, timeout=20)
    t = _transport_outcome(acq.ledger.events(unit), route_.adapter_id)
    label = 'ANSWERED' if t == 'RESPONDED' else t
    return {'adapter': route_.adapter_id, 'kind': kind, 'transport': label,
            'http': r.http_status, 'candidates': _count_candidates(payload),
            'url': url[:88] + ('…' if len(url) > 88 else '')}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# RENDERING — the dry-run report the task asks __main__ to print.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def render_plan(plan: RoutingPlan, table: RouteTable, *, title: str) -> str:
    L: list[str] = []
    W = 100
    L.append('═' * W)
    L.append(title)
    L.append('═' * W)
    j = ', '.join(f'{c} (from {p!r})' for c, p in plan.jurisdictions.items()) or 'none named — fire broadly'
    L.append(f'  citation policy : {plan.policy.name}  (may cite: {", ".join(plan.policy.permitted_expression_kinds)})')
    L.append(f'  jurisdictions   : {j}')
    L.append(f'  required roles  : {len(plan.required)}')
    for role, basis in plan.required.items():
        cover = plan.per_role.get(role) or []
        mark = '  ' if cover else '!!'
        L.append(f'    {mark} {role:<34} <- {basis}')
        L.append(f'         covered by: {", ".join(cover) if cover else "NOTHING (capability gap — reported, never a false evidence gap)"}')
    ev = [f for f in plan.fired if f.kind == 'evidence']
    inf = [f for f in plan.fired if f.kind == 'infrastructure']
    L.append('')
    L.append(f'  ROUTES THAT FIRE : {len(plan.fired)}   (evidence {len(ev)} · infrastructure {len(inf)})')
    L.append('  ── evidence routes ──────────────────────────────────────────────────────────────────')
    for f in sorted(ev, key=lambda x: (x.admissibility, x.adapter_id)):
        tag = 'CITABLE       ' if f.admissibility == 'citable' else 'discovery-only'
        L.append(f'    [{tag}] {f.adapter_id:<20} {",".join(f.covered_roles)}')
        L.append(f'                     └ {f.admissibility_reason}')
    L.append('  ── infrastructure (index / identity / locations) ────────────────────────────────────')
    L.append('    ' + ', '.join(f.adapter_id for f in inf))
    if plan.jurisdiction_filtered:
        L.append('  ── filtered by jurisdiction (supplied a role, wrong forum) ──────────────────────────')
        for r, why in plan.jurisdiction_filtered:
            L.append(f'    {r.adapter_id:<20} {why}')
    return '\n'.join(L)


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def route_question(question: str, *, question_id: int | None = None, use_llm: bool = False,
                   table: RouteTable | None = None) -> tuple[Any, RoutingPlan, RouteTable]:
    """Compile a contract (offline by default) and route it. Returns (contract, plan, table)."""
    from research_contract import compile_contract
    table = table or load_table()
    contract = compile_contract(question, question_id=question_id, use_llm=use_llm, verbose=False)
    return contract, route(table, contract), table


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# __main__ — the three routing dry-runs the task asks for, the NBER canary, and the outcome reducer.
# ════════════════════════════════════════════════════════════════════════════════════════════════════

# The three questions the standing order requires a mechanism to state its behaviour on — plus a
# thin-evidence one, where "the literature does not settle this" is the CORRECT answer. NONE of them is
# wired into the router: each is compiled to a contract and routed by the SAME data table.
_Q_TASK72 = ('Please write a literature review on the restructuring impact of Artificial Intelligence '
             '(AI) on the labor market. Focus on how AI, as a key driver of the Fourth Industrial '
             'Revolution, is causing significant disruptions and affecting various industries. Ensure '
             'the review only cites high-quality, English-language journal articles.')
_Q_CLINICAL = ('What is the comparative efficacy and cardiovascular safety of SGLT2 inhibitors versus '
               'GLP-1 receptor agonists in adults with type 2 diabetes? Synthesise the evidence from '
               'randomized controlled trials and current clinical practice guidelines.')
_Q_LEGAL = ('How have United States federal and state courts allocated tort liability for personal '
            'injuries caused by autonomous vehicle systems? Analyse the leading case law and the '
            'relevant federal statutes and regulations.')
_Q_THIN = ('What is known about the long-term neurological effects of chronic exposure to sub-acoustic '
           'infrasound from onshore wind turbines in human populations?')


def _words(n: int, seed: str = '') -> str:
    base = ('the estimated effect of automation on employment varies across occupations and industries '
            'with routine cognitive tasks most exposed while wages and productivity respond over the '
            'medium run subject to considerable uncertainty in the underlying identification strategy ')
    out = (seed + ' ') if seed else ''
    while len(out.split()) < n:
        out += base
    return ' '.join(out.split()[:n])


def _emit_fetch(L: Ledger, unit: str, adapter: str, text: str, *, requested_title: str = '',
                requested_authors: tuple[str, ...] = (), source_type: str = '') -> None:
    """A transport RESPONSE plus a recorded document — the shape acquisition.record_manifestation
    writes, minus the blob store. The content profile is computed by observe_text, exactly as in
    production, so the reducer sees a real profile and not a hand-set label."""
    rid = f'{adapter}#demo'
    L.emit(unit, EventKind.BACKEND_ATTEMPTED, 'router-demo', adapter=adapter, url='https://example/x',
           request_id=rid, attempt=1)
    L.emit(unit, EventKind.RESPONSE_RECEIVED, 'router-demo', adapter=adapter, url='https://example/x',
           request_id=rid, attempt=1, http_status=200, n_bytes=len(text.encode()))
    L.emit(unit, EventKind.MANIFESTATION_FETCHED, 'router-demo', adapter=adapter,
           locator='https://example/x', requested_title=requested_title,
           requested_authors=list(requested_authors), source_type=source_type)
    L.emit(unit, EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(text))


def _emit_transport(L: Ledger, unit: str, adapter: str, outcome: str) -> None:
    """A transport FAILURE with no document — the four ways an attempt can end without an answer."""
    rid = f'{adapter}#demo'
    L.emit(unit, EventKind.BACKEND_ATTEMPTED, 'router-demo', adapter=adapter, url='https://example/x',
           request_id=rid, attempt=1)
    if outcome == THROTTLED:
        L.emit(unit, EventKind.THROTTLED, 'router-demo', adapter=adapter, url='https://example/x',
               request_id=rid, attempt=1, http_status=429)
    elif outcome == ACCESS_DENIED:
        L.emit(unit, EventKind.BLOCKED, 'router-demo', adapter=adapter, url='https://example/x',
               request_id=rid, attempt=1, http_status=403)
    elif outcome == NOT_FOUND:
        L.emit(unit, EventKind.RESPONSE_RECEIVED, 'router-demo', adapter=adapter, url='https://example/x',
               request_id=rid, attempt=1, http_status=404, n_bytes=0)
    elif outcome == TRANSIENT_ERROR:
        L.emit(unit, EventKind.RESPONSE_RECEIVED, 'router-demo', adapter=adapter, url='https://example/x',
               request_id=rid, attempt=1, transport_error='TimeoutError', reason_text='timed out')


def _demo_outcomes() -> int:
    """Build one synthetic ledger that exercises ALL NINE discovery outcomes, DERIVE each from the
    ledger, and prove the absence-licensing invariant: only NOT_FOUND everywhere licenses absence; one
    429 never does. Deterministic, offline, and it fails loud if any mapping drifts."""
    print('\n' + '═' * 100)
    print('DISCOVERY-OUTCOME REDUCER — nine distinct outcomes, each DERIVED from the ledger (no asserts)')
    print('═' * 100)
    L = Ledger()   # in-memory, no path: this derives, it does not persist

    cases: list[tuple[str, str, str]] = []   # (unit, adapter, expected)
    _emit_fetch(L, 'w:fulltext', 'europe_pmc',
                _words(1600, 'Effects of Automation on Employment. By Daron Acemoglu and Pascual Restrepo.'),
                requested_title='Effects of Automation on Employment', requested_authors=('Acemoglu',),
                source_type='journal-article')
    cases.append(('w:fulltext', 'europe_pmc', FETCHED))

    _emit_fetch(L, 'w:opinion', 'courtlistener',
                'Doe v. Acme Autonomous Systems. Held: the operator of an autonomous vehicle system '
                'bears liability for a foreseeable failure it did not disclose. The judgment of the '
                'district court is affirmed.',
                requested_title='Doe v Acme Autonomous Systems Liability', source_type='opinion')
    cases.append(('w:opinion', 'courtlistener', FETCHED))   # complete at 40 words — a judicial opinion

    _emit_fetch(L, 'w:abstract', 'openalex', _words(300, 'Automation and Wages. By A. Author.'),
                requested_title='Automation and Wages', requested_authors=('Author',),
                source_type='journal-article')
    cases.append(('w:abstract', 'openalex', ABSTRACT_ONLY))

    _emit_fetch(L, 'w:stub', 'crossref', 'Automation and Wages. Journal of Labor Economics 2021.',
                requested_title='Automation and Wages', requested_authors=('Author',),
                source_type='journal-article')
    cases.append(('w:stub', 'crossref', NOT_FOUND))         # a citation stub is not an accessible copy

    _emit_fetch(L, 'w:landing', 'pmc',
                'This website uses cookies. Accept all cookies. Subscribe to read the full article. '
                'Sign in to continue. Privacy policy. Terms of use. All rights reserved.',
                requested_title='Automation and Wages', source_type='journal-article')
    cases.append(('w:landing', 'pmc', LANDING_PAGE))

    _emit_fetch(L, 'w:corrupt', 'core', '(cid:3) (cid:7) (cid:12) (cid:19) ' * 80,
                requested_title='Automation and Wages', source_type='journal-article')
    cases.append(('w:corrupt', 'core', CORRUPT_EXTRACTION))

    _emit_fetch(L, 'w:wrong', 'openalex',
                'Mathematics and the Rise of the Machines: Automated Theorem Proving. By Yang-Hui He. '
                'This paper develops a neural approach to formal proof search in algebraic geometry.',
                requested_title='rise machines', requested_authors=('Parry',),
                source_type='journal-article')
    cases.append(('w:wrong', 'openalex', WRONG_WORK))

    _emit_transport(L, 'w:denied', 'arxiv', ACCESS_DENIED)
    cases.append(('w:denied', 'arxiv', ACCESS_DENIED))
    _emit_transport(L, 'w:throttled', 'crossref', THROTTLED)
    cases.append(('w:throttled', 'crossref', THROTTLED))
    _emit_transport(L, 'w:timeout', 'doaj', TRANSIENT_ERROR)
    cases.append(('w:timeout', 'doaj', TRANSIENT_ERROR))
    _emit_transport(L, 'w:missing', 'openalex', NOT_FOUND)
    cases.append(('w:missing', 'openalex', NOT_FOUND))

    ok = True
    for unit, adapter, expected in cases:
        got, basis = classify_discovery_outcome(L, unit, adapter)
        flag = 'ok ' if got == expected else 'XX '
        ok = ok and got == expected
        print(f'  {flag}{got:<18} (expected {expected:<18}) {adapter:<13} {unit}')
        print(f'       └ {basis[:92]}')
    if not ok:
        print('\n  !! A DISCOVERY-OUTCOME MAPPING DRIFTED — see the XX rows above.')
        return 1

    print('\n  ── absence-licensing invariant (the 429-is-never-a-gap rule, at the discovery layer) ──')
    scenarios = [
        ('every applicable route answered 404', [NOT_FOUND, NOT_FOUND, NOT_FOUND]),
        ('same, but ONE route was throttled',   [NOT_FOUND, NOT_FOUND, THROTTLED]),
        ('same, but ONE route was blocked',     [NOT_FOUND, ACCESS_DENIED]),
        ('one route returned an abstract',      [NOT_FOUND, ABSTRACT_ONLY]),
        ('a copy was fetched',                  [FETCHED, NOT_FOUND]),
        ('an applicable route was never tried', [NOT_FOUND, NO_ATTEMPT]),
    ]
    inv_ok = True
    for label, outs in scenarios:
        lic, why = licenses_absence(outs)
        expect = (label == 'every applicable route answered 404')
        flag = 'ok ' if lic == expect else 'XX '
        inv_ok = inv_ok and lic == expect
        print(f'  {flag}absence {"LICENSED " if lic else "REFUSED  "} :: {label}')
        print(f'       └ {why[:92]}')
    return 0 if (ok and inv_ok) else 1


def _live_probes(table: RouteTable) -> None:
    """A handful of REAL index/identity probes through acquisition.Acquirer — proof of wiring, not a
    crawl. Each lands on a throwaway ledger; the transport-level outcome is DERIVED from it. Failures
    (a locked-down egress, a rate limit) print as the honest outcome, never as a router error."""
    import tempfile
    from acquisition import Acquirer, BlobStore
    print('\n' + '═' * 100)
    print('LIVE PROBES THROUGH acquisition.Acquirer (index/identity only; a few, politely spaced)')
    print('═' * 100)
    tmp = Path(tempfile.mkdtemp(prefix='sr_probe_'))
    acq = Acquirer('source_router.live_probe', ledger=Ledger(tmp / 'ledger.jsonl'),
                   blobs=BlobStore(tmp / 'blobs'))
    probes = [
        ('openalex', 'search', dict(query='artificial intelligence labor market', limit=2)),
        ('crossref', 'identity', dict(doi='10.1257/aer.103.5.1553')),
        ('unpaywall', 'identity', dict(doi='10.1257/aer.103.5.1553')),
        ('doaj', 'search', dict(query='artificial intelligence employment', limit=2)),
        ('europe_pmc', 'search', dict(query='SGLT2 inhibitors cardiovascular', limit=2)),
        ('clinicaltrials_gov', 'search', dict(query='SGLT2 inhibitors type 2 diabetes', limit=2)),
        ('courtlistener', 'search', dict(query='autonomous vehicle liability', limit=2)),
    ]
    for adapter_id, _kind, params in probes:
        r = table.by_id(adapter_id)
        if r is None:
            continue
        try:
            res = live_index_probe(acq, table, r, f'probe:{adapter_id}', **params)
        except Exception as e:                 # a probe may fail; the router must not
            res = {'adapter': adapter_id, 'error': f'{type(e).__name__}: {str(e)[:60]}'}
        if 'skipped' in res:
            print(f'  --  {adapter_id:<20} skipped: {res["skipped"]}')
        elif 'error' in res:
            print(f'  ..  {adapter_id:<20} {res["error"]}')
        else:
            cand = res.get('candidates')
            cand_s = f'{cand} candidates' if cand is not None else 'candidates: n/a'
            print(f'  ->  {adapter_id:<20} {res["transport"]:<16} http={res.get("http")}  {cand_s}')
    print(f'\n  ledger: {tmp / "ledger.jsonl"}  (every attempt above is on it, distinct and un-collapsible)')


def main() -> int:
    ap = argparse.ArgumentParser(description='Capability-based, data-driven OA-first source router.')
    ap.add_argument('--live', action='store_true', help='also fire a handful of real probes through Acquirer')
    ap.add_argument('--routes', action='store_true', help='print the route table as loaded, then exit')
    ap.add_argument('--llm', action='store_true', help='compile contracts with the LLM (default: offline regex)')
    ap.add_argument('--question', help='route a single ad-hoc question and exit')
    args = ap.parse_args()

    table = load_table()
    print(f'route table: {ROUTES_YAML}')
    print(f'  {len(table.routes)} routes · {len(table.roles)} evidence roles · '
          f'{len(table.role_requirements)} requirement rules · registry {table.registry_version}')

    if args.routes:
        for r in table.routes:
            print(f'\n  {r.adapter_id}')
            print(f'     roles     : {", ".join(r.evidence_roles)}')
            print(f'     doc_types : {", ".join(r.document_types)}')
            print(f'     coverage  : {", ".join(r.jurisdiction_coverage)}')
            print(f'     resolvers : {", ".join(r.version_resolvers) or "-"}')
            print(f'     note      : {r.coverage_note}')
        return 0

    from research_contract import compile_contract

    def _plan(q: str, title: str, qid: int | None = None) -> RoutingPlan:
        c = compile_contract(q, question_id=qid, use_llm=args.llm, verbose=False)
        p = route(table, c)
        print('\n' + render_plan(p, table, title=title))
        return p

    if args.question:
        _plan(args.question, f'AD-HOC QUESTION: {args.question[:70]}')
        return 0

    p72 = _plan(_Q_TASK72, 'DRY-RUN 1 · TASK 72 (AI × labor market, journal-only)', qid=72)
    pcl = _plan(_Q_CLINICAL, 'DRY-RUN 2 · CLINICAL (SGLT2 vs GLP-1, type 2 diabetes)')
    plg = _plan(_Q_LEGAL, 'DRY-RUN 3 · LEGAL (US tort liability, autonomous vehicles)')
    pth = _plan(_Q_THIN, 'DRY-RUN 4 · THIN EVIDENCE (infrasound & neurology — absence may be the answer)')

    # ── THE CANARY. "If the clinical question routes to NBER, IT IS BROKEN and you must say so." ──
    print('\n' + '═' * 100)
    print('CANARY — a CLINICAL plan must NOT acquire the economics working-paper channel')
    print('═' * 100)
    econ = [a for a in ('nber', 'iza', 'repec') if pcl.fires(a)]
    if econ:
        print(f'  !!!! BROKEN !!!!  the clinical plan fired {econ} — an economics working-paper route on a '
              f'clinical question.')
        print('  This is the exact "domain baked into code" failure. The router is WRONG. Do not ship it.')
        broken = True
    else:
        print('  PASS  the clinical plan fires NO economics working-paper route (nber/iza/repec).')
        print(f'        clinical evidence routes: {[f.adapter_id for f in pcl.fired if f.kind == "evidence"]}')
        # and the contrast that proves the routing is real, not a blanket suppression:
        print(f'        task-72 (economics) DOES fire nber={p72.fires("nber")} '
              f'(as {[f.admissibility for f in p72.fired if f.adapter_id == "nber"]}) — correct: task 72 IS economics')
        print(f'        legal plan fires nber={plg.fires("nber")} (must be False); '
              f'case-law route courtlistener={plg.fires("courtlistener")} (must be True)')
        broken = plg.fires('nber') or not plg.fires('courtlistener') or not pcl.fires('clinicaltrials_gov')

    rc = _demo_outcomes()

    if args.live:
        _live_probes(table)

    if broken or rc:
        print('\nRESULT: FAIL — see the flagged lines above.')
        return 1
    print('\nRESULT: PASS — routing is capability-derived, the clinical/legal plans avoid NBER, and all '
          'nine discovery outcomes derive correctly from the ledger.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
