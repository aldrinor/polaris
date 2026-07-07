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
from src.polaris_graph.retrieval import title_body_consistency  # I-deepfix-001 B14 (#1358)
from src.polaris_graph.authority.authority_model import score_source_authority
from src.polaris_graph.authority.source_class import AuthoritySignals
# I-deepfix-001 (#1344) Bug B: the SAME retraction truthiness predicate the credibility
# engine + the generator gate use, so `is_retracted="false"` is correctly NOT retracted
# (bool("false") is True in Python — the coercion bug Codex iter-1 flagged).
from src.polaris_graph.authority.supersession import _is_truthy as _retraction_is_truthy
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationResult,
    ClassificationSignals,
    TierLevel,
    _classify_source_tier_rules,
    _m2_dt,
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
    "id,doi,title,display_name,type,publication_year,publication_date,"
    "cited_by_count,is_retracted,primary_location,authorships"
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
# I-deepfix-001 Codex wave-2 P1: bumped 2 -> 3 so cached payloads predating the
# `publication_date` field are REBUILT (not served stale) — a cached boundary-year
# row that lacks pub_date would otherwise defeat the MONTH-precision date window.
AUTHORITY_CACHE_SCHEMA_VERSION = 3

# Hard caps
DEFAULT_MAX_SERPER = int(os.getenv("PG_LIVE_MAX_SERPER", "20"))
DEFAULT_MAX_S2 = int(os.getenv("PG_LIVE_MAX_S2", "20"))
# I-deepfix-001 D3 breadth (2026-06-29): the fetch BUDGET is the §-1.3 disclosed
# bound (the ONLY thing that limits how far down the demote-not-drop cosine-ordered
# candidate list we fetch). The legacy default of 40 was the dominant breadth lever
# on the diced-preflight drb_72 fixture (926 discovered -> 166 selected -> 149
# fetched: a 760-candidate count-cut). Raised to a generous 200 (5x) — cost is never
# the constraint, time is, and the fetch is BOUNDED-PARALLEL (worker ceiling 48, per-
# host cap 4) so a generous cap stays wall-time sane. Still env-overridable (LAW VI):
# a validation run that wants the FULL discovered pool fetched (dropped_pre_fetch==0)
# sets PG_LIVE_FETCH_CAP higher (and the sweep's own PG_SWEEP_FETCH_CAP, which
# overrides this default on run_live_retrieval's main lane). A CAP, not a target —
# billed by actual fetches, so a generous cap is free insurance.
DEFAULT_FETCH_CAP = int(os.getenv("PG_LIVE_FETCH_CAP", "200"))
# I-deepfix-001 U31 fetch-fidelity (2026-07-01): the legacy per-source extract
# cap of 25000 chars cut 75-87% of long clinical papers mid-body (a full
# systematic review / guideline PDF is ~100K-190K chars; at 25K only the
# abstract + intro survived, so downstream chunk/embed/retrieval never saw the
# methods/results/discussion that carry the dosing, contraindication and
# population claims). Raised to a generous 300000 (12x) so long papers are
# retained whole. This is the FETCH/extract fidelity cap (what is stored per
# source for chunking), NOT a single-prompt cap — the prompt-facing cap lives
# separately in frame_fetcher (`_M66_CONTENT_CAP`). A CAP, not a target: sources
# are stored at their real length, so a generous cap only helps the rare long
# doc and costs nothing on the common short one. Still env-overridable (LAW VI)
# via PG_LIVE_CONTENT_MAX — a memory-constrained box can lower it.
DEFAULT_CONTENT_MAX_CHARS = int(os.getenv("PG_LIVE_CONTENT_MAX", "300000"))
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


# FIX 2 (I-deepfix-001 composition-collapse plan, GH #1344): citation-metadata
# "SHELL" markers. A 200-OK fetch whose VISIBLE body is a citation-EXPORT widget
# (Frey-Osborne ora.ox.ac.uk "[BibTeX][EndNote]"), site/episode NAVIGATION
# (youreverydayai "Episode Categories:" / "Related Episodes:" / "Join the
# discussion"), or a bare title followed by a raw "@article{...}" BibTeX entry
# (a Semantic-Scholar record stub) is captured VERBATIM as the grounding span
# even though it carries NO article prose — starving otherwise-clean baskets.
# classify_block_page and _is_landing_or_abstract_page are both BLIND to this
# class. These are HIGH-PRECISION literals: each is an export-tool / nav / raw-
# BibTeX artefact, never rendered article language, so a full-text article that
# merely quotes a BibTeX block deep in its own references is NEVER flagged (the
# short-body gate below is the primary guard: a real article is > the landing
# max). Matched case-insensitively on the body head only.
_CITATION_METADATA_SHELL_MARKERS = (
    "[bibtex]",
    "[endnote]",
    "export_record",
    "export record",
    "episode categories:",
    "related episodes:",
    "join the discussion",
    "@article{",
)
# Head window for the citation-shell scan. Read at CALL time (LAW VI). Distinct
# knob from the landing-marker window so the two signals stay independently
# tunable.
_CITATION_SHELL_HEAD_CHARS_DEFAULT = 1500
# Master flag env name for the citation-metadata-shell signal (default OFF).
_ENV_CITATION_SHELL_REFETCH = "PG_CITATION_SHELL_REFETCH"


def _citation_shell_refetch_enabled() -> bool:
    """FIX 2: master switch for the citation-metadata-shell signal. Default OFF —
    when ``PG_CITATION_SHELL_REFETCH`` is unset the signal is never computed by
    the caller and the fetch path is BYTE-IDENTICAL. When ON, a flagged shell
    joins the EXISTING forced-Zyte re-fetch + §-1.3 down-weight disposition
    (identical to how F30 landing pages are handled: down-weight + disclose,
    NEVER hard-drop). LAW VI: env-overridable; recognized truthy 1/true/on/yes."""
    return os.environ.get(_ENV_CITATION_SHELL_REFETCH, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _is_citation_metadata_shell(content: str) -> bool:
    """FIX 2 (I-deepfix-001 composition-collapse plan): True iff the fetched body
    is a citation-EXPORT / site-NAV / bare-BibTeX SHELL rather than article text.

    Structurally mirrors ``_is_landing_or_abstract_page``: SHORT-body-gated
    (reuses ``PG_LANDING_PAGE_MAX_CHARS`` <= 3000 so a full-text article that
    quotes a BibTeX block in its references is NEVER flagged) + head-window scan
    + HIGH-PRECISION export-tool / nav literals only. Pure heuristic; no network.
    Thresholds read at CALL time via ``_env_int`` (LAW VI — env-overridable per
    run, not frozen at import). This predicate is PURE and always defined; the
    ``_citation_shell_refetch_enabled`` master flag gates whether the CALLER
    computes + acts on it, so the OFF path stays byte-identical."""
    if not content:
        return False
    stripped = content.strip()
    if len(stripped) > _env_int(
        "PG_LANDING_PAGE_MAX_CHARS", _LANDING_PAGE_MAX_CHARS_DEFAULT
    ):
        return False
    head = stripped[
        : _env_int(
            "PG_CITATION_SHELL_HEAD_CHARS", _CITATION_SHELL_HEAD_CHARS_DEFAULT
        )
    ].lower()
    return any(marker in head for marker in _CITATION_METADATA_SHELL_MARKERS)


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


def _row_degraded_flags(tier_result: Any, *, recovered: bool = False) -> dict[str, Any]:
    """I-deepfix-001 (Codex P1 #2 — no-laundering): the degraded-flag keys to merge onto a
    grounded evidence row so the corpus-adequacy grounded-content count
    (``corpus_adequacy_gate.count_grounded_rows``) EXCLUDES a source the tier layer already
    flagged ``tier_result.fetch_degraded`` (a short KNOWN-scholarly-venue / DOI stub — it keeps
    its venue-authority TIER weight but must not count as grounded content, so venue authority can
    never launder a contentless stub into "adequate"; see ``tier_classifier`` B17).

    The tier classifier sets ``fetch_degraded`` but the live row previously copied only
    ``tier_result.tier.value``, so a stub that is NOT otherwise ``content_starved`` /
    ``landing_page`` / ``fetch_failed`` still counted as grounded. Returns ``{'fetch_degraded':
    True}`` only when the tier layer flagged it; ``{}`` otherwise, so a normal (non-degraded) row is
    BYTE-IDENTICAL.

    ``recovered`` (BUG-B02/B04 forced-refetch): the tier ``fetch_degraded`` is a
    CLASSIFICATION-TIME signal computed on the ORIGINAL stub body. When a forced Zyte re-fetch later
    UPGRADED the stub to full text, the row proceeds as a NORMAL full-text row and that stale flag
    MUST NOT be propagated (the existing design contract — "recovered rows have degraded flags never
    set"). Returns ``{}`` when ``recovered`` regardless of the stale tier flag.

    Faithfulness-NEUTRAL: adds a LABEL only — never a claim/span/citation, never the faithfulness
    engine, and the row keeps its tier WEIGHT (§-1.3 WEIGHT-AND-LABEL, never a drop)."""
    if recovered:
        return {}
    if getattr(tier_result, "fetch_degraded", False):
        return {"fetch_degraded": True}
    return {}


# I-deepfix-001 U10 (Codex P1): the rule name the tier classifier fires for BOTH the
# OpenAlex retraction flag AND a title-only retraction / withdrawal marker
# (tier_classifier._detect_retraction_marker -> matched_rules "R0_retracted").
_TIER_RETRACTION_RULE = "R0_retracted"


def _row_is_retracted(oa: Any, tier_result: Any) -> bool:
    """True iff the grounded evidence row must carry ``is_retracted=True`` for the
    generator retraction grounding gate (``retraction_gate.partition_pool`` keys on
    exactly this row flag).

    Fires when EITHER:
      * the OpenAlex enrichment flags the paper retracted (the legacy leg), OR
      * the tier classifier fired its ``R0_retracted`` rule — which ALSO catches a
        TITLE-ONLY retraction / withdrawal marker whose OpenAlex flag was UNSET
        (I-deepfix-001 U10: a retracted paper re-deposited on a preprint host). Before
        this fix the row was flagged only from the OpenAlex leg, so a title-marker
        retracted paper entered the grounding pool with a non-empty ``direct_quote``.

    Placement / credibility metadata only. The FROZEN faithfulness engine (strict_verify /
    NLI / 4-role D8 / provenance span-grounding) is UNTOUCHED — this feeds the SEPARATE
    clinical-safety retraction gate, not any faithfulness check. Fail-open: on any missing
    signal the row is NOT flagged (a source with no retraction info grounds normally)."""
    if _retraction_is_truthy(oa, "is_retracted"):
        return True
    matched = getattr(tier_result, "matched_rules", None) or ()
    return _TIER_RETRACTION_RULE in matched


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
    # I-deepfix-001 item 4 (#1344): RETRIEVAL-PHASE wall telemetry (render-PASS
    # partial, DISTINCT from corpus_truncated). True iff the per-question retrieval
    # deadline (PG_RETRIEVAL_WALL_SECONDS) tripped in EITHER the search fan-out or
    # the post-fetch classify loop, so the run handed off a PARTIAL corpus and
    # rendered (it did NOT die on a bare timeout, and it is NOT gated out the way
    # corpus_truncated is). `retrieval_queries_skipped` = planned sub-queries never
    # fired; `retrieval_candidates_unclassified` = fetched bodies not reached before
    # the wall. Defaults keep existing constructors valid + byte-identical OFF path
    # (the wall never trips within budget => all False/0).
    retrieval_wall_hit: bool = False
    retrieval_queries_skipped: int = 0
    retrieval_candidates_unclassified: int = 0
    # I-deepfix-001 P1-2 (#1344): True iff the B4 semantic relevance scorer was
    # REQUESTED (PG_RETRIEVAL_RELEVANCE_GATE=1) but the semantic embedder was
    # unavailable so it fell back LOUDLY to the legacy lexical cut (live_retriever
    # ~4423). The winner-firing gate reads this as a SECOND W6/B4 dark signal
    # (independent of evidence_selector._SEMANTIC_EMBEDDER_CACHE): a requested
    # semantic winner that silently degraded to lexical is NOT firing. Default
    # False keeps existing constructors valid + the byte-identical OFF path (the
    # gate is never requested when the B4 gate is OFF).
    semantic_relevance_fell_back: bool = False
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
    # B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-ORDER + fetch-budget
    # selection telemetry. Populated ONLY on the B4 ON path
    # (PG_RETRIEVAL_RELEVANCE_GATE=1); None when OFF => byte-identical. §-1.3
    # DEMOTE-NOT-DROP (I-deepfix-001 D3): the floor no longer hard-drops below-floor
    # candidates — it orders them to the tail and DISCLOSES the demote conversion
    # (`demoted_below_floor` / `demoted_fetched_to_fill` / `demoted_tail`). Records
    # both the above-floor unfetched tail and the below-floor demoted tail (the fetch
    # BUDGET could not afford) so the recall cost is measurable, never dropped-and-
    # forgotten. A plain dict (RelevanceGateResult.to_dict()) so the manifest
    # write is a no-op getattr with a None default for pre-B4 callers.
    relevance_gate: dict[str, Any] | None = None
    # I-wire-001 W2 (#1311): content-relevance judge telemetry — DISTINCT from the
    # B4 `relevance_gate` above so the two never conflate. Populated ONLY on the
    # W2 ON path (PG_CONTENT_RELEVANCE_JUDGE=1); None when OFF => byte-identical.
    # Carries the per-passage DEMOTE dispositions (kept-at-low-weight, never a
    # drop list — §-1.3 weight-not-filter).
    content_relevance: dict[str, Any] | None = None
    #   extraction_finding_rows: the EXTRACTION-stage finding-row count captured
    #     at run_live_retrieval RETURN time (== len(evidence_rows) here), frozen
    #     as an int. Codex diff-gate iter-1 P1: run_one_query MUTATES
    #     retrieval.evidence_rows AFTER this returns (expansion append, deepener/
    #     agentic reassign), so reading len(evidence_rows) at manifest-write time
    #     reports the POST-expansion total, not the extraction yield. This frozen
    #     int is the stable fetched->finding extraction count.
    extraction_finding_rows: int = 0
    # I-deepfix-001 D5 (#1344): the HONEST machine-readable credibility-tiering batch
    # status produced by classify_sources_llm_tiering (a TieringBatchResult.tiering_status:
    # {tiering_mode, llm_success_count, rules_floor_count, fallback_count, error_count,
    # total}). Plumbed through to the durable manifest disclosure so the diced preflight's
    # D5 gate can assert `tiering_mode != 'rules_floor_degraded'` on a FRESH run — i.e. that
    # GLM credibility-tiering actually fired and the batch did not silently collapse to the
    # deterministic rules-floor. Default {} = LLM-tiering OFF, or no deferred sources to tier
    # (the W5 block never ran) => byte-identical OFF path. PURE telemetry: credibility stays a
    # WEIGHT (no drop, no abort — §-1.3); the faithfulness engine is untouched.
    credibility_tiering_status: dict[str, Any] = field(default_factory=dict)
    # I-deepfix-001 (wall/tiering-abort fix, #1344) P1a: fetch-SUBWALL disclosure —
    # DISTINCT from `retrieval_wall_hit`. True iff the content-fetch batch was bounded to a
    # FRACTION of the remaining wall (PG_RETRIEVAL_FETCH_WALL_FRACTION < 1.0) AND that cutoff
    # actually fired (some tasks timed out or were never dispatched before the fetch cutoff).
    # Those candidates flow on as ordinary `fetch_failed` and are DISCLOSED here as a wall
    # cutoff (§-1.3 disclose-don't-drop), never silently dropped. Kept SEPARATE from
    # `retrieval_wall_hit` because the FULL retrieval wall did NOT trip — every planned
    # sub-query fired and the classify/W5 loop kept its reserved slice — so flipping
    # `retrieval_wall_hit` would emit a misleading "N sub-queries unfired" note. Defaults keep
    # existing constructors byte-identical + the OFF path (fraction=1.0 => no subwall =>
    # False/0). `*_count` mirror parallel_report.timeout_count / not_dispatched_count.
    fetch_subwall_hit: bool = False
    fetch_subwall_timeout_count: int = 0
    fetch_subwall_not_dispatched_count: int = 0


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
        # I-deepfix-001 Codex wave-2 P1: full publication_date (YYYY-MM-DD) so the
        # selector can enforce a MONTH-precision date ceiling ("before June 2023").
        "publication_date": work.get("publication_date"),
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
        # U25 (I-deepfix-001): merge the config-driven OpenAlex auth/politeness
        # params (api_key / mailto) onto the ENRICH client too. httpx merges
        # client-level params into every request, so the DOI lookup, the
        # title-search fallback, AND the /sources fetch (which reuses this client)
        # all ride the key. Empty when unset => byte-identical keyless enrich. This
        # lifts the same 2026-02-13 anonymous 503 that was silently starving the
        # authority-signal enrich (venue / retraction / peer-review) path.
        from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
            _openalex_auth_params,
        )
        with httpx.Client(
            timeout=DEFAULT_HTTP_TIMEOUT, params=_openalex_auth_params()
        ) as c:
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


def _retrieval_wall_seconds() -> float:
    """I-deepfix-001 item 4 (#1344): per-question RETRIEVAL-PHASE wall budget.

    The proven hang-fixes (#1264/#1338) bound generate+verify, NOT retrieval. A
    slow-fetch tail (the 90s-per-URL fetch-timeout storm + AccessBypass daemon
    leak) can grind the retrieval phase for tens of minutes so the run never
    reaches CLOSE. This is the relaunch-BLOCKING retrieval-phase deadline: on
    expiry the snowball/fan-out STOPS firing further queries and the
    already-fetched partial corpus is HANDED OFF to tiering/consolidation/
    generation/render WITH disclosure (§-1.3 — the unfetched tail is disclosed,
    NEVER silently dropped, and the run COMPLETES+RENDERS rather than dying on a
    bare timeout).

    Read at CALL time (LAW VI — env-overridable per run). Default 1800s (30 min):
    generous enough that a healthy retrieval never trips it, tight enough that a
    fetch-timeout storm cannot grind for an hour. Pure (env-only); unit-testable.
    """
    return _env_float("PG_RETRIEVAL_WALL_SECONDS", 1800.0)


def _retrieval_fetch_wall_fraction() -> float:
    """I-deepfix-001 (wall/tiering-abort fix, #1344): the FRACTION of the REMAINING
    retrieval wall the content-FETCH batch may consume, so slow web-fetch cannot eat the
    ENTIRE ``PG_RETRIEVAL_WALL_SECONDS`` and starve the post-fetch classify loop (which
    builds the corpus + defers W5 credibility-tiering). The remainder of the wall is
    reserved for classification.

    Read at CALL time (LAW VI — env-overridable per run). Exactly three outcomes:
      * ``PG_RETRIEVAL_FETCH_WALL_FRACTION`` UNSET  -> ``0.75`` (the DEFAULT-ON cap).
      * a valid finite float in ``(0.0, 1.0]``      -> that value.
      * ANY set-but-invalid value (non-numeric, NaN/inf, zero, negative, or > 1.0)
        -> ``1.0`` = LEGACY full-wall fetch budget, byte-for-byte.

    P2 fix (Codex REQUEST_CHANGES): the prior body routed through ``_env_float`` which
    COERCES a garbage / NaN / zero / negative override to the 0.75 default BEFORE the
    range check ever sees it — so a bad env silently imposed a 0.75 recall cap the operator
    never validly requested. Reading the raw value and fail-SAFING every invalid override to
    the legacy 1.0 full-wall makes the docstring's contract TRUE (a garbage knob widens the
    fetch budget, never hides a drop). ``math`` is already imported (used by ``_env_float``).
    Pure (env-only); unit-testable. Faithfulness-neutral: a source not fetched before the cap
    is DISCLOSED via ``fetch_subwall_hit`` / ``notes``, never silently dropped (§-1.3).
    """
    raw = os.getenv("PG_RETRIEVAL_FETCH_WALL_FRACTION")
    if raw is None:
        return 0.75
    try:
        frac = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(frac) or not (0.0 < frac <= 1.0):
        return 1.0
    return frac


def _retrieval_w2_wall_fraction() -> float:
    """I-deepfix-001 (wall/tiering-abort fix, #1344) P1b: the FRACTION of the REMAINING
    retrieval wall the default-on W2 content-relevance batch (Stage-1 reranker one-pass +
    GLM escalation) may consume, so W2 cannot eat the ENTIRE remaining wall and re-starve the
    post-fetch classify/W5 loop it was supposed to protect. The remainder is reserved for
    classification.

    Mirrors :func:`_retrieval_fetch_wall_fraction`'s fail-safe parser exactly. Three outcomes:
      * ``PG_RETRIEVAL_W2_WALL_FRACTION`` UNSET     -> ``0.5`` (DEFAULT-ON: W2 gets at most
        half the remaining wall; classify/W5 keeps the other half).
      * a valid finite float in ``(0.0, 1.0]``      -> that value.
      * ANY set-but-invalid value                   -> ``1.0`` = pass the FULL retrieval
        deadline unchanged = byte-identical to the pre-P1b threading.

    Read at CALL time (LAW VI). Pure (env-only); unit-testable. Faithfulness-neutral: W2 only
    STOPS earlier — content_relevance_judge's always-release keeps un-scored / un-escalated
    passages at FULL weight (never demote-on-timeout, never drop — §-1.3).
    """
    raw = os.getenv("PG_RETRIEVAL_W2_WALL_FRACTION")
    if raw is None:
        return 0.5
    try:
        frac = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(frac) or not (0.0 < frac <= 1.0):
        return 1.0
    return frac


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
# I-deepfix-001 (#1344) WAVE 2 — fetch throughput. Two DEFAULT-OFF flags that
# stop already-FETCHED bodies from being lost under the retrieval wall (the
# throughput collapse behind "only 3 of ~35 queries mattered"):
#   (A) PG_POST_FETCH_ENRICH_PARALLEL — pre-batch the per-candidate OpenAlex
#       enrich in a BOUNDED ThreadPool BEFORE the serial classify loop, so a slow
#       serial enrich tail (~13-30s/source) cannot consume the whole retrieval
#       wall and leave fetched bodies unclassified.
#   (B) PG_WALL_CLASSIFY_RESCUE — at the wall break, keep classifying the
#       remaining already-fetched bodies RULES-ONLY at the deterministic rules-
#       floor tier and KEEP them (§-1.3 keep-not-drop), so they feed the CRAG
#       corrective reserve instead of being dropped.
# Both are FAITHFULNESS-NEUTRAL: enrich is credibility METADATA and the rescue
# only classifies+keeps. The FROZEN faithfulness engine (strict_verify / NLI /
# 4-role D8 / provenance / span-grounding) is byte-untouched — every rescued /
# enriched row still re-passes it unchanged downstream.
# ─────────────────────────────────────────────────────────────────────────────
_ENV_POST_FETCH_ENRICH_PARALLEL = "PG_POST_FETCH_ENRICH_PARALLEL"
_ENV_POST_FETCH_ENRICH_WORKERS = "PG_POST_FETCH_ENRICH_WORKERS"
_ENV_POST_FETCH_ENRICH_WALL_FRACTION = "PG_POST_FETCH_ENRICH_WALL_FRACTION"
_ENV_WALL_CLASSIFY_RESCUE = "PG_WALL_CLASSIFY_RESCUE"
_ENV_WALL_RESCUE_WEIGHT = "PG_WALL_RESCUE_WEIGHT"
# Bounded default worker cap for the Fix-A pre-batch (LAW VI — env-overridable):
# enough concurrency to collapse the serial enrich tail, small enough to never
# fan out unbounded onto OpenAlex.
_POST_FETCH_ENRICH_WORKERS_DEFAULT = 8
# WAVE-2 Fix B rules-floor WEIGHT for a wall-rescued body (§-1.3 keep-at-floor,
# NEVER drop). Mirrors content_relevance_judge._DEFAULT_DEMOTE_WEIGHT (0.25): a
# source classified RULES-ONLY past the wall never had its content-relevance
# scored, so it is KEPT at the low-but-nonzero rules floor — never at full (1.0)
# weight (which would falsely rank it as fully relevant) and never at zero (a
# drop). Clamped to (0, 1] by `_wall_rescue_weight`.
_WALL_RESCUE_WEIGHT_DEFAULT = 0.25
# Disclosed, KEEP-NEUTRAL telemetry label for a wall-rescued body. Deliberately
# NOT `demoted`/`escalated_demoted` (weighted_enrichment._CONFIRMED_OFFTOPIC_LABELS)
# — a rescued body was NEVER judged off-topic, only left unscored past the wall, so
# marking it off-topic would suppress its cite surface (a §-1.3 drop). This label
# is keep-neutral everywhere it is read (never suppressed), only surfacing the
# honest "kept at the rules floor because the wall was hit" disclosure.
_WALL_RESCUE_LABEL = "wall_rescue_floor"


def _post_fetch_enrich_parallel_enabled() -> bool:
    """WAVE-2 Fix A master switch (default OFF). Unset => the post-fetch loop runs
    the serial per-candidate OpenAlex enrich exactly as before (BYTE-IDENTICAL).
    ON => the enrich is pre-batched in a BOUNDED ThreadPool before the classify
    loop so the serial enrich tail cannot burn the retrieval wall and drop
    already-fetched bodies unclassified. LAW VI env-overridable; truthy
    1/true/on/yes. Faithfulness-neutral (enrich is credibility metadata)."""
    return os.environ.get(_ENV_POST_FETCH_ENRICH_PARALLEL, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _post_fetch_enrich_workers() -> int:
    """Bounded worker cap for the Fix-A parallel enrich pre-batch (LAW VI). Default
    8 — a sane bound (clamped >=1 by ``_env_int``); never an unbounded fan-out."""
    return _env_int(_ENV_POST_FETCH_ENRICH_WORKERS, _POST_FETCH_ENRICH_WORKERS_DEFAULT)


def _post_fetch_enrich_wall_fraction() -> float:
    """WAVE-2 Fix A (Codex wave-2 P1a): the FRACTION of the REMAINING retrieval wall the
    parallel OpenAlex enrich pre-batch may consume, so the batch cannot burn the ENTIRE
    wall before the classify loop even starts.

    The pre-batch's collection is SYNCHRONOUS (it blocks in index order until every
    future resolves or the deadline passes). Handing it the FULL ``_retrieval_deadline``
    let a slow early future stall the whole collection to the wall — starving the very
    classify loop the fix was meant to protect: with rescue OFF the fetched-body tail is
    dropped at candidate 0, and with rescue ON every candidate falls into rules-only
    rescue. Reserving the remainder for classification closes that (mirrors
    :func:`_retrieval_w2_wall_fraction`, the identical W2 fix).

    Three outcomes (fail-safe parser identical to :func:`_retrieval_w2_wall_fraction`):
      * ``PG_POST_FETCH_ENRICH_WALL_FRACTION`` UNSET -> ``0.5`` (enrich gets at most half
        the remaining wall; classification keeps the other half).
      * a valid finite float in ``(0.0, 1.0]``       -> that value.
      * ANY set-but-invalid value                    -> ``1.0`` = the FULL retrieval
        deadline unchanged (the pre-P1a behaviour; OFF path is unaffected either way).

    Read at CALL time (LAW VI). Pure (env-only); unit-testable. Faithfulness-neutral:
    a straggler not collected inside the reserved slice is recorded as ``{}`` — the SAME
    empty result the serial per-candidate enrich returns on timeout (an unenriched row is
    disclosed/undated downstream, NEVER dropped — §-1.3)."""
    raw = os.getenv(_ENV_POST_FETCH_ENRICH_WALL_FRACTION)
    if raw is None:
        return 0.5
    try:
        frac = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(frac) or not (0.0 < frac <= 1.0):
        return 1.0
    return frac


def _wall_rescue_weight() -> float:
    """WAVE-2 Fix B (Codex wave-2 P1b): the rules-floor content-relevance WEIGHT a
    wall-rescued body is KEPT at (§-1.3 keep-at-floor, never drop).

    A body classified RULES-ONLY past the retrieval wall never had its content-relevance
    scored, so it must NOT carry the default full weight (1.0) — that would falsely rank
    it as fully relevant. It is instead kept at the deterministic rules floor (default
    ``_WALL_RESCUE_WEIGHT_DEFAULT`` = 0.25, matching the content-relevance demote floor):
    low but NON-zero, so the source still flows to composition at reduced weight and is
    NEVER dropped. Clamped to ``(0, 1]`` (a zero/negative/garbage override can never
    zero-drop a rescued source). Read at CALL time (LAW VI). Faithfulness-neutral — the
    frozen strict_verify / NLI / 4-role / provenance engine still re-checks the row."""
    raw = os.getenv(_ENV_WALL_RESCUE_WEIGHT, "").strip()
    if not raw:
        return _WALL_RESCUE_WEIGHT_DEFAULT
    try:
        w = float(raw)
    except (TypeError, ValueError):
        return _WALL_RESCUE_WEIGHT_DEFAULT
    if not math.isfinite(w) or not (0.0 < w <= 1.0):
        return _WALL_RESCUE_WEIGHT_DEFAULT
    return w


def _wall_classify_rescue_enabled() -> bool:
    """WAVE-2 Fix B master switch (default OFF). Unset => the retrieval-wall break
    in the post-fetch loop hands off exactly as before (BYTE-IDENTICAL). ON => at
    the wall break the loop keeps classifying the REMAINING already-fetched bodies
    RULES-ONLY (deterministic rules-floor tier — no enrich, no LLM, no network) and
    KEEPS them (§-1.3 keep-not-drop) so they feed the CRAG corrective reserve. LAW
    VI env-overridable; truthy 1/true/on/yes. Verification is NEVER relaxed."""
    return os.environ.get(_ENV_WALL_CLASSIFY_RESCUE, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _loop_budget_truncation_active(
    *, wall_rescue_mode: bool, now: float, loop_deadline: float
) -> bool:
    """WAVE-2 Fix B (Codex wave-2 P1): whether the LEGACY post-fetch loop-budget
    truncation is allowed to fire.

    The loop-budget branch can DROP already-fetched bodies (its default 'warn' policy
    breaks the loop and sets ``corpus_truncated``, which the Path-B gate rejects). Once
    ``PG_WALL_CLASSIFY_RESCUE`` has engaged rules-only rescue, that break must NOT fire:
    in rescue mode every remaining fetched body is classified RULES-ONLY and KEPT
    (§-1.3 keep-not-drop), and the rules-only path is cheap (no enrich / LLM / network),
    so the serial-grind the loop budget guards against does not apply. Returning False
    in rescue mode lets the loop keep classifying+keeping to the end instead of dropping
    the tail at the loop deadline.

    OFF / pre-rescue (``wall_rescue_mode`` False — the ONLY value when the flag is OFF)
    => byte-identical to the bare ``now > loop_deadline`` check. Pure; unit-testable."""
    if wall_rescue_mode:
        return False
    return now > loop_deadline


def _wall_rescue_armed_marker(*, enrich_parallel: bool) -> str:
    """WAVE-2 Fix B (Codex wave-2 P1): the anti-dark LIVENESS marker for
    ``PG_WALL_CLASSIFY_RESCUE``.

    Emitted at post-fetch loop SETUP whenever the rescue flag is ON — INDEPENDENT of
    whether the retrieval wall trips. The wall-hit "engaged" log alone is NOT proof the
    rescue path is wired: the parallel enrich pre-batch (Fix A) can keep the wall from
    ever tripping on an official run, so a run could set ``PG_WALL_CLASSIFY_RESCUE=1``
    (FORCE_ON + SLATE prove only the ENV is set) yet emit no rescue log at all — a DARK
    path. This armed marker fires on EVERY run the flag is ON, proving the flag->code
    path was reached and the rescue is live. Pure (string only); the ``[activation] ``
    prefix routes it into the forensic activation-capture buffer streamed to stdout.
    Faithfulness-neutral (it only discloses that the keep-not-drop rescue is armed)."""
    return f"[activation] wall_classify_rescue: armed enrich_parallel={enrich_parallel}"


def _openalex_date_filter_enabled() -> bool:
    """I-deepfix-001 Wave-3 (#1344): kill-switch for the additive date-scoped OpenAlex lane.

    Default OFF => the extra date-scoped ``openalex_search`` never fires and the OpenAlex path is
    byte-identical. The Gate-B slate quad-pins ``PG_OPENALEX_DATE_FILTER`` ON."""
    return os.getenv("PG_OPENALEX_DATE_FILTER", "0").strip().lower() in ("1", "true", "on", "yes")


def _openalex_full_iso(iso: str | None, *, ceiling: bool) -> str | None:
    """Normalize a ``UserConstraints`` ISO bound to a full OpenAlex ``YYYY-MM-DD`` date.

    ``UserConstraints.date_start_iso`` yields ``YYYY-MM-01`` / ``YYYY-01-01`` (already full) and
    ``date_end_iso`` yields ``YYYY-MM`` (month precision) or ``YYYY-12-31``. OpenAlex date filters
    need a full ``YYYY-MM-DD``; a month-precision CEILING is snapped to that month's LAST day
    (inclusive), a month-precision FLOOR to the first. Returns ``None`` on an empty/unparseable
    bound. Pure; no network (``calendar`` is stdlib)."""
    s = (iso or "").strip()
    if not s:
        return None
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return s  # already YYYY-MM-DD
        if len(parts) == 2:
            year, month = int(parts[0]), int(parts[1])
            if ceiling:
                import calendar
                last = calendar.monthrange(year, month)[1]
                return f"{year:04d}-{month:02d}-{last:02d}"
            return f"{year:04d}-{month:02d}-01"
        if len(parts) == 1:
            year = int(parts[0])
            return f"{year:04d}-12-31" if ceiling else f"{year:04d}-01-01"
    except (ValueError, IndexError):
        return None
    return None


def _openalex_date_window(research_question: str) -> tuple[str | None, str | None]:
    """I-deepfix-001 Wave-3 (#1344): extract the (from_date, to_date) OpenAlex publication window
    from the research question's stated date constraints, as full ISO ``YYYY-MM-DD`` bounds.

    Reuses the deterministic ``extract_constraints_regex`` (no network, no LLM) and normalizes its
    ``UserConstraints`` bounds. ``(None, None)`` when the question states no window — the caller then
    fires no extra lane. Best-effort: any exception yields ``(None, None)`` (fail-open — the base
    OpenAlex lane is unaffected)."""
    try:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (
            extract_constraints_regex,
        )
        uc = extract_constraints_regex(research_question or "")
        from_date = _openalex_full_iso(uc.date_start_iso(), ceiling=False)
        to_date = _openalex_full_iso(uc.date_end_iso(), ceiling=True)
        return from_date, to_date
    except Exception:
        return None, None


def _prefetch_openalex_enrich_parallel(
    candidates: list[Any],
    *,
    workers: int,
    deadline_monotonic: Optional[float] = None,
    enrich_fn: Optional[Any] = None,
) -> dict[int, dict[str, Any]]:
    """WAVE-2 Fix A: bounded-parallel pre-batch of the per-candidate OpenAlex enrich.

    Returns ``{i: enrich_dict}`` keyed by each candidate's position in
    ``candidates`` — ORDER-STABLE (``result[i]`` always corresponds to
    ``candidates[i]`` regardless of completion order), so the merge is identical to
    the serial loop's per-candidate enrich. The batch NEVER reorders ``candidates``
    and NEVER touches ``seen_urls`` (the caller's upstream first-seen-wins candidate
    ordering is preserved); it only READS ``cand.url`` / ``cand.title`` (immutable)
    and calls the SAME bounded enrich the serial path calls, so there is no race on
    shared candidate/dedup state. The only shared write is the module authority
    cache inside the enrich, whose per-call sqlite connection + top-level
    try/except make a lock-contended write fail-open to ``{}`` (never corruption);
    the one-time cache migration is warmed once here before fan-out.

    Each candidate's enrich is hard-bounded (``enrich_fn`` defaults to
    ``_bounded_openalex_enrich`` — a daemon-thread join-timeout abandon), so a
    wedged OpenAlex response can never hang the pool teardown. An overall
    ``deadline_monotonic`` (absolute ``time.monotonic()``) additionally caps the
    whole batch: a straggler not collected by the deadline is recorded as ``{}`` —
    the SAME empty result the serial per-candidate bound returns on timeout (§-1.3:
    an unenriched row is disclosed/undated downstream, NEVER dropped). Codex wave-2
    P0: once the deadline passes the batch STOPS waiting AND CANCELS every still-queued
    future so no further OpenAlex enrich starts during the classify phase — the batch
    is bounded by the WALL, not just by worker count. Already-running futures (at most
    ``max_workers``) cannot be cancelled but are each self-bounded by the per-call
    daemon join-timeout. Pure w.r.t. inputs; unit-testable with a 2-arg stub
    ``enrich_fn`` (no heavy models).
    """
    results: dict[int, dict[str, Any]] = {}
    n = len(candidates)
    if n == 0:
        return results
    _enrich = enrich_fn if enrich_fn is not None else _bounded_openalex_enrich
    # Warm the authority-cache migration ONCE on the main thread so the pool
    # workers never race the one-time `_ensure_authority_cache_migrated` global.
    try:
        _ensure_authority_cache_migrated()
    except Exception:  # noqa: BLE001 — cache warm is best-effort; enrich fails open
        pass
    from concurrent.futures import (  # noqa: E402
        ThreadPoolExecutor,
        TimeoutError as _FutureTimeout,
    )

    max_workers = max(1, min(int(workers), n))
    per_call_timeout = _env_float("PG_OPENALEX_ENRICH_DEADLINE", 45.0) + 5.0
    executor = ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="oa-enrich-batch",
    )
    # Declared BEFORE the try so the finally can cancel every submitted future even
    # if the submit loop raises partway (Codex wave-2 P0 — no leaked queued enrich).
    _future_by_idx: dict[int, Any] = {}
    try:
        for idx, cand in enumerate(candidates):
            _future_by_idx[idx] = executor.submit(
                _enrich, getattr(cand, "url", ""), getattr(cand, "title", ""),
            )
        # Codex wave-2 P0: once the RESERVED wall slice is spent the pre-batch must
        # stop consuming network/threads — it is bounded by the WALL DEADLINE, not
        # just by worker count. When the deadline passes we STOP waiting on the
        # remaining futures AND CANCEL each still-queued one so no further enrich
        # starts during the classify phase. Every index STILL gets a value ({} for an
        # un-collected straggler) — §-1.3 keep-not-drop: the merge never loses an
        # index, it only records the SAME fail-open {} the serial enrich returns on
        # timeout. (Running futures <= max_workers can't be cancelled but are each
        # self-bounded by the per-call daemon join-timeout.)
        _deadline_expired = False
        for idx in range(n):  # collect in INDEX order -> order-stable merge
            fut = _future_by_idx[idx]
            if _deadline_expired:
                fut.cancel()  # still-queued -> never runs; already-running -> no-op
                results[idx] = {}
                continue
            if deadline_monotonic is not None:
                _timeout = max(0.0, deadline_monotonic - time.monotonic())
            else:
                _timeout = per_call_timeout
            try:
                val = fut.result(timeout=_timeout)
            except _FutureTimeout:
                val = {}
            except Exception:  # noqa: BLE001 — mirror serial enrich's {}-on-error
                val = {}
            results[idx] = val if isinstance(val, dict) else {}
            # Past the reserved deadline: do NOT keep waiting on / letting the
            # remaining futures run — cancel them on the next iterations + finally.
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                _deadline_expired = True
    finally:
        # Cancel every still-pending future so a queued OpenAlex enrich cannot keep
        # firing after the reserved wall slice (Codex wave-2 P0). cancel_futures also
        # purges the pool's work queue; still-running workers are self-bounded by the
        # per-call daemon join-timeout, so teardown never blocks on a wedged enrich.
        for _f in _future_by_idx.values():
            _f.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _wall_rescue_classify_source(
    signals: ClassificationSignals,
    url: str,
    title: str,
    domain: str,
    *,
    content_relevance_weight: float,
    content_relevance_label: str,
) -> tuple[CorpusSource, ClassificationResult]:
    """WAVE-2 Fix B: classify an already-fetched body RULES-ONLY and KEEP it.

    Uses the DETERMINISTIC rules-floor classifier (``_classify_source_tier_rules``
    — no enrich, no LLM, no network) so the rescued body carries a FINAL tier (never
    a placeholder). ALWAYS returns a ``CorpusSource`` (never ``None`` / never a
    drop) even when the rules floor lands at UNKNOWN/T7 — §-1.3 keep-not-drop: a
    low-credibility source stays in the corpus at its honest weight, it is never
    filtered out. The genre stamp (``_m2_dt``) mirrors the deferred W5 path so the
    disclosure surface matches. Faithfulness-NEUTRAL: this only classifies+keeps;
    the frozen strict_verify / NLI / 4-role / provenance engine is untouched and
    still re-checks the row downstream. Pure; unit-testable (no heavy models)."""
    tier_result = _classify_source_tier_rules(signals)
    _m2_dt(tier_result, signals)
    src = CorpusSource(
        url=url,
        title=title,
        domain=domain,
        tier=tier_result.tier.value,
        tier_confidence=tier_result.confidence,
        tier_rule=tier_result.matched_rules[0] if tier_result.matched_rules else "",
        tier_reasons=list(tier_result.reasons),
        content_relevance_weight=content_relevance_weight,
        content_relevance_label=content_relevance_label,
    )
    return src, tier_result


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


# I-extract-001 Layer-A (data-picked HTML main-content extractor): flag-gated
# trafilatura profile at the post-fetch HTML->text seam (_strip_html). The
# I-extract-001 Layer-A leaderboard measured trafilatura's favor_precision profile
# trimming page furniture while holding body-anchor recall at 1.000 (no body loss).
# The flag is OPT-IN: the default profile ("default" / unset) preserves the prior
# trafilatura behavior so no existing run changes silently. Faithfulness-neutral:
# it only changes WHICH text trafilatura returns; the readability-lxml -> regex
# fallback chain and the downstream strict_verify span-grounding are untouched.
PG_HTML_EXTRACTOR_ENV = "PG_HTML_EXTRACTOR"
_HTML_EXTRACTOR_DEFAULT = "default"
_HTML_EXTRACTOR_TRAFILATURA_PRECISION = "trafilatura_precision"


def _trafilatura_extract_kwargs() -> dict[str, Any]:
    """Resolve the trafilatura.extract kwargs for the configured PG_HTML_EXTRACTOR
    profile. Read at CALL time (not import) so deploy-slate / test overrides apply
    without re-import. Returns {} for the default profile (current behavior) and
    {"favor_precision": True} for the data-picked precision profile. An UNKNOWN
    value fails LOUD (warns + uses the default profile) rather than silently
    no-op'ing a typo'd flag into the wrong extractor."""
    mode = os.getenv(PG_HTML_EXTRACTOR_ENV, _HTML_EXTRACTOR_DEFAULT).strip().lower()
    if mode in ("", _HTML_EXTRACTOR_DEFAULT):
        return {}
    if mode == _HTML_EXTRACTOR_TRAFILATURA_PRECISION:
        return {"favor_precision": True}
    logger.warning(
        "[live_retriever] unknown %s=%r — expected %r or %r; using trafilatura "
        "defaults",
        PG_HTML_EXTRACTOR_ENV, mode, _HTML_EXTRACTOR_DEFAULT,
        _HTML_EXTRACTOR_TRAFILATURA_PRECISION,
    )
    return {}


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
        # I-extract-001 Layer-A: select the trafilatura profile via PG_HTML_EXTRACTOR
        # (default = current behavior; "trafilatura_precision" = favor_precision=True).
        extract_kwargs = _trafilatura_extract_kwargs()
        extracted = safe_trafilatura_extract(html, **extract_kwargs) or ""
        if extracted:
            base = extracted
            if extract_kwargs:
                # Behavioral canary: confirm the precision profile actually
                # produced the extracted base text (the favor_precision kwarg
                # reached trafilatura and did NOT silently fall through to the
                # readability/regex tiers). Only fires when the opt-in flag is
                # set, so default runs stay quiet.
                logger.info(
                    "[live_retriever] PG_HTML_EXTRACTOR=%s active — trafilatura "
                    "favor_precision produced %d chars",
                    _HTML_EXTRACTOR_TRAFILATURA_PRECISION, len(base),
                )
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


def _apply_min_body_stub_gate(
    *,
    content: str,
    ok: bool,
    url: str,
    method: str,
    max_chars: int,
    extracted_title: str,
    body_type: str,
    jsonld: str,
    doi_hint: str = "",
    pmid_hint: str = "",
) -> tuple[str, bool, str, str, str]:
    """FIX #2 (I-deepfix-001): apply the SAME F14 min-body stub gate that the
    PRIMARY ``_fetch_content`` branch applies (the 3014-3073 block) to the
    naive-httpx FALLBACK return path, which previously returned ``ok=True`` for a
    sub-floor body (an 11-char "Just a moment..." Cloudflare/paywall shell) — a
    dead fetch masquerading as a good source, exactly what F14 was built to stop,
    but only on the fallback path.

    Semantics MIRROR the primary branch: when the body is below the configured
    floor AND a DOI is resolvable, give the OA resolver a chance to UPGRADE the
    shell to full text; otherwise LABEL it ``stub`` (ok=False) — the content is
    STILL returned (a down-weight consumer can inspect it), never DROPPED (§-1.3
    label-not-drop). DEFAULT floor 0 (``PG_FETCH_MIN_BODY_CHARS`` unset) =>
    returns the tuple UNCHANGED => byte-identical to today; the gate fires only on
    the cert sweep (floor=1000). LAW VI: reuses only existing env knobs. The
    faithfulness engine (strict_verify / NLI / 4-role / span-grounding) is
    downstream and untouched — this is a fetch-layer ok-flag + telemetry change.

    Unlike the primary branch, this helper records ONLY the keyed ``_m45`` reason
    (no ``_trace_tool``): the naive path is reached via ``_fallback_naive_fetch``,
    which already emits the SINGLE per-fetch ``ok``/``fail`` trace for this call —
    mirroring the existing empty-extract precedent (the ``_m45``-only record at
    the ``fetched_200_but_empty_extract`` site below).
    """
    if not ok:
        return content, ok, extracted_title, body_type, jsonld
    _min_body = _fetch_min_body_chars()
    if _min_body <= 0 or len(content) >= _min_body:
        return content, ok, extracted_title, body_type, jsonld
    # Below the floor — give the OA resolver a chance to upgrade the short shell.
    if _oa_resolver_enabled():
        _oa_doi = (doi_hint or "").strip() or _extract_doi_from_url(url)
        if _oa_doi:
            # Codex iter1 P1-3: use the BOUNDED OA resolver here. This gate runs
            # on the naive-httpx FALLBACK return, which is reached via
            # `_fallback_naive_fetch` from (among others) the AccessBypass TIMEOUT
            # path — where FIX-3-piece-2 already attempted a bounded OA. A bare
            # synchronous `_try_oa_resolution` here would be a SECOND, UNBOUNDED OA
            # that can re-route the AccessBypass browser cascade and re-open the
            # very timeout storm we just escaped. `_try_oa_resolution_bounded`
            # caps it at PG_OA_RECOVERY_DEADLINE (daemon+join) and hands a wedged
            # thread to the drain registry. Recovery still only ADDS content
            # (§-1.3: never drops).
            _oa_content = _try_oa_resolution_bounded(
                url=url,
                extracted_doi=_oa_doi,
                pmid=(pmid_hint or "").strip(),
                max_chars=max_chars,
            )
            if _oa_content and len(_oa_content) >= _min_body:
                logger.info(
                    "[live_retriever] fetch_oa_upgrade %s (naive-path "
                    "short_body=%d -> oa_body=%d) — short shell upgraded to "
                    "full text via OA resolver",
                    url[:80], len(content), len(_oa_content),
                )
                _m45_record_fetch_telemetry(url, "oa_resolver", "")
                return _oa_content, True, extracted_title, body_type, jsonld
    # Still short after the OA attempt — STUB, not ok. KEEP content (§-1.3).
    _is_paywall_pub = _is_paywall_publisher_url(url)
    if _is_paywall_pub and not os.getenv("ZYTE_API_KEY"):
        logger.warning(
            "[live_retriever] PAYWALL_STUB_NO_ZYTE %s (method=%s chars=%d < "
            "floor=%d) — naive-fallback paywalled-publisher short shell and "
            "ZYTE_API_KEY is UNSET; the Zyte paid fallback was a silent no-op.",
            url[:80], method, len(content), _min_body,
        )
    else:
        logger.warning(
            "[live_retriever] PAYWALL_STUB %s (method=%s chars=%d < floor=%d, "
            "paywall_publisher=%s) — naive-fallback short body treated as a "
            "stub, NOT ok (fail-loud).",
            url[:80], method, len(content), _min_body, _is_paywall_pub,
        )
    _m45_record_fetch_telemetry(url, method, "paywall_stub_short_body")
    return content, False, extracted_title, body_type, jsonld


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
        # FIX #2 (I-deepfix-001): apply the SAME F14 min-body stub gate the
        # PRIMARY branch applies. Sub-floor fallback bodies (paywall shells,
        # 'Just a moment...' interstitials) are LABELED stub/ok=False (content
        # KEPT — §-1.3) instead of admitted as ok=True. DEFAULT floor 0 (unset)
        # => returns the tuple UNCHANGED => byte-identical.
        return _apply_min_body_stub_gate(
            content=content,
            ok=bool(content),
            url=url,
            method="httpx_naive",
            max_chars=max_chars,
            extracted_title=extracted_title,
            body_type=body_type,
            jsonld=jsonld,
        )
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
            'thin_content', 'paywall_shell', 'fetch_shell'
            ('fetch_shell' = clean_fetch_body reported the whole body is a
            boilerplate/interstitial shell — not extractable, not cited)
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
        # I-beatboth-010 (#1288) FIX-A: strip Jina/Crawl4AI reader chrome (Title:/
        # URL Source:/Published Time:/Number of Pages:/Markdown Content: preamble)
        # BEFORE the provenance quote is built, so the cited direct_quote is clean
        # at source. Input hygiene only — faithfulness gates untouched.
        from src.tools.access_bypass import clean_fetch_body
        _cf = clean_fetch_body(content)
        content = _cf.cleaned_text
        # I-beatboth-011 idx49 (#1289): when clean_fetch_body reports the WHOLE
        # cleaned body is a fetch SHELL (boilerplate / soft-404 / Cloudflare or
        # "security check required" interstitial that leaked through as cited
        # evidence on drb_72), route it to the EXISTING not-extractable failure
        # branch instead of building a cited quote from the junk — mirroring the
        # frame_fetcher METADATA_ONLY gap path (frame_fetcher.py:1098-1105). This
        # consumes the EXISTING `shell_reason` signal and the EXISTING early-return
        # failure path; it adds NO new drop/cap/threshold. The `empty_after_clean`
        # case is already caught by the `len(quote) < 100` gate below; the leak this
        # closes is a >100-char `boilerplate_or_error_stub` interstitial.
        if _cf.shell_reason:
            logger.info(
                "[refetch_for_extraction] fetch-shell rejected url=%s reason=%s "
                "len=%d → not-extractable (not cited as evidence)",
                (url or "")[:200], _cf.shell_reason, len(content),
            )
            diagnostics["failure_mode"] = "fetch_shell"
            return "", diagnostics  # failure (settled in finally)
        quote = _build_provenance_quote(
            content, head_chars=min(_PROVENANCE_HEAD_CHARS_CAP, max_chars),
            window_chars=500, max_total_chars=max_chars,
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


# FIX-3 PIECE 2 (I-deepfix-001): bounded OA recovery for the AccessBypass TIMEOUT
# path. Default deadline (seconds) for the whole recovery attempt. Named constant
# (LAW VI); env-overridable via PG_OA_RECOVERY_DEADLINE. A malformed/<=0 value
# falls back to the default so a bad knob can never UNBOUND the recovery (which
# would re-open the timeout storm the abandon path exists to escape).
_OA_RECOVERY_DEADLINE_DEFAULT = 20.0
PG_OA_RECOVERY_DEADLINE_ENV = "PG_OA_RECOVERY_DEADLINE"


def _oa_recovery_deadline_seconds() -> float:
    """Resolve the timeout-path OA-recovery wall-clock budget (seconds) from
    PG_OA_RECOVERY_DEADLINE, else `_OA_RECOVERY_DEADLINE_DEFAULT`."""
    raw = os.getenv(PG_OA_RECOVERY_DEADLINE_ENV)
    if raw is not None and raw.strip():
        try:
            parsed = float(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return _OA_RECOVERY_DEADLINE_DEFAULT


def _try_oa_resolution_bounded(
    url: str,
    extracted_doi: str = "",
    pmid: str = "",
    max_chars: int = DEFAULT_CONTENT_MAX_CHARS,
) -> str:
    """FIX-3 piece 2: run :func:`_try_oa_resolution` under a HARD wall-clock so it
    can be called on the AccessBypass timeout path WITHOUT re-opening the storm.

    `_try_oa_resolution` is NOT purely fast-API: its Unpaywall step calls
    `_fetch_oa_url_via_bypass`, which routes `frame_fetcher._fetch_url_pattern`
    (the AccessBypass browser cascade). A bare synchronous call could therefore
    stall the very path whose purpose is to NOT stall. So run it in a daemon
    thread and `join(PG_OA_RECOVERY_DEADLINE)`; on timeout REGISTER that thread
    with the same abandoned-bypass-worker registry the main worker uses (so the
    end-of-run bounded drain reclaims it / the live gauge counts it) and return
    "" so the caller falls through to the naive return unchanged (fail-OPEN).

    Returns recovered content (str) on a hit within budget, else "".
    """
    if not _oa_resolver_enabled():
        return ""
    _holder: dict[str, str] = {}

    def _runner() -> None:
        try:
            _holder["content"] = _try_oa_resolution(
                url=url, extracted_doi=extracted_doi, pmid=pmid, max_chars=max_chars,
            )
        except Exception:  # noqa: BLE001 — fail-OPEN; never raise out of the thread
            _holder["content"] = ""
        finally:
            # Symmetry with the main bypass worker: if this thread was abandoned
            # (registered on timeout) but then finished, drop it from the live
            # registry. A no-op when it was never registered. The drain/count
            # `is_alive()` filter also prunes it, so this is belt-and-suspenders.
            try:
                from src.tools.access_bypass import (
                    deregister_abandoned_bypass_worker,
                )
                deregister_abandoned_bypass_worker(threading.current_thread())
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

    _t = threading.Thread(target=_runner, daemon=True)
    _t.start()
    _t.join(timeout=_oa_recovery_deadline_seconds())
    if _t.is_alive():
        # Recovery exceeded its budget (the bypass cascade wedged). Hand the
        # thread to the SAME abandoned-worker registry so it is drained/counted
        # like an abandoned main worker; do NOT block on it (preserve non-hang).
        try:
            from src.tools.access_bypass import register_abandoned_bypass_worker
            register_abandoned_bypass_worker(_t)
        except Exception:  # noqa: BLE001 — best-effort; never break retrieval
            pass
        return ""
    return _holder.get("content", "") or ""


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


# I-deepfix-001 B2 (#1346): per-run ACTIVE blocked-reference deny-list. `run_live_retrieval`
# sets this once at the start of each run from its `research_question`; `_fetch_content`
# reads it to SKIP (and record) an operator-PROHIBITED URL BEFORE the HTTP call — saving
# spend and preventing tier laundering of a blocked mirror. A module global (vs threading
# the registry through every fetch call-site) matches this module's per-run reset pattern
# (`reset_refetch_cache`); it is overwritten fresh at the top of every run so a sequential
# per-question sweep never leaks a prior question's deny-list. The kill-switch / empty-
# registry path makes the read a no-op (byte-identical to pre-B2). Faithfulness-neutral.
_ACTIVE_BLOCKED_REGISTRY: "Any" = None


def set_active_blocked_registry(registry: "Any") -> None:
    """Install the per-run blocked-reference deny-list read by ``_fetch_content`` (B2)."""
    global _ACTIVE_BLOCKED_REGISTRY
    _ACTIVE_BLOCKED_REGISTRY = registry


def get_active_blocked_registry() -> "Any":
    """The per-run blocked-reference deny-list, or ``None`` when none is installed (B2)."""
    return _ACTIVE_BLOCKED_REGISTRY


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
    # I-deepfix-001 B2 (#1346): operator do-not-view enforcement at the FETCH seam. If this
    # URL (or a DOI/PII embedded in it, or the carried doi_hint) is on the per-run blocked-
    # reference deny-list, SKIP the HTTP call entirely — saving spend and preventing the
    # blocked mirror from being fetched, tiered, and laundered into the corpus. This is the
    # ONE legitimate hard drop (§-1.3, an explicit operator prohibition); it is fail-LOUD
    # (recorded to the fetch telemetry + logged, never a silent drop) and fail-OPEN (any
    # registry error is swallowed so it can NEVER break retrieval).
    _blocked_registry = _ACTIVE_BLOCKED_REGISTRY
    if _blocked_registry is not None:
        try:
            _is_blocked, _block_reason = _blocked_registry.is_blocked(
                url=url, doi=doi_hint
            )
        except Exception:  # noqa: BLE001 — fail-OPEN: deny-list error never breaks fetch
            _is_blocked, _block_reason = False, ""
        if _is_blocked:
            logger.info(
                "[live_retriever] B2 blocked-reference SKIP (no fetch) %s reason=%s",
                url[:120], _block_reason,
            )
            _m45_record_fetch_telemetry(
                url, "blocked_reference", f"blocked_reference_denylist:{_block_reason}"
            )
            return ("", False, "", "blocked_reference", "")
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
        deregister_abandoned_bypass_worker,
        polaris_asyncio_run,
        record_bypass_leaked_worker,
        register_abandoned_bypass_worker,
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
            # FIX-3 piece 1 (I-deepfix-001): self-deregister from the LIVE
            # abandoned-worker registry. If the outer join abandoned this worker
            # (registered it on the timeout path) but the worker then finished
            # cooperatively, drop it out of the live gauge so it is not counted
            # as a residual leak. A no-op when this worker was never abandoned.
            deregister_abandoned_bypass_worker(threading.current_thread())

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
        # FIX-3 piece 1 (I-deepfix-001): register the abandoned worker in the
        # LIVE registry so the end-of-run bounded drain can attempt to reclaim it
        # and `bypass_live_leaked_count()` reports whether it is still alive
        # (distinct from the cumulative gauge recorded just below). The worker
        # self-deregisters in its own finally if it later finishes cooperatively;
        # the `is_alive()` filter in the drain/count prunes the dead-from-race
        # case. The existing BoundedSemaphore stays the concurrency bound — this
        # adds reclamation + an honest live gauge, no second bound.
        register_abandoned_bypass_worker(worker)
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
        # FIX-3 piece 2 (I-deepfix-001): DOI recovery on the previously-DARK
        # TIMEOUT path. The existing stub-path OA resolver (below, ~L3129) is
        # UNREACHABLE from here — this return fires first — so a 90s-timed-out
        # academic doi.org URL never got an Unpaywall/EFetch attempt and went
        # dark. When the resolver is enabled and a DOI resolves (carried hint or
        # embedded in the URL), try the OA recovery BOUNDED by
        # PG_OA_RECOVERY_DEADLINE (the helper runs it in a daemon thread + joins
        # within budget so it CANNOT re-open the timeout storm). On a hit return
        # the recovered full text with ok=True; on miss/error fall through to the
        # naive return unchanged (fail-OPEN). Gated on _oa_resolver_enabled()
        # (default ON, like the stub-path OA at L3129) — when the resolver is OFF
        # this branch is byte-identical to the prior timeout return.
        if _oa_resolver_enabled():
            _to_doi = (doi_hint or "").strip() or _extract_doi_from_url(url)
            if _to_doi:
                _oa_content = _try_oa_resolution_bounded(
                    url=url,
                    extracted_doi=_to_doi,
                    pmid=(pmid_hint or "").strip(),
                    max_chars=max_chars,
                )
                if _oa_content:
                    logger.info(
                        "[live_retriever] fetch_oa_timeout_recovery %s "
                        "(doi=%s chars=%d) — recovered via OA resolver on the "
                        "AccessBypass timeout path (was previously dark)",
                        url[:80], _to_doi, len(_oa_content),
                    )
                    _m45_record_fetch_telemetry(
                        url, "oa_resolver", "timeout_recovery"
                    )
                    _trace_tool(
                        "fetch_content", target=url, status="ok",
                        latency_ms=(time.time() - _t0) * 1000.0,
                        backend_used="oa_resolver",
                        bytes_received=len(_oa_content),
                        content_length=len(_oa_content),
                    )
                    return _oa_content, True, "", "", ""
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
    # I-deepfix-001 wave-2 4IR (#1344): strip fetch chrome (Jina/Crawl4AI reader
    # preamble + Cookiebot/Usercentrics consent-manager taxonomy) BEFORE the char
    # cap — the same extract→clean→cap order already used at
    # frame_fetcher.py:1216-1234. Gated DEFAULT-ON by PG_FETCH_COOKIE_CHROME_STRIP;
    # flag OFF ("0") is byte-identical to the prior _strip_html(...)[:max_chars].
    # Input hygiene only — strict_verify / NLI / 4-role / span-grounding untouched.
    _stripped_body = _strip_html(result.content)
    if os.getenv("PG_FETCH_COOKIE_CHROME_STRIP", "1") != "0":
        from src.tools.access_bypass import clean_fetch_body
        _stripped_body = clean_fetch_body(_stripped_body).cleaned_text
    content = _stripped_body[:max_chars]
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

# I-wire-014 (#1327): the provenance-quote HEAD cap. The A15 resume re-fetch
# (resume_refetch.py) repopulates a row's cited ``direct_quote`` with the head of
# the freshly-fetched body via ``_build_provenance_quote``; with a hard
# ``content[:CAP]`` slice that head ended MID-WORD (proven: 80/96 spans in
# iwire014_replay2 landed at 1495-1505 chars ending alphanumeric → rendered
# fragments like "usand workers"). The cap value is UNCHANGED — only the slice is
# now snapped to the last word boundary at or before the cap (see
# ``_snap_end_to_word_boundary``). One source of truth for the default + both call
# sites (LAW VI: a named constant, not a magic number).
_PROVENANCE_HEAD_CHARS_CAP = 1500


def _is_quote_word_char(ch: str) -> bool:
    """A word-constituent char for span-boundary snapping: a letter/digit/underscore.

    Mirrors ``provenance_generator._is_word_char`` (kept local to avoid a
    retrieval→generator import). ``str.isalnum()`` is Unicode-aware, so
    multilingual prose snaps on its own real word boundaries.
    """
    return ch.isalnum() or ch == "_"


def _snap_end_to_word_boundary(text: str, end: int) -> int:
    """Snap a span END offset back to the tail of the last WHOLE word at or before
    ``end``, so a truncated span NEVER ends mid-word (never "...thou" of "thousand").

    Pure + deterministic. Only moves ``end`` when the slice would cut strictly
    INSIDE a word (the char at ``end-1`` AND the char at ``end`` are both word
    chars); an ``end`` already at whitespace/punctuation, at/past ``len(text)``, or
    at the document tail is returned unchanged. It only NARROWS the span rightward
    (end can decrease, never increase), so ``text[:end]`` stays a verbatim PREFIX of
    ``text`` and the FROZEN strict_verify (numeric / content-word grounding) is
    untouched — a span shorter by a few chars but word-complete still grounds.

    To bound worst-case (a single token longer than the snap window — e.g. a long
    URL or DNA string), if walking back to a word boundary would discard more than
    ``_QUOTE_SNAP_MAX_BACKTRACK`` chars the original ``end`` is kept (a mid-token
    cut is preferable to dropping a whole giant token from the cited span).
    """
    n = len(text)
    if end >= n or end <= 0:
        return max(0, min(end, n))
    # Not cutting inside a word (boundary already at end) → unchanged.
    if not (_is_quote_word_char(text[end - 1]) and _is_quote_word_char(text[end])):
        return end
    i = end
    floor = end - _QUOTE_SNAP_MAX_BACKTRACK
    while i > 0 and i > floor and _is_quote_word_char(text[i - 1]):
        i -= 1
    # If we hit the backtrack floor without finding a boundary, the token is huge:
    # keep the original cut rather than ejecting the whole token.
    if i <= floor and i > 0 and _is_quote_word_char(text[i - 1]):
        return end
    return i


# Max chars ``_snap_end_to_word_boundary`` will walk back to find a word boundary.
# A window is the decimal ± 250 chars (window_chars//2 each side), so snapping the
# end back by ≤ this many chars never ejects the centered decimal; faithfulness
# (``_find_span_for_decimal``) is unaffected. A token longer than this is treated as
# pathological and the hard cut is kept (see helper docstring).
_QUOTE_SNAP_MAX_BACKTRACK = 64


def _snap_start_to_quote_word_boundary(text: str, start: int) -> int:
    """Snap a window START offset back to the head of the word it lands inside, so a
    window chunk BEGINS at a whole word (never "...usand workers..." after a "[...]").

    Same contract as ``_snap_end_to_word_boundary`` but moves leftward: it only
    WIDENS the window start (start can decrease, never increase), keeping
    ``0 <= start`` and preserving the centered decimal. Bounded by the same
    backtrack window so a giant token never blows the chunk up.
    """
    if start <= 0 or start >= len(text):
        return max(0, min(start, len(text)))
    if not (_is_quote_word_char(text[start - 1]) and _is_quote_word_char(text[start])):
        return start
    i = start
    floor = start - _QUOTE_SNAP_MAX_BACKTRACK
    while i > 0 and i > floor and _is_quote_word_char(text[i - 1]):
        i -= 1
    if i <= floor and i > 0 and _is_quote_word_char(text[i - 1]):
        return start
    return i


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


def _recovered_content_error_class(text: str) -> str:
    """I-deepfix-001 (#1344) F4: classify a B02/B04-RECOVERED body as a
    registry/error/block page, returning a short class token (empty = real
    content, ADOPT it).

    The forced-Zyte degraded re-fetch only measured LENGTH (``is_content_starved``)
    before adopting a recovered body as upgraded full text — so a ~821-char doi.org
    "DOI Not Found" registry page (real English prose, well above the starvation
    floor) was adopted unchanged and cited (drb_72 ev_057). This delegates to the
    three EXISTING shell screens — the new registry-error screen, the error-shell
    text screen, and the block-page classifier — so an error / registry / block page
    is NOT adopted and the row instead keeps the existing degraded disposition (a
    disclosed gap, NOT deleted). FAIL-OPEN: if the screen import/scan raises, return
    "" with a LOUD warning so a transient import error never silently rejects a real
    body. §-1.3: a registry "not found" page is never a corroborator — refusing to
    adopt a fetch FAILURE as grounding is not a hard-drop. Faithfulness engine
    untouched."""
    if not text:
        return ""
    try:
        from src.tools.access_bypass import (
            classify_block_page,
            is_error_shell_text,
            is_registry_error_page,
            registry_error_guard_enabled,
        )
        # I-deepfix-002 (#1363): the WHOLE screen is behind the kill-switch — OFF
        # restores the legacy length-only adoption path byte-identically (no
        # error-shell / block-page rejection runs when PG_REGISTRY_ERROR_GUARD=0).
        if not registry_error_guard_enabled():
            return ""
        if is_registry_error_page(text):
            return "doi_registry_error"
        if is_error_shell_text(text):
            return "error_shell"
        klass = classify_block_page(text)
        if klass:
            return f"block_page:{klass}"
    except Exception as exc:  # FAIL-OPEN — never silently reject a real recovered body.
        logger.warning(
            "[live_retriever] F4 recovered-error screen raised (fail-open, "
            "adopting the recovered body): %s", str(exc)[:200],
        )
        return ""
    return ""


def _build_provenance_quote(
    content: str,
    head_chars: int = _PROVENANCE_HEAD_CHARS_CAP,
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
    # I-wire-013 (#1327) TRUNCATION-AT-SOURCE: repair PDF/HTML line-wrap hyphens
    # ("patent-\ning" -> "patenting") on the FULL body BEFORE any offset is taken,
    # so the persisted, cited direct_quote — and every [#ev:id:start-end] offset
    # the generator later resolves against it — is computed on the de-hyphenated
    # text. Newlines survive clean_fetch_body (it collapses only [ \t]{2,}), so the
    # line-wrap break is still present here. Input hygiene only; a legitimate
    # intra-word hyphen ("co-author", "GLP-1") and multilingual prose are preserved
    # byte-for-byte. The faithfulness engine (strict_verify / NLI / span-grounding)
    # is untouched.
    from src.tools.access_bypass import dehyphenate_line_wraps  # noqa: PLC0415
    content = dehyphenate_line_wraps(content)
    if len(content) <= head_chars:
        return content
    # I-wire-014 (#1327): snap the head cut back to the last word boundary at/before
    # ``head_chars`` so the stored span NEVER ends mid-word ("usand workers"). The
    # integer ``head_chars`` cap below (the ``e > head_chars`` window filter) is
    # unchanged; only the emitted head STRING is trimmed to a whole word. ``head``
    # stays a verbatim prefix of the de-hyphenated content (faithfulness-neutral).
    head = content[:_snap_end_to_word_boundary(content, head_chars)]

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
        # I-wire-014 (#1327): snap each decimal-window's START forward and END back
        # to whole-word boundaries, so a chunk neither BEGINS mid-word right after a
        # "[...]" nor ENDS mid-word — and the LAST chunk's end IS the whole quote's
        # end, so this is what guarantees the joined direct_quote never ends mid-word.
        # The decimal is centered ~250 chars inside the window (>> the ≤64-char snap
        # backtrack), so the centered decimal is never ejected (faithfulness-neutral);
        # each chunk stays a verbatim substring of the de-hyphenated content.
        s_snapped = _snap_start_to_quote_word_boundary(content, s)
        e_snapped = _snap_end_to_word_boundary(content, e)
        chunk = content[s_snapped:e_snapped]
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
# B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-ORDER + fetch-BUDGET
# (§-1.3 DEMOTE-NOT-DROP as of I-deepfix-001 D3 — the floor ORDERS, never filters)
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
# THE FIX (surgical, §-1.3 WEIGHT-and-CONSOLIDATE / DEMOTE-NOT-DROP): replace the
# COUNT cut with a relevance ORDERING by REUSING B1's semantic relevance scorer
# WHOLESALE — `evidence_selector._semantic_relevance_scores(research_question,
# sub_queries, evidence_rows)`. B4 does NOT re-implement the scoring loop: it shapes
# its pre-fetch candidates into the row-dicts B1's `_row_embed_text` reads, calls
# B1's scorer ONCE, and uses B1's IDENTICAL `score >= floor` predicate — but as of
# I-deepfix-001 D3 that predicate ORDERS + DISCLOSES, it is NOT a hard cut: above-
# floor candidates rank first, below-floor candidates are DEMOTED to the tail (NOT
# dropped) and survive to the fetch budget. One scorer, one relevance story across
# B1+B4 — the scorer contract CANNOT drift because there is only one implementation
# (Codex B4 iter-2 P1). The `fetch_cap` is then purely a COST budget on how far down
# the demote-ordered list we actually fetch — and the beyond-budget tail (above-floor
# relevant + below-floor demoted) is RECORDED (counts + reason + scores) instead of
# silently discarded. Each fetched candidate's relevance score is carried FORWARD as
# a weight onto its evidence row.
#
# B1's scorer returns ``None`` when the embedder is unavailable / scoring fails /
# there is no usable anchor — and B4 falls back LOUDLY to the legacy lexical
# `_rerank_and_reserve` on that ``None`` (LAW II: no silent degrade, never a silent
# keep-all). That ``None`` IS the shared infra-failure signal: B4 no longer
# hand-rolls a self-similarity canary (deleted in iter-3) — the canary would have
# been a B4-private divergence from B1's contract, the exact drift Codex flagged.
# FAIL-OPEN (I-deepfix-001, Codex wave-1 P0): `prefetch_offtopic_filter._similarity_scores`
# now SIGNALS its three internal infra failures (no embedder interface / zero-norm
# query / encode exception) by returning ``None`` instead of all-zeros. B1's
# `_semantic_relevance_scores` propagates that as ``None`` when EVERY anchor fails,
# so B4 here falls back LOUDLY to the legacy lexical `_rerank_and_reserve` (keeps the
# candidates) on a scorer/embedder failure — it NEVER mass-drops the corpus on an
# embedder hiccup. §-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3): a genuinely empty/text-
# less SNIPPET still scores a real 0.0, but it is now DEMOTED to the tail (kept,
# fetched-to-know if the budget reaches it), NOT dropped — the only hard drop is the
# downstream faithfulness engine. This is distinct from an infra failure (``None``).
#
# CREDIBILITY/TIER IS NEVER A DROP HERE — and as of I-deepfix-001 D3 (§-1.3
# DEMOTE-NOT-DROP) the relevance floor is no longer a DROP either: it ORDERS (above-
# floor first, below-floor demoted to the tail) and the fetch BUDGET is the only
# bound. The faithfulness engine (strict_verify / 4-role D8 / provenance) lives in
# the generator/evaluator and is UNTOUCHED: this lane only changes the pre-fetch
# candidate ORDER + which fill the budget, adds an additive weight + telemetry.
#
# GATING: `PG_RETRIEVAL_RELEVANCE_GATE` (default ON). OFF => the legacy
# `_rerank_and_reserve` count-cut runs byte-identically (the embedder is never
# even imported — preserving `test_no_embedder_model_loaded`). ON + embedder
# unavailable => LOUD fallback to the legacy lexical path (LAW II: no silent
# degrade, never a silent keep-all).

# B4 relevance floor — ONE relevance story across B1+B4 (Codex iter-1 P1.1).
# The threshold is NOT a B4-private constant; it is B1's `PG_RELEVANCE_FLOOR`
# (default 0.30, `evidence_selector._DEFAULT_RELEVANCE_FLOOR`), parsed by B1's
# `evidence_selector.parse_relevance_floor`. B4 and B1 use the IDENTICAL floor
# against the IDENTICAL [0,1]-clamped semantic cosine. §-1.3 DEMOTE-NOT-DROP
# (I-deepfix-001 D3): the floor is an ORDERING + disclosure boundary, NOT a hard cut.
# A cosine below this floor against EVERY anchor (question + each sub-query) marks a
# candidate as below-floor — it is DEMOTED to the tail of the cosine-ordered list,
# NOT removed, and survives to the fetch budget (fetched if the budget reaches it).
# The floor is consumed only on the B4 ON path (PG_RETRIEVAL_RELEVANCE_GATE=1); OFF
# => the legacy count-cut runs byte-identically and the floor is never even read.
# `parse_relevance_floor` is imported lazily inside `_relevance_gate_threshold` so
# the OFF path never imports evidence_selector.

def _relevance_gate_enabled() -> bool:
    """Kill-switch `PG_RETRIEVAL_RELEVANCE_GATE`.

    DEFAULT ON (I-deepfix-001 B1 keystone, 2026-06-28): the pre-fetch relevance
    ORDER replaces the blind `_rerank_and_reserve` COUNT-cut that silently cut
    on-topic candidates beyond the fetch budget. §-1.3 DEMOTE-NOT-DROP (D3,
    2026-06-29): the floor orders (above-floor first, below-floor demoted to the
    tail) but never hard-drops; the fetch BUDGET is the only bound, and the whole
    unfetched tail is RECORDED (RelevanceGateResult unfetched_relevant_tail +
    demoted_tail), never lost. Set `PG_RETRIEVAL_RELEVANCE_GATE=0` (or off/false/no)
    to revert to the byte-identical legacy count-cut (the semantic embedder is then
    never imported, preserving `test_no_embedder_model_loaded` on the OFF path)."""
    raw = os.environ.get("PG_RETRIEVAL_RELEVANCE_GATE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "disabled", "")


def _relevance_gate_threshold() -> float:
    """Relevance floor — B1's `PG_RELEVANCE_FLOOR` (default 0.30), parsed by B1's
    `evidence_selector.parse_relevance_floor` so B1 and B4 share ONE floor and ONE
    relevance story (Codex iter-1 P1.1). §-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3): a
    candidate whose MAX cosine over {research_question} ∪ {sub-queries} is below this
    floor is below-floor and DEMOTED to the tail of the cosine-ordered list — NOT
    dropped; the fetch BUDGET decides whether it is reached. The comparison is the
    IDENTICAL `score >= floor` on the IDENTICAL [0,1]-clamped cosine that B1 applies
    at `_relevance_floor_selection` (`item[1] >= relevance_floor`) — used here for
    ORDERING + disclosure, not as a hard cut.

    FAIL LOUD on a garbage / out-of-range `PG_RELEVANCE_FLOOR`: `parse_relevance_floor`
    raises `ValueError` (range (0.0, 1.0]) — identical to B1's behaviour — so a
    misconfigured floor can never silently pass an unbounded, off-topic pool. The
    import is lazy so the OFF path never imports evidence_selector."""
    from src.polaris_graph.retrieval.evidence_selector import parse_relevance_floor

    return parse_relevance_floor(os.environ.get("PG_RELEVANCE_FLOOR"))


def _relevance_fetch_all_relevant_enabled() -> bool:
    """Kill-switch `PG_RELEVANCE_FETCH_ALL_RELEVANT` (default ON).

    I-fetch-005 iter-2 P0 (§-1.3, Codex HIGHEST): a RELEVANT (above-floor) source must
    NEVER be stranded unfetched by the fetch BUDGET. Recording an above-floor source as an
    ``unfetched_relevant_tail`` is STILL a §-1.3 DROP — an unfetched source has no content,
    so it can carry no weight into composition. With this ON (the fix), EVERY above-floor
    source is fetched and the fetch BUDGET bounds ONLY the below-floor (truly-off-topic)
    demoted fill. Set it to 0/off/false/no to revert to the pre-fix behaviour where the
    budget bounds the WHOLE ordered list (above-floor beyond the budget lands in the
    recorded-but-unfetched relevant tail) — an EMERGENCY rollback only; that path drops
    credible relevant sources pre-fetch and must not be used in production."""
    raw = os.environ.get("PG_RELEVANCE_FETCH_ALL_RELEVANT", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "disabled", "")


@dataclass
class RelevanceGateResult:
    """B4 telemetry for the relevance-ORDER + fetch-budget selection.

    Emitted on `LiveRetrievalResult.relevance_gate` ONLY on the B4 ON path (None
    when OFF => byte-identical). Records the unfetched tail (the candidates the
    fetch BUDGET could not afford) so the recall cost is MEASURABLE + auditable,
    never dropped-and-forgotten.

    §-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3, 2026-06-29, Codex iter-1 P1): the
    relevance floor (`PG_RELEVANCE_FLOOR`) no longer HARD-DROPS below-floor
    candidates pre-fetch — that was the §-1.3-banned hard FILTER on the sweep path.
    The floor now only ORDERS + DISCLOSES: above-floor candidates rank first, the
    below-floor ones are DEMOTED to the tail (in relevance order). The fetch BUDGET
    (a generous disclosed COST cap) is the ONLY bound; if there are fewer above-floor
    than the budget, the most-relevant below-floor candidates FILL the remainder
    (`demoted_fetched_to_fill`) instead of the budget going unused. Off-topic content
    with no overlap still fails the faithfulness engine (strict_verify / NLI / 4-role
    D8 / provenance) downstream — the ONLY sanctioned hard drop.

    Fields:
      - threshold: the relevance floor used (ordering + disclosure boundary, NOT a
        drop gate).
      - total_scored: non-seed candidates scored (seeds bypass scoring).
      - kept_on_topic: above-floor candidate count (the on-topic survivors; these
        rank first). Renamed conceptually to "above-floor count" but the key is kept
        for telemetry continuity.
      - demoted_below_floor: below-floor candidate count — DEMOTED (kept, re-ordered
        to the tail), NOT dropped. The disclosed drop->demote conversion (replaces
        the old `dropped_off_topic`, which implied a hard drop that no longer occurs).
      - demoted_fetched_to_fill: below-floor candidates the BUDGET reached and FETCHED
        (the budget had room beyond the above-floor set) — proof the floor is no
        longer a pre-fetch hard cut.
      - demoted_tail: below-floor candidates left UNFETCHED in the budget tail (a COST
        bound, not a relevance/credibility drop).
      - fetched_budget: total candidates the fetch BUDGET kept (above-floor fetched
        + demoted_fetched_to_fill).
      - unfetched_relevant_tail: above-floor candidates BEYOND the budget — RELEVANT
        but unfetched for COST reasons (a real resource bound, not a relevance/
        credibility drop). This is the recall cost the operator must see.
      - tail_score_min / tail_score_max: the relevance-score band of the WHOLE tail
        (above-floor + demoted), so the operator sees the full unfetched band.
      - scorer: 'semantic_v2' (B1 embedder) or 'lexical_fallback' (embedder
        unavailable — LOUD degrade per LAW II).
    """

    threshold: float
    total_scored: int = 0
    kept_on_topic: int = 0
    demoted_below_floor: int = 0
    demoted_fetched_to_fill: int = 0
    demoted_tail: int = 0
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
            "demoted_below_floor": self.demoted_below_floor,
            "demoted_fetched_to_fill": self.demoted_fetched_to_fill,
            "demoted_tail": self.demoted_tail,
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
    """B4 ON-path selection: relevance ORDER (the floor orders, never filters) +
    fetch BUDGET (cost cap), using B1's semantic embedding-cosine scorer.

    §-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3, 2026-06-29, Codex iter-1 P1): the floor
    used to HARD-DROP every below-floor candidate BEFORE the budget slice, so a
    below-floor source could NEVER be fetched no matter how high the budget — the
    §-1.3-banned hard FILTER on the sweep path. It now only ORDERS + DISCLOSES.

    Pipeline:
      1. Split seeds (`source in _SEED_SOURCE_LABELS`) — NEVER scored, NEVER
         dropped, prepended exactly as `_rerank_and_reserve` does (seed lane
         preserved: primary-trial DOI seeds carry empty title/snippet).
      2. Score every non-seed by REUSING B1's `_semantic_relevance_scores` (max
         cosine over {question} ∪ {sub-queries}) — no B4-private scoring loop.
      3. ORDER (no drop): rank ALL scored candidates by relevance DESC — above-floor
         first, below-floor DEMOTED to the tail (in relevance order). The floor
         (`score >= floor`) decides ORDER + disclosure only; it NEVER removes a
         candidate. Credibility/tier is NEVER consulted.
      4. BUDGET (I-fetch-005 iter-2 P0, §-1.3 WEIGHT-not-FILTER): EVERY above-floor
         (RELEVANT) source is fetched UNCONDITIONALLY — the budget must never strand a
         relevant source unfetched (an unfetched source has no content and can carry no
         weight into composition, so recording it as a tail is STILL a §-1.3 drop). The
         fetch `fetch_cap` bounds ONLY the below-floor (truly-off-topic) demoted fill: if
         the budget has room beyond the WHOLE above-floor set, the most-relevant below-floor
         candidates FILL it (`demoted_fetched_to_fill`); the rest are the below-floor cost
         tail (`demoted_tail`), RECORDED in `RelevanceGateResult`, not silently discarded.
         `unfetched_relevant_tail` is therefore structurally 0 (proof no relevant source is
         stranded). `PG_RELEVANCE_FETCH_ALL_RELEVANT=0` reverts to the pre-fix budget bound.
      5. Carry each kept candidate's relevance score forward as a WEIGHT
         (`relevance_weight` on the returned score map, keyed by url).

    Returns `(selected_candidates, url_to_relevance_weight, gate_telemetry)`.
    Selected order: seeds first (arrival order), then budget-selected non-seeds in
    ARRIVAL order among the selected set (a stable corpus, mirroring
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
    # §-1.3 DEMOTE-NOT-DROP: the floor ORDERS, it does not filter. Partition by the
    # IDENTICAL B1 predicate (`score >= floor`, exactly `item[1] >= relevance_floor`
    # at B1's `_relevance_floor_selection`) but KEEP both sides. Above-floor ranks
    # first (relevance DESC), then the below-floor candidates are DEMOTED to the tail
    # (relevance DESC). A text-less non-seed scores 0.0 and is demoted (not dropped)
    # — it SURVIVES to the budget so it can be fetched-to-know if the budget reaches
    # it. The fetch BUDGET is the ONLY bound; off-topic content with no overlap fails
    # the downstream faithfulness engine (the only sanctioned hard drop), never here.
    above_floor = sorted((t for t in scored if t[0] >= threshold), key=lambda t: (-t[0], t[1]))
    below_floor = sorted((t for t in scored if t[0] < threshold), key=lambda t: (-t[0], t[1]))
    ranked = above_floor + below_floor

    # BUDGET. I-fetch-005 iter-2 P0 (§-1.3 WEIGHT-not-FILTER, Codex HIGHEST): the fetch
    # BUDGET must NEVER strand a RELEVANT (above-floor) source unfetched. Recording an
    # above-floor source as the "unfetched relevant tail" is STILL a §-1.3 DROP — an
    # unfetched source has no content and cannot carry weight into composition. So EVERY
    # above-floor source is fetched UNCONDITIONALLY; the budget bounds ONLY the below-floor
    # (truly-off-topic) demoted fill. If the budget has room beyond the WHOLE above-floor
    # set, the most-relevant below-floor candidates FILL the remainder
    # (`demoted_fetched_to_fill`); the rest sit in the cost-bound below-floor tail (a
    # genuine cost cap on genuinely-off-topic content, never on a relevant source). The
    # kill-switch `PG_RELEVANCE_FETCH_ALL_RELEVANT=0` reverts to the pre-fix budget bound
    # (emergency rollback only — that path drops relevant sources pre-fetch).
    if _relevance_fetch_all_relevant_enabled():
        _demoted_budget = max(0, budget - len(above_floor))
        fetched = above_floor + below_floor[:_demoted_budget]
        tail = below_floor[_demoted_budget:]
    else:
        # Pre-fix behaviour: the budget bounds the whole demote-ordered list; above-floor
        # beyond the budget lands in the (recorded, unfetched) relevant tail.
        fetched = ranked[:budget]
        tail = ranked[budget:]

    selected_idx = {t[1] for t in fetched}
    # Stable corpus: emit fetched non-seeds in ARRIVAL order among the selected set.
    selected_non_seeds = [c for i, c in enumerate(non_seeds) if i in selected_idx]

    # Carry the relevance score forward as a weight, keyed by url (kept set only).
    url_weight: dict[str, float] = {}
    for score, idx, cand in fetched:
        url_weight[cand.url] = float(score)

    # Disclosure splits: how the below-floor DEMOTED set was handled (fetched-to-fill
    # the budget vs left in the tail) + the above-floor relevant tail (cost-bound).
    demoted_fetched_to_fill = sum(1 for t in fetched if t[0] < threshold)
    demoted_tail = sum(1 for t in tail if t[0] < threshold)
    above_floor_tail = sum(1 for t in tail if t[0] >= threshold)

    tail_scores = [t[0] for t in tail]
    gate = RelevanceGateResult(
        threshold=threshold,
        total_scored=len(non_seeds),
        kept_on_topic=len(above_floor),
        demoted_below_floor=len(below_floor),
        demoted_fetched_to_fill=demoted_fetched_to_fill,
        demoted_tail=demoted_tail,
        fetched_budget=len(fetched),
        unfetched_relevant_tail=above_floor_tail,
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
    retrieval_deadline_monotonic: Optional[float] = None,
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
        retrieval_deadline_monotonic: Optional ABSOLUTE ``time.monotonic()`` instant
            that bounds the RETRIEVAL phase (I-deepfix-001 item 4, #1344). When
            ``None`` (DEFAULT — what runs on the relaunch) the deadline is anchored
            at function entry to ``time.monotonic() + PG_RETRIEVAL_WALL_SECONDS``
            (per-INVOCATION). When the caller passes an instant, it is honored
            verbatim so a multi-round ``run_one_query`` (baseline + expansion +
            deepener + agentic + gap) can SHARE ONE per-QUESTION deadline across
            rounds (honest gap: the per-question sharing is not yet wired by the
            ``run_one_query`` owner; per-invocation bounding already removes the
            tens-of-minutes grind on the relaunch). On expiry the snowball/fan-out
            STOPS firing further queries and the already-fetched partial corpus is
            HANDED OFF downstream WITH disclosure (§-1.3 — the unfetched tail is
            disclosed via ``notes`` + ``retrieval_wall_hit``, NEVER silently
            dropped; the run COMPLETES+RENDERS, it does NOT die on a bare timeout).
            Distinct from ``corpus_truncated`` (which the Path-B gate REJECTS) — the
            wall handoff is a render-PASS partial, not a gate-out.

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
    # I-fetch-005 (#1344) FIX 2: also clear the AccessBypass per-URL terminal-block cache (hard
    # WAF access-denied / akamai) at run start so a blocked url from a prior vector does not leak
    # across runs in a long-lived process. Fail-open: a reset error never breaks retrieval.
    try:
        from src.tools.access_bypass import (  # noqa: PLC0415
            reset_terminal_block_cache as _reset_terminal_block_cache,
        )
        _reset_terminal_block_cache()
    except Exception:  # noqa: BLE001 — best-effort cache reset, never breaks retrieval
        pass
    # I-deepfix-001 B2 (#1346): install this run's operator do-not-view deny-list so the
    # FETCH seam (`_fetch_content`) skips any prohibited URL BEFORE its HTTP call. Built from
    # THIS run's `research_question` and overwritten fresh each run (per-run reset, like
    # `reset_refetch_cache` above) so a sequential per-question sweep never leaks a prior
    # deny-list. Empty registry (no appendix / PG_BLOCKED_REFERENCE_DENYLIST=0) => no-op.
    # FAIL-OPEN: a build error yields an empty registry and never aborts retrieval.
    try:
        from src.polaris_graph.retrieval.blocked_reference_registry import (  # noqa: PLC0415
            build_blocked_registry as _build_blocked_registry,
        )
        set_active_blocked_registry(_build_blocked_registry(research_question or ""))
    except Exception as _blk_exc:  # noqa: BLE001 — deny-list never breaks retrieval
        logger.warning(
            "[live_retriever] B2 blocked-reference registry install failed "
            "(fail-open, no deny-list active): %s", _blk_exc,
        )
        set_active_blocked_registry(None)
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
        # I-beatboth-011 idx49 (#1289): rows skipped because clean_fetch_body
        # reported the whole body is a fetch SHELL (boilerplate/interstitial).
        # Telemetry label only — not a threshold.
        "fetch_shell": 0,
        # FIX 2 (#1344): rows DOWN-WEIGHTED because the fetched body is a
        # citation-metadata shell (BibTeX/EndNote export nav, site/episode nav,
        # bare title+@article{}). Telemetry label only — a §-1.3 weight, never a
        # drop. Stays 0 unless PG_CITATION_SHELL_REFETCH is ON.
        "citation_metadata_shell": 0,
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

    # ── U11 (I-deepfix-001): clinical evidence-type query expansion ──────
    # Clinical T1/T2 (RCT / systematic-review / meta-analysis / guideline)
    # starvation is an upstream RECALL gap: the sub-queries fired at the search
    # backends are plain NL with NO evidence-type targeting, so the pool is
    # dominated by generic web. ADD a bounded set of evidence-type-targeted
    # variants of the anchor query so the high-tier literature SURFACES. §-1.3
    # WEIGHT-not-filter: expansion only ADDS discovery queries (they flow through
    # the SAME fetch -> tier -> strict_verify chokepoint); it never drops / caps /
    # filters a source and never touches the faithfulness engine. Flag-gated
    # (PG_EVIDENCE_TYPE_QUERY_EXPANSION), default OFF => byte-identical. Fires ONLY
    # on clinical-domain runs (domain=='clinical') so non-clinical runs are
    # untouched. seed_only passes fetch exactly the injected seeds (no fan-out),
    # so it is excluded.
    if not seed_only:
        from src.polaris_graph.retrieval.evidence_type_query_expansion import (
            expand_evidence_type_queries,
        )
        _pre_expand_n = len(effective_queries)
        effective_queries = expand_evidence_type_queries(
            effective_queries,
            clinical=(isinstance(domain, str) and domain.strip().lower() == "clinical"),
        )
        _n_expanded = len(effective_queries) - _pre_expand_n
        if _n_expanded:
            notes.append(
                f"evidence_type_query_expansion: +{_n_expanded} clinical "
                f"evidence-type sub-queries"
            )

    # ── I-deepfix-001 item 4 (#1344): RETRIEVAL-PHASE wall-deadline ──────
    # Anchor the per-question retrieval deadline. When the caller passes an
    # absolute monotonic instant (multi-round run_one_query sharing ONE
    # per-question deadline) honor it; else anchor per-invocation at
    # now + PG_RETRIEVAL_WALL_SECONDS. On expiry the search fan-out STOPS firing
    # further queries (the snowball logic is UNCHANGED — only its loop is bounded)
    # and whatever was already fetched+classified is HANDED OFF downstream WITH
    # disclosure. This is NOT corpus_truncated (which the Path-B gate REJECTS): the
    # wall handoff is a render-PASS partial — the run COMPLETES+RENDERS on the
    # partial fetch, never dies on a bare timeout (§-1.3: the unfetched tail is
    # disclosed via `notes` + the `retrieval_wall_hit` telemetry below, NEVER
    # silently dropped).
    if retrieval_deadline_monotonic is not None:
        _retrieval_deadline = float(retrieval_deadline_monotonic)
    else:
        _retrieval_deadline = time.monotonic() + _retrieval_wall_seconds()
    # Disclosure counters (surfaced at return). `_retrieval_wall_hit` flips True the
    # moment the wall trips in EITHER phase (search fan-out OR the post-fetch loop);
    # `_queries_skipped_wall` records how many planned sub-queries were never fired.
    _retrieval_wall_hit = False
    _queries_skipped_wall = 0
    # I-deepfix-001 P1-2 (#1344): B4 semantic->lexical fallback disclosure. Flips
    # True at the B4 fallback site below when the relevance gate was requested but the
    # semantic embedder was unavailable (fell back LOUDLY to the lexical cut).
    _semantic_relevance_fell_back = False

    # I-deepfix-001 Wave-3 (#1344): the ADDITIVE date-scoped OpenAlex lane. Extract the question's
    # publication window ONCE (deterministic regex, no network/LLM) so the per-query loop below can
    # issue an EXTRA `openalex_search` scoped to `from_publication_date`/`to_publication_date` when
    # PG_OPENALEX_DATE_FILTER is ON and the question states a window. Strictly ADDITIVE: the base
    # (un-scoped) openalex_search still runs; this only UNIONs in-window primaries a plain search
    # buries. (None, None) or flag-OFF => no extra lane => byte-identical. §-1.3 additive; the frozen
    # faithfulness engine is untouched.
    _oa_date_filter_on = _openalex_date_filter_enabled() and not seed_only
    _oa_date_from, _oa_date_to = (
        _openalex_date_window(research_question) if _oa_date_filter_on else (None, None)
    )
    if _oa_date_filter_on and not (_oa_date_from or _oa_date_to):
        # I-deepfix-001 Wave-3 (#1344): eligible-yet-idle disclosure (Fable P1). The flag is ON but the
        # question states no publication window, so the additive dated lane never fires this call.
        # Surface a distinct [activation] line so the liveness canary can distinguish "idle by design"
        # (the flag is on, the window is simply absent) from "silently dark". Telemetry-only; the frozen
        # faithfulness engine is untouched.
        logger.info(
            "[activation] openalex_date_filter: eligible_no_window "
            "(flag on; question states no publication window; additive dated lane idle)"
        )

    # ── Step 2: run Serper + S2 across queries ──────────────────────
    seen_urls: set[str] = set()
    candidates: list[SearchCandidate] = []

    # I-wire-001 W3 (#1310): search-fusion WRRF. DEFAULT-OFF. When ON, the
    # per-engine RANKED candidate lists are gathered WITHOUT the inline
    # `seen_urls` dedup (the inline dedup destroys per-engine rank, which the
    # fuser needs), then WRRF-fused, then URL-deduped as a deterministic
    # post-step. When OFF, the legacy inline-dedup append below runs
    # byte-identically and `per_engine_lists` stays unused.
    # §-1.3: fusion is an ORDERING/WEIGHT, never a hard drop — the fused output
    # is the full union of every engine's URLs, only re-ordered.
    from src.polaris_graph.retrieval.search_fusion_wrrf import (  # noqa: E402
        wrrf_enabled,
    )
    _wrrf_on = wrrf_enabled()
    # engine-name -> that engine's candidates in returned (rank) order.
    per_engine_lists: dict[str, list[SearchCandidate]] = {}

    def _emit_candidate(engine: str, cand: SearchCandidate) -> None:
        """Append a candidate either to the per-engine WRRF list (ON) or the
        legacy flat `candidates` list with inline `seen_urls` dedup (OFF).

        OFF path is byte-identical to the historical
        `if url in seen_urls: continue; seen_urls.add(url); candidates.append`
        idiom. ON path keeps ALL hits per engine in rank order (cross-engine
        URL-dedup happens once, after fusion).
        """
        url = getattr(cand, "url", "") or ""
        if not url:
            return
        if _wrrf_on:
            per_engine_lists.setdefault(engine, []).append(cand)
            return
        if url in seen_urls:
            return
        seen_urls.add(url)
        candidates.append(cand)

    def _emit_engine_list(engine: str, cands: list[SearchCandidate]) -> None:
        """I-wire-001 W3 (#1310) P1-3: register a backend's WHOLE per-engine RANKED
        list (keyed by the declared backend name) as ONE engine for WRRF, with its
        RANK ORDER preserved. This is the real per-engine signal the domain/need
        backends produce — feeding it (instead of the flat cross-deduped list)
        keeps a URL that two backends both return at its DISTINCT per-engine rank
        in BOTH lists, so wrrf_fuse fuses on real ranks. WRRF-ON only (the caller
        gates on `_wrrf_on`); the intra-list rank order is exactly the backend's
        returned order (already intra-backend-deduped upstream)."""
        bucket = per_engine_lists.setdefault(engine, [])
        for cand in cands:
            if getattr(cand, "url", "") or "":
                bucket.append(cand)

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
    _search_queries = [] if seed_only else list(effective_queries)
    for _qi, q in enumerate(_search_queries):
        # I-deepfix-001 item 4 (#1344): RETRIEVAL-PHASE wall. On expiry STOP firing
        # further sub-queries (the search fan-out is the tens-of-minutes grind: each
        # remaining query pays serial Serper + S2 + OpenAlex round-trips). Record how
        # many planned queries were skipped so the partial cutoff is DISCLOSED (§-1.3
        # — never a silent drop), then break so the already-gathered candidates flow
        # on to fetch -> tiering -> ... -> render. Whatever was fetched still renders.
        if time.monotonic() > _retrieval_deadline:
            _retrieval_wall_hit = True
            _queries_skipped_wall = len(_search_queries) - _qi
            logger.warning(
                "[live_retriever] retrieval wall hit during search fan-out at "
                "query %d/%d — stopping further queries (%d skipped); handing off "
                "the %d candidates gathered so far (PG_RETRIEVAL_WALL_SECONDS)",
                _qi, len(_search_queries), _queries_skipped_wall, len(candidates),
            )
            break
        logger.info("[live_retriever] SERPER q=%r", q[:80])
        # FX-17 (#1126) iter-2: pass api_calls so each HTTP page (not each query) is counted inside
        # _serper_search. The old `+= 1` here undercounted paginated breadth.
        serper_hits = _serper_search(q, num=max_serper, api_calls=api_calls)
        for hit in serper_hits:
            url = hit.get("url", "")
            if not url:
                continue
            # I-wire-001 W3: route through _emit_candidate. OFF -> inline
            # seen_urls dedup (byte-identical). ON -> gather into the per-engine
            # ranked list (rank = append order) for WRRF.
            _emit_candidate("serper", SearchCandidate(
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
            if not url:
                continue
            # I-wire-001 W3: route through _emit_candidate (OFF = byte-identical).
            _emit_candidate("s2", SearchCandidate(
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
                # U25 (I-deepfix-001): UN-MASK the 0-candidate case. Previously EVERY return
                # (incl. a rate-limited 503 swallowed as []) recorded status='ok', so a backend
                # that yielded nothing still counted toward discovery success_rate=1.0. Now a
                # genuine 200-empty is recorded status='ok_zero' (zero_yield=True) — distinct from
                # 'ok' (real hits) and from the 'fail' below (an HTTP error, which now RAISES from
                # openalex_search instead of masking). ToolTracer counts only status=='ok' toward
                # success_rate, so both the empty and the failure honestly drop it below 1.0.
                _oa_zero = not _oa_hits
                _trace_tool(
                    "openalex_search", target=q,
                    status="ok_zero" if _oa_zero else "ok",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    result_count=len(_oa_hits), num_requested=max_s2,
                    zero_yield=_oa_zero,
                )
                # FX-18b (#1123): mirror serper/s2 -> emit an openalex retrieval_trace row so RERUN §-1.1 can verify it fired.
                _trace_query("openalex_search", q, [getattr(c, "url", "") for c in _oa_hits])
                for cand in _oa_hits:
                    url = getattr(cand, "url", "")
                    if not url:
                        continue
                    if not getattr(cand, "query_origin", ""):
                        cand.query_origin = q
                    # I-wire-001 W3: route through _emit_candidate (OFF = byte-identical).
                    _emit_candidate("openalex_search", cand)
                # I-deepfix-001 Wave-3 (#1344): ADDITIVE date-scoped OpenAlex lane. When the question
                # states a publication window and PG_OPENALEX_DATE_FILTER is ON, issue ONE EXTRA
                # date-scoped openalex_search and UNION its hits on top of the un-scoped base hits
                # above (via _emit_candidate's shared seen_urls dedup) — surfacing in-window primaries
                # a plain keyword search buries. Strictly ADDITIVE: removes no base source. Fail-open
                # (a fault adds 0 hits; the base lane already landed). §-1.3; faithfulness untouched.
                if _oa_date_filter_on and (_oa_date_from or _oa_date_to):
                    _oad_t0 = time.time()
                    _oad_t0_mono = time.monotonic()
                    try:
                        _oad_hits = openalex_search(
                            q, limit=max_s2,
                            from_date=_oa_date_from, to_date=_oa_date_to,
                        )
                        api_calls["openalex_search"] = api_calls.get("openalex_search", 0) + 1
                        _oad_zero = not _oad_hits
                        _trace_tool(
                            "openalex_search_dated", target=q,
                            status="ok_zero" if _oad_zero else "ok",
                            latency_ms=(time.time() - _oad_t0) * 1000.0,
                            backend_used="openalex_works_api",
                            result_count=len(_oad_hits), num_requested=max_s2,
                            zero_yield=_oad_zero,
                        )
                        # Distinct retrieval_trace backend name (Fable P1): the dated lane's rows are no
                        # longer conflated with the base openalex_search rows (the prior code reused the
                        # base name "openalex_search" here).
                        _trace_query(
                            "openalex_search_dated", q,
                            [getattr(c, "url", "") for c in _oad_hits],
                        )
                        # I-deepfix-001 Wave-3 (#1344): anti-dark liveness marker (Fable P1). The dated
                        # lane's only prior success signal was the tracer (telemetry-only, gated by
                        # PG_ENABLE_TOOL_TRACKER, swallowed on exception). Emit a distinct [activation]
                        # logger line the liveness canary reads — window bounds + hit count.
                        # dated_hits=0 is the eligible-yet-zero signal. Structural presence + count (§-1.3).
                        logger.info(
                            "[activation] openalex_date_filter: window=%s..%s dated_hits=%d",
                            _oa_date_from or "-", _oa_date_to or "-", len(_oad_hits),
                        )
                        for cand in _oad_hits:
                            url = getattr(cand, "url", "")
                            if not url:
                                continue
                            if not getattr(cand, "query_origin", ""):
                                cand.query_origin = q
                            _emit_candidate("openalex_search", cand)
                    except Exception as _oad_exc:
                        logger.warning(
                            "[live_retriever] openalex_search date-scoped lane failed for %r "
                            "(fail-open): %s", q[:60], _oad_exc,
                        )
                    finally:
                        # I-deepfix-001 Wave-3 (#1344): credit the ADDITIVE dated-lane time BACK to the
                        # retrieval wall so the lane rides OUTSIDE the baseline budget — the base
                        # per-query fan-out AND the downstream fetch/classify phases keep the full wall
                        # they would have with the lane OFF, so the extra HTTP call never displaces a
                        # baseline query/source (Codex/Fable P1 "or add budget"). Bounded: one extra
                        # openalex round-trip per query. LOCAL deadline only (the shared per-question
                        # wall passed from the spine is never mutated).
                        _retrieval_deadline += max(0.0, time.monotonic() - _oad_t0_mono)
            except Exception as exc:
                # U25: an HTTP error (the 503 anonymous-search rate-limit now RAISES
                # OpenAlexHTTPError from openalex_search) is recorded as a real failure —
                # zero_yield=True + the error text (carrying the 503) — never masked as 'ok'.
                _trace_tool(
                    "openalex_search", target=q, status="fail",
                    latency_ms=(time.time() - _oa_t0) * 1000.0,
                    backend_used="openalex_works_api",
                    error=str(exc), result_count=0, num_requested=max_s2,
                    zero_yield=True,
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
            # I-wire-001 W3 (#1310) P1-3: when WRRF is ON, feed each backend's REAL
            # per-engine RANKED list (from `per_engine_lists`, keyed by the declared
            # backend NAME, pre-cross-dedup) into the fuser — so a URL two backends
            # both return keeps its DISTINCT per-engine rank into wrrf_fuse. Routing
            # the flat `need_result.candidates` instead would feed the
            # already-cross-deduped list (the P1-3 bug: ranks collapsed before the
            # fuser). OFF => fall through to the legacy inline-dedup on the flat list.
            _need_per_engine = getattr(need_result, "per_engine_lists", None) or {}
            if _wrrf_on and _need_per_engine:
                for _bname, _blist in _need_per_engine.items():
                    for cand in _blist:
                        if not cand.url:
                            continue
                        if not getattr(cand, "query_origin", ""):
                            cand.query_origin = "need_type_backend"
                    _emit_engine_list(f"need:{_bname}", _blist)
            else:
                for cand in need_result.candidates:
                    url = cand.url
                    if not url:
                        continue
                    if not getattr(cand, "query_origin", ""):
                        cand.query_origin = "need_type_backend"
                    # I-wire-001 W3: key by the candidate's own backend source so each
                    # need-type backend's ranking is a distinct engine list for WRRF
                    # (e.g. clinicaltrials / openfda). OFF = byte-identical inline dedup.
                    _emit_candidate(
                        getattr(cand, "source", "") or "need_type_backend", cand,
                    )
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
            # I-wire-001 W3 (#1310) P1-3: on WRRF-ON, feed each domain backend's REAL
            # per-engine ranked list (keyed by declared backend NAME) into the fuser
            # so per-engine duplicate ranks survive to wrrf_fuse. OFF => legacy flat.
            _dom_per_engine = getattr(domain_result, "per_engine_lists", None) or {}
            if _wrrf_on and _dom_per_engine:
                for _bname, _blist in _dom_per_engine.items():
                    for cand in _blist:
                        if not cand.url:
                            continue
                        if not getattr(cand, "query_origin", ""):
                            cand.query_origin = "domain_backend"
                    _emit_engine_list(f"domain:{_bname}", _blist)
            else:
                for cand in domain_result.candidates:
                    url = cand.url
                    if not url:
                        continue
                    # I-meta-002-q1d (#951): give domain-backend candidates a stable origin
                    # bucket so the per-sub-query rerank reservation handles them consistently.
                    if not getattr(cand, "query_origin", ""):
                        cand.query_origin = "domain_backend"
                    # I-wire-001 W3: key by the candidate's own backend source for WRRF.
                    # OFF = byte-identical inline dedup.
                    _emit_candidate(
                        getattr(cand, "source", "") or "domain_backend", cand,
                    )
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

    # ── Step 2c: WRRF fusion post-step (I-wire-001 W3, #1310) ──────────
    # DEFAULT-OFF. When ON, fuse the per-engine RANKED lists gathered above on
    # their original ranks, THEN URL-dedup the fused order. Seeds stay at the
    # FRONT (already in `candidates` + `seen_urls` from the reserved-lane
    # injection); the fused search/backend candidates are appended AFTER the
    # seeds in WRRF order. §-1.3: the fused list is the FULL union of every
    # engine's URLs — fusion re-orders, it never drops a source. Deterministic
    # (no LLM); the highest-visibility WRRF event is logged for the console.
    if _wrrf_on and per_engine_lists:
        from src.polaris_graph.retrieval.search_fusion_wrrf import (  # noqa: E402
            wrrf_fuse,
        )
        _wrrf = wrrf_fuse(per_engine_lists)
        _n_fused_added = 0
        for _cand in _wrrf.fused:
            _curl = getattr(_cand, "url", "") or ""
            # Dedup against seeds (and across engines — the fuser already
            # collapsed cross-engine URL duplicates to one object).
            if not _curl or _curl in seen_urls:
                continue
            seen_urls.add(_curl)
            candidates.append(_cand)
            _n_fused_added += 1
        # Highest-visibility console/log event (standard point 8): the fused
        # ordering + per-engine contribution + the WRRF k/weights actually used.
        _top_preview = [
            getattr(c, "url", "")[:80] for c in candidates[
                len(candidates) - _n_fused_added:
            ][:5]
        ]
        logger.info(
            "[live_retriever] WRRF FUSED %d engines (%s) -> %d unique candidates "
            "(k=%.1f weights=%s); fused top-5=%s",
            len(per_engine_lists), _wrrf.per_engine_counts, _n_fused_added,
            _wrrf.k_used, _wrrf.weights_used, _top_preview,
        )
        notes.append(
            f"search_fusion_wrrf: fused {len(per_engine_lists)} engines "
            f"{_wrrf.per_engine_counts} -> {_n_fused_added} ranked candidates "
            f"(k={_wrrf.k_used}, weights={_wrrf.weights_used})"
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
            # I-deepfix-001 D3 (2026-06-29): DEMOTE-NOT-DROP (§-1.3). `filt.kept`
            # now carries EVERY non-seed candidate in cosine-DESCENDING order (most-
            # relevant first); the below-threshold tail is DEMOTED (kept), not
            # hard-dropped. The candidate ORDERING survives to the fetch stage via
            # this sorted list, so the downstream fetch BUDGET (the disclosed bound)
            # fetches the most-relevant first. The set-difference below is now empty
            # by construction (nothing is pre-fetch-dropped); it is kept defensively
            # in case `rejected` ever carries a genuine structural error.
            candidates = _seed_cands + filt.kept
            for _dropped_url in _pre_offtopic_urls - {c.url for c in filt.kept}:
                _trace_drop(_dropped_url, "offtopic")
                drop_reasons["offtopic"] += 1
            notes.append(
                f"prefetch_offtopic: {filt.total_kept} kept "
                f"({filt.total_demoted} demoted below threshold, "
                f"{filt.total_rejected} dropped) "
                f"(threshold={filt.threshold_used:.2f}, demote-not-drop)"
            )
            # I-ready-017 Task 2a (#1204): persist the off-topic split. Store the
            # raw threshold float (not the :.2f note string) so the manifest
            # carries the unrounded value used in the ordering decision.
            # I-deepfix-001 D3: `demoted` makes the drop->demote conversion DISCLOSED
            # in the manifest; `rejected` is 0 by default (demote-not-drop).
            prefetch_offtopic = {
                "kept": filt.total_kept,
                "rejected": filt.total_rejected,
                "demoted": filt.total_demoted,
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
            # I-deepfix-001 P1-2 (#1344): record the semantic->lexical fallback so the
            # winner-firing gate can catch a requested-but-degraded W6/B4 semantic
            # winner (it fired the legacy lexical cut, not the semantic scorer).
            _semantic_relevance_fell_back = True
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
    # B4 (§-1.3 DEMOTE-NOT-DROP, I-deepfix-001 D3 2026-06-29, Codex iter-1 P1): the
    # floor no longer HARD-DROPS below-floor candidates pre-fetch, so the ONLY
    # unfetched candidates are the budget TAIL — a disclosed COST bound, never a
    # quality/credibility verdict. The tail is split into the above-floor RELEVANT
    # tail (`relevance_budget_tail`) and the below-floor DEMOTED tail
    # (`relevance_below_floor_tail`); both are unfetched for COST. The old
    # `offtopic_below_threshold` DROP reason is GONE — below-floor is now demoted,
    # and its drop->demote conversion (total demoted + how many were fetched-to-fill
    # the budget vs left in the tail) is surfaced on `relevance_gate` telemetry
    # (manifest) below. `_rerank_dropped_urls` here is exactly the tail (the only
    # non-fetched set), so every traced url is a cost non-fetch, not a relevance drop.
    if _b4_gate is not None:
        drop_reasons.setdefault("relevance_budget_tail", 0)
        drop_reasons.setdefault("relevance_below_floor_tail", 0)
        drop_reasons["relevance_budget_tail"] += _b4_gate.unfetched_relevant_tail
        drop_reasons["relevance_below_floor_tail"] += _b4_gate.demoted_tail
        for _dropped_url in _rerank_dropped_urls:
            _trace_drop(_dropped_url, "relevance_gate_not_fetched")
        _msg = (
            f"relevance_gate: threshold={_b4_gate.threshold:.2f} scored="
            f"{_b4_gate.total_scored} above_floor={_b4_gate.kept_on_topic} "
            f"demoted_below_floor={_b4_gate.demoted_below_floor} "
            f"(fetched_to_fill={_b4_gate.demoted_fetched_to_fill}, "
            f"tail={_b4_gate.demoted_tail}) fetched={_b4_gate.fetched_budget} "
            f"unfetched_relevant_tail={_b4_gate.unfetched_relevant_tail} "
            f"(fetch_cap={fetch_cap} scorer={_b4_gate.scorer}, demote-not-drop)"
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
    # I-wire-001 W5 (PG_CREDIBILITY_LLM_TIERING): the credibility LLM-tiering winner runs
    # the per-source tier as a BOUNDED-PARALLEL batch (env cap PG_TIER_LLM_WORKERS) rather
    # than the serial per-candidate rule call. When ON we DEFER the tier: collect each
    # candidate's ClassificationSignals during the loop (keyed by the classified_sources
    # row index) and assign tiers in one bounded-parallel post-loop step; the rules-floor
    # is the instant per-source fallback. OFF -> the inline serial classify_source_tier
    # runs exactly as today (byte-identical). Tier is a WEIGHT, never a drop (§-1.3).
    _llm_tiering_on = os.environ.get(
        "PG_CREDIBILITY_LLM_TIERING", "0"
    ).strip().lower() in ("1", "true", "yes", "on")
    _deferred_tier_signals: list[ClassificationSignals] = []
    _deferred_tier_row_idx: list[int] = []
    # I-wire-001 W5 (Codex P1#1): the GENERATOR reads the per-citation tier off the
    # evidence ROW (evidence_rows[].tier, consumed as ev.get("tier") in the outline
    # digest), NOT off classified_sources. The post-loop LLM-tiering batch only
    # back-fills classified_sources, so without this the LLM tier would silently
    # no-op in report.md (rules-floor placeholder only). `_w5_loop_idx` carries the
    # current candidate's position in _deferred_tier_signals so the evidence row it
    # produces records that index; the post-loop batch then back-fills BOTH surfaces.
    _w5_loop_idx: int = -1
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
    # I-deepfix-001 (wall/tiering-abort fix, #1344) P1a: fetch-SUBWALL disclosure
    # counters. Stay False/0 on the serial-fallback / no-candidate path so that path is
    # byte-identical (the subwall only exists when the parallel fetch batch actually ran).
    _fetch_subwall_hit = False
    _fetch_subwall_timeout = 0
    _fetch_subwall_not_dispatched = 0

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
        # I-deepfix-001 (wall/tiering-abort fix, #1344): bound the fetch batch to a
        # FRACTION of the remaining retrieval wall so slow web-fetch cannot consume the
        # ENTIRE wall and leave the post-fetch classify loop (which builds the corpus and
        # defers W5 credibility-tiering) zero time — the starvation that produced an
        # all-rules-floor T4-skewed corpus and a FALSE abort_corpus_approval_denied. The
        # remainder of the wall is reserved for classification. Still hard-capped by the
        # wall itself (fraction <= 1.0); PG_RETRIEVAL_FETCH_WALL_FRACTION=1.0 reproduces
        # the legacy full-wall budget byte-for-byte. Faithfulness-neutral (§-1.3): a source
        # not fetched before the cap is DISCLOSED via retrieval_wall_hit/notes, never
        # silently dropped.
        _fetch_wall_fraction = _retrieval_fetch_wall_fraction()
        _fetch_now_mono = time.monotonic()
        _fetch_deadline = min(
            _retrieval_deadline,
            _fetch_now_mono
            + _fetch_wall_fraction
            * max(0.0, _retrieval_deadline - _fetch_now_mono),
        )
        parallel_report = parallel_fetch(
            fetch_tasks, fetcher,
            max_workers=max_workers,
            per_backend_max_concurrent=_per_host_concurrent,
            per_task_timeout=per_task_timeout,
            # I-deepfix-001 P1-3 (#1344): bound the fetch batch budget by the REMAINING
            # retrieval-phase wall. `_retrieval_deadline` is an absolute monotonic instant
            # (same domain as parallel_fetch's batch_start), so the effective batch
            # deadline = min(its derived budget, the wall). Without this the derived
            # budget (per_task_timeout * waves ≈ 3960s at FETCH_CAP=740) dwarfs the
            # 1800s wall and the wall could not cap the fetch grind.
            # I-deepfix-001 (wall/tiering-abort fix): use the fraction-reserved
            # `_fetch_deadline` (<= `_retrieval_deadline`) so a classify slice survives.
            overall_deadline_monotonic=_fetch_deadline,
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
        # I-deepfix-001 (wall/tiering-abort fix, #1344) P1a: DISCLOSE the fetch-SUBWALL
        # cutoff. When the fetch batch was bounded to a fraction of the remaining wall
        # (_fetch_deadline < _retrieval_deadline) AND that cutoff actually bit (tasks timed
        # out or were never dispatched before it), those candidates land as ordinary
        # `fetch_failed` (a NOT_DISPATCHED task has no fetched_side entry -> ok=False -> the
        # `fetch_failed` drop-reason below) with NO wall attribution. Surface a SEPARATE
        # `fetch_subwall_hit` signal (NOT `retrieval_wall_hit` — the full retrieval wall did
        # not trip: all queries fired and the classify loop kept its reserved slice) so the
        # cutoff is DISCLOSED (§-1.3 disclose-don't-drop), never a silent drop. The
        # fraction=1.0 legacy path keeps `_fetch_deadline == _retrieval_deadline` =>
        # `_fetch_subwall_active` False => no note, fields stay False/0 = byte-identical OFF
        # (a real cutoff under fraction=1.0 is already disclosed by the existing
        # `retrieval_wall_hit` path in the post-fetch classify loop).
        # I-deepfix-001 (wall/tiering-abort fix, #1344) P2 (Codex REQUEST_CHANGES): only
        # POPULATE the subwall counts when the subwall is ACTUALLY active (fraction < 1.0
        # => `_fetch_deadline < _retrieval_deadline`). When fraction=1.0 the subwall is OFF,
        # so the three counters keep their 0/0/False init above — GENUINELY byte-identical
        # OFF, never leaking parallel_report.timeout_count / not_dispatched_count into a
        # `fetch_subwall_*` field the subwall never bounded. A real cutoff under fraction=1.0
        # is disclosed by the existing `retrieval_wall_hit` + api_calls[
        # "parallel_fetch_timeout_count"] paths instead, not by fetch_subwall_*.
        _fetch_subwall_active = _fetch_deadline < _retrieval_deadline
        if _fetch_subwall_active:
            _fetch_subwall_timeout = parallel_report.timeout_count
            _fetch_subwall_not_dispatched = parallel_report.not_dispatched_count
            _fetch_subwall_hit = (
                _fetch_subwall_timeout > 0 or _fetch_subwall_not_dispatched > 0
            )
        if _fetch_subwall_hit:
            _subwall_note = (
                f"fetch_subwall_hit: fetch batch bounded to "
                f"{_fetch_wall_fraction:.2f} of the remaining retrieval wall "
                f"(PG_RETRIEVAL_FETCH_WALL_FRACTION) to reserve a classify/W5 slice; "
                f"{_fetch_subwall_timeout} timed out and "
                f"{_fetch_subwall_not_dispatched} never dispatched before the fetch "
                f"cutoff — DISCLOSED (flow on as fetch_failed), NOT dropped (§-1.3)"
            )
            logger.warning("[live_retriever] %s", _subwall_note)
            notes.append(_subwall_note)
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

    # ── W2 content-relevance judge — pre-loop bounded-parallel batch (I-wire-001
    # #1311) ──────────────────────────────────────────────────────────────────
    # DEFAULT-OFF. When ON AND the parallel-fetch path ran (production default),
    # all bodies are already in `fetched_side`, so score them ALL in ONE batched
    # Qwen3-Reranker-0.6B pass (one GPU load) + bounded-parallel GLM-5.2
    # escalation on the ambiguous band, BEFORE the per-candidate classify loop.
    # The per-candidate loop reads the precomputed weight from `_w2_by_idx` and
    # applies it as a WEIGHT on the CorpusSource (DEMOTE, never a drop — §-1.3).
    # On the serial fetch fallback (`use_parallel=False`) there is no pre-loop
    # body, so the score is computed inline per-candidate below with a LOUD
    # disclosed "serial non-batched" degrade (wiring_standard point 1).
    _w2_on = False
    _w2_by_idx: dict[int, Any] = {}
    _w2_report = None
    try:
        from src.polaris_graph.retrieval.content_relevance_judge import (  # noqa: E402
            content_relevance_enabled,
        )
        _w2_on = content_relevance_enabled()
    except Exception as _w2_imp_exc:  # import must never break retrieval
        logger.warning(
            "[live_retriever] W2 content_relevance import failed (%s) — W2 OFF",
            str(_w2_imp_exc)[:160],
        )
        _w2_on = False
    if _w2_on and use_parallel and candidates:
        from src.polaris_graph.retrieval.content_relevance_judge import (  # noqa: E402
            score_passages,
        )
        _w2_passages: list[tuple[int, str, str]] = []
        for _wi, _wcand in enumerate(candidates):
            _wcontent = fetched_side.get(_wcand.url, ("", False, "", "", ""))[0]
            _w2_passages.append((_wi, _wcand.url, _wcontent or ""))
        # I-deepfix-001 (wall/tiering-abort fix, #1344) P1b: bound W2 to a RESERVED SLICE of
        # the remaining wall (PG_RETRIEVAL_W2_WALL_FRACTION, default 0.5) instead of the FULL
        # retrieval deadline. The prior full-wall threading let W2 — whose Stage-1 reranker
        # one-pass is NOT deadline-checked and whose GLM escalation could grind to ~600s —
        # consume the entire remaining wall, so the per-candidate classify loop then tripped
        # `> _retrieval_deadline` near-immediately and handed off a near-empty corpus: exactly
        # the classify/W5 starvation the fetch subwall was built to prevent. Reserving half
        # the remaining wall for classification closes that. =1.0 => `_w2_deadline ==
        # _retrieval_deadline` = byte-identical to the prior threading. On expiry the remaining
        # ambiguous passages are kept at FULL weight (always-release, no drop — §-1.3); the new
        # pre-scoring guard in score_passages closes the zero-budget-at-entry case.
        _w2_now = time.monotonic()
        _w2_deadline = min(
            _retrieval_deadline,
            _w2_now
            + _retrieval_w2_wall_fraction()
            * max(0.0, _retrieval_deadline - _w2_now),
        )
        _w2_report = score_passages(
            research_question, _w2_passages,
            deadline_monotonic=_w2_deadline,
        )
        _w2_by_idx = _w2_report.by_idx()
        # Highest-visibility console event (point 8): the W2 disposition.
        logger.info(
            "[live_retriever] W2 content-relevance: scored=%d relevant=%d "
            "demoted=%d escalated=%d device=%s (DEMOTE keeps low weight, NO drop)",
            _w2_report.n_scored, _w2_report.n_relevant, _w2_report.n_demoted,
            _w2_report.n_escalated, _w2_report.reranker_device,
        )
        notes.append(
            f"content_relevance_judge: scored={_w2_report.n_scored} "
            f"relevant={_w2_report.n_relevant} demoted={_w2_report.n_demoted} "
            f"escalated={_w2_report.n_escalated} (weight-not-filter, no drop)"
        )

    # ── WAVE-2 Fix A: PG_POST_FETCH_ENRICH_PARALLEL — pre-loop bounded-parallel
    # OpenAlex enrich batch (I-deepfix-001 #1344) ───────────────────────────────
    # DEFAULT-OFF. When ON (and OpenAlex enrich is enabled), pre-batch the
    # per-candidate enrich in a BOUNDED ThreadPool BEFORE the serial classify loop
    # so a slow serial enrich tail cannot consume the retrieval wall and drop
    # already-fetched bodies unclassified (the Wave-2 throughput collapse). The
    # loop then reads each candidate's enrich from `_enrich_by_idx` (a dict lookup,
    # no per-candidate network) instead of the inline `_bounded_openalex_enrich`.
    # OFF => `_enrich_by_idx` stays empty and the loop's serial enrich path runs
    # byte-identically. Faithfulness-neutral (enrich is credibility metadata; the
    # frozen strict_verify / NLI / 4-role engine is untouched).
    _enrich_parallel_on = _post_fetch_enrich_parallel_enabled()
    _enrich_by_idx: dict[int, dict[str, Any]] = {}
    if _enrich_parallel_on and enable_openalex_enrich and candidates:
        _enrich_workers = _post_fetch_enrich_workers()
        # Codex wave-2 P1a: bound the SYNCHRONOUS pre-batch to a RESERVED SLICE of the
        # remaining wall (PG_POST_FETCH_ENRICH_WALL_FRACTION, default 0.5) — NOT the full
        # `_retrieval_deadline`. The batch collects in index order and blocks until every
        # future resolves or the deadline passes; handing it the full wall let a slow early
        # future stall collection to the wall and starve the classify loop it was meant to
        # protect (rescue OFF => the fetched-body tail is dropped at candidate 0; rescue ON
        # => every candidate falls into rules-only rescue). Reserving the remainder for
        # classification restores the intended protection. =1.0 (or any invalid value) =>
        # `_enrich_deadline == _retrieval_deadline` = byte-identical to the prior full-wall
        # collection. A straggler past the reserved slice is recorded as `{}` — the SAME
        # fail-open the serial enrich returns on timeout (undated row never dropped, §-1.3).
        _enrich_now = time.monotonic()
        _enrich_deadline = min(
            _retrieval_deadline,
            _enrich_now
            + _post_fetch_enrich_wall_fraction()
            * max(0.0, _retrieval_deadline - _enrich_now),
        )
        _enrich_by_idx = _prefetch_openalex_enrich_parallel(
            candidates,
            workers=_enrich_workers,
            deadline_monotonic=_enrich_deadline,
        )
        _enrich_nonempty = sum(1 for _v in _enrich_by_idx.values() if _v)
        logger.info(
            "[live_retriever] PG_POST_FETCH_ENRICH_PARALLEL ON — pre-batched "
            "OpenAlex enrich over %d candidates (workers=%d, enriched=%d, "
            "wall_reserved_for_classify=%.1fs) — replacing the serial in-loop enrich; "
            "already-fetched bodies no longer lost to a slow serial enrich tail, and the "
            "batch can no longer burn the whole wall before classification",
            len(candidates), _enrich_workers, _enrich_nonempty,
            max(0.0, _retrieval_deadline - _enrich_deadline),
        )

    # ── WAVE-2 Fix B: PG_WALL_CLASSIFY_RESCUE — wall-break rules-only rescue
    # (I-deepfix-001 #1344) ─────────────────────────────────────────────────────
    # DEFAULT-OFF. When ON, the retrieval-wall break below does NOT drop the
    # remaining already-fetched bodies: it switches the loop into RULES-ONLY rescue
    # mode (no enrich, no LLM tiering, no network re-fetch) that classifies them at
    # the deterministic rules-floor tier and KEEPS them (§-1.3 keep-not-drop) so
    # they feed the CRAG corrective reserve. OFF => the wall break hands off exactly
    # as before (byte-identical). The faithfulness engine is untouched.
    _wall_rescue_on = _wall_classify_rescue_enabled()
    _wall_rescue_mode = False
    _wall_rescued_count = 0
    if _wall_rescue_on:
        # WAVE-2 Fix B (Codex wave-2 P1): emit the anti-dark LIVENESS marker NOW —
        # independent of whether the retrieval wall trips — so an official run PROVES
        # the rescue path is wired even when the parallel enrich pre-batch keeps the
        # wall from ever tripping (the wall-hit "engaged" note is not liveness proof;
        # FORCE_ON + SLATE prove only that the env is set). Fires every run the flag
        # is ON. Faithfulness-neutral disclosure only.
        logger.info(
            "%s", _wall_rescue_armed_marker(enrich_parallel=_enrich_parallel_on)
        )

    for i, cand in enumerate(candidates):
        # I-deepfix-001 item 4 (#1344): RETRIEVAL-PHASE wall (checked BEFORE the
        # legacy post-fetch loop budget). On expiry, STOP classifying the remaining
        # already-fetched bodies and HAND OFF whatever was classified so far. This is
        # the render-PASS partial handoff — DISTINCT from the `corpus_truncated`
        # truncation policies below (which the Path-B gate REJECTS): the wall does
        # NOT set `corpus_truncated`, so the run COMPLETES+RENDERS on the partial
        # corpus. The skipped tail is DISCLOSED via `notes` + `retrieval_wall_hit`
        # (§-1.3 — never a silent drop). The per-candidate Layer-1 bound still guards
        # any single wedged candidate; this wall guards the whole-phase grind.
        if time.monotonic() > _retrieval_deadline:
            if _wall_rescue_on:
                # WAVE-2 Fix B (PG_WALL_CLASSIFY_RESCUE): DO NOT drop the remaining
                # already-fetched bodies. Engage rules-only rescue mode ONCE and FALL
                # THROUGH to classify this + every remaining candidate RULES-ONLY
                # (no enrich / LLM / network) and KEEP them for the CRAG reserve
                # (§-1.3 keep-not-drop). `_retrieval_wall_hit` still discloses the
                # wall tripped; the faithfulness engine is untouched.
                if not _wall_rescue_mode:
                    _wall_rescue_mode = True
                    _retrieval_wall_hit = True
                    logger.warning(
                        "[live_retriever] retrieval wall hit at candidate %d/%d — "
                        "PG_WALL_CLASSIFY_RESCUE ON: classifying the remaining "
                        "already-fetched bodies RULES-ONLY (rules-floor tier; no "
                        "enrich/LLM/network) and KEEPING them for the CRAG reserve "
                        "(§-1.3 keep-not-drop; faithfulness engine untouched)",
                        i, len(candidates),
                    )
                # fall through (no break) — process this candidate in rescue mode.
            else:
                _retrieval_wall_hit = True
                _candidates_processed = i
                logger.warning(
                    "[live_retriever] retrieval wall hit during the post-fetch "
                    "classify loop at candidate %d/%d (%d already classified) — "
                    "handing off the partial corpus (render-PASS, NOT corpus_truncated; "
                    "PG_RETRIEVAL_WALL_SECONDS)",
                    i, len(candidates), len(classified_sources),
                )
                break
        if _loop_budget_truncation_active(
            wall_rescue_mode=_wall_rescue_mode,
            now=time.monotonic(),
            loop_deadline=_loop_deadline,
        ):
            # WAVE-2 Fix B (Codex wave-2 P1): in rescue mode this branch is inert
            # (predicate returns False) so an also-expired _loop_deadline can NEVER
            # break the loop and DROP the remaining already-fetched bodies — they are
            # all classified RULES-ONLY and KEPT (§-1.3 keep-not-drop). OFF / pre-rescue
            # => byte-identical to the prior bare `time.monotonic() > _loop_deadline`.
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

        # ── W2 content-relevance APPLY (I-wire-001 #1311) — post-body, pre-tier ──
        # Resolve THIS candidate's relevance WEIGHT (§-1.3: a weight, never a
        # drop). Parallel path: read the precomputed batch verdict. Serial path:
        # compute inline with a LOUD disclosed "non-batched" degrade. OFF => the
        # weight stays 1.0 / label "" so the CorpusSource is byte-identical.
        _w2_weight = 1.0
        _w2_label = ""
        if _w2_on:
            if use_parallel:
                _w2v = _w2_by_idx.get(i)
                if _w2v is not None:
                    _w2_weight = _w2v.weight
                    _w2_label = _w2v.label
            elif not _wall_rescue_mode:
                # Serial fallback: no pre-loop batch — compute this one inline.
                # WAVE-2 Fix B: SKIP this inline (GPU) compute in rescue mode — the
                # rescued body keeps the default full weight (1.0), never demoted.
                from src.polaris_graph.retrieval.content_relevance_judge import (  # noqa: E402
                    score_passages,
                )
                if i == 0:
                    logger.warning(
                        "[live_retriever] W2 content-relevance running INLINE on "
                        "the serial fetch path (PG_USE_PARALLEL_FETCH=0) — this is "
                        "the DISCLOSED non-batched degrade; the production parallel "
                        "path batches the reranker once.",
                    )
                _w2_single = score_passages(
                    research_question, [(i, cand.url, content or "")],
                ).by_idx().get(i)
                if _w2_single is not None:
                    _w2_weight = _w2_single.weight
                    _w2_label = _w2_single.label

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
        if _wall_rescue_mode:
            # WAVE-2 Fix B: past the retrieval wall the already-fetched body is
            # classified RULES-ONLY — SKIP the (slow, serial) OpenAlex enrich
            # entirely so the fetched-body tail is not lost to the wall. `oa` stays
            # {} (an undated/unenriched row is never demoted downstream — fail-open);
            # the faithfulness engine is untouched (§-1.3 keep-not-drop).
            pass
        elif _enrich_parallel_on:
            # WAVE-2 Fix A: read THIS candidate's enrich from the pre-loop bounded-
            # parallel batch (built once before the loop) instead of the serial per-
            # candidate round-trip. Order-stable (keyed by candidate index); {} when
            # the batch abandoned a straggler past its bound (identical to the serial
            # failure return). Same downstream result as the serial enrich.
            oa = _enrich_by_idx.get(i, {})
            if oa:
                api_calls["openalex"] += 1
        elif enable_openalex_enrich and not _enrich_disabled:
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
        # I-deepfix-001 B14 (#1358): title<->body consistency gate. A mis-stitched
        # source (the serper/openalex METADATA title belongs to a DIFFERENT page
        # than the fetched body — verified on fresh2: ev_037 arxiv "K-12
        # COMPETITIVENESS" title glued to a CMU "Bellwether" body) makes the
        # pipeline reason about ONE source under TWO identities. Cross-check the
        # METADATA title (cand.title from serper/openalex) against the BODY-derived
        # title (content_title) + body head. On a confirmed mismatch the gate
        # RE-DERIVES classifier_title from the body and records the flag — it NEVER
        # drops a source (§-1.3 weight-not-filter; faithfulness engine untouched).
        # similarity_fn is None here: the leaf module's cheap token-overlap
        # prescreen + overlap fallback catches the gross "two different papers"
        # mismatches (overlap << floor) with NO per-source model load (§8.4); the
        # locked-slate reranker escalation is a future enhancement (see honest_gap).
        # OFF path (PG_TITLE_BODY_CONSISTENCY=0): no keys merged => byte-identical.
        _tb_verdict = None
        if title_body_consistency.title_body_consistency_enabled():
            _tb_verdict = title_body_consistency.check_title_body_consistency(
                metadata_title=cand.title or "",
                body_title=content_title or "",
                body_text=content or "",
                similarity_fn=None,
            )
            if not _tb_verdict.identity_consistent and _tb_verdict.resolved_title:
                logger.info(
                    "[live_retriever] B14 title<->body mismatch for %r — title "
                    "re-derived from body (meta=%r body=%r overlap=%.2f); flagged "
                    "identity_consistent=False, source KEPT (§-1.3)",
                    cand.url, (cand.title or "")[:60],
                    (content_title or "")[:60], _tb_verdict.prescreen_overlap,
                )
                classifier_title = _tb_verdict.resolved_title
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
        # I-deepfix-001 B10(b) (#1352, PREREQUISITE): resolve the publication YEAR
        # from the OpenAlex enrich already fetched, so downstream layers can ENFORCE
        # a user date window (B10 d/c/e) — nothing can demote an out-of-window
        # source without this. The year lives only inside the authority_signals
        # sub-dict today; surface it (no extra network). None when OpenAlex
        # returned nothing (an undated row is NEVER demoted later — fail-open).
        _pub_year = None
        _pub_date = None
        if isinstance(_auth_dict, dict):
            _py = _auth_dict.get("publication_year")
            try:
                if _py is not None:
                    _py_i = int(_py)
                    if 1900 <= _py_i <= 2100:
                        _pub_year = _py_i
            except (TypeError, ValueError):
                _pub_year = None
            # I-deepfix-001 Codex wave-2 P1: carry the full publication_date
            # (YYYY-MM-DD) so the selector can enforce a MONTH-precision ceiling.
            # Only accept a well-formed ISO YYYY-MM[-DD]; else leave None (the row
            # falls back to year-precision, never demoted on a malformed date).
            _pd = _auth_dict.get("publication_date")
            if isinstance(_pd, str) and re.match(r"^\s*\d{4}-\d{2}", _pd):
                _pub_date = _pd.strip()
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
        if _wall_rescue_mode:
            # WAVE-2 Fix B (PG_WALL_CLASSIFY_RESCUE): RULES-ONLY classification of an
            # already-fetched body past the retrieval wall. Deterministic rules-floor
            # tier (NO LLM defer, NO dispatcher, NO network) via the shared
            # `_wall_rescue_classify_source` helper; the source is KEPT with a FINAL
            # tier (never a placeholder -> the W5 batch never touches it) so it feeds
            # the CRAG reserve. `_w5_loop_idx=-1` disables the later evidence-row W5
            # back-fill hook. §-1.3 keep-not-drop; the frozen faithfulness engine
            # (strict_verify / NLI / 4-role / provenance) is UNTOUCHED — this only
            # classifies+keeps, the downstream verify leg still re-checks the row.
            _w5_loop_idx = -1
            # Codex wave-2 P1b + Wave-2 re-review P0/P1: KEEP the rescued body at the
            # deterministic RULES-FLOOR weight, NEVER the default full `_w2_weight`
            # (1.0). Past the wall the content-relevance pass is skipped (no GPU
            # reranker), so the row was never scored — carrying full weight would
            # falsely rank it as fully relevant. The floor (`_wall_rescue_weight`,
            # default 0.25) is low but NON-zero: the source still flows to composition
            # at reduced weight and is NEVER dropped (§-1.3 keep-at-floor). The label is
            # the keep-neutral `_WALL_RESCUE_LABEL` (NOT a `demoted` off-topic label,
            # which would suppress its cite surface) so the disclosure is honest without
            # ever removing the source.
            #
            # Resolve the floor ONCE and stamp it on BOTH surfaces so they can never
            # diverge (the Wave-2 re-review defect): (1) the per-candidate locals
            # `_w2_weight`/`_w2_label` — the values the groundable EVIDENCE row the
            # generator/CRAG path actually reads picks up below (~L6780). Previously
            # these were left at the full 1.0/"" default in rescue mode (the W2 block
            # above skips the inline compute via `elif not _wall_rescue_mode`), so the
            # rescued body's evidence row carried FULL weight while only the CorpusSource
            # got the floor — a rescued body laundered into the evidence/CRAG path at
            # full/default weight (§-1.3 weight-not-drop violated on that path); and
            # (2) the CorpusSource the helper builds. Setting the locals to the floor
            # makes the `if _w2_label:` evidence-row block below fire and stamp the SAME
            # floor weight + keep-neutral label onto the row, so the rescued body is
            # safely kept AND provenanced at the honest rules-floor on every downstream
            # surface. Faithfulness-neutral (a weight + disclosure label only; the frozen
            # strict_verify / NLI / 4-role / provenance engine is untouched).
            _rescue_weight = _wall_rescue_weight()
            _w2_weight = _rescue_weight
            _w2_label = _WALL_RESCUE_LABEL
            _rescue_src, tier_result = _wall_rescue_classify_source(
                signals, cand.url, cand.title, domain_,
                content_relevance_weight=_rescue_weight,
                content_relevance_label=_WALL_RESCUE_LABEL,
            )
            classified_sources.append(_rescue_src)
            _wall_rescued_count += 1
        elif _llm_tiering_on:
            # I-wire-001 W5: DEFER the LLM tier to the bounded-parallel post-loop batch.
            # Build the row now with a placeholder tier (back-filled below); record the
            # signals + row index so the batch assigns the LLM tier (rules-floor
            # fallback) in order. No source is dropped (§-1.3 weight-not-filter).
            #
            # Codex P1#1 fix: the inline `tier_result` MUST be bound on this ON-path so
            # the evidence-row build below (`_row["tier"] = tier_result.tier.value` at
            # ~L4890) reads a REAL value instead of raising UnboundLocalError on the
            # first fetched source. We bind it to the deterministic rules-floor —
            # `_classify_source_tier_rules`, the SAME instant fallback the W5 batch uses
            # at credibility_llm_tiering.py:238 — never the LLM dispatcher
            # `classify_source_tier` (that would fire a blocking per-source LLM call and
            # defeat the bounded-parallel batch). `_w5_loop_idx` is the position in
            # _deferred_tier_signals so the evidence row can record it and the post-loop
            # batch back-fills BOTH classified_sources AND the matching evidence row's
            # tier (the surface the generator actually reads).
            _w5_loop_idx = len(_deferred_tier_signals)
            tier_result = _classify_source_tier_rules(signals)
            # I-deepfix-001 (journal_genre_stamp): the W5 deferred path calls
            # `_classify_source_tier_rules` DIRECTLY, bypassing the `classify_source_tier`
            # dispatcher — so it skipped the dispatcher's per-citation document-GENRE stamp
            # (`_m2_dt` at tier_classifier.py:1278). Result: `tier_result.document_type` /
            # `is_journal_article` stayed None on the W5 winner path, so the groundable
            # evidence row below never set `document_type` and every journal article
            # (JEP/QJE/Science/Nature) was mislabeled non-journal downstream. Stamp the genre
            # here, IDENTICALLY to the dispatcher's OFF-path (~L5565 `classify_source_tier`)
            # so both paths carry the same disclosure. `_m2_dt` is PURE (no network/LLM),
            # gated by PG_DOCUMENT_TYPE_WEIGHT (no-op / byte-identical when OFF), fail-open,
            # and touches NO faithfulness surface (strict_verify / NLI / 4-role / provenance
            # are FROZEN) — it only sets the advisory genre label the credibility disclosure
            # reads (§-1.3 WEIGHT-and-DISCLOSE).
            _m2_dt(tier_result, signals)
            _deferred_tier_signals.append(signals)
            _deferred_tier_row_idx.append(len(classified_sources))
            classified_sources.append(CorpusSource(
                url=cand.url,
                title=cand.title,
                domain=domain_,
                tier=TierLevel.UNKNOWN.value,  # placeholder; back-filled by the batch
                tier_confidence=0.0,
                tier_rule="",
                tier_reasons=[],
                # I-wire-001 W2 (#1311): surface the content-relevance WEIGHT + label
                # per citation (§-1.3). Defaults 1.0/"" when W2 OFF => byte-identical.
                content_relevance_weight=_w2_weight,
                content_relevance_label=_w2_label,
            ))
        else:
            # OFF path: no W5 deferral; clear the W5 evidence-row index so a stale
            # value from a prior ON-path iteration can never leak onto this row.
            _w5_loop_idx = -1
            tier_result = classify_source_tier(signals)

            classified_sources.append(CorpusSource(
                url=cand.url,
                title=cand.title,
                domain=domain_,
                tier=tier_result.tier.value,
                tier_confidence=tier_result.confidence,
                tier_rule=tier_result.matched_rules[0] if tier_result.matched_rules else "",
                tier_reasons=list(tier_result.reasons),
                # I-wire-001 W2 (#1311): surface the content-relevance WEIGHT + label
                # per citation (§-1.3). Defaults 1.0/"" when W2 OFF => byte-identical.
                content_relevance_weight=_w2_weight,
                content_relevance_label=_w2_label,
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
                # I-deepfix-001 (#1344) Codex iter-2 P2: same single predicate as the
                # grounding row + the credibility engine (bool("false") is True — the
                # coercion bug); a string "false"/"0" must not mark the source retracted.
                is_retracted=_retraction_is_truthy(oa, "is_retracted"),
                doi=_jo_doi_resolved,
                venue=oa.get("openalex_venue", "") or "",
            )

        # I-deepfix-001 U21 (T1 fetch-repair): a source whose FIRST fetch returned
        # EMPTY content (ok=False, no body — the doi.org-timeout / anti-bot / paywall
        # total-failure case) never reaches the in-``if content:`` BUG-B02/B04
        # degraded re-fetch, so its ONLY disposition was the disclosed ZERO-weight
        # retention in the ``elif (not ok)`` branch below — RETAINED but with
        # ``direct_quote=""`` so it can NEVER be cited (the autopsy's "8 T1 lost at
        # citation time": AJCN / Food&Function / Br J Derm). REPAIR it with the SAME
        # forced-Zyte re-fetch already used for non-empty degraded rows: on a usable,
        # non-error recovery ADOPT the full text so the row flows through the normal
        # full-text path below and becomes a citable, full-weight source. On a miss it
        # falls through UNCHANGED to the disclosed zero-weight retention (never a
        # silent drop). Gated by the EXISTING default-OFF PG_REFETCH_DEGRADED_VIA_ZYTE
        # flag => byte-identical when OFF. Faithfulness-NEUTRAL: the recovered text is
        # judged by the SAME is_content_starved / _recovered_content_error_class
        # screens the BUG-B02/B04 path uses and then flows through the UNCHANGED
        # strict_verify / NLI / 4-role / provenance engine like any other full-text
        # row (nothing relaxed; ``_u21_repaired`` clears the stale classification-time
        # degraded flag exactly like the BUG-B02/B04 recovered case).
        _u21_repaired = False
        if (not content) and (not ok) and _refetch_degraded_enabled() and not _wall_rescue_mode:
            _u21_recovered = _try_refetch_degraded_row(
                cand.url, DEFAULT_CONTENT_MAX_CHARS,
            )
            if (
                _u21_recovered
                and not is_content_starved(_u21_recovered)
                and not _recovered_content_error_class(_u21_recovered)
            ):
                logger.info(
                    "[live_retriever] U21 EMPTY-FETCH REPAIRED %r (tier=%s "
                    "zyte_len=%d) — failed-fetch source recovered to full text via "
                    "forced Zyte; now a citable full-weight row, NOT retained at "
                    "zero weight.",
                    cand.url, tier_result.tier.value, len(_u21_recovered),
                )
                content = _u21_recovered
                ok = True
                _u21_repaired = True
            else:
                logger.info(
                    "[live_retriever] U21 EMPTY-FETCH REPAIR MISS %r (tier=%s) — "
                    "forced Zyte yielded no usable full text; row stays on the "
                    "disclosed zero-weight retention path (NOT dropped).",
                    cand.url, tier_result.tier.value,
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
            # FIX 2 (I-deepfix-001 composition-collapse plan, #1344): a
            # citation-metadata SHELL (BibTeX/EndNote export nav, site/episode
            # nav, bare title+@article{}) is full-text-incapable exactly like a
            # landing page. Gated by the default-OFF ``PG_CITATION_SHELL_REFETCH``
            # master flag so the OFF path is byte-identical (never computed). Only
            # flagged when NOT already starved / landing so the three signals stay
            # disjoint in the telemetry and a shell joins the SAME §-1.3
            # down-weight (never drop) + forced-Zyte re-fetch disposition below.
            _is_shell = (
                _citation_shell_refetch_enabled()
                and (not _starved)
                and (not _is_landing)
                and _is_citation_metadata_shell(content)
            )
            # I-deepfix-001 (Codex P1 #2): tracks whether the forced re-fetch below upgraded a
            # degraded stub to full text. A recovered row is a NORMAL full-text row, so the stale
            # classification-time ``tier_result.fetch_degraded`` must NOT be propagated onto it
            # (see ``_row_degraded_flags``). Seeded from ``_u21_repaired`` so the U21 empty-fetch
            # REPAIR above (which recovered this now-non-empty body) is likewise treated as a
            # recovered full-text row — the stale degraded flag from its empty-content
            # classification is cleared. Default False => a non-recovered stub keeps its label.
            _refetch_recovered = _u21_repaired
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
            if (
                _starved or _is_landing or _is_shell or not ok
            ) and _refetch_degraded_enabled() and not _wall_rescue_mode:
                _refetched = _try_refetch_degraded_row(
                    cand.url, DEFAULT_CONTENT_MAX_CHARS,
                )
                # I-deepfix-001 (#1344) F4: the recovery test measured LENGTH only
                # (is_content_starved), so a doi.org "DOI Not Found" registry page (~821
                # chars of real English) was ADOPTED as upgraded full text and cited
                # (ev_057). Adopt the recovered span ONLY if it is BOTH non-starved AND not
                # a registry/error/block page — otherwise it falls into the existing
                # degraded branch (row stays a disclosed gap, NOT passed off as full text).
                _recovered_error = (
                    _recovered_content_error_class(_refetched) if _refetched else ""
                )
                if (
                    _refetched
                    and not is_content_starved(_refetched)
                    and not _recovered_error
                ):
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
                    # FIX 2 (#1344): full text adopted — the row is no longer a
                    # citation-metadata shell either, so clear the flag before the
                    # down-weight branch below (a recovered body is full-weight).
                    _is_shell = False
                    # I-deepfix-001 (Codex P1 #2): full text adopted — the row is no longer
                    # degraded, so the stale tier ``fetch_degraded`` is NOT propagated below.
                    _refetch_recovered = True
                elif _refetched and _recovered_error:
                    # The forced Zyte fetch returned a REGISTRY/ERROR/BLOCK page, not the
                    # article — refuse to adopt it (F4). Mark the row degraded so the
                    # UNCHANGED down-weight/skip path below labels + excludes it; it is
                    # NEVER passed off as full text. Distinct warning so the recovered-but-
                    # rejected error page is auditable, never silent.
                    if not _starved and not _is_landing:
                        _starved = True
                    logger.warning(
                        "[live_retriever] B02/B04 RE-FETCH RECOVERED-ERROR-PAGE %r "
                        "(zyte_len=%d class=%s) — forced Zyte returned a registry/error/"
                        "block page, NOT the article; row stays LABELED degraded (NOT "
                        "adopted as full text). §-1.3: a 'not found' page is never a "
                        "corroborator; the source keeps its disclosed-gap disposition.",
                        cand.url, len(_refetched), _recovered_error,
                    )
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
                # I-beatboth-010 (#1288) FIX-A: strip Jina/Crawl4AI reader chrome
                # before building the PERSISTED, cited direct_quote (Codex iter-1
                # P1: this is the evidence_for_gen.direct_quote path). Input hygiene
                # only; full_content_length below keeps the raw fetched length.
                from src.tools.access_bypass import clean_fetch_body
                _cf_quote = clean_fetch_body(content)
                _cleaned_for_quote = _cf_quote.cleaned_text
                # I-beatboth-011 idx49 (#1289): when clean_fetch_body reports the
                # WHOLE cleaned body is a fetch SHELL (boilerplate / soft-404 /
                # Cloudflare or "security check required" interstitial — the junk
                # that leaked through as cited evidence on drb_72), SKIP it the same
                # way the existing content-starved branch above skips a row: trace
                # the drop + count it + `continue` so NO cited evidence row is
                # appended. This guard sits at the TOP of the else so it pre-empts
                # the redesign-ON down-weight-and-KEEP branch below — a down-weighted
                # row is still appended (still emitted as cited evidence), so a
                # confirmed fetch-shell must be dropped, never down-weighted. Mirrors
                # frame_fetcher's METADATA_ONLY gap path (frame_fetcher.py:1098-1105).
                # This consumes the EXISTING `shell_reason` signal and the EXISTING
                # skip mechanism (no new drop/cap/threshold; §-1.3: removes only
                # confirmed fetch-junk, never a real source).
                if _cf_quote.shell_reason:
                    logger.info(
                        "[live_retriever] fetch-shell evidence rejected for %r "
                        "(reason=%s len=%d) → existing skip/gap branch, NOT cited",
                        cand.url, _cf_quote.shell_reason, len(content),
                    )
                    _trace_drop(cand.url, "fetch_shell")
                    drop_reasons["fetch_shell"] += 1
                    continue
                direct_quote = _build_provenance_quote(
                    _cleaned_for_quote, head_chars=_PROVENANCE_HEAD_CHARS_CAP,
                    window_chars=500,
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
                # I-deepfix-001 (Codex P1 #2 — no-laundering): propagate the tier layer's
                # ``fetch_degraded`` label onto the grounded evidence row. A short KNOWN-scholarly-
                # venue / DOI stub keeps its venue-authority TIER (set above) but the tier classifier
                # flagged it ``fetch_degraded=True`` so the adequacy lane must EXCLUDE it from
                # grounded-content counts (``count_grounded_rows``). Previously only ``.tier.value``
                # was copied, so such a stub — not otherwise content_starved/landing_page/fetch_failed
                # — laundered into "adequate" grounded content. Additive-only: absent (byte-identical)
                # when the tier is not degraded. Faithfulness-NEUTRAL (a LABEL, never a claim/span).
                # ``recovered`` guards the BUG-B02/B04 case: a forced re-fetch that upgraded this
                # stub to full text must NOT inherit the stale classification-time degraded flag.
                _row.update(
                    _row_degraded_flags(tier_result, recovered=_refetch_recovered)
                )
                # I-deepfix-001 M2: carry the per-citation document GENRE forward onto the
                # groundable evidence row (mirror of ``.tier``/``.authority_score``) so the
                # weighted-corpus credibility disclosure can build its url->document_type join.
                # Set ONLY when the classifier stamped a non-None genre (i.e. PG_DOCUMENT_TYPE_WEIGHT
                # ON) so an OFF row is byte-identical. Pure placement/disclosure metadata — never
                # enters a verified claim, never relaxes strict_verify / NLI / 4-role (§-1.3).
                if getattr(tier_result, "document_type", None):
                    _row["document_type"] = tier_result.document_type
                # I-deepfix-001 (#1344) DEFER-1: carry the W2 content-relevance LABEL
                # (and its weight) onto the groundable evidence row so the cite-surface
                # off-topic suppression (weighted_enrichment._is_confirmed_offtopic) can
                # read the SEMANTIC confirmed-OFF verdict the W2 judge produced. The label
                # already rides on CorpusSource (classified_sources); this surfaces it on
                # the row the GENERATOR reads. Set ONLY when the label is non-empty (W2 ON
                # with a real disposition) so a W2-OFF / unlabelled row is byte-identical.
                # Pure placement/relevance metadata — never enters a verified claim, never
                # relaxes strict_verify / NLI / 4-role (§-1.3 disclose-don't-drop).
                if _w2_label:
                    _row["content_relevance_label"] = _w2_label
                    _row["content_relevance_weight"] = _w2_weight
                # I-deepfix-001 B10(b) (#1352): carry the publication year FORWARD.
                # `year` is the key the evidence_selector recency path already reads
                # (_row_year at evidence_selector.py:805) AND the B10(d) date-window
                # demotion reads; `publication_year` is the explicit audit field.
                # ABSENT when OpenAlex returned no year => an undated row, never
                # demoted downstream (fail-open). Never enters a verified claim.
                if _pub_year is not None:
                    _row["year"] = _pub_year
                    _row["publication_year"] = _pub_year
                # Codex wave-2 P1: carry the full publication_date for MONTH-precision
                # date-window enforcement at selection. ABSENT => year-precision
                # fallback (never demoted on a missing/malformed date — fail-open).
                if _pub_date is not None:
                    _row["pub_date"] = _pub_date
                # I-deepfix-001 (#1344) Bug B: carry the OpenAlex retraction flag
                # FORWARD onto the groundable evidence row so the generator's retraction
                # grounding gate (retraction_gate.partition_pool) can EXCLUDE a
                # retracted/withdrawn study from grounding BEFORE composition. The same
                # flag already feeds the journal_only sidecar (is_retracted at the
                # `_jo_meta_entry` call above) and the credibility supersession penalty —
                # this carries it onto the row the GENERATOR reads. Set ONLY when True so
                # a non-retracted row is byte-identical (fail-open: absent => not
                # retracted). Placement/credibility metadata; never enters a verified
                # claim, never relaxes strict_verify / NLI / 4-role (§-1.3: the one hard
                # exclusion is the faithfulness/credibility-safety gate, not a breadth cap).
                # I-deepfix-001 U10 (Codex P1): forward BOTH legs — the OpenAlex flag AND
                # the tier classifier's R0_retracted rule (which also catches a TITLE-ONLY
                # retraction/withdrawal marker whose OpenAlex flag was unset, e.g. a
                # retracted paper re-deposited on a preprint host). Keying on the OpenAlex
                # flag alone let a title-marker retracted paper ground prose; see
                # _row_is_retracted.
                if _row_is_retracted(oa, tier_result):
                    _row["is_retracted"] = True
                # I-deepfix-001 B14 (#1358): carry the title<->body identity flags so
                # the generator/dedup can avoid reasoning about a mis-stitched source
                # under two identities. Keys ABSENT when the gate is OFF => the OFF
                # evidence row is byte-identical. Never a drop; faithfulness-neutral.
                if _tb_verdict is not None:
                    _row.update(
                        title_body_consistency.consistency_keys(_tb_verdict)
                    )
                    # I-deepfix-001 (#1344): on a confirmed title<->body mismatch,
                    # correct the row's DISPLAY title to the body-derived one so the
                    # bibliography points a reader at the ACTUAL fetched document, not
                    # the mis-stitched metadata title (the [105] English-title /
                    # Romanian-body fault). The original metadata_title is preserved in
                    # the keys above for audit. Faithfulness-STRENGTHENING; never a drop.
                    if (
                        not _tb_verdict.identity_consistent
                        and _tb_verdict.resolved_title
                    ):
                        _row["source_title"] = _tb_verdict.resolved_title
                        _row["title"] = _tb_verdict.resolved_title
                # I-wire-001 W5 (Codex P1#1): when LLM-tiering is ON, the `_row["tier"]`
                # written above is the rules-floor PLACEHOLDER. Record this evidence
                # row's position in the deferred-tier batch so the post-loop
                # bounded-parallel LLM-tiering step can back-fill it with the real LLM
                # tier — otherwise the W5 winner reaches classified_sources but NOT the
                # evidence row the generator actually reads (ev.get("tier")), silently
                # no-opping in report.md. ABSENT on the OFF path => byte-identical.
                if _llm_tiering_on and _w5_loop_idx >= 0:
                    _row["_w5_tier_batch_idx"] = _w5_loop_idx
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
                # FIX 2 (#1344): a citation-metadata SHELL joins the SAME §-1.3
                # down-weight (kept-at-low-weight, NEVER dropped) disposition as a
                # landing page — it is likewise full-text-incapable. ``_is_shell``
                # is already False whenever ``PG_CITATION_SHELL_REFETCH`` is OFF, so
                # the OFF path stays byte-identical.
                if _redesign_on and (_starved or _is_landing or _is_shell):
                    _dw = _down_weight_retrieval()
                    _row["retrieval_weight"] = _dw
                    _row["down_weighted"] = True
                    if _starved:
                        _row["content_starved"] = True
                    if _is_landing:
                        # methods/results cannot be grounded on a landing page.
                        _row["landing_page"] = True
                        _row["full_text_capable"] = False
                    if _is_shell:
                        # a citation-export / nav / bare-BibTeX shell carries no
                        # article prose — it cannot ground a claim.
                        _row["citation_metadata_shell"] = True
                        _row["full_text_capable"] = False
                    logger.info(
                        "[live_retriever] DOWN-WEIGHT evidence for %r "
                        "(len=%d starved=%s landing=%s shell=%s weight=%.3f) — kept "
                        "in the pool at low weight, NOT dropped (§-1.3)",
                        cand.url, len(content), _starved, _is_landing, _is_shell, _dw,
                    )
                    _trace_drop(cand.url, "down_weighted")
                    drop_reasons["down_weighted"] += 1
                    if _starved:
                        drop_reasons["content_starved"] += 1
                    if _is_landing:
                        drop_reasons["landing_page"] += 1
                    if _is_shell:
                        drop_reasons["citation_metadata_shell"] += 1
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
        elif (not ok) and _credibility_redesign_enabled():
            # FIX-3 piece 3 (I-deepfix-001, §-1.3 STOP THE SILENT HARD-DROP):
            # a `not ok` candidate with EMPTY content (the doi.org-timeout →
            # naive-paywall → empty-body case) never reaches the `if content:`
            # block above, so the ONLY evidence_rows.append site is skipped and
            # the source is SILENTLY HARD-DROPPED — a high-credibility failed
            # academic DOI vanishes while a low-tier source that fetched fine is
            # kept (credibility inversion). The existing F30 down-weight-and-keep
            # path also lives inside `if content:`, so it does NOT cover the
            # empty-content case. Under the EXISTING redesign flag, RETAIN the
            # source as a DISCLOSED zero-weight row instead of dropping it
            # (§-1.3 WEIGHT-not-FILTER / disclose-don't-drop). This is the
            # `else`-of-`if content:` seam where `tier_result`/`signals`/
            # `classifier_title` are already bound for EVERY candidate
            # (computed unconditionally above, ~L5177/L5234/L5254), so the branch
            # references only locals valid at this scope.
            #
            # FAITHFULNESS-SAFE BY CONSTRUCTION: the row carries `direct_quote=""`
            # AND sets NO `statement`, so the provenance generator's grounding
            # fallback (`ev.get("direct_quote") or ev.get("statement") or ""` at
            # provenance_generator.py:1480) yields "" → `return None`: the row can
            # NEVER be selected to ground a claim, NEVER be cited, NEVER feed or
            # relax strict_verify / NLI / 4-role / span-grounding. It is disclosed
            # corpus metadata only. `retrieval_weight=0.0` is read by the SOLE
            # consumer `evidence_selector._retrieval_weight` as
            # `1.0 if w is None else float(w)` (NOT an `or`-default — 0.0 is
            # preserved, sorts the row LAST), and no other consumer `or`-launders
            # it (grep-verified). OFF path (redesign flag unset) → this elif is
            # never entered → byte-identical legacy hard-drop.
            _row0: dict[str, Any] = {
                "evidence_id": f"ev_{i:03d}",
                "source_url": cand.url,
                # NO `statement` key — see grounding note above.
                "title": classifier_title or cand.title or "",
                "direct_quote": "",
                "tier": tier_result.tier.value,
                "source": cand.source,
                "full_content_length": 0,
                "retrieval_weight": 0.0,
                "down_weighted": True,
                "fetch_failed": True,
                "full_text_capable": False,
                "query_origin": getattr(cand, "query_origin", "") or "",
            }
            if _pub_year is not None:
                _row0["year"] = _pub_year
                _row0["publication_year"] = _pub_year
            if research_frame is not None:
                _auth0 = score_source_authority(signals)
                _row0["authority_score"] = float(_auth0.authority_score)
                _row0["authority_confidence"] = _auth0.authority_confidence.value
            # I-deepfix-001 M2: carry the document GENRE on the disclosed zero-weight row too
            # (set ONLY when the classifier stamped one => PG_DOCUMENT_TYPE_WEIGHT ON; OFF row
            # byte-identical). Disclosure metadata only; this row already carries direct_quote=""
            # so it can never ground a claim (the faithfulness engine is untouched).
            if getattr(tier_result, "document_type", None):
                _row0["document_type"] = tier_result.document_type
            evidence_rows.append(_row0)
            logger.info(
                "[live_retriever] §-1.3 RETAIN failed-fetch source at ZERO weight "
                "for %r (tier=%s) — DISCLOSED (weight=0.0, fetch_failed=True, "
                "direct_quote='' so it can never ground a claim), NOT silently "
                "dropped",
                cand.url, tier_result.tier.value,
            )
            # DISCLOSED zero-weight retention is a KEEP, not a drop (§-1.3).
            _trace_kept(cand.url, cand.source)

    # I-wire-001 W5 (PG_CREDIBILITY_LLM_TIERING): bounded-parallel per-source LLM-tiering
    # post-step. Runs ONCE over every deferred source via a ThreadPoolExecutor capped by
    # PG_TIER_LLM_WORKERS; order-independent (gather-then-sort by index) so concurrency
    # never changes a per-source tier. The rules-floor is the instant fallback on any
    # judge_error/timeout. Tier is a WEIGHT, never a drop — every row keeps its slot and
    # only its tier fields are back-filled. OFF path never enters here (list is empty).
    # I-deepfix-001 D5 (#1344): default empty status; the W5 block (LLM-tiering ON, with
    # deferred sources) reassigns it with the real machine-readable batch mode below. The OFF
    # path (or no deferred sources) keeps {} so the manifest disclosure carries an honest
    # "tiering did not run" rather than a misleading absent/None field.
    _credibility_tiering_status: dict[str, Any] = {}
    if _llm_tiering_on and _deferred_tier_signals:
        from src.polaris_graph.retrieval.credibility_llm_tiering import (
            classify_sources_llm_tiering,
        )

        logger.info(
            "[live_retriever] PG_CREDIBILITY_LLM_TIERING ON — bounded-parallel LLM "
            "tiering over %d sources",
            len(_deferred_tier_signals),
        )
        # I-deepfix-001 (wall/tiering-abort fix, #1344): give the post-fetch W5 tiering
        # batch its OWN fetch-INDEPENDENT budget instead of the retrieval wall. When slow
        # web-fetch consumed the retrieval wall, threading the already-EXPIRED
        # `_retrieval_deadline` here made the batch trip its very FIRST futures_wait
        # (deadline already in the past) -> llm_success=0 -> tiering_mode=rules_floor_degraded
        # -> every source stuck at the T4-skewing deterministic rules-floor -> corpus_approval
        # counted those placeholder tiers -> FALSE material_deviation -> abort. Credibility
        # tiering is a WEIGHT that must COMPLETE over every fetched source BEFORE the
        # approval decision (§-1.3); the fetch wall must not starve it. Passing
        # `deadline_monotonic=None` lets `_run_llm_tiering_parallel` anchor a FRESH wall at
        # `now + PG_TIER_LLM_BATCH_WALL_SECONDS` (default 600s) — a guaranteed budget AFTER
        # the fetch wall tripped. This CANNOT hang: the batch is still self-bounded by the
        # in-flight worker cap (PG_TIER_LLM_WORKERS), its own total wall
        # (PG_TIER_LLM_BATCH_WALL_SECONDS), the consecutive-fallback circuit-breaker
        # (PG_TIER_LLM_DEGRADE_AFTER — a blank-200/trickle storm short-circuits fast), and a
        # non-blocking pool teardown, so the original "don't grind past the wall" goal is
        # still met by the batch's OWN wall. No source is dropped: an un-returned straggler
        # still keeps its deterministic rules-floor tier (a WEIGHT, §-1.3).
        _tier_results = classify_sources_llm_tiering(
            _deferred_tier_signals,
            deadline_monotonic=None,
        )
        # I-deepfix-001 D5 (#1344): capture the honest machine-readable batch status off the
        # TieringBatchResult so it survives to the durable manifest credibility disclosure
        # (the diced preflight's D5 gate reads tiering_mode here). Default {} if the producer
        # ever returns a bare list (defensive getattr) — never breaks the WEIGHT-only path.
        _credibility_tiering_status = getattr(_tier_results, "tiering_status", {})
        for _row_idx, _tier_result in zip(_deferred_tier_row_idx, _tier_results):
            _src = classified_sources[_row_idx]
            _src.tier = _tier_result.tier.value
            _src.tier_confidence = _tier_result.confidence
            _src.tier_rule = (
                _tier_result.matched_rules[0] if _tier_result.matched_rules else ""
            )
            _src.tier_reasons = list(_tier_result.reasons)
        # Codex P1#1: also back-fill the EVIDENCE rows (the surface the generator
        # reads via ev.get("tier")) with the LLM tier — keyed by the batch index each
        # row recorded at build time. The rules-floor placeholder is REPLACED by the
        # real W5 tier here, so the winner fires in report.md (not just on
        # classified_sources). The temporary `_w5_tier_batch_idx` key is popped so it
        # never leaks into the persisted/manifest evidence row.
        for _ev_row in evidence_rows:
            _ev_batch_idx = _ev_row.pop("_w5_tier_batch_idx", None)
            if _ev_batch_idx is not None and 0 <= _ev_batch_idx < len(_tier_results):
                _ev_row["tier"] = _tier_results[_ev_batch_idx].tier.value

    # ── W2 surfacing re-rank (I-wire-001 #1311) ────────────────────────
    # So the content-relevance effect APPEARS in the rendered output (not only a
    # manifest dict): when W2 is ON, STABLE-sort classified_sources by relevance
    # weight DESC so demoted (off-topic/junk) sources rank BELOW full-weight
    # evidence in the corpus ordering the downstream selection/render reads. This
    # is a REORDER only (parallel to W3's WRRF) — NO source is added or dropped,
    # the set is identical, and strict_verify re-checks every row regardless of
    # order (§-1.3 faithfulness-neutral). OFF => no reorder => byte-identical.
    # Runs AFTER the W5 tier back-fill so the reorder reflects final tier state.
    if _w2_on and classified_sources:
        classified_sources = sorted(
            classified_sources,
            key=lambda s: -getattr(s, "content_relevance_weight", 1.0),
        )

    # I-deepfix-001 item 4 (#1344): if the retrieval wall tripped in EITHER phase,
    # DISCLOSE the partial cutoff on the manifest channel (`notes`) so the §-1.3
    # "never silently drop, always disclose" requirement is satisfied within this
    # file's boundary (notes reaches telemetry; the structured `retrieval_wall_hit`
    # field below is a sibling). `_candidates_unclassified` = the fetched bodies the
    # post-fetch loop did not reach before the wall (0 when the wall tripped only in
    # the search phase, where all gathered candidates were still classified).
    _candidates_unclassified = max(0, len(candidates) - _candidates_processed)
    if _retrieval_wall_hit:
        _wall_note = (
            f"retrieval_wall_hit: PARTIAL retrieval — wall "
            f"({_retrieval_wall_seconds():.0f}s, PG_RETRIEVAL_WALL_SECONDS) tripped; "
            f"{_queries_skipped_wall} planned sub-queries unfired and "
            f"{_candidates_unclassified} fetched bodies unclassified — DISCLOSED, "
            f"NOT dropped; handed off {len(classified_sources)} classified sources "
            f"to render (render-PASS partial, NOT corpus_truncated)"
        )
        logger.warning("[live_retriever] %s", _wall_note)
        notes.append(_wall_note)

    # WAVE-2 Fix B (#1344): disclose the wall-rescue on the manifest channel so the
    # §-1.3 "never silently drop, always disclose" requirement holds — the bodies
    # the wall would have dropped were classified RULES-ONLY and KEPT.
    if _wall_rescue_mode:
        _rescue_note = (
            f"wall_classify_rescue: PG_WALL_CLASSIFY_RESCUE engaged — "
            f"{_wall_rescued_count} already-fetched bodies classified RULES-ONLY "
            f"(rules-floor tier, no enrich/LLM) past the retrieval wall and KEPT in "
            f"the corpus for the CRAG reserve (§-1.3 keep-not-drop; faithfulness "
            f"engine untouched)"
        )
        logger.info("[live_retriever] %s", _rescue_note)
        notes.append(_rescue_note)

    # FIX-3 piece 1 (I-deepfix-001): bounded end-of-run drain of abandoned bypass
    # workers. Fires ONCE per run on BOTH the parallel and serial fetch paths
    # (this is reached just before the single return). Reclaims cooperatively-
    # finishable abandoned workers within PG_BYPASS_DRAIN_SECONDS so the registry
    # cannot grow unbounded across questions in a long-lived UI/server process,
    # and surfaces the LIVE leak gauge (residual still-alive workers — typically
    # C-wedged Playwright workers that cannot be joined in-process) alongside the
    # existing CUMULATIVE gauge. Telemetry-only + fail-safe: a drain error never
    # breaks retrieval.
    try:
        from src.tools.access_bypass import (
            bypass_live_leaked_count,
            drain_bypass_workers,
        )
        api_calls["bypass_live_leaked_count_pre_drain"] = bypass_live_leaked_count()
        api_calls["bypass_live_leaked_count_post_drain"] = drain_bypass_workers()
    except Exception:  # noqa: BLE001 — telemetry only; never break retrieval
        pass

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
        # I-deepfix-001 item 4 (#1344): retrieval-wall partial-handoff telemetry.
        retrieval_wall_hit=_retrieval_wall_hit,
        retrieval_queries_skipped=_queries_skipped_wall,
        retrieval_candidates_unclassified=_candidates_unclassified,
        # I-deepfix-001 P1-2 (#1344): B4 semantic->lexical fallback disclosure.
        semantic_relevance_fell_back=_semantic_relevance_fell_back,
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
        # I-wire-001 W2 (#1311): content-relevance judge telemetry (None when W2
        # OFF => byte-identical). DISTINCT key from relevance_gate above.
        content_relevance=(
            _w2_report.to_dict() if _w2_report is not None else None
        ),
        # Codex diff-gate iter-1 P1: freeze the extraction-stage count HERE (at
        # return), before run_one_query mutates evidence_rows via the expansion/
        # deepener/agentic lanes.
        extraction_finding_rows=len(evidence_rows),
        # I-deepfix-001 D5 (#1344): honest credibility-tiering batch status (tiering_mode /
        # llm_success_count / rules_floor_count / ...) -> durable manifest disclosure. {} on
        # the OFF path (W5 never ran) => byte-identical.
        credibility_tiering_status=_credibility_tiering_status,
        # I-deepfix-001 (wall/tiering-abort fix, #1344) P1a: fetch-SUBWALL disclosure —
        # SEPARATE from retrieval_wall_hit. False/0 on the byte-identical OFF path
        # (fraction=1.0 / serial fallback / no candidates).
        fetch_subwall_hit=_fetch_subwall_hit,
        fetch_subwall_timeout_count=_fetch_subwall_timeout,
        fetch_subwall_not_dispatched_count=_fetch_subwall_not_dispatched,
    )
