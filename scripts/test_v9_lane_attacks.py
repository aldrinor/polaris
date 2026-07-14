#!/usr/bin/env python3
"""ADVERSARY — SOL V9. Six attacks on the four boundaries this change claims to have built.

WHY THIS FILE IS SEPARATE FROM THE THING IT TESTS

    "THE BUILDER CANNOT VERIFY ITSELF. Modules self-tested green while fabrication shipped;
     provenance.py passed 18/18 while the P0 ran live on disk; the canary went 16/16 while 6 attacks
     succeeded."

So this does not import the fixtures the implementation was written against, and it does not ask the
implementation whether it is happy. Each check below CONSTRUCTS THE ATTACK — a repository label, a
foreign route's PDF, a peer-reviewed number that moved — and asserts on the OUTCOME.

Every one of these attacks SUCCEEDED against the code as it stood before this change. Four of them are
Sol's own required tests (V9 §9); the route-lineage attack is the bug he found by reading source_router.

    python3 scripts/test_v9_lane_attacks.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P                                                          # noqa: E402
import event_ledger as EL                                                       # noqa: E402
import source_router as SR                                                      # noqa: E402
from event_ledger import EventKind, Ledger                                      # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail and not ok:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


print('=== ADVERSARY: SOL V9 — the accepted-manuscript P0, per-span attribution, route lineage ===\n')

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 1. THE REPOSITORY LABEL. `acceptedVersion` -> a journal finding, in three hops.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Unpaywall says version: "acceptedVersion". version_align mapped that to `accepted_manuscript_of`.
# provenance listed that edge in SPAN_PRESERVING. alignment_census ruled the result ADMISSIBLE. No
# component lied; each passed on what it was handed; and a manuscript's number printed under a journal's
# masthead. THE WHOLE PATH MUST BE DEAD, at every hop, independently.

# ─────────────────────────────────────────────────────────────────────────────────────────────────
# WHY ALL THREE OF THESE WERE REWRITTEN.
#
# The adversary's verdict on the previous versions: one held ONLY BY LUCK and two were "verified only
# via the builder's own suites". All three had the SAME defect, and it is the defect this whole file
# exists to punish — THEY DID NOT DRIVE THE CODE THAT DECIDES.
#
#   HOP 1 walked the AST of alignment_census looking for an `if` on "acceptedVersion" and checked that
#         the branch ASSIGNED 'INADMISSIBLE'. It never asked whether that branch was ever REACHED — and
#         it was not: an earlier rung (`is_publisher_typeset`) admitted the manuscript first. So the
#         test was GREEN THE ENTIRE TIME THE P0 RAN LIVE. Worse, when the P0 was finally fixed by
#         DELETING that `if` (inadmissibility became a precondition, not a rung), the test went RED.
#         It was ANTI-CORRELATED with the truth: green when broken, red when fixed. That is not luck,
#         it is a compass pointing south.
#
#   HOP 2 asserted `not VA.span_preserving('acceptedVersion')`. That function is called in exactly two
#         places in version_align — both of them inside an f-string, choosing the WORDING of
#         `alignment_note`. It gates NOTHING. `rec['alignment']` is set identically either way. The
#         test proved a prose-formatter picks the right sentence.
#
#   HOP 3 asserted `'accepted_manuscript_of' not in P.SPAN_PRESERVING` — reading the builder's own
#         constant. A constant can be correct while every consumer of it is wrong; provenance.py passed
#         18/18 while the P0 it was written to stop ran live on disk.
#
# All three now DRIVE THE DECIDING CODE with real bytes and assert on the DECISION.
# ─────────────────────────────────────────────────────────────────────────────────────────────────
import alignment_census as AC                                                   # noqa: E402

# The White Rose / LSE cover sheet, in its ACTUAL wording, over an author's manuscript. This is the
# document Unpaywall labels `acceptedVersion`, and it is the exact shape that defeated every earlier fix.
_AM_COVER = (
    'This is a repository copy of Robots and Jobs: Evidence from US Labor Markets.\n'
    'This is an author produced version of a paper published in Journal of Political Economy.\n'
    'Citation for the published version: Acemoglu, D. and Restrepo, P. (2020). '
    'Journal of Political Economy, 128 (6). pp. 2188-2244.\nDOI: 10.1086/705716\n'
    'This version is available at: http://eprints.whiterose.ac.uk/128744/\nGeneral rights.\n')
_AM_BODY = ('We analyse local labour markets exposed to automation across US commuting zones, using '
            'variation in robot adoption across industries and a shift-share instrument. ' * 130)
# ...paginated from 1, as a manuscript is, and citing the JPE three times, as an economics paper does.
AM_TEXT = (_AM_COVER + '\x0c1\nRobots and Jobs: Evidence from US Labor Markets\n'
           'Daron Acemoglu and Pascal Restrepo\n' + _AM_BODY
           + ''.join(f'\x0c{p}\n' + _AM_BODY for p in range(2, 6))
           + '\x0c6\nReferences\nAutor, D. (2013). Journal of Political Economy 121(3).\n'
             'Katz, L. (1999). Journal of Political Economy 107(1).\n'
             'Card, D. (2001). Journal of Political Economy 109(2).\n')
AM_WORK = P.Work(id='w', title='Robots and Jobs: Evidence from US Labor Markets',
                 authors=['Acemoglu', 'Restrepo'], year=2020, doi='10.1086/705716',
                 venue='Journal of Political Economy', kind='study')

# ── HOP 1, BY BEHAVIOUR: drive the census's ONE reducer with the bytes and the label. ─────────────
_kind, _ruling, _why = AC.rule(
    P.profile(AM_TEXT, AM_WORK), AC.typeset_profile(AM_TEXT, 'Journal of Political Economy'),
    bid=None, align_ver='acceptedVersion', oa_native=None, preprint=None)
check('HOP 1: the census RULES an accepted manuscript INADMISSIBLE (driven, not read)',
      _ruling == 'INADMISSIBLE' and _kind == 'ACCEPTED_MANUSCRIPT',
      f'the census ruled {_kind}/{_ruling} — a repository version string produced a journal-admissible '
      f'ruling on bytes carrying no publisher typeset furniture')

# ...and the thing the AST check could never see: THE BRANCH IS ACTUALLY REACHED. No admitting branch
# may answer first. Proven by exhausting the reducer's whole input space, below (ORDERING-INDEPENDENCE).

# ── HOP 2, INDEPENDENTLY: version_align's label, fed to the component that CONSUMES it. ───────────
# `span_preserving()` only picks prose, so asserting on it proves nothing. What matters is that the
# record version_align WRITES (`journal_bytes.version`) cannot become a journal attribution in the
# component that READS it. So: take version_align's own mapping, and drive the real consumer with it.
import version_align as VA                                                      # noqa: E402
_edge = VA.JOURNAL_VERSIONS.get('acceptedVersion')
_ruling_from_label = AC.rule(
    P.profile(AM_TEXT, AM_WORK), AC.typeset_profile(AM_TEXT, 'Journal of Political Economy'),
    bid=None, align_ver='acceptedVersion', oa_native=None, preprint=None)[1]
check('HOP 2: the `acceptedVersion` record version_align WRITES cannot be read as journal evidence',
      _edge == 'accepted_manuscript_of' and _ruling_from_label == 'INADMISSIBLE',
      f'version_align maps acceptedVersion -> {_edge!r}, and the consumer ruled {_ruling_from_label}')

# ── HOP 3, INDEPENDENTLY: assert the edge in a REAL graph and ask the REAL policy resolver. ───────
# Not "is the string absent from a tuple" — but "does an ASSERTED accepted_manuscript_of edge, on
# byte-level evidence, widen a manuscript's span onto the journal?" That is the question the P0 asked.
_g3 = P.Graph(works={'w': AM_WORK})
_g3.expressions['w:accepted_manuscript'] = P.Expression(
    'w:accepted_manuscript', 'w', 'accepted_manuscript', 'bytes', 'Acemoglu & Restrepo, accepted ms')
_g3.expressions['w:journal_version'] = P.Expression(
    'w:journal_version', 'w', 'journal_version', 'metadata', 'Acemoglu & Restrepo (2020), JPE')
_m3 = P.ingest_bytes(_g3, AM_WORK, AM_TEXT, text_field='fulltext', fetched_by='unpaywall',
                     locator='http://eprints.whiterose.ac.uk/128744/', locator_status='ok',
                     claimed_id='w:journal_version', claimed_kind='journal_version')
_g3.edges.append(P.Edge(src=_g3.manifestations[_m3].expression_id, dst='w:journal_version',
                        type='accepted_manuscript_of', status='ASSERTED',
                        basis='the adversary asserts it on byte-level evidence'))
_att3 = _g3.resolve_attribution(_m3, P.JOURNAL_ONLY)
check('HOP 3: an ASSERTED accepted_manuscript_of edge NAMES NO JOURNAL (resolver driven, not read)',
      not _att3.admitted,
      f'the resolver ADMITTED it and would print: {_att3.text!r}')

# ── HOP 6: the expression classifier itself. The cover sheet MAY NOT ACQUIT. ──────────────────────
# The manuscript above carries its journal's DOI *on its cover sheet*, and `_JOURNAL_MARK` matches a
# bare DOI string. For as long as the classifier read its marks out of the raw text, that cover sheet
# made an accepted manuscript a `journal_version` — inside resolve_attribution, the one reducer
# everything else routes through.
check('HOP 6: a cover sheet\'s DOI does NOT make a manuscript the journal version',
      _g3.manifestations[_m3].expression_id != 'w:journal_version',
      f'the manuscript was classified {_g3.manifestations[_m3].expression_id!r} — the library\'s '
      f'citation of the article was read as the article')

# ── ORDERING-INDEPENDENCE: the property the AST check pretended to have. ──────────────────────────
# The P0 was never a wrong RULE. It was a right rule that something else answered before. So the claim
# to prove is not "one branch says INADMISSIBLE" but "NO INPUT REACHES AN ADMITTING BRANCH". Exhaust
# the reducer's entire input space and assert the invariant directly.
import itertools                                                                # noqa: E402
_prof_ok = P.profile(AM_TEXT, AM_WORK)
_viol = []
for _lbl, _tsok, _wp, _oa, _pre in itertools.product(
        ('acceptedVersion', 'submittedVersion'), (False,), (0, 1), (None, 'oa'), (None, 'pre')):
    _tp = dict(running_heads=99, page_top_heads=0, folios=99, declared_range=None,
               folios_in_declared_range=0, wp_series_marks=_wp)   # every ADMITTING signal maxed out
    _oam = re.search(r'oa', _oa) if _oa else None
    _prem = re.search(r'pre', _pre) if _pre else None
    _r = AC.rule(_prof_ok, _tp, bid=None, align_ver=_lbl, oa_native=_oam, preprint=_prem)[1]
    if _r == 'ADMISSIBLE':
        _viol.append((_lbl, _wp, _oa, _pre))
    # ...and the same label arriving by the OTHER route (byte-identity), which is a separate source.
    _r2 = AC.rule(_prof_ok, _tp, bid={'version': _lbl, 'cover': 0.99, 'host': 'x'},
                  align_ver=None, oa_native=_oam, preprint=_prem)[1]
    if _r2 == 'ADMISSIBLE':
        _viol.append(('bid:' + _lbl, _wp, _oa, _pre))
check('ORDERING-INDEPENDENCE: NO combination of inputs admits an inadmissible version '
      f'({2 * 2 * 2 * 2 * 2} cases, every admitting signal forced on)',
      not _viol,
      f'{len(_viol)} input combinations still reach an ADMITTING branch: {_viol[:3]}')

# ── ANTI-STARVATION, ON THE REAL BYTES ON DISK. A gate that never opens is a gate nobody keeps. ───
# The LSE deposit of Goos-Manning-Salomons IS the AER article — and UNPAYWALL LABELS THAT FILE
# `submittedVersion`. The bytes must outrank the label in BOTH directions, or this fix is just a
# different way of being wrong. No synthetic fixture here: THE ACTUAL FILE, out of the corpus, with the
# actual wrong label forced on. Its folios (2510..2526) land inside the page range its own masthead
# prints (2509-2526) — an author manuscript paginating from 1 cannot counterfeit that.
_corpus_p = ROOT / 'outputs' / 'journal_corpus_content.json'
if _corpus_p.exists():
    import json as _json                                                        # noqa: E402
    _row = next((r for r in _json.loads(_corpus_p.read_text())
                 if (r.get('doi') or '') == '10.1257/aer.104.8.2509'), None)
    if _row and (_row.get('fulltext') or '').strip():
        _ft = _row['fulltext']
        _aer_w = P.Work(id='a', title=_row['title'], authors=_row['authors'], year=_row['year'],
                        venue=_row['venue'], doi=_row['doi'], kind='study')
        _aer_tp = AC.typeset_profile(_ft, _row['venue'])
        _aer_ruling = AC.rule(P.profile(_ft, _aer_w, _row.get('abstract') or ''), _aer_tp, bid=None,
                              align_ver='submittedVersion', oa_native=None, preprint=None)[1]
        check('ANTI-STARVATION (REAL BYTES): the LSE/AER article still ships though Unpaywall calls it '
              f'`submittedVersion` ({_aer_tp["folios_in_declared_range"]} of its folios land inside the '
              f'page range {_aer_tp["declared_range"]} its own masthead prints)',
              _aer_ruling == 'ADMISSIBLE',
              f'ruled {_aer_ruling}: the byte proof lost to the label. A genuine journal article was '
              f'refused, and a gate that never opens is a gate nobody keeps')
        # ...and the SAME real bytes must NOT be admitted on the strength of the label alone: strip the
        # typeset proof and the very same document becomes inadmissible. This is what proves the escape
        # hatch is the BYTES and not a soft spot in the veto.
        _blind_tp = dict(_aer_tp, folios_in_declared_range=0, page_top_heads=0, folios=0)
        check('...and with its typeset furniture removed, THE SAME BYTES are refused (the escape is the '
              'byte proof, not a hole in the veto)',
              AC.rule(P.profile(_ft, _aer_w, _row.get('abstract') or ''), _blind_tp, bid=None,
                      align_ver='submittedVersion', oa_native=None, preprint=None)[1] == 'INADMISSIBLE')
    else:
        print('  [skip] the AER row is not in the corpus on disk')
else:
    print('  [skip] no corpus on disk')

# ...and end-to-end, in the graph: an ASSERTED accepted_manuscript_of, on BYTE-LEVEL evidence, must
# still transfer nothing at all.
w = P.Work(id='work:ar', title='Robots and Jobs', authors=['Acemoglu', 'Restrepo'], year=2020,
           venue='Journal of Political Economy', doi='10.1086/705716', kind='study')
g = P.Graph(works={'work:ar': w})
g.expressions['work:ar:accepted_manuscript'] = P.Expression(
    'work:ar:accepted_manuscript', 'work:ar', 'accepted_manuscript', 'bytes',
    'Acemoglu and Restrepo (2020), accepted manuscript of Journal of Political Economy')
g.expressions['work:ar:journal_version'] = P.Expression(
    'work:ar:journal_version', 'work:ar', 'journal_version', 'metadata',
    'Acemoglu and Restrepo (2020), Journal of Political Economy')

SURVIVED = 'Industrial robots are fully autonomous reprogrammable machines used in manufacturing.'
AM_NUM = 'one more robot per thousand workers reduces the employment to population ratio by 0.37 percent'
JV_NUM = 'one more robot per thousand workers reduces the employment to population ratio by 0.2 percent'
PAD = 'Accepted manuscript. Robots and Jobs. Acemoglu and Restrepo. ' + (
    'We analyse local labour markets exposed to automation across commuting zones. ' * 140)
JPAD = 'Journal of Political Economy Vol. 128 No. 6. Robots and Jobs. Acemoglu and Restrepo. ' + (
    'We analyse local labour markets exposed to automation across commuting zones. ' * 140)

am_text = PAD + SURVIVED + ' ' + AM_NUM + ' end.'
jv_text = JPAD + SURVIVED + ' ' + JV_NUM + ' end.'


def _mk(mid, eid, text):
    prof = P.profile(text, w)
    g.manifestations[mid] = P.Manifestation(
        mid, eid, 'work:ar', text, hashlib.sha256(text.encode()).hexdigest(),
        len(text.split()), 'https://repo/x', 'RECORDED', 'test', 'fulltext', prof)
    return prof


am_prof = _mk('m:am', 'work:ar:accepted_manuscript', am_text)
jv_prof = _mk('m:jv', 'work:ar:journal_version', jv_text)
check('the AM bytes profile as a COMPLETE accepted manuscript with CONFIRMED identity (fixture sanity)',
      am_prof['complete'] and am_prof['identity']['verdict'] == 'CONFIRMED'
      and jv_prof['complete'] and jv_prof['identity']['verdict'] == 'CONFIRMED',
      f"am={am_prof['artifact_kind']}/{am_prof['identity']['verdict']} "
      f"jv={jv_prof['artifact_kind']}/{jv_prof['identity']['verdict']}")

g.add_edge('work:ar:accepted_manuscript', 'work:ar:journal_version', 'accepted_manuscript_of',
           'ASSERTED', 'sha-256 checksum of the deposited accepted manuscript, byte-for-byte')
check('END TO END: an ASSERTED accepted_manuscript_of on BYTE-LEVEL evidence still names NO journal',
      not g.journal_attributable('m:am')
      and 'work:ar:journal_version' not in g.attribution_targets('m:am'),
      'THE P0 IS ALIVE: a manuscript can be printed as the journal article')

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 2. THE ACEMOGLU MISMATCH. 0.37 in the manuscript, 0.2 in the JPE. It must not align.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
a_n, j_n = am_text.index(AM_NUM), jv_text.index(JV_NUM)
bad = P.make_correspondence(g, 'm:am', a_n, a_n + len(AM_NUM), 'm:jv', j_n, j_n + len(JV_NUM),
                            basis='the same sentence, in both documents')
ok, why = g.verify_correspondence(bad)
check('THE ACEMOGLU MISMATCH: a 0.37-vs-0.2 correspondence FAILS AT THE BYTES',
      not ok and any('NOT equal' in x for x in why),
      'peer review changed the number and the graph aligned them anyway')

try:
    g.add_correspondence(bad)
    admitted = True
except ValueError:
    admitted = False
check('...and it cannot be forced into the graph', not admitted)

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 3. THE SPAN THAT DID SURVIVE — and ONLY it.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
a_s, j_s = am_text.index(SURVIVED), jv_text.index(SURVIVED)
g.add_correspondence(P.make_correspondence(
    g, 'm:am', a_s, a_s + len(SURVIVED), 'm:jv', j_s, j_s + len(SURVIVED),
    basis='exact canonical equality of this span in both HELD documents'))

b_ok = g.bind_span('m:am', a_s, a_s + len(SURVIVED))
b_no = g.bind_span('m:am', a_n, a_n + len(AM_NUM))
check('the surviving span IS journal-attributable (a gate that never opens is a gate nobody keeps)',
      g.resolve_attribution(b_ok, P.JOURNAL_ONLY).names_expression_id == 'work:ar:journal_version')
check('THAT SPAN ONLY: the 0.37 sentence NEXT TO IT in the same manuscript is STILL refused',
      not g.resolve_attribution(b_no, P.JOURNAL_ONLY).admitted,
      'ONE proven span licensed the whole manuscript — permission by association')
check('...and the MANIFESTATION-WIDE question is still NO (a span proof is not a document permit)',
      not g.journal_attributable('m:am'))

# THE REBINDING: the span is in the VoR's own bytes, so bind it there and need no permission.
rb = g.rebind(b_ok, 'm:jv')
check('a span found independently in the VoR bytes REBINDS to the VoR manifestation',
      rb is not None and rb['manifestation_id'] == 'm:jv' and g.verify_span(rb)
      and rb['text'] == SURVIVED)

# THE FORGERY: hand-edit the correspondence to point at the 0.2 sentence and reload from disk.
import json                                                                     # noqa: E402
doc = json.loads(json.dumps(g.to_json()))
doc['correspondences'][0]['target_start'] = j_n
doc['correspondences'][0]['target_end'] = j_n + len(JV_NUM)
try:
    P.Graph.from_json(doc)
    loaded = True
except P.GraphIntegrityError:
    loaded = False
check('a correspondence RE-POINTED at a different sentence is REFUSED BY THE LOADER',
      not loaded, 'the file could grant a permission add_correspondence() would have refused')

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 4. ROUTE LINEAGE. One route cannot inherit another route's manifestation. (Sol V9 §1, §9)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# UNPAYWALL proposes a URL and the PDF is fetched from it. CORE is asked, RESPONDS, and finds nothing.
# The old reducer credited CORE with Unpaywall's document, because it reduced over every manifestation
# of the work rather than over CORE's own candidate lineage.
L = Ledger()
UNIT = '10.1086/705716'
BODY = ('Robots and Jobs. By Daron Acemoglu and Pascual Restrepo. '
        + 'We analyse commuting zones exposed to industrial robot adoption. ' * 200)

# CORE: asked, RESPONDED, proposed NOTHING.
L.emit(UNIT, EventKind.BACKEND_ATTEMPTED, 'test', adapter='core', url='https://core/search',
       request_id='core#1', attempt=1)
L.emit(UNIT, EventKind.RESPONSE_RECEIVED, 'test', adapter='core', url='https://core/search',
       request_id='core#1', attempt=1, http_status=200, n_bytes=17)

# UNPAYWALL: asked, RESPONDED, proposed a candidate, and the candidate produced bytes.
L.emit(UNIT, EventKind.BACKEND_ATTEMPTED, 'test', adapter='unpaywall', url='https://api.unpaywall/x',
       request_id='up#1', attempt=1)
L.emit(UNIT, EventKind.RESPONSE_RECEIVED, 'test', adapter='unpaywall', url='https://api.unpaywall/x',
       request_id='up#1', attempt=1, http_status=200, n_bytes=900)
CID = 'cand:deadbeefdeadbeef'
L.emit(UNIT, EventKind.CANDIDATE_IDENTIFIED, 'test', adapter='unpaywall',
       url='https://repo.example/paper.pdf', candidate_id=CID)
L.emit(UNIT, EventKind.BACKEND_ATTEMPTED, 'test', adapter='content:repo.example',
       url='https://repo.example/paper.pdf', request_id='c#1', candidate_id=CID, attempt=1)
L.emit(UNIT, EventKind.RESPONSE_RECEIVED, 'test', adapter='content:repo.example',
       url='https://repo.example/paper.pdf', request_id='c#1', candidate_id=CID, attempt=1,
       http_status=200, n_bytes=len(BODY))
L.emit(UNIT, EventKind.MANIFESTATION_FETCHED, 'test', adapter='content:repo.example',
       candidate_id=CID, locator='https://repo.example/paper.pdf',
       blob_id='sha256:x', byte_sha256='x', text_blob_id='sha256:y', text_sha256='y',
       requested_title='Robots and Jobs', requested_authors=['Acemoglu'],
       requested_doi=UNIT, source_type='journal-article')
L.emit(UNIT, EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **EL.observe_text(BODY))

up_out, _ = SR.classify_discovery_outcome(L, UNIT, 'unpaywall')
core_out, core_basis = SR.classify_discovery_outcome(L, UNIT, 'core')
check('UNPAYWALL — which proposed the candidate that produced the bytes — is credited with FETCHED',
      up_out == SR.FETCHED, f'got {up_out}')
check('ROUTE LINEAGE: CORE, which proposed NOTHING, is NOT credited with Unpaywall\'s document',
      core_out != SR.FETCHED,
      f'CORE inherited another route\'s manifestation and reads {core_out} — '
      f'unique incremental yield is now identically equal to gross yield, for every route')
check('...and CORE\'s basis says WHY: no candidate of its own produced bytes',
      core_out == SR.NOT_FOUND and 'THIS route' in core_basis, core_basis[:100])

# The content host is a route too: if repo.example had 403'd us, we were blocked BY REPO.EXAMPLE.
host_out, _ = SR.classify_discovery_outcome(L, UNIT, 'content:repo.example')
check('the CONTENT HOST is still credited with the document it actually served',
      host_out == SR.FETCHED, f'got {host_out}')

# ...and absence is not licensed off a route that never had a lineage of its own.
lic, _why = SR.licenses_absence([up_out, core_out])
check('absence is NOT licensed when one route FETCHED — the claim there is PRESENCE',
      not lic)

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 5. WRONG-WORK, BOTH WAYS. Parry/Yang-Hui He stays quarantined; a generic title does NOT
#           convict an innocent document. (Sol V9 §5 — "the current event reducer is too aggressive")
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def _bind(unit: str, text: str, **req) -> str:
    LL = Ledger()
    LL.emit(unit, EventKind.MANIFESTATION_FETCHED, 'test', adapter='x', locator='u',
            blob_id='sha256:b', byte_sha256='b', text_blob_id='sha256:t', text_sha256='t', **req)
    LL.emit(unit, EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **EL.observe_text(text))
    return EL.derive_semantic_binding(LL.events(unit))[0]


maths = ('Mathematics and the Rise of the Machines: Automated Theorem Proving. By Yang-Hui He. '
         + 'We develop a neural approach to formal proof search in algebraic geometry. ' * 60)
check('THE PARRY / YANG-HUI HE CASE IS QUARANTINED (a byline that names a stranger)',
      _bind('p', maths, requested_title='Rise of the Machines', requested_authors=['Parry'],
            requested_doi='10.1177/1059601115613144', source_type='journal-article')
      == EL.DIFFERENT_WORK,
      'a mathematics preprint is about to be printed as the findings of a management journal')

# ...and the SAME generic title, with NO byline to convict on, must NOT be called a stranger's paper.
noby = ('Rise of the Machines. ' + 'This study examines automated decision making in organizations '
        'across a panel of firms observed over two decades. ' * 60)
check('A GENERIC TITLE WITH NO BYLINE IS *NOT* DIFFERENT_WORK (Sol: "too aggressive")',
      _bind('q', noby, requested_title='Rise of the Machines', requested_authors=['Parry'],
            requested_doi='10.1177/1059601115613144', source_type='journal-article')
      == EL.UNRESOLVED,
      'an innocent document was quarantined on the ABSENCE of evidence')

# A LANDING PAGE NAMES NO AUTHOR BECAUSE IT IS NOT A DOCUMENT — not because a stranger wrote it.
banner = 'This website uses cookies. Accept all cookies. Sign in to continue. Privacy policy. ' * 8
check('a COOKIE BANNER is not a stranger\'s paper (an absent byline is not a disjoint one)',
      _bind('r', banner, requested_title='Automation and Wages', requested_authors=['Author'],
            requested_doi='10.1/x', source_type='journal-article') != EL.DIFFERENT_WORK)

# THE POSITIVE FOREIGN DOI — the one signal that convicts on its own.
foreign = ('A Study of Something Else. doi:10.9999/other.2020.1 By Q. Stranger. '
           + 'We examine an unrelated question at length. ' * 60)
check('a FOREIGN DOI printed in the article\'s own front matter IS positive evidence',
      _bind('s', foreign, requested_title='Robots and Jobs', requested_authors=['Acemoglu'],
            requested_doi='10.1086/705716', source_type='journal-article') == EL.DIFFERENT_WORK)

# A REPOSITORY COVER SHEET CITES US — that is the library's opinion, not the document's testimony.
cover = ('This is a repository copy of Robots and Jobs. Citation for the published version: '
         'Acemoglu, D. (2020) Journal of Political Economy. doi:10.1086/705716. '
         'General rights. Users may download and print one copy.\x0c'
         'A Study of Something Else. doi:10.9999/other.2020.1 By Q. Stranger. '
         + 'We examine an unrelated question at length. ' * 60)
check('a repository COVER SHEET is SEGMENTED: the DOI *it* prints does not confirm the paper under it',
      _bind('t', cover, requested_title='Robots and Jobs', requested_authors=['Acemoglu'],
            requested_doi='10.1086/705716', source_type='journal-article') == EL.DIFFERENT_WORK,
      'the cover sheet\'s citation of us was read as the document identifying itself as ours')

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ATTACK 6. THE ADAPTER MAY NOT CONCLUDE. (Sol V9 §1)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
for word in ('FULLTEXT', 'THIS_WORK', 'VERSION_OF_RECORD', 'ADMISSIBLE'):
    LL = Ledger()
    try:
        LL.emit('u', EventKind.CANDIDATE_IDENTIFIED, 'adapter', adapter='core',
                url='https://x/y', note=word.lower().replace('_', ' '))
        wrote = True
    except EL.ForbiddenLabel:
        wrote = False
    check(f'an adapter may NOT write the conclusion {word!r} into the ledger', not wrote,
          f'{word} is a REDUCER output and an adapter just asserted it')

print()
if fails:
    print(f'** {len(fails)} ATTACK(S) SUCCEEDED. THE DOOR IS OPEN. **')
    for f in fails:
        print(f'    - {f}')
    raise SystemExit(1)
print('** ALL ATTACKS REPELLED. **')
