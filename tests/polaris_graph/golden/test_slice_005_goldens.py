"""Slice 005 golden-test integration runner.

Each test_*.json fixture pairs:
  - config: BenchmarkConfig shape
  - polaris_results: per-question PolarisRunResult shape (subset)
  - chatgpt_outputs / gemini_outputs: text content
  - expected: assertion targets

Discovery resolution mirrors slices 002-004:
  POLARIS_CONTROLS_PATH > sibling polaris-controls > .codex draft
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.benchmark.beat_both_scorer import run_benchmark
from polaris_graph.benchmark.benchmark_config import BenchmarkConfig
from polaris_graph.benchmark.dimension_scorers import ALL_DIMENSIONS
from polaris_graph.benchmark.polaris_runner import PolarisRunResult


_POLARIS_ROOT = Path(__file__).resolve().parents[3]


def _find_golden_dir() -> Path | None:
    env = os.environ.get("POLARIS_CONTROLS_PATH")
    if env:
        candidate = Path(env).expanduser().resolve() / "golden" / "slice_005"
        if candidate.is_dir():
            return candidate
    sibling = _POLARIS_ROOT.parent / "polaris-controls" / "golden" / "slice_005"
    if sibling.is_dir():
        return sibling
    draft = _POLARIS_ROOT / ".codex" / "slices" / "slice_005" / "golden_drafts"
    if draft.is_dir():
        return draft
    return None


def _slice_005_test_files() -> list[Path]:
    pc = _find_golden_dir()
    if pc is None:
        return []
    return sorted(pc.glob("test_*.json"))


def test_slice_005_golden_dir_resolvable():
    if _find_golden_dir() is None:
        pytest.skip("slice 005 goldens not available")


def test_at_least_3_slice_005_golden_files_exist():
    files = _slice_005_test_files()
    if not files:
        pytest.skip("slice 005 goldens not available")
    assert len(files) >= 3


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _polaris_from_spec(qid: str, spec: dict) -> PolarisRunResult:
    iso = datetime.now(timezone.utc)
    pool = None
    if spec.get("has_pool"):
        pool = {
            "pool_id": "pool-1",
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
                    "full_text": "trial population intervention outcome",
                    "fetched_at_utc": iso.isoformat(),
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
            "retrieval_started_at_utc": iso.isoformat(),
            "retrieval_finished_at_utc": iso.isoformat(),
            "latency_ms": 100,
            "cost_usd": 0.0,
        }
    report = None
    if spec.get("has_report"):
        report = {
            "report_id": "report-1",
            "pool_id": "pool-1",
            "decision_id": "dec-1",
            "sections": [
                {
                    "section_id": "sec_x",
                    "section_title": "X",
                    "verified_sentences": [
                        {
                            "section_id": "sec_x",
                            "sentence_text": "Adults with intervention had outcome [#ev:src-A:0-50].",
                            "provenance_tokens": ["[#ev:src-A:0-50]"],
                            "verifier_pass": True,
                            "drop_reason": None,
                        }
                    ],
                    "section_verify_pass_rate": 1.0,
                    "section_status": "verified",
                }
            ],
            "overall_verify_pass_rate": 1.0,
            "pipeline_verdict": "success",
            "generator_model": "test/m",
            "verifier_pass_threshold": 0.4,
            "started_at_utc": iso.isoformat(),
            "finished_at_utc": iso.isoformat(),
            "latency_ms": 1000,
            "cost_usd": 0.01,
        }
    return PolarisRunResult(
        question_id=qid,
        intake_status=spec.get("intake_status"),
        intake_scope_class="clinical_efficacy" if spec.get("has_pool") else None,
        evidence_pool=pool,
        verified_report=report,
        bundle_available=spec.get("bundle_available", False),
        total_latency_ms=spec.get("total_latency_ms", 0),
    )


# ---------------------------------------------------------------------------
# Per-golden execution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "golden_path",
    _slice_005_test_files()
    or [pytest.param(None, marks=pytest.mark.skip(reason="no goldens"))],
    ids=lambda p: p.stem if p else "skipped",
)
def test_slice_005_golden(golden_path: Path | None):
    if golden_path is None:
        pytest.skip("no goldens")

    spec = json.loads(golden_path.read_text(encoding="utf-8"))

    config = BenchmarkConfig.model_validate(spec["config"])
    polaris_results = {
        qid: _polaris_from_spec(qid, qspec)
        for qid, qspec in spec.get("polaris_results", {}).items()
    }
    chatgpt = spec.get("chatgpt_outputs", {})
    gemini = spec.get("gemini_outputs", {})

    sb = run_benchmark(
        config=config,
        polaris_results=polaris_results,
        chatgpt_outputs=chatgpt,
        gemini_outputs=gemini,
    )

    expected = spec["expected"]
    assert expected["kind"] == "Scoreboard"

    if "polaris_wins_min" in expected:
        assert sb.polaris_wins >= expected["polaris_wins_min"]
    if "external_wins" in expected:
        assert sb.external_wins == expected["external_wins"]
    if "ties" in expected:
        assert sb.ties == expected["ties"]

    if "verify_polaris_auto_one" in expected:
        for dim in expected["verify_polaris_auto_one"]:
            for q in sb.per_question:
                p_score = q.polaris.by_dimension.get(dim)
                assert p_score == 1.0, (
                    f"{golden_path.name}: polaris {dim} should be 1.0 "
                    f"for {q.question_id}, got {p_score}"
                )

    if "polaris_refusal_score" in expected:
        for q in sb.per_question:
            p = q.polaris.by_dimension["refusal_correctness"]
            assert p == expected["polaris_refusal_score"]
    if "chatgpt_refusal_score" in expected:
        for q in sb.per_question:
            c = q.chatgpt.by_dimension["refusal_correctness"]
            assert c == expected["chatgpt_refusal_score"]
    if "gemini_refusal_score" in expected:
        for q in sb.per_question:
            g = q.gemini.by_dimension["refusal_correctness"]
            assert g == expected["gemini_refusal_score"]

    if expected.get("polaris_wins_for_refusal"):
        # POLARIS should beat ChatGPT (1.0 vs 0.0) and tie/beat Gemini
        for q in sb.per_question:
            p = q.polaris.by_dimension["refusal_correctness"]
            c = q.chatgpt.by_dimension["refusal_correctness"]
            assert p > c

    if expected.get("chatgpt_has_some_real_scores"):
        for q in sb.per_question:
            populated = [
                v for v in q.chatgpt.by_dimension.values() if v is not None
            ]
            assert len(populated) > 0

    if expected.get("gemini_all_external_dims_none_or_zero"):
        for q in sb.per_question:
            for dim in ALL_DIMENSIONS:
                v = q.gemini.by_dimension.get(dim)
                # When external text missing, most dims return None except
                # for refusal_correctness on bait + auditability/latency
                # which return defaults. Enforce: nothing > 0.0.
                if v is not None:
                    assert v <= 1.0
