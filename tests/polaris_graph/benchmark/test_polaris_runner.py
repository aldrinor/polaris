"""Tests for polaris_runner — drive POLARIS chain against live FastAPI.

Uses httpx.MockTransport to simulate the FastAPI app; no real
network/LLM calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from polaris_graph.benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkQuestion,
)
from polaris_graph.benchmark.polaris_runner import (
    PolarisRunResult,
    run_polaris_against,
)


# ---------- Fixtures ----------

def _config(questions: list[BenchmarkQuestion]) -> BenchmarkConfig:
    return BenchmarkConfig(benchmark_id="test", questions=questions)


def _q(qid: str = "Q1", refusal_bait: bool = False) -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id=qid,
        question_text=f"text {qid}",
        scope_class="out_of_scope" if refusal_bait else "clinical_efficacy",
        is_refusal_bait=refusal_bait,
    )


def _intake_response(status: str = "in_scope", scope_class: str = "clinical_efficacy") -> dict:
    iso = datetime.now(timezone.utc).isoformat()
    return {
        "error": False,
        "decision": {
            "decision_id": "dec-1",
            "status": status,
            "scope_class": scope_class,
            "ambiguity_axes": [],
            "clarifications_needed": [],
            "provenance": {},
            "decided_at_utc": iso,
            "latency_ms": 5,
        },
        "server_time_utc": iso,
    }


def _retrieval_response(adequate: bool = True) -> dict:
    iso = datetime.now(timezone.utc).isoformat()
    return {
        "error": False,
        "pool": {
            "pool_id": "pool-1",
            "decision_id": "dec-1",
            "sources": [],
            "adequacy": {
                "is_adequate": adequate,
                "sources_per_tier": {"T1": 0, "T2": 0, "T3": 0},
                "min_required_per_tier": {"T1": 0, "T2": 0, "T3": 0},
                "failure_reason": None if adequate else "no sources",
            },
            "queries_executed": [],
            "retrieval_started_at_utc": iso,
            "retrieval_finished_at_utc": iso,
            "latency_ms": 0,
            "cost_usd": 0.0,
        },
        "server_time_utc": iso,
    }


def _generation_response(verdict: str = "success") -> dict:
    iso = datetime.now(timezone.utc).isoformat()
    return {
        "error": False,
        "report": {
            "report_id": "report-1",
            "pool_id": "pool-1",
            "decision_id": "dec-1",
            "sections": [],
            "overall_verify_pass_rate": 1.0,
            "pipeline_verdict": verdict,
            "generator_model": "test/model",
            "evaluator_model": "strict_verify_v1",
            "verifier_pass_threshold": 0.4,
            "started_at_utc": iso,
            "finished_at_utc": iso,
            "latency_ms": 1000,
            "cost_usd": 0.01,
        },
        "server_time_utc": iso,
    }


def _make_handler(routes: dict[str, dict | int]):
    """Build a MockTransport handler that returns canned responses per path."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/audit-bundle/health"):
            return httpx.Response(200, json={"status": "ok"})
        spec = routes.get(path)
        if isinstance(spec, int):
            return httpx.Response(spec, json={"detail": "stubbed error"})
        if spec is None:
            return httpx.Response(404, json={"detail": "not stubbed"})
        return httpx.Response(200, json=spec)

    return handler


# ---------- Happy paths ----------

def test_run_one_in_scope_success():
    routes = {
        "/api/intake": _intake_response(),
        "/api/retrieval": _retrieval_response(adequate=True),
        "/api/generation": _generation_response(verdict="success"),
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert r.succeeded()
    assert r.intake_status == "in_scope"
    assert r.evidence_pool is not None
    assert r.verified_report is not None
    assert r.bundle_available is True


def test_run_refusal_bait_short_circuits_after_intake():
    """Bait questions stop after intake when skip_generation_for_bait=True."""
    routes = {
        "/api/intake": _intake_response(status="refused", scope_class=None),
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q(refusal_bait=True)])
    results = run_polaris_against(
        config, "http://test.local", client=client,
    )
    r = results["Q1"]
    assert r.succeeded()
    assert r.intake_status == "refused"
    assert r.evidence_pool is None
    assert r.verified_report is None


def test_run_intake_says_out_of_scope_chain_stops():
    """Non-bait question that intake declares out_of_scope -> chain stops cleanly."""
    routes = {
        "/api/intake": _intake_response(status="out_of_scope", scope_class=None),
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert r.succeeded()  # not a failure — captured the intake info
    assert r.intake_status == "out_of_scope"
    assert r.evidence_pool is None


def test_run_inadequate_pool_chain_stops():
    routes = {
        "/api/intake": _intake_response(),
        "/api/retrieval": _retrieval_response(adequate=False),
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert r.succeeded()  # not a failure; captured the inadequacy
    assert r.evidence_pool is not None
    assert r.evidence_pool["adequacy"]["is_adequate"] is False
    assert r.verified_report is None


# ---------- Failure paths ----------

def test_run_intake_400_records_failure():
    routes = {"/api/intake": 400}
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert not r.succeeded()
    assert "intake HTTP 400" in r.failure


def test_run_retrieval_400_records_failure():
    routes = {
        "/api/intake": _intake_response(),
        "/api/retrieval": 400,
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert not r.succeeded()
    assert "retrieval HTTP 400" in r.failure


def test_run_generation_400_records_failure():
    routes = {
        "/api/intake": _intake_response(),
        "/api/retrieval": _retrieval_response(adequate=True),
        "/api/generation": 400,
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert not r.succeeded()
    assert "generation HTTP 400" in r.failure


def test_run_continues_after_one_question_fails():
    """One failing question doesn't abort the whole benchmark."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/audit-bundle/health"):
            return httpx.Response(200, json={"status": "ok"})
        body = request.read().decode("utf-8")
        # Q1 fails at intake; Q2 succeeds
        if "Q1" in body or "text Q1" in body:
            return httpx.Response(500, json={"detail": "Q1 fails"})
        if request.url.path.endswith("/api/intake"):
            return httpx.Response(200, json=_intake_response())
        if request.url.path.endswith("/api/retrieval"):
            return httpx.Response(200, json=_retrieval_response(True))
        if request.url.path.endswith("/api/generation"):
            return httpx.Response(200, json=_generation_response())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    config = _config([_q("Q1"), _q("Q2")])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    assert not results["Q1"].succeeded()
    assert results["Q2"].succeeded()


# ---------- Latency capture ----------

def test_run_captures_per_stage_latency():
    routes = {
        "/api/intake": _intake_response(),
        "/api/retrieval": _retrieval_response(adequate=True),
        "/api/generation": _generation_response(),
    }
    transport = httpx.MockTransport(_make_handler(routes))
    client = httpx.Client(transport=transport)

    config = _config([_q()])
    results = run_polaris_against(
        config, "http://test.local", client=client
    )
    r = results["Q1"]
    assert r.intake_latency_ms >= 0
    assert r.retrieval_latency_ms >= 0
    assert r.generation_latency_ms >= 0
    assert r.total_latency_ms >= 0
