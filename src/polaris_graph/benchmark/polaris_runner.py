"""Drive POLARIS via /api/intake -> /api/retrieval -> /api/generation.

Per `.codex/slices/slice_005/architecture_proposal.md` §"polaris_runner".

For each BenchmarkQuestion in a config, runs the live POLARIS chain and
captures intake.status + EvidencePool + VerifiedReport + per-stage timing.
Fail rows recorded as PolarisRunResult with `failure` populated; the
benchmark continues even when individual questions fail (no aggregate-level
abort).

The runner does NOT call OpenRouter or Serper directly — it goes through
the FastAPI app's mounted routes, exercising the same code path the
end-user does.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from polaris_graph.benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkQuestion,
)

_LOG = logging.getLogger(__name__)


# Generous timeout — generation can take ~5 minutes per question.
DEFAULT_TIMEOUT_S = 600.0


@dataclass
class PolarisRunResult:
    """One question's POLARIS output. Either populated fields or `failure`."""

    question_id: str
    intake_status: str | None = None
    intake_scope_class: str | None = None
    intake_decision: dict[str, Any] | None = None  # raw ScopeDecision dict
    evidence_pool: dict[str, Any] | None = None    # raw EvidencePool dict
    verified_report: dict[str, Any] | None = None  # raw VerifiedReport dict
    intake_latency_ms: int = 0
    retrieval_latency_ms: int = 0
    generation_latency_ms: int = 0
    total_latency_ms: int = 0
    bundle_available: bool = False
    failure: str | None = None  # populated iff something failed; chain stopped

    def succeeded(self) -> bool:
        return self.failure is None


def run_polaris_against(
    config: BenchmarkConfig,
    backend_url: str,
    *,
    client: httpx.Client | None = None,
    skip_generation_for_bait: bool = True,
) -> dict[str, PolarisRunResult]:
    """Run every BenchmarkQuestion through the live POLARIS chain.

    Args:
        config: BenchmarkConfig with questions
        backend_url: e.g. 'http://127.0.0.1:8000' (no trailing /)
        client: optional pre-configured httpx.Client (tests inject MockTransport)
        skip_generation_for_bait: when True, refusal-bait questions stop
            after intake (since we expect them to refuse + scoring needs
            only the intake_status). Set False to forcibly attempt
            retrieval/generation on bait (will likely 400).

    Returns:
        dict[question_id -> PolarisRunResult]. Includes failure rows.
    """
    out: dict[str, PolarisRunResult] = {}
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT_S)

    try:
        for question in config.questions:
            out[question.question_id] = _run_one(
                question, backend_url, client, skip_generation_for_bait
            )
    finally:
        if own_client and client is not None:
            client.close()

    return out


def _run_one(
    question: BenchmarkQuestion,
    backend_url: str,
    client: httpx.Client,
    skip_generation_for_bait: bool,
) -> PolarisRunResult:
    result = PolarisRunResult(question_id=question.question_id)
    t_start = time.perf_counter()

    # 1. Intake
    try:
        t0 = time.perf_counter()
        r = client.post(
            f"{backend_url}/api/intake",
            json={"question": question.question_text},
        )
        result.intake_latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            result.failure = f"intake HTTP {r.status_code}: {r.text[:200]}"
            return result
        intake_body = r.json()
        decision = intake_body["decision"]
        result.intake_decision = decision
        result.intake_status = decision.get("status")
        result.intake_scope_class = decision.get("scope_class")
    except Exception as exc:  # noqa: BLE001
        result.failure = f"intake exception {type(exc).__name__}: {exc}"
        return result

    # Refusal-bait: stop here — we have what scoring needs
    if question.is_refusal_bait and skip_generation_for_bait:
        result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
        return result

    # If intake said NOT in_scope but the question wasn't bait, it's a
    # genuine failure of the question (or a slice 001 false positive).
    # Stop with the intake info captured.
    if result.intake_status != "in_scope":
        result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
        return result

    # 2. Retrieval
    try:
        t0 = time.perf_counter()
        r = client.post(
            f"{backend_url}/api/retrieval",
            json={"decision": decision},
        )
        result.retrieval_latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            result.failure = f"retrieval HTTP {r.status_code}: {r.text[:200]}"
            return result
        retrieval_body = r.json()
        result.evidence_pool = retrieval_body["pool"]
    except Exception as exc:  # noqa: BLE001
        result.failure = f"retrieval exception {type(exc).__name__}: {exc}"
        return result

    # Inadequate corpus -> can't generate
    if not result.evidence_pool["adequacy"]["is_adequate"]:
        result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
        return result

    # 3. Generation
    try:
        t0 = time.perf_counter()
        r = client.post(
            f"{backend_url}/api/generation",
            json={
                "pool": result.evidence_pool,
                "scope_class": result.intake_scope_class,
            },
        )
        result.generation_latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            result.failure = f"generation HTTP {r.status_code}: {r.text[:200]}"
            return result
        gen_body = r.json()
        result.verified_report = gen_body["report"]
    except Exception as exc:  # noqa: BLE001
        result.failure = f"generation exception {type(exc).__name__}: {exc}"
        return result

    # 4. Bundle availability check (HEAD or attempt; cheap)
    if (
        result.verified_report
        and result.verified_report.get("pipeline_verdict") == "success"
    ):
        try:
            r = client.get(f"{backend_url}/api/audit-bundle/health")
            result.bundle_available = r.status_code == 200
        except Exception:
            result.bundle_available = False

    result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
    return result
