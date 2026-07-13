#!/usr/bin/env python3
"""VERSION ALIGNMENT — Sol's condition for admitting recovered working-paper text as journal evidence.

THE QUESTION THIS ANSWERS, AND THE ONLY ONE

  We hold bytes. A corpus row says those bytes belong to a journal article, by DOI. For a large part
  of the corpus THAT IS FALSE: the bytes are an NBER working paper, a Fed discussion paper, an EHES
  working paper, a repository deposit -- and, in one case, SOMEONE ELSE'S PAPER ENTIRELY.

  A span from the working paper may NOT be attributed to the journal article. Peer review changes
  numbers; that is the whole point of peer review. The working paper is a DISCOVERY LEAD.

  It becomes journal-attributable in exactly one way: WE GET THE JOURNAL VERSION'S BYTES AND FIND THE
  SPAN VERBATIM INSIDE THEM. Nothing else does it. Not a title match, not a DOI match, not an
  author's word, not "it's obviously the same paper".

THE THREE OUTCOMES, AND WHY THE THIRD IS NOT THE SECOND

  ALIGNED           we hold the journal version's bytes and the span is in them, verbatim
  NOT_ALIGNED       we hold the journal version's bytes and THE SPAN IS NOT IN THEM  <- peer review
  NO_JOURNAL_BYTES  we do not hold the journal version -> the span STAYS INADMISSIBLE

  and, kept rigorously separate from all three:

  BACKEND_FAILED    WE could not ask. HTTP 429, a timeout, a DNS failure.

  BACKEND_FAILED IS NOT "no free copy exists". That conflation is the exact error that has cost this
  project the night: a fact about OUR REQUEST RATE, printed as a fact about the world. Every network
  call in this file returns a typed outcome, and `no OA journal version` is recorded ONLY when a
  backend actually ANSWERED and the answer was empty.

WHAT COUNTS AS A JOURNAL VERSION

  Unpaywall and OpenAlex both label every OA location with a `version`:
      publishedVersion   the typeset article of record        -> exact_copy_of        (span-preserving)
      acceptedVersion    post-peer-review author manuscript   -> accepted_manuscript_of (span-preserving)
      submittedVersion   the PREPRINT / WORKING PAPER         -> predecessor_of   (TRANSFERS NOTHING)
  That field is a version statement made by the repository, and it is the only authenticated one we
  can get without human eyes on the PDF. `submittedVersion` is not a weaker journal version. It is
  NOT THE JOURNAL VERSION. It is the thing we already hold and already cannot cite.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path('/home/polaris/wt/flywheel')
CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'
CARDS = ROOT / 'outputs' / 'evidence_cards_v2.json'
OUT = ROOT / 'outputs' / 'version_alignment.json'
CACHE = ROOT / 'cache' / 'version_align'
CACHE.mkdir(parents=True, exist_ok=True)

MAILTO = 'aldrin.or@c-polarbiotech.com'
UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}

_LAST = [0.0]
SPACING = 1.1


def nz(s: str) -> str:
    """Whitespace-normalised view. A PDF line break is not a textual difference; it is a rendering
    artifact of the column width. Everything else -- every character, every digit -- must match."""
    return re.sub(r'\s+', ' ', s or '').strip()


def polite(url: str, tries: int = 4, timeout: int = 30) -> tuple[str, object]:
    """(outcome, payload). outcome in {OK, HTTP_404, BACKEND_FAILED}.

    WE ARE THE ONES WHO GOT OURSELVES THROTTLED. 1.1s spacing, always; exponential backoff on 429/503;
    and if we exhaust the retries we say BACKEND_FAILED -- never, ever, "there is no copy".
    """
    for a in range(tries):
        wait = _LAST[0] + SPACING - time.time()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return 'OK', r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 502, 504):
                time.sleep(3 * (2 ** a))
                continue
            if e.code == 404:
                return 'HTTP_404', None          # the backend ANSWERED: it does not know this DOI
            return 'BACKEND_FAILED', f'HTTP {e.code}'
        except Exception as e:
            time.sleep(1.5 * (2 ** a))
            last = f'{type(e).__name__}'
    return 'BACKEND_FAILED', 'retries exhausted'


def pget(url: str) -> tuple[str, object]:
    o, raw = polite(url)
    if o != 'OK':
        return o, raw
    try:
        return 'OK', json.loads(raw)
    except Exception:
        return 'BACKEND_FAILED', 'unparseable JSON'


def fetch_doc(url: str) -> tuple[str, str]:
    """(outcome, text). Cached on disk by URL hash so a re-run costs the network NOTHING."""
    key = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:20] + '.txt')
    if key.exists():
        return 'OK', key.read_text()
    o, raw = polite(url, timeout=60)
    if o != 'OK':
        return o, ''
    txt = ''
    if raw[:4] == b'%PDF':
        try:
            from pdfminer.high_level import extract_text
            txt = extract_text(io.BytesIO(raw)) or ''
        except Exception as e:
            return 'PDF_UNPARSEABLE', ''
    else:
        html = raw.decode('utf-8', 'ignore')
        html = re.sub(r'(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html)
        txt = re.sub(r'\s{2,}', ' ', re.sub(r'&[a-z]+;', ' ', re.sub(r'<[^>]+>', ' ', html))).strip()
    key.write_text(txt)
    return 'OK', txt


# =====================================================================================================
# LOCATING A JOURNAL VERSION — and being honest about whether we actually asked
# =====================================================================================================

def unpaywall(doi: str) -> dict:
    o, d = pget(f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}')
    if o != 'OK':
        return dict(backend='unpaywall', outcome=o, locations=[])
    locs = []
    for L in (d.get('oa_locations') or []):
        locs.append(dict(
            version=L.get('version'), host_type=L.get('host_type'),
            url=L.get('url_for_pdf') or L.get('url'),
            license=L.get('license'), repo=L.get('repository_institution'),
        ))
    return dict(backend='unpaywall', outcome='OK', is_oa=d.get('is_oa'),
                oa_status=d.get('oa_status'), journal=d.get('journal_name'), locations=locs)


def openalex(doi: str) -> dict:
    o, d = pget(f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}')
    if o != 'OK':
        return dict(backend='openalex', outcome=o, locations=[])
    locs = []
    for L in (d.get('locations') or []):
        locs.append(dict(
            version=L.get('version'), is_oa=L.get('is_oa'),
            url=L.get('pdf_url') or L.get('landing_page_url'),
            host=(L.get('source') or {}).get('display_name'),
            host_type=(L.get('source') or {}).get('type'),
        ))
    return dict(backend='openalex', outcome='OK', is_oa=(d.get('open_access') or {}).get('is_oa'),
                locations=locs)


JOURNAL_VERSIONS = {'publishedVersion': 'exact_copy_of',
                    'acceptedVersion': 'accepted_manuscript_of'}


def candidate_journal_locations(up: dict, oa: dict) -> list[dict]:
    """OA locations that CLAIM to be the published article or the post-review accepted manuscript.

    `submittedVersion` is EXCLUDED and that exclusion is the whole point of this function: the
    submitted version IS the working paper. It is what we already hold. Re-fetching it and calling
    it an alignment would be manufacturing the exact fiction we are here to destroy.
    """
    out = []
    for src, rec in (('unpaywall', up), ('openalex', oa)):
        if rec.get('outcome') != 'OK':
            continue
        for L in rec.get('locations') or []:
            v = L.get('version')
            if v not in JOURNAL_VERSIONS:
                continue
            if src == 'openalex' and not L.get('is_oa'):
                continue                     # OpenAlex lists the paywalled publisher row too
            if not L.get('url'):
                continue
            out.append(dict(via=src, version=v, edge=JOURNAL_VERSIONS[v], url=L['url'],
                            host=L.get('host') or L.get('host_type') or L.get('repo')))
    # de-duplicate on URL, preferring publishedVersion
    seen, ded = set(), []
    for L in sorted(out, key=lambda x: x['version'] != 'publishedVersion'):
        if L['url'] in seen:
            continue
        seen.add(L['url'])
        ded.append(L)
    return ded


# =====================================================================================================
# THE VERIFICATION — the only thing that can make a span journal-attributable
# =====================================================================================================

def verify_spans(spans: list[str], journal_text: str) -> dict:
    """Each span must appear VERBATIM (whitespace-normalised) in the journal version's bytes.

    A span that does not appear is NOT a bug to be tuned away. It is the finding: peer review changed
    it, or the table was rebuilt, or the number moved. It STAYS INADMISSIBLE.
    """
    jt = nz(journal_text)
    hit, missraw = [], []
    for s in spans:
        (hit if nz(s) and nz(s) in jt else missraw).append(s)
    return dict(verified=hit, unverified=missraw,
                n_verified=len(hit), n_unverified=len(missraw))


def main() -> int:
    corpus = json.loads(CORPUS.read_text())
    cards = json.loads(CARDS.read_text())
    only = sys.argv[1:] or None

    spans_by_doi: dict[str, list[str]] = {}
    for c in cards:
        spans_by_doi.setdefault(c['doi'], []).append(c.get('span') or '')

    # Targets: every row whose BYTES are not already the journal article and that we might cite.
    # Derived by re-reading the bytes -- NOT by trusting `fulltext_source`, which wp_fetch hardcodes.
    sys.path.insert(0, str(ROOT / 'scripts'))
    from provenance import derive_expression_kind, profile, Work

    results = []
    for i, r in enumerate(corpus):
        ft = r.get('fulltext') or ''
        if not ft.strip():
            continue
        doi = r.get('doi') or ''
        if only and doi not in only:
            continue
        w = Work(id='w', title=r.get('title') or '', authors=r.get('authors') or [],
                 year=r.get('year'), venue=r.get('venue') or '', doi=doi)
        prof = profile(ft, w, r.get('abstract') or '')
        ekind, ebasis = derive_expression_kind(ft)
        ncards = len(spans_by_doi.get(doi, []))

        rec = dict(idx=i, doi=doi, title=r.get('title'), venue=r.get('venue'), year=r.get('year'),
                   held_words=len(ft.split()), n_cards=ncards,
                   wp_fetch_tag=r.get('fulltext_source') or None,
                   corpus_status=r.get('content_status'),
                   held_artifact_kind=prof['artifact_kind'],
                   held_kind_basis=prof['artifact_kind_basis'],
                   held_expression_kind=ekind, held_expression_basis=ebasis,
                   extractability=prof['extractability']['verdict'],
                   identity=prof['identity']['verdict'])

        # Only rows whose held bytes are NOT the journal article need alignment.
        if prof['artifact_kind'] == 'journal_article':
            rec['alignment'] = 'NOT_NEEDED'
            rec['alignment_note'] = 'the bytes we hold ARE the typeset journal article'
            results.append(rec)
            continue
        if prof['artifact_kind'] == 'wrong_work':
            rec['alignment'] = 'IMPOSSIBLE_WRONG_WORK'
            rec['alignment_note'] = ('these bytes are a DIFFERENT WORK. There is nothing to align. '
                                     'The text must be removed from this row.')
            results.append(rec)
            continue

        up = unpaywall(doi)
        oa = openalex(doi)
        rec['unpaywall_outcome'] = up.get('outcome')
        rec['openalex_outcome'] = oa.get('outcome')
        rec['unpaywall_locations'] = up.get('locations')
        rec['openalex_locations'] = oa.get('locations')

        if up.get('outcome') != 'OK' and oa.get('outcome') != 'OK':
            # WE could not ask. This says NOTHING about whether a copy exists.
            rec['alignment'] = 'BACKEND_FAILED'
            rec['alignment_note'] = (f"unpaywall={up.get('outcome')} openalex={oa.get('outcome')} — "
                                     f"we could not ask. This is a fact about OUR REQUEST, not about "
                                     f"the availability of a journal version.")
            results.append(rec)
            continue

        cands = candidate_journal_locations(up, oa)
        rec['journal_version_candidates'] = cands

        if not cands:
            rec['alignment'] = 'NO_JOURNAL_BYTES'
            rec['alignment_note'] = (
                'both backends answered, and NEITHER lists an OA publishedVersion or acceptedVersion. '
                'The only OA copy is the submitted/working version we already hold. '
                'DISCOVERY LEAD ONLY — every span stays inadmissible for a journal-only answer.')
            rec['spans_verified'] = 0
            rec['spans_inadmissible'] = ncards
            results.append(rec)
            continue

        # We have a candidate. Go and get the bytes and TEST THE SPANS.
        best = None
        for c in cands:
            o, txt = fetch_doc(c['url'])
            got = dict(**c, fetch_outcome=o, words=len(txt.split()))
            if o != 'OK' or len(txt.split()) < 1200:
                got['usable'] = False
                got['why'] = (f'fetch={o}' if o != 'OK'
                              else f'{len(txt.split())} words — a stub, not the article')
                rec.setdefault('fetch_attempts', []).append(got)
                continue
            got['usable'] = True
            rec.setdefault('fetch_attempts', []).append(got)
            best = (c, txt)
            break

        if not best:
            rec['alignment'] = 'JOURNAL_BYTES_UNREACHABLE'
            rec['alignment_note'] = ('a journal version is LISTED but we could not retrieve usable '
                                     'bytes for it. Spans stay inadmissible until we can.')
            rec['spans_verified'] = 0
            rec['spans_inadmissible'] = ncards
            results.append(rec)
            continue

        cand, jtext = best
        jw = Work(id='w', title=r.get('title') or '', authors=r.get('authors') or [],
                  year=r.get('year'), venue=r.get('venue') or '', doi=doi)
        jprof = profile(jtext, jw, r.get('abstract') or '')
        rec['journal_bytes'] = dict(url=cand['url'], via=cand['via'], version=cand['version'],
                                    words=len(jtext.split()),
                                    artifact_kind=jprof['artifact_kind'],
                                    kind_basis=jprof['artifact_kind_basis'],
                                    identity=jprof['identity']['verdict'],
                                    sha256=hashlib.sha256(jtext.encode()).hexdigest())

        # The repository SAYS publishedVersion. Do the bytes agree? Re-derive; never trust the label.
        if jprof['identity']['verdict'] == 'CONTRADICTED':
            rec['alignment'] = 'JOURNAL_BYTES_WRONG_WORK'
            rec['alignment_note'] = (f"the location labelled {cand['version']} returned a DIFFERENT "
                                     f"WORK: {jprof['identity']['basis']}")
            rec['spans_verified'] = 0
            rec['spans_inadmissible'] = ncards
            results.append(rec)
            continue

        v = verify_spans(spans_by_doi.get(doi, []), jtext)
        rec['spans_verified'] = v['n_verified']
        rec['spans_inadmissible'] = v['n_unverified']
        rec['unverified_examples'] = [s[:160] for s in v['unverified'][:5]]
        if ncards == 0:
            rec['alignment'] = 'JOURNAL_BYTES_HELD_NO_SPANS'
            rec['alignment_note'] = ('we now hold the journal version, but this row mined no spans. '
                                     'The row is re-minable AGAINST THE JOURNAL BYTES.')
        elif v['n_verified'] and not v['n_unverified']:
            rec['alignment'] = 'ALIGNED_FULL'
            rec['alignment_note'] = (f"all {v['n_verified']} spans appear VERBATIM in the "
                                     f"{cand['version']}. Edge {cand['edge']} may be ASSERTED.")
        elif v['n_verified']:
            rec['alignment'] = 'ALIGNED_PARTIAL'
            rec['alignment_note'] = (
                f"{v['n_verified']} of {ncards} spans appear verbatim in the {cand['version']}; "
                f"{v['n_unverified']} DO NOT and stay inadmissible. Per-span, never per-paper.")
        else:
            rec['alignment'] = 'NOT_ALIGNED'
            rec['alignment_note'] = (
                f"we HOLD the {cand['version']} and NOT ONE of the {ncards} mined spans appears in "
                f"it. This is the risk Sol named, observed: the working paper's text is not the "
                f"journal's text.")
        results.append(rec)

    OUT.write_text(json.dumps(results, indent=1))
    print(f'wrote {OUT}  ({len(results)} rows)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
