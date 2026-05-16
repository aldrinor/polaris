"""Tests for the I-rdy-009 (#505) question-only ambiguity scan.

Covers:
* ``fetch_candidate_snippets`` fail-loud behaviour — a missing
  ``SERPER_API_KEY``, an HTTP failure, or a zero-snippet search raises
  ``CandidateFetchError`` rather than returning ``[]`` (which would be a
  silent false-unambiguous result).
* ``POST /ambiguity/scan`` — 200 on a successful scan (ambiguous and
  unambiguous), 503 ``candidate_fetch_unavailable`` on a fetch failure,
  422 on a too-short question.

``detect_ambiguity`` runs for real; only the Serper network boundary is
stubbed, at ``candidate_fetcher._fetch_serper_organic`` (per CLAUDE.md
§9.4 — do not mock the detector itself).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from polaris_v6.ambiguity_detector.candidate_fetcher import (
    CandidateFetchError,
    fetch_candidate_snippets,
)

_FETCH = "polaris_v6.ambiguity_detector.candidate_fetcher._fetch_serper_organic"

# Four BPEI-style organic hits that cluster into two distinct meanings —
# the same fixture text test_api_ambiguity.py uses for /ambiguity.
_BPEI_ORGANIC = [
    {"link": "https://med.example/1", "title": "BPEI in cardiology",
     "snippet": "BPEI stands for blood pressure end-inspiration index in cardiovascular monitoring."},
    {"link": "https://med.example/2", "title": "Respiratory BPEI",
     "snippet": "Clinicians use BPEI as a blood pressure end-inspiration measurement during the respiratory cycle."},
    {"link": "https://fin.example/1", "title": "BPEI investment products",
     "snippet": "BPEI in finance refers to bank-protected enterprise investment instruments."},
    {"link": "https://fin.example/2", "title": "Sovereign-guarantee BPEI",
     "snippet": "Bank-protected enterprise investment (BPEI) products carry sovereign-guarantee structures."},
]

# Three near-identical hits — one meaning, not ambiguous.
_HOUSING_ORGANIC = [
    {"link": "https://h.example/1", "title": "Housing starts Q3 2025",
     "snippet": "Canadian housing starts rose 3.4% in Q3 2025."},
    {"link": "https://h.example/2", "title": "CMHC housing data",
     "snippet": "CMHC reports housing starts up 3.4% in Q3 2025."},
    {"link": "https://h.example/3", "title": "Q3 2025 starts",
     "snippet": "Q3 2025 housing starts data confirms a 3.4% increase."},
]


def _returns(organic: list[dict]):
    async def _fake(question, *, api_key, max_results, timeout_s):  # noqa: ARG001
        return list(organic)

    return _fake


def _raises(exc: Exception):
    async def _fake(question, *, api_key, max_results, timeout_s):  # noqa: ARG001
        raise exc

    return _fake


# --------------------------------------------------------------------------
# fetch_candidate_snippets — fail-loud guard
# --------------------------------------------------------------------------

def test_fetch_raises_when_serper_key_missing(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setattr(_FETCH, _returns(_BPEI_ORGANIC))
    with pytest.raises(CandidateFetchError, match="SERPER_API_KEY"):
        asyncio.run(fetch_candidate_snippets("What is BPEI?"))


def test_fetch_raises_when_search_request_fails(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(_FETCH, _raises(httpx.ConnectError("network down")))
    with pytest.raises(CandidateFetchError, match="Serper web search failed"):
        asyncio.run(fetch_candidate_snippets("What is BPEI?"))


def test_fetch_raises_when_search_returns_nothing(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(_FETCH, _returns([]))
    with pytest.raises(CandidateFetchError, match="zero candidate snippets"):
        asyncio.run(fetch_candidate_snippets("What is BPEI?"))


def test_fetch_raises_when_all_hits_have_empty_text(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(
        _FETCH, _returns([{"link": "https://x.example/1", "title": "", "snippet": ""}])
    )
    with pytest.raises(CandidateFetchError, match="zero candidate snippets"):
        asyncio.run(fetch_candidate_snippets("What is BPEI?"))


def test_fetch_happy_path_maps_hits_to_snippets(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(_FETCH, _returns(_BPEI_ORGANIC))
    snippets = asyncio.run(fetch_candidate_snippets("What is BPEI?"))
    assert len(snippets) == 4
    assert snippets[0].source_id == "https://med.example/1"
    assert "blood pressure" in snippets[0].text.lower()
    # title and snippet are both present in the candidate text
    assert "BPEI in cardiology" in snippets[0].text


# --------------------------------------------------------------------------
# POST /ambiguity/scan
# --------------------------------------------------------------------------

@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    try:
        from polaris_v6.api.app import create_app

        app = create_app()
    except OSError as exc:  # e.g. gpg binary unavailable on this host
        pytest.skip(f"create_app() unavailable in this environment: {exc}")
    return TestClient(app)


def test_scan_detects_ambiguous_question(client, monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(_FETCH, _returns(_BPEI_ORGANIC))
    response = client.post("/ambiguity/scan", json={"question": "What is BPEI?"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_ambiguous"] is True
    assert len(body["clusters"]) >= 2


def test_scan_unambiguous_question(client, monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr(_FETCH, _returns(_HOUSING_ORGANIC))
    response = client.post(
        "/ambiguity/scan", json={"question": "Q3 2025 housing starts?"}
    )
    assert response.status_code == 200
    assert response.json()["is_ambiguous"] is False


def test_scan_503_when_candidate_fetch_unavailable(client, monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    response = client.post("/ambiguity/scan", json={"question": "What is BPEI?"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "candidate_fetch_unavailable"


def test_scan_rejects_short_question(client):
    response = client.post("/ambiguity/scan", json={"question": "x"})
    assert response.status_code == 422
