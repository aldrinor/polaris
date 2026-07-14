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

check('HOP 3: accepted_manuscript_of is not span-preserving',
      'accepted_manuscript_of' not in P.SPAN_PRESERVING,
      'the P0 is reopened at its root')

import version_align as VA                                                      # noqa: E402
check('HOP 2: version_align does not treat `acceptedVersion` as span-preserving',
      not VA.span_preserving('acceptedVersion') and VA.span_preserving('publishedVersion'),
      'a repository label still licenses a journal attribution')

# HOP 1 is checked on the AST, NOT on the source text. My first version of this check grepped the
# `acceptedVersion` block for the string "'ADMISSIBLE'" — and it FAILED, because the COMMENT I wrote
# above the fix quotes the old line it replaced. A check that reads prose is defeated by prose; that is
# the same defect as the old `authentication_failure()` regex, committed by the test written to prove it
# gone. So: walk the branch, find what it actually ASSIGNS.
import ast                                                                      # noqa: E402
_tree = ast.parse(Path(ROOT / 'scripts' / 'alignment_census.py').read_text())
_am_rulings: set[str] = set()
for _n in ast.walk(_tree):
    if not isinstance(_n, ast.If):
        continue
    if "acceptedVersion" not in ast.dump(_n.test):
        continue
    for _s in ast.walk(ast.Module(body=_n.body, type_ignores=[])):
        if isinstance(_s, ast.Constant) and _s.value in ('ADMISSIBLE', 'INADMISSIBLE'):
            _am_rulings.add(_s.value)
check('HOP 1: alignment_census does not rule an accepted manuscript ADMISSIBLE from metadata',
      _am_rulings == {'INADMISSIBLE'},
      f'the acceptedVersion branch assigns {_am_rulings or "nothing"} — a repository version string '
      f'still produces a journal-admissible ruling')

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
