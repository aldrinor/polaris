"""P1 — foundation acceptance battery for the binding gate.

Every vector runs through the REAL chain: migrate() / ingest_bytes -> the ONE identity reducer
(event_ledger.derive_binding_core) -> Graph.resolve_attribution(binding|mid, policy), and where the
disk is the attack surface, through Graph.to_json / Graph.from_json. No Attribution is mocked and no
successful verdict is hand-assigned; the tests only ever READ the structured identity layer
(identity_verdict / disposition / reason_code) the resolver stamps.

Generality (Sol global rule 1 & 6): no rule under test may key on a DOI, title, author, venue, or
subject literal. The metamorphic tests replace every identifier and subject term while holding the
STRUCTURE constant, and assert the structural verdict is unchanged.
"""
import copy

import pytest

import provenance as P
from provenance import (DISPOSITION_ADMIT, DISPOSITION_LEAD_ONLY, DISPOSITION_QUARANTINE,
                        RC_ADMITTED, RC_SPAN_BINDING_INVALID, RC_IDENTITY_DIFFERENT_WORK,
                        RC_IDENTITY_UNRESOLVED, RC_IDENTITY_UNKNOWN_VERDICT, RC_INCOMPLETE_BYTES,
                        RC_VERSION_NOT_PERMITTED)

FILLER = ('This paper studies the question at length across many pages of careful analysis, '
          'reporting the design, the data and the estimates in full. ') * 110


def _row(requested_doi, body_doi, *, title='A Rigorous Study of the Widget Mechanism',
         authors=('Adams', 'Brown'), byline='By Alice Adams and Bob Brown', venue='Journal of Widgets',
         results='We find the effect is 0.2 units (standard error 0.05) across 722 sites.', **extra):
    """A single corpus row whose FULLTEXT carries `body_doi` in its own front matter. The row asks for
    `requested_doi`. When the two agree the bytes are SAME_WORK; when they differ the front matter is a
    foreign DOI and the bytes are a stranger's paper (DIFFERENT_WORK) — positive evidence, both ways."""
    src = (f'{title}\ndoi: {body_doi}\n{byline}\n'
           f'1. Introduction\n{FILLER}\n4. Results\n{results}\n')
    row = {'doi': requested_doi, 'title': title, 'authors': list(authors),
           'venue': venue, 'year': 2020, 'type': 'journal-article', 'fulltext': src, 'abstract': ''}
    row.update(extra)
    return row


def _one(rows):
    g = P.migrate(rows)
    m = next(iter(g.manifestations.values()))
    return g, m


# ── identity: the positive-proof core ───────────────────────────────────────────────────────────

def test_live_foreign_doi_derives_different_work():
    g, m = _one([_row('10.9999/zzzz', '10.2222/bbbb')])
    assert m.profile['semantic_binding'] == 'DIFFERENT_WORK'
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.identity_verdict == 'DIFFERENT_WORK'
    assert att.disposition == DISPOSITION_QUARANTINE
    assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
    assert att.admitted is False
    assert att.names_expression_id is None
    assert att.text is None
    assert att.permitted_expression_ids == ()


def test_matching_doi_is_same_work_and_admits_under_any_version():
    g, m = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    # P2 unification: a matching front-matter DOI is typeset journal furniture, so the ONE version
    # reducer derives VERSION_OF_PUBLISHED / journal_version (identity proven, journal-attributable) —
    # the pair the resolver admits, rather than the bare SAME_WORK label the pre-P2 stamp lane produced.
    assert m.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
    assert m.profile['expression_kind'] == 'journal_version'
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.admitted is True
    assert att.disposition == DISPOSITION_ADMIT
    assert att.reason_code == RC_ADMITTED
    assert att.names_expression_id is not None


def test_changing_only_requested_doi_rejects_the_same_bytes_under_both_policies():
    body = '10.2222/bbbb'
    # Same bytes, two requested identities. Only the requested DOI differs.
    _, ok = _one([_row(body, body)])
    _, foreign = _one([_row('10.9999/zzzz', body)])
    assert ok.text == foreign.text  # the bytes are byte-identical
    for policy in (P.JOURNAL_ONLY, P.ANY_VERSION):
        g_ok, m_ok = _one([_row(body, body)])
        g_f, m_f = _one([_row('10.9999/zzzz', body)])
        assert g_f.resolve_attribution(m_f.id, policy).admitted is False
        # the ONLY thing that changed was the requested DOI; the admissible one still resolves
        assert g_ok.resolve_attribution(m_ok.id, P.ANY_VERSION).admitted is True


def test_row_binding_cache_is_audit_only_and_cannot_grant_permission():
    # The row LIES: it caches SAME_WORK, but the bytes self-identify as a different work.
    g, m = _one([_row('10.9999/zzzz', '10.2222/bbbb', semantic_binding='SAME_WORK')])
    cache = m.profile.get('row_binding_cache')
    assert cache == {'stored': 'SAME_WORK', 'live': 'DIFFERENT_WORK', 'agrees': False}
    # Live resolution ignores the cache entirely and still quarantines.
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
    assert att.admitted is False


def test_row_cache_lying_different_work_does_not_suppress_a_true_same_work():
    g, m = _one([_row('10.2222/bbbb', '10.2222/bbbb', semantic_binding='DIFFERENT_WORK')])
    assert m.profile['row_binding_cache']['stored'] == 'DIFFERENT_WORK'
    # The live reducer ignores the lying cache and proves identity from the bytes: a matching
    # front-matter DOI is journal furniture -> VERSION_OF_PUBLISHED (identity proven), which admits.
    assert m.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
    assert g.resolve_attribution(m.id, P.ANY_VERSION).admitted is True


# ── fail-closed on missing / unknown verdicts ───────────────────────────────────────────────────

def test_missing_verdict_fails_closed():
    g, m = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    m.profile['semantic_binding'] = None
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.disposition == DISPOSITION_QUARANTINE
    assert att.reason_code == RC_IDENTITY_UNKNOWN_VERDICT
    assert att.admitted is False
    assert att.permitted_expression_ids == ()


def test_unknown_verdict_fails_closed():
    g, m = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    m.profile['semantic_binding'] = 'SAMEISH_WORK'
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.disposition == DISPOSITION_QUARANTINE
    assert att.reason_code == RC_IDENTITY_UNKNOWN_VERDICT
    assert att.admitted is False
    assert att.permitted_expression_ids == ()


def test_unresolved_binding_is_lead_only_not_quarantine():
    # A readable header, a generic 2-word title, no requested author present, no DOI tie: UNRESOLVED.
    row = _row('', '', title='Widget Study', authors=(), byline='An untitled report',
               venue='Journal of Widgets')
    g, m = _one([row])
    assert m.profile['semantic_binding'] == 'UNRESOLVED_BINDING'
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.disposition == DISPOSITION_LEAD_ONLY
    assert att.reason_code == RC_IDENTITY_UNRESOLVED
    assert att.admitted is False


# ── structural stamping of an invalid binding ───────────────────────────────────────────────────

def test_invalid_binding_is_structurally_stamped():
    g, m = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    binding = g.bind_span(m.id, 5, 60)
    tampered = dict(binding)
    tampered['content_hash'] = 'deadbeef' * 8          # no longer the manifestation's hash
    att = g.resolve_attribution(tampered, P.ANY_VERSION)
    assert att.disposition == DISPOSITION_QUARANTINE
    assert att.reason_code == RC_SPAN_BINDING_INVALID
    assert att.admitted is False
    assert att.names_expression_id is None
    assert att.text is None
    assert att.permitted_expression_ids == ()


def test_incomplete_bytes_are_stamped_and_name_nothing():
    # A stub: readable, identity-proven by its own DOI, but far too short to carry a finding.
    src = 'A Rigorous Study of the Widget Mechanism\ndoi: 10.2222/bbbb\nBy Alice Adams and Bob Brown\n'
    row = {'doi': '10.2222/bbbb', 'title': 'A Rigorous Study of the Widget Mechanism',
           'authors': ['Adams', 'Brown'], 'venue': 'Journal of Widgets', 'year': 2020,
           'type': 'journal-article', 'fulltext': src, 'abstract': ''}
    g, m = _one([row])
    if m.profile['complete']:
        pytest.skip('fixture is unexpectedly complete')
    att = g.resolve_attribution(m.id, P.JOURNAL_ONLY)
    assert att.disposition == DISPOSITION_QUARANTINE
    assert att.reason_code == RC_INCOMPLETE_BYTES
    assert att.admitted is False
    assert att.permitted_expression_ids == ()


# ── JSON tampering is refused, never repaired ───────────────────────────────────────────────────

def test_clean_graph_round_trips():
    g, _ = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    reloaded = P.Graph.from_json(g.to_json())
    assert len(reloaded.manifestations) == len(g.manifestations)


def test_json_verdict_tampering_is_refused():
    g, _ = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    d = g.to_json()
    for mm in d['manifestations']:
        mm['profile']['semantic_binding'] = 'DIFFERENT_WORK'   # bytes re-derive SAME_WORK
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(d)


def test_json_missing_verdict_is_an_integrity_error():
    g, _ = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    d = g.to_json()
    for mm in d['manifestations']:
        mm['profile'].pop('semantic_binding', None)
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(d)


def test_json_unknown_verdict_is_an_integrity_error():
    g, _ = _one([_row('10.2222/bbbb', '10.2222/bbbb')])
    d = g.to_json()
    for mm in d['manifestations']:
        mm['profile']['semantic_binding'] = 'WAT'
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(d)


# ── the corrected gate_card() passes its BINDING, not a bare id ──────────────────────────────────

def test_gate_card_passes_the_binding_not_the_bare_manifestation_id(monkeypatch):
    import evidence_miner as EM
    src = ('A Rigorous Study of the Widget Mechanism\ndoi: 10.2222/bbbb\n'
           'By Alice Adams and Bob Brown\n1. Introduction\n' + FILLER +
           '\n4. Results\nWe find that the widget mechanism reduces the failure rate by 0.2 '
           'percentage points (standard error 0.05) across 722 independent sites.\n')
    row = {'doi': '10.2222/bbbb', 'title': 'A Rigorous Study of the Widget Mechanism',
           'authors': ['Adams', 'Brown'], 'venue': 'Journal of Widgets', 'year': 2020,
           'type': 'journal-article', 'fulltext': src, 'abstract': ''}
    g = P.migrate([row])
    mid = next(iter(g.manifestations))
    view, chunks = EM.chunk_document('d', g.manifestations[mid].text)
    chunk = next(c for c in chunks if 'failure rate' in c.text)
    paper = {'doi': '10.2222/bbbb', 'authors': ['Adams', 'Brown'], 'year': 2020,
             'venue': 'Journal of Widgets', 'title': 'A Rigorous Study of the Widget Mechanism',
             'abstract': '', 'manifestation_id': mid, '_source_version': 'x', '_text_field': 'fulltext'}
    pw = EM.paper_window(view, chunks, paper)
    raw = {'span': 'We find that the widget mechanism reduces the failure rate by 0.2 percentage '
                   'points (standard error 0.05) across 722 independent sites.',
           'effect': '0.2', 'unit': 'percentage points', 'comparator': '', 'outcome': 'failure rate',
           'population': 'sites', 'geography': '', 'period': '', 'technology': 'widget', 'industry': '',
           'unit_of_analysis': 'region', 'design': 'observational', 'uncertainty': 'standard error 0.05',
           'horizon': 'long-run', 'mechanisms': []}

    seen = {}
    real = g.resolve_attribution

    def spy(ref, policy=P.JOURNAL_ONLY):
        seen['ref'] = ref
        return real(ref, policy)

    monkeypatch.setattr(g, 'resolve_attribution', spy)
    rejects = {k: 0 for k in ('span_not_in_source', 'span_too_short', 'offset_roundtrip_failed',
                              'span_binding_failed', 'span_binding_mismatch',
                              'source_policy_inadmissible')}
    from collections import defaultdict
    rejects = defaultdict(int)
    EM.gate_card(raw, view, chunk, paper, pw, EM.MiningContract(), rejects,
                 graph=g, source_policy=P.ANY_VERSION)
    # The gate reached resolve_attribution with a BINDING dict — carrying span offsets — never a str.
    assert 'ref' in seen, f'gate_card refused before resolving: {dict(rejects)}'
    assert isinstance(seen['ref'], dict)
    assert 'span_start' in seen['ref'] and 'span_end' in seen['ref']
    assert seen['ref']['manifestation_id'] == mid


# ── metamorphic generality: identifiers & subject swapped, structure held ────────────────────────

@pytest.mark.parametrize('subj', [
    dict(title='A Randomized Trial of the Antihypertensive Compound', authors=('Ng', 'Okafor'),
         byline='By Wei Ng and Chidi Okafor', venue='New England Journal of Medicine',
         requested='10.1056/clin-A', foreign='10.1056/clin-B'),
    dict(title='On the Interpretation of the Contract Formation Doctrine', authors=('Reyes', 'Silva'),
         byline='By Ana Reyes and Ivo Silva', venue='Harvard Law Review',
         requested='10.2307/legal-A', foreign='10.2307/legal-B'),
    dict(title='A Transformer Architecture for Program Synthesis Tasks', authors=('Park', 'Vasquez'),
         byline='By Jin Park and Luis Vasquez', venue='NeurIPS Proceedings',
         requested='10.5555/cs-A', foreign='10.5555/cs-B'),
])
def test_different_work_is_structural_across_unrelated_subjects(subj):
    # SAME structure (a foreign front-matter DOI), completely different subject/identifiers each time.
    g, m = _one([_row(subj['requested'], subj['foreign'], title=subj['title'],
                      authors=subj['authors'], byline=subj['byline'], venue=subj['venue'])])
    assert m.profile['semantic_binding'] == 'DIFFERENT_WORK'
    att = g.resolve_attribution(m.id, P.ANY_VERSION)
    assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
    assert att.admitted is False


@pytest.mark.parametrize('subj', [
    dict(title='A Randomized Trial of the Antihypertensive Compound', authors=('Ng', 'Okafor'),
         byline='By Wei Ng and Chidi Okafor', venue='New England Journal of Medicine', doi='10.1056/clin-A'),
    dict(title='On the Interpretation of the Contract Formation Doctrine', authors=('Reyes', 'Silva'),
         byline='By Ana Reyes and Ivo Silva', venue='Harvard Law Review', doi='10.2307/legal-A'),
    dict(title='A Transformer Architecture for Program Synthesis Tasks', authors=('Park', 'Vasquez'),
         byline='By Jin Park and Luis Vasquez', venue='NeurIPS Proceedings', doi='10.5555/cs-A'),
])
def test_same_work_admits_structurally_across_unrelated_subjects(subj):
    g, m = _one([_row(subj['doi'], subj['doi'], title=subj['title'], authors=subj['authors'],
                      byline=subj['byline'], venue=subj['venue'])])
    # Structural, not subject-keyed: a matching front-matter DOI is journal furniture for every one of
    # these unrelated subjects, so the ONE reducer derives the SAME proven pair each time.
    assert m.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
    assert m.profile['expression_kind'] == 'journal_version'
    assert g.resolve_attribution(m.id, P.ANY_VERSION).admitted is True
