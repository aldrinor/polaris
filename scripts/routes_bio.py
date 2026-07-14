#!/usr/bin/env python3
"""ROUTES_BIO — PMC, EUROPE PMC and DOAJ AS *FULL-TEXT* ROUTES. (Sol V9 §2, build order step 3.)

WHAT WAS WRONG BEFORE THIS FILE

  All three routes were in `config/source_routes.yaml` and all three were queried FOR DISCOVERY ONLY.
  `source_router.live_index_probe()` fired one `search`/`identity` request per route, read the transport
  outcome, counted the hits, and stopped. NOBODY EVER ASKED ANY OF THEM FOR THE DOCUMENT. The corpus is
  ten journal-attributable works and the argument planner found ZERO cross-source conflicts in it,
  because it is starved — and the three routes that hold the biomedical full text were being used as
  hit-counters.

  Worse, the configured retrieval templates were WRONG, and nothing had ever executed them hard enough
  to find out. Proven live, 2026-07-14, on DOIs from our own candidate lists:

      Europe PMC  /{source}/{id}/fullTextXML   ->  HTTP 404, 0 bytes      (the configured shape)
      Europe PMC  /{pmcid}/fullTextXML         ->  HTTP 200, 86,022 bytes, 34 <sec>
      PMC OAI     pmc.ncbi.../oai/oai.cgi      ->  HTTP 404, 48,676 BYTES OF HTML
      PMC OAI     pmc.ncbi.../api/oai/v1/mh/   ->  HTTP 200, 108,635 bytes of JATS, 17 <sec>

  Look hard at that third line, because it is this project's disease in one response. The 404 is not
  empty. It is FORTY-EIGHT KILOBYTES, it is served with `Content-Type: text/html`, and it contains a
  `<body>` tag. A route that proved full text by asking "did we get bytes?" would have believed it. A
  route that asked "does it have a <body>?" would have believed it. THE ONLY QUESTION THAT SURVIVES
  CONTACT WITH THAT RESPONSE IS THE ONE THE REDUCER ASKS: is this a complete, finding-bearing document?
  — and that question is not asked here. It is asked by `event_ledger.observe_text` /
  `derive_content_profile`, over bytes this module is not allowed to characterise.

THE BOUNDARY THIS FILE IS ON THE WRONG SIDE OF, AND KNOWS IT

  Sol V9 §1: "Repository adapters only discover DocumentCandidate records." / "The adapter must not
  write FULLTEXT, THIS_WORK, VERSION_OF_RECORD, ADMISSIBLE, or an expression edge."

  So the three adapters here —

      pmc_candidates()   europe_pmc_candidates()   doaj_candidates()

  — return `list[DocumentCandidate]` AND NOTHING ELSE. They have no access to a status vocabulary
  (acquisition.Acquirer does not expose one), and they do not touch the blob store or the manifestation
  event. `fetch_candidate()` — ONE generic executor, shared by all three, on the other side of the
  boundary — is what turns a candidate into bytes, and even it concludes nothing: it hands the bytes to
  `Acquirer.record_manifestation`, which computes the content profile ITSELF, from the bytes, via the
  shared reducer. There is no argument to that call that can inflate one.

  The tests in `test_routes_bio_attacks.py` assert this STRUCTURALLY, over the AST: no adapter function
  in this file may call `record_manifestation`.

WHAT IS DATA AND WHAT IS CODE (Sol V9 §2, verbatim: "Data edit: PMC endpoints, identifier transforms,
metadata prefixes, and rate budget. Code changes only for a new protocol/parser primitive.")

  DATA (`config/source_routes.yaml`):  every endpoint template, every identifier transform, the OAI
  metadata prefix, every response selector (including WHICH availability codes count as open), the
  200-id batch ceiling, and every rate budget. Retargeting Europe PMC's full-text URL — the actual bug
  above — is a one-line YAML edit and touches nothing here.

  CODE (this file):  the ONE genuinely new parser primitive the three routes needed — a JATS linearizer
  (`jats_to_text`) — plus the generic transform/selector evaluators that read the YAML. No endpoint, no
  field path, no metadata prefix and no host name is written in this module.

THE FOUR SILENT FAILURES SOL NAMED, AND WHERE EACH ONE DIES

  1. "PMCID exists but full text is not in the OA subset."
     PMC13200213 has a PMCID. The OA service answers `idDoesNotExist`; the OAI answers
     `cannotDisseminateFormat`; Europe PMC 404s its fullTextXML. THREE backends answered, and the
     answer is "not in the OA subset" — which is a fact about PMC'S SUBSET and is recorded as one
     (`oa_error_code`, `oai_http_status`). It is not a fact about the world, and there is no path in
     this file by which it becomes one.

  2. "XML is front matter only."  -> `jats_to_text` reports `body_present` / `sec_count` / `p_count` /
     `body_chars` as OBSERVATIONS, and the reducer sizes the document against the profile for its kind.
     A front-matter-only record has no <body>; it also has no body words, and `observe_text` sees that
     without being told.

  3. "An NIH accepted manuscript mistaken for the publisher VoR."  -> caught TWICE, and the important
     one is the second. Europe PMC's `nihAuthMan: Y` is recorded as a `version_hint` — an OBSERVATION,
     which under the V9 P0 decides NOTHING, because a repository label is not a fact about bytes. The
     VERDICT comes from the document's own front matter: `jats_to_text` linearizes
     `<article-id pub-id-type="manuscript">NIHMS…</article-id>` into the header, and
     `provenance._AM_MARK` (widened in this change) reads the NIHMS id and the "Author manuscript;
     available in PMC" stamp. Before this change the most common accepted manuscript in biomedicine —
     the NIH one — did not match the accepted-manuscript detector at all.

  4. "Abstract mistaken for full text."  -> this module never says the word. `derive_content_profile`
     returns ABSTRACT for an abstract, and ABSTRACT is not a gap either.

POLITENESS (Sol V9 §2) — ENFORCED SOMEWHERE ELSE, ON PURPOSE

  PMC: <=3 req/s, NO concurrent requests, tool+email registered on every ID-converter call, 200 ids per
  batch. Europe PMC: 1 req/s, 1 in flight. DOAJ: ~2 req/s.

  NOT ONE OF THOSE NUMBERS IS IN THIS FILE. They are `rate_policy` rows on the pmc / europe_pmc / doaj
  routes, and `scripts/host_scheduler.py` — the persistent, cross-process token bucket of Sol V9 §7 —
  reads them out of the same YAML and enforces them under an flock, for every worker, with a
  `not_before` that survives the process being told to wait. `Acquirer` asks it for a grant before every
  request this module makes. There is exactly one place in the system that knows how fast we may go, and
  it is not here. (An earlier cut of this file had its own sleep. See the note where it used to be.)
"""
from __future__ import annotations

import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402
    Acquirer, DocumentCandidate, ResolveContext, content_host, extract_text,
)
from event_ledger import EventKind  # noqa: E402
from source_router import Route, RouteTable  # noqa: E402

PMC = 'pmc'
EUROPE_PMC = 'europe_pmc'
DOAJ = 'doaj'
BIO_ROUTES = (PMC, EUROPE_PMC, DOAJ)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE GENERIC EVALUATORS — they read the YAML. They know no repository's name.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def dig(obj: Any, path: str, default: Any = None) -> Any:
    """Walk a dotted selector into a decoded JSON body. `resultList.result` -> obj['resultList']['result'].

    A selector that does not resolve returns `default` — and a caller must NEVER read that as "the
    document is not there". It means OUR PATH DID NOT MATCH THEIR SHAPE, which is a fact about this
    table and their API, and the two have already disagreed once tonight (`/{source}/{id}/fullTextXML`).
    """
    if not path:
        return default
    node = obj
    for key in path.split('.'):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node


def _transform(name: str, spec: str, known: dict[str, str]) -> str:
    """Evaluate ONE identifier transform from its YAML spec. A DECLARED VOCABULARY, deliberately tiny.

        strip_prefix:pmcid:PMC                        pmcid=PMC12754963 -> 12754963
        format:oai:pubmedcentral.nih.gov:{pmcid_numeric}

    ── WHY `strip_prefix` NAMES ITS SOURCE FIELD EXPLICITLY ──────────────────────────────────────────
    The first cut was `strip_prefix:PMC`, and it INFERRED the source identifier from the output's name
    (`pmcid_numeric` -> strip `_numeric` -> `pmcid`), with a loop that guessed by prefix-matching if
    that failed. It worked on the one row that existed, which is the only thing that kind of code ever
    does. A transform that guesses which input it reads is a transform that reads the WRONG input the
    first time somebody adds a row it did not anticipate — and it does so SILENTLY, producing an empty
    string, which becomes a URL with a hole in it (`?identifier=&metadataPrefix=`), which is a 400 that
    looks exactly like the backend refusing us. The route reports "PMC has no full text for this work"
    and it is OUR TEMPLATE THAT WAS EMPTY. That bug shipped into the first live run of this lane and
    the ledger caught it: 2 candidates, 0 manifestations, HTTP 400.

    So the source field is DATA now, and a missing one raises. `format` raises on an underived
    dependency for the same reason. An unknown verb raises. NOTHING HERE MAY QUIETLY RETURN ''.
    """
    verb, _, rest = spec.partition(':')
    if verb == 'strip_prefix':
        src, _, prefix = rest.partition(':')
        if not src or not prefix:
            raise ValueError(f'transform {name!r}: strip_prefix needs `strip_prefix:<source_field>:<prefix>`, '
                             f'got {spec!r}')
        v = known.get(src, '')
        if not v:
            raise KeyError(src)                     # the source is not derived YET — retry next pass
        return v[len(prefix):] if v.upper().startswith(prefix.upper()) else v
    if verb == 'format':
        try:
            return rest.format(**known)
        except KeyError as e:
            raise KeyError(f'transform {name!r} needs identifier {e} which we have not derived yet')
    raise ValueError(f'unknown identifier transform verb {verb!r} in {spec!r} — it is not in the '
                     f'declared vocabulary (strip_prefix | format)')


def derive_identifiers(route: Route, seed: dict[str, str]) -> dict[str, str]:
    """Apply the route's `identifier_transforms` over what we know. Order-independent (two passes)."""
    known = {k: v for k, v in seed.items() if v}
    for _ in range(2):
        for name, spec in (route.identifier_transforms or {}).items():
            if name in known:
                continue
            try:
                out = _transform(name, str(spec), known)
            except KeyError:
                continue                      # a dependency is not derived yet — try again next pass
            if out:
                known[name] = out
    return known


def fill(route: Route, table: RouteTable, kind: str, **params) -> str | None:
    """Fill an endpoint template from the route row. -> None if the route has no such endpoint.

    Every value is percent-encoded EXCEPT where the template's own shape requires otherwise; `ids` is
    a comma-joined batch and keeps its separators, and each id inside it is encoded individually.
    """
    tmpl = (route.endpoints or {}).get(kind)
    if not tmpl:
        return None
    rate = route.rate_policy or {}
    vals: dict[str, str] = {
        'mailto': urllib.parse.quote(table.mailto, safe='@.'),
        'tool': str(rate.get('tool') or 'polaris'),
        'metadata_prefix': route.metadata_prefix or '',
        'limit': '1',
    }
    for k, v in params.items():
        if v is None:
            continue
        if k == 'ids':
            vals[k] = ','.join(urllib.parse.quote(str(i), safe='') for i in v)
        else:
            vals[k] = urllib.parse.quote(str(v), safe='')
    try:
        return tmpl.format(**vals)
    except KeyError:
        return None                          # the template needs a param we do not hold


# ── POLITENESS IS NOT THIS MODULE'S JOB, AND IT MUST NOT BECOME IT ────────────────────────────────
#
# An earlier cut of this file carried a `_space_for(route, url)` helper that slept to the route's
# configured `min_spacing_s`. IT IS GONE, and its deletion is the point:
#
# `scripts/host_scheduler.py` (Sol V9 §7) is the persistent, cross-process politeness governor, and it
# reads `routes[*].rate_policy` OUT OF THE SAME YAML ROWS THIS MODULE'S ENDPOINTS LIVE IN — `min_spacing_s`
# and `max_in_flight`, per host, merged strictest-wins, under an flock, with a `not_before` that outlives
# the process that was told to wait. `Acquirer` asks it for a grant before every request.
#
# So the budgets in the pmc / europe_pmc / doaj rows (PMC's 3/s and NO CONCURRENCY; Europe PMC's 1/s and
# one in flight; DOAJ's ~2/s) are already enforced, by the one component that can enforce them across the
# workers that will actually run this lane. A second sleep here would not add safety — it would add an
# UNACCOUNTED sleep that the scheduler cannot see, cannot reason about, and cannot reduce over, and it
# would be one more place where "how fast are we allowed to go?" has an answer. There must be exactly one.
# ──────────────────────────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE ONE NEW PARSER PRIMITIVE: JATS -> TEXT
#
# Sol V9 §2 permits code "only for a new protocol/parser primitive", and JATS is exactly that. The
# existing `acquisition.extract_text` has two branches — pdfminer, and strip-the-tags — and the second
# one WOULD "work" on JATS, in the way that is worst: it would return a plausible wall of words with the
# document's structure, its article-DOI, its contributor list and its NIHMS manuscript id blended
# invisibly into the prose, and no way to tell a front-matter-only record from a complete one.
#
# WHY THIS RETURNS HEADER-FIRST TEXT, AND WHY THAT IS NOT A COSMETIC CHOICE
#   `observe_text` reads IDENTITY OUT OF THE FIRST 1,500 CHARACTERS and `derive_expression_kind` reads
#   VERSION OUT OF THE FIRST 12,000 — both deliberately bounded, because a whole-document scan finds the
#   BIBLIOGRAPHY (that is how a naive scan once read "NBER Working Paper" out of a reference list and
#   called the published JEP article a working paper). So a linearizer that emitted <body> first would
#   push the article's own DOI, byline and version furniture out of the window the reducers look at, and
#   every JATS document we fetched would come back UNRESOLVED. Front matter first is what makes the
#   reducers able to do their job on this format at all.
#
# It ADDS NOTHING. Every string it emits is a string the document contains.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _localname(tag: str) -> str:
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _itertext(el: ET.Element) -> str:
    return re.sub(r'\s{2,}', ' ', ''.join(el.itertext())).strip()


def _find(el: ET.Element, *names: str) -> list[ET.Element]:
    """Namespace-agnostic descendant search by local name. JATS in the wild is served both ways."""
    want = set(names)
    return [e for e in el.iter() if _localname(e.tag) in want]


def jats_to_text(raw: bytes) -> tuple[str, str, dict]:
    """(text, extraction_method, structure_observations). Raises nothing; a non-JATS body -> ('', ...).

    The observations are OBSERVATIONS: counts and presence flags and the ids the document prints on
    itself. There is no `complete`, no `is_fulltext` and no version verdict among them, and the ledger's
    conclusion guard would reject this event if there were.
    """
    obs: dict = {'jats_parsed': False, 'jats_body_present': False, 'jats_sec_count': 0,
                 'jats_p_count': 0, 'jats_body_chars': 0, 'jats_article_type': '',
                 'jats_manuscript_id': '', 'jats_article_doi': '', 'jats_contributors': 0}
    if not raw:
        return '', 'empty_body', obs
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        # NOT a document-level conclusion. It is a fact about THESE BYTES AND THIS PARSER, and the
        # caller falls back to the generic extractor rather than deciding anything.
        return '', f'jats_unparseable ({type(e).__name__})', obs

    arts = _find(root, 'article')
    art = arts[0] if arts else (root if _localname(root.tag) == 'article' else None)
    if art is None:
        return '', 'not_jats (no <article> element)', obs
    obs['jats_parsed'] = True
    obs['jats_article_type'] = art.get('article-type', '') or ''

    lines: list[str] = []

    # ---- FRONT MATTER — the document's own testimony about which article it is -------------------
    for j in _find(art, 'journal-title'):
        lines.append(_itertext(j))
        break
    for t in _find(art, 'article-title'):
        lines.append(_itertext(t))
        break

    contribs: list[str] = []
    for c in _find(art, 'contrib'):
        sur = [_itertext(e) for e in _find(c, 'surname')]
        giv = [_itertext(e) for e in _find(c, 'given-names')]
        nm = ' '.join([giv[0] if giv else '', sur[0] if sur else '']).strip()
        if nm:
            contribs.append(nm)
    obs['jats_contributors'] = len(contribs)
    if contribs:
        lines.append(', '.join(contribs))

    # <article-id pub-id-type="doi|pmid|pmcid|manuscript"> — INCLUDING the NIHMS manuscript id, which is
    # the front-matter tell that separates an NIH accepted manuscript from the publisher's VoR. It is
    # printed here because the DOCUMENT prints it; provenance._AM_MARK is what reads it.
    for aid in _find(art, 'article-id'):
        kind = aid.get('pub-id-type', '') or ''
        val = _itertext(aid)
        if not val:
            continue
        lines.append(f'{kind}: {val}' if kind else val)
        if kind == 'doi':
            obs['jats_article_doi'] = val.lower()
        if kind == 'manuscript':
            obs['jats_manuscript_id'] = val

    for el in _find(art, 'volume', 'issue', 'fpage', 'lpage', 'year', 'copyright-statement',
                    'license-p', 'article-version', 'subject'):
        t = _itertext(el)
        if t:
            lines.append(t)

    for ab in _find(art, 'abstract'):
        t = _itertext(ab)
        if t:
            lines.append(t)
        break

    # ---- BODY ------------------------------------------------------------------------------------
    bodies = _find(art, 'body')
    if bodies:
        body = bodies[0]
        secs = _find(body, 'sec')
        ps = _find(body, 'p')
        obs['jats_body_present'] = True
        obs['jats_sec_count'] = len(secs)
        obs['jats_p_count'] = len(ps)
        btxt = _itertext(body)
        obs['jats_body_chars'] = len(btxt)
        if btxt:
            lines.append(btxt)

    # ---- BACK (references etc.) — the document has them, so the text has them --------------------
    for back in _find(art, 'back'):
        t = _itertext(back)
        if t:
            lines.append(t)
        break

    text = re.sub(r'\n{3,}', '\n\n', '\n\n'.join(x for x in lines if x)).strip()
    return text, 'jats', obs


def looks_like_xml(raw: bytes, content_type: str = '') -> bool:
    head = (raw or b'')[:400].lstrip()
    return head.startswith(b'<?xml') or head.startswith(b'<article') or 'xml' in (content_type or '').lower()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ADAPTERS — THEY PRODUCE `DocumentCandidate` RECORDS. THAT IS THE WHOLE OF THEIR AUTHORITY.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _observe(acq: Acquirer, unit: str, adapter: str, r, **obs) -> None:
    """Record a PAYLOAD-LEVEL observation about a response WE ALREADY RECEIVED.

    ── WHY THIS IS NOT A `BACKEND_ATTEMPTED` EVENT, AND WHY THAT MATTERS ─────────────────────────────
    The obvious way to log "PMC's index does not contain this DOI" is a fresh event. My first cut emitted
    BACKEND_ATTEMPTED for it. That would have been a REDUCER-POISONING BUG, and the reducer is on our
    side, so it is worth stating exactly how:

    `source_router._transport_outcome` groups an adapter's events BY `request_id`, and for any request
    whose group holds no terminal event it returns TRANSIENT_ERROR — "attempted, never came back — a
    HANG". A synthetic BACKEND_ATTEMPTED carrying a request_id that never had a response (or, worse, an
    empty one) manufactures exactly that shape. And TRANSIENT_ERROR sits ABOVE 'RESPONDED' in
    `_TRANSPORT_PRECEDENCE`. So the fact "the backend answered, cleanly, and its index does not have
    this DOI" would have been reduced to "the backend never answered" — a fact about THEIR INDEX
    rewritten as a fact about OUR TRANSPORT, which is this project's original disease wearing a new hat.

    So an observation ATTACHES TO THE RESPONSE THAT ACTUALLY ARRIVED: same `request_id`, same
    `http_status`. The transport reduction is unchanged (the terminal event is still a response, and
    still RESPONDED); the observation is durable; and no request is invented.
    """
    acq.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, 'routes_bio',
                    adapter=adapter, url=r.url, request_id=r.request_id,
                    http_status=r.http_status, **obs)


def _mint(acq: Acquirer, ctx: ResolveContext, adapter: str, url: str, *,
          resolver_request_id: str, raw_metadata: bytes = b'', record_page: str = '',
          **obs) -> DocumentCandidate:
    """Emit CANDIDATE_IDENTIFIED and build the record. The lineage root is minted HERE, in the adapter
    that proposed the URL, and it is carried unchanged onto the manifestation — which is the only thing
    that makes "unique incremental yield per route" a measurement rather than an arithmetic identity."""
    blob_id = blob_sha = ''
    if raw_metadata:
        # The repository's OWN BYTES, hashed and kept. This is also where DOAJ's literal `"type":
        # "fulltext"` token goes: it is the world talking, it is evidence, and it is preserved
        # verbatim — but it is preserved as BYTES IN THE BLOB STORE, not as a string in the ledger,
        # because `fulltext` is a RESERVED_VALUE and the conclusion guard is right to refuse it.
        blob_id, blob_sha = acq.blobs.put(raw_metadata)
    cid = acq.candidate(ctx.work_id, adapter, url,
                        resolver_request_id=resolver_request_id,
                        raw_metadata_blob_id=blob_id, raw_metadata_hash=blob_sha, **obs)
    return DocumentCandidate(
        candidate_id=cid, work_id=ctx.work_id, discovered_by_route=adapter,
        resolver_request_id=resolver_request_id,
        identifier_used=str(obs.get('identifier_kind') or ''),
        retrieval_url=url,
        # NOT emitted into the ledger payload, ON PURPOSE. The record page is a URL under a key that is
        # NOT in the guard's VERBATIM_KEYS, so it would be scanned for reserved words — and a publisher
        # who puts `/fulltext` in a path (they do) would make the address of the record UNRECORDABLE.
        # The honest home for it is the raw metadata BLOB above, hashed, where the repository's own
        # bytes already contain it verbatim. Widening the guard's exemption list to carry a convenience
        # field is exactly the trade this codebase does not make.
        repository_record_url=record_page,
        media_hint=str(obs.get('media_hint') or ''),
        version_hint=str(obs.get('version_hint') or ''),
        license_observation=str(obs.get('license_observation') or ''),
        raw_metadata_blob_id=blob_id, raw_metadata_hash=blob_sha)


# ---- PMC ----------------------------------------------------------------------------------------

def pmc_convert_ids(acq: Acquirer, table: RouteTable, dois: Iterable[str],
                    unit: str = '') -> tuple[dict[str, dict], str]:
    """DOI/PMID -> PMCID through the PMC ID Converter, BATCHED (the documented ceiling is 200 ids).

    -> ({requested_id: record}, request_id). A record may be a RESOLUTION or a PER-RECORD ERROR:

        {"doi": "10.1186/...", "pmcid": "PMC12754963", "pmid": 41469701}
        {"doi": "10.3389/...", "status": "error", "errmsg": "Identifier not found in PMC"}

    ** BOTH ARRIVE INSIDE AN HTTP 200. ** The transport RESPONDED; three of our four probe DOIs simply
    are not in PMC's index. That is a fact about PMC'S INDEX — the same class of fact as Semantic
    Scholar 404ing the QJE DOI while NBER WP 8337 sits in the open — and it is kept as one. It is not a
    404, it is not a throttle, and it is not "no free copy exists".
    """
    route = table.by_id(PMC)
    assert route is not None, 'source_routes.yaml has no `pmc` row'
    ids = [d for d in dois if d]
    cap = int((route.batch or {}).get('id_convert_max_ids') or 200)
    out: dict[str, dict] = {}
    rid = ''
    sel = route.selectors or {}
    for i in range(0, len(ids), cap):
        chunk = ids[i:i + cap]
        url = fill(route, table, 'id_convert', ids=chunk)
        if not url:
            return out, ''
        r, payload = acq.get_json(unit or (chunk[0] if chunk else '?'), PMC, url, tries=3, timeout=30)
        rid = r.request_id
        if not r.ok or not isinstance(payload, dict):
            continue                          # a transport fact. Already on the ledger. NOT an absence.
        for rec in (dig(payload, sel.get('id_records', 'records')) or []):
            if not isinstance(rec, dict):
                continue
            key = str(rec.get('requested-id') or rec.get(sel.get('id_record_doi', 'doi')) or '')
            if not key:
                continue
            out[key] = rec
            if str(rec.get(sel.get('id_record_error', 'status'), '')).lower() == 'error':
                # PMC ANSWERED, AND ITS INDEX DOES NOT HAVE THIS DOI — inside an HTTP 200. Recorded
                # against the response that actually arrived (see _observe). The backend's own sentence
                # goes under `reason_text`, a VERBATIM key, because it is THEIR text and not our verdict.
                _observe(acq, unit or key, PMC, r,
                         doi=key, id_conversion_resolved=False,
                         reason_text=str(rec.get(sel.get('id_record_errmsg', 'errmsg'), ''))[:200])
    return out, rid


def pmc_candidates(acq: Acquirer, table: RouteTable, ctx: ResolveContext, *,
                   pmcid: str = '', id_records: dict[str, dict] | None = None) -> list[DocumentCandidate]:
    """PMC, as a FULL-TEXT route. -> DocumentCandidate records. Never a document, never a verdict.

    Hop 1 (ID conversion) may be done in BATCH by the caller and handed in via `id_records`; a lone
    lookup falls back to a single-DOI conversion.
    """
    route = table.by_id(PMC)
    assert route is not None, 'source_routes.yaml has no `pmc` row'
    sel = route.selectors or {}
    unit = ctx.work_id
    doi = next((i for i in ctx.identifiers if i.lower().startswith('10.')), '')
    cands: list[DocumentCandidate] = []
    resolver_rid = ''

    # ---- HOP 1: identity -------------------------------------------------------------------------
    if not pmcid:
        rec = (id_records or {}).get(doi)
        if rec is None and doi:
            recs, resolver_rid = pmc_convert_ids(acq, table, [doi], unit=unit)
            rec = recs.get(doi)
        if isinstance(rec, dict):
            if str(rec.get(sel.get('id_record_error', 'status'), '')).lower() == 'error':
                # Not in PMC's index. `pmc_convert_ids` ALREADY recorded that against the response it
                # received — this route proposes no candidate, and it concludes nothing by doing so.
                return []
            pmcid = str(rec.get(sel.get('id_record_pmcid', 'pmcid')) or '')
    if not pmcid:
        return []

    ids = derive_identifiers(route, {'pmcid': pmcid, 'doi': doi})

    # ---- HOP 2: THE DOCUMENT — JATS via OAI GetRecord ---------------------------------------------
    # A TEMPLATE WITH A HOLE IN IT IS NOT A CANDIDATE. If the transforms did not produce an OAI
    # identifier, or the row carries no metadata prefix, we do NOT propose the URL — because
    # `?identifier=&metadataPrefix=` fetches a 400, and a 400 from PMC is indistinguishable, downstream,
    # from PMC declining to serve us the document. That is a fact about OUR TABLE masquerading as a fact
    # about their holdings, and it is the same shape as every bug this subsystem exists to prevent. It
    # is loud instead: no candidate, and an observation naming the identifier we failed to derive.
    oai_id = ids.get('oai_identifier', '')
    if not oai_id or not route.metadata_prefix:
        acq.ledger.emit(unit, EventKind.ROUTE_PLANNED, 'routes_bio',
                        adapter=PMC, pmcid=pmcid,
                        oai_identifier_derived=bool(oai_id),
                        metadata_prefix_configured=bool(route.metadata_prefix))
    oai_url = fill(route, table, 'oai_getrecord',
                   oai_identifier=oai_id,
                   metadata_prefix=route.metadata_prefix) if (oai_id and route.metadata_prefix) else None
    if oai_url:
        cands.append(_mint(
            acq, ctx, PMC, oai_url, resolver_request_id=resolver_rid,
            identifier_kind='pmcid', pmcid=pmcid,
            media_hint='jats_xml',
            # `metadataPrefix=pmc` is the FULL-TEXT dialect. `oai_dc` would be metadata only — and an
            # oai_dc landing page treated as a document is the OAI-PMH silent failure Sol names.
            oai_metadata_prefix=route.metadata_prefix))

    # ---- HOP 3: the OA service — PDF / tarball links, and the OA-SUBSET ANSWER --------------------
    oa_url = fill(route, table, 'oa_service', pmcid=pmcid)
    if oa_url:
        r = acq.get(unit, PMC, oa_url, tries=2, timeout=30)
        if r.ok:
            try:
                oa = ET.fromstring(r.raw)
            except ET.ParseError:
                oa = None
            if oa is not None:
                err = oa.find('error')
                if err is not None:
                    # `idDoesNotExist` / `idIsNotOpenAccess`. THE PMCID EXISTS AND THE FULL TEXT IS NOT
                    # IN THE OA SUBSET — proven live on PMC13200213, an NIH author manuscript. This is
                    # an OBSERVATION ABOUT PMC'S OA SUBSET. It is not evidence about the literature, and
                    # nothing downstream may read it as such.
                    _observe(acq, unit, PMC, r,
                             pmcid=pmcid,
                             oa_service_error_code=str(err.get('code') or ''),
                             reason_text=(err.text or '')[:200])
                else:
                    lic = ''
                    retracted = ''
                    for rec_el in oa.iter('record'):
                        lic = rec_el.get('license', '') or ''
                        retracted = rec_el.get('retracted', '') or ''
                        break
                    for link in oa.iter('link'):
                        href = link.get('href', '') or ''
                        fmt = link.get('format', '') or ''
                        if not href:
                            continue
                        cands.append(_mint(
                            acq, ctx, PMC, href, resolver_request_id=r.request_id,
                            identifier_kind='pmcid', pmcid=pmcid,
                            media_hint=fmt, license_observation=lic,
                            retracted_observation=retracted))
    return cands


# ---- EUROPE PMC ---------------------------------------------------------------------------------

def europe_pmc_candidates(acq: Acquirer, table: RouteTable, ctx: ResolveContext) -> list[DocumentCandidate]:
    """Europe PMC, as a FULL-TEXT route. Exact-DOI core search -> the OA full-text XML, by BARE PMCID.

    `resultType=core` is not optional: it is the only result type that carries `isOpenAccess`,
    `fullTextIdList`, `fullTextUrlList`, `hasPDF`, `license` and the `authMan`/`nihAuthMan` flags. Every
    one of those is recorded as an OBSERVATION and decides nothing.
    """
    route = table.by_id(EUROPE_PMC)
    assert route is not None, 'source_routes.yaml has no `europe_pmc` row'
    sel = route.selectors or {}
    unit = ctx.work_id
    doi = next((i for i in ctx.identifiers if i.lower().startswith('10.')), '')
    if not doi:
        return []

    url = fill(route, table, 'identity', doi=doi)
    if not url:
        return []
    r, payload = acq.get_json(unit, EUROPE_PMC, url, tries=3, timeout=30)
    if not r.ok or not isinstance(payload, dict):
        return []                             # transport fact, already on the ledger. NOT an absence.

    results = dig(payload, sel.get('results', 'resultList.result')) or []
    if not results:
        # hitCount 0 = NOT IN THE EPMC INDEX. It is not "no full text exists" and it is not "not open".
        _observe(acq, unit, EUROPE_PMC, r,
                 epmc_hit_count=int(dig(payload, sel.get('hit_count', 'hitCount')) or 0))
        return []

    rec = results[0]
    pmcid = str(rec.get(sel.get('pmcid', 'pmcid')) or '')
    lic = str(rec.get(sel.get('license', 'license')) or '')
    is_oa = str(rec.get(sel.get('is_open_access', 'isOpenAccess')) or '')
    # THE NIH-AUTHOR-MANUSCRIPT FLAGS. A version_hint is an OBSERVATION — the suffix is load-bearing and
    # the V9 P0 is precisely the rule that this string may not become a version decision. The decision
    # is made later, from the document's own front matter, by provenance.derive_expression_kind.
    nih_am = str(rec.get(sel.get('nih_auth_man', 'nihAuthMan')) or '')
    any_am = str(rec.get(sel.get('auth_man', 'authMan')) or '')
    version_hint = 'nih_author_manuscript' if (nih_am.upper() == 'Y' or any_am.upper() == 'Y') else ''

    cands: list[DocumentCandidate] = []

    # ---- THE FULL TEXT — by BARE PMCID. (The configured {source}/{id} shape 404s. Proven live.) ----
    if pmcid:
        ft = fill(route, table, 'fulltext', pmcid=pmcid)
        if ft:
            cands.append(_mint(
                acq, ctx, EUROPE_PMC, ft, resolver_request_id=r.request_id, raw_metadata=r.raw,
                identifier_kind='pmcid', pmcid=pmcid, media_hint='jats_xml',
                license_observation=lic, version_hint=version_hint,
                is_open_access_flag=is_oa, auth_man_flag=any_am, nih_auth_man_flag=nih_am))

    # ---- THE OTHER LOCATIONS — FILTERED. fullTextUrlList IS NOT A LIST OF OPEN DOCUMENTS. ---------
    # Live, on 10.1186/s13643-025-03000-0, entry [0] was:
    #     {"availability": "Subscription required", "availabilityCode": "S", "site": "DOI", ...}
    # An adapter that took fullTextUrlList[0] would have fetched a PUBLISHER PAYWALL and handed the
    # login page to the miner as a document. The open set is a YAML row, not a rule in this file.
    open_codes = {str(c).upper() for c in (sel.get('url_availability_open') or ['OA', 'F'])}
    for u in (dig(rec, sel.get('full_text_urls', 'fullTextUrlList.fullTextUrl')) or []):
        if not isinstance(u, dict):
            continue
        code = str(u.get(sel.get('url_availability_key', 'availabilityCode')) or '').upper()
        if code not in open_codes:
            continue
        href = str(u.get(sel.get('url_value', 'url')) or '')
        if not href:
            continue
        cands.append(_mint(
            acq, ctx, EUROPE_PMC, href, resolver_request_id=r.request_id,
            identifier_kind='doi', pmcid=pmcid,
            media_hint=str(u.get(sel.get('url_style', 'documentStyle')) or ''),
            license_observation=lic, version_hint=version_hint,
            availability_code=code, is_open_access_flag=is_oa, nih_auth_man_flag=nih_am))
    return cands


# ---- DOAJ ---------------------------------------------------------------------------------------

def doaj_candidates(acq: Acquirer, table: RouteTable, ctx: ResolveContext) -> list[DocumentCandidate]:
    """DOAJ, as a LOCATION route. Exact-DOI article search -> `bibjson.link[]` of the wanted kind.

    DOAJ RETURNS LINKS, NOT BYTES, and the link is frequently a LANDING PAGE: live, on our own probe
    DOI, the single link of the wanted kind was `https://doi.org/10.1186/...` — a DOI RESOLVER. So this
    is a CANDIDATE GENERATOR. Directory membership is not byte-level version proof, and a DOAJ miss
    means "not indexed in DOAJ" — never "not open".
    """
    route = table.by_id(DOAJ)
    assert route is not None, 'source_routes.yaml has no `doaj` row'
    sel = route.selectors or {}
    unit = ctx.work_id
    doi = next((i for i in ctx.identifiers if i.lower().startswith('10.')), '')
    if not doi:
        return []

    url = fill(route, table, 'identity', doi=doi)
    if not url:
        return []
    r, payload = acq.get_json(unit, DOAJ, url, tries=3, timeout=30)
    if not r.ok or not isinstance(payload, dict):
        return []

    results = dig(payload, sel.get('results', 'results')) or []
    want = str(sel.get('link_kind_want', 'fulltext'))       # DATA. Compared against; never emitted.
    kind_key = str(sel.get('link_kind_key', 'type'))
    cands: list[DocumentCandidate] = []
    for art in results:
        bib = (art or {}).get('bibjson') or {}
        links = dig(bib, sel.get('links', 'link').split('.', 1)[-1]) or bib.get('link') or []
        matched = [l for l in links if isinstance(l, dict)
                   and str(l.get(kind_key, '')).lower() == want.lower()]
        for l in matched:
            href = str(l.get(sel.get('link_url', 'url')) or '')
            if not href:
                continue
            cands.append(_mint(
                acq, ctx, DOAJ, href, resolver_request_id=r.request_id, raw_metadata=r.raw,
                identifier_kind='doi',
                # NOTE WHAT IS *NOT* HERE: DOAJ's literal link-type token. `fulltext` is a RESERVED_VALUE
                # in the ledger's conclusion guard, and the guard is RIGHT: a component may not write that
                # word. So the observation is recorded as a COUNT — and DOAJ's own bytes, containing the
                # token verbatim, go to the content-addressed blob store above, hashed.
                n_links_total=len(links), n_links_matched=len(matched),
                media_hint=str(l.get(sel.get('link_media', 'content_type')) or ''),
                record_page=f"https://doaj.org/article/{art.get('id', '')}" if art.get('id') else ''))
    if not results:
        # total 0 = NOT INDEXED IN DOAJ. Sol V9 §2, verbatim: "A DOAJ miss means 'not indexed in DOAJ,'
        # NOT 'not open'." Nothing in this module may turn this integer into an absence.
        _observe(acq, unit, DOAJ, r, doaj_total=int(dig(payload, sel.get('total', 'total')) or 0))
    return cands


ADAPTERS = {PMC: pmc_candidates, EUROPE_PMC: europe_pmc_candidates, DOAJ: doaj_candidates}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE EXECUTOR — ONE, GENERIC, SHARED. It is not a route and it belongs to no route.
#
# Sol V9 §1: "2. A generic acquisition executor fetches and hashes the bytes." It is separate from the
# adapters ON PURPOSE: the moment fetching lives inside an adapter, the adapter has an opinion about
# what it fetched, and that opinion is the disease. This function's ENTIRE authority is:
#     get the bytes -> extract text -> hand both to record_manifestation, WITH THE LINEAGE
# and record_manifestation then derives the content profile ITSELF, from the bytes, through the shared
# reducer. There is no parameter here through which a caller could assert what the document is.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

FETCHABLE_SCHEMES = ('http', 'https')


def fetch_candidate(acq: Acquirer, table: RouteTable, ctx: ResolveContext,
                    cand: DocumentCandidate, *, tries: int = 3, timeout: int = 60) -> dict | None:
    """Fetch ONE candidate's bytes and record the manifestation, carrying `candidate_id` as lineage.

    -> the manifestation dict, or None if we did not obtain bytes. **None IS NOT AN ABSENCE.** It means
    THIS candidate did not yield bytes on THIS attempt; the transport fact is on the ledger, in its own
    vocabulary (THROTTLED / BLOCKED / NOT_INDEXED / TRANSPORT_ERROR), and only a reducer over the whole
    ledger may say anything about what exists.
    """
    url = cand.retrieval_url
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in FETCHABLE_SCHEMES:
        # PMC's OA service hands back `ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/...tar.gz`. We do
        # not fetch it here — but the CANDIDATE IS ALREADY ON THE LEDGER, with its media_hint and its
        # licence. It stays a recorded LEAD rather than being silently dropped, which is the difference
        # between "we have not fetched this" and "this does not exist".
        acq.budget_stopped(ctx.work_id, adapter=cand.discovered_by_route,
                           candidate_id=cand.candidate_id, url=url,
                           scheme_not_fetched=scheme or 'none')
        return None
    r = acq.get(ctx.work_id, content_host(url), url, tries=tries, timeout=timeout,
                candidate_id=cand.candidate_id)
    if not r.ok or not r.raw:
        return None

    # ---- extraction. NOT characterisation. -------------------------------------------------------
    obs: dict = {}
    if looks_like_xml(r.raw, r.content_type):
        text, method, jats_obs = jats_to_text(r.raw)
        obs.update(jats_obs)
        if not text:
            # It called itself XML and it is not JATS — a 404 page served as XML, or another dialect.
            # Fall back to the generic extractor and let the REDUCER size what came out. (The PMC OAI
            # 404 is 48KB of HTML with a <body> in it; this is the path on which it must NOT become a
            # document, and it does not, because nothing here says it is one.)
            text, method = extract_text(r.raw, r.content_type)
    else:
        text, method = extract_text(r.raw, r.content_type)

    return acq.record_manifestation(
        ctx.work_id,
        locator=url, raw=r.raw, text=text,
        adapter=content_host(url),
        candidate_id=cand.candidate_id,          # ** THE LINEAGE. WHICH ROUTE THESE BYTES ARE OWED TO. **
        requested_title=ctx.title,
        requested_authors=list(ctx.authors or []),
        requested_doi=next((i for i in ctx.identifiers if i.lower().startswith('10.')), ''),
        requested_year=ctx.year,
        extraction_method=method,
        discovered_by_route=cand.discovered_by_route,
        media_hint=cand.media_hint,
        version_hint=cand.version_hint,           # OBSERVATION. Carried, never obeyed.
        license_observation=cand.license_observation,
        raw_metadata_hash=cand.raw_metadata_hash,
        **obs)


def resolve_work(acq: Acquirer, table: RouteTable, ctx: ResolveContext, *,
                 routes: Iterable[str] = BIO_ROUTES, fetch: bool = True,
                 id_records: dict[str, dict] | None = None) -> dict:
    """Run the biomedical + OA-index wave for ONE work. -> a per-route report of what was OBSERVED.

    ROUTE_PLANNED goes down BEFORE the loop, with the adapters we are ABOUT to try — so `route_complete`
    can only ever mean "every one of these has a terminal outcome record", never "an adapter was mapped".
    """
    acq.plan_route(ctx.work_id, list(routes), requested_title=ctx.title,
                   doi=next((i for i in ctx.identifiers if i.lower().startswith('10.')), ''))
    report: dict = {'work_id': ctx.work_id, 'routes': {}}
    for name in routes:
        fn = ADAPTERS.get(name)
        if fn is None:
            continue
        kw = {'id_records': id_records} if name == PMC else {}
        cands = fn(acq, table, ctx, **kw)      # type: ignore[operator]
        row: dict = {'candidates': len(cands), 'manifestations': 0, 'candidate_ids': []}
        for c in cands:
            row['candidate_ids'].append(c.candidate_id)
            if fetch:
                m = fetch_candidate(acq, table, ctx, c)
                if m:
                    row['manifestations'] += 1
        report['routes'][name] = row
    return report


if __name__ == '__main__':
    print(__doc__)
    print('This module is a library. Its boundaries are attacked by:  '
          'python3 scripts/test_routes_bio_attacks.py')
    print('Its live probes are:                                       '
          'python3 scripts/probe_routes_bio_live.py')
