#!/usr/bin/env python3
"""A SYNTHETIC GRAPH WITH REAL BYTES. Every test fixture in this repo is now a BOUND card.

The old canary handed the composer bare dicts — `{'authors': [...], 'span': '...', 'claim': '...'}` —
with no manifestation, no content hash and no offsets, and asserted things about them. That is a fixture
for a lane the fabrication no longer uses. Under the law a card like that DOES NOT EXIST, so a test built
on one proves nothing about the pipeline that ships.

These fixtures bind. `bind_span()` slices real bytes, `verify_span()` re-checks them, and
`resolve_attribution()` decides what may be named — exactly as in production.

THE THIRD FIXTURE IS THE P0 ITSELF: metadata that says `Journal of Political Economy`, bytes that are
the NBER working paper. Every suite gets to try to cite it, and every suite must fail.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P  # noqa: E402

BRES_SPAN = 'Computer automation of such work has been correspondingly limited in its scope.'
AUTOR_SPAN = ('we contend that computer capital substitutes for workers in carrying out a limited and '
              'well-defined set of cognitive and manual activities, namely routine tasks')
AR_SPAN = 'we find that employment falls by 0.2 percentage points per robot per thousand workers'
LEAK_SPAN = 'productivity growth of 10.25 percent was observed across the sampled establishments'

#: Long enough to clear the scholarly stub floor (1,200 words). Completeness is a property of the KIND:
#: a `journal_article` of 40 words is a stub, and the registry is right to say so.
_FILLER = ('The paper proceeds as follows. We describe the data, the identification strategy and the '
           'estimation. ') * 120


def build() -> tuple[P.Graph, list[dict]]:
    g = P.Graph()

    def work(wid, authors, year, venue, doi, title='A study'):
        g.works[wid] = P.Work(id=wid, title=title, authors=authors, year=year, venue=venue,
                              doi=doi, kind='study')

    def expr(eid, wid, kind):
        g.expressions[eid] = P.Expression(id=eid, work_id=wid, kind=kind, kind_basis='test fixture',
                                          attribution=P._attribution_for(kind, g.works[wid]))

    def manif(mid, eid, wid, span, kind):
        text = _FILLER + span + ' ' + _FILLER
        g.manifestations[mid] = P.Manifestation(
            id=mid, expression_id=eid, work_id=wid, text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(), n_words=len(text.split()),
            locator='http://example/x', locator_status='RECORDED', fetched_by='test',
            text_field='fulltext',
            profile=dict(artifact_kind=kind, complete=True,
                         extractability=P.extractability(text), incomplete_because=[]))

    work('w:bres', ['Bresnahan', 'Brynjolfsson'], 2002, 'The Quarterly Journal of Economics', '10.1/b')
    expr('e:bres:j', 'w:bres', 'journal_version')
    manif('m:bres', 'e:bres:j', 'w:bres', BRES_SPAN, 'journal_article')

    work('w:autor', ['Autor', 'Levy', 'Murnane'], 2003, 'The Quarterly Journal of Economics', '10.1/a')
    expr('e:autor:j', 'w:autor', 'journal_version')
    manif('m:autor', 'e:autor:j', 'w:autor', AUTOR_SPAN, 'journal_article')

    # A REAL JOURNAL ARTICLE whose span contains 10.25 — the substring that leaks a fabricated "0.2".
    work('w:leak', ['Stiroh'], 2002, 'American Economic Review', '10.1/l')
    expr('e:leak:j', 'w:leak', 'journal_version')
    manif('m:leak', 'e:leak:j', 'w:leak', LEAK_SPAN, 'journal_article')

    # ---- THE P0, AS A FIXTURE ----------------------------------------------------------------------
    # The metadata row says "Journal of Political Economy". THE BYTES ARE NBER WORKING PAPER 23285.
    # Peer review changed this number: 0.37pp in the working paper, 0.2pp in the published JPE. The
    # journal expression EXISTS — and we do not hold one byte of it.
    work('w:ar', ['Acemoglu', 'Restrepo'], 2020, 'Journal of Political Economy', '10.1086/705716')
    expr('e:ar:wp', 'w:ar', 'working_paper')
    expr('e:ar:j', 'w:ar', 'journal_version')
    manif('m:ar', 'e:ar:wp', 'w:ar', AR_SPAN, 'working_paper')

    def card(cid, mid, span, claim, **kw):
        m = g.manifestations[mid]
        s = m.text.index(span)
        b = g.bind_span(mid, s, s + len(span))
        att = g.resolve_attribution(mid, P.JOURNAL_ONLY)
        w = g.works[m.work_id]
        return dict(
            id=cid, manifestation_id=mid, content_hash=b['content_hash'],
            span_start=s, span_end=s + len(span), span_raw=b['text'], span=span, claim=claim,
            expression_id=b['expression_id'],
            permitted_expression_ids=list(b['permitted_expression_ids']),
            attribution_target_expression_id=att.names_expression_id,
            work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, year=w.year,
            venue=w.venue, level=kw.get('level', 'firm'), horizon='long-run',
            method='observational', mechanisms=kw.get('mech', []), corroborating_sources=[],
            source_version=m.content_hash[:12], text_field='fulltext')

    cards = [
        card('c:bres', 'm:bres', BRES_SPAN,
             'Computer automation of routine work has been limited in scope.'),
        card('c:autor', 'm:autor', AUTOR_SPAN,
             'Computer capital substitutes for workers in routine tasks.',
             level='occupation', mech=['task displacement']),
        card('c:leak', 'm:leak', LEAK_SPAN, 'Productivity grew 10.25 percent.'),
        card('c:ar', 'm:ar', AR_SPAN,
             'Employment falls 0.2 percentage points per robot per thousand workers.', level='region'),
    ]
    return g, cards
