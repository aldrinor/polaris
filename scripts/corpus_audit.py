#!/usr/bin/env python3
"""CORPUS AUDIT — how many of our 105 "sources" are actually journal articles?

WHY: task 72 says "Ensure the review only cites high-quality, English-language journal articles."
We believed we had 97 journal sources — the same depth as cellcog (the #1 system). GPT-5.6 Sol
checked and said no: many are working papers, institutional reports, blogs, vendor pages, mirrors.
This settles it with the metadata we already hold.

CRITICAL CONSEQUENCE: we were about to make our sources VISIBLE in the prose (in-prose author/venue
attribution, which survives RACE's cleaner while [n] markers do not). If the pool is full of
Goldman Sachs / WEF / Toptal, that transform would ADVERTISE the instruction violation rather than
fix it. Corpus repair MUST precede attribution.

Usage: python scripts/corpus_audit.py [--bib PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

# Domains that are definitively NOT peer-reviewed journal articles.
NON_JOURNAL_DOMAINS = {
    'weforum.org': 'institutional report (WEF)',
    'oecd.org': 'institutional report (OECD)',
    'imf.org': 'institutional report (IMF)',
    'worldbank.org': 'institutional report (World Bank)',
    'ilo.org': 'institutional report (ILO)',
    'bls.gov': 'government statistics',
    'cbo.gov': 'government report',
    'whitehouse.gov': 'government',
    'europa.eu': 'government',
    'goldmansachs.com': 'bank research note',
    'jpmorgan.com': 'bank research note',
    'mckinsey.com': 'consultancy',
    'pwc.com': 'consultancy',
    'deloitte.com': 'consultancy',
    'arxiv.org': 'preprint (not peer-reviewed)',
    'ssrn.com': 'preprint / working paper',
    'nber.org': 'working paper (not peer-reviewed)',
    'iza.org': 'working paper',
    'repec.org': 'working-paper repository',
    'econpapers.repec.org': 'working-paper repository',
    'researchgate.net': 'mirror / repository',
    'semanticscholar.org': 'index / mirror',
    'scholar.google.com': 'search index (NOT a source)',
    'substack.com': 'blog',
    'medium.com': 'blog',
    'toptal.com': 'vendor marketing',
    'linkedin.com': 'social',
    'forbes.com': 'news',
    'nytimes.com': 'news',
    'wsj.com': 'news',
    'bbc.com': 'news',
    'theguardian.com': 'news',
    'cnbc.com': 'news',
    'techcrunch.com': 'news',
    'wikipedia.org': 'encyclopedia',
    'youtube.com': 'video',
    'github.com': 'code',
    'hrexecutive.com': 'trade press',
    'harvard.edu': 'university page (check)',
    'mit.edu': 'university page (check)',
    'stanford.edu': 'university page (check)',
}

# Publisher domains that DO host peer-reviewed journal articles.
JOURNAL_DOMAINS = {
    'aeaweb.org', 'sciencedirect.com', 'springer.com', 'link.springer.com', 'wiley.com',
    'onlinelibrary.wiley.com', 'tandfonline.com', 'sagepub.com', 'journals.sagepub.com',
    'oup.com', 'academic.oup.com', 'cambridge.org', 'jstor.org', 'nature.com', 'science.org',
    'pnas.org', 'plos.org', 'journals.plos.org', 'mdpi.com', 'frontiersin.org', 'ieee.org',
    'acm.org', 'emerald.com', 'informs.org', 'pubmed.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov',
    'doi.org', 'jmir.org', 'bmj.com', 'thelancet.com', 'nejm.org', 'annualreviews.org',
    'uchicago.edu',  # journals.uchicago.edu — JOLE etc.
}

# A venue string that looks like a real journal.
JOURNAL_VENUE_RE = re.compile(
    r'\b(journal|review|quarterly|economica|econometrica|proceedings of the national|'
    r'science|nature|research policy|labour economics|labor economics|management science|'
    r'annals|studies|perspectives|transactions|bulletin|letters)\b', re.I)

# Venue strings that are explicitly NOT journals.
NON_JOURNAL_VENUE_RE = re.compile(
    r'\b(working paper|discussion paper|preprint|arxiv|ssrn|nber|iza|mimeo|white ?paper|'
    r'report|blog|news|magazine|conference|workshop|symposium|proceedings of the \d+|thesis|'
    r'dissertation|book|chapter|press release|brief)\b', re.I)


def domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith('www.') else d
    except Exception:
        return ''


def classify(e: dict) -> tuple[str, str]:
    """Return (verdict, reason). verdict in {JOURNAL, NOT_JOURNAL, UNKNOWN}."""
    venue = (e.get('venue') or '').strip()
    doi = (e.get('doi') or '').strip()
    url = (e.get('url') or '').strip()
    d = domain(url)

    # 1. Hard negative on domain
    for bad, why in NON_JOURNAL_DOMAINS.items():
        if d == bad or d.endswith('.' + bad):
            return 'NOT_JOURNAL', f'{why} [{d}]'
    # 2. Hard negative on venue wording
    if venue and NON_JOURNAL_VENUE_RE.search(venue):
        return 'NOT_JOURNAL', f'venue is not a journal: "{venue}"'
    # 3. Positive: a real journal venue named
    if venue and JOURNAL_VENUE_RE.search(venue):
        return 'JOURNAL', f'venue="{venue}"' + (f' doi={doi}' if doi else ' (NO DOI)')
    # 4. Positive: DOI + publisher domain
    if doi and (d in JOURNAL_DOMAINS or any(d.endswith('.' + j) for j in JOURNAL_DOMAINS)):
        return 'JOURNAL', f'doi={doi} on publisher domain [{d}]' + (f' venue="{venue}"' if venue else ' (NO VENUE NAME)')
    # 5. DOI alone — likely journal but venue unknown => cannot attribute in prose
    if doi:
        return 'UNKNOWN', f'has DOI ({doi}) but no journal venue named [{d or "no url"}]'
    if not venue and not doi:
        return 'NOT_JOURNAL', f'no venue, no DOI [{d or "no url"}]'
    return 'UNKNOWN', f'venue="{venue}" doi="{doi}" [{d}]'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--bib', default='outputs/rank10_sections_compose/bibliography.json')
    ap.add_argument('--out', default='outputs/corpus_audit.json')
    a = ap.parse_args()

    bib = json.loads(Path(a.bib).read_text())
    rows, counts, reasons = [], Counter(), Counter()
    for e in bib:
        v, why = classify(e)
        counts[v] += 1
        if v == 'NOT_JOURNAL':
            reasons[why.split(' [')[0]] += 1
        rows.append({
            'num': e.get('num'), 'verdict': v, 'reason': why,
            'venue': e.get('venue'), 'doi': e.get('doi'), 'year': e.get('year'),
            'authors': e.get('authors'), 'tier': e.get('tier'),
            'title': (e.get('source_title') or '')[:90], 'url': e.get('url'),
            # can we render an in-prose attribution?  needs author + year + venue
            'attributable': bool(e.get('authors') and e.get('year') and e.get('venue')),
        })

    n = len(bib)
    print(f"=== CORPUS AUDIT: {n} bibliography entries ===\n")
    for v in ('JOURNAL', 'UNKNOWN', 'NOT_JOURNAL'):
        print(f"  {v:12s} {counts[v]:3d}  ({100*counts[v]/n:.0f}%)")
    print(f"\n=== WHY entries were rejected ===")
    for why, c in reasons.most_common(15):
        print(f"  {c:3d}  {why}")

    att = sum(1 for r in rows if r['attributable'])
    att_j = sum(1 for r in rows if r['attributable'] and r['verdict'] == 'JOURNAL')
    print(f"\n=== IN-PROSE ATTRIBUTION READINESS (needs authors + year + venue) ===")
    print(f"  attributable at all      : {att}/{n}")
    print(f"  attributable AND JOURNAL : {att_j}/{n}   <-- the sources we could safely NAME in the prose")

    print(f"\n=== THE NON-JOURNAL SOURCES WE WOULD HAVE ADVERTISED (first 12) ===")
    for r in [r for r in rows if r['verdict'] == 'NOT_JOURNAL'][:12]:
        au = (r['authors'] or ['?'])[0] if r['authors'] else '?'
        print(f"  [{r['num']:>3}] {au:<22.22} {r['reason'][:62]:<62} {r['title'][:40]}")

    Path(a.out).write_text(json.dumps({'counts': dict(counts), 'rows': rows}, indent=1))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
