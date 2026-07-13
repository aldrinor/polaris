#!/usr/bin/env python3
"""ATTACK 2 — ABSTRACT RENDERED AS FULL TEXT.

Feed a 535-word abstract to every component that assigns a content label. Does anything call it
FULLTEXT? It did tonight, twice. Frey & Osborne — 548 words — is the paper the synthesis leaned on.

We feed the REAL Frey & Osborne bytes off the live corpus, plus a synthetic 535-word abstract.
"""
from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

CORPUS = json.loads((ROOT / 'outputs' / 'journal_corpus_content.json').read_text())

# ---- the REAL bytes: whatever we actually hold for Frey & Osborne ----------------------------
frey = next(c for c in CORPUS if (c.get('authors') or [''])[0] == 'Frey')
frey_text = (frey.get('fulltext') or frey.get('abstract') or '')
print('=' * 96)
print('ATTACK 2 — DOES A 535-WORD ABSTRACT GET CALLED "FULLTEXT"?')
print('=' * 96)
print(f"\n  Frey & Osborne (2017), {frey.get('venue')}")
print(f"  bytes we hold      : {len(frey_text.split())} words")
print(f"  corpus label       : content_status={frey.get('content_status')}")
print(f"  first 130 chars    : {frey_text[:130]!r}")

# a synthetic 535-word ABSTRACT (real prose, no web chrome — the hardest case for a chrome detector)
ABSTRACT_535 = (
    'We examine how susceptible jobs are to computerisation. To assess this, we begin by implementing '
    'a novel methodology to estimate the probability of computerisation for 702 detailed occupations, '
    'using a Gaussian process classifier. Based on these estimates, we examine expected impacts of '
    'future computerisation on US labour market outcomes, with the primary objective of analysing the '
    'number of jobs at risk and the relationship between an occupation, its probability of '
    'computerisation, wages and educational attainment. According to our estimates, about 47 percent '
    'of total US employment is at risk. We further provide evidence that wages and educational '
    'attainment exhibit a strong negative relationship with an occupation probability of '
    'computerisation. ') * 6      # ~535 words of GENUINE ABSTRACT PROSE, zero web furniture

print(f'\n  synthetic abstract : {len(ABSTRACT_535.split())} words of genuine abstract prose, no web chrome')

# ---------------------------------------------------------------------------- 1. deep_fetch
print('\n--- 1. deep_fetch.py: what label does it write for 535 words? ---')
import deep_fetch


class FakeResp:
    def __init__(self, body):
        self._b = body.encode()
        self.headers = {'Content-Type': 'text/plain'}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    if 'unpaywall' in url:
        return FakeResp(json.dumps({'oa_locations': [{'url': 'https://repo.example/abs'}]}))
    return FakeResp(ABSTRACT_535)          # every fetch returns the 535-word ABSTRACT


tmp = Path(tempfile.mkdtemp())
p = tmp / 'c.json'
row = dict(frey, content_status='CITATION_ONLY', citations=9999,
           attribution_short='Frey and Osborne (2017), TFSC')
row.pop('fulltext', None)
row.pop('abstract', None)
p.write_text(json.dumps([row]))
deep_fetch.CORPUS = p
_real = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
try:
    deep_fetch.main()
finally:
    urllib.request.urlopen = _real
got = json.loads(p.read_text())[0]
verdict1 = got['content_status']
print(f"\n  >>> deep_fetch labelled a {len(ABSTRACT_535.split())}-word ABSTRACT as: {verdict1}")
print(f"  >>> ATTACK {'SUCCEEDS — an abstract is now FULLTEXT' if verdict1 == 'FULLTEXT' else 'repelled'}")

# ---------------------------------------------------------------------------- 2. corpus_truth
print('\n--- 2. corpus_truth.py: does it re-derive the label from content? ---')
import corpus_truth

t = corpus_truth.truth({'fulltext': ABSTRACT_535, 'abstract': ''})
print(f"  corpus_truth.truth() on the same 535 words -> {t}")

t_frey = corpus_truth.truth(frey)
print(f"  corpus_truth.truth() on the REAL Frey bytes -> {t_frey}")

# ---------------------------------------------------------------------------- 3. provenance
print('\n--- 3. provenance.py profile(): does it see through it? ---')
from provenance import Work, profile

w = Work(id='w', title=frey.get('title', ''), authors=frey.get('authors', []),
         year=frey.get('year'), venue=frey.get('venue'), doi=frey.get('doi'))
pr = profile(ABSTRACT_535, w)
print(f"  synthetic 535w abstract -> artifact_kind={pr['artifact_kind']!r} complete={pr['complete']}")
print(f"                             because: {pr['incomplete_because']}")
pr2 = profile(frey_text, w)
print(f"  REAL Frey bytes ({len(frey_text.split())}w) -> artifact_kind={pr2['artifact_kind']!r} complete={pr2['complete']}")
print(f"                             basis: {pr2['artifact_kind_basis'][:90]}")

# ---------------------------------------------------------------------------- 4. THE MINER
print('\n--- 4. evidence_miner: is the 548-word landing page ADMITTED as a source? ---')
import evidence_miner

usable = [c for c in CORPUS if c.get('content_status') != 'CITATION_ONLY'
          and ((c.get('fulltext') or '').strip() or (c.get('abstract') or '').strip())]
frey_in = any((c.get('authors') or [''])[0] == 'Frey' for c in usable)
print(f"  the miner's `usable` filter (evidence_miner.py:1580) admits Frey & Osborne? {frey_in}")
print(f"  ...and it decides that on content_status alone: {frey.get('content_status')!r}")
cards = json.loads((ROOT / 'outputs' / 'evidence_cards.json').read_text())
frey_cards = [c for c in cards if 'Frey' in (c.get('source') or '')]
print(f"  evidence cards ALREADY ON DISK sourced to Frey & Osborne: {len(frey_cards)}")
for c in frey_cards:
    inside = (c['span'][:60].lower() in frey_text.lower())
    print(f"     span in the 548-byte landing page? {inside}   {c['span'][:66]!r}")
