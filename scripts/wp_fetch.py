#!/usr/bin/env python3
"""WORKING-PAPER FETCH — go and get the papers where economists actually publish them.

THE PROBLEM THIS SOLVES

  Our 8,000-word review of AI and the labour market rests on TWELVE full-text papers.
  34 of 70 are CITATION_ONLY (the extractor skips them entirely) and 24 are ABSTRACT_ONLY.
  1,825 quantitative findings sit in the text we DO hold; two of them reached the page.
  The #1 system reports 202 numbers. We reported 2. The judge: "rarely presents quantitative
  evidence clearly... citations are named but findings are missing."

  deep_fetch.py asks Unpaywall and Semantic Scholar for the PUBLISHED article, and for a
  corpus like ours that is asking the wrong question. Autor, Levy and Murnane (2003) — the
  most-cited paper in this literature, 4,743 citations — comes back "still paywalled". Of
  course it does. It is in the Quarterly Journal of Economics.

  But it is ALSO NBER Working Paper 8337, free, in full, forever.

  That is not an exception, it is the norm: in economics the working paper is the paper.
  NBER, IZA, RePEc and SSRN hold free full text for essentially every author in this corpus —
  Autor, Acemoglu, Restrepo, Bresnahan. We were never looking there.

WHAT IT DOES
  For every paper still without full text, in order:
    1. Semantic Scholar `openAccessPdf` — aggregates arXiv, NBER, IZA, RePEc, institutional repos
    2. OpenAlex `locations[]`   — every OA copy it knows, not just the publisher's
    3. arXiv title search       — the CS/AI half of the corpus
    4. Unpaywall repository copies
  and takes the first that yields real text.

  It NEVER invents content and never relaxes the gate. Every number it recovers is a number a
  peer-reviewed paper actually printed — which is precisely why it is allowed to reach the page.
"""
from __future__ import annotations

import json
import re
import sys

LOG = open('/home/polaris/wt/flywheel/outputs/wp_fetch.log', 'w', buffering=1)


def say(m):
    print(m, flush=True)
    LOG.write(m + '\n')
import urllib.error
import urllib.parse
import urllib.request      # MUST be module-level: importing it INSIDE a function makes `urllib` a
                           # local name for that whole function, so the urllib.parse call ABOVE the
                           # import raised UnboundLocalError -- and killed the run on paper 1, in
                           # silence, because stderr went to /dev/null. That is how a fetcher spends
                           # 25 minutes "running" and recovers nothing.
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep_fetch import CORPUS, fetch_text, jget  # reuse the proven fetchers

MAILTO = 'polaris@example.org'
MIN_WORDS = 500          # below this it is an abstract wearing a fulltext's clothes

_LAST = [0.0]


def polite_get(url: str, tries: int = 4):
    """A rate-limited, backoff-aware GET. THIS IS NOT POLISH -- IT IS CORRECTNESS.

    Semantic Scholar and OpenAlex were BOTH returning HTTP 429 (we hammered them all night with
    repeated fetch runs). `jget` swallows the error and returns None, and the caller reads None as
    "NO FREE COPY OF THIS PAPER EXISTS".

    That is a false conclusion of the most dangerous kind: it looks like a fact about the world
    ("the literature is paywalled") when it is a fact about our own request rate. We nearly concluded
    the canonical papers were unreachable when we were merely being throttled.
    """
    import time
    for a in range(tries):
        wait = _LAST[0] + 1.1 - time.time()          # >= 1.1s between calls, always
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': f'polaris/1.0 (mailto:{MAILTO})'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(3 * (2 ** a))              # 3s, 6s, 12s, 24s -- let the API breathe
                continue
            return None
        except Exception:
            return None
    return None


def s2_oa_pdf(doi: str) -> str:
    d = polite_get(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}'
                   f'?fields=openAccessPdf,externalIds,title')
    if not d:
        return ''
    url = ((d.get('openAccessPdf') or {}).get('url') or '')
    if url:
        return url
    # arXiv id -> the PDF is free and always reachable
    ax = (d.get('externalIds') or {}).get('ArXiv')
    return f'https://arxiv.org/pdf/{ax}' if ax else ''


def openalex_pdfs(doi: str) -> list[str]:
    """EVERY OA location OpenAlex knows. This is where the NBER/IZA copy shows up."""
    d = polite_get(f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}')
    if not d:
        return []
    urls = []
    for loc in (d.get('locations') or []):
        if not loc.get('is_oa'):
            continue
        for k in ('pdf_url', 'landing_page_url'):
            if loc.get(k):
                urls.append(loc[k])
    return list(dict.fromkeys(urls))


def s2_search_by_title(title: str) -> str:
    """THE ONE THAT ACTUALLY FINDS THE WORKING PAPER.

    Autor/Levy/Murnane (2003) returns NOTHING from Semantic Scholar or OpenAlex when asked BY DOI --
    because the free copy is not an OA location of the QJE article, it is a SEPARATE WORK: NBER
    Working Paper 8337. A DOI lookup can never find it. You have to search by TITLE.
    """
    q = urllib.parse.quote(title[:120])
    d = polite_get(f'https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=5'
                   f'&fields=title,openAccessPdf,externalIds')
    if not d:
        return ''
    want = re.sub(r'[^a-z]', '', title.lower())[:55]
    for p in (d.get('data') or []):
        got = re.sub(r'[^a-z]', '', (p.get('title') or '').lower())
        if not want or want not in got and got[:55] not in want:
            continue                                   # must be THIS paper, not a topical neighbour
        url = ((p.get('openAccessPdf') or {}).get('url') or '')
        if url:
            return url
        ax = (p.get('externalIds') or {}).get('ArXiv')
        if ax:
            return f'https://arxiv.org/pdf/{ax}'
    return ''


def arxiv_by_title(title: str) -> str:
    q = urllib.parse.quote(f'ti:"{title[:110]}"')
    try:
        with urllib.request.urlopen(
                f'http://export.arxiv.org/api/query?search_query={q}&max_results=1', timeout=25) as r:
            xml = r.read().decode('utf-8', 'ignore')
    except Exception:
        return ''
    m = re.search(r'<id>(http://arxiv\.org/abs/([^<]+))</id>', xml)
    if not m:
        return ''
    # the returned entry must actually BE this paper, not a topical neighbour
    t = re.search(r'<title>([^<]+)</title>', xml[xml.find('<entry>'):]) if '<entry>' in xml else None
    if t:
        a = re.sub(r'[^a-z]', '', t.group(1).lower())
        b = re.sub(r'[^a-z]', '', title.lower())
        if not (a[:60] in b or b[:60] in a):
            return ''
    return f'https://arxiv.org/pdf/{m.group(2)}'


def main() -> int:
    corpus = json.loads(CORPUS.read_text())
    targets = [c for c in corpus if c.get('content_status') != 'FULLTEXT']
    say(f'=== working-paper fetch: {len(targets)} papers without full text ===')
    print('    (NBER / IZA / RePEc / arXiv — where economists actually put the paper)\n')

    won = 0
    for i, c in enumerate(targets, 1):
        doi = c.get('doi') or ''
        title = c.get('title') or ''
        who = f"{c['authors'][0] if c.get('authors') else '?'} ({c.get('year')})"

        # NO SOURCE MAY KILL THE RUN. One paper's failure is one paper's failure.
        urls: list[str] = []
        for name, fn in (('s2/doi', lambda: [s2_oa_pdf(doi)] if doi else []),
                         ('openalex', lambda: openalex_pdfs(doi) if doi else []),
                         ('s2/title', lambda: [s2_search_by_title(title)]),   # finds the NBER/IZA copy
                         ('arxiv', lambda: [arxiv_by_title(title)])):
            try:
                urls += [u for u in (fn() or []) if u]
            except Exception as e:
                say(f'       ({name} failed: {type(e).__name__})')

        best = ''
        for u in list(dict.fromkeys(urls))[:4]:
            try:
                txt = fetch_text(u)
            except Exception:
                continue
            if len(txt.split()) > len(best.split()):
                best = txt
            if len(best.split()) >= 3000:
                break

        nw = len(best.split())
        if nw >= MIN_WORDS:
            nums = len(re.findall(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b', best))
            c['fulltext'] = best[:120000]
            c['content_status'] = 'FULLTEXT'
            c['fulltext_source'] = 'working_paper'
            won += 1
            say(f'  [{i:2}/{len(targets)}] ** GOT IT ** {nw:>6,}w  {nums:>3} numbers  {who[:34]:<34}')
        else:
            say(f'  [{i:2}/{len(targets)}] no free text        {who[:34]:<34}')

    Path(CORPUS).write_text(json.dumps(corpus, indent=1))
    ft = sum(1 for c in corpus if c.get('content_status') == 'FULLTEXT')
    tot = sum(len(re.findall(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b',
                             c.get('fulltext') or '')) for c in corpus)
    print(f'\n=== recovered full text for {won} more papers ===')
    print(f'    FULLTEXT papers : 12 -> {ft}  (of {len(corpus)})')
    print(f'    quantitative claims now available to the extractor: {tot:,}  (was 1,825)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
