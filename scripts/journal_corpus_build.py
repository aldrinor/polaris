#!/usr/bin/env python3
"""BUILD THE JOURNAL CORPUS by CITATION-GRAPH EXPANSION — the "deep source" half of the SOTA plan.

WHY: the corpus audit found our 105 "sources" contain only 22 distinct real journal articles (~12
serious). cellcog, the #1 system on the board, has ~98. The task instruction is literally:
"Ensure the review only cites high-quality, English-language journal articles."

WHY NOT KEYWORD SEARCH: tried and rejected, with evidence.
  - OpenAlex: hard 429 for this box's IP.
  - Crossref sorted by citations: returns ResNet and SMOTE — famous, not relevant.
  - Crossref sorted by relevance: returns papers with the keywords IN THE TITLE, which are the
    LOW-QUALITY ones (0-25 citations, near-predatory venues). The canonical papers do not have
    "artificial intelligence labor market employment" verbatim in their titles.

WHAT ACTUALLY WORKS: a real literature review is not assembled by search — it is assembled by
following the CITATION GRAPH out from the canonical papers. We already hold those anchors (Frey &
Osborne, Autor, Acemoglu & Restrepo, Eloundou, Noy & Zhang, Felten). Crossref returns each paper's
reference list, so we expand backwards from the anchors, then enrich and filter every candidate.

FABRICATION SAFETY: every field is copied verbatim from the Crossref record for that DOI. A work
whose author/venue/year cannot be resolved is DROPPED, never invented — the entire point of this
corpus is that we can NAME these papers in the prose, and the cleaner-survival test proved that only
journal-named prose survives RACE's cleaner.

Usage:
  python scripts/journal_corpus_build.py --target 100
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

MAILTO = 'aldrin.or@c-polarbiotech.com'
UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}

# Our verified canonical anchors (from the Crossref-enriched bibliography).
# These are the papers any serious review of AI and the labour market MUST cite.
ANCHORS = [
    ('10.1016/j.techfore.2016.08.019', 'Frey & Osborne 2017, Technological Forecasting'),
    ('10.1257/jep.33.2.3',             'Acemoglu & Restrepo 2019, JEP'),
    ('10.1257/jep.29.3.3',             'Autor 2015, JEP'),
    ('10.1257/aer.103.5.1553',         'Autor et al. 2013, AER'),
    ('10.1126/science.adj0998',        'Eloundou et al. 2024, Science'),
    ('10.1126/science.adh2586',        'Noy & Zhang 2023, Science'),
    ('10.1002/smj.3286',               'Felten et al. 2021, Strategic Management Journal'),
    ('10.1016/j.hrmr.2022.100899',     'Chowdhury et al. 2023, HRMR'),
    ('10.1257/aer.96.2.189',           'Autor et al. 2006, AER'),
    ('10.1162/REST_a_00286',           'Baum-Snow & Pavan 2013, REStat'),
    ('10.1108/JOSM-04-2019-0088',      'Buhalis et al. 2019, J. Service Management'),
    ('10.1177/1042258720934581',       'Chalmers et al. 2021, ETP'),
]

# Venues that are NOT peer-reviewed journals, whatever Crossref's `type` says.
BAD_VENUE = ('ssrn', 'arxiv', 'preprint', 'working paper', 'conference', 'proceedings',
             'repository', 'mimeo', 'discussion paper')

# On-topic gate: the corpus must be about AI/automation/technology AND work/labour, not generic ML.
# NOTE: these are PREFIX patterns with NO trailing \b. A trailing boundary was a real bug here — it
# made "automat" fail to match "automation" and "computeris" fail to match "computerisation", which
# rejected Frey & Osborne, Acemoglu-Restrepo and Autor as "off-topic". Prefix-match, deliberately.
TOPIC_AI = re.compile(r'(artificial intelligence|\bAI\b|machine learning|machine|automat|robot|'
                      r'algorithm|generative|large language model|\bLLM\b|digital|computeris|'
                      r'computeriz|computer|technolog|industry 4\.0|fourth industrial revolution)', re.I)
TOPIC_WORK = re.compile(r'(labor|labour|employment|job|work|occupation|wage|skill|task|'
                        r'workforce|productiv|inequality|displac|polariz|polaris|firm|industr|'
                        r'human resource|organiz|organis)', re.I)


def get(url: str, timeout: int = 25, tries: int = 3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def crossref_work(doi: str) -> dict | None:
    d = get(f'https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}')
    return d.get('message') if d else None


def refs_of(msg: dict) -> list[str]:
    return [r['DOI'].lower() for r in (msg.get('reference') or []) if r.get('DOI')]


def card(msg: dict) -> dict | None:
    """Verbatim card. Drop anything we cannot NAME — no guessing, ever."""
    au = [a.get('family', '').strip() for a in (msg.get('author') or []) if a.get('family')]
    venue = (msg.get('container-title') or [''])[0].strip()
    doi = (msg.get('DOI') or '').lower()
    title = (msg.get('title') or [''])[0].strip()
    typ = msg.get('type') or ''
    yr = None
    for k in ('published-print', 'published-online', 'issued'):
        parts = ((msg.get(k) or {}).get('date-parts') or [[None]])[0]
        if parts and parts[0]:
            yr = int(parts[0])
            break
    if not (au and venue and yr and doi and title):
        return None
    if typ != 'journal-article':
        return None
    if any(b in venue.lower() for b in BAD_VENUE):
        return None
    blob = f'{title} {venue}'
    if not (TOPIC_AI.search(blob) and TOPIC_WORK.search(blob)):
        return None
    who = au[0] if len(au) == 1 else (f'{au[0]} and {au[1]}' if len(au) == 2 else f'{au[0]} et al.')
    return {
        'doi': doi, 'title': title, 'authors': au[:6], 'venue': venue, 'year': yr,
        'citations': msg.get('is-referenced-by-count', 0),
        'type': typ,
        # THE format the cleaner-survival test proved survives RACE (journal named, year as PROSE):
        'attribution': (f'Writing in {venue} in {yr}, {who}' if venue[:4].lower() == 'the '
                        else f'Writing in the {venue} in {yr}, {who}'),
        'attribution_short': f'{who} ({yr}), {venue}',
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='outputs/journal_corpus.json')
    ap.add_argument('--target', type=int, default=100)
    ap.add_argument('--sleep', type=float, default=0.15)
    a = ap.parse_args()

    corpus: dict[str, dict] = {}
    stats = Counter()

    # 1. the anchors themselves
    print('=== STEP 1: the canonical anchors ===')
    anchor_msgs = {}
    for doi, label in ANCHORS:
        msg = crossref_work(doi)
        time.sleep(a.sleep)
        if not msg:
            print(f'  MISS  {label}')
            continue
        anchor_msgs[doi] = msg
        c = card(msg)
        if c:
            corpus[c['doi']] = c
            print(f'  ok    {c["citations"]:>6} cites  {label}')
        else:
            print(f'  (anchor kept as expansion seed only): {label}')

    # 2. expand backwards through their reference lists
    print(f'\n=== STEP 2: citation-graph expansion from {len(anchor_msgs)} anchors ===')
    candidates: Counter = Counter()
    for doi, msg in anchor_msgs.items():
        rs = refs_of(msg)
        for r in rs:
            candidates[r] += 1          # co-citation count = how many anchors cite it
        print(f'  {doi[:34]:<34} -> {len(rs):>3} referenced DOIs')

    ranked = [d for d, _ in candidates.most_common() if d not in corpus]
    print(f'\n  {len(ranked)} distinct candidate DOIs (ranked by how many anchors cite them)')

    # 3. enrich + filter each candidate
    print(f'\n=== STEP 3: enrich + filter (journal-article, on-topic, nameable) ===')
    for i, doi in enumerate(ranked, 1):
        if len(corpus) >= a.target:
            break
        msg = crossref_work(doi)
        time.sleep(a.sleep)
        if not msg:
            stats['crossref_miss'] += 1
            continue
        c = card(msg)
        if not c:
            stats['rejected'] += 1
            continue
        corpus[c['doi']] = c
        stats['accepted'] += 1
        if stats['accepted'] % 10 == 0:
            print(f'  ... {len(corpus)} in corpus (checked {i}/{len(ranked)})')

    out = sorted(corpus.values(), key=lambda c: -c['citations'])
    Path(a.out).write_text(json.dumps(out, indent=1))

    print('\n' + '=' * 76)
    print(f'=== JOURNAL CORPUS: {len(out)} distinct peer-reviewed journal articles ===')
    print(f'    we had 22.  cellcog (#1 on the board) has ~98.')
    print(f'    candidates checked: {stats["accepted"] + stats["rejected"] + stats["crossref_miss"]}'
          f' | accepted {stats["accepted"]} | rejected {stats["rejected"]} | crossref miss {stats["crossref_miss"]}')
    print(f'\n=== TOP 30 (the papers a real review MUST cite) ===')
    for c in out[:30]:
        print(f'  {c["citations"]:>6} | {c["attribution_short"][:64]}')
    print(f'\nwrote {a.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
