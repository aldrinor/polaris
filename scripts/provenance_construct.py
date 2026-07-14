#!/usr/bin/env python3
"""THE PROVENANCE CONSTRUCTION REDUCER — Sol (a)(2).

    "After every acquisition batch, ONE reducer builds/extends the typed graph —
     Work / Expression / Manifestation / evidenced edges."

WHY IT MUST BE A REDUCER OVER THE LEDGER, AND NOT A PASS OVER THE CORPUS
─────────────────────────────────────────────────────────────────────────────────────────────────
`provenance.migrate()` builds the same graph from the corpus ROWS. It is honest code and it still
cannot see two things, because THE ROW DOES NOT CARRY THEM:

  1. WHERE THE BYTES CAME FROM. wp_fetch never recorded the URL it fetched. So for every row it
     touched, the only locator available to migrate() was `oa_url` — left by an EARLIER fetcher, and
     pointing at the PUBLISHER (aeaweb.org) while the bytes in the row are an NBER working paper.
     migrate() has to mark those `CONTRADICTS_CONTENT` and move on. It is doing the best that can be
     done with a row that has already forgotten.

     The ledger did not forget. `MANIFESTATION_FETCHED` carries the locator, the immutable blob id and
     the byte hash, WRITTEN AT THE MOMENT OF THE FETCH, by the fetcher that made the request.

  2. THE BYTES WE DID NOT KEEP. A row holds ONE `fulltext`. When two fetchers retrieved two different
     documents for one DOI, the old merge threw one away on a word count — so migrate() never saw it,
     and neither did anyone else. The ledger holds every manifestation ever recorded, and this reducer
     puts EVERY ONE of them in the graph, each against its own expression.

  A graph built from the row can only ever be as truthful as the row. This one is built from what
  happened.

WHAT IT DOES NOT DO
─────────────────────────────────────────────────────────────────────────────────────────────────
It does not decide anything on its own. Every judgement — what kind of artifact these bytes are, which
version they express, whether they are the work we asked for, whether an edge may be ASSERTED — is made
by `provenance.ingest_bytes()`, which `migrate()` also calls. Two functions that each decided what an
expression is would be two answers to "may this span name the journal", and the one that shipped would
be whichever ran last.

IT NEVER ASSERTS A SPAN-PRESERVING EDGE. A working paper gets `predecessor_of` PROPOSED, and that
edge transfers NOTHING. Only a byte-level comparison against the journal version's own bytes can
ASSERT `exact_copy_of` — and `provenance.add_edge()` refuses to construct one on any lesser basis,
which is why this file cannot do it by accident.

    python3 scripts/provenance_construct.py              # build/extend from the durable ledger
    python3 scripts/provenance_construct.py --rebuild    # discard the graph on disk and re-derive
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acquisition import BlobStore, manifestations_of, open_ledger  # noqa: E402
from event_ledger import (  # noqa: E402
    EventKind, Ledger, derive_backend_outcome, derive_route_status, derive_semantic_binding,
)
from provenance import (  # noqa: E402
    Graph, GraphIntegrityError, ensure_work, ingest_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
GRAPH_OUT = ROOT / 'outputs' / 'provenance_graph.json'


def _requested_identity(ledger: Ledger, unit: str) -> dict:
    """WHAT WE ASKED FOR, as the fetcher recorded it at request time. Not what came back."""
    ident = dict(doi='', title='', authors=[], venue='', year=None, source_type='')
    for e in ledger.events(unit):
        if 'derived_by' in e.payload:
            continue
        p = e.payload
        ident['doi'] = p.get('requested_doi') or p.get('doi') or ident['doi']
        ident['title'] = p.get('requested_title') or ident['title']
        ident['authors'] = p.get('requested_authors') or ident['authors']
        ident['venue'] = p.get('requested_venue') or ident['venue']
        ident['year'] = p.get('requested_year') if p.get('requested_year') is not None else ident['year']
        ident['source_type'] = p.get('source_type') or ident['source_type']
    return ident


def _locator_status(m: dict) -> str:
    """WHO SAID THE BYTES CAME FROM THERE — the fetcher that fetched them, or a row that inherited it?

    This distinction is the whole reason the ledger exists. `RECORDED` here means: the component that
    made the HTTP request wrote this URL down at the moment it made it. Nothing else earns that word.
    """
    if not (m.get('locator') or '').strip():
        return 'NOT_RECORDED_BY_FETCHER'
    if m.get('extraction_method') == 'corpus_ingest' or m.get('locator_recorded_by'):
        # The bytes came off a corpus row that had already forgotten where it got them. The URL on the
        # row is a CLAIM by the row, and for the rows wp_fetch touched it points at the publisher while
        # the bytes are a working paper.
        return ('CLAIMED_BY_CORPUS_ROW (not recorded by the fetcher that obtained these bytes; for the '
                'rows wp_fetch touched this URL names the PUBLISHER over working-paper bytes)')
    return 'RECORDED'


def construct(ledger: Ledger, graph: Graph | None = None, blobs: BlobStore | None = None,
              bibliography: list[dict] | None = None) -> tuple[Graph, dict]:
    """BUILD OR EXTEND the typed graph from the durable ledger. -> (graph, stats)

    EXTENDS, never rebuilds from scratch unless asked: every id in the graph is content-addressed or
    derived (`manif:<sha256[:12]>`, `work:<doi-slug>`, `<work>:<expression-kind>`), so running this
    after every acquisition batch is idempotent — the same bytes produce the same nodes, and new bytes
    produce new nodes beside them. Nothing that was in the graph leaves it.

    THE TWO SOURCES, AND WHY THEY ARE DIFFERENT SOURCES
      * THE BIBLIOGRAPHY says WHICH WORKS EXIST and what they are called. That is what a bibliography
        IS, and it is the only thing here that is allowed to say it.
      * THE LEDGER says WHAT WE HOLD, WHERE IT CAME FROM, and WHAT IT TURNED OUT TO BE. Every
        manifestation, every locator, every expression and every edge comes from the ledger and from
        nowhere else.

    Passing the bibliography is what puts the PAPERS WE RETRIEVED NOTHING FOR into the graph — as Works
    with no manifestation. That emptiness is the honest record of what we do not have, and it has to be
    VISIBLE: a paper that is simply ABSENT from the graph reads as a paper nobody ever wanted, and the
    thirteen missing from this corpus are thirteen we tried for and failed to get.
    """
    g = graph if graph is not None else Graph()
    blobs = blobs or BlobStore()
    stats = dict(works=0, manifestations=0, skipped_no_blob=0, quarantined=0, units=0,
                 works_with_no_bytes=0)

    for row in (bibliography or []):
        ensure_work(g, doi=row.get('doi') or '', title=row.get('title') or '',
                    authors=list(row.get('authors') or []), year=row.get('year'),
                    venue=row.get('venue') or '', source_type=str(row.get('type') or ''))

    for unit in ledger.units():
        manifs = manifestations_of(ledger, unit)
        if not manifs:
            # A unit we asked about and got NOTHING for. It STILL belongs in the graph: the Work is
            # real, and the honest record of a paper we could not retrieve is a Work with no
            # manifestation — NOT an absence, and NOT a row quietly missing from the file.
            ident = _requested_identity(ledger, unit)
            if ident['title'] or ident['doi']:
                ensure_work(g, doi=ident['doi'], title=ident['title'], authors=ident['authors'],
                            year=ident['year'], venue=ident['venue'],
                            source_type=ident['source_type'])
                stats['works'] += 1
            stats['units'] += 1
            continue

        ident = _requested_identity(ledger, unit)
        work, claimed_id, claimed_kind = ensure_work(
            g, doi=ident['doi'] or unit, title=ident['title'], authors=ident['authors'],
            year=ident['year'], venue=ident['venue'], source_type=ident['source_type'])
        stats['works'] += 1
        stats['units'] += 1

        # The bibliography's abstract is an INDEPENDENT probe against a fetched body — it did not come
        # from the document we are testing, which is exactly what makes it able to catch a stranger's
        # paper. It is never used to probe itself.
        indep = ''
        for m in manifs:
            if m.get('source_field') == 'abstract' and m.get('text_blob_id'):
                try:
                    indep = blobs.get_text(m['text_blob_id'])
                except (FileNotFoundError, ValueError):
                    indep = ''
                break

        for m in manifs:
            bid = m.get('text_blob_id')
            if not bid:
                stats['skipped_no_blob'] += 1
                continue
            try:
                text = blobs.get_text(bid)
            except (FileNotFoundError, ValueError) as e:
                # The event names bytes the store does not have (or that do not hash to their own
                # name). We do not invent them and we do not silently skip: it is reported.
                print(f'  !! {unit}: {e}')
                stats['skipped_no_blob'] += 1
                continue
            if not text.strip():
                continue
            # THE LEDGER SAYS `body`; THE GRAPH SAYS `fulltext`. The translation lives here, in one
            # line, on purpose: the ledger may not write the word "fulltext" (it is a VERDICT about
            # completeness, and the conclusion guard refuses it), while the graph's `text_field` is an
            # established interface that `evidence_miner` and `provenance.census` both branch on.
            field = 'abstract' if m.get('source_field') == 'abstract' else 'fulltext'
            mid = ingest_bytes(
                g, work, text,
                text_field=field,
                # WHO fetched it, and THROUGH WHICH ADAPTER. `fulltext_source='working_paper'` used to
                # sit here and it named neither: it named the SCRIPT, and it was wrong about the
                # document six times out of six.
                fetched_by=f"{m.get('actor', '?')} via {m.get('adapter', '?')}",
                locator=m.get('locator') or None,
                locator_status=_locator_status(m),
                claimed_id=claimed_id, claimed_kind=claimed_kind,
                independent_abstract=indep if field == 'fulltext' else '')
            stats['manifestations'] += 1
            if ':quarantine:' in g.manifestations[mid].expression_id:
                stats['quarantined'] += 1

    return g, stats


def main() -> int:
    rebuild = '--rebuild' in sys.argv
    ledger = open_ledger()
    blobs = BlobStore()

    if not len(ledger):
        print(f'!! the ledger is EMPTY ({ledger._path}).')
        print('   Nothing has been acquired through the observing fetchers yet, so there is nothing')
        print('   to construct FROM. This is not an error and it is not an absence: run an acquisition')
        print('   batch (or scripts/merge_corpus.py, which ingests legacy corpus bytes) first.')
        return 0

    g = None
    if not rebuild and GRAPH_OUT.exists():
        try:
            g = Graph.from_json(json.loads(GRAPH_OUT.read_text()))
            print(f'  extending the graph on disk: {len(g.works)} works, '
                  f'{len(g.manifestations)} manifestations')
        except GraphIntegrityError as e:
            # REFUSES, NEVER REPAIRS. A graph that does not agree with itself is not a starting point.
            print(f'!! the graph on disk DOES NOT AGREE WITH ITSELF and will not be extended:\n{e}')
            print('\n   re-run with --rebuild to re-derive it from the ledger.')
            return 1

    # THE BIBLIOGRAPHY names the works; THE LEDGER says what we hold of them. Two sources, on purpose.
    biblio = None
    corpus_p = ROOT / 'outputs' / 'journal_corpus_content.json'
    if corpus_p.exists():
        biblio = json.loads(corpus_p.read_text())

    g, stats = construct(ledger, graph=g, blobs=blobs, bibliography=biblio)

    # A work with NO manifestation is a paper we tried for and did not get. It stays in the graph, and
    # it is COUNTED — because a paper that is merely ABSENT reads as a paper nobody ever wanted.
    held = {m.work_id for m in g.manifestations.values()}
    stats['works_with_no_bytes'] = len([w for w in g.works if w not in held])

    GRAPH_OUT.write_text(json.dumps(g.to_json(), indent=1))

    print('\n' + '=' * 96)
    print('PROVENANCE GRAPH — CONSTRUCTED FROM THE EVENT LEDGER')
    print('=' * 96)
    print(f'  units in the ledger      : {stats["units"]}')
    print(f'  works                    : {len(g.works)}')
    print(f'  expressions              : {len(g.expressions)}')
    print(f'  manifestations           : {len(g.manifestations)}   (every set of bytes ever recorded)')
    print(f'  edges                    : {len(g.edges)}')
    print(f'  works we hold NO BYTES for: {stats["works_with_no_bytes"]}   <- in the graph, and empty. '
          f'That emptiness IS the record.')
    if stats['skipped_no_blob']:
        print(f'  !! manifestations whose blob is MISSING: {stats["skipped_no_blob"]}')

    asserted = [e for e in g.edges if e.status == 'ASSERTED']
    print(f'\n  ASSERTED span-preserving edges: {len([e for e in asserted if e.type in ("exact_copy_of", "accepted_manuscript_of")])}')
    print('    (an ASSERTED span-preserving edge is the ONLY thing that lets a span name a document')
    print('     whose bytes we do not hold. `provenance.add_edge` refuses to construct one without')
    print('     byte-level evidence, so this number can only be raised by version_align.py actually')
    print('     fetching the journal version and finding the span verbatim inside it.)')

    # what the locators say now — the thing the row could never tell us
    rec = sum(1 for m in g.manifestations.values() if m.locator_status == 'RECORDED')
    claimed = sum(1 for m in g.manifestations.values() if m.locator_status.startswith('CLAIMED'))
    none_ = sum(1 for m in g.manifestations.values()
                if m.locator_status == 'NOT_RECORDED_BY_FETCHER')
    print(f'\n  LOCATORS')
    print(f'    RECORDED by the fetcher that made the request : {rec}')
    print(f'    CLAIMED by a corpus row that had forgotten    : {claimed}')
    print(f'    absent                                        : {none_}')

    # per-expression-kind census
    kinds: dict[str, int] = {}
    for m in g.manifestations.values():
        k = g.expressions[m.expression_id].kind
        kinds[k] = kinds.get(k, 0) + 1
    print(f'\n  WHAT THE BYTES ARE (derived from their own headers, never from a fetcher\'s label)')
    for k in sorted(kinds, key=lambda x: -kinds[x]):
        print(f'    {k:<24}{kinds[k]:>4}')

    print(f'\n  graph written to {GRAPH_OUT}  (all text retained — nothing deleted)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
