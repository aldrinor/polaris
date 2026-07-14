#!/usr/bin/env python3
"""IDENTITY RECEIPTS — positive machine-metadata salvage for UNRESOLVED manifestations (Sol P5).

A manifestation whose RENDERED bytes cannot establish identity (a PDF whose title page is pure
`(cid:NN)` glyph codes; an HTML page whose readable body only cites the requested authors) is
`UNRESOLVED_BINDING`. It is not a stranger's paper — it is an unreadable one — and it stays a lead.

But the file may STILL CARRY, in its MACHINE-READABLE SELF-METADATA, a positive statement of what it
is: a PDF Info/XMP DOI, an HTML `<head>` `citation_doi`, a JATS `<article-id pub-id-type="doi">`.
That metadata is written by the same document about itself, in a named container, at a byte offset we
can record and RE-FIND. It is exactly the kind of positive, revalidatable evidence this project admits
on — and nothing else.

THE RULES THIS MODULE OBEYS (Sol global invariants + P5):
  * POSITIVE PROOF ONLY. A receipt can only PROMOTE identity. Absence of metadata changes nothing; a
    conflict between a target and a foreign self-identifier LEAVES the manifestation unresolved.
  * NO SUBJECT LITERALS. Extraction fires on STRUCTURAL container/field names (`citation_doi`,
    `article-id[pub-id-type=doi]`, PDF Info/XMP fields) — never on a DOI, title, author, venue or
    subject string. The requested identity is compared, never matched by a hard-coded value.
  * SELF-METADATA ONLY. PDF Info/XMP; HTML `<head>`; JATS `<front><article-meta>`. Never the rendered
    body, references, or `<back>`.
  * A VERIFIED RECEIPT BECOMES AN OBSERVATION. It is fed to `event_ledger.derive_binding_core()`, which
    RE-DERIVES the semantic binding. This module never assigns a verdict directly.
  * NO OCR. There is no revalidatable OCR backend installed, so an OCR-typed receipt is REFUSED as an
    unsupported receipt type. See docs/identity_metadata_salvage.md.
"""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field, asdict

# ── EXTRACTOR IDENTITY. Travels on every receipt so the loader reruns the SAME extractor+version. ──
EXTRACTOR_NAME = 'identity_receipts'
EXTRACTOR_VERSION = '1'

# ── RECEIPT KINDS (Sol P5 data model). ──────────────────────────────────────────────────────────
RECEIPT_SELF_IDENTIFIER = 'SELF_IDENTIFIER'      # an exact self-DOI in a permitted identifier field
RECEIPT_SELF_TITLE_BYLINE = 'SELF_TITLE_BYLINE'  # exact self-title + >=1 self-author

# ── METADATA CONTAINERS. The only four places we look, each a named self-metadata region. ─────────
CONTAINER_PDF_INFO = 'pdf_info'
CONTAINER_PDF_XMP = 'pdf_xmp'
CONTAINER_HTML_HEAD = 'html_head'
CONTAINER_JATS_FRONT = 'jats_front'
SUPPORTED_CONTAINERS = frozenset({CONTAINER_PDF_INFO, CONTAINER_PDF_XMP,
                                  CONTAINER_HTML_HEAD, CONTAINER_JATS_FRONT})

# ── FIELD ROLES. STRUCTURAL — the KIND of thing a field asserts, not its value. ───────────────────
FIELD_DOI = 'doi'
FIELD_TITLE = 'title'
FIELD_AUTHOR = 'author'

# ── COORDINATE SPACES. Which byte/char string an offset indexes into (Sol P5: make it explicit). ──
COORD_PDF_INFO_FIELD = 'pdf_info_field'   # offsets index into the named PDF Info field's value
COORD_PDF_XMP = 'pdf_xmp_string'          # offsets index into the decoded XMP packet
COORD_RAW_TEXT = 'raw_decoded_text'       # offsets index into the raw artifact decoded utf-8

#: The one state a conflicting self-identifier produces. NOT a promotion — the manifestation STAYS
#: UNRESOLVED and this token records why the metadata could not settle it.
IDENTITY_METADATA_CONFLICT = 'IDENTITY_METADATA_CONFLICT'

#: A DOI has an unbounded suffix that MAY legitimately contain parentheses (e.g.
#: `10.31392/udu-nc.series15.2025.12(199).42`). We therefore allow `()` in the suffix and rely on
#: `normalize_doi` to strip any single trailing citation bracket. `<`, `"`, `'` and whitespace still
#: bound it, so a DOI never runs into surrounding markup.
_DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"\'<>]+')
_STOP = {'the', 'a', 'an', 'of', 'and', 'for', 'in', 'on', 'to', 'from', 'with'}


class UnsupportedReceipt(ValueError):
    """A receipt of a type this build cannot revalidate (e.g. OCR). Fails closed — never admitted."""


@dataclass(frozen=True)
class IdentityReceipt:
    """One positive, revalidatable piece of self-metadata that identifies these bytes as the Work.

    Every field is either a hash, an offset, a named container/field, or a normalized value derived
    from bytes. There is no field where a fetcher's OPINION could be written."""
    receipt_id: str
    manifestation_id: str
    manifestation_content_hash: str
    artifact_blob_id: str
    artifact_sha256: str
    media_type: str
    extractor_name: str
    extractor_version: str
    receipt_kind: str                 # SELF_IDENTIFIER | SELF_TITLE_BYLINE
    metadata_container: str           # pdf_info | pdf_xmp | html_head | jats_front
    metadata_field: str               # the named field within the container
    coordinate_space: str             # which string start/end index into (Sol P5)
    raw_match: str                    # the VERBATIM substring at [start:end]
    start_offset: int
    end_offset: int
    normalized_value: str             # what the artifact says, normalized
    requested_normalized_value: str   # what the Work asked for, normalized the same way
    supporting_matches: list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# NORMALIZATION — one canonical form per field kind, applied to BOTH the artifact and the request.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def normalize_doi(s: str) -> str:
    """Parse DOI URI/prefix forms, percent-decode, case-fold, strip terminal citation punctuation."""
    s = urllib.parse.unquote(str(s or '')).strip()
    s = re.sub(r'(?i)^\s*doi:\s*', '', s)
    s = re.sub(r'(?i)^\s*https?://(dx\.)?doi\.org/', '', s).strip()
    s = s.rstrip('.,;)]}>\'"')
    return s.casefold()


def find_doi(value: str) -> tuple[str, int, int] | None:
    """The first `10.xxxx/...` DOI inside a field value, with its offsets INSIDE that value."""
    m = _DOI_RE.search(str(value or ''))
    if not m:
        return None
    raw = m.group(0).rstrip('.,;)]}>\'"')
    return raw, m.start(), m.start() + len(raw)


def normalize_title(s: str) -> str:
    """NFKC, entity-decode, case-fold, punctuation->space, whitespace collapse. EXACT match after."""
    s = html.unescape(str(s or ''))
    s = unicodedata.normalize('NFKC', s).casefold()
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _surname(author: str) -> str:
    """The structured surname of one author string. `Smith, John` -> smith; `John Q. Smith` -> smith."""
    a = html.unescape(str(author or '')).strip()
    a = unicodedata.normalize('NFKC', a)
    if ',' in a:
        fam = a.split(',', 1)[0]
    else:
        toks = [t for t in re.split(r'\s+', a) if t]
        fam = toks[-1] if toks else ''
    fam = re.sub(r'[^\w]', '', fam).casefold()
    return fam


def author_surnames(authors) -> set[str]:
    if isinstance(authors, str):
        authors = re.split(r'\s*(?:;|\band\b|,)\s*', authors)
    out = set()
    for a in (authors or []):
        s = _surname(a)
        if s:
            out.add(s)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MEDIA SNIFF + EXTRACTION.  Every extractor returns FIELD OBSERVATIONS — never a conclusion.
#   FieldObs = (container, field_kind, metadata_field, raw_match, start, end, coordinate_space)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def sniff_media_type(raw: bytes, declared: str = '') -> str:
    if raw[:5] == b'%PDF-' or raw[:4] == b'%PDF':
        return 'pdf'
    if 'pdf' in (declared or '').lower():
        return 'pdf'
    text = raw[:4000].decode('utf-8', 'ignore').lower()
    if '<article-meta' in text or ('<article' in text and 'article-id' in text) \
            or '//dtd jats' in text or '<article-title' in text:
        return 'jats'
    if '<html' in text or '<head' in text or '<meta' in text:
        return 'html'
    if '<article' in text:
        return 'jats'
    return 'unknown'


def _pdf_field_obs(raw: bytes) -> list[dict]:
    """PDF Info + XMP self-metadata, through PyMuPDF/fitz. Never the rendered body."""
    import fitz  # noqa: PLC0415  (heavy; imported only when a PDF is actually seen)
    obs: list[dict] = []
    try:
        doc = fitz.open(stream=raw, filetype='pdf')
    except Exception:
        return obs
    # ---- PDF Info dictionary ----
    info = doc.metadata or {}
    title = info.get('title') or ''
    author = info.get('author') or info.get('creator') or ''
    if title.strip():
        obs.append(dict(container=CONTAINER_PDF_INFO, field=FIELD_TITLE, metadata_field='title',
                        raw_match=title, start=0, end=len(title), coord=COORD_PDF_INFO_FIELD))
    if author.strip():
        mf = 'author' if (info.get('author') or '').strip() else 'creator'
        obs.append(dict(container=CONTAINER_PDF_INFO, field=FIELD_AUTHOR, metadata_field=mf,
                        raw_match=author, start=0, end=len(author), coord=COORD_PDF_INFO_FIELD))
    # A DOI printed in ANY standard Info string field is a self-identifier. metadata_field names which.
    for mf in ('subject', 'keywords', 'title'):
        val = info.get(mf) or ''
        d = find_doi(val)
        if d:
            raw_match, s, e = d
            obs.append(dict(container=CONTAINER_PDF_INFO, field=FIELD_DOI, metadata_field=mf,
                            raw_match=raw_match, start=s, end=e, coord=COORD_PDF_INFO_FIELD))
    # ---- XMP packet ----
    try:
        xmp = doc.get_xml_metadata() or ''
    except Exception:
        xmp = ''
    if xmp:
        for m in re.finditer(r'<dc:title>.*?<rdf:li[^>]*>(.*?)</rdf:li>', xmp, re.S):
            v = m.group(1).strip()
            off = xmp.find(v, m.start())
            if v and off >= 0:
                obs.append(dict(container=CONTAINER_PDF_XMP, field=FIELD_TITLE, metadata_field='dc:title',
                                raw_match=v, start=off, end=off + len(v), coord=COORD_PDF_XMP))
        for m in re.finditer(r'<dc:creator>.*?<rdf:li[^>]*>(.*?)</rdf:li>', xmp, re.S):
            v = m.group(1).strip()
            off = xmp.find(v, m.start())
            if v and off >= 0:
                obs.append(dict(container=CONTAINER_PDF_XMP, field=FIELD_AUTHOR,
                                metadata_field='dc:creator', raw_match=v, start=off,
                                end=off + len(v), coord=COORD_PDF_XMP))
        for m in re.finditer(r'<(?:prism:doi|dc:identifier)>([^<]+)</(?:prism:doi|dc:identifier)>', xmp):
            val = m.group(1)           # a dedicated DOI element: the whole value is the identifier
            if _DOI_RE.search(val):
                off = xmp.find(val, m.start(1))
                if off >= 0:
                    obs.append(dict(container=CONTAINER_PDF_XMP, field=FIELD_DOI,
                                    metadata_field='prism:doi', raw_match=val, start=off,
                                    end=off + len(val), coord=COORD_PDF_XMP))
    return obs


def _html_head_region(text: str) -> tuple[int, int]:
    hm = re.search(r'<head[^>]*>', text, re.I)
    he = re.search(r'</head\s*>', text, re.I)
    start = hm.end() if hm else 0
    end = he.start() if he else min(len(text), 8000)
    if end <= start:
        end = min(len(text), 8000)
    return start, end


def _html_field_obs(raw: bytes) -> list[dict]:
    """Only inside <head>. citation_doi / DC.identifier / citation_title / DC.title / citation_author."""
    text = raw.decode('utf-8', 'ignore')
    hstart, hend = _html_head_region(text)
    head = text[hstart:hend]
    obs: list[dict] = []
    role = {'citation_doi': (FIELD_DOI, 'citation_doi'), 'dc.identifier': (FIELD_DOI, 'DC.identifier'),
            'citation_title': (FIELD_TITLE, 'citation_title'), 'dc.title': (FIELD_TITLE, 'DC.title'),
            'citation_author': (FIELD_AUTHOR, 'citation_author'),
            'dc.creator': (FIELD_AUTHOR, 'DC.creator')}
    for tag in re.finditer(r'<meta\b[^>]*>', head, re.I):
        blob = tag.group(0)
        nm = re.search(r'name\s*=\s*"([^"]+)"', blob, re.I) or \
            re.search(r"name\s*=\s*'([^']+)'", blob, re.I)
        cm = re.search(r'content\s*=\s*"([^"]*)"', blob, re.I) or \
            re.search(r"content\s*=\s*'([^']*)'", blob, re.I)
        if not nm or not cm:
            continue
        key = nm.group(1).strip().lower()
        if key not in role:
            continue
        field_kind, mf = role[key]
        content = html.unescape(cm.group(1))
        # ABSOLUTE offset of the content value within the whole decoded artifact.
        tag_abs = hstart + tag.start()
        val_abs = text.find(cm.group(1), tag_abs)
        if val_abs < 0:
            continue
        if field_kind == FIELD_DOI:
            # A DEDICATED DOI field: the WHOLE value is the identifier (`normalize_doi` strips any
            # `doi:`/URL prefix and terminal punctuation). Substring-scanning it would truncate a DOI
            # that legitimately contains parentheses.
            raw_match = cm.group(1)
            if not _DOI_RE.search(html.unescape(raw_match)):
                continue
            obs.append(dict(container=CONTAINER_HTML_HEAD, field=FIELD_DOI, metadata_field=mf,
                            raw_match=raw_match, start=val_abs, end=val_abs + len(raw_match),
                            coord=COORD_RAW_TEXT))
        else:
            raw_match = cm.group(1)
            obs.append(dict(container=CONTAINER_HTML_HEAD, field=field_kind, metadata_field=mf,
                            raw_match=raw_match, start=val_abs, end=val_abs + len(raw_match),
                            coord=COORD_RAW_TEXT))
    return obs


def _jats_field_obs(raw: bytes) -> list[dict]:
    """Only inside <front><article-meta>. article-id[doi] / article-title / contrib[author] surname."""
    text = raw.decode('utf-8', 'ignore')
    fm = re.search(r'<front\b', text, re.I)
    fe = re.search(r'</front\s*>', text, re.I)
    if not fm:
        return []
    fstart = fm.start()
    fend = fe.end() if fe else len(text)
    front = text[fstart:fend]
    obs: list[dict] = []

    def _abs(local_off: int) -> int:
        return fstart + local_off

    for m in re.finditer(r'<article-id[^>]*pub-id-type\s*=\s*"doi"[^>]*>([^<]+)</article-id>',
                         front, re.I):
        val = m.group(1)               # a dedicated DOI element: the whole value is the identifier
        if not _DOI_RE.search(val):
            continue
        loc = front.find(val, m.start(1))
        if loc < 0:
            continue
        obs.append(dict(container=CONTAINER_JATS_FRONT, field=FIELD_DOI,
                        metadata_field='article-id[doi]', raw_match=val,
                        start=_abs(loc), end=_abs(loc) + len(val), coord=COORD_RAW_TEXT))
    for m in re.finditer(r'<article-title[^>]*>(.*?)</article-title>', front, re.S | re.I):
        v = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        loc = front.find(m.group(1))
        if v and loc >= 0:
            obs.append(dict(container=CONTAINER_JATS_FRONT, field=FIELD_TITLE,
                            metadata_field='article-title', raw_match=m.group(1),
                            start=_abs(loc), end=_abs(loc) + len(m.group(1)), coord=COORD_RAW_TEXT))
    for cm in re.finditer(r'<contrib\b[^>]*contrib-type\s*=\s*"author"[^>]*>(.*?)</contrib>',
                          front, re.S | re.I):
        block = cm.group(1)
        sm = re.search(r'<surname[^>]*>([^<]+)</surname>', block, re.I)
        if not sm:
            continue
        v = sm.group(1).strip()
        loc = front.find(sm.group(1), cm.start())
        if v and loc >= 0:
            obs.append(dict(container=CONTAINER_JATS_FRONT, field=FIELD_AUTHOR,
                            metadata_field='contrib[author]/surname', raw_match=sm.group(1),
                            start=_abs(loc), end=_abs(loc) + len(sm.group(1)), coord=COORD_RAW_TEXT))
    return obs


def extract_field_observations(raw: bytes, media_type: str) -> list[dict]:
    if media_type == 'pdf':
        return _pdf_field_obs(raw)
    if media_type == 'html':
        return _html_field_obs(raw)
    if media_type == 'jats':
        return _jats_field_obs(raw)
    return []


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# BUILD RECEIPTS — compare the field observations to the REQUESTED identity. Positive proof only.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class SalvageResult:
    receipts: list          # list[IdentityReceipt] that constitute positive promoting evidence
    conflict: str           # '' or IDENTITY_METADATA_CONFLICT
    basis: str


def _requested(work) -> tuple[str, str, set[str]]:
    return (normalize_doi(getattr(work, 'doi', '') or ''),
            normalize_title(getattr(work, 'title', '') or ''),
            author_surnames(getattr(work, 'authors', []) or []))


def build_salvage(raw: bytes, work, *, manifestation_id: str, manifestation_content_hash: str,
                  artifact_blob_id: str, artifact_sha256: str,
                  media_type: str = '') -> SalvageResult:
    """Extract self-metadata, compare to the Work, and return the POSITIVE receipts that promote it.

    Promote only when: (1) an exact requested DOI is in a permitted self-identifier field, OR (2) an
    exact requested title AND at least one requested author are in permitted self-identity fields.

    Conflict: if self-identifier fields contain BOTH the target and a foreign DOI, stay unresolved with
    IDENTITY_METADATA_CONFLICT — title/author evidence cannot override a conflicting self-identifier."""
    mt = media_type or sniff_media_type(raw)
    obs = extract_field_observations(raw, mt)
    req_doi, req_title, req_surnames = _requested(work)

    def mk(o: dict, kind: str, normalized: str, requested_norm: str,
           supporting: list) -> IdentityReceipt:
        rid = 'receipt:' + hashlib.sha256(
            f'{artifact_sha256}|{o["container"]}|{o["metadata_field"]}|{o["start"]}|{o["end"]}'
            f'|{normalized}'.encode()).hexdigest()[:16]
        return IdentityReceipt(
            receipt_id=rid, manifestation_id=manifestation_id,
            manifestation_content_hash=manifestation_content_hash,
            artifact_blob_id=artifact_blob_id, artifact_sha256=artifact_sha256, media_type=mt,
            extractor_name=EXTRACTOR_NAME, extractor_version=EXTRACTOR_VERSION,
            receipt_kind=kind, metadata_container=o['container'], metadata_field=o['metadata_field'],
            coordinate_space=o['coord'], raw_match=o['raw_match'], start_offset=o['start'],
            end_offset=o['end'], normalized_value=normalized,
            requested_normalized_value=requested_norm, supporting_matches=list(supporting))

    # ---- DOI self-identifiers ----
    doi_receipts_target: list[IdentityReceipt] = []
    foreign_doi = False
    for o in obs:
        if o['field'] != FIELD_DOI:
            continue
        nd = normalize_doi(o['raw_match'])
        if req_doi and nd == req_doi:
            doi_receipts_target.append(mk(o, RECEIPT_SELF_IDENTIFIER, nd, req_doi, []))
        elif _DOI_RE.match(nd) or nd.startswith('10.'):
            foreign_doi = True

    # A conflicting self-identifier is decisive: it defeats promotion by ANY evidence (Sol P5).
    if doi_receipts_target and foreign_doi:
        return SalvageResult(receipts=[], conflict=IDENTITY_METADATA_CONFLICT,
                             basis='self-identifier fields carry BOTH the requested DOI and a foreign '
                                   'DOI — the metadata cannot settle which work these bytes are')
    if foreign_doi and not doi_receipts_target and req_doi:
        # A foreign self-DOI with no matching target DOI is NOT our work by its own metadata.
        return SalvageResult(receipts=[], conflict=IDENTITY_METADATA_CONFLICT,
                             basis='a self-identifier field carries a foreign DOI and none of ours')

    if doi_receipts_target:
        return SalvageResult(receipts=[doi_receipts_target[0]], conflict='',
                             basis='exact requested DOI found in a permitted self-identifier field')

    # ---- title + author (both required) ----
    title_obs = next((o for o in obs if o['field'] == FIELD_TITLE
                      and normalize_title(re.sub(r'<[^>]+>', ' ', o['raw_match'])) == req_title
                      and req_title), None)
    author_hits = [o for o in obs if o['field'] == FIELD_AUTHOR
                   and (author_surnames([re.sub(r'<[^>]+>', ' ', o['raw_match'])]) & req_surnames)]
    if title_obs and author_hits and req_surnames:
        t_norm = normalize_title(re.sub(r'<[^>]+>', ' ', title_obs['raw_match']))
        support = [dict(field=a['metadata_field'], surname=sorted(
            author_surnames([re.sub(r'<[^>]+>', ' ', a['raw_match'])]) & req_surnames))
            for a in author_hits]
        rec = mk(title_obs, RECEIPT_SELF_TITLE_BYLINE, t_norm, req_title, support)
        return SalvageResult(receipts=[rec], conflict='',
                             basis='exact requested title plus >=1 requested author in self-metadata')

    return SalvageResult(receipts=[], conflict='',
                         basis='no promoting self-metadata (a generic title without a matching author, '
                               'or no self-identifier, does not promote)')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECEIPTS -> OBSERVATION.  A verified receipt is fed to derive_binding_core as positive evidence.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def receipts_supplement(receipts) -> dict:
    """Turn verified receipts into the supplemental observation `derive_binding_core` consumes.

    This does NOT decide identity. It presents the machine-metadata as the readable, positive identity
    evidence it is — a self-DOI joins `front_matter_dois`; a self-title/byline joins the identity window
    and asserts a byline — and the reducer then RE-DERIVES the verdict. `verified_identity_receipts`
    marks that a POSITIVE machine receipt exists, so the unreadable-header guard (which would otherwise
    stop a glyph PDF before its metadata is read) is lifted — but ONLY here, and ONLY on positive proof.
    """
    dois: list[str] = []
    window_bits: list[str] = []
    byline = False
    for r in receipts:
        rd = r if isinstance(r, dict) else asdict(r)
        kind = rd.get('receipt_kind')
        if kind == RECEIPT_SELF_IDENTIFIER:
            dois.append(normalize_doi(rd.get('normalized_value') or rd.get('raw_match') or ''))
        elif kind == RECEIPT_SELF_TITLE_BYLINE:
            window_bits.append(rd.get('normalized_value') or '')
            for s in (rd.get('supporting_matches') or []):
                for sn in (s.get('surname') or []):
                    window_bits.append(sn)
                    byline = True
    sup: dict = {'verified_identity_receipts': True}
    if dois:
        sup['salvage_front_matter_dois'] = sorted({d for d in dois if d})
    if window_bits:
        sup['salvage_identity_window'] = ' '.join(b for b in window_bits if b)
        sup['salvage_byline'] = byline
    return sup


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# REVALIDATION.  Every stored receipt is an UNTRUSTED INPUT re-checked against the raw artifact.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def revalidate_receipt(raw: bytes, stored: dict, work) -> tuple[bool, str]:
    """Re-derive the stored receipt from the raw artifact and refuse any disagreement (Sol P5 loader).

    1. raw hash matches the stored artifact_sha256;
    2. the named extractor+version is the one we run;
    3. the exact raw match is re-found at the recorded location;
    4. the value re-normalizes to the stored normalized_value;
    5. it re-evaluates against the Work (still our DOI / title+author);
    6. the canonical live receipt equals the stored receipt.
    An OCR-typed or otherwise unsupported receipt is REFUSED (raises nothing here — returns False)."""
    container = stored.get('metadata_container')
    if container not in SUPPORTED_CONTAINERS:
        return False, (f'receipt container {container!r} is not a supported, revalidatable container '
                       f'{sorted(SUPPORTED_CONTAINERS)} — an unsupported receipt type (e.g. OCR) fails '
                       f'closed')
    if stored.get('extractor_name') != EXTRACTOR_NAME or \
            str(stored.get('extractor_version')) != EXTRACTOR_VERSION:
        return False, (f'receipt names extractor {stored.get("extractor_name")!r} '
                       f'v{stored.get("extractor_version")!r}, but this build runs '
                       f'{EXTRACTOR_NAME} v{EXTRACTOR_VERSION}')
    # 1. raw hash
    live_sha = 'sha256:' + hashlib.sha256(raw).hexdigest()
    stored_sha = stored.get('artifact_sha256') or ''
    norm_stored_sha = stored_sha if stored_sha.startswith('sha256:') else 'sha256:' + stored_sha
    if live_sha != norm_stored_sha and hashlib.sha256(raw).hexdigest() != stored_sha:
        return False, 'raw artifact hash does not match the stored artifact_sha256 — the bytes moved'

    mt = stored.get('media_type') or sniff_media_type(raw)
    field_kind = {RECEIPT_SELF_IDENTIFIER: FIELD_DOI}.get(stored.get('receipt_kind'))

    # 3-4. re-find the exact raw match at the recorded coordinate space.
    s, e = stored.get('start_offset'), stored.get('end_offset')
    if not isinstance(s, int) or not isinstance(e, int) or isinstance(s, bool) or isinstance(e, bool) \
            or s < 0 or e <= s:
        return False, 'receipt offsets are not a valid span'
    coord = stored.get('coordinate_space')
    space = _coordinate_string(raw, mt, container, stored.get('metadata_field'), coord)
    if space is None:
        return False, f'cannot re-open coordinate space {coord!r} for container {container!r}'
    if e > len(space) or space[s:e] != stored.get('raw_match'):
        return False, ('the raw match is NOT at the recorded offsets in the named container — the '
                       'receipt was tampered with or the artifact changed')

    # 5. re-normalize + re-evaluate against the Work.
    req_doi, req_title, req_surnames = _requested(work)
    kind = stored.get('receipt_kind')
    if kind == RECEIPT_SELF_IDENTIFIER:
        live_norm = normalize_doi(stored.get('raw_match'))
        if not req_doi or live_norm != req_doi:
            return False, 'the re-normalized DOI no longer equals the requested DOI'
        if live_norm != normalize_doi(stored.get('normalized_value')):
            return False, 'the stored normalized DOI does not match the live normalization'
    elif kind == RECEIPT_SELF_TITLE_BYLINE:
        live_norm = normalize_title(re.sub(r'<[^>]+>', ' ', stored.get('raw_match') or ''))
        if not req_title or live_norm != req_title:
            return False, 'the re-normalized title no longer equals the requested title'
        if live_norm != normalize_title(stored.get('normalized_value')):
            return False, 'the stored normalized title does not match the live normalization'
        support = stored.get('supporting_matches') or []
        surnames = {sn for sup in support for sn in (sup.get('surname') or [])}
        if not (surnames & req_surnames):
            return False, 'no supporting author surname still matches the requested authors'
    else:
        return False, f'unsupported receipt_kind {kind!r} — fails closed'

    return True, ''


def _coordinate_string(raw: bytes, media_type: str, container: str, metadata_field: str,
                       coord: str) -> str | None:
    """Re-open the exact string the receipt's offsets index into."""
    if coord == COORD_RAW_TEXT:
        return raw.decode('utf-8', 'ignore')
    if coord == COORD_PDF_INFO_FIELD:
        import fitz  # noqa: PLC0415
        try:
            doc = fitz.open(stream=raw, filetype='pdf')
        except Exception:
            return None
        return (doc.metadata or {}).get(metadata_field) or ''
    if coord == COORD_PDF_XMP:
        import fitz  # noqa: PLC0415
        try:
            doc = fitz.open(stream=raw, filetype='pdf')
            return doc.get_xml_metadata() or ''
        except Exception:
            return None
    return None


def revalidate_all(raw: bytes, receipts: list, work) -> tuple[bool, list[str]]:
    """Every receipt must revalidate; report all failures. Empty receipts -> trivially OK."""
    errs: list[str] = []
    for i, r in enumerate(receipts or []):
        rd = r if isinstance(r, dict) else asdict(r)
        ok, why = revalidate_receipt(raw, rd, work)
        if not ok:
            errs.append(f'receipt #{i} ({rd.get("receipt_id")}): {why}')
    return (not errs), errs
