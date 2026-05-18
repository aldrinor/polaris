"""GET /api/inspector/runs/{run_id} — v6 live-inspector AuditIR route.

I-rdy-008 (#504) slice 1. Covers the 5 resolution outcomes: unknown run,
not-completed run, abort run, completed-but-unloadable run, and a loadable
completed run. The loadable case builds a complete minimal artifact_dir under
tmp_path — clean-checkout reproducible, no dependency on the gitignored
outputs/ tree (Codex brief iter-1 P1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_v6.queue import run_store

_QUESTION = "What does the latest evidence show on this topic?"


def _write_minimal_artifact_dir(d: Path) -> Path:
    """A complete minimal artifact_dir that ``load_audit_ir()`` accepts.

    Writes exactly the 5 loader-required files with the keys
    ``src/polaris_graph/audit_ir/loader.py`` requires — no more.
    """
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "manifest_run_1",
                "slug": "inspector_test_slug",
                "status": "success",
                "question": _QUESTION,
                "protocol_sha256": "0" * 64,
                "completeness": {"covered_fraction": 1.0},
                "evaluator_gate": {"gate_class": "release", "release_allowed": True},
                "corpus": {"count": 1, "tier_fractions": {"T1": 1.0}},
                "frame_coverage_report": {"entries": [], "by_status": {}},
            }
        ),
        encoding="utf-8",
    )
    (d / "report.md").write_text("# Research report\n\nMinimal.\n", encoding="utf-8")
    (d / "bibliography.json").write_text("[]", encoding="utf-8")
    (d / "contradictions.json").write_text("[]", encoding="utf-8")
    (d / "verification_details.json").write_text(
        json.dumps({"sections": [], "totals": {}}), encoding="utf-8"
    )
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a fresh per-test run-store DB.

    POLARIS_V6_RUN_DB is set BEFORE create_app() so both the seeding calls and
    the route resolve to the same temp DB, never state/v6_runs.sqlite.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "runs.sqlite"))
    run_store.init_db()
    return TestClient(create_app())


def test_unknown_run_returns_404(client):
    response = client.get("/api/inspector/runs/no_such_run")
    assert response.status_code == 404


def test_not_completed_run_returns_409(client):
    run_store.insert_run("queued_run", "clinical", _QUESTION)
    response = client.get("/api/inspector/runs/queued_run")
    assert response.status_code == 409


def test_abort_run_returns_422(client):
    run_store.insert_run("abort_run", "policy", _QUESTION)
    run_store.mark_aborted(
        "abort_run",
        pipeline_status="abort_corpus_inadequate",
        abort_reason="corpus fails T1 threshold",
    )
    response = client.get("/api/inspector/runs/abort_run")
    assert response.status_code == 422


def test_completed_run_missing_artifact_dir_returns_404(client, tmp_path):
    run_store.insert_run("nodir_run", "clinical", _QUESTION)
    run_store.set_pipeline_meta(
        "nodir_run", artifact_dir=str(tmp_path / "artifacts" / "does_not_exist")
    )
    run_store.mark_completed("nodir_run", {}, pipeline_status="success")
    response = client.get("/api/inspector/runs/nodir_run")
    assert response.status_code == 404


def test_loadable_completed_run_returns_200_audit_ir(client, tmp_path):
    artifact_dir = _write_minimal_artifact_dir(tmp_path / "artifacts" / "good_run")
    run_store.insert_run("good_run", "clinical", _QUESTION)
    run_store.set_pipeline_meta("good_run", artifact_dir=str(artifact_dir))
    run_store.mark_completed("good_run", {}, pipeline_status="success")

    response = client.get("/api/inspector/runs/good_run")
    assert response.status_code == 200, response.text
    body = response.json()
    # Faithful AuditIR JSON — top-level run_id is the manifest run_id, plus the
    # canonical IR blocks the rich surfaces project from.
    assert body["run_id"] == "manifest_run_1"
    assert body["ir_schema_version"]
    assert "manifest" in body
    assert "bibliography" in body
    assert "verified_report" in body


# ---------------------------------------------------------------------------
# I-rdy-008 (#504) slice 7a — GET /api/inspector/runs/{run_id}/evidence
#
# The evidence-span route reconstructs each verified token's exact cited span
# as evidence_pool.json's body[start:end]. Per the Codex arch consult
# (.codex/I-rdy-008/slice7_arch_consult_verdict.txt) it fails loud (422)
# rather than degrade to a bibliography statement.
# ---------------------------------------------------------------------------

# A known 40-char body so exact-slice assertions are unambiguous.
_BODY = "0123456789ABCDEFGHIJabcdefghij0123456789"


def _write_artifact_dir_with_evidence(d: Path, *, kept, evidence_pool) -> Path:
    """A minimal artifact_dir whose verification_details.json carries tokened
    kept sentences, plus an optional evidence_pool.json.

    ``kept`` — the kept-sentence dicts (``{sentence, tokens}``).
    ``evidence_pool`` — written as evidence_pool.json: a str is written
    verbatim (the malformed-JSON case); a list/dict is JSON-dumped; ``None``
    omits the file entirely (the missing-pool case).
    """
    _write_minimal_artifact_dir(d)
    (d / "verification_details.json").write_text(
        json.dumps(
            {
                "sections": [{"title": "Efficacy", "kept": kept, "dropped": []}],
                "totals": {},
            }
        ),
        encoding="utf-8",
    )
    if evidence_pool is not None:
        (d / "evidence_pool.json").write_text(
            evidence_pool
            if isinstance(evidence_pool, str)
            else json.dumps(evidence_pool),
            encoding="utf-8",
        )
    return d


def _seed_completed(run_id: str, artifact_dir: Path) -> None:
    """Seed run_store with a completed run pointing at ``artifact_dir``."""
    run_store.insert_run(run_id, "clinical", _QUESTION)
    run_store.set_pipeline_meta(run_id, artifact_dir=str(artifact_dir))
    run_store.mark_completed(run_id, {}, pipeline_status="success")


def test_evidence_unknown_run_returns_404(client):
    # Shared-resolver regression: the evidence route reuses get_inspector_run's
    # run-resolution, so an unknown run still 404s.
    response = client.get("/api/inspector/runs/no_such_run/evidence")
    assert response.status_code == 404


def test_evidence_200_exact_span_slice(client, tmp_path):
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "ev_run",
        kept=[
            {
                "sentence": "Claim one [#ev:ev_001:5-25].",
                "tokens": [{"evidence_id": "ev_001", "start": 5, "end": 25}],
            }
        ],
        evidence_pool=[
            {
                "evidence_id": "ev_001",
                "direct_quote": _BODY,
                "source_url": "https://example.test/a",
                "tier": "T2",
            }
        ],
    )
    _seed_completed("ev_run", artifact_dir)

    response = client.get("/api/inspector/runs/ev_run/evidence")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "ev_run"
    assert len(body["spans"]) == 1
    span = body["spans"][0]
    assert span["evidence_id"] == "ev_001"
    assert span["span_start"] == 5
    assert span["span_end"] == 25
    assert span["span_text"] == _BODY[5:25]
    assert span["tier"] == "T2"
    assert span["source_url"] == "https://example.test/a"
    assert span["claim_ids"] == ["Efficacy:kept:0"]


def test_evidence_multi_span_same_evidence_id(client, tmp_path):
    # One sentence, two tokens on the SAME evidence_id but different ranges →
    # two distinct range-keyed span entries.
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "multi_run",
        kept=[
            {
                "sentence": "Two ranges [#ev:ev_001:0-10] [#ev:ev_001:10-20].",
                "tokens": [
                    {"evidence_id": "ev_001", "start": 0, "end": 10},
                    {"evidence_id": "ev_001", "start": 10, "end": 20},
                ],
            }
        ],
        evidence_pool=[{"evidence_id": "ev_001", "direct_quote": _BODY, "tier": "T1"}],
    )
    _seed_completed("multi_run", artifact_dir)

    response = client.get("/api/inspector/runs/multi_run/evidence")
    assert response.status_code == 200, response.text
    spans = response.json()["spans"]
    assert len(spans) == 2
    assert {(s["span_start"], s["span_end"]) for s in spans} == {(0, 10), (10, 20)}
    assert spans[0]["span_text"] == _BODY[0:10]
    assert spans[1]["span_text"] == _BODY[10:20]


def test_evidence_missing_pool_returns_422(client, tmp_path):
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "nopool_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_001:0-5].",
                "tokens": [{"evidence_id": "ev_001", "start": 0, "end": 5}],
            }
        ],
        evidence_pool=None,  # evidence_pool.json deliberately omitted
    )
    _seed_completed("nopool_run", artifact_dir)

    response = client.get("/api/inspector/runs/nopool_run/evidence")
    assert response.status_code == 422
    assert "evidence_pool.json" in response.json()["detail"]


def test_evidence_malformed_pool_returns_422(client, tmp_path):
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "badpool_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_001:0-5].",
                "tokens": [{"evidence_id": "ev_001", "start": 0, "end": 5}],
            }
        ],
        evidence_pool="{not valid json",
    )
    _seed_completed("badpool_run", artifact_dir)

    response = client.get("/api/inspector/runs/badpool_run/evidence")
    assert response.status_code == 422


def test_evidence_out_of_range_offset_returns_422(client, tmp_path):
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "oob_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_001:0-9999].",
                "tokens": [{"evidence_id": "ev_001", "start": 0, "end": 9999}],
            }
        ],
        evidence_pool=[{"evidence_id": "ev_001", "direct_quote": _BODY, "tier": "T1"}],
    )
    _seed_completed("oob_run", artifact_dir)

    response = client.get("/api/inspector/runs/oob_run/evidence")
    assert response.status_code == 422
    assert "out of range" in response.json()["detail"]


def test_evidence_unknown_evidence_id_returns_422(client, tmp_path):
    # A verified token cites ev_999, which is absent from the pool.
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "missing_ev_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_999:0-5].",
                "tokens": [{"evidence_id": "ev_999", "start": 0, "end": 5}],
            }
        ],
        evidence_pool=[{"evidence_id": "ev_001", "direct_quote": _BODY, "tier": "T1"}],
    )
    _seed_completed("missing_ev_run", artifact_dir)

    response = client.get("/api/inspector/runs/missing_ev_run/evidence")
    assert response.status_code == 422
    assert "ev_999" in response.json()["detail"]


def test_evidence_missing_body_text_returns_422(client, tmp_path):
    # The pool row has no full_text / direct_quote / snippet body.
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "nobody_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_001:0-5].",
                "tokens": [{"evidence_id": "ev_001", "start": 0, "end": 5}],
            }
        ],
        evidence_pool=[
            {
                "evidence_id": "ev_001",
                "source_url": "https://example.test/a",
                "tier": "T1",
            }
        ],
    )
    _seed_completed("nobody_run", artifact_dir)

    response = client.get("/api/inspector/runs/nobody_run/evidence")
    assert response.status_code == 422
    assert "no body text" in response.json()["detail"]


def test_evidence_zero_token_run_returns_200_empty(client, tmp_path):
    # A verified sentence with no tokens (e.g. a synthesis claim) contributes
    # no spans; a run with zero tokens overall is a valid 200 with spans: [].
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "zerotok_run",
        kept=[{"sentence": "A synthesis sentence with no citation.", "tokens": []}],
        evidence_pool=[{"evidence_id": "ev_001", "direct_quote": _BODY, "tier": "T1"}],
    )
    _seed_completed("zerotok_run", artifact_dir)

    response = client.get("/api/inspector/runs/zerotok_run/evidence")
    assert response.status_code == 200, response.text
    assert response.json()["spans"] == []


def test_evidence_sources_container_and_full_text_precedence(client, tmp_path):
    # evidence_pool.json as {"sources": [...]} (not a bare list); the body
    # field precedence is full_text > direct_quote, so full_text wins.
    artifact_dir = _write_artifact_dir_with_evidence(
        tmp_path / "artifacts" / "sources_run",
        kept=[
            {
                "sentence": "Claim [#ev:ev_001:0-10].",
                "tokens": [{"evidence_id": "ev_001", "start": 0, "end": 10}],
            }
        ],
        evidence_pool={
            "sources": [
                {
                    "evidence_id": "ev_001",
                    "full_text": _BODY,
                    "direct_quote": "WRONG-this-should-not-be-used",
                    "tier": "T1",
                }
            ]
        },
    )
    _seed_completed("sources_run", artifact_dir)

    response = client.get("/api/inspector/runs/sources_run/evidence")
    assert response.status_code == 200, response.text
    span = response.json()["spans"][0]
    assert span["span_text"] == _BODY[0:10]
