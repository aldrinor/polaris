"""Tests for the audit-bundle FastAPI route."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.audit_bundle_route import get_sign_fn, router


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


def _stub_sign(payload: bytes) -> bytes:
    digest = hashlib.sha256(payload).hexdigest()
    return (
        f"-----BEGIN PGP SIGNATURE-----\n# stub hash={digest}\n-----END PGP SIGNATURE-----\n"
    ).encode("utf-8")


def _override_sign(app: FastAPI):
    def stub_provider():
        return _stub_sign

    app.dependency_overrides[get_sign_fn] = stub_provider


def _payload(verdict: str = "success", pool_id: str = "pool-1") -> dict:
    """Build a request body that satisfies the FK chain + verdict."""
    iso = datetime.now(timezone.utc).isoformat()
    decision = {
        "decision_id": "dec-1",
        "status": "in_scope",
        "scope_class": "clinical_efficacy",
        "ambiguity_axes": [
            {
                "axis": "population",
                "plausible_interpretations": ["adults"],
                "needs_clarification": False,
            }
        ],
        "clarifications_needed": [],
        "provenance": {},
        "latency_ms": 0,
    }
    pool = {
        "pool_id": pool_id,
        "decision_id": "dec-1",
        "sources": [
            {
                "source_id": "src-A",
                "url": "https://www.cochrane.org/CD001",
                "domain": "cochrane.org",
                "tier": "T1",
                "title": "Source",
                "publication_date": None,
                "authors": [],
                "snippet": "snippet",
                "full_text_available": True,
                "full_text": "trial of aspirin",
                "fetched_at_utc": iso,
                "provenance": {},
            }
        ],
        "adequacy": {
            "is_adequate": True,
            "sources_per_tier": {"T1": 1, "T2": 0, "T3": 0},
            "min_required_per_tier": {"T1": 0, "T2": 0, "T3": 0},
            "failure_reason": None,
        },
        "queries_executed": [],
        "retrieval_started_at_utc": iso,
        "retrieval_finished_at_utc": iso,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    if verdict == "success":
        sections = [
            {
                "section_id": "sec_x",
                "section_title": "X",
                "verified_sentences": [
                    {
                        "section_id": "sec_x",
                        "sentence_text": "claim [#ev:src-A:0-3].",
                        "provenance_tokens": ["[#ev:src-A:0-3]"],
                        "verifier_pass": True,
                        "drop_reason": None,
                    }
                ],
                "section_verify_pass_rate": 1.0,
                "section_status": "verified",
            }
        ]
    else:
        sections = [
            {
                "section_id": "sec_x",
                "section_title": "X",
                "verified_sentences": [
                    {
                        "section_id": "sec_x",
                        "sentence_text": "bad",
                        "provenance_tokens": [],
                        "verifier_pass": False,
                        "drop_reason": "no_provenance_token",
                    }
                ],
                "section_verify_pass_rate": 0.0,
                "section_status": "dropped",
            }
        ]
    report = {
        "pool_id": pool_id,
        "decision_id": "dec-1",
        "sections": sections,
        "overall_verify_pass_rate": 1.0 if verdict == "success" else 0.0,
        "pipeline_verdict": verdict,
        "generator_model": "test/model",
        "verifier_pass_threshold": 0.4,
        "started_at_utc": iso,
        "finished_at_utc": iso,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    return {"decision": decision, "pool": pool, "report": report}


# ---------- Health ----------

def test_health(app: FastAPI):
    r = TestClient(app).get("/api/audit-bundle/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_004_audit_bundle_export"
    assert "gpg_sign" in body["pipeline_stages"]


# ---------- 503 (no signer) ----------

def test_post_without_sign_fn_returns_503(app: FastAPI):
    """No signer dep override -> sentinel default -> HTTP 503 (gpg unavailable)."""
    r = TestClient(app).post("/api/audit-bundle", json=_payload())
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "gpg_unavailable"


# ---------- 400 paths ----------

def test_post_pool_id_mismatch_returns_400(app: FastAPI):
    _override_sign(app)
    payload = _payload(pool_id="pool-A")
    payload["report"]["pool_id"] = "pool-B"  # mismatch
    r = TestClient(app).post("/api/audit-bundle", json=payload)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "fk_chain_mismatch"


def test_post_decision_id_mismatch_returns_400(app: FastAPI):
    _override_sign(app)
    payload = _payload()
    payload["report"]["decision_id"] = "dec-OTHER"  # mismatch
    r = TestClient(app).post("/api/audit-bundle", json=payload)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "fk_chain_mismatch"


def test_post_non_success_verdict_returns_400(app: FastAPI):
    _override_sign(app)
    r = TestClient(app).post(
        "/api/audit-bundle", json=_payload(verdict="abort_no_verified_sections")
    )
    # Pydantic validates first; abort+verdict-mismatch may yield 422 or 400
    assert r.status_code in (400, 422)


# ---------- 502 (sign failed) ----------

def test_post_sign_fn_raises_returns_502(app: FastAPI):
    def boom_provider():
        def fn(_payload: bytes) -> bytes:
            raise OSError("simulated gpg crash")
        return fn

    app.dependency_overrides[get_sign_fn] = boom_provider
    r = TestClient(app).post("/api/audit-bundle", json=_payload())
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "sign_failed"


# ---------- Happy path ----------

def test_post_returns_targz(app: FastAPI, tmp_path: Path):
    _override_sign(app)
    r = TestClient(app).post("/api/audit-bundle", json=_payload())
    assert r.status_code == 200
    # Content-Disposition should set the filename for download
    cd = r.headers.get("content-disposition", "")
    assert "audit_" in cd
    assert ".tar.gz" in cd
    # Content-Type
    assert r.headers.get("content-type") == "application/gzip"
    # Body is a valid tarball
    assert tarfile.is_tarfile(io.BytesIO(r.content))


def test_post_targz_contains_manifest_and_signature(app: FastAPI):
    _override_sign(app)
    r = TestClient(app).post("/api/audit-bundle", json=_payload())
    assert r.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = [m.name for m in tar.getmembers()]
    assert any(n.endswith("manifest.yaml") and not n.endswith(".asc") for n in names)
    assert any(n.endswith("manifest.yaml.asc") for n in names)
    assert any(n.endswith("scope_decision.json") for n in names)
    assert any(n.endswith("evidence_pool.json") for n in names)
    assert any(n.endswith("verified_report.json") for n in names)


# ---------- 422 validation ----------

def test_post_missing_decision_returns_422(app: FastAPI):
    _override_sign(app)
    payload = _payload()
    del payload["decision"]
    r = TestClient(app).post("/api/audit-bundle", json=payload)
    assert r.status_code == 422


def test_post_malformed_pool_returns_422(app: FastAPI):
    _override_sign(app)
    payload = _payload()
    payload["pool"] = {"decision_id": "x"}  # missing required fields
    r = TestClient(app).post("/api/audit-bundle", json=payload)
    assert r.status_code in (400, 422)
