#!/usr/bin/env python3
"""TARGETED OAI-PMH — Sol V9 §2, "Institutional OAI-PMH" (gross yield forecast 35-90).

    Sol, verbatim: "Do not attempt global per-work OAI harvesting."

WHY NOT, IN ONE SENTENCE: **OAI-PMH HAS NO EXACT-DOI LOOKUP.** There is no `GetRecord(doi:10.1257/...)`.
The protocol has six verbs and the only one that retrieves a specific work takes an OAI IDENTIFIER —
an opaque, repository-local string (`oai:ora.ox.ac.uk:uuid:2c4b...`) that you cannot derive from a DOI,
a title, or anything else you hold. So the only two ways to harvest by DOI are:

  (a) LIST EVERY RECORD IN EVERY REPOSITORY AND GREP. That is thousands of hours of somebody else's
      bandwidth to answer 2,490 questions, and it is what "global per-work OAI harvesting" means.
  (b) GET THE IDENTIFIER FROM SOMETHING THAT *DOES* INDEX BY DOI — and CORE returns `oaiIds`, OpenAIRE
      returns the repository's `originalId` and its OAI base URL. Then ONE `GetRecord` per work.

This module is (b). It is a RETRIEVAL lane, not a discovery lane: it is handed an identifier and it
fetches a record. `LocalOaiIndex` is where the identifiers we learn are kept, so the next run does not
have to learn them again.

THE FIVE SILENT FAILURES SOL NAMES, AND WHERE EACH ONE IS STOPPED

  1. "`oai_dc` landing page treated as PDF."
     `oai_dc`'s <dc:identifier> is, in the overwhelming majority of repositories, A LINK TO AN HTML
     SPLASH PAGE — the page with the "Download (PDF, 2.4MB)" button on it. Fetch it, strip the tags,
     and you get 500 words of navigation chrome that a length-based reducer will happily call a
     document. So `document_urls()` DOES NOT RETURN IT. Landing pages come back from a DIFFERENT
     function, with a different name, and they are never proposed as document candidates.
     THE ORDER OF `metadata_prefixes` IS THE WHOLE DEFENCE: ask for JATS/METS/MODS/TEI first, because
     those dialects have a place to put A FILE URL, and oai_dc does not.

  2. "A deleted record treated as no-world evidence."
     `<header status="deleted"/>` means THIS REPOSITORY WITHDREW ITS COPY. It is a fact about a
     repository's shelf. It is not a fact about the literature, and `RECORD_DELETED` is not, and can
     never become, "no OA copy exists".

  3. "The DOI belongs to a CITED REFERENCE."
     A record's metadata contains its bibliography. Grep the XML for `10\\.` and you will find the DOIs
     of the FIFTY PAPERS IT CITES — and one of them will match the DOI you were looking for, and you
     will file somebody else's paper under it. `record_dois()` therefore reads ONLY the record's own
     identifier and relation elements, and it REFUSES to look anywhere else.

  4. "A repository cover sheet hides a different article."
     Institutional repositories staple a branded cover page onto the PDF. The cover sheet prints the
     right DOI; the PDF underneath can be the wrong paper. Nothing in a metadata record can catch
     that, so this module does not try: it passes the REQUESTED IDENTITY down to
     `record_manifestation()` and lets the byte-level reducer (which already segments cover sheets)
     do it. What this module must not do is CONCLUDE, and it does not.

  5. "Resumption state is lost."
     A resumption token expires. `list_records()` persists its cursor after every page, so a killed
     harvest resumes at the page it reached rather than at page one.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402  THE ONE DOOR TO THE NETWORK
    Acquirer, Response, make_candidate_id,
)
from event_ledger import EventKind  # noqa: E402
from host_scheduler import RobotsCache, Scheduler, host_of  # noqa: E402

ROUTES_YAML = ROOT / 'config' / 'source_routes.yaml'
INDEX_PATH = ROOT / 'outputs' / 'oai_index' / 'doi_to_oai.jsonl'
CURSOR_DIR = ROOT / 'outputs' / 'oai_state'

# ---- WHAT THE REPOSITORY SAID. Not one of these is a fact about the literature. -------------------
RECORD_RETURNED  = 'RECORD_RETURNED'            # a record came back, and it is not deleted
RECORD_DELETED   = 'RECORD_DELETED'             # THIS REPOSITORY withdrew ITS COPY. Not an absence.
ID_DOES_NOT_EXIST = 'ID_DOES_NOT_EXIST'         # not in THIS repository's index. Not an absence.
CANNOT_DISSEMINATE = 'CANNOT_DISSEMINATE_FORMAT'  # it has the record, not in that FORMAT
BAD_ARGUMENT     = 'BAD_ARGUMENT'               # OUR request was malformed. A fact about US.
NO_RECORDS_MATCH = 'NO_RECORDS_MATCH'           # an empty set/date window
NOT_XML          = 'NOT_XML'                    # 200 OK, and it is 48KB of HTML. It happened.
NO_IDENTIFIER    = 'NO_IDENTIFIER'              # we never had an OAI id for this work. UNSEARCHED.
ROBOTS_DISALLOWED = 'ROBOTS_DISALLOWED'         # we did not ask. We are not entitled to guess.

#: ** NOT ONE OF THESE MAY EVER BECOME "no OA copy exists." ** `ID_DOES_NOT_EXIST` is the closest
#: thing here to an absence and it is still only a fact about ONE REPOSITORY'S INDEX — the same shape
#: as an HTTP 404, and the same rule applies: it closes THAT repository and nothing else. Sol §2:
#: "only a clean GetRecord/indexed lookup closes that repository. A missing local DOI-to-OAI mapping
#: does not."
NEVER_AN_ABSENCE = (RECORD_DELETED, CANNOT_DISSEMINATE, BAD_ARGUMENT, NOT_XML, NO_IDENTIFIER,
                    ROBOTS_DISALLOWED)

_OAI_ERROR_MAP = {
    'idDoesNotExist': ID_DOES_NOT_EXIST,
    'cannotDisseminateFormat': CANNOT_DISSEMINATE,
    'badArgument': BAD_ARGUMENT,
    'badVerb': BAD_ARGUMENT,
    'badResumptionToken': BAD_ARGUMENT,
    'noRecordsMatch': NO_RECORDS_MATCH,
    'noSetHierarchy': NO_RECORDS_MATCH,
    'noMetadataFormats': CANNOT_DISSEMINATE,
}

#: A URL that ENDS in one of these is a file. Anything else that a repository hands us is a PAGE ABOUT
#: a file until proven otherwise — and the proof is the bytes, not the extension.
_DOC_EXT = re.compile(r'\.(pdf|xml|nxml|docx?|ps|epub|txt)(\?|#|$)', re.I)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# EACH REPOSITORY IS A DATA ROW (Sol §2, verbatim)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Repository:
    """base URL, metadata prefixes, identifier mappings, file selectors, rate policy. ALL FROM YAML.

    Adding the long tail of DSpace/EPrints repositories is meant to cost YAML AND ZERO PYTHON — that
    is the entire argument for a 35-90 yield being reachable at all. If a new repository needs a new
    function, this schema has failed; if it needs a new METADATA DIALECT, that is a genuinely new wire
    format and `_DIALECTS` below is where it goes.
    """
    repository_id: str
    base_url: str
    metadata_prefixes: tuple[str, ...] = ('oai_dc',)     # ORDERED. RICHEST FIRST. See the module doc.
    identifier_pattern: str = ''
    identifier_from: str = ''
    identifier_transforms: dict = field(default_factory=dict)
    file_selectors: tuple[str, ...] = ()
    rate_policy: dict = field(default_factory=dict)
    #: The base a RELATIVE file href resolves against. Empty = WE DO NOT GUESS (see `_resolve`).
    document_base_url: str = ''

    @property
    def adapter(self) -> str:
        """The acquisition adapter name. Every attempt is attributable TO A REPOSITORY, so a route
        that found nothing is credited with nothing (the V9 §1 lineage rule)."""
        return f'oai:{self.repository_id}'

    @property
    def host(self) -> str:
        return str(self.rate_policy.get('host') or host_of(self.base_url))


def load_repositories(path: Path | str = ROUTES_YAML) -> dict[str, Repository]:
    import yaml
    doc = yaml.safe_load(Path(path).read_text()) or {}
    out: dict[str, Repository] = {}
    for row in doc.get('oai_repositories') or []:
        rid = str(row.get('repository_id') or '').strip()
        if not rid:
            continue
        out[rid] = Repository(
            repository_id=rid,
            base_url=str(row.get('base_url') or ''),
            metadata_prefixes=tuple(row.get('metadata_prefixes') or ('oai_dc',)),
            identifier_pattern=str(row.get('identifier_pattern') or ''),
            identifier_from=str(row.get('identifier_from') or ''),
            identifier_transforms=dict(row.get('identifier_transforms') or {}),
            file_selectors=tuple(row.get('file_selectors') or ()),
            rate_policy=dict(row.get('rate_policy') or {}),
            document_base_url=str(row.get('document_base_url') or ''),
        )
    return out


def apply_transform(spec: str, value: str) -> str:
    """The TINY declared vocabulary of identifier transforms. `strip_prefix:PMC` -> 12754963.

    It is deliberately almost empty. A transform language rich enough to be interesting is a
    programming language in a YAML file, and the next thing in it is a topic gate.
    """
    if not spec:
        return value
    op, _, arg = spec.partition(':')
    if op == 'strip_prefix':
        return value[len(arg):] if value.startswith(arg) else value
    if op == 'lower':
        return value.lower()
    if op == 'strip':
        return value.strip()
    raise ValueError(f'unknown identifier transform {spec!r} — add it to apply_transform, in code, '
                     f'deliberately. A YAML file may not define new operations.')


def build_identifier(repo: Repository, identifiers: dict[str, str]) -> str:
    """A REPOSITORY-LOCAL OAI IDENTIFIER, or '' — and '' IS THE COMMON CASE, ON PURPOSE.

    Only a repository whose ids are FORMULAIC (PMC: `oai:pubmedcentral.nih.gov:<numeric pmcid>`) can be
    addressed from an identifier we already hold. For every DSpace and EPrints repository on earth the
    id is opaque and MUST come from CORE / OpenAIRE / the local index. Returning '' here is the honest
    answer, and its consequence — NO_IDENTIFIER, an UNSEARCHED repository — is never an absence.
    """
    if not repo.identifier_pattern or not repo.identifier_from:
        return ''
    raw = str(identifiers.get(repo.identifier_from) or '').strip()
    if not raw:
        return ''
    vals = {repo.identifier_from: raw}
    for name, spec in (repo.identifier_transforms or {}).items():
        vals[name] = apply_transform(str(spec), raw)
    try:
        return repo.identifier_pattern.format(**vals)
    except KeyError:
        return ''


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE RECORD
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _lname(el) -> str:
    """The local name, namespace stripped. Repositories disagree about namespaces constantly and a
    parser that insists on them fails on half the DSpace instances in the world."""
    t = el.tag if isinstance(el.tag, str) else ''
    return t.rsplit('}', 1)[-1]


def _find_all(root, name: str):
    return [e for e in root.iter() if _lname(e) == name]


def _attr(el, name: str) -> str:
    """An attribute, namespace-insensitively (`xlink:href` / `href` / `{...}href`)."""
    for k, v in (el.attrib or {}).items():
        if str(k).rsplit('}', 1)[-1] == name:
            return str(v)
    return ''


@dataclass
class OaiRecord:
    """WHAT THE REPOSITORY SAID. It concludes nothing, and nothing here is a version verdict."""
    repository_id: str
    identifier: str
    metadata_prefix: str
    outcome: str
    raw: bytes = b''
    oai_error: str = ''
    datestamp: str = ''
    set_specs: tuple[str, ...] = ()
    root: Any = None
    metadata_el: Any = None

    @property
    def ok(self) -> bool:
        return self.outcome == RECORD_RETURNED

    @property
    def deleted(self) -> bool:
        return self.outcome == RECORD_DELETED


def parse_record(raw: bytes, repo: Repository, identifier: str, prefix: str) -> OaiRecord:
    """Bytes -> an OaiRecord. THE ERROR CASES ARE THE POINT; the happy path is four lines.

    An HTTP 200 from an OAI endpoint is not a record. `pmc.ncbi.nlm.nih.gov/oai/oai.cgi` answers 200
    with FORTY-EIGHT KILOBYTES OF HTML — it has a <body> tag, it strips to thousands of words, and a
    fetcher that checked only `resp.ok` would have filed that error page as a full-text document.
    """
    mk = lambda outcome, **kw: OaiRecord(repo.repository_id, identifier, prefix, outcome, raw=raw, **kw)  # noqa: E731
    try:
        root = ET.fromstring(raw)
    except Exception:
        return mk(NOT_XML)
    if _lname(root) != 'OAI-PMH':
        return mk(NOT_XML)                    # well-formed XML that is not an OAI response (an XHTML
        #                                     # error page parses fine, and is not a record)

    errs = _find_all(root, 'error')
    if errs:
        code = _attr(errs[0], 'code') or (errs[0].text or '').strip()
        return mk(_OAI_ERROR_MAP.get(code, BAD_ARGUMENT), oai_error=code)

    headers = _find_all(root, 'header')
    if not headers:
        return mk(NOT_XML)
    hdr = headers[0]
    # ---- THE DELETION RECORD (Sol §2 silent failure #2) -----------------------------------------
    # `status="deleted"` is a fact about a REPOSITORY'S SHELF. The record is gone from THIS repository.
    # The paper is not gone from the world, and this outcome is in NEVER_AN_ABSENCE forever.
    if (_attr(hdr, 'status') or '').lower() == 'deleted':
        ident = next((e.text or '' for e in _find_all(hdr, 'identifier')), identifier)
        ds = next((e.text or '' for e in _find_all(hdr, 'datestamp')), '')
        return mk(RECORD_DELETED, root=root, datestamp=ds.strip())

    mds = _find_all(root, 'metadata')
    ds = next((e.text or '' for e in _find_all(hdr, 'datestamp')), '')
    sets = tuple((e.text or '').strip() for e in _find_all(hdr, 'setSpec') if (e.text or '').strip())
    return mk(RECORD_RETURNED, root=root, datestamp=ds.strip(), set_specs=sets,
              metadata_el=(mds[0] if mds else None))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE FILE SELECTORS — ONE ROW PER DIALECT. `oai_dc` IS NOT IN THE DOCUMENT LIST, AND THAT IS THE FIX.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Link:
    url: str
    role: str            # 'document' | 'landing_page'  — NEVER conflated. This is silent failure #1.
    media_hint: str      # 'pdf' | 'xml' | 'unknown'
    selector: str        # WHICH dialect element produced it, so a bad selector is attributable


def _media_of(url: str) -> str:
    m = _DOC_EXT.search(url or '')
    return (m.group(1).lower() if m else 'unknown')


def _jats_links(md) -> list[Link]:
    # <self-uri xlink:href="..."> — JATS's own pointer at its own file.
    return [Link(_attr(e, 'href'), 'document', _media_of(_attr(e, 'href')), 'jats_self_uri')
            for e in _find_all(md, 'self-uri') if _attr(e, 'href')]


def _mets_links(md) -> list[Link]:
    # METS: <fileGrp USE="ORIGINAL"><file><FLocat xlink:href="..."/>. The USE attribute matters —
    # a THUMBNAIL and a TEXT-extraction derivative live in the same METS beside the real thing.
    out = []
    for grp in _find_all(md, 'fileGrp'):
        use = (_attr(grp, 'USE') or _attr(grp, 'use') or '').upper()
        if use and use not in ('ORIGINAL', 'CONTENT', 'BITSTREAMS'):
            continue                              # THUMBNAIL / TEXT / LICENSE are not the article
        for fl in _find_all(grp, 'FLocat'):
            href = _attr(fl, 'href')
            if href:
                out.append(Link(href, 'document', _media_of(href), 'mets_flocat'))
    return out


def _mods_links(md) -> list[Link]:
    # MODS: <location><url access="raw object">. `access="object in context"` is THE LANDING PAGE, and
    # MODS says so in the attribute. Reading it is the difference between a PDF and a splash screen.
    out = []
    for u in _find_all(md, 'url'):
        access = (_attr(u, 'access') or '').lower()
        url = (u.text or '').strip()
        if not url:
            continue
        if access == 'raw object':
            out.append(Link(url, 'document', _media_of(url), 'mods_location_url'))
        elif access in ('object in context', 'preview'):
            out.append(Link(url, 'landing_page', 'unknown', 'mods_location_url'))
    return out


def _ore_links(md) -> list[Link]:
    out = []
    for e in _find_all(md, 'aggregates'):
        href = _attr(e, 'resource')
        if href:
            out.append(Link(href, 'document', _media_of(href), 'ore_aggregated_resource'))
    return out


def _tei_links(md) -> list[Link]:
    # HAL TEI: <ref type="file" target="https://hal.../document">
    out = []
    for e in _find_all(md, 'ref'):
        if (_attr(e, 'type') or '').lower() == 'file' and _attr(e, 'target'):
            t = _attr(e, 'target')
            out.append(Link(t, 'document', _media_of(t), 'tei_ref_target'))
    return out


def _oai_dc_links(md) -> list[Link]:
    """** SILENT FAILURE #1, STOPPED HERE. **

    `<dc:identifier>https://ora.ox.ac.uk/objects/uuid:xyz</dc:identifier>` IS NOT A PDF. It is the
    HTML page that HAS a PDF on it. Fetch it, strip the tags, and you get several hundred words of
    repository chrome — which is exactly the shape of the 535-word aeaweb cookie banner that got
    stamped FULLTEXT.

    So every oai_dc link comes back as a LANDING PAGE... unless the URL itself ends in `.pdf`/`.xml`,
    in which case it is a file and says so. The role is decided by evidence, and an absence of
    evidence produces the CAUTIOUS role, not the useful one.
    """
    out = []
    for e in _find_all(md, 'identifier'):
        url = (e.text or '').strip()
        if not url.lower().startswith(('http://', 'https://')):
            continue                                       # a DOI or a handle, not a location
        if _DOC_EXT.search(url):
            out.append(Link(url, 'document', _media_of(url), 'oai_dc_identifier_file'))
        else:
            out.append(Link(url, 'landing_page', 'unknown', 'oai_dc_identifier'))
    return out


def _datacite_links(md) -> list[Link]:
    out = []
    for e in _find_all(md, 'alternateIdentifier'):
        t = (_attr(e, 'alternateIdentifierType') or '').lower()
        url = (e.text or '').strip()
        if t == 'url' and url.startswith('http'):
            role = 'document' if _DOC_EXT.search(url) else 'landing_page'
            out.append(Link(url, role, _media_of(url), 'datacite_alternate_identifier'))
    return out


#: ONE ROW PER WIRE DIALECT. A new REPOSITORY is a YAML row. A new DIALECT is a row here — and Sol
#: allows exactly that: "A code edit is needed only for a genuinely new metadata dialect primitive."
_DIALECTS = {
    'jats_self_uri': _jats_links,
    'mets_flocat': _mets_links,
    'mods_location_url': _mods_links,
    'ore_aggregated_resource': _ore_links,
    'tei_ref_target': _tei_links,
    'oai_dc_identifier': _oai_dc_links,
    'datacite_alternate_identifier': _datacite_links,
}


RELATIVE_REFERENCE = 'relative_reference'


def _resolve(lk: Link, repo: Repository) -> Link:
    """** A RELATIVE href IS NOT A URL WE CAN FETCH. ** Found LIVE, on the first real GetRecord.

    PMC's JATS says, of the article we just pulled 108,635 bytes of:

        <self-uri xlink:href="13643_2025_Article_3000.pdf"/>

    A BARE FILENAME. Not a path, not a URL — a filename, relative to a base the OAI response never
    states. Hand that to a fetcher and it will either fail, or (worse) urljoin it against whatever
    happens to be lying around and fetch A DIFFERENT DOCUMENT ENTIRELY.

    So: a relative href is resolved ONLY against a base the REPOSITORY ROW declares
    (`document_base_url`). With no declared base we DO NOT GUESS — the link is demoted to
    RELATIVE_REFERENCE, which is recorded (it is real evidence that a PDF exists) and is never
    proposed as a document. For PMC specifically the PDF comes from the OA SERVICE, a different
    endpoint entirely, and the JATS we already hold IS the document — so guessing here would buy a
    junk fetch to re-acquire something we have.
    """
    url = (lk.url or '').strip()
    if url.lower().startswith(('http://', 'https://', 'ftp://')):
        return lk
    base = str(repo.rate_policy.get('document_base_url') or getattr(repo, 'document_base_url', '') or '')
    if base:
        return Link(urllib.parse.urljoin(base, url), lk.role, _media_of(url), lk.selector)
    return Link(url, RELATIVE_REFERENCE, _media_of(url), lk.selector)


def _all_links(rec: OaiRecord, repo: Repository) -> list[Link]:
    if rec.metadata_el is None:
        return []
    sels = list(repo.file_selectors) or []
    if rec.metadata_prefix == 'oai_dc' or not sels:
        sels = sels + ['oai_dc_identifier']
    out: list[Link] = []
    seen = set()
    for name in sels:
        fn = _DIALECTS.get(name)
        if not fn:
            continue
        for lk in fn(rec.metadata_el):
            if lk.url and lk.url not in seen:
                seen.add(lk.url)
                out.append(_resolve(lk, repo))
    return out


def relative_refs(rec: OaiRecord, repo: Repository) -> list[Link]:
    """Hrefs the record states but does not locate. Real evidence; not a fetchable address."""
    return [lk for lk in _all_links(rec, repo) if lk.role == RELATIVE_REFERENCE]


def document_urls(rec: OaiRecord, repo: Repository) -> list[Link]:
    """THE FILE LINKS. A LANDING PAGE IS NOT IN HERE, and there is no flag that puts one in."""
    return [lk for lk in _all_links(rec, repo) if lk.role == 'document']


def landing_urls(rec: OaiRecord, repo: Repository) -> list[Link]:
    """The pages ABOUT the document. Kept, because they are real leads for a human and for a scraper
    that knows what it is doing — and kept SEPARATE, because the miner must never see one."""
    return [lk for lk in _all_links(rec, repo) if lk.role == 'landing_page']


def inline_document(rec: OaiRecord) -> bytes:
    """SOME RECORDS *ARE* THE DOCUMENT. PMC's `metadataPrefix=pmc` returns the whole JATS article —
    108,635 bytes with 17 <sec> elements — inside the GetRecord response. There is no file to fetch:
    the bytes are already here, and asking for a PDF as well would be a second request for a document
    we hold.

    Returns b'' when the metadata is a description OF a document rather than a document.
    """
    if rec.metadata_el is None:
        return b''
    for name in ('article', 'TEI', 'text'):
        for el in _find_all(rec.metadata_el, name):
            body = _find_all(el, 'body') + _find_all(el, 'sec')
            if body:                              # a metadata stub is not a document
                return ET.tostring(el, encoding='utf-8')
    return b''


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# IDENTITY — ** THE DOI IN A RECORD MAY BELONG TO A PAPER IT CITES ** (Sol §2, silent failure #3)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: The elements in which a record states ITS OWN identity. NOT `description`, NOT `references`, NOT
#: `citation`, NOT the free text of an abstract.
_OWN_ID_ELEMENTS = ('identifier', 'alternateIdentifier', 'article-id', 'idno', 'relatedIdentifier',
                    'ELocation-ID', 'pub-id')
#: Elements that CONTAIN OTHER PEOPLE'S DOIs. A record's back matter is a list of fifty other works.
_FOREIGN_ID_ELEMENTS = ('ref', 'ref-list', 'citation', 'element-citation', 'mixed-citation',
                        'references', 'back', 'related-article', 'relation', 'source')

_DOI = re.compile(r'10\.\d{4,9}/[^\s"\'<>&]+', re.I)


def record_dois(rec: OaiRecord) -> list[str]:
    """The DOIs THIS RECORD CLAIMS AS ITS OWN. Never a DOI it merely mentions.

    ** THE ATTACK THIS EXISTS FOR: ** a full-text JATS record carries its entire bibliography. Run a
    regex for `10\\.\\d{4,9}/...` over the record and you will harvest the DOIs of the fifty papers it
    CITES. One of them will be the DOI you were searching for — because you found this record BY
    following a citation — and you will bind a stranger's paper to it, with a DOI match as your
    evidence. That is the Parry / Yang-Hui He failure with a bibliography instead of a title search.

    So: we walk down from the metadata root, and we DO NOT DESCEND into an element that holds other
    people's identifiers. What is left is what the record says about itself.
    """
    if rec.metadata_el is None:
        return []
    out: list[str] = []

    def walk(el) -> None:
        for child in el:
            if _lname(child) in _FOREIGN_ID_ELEMENTS:
                continue                       # ** the bibliography is not this paper's identity **
            if _lname(child) in _OWN_ID_ELEMENTS:
                for m in _DOI.finditer((child.text or '') + ' ' + ' '.join(
                        str(v) for v in (child.attrib or {}).values())):
                    d = m.group(0).rstrip('.,;)')
                    if d.lower() not in [x.lower() for x in out]:
                        out.append(d)
            walk(child)

    walk(rec.metadata_el)
    return out


def record_confirms_doi(rec: OaiRecord, doi: str) -> tuple[bool, str]:
    """Does this record CLAIM the DOI we asked for? -> (confirmed, basis).

    A False here is NOT "wrong work" — it is "this record does not state its DOI", which is extremely
    common in oai_dc and means only that the metadata cannot settle identity. The bytes still can.
    """
    want = (doi or '').strip().lower()
    if not want:
        return False, 'no DOI requested'
    own = [d.lower() for d in record_dois(rec)]
    if want in own:
        return True, 'the record states this DOI as its own identifier'
    if own:
        return False, f'the record states a DIFFERENT DOI as its own ({own[0]})'
    return False, 'the record states no DOI of its own — metadata cannot settle identity here'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE LOCAL DOI -> OAI INDEX. Where the identifiers CORE and OpenAIRE hand us are KEPT.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OaiSeed:
    doi: str
    oai_identifier: str
    base_url: str = ''
    repository_id: str = ''
    learned_from: str = ''          # 'core' | 'openaire' | 'operator' — a seed has a provenance too


class LocalOaiIndex:
    """Append-only JSONL. `outputs/oai_index/doi_to_oai.jsonl`.

    Sol §2: "an incrementally maintained local index". The point is that resolving a DOI to an OAI
    identifier costs a CORE or OpenAIRE call, and we should pay it ONCE. A MISS HERE IS NOT AN
    ABSENCE — it is `NO_IDENTIFIER`, an UNSEARCHED repository, which is precisely the distinction Sol
    draws: "only a clean GetRecord closes that repository; a missing local DOI-to-OAI mapping does not."
    """

    def __init__(self, path: Path | str = INDEX_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._by_doi: dict[str, list[OaiSeed]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    try:
                        self._add(OaiSeed(**json.loads(line)), persist=False)
                    except Exception:
                        continue

    def _add(self, seed: OaiSeed, persist: bool = True) -> bool:
        key = seed.doi.lower()
        cur = self._by_doi.setdefault(key, [])
        if any(s.oai_identifier == seed.oai_identifier for s in cur):
            return False
        cur.append(seed)
        if persist:
            with open(self.path, 'a') as fh:
                fh.write(json.dumps(seed.__dict__, sort_keys=True) + '\n')
        return True

    def add(self, seed: OaiSeed) -> bool:
        return self._add(seed)

    def get(self, doi: str) -> list[OaiSeed]:
        return list(self._by_doi.get((doi or '').lower(), []))


def seeds_from_core(doi: str, record: dict) -> list[OaiSeed]:
    """CORE's `oaiIds` ARE THE SEED OF THIS ENTIRE LANE (Sol §2: "Obtain the OAI identifier and
    repository base URL through CORE"). This is a pure function over a record CORE already returned —
    it makes no network call, so the OAI lane costs nothing extra when CORE has already run.
    """
    out: list[OaiSeed] = []
    ids = record.get('oaiIds') or record.get('oai_ids') or []
    if isinstance(ids, str):
        ids = [ids]
    providers = record.get('dataProviders') or []
    base = ''
    for p in providers:
        if isinstance(p, dict):
            base = str(p.get('url') or p.get('oaiPmhUrl') or '') or base
    for oid in ids:
        oid = str(oid or '').strip()
        if oid.startswith('oai:'):
            out.append(OaiSeed(doi=doi, oai_identifier=oid, base_url=base, learned_from='core'))
    return out


def seeds_from_openaire(doi: str, record: dict) -> list[OaiSeed]:
    """OpenAIRE's `originalId` carries the repository's own OAI identifier for the same deposit."""
    out: list[OaiSeed] = []
    ids = record.get('originalId') or record.get('originalIds') or []
    if isinstance(ids, str):
        ids = [ids]
    for oid in ids:
        oid = str(oid or '').strip()
        if oid.startswith('oai:'):
            out.append(OaiSeed(doi=doi, oai_identifier=oid, learned_from='openaire'))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE VERBS. Every request goes through acquisition.Acquirer — THE ONE DOOR — so the transport
# outcome lands on the ledger and stays distinct from what the repository SAID.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _url(repo: Repository, **params) -> str:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    sep = '&' if '?' in repo.base_url else '?'
    return f'{repo.base_url}{sep}{q}'


class OaiHarvester:
    """Targeted GetRecord, plus a resumable ListRecords for building the local index.

    IT DOES NOT CONCLUDE. It returns `OaiRecord`s whose `outcome` is a fact about a REPOSITORY, and
    `NEVER_AN_ABSENCE` names every one of those facts that a careless reader might mistake for a fact
    about the world.
    """

    def __init__(self, acq: Acquirer, repos: dict[str, Repository] | None = None,
                 robots: RobotsCache | None = None, index: LocalOaiIndex | None = None,
                 check_robots: bool = True):
        self.acq = acq
        self.repos = repos if repos is not None else load_repositories()
        self.index = index if index is not None else LocalOaiIndex()
        self.check_robots = check_robots
        self._robots = robots
        self.cursor_dir = CURSOR_DIR

    def _robots_ok(self, url: str) -> tuple[bool, str]:
        if not self.check_robots:
            return True, 'robots check disabled by caller'
        if self._robots is None:
            from acquisition import SCHEDULER
            self._robots = RobotsCache(SCHEDULER)
        return self._robots.allowed(url)

    # ---- GetRecord ------------------------------------------------------------------------------
    def get_record(self, unit: str, repo: Repository, identifier: str, prefix: str = '',
                   **obs) -> OaiRecord:
        """ONE record. The ONLY OAI verb that can answer a question about a specific work."""
        prefix = prefix or (repo.metadata_prefixes[0] if repo.metadata_prefixes else 'oai_dc')
        if not identifier:
            # WE NEVER ASKED. Sol: a missing DOI->OAI mapping does not close a repository.
            self.acq.ledger.emit(unit, EventKind.BUDGET_STOPPED, self.acq.actor,
                                 adapter=repo.adapter, deferral_reason='no_oai_identifier',
                                 repository=repo.repository_id)
            return OaiRecord(repo.repository_id, '', prefix, NO_IDENTIFIER)

        url = _url(repo, verb='GetRecord', identifier=identifier, metadataPrefix=prefix)
        ok, why = self._robots_ok(url)
        if not ok:
            self.acq.ledger.emit(unit, EventKind.BUDGET_STOPPED, self.acq.actor,
                                 adapter=repo.adapter, url=url, deferral_reason='robots_disallowed',
                                 reason_text=why, repository=repo.repository_id)
            return OaiRecord(repo.repository_id, identifier, prefix, ROBOTS_DISALLOWED)

        r = self.acq.get(unit, repo.adapter, url, tries=3,
                         # The record for one identifier in one format DOES NOT CHANGE between runs,
                         # and re-asking a repository the same question every night is how a polite
                         # client becomes an impolite one.
                         cacheable=True, repository=repo.repository_id,
                         metadata_prefix=prefix, oai_identifier=identifier, **obs)
        if not r.ok:
            # THE TRANSPORT FAILED. That is already on the ledger, as THROTTLED / BLOCKED / a 404, and
            # it is NOT an OAI outcome — this repository never got to say anything.
            return OaiRecord(repo.repository_id, identifier, prefix, r.outcome, raw=r.raw)

        rec = parse_record(r.raw, repo, identifier, prefix)
        self.acq.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.acq.actor,
                             adapter=repo.adapter, url=url, request_id=r.request_id,
                             http_status=r.http_status, repository=repo.repository_id,
                             # NOT `status=` — that key IS a label, and the ledger refuses it. What the
                             # repository said about its own record is `record_state`, an observation.
                             record_state=('deleted' if rec.deleted else 'present'),
                             oai_outcome=rec.outcome, oai_error=rec.oai_error,
                             n_bytes=len(r.raw), metadata_prefix=prefix)
        return rec

    def get_record_any_format(self, unit: str, repo: Repository, identifier: str,
                              **obs) -> OaiRecord:
        """Walk `metadata_prefixes` IN ORDER — RICHEST FIRST — and stop at the first that answers.

        THE ORDER IS THE DEFENCE (silent failure #1). JATS/METS/MODS/TEI have somewhere to put a FILE
        URL. `oai_dc` has somewhere to put a LANDING PAGE. A repository that supports both and is asked
        for oai_dc will happily give you the landing page and never mention that the PDF was one
        `metadataPrefix` away. `cannotDisseminateFormat` is the expected answer to the first ask, not
        an error — it is how we find out what this repository can actually do.
        """
        last: OaiRecord | None = None
        for prefix in (repo.metadata_prefixes or ('oai_dc',)):
            rec = self.get_record(unit, repo, identifier, prefix, **obs)
            last = rec
            if rec.outcome == RECORD_RETURNED:
                return rec
            if rec.outcome in (RECORD_DELETED, ID_DOES_NOT_EXIST):
                return rec               # the repository ANSWERED about this id. Another format
                #                        # will not make a deleted record undeleted.
            if rec.outcome != CANNOT_DISSEMINATE:
                return rec               # a throttle or a 5xx is not a reason to try more formats
        return last or OaiRecord(repo.repository_id, identifier, '', NO_IDENTIFIER)

    # ---- the candidates this record supports ----------------------------------------------------
    def propose_candidates(self, unit: str, repo: Repository, rec: OaiRecord,
                           resolver_request_id: str = '') -> list[str]:
        """The DOCUMENT urls become candidates. THE LANDING PAGES DO NOT.

        A landing page is still RECORDED — it is a real observation and a real lead — but it is
        recorded with `link_role='landing_page'`, and the fetch loop selects candidates from what this
        function RETURNS, which is documents only. The 535-word repository splash page cannot enter
        the corpus as a document, because nothing ever proposes it as one.
        """
        ids: list[str] = []
        for lk in document_urls(rec, repo):
            ids.append(self.acq.candidate(
                unit, repo.adapter, lk.url, resolver_request_id=resolver_request_id,
                media_hint=lk.media_hint, link_role=lk.role, selector=lk.selector,
                repository=repo.repository_id, oai_identifier=rec.identifier))
        for lk in landing_urls(rec, repo) + relative_refs(rec, repo):
            # An OBSERVATION, on the ledger, that is NOT a candidate. It has no candidate_id, so no
            # manifestation can ever descend from it and no route can be credited with it.
            self.acq.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.acq.actor,
                                 adapter=repo.adapter, url=lk.url, link_role=lk.role,
                                 selector=lk.selector, repository=repo.repository_id,
                                 reason_text=('a page ABOUT a document is not a document'
                                              if lk.role == 'landing_page' else
                                              'the record names a file but not where it lives'))
        return ids

    # ---- ListRecords, RESUMABLE (this is how the local index gets built) --------------------------
    def list_records(self, unit: str, repo: Repository, prefix: str = '', *,
                     set_spec: str = '', from_: str = '', until: str = '',
                     max_pages: int = 50) -> Iterator[OaiRecord]:
        """Resumption tokens, WITH A PERSISTED CURSOR (Sol §2 silent failure #5).

        A resumption token expires, a harvest gets killed at 3am, and a harvester that kept its cursor
        in RAM starts again at page one — hammering a repository through the pages it already has, and
        (worse) making the run look like it made no progress. The cursor is written after EVERY page.
        """
        prefix = prefix or (repo.metadata_prefixes[0] if repo.metadata_prefixes else 'oai_dc')
        self.cursor_dir.mkdir(parents=True, exist_ok=True)
        cpath = self.cursor_dir / f'{repo.repository_id}.{prefix}.{set_spec or "all"}.json'
        token = ''
        if cpath.exists():
            try:
                token = str(json.loads(cpath.read_text()).get('resumption_token') or '')
            except Exception:
                token = ''

        for _page in range(max_pages):
            url = (_url(repo, verb='ListRecords', resumptionToken=token) if token
                   else _url(repo, verb='ListRecords', metadataPrefix=prefix, set=set_spec,
                             **{'from': from_, 'until': until}))
            ok, why = self._robots_ok(url)
            if not ok:
                self.acq.ledger.emit(unit, EventKind.BUDGET_STOPPED, self.acq.actor,
                                     adapter=repo.adapter, url=url,
                                     deferral_reason='robots_disallowed', reason_text=why)
                return
            r = self.acq.get(unit, repo.adapter, url, tries=3, repository=repo.repository_id)
            if not r.ok:
                return                       # THROTTLED / DEFERRED / 5xx: the cursor stays where it is,
                #                            # so the next run picks up exactly here.
            try:
                root = ET.fromstring(r.raw)
            except Exception:
                return
            for rnode in _find_all(root, 'record'):
                hdrs = _find_all(rnode, 'header')
                hdr = hdrs[0] if hdrs else None
                if hdr is None:
                    continue
                ident = next((e.text or '' for e in _find_all(hdr, 'identifier')), '').strip()
                deleted = (_attr(hdr, 'status') or '').lower() == 'deleted'
                mds = _find_all(rnode, 'metadata')
                yield OaiRecord(
                    repo.repository_id, ident, prefix,
                    RECORD_DELETED if deleted else RECORD_RETURNED,
                    raw=ET.tostring(rnode), root=rnode,
                    metadata_el=(mds[0] if mds and not deleted else None))

            toks = _find_all(root, 'resumptionToken')
            token = (toks[0].text or '').strip() if toks else ''
            # ---- THE CURSOR IS WRITTEN AFTER EVERY PAGE, NOT AT THE END ----------------------
            cpath.write_text(json.dumps({'repository': repo.repository_id, 'prefix': prefix,
                                         'set': set_spec, 'resumption_token': token,
                                         'updated': time.time()}, sort_keys=True))
            if not token:
                return                       # an EMPTY token is the end of the list, per the spec


if __name__ == '__main__':
    print(__doc__)
    repos = load_repositories()
    print(f'{len(repos)} OAI repositories (config/source_routes.yaml: oai_repositories)\n')
    for rid, r in repos.items():
        constructible = 'CONSTRUCTIBLE from ' + r.identifier_from if r.identifier_pattern else \
            'identifier MUST come from CORE / OpenAIRE / the local index'
        print(f'  {rid:16s} {r.base_url or "(template row — filled in per repository)"}')
        print(f'  {"":16s} prefixes={list(r.metadata_prefixes)}  {constructible}')
    print('\nInvariants are tested by:  python3 scripts/test_oai_pmh.py')
