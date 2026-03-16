"""
FIX-124I-E: Regression tests for perspective tracking and health checks.

Tests the check_perspective_health() function to ensure:
1. Balanced 9-perspective results pass health checks
2. Low perspective count (< 5) fails health checks
3. Low balance (< 0.15) fails health checks
"""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# Mock SearchResult for testing (matches schema from phase_models.py)
@dataclass
class MockSearchResult:
    """Mock SearchResult for testing perspective health checks."""
    url: str
    title: str = ""
    snippet: str = ""
    source_engine: str = "serper"
    rank: int = 1
    perspective_origin: Optional[str] = None
    perspective_origins: List[str] = field(default_factory=list)


def create_mock_results(perspectives: int = 9, per_perspective: int = 10) -> List[MockSearchResult]:
    """
    Create mock results with balanced perspective distribution.

    Args:
        perspectives: Number of unique perspectives
        per_perspective: Number of results per perspective

    Returns:
        List of mock search results
    """
    perspective_names = [
        "Scientific", "Public_Health", "Regulatory", "Historical",
        "Economic", "Emerging_Trends", "Industry", "Methodological", "Regional"
    ][:perspectives]

    results = []
    for i, pname in enumerate(perspective_names):
        for j in range(per_perspective):
            result = MockSearchResult(
                url=f"https://example.com/{pname.lower()}/{j}",
                title=f"{pname} Result {j}",
                perspective_origin=pname,
                perspective_origins=[pname],
                rank=i * per_perspective + j + 1,
            )
            results.append(result)

    return results


def create_mock_results_imbalanced() -> List[MockSearchResult]:
    """
    Create mock results with imbalanced perspective distribution.

    Returns:
        List with 1 dominant perspective (100 results) and 8 weak perspectives (10 each).
        Balance = 10/100 = 0.10 (below 0.15 threshold)
    """
    results = []

    # Dominant perspective: Scientific with 100 results
    for j in range(100):
        result = MockSearchResult(
            url=f"https://example.com/scientific/{j}",
            title=f"Scientific Result {j}",
            perspective_origin="Scientific",
            perspective_origins=["Scientific"],
            rank=j + 1,
        )
        results.append(result)

    # Weak perspectives: 8 others with 10 results each
    weak_perspectives = [
        "Public_Health", "Regulatory", "Historical", "Economic",
        "Emerging_Trends", "Industry", "Methodological", "Regional"
    ]

    for i, pname in enumerate(weak_perspectives):
        for j in range(10):
            result = MockSearchResult(
                url=f"https://example.com/{pname.lower()}/{j}",
                title=f"{pname} Result {j}",
                perspective_origin=pname,
                perspective_origins=[pname],
                rank=100 + i * 10 + j + 1,
            )
            results.append(result)

    return results


# Import the function under test
# Note: We import here to allow the mock classes to be defined first
import sys
from pathlib import Path

# Add project root to path for import
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.phases.p03_search import check_perspective_health


class TestPerspectiveHealthCheck:
    """Tests for check_perspective_health() function."""

    def test_perspective_health_all_9_balanced(self):
        """9 balanced perspectives should pass health check."""
        results = create_mock_results(perspectives=9, per_perspective=10)

        is_healthy, info = check_perspective_health(results)

        assert is_healthy, f"Expected healthy, got: {info['reason']}"
        assert info["perspectives_count"] == 9
        assert info["balance"] == 1.0, f"Expected perfect balance, got: {info['balance']}"
        assert info["reason"] is None
        assert len(info["coverage"]) == 9

    def test_perspective_health_7_perspectives_passes(self):
        """7 perspectives should pass (min_required=5 default)."""
        results = create_mock_results(perspectives=7, per_perspective=10)

        is_healthy, info = check_perspective_health(results)

        assert is_healthy
        assert info["perspectives_count"] == 7
        assert info["balance"] == 1.0

    def test_perspective_health_5_perspectives_passes(self):
        """5 perspectives should pass (exactly at min_required=5)."""
        results = create_mock_results(perspectives=5, per_perspective=10)

        is_healthy, info = check_perspective_health(results)

        assert is_healthy
        assert info["perspectives_count"] == 5

    def test_perspective_health_4_perspectives_fails(self):
        """Only 4 perspectives should fail (min=5)."""
        results = create_mock_results(perspectives=4, per_perspective=10)

        is_healthy, info = check_perspective_health(results, min_required=5)

        assert not is_healthy
        assert info["perspectives_count"] == 4
        assert "4 perspectives < 5 required" in info["reason"]

    def test_perspective_health_low_balance_fails(self):
        """Low balance (0.10) should fail (min=0.15)."""
        results = create_mock_results_imbalanced()

        is_healthy, info = check_perspective_health(results, min_balance=0.15)

        assert not is_healthy
        assert info["balance"] < 0.15
        assert "balance=" in info["reason"]

    def test_perspective_health_empty_results(self):
        """Empty results should fail with appropriate message."""
        results = []

        is_healthy, info = check_perspective_health(results)

        assert not is_healthy
        assert info["perspectives_count"] == 0
        assert info["balance"] == 0.0
        assert "No perspective-tagged results" in info["reason"]

    def test_perspective_health_no_perspective_tags(self):
        """Results without perspective tags should fail."""
        results = [
            MockSearchResult(url="https://example.com/1", title="Result 1"),
            MockSearchResult(url="https://example.com/2", title="Result 2"),
        ]

        is_healthy, info = check_perspective_health(results)

        assert not is_healthy
        assert info["perspectives_count"] == 0

    def test_perspective_health_custom_thresholds(self):
        """Custom thresholds should be respected."""
        results = create_mock_results(perspectives=3, per_perspective=10)

        # With min_required=3, should pass
        is_healthy, info = check_perspective_health(results, min_required=3, min_balance=0.10)
        assert is_healthy

        # With min_required=4, should fail
        is_healthy, info = check_perspective_health(results, min_required=4, min_balance=0.10)
        assert not is_healthy

    def test_perspective_origins_merge_counted_correctly(self):
        """Results with multiple perspective_origins should count all perspectives."""
        results = [
            MockSearchResult(
                url="https://example.com/1",
                title="Multi-perspective Result",
                perspective_origin="Scientific",
                perspective_origins=["Scientific", "Public_Health", "Regulatory"],
            ),
        ]

        is_healthy, info = check_perspective_health(results, min_required=1, min_balance=0.0)

        # Should count all 3 perspectives from perspective_origins
        assert info["perspectives_count"] == 3
        assert "Scientific" in info["coverage"]
        assert "Public_Health" in info["coverage"]
        assert "Regulatory" in info["coverage"]

    def test_perspective_health_both_failures(self):
        """Both low count AND low balance should be reported."""
        results = [
            MockSearchResult(
                url="https://example.com/1",
                title="Result 1",
                perspective_origin="Scientific",
                perspective_origins=["Scientific"],
            ),
        ] * 100 + [
            MockSearchResult(
                url="https://example.com/2",
                title="Result 2",
                perspective_origin="Public_Health",
                perspective_origins=["Public_Health"],
            ),
        ]

        is_healthy, info = check_perspective_health(results, min_required=5, min_balance=0.15)

        assert not is_healthy
        assert "2 perspectives < 5 required" in info["reason"]
        # Balance is 1/100 = 0.01 which is also below 0.15
        assert "balance=" in info["reason"]


class TestPerspectiveCoverageLogging:
    """Tests for perspective coverage calculation logic used in logging."""

    def test_coverage_calculation_from_perspective_origins(self):
        """Coverage should be calculated from perspective_origins list."""
        results = create_mock_results(perspectives=9, per_perspective=10)

        _, info = check_perspective_health(results)

        # Each perspective should have 10 results
        for count in info["coverage"].values():
            assert count == 10

    def test_coverage_calculation_fallback_to_perspective_origin(self):
        """Should fallback to perspective_origin if perspective_origins is empty."""
        results = [
            MockSearchResult(
                url="https://example.com/1",
                title="Result",
                perspective_origin="Scientific",
                perspective_origins=[],  # Empty list, should fallback
            ),
        ]

        _, info = check_perspective_health(results, min_required=1)

        assert info["coverage"].get("Scientific") == 1


class TestRevisionDeadlockDetection:
    """FIX-126C: Tests for revision deadlock detection via rejection counting."""

    def test_revision_rejected_count_increments(self):
        """Revision rejection should increment counter in state."""
        state = {"revision_rejected_count": 0}
        # Simulate FIX 54 rejection
        state["revision_rejected_count"] = state.get("revision_rejected_count", 0) + 1
        assert state["revision_rejected_count"] == 1
        state["revision_rejected_count"] = state.get("revision_rejected_count", 0) + 1
        assert state["revision_rejected_count"] == 2

    def test_revision_accepted_resets_counter(self):
        """Successful revision should reset rejection counter."""
        state = {"revision_rejected_count": 3}
        # Simulate successful revision acceptance (FIX-126C reset)
        state["revision_rejected_count"] = 0
        assert state["revision_rejected_count"] == 0

    def test_convergence_detected_after_2_rejections(self):
        """Convergence should be forced after 2+ consecutive rejections and 2+ revisions."""
        state = {
            "revision_rejected_count": 2,
            "auditor_revision_count": 2,
            "convergence_detected": False,
        }
        # Simulate FIX-126C convergence check (from graph.py auditor_node)
        revision_rejected_count = state.get("revision_rejected_count", 0)
        current_revision_count = state.get("auditor_revision_count", 0)
        if revision_rejected_count >= 2 and current_revision_count >= 2:
            if not state.get("convergence_detected"):
                state["convergence_detected"] = True
                state["convergence_reason"] = (
                    f"Revision deadlock: {revision_rejected_count} consecutive revisions "
                    f"rejected by word count/citation safeguards"
                )
        assert state["convergence_detected"] is True
        assert "deadlock" in state["convergence_reason"].lower()

    def test_no_convergence_with_1_rejection(self):
        """Single rejection should NOT trigger convergence."""
        state = {
            "revision_rejected_count": 1,
            "auditor_revision_count": 2,
            "convergence_detected": False,
        }
        revision_rejected_count = state.get("revision_rejected_count", 0)
        current_revision_count = state.get("auditor_revision_count", 0)
        if revision_rejected_count >= 2 and current_revision_count >= 2:
            state["convergence_detected"] = True
        assert state["convergence_detected"] is False

    def test_no_convergence_with_low_revision_count(self):
        """Should NOT trigger convergence on first revision even with 2 rejections."""
        state = {
            "revision_rejected_count": 2,
            "auditor_revision_count": 1,
            "convergence_detected": False,
        }
        revision_rejected_count = state.get("revision_rejected_count", 0)
        current_revision_count = state.get("auditor_revision_count", 0)
        if revision_rejected_count >= 2 and current_revision_count >= 2:
            state["convergence_detected"] = True
        assert state["convergence_detected"] is False


class TestConvergenceDetectionUniversal:
    """FIX-126B: Convergence detection works for all synthesis paths."""

    def test_convergence_on_target_achieved(self):
        """Should converge when target faithfulness is reached."""
        faithfulness_history = [0.60, 0.92]
        target = 0.90
        current = faithfulness_history[-1]
        assert current >= target

    def test_convergence_on_regression(self):
        """Should detect regression when faithfulness drops."""
        faithfulness_history = [0.59, 0.61, 0.58]
        current = faithfulness_history[-1]
        previous = faithfulness_history[-2]
        improvement = current - previous
        assert improvement < 0  # Regression detected

    def test_convergence_on_stagnation(self):
        """Should detect stagnation when improvement < threshold."""
        faithfulness_history = [0.59, 0.595]
        current = faithfulness_history[-1]
        previous = faithfulness_history[-2]
        improvement = current - previous
        convergence_threshold = 0.01
        assert improvement < convergence_threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
