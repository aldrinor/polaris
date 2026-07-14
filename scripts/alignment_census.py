#!/usr/bin/env python3
"""THE ALIGNMENT CENSUS — which held bytes may name a journal article, and which may not.

Every label here is RE-DERIVED FROM THE BYTES. Three checks in this file exist because the first
version of it produced a confident, wrong answer, and its own audit caught it:

 1. THE CIRCULARITY GUARD.  My first pass reported three papers "ALIGNED — all spans verified in the
    publishedVersion". They were not aligned. Unpaywall's `publishedVersion` URL pointed at THE SAME
    SPRINGER PDF ALREADY IN THE CORPUS, and I had verified the text against itself. An alignment is
    only an alignment if the journal bytes are a DIFFERENT DOCUMENT from the bytes we hold, so the
    fetched text must now clear an 8-gram distinctness test before any span is counted.

 2. THE PUBLISHER-TYPESET TEST.  `_JOURNAL_MARK` in provenance.py matches a DOI string — but a DOI
    string is printed by every repository COVER SHEET, which cites the article rather than being it.
    The article of record is identified by furniture only a typesetter emits: the journal's name
    recurring as a RUNNING HEAD, and printed page FOLIOS after form-feeds, matching the bibliographic
    page range. That test, and not the metadata, is what proved the LSE deposit of Goos-Manning-
    Salomons really is the AER article (running heads "AMERICAN ECONOMIC REVIEW August 2014", folios
    2509-2526) -- against Unpaywall, which labels that same file `submittedVersion`.

 3. BACKEND_FAILED IS NEVER "NO COPY".  HTTP 403 from AEA and SAGE is a fact about our request.
    It is recorded as ACCESS_BLOCKED and it concludes NOTHING about what exists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path('/home/polaris/wt/flywheel')


def nz(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def shingles(t: str, k: int = 8) -> set:
    w = nz(t).lower().split()
    return {' '.join(w[i:i + k]) for i in range(0, max(0, len(w) - k), 3)}


def venue_running_head_pattern(venue: str):
    toks = re.findall(r'[A-Za-z]{3,}', re.sub(r'&amp;', '&', venue or ''))
    if not toks:
        return None
    return r'\b' + r'[\s\W]+(?:of|and|the|in|for)?[\s\W]*'.join(re.escape(t) for t in toks[:4]) + r'\b'


def typeset_profile(text: str, venue: str) -> dict:
    """Is this the PUBLISHER'S rendering? Only a typesetter emits running heads and printed folios."""
    p = venue_running_head_pattern(venue)
    return dict(
        running_heads=len(re.findall(p, text, re.I)) if p else 0,
        folios=len(re.findall(r'\x0c\s*\d{1,4}\b', text)),
        wp_series_marks=len(re.findall(
            r'(nber working paper|working paper (no|series)|discussion paper|this draft)',
            text[:6000], re.I)),
    )


def is_publisher_typeset(tp: dict) -> bool:
    # Both, together. A cover sheet can print the journal's name once; it cannot print the article's
    # page folios across a form-feed on every page.
    return tp['running_heads'] >= 3 and tp['folios'] >= 3


BYTE_ID: dict = {}


def main() -> int:
    global BYTE_ID
    p = Path('/tmp/byteid.json')
    BYTE_ID = {k: v for k, v in (json.loads(p.read_text()) if p.exists() else {}).items() if v}
    corpus = json.loads((ROOT / 'outputs' / 'journal_corpus_content.json').read_text())
    cards = json.loads((ROOT / 'outputs' / 'evidence_cards_v2.json').read_text())
    align = {r['idx']: r for r in json.loads((ROOT / 'outputs' / 'version_alignment.json').read_text())}

    ncards: dict[str, int] = {}
    for c in cards:
        ncards[c['doi']] = ncards.get(c['doi'], 0) + 1

    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from provenance import profile, Work

    out = []
    for i, r in enumerate(corpus):
        ft = r.get('fulltext') or ''
        if not ft.strip():
            continue
        doi = r.get('doi') or ''
        w = Work(id='w', title=r.get('title') or '', authors=r.get('authors') or [],
                 year=r.get('year'), venue=r.get('venue') or '', doi=doi)
        prof = profile(ft, w, r.get('abstract') or '')
        tp = typeset_profile(ft, r.get('venue') or '')
        a = align.get(i, {})
        n = ncards.get(doi, 0)

        # BYTE-IDENTITY against an authenticated version statement. This route CONVICTS as readily as
        # it acquits: Bresnahan's held bytes are 0.999-identical to UPenn's `submittedVersion`, which
        # is how we know the QJE row holds the working paper.
        bid = BYTE_ID.get(str(i)) or BYTE_ID.get(i)
        bid_ver = (bid or {}).get('version')

        # An OA-NATIVE journal article (PLOS, JAIR, BMC, PMC, ScienceDirect) has no form-feed folios
        # to count -- the folio test is a PDF test and simply cannot see them. Their article-of-record
        # furniture is a header block: a volume/page range, a received/accepted date line, an
        # "OPEN ACCESS"/"RESEARCH ARTICLE" stamp, or the publisher's masthead.
        oa_native = re.search(
            r'(research article|open access|contents lists available at sciencedirect'
            r'|received .{0,60}accepted|\(\d{4}\) *\d+:\d+|\b\d+ *\(\d{4}\) *\d+[-–]\d+)', ft[:3000], re.I)
        # A preprint says which journal it is FOR. That is not the journal's rendering of it.
        preprint = re.search(r'\bfor [A-Z][a-z]+ and [A-Z][a-z]+\s*$|submitted to\b', ft[:3000], re.M)

        # ---- THE RULING. Derived, in the order of what the bytes can prove. --------------------
        if prof['identity']['verdict'] == 'CONTRADICTED':
            kind, ruling = 'WRONG_WORK', 'PURGE'
            why = 'these bytes are a different work by a different author — nothing to align'
        elif prof['artifact_kind'] == 'landing_page':
            kind, ruling = 'LANDING_PAGE', 'NO_EVIDENCE'
            why = 'a web page about the document, not the document'
        elif prof['extractability']['verdict'] == 'CORRUPT':
            kind, ruling = 'EXTRACTION_FAILURE', 'NO_EVIDENCE'
            why = 'bytes are not readable prose'
        elif bid_ver == 'submittedVersion':
            kind, ruling = 'WORKING_PAPER', 'INADMISSIBLE'
            why = (f"held bytes are {bid['cover']:.3f}-identical to a location an authenticated backend "
                   f"labels `submittedVersion` ({bid['host']}) — this IS the working paper")
        elif tp['wp_series_marks'] >= 1 and not is_publisher_typeset(tp):
            kind, ruling = 'WORKING_PAPER', 'INADMISSIBLE'
            why = 'the bytes self-declare a working-paper series and carry no publisher typeset furniture'
        elif is_publisher_typeset(tp):
            kind, ruling = 'JOURNAL_ARTICLE', 'ADMISSIBLE'
            why = (f"publisher typeset furniture: {tp['running_heads']} running heads of the journal's "
                   f"name, {tp['folios']} printed page folios — only a typesetter emits these")
        elif bid_ver == 'publishedVersion':
            kind, ruling = 'JOURNAL_ARTICLE', 'ADMISSIBLE'
            why = (f"held bytes are {bid['cover']:.3f}-identical to a location an authenticated backend "
                   f"labels `publishedVersion` — these ARE the article of record")
        elif (a.get('journal_bytes') or {}).get('version') == 'acceptedVersion':
            # ── THE V9 P0, AT ITS LAST HOP ────────────────────────────────────────────────────────
            # This branch used to read `ruling = 'ADMISSIBLE'`, on the basis that
            # "accepted_manuscript_of is span-preserving". It was, and it should never have been.
            #
            # Read what the condition actually tests: a field in a JSON record that came from Unpaywall,
            # whose value is the string 'acceptedVersion'. NOT ONE BYTE OF THE DOCUMENT IS CONSULTED.
            # A repository's one-word opinion — self-reported by the depositing author, frequently stale,
            # never audited — was the whole evidence for printing a manuscript's numbers as a journal's
            # findings. Every other branch in this ruling ladder reads the BYTES: running heads, printed
            # folios, cover-sheet furniture, an 8-gram distinctness test. This one read a label.
            #
            # Sol V9 §4: "An accepted manuscript is NEVER the journal version merely because a repository
            # says acceptedVersion." Acceptance precedes copy-editing, proofs and the editor's last
            # round, and THE NUMBERS MOVE ACROSS THEM (0.37pp -> 0.2pp, Acemoglu & Restrepo).
            #
            # An accepted manuscript is now attributable AS AN ACCEPTED MANUSCRIPT and as nothing else.
            # Under a JOURNAL-ONLY contract that means INADMISSIBLE — and it is not a downgrade of the
            # evidence, it is the correct name for it. A span in it reaches the journal only across a
            # verified SpanCorrespondence (provenance.SpanCorrespondence): that span, both hashes, both
            # offsets, exact canonical equality, and THAT SPAN ONLY.
            kind, ruling = 'ACCEPTED_MANUSCRIPT', 'INADMISSIBLE'
            why = ('a repository VERSION LABEL (`acceptedVersion`, via Unpaywall) — a string, not bytes. '
                   'An accepted manuscript is NOT the journal version: peer review is not the last thing '
                   'that changes a number. Attributable as an accepted manuscript ONLY; a span reaches '
                   'the journal only across a verified per-span SpanCorrespondence into VoR bytes')
        elif preprint and not oa_native:
            kind, ruling = 'PREPRINT', 'INADMISSIBLE'
            why = 'the bytes say which journal they are FOR — an author preprint, not the journal’s text'
        elif oa_native and tp['wp_series_marks'] == 0:
            kind, ruling = 'JOURNAL_ARTICLE', 'ADMISSIBLE'
            why = (f"open-access article-of-record header block ({oa_native.group(0)[:40]!r}) and no "
                   f"working-paper furniture anywhere in the front matter")
        else:
            kind, ruling = 'UNDETERMINED_VERSION', 'INADMISSIBLE'
            why = ('no publisher typeset furniture and no authenticated version statement — we cannot '
                   'show these bytes are the article of record')

        out.append(dict(
            idx=i, doi=doi, title=r.get('title'), venue=r.get('venue'), year=r.get('year'),
            authors=r.get('authors'), held_words=len(ft.split()), cards=n,
            wp_fetch_tag=r.get('fulltext_source'), corpus_status=r.get('content_status'),
            held_kind=kind, ruling=ruling, why=why, typeset=tp,
            journal_version_reachable=a.get('alignment'),
            backend=dict(unpaywall=a.get('unpaywall_outcome'), openalex=a.get('openalex_outcome')),
        ))

    (ROOT / 'outputs' / 'alignment_census.json').write_text(json.dumps(out, indent=1))

    adm = [r for r in out if r['ruling'] == 'ADMISSIBLE']
    bad = [r for r in out if r['ruling'] == 'INADMISSIBLE']
    print(f"{'idx':>3} {'cards':>5}  {'held_kind':21s} {'ruling':13s} {'venue':30s} {'doi'}")
    print('-' * 128)
    for r in sorted(out, key=lambda x: (x['ruling'] != 'INADMISSIBLE', -x['cards'])):
        print(f"{r['idx']:>3} {r['cards']:>5}  {r['held_kind']:21s} {r['ruling']:13s} "
              f"{str(r['venue'])[:30]:30s} {r['doi']}")
    print()
    print(f"  cards on ADMISSIBLE bytes   : {sum(r['cards'] for r in adm):>4}")
    print(f"  cards on INADMISSIBLE bytes : {sum(r['cards'] for r in bad):>4}  <-- must not reach the page")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
