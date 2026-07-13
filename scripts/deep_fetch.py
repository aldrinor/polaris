#!/usr/bin/env python3
"""DEEP FETCH — go back for the 34 papers we failed to get text for.

The first pass asked Unpaywall for its single "best" OA location and gave up if that failed. But the
34 papers we missed include the MOST important work in the field: Autor-Levy-Murnane (4,743 cites, the
foundational task-based paper), Acemoglu & Restrepo's JPE, Goldin & Katz, Krueger. 21,726 combined
citations. A review of this literature that cannot cite Autor-Levy-Murnane is not a serious review.

They are paywalled at the publisher — but economics papers almost always have a legitimate free
version: an NBER/IZA working paper, an institutional repository copy (MIT DSpace), a RePEc listing,
or an author's own posting. This tries EVERY location Unpaywall knows about, not just the best one,
plus the abstract from the publisher landing page.

Everything stored is VERBATIM. A paper we still cannot reach stays CITATION_ONLY — nameable as part of
the literature, never usable to ground a claim. We do not paraphrase what we have not read.

Usage: python scripts/deep_fetch.py
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

MAILTO = 'aldrin.or@c-polarbiotech.com'
UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}
CORPUS = Path('outputs/journal_corpus_content.json')
TAG = re.compile(r'<[^>]+>')


def jget(url, t=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
            return json.loads(r.read())
    except Exception:
        return None


def fetch_text(url: str, t: int = 35) -> str:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
            raw = r.read()
            ctype = r.headers.get('Content-Type', '').lower()
    except Exception:
        return ''
    if 'pdf' in ctype or raw[:4] == b'%PDF':
        try:
            import io
            from pdfminer.high_level import extract_text
            return extract_text(io.BytesIO(raw)) or ''
        except Exception:
            return ''
    try:
        html = raw.decode('utf-8', 'ignore')
    except Exception:
        return ''
    html = re.sub(r'(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html)
    txt = re.sub(r'&[a-z]+;', ' ', TAG.sub(' ', html))
    return re.sub(r'\s{2,}', ' ', txt).strip()


def all_oa_locations(doi: str) -> list[str]:
    """EVERY OA location Unpaywall knows — repositories, not just the publisher's best."""
    up = jget(f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}')
    if not up:
        return []
    urls = []
    for loc in (up.get('oa_locations') or []):
        for k in ('url_for_pdf', 'url'):
            if loc.get(k):
                urls.append(loc[k])
    return list(dict.fromkeys(urls))


def semantic_scholar_pdf(doi: str) -> str:
    d = jget(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}'
             f'?fields=openAccessPdf,abstract')
    if not d:
        return ''
    return ((d.get('openAccessPdf') or {}).get('url') or '')


def s2_abstract(doi: str) -> str:
    d = jget(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}?fields=abstract')
    return (d or {}).get('abstract') or ''


def main() -> int:
    corpus = json.loads(CORPUS.read_text())
    targets = [c for c in corpus if c['content_status'] == 'CITATION_ONLY']
    print(f'=== deep fetch: {len(targets)} papers we could not reach on the first pass ===\n')

    recovered = 0
    for i, c in enumerate(targets, 1):
        doi = c['doi']
        got = ''
        how = ''

        # 1. every OA location Unpaywall knows (repository copies, working papers)
        for url in all_oa_locations(doi)[:4]:
            t = fetch_text(url)
            if len(t.split()) >= 500:
                got, how = t, f'unpaywall:{urllib.parse.urlparse(url).netloc}'
                break
            time.sleep(0.2)

        # 2. Semantic Scholar's own OA pdf pointer
        if not got:
            pdf = semantic_scholar_pdf(doi)
            time.sleep(0.4)
            if pdf:
                t = fetch_text(pdf)
                if len(t.split()) >= 500:
                    got, how = t, f's2:{urllib.parse.urlparse(pdf).netloc}'

        # 3. at minimum, an abstract
        abstract = c.get('abstract') or ''
        if not got and not abstract:
            abstract = s2_abstract(doi)
            time.sleep(0.4)
            if abstract:
                how = 's2-abstract'

        if got:
            c['fulltext'] = got[:120000]
            c['fulltext_words'] = len(got.split())
            c['content_status'] = 'FULLTEXT'
            recovered += 1
        elif abstract:
            c['abstract'] = abstract
            c['content_status'] = 'ABSTRACT_ONLY'
            recovered += 1

        mark = 'RECOVERED' if c['content_status'] != 'CITATION_ONLY' else 'still paywalled'
        print(f"  [{i:>2}/{len(targets)}] {mark:<15} {c['citations']:>5} cites | "
              f"{c['attribution_short'][:44]:<44} {how}")

    CORPUS.write_text(json.dumps(corpus, indent=1))
    ft = sum(1 for c in corpus if c['content_status'] == 'FULLTEXT')
    ab = sum(1 for c in corpus if c['content_status'] == 'ABSTRACT_ONLY')
    co = sum(1 for c in corpus if c['content_status'] == 'CITATION_ONLY')
    print('\n' + '=' * 70)
    print(f'  RECOVERED THIS PASS : {recovered}/{len(targets)}')
    print(f'  FULLTEXT      : {ft}')
    print(f'  ABSTRACT_ONLY : {ab}')
    print(f'  CITATION_ONLY : {co}   (nameable as literature; never used to ground a claim)')
    print(f'\n  ** USABLE AS EVIDENCE: {ft + ab}/{len(corpus)} **   (was 36; bodhi wins with 33; cellcog has ~98)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
