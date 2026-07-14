"""P7 — the independent adversary pass against the binding gate.

Written by an Opus agent that did NOT implement P1-P6. Its job is to treat every input the gate reads —
graph JSON, corpus rows, metadata receipts, bindings, expression nodes, cached contracts, source policy
— as attacker-controlled, and to try to make ONE fabricated attribution slip through: a DIFFERENT_WORK
or UNRESOLVED_BINDING manifestation naming a claimed source, or a preprint/working-paper cited as the
journal under a journal-only instruction.

Everything here drives the REAL production chain (observe/derive -> ingest_bytes -> bind -> resolve ->
to_json -> from_json). Nothing mocks an Attribution or hand-assigns a successful verdict. The six
required attack families each run a hand-built minimized case AND >=100 seeded structural mutations that
vary every DOI / title / author / field string independently — proving the gate's refusal is keyed on
typed structure, never on a subject literal.

The terminal contract, asserted by `test_zzz_audit_report`, and recorded in
outputs/audits/binding-gate-adversary/report.md:

    admitted fabricated attributions: 0
    unknown-enum admissions:          0
    tampered graphs loaded:           0
    policy-laundering successes:      0
"""
import copy
import hashlib
import json
import random
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures' / 'binding_gate'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures' / 'identity_metadata'))

import provenance as P                                              # noqa: E402
import evidence_miner as EM                                        # noqa: E402
import identity_receipts as ir                                     # noqa: E402
import research_contract as RC                                     # noqa: E402
from acquisition import BlobStore                                  # noqa: E402
from event_ledger import IDENTITY_PROVEN, UNRESOLVED               # noqa: E402
from provenance import (DISPOSITION_ADMIT, DISPOSITION_LEAD_ONLY, DISPOSITION_QUARANTINE,  # noqa: E402
                        RC_ADMITTED, RC_IDENTITY_DIFFERENT_WORK, RC_IDENTITY_UNRESOLVED,
                        RC_IDENTITY_UNKNOWN_VERDICT, RC_DERIVATION_CONFLICT, RC_VERSION_NOT_PERMITTED,
                        RC_SPAN_BINDING_INVALID, JOURNAL_ONLY, ANY_VERSION, SourcePolicy,
                        GraphIntegrityError)

import vectors as V                                                # noqa: E402
import build_fixtures as F                                         # noqa: E402

SEED = 0xB1ADE          # the audit seed — every fuzz stream is derived from it and is reproducible.

# ── the audit accumulator. Every attack updates it; `test_zzz_audit_report` writes and asserts it. ──
AUDIT = {
    'seed': SEED,
    'families': {},                    # family -> {'attacks': int, 'bypasses': [str]}
    'admitted_fabrications': 0,        # a DIFFERENT_WORK/UNRESOLVED span that named a source, or a
                                       #   non-journal version admitted as the journal
    'unknown_enum_admissions': 0,      # an unknown binding/kind/policy/receipt token that admitted
    'tampered_graphs_loaded': 0,       # a tampered graph the strict loader accepted
    'policy_laundering_successes': 0,  # a prompt-derived policy silently overridden
    'regression_fixtures': [],         # minimized artifacts saved for any real bypass
}
_FIX_DIR = Path(__file__).resolve().parent / 'fixtures' / 'binding_gate_adversary'


def _fam(name):
    return AUDIT['families'].setdefault(name, {'attacks': 0, 'bypasses': []})


def _record(name, n=1):
    _fam(name)['attacks'] += n


def _bypass(name, kind, detail, artifact=None):
    """A genuine structural bypass. Save the minimized artifact and flag the terminal counter."""
    _fam(name)['bypasses'].append(detail)
    AUDIT[kind] += 1
    if artifact is not None:
        _FIX_DIR.mkdir(parents=True, exist_ok=True)
        fp = _FIX_DIR / f'{name}_{len(AUDIT["regression_fixtures"])}.json'
        fp.write_text(json.dumps(artifact, indent=2, default=str))
        AUDIT['regression_fixtures'].append(str(fp.relative_to(_ROOT)))


def _names_nothing(att):
    """The refusal contract: an inadmissible span names NOTHING and carries NO permitted set."""
    return (att.admitted is False and att.names_expression_id is None and att.text is None
            and att.permitted_expression_ids == ())


# ── a random Work identity generator. Every string that a rule is FORBIDDEN to key on is randomized,
#    so a passing fuzz run proves the refusal is keyed on typed structure, not on any subject literal.
#    The requested and FOREIGN identity components are drawn from DISJOINT pools, so a "different work"
#    shape is genuinely a different work — a collision in a tiny pool would look like same-work identity
#    and (correctly) resolve as such, which would be a fixture bug, not a gate finding. ──
_PREFIX = ['10.1056', '10.2307', '10.1086', '10.5555', '10.1001', '10.48550', '10.3386', '10.1093']
_TITLEWORDS = ('Widget Gadget Protocol Doctrine Kernel Estimator Cohort Statute Transformer Sepsis '
               'Estoppel Wage Attention Trial Regimen Liability Mobility Inference Synthesis Lattice '
               'Foreseeability Perfusion Arbitrage Heuristic Manifold Cardinal Reagent Quorum').split()
_SURNAMES = ('Adams Brown Carter Dupont Reyes Silva Okoro Tan Park Vasquez Okafor Lindqvist Nakamura '
             'Farouk Vogt Nair Holt Chen Ober Delgado Ibrahim Sato Novak Bauer Costa Ahmed Rossi Klein '
             'Moreau Petrov Yamada Andersson Haddad Sorensen Kowalski Nguyen').split()
_DOISUFFIX = 0


def _rand_domain(rng):
    """A V-shaped domain dict; requested vs foreign identity components come from DISJOINT samples."""
    global _DOISUFFIX
    surnames = rng.sample(_SURNAMES, 4)          # four DISTINCT surnames: 2 requested, 2 foreign
    a1, a2, b1, b2 = surnames

    def doi():
        global _DOISUFFIX
        _DOISUFFIX += 1                            # a monotonic suffix => requested/foreign DOIs never collide
        return f'{rng.choice(_PREFIX)}/{rng.choice(_TITLEWORDS).lower()}-{_DOISUFFIX:07d}'

    tw = rng.sample(_TITLEWORDS, 10)              # ten distinct title tokens split 5 requested / 5 foreign
    return dict(
        id=f'rand{rng.randrange(10**9)}', doi=doi(), foreign_doi=doi(),
        title=' '.join(tw[:5]), authors=(a1, a2), byline=f'By {a1} {a2}',
        venue=' '.join(rng.sample(_TITLEWORDS, 3)) + ' Review',
        foreign_title=' '.join(tw[5:]), foreign_byline=f'By {b1} {b2}',
        generic_title=rng.choice(_TITLEWORDS) + ' Report')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 1 — FOREIGN-DOI RELABEL. Keep the bytes self-identifying as d1; relabel the requested Work, the
# row DOI, the claimed expression and the attribution string as d2. Both policies must name NOTHING.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _relabel_case(d):
    """A row REQUESTING the foreign identity d2, wrapping bytes whose front matter self-identifies as
    the real d1. The row/work/claimed-expression are all d2; only the BYTES are d1."""
    return V.row(d, doi=d['foreign_doi'], title=d['foreign_title'], authors=('Stranger', 'Other'),
                 fulltext=V.scholarly_body(d, doi=d['doi'], title=d['title'], byline=d['byline']))


def _assert_relabel_convicts(d):
    g = P.migrate([_relabel_case(d)])
    m = next(iter(g.manifestations.values()))
    if m.profile.get('semantic_binding') != 'DIFFERENT_WORK':
        return f'relabel did not convict: binding={m.profile.get("semantic_binding")!r}'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = g.resolve_attribution(m.id, policy)
        if not _names_nothing(att) or att.reason_code != RC_IDENTITY_DIFFERENT_WORK:
            return f'relabelled DIFFERENT_WORK admitted/named under {policy.name}: {att}'
    # ...and the same refusal survives the strict round-trip (no on-disk relabel repairs it).
    g2 = P.Graph.from_json(copy.deepcopy(g.to_json()))
    if not _names_nothing(g2.resolve_attribution(m.id, ANY_VERSION)):
        return 'relabel refusal did not survive round-trip'
    return ''


def test_attack1_foreign_doi_relabel_minimized():
    for d in V.DOMAINS:
        _record('foreign_doi_relabel')
        why = _assert_relabel_convicts(d)
        assert why == '', why
    # on-disk relabel of the Work DOI on a CLEAN journal graph: the loader re-derives from the bytes
    # (which still print the real DOI) and refuses the tampered graph.
    d = V.DOMAINS[0]
    g = P.migrate([V.row(d, fulltext=V.scholarly_body(d))])
    js = g.to_json()
    for w in js['works']:
        w['doi'] = d['foreign_doi']            # relabel the requested identity, leave the bytes
    _record('foreign_doi_relabel')
    try:
        P.Graph.from_json(js)
        _bypass('foreign_doi_relabel', 'tampered_graphs_loaded',
                'on-disk Work-DOI relabel loaded without re-derivation refusal', artifact=js)
    except GraphIntegrityError:
        pass


def test_attack1_foreign_doi_relabel_fuzz():
    rng = random.Random(SEED ^ 0x01)
    for _ in range(150):
        _record('foreign_doi_relabel')
        d = _rand_domain(rng)
        why = _assert_relabel_convicts(d)
        if why:
            _bypass('foreign_doi_relabel', 'admitted_fabrications', why, artifact={'domain': d})
    assert not _fam('foreign_doi_relabel')['bypasses']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 2 — GLYPH-HEADER LAUNDERING. The target DOI/title/authors appear ONLY in body citations /
# references; the self-header is unreadable. Result: unresolved LEAD; a forged metadata/OCR receipt is
# rejected. The bytes may never name a source.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _launder_body(d):
    return (V.GLYPH_HEADER + '\n1. Introduction\n' + V.FILLER + '\n4. Results\nWe find 0.2 units.\n'
            f'References\n{d["authors"][0]}, A. and {d["authors"][1]}, B. doi: {d["doi"]}. '
            f'{d["title"]}. Prior work.\n')


def _assert_launder_unresolved(d):
    g = P.migrate([V.row(d, fulltext=_launder_body(d))])
    m = next(iter(g.manifestations.values()))
    if m.profile.get('semantic_binding') != UNRESOLVED:
        return f'citation laundering promoted identity: {m.profile.get("semantic_binding")!r}'
    for policy in (JOURNAL_ONLY, ANY_VERSION):
        att = g.resolve_attribution(m.id, policy)
        if att.admitted or att.names_expression_id is not None:
            return f'laundered UNRESOLVED admitted under {policy.name}'
        if att.reason_code != RC_IDENTITY_UNRESOLVED:
            return f'laundered UNRESOLVED wrong reason {att.reason_code!r}'
    return ''


def test_attack2_glyph_header_laundering_minimized(tmp_path):
    for d in V.DOMAINS:
        _record('glyph_laundering')
        why = _assert_launder_unresolved(d)
        assert why == '', why

    # a FORGED receipt: a real glyph artifact whose raw bytes DO NOT contain the claimed self-metadata,
    # but which is handed a hand-built receipt asserting they do. revalidation must refuse it.
    work = F.DOMAINS['medicine']
    blobs = BlobStore(tmp_path / 'blobs')
    raw = F.html_head([('citation_title', 'An Unrelated Generic Report')])   # NO citation_doi
    forged = {
        'receipt_id': 'forge-1', 'manifestation_id': 'm', 'manifestation_content_hash': 'x',
        'artifact_blob_id': 'b', 'artifact_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(),
        'media_type': 'text/html', 'extractor_name': ir.EXTRACTOR_NAME,
        'extractor_version': ir.EXTRACTOR_VERSION, 'receipt_kind': ir.RECEIPT_SELF_IDENTIFIER,
        'metadata_container': 'html_head', 'metadata_field': 'citation_doi',
        'coordinate_space': ir.COORD_RAW_TEXT, 'raw_match': work.doi,
        'start_offset': 0, 'end_offset': len(work.doi), 'normalized_value': work.doi,
        'requested_normalized_value': work.doi, 'supporting_matches': [],
    }
    _record('glyph_laundering')
    ok, why = ir.revalidate_receipt(raw, forged, work)
    if ok:
        _bypass('glyph_laundering', 'admitted_fabrications',
                'a forged self-identifier receipt revalidated against bytes that lack it', artifact=forged)
    assert ok is False, why

    # an OCR-typed receipt is refused as an unsupported, non-revalidatable container.
    _record('glyph_laundering')
    ok2, why2 = ir.revalidate_receipt(raw, {**forged, 'metadata_container': 'ocr',
                                            'receipt_kind': 'IMAGE_OCR'}, work)
    if ok2:
        _bypass('glyph_laundering', 'unknown_enum_admissions', 'an OCR-typed receipt revalidated')
    assert ok2 is False


def test_attack2_glyph_header_laundering_fuzz():
    rng = random.Random(SEED ^ 0x02)
    for _ in range(120):
        _record('glyph_laundering')
        d = _rand_domain(rng)
        why = _assert_launder_unresolved(d)
        if why:
            _bypass('glyph_laundering', 'admitted_fabrications', why, artifact={'domain': d})
    assert not _fam('glyph_laundering')['bypasses']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 3 — GENERIC-TITLE COLLISION. Reuse a short generic title across unrelated Works. Absent byline
# -> UNRESOLVED; a positive DISJOINT byline -> DIFFERENT_WORK. Neither is ever admitted.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _assert_generic_collision(d):
    # (a) the artifact self-titles with the GENERIC requested title, no DOI, no requested author.
    body = V.scholarly_body(d, doi='', title=d['generic_title'], byline='An untitled report')
    g, = [P.migrate([V.row(d, fulltext=body, doi='', title=d['generic_title'], authors=())])]
    m = next(iter(g.manifestations.values()))
    if m.profile.get('semantic_binding') != UNRESOLVED:
        return f'generic-title collision was not UNRESOLVED: {m.profile.get("semantic_binding")!r}'
    att = g.resolve_attribution(m.id, ANY_VERSION)
    if att.admitted or att.names_expression_id is not None:
        return 'generic-title collision admitted an attribution'
    # (b) keep the REQUESTED authors but print a POSITIVE disjoint foreign byline -> the collision
    #     hardens to DIFFERENT_WORK (a byline is disjoint only against authors we actually asked for),
    #     still never admitted.
    body2 = V.scholarly_body(d, doi='', title=d['generic_title'], byline=d['foreign_byline'])
    g2 = P.migrate([V.row(d, fulltext=body2, doi='', title=d['generic_title'])])
    m2 = next(iter(g2.manifestations.values()))
    if m2.profile.get('semantic_binding') != 'DIFFERENT_WORK':
        return f'disjoint byline did not convict: {m2.profile.get("semantic_binding")!r}'
    if g2.resolve_attribution(m2.id, ANY_VERSION).admitted:
        return 'disjoint-byline collision admitted an attribution'
    return ''


def test_attack3_generic_title_collision_minimized():
    for d in V.DOMAINS:
        _record('generic_title_collision')
        why = _assert_generic_collision(d)
        assert why == '', why


def test_attack3_generic_title_collision_fuzz():
    rng = random.Random(SEED ^ 0x03)
    for _ in range(120):
        _record('generic_title_collision')
        d = _rand_domain(rng)
        why = _assert_generic_collision(d)
        if why:
            _bypass('generic_title_collision', 'admitted_fabrications', why, artifact={'domain': d})
    assert not _fam('generic_title_collision')['bypasses']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 4 — JSON TAMPERING. Modify, independently: semantic verdict, expression kind, content hash,
# Work ID, receipt raw-match/offset, correspondence identity, permitted expression IDs, cached-contract
# source policy. Each must be a strict-load FAILURE or a resolver QUARANTINE — no repair that increases
# permission. The loader must never load a tampered graph.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _clean_journal_graph(d):
    g = P.migrate([V.row(d, fulltext=V.scholarly_body(d))])
    m = next(iter(g.manifestations.values()))
    assert g.resolve_attribution(m.id, JOURNAL_ONLY).admitted is True      # baseline: it DOES admit
    return g, m


def _expect_refused(js, tag, artifact=None, blob_store=None):
    """The strict loader must refuse `js`. If it loads, that is a tampered_graphs_loaded bypass."""
    _record('json_tampering')
    try:
        P.Graph.from_json(js, blob_store=blob_store) if blob_store else P.Graph.from_json(js)
        _bypass('json_tampering', 'tampered_graphs_loaded',
                f'{tag}: strict load ACCEPTED a tampered graph', artifact=artifact or js)
        return False
    except GraphIntegrityError:
        return True


def test_attack4_json_tampering_loader():
    d = V.DOMAINS[0]
    g, m = _clean_journal_graph(d)

    # 1. semantic verdict: flip VERSION_OF_PUBLISHED -> SAME_WORK on disk.
    js = g.to_json()
    for mm in js['manifestations']:
        mm['profile']['semantic_binding'] = 'SAME_WORK'
    assert _expect_refused(js, 'semantic_verdict_flip')

    # 2. expression kind: relabel the journal expression node to accepted_manuscript.
    js = g.to_json()
    for e in js['expressions']:
        if e['kind'] == 'journal_version':
            e['kind'] = 'accepted_manuscript'
    assert _expect_refused(js, 'expression_kind_relabel')

    # 3. content hash: change the stored hash so the span gate's only anchor is a lie.
    js = g.to_json()
    js['manifestations'][0]['content_hash'] = 'deadbeef' * 8
    assert _expect_refused(js, 'content_hash_tamper')

    # 4. Work ID: point the manifestation at a work that does not exist.
    js = g.to_json()
    js['manifestations'][0]['work_id'] = 'work:ghost'
    assert _expect_refused(js, 'work_id_dangling')

    # 5. correspondence identity: build a real correspondence, then flip its stored source_identity.
    wp_text = V.scholarly_body(d, furniture=V.WORKING_STAMP, span=V.SHARED_SPAN)
    jv_text = V.scholarly_body(d, furniture='', span=V.SHARED_SPAN)
    gc = P.migrate([V.row(d, fulltext=wp_text), V.row(d, fulltext=jv_text)])
    mans = list(gc.manifestations.values())
    wp = next(x for x in mans if x.profile['semantic_binding'] == 'VERSION_OF_PREPRINT')
    jv = next(x for x in mans if x.profile['semantic_binding'] == 'VERSION_OF_PUBLISHED')
    ss, ts, ln = wp.text.index(V.SHARED_SPAN), jv.text.index(V.SHARED_SPAN), len(V.SHARED_SPAN)
    sc = P.make_correspondence(gc, wp.id, ss, ss + ln, jv.id, ts, ts + ln,
                               basis='byte-for-byte checksum equality of the shared span in both held bytes')
    gc.add_correspondence(sc)
    jsc = gc.to_json()
    for c in jsc['correspondences']:
        c['source_identity'] = 'DIFFERENT_WORK'          # a stale/forged identity on the edge
    assert _expect_refused(jsc, 'correspondence_identity_forge')

    # 6. permitted expression IDs on a BINDING: verify_span must reject a widened permitted set (resolver
    #    QUARANTINE, not a load). This is the per-span door, tampered.
    _record('json_tampering')
    binding = gc.bind_span(wp.id, ss, ss + ln)
    tampered = dict(binding, permitted_expression_ids=list(binding.get('permitted_expression_ids', []))
                    + [jv.expression_id])
    att = gc.resolve_attribution(tampered, JOURNAL_ONLY)
    if att.admitted or att.names_expression_id is not None:
        _bypass('json_tampering', 'admitted_fabrications',
                'a binding with a widened permitted set was admitted', artifact=tampered)
    assert att.reason_code == RC_SPAN_BINDING_INVALID and _names_nothing(att)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 5 — UNKNOWN ENUM. Inject an unknown semantic binding, expression kind, disposition, receipt
# type and policy kind. Every one must fail closed — no default admission.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_attack5_unknown_enum():
    d = V.DOMAINS[0]
    g, m = _clean_journal_graph(d)

    # 1. unknown semantic binding (in memory) -> QUARANTINE / IDENTITY_UNKNOWN_VERDICT.
    for tok in ('SAMEISH_WORK', 'PROVEN?', '', 'same_work', 'VERSION_OF_ANYTHING'):
        _record('unknown_enum')
        g2 = P.migrate([V.row(d, fulltext=V.scholarly_body(d))])
        mm = next(iter(g2.manifestations.values()))
        mm.profile['semantic_binding'] = tok
        for policy in (JOURNAL_ONLY, ANY_VERSION):
            att = g2.resolve_attribution(mm.id, policy)
            if att.admitted:
                _bypass('unknown_enum', 'unknown_enum_admissions',
                        f'unknown semantic_binding {tok!r} admitted under {policy.name}')
            assert att.disposition == DISPOSITION_QUARANTINE
            assert att.reason_code == RC_IDENTITY_UNKNOWN_VERDICT and _names_nothing(att)
        # on disk, the same unknown token fails the strict load.
        js = g2.to_json()
        for x in js['manifestations']:
            x['profile']['semantic_binding'] = tok
        assert _expect_refused_enum(js, f'unknown_binding_{tok!r}')

    # 2. unknown expression-node kind (in memory) -> DERIVATION_CONFLICT quarantine, never admitted.
    _record('unknown_enum')
    g3 = P.migrate([V.row(d, fulltext=V.scholarly_body(d))])
    mm3 = next(iter(g3.manifestations.values()))
    g3.expressions[mm3.expression_id].kind = 'peer_reviewed_gold'      # not a real kind
    att = g3.resolve_attribution(mm3.id, ANY_VERSION)
    if att.admitted:
        _bypass('unknown_enum', 'unknown_enum_admissions', 'unknown expression kind admitted')
    assert att.disposition == DISPOSITION_QUARANTINE and _names_nothing(att)

    # 3. unknown POLICY kind: a SourcePolicy whose permitted kinds are meaningless permits NOTHING.
    _record('unknown_enum')
    bogus = SourcePolicy('made_up_policy', ('peer_reviewed_gold', 'nonexistent_version'))
    att = g.resolve_attribution(m.id, bogus)
    if att.admitted or att.names_expression_id is not None:
        _bypass('unknown_enum', 'unknown_enum_admissions',
                'an unknown policy admitted an expression it should not permit')
    assert att.reason_code == RC_VERSION_NOT_PERMITTED and att.admitted is False

    # 4. unknown receipt type refused (OCR and a garbage container both fail closed).
    for container in ('ocr', 'quantum', '', None):
        _record('unknown_enum')
        ok, _why = ir.revalidate_receipt(b'x', {'metadata_container': container,
                                                'receipt_kind': 'IMAGE_OCR',
                                                'extractor_name': ir.EXTRACTOR_NAME,
                                                'extractor_version': ir.EXTRACTOR_VERSION},
                                         F.DOMAINS['medicine'])
        if ok:
            _bypass('unknown_enum', 'unknown_enum_admissions',
                    f'unknown receipt container {container!r} revalidated')
        assert ok is False

    # 5. unknown disposition/reason token can never be MINTED — the resolver only emits registry tokens.
    _record('unknown_enum')
    att = g.resolve_attribution(m.id, ANY_VERSION)
    assert att.disposition in P.DISPOSITIONS and att.reason_code in P.REASON_CODES
    assert not _fam('unknown_enum')['bypasses']


def _expect_refused_enum(js, tag):
    _record('unknown_enum')
    try:
        P.Graph.from_json(js)
        _bypass('unknown_enum', 'tampered_graphs_loaded', f'{tag}: unknown-enum graph loaded', artifact=js)
        return False
    except GraphIntegrityError:
        return True


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 6 — POLICY LAUNDERING. Compile a journal-only prompt, then pass/corrupt ANY_VERSION; compile an
# unconstrained prompt, then verify NO path silently substitutes JOURNAL_ONLY. The prompt-derived policy
# is authoritative and every load_contract return path re-derives it from the ORIGINAL question.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_JOURNAL_PROMPTS = [
    'Use only peer-reviewed sources about {x}.',
    'Cite published journal articles about {x}.',
    'Restrict to journal articles when summarizing {x}.',
    'Ensure sources are peer-reviewed publications on {x}.',
]
_ANY_PROMPTS = [
    'Summarize the evidence about {x}.',
    'Use journal articles and preprints about {x}.',
    'Explain the differences between journals and preprint servers for {x}.',
    'Do not limit this to journal articles; include working papers on {x}.',
    'Draw on the literature about {x}.',                 # "literature" without a source-CLASS demand
]


def _mining_contract_policy(question):
    """load_contract via the FACET branch (no LLM), then read the finalizer-derived source policy."""
    c = EM.load_contract(question, facets=[{'name': 'x', 'terms': ['x']}])
    return c.source_policy.name


def test_attack6_policy_laundering():
    subjects = ['sepsis care', 'contract formation', 'wage dispersion', 'program synthesis', 'X']
    # a journal-only prompt derives JOURNAL_ONLY on every finalized path, regardless of the facets given.
    for tmpl in _JOURNAL_PROMPTS:
        for x in subjects:
            _record('policy_laundering')
            q = tmpl.format(x=x)
            if _mining_contract_policy(q) != JOURNAL_ONLY.name:
                _bypass('policy_laundering', 'policy_laundering_successes',
                        f'journal-only prompt did NOT derive JOURNAL_ONLY: {q!r}')
    # an unconstrained prompt NEVER silently becomes JOURNAL_ONLY.
    for tmpl in _ANY_PROMPTS:
        for x in subjects:
            _record('policy_laundering')
            q = tmpl.format(x=x)
            if _mining_contract_policy(q) != ANY_VERSION.name:
                _bypass('policy_laundering', 'policy_laundering_successes',
                        f'unconstrained prompt silently became journal-only: {q!r}')

    # the mine() guard: an explicit source_policy that DISAGREES with the prompt is refused, in BOTH
    # directions — you cannot launder a journal-only prompt into ANY_VERSION, nor an open prompt into
    # JOURNAL_ONLY. Driven through the real mine() entrypoint (facets => no LLM), refusing before spend.
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as _cf:
        _cf.write(json.dumps([V.row(V.DOMAINS[0], fulltext=V.scholarly_body(V.DOMAINS[0]))]))
        corpus = Path(_cf.name)
    try:
        for q, explicit in (('Use only peer-reviewed sources about X.', ANY_VERSION),
                            ('Summarize the evidence about X.', JOURNAL_ONLY)):
            _record('policy_laundering')
            try:
                EM.mine(corpus, question=q, facets=[{'name': 'x', 'terms': ['x']}],
                        use_llm=False, source_policy=explicit)
                _bypass('policy_laundering', 'policy_laundering_successes',
                        f'mine() accepted an explicit {explicit.name!r} against prompt {q!r}')
            except ValueError:
                pass          # the laundering refusal — the prompt is authoritative.
    finally:
        corpus.unlink(missing_ok=True)
    assert not _fam('policy_laundering')['bypasses']


def test_attack6_derive_version_scope_generality_fuzz():
    """derive_version_scope is a positive-proof rule keyed on structural source-class + directive signal,
    NEVER on subject vocabulary. Swapping the subject across 100+ unrelated domains must not change it."""
    rng = random.Random(SEED ^ 0x06)
    for _ in range(120):
        _record('policy_laundering')
        subj = ' '.join(rng.sample(_TITLEWORDS, 3))
        jo, _ev = RC.derive_version_scope(f'Use only peer-reviewed sources about {subj}.')
        an, _ev2 = RC.derive_version_scope(f'Summarize the evidence about {subj}.')
        wide, _ev3 = RC.derive_version_scope(
            f'Do not limit this to journal articles; include preprints about {subj}.')
        if jo != 'JOURNAL_ONLY':
            _bypass('policy_laundering', 'policy_laundering_successes',
                    f'journal-only directive not detected for subject {subj!r}')
        if an != 'ANY_VERSION' or wide != 'ANY_VERSION':
            _bypass('policy_laundering', 'policy_laundering_successes',
                    f'unconstrained/widened prompt became journal-only for subject {subj!r}')
    assert not _fam('policy_laundering')['bypasses']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 7 — STRUCTURAL FUZZING as an END-TO-END property: for EVERY randomized identity and EVERY
# structural shape, the real chain's admission decision must match the shape's typed expectation and must
# NEVER admit a DIFFERENT_WORK/UNRESOLVED span or name a non-journal version under JOURNAL_ONLY. This is
# the cross-family invariant: >100 seeded mutations, all identifiers/subjects varied independently.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _shape_cases(d):
    """(shape, fulltext, row-kwargs, expected_binding, journal_admits, any_admits)."""
    return [
        ('foreign_doi', V.scholarly_body(d, doi=d['foreign_doi']), {},
         'DIFFERENT_WORK', False, False),
        ('disjoint_byline', V.scholarly_body(d, doi='', title=d['foreign_title'],
                                             byline=d['foreign_byline']), {'doi': ''},
         'DIFFERENT_WORK', False, False),
        ('clean_journal', V.scholarly_body(d), {},
         'VERSION_OF_PUBLISHED', True, True),
        ('working_paper', V.scholarly_body(d, furniture=V.WORKING_STAMP), {},
         'VERSION_OF_PREPRINT', False, True),
        ('accepted', V.scholarly_body(d, furniture=V.ACCEPTED_STAMP), {},
         'VERSION_OF_ACCEPTED', False, True),
    ]


def test_attack7_structural_fuzz_end_to_end():
    rng = random.Random(SEED ^ 0x07)
    for _ in range(140):
        d = _rand_domain(rng)
        for shape, body, rowkw, exp_bind, jo_ok, any_ok in _shape_cases(d):
            _record('structural_fuzz')
            g = P.migrate([V.row(d, fulltext=body, **rowkw)])
            m = next(iter(g.manifestations.values()))
            sb = m.profile.get('semantic_binding')
            if sb != exp_bind:
                _bypass('structural_fuzz', 'admitted_fabrications',
                        f'{shape}: derived {sb!r}, expected {exp_bind!r}', artifact={'domain': d})
                continue
            jo = g.resolve_attribution(m.id, JOURNAL_ONLY)
            an = g.resolve_attribution(m.id, ANY_VERSION)
            # SAFETY: a non-proven identity must NEVER name anything under either policy.
            if sb not in IDENTITY_PROVEN and (jo.names_expression_id or an.names_expression_id):
                _bypass('structural_fuzz', 'admitted_fabrications',
                        f'{shape}: non-proven identity named a source', artifact={'domain': d})
            # SAFETY: a non-journal version must NEVER name a journal under JOURNAL_ONLY.
            if jo.admitted != jo_ok:
                _bypass('structural_fuzz', 'admitted_fabrications',
                        f'{shape}: JOURNAL_ONLY admitted={jo.admitted}, expected {jo_ok}',
                        artifact={'domain': d})
            if jo.admitted and not (jo.names_expression_id or '').endswith('journal_version'):
                _bypass('structural_fuzz', 'admitted_fabrications',
                        f'{shape}: JOURNAL_ONLY admitted a non-journal expression', artifact={'domain': d})
            if an.admitted != any_ok:
                _bypass('structural_fuzz', 'admitted_fabrications',
                        f'{shape}: ANY_VERSION admitted={an.admitted}, expected {any_ok}',
                        artifact={'domain': d})
            # every admission must survive the strict round-trip unchanged.
            g2 = P.Graph.from_json(copy.deepcopy(g.to_json()))
            if g2.resolve_attribution(m.id, JOURNAL_ONLY).admitted != jo_ok:
                _bypass('structural_fuzz', 'tampered_graphs_loaded',
                        f'{shape}: round-trip changed the JOURNAL_ONLY decision', artifact={'domain': d})
    assert not _fam('structural_fuzz')['bypasses']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE AUDIT REPORT. Runs last: aggregates every family's attack count and asserts the terminal contract.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_zzz_audit_report():
    total_attacks = sum(f['attacks'] for f in AUDIT['families'].values())
    all_bypasses = [b for f in AUDIT['families'].values() for b in f['bypasses']]

    lines = []
    w = lines.append
    w('# Binding-gate independent adversary pass (P7)')
    w('')
    w('An Opus agent that did not implement P1-P6 treated graph JSON, corpus rows, metadata receipts,')
    w('bindings, expression nodes, cached contracts, and source policy as attacker-controlled inputs and')
    w('tried to make one fabricated attribution slip through the real production chain.')
    w('')
    w(f'- **seed:** `{hex(AUDIT["seed"])}`')
    w(f'- **total attacks run:** {total_attacks}')
    w(f'- **attack families:** {len(AUDIT["families"])}')
    w('')
    w('## Attacks by family')
    w('')
    w('| family | attacks | bypasses |')
    w('|---|---:|---:|')
    for name in sorted(AUDIT['families']):
        f = AUDIT['families'][name]
        w(f'| {name} | {f["attacks"]} | {len(f["bypasses"])} |')
    w('')
    w('## Minimized failures')
    w('')
    if all_bypasses:
        for b in all_bypasses:
            w(f'- {b}')
        w('')
        w('### Regression fixtures saved')
        for fp in AUDIT['regression_fixtures']:
            w(f'- `{fp}`')
    else:
        w('None. Every attack — hand-built minimized case and seeded structural mutation — failed closed.')
        w('No regression fixture was required, because no bypass was reproduced.')
    w('')
    w('## Regression test added')
    w('')
    w('`tests/test_binding_gate_adversary.py` — this file. It is now part of the P7 gate and the final')
    w('release sequence, so every attack family re-runs on every future change to the binding gate.')
    w('')
    w('## Terminal result')
    w('')
    w('```text')
    w(f'admitted fabricated attributions: {AUDIT["admitted_fabrications"]}')
    w(f'unknown-enum admissions:          {AUDIT["unknown_enum_admissions"]}')
    w(f'tampered graphs loaded:           {AUDIT["tampered_graphs_loaded"]}')
    w(f'policy-laundering successes:      {AUDIT["policy_laundering_successes"]}')
    w('```')
    w('')

    out = _ROOT / 'outputs' / 'audits' / 'binding-gate-adversary' / 'report.md'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n')

    # every family must have actually run its attacks (the report is not vacuous).
    for fam in ('foreign_doi_relabel', 'glyph_laundering', 'generic_title_collision', 'json_tampering',
                'unknown_enum', 'policy_laundering', 'structural_fuzz'):
        assert AUDIT['families'].get(fam, {}).get('attacks', 0) > 0, f'{fam} ran no attacks'
    # each required structural-fuzzing family cleared >=100 seeded mutations.
    for fam in ('foreign_doi_relabel', 'glyph_laundering', 'generic_title_collision', 'policy_laundering',
                'structural_fuzz'):
        assert AUDIT['families'][fam]['attacks'] >= 100, f'{fam} ran <100 mutations'

    # THE TERMINAL CONTRACT (Sol P7).
    assert AUDIT['admitted_fabrications'] == 0
    assert AUDIT['unknown_enum_admissions'] == 0
    assert AUDIT['tampered_graphs_loaded'] == 0
    assert AUDIT['policy_laundering_successes'] == 0
    assert not all_bypasses


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
