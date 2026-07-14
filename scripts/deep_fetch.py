#!/usr/bin/env python3
"""DEEP FETCH — go back for the papers we failed to get text for.

The first pass asked Unpaywall for its single "best" OA location and gave up if that failed. But the
papers we missed include the MOST important work in the field: Autor-Levy-Murnane (4,743 cites, the
foundational task-based paper), Acemoglu & Restrepo's JPE, Goldin & Katz, Krueger. 21,726 combined
citations. A review of this literature that cannot cite Autor-Levy-Murnane is not a serious review.

They are paywalled at the publisher — but economics papers almost always have a legitimate free
version: an NBER/IZA working paper, an institutional repository copy (MIT DSpace), a RePEc listing,
or an author's own posting. This tries EVERY location Unpaywall knows about, not just the best one,
plus the abstract from the publisher landing page.

Everything stored is VERBATIM.

TWO THINGS THIS FILE USED TO SAY, AND MAY NOT SAY ANY MORE
─────────────────────────────────────────────────────────────────────────────────────────────────
1.  `mark = 'RECOVERED' if c['content_status'] != 'CITATION_ONLY' else 'still paywalled'`

    "still paywalled" is a claim about ENTITLEMENT — about the world. We printed it after an HTTP 429.
    We printed it for Autor, Levy & Murnane, whose free copy is NBER Working Paper 8337 and has been
    free, in full, forever. The line was not describing the literature. It was describing our own
    request rate, and it was doing it in the vocabulary of the literature.

2.  `c['content_status'] = 'FULLTEXT'` / `'ABSTRACT_ONLY'` / (silently left) `'CITATION_ONLY'`

    A component asserting its own success. CITATION_ONLY is the MINER'S EXCLUSION LABEL: a paper that
    carries it is never read again. So the throttle did not merely fail to recover the paper — it
    DELETED THE PAPER FROM THE EVIDENCE BASE, permanently, and left a label saying the world was
    responsible.

    And the SELECTOR at the top of main() closed the loop: `targets = [c for c in corpus if
    c['content_status'] == 'CITATION_ONLY']`. It read the label that the failing fetcher had written,
    so the 535-word cookie banner stamped FULLTEXT was NEVER RETRIED — the lie protected itself.

NOW: targets are DERIVED from the bytes we hold (`holds_nothing`, through the shared reducer), every
request's outcome is on the durable ledger, and every set of bytes we obtain becomes an immutable,
content-addressed manifestation. This file writes no status, and has no API that could.

Usage: python scripts/deep_fetch.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402
    MAILTO, Acquirer, BlobStore, content_host, extract_text, holds_nothing, open_ledger,
)
from event_ledger import derive_backend_outcome, derive_content_profile, derive_route_status  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'

#: Named BEFORE the loop walks them. `route_complete` = every one of these has a TERMINAL OUTCOME
#: RECORD — never "an adapter was mapped".
ADAPTERS = ('unpaywall', 's2/oa-pdf', 's2/abstract')

#: How many OA locations to try per paper. A BUDGET, not a fact about the world — and when we stop
#: because of it we emit BUDGET_STOPPED, because a budget stop IS NOT AN EVIDENCE GAP.
MAX_LOCATIONS = 4


def jget(acq: Acquirer, unit: str, adapter: str, url: str):
    """A JSON backend call. `unit` and `adapter` are REQUIRED — a request that cannot say what work it
    is about and which backend it asked is a request nothing can reduce over.

    It still returns None when there is no usable body. What changed is that None is no longer the
    ONLY RECORD: THROTTLED / BLOCKED / 404 / timeout is now on the durable ledger with its status code,
    and the reducer decides what it means. The caller is not permitted to.
    """
    return acq.get_json(unit, adapter, url)[1]


def fetch_text(acq: Acquirer, unit: str, url: str, row: dict, candidate_id: str = '') -> str:
    """Fetch a document and RECORD IT AS AN IMMUTABLE MANIFESTATION. Returns the text, verbatim.

    No threshold. No deletion. A 500-word landing page is stored, hashed and profiled like anything
    else — and the shared reducer calls it a landing_page, with its reasons, on the record.

    `candidate_id` IS THE LINEAGE (Sol V9 §1). It says WHICH ROUTE proposed this URL, and it rides the
    content request onto the manifestation. Without it the discovery reducer cannot tell whose document
    this is, and — as it did — credits every route with it.
    """
    adapter = content_host(url)
    r = acq.get(unit, adapter, url, candidate_id=candidate_id)
    if not r.ok:
        return ''
    text, method = extract_text(r.raw, r.content_type)
    acq.record_manifestation(
        unit, locator=url, raw=r.raw, text=text, adapter=adapter, candidate_id=candidate_id,
        requested_title=row.get('title') or '',
        requested_authors=list(row.get('authors') or []),
        requested_doi=row.get('doi') or '',
        requested_venue=row.get('venue') or '',
        requested_year=row.get('year'),
        source_type=str(row.get('type') or 'journal-article'),
        extraction_method=method,
        http_status=r.http_status, content_type=r.content_type)
    return text


def all_oa_locations(acq: Acquirer, unit: str, doi: str) -> list[tuple[str, str]]:
    """EVERY OA location Unpaywall knows — repositories, not just the publisher's best.

    -> [(url, candidate_id)]. The candidate_id is CARRIED, not discarded: these URLs are UNPAYWALL'S
    candidates, and when one of them yields bytes it is Unpaywall's route that earned them. `oa_version`
    stays an OBSERVATION (`acceptedVersion` is a string a repository emitted, never a fact about bytes —
    that conflation is the V9 P0).
    """
    up = jget(acq, unit, 'unpaywall',
              f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}')
    if not up:
        return []
    out: dict[str, str] = {}
    for loc in (up.get('oa_locations') or []):
        for k in ('url_for_pdf', 'url'):
            if loc.get(k) and loc[k] not in out:
                out[loc[k]] = acq.candidate(
                    unit, 'unpaywall', loc[k],
                    oa_version=str(loc.get('version') or ''),
                    host_type=str(loc.get('host_type') or ''))
    return list(out.items())


def semantic_scholar_pdf(acq: Acquirer, unit: str, doi: str) -> tuple[str, str]:
    """-> (url, candidate_id). Semantic Scholar's OWN candidate — and it is credited to Semantic Scholar,
    not to whoever else happened to fetch a document for this work."""
    d = jget(acq, unit, 's2/oa-pdf',
             f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}'
             f'?fields=openAccessPdf,abstract')
    url = ((d or {}).get('openAccessPdf') or {}).get('url') or ''
    if not url:
        return '', ''
    return url, acq.candidate(unit, 's2/oa-pdf', url)


def s2_abstract(acq: Acquirer, unit: str, doi: str) -> str:
    d = jget(acq, unit, 's2/abstract',
             f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}'
             f'?fields=abstract')
    return (d or {}).get('abstract') or ''


def main() -> int:
    corpus = json.loads(Path(CORPUS).read_text())

    # ── ONE DURABLE LEDGER, OPENED BEFORE RETRIEVAL ───────────────────────────────────────────────
    ledger = open_ledger()
    blobs = BlobStore()
    acq = Acquirer('deep_fetch', ledger=ledger, blobs=blobs)

    # ── TARGETS ARE DERIVED FROM THE BYTES, NOT READ OFF A LABEL. ─────────────────────────────────
    # `content_status == 'CITATION_ONLY'` asked the failing fetcher whether it had failed. This asks
    # the reducer what we actually hold — so the cookie banner that was stamped FULLTEXT, and the PDF
    # whose font never decoded, are BOTH targets now. They never were before.
    targets = [c for c in corpus if holds_nothing(c)]
    print(f'=== deep fetch: {len(targets)} papers for which we hold no usable document ===')
    print(f'    (derived from the bytes, through the shared reducer — not from a `content_status`)')
    print(f'    ledger: {ledger._path}  ({len(ledger)} events already on the record)\n')

    for i, c in enumerate(targets, 1):
        doi = c['doi']
        unit = doi

        # 1. ROUTE_PLANNED, before the adapter loop.
        acq.plan_route(unit, ADAPTERS, requested_title=c.get('title') or '', doi=doi,
                       requested_venue=c.get('venue') or '', requested_year=c.get('year'),
                       requested_authors=list(c.get('authors') or []),
                       source_type=str(c.get('type') or 'journal-article'))

        # 2. every OA location Unpaywall knows (repository copies, working papers)
        locs = all_oa_locations(acq, unit, doi)
        for url, cid in locs[:MAX_LOCATIONS]:
            fetch_text(acq, unit, url, c, candidate_id=cid)
        if len(locs) > MAX_LOCATIONS:
            # A BUDGET STOP IS NOT AN EVIDENCE GAP. We stopped; the world did not run out.
            acq.budget_stopped(unit, n_locations_known=len(locs), n_locations_tried=MAX_LOCATIONS,
                               reason_text=f'tried {MAX_LOCATIONS} of {len(locs)} known OA locations')

        # 3. Semantic Scholar's own OA pdf pointer
        pdf, pdf_cid = semantic_scholar_pdf(acq, unit, doi)
        if pdf:
            fetch_text(acq, unit, pdf, c, candidate_id=pdf_cid)

        # 4. at minimum, an abstract. (Note: NOT gated on "did we get full text?" — we have no way of
        #    knowing that here, and asking would mean concluding.)
        ab = s2_abstract(acq, unit, doi)
        if ab and not (c.get('abstract') or '').strip():
            c['abstract'] = ab

        # ---- what do the EVENTS say we now hold? -------------------------------------------------
        # THE FLAT-CORPUS WRITE IS GONE (Sol V9 §1). It used to be four lines:
        #
        #     if best is not None and best['content_class'] != 'CITATION_ONLY':
        #         c['fulltext'] = best['text'][:120000]
        #         c['fulltext_words'] = len(c['fulltext'].split())
        #         c['oa_url'] = best['manifestation'].get('locator') or c.get('oa_url') or ''
        #
        # and each of them did damage:
        #
        #   1. `!= 'CITATION_ONLY'` ADMITS ANYTHING ELSE. A landing page, an unreadable PDF, a
        #      stranger's paper — all of them are "not CITATION_ONLY", so all of them became `fulltext`.
        #      That is admission by ELIMINATION, which is not a reducer's judgment; it is the absence of
        #      one. The reducers already say what a document IS (`derive_content_profile`,
        #      `derive_semantic_binding`), and this line did not ask them.
        #   2. `[:120000]` SILENTLY TRUNCATES. A span mined at offset 121,000 of the real document simply
        #      cannot exist, and — far worse — a span mined from the truncated text has offsets into a
        #      STRING NOBODY HOLDS. The manifestation's hash covers the full bytes; the corpus row held a
        #      prefix. Every offset in every card built from that row indexed a document that was never
        #      stored anywhere.
        #   3. IT DISCARDS THE MANIFESTATION IDENTITY THE LAW NEEDS. `c['fulltext']` is a detached string.
        #      A span bound to it binds to nothing: no manifestation_id, no content hash, no route, no
        #      candidate, no identity decision. That is precisely the shape of the original P0 — a row
        #      with a journal's name and a working paper's text — reintroduced by the fetcher that was
        #      written to end it.
        #
        # What the row gets instead is a REFERENCE: the ids of the immutable manifestations this run
        # recorded, each already hashed, profiled and lineage-bearing. Downstream synthesis resolves
        # those through provenance.Graph and binds spans to REAL BYTES, or it gets nothing. There is no
        # third option, and there is no `fulltext` key written here to provide one.
        held = []
        for e in ledger.events(unit):
            if e.kind != 'manifestation_fetched' or 'derived_by' in e.payload:
                continue
            held.append(dict(
                manifestation_id=e.payload.get('text_sha256', '')[:12],
                text_sha256=e.payload.get('text_sha256', ''),
                text_blob_id=e.payload.get('text_blob_id', ''),
                blob_id=e.payload.get('blob_id', ''),
                byte_sha256=e.payload.get('byte_sha256', ''),
                locator=e.payload.get('locator', ''),
                adapter=e.payload.get('adapter', ''),
                candidate_id=e.payload.get('candidate_id', ''),
            ))
        if held:
            # NOT `fulltext`, NOT `fulltext_words`, NOT `content_status`. This key names BYTES WE HOLD,
            # and it is the only thing this file is entitled to say about them.
            c['manifestations'] = held

        cls, _ = derive_content_profile(ledger.events(unit))
        route = derive_route_status(ledger.events(unit))
        outcomes = ', '.join(f'{a}={derive_backend_outcome(ledger.events(unit), a)}'
                             for a in route.planned)
        print(f"  [{i:>2}/{len(targets)}] {cls:<15} {c.get('citations', 0):>5} cites | "
              f"{str(c.get('attribution_short', ''))[:40]:<40} route={route.state}")
        print(f"                        {outcomes}")

    Path(CORPUS).write_text(json.dumps(corpus, indent=1))
    print('\n' + '=' * 78)
    print(f'  wrote {CORPUS}')
    print(f'  wrote {ledger._path}  ({len(ledger)} events)')
    print('\n  NOTHING ABOVE IS A CONCLUSION ABOUT THE LITERATURE. Where a route reads BACKEND_FAILED,')
    print('  that is a fact about OUR REQUEST — and it is the reason no paper on this list can be')
    print('  marked CITATION_ONLY by anything that ran here. The word is not in this file.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
