"""Tests for graph_route (I-snowball-002)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.graph_route import build_graph_payload, router


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, small_ir: SimpleNamespace) -> FastAPI:
    a = FastAPI()
    a.include_router(router, prefix="/api")

    def _find(rid: str) -> SimpleNamespace | None:
        if rid == small_ir.run_id:
            return SimpleNamespace(
                run_id=rid, slug=rid, domain="clinical", status="ok",
                artifact_dir=Path("/fake/dir"), cost_usd=0.0, word_count=0,
                contradictions_found=1, release_allowed=True, created_at_iso=None,
            )
        return None

    def _load(_: Path) -> SimpleNamespace:
        return small_ir

    # Patch the source modules (graph_route lazy-imports them inside the
    # route handler per Codex diff iter 1 P1 fix).
    from polaris_graph.audit_ir import registry as _registry
    from polaris_graph.audit_ir import loader as _loader
    monkeypatch.setattr(_registry, "find_run_by_id", _find)
    monkeypatch.setattr(_loader, "load_audit_ir", _load)
    return a


def test_404_for_missing_run(app: FastAPI) -> None:
    client = TestClient(app)
    r = client.get("/api/runs/no_such_run/graph")
    assert r.status_code == 404


def test_422_on_audit_ir_load_failure(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, small_ir: SimpleNamespace,
) -> None:
    def _raise(_: Path) -> SimpleNamespace:
        raise ValueError("synthetic load failure")

    from polaris_graph.audit_ir import loader as _loader
    monkeypatch.setattr(_loader, "load_audit_ir", _raise)
    client = TestClient(app)
    r = client.get(f"/api/runs/{small_ir.run_id}/graph")
    assert r.status_code == 422
    assert "load failed" in r.json()["detail"]


def test_returns_payload_with_diagnostics(app: FastAPI, small_ir: SimpleNamespace) -> None:
    client = TestClient(app)
    r = client.get(f"/api/runs/{small_ir.run_id}/graph")
    assert r.status_code == 200
    payload = r.json()
    diag = payload["diagnostics"]
    # 2 bib sources; 1 referenced-missing (ev_missing); 1 missing occurrence (only sent B)
    assert diag["bibliography_count"] == 2
    assert diag["fallback_source_count"] == 1
    assert diag["missing_reference_occurrence_count"] == 1
    assert diag["referenced_unknown_evidence_ids"] == ["ev_missing"]


def test_no_dangling_edges(small_ir: SimpleNamespace) -> None:
    payload = build_graph_payload(small_ir)
    node_ids = {n.data.id for n in payload.elements.nodes}
    for edge in payload.elements.edges:
        assert edge.data.source in node_ids, f"dangling source: {edge.data.source}"
        assert edge.data.target in node_ids, f"dangling target: {edge.data.target}"


def test_deterministic_byte_equal(small_ir: SimpleNamespace) -> None:
    p1 = build_graph_payload(small_ir)
    p2 = build_graph_payload(small_ir)
    assert p1.elements_hash == p2.elements_hash


def test_section_member_edges_match_kept_sentences(small_ir: SimpleNamespace) -> None:
    payload = build_graph_payload(small_ir)
    section_member_count = sum(1 for e in payload.elements.edges if e.data.edge_type == "section_member")
    # 2 kept sentences (Safety:verified:0 + Safety:verified:1); 1 dropped excluded
    assert section_member_count == 2


def test_self_contradiction_skipped(small_ir: SimpleNamespace) -> None:
    # Replace the cluster with a single-evidence_id cluster (self-contradiction shape)
    self_cluster = SimpleNamespace(
        cluster_id=99, subject="x", predicate="x", severity="low",
        absolute_difference=0.0, relative_difference=0.0, recommended_action="ignore",
        claims=(SimpleNamespace(
            evidence_id="ev_001", subject="x", predicate="x", arm="", dose="",
            value=0.0, unit="", source_tier="T1", source_url="", context_snippet="",
            endpoint_phrase="",
        ),),
    )
    small_ir.contradictions = (self_cluster,)
    payload = build_graph_payload(small_ir)
    contradicts = [e for e in payload.elements.edges if e.data.edge_type == "contradicts"]
    assert contradicts == [], "single-evidence_id cluster must NOT emit contradicts edges"


def test_frame_status_normalization(small_ir: SimpleNamespace) -> None:
    payload = build_graph_payload(small_ir)
    frame_nodes = [n for n in payload.elements.nodes if n.data.type == "frame"]
    statuses = {n.data.id: n.data.frame_status for n in frame_nodes}
    assert statuses["frame:efficacy_endpoint"] == "pass"
    assert statuses["frame:safety_endpoint"] == "fail"  # fail_min_fields → fail


def test_normalize_frame_status_generation_failed_maps_to_fail() -> None:
    """I-ready-017 FX-07b leg-2 (#1111) Codex diff-gate iter-1 P2: the
    frame_coverage honesty override emits status='generation_failed' for a
    pipeline-fault slot (drafted prose fully dropped by strict_verify). The
    graph inspector must render it as a failed frame, not frame_status null."""
    from polaris_graph.api.graph_route import _normalize_frame_status
    assert _normalize_frame_status("generation_failed") == "fail"
    # I-ready-017 FX-07b leg-2 (#1111) root-cause design: the curator-gap
    # honesty status also renders as a failed frame (not null).
    assert _normalize_frame_status("curator_gap_no_substantive_content") == "fail"
    # Unchanged mappings still hold.
    assert _normalize_frame_status("pass") == "pass"
    assert _normalize_frame_status("partial") == "partial"
    assert _normalize_frame_status("fail_min_fields") == "fail"
    # Genuinely unknown statuses still fall through to None.
    assert _normalize_frame_status("some_unknown_status") is None


def test_graph_route_mounted_in_create_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke: graph route must be mounted in the serving FastAPI app.

    Blank real-backend env vars before importing create_app so the mount
    check doesn't accidentally trigger GPG / Serper / OpenRouter wiring
    (Codex diff iter 2 P1).
    """
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "")
    monkeypatch.setenv("SERPER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("POLARIS_BENCHMARK_RESULTS_DIR", "")

    from polaris_v6.api.app import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert any("/api/runs/{run_id}/graph" in p for p in paths), \
        f"graph route not mounted; paths sample: {[p for p in paths if '/api/runs' in p][:5]}"
