#!/usr/bin/env python3
"""MERGE CORPUS — union of EVENT STREAMS and IMMUTABLE MANIFESTATIONS. There is no winner.

WHAT THIS FILE USED TO BE
─────────────────────────────────────────────────────────────────────────────────────────────────
Two fetchers loaded one JSON file, both improved it, and both wrote it back whole — so the last writer
silently flattened the other's work. This script was the patch for that, and it merged by DOI keeping,
for each paper, THE VERSION WITH THE MOST TEXT:

    RANK = {'FULLTEXT': 3, 'ABSTRACT_ONLY': 2, 'CITATION_ONLY': 1, None: 0}
    if (textlen(c), RANK.get(c['content_status'])) > (textlen(cur), RANK.get(cur['content_status'])):
        best[k] = c                                            # ...and the loser was DROPPED

Both of those keys are the disease.

  TEXT LENGTH does not distinguish a paper from a cookie banner. The aeaweb.org landing page for
  Autor (2015) is 535 words; the ORA landing page for Frey & Osborne is 548. Either one BEATS a real
  400-word abstract on length, and this line would hand it the row.

  CLAIMED STATUS is the label the FAILING FETCHER WROTE ABOUT ITSELF. Ranking by it means asking the
  component whether it succeeded and believing the answer — which is how `FULLTEXT` came to sit on
  535 words of cookie banner in the first place. The merge did not just fail to catch that lie; it
  USED IT AS THE TIEBREAK.

  And `best[k] = c` DELETED the loser. Two fetchers that retrieved two DIFFERENT DOCUMENTS for one
  DOI — which is exactly what happened, an NBER working paper and a publisher landing page — had one
  of them thrown away, unrecorded, on the strength of a word count.

WHAT IT IS NOW
─────────────────────────────────────────────────────────────────────────────────────────────────
An append-only log admits exactly one merge: UNION. A content-addressed blob admits exactly one
merge: UNION. So:

  1. EVENT STREAMS are unioned and re-sequenced. An observation is not a slot to be overwritten.
  2. Legacy bytes sitting on corpus rows are INGESTED as manifestations — hashed, blobbed, profiled.
     NOTHING IS DELETED. If two files hold two different documents for one DOI, we now hold BOTH,
     forever, and the graph carries both.
  3. The row's `fulltext` is a DERIVED VIEW over the manifestations, chosen by the SHARED REDUCER —
     the complete, finding-bearing document, and among those the most AUTHORITATIVE VERSION (peer
     review changes numbers). Length breaks ties only between documents already agreed to be the same
     kind of thing. Nothing is discarded to build that view; it is a pointer, and it is re-derivable.

Usage: python scripts/merge_corpus.py <base.json> <other.json> [<other2.json> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import (  # noqa: E402
    LEDGER_PATH, Acquirer, BlobStore, classify_manifestation, manifestations_of, merge_ledgers,
    open_ledger, select_evidence,
)
from event_ledger import (  # noqa: E402
    C_ABSTRACT, C_FULLTEXT, LEGACY_STATUS, derive_route_status, derive_semantic_binding,
    record_content_profile,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'


def unit_of(row: dict) -> str:
    return row.get('doi') or (row.get('title') or '')[:80]


def ingest_legacy_bytes(acq: Acquirer, ledger, row: dict, source_file: str) -> int:
    """PRESERVE THE ACQUIRED BYTES. Text that is on a corpus row but has no manifestation behind it is
    still text WE HOLD — it just has no provenance yet. Give it one; never drop it.

    This is the step that makes the union safe. Without it, "merge by manifestation" would silently
    discard every byte fetched before the ledger existed — which would be this script's original sin
    (deleting the loser) committed again, at ten times the scale, in the fix for it.
    """
    unit = unit_of(row)
    have = {m.get('text_sha256') for m in manifestations_of(ledger, unit)}
    n = 0
    #: WHICH COLUMN the bytes came from. Note the ledger vocabulary: `body`, never `fulltext`.
    #: The conclusion guard REFUSED `text_field='fulltext'` — and it was right to. "Full text" is a
    #: VERDICT about completeness, and it is the one the reducer exists to reach; a component that
    #: writes the word, even as a column name, has stated the conclusion in the log. `body` says the
    #: same true thing (these bytes are the document body) and asserts nothing about whether they are
    #: all of it. The graph's own `text_field` vocabulary is unchanged — provenance_construct maps it.
    for field, column in (('body', 'fulltext'), ('abstract', 'abstract')):
        text = (row.get(column) or '').strip()
        if not text:
            continue
        import hashlib
        h = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if h in have:
            continue                       # content-addressed: we already hold exactly these bytes
        acq.record_manifestation(
            unit, locator=row.get('oa_url') or '', raw=text.encode('utf-8'), text=text,
            adapter=f'corpus:{source_file}',
            requested_title=row.get('title') or '',
            requested_authors=list(row.get('authors') or []),
            requested_doi=row.get('doi') or '',
            requested_venue=row.get('venue') or '',
            requested_year=row.get('year'),
            source_type=str(row.get('type') or 'journal-article'),
            extraction_method='corpus_ingest', source_field=field,
            # The locator is the row's `oa_url`, which for the rows wp_fetch touched points at the
            # PUBLISHER while the bytes are an NBER working paper. We record it and let the graph
            # contradict it in the open, rather than adopting it silently.
            locator_recorded_by='corpus_row_not_fetcher')
        have.add(h)
        n += 1
    return n


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:] if not p.startswith('-')]
    if len(paths) < 2:
        print(__doc__)
        return 2

    ledger_path = Path(LEDGER_PATH)

    # ── 1. UNION THE EVENT STREAMS. ───────────────────────────────────────────────────────────────
    # A ledger beside each input (`<corpus>.events.jsonl`) is merged in too, so a fetcher that ran
    # against its own log does not lose its history to the one that ran against the main log.
    side = [p.with_suffix('.events.jsonl') for p in paths]
    n_ev, dupes = merge_ledgers([ledger_path] + [s for s in side if s.exists()], ledger_path)
    print(f'  event streams merged  : {n_ev:,} events ({dupes} duplicate observations dropped)')

    ledger = open_ledger(ledger_path)
    blobs = BlobStore()
    acq = Acquirer('merge_corpus', ledger=ledger, blobs=blobs)

    # ── 2. UNION THE ROWS, AND INGEST EVERY BYTE ANY OF THEM CARRIES. ─────────────────────────────
    rows: dict[str, dict] = {}
    ingested = 0
    for p in paths:
        if not p.exists():
            print(f'  skip (missing): {p}')
            continue
        data = json.loads(p.read_text())
        for c in data:
            k = unit_of(c)
            ingested += ingest_legacy_bytes(acq, ledger, c, p.name)
            if k not in rows:
                rows[k] = dict(c)
            else:
                # Merge the row's METADATA (citations, venue, authors...). The TEXT is not merged here
                # and is not fought over here: it lives in the manifestations, and the view is derived
                # below. There is nothing left for the last writer to win.
                for kk, vv in c.items():
                    if kk in ('fulltext', 'abstract', 'content_status', 'fulltext_source',
                              'fulltext_words', 'oa_url'):
                        continue
                    if vv not in (None, '', [], {}) and not rows[k].get(kk):
                        rows[k][kk] = vv
        print(f'  {p.name:<44} {len(data):>3} rows')
    print(f'  legacy bytes ingested : {ingested} new manifestation(s) — nothing was dropped')

    # ── 3. DERIVE THE VIEW. NO WINNER IS CHOSEN BY LENGTH, AND NO LOSER IS DELETED. ───────────────
    out = []
    stats: dict[str, int] = {}
    multi = 0
    for k, row in rows.items():
        unit = unit_of(row)
        manifs = manifestations_of(ledger, unit)
        if len(manifs) > 1:
            multi += 1

        # every set of bytes we hold for this work, kept, with what the shared reducer makes of it
        row['manifestations'] = [
            dict(text_sha256=c['manifestation'].get('text_sha256', ''),
                 blob_id=c['manifestation'].get('blob_id', ''),
                 locator=c['manifestation'].get('locator', ''),
                 adapter=c['manifestation'].get('adapter', ''),
                 n_words=c['readable_words'],
                 artifact_kind=c['artifact_kind'],
                 expression_kind=c['expression_kind'],
                 content_class=c['content_class'])
            for c in (classify_manifestation(m, blobs) for m in manifs)]

        # THE LABEL, DERIVED. `record_content_profile` runs the reducer over the observations and
        # MINUTES the verdict in the ledger as an audit artifact that no reducer will ever read back.
        # This script may do that because it IS a reducer. A fetcher may not, and now cannot: there is
        # no API in `acquisition` that takes a status.
        cls, info = record_content_profile(ledger, unit)
        binding, _ = derive_semantic_binding(ledger.events(unit))
        route = derive_route_status(ledger.events(unit))
        best = select_evidence(ledger, unit, blobs)

        # ---- THE ROW IS A VIEW. Only bytes the reducer calls a DOCUMENT are presented as one. ------
        if cls == C_FULLTEXT and best is not None:
            row['fulltext'] = best['text'][:120000]
            row['fulltext_words'] = len(row['fulltext'].split())
            row['oa_url'] = best['manifestation'].get('locator') or row.get('oa_url') or ''
            row['fulltext_manifestation'] = best['manifestation'].get('text_sha256', '')[:12]
            row['fulltext_selected_because'] = best['basis'][:200]
        else:
            # These bytes are NOT the paper. THEY ARE NOT DELETED — they are in the blob store,
            # addressed by their own hash, and every one of them is a node in the provenance graph.
            # They are simply not handed to the miner under the name `fulltext`, because the miner
            # reads that field as "the words of this paper" and they are not.
            if (row.get('fulltext') or '').strip():
                row['fulltext_withheld_because'] = str(info.get('reason', ''))[:200]
                row['fulltext_withheld_manifestation'] = (
                    best['manifestation'].get('text_sha256', '')[:12] if best else '')
                row.pop('fulltext', None)
                row['fulltext_words'] = 0
            if cls == C_ABSTRACT and best is not None and not (row.get('abstract') or '').strip():
                row['abstract'] = best['text'][:8000]

        # `fulltext_source` NAMED THE SCRIPT THAT RAN. It agreed with the truth zero times out of six.
        # It is not corrected here — IT IS REMOVED, and replaced by what the bytes' own header says.
        row.pop('fulltext_source', None)

        # THE COARSE LABEL the miner and composer contract on, PROJECTED from the derived class in the
        # one place that knows the mapping — and projected SAFE: a cookie banner is not an abstract.
        row['content_status'] = LEGACY_STATUS[cls]
        row['content_class'] = cls                        # ...and the precise class is right beside it
        row['content_status_basis'] = str(info.get('reason', ''))[:300]
        row['content_status_derived_by'] = 'event_ledger.derive_content_profile'
        row['artifact_kind'] = info.get('artifact_kind')
        row['semantic_binding'] = binding               # SAME_WORK / VERSION_OF_PREPRINT / ...
        row['route_state'] = route.state
        stats[cls] = stats.get(cls, 0) + 1
        out.append(row)

    CORPUS.write_text(json.dumps(out, indent=1))

    print(f'\n=== MERGED CORPUS: {len(out)} papers ===')
    for k in sorted(stats, key=lambda x: -stats[x]):
        print(f'    {k:<22}{stats[k]:>4}')
    print(f'\n    works holding MORE THAN ONE document : {multi}   <- the old merge deleted one of each')
    print(f'    total manifestations retained        : {sum(len(r.get("manifestations") or []) for r in out)}')
    print(f'    wrote {CORPUS}')
    print(f'    wrote {ledger_path}  ({len(ledger)} events)')
    print('\n  Every label above was DERIVED by `event_ledger.derive_content_profile` from the events,')
    print('  and every one carries its basis on the row. Not one was ranked by word count, and not')
    print('  one was read off a claim a fetcher made about its own success.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
