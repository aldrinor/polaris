#!/usr/bin/env python3
"""A REAL GRAPH BUILT THE PRODUCTION WAY. Every fixture card here is a BOUND card whose identity was
EARNED, not stamped.

The old canary handed the composer bare dicts — `{'authors': [...], 'span': '...', 'claim': '...'}` —
with no manifestation, no content hash and no offsets. Its successor bound real bytes but still
HAND-BUILT the `Manifestation.profile` (`dict(artifact_kind='journal_article', complete=True, ...)`)
and NEVER RAN THE IDENTITY REDUCER — so `profile['semantic_binding']` was `None`, and every card was
refused at the identity gate with `SOURCE_POLICY_REFUSES: None is not in the proven allowlist`. That
masked every attack behind one generic refusal and REGRESSED the positive controls: a true finding
could not reach the page because the fixture never proved it was the work it claimed to be.

These fixtures now go through THE PRODUCTION CONSTRUCTION PATH, exactly as `migrate()` does:

    ensure_work  ->  ingest_bytes  ->  event_ledger.derive_binding_core  ->  Graph.resolve_attribution

The bytes carry POSITIVE front-matter evidence — a title, a byline naming the requested authors, and
typeset journal furniture (a masthead with volume/number/pages) — so `derive_binding_core` GENUINELY
EARNS `VERSION_OF_PUBLISHED` (in `event_ledger.IDENTITY_PROVEN`). Nothing here stamps `semantic_binding`.

THE FOURTH FIXTURE IS THE P0 ITSELF: metadata that says `Journal of Political Economy`, bytes that
carry an NBER WORKING-PAPER stamp. The reducer proves its identity (`VERSION_OF_PREPRINT`, also in the
allowlist), and then the JOURNAL-ONLY policy REFUSES it — a working paper is not a journal article, and
the numbers move across peer review. Every suite gets to try to cite it, and every suite must fail —
for the RIGHT reason (a policy refusal on a proven preprint), never a masked identity failure.
"""
from __future__ import annotations

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

#: STRUCTURAL VERSION FURNITURE — the vocabulary of the world, never a subject or an identifier. A
#: typeset masthead (`Volume N, Number M, ... Pages a-b`) is what `_JOURNAL_MARK` reads as the article
#: of record; an NBER stamp is what `_WP_MARK` reads as a working paper. Neither names any subject.
_WP_STAMP = 'NBER Working Paper No. 23285'


def _scholarly_body(title: str, authors: list, span: str, *, furniture: str = '',
                    masthead: str = '') -> str:
    """A complete scholarly body whose FRONT MATTER positively identifies the work: a title, a byline
    naming the requested authors (`derive_binding_core` confirms on `author_in_byline`), and — for a
    published article — a typeset masthead the journal furniture detector reads. `furniture` (an NBER /
    preprint stamp) makes the bytes a working paper, exactly as a repository deposit that carries one."""
    byline = 'By ' + ' and '.join(authors)
    parts = [title, byline]
    if furniture:
        parts.append(furniture)
    if masthead:
        parts.append(masthead)
    front = '\n'.join(parts) + '\n1. Introduction\n'
    return front + _FILLER + '\n4. Results\n' + span + ' ' + _FILLER


def _ingest(g: P.Graph, *, mid: str, doi: str, title: str, authors: list, year: int, venue: str,
            span: str, kind: str = 'journal') -> P.Manifestation:
    """Run the ONE production construction path and re-key the resulting manifestation to a stable id.

    `ensure_work` builds the Work and the expression its metadata CLAIMS; `ingest_bytes` observes the
    bytes, runs `derive_binding_core`, and stores the EARNED `semantic_binding`. We then rename the
    hash-keyed manifestation to a readable id (`m:bres`) so downstream tests can address it — the
    identity was derived, not stamped."""
    furniture = _WP_STAMP if kind == 'working_paper' else ''
    masthead = '' if kind == 'working_paper' else \
        f'{venue}, Volume 12, Number 3, {year}, Pages 45-67.'
    body = _scholarly_body(title, authors, span, furniture=furniture, masthead=masthead)
    work, claimed_id, claimed_kind = P.ensure_work(
        g, doi=doi, title=title, authors=list(authors), year=year, venue=venue,
        source_type='journal-article')
    real_mid = P.ingest_bytes(
        g, work, body, text_field='fulltext', fetched_by='test',
        locator='http://example/x', locator_status='RECORDED',
        claimed_id=claimed_id, claimed_kind=claimed_kind)
    m = g.manifestations.pop(real_mid)
    m.id = mid
    g.manifestations[mid] = m
    return m


def _card(g: P.Graph, cid: str, mid: str, span: str, claim: str, **kw) -> dict:
    """Bind the span through the REAL chain and resolve its attribution FROM THE BINDING (the same call
    `CardBundle.resolve` makes), so the stored target never goes stale against the graph."""
    m = g.manifestations[mid]
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    att = g.resolve_attribution(b, P.JOURNAL_ONLY)
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


def build() -> tuple[P.Graph, list[dict]]:
    g = P.Graph()

    _ingest(g, mid='m:bres', doi='10.1/b', title='A study', authors=['Bresnahan', 'Brynjolfsson'],
            year=2002, venue='The Quarterly Journal of Economics', span=BRES_SPAN)
    _ingest(g, mid='m:autor', doi='10.1/a', title='A study', authors=['Autor', 'Levy', 'Murnane'],
            year=2003, venue='The Quarterly Journal of Economics', span=AUTOR_SPAN)
    # A REAL JOURNAL ARTICLE whose span contains 10.25 — the substring that leaks a fabricated "0.2".
    _ingest(g, mid='m:leak', doi='10.1/l', title='A study', authors=['Stiroh'],
            year=2002, venue='American Economic Review', span=LEAK_SPAN)

    # ---- THE P0, AS A FIXTURE ----------------------------------------------------------------------
    # The metadata row REQUESTS "Journal of Political Economy". THE BYTES CARRY AN NBER WORKING-PAPER
    # STAMP. Peer review changed this number: 0.37pp in the working paper, 0.2pp in the published JPE.
    # The reducer PROVES identity (VERSION_OF_PREPRINT) and the JOURNAL-ONLY policy then refuses it — a
    # working paper may not be cited as the journal article we do not hold.
    _ingest(g, mid='m:ar', doi='10.1086/705716', title='A study', authors=['Acemoglu', 'Restrepo'],
            year=2020, venue='Journal of Political Economy', span=AR_SPAN, kind='working_paper')

    cards = [
        _card(g, 'c:bres', 'm:bres', BRES_SPAN,
              'Computer automation of routine work has been limited in scope.'),
        _card(g, 'c:autor', 'm:autor', AUTOR_SPAN,
              'Computer capital substitutes for workers in routine tasks.',
              level='occupation', mech=['task displacement']),
        _card(g, 'c:leak', 'm:leak', LEAK_SPAN, 'Productivity grew 10.25 percent.'),
        _card(g, 'c:ar', 'm:ar', AR_SPAN,
              'Employment falls 0.2 percentage points per robot per thousand workers.', level='region'),
    ]
    return g, cards
