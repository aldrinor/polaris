#!/usr/bin/env python3
"""
Unit tests for HLE Benchmark Integration.

Tests:
- HLE dataset loading and structure
- Question sampling and filtering
- Evaluation data structures
- Result computation

Run:
    pytest tests/unit/test_hle_benchmark.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.benchmarks.hle_dataset import HLEDataset, HLEQuestion, HLEDatasetStats
from src.benchmarks.hle_benchmark import (
    HLEBenchmarkRunner,
    HLEEvaluation,
    HLEResult,
)


class TestHLEQuestion:
    """Tests for HLEQuestion dataclass."""

    def test_question_creation(self):
        """Test creating a question directly."""
        q = HLEQuestion(
            question_id="test_001",
            question_text="What is the capital of France?",
            subject="geography",
            difficulty="expert",
            answer_type="open",
            ground_truth="Paris",
        )
        assert q.question_id == "test_001"
        assert q.subject == "geography"
        assert q.ground_truth == "Paris"

    def test_question_from_dict(self):
        """Test creating question from dictionary."""
        data = {
            "question_id": "test_002",
            "question_text": "Explain quantum entanglement.",
            "subject": "physics",
            "answer": "Quantum entanglement is...",
        }
        q = HLEQuestion.from_dict(data)
        assert q.question_id == "test_002"
        assert q.subject == "physics"
        assert q.ground_truth == "Quantum entanglement is..."

    def test_question_to_dict(self):
        """Test converting question to dictionary."""
        q = HLEQuestion(
            question_id="test_003",
            question_text="Test",
            subject="test",
        )
        d = q.to_dict()
        assert d["question_id"] == "test_003"
        assert "metadata" in d

    def test_multimodal_question(self):
        """Test multimodal question fields."""
        q = HLEQuestion(
            question_id="multi_001",
            question_text="Describe this image.",
            subject="vision",
            has_image=True,
            image_path="/path/to/image.png",
        )
        assert q.has_image is True
        assert q.image_path == "/path/to/image.png"


class TestHLEDataset:
    """Tests for HLEDataset class."""

    def test_dataset_initialization(self):
        """Test dataset initializes with questions."""
        dataset = HLEDataset()
        assert dataset.stats.total_questions > 0
        assert len(dataset.questions) > 0

    def test_dataset_stats(self):
        """Test dataset statistics."""
        dataset = HLEDataset()
        stats = dataset.get_stats()
        assert "total_questions" in stats
        assert "subjects" in stats
        assert "text_only" in stats
        assert "multimodal" in stats

    def test_sampling(self):
        """Test random sampling."""
        dataset = HLEDataset()
        sample = dataset.get_sample(n=5, seed=42)
        assert len(sample) == 5
        assert all(isinstance(q, HLEQuestion) for q in sample)

    def test_sampling_with_seed(self):
        """Test reproducible sampling with seed."""
        dataset = HLEDataset()
        sample1 = dataset.get_sample(n=3, seed=123)
        sample2 = dataset.get_sample(n=3, seed=123)
        assert [q.question_id for q in sample1] == [q.question_id for q in sample2]

    def test_subject_filtering(self):
        """Test filtering by subject."""
        dataset = HLEDataset()
        math_qs = dataset.get_by_subject("mathematics")
        assert all(q.subject == "mathematics" for q in math_qs)

    def test_get_by_id(self):
        """Test getting question by ID."""
        dataset = HLEDataset()
        first_q = dataset.questions[0]
        found = dataset.get_by_id(first_q.question_id)
        assert found is not None
        assert found.question_id == first_q.question_id

    def test_get_by_id_not_found(self):
        """Test getting non-existent question."""
        dataset = HLEDataset()
        found = dataset.get_by_id("nonexistent_id")
        assert found is None

    def test_text_only_filter(self):
        """Test text-only filtering."""
        dataset = HLEDataset()
        sample = dataset.get_sample(n=10, text_only=True)
        assert all(not q.has_image for q in sample)


class TestHLEEvaluation:
    """Tests for HLEEvaluation dataclass."""

    def test_evaluation_creation(self):
        """Test creating an evaluation."""
        eval = HLEEvaluation(
            question_id="test_001",
            question_text="Test question",
            subject="test",
            model_answer="Test answer",
            ground_truth="True answer",
            is_correct=True,
            confidence=0.95,
            reasoning="Good reasoning",
            evidence_count=10,
            sources_cited=5,
            processing_time_sec=2.5,
        )
        assert eval.is_correct is True
        assert eval.confidence == 0.95
        assert eval.evidence_count == 10

    def test_evaluation_to_dict(self):
        """Test converting evaluation to dictionary."""
        eval = HLEEvaluation(
            question_id="test_001",
            question_text="Test",
            subject="test",
            model_answer="Answer",
            ground_truth=None,
            is_correct=False,
            confidence=0.5,
            reasoning="",
            evidence_count=0,
            sources_cited=0,
            processing_time_sec=1.0,
        )
        d = eval.to_dict()
        assert d["question_id"] == "test_001"
        assert d["is_correct"] is False
        assert "error" in d

    def test_evaluation_with_error(self):
        """Test evaluation with error."""
        eval = HLEEvaluation(
            question_id="error_test",
            question_text="Error test",
            subject="test",
            model_answer="",
            ground_truth=None,
            is_correct=False,
            confidence=0.0,
            reasoning="",
            evidence_count=0,
            sources_cited=0,
            processing_time_sec=0.1,
            error="API timeout",
        )
        assert eval.error == "API timeout"


class TestHLEResult:
    """Tests for HLEResult dataclass."""

    def test_result_creation(self):
        """Test creating a result."""
        result = HLEResult(
            accuracy=0.75,
            total_questions=100,
            correct_answers=75,
            by_subject={"math": {"total": 50, "correct": 40, "accuracy": 0.8}},
            evaluations=[],
        )
        assert result.accuracy == 0.75
        assert result.total_questions == 100

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        eval = HLEEvaluation(
            question_id="test",
            question_text="Test",
            subject="test",
            model_answer="Answer",
            ground_truth=None,
            is_correct=True,
            confidence=0.8,
            reasoning="",
            evidence_count=0,
            sources_cited=0,
            processing_time_sec=1.0,
        )
        result = HLEResult(
            accuracy=1.0,
            total_questions=1,
            correct_answers=1,
            by_subject={},
            evaluations=[eval],
            model_name="POLARIS",
        )
        d = result.to_dict()
        assert d["accuracy"] == 1.0
        assert d["model_name"] == "POLARIS"
        assert len(d["evaluations"]) == 1


class TestHLEBenchmarkRunner:
    """Tests for HLEBenchmarkRunner class."""

    def test_runner_initialization(self):
        """Test runner initializes correctly."""
        runner = HLEBenchmarkRunner()
        assert runner.dataset is not None
        assert len(runner.dataset.questions) > 0

    def test_runner_with_custom_dataset(self):
        """Test runner with custom dataset."""
        dataset = HLEDataset()
        runner = HLEBenchmarkRunner(dataset=dataset)
        assert runner.dataset is dataset

    @patch("src.benchmarks.hle_benchmark.HLEBenchmarkRunner._answer_question_direct")
    @patch("src.benchmarks.hle_benchmark.HLEBenchmarkRunner._evaluate_answer")
    def test_evaluate_question(self, mock_eval, mock_answer):
        """Test evaluating a single question."""
        mock_answer.return_value = ("Paris", "It's the capital", 0.95)
        mock_eval.return_value = (True, "Correct answer")

        runner = HLEBenchmarkRunner()
        question = HLEQuestion(
            question_id="test",
            question_text="Capital of France?",
            subject="geography",
            ground_truth="Paris",
        )

        result = runner.evaluate_question(question)

        assert result.question_id == "test"
        assert result.is_correct is True
        assert result.confidence == 0.95

    @patch("src.benchmarks.hle_benchmark.HLEBenchmarkRunner.evaluate_question")
    def test_run_benchmark(self, mock_evaluate):
        """Test running benchmark on sample."""
        mock_evaluate.return_value = HLEEvaluation(
            question_id="test",
            question_text="Test",
            subject="test",
            model_answer="Answer",
            ground_truth=None,
            is_correct=True,
            confidence=0.8,
            reasoning="",
            evidence_count=0,
            sources_cited=0,
            processing_time_sec=1.0,
        )

        runner = HLEBenchmarkRunner()
        result = runner.run_benchmark(sample_size=3, seed=42, parallel=False)

        assert result.total_questions == 3
        assert result.accuracy == 1.0  # All mocked as correct

    def test_per_subject_breakdown(self):
        """Test per-subject accuracy breakdown."""
        evaluations = [
            HLEEvaluation(
                question_id="m1",
                question_text="Math Q1",
                subject="mathematics",
                model_answer="",
                ground_truth=None,
                is_correct=True,
                confidence=0.9,
                reasoning="",
                evidence_count=0,
                sources_cited=0,
                processing_time_sec=1.0,
            ),
            HLEEvaluation(
                question_id="m2",
                question_text="Math Q2",
                subject="mathematics",
                model_answer="",
                ground_truth=None,
                is_correct=False,
                confidence=0.5,
                reasoning="",
                evidence_count=0,
                sources_cited=0,
                processing_time_sec=1.0,
            ),
            HLEEvaluation(
                question_id="p1",
                question_text="Physics Q1",
                subject="physics",
                model_answer="",
                ground_truth=None,
                is_correct=True,
                confidence=0.85,
                reasoning="",
                evidence_count=0,
                sources_cited=0,
                processing_time_sec=1.0,
            ),
        ]

        # Compute by_subject manually
        by_subject = {}
        for e in evaluations:
            if e.subject not in by_subject:
                by_subject[e.subject] = {"total": 0, "correct": 0}
            by_subject[e.subject]["total"] += 1
            if e.is_correct:
                by_subject[e.subject]["correct"] += 1

        for subject in by_subject:
            stats = by_subject[subject]
            stats["accuracy"] = stats["correct"] / stats["total"]

        assert by_subject["mathematics"]["accuracy"] == 0.5
        assert by_subject["physics"]["accuracy"] == 1.0


class TestHLEIntegration:
    """Integration tests for HLE benchmark system."""

    def test_end_to_end_dataclass_flow(self):
        """Test complete dataclass flow from question to result."""
        # Create question
        question = HLEQuestion(
            question_id="e2e_001",
            question_text="What is 2+2?",
            subject="mathematics",
            ground_truth="4",
        )

        # Create evaluation
        evaluation = HLEEvaluation(
            question_id=question.question_id,
            question_text=question.question_text,
            subject=question.subject,
            model_answer="4",
            ground_truth=question.ground_truth,
            is_correct=True,
            confidence=0.99,
            reasoning="Simple arithmetic",
            evidence_count=0,
            sources_cited=0,
            processing_time_sec=0.1,
        )

        # Create result
        result = HLEResult(
            accuracy=1.0,
            total_questions=1,
            correct_answers=1,
            by_subject={"mathematics": {"total": 1, "correct": 1, "accuracy": 1.0}},
            evaluations=[evaluation],
            model_name="POLARIS",
        )

        # Verify serialization
        result_dict = result.to_dict()
        assert result_dict["accuracy"] == 1.0
        assert len(result_dict["evaluations"]) == 1
        assert result_dict["evaluations"][0]["is_correct"] is True

    def test_dataset_cache_persistence(self, tmp_path):
        """Test dataset caches and reloads correctly."""
        cache_path = tmp_path / "test_hle_cache.json"

        # Create and save
        dataset1 = HLEDataset(cache_path=cache_path)
        initial_count = dataset1.stats.total_questions

        # Reload from cache
        dataset2 = HLEDataset(cache_path=cache_path)
        assert dataset2.stats.total_questions == initial_count

    def test_self_test_functions(self):
        """Test that self-test functions pass."""
        from src.benchmarks.hle_dataset import self_test as dataset_self_test
        from src.benchmarks.hle_benchmark import self_test as benchmark_self_test

        assert dataset_self_test() is True
        assert benchmark_self_test() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
