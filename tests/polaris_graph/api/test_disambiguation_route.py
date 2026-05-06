"""Tests for I-f2-003 — disambiguation route + adapter wiring (hermetic)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.disambiguation_route import (
    _make_openrouter_label_client, get_label_client, router,
)


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses, self.calls = list(responses), []

    def complete(self, prompt: str, *, max_tokens: int = 50) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else "fallback"


def _app(client_obj):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_label_client] = lambda: client_obj
    return app


def _two_cluster_payload() -> dict:
    return {"candidates":
        [{"text": f"a{i}", "embedding": [1.0, 0.0]} for i in range(3)]
        + [{"text": f"b{i}", "embedding": [0.0, 1.0]} for i in range(3)]}


def test_post_returns_clusters() -> None:
    fake = FakeClient(["syndrome", "institute"])
    r = TestClient(_app(fake)).post("/api/disambiguation", json=_two_cluster_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_ambiguous"] is True and body["num_clusters"] == 2
    assert {c["label"] for c in body["clusters"]} == {"syndrome", "institute"}
    assert len(fake.calls) == 2


def test_single_cluster_unambiguous_skips_labeling() -> None:
    fake = FakeClient(["unused"])
    payload = {"candidates": [{"text": f"x{i}", "embedding": [1.0 + i * 0.001, 0.0]} for i in range(4)]}
    r = TestClient(_app(fake)).post("/api/disambiguation", json=payload)
    assert r.status_code == 200 and r.json()["is_ambiguous"] is False and r.json()["clusters"] == [] and len(fake.calls) == 0


def test_no_clusters_skips_labeling() -> None:
    fake = FakeClient(["unused"])
    r = TestClient(_app(fake)).post("/api/disambiguation",
        json={"candidates": [{"text": "lone", "embedding": [1.0, 0.0]}]})
    assert r.status_code == 200 and r.json()["num_clusters"] == 0 and r.json()["clusters"] == [] and len(fake.calls) == 0


def test_embedding_dim_mismatch_400() -> None:
    payload = {"candidates": [{"text": "a", "embedding": [1.0, 0.0]},
                              {"text": "b", "embedding": [1.0, 0.0, 0.0]}]}
    r = TestClient(_app(FakeClient([]))).post("/api/disambiguation", json=payload)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "embedding_dim_mismatch"


def test_empty_candidates_422() -> None:
    r = TestClient(_app(FakeClient([]))).post("/api/disambiguation", json={"candidates": []})
    assert r.status_code == 422


def test_no_label_client_503_only_when_ambiguous() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_label_client] = lambda: None
    r = TestClient(app).post("/api/disambiguation", json=_two_cluster_payload())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "label_client_unavailable"


def test_health_endpoint() -> None:
    r = TestClient(_app(FakeClient([]))).get("/api/disambiguation/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and "label_client" in r.json()


def test_create_app_mounts_router_and_env_unset_factory_returns_none(
        monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("SERPER_API_KEY", "OPENROUTER_API_KEY", "POLARIS_GPG_KEY_ID",
              "OTEL_SEMCONV_STABILITY_OPT_IN", "SEMANTIC_SCHOLAR_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert _make_openrouter_label_client() is None
    from polaris_v6.api.app import create_app
    paths = set(create_app().openapi()["paths"].keys())
    assert "/api/disambiguation" in paths and "/api/disambiguation/health" in paths
