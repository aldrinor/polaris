#!/usr/bin/env python3
"""FETCH CONTENT for the journal corpus — turn 70 citations into 70 usable evidence sources.

A citation with no text cannot ground a claim. This pulls, for every paper in the corpus:
  1. the Crossref abstract (JATS-tagged; we strip the tags), and
  2. the open-access full text where Unpaywall finds one (PDF or HTML landing page).

Both are free, no key. Everything stored is VERBATIM — we never paraphrase or summarise at fetch
time, because every downstream claim must be span-grounded against the real words.

WHAT THIS FILE USED TO DO, AND WHY IT WAS THE DISEASE
─────────────────────────────────────────────────────────────────────────────────────────────────
It ENDED with a conclusion. Three branches, at the bottom of the loop:

        if fulltext:   rec['content_status'] = 'FULLTEXT'
        elif abstract: rec['content_status'] = 'ABSTRACT_ONLY'
        else:          rec['content_status'] = 'CITATION_ONLY'   # <- the MINER'S EXCLUSION LABEL

and, four lines above it, the quiet one that made the third branch reachable:

        if len(fulltext.split()) < 400:
            fulltext = ''                       # "a landing page that yielded almost nothing"

That line DELETED THE BYTES. It applied one universal number to every document in the world, decided
the document did not count, threw it away, and then — with the evidence gone — wrote CITATION_ONLY,
which tells the miner never to look at this paper again.

Every one of those `get_json` calls returns `None` on ANY exception. HTTP 429 is an exception. So a
throttle we caused, on a paper whose free copy provably exists, walked straight down that chain and
came out as a permanent, load-bearing claim about the literature.

NOW: THIS FILE OBSERVES. IT DOES NOT CONCLUDE.
─────────────────────────────────────────────────────────────────────────────────────────────────
Every request emits BACKEND_ATTEMPTED and exactly one of RESPONSE_RECEIVED | THROTTLED | BLOCKED.
Every byte we obtain becomes an IMMUTABLE MANIFESTATION — blob id, byte hash, locator, the identity we
ASKED for — and is profiled by the shared reducer. Nothing here decides what a document IS, whether it
is complete, or whether it may be cited. There is no `content_status` in this file, and no API it
could call to write one.

Usage:  python scripts/journal_corpus_fetch.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402
    MAILTO, Acquirer, content_host, extract_text, open_ledger,
)
from event_ledger import derive_content_profile  # noqa: E402

JATS = re.compile(r'<[^>]+>')

#: The route, named BEFORE we walk it — so `route_complete` can mean "every one of these answered",
#: and never "an adapter was mapped".
ADAPTERS = ('crossref', 'unpaywall')


def get_json(acq: Acquirer, unit: str, adapter: str, url: str):
    """A JSON backend call. THE UNIT AND THE ADAPTER ARE REQUIRED ARGUMENTS.

    They used to be absent — `get_json(url)` — and that is not a stylistic difference. A request that
    does not say WHAT WORK IT IS ABOUT and WHICH BACKEND IT ASKED cannot be reduced over, so the only
    thing left to interpret its failure was the caller, who read `None` as "no copy exists".

    This still returns None when there is no usable body. The difference is that the None is no longer
    the only surviving record of what happened: THROTTLED, BLOCKED, or a 404 is now on disk, durably,
    and the reducer — not this function's caller — decides what it means.
    """
    return acq.get_json(unit, adapter, url)[1]


def get_text(acq: Acquirer, unit: str, url: str, row: dict) -> str:
    """Fetch an OA document and RECORD IT AS A MANIFESTATION. Returns the text, verbatim.

    NOTHING IS THRESHOLDED HERE AND NOTHING IS DELETED. A 500-word landing page is retained, hashed,
    stored and profiled — and the SHARED REDUCER calls it a landing_page. That is the same outcome the
    old `if len(fulltext.split()) < 400: fulltext = ''` was reaching for, except that the bytes still
    exist afterwards, the reason is on the record, and the judgement was made by the one component
    entitled to make it.
    """
    adapter = content_host(url)
    r = acq.get(unit, adapter, url)
    if not r.ok:
        # THROTTLED / BLOCKED / 404 / timeout — all of it is already in the ledger, with its status
        # code. We return no text because we HAVE no text. We do not say why: we are not entitled to.
        return ''
    text, method = extract_text(r.raw, r.content_type)
    acq.record_manifestation(
        unit, locator=url, raw=r.raw, text=text, adapter=adapter,
        requested_title=row.get('title') or '',
        requested_authors=list(row.get('authors') or []),
        requested_doi=row.get('doi') or '',
        requested_venue=row.get('venue') or '',
        requested_year=row.get('year'),
        source_type=str(row.get('type') or 'journal-article'),
        extraction_method=method,
        http_status=r.http_status, content_type=r.content_type)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default='outputs/journal_corpus.json')
    ap.add_argument('--out', default='outputs/journal_corpus_content.json')
    ap.add_argument('--ledger', default=None, help='THE ONE DURABLE LEDGER (default: outputs/)')
    a = ap.parse_args()

    corpus = json.loads(Path(a.corpus).read_text())

    # ── ONE DURABLE LEDGER, OPENED BEFORE RETRIEVAL. ──────────────────────────────────────────────
    ledger = open_ledger(a.ledger)
    acq = Acquirer('journal_corpus_fetch', ledger=ledger)
    print(f'=== content acquisition: {len(corpus)} papers ===')
    print(f'    ledger: {ledger._path}  ({len(ledger)} events already on the record)\n')

    out = []
    for i, c in enumerate(corpus, 1):
        doi = c['doi']
        unit = doi
        rec = dict(c)

        # 1. ROUTE_PLANNED — before the adapter loop, naming the adapters we are ABOUT to try.
        acq.plan_route(unit, ADAPTERS, requested_title=c.get('title') or '', doi=doi,
                       requested_venue=c.get('venue') or '', requested_year=c.get('year'),
                       requested_authors=list(c.get('authors') or []),
                       source_type=str(c.get('type') or 'journal-article'))

        # 2. abstract (Crossref, JATS -> plain). The abstract is an OBSERVATION: it is text we hold.
        m = get_json(acq, unit, 'crossref',
                     f'https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}')
        abstract = ''
        if m:
            raw = (m.get('message') or {}).get('abstract') or ''
            if raw:
                abstract = re.sub(r'\s{2,}', ' ', JATS.sub(' ', raw)).strip()
        rec['abstract'] = abstract

        # 3. open-access full text (Unpaywall -> fetch)
        up = get_json(acq, unit, 'unpaywall',
                      f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}')
        loc = (up or {}).get('best_oa_location') or {}
        url = loc.get('url_for_pdf') or loc.get('url') or ''

        fulltext = ''
        if url:
            acq.candidate(unit, 'unpaywall', url,
                          oa_version=str(loc.get('version') or ''),
                          host_type=str(loc.get('host_type') or ''))
            fulltext = get_text(acq, unit, url, c)

        rec['oa_url'] = url
        rec['fulltext'] = fulltext[:120000]
        # The count describes the text ON THIS ROW. It was taken BEFORE the truncation and never
        # re-derived, so four rows claimed a document they no longer held.
        rec['fulltext_words'] = len(rec['fulltext'].split())

        # ** NO content_status IS WRITTEN HERE. ** The label is DERIVED, by the reducer, from the
        # events above — and this call reads the ledger, not a variable we happen to have in scope.
        cls, info = derive_content_profile(ledger.events(unit))

        out.append(rec)
        print(f"  [{i:>2}/{len(corpus)}] {cls:<14} "
              f"{(c['authors'][0] + ' ' + str(c['year'])):<22.22} "
              f"abs={len(abstract.split()):>4}w ft={rec['fulltext_words']:>6}w  "
              f"{info.get('artifact_kind', '?'):<18.18} {c['venue'][:26]}")

    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f'\nwrote {a.out}')
    print(f'wrote {ledger._path}  ({len(ledger)} events)')
    print('\n  Every label above was DERIVED from the events by a reducer. This script wrote none of')
    print('  them, and holds no API that could. What it wrote is bytes, hashes, and observations.')
    print('\n  A 429 is now THROTTLED -> BACKEND_FAILED, on the record, forever. It cannot become')
    print('  CITATION_ONLY, because CITATION_ONLY is not a sentence this file is able to say.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
