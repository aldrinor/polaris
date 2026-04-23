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
    """

    OPEN_ACCESS = "open_access"
    ABSTRACT_ONLY = "abstract_only"
    METADATA_ONLY = "metadata_only"
    FRAME_GAP_UNRECOVERABLE = "frame_gap_unrecoverable"


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
    quote_source: str           # "crossref_abstract" | "unpaywall_oa_fulltext"
                                # | "pubmed_abstract" | "url_pattern_placeholder"
                                # | "none"
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

    return {
        "title": title,
        "authors": tuple(authors),
        "journal": journal,
        "year": year,
        "abstract": abstract,
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


def _urlsafe_doi(doi: str) -> str:
    """CrossRef and Unpaywall accept DOIs verbatim; percent-encode
    any slashes? The standard is to pass the raw DOI. Both APIs
    accept both forms. We keep it raw — no encoding needed for the
    typical DOI characters (10.XXXX/YYYY)."""
    return doi.strip()


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

    # URL-pattern-primary entities (regulatory): don't try CrossRef /
    # Unpaywall / PubMed. Emit METADATA_ONLY with url as locator;
    # full-content fetch deferred to POLARIS existing infrastructure.
    if binding.primary_identifier.startswith("url:") and not (
        identifiers.get("doi") or identifiers.get("pmid")
    ):
        url = identifiers["url"]
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
            retrieval_attempts=(),
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
    if doi:
        up_data, up_attempts, up_timings = _call_unpaywall(client, doi)
        attempts.extend(up_attempts)
        timings.extend(up_timings)
        if up_data is not None:
            parsed_up = _parse_unpaywall_response(up_data)
            if parsed_up.get("is_oa"):
                oa_pdf_url = parsed_up.get("oa_pdf_url")
                oa_html_url = parsed_up.get("oa_html_url")

    # Step 3: PubMed EFetch when PMID present and we still lack abstract
    abstract_pubmed: str | None = None
    if pmid and not abstract_crossref:
        pm_xml, pm_attempts, pm_timings = _call_pubmed(client, pmid)
        attempts.extend(pm_attempts)
        timings.extend(pm_timings)
        if pm_xml is not None:
            parsed_pm = _parse_pubmed_xml(pm_xml)
            abstract_pubmed = parsed_pm.get("abstract")
            # Fill missing metadata from PubMed if CrossRef didn't
            # provide it.
            title = title or parsed_pm.get("title")
            authors = authors or parsed_pm.get("authors") or ()
            journal = journal or parsed_pm.get("journal")
            year = year or parsed_pm.get("year")

    # Decide provenance_class and direct_quote.
    # OPEN_ACCESS when Unpaywall surfaced ANY OA locator (PDF or
    # HTML landing). HTML-only is still fetchable by existing
    # POLARIS content fetch infrastructure at M-57; the distinction
    # from ABSTRACT_ONLY is that a full-text source exists.
    any_oa_url = oa_pdf_url or oa_html_url
    if any_oa_url:
        # Future work: fetch OA full-text via AccessBypass + Crawl4AI.
        # At M-56 we record the OA URL and use abstract (if available)
        # as direct_quote placeholder. M-57/M-58 may upgrade to
        # fetched full-text. Provenance_class is OPEN_ACCESS so
        # downstream knows the URL exists.
        direct_quote = abstract_crossref or abstract_pubmed or ""
        quote_source = (
            "crossref_abstract"
            if abstract_crossref
            else ("pubmed_abstract" if abstract_pubmed else "none")
        )
        provenance = ProvenanceClass.OPEN_ACCESS
        failure_reason = None
    elif abstract_crossref:
        direct_quote = abstract_crossref
        quote_source = "crossref_abstract"
        provenance = ProvenanceClass.ABSTRACT_ONLY
        failure_reason = None
    elif abstract_pubmed:
        direct_quote = abstract_pubmed
        quote_source = "pubmed_abstract"
        provenance = ProvenanceClass.ABSTRACT_ONLY
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
