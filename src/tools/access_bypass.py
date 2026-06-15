"""
Access Bypass Mechanisms (Research Access)
===========================================
Provides research access through multiple channels.

ETHICAL GUIDELINES:
- Only use for legitimate research purposes
- Respect rate limits and fair use policies
- Prefer legal open access when available
- Document all access methods used

Supports:
- Crawl4AI (free, local Playwright-based markdown extraction)
- Jina Reader (primary markdown extraction)
- Firecrawl (secondary markdown extraction)
- robots.txt bypass (for research indexing)
- Paywall detection and alternatives
- Archive.org fallback
- Institutional proxy support
"""

import asyncio
import logging
import os
import re
import sys
import threading
import time as _time_module
import weakref
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _safe_log_str(text: str, max_len: int = 200) -> str:
    """Sanitize text for Windows console logging (cp1252 safe).

    Unicode chars like arrows, Greek letters, and math symbols cause
    UnicodeEncodeError on Windows cp1252 console handler. This replaces
    non-encodable chars with '?' before logging.
    """
    truncated = text[:max_len]
    try:
        truncated.encode("cp1252")
        return truncated
    except (UnicodeEncodeError, UnicodeDecodeError):
        return truncated.encode("ascii", errors="replace").decode("ascii")

# FIX-BR: Suppress Brotli Accept-Encoding to prevent decompression failures.
# aiohttp advertises `br` (Brotli) by default but cannot decode it without the
# `brotli` package installed, causing 100% failure rate on servers that honour it.
# Explicitly request only gzip/deflate across ALL aiohttp sessions.
_NO_BROTLI_HEADERS = {"Accept-Encoding": "gzip, deflate"}

# FIX-JINA: Jina concurrency semaphore (initialized lazily in _try_jina_reader)
_jina_semaphore: "asyncio.Semaphore | None" = None

# RC-9: Circuit breaker for fetch providers.
# After N consecutive failures, skip the provider for a cooldown period.
_jina_consecutive_failures: int = 0
_jina_circuit_open_until: float = 0.0
_firecrawl_consecutive_failures: int = 0
_firecrawl_circuit_open_until: float = 0.0
# I-fetch-004 (#1185): circuit breaker for the PAID Zyte fallback. Mirrors the
# firecrawl/jina breaker so a Zyte outage cannot fire N doomed PAID calls on a
# ~1000-URL run. Shares the same threshold/cooldown constants below.
_zyte_consecutive_failures: int = 0
_zyte_circuit_open_until: float = 0.0
# FIX-G: Raised defaults — threshold 5→8, cooldown 60→120s for transient tolerance
_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("PG_CIRCUIT_BREAKER_THRESHOLD", "8"))
_CIRCUIT_BREAKER_COOLDOWN = float(os.getenv("PG_CIRCUIT_BREAKER_COOLDOWN", "120.0"))

# I-fetch-004 (#1185): Zyte paid-fallback telemetry + tunables (LAW VI — no
# hard-coded thresholds; every knob is env-overridable). These counters are
# separate from the circuit-breaker failure counter above: attempts/successes
# track usage, the breaker tracks consecutive failures.
_zyte_fallback_attempts: int = 0
_zyte_fallback_success: int = 0
# Per-call HTTP timeout for both the cheap (httpResponseBody) and escalated
# (browserHtml) Zyte requests.
_ZYTE_TIMEOUT = float(os.getenv("PG_ZYTE_TIMEOUT", "60.0"))
# Minimum usable-content length. Shared by the escalation trigger (a cheap
# result shorter than this escalates to browserHtml) and the final success
# gate (content shorter than this is rejected). Mirrors the 500-char floor used
# by the PDF/crawl4ai paths.
_ZYTE_MIN_CONTENT_CHARS = int(os.getenv("PG_ZYTE_MIN_CONTENT_CHARS", "500"))
# Zyte API endpoint (override only for testing against a mock server).
_ZYTE_API_ENDPOINT = os.getenv("PG_ZYTE_API_ENDPOINT", "https://api.zyte.com/v1/extract")

# F14 (GH #1245 / D9, D10): paywalled-publisher hosts. The free fetch chain
# (Crawl4AI/Jina/Firecrawl) returns a short abstract SHELL for these hosts; they
# are routed to Zyte FIRST when PG_ZYTE_PAYWALL_FIRST=1 and a key is present, and
# a LOUD warning fires when the key is absent (the Zyte fallback is otherwise a
# silent no-op). Env-extendable via PG_PAYWALL_PUBLISHER_HOSTS (comma-sep,
# additive). Never a hard DROP — only a routing + loud-warning signal.
_PAYWALL_PUBLISHER_HOSTS = (
    "sciencedirect.com",
    "elsevier.com",
    "linkinghub.elsevier.com",
    "onlinelibrary.wiley.com",
    "link.springer.com",
    "nature.com",
    "tandfonline.com",
    "journals.sagepub.com",
    "academic.oup.com",
    "nejm.org",
    "thelancet.com",
    "jamanetwork.com",
    "bmj.com",
    "cell.com",
    "ahajournals.org",
    "annualreviews.org",
)


def _is_paywall_publisher_host(url: str) -> bool:
    """F14: True iff the URL host is a known paywalled publisher (substring
    match on the lowercased netloc; default list + env-additive). Pure, no
    network."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse as _urlparse
        netloc = (_urlparse(url).netloc or "").lower()
    except Exception:
        return False
    if not netloc:
        return False
    hosts = list(_PAYWALL_PUBLISHER_HOSTS)
    extra = os.getenv("PG_PAYWALL_PUBLISHER_HOSTS", "").strip()
    if extra:
        hosts.extend(h.strip().lower() for h in extra.split(",") if h.strip())
    return any(h in netloc for h in hosts)

# ---------------------------------------------------------------------------
# Crawl4AI availability flag (set on first import attempt)
# ---------------------------------------------------------------------------
_crawl4ai_available: "bool | None" = None

# ---------------------------------------------------------------------------
# FIX-EPIPE: Crawl4AI circuit breaker for subprocess crashes.
# After consecutive subprocess crashes (EPIPE, BrokenPipeError, OSError),
# skip crawl4ai entirely for a cooldown period to avoid cascading failures
# from a broken Playwright installation or dead browser process.
# ---------------------------------------------------------------------------
_crawl4ai_consecutive_failures: int = 0
_crawl4ai_circuit_open_until: float = 0.0
# I-fetch-002 (#1168): raise 3->6 so a couple of TRANSIENT subprocess crashes (EPIPE under concurrent
# load) do not trip the breaker and disable crawl4ai for the whole run. Pairs with the new concurrency
# semaphore below — fewer concurrent browsers means fewer crashes in the first place.
_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = int(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")
)
_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN", "120.0")
)

# I-fetch-002 (#1168): crawl4ai launches a Playwright browser subprocess PER URL; under the ~1000-URL
# benchmark fan-out, many concurrent browsers exhaust the OS and crash (EPIPE), which then trips the
# circuit breaker and disables crawl4ai run-wide. Bound the number of concurrently-LIVE browsers with a
# semaphore (mirrors the PG_JINA_CONCURRENCY=2 pattern). Lazy-init so it binds to the running loop.
_crawl4ai_semaphore: "asyncio.Semaphore | None" = None

# I-pipe-002 (#1227): per-running-loop crawl4ai concurrency gates.
#
# THE BUG (old global path below): `_crawl4ai_semaphore` was a SINGLE module-global
# `asyncio.Semaphore`. `live_retriever._fetch_content` runs each bypass fetch on a fresh
# daemon thread with its OWN `asyncio.run` loop. An `asyncio.Semaphore` binds (on 3.11
# via `_LoopBoundMixin`, lazily on FIRST acquire) to the loop that first acquired it. The
# first worker thread's loop wins the binding; EVERY OTHER worker thread then hits
# `RuntimeError: <Semaphore> is bound to a different event loop` inside `async with`,
# crashing the fetch -> EPIPE -> ~159 distinct JS-rendered journal sources (Oxford/Cambridge)
# never fetched (553 EPIPE in the forensic).
#
# THE FIX (default, kill-switch): keep ONE `asyncio.Semaphore` PER running loop, looked up
# inside the async context by the loop OBJECT. A `weakref.WeakKeyDictionary` keyed by the
# loop (NOT a plain dict keyed by `id(loop)`):
#   - auto-evicts the entry when the worker's loop is GC'd (no per-fetch leak over 1000 URLs),
#   - is immune to `id()` address-recycling: a closed loop whose address is reused would, with
#     an id-keyed dict, hand a NEW loop the dead loop's semaphore -> the exact RuntimeError
#     we are fixing, now intermittent. Keying by the live object cannot alias.
# A `threading.Lock` guards the dict (WeakKeyDictionary is not safe under concurrent inserts +
# weakref-removal callbacks).
#
# This is a PURE-RELIABILITY kill-switch (default-ON correct fix). It does NOT change WHICH urls
# are fetched, the concurrency VALUE (still PG_CRAWL4AI_CONCURRENCY), or any verification gate —
# only that already-selected fetches stop crashing cross-loop. Each worker loop runs ~1 crawl4ai
# call, so the per-loop value (2) is never contended: the gate never BLOCKS, it just stops the
# crash. Setting PG_CRAWL4AI_PERLOOP_SEMAPHORE=0 reverts to the old single-global behavior.
PG_CRAWL4AI_PERLOOP_SEMAPHORE_ENV = "PG_CRAWL4AI_PERLOOP_SEMAPHORE"
_crawl4ai_perloop_semaphores: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)
_crawl4ai_perloop_lock = threading.Lock()


def _crawl4ai_perloop_enabled() -> bool:
    """I-pipe-002 (#1227): per-loop semaphore is ON unless PG_CRAWL4AI_PERLOOP_SEMAPHORE=0.

    Default-ON is the sanctioned kill-switch (pure-reliability correct fix); '0' reverts to
    the old loop-bound module-global that crashed on every worker thread but the first."""
    return os.getenv(PG_CRAWL4AI_PERLOOP_SEMAPHORE_ENV, "1").strip() != "0"


def _crawl4ai_concurrency() -> int:
    """Concurrency ceiling for crawl4ai browsers. Default 2 (env PG_CRAWL4AI_CONCURRENCY).
    A malformed/<=0 value falls back to 2 so a bad knob never disables the bound."""
    raw = os.getenv("PG_CRAWL4AI_CONCURRENCY", "2")
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return 2


def _get_crawl4ai_semaphore() -> "asyncio.Semaphore":
    """I-fetch-002 (#1168) + I-pipe-002 (#1227): crawl4ai browser-concurrency gate.

    MUST be called from inside the running event loop (the `async with` site at the crawl
    region). Default (PG_CRAWL4AI_PERLOOP_SEMAPHORE != '0'): one `asyncio.Semaphore` per
    running loop, keyed by the loop object in a `WeakKeyDictionary` — so each worker thread's
    fresh loop gets a semaphore bound to ITSELF and the `async with` never raises the cross-loop
    `RuntimeError`. Old path (='0'): the single loop-bound module-global (preserved verbatim).
    Default 2 concurrent browsers (env PG_CRAWL4AI_CONCURRENCY)."""
    if not _crawl4ai_perloop_enabled():
        # --- OLD GLOBAL PATH (PG_CRAWL4AI_PERLOOP_SEMAPHORE=0): byte-for-byte the pre-#1227
        # behavior. Binds to the first acquiring loop; crashes on every other worker loop. ---
        global _crawl4ai_semaphore
        if _crawl4ai_semaphore is None:
            _crawl4ai_semaphore = asyncio.Semaphore(
                int(os.getenv("PG_CRAWL4AI_CONCURRENCY", "2"))
            )
        return _crawl4ai_semaphore

    # --- PER-LOOP PATH (default): a semaphore bound to THIS running loop. ---
    loop = asyncio.get_running_loop()
    with _crawl4ai_perloop_lock:
        sem = _crawl4ai_perloop_semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(_crawl4ai_concurrency())
            _crawl4ai_perloop_semaphores[loop] = sem
        return sem


def reset_crawl4ai_semaphore_state() -> None:
    """I-pipe-002 (#1227): reset BOTH crawl4ai semaphore holders (global + per-loop map).
    For test isolation ONLY — not called on the production path (mirrors
    `reset_bypass_leak_state`)."""
    global _crawl4ai_semaphore
    _crawl4ai_semaphore = None
    with _crawl4ai_perloop_lock:
        _crawl4ai_perloop_semaphores.clear()


# ---------------------------------------------------------------------------
# BB5-S02 (#1177): cross-THREAD in-flight bypass-worker bound + leak gauge.
#
# `live_retriever._fetch_content` runs each `AccessBypass.fetch_with_bypass`
# on a fresh daemon thread with its OWN `asyncio.run` loop, joined with a hard
# timeout. On timeout the thread is ABANDONED (it keeps running, holding a live
# Crawl4AI/Playwright browser subprocess mid-`arun`). Under the ~740-URL
# benchmark fan-out, hundreds of abandoned threads + browser subprocesses
# accumulate (the resource-exhaustion / segfault mechanism).
#
# `_get_crawl4ai_semaphore()` cannot bound this: it is lazy-bound to the
# RUNNING loop, and every bypass worker thread has its OWN fresh loop — so it
# only caps browsers WITHIN one thread. A `threading`-level BoundedSemaphore is
# the only primitive that bounds the abandoned-thread FLEET across loops.
#
# Acquire at the TOP of the worker (in `live_retriever`), release in THAT
# worker's `finally` — never in the outer join path (releasing on abandonment
# would over-release; not releasing would leak the slot). Sized BELOW the
# parallel `max_workers` so it creates back-pressure; no deadlock because the
# inner per-backend wall-clocks guarantee every abandoned worker eventually
# terminates and releases its slot.
# ---------------------------------------------------------------------------

# Default ceiling on concurrently-LIVE bypass worker threads (each may hold a
# browser subprocess). Env-overridable. Below the live_retriever parallel
# `max_workers` ceiling (48) so abandoned in-flight workers cannot fan out a
# browser-per-candidate. Named constant (LAW VI — no magic numbers).
_BYPASS_INFLIGHT_DEFAULT_LIMIT = 16
PG_BYPASS_MAX_INFLIGHT_ENV = "PG_BYPASS_MAX_INFLIGHT"

_bypass_inflight_semaphore: "threading.BoundedSemaphore | None" = None
_bypass_inflight_semaphore_lock = threading.Lock()

# BB5-S02 leaked-worker gauge: monotonically-incremented count of bypass worker
# threads that were ABANDONED (outer join timed out while the worker was still
# alive). A non-zero gauge is the auditable signal that orphan browser
# subprocesses may have accumulated. Guarded by its own lock.
_bypass_leaked_worker_count: int = 0
_bypass_leaked_worker_lock = threading.Lock()


def _get_bypass_inflight_semaphore() -> "threading.BoundedSemaphore":
    """BB5-S02 (#1177): lazy-init the cross-thread in-flight bypass-worker
    bound. A `threading.BoundedSemaphore` (NOT asyncio) — it must bound worker
    threads across their independent per-thread event loops.

    Limit from `PG_BYPASS_MAX_INFLIGHT` (positive int), else
    `_BYPASS_INFLIGHT_DEFAULT_LIMIT`. A malformed/<=0 value falls back to the
    default — a bad knob must never disable the bound (which would re-open the
    abandoned-fleet leak)."""
    global _bypass_inflight_semaphore
    if _bypass_inflight_semaphore is None:
        with _bypass_inflight_semaphore_lock:
            if _bypass_inflight_semaphore is None:
                raw = os.getenv(PG_BYPASS_MAX_INFLIGHT_ENV)
                limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
                if raw is not None and raw.strip():
                    try:
                        parsed = int(raw)
                        if parsed > 0:
                            limit = parsed
                    except ValueError:
                        limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
                _bypass_inflight_semaphore = threading.BoundedSemaphore(limit)
    return _bypass_inflight_semaphore


def record_bypass_leaked_worker() -> int:
    """BB5-S02 (#1177): increment + return the leaked-bypass-worker gauge. The
    caller (live_retriever) invokes this when an outer fetch join times out
    while the worker thread is still alive (abandoned → potential orphan
    browser subprocess). Thread-safe; returns the new total for logging."""
    global _bypass_leaked_worker_count
    with _bypass_leaked_worker_lock:
        _bypass_leaked_worker_count += 1
        return _bypass_leaked_worker_count


def bypass_leaked_worker_count() -> int:
    """BB5-S02 (#1177): read the current leaked-bypass-worker gauge (auditable
    orphan-subprocess signal). Thread-safe snapshot."""
    with _bypass_leaked_worker_lock:
        return _bypass_leaked_worker_count


def reset_bypass_leak_state() -> None:
    """BB5-S02 (#1177): reset the leak gauge + in-flight semaphore. For test
    isolation ONLY — not called on the production path."""
    global _bypass_leaked_worker_count, _bypass_inflight_semaphore
    with _bypass_leaked_worker_lock:
        _bypass_leaked_worker_count = 0
    with _bypass_inflight_semaphore_lock:
        _bypass_inflight_semaphore = None


# ---------------------------------------------------------------------------
# BB5-S03 (#1177): SIGSEGV-mitigated shared trafilatura extractor.
#
# `trafilatura.extract` runs libxml2 (a C extension). On a pathological /
# malformed / adversarial document libxml2 can SIGSEGV (drb_76 exit 139) — a
# C-level crash that is NOT a Python exception and CANNOT be caught by
# `except Exception`. A try/except around the call is false confidence.
#
# True containment is a per-page hard-killable subprocess, but that is heavy at
# hundreds of calls/run AND `resource` RLIMIT is Unix-only (no-op on win32).
# So the DEFAULT is lean MITIGATION (not containment): size-bound the HTML and
# prefer the caller's regex fallback for oversized/suspect docs, which never
# enters libxml2 at all. An optional hard-killable subprocess path is gated
# behind `PG_TRAFILATURA_SUBPROCESS=1` (OFF by default).
#
# Lives in access_bypass (NOT live_retriever): live_retriever already imports
# access_bypass, so the reverse import would be circular. Both trafilatura
# sites import this one guarded entrypoint.
# ---------------------------------------------------------------------------

# Upper bound (chars) on HTML handed to libxml2 via trafilatura. A document
# larger than this is treated as suspect/oversized: we skip trafilatura and
# signal the caller to use its regex fallback (which never enters the C
# extension). Env-overridable. Named constant (LAW VI).
_TRAFILATURA_MAX_HTML_CHARS = int(
    os.getenv("PG_TRAFILATURA_MAX_HTML_CHARS", "3000000")
)
PG_TRAFILATURA_SUBPROCESS_ENV = "PG_TRAFILATURA_SUBPROCESS"
# Hard wall-clock for the optional subprocess extractor path (seconds).
_TRAFILATURA_SUBPROCESS_TIMEOUT = float(
    os.getenv("PG_TRAFILATURA_SUBPROCESS_TIMEOUT_SECONDS", "20")
)


def _html_is_extract_safe(html: str) -> bool:
    """BB5-S03 (#1177): cheap pre-validation gate. Returns False for an
    oversized document (over `_TRAFILATURA_MAX_HTML_CHARS`) that should bypass
    libxml2 entirely. Pure size check — no parsing, never itself crashes."""
    if not html:
        return False
    if len(html) > _TRAFILATURA_MAX_HTML_CHARS:
        return False
    return True


def _trafilatura_extract_subprocess(html: str, **kwargs: Any) -> "str | None":
    """BB5-S03 (#1177): run `trafilatura.extract` in a hard-killable child
    process so a libxml2 SIGSEGV takes down the child (exit 139) instead of the
    sweep. Returns the extracted text, or None on timeout/crash/error.

    Gated OFF by default (`PG_TRAFILATURA_SUBPROCESS=1` to enable) — true
    containment is heavy at hundreds of calls/run. Best-effort: any failure
    (spawn error, non-zero exit incl. -11/139 SIGSEGV, timeout) returns None so
    the caller falls back to regex extraction. Never raises."""
    import json
    import subprocess

    payload = json.dumps({"html": html, "kwargs": kwargs})
    code = (
        "import sys, json\n"
        "data = json.loads(sys.stdin.read())\n"
        "import trafilatura\n"
        "out = trafilatura.extract(data['html'], **data['kwargs']) or ''\n"
        "sys.stdout.write(out)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_TRAFILATURA_SUBPROCESS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura subprocess failed (%s) — "
            "regex fallback", type(exc).__name__,
        )
        return None
    if proc.returncode != 0:
        # A negative return code is a signal (e.g. -11 == SIGSEGV / exit 139):
        # the child crashed on a pathological doc and the SWEEP survived.
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura subprocess exited rc=%s "
            "(SIGSEGV-class crash contained) — regex fallback",
            proc.returncode,
        )
        return None
    return proc.stdout or None


def safe_trafilatura_extract(html: str, **kwargs: Any) -> "str | None":
    """BB5-S03 (#1177): the ONE guarded trafilatura entrypoint used by every
    extraction site (live_retriever `_strip_html`, access_bypass
    `_try_crawl4ai`).

    Contract:
      - Returns extracted text (str) on success, or None when extraction is
        unsafe/empty/failed (caller falls back to its own regex path).
      - Honest MITIGATION, not containment, on the default in-process path:
        an oversized/suspect doc skips libxml2 (returns None → regex fallback);
        a SIGSEGV on a doc that passes the size gate is still uncatchable
        in-process. Enable `PG_TRAFILATURA_SUBPROCESS=1` for true containment.
      - Never raises (the C-extension SIGSEGV is the one thing it cannot
        promise to catch on the in-process path — documented, not hidden)."""
    if not _html_is_extract_safe(html):
        return None
    if os.getenv(PG_TRAFILATURA_SUBPROCESS_ENV, "0") == "1":
        return _trafilatura_extract_subprocess(html, **kwargs)
    try:
        import trafilatura  # type: ignore
        return trafilatura.extract(html, **kwargs) or None
    except Exception as exc:  # noqa: BLE001 — Python-level errors only; a
        # libxml2 SIGSEGV is NOT a Python exception and escapes this guard (by
        # design — that is what PG_TRAFILATURA_SUBPROCESS=1 contains).
        logger.debug(
            "[ACCESS] BB5-S03 trafilatura in-process extract error (%s) — "
            "regex fallback", type(exc).__name__,
        )
        return None


# Fields the metadata callers actually consume (src/utils/ingest.py). The
# subprocess door serializes exactly these to JSON and the parent rebuilds a
# lightweight object exposing the same attributes — never the live trafilatura
# Document (it does not survive a process boundary).
_TRAFILATURA_METADATA_FIELDS = ("title", "author", "date", "description")


def _trafilatura_metadata_subprocess(html: str) -> "Any | None":
    """GH #1260: run `trafilatura.extract_metadata` in a hard-killable child so
    a libxml2 SIGSEGV takes down the child (exit 139 / Windows 0xC0000005)
    instead of the sweep. Returns an object exposing the four consumed metadata
    fields, or None on timeout/crash/error. Never raises."""
    import json
    import subprocess
    from types import SimpleNamespace

    payload = json.dumps({"html": html})
    code = (
        "import sys, json\n"
        "data = json.loads(sys.stdin.read())\n"
        "import trafilatura\n"
        "meta = trafilatura.extract_metadata(data['html'])\n"
        "fields = " + repr(list(_TRAFILATURA_METADATA_FIELDS)) + "\n"
        "out = {} if meta is None else {\n"
        "    f: (lambda v: None if v is None else str(v))(getattr(meta, f, None))\n"
        "    for f in fields\n"
        "}\n"
        "sys.stdout.write(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_TRAFILATURA_SUBPROCESS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura metadata subprocess failed (%s) — "
            "skip", type(exc).__name__,
        )
        return None
    if proc.returncode != 0:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura metadata subprocess exited rc=%s "
            "(SIGSEGV-class crash contained) — skip", proc.returncode,
        )
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        fields = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return SimpleNamespace(**{
        f: fields.get(f) for f in _TRAFILATURA_METADATA_FIELDS
    })


def safe_trafilatura_extract_metadata(html: str) -> "Any | None":
    """GH #1260: the ONE guarded `trafilatura.extract_metadata` entrypoint.
    `extract_metadata` enters libxml2 exactly like `extract`, so it carries the
    SAME uncatchable-SIGSEGV surface — it must pass through the SAME size gate
    and the SAME `PG_TRAFILATURA_SUBPROCESS` containment.

    Returns an object exposing `.title/.author/.date/.description` (str or
    None) on success, or None when extraction is unsafe/empty/failed (caller
    falls back to its own BS4 metadata path). Cannot return the live
    trafilatura Document on the subprocess path (it does not cross a process
    boundary); the four consumed fields are preserved on a SimpleNamespace.
    Never raises (the in-process libxml2 SIGSEGV is the one thing it cannot
    promise to catch — that is what PG_TRAFILATURA_SUBPROCESS=1 contains)."""
    if not _html_is_extract_safe(html):
        return None
    if os.getenv(PG_TRAFILATURA_SUBPROCESS_ENV, "0") == "1":
        return _trafilatura_metadata_subprocess(html)
    try:
        import trafilatura  # type: ignore
        return trafilatura.extract_metadata(html)
    except Exception as exc:  # noqa: BLE001 — Python-level errors only; a
        # libxml2 SIGSEGV is NOT a Python exception and escapes this guard (by
        # design — that is what PG_TRAFILATURA_SUBPROCESS=1 contains).
        logger.debug(
            "[ACCESS] BB5-S03 trafilatura in-process metadata error (%s) — "
            "skip", type(exc).__name__,
        )
        return None

# ---------------------------------------------------------------------------
# Firecrawl free-plan hardening: rate limiter + credit tracker
# ---------------------------------------------------------------------------

_firecrawl_last_request_time: float = 0.0
_firecrawl_credits_used: int = 0

# Load config from env (imported at module level for speed)
_FIRECRAWL_MIN_INTERVAL = float(os.getenv("FIRECRAWL_MIN_INTERVAL_SECONDS", "6.0"))
_FIRECRAWL_MONTHLY_QUOTA = int(os.getenv("FIRECRAWL_MONTHLY_QUOTA", "500"))
_FIRECRAWL_WARN_PCT = float(os.getenv("FIRECRAWL_WARN_THRESHOLD_PCT", "0.80"))

# ---------------------------------------------------------------------------
# I-bug-775 (#815): NCBI PMC BioC full-text limiter. Conservative per Codex
# decision — max 1 concurrent + a min-interval (~3 req/s), NOT the API-key 10rps
# allowance (the BioC endpoint is separate from E-Utilities and we do not assume
# it honours the key). Lazy-init the semaphore so it binds to the running loop.
# ---------------------------------------------------------------------------
_ncbi_semaphore: "asyncio.Semaphore | None" = None
_ncbi_last_request_time: float = 0.0
_NCBI_MIN_INTERVAL = float(os.getenv("PG_NCBI_MIN_INTERVAL_SECONDS", "0.34"))  # ~3 req/s
_PMC_BIOC_MIN_FULLTEXT_CHARS = int(os.getenv("PG_PMC_BIOC_MIN_FULLTEXT_CHARS", "1000"))

# BioC passage section_types that are NOT article body (so a doc with ONLY these
# is abstract-only / references-only and must be rejected per Codex guardrail).
_BIOC_NON_BODY_SECTIONS = frozenset({
    "TITLE", "ABSTRACT", "REF", "COMP_INT", "AUTH_CONT", "ACK_FUND",
    "SUPPL", "FIG", "TABLE", "KEYWORD", "ABBR",
})


def _get_ncbi_semaphore() -> "asyncio.Semaphore":
    """Lazy-init the NCBI concurrency gate on the running loop (max 1)."""
    global _ncbi_semaphore
    if _ncbi_semaphore is None:
        _ncbi_semaphore = asyncio.Semaphore(1)
    return _ncbi_semaphore


def _parse_bioc_fulltext(raw: str) -> str:
    """I-bug-775 (#815): extract body full text from a PMC BioC_json response.

    Returns '' (reject) if the response is an error, abstract-only, or
    references-only — Codex guardrail: never accept non-full-text. Accepts only
    when there is an explicit body section (INTRO/METHODS/RESULTS/DISCUSS/CONCL/
    CASE/...) OR a clearly article-sized passage set (>=5 passages, >=3000 chars)
    for OA docs whose passages lack section_type infons.
    """
    import json
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    collections = data if isinstance(data, list) else [data]
    all_parts: list[str] = []
    has_body_section = False
    for coll in collections:
        if not isinstance(coll, dict):
            continue
        for doc in coll.get("documents", []) or []:
            for psg in doc.get("passages", []) or []:
                ptext = (psg.get("text") or "").strip()
                if not ptext:
                    continue
                all_parts.append(ptext)
                infons = psg.get("infons") or {}
                section = str(
                    infons.get("section_type") or infons.get("type") or ""
                ).upper()
                if section and section not in _BIOC_NON_BODY_SECTIONS:
                    has_body_section = True
    if not all_parts:
        return ""
    total_len = sum(len(p) for p in all_parts)
    # Reject abstract/refs/error-only: require a body section OR an article-sized
    # passage set.
    if not has_body_section and not (len(all_parts) >= 5 and total_len >= 3000):
        return ""
    return "\n\n".join(all_parts).strip()


async def _firecrawl_rate_limit() -> None:
    """Enforce minimum interval between Firecrawl requests (free plan: 10 RPM)."""
    global _firecrawl_last_request_time
    now = _time_module.monotonic()
    elapsed = now - _firecrawl_last_request_time
    if elapsed < _FIRECRAWL_MIN_INTERVAL and _firecrawl_last_request_time > 0:
        wait = _FIRECRAWL_MIN_INTERVAL - elapsed
        logger.info(
            "[ACCESS] Firecrawl rate limit: waiting %.1fs (10 RPM free plan)",
            wait,
        )
        await asyncio.sleep(wait)
    _firecrawl_last_request_time = _time_module.monotonic()


def _firecrawl_has_credits() -> bool:
    """Check if monthly Firecrawl credit quota has remaining credits."""
    if _firecrawl_credits_used >= _FIRECRAWL_MONTHLY_QUOTA:
        logger.error(
            "[ACCESS] Firecrawl monthly quota exhausted: %d/%d credits used",
            _firecrawl_credits_used,
            _FIRECRAWL_MONTHLY_QUOTA,
        )
        return False
    return True


def _firecrawl_track_credit() -> None:
    """Increment Firecrawl credit counter and warn at threshold."""
    global _firecrawl_credits_used
    _firecrawl_credits_used += 1
    pct = _firecrawl_credits_used / _FIRECRAWL_MONTHLY_QUOTA
    if pct >= _FIRECRAWL_WARN_PCT:
        logger.warning(
            "[ACCESS] Firecrawl credit warning: %d/%d used (%.0f%% of monthly quota)",
            _firecrawl_credits_used,
            _FIRECRAWL_MONTHLY_QUOTA,
            pct * 100,
        )


@dataclass
class AccessResult:
    """Result from access attempt."""
    url: str
    content: str
    access_method: str
    legal_alternative: Optional[str]
    success: bool
    metadata: Dict[str, Any]


# FIX-045B: Navigation boilerplate patterns to strip from fetched content
_BOILERPLATE_RE = re.compile(
    r"|".join([
        r"\[Skip to [^\]]*\]",           # [Skip to Main Content], [Skip to Navigation]
        r"\[Jump to [^\]]*\]",           # [Jump to Content]
        r"^\s*Menu\s*$",                 # Standalone "Menu" lines
        r"^\s*Navigation\s*$",           # Standalone "Navigation" lines
        r"^\s*Toggle navigation\s*$",    # Mobile nav toggle
        r"^\s*Search\.\.\.\s*$",         # Search placeholder
        r"^\s*Sign [Ii]n\s*$",          # Standalone sign-in links
        r"^\s*Create [Aa]ccount\s*$",   # Standalone create account
        r"^\s*Log [Ii]n\s*$",           # Standalone login
        r"^\s*Subscribe\s*$",            # Standalone subscribe
        r"^\s*Share on .*$",             # Share on Twitter/Facebook/etc.
        r"^\s*Cookie [Pp]olicy\s*$",    # Cookie policy links
    ]),
    re.MULTILINE,
)


def _strip_navigation_boilerplate(content: str) -> str:
    """FIX-045B: Strip navigation boilerplate from fetched content.

    Removes common HTML-to-markdown artifacts like [Skip to Main Content],
    standalone navigation links, and similar boilerplate that degrades
    evidence quality.
    """
    if not content:
        return content
    cleaned = _BOILERPLATE_RE.sub("", content)
    # Remove runs of blank lines left by stripping
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# M-23c: Structural markers for content quality scoring.
# Presence of academic-paper markers indicates full article body
# (vs paywall stub or landing page).
_STRUCTURAL_MARKERS = (
    "abstract", "methods", "results", "conclusion",
    "discussion", "introduction", "background", "references",
    "materials and methods", "statistical analysis",
)

_NUMERIC_TOKEN_RE = re.compile(r"\d+\.\d+|\d+\s*%|\d{3,}|\bp\s*[<=>]\s*0\.\d+\b")


def _score_content_quality(content: str) -> float:
    """Score a fetched-content candidate on quality (0.0 .. ~1.5).

    Combines normalized length, structural-marker hits, and numeric
    density. Fully stripped stubs and paywall shells score low; full
    article bodies with numeric data score high. Used to pick the winner
    when multiple concurrent backends (Crawl4AI, Jina, Trafilatura)
    return successful results — replaces first-success-wins, which let
    Jina stubs beat Crawl4AI full-article fetches.

    This is NOT just length: a long paywall page with repeated
    "subscribe to read" blocks will have no structural markers and low
    numeric density, so it loses to a shorter true article body.
    """
    if not content:
        return 0.0

    length = len(content)
    # 30K chars normalizes to 1.0 — NEJM/Lancet full articles are ~40-70K
    length_norm = min(length / 30000.0, 1.0)

    lower = content.lower()
    marker_hits = sum(1 for m in _STRUCTURAL_MARKERS if m in lower)
    marker_score = min(marker_hits / 6.0, 1.0)

    numeric_count = len(_NUMERIC_TOKEN_RE.findall(content))
    # Numeric tokens per KB of text; cap at 1.0
    density = min(numeric_count / max(length / 1000.0, 1.0) / 5.0, 1.0)

    return 0.5 * length_norm + 0.3 * marker_score + 0.2 * density


def _crawl4ai_failure_result(url: str, error: str) -> AccessResult:
    """Build a standard failure AccessResult for crawl4ai.

    FIX-EPIPE: Extracted to reduce duplication across the many except
    branches in _try_crawl4ai.
    """
    return AccessResult(
        url=url,
        content="",
        access_method="crawl4ai",
        legal_alternative=None,
        success=False,
        metadata={"error": error[:200]},
    )


def _crawl4ai_track_failure() -> None:
    """FIX-EPIPE: Increment crawl4ai failure counter and open circuit breaker
    if threshold is reached. Extracted to avoid duplicating the circuit
    breaker logic in every except branch."""
    global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until
    _crawl4ai_consecutive_failures += 1
    if _crawl4ai_consecutive_failures >= _CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD:
        _crawl4ai_circuit_open_until = (
            _time_module.time() + _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN
        )
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPENED "
            "after %d consecutive failures (cooldown %.0fs)",
            _crawl4ai_consecutive_failures,
            _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN,
        )


async def _safe_close_crawler(crawler: Any, url: str) -> None:
    """FIX-EPIPE: Safely close a crawl4ai AsyncWebCrawler instance.

    When the Playwright browser subprocess dies (EPIPE on websocket close),
    calling __aexit__ on the crawler will attempt to close the dead socket
    and raise BrokenPipeError. This function catches ALL exceptions from
    __aexit__ to prevent the cleanup from killing the server.

    Args:
        crawler: The AsyncWebCrawler instance to close.
        url: The URL being fetched (for logging only).
    """
    if crawler is None:
        return
    try:
        await crawler.__aexit__(None, None, None)
    except (BrokenPipeError, ConnectionError, OSError) as exit_err:
        # PRIMARY CRASH VECTOR: Browser subprocess died, socket is broken.
        # This is expected and non-fatal -- the crawl result (if any) is
        # already captured.
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup pipe "
            "error for %s (non-fatal, server protected): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )
    except asyncio.CancelledError:
        # Task cancellation during cleanup -- non-fatal.
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "cancelled for %s (non-fatal)",
            _safe_log_str(url, 60),
        )
    except Exception as exit_err:
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "exception for %s (non-fatal): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )
    except BaseException as exit_err:
        # Even GeneratorExit or exotic BaseException subclasses from
        # native Playwright extensions must not kill the server.
        if isinstance(exit_err, (KeyboardInterrupt, SystemExit)):
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
                "interrupted for %s -- re-raising",
                _safe_log_str(url, 60),
            )
            raise
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "BaseException for %s (non-fatal, server protected): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )


# ---------------------------------------------------------------------------
# I-bug-114 (#551): per-backend hard wall-clock bound for the concurrent fetch
# fan-out. A single backend wedged in a Playwright op must not freeze the whole
# `asyncio.gather`. `_bounded_backend` returns within PG_BACKEND_FETCH_TIMEOUT
# + PG_BACKEND_CLEANUP_GRACE regardless of backend state — it uses
# `asyncio.wait` (which returns after its timeout unconditionally) and never
# `asyncio.wait_for` (which would await the cancelled coroutine's cleanup).
# The post-artifacts asyncio.run-teardown residual is tracked in #552.
# ---------------------------------------------------------------------------

# Strong refs to backend tasks abandoned after the cancel-grace window — kept
# so they are not GC-warned; the done-callback also retrieves any exception.
_DETACHED_BACKEND_TASKS: "set[asyncio.Task]" = set()


def _backend_fetch_timeout() -> float:
    """Per-backend in-flight wall-clock ceiling (seconds)."""
    try:
        return float(os.getenv("PG_BACKEND_FETCH_TIMEOUT", "60.0"))
    except ValueError:
        return 60.0


def _backend_cleanup_grace() -> float:
    """Bounded grace window for a cancelled backend's cleanup (seconds)."""
    try:
        return float(os.getenv("PG_BACKEND_CLEANUP_GRACE", "10.0"))
    except ValueError:
        return 10.0


def _drain_detached(task: "asyncio.Task") -> None:
    """Done-callback for a detached backend task: drop the strong ref and
    retrieve any exception so asyncio does not log 'exception never retrieved'.
    """
    _DETACHED_BACKEND_TASKS.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:  # noqa: BLE001 — exception retrieval is best-effort
            pass


def _force_drop_detached_task(task: "asyncio.Task") -> None:
    """I-cd-032 (#632): forcibly remove a wedged detached task from the
    main asyncio loop's await-list at teardown.

    `asyncio.run`'s built-in shutdown calls `_cancel_all_tasks` which
    `await`s every still-pending task. If a detached backend ignores
    cancellation, that await is unbounded.

    Mitigation: close the task's underlying coroutine via
    `_coro.close()` — this raises GeneratorExit in the coroutine,
    cleanup runs synchronously, and the task is finalized as cancelled
    so `_cancel_all_tasks` does not have to await it.

    Best-effort: if `_coro` is not accessible OR `close()` itself blocks
    (it shouldn't — close just raises GeneratorExit into the frame), the
    fallback path drops the strong reference and lets asyncio teardown
    proceed with the standard cancellation + await behavior.

    Called by an `asyncio.run`-teardown hook installed at run start.
    """
    if task.done():
        return
    coro = getattr(task, "_coro", None)
    if coro is None:
        return
    try:
        # close() raises GeneratorExit into the coroutine's current
        # suspension point, which runs any finally/except blocks but
        # cannot await anything new (GeneratorExit suppresses yields).
        coro.close()
    except Exception:  # noqa: BLE001 — close() must never raise here
        pass
    _DETACHED_BACKEND_TASKS.discard(task)


def install_teardown_drain_hook(loop: "asyncio.AbstractEventLoop") -> None:
    """I-cd-032 (#632) DEPRECATED — hooking loop.close() runs too late:
    `asyncio.run` calls `_cancel_all_tasks` (which awaits every pending
    task) BEFORE `loop.close()`, so a wedged detached task hangs the
    cancel-all phase. Use `polaris_asyncio_run()` below instead. Kept
    as a thin shim that ALSO patches `_cancel_all_tasks` for callers
    that already use `asyncio.run` directly.
    """
    original_close = loop.close

    def _drain_then_close() -> None:
        for task in list(_DETACHED_BACKEND_TASKS):
            _force_drop_detached_task(task)
        original_close()

    loop.close = _drain_then_close  # type: ignore[method-assign]


def polaris_asyncio_run(coro: Any) -> Any:
    """I-cd-032 (#632): drop-in replacement for `asyncio.run` that
    drains wedged detached backend tasks BEFORE the loop's
    `_cancel_all_tasks` phase awaits them.

    Sequence:
      1. Create a new event loop.
      2. Run the main coroutine to completion (or exception).
      3. **Drain `_DETACHED_BACKEND_TASKS` by force-closing each.** This
         must happen BEFORE `_cancel_all_tasks` so the task is already
         finalized (cancelled) when the standard shutdown iterates it.
      4. Mirror `asyncio.run`'s standard shutdown: cancel all remaining
         tasks, run them until complete, run async generator shutdown,
         shutdown default executor, close the loop.

    Replaces `asyncio.run(...)` at pipeline-A entry (`run_one_query`)
    when the run includes any Playwright-bound fetch backend.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(coro)
        try:
            return loop.run_until_complete(main_task)
        finally:
            # I-cd-032: force-close wedged detached tasks BEFORE the
            # standard cancel-all-tasks step so it has nothing
            # un-cancellable to await.
            for task in list(_DETACHED_BACKEND_TASKS):
                _force_drop_detached_task(task)
            # Mirror asyncio.run's shutdown phases.
            try:
                _polaris_cancel_all_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
                if hasattr(loop, "shutdown_default_executor"):
                    loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                asyncio.set_event_loop(None)
                loop.close()
    except BaseException:
        # Ensure the loop is closed on any exception path.
        if not loop.is_closed():
            loop.close()
        raise


def _polaris_cancel_all_tasks(loop: "asyncio.AbstractEventLoop") -> None:
    """Mirror of stdlib asyncio.runners._cancel_all_tasks but with a
    GENUINE hard wall-clock. Codex iter-2 P0 fix: stdlib
    `asyncio.wait_for(asyncio.gather(...), timeout=2)` does NOT bound
    because gather's child-task cancellation cleanup continues past
    the wait_for's own cancellation. Use `asyncio.wait(..., timeout)`
    instead — it returns `(done, pending)` sets unconditionally at
    the timeout AND does not propagate cancellation to children.

    After the 2s wall, every task still in `pending` is force-closed
    via `_force_drop_detached_task` so the subsequent loop.close()
    has nothing pending to await.
    """
    to_cancel = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()

    async def _wait_with_hard_wall():
        # asyncio.wait returns (done, pending) at timeout — does NOT
        # await child-task cleanup beyond the wall. Defense-in-depth
        # against untracked wedged tasks.
        done, pending = await asyncio.wait(to_cancel, timeout=2.0)
        return done, pending

    try:
        _done, pending = loop.run_until_complete(_wait_with_hard_wall())
    except BaseException:
        # Best-effort — if even our wait helper raises, just force-
        # drop every pending task.
        pending = [t for t in to_cancel if not t.done()]

    for task in pending:
        if not task.done():
            _force_drop_detached_task(task)


def _backend_failure(label: str, url: str, error: str) -> AccessResult:
    """A failure AccessResult for a backend that timed out or errored."""
    return AccessResult(
        url=url,
        content="",
        access_method=label,
        legal_alternative=None,
        success=False,
        metadata={"error": error},
    )


async def _bounded_backend(label: str, coro: Any, url: str) -> AccessResult:
    """Run one fetch-backend coroutine under a hard wall-clock bound.

    Returns within PG_BACKEND_FETCH_TIMEOUT + PG_BACKEND_CLEANUP_GRACE
    regardless of whether `coro` ever finishes — `asyncio.wait` returns after
    its timeout unconditionally (unlike `asyncio.wait_for`, which awaits the
    cancelled coroutine's cleanup). A backend whose cancellation cleanup itself
    exceeds the grace window is detached (post-artifacts teardown — see #552).
    """
    timeout = _backend_fetch_timeout()
    grace = _backend_cleanup_grace()
    task = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        exc = task.exception()
        if exc is not None:
            return _backend_failure(label, url, f"{type(exc).__name__}: {exc}")
        return task.result()
    # Timed out — cancel, then allow a BOUNDED grace window for cleanup.
    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=grace)
    if task in done:
        if not task.cancelled():
            try:
                task.exception()  # retrieve, discard
            except Exception:  # noqa: BLE001
                pass
        logger.warning(
            "[ACCESS] backend %s exceeded %.0fs wall-clock for %s — cancelled",
            label, timeout, _safe_log_str(url, 60),
        )
    else:
        # Cleanup itself exceeded the grace window: detach (ref-kept,
        # exception-drained). Residual asyncio.run-teardown case: #552.
        _DETACHED_BACKEND_TASKS.add(task)
        task.add_done_callback(_drain_detached)
        logger.warning(
            "[ACCESS] backend %s exceeded %.0fs + %.0fs grace for %s — "
            "detached (see #552)", label, timeout, grace, _safe_log_str(url, 60),
        )
    return _backend_failure(label, url, f"backend_timeout_{timeout:.0f}s")


class AccessBypass:
    """
    Research access manager.

    Provides multiple methods to access research content.
    """

    def __init__(
        self,
        respect_robots_txt: bool = False,  # For research indexing
        use_archive_org: bool = True,
        institutional_proxy: Optional[str] = None,
        user_agent: str = "POLARIS Research Bot (academic research)",
    ):
        self.respect_robots = respect_robots_txt
        self.use_archive_org = use_archive_org
        self.proxy = institutional_proxy
        self.user_agent = user_agent

        # Paywall detection patterns.
        # M-23f: Tightened to fix false positives on long article bodies.
        # The old patterns used greedy `.*` across arbitrary spans, which
        # meant a 50K-char NEJM article saying "the authors had full
        # access to the data" (far from any "sign in") would match
        # `sign.*in.*to.*access` because regex `.*` spans ~49K chars.
        # New patterns use `\s+` / `\s*[.:]?\s*` for tight token adjacency
        # and word boundaries. Length-gating in `_detect_paywall`
        # further protects long article bodies from the loosest patterns.
        self.paywall_patterns_strict = [
            # These fire on ANY content length — extremely specific
            r"\bpaywall\b",
            r"\bpremium\s+content\b",
            r"\bunlock\s+(the\s+)?full\s+article\b",
            r"\bthis\s+article\s+is\s+available\s+to\s+subscribers\b",
            r"\blog\s+in\s+to\s+read\s+this\s+article\b",
            r"\bsubscribe\s+to\s+read\s+the\s+full\s+article\b",
        ]
        self.paywall_patterns_short_only = [
            # These fire ONLY when content is short (<2K chars) — the
            # bare phrase "members only" or "sign in to access" in a
            # 50K article body is almost always incidental.
            r"\bsubscribe\s+to\s+read\b",
            r"\bsign\s+in\s+to\s+access\b",
            r"\bpurchase\s+(this\s+)?article\b",
            r"\bmembers\s+only\b",
        ]
        # Back-compat: tests or callers referencing .paywall_patterns get
        # the strict-always list (the safer set).
        self.paywall_patterns = self.paywall_patterns_strict

    async def fetch_with_bypass(
        self,
        url: str,
        prefer_legal: bool = True,
    ) -> AccessResult:
        """
        Fetch content with bypass mechanisms.

        FIX-QM2: Crawl4AI, Jina and Firecrawl run concurrently -- first
        success wins.  Crawl4AI is checked first (free, local, no API credits).

        Fallback cascade (if concurrent fetch fails):
        1. Direct HTTP with Accept: text/markdown
        2. Unpaywall (legal open access)
        3. Archive.org (historical)
        4. Institutional proxy
        5. Sci-Hub (last resort for academic papers)
        """
        # PL: Skip S2 landing pages — they're metadata, not content.
        # S2 bulk search returns paper IDs that are 404 via individual API.
        # S2's value is the search metadata (title, abstract, DOI), not the landing page.
        if "semanticscholar.org/paper/" in url:
            logger.debug("[ACCESS] PL: Skipping S2 landing page: %s", url[:60])
            return AccessResult(
                url=url, content="", access_method="skipped_s2_landing",
                legal_alternative=None, success=False,
                metadata={"reason": "S2 landing pages have no content"},
            )

        # PL: Resolve ScienceDirect PIIs and extract DOIs for Sci-Hub fallback.
        resolved_url, resolved_doi = await self._resolve_academic_url(url)
        if resolved_url and resolved_url != url:
            logger.info("[ACCESS] PL: Resolved %s -> %s", url[:50], resolved_url[:50])
            url = resolved_url

        # I-bug-775 (#815): PMC BioC full-text FIRST. PMC HTML/PDF scraping is
        # flaky (jina 60s timeouts, 111-char crawl4ai stubs); the BioC OA API
        # gives structured full text reliably for the OA Subset. Try it before
        # Unpaywall/PDF/scrapers when the URL already carries a PMCID. Falls
        # through (returns None) on non-OA / error / abstract-only.
        _pmcid = self._extract_pmcid(url)
        if _pmcid:
            _bioc_text = await self._try_pmc_bioc_fulltext(_pmcid)
            if _bioc_text:
                return AccessResult(
                    url=url, content=_bioc_text[:50000], access_method="pmc_bioc",
                    legal_alternative=None, success=True,
                    metadata={"pmcid": _pmcid, "source": "pmc_bioc_oa"},
                )

        # M-23a: Unpaywall step 0 — try legal OA before anything else.
        # For DOI-bearing URLs (NEJM, Lancet, JAMA, Elsevier, Springer...)
        # Unpaywall frequently returns a PMC or arXiv OA PDF that is the
        # same article, legally free, full-text. This fixes the "NEJM/Lancet
        # return 400-char paywall stubs" problem upstream of any paywall
        # bypass logic.
        if os.getenv("PG_UNPAYWALL_ENABLED", "1") == "1":
            candidate_doi = self._extract_doi(url) or resolved_doi
            if candidate_doi:
                oa_url = await self._try_unpaywall(candidate_doi)
                if oa_url and oa_url != url:
                    logger.info(
                        "[ACCESS] M-23a: Swapping %s -> OA %s",
                        url[:60], oa_url[:80],
                    )
                    url = oa_url
                    # I-bug-775 (#815): Unpaywall frequently resolves to a PMC
                    # OA copy (e.g. .../PMCxxxxxxx/pdf/main.pdf). Prefer the BioC
                    # full-text API over scraping that PDF (mode-2: PMC PDF
                    # fetches sometimes returned 54-char stubs).
                    _oa_pmcid = self._extract_pmcid(url)
                    if _oa_pmcid:
                        _oa_bioc = await self._try_pmc_bioc_fulltext(_oa_pmcid)
                        if _oa_bioc:
                            return AccessResult(
                                url=url, content=_oa_bioc[:50000],
                                access_method="pmc_bioc",
                                legal_alternative=None, success=True,
                                metadata={"pmcid": _oa_pmcid,
                                          "source": "pmc_bioc_oa_via_unpaywall"},
                            )

        # FIX-CITE-3/GAP4: Detect PDF URLs and extract text directly.
        # Academic open-access PDFs (from S2 openAccessPdf) need PDF parsing,
        # not HTML scraping. This gives the analyzer full paper content with
        # forest plots, I² values, GRADE ratings — the detail Gemini captures.
        if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
            try:
                pdf_text = await self._extract_pdf_text(url)
                if pdf_text and len(pdf_text) > 500:
                    logger.info(
                        "[ACCESS] FIX-GAP4: PDF text extracted for %s (%d chars)",
                        url[:60], len(pdf_text),
                    )
                    return AccessResult(
                        url=url,
                        content=pdf_text[:50000],  # Cap at 50K chars
                        # FIX-GAP4-KWARG: was `method=`, dataclass field is
                        # `access_method`. The old kwarg triggered TypeError
                        # every successful docling/PyMuPDF extraction, which
                        # was then caught as "PDF extraction failed" and
                        # replaced with a 153-char snippet. Every successful
                        # 10K-50K char PDF extract was being silently discarded.
                        access_method="pdf_extract",
                        legal_alternative=None,
                        success=True,
                        metadata={"content_type": "application/pdf"},
                    )
            except Exception as pdf_exc:
                logger.warning(
                    "[ACCESS] FIX-GAP4: PDF extraction failed for %s: %s — falling back to HTML",
                    url[:60], str(pdf_exc)[:100],
                )

        # F14 (GH #1245 / D9, D10): route paywalled publishers to Zyte FIRST.
        # The free scraper group (Crawl4AI/Jina/Firecrawl) reliably returns a
        # few-hundred-char ABSTRACT SHELL for these hosts, which then gets logged
        # as an "ok" source — a dead fetch masquerading as good content. For a
        # known paywalled-publisher host, try Zyte (the paid browser fetch) FIRST
        # so a REAL body is fetched instead of a shell. This runs AFTER the free
        # LEGAL OA chain (PMC-BioC / Unpaywall / direct PDF) above — a legally
        # free full-text copy always wins over a paid call. Gated by
        # PG_ZYTE_PAYWALL_FIRST (default OFF => byte-identical: the early Zyte
        # attempt never fires). When ON but ZYTE_API_KEY is UNSET, a LOUD warning
        # fires (the Zyte path is otherwise a silent no-op without the key) so a
        # Zyte-blind run on paywalled journals is auditable. Zyte content still
        # flows through the SAME extractor + strict_verify / 4-role gates — no
        # faithfulness gate is bypassed (§-1.3: the only hard gate is untouched).
        if (
            os.getenv("PG_ZYTE_PAYWALL_FIRST", "0") == "1"
            and _is_paywall_publisher_host(url)
        ):
            if os.getenv("ZYTE_API_KEY"):
                logger.info(
                    "[ACCESS] F14: paywalled publisher %s — trying Zyte FIRST "
                    "(before the free scraper group)", url[:60],
                )
                _zyte_first = await self._try_zyte(url)
                if _zyte_first.success:
                    return _zyte_first
            else:
                logger.warning(
                    "[ACCESS] F14: paywalled publisher %s but ZYTE_API_KEY is "
                    "UNSET — Zyte-first routing is a silent no-op; the free "
                    "scraper group will likely return only an abstract shell. "
                    "Set ZYTE_API_KEY to recover full text.", url[:80],
                )

        # FIX-QM2: Run the enabled fetch backends concurrently -- first success wins.
        # Build concurrent task list: Crawl4AI first (free/local), then Jina, then Firecrawl
        concurrent_tasks: list = []
        # GH #1260 (cosmetic): track the backends ACTUALLY queued so the log line
        # names only those (the old unconditional "Crawl4AI+Jina+Firecrawl" lied
        # when PG_CRAWL4AI_ENABLED=0 / Firecrawl had no key/credits).
        _queued_backends: list[str] = []

        # I-bug-114 (#551): every concurrent backend is wrapped in
        # `_bounded_backend` so a single wedged backend (e.g. a Playwright op
        # stuck on an anti-bot interstitial) cannot freeze the gather. Each
        # wrapper returns an AccessResult within the per-backend wall-clock.
        crawl4ai_enabled = os.getenv("PG_CRAWL4AI_ENABLED", "1") == "1"
        if crawl4ai_enabled:
            concurrent_tasks.append(
                _bounded_backend("crawl4ai", self._try_crawl4ai(url), url))
            _queued_backends.append("Crawl4AI")

        concurrent_tasks.append(
            _bounded_backend("jina_reader", self._try_jina_reader(url), url))
        _queued_backends.append("Jina")

        firecrawl_enabled = os.getenv("PG_FIRECRAWL_ENABLED", "1") == "1"
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_enabled and firecrawl_api_key and _firecrawl_has_credits():
            concurrent_tasks.append(
                _bounded_backend("firecrawl", self._try_firecrawl(url), url))
            _queued_backends.append("Firecrawl")

        # FIX-039/B.3: Add trafilatura to concurrent group (was dead-code fallback)
        if os.getenv("PG_TRAFILATURA_ENABLED", "0") == "1":
            concurrent_tasks.append(
                _bounded_backend("trafilatura", self._try_trafilatura(url), url))
            _queued_backends.append("Trafilatura")

        # GH #1260 (cosmetic): log AFTER the backend list is built so it names
        # only the backends actually queued, not a hardcoded triple.
        logger.info(
            "[ACCESS] FIX-QM2: Concurrent %s for %s",
            "+".join(_queued_backends) or "(none)", url[:60],
        )

        # FIX-EPIPE: Wrap gather in try/except to catch CancelledError and
        # any BaseException that escapes from subprocess crashes in crawl4ai.
        # asyncio.gather(return_exceptions=True) captures Exception subclasses
        # as return values, but CancelledError (BaseException in Python 3.9+)
        # can still propagate if the gather task itself is cancelled.
        try:
            concurrent_results = await asyncio.gather(
                *concurrent_tasks, return_exceptions=True
            )
        except asyncio.CancelledError:
            logger.warning(
                "[ACCESS] FIX-EPIPE: Concurrent fetch cancelled for %s "
                "(likely subprocess crash or task cancellation)",
                url[:60],
            )
            concurrent_results = []
        except BaseException as gather_err:
            # Safety net for anything that escapes gather
            if isinstance(gather_err, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning(
                "[ACCESS] FIX-EPIPE: Unexpected %s from concurrent fetch "
                "for %s: %s -- server protected",
                type(gather_err).__name__, url[:60], str(gather_err)[:150],
            )
            concurrent_results = []

        # M-23b/c: Replace first-success-wins with quality-scored winner.
        # OLD BUG: Jina 422-char paywall stub won the race over Crawl4AI's
        # 45K-char NEJM SURPASS-5 fetch, because Jina's task finished first.
        # NEW: Collect ALL successful candidates, strip boilerplate FIRST
        # (so nav chrome containing "sign in" doesn't trigger paywall
        # false-positives on full article bodies), filter by paywall check,
        # then pick the highest-scoring candidate by content quality
        # (length + structural markers + numeric density).
        candidates: list[AccessResult] = []
        rejected_log: list[tuple[str, str, int]] = []
        for r in concurrent_results:
            if not isinstance(r, AccessResult):
                continue
            if not r.success:
                continue
            # M-23b: strip boilerplate BEFORE paywall check
            r.content = _strip_navigation_boilerplate(r.content)
            if self._detect_paywall(r.content):
                rejected_log.append((r.access_method, "paywall", len(r.content)))
                continue
            candidates.append(r)

        if candidates:
            # M-23c: quality-scored winner
            scored = [(c, _score_content_quality(c.content)) for c in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)
            winner, winner_score = scored[0]
            winner.metadata = {
                **(winner.metadata or {}),
                "quality_score": round(winner_score, 3),
                "n_candidates": len(candidates),
                "all_scores": {
                    c.access_method: round(s, 3) for c, s in scored
                },
            }
            logger.info(
                "[ACCESS] M-23c: %s won quality-scored fetch for %s "
                "(%d chars, score=%.3f, %d candidates, scores=%s)",
                winner.access_method, url[:60], len(winner.content),
                winner_score, len(candidates),
                {c.access_method: round(s, 3) for c, s in scored},
            )
            if rejected_log:
                logger.debug(
                    "[ACCESS] M-23b: rejected %d stub/paywall candidates: %s",
                    len(rejected_log), rejected_log,
                )
            return winner

        # FIX-039/B.3: Trafilatura now runs in concurrent group above (no standalone fallback)

        # Direct HTTP fetch with markdown Accept header (FIX-D6/A3)
        logger.info("[ACCESS] Trying direct fetch for %s", url[:60])
        timeout_occurred = False
        direct_result = await self._direct_fetch(url)

        if direct_result.success:
            # M-23b: strip BEFORE paywall detection
            direct_result.content = _strip_navigation_boilerplate(direct_result.content)
            if not self._detect_paywall(direct_result.content):
                return direct_result

        # Track if direct fetch failed due to timeout for retry logic (FIX-D5)
        if not direct_result.success and "timeout" in str(direct_result.metadata.get("error", "")).lower():
            timeout_occurred = True

        logger.info("[ACCESS] Direct access blocked for %s, trying alternatives", url[:80])

        # Try Archive.org
        if self.use_archive_org:
            logger.info("[ACCESS] Trying Archive.org for %s", url[:60])
            archive_result = await self._try_archive_org(url)
            if archive_result.success:
                # FIX-045B: Strip navigation boilerplate
                archive_result.content = _strip_navigation_boilerplate(archive_result.content)
                return archive_result

        # Try institutional proxy
        if self.proxy:
            logger.info("[ACCESS] Trying proxy for %s", url[:60])
            proxy_result = await self._try_proxy(url)
            if proxy_result.success:
                # FIX-045B: Strip navigation boilerplate
                proxy_result.content = _strip_navigation_boilerplate(proxy_result.content)
                return proxy_result

        # FIX-D5: Retry once on timeout errors before giving up
        if timeout_occurred:
            logger.info("[ACCESS] Retrying direct fetch after timeout for %s", url[:60])
            await asyncio.sleep(3)
            retry_result = await self._direct_fetch(url)
            if retry_result.success:
                # M-23b: strip BEFORE paywall detection
                retry_result.content = _strip_navigation_boilerplate(retry_result.content)
                if not self._detect_paywall(retry_result.content):
                    return retry_result

        # Sci-Hub is DISABLED BY DEFAULT (I-faith-002): the legal OA full-text
        # path is now CORE (src/tools/core_client.py) wired at
        # frame_fetcher.py Step 2b. PG_SCIHUB_ENABLED defaults to "0" so NO
        # outbound request is ever issued to any sci-hub.* host unless an
        # operator explicitly opts in by setting PG_SCIHUB_ENABLED=1. When
        # the flag is not "1" this block is skipped entirely — _try_scihub
        # (the sole sci-hub.* URL builder) is never called.
        # Use resolved DOI if available (more reliable than URL-based DOI extraction)
        if os.getenv("PG_SCIHUB_ENABLED", "0") == "1":
            scihub_url = url
            if resolved_doi:
                scihub_url = f"https://doi.org/{resolved_doi}"
            scihub_result = await self._try_scihub(scihub_url)
            if scihub_result.success:
                logger.info("[ACCESS] Sci-Hub succeeded for %s (%d chars)", url[:60], len(scihub_result.content))
                scihub_result.content = _strip_navigation_boilerplate(scihub_result.content)
                return scihub_result

        # I-fetch-004 (#1185): PAID Zyte fallback — the genuine LAST resort,
        # ONLY after the entire FREE chain (PDF/Unpaywall/PMC-BioC -> concurrent
        # quality-scored group -> direct -> Archive.org -> proxy -> timeout-retry
        # -> Sci-Hub) has failed. STRICT NO-OP: when ZYTE_API_KEY is absent the
        # helper is never even invoked, so behaviour here is byte-identical to
        # before (zero spend, zero risk on un-keyed runs). Zyte only RETRIEVES
        # raw content; the returned text still flows through the SAME extractor
        # and the downstream strict_verify / 4-role faithfulness gates — no gate
        # is bypassed. _try_zyte strips boilerplate internally and only returns
        # success on non-paywalled content above the min-length floor, so there
        # is no extra strip needed at this call site.
        if os.getenv("ZYTE_API_KEY"):
            logger.info(
                "[ACCESS] I-fetch-004: Trying Zyte paid fallback for %s", url[:60]
            )
            zyte_result = await self._try_zyte(url)
            if zyte_result.success:
                return zyte_result

        # SF-40: Log total failure at WARNING (was completely silent)
        logger.warning("[ACCESS] ALL access methods exhausted for %s", url[:80])
        # F14 (GH #1245 / D9, D10): when a PAYWALLED-publisher URL exhausts every
        # method and ZYTE_API_KEY is UNSET, surface a LOUD diagnostic — this is
        # exactly the case where the Zyte paid fallback (the one method that
        # could recover the body) was a silent no-op. Makes a Zyte-blind run on
        # paywalled journals auditable instead of a quiet exhaustion.
        if _is_paywall_publisher_host(url) and not os.getenv("ZYTE_API_KEY"):
            logger.warning(
                "[ACCESS] F14: paywalled publisher %s exhausted ALL free "
                "methods and ZYTE_API_KEY is UNSET — the Zyte paid fallback "
                "was never invoked (silent no-op). Set ZYTE_API_KEY to recover "
                "full text for paywalled journals.", url[:80],
            )
        return AccessResult(
            url=url,
            content="",
            access_method="failed",
            legal_alternative=None,
            success=False,
            metadata={"error": "All access methods failed"}
        )

    async def _try_crawl4ai(self, url: str) -> AccessResult:
        """
        Crawl4AI: Free, local, Playwright-based web crawler that generates
        LLM-ready markdown.  No API key or credits required.

        FIX-EPIPE: Hardened against Node.js subprocess EPIPE/broken pipe
        errors that can kill the Python server process. The Playwright
        browser subprocess can crash (EPIPE on websocket close), and the
        error propagates through AsyncWebCrawler.__aenter__/__aexit__.

        Defense layers:
        1. Circuit breaker -- skip crawl4ai after repeated subprocess crashes
        2. Import error catch -- handles corrupted crawl4ai installations
        3. Explicit __aenter__/__aexit__ -- no `async with` so __aexit__
           failures are caught independently via _safe_close_crawler()
        4. Specific catches for BrokenPipeError, ConnectionError, OSError
        5. asyncio.CancelledError catch (BaseException in Python 3.9+)
        6. BaseException safety net (re-raises KeyboardInterrupt/SystemExit)

        Controlled by env vars:
          - PG_CRAWL4AI_ENABLED (default "1")
          - PG_CRAWL4AI_TIMEOUT (default 30, in seconds)
          - PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD (default "3")
          - PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN (default "120.0")

        Returns AccessResult. NEVER raises -- all exceptions are caught
        and converted to failure results.
        """
        global _crawl4ai_available
        global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until

        # FIX-EPIPE: Circuit breaker -- skip after repeated subprocess crashes
        now = _time_module.time()
        if _crawl4ai_circuit_open_until > now:
            remaining = _crawl4ai_circuit_open_until - now
            logger.debug(
                "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPEN "
                "(%.0fs remaining) -- skipping %s",
                remaining, _safe_log_str(url, 60),
            )
            return _crawl4ai_failure_result(
                url, f"circuit_breaker_open ({remaining:.0f}s remaining)"
            )

        # Fast-path: already know crawl4ai is not installed
        if _crawl4ai_available is False:
            return _crawl4ai_failure_result(url, "crawl4ai not installed")

        # Lazy import with availability caching.
        # FIX-EPIPE: Catch all exceptions during import, not just ImportError.
        # crawl4ai's __init__.py may spawn subprocesses or load native libs
        # that can fail with OSError/RuntimeError on corrupted installations.
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
            try:
                from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
                from crawl4ai.content_filter_strategy import PruningContentFilter
                _crawl4ai_filter_available = True
            except ImportError:
                _crawl4ai_filter_available = False
            _crawl4ai_available = True
        except ImportError:
            _crawl4ai_available = False
            logger.warning(
                "[polaris graph] CRAWL4AI: crawl4ai package not installed. "
                "Install with: pip install crawl4ai"
            )
            return _crawl4ai_failure_result(url, "crawl4ai not installed")
        except Exception as import_err:
            _crawl4ai_available = False
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE import failed with "
                "%s: %s -- disabling crawl4ai for this session",
                type(import_err).__name__,
                _safe_log_str(str(import_err)),
            )
            return _crawl4ai_failure_result(
                url,
                f"import failed: {type(import_err).__name__}: {str(import_err)}",
            )

        timeout_seconds = int(os.getenv("PG_CRAWL4AI_TIMEOUT", "30"))
        page_timeout_ms = timeout_seconds * 1000

        # FIX-UNICODE: Crawl4AI/Playwright write Unicode to stdout/stderr.
        # Windows console uses cp1252 which cannot encode many chars.
        try:
            if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception as enc_err:
            logger.debug("Windows encoding reconfiguration skipped: %s", enc_err)

        # ---------------------------------------------------------------
        # FIX-EPIPE: Main crawl execution with decomposed context manager.
        #
        # Instead of `async with AsyncWebCrawler(...) as crawler:` which
        # makes __aexit__ failures escape into the caller, we manually
        # call __aenter__ and __aexit__ with independent error handling.
        # This ensures that a BrokenPipeError during browser cleanup
        # (the primary crash vector) cannot kill the server.
        # ---------------------------------------------------------------
        crawler = None
        try:
            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
            )
            # PL: Use PruningContentFilter to strip nav/ads/footers/cookie banners.
            # Without this, result.markdown contains full page including junk.
            # With fit_markdown, we get clean article body with proper tables.
            if _crawl4ai_filter_available:
                crawler_config = CrawlerRunConfig(
                    page_timeout=page_timeout_ms,
                    wait_until="domcontentloaded",
                    markdown_generator=DefaultMarkdownGenerator(
                        content_filter=PruningContentFilter(threshold=0.48),
                        options={"ignore_links": False, "body_width": 0},
                    ),
                )
            else:
                crawler_config = CrawlerRunConfig(
                    page_timeout=page_timeout_ms,
                    wait_until="domcontentloaded",
                )

            logger.info(
                "[polaris graph] CRAWL4AI: Fetching %s (timeout=%ds)",
                _safe_log_str(url, 80),
                timeout_seconds,
            )

            # I-fetch-002 (#1168): hold a crawl4ai concurrency slot ONLY for the browser-active region
            # (startup -> crawl -> close). The extraction (Step 4, trafilatura — CPU-bound) and the
            # cheap config build above run OUTSIDE the slot so a browser slot is never pinned by
            # non-browser work. `result` is assigned inside and read after the `async with` (it persists
            # in the enclosing scope). The inner early-returns release the slot cleanly on `async with`
            # exit. At most PG_CRAWL4AI_CONCURRENCY browsers are live at once.
            async with _get_crawl4ai_semaphore():
                # Step 1: Start the browser subprocess.
                # FIX-EPIPE: Separate try for __aenter__ to catch startup failures.
                try:
                    crawler = AsyncWebCrawler(config=browser_config)
                    await crawler.__aenter__()
                except (BrokenPipeError, ConnectionError, OSError) as enter_err:
                    logger.warning(
                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser startup "
                        "pipe/OS error for %s: %s: %s",
                        _safe_log_str(url, 60),
                        type(enter_err).__name__,
                        _safe_log_str(str(enter_err)),
                    )
                    _crawl4ai_track_failure()
                    return _crawl4ai_failure_result(
                        url,
                        f"Browser startup failed: {type(enter_err).__name__}: "
                        f"{str(enter_err)}",
                    )
                except Exception as enter_err:
                    logger.warning(
                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser init "
                        "exception for %s: %s: %s",
                        _safe_log_str(url, 60),
                        type(enter_err).__name__,
                        _safe_log_str(str(enter_err)),
                    )
                    _crawl4ai_track_failure()
                    return _crawl4ai_failure_result(
                        url,
                        f"Browser init failed: {type(enter_err).__name__}: "
                        f"{str(enter_err)}",
                    )

                # Step 2: Run the crawl with timeout guard.
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=crawler_config),
                        timeout=timeout_seconds + 10,
                    )
                finally:
                    # Step 3: Close browser via _safe_close_crawler which catches
                    # ALL exceptions from __aexit__ independently.
                    await _safe_close_crawler(crawler, url)
                    crawler = None  # Prevent double-close in outer finally

            # Step 4: Process the crawl result.
            # If we reached here, the subprocess survived (reset breaker).
            _crawl4ai_consecutive_failures = 0

            if not result.success:
                error_msg = result.error_message or "Crawl returned success=False"
                logger.warning(
                    "[polaris graph] CRAWL4AI: Failed for %s: %s",
                    _safe_log_str(url, 60),
                    _safe_log_str(str(error_msg)),
                )
                return AccessResult(
                    url=url,
                    content="",
                    access_method="crawl4ai",
                    legal_alternative=None,
                    success=False,
                    metadata={
                        "error": str(error_msg)[:200],
                        "status_code": result.status_code,
                    },
                )

            # PL: Crawl4AI renders JS → Trafilatura extracts article body.
            # Trafilatura (F1=0.958) strips nav/ads/gov banners/footers that
            # PruningContentFilter misses. Falls back to fit_markdown/raw.
            markdown_content = ""
            if result.html:
                # BB5-S03 (#1177): route through the SIGSEGV-mitigated shared
                # extractor (size-bounds the HTML, optional subprocess
                # containment) instead of a bare `trafilatura.extract` under
                # `except Exception` — a libxml2 C-crash on Crawl4AI's raw HTML
                # is not a catchable Python exception.
                clean = safe_trafilatura_extract(
                    result.html,
                    include_tables=True,
                    include_links=False,
                    output_format="txt",
                )
                if clean and len(clean) > 500:
                    markdown_content = clean
                    logger.info(
                        "[ACCESS] PL: Trafilatura cleaned Crawl4AI HTML: %d chars",
                        len(clean),
                    )

            # Fallback: fit_markdown or raw markdown from Crawl4AI
            if not markdown_content:
                if hasattr(result, "markdown") and result.markdown:
                    md_obj = result.markdown
                    if hasattr(md_obj, "fit_markdown") and md_obj.fit_markdown:
                        markdown_content = md_obj.fit_markdown
                    elif isinstance(md_obj, str):
                        markdown_content = md_obj
                    else:
                        markdown_content = str(md_obj)

            if not markdown_content or len(markdown_content.strip()) <= 100:
                logger.warning(
                    "[polaris graph] CRAWL4AI: Insufficient content for %s (%d chars)",
                    _safe_log_str(url, 60),
                    len(markdown_content),
                )
                return AccessResult(
                    url=url,
                    content="",
                    access_method="crawl4ai",
                    legal_alternative=None,
                    success=False,
                    metadata={
                        "error": "Insufficient content",
                        "content_length": len(markdown_content),
                        "status_code": result.status_code,
                    },
                )

            logger.info(
                "[polaris graph] CRAWL4AI: Succeeded for %s (%d chars, status %s)",
                _safe_log_str(url, 60),
                len(markdown_content),
                result.status_code,
            )
            return AccessResult(
                url=url,
                content=markdown_content,
                access_method="crawl4ai",
                legal_alternative=None,
                success=True,
                metadata={
                    "content_length": len(markdown_content),
                    "format": "markdown",
                    "status_code": result.status_code,
                    "redirected_url": result.redirected_url,
                },
            )

        except asyncio.TimeoutError:
            logger.warning(
                "[polaris graph] CRAWL4AI: Timeout after %ds for %s",
                timeout_seconds,
                _safe_log_str(url, 80),
            )
            return _crawl4ai_failure_result(
                url, f"Timeout after {timeout_seconds}s"
            )

        except asyncio.CancelledError:
            # FIX-EPIPE: CancelledError is BaseException in Python 3.9+.
            # NOT caught by `except Exception`. Happens when asyncio.wait_for
            # cancels the inner task, parent task is cancelled, or event loop
            # shuts down during a crawl.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE task cancelled for %s "
                "(CancelledError -- subprocess crash or shutdown)",
                _safe_log_str(url, 80),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, "Task cancelled (CancelledError)"
            )

        except (BrokenPipeError, ConnectionError) as pipe_err:
            # FIX-EPIPE: PRIMARY CRASH VECTOR. Playwright browser subprocess
            # dies, Node.js sends EPIPE on the websocket. Propagates as
            # BrokenPipeError or ConnectionError through asyncio transport.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE broken pipe for %s: "
                "%s: %s -- subprocess likely crashed, server protected",
                _safe_log_str(url, 60),
                type(pipe_err).__name__,
                _safe_log_str(str(pipe_err)),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url,
                f"Subprocess pipe error: {type(pipe_err).__name__}: "
                f"{str(pipe_err)}",
            )

        except OSError as os_err:
            # FIX-EPIPE: Parent of BrokenPipeError/ConnectionError. Also
            # covers "Invalid argument" (errno 22), "Bad file descriptor"
            # (errno 9), and other OS-level subprocess handle failures.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE OS error for %s: "
                "%s (errno=%s) -- subprocess likely crashed",
                _safe_log_str(url, 60),
                _safe_log_str(str(os_err)),
                getattr(os_err, "errno", "unknown"),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, f"OS error (errno={getattr(os_err, 'errno', '?')}): {str(os_err)}"
            )

        except RuntimeError as rt_err:
            # FIX-EPIPE: Playwright/asyncio internal errors after subprocess
            # death ("Event loop is closed", "Cannot write to closing
            # transport", etc.).
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE RuntimeError for %s: %s",
                _safe_log_str(url, 80),
                _safe_log_str(str(rt_err)),
            )
            return _crawl4ai_failure_result(
                url, f"RuntimeError: {str(rt_err)}"
            )

        except Exception as e:
            logger.warning(
                "[polaris graph] CRAWL4AI: Failed for %s: %s: %s",
                _safe_log_str(url, 80),
                type(e).__name__,
                _safe_log_str(str(e)),
            )
            return _crawl4ai_failure_result(
                url, f"{type(e).__name__}: {str(e)}"
            )

        except BaseException as be:
            # FIX-EPIPE: Ultimate safety net. Catches anything not a
            # subclass of Exception (GeneratorExit, exotic BaseException
            # subclasses from native extensions). Re-raise only
            # KeyboardInterrupt and SystemExit for clean shutdown.
            if isinstance(be, (KeyboardInterrupt, SystemExit)):
                raise
            logger.error(
                "[polaris graph] CRAWL4AI: FIX-EPIPE unexpected "
                "BaseException for %s (server protected): %s: %s",
                _safe_log_str(url, 80),
                type(be).__name__,
                _safe_log_str(str(be)),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, f"BaseException: {type(be).__name__}: {str(be)}"
            )

        finally:
            # FIX-EPIPE: Safety close in case crawler was not closed above
            # (e.g., exception during __aenter__ after partial init).
            if crawler is not None:
                await _safe_close_crawler(crawler, url)
            # FIX-UNICODE: Do NOT restore original encoding. Multiple
            # concurrent Crawl4AI calls race: one call's restore undoes
            # another call's reconfigure. utf-8 is strictly superior.

    async def _extract_pdf_text(self, url: str) -> str:
        """FIX-CITE-3/GAP4: Download and extract text from academic PDF.

        Uses PyMuPDF (fitz) for extraction. Falls back to basic text
        extraction if PyMuPDF is not available.
        """
        import aiohttp
        import tempfile

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return ""
                pdf_bytes = await resp.read()
                if len(pdf_bytes) < 1000:
                    return ""

        # FIX-DOCLING-OOM-V2: Guard against docling std::bad_alloc on large PDFs.
        # Docling's C++ preprocess stage has memory complexity proportional to
        # total_pages x image_resolution^2, doesn't release memory between
        # pages, and throws std::bad_alloc on 100+ page PDFs — killing the
        # Python process with SIGSEGV.
        #
        # V2 improvement: check BOTH byte size AND page count. A 3MB 200-page
        # dense-text PDF wouldn't trip a bytes-only guard but would still OOM
        # docling. PyMuPDF page count costs ~50ms and is memory-safe.
        #
        # Env overrides:
        #   PG_MAX_DOCLING_PDF_BYTES (default 5MB)
        #   PG_MAX_DOCLING_PDF_PAGES (default 40 pages)
        max_docling_bytes = int(
            os.getenv("PG_MAX_DOCLING_PDF_BYTES", str(5 * 1024 * 1024))
        )
        max_docling_pages = int(
            os.getenv("PG_MAX_DOCLING_PDF_PAGES", "40")
        )

        _skip_docling_reason = None
        if len(pdf_bytes) > max_docling_bytes:
            _skip_docling_reason = f"bytes={len(pdf_bytes)}>{max_docling_bytes}"
        else:
            # Cheap page count via PyMuPDF before committing to docling.
            try:
                import fitz as _fitz
                import tempfile as _tempfile
                with _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tmp:
                    _tmp.write(pdf_bytes)
                    _tmp_path = _tmp.name
                _doc = _fitz.open(_tmp_path)
                _page_count = _doc.page_count
                _doc.close()
                import os as _os_pc
                _os_pc.unlink(_tmp_path)
                if _page_count > max_docling_pages:
                    _skip_docling_reason = f"pages={_page_count}>{max_docling_pages}"
            except Exception as _exc:
                # If PyMuPDF can't even open it, docling probably can't either.
                # Skip docling and let PyMuPDF fallback handle with its own error.
                logger.debug(
                    "[ACCESS] FIX-DOCLING-OOM-V2: page count failed (%s), skipping docling",
                    str(_exc)[:80],
                )
                _skip_docling_reason = "pymupdf_open_failed"

        if _skip_docling_reason:
            logger.warning(
                "[ACCESS] FIX-DOCLING-OOM-V2: Skipping docling (%s), using PyMuPDF: %s",
                _skip_docling_reason, url[:50],
            )
        else:
            # PL: Try Docling first (97.9% table accuracy), PyMuPDF fallback
            try:
                import asyncio as _aio
                loop = _aio.get_event_loop()
                docling_text = await loop.run_in_executor(None, self._docling_extract, pdf_bytes)
                if docling_text and len(docling_text) > 500:
                    logger.info("[ACCESS] PL: Docling extracted %d chars from PDF %s", len(docling_text), url[:50])
                    return docling_text
            except Exception as exc:
                logger.debug("[ACCESS] PL: Docling failed, trying PyMuPDF: %s", str(exc)[:80])

        # Fallback: PyMuPDF (text-only, no table structure)
        try:
            import fitz
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            doc = fitz.open(tmp_path)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()

            import os as _os
            _os.unlink(tmp_path)

            full_text = "\n\n".join(pages_text)
            return full_text.strip()
        except ImportError:
            logger.warning("[ACCESS] FIX-GAP4: PyMuPDF not installed, PDF extraction unavailable")
            return ""
        except Exception as exc:
            logger.warning("[ACCESS] FIX-GAP4: PDF extraction error: %s", str(exc)[:100])
            return ""

    async def _try_trafilatura(self, url: str) -> Optional[AccessResult]:
        """Fetch content via trafilatura in thread pool (non-blocking).

        FIX-QM25-REVIVE: Trafilatura was disabled because its CPU-bound
        lxml/BS4 parsing blocks the asyncio event loop. This fix runs
        it in a thread pool executor to avoid GIL contention.

        Controlled by PG_TRAFILATURA_ENABLED env var (default "0").
        Returns None when disabled or when extraction fails.
        """
        if os.getenv("PG_TRAFILATURA_ENABLED", "0") != "1":
            return None

        try:
            import trafilatura

            loop = asyncio.get_event_loop()
            downloaded = await loop.run_in_executor(
                None, trafilatura.fetch_url, url
            )
            if not downloaded:
                return None

            # GH #1260: route the extraction through the ONE SIGSEGV-guarded
            # door (size gate + optional hard-killable subprocess) instead of a
            # bare `trafilatura.extract` in this thread-pool worker. A libxml2
            # C-crash on a pathological doc is NOT a catchable Python exception;
            # in a ThreadPoolExecutor thread it would take down the whole sweep.
            text = await loop.run_in_executor(
                None,
                lambda: safe_trafilatura_extract(
                    downloaded, include_links=True, include_tables=True
                ),
            )
            if text and len(text) > 200:
                logger.info(
                    "[ACCESS] Trafilatura succeeded for %s (%d chars)",
                    url[:60], len(text),
                )
                return AccessResult(
                    url=url,
                    content=text,
                    access_method="trafilatura",
                    legal_alternative=None,
                    success=True,
                    metadata={
                        "content_length": len(text),
                        "format": "text",
                    },
                )
            return None
        except ImportError:
            logger.warning(
                "[ACCESS] trafilatura not installed — skipping. "
                "Install with: pip install trafilatura"
            )
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] Trafilatura failed for %s: %s",
                url[:60], _safe_log_str(str(e)),
            )
            return None

    async def _try_jina_reader(self, url: str) -> AccessResult:
        """
        FIX-D1: Jina Reader as primary fetch tier.
        FIX-QM2: Exponential backoff on 429 (up to 2 retries).
        FIX-JINA: Also retry 401 (Jina returns 401 when concurrency
        exceeds free tier limit of 2). Add jitter to backoff.
        RC-9: Circuit breaker — skip after consecutive failures.

        Calls GET https://r.jina.ai/{url} to extract clean markdown content.
        With API key: 500 RPM. Without: 20 RPM.
        """
        import aiohttp
        import random

        # RC-9: Circuit breaker check
        global _jina_consecutive_failures, _jina_circuit_open_until
        now = _time_module.time()
        if _jina_circuit_open_until > now:
            logger.debug(
                "[ACCESS] RC-9: Jina circuit breaker OPEN (%.0fs remaining) — skipping %s",
                _jina_circuit_open_until - now, url[:60],
            )
            return AccessResult(
                url=url, content="", access_method="jina_reader",
                legal_alternative=None, success=False,
                metadata={"error": "circuit_breaker_open"},
            )

        jina_url = f"https://r.jina.ai/{url}"
        max_retries = int(os.getenv("PG_JINA_MAX_RETRIES", "3"))

        # FIX-JINA: Jina concurrency semaphore (free tier = 2 concurrent)
        global _jina_semaphore
        if _jina_semaphore is None:
            jina_concurrency = int(os.getenv("PG_JINA_CONCURRENCY", "2"))
            _jina_semaphore = asyncio.Semaphore(jina_concurrency)

        async with _jina_semaphore:
            for attempt in range(max_retries + 1):
                try:
                    timeout = aiohttp.ClientTimeout(total=30)
                    headers = {
                        **_NO_BROTLI_HEADERS,
                        "User-Agent": self.user_agent,
                        "Accept": "text/markdown",
                    }

                    jina_api_key = os.getenv("JINA_API_KEY")
                    if jina_api_key:
                        headers["Authorization"] = f"Bearer {jina_api_key}"

                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(jina_url, headers=headers) as response:
                            # FIX-JINA: Retry on 401 (concurrency exceeded) AND 429
                            if response.status in (401, 429):
                                if attempt < max_retries:
                                    jitter = random.uniform(0, 1.0)
                                    wait = 2.0 ** (attempt + 1) + jitter
                                    logger.warning(
                                        "[ACCESS] Jina %d for %s, "
                                        "backing off %.1fs (attempt %d/%d)",
                                        response.status,
                                        url[:60], wait, attempt + 1, max_retries + 1,
                                    )
                                    await asyncio.sleep(wait)
                                    continue
                                logger.warning(
                                    "[ACCESS] Jina %d exhausted retries for %s",
                                    response.status, url[:60],
                                )
                                return AccessResult(
                                    url=url,
                                    content="",
                                    access_method="jina_reader",
                                    legal_alternative=None,
                                    success=False,
                                    metadata={
                                        "status": response.status,
                                        "retries_exhausted": True,
                                    },
                                )

                            if response.status == 200:
                                content = await response.text()
                                if content and len(content.strip()) > 100:
                                    # RC-9: Reset circuit breaker on success
                                    _jina_consecutive_failures = 0
                                    logger.info(
                                        "[ACCESS] Jina Reader succeeded for %s (%d chars)",
                                        url[:60], len(content),
                                    )
                                    return AccessResult(
                                        url=url,
                                        content=content,
                                        access_method="jina_reader",
                                        legal_alternative=jina_url,
                                        success=True,
                                        metadata={
                                            "jina_url": jina_url,
                                            "content_length": len(content),
                                            "authenticated": bool(jina_api_key),
                                        },
                                    )

                            # RC-9: Track consecutive failure for circuit breaker
                            _jina_consecutive_failures += 1
                            if _jina_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                                _jina_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                                logger.warning(
                                    "[ACCESS] RC-9: Jina circuit breaker OPENED after "
                                    "%d consecutive failures (cooldown %.0fs)",
                                    _jina_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                                )
                            logger.warning(
                                "[ACCESS] Jina Reader returned status %d for %s",
                                response.status, url[:60],
                            )
                            return AccessResult(
                                url=url,
                                content="",
                                access_method="jina_reader",
                                legal_alternative=None,
                                success=False,
                                metadata={"status": response.status},
                            )

                except Exception as e:
                    if attempt < max_retries:
                        # FIX-G: Exponential backoff for exceptions (was flat 1s)
                        jitter = random.uniform(0, 1.0)
                        wait = 2.0 ** (attempt + 1) + jitter
                        logger.warning(
                            "[ACCESS] Jina Reader exception for %s: %s — "
                            "backing off %.1fs (attempt %d/%d)",
                            url[:60], str(e)[:100], wait,
                            attempt + 1, max_retries + 1,
                        )
                        await asyncio.sleep(wait)
                        continue
                    # RC-9: Track consecutive failure for circuit breaker
                    _jina_consecutive_failures += 1
                    if _jina_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                        _jina_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                        logger.warning(
                            "[ACCESS] RC-9: Jina circuit breaker OPENED after "
                            "%d consecutive failures",
                            _jina_consecutive_failures,
                        )
                    logger.warning("[ACCESS] Jina Reader failed for %s: %s", url[:80], str(e)[:150])
                    return AccessResult(
                        url=url,
                        content="",
                        access_method="jina_reader",
                        legal_alternative=None,
                        success=False,
                        metadata={"error": str(e)},
                    )

        # Should not reach here, but safety fallback
        return AccessResult(
            url=url,
            content="",
            access_method="jina_reader",
            legal_alternative=None,
            success=False,
            metadata={"error": "Unexpected loop exit"},
        )

    async def _try_zyte(self, url: str) -> AccessResult:
        """I-fetch-004 (#1185): PAID Zyte fallback — the genuine last resort.

        Called by `fetch_with_bypass` ONLY after the entire free chain
        (direct -> concurrent quality-scored group -> Archive.org -> proxy ->
        timeout-retry -> Sci-Hub) has failed.

        Safety couplings (all required):
          - ENV-GATED: with ZYTE_API_KEY absent this is a complete NO-OP that
            returns a failure AccessResult and spends nothing. The call site
            also guards on the key, so the helper is never even invoked on
            un-keyed runs (double-safe — behaviour byte-identical to before).
          - COST-SMART: tries the cheap httpResponseBody mode first and
            escalates to the pricier JS-rendering browserHtml mode ONLY when
            the cheap result is unusable (empty / short / paywalled). A hard
            auth/quota error (401/402/429) returns fast WITHOUT a second paid
            call.
          - CIRCUIT BREAKER: after N consecutive failures the breaker opens for
            a cooldown so a Zyte outage cannot fire N doomed PAID calls on a
            ~1000-URL run.
          - FAITHFULNESS-UNAFFECTED: Zyte only RETRIEVES raw HTML; it is routed
            through the SAME `safe_trafilatura_extract` extractor every other
            backend uses, then through the downstream strict_verify / 4-role
            gates. No faithfulness gate is bypassed. The issue notes scraping
            bypasses bot-blocks, NOT paywalls — so a paywall stub remains a
            live possibility and is rejected by `_detect_paywall` before any
            success is returned.

        Zyte API (docs.zyte.com): POST https://api.zyte.com/v1/extract, HTTP
        Basic auth with the API key as username and an EMPTY password.
        httpResponseBody is BASE64-encoded; browserHtml is a plain HTML string.
        """
        import aiohttp
        import base64

        # Telemetry + breaker globals. Declared together so the `+= 1` lines
        # below do not raise UnboundLocalError.
        global _zyte_consecutive_failures, _zyte_circuit_open_until
        global _zyte_fallback_attempts, _zyte_fallback_success

        # ENV-GATE (strict NO-OP, zero spend when the key is absent).
        key = os.getenv("ZYTE_API_KEY")
        if not key:
            return AccessResult(
                url=url,
                content="",
                access_method="zyte",
                legal_alternative=None,
                success=False,
                metadata={"error": "ZYTE_API_KEY not set"},
            )

        # CIRCUIT BREAKER: skip (no paid call) while open.
        now = _time_module.time()
        if _zyte_circuit_open_until > now:
            remaining = _zyte_circuit_open_until - now
            logger.debug(
                "[ACCESS] Zyte circuit breaker OPEN for %s (%.0fs remaining)",
                url[:60], remaining,
            )
            return AccessResult(
                url=url,
                content="",
                access_method="zyte",
                legal_alternative=None,
                success=False,
                metadata={
                    "error": "circuit_breaker_open",
                    "cooldown_remaining": remaining,
                },
            )

        def _record_failure() -> None:
            """Increment the breaker and open it at threshold."""
            global _zyte_consecutive_failures, _zyte_circuit_open_until
            _zyte_consecutive_failures += 1
            if _zyte_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                _zyte_circuit_open_until = (
                    _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                )
                logger.warning(
                    "[ACCESS] Zyte circuit breaker OPENED after %d consecutive "
                    "failures (cooldown %.0fs)",
                    _zyte_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                )

        def _is_usable(text: "str | None") -> bool:
            """Usable = extracted, long enough, and not a paywall stub."""
            if not text or len(text) < _ZYTE_MIN_CONTENT_CHARS:
                return False
            if self._detect_paywall(text):
                return False
            return True

        timeout = aiohttp.ClientTimeout(total=_ZYTE_TIMEOUT)
        headers = {**_NO_BROTLI_HEADERS, "Content-Type": "application/json"}
        auth = aiohttp.BasicAuth(key, "")

        _zyte_fallback_attempts += 1

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # (1) CHEAP mode: httpResponseBody (base64-encoded).
                async with session.post(
                    _ZYTE_API_ENDPOINT,
                    headers=headers,
                    auth=auth,
                    json={"url": url, "httpResponseBody": True},
                ) as resp:
                    status = resp.status
                    # DIFFERENTIATED hard-error handling: auth/quota/rate-limit
                    # return fast and count toward the breaker — do NOT escalate
                    # a hard error into a second paid call.
                    if status in (401, 402, 403, 429):
                        body = (await resp.text())[:200]
                        logger.warning(
                            "[ACCESS] Zyte cheap request returned %d for %s: %s",
                            status, url[:60], _safe_log_str(body, 120),
                        )
                        _record_failure()
                        return AccessResult(
                            url=url, content="", access_method="zyte",
                            legal_alternative=None, success=False,
                            metadata={"status": status, "error": "auth_or_quota"},
                        )
                    if status != 200:
                        logger.warning(
                            "[ACCESS] Zyte cheap request returned status %d for %s",
                            status, url[:60],
                        )
                        _record_failure()
                        return AccessResult(
                            url=url, content="", access_method="zyte",
                            legal_alternative=None, success=False,
                            metadata={"status": status},
                        )
                    data = await resp.json()

                encoded = (data or {}).get("httpResponseBody")
                cheap_text: "str | None" = None
                if encoded:
                    html = base64.b64decode(encoded).decode(
                        "utf-8", errors="replace"
                    )
                    cheap_text = safe_trafilatura_extract(
                        html,
                        include_tables=True,
                        include_links=False,
                        output_format="txt",
                    )

                used_text = cheap_text
                mode = "httpResponseBody"
                escalated = False

                # (2) ESCALATE to browserHtml ONLY when the cheap result is
                # unusable (None / too short / paywalled). browserHtml is the
                # pricier JS-rendering, ban-solving mode.
                if not _is_usable(cheap_text):
                    escalated = True
                    mode = "browserHtml"
                    async with session.post(
                        _ZYTE_API_ENDPOINT,
                        headers=headers,
                        auth=auth,
                        json={"url": url, "browserHtml": True},
                    ) as resp2:
                        status2 = resp2.status
                        if status2 in (401, 402, 403, 429):
                            body2 = (await resp2.text())[:200]
                            logger.warning(
                                "[ACCESS] Zyte browserHtml returned %d for %s: %s",
                                status2, url[:60], _safe_log_str(body2, 120),
                            )
                            _record_failure()
                            return AccessResult(
                                url=url, content="", access_method="zyte",
                                legal_alternative=None, success=False,
                                metadata={"status": status2, "error": "auth_or_quota"},
                            )
                        if status2 != 200:
                            logger.warning(
                                "[ACCESS] Zyte browserHtml returned status %d for %s",
                                status2, url[:60],
                            )
                            _record_failure()
                            return AccessResult(
                                url=url, content="", access_method="zyte",
                                legal_alternative=None, success=False,
                                metadata={"status": status2},
                            )
                        data2 = await resp2.json()
                    browser_html = (data2 or {}).get("browserHtml")
                    used_text = None
                    if browser_html:
                        used_text = safe_trafilatura_extract(
                            browser_html,
                            include_tables=True,
                            include_links=False,
                            output_format="txt",
                        )

            # POST-PROCESSING CONSISTENCY: strip boilerplate (every sibling
            # return does this) then gate on paywall + min-length so a stub
            # can never pollute the evidence pool.
            content = _strip_navigation_boilerplate(used_text or "")
            if (
                content
                and len(content) >= _ZYTE_MIN_CONTENT_CHARS
                and not self._detect_paywall(content)
            ):
                _zyte_consecutive_failures = 0
                _zyte_fallback_success += 1
                logger.info(
                    "[ACCESS] Zyte succeeded for %s (%d chars, mode=%s, "
                    "escalated=%s, attempts=%d, successes=%d)",
                    url[:60], len(content), mode, escalated,
                    _zyte_fallback_attempts, _zyte_fallback_success,
                )
                return AccessResult(
                    url=url,
                    content=content[:50000],
                    access_method="zyte",
                    legal_alternative=None,
                    success=True,
                    metadata={
                        "content_length": len(content),
                        "zyte_mode": mode,
                        "escalated": escalated,
                    },
                )

            # Unusable (short / paywalled / empty) — terminal failure, no
            # further escalation.
            _record_failure()
            logger.info(
                "[ACCESS] Zyte produced unusable content for %s "
                "(mode=%s, escalated=%s)",
                url[:60], mode, escalated,
            )
            return AccessResult(
                url=url, content="", access_method="zyte",
                legal_alternative=None, success=False,
                metadata={
                    "error": "unusable_content",
                    "zyte_mode": mode,
                    "escalated": escalated,
                },
            )

        except Exception as e:
            # Never crash the fetch loop — any error returns a failure result.
            _record_failure()
            logger.warning(
                "[ACCESS] Zyte failed for %s: %s", url[:80], str(e)[:150],
            )
            return AccessResult(
                url=url, content="", access_method="zyte",
                legal_alternative=None, success=False,
                metadata={"error": str(e)[:200]},
            )

    async def _try_firecrawl(self, url: str) -> AccessResult:
        """
        FIX-D2 Hardened: Firecrawl with rate limiting, credit tracking,
        and differentiated error handling.

        Free plan limits: 500 credits/month, 10 req/min.
        """
        # FIX-044/Issue3: Respect PG_FIRECRAWL_ENABLED kill switch
        if os.getenv("PG_FIRECRAWL_ENABLED", "1") != "1":
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "Firecrawl disabled via PG_FIRECRAWL_ENABLED=0"},
            )

        import aiohttp

        # RC-10: Circuit breaker check for Firecrawl (mirrors Jina pattern)
        global _firecrawl_consecutive_failures, _firecrawl_circuit_open_until
        now = _time_module.time()
        if _firecrawl_circuit_open_until > now:
            remaining = _firecrawl_circuit_open_until - now
            logger.debug(
                "[ACCESS] Firecrawl circuit breaker OPEN for %s (%.0fs remaining)",
                url[:60], remaining,
            )
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "circuit_breaker_open", "cooldown_remaining": remaining},
            )

        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_api_key:
            logger.warning("[ACCESS] Firecrawl skipped — FIRECRAWL_API_KEY not set")
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "FIRECRAWL_API_KEY not set"},
            )

        # Credit gate: check before making request
        if not _firecrawl_has_credits():
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={
                    "error": "Monthly credit quota exhausted",
                    "credits_used": _firecrawl_credits_used,
                    "credits_quota": _FIRECRAWL_MONTHLY_QUOTA,
                },
            )

        # Rate limit: enforce minimum interval
        await _firecrawl_rate_limit()

        firecrawl_endpoint = "https://api.firecrawl.dev/v1/scrape"

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                **_NO_BROTLI_HEADERS,
                "Authorization": f"Bearer {firecrawl_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "url": url,
                "formats": ["markdown"],
            }

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    firecrawl_endpoint, headers=headers, json=payload
                ) as response:
                    status_code = response.status

                    # Differentiated error handling
                    if status_code == 429:
                        retry_after = response.headers.get("Retry-After", "10")
                        logger.warning(
                            "[ACCESS] Firecrawl 429 rate limited for %s — "
                            "Retry-After: %s",
                            url[:60],
                            retry_after,
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={
                                "status": 429,
                                "retry_after": retry_after,
                                "error": "Rate limited",
                            },
                        )

                    if status_code == 401:
                        logger.error(
                            "[ACCESS] Firecrawl 401 unauthorized — "
                            "check FIRECRAWL_API_KEY"
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={"status": 401, "error": "Unauthorized"},
                        )

                    if status_code == 402:
                        logger.error(
                            "[ACCESS] Firecrawl 402 payment required — "
                            "credits exhausted"
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={"status": 402, "error": "Credits exhausted"},
                        )

                    if status_code == 200:
                        data = await response.json()

                        # Track credit usage
                        _firecrawl_track_credit()

                        # Validate response success field
                        if isinstance(data, dict) and not data.get("success", True):
                            error_msg = data.get("error", "Unknown error")
                            logger.warning(
                                "[ACCESS] Firecrawl returned success=false for %s: %s",
                                url[:60],
                                str(error_msg)[:200],
                            )
                            return AccessResult(
                                url=url,
                                content="",
                                access_method="firecrawl",
                                legal_alternative=None,
                                success=False,
                                metadata={
                                    "status": 200,
                                    "firecrawl_success": False,
                                    "error": str(error_msg)[:200],
                                },
                            )

                        # Extract markdown content
                        markdown_content = ""
                        resp_metadata: dict = {}
                        if isinstance(data, dict):
                            resp_data = data.get("data", {})
                            if isinstance(resp_data, dict):
                                markdown_content = resp_data.get("markdown", "")
                                resp_metadata = {
                                    "status_code": resp_data.get("statusCode"),
                                    "credits_used": _firecrawl_credits_used,
                                    "credits_quota": _FIRECRAWL_MONTHLY_QUOTA,
                                }

                        if markdown_content and len(markdown_content.strip()) > 100:
                            # RC-10: Reset circuit breaker on success
                            _firecrawl_consecutive_failures = 0
                            logger.info(
                                "[ACCESS] Firecrawl succeeded for %s "
                                "(%d chars, credit %d/%d)",
                                url[:60],
                                len(markdown_content),
                                _firecrawl_credits_used,
                                _FIRECRAWL_MONTHLY_QUOTA,
                            )
                            return AccessResult(
                                url=url,
                                content=markdown_content,
                                access_method="firecrawl",
                                legal_alternative=None,
                                success=True,
                                metadata={
                                    "content_length": len(markdown_content),
                                    "format": "markdown",
                                    **resp_metadata,
                                },
                            )

                    # RC-10: Track failure for circuit breaker
                    _firecrawl_consecutive_failures += 1
                    if _firecrawl_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                        _firecrawl_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                        logger.warning(
                            "[ACCESS] Firecrawl circuit breaker OPENED after %d consecutive failures "
                            "(cooldown %.0fs)",
                            _firecrawl_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                        )
                    logger.warning(
                        "[ACCESS] Firecrawl returned status %d for %s",
                        status_code,
                        url[:60],
                    )
                    return AccessResult(
                        url=url,
                        content="",
                        access_method="firecrawl",
                        legal_alternative=None,
                        success=False,
                        metadata={"status": status_code},
                    )

        except Exception as e:
            # RC-10: Track failure for circuit breaker
            _firecrawl_consecutive_failures += 1
            if _firecrawl_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                _firecrawl_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                logger.warning(
                    "[ACCESS] Firecrawl circuit breaker OPENED after %d consecutive failures "
                    "(cooldown %.0fs)",
                    _firecrawl_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                )
            logger.warning(
                "[ACCESS] Firecrawl failed for %s: %s",
                url[:80],
                str(e)[:150],
            )
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": str(e)},
            )

    async def _try_unpaywall(self, doi: str) -> Optional[str]:
        """M-23a: Query Unpaywall for best legal open-access URL for a DOI.

        Unpaywall indexes 30M+ OA articles from repositories (arXiv,
        PMC, institutional) and publisher DOIs. Returns the best OA URL
        (PDF preferred) if available, else None. Free, ethical, and the
        first thing to try for paywalled journals like NEJM/Lancet/JAMA
        whose authors frequently post preprints or PMC copies.

        Reference: https://unpaywall.org/products/api
        Endpoint: https://api.unpaywall.org/v2/{doi}?email={email}
        Rate limit: 100K/day with free email-tagged access.
        """
        import aiohttp

        email = os.getenv("UNPAYWALL_EMAIL")
        if not email:
            return None

        api_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    api_url, headers=_NO_BROTLI_HEADERS
                ) as response:
                    if response.status == 404:
                        # Unknown DOI — normal, don't log noisily
                        return None
                    if response.status != 200:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall HTTP %d for DOI %s",
                            response.status, doi,
                        )
                        return None
                    data = await response.json()
                    if not data.get("is_oa"):
                        return None
                    # M-23e: Prefer a direct PDF URL across ALL oa_locations.
                    # Live testing exposed: Unpaywall's best_oa_location may
                    # be a repository landing page (figshare, discovery.ucl)
                    # whose bare URL 403s on headless fetch. A PDF URL from
                    # any location gets clean extraction via _extract_pdf_text.
                    # Only fall back to best.url when NO location has a PDF.
                    oa_locations = data.get("oa_locations") or []
                    pdf_urls = [
                        loc.get("url_for_pdf")
                        for loc in oa_locations
                        if loc.get("url_for_pdf")
                    ]
                    if pdf_urls:
                        oa_url = pdf_urls[0]
                        host_type = next(
                            (loc.get("host_type", "unknown")
                             for loc in oa_locations
                             if loc.get("url_for_pdf") == oa_url),
                            "unknown",
                        )
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall PDF OA for %s: %s (%s)",
                            doi, oa_url[:80], host_type,
                        )
                        return oa_url
                    # No PDF. I-bug-775 (#815, Codex B): do NOT swap to a
                    # publisher / doi.org / DOI-resolver landing page — those
                    # fetch as 280-400-char stubs (mode 1) and are no better
                    # than the paywalled original. The ONLY non-PDF swap we
                    # allow is a PMC URL (it carries a PMCID, so the caller's
                    # BioC full-text path will resolve it). Everything else:
                    # return None and let the main cascade try the original URL.
                    best = data.get("best_oa_location") or {}
                    landing = best.get("url")
                    host_type = best.get("host_type", "unknown")
                    # Scan all OA locations for a PMC URL (PMCID-bearing).
                    pmc_landing = next(
                        (
                            loc.get("url")
                            for loc in oa_locations
                            if loc.get("url")
                            and re.search(r"/PMC\d+\b", loc.get("url"), re.IGNORECASE)
                        ),
                        None,
                    )
                    if pmc_landing:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall PMC OA URL for %s: %s "
                            "(BioC full-text will resolve)",
                            doi, pmc_landing[:80],
                        )
                        return pmc_landing
                    # No PDF, no PMC URL — do not swap to a landing page
                    # (mode-1 stub). Keep the original URL for the cascade.
                    if landing:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall %s landing without PDF/PMC "
                            "for %s — keeping original URL (no landing swap)",
                            host_type, doi,
                        )
                    return None
        except asyncio.TimeoutError:
            logger.info("[ACCESS] M-23a: Unpaywall timeout for DOI %s", doi)
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] M-23a: Unpaywall failed for DOI %s: %s",
                doi, str(e)[:120],
            )
            return None

    async def _direct_fetch(self, url: str) -> AccessResult:
        """Direct HTTP fetch with markdown Accept header (FIX-D6/A3) and 5xx retry (FIX-D5)."""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # FIX-D6/A3: Add markdown Accept header to prefer markdown responses
                headers = {
                    **_NO_BROTLI_HEADERS,
                    "User-Agent": self.user_agent,
                    "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
                }

                async with session.get(url, headers=headers) as response:
                    # FIX-D6/A3: Log if server returned markdown content type
                    content_type = response.headers.get("Content-Type", "")
                    if "text/markdown" in content_type.lower():
                        logger.info(
                            "[ACCESS] Server returned markdown content for %s",
                            url[:60],
                        )

                    # FIX-D5: Retry once with 3s delay for 5xx status codes
                    if response.status >= 500:
                        logger.info(
                            "[ACCESS] Direct fetch got %d for %s, retrying in 3s",
                            response.status, url[:60],
                        )
                        await asyncio.sleep(3)
                        async with session.get(url, headers=headers) as retry_response:
                            retry_content_type = retry_response.headers.get("Content-Type", "")
                            if "text/markdown" in retry_content_type.lower():
                                logger.info(
                                    "[ACCESS] Server returned markdown content on retry for %s",
                                    url[:60],
                                )
                            content = await retry_response.text()
                            return AccessResult(
                                url=url,
                                content=content,
                                access_method="direct",
                                legal_alternative=None,
                                success=retry_response.status == 200,
                                metadata={
                                    "status": retry_response.status,
                                    "retried": True,
                                    "original_status": response.status,
                                    "content_type": retry_content_type,
                                },
                            )

                    content = await response.text()

                    return AccessResult(
                        url=url,
                        content=content,
                        access_method="direct",
                        legal_alternative=None,
                        success=response.status == 200,
                        metadata={
                            "status": response.status,
                            "content_type": content_type,
                        },
                    )

        except Exception as e:
            # SF-35: Log direct fetch failures (was completely silent)
            logger.warning("[ACCESS] direct fetch failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(
                url=url,
                content="",
                access_method="direct",
                legal_alternative=None,
                success=False,
                metadata={"error": str(e)}
            )

    async def _try_archive_org(self, url: str) -> AccessResult:
        """Try Archive.org Wayback Machine."""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Check availability
                api_url = f"https://archive.org/wayback/available?url={url}"

                async with session.get(api_url, headers=_NO_BROTLI_HEADERS) as response:
                    data = await response.json()

                    snapshots = data.get("archived_snapshots", {})
                    closest = snapshots.get("closest", {})

                    if closest.get("available"):
                        archive_url = closest["url"]

                        async with session.get(archive_url, headers=_NO_BROTLI_HEADERS) as archive_response:
                            content = await archive_response.text()

                            return AccessResult(
                                url=url,
                                content=content,
                                access_method="archive.org",
                                legal_alternative=archive_url,
                                success=True,
                                metadata={"archive_url": archive_url, "timestamp": closest.get("timestamp")}
                            )

                    return AccessResult(url=url, content="", access_method="archive.org",
                                      legal_alternative=None, success=False,
                                      metadata={"error": "No archive available"})

        except Exception as e:
            # SF-37: Log Archive.org failures (was completely silent)
            logger.warning("[ACCESS] Archive.org failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(url=url, content="", access_method="archive.org",
                              legal_alternative=None, success=False,
                              metadata={"error": str(e)})

    @staticmethod
    def _docling_extract(pdf_bytes: bytes) -> str:
        """PL: Extract markdown from PDF using IBM Docling (97.9% table accuracy)."""
        import tempfile
        import os as _os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            md_text = result.document.export_to_markdown()
            return md_text.strip()
        finally:
            _os.unlink(tmp_path)

    async def _resolve_academic_url(self, url: str) -> tuple[str, str]:
        """PL: Resolve academic metadata URLs to actual paper URLs + DOIs.

        Handles three cases:
        1. S2 landing pages (semanticscholar.org/paper/xxx) -> OA PDF URL or DOI
        2. ScienceDirect PIIs -> CrossRef -> DOI
        3. doi.org URLs -> follow redirect to publisher

        Returns (resolved_url, doi). Both may be empty if resolution fails.
        """
        import aiohttp
        import re

        resolved_url = ""
        doi = ""

        # Case 1: Semantic Scholar landing pages
        if "semanticscholar.org/paper/" in url:
            paper_id = url.rstrip("/").split("/")[-1]
            # Strip any title slug (e.g., "Title-of-Paper/abc123" -> "abc123")
            if len(paper_id) < 10:
                parts = url.rstrip("/").split("/")
                paper_id = parts[-1] if len(parts[-1]) >= 10 else parts[-2] if len(parts) > 1 else paper_id

            s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
            headers = {"x-api-key": s2_key} if s2_key else {}

            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    api_url = (
                        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
                        f"?fields=doi,openAccessPdf,url"
                    )
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            doi = data.get("doi", "") or ""
                            oa_pdf = data.get("openAccessPdf")
                            if oa_pdf and oa_pdf.get("url"):
                                resolved_url = oa_pdf["url"]
                                logger.info(
                                    "[ACCESS] PL: S2 %s -> OA PDF: %s",
                                    paper_id[:12], resolved_url[:60],
                                )
                            elif doi:
                                resolved_url = f"https://doi.org/{doi}"
                                logger.info(
                                    "[ACCESS] PL: S2 %s -> DOI: %s",
                                    paper_id[:12], doi,
                                )
            except Exception as exc:
                logger.debug("[ACCESS] PL: S2 resolve failed for %s: %s", paper_id[:12], str(exc)[:60])

        # Case 2: ScienceDirect PIIs
        elif "sciencedirect.com" in url and "pii/" in url:
            pii_match = re.search(r"pii/([A-Z0-9]+)", url)
            if pii_match:
                pii = pii_match.group(1)
                try:
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        cr_url = f"https://api.crossref.org/works?filter=alternative-id:{pii}&rows=1"
                        async with session.get(cr_url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                items = data.get("message", {}).get("items", [])
                                if items:
                                    doi = items[0].get("DOI", "")
                                    if doi:
                                        resolved_url = f"https://doi.org/{doi}"
                                        logger.info(
                                            "[ACCESS] PL: ScienceDirect PII %s -> DOI: %s",
                                            pii[:12], doi,
                                        )
                except Exception as exc:
                    logger.debug("[ACCESS] PL: CrossRef resolve failed for %s: %s", pii[:12], str(exc)[:60])

        # Case 3: Extract DOI from URL for Nature, JAMA, tandfonline, etc.
        if not doi:
            doi_match = re.search(r"(10\.\d{4,9}/[^\s\"<>',;]+)", url)
            if doi_match:
                doi = doi_match.group(1).rstrip(".")
            # Nature: /articles/s41574-022-00638-x -> 10.1038/s41574-022-00638-x
            elif "nature.com/articles/" in url:
                art_match = re.search(r"articles/(s\d+-\d+-\d+-\w+)", url)
                if art_match:
                    doi = f"10.1038/{art_match.group(1)}"

        return resolved_url or url, doi

    async def _try_scihub(self, url: str) -> AccessResult:
        """PL: Try Sci-Hub for paywalled academic papers.

        Extracts DOI from URL, queries Sci-Hub mirrors, downloads PDF,
        and converts to text via PyMuPDF. Last resort after all legal
        methods exhausted.
        """
        import aiohttp
        import re

        # Extract DOI from URL
        doi = None
        doi_match = re.search(r"(10\.\d{4,9}/[^\s\])<>\"',;]+)", url)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")

        if not doi:
            return AccessResult(url=url, content="", access_method="scihub",
                                legal_alternative=None, success=False,
                                metadata={"error": "No DOI found in URL"})

        mirrors = ["https://sci-hub.st", "https://sci-hub.ru"]
        timeout = aiohttp.ClientTimeout(total=20)

        for mirror in mirrors:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    scihub_url = f"{mirror}/{doi}"
                    async with session.get(scihub_url) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                        # Check if paper is available
                        if "not available" in html.lower()[:500]:
                            continue

                        # Extract PDF URL from embed/iframe
                        pdf_match = re.search(
                            r'(?:embed|iframe)[^>]+src=["\']([^"\']+\.pdf[^"\']*)',
                            html,
                        )
                        if not pdf_match:
                            # Try direct PDF link pattern
                            pdf_match = re.search(r'(//[^\s"<>]+\.pdf)', html)

                        if not pdf_match:
                            # No PDF found but page loaded — try extracting
                            # text content from the HTML itself
                            if len(html) > 5000:
                                return AccessResult(
                                    url=url, content=html[:30000],
                                    access_method="scihub_html",
                                    legal_alternative=scihub_url,
                                    success=True,
                                    metadata={"doi": doi, "mirror": mirror},
                                )
                            continue

                        pdf_url = pdf_match.group(1)
                        if pdf_url.startswith("//"):
                            pdf_url = "https:" + pdf_url

                        # Download PDF
                        async with session.get(pdf_url) as pdf_resp:
                            if pdf_resp.status != 200:
                                continue
                            pdf_bytes = await pdf_resp.read()

                        # Extract text from PDF
                        try:
                            import fitz  # PyMuPDF
                            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                            text_parts = []
                            for page in doc:
                                text_parts.append(page.get_text())
                            doc.close()
                            full_text = "\n\n".join(text_parts)

                            if len(full_text) > 500:
                                logger.info(
                                    "[ACCESS] Sci-Hub PDF extracted for %s: %d chars from %d pages",
                                    doi, len(full_text), len(text_parts),
                                )
                                return AccessResult(
                                    url=url, content=full_text[:50000],
                                    access_method="scihub_pdf",
                                    legal_alternative=scihub_url,
                                    success=True,
                                    metadata={"doi": doi, "mirror": mirror, "pages": len(text_parts)},
                                )
                        except ImportError:
                            logger.warning("[ACCESS] PyMuPDF not installed — cannot extract Sci-Hub PDF")
                        except Exception as pdf_exc:
                            logger.warning("[ACCESS] Sci-Hub PDF extraction failed: %s", str(pdf_exc)[:100])

            except Exception as exc:
                logger.debug("[ACCESS] Sci-Hub mirror %s failed: %s", mirror, str(exc)[:80])

        return AccessResult(url=url, content="", access_method="scihub",
                            legal_alternative=None, success=False,
                            metadata={"error": "All Sci-Hub mirrors failed", "doi": doi})

    async def _try_proxy(self, url: str) -> AccessResult:
        """Try institutional proxy."""
        import aiohttp

        if not self.proxy:
            return AccessResult(url=url, content="", access_method="proxy",
                              legal_alternative=None, success=False,
                              metadata={"error": "No proxy configured"})

        try:
            # Rewrite URL through proxy
            parsed = urlparse(url)
            proxied_url = url.replace(parsed.netloc, f"{parsed.netloc}.{self.proxy}")

            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(proxied_url, headers={**_NO_BROTLI_HEADERS, "User-Agent": self.user_agent}) as response:
                    content = await response.text()

                    return AccessResult(
                        url=url,
                        content=content,
                        access_method="proxy",
                        legal_alternative=proxied_url,
                        success=response.status == 200,
                        metadata={"proxied_url": proxied_url}
                    )

        except Exception as e:
            # SF-38: Log proxy failures (was completely silent)
            logger.warning("[ACCESS] Proxy failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(url=url, content="", access_method="proxy",
                              legal_alternative=None, success=False,
                              metadata={"error": str(e)})

    def _detect_paywall(self, content: str) -> bool:
        """Detect if content is behind paywall OR an HTTP-error stub.

        M-23d: Extended to detect HTTP error stubs (403/404/5xx proxied
        through Jina Reader or similar). Jina returns success=True with
        a 200-500 char "403 Forbidden" / "Access Denied" page when the
        upstream server rejected its request. Without this detection,
        those stubs wait through all paywall patterns (which don't
        match "403 Forbidden" text) and get picked as fetch winners.

        M-23f: Paywall patterns are split into strict (fire on any
        length) and short-only (fire only on <2K char content). This
        prevents greedy-regex false positives like `sign.*in.*to.*
        access` matching "signed...had full access" in a 50K-char
        NEJM article body.
        """
        content_lower = content.lower()
        is_short = len(content) < 2000

        # Strict patterns: always apply
        for pattern in self.paywall_patterns_strict:
            if re.search(pattern, content_lower):
                return True

        # Loose patterns: only apply to short content
        if is_short:
            for pattern in self.paywall_patterns_short_only:
                if re.search(pattern, content_lower):
                    return True

        # SF-42: Short content with paywall indicators is likely paywalled
        # (removed dead `pass` code — either implement or remove)
        if len(content) < 2000 and any(
            re.search(p, content_lower) for p in [
                r"sign\s*in", r"log\s*in", r"create.*account",
            ]
        ):
            logger.info("[ACCESS] Short content (%d chars) with auth prompt — likely paywalled", len(content))
            return True

        # M-23d: HTTP error stubs. Short pages (<2K chars) containing
        # error status text are almost always failed fetches, not real
        # content. "403 Forbidden" / "404 Not Found" / "Error 5xx" /
        # "Access Denied" / "Target URL returned error" (Jina's phrasing).
        if len(content) < 2000:
            http_error_signals = [
                r"\b403\s+forbidden\b",
                r"\b404\s+not\s+found\b",
                r"\b5\d{2}\s+(internal\s+server\s+error|bad\s+gateway|service\s+unavailable|gateway\s+timeout)\b",
                r"access\s+denied",
                r"returned\s+error\s+\d{3}",
                r"target\s+url\s+returned\s+error",
                r"\bcloudflare\b.*\bblocked\b",
                r"\brate\s+limit(ed)?\b",
            ]
            for pattern in http_error_signals:
                if re.search(pattern, content_lower):
                    logger.info(
                        "[ACCESS] M-23d: Short content (%d chars) with "
                        "HTTP-error signal (%s) — treating as failed fetch",
                        len(content), pattern,
                    )
                    return True

        return False

    def _extract_pmcid(self, url: str) -> Optional[str]:
        """I-bug-775 (#815): extract a PMCID (e.g. 'PMC6490750') from a PMC URL
        — pmc.ncbi.nlm.nih.gov/articles/PMC<digits>/ or a PMC PDF URL."""
        if not url:
            return None
        m = re.search(r"/(PMC\d+)\b", url, re.IGNORECASE)
        return m.group(1).upper() if m else None

    async def _try_pmc_bioc_fulltext(self, pmcid: str) -> Optional[str]:
        """I-bug-775 (#815): fetch PMC Open-Access full text via the BioC API
        (Codex decision A). Returns normalized full text (>= the min-fulltext
        threshold, with body-like sections) or None. Conservative NCBI throttle
        (max 1 concurrent + ~3 req/s) with 429 exponential backoff. NEVER returns
        abstract-only / references-only / API-error text (see _parse_bioc_fulltext)."""
        global _ncbi_last_request_time
        import aiohttp

        bioc_url = (
            "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/"
            f"BioC_json/{pmcid}/unicode"
        )
        raw: Optional[str] = None
        try:
            async with _get_ncbi_semaphore():
                elapsed = _time_module.monotonic() - _ncbi_last_request_time
                if _ncbi_last_request_time > 0 and elapsed < _NCBI_MIN_INTERVAL:
                    await asyncio.sleep(_NCBI_MIN_INTERVAL - elapsed)
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for attempt in range(3):
                        async with session.get(
                            bioc_url, headers=_NO_BROTLI_HEADERS
                        ) as resp:
                            _ncbi_last_request_time = _time_module.monotonic()
                            if resp.status == 429:
                                await asyncio.sleep(1.0 * (2 ** attempt))
                                continue
                            if resp.status != 200:
                                logger.info(
                                    "[ACCESS] PMC-BioC HTTP %d for %s",
                                    resp.status, pmcid,
                                )
                                return None
                            raw = await resp.text()
                            break
        except asyncio.TimeoutError:
            logger.info("[ACCESS] PMC-BioC timeout for %s", pmcid)
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] PMC-BioC failed for %s: %s", pmcid, str(e)[:120]
            )
            return None

        if not raw:
            return None
        text = _parse_bioc_fulltext(raw)
        if not text or len(text) < _PMC_BIOC_MIN_FULLTEXT_CHARS:
            logger.info(
                "[ACCESS] PMC-BioC %s: no body-like full text (len=%d) — falling through",
                pmcid, len(text or ""),
            )
            return None
        logger.info(
            "[ACCESS] PMC-BioC full text for %s (%d chars)", pmcid, len(text)
        )
        return text

    def _extract_doi(self, url: str) -> Optional[str]:
        """Extract DOI from URL."""
        # DOI patterns
        patterns = [
            r'10\.\d{4,9}/[-._;()/:A-Z0-9]+',
            r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1) if len(match.groups()) > 0 else match.group(0)

        return None

    def _is_academic_url(self, url: str) -> bool:
        """Check if URL is likely academic."""
        academic_domains = [
            "springer", "wiley", "elsevier", "sciencedirect",
            "nature", "science", "jstor", "ieee", "acm",
            "arxiv", "pubmed", "ncbi", "nih.gov",
            "semanticscholar.org",
        ]

        url_lower = url.lower()
        return any(domain in url_lower for domain in academic_domains) or bool(self._extract_doi(url))

    def get_access_stats(self) -> Dict[str, Any]:
        """Get statistics about access methods used."""
        return {
            "archive_org_enabled": self.use_archive_org,
            "proxy_configured": bool(self.proxy),
            "respect_robots_txt": self.respect_robots,
            "crawl4ai_enabled": os.getenv("PG_CRAWL4AI_ENABLED", "1") == "1",
            "jina_reader_enabled": True,
            "firecrawl_enabled": bool(os.getenv("FIRECRAWL_API_KEY")),
        }
