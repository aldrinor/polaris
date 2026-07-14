"""P1S — the adjustable source policy is INFERRED FROM THE ORIGINAL PROMPT.

The same valid, complete, identity-proven PREPRINT fixture runs through the REAL chain
(migrate/ingest -> the one identity reducer -> Graph.resolve_attribution(binding, policy)). What
changes across cases is ONLY the prompt, and therefore only the policy `research_contract.
derive_version_scope` infers from it. Nothing is mocked and no verdict is hand-assigned.

Generality (Sol global rules 1 & 6): `derive_version_scope` keys on source-class + directive
structure ONLY — never on a DOI, title, author, venue, or subject literal. The metamorphic test
replaces the subject with unrelated clinical, legal, economics, and CS vocabulary and asserts the
inferred policy is unchanged.
"""
import pytest

import provenance as P
import research_contract as rc
from provenance import DISPOSITION_ADMIT, DISPOSITION_LEAD_ONLY, RC_ADMITTED, RC_VERSION_NOT_PERMITTED

FILLER = ('This paper studies the question at length across many pages of careful analysis, '
          'reporting the design, the data and the estimates in full. ') * 110


def _preprint_row(requested_doi='10.2222/bbbb',
                  title='A Rigorous Study of the Widget Mechanism',
                  byline='By Alice Adams and Bob Brown', authors=('Adams', 'Brown')):
    """A COMPLETE, IDENTITY-PROVEN WORKING PAPER: the article's own front matter carries the requested
    DOI (so the bytes are the requested work) AND a working-paper stamp (so the version is a preprint,
    never a journal article). One fixture; the policy is the only thing that moves."""
    src = (f'{title}\nNBER Working Paper No. 26123\ndoi: {requested_doi}\n{byline}\n'
           f'1. Introduction\n{FILLER}\n4. Results\n'
           f'We find the effect is 0.2 units (standard error 0.05) across 722 sites.\n')
    return {'doi': requested_doi, 'title': title, 'authors': list(authors),
            'venue': 'Journal of Widgets', 'year': 2020, 'type': 'journal-article',
            'fulltext': src, 'abstract': ''}


def _resolve_under(prompt, row=None):
    """Infer the policy FROM THE PROMPT, then resolve the fixture under it. Returns (policy, att)."""
    scope, _ev = rc.derive_version_scope(prompt)
    policy = P.JOURNAL_ONLY if scope == 'JOURNAL_ONLY' else P.ANY_VERSION
    g = P.migrate([row or _preprint_row()])
    m = next(iter(g.manifestations.values()))
    assert m.profile['semantic_binding'] == 'VERSION_OF_PREPRINT'  # the fixture really is a preprint
    return policy, g.resolve_attribution(m.id, policy)


# ── the fixture is genuinely a valid, complete preprint ──────────────────────────────────────────

def test_fixture_is_a_complete_identity_proven_preprint():
    g = P.migrate([_preprint_row()])
    m = next(iter(g.manifestations.values()))
    assert m.profile['semantic_binding'] == 'VERSION_OF_PREPRINT'
    assert g.expressions[m.expression_id].kind == 'working_paper'


# ── THE ACCEPTANCE TABLE: same bytes, prompt decides the policy ──────────────────────────────────

ANY_VERSION_PROMPTS = [
    'Summarize the evidence about X.',
    'Use journal articles and preprints about X.',
    'Explain differences between journals and preprint servers.',
    'Do not limit this to journal articles; include working papers.',
]

JOURNAL_ONLY_PROMPTS = [
    'Use only peer-reviewed sources about X.',
    'Cite published journal articles about X.',
]


@pytest.mark.parametrize('prompt', ANY_VERSION_PROMPTS)
def test_any_version_prompts_admit_the_preprint(prompt):
    policy, att = _resolve_under(prompt)
    assert policy is P.ANY_VERSION, f'{prompt!r} should infer ANY_VERSION'
    assert att.admitted is True
    assert att.disposition == DISPOSITION_ADMIT
    assert att.reason_code == RC_ADMITTED
    assert att.names_expression_id is not None
    assert att.names_expression_id.endswith('working_paper')  # names the PREPRINT, never a journal


@pytest.mark.parametrize('prompt', JOURNAL_ONLY_PROMPTS)
def test_journal_only_prompts_reduce_the_preprint_to_a_lead(prompt):
    policy, att = _resolve_under(prompt)
    assert policy is P.JOURNAL_ONLY, f'{prompt!r} should infer JOURNAL_ONLY'
    # THE EXACT REFUSAL CONTRACT the plan requires.
    assert att.admitted is False
    assert att.disposition == 'LEAD_ONLY'
    assert att.reason_code == 'VERSION_NOT_PERMITTED'
    assert att.names_expression_id is None
    assert att.disposition == DISPOSITION_LEAD_ONLY
    assert att.reason_code == RC_VERSION_NOT_PERMITTED


# ── POSITIVE PROOF ONLY: discussion / negation / widening never set the gate ─────────────────────

def test_widening_clause_defeats_the_journal_class_demand():
    # A source-class phrase AND a directive, but widened in the SAME clause -> ANY_VERSION.
    scope, ev = rc.derive_version_scope('Use journal articles and preprints about labour markets.')
    assert scope == 'ANY_VERSION' and ev == []


def test_negation_clause_defeats_the_journal_class_demand():
    scope, ev = rc.derive_version_scope('Do not restrict to journal articles about the topic.')
    assert scope == 'ANY_VERSION' and ev == []


def test_mere_comparison_of_source_types_does_not_set_the_gate():
    scope, ev = rc.derive_version_scope('Contrast journals and preprint servers as venues.')
    assert scope == 'ANY_VERSION' and ev == []


def test_positive_directive_returns_the_verbatim_clause():
    q = 'First, gather the data. Then use only peer-reviewed sources about wage inequality.'
    scope, ev = rc.derive_version_scope(q)
    assert scope == 'JOURNAL_ONLY'
    assert ev == ['Then use only peer-reviewed sources about wage inequality']
    for clause in ev:                       # every returned clause is a VERBATIM span of the prompt
        assert clause in q


# ── the two SourcePolicy fields are wired and non-negotiable through the compiler ────────────────

def test_floor_source_policy_sets_the_version_scope_fields():
    q = 'Use only peer-reviewed sources about diabetes.'
    sp = rc._floor_source_policy(q)
    assert sp.version_scope == 'JOURNAL_ONLY'
    assert sp.version_scope_evidence
    assert all(clause in q for clause in sp.version_scope_evidence)   # verbatim spans of the prompt
    sp2 = rc._floor_source_policy('Summarize what is known about diabetes.')
    assert sp2.version_scope == 'ANY_VERSION'
    assert sp2.version_scope_evidence == []


def test_offline_contract_carries_the_prompt_derived_version_scope():
    c = rc.compile_contract('Cite published journal articles about hypertension.',
                            use_llm=False, verbose=False, force=True)
    assert c.source_policy.version_scope == 'JOURNAL_ONLY'
    c2 = rc.compile_contract('Review what is known about hypertension.',
                             use_llm=False, verbose=False, force=True)
    assert c2.source_policy.version_scope == 'ANY_VERSION'


# ── the event-ledger eligibility lane consumes the SAME policy ───────────────────────────────────

def test_event_ledger_eligibility_consults_the_policy():
    import event_ledger as EL
    L = EL.Ledger()
    src = _preprint_row()['fulltext']
    L.emit('u', EL.EventKind.MANIFESTATION_FETCHED, 'test', adapter='x', locator='u',
           blob_id='sha256:b', byte_sha256='b', text_blob_id='sha256:t', text_sha256='t',
           requested_title='A Rigorous Study of the Widget Mechanism',
           requested_authors=['Adams', 'Brown'], requested_doi='10.2222/bbbb',
           source_type='journal-article')
    L.emit('u', EL.EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **EL.observe_text(src))
    # Default ANY_VERSION: a proven preprint is ADMISSIBLE as its own expression, NOT a lead.
    elig_any, _ = EL.derive_eligibility(L.events('u'))
    assert elig_any == EL.ADMISSIBLE
    # JOURNAL_ONLY: the same binding is a discovery lead — the policy does not permit its kind.
    elig_jo, _ = EL.derive_eligibility(L.events('u'), policy=P.JOURNAL_ONLY)
    assert elig_jo == EL.DISCOVERY_LEAD


# ── METAMORPHIC: replace the subject; the inferred policy must not move ───────────────────────────

_SUBJECTS = ['type 2 diabetes remission', 'qualified immunity doctrine',
             'minimum wage employment effects', 'transformer inference latency']


@pytest.mark.parametrize('subject', _SUBJECTS)
def test_journal_only_is_subject_invariant(subject):
    scope, _ev = rc.derive_version_scope(f'Use only peer-reviewed sources about {subject}.')
    assert scope == 'JOURNAL_ONLY'


@pytest.mark.parametrize('subject', _SUBJECTS)
def test_any_version_is_subject_invariant(subject):
    scope, _ev = rc.derive_version_scope(f'Summarize the current evidence about {subject}.')
    assert scope == 'ANY_VERSION'


@pytest.mark.parametrize('subject', _SUBJECTS)
def test_full_chain_admission_is_subject_invariant(subject):
    # Change the fixture's subject/identifiers AND the prompt subject together; structure is held.
    doi = '10.5555/' + str(abs(hash(subject)) % 100000)
    row = _preprint_row(requested_doi=doi, title=f'A Structured Study of {subject}',
                        byline='By Casey Doe and Dana Roe', authors=('Doe', 'Roe'))
    _, att_any = _resolve_under(f'Summarize the evidence about {subject}.', row=row)
    assert att_any.admitted is True and att_any.names_expression_id.endswith('working_paper')
    _, att_jo = _resolve_under(f'Use only peer-reviewed sources about {subject}.', row=row)
    assert att_jo.admitted is False and att_jo.reason_code == 'VERSION_NOT_PERMITTED'


# ── policy laundering is refused: an explicit override that disagrees with the prompt raises ──────

def test_mine_refuses_an_explicit_policy_that_disagrees_with_the_prompt(tmp_path):
    import json
    import evidence_miner as EM
    corpus = tmp_path / 'corpus.json'
    corpus.write_text(json.dumps([_preprint_row()]))
    # The prompt demands journal-only; passing ANY_VERSION is a laundering attempt and must raise.
    with pytest.raises(ValueError):
        EM.mine(corpus, question='Use only peer-reviewed sources about the widget mechanism.',
                use_llm=False, source_policy=P.ANY_VERSION)
