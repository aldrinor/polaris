#!/usr/bin/env python3
"""HOST SCHEDULER — THE PERSISTENT, CROSS-PROCESS POLITENESS GOVERNOR (Sol V9 §7).

    Sol §7, verbatim: "Replace `_HOST_LAST` and the single `SPACING_S` in acquisition.py with a
    cross-process persistent scheduler."

WHAT `_HOST_LAST` WAS, AND WHY IT COULD NOT HOLD

  It was a MODULE-LEVEL DICT.

      _HOST_LAST: dict[str, float] = {}          # acquisition.py:225

  Three facts follow from that one line, and each of them is a way we got IP-throttled all night:

    1. IT DIED WITH THE PROCESS. Every fetcher we launched started life believing it had never
       spoken to api.crossref.org. A detached, resumable run — which is what we are about to do —
       restarts, and restarts, and each restart is a fresh burst against a host that is already
       angry with us.

    2. IT WAS NOT SHARED. Two worker processes each held their OWN `_HOST_LAST`, so `SPACING_S = 1.1`
       meant 1.1s per host PER PROCESS. Run four workers and the "polite" 0.9 req/s is 3.6 req/s at
       the host, which is the definition of the thing we were trying not to do. THE HOST DOES NOT
       SEE OUR PROCESSES. It sees our IP.

    3. IT COULD NOT REMEMBER A REFUSAL. `Retry-After: 3600` was read (`_retry_after`), written to
       the ledger, and then THROWN AWAY: `_backoff()` slept 3, 6, 12 seconds and hammered again.
       The server asked for an hour and we came back in three seconds, four times, and then called
       the paper unavailable.

WHAT THIS IS INSTEAD

  A per-host TOKEN BUCKET plus a CONCURRENCY LIMIT, in a file, under an flock. The file is the
  shared truth: N worker processes on one machine contend for the same bucket, so the rate at the
  HOST is the configured rate no matter how many of us there are. The budget is keyed by HOST, so
  the resolver host (api.unpaywall.org) and the content host (www.nber.org) are budgeted SEPARATELY
  and neither can spend the other's tokens — and a REDIRECT CHARGES ITS DESTINATION, because the
  bytes come from wherever we land, not from wherever we asked.

  `not_before` is DURABLE. When a server says "come back in an hour", the hour survives the process
  that was told.

THE ONE THING IT MAY NEVER DO

  A deferral is not an absence. When the bucket is empty, when `not_before` is in the future, when
  the circuit is open — the request DOES NOT HAPPEN, and what goes on the ledger is BUDGET_STOPPED:
  the event that exists precisely because "a budget stop IS NOT AN EVIDENCE GAP". It is not a
  RESPONSE_RECEIVED with an empty body. It is not a 404. Nothing here can be reduced to "no OA copy
  exists", and `RouteStatus.supports_absence` is False whenever `budget_stopped` is set, forever.

DYNAMIC LIMITS MAY ONLY REDUCE THE RATE (Sol §7)

  `observe_rate_limit()` takes what a server told us (`X-RateLimit-Limit`, a `Retry-After`, a
  documented tier) and applies it ONLY IF IT IS SLOWER than the configured policy. A response header
  can slow us down. It can never speed us up — a compromised or merely mistaken header must not be
  able to talk us into hammering a host, and "the server said we could" is not a defence we get to
  offer.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROUTES_YAML = ROOT / 'config' / 'source_routes.yaml'
STATE_DIR = Path(os.environ.get('POLARIS_SCHED_STATE', str(ROOT / 'outputs' / 'scheduler')))

#: SLEEP ONLY. Scales the CONFIGURED SPACING so an adversarial harness can drive a thousand grants
#: without waiting twenty minutes. It cannot change an event, a retry count, an outcome, `not_before`,
#: or a circuit decision — those are facts, and a test knob that could edit a fact is a test knob that
#: certifies a lane the production code does not use.
SPACING_SCALE = float(os.environ.get('POLARIS_SPACING_SCALE', '1.0'))

#: The longest a single request is willing to WAIT for its turn before it gives up and DEFERS. This is
#: the line Sol drew: "do not sleep and retry three seconds later when the server requests hours."
#: Beyond this, we do not sleep — we record BUDGET_STOPPED and move to another host.
MAX_WAIT_S = float(os.environ.get('POLARIS_MAX_WAIT', '30'))

#: A lease that outlives this is a CRASHED WORKER's lease, and it is reaped. Without this, one worker
#: killed with SIGKILL while holding the only concurrency slot would wedge a host forever.
LEASE_TTL_S = float(os.environ.get('POLARIS_LEASE_TTL', '180'))

# ---- the deferral reasons. Each is a fact about US, and none of them is a fact about the world. ----
D_TOKEN       = 'rate_budget_exhausted'    # our token bucket is empty
D_CONCURRENCY = 'concurrency_limit'        # this host's in-flight slots are all taken
D_NOT_BEFORE  = 'server_requested_wait'    # the SERVER told us when to come back, and we listened
D_CIRCUIT     = 'circuit_open'             # this host has refused us repeatedly; we stopped asking
D_ROBOTS      = 'robots_disallowed'        # robots.txt forbids this path for our agent

#: The codes that COUNT AGAINST A HOST. 401/403 are entitlement, 429 is our rate, 5xx is their box —
#: three different worlds, and all three mean "stop hammering this host". The breaker does not care
#: WHY it is failing; that distinction is preserved exactly where it matters, in the OUTCOME.
BREAKER_CODES = (401, 402, 403, 429, 451, 500, 502, 503, 504)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RETRY-AFTER — BOTH SPELLINGS. The HTTP-date one is not exotic; Cloudflare and NCBI both send it.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def parse_retry_after(value: Any, now: float | None = None) -> float | None:
    """`Retry-After` -> SECONDS FROM NOW, or None if there was no parseable instruction.

    RFC 9110 allows TWO forms and we were reading neither:

        Retry-After: 3600                              (delta-seconds)
        Retry-After: Wed, 21 Oct 2026 07:28:00 GMT     (HTTP-date)

    `acquisition._retry_after` returned the raw string, the ledger recorded it, and the retry loop
    slept `3 * 2**attempt` regardless. An HTTP-date parsed as an int throws; a delta of 3600 slept
    for 3. Both ended in the same place: we came back too early and the host stopped answering.

    None means NO INSTRUCTION — which is not the same as zero, and the caller must not treat it as
    permission to retry immediately.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    now = time.time() if now is None else now
    if re.fullmatch(r'\d+(\.\d+)?', s):
        return max(0.0, float(s))
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        return None
    if dt is None:
        return None
    try:
        return max(0.0, dt.timestamp() - now)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# POLICY — DATA. Every limit here is read from config/source_routes.yaml. None of it is in code.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HostPolicy:
    """What we are ALLOWED to do to one host. `origin` names the row that said so, so a limit is
    never anonymous: `source_routes.yaml#core` is answerable for `min_spacing_s: 2.0` in a way that a
    magic number in a Python file is not."""
    host: str
    min_spacing_s: float = 2.0
    max_concurrency: int = 1
    burst: float = 1.0
    breaker_threshold: int = 6          # FAILED LOGICAL REQUESTS, not failed attempts
    breaker_window_s: float = 300.0
    breaker_cooldown_s: float = 300.0
    origin: str = 'default'

    @property
    def effective_spacing_s(self) -> float:
        return max(0.0, self.min_spacing_s) * SPACING_SCALE


def _policy_from_row(host: str, row: dict, origin: str, default: HostPolicy) -> HostPolicy:
    def num(dflt, *keys):
        for key in keys:
            v = row.get(key)
            if v is not None:
                return float(v)
        return dflt
    return HostPolicy(
        host=host,
        min_spacing_s=num(default.min_spacing_s, 'min_spacing_s'),
        # `max_in_flight` is the spelling the PMC row already uses ("NO CONCURRENT REQUESTS"). Two
        # names for one limit is how a limit gets silently ignored, so BOTH are read, here, once.
        max_concurrency=int(num(default.max_concurrency, 'max_concurrency', 'max_in_flight')),
        burst=num(default.burst, 'burst'),
        breaker_threshold=int(num(default.breaker_threshold, 'breaker_threshold')),
        breaker_window_s=num(default.breaker_window_s, 'breaker_window_s'),
        breaker_cooldown_s=num(default.breaker_cooldown_s, 'breaker_cooldown_s'),
        origin=origin,
    )


def _strictest(a: HostPolicy, b: HostPolicy) -> HostPolicy:
    """ONE HOST, TWO ROWS -> THE STRICTER OF THE TWO. Never the later one, never the faster one.

    `pmc.ncbi.nlm.nih.gov` appears in routes[pmc].rate_policy (0.34s — their documented 3/s ceiling),
    in host_policies, and in oai_repositories[pmc]. Under last-row-wins, adding a generous row anywhere
    in a 600-line YAML would quietly raise our rate against a host we are already being throttled by,
    and nobody would ever see it. The merge is a MIN over permissions, so a new row can only ever make
    us more polite — which is the same invariant as `observe_rate_limit`, applied to the config itself.
    """
    return HostPolicy(
        host=a.host,
        min_spacing_s=max(a.min_spacing_s, b.min_spacing_s),
        max_concurrency=max(1, min(a.max_concurrency, b.max_concurrency)),
        burst=max(1.0, min(a.burst, b.burst)),
        breaker_threshold=max(1, min(a.breaker_threshold, b.breaker_threshold)),
        breaker_window_s=max(a.breaker_window_s, b.breaker_window_s),
        breaker_cooldown_s=max(a.breaker_cooldown_s, b.breaker_cooldown_s),
        origin=f'{a.origin} + {b.origin}',
    )


def load_policies(path: Path | str = ROUTES_YAML) -> tuple[dict[str, HostPolicy], HostPolicy]:
    """-> ({host: HostPolicy}, default). EVERY LIMIT COMES FROM THE YAML (Sol §7).

    Three places in the table declare a host budget, and all three are DATA:
      routes[*].rate_policy      the resolver/index APIs
      host_policies[*]           CONTENT hosts (publishers, repositories) — they are backends too
      oai_repositories[*].rate_policy   one row per repository (Sol §2: "each repository is a data row")
    """
    import yaml
    doc = yaml.safe_load(Path(path).read_text()) or {}
    default = HostPolicy(host='*', origin='default_host_policy')
    if isinstance(doc.get('default_host_policy'), dict):
        default = _policy_from_row('*', doc['default_host_policy'], 'source_routes.yaml#default', default)

    out: dict[str, HostPolicy] = {}

    def add(row: dict, origin: str) -> None:
        host = str(row.get('host') or '').strip().lower()
        if not host or host == 'scoped':      # `scoped` is a placeholder, not a hostname
            return
        pol = _policy_from_row(host, row, origin, default)
        out[host] = _strictest(out[host], pol) if host in out else pol

    for r in doc.get('routes') or []:
        rp = r.get('rate_policy') or {}
        if rp:
            add(rp, f"source_routes.yaml#routes.{r.get('adapter_id')}")
    for r in doc.get('host_policies') or []:
        add(r, f"source_routes.yaml#host_policies.{r.get('host')}")
    for r in doc.get('oai_repositories') or []:
        rp = r.get('rate_policy') or {}
        if rp:
            add(rp, f"source_routes.yaml#oai_repositories.{r.get('repository_id')}")
    return out, default


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).netloc or 'unknown').lower().split('@')[-1]
    except Exception:
        return 'unknown'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE GRANT — a token, a slot, and a lease id. Or a REFUSAL that carries WHY and UNTIL WHEN.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Grant:
    host: str
    granted: bool
    lease_id: str = ''
    reason: str = ''                 # set only when granted is False. One of D_*.
    not_before: float = 0.0          # when this host will next accept a request from us
    waited_s: float = 0.0

    @property
    def deferred(self) -> bool:
        return not self.granted


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class Scheduler:
    """Cross-process, per-host. The STATE IS A FILE and the file is the arbiter.

    WHY A FILE AND NOT A LOCK SERVER: because the thing we must survive is a worker being SIGKILLed
    mid-fetch, and a resumable overnight run being restarted at 3am by a supervisor that does not
    know what happened before it. A file with an flock and expiring leases survives both. A daemon
    holding the state in RAM is `_HOST_LAST` with extra steps.
    """

    def __init__(self, state_dir: Path | str | None = None,
                 policies: dict[str, HostPolicy] | None = None,
                 default: HostPolicy | None = None):
        self.state_dir = Path(state_dir) if state_dir else Path(STATE_DIR)
        self.hosts_dir = self.state_dir / 'hosts'
        self.hosts_dir.mkdir(parents=True, exist_ok=True)
        if policies is None:
            try:
                policies, loaded_default = load_policies()
            except Exception:
                policies, loaded_default = {}, HostPolicy(host='*')
            default = default or loaded_default
        self._policies = policies
        self._default = default or HostPolicy(host='*')

    # ---- policy ---------------------------------------------------------------------------------
    def policy(self, host: str) -> HostPolicy:
        h = (host or 'unknown').lower()
        p = self._policies.get(h)
        if p is not None:
            return p
        # a subdomain inherits its parent's row only if the parent is explicitly listed
        for cand, pol in self._policies.items():
            if h.endswith('.' + cand):
                return HostPolicy(**{**pol.__dict__, 'host': h, 'origin': pol.origin + ' (parent)'})
        return HostPolicy(**{**self._default.__dict__, 'host': h})

    # ---- the state file -------------------------------------------------------------------------
    def _path(self, host: str) -> Path:
        safe = re.sub(r'[^a-z0-9._-]', '_', (host or 'unknown').lower())[:80]
        return self.hosts_dir / f'{safe}.json'

    def _blank(self, host: str, pol: HostPolicy, now: float) -> dict:
        return {'host': host, 'tokens': pol.burst, 'last_refill': now, 'not_before': 0.0,
                'dyn_min_spacing_s': 0.0, 'leases': {}, 'failures': [], 'trips': 0,
                'circuit_open_until': 0.0, 'grants': 0, 'deferrals': 0}

    class _Locked:
        """flock(LOCK_EX) around a read-modify-write. WE NEVER SLEEP HOLDING THIS LOCK — a sleeping
        worker inside the critical section is a worker that stops every other worker from even
        LOOKING at the bucket, which turns a rate limiter into a global serializer."""

        def __init__(self, sched: 'Scheduler', host: str):
            self.sched, self.host = sched, host
            self.fh = None
            self.state: dict = {}

        def __enter__(self) -> dict:
            p = self.sched._path(self.host)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(p, 'a+')
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
            self.fh.seek(0)
            raw = self.fh.read()
            pol = self.sched.policy(self.host)
            try:
                self.state = json.loads(raw) if raw.strip() else self.sched._blank(self.host, pol, time.time())
            except Exception:
                # A CORRUPT BUCKET IS NOT AN EMPTY BUCKET. Start EMPTY (zero tokens), not full: if we
                # cannot read how much of our budget we already spent, the safe assumption is ALL OF IT.
                self.state = self.sched._blank(self.host, pol, time.time())
                self.state['tokens'] = 0.0
            self.state.setdefault('leases', {})
            self.state.setdefault('failures', [])
            return self.state

        def __exit__(self, *exc) -> None:
            try:
                self.fh.seek(0)
                self.fh.truncate()
                self.fh.write(json.dumps(self.state, sort_keys=True))
                self.fh.flush()
                os.fsync(self.fh.fileno())
            finally:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
                self.fh.close()

    def _locked(self, host: str) -> '_Locked':
        return Scheduler._Locked(self, host)

    # ---- the bucket -----------------------------------------------------------------------------
    @staticmethod
    def _refill(st: dict, pol: HostPolicy, spacing: float, now: float) -> None:
        elapsed = max(0.0, now - float(st.get('last_refill') or now))
        st['last_refill'] = now
        if spacing <= 0:
            st['tokens'] = pol.burst           # spacing 0 => the harness turned politeness off
            return
        st['tokens'] = min(pol.burst, float(st.get('tokens') or 0.0) + elapsed / spacing)

    @staticmethod
    def _reap(st: dict, now: float) -> None:
        """A lease held by a process that no longer exists is not a lease. It is a wedge."""
        live = {}
        for lid, rec in (st.get('leases') or {}).items():
            if float(rec.get('expires') or 0) <= now:
                continue
            pid = int(rec.get('pid') or 0)
            if pid and pid != os.getpid():
                try:
                    os.kill(pid, 0)
                except OSError as e:
                    if e.errno == errno.ESRCH:      # the holder is dead. Its slot is free.
                        continue
            live[lid] = rec
        st['leases'] = live

    def _spacing(self, st: dict, pol: HostPolicy) -> float:
        """The effective spacing: THE SLOWER of the configured policy and anything a server told us.

        Sol §7: "Dynamic limits can only reduce the configured rate." So this is a MAX over spacings,
        never a min. A `X-RateLimit-Limit: 10000` header cannot buy us a faster rate than the row in
        the YAML allows — the YAML is the promise we made, and a stranger's header does not get to
        renegotiate it.
        """
        dyn = float(st.get('dyn_min_spacing_s') or 0.0) * SPACING_SCALE
        return max(pol.effective_spacing_s, dyn)

    # ---- acquire / release ----------------------------------------------------------------------
    def acquire(self, host: str, *, max_wait_s: float | None = None) -> Grant:
        """A token AND a concurrency slot for one request to `host`, or a DEFERRAL that says why.

        Blocks only up to `max_wait_s` (default POLARIS_MAX_WAIT=30s). Past that it REFUSES rather
        than sleeps — which is the whole point of `not_before`: when NCBI says "in one hour", the
        answer is not to sleep for an hour holding a worker hostage. It is to go do another host.
        """
        host = (host or 'unknown').lower()
        pol = self.policy(host)
        budget = MAX_WAIT_S if max_wait_s is None else float(max_wait_s)
        t0 = time.time()
        deadline = t0 + budget
        while True:
            now = time.time()
            with self._locked(host) as st:
                self._reap(st, now)
                wait, reason = 0.0, ''
                if float(st.get('circuit_open_until') or 0) > now:
                    wait, reason = float(st['circuit_open_until']) - now, D_CIRCUIT
                elif float(st.get('not_before') or 0) > now:
                    wait, reason = float(st['not_before']) - now, D_NOT_BEFORE
                else:
                    spacing = self._spacing(st, pol)
                    self._refill(st, pol, spacing, now)
                    if len(st['leases']) >= max(1, pol.max_concurrency):
                        # A slot frees when a peer RELEASES. Poll — but the poll is short and the
                        # LOCK IS NOT HELD while we wait.
                        wait, reason = 0.05, D_CONCURRENCY
                    elif float(st['tokens']) < 1.0:
                        wait = (1.0 - float(st['tokens'])) * spacing if spacing > 0 else 0.0
                        reason = D_TOKEN
                    else:
                        st['tokens'] = float(st['tokens']) - 1.0
                        lid = f'{os.getpid()}:{random.getrandbits(48):012x}'
                        st['leases'][lid] = {'pid': os.getpid(), 'started': now,
                                             'expires': now + LEASE_TTL_S}
                        st['grants'] = int(st.get('grants') or 0) + 1
                        return Grant(host, True, lease_id=lid, waited_s=now - t0)
                if now + wait > deadline:
                    st['deferrals'] = int(st.get('deferrals') or 0) + 1
                    return Grant(host, False, reason=reason, not_before=now + wait, waited_s=now - t0)
            time.sleep(max(0.0, min(wait, deadline - time.time())))   # OUTSIDE THE LOCK.

    def release(self, grant: Grant) -> None:
        if not grant.granted or not grant.lease_id:
            return
        with self._locked(grant.host) as st:
            st['leases'].pop(grant.lease_id, None)

    def debit_landing(self, origin_host: str, landed_url: str) -> str:
        """A REDIRECT CHARGES ITS DESTINATION (Sol §7). -> the host charged, or ''.

        We asked doi.org and the bytes came from www.sciencedirect.com. doi.org is a cheap, generous
        resolver; sciencedirect is a host that will happily stop answering us. Charging only the host
        we ADDRESSED makes every publisher fetch a laundering operation through a resolver's budget,
        and the host we actually hammered never appears in our accounting at all.

        This is a pure DEBIT, taken after urllib has already followed the hops: it may drive the
        bucket NEGATIVE, and that is the point — the NEXT request to that host waits for the deficit
        to refill. It never blocks the request that already happened.
        """
        dest = host_of(landed_url)
        if not dest or dest == (origin_host or '').lower() or dest == 'unknown':
            return ''
        pol = self.policy(dest)
        with self._locked(dest) as st:
            now = time.time()
            self._refill(st, pol, self._spacing(st, pol), now)
            # Floored at -2 bursts: a debit is a bill, not a punishment, and an unbounded negative
            # bucket would take hours to climb out of after one redirect-heavy run.
            st['tokens'] = max(-2.0 * pol.burst, float(st.get('tokens') or 0.0) - 1.0)
            st['grants'] = int(st.get('grants') or 0) + 1
        return dest

    # ---- what the server told us ----------------------------------------------------------------
    def note_server_instruction(self, host: str, *, retry_after: Any = None,
                                headers: Any = None) -> dict:
        """THE SERVER TOLD US WHEN TO COME BACK, AND WHAT OUR RATE IS. -> what changed (for the ledger).

        This is where a `Retry-After` stops being a number we printed into a log and starts being a
        CONSTRAINT WE OBEY. It is NOT a strike: an instruction can arrive on every attempt of one
        request, and counting each of them against the breaker would let one stubborn URL convict a
        host. `note_request_outcome` does the scoring, exactly once per logical request.
        """
        host = (host or 'unknown').lower()
        now = time.time()
        ra = parse_retry_after(retry_after, now)
        changed: dict[str, Any] = {}
        with self._locked(host) as st:
            # 1. not_before — the server NAMED A TIME. It is DURABLE and it outlives this process.
            if ra is not None and ra > 0:
                nb = max(float(st.get('not_before') or 0.0), now + ra)
                st['not_before'] = nb
                changed['not_before_in_s'] = round(nb - now, 3)
                changed['retry_after_parsed_s'] = round(ra, 3)

            # 2. an observed rate limit MAY ONLY SLOW US DOWN (Sol §7). Never speed us up.
            spacing = _spacing_from_headers(headers)
            if spacing is not None and spacing > float(st.get('dyn_min_spacing_s') or 0.0):
                st['dyn_min_spacing_s'] = spacing
                changed['dyn_min_spacing_s'] = round(spacing, 3)
        return changed

    def note_request_outcome(self, host: str, http_status: int | None, *,
                             headers: Any = None) -> dict:
        """SCORE ONE **LOGICAL REQUEST** AGAINST THE HOST. Called EXACTLY ONCE per request, at its
        terminal outcome. -> what changed (for the ledger).

        A request that was retried four times and 429'd four times is ONE strike against this host,
        not four. And A CLEAN ANSWER CLEARS THE RECORD — including a 404, because a 404 is the host
        ANSWERING US, and a breaker that counted honest answers as failures would trip on a
        well-behaved index that simply does not have our DOI.
        """
        host = (host or 'unknown').lower()
        pol = self.policy(host)
        now = time.time()
        code = int(http_status or 0)
        changed: dict[str, Any] = {}
        with self._locked(host) as st:
            if headers:
                spacing = _spacing_from_headers(headers)
                if spacing is not None and spacing > float(st.get('dyn_min_spacing_s') or 0.0):
                    st['dyn_min_spacing_s'] = spacing
                    changed['dyn_min_spacing_s'] = round(spacing, 3)

            if code and code not in BREAKER_CODES and code < 500:
                st['failures'] = []                       # they answered. The record is clean.
                if float(st.get('circuit_open_until') or 0) <= now:
                    st['trips'] = 0
                return changed

            if code in BREAKER_CODES or code >= 500:
                fails = [f for f in (st.get('failures') or [])
                         if now - float(f.get('ts') or 0) <= pol.breaker_window_s]
                fails.append({'ts': now, 'code': code})
                st['failures'] = fails
                changed['host_failures_in_window'] = len(fails)
                if (len(fails) >= pol.breaker_threshold
                        and float(st.get('circuit_open_until') or 0) <= now):
                    st['trips'] = int(st.get('trips') or 0) + 1
                    cool = min(3600.0, pol.breaker_cooldown_s * (2 ** (int(st['trips']) - 1)))
                    st['circuit_open_until'] = now + cool
                    st['failures'] = []
                    changed['circuit_opened_for_s'] = round(cool, 1)
                    changed['circuit_trip'] = int(st['trips'])
                    changed['tripped_on_codes'] = sorted({int(f['code']) for f in fails})
        return changed

    def observe_rate_limit(self, host: str, *, min_spacing_s: float | None = None,
                           requests_per_second: float | None = None) -> bool:
        """A documented/observed limit. -> True if it was APPLIED. IT MAY ONLY REDUCE THE RATE."""
        s = min_spacing_s
        if s is None and requests_per_second:
            s = 1.0 / float(requests_per_second)
        if not s or s <= 0:
            return False
        with self._locked(host.lower()) as st:
            if float(s) > float(st.get('dyn_min_spacing_s') or 0.0):
                st['dyn_min_spacing_s'] = float(s)
                return True
        return False

    # ---- introspection (for the tests, the supervisor, and the operator) --------------------------
    def snapshot(self, host: str) -> dict:
        p = self._path(host.lower())
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text() or '{}')
        except Exception:
            return {}

    def circuit_open(self, host: str) -> bool:
        return float(self.snapshot(host).get('circuit_open_until') or 0) > time.time()

    def not_before(self, host: str) -> float:
        return float(self.snapshot(host).get('not_before') or 0)

    def reset(self, host: str) -> None:
        """Operator escape hatch. Used by NOTHING on the retrieval path — a component that could
        clear its own circuit breaker does not have one."""
        p = self._path(host.lower())
        if p.exists():
            p.unlink()


_RL_LIMIT = ('x-ratelimit-limit', 'x-rate-limit-limit', 'ratelimit-limit')
_RL_REMAINING = ('x-ratelimit-remaining', 'ratelimit-remaining')
_RL_RESET = ('x-ratelimit-reset', 'ratelimit-reset')


def _spacing_from_headers(headers: Any) -> float | None:
    """A rate-limit header -> the MINIMUM SPACING it implies. None if it says nothing we understand.

    Crossref sends `X-Rate-Limit-Limit: 50` with `X-Rate-Limit-Interval: 1s`; Zenodo sends
    `X-RateLimit-Limit`/`Remaining`/`Reset`. We read them CONSERVATIVELY: if the host says we have 3
    requests left before a reset 60 seconds away, that is one request per 20 seconds, and we take it.
    """
    if not headers:
        return None

    def h(names) -> str:
        for n in names:
            try:
                v = headers.get(n) or headers.get(n.title()) or headers.get(n.upper())
            except Exception:
                v = None
            if v:
                return str(v)
        return ''

    remaining, reset = h(_RL_REMAINING), h(_RL_RESET)
    if remaining and reset:
        try:
            rem = float(remaining)
            rst = float(reset)
            if rst > 1e6:                     # an epoch timestamp, not a delta
                rst = rst - time.time()
            if rem <= 0 and rst > 0:
                return float(rst)             # nothing left: space by the whole reset window
            if rem > 0 and rst > 0:
                return max(0.0, rst / rem)
        except Exception:
            pass
    limit, interval = h(_RL_LIMIT), h(('x-rate-limit-interval', 'x-ratelimit-interval'))
    if limit:
        try:
            lim = float(limit)
            secs = 1.0
            m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*([smh]?)', interval.strip()) if interval else None
            if m:
                secs = float(m.group(1)) * {'': 1, 's': 1, 'm': 60, 'h': 3600}[m.group(2)]
            if lim > 0:
                return secs / lim
        except Exception:
            pass
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE CONDITIONAL CACHE — exact-ID resolver responses (Sol §7: "cache exact-ID resolver responses")
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class CacheEntry:
    url: str
    etag: str = ''
    last_modified: str = ''
    body_path: str = ''
    content_type: str = ''
    fetched_at: float = 0.0
    http_status: int = 200


class HttpCache:
    """ETag / Last-Modified conditional GETs, on disk, shared across processes.

    An exact-ID resolver query — `unpaywall/v2/10.1257/aer.20160696` — has the same answer today as
    it had this morning. We re-asked it every run, on a host we were being throttled by, to be told
    the same thing. A conditional GET costs the host a 304 and costs us nothing, AND — this is the
    part that matters for a resumable overnight run — a 304 does not spend the paper's retry budget.
    """

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else (Path(STATE_DIR) / 'http_cache')
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, url: str) -> Path:
        return self.root / f'{hashlib.sha256(url.encode()).hexdigest()[:32]}.json'

    def get(self, url: str) -> CacheEntry | None:
        p = self._key(url)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text())
            e = CacheEntry(**d)
            return e if Path(e.body_path).exists() else None
        except Exception:
            return None

    def validators(self, url: str) -> dict[str, str]:
        e = self.get(url)
        if not e:
            return {}
        h = {}
        if e.etag:
            h['If-None-Match'] = e.etag
        if e.last_modified:
            h['If-Modified-Since'] = e.last_modified
        return h

    def body(self, url: str) -> tuple[bytes, str]:
        e = self.get(url)
        if not e:
            raise FileNotFoundError(url)
        return Path(e.body_path).read_bytes(), e.content_type

    def put(self, url: str, raw: bytes, headers: Any, http_status: int = 200) -> None:
        def hv(n):
            try:
                return str(headers.get(n) or '') if headers else ''
            except Exception:
                return ''
        etag, lm = hv('ETag'), hv('Last-Modified')
        if not etag and not lm:
            return                       # nothing to revalidate against — do not pretend we cached it
        bp = self.root / f'{hashlib.sha256(url.encode()).hexdigest()[:32]}.body'
        bp.write_bytes(raw)
        self._key(url).write_text(json.dumps(dict(
            url=url, etag=etag, last_modified=lm, body_path=str(bp),
            content_type=hv('Content-Type'), fetched_at=time.time(), http_status=int(http_status),
        ), sort_keys=True))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ROBOTS — for the OAI lane (Sol §2: "obey Retry-After, robots, resumption tokens, deletion records")
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class RobotsCache:
    """robots.txt per host, cached, fetched THROUGH THE SCHEDULER (it is a request to that host too).

    A robots FETCH FAILURE IS NOT PERMISSION. 404/410 -> allowed (the standard reading: no file, no
    rules). 401/403 -> DISALLOWED (they told us the rules are none of our business). 5xx/timeout ->
    DISALLOWED until the cache expires, because "we could not read the rules" is not "there are no
    rules" — the same shape of error as reading a 429 as an absence.
    """
    TTL_S = 3600.0

    def __init__(self, sched: Scheduler, ua: str = 'POLARIS'):
        self.sched, self.ua = sched, ua
        self.dir = Path(sched.state_dir) / 'robots'
        self.dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, tuple[float, Any]] = {}

    def _fetch(self, host: str, scheme: str) -> tuple[int, str]:
        url = f'{scheme}://{host}/robots.txt'
        g = self.sched.acquire(host)
        if not g.granted:
            return 0, ''                       # we could not even ask. Fails CLOSED below.
        try:
            req = urllib.request.Request(url, headers={'User-Agent': self.ua})
            with urllib.request.urlopen(req, timeout=20) as r:
                return int(getattr(r, 'status', 200) or 200), r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            return int(getattr(e, 'code', 0) or 0), ''
        except Exception:
            return 0, ''
        finally:
            self.sched.release(g)

    def allowed(self, url: str) -> tuple[bool, str]:
        parts = urllib.parse.urlparse(url)
        host, scheme = (parts.netloc or '').lower(), (parts.scheme or 'https')
        now = time.time()
        hit = self._mem.get(host)
        if not hit or now - hit[0] > self.TTL_S:
            code, body = self._fetch(host, scheme)
            if code in (404, 410):
                rp = None                      # no file => no rules => allowed
            elif code == 200 and body:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.splitlines())
            else:
                rp = False                     # 401/403/5xx/unreachable => WE MAY NOT ASSUME YES
            self._mem[host] = (now, rp)
            hit = self._mem[host]
        rp = hit[1]
        if rp is None:
            return True, 'no robots.txt'
        if rp is False:
            return False, 'robots.txt unreadable — we do not assume permission'
        ok = rp.can_fetch(self.ua, url)
        return bool(ok), 'robots.txt allows' if ok else 'robots.txt disallows this path'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# PARALLELISM — ACROSS INDEPENDENT HOSTS. NEVER WITHIN A HOST BEYOND ITS POLICY.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

T = TypeVar('T')
R = TypeVar('R')


def parallel_across_hosts(items: Sequence[T], key: Callable[[T], str],
                          fn: Callable[[T], R], *, max_hosts: int = 8) -> list[tuple[T, R | None, str]]:
    """Run one worker PER HOST. Within a host, items run in sequence.

    Sol §7: "Parallelize across independent hosts, not within a host beyond its policy." The
    scheduler would enforce the per-host limit anyway — but a thread pool that fans 32 requests at
    one host and then makes 31 of them queue is not parallelism, it is 31 threads asleep. Group first.
    """
    groups: dict[str, list[T]] = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    out: list[tuple[T, R | None, str]] = []

    def run_host(host: str) -> list[tuple[T, R | None, str]]:
        res = []
        for it in groups[host]:
            try:
                res.append((it, fn(it), ''))
            except Exception as e:               # an exception is an OBSERVATION, not a conclusion
                res.append((it, None, f'{type(e).__name__}: {e}'))
        return res

    with ThreadPoolExecutor(max_workers=max(1, min(max_hosts, len(groups) or 1))) as ex:
        for chunk in ex.map(run_host, list(groups)):
            out.extend(chunk)
    return out


def batched(items: Iterable[T], size: int) -> Iterator[list[T]]:
    """N ids -> ceil(N/size) requests. The batching primitive behind `pmc_ids.id_converter_batches`."""
    buf: list[T] = []
    for it in items:
        buf.append(it)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


if __name__ == '__main__':
    print(__doc__)
    pols, dflt = load_policies()
    print(f'{len(pols)} host policies from config/source_routes.yaml (default: '
          f'{dflt.min_spacing_s}s, conc {dflt.max_concurrency})\n')
    for h, p in sorted(pols.items()):
        print(f'  {h:34s} spacing={p.min_spacing_s:<5} conc={p.max_concurrency}  <- {p.origin}')
    print('\nInvariants are tested by:  python3 scripts/test_host_scheduler.py')
