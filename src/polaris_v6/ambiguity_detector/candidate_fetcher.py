"""Cheap candidate-snippet fetcher feeding the ambiguity detector.

Issue I-rdy-009 (#505), Phase 3.6. ``detect_ambiguity`` needs candidate
snippets to cluster, but the dashboard create-run flow has no candidate
source for a *question-only* query (no uploaded documents). Both the
``ambiguity_detector`` module docstring and the ``/ambiguity`` request
schema named the missing piece:

    "Phase 1: backend fetches via cheap retrieval before this call."

This module IS that cheap retrieval — a single Serper ``/search`` call
mapped into ``CandidateSnippet`` objects.

Why a self-contained Serper call
--------------------------------
The I-rdy-009 brief originally specified reusing ``SerperClient`` from
``src/search/serper_client.py``. At implement time ``src/search/__init__.py``
was found broken — it imports ``src.search.engines`` and
``src.search.fan_out_executor``, neither of which exists — so
``import src.search.serper_client`` raises ``ModuleNotFoundError`` and
``SerperClient`` is unimportable. This module therefore issues the Serper
``/search`` request directly via ``httpx``, mirroring the proven pattern
in ``src/polaris_graph/retrieval2/real_fetcher.py`` (slice-002's real
Serper fetcher). Same Serper service, same endpoint, same fail-loud
contract — and no dependency on the broken ``src.search`` package.

Fail-loud per CLAUDE.md LAW II
------------------------------
A missing ``SERPER_API_KEY``, a network/HTTP failure, or a search that
yields zero usable snippets raises ``CandidateFetchError`` rather than
returning an empty list. An empty list would be silently misread by
``detect_ambiguity`` as "not ambiguous" — the exact false-negative this
guard exists to prevent. Zero results means *search failed*, not *the
question is unambiguous*.
"""

from __future__ import annotations

import os

import httpx

from polaris_v6.ambiguity_detector.ambiguity_detector import CandidateSnippet

SERPER_SEARCH_ENDPOINT = "https://google.serper.dev/search"
DEFAULT_MAX_RESULTS = 10
DEFAULT_TIMEOUT_S = 10.0


class CandidateFetchError(RuntimeError):
    """Raised when candidate snippets cannot be fetched for a question.

    Surfaced by ``POST /ambiguity/scan`` as HTTP 503
    ``candidate_fetch_unavailable`` so the caller fails loud rather than
    proceeding on an empty (falsely-unambiguous) candidate set.
    """


async def _fetch_serper_organic(
    question: str, *, api_key: str, max_results: int, timeout_s: float
) -> list[dict]:
    """Issue one Serper ``/search`` request; return the raw ``organic`` list.

    Raises ``httpx.HTTPError`` on network failure or a non-2xx response.
    Isolated as a seam so tests can stub the network boundary without
    mocking the detector itself (per CLAUDE.md §9.4).
    """
    payload = {"q": question, "num": max_results}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SERPER_SEARCH_ENDPOINT, json=payload, headers=headers, timeout=timeout_s
        )
        response.raise_for_status()
        data = response.json()
    return data.get("organic", []) or []


async def fetch_candidate_snippets(
    question: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[CandidateSnippet]:
    """Fetch candidate snippets for ``question`` via one cheap web search.

    Args:
        question: the user-typed research question.
        max_results: cap on web-search results requested.
        timeout_s: per-request HTTP timeout.

    Returns:
        A non-empty list of ``CandidateSnippet`` (``source_id`` = result
        URL, ``text`` = ``"<title>. <snippet>"``).

    Raises:
        CandidateFetchError: when ``SERPER_API_KEY`` is unset, the search
            request fails, or it yields zero usable snippets. Never
            returns an empty list — see the module docstring.
    """
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        raise CandidateFetchError(
            "SERPER_API_KEY is unset; cannot fetch ambiguity candidates."
        )

    try:
        organic = await _fetch_serper_organic(
            question, api_key=api_key, max_results=max_results, timeout_s=timeout_s
        )
    except httpx.HTTPError as exc:
        raise CandidateFetchError(
            f"Serper web search failed for {question!r}: {exc}"
        ) from exc

    snippets: list[CandidateSnippet] = []
    for hit in organic:
        url = hit.get("link", "") or ""
        if not url:
            continue
        title = hit.get("title", "") or ""
        snippet = hit.get("snippet", "") or ""
        text = f"{title}. {snippet}".strip()
        if text in (".", ""):
            # Both title and snippet were empty — nothing to cluster on.
            continue
        snippets.append(CandidateSnippet(source_id=url, text=text))

    if not snippets:
        raise CandidateFetchError(
            f"web search returned zero candidate snippets for {question!r}; "
            "the search backend is unreachable or returned no usable results."
        )
    return snippets
