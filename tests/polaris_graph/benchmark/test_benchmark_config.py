"""Tests for benchmark.benchmark_config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from polaris_graph.benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkQuestion,
    load_config,
)


# ---------- BenchmarkQuestion ----------

def test_question_minimal():
    q = BenchmarkQuestion(
        question_id="Q01",
        question_text="Is aspirin effective?",
        scope_class="clinical_efficacy",
    )
    assert q.expected_pico_axes == []
    assert q.is_refusal_bait is False
    assert q.notes == ""


def test_question_full():
    q = BenchmarkQuestion(
        question_id="Q01",
        question_text="Is aspirin effective for headache?",
        scope_class="clinical_efficacy",
        expected_pico_axes=["population", "intervention", "outcome"],
        is_refusal_bait=False,
        notes="Canonical test",
    )
    assert len(q.expected_pico_axes) == 3


def test_question_id_path_traversal_rejected():
    with pytest.raises(ValidationError, match="path"):
        BenchmarkQuestion(
            question_id="../etc/passwd",
            question_text="x",
            scope_class="clinical_efficacy",
        )


def test_question_id_slash_rejected():
    with pytest.raises(ValidationError, match="path"):
        BenchmarkQuestion(
            question_id="bad/id",
            question_text="x",
            scope_class="clinical_efficacy",
        )


def test_question_blank_text_rejected():
    with pytest.raises(ValidationError):
        BenchmarkQuestion(
            question_id="Q1",
            question_text="",
            scope_class="clinical_efficacy",
        )


def test_question_invalid_scope_class_rejected():
    with pytest.raises(ValidationError):
        BenchmarkQuestion(
            question_id="Q1",
            question_text="x",
            scope_class="bogus",  # type: ignore[arg-type]
        )


def test_question_invalid_axis_rejected():
    with pytest.raises(ValidationError):
        BenchmarkQuestion(
            question_id="Q1",
            question_text="x",
            scope_class="clinical_efficacy",
            expected_pico_axes=["comparator"],  # type: ignore[list-item]
        )


def test_question_axes_must_be_unique():
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkQuestion(
            question_id="Q1",
            question_text="x",
            scope_class="clinical_efficacy",
            expected_pico_axes=["population", "population"],
        )


def test_question_refusal_bait_default_false():
    q = BenchmarkQuestion(
        question_id="Q1", question_text="x", scope_class="clinical_efficacy"
    )
    assert q.is_refusal_bait is False


# ---------- BenchmarkConfig ----------

def _q(qid: str, refusal_bait: bool = False) -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id=qid,
        question_text=f"text for {qid}",
        scope_class="out_of_scope" if refusal_bait else "clinical_efficacy",
        is_refusal_bait=refusal_bait,
    )


def test_config_minimal():
    c = BenchmarkConfig(benchmark_id="test", questions=[_q("Q1")])
    assert c.benchmark_version == "1.0"
    assert len(c.questions) == 1


def test_config_question_ids_unique():
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkConfig(
            benchmark_id="test",
            questions=[_q("Q1"), _q("Q1")],
        )


def test_config_empty_questions_rejected():
    with pytest.raises(ValidationError):
        BenchmarkConfig(benchmark_id="test", questions=[])


def test_config_benchmark_id_path_chars_rejected():
    with pytest.raises(ValidationError):
        BenchmarkConfig(
            benchmark_id="../escape", questions=[_q("Q1")]
        )


def test_config_question_ids_helper():
    c = BenchmarkConfig(
        benchmark_id="test", questions=[_q("Q1"), _q("Q2"), _q("Q3")]
    )
    assert c.question_ids() == ["Q1", "Q2", "Q3"]


def test_config_question_by_id():
    c = BenchmarkConfig(
        benchmark_id="test", questions=[_q("Q1"), _q("Q2")]
    )
    assert c.question_by_id("Q1").question_id == "Q1"
    assert c.question_by_id("nonexistent") is None


def test_config_refusal_bait_count():
    c = BenchmarkConfig(
        benchmark_id="test",
        questions=[
            _q("Q1"),
            _q("Q2", refusal_bait=True),
            _q("Q3", refusal_bait=True),
        ],
    )
    assert c.refusal_bait_count() == 2


# ---------- load_config + canonical clinical_n10.json ----------

def test_load_canonical_config_file():
    path = Path(__file__).resolve().parents[3] / "config" / "benchmark" / "clinical_n10.json"
    c = load_config(path)
    assert c.benchmark_id == "clinical_n10_v1"
    assert len(c.questions) == 10


def test_canonical_config_has_2_refusal_bait():
    path = Path(__file__).resolve().parents[3] / "config" / "benchmark" / "clinical_n10.json"
    c = load_config(path)
    assert c.refusal_bait_count() == 2


def test_canonical_config_question_ids_unique():
    path = Path(__file__).resolve().parents[3] / "config" / "benchmark" / "clinical_n10.json"
    c = load_config(path)
    ids = c.question_ids()
    assert len(set(ids)) == len(ids)


def test_canonical_config_includes_all_scope_classes():
    """N=10 mix should include efficacy/safety/diagnosis/prognosis + 2 refusal."""
    path = Path(__file__).resolve().parents[3] / "config" / "benchmark" / "clinical_n10.json"
    c = load_config(path)
    classes = {q.scope_class for q in c.questions}
    assert "clinical_efficacy" in classes
    assert "clinical_safety" in classes
    assert "clinical_diagnosis" in classes
    assert "clinical_prognosis" in classes
    assert "out_of_scope" in classes


def test_load_config_round_trip(tmp_path: Path):
    """Write a config, load it, assert equality of essential fields."""
    src = BenchmarkConfig(
        benchmark_id="round_trip",
        description="test",
        questions=[_q("Q1"), _q("Q2", refusal_bait=True)],
    )
    p = tmp_path / "config.json"
    p.write_text(json.dumps(src.model_dump(mode="json"), indent=2))
    loaded = load_config(p)
    assert loaded.benchmark_id == "round_trip"
    assert len(loaded.questions) == 2
    assert loaded.refusal_bait_count() == 1
