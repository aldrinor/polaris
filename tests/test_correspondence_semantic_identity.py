"""P3 — correspondence and whole-copy edges must authorize on SEMANTIC IDENTITY, not the legacy
whole-body `identity.verdict`.

The disease this phase kills: the old `identity_agreement()` verdict ("CONFIRMED") scans the WHOLE
document, so it "confirms" any requested author it finds ANYWHERE — including in the references. A
manuscript that merely CITES the requested authors would score CONFIRMED, and the three correspondence
seams (`make_correspondence`, `Graph.exact_copy_failure`, `Graph.verify_correspondence`) trusted that
verdict. After P3 those seams re-derive the SEMANTIC BINDING from the bytes and the Work through the ONE
reducer, admit only `IDENTITY_PROVEN` verdicts, and reject a stale stored value.

Every fixture runs through the REAL chain: migrate()/ingest_bytes -> event_ledger.derive_binding_core.
No Attribution is mocked and no successful verdict is hand-assigned; the tests only stamp the LEGACY
`identity.verdict` to CONFIRMED to prove that the legacy layer cannot authorize anything.

Generality (Sol global rules 1 & 6): no rule under test keys on a DOI, title, author, venue, or subject
literal. The scholarly, legal, and registry variants are run over the SAME structure with every
identifier and subject term replaced; the structural result is identical in every case.
"""
import copy

import pytest

import provenance as P
from event_ledger import IDENTITY_PROVEN


# A span with DIGITS — canonicalization never touches them, so an exactly-shared span is exactly equal
# in both documents and a changed one is not (the Acemoglu test). Nothing here is a subject literal any
# rule reads; it is body prose the two documents happen to share.
SPAN = ('The estimated elasticity was 0.42 with a robust standard error of 0.06 across every '
        'specification we ran, and the point estimate did not move when controls were added.')

# A long neutral header (>= 10 readable words, no DOI, no byline cue, none of any requested title word).
# It fills the bounded identity window so that anything in the body/references is OUT of view.
_NEUTRAL_HEADER = ('Section one introduces the general setting and the notation carried throughout, '
                   'describing the framework in broad terms before any numeric result is presented. ') * 9
# Body padding that pushes the shared span and the references well past the 1500-char identity window.
_PAD = ('The work proceeds in several stages across many regions and time periods, laying out the '
        'design, the collected data, and the resulting estimates in complete detail. ') * 22


def _text(header_extra: str, refs_names: str) -> str:
    """One document. `header_extra` is any self-identifying furniture we CHOOSE to put in the front
    matter (a DOI line, a title, a byline) — empty for the unresolved case. `refs_names` are author
    names dropped in a references block, which is PAST the identity window and must never confirm."""
    head = _NEUTRAL_HEADER + (header_extra + ' ' if header_extra else '')
    body = _PAD + ' ' + SPAN + ' References. ' + refs_names
    return head + body


def _graph(rows):
    g = P.migrate(rows)
    mans = list(g.manifestations.values())
    return g, mans


def _stamp_legacy_confirmed(m):
    """Make the LEGACY whole-body identity say CONFIRMED — the precondition of every 'both fail' test.
    If the legacy verdict could authorize, this stamp would let it. It must not."""
    ident = dict(m.profile.get('identity') or {})
    ident['verdict'] = 'CONFIRMED'
    ident['basis'] = 'test fixture: legacy whole-body identity stamped CONFIRMED'
    m.profile['identity'] = ident


# ── the scholarly rows ───────────────────────────────────────────────────────────────────────────

def _scholarly_rows(*, doi_a, doi_b, title_a, title_b, authors_a, authors_b, prove):
    """Two scholarly documents that share SPAN verbatim. `prove` toggles whether each front matter
    self-identifies (an exact front-matter DOI -> SAME_WORK) or stays neutral (-> UNRESOLVED_BINDING).
    The shared SPAN bytes are IDENTICAL in both branches — only the header furniture changes."""
    head_a = f'doi: {doi_a}' if prove else ''
    head_b = f'doi: {doi_b}' if prove else ''
    refs_a = f'{authors_a[0]}, and {authors_a[1]}. Earlier study. Some Journal.'
    refs_b = f'{authors_b[0]}, and {authors_b[1]}. Earlier study. Some Journal.'
    row_a = {'doi': doi_a, 'title': title_a, 'authors': list(authors_a), 'venue': 'Journal of Widgets',
             'year': 2020, 'type': 'journal-article', 'fulltext': _text(head_a, refs_a), 'abstract': ''}
    row_b = {'doi': doi_b, 'title': title_b, 'authors': list(authors_b), 'venue': 'Journal of Gadgets',
             'year': 2020, 'type': 'journal-article', 'fulltext': _text(head_b, refs_b), 'abstract': ''}
    return [row_a, row_b]


_SCHOLARLY = dict(doi_a='10.1000/aaaa', doi_b='10.2000/bbbb',
                  title_a='A Rigorous Empirical Study of the Widget Mechanism',
                  title_b='A Careful Longitudinal Analysis of the Gadget Apparatus',
                  authors_a=('Adams', 'Brown'), authors_b=('Carter', 'Dupont'))


def _typed_rows(*, type_str, prove):
    """The SAME structure with two TYPED works (a court opinion / a trial registry record). Identity is
    proven by an exact self-title in the front matter, not by a byline or a field — the point of the
    metamorphic case. Every identifier and subject term differs from the scholarly rows."""
    title_a = 'Henderson versus Continental Freight Holdings Incorporated'
    title_b = 'Ferndale Municipal Authority versus Okafor Logistics Group'
    head_a = title_a if prove else ''
    head_b = title_b if prove else ''
    row_a = {'title': title_a, 'authors': [], 'year': 2018, 'venue': 'Court of Appeal', 'type': type_str,
             'fulltext': _text(head_a, 'Unrelated Reporter Citation 42.'), 'abstract': ''}
    row_b = {'title': title_b, 'authors': [], 'year': 2019, 'venue': 'High Court', 'type': type_str,
             'fulltext': _text(head_b, 'Unrelated Reporter Citation 91.'), 'abstract': ''}
    return [row_a, row_b]


# =================================================================================================
# 1. THE CORE FAILURE — legacy CONFIRMED must NOT authorize when semantic identity is unresolved
# =================================================================================================

def _corr(g, src, tgt):
    ss = src.text.index(SPAN)
    ts = tgt.text.index(SPAN)
    return P.make_correspondence(g, src.id, ss, ss + len(SPAN), tgt.id, ts, ts + len(SPAN),
                                 basis='exact canonical equality of the shared span in both held bytes')


def test_unresolved_bytes_block_correspondence_even_when_legacy_says_confirmed():
    g, (src, tgt) = _graph(_scholarly_rows(prove=False, **_SCHOLARLY))

    # Precondition: semantic identity is UNRESOLVED for BOTH, while legacy whole-body identity is CONFIRMED.
    for m in (src, tgt):
        assert m.profile['semantic_binding'] == 'UNRESOLVED_BINDING'
        _stamp_legacy_confirmed(m)
        assert m.profile['identity']['verdict'] == 'CONFIRMED'

    # (a) the whole-document exact_copy_of edge cannot be ASSERTED.
    with pytest.raises(ValueError) as ei:
        g.add_edge(src.expression_id, tgt.expression_id, 'exact_copy_of', 'ASSERTED',
                   basis='byte-for-byte comparison: identical')
    assert 'semantic binding' in str(ei.value)
    why = g.exact_copy_failure(src.expression_id, tgt.expression_id)
    assert why and 'PROVEN' in why

    # (b) the per-span correspondence does not verify, and add_correspondence refuses it.
    sc = _corr(g, src, tgt)
    ok, reasons = g.verify_correspondence(sc)
    assert ok is False
    assert any('semantic binding' in r for r in reasons)
    with pytest.raises(ValueError):
        g.add_correspondence(sc)
    assert g.correspondences == []          # nothing reached the graph on the legacy verdict's word


def test_valid_semantic_identity_admits_the_same_equal_span():
    # SAME shared SPAN bytes, now with self-identifying front matter -> SAME_WORK for both.
    g, (src, tgt) = _graph(_scholarly_rows(prove=True, **_SCHOLARLY))
    for m in (src, tgt):
        assert m.profile['semantic_binding'] in IDENTITY_PROVEN

    sc = _corr(g, src, tgt)
    assert sc.source_identity in IDENTITY_PROVEN and sc.target_identity in IDENTITY_PROVEN
    ok, reasons = g.verify_correspondence(sc)
    assert ok is True, reasons
    g.add_correspondence(sc)                # accepted — identity is proven and the span is exactly equal
    assert len(g.correspondences) == 1


# =================================================================================================
# 2. SEMANTIC BINDING, not the stored token, is authoritative
# =================================================================================================

def test_stale_stored_correspondence_identity_is_rejected():
    g, (src, tgt) = _graph(_scholarly_rows(prove=True, **_SCHOLARLY))
    sc = _corr(g, src, tgt)
    # A JSON file could carry a correspondence whose stored identity disagrees with the live bytes.
    sc.source_identity = 'DIFFERENT_WORK'
    ok, reasons = g.verify_correspondence(sc)
    assert ok is False
    assert any('stale' in r for r in reasons)


def test_correspondence_ignores_legacy_identity_field_entirely():
    # Prove identity, build a valid correspondence, then POISON only the legacy whole-body verdict to a
    # nonsense value on both nodes. Verification must be UNAFFECTED — it never reads that field.
    g, (src, tgt) = _graph(_scholarly_rows(prove=True, **_SCHOLARLY))
    sc = _corr(g, src, tgt)
    for m in (src, tgt):
        m.profile['identity'] = {'verdict': 'DIFFERENT_WORK', 'basis': 'poisoned legacy field'}
    ok, reasons = g.verify_correspondence(sc)
    assert ok is True, reasons


def test_different_work_source_cannot_lend_a_span():
    # A foreign front-matter DOI makes the SOURCE a DIFFERENT_WORK; even a byte-identical span may not
    # cross out of a stranger's paper.
    rows = _scholarly_rows(prove=False, **_SCHOLARLY)
    rows[0]['fulltext'] = _text(f'doi: 10.9999/foreign-{"stranger"}', 'Adams, and Brown. Prior.')
    # keep the shared span present in the (now foreign) source
    assert SPAN in rows[0]['fulltext']
    rows[1]['fulltext'] = _text('doi: 10.2000/bbbb', 'Carter, and Dupont. Prior.')  # target proven
    g, (src, tgt) = _graph(rows)
    assert src.profile['semantic_binding'] == 'DIFFERENT_WORK'
    sc = _corr(g, src, tgt)
    ok, reasons = g.verify_correspondence(sc)
    assert ok is False
    assert any('DIFFERENT_WORK' in r or 'semantic binding' in r for r in reasons)


# =================================================================================================
# 3. THE ACEMOGLU TEST still lives here — a non-identical span never verifies even when identity is proven
# =================================================================================================

def test_changed_span_fails_at_the_bytes_under_proven_identity():
    g, (src, tgt) = _graph(_scholarly_rows(prove=True, **_SCHOLARLY))
    # A span present only in the source; the target's byte at those offsets differs. Identity is proven,
    # so this is a pure byte failure — exactly the peer-review-changed-a-number case.
    ss = src.text.index(SPAN)
    # bind the source's span but point the target at a DIFFERENT equal-length body slice
    ts = tgt.text.index(_PAD.strip()[:len(SPAN)])
    sc = P.make_correspondence(g, src.id, ss, ss + len(SPAN),
                               tgt.id, ts, ts + len(SPAN), basis='claimed equal, but it is not')
    ok, reasons = g.verify_correspondence(sc)
    assert ok is False
    assert any('NOT equal' in r for r in reasons)


# =================================================================================================
# 4. METAMORPHIC — typed legal / registry works, same structure, same result
# =================================================================================================

@pytest.mark.parametrize('type_str, expect_kind', [
    ('case', 'case'),
    ('clinical-trial', 'trial'),
])
def test_typed_works_authorize_on_semantic_identity_not_field(type_str, expect_kind):
    # Unresolved variant: neither typed doc self-identifies -> UNRESOLVED_BINDING, correspondence fails
    # even with the legacy verdict stamped CONFIRMED.
    g, (src, tgt) = _graph(_typed_rows(type_str=type_str, prove=False))
    for m in (src, tgt):
        assert g.works[m.work_id].kind == expect_kind
        assert m.profile['semantic_binding'] == 'UNRESOLVED_BINDING'
        _stamp_legacy_confirmed(m)
    sc = _corr(g, src, tgt)
    ok, _ = g.verify_correspondence(sc)
    assert ok is False
    with pytest.raises(ValueError):
        g.add_correspondence(sc)

    # Proven variant: an exact self-title makes each typed work SAME_WORK; the SAME shared span verifies.
    g2, (src2, tgt2) = _graph(_typed_rows(type_str=type_str, prove=True))
    for m in (src2, tgt2):
        assert m.profile['semantic_binding'] == 'SAME_WORK'
    sc2 = _corr(g2, src2, tgt2)
    ok2, reasons2 = g2.verify_correspondence(sc2)
    assert ok2 is True, reasons2
    g2.add_correspondence(sc2)
    assert len(g2.correspondences) == 1


def test_metamorphic_identifier_swap_is_structurally_invariant():
    # Replace every DOI/title/author/venue with a completely different set; the STRUCTURE (neutral header
    # -> unresolved; self-DOI -> proven) is held constant. The authorization outcome must not change.
    alt = dict(doi_a='10.5555/qqqq', doi_b='10.6666/rrrr',
               title_a='An Exhaustive Field Investigation of the Sprocket Assembly',
               title_b='A Systematic Review of the Flange Coupling Procedure',
               authors_a=('Novak', 'Ortega'), authors_b=('Pran', 'Quill'))
    # unresolved both ways
    g0, (s0, t0) = _graph(_scholarly_rows(prove=False, **alt))
    assert s0.profile['semantic_binding'] == 'UNRESOLVED_BINDING'
    sc0 = _corr(g0, s0, t0)
    assert g0.verify_correspondence(sc0)[0] is False
    # proven both ways -> same equal span verifies
    g1, (s1, t1) = _graph(_scholarly_rows(prove=True, **alt))
    assert s1.profile['semantic_binding'] in IDENTITY_PROVEN
    sc1 = _corr(g1, s1, t1)
    assert g1.verify_correspondence(sc1)[0] is True


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
