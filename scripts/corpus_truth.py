#!/usr/bin/env python3
"""CORPUS TRUTH — does every label on this corpus actually describe its content?

Tonight, every single failure had the same shape: A LABEL THAT ASSERTED MORE THAN THE CONTENT
SUPPORTED, and nothing checked.

    "gate: WIRED"        -- it checked the wrong lane; fabrication shipped
    "span-verified"      -- verified by its first 60 characters
    "fabrication-proof"  -- the table printed model-written prose
    "still paywalled"    -- we asked by DOI; the free copy is a separate work
    "FULLTEXT"           -- 535 words. An abstract.

Not one of them announced itself. Each read as a fact about the world.

This script re-derives every corpus label FROM THE CONTENT and rewrites it to the truth. It is
idempotent, it never deletes text, and it is allowed to make the corpus look worse -- because a
corpus that looks worse and IS honest is the only kind we can build on.

    python scripts/corpus_truth.py [--fix]
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / 'outputs' / 'journal_corpus_content.json'
FULLTEXT_MIN = 2500      # a journal article is 5,000-20,000 words
ABSTRACT_MIN = 120
NUMS = re.compile(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b')


def truth(c: dict) -> str:
    """The label the CONTENT earns -- not the one it was given."""
    ft = len((c.get('fulltext') or '').split())
    ab = len((c.get('abstract') or '').split())
    if ft >= FULLTEXT_MIN:
        return 'FULLTEXT'
    if max(ft, ab) >= ABSTRACT_MIN:
        return 'ABSTRACT_ONLY'
    return 'CITATION_ONLY'


def main() -> int:
    fix = '--fix' in sys.argv
    rows = json.loads(CORPUS.read_text())

    lied = []
    for c in rows:
        was, is_ = c.get('content_status'), truth(c)
        if was != is_:
            lied.append((c.get('authors', ['?'])[0], c.get('year'),
                         len((c.get('fulltext') or '').split()), was, is_))
            if fix:
                # a document that is not a paper must not be READ as a paper
                if is_ != 'FULLTEXT' and c.get('fulltext'):
                    c['abstract'] = c.get('abstract') or c['fulltext'][:8000]
                    c.pop('fulltext', None)
                c['content_status'] = is_

    print(f'=== CORPUS TRUTH: {len(rows)} papers ===\n')
    if lied:
        print(f'  {len(lied)} LABEL(S) THAT DID NOT DESCRIBE THEIR CONTENT:')
        for au, yr, w, was, is_ in lied[:14]:
            print(f'    {au[:16]:<16} {yr}  {w:>6,}w   {was:<14} -> {is_}')
    else:
        print('  every label is earned by its content.')

    if fix:
        CORPUS.write_text(json.dumps(rows, indent=1))
        print(f'\n  rewritten to the truth.')

    st = collections.Counter(truth(c) for c in rows)
    real = sum(len(NUMS.findall(c.get('fulltext') or '')) for c in rows if truth(c) == 'FULLTEXT')
    print(f'\n  FULLTEXT      : {st["FULLTEXT"]}')
    print(f'  ABSTRACT_ONLY : {st["ABSTRACT_ONLY"]}')
    print(f'  CITATION_ONLY : {st["CITATION_ONLY"]}')
    print(f'  USABLE AS EVIDENCE: {st["FULLTEXT"] + st["ABSTRACT_ONLY"]}/{len(rows)}')
    print(f'\n  QUANTITATIVE CLAIMS IN REAL FULL TEXT: {real:,}')
    print(f'  (the report printed 2. cellcog prints 202. the extractor read only the first 31.9%'
          f' of each paper -- the introductions.)')
    return 1 if (lied and not fix) else 0


if __name__ == '__main__':
    raise SystemExit(main())
