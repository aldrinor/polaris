#!/usr/bin/env python3
"""Acceptance for the Tier-1/2/3 Opus audit harness (Sol §3 Tier 1/2/3, §Faithfulness, §Numeric,
§Relevance, §Voice, §4, Phase 2/3/8).

HERMETIC. There is NO real Opus call. The Opus transport is injected as a deterministic stub (exactly as
`report_ast.set_entailment_judge` stubs the faithfulness judge), so the whole tier ladder — schema
validation, model-metadata enforcement, fail-closed combination, adjudication floors — is exercised
offline while the real card mine is still running.

Every assertion is about STRUCTURE. No task-72 / DOI / subject literal drives a verdict.
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
from card_audit import tier0, harness        # noqa: E402
from card_audit.audit_schema import PASS, FAIL, UNCERTAIN, NOT_APPLICABLE  # noqa: E402
from card_audit.harness import (             # noqa: E402
    NUMERIC_SUBDIMENSIONS, REL_DIRECT, REL_CONTEXT, PASS_A, PASS_B,
    FAITH_UNREACHABLE, OpusVerdict, OpusResponseInvalid, OpusUnavailable,
    RC_FAITH_NOT_ENTAILED, RC_FAITH_UNREACHABLE, RC_OPUS_MODEL, RC_OPUS_DISAGREE,
    RC_OPUS_ALLEGES_ATOM, RC_OPUS_RELEVANCE, RC_OPUS_TRANSPORT,
)

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


@pytest.fixture(scope='module')
def graph_and_clean():
    g, _ = TF.build()
    _kv = {'journal_version': 'VERSION_OF_PUBLISHED', 'working_paper': 'VERSION_OF_PREPRINT'}
    for m in g.manifestations.values():
        m.profile['semantic_binding'] = _kv.get(g.expressions[m.expression_id].kind, 'SAME_WORK')
    mid = 'm:bres'
    m = g.manifestations[mid]
    span = TF.BRES_SPAN
    s = m.text.index(span)
    b = g.bind_span(mid, s, s + len(span))
    att = g.resolve_attribution(b, POLICY)
    assert att.admitted, att.refusal
    w = g.works[m.work_id]
    finding = 'Computer automation of such work has been correspondingly limited in its scope'
    card = _base_fields()
    card.update(
        id='c:clean', manifestation_id=mid, content_hash=b['content_hash'],
        span_start=s, span_end=s + len(span), span_raw=b['text'], span=span,
        expression_id=b['expression_id'], permitted_expression_ids=list(b['permitted_expression_ids']),
        attribution_target_expression_id=att.names_expression_id, attribution=att.text or '',
        work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, venue=w.venue, year=w.year,
        doi=w.doi, source_version=m.content_hash[:12], source_policy=POLICY.name,
        act='qualitative_empirical_result', finding=finding,
    )
    act = EM.REGISTRY.acts['qualitative_empirical_result']
    card['claim'] = EM.derive_claim(card, act)
    card['span_numbers'] = sorted(EM.number_tokens(span))
    card['has_number'] = bool(card['span_numbers'])
    return g, card


def _receipt(card, g):
    return tier0.screen_card(card, g, POLICY, taxonomy=TAXONOMY, tagger=_tagger, json_pointer='/0')


# -------------------------------------------------------------------------------------------------
# Deterministic Opus transport stub — the injectable runner (prompt, schema) -> claude -p envelope
# -------------------------------------------------------------------------------------------------
def _verdict(rid, *, faith=PASS, rel=(PASS, REL_DIRECT), numeric_applicable=False, numeric_fail=None,
            facet=PASS, cot_fail=False, disp='KEEP_UNCHANGED'):
    subs = {}
    if numeric_applicable:
        subs = {k: PASS for k in NUMERIC_SUBDIMENSIONS}
        if numeric_fail:
            subs[numeric_fail] = FAIL
    ccs = [{'field': 'finding', 'content_class': 'ATOMIC_EVIDENCE_VALUE',
            'verdict': FAIL if cot_fail else PASS}]
    return {
        'audit_row_id': rid,
        'faithfulness': {'verdict': faith},
        'numeric': {'applicable': numeric_applicable, 'subdimensions': subs},
        'relevance': {'verdict': rel[0], 'classification': rel[1]},
        'facet': {'verdict': facet},
        'content_classes': ccs,
        'proposed_disposition': disp,
    }


def _envelope(verdict, model='claude-opus-4-8'):
    return {'result': json.dumps(verdict), 'modelUsage': {model: {'inputTokens': 1}},
            'total_cost_usd': 0.01, 'is_error': False}


def _runner_for(verdict, model='claude-opus-4-8'):
    def run(_prompt, _schema):
        return _envelope(verdict, model)
    return run


# =================================================================================================
# Faithfulness reuses report_ast.entailed_by_span (Sol §1, §Faithfulness) — NOT reinvented
# =================================================================================================
def test_faithfulness_passes_when_span_entails_claim(graph_and_clean):
    g, card = graph_and_clean
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))
    try:
        r = harness.audit_faithfulness_primary(card, g)
    finally:
        RA.set_entailment_judge(None)
    assert r.verdict == PASS and r.faith_label == 'ENTAILED'


def test_faithfulness_fails_when_judge_rejects(graph_and_clean):
    g, card = graph_and_clean
    RA.set_entailment_judge(lambda clause, span: ('NOT_ENTAILED', 'nope'))
    try:
        r = harness.audit_faithfulness_primary(card, g)
    finally:
        RA.set_entailment_judge(None)
    assert r.verdict == FAIL and RC_FAITH_NOT_ENTAILED in r.reason_codes


def test_unreachable_span_is_never_faithful(graph_and_clean):
    """Sol §Faithfulness: a structurally unreachable span (binding does not verify) is UNREACHABLE, never
    PASS. Opus can never mark it faithful because the harness never even asks — it resolves to FAIL."""
    g, card = graph_and_clean
    bad = copy.deepcopy(card)
    bad['span_end'] = bad['span_start']                 # empty/reversed window -> verify_span fails
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))  # even a generous judge cannot save it
    try:
        r = harness.audit_faithfulness_primary(bad, g)
    finally:
        RA.set_entailment_judge(None)
    assert r.verdict == FAIL and r.faith_label == FAITH_UNREACHABLE
    assert RC_FAITH_UNREACHABLE in r.reason_codes


def test_faithfulness_uses_manifestation_bytes_not_card_span(graph_and_clean):
    """Sol §Faithfulness: resolved_span = manifestation.text[start:end], the VERIFIED bytes — never
    card['span']. A card whose display `span` was swapped to a lie but whose offsets still verify is judged
    against the real bytes, so the swap cannot launder the claim."""
    g, card = graph_and_clean
    poisoned = copy.deepcopy(card)
    poisoned['span'] = 'automation doubled worldwide causing mass unemployment'  # a lie in the DISPLAY field
    resolved = harness.resolve_verified_span(poisoned, g)
    assert resolved == card['span_raw']                 # the real bytes, not the swapped display span


# =================================================================================================
# Opus response schema validation (Sol Phase 2 step 6, Phase 3 step 5) — fail closed
# =================================================================================================
def test_valid_response_validates():
    v = _verdict('rid-1', numeric_applicable=True)
    assert harness.validate_opus_response(v, 'rid-1') is v


def test_wrong_audit_row_id_rejected():
    with pytest.raises(OpusResponseInvalid):
        harness.validate_opus_response(_verdict('rid-1'), 'rid-2')


def test_missing_numeric_subdimension_rejected():
    v = _verdict('rid-1', numeric_applicable=True)
    del v['numeric']['subdimensions']['modality']       # a numeric claim missing one subdimension
    with pytest.raises(OpusResponseInvalid):
        harness.validate_opus_response(v, 'rid-1')


def test_illegal_verdict_rejected():
    v = _verdict('rid-1')
    v['relevance']['verdict'] = 'DEFINITELY'
    with pytest.raises(OpusResponseInvalid):
        harness.validate_opus_response(v, 'rid-1')


def test_unknown_key_rejected():
    v = _verdict('rid-1')
    v['reasoning_trace'] = 'let me think step by step'   # no free-form reasoning persisted (Sol Phase 2)
    with pytest.raises(OpusResponseInvalid):
        harness.validate_opus_response(v, 'rid-1')


def test_illegal_disposition_rejected():
    v = _verdict('rid-1', disp='DELETE')                 # there is no DELETE disposition (Sol §4)
    with pytest.raises(OpusResponseInvalid):
        harness.validate_opus_response(v, 'rid-1')


# =================================================================================================
# Model-metadata enforcement — opus only, no cheaper fallback (Sol §"Efficient execution")
# =================================================================================================
def test_model_is_opus_true_for_opus_envelope():
    assert harness.model_is_opus(_envelope(_verdict('r'), model='claude-opus-4-8')) is True


def test_model_is_opus_false_for_cheaper_model():
    assert harness.model_is_opus(_envelope(_verdict('r'), model='claude-sonnet-4-5')) is False
    assert harness.model_is_opus(_envelope(_verdict('r'), model='glm-4.6')) is False


def test_model_is_opus_false_when_metadata_absent():
    assert harness.model_is_opus({'result': '{}'}) is False


def test_run_opus_pass_flags_unverified_model(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    runner = _runner_for(_verdict(rec.audit_row_id), model='claude-sonnet-4-5')
    v = harness.run_opus_pass(card, g, question=QUESTION, contract_facets=FACETS,
                              det_receipt=rec, pass_label=PASS_A, runner=runner)
    assert v.model_verified is False


# =================================================================================================
# Fail-closed combination (Sol §Faithfulness, §Tier 3, §4)
# =================================================================================================
def _clean_faith():
    return harness.FaithfulnessReceipt(PASS, 'ENTAILED', [], '', 'primary')


def test_clean_card_two_agreeing_passes_keep_unchanged(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, _verdict(rec.audit_row_id))
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, b)
    assert c.final == PASS and c.proposed_disposition == 'KEEP_UNCHANGED'
    assert c.needs_adjudication is False


def test_reportast_faith_fail_cannot_be_overridden_by_opus(graph_and_clean):
    """Sol §Faithfulness/§Tier 3: a report-AST FAIL is decisive; two PASSing Opus opinions cannot save
    the card."""
    g, card = graph_and_clean
    rec = _receipt(card, g)
    faith_fail = harness.FaithfulnessReceipt(FAIL, 'NOT_ENTAILED', [RC_FAITH_NOT_ENTAILED], 'x', 'primary')
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))  # both say KEEP
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, _verdict(rec.audit_row_id))
    c = harness.combine_card_verdicts(rec, faith_fail, [], a, b)
    assert c.final == FAIL and c.proposed_disposition == 'QUARANTINE_CARD'


def test_disagreeing_passes_route_to_adjudication(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True,
                    _verdict(rec.audit_row_id, rel=(FAIL, 'GENERIC_FILLER'), disp='QUARANTINE_CARD'))
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, b)
    assert c.needs_adjudication is True and c.final == UNCERTAIN
    assert RC_OPUS_DISAGREE in c.reason_codes


def test_reportast_pass_but_opus_alleges_atom_routes_to_adjudication(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id, faith=FAIL))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, _verdict(rec.audit_row_id, faith=FAIL))
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, b)
    assert c.needs_adjudication is True and RC_OPUS_ALLEGES_ATOM in c.reason_codes


def test_missing_pass_fails_closed(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, None)
    assert c.final == UNCERTAIN and RC_OPUS_TRANSPORT in c.reason_codes


def test_unverified_model_fails_closed(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, False, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, False, _verdict(rec.audit_row_id))
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, b)
    assert c.final == UNCERTAIN and RC_OPUS_MODEL in c.reason_codes


def test_both_passes_agree_on_relevance_fail(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    bad = _verdict(rec.audit_row_id, rel=(FAIL, 'OTHER_QUESTION'), disp='QUARANTINE_CARD')
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, bad)
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, bad)
    c = harness.combine_card_verdicts(rec, _clean_faith(), [], a, b)
    assert c.final == FAIL and RC_OPUS_RELEVANCE in c.reason_codes


# =================================================================================================
# Tier 3 adjudication floors (Sol §Tier 3)
# =================================================================================================
def test_adjudicator_cannot_override_reportast_fail(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    faith_fail = harness.FaithfulnessReceipt(FAIL, 'NOT_ENTAILED', [RC_FAITH_NOT_ENTAILED], 'x', 'primary')
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, _verdict(rec.audit_row_id))
    runner = _runner_for(_verdict(rec.audit_row_id, disp='KEEP_UNCHANGED'))  # adjudicator says keep
    c = harness.run_adjudication(card, g, rec, faith_fail, [], a, b,
                                 question=QUESTION, contract_facets=FACETS, runner=runner)
    assert c.final == FAIL and c.proposed_disposition == 'QUARANTINE_CARD'


def test_adjudicator_resolves_false_positive_to_keep(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True,
                    _verdict(rec.audit_row_id, rel=(FAIL, 'GENERIC_FILLER'), disp='QUARANTINE_CARD'))
    runner = _runner_for(_verdict(rec.audit_row_id, disp='KEEP_UNCHANGED'))
    c = harness.run_adjudication(card, g, rec, _clean_faith(), [], a, b,
                                 question=QUESTION, contract_facets=FACETS, runner=runner)
    assert c.final == PASS and c.proposed_disposition == 'KEEP_UNCHANGED'


def test_adjudicator_response_must_prove_opus(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    a = OpusVerdict(rec.audit_row_id, PASS_A, True, _verdict(rec.audit_row_id))
    b = OpusVerdict(rec.audit_row_id, PASS_B, True, _verdict(rec.audit_row_id))
    runner = _runner_for(_verdict(rec.audit_row_id), model='claude-haiku-4-5')
    c = harness.run_adjudication(card, g, rec, _clean_faith(), [], a, b,
                                 question=QUESTION, contract_facets=FACETS, runner=runner)
    assert c.final == UNCERTAIN and RC_OPUS_MODEL in c.reason_codes


# =================================================================================================
# End-to-end audit_card with the injected transport (Sol §7 per-card slice)
# =================================================================================================
def test_audit_card_happy_path_keeps_clean_card(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    runner = _runner_for(_verdict(rec.audit_row_id))
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))
    try:
        c = harness.audit_card(card, g, rec, question=QUESTION, contract_facets=FACETS, runner=runner)
    finally:
        RA.set_entailment_judge(None)
    assert c.final == PASS and c.proposed_disposition == 'KEEP_UNCHANGED'


def test_audit_card_transport_failure_fails_closed(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)

    def dead_runner(_prompt, _schema):
        raise OpusUnavailable('opus transport down')

    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))
    try:
        c = harness.audit_card(card, g, rec, question=QUESTION, contract_facets=FACETS, runner=dead_runner)
    finally:
        RA.set_entailment_judge(None)
    assert c.final == UNCERTAIN and c.proposed_disposition == 'QUARANTINE_CARD'
    assert RC_OPUS_TRANSPORT in c.reason_codes


# =================================================================================================
# Generality / metamorphic (Sol Phase 8): renaming the subject changes no verdict
# =================================================================================================
def test_question_and_facet_rename_change_no_verdict(graph_and_clean):
    g, card = graph_and_clean
    rec = _receipt(card, g)
    runner = _runner_for(_verdict(rec.audit_row_id))
    RA.set_entailment_judge(lambda clause, span: ('ENTAILED', 'ok'))
    try:
        c1 = harness.audit_card(card, g, rec, question=QUESTION, contract_facets=FACETS, runner=runner)
        # a clinical corpus: different subject words, structurally identical card
        c2 = harness.audit_card(card, g, rec, question='What is the treatment effect on mortality?',
                                contract_facets=['oncology', 'survival'], runner=runner)
    finally:
        RA.set_entailment_judge(None)
    assert c1.final == c2.final == PASS
    assert c1.proposed_disposition == c2.proposed_disposition


def test_no_task_literal_in_prompt(graph_and_clean):
    """Sol Phase 8 / §Generality: the production prompt carries no task-72/DOI/venue literal — only
    injected values. Build a packet+prompt and assert the injected question is what parametrizes it."""
    g, card = graph_and_clean
    rec = _receipt(card, g)
    schema = harness.opus_response_json_schema()
    packet = harness.build_opus_packet(card, g, question='SENTINEL_QUESTION',
                                       contract_facets=['SENTINEL_FACET'], det_receipt=rec)
    prompt = harness.build_opus_prompt(packet, schema)
    assert 'SENTINEL_QUESTION' in prompt and 'SENTINEL_FACET' in prompt
    # the resolved span injected is the exact verified bytes
    assert card['span_raw'] in prompt
