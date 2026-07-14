#!/usr/bin/env python3
"""ACQUISITION — THE ONLY DOOR TO THE NETWORK, AND IT CANNOT CONCLUDE.

    Sol (a)(1): "ACQUISITION EMITS OBSERVATIONS AND MANIFESTATIONS, NEVER STATUSES."

THE FAILURE THIS IS THE STRUCTURAL CURE FOR

  Tonight a forced HTTP 429 on Autor, Levy & Murnane (2003) — whose free copy provably exists, NBER
  Working Paper 8337, in full, forever — was written to disk as `content_status = CITATION_ONLY`.
  CITATION_ONLY is the MINER'S EXCLUSION LABEL. A transient throttle PERMANENTLY DELETED the
  most-cited paper in the literature from our evidence base.

  A FACT ABOUT OUR REQUEST RATE, WRITTEN TO DISK AS A FACT ABOUT THE WORLD.

  The mechanism was three lines long and lived in every fetcher:

      d = jget(url)          # returns None on ANY exception — 429, 404, timeout, DNS, bad JSON
      if not d:              # ...and the caller reads that None as
          return []          # "NO FREE COPY OF THIS PAPER EXISTS"

  `None` is four different worlds — THEIR INDEX, OUR REQUEST RATE, THEIR ENTITLEMENT WALL, and a HANG —
  and every one of them collapsed into the one word the miner obeys.

WHY A GUARD ON THE FETCHERS WOULD NOT HAVE HELPED

  It is not that the fetchers concluded WRONGLY. It is that they concluded AT ALL. So this module does
  not check their conclusions: IT REMOVES THE VOCABULARY. There is no `content_status=` parameter in
  this API. There is no `fulltext_source=`. A fetcher physically cannot say "still paywalled", because
  nothing here accepts the sentence. It may say `http_status=429`, and a REDUCER nobody can bypass
  turns that into THROTTLED -> BACKEND_FAILED — which is not an absence, and never becomes one.

THE EXACT EVENT SEQUENCE, PER REQUESTED WORK (Sol's, verbatim)

    1. ROUTE_PLANNED            in each fetcher's main(), before its adapter loop
    2. BACKEND_ATTEMPTED        immediately before each network request
    3. at the exception boundary, EXACTLY ONE of: RESPONSE_RECEIVED | THROTTLED | BLOCKED
    4. CANDIDATE_IDENTIFIED     when a URL/result is returned
    5. MANIFESTATION_FETCHED    after bytes are obtained — locator, immutable blob id, byte hash,
                                requested identity, adapter observations
    6. CONTENT_PROFILE_DERIVED  only from the shared artifact-profile reducer

  Step 6 takes NO PAYLOAD FROM THE CALLER. `record_manifestation()` computes it by calling
  `event_ledger.observe_text()` itself. A fetcher cannot hand-build a profile, so it cannot inflate
  one — which is how a 535-word cookie banner came to be stamped FULLTEXT with a word count of 8,000.

MANIFESTATIONS ARE IMMUTABLE AND CONTENT-ADDRESSED

  The bytes go to a content-addressed blob store, keyed by sha256 OF THE BYTES. Two fetchers that
  retrieve the same document write the same blob. Two fetchers that retrieve DIFFERENT documents for
  one DOI write TWO blobs, and NEITHER IS DELETED — which is what lets merge_corpus stop holding a
  fight between them and picking the longer one.
"""
from __future__ import annotations

import hashlib
import io
import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_ledger import (  # noqa: E402
    C_ABSTRACT, C_CITATION, C_FULLTEXT, C_NOT_DOC, C_UNREADABLE,
    EventKind, Ledger, derive_content_profile, observe_text,
)
from host_scheduler import (  # noqa: E402  THE PERSISTENT, CROSS-PROCESS POLITENESS GOVERNOR (Sol §7)
    HttpCache, Scheduler, host_of, parse_retry_after,
)

#: THE ONE DURABLE LEDGER. The run orchestrator opens it BEFORE retrieval; every fetcher appends.
LEDGER_PATH = ROOT / 'outputs' / 'event_ledger.jsonl'
#: THE IMMUTABLE BLOB STORE. Content-addressed => a blob can never be overwritten, only re-written
#: identically. There is no "update" operation and no way to ask for one.
BLOB_DIR = ROOT / 'outputs' / 'blobs'

MAILTO = os.environ.get('POLARIS_MAILTO', 'aldrin.or@c-polarbiotech.com')
UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}

#: Backoff is scaled by POLARIS_BACKOFF_SCALE so an adversarial test can force a 429 storm without
#: sleeping for four minutes. It scales SLEEP ONLY: it cannot change an event, a retry count, or an
#: outcome.
BACKOFF_SCALE = float(os.environ.get('POLARIS_BACKOFF_SCALE', '1.0'))

#: `SPACING_S` AND `_HOST_LAST` ARE GONE (Sol V9 §7). They were a module-level dict: they died with the
#: process, they were not shared between our own workers, and they could not remember a refusal. Their
#: replacement is scripts/host_scheduler.py — a per-host token bucket and concurrency limit in a file,
#: under an flock, whose limits come from config/source_routes.yaml and whose `not_before` OUTLIVES THE
#: PROCESS THAT WAS TOLD. Nothing in this module holds a rate any more; it ASKS.
SCHEDULER = Scheduler()
HTTP_CACHE = HttpCache()

#: What the transport did. NOT what the world contains — that distinction is the whole module.
#:
#: SOL §7 SPLIT `BLOCKED` IN TWO, AND THE SPLIT IS NOT COSMETIC. 401 is A FACT ABOUT OUR CREDENTIAL —
#: the CORE key returns 401, and the honest consequence is that THE ROUTE IS UNAVAILABLE AND THE
#: LITERATURE IS UNEXAMINED. 403 is a fact about THAT URL's entitlement, and the honest consequence is
#: to try a repository instead. Collapsed into one word, an expired key of ours read exactly like a
#: publisher's paywall, and the retrieval plan could not tell "fix your key" from "look elsewhere".
RESPONDED      = 'RESPONDED'        # the backend answered with content
NOT_INDEXED    = 'NOT_INDEXED'      # HTTP 404: a fact about THEIR INDEX
THROTTLED      = 'THROTTLED'        # HTTP 429/503: a fact about OUR REQUEST RATE
AUTH_FAILED    = 'AUTH_FAILED'      # HTTP 401: a fact about OUR CREDENTIAL. The route is unavailable.
ACCESS_DENIED  = 'ACCESS_DENIED'    # HTTP 402/403/451: a fact about ENTITLEMENT, for THAT URL
BACKEND_FAILED = 'BACKEND_FAILED'   # timeout / DNS / reset / 5xx, after bounded retry
DEFERRED       = 'DEFERRED'         # OUR OWN GOVERNOR stopped us. We never touched the backend.

#: NOT ONE OF THESE IS AN ABSENCE, AND THERE IS NO SPELLING OF THIS MODULE THAT MAKES ONE. The reducer
#: (event_ledger.derive_backend_outcome) maps every one of them to BACKEND_FAILED / ACCESS_BLOCKED, and
#: `RouteStatus.supports_absence` is False for all of them. Only NOT_INDEXED — a backend that ANSWERED,
#: saying its own index lacks the id — contributes to a scoped absence, and only if every route agrees.
NEVER_AN_ABSENCE = (THROTTLED, AUTH_FAILED, ACCESS_DENIED, BACKEND_FAILED, DEFERRED)

THROTTLE_CODES = (429, 503)
AUTH_CODES     = (401,)
DENIED_CODES   = (402, 403, 451)
BLOCK_CODES    = AUTH_CODES + DENIED_CODES     # both still emit EventKind.BLOCKED on the ledger


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE IMMUTABLE BLOB STORE
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class BlobStore:
    """Content-addressed, write-once. `put` is idempotent BY CONSTRUCTION, not by convention."""

    def __init__(self, root: Path | str | None = None):
        # Resolved AT CALL TIME, not bound as a default at def time — a test that redirects the store
        # to a temp dir must not silently write to the production one.
        self.root = Path(root) if root is not None else Path(BLOB_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / f'{digest}.bin'

    def put(self, raw: bytes) -> tuple[str, str]:
        """-> (blob_id, sha256). Writing the same bytes twice writes the same blob, always."""
        digest = hashlib.sha256(raw).hexdigest()
        p = self._path(digest)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix('.tmp')
            tmp.write_bytes(raw)
            tmp.replace(p)                     # atomic: a half-written blob is never a readable blob
        return f'sha256:{digest}', digest

    def put_text(self, text: str) -> tuple[str, str]:
        return self.put((text or '').encode('utf-8'))

    def get(self, blob_id: str) -> bytes:
        digest = blob_id.split(':', 1)[-1]
        p = self._path(digest)
        if not p.exists():
            raise FileNotFoundError(f'no blob {blob_id!r} — the bytes a manifestation names are gone')
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f'blob {blob_id!r} DOES NOT HASH TO ITS OWN NAME — the store is corrupt')
        return raw

    def get_text(self, blob_id: str) -> str:
        return self.get(blob_id).decode('utf-8', 'ignore')

    def has(self, blob_id: str) -> bool:
        return self._path(blob_id.split(':', 1)[-1]).exists()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE ONE EXTRACTOR — four fetchers had four copies of this, and they disagreed
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_TAG = re.compile(r'<[^>]+>')


def extract_text(raw: bytes, content_type: str = '') -> tuple[str, str]:
    """(text, method). PDF via pdfminer, HTML via tag-stripping. Verbatim: NOTHING is summarised here.

    An extraction FAILURE returns ('', 'pdf_unparseable') — never ''-meaning-"no document exists".
    The caller records the observation; the reducer decides what it means.
    """
    if not raw:
        return '', 'empty_body'
    if 'pdf' in (content_type or '').lower() or raw[:4] == b'%PDF':
        try:
            from pdfminer.high_level import extract_text as _pdf
            return (_pdf(io.BytesIO(raw)) or ''), 'pdfminer'
        except Exception as e:
            return '', f'pdf_unparseable ({type(e).__name__})'
    try:
        html = raw.decode('utf-8', 'ignore')
    except Exception:
        return '', 'undecodable_bytes'
    html = re.sub(r'(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html)
    txt = re.sub(r'&[a-z]+;', ' ', _TAG.sub(' ', html))
    return re.sub(r'\s{2,}', ' ', txt).strip(), 'html_strip'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE TYPED RESPONSE — `None` is four different worlds, and it is not one of them any more
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Response:
    """What came back. `outcome` is an OBSERVATION about the transport, never about the literature.

    THERE IS NO `.absent` AND THERE NEVER WILL BE. The whole disease was one line — `if not d: return
    []` — in which four transport outcomes became a claim about the world. A caller may branch on
    `.ok`; if it wants to know whether a copy EXISTS it must ask a reducer, over the ledger, which
    knows the difference between "they answered, and it is not there" and "we were throttled".
    """
    outcome: str
    http_status: int | None
    raw: bytes
    content_type: str
    url: str
    adapter: str
    request_id: str
    transport_error: str = ''
    #: THE RESPONSE HEADERS, lowercased. Sol V9 §2 requires the repository routes to OBEY the servers'
    #: own rate headers (CORE's tier headers, Zenodo's `X-RateLimit-*`, OpenAIRE's `x-ratelimit-*`) —
    #: and a header you cannot see is a budget you cannot honour. They are OBSERVATIONS, like every
    #: other thing on this record: they say what the server told us about OUR request rate, and nothing
    #: whatever about what the literature contains.
    resp_headers: dict = field(default_factory=dict)
    #: WHERE THE BYTES ACTUALLY CAME FROM after urllib followed the redirects. `url` is where we ASKED.
    #: They differ on every doi.org resolution, and the difference is what `debit_landing` charges.
    final_url: str = ''
    #: A 304 revalidation: we hold these bytes already and the server confirmed they are current.
    from_cache: bool = False
    #: SET ONLY ON `DEFERRED` — OUR OWN GOVERNOR stopped us, and we never touched the backend.
    deferred_until: float = 0.0
    deferral_reason: str = ''

    @property
    def ok(self) -> bool:
        return self.outcome == RESPONDED

    @property
    def is_absence_evidence(self) -> bool:
        """THE ONLY OUTCOME THAT MAY EVER CONTRIBUTE TO "we looked and it is not there."

        A backend ANSWERED, and its answer was "my index does not have this id". Everything else —
        THROTTLED, AUTH_FAILED, ACCESS_DENIED, BACKEND_FAILED, DEFERRED — is a fact about US, OUR
        CREDENTIAL, OUR REQUEST RATE, or THEIR BOX, and this property is False for every one of them.
        It exists so that a caller who wants to reason about absence has exactly one thing to read,
        and cannot get there by testing `not resp.ok`.
        """
        return self.outcome == NOT_INDEXED

    def json(self) -> Any | None:
        """The parsed body, or None — and a None HERE means UNPARSEABLE JSON, nothing else."""
        if not self.ok:
            return None
        try:
            return json.loads(self.raw)
        except Exception:
            return None

    def text(self) -> tuple[str, str]:
        return extract_text(self.raw, self.content_type) if self.ok else ('', 'no_response')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE ACQUIRER
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_RID = itertools.count(1)

#: The response headers that describe OUR BUDGET at a backend. Sol V9 §2 makes obeying them a
#: requirement of the CORE / OpenAIRE / Zenodo routes; §7 makes "dynamic limits may only REDUCE the
#: configured rate" the rule for reading them. Recorded as observations, on the request that saw them.
RATE_HEADERS = ('x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset',
                'x-ratelimit-used', 'retry-after')


def _sched_max_wait() -> float:
    """The longest a single request will WAIT for its turn before it defers (host_scheduler.MAX_WAIT_S).

    Read through a function, not bound at import: an adversary harness that sets POLARIS_MAX_WAIT must
    be able to move it, and a module-level constant would have frozen the value before the test ran.
    """
    import host_scheduler
    return float(host_scheduler.MAX_WAIT_S)


def _headers_dict(h) -> dict:
    """Response headers, lowercased. An absent header object is {} — never an exception, and never a
    silent claim that the server said nothing about our rate."""
    try:
        return {str(k).lower(): str(v) for k, v in h.items()} if h else {}
    except Exception:
        return {}


def _rate_obs(h: dict) -> dict:
    """Just the rate headers, for the ledger. `_scan_for_conclusions` sees only numbers and dates here,
    which is the point: what the server said about our request rate, stated as what it is."""
    return {k.replace('-', '_'): v for k, v in (h or {}).items() if k in RATE_HEADERS}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE LANE RECORDS (Sol V9 §1) — AND THE LINEAGE THAT MAKES ROUTE CREDIT MEAN ANYTHING
# ══════════════════════════════════════════════════════════════════════════════════════════════════
"""
THE ROUTE-CREDIT BUG, IN ONE SENTENCE: a route could be credited with a full text SOMEBODY ELSE FETCHED.

`source_router.classify_discovery_outcome(ledger, unit, adapter)` checked the TRANSPORT outcome per
adapter — correctly — and then asked what we HELD by reducing over EVERY manifestation of the unit. But
a manifestation's `adapter` is the CONTENT HOST it was pulled from (`content:arxiv.org`), not the
resolver that proposed it. So the reduction had no way to tell whose candidate those bytes came from:
if Unpaywall proposed the URL that produced the PDF, and CORE merely answered "RESPONDED" to a search
that found nothing, CORE's discovery outcome read FETCHED. A ladder built on that number measures
nothing — every route inherits the union of every other route's luck, and "unique incremental yield"
becomes an arithmetic identity.

THE FIX IS A CHAIN, NOT A FLAG:

    resolver request  ->  candidate  ->  content request  ->  redirects  ->  manifestation
    (request_id)          (candidate_id)   (request_id, candidate_id)         (candidate_id)

`candidate_id` is minted where the candidate is BORN — inside the adapter that proposed the URL — and it
is carried, unchanged, through the content request and onto the manifestation. A reducer can then ask
the only question that means anything: "which manifestations descend from a candidate THIS ADAPTER
proposed?" A route that proposed nothing gets credited with nothing, however many other routes succeeded.

THE ADAPTER STILL MAY NOT WRITE A CONCLUSION. Sol V9 §1: "The adapter must not write FULLTEXT, THIS_WORK,
VERSION_OF_RECORD, ADMISSIBLE, or an expression edge." Those are REDUCER outputs. `version_hint` and
`license_observation` below are named `_hint` / `_observation` for exactly that reason: they are what a
repository SAID, kept because it is evidence, and they are never read as what a document IS.
"""


@dataclass(frozen=True)
class ResolveContext:
    """WHAT WE ARE LOOKING FOR, and what the contract will and will not accept. Sol V9 §1.

    The router's input is this — STRUCTURED CAPABILITIES — never a lexical guess at the topic.
    """
    work_id: str
    contract_id: str = ''
    identifiers: tuple[str, ...] = ()          # DOI, PMCID, PMID, OAI ID, CELEX, ECLI, NCT...
    title: str = ''
    authors: tuple[str, ...] = ()
    year: int | None = None
    required_artifact_kinds: tuple[str, ...] = ()
    permitted_expression_kinds: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentCandidate:
    """A URL AN ADAPTER PROPOSED. NOT a document, not a version, not evidence — a lead with a lineage.

    `version_hint` and `license_observation` are OBSERVATIONS ONLY, and the suffixes are load-bearing:
    `acceptedVersion` from a repository is a string a repository emitted, and the entire V9 P0 was the
    project of treating that string as a fact about bytes. It is recorded and it concludes NOTHING.
    """
    candidate_id: str
    work_id: str
    discovered_by_route: str                   # the ADAPTER that proposed it. The lineage root.
    resolver_request_id: str = ''              # the request in which it was proposed
    identifier_used: str = ''
    retrieval_url: str = ''
    repository_record_url: str = ''
    media_hint: str = ''
    version_hint: str = ''                     # observation only — NEVER a version decision
    license_observation: str = ''              # observation only
    raw_metadata_blob_id: str = ''
    raw_metadata_hash: str = ''


def make_candidate_id(unit: str, adapter: str, url: str) -> str:
    """DERIVED, never minted. The same adapter proposing the same URL for the same work is the same
    candidate — so a re-run does not fork the lineage, and two adapters proposing the SAME url are two
    DIFFERENT candidates, which is exactly right: they are two routes, and each must be scored alone."""
    h = hashlib.sha256(f'{unit}|{adapter}|{url}'.encode()).hexdigest()
    return f'cand:{h[:16]}'


def open_ledger(path: Path | str | None = None) -> Ledger:
    """THE ONE DURABLE LEDGER, opened AS IT STANDS ON DISK. Every fetcher in a run shares it.

    `Ledger.load` re-reads the history, so a fetcher started after another fetcher finished REDUCES
    OVER WHAT HAPPENED, not over the handful of events it emitted itself.
    """
    return Ledger.load(Path(path) if path else LEDGER_PATH)


def content_host(url: str) -> str:
    """The adapter name for a DOCUMENT fetch. A content host is a backend too: if nber.org 403s us,
    we were BLOCKED BY NBER, and that is a fact worth keeping — distinct from "no copy exists"."""
    try:
        return 'content:' + (urllib.parse.urlparse(url).netloc or 'unknown')
    except Exception:
        return 'content:unknown'


class Acquirer:
    """Emits observations. Cannot emit a status: no method here takes one.

    Every method is a thin, boring wrapper over `Ledger.emit`, and that is the point — the interesting
    part of this class is what it DOES NOT EXPOSE.
    """

    def __init__(self, actor: str, ledger: Ledger | None = None, blobs: BlobStore | None = None):
        self.actor = actor
        self.ledger = ledger if ledger is not None else open_ledger()
        self.blobs = blobs if blobs is not None else BlobStore()

    # -- 1. ROUTE_PLANNED -------------------------------------------------------------------------
    def plan_route(self, unit: str, adapters: Iterable[str], **obs) -> None:
        """`route_complete` will mean EVERY ONE OF THESE HAS A TERMINAL OUTCOME RECORD.

        It must never mean "an adapter was mapped", so this is called BEFORE the loop, with the
        adapters we are ABOUT to try — not after, with the ones that happened to answer.
        """
        self.ledger.emit(unit, EventKind.ROUTE_PLANNED, self.actor,
                         adapters=list(adapters), **obs)

    # -- 2 & 3. THE EXCEPTION BOUNDARY ------------------------------------------------------------
    def get(self, unit: str, adapter: str, url: str, *, tries: int = 4, timeout: int = 30,
            candidate_id: str = '', headers: dict | None = None, cacheable: bool = False,
            max_wait_s: float | None = None, **obs) -> Response:
        """One logical request, THROUGH THE PERSISTENT HOST SCHEDULER. BACKEND_ATTEMPTED before each
        attempt; EXACTLY ONE of RESPONSE_RECEIVED | THROTTLED | BLOCKED at the exception boundary of
        each attempt.

        THE RETRIES SHARE A `request_id`. That is load-bearing: a 429 that a backoff RESOLVED and a
        429 that we GAVE UP ON are different facts, and the reducer must be able to tell them apart
        without either of them being deleted from the log. Both are here, forever; the reducer reads
        the request's FINAL terminal event.

          exhausted 429s -> the last terminal event is THROTTLED -> BACKEND_FAILED. FOREVER.
          429 then 200   -> the last terminal event is RESPONSE_RECEIVED -> RESPONDED. The 429 is
                            still on disk, because the backoff working is not the same as it never
                            having been throttled.

        WHAT SOL §7 ADDED HERE, AND WHY EACH LINE IS A BUG WE SHIPPED

        * THE TOKEN IS TAKEN BEFORE THE ATTEMPT, FROM A FILE. Four worker processes now share one
          bucket per host, so "1.1s spacing" is 1.1s AT THE HOST and not 1.1s per process.
        * `not_before` IS OBEYED. When the server said `Retry-After: 3600` we used to sleep three
          seconds and hammer it again. Now the hour is written down, it survives this process, and
          this request DEFERS instead of retrying into a wall.
        * A DEFERRAL IS `BUDGET_STOPPED`, NEVER A RESPONSE. We did not touch the backend, so we emit
          no BACKEND_ATTEMPTED and no RESPONSE_RECEIVED. `RouteStatus.supports_absence` is False
          whenever a budget stop is on the log — which is exactly the guarantee we need: OUR OWN
          GOVERNOR CAN NEVER MANUFACTURE AN ABSENCE. It is the one failure mode a rate limiter can
          introduce, and the ledger already had the vocabulary to refuse it.
        * A 429 IS ONE STRIKE PER LOGICAL REQUEST, NOT PER ATTEMPT. Every terminal path calls
          `note_request_outcome` exactly once. The breaker measures a HOST; a stubborn URL retried
          four times is not four pieces of evidence about that host — and a clean answer CLEARS it.
        """
        rid = f'{adapter}#{next(_RID)}'
        host = host_of(url)
        last: Response | None = None

        for attempt in range(1, max(1, tries) + 1):
            # ---- THE GOVERNOR. It may refuse, and a refusal is not an answer about the world. ----
            grant = SCHEDULER.acquire(host, max_wait_s=max_wait_s)
            if not grant.granted:
                self.ledger.emit(
                    unit, EventKind.BUDGET_STOPPED, self.actor,
                    adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                    attempt=attempt, host=host, deferral_reason=grant.reason,
                    not_before_in_s=round(max(0.0, grant.not_before - time.time()), 1))
                return Response(DEFERRED, None, b'', '', url, adapter, rid,
                                transport_error=f'deferred:{grant.reason}',
                                deferred_until=grant.not_before, deferral_reason=grant.reason)

            self.ledger.emit(unit, EventKind.BACKEND_ATTEMPTED, self.actor,
                             adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                             attempt=attempt, host=host, **obs)
            try:
                # `headers` carries CREDENTIALS (CORE requires `Authorization: Bearer`). THE SECRET
                # NEVER REACHES THE LEDGER: `_rate_obs` below records only the server's rate headers,
                # and the request headers are not emitted at all. A key in an append-only, committed log
                # is a key you cannot rotate.
                #
                # `cacheable` adds If-None-Match / If-Modified-Since for EXACT-ID RESOLVER queries
                # (Sol §7). The answer to "what are the OA locations of DOI X" does not change between
                # 2am and 3am, and re-asking it over and over on a host that is throttling us spends
                # the budget that the DOCUMENT fetch needed.
                cond = HTTP_CACHE.validators(url) if cacheable else {}
                req = urllib.request.Request(url, headers={**UA, **(headers or {}), **cond})
                # NOTE: `urllib.request.urlopen` is resolved AT CALL TIME, on purpose. The adversary
                # harness monkeypatches it to force a 429 storm, and a `from ... import urlopen` would
                # bind past the patch and test nothing. THERE IS EXACTLY ONE NETWORK CALL IN THIS
                # MODULE and it is this line — so the lane the adversary attacks is the lane that ships.
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                    hdrs = r.headers
                    ctype = hdrs.get('Content-Type', '') or ''
                    code = int(getattr(r, 'status', 200) or 200)
                    rhdr = _headers_dict(hdrs)
                    landed = str(getattr(r, 'url', '') or url)
                # ---- THE REDIRECT CHARGES ITS DESTINATION (Sol §7) --------------------------------
                # urllib followed the hops for us, so we pay for where we LANDED, not where we asked.
                # doi.org is a cheap, generous resolver and www.sciencedirect.com is not; without this
                # line every publisher fetch is laundered through doi.org's budget and the host we
                # actually hammered never appears in our accounting at all.
                SCHEDULER.debit_landing(host, landed)
                if cacheable:
                    HTTP_CACHE.put(url, raw, hdrs, code)
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                 attempt=attempt, http_status=code, content_type=ctype,
                                 n_bytes=len(raw), locator=landed, **_rate_obs(rhdr))
                SCHEDULER.note_request_outcome(host, code, headers=rhdr)   # a clean answer CLEARS
                return Response(RESPONDED, code, raw, ctype, url, adapter, rid, resp_headers=rhdr,
                                final_url=landed)

            except urllib.error.HTTPError as e:
                code = int(getattr(e, 'code', 0) or 0)
                ehdr = _headers_dict(getattr(e, 'headers', None))

                if code == 304 and cacheable:
                    # NOT MODIFIED. The bytes we already hold ARE the answer — and this cost the host
                    # a header and cost this paper's retry budget nothing.
                    try:
                        raw, ctype = HTTP_CACHE.body(url)
                        self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                         adapter=adapter, url=url, request_id=rid,
                                         candidate_id=candidate_id, attempt=attempt, http_status=200,
                                         content_type=ctype, n_bytes=len(raw), revalidated_304=True)
                        return Response(RESPONDED, 200, raw, ctype, url, adapter, rid,
                                        resp_headers=ehdr, from_cache=True)
                    except Exception:
                        pass          # the cached body is gone; fall through and fetch it properly

                if code in THROTTLE_CODES:
                    # ** A 429 PERSISTS AS THROTTLED. IT CANNOT BECOME CITATION_ONLY. **
                    ra_raw = self._retry_after(e)
                    ra_s = parse_retry_after(ra_raw)
                    # `retry_after` is ALREADY in `_rate_obs` (it is a rate header). Passing it a second
                    # time as a keyword is a duplicate-kwarg TypeError, and it fired on exactly the
                    # response this whole module exists for: a 429 THAT CARRIES A Retry-After. The
                    # harness's 429s had no headers, so nothing ever saw it. The parsed SECONDS go
                    # beside the raw string — a reader of the ledger should not have to parse RFC 9110.
                    rate = _rate_obs(ehdr)
                    if ra_s is not None:
                        rate['retry_after_parsed_s'] = round(ra_s, 1)
                    self.ledger.emit(unit, EventKind.THROTTLED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                     attempt=attempt, http_status=code, **rate)
                    last = Response(THROTTLED, code, b'', '', url, adapter, rid, f'HTTP {code}',
                                    resp_headers=ehdr)
                    # THE SERVER NAMED A TIME. It is DURABLE, it is written down BEFORE we decide
                    # whether to retry, and the decision is made against THE INSTRUCTION rather than
                    # against a fixed 3*2**n. This is an instruction, not a strike: it is recorded on
                    # every attempt, and it never double-counts against the breaker.
                    SCHEDULER.note_server_instruction(host, retry_after=ra_raw, headers=ehdr)
                    if ra_s is not None and ra_s > (max_wait_s if max_wait_s is not None
                                                    else _sched_max_wait()):
                        # "do not sleep and retry three seconds later when the server requests hours"
                        SCHEDULER.note_request_outcome(host, code, headers=ehdr)
                        return last
                    if attempt < tries:
                        self._backoff(attempt)
                        continue
                    SCHEDULER.note_request_outcome(host, code, headers=ehdr)   # gave up. ONE strike.
                    return last

                if code in BLOCK_CODES:
                    # A fact about ENTITLEMENT. Retrying a paywall is not politeness, it is noise.
                    # 401 is the CORE case Sol V9 §2 names — a rejected credential is a fact about OUR
                    # KEY: the route is UNAVAILABLE and the literature is UNEXAMINED. 403 is a fact
                    # about THAT URL, and the answer to it is a repository, not another publisher hit
                    # ("A publisher URL gets one normal attempt", Sol §3).
                    self.ledger.emit(unit, EventKind.BLOCKED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                     attempt=attempt, http_status=code, **_rate_obs(ehdr))
                    SCHEDULER.note_request_outcome(host, code, headers=ehdr)
                    out = AUTH_FAILED if code in AUTH_CODES else ACCESS_DENIED
                    return Response(out, code, b'', '', url, adapter, rid, f'HTTP {code}',
                                    resp_headers=ehdr)

                if code == 404:
                    # THE BACKEND ANSWERED. "My index does not have this" is a RESPONSE, and it is a
                    # fact about THEIR INDEX — not about whether the paper is free somewhere else.
                    # (Semantic Scholar 404s the QJE DOI for Autor/Levy/Murnane. NBER WP 8337 exists.)
                    self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                     attempt=attempt, http_status=404, n_bytes=0)
                    SCHEDULER.note_request_outcome(host, 404, headers=ehdr)  # they ANSWERED. CLEARS.
                    return Response(NOT_INDEXED, 404, b'', '', url, adapter, rid)

                # 5xx and the rest: they responded, and the response is not an answer.
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                 attempt=attempt, http_status=code, transport_error=f'HTTP {code}',
                                 **_rate_obs(ehdr))
                last = Response(BACKEND_FAILED, code, b'', '', url, adapter, rid, f'HTTP {code}',
                                resp_headers=ehdr)
                if code >= 500 and attempt < tries:
                    self._backoff(attempt)
                    continue
                SCHEDULER.note_request_outcome(host, code, headers=ehdr)
                return last

            except Exception as e:
                # A HANG IS NOT A GAP. `transport_error` carries the exception CLASS (a bounded,
                # component-authored word); the message goes under `reason_text`, which the ledger's
                # conclusion guard treats as raw text from the world — because an exception string is
                # free text and could otherwise smuggle "not available" into the log as a conclusion.
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, candidate_id=candidate_id,
                                 attempt=attempt, transport_error=type(e).__name__,
                                 reason_text=str(e)[:200])
                last = Response(BACKEND_FAILED, None, b'', '', url, adapter, rid, type(e).__name__)
                if attempt < tries:
                    self._backoff(attempt)
                    continue
                SCHEDULER.note_request_outcome(host, 599)   # a hang is a failed request. ONE strike.
                return last

            finally:
                # THE SLOT COMES BACK EVEN IF WE CRASHED IN IT. A concurrency limit whose slots leak
                # on an exception is a concurrency limit that wedges the host at zero after N errors —
                # and the errors are exactly when it matters.
                SCHEDULER.release(grant)

        # EVERY path above scores itself EXACTLY ONCE — that is the invariant, and it is why a request
        # that 429'd four times is ONE piece of evidence that this host does not want us. Scoring it
        # per ATTEMPT would trip a breaker that is supposed to be measuring a HOST on the strength of
        # one stubborn URL. This line is unreachable; it exists so the function has no implicit None.
        return last or Response(BACKEND_FAILED, None, b'', '', url, adapter, rid, 'no attempt made')

    def get_json(self, unit: str, adapter: str, url: str, **kw) -> tuple[Response, Any | None]:
        r = self.get(unit, adapter, url, **kw)
        return r, r.json()

    # -- 4. CANDIDATE_IDENTIFIED ------------------------------------------------------------------
    def candidate(self, unit: str, adapter: str, url: str, *,
                  resolver_request_id: str = '', **obs) -> str:
        """An adapter returned a URL. It is a CANDIDATE — not evidence, not a copy of anything yet.

        RETURNS THE `candidate_id`, AND THE CALLER MUST CARRY IT. That id is the root of the lineage

            resolver request -> candidate -> content request -> redirects -> manifestation

        and it is the ONLY thing that can say WHICH ROUTE a document is owed to. Without it the
        discovery reducer had to guess, and it guessed by reducing over every manifestation of the work —
        so a route that found nothing was credited with a route that found everything. A ladder measured
        with that reducer cannot see incremental yield at all.
        """
        cid = make_candidate_id(unit, adapter, url)
        self.ledger.emit(unit, EventKind.CANDIDATE_IDENTIFIED, self.actor,
                         adapter=adapter, url=url, candidate_id=cid,
                         resolver_request_id=resolver_request_id, **obs)
        return cid

    # -- 5 & 6. MANIFESTATION_FETCHED, then CONTENT_PROFILE_DERIVED -------------------------------
    def record_manifestation(self, unit: str, *, locator: str, raw: bytes, text: str,
                             adapter: str, candidate_id: str = '', requested_title: str = '',
                             requested_authors: Iterable[str] | None = None,
                             requested_doi: str = '', requested_venue: str = '',
                             requested_year: int | None = None, source_type: str = '',
                             extraction_method: str = '', **obs) -> dict:
        """The bytes we hold, pinned to an IMMUTABLE BLOB and its HASH — then profiled by the SHARED
        reducer, which is the only thing allowed to look at content.

        NOTE WHAT THIS SIGNATURE DOES NOT ACCEPT: a content status, a fulltext_source, a word count, a
        `complete` flag, or a profile. The profile is computed HERE, by `observe_text`, from the bytes
        that were just stored. A fetcher cannot hand one in, so a fetcher cannot inflate one — which is
        exactly how `fulltext_words: 8,000` came to sit beside 535 words of cookie banner.
        """
        blob_id, byte_sha = self.blobs.put(raw or b'')
        text_blob_id, text_sha = self.blobs.put_text(text or '')

        self.ledger.emit(
            unit, EventKind.MANIFESTATION_FETCHED, self.actor,
            adapter=adapter,
            # THE LINEAGE (Sol V9 §1). WHICH CANDIDATE, AND THEREFORE WHICH ROUTE, THESE BYTES ARE OWED
            # TO. Empty means UNATTRIBUTED — and an unattributed manifestation credits NO route, which
            # is the honest answer and, importantly, the SAFE default: the old reducer credited EVERY
            # route instead.
            candidate_id=candidate_id or '',
            locator=locator,                 # THE URL THESE BYTES CAME FROM. wp_fetch never recorded
            #                                # it, so `oa_url` (the PUBLISHER's link, left by an
            #                                # earlier fetcher) was the only URL on the row — a locator
            #                                # naming aeaweb.org over the bytes of an NBER working paper.
            blob_id=blob_id, byte_sha256=byte_sha, n_bytes=len(raw or b''),
            text_blob_id=text_blob_id, text_sha256=text_sha,
            extraction_method=extraction_method,
            # THE IDENTITY WE ASKED FOR — kept beside the bytes, so the reducer can ask whether the
            # bytes are the work we requested. (A title search for "Rise of the Machines" returned
            # Yang-Hui He's arXiv paper on theorem-proving, and it was filed under an HR journal
            # article by Parry et al. Nothing on the row could have caught that; the requested identity
            # is what makes it catchable.)
            requested_title=requested_title or '',
            requested_authors=list(requested_authors or []),
            requested_doi=requested_doi or '',
            requested_venue=requested_venue or '',
            requested_year=requested_year,
            source_type=source_type or '',
            **obs)

        # ---- 6. THE SHARED ARTIFACT-PROFILE REDUCER. The caller supplies no part of this. ---------
        self.ledger.emit(unit, EventKind.CONTENT_PROFILE_DERIVED, 'observe_text',
                         **observe_text(text or ''))

        return dict(blob_id=blob_id, byte_sha256=byte_sha,
                    text_blob_id=text_blob_id, text_sha256=text_sha)

    # -- a budget stop IS NOT AN EVIDENCE GAP -----------------------------------------------------
    def budget_stopped(self, unit: str, **obs) -> None:
        self.ledger.emit(unit, EventKind.BUDGET_STOPPED, self.actor, **obs)

    # -- politeness ------------------------------------------------------------------------------
    @staticmethod
    def _retry_after(e: urllib.error.HTTPError) -> str:
        try:
            return str(e.headers.get('Retry-After') or '') if e.headers else ''
        except Exception:
            return ''

    @staticmethod
    def _backoff(attempt: int) -> None:
        d = 3.0 * (2 ** (attempt - 1)) * BACKOFF_SCALE
        if d > 0:
            time.sleep(d)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# WHAT DO WE ALREADY HOLD? — DERIVED from the bytes, never read off a label
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def held_content_class(row: dict) -> tuple[str, dict]:
    """The content class the ROW'S OWN BYTES earn, through the shared reducer.

    THIS REPLACES `row['content_status'] == 'CITATION_ONLY'` AS THE TARGET SELECTOR, and the
    replacement is not cosmetic. Selecting targets by the label meant:

      * deep_fetch NEVER RETRIED the 535-word aeaweb cookie banner, because the label on it said
        FULLTEXT. The label was written by the fetcher that failed to get the paper.
      * wp_fetch NEVER RETRIED the paper whose PDF decoded to pure (cid:NN) glyph codes, for the
        same reason.

    A selector that reads a component's own claim about its own success can only ever confirm it.
    """
    L = Ledger()                                    # scratch, in-memory: this derives, it does not log
    unit = row.get('doi') or row.get('title') or '?'
    text = (row.get('fulltext') or '').strip()
    if text:
        L.emit(unit, EventKind.MANIFESTATION_FETCHED, 'corpus',
               locator=row.get('oa_url') or '',
               requested_title=row.get('title') or '',
               requested_authors=list(row.get('authors') or []),
               source_type=str(row.get('type') or ''))
        L.emit(unit, EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(text))
    return derive_content_profile(L.events(unit))


def holds_usable_document(row: dict) -> bool:
    """Do we hold a COMPLETE document for this row? (not: does a label say so)"""
    return held_content_class(row)[0] == C_FULLTEXT


def holds_nothing(row: dict) -> bool:
    """Do we hold no usable document at all — no bytes, or bytes that are not a document?

    C_NOT_DOC (a cookie banner) and C_UNREADABLE (a PDF whose font never decoded) belong HERE, with
    C_CITATION. Under the old label they were `FULLTEXT` and were never fetched again.
    """
    cls, _ = held_content_class(row)
    if cls in (C_NOT_DOC, C_UNREADABLE):
        return True
    return cls == C_CITATION and not (row.get('abstract') or '').strip()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MERGING EVENT STREAMS — an append-only log is merged by UNION, never by a winner
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _event_identity(d: dict) -> str:
    """What makes two records THE SAME OBSERVATION. Not `seq` — that is local to one log."""
    return json.dumps([d.get('unit'), d.get('kind'), d.get('actor'), round(float(d.get('ts') or 0), 4),
                       d.get('payload')], sort_keys=True)


def merge_ledgers(paths: Iterable[Path | str], out: Path | str) -> tuple[int, int]:
    """Union of append-only logs, re-sequenced. -> (n_events, n_duplicates_dropped).

    Two fetchers running against one file made the LAST WRITER WIN and silently flatten the other's
    work. Two fetchers appending to one LOG cannot: an observation is not a slot to be overwritten,
    it is a record that happened. The only merge an append-only log admits is a union.
    """
    seen: set[str] = set()
    rows: list[dict] = []
    dupes = 0
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            key = _event_identity(d)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            rows.append(d)
    rows.sort(key=lambda d: (float(d.get('ts') or 0), int(d.get('seq') or 0)))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as fh:
        for i, d in enumerate(rows, 1):
            d['seq'] = i                            # re-sequenced: seq is an ORDER, not an identity
            fh.write(json.dumps(d, sort_keys=True) + '\n')
    return len(rows), dupes


def manifestations_of(ledger: Ledger, unit: str) -> list[dict]:
    """Every distinct set of bytes we have EVER held for this work, newest last. NOTHING IS DELETED.

    Deduped on `text_sha256` — the content address. Fetching the same document twice is one
    manifestation; fetching two DIFFERENT documents for one DOI is two, and the graph keeps both,
    because "which of these is the paper" is a question for a reducer with evidence, not for whichever
    fetcher wrote the file last.
    """
    out: dict[str, dict] = {}
    for e in ledger.events(unit, EventKind.MANIFESTATION_FETCHED):
        if 'derived_by' in e.payload:
            continue
        h = e.payload.get('text_sha256') or e.payload.get('byte_sha256')
        if not h:
            continue
        out[h] = {**e.payload, 'seq': e.seq, 'actor': e.actor}
    return list(out.values())


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE EVIDENCE SELECTION REDUCER — which of the bytes we hold is THE DOCUMENT?
#
# THE OLD ANSWER WAS "THE LONGEST ONE" (merge_corpus.py:47-54, and a `if len(t.split()) >= 500: break`
# in every fetcher). Length is not a property that distinguishes a paper from a cookie banner: the
# aeaweb.org landing page for Autor (2015) is 535 words and the ORA landing page for Frey & Osborne is
# 548, and BOTH of them beat a real 400-word abstract on length while being no document at all.
#
# The answer here is: the one the SHARED REDUCER says is a complete, finding-bearing document — and
# among those, the most AUTHORITATIVE VERSION, which is a question about peer review, not about size.
# Length breaks ties only between documents already agreed to be the same kind of thing.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: How much authority a version carries. `journal_version` outranks `working_paper` because PEER REVIEW
#: CHANGES NUMBERS — Acemoglu-Restrepo robots-and-jobs is 0.37pp in NBER WP 23285 and 0.2pp in the
#: published JPE. It is not a preference. They are different documents with different numbers in them.
_VERSION_AUTHORITY = {
    'journal_version': 6, 'official_text': 6, 'registry_record': 6,
    'proceedings_version': 5, 'accepted_manuscript': 4,
    'working_paper': 3, 'preprint': 2, 'unknown': 1,
}

#: The content classes that can be a document at all, best first.
_CLASS_RANK = {C_FULLTEXT: 3, C_ABSTRACT: 2, C_CITATION: 1, C_NOT_DOC: 0, C_UNREADABLE: 0}


def classify_manifestation(m: dict, blobs: BlobStore) -> dict:
    """Run ONE manifestation's bytes back through the shared reducer. Concludes nothing on its own."""
    from provenance import derive_expression_kind      # local: provenance imports are not free

    text = blobs.get_text(m['text_blob_id']) if m.get('text_blob_id') else ''
    L = Ledger()
    L.emit('m', EventKind.MANIFESTATION_FETCHED, 'select', **{
        k: v for k, v in m.items()
        if k in ('locator', 'requested_title', 'requested_authors', 'source_type', 'adapter')})
    L.emit('m', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(text))
    cls, info = derive_content_profile(L.events('m'))
    ekind, ebasis = derive_expression_kind(text)
    return dict(
        manifestation=m, text=text, content_class=cls, artifact_kind=info.get('artifact_kind'),
        is_complete=bool(info.get('complete')), expression_kind=ekind, expression_basis=ebasis,
        readable_words=info.get('readable_word_count', 0) or 0,
        basis=info.get('reason', ''),
        rank=(_CLASS_RANK.get(cls, 0), _VERSION_AUTHORITY.get(ekind, 0),
              info.get('readable_word_count', 0) or 0))


def select_evidence(ledger: Ledger, unit: str, blobs: BlobStore | None = None) -> dict | None:
    """Which manifestation is THE DOCUMENT for this work? -> the winner, with its basis. Or None.

    EVERY CANDIDATE SURVIVES THIS CALL. Selection is a VIEW, not a deletion: the losers keep their
    blobs, their hashes and their events, and the provenance graph carries every one of them. "Which
    of these is the paper" is a question a reducer answers with evidence, and it is allowed to be
    answered differently tomorrow, on the same bytes, by a better reducer.
    """
    blobs = blobs or BlobStore()
    cands = [classify_manifestation(m, blobs) for m in manifestations_of(ledger, unit)]
    if not cands:
        return None
    return max(cands, key=lambda c: c['rank'])


if __name__ == '__main__':
    print(__doc__)
    print('This module is a library. Its invariants are tested by:  '
          'python3 scripts/test_acquisition_observes.py')
