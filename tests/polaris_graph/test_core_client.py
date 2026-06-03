"""Tests for the CORE API v3 client (I-faith-002).

All tests are deterministic and run WITHOUT network access — CORE is
mocked via an injected `httpx.MockTransport` (mirrors the M-56
frame_fetcher test style). The transport matches on the CORE host so it
is robust to httpx percent-encoding the `doi:"..."` query value.

Covers the contract:
  1. Exact-DOI match -> returns (fullText, source_url).
  2. FUZZY mismatch (CORE returns a different DOI) -> ("", "").
  3. Zero hits -> ("", "").
  4. Missing api_key (env + arg) -> ("", "") with NO request made.
  5. DOI normalization (https://doi.org/ prefix input still matches a
     bare returned DOI).
"""
from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from src.tools.core_client import _normalize_doi, fetch_core_oa_fulltext

_CORE_HOST = "api.core.ac.uk"
_TARGET_DOI = "10.1257/jep.33.2.3"  # Acemoglu — the verified fuzzy case
_FULL_TEXT = "Automation and New Tasks: full open-access body text ..."
# A ≥2-significant-token title used as the identity anchor in the positive
# tests. The content-identity guard (#1039) REQUIRES a matching expected_title
# for any positive return, so base tests pass this as both the result title
# and the anchor.
_MATCH_TITLE = "Automation and New Tasks"


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _work(
    *,
    doi: str,
    full_text: str | None = _FULL_TEXT,
    download_url: str | None = None,
    title: str = _MATCH_TITLE,
    year: int | None = None,
) -> dict[str, Any]:
    work: dict[str, Any] = {"doi": doi, "title": title}
    if full_text is not None:
        work["fullText"] = full_text
    if download_url is not None:
        work["downloadUrl"] = download_url
    if year is not None:
        work["yearPublished"] = year
    return work


def _search_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"totalHits": len(results), "results": results}


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _static_handler(
    body: dict[str, Any],
    *,
    status: int = 200,
    call_log: list[str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if call_log is not None:
            call_log.append(str(request.url))
        assert _CORE_HOST in str(request.url)
        return httpx.Response(status, json=body)

    return handler


# ─────────────────────────────────────────────────────────────────────
# (1) Exact-DOI match returns fullText
# ─────────────────────────────────────────────────────────────────────
def test_exact_doi_match_returns_full_text() -> None:
    body = _search_response([_work(doi=_TARGET_DOI)])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert content == _FULL_TEXT
    # Default source_url is the canonical DOI resolver URL.
    assert url == f"https://doi.org/{_TARGET_DOI}"


def test_exact_doi_match_prefers_download_url() -> None:
    download = "https://oa.example.org/paper.pdf"
    body = _search_response(
        [_work(doi=_TARGET_DOI, download_url=download)]
    )
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert content == _FULL_TEXT
    assert url == download


def test_authorization_header_sent() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200, json=_search_response([_work(doi=_TARGET_DOI)])
        )

    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="secret-key", client=_client(handler)
    )
    assert content == _FULL_TEXT
    assert captured["auth"] == "Bearer secret-key"


# ─────────────────────────────────────────────────────────────────────
# (2) Fuzzy mismatch (different DOI) returns empty
# ─────────────────────────────────────────────────────────────────────
def test_fuzzy_mismatch_returns_empty() -> None:
    # CORE's fuzzy search returned a SPANISH paper with a DIFFERENT DOI
    # for the Acemoglu query — must be rejected as wrong-paper.
    body = _search_response(
        [_work(doi="10.5209/rev_xyz.2018.v99.99999")]
    )
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert (content, url) == ("", "")


def test_exact_match_after_fuzzy_hit_is_selected() -> None:
    # First hit is a fuzzy mismatch; the exact match follows -> selected.
    body = _search_response(
        [
            _work(doi="10.9999/wrong.paper", full_text="wrong body"),
            _work(doi=_TARGET_DOI),
        ]
    )
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert content == _FULL_TEXT


# ─────────────────────────────────────────────────────────────────────
# (3) Zero hits returns empty
# ─────────────────────────────────────────────────────────────────────
def test_zero_hits_returns_empty() -> None:
    body = _search_response([])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert (content, url) == ("", "")


def test_exact_match_with_empty_full_text_returns_empty() -> None:
    body = _search_response([_work(doi=_TARGET_DOI, full_text="")])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert (content, url) == ("", "")


# ─────────────────────────────────────────────────────────────────────
# (4) Missing api_key returns empty WITHOUT making a request
# ─────────────────────────────────────────────────────────────────────
def test_missing_api_key_returns_empty_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json=_search_response([]))

    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, api_key=None, client=_client(handler)
    )
    assert (content, url) == ("", "")
    # No HTTP request must be made when the key is absent.
    assert called["n"] == 0


def test_api_key_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORE_API_KEY", "env-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200, json=_search_response([_work(doi=_TARGET_DOI)])
        )

    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE, client=_client(handler)
    )
    assert content == _FULL_TEXT
    assert captured["auth"] == "Bearer env-key"


# ─────────────────────────────────────────────────────────────────────
# (5) DOI normalization (https://doi.org/ prefix input)
# ─────────────────────────────────────────────────────────────────────
def test_doi_normalization_prefix_input_matches() -> None:
    # Caller passes a resolver-prefixed DOI; CORE returns the bare form.
    # Normalization must make them compare equal.
    body = _search_response([_work(doi=_TARGET_DOI)])
    content, url = fetch_core_oa_fulltext(
        f"https://doi.org/{_TARGET_DOI}",
        expected_title=_MATCH_TITLE,
        api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert content == _FULL_TEXT
    # source_url uses the normalized (bare-prefixed) DOI.
    assert url == f"https://doi.org/{_TARGET_DOI}"


def test_doi_normalization_returned_prefixed_matches() -> None:
    # Inverse: caller passes bare; CORE returns a resolver-prefixed DOI.
    body = _search_response(
        [_work(doi=f"https://doi.org/{_TARGET_DOI.upper()}")]
    )
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE,
        api_key="test-key", client=_client(_static_handler(body))
    )
    assert content == _FULL_TEXT


def test_normalize_doi_helper() -> None:
    assert _normalize_doi("https://doi.org/10.1/AbC/") == "10.1/abc"
    assert _normalize_doi("doi:10.1/abc") == "10.1/abc"
    assert _normalize_doi("  10.1/ABC  ") == "10.1/abc"
    assert _normalize_doi("") == ""


# ─────────────────────────────────────────────────────────────────────
# Robustness: non-200 / malformed JSON
# ─────────────────────────────────────────────────────────────────────
def test_non_200_returns_empty() -> None:
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI,
        api_key="test-key",
        client=_client(_static_handler({}, status=503)),
    )
    assert (content, url) == ("", "")


def test_malformed_json_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, api_key="test-key", client=_client(handler)
    )
    assert (content, url) == ("", "")


# ─────────────────────────────────────────────────────────────────────
# #1039 Bug 1 — the production client MUST follow redirects
# ─────────────────────────────────────────────────────────────────────
def test_production_client_follows_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CORE v3 301-redirects `/v3/search/works` -> `/v3/search/works/`.
    # Without follow_redirects=True every production call lands on the
    # non-200 branch and returns ("","") for EVERY DOI — a silent dead
    # path that also hides the Bug-2 wrong-paper guard. Assert the
    # client fetch_core_oa_fulltext builds is redirect-following.
    captured: dict[str, Any] = {}
    real_client_cls = httpx.Client

    def fake_client(*args: Any, **kwargs: Any) -> httpx.Client:
        captured.update(kwargs)
        return real_client_cls(
            transport=httpx.MockTransport(
                _static_handler(_search_response([_work(doi=_TARGET_DOI)]))
            ),
            timeout=5.0,
        )

    monkeypatch.setattr("src.tools.core_client.httpx.Client", fake_client)
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_MATCH_TITLE, api_key="test-key"
    )
    assert content == _FULL_TEXT
    assert captured.get("follow_redirects") is True


# ─────────────────────────────────────────────────────────────────────
# #1039 Bug 2 — content-identity guard (CORE mis-tags papers under a DOI)
# ─────────────────────────────────────────────────────────────────────
_ACEMOGLU_TITLE = (
    "Automation and New Tasks: How Technology Displaces and Reinstates Labor"
)
_SPANISH_TITLE = (
    "Impacto de las nuevas tecnologias en los salarios en Colombia"
)


def test_wrong_paper_rejected_on_title_mismatch() -> None:
    # The LIVE #1039 Bug 2: CORE returns the WRONG (Spanish) paper tagged
    # with the EXACT Acemoglu DOI, carrying fullText; the correct paper
    # also appears under the same DOI but with empty fullText. With the
    # CrossRef title as the anchor, the wrong paper's fullText must be
    # rejected -> empty (no wrong-paper fabrication).
    body = _search_response([
        _work(
            doi=_TARGET_DOI, title=_SPANISH_TITLE,
            full_text="WRONG PAPER BODY about Colombian wages", year=2022,
        ),
        _work(doi=_TARGET_DOI, title=_ACEMOGLU_TITLE, full_text="", year=2019),
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE, expected_year=2019,
        api_key="test-key", client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_correct_paper_returned_when_title_matches() -> None:
    # Same mis-tagged set but now the CORRECT paper carries fullText —
    # the title anchor selects it, not the wrong-paper sibling.
    body = _search_response([
        _work(
            doi=_TARGET_DOI, title=_SPANISH_TITLE,
            full_text="WRONG PAPER BODY", year=2022,
        ),
        _work(
            doi=_TARGET_DOI, title=_ACEMOGLU_TITLE,
            full_text=_FULL_TEXT, year=2019,
        ),
    ])
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE, expected_year=2019,
        api_key="test-key", client=_client(_static_handler(body)),
    )
    assert content == _FULL_TEXT


def test_title_match_tolerates_truncated_core_title() -> None:
    # CORE truncates long titles; overlap-coefficient vs the smaller token
    # set still confirms identity.
    truncated = "Automation and New Tasks How Technology Displaces"
    body = _search_response(
        [_work(doi=_TARGET_DOI, title=truncated, full_text=_FULL_TEXT)]
    )
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE,
        api_key="test-key", client=_client(_static_handler(body)),
    )
    assert content == _FULL_TEXT


def test_year_mismatch_rejected() -> None:
    # Title matches but the year is implausibly far off -> reject.
    body = _search_response([
        _work(
            doi=_TARGET_DOI, title=_ACEMOGLU_TITLE,
            full_text=_FULL_TEXT, year=1990,
        )
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE, expected_year=2019,
        api_key="test-key", client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_no_anchor_rejects_even_with_exact_match() -> None:
    # Codex diff-gate P1.2: with NO independent title anchor, CORE fullText
    # must NOT be trusted on DOI-equality alone (CORE mis-tags). A single
    # clean exact-DOI result with fullText still returns ("","").
    body = _search_response(
        [_work(doi=_TARGET_DOI, title=_ACEMOGLU_TITLE, full_text=_FULL_TEXT)]
    )
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_blank_anchor_rejects() -> None:
    # An empty/whitespace expected_title is treated as "no anchor" -> reject.
    body = _search_response(
        [_work(doi=_TARGET_DOI, title=_ACEMOGLU_TITLE, full_text=_FULL_TEXT)]
    )
    content, _ = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title="   ", api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert content == ""


def test_short_subset_wrong_title_rejected() -> None:
    # Codex diff-gate P1.1: a SHORT/SUBSET wrong title must NOT pass. A CORE
    # record titled just "Automation" (1 significant token) under the exact
    # DOI, carrying fullText, vs the full expected title -> Jaccard 1/6 ≈
    # 0.17 < 0.5 AND shared 1 < min_shared 2 -> rejected.
    body = _search_response([
        _work(doi=_TARGET_DOI, title="Automation", full_text="WRONG SUBSET"),
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE, api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_partial_two_token_overlap_rejected() -> None:
    # "Automation and Labor" shares 2 tokens with the 6-token expected title
    # but coverage 2/6 ≈ 0.33 < 0.5 -> rejected (overlap-over-min would have
    # wrongly passed this at 2/2=1.0).
    body = _search_response([
        _work(doi=_TARGET_DOI, title="Automation and Labor", full_text="WRONG"),
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=_ACEMOGLU_TITLE, api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_clinical_sibling_drug_substitution_rejected() -> None:
    # Codex diff-gate iter-2 P1 (clinical-safety): a mis-tagged SIBLING trial
    # whose title differs only in the INTERVENTION token must be rejected even
    # though token overlap is high (4/6, would-be coverage 0.8). The drug
    # substitution semaglutide<->tirzepatide is the wrong-drug fabrication the
    # span-grounded clinical path must never admit.
    expected = "Tirzepatide Once Weekly for the Treatment of Obesity"
    body = _search_response([
        _work(
            doi=_TARGET_DOI,
            title="Semaglutide Once Weekly for the Treatment of Obesity",
            full_text="WRONG DRUG body text",
        ),
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=expected, api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")


def test_superset_core_title_with_extra_identity_terms_rejected() -> None:
    # Codex diff-gate iter-3 P1: a SUPERSET that adds identity terms
    # (population/subgroup/phase/acronym) names a DIFFERENT trial, not a
    # subtitle, and must be rejected. Expected "Tirzepatide ... Obesity" vs
    # CORE "... Obesity in People with Type 2 Diabetes" (exp ⊆ cand, coverage
    # 1.0) -> rejected because the candidate adds `diabetes`/`type`/`people`.
    expected = "Tirzepatide Once Weekly for the Treatment of Obesity"
    body = _search_response([
        _work(
            doi=_TARGET_DOI,
            title=(
                "Tirzepatide Once Weekly for the Treatment of Obesity in "
                "People with Type 2 Diabetes"
            ),
            full_text="WRONG POPULATION body text",
        ),
    ])
    content, url = fetch_core_oa_fulltext(
        _TARGET_DOI, expected_title=expected, api_key="test-key",
        client=_client(_static_handler(body)),
    )
    assert (content, url) == ("", "")
