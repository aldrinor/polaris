"""M-56 (2026-04-23): V30 deterministic frame fetcher.

V30 Report Contract Architecture Layer 2b. Replaces Serper/S2
non-deterministic keyword retrieval for known-identifier entities
with three deterministic, free, never-paywalled APIs:

  1. CrossRef `/works/{doi}` — metadata (title, authors, abstract, year)
  2. Unpaywall `/v2/{doi}`   — OA PDF URL if an OA version exists
  3. PubMed EFetch (pmid)    — deterministic abstract XML when
                                full-text paywalled.

V28/V29 showed that keyword retrieval via Serper/S2 was the primary
cause of V30 Defect A (non-determinism). Same M-48 variant queries
landed different primary sets across runs. M-56 bypasses keyword
retrieval entirely for known-DOI entities — given the same DOI the
retriever emits a byte-identical FrameRow.

## Layered architecture

The module has four distinct layers. Tests exercise them separately
to isolate network dependency:

  Layer 1: Pure data types (FrameRow, ProvenanceClass, RetrievalAttempt).
  Layer 2: Pure parsers (_parse_crossref_response, _parse_unpaywall_response,
           _parse_pubmed_xml). Given raw API response, return structured
           fields.
  Layer 3: Network callers (_call_crossref, _call_unpaywall, _call_pubmed)
           with bounded retry + fixed timeout + status-code-to-outcome
           mapping.
  Layer 4: Orchestrator (fetch_frame_entity) which dispatches by
           primary_identifier and composes FrameRow.

## Dependency injection for testability

`fetch_frame_entity(binding, *, client=None, ...)` accepts an
optional httpx.Client. Production callers pass None (module creates
one per call); tests pass a fake client that returns canned
responses. No test needs monkey-patching of module globals.

## Codex V30 plan pass-1 revision #4 (M-60 manifest metadata)

Every fetch attempt — success or failure — is logged into
FrameRow.retrieval_attempts: list of RetrievalAttempt(source, url,
status, duration_ms, outcome). M-60 manifest rendering consumes this
log to explain exactly what the pipeline tried for every slot that
ended up in frame_gap_unrecoverable state.

## Determinism contract

Given the same (binding, same upstream API responses), the same
FrameRow is emitted. Specifically:
  - No wall-clock reads other than duration measurement (which is
    logged but does not affect the FrameRow payload proper).
  - No randomness in retry backoff (fixed 1s/2s/4s schedule).
  - Sort order within parsed fields is explicit.
  - direct_quote is deterministic given inputs.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from ..nodes.frame_compiler import EvidenceBinding
from src.tools.core_client import fetch_core_oa_fulltext

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Layer 1 — Pure data types
# ─────────────────────────────────────────────────────────────────────
class ProvenanceClass(str, Enum):
    """Provenance of the content captured in FrameRow.direct_quote.

    open_access: full OA text retrieved (preferred; richest for M-58
      slot-fill).
    abstract_only: abstract text available (from CrossRef or PubMed);
      full-text paywalled.
    metadata_only: title/authors/year known but no abstract text.
      Can still surface structured citation but M-58 will emit
      `not_extractable` for most required_fields.
    frame_gap_unrecoverable: all three sources failed; no locator
      resolved anything. M-60 will emit explicit gap sentence.
    human_curated: content supplied by M-61 operator via the
      hybrid-completion Path B. PERMANENT marker — downstream
      rendering MUST surface the human-curated flag in every
      citation + Methods disclosure. M-61 supplies the
      StructuredProvenance audit evidence separately via
      FrameRow.human_curated_provenance.
    """

    OPEN_ACCESS = "open_access"
    ABSTRACT_ONLY = "abstract_only"
    METADATA_ONLY = "metadata_only"
    FRAME_GAP_UNRECOVERABLE = "frame_gap_unrecoverable"
    HUMAN_CURATED = "human_curated"


@dataclass(frozen=True)
class RetrievalAttempt:
    """One network attempt log entry — EXACTLY ONE PER HTTP REQUEST
    (not per source). Codex M-56 audit Blocker 2: retry chains must
    be fully visible so M-60 manifest can show exactly what was
    tried.

    Deterministic fields only — `duration_ms` lives in
    RetrievalTiming so FrameRow payload equality is meaningful.
    """

    source: str           # "crossref" | "unpaywall" | "pubmed"
    url: str              # full requested URL including query params
    attempt_index: int    # 1-based per-source counter (1, 2, 3 = retry 1, 2, 3)
    http_status: int | None  # None on network-level failure
    outcome: str          # "success" | "not_found" | "error:<short>"
                          # | "retryable_http_<code>" | "retryable_network:<cls>"


@dataclass(frozen=True)
class RetrievalTiming:
    """Per-attempt timing, separated from RetrievalAttempt so
    FrameRow.retrieval_attempts stays byte-deterministic across
    runs. Codex M-56 audit Blocker 1."""

    source: str
    attempt_index: int
    duration_ms: int


@dataclass(frozen=True)
class FrameRow:
    """Output of M-56 frame_fetcher. One row per required entity.

    Maps to existing POLARIS evidence shape (entity_id, direct_quote,
    url) so M-57/M-58/M-59 can consume it alongside non-frame
    evidence rows.
    """

    entity_id: str
    entity_type: str
    rendering_slot: str
    provenance_class: ProvenanceClass
    direct_quote: str           # empty when gap
    quote_source: str           # "crossref_abstract" | "openalex_abstract"
                                # | "pubmed_abstract" | "oa_full_text"
                                # | "core_oa_fulltext" (legal CORE OA fetch,
                                #   I-faith-002) | "url_pattern_fetch"
                                # | "url_pattern_placeholder" | "none"
    # Resolved locators (may be empty for gap rows)
    doi: str | None
    pmid: str | None            # string form to handle both int/str inputs
    oa_pdf_url: str | None
    url: str | None             # for regulatory url_pattern entities
    # Metadata where available
    title: str | None
    authors: tuple[str, ...]
    journal: str | None
    year: int | None
    # Failure metadata (only populated on gap)
    failure_reason: str | None
    # Audit log — deterministic payload: one RetrievalAttempt per
    # HTTP request (retry chain fully expanded). Codex M-56 audit
    # Blocker 2.
    retrieval_attempts: tuple[RetrievalAttempt, ...] = field(
        default_factory=tuple
    )
    # Per-attempt timing, non-deterministic (wall-clock-derived).
    # Lives outside the determinism-comparable payload per Codex
    # M-56 audit Blocker 1. Correlated to retrieval_attempts via
    # (source, attempt_index).
    retrieval_timings: tuple[RetrievalTiming, ...] = field(
        default_factory=tuple
    )
    # M-61 structured provenance for human-curated rows. None for
    # rows with provenance_class != HUMAN_CURATED. Dict shape —
    # NOT a typed StructuredProvenance reference — to avoid
    # circular import between frame_fetcher and
    # human_gap_completion. Callers can round-trip via
    # StructuredProvenance.from_dict when needed. Codex M-61
    # audit Blocker 3 fix.
    human_curated_provenance: dict[str, str] | None = None

    def is_gap(self) -> bool:
        return self.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE


# ─────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────
_CROSSREF_BASE = "https://api.crossref.org/works/"
_UNPAYWALL_BASE = "https://api.unpaywall.org/v2/"
_PUBMED_EFETCH_BASE = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
)
# OpenAlex /works/{doi} — issue #1033 abstract fallback. When CrossRef
# carries no abstract and the OA full-text PDF is paywalled (403),
# OpenAlex's abstract_inverted_index reliably holds the abstract for
# indexed journal DOIs. DOI-driven; deterministic.
_OPENALEX_WORK_BASE = "https://api.openalex.org/works/"
_OPENALEX_FRAME_FALLBACK_ENABLED = (
    os.getenv("PG_OPENALEX_FRAME_FALLBACK", "1").strip().lower()
    not in ("0", "false", "no", "off")
)
# Semantic Scholar Graph API /paper/DOI:{doi} — M3b (I-deepfix-001) 3rd deterministic
# abstract source. For a closed-access primary whose CrossRef/OpenAlex abstract is a
# degenerate fragment (or a single transient throttle leaves it empty), S2 carries a
# full abstract for most indexed DOIs. DOI-driven; deterministic; abstract is the honest
# reachable ceiling for a paywalled primary (NO full-text, NO Sci-Hub).
_S2_WORK_BASE = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
# Minimum chars for an OA full-text fetch to count as REAL full text
# (issue #1034). Paywalled-PDF stubs (e.g. aeaweb via Jina ~540 chars)
# fall below this -> they must not block the abstract fallbacks and
# must lose to a real abstract (e.g. OpenAlex 1331 chars).
_OA_FULLTEXT_MIN_CHARS = int(os.getenv("PG_OA_FULLTEXT_MIN_CHARS", "1200"))
# Prefer the clean, deterministic abstract (CrossRef/OpenAlex/PubMed) over a
# scraped OA "full text" for frame-contract grounding (#1034). Ground-truthed:
# paywalled-journal OA fetches are NON-DETERMINISTIC (Sci-Hub HTML one call,
# Jina landing-page markdown the next, clean CrossRef abstract a third) and
# noisy, while the abstract is clean and stable — and contract fields
# (thesis/mechanism/effect) are abstract-level claims. Default OFF preserves
# the M-66b-T clinical full-text path (multi-field trial rosters live in
# tables, not abstracts); run_gate_b sets it ON for the benchmark.
_FRAME_PREFER_ABSTRACT = (
    os.getenv("PG_FRAME_PREFER_ABSTRACT", "0").strip().lower()
    in ("1", "true", "yes", "on")
)
# Entity types whose contract fields live in full-text TABLES (clinical trial
# 9-field rosters etc.) KEEP the OA full-text path even under prefer-abstract,
# so Gate-B gold-rubric coverage for clinical questions is preserved (dual-audit
# #1034 P1). Narrative entity types (economic_report, ...) prefer the clean
# abstract AND skip the scrape entirely (no non-deterministic fetch, no Sci-Hub
# request).
_FULLTEXT_ENTITY_TYPES = frozenset(
    t.strip().lower()
    for t in os.getenv(
        "PG_FRAME_FULLTEXT_ENTITY_TYPES",
        "pivotal_trial,clinical_trial,rct,systematic_review,meta_analysis",
    ).split(",")
    if t.strip()
)

def _frame_multi_abstract_enabled() -> bool:
    """M3b (I-deepfix-001) gather-all-then-pick-richest toggle (default ON).

    When ON, the deterministic abstract sources (OpenAlex, and Semantic Scholar
    below) are consulted for a DOI EVEN WHEN CrossRef/PubMed already returned an
    abstract, so the RICHEST abstract wins via ``_pick_richest_abstract`` instead
    of a degenerate first-source fragment short-circuiting the gather. Read at
    CALL TIME so a test/operator can flip ``PG_FRAME_MULTI_ABSTRACT`` after import
    (same pattern as ``_core_enabled``). OFF restores the legacy
    ``not abstract_crossref and not abstract_pubmed`` short-circuit byte-identically.
    """
    return os.getenv("PG_FRAME_MULTI_ABSTRACT", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _frame_s2_abstract_enabled() -> bool:
    """M3b (I-deepfix-001) Semantic Scholar Graph API 3rd abstract source toggle
    (default ON). Read at CALL TIME. OFF removes the S2 source entirely so the
    abstract gather is byte-identical to the pre-M3b CrossRef/OpenAlex/PubMed set."""
    return os.getenv("PG_FRAME_S2_ABSTRACT", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _core_enabled() -> bool:
    """CORE (core.ac.uk) legal OA full-text fetch toggle (I-faith-002).

    Read at CALL TIME (not as an import-time module constant) so a test
    or operator can flip ``PG_CORE_ENABLED`` with a plain
    ``monkeypatch.setenv`` / env change after import and have it take
    effect. Default "1" (on): CORE is the legal full-text source that
    replaced the now-disabled Sci-Hub path. Set "0" to disable.
    """
    return os.getenv("PG_CORE_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


_DEFAULT_TIMEOUT = float(os.getenv("PG_FRAME_FETCHER_TIMEOUT", "15"))
_MAX_RETRIES = int(os.getenv("PG_FRAME_FETCHER_MAX_RETRIES", "3"))
# Fixed backoff schedule; deterministic (no jitter).
_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)

_POLARIS_UA = os.getenv(
    "PG_HTTP_USER_AGENT",
    "POLARIS-research-pipeline/30.1 (mailto:polaris@example.org)",
)


# ─────────────────────────────────────────────────────────────────────
# Layer 2 — Pure parsers
# ─────────────────────────────────────────────────────────────────────
def _parse_crossref_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields from CrossRef /works/{doi} JSON.

    Returns dict with keys: title, authors, journal, year, abstract,
    doi (normalized). Values may be None/empty when not present in
    the response."""
    msg = data.get("message", {}) if isinstance(data, dict) else {}
    title_list = msg.get("title") or []
    title = title_list[0].strip() if title_list else None

    authors_raw = msg.get("author") or []
    authors: list[str] = []
    for a in authors_raw:
        if not isinstance(a, dict):
            continue
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if family and given:
            authors.append(f"{family} {given[0]}".strip())
        elif family:
            authors.append(family)

    container = msg.get("container-title") or []
    journal = container[0].strip() if container else None

    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        dp = msg.get(key) or {}
        parts = dp.get("date-parts") or []
        if parts and parts[0]:
            try:
                year = int(parts[0][0])
                break
            except (ValueError, TypeError):
                continue

    abstract = msg.get("abstract") or None
    if isinstance(abstract, str):
        # CrossRef abstracts often carry JATS XML tags; strip the
        # outer <jats:p>...</jats:p> but keep text content.
        abstract = _strip_jats_tags(abstract)

    doi = (msg.get("DOI") or "").strip() or None

    return {
        "title": title,
        "authors": tuple(authors),
        "journal": journal,
        "year": year,
        "abstract": abstract,
        "doi": doi,
    }


def _parse_unpaywall_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract OA status + best OA PDF URL from Unpaywall response."""
    if not isinstance(data, dict):
        return {"is_oa": False, "oa_pdf_url": None, "oa_html_url": None}

    is_oa = bool(data.get("is_oa"))
    best = data.get("best_oa_location") or {}
    oa_pdf_url = (
        best.get("url_for_pdf") if isinstance(best, dict) else None
    ) or None
    oa_html_url = (
        best.get("url_for_landing_page") if isinstance(best, dict) else None
    ) or None

    return {
        "is_oa": is_oa,
        "oa_pdf_url": oa_pdf_url,
        "oa_html_url": oa_html_url,
    }


def _parse_pubmed_xml(xml_text: str) -> dict[str, Any]:
    """Extract abstract text + metadata from PubMed EFetch XML.

    Handles the standard <PubmedArticleSet>/<PubmedArticle>/<MedlineCitation>
    structure. When the XML is malformed or empty, returns an empty
    dict (caller treats as not_found)."""
    if not isinstance(xml_text, str) or not xml_text.strip():
        return {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    # Abstract is under Article/Abstract/AbstractText (may be multiple)
    abstract_parts: list[str] = []
    for at in root.iter("AbstractText"):
        label = at.get("Label")
        text = (at.text or "").strip()
        if label and text:
            abstract_parts.append(f"{label}: {text}")
        elif text:
            abstract_parts.append(text)
    abstract = " ".join(abstract_parts) if abstract_parts else None

    title_elt = next(root.iter("ArticleTitle"), None)
    title = (title_elt.text or "").strip() if title_elt is not None else None

    journal_elt = next(root.iter("Title"), None)  # Journal/Title
    journal = (journal_elt.text or "").strip() if journal_elt is not None else None

    year = None
    year_elt = next(root.iter("Year"), None)
    if year_elt is not None and year_elt.text:
        try:
            year = int(year_elt.text.strip())
        except ValueError:
            year = None

    authors: list[str] = []
    for a in root.iter("Author"):
        last = (a.findtext("LastName") or "").strip()
        init = (a.findtext("Initials") or "").strip()
        if last and init:
            authors.append(f"{last} {init[0]}")
        elif last:
            authors.append(last)

    # V30 Phase-2 sweep run-1 root cause: stale/wrong PMID in the
    # contract YAML (e.g. PMID 34010531 bound to surpass_2_primary
    # actually points at the SPRINT blood-pressure trial, not the
    # Frias tirzepatide paper). The extractor passed anti-fabrication
    # because SPRINT prose WAS verbatim in the abstract we fetched.
    # Defense: pull PubMed's own DOI (`<ELocationID EIdType="doi">`)
    # so the caller can cross-check against the bound DOI and reject
    # mismatches rather than render wrong content.
    pubmed_doi: str | None = None
    for el in root.iter("ELocationID"):
        if el.get("EIdType") == "doi" and el.text:
            pubmed_doi = el.text.strip().lower()
            break
    # PMID itself (for round-trip consistency checks).
    pmid_elt = next(root.iter("PMID"), None)
    pubmed_pmid = (
        pmid_elt.text.strip() if pmid_elt is not None and pmid_elt.text
        else None
    )

    return {
        "title": title,
        "authors": tuple(authors),
        "journal": journal,
        "year": year,
        "abstract": abstract,
        "doi": pubmed_doi,
        "pmid": pubmed_pmid,
    }


def _reconstruct_inverted_abstract(inverted_index: Any) -> str | None:
    """Reconstruct a plain-text abstract from an OpenAlex
    `abstract_inverted_index` ({word: [pos, ...]}). Deterministic:
    positions are unique within a work, so sort-by-position is a
    total order -> same input yields byte-identical text.

    Kept local (mirrors the proven reconstruction in
    agents/searcher.py) so frame_fetcher stays free of the
    non-deterministic keyword-retrieval stack per its module
    determinism contract."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, (list, tuple)):
            continue
        for pos in positions:
            if isinstance(pos, int):
                word_positions.append((pos, word))
    if not word_positions:
        return None
    word_positions.sort()
    text = " ".join(w for _, w in word_positions).strip()
    return text or None


def _parse_openalex_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract abstract + metadata from an OpenAlex /works/{doi}
    JSON object (issue #1033). Abstract is reconstructed from
    abstract_inverted_index. Returns dict with keys: title, authors,
    journal, year, abstract, doi (normalized, prefix-stripped,
    lowercased). Values may be None/empty when absent."""
    if not isinstance(data, dict):
        return {}
    abstract = _reconstruct_inverted_abstract(
        data.get("abstract_inverted_index")
    )

    title = data.get("title") or data.get("display_name") or None
    if isinstance(title, str):
        title = title.strip() or None

    authors: list[str] = []
    for a in (data.get("authorships") or []):
        if not isinstance(a, dict):
            continue
        au = a.get("author")
        name = (au.get("display_name") or "").strip() if isinstance(au, dict) else ""
        if name:
            authors.append(name)

    journal = None
    pl = data.get("primary_location")
    if isinstance(pl, dict):
        src = pl.get("source")
        if isinstance(src, dict):
            journal = (src.get("display_name") or "").strip() or None

    year = data.get("publication_year")
    if not isinstance(year, int):
        year = None

    doi_raw = data.get("doi") or ""
    doi_norm = doi_raw.lower().strip() if isinstance(doi_raw, str) else ""
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi_norm.startswith(prefix):
            doi_norm = doi_norm[len(prefix):]
            break
    doi_norm = doi_norm.rstrip("/") or None

    return {
        "title": title,
        "authors": tuple(authors),
        "journal": journal,
        "year": year,
        "abstract": abstract,
        "doi": doi_norm,
    }


def _strip_jats_tags(text: str) -> str:
    """Very conservative JATS XML stripping for CrossRef abstracts.
    Keeps text content, drops tags.

    CrossRef abstracts frequently use the `<jats:p>` etc. namespace
    prefix without declaring the xmlns. We wrap the text in a root
    element that declares `xmlns:jats` so ElementTree can parse it.
    """
    # Wrap with a root that declares the JATS namespace so prefixed
    # tags parse. Several common JATS prefixes seen in the wild.
    wrapped = (
        '<root xmlns:jats="http://jats.nlm.nih.gov" '
        'xmlns:mml="http://www.w3.org/1998/Math/MathML">'
        f'{text}</root>'
    )
    try:
        root = ET.fromstring(wrapped)
        return " ".join(
            s.strip() for s in root.itertext() if s and s.strip()
        )
    except ET.ParseError:
        # Last-resort: strip crude <...> tags via a single pass.
        # Safe on CrossRef content (no user-controlled bytes).
        out_chars: list[str] = []
        depth = 0
        for ch in text:
            if ch == "<":
                depth += 1
                continue
            if ch == ">":
                depth = max(0, depth - 1)
                continue
            if depth == 0:
                out_chars.append(ch)
        return "".join(out_chars).strip()


# ─────────────────────────────────────────────────────────────────────
# Layer 3 — Network callers
# ─────────────────────────────────────────────────────────────────────
def _build_full_url(
    base: str, params: dict[str, Any] | None,
) -> str:
    """Compose a URL string including query params so logs carry
    the exact HTTP line. Codex M-56 audit Blocker 2: PubMed
    attempts must show id/rettype/retmode, not just base endpoint."""
    if not params:
        return base
    # Deterministic param ordering — sorted by key.
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{q}"


def _request_with_retry(
    client: httpx.Client,
    method: str,
    source: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[
    httpx.Response | None,
    str,
    list[RetrievalAttempt],
    list[RetrievalTiming],
]:
    """Deterministic retry with fixed backoff. Emits ONE
    RetrievalAttempt per HTTP request (Codex M-56 audit Blocker 2)
    with per-attempt timing in a separate RetrievalTiming list
    (Blocker 1: non-deterministic wall-clock out of payload).

    Returns (response_or_None, final_outcome, attempts, timings).
    final_outcome ∈ {"success", "not_found", "error:timeout",
    "error:http_<code>", "error:network:<short>", "error:exhausted:<cls>"}.
    """
    headers = {**(headers or {}), "User-Agent": _POLARIS_UA}
    full_url = _build_full_url(url, params)
    attempts: list[RetrievalAttempt] = []
    timings: list[RetrievalTiming] = []
    last_exc: Exception | None = None
    for attempt_idx in range(1, _MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            if method == "GET":
                r = client.get(url, headers=headers, params=params)
            else:
                raise ValueError(f"unsupported method {method!r}")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            last_exc = exc
            outcome = (
                f"retryable_network:{type(exc).__name__}"
                if attempt_idx < _MAX_RETRIES
                else f"error:{type(exc).__name__}"
            )
            attempts.append(RetrievalAttempt(
                source=source, url=full_url,
                attempt_index=attempt_idx,
                http_status=None, outcome=outcome,
            ))
            timings.append(RetrievalTiming(
                source=source, attempt_index=attempt_idx,
                duration_ms=elapsed,
            ))
            if attempt_idx < _MAX_RETRIES:
                time.sleep(_BACKOFF_SECONDS[attempt_idx - 1])
                continue
            return (None, outcome, attempts, timings)
        except Exception as exc:  # network / TLS / unexpected
            elapsed = int((time.monotonic() - t0) * 1000)
            last_exc = exc
            outcome = f"error:network:{type(exc).__name__}"
            attempts.append(RetrievalAttempt(
                source=source, url=full_url,
                attempt_index=attempt_idx,
                http_status=None, outcome=outcome,
            ))
            timings.append(RetrievalTiming(
                source=source, attempt_index=attempt_idx,
                duration_ms=elapsed,
            ))
            return (None, outcome, attempts, timings)

        elapsed = int((time.monotonic() - t0) * 1000)

        if r.status_code == 200:
            attempts.append(RetrievalAttempt(
                source=source, url=full_url,
                attempt_index=attempt_idx,
                http_status=200, outcome="success",
            ))
            timings.append(RetrievalTiming(
                source=source, attempt_index=attempt_idx,
                duration_ms=elapsed,
            ))
            return (r, "success", attempts, timings)

        if r.status_code == 404:
            attempts.append(RetrievalAttempt(
                source=source, url=full_url,
                attempt_index=attempt_idx,
                http_status=404, outcome="not_found",
            ))
            timings.append(RetrievalTiming(
                source=source, attempt_index=attempt_idx,
                duration_ms=elapsed,
            ))
            return (r, "not_found", attempts, timings)

        if r.status_code in (429, 500, 502, 503, 504):
            # Retryable. Log attempt, maybe continue.
            if attempt_idx < _MAX_RETRIES:
                attempts.append(RetrievalAttempt(
                    source=source, url=full_url,
                    attempt_index=attempt_idx,
                    http_status=r.status_code,
                    outcome=f"retryable_http_{r.status_code}",
                ))
                timings.append(RetrievalTiming(
                    source=source, attempt_index=attempt_idx,
                    duration_ms=elapsed,
                ))
                time.sleep(_BACKOFF_SECONDS[attempt_idx - 1])
                continue
            # Final retry failed.
            outcome = f"error:http_{r.status_code}"
            attempts.append(RetrievalAttempt(
                source=source, url=full_url,
                attempt_index=attempt_idx,
                http_status=r.status_code, outcome=outcome,
            ))
            timings.append(RetrievalTiming(
                source=source, attempt_index=attempt_idx,
                duration_ms=elapsed,
            ))
            return (r, outcome, attempts, timings)

        # Non-retryable (400, 401, 403, etc.)
        outcome = f"error:http_{r.status_code}"
        attempts.append(RetrievalAttempt(
            source=source, url=full_url,
            attempt_index=attempt_idx,
            http_status=r.status_code, outcome=outcome,
        ))
        timings.append(RetrievalTiming(
            source=source, attempt_index=attempt_idx,
            duration_ms=elapsed,
        ))
        return (r, outcome, attempts, timings)

    # Exhausted retries
    outcome = (
        f"error:exhausted:{type(last_exc).__name__ if last_exc else 'unknown'}"
    )
    return (None, outcome, attempts, timings)


def _call_crossref(
    client: httpx.Client, doi: str
) -> tuple[dict[str, Any] | None, list[RetrievalAttempt], list[RetrievalTiming]]:
    url = _CROSSREF_BASE + _urlsafe_doi(doi)
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "crossref", url,
    )
    if outcome != "success" or r is None:
        return None, attempts, timings
    try:
        data = r.json()
    except ValueError:
        # Replace the final success attempt with an invalid_json
        # failure record so the log is honest about the outcome.
        last = attempts[-1]
        attempts[-1] = RetrievalAttempt(
            source=last.source, url=last.url,
            attempt_index=last.attempt_index,
            http_status=last.http_status,
            outcome="error:invalid_json",
        )
        return None, attempts, timings
    return data, attempts, timings


def _call_unpaywall(
    client: httpx.Client, doi: str, *, email: str | None = None
) -> tuple[dict[str, Any] | None, list[RetrievalAttempt], list[RetrievalTiming]]:
    email = email or os.getenv("PG_UNPAYWALL_EMAIL", "polaris@example.org")
    url = _UNPAYWALL_BASE + _urlsafe_doi(doi)
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "unpaywall", url,
        params={"email": email},
    )
    if outcome != "success" or r is None:
        return None, attempts, timings
    try:
        data = r.json()
    except ValueError:
        last = attempts[-1]
        attempts[-1] = RetrievalAttempt(
            source=last.source, url=last.url,
            attempt_index=last.attempt_index,
            http_status=last.http_status,
            outcome="error:invalid_json",
        )
        return None, attempts, timings
    return data, attempts, timings


def _call_pubmed(
    client: httpx.Client, pmid: str
) -> tuple[str | None, list[RetrievalAttempt], list[RetrievalTiming]]:
    url = _PUBMED_EFETCH_BASE
    params = {
        "db": "pubmed",
        "id": str(pmid),
        "rettype": "abstract",
        "retmode": "xml",
    }
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "pubmed", url, params=params,
    )
    if outcome != "success" or r is None:
        return None, attempts, timings
    body = r.text or ""
    if not body.strip():
        # PubMed returns 200 empty for unknown PMIDs. Replace the
        # success record with not_found so the log matches reality.
        last = attempts[-1]
        attempts[-1] = RetrievalAttempt(
            source=last.source, url=last.url,
            attempt_index=last.attempt_index,
            http_status=last.http_status,
            outcome="not_found",
        )
        return None, attempts, timings
    return body, attempts, timings


def _call_openalex(
    client: httpx.Client, doi: str
) -> tuple[dict[str, Any] | None, list[RetrievalAttempt], list[RetrievalTiming]]:
    """Deterministic OpenAlex /works/{doi} fetch (issue #1033).

    Abstract fallback for journal DOIs where CrossRef returned no
    abstract and the OA full-text PDF was paywalled (403). Uses the
    same retry/attempt-logging discipline as the other callers so
    M-60 manifest telemetry shows the OpenAlex attempt."""
    email = os.getenv("PG_UNPAYWALL_EMAIL", "polaris@example.org")
    url = _OPENALEX_WORK_BASE + "https://doi.org/" + _urlsafe_doi(doi)
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "openalex", url, params={"mailto": email},
    )
    if outcome != "success" or r is None:
        return None, attempts, timings
    try:
        data = r.json()
    except ValueError:
        last = attempts[-1]
        attempts[-1] = RetrievalAttempt(
            source=last.source, url=last.url,
            attempt_index=last.attempt_index,
            http_status=last.http_status,
            outcome="error:invalid_json",
        )
        return None, attempts, timings
    return data, attempts, timings


def _call_s2(
    client: httpx.Client, doi: str
) -> tuple[dict[str, Any] | None, list[RetrievalAttempt], list[RetrievalTiming]]:
    """Deterministic Semantic Scholar Graph API /paper/DOI:{doi} fetch — M3b
    (I-deepfix-001) 3rd abstract source.

    Mirrors ``_call_openalex``: same ``_request_with_retry`` discipline (one
    RetrievalAttempt per HTTP request, fixed backoff, status->outcome mapping)
    so M-60 manifest telemetry shows the S2 attempt. An optional
    ``SEMANTIC_SCHOLAR_API_KEY`` (already an env in the codebase) is sent as the
    ``x-api-key`` header for rate-limit headroom; unauthenticated still works
    (S2 throttles, which the 429 backoff already handles)."""
    headers: dict[str, str] = {}
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    url = _S2_WORK_BASE + _urlsafe_doi(doi)
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "s2", url,
        params={"fields": "title,abstract,year,venue,externalIds"},
        headers=headers,
    )
    if outcome != "success" or r is None:
        return None, attempts, timings
    try:
        data = r.json()
    except ValueError:
        last = attempts[-1]
        attempts[-1] = RetrievalAttempt(
            source=last.source, url=last.url,
            attempt_index=last.attempt_index,
            http_status=last.http_status,
            outcome="error:invalid_json",
        )
        return None, attempts, timings
    return data, attempts, timings


def _parse_s2_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract abstract + metadata from a Semantic Scholar Graph API
    /paper/DOI:{doi} JSON object (M3b). Returns dict with keys: title, authors,
    journal, year, abstract, doi (normalized, prefix-stripped, lowercased).
    Values may be None/empty when absent. DOI is read from ``externalIds.DOI``
    so the caller's DOI-consistency guard can reject a wrong-paper response
    (mirrors the OpenAlex/PubMed guards)."""
    if not isinstance(data, dict):
        return {}

    abstract = data.get("abstract")
    if isinstance(abstract, str):
        abstract = abstract.strip() or None
    else:
        abstract = None

    title = data.get("title")
    if isinstance(title, str):
        title = title.strip() or None
    else:
        title = None

    journal = data.get("venue")
    if isinstance(journal, str):
        journal = journal.strip() or None
    else:
        journal = None

    year = data.get("year")
    if not isinstance(year, int):
        year = None

    doi_norm: str | None = None
    ext = data.get("externalIds")
    if isinstance(ext, dict):
        doi_raw = ext.get("DOI") or ext.get("doi") or ""
        if isinstance(doi_raw, str):
            doi_norm = doi_raw.lower().strip()
            for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
                if doi_norm.startswith(prefix):
                    doi_norm = doi_norm[len(prefix):]
                    break
            doi_norm = doi_norm.rstrip("/") or None

    return {
        "title": title,
        "authors": (),
        "journal": journal,
        "year": year,
        "abstract": abstract,
        "doi": doi_norm,
    }


def _looks_like_html_junk(text: str) -> bool:
    """True when a fetched 'full text' is actually raw HTML markup or a
    Sci-Hub wrapper page rather than clean extracted prose (#1034
    follow-up). Ground-truthed: aeaweb paywalled econ papers (e.g.
    Acemoglu 10.1257/jep.33.2.3) come back as a ~25K-char Sci-Hub HTML
    viewer page that passes any length threshold but is useless for M-58
    extraction. Inspects the head of the content for HTML structural
    markers or Sci-Hub branding (case-insensitive)."""
    head = text[:600].lower()
    return (
        "<!doctype" in head
        or "<html" in head
        or "<head>" in head
        or "<head " in head
        or "<body" in head
        or "sci-hub" in head
    )


def _is_usable_full_text(text: str | None) -> bool:
    """A fetched OA full text is usable as the rich `direct_quote` source
    only if it is SUBSTANTIAL (>= _OA_FULLTEXT_MIN_CHARS) AND clean prose
    (not HTML / Sci-Hub junk). Otherwise the abstract fallbacks
    (CrossRef / OpenAlex / PubMed) must take over (#1034)."""
    return bool(
        text
        and len(text) >= _OA_FULLTEXT_MIN_CHARS
        and not _looks_like_html_junk(text)
    )


def _pick_richest_abstract(
    *,
    crossref: str | None,
    openalex: str | None,
    pubmed: str | None,
    s2: str | None = None,
    partial_full_text: str | None = None,
) -> tuple[str, str]:
    """Choose the RICHEST (longest) available abstract text + its
    quote_source label. Candidates in priority order CrossRef >
    OpenAlex > PubMed > Semantic Scholar (M3b) > thin-OA-full-text
    partial; the LONGEST wins, ties break toward the higher-priority
    source (deterministic — strictly-greater comparison while
    iterating priority order). ``s2`` defaults to None so existing
    keyword callers are byte-identical.

    A thin oa_full_text stub (paywalled-PDF Jina result, ~540 chars)
    is admitted only as the last-priority `partial_full_text`
    candidate, so a real abstract (e.g. OpenAlex 1331 chars) overrides
    it rather than being blocked by it (issue #1034). Returns
    ("", "none") when every candidate is empty."""
    candidates: list[tuple[str, str]] = []
    if crossref:
        candidates.append((crossref, "crossref_abstract"))
    if openalex:
        candidates.append((openalex, "openalex_abstract"))
    if pubmed:
        candidates.append((pubmed, "pubmed_abstract"))
    if s2:
        candidates.append((s2, "s2_abstract"))
    # A thin OA full-text stub is a TRUE last resort: admit it ONLY when
    # no real abstract resolved. Per §-1.1 clinical-safety (dual-audit
    # finding #1034), a paywall junk stub must never become the extracted
    # span when a real abstract exists — even if the stub is longer.
    if partial_full_text and not candidates:
        candidates.append((partial_full_text, "oa_full_text_partial"))
    best: tuple[str, str] | None = None
    for text, src in candidates:
        if best is None or len(text) > len(best[0]):
            best = (text, src)
    return best if best is not None else ("", "none")


def _urlsafe_doi(doi: str) -> str:
    """CrossRef and Unpaywall accept DOIs verbatim; percent-encode
    any slashes? The standard is to pass the raw DOI. Both APIs
    accept both forms. We keep it raw — no encoding needed for the
    typical DOI characters (10.XXXX/YYYY)."""
    return doi.strip()


# V30 Phase-2 M-66b content-fetch helper (Codex pass-3 CONDITIONAL-
# no-blockers approved). Wraps POLARIS's existing AccessBypass
# stack (Crawl4AI + Jina Reader + Firecrawl concurrent) used
# elsewhere for content extraction. Used by M-56 for:
#
#   - M-66b-R: url_pattern-primary regulatory entities (FDA, EMA,
#     NICE, HC landing pages) where no DOI/PMID exists.
#   - M-66b-T: OA PDF/HTML full-text fetch when Unpaywall
#     surfaced an OA URL — upgrades direct_quote from abstract
#     to full text so M-58 can extract 9-field SURPASS rosters.
#
# Returns `(content_str, final_url_str)` on success, `("", "")` on
# failure. Caller decides provenance class + attempt logging.
# Content is truncated at `_M66_CONTENT_CAP` chars for prompt-
# budget predictability.
_M66_CONTENT_CAP = 25000

# ─────────────────────────────────────────────────────────────────────
# A1 (iarch006 RC1) — fetch-INGESTION shell detector.
#
# The url-pattern / OA-locator fetch layer previously accepted ANY
# non-empty body as bound evidence (`return content[:_M66_CONTENT_CAP]`).
# In the Q90 epic-failure run every mandated legal section was wired to
# ONE web page that returned HTTP 200 but whose captured text was page
# FURNITURE — an Archive.org JS wrapper, a CourtListener docket index
# ("Filing fee $402.00") instead of the verdict, a literal "Page not
# found" NTSB body. No real prose to ground on, so the section honestly
# printed an empty gap stub even though real case-law content sat in the
# pool unbound.
#
# This detector keys ONLY on FETCH-INTEGRITY (chrome / soft-404 / docket
# index / JS-wrapper / content-starvation), NEVER on topicality. It must
# NOT become a generic relevance hard-drop on real-but-junk-host content
# — that would be the §-1.3-banned FILTER. A detected shell is routed to
# the EXISTING METADATA_ONLY / not_extractable branch (a gap/recovery
# signal), NOT a new hard-drop and NOT bound evidence.
#
# Minimum chars of recovered main content for a fetched body to count as
# real prose (env-overridable, LAW VI). Sits at the same order of
# magnitude as live_retriever.is_content_starved's 200-char useful-text
# floor; the fetch layer wants a slightly higher bar because a bound
# frame-entity quote feeds slot prose, not a corpus weight.
_MIN_MAINCONTENT_CHARS = int(os.getenv("PG_MIN_MAINCONTENT_CHARS", "250"))

# Above this fraction of lines being pure link/nav markers a body is a
# navigation index / docket listing, not article prose (env, LAW VI).
_MAX_LINK_DENSITY = float(os.getenv("PG_FETCH_MAX_LINK_DENSITY", "0.6"))

# A body shorter than this is treated as a single unit for the
# boilerplate / non-assertional whole-unit check (a real article body is
# far longer; a stub / docket index / error page is short). Env, LAW VI.
_SHELL_WHOLE_UNIT_MAX_CHARS = int(
    os.getenv("PG_FETCH_SHELL_WHOLE_UNIT_MAX_CHARS", "1200")
)


def _link_density(text: str) -> float:
    """Fraction of non-blank lines that are pure link / nav / bullet
    markers (markdown `[...](...)`, bare URLs, or `* `/`- ` list chrome
    with little prose). A docket index or a JS-wrapper landing page is
    almost entirely such lines; a real article is almost none.

    Pure fetch-integrity signal — measures STRUCTURE, never topic."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 1.0
    import re as _re

    link_like = 0
    for ln in lines:
        # A markdown link line, a bare-URL line, or a short nav/list-glue
        # line dominated by a link token.
        if _re.match(r"^[*\-•]?\s*\[[^\]]*\]\([^)]*\)\s*$", ln):
            link_like += 1
        elif _re.match(r"^https?://\S+$", ln):
            link_like += 1
        elif "](" in ln and len(_re.sub(r"\[[^\]]*\]\([^)]*\)", "", ln).strip()) < 24:
            link_like += 1
    return link_like / len(lines)


def _is_fetch_shell(content: str) -> tuple[bool, str]:
    """A1 — return ``(True, reason)`` when a fetched body is a fetch-layer
    SHELL (page furniture / soft-404 / docket index / JS-wrapper /
    content-starved) rather than real article prose to ground on.

    Keys ONLY on fetch-integrity. NEVER inspects topicality — a real
    article about an unrelated subject is NOT a shell. The detector
    REUSES the existing markers:
      - `_looks_like_html_junk` (raw-HTML / Sci-Hub wrapper) → recover
        the main text via the guarded `safe_trafilatura_extract`
        (favor_precision) before measuring, so a real article that the
        backend returned as raw HTML is NOT mis-flagged.
      - `is_boilerplate_or_nonassertional` (access_bypass) — the GATE-layer
        chrome / bare-DOI / table-row / soft-404 marker, now applied at the
        FETCH layer (the exact layer gap A1 names) on a short whole body.
      - a `_MIN_MAINCONTENT_CHARS` floor and a `_MAX_LINK_DENSITY` cap.

    The empty-string return is the caller's existing "no usable content"
    signal — it routes to the METADATA_ONLY / not_extractable branch."""
    if not content:
        return True, "empty_body"

    body = content
    # If the body is raw HTML markup (Sci-Hub viewer / JS-wrapper), recover
    # the main text via the ONE guarded trafilatura entrypoint before
    # measuring — a real article wrapped in markup must survive.
    if _looks_like_html_junk(body):
        try:
            from src.tools.access_bypass import safe_trafilatura_extract

            recovered = safe_trafilatura_extract(
                body, favor_precision=True, include_links=False
            )
        except Exception:  # noqa: BLE001 — recovery is best-effort.
            recovered = None
        if recovered and len(recovered.strip()) >= _MIN_MAINCONTENT_CHARS:
            # Real prose was hidden under the markup — not a shell.
            return False, ""
        # No real main content recovered from the markup → shell.
        return True, "js_wrapper_no_maincontent"

    stripped = body.strip()

    # Content-starvation floor (fetch-integrity, not topicality).
    if len(stripped) < _MIN_MAINCONTENT_CHARS:
        # A short body that IS a known chrome / soft-404 / docket-row
        # stub is a shell; reuse the gate-layer marker at the fetch layer.
        try:
            from src.tools.access_bypass import is_boilerplate_or_nonassertional

            if is_boilerplate_or_nonassertional(stripped):
                return True, "boilerplate_or_error_stub"
        except Exception:  # noqa: BLE001
            pass
        return True, "content_starved"

    # A short-ish body that is wholly non-assertional chrome / a docket
    # index / a soft-404 (the gate-layer marker, now at fetch layer).
    if len(stripped) <= _SHELL_WHOLE_UNIT_MAX_CHARS:
        try:
            from src.tools.access_bypass import is_boilerplate_or_nonassertional

            if is_boilerplate_or_nonassertional(stripped):
                return True, "boilerplate_or_error_stub"
        except Exception:  # noqa: BLE001
            pass

    # Navigation-index / docket-listing structure (high link density) —
    # a fetch-integrity STRUCTURE signal, never a topic signal.
    if _link_density(stripped) >= _MAX_LINK_DENSITY:
        return True, "link_density_index_page"

    return False, ""


def _fetch_url_pattern(url: str) -> tuple[str, str]:
    """Fetch content at `url` via AccessBypass. Returns
    `(content, final_url)` or `("", "")` on failure.

    Deterministic-test seam: this function is the mockable
    boundary for M-66b-R / M-66b-T tests (stub via
    `monkeypatch.setattr("...frame_fetcher._fetch_url_pattern",
    lambda u: ("stubbed content", u))`).

    AccessBypass.fetch_with_bypass is async; M-56 is sync. The
    helper wraps the async call in asyncio.run(). If an event
    loop is already running in the caller's thread (live server
    context), we fall back to a fresh thread + new loop so this
    helper is safe to invoke from any caller context.
    """
    if not url:
        return "", ""
    try:
        import asyncio as _asyncio
        from src.tools.access_bypass import AccessBypass

        async def _run() -> tuple[str, str]:
            ab = AccessBypass()
            result = await ab.fetch_with_bypass(url)
            if result is None or not getattr(result, "success", False):
                return "", ""
            content = getattr(result, "content", "") or ""
            final_url = getattr(result, "url", "") or url
            method = (getattr(result, "access_method", "") or "").lower()
            # Never use pirate-source (Sci-Hub) content in a research /
            # clinical product — legal + provenance (#1034 dual-audit P1).
            # Rejects BOTH the Sci-Hub HTML viewer page AND clean Sci-Hub
            # PDF text (which _looks_like_html_junk cannot detect).
            if "scihub" in method or "sci-hub" in method:
                return "", ""
            if not content:
                return "", ""
            # I-beatboth-010 (#1288) FIX-A: strip Jina/Crawl4AI reader chrome
            # (Title:/URL Source:/Published Time:/Number of Pages:/Markdown
            # Content: preamble) BEFORE the shell check + evidence binding, so the
            # fetched body returned from this path is clean. Input hygiene only;
            # faithfulness gates untouched. An all-chrome body cleans to empty and
            # is then correctly routed to the existing METADATA_ONLY gap branch.
            from src.tools.access_bypass import clean_fetch_body
            content = clean_fetch_body(content).cleaned_text
            if not content:
                return "", ""
            # A1 (iarch006 RC1): reject a fetch-layer SHELL (page furniture
            # / soft-404 / docket index / JS-wrapper / content-starved)
            # BEFORE it is bound as evidence. Keys on fetch-integrity only,
            # never topicality. Returning ("", "") routes the caller to the
            # EXISTING METADATA_ONLY / not_extractable branch — a gap/
            # recovery signal, not bound evidence and not a new hard-drop.
            is_shell, shell_reason = _is_fetch_shell(content)
            if is_shell:
                logger.info(
                    "[frame_fetcher] A1 fetch-shell rejected url=%s "
                    "reason=%s len=%d → METADATA_ONLY gap/recovery",
                    final_url or url, shell_reason, len(content),
                )
                return "", ""
            return content[:_M66_CONTENT_CAP], final_url

        try:
            # Probe for a running loop. asyncio.get_running_loop
            # raises RuntimeError when no loop is running (normal
            # sync context); the no-warning way to ask.
            _asyncio.get_running_loop()
            # A loop IS running — spin a fresh one in a worker
            # thread so we don't collide with it (e.g. live-server
            # FastAPI context).
            import concurrent.futures as _cf

            def _thread_run() -> tuple[str, str]:
                return _asyncio.run(_run())

            with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(_thread_run).result()
        except RuntimeError:
            # No running loop — asyncio.run will create one.
            return _asyncio.run(_run())
    except Exception:  # noqa: BLE001
        # AccessBypass raised — don't propagate; M-56 treats as
        # failed fetch and continues with whatever it has.
        return "", ""


# ─────────────────────────────────────────────────────────────────────
# Layer 4 — Orchestrator
# ─────────────────────────────────────────────────────────────────────
def fetch_frame_entity(
    binding: EvidenceBinding,
    *,
    client: httpx.Client | None = None,
) -> FrameRow:
    """Deterministic frame-entity retriever.

    Given a compiled EvidenceBinding (from M-55), emit one FrameRow
    with provenance_class, direct_quote, metadata, and retrieval
    attempt log.

    Args:
        binding: M-55 compiled binding with primary_identifier +
            secondary_identifiers.
        client: optional httpx.Client for DI (testing). When None,
            a fresh client is created per call with _DEFAULT_TIMEOUT.

    Returns:
        FrameRow — always non-None. A FRAME_GAP_UNRECOVERABLE row is
        still a valid return — callers inspect `is_gap()` or
        `provenance_class` to branch.

    Deterministic per design — same (binding, upstream API state) →
    byte-identical FrameRow. No randomness, no wall-clock in payload.
    """
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=_DEFAULT_TIMEOUT)
    try:
        return _fetch_frame_entity_inner(binding, client)
    finally:
        if owns_client:
            client.close()


def _fetch_frame_entity_inner(
    binding: EvidenceBinding,
    client: httpx.Client,
) -> FrameRow:
    """Core dispatch: pick strategy by primary_identifier prefix."""
    identifiers = _collect_identifiers(binding)

    # URL-pattern-primary entities (regulatory): V30 Phase-2 M-66b-R
    # lifts these from METADATA_ONLY to OPEN_ACCESS when content can
    # be fetched via the POLARIS AccessBypass helper. Codex pass-3
    # CONDITIONAL-no-blockers approved this scope.
    if binding.primary_identifier.startswith("url:") and not (
        identifiers.get("doi") or identifiers.get("pmid")
    ):
        url = identifiers["url"]
        fetched_content, fetched_url = _fetch_url_pattern(url)
        # I-wire-013 (#1327): repair PDF/HTML line-wrap hyphens in the stored,
        # cited direct_quote at the fetch layer (frame url-pattern path). Input
        # hygiene only; legit hyphens / multilingual prose preserved byte-for-byte.
        from src.tools.access_bypass import dehyphenate_line_wraps  # noqa: PLC0415
        fetched_content = dehyphenate_line_wraps(fetched_content)
        url_attempts: list[RetrievalAttempt] = []
        if fetched_content:
            url_attempts.append(RetrievalAttempt(
                source="access_bypass",
                url=f"url_pattern:{fetched_url or url}",
                attempt_index=1,
                http_status=200,
                outcome="success",
            ))
            return FrameRow(
                entity_id=binding.entity_id,
                entity_type=binding.entity_type,
                rendering_slot=binding.rendering_slot,
                provenance_class=ProvenanceClass.OPEN_ACCESS,
                direct_quote=fetched_content,
                quote_source="url_pattern_fetch",
                doi=None,
                pmid=None,
                oa_pdf_url=None,
                url=fetched_url or url,
                title=None,
                authors=(),
                journal=None,
                year=None,
                failure_reason=None,
                retrieval_attempts=tuple(url_attempts),
                retrieval_timings=(),
            )
        # Fetch produced nothing usable — fall back to METADATA_ONLY
        # so M-58 emits `not_extractable` (curator-actionable) rather
        # than crash downstream. Log the attempt.
        url_attempts.append(RetrievalAttempt(
            source="access_bypass",
            url=f"url_pattern:{url}",
            attempt_index=1,
            http_status=None,
            outcome="error:fetch_returned_no_content",
        ))
        return FrameRow(
            entity_id=binding.entity_id,
            entity_type=binding.entity_type,
            rendering_slot=binding.rendering_slot,
            provenance_class=ProvenanceClass.METADATA_ONLY,
            direct_quote="",
            quote_source="url_pattern_placeholder",
            doi=None,
            pmid=None,
            oa_pdf_url=None,
            url=url,
            title=None,
            authors=(),
            journal=None,
            year=None,
            failure_reason=None,
            retrieval_attempts=tuple(url_attempts),
            retrieval_timings=(),
        )

    # Anchor-only entities (no DOI, no PMID, no URL): cannot resolve.
    if not (
        identifiers.get("doi")
        or identifiers.get("pmid")
        or identifiers.get("url")
    ):
        return FrameRow(
            entity_id=binding.entity_id,
            entity_type=binding.entity_type,
            rendering_slot=binding.rendering_slot,
            provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            direct_quote="",
            quote_source="none",
            doi=None,
            pmid=None,
            oa_pdf_url=None,
            url=None,
            title=None,
            authors=(),
            journal=None,
            year=None,
            failure_reason=(
                "entity has anchor-only identifier; M-56 retriever "
                "requires doi, pmid, or url."
            ),
            retrieval_attempts=(),
            retrieval_timings=(),
        )

    # Normal path: DOI / PMID
    attempts: list[RetrievalAttempt] = []
    timings: list[RetrievalTiming] = []
    title: str | None = None
    authors: tuple[str, ...] = ()
    journal: str | None = None
    year: int | None = None
    abstract_crossref: str | None = None
    doi = identifiers.get("doi")
    pmid = identifiers.get("pmid")
    # Entity-scoped prefer-abstract (#1034 dual-audit P1): a narrative
    # frame entity (economic_report, ...) under the flag prefers the clean
    # abstract AND skips the OA scrape entirely; a full-text entity type
    # (clinical trial rosters) keeps the full-text path so Gate-B coverage
    # is preserved.
    entity_prefers_abstract = (
        _FRAME_PREFER_ABSTRACT
        and binding.entity_type.strip().lower() not in _FULLTEXT_ENTITY_TYPES
    )

    # Step 1: CrossRef for metadata + abstract when DOI present
    if doi:
        cr_data, cr_attempts, cr_timings = _call_crossref(client, doi)
        attempts.extend(cr_attempts)
        timings.extend(cr_timings)
        if cr_data is not None:
            parsed = _parse_crossref_response(cr_data)
            title = parsed.get("title")
            authors = parsed.get("authors") or ()
            journal = parsed.get("journal")
            year = parsed.get("year")
            abstract_crossref = parsed.get("abstract")

    # Step 2: Unpaywall for OA URL
    oa_pdf_url: str | None = None
    oa_html_url: str | None = None
    oa_full_text: str | None = None
    # Which source produced oa_full_text — drives the quote_source label
    # downstream ("core" -> "core_oa_fulltext"; AccessBypass -> "oa_full_text").
    oa_full_text_source: str | None = None
    if doi:
        up_data, up_attempts, up_timings = _call_unpaywall(client, doi)
        attempts.extend(up_attempts)
        timings.extend(up_timings)
        if up_data is not None:
            parsed_up = _parse_unpaywall_response(up_data)
            if parsed_up.get("is_oa"):
                oa_pdf_url = parsed_up.get("oa_pdf_url")
                oa_html_url = parsed_up.get("oa_html_url")

    # Step 2b: V30 Phase-2 M-66b-T — fetch OA PDF/HTML full text
    # (Codex pass-3 CONDITIONAL-no-blockers). Upgrades
    # direct_quote from ~500-char abstract to up to 25K chars of
    # full text, giving M-58 enough surface to extract SURPASS
    # 9-field rosters. Falls back to abstract on fetch failure.
    oa_locator = oa_pdf_url or oa_html_url
    if oa_locator and entity_prefers_abstract:
        # Narrative frame entity under prefer-abstract: SKIP the OA scrape
        # entirely — no non-deterministic AccessBypass call, no Sci-Hub
        # request (#1034 dual-audit P1). The clean abstract is the source.
        attempts.append(RetrievalAttempt(
            source="access_bypass",
            url=f"oa_full_text_skipped:{oa_locator}",
            attempt_index=1,
            http_status=None,
            outcome="skipped:prefer_abstract",
        ))
    elif oa_locator:
        # Step 2b.0 (I-faith-002): try CORE (core.ac.uk) FIRST as the LEGAL
        # OA full-text source that replaced the now-disabled Sci-Hub path.
        # CORE is DOI-keyed and exact-DOI-guarded (wrong-paper-fabrication
        # guard lives in core_client). It returns ("", "") on a missing
        # key / fuzzy mismatch / empty fullText / network failure, in which
        # case we fall through to the existing (Sci-Hub-free) AccessBypass
        # scrape. The usability guards (_is_usable_full_text /
        # _looks_like_html_junk) run downstream, source-agnostically, on
        # whatever oa_full_text we capture here.
        core_text = ""
        if _core_enabled() and doi:
            # Pass the CrossRef-resolved title/year as the INDEPENDENT
            # identity anchor (#1039 Bug 2): CORE mis-tags distinct papers
            # under one DOI, so core_client requires this anchor to match
            # before trusting a result's fullText. When CrossRef did not
            # resolve a title, the anchor is None and core_client falls
            # back to its conservative no-hint / mis-tag-conflict rejection.
            core_text, core_url = fetch_core_oa_fulltext(
                doi, expected_title=title, expected_year=year
            )
            if core_text:
                oa_full_text = core_text
                oa_full_text_source = "core"
                attempts.append(RetrievalAttempt(
                    source="core",
                    url=f"oa_full_text:{core_url or oa_locator}",
                    attempt_index=1,
                    http_status=200,
                    outcome="success",
                ))
            else:
                # Telemetry parity (module contract lines 42-46: every
                # attempt logged): a CORE miss (no key / fuzzy mismatch /
                # empty fullText / network failure) records an error
                # attempt so a frame_gap_unrecoverable row shows CORE was
                # tried before falling through to AccessBypass.
                attempts.append(RetrievalAttempt(
                    source="core",
                    url=f"oa_full_text:doi={doi}",
                    attempt_index=1,
                    http_status=None,
                    outcome="error:core_returned_no_content",
                ))
        if not core_text:
            full_text, final_url = _fetch_url_pattern(oa_locator)
            if full_text:
                oa_full_text = full_text
                oa_full_text_source = "access_bypass"
                attempts.append(RetrievalAttempt(
                    source="access_bypass",
                    url=f"oa_full_text:{final_url or oa_locator}",
                    attempt_index=1,
                    http_status=200,
                    outcome="success",
                ))
            else:
                attempts.append(RetrievalAttempt(
                    source="access_bypass",
                    url=f"oa_full_text:{oa_locator}",
                    attempt_index=1,
                    http_status=None,
                    outcome="error:fetch_returned_no_content",
                ))

    # Step 3: PubMed EFetch when PMID present and we still lack abstract
    abstract_pubmed: str | None = None
    if pmid and not abstract_crossref:
        pm_xml, pm_attempts, pm_timings = _call_pubmed(client, pmid)
        attempts.extend(pm_attempts)
        timings.extend(pm_timings)
        if pm_xml is not None:
            parsed_pm = _parse_pubmed_xml(pm_xml)
            # DOI-consistency guard (V30 Phase-2 sweep run-1 root
            # cause fix): when the bound entity has BOTH doi and
            # pmid, require PubMed's returned DOI to match the
            # bound DOI (case-insensitive). Silent DOI↔PMID
            # mismatches in the contract YAML otherwise produce
            # on-topic-looking prose extracted from the WRONG
            # paper, sailing past M-58's verbatim-substring
            # anti-fabrication check.
            pm_doi = parsed_pm.get("doi") or ""
            bound_doi_l = (doi or "").lower()
            if doi and pm_doi and pm_doi != bound_doi_l:
                # Codex M-66 plan review Medium #4: emit a real
                # RetrievalAttempt (source/url/attempt_index/
                # http_status/outcome) so M-60 manifest telemetry
                # shows the DOI-mismatch rejection. Earlier draft
                # used the legacy (method/endpoint/status_code/
                # error/duration_ms) constructor which would have
                # raised TypeError if triggered.
                attempts.append(RetrievalAttempt(
                    source="pubmed",
                    url=f"pubmed:pmid={pmid}",
                    attempt_index=1,
                    http_status=None,
                    outcome=(
                        f"error:doi_mismatch bound={bound_doi_l} "
                        f"pubmed_returned={pm_doi}"
                    ),
                ))
                # Reject PubMed content entirely for this entity —
                # we MUST NOT extract from SPRINT when the contract
                # intended SURPASS-2.
            else:
                abstract_pubmed = parsed_pm.get("abstract")
                # Fill missing metadata from PubMed if CrossRef didn't
                # provide it.
                title = title or parsed_pm.get("title")
                authors = authors or parsed_pm.get("authors") or ()
                journal = journal or parsed_pm.get("journal")
                year = year or parsed_pm.get("year")

    # Step 4: OpenAlex abstract fallback (issue #1033). When CrossRef
    # carried no abstract, PubMed yielded none (or there was no PMID),
    # and the OA full-text fetch failed (paywalled PDF 403'd), OpenAlex's
    # abstract_inverted_index reliably holds the abstract for indexed
    # journal DOIs (Acemoglu/Autor/Brynjolfsson/Eloundou all resolve).
    # DOI-driven; no source allowlist; same DOI -> byte-identical text.
    abstract_openalex: str | None = None
    # M3b (I-deepfix-001): gather-all-then-pick-richest. With PG_FRAME_MULTI_ABSTRACT
    # ON (default), OpenAlex is consulted for a DOI EVEN WHEN CrossRef/PubMed already
    # returned an abstract, so a degenerate first-source fragment can no longer
    # short-circuit the gather and starve the slot — `_pick_richest_abstract` picks the
    # longest. OFF restores the legacy `not abstract_crossref and not abstract_pubmed`
    # short-circuit byte-identically. The full-text guard clause is INTENTIONALLY kept:
    # a clinical entity with real OA full text still skips OpenAlex (full text wins),
    # while the paywalled primaries here (no usable full text) still consult OpenAlex.
    if (
        _OPENALEX_FRAME_FALLBACK_ENABLED
        and doi
        and (
            _frame_multi_abstract_enabled()
            or (not abstract_crossref and not abstract_pubmed)
        )
        and (not _is_usable_full_text(oa_full_text) or entity_prefers_abstract)
    ):
        oa_meta, oa_attempts, oa_timings = _call_openalex(client, doi)
        attempts.extend(oa_attempts)
        timings.extend(oa_timings)
        if oa_meta is not None:
            parsed_oa = _parse_openalex_response(oa_meta)
            # DOI-consistency guard (mirrors the PubMed guard above):
            # reject content when OpenAlex's own DOI disagrees with the
            # bound DOI, so we never extract from the wrong work.
            oa_doi = parsed_oa.get("doi") or ""
            bound_doi_l = (doi or "").lower()
            if oa_doi and oa_doi != bound_doi_l:
                attempts.append(RetrievalAttempt(
                    source="openalex",
                    url=f"openalex:doi={bound_doi_l}",
                    attempt_index=1,
                    http_status=None,
                    outcome=(
                        f"error:doi_mismatch bound={bound_doi_l} "
                        f"openalex_returned={oa_doi}"
                    ),
                ))
            else:
                abstract_openalex = parsed_oa.get("abstract")
                title = title or parsed_oa.get("title")
                authors = authors or parsed_oa.get("authors") or ()
                journal = journal or parsed_oa.get("journal")
                year = year or parsed_oa.get("year")

    # Step 5: Semantic Scholar abstract source (M3b, I-deepfix-001). A 3rd
    # deterministic source so a closed-access primary whose CrossRef/OpenAlex
    # abstract is a degenerate fragment (or a single transient throttle left it
    # empty) still lands a full abstract. Same gather-all gating as OpenAlex: when
    # PG_FRAME_S2_ABSTRACT is ON (default), consult S2 even if other sources have an
    # abstract so `_pick_richest_abstract` can pick the longest; OFF removes S2
    # entirely. The full-text guard is kept so a real OA full text still wins. Same
    # DOI-consistency guard as OpenAlex/PubMed — never extract from the wrong work.
    abstract_s2: str | None = None
    if (
        _frame_s2_abstract_enabled()
        and doi
        and (
            _frame_multi_abstract_enabled()
            or (not abstract_crossref and not abstract_pubmed and not abstract_openalex)
        )
        and (not _is_usable_full_text(oa_full_text) or entity_prefers_abstract)
    ):
        s2_meta, s2_attempts, s2_timings = _call_s2(client, doi)
        attempts.extend(s2_attempts)
        timings.extend(s2_timings)
        if s2_meta is not None:
            parsed_s2 = _parse_s2_response(s2_meta)
            s2_doi = parsed_s2.get("doi") or ""
            bound_doi_l = (doi or "").lower()
            if s2_doi and s2_doi != bound_doi_l:
                attempts.append(RetrievalAttempt(
                    source="s2",
                    url=f"s2:doi={bound_doi_l}",
                    attempt_index=1,
                    http_status=None,
                    outcome=(
                        f"error:doi_mismatch bound={bound_doi_l} "
                        f"s2_returned={s2_doi}"
                    ),
                ))
            else:
                abstract_s2 = parsed_s2.get("abstract")
                title = title or parsed_s2.get("title")
                authors = authors or parsed_s2.get("authors") or ()
                journal = journal or parsed_s2.get("journal")
                year = year or parsed_s2.get("year")

    # Decide provenance_class and direct_quote.
    # OPEN_ACCESS when Unpaywall surfaced ANY OA locator (PDF or
    # HTML landing). HTML-only is still fetchable by existing
    # POLARIS content fetch infrastructure at M-57; the distinction
    # from ABSTRACT_ONLY is that a full-text source exists.
    any_oa_url = oa_pdf_url or oa_html_url
    # A real OA full-text extraction is long; a paywalled-PDF stub
    # (e.g. aeaweb returns ~540 chars via Jina) is NOT usable full text
    # (issue #1034). Only treat oa_full_text as real full text above the
    # threshold; otherwise it competes as a last-priority partial.
    real_full_text = oa_full_text if _is_usable_full_text(oa_full_text) else None
    # Richest abstract across CrossRef/OpenAlex/PubMed (+ a thin but CLEAN
    # oa_full_text stub as last resort), longest wins (#1033/#1034). HTML /
    # Sci-Hub junk is never admitted as a partial — it would poison the span.
    abstract_text, abstract_quote_source = _pick_richest_abstract(
        crossref=abstract_crossref,
        openalex=abstract_openalex,
        pubmed=abstract_pubmed,
        s2=abstract_s2,
        partial_full_text=(
            oa_full_text
            if (
                oa_full_text
                and not real_full_text
                and not _looks_like_html_junk(oa_full_text)
            )
            else None
        ),
    )
    if entity_prefers_abstract and abstract_text:
        # Frame-contract grounding (#1034): the clean, deterministic
        # abstract is preferred over a non-deterministic / noisy OA scrape.
        # Contract fields (thesis/mechanism/effect) are abstract-level claims.
        direct_quote = abstract_text
        quote_source = abstract_quote_source
        provenance = (
            ProvenanceClass.OPEN_ACCESS if any_oa_url
            else ProvenanceClass.ABSTRACT_ONLY
        )
        failure_reason = None
    elif real_full_text:
        # V30 Phase-2 M-66b-T: real OA full text — rich source for
        # M-58's multi-field extractions (default path; clinical rosters).
        # I-faith-002: label by source so the manifest distinguishes a
        # legal CORE OA fetch from an AccessBypass scrape.
        direct_quote = real_full_text
        quote_source = (
            "core_oa_fulltext" if oa_full_text_source == "core"
            else "oa_full_text"
        )
        provenance = ProvenanceClass.OPEN_ACCESS
        failure_reason = None
    elif abstract_text:
        direct_quote = abstract_text
        quote_source = abstract_quote_source
        # OPEN_ACCESS when an OA locator existed (full text just wasn't
        # extractable); else ABSTRACT_ONLY.
        provenance = (
            ProvenanceClass.OPEN_ACCESS if any_oa_url
            else ProvenanceClass.ABSTRACT_ONLY
        )
        failure_reason = None
    elif title:  # we have metadata but no abstract, no OA
        direct_quote = ""
        quote_source = "none"
        provenance = ProvenanceClass.METADATA_ONLY
        failure_reason = None
    else:
        # All sources failed.
        direct_quote = ""
        quote_source = "none"
        provenance = ProvenanceClass.FRAME_GAP_UNRECOVERABLE
        failure_reason = _summarize_failure(attempts)

    # I-wire-013 (#1327): repair PDF/HTML line-wrap hyphens in the stored, cited
    # direct_quote (covers the real-full-text + abstract branches above) at the
    # fetch layer BEFORE the row is persisted, so every later span offset resolves
    # against the de-hyphenated text. Input hygiene only; legit hyphens ("co-author",
    # "GLP-1") and multilingual prose preserved byte-for-byte; faithfulness FROZEN.
    from src.tools.access_bypass import dehyphenate_line_wraps  # noqa: PLC0415
    direct_quote = dehyphenate_line_wraps(direct_quote)
    return FrameRow(
        entity_id=binding.entity_id,
        entity_type=binding.entity_type,
        rendering_slot=binding.rendering_slot,
        provenance_class=provenance,
        direct_quote=direct_quote,
        quote_source=quote_source,
        doi=doi,
        pmid=pmid,
        oa_pdf_url=oa_pdf_url or oa_html_url,
        url=identifiers.get("url"),
        title=title,
        authors=authors,
        journal=journal,
        year=year,
        failure_reason=failure_reason,
        retrieval_attempts=tuple(attempts),
        retrieval_timings=tuple(timings),
    )


def _collect_identifiers(binding: EvidenceBinding) -> dict[str, str]:
    """Flatten primary + secondary identifiers into a {kind: value}
    dict. Kinds: 'doi', 'pmid', 'url', 'anchor'."""
    out: dict[str, str] = {}
    for ident in (binding.primary_identifier, *binding.secondary_identifiers):
        if ":" not in ident:
            continue
        kind, value = ident.split(":", 1)
        out.setdefault(kind, value)
    return out


def _summarize_failure(attempts: list[RetrievalAttempt]) -> str:
    """Compose a short failure_reason string from the attempt log.
    Consumed by M-60 manifest rendering. Summarizes the FINAL
    outcome per source (aggregates retry noise, while the full
    chain remains visible via FrameRow.retrieval_attempts)."""
    if not attempts:
        return "no retrieval attempted (no resolvable identifier)"
    # Collapse per-source by taking the last attempt for each
    # source (which carries the terminal outcome).
    final_by_source: dict[str, RetrievalAttempt] = {}
    for a in attempts:
        final_by_source[a.source] = a
    summaries = [
        f"{a.source}={a.outcome}({a.http_status})"
        for a in final_by_source.values()
    ]
    return "all sources failed: " + "; ".join(summaries)


def fetch_compiled_frame(
    bindings: tuple[EvidenceBinding, ...],
    *,
    client: httpx.Client | None = None,
) -> tuple[FrameRow, ...]:
    """Fetch all entities in a CompiledFrame.evidence_bindings.

    Reuses a single httpx.Client across all entities for efficiency.
    Returns rows in the same order as `bindings`.
    """
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=_DEFAULT_TIMEOUT)
    try:
        return tuple(
            _fetch_frame_entity_inner(b, client) for b in bindings
        )
    finally:
        if owns_client:
            client.close()
