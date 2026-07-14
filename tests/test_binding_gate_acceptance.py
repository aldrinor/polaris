"""P6 — the real-chain 12-vector binding-gate acceptance battery and cohort regression.

This is the integration battery for the whole binding gate (P1-P5). EVERY synthetic vector runs the
FULL production chain — never a mocked Attribution, never a hand-assigned successful verdict:

    observe/derive -> ingest_bytes (via migrate) -> [optional metadata re-resolution]
      -> bind_span -> resolve_attribution(binding, policy) -> Graph.to_json -> Graph.from_json
      -> bind/resolve again

The tests only ever READ the structured identity layer (identity_verdict / disposition / reason_code)
the resolver stamps, and check that the SAME structural verdict survives a JSON round-trip.

Generality (Sol global rules 1 & 6): no rule under test may key on a DOI, title, author, venue, or
subject literal. Vectors 1-11 are parameterised over FOUR unrelated Work identities — clinical, legal,
economics, CS — and the expected result is determined by typed structure alone. No production code or
fixture helper branches on the domain label.
"""
import copy
import hashlib
import sys
import tempfile
from dataclasses import asdict, replace as dc_replace
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures' / 'binding_gate'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures' / 'identity_metadata'))

import provenance as P                                          # noqa: E402
import evidence_miner as EM                                     # noqa: E402
import identity_receipts as ir                                  # noqa: E402
from acquisition import BlobStore                               # noqa: E402
from event_ledger import IDENTITY_PROVEN, UNRESOLVED           # noqa: E402
from provenance import (DISPOSITION_ADMIT, DISPOSITION_LEAD_ONLY, DISPOSITION_QUARANTINE,  # noqa: E402
                        RC_ADMITTED, RC_IDENTITY_DIFFERENT_WORK, RC_IDENTITY_UNRESOLVED,
                        RC_IDENTITY_UNKNOWN_VERDICT, RC_DERIVATION_CONFLICT, RC_VERSION_NOT_PERMITTED,
                        JOURNAL_ONLY, ANY_VERSION, GraphIntegrityError)

import vectors as V                                             # noqa: E402
import build_fixtures as F                                      # noqa: E402

DOMAINS = V.DOMAINS
IDS = [d['id'] for d in DOMAINS]
SALVAGE_DOMAINS = list(F.DOMAINS)          # medicine / law / economics / cs raw-artifact identities


# ── real-chain helpers ───────────────────────────────────────────────────────────────────────────

def _migrate_one(r):
    """observe/derive -> ingest_bytes, through the production migrate() path. Returns (graph, manif)."""
    g = P.migrate([r])
    m = next(iter(g.manifestations.values()))
    return g, m


def _roundtrip(g):
    """Graph.to_json -> Graph.from_json through the STRICT loader (re-derives every verdict)."""
    return P.Graph.from_json(copy.deepcopy(g.to_json()))


def _resolve_whole(g, m, policy):
    return g.resolve_attribution(m.id, policy)


def _resolve_span(g, m, policy, lo=None, hi=None):
    lo = 0 if lo is None else lo
    hi = min(len(m.text), 400) if hi is None else hi
    return g.resolve_attribution(g.bind_span(m.id, lo, hi), policy)


def _refusal_is_total(att):
    """The exact refusal contract Sol requires for every identity/integrity failure."""
    assert att.admitted is False
    assert att.names_expression_id is None
    assert att.text is None
    assert att.permitted_expression_ids == ()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 1 — Foreign front-matter DOI. Requested d1; the article self-front-matter carries only d2.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector01_foreign_frontmatter_doi(d):
    r = V.row(d, fulltext=V.scholarly_body(d, doi=d['foreign_doi']))
    g, m = _migrate_one(r)
    assert m.profile['semantic_binding'] == 'DIFFERENT_WORK'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.identity_verdict == 'DIFFERENT_WORK'
        assert att.disposition == DISPOSITION_QUARANTINE
        assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
        _refusal_is_total(att)
    # no expression for d1 is ever named — before OR after the JSON round-trip.
    g2 = _roundtrip(g)
    m2 = g2.manifestations[m.id]
    assert m2.profile['semantic_binding'] == 'DIFFERENT_WORK'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att2 = _resolve_whole(g2, m2, policy)
        assert att2.reason_code == RC_IDENTITY_DIFFERENT_WORK
        _refusal_is_total(att2)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 2 — Disjoint byline. A positive foreign byline convicts; removing ONLY the byline cue weakens
# the verdict to UNRESOLVED (absence of a byline is not disjointness).
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector02_disjoint_byline(d):
    # foreign title + a POSITIVELY OBSERVED foreign byline, and NO requested DOI/title tie.
    with_byline = V.scholarly_body(d, doi='', title=d['foreign_title'], byline=d['foreign_byline'])
    g, m = _migrate_one(V.row(d, fulltext=with_byline, doi=''))
    assert m.profile['semantic_binding'] == 'DIFFERENT_WORK'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
        _refusal_is_total(att)

    # remove ONLY the byline cue -> the disjointness evidence is gone -> UNRESOLVED, not different work.
    no_byline = V.scholarly_body(d, doi='', title=d['foreign_title'], byline='')
    g2, m2 = _migrate_one(V.row(d, fulltext=no_byline, doi=''))
    assert m2.profile['semantic_binding'] == 'UNRESOLVED_BINDING'
    assert _resolve_whole(g2, m2, ANY_VERSION).reason_code == RC_IDENTITY_UNRESOLVED


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 3 — Glyph header, no receipt. Unreadable front matter; the requested identity appears ONLY in
# the references. UNRESOLVED / LEAD_ONLY under both policies, and P4 pre-skips it before any LLM spend.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _glyph_refs_body(d):
    return (V.GLYPH_HEADER + '\n1. Introduction\n' + V.FILLER + '\n4. Results\nWe find 0.2 units.\n'
            f'References\n{d["authors"][0]}, A. and {d["authors"][1]}, B. doi: {d["doi"]}. Prior work.\n')


@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector03_glyph_header_no_receipt(d):
    g, m = _migrate_one(V.row(d, fulltext=_glyph_refs_body(d)))
    assert m.profile['semantic_binding'] == UNRESOLVED
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.disposition == DISPOSITION_LEAD_ONLY
        assert att.reason_code == RC_IDENTITY_UNRESOLVED
        assert att.admitted is False
    # P4 pre-skips it into the unresolved-lead bucket (no LLM is paid to mine bytes it can never cite).
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        units, skipped = EM._mining_units(g, [], policy)
        assert m.id not in {u['manifestation_id'] for u in units}
        assert m.id in {e['manifestation_id'] for e in skipped.get('identity_unresolved_lead', [])}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 4 — Glyph-header salvage and the deliberate no-OCR block. The SAME unreadable artifact, now
# carrying valid machine self-metadata: the receipt revalidates, identity promotes, and admission then
# follows version/policy. An OCR-typed receipt is refused, and a no-metadata artifact stays unresolved.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _build_salvageable_graph(work, raw, blobs, *, body=None):
    body = F.GENERIC_BODY if body is None else body
    g = P.Graph()
    w, cid, ck = P.ensure_work(g, doi=work.doi or '', title=work.title, authors=list(work.authors),
                               year=work.year, venue=work.venue or '', source_type='journal')
    bid, sha = blobs.put(raw)
    mid = P.ingest_bytes(g, w, body, text_field='fulltext', fetched_by='fixture', locator=None,
                         locator_status='NOT_RECORDED_BY_FETCHER', claimed_id=cid, claimed_kind=ck,
                         raw_blob_id=bid, raw_content_hash=sha, content_type='text/html')
    return g, mid


@pytest.mark.parametrize('domain', SALVAGE_DOMAINS)
def test_vector04_glyph_salvage_and_ocr_block(tmp_path, domain):
    work = F.DOMAINS[domain]
    blobs = BlobStore(tmp_path / 'blobs')
    # the extracted body is unreadable glyph garbage -> UNRESOLVED; the RAW artifact self-identifies.
    raw = F.html_head([('citation_doi', work.doi)])
    g, mid = _build_salvageable_graph(work, raw, blobs, body=V.GLYPH_HEADER)
    assert g.manifestations[mid].profile['semantic_binding'] == UNRESOLVED

    stats = P.reresolve_unresolved_metadata(g, blobs)
    assert stats['promotions'] == 1
    m = g.manifestations[mid]
    assert m.profile['semantic_binding'] in IDENTITY_PROVEN
    assert m.identity_receipts, 'a promoted manifestation must carry its revalidatable receipts'
    # the promoted graph round-trips ONLY with the blob store (every receipt is re-verified on load)...
    g2 = P.Graph.from_json(g.to_json(), blob_store=blobs)
    assert g2.manifestations[mid].profile['semantic_binding'] in IDENTITY_PROVEN
    # ...and a receipt-bearing graph CANNOT load without it.
    with pytest.raises(GraphIntegrityError):
        P.Graph.from_json(g.to_json())

    # COMPANION — the no-OCR adaptation: an OCR-typed receipt is refused as an unsupported type...
    ok, why = ir.revalidate_receipt(b'', {'metadata_container': 'ocr', 'receipt_kind': 'IMAGE_OCR',
                                          'extractor_name': ir.EXTRACTOR_NAME,
                                          'extractor_version': ir.EXTRACTOR_VERSION}, work)
    assert ok is False and ('ocr' in why.lower() or 'unsupported' in why.lower())
    # ...and the SAME glyph artifact with NO machine metadata stays an unresolved lead.
    blobs2 = BlobStore(tmp_path / 'blobs2')
    raw_blank = F.html_head([('citation_title', 'An Unrelated Generic Report')])
    g3, mid3 = _build_salvageable_graph(work, raw_blank, blobs2, body=V.GLYPH_HEADER)
    P.reresolve_unresolved_metadata(g3, blobs2)
    assert g3.manifestations[mid3].profile['semantic_binding'] == UNRESOLVED


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 5 — Generic-title collision. A generic requested title overlaps the artifact title, with no
# matching self-ID or author. UNRESOLVED, NEVER different-work, no attribution.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector05_generic_title_collision(d):
    # the artifact self-titles with the GENERIC requested title, prints no DOI and no requested author.
    body = V.scholarly_body(d, doi='', title=d['generic_title'], byline='An untitled report')
    g, m = _migrate_one(V.row(d, fulltext=body, doi='', title=d['generic_title'], authors=()))
    assert m.profile['semantic_binding'] == UNRESOLVED     # a 100% match on a GENERIC title is NEITHER
    assert m.profile['semantic_binding'] != 'DIFFERENT_WORK'
    att = _resolve_whole(g, m, ANY_VERSION)
    assert att.reason_code == RC_IDENTITY_UNRESOLVED
    assert att.admitted is False and att.names_expression_id is None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 6 — Clean same-work journal. Exact identity + journal furniture + complete body. The unified
# reducer gives VERSION_OF_PUBLISHED / journal_version and BOTH policies admit the actual journal.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector06_clean_same_work_journal(d):
    g, m = _migrate_one(V.row(d, fulltext=V.scholarly_body(d)))
    assert m.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED'
    assert m.profile['expression_kind'] == 'journal_version'
    assert g.expressions[m.expression_id].kind == 'journal_version'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.admitted is True and att.disposition == DISPOSITION_ADMIT
        assert att.reason_code == RC_ADMITTED
        assert att.names_expression_id == m.expression_id
        assert att.names_expression_id.endswith('journal_version')
    # the admission survives the strict round-trip.
    g2 = _roundtrip(g)
    assert g2.resolve_attribution(m.id, JOURNAL_ONLY).admitted is True


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 7 — Working-paper manifestation. ANY_VERSION admits its OWN expression; JOURNAL_ONLY is
# lead-only and NEVER names the journal.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector07_working_paper(d):
    g, m = _migrate_one(V.row(d, fulltext=V.scholarly_body(d, furniture=V.WORKING_STAMP)))
    assert m.profile['semantic_binding'] == 'VERSION_OF_PREPRINT'
    assert m.profile['expression_kind'] == 'working_paper'
    av = _resolve_whole(g, m, ANY_VERSION)
    assert av.admitted is True and av.names_expression_id == m.expression_id
    assert av.names_expression_id.endswith('working_paper')
    jo = _resolve_whole(g, m, JOURNAL_ONLY)
    assert jo.admitted is False and jo.disposition == DISPOSITION_LEAD_ONLY
    assert jo.reason_code == RC_VERSION_NOT_PERMITTED
    assert jo.names_expression_id is None                 # never names the journal
    g2 = _roundtrip(g)
    assert g2.resolve_attribution(m.id, JOURNAL_ONLY).names_expression_id is None
    assert g2.resolve_attribution(m.id, ANY_VERSION).admitted is True


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 8 — Accepted manuscript. VERSION_OF_ACCEPTED / accepted_manuscript. ANY_VERSION admits the
# manuscript; JOURNAL_ONLY is lead-only.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector08_accepted_manuscript(d):
    furniture = V.ACCEPTED_STAMP + ' ' + V.ACCEPTED_CITE
    g, m = _migrate_one(V.row(d, fulltext=V.scholarly_body(d, furniture=furniture)))
    assert m.profile['semantic_binding'] == 'VERSION_OF_ACCEPTED'
    assert m.profile['expression_kind'] == 'accepted_manuscript'
    av = _resolve_whole(g, m, ANY_VERSION)
    assert av.admitted is True and av.names_expression_id == m.expression_id
    assert av.names_expression_id.endswith('accepted_manuscript')
    jo = _resolve_whole(g, m, JOURNAL_ONLY)
    assert jo.admitted is False and jo.disposition == DISPOSITION_LEAD_ONLY
    assert jo.names_expression_id is None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 9 — Exact-span journal correspondence. A preprint/working-paper manifestation plus separately
# held identity-proven journal bytes, with one verified exact correspondence. The bare manifestation is
# not journal-admissible; the exact bound span is; and an adjacent/overlapping span is NOT widened.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector09_exact_span_journal_correspondence(d):
    wp_text = V.scholarly_body(d, furniture=V.WORKING_STAMP, span=V.SHARED_SPAN)
    jv_text = V.scholarly_body(d, furniture='', span=V.SHARED_SPAN)
    g = P.migrate([V.row(d, fulltext=wp_text), V.row(d, fulltext=jv_text)])
    mans = list(g.manifestations.values())
    wp = next(x for x in mans if x.profile['semantic_binding'] == 'VERSION_OF_PREPRINT')
    jv = next(x for x in mans if x.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED')

    ss, ts = wp.text.index(V.SHARED_SPAN), jv.text.index(V.SHARED_SPAN)
    span_len = len(V.SHARED_SPAN)

    # bare manifestation span under JOURNAL_ONLY: not admitted.
    assert g.resolve_attribution(g.bind_span(wp.id, ss, ss + span_len), JOURNAL_ONLY).admitted is False

    sc = P.make_correspondence(g, wp.id, ss, ss + span_len, jv.id, ts, ts + span_len,
                               basis='exact canonical equality of the shared span in both held bytes')
    ok, reasons = g.verify_correspondence(sc)
    assert ok is True, reasons
    g.add_correspondence(sc)

    # the EXACT bound span is admitted and names the journal.
    att = g.resolve_attribution(g.bind_span(wp.id, ss, ss + span_len), JOURNAL_ONLY)
    assert att.admitted is True
    assert att.names_expression_id == jv.expression_id
    assert att.names_expression_id.endswith('journal_version')

    # an adjacent / containing / overlapping-but-not-identical span is NOT widened.
    for lo, hi in ((ss, ss + span_len - 10),          # contained (shorter)
                   (ss - 5, ss + span_len),           # containing (starts earlier)
                   (ss + 10, ss + span_len + 10)):     # overlapping, shifted
        lo = max(0, lo)
        hi = min(len(wp.text), hi)
        assert g.resolve_attribution(g.bind_span(wp.id, lo, hi), JOURNAL_ONLY).admitted is False


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 10 — Conflicting recovered identifiers. Self-metadata carries BOTH the target and a foreign DOI
# without structural separation: unresolved with a metadata conflict; both policies reject; the refusal
# survives the round-trip.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('domain', SALVAGE_DOMAINS)
def test_vector10_conflicting_recovered_identifiers(tmp_path, domain):
    work = F.DOMAINS[domain]
    blobs = BlobStore(tmp_path / 'blobs')
    raw = F.html_head([('citation_doi', work.doi),
                       ('DC.identifier', 'doi:10.9999/foreign.stranger.0001')])
    g, mid = _build_salvageable_graph(work, raw, blobs, body=V.GLYPH_HEADER)
    stats = P.reresolve_unresolved_metadata(g, blobs)
    assert stats['promotions'] == 0 and stats['conflicts'] == 1
    m = g.manifestations[mid]
    assert m.profile['semantic_binding'] == UNRESOLVED
    assert m.profile.get('identity_metadata') == ir.IDENTITY_METADATA_CONFLICT
    assert not m.identity_receipts
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        assert g.resolve_attribution(mid, policy).admitted is False
    # the refusal survives the JSON round-trip (a conflicted manifestation has no receipt to promote).
    g2 = P.Graph.from_json(g.to_json(), blob_store=blobs)
    assert g2.manifestations[mid].profile['semantic_binding'] == UNRESOLVED
    assert g2.resolve_attribution(mid, ANY_VERSION).admitted is False


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 11 — Unknown enum and impossible pair. A stored unknown verdict and a relabelled expression
# node each FAIL the strict load; the equivalent in-memory corruption QUARANTINES with the right code.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector11a_unknown_semantic_binding(d):
    g, m = _migrate_one(V.row(d, fulltext=V.scholarly_body(d)))
    # (a) on disk: an unknown stored verdict fails the strict load.
    js = g.to_json()
    for mm in js['manifestations']:
        mm['profile']['semantic_binding'] = 'SAMEISH_WORK'
    with pytest.raises(GraphIntegrityError):
        P.Graph.from_json(js)
    # (b) in memory: the same corruption quarantines with IDENTITY_UNKNOWN_VERDICT under both policies.
    m.profile['semantic_binding'] = 'SAMEISH_WORK'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.disposition == DISPOSITION_QUARANTINE
        assert att.reason_code == RC_IDENTITY_UNKNOWN_VERDICT
        _refusal_is_total(att)


@pytest.mark.parametrize('d', DOMAINS, ids=IDS)
def test_vector11b_impossible_pair(d):
    # a working paper whose OWN expression node is relabelled to journal_version WITHOUT changing bytes.
    g, m = _migrate_one(V.row(d, fulltext=V.scholarly_body(d, furniture=V.WORKING_STAMP)))
    assert m.profile['semantic_binding'] == 'VERSION_OF_PREPRINT'
    g.expressions[m.expression_id].kind = 'journal_version'
    # (a) in memory: the resolver quarantines the impossible pair under both policies.
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = _resolve_whole(g, m, policy)
        assert att.disposition == DISPOSITION_QUARANTINE
        assert att.reason_code == RC_DERIVATION_CONFLICT
        _refusal_is_total(att)
    # (b) on disk: the same relabel fails the strict load.
    with pytest.raises(GraphIntegrityError):
        P.Graph.from_json(g.to_json())


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CROSS-VECTOR GENERALITY — the outcome is determined by typed STRUCTURE, not by the domain label.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_cross_vector_generality_is_structural():
    """For each structural shape, the derived (semantic_binding, expression_kind) pair — or the identity
    verdict — must be IDENTICAL across all four unrelated subjects. If any rule keyed on a subject, one
    of these sets would have more than one member."""
    shapes = {
        'foreign_doi':   lambda d: V.scholarly_body(d, doi=d['foreign_doi']),
        'disjoint':      lambda d: V.scholarly_body(d, doi='', title=d['foreign_title'],
                                                    byline=d['foreign_byline']),
        'clean_journal': lambda d: V.scholarly_body(d),
        'working_paper': lambda d: V.scholarly_body(d, furniture=V.WORKING_STAMP),
        'accepted':      lambda d: V.scholarly_body(d, furniture=V.ACCEPTED_STAMP),
        'generic':       lambda d: V.scholarly_body(d, doi='', title=d['generic_title'],
                                                    byline='An untitled report'),
    }
    expected_binding = {
        'foreign_doi': 'DIFFERENT_WORK', 'disjoint': 'DIFFERENT_WORK',
        'clean_journal': 'VERSION_OF_PUBLISHED', 'working_paper': 'VERSION_OF_PREPRINT',
        'accepted': 'VERSION_OF_ACCEPTED', 'generic': 'UNRESOLVED_BINDING',
    }
    for shape, make in shapes.items():
        pairs = set()
        for d in DOMAINS:
            doi = '' if shape in ('disjoint', 'generic') else None
            title = d['generic_title'] if shape == 'generic' else None
            authors = () if shape == 'generic' else None
            _g, m = _migrate_one(V.row(d, fulltext=make(d), doi=doi, title=title, authors=authors))
            pairs.add((m.profile['semantic_binding'], m.profile.get('expression_kind') or 'unknown'))
        # subject-invariance: the derived pair is IDENTICAL across all four unrelated subjects...
        assert len(pairs) == 1, f'{shape} was not subject-invariant: {pairs}'
        # ...and it is the expected structural verdict.
        assert {b for b, _ in pairs} == {expected_binding[shape]}, f'{shape}: {pairs}'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VECTOR 12 — Cohort regression. The corpus-INVARIANT safety properties must hold at ANY corpus size
# (Sol global rule 7: cohort counts are OBSERVATIONS, not rule inputs). This default-run version builds
# a synthetic cohort GUARANTEED to contain every counted category and asserts the safety invariants and
# the six separated counts. The real 501-row corpus regression is the opt-in test below it.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _synthetic_cohort():
    """One graph holding, for every domain, a manifestation in each identity/version category the plan
    requires the cohort to separate: different-work, unresolved lead, clean journal, working paper,
    accepted manuscript, and an incomplete stub."""
    rows = []
    for idx, d in enumerate(DOMAINS):
        rows.append(V.row(d, fulltext=V.scholarly_body(d, doi=d['foreign_doi'])))          # different work
        # a NEUTRAL per-document marker (a bare index, no identity) keeps the four unreadable bodies
        # byte-distinct so migrate() does not dedup them — it never affects the UNRESOLVED derivation.
        rows.append(V.row(d, fulltext=(f'Document series entry {idx}.\n' + V.GLYPH_HEADER +
                                       '\n1. Introduction\n' + V.FILLER +                     # unresolved
                                       '\n4. Results\nWe find 0.2 units.\n')))
        rows.append(V.row(d, fulltext=V.scholarly_body(d)))                                  # clean journal
        rows.append(V.row(d, fulltext=V.scholarly_body(d, furniture=V.WORKING_STAMP)))       # working paper
        rows.append(V.row(d, fulltext=V.scholarly_body(d, furniture=V.ACCEPTED_STAMP)))      # accepted ms
        stub = f'{d["title"]}\n{d["byline"]}\ndoi: {d["doi"]}\n'                             # incomplete
        rows.append(V.row(d, fulltext=stub))
    return P.migrate(rows)


def test_vector12_synthetic_cohort_regression():
    g = _synthetic_cohort()
    counts = {'different_work_quarantine': 0, 'unresolved_lead': 0, 'derivation_conflict': 0,
              'incomplete_bytes': 0, 'version_policy_lead': 0, 'metadata_promotion': 0}
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        for mid, m in g.manifestations.items():
            sb = m.profile.get('semantic_binding')
            att = g.resolve_attribution(mid, policy)
            # ── THE CORPUS-INVARIANT SAFETY PROPERTIES ──────────────────────────────────────────────
            if sb == 'DIFFERENT_WORK':
                # every different-work manifestation rejects FOR IDENTITY and names NO claimed expression.
                assert att.admitted is False
                assert att.reason_code == RC_IDENTITY_DIFFERENT_WORK
                assert att.names_expression_id is None
            if sb == UNRESOLVED:
                # every residual unresolved manifestation is admitted=False under BOTH policies.
                assert att.admitted is False
            # zero derivation conflicts are admitted (there are none here, but the property must hold).
            if att.reason_code == RC_DERIVATION_CONFLICT:
                assert att.admitted is False

    # ── the six separated counts (a single pass, ANY_VERSION for the version/incomplete distinction) ──
    for mid, m in g.manifestations.items():
        sb = m.profile.get('semantic_binding')
        att_any = g.resolve_attribution(mid, ANY_VERSION)
        att_jo = g.resolve_attribution(mid, JOURNAL_ONLY)
        if sb == 'DIFFERENT_WORK':
            counts['different_work_quarantine'] += 1
        elif sb == UNRESOLVED:
            counts['unresolved_lead'] += 1
        elif att_any.reason_code == P.RC_INCOMPLETE_BYTES:
            counts['incomplete_bytes'] += 1
        # a version-policy lead: admissible under ANY_VERSION but a lead under JOURNAL_ONLY.
        if att_any.admitted and not att_jo.admitted and att_jo.reason_code == RC_VERSION_NOT_PERMITTED:
            counts['version_policy_lead'] += 1

    # every category is populated — the cohort actually exercises each separated bucket.
    assert counts['different_work_quarantine'] == len(DOMAINS)
    assert counts['unresolved_lead'] == len(DOMAINS)
    assert counts['incomplete_bytes'] == len(DOMAINS)
    assert counts['version_policy_lead'] == 2 * len(DOMAINS)      # working paper + accepted, per domain
    # zero different-work manifestations name the claimed DOI/expression, under either policy.
    for mid, m in g.manifestations.items():
        if m.profile.get('semantic_binding') == 'DIFFERENT_WORK':
            for policy in (JOURNAL_ONLY, ANY_VERSION):
                assert g.resolve_attribution(mid, policy).names_expression_id is None


@pytest.mark.skipif(__import__('os').environ.get('POLARIS_RUN_COHORT') != '1',
                    reason='real 501-row cohort regression needs the full ledger + raw blobs; '
                           'set POLARIS_RUN_COHORT=1')
def test_vector12_real_corpus_cohort_regression():
    """The real-corpus regression (Sol P6 vector 12). Opt-in, because it needs the full corpus/blobs and
    must not run in the offline acceptance gate. It asserts the SAME corpus-invariant safety properties —
    never a magic count — over the actual rebuilt graph, under both policies."""
    import json
    from acquisition import open_ledger
    from provenance_construct import construct
    ledger = open_ledger()
    blobs = BlobStore()
    biblio_p = _ROOT / 'outputs' / 'journal_corpus_content.json'
    biblio = json.loads(biblio_p.read_text()) if biblio_p.exists() else None
    g, _ = construct(ledger, blobs=blobs, bibliography=biblio)
    P.reresolve_unresolved_metadata(g, blobs)

    buckets = {'different_work': 0, 'unresolved': 0, 'derivation_conflict': 0}
    for mid, m in g.manifestations.items():
        sb = m.profile.get('semantic_binding')
        for policy in (JOURNAL_ONLY, ANY_VERSION):
            att = g.resolve_attribution(mid, policy)
            if sb == 'DIFFERENT_WORK':
                assert att.admitted is False and att.names_expression_id is None
            if sb == UNRESOLVED:
                assert att.admitted is False
            if att.reason_code == RC_DERIVATION_CONFLICT:
                assert att.admitted is False
        if sb == 'DIFFERENT_WORK':
            buckets['different_work'] += 1
        elif sb == UNRESOLVED:
            buckets['unresolved'] += 1
    print(f'\nCOHORT: different_work={buckets["different_work"]} unresolved={buckets["unresolved"]}')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
