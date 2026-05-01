"""Tests for the industry benchmark adapter shims (Phase 3 Task 3.7)."""

from __future__ import annotations

import pytest

from polaris_v6.benchmark.industry_adapters import (
    IndustryRunRecord,
    adapt,
    adapt_browsecomp,
    adapt_deepresearch_bench,
    adapt_gaia,
)


def test_browsecomp_basic():
    rec = adapt_browsecomp(
        {
            "id": "bc_001",
            "prompt": "What was the year of the first official ascent of K2?",
            "target": "1954",
            "sources": ["https://www.britannica.com/place/K2"],
        }
    )
    assert rec.benchmark == "browsecomp"
    assert rec.question_id == "bc_001"
    assert rec.expected_answer == "1954"
    assert rec.expected_citations == ["https://www.britannica.com/place/K2"]


def test_browsecomp_missing_required_raises():
    with pytest.raises(ValueError):
        adapt_browsecomp({"id": "x"})


def test_gaia_basic():
    rec = adapt_gaia(
        {
            "task_id": "gaia_42",
            "Question": "Sum of Fibonacci numbers below 100",
            "Final answer": "232",
            "Level": "1",
            "file_name": "",
        }
    )
    assert rec.benchmark == "gaia"
    assert rec.metadata["level"] == "1"


def test_gaia_missing_question_raises():
    with pytest.raises(ValueError):
        adapt_gaia({"task_id": "x"})


def test_deepresearch_bench_basic():
    rec = adapt_deepresearch_bench(
        {
            "question_id": "drb_007",
            "query": "Compare Canadian and Australian critical-mineral strategies for lithium",
            "reference_answer": "Both targeted onshore refining; Canada via 2024 strategy, Australia via 2023 strategic reserves.",
            "reference_sources": [
                "https://natural-resources.canada.ca",
                "https://www.industry.gov.au",
            ],
            "domain": "trade",
            "difficulty": "novel_synthesis",
        }
    )
    assert rec.benchmark == "deepresearch_bench"
    assert rec.metadata["domain"] == "trade"
    assert len(rec.expected_citations) == 2


def test_dispatch_known_and_unknown():
    rec = adapt("browsecomp", {"id": "x", "prompt": "test prompt"})
    assert isinstance(rec, IndustryRunRecord)
    with pytest.raises(ValueError):
        adapt("not_a_real_benchmark", {})  # type: ignore[arg-type]


def test_round_trip_via_dispatch():
    rec = adapt(
        "deepresearch_bench",
        {"question_id": "drb_1", "query": "Some research query about housing."},
    )
    assert rec.question_id == "drb_1"
    assert rec.expected_citations == []
