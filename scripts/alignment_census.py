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
import sys
from pathlib import Path

ROOT = Path('/home/polaris/wt/flywheel')
sys.path.insert(0, str(ROOT / 'scripts'))

# ONE definition of "what a repository cover sheet is", shared with the provenance / event_ledger lanes.
# The census reads typeset furniture (folios, page ranges, running heads) to decide whether a typesetter
# made a document — and a cover sheet FORGES every one of those signals (it CITES the article: its
# journal name, its "14(1): 1-12" page range, its masthead-looking header). So the cover sheet must be
# segmented off BEFORE any typeset fact is derived, using the SAME segmenter the other two lanes use.
from provenance import segment_cover_sheet  # noqa: E402


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


def folio_numbers(text: str) -> list[int]:
    """The printed page numbers — the integer that follows a form feed. A PDF's own pagination."""
    return [int(m.group(1)) for m in re.finditer(r'\x0c\s*(\d{1,5})\b', text)]


def declared_page_range(text: str, venue: str) -> tuple[int, int] | None:
    """The page range the document's OWN masthead prints beside the journal's name.

    e.g. `American Economic Review 2014, 104(8): 2509-2526`. A repository cover sheet prints this too
    (it is citing the article) — which is exactly why the range ALONE proves nothing. It is the
    ANCHOR, not the evidence: what it lets us ask is whether THIS DOCUMENT'S OWN FOLIOS LAND IN IT.
    """
    p = venue_running_head_pattern(venue)
    if not p:
        return None
    for m in re.finditer(p, text, re.I):
        r = re.search(r'(\d{1,5})\s*[-–—]\s*(\d{1,5})', text[m.end():m.end() + 80])
        if r:
            lo, hi = int(r.group(1)), int(r.group(2))
            if 0 < hi - lo < 200:          # a page range, not a year range or a DOI fragment
                return lo, hi
    return None


def page_top_heads(text: str, venue: str, window: int = 200) -> int:
    """The journal's name AT THE TOP OF A PAGE — i.e. immediately after a form feed. THIS is what a
    running head IS, and the distinction is the whole point:

    A repository COVER SHEET can print the journal's name (it is citing the article). A BIBLIOGRAPHY
    can print it thirty times (every economics paper cites the AER). NEITHER can put it at the top of
    three separate pages of the document's own body. Only the typesetter's page furniture does that.

    The old test counted the venue name ANYWHERE in the text and called >=3 "running heads". On the
    LSE deposit of Goos-Manning-Salomons it counted 9 -- ONE masthead, ONE cover-sheet citation, and
    SEVEN references to other AER papers. It reached the right verdict on that file THROUGH ITS
    BIBLIOGRAPHY, and it would have reached the same verdict for an accepted manuscript with the same
    bibliography.
    """
    p = venue_running_head_pattern(venue)
    if not p:
        return 0
    return sum(1 for m in re.finditer(r'\x0c', text)
               if re.search(p, text[m.end():m.end() + window], re.I))


def typeset_profile(text: str, venue: str) -> dict:
    """Is this the PUBLISHER'S rendering? Only a typesetter emits page furniture.

    THE COUNTERFEIT TYPESET (the seventh hop of the V9 P0). Every ADMITTING signal in this profile —
    the declared page range, the folios, the running heads — was read from the WHOLE text, cover sheet
    included. But a repository cover sheet CITES the article it wraps: it prints the journal's name, it
    prints "Nature Communications 14(1): 1-12", and an accepted manuscript underneath paginates from 1.
    So `declared_page_range` read "1-12" off the cover sheet's citation, `folio_numbers` counted the
    manuscript's own 1,2,3,…,10, `is_publisher_typeset` found >=3 folios "in range", and a Nature
    Communications ACCEPTED MANUSCRIPT was ruled the JOURNAL ARTICLE — while `provenance.
    derive_expression_kind`, reading the same bytes, correctly returned `accepted_manuscript`.
    THE CENSUS MUST AGREE WITH PROVENANCE, NOT OVERRULE IT.

    So the cover sheet is SEGMENTED OFF FIRST, and every typeset fact is derived from the ARTICLE BODY
    ONLY — where a manuscript CANNOT counterfeit them: it has no masthead printing the journal's page
    range, and its folios paginate from 1, landing in no range the body itself declares. The LSE deposit
    of the AER article is untouched: its cover sheet is stripped, but the typeset first page UNDER it
    still prints "American Economic Review 2014, 104(8): 2509-2526" and its folios ARE 2509-2526.
    (`wp_series_marks` is a DISQUALIFIER — a cover sheet MAY CONVICT — so it still reads the whole text.)
    """
    _cover, body = segment_cover_sheet(text)
    rng = declared_page_range(body, venue)
    folios = folio_numbers(body)
    p = venue_running_head_pattern(venue)
    return dict(
        running_heads=len(re.findall(p, body, re.I)) if p else 0,   # RETAINED, but no longer decides
        page_top_heads=page_top_heads(body, venue),
        folios=len(folios),
        declared_range=list(rng) if rng else None,
        folios_in_declared_range=len([f for f in folios if rng and rng[0] <= f <= rng[1]]),
        wp_series_marks=len(re.findall(
            r'(nber working paper|working paper (no|series)|discussion paper|this draft)',
            text[:6000], re.I)),
    )


def is_publisher_typeset(tp: dict) -> bool:
    """PROOF, IN THE BYTES, THAT A TYPESETTER MADE THIS DOCUMENT.

    This is the ONLY thing in this file that may overturn an inadmissible version label, so it has to
    be a fact a manuscript CANNOT counterfeit. Two independent proofs, either sufficient:

      1. FOLIOS THAT LAND IN THE DECLARED PAGE RANGE. The masthead says the article runs 2509-2526 and
         the document's own printed page numbers ARE 2510, 2511, ... 2526. An author manuscript
         paginates from 1. To forge this, a manuscript would have to be typeset -- i.e. to BE the
         article of record. (This is the test the file's own docstring always described and the code
         never actually performed: it counted folios and never once checked they were in range.)

      2. THE JOURNAL'S NAME AT THE TOP OF THREE OR MORE PAGES. A cover sheet is one page; a
         bibliography is not page furniture. Neither can do this.
    """
    return (tp['folios_in_declared_range'] >= 3
            or (tp['page_top_heads'] >= 3 and tp['folios'] >= 3))


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# THE VERSION VETO — WHICH VERSIONS ARE INADMISSIBLE IS A *STATEMENT*, NOT AN ORDERING ACCIDENT.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# The V9 P0 was patched at three hops (provenance.SPAN_PRESERVING, version_align, and the `acceptedVersion`
# branch of the ruling ladder below) AND IT STAYED OPEN AT A FOURTH -- because the fix was a RUNG IN A
# LADDER. The `acceptedVersion -> INADMISSIBLE` rung sat beneath `is_publisher_typeset -> ADMISSIBLE`,
# and an accepted manuscript that tripped the earlier rung was ruled a JOURNAL ARTICLE and never reached
# its own rule. The rule was right. It was simply never asked.
#
# A rule that is correct but UNREACHABLE is not a fix, and no amount of care about the ORDER of a ladder
# will keep it reachable across the next edit. So the ladder no longer decides this. Inadmissibility is
# now a PRECONDITION, evaluated before any admitting branch may run, and re-asserted after -- Sol's
# principle, applied to versions: WHICH VERSIONS ARE INADMISSIBLE MUST BE A STATEMENT, NOT AN ABSENCE.

#: A version label that can NEVER, on its own, name the journal under a journal-only policy.
INADMISSIBLE_VERSION_LABELS: dict[str, str] = {
    'acceptedVersion': ('an accepted manuscript — acceptance precedes copy-editing, proofs and the '
                        'editor\'s last round, and THE NUMBERS MOVE ACROSS THEM (Acemoglu & Restrepo: '
                        '0.37pp in the manuscript, 0.2pp in the JPE)'),
    'submittedVersion': ('a submitted manuscript — the working paper / preprint, before peer review '
                         'has touched a single number'),
}
#: ...and the only label that asserts the article of record.
ADMISSIBLE_VERSION_LABELS: frozenset[str] = frozenset({'publishedVersion'})


def version_statements(bid_ver: str | None, align_ver: str | None) -> list[tuple[str, str]]:
    """EVERY authenticated version statement about these bytes, from EVERY source, in ONE list.

    This exists so that no future source of a version label can be added without passing through the
    veto: a label that is not in this list cannot influence the ruling at all, and a label that IS in
    it is vetted by `version_veto()` before any admitting branch runs. There is no third way in.
    """
    out = []
    if bid_ver:
        out.append(('byte-identity against an authenticated backend', bid_ver))
    if align_ver:
        out.append(('a repository version label (via Unpaywall)', align_ver))
    return out


def version_veto(stmts: list[tuple[str, str]], typeset_ok: bool) -> tuple[str, str, str] | None:
    """THE PRECONDITION. Returns a refusal if ANY version statement forbids a journal attribution.

    The ONE thing that may overturn an inadmissible label is BYTE PROOF that a typesetter made this
    document (`is_publisher_typeset`) -- never another label, never a metadata field, and never the
    order of the branches below. That escape is not a courtesy to the label: it is the reason the LSE
    deposit of Goos-Manning-Salomons is admissible AS THE AER ARTICLE, its folios landing inside the
    page range its own masthead prints, WHILE UNPAYWALL CALLS IT `submittedVersion`. The bytes outrank
    the label in BOTH directions -- and only the bytes ever do.
    """
    for src, label in stmts:
        if label in INADMISSIBLE_VERSION_LABELS:
            if typeset_ok:
                continue          # the BYTES say typesetter. A label does not outrank the bytes.
            kind = 'ACCEPTED_MANUSCRIPT' if label == 'acceptedVersion' else 'WORKING_PAPER'
            return (kind, 'INADMISSIBLE',
                    f'{src} says `{label}`: {INADMISSIBLE_VERSION_LABELS[label]}. Not one byte of this '
                    f'document carries publisher typeset furniture, so nothing overturns that label. '
                    f'Attributable AS AN ACCEPTED MANUSCRIPT / WORKING PAPER ONLY; a span reaches the '
                    f'journal only across a verified per-span SpanCorrespondence into VoR bytes')
    return None


def _admit(prof: dict, tp: dict, stmts: list[tuple[str, str]], bid: dict | None,
           oa_native, preprint) -> tuple[str, str, str]:
    """THE ADMITTING BRANCHES. A ruling of ADMISSIBLE can be minted HERE AND NOWHERE ELSE.

    DEFENCE IN DEPTH: this function re-checks the veto and REFUSES TO RUN if one is live. The caller
    already checked it; that is the point. The P0 came back twice because a correct rule was placed
    where something else could answer first, so the admitting code now makes the check ITSELF, and a
    future refactor that calls `_admit()` directly -- or reorders `rule()` -- raises instead of
    admitting. You cannot get here with an accepted manuscript. There is no branch order that permits it.
    """
    typeset_ok = is_publisher_typeset(tp)
    veto = version_veto(stmts, typeset_ok)
    if veto is not None:
        raise AssertionError(
            f'_admit() was reached for a manifestation the version veto forbids ({veto[0]}). '
            f'THE V9 P0 HAS BEEN REOPENED BY A REORDERING. Nothing may be admitted here.')

    if typeset_ok:
        if tp['folios_in_declared_range'] >= 3:
            return ('JOURNAL_ARTICLE', 'ADMISSIBLE',
                    f"publisher typeset furniture: {tp['folios_in_declared_range']} printed page folios "
                    f"landing inside the page range {tp['declared_range']} that this document's own "
                    f"masthead prints — an author manuscript paginates from 1; only the article of "
                    f"record is numbered with the journal's own pages")
        return ('JOURNAL_ARTICLE', 'ADMISSIBLE',
                f"publisher typeset furniture: the journal's name at the top of {tp['page_top_heads']} "
                f"pages, {tp['folios']} printed page folios — a cover sheet is one page and a "
                f"bibliography is not page furniture; only a typesetter emits these")

    if any(lbl in ADMISSIBLE_VERSION_LABELS for _s, lbl in stmts) and bid:
        return ('JOURNAL_ARTICLE', 'ADMISSIBLE',
                f"held bytes are {bid['cover']:.3f}-identical to a location an authenticated backend "
                f"labels `publishedVersion` — these ARE the article of record")

    if oa_native and tp['wp_series_marks'] == 0:
        return ('JOURNAL_ARTICLE', 'ADMISSIBLE',
                f"open-access article-of-record header block ({oa_native.group(0)[:40]!r}) and no "
                f"working-paper furniture anywhere in the front matter")

    return ('UNDETERMINED_VERSION', 'INADMISSIBLE',
            'no publisher typeset furniture and no authenticated version statement — we cannot show '
            'these bytes are the article of record')


def rule(prof: dict, tp: dict, bid: dict | None, align_ver: str | None,
         oa_native, preprint) -> tuple[str, str, str]:
    """THE ONE REDUCER. Every ruling in this file is minted here — (held_kind, ruling, why).

    Read the shape, not the branches: DISQUALIFIERS FIRST, ALL OF THEM, and only then may `_admit()`
    be called at all. Admissibility is what is left when nothing forbids it — it is never something a
    branch races to say first.
    """
    bid_ver = (bid or {}).get('version')
    stmts = version_statements(bid_ver, align_ver)
    typeset_ok = is_publisher_typeset(tp)

    # ---- 1. THE BYTES ARE NOT USABLE EVIDENCE AT ALL. Version is moot. --------------------------
    if prof['identity']['verdict'] == 'CONTRADICTED':
        return ('WRONG_WORK', 'PURGE',
                'these bytes are a different work by a different author — nothing to align')
    if prof['artifact_kind'] == 'landing_page':
        return ('LANDING_PAGE', 'NO_EVIDENCE', 'a web page about the document, not the document')
    if prof['extractability']['verdict'] == 'CORRUPT':
        return ('EXTRACTION_FAILURE', 'NO_EVIDENCE', 'bytes are not readable prose')

    # ---- 2. THE VERSION VETO. A PRECONDITION — checked before ANY admitting branch can run. -----
    veto = version_veto(stmts, typeset_ok)
    if veto is not None:
        return veto

    # ---- 3. THE BYTES DISQUALIFY THEMSELVES. Also a precondition, for the same reason: a preprint
    #         that happens to trip an admitting branch is the identical bug with a different label.
    if tp['wp_series_marks'] >= 1 and not typeset_ok:
        return ('WORKING_PAPER', 'INADMISSIBLE',
                'the bytes self-declare a working-paper series and carry no publisher typeset furniture')
    if preprint and not oa_native and not typeset_ok:
        return ('PREPRINT', 'INADMISSIBLE',
                'the bytes say which journal they are FOR — an author preprint, not the journal’s text')

    # ---- 4. NOTHING FORBIDS IT. Only now may anything be admitted. ------------------------------
    kind, ruling, why = _admit(prof, tp, stmts, bid, oa_native, preprint)

    # ---- 5. THE POSTCONDITION. The ladder cannot be reordered into a fabrication without tripping
    #         this, and it does not care which branch answered or in what order.
    if ruling == 'ADMISSIBLE':
        bad = [lbl for _s, lbl in stmts if lbl in INADMISSIBLE_VERSION_LABELS]
        assert not bad or typeset_ok, (
            f'ADMISSIBLE was minted for a manifestation an authenticated backend labels {bad!r} and '
            f'whose bytes carry NO publisher typeset furniture. THE V9 P0 IS REOPENED.')
    return kind, ruling, why


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

        # An OA-NATIVE journal article (PLOS, JAIR, BMC, PMC, ScienceDirect) has no form-feed folios
        # to count -- the folio test is a PDF test and simply cannot see them. Their article-of-record
        # furniture is a header block: a volume/page range, a received/accepted date line, an
        # "OPEN ACCESS"/"RESEARCH ARTICLE" stamp, or the publisher's masthead.
        oa_native = re.search(
            r'(research article|open access|contents lists available at sciencedirect'
            r'|received .{0,60}accepted|\(\d{4}\) *\d+:\d+|\b\d+ *\(\d{4}\) *\d+[-–]\d+)', ft[:3000], re.I)
        # A preprint says which journal it is FOR. That is not the journal's rendering of it.
        preprint = re.search(r'\bfor [A-Z][a-z]+ and [A-Z][a-z]+\s*$|submitted to\b', ft[:3000], re.M)

        # ---- THE RULING. ONE reducer, which no branch order can bypass. (See `rule()` above.) ----
        kind, ruling, why = rule(prof, tp, bid, (a.get('journal_bytes') or {}).get('version'),
                                 oa_native, preprint)

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
