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
      acceptedVersion    post-peer-review author manuscript   -> accepted_manuscript_of (TRANSFERS NOTHING)
      submittedVersion   the PREPRINT / WORKING PAPER         -> predecessor_of   (TRANSFERS NOTHING)
  That field is a version statement made by the repository, and it is the only authenticated one we
  can get without human eyes on the PDF. `submittedVersion` is not a weaker journal version. It is
  NOT THE JOURNAL VERSION. It is the thing we already hold and already cannot cite.

WHAT CHANGED IN V9, AND WHY IT WAS A P0

  `acceptedVersion` used to map to a SPAN-PRESERVING edge. So this file's most innocuous-looking line —
  a two-entry dict — was hop one of a path that ended with a repository's eleven-character string
  authorising a manuscript's numbers to be printed under a journal masthead:

      Unpaywall says   version: "acceptedVersion"
          -> version_align maps it to     accepted_manuscript_of
          -> provenance lists that in     SPAN_PRESERVING
          -> alignment_census rules it    ADMISSIBLE
          -> a span from the manuscript   prints as a finding of the journal

  No component lied. Each one passed on what it was given. Sol, V9 §4: "An accepted manuscript is NEVER
  the journal version merely because a repository says acceptedVersion." Acceptance is not publication:
  copy-editing, proofs and the editor's last round all land after it, and THE NUMBERS MOVE — 0.37pp in
  Acemoglu & Restrepo's NBER working paper, 0.2pp in the published JPE.

  An accepted manuscript is now attributable AS AN ACCEPTED MANUSCRIPT and as nothing else. A span in it
  reaches the journal only across a verified SpanCorrespondence: THAT span, both hashes, both offsets,
  exact canonical equality — and it carries THAT SPAN ONLY, never the paragraph beside it.
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

sys.path.insert(0, str(ROOT / 'scripts'))
from acquisition import (  # noqa: E402
    MAILTO, Acquirer, BlobStore, content_host, extract_text as _extract, open_ledger,
)

UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}

#: The two backends we ask whether an OA JOURNAL version exists. Named before the loop walks them.
ADAPTERS = ('unpaywall', 'openalex')

#: THE ONE DURABLE LEDGER + the acquirer. Set in main(); the module-level default lets the helpers be
#: imported and called in isolation without silently writing to the production log.
ACQ: Acquirer | None = None


def _acq() -> Acquirer:
    global ACQ
    if ACQ is None:
        ACQ = Acquirer('version_align', ledger=open_ledger(), blobs=BlobStore())
    return ACQ


def nz(s: str) -> str:
    """Whitespace-normalised view. A PDF line break is not a textual difference; it is a rendering
    artifact of the column width. Everything else -- every character, every digit -- must match."""
    return re.sub(r'\s+', ' ', s or '').strip()


def polite(unit: str, adapter: str, url: str, tries: int = 4,
           timeout: int = 30) -> tuple[str, object]:
    """(outcome, payload). outcome in {OK, HTTP_404, BACKEND_FAILED}.

    WE ARE THE ONES WHO GOT OURSELVES THROTTLED. 1.1s spacing, always; exponential backoff on 429/503;
    and if we exhaust the retries we say BACKEND_FAILED -- never, ever, "there is no copy".

    This function ALREADY returned a typed outcome, which made it the most honest of the four
    fetchers — and it was still not enough, because the outcome LIVED ONLY IN A LOCAL VARIABLE. It was
    written into `version_alignment.json` as a string, in a field a later component could overwrite,
    and NOTHING COULD REDUCE OVER IT. Now the observation goes to the durable ledger at the exception
    boundary — BACKEND_ATTEMPTED, then exactly one of RESPONSE_RECEIVED | THROTTLED | BLOCKED — and the
    typed return below is a CONVENIENCE FOR THIS FILE'S CONTROL FLOW, not the record of what happened.
    """
    r = _acq().get(unit, adapter, url, tries=tries, timeout=timeout)
    if r.ok:
        return 'OK', r.raw
    if r.outcome == 'NOT_INDEXED':
        return 'HTTP_404', None              # the backend ANSWERED: it does not know this DOI
    # THROTTLED / BLOCKED / timeout. All of it is on the ledger with its status code. None of it is
    # "there is no copy", and this file has never been allowed to say that.
    return 'BACKEND_FAILED', f'{r.outcome} {r.transport_error}'.strip()


def pget(unit: str, adapter: str, url: str) -> tuple[str, object]:
    o, raw = polite(unit, adapter, url)
    if o != 'OK':
        return o, raw
    try:
        return 'OK', json.loads(raw)
    except Exception:
        return 'BACKEND_FAILED', 'unparseable JSON'


def fetch_doc(unit: str, url: str, requested: dict | None = None) -> tuple[str, str]:
    """(outcome, text). Cached on disk by URL hash so a re-run costs the network NOTHING.

    These are THE JOURNAL VERSION'S BYTES — the only thing in the world that can make a working-paper
    span journal-attributable. So they are recorded as a MANIFESTATION like any other bytes: blob id,
    byte hash, locator, and the identity we asked for. An alignment that cannot name the bytes it
    aligned against is not an alignment.
    """
    requested = requested or {}
    acq = _acq()
    adapter = content_host(url)
    key = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:20] + '.txt')

    if key.exists():
        txt = key.read_text()
        # No network request happened, so NO BACKEND_ATTEMPTED is emitted — we did not attempt a
        # backend. But we DO hold the bytes, and a manifestation is a fact about what we hold.
        acq.record_manifestation(
            unit, locator=url, raw=txt.encode('utf-8'), text=txt, adapter=adapter,
            requested_title=requested.get('title') or '',
            requested_authors=list(requested.get('authors') or []),
            requested_doi=requested.get('doi') or '',
            requested_venue=requested.get('venue') or '',
            requested_year=requested.get('year'),
            source_type=str(requested.get('type') or 'journal-article'),
            extraction_method='disk_cache', from_cache=True)
        return 'OK', txt

    r = acq.get(unit, adapter, url, timeout=60)
    if not r.ok:
        return ('HTTP_404' if r.outcome == 'NOT_INDEXED' else 'BACKEND_FAILED'), ''

    txt, method = _extract(r.raw, r.content_type)
    if not txt and method.startswith('pdf_unparseable'):
        # WE HOLD BYTES WE CANNOT READ. That is not "no journal version exists" — it is an extraction
        # failure, and the two must never share a label. The bytes are kept.
        acq.record_manifestation(
            unit, locator=url, raw=r.raw, text='', adapter=adapter,
            requested_title=requested.get('title') or '',
            requested_authors=list(requested.get('authors') or []),
            requested_doi=requested.get('doi') or '',
            requested_venue=requested.get('venue') or '',
            requested_year=requested.get('year'),
            extraction_method=method, http_status=r.http_status, content_type=r.content_type)
        return 'PDF_UNPARSEABLE', ''

    acq.record_manifestation(
        unit, locator=url, raw=r.raw, text=txt, adapter=adapter,
        requested_title=requested.get('title') or '',
        requested_authors=list(requested.get('authors') or []),
        requested_doi=requested.get('doi') or '',
        requested_venue=requested.get('venue') or '',
        requested_year=requested.get('year'),
        source_type=str(requested.get('type') or 'journal-article'),
        extraction_method=method, http_status=r.http_status, content_type=r.content_type)
    key.write_text(txt)
    return 'OK', txt


# =====================================================================================================
# LOCATING A JOURNAL VERSION — and being honest about whether we actually asked
# =====================================================================================================

def unpaywall(unit: str, doi: str) -> dict:
    o, d = pget(unit, 'unpaywall',
                f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}')
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


def openalex(unit: str, doi: str) -> dict:
    o, d = pget(unit, 'openalex',
                f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}')
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


#: A REPOSITORY'S VERSION LABEL -> THE EDGE IT COULD AT MOST SUPPORT. It is not an edge we may ASSERT,
#: and — since V9 — for `acceptedVersion` it is not even a span-preserving one.
#:
#: THIS DICT WAS THE FIRST HOP OF A LIVE FABRICATION PATH. It read:
#:
#:     JOURNAL_VERSIONS = {'publishedVersion': 'exact_copy_of',
#:                         'acceptedVersion':  'accepted_manuscript_of'}   # <- span-preserving
#:
#: `accepted_manuscript_of` was in provenance.SPAN_PRESERVING, so an Unpaywall record whose `version`
#: field held the eleven characters `acceptedVersion` was, three hops later, licence to print that
#: manuscript's numbers under the journal's name. A repository's one-word opinion, laundered into a
#: claim about bytes.
#:
#: Sol V9, verbatim: "An accepted manuscript is NEVER the journal version merely because a repository
#: says acceptedVersion." The mapping stays — the label is real EVIDENCE and worth fetching on — but what
#: it maps to is now inert, and the assertion below makes that structural rather than remembered.
JOURNAL_VERSIONS = {'publishedVersion': 'exact_copy_of',
                    'acceptedVersion': 'accepted_manuscript_of'}

sys.path.insert(0, str(ROOT / 'scripts'))
from provenance import SPAN_PRESERVING as _SPAN_PRESERVING  # noqa: E402

#: WHICH OF THOSE EDGES ACTUALLY CARRIES A SPAN. Read from provenance — never restated here, because a
#: second list of "the span-preserving edges" is a second answer to the only question that matters, and
#: the one that ships is whichever module the reducer imported.
assert 'accepted_manuscript_of' not in _SPAN_PRESERVING, (
    'accepted_manuscript_of is span-preserving again. THAT IS THE V9 P0 REOPENED: a repository label '
    'would once more be sufficient to print a manuscript under a journal masthead.')


def span_preserving(version_label: str) -> bool:
    """Does a location carrying THIS repository label license a span to name the journal article?

    Only `publishedVersion` — and even then only after the BYTES are fetched, profiled, and found to be
    the article of record. This function reports what the LABEL could support. It never concludes.
    """
    return JOURNAL_VERSIONS.get(version_label) in _SPAN_PRESERVING


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

        # ── ROUTE_PLANNED, before the adapter loop. ───────────────────────────────────────────────
        # `route_complete` will mean BOTH of these have a terminal outcome record. It is what licenses
        # the NO_JOURNAL_BYTES branch below to say "both backends answered, and NEITHER lists an OA
        # published version" — a scoped absence, and the ONLY state that can support one.
        acq = _acq()
        acq.plan_route(doi, ADAPTERS, requested_title=r.get('title') or '', doi=doi,
                       requested_venue=r.get('venue') or '', requested_year=r.get('year'),
                       requested_authors=list(r.get('authors') or []),
                       source_type=str(r.get('type') or 'journal-article'))

        up = unpaywall(doi, doi)
        oa = openalex(doi, doi)
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
        want = dict(title=r.get('title') or '', authors=r.get('authors') or [], doi=doi,
                    venue=r.get('venue') or '', year=r.get('year'),
                    type=r.get('type') or 'journal-article')
        for c in cands:
            o, txt = fetch_doc(doi, c['url'], want)
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
            rec['alignment_note'] = (
                f"all {v['n_verified']} spans appear VERBATIM in the {cand['version']}. "
                + (f"Edge {cand['edge']} may be ASSERTED (subject to provenance.exact_copy_failure: we "
                   f"must HOLD both documents and their ENTIRE canonical texts must be equal)."
                   if span_preserving(cand['version']) else
                   f"THE {cand['version']} IS NOT THE JOURNAL VERSION. `{cand['edge']}` is not "
                   f"span-preserving (V9 §4), so this licenses NOTHING wholesale. Each verified span "
                   f"gets a SpanCorrespondence — that span, those two hashes, those two offsets, exact "
                   f"canonical equality — and each grants THAT SPAN ONLY."))
        elif v['n_verified']:
            rec['alignment'] = 'ALIGNED_PARTIAL'
            rec['alignment_note'] = (
                f"{v['n_verified']} of {ncards} spans appear verbatim in the {cand['version']}; "
                f"{v['n_unverified']} DO NOT and stay inadmissible. Per-span, never per-paper."
                + ('' if span_preserving(cand['version']) else
                   f" And the {cand['version']} is not the journal version: even the verified spans name "
                   f"the accepted manuscript unless a SpanCorrespondence carries them into VoR bytes."))
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
