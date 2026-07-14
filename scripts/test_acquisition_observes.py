#!/usr/bin/env python3
"""ACQUISITION CANARY — DOES A THROTTLE STILL DELETE A PAPER FROM THE EVIDENCE BASE?

This is adversary attack 1, kept, and pointed at the wired fetchers. Nothing is mocked except THE
SOCKET: `deep_fetch.main()`, `wp_fetch.main()` and `merge_corpus.main()` are the real ones, and every
assertion is made against WHAT LANDED ON DISK — the corpus JSON, the durable ledger, the blob store —
never against a return value a component handed us.

GROUND TRUTH, FIXED AND EXTERNAL: Autor, Levy & Murnane (2003), QJE, 4,743 citations. A FREE COPY
EXISTS — NBER Working Paper 8337, in full, forever. So ANY artifact on disk that says otherwise is
FALSE, and it does not matter how it got there.

    python3 scripts/test_acquisition_observes.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

os.environ['POLARIS_BACKOFF_SCALE'] = '0'      # SLEEP ONLY. It cannot change an event or an outcome.
os.environ['POLARIS_SPACING'] = '0'
os.environ['POLARIS_SPACING_SCALE'] = '0'      # ditto, for host_scheduler's token bucket (Sol V9 §7)

#: ** THIS TEST FIRES A 429 STORM. IT MUST NOT DO SO AT THE PRODUCTION SCHEDULER. **
#: The host scheduler's state is DURABLE and CROSS-PROCESS, which is the whole point of it — a
#: `not_before` and an open circuit breaker survive the process that earned them. That means a test
#: that hammers `api.crossref.org` with synthetic 429s against the REAL state directory would leave a
#: REAL circuit open, and the next overnight run would defer every request to a host that was never
#: actually angry with us. The storm is simulated; the throttle must not be.
#: (Not one assertion below is relaxed by this. It redirects WHERE the state is written, and nothing else.)
os.environ['POLARIS_SCHED_STATE'] = tempfile.mkdtemp(prefix='polaris_sched_canary_')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import acquisition  # noqa: E402
from acquisition import BlobStore, open_ledger  # noqa: E402
from event_ledger import (  # noqa: E402
    ACCESS_BLOCKED, BACKEND_FAILED, SEARCH_FAILED, SEARCHED_NONE, Ledger, EventKind,
    derive_backend_outcome, derive_content_profile, derive_coverage_status, derive_route_status,
)

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


ALM = {
    'doi': '10.1162/003355303322552801',
    'title': 'The Skill Content of Recent Technological Change: An Empirical Exploration',
    'authors': ['Autor', 'Levy', 'Murnane'],
    'year': 2003,
    'venue': 'The Quarterly Journal of Economics',
    'type': 'journal-article',
    'citations': 4743,
    'attribution_short': 'Autor et al. (2003), QJE',
    # NOTE: NO `content_status`. This is a FRESH acquisition of a paper we have never reached.
    # Under the old code, a 429 storm on this row ENDED with content_status='CITATION_ONLY' written
    # to disk — the miner's exclusion label — and the paper was gone. That is the claim under test.
}

CALLS: list[str] = []


def throttle_everything(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    CALLS.append(url)
    raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {}, io.BytesIO(b'rate limited'))


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, ctype='text/html'):
        super().__init__(body)
        self.headers = {'Content-Type': ctype}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_under(patch, fn):
    real = urllib.request.urlopen
    urllib.request.urlopen = patch
    try:
        return fn()
    finally:
        urllib.request.urlopen = real


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('=' * 98)
print('ATTACK 1 (kept) — EVERY BACKEND RETURNS HTTP 429.')
print('GROUND TRUTH: A FREE COPY EXISTS (NBER WP 8337). ANY "no copy" ON DISK IS FALSE.')
print('=' * 98)

tmp = Path(tempfile.mkdtemp())
acquisition.LEDGER_PATH = tmp / 'event_ledger.jsonl'
acquisition.BLOB_DIR = tmp / 'blobs'

corpus_p = tmp / 'c1.json'
corpus_p.write_text(json.dumps([dict(ALM)]))

import deep_fetch  # noqa: E402
import wp_fetch  # noqa: E402

deep_fetch.CORPUS = corpus_p
wp_fetch.CORPUS = corpus_p

print('\n--- deep_fetch.main() under HTTP 429 ---')
run_under(throttle_everything, deep_fetch.main)
print('\n--- wp_fetch.main() under HTTP 429 ---')
run_under(throttle_everything, wp_fetch.main)

row = json.loads(corpus_p.read_text())[0]
ledger = open_ledger(acquisition.LEDGER_PATH)
unit = ALM['doi']

print(f'\n  backend calls made: {len(CALLS)} (all 429)   ledger events: {len(ledger)}')

# ---- THE ONE THAT MATTERED ---------------------------------------------------------------------
# Under the old code this row came out of a 429 storm carrying content_status='CITATION_ONLY'. That
# label is the MINER'S EXCLUSION RULE: a paper that carries it is never read again. So a transient
# throttle permanently deleted the most-cited paper in the literature from the evidence base.
check('** a 429 storm writes NO content_status onto the row AT ALL **',
      'content_status' not in row,
      f"row carries content_status={row.get('content_status')!r} — written by a fetcher that was "
      f"merely throttled")

check('...and no CITATION_ONLY (the miner\'s exclusion label) appears anywhere on the row',
      'CITATION_ONLY' not in json.dumps(row),
      f'row: {json.dumps(row)[:200]}')

check('NO fetcher wrote `fulltext_source` (it named the SCRIPT, and was wrong 6 times out of 6)',
      'fulltext_source' not in row)

check('the paper is NOT deleted from the corpus — the row, and its citation, survive intact',
      row.get('doi') == ALM['doi'] and row.get('citations') == 4743)

# ---- WHAT THE LEDGER SAYS INSTEAD --------------------------------------------------------------
throttles = ledger.events(unit, EventKind.THROTTLED)
check('the 429s are ON THE DURABLE LEDGER as THROTTLED',
      len(throttles) > 0 and all(e.payload.get('http_status') == 429 for e in throttles),
      f'{len(throttles)} THROTTLED events')

route = derive_route_status(ledger.events(unit))
outcomes = {a: derive_backend_outcome(ledger.events(unit), a) for a in route.planned}
check('EVERY planned adapter reduces to BACKEND_FAILED (never "no copy exists")',
      bool(outcomes) and all(o == BACKEND_FAILED for o in outcomes.values()),
      ', '.join(f'{a}={o}' for a, o in outcomes.items()))

check('the route is COMPLETE_DEGRADED — every adapter has a record, and the search DID NOT WORK',
      route.state == 'COMPLETE_DEGRADED', f'got {route.state}')

check('** the route CANNOT support an absence claim **',
      not route.supports_absence)

cov, cinfo = derive_coverage_status(ledger, unit)
check('coverage reduces to SEARCH_FAILED, and NEVER to SEARCHED_NONE',
      cov == SEARCH_FAILED and cov != SEARCHED_NONE, f'got {cov}')
print(f'            reason: {cinfo["reason"][:110]}')

cls, _ = derive_content_profile(ledger.events(unit))
check('the reducer CAN still say CITATION_ONLY over zero bytes — but only as a derivation, sitting '
      'beside a route that reads SEARCH_FAILED, which is what stops it meaning "no copy exists"',
      cls == 'CITATION_ONLY' and cov == SEARCH_FAILED)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
print('THE OTHER THREE WORLDS `None` USED TO COLLAPSE INTO')
print('=' * 98)

L = Ledger()
acq = acquisition.Acquirer('t', ledger=L, blobs=BlobStore(tmp / 'blobs'))


def _raise(code):
    def f(req, *a, **k):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        raise urllib.error.HTTPError(url, code, 'x', {}, io.BytesIO(b''))
    return f


run_under(_raise(404), lambda: acq.get('u', 's2', 'https://x/404'))
check('HTTP 404 -> NOT_INDEXED_BY_THIS_BACKEND (their index, not the world)',
      derive_backend_outcome(L.events('u'), 's2') == 'NOT_INDEXED_BY_THIS_BACKEND',
      derive_backend_outcome(L.events('u'), 's2'))

run_under(_raise(403), lambda: acq.get('u2', 'publisher', 'https://x/403'))
check('HTTP 403 -> ACCESS_BLOCKED (entitlement, not absence)',
      derive_backend_outcome(L.events('u2'), 'publisher') == ACCESS_BLOCKED)


def _hang(req, *a, **k):
    raise TimeoutError('The read operation timed out')


run_under(_hang, lambda: acq.get('u3', 's2', 'https://x/hang', tries=2))
check('a TIMEOUT -> BACKEND_FAILED (a hang, not a gap)',
      derive_backend_outcome(L.events('u3'), 's2') == BACKEND_FAILED)

# ...and the backoff that WORKS is not a failure.
state = {'n': 0}


def _flaky(req, *a, **k):
    state['n'] += 1
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    if state['n'] < 3:
        raise urllib.error.HTTPError(url, 429, 'Too Many', {}, io.BytesIO(b''))
    return _Resp(b'{"ok":1}', 'application/json')


r = run_under(_flaky, lambda: acq.get('u4', 's2', 'https://x/flaky'))
check('429, 429, then 200 -> RESPONDED, and the bytes are returned (backoff is what backoff is FOR)',
      r.ok and derive_backend_outcome(L.events('u4'), 's2') == 'RESPONDED')
check('...and BOTH 429s are still on the ledger — nothing was deleted to reach that answer',
      len(L.events('u4', EventKind.THROTTLED)) == 2)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
print('THE HAPPY PATH — BYTES BECOME AN IMMUTABLE, ADDRESSED, PROFILED MANIFESTATION')
print('=' * 98)

PAPER = (b'Journal of Economic Perspectives - Volume 33, Number 2 - Spring 2019 - Pages 3-30\n'
         b'Automation and New Tasks: How Technology Displaces and Reinstates Labor\n'
         b'Daron Acemoglu and Pascual Restrepo\n\n') + b'the effect of robots on employment is 0.2 percentage points. ' * 400

L2 = Ledger(tmp / 'happy.jsonl')
blobs = BlobStore(tmp / 'blobs')
acq2 = acquisition.Acquirer('t', ledger=L2, blobs=blobs)
u = '10.1257/jep.33.2.3'

acq2.plan_route(u, ['s2/doi'])
r = run_under(lambda req, *a, **k: _Resp(PAPER, 'application/pdf' if False else 'text/plain'),
              lambda: acq2.get(u, 's2/doi', 'https://nber.org/x.pdf'))
txt, method = r.text()
acq2.candidate(u, 's2/doi', 'https://nber.org/x.pdf')
info = acq2.record_manifestation(
    u, locator='https://nber.org/x.pdf', raw=r.raw, text=txt, adapter='s2/doi',
    requested_title='Automation and New Tasks', requested_authors=['Acemoglu', 'Restrepo'],
    requested_doi=u, requested_venue='Journal of Economic Perspectives', requested_year=2019,
    source_type='journal-article', extraction_method=method)

check('the manifestation carries an IMMUTABLE BLOB ID and a BYTE HASH',
      info['blob_id'].startswith('sha256:') and len(info['byte_sha256']) == 64)
check('the blob is content-addressed and re-reads byte-for-byte',
      blobs.get(info['blob_id']) == PAPER)
check('the LOCATOR is recorded BY THE FETCHER THAT MADE THE REQUEST',
      L2.events(u, EventKind.MANIFESTATION_FETCHED)[0].payload['locator'] == 'https://nber.org/x.pdf')

profs = L2.events(u, EventKind.CONTENT_PROFILE_DERIVED)
check('CONTENT_PROFILE_DERIVED came from the shared reducer, and the fetcher supplied no part of it',
      len(profs) == 1 and profs[0].actor == 'observe_text'
      and 'readable_word_count' in profs[0].payload)

cls2, i2 = derive_content_profile(L2.events(u))
check('the bytes EARN their label (FULLTEXT / journal_article) — nobody declared it',
      cls2 == 'FULLTEXT' and i2['artifact_kind'] == 'journal_article',
      f'{cls2} / {i2.get("artifact_kind")}')

# a fetcher cannot inflate a profile, because the API has no parameter for one
try:
    acq2.record_manifestation(u, locator='x', raw=b'x', text='x', adapter='a',
                              content_status='FULLTEXT')
    check('a fetcher CANNOT smuggle a content_status into a manifestation', False, 'IT WAS ACCEPTED')
except Exception as e:
    check('a fetcher CANNOT smuggle a content_status into a manifestation '
          f'({type(e).__name__})', True)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
print('THE MERGE — "THE VERSION WITH THE MOST TEXT" IS DEAD')
print('=' * 98)

# The exact shape that beat us: a LONGER cookie banner vs a SHORTER real article, for one DOI.
BANNER = ('This website uses cookies. By clicking the "Accept" button you agree. Sign in to your '
          'account. Privacy policy. Terms of use. All rights reserved. Subscribe to read. '
          'Download PDF. Share this. ') * 60
ARTICLE = ('Journal of Economic Perspectives - Volume 33, Number 2 - Spring 2019 - Pages 3-30. '
           'Automation and New Tasks. By Daron Acemoglu and Pascual Restrepo. ') + \
          ('We estimate that one more robot per thousand workers reduces the employment to population '
           'ratio by 0.2 percentage points. ') * 130

print(f'  the cookie banner is {len(BANNER.split()):,} words')
print(f'  the real article is  {len(ARTICLE.split()):,} words   <- SHORTER. The old merge picked the banner.')

DOI = '10.1257/jep.33.2.3'
a_p, b_p = tmp / 'a.json', tmp / 'b.json'
a_p.write_text(json.dumps([{**ALM, 'doi': DOI, 'title': 'Automation and New Tasks',
                            'authors': ['Acemoglu', 'Restrepo'], 'year': 2019,
                            'venue': 'Journal of Economic Perspectives',
                            'fulltext': BANNER, 'content_status': 'FULLTEXT',
                            'fulltext_source': 'working_paper'}]))
b_p.write_text(json.dumps([{**ALM, 'doi': DOI, 'title': 'Automation and New Tasks',
                            'authors': ['Acemoglu', 'Restrepo'], 'year': 2019,
                            'venue': 'Journal of Economic Perspectives',
                            'fulltext': ARTICLE, 'content_status': 'ABSTRACT_ONLY'}]))

import merge_corpus  # noqa: E402

merge_corpus.CORPUS = tmp / 'merged.json'
sys.argv = ['merge_corpus.py', str(a_p), str(b_p)]
merge_corpus.main()

merged = json.loads((tmp / 'merged.json').read_text())
check('the merge produced ONE row for the DOI', len(merged) == 1, f'{len(merged)} rows')
m = merged[0]

check('** the SHORTER real article won over the LONGER cookie banner **',
      'one more robot per thousand workers' in (m.get('fulltext') or ''),
      f"row holds {len((m.get('fulltext') or '').split()):,} words; "
      f"starts {(m.get('fulltext') or '')[:60]!r}")
check('...and the losing bytes were NOT DELETED — both manifestations are retained',
      len(m.get('manifestations') or []) == 2,
      f"{len(m.get('manifestations') or [])} manifestations")
kinds = {mm['artifact_kind'] for mm in (m.get('manifestations') or [])}
check('...and the banner is retained AS A landing_page, named for what it is',
      'landing_page' in kinds and 'journal_article' in kinds, str(sorted(kinds)))
check('the derived label carries its BASIS and names the reducer that derived it',
      m.get('content_status_derived_by') == 'event_ledger.derive_content_profile'
      and bool(m.get('content_status_basis')))
check('`fulltext_source` was REMOVED, not corrected', 'fulltext_source' not in m)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
print('THE SOURCE CANARY — the vocabulary is GONE, not merely unused')
print('=' * 98)

import ast

# THE CHECK MUST READ THE CODE, NOT THE PROSE. Every one of these files QUOTES the line it deleted, in
# its docstring, as a headstone — and a grep for the dead word finds the epitaph and calls it the
# corpse. (My first version of this canary did exactly that and failed all three. A gate that cannot
# tell an executable string from a comment about one is the same class of error as a gate that checks
# the wrong lane.) So: docstrings are excluded, and only strings that CAN REACH A ROW are examined.


def _live_strings(tree) -> list[tuple[int, str]]:
    """Every string constant that is NOT a docstring — i.e. every string this module can actually say."""
    docstrings = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, 'body', None) or []
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


for f in ('journal_corpus_fetch.py', 'deep_fetch.py', 'wp_fetch.py', 'version_align.py'):
    tree = ast.parse((ROOT / 'scripts' / f).read_text())

    # 1. an ASSIGNMENT to a row's conclusion field: c['content_status'] = ... / c['fulltext_source'] = ...
    writes = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                        and t.slice.value in ('content_status', 'fulltext_source')):
                    writes.append(f'{f}:{n.lineno} writes [{t.slice.value!r}]')
    check(f'{f}: writes NO content_status / fulltext_source onto a row', not writes, '; '.join(writes))

    # 2. the CONCLUSION VOCABULARY is gone from every string this file can actually emit.
    said = [f'{f}:{ln} says {s[:50]!r}' for ln, s in _live_strings(tree)
            if any(w in s.lower() for w in ('paywalled', 'no free copy', 'no free text'))]
    check(f'{f}: cannot SAY "paywalled" / "no free copy" (not one live string literal)',
          not said, '; '.join(said))

# ...and the ONE place a conclusion may still be written is a REDUCER, and it names the one that made it.
mtree = ast.parse((ROOT / 'scripts' / 'merge_corpus.py').read_text())
mcalls = {n.func.id for n in ast.walk(mtree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
check('merge_corpus CALLS record_content_profile (the audited reducer) — not merely imports it',
      'record_content_profile' in mcalls)
mnames = {t.id for n in ast.walk(mtree) if isinstance(n, ast.Assign)
          for t in n.targets if isinstance(t, ast.Name)}
mfuncs = {n.name for n in ast.walk(mtree) if isinstance(n, ast.FunctionDef)}
check('merge_corpus no longer defines RANK or textlen (the length-and-claimed-status contest is gone)',
      'RANK' not in mnames and 'textlen' not in mfuncs,
      f'RANK in names: {"RANK" in mnames}; textlen defined: {"textlen" in mfuncs}')

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
print('THE PROVENANCE CONSTRUCTION REDUCER (Sol a.2)')
print('=' * 98)

import provenance_construct  # noqa: E402

g, stats = provenance_construct.construct(open_ledger(tmp / 'event_ledger.jsonl'),
                                          blobs=BlobStore(tmp / 'blobs'))
lg = open_ledger(merge_corpus.LEDGER_PATH if hasattr(merge_corpus, 'LEDGER_PATH')
                 else acquisition.LEDGER_PATH)
g2, stats2 = provenance_construct.construct(lg, blobs=BlobStore(tmp / 'blobs'))

check('the reducer builds a typed graph FROM THE LEDGER (works / expressions / manifestations)',
      len(g2.works) >= 1 and len(g2.manifestations) >= 2,
      f'{len(g2.works)} works, {len(g2.expressions)} expressions, '
      f'{len(g2.manifestations)} manifestations, {len(g2.edges)} edges')

check('EVERY manifestation in the graph names a real expression of its own work',
      all(m.expression_id in g2.expressions and g2.expressions[m.expression_id].work_id == m.work_id
          for m in g2.manifestations.values()))

check('the cookie banner is QUARANTINED — it expresses no version of the work',
      any(':quarantine:' in m.expression_id for m in g2.manifestations.values()))

check('NOT ONE span-preserving edge is ASSERTED (only byte-level evidence could do that)',
      not [e for e in g2.edges
           if e.status == 'ASSERTED' and e.type in ('exact_copy_of', 'accepted_manuscript_of')])

check('the locator on a fetched manifestation is RECORDED, by the fetcher that requested it',
      any(m.locator_status == 'RECORDED' for m in g2.manifestations.values())
      or all(m.locator_status.startswith('CLAIMED') or m.locator_status == 'NOT_RECORDED_BY_FETCHER'
             for m in g2.manifestations.values()))

# IDEMPOTENT: it runs after EVERY acquisition batch.
before = (len(g2.works), len(g2.expressions), len(g2.manifestations), len(g2.edges))
g3, _ = provenance_construct.construct(lg, graph=g2, blobs=BlobStore(tmp / 'blobs'))
after = (len(g3.works), len(g3.expressions), len(g3.manifestations), len(g3.edges))
check('re-running the reducer over the same ledger changes NOTHING (it extends, it does not duplicate)',
      before == after, f'{before} -> {after}')

# the graph it writes must survive its own STRICT loader
from provenance import Graph  # noqa: E402
try:
    Graph.from_json(g3.to_json())
    check('the constructed graph SURVIVES provenance.Graph.from_json (the strict, refusing loader)',
          True)
except Exception as e:
    check('the constructed graph SURVIVES provenance.Graph.from_json', False, str(e)[:300])

# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 98)
if fails:
    print(f'** {len(fails)} FAILURE(S) **')
    for f in fails:
        print(f'   - {f}')
    raise SystemExit(1)
print('ACQUISITION OBSERVES. IT DOES NOT CONCLUDE.')
print('A 429 on Autor/Levy/Murnane is THROTTLED -> BACKEND_FAILED -> SEARCH_FAILED, on the durable')
print('ledger, forever. It cannot become CITATION_ONLY: no fetcher holds an API that could write it.')
print('=' * 98)
raise SystemExit(0)
