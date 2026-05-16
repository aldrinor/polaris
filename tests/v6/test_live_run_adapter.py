"""I-rdy-008 — tests for live_run_adapter + the rewired rich-UI endpoints.

Covers the resolver error matrix, all 6 adapter decisions, and a live-path
test per rewired endpoint (bundle / charts / follow-up / compare). The golden
fixture fallback is also exercised so the pre-existing endpoint tests' contract
is shown to survive.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


def _synthetic_artifact(tmp_path: Path, **kwargs) -> Path:
    """Reuse the I-arch-001d synthetic AuditIR artifact-dir builder."""
    from tests.polaris_v6.api.test_artifact_to_slice_chain import (
        _write_synthetic_artifact_dir,
    )

    return _write_synthetic_artifact_dir(tmp_path, **kwargs)


def _artifact_with_pool(tmp_path: Path, *, pool: dict | None = None, **kwargs) -> Path:
    """Synthetic artifact_dir + an evidence_pool.json (the helper omits it)."""
    artifact_dir = _synthetic_artifact(tmp_path, **kwargs)
    pool = pool or {
        "sources": [
            {"evidence_id": "ev_001", "full_text": "A" * 150},
            {"evidence_id": "ev_002", "full_text": "B" * 150},
        ]
    }
    (artifact_dir / "evidence_pool.json").write_text(json.dumps(pool))
    return artifact_dir


def _completed_run(
    artifact_dir: Path, *, pipeline_status: str = "success", cost_usd: float = 0.42
) -> str:
    """Insert a completed run_store row pointing at `artifact_dir`."""
    from polaris_v6.queue import run_store

    run_id = uuid.uuid4().hex
    run_store.insert_run(run_id, "clinical", "test question")
    run_store.mark_in_progress(run_id)
    run_store.set_pipeline_meta(run_id, artifact_dir=str(artifact_dir))
    run_store.mark_completed(
        run_id, {}, pipeline_status=pipeline_status, cost_usd=cost_usd
    )
    return run_id


@pytest.fixture(autouse=True)
def _temp_run_db(tmp_path, monkeypatch):
    """Point run_store at a fresh per-test SQLite db."""
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "runs.sqlite"))
    yield


# ---------------------------------------------------------------------------
# resolve_run — error-state matrix
# ---------------------------------------------------------------------------


def test_resolve_run_404_not_found():
    from fastapi import HTTPException

    from polaris_v6.api.live_run_adapter import resolve_run

    with pytest.raises(HTTPException) as exc:
        resolve_run("no_such_run")
    assert exc.value.status_code == 404


def test_resolve_run_404_not_completed():
    from fastapi import HTTPException

    from polaris_v6.api.live_run_adapter import resolve_run
    from polaris_v6.queue import run_store

    run_id = uuid.uuid4().hex
    run_store.insert_run(run_id, "clinical", "q")  # stays 'queued'
    with pytest.raises(HTTPException) as exc:
        resolve_run(run_id)
    assert exc.value.status_code == 404


def test_resolve_run_422_aborted(tmp_path):
    from fastapi import HTTPException

    from polaris_v6.api.live_run_adapter import resolve_run

    artifact_dir = _artifact_with_pool(tmp_path)
    run_id = _completed_run(artifact_dir, pipeline_status="abort_no_verified_sections")
    with pytest.raises(HTTPException) as exc:
        resolve_run(run_id)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# artifact_dir_to_evidence_contract — happy path + the 6 adapter decisions
# ---------------------------------------------------------------------------


def test_adapter_happy_path(tmp_path):
    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    artifact_dir = _artifact_with_pool(tmp_path)
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    ec = artifact_dir_to_evidence_contract(resolved, info)

    assert ec.contract_version == "1.0"
    assert ec.run_id == run_id
    assert ec.pipeline_status == "success"
    # evidence_pool: exactly one SourceSpan per distinct cited evidence_id.
    ids = [s.evidence_id for s in ec.evidence_pool]
    assert sorted(ids) == ["ev_001", "ev_002"]
    assert len(ids) == len(set(ids))
    assert all(s.source_tier in ("T1", "T2", "T3") for s in ec.evidence_pool)
    assert ec.verified_sentences  # non-empty
    # dec-1: model identity from manifest.models (no provenance files present).
    assert ec.generator_model == "gen-synth-v1"
    assert ec.verifier_model == "strict_verify_v1"


def test_adapter_404_missing_evidence_pool(tmp_path):
    from fastapi import HTTPException

    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    artifact_dir = _synthetic_artifact(tmp_path)  # NO evidence_pool.json
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    with pytest.raises(HTTPException) as exc:
        artifact_dir_to_evidence_contract(resolved, info)
    assert exc.value.status_code == 404


def test_adapter_dec5_tier_normalization(tmp_path):
    """A non-T1/2/3 bibliography tier collapses to T3 — no ValidationError."""
    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    bib = [
        {"num": 1, "evidence_id": "ev_t5", "statement": "s",
         "tier": "T5", "url": "https://example.org/x"}
    ]
    artifact_dir = _artifact_with_pool(
        tmp_path,
        bibliography_entries=bib,
        pool={"sources": [{"evidence_id": "ev_t5", "full_text": "Z" * 150}]},
    )
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    ec = artifact_dir_to_evidence_contract(resolved, info)
    assert ec.evidence_pool
    assert all(s.source_tier == "T3" for s in ec.evidence_pool)


def test_adapter_dec6_span_clamp(tmp_path):
    """Token span [0:100] over a 40-char body clamps to [0:40]."""
    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    bib = [
        {"num": 1, "evidence_id": "ev_001", "statement": "s",
         "tier": "T1", "url": "https://example.org/x"}
    ]
    body = "C" * 40
    artifact_dir = _artifact_with_pool(
        tmp_path,
        bibliography_entries=bib,
        pool={"sources": [{"evidence_id": "ev_001", "full_text": body}]},
    )
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    ec = artifact_dir_to_evidence_contract(resolved, info)
    span = next(s for s in ec.evidence_pool if s.evidence_id == "ev_001")
    assert span.span_end == 40
    assert span.span_text == body


def test_adapter_dec1_model_identity_422(tmp_path):
    """No model_provenance files + no manifest.models block → 422."""
    from fastapi import HTTPException

    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    artifact_dir = _artifact_with_pool(tmp_path)
    manifest = json.loads((artifact_dir / "manifest.json").read_text())
    del manifest["models"]
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    with pytest.raises(HTTPException) as exc:
        artifact_dir_to_evidence_contract(resolved, info)
    assert exc.value.status_code == 422


def test_adapter_dec4_contradiction_projection(tmp_path):
    """A 2-claim contradiction cluster → one ContradictionRecord."""
    from polaris_v6.api.live_run_adapter import (
        artifact_dir_to_evidence_contract,
        resolve_run,
    )

    artifact_dir = _artifact_with_pool(tmp_path)
    contradictions = [
        {
            "subject": "tirzepatide",
            "predicate": "body weight",
            "claims": [
                {"evidence_id": "ev_001", "predicate": "body weight",
                 "value": 5.0, "context_snippet": "5% loss at 10 mg"},
                {"evidence_id": "ev_002", "predicate": "body weight",
                 "value": 10.0, "context_snippet": "10% loss at 10 mg"},
            ],
        }
    ]
    (artifact_dir / "contradictions.json").write_text(json.dumps(contradictions))
    run_id = _completed_run(artifact_dir)
    info, resolved = resolve_run(run_id)
    ec = artifact_dir_to_evidence_contract(resolved, info)
    assert len(ec.contradictions) == 1
    rec = ec.contradictions[0]
    assert rec.evidence_a == ["ev_001"]
    assert "ev_002" in rec.evidence_b
    assert rec.resolution == "unresolved"


# ---------------------------------------------------------------------------
# Live-path endpoint tests — a real completed run_id resolves end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    try:
        # NB: importing polaris_v6.api.app triggers a module-level
        # `app = create_app()` (app.py), which eagerly builds the GPG signer.
        # A host without the `gpg` binary cannot construct the app — the whole
        # v6 endpoint suite is gpg-gated this way (CI provides gpg). Skip
        # rather than error so a gpg-less dev box gives a clean signal.
        from polaris_v6.api.app import create_app

        app = create_app()
    except OSError as exc:
        pytest.skip(f"create_app() requires the gpg binary, unavailable here: {exc}")
    return TestClient(app)


def test_endpoint_bundle_live_run(client, tmp_path):
    run_id = _completed_run(_artifact_with_pool(tmp_path))
    resp = client.get(f"/runs/{run_id}/bundle")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id


def test_endpoint_charts_live_run(client, tmp_path):
    run_id = _completed_run(_artifact_with_pool(tmp_path))
    resp = client.get(f"/runs/{run_id}/charts/forest_plot")
    assert resp.status_code == 200


def test_endpoint_followup_live_run(client, tmp_path):
    run_id = _completed_run(_artifact_with_pool(tmp_path))
    resp = client.post(f"/runs/{run_id}/followup", json={"question": "what dose works?"})
    assert resp.status_code == 200


def test_endpoint_compare_live_runs(client, tmp_path):
    run_a = _completed_run(_artifact_with_pool(tmp_path / "a"))
    run_b = _completed_run(_artifact_with_pool(tmp_path / "b"))
    resp = client.get(f"/runs/{run_a}/compare/{run_b}")
    assert resp.status_code == 200


def test_endpoint_bundle_golden_fallback_intact(client):
    """A golden fixture id (no run_store row) still resolves via the fallback."""
    resp = client.get("/runs/golden_clinical_001/bundle")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "golden_clinical_001"
