"""P4 — pre-skip identity failures before LLM mining.

`evidence_miner._mining_units()` now asks the ONE universal resolver
(`Graph.resolve_attribution(mid, policy)`) at the top of every manifestation iteration and, switching
ONLY on the structured `reason_code`, drops the manifestations whose identity can never be attributed
into four separately-counted buckets BEFORE any LLM is paid to mine them:

    IDENTITY_UNRESOLVED       -> identity_unresolved_lead
    IDENTITY_DIFFERENT_WORK   -> different_work_quarantine
    IDENTITY_UNKNOWN_VERDICT  -> identity_integrity_quarantine
    DERIVATION_CONFLICT       -> derivation_conflict_quarantine

This is ONLY a spend optimization — card construction still calls the same resolver, so nothing that
this selector lets through can be attributed without passing the identical gate. In particular a
`VERSION_NOT_PERMITTED` preprint is NOT pre-skipped: a verified exact-span correspondence may still
name a permitted expression for one span even when the whole manifestation cannot.

Every fixture runs through the REAL chain — `migrate()`/`ingest_bytes` -> `derive_binding_core` ->
`resolve_attribution`. No Attribution is mocked and no verdict is hand-assigned.

Generality (Sol global rules 1 & 6): the selector keys on the machine `reason_code` alone, never on a
DOI, title, author, venue, or subject literal. The metamorphic parameters replace every identifier and
subject term while holding the STRUCTURE constant; unit selection and the four counters are identical
across all of them.
"""
import json

import pytest

import provenance as P
import evidence_miner as EM
from provenance import (RC_IDENTITY_UNRESOLVED, RC_IDENTITY_DIFFERENT_WORK,
                        RC_IDENTITY_UNKNOWN_VERDICT, RC_DERIVATION_CONFLICT, RC_VERSION_NOT_PERMITTED,
                        RC_ADMITTED, JOURNAL_ONLY, ANY_VERSION)


FILLER = ('This paper studies the question at length across many pages of careful analysis, '
          'reporting the design, the data and the estimates in full. ') * 120
# A long, self-contained body that self-identifies NOWHERE — no DOI, no title echo, no byline cue. It
# is long enough to be a complete document, so its ONLY reason to be skipped is unproven identity.
NEUTRAL = ('The section opens with the general setting and the notation used throughout, describing '
           'the framework in broad terms before any numeric quantity is reported below. ') * 130

JOURNAL_MASTHEAD = 'Some Learned Review, Volume 12, Number 3, 2020, Pages 45-67.'
PREPRINT_STAMP   = 'arXiv:2401.01234'

# Four unrelated Work identities. NO rule under test may branch on any of these strings.
DOMAINS = [
    dict(id='clinical', title='A Randomised Trial of the Widget Regimen in Adults',
         authors=('Adams', 'Brown'), byline='By Alice Adams and Bob Brown', doi='10.1056/clin-A',
         venue='New England Journal of Medicine', foreign_doi='10.9999/clin-STRANGER'),
    dict(id='legal', title='On the Interpretation of the Contract Formation Doctrine',
         authors=('Reyes', 'Silva'), byline='By Ana Reyes and Ivo Silva', doi='10.2307/legal-A',
         venue='Harvard Law Review', foreign_doi='10.9999/legal-STRANGER'),
    dict(id='economics', title='Automation and the Structure of New Labour Tasks',
         authors=('Okoro', 'Tan'), byline='By Ngozi Okoro and Wei Tan', doi='10.1086/econ-A',
         venue='Journal of Political Economy', foreign_doi='10.9999/econ-STRANGER'),
    dict(id='cs', title='A Transformer Architecture for Program Synthesis Tasks',
         authors=('Park', 'Vasquez'), byline='By Jin Park and Luis Vasquez', doi='10.5555/cs-A',
         venue='NeurIPS Proceedings', foreign_doi='10.9999/cs-STRANGER'),
]


def _scholarly_body(d, *, furniture=''):
    """A complete scholarly body that self-identifies (matching front-matter DOI + byline) and carries
    the given structural version `furniture`."""
    return (f'{d["title"]}\n{d["byline"]}\n{furniture}\n'
            f'{JOURNAL_MASTHEAD} doi: {d["doi"]}\n'
            f'1. Introduction\n{FILLER}\n4. Results\nWe estimate the effect is 0.2 units.\n')


def _row(d, *, fulltext):
    return {'doi': d['doi'], 'title': d['title'], 'authors': list(d['authors']),
            'venue': d['venue'], 'year': 2020, 'type': 'journal-article',
            'fulltext': fulltext, 'abstract': ''}


def _four_manifestation_graph(d):
    """One graph holding the four canonical manifestations for domain `d`, keyed by role.

      unresolved   -> UNRESOLVED_BINDING  (complete, but self-identifies nowhere)
      different    -> DIFFERENT_WORK       (foreign front-matter DOI)
      preprint     -> VERSION_OF_PREPRINT  (self-identifies + preprint furniture)
      journal      -> VERSION_OF_PUBLISHED (self-identifies + journal furniture)
    """
    rows = [
        _row(d, fulltext=(f'1. Introduction\n{NEUTRAL}\n4. Results\n'
                          'We estimate the effect is 0.2 units.\n')),        # unresolved
        _row(d, fulltext=(f'{d["title"]}\n{d["byline"]}\n'
                          f'{JOURNAL_MASTHEAD} doi: {d["foreign_doi"]}\n'
                          f'1. Introduction\n{FILLER}\n4. Results\n'
                          'We estimate the effect is 0.2 units.\n')),         # different work
        _row(d, fulltext=_scholarly_body(d, furniture=PREPRINT_STAMP)),       # preprint
        _row(d, fulltext=_scholarly_body(d, furniture='')),                   # journal
    ]
    g = P.migrate(rows)
    # migrate preserves order; recover the four manifestations positionally, then verify the LIVE
    # semantic binding each one derived, so the roles are asserted from the bytes, not assumed.
    mans = list(g.manifestations.values())
    assert len(mans) == 4, mans
    roles = dict(zip(('unresolved', 'different', 'preprint', 'journal'), mans))
    assert roles['unresolved'].profile['semantic_binding'] == 'UNRESOLVED_BINDING'
    assert roles['different'].profile['semantic_binding'] == 'DIFFERENT_WORK'
    assert roles['preprint'].profile['semantic_binding'] == 'VERSION_OF_PREPRINT'
    assert roles['journal'].profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
    return g, roles


# ══ THE FOUR IDENTITY FAILURES ARE PRE-SKIPPED INTO SEPARATE BUCKETS; THE TWO GOOD ONES SURVIVE ═════

@pytest.mark.parametrize('d', DOMAINS, ids=[d['id'] for d in DOMAINS])
@pytest.mark.parametrize('policy', [ANY_VERSION, JOURNAL_ONLY], ids=['any', 'journal_only'])
def test_preskip_selection_and_buckets(d, policy):
    g, roles = _four_manifestation_graph(d)
    units, skipped = EM._mining_units(g, [], policy)

    unit_ids = {u['manifestation_id'] for u in units}

    # unresolved and different work are ABSENT from mining units...
    assert roles['unresolved'].id not in unit_ids
    assert roles['different'].id not in unit_ids
    # ...and counted in SEPARATE buckets under the exact Sol names.
    assert {u['manifestation_id'] for u in skipped.get('identity_unresolved_lead', [])} \
        == {roles['unresolved'].id}
    assert {u['manifestation_id'] for u in skipped.get('different_work_quarantine', [])} \
        == {roles['different'].id}

    # the journal remains available for mining under BOTH policies...
    assert roles['journal'].id in unit_ids
    # ...and so does the preprint: VERSION_NOT_PERMITTED is NOT pre-skipped, because a verified
    # exact-span correspondence may yet name a permitted expression for one of its spans.
    assert roles['preprint'].id in unit_ids

    # the detail entries carry the required structured fields, not prose the caller must parse.
    for entry in skipped['identity_unresolved_lead'] + skipped['different_work_quarantine']:
        assert set(entry) >= {'manifestation_id', 'work_id', 'content_hash', 'identity_verdict',
                              'disposition', 'reason_code', 'why'}
    assert skipped['identity_unresolved_lead'][0]['reason_code'] == RC_IDENTITY_UNRESOLVED
    assert skipped['different_work_quarantine'][0]['reason_code'] == RC_IDENTITY_DIFFERENT_WORK
    assert skipped['identity_unresolved_lead'][0]['identity_verdict'] == 'UNRESOLVED_BINDING'
    assert skipped['different_work_quarantine'][0]['identity_verdict'] == 'DIFFERENT_WORK'


# ══ THE PRE-SKIPPED MANIFESTATIONS NEVER REACH THE LLM/MINER ═══════════════════════════════════════

@pytest.mark.parametrize('policy', [ANY_VERSION, JOURNAL_ONLY], ids=['any', 'journal_only'])
def test_llm_never_called_for_preskipped(tmp_path, monkeypatch, policy):
    d = DOMAINS[0]
    g, roles = _four_manifestation_graph(d)

    # A corpus file is required by mine(); its content is irrelevant here because we pass the graph.
    corpus_path = tmp_path / 'corpus.json'
    corpus_path.write_text(json.dumps([]))

    seen: list[str] = []

    def _spy_mine_paper(paper, *a, **kw):
        seen.append(paper['manifestation_id'])
        return []          # the actual LLM/harvest machinery below this point is never exercised

    monkeypatch.setattr(EM, 'mine_paper', _spy_mine_paper)

    EM.mine(corpus_path, question='', use_llm=True, graph=g, source_policy=policy)

    # the miner is invoked ONLY for the two admissible/available manifestations...
    assert roles['journal'].id in seen
    assert roles['preprint'].id in seen
    # ...and NEVER for the pre-skipped identity failures — no spend on bytes that can never be cited.
    assert roles['unresolved'].id not in seen
    assert roles['different'].id not in seen


# ══ UNKNOWN VERDICT AND DERIVATION CONFLICT GET THEIR OWN BUCKETS (in-memory corruption) ═══════════

def test_unknown_verdict_and_conflict_buckets():
    """The remaining two buckets fire on the structured reason_code the resolver emits for a tampered /
    corrupted in-memory graph. We corrupt AFTER a clean derive, exactly as an in-RAM bit-flip would, and
    assert the selector routes each to its own bucket without touching the good manifestations."""
    d = DOMAINS[0]
    g, roles = _four_manifestation_graph(d)

    # (a) an unknown semantic binding on the (previously) journal manifestation -> UNKNOWN_VERDICT.
    roles['journal'].profile['semantic_binding'] = 'SAMEISH_WORK'
    # (b) relabel the preprint's own expression node to a journal version without changing its bytes:
    #     the reducer still says VERSION_OF_PREPRINT, so the pair is impossible -> DERIVATION_CONFLICT.
    g.expressions[roles['preprint'].expression_id].kind = 'journal_version'

    units, skipped = EM._mining_units(g, [], ANY_VERSION)
    unit_ids = {u['manifestation_id'] for u in units}

    assert {u['manifestation_id'] for u in skipped.get('identity_integrity_quarantine', [])} \
        == {roles['journal'].id}
    assert {u['manifestation_id'] for u in skipped.get('derivation_conflict_quarantine', [])} \
        == {roles['preprint'].id}
    assert skipped['identity_integrity_quarantine'][0]['reason_code'] == RC_IDENTITY_UNKNOWN_VERDICT
    assert skipped['derivation_conflict_quarantine'][0]['reason_code'] == RC_DERIVATION_CONFLICT
    # the untouched unresolved/different manifestations are still routed to THEIR buckets, not these.
    assert roles['journal'].id not in unit_ids
    assert roles['preprint'].id not in unit_ids


# ══ METAMORPHIC: identical STRUCTURE across four unrelated domains => identical selection & counts ══

def test_metamorphic_counts_invariant_across_domains():
    """Replace every DOI, title, author, venue, and subject term across four unrelated fields. Because
    the selector keys on typed structure alone, the bucket counts and the surviving-unit count must be
    byte-for-byte identical for all of them — proof the P4 optimization is not tuned to any subject."""
    signatures = set()
    for d in DOMAINS:
        g, roles = _four_manifestation_graph(d)
        units, skipped = EM._mining_units(g, [], ANY_VERSION)
        sig = (len(units),
               len(skipped.get('identity_unresolved_lead', [])),
               len(skipped.get('different_work_quarantine', [])),
               len(skipped.get('identity_integrity_quarantine', [])),
               len(skipped.get('derivation_conflict_quarantine', [])))
        signatures.add(sig)
    assert len(signatures) == 1, signatures
    # the one signature is the expected shape: 2 survive (preprint+journal), 1 unresolved, 1 different.
    assert signatures == {(2, 1, 1, 0, 0)}
