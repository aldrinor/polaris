"""P2 — unify version derivation and quarantine impossible pairs.

ONE reducer (`event_ledger.version_evidence` -> `VersionDecision`) now returns BOTH the semantic
binding and the own-expression kind from a single pass over one set of observations, so the
semantic-binding lane (`derive_binding_core`) and the expression-kind lane
(`provenance.derive_expression_kind` / `profile`) can no longer disagree. The resolver validates the
resulting (binding, expression kind) pair against ONE declarative compatibility table
(`COMPATIBLE_VERSION_PAIRS`) and QUARANTINES any impossible pair as `DERIVATION_CONFLICT`.

Every vector runs through the REAL chain — migrate()/ingest_bytes -> the ONE reducer ->
resolve_attribution -> (for the tampering vector) Graph.to_json/from_json. No Attribution is mocked
and no verdict is hand-assigned.

Generality (Sol global rules 1 & 6): no rule under test keys on a DOI, title, author, venue, or
subject literal. The metamorphic parameters replace every identifier and subject term while holding
the STRUCTURE constant; the derived pair must be identical across all of them.
"""
import copy

import pytest

import provenance as P
from provenance import (DISPOSITION_ADMIT, DISPOSITION_LEAD_ONLY, DISPOSITION_QUARANTINE,
                        RC_ADMITTED, RC_VERSION_NOT_PERMITTED, RC_DERIVATION_CONFLICT,
                        GraphIntegrityError)
from event_ledger import (VersionDecision, version_evidence, version_furniture,
                          COMPATIBLE_VERSION_PAIRS, SAME_WORK, VERSION_PUBLISHED, VERSION_ACCEPTED,
                          VERSION_PREPRINT)

FILLER = ('This paper studies the question at length across many pages of careful analysis, '
          'reporting the design, the data and the estimates in full. ') * 120

# ── structural version furniture, in the vocabulary of the world — NOT a subject or an identifier ──
JOURNAL_MASTHEAD = 'Some Learned Review, Volume 12, Number 3, 2020, Pages 45-67.'
ACCEPTED_STAMP   = 'Accepted manuscript.'
WORKING_STAMP    = 'NBER Working Paper No. 25682'
PREPRINT_STAMP   = 'arXiv:2401.01234'

# Four unrelated Work identities. The rules may NOT branch on any of these strings.
DOMAINS = [
    dict(id='clinical', title='A Randomised Trial of the Widget Regimen in Adults',
         authors=('Adams', 'Brown'), byline='By Alice Adams and Bob Brown',
         venue='New England Journal of Medicine', doi='10.1056/clin-A'),
    dict(id='legal', title='On the Interpretation of the Contract Formation Doctrine',
         authors=('Reyes', 'Silva'), byline='By Ana Reyes and Ivo Silva',
         venue='Harvard Law Review', doi='10.2307/legal-A'),
    dict(id='economics', title='Automation and the Structure of New Labour Tasks',
         authors=('Okoro', 'Tan'), byline='By Ngozi Okoro and Wei Tan',
         venue='Journal of Political Economy', doi='10.1086/econ-A'),
    dict(id='cs', title='A Transformer Architecture for Program Synthesis Tasks',
         authors=('Park', 'Vasquez'), byline='By Jin Park and Luis Vasquez',
         venue='NeurIPS Proceedings', doi='10.5555/cs-A'),
]


def _doc(d, *, furniture=''):
    """A complete scholarly body that self-identifies (matching front-matter DOI + byline) and carries
    the given structural version `furniture`. The journal masthead + DOI are always present; a working
    paper / accepted stamp, when supplied, VETOES the published furniture — exactly the shape of a
    repository deposit that carries both."""
    return (f'{d["title"]}\n{d["byline"]}\n{furniture}\n'
            f'{JOURNAL_MASTHEAD} doi: {d["doi"]}\n'
            f'1. Introduction\n{FILLER}\n4. Results\nWe estimate the effect is 0.2 units.\n')


def _graph(d, *, furniture=''):
    row = {'doi': d['doi'], 'title': d['title'], 'authors': list(d['authors']),
           'venue': d['venue'], 'year': 2020, 'type': 'journal-article',
           'fulltext': _doc(d, furniture=furniture), 'abstract': ''}
    g = P.migrate([row])
    m = next(iter(g.manifestations.values()))
    return g, m


def _own_kind(g, m):
    return g.expressions[m.expression_id].kind


# ══ THE ONE REDUCER RETURNS BOTH FIELDS, CONSISTENTLY ═════════════════════════════════════════════

def test_version_evidence_returns_a_versiondecision_with_both_fields():
    dec = version_evidence({'version_furniture': version_furniture(_doc(DOMAINS[0]))}, 'study')
    assert isinstance(dec, VersionDecision)
    assert dec.semantic_binding == VERSION_PUBLISHED
    assert dec.expression_kind == 'journal_version'
    # the pair the reducer emits is, by construction, always in the compatibility table
    assert (dec.semantic_binding, dec.expression_kind) in COMPATIBLE_VERSION_PAIRS


def test_compatibility_table_is_the_inverse_of_the_reducer_mapping():
    # Every emittable pair is compatible; the impossible cross-pairs are not.
    assert (VERSION_PREPRINT, 'journal_version') not in COMPATIBLE_VERSION_PAIRS
    assert (VERSION_ACCEPTED, 'journal_version') not in COMPATIBLE_VERSION_PAIRS
    assert (VERSION_PUBLISHED, 'working_paper') not in COMPATIBLE_VERSION_PAIRS
    assert (VERSION_PUBLISHED, 'preprint') not in COMPATIBLE_VERSION_PAIRS
    assert (VERSION_PUBLISHED, 'accepted_manuscript') not in COMPATIBLE_VERSION_PAIRS


# ══ THE METAMORPHIC ACCEPTANCE VECTOR (Sol P2) ═══════════════════════════════════════════════════
# One accepted fixture, mutate ONLY the structural version furniture, over four unrelated subjects.

@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_step1_published_furniture(d):
    """1. Published furniture -> VERSION_OF_PUBLISHED / journal_version; both policies admit journal."""
    g, m = _graph(d)                       # masthead + DOI, no veto furniture
    assert m.profile['semantic_binding'] == VERSION_PUBLISHED
    assert m.profile['expression_kind'] == 'journal_version'
    assert _own_kind(g, m) == 'journal_version'
    for policy in (P.JOURNAL_ONLY, P.ANY_VERSION):
        att = g.resolve_attribution(m.id, policy)
        assert att.admitted is True and att.disposition == DISPOSITION_ADMIT
        assert att.reason_code == RC_ADMITTED
        assert att.names_expression_id == m.expression_id


@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_step2_add_accepted_stamp(d):
    """2. Add an accepted-manuscript stamp -> BOTH outputs change to accepted."""
    g, m = _graph(d, furniture=ACCEPTED_STAMP)
    assert m.profile['semantic_binding'] == VERSION_ACCEPTED
    assert m.profile['expression_kind'] == 'accepted_manuscript'
    assert _own_kind(g, m) == 'accepted_manuscript'
    # JOURNAL_ONLY: not the journal, lead-only (never names the journal). ANY_VERSION: admit manuscript.
    jo = g.resolve_attribution(m.id, P.JOURNAL_ONLY)
    assert jo.admitted is False and jo.disposition == DISPOSITION_LEAD_ONLY
    assert jo.reason_code == RC_VERSION_NOT_PERMITTED and jo.names_expression_id is None
    av = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert av.admitted is True and av.names_expression_id == m.expression_id


@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_step3_replace_with_working_paper_stamp(d):
    """3. Replace the accepted stamp with a working-paper stamp -> BOTH change to preprint/working."""
    g, m = _graph(d, furniture=WORKING_STAMP)
    assert m.profile['semantic_binding'] == VERSION_PREPRINT
    assert m.profile['expression_kind'] == 'working_paper'
    assert _own_kind(g, m) == 'working_paper'
    jo = g.resolve_attribution(m.id, P.JOURNAL_ONLY)
    assert jo.admitted is False and jo.disposition == DISPOSITION_LEAD_ONLY
    assert jo.names_expression_id is None
    av = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert av.admitted is True and av.names_expression_id == m.expression_id


@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_step3b_preprint_stamp(d):
    """3b. A preprint stamp is SPLIT structurally from a working paper: VERSION_OF_PREPRINT / preprint."""
    g, m = _graph(d, furniture=PREPRINT_STAMP)
    assert m.profile['semantic_binding'] == VERSION_PREPRINT
    assert m.profile['expression_kind'] == 'preprint'
    assert _own_kind(g, m) == 'preprint'
    assert g.resolve_attribution(m.id, P.JOURNAL_ONLY).disposition == DISPOSITION_LEAD_ONLY
    assert g.resolve_attribution(m.id, P.ANY_VERSION).admitted is True


@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_step4_relabel_expression_node_is_quarantined_and_refused(d):
    """4. Relabel the graph expression node to journal_version WITHOUT changing the bytes:
    the resolver returns DERIVATION_CONFLICT and the loader refuses the graph."""
    g, m = _graph(d, furniture=WORKING_STAMP)      # bytes are a working paper
    assert m.profile['semantic_binding'] == VERSION_PREPRINT

    # relabel ONLY the manifestation's own expression node kind (bytes untouched)
    g.expressions[m.expression_id].kind = 'journal_version'

    # (a) in-memory corruption -> the resolver quarantines the impossible pair, under BOTH policies
    for policy in (P.JOURNAL_ONLY, P.ANY_VERSION):
        att = g.resolve_attribution(m.id, policy)
        assert att.admitted is False
        assert att.disposition == DISPOSITION_QUARANTINE
        assert att.reason_code == RC_DERIVATION_CONFLICT
        assert att.names_expression_id is None
        assert att.text is None
        assert att.permitted_expression_ids == ()

    # (b) the SAME corruption on disk -> strict load refuses the whole graph
    with pytest.raises(GraphIntegrityError):
        P.Graph.from_json(g.to_json())


@pytest.mark.parametrize('d', DOMAINS, ids=[x['id'] for x in DOMAINS])
def test_clean_journal_round_trips(d):
    """A consistent pair survives the JSON round-trip (the loader re-runs the SAME reducer and agrees)."""
    g, m = _graph(d)
    g2 = P.Graph.from_json(g.to_json())
    m2 = g2.manifestations[m.id]
    assert m2.profile['semantic_binding'] == VERSION_PUBLISHED
    assert g2.expressions[m2.expression_id].kind == 'journal_version'
    assert g2.resolve_attribution(m2.id, P.JOURNAL_ONLY).admitted is True


# ══ THE SEVEN-KIND CONFLICT SWEEP — zero admissible conflicts, no identifiers listed ═════════════════
# Every proven-version binding paired with an incompatible own expression kind must QUARANTINE. We
# enumerate the impossible pairs STRUCTURALLY (from the tables), never by naming a real work.

_PROVEN = (SAME_WORK, VERSION_PUBLISHED, VERSION_ACCEPTED, VERSION_PREPRINT)
_REAL_KINDS = ('journal_version', 'proceedings_version', 'accepted_manuscript',
               'working_paper', 'preprint', 'official_text', 'registry_record')
_IMPOSSIBLE = [(b, k) for b in _PROVEN for k in _REAL_KINDS
               if (b, k) not in COMPATIBLE_VERSION_PAIRS]


@pytest.mark.parametrize('binding,kind', _IMPOSSIBLE)
def test_every_impossible_pair_quarantines(binding, kind):
    """Zero admissible conflicts. Build a real self-identifying manifestation, then force an impossible
    (binding, own expression kind) pair in memory; the resolver must quarantine it under both policies."""
    g, m = _graph(DOMAINS[2])
    m.profile['semantic_binding'] = binding           # a proven binding...
    g.expressions[m.expression_id].kind = kind         # ...bound to an incompatible own expression
    for policy in (P.JOURNAL_ONLY, P.ANY_VERSION):
        att = g.resolve_attribution(m.id, policy)
        assert att.admitted is False
        assert att.reason_code == RC_DERIVATION_CONFLICT
        assert att.disposition == DISPOSITION_QUARANTINE


def test_no_impossible_pair_was_accidentally_left_compatible():
    # There ARE impossible pairs to test (guards against an empty parametrization passing vacuously).
    assert len(_IMPOSSIBLE) >= 7


# ══ TYPED NON-SCHOLARLY WORKS DERIVE official_text / registry_record FROM Work.kind ═════════════════

def test_typed_case_is_official_text_same_work():
    """A judicial opinion's version taxonomy is not the scholarly one: SAME_WORK / official_text,
    derived from Work.kind, never from scholarly furniture the opinion may quote."""
    body = ('Smith versus Jones Corporation Holdings Limited\n'
            'IN THE SUPREME COURT\n' + ('The court considered the matter at length. ') * 60 +
            # a working-paper stamp QUOTED inside the opinion must NOT make it a working paper:
            'The parties cited an NBER Working Paper in argument.\n')
    row = {'doi': '', 'title': 'Smith versus Jones Corporation Holdings Limited', 'authors': [],
           'venue': 'Supreme Court', 'year': 2019, 'type': 'judicial-opinion',
           'fulltext': body, 'abstract': ''}
    g = P.migrate([row])
    m = next(iter(g.manifestations.values()))
    assert m.profile['semantic_binding'] == SAME_WORK
    assert m.profile['expression_kind'] == 'official_text'
    assert _own_kind(g, m) == 'official_text'
    # official_text is not a journal -> JOURNAL_ONLY lead-only; the official-text policy admits it.
    assert g.resolve_attribution(m.id, P.JOURNAL_ONLY).disposition == DISPOSITION_LEAD_ONLY
    assert g.resolve_attribution(m.id, P.OFFICIAL_TEXT).admitted is True


def test_typed_trial_is_registry_record_same_work():
    body = ('A Randomised Trial of the Widget Regimen in Adults\n'
            'ClinicalTrials registry record.\n' + ('Primary outcome measured at twelve weeks. ') * 40)
    row = {'doi': '', 'title': 'A Randomised Trial of the Widget Regimen in Adults', 'authors': [],
           'venue': 'ClinicalTrials.gov', 'year': 2021, 'type': 'clinical-trial',
           'fulltext': body, 'abstract': '', 'nct_id': 'NCT01234567'}
    g = P.migrate([row])
    m = next(iter(g.manifestations.values()))
    assert m.profile['semantic_binding'] == SAME_WORK
    assert m.profile['expression_kind'] == 'registry_record'
    assert (SAME_WORK, 'registry_record') in COMPATIBLE_VERSION_PAIRS


# ══ CROSS-SUBJECT GENERALITY — the pair is determined by structure, not by domain ══════════════════

def test_pair_is_identical_across_unrelated_subjects_for_each_furniture():
    """Changing ONLY the subject/identifiers never changes the derived pair; changing the STRUCTURAL
    furniture always does. No rule keys on a subject."""
    for furniture, expect in ((JOURNAL_MASTHEAD, (VERSION_PUBLISHED, 'journal_version')),
                              (ACCEPTED_STAMP, (VERSION_ACCEPTED, 'accepted_manuscript')),
                              (WORKING_STAMP, (VERSION_PREPRINT, 'working_paper')),
                              (PREPRINT_STAMP, (VERSION_PREPRINT, 'preprint'))):
        pairs = set()
        for d in DOMAINS:
            _g, m = _graph(d, furniture=furniture)
            pairs.add((m.profile['semantic_binding'], m.profile['expression_kind']))
        assert pairs == {expect}, f'furniture {furniture!r} was not subject-invariant: {pairs}'
