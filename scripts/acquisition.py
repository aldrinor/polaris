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

#: THE ONE DURABLE LEDGER. The run orchestrator opens it BEFORE retrieval; every fetcher appends.
LEDGER_PATH = ROOT / 'outputs' / 'event_ledger.jsonl'
#: THE IMMUTABLE BLOB STORE. Content-addressed => a blob can never be overwritten, only re-written
#: identically. There is no "update" operation and no way to ask for one.
BLOB_DIR = ROOT / 'outputs' / 'blobs'

MAILTO = os.environ.get('POLARIS_MAILTO', 'aldrin.or@c-polarbiotech.com')
UA = {'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'}

#: Politeness spacing, PER HOST — we are the ones who got ourselves throttled, and we got throttled by
#: hammering two hosts, not "the network". Backoff is scaled by POLARIS_BACKOFF_SCALE so an adversarial
#: test can force a 429 storm without sleeping for four minutes. It scales SLEEP ONLY: it cannot change
#: an event, a retry count, or an outcome.
SPACING_S = float(os.environ.get('POLARIS_SPACING', '1.1'))
BACKOFF_SCALE = float(os.environ.get('POLARIS_BACKOFF_SCALE', '1.0'))

#: What the transport did. NOT what the world contains — that distinction is the whole module.
RESPONDED       = 'RESPONDED'         # the backend answered with content
NOT_INDEXED     = 'NOT_INDEXED'       # HTTP 404: a fact about THEIR INDEX
THROTTLED       = 'THROTTLED'         # HTTP 429/503: a fact about OUR REQUEST RATE
BLOCKED         = 'BLOCKED'           # HTTP 401/403/402/451: a fact about ENTITLEMENT
TRANSPORT_ERROR = 'TRANSPORT_ERROR'   # timeout / DNS / reset / 5xx: we never got an answer

THROTTLE_CODES = (429, 503)
BLOCK_CODES    = (401, 402, 403, 451)


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

    @property
    def ok(self) -> bool:
        return self.outcome == RESPONDED

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

_HOST_LAST: dict[str, float] = {}
_RID = itertools.count(1)


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
            **obs) -> Response:
        """One logical request. BACKEND_ATTEMPTED before each attempt; EXACTLY ONE of
        RESPONSE_RECEIVED | THROTTLED | BLOCKED at the exception boundary of each attempt.

        THE RETRIES SHARE A `request_id`. That is load-bearing: a 429 that a backoff RESOLVED and a
        429 that we GAVE UP ON are different facts, and the reducer must be able to tell them apart
        without either of them being deleted from the log. Both are here, forever; the reducer reads
        the request's FINAL terminal event.

          exhausted 429s -> the last terminal event is THROTTLED -> BACKEND_FAILED. FOREVER.
          429 then 200   -> the last terminal event is RESPONSE_RECEIVED -> RESPONDED. The 429 is
                            still on disk, because the backoff working is not the same as it never
                            having been throttled.
        """
        rid = f'{adapter}#{next(_RID)}'
        last: Response | None = None
        for attempt in range(1, max(1, tries) + 1):
            self._space(url)
            self.ledger.emit(unit, EventKind.BACKEND_ATTEMPTED, self.actor,
                             adapter=adapter, url=url, request_id=rid, attempt=attempt, **obs)
            try:
                req = urllib.request.Request(url, headers=UA)
                # NOTE: `urllib.request.urlopen` is resolved AT CALL TIME, on purpose. The adversary
                # harness monkeypatches it to force a 429 storm, and a `from ... import urlopen` would
                # bind past the patch and test nothing.
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                    ctype = r.headers.get('Content-Type', '') or ''
                    code = int(getattr(r, 'status', 200) or 200)
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                 http_status=code, content_type=ctype, n_bytes=len(raw))
                return Response(RESPONDED, code, raw, ctype, url, adapter, rid)

            except urllib.error.HTTPError as e:
                code = int(getattr(e, 'code', 0) or 0)

                if code in THROTTLE_CODES:
                    # ** A 429 PERSISTS AS THROTTLED. IT CANNOT BECOME CITATION_ONLY. **
                    self.ledger.emit(unit, EventKind.THROTTLED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                     http_status=code, retry_after=self._retry_after(e))
                    last = Response(THROTTLED, code, b'', '', url, adapter, rid, f'HTTP {code}')
                    if attempt < tries:
                        self._backoff(attempt)
                        continue
                    return last

                if code in BLOCK_CODES:
                    # A fact about ENTITLEMENT. Retrying a paywall is not politeness, it is noise.
                    self.ledger.emit(unit, EventKind.BLOCKED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                     http_status=code)
                    return Response(BLOCKED, code, b'', '', url, adapter, rid, f'HTTP {code}')

                if code == 404:
                    # THE BACKEND ANSWERED. "My index does not have this" is a RESPONSE, and it is a
                    # fact about THEIR INDEX — not about whether the paper is free somewhere else.
                    # (Semantic Scholar 404s the QJE DOI for Autor/Levy/Murnane. NBER WP 8337 exists.)
                    self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                     adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                     http_status=404, n_bytes=0)
                    return Response(NOT_INDEXED, 404, b'', '', url, adapter, rid)

                # 5xx and the rest: they responded, and the response is not an answer.
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                 http_status=code, transport_error=f'HTTP {code}')
                last = Response(TRANSPORT_ERROR, code, b'', '', url, adapter, rid, f'HTTP {code}')
                if code >= 500 and attempt < tries:
                    self._backoff(attempt)
                    continue
                return last

            except Exception as e:
                # A HANG IS NOT A GAP. `transport_error` carries the exception CLASS (a bounded,
                # component-authored word); the message goes under `reason_text`, which the ledger's
                # conclusion guard treats as raw text from the world — because an exception string is
                # free text and could otherwise smuggle "not available" into the log as a conclusion.
                self.ledger.emit(unit, EventKind.RESPONSE_RECEIVED, self.actor,
                                 adapter=adapter, url=url, request_id=rid, attempt=attempt,
                                 transport_error=type(e).__name__, reason_text=str(e)[:200])
                last = Response(TRANSPORT_ERROR, None, b'', '', url, adapter, rid, type(e).__name__)
                if attempt < tries:
                    self._backoff(attempt)
                    continue
                return last

        return last or Response(TRANSPORT_ERROR, None, b'', '', url, adapter, rid, 'no attempt made')

    def get_json(self, unit: str, adapter: str, url: str, **kw) -> tuple[Response, Any | None]:
        r = self.get(unit, adapter, url, **kw)
        return r, r.json()

    # -- 4. CANDIDATE_IDENTIFIED ------------------------------------------------------------------
    def candidate(self, unit: str, adapter: str, url: str, **obs) -> None:
        """An adapter returned a URL. It is a CANDIDATE — not evidence, not a copy of anything yet."""
        self.ledger.emit(unit, EventKind.CANDIDATE_IDENTIFIED, self.actor,
                         adapter=adapter, url=url, **obs)

    # -- 5 & 6. MANIFESTATION_FETCHED, then CONTENT_PROFILE_DERIVED -------------------------------
    def record_manifestation(self, unit: str, *, locator: str, raw: bytes, text: str,
                             adapter: str, requested_title: str = '',
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
    def _space(url: str) -> None:
        host = urllib.parse.urlparse(url).netloc or 'unknown'
        wait = _HOST_LAST.get(host, 0.0) + SPACING_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _HOST_LAST[host] = time.time()

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
