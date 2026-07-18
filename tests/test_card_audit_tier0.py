#!/usr/bin/env python3
"""Acceptance for the Tier-0 deterministic evidence-card screen (Sol §3 Tier 0, Phase 1, Phase 8).

Hermetic: it builds the repo's synthetic bound-card graph (`scripts/_test_fixtures.build`), constructs
a fully v2-shaped card that is deterministically clean, then plants ONE fault at a time and asserts the
INTENDED Tier-0 dimension — and only a determinate outcome — catches it. This is the "removing or
disabling any critical check makes at least one adversary test fail" law, at Tier-0 scope.

No task-72 / DOI / subject literal appears here beyond the neutral synthetic fixture. Every assertion is
about STRUCTURE.
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import provenance as P                       # noqa: E402
import evidence_miner as EM                  # noqa: E402
import _test_fixtures as TF                  # noqa: E402
from card_audit import tier0                 # noqa: E402
from card_audit.audit_schema import (        # noqa: E402
    PASS, FAIL, NOT_APPLICABLE, NEEDS_OPUS, NEEDS_CONTRACT,
    DIM_STRUCTURE, DIM_BINDING, DIM_CACHES, DIM_NUMERIC, DIM_COT, DIM_FACET, DIM_CORROBORATOR,
    RC_SCHEMA_UNKNOWN_FIELD, RC_SCHEMA_DUP_ID, RC_BINDING_SPAN_UNVERIFIED, RC_CACHE_CLAIM_MISMATCH,
    RC_CACHE_COUNTS, RC_NUMERIC_FABRICATED, RC_NUMERIC_UNIT, RC_COT_SCAFFOLD, RC_FACET_NOT_IN_TAXONOMY,
    RC_CORR_INCOMPLETE_BINDING, DERIVED_CACHE, ATOMIC_EVIDENCE_VALUE, SOURCE_BYTES, EMPTY,
    CONTENT_CLASSES,
)

POLICY = P.JOURNAL_ONLY
TAXONOMY = frozenset({'automation', 'labor'})


def _tagger(_span: str) -> list[str]:
    return ['automation']


def _base_fields():
    """The full closed v2 surface, every optional field present-but-empty so only what we set is live."""
    return dict(
        claim='', span='', span_raw='', span_start=-1, span_end=-1, span_numbers=[], has_number=False,
        level='', horizon='', method='', mechanisms=[], doi='', authors=[], venue='', year='',
        attribution='', source='', work_id='', evidence_unit_id='', expression_id='',
        attribution_target_expression_id='', permitted_expression_ids=[], manifestation_id='',
        content_hash='', source_policy='', act='', act_registry_version=EM.REGISTRY.version,
        card_kind='qualitative', effect='', unit='', comparator='', outcome='', finding='', holding='',
        authority='', recommendation='', limitation='', population='', geography='', period='',
        technology='', industry='', unit_of_analysis='', design='', uncertainty='', study_design='',
        geographic_scope='', section='results', section_weight=0.5, context_start=0, context_end=10,
        field_provenance={}, source_version='', text_field='fulltext', facet_tags=['automation'],
        facet_tags_span=['automation'], complete_tuple=False, corroborating_sources=[],
        same_unit_other_expressions=[], n_sources=1, n_evidence_units=1,
    )


@pytest.fixture(scope='module')
def graph_and_clean():
    g, _ = TF.build()
    # Stamp a positive identity verdict on the synthetic bytes so resolve_attribution admits them —
    # in production the miner writes this profile field; the fixture graph does not. SAME_WORK is an
    # IDENTITY_PROVEN member. (This is test scaffolding only; the screen reads the verdict, never sets it.)
    _kind_verdict = {'journal_version': 'VERSION_OF_PUBLISHED', 'working_paper': 'VERSION_OF_PREPRINT'}
    for m in g.manifestations.values():
        kind = g.expressions[m.expression_id].kind
        m.profile['semantic_binding'] = _kind_verdict.get(kind, 'SAME_WORK')
    mid = 'm:bres'
    m = g.manifestations[mid]
    span = TF.BRES_SPAN
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    att = g.resolve_attribution(b, POLICY)
    assert att.admitted, att.refusal
    w = g.works[m.work_id]
    # a finding that is a verbatim slice of the span (so the CoT test can prove it clean offline)
    finding = 'Computer automation of such work has been correspondingly limited in its scope'
    card = _base_fields()
    card.update(
        id='c:clean', manifestation_id=mid, content_hash=b['content_hash'],
        span_start=s, span_end=s + len(span), span_raw=b['text'], span=span,
        expression_id=b['expression_id'], permitted_expression_ids=list(b['permitted_expression_ids']),
        attribution_target_expression_id=att.names_expression_id,
        attribution=att.text or '', work_id=m.work_id, evidence_unit_id=m.work_id,
        authors=w.authors, venue=w.venue, year=w.year, doi=w.doi, source_version=m.content_hash[:12],
        source_policy=POLICY.name, act='qualitative_empirical_result', finding=finding,
    )
    act = EM.REGISTRY.acts['qualitative_empirical_result']
    card['claim'] = EM.derive_claim(card, act)
    card['span_numbers'] = sorted(EM.number_tokens(span))
    card['has_number'] = bool(card['span_numbers'])
    return g, card


def _screen(card, g):
    return tier0.screen_card(card, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger, json_pointer='/0')


def test_clean_card_passes_every_deterministic_dimension(graph_and_clean):
    g, card = graph_and_clean
    r = _screen(card, g)
    for name, d in r.dimensions.items():
        assert d.verdict in (PASS, NOT_APPLICABLE), f'{name} -> {d.verdict} :: {d.detail}'
    assert r.overall == PASS, [d.detail for d in r.dimensions.values() if d.verdict == FAIL]
    # every non-empty field got a legal content class, none unclassified
    for c in r.content_classes:
        assert c.content_class in (CONTENT_CLASSES | {''})
        assert c.verdict == PASS, f'{c.field} -> {c.verdict} ({c.reason_code})'
    # the display cache recomputes; the finding is proven source bytes
    classes = {c.field: c for c in r.content_classes}
    assert classes['claim'].content_class == DERIVED_CACHE
    assert classes['finding'].content_class == ATOMIC_EVIDENCE_VALUE
    assert classes['span_raw'].content_class == SOURCE_BYTES


def test_receipt_is_deterministic(graph_and_clean):
    g, card = graph_and_clean
    a, b = _screen(card, g).to_json(), _screen(card, g).to_json()
    assert a == b
    # renaming the id changes only the row id and card_id, never a verdict (metamorphic)
    renamed = copy.deepcopy(card)
    renamed['id'] = 'c:clean-renamed'
    r0, r1 = _screen(card, g), _screen(renamed, g)
    assert {k: v.verdict for k, v in r0.dimensions.items()} == \
           {k: v.verdict for k, v in r1.dimensions.items()}


# ---- planted single-fault adversaries: each caught by its INTENDED dimension --------------------

def test_unknown_field_fails_structure(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['reasoning_trace'] = 'let me think about which number to pick'
    r = _screen(bad, g)
    assert r.dimensions[DIM_STRUCTURE].verdict == FAIL
    assert RC_SCHEMA_UNKNOWN_FIELD in r.dimensions[DIM_STRUCTURE].reason_codes
    assert r.overall == FAIL


def test_tampered_offsets_fail_binding(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['span_end'] = bad['span_start']          # empty/reversed window: text[s:s] == ''
    r = _screen(bad, g)
    assert r.dimensions[DIM_BINDING].verdict == FAIL
    assert RC_BINDING_SPAN_UNVERIFIED in r.dimensions[DIM_BINDING].reason_codes


def test_wrong_content_hash_fails_binding(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['content_hash'] = hashlib.sha256(b'not the bytes').hexdigest()
    assert _screen(bad, g).dimensions[DIM_BINDING].verdict == FAIL


def test_claim_not_derive_claim_fails_caches(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['claim'] = 'Automation doubled worldwide, causing mass unemployment.'
    r = _screen(bad, g)
    assert r.dimensions[DIM_CACHES].verdict == FAIL
    assert RC_CACHE_CLAIM_MISMATCH in r.dimensions[DIM_CACHES].reason_codes


def test_fabricated_number_fails_numeric(graph_and_clean):
    """A claim that asserts a figure the span never states (Sol §Numeric): caught mechanically, offline.
    We build a numeric card on the LEAK span (span says 10.25) and claim a fabricated 0.2."""
    g, _ = graph_and_clean
    mid = 'm:leak'
    m = g.manifestations[mid]
    span = TF.LEAK_SPAN
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    att = g.resolve_attribution(b, POLICY)
    w = g.works[m.work_id]
    card = _base_fields()
    card.update(
        id='c:num', manifestation_id=mid, content_hash=b['content_hash'], span_start=s,
        span_end=s + len(span), span_raw=b['text'], span=span, expression_id=b['expression_id'],
        permitted_expression_ids=list(b['permitted_expression_ids']),
        attribution_target_expression_id=att.names_expression_id, attribution=att.text or '',
        work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, venue=w.venue, year=w.year,
        doi=w.doi, source_version=m.content_hash[:12], source_policy=POLICY.name,
        act='qualitative_empirical_result', finding='productivity growth of 10.25 percent was observed',
    )
    card['span_numbers'] = sorted(EM.number_tokens(span))
    card['has_number'] = True
    act = EM.REGISTRY.acts['qualitative_empirical_result']
    card['claim'] = EM.derive_claim(card, act)
    # honest numeric card first: numeric dimension must not fire
    assert tier0.screen_card(card, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                             json_pointer='/0').dimensions[DIM_NUMERIC].verdict in (PASS, NOT_APPLICABLE)
    # now inject a fabricated number into the claim cache (bypassing derive) -> numeric FAIL
    bad = copy.deepcopy(card)
    bad['claim'] = 'productivity fell 0.2 percent'
    r = tier0.screen_card(bad, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger, json_pointer='/0')
    assert r.dimensions[DIM_NUMERIC].verdict == FAIL
    assert RC_NUMERIC_FABRICATED in r.dimensions[DIM_NUMERIC].reason_codes


def test_percent_vs_pp_swap_fails_numeric(graph_and_clean):
    g, _ = graph_and_clean
    mid = 'm:ar'                                  # AR span: "0.2 percentage points"
    m = g.manifestations[mid]
    span = TF.AR_SPAN
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    card = _base_fields()
    card.update(
        id='c:pp', manifestation_id=mid, content_hash=b['content_hash'], span_start=s,
        span_end=s + len(span), span_raw=b['text'], span=span, expression_id=b['expression_id'],
        permitted_expression_ids=list(b['permitted_expression_ids']),
        work_id=m.work_id, evidence_unit_id=m.work_id, source_policy=POLICY.name,
        act='qualitative_empirical_result', finding='employment falls',
        claim='employment falls 0.2 percent',    # span says percentage POINTS, claim says percent
        span_numbers=sorted(EM.number_tokens(span)), has_number=True,
    )
    r = tier0.screen_card(card, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger, json_pointer='/0')
    assert r.dimensions[DIM_NUMERIC].verdict == FAIL
    assert RC_NUMERIC_UNIT in r.dimensions[DIM_NUMERIC].reason_codes


def test_cot_scaffold_field_fails_cot(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['finding'] = '{"reason": "the user wants a strong finding", "pick": "option 2"}'
    r = _screen(bad, g)
    assert r.dimensions[DIM_COT].verdict == FAIL
    assert RC_COT_SCAFFOLD in r.dimensions[DIM_COT].reason_codes


def test_offtopic_facet_not_in_taxonomy_fails_facet(graph_and_clean):
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['facet_tags_span'] = ['oncology']        # not a member of the pinned taxonomy
    bad['facet_tags'] = ['oncology']
    r = tier0.screen_card(bad, g, POLICY, taxonomy=TAXONOMY, tagger=None, json_pointer='/0')
    assert r.dimensions[DIM_FACET].verdict == FAIL
    assert RC_FACET_NOT_IN_TAXONOMY in r.dimensions[DIM_FACET].reason_codes


def test_unpinned_taxonomy_never_silently_passes(graph_and_clean):
    g, card = graph_and_clean
    r = tier0.screen_card(card, g, POLICY, taxonomy=None, tagger=None, json_pointer='/0')
    assert r.dimensions[DIM_FACET].verdict == NEEDS_CONTRACT
    assert r.overall == NEEDS_OPUS               # never composer-ready without a pinned contract


def test_incomplete_corroborator_binding_fails_edge(graph_and_clean):
    """The live miner serializes corroborators WITHOUT span_raw / permitted_expression_ids — Sol's
    lossy-consolidation defect. A nested edge that cannot be independently verified must fail."""
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['corroborating_sources'] = [dict(
        manifestation_id='m:autor', content_hash='x', span_start=1, span_end=2,
        evidence_unit_id='w:autor', span='some corroborating prose',   # no span_raw, no permitted ids
    )]
    bad['n_sources'] = 2
    bad['n_evidence_units'] = 2
    r = _screen(bad, g)
    assert r.dimensions[DIM_CORROBORATOR].verdict == FAIL
    assert RC_CORR_INCOMPLETE_BINDING in r.dimensions[DIM_CORROBORATOR].reason_codes
    # and the inflated count (2 stored, 1 verifiable) is caught independently
    assert r.dimensions[DIM_CACHES].verdict == FAIL
    assert RC_CACHE_COUNTS in r.dimensions[DIM_CACHES].reason_codes


def test_duplicate_id_is_caught_at_census(graph_and_clean):
    g, card = graph_and_clean
    twin = copy.deepcopy(card)
    receipts = tier0.screen_corpus([card, twin], g, POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    assert all(RC_SCHEMA_DUP_ID in r.dimensions[DIM_STRUCTURE].reason_codes for r in receipts)
    # distinct audit_row_ids despite the identical id, so neither record can hide the other
    assert receipts[0].audit_row_id != receipts[1].audit_row_id


def test_compound_canary_caught_in_multiple_dimensions(graph_and_clean):
    """Sol Phase 8 compound canary: one card carrying several planted faults; every dimension runs even
    after the first failure, and the final overall is FAIL."""
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['span_end'] = bad['span_start']                       # fabricated/empty binding
    bad['finding'] = '```json\n{"step": 1}\n```'             # CoT scaffold
    bad['claim'] = 'employment doubled 999 percent worldwide'  # fabricated number
    bad['facet_tags_span'] = ['oncology']                     # off-topic
    r = _screen(bad, g)
    assert r.dimensions[DIM_BINDING].verdict == FAIL
    assert r.dimensions[DIM_COT].verdict == FAIL
    assert r.dimensions[DIM_NUMERIC].verdict == FAIL
    assert r.dimensions[DIM_FACET].verdict == FAIL
    assert r.overall == FAIL
