"""Exhaustive cross-org-leakage tests for M-15b authz retrofit.

Codex M-15b mandate: "every M-1..M-13 endpoint that returns
workspace-scoped resource gets a workspace-membership gate.
Cross-org → 403."

This test file enumerates every M-8..M-13 endpoint that touches
a workspace, upload, or job, and verifies:
  (a) no auth → 401
  (b) wrong-org caller → 403
  (c) right-org caller → 200/expected

Run-endpoints (M-1..M-7) are NOT in scope for this milestone —
they read pre-Phase B artifacts from disk that don't have org_id
tags. Tagging them is M-15c (deferred) per Phase C plan v2.

Public endpoints (templates/catalog, templates/route) are also
out of scope: they don't expose workspace data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir import (
    JobQueue,
    MockJobRunner,
    register_runner,
)
from src.polaris_graph.audit_ir.inspector_router import (
    _set_brief_llm_for_tests,
    _set_job_queue_for_tests,
    _set_job_worker_for_tests,
    _set_workspace_files_root_for_tests,
    _set_workspace_store_for_tests,
    router,
)
from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests
from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


_ALPHA = "X-Polaris-Caller", "org_alpha:usr_alpha:owner"
_BETA = "X-Polaris-Caller", "org_beta:usr_beta:owner"


class _FakeAsyncLlm:
    async def draft_brief(self, question, chunks):
        return []


@pytest.fixture
def alpha_beta_setup(tmp_path: Path):
    """Build two orgs (alpha, beta) each with a workspace + an
    upload + a job. Tests use this to verify cross-org access
    fails with 403."""
    _reset_runners_for_tests()
    register_runner(
        MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05)
    )

    ws_store = WorkspaceStore(tmp_path / "ws.sqlite")
    _set_workspace_store_for_tests(ws_store)
    _set_workspace_files_root_for_tests(tmp_path / "files")
    _set_brief_llm_for_tests(_FakeAsyncLlm())

    queue = JobQueue(tmp_path / "jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)

    # Seed alpha
    ws_alpha = ws_store.create_workspace("Alpha", max_docs=10, org_id="org_alpha")
    up_alpha = ws_store.upload_file(
        ws_alpha.workspace_id, "a.txt", "text/plain", 10, "/p/a",
    )
    ws_store.transition_parser_status(up_alpha.upload_id, "parsing")
    ws_store.insert_chunks(up_alpha.upload_id, [
        ("alpha content", to_dict(TextSpan(up_alpha.upload_id, 0, 13))),
    ])
    ws_store.transition_parser_status(up_alpha.upload_id, "parsed")
    job_alpha = queue.enqueue("mock", {}, org_id="org_alpha")

    # Seed beta
    ws_beta = ws_store.create_workspace("Beta", max_docs=10, org_id="org_beta")
    up_beta = ws_store.upload_file(
        ws_beta.workspace_id, "b.txt", "text/plain", 10, "/p/b",
    )
    ws_store.transition_parser_status(up_beta.upload_id, "parsing")
    ws_store.insert_chunks(up_beta.upload_id, [
        ("beta content", to_dict(TextSpan(up_beta.upload_id, 0, 12))),
    ])
    ws_store.transition_parser_status(up_beta.upload_id, "parsed")
    job_beta = queue.enqueue("mock", {}, org_id="org_beta")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    yield {
        "client": client,
        "ws_alpha": ws_alpha,
        "ws_beta": ws_beta,
        "up_alpha": up_alpha,
        "up_beta": up_beta,
        "job_alpha": job_alpha,
        "job_beta": job_beta,
    }

    _set_brief_llm_for_tests(None)
    _set_job_worker_for_tests(None)
    _set_job_queue_for_tests(None)
    _set_workspace_store_for_tests(None)
    _set_workspace_files_root_for_tests(None)
    _reset_runners_for_tests()


def _alpha(headers=None):
    h = {_ALPHA[0]: _ALPHA[1]}
    if headers:
        h.update(headers)
    return h


def _beta(headers=None):
    h = {_BETA[0]: _BETA[1]}
    if headers:
        h.update(headers)
    return h


# ---------------------------------------------------------------------------
# Auth-required: each endpoint must 401 without an auth header
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/inspector/workspaces"),
        ("GET", "/api/inspector/workspaces"),
        ("GET", "/api/inspector/workspaces/ws_x"),
        ("POST", "/api/inspector/workspaces/ws_x/uploads"),
        ("GET", "/api/inspector/workspaces/ws_x/uploads"),
        ("POST", "/api/inspector/workspaces/ws_x/brief"),
        ("GET", "/api/inspector/uploads/up_x"),
        ("DELETE", "/api/inspector/uploads/up_x"),
        ("GET", "/api/inspector/uploads/up_x/chunks"),
        ("POST", "/api/inspector/jobs"),
        ("GET", "/api/inspector/jobs"),
        ("GET", "/api/inspector/jobs/job_x"),
        ("POST", "/api/inspector/jobs/job_x/pause"),
        ("POST", "/api/inspector/jobs/job_x/cancel"),
        ("POST", "/api/inspector/jobs/job_x/resume"),
        ("GET", "/api/inspector/jobs/job_x/surfaces"),
        ("GET", "/api/inspector/jobs/job_x/stream"),
    ],
)
def test_endpoint_requires_auth(alpha_beta_setup, method: str, path: str) -> None:
    """No auth header → 401."""
    client = alpha_beta_setup["client"]
    body = {"name": "x", "question": "q", "template_id": "mock", "params": {}}
    if method == "POST":
        resp = client.post(path, json=body)
    elif method == "GET":
        resp = client.get(path)
    elif method == "DELETE":
        resp = client.delete(path)
    else:
        raise ValueError(method)
    assert resp.status_code == 401, (
        f"{method} {path} did not require auth (status={resp.status_code})"
    )


# ---------------------------------------------------------------------------
# Cross-org: every workspace-scoped read/write rejects beta on alpha resources
# ---------------------------------------------------------------------------


def test_get_workspace_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.get(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}",
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_list_workspace_uploads_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.get(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}/uploads",
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_upload_to_workspace_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.post(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}/uploads",
        files={"file": ("x.txt", b"hi", "text/plain")},
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_brief_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.post(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}/brief",
        json={"question": "x"},
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_get_upload_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    up_alpha = alpha_beta_setup["up_alpha"]
    resp = client.get(
        f"/api/inspector/uploads/{up_alpha.upload_id}",
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_delete_upload_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    up_alpha = alpha_beta_setup["up_alpha"]
    resp = client.delete(
        f"/api/inspector/uploads/{up_alpha.upload_id}",
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_list_upload_chunks_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    up_alpha = alpha_beta_setup["up_alpha"]
    resp = client.get(
        f"/api/inspector/uploads/{up_alpha.upload_id}/chunks",
        headers=_beta(),
    )
    assert resp.status_code == 403


def test_get_job_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.get(
        f"/api/inspector/jobs/{job_alpha.job_id}", headers=_beta(),
    )
    assert resp.status_code == 403


def test_pause_job_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.post(
        f"/api/inspector/jobs/{job_alpha.job_id}/pause", headers=_beta(),
    )
    assert resp.status_code == 403


def test_cancel_job_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.post(
        f"/api/inspector/jobs/{job_alpha.job_id}/cancel", headers=_beta(),
    )
    assert resp.status_code == 403


def test_resume_job_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.post(
        f"/api/inspector/jobs/{job_alpha.job_id}/resume", headers=_beta(),
    )
    assert resp.status_code == 403


def test_get_job_surfaces_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.get(
        f"/api/inspector/jobs/{job_alpha.job_id}/surfaces", headers=_beta(),
    )
    assert resp.status_code == 403


def test_stream_job_surfaces_cross_org_returns_403(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.get(
        f"/api/inspector/jobs/{job_alpha.job_id}/stream", headers=_beta(),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Same-org: caller can access their own org's resources (sanity)
# ---------------------------------------------------------------------------


def test_alpha_can_read_alpha_workspace(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.get(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}",
        headers=_alpha(),
    )
    assert resp.status_code == 200
    assert resp.json()["org_id"] == "org_alpha"


def test_alpha_can_read_alpha_upload(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    up_alpha = alpha_beta_setup["up_alpha"]
    resp = client.get(
        f"/api/inspector/uploads/{up_alpha.upload_id}", headers=_alpha(),
    )
    assert resp.status_code == 200


def test_alpha_can_read_alpha_job(alpha_beta_setup) -> None:
    client = alpha_beta_setup["client"]
    job_alpha = alpha_beta_setup["job_alpha"]
    resp = client.get(
        f"/api/inspector/jobs/{job_alpha.job_id}", headers=_alpha(),
    )
    assert resp.status_code == 200


def test_list_workspaces_does_not_leak_other_orgs(alpha_beta_setup) -> None:
    """Cross-org listing must NOT leak other orgs' workspaces."""
    client = alpha_beta_setup["client"]
    resp = client.get("/api/inspector/workspaces", headers=_alpha())
    body = resp.json()
    org_ids = {w["org_id"] for w in body["workspaces"]}
    assert org_ids == {"org_alpha"}, f"got orgs {org_ids}"


def test_list_jobs_does_not_leak_other_orgs(alpha_beta_setup) -> None:
    """Cross-org listing must NOT leak other orgs' jobs."""
    client = alpha_beta_setup["client"]
    resp = client.get("/api/inspector/jobs", headers=_alpha())
    body = resp.json()
    # Each job is org-tagged; alpha caller must see only alpha jobs.
    for job in body["jobs"]:
        assert job.get("org_id") == "org_alpha", (
            f"alpha caller saw job from org {job.get('org_id')}"
        )


# ---------------------------------------------------------------------------
# Test-header trusted flag: required for the X-Polaris-Caller path
# ---------------------------------------------------------------------------


def test_test_header_ignored_when_trust_flag_off(
    alpha_beta_setup, monkeypatch,
) -> None:
    """Codex M-15b mandate: PG_AUTH_TRUSTED_TEST_HEADER MUST be
    explicitly enabled for X-Polaris-Caller to be honored. With
    the flag off (production default), the header is ignored
    and the request 401s."""
    monkeypatch.setenv("PG_AUTH_TRUSTED_TEST_HEADER", "0")
    client = alpha_beta_setup["client"]
    ws_alpha = alpha_beta_setup["ws_alpha"]
    resp = client.get(
        f"/api/inspector/workspaces/{ws_alpha.workspace_id}",
        headers=_alpha(),  # legitimate test header
    )
    # With trust flag off, the test header is ignored → no auth → 401.
    assert resp.status_code == 401
