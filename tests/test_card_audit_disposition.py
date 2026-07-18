#!/usr/bin/env python3
"""Acceptance for the DISPOSITION engine (Sol §4 disposition rules, Phase 4 adjudication/repair).

HERMETIC. No real Opus call: the Opus transport is injected as a deterministic stub and the report-AST
faithfulness judge is stubbed, exactly as the Tier-1/2/3 harness test does. Every repairing disposition
is rebuilt as a NEW object and RE-RUN through the deterministic screen (and the full ladder when a runner
is injected); a repair that does not hold falls closed to quarantine; and the corpus census must reconcile
so nothing is silently dropped.

Every assertion is about STRUCTURE. No task-72 / DOI / subject literal drives a verdict (Sol Phase 8).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import provenance as P                       # noqa: E402
import evidence_miner as EM                  # noqa: E402
import report_ast as RA                      # noqa: E402
import _test_fixtures as TF                  # noqa: E402
from card_audit import tier0, harness, disposition as D  # noqa: E402
from card_audit.audit_schema import PASS, FAIL, UNCERTAIN  # noqa: E402

POLICY = P.JOURNAL_ONLY
TAXONOMY = frozenset({'automation', 'labor'})
QUESTION = 'What is the measured effect under study?'
FACETS = ['automation', 'labor']


def _tagger(_span: str) -> list[str]:
    return ['automation']


def _base_fields():
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


def _bind(g, mid, span):
    m = g.manifestations[mid]
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    return m, s, b


def _edge(g, mid, span):
    """A complete, independently-verifying corroborating support edge."""
    m, s, b = _bind(g, mid, span)
    return dict(
        manifestation_id=mid, content_hash=b['content_hash'], span_start=s, span_end=s + len(span),
        span_raw=b['text'], span=span, permitted_expression_ids=list(b['permitted_expression_ids']),
        expression_id=b['expression_id'], work_id=m.work_id, evidence_unit_id=m.work_id)


@pytest.fixture()
def g():
    graph, _ = TF.build()
    _kv = {'journal_version': 'VERSION_OF_PUBLISHED', 'working_paper': 'VERSION_OF_PREPRINT'}
    for m in graph.manifestations.values():
        m.profile['semantic_binding'] = _kv.get(graph.expressions[m.expression_id].kind, 'SAME_WORK')
    return graph


def _clean_card(g, *, finding=None, corroborators=None, n=1):
    mid = 'm:bres'
    span = TF.BRES_SPAN
    m, s, b = _bind(g, mid, span)
    att = g.resolve_attribution(b, POLICY)
    assert att.admitted, att.refusal
    w = g.works[m.work_id]
    finding = finding if finding is not None else \
        'Computer automation of such work has been correspondingly limited in its scope'
    card = _base_fields()
    card.update(
        id='c:clean', manifestation_id=mid, content_hash=b['content_hash'],
        span_start=s, span_end=s + len(span), span_raw=b['text'], span=span,
        expression_id=b['expression_id'], permitted_expression_ids=list(b['permitted_expression_ids']),
        attribution_target_expression_id=att.names_expression_id, attribution=att.text or '',
        work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, venue=w.venue, year=w.year,
        doi=w.doi, source_version=m.content_hash[:12], source_policy=POLICY.name,
        act='qualitative_empirical_result', finding=finding,
        corroborating_sources=list(corroborators or []), n_sources=n, n_evidence_units=n,
    )
    act = EM.REGISTRY.acts['qualitative_empirical_result']
    card['claim'] = EM.derive_claim(card, act)
    card['span_numbers'] = sorted(EM.number_tokens(span))
    card['has_number'] = bool(card['span_numbers'])
    return card


def _receipt(card, g):
    return tier0.screen_card(card, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger, json_pointer='/0')


def _combined(rid, disp, final=PASS, rcs=None):
    return harness.CombinedVerdict(rid, final, False, disp, rcs or [], '')


def _entailed():
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))


# =================================================================================================
# Lineage hash and the typed-repair firewall (Sol §REPAIR_TIGHTEN 2-3)
# =================================================================================================
def test_content_hash_stable_and_sensitive(g):
    c = _clean_card(g)
    h1 = D.card_content_hash(c)
    assert h1 == D.card_content_hash(copy.deepcopy(c))
    c2 = copy.deepcopy(c)
    c2['finding'] = c2['finding'] + ' slightly'
    assert D.card_content_hash(c2) != h1


def test_repair_refuses_immutable_field():
    p = D.RepairProposal(field_changes={'span_raw': 'a lie'})
    assert D.RC_REPAIR_TOUCHED_IMMUTABLE in D.validate_repair_proposal(p)


def test_repair_refuses_derived_cache_field():
    p = D.RepairProposal(field_changes={'claim': 'model-written prose'})
    assert D.RC_REPAIR_TOUCHED_DERIVED in D.validate_repair_proposal(p)


def test_repair_refuses_unknown_field():
    p = D.RepairProposal(field_changes={'nonexistent_field': 'x'})
    assert D.RC_REPAIR_UNKNOWN_FIELD in D.validate_repair_proposal(p)


def test_legal_typed_repair_passes_validation():
    assert D.validate_repair_proposal(D.RepairProposal(field_changes={'finding': 'narrower'})) == []


# =================================================================================================
# REPAIR_TIGHTEN — typed change, claim RECOMPUTED, deterministic dims RE-RUN (Sol §REPAIR_TIGHTEN)
# =================================================================================================
def test_repair_tighten_recomputes_claim_and_reruns(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    # tighten to a NARROWER supported slice of the same span
    narrower = 'Computer automation of such work has been correspondingly limited'
    proposal = D.RepairProposal(field_changes={'finding': narrower})
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                             graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                             proposal=proposal)
    finally:
        RA.set_entailment_judge(None)
    assert out.disposition == D.REPAIR_TIGHTEN and out.bucket == D.BUCKET_REPAIRED
    assert out.result_card is not None
    # the claim was recomputed by derive_claim, NOT taken from the proposal
    act = EM.REGISTRY.acts['qualitative_empirical_result']
    assert out.result_card['claim'] == EM.derive_claim(out.result_card, act)
    assert 'finding' in out.changed_fields and 'claim' in out.changed_fields
    assert out.rerun_overall != FAIL
    # source bytes stayed immutable
    assert out.result_card['span_raw'] == card['span_raw']
    assert out.result_card['content_hash'] == card['content_hash']


def test_repair_tighten_without_proposal_fails_closed(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger, proposal=None)
    assert out.bucket == D.BUCKET_QUARANTINED and D.RC_REPAIR_NO_PROPOSAL in out.reason_codes


def test_repair_tighten_illegal_field_fails_closed(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    p = D.RepairProposal(field_changes={'content_hash': 'deadbeef'})
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger, proposal=p)
    assert out.bucket == D.BUCKET_QUARANTINED
    assert D.RC_REPAIR_TOUCHED_IMMUTABLE in out.reason_codes


def test_repair_that_still_fails_is_quarantined_not_kept(g):
    """Sol: nothing silently dropped. A tighten whose recomputed claim FABRICATES a number the span does
    not carry fails the deterministic numeric rerun and is quarantined, never kept."""
    card = _clean_card(g)
    rec = _receipt(card, g)
    # inject a fabricated number into the finding -> derive_claim carries "88" -> numeric rerun FAILS
    bad = D.RepairProposal(field_changes={'finding': 'automation rose by 88 percent everywhere'})
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                             graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger, proposal=bad)
    finally:
        RA.set_entailment_judge(None)
    assert out.bucket == D.BUCKET_QUARANTINED and D.RC_REPAIR_RERUN_FAILED in out.reason_codes


# =================================================================================================
# REMOVE_BAD_SUPPORT_EDGE — retain primary, quarantine bad edge, recompute counts (Sol §REMOVE)
# =================================================================================================
def test_remove_bad_support_edge_recomputes_counts(g):
    good = _edge(g, 'm:autor', TF.AUTOR_SPAN)
    bad = _edge(g, 'm:leak', TF.LEAK_SPAN)
    del bad['span_raw']                                   # incomplete nested binding -> unverifiable
    card = _clean_card(g, corroborators=[good, bad], n=2)  # verified units = primary + good = 2
    rec = _receipt(card, g)
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.REMOVE_BAD_SUPPORT_EDGE, final=FAIL), rec,
                             graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    finally:
        RA.set_entailment_judge(None)
    assert out.disposition == D.REMOVE_BAD_SUPPORT_EDGE and out.bucket == D.BUCKET_REPAIRED
    # the good edge is kept, the bad edge quarantined WITH a reason — never hidden
    kept = [e for e in out.edge_dispositions if e.bucket == D.EDGE_KEPT]
    quar = [e for e in out.edge_dispositions if e.bucket == D.EDGE_QUARANTINED]
    assert len(kept) == 1 and len(quar) == 1 and quar[0].quarantine_reason
    # counts recomputed to the independently-verified units (still 2), and one edge dropped
    assert out.result_card['n_sources'] == 2 and out.result_card['n_evidence_units'] == 2
    assert len(out.result_card['corroborating_sources']) == 1


# =================================================================================================
# REBASE_TO_VALID_SUPPORT — rebuild a complete binding, collision-safe id, recompute (Sol §REBASE)
# =================================================================================================
def test_apply_rebase_rebuilds_primary_from_corroborator(g):
    edge = _edge(g, 'm:autor', TF.AUTOR_SPAN)
    card = _clean_card(g, corroborators=[edge], n=2)
    new, rcs = D.apply_rebase(card, 0, g, POLICY, existing_ids=frozenset({card['id']}))
    assert new is not None and rcs == []
    # a fresh collision-safe id, the corroborator's bytes promoted, and identity recomputed from the graph
    assert new['id'] != card['id']
    assert new['manifestation_id'] == 'm:autor' and new['span_raw'] == edge['span_raw']
    m = g.manifestations['m:autor']
    assert new['work_id'] == m.work_id and new['expression_id'] == m.expression_id
    assert new['corroborating_sources'] == []            # promoted edge left the corroborator list


def test_dispose_rebase_routes_and_holds(g):
    edge = _edge(g, 'm:autor', TF.AUTOR_SPAN)
    card = _clean_card(g, corroborators=[edge], n=2)
    rec = _receipt(card, g)
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.REBASE_TO_VALID_SUPPORT, final=FAIL), rec,
                             graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                             existing_ids=frozenset({card['id']}))
    finally:
        RA.set_entailment_judge(None)
    assert out.disposition == D.REBASE_TO_VALID_SUPPORT and out.bucket == D.BUCKET_REPAIRED
    assert out.result_card['manifestation_id'] == 'm:autor'


def test_dispose_rebase_with_no_valid_support_quarantines(g):
    card = _clean_card(g, corroborators=[], n=1)
    rec = _receipt(card, g)
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.REBASE_TO_VALID_SUPPORT, final=FAIL), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    assert out.bucket == D.BUCKET_QUARANTINED and D.RC_REBASE_NO_VALID_SUPPORT in out.reason_codes


# =================================================================================================
# DEMOTE_TO_OWNED_SUGGESTION — the gate IS report_ast.validate_node(Owned(...)) (Sol §DEMOTE)
# =================================================================================================
def _bundle(g, cards):
    return RA.CardBundle(cards, g, POLICY)


def test_demote_number_bearing_owned_is_rejected(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    bundle = _bundle(g, [card])
    p = D.RepairProposal(owned_text='This frame carries a number 42 and must be refused')
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.DEMOTE_TO_OWNED_SUGGESTION, final=FAIL),
                             rec, graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                             proposal=p, bundle=bundle)
    finally:
        RA.set_entailment_judge(None)
    assert out.bucket == D.BUCKET_QUARANTINED and D.RC_DEMOTE_OWNED_REJECTED in out.reason_codes


def test_demote_of_unreachable_card_is_voice_launder_blocked(g):
    card = _clean_card(g)
    card['span_end'] = card['span_start']                 # unreachable binding -> no bytes to demote from
    rec = _receipt(card, g)
    bundle = _bundle(g, [card])
    p = D.RepairProposal(owned_text='A perfectly clean reviewer frame')
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.DEMOTE_TO_OWNED_SUGGESTION, final=FAIL),
                         rec, graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                         proposal=p, bundle=bundle)
    assert out.bucket == D.BUCKET_QUARANTINED and D.RC_DEMOTE_VOICE_LAUNDER in out.reason_codes


def test_valid_owned_frame_demotes_to_owned_suggestion(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    bundle = _bundle(g, [card])
    # a clean frame: names no source, carries no number, asserts no first-order finding
    frame = 'The reviewed literature is organized below by theme'
    assert D.validate_owned_demotion(frame, (), bundle) == [], 'fixture frame must be a clean OWNED node'
    _entailed()
    try:
        out = D.dispose_card(card, _combined(rec.audit_row_id, D.DEMOTE_TO_OWNED_SUGGESTION, final=FAIL),
                             rec, graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                             proposal=D.RepairProposal(owned_text=frame), bundle=bundle)
    finally:
        RA.set_entailment_judge(None)
    assert out.disposition == D.DEMOTE_TO_OWNED_SUGGESTION and out.bucket == D.BUCKET_DEMOTED
    # it moves to owned_suggestions, NOT audited_cards, and is not citeable evidence
    assert out.owned_suggestion is not None and out.result_card is None
    assert out.owned_suggestion['demoted_from_card_id'] == card['id']


# =================================================================================================
# KEEP / QUARANTINE passthrough
# =================================================================================================
def test_keep_unchanged_ships_the_card(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.KEEP_UNCHANGED, final=PASS), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    assert out.bucket == D.BUCKET_KEPT and out.result_card is not None
    assert out.result_hash == out.original_hash


def test_quarantine_card_carries_its_edges(g):
    edge = _edge(g, 'm:autor', TF.AUTOR_SPAN)
    card = _clean_card(g, corroborators=[edge], n=2)
    rec = _receipt(card, g)
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.QUARANTINE_CARD, final=FAIL,
                                         rcs=[D.RC_QUARANTINE]), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    assert out.bucket == D.BUCKET_QUARANTINED and out.result_card is None
    # the support edge is quarantined WITH the card, never hidden
    assert all(e.bucket == D.EDGE_QUARANTINED for e in out.edge_dispositions)


# =================================================================================================
# Corpus reconciliation — the accounting invariant (Sol Phase 4 acceptance): nothing unaccounted
# =================================================================================================
def test_reconcile_accounts_every_row_and_edge(g):
    edge = _edge(g, 'm:autor', TF.AUTOR_SPAN)
    keep = _clean_card(g)
    keep['id'] = 'c:keep'
    withedge = _clean_card(g, corroborators=[edge], n=2)
    withedge['id'] = 'c:withedge'
    inputs = [keep, withedge]
    _entailed()
    try:
        d1 = D.dispose_card(keep, _combined(_receipt(keep, g).audit_row_id, D.KEEP_UNCHANGED, final=PASS),
                            _receipt(keep, g), graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
        d2 = D.dispose_card(withedge, _combined(_receipt(withedge, g).audit_row_id, D.KEEP_UNCHANGED,
                                                final=PASS),
                            _receipt(withedge, g), graph=g, policy=POLICY, taxonomy=TAXONOMY,
                            tagger=_tagger)
    finally:
        RA.set_entailment_judge(None)
    census = D.reconcile_corpus([d1, d2], inputs)
    assert census['reconciled'] is True
    assert census['input_top_level'] == 2
    assert census['input_support_edges'] == 1
    assert sum(census['top_level'].values()) == 2
    assert sum(census['support_edges'].values()) == 1


def test_reconcile_raises_on_unaccounted_row(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    out = D.dispose_card(card, _combined(rec.audit_row_id, D.KEEP_UNCHANGED, final=PASS), rec,
                         graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger)
    # two input cards but only one disposition -> the census MUST refuse to reconcile
    with pytest.raises(D.AccountingError):
        D.reconcile_corpus([out], [card, _clean_card(g)])


# =================================================================================================
# Generality / metamorphic (Sol Phase 8): renaming subject/facets changes no disposition
# =================================================================================================
def test_question_and_facet_rename_change_no_disposition(g):
    card = _clean_card(g)
    rec = _receipt(card, g)
    proposal = D.RepairProposal(field_changes={'finding':
                                'Computer automation of such work has been correspondingly limited'})
    _entailed()
    try:
        a = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                           graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                           question=QUESTION, contract_facets=FACETS, proposal=proposal)
        b = D.dispose_card(card, _combined(rec.audit_row_id, D.REPAIR_TIGHTEN, final=FAIL), rec,
                           graph=g, policy=POLICY, taxonomy=TAXONOMY, tagger=_tagger,
                           question='What is the treatment effect on mortality?',
                           contract_facets=['oncology', 'survival'], proposal=proposal)
    finally:
        RA.set_entailment_judge(None)
    assert a.disposition == b.disposition == D.REPAIR_TIGHTEN
    assert a.bucket == b.bucket == D.BUCKET_REPAIRED


def test_no_task_literal_in_module():
    src = Path(D.__file__).read_text(encoding='utf-8')
    for banned in ('task-72', 'task72', '10.1086', 'Acemoglu', 'Bresnahan', 'automation'):
        assert banned.lower() not in src.lower(), f'generality breach: {banned!r} literal in disposition.py'
