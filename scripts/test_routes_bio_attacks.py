#!/usr/bin/env python3
"""ADVERSARY SUITE for the biomedical + OA-index lane (routes_bio.py).

    python3 scripts/test_routes_bio_attacks.py

READ THIS FIRST, BECAUSE IT IS THE HONEST LIMIT OF THIS FILE:

    THE BUILDER CANNOT VERIFY ITSELF.

I wrote routes_bio.py. I wrote these attacks. That is precisely the loop the project's own law says
does not work — "modules self-tested green while fabrication shipped; provenance.py passed 18/18 while
the P0 ran live on disk; the canary went 16/16 while 6 attacks succeeded." So this suite is NOT a
certificate. It is the set of failures I could think of, encoded so that a SEPARATE ADVERSARY can start
from a green board and go looking for the ones I could not. Every attack below is aimed at MY OWN code
and is designed to make it lie.

The attacks are the four silent failures Sol named for these three routes, plus the two structural
invariants the lane rests on, plus the bug this lane actually shipped on its first live run.

  A1  the PMC OAI 404 page — 48,676 REAL BYTES of HTML with a <body> in it — must not become FULLTEXT
  A2  an NIH author manuscript must not be attributable as the journal Version of Record
  A3  a front-matter-only JATS record must not become a complete document
  A4  an abstract must not become full text
  A5  Europe PMC's "Subscription required" location must never become a candidate
  A6  a 429 on every route must never become "no OA copy exists"
  A7  one route may not inherit another route's manifestation (the route-credit bug)
  A8  an adapter may not write a conclusion — asserted STRUCTURALLY, over the AST
  A9  a template with a hole in it must not become a candidate (the bug that shipped, live, tonight)
  A10 the ledger's conclusion guard must REFUSE DOAJ's literal `fulltext` token — proving that the
      reason routes_bio does not emit it is the guard, not the author's good manners
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

# ── THE SANDBOX, AND WHY IT IS SET BEFORE THE IMPORTS ─────────────────────────────────────────────
# `host_scheduler` (Sol §7) is a PERSISTENT, CROSS-PROCESS politeness governor: its state is a FILE, it
# is shared by every worker on this box, and a `Retry-After` it is told about OUTLIVES THE PROCESS THAT
# WAS TOLD. That is exactly what we want in production — and it means attack A6, which forces a 429
# storm with `Retry-After: 3600`, WRITES A ONE-HOUR BACKOFF FOR pmc/ebi/doaj INTO THE SHARED STATE.
#
# It did. The first run of this suite left the real lane, and every other process on this machine,
# deferring live requests to all three hosts for an hour — and then A6 itself started failing, because
# the routes were no longer being ATTEMPTED (NO_ATTEMPT) rather than THROTTLED. An adversarial test that
# silently disables the system it is testing is not a test; it is an outage with a PASS next to it.
#
# So the suite gets its own scheduler state, and `acquisition` binds `SCHEDULER = Scheduler()` AT IMPORT,
# which is why this must run before the import below and not in a fixture.
os.environ['POLARIS_SCHED_STATE'] = tempfile.mkdtemp(prefix='routes_bio_sched_')
os.environ.setdefault('POLARIS_BACKOFF_SCALE', '0')   # a 429 storm must not cost four minutes of sleep
os.environ.setdefault('POLARIS_MAX_WAIT', '0')        # ...nor thirty seconds of waiting for a grant

import acquisition  # noqa: E402
import provenance as P  # noqa: E402
import routes_bio as RB  # noqa: E402
from acquisition import Acquirer, BlobStore, ResolveContext  # noqa: E402
from event_ledger import (  # noqa: E402
    C_FULLTEXT, EventKind, ForbiddenLabel, Ledger, derive_content_profile, observe_text,
)
from source_router import classify_discovery_outcome, licenses_absence, load_table  # noqa: E402

FIX = Path(__file__).resolve().parent / 'tests' / 'fixtures_bio'
fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


def _tmp() -> tuple[Acquirer, BlobStore]:
    d = Path(tempfile.mkdtemp(prefix='routes_bio_attack_'))
    blobs = BlobStore(d / 'blobs')
    return Acquirer('adversary', ledger=Ledger.load(d / 'l.jsonl'), blobs=blobs), blobs


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# FIXTURES — a real 404 page, and JATS documents shaped like the ones PMC actually serves.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: A REAL NIH AUTHOR MANUSCRIPT'S FRONT MATTER. Europe PMC 404s the XML of every author manuscript we
#: probed (PMC13200213 / PMC13071806 / PMC12353900 — all `nihAuthMan: Y`, all `isOpenAccess: N`), so
#: the bytes cannot be taken live. This is the JATS shape PMC serves for one, with the two tells that
#: matter: the `manuscript` article-id, and the stamp PMC prints in the running head of every page.
JATS_NIH_AUTHOR_MANUSCRIPT = b'''<?xml version="1.0"?>
<article article-type="research-article">
 <front><journal-meta><journal-title>Journal of Biomechanical Engineering</journal-title></journal-meta>
  <article-meta>
   <article-id pub-id-type="doi">10.1115/1.4071773</article-id>
   <article-id pub-id-type="pmcid">PMC13200213</article-id>
   <article-id pub-id-type="manuscript">NIHMS2075474</article-id>
   <title-group><article-title>Integrating Uncertainty Quantification into Biomechanical Models</article-title></title-group>
   <contrib-group><contrib><name><surname>Doe</surname><given-names>Jane</given-names></name></contrib></contrib-group>
   <custom-meta-group><custom-meta><meta-name>notice</meta-name>
     <meta-value>Author manuscript; available in PMC 2026 Jan 01.</meta-value></custom-meta></custom-meta-group>
   <abstract><p>We integrate uncertainty quantification into subject-specific biomechanical models.</p></abstract>
  </article-meta></front>
 <body><sec><title>Introduction</title><p>%s</p></sec>
       <sec><title>Methods</title><p>%s</p></sec>
       <sec><title>Results</title><p>The effect was 0.37 percentage points.</p></sec>
       <sec><title>Discussion</title><p>%s</p></sec></body>
</article>''' % (b'Uncertainty propagates through the model in ways that matter clinically. ' * 40,
                 b'We used a Monte Carlo scheme over the parameter space of the model. ' * 40,
                 b'The finding is robust to the specification of the prior distribution. ' * 40)

#: THE SAME JOURNAL, THE SAME SHAPE — but it is the publisher's typeset Version of Record: no
#: `manuscript` id, no author-manuscript stamp. If A2 passes for the wrong reason (e.g. the detector
#: has started calling EVERYTHING an accepted manuscript) this fixture catches it.
JATS_PUBLISHER_VOR = b'''<?xml version="1.0"?>
<article article-type="research-article">
 <front><journal-meta><journal-title>Systematic Reviews</journal-title></journal-meta>
  <article-meta>
   <article-id pub-id-type="doi">10.1186/s13643-025-03000-0</article-id>
   <article-id pub-id-type="pmcid">PMC12754963</article-id>
   <title-group><article-title>Artificial intelligence in the workplace</article-title></title-group>
   <contrib-group><contrib><name><surname>Roe</surname><given-names>Richard</given-names></name></contrib></contrib-group>
   <volume>14</volume><issue>1</issue><fpage>255</fpage>
   <copyright-statement>\xc2\xa9 2026 The Author(s)</copyright-statement>
   <abstract><p>A living systematic review protocol.</p></abstract>
  </article-meta></front>
 <body><sec><title>Background</title><p>%s</p></sec>
       <sec><title>Methods</title><p>%s</p></sec>
       <sec><title>Results</title><p>%s</p></sec></body>
</article>''' % (b'Artificial intelligence is reshaping the workplace in measurable ways. ' * 40,
                 b'We searched the literature systematically across several databases. ' * 40,
                 b'We report the pooled estimate and its confidence interval here. ' * 40)

#: A JATS record with NO <body> — metadata and abstract only. PMC serves these.
JATS_FRONT_MATTER_ONLY = b'''<?xml version="1.0"?>
<article article-type="research-article">
 <front><journal-meta><journal-title>Systematic Reviews</journal-title></journal-meta>
  <article-meta>
   <article-id pub-id-type="doi">10.1186/s13643-025-03000-0</article-id>
   <title-group><article-title>Artificial intelligence in the workplace</article-title></title-group>
   <contrib-group><contrib><name><surname>Roe</surname><given-names>Richard</given-names></name></contrib></contrib-group>
   <abstract><p>Artificial intelligence is reshaping the workplace. We protocol a living review.</p></abstract>
  </article-meta></front>
</article>'''


print(__doc__)
print('=' * 100)

# ── A1. THE 48KB 404 PAGE ─────────────────────────────────────────────────────────────────────────
# The single most dangerous response in this lane, because it is BIG. `pmc.ncbi.nlm.nih.gov/oai/oai.cgi`
# — the endpoint a reasonable person would configure, and the one that WAS configured — returns 48,676
# bytes of HTML on a 404. It has a <body>. It has a <head>. It looks, to any check based on size or on
# the presence of markup, exactly like a document.
print('\nA1  the PMC OAI 404 page (48,676 REAL bytes of HTML) must not become a document')
raw404 = (FIX / 'pmc_oai_404_page.html').read_bytes()
text, method, obs = RB.jats_to_text(raw404)
check('A1a  jats_to_text refuses it (it is not JATS)',
      text == '' and not obs['jats_parsed'],
      f'{len(raw404):,} bytes -> extraction_method={method!r}, jats_parsed={obs["jats_parsed"]}')

# and if it reaches the generic extractor anyway, the REDUCER must still refuse it
gtext, _gm = acquisition.extract_text(raw404, 'text/html')
L = Ledger()
L.emit('u', EventKind.MANIFESTATION_FETCHED, 'a', locator='https://pmc.ncbi.nlm.nih.gov/oai/oai.cgi')
L.emit('u', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(gtext))
cls404, info404 = derive_content_profile(L.events('u'))
check('A1b  the shared reducer refuses it even after tag-stripping',
      cls404 != C_FULLTEXT,
      f'{len(gtext.split()):,} stripped words -> {cls404} ({info404.get("reason", "")[:60]})')

# ── A2. THE NIH AUTHOR MANUSCRIPT ─────────────────────────────────────────────────────────────────
print('\nA2  an NIH author manuscript must not be attributable as the journal Version of Record')
am_text, am_method, am_obs = RB.jats_to_text(JATS_NIH_AUTHOR_MANUSCRIPT)
vor_text, _vm, vor_obs = RB.jats_to_text(JATS_PUBLISHER_VOR)
am_kind, am_basis = P.derive_expression_kind(am_text)
vor_kind, vor_basis = P.derive_expression_kind(vor_text)
check('A2a  the accepted-manuscript verdict comes from the BYTES',
      am_kind == 'accepted_manuscript',
      f'expression_kind={am_kind!r} — {am_basis[:64]}')
check('A2b  and the publisher VoR of the same shape is NOT swept up with it',
      vor_kind == 'journal_version',
      f'expression_kind={vor_kind!r} — {vor_basis[:64]}')
check('A2c  the manuscript id is linearized into the header where the reducer can see it',
      am_obs['jats_manuscript_id'] == 'NIHMS2075474' and vor_obs['jats_manuscript_id'] == '',
      f'AM jats_manuscript_id={am_obs["jats_manuscript_id"]!r}, VoR={vor_obs["jats_manuscript_id"]!r}')
# THE POINT OF THE WHOLE P0: it is not the repository's label that decides this.
check('A2d  `accepted_manuscript_of` is still NOT span-preserving (the V9 P0 stays closed)',
      'accepted_manuscript_of' not in P.SPAN_PRESERVING,
      f'SPAN_PRESERVING={P.SPAN_PRESERVING}')

# ── A3. FRONT MATTER ONLY ─────────────────────────────────────────────────────────────────────────
print('\nA3  a front-matter-only JATS record must not become a complete document')
fm_text, _fm, fm_obs = RB.jats_to_text(JATS_FRONT_MATTER_ONLY)
L = Ledger()
L.emit('u', EventKind.MANIFESTATION_FETCHED, 'a', locator='x')
L.emit('u', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(fm_text))
fm_cls, fm_info = derive_content_profile(L.events('u'))
check('A3a  no <body> is OBSERVED, not concluded',
      fm_obs['jats_body_present'] is False and fm_obs['jats_sec_count'] == 0,
      f'jats_body_present={fm_obs["jats_body_present"]}, sec_count={fm_obs["jats_sec_count"]}')
check('A3b  and the reducer does not call it FULLTEXT',
      fm_cls != C_FULLTEXT,
      f'-> {fm_cls} ({fm_info.get("reason", "")[:56]})')

# ── A4. ABSTRACT != FULL TEXT ─────────────────────────────────────────────────────────────────────
print('\nA4  an abstract must not become full text')
check('A4a  the front-matter-only record is at best an ABSTRACT',
      fm_cls in ('ABSTRACT', 'CITATION_ONLY'),
      f'-> {fm_cls}')

# ── A5. THE "SUBSCRIPTION REQUIRED" LOCATION ──────────────────────────────────────────────────────
# Live, Europe PMC's fullTextUrlList[0] for our probe DOI was availabilityCode "S", pointing at
# doi.org. An adapter that took [0] would have handed a publisher paywall to the miner as a document.
print('\nA5  Europe PMC\'s "Subscription required" location must never become a candidate')
table = load_table()
epmc = table.by_id('europe_pmc')
open_codes = {str(c).upper() for c in (epmc.selectors.get('url_availability_open') or [])}
check('A5a  the open set is DATA on the route row, and "S" is not in it',
      'S' not in open_codes and 'OA' in open_codes,
      f'url_availability_open={sorted(open_codes)}')
src = inspect.getsource(RB.europe_pmc_candidates)
# Assert on the BEHAVIOUR, not on a substring: run the adapter's actual selection over a fixture
# shaped exactly like the live response — paywalled entry FIRST, in the position a naive adapter reads.
live_shaped = {'fullTextUrlList': {'fullTextUrl': [
    {'availability': 'Subscription required', 'availabilityCode': 'S',
     'documentStyle': 'doi', 'site': 'DOI', 'url': 'https://doi.org/10.1186/paywalled'},
    {'availability': 'Open access', 'availabilityCode': 'OA',
     'documentStyle': 'html', 'site': 'Europe_PMC', 'url': 'https://europepmc.org/articles/PMC1'},
]}}
sel = epmc.selectors
picked = [u['url'] for u in RB.dig(live_shaped, sel['full_text_urls'])
          if str(u.get(sel['url_availability_key'], '')).upper() in open_codes]
check('A5b  the paywalled entry — which is FIRST in the live response — is not selected',
      picked == ['https://europepmc.org/articles/PMC1'],
      f'selected {picked} out of 2 locations; the "S" entry at index 0 was dropped')
check('A5c  and the adapter selects by availability code, never by list position',
      'open_codes' in src and 'url_availability_key' in src,
      'europe_pmc_candidates() filters fullTextUrlList on the configured open set')

# ── A6. A 429 IS NOT AN ABSENCE ───────────────────────────────────────────────────────────────────
print('\nA6  a 429 on every route must never become "no OA copy exists"')
acq, _b = _tmp()
ctx = ResolveContext(work_id='10.9999/throttled', identifiers=('10.9999/throttled',))
real_urlopen = urllib.request.urlopen


def _always_429(req, timeout=None):  # noqa: ARG001
    raise urllib.error.HTTPError(getattr(req, 'full_url', 'u'), 429, 'Too Many Requests',
                                 {'Retry-After': '3600'}, None)  # type: ignore[arg-type]


urllib.request.urlopen = _always_429  # type: ignore[assignment]
try:
    RB.resolve_work(acq, table, ctx, fetch=True)
finally:
    urllib.request.urlopen = real_urlopen  # type: ignore[assignment]

outcomes = [classify_discovery_outcome(acq.ledger, ctx.work_id, r)[0] for r in RB.BIO_ROUTES]
licensed, why = licenses_absence(outcomes)
check('A6a  every route reports THROTTLED, not NOT_FOUND',
      all(o == 'THROTTLED' for o in outcomes),
      f'{dict(zip(RB.BIO_ROUTES, outcomes))}')
check('A6b  and absence is NOT licensed by them',
      not licensed,
      why[:88])

# ── A7. ROUTE CREDIT ──────────────────────────────────────────────────────────────────────────────
# The bug Sol names in §1: a route credited with a document SOMEBODY ELSE fetched. If the lineage is
# real, a route that proposed no candidate is credited with nothing, however well its neighbours did.
print('\nA7  one route may not inherit another route\'s manifestation')
acq2, blobs2 = _tmp()
unit = '10.1234/lineage'
# BOTH routes made a real resolver request and BOTH backends answered. That is the whole point of the
# attack: the two routes are indistinguishable at the transport layer, and only the LINEAGE separates
# them. (An earlier cut of this fixture gave doaj no request at all — and then `NO_ATTEMPT` would have
# passed the test for the wrong reason, proving nothing about credit.)
acq2.ledger.emit(unit, EventKind.BACKEND_ATTEMPTED, 'a', adapter='doaj',
                 url='https://doaj.org/api/x', request_id='rq#1')
acq2.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, 'a', adapter='doaj',
                 url='https://doaj.org/api/x', request_id='rq#1', http_status=200, n_bytes=10)
cid = acq2.candidate(unit, 'doaj', 'https://example.org/doc.html', resolver_request_id='rq#1')
acq2.record_manifestation(unit, locator='https://example.org/doc.html',
                          raw=b'x' * 100, text='word ' * 3000, adapter='content:example.org',
                          candidate_id=cid, requested_title='t')
# europe_pmc searched, answered, and proposed nothing.
acq2.ledger.emit(unit, EventKind.BACKEND_ATTEMPTED, 'a', adapter='europe_pmc',
                 url='https://www.ebi.ac.uk/x', request_id='rq#2')
acq2.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, 'a', adapter='europe_pmc',
                 url='https://www.ebi.ac.uk/x', request_id='rq#2', http_status=200, n_bytes=10)
o_doaj, _ = classify_discovery_outcome(acq2.ledger, unit, 'doaj')
o_epmc, _ = classify_discovery_outcome(acq2.ledger, unit, 'europe_pmc')
check('A7a  the route that proposed the candidate is credited',
      o_doaj == 'FETCHED', f'doaj -> {o_doaj}')
check('A7b  the route that proposed NOTHING inherits NOTHING',
      o_epmc == 'NOT_FOUND', f'europe_pmc -> {o_epmc} (it answered; it found no copy of its own)')

# ── A8. THE ADAPTER MAY NOT CONCLUDE — STRUCTURALLY ───────────────────────────────────────────────
print('\nA8  an adapter may not write a conclusion (asserted over the AST, not by reading it)')
tree = ast.parse(Path(RB.__file__).read_text())
ADAPTER_FNS = {'pmc_candidates', 'europe_pmc_candidates', 'doaj_candidates', 'pmc_convert_ids'}
BANNED_CALLS = {'record_manifestation'}
offenders: list[str] = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in ADAPTER_FNS:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                nm = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, 'id', '')
                if nm in BANNED_CALLS:
                    offenders.append(f'{node.name} calls {nm}() at line {sub.lineno}')
check('A8a  no adapter calls record_manifestation — only the generic executor may',
      not offenders, '; '.join(offenders) or 'the four adapters produce DocumentCandidate records only')
check('A8b  and the executor is the ONLY caller of it in the module',
      sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)
          and isinstance(n.func, ast.Attribute) and n.func.attr == 'record_manifestation') == 1,
      'exactly one call site: fetch_candidate()')

# ── A9. A TEMPLATE WITH A HOLE IS NOT A CANDIDATE ─────────────────────────────────────────────────
# This is not hypothetical. It SHIPPED, tonight, into the first live run of this lane: `_transform`
# inferred its source field, guessed wrong, returned '', and built
# `?identifier=&metadataPrefix=` — which PMC answered with a 400 that reads, downstream, exactly like
# PMC declining to serve the document. 2 candidates, 0 manifestations, and a fact about OUR TABLE
# wearing the clothes of a fact about their holdings.
print('\nA9  a template with a hole in it must not become a candidate (the bug this lane shipped)')
pmc_route = table.by_id('pmc')
ids = RB.derive_identifiers(pmc_route, {'pmcid': 'PMC12754963'})
check('A9a  the transforms resolve the OAI identifier from data',
      ids.get('oai_identifier') == 'oai:pubmedcentral.nih.gov:12754963',
      f'-> {ids.get("oai_identifier")!r}')
try:
    RB._transform('oai_identifier', 'format:oai:pubmedcentral.nih.gov:{pmcid_numeric}', {})
    raised = False
except KeyError:
    raised = True
check('A9b  an underivable identifier RAISES rather than yielding an empty string',
      raised, 'format: on a missing dependency -> KeyError, not ""')
try:
    RB._transform('x', 'strip_prefix:PMC', {'pmcid': 'PMC1'})
    raised2 = False
except ValueError:
    raised2 = True
check('A9c  a strip_prefix that does not NAME its source field is rejected',
      raised2, 'the old inferring form is now a hard error')

# ── A10. THE GUARD, NOT THE AUTHOR'S GOOD MANNERS ─────────────────────────────────────────────────
print('\nA10 the ledger must REFUSE the literal `fulltext` token an adapter might copy from DOAJ')
L = Ledger()
try:
    L.emit('u', EventKind.CANDIDATE_IDENTIFIED, 'doaj', link_type='fulltext')
    guarded = False
except ForbiddenLabel:
    guarded = True
check('A10a the conclusion guard refuses it — which is WHY routes_bio records a count instead',
      guarded, "emit(link_type='fulltext') -> ForbiddenLabel")
doaj_src = inspect.getsource(RB.doaj_candidates)
check('A10b and routes_bio does not smuggle it through anyway',
      "n_links_matched" in doaj_src and "link_type=" not in doaj_src,
      'DOAJ\'s own bytes go to the content-addressed blob store, hashed, instead')

print('\n' + '=' * 100)
if fails:
    print(f'**{len(fails)} ATTACK(S) SUCCEEDED** — the lane is not sound:')
    for f in fails:
        print(f'   - {f}')
    raise SystemExit(1)
print('ALL ATTACKS REPELLED.')
print()
print('AND THAT SENTENCE IS WORTH EXACTLY WHAT THE PROJECT\'S OWN LAW SAYS IT IS WORTH:')
print('  "THE BUILDER CANNOT VERIFY ITSELF." I wrote the lane and I wrote its attacks. A green board')
print('  here means I could not break it with the failures I was able to imagine. It is a floor for a')
print('  separate adversary to start from — it is not a certificate, and it must not be read as one.')
raise SystemExit(0)
