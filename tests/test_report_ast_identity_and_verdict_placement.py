#!/usr/bin/env python3
"""ACCEPTANCE — report_ast identity handoff AND cross-source verdict placement.

Every fixture here is built THE PRODUCTION WAY — `ensure_work -> ingest_bytes -> derive_binding_core
-> Graph.resolve_attribution -> CardBundle.resolve` — so a source's identity is EARNED from POSITIVE
front-matter evidence (a title, a byline naming the requested authors, typeset journal furniture), never
stamped. That is the whole point of this file: the prior suites hand-built `Manifestation.profile` and
left `semantic_binding=None`, so EVERY card was refused at the identity gate with a generic
`SOURCE_POLICY_REFUSES` — which masked every attack behind one refusal AND starved every true finding.

This suite proves both halves of the fix at once:

  * POSITIVE — an identity-proven source's true finding SHIPS; a span-proved different-unit verdict is
    PLACED and revalidates at final render.
  * NEGATIVE — `None`, an unknown verdict token, `UNRESOLVED_BINDING` and `DIFFERENT_WORK` all REJECT;
    card `venue`/`doi`/`authors`/`attribution` can NEVER promote identity (the bytes decide); and each
    fabrication attack rejects for its INTENDED semantic reason, not a masked source-policy refusal.

  * METAMORPHIC — consistently renaming every identifier leaves admission and placement UNCHANGED;
    changing only the REQUESTED identity while holding the bytes fixed drops the changed source to zero;
    a corporate byline keeps common prose tokens usable while forbidding the exact corporate name; and
    replacing every venue leaves behavior structural, the placed verdict carrying no identifier literal.

Determinism: the entailment JUDGE is stubbed and the facet contract is pinned to the shipped AI-labour
demo contract, so nothing here depends on a live model. The DETERMINISTIC gates (identity, source
policy, numbers, direction, source-name) do the work these tests observe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / 'scripts'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import provenance as P                                                    # noqa: E402
import report_ast as RA                                                   # noqa: E402
import argument_planner as AP                                             # noqa: E402
import _test_fixtures as TF                                               # noqa: E402
from event_ledger import IDENTITY_PROVEN, UNRESOLVED, DIFFERENT_WORK      # noqa: E402
from report_ast import CardBundle, Attributed, Clause, Owned             # noqa: E402

POLICY = P.JOURNAL_ONLY

# A span whose OUTCOME is employment and whose UNIT is the FIRM; and one whose unit is the REGION. Same
# construct, different span-bound unit of analysis — the exact shape a CONTRASTS_LEVEL verdict proves on.
FIRM_SPAN = 'firm-level employment expanded at the establishments that adopted the technology'
REGION_SPAN = 'regional employment declined in the local labor markets that adopted the technology'

# The reviewer's own closed template for a different-unit verdict. It carries NO identifier — no venue,
# no DOI, no author, no task subject — only the proved relation.
VERDICT_TEXT = ('These employment findings concern different units of analysis and are not directly '
                'comparable across the firm and regional levels.')
INDIRECT_VERDICT_TEXT = ('The unit labels are declared metadata and are not fully stated in the quoted '
                         'findings, so this is an indirect comparison of employment across different '
                         'units of analysis (worker versus firm) and is not directly comparable.')

_FILLER = ('This paper studies the question at length across many pages of careful analysis, reporting '
           'the design, the data and the estimates in full. ') * 120


@pytest.fixture(autouse=True)
def _deterministic():
    """Pin the facet contract and stub the judge so placement/admission are deterministic. RESET after,
    so no global leaks into the binding-gate suites that run alongside this file."""
    RA.set_facet_contract(AP._ai_labor_demo_contract())
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))
    yield
    RA.set_entailment_judge(None)
    RA.set_facet_contract(None)


# =================================================================================================
# BUILDERS — the ONE production construction path, plus the two negative-identity bodies.
# =================================================================================================
def _ingest_raw(g, *, doi, title, authors, venue, body, mid=None):
    """ensure_work -> ingest_bytes for an arbitrary body (used for the NEGATIVE identity cases where the
    bytes deliberately do NOT prove identity). Optionally re-keys to a readable manifestation id."""
    work, cid, ck = P.ensure_work(g, doi=doi, title=title, authors=list(authors), year=2020,
                                  venue=venue, source_type='journal-article')
    real = P.ingest_bytes(g, work, body, text_field='fulltext', fetched_by='test',
                          locator='http://example/x', locator_status='RECORDED',
                          claimed_id=cid, claimed_kind=ck)
    m = g.manifestations[real]
    if mid and mid != real:
        g.manifestations.pop(real)
        m.id = mid
        g.manifestations[mid] = m
    return m


def _proven_pair(names=(('Wu', 'Acemoglu'), ('Ng', 'Restrepo')),
                 venues=('American Economic Review', 'Journal of Political Economy'),
                 dois=('10.5/firm', '10.5/region'), titles=('A study', 'A study')):
    """A two-source bundle: a firm-level and a region-level employment finding, both identity-proven
    (`VERSION_OF_PUBLISHED`) through the real chain. Returns (graph, bundle)."""
    g = P.Graph()
    TF._ingest(g, mid='m:firm', doi=dois[0], title=titles[0], authors=list(names[0]), year=2021,
               venue=venues[0], span=FIRM_SPAN)
    TF._ingest(g, mid='m:region', doi=dois[1], title=titles[1], authors=list(names[1]), year=2020,
               venue=venues[1], span=REGION_SPAN)
    cf = TF._card(g, 'c:firm', 'm:firm', FIRM_SPAN, 'firm employment rose', level='firm')
    cr = TF._card(g, 'c:region', 'm:region', REGION_SPAN, 'regional employment fell', level='region')
    return g, CardBundle([cf, cr], g, POLICY)


def _admitted(b, *card_ids):
    return sum(1 for cid in card_ids if b.resolve(cid).ok)


def _placed(b, *pairs):
    return sum(1 for pair in pairs if RA.make_proven_verdict(VERDICT_TEXT, pair, b) is not None)


# =================================================================================================
# POSITIVE CONTROLS — identity earned, finding ships, verdict places and revalidates.
# =================================================================================================
def test_sources_earn_identity_proven_from_bytes():
    g, b = _proven_pair()
    for mid in ('m:firm', 'm:region'):
        m = g.manifestations[mid]
        assert m.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
        assert m.profile['semantic_binding'] in IDENTITY_PROVEN
        # it was DERIVED by the reducer, not stamped by the fixture
        assert m.profile.get('semantic_binding_derived_by') == 'ingest_bytes:derive_binding_core'


def test_p0_true_finding_from_proven_source_ships():
    g, b = _proven_pair()
    node = Attributed(clauses=(Clause('c:firm', FIRM_SPAN),))
    assert RA.validate_report([node], b) == []


def test_p1_span_proved_different_unit_verdict_places():
    g, b = _proven_pair()
    v = RA.make_proven_verdict(VERDICT_TEXT, ('c:firm', 'c:region'), b)
    assert v is not None
    assert v.operation == 'CONTRASTS_LEVEL'


def test_declared_only_different_units_place_only_with_indirect_disclosure():
    g = P.Graph()
    a_span = 'employment expanded after adoption of the technology'
    b_span = 'employment declined after exposure to the technology'
    TF._ingest(g, mid='m:worker', doi='10.5/worker', title='A study', authors=['Wu', 'Acemoglu'],
               year=2021, venue='American Economic Review', span=a_span)
    TF._ingest(g, mid='m:firm2', doi='10.5/firm2', title='A study', authors=['Ng', 'Restrepo'],
               year=2020, venue='Journal of Political Economy', span=b_span)
    ca = TF._card(g, 'c:worker', 'm:worker', a_span, 'employment expanded', level='worker')
    cb = TF._card(g, 'c:firm2', 'm:firm2', b_span, 'employment declined', level='firm')
    b = CardBundle([ca, cb], g, POLICY)

    assert RA.make_proven_verdict(VERDICT_TEXT, ('c:worker', 'c:firm2'), b) is None
    v = RA.make_proven_verdict(INDIRECT_VERDICT_TEXT, ('c:worker', 'c:firm2'), b)
    assert v is not None and v.operation == 'CONTRASTS_LEVEL'
    assert 'declared metadata' in v.text and 'indirect comparison' in v.text


def test_placed_verdict_revalidates_at_final_render():
    g, b = _proven_pair()
    v = RA.make_proven_verdict(VERDICT_TEXT, ('c:firm', 'c:region'), b)
    assert v is not None
    md, _receipts = RA.render([v], b)          # render RE-RUNS the full gate; a stale proof would raise
    assert 'different units of analysis' in md
    assert RA.validate_report([v], b) == []    # and it survives a second, independent revalidation


def test_at_least_one_comparison_is_placed():
    g, b = _proven_pair()
    assert _placed(b, ('c:firm', 'c:region')) >= 1


# =================================================================================================
# NEGATIVE — identity gate. None / unknown / UNRESOLVED / DIFFERENT_WORK all reject.
# =================================================================================================
def test_none_identity_rejects():
    g, b = _proven_pair()
    g.manifestations['m:firm'].profile['semantic_binding'] = None
    b._cache.clear()
    r = b.resolve('c:firm')
    assert not r.ok and 'SOURCE_POLICY_REFUSES' in (r.refusal or '')
    att = g.resolve_attribution(RA._binding_from_card(b.cards['c:firm']), POLICY)
    assert att.reason_code == P.RC_IDENTITY_UNKNOWN_VERDICT and not att.admitted


def test_unknown_verdict_token_rejects():
    g, b = _proven_pair()
    g.manifestations['m:firm'].profile['semantic_binding'] = 'A_TOKEN_WE_NEVER_DEFINED'
    b._cache.clear()
    att = g.resolve_attribution(RA._binding_from_card(b.cards['c:firm']), POLICY)
    assert not att.admitted and att.reason_code == P.RC_IDENTITY_UNKNOWN_VERDICT


def test_unresolved_binding_rejects():
    g = P.Graph()
    # generic title, NO byline, requested authors absent from the bytes -> identity NOT proven.
    body = ('Adult Report\n\nSome Learned Review, Volume 12, Number 3, 2020, Pages 45-67.\n'
            '1. Introduction\n' + _FILLER + '\n4. Results\n' + REGION_SPAN + '\n')
    m = _ingest_raw(g, doi='10.5/u', title='A Detailed Report on Widget Outcomes in Adults',
                    authors=['Zeta', 'Theta'], venue='American Economic Review', body=body, mid='m:u')
    assert m.profile['semantic_binding'] == UNRESOLVED
    card = TF._card(g, 'c:u', 'm:u', REGION_SPAN, 'employment fell', level='region')
    b = CardBundle([card], g, POLICY)
    r = b.resolve('c:u')
    assert not r.ok
    att = g.resolve_attribution(RA._binding_from_card(card), POLICY)
    assert att.reason_code == P.RC_IDENTITY_UNRESOLVED


def test_different_work_rejects():
    g = P.Graph()
    # the article's OWN front matter prints a FOREIGN DOI -> positive evidence of a stranger's paper.
    body = ('A study\nBy Alice Adams and Bob Brown\nSome Learned Review, Volume 12, Number 3, 2020.\n'
            'doi: 10.9999/a-different-paper\n1. Introduction\n' + _FILLER + '\n4. Results\n'
            + REGION_SPAN + '\n')
    m = _ingest_raw(g, doi='10.5/mine', title='A study', authors=['Adams', 'Brown'],
                    venue='American Economic Review', body=body, mid='m:dw')
    assert m.profile['semantic_binding'] == DIFFERENT_WORK
    card = TF._card(g, 'c:dw', 'm:dw', REGION_SPAN, 'employment fell', level='region')
    b = CardBundle([card], g, POLICY)
    att = g.resolve_attribution(RA._binding_from_card(card), POLICY)
    assert not att.admitted and att.reason_code == P.RC_IDENTITY_DIFFERENT_WORK


def test_card_metadata_cannot_promote_identity():
    """The bytes never proved identity (UNRESOLVED). Rewriting the card's venue/doi/authors/attribution
    to pristine journal values must NOT admit it — the graph re-derives identity FROM THE BYTES."""
    g = P.Graph()
    body = ('Adult Report\n\nSome Learned Review, Volume 12, Number 3, 2020, Pages 45-67.\n'
            '1. Introduction\n' + _FILLER + '\n4. Results\n' + REGION_SPAN + '\n')
    _ingest_raw(g, doi='10.5/u2', title='A Detailed Report on Widget Outcomes in Adults',
                authors=['Zeta', 'Theta'], venue='American Economic Review', body=body, mid='m:u2')
    card = TF._card(g, 'c:u2', 'm:u2', REGION_SPAN, 'employment fell', level='region')
    card.update(venue='Nature', doi='10.1/prestige', authors=['Acemoglu', 'Restrepo'],
                attribution='Acemoglu and Restrepo (2020), Nature',
                attribution_target_expression_id='forged:journal_version')
    b = CardBundle([card], g, POLICY)
    assert not b.resolve('c:u2').ok


# =================================================================================================
# NEGATIVE — the fabrication lanes reject for their INTENDED reason, identity being PROVEN throughout.
# =================================================================================================
def _only_refusal(b, node):
    fails = RA.validate_report([node], b)
    assert fails, 'attack was admitted'
    return ' :: '.join(str(f) for f in fails)


def test_attacks_reject_for_semantic_reason_not_masked_source_policy():
    g, b = _proven_pair()
    assert b.resolve('c:firm').ok and b.resolve('c:region').ok      # identity is PROVEN for both

    # (a) DIRECTION flip — the firm span says employment EXPANDED; the clause says it DECLINED.
    why = _only_refusal(b, Attributed(clauses=(Clause('c:firm',
        'firm-level employment declined at the establishments that adopted the technology'),)))
    assert 'DIRECTION_CONTRADICTS_SPAN' in why and 'SOURCE_POLICY' not in why

    # (b) FABRICATED NUMBER — a magnitude that never appears in the span.
    why = _only_refusal(b, Attributed(clauses=(Clause('c:firm',
        'firm-level employment expanded by 47 percent at the adopting establishments'),)))
    assert 'NUMBER_OR_UNIT_NOT_IN_SPAN' in why and 'SOURCE_POLICY' not in why

    # (c) OWNED sentence carrying a particular — the reviewer's voice may assert none.
    why = _only_refusal(b, Owned(text='The technology doubled regional employment.'))
    assert 'OWNED_' in why and 'SOURCE_POLICY' not in why

    # (d) MODEL TYPES A SOURCE NAME — attribution is rendered from the graph, never typed by the model.
    why = _only_refusal(b, Attributed(clauses=(Clause('c:firm',
        'Nature reports that firm-level employment expanded at the adopting establishments'),)))
    assert 'SOURCE_NAMED_IN_CLAUSE_TEXT' in why and 'SOURCE_POLICY' not in why


# =================================================================================================
# THE POISONED SOURCE-NAME INDEX — function words absent; real names present.
# =================================================================================================
def test_source_words_exclude_function_words():
    g = P.Graph()
    # a corporate byline whose tokens are "the"/"of"/"on"/"behalf" — exactly the poison that placed 0.
    TF._ingest(g, mid='m:corp', doi='10.5/corp', title='A study',
               authors=['on behalf of the INSPIRING Project Consortium'], year=2020,
               venue='American Economic Review', span=REGION_SPAN)
    card = TF._card(g, 'c:corp', 'm:corp', REGION_SPAN, 'employment fell', level='region')
    b = CardBundle([card], g, POLICY)
    for w in ('the', 'of', 'on', 'behalf', 'for', 'and', 'by'):
        assert w not in b._source_words, f'{w!r} poisoned the source-name index'


def test_real_names_and_venue_remain_detectable():
    g, b = _proven_pair()
    # short surnames AND long ones survive
    assert 'wu' in b._source_words
    assert 'acemoglu' in b._source_words
    assert 'ng' in b._source_words
    # a graph venue is detectable (whole distinctive word OR full phrase)
    phrases = b._source_phrases
    assert any('american economic review' in p for p in phrases)
    # the EXACT corporate phrase is a forbidden phrase, its function-word tokens are not
    g2 = P.Graph()
    TF._ingest(g2, mid='m:c', doi='10.5/c', title='A study',
               authors=['on behalf of the INSPIRING Project Consortium'], year=2020,
               venue='American Economic Review', span=REGION_SPAN)
    card = TF._card(g2, 'c:c', 'm:c', REGION_SPAN, 'x', level='region')
    b2 = CardBundle([card], g2, POLICY)
    assert 'on behalf of the inspiring project consortium' in b2._source_phrases


# =================================================================================================
# METAMORPHIC — the behaviour is STRUCTURAL, never keyed on a literal.
# =================================================================================================
def test_metamorphic_rename_is_invariant():
    """Consistently renaming every identifier in BOTH bytes and metadata leaves admission and placement
    unchanged — the gate turns on structure, not on any author/venue/DOI literal."""
    _g1, b1 = _proven_pair(
        names=(('Wu', 'Acemoglu'), ('Ng', 'Restrepo')),
        venues=('American Economic Review', 'Journal of Political Economy'),
        dois=('10.5/firm', '10.5/region'))
    _g2, b2 = _proven_pair(
        names=(('Okoro', 'Tanaka'), ('Silva', 'Novak')),
        venues=('The Lancet', 'Harvard Law Review'),
        dois=('10.7/alpha', '10.7/beta'))
    assert _admitted(b1, 'c:firm', 'c:region') == _admitted(b2, 'c:firm', 'c:region') == 2
    assert _placed(b1, ('c:firm', 'c:region')) == _placed(b2, ('c:firm', 'c:region')) == 1


def test_metamorphic_changing_only_requested_identity_zeroes_the_source():
    """Hold the BYTES fixed (their byline names Wu & Acemoglu); change only the REQUESTED identity to
    other people. Admission and placement for that source must fall to zero — identity is from the bytes,
    and the bytes now testify to someone we did not ask for."""
    g = P.Graph()
    body = TF._scholarly_body('A study', ['Wu', 'Acemoglu'], FIRM_SPAN,
                              masthead='American Economic Review, Volume 12, Number 3, 2021, Pages 1-9.')
    # request a DISJOINT byline: the bytes say Wu & Acemoglu, we ask for Bloom & Draca.
    m = _ingest_raw(g, doi='10.5/req', title='A study', authors=['Bloom', 'Draca'],
                    venue='American Economic Review', body=body, mid='m:req')
    assert m.profile['semantic_binding'] not in IDENTITY_PROVEN
    card = TF._card(g, 'c:req', 'm:req', FIRM_SPAN, 'firm employment rose', level='firm')
    b = CardBundle([card], g, POLICY)
    assert _admitted(b, 'c:req') == 0
    # and no verdict can be built on an unadmitted premise
    assert RA.make_proven_verdict(VERDICT_TEXT, ('c:req', 'c:req'), b) is None


def test_metamorphic_corporate_byline_keeps_prose_usable():
    """A corporate author `on behalf of the <random> Consortium` must NOT forbid common prose tokens
    ('the', 'of', 'behalf'), while the EXACT corporate name stays forbidden in the reviewer's own prose."""
    g = P.Graph()
    TF._ingest(g, mid='m:cb', doi='10.5/cb', title='A study',
               authors=['on behalf of the RANDOMISED Widget Consortium'], year=2020,
               venue='American Economic Review', span=REGION_SPAN)
    card = TF._card(g, 'c:cb', 'm:cb', REGION_SPAN, 'employment fell', level='region')
    b = CardBundle([card], g, POLICY)
    # honest reviewer prose that merely uses function words is NOT refused for naming a source
    ok_prose = Owned(text='On balance, the weight of the evidence is mixed.')
    fails = RA.validate_report([ok_prose], b)
    assert not any('SOURCE' in str(f) for f in fails), fails
    # but the EXACT corporate phrase IS a source the model may not reproduce in its own voice
    named = Owned(text='the RANDOMISED Widget Consortium settles the question')
    assert RA.validate_report([named], b), 'the exact corporate name was allowed in owned prose'


def test_metamorphic_venue_replacement_leaves_verdict_literal_free():
    """Replace every venue; placement is unchanged and the placed verdict text carries NO venue, DOI,
    author, or task-subject literal — only the proved, structural relation."""
    _g, b = _proven_pair(venues=('Some Learned Review', 'Another Learned Journal'),
                         names=(('Park', 'Vasquez'), ('Chen', 'Ober')),
                         dois=('10.3/one', '10.3/two'))
    v = RA.make_proven_verdict(VERDICT_TEXT, ('c:firm', 'c:region'), b)
    assert v is not None
    low = v.text.lower()
    for literal in ('some learned review', 'another learned journal', '10.3/', 'park', 'vasquez',
                    'chen', 'ober', 'artificial intelligence', 'labor market'):
        assert literal not in low, f'the verdict leaked the literal {literal!r}'
