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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acquisition import held_content_class                      # noqa: E402
from event_ledger import C_ABSTRACT, C_FULLTEXT, LEGACY_STATUS  # noqa: E402

CORPUS = Path(__file__).resolve().parents[1] / 'outputs' / 'journal_corpus_content.json'
NUMS = re.compile(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b')

# ─────────────────────────────────────────────────────────────────────────────────────────────────
# THERE WAS A `FULLTEXT_MIN = 2500` HERE, AND AN `ABSTRACT_MIN = 120`. They are deleted, and this is
# their headstone.
#
# THE THIRD ONE. `event_ledger.py` deleted its own `FULLTEXT_MIN = 2500` (its headstone is still in
# that file); `provenance.py`'s registry uses a scholarly floor of 1,200 and NO FLOOR AT ALL for a
# judicial opinion, a statute section or a trial-registry record, which are complete at any length.
# And this file — which `run_ladder.sh` and `post_fetch.sh` BOTH run IMMEDIATELY AFTER the merge, with
# `--fix` — held a third number, knew about neither of the others, and OVERWROTE their answer.
#
# It was not a redundant check. It was a LOUDER one, and it ran LAST:
#
#     * a 105-word judicial opinion is COMPLETE (registry: stub_floor=None). This file called it
#       CITATION_ONLY and then POPPED ITS TEXT.
#     * a 2,600-word aeaweb cookie banner clears 2,500. This file called it FULLTEXT.
#
# Three modules holding three different numbers is not three checks. It is no rule at all: which
# document a card could cite depended on which module happened to look at it last, and this one always
# did. So completeness is not decided here. It is READ FROM THE ONE REDUCER, over the bytes.
# ─────────────────────────────────────────────────────────────────────────────────────────────────


def truth(c: dict) -> str:
    """The label the CONTENT earns -- not the one it was given, and not one this file invented.

    Delegates to `event_ledger.derive_content_profile` (through `acquisition.held_content_class`),
    which is the SAME reducer `merge_corpus` and the fetchers' target selectors use, driven by the
    SAME registry in `provenance.KIND_PROFILE`. There is now exactly one answer in the codebase to
    "is this document complete", and this file no longer has a second opinion.
    """
    cls, _info = held_content_class(c)
    if cls == 'CITATION_ONLY' and len((c.get('abstract') or '').split()) >= 120:
        # We hold no document, but we DO hold the bibliography's abstract. That is real, quotable text
        # — it is simply not the paper. (The floor is the registry's SCHOLARLY_ABSTRACT_FLOOR.)
        return 'ABSTRACT_ONLY'
    return LEGACY_STATUS.get(cls, 'CITATION_ONLY')


def main() -> int:
    fix = '--fix' in sys.argv
    rows = json.loads(CORPUS.read_text())

    lied = []
    for c in rows:
        cls, info = held_content_class(c)
        was, is_ = c.get('content_status'), truth(c)
        if was != is_:
            lied.append((c.get('authors', ['?'])[0], c.get('year'),
                         len((c.get('fulltext') or '').split()), was, is_))
        if fix:
            # ── A DOCUMENT THAT IS NOT A PAPER MUST NOT BE READ AS ONE — UNDER ANY FIELD NAME. ────
            #
            # This block used to say:
            #
            #     if is_ != 'FULLTEXT' and c.get('fulltext'):
            #         c['abstract'] = c.get('abstract') or c['fulltext'][:8000]   # <-- HERE
            #         c.pop('fulltext', None)
            #
            # which MOVED THE COOKIE BANNER INTO THE `abstract` FIELD. On this pass the row is
            # CITATION_ONLY and the miner skips it, so it looks harmless. IT IS NOT, BECAUSE THIS
            # SCRIPT IS IDEMPOTENT AND GETS RUN AGAIN: on the second run the reducer finds no
            # `fulltext`, sees 535 words of banner sitting in `abstract`, and promotes the row to
            # ABSTRACT_ONLY — which PASSES the miner's `!= 'CITATION_ONLY'` test. The banner becomes
            # evidence, and it laundered itself through the FIX, in two hops, using nothing but this
            # script's own idempotency.
            #
            # So bytes that are not a document go to a field NOTHING READS. They are not deleted —
            # nothing here is ever deleted, and merge_corpus has them blobbed and hashed besides.
            if cls != C_FULLTEXT and (c.get('fulltext') or '').strip():
                if cls == C_ABSTRACT and not (c.get('abstract') or '').strip():
                    c['abstract'] = c['fulltext'][:8000]     # a GENUINE scholarly fragment. It is one.
                else:
                    c['withheld_text'] = c['fulltext']       # a banner / a glyph dump / a stranger
                    c['withheld_because'] = str(info.get('reason', ''))[:200]
                c.pop('fulltext', None)
                c['fulltext_words'] = 0
            c['content_status'] = is_
            c['content_class'] = cls
            c['content_status_derived_by'] = 'event_ledger.derive_content_profile'

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
