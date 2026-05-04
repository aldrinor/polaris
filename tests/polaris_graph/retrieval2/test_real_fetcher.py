"""Tests for the real Serper + Semantic Scholar fetcher.

Uses httpx.MockTransport to intercept HTTP without hitting the network.
No real API keys consumed; tests pass deterministic JSON payloads.
"""

from __future__ import annotations

import json

import httpx
import pytest

from polaris_graph.retrieval2.real_fetcher import (
    RealFetcher,
    RealFetcherConfig,
    SERPER_ENDPOINT,
    S2_ENDPOINT,
    _fetch_semantic_scholar,
    _fetch_serper,
    build_real_fetcher,
    load_config_from_env,
)


# ---------- Config / env handling ----------

def test_load_config_from_env_requires_serper_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SERPER_API_KEY is required"):
        load_config_from_env()


def test_load_config_from_env_blank_serper_key_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SERPER_API_KEY", "   ")
    with pytest.raises(RuntimeError, match="SERPER_API_KEY is required"):
        load_config_from_env()


def test_load_config_from_env_with_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-serper")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-s2")
    cfg = load_config_from_env()
    assert cfg.serper_api_key == "test-serper"
    assert cfg.semantic_scholar_api_key == "test-s2"


def test_load_config_from_env_optional_s2_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-serper")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    cfg = load_config_from_env()
    assert cfg.semantic_scholar_api_key is None


def test_build_real_fetcher_uses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-serper")
    fetcher = build_real_fetcher()
    assert isinstance(fetcher, RealFetcher)
    assert fetcher.config.serper_api_key == "test-serper"


# ---------- Serper backend (mocked) ----------

def _serper_handler(payload_to_return: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "google.serper.dev"
        body = json.loads(request.content.decode())
        assert "q" in body
        assert request.headers.get("x-api-key")
        return httpx.Response(200, json=payload_to_return)

    return handler


def test_fetch_serper_parses_organic_hits():
    cfg = RealFetcherConfig(serper_api_key="x")
    transport = httpx.MockTransport(
        _serper_handler(
            {
                "organic": [
                    {
                        "link": "https://www.cochrane.org/CD001",
                        "title": "Cochrane review on aspirin",
                        "snippet": "RCT data shows benefit",
                    },
                    {
                        "link": "https://www.nejm.org/doi/abc",
                        "title": "NEJM article",
                        "snippet": "Trial results",
                    },
                ]
            }
        )
    )
    with httpx.Client(transport=transport) as client:
        results = _fetch_serper("aspirin headache", cfg, client)

    assert len(results) == 2
    assert results[0].url == "https://www.cochrane.org/CD001"
    assert results[0].title == "Cochrane review on aspirin"
    assert results[1].snippet == "Trial results"


def test_fetch_serper_skips_hits_without_link():
    cfg = RealFetcherConfig(serper_api_key="x")
    transport = httpx.MockTransport(
        _serper_handler(
            {
                "organic": [
                    {"title": "no link"},
                    {"link": "https://nejm.org/a", "title": "ok"},
                ]
            }
        )
    )
    with httpx.Client(transport=transport) as client:
        results = _fetch_serper("q", cfg, client)
    assert len(results) == 1


def test_fetch_serper_handles_empty_organic():
    cfg = RealFetcherConfig(serper_api_key="x")
    transport = httpx.MockTransport(_serper_handler({"organic": []}))
    with httpx.Client(transport=transport) as client:
        results = _fetch_serper("q", cfg, client)
    assert results == []


def test_fetch_serper_raises_on_http_error():
    cfg = RealFetcherConfig(serper_api_key="x")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            _fetch_serper("q", cfg, client)


# ---------- Semantic Scholar backend (mocked) ----------

def _s2_handler(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.semanticscholar.org"
        return httpx.Response(200, json=payload)

    return handler


def test_fetch_semantic_scholar_parses_papers():
    cfg = RealFetcherConfig(serper_api_key="x")
    transport = httpx.MockTransport(
        _s2_handler(
            {
                "data": [
                    {
                        "title": "RCT of aspirin",
                        "url": "https://www.semanticscholar.org/paper/abc",
                        "abstract": "Background... Methods... Results...",
                        "year": 2024,
                    },
                    {
                        "title": "Meta-analysis",
                        "url": "",
                        "externalIds": {"DOI": "10.1000/abc"},
                        "abstract": "",
                    },
                ]
            }
        )
    )
    with httpx.Client(transport=transport) as client:
        results = _fetch_semantic_scholar("q", cfg, client)
    assert len(results) == 2
    assert results[0].title == "RCT of aspirin"
    assert "Background" in results[0].snippet
    # DOI fallback
    assert results[1].url == "https://doi.org/10.1000/abc"


def test_fetch_semantic_scholar_skips_paper_without_url_or_doi():
    cfg = RealFetcherConfig(serper_api_key="x")
    transport = httpx.MockTransport(
        _s2_handler({"data": [{"title": "no url, no doi"}]})
    )
    with httpx.Client(transport=transport) as client:
        results = _fetch_semantic_scholar("q", cfg, client)
    assert results == []


def test_fetch_semantic_scholar_passes_api_key_when_set():
    cfg = RealFetcherConfig(serper_api_key="x", semantic_scholar_api_key="s2-key")
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        _fetch_semantic_scholar("q", cfg, client)
    assert seen_headers.get("x-api-key") == "s2-key"


def test_fetch_semantic_scholar_handles_429_with_retry():
    """A single 429 should trigger a backoff + retry. Persistent 429 fails."""
    cfg = RealFetcherConfig(
        serper_api_key="x", s2_rate_limit_seconds=0.01
    )
    state = {"calls": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        # Should NOT raise; retry succeeds on attempt 2
        results = _fetch_semantic_scholar("q", cfg, client)
    assert state["calls"] == 2
    assert results == []


def test_fetch_semantic_scholar_persistent_429_raises():
    cfg = RealFetcherConfig(
        serper_api_key="x", s2_rate_limit_seconds=0.01
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            _fetch_semantic_scholar("q", cfg, client)


# ---------- Combined RealFetcher orchestrator (mocked) ----------

def _combined_handler(serper_payload: dict, s2_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "google.serper.dev":
            return httpx.Response(200, json=serper_payload)
        if request.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json=s2_payload)
        return httpx.Response(404)

    return handler


def test_real_fetcher_merges_both_backends(monkeypatch: pytest.MonkeyPatch):
    cfg = RealFetcherConfig(serper_api_key="x", s2_rate_limit_seconds=0.01)
    fetcher = RealFetcher(config=cfg)

    transport = httpx.MockTransport(
        _combined_handler(
            serper_payload={
                "organic": [
                    {
                        "link": "https://www.cochrane.org/CD001",
                        "title": "Cochrane review",
                        "snippet": "snippet",
                    }
                ]
            },
            s2_payload={
                "data": [
                    {
                        "title": "Meta-analysis",
                        "url": "https://doi.org/10.1000/abc",
                        "abstract": "abstract",
                    }
                ]
            },
        )
    )

    # Monkeypatch httpx.Client to use the mock transport
    real_client_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    results = fetcher("aspirin headache")
    assert len(results) == 2
    urls = {r.url for r in results}
    assert "https://www.cochrane.org/CD001" in urls
    assert "https://doi.org/10.1000/abc" in urls


def test_real_fetcher_raises_when_both_backends_return_nothing(
    monkeypatch: pytest.MonkeyPatch,
):
    """LAW II fail-loud: empty Serper + empty S2 -> RuntimeError."""
    cfg = RealFetcherConfig(serper_api_key="x", s2_rate_limit_seconds=0.01)
    fetcher = RealFetcher(config=cfg)

    transport = httpx.MockTransport(
        _combined_handler(
            serper_payload={"organic": []},
            s2_payload={"data": []},
        )
    )
    real_client_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    with pytest.raises(RuntimeError, match="both Serper and Semantic Scholar"):
        fetcher("nothing-matches-this-query-xyzxyz")
