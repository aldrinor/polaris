#!/usr/bin/env python3
"""WORKING-PAPER FETCH — go and get the papers where economists actually publish them.

THE PROBLEM THIS SOLVES

  deep_fetch asks Unpaywall and Semantic Scholar for the PUBLISHED article, and for a corpus like
  ours that is asking the wrong question. Autor, Levy and Murnane (2003) — the most-cited paper in
  this literature, 4,743 citations — comes back "still paywalled". Of course it does. It is in the
  Quarterly Journal of Economics.

  But it is ALSO NBER Working Paper 8337, free, in full, forever.

  In economics the working paper IS the paper. NBER, IZA, RePEc and SSRN hold free full text for
  essentially every author in this corpus. We were never looking there. So: Semantic Scholar's
  openAccessPdf, OpenAlex's every location, an arXiv title search, and — the one that actually works —
  a TITLE search, because the free copy is not an OA location of the QJE article, it is A SEPARATE
  WORK, and a DOI lookup can never find it.

THE THREE LINES THAT MADE THIS FILE A LIABILITY
─────────────────────────────────────────────────────────────────────────────────────────────────
        c['content_status'] = 'FULLTEXT'
        c['fulltext_source'] = 'working_paper'

  `fulltext_source='working_paper'` reads as a statement about the DOCUMENT. It is not. It is a
  statement about WHICH SCRIPT RAN — this one. It was tested against what the documents actually are,
  and IT IS WRONG IN BOTH DIRECTIONS:

      * it MARKED Acemoglu & Restrepo (2019), whose header reads "Journal of Economic Perspectives —
        Volume 33, Number 2 — Spring 2019 — Pages 3-30". That IS the journal article. Quarantining on
        this label would have DESTROYED it, along with Goos (2014, AER) and Chalmers (2021).
      * it MISSED four genuine NBER/MIT/Fed working papers that no fetcher in this file touched.

  AGREEMENT BETWEEN THE LABEL AND THE TRUTH: ZERO.

  And `MIN_WORDS = 2500` — a universal word threshold, written in this file, in the fix for the bug
  that a universal word threshold IS. A judicial opinion is complete at 105 words. A cookie banner is
  incomplete at 100,000. Completeness is a property OF A KIND, and the registry in provenance.py is
  the one place that knows it.

NOW: this file OBSERVES. Whether these bytes are the journal version or a working paper is DERIVED
FROM THEIR OWN HEADER, by the reducer, in the open — and if they are a working paper, that is not a
defect to be hidden behind a label. It is a DISCOVERY LEAD, and peer review changes numbers.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402
    MAILTO, Acquirer, BlobStore, holds_usable_document, open_ledger, select_evidence,
)
from deep_fetch import CORPUS, fetch_text  # THE ONE document fetcher — it records the manifestation
from event_ledger import (  # noqa: E402
    derive_backend_outcome, derive_content_profile, derive_route_status, derive_semantic_binding,
)

LOG = open('/home/polaris/wt/flywheel/outputs/wp_fetch.log', 'w', buffering=1)


def say(m):
    print(m, flush=True)
    LOG.write(m + '\n')


#: Named BEFORE the loop walks them.
ADAPTERS = ('s2/doi', 'openalex', 's2/title', 'arxiv')

#: A BUDGET, not a fact about the world. Exceeding it emits BUDGET_STOPPED.
MAX_CANDIDATES = 4


def polite_get(acq: Acquirer, unit: str, adapter: str, url: str):
    """A rate-limited, backoff-aware JSON GET. THIS IS NOT POLISH — IT IS CORRECTNESS.

    Semantic Scholar and OpenAlex were BOTH returning HTTP 429 (we hammered them all night with
    repeated fetch runs). The old `jget` swallowed the error and returned None, and the caller read
    None as "NO FREE COPY OF THIS PAPER EXISTS" — a false conclusion of the most dangerous kind,
    because it looks like a fact about the world when it is a fact about our own request rate.

    The backoff is still here (spacing and 3/6/12/24s retries live in `Acquirer.get`). What is new is
    that IT NO LONGER MATTERS WHETHER THE BACKOFF SAVES US: if it does not, the exhausted 429 is on
    the durable ledger as THROTTLED, the reducer derives BACKEND_FAILED, and there is no code path
    anywhere in this file that can turn that into a claim about the literature.
    """
    return acq.get_json(unit, adapter, url)[1]


def s2_oa_pdf(acq: Acquirer, unit: str, doi: str) -> list[str]:
    d = polite_get(acq, unit, 's2/doi',
                   f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}'
                   f'?fields=openAccessPdf,externalIds,title')
    if not d:
        return []
    url = ((d.get('openAccessPdf') or {}).get('url') or '')
    if url:
        acq.candidate(unit, 's2/doi', url, document_title=str(d.get('title') or ''))
        return [url]
    ax = (d.get('externalIds') or {}).get('ArXiv')      # arXiv id -> the PDF is free and reachable
    if ax:
        u = f'https://arxiv.org/pdf/{ax}'
        acq.candidate(unit, 's2/doi', u, document_title=str(d.get('title') or ''),
                      matched_on='arXiv id from the DOI record')
        return [u]
    return []


def openalex_pdfs(acq: Acquirer, unit: str, doi: str) -> list[str]:
    """EVERY OA location OpenAlex knows. This is where the NBER/IZA copy shows up."""
    d = polite_get(acq, unit, 'openalex',
                   f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}')
    if not d:
        return []
    urls = []
    for loc in (d.get('locations') or []):
        if not loc.get('is_oa'):
            continue
        for k in ('pdf_url', 'landing_page_url'):
            if loc.get(k):
                urls.append(loc[k])
                acq.candidate(unit, 'openalex', loc[k],
                              oa_version=str(loc.get('version') or ''),
                              host=str((loc.get('source') or {}).get('display_name') or ''))
    return list(dict.fromkeys(urls))


def s2_search_by_title(acq: Acquirer, unit: str, title: str) -> list[str]:
    """THE ONE THAT ACTUALLY FINDS THE WORKING PAPER.

    Autor/Levy/Murnane (2003) returns NOTHING from Semantic Scholar or OpenAlex when asked BY DOI —
    because the free copy is not an OA location of the QJE article, it is a SEPARATE WORK: NBER
    Working Paper 8337. A DOI lookup can never find it. You have to search by TITLE.

    And a title search is exactly how we came to hold Yang-Hui He's "Mathematics: The Rise of the
    Machines" (arXiv, theorem-proving) filed under an HR journal article by Parry et al. So the
    title the backend returned is recorded on the CANDIDATE as `document_title`, and the IDENTITY
    CHECK is done by the reducer, against the bytes' own header — not by this filter.
    """
    q = urllib.parse.quote(title[:120])
    d = polite_get(acq, unit, 's2/title',
                   f'https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=5'
                   f'&fields=title,openAccessPdf,externalIds')
    if not d:
        return []
    want = re.sub(r'[^a-z]', '', title.lower())[:55]
    out = []
    for p in (d.get('data') or []):
        got = re.sub(r'[^a-z]', '', (p.get('title') or '').lower())
        if not want or want not in got and got[:55] not in want:
            continue                                   # must be THIS paper, not a topical neighbour
        url = ((p.get('openAccessPdf') or {}).get('url') or '')
        if not url:
            ax = (p.get('externalIds') or {}).get('ArXiv')
            url = f'https://arxiv.org/pdf/{ax}' if ax else ''
        if url:
            out.append(url)
            acq.candidate(unit, 's2/title', url, document_title=str(p.get('title') or ''),
                          matched_on='title search')
    return out


def arxiv_by_title(acq: Acquirer, unit: str, title: str) -> list[str]:
    q = urllib.parse.quote(f'ti:"{title[:110]}"')
    r = acq.get(unit, 'arxiv',
                f'http://export.arxiv.org/api/query?search_query={q}&max_results=1', timeout=25)
    if not r.ok:
        return []
    xml = r.raw.decode('utf-8', 'ignore')
    m = re.search(r'<id>(http://arxiv\.org/abs/([^<]+))</id>', xml)
    if not m:
        return []
    t = re.search(r'<title>([^<]+)</title>', xml[xml.find('<entry>'):]) if '<entry>' in xml else None
    got_title = t.group(1) if t else ''
    if t:
        a = re.sub(r'[^a-z]', '', got_title.lower())
        b = re.sub(r'[^a-z]', '', title.lower())
        if not (a[:60] in b or b[:60] in a):
            return []
    u = f'https://arxiv.org/pdf/{m.group(2)}'
    acq.candidate(unit, 'arxiv', u, document_title=got_title, matched_on='arXiv title search')
    return [u]


def main() -> int:
    corpus = json.loads(Path(CORPUS).read_text())

    # ── ONE DURABLE LEDGER, OPENED BEFORE RETRIEVAL ───────────────────────────────────────────────
    ledger = open_ledger()
    blobs = BlobStore()
    acq = Acquirer('wp_fetch', ledger=ledger, blobs=blobs)

    # ── TARGETS DERIVED FROM THE BYTES. `content_status != 'FULLTEXT'` asked a label written by the
    #    fetcher that failed. This asks the shared reducer what we actually hold.
    targets = [c for c in corpus if not holds_usable_document(c)]
    say(f'=== working-paper fetch: {len(targets)} papers for which we hold no complete document ===')
    say('    (NBER / IZA / RePEc / arXiv — where economists actually put the paper)')
    say(f'    ledger: {ledger._path}  ({len(ledger)} events already on the record)\n')

    for i, c in enumerate(targets, 1):
        doi = c.get('doi') or ''
        title = c.get('title') or ''
        unit = doi or title
        who = f"{c['authors'][0] if c.get('authors') else '?'} ({c.get('year')})"

        # 1. ROUTE_PLANNED, before the adapter loop.
        acq.plan_route(unit, ADAPTERS, requested_title=title, doi=doi,
                       requested_venue=c.get('venue') or '', requested_year=c.get('year'),
                       requested_authors=list(c.get('authors') or []),
                       source_type=str(c.get('type') or 'journal-article'))

        # NO SOURCE MAY KILL THE RUN. One paper's failure is one paper's failure.
        urls: list[str] = []
        for name, fn in (('s2/doi',   lambda: s2_oa_pdf(acq, unit, doi) if doi else []),
                         ('openalex', lambda: openalex_pdfs(acq, unit, doi) if doi else []),
                         ('s2/title', lambda: s2_search_by_title(acq, unit, title)),
                         ('arxiv',    lambda: arxiv_by_title(acq, unit, title))):
            try:
                urls += [u for u in (fn() or []) if u]
            except Exception as e:
                say(f'       ({name} raised: {type(e).__name__})')

        # 2. fetch the candidates. NOT "until one is long enough" — the reducer decides what they are,
        #    and every one of them is retained. Choosing by length is how a 535-word cookie banner
        #    beat a real abstract and became FULLTEXT.
        uniq = list(dict.fromkeys(urls))
        for u in uniq[:MAX_CANDIDATES]:
            fetch_text(acq, unit, u, c)
        if len(uniq) > MAX_CANDIDATES:
            acq.budget_stopped(unit, n_candidates=len(uniq), n_tried=MAX_CANDIDATES,
                               reason_text=f'tried {MAX_CANDIDATES} of {len(uniq)} candidate URLs')

        # ---- 3. WHAT DO THE EVENTS SAY WE HOLD? -------------------------------------------------
        best = select_evidence(ledger, unit, blobs)
        if best is not None and best['content_class'] != 'CITATION_ONLY':
            c['fulltext'] = best['text'][:120000]
            c['fulltext_words'] = len(c['fulltext'].split())
            c['oa_url'] = best['manifestation'].get('locator') or c.get('oa_url') or ''
            c['fulltext_manifestation'] = best['manifestation'].get('text_sha256', '')[:12]

        cls, info = derive_content_profile(ledger.events(unit))
        binding, binfo = derive_semantic_binding(ledger.events(unit))
        route = derive_route_status(ledger.events(unit))

        if cls == 'FULLTEXT':
            nw = len((c.get('fulltext') or '').split())
            say(f'  [{i:2}/{len(targets)}] {cls:<15} {nw:>6,}w  {info.get("artifact_kind", "?"):<16} '
                f'{binding:<22} {who[:30]:<30}')
        else:
            say(f'  [{i:2}/{len(targets)}] {cls:<15} route={route.state:<18} '
                f'{who[:30]:<30}')
            for a in route.planned:
                o = derive_backend_outcome(ledger.events(unit), a)
                if o != 'RESPONDED':
                    # NOT "still paywalled". The reason we have no bytes, in the vocabulary of the
                    # transport — which is the only vocabulary we are entitled to use about it.
                    say(f'                        {a:<12} {o}')

    Path(CORPUS).write_text(json.dumps(corpus, indent=1))
    say('\n' + '=' * 78)
    say(f'  wrote {CORPUS}')
    say(f'  wrote {ledger._path}  ({len(ledger)} events)')
    say('\n  NOTE WHAT IS NOT ON THIS ROW ANY MORE: `fulltext_source`. Whether these bytes are the')
    say('  journal version or a working paper is DERIVED FROM THEIR OWN HEADER by the reducer, and')
    say('  reported above as the semantic binding. The old label named the script that ran, agreed')
    say('  with the truth ZERO times out of six, and would have destroyed three genuine journal')
    say('  articles if anyone had quarantined on it.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
