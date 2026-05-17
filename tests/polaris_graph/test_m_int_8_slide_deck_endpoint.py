"""M-INT-8 — M-22 slide deck endpoint exposed in inspector_router.

Acceptance bar:
  1. Endpoint exists: GET /api/inspector/runs/{slug}/slide-deck (json)
                      GET /api/inspector/runs/{slug}/slide-deck.html (html)
  2. Wraps build_slide_deck + deck_to_dict / render_deck_html
  3. 404 when slug unknown
  4. 500 / structured error when IR missing or empty report
  5. PG_USE_SLIDE_DECK_ENDPOINT=0 returns 404 (rollback)
  6. AuthZ: requires authenticated caller (M-15b retrofit)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_client() -> TestClient:
    from src.polaris_graph.audit_ir.inspector_router import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(
        app,
        headers={"X-Polaris-Caller": "org_default:usr_test:owner"},
    )


def test_slide_deck_endpoint_imported() -> None:
    """The endpoint registration imports the slide_deck substrate."""
    router_mod = importlib.import_module(
        "src.polaris_graph.audit_ir.inspector_router"
    )
    assert hasattr(router_mod, "build_slide_deck")
    assert hasattr(router_mod, "deck_to_dict")
    assert hasattr(router_mod, "render_deck_html")


def test_slide_deck_json_returns_deck_for_canonical_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    # Either 200 with deck or 500 if canonical IR is missing in test env;
    # we only assert it's not 404 (the endpoint exists) and not 401/403.
    assert response.status_code in {200, 500}
    if response.status_code == 200:
        body = response.json()
        assert "slides" in body
        assert isinstance(body["slides"], list)
        assert len(body["slides"]) >= 1
        # Title slide always first (deck_to_dict uses `layout` field).
        first_slide = body["slides"][0]
        assert first_slide.get("layout") == "title", (
            f"expected layout='title' on first slide; got {first_slide!r}"
        )


def test_slide_deck_html_returns_html_for_canonical_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck.html",
    )
    assert response.status_code in {200, 500}
    if response.status_code == 200:
        assert "text/html" in response.headers["content-type"]
        assert "<html" in response.text.lower() or \
               "<!doctype" in response.text.lower() or \
               "<div" in response.text.lower()


def test_slide_deck_unknown_slug_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    response = client.get(
        "/api/inspector/runs/nonexistent_slug/slide-deck",
    )
    assert response.status_code == 404
    body = response.json()
    assert "Unknown" in body["detail"] or "not found" in body["detail"].lower()


def test_slide_deck_html_unknown_slug_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    client = _make_client()
    response = client.get(
        "/api/inspector/runs/nonexistent_slug/slide-deck.html",
    )
    assert response.status_code == 404


def test_disabled_flag_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PG_USE_SLIDE_DECK_ENDPOINT=0 → endpoint returns 404 (feature off)."""
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "0")
    client = _make_client()
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    assert response.status_code == 404


def test_slide_deck_endpoint_requires_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-15b retrofit: every endpoint requires an authenticated caller."""
    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    from src.polaris_graph.audit_ir.inspector_router import router
    from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    app = FastAPI()
    app.include_router(router)
    # No X-Polaris-Caller header — should be rejected.
    client = TestClient(app)
    response = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    assert response.status_code in {401, 403}


# ---------------------------------------------------------------------------
# Codex round-1 LOW fix (v2) — explicit error-path coverage
# ---------------------------------------------------------------------------


def _build_minimal_audit_ir():
    """Build an AuditIR with sentences_verified=0 to force
    SlideDeckEmptyReportError on build_slide_deck."""
    from pathlib import Path as _P
    from types import MappingProxyType
    from src.polaris_graph.audit_ir.loader import (
        AdequacyGate, AuditIR, BibliographyEntry, EvaluatorGate,
        FrameCoverageReport, IR_SCHEMA_VERSION, ReportSection,
        RunManifest, TierMix, VerifiedReport,
    )
    section = ReportSection(
        title="Findings", kept_count=0, dropped_count=0, total_in=0,
        dropped_due_to_failure=0, sentences=(),
    )
    vr = VerifiedReport(
        sections=(section,),
        sentences_verified=0,
        sentences_dropped=0,
        drop_reason_counts=MappingProxyType({}),
    )
    manifest = RunManifest(
        run_id="run_empty", slug="empty", status="success",
        question="q", protocol_sha256="0" * 64,
        cost_usd=0.0, budget_cap_usd=1.0, word_count=0,
        sentences_verified=0, sentences_dropped=0,
        contradictions_found=0, completeness_percent=0.0,
        evaluator_gate=EvaluatorGate(
            gate_class="pass", release_allowed=True, reasons=(),
            rule_blockers=(), judge_critical_axes=(),
            judge_parse_ok=True,
        ),
        release_allowed=True, v30_enabled=True, v30_warnings=(),
        retrieval_stats=None,
    )
    fc = FrameCoverageReport(
        pass_count=0, partial_count=0, frame_gap_count=0,
        pipeline_fault_count=0, total_entities=0, total_slots=0,
        research_question="q", schema_version="1.0",
        semantics_warning=None, entries=(),
    )
    adequacy = AdequacyGate(
        decision="proceed", findings_ok=0, findings_total=0,
        critical_count=0,
    )
    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION, run_id="run_empty",
        artifact_dir=_P("."), report_md="", manifest=manifest,
        bibliography=(BibliographyEntry(
            num=1, evidence_id="ev_a", statement="s", tier="T1",
            url="https://x.example",
        ),),
        contradictions=(), frame_coverage=fc,
        tier_mix=TierMix(
            fractions=MappingProxyType({"T1": 1.0}),
            corpus_count=1, approved=True, material_deviation=False,
        ),
        verified_report=vr,
        model_provenance=None, protocol=None,
        adequacy=adequacy, corpus_approval=None,
    )


def test_slide_deck_empty_report_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 LOW: explicit test that an empty report
    (sentences_verified=0) returns 422 not 500."""
    from pathlib import Path as _P
    from src.polaris_graph.audit_ir import inspector_router as ir_mod
    from src.polaris_graph.audit_ir.registry import RunSummary

    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    fake_summary = RunSummary(
        slug="empty", run_id="run_empty", domain="clinical",
        status="success", artifact_dir=_P("."),
        cost_usd=0.0, word_count=0, contradictions_found=0,
        release_allowed=True, created_at_iso=None,
    )
    monkeypatch.setattr(
        ir_mod, "find_run_by_slug",
        lambda s: fake_summary if s == "empty" else None,
    )
    monkeypatch.setattr(
        ir_mod, "load_audit_ir",
        lambda d: _build_minimal_audit_ir(),
    )
    client = _make_client()
    response = client.get("/api/inspector/runs/empty/slide-deck")
    assert response.status_code == 422
    body = response.json()
    assert "empty report" in body["detail"].lower()


def test_slide_deck_html_empty_report_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same as above for the HTML variant."""
    from pathlib import Path as _P
    from src.polaris_graph.audit_ir import inspector_router as ir_mod
    from src.polaris_graph.audit_ir.registry import RunSummary

    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    fake_summary = RunSummary(
        slug="empty_html", run_id="run_empty_html", domain="clinical",
        status="success", artifact_dir=_P("."),
        cost_usd=0.0, word_count=0, contradictions_found=0,
        release_allowed=True, created_at_iso=None,
    )
    monkeypatch.setattr(
        ir_mod, "find_run_by_slug",
        lambda s: fake_summary if s == "empty_html" else None,
    )
    monkeypatch.setattr(
        ir_mod, "load_audit_ir",
        lambda d: _build_minimal_audit_ir(),
    )
    client = _make_client()
    response = client.get(
        "/api/inspector/runs/empty_html/slide-deck.html",
    )
    assert response.status_code == 422


def test_slide_deck_ir_load_failure_returns_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 LOW: explicit test that IR load failure
    (FileNotFoundError) maps to 500."""
    from pathlib import Path as _P
    from src.polaris_graph.audit_ir import inspector_router as ir_mod
    from src.polaris_graph.audit_ir.registry import RunSummary

    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    fake_summary = RunSummary(
        slug="missing_ir", run_id="run_missing", domain="clinical",
        status="success", artifact_dir=_P("/nonexistent/path"),
        cost_usd=0.0, word_count=0, contradictions_found=0,
        release_allowed=True, created_at_iso=None,
    )
    monkeypatch.setattr(
        ir_mod, "find_run_by_slug",
        lambda s: fake_summary if s == "missing_ir" else None,
    )

    def _raise_missing(*args, **kwargs):
        raise FileNotFoundError("IR not found at this path")

    monkeypatch.setattr(ir_mod, "load_audit_ir", _raise_missing)
    client = _make_client()
    response = client.get("/api/inspector/runs/missing_ir/slide-deck")
    assert response.status_code == 500
    body = response.json()
    assert "Failed to load IR" in body["detail"]


def test_slide_deck_build_failure_returns_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 LOW: explicit test that build_slide_deck
    raising SlideDeckError (not the empty-report subclass)
    maps to 500."""
    from pathlib import Path as _P
    from src.polaris_graph.audit_ir import inspector_router as ir_mod
    from src.polaris_graph.audit_ir.registry import RunSummary
    from src.polaris_graph.audit_ir.slide_deck import SlideDeckError

    monkeypatch.setenv("PG_USE_SLIDE_DECK_ENDPOINT", "1")
    fake_summary = RunSummary(
        slug="build_fail", run_id="run_build_fail", domain="clinical",
        status="success", artifact_dir=_P("."),
        cost_usd=0.0, word_count=0, contradictions_found=0,
        release_allowed=True, created_at_iso=None,
    )
    monkeypatch.setattr(
        ir_mod, "find_run_by_slug",
        lambda s: fake_summary if s == "build_fail" else None,
    )
    monkeypatch.setattr(
        ir_mod, "load_audit_ir",
        lambda d: _build_minimal_audit_ir(),  # any IR works
    )

    def _broken_build(*args, **kwargs):
        raise SlideDeckError("simulated build failure (non-empty)")

    monkeypatch.setattr(ir_mod, "build_slide_deck", _broken_build)
    client = _make_client()
    response = client.get("/api/inspector/runs/build_fail/slide-deck")
    assert response.status_code == 500
    body = response.json()
    assert "build failed" in body["detail"]
