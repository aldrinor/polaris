"""P5 — positive machine-metadata salvage for unresolved manifestations.

Every test drives the REAL chain: ingest bytes that derive UNRESOLVED_BINDING, run the salvage
reducer over the raw artifact, and check that identity is promoted ONLY on positive, revalidatable
self-metadata — and never on a stranger's DOI, a body mention, a generic title, or a conflicting
self-identifier. Loader revalidation and OCR refusal are exercised end-to-end through to_json/from_json.

No production code branches on any subject/domain label: the metamorphic test proves the outcome is
determined by structure by swapping four unrelated Work identities and changing only the identifier.
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures' / 'identity_metadata'))

import identity_receipts as ir           # noqa: E402
import provenance as P                    # noqa: E402
from acquisition import BlobStore         # noqa: E402
from event_ledger import IDENTITY_PROVEN, UNRESOLVED  # noqa: E402
import build_fixtures as F                # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_CT = {'pdf': 'application/pdf', 'html': 'text/html', 'jats': 'application/xml'}


def _salvage(raw, work, media):
    return ir.build_salvage(
        raw, work, manifestation_id='m', manifestation_content_hash='ch',
        artifact_blob_id='sha256:' + hashlib.sha256(raw).hexdigest(),
        artifact_sha256=hashlib.sha256(raw).hexdigest(), media_type=media)


def _build_unresolved_graph(work_obj, raw, media, blobs):
    """Ingest a generic body (-> UNRESOLVED) with raw-artifact lineage into a fresh graph."""
    g = P.Graph()
    w, claimed_id, claimed_kind = P.ensure_work(
        g, doi=work_obj.doi or '', title=work_obj.title, authors=list(work_obj.authors),
        year=work_obj.year, venue=work_obj.venue or '', source_type='journal')
    blob_id, sha = blobs.put(raw)
    mid = P.ingest_bytes(
        g, w, F.GENERIC_BODY, text_field='fulltext', fetched_by='fixture',
        locator=None, locator_status='NOT_RECORDED_BY_FETCHER',
        claimed_id=claimed_id, claimed_kind=claimed_kind,
        raw_blob_id=blob_id, raw_content_hash=sha, content_type=_CT[media])
    return g, mid


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The six admissible containers promote; the four non-promoting shapes do not.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('fx', F.promoting_fixtures(), ids=lambda f: f['name'])
def test_six_containers_promote(fx):
    res = _salvage(fx['raw'], fx['work'], fx['media'])
    assert res.conflict == '', f'{fx["name"]} unexpectedly conflicted: {res.basis}'
    assert res.receipts, f'{fx["name"]} produced no receipt: {res.basis}'
    # a verified receipt, fed to the reducer, promotes identity out of UNRESOLVED
    from event_ledger import observe_text, derive_binding_core
    sup = ir.receipts_supplement(res.receipts)
    prof = {**observe_text(F.GENERIC_BODY), **sup}
    verdict, _ = derive_binding_core(
        requested_doi=fx['work'].doi or '', requested_title=fx['work'].title,
        requested_authors=list(fx['work'].authors), prof=prof)
    assert verdict in IDENTITY_PROVEN, f'{fx["name"]} did not promote: {verdict}'
    # every promoting receipt revalidates against its own raw bytes
    from dataclasses import asdict
    ok, errs = ir.revalidate_all(fx['raw'], [asdict(r) for r in res.receipts], fx['work'])
    assert ok, errs


@pytest.mark.parametrize('fx', F.non_promoting_fixtures(), ids=lambda f: f['name'])
def test_non_promoting_shapes_stay_unresolved(fx):
    res = _salvage(fx['raw'], fx['work'], fx['media'])
    if fx['expect'] == 'conflict':
        assert res.conflict == ir.IDENTITY_METADATA_CONFLICT
        assert not res.receipts
    else:
        assert res.conflict == ''
        assert not res.receipts, f'{fx["name"]} should not have promoted: {res.basis}'


def test_exactly_six_of_the_thirteen_promote():
    """The plan's headline assertion: of the thirteen fixtures, ONLY the first six promote."""
    promoted = sum(1 for fx in F.promoting_fixtures()
                   if _salvage(fx['raw'], fx['work'], fx['media']).receipts)
    non_promoted = sum(1 for fx in F.non_promoting_fixtures()
                       if _salvage(fx['raw'], fx['work'], fx['media']).receipts)
    assert promoted == 6
    assert non_promoted == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The full graph chain: ingest UNRESOLVED -> reresolve -> promote -> to_json -> from_json.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_reresolve_promotes_and_roundtrips(tmp_path):
    blobs = BlobStore(tmp_path / 'blobs')
    fx = F.promoting_fixtures()[0]                 # PDF Info DOI
    g, mid = _build_unresolved_graph(fx['work'], fx['raw'], fx['media'], blobs)
    assert g.manifestations[mid].profile['semantic_binding'] == UNRESOLVED
    assert not g.manifestations[mid].identity_receipts

    stats = P.reresolve_unresolved_metadata(g, blobs)
    assert stats['promotions'] == 1
    m = g.manifestations[mid]
    assert m.profile['semantic_binding'] in IDENTITY_PROVEN
    assert m.identity_receipts, 'a promoted manifestation must carry its receipts'
    assert m.profile['semantic_binding_derived_by'].startswith('identity_receipts:')

    # the promoted graph round-trips through the STRICT loader WITH the blob store
    js = g.to_json()
    g2 = P.Graph.from_json(js, blob_store=blobs)
    assert g2.manifestations[mid].profile['semantic_binding'] in IDENTITY_PROVEN

    # ...and a graph carrying receipts CANNOT load without the blob store
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(js)


def test_promoted_but_versionless_is_lead_only_never_admitted(tmp_path):
    """Promotion settles IDENTITY, not VERSION. A salvaged body with no version furniture is
    identity-proven but still LEAD_ONLY under every policy — it is never admitted as a journal."""
    blobs = BlobStore(tmp_path / 'blobs')
    fx = F.promoting_fixtures()[2]                 # HTML citation_doi
    g, mid = _build_unresolved_graph(fx['work'], fx['raw'], fx['media'], blobs)
    P.reresolve_unresolved_metadata(g, blobs)
    for policy in (P.ANY_VERSION, P.JOURNAL_ONLY):
        att = g.resolve_attribution(mid, policy)
        assert att.admitted is False
        assert att.names_expression_id is None
        # identity IS proven now (no longer a stranger / unresolved); it fails downstream on version or
        # completeness, never on an identity-fabrication verdict.
        assert att.identity_verdict in IDENTITY_PROVEN
        assert att.reason_code != P.RC_IDENTITY_DIFFERENT_WORK
        assert att.reason_code != P.RC_IDENTITY_UNRESOLVED


def test_conflict_leaves_unresolved_and_unpromoted(tmp_path):
    blobs = BlobStore(tmp_path / 'blobs')
    fx = next(f for f in F.non_promoting_fixtures() if f['expect'] == 'conflict')
    g, mid = _build_unresolved_graph(fx['work'], fx['raw'], fx['media'], blobs)
    stats = P.reresolve_unresolved_metadata(g, blobs)
    assert stats['promotions'] == 0
    assert stats['conflicts'] == 1
    m = g.manifestations[mid]
    assert m.profile['semantic_binding'] == UNRESOLVED
    assert m.profile.get('identity_metadata') == ir.IDENTITY_METADATA_CONFLICT
    assert not m.identity_receipts
    # a conflicting manifestation resolves to a lead, never an admission
    assert g.resolve_attribution(mid, P.ANY_VERSION).admitted is False


def test_no_raw_artifact_cannot_be_salvaged(tmp_path):
    """A manifestation with no raw blob (legacy row, abstract-only) stays a residual lead."""
    blobs = BlobStore(tmp_path / 'blobs')
    g = P.Graph()
    w, cid, ck = P.ensure_work(g, doi='10.1/none', title='A Distinctive Untraceable Study',
                               authors=['Ghost'], year=2020, venue='J', source_type='journal')
    mid = P.ingest_bytes(g, w, F.GENERIC_BODY, text_field='fulltext', fetched_by='x',
                         locator=None, locator_status='NOT_RECORDED_BY_FETCHER',
                         claimed_id=cid, claimed_kind=ck)   # NO raw lineage
    stats = P.reresolve_unresolved_metadata(g, blobs)
    assert stats['promotions'] == 0
    assert stats['no_raw_artifact'] == 1
    assert g.manifestations[mid].profile['semantic_binding'] == UNRESOLVED


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. Loader refuses tampered raw artifacts, tampered offsets, and unsupported (OCR) receipts.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _promoted_json(tmp_path):
    blobs = BlobStore(tmp_path / 'blobs')
    fx = F.promoting_fixtures()[2]                 # HTML citation_doi
    g, mid = _build_unresolved_graph(fx['work'], fx['raw'], fx['media'], blobs)
    P.reresolve_unresolved_metadata(g, blobs)
    return g.to_json(), blobs, mid


def _manifest(js, mid):
    return next(m for m in js['manifestations'] if m['id'] == mid)


def test_loader_refuses_tampered_receipt_offsets(tmp_path):
    js, blobs, mid = _promoted_json(tmp_path)
    rec = _manifest(js, mid)['identity_receipts'][0]
    rec['start_offset'], rec['end_offset'] = rec['start_offset'] + 3, rec['end_offset'] + 3
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(js, blob_store=blobs)


def test_loader_refuses_tampered_raw_artifact(tmp_path):
    js, blobs, mid = _promoted_json(tmp_path)
    # point the manifestation at a DIFFERENT raw artifact (one with no self-DOI at all)
    benign = F.html_head([('citation_title', 'Nothing Here')])
    bid, bsha = blobs.put(benign)
    m = _manifest(js, mid)
    m['raw_blob_id'], m['raw_content_hash'] = bid, bsha
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(js, blob_store=blobs)


def test_loader_refuses_unsupported_ocr_receipt(tmp_path):
    js, blobs, mid = _promoted_json(tmp_path)
    rec = _manifest(js, mid)['identity_receipts'][0]
    rec['metadata_container'] = 'ocr'              # not a supported, revalidatable container
    rec['receipt_kind'] = 'IMAGE_OCR'
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(js, blob_store=blobs)


def test_ocr_receipt_is_refused_by_revalidator_directly():
    """An OCR-typed receipt supplied through JSON must be refused as an unsupported receipt type."""
    ok, why = ir.revalidate_receipt(b'', {'metadata_container': 'ocr', 'receipt_kind': 'IMAGE_OCR',
                                          'extractor_name': ir.EXTRACTOR_NAME,
                                          'extractor_version': ir.EXTRACTOR_VERSION}, F.DOMAINS['cs'])
    assert ok is False
    assert 'ocr' in why.lower() or 'unsupported' in why.lower()


def test_loader_refuses_forged_promotion_without_receipt(tmp_path):
    """The salvage superhighway attack: hand-edit a stored SAME_WORK onto UNRESOLVED bytes with NO
    receipt to back it. The loader re-derives from bytes and refuses the promotion."""
    blobs = BlobStore(tmp_path / 'blobs')
    fx = F.promoting_fixtures()[2]
    g, mid = _build_unresolved_graph(fx['work'], fx['raw'], fx['media'], blobs)
    js = g.to_json()
    m = _manifest(js, mid)
    m['profile']['semantic_binding'] = 'SAME_WORK'   # forged, no receipt supports it
    with pytest.raises(P.GraphIntegrityError):
        P.Graph.from_json(js, blob_store=blobs)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. Metamorphic: the outcome is structural. Swap four unrelated identities; change only the DOI.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('domain', list(F.DOMAINS))
def test_metamorphic_identifier_swap(domain):
    work = F.DOMAINS[domain]
    raw = F.html_head([('citation_doi', work.doi)])

    # extraction behavior is a property of the CONTAINER, not the identity
    obs = ir.extract_field_observations(raw, 'html')
    doi_fields = [o for o in obs if o['field'] == ir.FIELD_DOI]
    assert len(doi_fields) == 1

    # with the matching identity -> promotes
    good = _salvage(raw, work, 'html')
    assert good.receipts and not good.conflict

    # change ONLY the requested DOI (same artifact) -> the self-DOI is now foreign -> no promotion.
    # Extraction is byte-identical; only the comparison to the request changed.
    from dataclasses import replace as _dc_replace
    mutated = _dc_replace(work, doi='10.0000/unrelated.' + domain)
    bad = _salvage(raw, work=mutated, media='html')
    assert not bad.receipts
    assert bad.conflict == ir.IDENTITY_METADATA_CONFLICT
    assert len(ir.extract_field_observations(raw, 'html')) == len(obs)  # extraction unchanged


def test_no_production_module_branches_on_domain_labels():
    """The generality invariant: no domain vocabulary decides anything in the salvage code."""
    src = (Path(F.__file__).parent.parent.parent.parent / 'scripts' / 'identity_receipts.py').read_text()
    for token in ('medicine', 'sepsis', 'tort', 'wage', 'attention', 'law review', 'clinical'):
        assert token not in src.lower(), f'salvage code must not name the subject {token!r}'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. Cohort gate — the recorded-corpus regression (opt-in: needs the full ledger + raw blob store).
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(os.environ.get('POLARIS_RUN_COHORT') != '1',
                    reason='cohort regression needs the full corpus + raw blobs; set POLARIS_RUN_COHORT=1')
def test_cohort_regression():
    import json
    from acquisition import open_ledger
    from provenance_construct import construct
    ledger = open_ledger()
    blobs = BlobStore()
    biblio_p = _ROOT / 'outputs' / 'journal_corpus_content.json'
    biblio = json.loads(biblio_p.read_text()) if biblio_p.exists() else None
    g, _ = construct(ledger, blobs=blobs, bibliography=biblio)

    baseline = [mid for mid, m in g.manifestations.items()
                if m.profile.get('semantic_binding') == UNRESOLVED]
    stats = P.reresolve_unresolved_metadata(g, blobs)

    # ── THE CORPUS-INVARIANT SAFETY PROPERTIES (these must hold at ANY corpus size) ──────────────
    # 1. zero residual unresolved manifestation is admitted under either policy — no fabrication.
    for mid, m in g.manifestations.items():
        if m.profile.get('semantic_binding') == UNRESOLVED:
            assert g.resolve_attribution(mid, P.ANY_VERSION).admitted is False
            assert g.resolve_attribution(mid, P.JOURNAL_ONLY).admitted is False
    # 2. every promotion carries a receipt that revalidates against its raw artifact.
    for mid in stats['promoted_ids']:
        m = g.manifestations[mid]
        assert m.identity_receipts
        raw = blobs.get(m.raw_blob_id)
        ok, errs = ir.revalidate_all(raw, m.identity_receipts, g.works[m.work_id])
        assert ok, errs
    # 3. residual == initial - promotions; no OCR promotion; promotions never exceed the baseline.
    assert stats['residual'] == len(baseline) - stats['promotions']
    assert 0 <= stats['promotions'] <= len(baseline)
    for mid in stats['promoted_ids']:
        for r in g.manifestations[mid].identity_receipts:
            assert r['metadata_container'] in ir.SUPPORTED_CONTAINERS   # never OCR

    # The audit count (~67 against Sol's recorded 155-unresolved snapshot) is a corpus-state
    # OBSERVATION, not a production threshold (Sol global rule 7). It is reported, never asserted as a
    # magic number: the live ledger has since resolved most of that cohort, so the invariants above —
    # not the count — are what the gate enforces.
    print(f'\nCOHORT: initial unresolved={len(baseline)} promotions={stats["promotions"]} '
          f'conflicts={stats["conflicts"]} residual={stats["residual"]} '
          f'no_raw={stats["no_raw_artifact"]}')
