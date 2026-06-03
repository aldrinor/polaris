"""CORE API v3 client — legal OA full-text fetch by DOI (I-faith-002).

Replaces the Sci-Hub access path (`src/tools/access_bypass.py`
`_try_scihub`) with the CORE (core.ac.uk) aggregator's v3 search API,
a LEGAL best-effort full-text source for open-access works.

## Why a DOI guard is non-negotiable

The CORE `/v3/search/works?q=doi:"<doi>"` endpoint is FUZZY: for the
Acemoglu DOI `10.1257/jep.33.2.3` it returned a *Spanish* paper with a
different DOI (verified — see `.codex/I-faith-002/core_api_facts.md`).
Returning that paper's `fullText` to the caller would be wrong-paper
fabrication. So this client REJECTS every result whose normalized
`work["doi"]` does not EXACTLY equal the normalized queried DOI.

## Contract

`fetch_core_oa_fulltext(doi, *, api_key=None, client=None)` returns
`(content, source_url)` on success or `("", "")` otherwise. It NEVER
raises on a missing key, a network failure, a fuzzy mismatch, or an
empty result — coverage is partial by design and the caller falls
back to the abstract on `("", "")`.

## Dependency injection (testability — mirrors frame_fetcher M-56)

`client` is an optional `httpx.Client`. Production callers pass None
(a fresh, bounded-timeout client is created per call and closed in a
`finally`); tests inject an `httpx.MockTransport`-backed client. No
test needs to monkeypatch module globals.

## Determinism

Given the same DOI and the same upstream CORE response, the same
`(content, source_url)` is returned: explicit normalization, in-order
result iteration, no randomness, no wall-clock in the payload. Content
is capped at `_CORE_CONTENT_CAP` chars for prompt-budget predictability.
"""
from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Config (LAW VI — all tunables from env, never hardcoded)
# ─────────────────────────────────────────────────────────────────────
_CORE_SEARCH_URL = os.getenv(
    "PG_CORE_SEARCH_URL", "https://api.core.ac.uk/v3/search/works"
)
# Number of fuzzy hits to inspect for an exact-DOI match.
_CORE_SEARCH_LIMIT = int(os.getenv("PG_CORE_SEARCH_LIMIT", "3"))
_CORE_TIMEOUT = float(os.getenv("PG_CORE_TIMEOUT", "15"))
# Content cap mirrors frame_fetcher._M66_CONTENT_CAP (~25000) for
# prompt-budget predictability; kept local to avoid cross-module
# coupling (LAW VII CLI isolation).
_CORE_CONTENT_CAP = int(os.getenv("PG_CORE_CONTENT_CAP", "25000"))
# DOI-resolver prefixes stripped during normalization.
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")
# Content-identity guard (#1039 Bug 2, hardened per Codex diff-gate P1×3):
# CORE mis-tags distinct papers under one DOI, so DOI-equality alone returned
# the WRONG paper. `_title_matches` requires (a) the candidate adds NO
# significant token absent from the caller's expected (CrossRef) title — i.e.
# `cand ⊆ exp`, rejecting both a drug substitution and an identity-adding
# superset (population/subgroup/phase/acronym = a sibling trial) — and (b)
# coverage of the expected title ≥ this fraction. A SHORT/SUBSET wrong title
# ("Automation" vs the 6-token expected) fails on coverage (1/6 < 0.5); a
# genuinely truncated correct title (4 of 6 tokens, 0.67) passes.
_TITLE_MATCH_MIN = float(os.getenv("PG_CORE_TITLE_MATCH_MIN", "0.5"))
# Absolute floor on shared significant tokens — blocks a single-token
# coincidence from passing on coverage alone.
_TITLE_MIN_SHARED_TOKENS = int(os.getenv("PG_CORE_TITLE_MIN_SHARED_TOKENS", "2"))
# Publication-year jitter tolerance for the secondary identity signal.
_YEAR_TOLERANCE = int(os.getenv("PG_CORE_YEAR_TOLERANCE", "1"))
# Short function words dropped before title-token comparison so they do
# not inflate the overlap of two unrelated titles.
_TITLE_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "how", "new", "via",
    "into", "over", "under", "between", "about", "across",
})


def _normalize_doi(doi: str) -> str:
    """Normalize a DOI for exact comparison: strip a doi.org / doi:
    prefix, lowercase, and rstrip a trailing slash.

    Mirrors the normalization in
    `frame_fetcher._parse_openalex_response` so the two retrieval paths
    agree on DOI identity.
    """
    norm = (doi or "").strip().lower()
    for prefix in _DOI_PREFIXES:
        if norm.startswith(prefix):
            norm = norm[len(prefix):]
            break
    return norm.rstrip("/")


def _title_tokens(title: str | None) -> frozenset[str]:
    """Significant lowercased alphanumeric tokens of a title (len > 2,
    stopwords removed). Deterministic; used for the content-identity
    guard."""
    toks = re.findall(r"[a-z0-9]+", (title or "").lower())
    return frozenset(
        t for t in toks if len(t) > 2 and t not in _TITLE_STOPWORDS
    )


def _title_matches(candidate: str | None, expected: str | None) -> bool:
    """True iff `candidate` is the SAME work as `expected` by title. Three
    conditions, all required (empty/blank on either side → False, the
    conservative clinical-safe default):

    1. ≥ `_TITLE_MIN_SHARED_TOKENS` shared significant tokens.
    2. NO EXTRA CANDIDATE TOKEN — the candidate introduces NO significant
       token absent from the expected (CrossRef) title (`cand ⊆ exp`). This
       rejects BOTH a SUBSTITUTION and an IDENTITY-ADDING SUPERSET, the two
       clinical wrong-paper vectors #1039 surfaced:
         * substitution — candidate "Semaglutide Once Weekly for the
           Treatment of Obesity" vs expected "Tirzepatide …": `semaglutide`
           ∉ expected → reject (iter-2);
         * superset adding a population/subgroup/phase/acronym — candidate
           "Tirzepatide … Obesity in People with Type 2 Diabetes" vs expected
           "Tirzepatide … Obesity": `diabetes`/`type`/`people` ∉ expected →
           reject (iter-3). These name a DIFFERENT trial, not a subtitle.
       Only a pure subset/truncation of the expected title (the candidate is
       a clean abbreviation of CrossRef's authoritative title) is allowed —
       a truncation cannot introduce a different population or intervention.
    3. COVERAGE — enough of the expected title's identity is present:
       `|shared| / |expected| ≥ _TITLE_MATCH_MIN`."""
    cand = _title_tokens(candidate)
    exp = _title_tokens(expected)
    if not cand or not exp:
        return False
    shared = cand & exp
    if len(shared) < _TITLE_MIN_SHARED_TOKENS:
        return False
    # The candidate must NOT assert a significant token the expected
    # (CrossRef-authoritative) title lacks. Any extra token is a different
    # work — a drug substitution OR a population/subgroup/phase/acronym that
    # names a SIBLING trial. Only a clean subset/truncation of the expected
    # title is admissible.
    if cand - exp:
        return False
    return (len(shared) / len(exp)) >= _TITLE_MATCH_MIN


def fetch_core_oa_fulltext(
    doi: str,
    *,
    expected_title: str | None = None,
    expected_year: int | None = None,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Fetch legal OA full text for `doi` from CORE v3.

    Args:
        doi: the target DOI. Accepts bare (`10.1257/jep.33.2.3`) or
            resolver-prefixed (`https://doi.org/10.1257/...`) form; it is
            normalized before querying and comparison.
        expected_title: the DOI's title from an INDEPENDENT source
            (CrossRef, in the frame_fetcher caller). When supplied, a
            CORE result's `title` must share enough significant tokens
            with it (overlap ≥ `_TITLE_MATCH_MIN`) before its `fullText`
            is trusted — the #1039 Bug-2 wrong-paper guard. Without it,
            DOI-equality alone is NOT safe (CORE mis-tags distinct papers
            under one DOI).
        expected_year: the DOI's publication year from an independent
            source. Secondary signal: a CORE result whose
            `yearPublished` differs by more than `_YEAR_TOLERANCE` is
            rejected.
        api_key: CORE API key. Defaults to `os.getenv("CORE_API_KEY")`.
            If absent, returns `("", "")` WITHOUT making any request and
            WITHOUT raising (LAW VI: never hardcode the key).
        client: optional `httpx.Client` for dependency injection
            (testing). When None, a fresh bounded-timeout client is
            created per call and closed in a `finally`.

    Returns:
        `(content, source_url)` when a result whose normalized DOI
        EXACTLY matches the queried DOI AND whose identity is confirmed
        (title/year guard, or — with no caller hint — no conflicting-title
        mis-tag in the result set) carries non-empty `fullText`;
        otherwise `("", "")`. Never raises on missing key, network
        failure, non-200 status, malformed JSON, fuzzy mismatch, mis-tag,
        or zero hits — the caller falls back to the abstract on
        `("", "")`.
    """
    norm_doi = _normalize_doi(doi)
    if not norm_doi:
        logger.debug("core_client: empty/blank DOI; returning empty.")
        return "", ""

    key = api_key if api_key is not None else os.getenv("CORE_API_KEY")
    if not key:
        # No key — return empty rather than crash; caller falls back to
        # the abstract. LAW VI: the key is never hardcoded.
        logger.info(
            "core_client: CORE_API_KEY missing; skipping CORE fetch for %s.",
            norm_doi,
        )
        return "", ""

    owns_client = client is None
    if client is None:
        # follow_redirects=True is REQUIRED (#1039 Bug 1): CORE v3
        # 301-redirects `/v3/search/works` -> `/v3/search/works/`. Without
        # it every call hits the non-200 branch and returns ("","") for
        # EVERY DOI — a silent dead path that also hides the Bug-2 guard.
        client = httpx.Client(timeout=_CORE_TIMEOUT, follow_redirects=True)
    try:
        return _fetch_inner(client, norm_doi, key, expected_title, expected_year)
    finally:
        if owns_client:
            client.close()


def _fetch_inner(
    client: httpx.Client,
    norm_doi: str,
    key: str,
    expected_title: str | None,
    expected_year: int | None,
) -> tuple[str, str]:
    """Inner fetch given a normalized DOI + resolved key + DI client."""
    params = {
        # Query with the NORMALIZED bare DOI so a resolver-prefixed
        # input still produces the canonical CORE query.
        "q": f'doi:"{norm_doi}"',
        "limit": _CORE_SEARCH_LIMIT,
    }
    headers = {"Authorization": f"Bearer {key}"}

    try:
        response = client.get(
            _CORE_SEARCH_URL, params=params, headers=headers
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "core_client: request failed for %s: %s", norm_doi, exc
        )
        return "", ""

    if response.status_code != 200:
        logger.info(
            "core_client: non-200 (%s) for %s.",
            response.status_code,
            norm_doi,
        )
        return "", ""

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning(
            "core_client: malformed JSON for %s: %s", norm_doi, exc
        )
        return "", ""

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        return "", ""

    # Stage 1 — DOI guard: the CORE search is FUZZY (it returned a Spanish
    # paper for Acemoglu's DOI), so keep only results whose normalized DOI
    # EXACTLY equals the queried DOI. Necessary, but NOT sufficient (#1039
    # Bug 2): CORE also mis-tags DISTINCT papers under one exact DOI.
    exact = [
        work
        for work in results
        if isinstance(work, dict)
        and isinstance(work.get("doi"), str)
        and _normalize_doi(work["doi"]) == norm_doi
    ]
    if not exact:
        # No exact-DOI match among the fuzzy hits.
        return "", ""

    # Stage 2 — content-identity guard (#1039 Bug 2, hardened per Codex
    # diff-gate P1). A result's fullText is trusted ONLY when its identity
    # is confirmed beyond the (mis-taggable) DOI by an INDEPENDENT title
    # anchor. CORE is proven to mis-tag distinct papers under one exact DOI,
    # so without an anchor we cannot tell which paper is real — reject.
    if not (expected_title or "").strip():
        logger.info(
            "core_client: %s — no independent title anchor; refusing to "
            "trust CORE fullText on DOI-equality alone (mis-tag risk).",
            norm_doi,
        )
        return "", ""

    for work in exact:
        if not _title_matches(work.get("title"), expected_title):
            logger.info(
                "core_client: title mismatch for %s (expected %r, got %r); "
                "rejecting wrong-paper fullText.",
                norm_doi,
                (expected_title or "")[:60],
                (work.get("title") or "")[:60],
            )
            continue
        if expected_year is not None:
            cand_year = work.get("yearPublished")
            if (
                isinstance(cand_year, int)
                and abs(cand_year - expected_year) > _YEAR_TOLERANCE
            ):
                logger.info(
                    "core_client: year mismatch for %s (expected %s, got %s); "
                    "rejecting.",
                    norm_doi,
                    expected_year,
                    cand_year,
                )
                continue

        full_text = work.get("fullText")
        if isinstance(full_text, str) and full_text.strip():
            # Source URL: prefer the OA downloadUrl marker the caller can
            # re-fetch; else the canonical DOI resolver URL. Keep it
            # simple — PDF fetching (AccessBypass) is left to the caller.
            download_url = work.get("downloadUrl")
            if isinstance(download_url, str) and download_url.strip():
                source_url = download_url.strip()
            else:
                source_url = f"https://doi.org/{norm_doi}"
            return full_text[:_CORE_CONTENT_CAP], source_url
        # Identity-confirmed but empty fullText — keep scanning; another
        # exact+matching copy may carry the text.

    # No identity-confirmed result with usable fullText.
    return "", ""
