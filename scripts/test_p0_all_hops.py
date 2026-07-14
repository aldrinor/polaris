#!/usr/bin/env python3
"""THE ACCEPTED-MANUSCRIPT P0 — INDEPENDENT VERIFICATION AT EVERY HOP.

    python3 scripts/test_p0_all_hops.py

WHY THIS FILE EXISTS AND WHY IT IS NOT test_v9_lane_attacks.py
==============================================================
The P0 — "a repository's one-word label, three hops later, prints a manuscript's number under a
journal's masthead" — has now been declared closed FOUR TIMES and was open every time:

    hop 1  provenance.SPAN_PRESERVING      patched.  STILL OPEN AT HOP 2.
    hop 2  version_align                   patched.  STILL OPEN AT HOP 3.
    hop 3  alignment_census (the branch)   patched.  STILL OPEN AT HOP 4 — the branch was UNREACHABLE:
                                                     an earlier rung admitted the manuscript first.
    hop 4  alignment_census (the ORDER)    patched.  AND THERE WAS A FIFTH, AND A SIXTH:
    hop 5  event_ledger.derive_eligibility          a repository cover sheet's "citation for the
                                                    published version" was read as the DOCUMENT saying
                                                    it IS the version of record. ADMISSIBLE.
    hop 6  provenance.derive_expression_kind        the cover sheet's DOI matched _JOURNAL_MARK, so an
                                                    accepted manuscript was classified `journal_version`
                                                    and resolve_attribution ADMITTED it — inside the one
                                                    reducer everything else routes through.

Every one of those patches was verified BY THE SUITE OF THE PERSON WHO WROTE THE PATCH, and every one
of those suites was green while the P0 ran live on disk. provenance.py passed 18/18. The canary went
16/16 while six attacks succeeded. So this file is deliberately NOT the builder's suite:

  * it shares NO fixture and NO helper with any other test file;
  * every check DRIVES THE SHIPPING CODE and asserts on the DECISION, never on a constant, a tuple
    membership, a regex, or the shape of an AST — all four of which have been green through a live P0;
  * the anti-starvation checks run on THE REAL BYTES ON DISK, not on a synthetic;
  * and the last check is a TRIPWIRE FOR THE SEVENTH HOP, because there was a fifth and a sixth.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P              # noqa: E402
import alignment_census as AC       # noqa: E402
import event_ledger as EL           # noqa: E402
from event_ledger import EventKind, Ledger   # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail and not ok:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


print('=== THE ACCEPTED-MANUSCRIPT P0: INDEPENDENT VERIFICATION AT ALL SIX HOPS ===\n')

# =================================================================================================
# THE SUBJECT. A White Rose deposit of an accepted manuscript, in the repository's ACTUAL wording.
# Nothing about this document is exotic. It is the single commonest shape in an institutional
# repository, and it defeated four consecutive fixes.
# =================================================================================================
COVER = (
    'This is a repository copy of Robots and Jobs: Evidence from US Labor Markets.\n'
    'This is an author produced version of a paper published in Journal of Political Economy.\n'
    'Citation for the published version: Acemoglu, D. and Restrepo, P. (2020). Robots and Jobs: '
    'Evidence from US Labor Markets. Journal of Political Economy, 128 (6). pp. 2188-2244.\n'
    'DOI: 10.1086/705716\n'
    'This version is available at: http://eprints.whiterose.ac.uk/128744/\n'
    'General rights: Users may download and print one copy for personal study.\n')
BODY = ('We analyse the local labour markets that were most exposed to automation across the United '
        'States, using the variation in robot adoption between industries and a shift-share design. '
        'The estimates imply that the effect on employment is negative and that it is concentrated in '
        'the commuting zones where routine work was most common before the period we study. ' * 40)
# Paginated from 1, as an author's manuscript is; and citing the JPE in its references, as an
# economics paper does. Between them, those two facts were "publisher typeset furniture" to the old test.
AM_TEXT = (COVER + '\x0c1\nRobots and Jobs: Evidence from US Labor Markets\n'
           'Daron Acemoglu and Pascal Restrepo\n' + BODY
           + ''.join(f'\x0c{p}\n' + BODY for p in range(2, 6))
           + '\x0c6\nReferences\n'
             'Autor, D. (2013). The task approach to labor markets. Journal of Political Economy 121.\n'
             'Katz, L. (1999). Changes in the wage structure. Journal of Political Economy 107.\n'
             'Card, D. (2001). Immigrant inflows and the labor market. Journal of Political Economy 109.\n')
AM_WORK = P.Work(id='w:ar', title='Robots and Jobs: Evidence from US Labor Markets',
                 authors=['Acemoglu', 'Restrepo'], year=2020, doi='10.1086/705716',
                 venue='Journal of Political Economy', kind='study')
AM_PROF = P.profile(AM_TEXT, AM_WORK)
AM_TP = AC.typeset_profile(AM_TEXT, 'Journal of Political Economy')

# Fixture sanity — if the subject is not a readable, identified document, every check below is vacuous
# and would pass for the wrong reason. (A test whose fixture is broken is a test that proves nothing;
# the old AER fixture in the adversary suite silently profiled as `extraction_failure`.)
check('FIXTURE SANITY: the manuscript is readable prose, identity CONFIRMED, not a landing page',
      AM_PROF['identity']['verdict'] == 'CONFIRMED'
      and AM_PROF['extractability']['verdict'] != 'CORRUPT'
      and AM_PROF['artifact_kind'] != 'landing_page',
      f"identity={AM_PROF['identity']['verdict']} extract={AM_PROF['extractability']['verdict']} "
      f"kind={AM_PROF['artifact_kind']} — the fixture is broken, so nothing below means anything")
check('FIXTURE SANITY: it carries NO publisher typeset furniture (it is a manuscript, and that is why '
      'it must lose)',
      not AC.is_publisher_typeset(AM_TP),
      f'the fixture LOOKS typeset ({AM_TP}) — it is not the document this test is about')

# =================================================================================================
# HOP 6. THE EXPRESSION CLASSIFIER — inside resolve_attribution, the ONE reducer.
# The cover sheet may CONVICT; it may never ACQUIT.
# =================================================================================================
kind6, basis6 = P.derive_expression_kind(AM_TEXT, 'study')
check('HOP 6: the classifier calls it an ACCEPTED MANUSCRIPT, not a journal_version',
      kind6 == 'accepted_manuscript',
      f'classified {kind6!r} because {basis6!r} — the cover sheet\'s own DOI was read as proof that '
      f'the manuscript IS the article of record')

g = P.Graph(works={'w:ar': AM_WORK})
g.expressions['w:ar:journal_version'] = P.Expression(
    'w:ar:journal_version', 'w:ar', 'journal_version', 'crossref type says journal-article',
    'Acemoglu and Restrepo (2020), Journal of Political Economy')
mid = P.ingest_bytes(g, AM_WORK, AM_TEXT, text_field='fulltext', fetched_by='unpaywall',
                     locator='http://eprints.whiterose.ac.uk/128744/', locator_status='ok',
                     claimed_id='w:ar:journal_version', claimed_kind='journal_version')
att = g.resolve_attribution(mid, P.JOURNAL_ONLY)
check('HOP 6 (END TO END): resolve_attribution(JOURNAL_ONLY) REFUSES the manuscript',
      not att.admitted,
      f'IT ADMITTED IT, and would have printed: {att.text!r}')

# ...and the edge cannot be used to launder it either: assert accepted_manuscript_of ON PURPOSE.
g.edges.append(P.Edge(src=g.manifestations[mid].expression_id, dst='w:ar:journal_version',
                      type='accepted_manuscript_of', status='ASSERTED',
                      basis='asserted by the adversary on byte-level evidence'))
check('HOP 3: an ASSERTED accepted_manuscript_of edge still widens NOTHING onto the journal',
      not g.resolve_attribution(mid, P.JOURNAL_ONLY).admitted,
      'the edge laundered a manuscript into a journal attribution — the P0 at its root')

# =================================================================================================
# HOP 4. THE CENSUS RULING LADDER. Inadmissibility is a PRECONDITION, not a rung.
# =================================================================================================
k4, r4, _w4 = AC.rule(AM_PROF, AM_TP, bid=None, align_ver='acceptedVersion',
                      oa_native=None, preprint=None)
check('HOP 4: the census rules the manuscript INADMISSIBLE (Unpaywall says `acceptedVersion`)',
      (k4, r4) == ('ACCEPTED_MANUSCRIPT', 'INADMISSIBLE'),
      f'ruled {k4}/{r4}')

# THE THING THE OLD AST CHECK COULD NOT SEE: not "does the rule say INADMISSIBLE" but "can ANYTHING
# reach an admitting branch first". Exhaust the reducer's entire input space with every admitting
# signal forced ON simultaneously — which is precisely the state the old ladder admitted from.
viol = []
for lbl, wp, oa, pre, via_bid in itertools.product(
        ('acceptedVersion', 'submittedVersion'), (0, 1), (None, 'oa'), (None, 'pre'), (False, True)):
    tp = dict(running_heads=99, page_top_heads=0, folios=99, declared_range=None,
              folios_in_declared_range=0, wp_series_marks=wp)   # no BYTE proof; everything else maxed
    r = AC.rule(AM_PROF, tp,
                bid={'version': lbl, 'cover': 0.99, 'host': 'x'} if via_bid else None,
                align_ver=None if via_bid else lbl,
                oa_native=re.search('oa', oa) if oa else None,
                preprint=re.search('pre', pre) if pre else None)[1]
    if r == 'ADMISSIBLE':
        viol.append((lbl, 'byte-id' if via_bid else 'unpaywall', wp, oa, pre))
check(f'HOP 4 (ORDERING-INDEPENDENCE): NO input reaches an admitting branch — {2*2*2*2*2} cases, '
      f'both label routes, every admitting signal forced on',
      not viol, f'{len(viol)} combinations still ADMIT: {viol[:4]}')

# =================================================================================================
# HOP 5. THE EVENT LANE. A cover sheet's "citation for the published version" is the library
#        POINTING AWAY FROM ITSELF — it is not the document claiming to be the article of record.
# =================================================================================================
L = Ledger()
L.emit('u', EventKind.MANIFESTATION_FETCHED, 'test', adapter='x', locator='u', blob_id='sha256:b',
       byte_sha256='b', text_blob_id='sha256:t', text_sha256='t',
       requested_title='Robots and Jobs: Evidence from US Labor Markets',
       requested_authors=['Acemoglu', 'Restrepo'], requested_doi='10.1086/705716',
       source_type='journal-article')
L.emit('u', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **EL.observe_text(AM_TEXT))
binding5, _ = EL.derive_semantic_binding(L.events('u'))
elig5, info5 = EL.derive_eligibility(L.events('u'), journal_articles_only=True)
check('HOP 5: the event lane binds the manuscript as VERSION_OF_ACCEPTED, not VERSION_OF_PUBLISHED',
      binding5 == EL.VERSION_ACCEPTED,
      f'bound as {binding5} — a cover sheet phrase was read as the document\'s own testimony')
check('HOP 5 (END TO END): derive_eligibility refuses it as journal evidence (DISCOVERY_LEAD)',
      elig5 == EL.DISCOVERY_LEAD,
      f'ruled {elig5}: {info5.get("reason", "")[:90]}')

# =================================================================================================
# ANTI-STARVATION, ON THE REAL BYTES. The bytes must outrank the label IN BOTH DIRECTIONS.
# Unpaywall labels the LSE deposit of Goos-Manning-Salomons `submittedVersion`. IT IS THE AER ARTICLE.
# If the fix cannot tell that document from the manuscript above, it is not a fix, it is a mute button.
# =================================================================================================
corpus_p = ROOT / 'outputs' / 'journal_corpus_content.json'
if corpus_p.exists():
    corpus = json.loads(corpus_p.read_text())
    aer = next((r for r in corpus if (r.get('doi') or '') == '10.1257/aer.104.8.2509'), None)
    if aer and (aer.get('fulltext') or '').strip():
        ft = aer['fulltext']
        aw = P.Work(id='a', title=aer['title'], authors=aer['authors'], year=aer['year'],
                    venue=aer['venue'], doi=aer['doi'], kind='study')
        aprof = P.profile(ft, aw, aer.get('abstract') or '')
        atp = AC.typeset_profile(ft, aer['venue'])
        aruling = AC.rule(aprof, atp, bid=None, align_ver='submittedVersion',
                          oa_native=None, preprint=None)[1]
        check(f'ANTI-STARVATION (REAL BYTES ON DISK): the LSE/AER article SHIPS even though Unpaywall '
              f'calls it `submittedVersion` — {atp["folios_in_declared_range"]} of its printed folios '
              f'land inside the page range {atp["declared_range"]} its own masthead prints',
              aruling == 'ADMISSIBLE',
              f'ruled {aruling}. A real journal article was refused: the byte proof lost to the label, '
              f'and a gate that never opens is a gate nobody keeps')
        # ...and the escape hatch is THE BYTES, not a soft spot in the veto: remove the typeset proof
        # from the very same document and it must go straight back to INADMISSIBLE.
        blind = dict(atp, folios_in_declared_range=0, page_top_heads=0, folios=0)
        check('...and strip that byte proof from THE SAME DOCUMENT and it is refused again (the escape '
              'is the typeset furniture, not a hole in the veto)',
              AC.rule(aprof, blind, bid=None, align_ver='submittedVersion',
                      oa_native=None, preprint=None)[1] == 'INADMISSIBLE')
    else:
        print('  [skip] the AER row is not in the corpus on disk')

    # AND THE WHOLE CORPUS, AS IT ACTUALLY STANDS: no row may be ADMISSIBLE while an authenticated
    # backend calls it an accepted manuscript and its bytes carry no typeset proof.
    census_p = ROOT / 'outputs' / 'alignment_census.json'
    align_p = ROOT / 'outputs' / 'version_alignment.json'
    if census_p.exists() and align_p.exists():
        census = {r['idx']: r for r in json.loads(census_p.read_text())}
        align = {r['idx']: r for r in json.loads(align_p.read_text())}
        live = []
        for idx, row in census.items():
            lbl = ((align.get(idx) or {}).get('journal_bytes') or {}).get('version')
            if lbl in AC.INADMISSIBLE_VERSION_LABELS and row['ruling'] == 'ADMISSIBLE' \
                    and not AC.is_publisher_typeset(row.get('typeset') or {}):
                live.append((idx, lbl, row.get('venue'), row.get('cards')))
        check(f'LIVE DISK: no row in the shipped census is ADMISSIBLE on a bare inadmissible label '
              f'({len(census)} rows audited)',
              not live, f'{len(live)} live fabrication path(s) ON DISK RIGHT NOW: {live[:3]}')

# =================================================================================================
# THE TRIPWIRE FOR THE SEVENTH HOP.
# The P0 has been found at six hops. It was found at the fifth and sixth AFTER being declared closed
# at the fourth. So the only honest posture is that there is a seventh, in a file that does not exist
# yet. WHICH COMPONENTS MAY READ A VERSION LABEL IS THEREFORE A STATEMENT — the same principle Sol
# applied to inert edges and this fix applied to versions, now applied to the AUDIT ITSELF.
#
# Add a component that reads a version label and this test goes RED until someone writes down what it
# does with it. That is the whole point: the previous five hops were all found by a human reading code,
# and every one of them was invisible to every suite that was green at the time.
# =================================================================================================
DECLARED_VERSION_LABEL_SITES: dict[str, str] = {
    'scripts/version_align.py':
        'MAPS the label to an edge type and writes it into version_alignment.json as an OBSERVATION. '
        'Mints no admissibility. `span_preserving()` only selects the wording of alignment_note.',
    'scripts/alignment_census.py':
        'CONSUMES the label. The ONLY component that turns one into a ruling — and it does so through '
        'rule() -> version_veto(), where inadmissibility is a precondition, not a branch in a ladder.',
    'scripts/provenance.py':
        'Never reads a repository label at all. Derives the expression kind FROM THE BYTES, with the '
        'cover sheet segmented off the acquitting mark. Documents the label only in comments.',
    'scripts/event_ledger.py':
        'Reads version FURNITURE (stamps), never a backend label. NEVER_JOURNAL_EVIDENCE is the veto.',
    'scripts/deep_fetch.py':
        'Records `oa_version` as an OBSERVATION on a candidate. Concludes nothing.',
    'scripts/acquisition.py':
        '`version_hint` on a Candidate — an OBSERVATION ONLY, by the suffix and by the docstring.',
    'scripts/quarantine.py':
        'Routes on the EXPRESSION KIND that provenance derived from bytes, never on a backend label.',
    'scripts/provenance_construct.py':
        'Builds the graph; asserts edges only on byte-level evidence.',
}
LABEL_RE = re.compile(r'acceptedVersion|submittedVersion|publishedVersion')
found = set()
for f in sorted((ROOT / 'scripts').glob('*.py')):
    rel = f'scripts/{f.name}'
    if f.name.startswith(('test_', '_test', 'adv_attack')):
        continue
    try:
        if LABEL_RE.search(f.read_text(errors='ignore')):
            found.add(rel)
    except OSError:
        pass
undeclared = found - set(DECLARED_VERSION_LABEL_SITES)
check('THE SEVENTH HOP: every component that reads a version label is DECLARED (a new one turns this '
      'red until its role is written down and proven)',
      not undeclared,
      f'UNDECLARED components now read a version label: {sorted(undeclared)}. Each is a candidate '
      f'seventh hop. Declare what it does with the label, and prove it cannot mint an attribution.')

print()
if fails:
    print(f'** {len(fails)} FAILURE(S). THE P0 IS OPEN. THE FETCH STAYS BLOCKED. **')
    for f in fails:
        print(f'    - {f}')
    raise SystemExit(1)
print('** THE P0 IS CLOSED AT ALL SIX HOPS — and the real journal article still ships. **')
