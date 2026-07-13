#!/usr/bin/env python3
"""MERGE CORPUS — because two fetchers writing one file means the last writer wins, silently.

deep_fetch and wp_fetch both load journal_corpus_content.json, both spend half an hour improving it,
and both write it back whole. wp_fetch started at 19:20:54 holding the corpus as it was; deep_fetch
finished and wrote NINE newly-recovered fulltext papers at 19:23:11. wp_fetch has never seen them and
will flatten all nine the moment it finishes -- no error, no warning, just nine papers quietly back to
CITATION_ONLY and an extractor that skips them.

This merges by DOI and keeps, for each paper, THE VERSION WITH THE MOST TEXT. Both fetchers' work
survives, and running it twice changes nothing.

Usage: python scripts/merge_corpus.py <base.json> <other.json> [<other2.json> ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CORPUS = Path('outputs/journal_corpus_content.json')
NUMS = re.compile(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b')
RANK = {'FULLTEXT': 3, 'ABSTRACT_ONLY': 2, 'CITATION_ONLY': 1, None: 0}


def textlen(c: dict) -> int:
    return len((c.get('fulltext') or c.get('abstract') or '').split())


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if len(paths) < 2:
        print(__doc__)
        return 2

    best: dict[str, dict] = {}
    for p in paths:
        if not p.exists():
            print(f'  skip (missing): {p}')
            continue
        rows = json.loads(p.read_text())
        kept = 0
        for c in rows:
            k = c.get('doi') or c.get('title', '')[:80]
            cur = best.get(k)
            # the winner is the one carrying the most actual text -- status is a label, text is the asset
            if cur is None or (textlen(c), RANK.get(c.get('content_status'))) > (textlen(cur), RANK.get(cur.get('content_status'))):
                best[k] = c
                kept += 1
        print(f'  {p.name:<44} {len(rows):>3} papers, {kept:>3} became the best copy')

    out = list(best.values())
    CORPUS.write_text(json.dumps(out, indent=1))

    ft = sum(1 for c in out if c.get('content_status') == 'FULLTEXT')
    ab = sum(1 for c in out if c.get('content_status') == 'ABSTRACT_ONLY')
    co = sum(1 for c in out if c.get('content_status') == 'CITATION_ONLY')
    nums = sum(len(NUMS.findall(c.get('fulltext') or '')) for c in out)
    print(f'\n=== MERGED CORPUS: {len(out)} papers ===')
    print(f'    FULLTEXT      : {ft}')
    print(f'    ABSTRACT_ONLY : {ab}')
    print(f'    CITATION_ONLY : {co}')
    print(f'    USABLE AS EVIDENCE: {ft + ab}/{len(out)}   (bodhi wins with 33; cellcog has ~98)')
    print(f'    QUANTITATIVE CLAIMS AVAILABLE TO THE EXTRACTOR: {nums:,}   (was 1,825; we used 2)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
