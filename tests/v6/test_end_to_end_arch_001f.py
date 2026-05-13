"""I-arch-001f — end-to-end capstone test for the I-arch-001a..001e seam.

POST /runs → simulate pipeline-A side-effects → GET /runs/{id} →
GET /stream/{id} → GET /stream/{id} with Last-Event-ID resume →
GET /runs/{id}/bundle.tar.gz → extract tar → cross-validate manifest.yaml
+ verified_report.json IDs.

Hermetic via fakeredis + synthetic AuditIR fixture (no real Redis, no LLM,
no network). Pins the I-arch-001a..001e architectural seam end-to-end so
any future drift breaks one obvious assertion. Brief APPROVE iter 3 of 5
at .codex/I-arch-001f/codex_brief_verdict_iter_3.txt.
"""

from __future__ import annotations

import io
import json
import tarfile

import pytest
import yaml

# Force StubBroker BEFORE importing actors / runs (tests/v6/conftest.py
# already does this, but be defensive when this module is collected alone).
pytest.importorskip("dramatiq")
pytest.importorskip("fakeredis")
pytest.importorskip("fastapi")
pytest.importorskip("sse_starlette")

from polaris_v6.queue import run_events as _run_events_module
from polaris_v6.queue import run_store
from polaris_graph.api.audit_bundle_route import get_sign_fn

# Reuse the synthetic AuditIR fixture builder from I-arch-001d tests.
from tests.polaris_v6.api.test_artifact_to_slice_chain import (
    _write_synthetic_artifact_dir,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_runs_db(tmp_path, monkeypatch):
    """Per Codex iter-2 P1-002: isolate POLARIS_V6_RUN_DB so the test does NOT
    write to state/v6_runs.sqlite or bleed into other tests."""
    db_path = tmp_path / "e2e_v6_runs.sqlite"
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(db_path))
    run_store.init_db(str(db_path))
    yield db_path


@pytest.fixture(autouse=True)
def flush_stub_broker():
    """Per Codex iter-3 P1-005: StubBroker uses flush_all(), not flush_queue().
    Guarded by hasattr so a real-Redis broker (no flush_all) is a no-op."""
    import dramatiq

    broker = dramatiq.get_broker()
    if hasattr(broker, "flush_all"):
        broker.flush_all()
    yield
    if hasattr(broker, "flush_all"):
        broker.flush_all()


@pytest.fixture
def fake_server():
    import fakeredis

    return fakeredis.FakeServer()


@pytest.fixture
def sync_fake(fake_server):
    import fakeredis

    return fakeredis.FakeStrictRedis(server=fake_server)


@pytest.fixture
def async_fake(fake_server):
    import fakeredis

    return fakeredis.aioredis.FakeRedis(server=fake_server)


@pytest.fixture
def app_with_v6_routers(isolated_runs_db):
    """Mount the v6 routers needed for the e2e chain: runs, stream, bundle."""
    from fastapi import FastAPI
    from polaris_v6.api import bundle as bundle_module
    from polaris_v6.api import runs as runs_module
    from polaris_v6.api import stream as stream_module

    app = FastAPI()
    app.include_router(runs_module.router)
    app.include_router(stream_module.router)
    app.include_router(bundle_module.router)
    return app


def _stub_sign_fn():
    """Per I-arch-001d test_get_bundle_targz_signer_override_fires."""
    def _sign(_data: bytes) -> bytes:
        return b"-----BEGIN PGP SIGNATURE-----\nstub\n-----END PGP SIGNATURE-----\n"

    return _sign


def _parse_sse_block(raw: str) -> list[dict]:
    """Parse SSE wire format into list of dicts with optional id/event/data."""
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    events: list[dict] = []
    for block in normalized.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        evt: dict = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                evt["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                evt["data"] = json.loads(line[len("data:"):].strip())
            elif line.startswith("id:"):
                evt["id"] = line[len("id:"):].strip()
        if evt.get("event"):
            events.append(evt)
    return events


# ---------------------------------------------------------------------------
# E2E capstone test
# ---------------------------------------------------------------------------


def test_e2e_post_run_through_stream_resume_and_bundle(
    app_with_v6_routers,
    isolated_runs_db,
    fake_server,
    sync_fake,
    async_fake,
    tmp_path,
    monkeypatch,
):
    """Capstone test pinning POST/runs → stream → resume → bundle chain."""
    from fastapi.testclient import TestClient

    client = TestClient(app_with_v6_routers)

    # ----- Step 1: POST /runs ---------------------------------------------
    create_resp = client.post(
        "/runs", json={"template": "clinical", "question": "synthetic question"}
    )
    assert create_resp.status_code == 202, create_resp.text
    create_body = create_resp.json()
    posted_run_id = create_body["run_id"]
    assert create_body["lifecycle_status"] == "queued"

    # ----- Step 2: simulate pipeline-A side-effects -----------------------
    # 2a. Build a synthetic AuditIR-shape artifact directory.
    artifact_dir = _write_synthetic_artifact_dir(tmp_path)

    # 2b. Patch the source manifest.json to thread the POST uuid + decision_id
    #     consistently — per Codex iter-2 P1-001. The augment_v6_manifest helper
    #     would normally do this inside pipeline-A; in the test we set the
    #     final values directly so artifact_to_slice_chain produces a
    #     ScopeDecision with our decision_id.
    manifest_path = artifact_dir / "manifest.json"
    src_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    src_manifest["external_run_id"] = posted_run_id
    src_manifest["scope"]["decision_id"] = f"dec-{posted_run_id}"
    src_manifest["slug"] = "synthetic_e2e"
    manifest_path.write_text(json.dumps(src_manifest, sort_keys=True), encoding="utf-8")

    # 2b-bis. Per Codex diff iter-1 P1: write evidence_pool.json so source
    # full_text is long enough to cover the cited span (0-100). Without this,
    # `snapshot_sources` raises 'cited span unreachable after snapshot' and
    # the bundle endpoint returns HTTP 400 instead of the 200 tar.gz this
    # test must verify.
    evidence_pool_path = artifact_dir / "evidence_pool.json"
    long_text = (
        "Pinned-fixture evidence body intentionally padded to exceed the "
        "100-character span boundary so snapshot_sources can resolve the "
        "[#ev:ev_001:0-100] token cleanly. "
        "Padding lorem ipsum dolor sit amet consectetur adipiscing elit."
    )
    evidence_pool_path.write_text(json.dumps({
        "sources": [
            {"evidence_id": "ev_001", "full_text": long_text},
            {"evidence_id": "ev_002", "full_text": long_text},
        ],
    }, sort_keys=True), encoding="utf-8")

    # 2c. run_store transitions (the Phase-0 actor stub does NOT call these;
    #     the real pipeline-A actor will).
    run_store.mark_in_progress(posted_run_id, path=str(isolated_runs_db))
    run_store.set_pipeline_meta(
        posted_run_id,
        query_slug="synthetic_e2e",
        artifact_dir=str(artifact_dir),
        manifest_run_id=src_manifest["run_id"],
        decision_id=f"dec-{posted_run_id}",
        path=str(isolated_runs_db),
    )
    # 2d. Emit pipeline-A events into fakeredis.
    _run_events_module.emit_event(
        posted_run_id,
        "scope_gate.completed",
        {"decision": "in_scope", "reason": "synthetic"},
        redis_client=sync_fake,
    )
    _run_events_module.emit_terminal_event(
        posted_run_id, "success", redis_client=sync_fake,
    )
    # 2e. Final run_store transition.
    run_store.mark_completed(
        posted_run_id,
        {"manifest": {"status": "success"}, "status": "success"},
        pipeline_status="success",
        cost_usd=0.42,
        path=str(isolated_runs_db),
    )

    # ----- Step 3: GET /runs/{id} -----------------------------------------
    get_resp = client.get(f"/runs/{posted_run_id}")
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["lifecycle_status"] == "completed"
    assert get_body["pipeline_status"] == "success"

    # ----- Step 4: GET /stream/{id} ---------------------------------------
    # Monkeypatch stream module's read_events to feed pre-seeded fakeredis to
    # the async reader (same pattern as I-arch-001e tests).
    from polaris_v6.api import stream as stream_module
    real_read = _run_events_module.read_events

    async def _read_with_fake(run_id, last_event_id="0-0", *, block_ms=5000, redis_client_async=None):
        async for sid, raw in real_read(
            run_id, last_event_id=last_event_id, block_ms=50, redis_client_async=async_fake
        ):
            yield sid, raw

    monkeypatch.setattr(stream_module, "read_events", _read_with_fake)

    stream_resp = client.get(f"/stream/{posted_run_id}")
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    events_seen = _parse_sse_block(stream_resp.text)
    names = [e["event"] for e in events_seen]
    assert names == ["scope_decision", "run_complete"]
    first_event_id = events_seen[0]["id"]
    run_complete_payload = events_seen[1]["data"]
    assert run_complete_payload["run_id"] == posted_run_id
    assert run_complete_payload["status"] == "success"

    # ----- Step 5: GET /stream/{id} with Last-Event-ID resume -------------
    # Per Codex iter-2 P1-003: pin the resume semantics. After consuming
    # scope_decision, a reconnect with Last-Event-ID=<first_id> should
    # return only run_complete (replay starts after the consumed event).
    resume_resp = client.get(
        f"/stream/{posted_run_id}", headers={"Last-Event-ID": first_event_id}
    )
    assert resume_resp.status_code == 200
    resume_events = _parse_sse_block(resume_resp.text)
    assert [e["event"] for e in resume_events] == ["run_complete"]

    # ----- Step 6: GET /runs/{id}/bundle.tar.gz ---------------------------
    app_with_v6_routers.dependency_overrides[get_sign_fn] = _stub_sign_fn
    bundle_resp = client.get(f"/runs/{posted_run_id}/bundle.tar.gz")
    # Critical I-arch-001d P1-001 regression check + Codex diff iter-1 P1:
    # must be 200 (signer override fires + spans reachable). 503 means
    # signer wiring is wrong; 400 means evidence_pool.json snapshot is wrong.
    assert bundle_resp.status_code == 200, (
        f"bundle endpoint did not return 200. Got {bundle_resp.status_code}: "
        f"{bundle_resp.text[:500]}"
    )

    # ----- Step 7: extract tar + cross-validate IDs -----------------------
    # Per Codex iter-3 P1-006: bundle structure is
    #   audit_<bundle_id>/{manifest.yaml, verified_report.json, ...}
    # NOT manifest.json. Use yaml.safe_load on manifest.yaml.
    assert "application/gzip" in bundle_resp.headers.get("content-type", "")
    with tarfile.open(fileobj=io.BytesIO(bundle_resp.content), mode="r:gz") as tar:
        names = tar.getnames()
        assert len(names) > 0, "empty tar"
        bundle_dir = names[0].split("/")[0]
        manifest_member = tar.extractfile(f"{bundle_dir}/manifest.yaml")
        assert manifest_member is not None, f"missing manifest.yaml in {names}"
        bundle_manifest = yaml.safe_load(manifest_member.read())
        report_member = tar.extractfile(f"{bundle_dir}/verified_report.json")
        assert report_member is not None, f"missing verified_report.json in {names}"
        bundle_report = json.loads(report_member.read())

    # Per Codex iter-2 P2 nudge + iter-3 P2: assert the FK chain inside the bundle.
    assert bundle_manifest["report_id"] == bundle_report["report_id"]
    assert (
        bundle_manifest["decision_id"]
        == bundle_report["decision_id"]
        == f"dec-{posted_run_id}"
    )
    # Per Codex diff iter-1 P2: pool_id is part of the BundleManifest schema —
    # assert unconditionally (not behind an `if "pool_id" in` guard).
    assert bundle_manifest["pool_id"] == bundle_report["pool_id"]

    # Per Codex iter-3 P1-006 second half: external_run_id is asserted against
    # the SOURCE manifest.json and run_store record, NOT against bundle manifest.
    src_after = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert src_after["external_run_id"] == posted_run_id
    record = run_store.get_run(posted_run_id, path=str(isolated_runs_db))
    assert record is not None
    assert record.run_id == posted_run_id
