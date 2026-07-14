#!/usr/bin/env python3
"""ADVERSARY: THE PERSISTENT HOST SCHEDULER (Sol V9 §7).

THE BUILDER CANNOT VERIFY ITSELF. So this file does not ask the scheduler whether it worked. It runs
REAL WORKER PROCESSES against a REAL STATE FILE, records the wall-clock instant of every grant, and
then reads the timeline back to see what the HOST would have seen. A rate limiter that self-reports
its own compliance is `_HOST_LAST` with a dashboard.

THE SIX THINGS THAT MUST HOLD, AND THE BUG EACH ONE IS

  1. MULTIPLE WORKER PROCESSES STAY INSIDE ONE HOST BUDGET   (Sol §9: a required test, verbatim)
     `_HOST_LAST` was a module dict. Four workers meant four private "polite" rates and one very
     impolite IP.
  2. CONCURRENCY NEVER EXCEEDS THE POLICY, ACROSS PROCESSES
     "no concurrent requests" (PMC's words) cannot be enforced by a per-process counter.
  3. `Retry-After: 3600` IS OBEYED, AND IT OUTLIVES THE PROCESS THAT WAS TOLD
     We read it, logged it, and then slept 3 seconds and hammered again. Four times.
  4. A DYNAMIC LIMIT MAY ONLY *REDUCE* THE RATE
     A header that could raise our rate is a header that can talk us into a ban.
  5. THE BREAKER TRIPS ON REPEATED 401/403/429/5xx — AND A CLEAN ANSWER CLEARS IT
  6. ** NO DEFERRAL, THROTTLE, 401, 403 OR TIMEOUT MAY EVER REDUCE TO "NO OA COPY EXISTS" **
     This is the one that matters. A rate limiter is a NEW WAY to manufacture an absence: it can
     stop a request that would have succeeded, and if that silence reaches the corpus as CITATION_ONLY
     we have rebuilt the original bug inside the cure.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

STATE = Path(tempfile.mkdtemp(prefix='polaris_sched_'))
os.environ['POLARIS_SCHED_STATE'] = str(STATE)
os.environ['POLARIS_BACKOFF_SCALE'] = '0'          # SLEEP ONLY. It cannot change an event or an outcome.
os.environ['POLARIS_MAX_WAIT'] = '2'               # defer fast; we are not here to watch a clock

import host_scheduler  # noqa: E402
from host_scheduler import HostPolicy, Scheduler, parse_retry_after  # noqa: E402

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = '') -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  [PASS] {name}' + (f'\n            {detail}' if detail else ''))
    else:
        FAIL += 1
        print(f'  [FAIL] {name}\n            {detail}')


def sched(**pol) -> Scheduler:
    p = HostPolicy(host='h.test', **pol)
    return Scheduler(state_dir=STATE / f'case{time.time_ns()}', policies={'h.test': p},
                     default=p)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 1 — RETRY-AFTER IN BOTH SPELLINGS (we were parsing NEITHER).')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
now = time.time()
check('numeric Retry-After parses to seconds', parse_retry_after('3600', now) == 3600.0)
check('HTTP-date Retry-After parses to seconds (this one used to THROW, and we slept 3s)',
      abs((parse_retry_after(
          time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(now + 1800)), now) or 0) - 1800) < 2)
check('a Retry-After IN THE PAST is zero, never negative', parse_retry_after('Thu, 01 Jan 1970 00:00:00 GMT') == 0.0)
check('NO Retry-After header is None — which is NOT permission to retry immediately',
      parse_retry_after(None) is None and parse_retry_after('') is None)
check('garbage is None, not 0 (a 0 would be read as "come back now")', parse_retry_after('soon') is None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 2 — THE SERVER ASKS FOR AN HOUR. DO WE COME BACK IN THREE SECONDS?')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
s = sched(min_spacing_s=0.0, max_concurrency=4)
s.note_server_instruction('h.test', retry_after='3600')
g = s.acquire('h.test', max_wait_s=1.0)
check('** a Retry-After of ONE HOUR DEFERS the request — it does not sleep 3s and hammer **',
      g.deferred and g.reason == host_scheduler.D_NOT_BEFORE,
      f'granted={g.granted} reason={g.reason!r} not_before=+{g.not_before - time.time():.0f}s')
check('...and the hour is ON DISK, so it OUTLIVES THIS PROCESS (a restart does not forget)',
      abs(json.loads((s.hosts_dir / 'h.test.json').read_text())['not_before'] - (time.time() + 3600)) < 5)
s2 = Scheduler(state_dir=s.state_dir, policies={'h.test': s.policy('h.test')}, default=s.policy('h.test'))
check('...and A BRAND-NEW SCHEDULER OBJECT reads the same refusal (this is the cross-process seam)',
      s2.acquire('h.test', max_wait_s=0.5).deferred)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 3 — A DYNAMIC LIMIT TRIES TO SPEED US UP.')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
s = sched(min_spacing_s=2.0)
check('a SLOWER observed limit is APPLIED (5s > the configured 2s)',
      s.observe_rate_limit('h.test', min_spacing_s=5.0) is True)
check('** a FASTER observed limit is REFUSED — a header may never buy us a higher rate **',
      s.observe_rate_limit('h.test', min_spacing_s=0.1) is False,
      f"dyn stays {s.snapshot('h.test').get('dyn_min_spacing_s')}s")
check('...and the effective spacing is the SLOWER of config and observation',
      s._spacing(s.snapshot('h.test'), s.policy('h.test')) == 5.0)
hdr = {'x-ratelimit-remaining': '2', 'x-ratelimit-reset': '60'}
check('a rate-limit HEADER (2 left, resets in 60s) is read as 30s spacing',
      host_scheduler._spacing_from_headers(hdr) == 30.0)
s3 = sched(min_spacing_s=2.0)
s3.note_request_outcome('h.test', 200, headers={'x-ratelimit-remaining': '1', 'x-ratelimit-reset': '100'})
check('...and a 200 that CARRIES that header still slows us down (the limit is not only for errors)',
      s3.snapshot('h.test').get('dyn_min_spacing_s') == 100.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 4 — THE CIRCUIT BREAKER: repeated 401/403/429/5xx.')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
s = sched(min_spacing_s=0.0, breaker_threshold=3, breaker_cooldown_s=600)
for code in (429, 503, 403):
    s.note_request_outcome('h.test', code)
check('the breaker OPENS after 3 failed logical requests (429, 503, 403)', s.circuit_open('h.test'))
g = s.acquire('h.test', max_wait_s=0.5)
check('...and an open circuit DEFERS — we stop asking a host that keeps refusing us',
      g.deferred and g.reason == host_scheduler.D_CIRCUIT)
check('...and the cooldown is REAL (600s), not a 3-second pause',
      s.snapshot('h.test')['circuit_open_until'] - time.time() > 500)

s = sched(min_spacing_s=0.0, breaker_threshold=3)
s.note_request_outcome('h.test', 429)
s.note_request_outcome('h.test', 429)
s.note_request_outcome('h.test', 200)                      # they answered
s.note_request_outcome('h.test', 429)
check('a CLEAN ANSWER CLEARS the failure record (2 x 429, one 200, one 429 != a trip)',
      not s.circuit_open('h.test'), f"failures={len(s.snapshot('h.test')['failures'])}")

s = sched(min_spacing_s=0.0, breaker_threshold=3)
for _ in range(3):
    s.note_request_outcome('h.test', 404)
check('** a 404 NEVER trips the breaker — a host ANSWERING "not in my index" is not a host refusing us **',
      not s.circuit_open('h.test'))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 5 — A REDIRECT PAYS FOR THE HOST IT LANDS ON, NOT THE ONE IT ASKED.')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
pols = {'doi.org': HostPolicy('doi.org', min_spacing_s=0.0, burst=5),
        'publisher.test': HostPolicy('publisher.test', min_spacing_s=60.0, burst=1)}
s = Scheduler(state_dir=STATE / 'redir', policies=pols, default=HostPolicy('*'))
dest = s.debit_landing('doi.org', 'https://publisher.test/article.pdf')
check('the DESTINATION host is the one charged (doi.org resolved; publisher.test served)',
      dest == 'publisher.test')
check('** and the publisher\'s bucket is now in DEFICIT — the next fetch of it WAITS **',
      s.snapshot('publisher.test')['tokens'] < 1.0,
      f"publisher tokens={s.snapshot('publisher.test')['tokens']:.2f}, "
      f"doi.org untouched={not (s.hosts_dir / 'doi.org.json').exists()}")
check('...so a resolver CANNOT launder a strict host\'s budget through its own generous one',
      s.acquire('publisher.test', max_wait_s=0.2).deferred)
check('a redirect that stays ON THE SAME HOST charges nothing extra',
      s.debit_landing('publisher.test', 'https://publisher.test/other.pdf') == '')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 6 — A CRASHED WORKER HOLDS THE ONLY SLOT FOREVER.')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
s = sched(min_spacing_s=0.0, max_concurrency=1)
p = s._path('h.test')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({'host': 'h.test', 'tokens': 1.0, 'last_refill': time.time(),
                         'not_before': 0.0, 'dyn_min_spacing_s': 0.0,
                         'leases': {'ghost:1': {'pid': 999999, 'started': time.time(),
                                                'expires': time.time() + 9999}},
                         'failures': [], 'trips': 0, 'circuit_open_until': 0.0}))
g = s.acquire('h.test', max_wait_s=1.0)
check('a lease held by a DEAD PID is reaped — a SIGKILLed worker cannot wedge a host forever',
      g.granted, f'granted={g.granted} reason={g.reason!r}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 7 — CORRUPT STATE FILE. Does an unreadable bucket read as an EMPTY one or a FULL one?')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
s = sched(min_spacing_s=30.0, max_concurrency=1)
p = s._path('h.test')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text('{"tokens": NOT JSON')
g = s.acquire('h.test', max_wait_s=0.5)
check('** a CORRUPT bucket starts EMPTY, not full — "we cannot tell what we spent" means we spent it **',
      g.deferred and g.reason == host_scheduler.D_TOKEN,
      f'granted={g.granted} reason={g.reason!r}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 8 — ** THE ONE THAT MATTERS: CAN THE GOVERNOR MANUFACTURE AN ABSENCE? **')
#   A rate limiter is a NEW WAY to produce silence. If a deferral reaches the corpus as
#   "no OA copy exists", we have rebuilt the 429->CITATION_ONLY bug INSIDE THE CURE.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
os.environ['POLARIS_SPACING_SCALE'] = '0'
import importlib  # noqa: E402
importlib.reload(host_scheduler)
import acquisition  # noqa: E402
importlib.reload(acquisition)
from event_ledger import (  # noqa: E402
    BACKEND_FAILED, EventKind, Ledger, derive_route_status,
)

acquisition.SCHEDULER = Scheduler(
    state_dir=STATE / 'absence',
    policies={'wall.test': HostPolicy('wall.test', min_spacing_s=0.0, breaker_threshold=1,
                                      breaker_cooldown_s=3600)},
    default=HostPolicy('*', min_spacing_s=0.0))

L = Ledger()
acq = acquisition.Acquirer('adversary', ledger=L, blobs=acquisition.BlobStore(STATE / 'blobs'))
acq.plan_route('alm2003', ['wall'])

_real = urllib.request.urlopen


def _429_with_an_hour(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    raise urllib.error.HTTPError(url, 429, 'Too Many Requests',
                                 {'Retry-After': '3600'}, io.BytesIO(b''))


urllib.request.urlopen = _429_with_an_hour
try:
    r1 = acq.get('alm2003', 'wall', 'https://wall.test/alm.pdf', tries=4)
    r2 = acq.get('alm2003', 'wall', 'https://wall.test/alm.pdf', tries=4)   # the circuit is open now
finally:
    urllib.request.urlopen = _real

check('a 429 carrying `Retry-After: 3600` returns THROTTLED and STOPS RETRYING',
      r1.outcome == acquisition.THROTTLED, f'outcome={r1.outcome}')
attempts = [e for e in L.events('alm2003', EventKind.BACKEND_ATTEMPTED)]
check('...it made ONE attempt, not four — "the server requested hours" ended the retry loop',
      len(attempts) == 1, f'{len(attempts)} BACKEND_ATTEMPTED')
check('the SECOND request is DEFERRED by our own governor (the circuit is open / not_before is set)',
      r2.outcome == acquisition.DEFERRED, f'outcome={r2.outcome} reason={r2.deferral_reason}')

budget = L.events('alm2003', EventKind.BUDGET_STOPPED)
check('...and the deferral is on the ledger as BUDGET_STOPPED — "a budget stop IS NOT AN EVIDENCE GAP"',
      len(budget) == 1 and budget[0].payload.get('deferral_reason'),
      f"reason={budget[0].payload.get('deferral_reason') if budget else None}")
check('...and it emitted NO RESPONSE_RECEIVED — we never touched the backend, so we did not hear from it',
      not [e for e in L.events('alm2003', EventKind.RESPONSE_RECEIVED)])

route = derive_route_status(L.events('alm2003'))
check('the route reduces to BACKEND_FAILED (never "no copy exists")',
      route.outcomes.get('wall') == BACKEND_FAILED, f'{route.outcomes}')
check('** THE ROUTE CANNOT SUPPORT AN ABSENCE CLAIM **',
      not route.supports_absence, f'state={route.state} budget_stopped={route.budget_stopped}')
check('** NOT ONE outcome the governor can produce is `is_absence_evidence` **',
      not r1.is_absence_evidence and not r2.is_absence_evidence and not r1.ok and not r2.ok)
check('NOTHING in the ledger says the paper is unavailable',
      'CITATION_ONLY' not in json.dumps([e.payload for e in L.events('alm2003')]))

# -- and the OTHER four codes, each to its own word (Sol §7's outcome semantics, EXACTLY) ----------
outs = {}
for code, hdrs in ((401, {}), (403, {}), (500, {}), (404, {})):
    acquisition.SCHEDULER = Scheduler(state_dir=STATE / f'code{code}',
                                      policies={}, default=HostPolicy('*', min_spacing_s=0.0))
    L2 = Ledger()
    a2 = acquisition.Acquirer('adversary', ledger=L2, blobs=acquisition.BlobStore(STATE / 'blobs'))

    def _raise(req, *a, _c=code, _h=hdrs, **k):
        raise urllib.error.HTTPError(req.full_url, _c, 'x', _h, io.BytesIO(b''))

    urllib.request.urlopen = _raise
    try:
        outs[code] = a2.get('u', 's', f'https://code{code}.test/x', tries=2)
    finally:
        urllib.request.urlopen = _real

check('429 -> THROTTLED   (a fact about OUR REQUEST RATE)', r1.outcome == acquisition.THROTTLED)
check('401 -> AUTH_FAILED (a fact about OUR CREDENTIAL — the CORE key. The route is UNAVAILABLE.)',
      outs[401].outcome == acquisition.AUTH_FAILED, f'got {outs[401].outcome}')
check('403 -> ACCESS_DENIED (a fact about ENTITLEMENT, for THAT URL)',
      outs[403].outcome == acquisition.ACCESS_DENIED, f'got {outs[403].outcome}')
check('5xx -> bounded retry, then BACKEND_FAILED (we never got an answer)',
      outs[500].outcome == acquisition.BACKEND_FAILED, f'got {outs[500].outcome}')
check('404 -> NOT_INDEXED, and it is THE ONLY ONE that may contribute to an absence',
      outs[404].outcome == acquisition.NOT_INDEXED and outs[404].is_absence_evidence
      and not any(outs[c].is_absence_evidence for c in (401, 403, 500)))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 9 — ** MULTIPLE WORKER PROCESSES. THE HOST DOES NOT SEE OUR PROCESSES; IT SEES OUR IP. **')
#   Sol §9, required test, verbatim: "Multiple worker processes remain inside the host budget."
# ══════════════════════════════════════════════════════════════════════════════════════════════════
WORKER = STATE / 'worker.py'
WORKER.write_text('''
import json, os, sys, time
sys.path.insert(0, %r)
from host_scheduler import HostPolicy, Scheduler

state, out, n, spacing, conc = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
pol = HostPolicy(host="busy.test", min_spacing_s=spacing, max_concurrency=conc, burst=1)
s = Scheduler(state_dir=state, policies={"busy.test": pol}, default=pol)
rows = []
for _ in range(n):
    g = s.acquire("busy.test", max_wait_s=60)
    if not g.granted:
        rows.append({"pid": os.getpid(), "deferred": g.reason}); continue
    t0 = time.time()
    time.sleep(0.05)                      # the "request"
    t1 = time.time()
    s.release(g)
    rows.append({"pid": os.getpid(), "start": t0, "end": t1})
open(out, "w").write(json.dumps(rows))
''' % str(ROOT / 'scripts'))

SPACING, CONC, NPROC, NREQ = 0.30, 1, 3, 6
shared = STATE / 'mp'
procs, outs_f = [], []
env = {**os.environ, 'POLARIS_SPACING_SCALE': '1.0', 'POLARIS_SCHED_STATE': str(shared)}
t_start = time.time()
for i in range(NPROC):
    of = STATE / f'w{i}.json'
    outs_f.append(of)
    procs.append(subprocess.Popen([sys.executable, str(WORKER), str(shared), str(of),
                                   str(NREQ), str(SPACING), str(CONC)], env=env))
for p in procs:
    p.wait(timeout=180)
elapsed = time.time() - t_start

rows = [r for of in outs_f for r in json.loads(of.read_text())]
grants = sorted([r for r in rows if 'start' in r], key=lambda r: r['start'])
pids = {r['pid'] for r in grants}
check(f'{NPROC} SEPARATE OS PROCESSES contended for one bucket ({len(grants)} grants across {len(pids)} pids)',
      len(pids) == NPROC and len(grants) == NPROC * NREQ, f'{len(grants)} grants, pids={sorted(pids)}')

gaps = [grants[i + 1]['start'] - grants[i]['start'] for i in range(len(grants) - 1)]
worst = min(gaps) if gaps else 999
check(f'** NO TWO REQUESTS TO THE HOST ARE CLOSER THAN THE {SPACING}s POLICY — across all {NPROC} processes **',
      worst >= SPACING * 0.95,
      f'tightest gap seen at the host: {worst:.3f}s (policy {SPACING}s); '
      f'{len(grants)} requests in {elapsed:.1f}s = {len(grants)/elapsed:.2f} req/s '
      f'(the policy ceiling is {1/SPACING:.2f} req/s)')
check('...which is the bug `_HOST_LAST` could not even see: 3 private dicts would have allowed '
      f'{NPROC/SPACING:.1f} req/s at that host',
      len(grants) / elapsed <= (1.0 / SPACING) * 1.15,
      f'measured {len(grants)/elapsed:.2f} req/s vs the {1/SPACING:.2f} req/s ceiling')

overlaps = sum(1 for a in grants for b in grants
               if a is not b and a['start'] < b['start'] < a['end'])
check(f'** CONCURRENCY NEVER EXCEEDED {CONC} IN FLIGHT — across processes ("no concurrent requests") **',
      overlaps == 0, f'{overlaps} overlapping in-flight windows')

# and now the same thing with a REAL concurrency budget of 2 — it must ALLOW 2 and never 3.
SPACING2, CONC2 = 0.02, 2
shared2 = STATE / 'mp2'
procs, outs_f = [], []
env2 = {**os.environ, 'POLARIS_SPACING_SCALE': '1.0', 'POLARIS_SCHED_STATE': str(shared2)}
for i in range(4):
    of = STATE / f'c{i}.json'
    outs_f.append(of)
    procs.append(subprocess.Popen([sys.executable, str(WORKER), str(shared2), str(of),
                                   '6', str(SPACING2), str(CONC2)], env=env2))
for p in procs:
    p.wait(timeout=180)
g2 = sorted([r for of in outs_f for r in json.loads(of.read_text()) if 'start' in r],
            key=lambda r: r['start'])
peak = 0
for r in g2:
    peak = max(peak, sum(1 for x in g2 if x['start'] <= r['start'] < x['end']))
check(f'a max_concurrency of {CONC2} ALLOWS {CONC2} in flight and NEVER {CONC2 + 1} (it limits, it does not serialize)',
      peak == CONC2, f'peak concurrent in-flight requests across 4 processes: {peak}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
print('\nATTACK 10 — THE LIMITS COME FROM THE YAML, AND A NEW ROW CANNOT SPEED US UP.')
# ══════════════════════════════════════════════════════════════════════════════════════════════════
pols, dflt = host_scheduler.load_policies()
check('every host budget is loaded from config/source_routes.yaml (not from a constant in Python)',
      len(pols) >= 10 and 'api.crossref.org' in pols and 'www.aeaweb.org' in pols,
      f'{len(pols)} host policies; the 403-ing publisher www.aeaweb.org now HAS a row')
check('an UNKNOWN host gets the default policy, and the default is the STRICTEST row in the file',
      dflt.min_spacing_s >= 2.0 and dflt.max_concurrency == 1,
      f'default: {dflt.min_spacing_s}s, conc={dflt.max_concurrency}')
pmc = pols.get('pmc.ncbi.nlm.nih.gov')
check('** a host named in TWO rows gets the STRICTER of the two, never the later one **',
      pmc is not None and pmc.min_spacing_s >= 1.0 and pmc.max_concurrency == 1,
      f'pmc: routes[pmc]=0.34s + host_policies=1.0s -> {pmc.min_spacing_s}s '
      f'(a generous row added anywhere in a 700-line YAML cannot raise our rate)')

print('\n' + '=' * 98)
print(f'{PASS} passed, {FAIL} failed')
print('THE GOVERNOR CANNOT MANUFACTURE AN ABSENCE, AND N WORKERS ARE ONE CLIENT AT THE HOST.')
print('=' * 98)
shutil.rmtree(STATE, ignore_errors=True)
sys.exit(1 if FAIL else 0)
