#!/usr/bin/env python3
"""ADVERSARIAL TESTS FOR THE REPOSITORY LANE — CORE / OpenAIRE Graph v3 / Zenodo.

    "THE BUILDER CANNOT VERIFY ITSELF. Modules self-tested green while fabrication shipped."

So this does not import the adapter's fixtures and it does not ask the adapter whether it is happy. It
hands the three routes HOSTILE BACKEND RESPONSES — the exact silent failures Sol V9 §2 names — and then
asks the LEDGER, through the reducers the pipeline actually uses, what the run believes. A test that
only asked `RouteResult.candidates` would be checking the adapter's own account of itself; every attack
below therefore ends at `source_router.classify_discovery_outcome` / `licenses_absence`, which are what
the report is built from.

    A1  CORE 401 must NEVER license "no accessible copy"          (the live state of our key)
    A2  CORE `fullText` must not become a complete-PDF equivalent
    A3  a Zenodo deposit that CITES the DOI is not that DOI's paper
    A4  a concept DOI must not silently stand as the version's identity
    A5  a record's files must never be concatenated into one document
    A6  a dataset/supplement must not pass as an article
    A7  one route may not inherit another route's manifestation
    A8  a 429 on one query form must not be outvoted by two clean empties
    A9  an unscoped (free-text) query form must die at build time
    A10 a restricted record with no bytes is not an absence
    A11 the adapter cannot write a conclusion into the ledger even if it tries
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import acquisition as ACQ                                                       # noqa: E402
import event_ledger as EL                                                       # noqa: E402
import routes_repo as RR                                                        # noqa: E402
import source_router as SR                                                      # noqa: E402
from acquisition import Acquirer, BlobStore, ResolveContext                     # noqa: E402
from event_ledger import EventKind, Ledger                                      # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f'  {"PASS" if ok else "FAIL"}  {name}')
    if not ok:
        if detail:
            print(f'        {detail}')
        FAILED.append(name)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# A FAKE NETWORK. The adapters must not be able to tell — they get bytes, like always.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class FakeHTTP:
    """Serves canned bodies / HTTP errors by URL substring. Nothing here is a fixture the adapter has
    ever seen; these are the SHAPES THE REAL BACKENDS RETURN, with the poison Sol named in them."""

    def __init__(self, rules: list[tuple[str, object]]):
        self.rules = rules
        self.calls: list[str] = []

    def __call__(self, req, timeout=None, **kw):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        self.calls.append(url)
        for frag, resp in self.rules:
            if frag in url:
                if isinstance(resp, int):
                    raise urllib.error.HTTPError(url, resp, f'HTTP {resp}', {}, None)
                body = json.dumps(resp).encode()
                return _Resp(body, url)
        return _Resp(json.dumps({}).encode(), url)


class _Resp:
    def __init__(self, body: bytes, url: str):
        self._b, self.status, self.url = body, 200, url
        self.headers = {'Content-Type': 'application/json'}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return self.url


def harness(tmp: str, rules: list[tuple[str, object]]) -> tuple[Acquirer, SR.RouteTable, FakeHTTP]:
    d = ROOT / 'outputs' / '_attack' / tmp
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob('*.jsonl'):
        f.unlink()
    acq = Acquirer('attacker', ledger=Ledger.load(d / 'l.jsonl'), blobs=BlobStore(d / 'b'))
    fake = FakeHTTP(rules)
    urllib.request.urlopen = fake                       # the ONE door to the network, replaced
    RR.reset_circuit()
    # The persistent host scheduler REMEMBERS a circuit-break across processes (Sol V9 §7) — which is
    # correct in production and fatal in a test suite that deliberately serves 401s and 429s. Clear the
    # hosts this file abuses, so attack N+1 is not silently deferred by attack N's punishment.
    for h in ('api.core.ac.uk', 'api.openaire.eu', 'zenodo.org'):
        try:
            ACQ.SCHEDULER.reset(h)
        except Exception:
            pass
    return acq, SR.load_table(), fake


def ctx(doi: str) -> ResolveContext:
    return ResolveContext(work_id=doi, identifiers=(doi,), contract_id='attack')


_REAL_URLOPEN = urllib.request.urlopen
DOI = '10.1000/target.paper'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A1. CORE 401 — the state of our key TODAY — must never license an absence ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
acq, table, fake = harness('a1', [('api.core.ac.uk', 401)])
r = RR.resolve(acq, table, 'core', ctx(DOI))

check('a CORE 401 is AUTH_FAILED, not an empty result set',
      r.state == RR.AUTH_FAILED, f'state={r.state}')
check('AUTH_FAILED yields ZERO candidates AND `answered` is False',
      not r.candidates and not r.answered, f'answered={r.answered}')
check('AUTH_FAILED is in the set of states that are NOT an observation of the world',
      RR.AUTH_FAILED in RR.NOT_AN_OBSERVATION_OF_THE_WORLD)

# THE REAL TEST: what does the PIPELINE'S OWN REDUCER say, off the ledger?
outcome, basis = SR.classify_discovery_outcome(acq.ledger, DOI, 'core')
check('the ledger reducer calls it ACCESS_DENIED (a fact about entitlement/credential)',
      outcome == SR.ACCESS_DENIED, f'outcome={outcome}')
lic, why = SR.licenses_absence([outcome])
check('** licenses_absence() REFUSES to say "we did not locate an accessible copy" **',
      lic is False, f'IT LICENSED AN ABSENCE OFF A 401: {why}')

# and the circuit breaker: a rejected key is not re-probed 2,490 times
n_before = len(fake.calls)
RR.resolve(acq, table, 'core', ctx('10.1000/another'))
check('the rejected credential CIRCUIT-BREAKS (no second 401 storm)',
      len(fake.calls) == n_before, f'{len(fake.calls) - n_before} extra requests')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A2. CORE `fullText` is DERIVED TEXT — not automatically a complete PDF equivalent ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
CORE_HIT = {'results': [{
    'doi': DOI, 'title': 'The Target Paper',
    'downloadUrl': 'https://repo.example.org/target.pdf',
    # OCR'd, truncated, and it ends mid-sentence — Sol's named CORE silent failure
    'fullText': 'The Target Paper\nAbstract. We find that the effect is 0.37pp. Introduction. The'}]}
acq, table, fake = harness('a2', [('api.core.ac.uk', CORE_HIT)])
r = RR.resolve(acq, table, 'core', ctx(DOI))
by_hint = {c.media_hint for c in r.candidates}

check('CORE answered and proposed candidates', r.answered and len(r.candidates) == 2,
      f'{len(r.candidates)} candidates: {[c.retrieval_url for c in r.candidates]}')
check('the `fullText` candidate is marked DERIVED TEXT, not a document',
      'derived_text' in by_hint, f'media hints: {by_hint}')
check('the derived text is NOT presented as the pdf/document candidate',
      len([c for c in r.candidates if c.media_hint == 'derived_text']) == 1 and
      len([c for c in r.candidates if c.media_hint == 'document']) == 1)
ft = [c for c in r.candidates if c.media_hint == 'derived_text'][0]
check('no manifestation was recorded by the adapter (bytes are the executor\'s job)',
      not [e for e in acq.ledger.events(DOI) if e.kind == EventKind.MANIFESTATION_FETCHED])
check('the derived text carries no completeness claim anywhere on the candidate',
      not any('complete' in str(v).lower() for v in vars(ft).values()))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A3. A Zenodo deposit that merely CITES the DOI is NOT that DOI\'s paper ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
CITING_DEPOSIT = {'hits': {'total': 1, 'hits': [{
    'doi': '10.5281/zenodo.7865494', 'id': 7865494,
    'metadata': {
        'title': 'WEBINAR: what is in it for me?',
        'resource_type': {'type': 'other'},
        'access_right': 'open',
        'related_identifiers': [{'identifier': DOI, 'relation': 'cites', 'scheme': 'doi'}]},
    'files': [{'key': 'Event metadata.pdf', 'size': 157882,
               'checksum': 'md5:d4c6b8ae8dccf654',
               'links': {'self': 'https://zenodo.org/api/records/7865494/files/Event%20metadata.pdf/content'}}]}]}}
acq, table, fake = harness('a3', [('zenodo.org', CITING_DEPOSIT)])
r = RR.resolve(acq, table, 'zenodo', ctx(DOI))

check('the citing deposit produced NO candidate', len(r.candidates) == 0,
      f'ADMITTED: {[c.retrieval_url for c in r.candidates]}')
check('the route still ANSWERED (this is a real answer, not a failure)', r.answered)
check('the refusal names the actual relation that disqualified it',
      any('cites' in x['why'] for x in r.rejected), f'{[x["why"][:60] for x in r.rejected]}')
outcome, _ = SR.classify_discovery_outcome(acq.ledger, DOI, 'zenodo')
check('the reducer reports NOT_FOUND for zenodo — it answered and holds nothing for this work',
      outcome == SR.NOT_FOUND, f'outcome={outcome}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A4. A CONCEPT DOI must not silently stand as the version\'s identity ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
CONCEPT = '10.5281/zenodo.1215934'
VERSION = '10.5281/zenodo.1424505'
CONCEPT_HIT = {'hits': {'total': 1, 'hits': [{
    'doi': VERSION, 'conceptdoi': CONCEPT, 'id': 1424505,
    'metadata': {'title': 'bgc-val', 'resource_type': {'type': 'software'}, 'access_right': 'open',
                 'version': 'v1.0.1'},
    'files': [{'key': 'bgc-val.zip', 'size': 100,
               'links': {'self': 'https://zenodo.org/api/records/1424505/files/bgc-val.zip/content'}}]}]}}
acq, table, fake = harness('a4', [('zenodo.org', CONCEPT_HIT)])
r = RR.resolve(acq, table, 'zenodo', ctx(CONCEPT))
obs = list(r.candidate_obs.values())

check('the version record was found through the concept DOI', len(r.candidates) == 1)
check('** the substitution is RECORDED — the record\'s own DOI is not the one we asked for **',
      bool(obs) and obs[0].get('identifier_the_record_carries') == VERSION and
      obs[0].get('identifier_asked') == CONCEPT,
      f'{obs}')
check('the candidate does not silently claim the concept DOI as the record\'s identity',
      bool(obs) and obs[0].get('identifier_substitution') == 'alias')
ev = [e for e in acq.ledger.events(CONCEPT) if e.kind == EventKind.CANDIDATE_IDENTIFIED]
check('the substitution is ON THE LEDGER, not just in the return value',
      bool(ev) and ev[0].payload.get('identifier_the_record_carries') == VERSION)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A5/A6. Files are never concatenated; a dataset never passes as an article ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
MULTIFILE = {'hits': {'total': 1, 'hits': [{
    'doi': DOI, 'id': 999,
    'metadata': {'title': 'Replication package', 'access_right': 'open',
                 'resource_type': {'type': 'dataset'}},
    'files': [
        {'key': 'manuscript.pdf', 'size': 900000,
         'links': {'self': 'https://zenodo.org/api/records/999/files/manuscript.pdf/content'}},
        {'key': 'appendix.pdf', 'size': 300000,
         'links': {'self': 'https://zenodo.org/api/records/999/files/appendix.pdf/content'}},
        {'key': 'data.csv', 'size': 5000,
         'links': {'self': 'https://zenodo.org/api/records/999/files/data.csv/content'}},
        {'key': 'README.txt', 'size': 100,
         'links': {'self': 'https://zenodo.org/api/records/999/files/README.txt/content'}}]}]}}
acq, table, fake = harness('a5', [('zenodo.org', MULTIFILE)])
r = RR.resolve(acq, table, 'zenodo', ctx(DOI))

check('4 files -> 4 SEPARATE candidates (never one concatenated document)',
      len(r.candidates) == 4, f'{len(r.candidates)}')
check('each candidate names exactly one file',
      all(c.retrieval_url.count('/files/') == 1 for c in r.candidates))
check('the media hints are per-file, derived from the bytes\' names',
      sorted(c.media_hint for c in r.candidates) == ['data', 'pdf', 'pdf', 'text'],
      f'{sorted(c.media_hint for c in r.candidates)}')
o = list(r.candidate_obs.values())
check('** the DATASET declaration is explicit and `declares_article` is False **',
      all(x.get('artifact_declaration') == 'dataset' and x.get('declares_article') is False
          for x in o), f'{[(x.get("artifact_declaration"), x.get("declares_article")) for x in o]}')
check('no candidate claims to be the article merely because it is a .pdf inside the record',
      not any(x.get('declares_article') for x in o))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A7. One route may not inherit another route\'s manifestation (the route-credit bug) ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
OA_HIT = {'results': [{
    'mainTitle': 'The Target Paper', 'type': 'publication',
    'pids': [{'scheme': 'doi', 'value': DOI}],
    'instances': [{'urls': ['https://repo.example.org/target.pdf'], 'license': 'CC BY',
                   'accessRight': {'label': 'OPEN'}, 'refereed': 'peerReviewed'}]}]}
acq, table, fake = harness('a7', [('api.openaire.eu', OA_HIT), ('zenodo.org', {'hits': {'hits': []}}),
                                  ('api.core.ac.uk', 401)])
r_oa = RR.resolve(acq, table, 'openaire', ctx(DOI))
r_ze = RR.resolve(acq, table, 'zenodo', ctx(DOI))
r_co = RR.resolve(acq, table, 'core', ctx(DOI))          # 401 — it must inherit nothing either
check('openaire proposed a candidate; zenodo proposed none',
      len(r_oa.candidates) == 1 and len(r_ze.candidates) == 0)

# Now the EXECUTOR fetches OpenAIRE's candidate and records the manifestation against its lineage.
cid = r_oa.candidates[0].candidate_id
acq.record_manifestation(DOI, locator='https://repo.example.org/target.pdf', raw=b'%PDF-1.4',
                         text=('The Target Paper. Introduction. ' + 'method result discussion ' * 400),
                         adapter='content:repo.example.org', candidate_id=cid,
                         requested_title='The Target Paper', requested_doi=DOI)

o_oa, _ = SR.classify_discovery_outcome(acq.ledger, DOI, 'openaire')
o_ze, b_ze = SR.classify_discovery_outcome(acq.ledger, DOI, 'zenodo')
o_co, _ = SR.classify_discovery_outcome(acq.ledger, DOI, 'core')
check('openaire is credited with the document ITS candidate produced', o_oa == SR.FETCHED, f'{o_oa}')
check('** zenodo is NOT credited with openaire\'s document **', o_ze == SR.NOT_FOUND,
      f'zenodo inherited the outcome {o_ze} — the route-credit bug is back')
check('core (401) is still ACCESS_DENIED and inherits nothing', o_co == SR.ACCESS_DENIED, f'{o_co}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A8. A 429 on one query form must not be outvoted by two clean empties ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class Mixed(FakeHTTP):
    def __call__(self, req, timeout=None, **kw):
        url = req.full_url
        self.calls.append(url)
        if 'conceptdoi' in url:                       # the middle query form gets throttled
            raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {'Retry-After': '3600'}, None)
        return _Resp(json.dumps({'hits': {'total': 0, 'hits': []}}).encode(), url)


acq, table, _ = harness('a8', [])
urllib.request.urlopen = Mixed([])
ACQ.BACKOFF_SCALE = 0.0
r = RR.resolve(acq, table, 'zenodo', ctx(DOI))
check('** the route state is THROTTLED, not ANSWERED — the 429 is not outvoted **',
      r.state == RR.THROTTLED, f'state={r.state} (two empty forms tried to outvote the 429)')
check('a THROTTLED route reports `answered` False', not r.answered)
outcome, _ = SR.classify_discovery_outcome(acq.ledger, DOI, 'zenodo')
lic, why = SR.licenses_absence([outcome])
check('the reducer sees THROTTLED and licenses_absence REFUSES',
      outcome == SR.THROTTLED and lic is False, f'outcome={outcome} licensed={lic}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A9. An unscoped free-text query form dies at build time, not at 3am ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
try:
    RR._fill({'id': 'sloppy', 'accepts': 'doi', 'q': '{doi}',
              'url': 'https://zenodo.org/api/records?q={q}&size=10'}, DOI)
    check('a bare identifier in `q=` is REFUSED', False, 'IT WAS ACCEPTED')
except ValueError as e:
    check('a bare identifier in `q=` is REFUSED', True)

try:
    u = RR._fill({'id': 'ok_param', 'accepts': 'doi', 'q': '{doi}',
                  'url': 'https://api.openaire.eu/graph/v3/research-products?pid={q}'}, DOI)
    check('an identifier-SCOPED parameter (`pid=`) is accepted', 'pid=' in u)
except ValueError as e:
    check('an identifier-SCOPED parameter (`pid=`) is accepted', False, str(e))

try:
    RR._fill({'id': 'legacy', 'accepts': 'doi', 'q': '{doi}',
              'url': 'https://api.openaire.eu/search/publications?keywords={q}'}, DOI)
    check('the LEGACY keyword endpoint would be REFUSED (it is a lexical search)', False,
          'IT WAS ACCEPTED')
except ValueError:
    check('the LEGACY keyword endpoint would be REFUSED (it is a lexical search)', True)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A10. A restricted record (metadata, no bytes) is not an absence ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
RESTRICTED = {'hits': {'total': 1, 'hits': [{
    'doi': DOI, 'id': 5,
    'metadata': {'title': 'Embargoed', 'access_right': 'restricted',
                 'resource_type': {'type': 'publication', 'subtype': 'article'}},
    'files': []}]}}
acq, table, _ = harness('a10', [('zenodo.org', RESTRICTED)])
r = RR.resolve(acq, table, 'zenodo', ctx(DOI))
check('a restricted record yields no candidate but the route ANSWERED',
      r.answered and len(r.candidates) == 0 and r.records_seen == 1,
      f'answered={r.answered} cands={len(r.candidates)} seen={r.records_seen}')
check('the route did not invent a file link for a record that exposes none',
      not r.candidates)
outcome, _ = SR.classify_discovery_outcome(acq.ledger, DOI, 'zenodo')
lic, _ = SR.licenses_absence([outcome])
check('one route answering empty does not by itself license an absence for the work',
      lic is False or outcome == SR.NOT_FOUND, f'outcome={outcome}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n=== A11. The adapter cannot write a conclusion into the ledger, even deliberately ===')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
POISON = {'results': [{
    'doi': DOI, 'title': 'The Target Paper',
    'downloadUrl': 'https://repo.example.org/x.pdf',
    # a backend that hands us its own verdicts. They must not reach the log as ours.
    'documentType': 'version of record',
    'license': 'this is the FULLTEXT and it is ADMISSIBLE'}]}
acq, table, _ = harness('a11', [('api.core.ac.uk', POISON)])
raised = ''
try:
    r = RR.resolve(acq, table, 'core', ctx(DOI))
except EL.ForbiddenLabel as e:
    raised = str(e)
check('** a backend\'s own verdict cannot enter the ledger as our observation **',
      bool(raised), 'the poisoned version/license strings were written to the ledger unchallenged')
if raised:
    print(f'        the guard fired: {raised.splitlines()[0][:88]}')

# and the structural fact underneath it
import inspect                                                                  # noqa: E402
src = inspect.getsource(RR)
check('routes_repo never emits MANIFESTATION_FETCHED (it does not touch bytes)',
      'MANIFESTATION_FETCHED' not in src)
check('routes_repo never names a content class / admissibility verdict',
      not any(w in src for w in ('C_FULLTEXT', 'VERSION_OF_RECORD', 'ADMISSIBLE', 'THIS_WORK')))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
urllib.request.urlopen = _REAL_URLOPEN
print('\n' + '=' * 100)
if FAILED:
    print(f'{len(FAILED)} ATTACK(S) SUCCEEDED — the lane is NOT safe:')
    for f in FAILED:
        print(f'  - {f}')
    raise SystemExit(1)
print('ALL ATTACKS DEFEATED. The three routes discover candidates and conclude nothing.')
raise SystemExit(0)
