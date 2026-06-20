"""
Live retriever — HONEST-REBUILD.

Performs REAL retrieval using Serper (web) + Semantic Scholar (academic)
+ OpenAlex (canonicalization) and wires every candidate URL through the
honest-rebuild modules in one clean path:

    1. Serper + Semantic Scholar bulk search
    2. Convert hits into SearchCandidate
    3. scope_query_validator on amplified queries
    4. prefetch_offtopic_filter on candidates (if embedder available)
    5. Fetch each URL's content (basic http.get) with size cap
    6. Classify each with tier_classifier
    7. Return list[CorpusSource] + evidence rows

This is the live alternative to the pre-rebuild searcher.py path,
which had complex dependencies into src/agents/ that we're trying
to archive. Keeping the live retriever in polaris_graph/retrieval/
means the honest-rebuild pipeline is self-contained.

Performance: rate-limited, caps total candidates. Designed to be
called ONCE per research question (not repeatedly in a loop).
"""
from __future__ import annotations

import logging
import math
import os
import asyncio
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlsplit

import httpx

from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
    filter_search_results,
)
from src.polaris_graph.retrieval.scope_query_validator import (
    validate_amplified_queries,
)
from src.polaris_graph.retrieval.query_decomposer import distill_keywords  # FX-18 (#1122)
from src.polaris_graph.retrieval import shell_detector  # I-beatboth-001 (#1276): single-sourced shell vocab
from src.polaris_graph.authority.authority_model import score_source_authority
from src.polaris_graph.authority.source_class import AuthoritySignals
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)

logger = logging.getLogger("polaris_graph.live_retriever")


SERPER_ENDPOINT = "https://google.serper.dev/search"
S2_BULK_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
OPENALEX_SOURCES_ENDPOINT = "https://api.openalex.org/sources"

# Phase 0a (GH #983, ADDENDUM C5): root-level /works select= fieldset for the
# authority model. OpenAlex select= is ROOT-LEVEL ONLY (rejects nested props),
# so summary_stats / apc_prices / is_core / is_in_doaj come from a SEPARATE
# /sources/{id} fetch keyed by primary_location.source.id.
OPENALEX_WORKS_SELECT = (
    "id,doi,title,display_name,type,publication_year,cited_by_count,"
    "is_retracted,primary_location,authorships"
)
OPENALEX_SOURCES_SELECT = (
    "id,is_core,is_in_doaj,apc_prices,summary_stats"
)

# Versioned local cache for the authority-enrich payload (live path). The
# schema version is bumped (not CREATE-IF-NOT-EXISTS no-op) on any column
# change, with an ALTER/rebuild migration (C5 requirement).
AUTHORITY_CACHE_DB = Path(
    os.getenv("PG_AUTHORITY_CACHE_DB", "cache/authority_enrich.sqlite")
)
# I-ready-017 #1134 (Codex diff-gate P1-2): bumped 1->2 so cached enrich payloads
# written before the journal_only `is_retracted` + `openalex_venue` fields are
# REBUILT (not served stale) — a cached retracted article must not pass the
# journal_only predicate via a payload that predates the retraction field.
AUTHORITY_CACHE_SCHEMA_VERSION = 2

# Hard caps
DEFAULT_MAX_SERPER = int(os.getenv("PG_LIVE_MAX_SERPER", "20"))
DEFAULT_MAX_S2 = int(os.getenv("PG_LIVE_MAX_S2", "20"))
DEFAULT_FETCH_CAP = int(os.getenv("PG_LIVE_FETCH_CAP", "40"))
DEFAULT_CONTENT_MAX_CHARS = int(os.getenv("PG_LIVE_CONTENT_MAX", "25000"))
DEFAULT_HTTP_TIMEOUT = float(os.getenv("PG_LIVE_HTTP_TIMEOUT", "20"))

# I-fetch-003 (#1175 / BB5-C02): parallel-fetch worker-pool sizing. When
# PG_LIVE_RETRIEVER_MAX_WORKERS is UNSET, the pool scales with the candidate
# count: min(_CEILING, max(_FLOOR, len(candidates) // _PER_CANDIDATE)). Named
# constants (LAW VI — no magic numbers). Floor keeps small corpora at the
# legacy default of 8; ceiling caps the pool so a huge corpus cannot spawn an
# unbounded thread count; per-candidate divisor sets the ramp.
_FETCH_WORKERS_FLOOR = 8
_FETCH_WORKERS_CEILING = 48
_FETCH_WORKERS_PER_CANDIDATE = 16
# Mirror of parallel_fetch.DEFAULT_PER_BACKEND_LIMIT (4) used as the default
# per-HOST concurrency cap; imported as a named constant rather than hardcoded.
from src.polaris_graph.audit_ir.parallel_fetch import (  # noqa: E402
    DEFAULT_PER_BACKEND_LIMIT as _PARALLEL_FETCH_DEFAULT_PER_BACKEND_LIMIT,
)
# I-fetch-003 (#1175 / AC3): WARN floor for the new fetch_success_rate
# retrieval diagnostic. Env-overridable; below this, a loud warning fires.
_FETCH_SUCCESS_RATE_WARN_FLOOR = float(
    os.getenv("PG_LIVE_FETCH_SUCCESS_RATE_WARN_FLOOR", "0.5")
)

# BB5-C05 (#1177): "fetched-200-but-empty-extract" thresholds. A fetch counts
# as this DISTINCT bucket when the backend returned a non-trivial raw body
# (>= _EXTRACT_NONEMPTY_RAW_FLOOR chars) yet the extractor chain (trafilatura →
# readability → regex) yielded fewer than _EXTRACT_EMPTY_FLOOR usable chars.
# Named constants (LAW VI — no magic numbers); env-overridable.
_EXTRACT_NONEMPTY_RAW_FLOOR = int(
    os.getenv("PG_FETCH_NONEMPTY_RAW_FLOOR", "200")
)
_EXTRACT_EMPTY_FLOOR = int(
    os.getenv("PG_FETCH_EMPTY_EXTRACT_FLOOR", "50")
)

# ─────────────────────────────────────────────────────────────────────────────
# F14 (GH #1245 / D9, D10): paywall-stub min-body gate.
#
# A fetch that returns a short body from a demanded paywalled journal was
# logged status="ok" with an empty refetch ledger — a DEAD fetch masquerading
# as a good source. This gate makes a sub-floor body a `stub` (fail-LOUD,
# ok=False), NOT `ok`, so the refetch ladder / down-weight semantics kick in
# instead of admitting an empty shell to the evidence pool.
#
# DEFAULT 0 = OFF = byte-identical to prior behavior (every existing fetch that
# returned non-empty content stays ok=True). The live cert sweep sets this to
# 1000 (a real journal article is tens of thousands of chars; a paywall shell
# is a few hundred). A CAP-not-target: it never drops a long body, only flags a
# short one. Set PG_FETCH_MIN_BODY_CHARS=1000 on the run slate. The OA resolver
# (Unpaywall / PMC-BioC / Zyte) gets first chance to upgrade the body ABOVE the
# floor before the stub verdict is rendered — so this STRENGTHENS honesty,
# never relaxes it (LAW II fail-loud; §-1.3 the faithfulness path is untouched).
# Read at CALL time (LAW VI — env-overridable per run; not frozen at import).
def _fetch_min_body_chars() -> int:
    try:
        return int(os.getenv("PG_FETCH_MIN_BODY_CHARS", "0"))
    except ValueError:
        return 0

# F14: publisher hosts that overwhelmingly serve paywalled article bodies via
# the free fetch chain (the free backends 403 / return a few-hundred-char
# abstract shell). When ZYTE_API_KEY is present, these are routed to Zyte FIRST
# (a real body instead of a shell); when it is ABSENT, a LOUD warning fires so
# a Zyte-blind run is auditable instead of a silent no-op (the access_bypass
# Zyte fallback was a SILENT no-op without the key). Substring match on the
# lowercased netloc; env-extendable via PG_PAYWALL_PUBLISHER_HOSTS (comma-sep,
# additive). Never a hard DROP — only a routing + loud-warning signal.
_PAYWALL_PUBLISHER_HOSTS_DEFAULT = (
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


def _paywall_publisher_hosts() -> tuple[str, ...]:
    """F14: the paywalled-publisher host list (default + env-additive). Read at
    call time so PG_PAYWALL_PUBLISHER_HOSTS can extend it per run (LAW VI)."""
    extra = os.getenv("PG_PAYWALL_PUBLISHER_HOSTS", "").strip()
    hosts = list(_PAYWALL_PUBLISHER_HOSTS_DEFAULT)
    if extra:
        hosts.extend(
            h.strip().lower() for h in extra.split(",") if h.strip()
        )
    return tuple(hosts)


def _is_paywall_publisher_url(url: str) -> bool:
    """F14: True iff the URL's host is a known paywalled publisher (substring
    match on the lowercased netloc). Pure, no network."""
    if not url:
        return False
    try:
        netloc = (urlparse(url).netloc or "").lower()
    except Exception:
        return False
    if not netloc:
        return False
    return any(h in netloc for h in _paywall_publisher_hosts())


# F30 (GH #1245): repository / landing / abstract-page markers. A source whose
# fetched body is a publication-record / landing / abstract page (NOT the full
# article text) cannot ground a methods/results claim — methods do not live on
# a landing page. These are the literal markers the free fetch backends emit
# when they land on a repository record page (Jina's "URL Source:" header, an
# APA-style citation block, a "Publication status:" record field). Detection
# DOWN-WEIGHTS + FLAGS the row (it stays in the pool at low weight per §-1.3),
# it NEVER hard-drops. Matched case-insensitively on the body head only.
_LANDING_PAGE_MARKERS = (
    "url source:",
    "## apa style",
    "apa style",
    "publication status:",
    "this record",
    "view record",
    "full text not available",
    "request full text",
    "abstract only",
)
# Defaults for the landing-marker head window + max body length. Read at CALL
# time (Codex diff-gate P2 iter-2 — env-overridable per run, not frozen at
# import). A real full-text body may quote a marker deep in its references, so we
# only inspect the head; and a landing/abstract page is short AND marker-bearing,
# so a long body with a head-of-body citation is NOT flagged unless it is short.
_LANDING_MARKER_HEAD_CHARS_DEFAULT = 1500
_LANDING_PAGE_MAX_CHARS_DEFAULT = 3000


def _is_landing_or_abstract_page(content: str) -> bool:
    """F30: True iff the fetched body looks like a repository/landing/abstract
    RECORD page rather than full article text. Keys on SPECIFIC landing markers
    AND a short body so a long full-text article that merely cites one of these
    phrases is never false-flagged. Pure heuristic; no network. Thresholds are
    read at CALL time via `_env_int` (Codex diff-gate P2 iter-2 — env-overridable
    per run, not frozen at import)."""
    if not content:
        return False
    stripped = content.strip()
    if len(stripped) > _env_int(
        "PG_LANDING_PAGE_MAX_CHARS", _LANDING_PAGE_MAX_CHARS_DEFAULT
    ):
        return False
    head = stripped[
        : _env_int("PG_LANDING_MARKER_HEAD_CHARS", _LANDING_MARKER_HEAD_CHARS_DEFAULT)
    ].lower()
    return any(marker in head for marker in _LANDING_PAGE_MARKERS)


# ─────────────────────────────────────────────────────────────────────────────
# F15 (GH #1245 / D11): per-URL refetch cap + negative cache.
#
# A DEAD DOI / URL was refetched ~5.5x per URL across the expansion / deepener /
# agentic stages because `refetch_for_extraction_with_diagnostics` had NO memory
# of prior failures — every section that wanted to ground a claim re-paid the
# full AccessBypass cascade (Crawl4AI / Jina / Firecrawl / proxy) for the SAME
# dead URL. This adds:
#   - a per-URL attempt counter so a FAILING URL is fetched at most _REFETCH_CAP
#     times (cap=2 => up to two real attempts before a permanent skip — a
#     transient failure still gets its retry budget), and
#   - a negative cache that a URL enters ONLY once it has both FAILED and reached
#     the cap, so subsequent requests short-circuit with NO network call and the
#     skip is honestly attributable to the cap.
# Codex diff-gate P1 (#1245): the attempt budget — NOT a mark-dead-on-first-
# failure — is the cap. A URL is refetched up to `cap` times; only at exhaustion
# is it cached. This preserves the retry budget the spec requires ("refetched at
# most the cap") while still killing the ~5.5x re-fetch storm.
#
# Codex diff-gate P1 iter-2 + iter-3 (#1245): the SKIP decision gates ONLY on
# SETTLED FAILURES reaching the cap (the negative cache). It does NOT gate on
# in-flight/concurrent reservations. Rationale (iter-3 P1): gating on in-flight
# would HARD-SKIP a concurrent caller of a LIVE URL whose reserved fetches will
# SUCCEED — wrongly suppressing a fetch that could succeed, which violates the
# §-1.3 "never suppress a fetch that could succeed" / successes-uncapped
# constraint. A SUCCESS never counts toward the cap. Only FAILED fetches count;
# once a URL has FAILED `cap` times it is cached and permanently short-circuited.
#
# Concurrency honesty: in the real call topology the refetch loop is SERIAL (the
# `for anchor in primary_trial_anchors` grounding loop), so a dead URL is fetched
# exactly `cap` times. Under hypothetical TRUE concurrency a dead URL could see a
# small bounded OVERSHOOT (callers already in-flight when the cap-th failure
# populates the cache) — that is an acceptable perf trade-off; it NEVER over-
# suppresses (the iter-3 constraint), and it still kills the ~5.5x storm. A
# threading lock guards every read/write of the shared dicts.
#
# The cache is process-local + bounded; it is a PERFORMANCE de-dup, NOT a
# faithfulness gate — it only stops repeating a fetch that ALREADY failed cap
# times, never suppresses a fetch that could succeed. Default cap 2; env-tunable.
_REFETCH_CAP_DEFAULT = 2
# Per-URL count of SETTLED failed attempts (a success never counts toward the cap).
_refetch_failures: dict[str, int] = {}
# URLs whose SETTLED failures have reached the cap (the permanent-skip set).
_refetch_negative_cache: set[str] = set()
_refetch_cache_lock = threading.Lock()


def _refetch_cap() -> int:
    """F15: per-URL refetch cap, read at CALL time (LAW VI — env-overridable per
    run). <= 0 disables the cap (a failing URL may be retried without bound — the
    legacy pre-F15 behavior)."""
    try:
        return int(os.getenv("PG_REFETCH_PER_URL_CAP", str(_REFETCH_CAP_DEFAULT)))
    except ValueError:
        return _REFETCH_CAP_DEFAULT


def reset_refetch_cache() -> None:
    """F15: clear the per-URL failure counters + negative cache. Called at the
    start of each retrieval run (and by tests) so the bounded cache does not leak
    across independent runs/vectors in a long-lived process."""
    with _refetch_cache_lock:
        _refetch_failures.clear()
        _refetch_negative_cache.clear()


def _refetch_try_acquire(url: str) -> bool:
    """F15: True => caller MAY fetch; False => skip because the URL has FAILED the
    cap number of times (it is in the negative cache). Gates ONLY on settled
    failures — NEVER on in-flight/concurrent reservations — so a concurrent caller
    of a LIVE URL is never wrongly skipped (Codex diff-gate iter-3 P1: never
    suppress a fetch that could succeed). Thread-safe (single lock)."""
    if not url:
        return True
    with _refetch_cache_lock:
        return url not in _refetch_negative_cache


def _refetch_settle(url: str, *, succeeded: bool) -> None:
    """F15: settle the outcome of a fetch. A SUCCESS is a no-op (a live URL never
    counts toward the cap and may be re-grounded by many sections). A FAILURE
    increments the settled-failure count and, at the cap, caches the URL so
    further requests short-circuit. Thread-safe (single lock)."""
    if not url or succeeded:
        return
    _cap = _refetch_cap()
    with _refetch_cache_lock:
        n = _refetch_failures.get(url, 0) + 1
        _refetch_failures[url] = n
        if _cap > 0 and n >= _cap:
            _refetch_negative_cache.add(url)


def _refetch_should_skip(url: str) -> bool:
    """F15: True iff this URL has SETTLED-failed to the cap (permanently cached).
    Equivalent to `not _refetch_try_acquire(url)`; kept as a pure read for tests /
    diagnostics. Thread-safe."""
    if not url:
        return False
    with _refetch_cache_lock:
        return url in _refetch_negative_cache


def _refetch_record_failure(url: str) -> None:
    """F15: record a failure for a URL acquired OUTSIDE the try/settle protocol
    (e.g. a test or a non-reserved path). Increments the settled-failure count and
    caches at the cap. Thread-safe."""
    if not url:
        return
    _cap = _refetch_cap()
    with _refetch_cache_lock:
        n = _refetch_failures.get(url, 0) + 1
        _refetch_failures[url] = n
        if _cap > 0 and n >= _cap:
            _refetch_negative_cache.add(url)


def _credibility_redesign_enabled() -> bool:
    """F15/F30: master switch for the WEIGHT-AND-CONSOLIDATE redesign (§-1.3 /
    I-arch-002 #1246), mirroring ``evidence_selector._credibility_redesign_enabled``.
    Default OFF — when ``PG_SWEEP_CREDIBILITY_REDESIGN`` is unset, the
    content-starved / landing-page rows stay on the legacy HARD-DROP path so the
    OFF path is byte-identical. When ON, those rows are DOWN-WEIGHTED (kept in the
    pool at low weight) instead of dropped."""
    return os.environ.get("PG_SWEEP_CREDIBILITY_REDESIGN", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


# F15/F30: the low retrieval weight stamped on a down-weighted (content-starved
# or landing-page) row so the composition layer can rank it last while still
# carrying it (§-1.3 WEIGHT-not-FILTER). A small positive float so it never ties
# with a real full-text row but is never zero (zero would let a falsy `or`
# launder it back to a default). Read at CALL time (Codex diff-gate P2 iter-2 —
# env-overridable per run, not frozen at import). LAW VI — no magic number.
_DOWN_WEIGHT_RETRIEVAL_DEFAULT = 0.05


def _down_weight_retrieval() -> float:
    try:
        return float(os.getenv("PG_DOWN_WEIGHT_RETRIEVAL", str(_DOWN_WEIGHT_RETRIEVAL_DEFAULT)))
    except (TypeError, ValueError):
        return _DOWN_WEIGHT_RETRIEVAL_DEFAULT


@dataclass
class LiveRetrievalResult:
    classified_sources: list[CorpusSource]
    evidence_rows: list[dict[str, Any]]
    total_candidates_pre_filter: int
    candidates_kept_by_scope: int
    candidates_kept_by_offtopic: int
    candidates_fetched: int
    candidates_failed_fetch: int
    api_calls: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # #958 (S2): fail-loud corpus-truncation signal. True when the post-fetch
    # loop budget (PG_POST_FETCH_LOOP_BUDGET) broke mid-corpus, leaving later
    # candidates unclassified. Defaults keep existing constructors valid.
    corpus_truncated: bool = False
    candidates_total: int = 0
    candidates_processed: int = 0
    # I-ready-017 #1134: journal_only metadata sidecar, keyed by canonical URL.
    # Populated ONLY on the journal_only ON path (None = OFF = byte-identical).
    # Carries the per-source journal-article signals (openalex pub_type /
    # source_type / is_peer_reviewed / is_retracted / doi / venue) that the
    # citeability predicate needs; merged across retrieval stages by the sweep.
    journal_metadata_sidecar: dict[str, Any] | None = None
    # I-fetch-003 (#1175 / AC3): NEW retrieval-throughput diagnostics, emitted
    # as SIBLING fields (NOT folded into api_calls: dict[str, int] — that
    # contract stays unwidened). None when the parallel-fetch path did not run
    # (serial fallback or no candidates). fetch_success_rate = usable / (usable
    # + failed); parallel_completion_rate = completed-in-deadline / submitted.
    fetch_success_rate: float | None = None
    parallel_completion_rate: float | None = None
    fetch_workers: int | None = None
    distinct_hosts: int | None = None
    # I-ready-017 Task 2a (#1204): ADDITIVE source-funnel telemetry (read-only).
    # Persists existing-but-unsaved retrieval counts so the ~90% pre-fetch
    # source loss is MEASURABLE on a fresh run. NONE of these change what is
    # discovered/filtered/fetched/selected — they only mirror locals already
    # computed inside run_live_retrieval.
    #   prefetch_offtopic: the off-topic filter's kept/rejected/threshold. None
    #     when the filter is disabled or only seeds are present (seed_only) —
    #     honestly absent, never a faked count.
    #   drop_reasons: per-reason aggregate of the in-run _trace_drop calls
    #     (offtopic / rerank_not_selected / fetch_failed / content_starved). The
    #     four statically-known reasons are pre-seeded to 0 so the schema is
    #     stable; counts derive locally (not from the pathB trace contextvar,
    #     which is empty on a normal sweep).
    prefetch_offtopic: dict[str, Any] | None = None
    drop_reasons: dict[str, int] = field(default_factory=dict)
    # B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-threshold + fetch-budget
    # selection telemetry. Populated ONLY on the B4 ON path
    # (PG_RETRIEVAL_RELEVANCE_GATE=1); None when OFF => byte-identical. Records the
    # unfetched-but-relevant tail (above-threshold candidates the fetch BUDGET
    # could not afford) so the recall cost is measurable, never dropped-and-
    # forgotten. A plain dict (RelevanceGateResult.to_dict()) so the manifest
    # write is a no-op getattr with a None default for pre-B4 callers.
    relevance_gate: dict[str, Any] | None = None
    #   extraction_finding_rows: the EXTRACTION-stage finding-row count captured
    #     at run_live_retrieval RETURN time (== len(evidence_rows) here), frozen
    #     as an int. Codex diff-gate iter-1 P1: run_one_query MUTATES
    #     retrieval.evidence_rows AFTER this returns (expansion append, deepener/
    #     agentic reassign), so reading len(evidence_rows) at manifest-write time
    #     reports the POST-expansion total, not the extraction yield. This frozen
    #     int is the stable fetched->finding extraction count.
    extraction_finding_rows: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-002-q1d (#945): per-call retrieval-trace helpers. Best-effort, lazy-import, no-op when the
# trace is not started — PURELY OBSERVATIONAL (the retrieval/verify chokepoint is never altered).
# Mirrors the existing record_retrieval_attempt idiom (lazy import + swallow any error).
# ─────────────────────────────────────────────────────────────────────────────
def _trace_query(backend: str, query: str, urls: list[str]) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_query(backend, query, urls)
    except Exception:
        pass


def _trace_kept(url: str, backend: str) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_kept(url, backend)
    except Exception:
        pass


def _trace_drop(url: str, reason: str) -> None:
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_drop(url, reason)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-007b (#meta-007): per-tool utilization tracer. Record-only + fail-safe.
# The tracer NEVER changes retrieval behavior or return values; any tracer error
# (import failure, None tracer, disk error) is swallowed here so a telemetry bug
# can never break retrieval. Lazy import keeps the dependency one-directional.
# ─────────────────────────────────────────────────────────────────────────────
def _trace_tool(
    tool_name: str,
    target: str = "",
    status: str = "ok",
    latency_ms: float = 0.0,
    bytes_sent: int = 0,
    bytes_received: int = 0,
    backend_used: str = "",
    error: str = "",
    **metadata: Any,
) -> None:
    try:
        from src.polaris_graph.telemetry.tool_tracer import (
            get_tool_tracer,
            tool_tracker_enabled,
        )
        # I-meta-007b P2b: gate on PG_ENABLE_TOOL_TRACKER (default ON) so a
        # direct caller OUTSIDE run_one_query (which never ran the per-query
        # reset/bind) cannot append to a stale ON singleton when tracking is
        # disabled. When OFF this is a pure no-op.
        if not tool_tracker_enabled():
            return
        get_tool_tracer().record(
            tool_name=tool_name,
            target=target,
            status=status,
            latency_ms=latency_ms,
            bytes_sent=bytes_sent,
            bytes_received=bytes_received,
            backend_used=backend_used,
            error=error,
            **metadata,
        )
    except Exception:  # noqa: BLE001 — telemetry must never break retrieval
        pass


def _resp_content_len(resp: Any) -> int:
    """Best-effort byte length of an httpx response body for telemetry.

    Returns 0 when the response object lacks a measurable ``content`` (e.g. a
    lightweight test double). NEVER raises — record-only telemetry must not
    depend on the response's concrete shape.
    """
    try:
        content = getattr(resp, "content", None)
        return len(content) if content else 0
    except Exception:  # noqa: BLE001 — telemetry must never break retrieval
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# API clients
# ─────────────────────────────────────────────────────────────────────────────


# FX-17 (#1126): Serper `num` is a PAGE size (provider max ~20); large result sets need the `page`
# param (pagination). The old code silently floored `num` to 20 with no warning and never paginated.
_SERPER_PAGE_MAX = 20


def _serper_fetch_page(
    query: str, per_page: int, page: int, headers: dict[str, str]
) -> tuple[list[dict[str, Any]], bool, float, int, str]:
    """FX-17 (#1126): fetch ONE Serper page. Returns (items, ok, latency_ms, resp_bytes, error).
    Byte-identical to the legacy single call when page==1 (no `page` key in the payload)."""
    payload: dict[str, Any] = {"q": query, "num": per_page}
    if page > 1:
        payload["page"] = page
    _t0 = time.time()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.post(SERPER_ENDPOINT, json=payload, headers=headers)
        _latency_ms = (time.time() - _t0) * 1000.0
        if r.status_code != 200:
            return [], False, _latency_ms, _resp_content_len(r), f"HTTP {r.status_code}"
        organic = (r.json().get("organic", []) or [])
        items = [
            {"url": it.get("link", ""), "title": it.get("title", ""),
             "snippet": it.get("snippet", ""), "source": "serper"}
            for it in organic
        ]
        return items, True, _latency_ms, _resp_content_len(r), ""
    except Exception as exc:
        return [], False, (time.time() - _t0) * 1000.0, 0, str(exc)


def _serper_search(
    query: str, num: int = 10, api_calls: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        logger.warning("[live_retriever] SERPER_API_KEY missing — skipping Serper")
        return []
    # I-safety-002b (#925) PR-2: record that the Path-B-required backend was actually
    # invoked (key present + call attempted). assert_post_run rejects a run where a
    # required backend was never tried. Lazy + best-effort; no-op when gate is off.
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("serper")
    except Exception:
        pass
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    per_page = max(1, min(num, _SERPER_PAGE_MAX))
    # FX-17 (#1126): make the silent clamp VISIBLE — the inert PG_SWEEP_MAX_SERPER=100 used to floor
    # to 20 with no signal. Surface it loudly so the requested-vs-served gap stops lying.
    _clamped = num > _SERPER_PAGE_MAX
    if _clamped:
        logger.warning(
            "[live_retriever] Serper num=%d exceeds the page max %d — clamping per-page to %d and "
            "paginating to the PG_SERPER_TOTAL_PER_QUERY budget.", num, _SERPER_PAGE_MAX, per_page,
        )
    # FX-17 (#1126): total-URL budget across pages. DEFAULT = one page (per_page) -> byte-identical to
    # the legacy single call; the benchmark slate raises PG_SERPER_TOTAL_PER_QUERY. Page count is
    # bounded by PG_SERPER_MAX_PAGES (small) and early-stops when a page returns < per_page.
    try:
        _total = max(per_page, int(os.getenv("PG_SERPER_TOTAL_PER_QUERY", str(per_page))))
    except ValueError:
        _total = per_page
    try:
        _max_pages = max(1, int(os.getenv("PG_SERPER_MAX_PAGES", "3")))
    except ValueError:
        _max_pages = 3
    _n_pages = min(_max_pages, -(-_total // per_page))  # ceil(total/per_page)

    # BB-002 (I-beatboth-fix-000 #1171): a sub-`per_page` page-1 count is NOT a reliable
    # end-of-results signal for an OFFSET-paginated SERP API — Serper routinely returns
    # 10 organic on page 1 even when page 2 has more, so the legacy `len(items) < per_page`
    # break short-circuited before page 2 and the PG_SERPER_TOTAL_PER_QUERY budget was never
    # reached (de-facto 10/query ceiling — chokepoint #4). When PG_SERPER_STOP_ON_ZERO_NEW=1
    # the loop keeps offset-paging until (a) budget met, (b) a page returns 0 NEW (post-dedup)
    # items, or (c) PG_SERPER_MAX_PAGES — the only RELIABLE end-of-results signals. DEFAULT OFF
    # = byte-identical (the legacy short-page break is preserved). Discovery-breadth only; every
    # new URL flows through the same fetch -> strict_verify -> 4-role chokepoint unchanged.
    _stop_on_zero_new = os.getenv("PG_SERPER_STOP_ON_ZERO_NEW", "0").strip() in (
        "1", "true", "True",
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    _pages_fetched = 0
    _last_latency = 0.0
    _last_bytes = 0
    _last_err = ""
    for _page in range(1, _n_pages + 1):
        items, ok, _last_latency, _last_bytes, _last_err = _serper_fetch_page(
            query, per_page, _page, headers
        )
        # FX-17 (#1126) iter-2: count EACH HTTP page request (a real Serper API call), not once
        # per query. P2 fix — api_calls['serper'] used to undercount paginated breadth.
        if api_calls is not None:
            api_calls["serper"] = api_calls.get("serper", 0) + 1
        if not ok:
            _trace_tool(
                "serper", target=query, status="fail", latency_ms=_last_latency,
                bytes_sent=len(query), bytes_received=_last_bytes,
                backend_used="serper_api_v1", error=_last_err, page=_page,
            )
            logger.warning("[live_retriever] Serper page %d failed for %r: %s",
                           _page, query[:60], _last_err)
            break  # fail-open: keep pages already accumulated; do not discard.
        _pages_fetched += 1
        _new = 0
        for it in items:
            u = it.get("url", "")
            if u and u not in seen:
                seen.add(u)
                out.append(it)
                _new += 1
        if len(out) >= _total:
            break  # budget met.
        if _stop_on_zero_new:
            # BB-002 (#1171): keep paging past a short page; stop only when a page
            # added 0 NEW (post-dedup) URLs — the reliable end-of-results signal.
            if _new == 0:
                break
        elif len(items) < per_page:
            break  # legacy (default OFF): short page -> assume no more results.
    _trace_tool(
        "serper", target=query, status="ok" if out or not _last_err else "fail",
        latency_ms=_last_latency, bytes_sent=len(query), bytes_received=_last_bytes,
        backend_used="serper_api_v1", result_count=len(out),
        pages_fetched=_pages_fetched, num_requested=num, per_page=per_page,
        page_max=_SERPER_PAGE_MAX, clamped=_clamped, total_budget=_total,
        stop_on_zero_new=_stop_on_zero_new,   # BB-002 (#1171): which stop policy ran
    )
    _trace_query("serper", query, [o["url"] for o in out])
    return out


def _s2_bulk_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    # I-safety-002b (#925) PR-2: record S2 backend attempt (lazy, best-effort).
    try:
        from src.polaris_graph.benchmark import pathB_capture as _pathb
        _pathb.record_retrieval_attempt("semantic_scholar")
    except Exception:
        pass
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "fields": "title,abstract,url,openAccessPdf,externalIds,year,venue",
        "limit": max(1, min(limit, 100)),
    }
    # I-meta-007b: wall-clock for the tool tracer (record-only).
    _t0 = time.time()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            r = c.get(S2_BULK_ENDPOINT, params=params, headers=headers)
        _latency_ms = (time.time() - _t0) * 1000.0
        if r.status_code != 200:
            _trace_tool(
                "s2", target=query, status="fail", latency_ms=_latency_ms,
                bytes_received=_resp_content_len(r),
                backend_used="semantic_scholar_api", error=f"HTTP {r.status_code}",
            )
            logger.warning(
                "[live_retriever] S2 returned %s for %r",
                r.status_code, query[:60],
            )
            _trace_query("semantic_scholar", query, [])
            return []
        data = r.json()
    except Exception as exc:
        _trace_tool(
            "s2", target=query, status="fail",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used="semantic_scholar_api", error=str(exc),
        )
        logger.warning("[live_retriever] S2 exception: %s", exc)
        _trace_query("semantic_scholar", query, [])
        return []
    papers = data.get("data", []) or []
    out: list[dict[str, Any]] = []
    for p in papers:
        oa_pdf = (p.get("openAccessPdf") or {}).get("url", "")
        ext_ids = p.get("externalIds") or {}
        doi = ext_ids.get("DOI", "")
        # Full-scale fix (cycle 11): prefer open-access PDF, fall back
        # to DOI-resolved URL. Never return a bare semanticscholar.org
        # landing page — those are T7 abstract-only stubs that
        # AccessBypass deliberately skips and that inflate the T7
        # fraction in corpus adequacy. If neither oa_pdf nor DOI is
        # available, skip the paper entirely.
        if oa_pdf:
            url = oa_pdf
        elif doi:
            url = f"https://doi.org/{doi}"
        else:
            # Bare S2 landing page would be returned here; skip.
            continue
        abstract = p.get("abstract") or ""
        out.append({
            "url": url,
            "title": p.get("title", "") or "",
            "snippet": (abstract[:500] if abstract else "")[:500],
            "source": "s2",
            "s2_paper_id": p.get("paperId", ""),
            "doi": doi,
            "year": p.get("year"),
            "venue": p.get("venue"),
        })
    # BB-004 (I-beatboth-fix-000 #1171): a HTTP-200 that yields ZERO usable papers
    # (all lacked oa_pdf + DOI, or `data` was empty) is a DEAD-BACKEND signal — the
    # legacy unconditional status="ok" reported it as success_rate=1.0 and masked the
    # collapse (15 S2 calls -> 0 results on drb_90 still showed success). LAW II
    # silent-downgrade fix: trace a DISTINCT "ok_zero" status + zero_yield=True so the
    # discovery_funnel / run-health surfaces it LOUDLY instead of as a clean success.
    # Telemetry/loudness ONLY — no evidence or verification path is touched; the
    # returned list is unchanged (empty), so downstream control flow is identical.
    _s2_zero_yield = len(out) == 0
    _trace_tool(
        "s2", target=query,
        status="ok_zero" if _s2_zero_yield else "ok",
        latency_ms=_latency_ms,
        bytes_received=_resp_content_len(r),
        backend_used="semantic_scholar_api", result_count=len(out),
        zero_yield=_s2_zero_yield,
    )
    _trace_query("semantic_scholar", query, [o["url"] for o in out])
    return out


_DOI_FROM_URL_RE = re.compile(
    r"(10\.\d{4,9}/[^\s?#]+?)(?:[?#]|/full|/abstract|/pdf|/meta|\.html|$)",
    re.IGNORECASE,
)


# BUG-M-17 (Codex full-scale pass 2): bounded body-text inspection
# for article-type signals. Reads high-signal regions of fetched
# content (meta tags, first 4KB, abstract/methods lead) for SR/MA,
# case-report, perspective, guidance markers. Used by the classifier
# as a SECONDARY signal when the title is truncated or non-diagnostic.
#
# NOT a full-body scan — Codex pass 2 explicitly warned:
# "do not scan the entire body naively for generic terms. Add a
#  bounded secondary narrative/SR signal extractor that inspects
#  high-signal fetched regions only."

# BUG-M-17b (Codex pass 3 BLOCKED fix): tightened to require context,
# not lone keywords. Explicit publisher metadata and section headers
# are trusted; lone body keywords are REJECTED because primary papers
# routinely cite prior systematic reviews, meta-analyses, case series,
# and guidelines in their background/methods without themselves being
# that article type.

# High-precision metadata patterns — trust these alone.
# Each entry: (regex_pattern, attribute_order_flexible)
_BODY_META_ARTICLE_TYPE_TAGS: tuple[str, ...] = (
    # HTML meta citation_article_type (both attr orders)
    r'<meta[^>]+citation_article_type[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+citation_article_type',
    r'<meta[^>]+article:section[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+article:section',
    r'<meta[^>]+prism\.section[^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+prism\.section',
    # JSON-LD
    r'"articleType"\s*:\s*"([^"]+)"',
)

# Publisher-embedded article-type HEADERS (top-of-page text).
# Frontiers "SYSTEMATIC REVIEW article", Nature "Article type: X" etc.
_BODY_PUBLISHER_HEADERS: tuple[str, ...] = (
    # Frontiers-style: "SYSTEMATIC REVIEW article" (all caps, with space + "article")
    r'\b(SYSTEMATIC REVIEW|META[- ]ANALYSIS|NETWORK META[- ]ANALYSIS|'
    r'CASE REPORT|CASE SERIES|PERSPECTIVE|EDITORIAL|'
    r'GUIDELINE|COMMENTARY|LETTER|BRIEF REPORT|OPINION) article\b',
    # Nature family: "Article type: <Type>"
    r'Article type:?\s*(Systematic Review|Meta-Analysis|Meta[- ]Analysis|'
    r'Network Meta[- ]Analysis|Case Report|Case Series|Perspective|'
    r'Editorial|Commentary|Letter|Brief Report|Opinion|Guideline)',
)

# Strong contextual patterns that need to co-occur to call SR_MA from body.
# NEVER fire on a lone keyword — require the declared-intent-or-method shape.
_BODY_SR_MA_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "objective: to conduct a systematic review / meta-analysis"
    r'objective[s]?:\s*to\s+(conduct|perform|undertake)\s+(a\s+)?(systematic review|meta[- ]analysis)',
    # "we conducted a systematic review"
    r'we\s+(conducted|performed|undertook)\s+(a\s+)?(systematic review|meta[- ]analysis)',
    # M-17c (Codex pass 4): "this SR/MA" must be followed by a
    # self-descriptive predicate within a short window. Rejects
    # citation-byline shapes like "this meta-analysis by Smith et al.
    # shaped the endpoint hierarchy" where SR/MA is the cited work,
    # not the fetched paper.
    r'this\s+(systematic review(?:\s+and\s+meta[- ]analysis)?|meta[- ]analysis)'
    r'\s+(aims?|evaluates?|examines?|investigates?|assesses?|reviews?|'
    r'reports?|presents?|summarizes?|synthesizes?|demonstrates?|'
    r'pools?|analyses|analyzes|combines?|explores?|'
    r'was\s+(conducted|performed|undertaken|registered|designed))\b',
    # M-17c: "PRISMA" with contextual search/selection/extraction/flow diagram
    r'PRISMA.{0,40}(search|selection|extraction|flow diagram)',
    r'(search|selection|extraction|flow diagram).{0,40}PRISMA',
    # M-17c (Codex pass 4): Cochrane tightened. Previously
    # "cochrane (systematic )?review" fired on "A Cochrane review
    # found..." citation in a primary trial. Now requires declarative
    # "this Cochrane review" + self-descriptive verb, OR registration
    # metadata (Cochrane Library CD-number).
    r'this\s+cochrane\s+(systematic\s+)?review\s+'
    r'(aims?|evaluates?|examines?|investigates?|assesses?|reports?|'
    r'presents?|summarizes?|was\s+(conducted|performed|registered))\b',
    # Cochrane Library registration ID (unique to Cochrane SRs)
    r'cochrane\s+(database|library).*CD\d{6}',
    # Conclusive meta-analytic methods signature: "pooled estimate" + "random-effects"
    r'(pooled (estimate|effect|odds ratio|risk ratio|hazard ratio)).{0,200}(random[- ]effects|fixed[- ]effects)',
    r'(random[- ]effects|fixed[- ]effects).{0,200}(pooled (estimate|effect|odds ratio|risk ratio|hazard ratio))',
)

# Case report body patterns — require declarative "we report/present"
# OR the X-year-old patient opener together with PATIENT-centered framing.
_BODY_CASE_REPORT_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "we report/describe/present a/the case"  (declarative)
    r'we\s+(report|describe|present)\s+(a|the)\s+case\b',
    # "here we report/describe a case"
    r'here\s+we\s+(report|describe|present)\s+(a|the)\s+case\b',
    # "we report a X-year-old patient" (opener)
    r'we\s+report\s+(a|an)\s+\d+[- ]year[- ]old',
    # Patient opener at very beginning of abstract (first 300 chars)
    # handled separately below — not in this tuple.
)

# Guideline body patterns — declarative intent.
# M-17c (Codex pass 4): tightened. Previously "this (clinical
# practice) guideline" and "consensus statement from" fired on
# citation-byline references like "according to a consensus
# statement from the Endocrine Society" in a primary trial.
# Now requires the fetched article to EITHER say "this clinical
# practice guideline" (fully qualified) OR be followed by a
# self-descriptive verb ("provides", "recommends", "was developed",
# "we developed").
# M-17d (Codex pass 5): the unanchored "(clinical practice )?
# guideline <verb>" still fired on dated external citations like
# "The 2025 clinical practice guideline recommends...". Now requires
# explicit "this" self-reference in front of the guideline noun.
# M-17e (Codex pass 6): "this guideline" alone is insufficient when
# the lead has already cited an external guideline (anaphoric
# reference). The detector now additionally rejects matches preceded
# by anaphoric-citation markers. Ambiguous verbs "summarizes" and
# "describes" have been removed because they apply equally to cited
# external guidelines. The bare "this clinical practice guideline"
# phrase must appear at sentence start (not as object of "followed").
# "updates?" added to close a recall miss.
_BODY_GUIDELINE_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "This clinical practice guideline" at sentence start — must be
    # subject, not object of "followed this guideline during trial"
    r'(?:^|[.!?]\s+|\n\s*)this\s+clinical\s+practice\s+guideline\b',
    # "This (clinical practice) guideline ... <verb>" — must be "this"
    # to reject dated/external citations (M-17d). Verb list tightened
    # to unambiguous self-authorship verbs (M-17e).
    r'this\s+(clinical\s+practice\s+)?guideline\s+'
    r'(provides|recommends|was\s+developed|is\s+intended|'
    r'presents|outlines|aims?|establishes|offers|updates?)',
    # "this consensus statement ... verb" (declarative, not cited)
    r'this\s+consensus\s+statement\s+'
    r'(provides|recommends|was\s+developed|outlines|presents|'
    r'aims?|establishes|summarizes)',
    # "Consensus statement from X: <descriptive phrase>" — structural
    # form of a consensus paper, NOT "according to a consensus
    # statement from". Require the consensus statement to be the
    # subject of a descriptive predicate.
    r'consensus\s+statement\s+from\s+(the\s+)?[A-Z][A-Za-z ]+\s+'
    r'(provides|recommends|was\s+developed|outlines|presents|aims?)',
    # "Expert consensus panel/group was convened/developed..."
    r'expert\s+consensus\s+(panel|group)\s+'
    r'(was\s+convened|developed|provides|recommends|presents)',
    # Declarative: "we developed this clinical/practical guidance"
    r'we\s+(developed|provide)\s+(this\s+)?(clinical|practical)\s+guidance',
)

# Perspective/commentary body patterns — declarative framing, not
# audience phrases alone.
_BODY_PERSPECTIVE_CONTEXT_PATTERNS: tuple[str, ...] = (
    # "In this perspective / commentary / editorial"
    r'in\s+this\s+(perspective|commentary|editorial|opinion)',
    # "This perspective examines / reviews"
    r'this\s+(perspective|commentary|editorial)\s+(examines|reviews|discusses|considers)',
    # "offer a perspective on"
    r'(offer|present|provide)\s+a\s+perspective\s+(on|for|of)',
)


def _classify_from_meta_keywords(captured: str) -> str:
    """Map a captured metadata/header value to a tier signal. Used
    for publisher-embedded explicit article-type tags (high precision).
    """
    c = (captured or "").lower().strip()
    if not c:
        return ""
    if any(k in c for k in ("systematic review", "meta-analysis",
                            "meta analysis", "cochrane",
                            "network meta-analysis",
                            "network meta analysis")):
        return "SR_MA"
    if "case report" in c or "case series" in c:
        return "CASE_REPORT"
    if "perspective" in c:
        return "PERSPECTIVE"
    if "guideline" in c or "consensus" in c:
        return "GUIDELINE"
    if "editorial" in c or "commentary" in c:
        return "PERSPECTIVE"
    if "letter" in c or "opinion" in c or "brief report" in c:
        return "PERSPECTIVE"
    return ""


def _detect_article_type_from_body(raw_content: str) -> str:
    """Bounded body-text inspection for article-type signal.

    Returns one of: "SR_MA", "CASE_REPORT", "PERSPECTIVE", "GUIDELINE",
    or "" (no signal). Inspects only the first 8KB of content to keep
    cost bounded.

    M-17b (Codex pass 3 BLOCKED): tightened to avoid false positives
    from primary papers citing prior systematic reviews / case reports
    as background. Now requires either:

    (P1) explicit publisher-embedded article-type metadata
         (HTML meta tag, JSON-LD articleType, Nature-style "Article
         type:" header, Frontiers-style "SYSTEMATIC REVIEW article"
         section marker), OR
    (P2) a declarative contextual body pattern that indicates the
         fetched article IS the given type (not merely citing it).

    Lone keywords like "systematic review" or "case report" alone
    are NOT sufficient — primary trial abstracts commonly cite prior
    reviews in their background, and primary-study methods often
    mention excluding case series.
    """
    if not raw_content:
        return ""
    # Bound the scan window
    head = raw_content[:8000]
    lead = head[:4000]
    lead_lower = lead.lower()

    # ── Priority 1a: explicit meta / JSON-LD article-type tags
    for pattern in _BODY_META_ARTICLE_TYPE_TAGS:
        m = re.search(pattern, head, re.IGNORECASE)
        if m and m.lastindex:
            signal = _classify_from_meta_keywords(m.group(1))
            if signal:
                return signal

    # ── Priority 1b: publisher-embedded article-type headers
    # These are ALL-CAPS or structured banners at the page top
    # (Frontiers "SYSTEMATIC REVIEW article", Nature "Article type: X")
    for pattern in _BODY_PUBLISHER_HEADERS:
        m = re.search(pattern, head, re.IGNORECASE)
        if m and m.lastindex:
            signal = _classify_from_meta_keywords(m.group(1))
            if signal:
                return signal

    # ── Priority 2: declarative body patterns (must co-occur with
    # study-type context, not lone keywords)
    for pattern in _BODY_SR_MA_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "SR_MA"
    for pattern in _BODY_CASE_REPORT_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "CASE_REPORT"
    # "X-year-old patient" opener as first significant content in abstract
    # (look only in first 500 chars to avoid methods/exclusion-criteria false positives)
    opener = lead_lower[:500]
    if re.search(
        r'^\s*(a|this)\s+\d+[- ]year[- ]old\s+(man|woman|male|female|patient)\s+(presented|was\s+admitted|with)',
        opener,
    ):
        return "CASE_REPORT"
    # M-17e (Codex pass 6): anaphoric-citation guard. If the lead
    # contains a citation-style reference to an external guideline
    # ("followed the 2025 ADA guideline", "according to the NICE
    # guideline"), a subsequent "This guideline <verb>" is likely
    # anaphoric to that external citation rather than self-declarative.
    # We therefore require the guideline match to precede, not follow,
    # any such external-guideline citation in the lead.
    _ANAPHORIC_GUIDELINE_CITATION = re.compile(
        r'(?:followed|following|according\s+to|citing|cited|per|'
        r'as\s+recommended\s+by|as\s+per|based\s+on|in\s+line\s+with)'
        r'\s+(?:the\s+)?(?:\d{4}\s+)?(?:[a-z]+\s+)?(?:clinical\s+practice\s+)?'
        r'guidelines?\b',
        re.IGNORECASE,
    )
    for pattern in _BODY_GUIDELINE_CONTEXT_PATTERNS:
        m = re.search(pattern, lead_lower, re.IGNORECASE)
        if m:
            # Reject if an external-guideline citation appears in the
            # preceding 300 chars (anaphoric reference) — e.g. "followed
            # the 2025 ADA guideline ... This guideline summarizes".
            preceding = lead_lower[max(0, m.start() - 300): m.start()]
            if _ANAPHORIC_GUIDELINE_CITATION.search(preceding):
                continue
            return "GUIDELINE"
    for pattern in _BODY_PERSPECTIVE_CONTEXT_PATTERNS:
        if re.search(pattern, lead_lower, re.IGNORECASE):
            return "PERSPECTIVE"

    return ""


def _extract_title_from_content(content: str) -> str:
    """Extract the full paper title from fetched page content.

    M-13 fallback (Codex pass 13): OpenAlex DOI lookup doesn't work
    for MDPI URLs (they don't embed DOI in URL path). And OpenAlex
    title-search with a truncated Serper snippet often misses the
    right paper. As a third recovery path, parse the fetched HTML
    or markdown for the real title.

    - Jina Reader and Crawl4AI often emit markdown with `Title: ...`
      or `# Title` on the first line.
    - Direct HTTP returns HTML; look for `<title>...</title>` tag.
    - trafilatura output is plain text; the first significant line
      is usually the title.

    Returns empty string if no plausible title found.
    """
    if not content:
        return ""
    # Jina/Crawl4AI "Title: X" pattern
    m = re.search(r"^\s*Title:\s*(.+?)\s*$", content[:2000], re.MULTILINE)
    if m:
        t = m.group(1).strip()
        if 10 <= len(t) <= 500:
            return t
    # Markdown H1
    m = re.search(r"^\s*#\s+(.+?)\s*$", content[:2000], re.MULTILINE)
    if m:
        t = m.group(1).strip()
        if 10 <= len(t) <= 500 and "content" not in t.lower()[:30]:
            return t
    # HTML <title> tag
    m = re.search(r"<title[^>]*>(.+?)</title>", content[:4000],
                  re.IGNORECASE | re.DOTALL)
    if m:
        t = m.group(1).strip()
        # Strip journal suffixes like " — Frontiers", " | MDPI"
        t = re.sub(r"\s*[|\-—–]\s*(mdpi|frontiers|nejm|jama|lancet|"
                   r"bmc|springer|nature|science|cell|plos).*$", "",
                   t, flags=re.IGNORECASE)
        if 10 <= len(t) <= 500:
            return t
    return ""


def _extract_doi_from_url(url: str) -> str:
    """Extract a DOI from a URL if present. Handles Frontiers
    (`/10.3389/fphar.2022.1016639/full`), JAMA, NEJM, OUP, Sage,
    ACS, RSC, Wiley, and direct `doi.org/...` URLs. MDPI URLs don't
    embed DOIs; return empty there.
    """
    if not url:
        return ""
    # Direct DOI URL
    u = url.strip()
    if "doi.org/" in u.lower():
        idx = u.lower().find("doi.org/") + len("doi.org/")
        doi = u[idx:].split("?")[0].split("#")[0].rstrip("/")
        return doi
    # Embedded DOI in publisher URLs
    m = _DOI_FROM_URL_RE.search(u)
    if m:
        return m.group(1).rstrip("/").rstrip(".")
    return ""


def _candidate_oa_hints(metadata: Any) -> tuple[str, str]:
    """I-meta-007c: pull (doi, pmid) hints from a candidate's metadata dict.

    S2 candidates carry ``metadata["doi"]`` (line ~2001); PMIDs are not in the
    S2 dict today but the slot is honoured for forward-compat / testability.
    Returns ("", "") for non-dict / missing metadata. NEVER raises.

    Diff-gate P2a: the whole body is wrapped in a fail-open try/except returning
    ("", "") on ANY error, matching the resolver helpers' fail-open contract —
    a malformed metadata object must never break the retrieval loop."""
    try:
        if not isinstance(metadata, dict):
            return "", ""
        doi = str(metadata.get("doi") or "").strip()
        pmid = str(metadata.get("pmid") or "").strip()
        return doi, pmid
    except Exception:  # noqa: BLE001 — fail-OPEN, never break retrieval.
        return "", ""


def _authority_cache_init() -> None:
    """Create the authority-enrich cache with a VERSIONED migration (C5).

    Not a CREATE-IF-NOT-EXISTS no-op: a stale cache whose recorded schema
    version is older than AUTHORITY_CACHE_SCHEMA_VERSION is rebuilt rather than
    silently used with missing columns.
    """
    AUTHORITY_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            " id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
        )
        row = conn.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
        existing = row[0] if row else 0
        table_present = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='authority_enrich'"
        ).fetchone() is not None
        # Migrate whenever the recorded version is older than the current one
        # (existing=0 means an unversioned/legacy cache). Drop + rebuild the
        # payload table (the cache is a rebuildable accelerator, never the
        # source of truth) — NOT a CREATE-IF-NOT-EXISTS no-op (C5).
        if table_present and existing < AUTHORITY_CACHE_SCHEMA_VERSION:
            conn.execute("DROP TABLE IF EXISTS authority_enrich")
            logger.warning(
                "[live_retriever] authority cache schema %d < %d — migrating "
                "(rebuild)", existing, AUTHORITY_CACHE_SCHEMA_VERSION,
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS authority_enrich ("
            " key TEXT PRIMARY KEY,"
            " payload_json TEXT NOT NULL,"
            " fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO schema_meta (id, version) VALUES (1, ?)"
            " ON CONFLICT(id) DO UPDATE SET version = excluded.version",
            (AUTHORITY_CACHE_SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


# I-ready-017 #1134 (Codex diff-gate P1): run the versioned migration once before
# the FIRST cache access (read OR write), so a stale v1 payload — which predates
# the journal_only is_retracted/openalex_venue fields — is rebuilt away on the
# READ path too, never served unchanged. Previously the migration ran only on
# _authority_cache_put, so a get-before-put returned a stale payload and a cached
# retracted journal article could pass the journal_only predicate.
_authority_cache_migrated = False


def _ensure_authority_cache_migrated() -> None:
    global _authority_cache_migrated
    if not _authority_cache_migrated:
        _authority_cache_init()
        _authority_cache_migrated = True


def _authority_cache_get(key: str) -> Optional[dict[str, Any]]:
    _ensure_authority_cache_migrated()
    if not AUTHORITY_CACHE_DB.exists():
        return None
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        row = conn.execute(
            "SELECT payload_json FROM authority_enrich WHERE key = ?", (key,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if not row:
        return None
    import json
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def _authority_cache_put(key: str, payload: dict[str, Any]) -> None:
    import json
    _ensure_authority_cache_migrated()
    conn = sqlite3.connect(AUTHORITY_CACHE_DB)
    try:
        conn.execute(
            "INSERT INTO authority_enrich (key, payload_json) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET payload_json = excluded.payload_json,"
            " fetched_at = CURRENT_TIMESTAMP",
            (key, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


def _openalex_fetch_source(
    client: httpx.Client, source_id: str
) -> dict[str, Any]:
    """Separate /sources/{id} fetch for venue-level authority fields (C5).

    Returns the summary_stats / apc_prices / is_core / is_in_doaj subset, or
    {} on any failure (the model degrades to LOW confidence — never fabricates).
    """
    if not source_id:
        return {}
    sid = source_id.rsplit("/", 1)[-1]  # accept full URL or bare S-id
    if not sid.startswith("S"):
        return {}
    resp = client.get(
        f"{OPENALEX_SOURCES_ENDPOINT}/{sid}",
        params={"select": OPENALEX_SOURCES_SELECT},
    )
    if resp.status_code != 200:
        return {}
    src = resp.json()
    if not isinstance(src, dict):
        return {}
    return {
        "is_core": src.get("is_core"),
        "is_in_doaj": src.get("is_in_doaj"),
        "apc_prices": src.get("apc_prices"),
        "summary_stats": src.get("summary_stats") or {},
    }


def _build_authority_signals_dict(
    work: dict[str, Any], source_fields: dict[str, Any]
) -> dict[str, Any]:
    """Build the additive AuthoritySignals payload (C1/C5) as a plain dict.

    Stored as a dict so the live-path enrich return value stays JSON-cacheable;
    live_retriever reconstructs the AuthoritySignals dataclass at classify time.
    Missing fields stay absent/None -> the authority model returns LOW
    confidence (fail-honest, never fabricate).
    """
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    # First resolved institution (ROR) from authorships.
    ror_id = ""
    inst_type = ""
    country_code = ""
    for authorship in work.get("authorships") or []:
        for inst in authorship.get("institutions") or []:
            if inst.get("ror"):
                ror_id = inst.get("ror") or ""
                inst_type = inst.get("type") or ""
                country_code = inst.get("country_code") or ""
                break
        if ror_id:
            break

    stats = source_fields.get("summary_stats") or {}
    venue_summary_stats: dict[str, Any] = {}
    if isinstance(stats, dict):
        if "h_index" in stats:
            venue_summary_stats["h_index"] = stats.get("h_index")
        if "2yr_mean_citedness" in stats:
            venue_summary_stats["2yr_mean_citedness"] = stats.get("2yr_mean_citedness")

    return {
        "cited_by_count": work.get("cited_by_count"),
        "source_id": source.get("id", "") or "",
        "venue_summary_stats": venue_summary_stats or None,
        "is_core": source_fields.get("is_core"),
        "is_in_doaj": source_fields.get("is_in_doaj"),
        "apc_prices": source_fields.get("apc_prices"),
        "publication_year": work.get("publication_year"),
        "ror_id": ror_id,
        "institution_type": inst_type,
        "country_code": country_code,
    }


def _openalex_enrich(url: str, title: str) -> dict[str, Any]:
    """Query OpenAlex for pub_type / source_type / is_peer_reviewed.

    M-13 (BUG-M-13, Codex pass 13): prefer DOI-based lookup over
    title search. When the URL embeds a DOI (Frontiers, JAMA, NEJM,
    OUP, etc.), OpenAlex's /works/doi:<doi> endpoint is exact and
    always returns the full display_name. Title-based search often
    fails when Serper truncated the title or returned a variant
    that OpenAlex doesn't index. Falls back to title search when no
    DOI can be extracted (e.g., MDPI URLs, publisher blog posts).
    """
    try:
        doi = _extract_doi_from_url(url)
        # Diff-gate P2-B: READ the authority-enrich cache first, keyed by the
        # stable pre-fetch identifier (DOI when present, else the URL). A hit
        # returns the frozen enrich dict and AVOIDS the OpenAlex /works +
        # /sources round-trip entirely (the read path the cache exists for).
        enrich_cache_key = f"doi:{doi}" if doi else f"url:{url}"
        cached = _authority_cache_get(enrich_cache_key)
        if isinstance(cached, dict) and cached:
            return cached
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT) as c:
            if doi:
                # Exact DOI lookup — most reliable. OpenAlex accepts
                # both the bare DOI and the URL form; use bare DOI.
                # Phase 0a (C5): request the root-level authority select=.
                r = c.get(
                    f"{OPENALEX_ENDPOINT}/doi:{doi}",
                    params={"select": OPENALEX_WORKS_SELECT},
                )
                if r.status_code != 200:
                    # Fall back to title search if DOI not indexed
                    r = c.get(
                        OPENALEX_ENDPOINT,
                        params={
                            "search": (title or url)[:200],
                            "per-page": 1,
                            "select": OPENALEX_WORKS_SELECT,
                        },
                    )
                    if r.status_code != 200:
                        return {}
                    data = r.json()
                    results = data.get("results", [])
                    if not results:
                        return {}
                    work = results[0]
                else:
                    work = r.json()  # single-work response from /works/doi
            else:
                r = c.get(
                    OPENALEX_ENDPOINT,
                    params={
                        "search": (title or url)[:200],
                        "per-page": 1,
                        "select": OPENALEX_WORKS_SELECT,
                    },
                )
                if r.status_code != 200:
                    return {}
                data = r.json()
                results = data.get("results", [])
                if not results:
                    return {}
                work = results[0]

            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}

            # Phase 0a (C5): SEPARATE /sources/{id} fetch for venue-level
            # authority fields, keyed by primary_location.source.id. Absent
            # source / failed fetch -> empty -> LOW confidence downstream.
            source_id = source.get("id", "") or ""
            source_fields = _openalex_fetch_source(c, source_id)

        # Build the additive AuthoritySignals payload (dict form, cacheable).
        authority_signals = _build_authority_signals_dict(work, source_fields)

        enrich = {
            "openalex_pub_type": work.get("type", "") or "",
            "openalex_source_type": source.get("type", "") or "",
            "is_peer_reviewed": bool(
                work.get("type") in ("article", "review")
                and source.get("type") == "journal"
            ),
            # I-ready-017 #1134 (Codex diff-gate P1-2/P1-3): carry the journal
            # VENUE (for the distinct-journal adequacy count) and the RETRACTION
            # flag (so the journal_only predicate can reject retracted articles)
            # into the enrich dict -> sidecar. ADDITIVE; legacy consumers ignore.
            "openalex_venue": (source.get("display_name", "") or ""),
            "is_retracted": bool(work.get("is_retracted", False)),
            # Codex diff-gate P2: carry the OpenAlex work DOI so the journal_only
            # sidecar can credit an anchor discovered via a Serper/URL-only path
            # (not just SearchCandidate metadata). Normalized (no scheme).
            "doi": str(work.get("doi", "") or "").replace("https://doi.org/", "").replace("http://doi.org/", ""),
            "openalex_id": work.get("id", ""),
            # BUG-M-12 (Codex pass 12): preserve OpenAlex's full
            # display_name. Serper snippet titles are often truncated
            # mid-title, losing "systematic review and meta-analysis",
            # "perspective for primary care providers", etc. suffixes
            # that the classifier needs to demote false T1s.
            "openalex_full_title": work.get("display_name", "") or "",
            # Phase 0a (C1/C5): the additive authority payload, carried at
            # :1751 -> :1789 into ClassificationSignals.authority.
            "authority_signals": authority_signals,
        }
        # Diff-gate P2-B: WRITE the whole enrich dict under the SAME stable
        # pre-fetch key the read path uses, so a later lookup is a true cache
        # hit that skips the network (the read path is now exercised).
        _authority_cache_put(enrich_cache_key, enrich)
        return enrich
    except Exception as exc:
        logger.debug("[live_retriever] OpenAlex enrich failed for %r: %s", url, exc)
        return {}


def _env_float(name: str, default: float) -> float:
    """Positive-*finite*-float env knob with a safe fallback (LAW VI).

    Non-finite overrides (``inf``/``-inf``/``nan``) fall back to ``default``:
    ``float("inf")`` parses fine and is ``> 0``, but feeding it to e.g.
    ``threading.Thread.join(timeout=...)`` raises ``OverflowError`` on
    Windows (I-bug-116 / #556).
    """
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_int(name: str, default: int) -> int:
    """Positive-int env knob with a safe fallback (LAW VI — no hardcode)."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _post_fetch_loop_budget(fetch_cap: int) -> float:
    """I-ready-003 (#1074) P1: the post-fetch loop wall-clock budget, SCALED with ``fetch_cap``.

    The loop classifies all ~``fetch_cap`` candidates serially (each paying an OpenAlex enrich
    round-trip). A FIXED budget that does not scale with ``fetch_cap`` silently truncates the corpus at
    full cap (the I-cap-005 ~40-URL silent-throttle class, one layer deeper). Returns
    ``max(PG_POST_FETCH_LOOP_BUDGET floor, fetch_cap * PG_POST_FETCH_PER_URL_BUDGET)`` — byte-identical
    for small caps (the 900s floor wins), and a conservative operator env can no longer silently win
    because the ``fetch_cap`` term floors it. Pure (env-only); unit-testable."""
    return max(
        _env_float("PG_POST_FETCH_LOOP_BUDGET", 900.0),
        max(0, int(fetch_cap)) * _env_float("PG_POST_FETCH_PER_URL_BUDGET", 4.0),
    )


class CorpusTruncationError(RuntimeError):
    """I-arch-004 F18b (#1255): raised when the post-fetch loop budget breaks
    mid-corpus AND ``PG_CORPUS_TRUNCATION_POLICY=fail_closed``.

    The post-fetch loop can hit its wall-clock deadline before classifying every
    fetched candidate; the legacy behavior set a fail-loud ``corpus_truncated``
    flag and BROKE, leaving a PARTIAL corpus to flow into generation (§-1.3: a
    silent recall degradation — a "1000-URL" run could be composed from the first
    few hundred sources with no in-run gate). ``fail_closed`` raises this BEFORE
    any generator token is billed so a truncated corpus never ships. The post-hoc
    scorer backstop (``score_run._check_polaris_gate``) still rejects a truncated
    manifest under the default ``warn`` policy; this error is the additive in-run
    gate."""


def _corpus_truncation_policy() -> str:
    """Read ``PG_CORPUS_TRUNCATION_POLICY`` (LAW VI). One of:

      - ``warn``   (DEFAULT): legacy behavior — set ``corpus_truncated`` and BREAK.
                   Byte-identical to pre-F18b. The post-hoc scorer backstop is the
                   gate; the in-run report still composes over the partial corpus.
      - ``repair``: do NOT break at the deadline; CONTINUE processing the remaining
                   candidates so recall is preserved (§-1.3 weight-not-filter). The
                   per-candidate Layer-1 bound (``_bounded_openalex_enrich``,
                   PG_OPENALEX_ENRICH_DEADLINE) still prevents a single wedged
                   candidate from hanging the run, so dropping the loop-level
                   deadline does not reintroduce the #554 hang.
      - ``fail_closed``: RAISE ``CorpusTruncationError`` at the deadline so a
                   truncated corpus never reaches generation (no tokens billed).

    Unknown / empty value falls back to ``warn`` (byte-identical default)."""
    raw = (os.getenv("PG_CORPUS_TRUNCATION_POLICY", "") or "").strip().lower()
    if raw in ("warn", "repair", "fail_closed"):
        return raw
    if raw:
        logger.warning(
            "[live_retriever] PG_CORPUS_TRUNCATION_POLICY=%r is not one of "
            "warn/repair/fail_closed — using 'warn' (legacy default)",
            raw,
        )
    return "warn"


def _bounded_openalex_enrich(
    url: str, title: str, stats: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Wall-clock-bounded wrapper around `_openalex_enrich` (GH #554).

    `_openalex_enrich` issues `httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT)`
    requests. `httpx`'s timeout bounds each request *phase*
    (connect/read/write/pool) but NOT total request time, so a wedged or
    byte-trickling OpenAlex response (slowloris pattern) is never
    hard-bounded. The post-`parallel_fetch` candidate loop in
    `run_live_retrieval` is synchronous, so one wedged enrich call hangs the
    whole run before it reaches any terminal verdict (#554 — demo-fatal).

    Run the call in a daemon thread and abandon it past
    `PG_OPENALEX_ENRICH_DEADLINE` (default 45 s = 2x the 20 s httpx phase
    timeout, covering the DOI-lookup + title-search-fallback double request,
    + margin). Enrichment is optional — the tier classifier degrades
    gracefully to title/content signals without it. `stats["enrich_timeouts"]`
    is incremented on timeout so the caller can fail-fast.
    """
    deadline = _env_float("PG_OPENALEX_ENRICH_DEADLINE", 45.0)
    holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            holder["value"] = _openalex_enrich(url, title)
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    worker = threading.Thread(
        target=_worker, name="openalex-enrich", daemon=True,
    )
    worker.start()
    worker.join(timeout=deadline)
    if worker.is_alive():
        if stats is not None:
            stats["enrich_timeouts"] = stats.get("enrich_timeouts", 0) + 1
        logger.warning(
            "[live_retriever] OpenAlex enrich exceeded %.0fs for %s — "
            "skipping enrichment (daemon thread abandoned)",
            deadline, url[:80],
        )
        return {}
    if "error" in holder:
        logger.debug(
            "[live_retriever] OpenAlex enrich raised for %r: %s",
            url, holder["error"],
        )
        return {}
    return holder.get("value", {})


# ─────────────────────────────────────────────────────────────────────────────
# Content fetching (very basic — just enough to get tier + evidence)
# ─────────────────────────────────────────────────────────────────────────────


# I-meta-002-q1d (#954): table-aware linearization. _strip_html flattens <table> markup to running text,
# so a result-table cell loses its header association ("Discontinuation due to nausea ... 3.8%" collapses to
# a floating "3.8") and integer / %-without-decimal cells become unanchored — strict_verify can then only
# verify the loose decimals that survive in prose, under-verifying the richest clinical data (results tables).
# This no-network pass detects <table> blocks and linearizes each data row as "header: cell | header: cell"
# BEFORE flattening, so the cell keeps its column header in the text the provenance window captures.
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
# Capture each cell WITH its tag (th vs td) so a column-header row is distinguishable from a row-header.
_CELL_TAGGED_RE = re.compile(r"<(t[hd])\b[^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)
# colspan/rowspan shift columns → index-zip would mis-align → degrade (Codex diff-gate iter-1 P1).
_SPAN_ATTR_RE = re.compile(r"\b(?:col|row)span\s*=", re.IGNORECASE)


def _cell_text(cell_html: str) -> str:
    """Strip inner tags from a single cell and collapse whitespace."""
    txt = re.sub(r"<[^>]+>", " ", cell_html)
    return re.sub(r"\s+", " ", txt).strip()


def _parse_row_cells(row_html: str) -> list[tuple[str, str]]:
    """Return [(tag, text)] for each <th>/<td> in the row (tag lowercased)."""
    return [(m.group(1).lower(), _cell_text(m.group(2))) for m in _CELL_TAGGED_RE.finditer(row_html)]


def linearize_html_tables(html: str) -> str:
    """Return result-table rows linearized so table numbers survive in text WITH their column header when —
    and ONLY when — the source unambiguously declares one. Pure regex, no network, fail-open ('').

    Header:cell association is emitted ONLY for the CANONICAL column-header table: the first non-empty row
    is ENTIRELY <th> with non-empty header text, the table has >1 column, NO colspan/rowspan anywhere, and
    <th> appears in NO other row (so it is column headers, not per-row row-headers). EVERY other shape —
    span tables, headerless tables, row-header / mixed <th>+<td> data rows, empty-<th>-before-data — DEGRADES
    to plain ' | '-joined cells. Joined still surfaces the number next to its row label, but a cell can NEVER
    receive a column header the source did not declare (no fabricated provenance). This single conservative
    rule covers the Codex diff-gate P1s (colspan/rowspan, headerless-multirow, row-header, empty-th-before-
    data) without enumerating each."""
    try:
        out_rows: list[str] = []
        for table_html in _TABLE_RE.findall(html or ""):
            raw_rows = _ROW_RE.findall(table_html)
            if not raw_rows:
                continue
            rows = [_parse_row_cells(r) for r in raw_rows]
            rows = [r for r in rows if any(text for _tag, text in r)]  # drop all-empty rows
            if not rows:
                continue

            def _join(r: list[tuple[str, str]]) -> str:
                return " | ".join(text for _tag, text in r if text)

            first = rows[0]
            canonical = (
                not _SPAN_ATTR_RE.search(table_html)              # no colspan/rowspan
                and len(first) > 1                                # multi-column
                and all(tag == "th" for tag, _t in first)         # row 0 is ENTIRELY <th> (column headers)
                and all(text for _tag, text in first)             # ... with non-empty header text
                and not any(tag == "th" for r in rows[1:] for tag, _t in r)  # <th> only in row 0
            )
            if not canonical:
                # DEGRADE: every ambiguous shape joins plainly — never a fabricated header:cell.
                out_rows.extend(j for r in rows if (j := _join(r)))
                continue
            # CANONICAL column-header table: zip each data row to the <th> header row by column index.
            headers = [text for _tag, text in first]
            for row in rows[1:]:
                cells = [text for _tag, text in row]
                pairs = [
                    f"{headers[j]}: {cells[j]}"
                    if j < len(headers) and headers[j] and cells[j]
                    else cells[j]
                    for j in range(len(cells))
                ]
                joined = " | ".join(p for p in pairs if p)
                if joined:
                    out_rows.append(joined)
        return "\n".join(r for r in out_rows if r)
    except Exception:  # noqa: BLE001 — additive observability; never break fetch on a malformed table
        return ""


_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Bound the captured JSON-LD so a pathological page cannot balloon the payload
# the classifier scans (the junk patterns only need the @type marker near the top).
_JSONLD_MAX_CHARS = 20000


def _extract_jsonld_blocks(raw_html: str) -> str:
    """Capture the raw <script type="application/ld+json"> block contents from
    the RAW fetched HTML — BEFORE _strip_html() deletes every <script> block.

    Diff-gate P1-C: the structural junk-detection classifier (Signal C,
    news_article/login_wall/press_release classes) scans JSON-LD strings such as
    `"@type":"NewsArticle"` that live ONLY inside ld+json <script> blocks. Those
    blocks are destroyed by _strip_html (line removing <script>...</script>), so
    the demotion never fires unless the JSON-LD is extracted FIRST and routed to
    ClassificationSignals.structured_jsonld separately from the stripped body.

    Returns the concatenated block contents (bounded), or "" when the input is
    not raw HTML (e.g. Jina markdown / Crawl4AI cleaned text already had its
    <script> blocks removed upstream) — honestly empty, never fabricated. Pure
    regex, no network, fail-open ("").
    """
    if not raw_html or "ld+json" not in raw_html.lower():
        return ""
    try:
        blocks = [m.group(1).strip() for m in _JSONLD_SCRIPT_RE.finditer(raw_html)]
        joined = "\n".join(b for b in blocks if b)
        return joined[:_JSONLD_MAX_CHARS]
    except Exception:  # noqa: BLE001 — additive structural signal; never break fetch
        return ""


def _readability_extract(html: str) -> str:
    """BB5-C05 (#1177): readability-lxml fallback extractor. trafilatura returns
    empty trees on 30-50% of fetched pages; readability's article-detection
    recovers many of them. Guarded import (skip-with-log when the optional dep
    is absent — never break `_strip_html`). Returns extracted plain text or ""."""
    if not html:
        return ""
    try:
        from readability import Document  # type: ignore
    except ImportError:
        logger.debug(
            "[live_retriever] BB5-C05 readability-lxml not installed — "
            "skipping fallback extractor"
        )
        return ""
    try:
        summary_html = Document(html).summary(html_partial=True)
    except Exception as exc:  # noqa: BLE001 — readability runs lxml; a parse
        # error must never break the strip path. (A C-level SIGSEGV would still
        # escape, but readability only runs AFTER trafilatura already declined,
        # and on the SAME doc that passed the trafilatura size gate.)
        logger.debug(
            "[live_retriever] BB5-C05 readability extract error (%s)",
            type(exc).__name__,
        )
        return ""
    # readability returns cleaned HTML — strip residual tags to plain text.
    no_tags = re.sub(r"<[^>]+>", " ", summary_html or "")
    no_tags = re.sub(r"\s+", " ", no_tags)
    return no_tags.strip()


def _strip_html(html: str) -> str:
    """Extract visible text from HTML via trafilatura (BB5-S03 SIGSEGV-guarded),
    then a readability-lxml fallback (BB5-C05), then a regex fallback, then APPEND
    table-aware linearized rows (#954) so result-table cells survive with their
    column headers regardless of how the base extractor flattened the tables.
    Default-ON; PG_FETCH_TABLE_LINEARIZE=0 disables the append."""
    base = ""
    # BB5-S03 (#1177): route trafilatura through the SIGSEGV-mitigated shared
    # guard (size-bounds the HTML; optional subprocess containment) instead of a
    # bare `trafilatura.extract` under `except Exception: pass` — a libxml2
    # C-crash on a pathological doc is NOT a catchable Python exception.
    try:
        from src.tools.access_bypass import safe_trafilatura_extract
        extracted = safe_trafilatura_extract(html) or ""
        if extracted:
            base = extracted
    except Exception:  # noqa: BLE001 — import/guard failure must never break strip
        pass
    if not base:
        # BB5-C05 (#1177): trafilatura returned an empty tree — try the
        # readability-lxml article extractor before the last-resort regex strip.
        #
        # BB5-S03 iter-2 (#1177, Codex P1-S03): readability-lxml ALSO parses via
        # lxml/libxml2 — the SAME C-crash surface trafilatura was size-gated away
        # from. An oversized/suspect doc that skipped trafilatura must therefore
        # ALSO skip readability and go straight to the regex strip, or it just
        # re-enters libxml2 by another door (same SIGSEGV risk). Gate on the
        # SHARED size predicate. Import the FUNCTION (not the constant value) so
        # the deploy-slate PG_TRAFILATURA_MAX_HTML_CHARS override + test monkey-
        # patch are read at call time, keeping ONE source of truth for the bound.
        _extract_safe = True
        try:
            from src.tools.access_bypass import _html_is_extract_safe
            _extract_safe = _html_is_extract_safe(html)
        except Exception:  # noqa: BLE001 — import/guard failure must never break strip
            _extract_safe = True
        if _extract_safe:
            base = _readability_extract(html)
    if not base:
        # Fallback: strip tags + collapse whitespace
        no_tags = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        no_tags = re.sub(r"<style[^>]*>.*?</style>", " ", no_tags, flags=re.DOTALL | re.IGNORECASE)
        no_tags = re.sub(r"<[^>]+>", " ", no_tags)
        no_tags = re.sub(r"\s+", " ", no_tags)
        base = no_tags.strip()
    if os.getenv("PG_FETCH_TABLE_LINEARIZE", "1").strip().lower() not in ("0", "false", "no", "off", ""):
        tables = linearize_html_tables(html)
        if tables:
            base = (base + "\n\n" + tables).strip() if base else tables
    return base


def _fetch_content_httpx_naive(
    url: str, max_chars: int
) -> tuple[str, bool, str, str, str]:
    """Legacy naive httpx fetcher. Kept as emergency fallback when
    AccessBypass is unavailable (tests that don't want Crawl4AI browser
    spawning, or sandboxes without Playwright).

    Returns (content, ok, title, body_type, jsonld). Diff-gate P1-C: `jsonld`
    is the raw ld+json <script> block contents extracted from the RAW HTML
    BEFORE _strip_html deletes the <script> blocks (empty when the page carries
    no JSON-LD)."""
    try:
        with httpx.Client(
            timeout=DEFAULT_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (POLARIS-honest-rebuild/1.0) "
                    "research-assistant"
                ),
                # BUG-BROTLI-R8d: httpx/aiohttp advertise `br` by default
                # but can't always decode it. Forbid it so servers don't
                # return Brotli-encoded bodies we can't read.
                "Accept-Encoding": "gzip, deflate",
            },
        ) as c:
            r = c.get(url)
        if r.status_code != 200:
            return "", False, "", "", ""
        ctype = (r.headers.get("content-type", "") or "").lower()
        raw = r.text if "text" in ctype or "html" in ctype or "json" in ctype else ""
        if not raw and r.content:
            raw = r.content.decode("utf-8", errors="ignore")
        # BUG-M-13/M-14: extract title from raw HTML BEFORE stripping
        # (the <title> tag is gone after _strip_html).
        extracted_title = _extract_title_from_content(raw)
        # BUG-M-17: detect article-type from bounded body region.
        body_type = _detect_article_type_from_body(raw)
        # Diff-gate P1-C: capture raw ld+json BEFORE _strip_html removes <script>.
        jsonld = _extract_jsonld_blocks(raw)
        content = _strip_html(raw)[:max_chars]
        # BB5-C05 iter-2 (#1177, Codex P2): mirror the parallel/AccessBypass
        # path's "fetched-200-but-empty-extract" bucket on the NAIVE/DIRECT path
        # too. A real 200 body (>= _EXTRACT_NONEMPTY_RAW_FLOOR raw chars) whose
        # extractor chain (trafilatura → readability → regex) collapses below
        # _EXTRACT_EMPTY_FLOOR usable chars is the SAME distinct failure class
        # here as there — previously this naive path swallowed it silently as a
        # generic empty fetch. Surface it as its own auditable telemetry bucket.
        # Telemetry-only: the returned tuple is unchanged (control flow is byte-
        # identical). Reuses the existing floors — no new constants.
        if len(raw) >= _EXTRACT_NONEMPTY_RAW_FLOOR and len(content) < _EXTRACT_EMPTY_FLOOR:
            logger.info(
                "[live_retriever] fetched_200_but_empty_extract %s "
                "(method=httpx_naive raw_chars=%d extracted_chars=%d)",
                url[:80], len(raw), len(content),
            )
            # BB5-C05 iter-2 (#1177, Codex P2 reconcile): record ONLY the keyed
            # _m45 reason here — NOT a second _trace_tool. The production naive
            # path is reached via `_fallback_naive_fetch`, which already emits the
            # SINGLE per-fetch `_trace_tool` (ok/fail) for this call; adding an
            # `empty_extract` _trace_tool too would double-record one fetch into
            # two contradictory buckets (empty_extract AND fail), whereas the
            # parallel path emits exactly one. The _m45 reason is keyed by URL +
            # last-write-wins, so it carries the distinct empty-extract signal
            # without duplicating the trace. (Direct callers of this function —
            # e.g. the M-45 diagnostics refetch — still get the _m45 reason.)
            _m45_record_fetch_telemetry(
                url, "httpx_naive", "fetched_200_but_empty_extract",
            )
        return content, bool(content), extracted_title, body_type, jsonld
    except Exception as exc:
        logger.debug(
            "[live_retriever] naive-httpx fetch %r failed: %s", url, exc,
        )
        return "", False, "", "", ""


def _fallback_naive_fetch(
    url: str,
    max_chars: int,
    t0: float,
    primary_reason: str,
) -> tuple[str, bool, str, str, str]:
    """Run the naive-httpx fallback and record its FINAL outcome (I-meta-007b P2a).

    Every content-fetch fallback in :func:`_fetch_content` (AccessBypass
    disabled / unavailable / timed out / raised / produced no result) ends by
    delegating to :func:`_fetch_content_httpx_naive`. The pre-fix code traced
    ``fail``/``timeout`` BEFORE that delegation, so a SUCCESSFUL fallback was
    still recorded as a failure. This helper traces the ACTUAL result instead:

    * ``status="ok"`` + real ``bytes_received`` (length of fetched content) when
      the naive fetch returned content,
    * ``status="fail"`` otherwise — carrying ``primary_reason`` (the reason the
      primary path fell back, e.g. ``access_bypass_timeout_90s``) in ``error``
      for diagnostics.

    ``backend_used="httpx_naive"`` uniformly because the naive fetcher is what
    actually ran. ``t0`` is the single wall-clock start captured at the top of
    :func:`_fetch_content` so latency reflects total fetch time. Record-only +
    fail-safe (``_trace_tool`` swallows its own errors); returns the naive
    fetcher's tuple unchanged so retrieval behavior is identical to before.
    """
    result = _fetch_content_httpx_naive(url, max_chars)
    content, ok = result[0], result[1]
    _trace_tool(
        "fetch_content",
        target=url,
        status="ok" if ok else "fail",
        latency_ms=(time.time() - t0) * 1000.0,
        backend_used="httpx_naive",
        bytes_received=len(content) if ok else 0,
        error="" if ok else str(primary_reason),
        primary_reason=str(primary_reason),
    )
    return result


def refetch_for_extraction(url: str, max_chars: int = 2000) -> str:
    """M-42b (2026-04-22): re-fetch source content for deterministic
    trial-table / timeline extraction when the evidence row's
    existing `direct_quote` is thin (<100 chars) or the row was
    never successfully fetched.

    Returns a 2000-char extract (head + decimal-windows) via
    _fetch_content + _build_provenance_quote, or empty string when
    the URL cannot be fetched or returns thin content.

    Caller is expected to cache the result on the evidence row for
    the remainder of the run so repeat table generation within the
    same sweep does not re-hit the network.

    Generic wrapper — not trial/drug/domain-specific. Used by the
    M-42b trial-table builder and the Trial Program Timeline builder.

    M-45 (2026-04-22): see `refetch_for_extraction_with_diagnostics`
    for a variant that returns structured per-URL diagnostics
    (backend, char count, body type, eligibility, failure mode) for
    the V28 preflight and downstream audits. This function is a thin
    wrapper around that variant.
    """
    quote, _diag = refetch_for_extraction_with_diagnostics(url, max_chars)
    return quote


# M-45 pass-2 (Codex audit HIGH): per-URL method + failure-reason
# telemetry. Module-level dict populated by `_fetch_content` just
# before it returns, then read by `refetch_for_extraction_with_
# diagnostics`. Keyed by url; overwritten on each call so memory
# stays bounded. Not thread-safe for concurrent refetches of the
# same URL, but the current sweep path is sequential per URL.
_M45_LAST_FETCH_TELEMETRY: dict[str, dict[str, Any]] = {}


def _m45_record_fetch_telemetry(
    url: str, method: str, failure_reason: str = "",
) -> None:
    """M-45 pass-2: record the final AccessBypass method + failure
    reason for a fetch call. Overwrites any prior entry for the same
    URL so repeat refetches in one run show the latest attempt."""
    _M45_LAST_FETCH_TELEMETRY[url] = {
        "method": method or "unknown",
        "failure_reason": failure_reason,
    }


def _m45_pop_fetch_telemetry(url: str) -> dict[str, Any]:
    """M-45 pass-2: read + remove the telemetry for a URL so it's
    not reused by a later unrelated call. Returns empty dict if no
    entry was recorded."""
    return _M45_LAST_FETCH_TELEMETRY.pop(url, {})


def refetch_for_extraction_with_diagnostics(
    url: str, max_chars: int = 2000,
) -> tuple[str, dict[str, Any]]:
    """M-45 (2026-04-22): refetch with structured per-URL diagnostics.

    Codex V28 plan pass-2 APPROVED this diagnostic-first approach.
    V27 still produced thin quotes for paywalled PDFs despite the
    AccessBypass cascade existing. This variant records WHY each
    refetch landed or failed so audits can branch the fix
    (explicit-wire Jina/Firecrawl, better extraction window, or
    strict skip) based on real data instead of assumption.

    Returns (quote, diagnostics) where:
      - quote: same as `refetch_for_extraction` — non-empty iff the
        refetched content is ≥100 chars and the provenance quote
        was built; empty string otherwise. Strict ≥100 char contract
        preserved (no statement fallback, no prose fallback).
      - diagnostics: dict with these keys:
          url: the input URL (truncated to 200 chars for JSON safety)
          attempted: bool — did we try the fetch at all
          method: str — AccessBypass method that produced content
            ('crawl4ai', 'jina', 'firecrawl', 'httpx', 'archive_org',
            'scihub', or 'none')
          raw_char_count: int — bytes returned by _fetch_content
            before provenance-quote extraction
          body_type: str — 'abstract' / 'full_text' / 'paywall_shell'
            / 'html_meta' per `_detect_article_type_from_body`
          eligible: bool — True iff quote was emitted (≥100 chars)
          failure_mode: str — one of:
            '' (eligible), 'exception', 'fetch_failed',
            'thin_content', 'paywall_shell'
          exception_type: str — class name when failure_mode=exception
    """
    diagnostics: dict[str, Any] = {
        "url": (url or "")[:200],
        "attempted": False,
        "method": "none",
        "raw_char_count": 0,
        "body_type": "",
        "eligible": False,
        "failure_mode": "",
        "exception_type": "",
    }
    if not url:
        diagnostics["failure_mode"] = "empty_url"
        return "", diagnostics
    # F15 (GH #1245 / D11): per-URL refetch cap + negative cache. A dead URL was
    # refetched ~5.5x across expansion/deepener/agentic stages, re-paying the
    # full AccessBypass cascade each time. `_refetch_try_acquire` returns False
    # ONLY when the URL has SETTLED-FAILED the cap number of times (it is in the
    # negative cache) — it gates on settled failures, NOT in-flight reservations,
    # so a concurrent caller of a LIVE URL is never wrongly skipped (Codex diff-
    # gate iter-3 P1). False => short-circuit with NO network call (cap is the
    # reason). This is a PERFORMANCE de-dup; it never suppresses a fetch that
    # could succeed (only a URL that has already FAILED cap times is cached), so
    # no faithfulness gate is touched. `attempted` stays False so the caller sees
    # this was skipped. The reserved-slot settle below counts a FAILURE toward the
    # cap and leaves a SUCCESS uncapped.
    if not _refetch_try_acquire(url):
        logger.info(
            "[refetch_for_extraction] skipping refetch of %s — failed the "
            "per-URL cap=%d times (negative-cached, no further refetch)",
            url[:80], _refetch_cap(),
        )
        diagnostics["failure_mode"] = "refetch_capped"
        return "", diagnostics
    # A slot is reserved; it MUST be settled exactly once. `_settled` tracks the
    # success/failure outcome so the finally below settles correctly on EVERY
    # post-acquire return path (success counts a slot release; a failure converts
    # it into a recorded failure toward the cap).
    _fetch_succeeded = False
    try:
        diagnostics["attempted"] = True
        try:
            content, ok, _title, body_type, _jsonld = _fetch_content(url, max_chars)
        except Exception as exc:
            logger.warning(
                "[refetch_for_extraction] fetch failed for %s: %s", url, exc,
            )
            diagnostics["failure_mode"] = "exception"
            diagnostics["exception_type"] = type(exc).__name__
            # M-45 pass-2: read any telemetry recorded before the exception.
            te = _m45_pop_fetch_telemetry(url)
            diagnostics["method"] = te.get("method", "none")
            return "", diagnostics  # failure (settled in finally)

        diagnostics["raw_char_count"] = len(content) if content else 0
        diagnostics["body_type"] = body_type or ""
        # M-45 pass-2 (Codex audit HIGH): read the winning AccessBypass
        # method + failure reason that `_fetch_content` recorded. Pre-
        # pass-2 the method was always "none" because `_fetch_content`
        # discarded `result.access_method` before returning.
        tele = _m45_pop_fetch_telemetry(url)
        if tele:
            diagnostics["method"] = tele.get("method", "none")
            reason = tele.get("failure_reason", "")
            if reason and "timeout" in reason:
                diagnostics["failure_mode"] = "timeout"

        if not ok or not content:
            # M-45 pass-2: preserve timeout classification from telemetry
            # (set above) instead of overwriting with generic fetch_failed.
            if diagnostics["failure_mode"] != "timeout":
                diagnostics["failure_mode"] = "fetch_failed"
            return "", diagnostics  # failure (settled in finally)
        if len(content) < 100:
            if diagnostics["failure_mode"] != "timeout":
                diagnostics["failure_mode"] = "thin_content"
            return "", diagnostics  # failure (settled in finally)
        # Paywall-shell detection: body_type marker set by
        # _detect_article_type_from_body. We still build a provenance
        # quote from the content but tag the diagnostic so downstream
        # audits can filter these out if they want only full-text sources.
        if body_type == "paywall_shell":
            diagnostics["failure_mode"] = "paywall_shell"
            # Continue to build the quote — the shell may still contain
            # enough abstract text to hit ≥100 chars. Eligibility is
            # determined by the provenance-quote length check below.
        quote = _build_provenance_quote(
            content, head_chars=min(1500, max_chars), window_chars=500,
            max_total_chars=max_chars,
        )
        if not quote or len(quote) < 100:
            if not diagnostics["failure_mode"]:
                diagnostics["failure_mode"] = "thin_content"
            return "", diagnostics  # failure (settled in finally)
        diagnostics["eligible"] = True
        if diagnostics["failure_mode"] == "paywall_shell":
            # Eligible despite shell marker — abstract-only case.
            diagnostics["failure_mode"] = ""
        # A real fetch produced usable content — the URL is LIVE. This is NOT a
        # failure and must NOT count toward the cap (other sections may re-ground
        # on it). Mark success so the finally releases the reservation cleanly.
        _fetch_succeeded = True
        return quote, diagnostics
    finally:
        # Settle the reserved slot exactly once: success releases without counting
        # toward the cap; any failure converts the reservation into a recorded
        # failure and, at the cap, caches the URL.
        _refetch_settle(url, succeeded=_fetch_succeeded)


# ─────────────────────────────────────────────────────────────────────────────
# I-meta-007c: OPEN-ACCESS resolver for the LIVE retrieval loop.
#
# When AccessBypass returns a stub/empty/paywalled result for a candidate that
# carries a DOI (from S2 metadata or embedded in the URL), resolve the
# best open-access full text BEFORE giving up. Fail-OPEN: any resolver error
# returns "" and the caller falls through to its existing path — retrieval is
# NEVER broken by a resolver failure.
#
# Fallback order (exact, per `.codex/I-meta-007/_wiring_specs.txt`
# LANE wire:unpaywall-live-path):
#   1. Unpaywall v2 best-OA URL  -> fetch via AccessBypass
#   2. PubMed EFetch abstract (only when a PMID is available)
#   3. else "" (caller keeps its existing stub/fallback behaviour)
#
# The OA fetch REUSES the existing AccessBypass stack (already budgeted in the
# per-candidate fetch timeout) and the existing frame_fetcher parsers — no new
# network budget, no duplicated parsing. All helpers are module-level so tests
# can monkeypatch each seam independently (no real network, no spend).
#
# Env gates (LAW VI):
#   PG_ENABLE_LIVE_OA_RESOLVER  default "1"  — master on/off switch.
#   PG_UNPAYWALL_EMAIL          default placeholder — Unpaywall ToS email.
# ─────────────────────────────────────────────────────────────────────────────
# BB-007 (I-beatboth-fix-000 #1171): the placeholder Unpaywall email. The OA resolver treats this
# (or an empty value) as "resolver unavailable" and fails LOUD (traces a distinct signal) rather than
# issuing a doomed request that Unpaywall ToS rejects/throttles — a hidden cause of the fetch-fail rate.
_UNPAYWALL_PLACEHOLDER_EMAIL = "polaris@example.org"


def _oa_resolver_enabled() -> bool:
    """True iff the live OA resolver is enabled. Off iff the env var is set to
    a recognized falsey value ("0" / "false" / "no"); default ON."""
    raw = os.getenv("PG_ENABLE_LIVE_OA_RESOLVER", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _try_oa_resolution(
    url: str,
    extracted_doi: str = "",
    pmid: str = "",
    max_chars: int = DEFAULT_CONTENT_MAX_CHARS,
) -> str:
    """Resolve open-access full text for a paywalled/stub candidate.

    Public entry point called from :func:`_fetch_content` when AccessBypass
    returns stub/empty content AND a DOI is available. Returns upgraded content
    (str, capped at ``max_chars``) or "" on any failure / when disabled.

    Fail-OPEN by contract: every internal failure mode returns "" so the caller
    falls through to its existing behaviour. NEVER raises.

    Diff-gate P1: a DOI is REQUIRED to do anything. The PubMed EFetch abstract
    is only a SECONDARY fallback AFTER a DOI-keyed Unpaywall miss — a PMID-only,
    no-DOI candidate must NOT be upgraded (Europe-PMC can emit metadata with
    doi=None + pmid set; that record must stay a miss, not become PubMed text).

    Fallback order (DOI required throughout):
      1. Unpaywall v2 best-OA URL  -> AccessBypass fetch
      2. PubMed EFetch abstract    (only after a DOI-keyed Unpaywall miss AND
                                     when ``pmid`` is present)
      3. ""
    """
    if not _oa_resolver_enabled():
        return ""
    doi = (extracted_doi or "").strip()
    # Diff-gate P1: DOI-present gate. Without a DOI the resolver does nothing —
    # the PMID is only a secondary fallback after a DOI-keyed Unpaywall miss.
    if not doi:
        return ""
    try:
        # Step 1: Unpaywall best-OA URL(s), prioritized pdf > html.
        if doi:
            for oa_url in _unpaywall_get_oa_urls(doi):
                if not oa_url:
                    continue
                content = _fetch_oa_url_via_bypass(oa_url, max_chars)
                if content:
                    logger.info(
                        "[live_retriever] OA resolver: Unpaywall hit for "
                        "doi=%s url=%r (%d chars)",
                        doi, oa_url[:80], len(content),
                    )
                    return content[:max_chars]
        # Step 2: PubMed EFetch abstract when a PMID is available.
        if pmid:
            abstract = _pubmed_fetch_abstract(pmid)
            if abstract:
                logger.info(
                    "[live_retriever] OA resolver: PubMed EFetch fallback "
                    "for pmid=%s (%d chars)",
                    pmid, len(abstract),
                )
                return abstract[:max_chars]
    except Exception as exc:  # noqa: BLE001 — fail-OPEN, never break retrieval.
        logger.debug(
            "[live_retriever] OA resolver error for doi=%s url=%r: %s",
            doi, url[:80], exc,
        )
        return ""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# BUG-B02 / BUG-B04 (I-arch-011): degraded-row re-fetch via the FORCED Zyte path.
#
# THE BUG: on the live cert run 96/528 sources fetched as DEGRADED (content-less
# stub / landing-page shell) and were FLAGGED but NEVER re-fetched. The named B04
# anchors (NEJM 489 chars, FDA P960009 266 chars) are anti-bot/paywall shells: the
# free fetch cascade returns the shell with ``success=True``, so the in-cascade
# Zyte LAST-resort (access_bypass:1745, which only fires after the free chain
# FAILS) never gets a turn, and the no-DOI device PMA (FDA P960009) cannot be
# rescued by the DOI-gated OA resolver either. So the disease-staging slot was
# ungroundable — a real breadth loss, not a faithfulness call.
#
# THE FIX — ESCALATE, don't re-run the same path: for a row the fetch layer is
# about to mark degraded, call Zyte DIRECTLY on the original URL (force the paid
# browserHtml anti-bot solver — 2025 Proxyway benchmark: Zyte led all unblockers
# at 93.14% on heavily protected sites) instead of re-deriving the identical shell
# through the deterministic free cascade. On a usable, NON-content-starved result
# the row's grounding span is REPOPULATED and the degraded flags are cleared, so
# the row flows through the UNCHANGED strict_verify exactly like a full-text row.
#
# FAITHFULNESS-SAFE BY CONSTRUCTION: this touches the INPUT span only. It moves NO
# gate (strict_verify / NLI / 4-role D8 / span-grounding) and adds NO cap/floor/
# throttle — the re-fetched span is judged by the SAME pre-existing
# ``is_content_starved`` heuristic the legacy path already used, never a new
# threshold. A row that cannot be re-grounded STAYS LABELED degraded (it is never
# passed off as full text), and the run FAILS LOUD when ``ZYTE_API_KEY`` is unset
# (the Zyte fallback is otherwise a silent no-op without the key). Default-OFF
# master flag (LAW VI) => no re-fetch => byte-identical legacy behaviour; the
# later wiring pass owns turning it on for the cert slate.
# ─────────────────────────────────────────────────────────────────────────────
_ENV_REFETCH_DEGRADED = "PG_REFETCH_DEGRADED_VIA_ZYTE"


def _refetch_degraded_enabled() -> bool:
    """True iff the default-OFF degraded-row Zyte re-fetch is explicitly enabled.

    LAW VI: env-overridable, default OFF (unset => no re-fetch => byte-identical
    legacy behaviour). Recognized truthy values: 1/true/on/yes.
    """
    return os.environ.get(_ENV_REFETCH_DEGRADED, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _force_zyte_refetch(url: str, max_chars: int = DEFAULT_CONTENT_MAX_CHARS) -> str:
    """Force a Zyte browser re-fetch of a single degraded URL; return clean text.

    Calls ``AccessBypass._try_zyte`` DIRECTLY (bypassing the free-cascade-must-
    fail-first gate), because for an anti-bot/paywall SHELL the free cascade
    returns ``success=True`` with the shell and would re-derive the identical
    stub on any plain re-fetch. ``_try_zyte`` already tries the cheap
    httpResponseBody mode and ESCALATES to the paid JS-rendering browserHtml mode
    when the cheap result is a shell, runs the same ``safe_trafilatura_extract``
    every backend uses, and rejects paywall stubs internally — so a SUCCESS here
    is real extracted full text, never a shell laundered as content.

    STRICT NO-OP when ``ZYTE_API_KEY`` is absent (``_try_zyte`` itself returns a
    failure result spending nothing); a LOUD warning is emitted at the call site
    so a Zyte-blind run on the degraded rows is auditable instead of a silent
    no-op. Returns the extracted content string on a usable Zyte success, or ""
    on any failure / no key / timeout. NEVER raises (fail-OPEN per URL — one
    degraded row's re-fetch must never abort the retrieval loop).
    """
    if not url:
        return ""
    try:
        from src.tools.access_bypass import AccessBypass, polaris_asyncio_run
    except Exception as exc:  # noqa: BLE001 — AccessBypass unavailable => no re-fetch.
        logger.warning(
            "[live_retriever] B02/B04 degraded re-fetch: AccessBypass "
            "unavailable (%s) — cannot force Zyte for %s; row stays degraded.",
            exc, url[:80],
        )
        return ""

    result_holder: dict[str, Any] = {}

    def _zyte_worker() -> None:
        try:
            bypass = AccessBypass()

            async def _run() -> Any:
                # Force the Zyte browser path on the ORIGINAL url directly.
                return await bypass._try_zyte(url)

            result_holder["value"] = polaris_asyncio_run(_run())
        except Exception as exc:  # noqa: BLE001 — captured, surfaced as a miss.
            result_holder["error"] = exc

    worker = threading.Thread(target=_zyte_worker, daemon=True)
    worker.start()
    try:
        deadline = float(os.getenv("PG_FETCH_DEADLINE_SECONDS", "90"))
    except ValueError:
        deadline = 90.0
    worker.join(timeout=deadline if deadline > 0 else None)
    if worker.is_alive():
        logger.warning(
            "[live_retriever] B02/B04 degraded re-fetch: Zyte timed out after "
            "%.0fs for %s — row stays degraded (thread abandoned as daemon).",
            deadline, url[:80],
        )
        return ""
    if "error" in result_holder:
        logger.warning(
            "[live_retriever] B02/B04 degraded re-fetch: Zyte raised for %s: "
            "%s — row stays degraded.", url[:80], result_holder["error"],
        )
        return ""
    result = result_holder.get("value")
    content = getattr(result, "content", "") if result is not None else ""
    if result is not None and getattr(result, "success", False) and content:
        return str(content)[:max_chars]
    return ""


def _try_refetch_degraded_row(url: str, max_chars: int = DEFAULT_CONTENT_MAX_CHARS) -> str:
    """Re-fetch a fetch-degraded row through the strongest path; return clean text.

    Wraps :func:`_force_zyte_refetch`. FAILS LOUD when ``ZYTE_API_KEY`` is unset
    (the strongest path is a silent no-op without the key) so a Zyte-blind run is
    auditable; returns "" in that case (no recovery). On a usable Zyte success the
    extracted full text is returned for the caller to re-ground against. Returns
    "" on any failure — the caller then KEEPS the row labeled degraded (never a
    fabricated full-text span). Never raises.
    """
    if not url:
        return ""
    if not os.getenv("ZYTE_API_KEY"):
        logger.warning(
            "[live_retriever] B02/B04 DEGRADED_REFETCH_NO_ZYTE %s — a degraded "
            "stub cannot be re-fetched because ZYTE_API_KEY is UNSET (the Zyte "
            "paid fallback is a silent no-op without the key). Row stays LABELED "
            "fetch_degraded (NOT passed off as full text). Set ZYTE_API_KEY to "
            "recover full text.", url[:80],
        )
        return ""
    return _force_zyte_refetch(url, max_chars)


def _unpaywall_get_oa_urls(doi: str) -> list[str]:
    """Query the Unpaywall v2 API for OA location URLs.

    Returns an ordered list ``[pdf_url, html_url]`` (each may be absent; the
    list is empty when the work is not OA or the lookup fails). Fail-OPEN: any
    error returns ``[]`` so the caller falls back to PubMed / its existing path.

    Reuses ``frame_fetcher._parse_unpaywall_response`` for the OA-URL parse so
    the live path and the M-56 frame path share one parser.
    """
    if not doi:
        return []
    try:
        import httpx as _httpx
        from src.polaris_graph.retrieval.frame_fetcher import (
            _parse_unpaywall_response,
        )

        # BB-007 (I-beatboth-fix-000 #1171): Unpaywall ToS REQUIRES a real contact email; the
        # placeholder polaris@example.org is rejected/throttled, so the resolver silently no-ops
        # (a hidden cause of the 67-72% fetch-fail rate). FAIL LOUD instead of silent: if the email
        # is the placeholder (or empty), trace a DISTINCT resolver-unavailable signal and return []
        # without issuing the doomed request. The benchmark slate must supply a REAL PG_UNPAYWALL_EMAIL.
        email = os.getenv("PG_UNPAYWALL_EMAIL", _UNPAYWALL_PLACEHOLDER_EMAIL).strip()
        if not email or email.lower() == _UNPAYWALL_PLACEHOLDER_EMAIL:
            logger.warning(
                "[live_retriever] OA resolver UNAVAILABLE: PG_UNPAYWALL_EMAIL is the placeholder "
                "%r — Unpaywall ToS requires a real contact email. Set a real PG_UNPAYWALL_EMAIL "
                "to enable OA full-text resolution (doi=%s).",
                _UNPAYWALL_PLACEHOLDER_EMAIL, doi,
            )
            _trace_tool(
                "oa_resolver", target=doi, status="unavailable",
                backend_used="unpaywall_v2",
                error="placeholder_unpaywall_email",
                resolver_unavailable=True,
            )
            return []
        endpoint = "https://api.unpaywall.org/v2/" + doi.strip()
        with _httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, params={"email": email})
        if response.status_code != 200:
            return []
        try:
            data = response.json()
        except Exception:  # noqa: BLE001 — malformed JSON => no OA.
            return []
        parsed = _parse_unpaywall_response(data if isinstance(data, dict) else {})
        if not parsed.get("is_oa"):
            return []
        # Prioritize PDF over landing-page HTML (PDF is full text; HTML may be
        # an abstract-only shell).
        urls = [parsed.get("oa_pdf_url") or "", parsed.get("oa_html_url") or ""]
        return [u for u in urls if u]
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] Unpaywall OA query failed for doi=%s: %s",
            doi, exc,
        )
        return []


def _fetch_oa_url_via_bypass(oa_url: str, max_chars: int) -> str:
    """Fetch an OA URL via the existing AccessBypass stack.

    Reuses ``frame_fetcher._fetch_url_pattern`` — the proven sync/async-safe
    AccessBypass wrapper (also the documented monkeypatch seam) — so the live
    path does not re-implement the event-loop juggling. Returns content (str,
    capped at ``max_chars``) or "" on failure. Fail-OPEN.
    """
    if not oa_url:
        return ""
    try:
        from src.polaris_graph.retrieval.frame_fetcher import _fetch_url_pattern

        content, _final_url = _fetch_url_pattern(oa_url)
        if content:
            return content[:max_chars]
        return ""
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] OA bypass fetch failed for %r: %s",
            oa_url[:80], exc,
        )
        return ""


def _pubmed_fetch_abstract(pmid: str) -> str:
    """Fetch an abstract from PubMed EFetch for ``pmid``.

    Reuses ``frame_fetcher._parse_pubmed_xml`` for the XML -> abstract parse so
    the live path and the M-56 frame path share one parser. Returns the
    abstract text or "" on failure. Fail-OPEN.
    """
    if not pmid:
        return ""
    try:
        import httpx as _httpx
        from src.polaris_graph.retrieval.frame_fetcher import _parse_pubmed_xml

        endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": str(pmid).strip(),
            "rettype": "abstract",
            "retmode": "xml",
        }
        with _httpx.Client(timeout=15.0) as client:
            response = client.get(endpoint, params=params)
        if response.status_code != 200 or not (response.text or "").strip():
            return ""
        parsed = _parse_pubmed_xml(response.text)
        return parsed.get("abstract") or ""
    except Exception as exc:  # noqa: BLE001 — fail-OPEN.
        logger.debug(
            "[live_retriever] PubMed abstract fetch failed for pmid=%s: %s",
            pmid, exc,
        )
        return ""


def _fetch_content(
    url: str,
    max_chars: int,
    doi_hint: str = "",
    pmid_hint: str = "",
) -> tuple[str, bool, str, str, str]:
    """Fetch URL content using the AccessBypass cascade (Crawl4AI +
    Jina Reader + Firecrawl concurrent, fallback to direct HTTP +
    Archive.org + institutional proxy + Sci-Hub).

    Returns (content, ok, title, body_type, jsonld). Diff-gate P1-C: `jsonld`
    is the raw ld+json <script> block contents extracted from the RAW fetched
    HTML BEFORE _strip_html removes <script> blocks, so the structural junk
    classifier (Signal C: NewsArticle / press-release / login-wall) can fire on
    the live ON path. Empty when the winning backend already returned cleaned
    text (Jina markdown / Crawl4AI) with no <script> blocks — honestly empty,
    never fabricated.

    BUG-FETCH-R8d (2026-04-18): the live smoke test of
    clinical_tirzepatide_t2dm showed 19/20 candidates failed via the
    previous naive httpx.Client. `src/tools/access_bypass.py` already
    had the full cascade (including BUG-BROTLI fix, concurrent Crawl4AI
    /Jina/Firecrawl, paywall detection) but pipeline A wasn't wired
    to it. This is the wiring.

    The AccessBypass call is async; live_retriever's fetch loop is
    sync by historical choice. We run the async call in a fresh event
    loop per URL. Full async refactor of run_live_retrieval (with
    asyncio.gather for concurrency) is tracked as R-RETRIEVE-ASYNC in
    docs/todo_list.md.

    Env opt-out: set PG_DISABLE_ACCESS_BYPASS=1 to fall back to the
    naive httpx path (useful when Playwright/Crawl4AI is unavailable).

    I-meta-007c: ``doi_hint`` / ``pmid_hint`` are optional identifiers carried
    from the candidate's S2 metadata. When AccessBypass returns stub/empty/
    paywalled content AND a DOI is resolvable (hint or extracted from the URL),
    the OPEN-ACCESS resolver (Unpaywall v2 -> AccessBypass; else PubMed EFetch
    abstract) is tried BEFORE giving up. Gated by PG_ENABLE_LIVE_OA_RESOLVER
    (default "1"); fail-OPEN (resolver errors never break retrieval).
    """
    # I-meta-007b: single wall-clock for the tool tracer (record-only). The
    # naive-httpx fallbacks below are recorded as the content-fetch outcome so
    # the per-run summary reflects every fetch attempt's path + latency.
    _t0 = time.time()
    if os.getenv("PG_DISABLE_ACCESS_BYPASS", "0") == "1":
        # M-45 pass-2: record env-opt-out so diagnostics can see it.
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "pg_disable_access_bypass=1"
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail), not the
        # pre-fallback "fail" — a successful naive fetch must be recorded ok.
        return _fallback_naive_fetch(
            url, max_chars, _t0, "pg_disable_access_bypass=1"
        )
    try:
        from src.tools.access_bypass import AccessBypass
    except Exception as exc:
        logger.warning(
            "[live_retriever] AccessBypass unavailable (%s); "
            "falling back to naive httpx", exc,
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive", f"access_bypass_import_failed: {exc}"
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_import_failed: {exc}"
        )

    # Run AccessBypass in a dedicated thread so each call gets its own
    # fresh event loop. This works whether we're called from sync or
    # async context (expansion path runs inside a live loop). Crawl4AI
    # leaves background tasks that make subsequent asyncio.run() in the
    # same thread fail with "cannot be called from a running event loop".
    #
    # BB5-S02 (#1177): import the cross-thread in-flight bound + leak gauge +
    # the wedged-task-draining runner. The bound is acquired INSIDE the worker
    # (so an abandoned worker holds its slot until it truly terminates) and
    # released in the worker's OWN finally — never in the outer join path
    # (releasing on abandonment over-releases; not releasing leaks the slot).
    from src.tools.access_bypass import (
        _get_bypass_inflight_semaphore,
        polaris_asyncio_run,
        record_bypass_leaked_worker,
    )
    result_holder: dict[str, Any] = {}
    _inflight_sem = _get_bypass_inflight_semaphore()
    # BB5-S02 iter-3 (#1177, Codex P1 continuing): a per-worker ABANDONED flag.
    # The outer join-timeout path SETS it; the worker CHECKS it twice — (a)
    # immediately after acquiring the in-flight slot (closes the
    # blocked-on-semaphore window: a worker that timed out while STILL queued on
    # `_inflight_sem.acquire()` must NOT proceed to run AccessBypass / spawn a
    # browser once the slot finally frees) and (b) right after publishing its
    # loop (closes the narrow TOCTOU between passing check (a) and the outer path
    # reading a not-yet-published loop). Under the GIL the handshake is closed:
    # worker = publish-loop-then-check-flag; outer = set-flag-then-read-loop.
    _abandoned = threading.Event()

    def _bypass_worker() -> None:
        # BB5-S02: acquire a cross-thread in-flight slot. Bounds the number of
        # concurrently-LIVE bypass workers (each may hold a browser subprocess)
        # across all per-thread event loops — `_get_crawl4ai_semaphore` cannot,
        # being lazy-bound to THIS thread's fresh loop only.
        _inflight_sem.acquire()
        try:
            # BB5-S02 iter-3 (#1177, Codex P1 continuing): if this worker was
            # abandoned (outer join timed out) WHILE it was blocked here on
            # `acquire()`, bail BEFORE constructing AccessBypass / publishing a
            # loop / spawning a browser. The outer path could not cancel us (no
            # loop was ever published), so the worker itself must self-abort —
            # otherwise a stale fetch starts AFTER its caller already fell back,
            # consuming a slot + browser resources. `return` here lets the
            # existing `finally` perform the single in-flight-slot release (do
            # NOT release explicitly — a BoundedSemaphore double-release raises).
            if _abandoned.is_set():
                return
            bypass = AccessBypass()

            async def _capture_loop_and_fetch() -> Any:
                # BB5-S02 iter-2 (#1177, Codex P1-S02): publish THIS worker's
                # running loop into the shared holder as the FIRST awaited step,
                # BEFORE the (potentially wedging) fetch. The outer join path
                # reads this loop to actively signal teardown on abandonment.
                # Capturing here — inside the coro rather than by changing
                # polaris_asyncio_run — keeps the drain-runner's signature (and
                # its spy test) untouched.
                result_holder["loop"] = asyncio.get_running_loop()
                # BB5-S02 iter-3 (#1177): second abandonment check, AFTER the
                # loop is published. Closes the TOCTOU where the worker passed
                # the post-acquire check, then the outer path timed out and read
                # `loop` as None (not yet published) → no teardown was sent.
                # Raising CancelledError (vs returning) matches the worker's
                # existing `except asyncio.CancelledError` handler and skips the
                # fetch entirely, so no stale browser op starts.
                if _abandoned.is_set():
                    raise asyncio.CancelledError(
                        "bypass worker abandoned before fetch start"
                    )
                return await bypass.fetch_with_bypass(url, prefer_legal=True)

            # BB5-S02: polaris_asyncio_run (vs bare asyncio.run) force-drains
            # wedged detached Playwright fetch tasks BEFORE the loop's
            # cancel-all phase, so the loop teardown cannot hang on an
            # un-cancellable browser op — closing the orphan-subprocess window
            # for a worker that DOES eventually return.
            result_holder["value"] = polaris_asyncio_run(_capture_loop_and_fetch())
        except asyncio.CancelledError:
            # BB5-S02 iter-2: the outer join path actively cancelled this loop's
            # tasks on abandonment (active teardown). CancelledError is a
            # BaseException — NOT caught by `except Exception` — so catch it
            # explicitly here, or it escapes the daemon thread as a noisy
            # traceback. The slot still releases in the finally below.
            result_holder["error"] = result_holder.get("error") or RuntimeError(
                "bypass worker cancelled on abandonment teardown"
            )
        except Exception as exc:  # noqa: BLE001
            result_holder["error"] = exc
        finally:
            _inflight_sem.release()

    worker = threading.Thread(target=_bypass_worker, daemon=True)
    worker.start()
    # BUG-FETCH-R8d medium-1 (Codex pass 4): bound the join so a wedged
    # Crawl4AI/Playwright browser startup/cleanup can't hang the sweep
    # indefinitely. AccessBypass has internal timeouts but they don't
    # cover every subprocess/import/browser-cleanup failure mode.
    # Default 90s = Crawl4AI worst-case (~70s) + margin. Override via
    # PG_FETCH_DEADLINE_SECONDS. Set to 0 to disable (not recommended).
    try:
        deadline = float(os.getenv("PG_FETCH_DEADLINE_SECONDS", "90"))
    except ValueError:
        deadline = 90.0
    worker.join(timeout=deadline if deadline > 0 else None)
    if worker.is_alive():
        # BB5-S02 iter-3 (#1177, Codex P1 continuing): SET the abandoned flag
        # FIRST — before the gauge/log/loop-read — so a worker about to wake
        # from a blocked `_inflight_sem.acquire()` (or about to publish its
        # loop) observes the abandonment ASAP and self-aborts WITHOUT starting
        # AccessBypass. This closes the pre-loop window the active loop-cancel
        # teardown below cannot reach (that teardown needs a published loop;
        # a still-queued worker has none). The two mechanisms compose: this
        # flag covers the never-started (pre-loop) case; the loop cancel below
        # covers the in-flight (post-loop) case.
        _abandoned.set()
        # BB5-S02 (#1177): the worker is ABANDONED (still alive past the join
        # deadline) — it holds its in-flight slot + possibly a live browser
        # subprocess until it finally terminates. Record the leak gauge so the
        # accumulated-orphan-subprocess signal is auditable (was silent before).
        _leaked = record_bypass_leaked_worker()
        logger.warning(
            "[live_retriever] AccessBypass timed out after %.0fs for %s "
            "— falling back to naive httpx (thread abandoned as daemon; "
            "leaked_bypass_workers=%d)",
            deadline, url[:80], _leaked,
        )
        # BB5-S02 iter-2 (#1177, Codex P1-S02): the previous code only RECORDED
        # the abandonment (gauge) — it never FORCED the wedged worker to release
        # its browser. Here we ACTIVELY signal teardown: cancel every task on the
        # abandoned worker's event loop. The fetch coro was created via
        # `loop.create_task` inside polaris_asyncio_run, so cancelling it injects
        # CancelledError at the wedged `await`, which runs _try_crawl4ai's
        # `finally: await _safe_close_crawler(...)` — closing the Crawl4AI/
        # Playwright browser context instead of orphaning it. `call_soon_thread-
        # safe` is the ONLY thread-safe way to touch another loop; `all_tasks`
        # then runs IN that loop thread where it is safe. Fire-and-forget — we do
        # NOT join the worker, preserving the non-hang property of this fallback.
        #
        # Honest limitation (mirrors the trafilatura SIGSEGV mitigation note): a
        # worker wedged in a synchronous C-level Playwright call observes the
        # cancellation only when it next yields to its loop. This is inherent to
        # cooperative cancellation and cannot be engineered past in-process; the
        # signal is still sent so a cancellable wait tears down promptly.
        _abandoned_loop = result_holder.get("loop")
        if _abandoned_loop is not None:
            try:
                if not _abandoned_loop.is_closed():
                    def _cancel_all_on_abandoned_loop(
                        _loop: Any = _abandoned_loop,
                    ) -> None:
                        try:
                            for _task in asyncio.all_tasks(_loop):
                                _task.cancel()
                        except Exception:  # noqa: BLE001 — best-effort teardown
                            pass

                    _abandoned_loop.call_soon_threadsafe(
                        _cancel_all_on_abandoned_loop
                    )
            except RuntimeError:
                # Loop closed/finished racing with the cancel request — the
                # worker already returned on its own; nothing to tear down.
                pass
        # M-45 pass-2: record AccessBypass timeout so diagnostics can
        # distinguish timeout from backend refusal.
        _m45_record_fetch_telemetry(
            url, "httpx_naive", f"access_bypass_timeout_{int(deadline)}s",
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail). The
        # backend that actually ran is httpx_naive, not access_bypass.
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_timeout_{int(deadline)}s"
        )

    if "error" in result_holder:
        exc = result_holder["error"]
        logger.warning(
            "[live_retriever] AccessBypass raised for %s: %s: %s",
            url[:80], type(exc).__name__, exc,
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive",
            f"access_bypass_raised_{type(exc).__name__}",
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, f"access_bypass_raised_{type(exc).__name__}"
        )
    if "value" not in result_holder:
        logger.warning(
            "[live_retriever] AccessBypass produced no result for %s",
            url[:80],
        )
        _m45_record_fetch_telemetry(
            url, "httpx_naive", "access_bypass_no_result"
        )
        # I-meta-007b P2a: record the FINAL fallback outcome (ok/fail).
        return _fallback_naive_fetch(
            url, max_chars, _t0, "access_bypass_no_result"
        )
    result = result_holder["value"]

    method = getattr(result, "access_method", "unknown") or "unknown"
    if not result.success or not result.content:
        reason = (result.metadata or {}).get("reason") if hasattr(result, "metadata") else None
        logger.info(
            "[live_retriever] fetch_miss %s (method=%s reason=%s)",
            url[:80], method, reason or "no_content",
        )
        # M-45 pass-2: record the winning backend + reason even on miss
        # so downstream audits can see which backend was last invoked.
        _m45_record_fetch_telemetry(url, method, reason or "no_content")
        # I-meta-007c: AccessBypass returned a stub/empty/paywalled result.
        # Before giving up, try the OPEN-ACCESS resolver when a DOI is
        # available (from S2 metadata hint or embedded in the URL). On a hit
        # we return the upgraded content with ok=True so the longer body
        # re-tiers above T7 downstream. Fail-OPEN: an empty resolver result
        # leaves the existing stub return path untouched.
        #
        # Diff-gate P2b: when the resolver is gated OFF, do NOT compute the DOI
        # and do NOT call _try_oa_resolution — the OFF path is byte-identical to
        # the pre-existing stub control flow (resolver never invoked).
        # Diff-gate P1: enforce the DOI-present gate at the CALL SITE. Only enter
        # the OA-resolver branch when a non-empty DOI is resolvable (hint or
        # embedded in the URL). An empty-DOI candidate (e.g. an Europe-PMC record
        # with doi=None + pmid set) must NOT be upgraded via a PMID-only PubMed
        # fetch — it falls straight through to the pre-existing miss tuple.
        if _oa_resolver_enabled():
            oa_doi = (doi_hint or "").strip() or _extract_doi_from_url(url)
            if oa_doi:
                oa_content = _try_oa_resolution(
                    url=url,
                    extracted_doi=oa_doi,
                    pmid=(pmid_hint or "").strip(),
                    max_chars=max_chars,
                )
                if oa_content:
                    logger.info(
                        "[live_retriever] fetch_oa %s (doi=%s chars=%d) — "
                        "upgraded from stub via OA resolver",
                        url[:80], oa_doi, len(oa_content),
                    )
                    _m45_record_fetch_telemetry(url, "oa_resolver", "")
                    _trace_tool(
                        "fetch_content", target=url, status="ok",
                        latency_ms=(time.time() - _t0) * 1000.0,
                        backend_used="oa_resolver",
                        bytes_received=len(oa_content),
                        content_length=len(oa_content),
                    )
                    return oa_content, True, "", "", ""
        _trace_tool(
            "fetch_content", target=url, status="stub",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used=method, error=str(reason or "no_content"),
        )
        return "", False, "", "", ""
    # BUG-M-14 (Codex pass 14): extract the full page title from the
    # raw result.content BEFORE _strip_html removes <title> tags. Jina
    # markdown has "Title: X" on first line; Crawl4AI cleaned text has
    # the same. HTML fetches have <title>.
    extracted_title = _extract_title_from_content(result.content)
    # BUG-M-17 (Codex pass 2): detect article-type from body.
    body_type = _detect_article_type_from_body(result.content)
    # Diff-gate P1-C: capture raw ld+json from result.content BEFORE _strip_html
    # removes <script> blocks. Direct-HTTP path returns raw HTML (JSON-LD present);
    # Jina/Crawl4AI return cleaned text with <script> already gone (honestly empty).
    jsonld = _extract_jsonld_blocks(result.content)
    # result.content is already extracted (Jina = markdown, Crawl4AI =
    # cleaned text). _strip_html is a safety net for direct-HTTP path
    # which returns raw HTML.
    content = _strip_html(result.content)[:max_chars]
    # BB5-C05 (#1177): "fetched-200-but-empty-extract" — the backend fetched
    # real content (success + non-empty result.content) yet the extractor chain
    # (trafilatura → readability → regex) collapsed it below the usable floor.
    # This is a DISTINCT failure class from a network miss / paywall stub, and
    # was previously swallowed silently (counted as a generic miss). Surface it
    # as its own telemetry bucket so it is auditable, not silent.
    _raw_len = len(result.content or "")
    if _raw_len >= _EXTRACT_NONEMPTY_RAW_FLOOR and len(content) < _EXTRACT_EMPTY_FLOOR:
        logger.info(
            "[live_retriever] fetched_200_but_empty_extract %s "
            "(method=%s raw_chars=%d extracted_chars=%d)",
            url[:80], method, _raw_len, len(content),
        )
        _m45_record_fetch_telemetry(
            url, method, "fetched_200_but_empty_extract",
        )
        _trace_tool(
            "fetch_content", target=url, status="empty_extract",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used=method, bytes_received=len(content),
            content_length=len(content),
            error="fetched_200_but_empty_extract",
        )
        return content, bool(content), extracted_title, body_type, jsonld
    # ──────────────────────────────────────────────────────────────────────
    # F14 (GH #1245 / D9, D10): paywall-stub min-body gate. A backend that
    # returns success=True with a SHORT body (a paywall/abstract shell) was
    # previously logged status="ok" — a dead fetch masquerading as a good
    # source, and the OA resolver (which only fires on a hard miss above) never
    # got a chance. Here, when the extracted body is below the configured floor
    # AND a DOI is resolvable, give the OA resolver (Unpaywall / PMC-BioC / Zyte)
    # a chance to UPGRADE the body above the floor; if it cannot, render a LOUD
    # `stub` verdict (ok=False) instead of a silent ok. DEFAULT floor 0 = OFF =
    # byte-identical (the gate never fires); the cert sweep sets 1000.
    _min_body = _fetch_min_body_chars()
    if _min_body > 0 and len(content) < _min_body:
        # Give the OA resolver a chance to upgrade a short shell to full text.
        if _oa_resolver_enabled():
            _oa_doi = (doi_hint or "").strip() or _extract_doi_from_url(url)
            if _oa_doi:
                _oa_content = _try_oa_resolution(
                    url=url,
                    extracted_doi=_oa_doi,
                    pmid=(pmid_hint or "").strip(),
                    max_chars=max_chars,
                )
                if _oa_content and len(_oa_content) >= _min_body:
                    logger.info(
                        "[live_retriever] fetch_oa_upgrade %s (doi=%s "
                        "short_body=%d -> oa_body=%d) — short shell upgraded "
                        "to full text via OA resolver",
                        url[:80], _oa_doi, len(content), len(_oa_content),
                    )
                    _m45_record_fetch_telemetry(url, "oa_resolver", "")
                    _trace_tool(
                        "fetch_content", target=url, status="ok",
                        latency_ms=(time.time() - _t0) * 1000.0,
                        backend_used="oa_resolver",
                        bytes_received=len(_oa_content),
                        content_length=len(_oa_content),
                    )
                    return _oa_content, True, extracted_title, body_type, jsonld
        # Still short after the OA attempt — this is a STUB, not an ok source.
        # Fail LOUD: a paywalled-publisher short body with no key is logged so a
        # Zyte-blind run is auditable (the Zyte fallback is a silent no-op
        # without ZYTE_API_KEY). We KEEP returning the content (so a down-weight
        # consumer can still inspect it) but with ok=False + status="stub" so it
        # never enters the pool as a verified full-text source.
        _is_paywall_pub = _is_paywall_publisher_url(url)
        if _is_paywall_pub and not os.getenv("ZYTE_API_KEY"):
            logger.warning(
                "[live_retriever] PAYWALL_STUB_NO_ZYTE %s (method=%s chars=%d "
                "< floor=%d) — paywalled publisher returned a short shell and "
                "ZYTE_API_KEY is UNSET; the Zyte paid fallback was a silent "
                "no-op. Set ZYTE_API_KEY to recover full text.",
                url[:80], method, len(content), _min_body,
            )
        else:
            logger.warning(
                "[live_retriever] PAYWALL_STUB %s (method=%s chars=%d < "
                "floor=%d, paywall_publisher=%s) — short body treated as a "
                "stub, NOT ok (fail-loud).",
                url[:80], method, len(content), _min_body,
                _is_paywall_pub,
            )
        _m45_record_fetch_telemetry(url, method, "paywall_stub_short_body")
        _trace_tool(
            "fetch_content", target=url, status="stub",
            latency_ms=(time.time() - _t0) * 1000.0,
            backend_used=method, bytes_received=len(content),
            content_length=len(content),
            error="paywall_stub_short_body",
        )
        return content, False, extracted_title, body_type, jsonld
    logger.info(
        "[live_retriever] fetch_ok %s (method=%s chars=%d)",
        url[:80], method, len(content),
    )
    # M-45 pass-2: record winning backend for diagnostics.
    _m45_record_fetch_telemetry(url, method, "")
    _trace_tool(
        "fetch_content", target=url, status="ok",
        latency_ms=(time.time() - _t0) * 1000.0,
        backend_used=method, bytes_received=len(content),
        content_length=len(content),
    )
    return content, bool(content), extracted_title, body_type, jsonld


def _domain_of(url: str) -> str:
    try:
        # FX-13 (#1125): removeprefix, NOT lstrip — `lstrip("www.")` strips any leading char in the
        # SET {w, .}, corrupting domains like www.who.int -> "ho.int" / www.washington.edu ->
        # "ashington.edu". removeprefix removes only the literal "www." prefix.
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


_DECIMAL_PATTERN = re.compile(r"-?\d+\.\d+")


_PDF_METADATA_PATTERNS = (
    re.compile(r"^\s*%PDF", re.MULTILINE),
    re.compile(r"endobj|xref|startxref|trailer", re.IGNORECASE),
    re.compile(r"\.(pdf|obj|endstream)\s+\d+", re.IGNORECASE),
)
_FORMATTING_NOISE_MARKERS = (
    "/Contents", "/MediaBox", "/Font", "/FontName",
    "<<", ">>", "stream\n",
)


# I-run11-010 (#1056, S1) / RC-C (TI-05/06): bot-challenge / access-denial stub markers + the
# unambiguous Cloudflare challenge-page co-occurrence signatures. SINGLE-SOURCED in the leaf module
# ``shell_detector`` (I-beatboth-001 #1276, LAW V: one list so the retrieval-time stub gate and the
# cited-span faithfulness gate can NEVER drift — the markers were historically bolted on in waves,
# which is exactly the divergence this consolidation prevents). Re-pointed here as module-level
# aliases so every existing reference is byte-identical.
_ACCESS_DENIAL_MARKERS = shell_detector.ACCESS_DENIAL_MARKERS
_ACCESS_DENIAL_MAX_CHARS = int(os.getenv("PG_ACCESS_DENIAL_MAX_CHARS", "3000"))
_CHALLENGE_PAGE_COOCCURRENCE = shell_detector.CHALLENGE_PAGE_COOCCURRENCE


def _is_access_denial_stub(content: str) -> bool:
    """True if a fetched body looks like a bot-challenge / access-denial page rather than article
    content (I-run11-010 #1056 S1; RC-C TI-05/06 extends it). Keys on SPECIFIC access-denial phrases:
    short-body markers fire only on a short body (so a full article that merely quotes one is not
    false-dropped), while the UNAMBIGUOUS Cloudflare co-occurrence signatures fire at ANY length
    (they never appear in real article prose, so a long challenge/enrichment-shell page is caught).

    I-beatboth-001 (#1276): delegates to ``shell_detector.is_access_denial_stub`` (the SINGLE
    source of the vocabulary), passing THIS module's own ``_ACCESS_DENIAL_MAX_CHARS`` so the
    short-body ceiling stays governed by ``PG_ACCESS_DENIAL_MAX_CHARS`` — byte-identical to the
    prior inline implementation."""
    return shell_detector.is_access_denial_stub(content, max_chars=_ACCESS_DENIAL_MAX_CHARS)


def is_content_starved(content: str, min_useful_chars: int = 200) -> bool:
    """R-5 Fix D: detect evidence rows whose fetched content is PDF
    metadata / formatting fragments / empty text — not useful prose.

    Returns True if the content should NOT be passed to the generator
    (because the LLM would admit it has no answer, wasting tokens).

    Heuristics:
      - Length of visible text < min_useful_chars
      - Bot-challenge / access-denial stub (I-run11-010 #1056 S1)
      - PDF metadata markers dominate
      - Ratio of alphabetic chars to total chars is low
    """
    if not content or len(content.strip()) < min_useful_chars:
        return True

    # I-run11-010 (#1056, S1): a captcha / robot-challenge stub is starved even when it clears the
    # length + alpha-ratio bars — it carries no article content to ground a claim against.
    if _is_access_denial_stub(content):
        return True

    # PDF-metadata dominance check
    pdf_hits = 0
    for pat in _PDF_METADATA_PATTERNS:
        if pat.search(content):
            pdf_hits += 1
    if pdf_hits >= 2:
        return True

    # Formatting-marker dominance check
    marker_count = sum(content.count(m) for m in _FORMATTING_NOISE_MARKERS)
    if marker_count > 20 and marker_count / max(1, len(content) / 100) > 0.5:
        return True

    # Alphabetic ratio: if less than 40% of chars are letters, probably
    # not readable prose (e.g., binary-looking PDF remnants).
    alpha = sum(1 for ch in content if ch.isalpha())
    total = len(content)
    if total > 0 and alpha / total < 0.4:
        return True

    return False


def _build_provenance_quote(
    content: str,
    head_chars: int = 1500,
    window_chars: int = 500,
    max_total_chars: int = 12000,
    max_windows: int = 20,
) -> str:
    """Build a direct_quote that contains the head of the document AND
    500-char windows around every decimal found in the full content.

    Fixes Fix-3: strict_verify was dropping sentences that cited real
    numbers living outside the first 1500 chars (e.g., STEP 5 -15.2%
    in the results section of a Nature paper). Caller stores the result
    as evidence.direct_quote; Phase 4 _find_span_for_decimal will now
    find the decimal because a window containing it is in the quote.

    Returns a concatenation: head || "\\n\\n[...]\\n\\n" || window_1 || ...
    Deduplicates overlapping windows. Caps total length at max_total_chars
    to keep prompt budget under control.
    """
    if not content:
        return ""
    head = content[:head_chars]
    if len(content) <= head_chars:
        return head

    # Find all decimal positions in the full content
    positions: list[tuple[int, int]] = []
    for m in _DECIMAL_PATTERN.finditer(content):
        start = max(0, m.start() - window_chars // 2)
        end = min(len(content), m.end() + window_chars // 2)
        positions.append((start, end))

    # De-overlap: merge adjacent windows that touch each other
    positions.sort()
    merged: list[tuple[int, int]] = []
    for s, e in positions:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Drop windows already fully inside the head
    merged = [(s, e) for s, e in merged if e > head_chars]

    # Cap count
    merged = merged[:max_windows]

    chunks = [head]
    total = len(head)
    for s, e in merged:
        chunk = content[s:e]
        # Stop if we'd exceed the total cap
        if total + len(chunk) + 6 > max_total_chars:
            break
        chunks.append(chunk)
        total += len(chunk) + 6  # rough separator overhead

    return "\n\n[...]\n\n".join(chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Fetch-time relevance rerank + per-sub-query reservation (I-meta-002-q1d #951/#943)
# ─────────────────────────────────────────────────────────────────────────────

# Pure-lexical, no-model relevance: stopword-filtered content-word overlap of a
# candidate's (title+snippet) against the research question. NO embedder / no model
# load (§8.4) — sentence-transformers/CUDA are never touched on the ranking path.
_RERANK_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of", "in",
    "on", "at", "to", "for", "with", "by", "from", "as", "that", "this", "these",
    "those", "it", "its", "be", "been", "what", "which", "who", "how", "why",
    "when", "where", "we", "our", "their", "between", "into", "about", "than",
})


def _rerank_content_tokens(text: str) -> set[str]:
    """Lowercase content-word tokens (3+ chars, stopword-filtered). Pure lexical."""
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", (text or "").lower())
    return {t for t in toks if t not in _RERANK_STOPWORDS}


def _lexical_relevance_score(candidate: "SearchCandidate", question_tokens: set[str]) -> float:
    """Overlap fraction of the candidate's (title+snippet) content tokens with the
    question tokens. 0.0 when either side is empty. Deterministic, no network/model."""
    if not question_tokens:
        return 0.0
    cand_tokens = _rerank_content_tokens(getattr(candidate, "snippet_text", "") or "")
    if not cand_tokens:
        return 0.0
    return len(cand_tokens & question_tokens) / float(len(question_tokens))


# FX-15a (#1118): the injected-seed source classes that share the reserved/undroppable/unranked
# lane. `primary_trial_doi` = #817 layer-4 direct primary-trial DOI seeds; `agentic_seed` =
# agentic-discovered URLs; `deepener_seed` = citation-snowball deepener URLs (Codex iter-1 P1:
# these are primary-trial-DERIVED but NOT direct DOI seeds, so they must not pollute
# `primary_trial_doi` telemetry either). BB-006 (#1171): `storm_seed` = STORM interview-search-result
# URLs harvested URL-ONLY (the synthesized STORM text is NEVER ingested). ALL are split out and
# prepended unranked; FX-15b later makes the web-discovered classes droppable via the host-class
# filter (telemetry-correctness here is the prerequisite).
_SEED_SOURCE_LABELS: frozenset[str] = frozenset(
    {"primary_trial_doi", "agentic_seed", "deepener_seed", "storm_seed"}
)


# FX-15b (#1119): path/route markers for pages that CANNOT carry a single paper's content — pure
# navigation / search-result / table-of-contents / discussion listings. Matched as lowercase
# substrings of the URL. Chosen PRECISION-FIRST and EMPIRICALLY (Codex iter-1 P1 + evidence_pool.json
# cross-reference on the held drb_72 trace): every one appears ONLY on listing/nav pages, never on a
# page that fetched real evidence.
#
# DELIBERATELY EXCLUDED (Codex iter-1 P1 — these CAN bear evidence, so pre-fetch dropping is a
# precision failure; the POST-fetch tier classifier + content-starvation check handle the empty ones):
#   - `/conference/.../program/paper/<id>` — held S7SHZQ4n (50k chars) + S25ktKkD (30k chars) fetched
#     as REAL papers; the junk 8A8RRTQY has the IDENTICAL shape, so URL cannot distinguish them.
#   - `/annual-meeting/.../paper/...` — same ambiguity as conference papers.
#   - conference SUPPLEMENT abstracts (`/Supplement_`) — bear abstract-level evidence; let the tier
#     classifier DOWN-TIER them (it already does) rather than pre-fetch DROP them.
# `/issue/` (singular) is NOT a marker (it prefixes real article paths); `/issues/` (plural TOC
# listing) IS.
_LOW_CONTENT_PATH_MARKERS: tuple[str, ...] = (
    "/search", "/browse", "/issues/", "/forum/",
    "/toc/",  # journal table-of-contents listing (e.g. /toc/jpe/current) — never a real article
)


def _is_low_content_host_or_page(url: str, title: str = "") -> bool:
    """FX-15b (#1119): structural reject of pure NAV / SERP / table-of-contents / discussion URLs,
    applied to agentic-discovered seed URLs BEFORE fetch (a cheap deterministic floor that skips a
    wasted fetch on pages that cannot contain a paper). PRECISION-FIRST — must NEVER reject a page
    that could fetch real evidence (conference papers, supplement abstracts, working-paper PDFs are
    all KEPT and decided by the post-fetch tier classifier + content-starvation check). Pure + no
    network. Returns True iff the URL is a pure listing/nav page that should be dropped.
    """
    if not url:
        return False
    u = url.lower()
    if any(marker in u for marker in _LOW_CONTENT_PATH_MARKERS):
        return True
    # Paginated SERP / search-result listing pages (not an article).
    if "search-results" in u or "per-page=" in u:
        return True
    return False


def _rerank_and_reserve(
    candidates: list["SearchCandidate"],
    *,
    research_question: str,
    fetch_cap: int,
    n_seed_injected: int,
) -> list["SearchCandidate"]:
    """Replace arrival-order truncation with a no-spend, no-model-load relevance rerank
    that reserves at least one slot per sub-query (I-meta-002-q1d #951, Codex brief-gate
    iter-1 required-changes).

    Seed lane (I-bug-776 #817): primary-trial DOI seeds carry empty title/snippet, so
    relevance scoring would drop them. They are SPLIT OUT by `source in _SEED_SOURCE_LABELS`
    (FX-15a #1118: the set `{primary_trial_doi, agentic_seed}` — both injected seed classes keep
    the additive/reserved lane) and prepended AFTER ranking — never ranked, never dropped, exactly
    additive as before.

    Reservation: group non-seeds by `query_origin`; sort each group by (-score, index);
    take at most ONE reserved item per origin while capacity remains (origins with the best
    candidate score reserved first when origins exceed cap); then fill the remaining slots
    by global (-score, index). The long full-paragraph/anchor query is not starved.

    Fail-open (never raise): on any error fall back to the previous arrival-order behavior
    `candidates[:fetch_cap + n_seed_injected]`.
    """
    try:
        seeds = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
        non_seeds = [c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS]
        if fetch_cap <= 0 or not non_seeds:
            return seeds + non_seeds[:max(fetch_cap, 0)]

        question_tokens = _rerank_content_tokens(research_question)
        # (score, original_index, candidate) so ties + zero-overlap fall back to arrival order.
        scored = [
            (_lexical_relevance_score(c, question_tokens), i, c)
            for i, c in enumerate(non_seeds)
        ]
        # Group by origin, each group sorted by (-score, index).
        groups: dict[str, list[tuple[float, int, "SearchCandidate"]]] = {}
        for entry in scored:
            origin = getattr(entry[2], "query_origin", "") or "_unlabeled"
            groups.setdefault(origin, []).append(entry)
        for entries in groups.values():
            entries.sort(key=lambda e: (-e[0], e[1]))

        selected_idx: set[int] = set()
        chosen: list[tuple[float, int, "SearchCandidate"]] = []
        # Phase 1 — reserve >=1 slot per origin (origins ranked by their best candidate score),
        # bounded by capacity.
        origins_by_best = sorted(
            groups.items(), key=lambda kv: (-kv[1][0][0], kv[1][0][1])
        )
        for _origin, entries in origins_by_best:
            if len(chosen) >= fetch_cap:
                break
            top = entries[0]
            chosen.append(top)
            selected_idx.add(top[1])
        # Phase 2 — fill remaining slots by global (-score, index).
        if len(chosen) < fetch_cap:
            remainder = sorted(
                (e for e in scored if e[1] not in selected_idx),
                key=lambda e: (-e[0], e[1]),
            )
            for entry in remainder:
                if len(chosen) >= fetch_cap:
                    break
                chosen.append(entry)
                selected_idx.add(entry[1])
        # Emit non-seeds in original arrival order among the selected set (stable corpus).
        selected_non_seeds = [c for i, c in enumerate(non_seeds) if i in selected_idx]
        return seeds + selected_non_seeds
    except Exception as exc:  # fail-open: never break retrieval on a ranking error
        logger.warning("[live_retriever] rerank failed (%s) — arrival-order fallback", exc)
        return candidates[:fetch_cap + n_seed_injected]


# ─────────────────────────────────────────────────────────────────────────────
# B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-THRESHOLD + fetch-BUDGET
# ─────────────────────────────────────────────────────────────────────────────
# THE BUG (PHASE2_3_LANE_SPECS.md LANE-RETRIEVAL): the fetch-time cut above is a
# fixed top-N COUNT cut keyed on a PURE-LEXICAL relevance score
# (`_lexical_relevance_score` = content-word overlap / len(question_tokens)). The
# denominator scales with QUESTION LENGTH, so a long multi-part research question
# (the drb_76 shape) makes an on-topic paper whose domain vocabulary does not
# lexically match the question's exact words score near-zero and get cut purely
# because the cap could not afford it — and the cut count was lumped into the
# generic `rerank_not_selected` reason, dropped-and-forgotten.
#
# THE FIX (surgical, §-1.3 weight-not-filter for credibility; topical relevance
# MAY gate): replace the COUNT cut with a relevance THRESHOLD by REUSING B1's
# semantic relevance scorer WHOLESALE —
# `evidence_selector._semantic_relevance_scores(research_question, sub_queries,
# evidence_rows)`. B4 does NOT re-implement the scoring loop: it shapes its
# pre-fetch candidates into the row-dicts B1's `_row_embed_text` reads, calls B1's
# scorer ONCE, and applies B1's IDENTICAL keep predicate (`score >= floor`). One
# scorer, one relevance story across B1+B4 — the scorer contract CANNOT drift
# because there is only one implementation (Codex B4 iter-2 P1). Then the
# `fetch_cap` stays purely a COST budget on how many of the on-topic survivors we
# actually fetch — but the above-threshold-but-beyond-budget tail is RECORDED
# (count + reason + scores) instead of silently discarded. Each kept candidate's
# relevance score is carried FORWARD as a weight onto its evidence row.
#
# B1's scorer returns ``None`` when the embedder is unavailable / scoring fails /
# there is no usable anchor — and B4 falls back LOUDLY to the legacy lexical
# `_rerank_and_reserve` on that ``None`` (LAW II: no silent degrade, never a silent
# keep-all). That ``None`` IS the shared infra-failure signal: B4 no longer
# hand-rolls a self-similarity canary (deleted in iter-3) — the canary would have
# been a B4-private divergence from B1's contract, the exact drift Codex flagged.
# RECONCILIATION NOTE (conscious, iter-3): `prefetch_offtopic_filter._similarity_scores`
# SWALLOWS its three internal infra failures (no embedder interface / zero-norm
# query / encode exception) and returns all-zeros WITHOUT raising, so neither B1 NOR
# B4 returns ``None`` on that rare loaded-embedder-but-zeroed case — both return an
# all-0.0 score set and drop every non-seed. That degrades LOUDLY to a downstream
# corpus-adequacy abort (a visible empty-corpus failure, never a confidently-wrong
# report), and it matches B1's own behavior exactly. A canary belongs in B1's SHARED
# scorer (one place, one story) if it is wanted at all — it is NOT re-added here.
#
# CREDIBILITY/TIER IS NEVER A DROP HERE — only TOPICAL relevance gates (off-topic
# is useless at any weight). The faithfulness engine (strict_verify / 4-role D8 /
# provenance) lives in the generator/evaluator and is UNTOUCHED: this lane only
# changes the pre-fetch candidate menu + adds an additive weight + telemetry.
#
# GATING: `PG_RETRIEVAL_RELEVANCE_GATE` (default OFF). OFF => the legacy
# `_rerank_and_reserve` count-cut runs byte-identically (the embedder is never
# even imported — preserving `test_no_embedder_model_loaded`). ON + embedder
# unavailable => LOUD fallback to the legacy lexical path (LAW II: no silent
# degrade, never a silent keep-all).

# B4 relevance floor — ONE relevance story across B1+B4 (Codex iter-1 P1.1).
# The threshold is NOT a B4-private constant; it is B1's `PG_RELEVANCE_FLOOR`
# (default 0.30, `evidence_selector._DEFAULT_RELEVANCE_FLOOR`), parsed by B1's
# `evidence_selector.parse_relevance_floor`. B4 and B1 therefore gate on the
# IDENTICAL floor against the IDENTICAL [0,1]-clamped semantic cosine — a candidate
# B1's selector would keep (`item[1] >= relevance_floor` at evidence_selector.py
# _relevance_floor_selection) is never pre-fetch-dropped here by a tighter B4-only
# number. A cosine below this floor against EVERY anchor (question + each sub-query)
# = off-topic. The floor is consumed only on the B4 ON path
# (PG_RETRIEVAL_RELEVANCE_GATE=1); OFF => the legacy count-cut runs byte-identically
# and the floor is never even read. `parse_relevance_floor` is imported lazily
# inside `_relevance_gate_threshold` so the OFF path never imports evidence_selector.

def _relevance_gate_enabled() -> bool:
    """Kill-switch `PG_RETRIEVAL_RELEVANCE_GATE` (default OFF). ON only on an
    explicit truthy ('1'/'true'/'yes'/'on'). OFF (incl. unset / any other value)
    => the legacy `_rerank_and_reserve` count-cut runs byte-identically AND the
    semantic embedder is never imported."""
    raw = os.environ.get("PG_RETRIEVAL_RELEVANCE_GATE", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _relevance_gate_threshold() -> float:
    """Topical-relevance floor — B1's `PG_RELEVANCE_FLOOR` (default 0.30), parsed by
    B1's `evidence_selector.parse_relevance_floor` so B1 and B4 share ONE floor and
    ONE relevance story (Codex iter-1 P1.1). A candidate whose MAX cosine over
    {research_question} ∪ {sub-queries} is below this floor is OFF-TOPIC and gated
    out (topical filter, the one axis §-1.3 permits to filter). The comparison is
    the IDENTICAL `score >= floor` on the IDENTICAL [0,1]-clamped cosine that B1
    applies at `_relevance_floor_selection` (`item[1] >= relevance_floor`).

    FAIL LOUD on a garbage / out-of-range `PG_RELEVANCE_FLOOR`: `parse_relevance_floor`
    raises `ValueError` (range (0.0, 1.0]) — identical to B1's behaviour — so a
    misconfigured floor can never silently pass an unbounded, off-topic pool. The
    import is lazy so the OFF path never imports evidence_selector."""
    from src.polaris_graph.retrieval.evidence_selector import parse_relevance_floor

    return parse_relevance_floor(os.environ.get("PG_RELEVANCE_FLOOR"))


@dataclass
class RelevanceGateResult:
    """B4 telemetry for the relevance-threshold + fetch-budget selection.

    Emitted on `LiveRetrievalResult.relevance_gate` ONLY on the B4 ON path (None
    when OFF => byte-identical). Records the unfetched-but-relevant tail (the
    above-threshold candidates the fetch BUDGET could not afford) so the recall
    cost is MEASURABLE + auditable, never dropped-and-forgotten.

    Fields:
      - threshold: the topical-relevance floor used.
      - total_scored: non-seed candidates scored (seeds bypass scoring).
      - kept_on_topic: above-threshold candidates (the on-topic survivors).
      - dropped_off_topic: below-threshold candidates (true off-topic, gated out).
      - fetched_budget: on-topic candidates the fetch BUDGET could afford to keep.
      - unfetched_relevant_tail: on-topic candidates BEYOND the budget — RELEVANT
        but unfetched for COST reasons (a real resource bound, not a relevance/
        credibility drop). This is the recall cost the operator must see.
      - tail_score_min / tail_score_max: the relevance-score band of that tail.
      - scorer: 'semantic_v2' (B1 embedder) or 'lexical_fallback' (embedder
        unavailable — LOUD degrade per LAW II).
    """

    threshold: float
    total_scored: int = 0
    kept_on_topic: int = 0
    dropped_off_topic: int = 0
    fetched_budget: int = 0
    unfetched_relevant_tail: int = 0
    tail_score_min: float | None = None
    tail_score_max: float | None = None
    scorer: str = "semantic_v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "total_scored": self.total_scored,
            "kept_on_topic": self.kept_on_topic,
            "dropped_off_topic": self.dropped_off_topic,
            "fetched_budget": self.fetched_budget,
            "unfetched_relevant_tail": self.unfetched_relevant_tail,
            "tail_score_min": self.tail_score_min,
            "tail_score_max": self.tail_score_max,
            "scorer": self.scorer,
        }


def _candidate_relevance_scores(
    research_question: str,
    sub_queries: list[str],
    candidates: list["SearchCandidate"],
) -> Optional[list[float]]:
    """Per-candidate topical relevance, computed by REUSING B1's scorer wholesale
    (`evidence_selector._semantic_relevance_scores`) — NO B4-private scoring loop,
    NO B4-private canary, so the scorer contract cannot drift (Codex B4 iter-2 P1).

    Each candidate is shaped into the row-dict B1's `_row_embed_text` reads. That
    helper embeds the row's ``statement`` + ``direct_quote`` fields, so a
    candidate's text surface (`snippet_text` = title + snippet — the SAME surface
    the lexical scorer reads) is mapped onto ``statement``. B1 then returns
    ``{row_index -> max cosine over {research_question} ∪ {sub_queries}}`` clamped
    to [0, 1], or ``None`` (embedder unavailable / scoring failed / no anchor).

    Returns a per-candidate score list aligned to ``candidates`` (in [0, 1]), or
    ``None`` — the caller falls back LOUDLY to the legacy lexical cut on ``None``
    (LAW II: no silent keep-all). The import is INSIDE this function so the OFF path
    (which never calls it) never imports the embedder / evidence_selector."""
    try:
        from src.polaris_graph.retrieval.evidence_selector import (
            _semantic_relevance_scores,
        )
    except Exception as exc:  # import-path failure
        logger.warning(
            "[live_retriever] B4 relevance scorer import failed (%s) — falling "
            "back LOUDLY to the lexical count-cut.",
            str(exc)[:200],
        )
        return None
    # Shape each candidate as the row-dict B1's `_row_embed_text` reads: it embeds
    # `statement` + `direct_quote`, so the candidate's title+snippet surface goes
    # onto `statement` (an empty-snippet candidate therefore embeds to ~0.0, exactly
    # as B1 scores a row with no text — no B4-private bypass).
    rows = [
        {"statement": (getattr(c, "snippet_text", "") or "")}
        for c in candidates
    ]
    score_map = _semantic_relevance_scores(research_question, sub_queries, rows)
    if score_map is None:
        # B1's None = embedder unavailable / scoring failed / no usable anchor.
        return None
    # `_semantic_relevance_scores` keys by row index; project back to list order.
    return [float(score_map.get(i, 0.0)) for i in range(len(candidates))]


def _relevance_threshold_select(
    candidates: list["SearchCandidate"],
    *,
    research_question: str,
    sub_queries: list[str],
    fetch_cap: int,
    n_seed_injected: int,
) -> tuple[list["SearchCandidate"], dict[str, float], Optional[RelevanceGateResult]]:
    """B4 ON-path selection: relevance THRESHOLD (topical gate) + fetch BUDGET
    (cost cap), using B1's semantic embedding-cosine scorer.

    Pipeline:
      1. Split seeds (`source in _SEED_SOURCE_LABELS`) — NEVER scored, NEVER
         dropped, prepended exactly as `_rerank_and_reserve` does (seed lane
         preserved: primary-trial DOI seeds carry empty title/snippet).
      2. Score every non-seed by REUSING B1's `_semantic_relevance_scores` (max
         cosine over {question} ∪ {sub-queries}) — no B4-private scoring loop.
      3. THRESHOLD: drop BELOW-threshold (off-topic) candidates with B1's IDENTICAL
         `score >= floor` predicate (no empty-snippet bypass) — topical relevance is
         the only axis allowed to gate (§-1.3). Credibility/tier is NEVER consulted.
      4. BUDGET: keep the on-topic survivors in DESCENDING relevance up to
         `fetch_cap` (a pure COST budget). The above-threshold-but-beyond-budget
         tail is RECORDED in `RelevanceGateResult.unfetched_relevant_tail` (count
         + score band), not silently discarded.
      5. Carry each kept candidate's relevance score forward as a WEIGHT
         (`relevance_weight` on the returned score map, keyed by url).

    Returns `(selected_candidates, url_to_relevance_weight, gate_telemetry)`.
    Selected order: seeds first (arrival order), then on-topic survivors in
    ARRIVAL order among the budget-selected set (a stable corpus, mirroring
    `_rerank_and_reserve`'s stable-order emit). On any scorer failure returns
    `(None, {}, None)` so the caller falls back LOUDLY to the legacy lexical cut.

    `n_seed_injected` is accepted for SIGNATURE PARITY with `_rerank_and_reserve`
    (the caller passes the same args to either path); seeds are handled here by the
    `source in _SEED_SOURCE_LABELS` split, so the count itself is not read.
    """
    seeds = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
    non_seeds = [c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS]
    threshold = _relevance_gate_threshold()

    if not non_seeds:
        # Only seeds present — nothing to score; budget bounds the (empty) non-seeds.
        gate = RelevanceGateResult(threshold=threshold, scorer="semantic_v2")
        return seeds + non_seeds[:max(fetch_cap, 0)], {}, gate

    scores = _candidate_relevance_scores(research_question, sub_queries, non_seeds)
    if scores is None:
        # LOUD fallback: signal the caller to run the legacy lexical count-cut.
        return None, {}, None  # type: ignore[return-value]

    budget = max(0, int(fetch_cap))
    # (score, arrival_index, candidate) for stable, deterministic ordering.
    scored = list(zip(scores, range(len(non_seeds)), non_seeds))
    # IDENTICAL B1 keep predicate (Codex B4 iter-2 P1): `score >= floor`, exactly the
    # `item[1] >= relevance_floor` B1 applies at `_relevance_floor_selection`. NO
    # B4-private empty-snippet bypass: a candidate with no embeddable text scores 0.0
    # under B1's scorer and therefore drops below the floor — the SAME way B1 treats a
    # row with no text. Seeds (the floor-EXEMPT lane, B1's primary-trial-anchor
    # analogue) are already split out above and never scored, so they are never
    # dropped here; the only thing this floor drops is a genuinely text-less non-seed,
    # which is the documented reconciliation (do not diverge from B1's predicate).
    on_topic = [t for t in scored if t[0] >= threshold]
    off_topic = [t for t in scored if t[0] < threshold]

    # BUDGET: rank on-topic survivors by (-score, arrival_index); the top `budget`
    # are fetched, the rest are the unfetched-but-relevant tail (a COST drop).
    on_topic_ranked = sorted(on_topic, key=lambda t: (-t[0], t[1]))
    fetched = on_topic_ranked[:budget]
    tail = on_topic_ranked[budget:]

    selected_idx = {t[1] for t in fetched}
    # Stable corpus: emit fetched non-seeds in ARRIVAL order among the selected set.
    selected_non_seeds = [c for i, c in enumerate(non_seeds) if i in selected_idx]

    # Carry the relevance score forward as a weight, keyed by url (kept set only).
    url_weight: dict[str, float] = {}
    for score, idx, cand in fetched:
        url_weight[cand.url] = float(score)

    tail_scores = [t[0] for t in tail]
    gate = RelevanceGateResult(
        threshold=threshold,
        total_scored=len(non_seeds),
        kept_on_topic=len(on_topic),
        dropped_off_topic=len(off_topic),
        fetched_budget=len(fetched),
        unfetched_relevant_tail=len(tail),
        tail_score_min=(min(tail_scores) if tail_scores else None),
        tail_score_max=(max(tail_scores) if tail_scores else None),
        scorer="semantic_v2",
    )
    return seeds + selected_non_seeds, url_weight, gate


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────


def run_live_retrieval(
    *,
    research_question: str,
    amplified_queries: Optional[list[str]] = None,
    protocol: Optional[dict[str, Any]] = None,
    max_serper: int = DEFAULT_MAX_SERPER,
    max_s2: int = DEFAULT_MAX_S2,
    fetch_cap: int = DEFAULT_FETCH_CAP,
    enable_openalex_enrich: bool = True,
    enable_prefetch_filter: bool = False,
    domain: Optional[str] = None,
    seed_urls: Optional[list[str]] = None,
    seed_only: bool = False,
    seed_source: str = "primary_trial_doi",
    seed_query_origin: str = "primary_trial_doi_seed",
    research_frame: Any = None,
    anchor_seed: bool = True,
    progress_cb: Any = None,
) -> LiveRetrievalResult:
    """Execute live retrieval and classify the corpus.

    Args:
        research_question: Raw user query (anchor for scope validator).
        amplified_queries: Optional extra queries (scope-validated).
        protocol: Protocol dict; used for scope validation.
        max_serper: Max Serper results per query.
        max_s2: Max S2 results per query.
        fetch_cap: Hard cap on total URLs to fetch (cost control).
        enable_openalex_enrich: Toggle OpenAlex lookup per URL.
        enable_prefetch_filter: Toggle embedding-based off-topic filter
            (slow; off by default for the first live run).
        domain: Optional scope-template domain name (clinical / policy /
            tech / due_diligence). When set, R-6 Gap-2 domain backends
            augment the generic Serper+S2 retrieval with arxiv (tech),
            SEC EDGAR (DD), or policy-site targeted Serper queries.
        research_frame: Optional planner `ResearchFrame` (I-meta-005 Phase 2
            #986). When set (ON-mode), the field-agnostic need-type registry
            REPLACES the domain backends at the Step-2a seam — discovery is
            keyed on the frame's declared `evidence_needs` + extracted
            `jurisdictions`, NOT a domain. Mutually exclusive with `domain` on
            the on-path (the sweep passes `domain=None` on-mode).
        anchor_seed: When True (default — OFF-mode byte-identical), the verbatim
            `research_question` is PREPENDED to the effective query list and the
            scope validator keeps it (`always_keep_anchor=True`). I-meta-005
            Phase 4 (#988) GAP rounds pass `anchor_seed=False` so the broad anchor
            is NOT re-fired: `all_queries = amplified_queries` ONLY, the scope
            validator does NOT re-add the anchor (`always_keep_anchor=False`), and
            the need-type backend is invoked with `anchor_seed=False` (no
            `research_question` prepend there either). A gap round therefore fires
            EXACTLY the gap sub-queries on BOTH the core Serper/S2 seam AND the
            need-type adapters.
        progress_cb: Optional liveness callback ``cb(stage: str, **kw) -> None``
            (GH #1258 PART 2). Called on the caller's thread at the boundaries of
            the two long synchronous phases — after ``parallel_fetch`` returns and
            periodically inside the per-URL classification loop — so the run-status
            heartbeat keeps ticking (stage / elapsed / cost) instead of freezing at
            ``scope_gate_passed``. Default ``None`` => byte-identical (no calls). A
            raising callback is swallowed; it can never perturb retrieval.

    Returns LiveRetrievalResult.

    Raises:
        MalformedPlanError: when `research_frame` carries a malformed
            `evidence_needs` value OR a malformed jurisdiction SHAPE. This is
            validated UP-FRONT (before ANY live discovery, incl. core
            Serper/S2) and FAILS LOUD — it NEVER silently degrades to core
            Serper/S2 (brief §2.4 P2-note-1). Distinct from the fail-OPEN
            adapter/network handling at the Step-2a seam.
    """
    api_calls: dict[str, int] = {"serper": 0, "s2": 0, "openalex": 0, "fetch": 0}
    notes: list[str] = []
    # GH #1258 PART 2: optional liveness callback so the run-status heartbeat ticks DURING the two
    # long phases of this synchronous function — the network-bound parallel_fetch and the per-URL
    # OpenAlex-enrich + tier-classify loop — instead of going dark until retrieval_done. The callback
    # runs ON THE CALLER'S THREAD (this function is synchronous), so it inherits the run's cost
    # ContextVar with no race and is unaffected by faithfulness/gating logic. It is purely additive:
    # `progress_cb is None` (the default) keeps every behavior byte-identical, and a callback that
    # raises is swallowed so observability can never perturb retrieval.
    def _emit_progress(stage: str, **kw: Any) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(stage, **kw)
        except Exception:  # noqa: BLE001 — observability must never perturb retrieval
            pass
    # F15 (GH #1245 / D11): clear the per-URL refetch counters + negative cache at
    # the START of each run so a dead URL from a prior run/vector does not stay
    # poisoned, and so the per-URL cap is per-run (not per-process). Cheap, no
    # network.
    reset_refetch_cache()
    # I-ready-017 Task 2a (#1204): ADDITIVE source-funnel telemetry. Local
    # aggregate of every _trace_drop call by reason, mirrored onto the result so
    # the per-stage source loss is persisted (not just the pathB trace, which is
    # empty on a normal sweep). Pre-seed the four statically-known reasons to 0
    # so the manifest schema is stable; incrementing beside each _trace_drop
    # leaves _trace_drop itself byte-identical (no behavior change).
    #
    # F15/F30 (GH #1245 / D11): two ADDITIVE WEIGHT-not-FILTER counters. Under the
    # PG_SWEEP_CREDIBILITY_REDESIGN master flag, a content-starved / landing-page
    # source is DOWN-WEIGHTED (kept in the pool at low weight) instead of hard-
    # dropped (§-1.3). `down_weighted` counts those kept-at-low-weight rows so the
    # operator sees the REAL disposition; the legacy hard-drop reasons still carry
    # the honest count. Pre-seeded to 0 so the schema is stable on the OFF path.
    drop_reasons: dict[str, int] = {
        "offtopic": 0,
        "rerank_not_selected": 0,
        "fetch_failed": 0,
        "content_starved": 0,
        "landing_page": 0,
        "down_weighted": 0,
    }
    # Populated inside the Step-3 off-topic block; stays None when the filter is
    # disabled or only seeds are present (honest absence, never a faked count).
    prefetch_offtopic: dict[str, Any] | None = None

    # ── Step 0: UP-FRONT plan validation (I-meta-005 Phase 2, P2-note-1) ──
    # A malformed frame (bad evidence_need / bad jurisdiction SHAPE) must FAIL
    # LOUD here — BEFORE the core Serper/S2 baseline spends or populates any
    # candidate. The router's validation raises MalformedPlanError; we let it
    # propagate (it is a VALIDATION error, distinct from the fail-OPEN
    # adapter/network handling at Step 2a). Only fires on-mode (frame present).
    if research_frame is not None and not seed_only:
        from src.polaris_graph.discovery.need_type_router import (
            validate_frame_needs,
        )
        # Raises MalformedPlanError on a malformed value/SHAPE; a valid-shape
        # unknown jurisdiction + an empty evidence_needs both pass (non-fatal).
        validate_frame_needs(research_frame)

    # ── Step 1: compile the effective query list ──────────────────────
    # I-meta-005 Phase 4 (#988): `anchor_seed=False` (gap rounds) suppresses the
    # broad `research_question` anchor on BOTH the prepend AND the scope-validator
    # reinsertion, so a gap round fires ONLY the gap sub-queries (no wasted
    # anchor re-run). Default True = OFF-mode byte-identical.
    all_queries: list[str] = [research_question] if anchor_seed else []
    if amplified_queries:
        all_queries.extend(amplified_queries)
    # Scope validation (de-drift)
    if protocol:
        valid = validate_amplified_queries(
            all_queries, protocol, always_keep_anchor=anchor_seed,
        )
        effective_queries = valid.kept
        notes.append(
            f"scope_query_validator: {len(valid.kept)} kept / "
            f"{len(valid.dropped)} dropped"
        )
    else:
        effective_queries = list(all_queries)

    # ── Step 2: run Serper + S2 across queries ──────────────────────
    seen_urls: set[str] = set()
    candidates: list[SearchCandidate] = []

    # I-bug-776 (#817) layer-4 (Codex decision b): direct primary-trial DOI seed
    # candidates. Injected at the FRONT so the fetch_cap slice always includes
    # them (a reserved anchored-primary lane), and fetch_cap is bumped by the
    # seed count below so they are ADDITIVE — they do not evict search/guideline
    # candidates. They pass the SAME fetch / Unpaywall-OA / extraction / tier /
    # adequacy gates as every other source: a seed counts as T1 ONLY if the tier
    # classifier identifies the fetched content as a primary trial (no laundering).
    _n_seed_injected = 0
    for _surl in seed_urls or []:
        if _surl and _surl not in seen_urls:
            seen_urls.add(_surl)
            # FX-15a (#1118): the seed SOURCE/ORIGIN labels are now caller-supplied so the agentic
            # lane (seed_source='agentic_seed') is no longer mislabeled as a primary-trial DOI seed.
            # Defaults preserve the #817 layer-4 DOI-lane labels for every existing caller.
            candidates.append(SearchCandidate(
                url=_surl, title="", snippet="", source=seed_source,
                query_origin=seed_query_origin,
            ))
            _n_seed_injected += 1
    if _n_seed_injected:
        logger.info(
            "[live_retriever] injected %d direct seed candidates (source=%s, query_origin=%s)",
            _n_seed_injected, seed_source, seed_query_origin,
        )

    # I-meta-002-q1d (#942-deepener, Codex diff-gate iter-2 P1): seed_only processes ONLY the injected
    # seed_urls — no Serper/S2 fan-out and no domain backends. Used by the deepener pass so it fetches
    # exactly the citation-snowball-discovered URLs (and nothing else) through the same chokepoint.
    for q in ([] if seed_only else effective_queries):
        logger.info("[live_retriever] SERPER q=%r", q[:80])
        # FX-17 (#1126) iter-2: pass api_calls so each HTTP page (not each query) is counted inside
        # _serper_search. The old `+= 1` here undercounted paginated breadth.
        serper_hits = _serper_search(q, num=max_serper, api_calls=api_calls)
        for hit in serper_hits:
            url = hit.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(SearchCandidate(
                url=url,
                title=hit.get("title", ""),
                snippet=hit.get("snippet", ""),
                source="serper",
                query_origin=q,
            ))

        # FX-18 (#1122): S2 bulk is a KEYWORD index — feeding it the 40-70-word NL query returned ~0
        # for 4/5 golden questions. Send a SHORT content-keyword distillation of `q` instead (pure,
        # stopword-filtered, capped). Flag-gated PG_S2_KEYWORD_DISTILL (default on); an empty
        # distillation falls back to the NL `q` (never an empty search). The candidate's `query_origin`
        # stays the NL `q` so the per-sub-query rerank reservation + plan-sufficiency are unchanged.
        _s2_query = q
        if os.getenv("PG_S2_KEYWORD_DISTILL", "1") != "0":
            _kw = distill_keywords(q, max_terms=int(os.getenv("PG_S2_KEYWORD_MAX_TERMS", "8")))
            if _kw:
                _s2_query = _kw
        logger.info("[live_retriever] S2 q=%r", _s2_query[:80])
        s2_hits = _s2_bulk_search(_s2_query, limit=max_s2)
        api_calls["s2"] += 1
        for hit in s2_hits:
            url = hit.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(SearchCandidate(
                url=url,
                title=hit.get("title", ""),
                snippet=hit.get("snippet", ""),
                source="s2",
                metadata={"doi": hit.get("doi"), "year": hit.get("year")},
                query_origin=q,
            ))

        # FX-18 (#1122): OpenAlex /works?search handles NL queries that the S2 keyword index does not,
        # and is already built (domain_backends.openalex_search, fail-open). Wire it as a PARALLEL
        # academic backend — ADD (union), not replace S2 (Codex Q8) — sending the NL `q`; union+dedup
        # via the shared `seen_urls`. Candidates carry source="openalex_search"; default query_origin
        # to `q`. Flag-gated PG_OPENALEX_SEARCH (default on). Fail-open: a backend fault adds 0 hits.
        if os.getenv("PG_OPENALEX_SEARCH", "1") != "0":
            _oa_t0 = time.time()
            try:
                from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                    openalex_search,
                )
                _oa_hits = openalex_search(q, limit=max_s2)
                api_calls["openalex_search"] = api_calls.get("openalex_search", 0) + 1
                # FX-20 (#1128): trace openalex as a first-class backend so the discovery_funnel reads
                # its requested-vs-returned from the SAME tool_trace rows as serper/s2 (FX-18 wired the
                # call but never traced it — a tracer-only funnel would silently OMIT openalex).
                _trace_tool(
                    "openalex_search", target=q, status="ok",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    result_count=len(_oa_hits), num_requested=max_s2,
                )
                # FX-18b (#1123): mirror serper/s2 -> emit an openalex retrieval_trace row so RERUN §-1.1 can verify it fired.
                _trace_query("openalex_search", q, [getattr(c, "url", "") for c in _oa_hits])
                for cand in _oa_hits:
                    url = getattr(cand, "url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if not getattr(cand, "query_origin", ""):
                        cand.query_origin = q
                    candidates.append(cand)
            except Exception as exc:
                _trace_tool(
                    "openalex_search", target=q, status="fail",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    error=str(exc), result_count=0, num_requested=max_s2,
                )
                logger.warning(
                    "[live_retriever] openalex_search failed for %r (fail-open): %s",
                    q[:60], exc,
                )

    # ── Step 2a: specialized issuer-class backends ──────────────────
    # I-meta-005 Phase 2 (#986) DUAL PATH:
    #   ON-mode (research_frame present): the field-agnostic NEED-TYPE registry
    #     REPLACES the domain backends — discovery is routed off the frame's
    #     declared evidence_needs + jurisdictions (NO `if domain ==` branch
    #     reached). The malformed-frame case already FAILED LOUD at Step 0.
    #   OFF-mode (domain set, no frame): the legacy R-6 Gap-2 domain switch runs
    #     byte-identically (arXiv for tech, SEC EDGAR for DD, policy-site Serper
    #     for policy, Europe PMC for clinical).
    # Both stay fail-OPEN at the live seam (ADAPTER/network exception -> 0 new
    # hits; the run degrades to the core Serper/S2 baseline). Skipped on the
    # seed_only deepener pass (no extra retrieval).
    if research_frame is not None and not seed_only:
        # ON-path: need-type registry dispatch. NO domain literal consulted.
        try:
            from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                run_need_type_backends,
            )
            need_result = run_need_type_backends(
                frame=research_frame,
                research_question=research_question,
                amplified_queries=amplified_queries,
                anchor_seed=anchor_seed,
            )
            for cand in need_result.candidates:
                url = cand.url
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                if not getattr(cand, "query_origin", ""):
                    cand.query_origin = "need_type_backend"
                candidates.append(cand)
            if need_result.backends_used:
                notes.append(
                    f"need_type_backends({need_result.needs}): "
                    f"{need_result.per_backend_counts}"
                )
                for backend_name in need_result.backends_used:
                    api_calls[backend_name] = (
                        api_calls.get(backend_name, 0) + 1
                    )
        except Exception as exc:
            # ADAPTER/network fail-open ONLY. A MalformedPlanError cannot reach
            # here — it raised at Step 0 before the baseline ran.
            logger.warning(
                "[live_retriever] need_type_backends failed (fail-open): %s",
                exc,
            )
    elif domain and not seed_only:
        try:
            from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                run_domain_backends,
            )
            domain_result = run_domain_backends(
                domain=domain,
                research_question=research_question,
                amplified_queries=amplified_queries,
            )
            for cand in domain_result.candidates:
                url = cand.url
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                # I-meta-002-q1d (#951): give domain-backend candidates a stable origin
                # bucket so the per-sub-query rerank reservation handles them consistently.
                if not getattr(cand, "query_origin", ""):
                    cand.query_origin = "domain_backend"
                candidates.append(cand)
            if domain_result.backends_used:
                notes.append(
                    f"domain_backends({domain}): "
                    f"{domain_result.per_backend_counts}"
                )
                for backend_name in domain_result.backends_used:
                    api_calls[backend_name] = (
                        api_calls.get(backend_name, 0) + 1
                    )
        except Exception as exc:
            logger.warning(
                "[live_retriever] domain_backends failed for %r: %s",
                domain, exc,
            )

    total_pre_filter = len(candidates)
    logger.info("[live_retriever] %d unique candidates from search", total_pre_filter)

    # ── Step 3: prefetch off-topic filter ──────────────────────────
    if enable_prefetch_filter and candidates:
        # FX-15b (#1119): EXCLUDE the injected seeds (empty title/snippet, source in
        # _SEED_SOURCE_LABELS) from the semantic off-topic filter. They have no snippet to embed,
        # so `filter_search_results` would score them ~0 similarity and REJECT the entire reserved
        # seed lane (e.g. all agentic seeds). Filter only the non-seed search candidates; re-prepend
        # the seeds untouched (mirrors the seed split in `_rerank_and_reserve`). Seeds are never
        # off-topic-dropped — exactly as before this lane could enable the filter.
        _seed_cands = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
        _nonseed_cands = [
            c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS
        ]
        if _nonseed_cands:
            _pre_offtopic_urls = {c.url for c in _nonseed_cands}
            filt = filter_search_results(_nonseed_cands, research_question)
            candidates = _seed_cands + filt.kept
            for _dropped_url in _pre_offtopic_urls - {c.url for c in filt.kept}:
                _trace_drop(_dropped_url, "offtopic")
                drop_reasons["offtopic"] += 1
            notes.append(
                f"prefetch_offtopic: {filt.total_kept} kept / "
                f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
            )
            # I-ready-017 Task 2a (#1204): persist the off-topic split. Store the
            # raw threshold float (not the :.2f note string) so the manifest
            # carries the unrounded value used in the filter decision.
            prefetch_offtopic = {
                "kept": filt.total_kept,
                "rejected": filt.total_rejected,
                "threshold": filt.threshold_used,
            }
        # else: only seeds present (e.g. seed_only mode) — nothing to off-topic filter.
    kept_by_offtopic = len(candidates)

    # ── Step 4: fetch-time relevance rerank + per-sub-query reservation, then cap ──
    # I-meta-002-q1d (#951, #943): replace arrival-order truncation with a no-spend,
    # no-model-load lexical relevance rerank that reserves >=1 slot per sub-query so a
    # long full-paragraph query cannot monopolize the cap (the breadth of amplified
    # queries was previously illusory). I-bug-776 (#817) layer-4 seed lane preserved:
    # primary-trial DOI seeds (empty title/snippet) are split out and prepended AFTER
    # ranking so relevance scoring can never drop them — they remain additive.
    _pre_rerank_urls = {c.url for c in candidates}
    # B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-THRESHOLD + fetch-BUDGET
    # selection (PG_RETRIEVAL_RELEVANCE_GATE=1). Replaces the fixed top-N COUNT cut
    # with a topical-relevance THRESHOLD scored by B1's semantic embedder, carrying
    # each kept source's relevance score forward as a weight and RECORDING the
    # unfetched-but-relevant tail instead of dropping-and-forgetting. OFF (default)
    # => the legacy `_rerank_and_reserve` count-cut runs byte-identically AND the
    # semantic embedder is never imported. ON + embedder unavailable => LOUD
    # fallback to the SAME legacy cut (LAW II: no silent degrade).
    _b4_relevance_weights: dict[str, float] = {}
    _b4_gate: Optional[RelevanceGateResult] = None
    _b4_selected: Optional[list[SearchCandidate]] = None
    if _relevance_gate_enabled():
        _b4_selected, _b4_relevance_weights, _b4_gate = _relevance_threshold_select(
            candidates,
            research_question=research_question,
            sub_queries=list(effective_queries),
            fetch_cap=fetch_cap,
            n_seed_injected=_n_seed_injected,
        )
        if _b4_selected is None:
            logger.warning(
                "[live_retriever] B4 relevance gate ON but semantic scorer "
                "unavailable — falling back LOUDLY to the legacy lexical cut."
            )
    if _b4_selected is not None:
        candidates = _b4_selected
    else:
        candidates = _rerank_and_reserve(
            candidates,
            research_question=research_question,
            fetch_cap=fetch_cap,
            n_seed_injected=_n_seed_injected,
        )
    _rerank_dropped_urls = _pre_rerank_urls - {c.url for c in candidates}
    # B4: split the topical OFF-topic drops from the cost-bound RELEVANT tail so
    # the recall cost is attributable. On the B4 ON path, the unfetched-but-
    # relevant tail is a COST drop (above threshold, beyond budget) recorded under
    # `relevance_budget_tail`; truly off-topic drops are `offtopic_below_threshold`.
    if _b4_gate is not None:
        drop_reasons.setdefault("relevance_budget_tail", 0)
        drop_reasons.setdefault("offtopic_below_threshold", 0)
        drop_reasons["relevance_budget_tail"] += _b4_gate.unfetched_relevant_tail
        drop_reasons["offtopic_below_threshold"] += _b4_gate.dropped_off_topic
        for _dropped_url in _rerank_dropped_urls:
            _trace_drop(_dropped_url, "relevance_gate_not_fetched")
        _msg = (
            f"relevance_gate: threshold={_b4_gate.threshold:.2f} scored="
            f"{_b4_gate.total_scored} on_topic={_b4_gate.kept_on_topic} "
            f"off_topic={_b4_gate.dropped_off_topic} fetched={_b4_gate.fetched_budget} "
            f"unfetched_relevant_tail={_b4_gate.unfetched_relevant_tail} "
            f"(fetch_cap={fetch_cap} scorer={_b4_gate.scorer})"
        )
        logger.info("[live_retriever] %s", _msg)
        notes.append(_msg)
    else:
        for _dropped_url in _rerank_dropped_urls:
            _trace_drop(_dropped_url, "rerank_not_selected")
            drop_reasons["rerank_not_selected"] += 1
        # F15 (GH #1245 / D11): surface the REAL rerank-cut count honestly. The bug
        # was a `dropped=0` line printed while 539 candidates were cut by the
        # fetch-cap rerank — the count existed in `drop_reasons` but was never
        # surfaced to the operator. This LOUD note makes the cut auditable. These
        # are candidates the fetch_cap could not afford to fetch (a real resource
        # bound, not a credibility filter); they are reported, not hidden as 0.
        if _rerank_dropped_urls:
            _msg = (
                f"rerank_not_selected: cut {len(_rerank_dropped_urls)} of "
                f"{len(_pre_rerank_urls)} candidates to fit fetch_cap={fetch_cap} "
                f"(kept {len(candidates)})"
            )
            logger.info("[live_retriever] %s", _msg)
            notes.append(_msg)

    classified_sources: list[CorpusSource] = []
    evidence_rows: list[dict[str, Any]] = []
    fetched = 0
    failed_fetch = 0
    # I-ready-017 #1134: journal_only metadata sidecar (ON-path only). Keyed by
    # canonical URL; carries per-source journal-article signals for the
    # citeability predicate. Stays None when the flag is OFF (byte-identical).
    from src.polaris_graph.nodes.journal_only_filter import (
        journal_only_flag_enabled as _jo_flag_enabled,
        journal_metadata_entry as _jo_meta_entry,
        canonicalize_url as _jo_canon,
    )
    _journal_only_on = _jo_flag_enabled()
    _journal_sidecar: dict[str, Any] = {} if _journal_only_on else {}

    # ------------------------------------------------------------------
    # M-INT-1 — Parallel fetch into live_retriever (Phase E1)
    # ------------------------------------------------------------------
    # Wires `parallel_fetch.parallel_fetch(...)` into the content-fetch
    # loop. Per FINAL_PLAN.md M-INT-1: imported, invoked, run-log
    # evidence, and PG_USE_PARALLEL_FETCH=0 disables (rollback).
    #
    # The substrate's ParallelFetcher Protocol expects (bytes, str,
    # int). Live retrieval's existing _fetch_content returns
    # (content, ok, title, body_type, jsonld) — we wrap it in an adapter
    # that stashes the full 5-tuple in a side dict keyed by URL,
    # then post-process serially using the side dict. Diff-gate P1-C: the 5th
    # element is the raw ld+json captured before _strip_html (Signal C input).
    use_parallel = os.environ.get("PG_USE_PARALLEL_FETCH", "1") != "0"
    fetched_side: dict[str, tuple[str, bool, str, str, str]] = {}
    # I-fetch-003 (#1175 / AC3): retrieval-throughput diagnostics. Stay None on
    # the serial fallback / no-candidates path (no parallel_fetch report).
    _fetch_success_rate: float | None = None
    _parallel_completion_rate: float | None = None
    _fetch_workers: int | None = None
    _distinct_hosts: int | None = None

    if use_parallel and candidates:
        from src.polaris_graph.audit_ir.parallel_fetch import (
            FetchOutcome,
            FetchTask,
            parallel_fetch,
        )

        class _LiveContentParallelFetcher:
            """Adapter wrapping `_fetch_content(url, max_chars)` for
            the parallel_fetch substrate's ParallelFetcher Protocol.
            Stashes the full 5-tuple (content, ok, title, body_type, jsonld)
            in a thread-safe side dict so the post-processing loop
            can read it back per-candidate."""

            def __init__(self, max_chars: int) -> None:
                self.max_chars = max_chars
                self._lock = threading.Lock()
                self.results = fetched_side

            def fetch(
                self, task: "FetchTask"
            ) -> tuple[bytes, str, int]:
                # I-meta-007c: surface the per-candidate DOI/PMID hints
                # (stashed in task_metadata at task construction) so the OA
                # resolver can fire on the DEFAULT parallel path, not just the
                # serial fallback.
                _meta = task.task_metadata or {}
                content, ok, title, body_type, jsonld = _fetch_content(
                    task.source_url, self.max_chars,
                    doi_hint=str(_meta.get("doi") or ""),
                    pmid_hint=str(_meta.get("pmid") or ""),
                )
                with self._lock:
                    self.results[task.source_url] = (
                        content, ok, title, body_type, jsonld,
                    )
                payload = (content or "").encode("utf-8", errors="replace")
                return (payload, "text/plain", 200 if ok else 502)

        # I-fetch-003 (#1175 / BB5-C02): scale max_workers with the candidate
        # count instead of a flat default-8. Explicit env wins; when UNSET,
        # min(_CEILING, max(_FLOOR, len(candidates) // _PER_CANDIDATE)). Named
        # constants (LAW VI — no magic numbers). For ~740 candidates this
        # yields ~46 workers; small corpora stay at the floor of 8.
        _explicit_workers = os.environ.get("PG_LIVE_RETRIEVER_MAX_WORKERS")
        if _explicit_workers is not None:
            try:
                max_workers = max(1, int(_explicit_workers))
            except ValueError:
                max_workers = _FETCH_WORKERS_FLOOR
        else:
            max_workers = min(
                _FETCH_WORKERS_CEILING,
                max(
                    _FETCH_WORKERS_FLOOR,
                    len(candidates) // _FETCH_WORKERS_PER_CANDIDATE,
                ),
            )
        try:
            per_task_timeout = float(os.environ.get(
                "PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS", "120",
            ))
        except ValueError:
            per_task_timeout = 120.0

        # I-fetch-003 (#1175 / BB5-C02): per-HOST politeness limit. The
        # parallel_fetch semaphore is keyed by FetchTask.backend_id; keying it
        # by the URL host (below) gives each host its own Semaphore so distinct
        # hosts fetch concurrently while same-host stays capped. Env-overridable;
        # default mirrors parallel_fetch DEFAULT_PER_BACKEND_LIMIT (4).
        _per_host_limit = _env_int(
            "PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT",
            _PARALLEL_FETCH_DEFAULT_PER_BACKEND_LIMIT,
        )

        fetch_tasks = []
        _per_host_concurrent: dict[str, int] = {}
        for idx, c in enumerate(candidates):
            # I-meta-007c: carry the candidate's DOI/PMID hints into the
            # FetchTask so _LiveContentParallelFetcher.fetch can pass them to
            # _fetch_content for the OA resolver (default = parallel path).
            _doi, _pmid = _candidate_oa_hints(getattr(c, "metadata", None))
            # I-fetch-003 (#1175): key the rate-limit class by URL host so the
            # parallel_fetch host-semaphore yields cross-host parallelism.
            _host = urlsplit(c.url).hostname or "default"
            _per_host_concurrent[_host] = _per_host_limit
            fetch_tasks.append(
                FetchTask(
                    source_url=c.url,
                    backend_id=_host,
                    task_metadata={"index": idx, "doi": _doi, "pmid": _pmid},
                )
            )
        fetcher = _LiveContentParallelFetcher(DEFAULT_CONTENT_MAX_CHARS)
        parallel_report = parallel_fetch(
            fetch_tasks, fetcher,
            max_workers=max_workers,
            per_backend_max_concurrent=_per_host_concurrent,
            per_task_timeout=per_task_timeout,
        )
        # Run-log evidence: persist the substrate's report into
        # api_calls so the manifest sees a non-zero invocation count.
        api_calls["parallel_fetch_success_count"] = (
            parallel_report.success_count
        )
        api_calls["parallel_fetch_errored_count"] = (
            parallel_report.errored_count
        )
        api_calls["parallel_fetch_timeout_count"] = (
            parallel_report.timeout_count
        )
        # BB5-S02 (#1177): surface the leaked-bypass-worker gauge (abandoned
        # in-flight workers that may hold orphan browser subprocesses) into the
        # manifest so the resource-leak signal is auditable, not log-only.
        try:
            from src.tools.access_bypass import bypass_leaked_worker_count
            api_calls["bypass_leaked_worker_count"] = (
                bypass_leaked_worker_count()
            )
        except Exception:  # noqa: BLE001 — telemetry only; never break fetch
            pass
        logger.info(
            "[live_retriever] M-INT-1 parallel_fetch: %d success, "
            "%d errored, %d timeout (max_workers=%d, "
            "per_task_timeout=%.0fs)",
            parallel_report.success_count,
            parallel_report.errored_count,
            parallel_report.timeout_count,
            max_workers, per_task_timeout,
        )
        # GH #1258 PART 2: parallel_fetch (the longest network-bound phase) just returned —
        # tick the heartbeat so a human tailing run_status.json sees the run advance out of
        # the fetch wait instead of a frozen scope_gate_passed snapshot.
        _emit_progress("retrieval_fetched", sources_kept=parallel_report.success_count)
        # I-fetch-003 (#1175 / AC3): NEW retrieval-throughput diagnostics.
        # fetch_success_rate = usable / (usable + failed): a SUCCESS outcome
        # with a 2xx status is "usable"; an ERRORED/TIMEOUT or a non-2xx
        # SUCCESS (the adapter returns 502 when _fetch_content reports not-ok)
        # is "failed". parallel_completion_rate = completed-in-deadline /
        # submitted (1 - timeout_fraction). These are SIBLING fields surfaced on
        # LiveRetrievalResult; they are NOT folded into api_calls (contract
        # stays unwidened, M-INT-1 fields above unchanged).
        _usable_fetched = sum(
            1 for r in parallel_report.results
            if r.outcome is FetchOutcome.SUCCESS
            and (r.fetch_status_code or 0) < 400
        )
        _failed_fetched = len(parallel_report.results) - _usable_fetched
        _denom = _usable_fetched + _failed_fetched
        _fetch_success_rate = (
            _usable_fetched / _denom if _denom > 0 else None
        )
        _submitted = len(parallel_report.results)
        # I-fetch-003 (#1175): a NOT_DISPATCHED task (batch-budget starvation)
        # never ran — it is NOT a completion. Subtract it alongside timeouts so
        # a starved batch reports a LOW completion rate (else the AC3 diagnostic
        # this issue added would paint a starved run as near-fully-complete).
        _parallel_completion_rate = (
            (
                _submitted
                - parallel_report.timeout_count
                - parallel_report.not_dispatched_count
            ) / _submitted
            if _submitted > 0 else None
        )
        _fetch_workers = max_workers
        _distinct_hosts = len(_per_host_concurrent)
        if (
            _fetch_success_rate is not None
            and _fetch_success_rate < _FETCH_SUCCESS_RATE_WARN_FLOOR
        ):
            logger.warning(
                "[live_retriever] I-fetch-003 LOW fetch_success_rate %.2f "
                "(< floor %.2f): %d usable / %d submitted across %d hosts, "
                "%d timeout — corpus may be starved; check per-host limit / "
                "max_workers / per_task_timeout.",
                _fetch_success_rate,
                _FETCH_SUCCESS_RATE_WARN_FLOOR,
                _usable_fetched, _submitted, _distinct_hosts,
                parallel_report.timeout_count,
            )

    # #554 (I-bug-115): bound the synchronous post-fetch candidate loop so a
    # wedged per-candidate operation can never hang the run with no terminal
    # verdict. Layer 1 = per-candidate enrich bound (_bounded_openalex_enrich);
    # Layer 2 = this overall wall-clock budget; Layer 3 = per-candidate
    # progress logging below so any future loop stall is diagnosable.
    # I-ready-003 (#1074) P1: the post-fetch loop processes ALL ~fetch_cap candidates serially (each
    # paying an OpenAlex enrich round-trip + tier-classify). A FIXED budget that does NOT scale with
    # fetch_cap silently TRUNCATES the corpus at full cap (the I-cap-005 ~40-URL silent-throttle class,
    # one layer deeper): the slate raised fetch_cap 25x without scaling this wall-clock budget, so the
    # loop hit the deadline mid-corpus, set corpus_truncated, and broke — a "1000-URL" run classified
    # only the first few hundred. Scale the budget with fetch_cap: max(explicit env floor, fetch_cap *
    # per-URL budget). BYTE-IDENTICAL for small caps (the 900s env floor wins when fetch_cap is small);
    # a conservative operator env can no longer silently win because the fetch_cap term floors it.
    _loop_deadline = time.monotonic() + _post_fetch_loop_budget(fetch_cap)
    _enrich_failfast = _env_int("PG_OPENALEX_ENRICH_FAILFAST", 3)
    _enrich_stats: dict[str, int] = {}
    _enrich_disabled = False

    # #958 (S2): corpus-truncation counters. Initialized BEFORE the loop so the
    # empty/no-break path does not depend on a loop-local `i` (Codex P2). Default
    # = "processed all" / not truncated; the budget-break below overrides.
    _corpus_truncated = False
    _candidates_total = len(candidates)
    _candidates_processed = len(candidates)

    # I-arch-004 F18b (#1255): how to treat a mid-corpus budget break. Read ONCE
    # before the loop (LAW VI). Default 'warn' = legacy flag+break (byte-identical).
    _trunc_policy = _corpus_truncation_policy()
    _repair_logged = False
    # GH #1258 PART 2: heartbeat-tick stride for the per-URL classification loop (LAW VI). Default
    # 25 candidates ≈ one tick every few seconds at full fetch_cap; clamped >=1 so a misconfig can
    # never make `i % stride` a ZeroDivisionError. Only consulted when progress_cb is wired.
    _progress_stride = max(1, _env_int("PG_RETRIEVAL_PROGRESS_STRIDE", 25))

    for i, cand in enumerate(candidates):
        if time.monotonic() > _loop_deadline:
            if _trunc_policy == "repair":
                # §-1.3: do NOT ship a thinned corpus. Keep processing the
                # remaining candidates so recall is preserved. The per-candidate
                # Layer-1 bound (_bounded_openalex_enrich) still prevents a single
                # wedged candidate from hanging the run, so the loop-level deadline
                # can be advisory here. Log once to avoid per-iteration spam.
                if not _repair_logged:
                    logger.warning(
                        "[live_retriever] post-fetch loop budget exceeded at "
                        "candidate %d/%d — PG_CORPUS_TRUNCATION_POLICY=repair: "
                        "continuing to process the remaining corpus (no truncation)",
                        i, len(candidates),
                    )
                    _repair_logged = True
                # fall through (no break) — corpus_truncated stays False.
            elif _trunc_policy == "fail_closed":
                # Raise BEFORE generation bills any token so a partial corpus
                # never ships. The caller surfaces this as a loud run failure.
                logger.error(
                    "[live_retriever] post-fetch loop budget exceeded at "
                    "candidate %d/%d — PG_CORPUS_TRUNCATION_POLICY=fail_closed: "
                    "aborting (refusing to ship a truncated corpus)",
                    i, len(candidates),
                )
                raise CorpusTruncationError(
                    f"corpus truncated at candidate {i}/{len(candidates)} "
                    f"(post-fetch loop budget exceeded); "
                    f"PG_CORPUS_TRUNCATION_POLICY=fail_closed"
                )
            else:
                # 'warn' (default, legacy): record the truncation as a fail-loud
                # signal (was log-only) and BREAK. candidates_processed = the
                # zero-based break index i = post-filter candidates whose loop
                # iteration began before the cutoff (Codex P2).
                logger.warning(
                    "[live_retriever] post-fetch loop budget exceeded — stopping "
                    "at candidate %d/%d (%d already classified)",
                    i, len(candidates), len(classified_sources),
                )
                _corpus_truncated = True
                _candidates_processed = i
                break
        logger.info(
            "[live_retriever] post-fetch candidate %d/%d %s",
            i + 1, len(candidates), cand.url[:60],
        )
        # GH #1258 PART 2: tick the heartbeat every N candidates during the per-URL
        # OpenAlex-enrich + tier-classify loop (the CPU-bound "embedding-rerank" phase that
        # otherwise runs silent for minutes). Stride-gated (env-overridable) so the cost is a
        # single env read + a modulo per iteration; the actual writes happen only every N URLs.
        if progress_cb is not None and (i % _progress_stride == 0):
            _emit_progress(
                "retrieval_classifying",
                sources_kept=len(classified_sources),
            )
        if use_parallel:
            content, ok, content_title_from_fetch, body_article_type, raw_jsonld = (
                fetched_side.get(cand.url, ("", False, "", "", ""))
            )
        else:
            # Fallback serial path (PG_USE_PARALLEL_FETCH=0).
            # Rate-limit gently (Serper doesn't but S2 prefers <= 1rps)
            if i > 0 and i % 5 == 0:
                time.sleep(0.2)
            # I-meta-007c: thread the DOI/PMID hints from S2 metadata so the
            # OA resolver can fire when AccessBypass returns a stub/paywall.
            _cand_doi, _cand_pmid = _candidate_oa_hints(
                getattr(cand, "metadata", None)
            )
            # Fetch content (for tier classification + evidence)
            content, ok, content_title_from_fetch, body_article_type, raw_jsonld = (
                _fetch_content(
                    cand.url, DEFAULT_CONTENT_MAX_CHARS,
                    doi_hint=_cand_doi, pmid_hint=_cand_pmid,
                )
            )
        api_calls["fetch"] += 1
        if not ok:
            failed_fetch += 1
            _trace_drop(cand.url, "fetch_failed")
            drop_reasons["fetch_failed"] += 1
        else:
            fetched += 1

        # Optional OpenAlex enrichment — wall-clock-bounded (#554). After
        # PG_OPENALEX_ENRICH_FAILFAST timeouts in this run, stop attempting
        # enrichment: it prevents abandoned daemon threads from accumulating
        # when OpenAlex is degraded for the whole run.
        oa = {}
        if enable_openalex_enrich and not _enrich_disabled:
            oa = _bounded_openalex_enrich(cand.url, cand.title, _enrich_stats)
            if oa:
                api_calls["openalex"] += 1
            if _enrich_stats.get("enrich_timeouts", 0) >= _enrich_failfast:
                _enrich_disabled = True
                logger.warning(
                    "[live_retriever] OpenAlex enrich timed out %dx — "
                    "disabling enrichment for the rest of this run",
                    _enrich_stats["enrich_timeouts"],
                )

        # Classify via tier_classifier
        domain_ = _domain_of(cand.url)
        # BUG-M-12 / M-13 (Codex pass 12/13): title resolution order
        # (longest → most reliable):
        #   1. OpenAlex display_name (full title from DOI lookup when
        #      URL embeds a DOI; otherwise from title-search fallback)
        #   2. Content-extracted title from fetched page (Jina/Crawl4AI
        #      markdown or HTML <title>) — catches MDPI/JAMA/PMC URLs
        #      where DOI isn't in the URL path
        #   3. Serper snippet title (often truncated)
        # Existing detectors (_detect_systematic_review_from_title,
        # _detect_narrative_flavor_from_title) then see the full
        # suffix and demote correctly.
        # BUG-M-14 (Codex pass 14): use the title extracted at fetch
        # time (from raw content BEFORE _strip_html stripped tags)
        # rather than trying to re-extract from the already-stripped
        # text. Fall back to the content-based extraction on stripped
        # text in case fetch didn't populate it.
        content_title = content_title_from_fetch or _extract_title_from_content(content)
        openalex_title = oa.get("openalex_full_title", "") or ""
        # Pick the longest candidate — longer titles carry more signal
        # (SR/MA / perspective / guidance suffixes).
        title_candidates = [t for t in (openalex_title, content_title, cand.title) if t]
        if title_candidates:
            classifier_title = max(title_candidates, key=len)
        else:
            classifier_title = cand.title or ""
        # Phase 0a (C1/C5): reconstruct the additive AuthoritySignals payload
        # from the live-path enrich dict. Absent/partial -> None / partial ->
        # the authority model returns LOW confidence (fail-honest). Inert on the
        # OFF path (the legacy rule body never reads `.authority`).
        authority_payload = None
        _auth_dict = oa.get("authority_signals")
        if isinstance(_auth_dict, dict):
            authority_payload = AuthoritySignals(
                cited_by_count=_auth_dict.get("cited_by_count"),
                source_id=_auth_dict.get("source_id", "") or "",
                venue_summary_stats=_auth_dict.get("venue_summary_stats"),
                is_core=_auth_dict.get("is_core"),
                is_in_doaj=_auth_dict.get("is_in_doaj"),
                apc_prices=_auth_dict.get("apc_prices"),
                publication_year=_auth_dict.get("publication_year"),
                ror_id=_auth_dict.get("ror_id", "") or "",
                institution_type=_auth_dict.get("institution_type", "") or "",
                country_code=_auth_dict.get("country_code", "") or "",
            )
        # I-ready-017 #1134: resolve the article DOI for the journal_only
        # citeability predicate (ADDITIVE — sourced from the candidate's OA
        # hints; "" when unknown). Cheap, no network.
        _jo_doi, _jo_pmid = _candidate_oa_hints(getattr(cand, "metadata", None))
        signals = ClassificationSignals(
            url=cand.url,
            title=classifier_title,
            publisher="",
            fetched_content_length=len(content),
            openalex_publication_type=oa.get("openalex_pub_type", "") or "",
            openalex_source_type=oa.get("openalex_source_type", "") or "",
            openalex_is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
            # F12 (GH #1245 / D12): wire the resolved OpenAlex venue into the
            # classifier so a doi.org-hosted canonical-DOI journal (JEP/JPE) is
            # trusted by _is_doi_org_journal_with_venue instead of being demoted
            # to T4 by R9's unverified-host guard. Without this line the
            # classifier fix is INERT on the live cert path (the run-killer
            # path). "" when OpenAlex returned no venue (demotion preserved).
            openalex_venue=oa.get("openalex_venue", "") or "",
            doi=str(_jo_doi or ""),
            source_type_hint="",
            # BUG-M-17 (Codex pass 2): body-inspection secondary signal.
            body_article_type=body_article_type,
            authority=authority_payload,
            # Diff-gate P1-B/P1-C: wire the structural junk inputs so Signal C
            # (junk_detection) can actually fire on the ON path. INERT when OFF
            # (the legacy rule body never reads these).
            #   * fetched_body = the stripped visible page text (survives
            #     _strip_html; carries press-release / login-wall body cues).
            #   * structured_jsonld = the RAW ld+json <script> block contents
            #     captured by _fetch_content BEFORE _strip_html deleted the
            #     <script> blocks (P1-C). Without this the NewsArticle @type
            #     marker never reaches the classifier on the live path — it is
            #     destroyed by stripping. Honestly empty when the fetch backend
            #     already returned cleaned text (Jina/Crawl4AI) with no JSON-LD.
            #   * claim_vendor_token = the lowercased research question, used by
            #     the self-interest check (exact host-org-token == vendor-token
            #     equality, so a phrase can never false-fire). Extracting single
            #     candidate vendor tokens from the question is a Gate-A residual.
            fetched_body=content or "",
            structured_jsonld=raw_jsonld or "",
            claim_vendor_token=(research_question or "").strip().lower(),
        )
        tier_result = classify_source_tier(signals)

        classified_sources.append(CorpusSource(
            url=cand.url,
            title=cand.title,
            domain=domain_,
            tier=tier_result.tier.value,
            tier_confidence=tier_result.confidence,
            tier_rule=tier_result.matched_rules[0] if tier_result.matched_rules else "",
            tier_reasons=list(tier_result.reasons),
        ))

        # I-ready-017 #1134: record the per-source journal-article signals into
        # the journal_only sidecar (ON-path only; keyed by canonical URL). The
        # citeability predicate reads these. OFF → never populated (no-op).
        if _journal_only_on:
            # Codex diff-gate P2: resolve the DOI from candidate metadata, then
            # the OpenAlex work DOI, then a DOI embedded in the URL — so an anchor
            # discovered via a Serper/URL-only path is still credited.
            _jo_doi_resolved = str(_jo_doi or "") or str(oa.get("doi", "") or "")
            if not _jo_doi_resolved:
                _jo_doi_m = re.search(r"10\.\d{4,9}/[^\s?#\"'<>]+", cand.url or "")
                if _jo_doi_m:
                    _jo_doi_resolved = _jo_doi_m.group(0)
            _journal_sidecar[_jo_canon(cand.url)] = _jo_meta_entry(
                openalex_pub_type=oa.get("openalex_pub_type", "") or "",
                openalex_source_type=oa.get("openalex_source_type", "") or "",
                is_peer_reviewed=bool(oa.get("is_peer_reviewed", False)),
                is_retracted=bool(oa.get("is_retracted", False)),
                doi=_jo_doi_resolved,
                venue=oa.get("openalex_venue", "") or "",
            )

        # Build direct_quote: head-window (first 1500 chars) PLUS 500-char
        # windows around every decimal in the full content. This way the
        # Phase-4 provenance verifier can find numeric claims that live
        # deep in the fetched HTML (e.g., STEP 5 -15.2% on page 3 of a
        # Nature paper). Without this, strict_verify drops real data
        # because the number it's looking for is outside the head window.
        if content:
            # R-5 Fix D: content-starved evidence (PDF metadata, empty body,
            # formatting noise). F30 (#1245): landing/abstract RECORD pages —
            # methods cannot ground on a landing page. Both are computed once
            # here; the disposition below depends on the §-1.3 redesign flag.
            _starved = is_content_starved(content)
            # F30: a landing/abstract page is full-text-incapable. Only flag it
            # when it is NOT already starved (avoid double-counting) so the two
            # signals are disjoint in the telemetry.
            _is_landing = (not _starved) and _is_landing_or_abstract_page(content)
            # BUG-B02 / BUG-B04 (I-arch-011): degraded-row re-fetch. When this row
            # is about to be flagged degraded (content-less stub / landing-page
            # shell — e.g. the NEJM 489-char / FDA P960009 266-char anti-bot
            # shells that left the disease-staging slot ungroundable) and the
            # default-OFF master flag is enabled, ESCALATE to a forced Zyte browser
            # re-fetch of the ORIGINAL url (a plain re-fetch would re-derive the
            # identical shell through the deterministic free cascade). On a usable,
            # NON-content-starved Zyte result, ADOPT the recovered full text: the
            # row then proceeds through the normal full-text path below (real
            # grounding span, degraded flags never set) and flows through the
            # UNCHANGED strict_verify like any other row. On failure the row stays
            # degraded (the unchanged down-weight/skip logic below runs) and is
            # NEVER passed off as full text. FAIL-LOUD without ZYTE_API_KEY.
            # Faithfulness-neutral: no gate moves, no cap/floor — the recovered
            # span is judged by the SAME is_content_starved heuristic already used.
            #
            # The degraded set is the UNION of three EXISTING signals (no NEW
            # threshold): (1) ``_starved`` (is_content_starved), (2) ``_is_landing``
            # (landing/abstract RECORD page), and (3) ``not ok`` — the FETCH
            # LAYER's OWN paywall-stub verdict for a NON-EMPTY short body (the
            # paywall-stub gate in _fetch_content returns ok=False for the FDA
            # P960009 266-char PMA stub class: thin REAL prose that clears the
            # starvation floor and carries no landing marker, so signals 1+2 alone
            # would MISS it). Reusing the fetch layer's settled ok=False here is
            # NOT a new cap — it is the same stub decision already made upstream.
            if (_starved or _is_landing or not ok) and _refetch_degraded_enabled():
                _refetched = _try_refetch_degraded_row(
                    cand.url, DEFAULT_CONTENT_MAX_CHARS,
                )
                if _refetched and not is_content_starved(_refetched):
                    logger.info(
                        "[live_retriever] B02/B04 RE-FETCH RECOVERED %r "
                        "(stub_len=%d -> zyte_len=%d) — degraded shell upgraded "
                        "to full text via forced Zyte; flows through UNCHANGED "
                        "strict_verify.",
                        cand.url, len(content), len(_refetched),
                    )
                    content = _refetched
                    _starved = False
                    _is_landing = False
                else:
                    # FAITHFULNESS: the re-fetch did not recover this row, so it is
                    # NOT full text. A row that entered via the fetch layer's stub
                    # verdict (``not ok``) but is neither starved nor a landing page
                    # (the FDA P960009 thin-prose stub) would otherwise be admitted
                    # as a NORMAL grounded row — laundering an unrecovered stub. So
                    # mark it content-degraded (``_starved``) so the UNCHANGED
                    # down-weight/skip path below labels + excludes it. This NEVER
                    # passes a stub off as full text; it only fires under the
                    # default-OFF re-fetch flag (OFF => block skipped => byte-
                    # identical, including the legacy ``not ok`` admit behaviour).
                    if not _starved and not _is_landing:
                        _starved = True
                    logger.warning(
                        "[live_retriever] B02/B04 RE-FETCH STILL-DEGRADED %r "
                        "(stub_len=%d ok=%s) — forced Zyte yielded no usable full "
                        "text; row stays LABELED degraded (NOT passed off as full "
                        "text).",
                        cand.url, len(content), ok,
                    )
            _redesign_on = _credibility_redesign_enabled()
            if _starved and not _redesign_on:
                # LEGACY OFF path — byte-identical hard-drop (no row appended).
                logger.info(
                    "[live_retriever] skipping content-starved evidence "
                    "for %r (len=%d)", cand.url, len(content),
                )
                _trace_drop(cand.url, "content_starved")
                drop_reasons["content_starved"] += 1
            else:
                direct_quote = _build_provenance_quote(
                    content, head_chars=1500, window_chars=500,
                )
                _row = {
                    "evidence_id": f"ev_{i:03d}",
                    "source_url": cand.url,
                    "statement": cand.title[:300],
                    # BUG-1 (#1262): carry the already-resolved title onto the
                    # final evidence row so the outline digest / evidence
                    # selector see it. The title was extracted upstream
                    # (classifier_title = the longest of OpenAlex display_name /
                    # _extract_title_from_content / cand.title at ~4231-4239) and
                    # fed to the tier classifier, then SILENTLY DROPPED here —
                    # the row carried only the truncated `statement`, so the
                    # outliner in multi_section_generator placed sources by tier
                    # marker alone ("ev_022 [T2]") and admitted guessing. We do
                    # NOT refetch or recompute — the title already exists; we
                    # simply stop dropping it. Faithfulness is SAFE: a title is
                    # placement/planning metadata only — it never enters a
                    # verified claim, never feeds strict_verify / NLI / 4-role,
                    # and never relaxes a gate (§-1.3 disclose-don't-drop: this
                    # carries information FORWARD, it never drops a source).
                    "title": classifier_title or cand.title or "",
                    "direct_quote": direct_quote,
                    "tier": tier_result.tier.value,
                    "source": cand.source,
                    "full_content_length": len(content),
                    # #956 (S2): the sub-query that surfaced this candidate, so
                    # the evidence selector can reserve per-sub-topic diversity.
                    # Additive only; absent/empty for seed-lane or legacy rows.
                    "query_origin": getattr(cand, "query_origin", "") or "",
                }
                # B4 (b1b10 redesign, I-arch-005 Phase-2/3): carry the source's
                # topical-relevance score FORWARD as a weight. ON-path only
                # (`_b4_relevance_weights` is empty when PG_RETRIEVAL_RELEVANCE_GATE
                # is OFF), so the key is ABSENT on the OFF path => byte-identical.
                # This is a topical-relevance WEIGHT surfaced to composition; it is
                # NOT a credibility/authority weight (those stay the tier/authority
                # surface) and it NEVER gates here — the gate already happened
                # pre-fetch. Seeds carry empty text so they are not in the map.
                _b4_rw = _b4_relevance_weights.get(cand.url)
                if _b4_rw is not None:
                    _row["relevance_weight"] = float(_b4_rw)
                # F15/F30 (§-1.3 WEIGHT-not-FILTER): under the redesign flag, a
                # content-starved or landing-page source is DOWN-WEIGHTED (kept in
                # the pool carrying a low retrieval weight + an honest flag) rather
                # than hard-dropped — every relevant source flows to composition
                # carrying its weight. These additive keys are ABSENT on the OFF
                # path AND on a normal full-text row, so a normal row stays
                # byte-identical. The flags let the composition layer rank these
                # last + refuse to ground a METHODS claim on a landing page.
                if _redesign_on and (_starved or _is_landing):
                    _dw = _down_weight_retrieval()
                    _row["retrieval_weight"] = _dw
                    _row["down_weighted"] = True
                    if _starved:
                        _row["content_starved"] = True
                    if _is_landing:
                        # methods/results cannot be grounded on a landing page.
                        _row["landing_page"] = True
                        _row["full_text_capable"] = False
                    logger.info(
                        "[live_retriever] DOWN-WEIGHT evidence for %r "
                        "(len=%d starved=%s landing=%s weight=%.3f) — kept in "
                        "the pool at low weight, NOT dropped (§-1.3)",
                        cand.url, len(content), _starved, _is_landing, _dw,
                    )
                    _trace_drop(cand.url, "down_weighted")
                    drop_reasons["down_weighted"] += 1
                    if _starved:
                        drop_reasons["content_starved"] += 1
                    if _is_landing:
                        drop_reasons["landing_page"] += 1
                # NOTE: on the OFF path (redesign flag unset) a landing page is
                # NOT flagged or mutated — the row stays byte-identical to the
                # pre-F30 row. F30's flag+down-weight is ON-path only (the weight
                # surface only exists under the redesign), preserving the binding
                # "byte-identical when the flag is OFF" constraint.
                # I-meta-005 Phase 3 (#987): per-row AUTHORITY sidecar. ON-mode
                # ONLY (research_frame present), and INDEPENDENT of the legacy
                # `PG_USE_AUTHORITY_MODEL` tier switch — the plan-sufficiency gate
                # reads the NUMERIC `authority_score`, so planner mode computes it
                # DIRECTLY via the Phase-0a pure function over the SAME `signals`
                # already built for tier classification (no network, spend-free).
                # Honest LOW score/confidence when signals are thin (never a
                # silent 0.0). OFF-mode the keys are ABSENT -> rows byte-identical
                # (the legacy domain-keyed gate never reads them).
                if research_frame is not None:
                    _auth = score_source_authority(signals)
                    _row["authority_score"] = float(_auth.authority_score)
                    _row["authority_confidence"] = _auth.authority_confidence.value
                evidence_rows.append(_row)
                _trace_kept(cand.url, cand.source)

    return LiveRetrievalResult(
        classified_sources=classified_sources,
        evidence_rows=evidence_rows,
        total_candidates_pre_filter=total_pre_filter,
        candidates_kept_by_scope=len(effective_queries),
        candidates_kept_by_offtopic=kept_by_offtopic,
        candidates_fetched=fetched,
        candidates_failed_fetch=failed_fetch,
        api_calls=api_calls,
        notes=notes,
        corpus_truncated=_corpus_truncated,
        candidates_total=_candidates_total,
        candidates_processed=_candidates_processed,
        journal_metadata_sidecar=(_journal_sidecar if _journal_only_on else None),
        fetch_success_rate=_fetch_success_rate,
        parallel_completion_rate=_parallel_completion_rate,
        fetch_workers=_fetch_workers,
        distinct_hosts=_distinct_hosts,
        # I-ready-017 Task 2a (#1204): additive source-funnel telemetry.
        prefetch_offtopic=prefetch_offtopic,
        drop_reasons=drop_reasons,
        # B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-gate telemetry,
        # including the unfetched-but-relevant tail. None when the B4 gate is OFF
        # (PG_RETRIEVAL_RELEVANCE_GATE unset) => byte-identical.
        relevance_gate=(_b4_gate.to_dict() if _b4_gate is not None else None),
        # Codex diff-gate iter-1 P1: freeze the extraction-stage count HERE (at
        # return), before run_one_query mutates evidence_rows via the expansion/
        # deepener/agentic lanes.
        extraction_finding_rows=len(evidence_rows),
    )
