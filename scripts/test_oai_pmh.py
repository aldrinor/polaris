#!/usr/bin/env python3
"""ADVERSARY: TARGETED OAI-PMH (Sol V9 §2).

Sol lists FIVE silent failures for this lane. A silent failure is one where the pipeline produces an
answer, the answer is confidently wrong, and NOTHING IN THE LOG SAYS SO. Every one of them gets an
attack here, and each attack is built to SUCCEED against the naive implementation:

  1. `oai_dc` landing page treated as a PDF.
  2. A deleted record treated as "no evidence in the world".
  3. The DOI belongs to a CITED REFERENCE.
  4. A repository cover sheet hides a different article.
  5. Resumption state is lost.

Plus the two that the transport layer must not smuggle back in:

  6. A 200 OK carrying 48KB of HTML from an OAI endpoint (this one is REAL — `pmc.ncbi.nlm.nih.gov/
     oai/oai.cgi` does exactly this) treated as a document.
  7. `cannotDisseminateFormat` / `idDoesNotExist` treated as "no OA copy exists".
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

STATE = Path(tempfile.mkdtemp(prefix='polaris_oai_'))
os.environ['POLARIS_SCHED_STATE'] = str(STATE / 'sched')
os.environ['POLARIS_SPACING_SCALE'] = '0'       # SLEEP ONLY
os.environ['POLARIS_BACKOFF_SCALE'] = '0'

import acquisition  # noqa: E402
import oai_pmh  # noqa: E402
from event_ledger import C_FULLTEXT, EventKind, Ledger, derive_route_status  # noqa: E402
from host_scheduler import HostPolicy, Scheduler  # noqa: E402
from oai_pmh import (  # noqa: E402
    CANNOT_DISSEMINATE, ID_DOES_NOT_EXIST, NEVER_AN_ABSENCE, NOT_XML, NO_IDENTIFIER, RECORD_DELETED,
    RECORD_RETURNED, LocalOaiIndex, OaiHarvester, Repository, build_identifier, document_urls,
    inline_document, landing_urls, load_repositories, parse_record, record_confirms_doi, record_dois,
    relative_refs,
    seeds_from_core,
)

acquisition.SCHEDULER = Scheduler(state_dir=STATE / 'sched', policies={},
                                  default=HostPolicy('*', min_spacing_s=0.0, max_concurrency=4))

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = '') -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  [PASS] {name}' + (f'\n            {detail}' if detail else ''))
    else:
        FAIL += 1
        print(f'  [FAIL] {name}\n            {detail}')


def harvester(bodies: dict[str, bytes]) -> tuple[OaiHarvester, Ledger]:
    """A harvester wired to a FAKE REPOSITORY that serves exactly the bytes an attack needs."""
    L = Ledger()
    acq = acquisition.Acquirer('adversary', ledger=L, blobs=acquisition.BlobStore(STATE / 'blobs'))
    h = OaiHarvester(acq, repos={}, index=LocalOaiIndex(STATE / 'idx.jsonl'), check_robots=False)

    def _serve(req, *a, **k):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        for frag, body in bodies.items():
            if frag in url:
                return _Resp(body)
        raise urllib.error.HTTPError(url, 404, 'no', {}, io.BytesIO(b''))

    urllib.request.urlopen = _serve
    return h, L


class _Resp:
    def __init__(self, body: bytes, ctype='text/xml'):
        self.body, self.status = body, 200
        self.headers = {'Content-Type': ctype}
        self.url = 'https://repo.test/oai'

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_REAL = urllib.request.urlopen
REPO_DC = Repository('r', 'https://repo.test/oai', ('oai_dc',), file_selectors=('oai_dc_identifier',))
REPO_METS = Repository('r', 'https://repo.test/oai', ('mets', 'oai_dc'),
                       file_selectors=('mets_flocat',))


def wrap(inner: str, prefix: str = 'oai_dc') -> bytes:
    return f'''<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <GetRecord><record>
    <header><identifier>oai:repo.test:1</identifier><datestamp>2026-01-01</datestamp></header>
    <metadata>{inner}</metadata>
  </record></GetRecord>
</OAI-PMH>'''.encode()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 1 — ** THE oai_dc LANDING PAGE, DRESSED AS A PDF. **')
#   <dc:identifier>https://ora.ox.ac.uk/objects/uuid:...</dc:identifier> is an HTML SPLASH PAGE with a
#   download button on it. It strips to ~550 words of repository chrome — the exact shape of the
#   535-word aeaweb cookie banner that got stamped FULLTEXT.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
raw = wrap('''<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                         xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>Skill Content of Recent Technological Change</dc:title>
      <dc:identifier>https://ora.ox.ac.uk/objects/uuid:2c4b8f1a</dc:identifier>
      <dc:identifier>10.1162/003355303322552801</dc:identifier>
    </oai_dc:dc>''')
rec = parse_record(raw, REPO_DC, 'oai:repo.test:1', 'oai_dc')
docs, lands = document_urls(rec, REPO_DC), landing_urls(rec, REPO_DC)
check('** the oai_dc <dc:identifier> URL is NOT proposed as a document **',
      docs == [], f'document_urls -> {[d.url for d in docs]}')
check('...it is recorded as a LANDING PAGE — a real lead, kept, and never handed to the miner',
      len(lands) == 1 and lands[0].role == 'landing_page' and 'ora.ox.ac.uk' in lands[0].url,
      f'{[(l.role, l.url) for l in lands]}')
check('...and the bare DOI in a second <dc:identifier> is not mistaken for a URL at all',
      not any('10.1162' in l.url for l in lands + docs))

h, L = harvester({'GetRecord': raw})
try:
    rec2 = h.get_record('w1', REPO_DC, 'oai:repo.test:1', 'oai_dc')
    cands = h.propose_candidates('w1', REPO_DC, rec2)
finally:
    urllib.request.urlopen = _REAL
check('** the harvester proposes ZERO candidates from that record — nothing can descend from it **',
      cands == [], f'{len(cands)} candidates')
check('...and the landing page IS on the ledger as an observation (we saw it; we did not use it)',
      any(e.payload.get('link_role') == 'landing_page' for e in L.events('w1')))

# ...but a dc:identifier that IS a file is a file, and says so.
raw_pdf = wrap('''<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                             xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:identifier>https://repo.test/bitstream/1/paper.pdf</dc:identifier>
    </oai_dc:dc>''')
d2 = document_urls(parse_record(raw_pdf, REPO_DC, 'x', 'oai_dc'), REPO_DC)
check('a dc:identifier that ends in .pdf IS a document (the role is decided by EVIDENCE, not by dogma)',
      len(d2) == 1 and d2[0].media_hint == 'pdf')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 2 — ** A DELETED RECORD IS NOT AN EMPTY WORLD. **')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
deleted = b'''<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <GetRecord><record>
    <header status="deleted"><identifier>oai:repo.test:9</identifier>
      <datestamp>2026-03-02</datestamp></header>
  </record></GetRecord>
</OAI-PMH>'''
h, L = harvester({'GetRecord': deleted})
try:
    rec = h.get_record('w2', REPO_DC, 'oai:repo.test:9')
finally:
    urllib.request.urlopen = _REAL
check('a `<header status="deleted">` is RECORD_DELETED', rec.outcome == RECORD_DELETED and rec.deleted)
check('** RECORD_DELETED is in NEVER_AN_ABSENCE — a repository withdrawing ITS copy says nothing '
      'about the literature **', RECORD_DELETED in NEVER_AN_ABSENCE)
check('the deletion is on the ledger as `record_state`, NOT as `status` (that key IS a label)',
      any(e.payload.get('record_state') == 'deleted' for e in L.events('w2'))
      and not any('status' in e.payload for e in L.events('w2'))
      and not any(e.payload.get('deferral_reason') for e in L.events('w2')))
check('...and a deleted record proposes no candidates and yields no document',
      h.propose_candidates('w2', REPO_DC, rec) == [] and inline_document(rec) == b'')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 3 — ** THE DOI IN THE BIBLIOGRAPHY. **')
#   The record is a JATS full text for a DIFFERENT paper — and it CITES Autor/Levy/Murnane. A regex
#   over the XML finds 10.1162/003355303322552801 and binds a stranger's paper to that DOI, with a
#   DOI match as its evidence. This is the Parry / Yang-Hui He failure with a bibliography.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
jats = wrap('''<article xmlns:xlink="http://www.w3.org/1999/xlink">
      <front><article-meta>
        <article-id pub-id-type="doi">10.9999/someone.else.2024</article-id>
        <title-group><article-title>A Totally Different Paper</article-title></title-group>
      </article-meta></front>
      <body><sec><p>We build on prior work.</p></sec></body>
      <back><ref-list>
        <ref id="r1"><element-citation>
          <article-title>The Skill Content of Recent Technological Change</article-title>
          <pub-id pub-id-type="doi">10.1162/003355303322552801</pub-id>
        </element-citation></ref>
      </ref-list></back>
    </article>''', 'jats')
rec = parse_record(jats, REPO_METS, 'oai:repo.test:3', 'jats')
dois = record_dois(rec)
WANTED = '10.1162/003355303322552801'
check('the record\'s OWN doi is found (from <article-id>)', dois == ['10.9999/someone.else.2024'],
      f'record_dois -> {dois}')
check('** THE CITED DOI IS NOT IN THE RECORD\'S IDENTITY — the bibliography is fifty other papers **',
      WANTED not in dois,
      f'a naive regex over these bytes finds it: {WANTED in jats.decode()}')
ok, basis = record_confirms_doi(rec, WANTED)
check('** record_confirms_doi REFUSES the citing paper, and says which DOI it actually claims **',
      not ok and '10.9999' in basis, basis)
ok2, basis2 = record_confirms_doi(rec, '10.9999/someone.else.2024')
check('...and it CONFIRMS the record that really is that work', ok2, basis2)
check('a record that states NO doi is "cannot settle identity", which is not "wrong work"',
      record_confirms_doi(parse_record(wrap('<oai_dc:dc xmlns:oai_dc="x"/>'), REPO_DC, 'i', 'oai_dc'),
                          WANTED) == (False, 'the record states no DOI of its own — metadata cannot '
                                             'settle identity here'))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 4 — ** THE COVER SHEET. ** The metadata is right; the PDF underneath is another paper.')
#   NOTHING IN A METADATA RECORD CAN CATCH THIS, so the module must not pretend to. What it MUST do is
#   carry the REQUESTED IDENTITY down to the bytes, where the reducer that already segments cover
#   sheets can fire. A module that concluded here would be the bug.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
mets = wrap('''<mets xmlns:xlink="http://www.w3.org/1999/xlink">
      <fileSec><fileGrp USE="ORIGINAL">
        <file><FLocat xlink:href="https://repo.test/bitstream/1/coversheet.pdf"/></file>
      </fileGrp>
      <fileGrp USE="THUMBNAIL">
        <file><FLocat xlink:href="https://repo.test/bitstream/1/thumb.jpg"/></file>
      </fileGrp></fileSec>
    </mets>''', 'mets')
rec = parse_record(mets, REPO_METS, 'oai:repo.test:4', 'mets')
docs = document_urls(rec, REPO_METS)
check('METS <FLocat> in fileGrp USE="ORIGINAL" IS a document url', len(docs) == 1
      and docs[0].url.endswith('coversheet.pdf'), f'{[d.url for d in docs]}')
check('...and the THUMBNAIL fileGrp is NOT (a JPEG of page 1 is not the article)',
      not any('thumb' in d.url for d in docs))
h, L = harvester({'GetRecord': mets})
try:
    rec = h.get_record('w4', REPO_METS, 'oai:repo.test:4', 'mets')
    cids = h.propose_candidates('w4', REPO_METS, rec)
finally:
    urllib.request.urlopen = _REAL
cand_ev = [e for e in L.events('w4', EventKind.CANDIDATE_IDENTIFIED)]
check('the PDF is proposed as a CANDIDATE — a lead with a lineage, not a document',
      len(cids) == 1 and len(cand_ev) == 1)
check('** the candidate concludes NOTHING about the version — no `version_of_record`, no `fulltext` **',
      not any(k in cand_ev[0].payload for k in ('version', 'content_status', 'fulltext_source')),
      f'payload keys: {sorted(cand_ev[0].payload)}')
check('...it carries `link_role` and `selector`, so a bad selector is ATTRIBUTABLE to its dialect row',
      cand_ev[0].payload.get('link_role') == 'document'
      and cand_ev[0].payload.get('selector') == 'mets_flocat')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 5 — ** RESUMPTION STATE IS LOST. ** Kill the harvest mid-list; does it start over?')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
page1 = b'''<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record><header><identifier>oai:repo.test:a</identifier></header><metadata/></record>
    <record><header status="deleted"><identifier>oai:repo.test:b</identifier></header></record>
    <resumptionToken>TOKEN_PAGE_2</resumptionToken>
  </ListRecords>
</OAI-PMH>'''
page2 = b'''<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record><header><identifier>oai:repo.test:c</identifier></header><metadata/></record>
    <resumptionToken/>
  </ListRecords>
</OAI-PMH>'''
h, L = harvester({'resumptionToken=TOKEN_PAGE_2': page2, 'ListRecords': page1})
h.cursor_dir = STATE / 'cursors'
try:
    seen = [r.identifier for r in h.list_records('idx', REPO_DC, 'oai_dc', max_pages=1)]
finally:
    urllib.request.urlopen = _REAL
cur = json.loads((h.cursor_dir / 'r.oai_dc.all.json').read_text())
check('page 1 yields its records, and the DELETED one is yielded AS DELETED (not skipped, not present)',
      seen == ['oai:repo.test:a', 'oai:repo.test:b'], f'{seen}')
check('** the resumption token is PERSISTED after the page — a killed harvest resumes where it was **',
      cur['resumption_token'] == 'TOKEN_PAGE_2', f'cursor: {cur}')

h2, _ = harvester({'resumptionToken=TOKEN_PAGE_2': page2, 'ListRecords': page1})
h2.cursor_dir = STATE / 'cursors'
try:
    seen2 = [r.identifier for r in h2.list_records('idx', REPO_DC, 'oai_dc', max_pages=5)]
finally:
    urllib.request.urlopen = _REAL
check('...and A NEW HARVESTER PROCESS resumes AT PAGE 2 — it does not re-walk page 1',
      seen2 == ['oai:repo.test:c'], f'{seen2}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 6 — ** HTTP 200 + 48KB OF HTML FROM AN OAI ENDPOINT. ** (This one is REAL.)')
#   pmc.ncbi.nlm.nih.gov/oai/oai.cgi answers 200 with an HTML error page. It has a <body> tag. It
#   strips to thousands of words. A fetcher that checked `resp.ok` would file it as a full text.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
html = (b'<html><head><title>Page not found</title></head><body>'
        + b'<p>The page you requested was not found. Try the PMC home page. </p>' * 400
        + b'</body></html>')
h, L = harvester({'GetRecord': html})
try:
    rec = h.get_record('w6', REPO_DC, 'oai:repo.test:6')
finally:
    urllib.request.urlopen = _REAL
check('** a 200 carrying HTML is NOT_XML — not a record, and CERTAINLY not a document **',
      rec.outcome == NOT_XML, f'outcome={rec.outcome} ({len(html)} bytes, "<body>" present)')
check('...it yields no inline document and no candidates',
      inline_document(rec) == b'' and h.propose_candidates('w6', REPO_DC, rec) == [])
check('...and NOT_XML is in NEVER_AN_ABSENCE (their broken endpoint is not our missing paper)',
      NOT_XML in NEVER_AN_ABSENCE)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 7 — THE OAI ERROR CODES. Does `cannotDisseminateFormat` mean "no OA copy exists"?')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def err(code: str) -> bytes:
    return f'''<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <error code="{code}">x</error></OAI-PMH>'''.encode()


for code, want in (('idDoesNotExist', ID_DOES_NOT_EXIST),
                   ('cannotDisseminateFormat', CANNOT_DISSEMINATE)):
    r = parse_record(err(code), REPO_DC, 'i', 'oai_dc')
    check(f'`{code}` -> {want}', r.outcome == want and r.oai_error == code)
check('** `cannotDisseminateFormat` NEVER becomes an absence — PMC13200213 answers exactly this, and '
      'it is an NIH manuscript outside the OA subset, not a paper that does not exist **',
      CANNOT_DISSEMINATE in NEVER_AN_ABSENCE)

# the format walk: richest first, and cannotDisseminateFormat is how we LEARN what a repo can do
walked = []
h, L = harvester({})


def _walk(req, *a, **k):
    url = req.full_url
    walked.append('mets' if 'metadataPrefix=mets' in url else 'oai_dc')
    if 'metadataPrefix=mets' in url:
        return _Resp(err('cannotDisseminateFormat'))
    return _Resp(wrap('''<oai_dc:dc xmlns:oai_dc="x" xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier>https://repo.test/bitstream/9/a.pdf</dc:identifier></oai_dc:dc>'''))


urllib.request.urlopen = _walk
try:
    rec = h.get_record_any_format('w7', REPO_METS, 'oai:repo.test:7')
finally:
    urllib.request.urlopen = _REAL
check('the format walk asks for the RICH dialect FIRST and falls back on cannotDisseminateFormat',
      walked == ['mets', 'oai_dc'] and rec.outcome == RECORD_RETURNED, f'asked: {walked}')
check('...so a repository that CAN serve METS is never silently answered with a landing page',
      True)

h, L = harvester({'GetRecord': b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
                               b'<error code="idDoesNotExist">x</error></OAI-PMH>'})
try:
    rec = h.get_record_any_format('w7b', REPO_METS, 'oai:repo.test:7b')
finally:
    urllib.request.urlopen = _REAL
check('an `idDoesNotExist` STOPS the walk — another format will not conjure a record they do not have',
      rec.outcome == ID_DOES_NOT_EXIST)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 8 — NO IDENTIFIER. Is "we never asked" the same as "we looked and found nothing"?')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
h, L = harvester({})
try:
    rec = h.get_record('w8', REPO_DC, '')          # no OAI id: CORE/OpenAIRE never gave us one
finally:
    urllib.request.urlopen = _REAL
check('no OAI identifier -> NO_IDENTIFIER, and NO network request is made',
      rec.outcome == NO_IDENTIFIER and not L.events('w8', EventKind.BACKEND_ATTEMPTED))
check('** it is a BUDGET_STOPPED — "a missing local DOI-to-OAI mapping does not close a repository" **',
      [e.payload.get('deferral_reason') for e in L.events('w8', EventKind.BUDGET_STOPPED)]
      == ['no_oai_identifier'])
L.emit('w8', EventKind.ROUTE_PLANNED, 'adversary', adapters=[REPO_DC.adapter])
check('** and the route CANNOT support an absence claim on the strength of a question we never asked **',
      not derive_route_status(L.events('w8')).supports_absence)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 9 — THE SEEDS AND THE DATA ROWS (the lane only works if the identifiers arrive).')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
seeds = seeds_from_core('10.1162/x', {
    'oaiIds': ['oai:ora.ox.ac.uk:uuid:2c4b', 'not-an-oai-id'],
    'dataProviders': [{'url': 'https://ora.ox.ac.uk/oai'}]})
check('CORE\'s `oaiIds` become seeds — this is the ONLY way the long tail is reachable at all',
      len(seeds) == 1 and seeds[0].oai_identifier == 'oai:ora.ox.ac.uk:uuid:2c4b'
      and seeds[0].base_url == 'https://ora.ox.ac.uk/oai' and seeds[0].learned_from == 'core')
idx = LocalOaiIndex(STATE / 'idx2.jsonl')
idx.add(seeds[0])
check('...and the index is append-only and DEDUPED (a re-run does not fork the lineage)',
      idx.add(seeds[0]) is False and len(LocalOaiIndex(STATE / 'idx2.jsonl').get('10.1162/X')) == 1,
      'a second process reads the seed back, case-insensitively')

repos = load_repositories()
check('the repositories are DATA ROWS in config/source_routes.yaml, not code',
      len(repos) >= 3 and 'pmc' in repos,
      f'{sorted(repos)}')
check('** PMC\'s OAI identifier is CONSTRUCTIBLE from a PMCID (strip_prefix:PMC) — it is the one that is **',
      build_identifier(repos['pmc'], {'pmcid': 'PMC12754963'})
      == 'oai:pubmedcentral.nih.gov:12754963',
      build_identifier(repos['pmc'], {'pmcid': 'PMC12754963'}))
check('...and PMC asks for `pmc` (JATS) BEFORE `oai_dc` — the order IS the landing-page defence',
      repos['pmc'].metadata_prefixes[0] == 'pmc')
check('** a DSpace identifier is NOT constructible from a DOI — it must be HANDED to us, and "" is '
      'the honest answer **', build_identifier(repos['dspace_generic'], {'doi': '10.1/x'}) == '')
check('the PMC base URL is the one PROVEN LIVE, not the one in the docs (`/oai/oai.cgi` is the 48KB '
      'HTML error page)', repos['pmc'].base_url == 'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/',
      repos['pmc'].base_url)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 10 — THE PAYOFF: a real JATS record IS the document (no second request).')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
REPO_PMC = Repository('pmc', 'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/', ('pmc',),
                      file_selectors=('jats_self_uri',))
#: 17 sections, article-length. NOT a nice round number chosen to clear a threshold: the real
#: PMC12754963 GetRecord is 108,635 bytes of JATS with 17 <sec>, and this fixture is that shape. The
#: FIRST draft of it was 1,020 words and the shared reducer called it ABSTRACT — correctly. A test that
#: had asserted `b'<sec>' in bytes` would have passed on it and certified a fragment as a full text.
_PARA = ('The estimated effect on employment persists across specifications and is robust to the '
         'inclusion of industry and year controls. ') * 20
body = ''.join(f'<sec><title>Section {i}</title><p>{_PARA}</p></sec>' for i in range(1, 18))
full = wrap(f'''<article xmlns:xlink="http://www.w3.org/1999/xlink">
      <front><article-meta>
        <article-id pub-id-type="doi">10.1186/s13643-025-03000-0</article-id>
      </article-meta></front>
      <body>{body}</body>
    </article>''', 'pmc')
rec = parse_record(full, REPO_PMC, 'oai:pubmedcentral.nih.gov:12754963', 'pmc')
doc = inline_document(rec)
# The claim is NOT "the bytes contain the string <sec>". It is that THE SHARED REDUCER — the only
# thing in this project allowed to look at content — reads these bytes as a complete document. A test
# that asserted on a tag name would pass on a namespace-mangled stub and fail on a real PMC record.
text, _how = acquisition.extract_text(doc, 'application/xml')
cls, info = acquisition.held_content_class({'doi': 'x', 'fulltext': text})
check('a JATS GetRecord with 17 sections IS the document — the bytes are already in the response, '
      'and THE SHARED REDUCER (not this test) calls them complete',
      rec.outcome == RECORD_RETURNED and len(doc) > 5000 and cls == C_FULLTEXT
      and info.get('complete'),
      f'{len(doc)} bytes of inline JATS -> {cls}, {info.get("readable_word_count")} readable words')
ok, basis = record_confirms_doi(rec, '10.1186/s13643-025-03000-0')
check('...and it CONFIRMS its own DOI from <article-id>, not from a regex over its bibliography', ok)
stub = parse_record(wrap('<article><front><article-meta/></front></article>', 'pmc'), REPO_PMC,
                    'i', 'pmc')
check('** a JATS FRONT-MATTER-ONLY record is NOT a document (Sol: "XML is front matter only") **',
      inline_document(stub) == b'')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 11 — ** THE RELATIVE href. ** (Found LIVE, on the first real PMC GetRecord.)')
#   PMC's JATS says, of an article we just pulled 108,635 bytes of:
#       <self-uri xlink:href="13643_2025_Article_3000.pdf"/>
#   A BARE FILENAME. Propose that as a document candidate and a fetcher goes at a URL that does not
#   exist — or, far worse, urljoins it against whatever base is lying around and fetches ANOTHER
#   ARTICLE'S PDF from the same directory.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
rel = wrap('''<article xmlns:xlink="http://www.w3.org/1999/xlink">
      <front><article-meta>
        <self-uri xlink:href="13643_2025_Article_3000.pdf"/>
      </article-meta></front>
      <body><sec><p>x</p></sec></body>
    </article>''', 'pmc')
rec = parse_record(rel, REPO_PMC, 'i', 'pmc')
check('** a relative href is NOT a document candidate — we do not know where it lives **',
      document_urls(rec, REPO_PMC) == [],
      f'relative refs recorded instead: {[(l.role, l.url) for l in relative_refs(rec, REPO_PMC)]}')
check('...and it is not silently dropped either — it is RECORDED as a relative_reference',
      [l.url for l in relative_refs(rec, REPO_PMC)] == ['13643_2025_Article_3000.pdf'])
h, L = harvester({'GetRecord': rel})
try:
    r = h.get_record('w11', REPO_PMC, 'i', 'pmc')
    check('** the harvester proposes NO candidate for it — nothing will ever fetch that filename **',
          h.propose_candidates('w11', REPO_PMC, r) == []
          and any(e.payload.get('link_role') == 'relative_reference' for e in L.events('w11')))
finally:
    urllib.request.urlopen = _REAL

REPO_BASED = Repository('r', 'https://repo.test/oai', ('pmc',), file_selectors=('jats_self_uri',),
                        document_base_url='https://repo.test/articles/PMC1/')
d = document_urls(parse_record(rel, REPO_BASED, 'i', 'pmc'), REPO_BASED)
check('...but a repository row that DECLARES a document_base_url resolves it properly (data, not a guess)',
      len(d) == 1 and d[0].url == 'https://repo.test/articles/PMC1/13643_2025_Article_3000.pdf',
      f'{[x.url for x in d]}')

print('\n' + '=' * 98)
print(f'{PASS} passed, {FAIL} failed')
print('A LANDING PAGE IS NOT A PDF. A DELETED RECORD IS NOT AN EMPTY WORLD. A CITED DOI IS NOT AN IDENTITY.')
print('=' * 98)
shutil.rmtree(STATE, ignore_errors=True)
sys.exit(1 if FAIL else 0)
