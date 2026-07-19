"""
Unit tests for wiki mesh snowball formulas (Unit 4).

Tests the 4 bounded feedback mechanisms from design doc §8:
  M1: usage_bonus — age-decayed, ≥ 1.0
  M2: corroboration_factor — sqrt-bounded, ≥ 1.0
  M3: contradiction_penalty — ≤ 1.0
  M4: upload_gravity_boost — fixed ×1.3

Also tests:
  - Composite compute_snowball_score
  - Design doc bounds (times_used=100 age<30d ≈ 1.46, age>2y ≈ 1.0)
  - Edge cases (negative inputs, zero inputs, extreme values)

Run:
    python -m pytest tests/unit/test_mesh_snowball.py -v
"""

from __future__ import annotations

import math

import pytest

from src.polaris_graph.wiki.mesh.snowball import (
    contradiction_penalty,
    corroboration_factor,
    compute_snowball_score,
    upload_gravity_boost,
    usage_bonus,
)


# ───── TestUsageBonus (M1) ─────

class TestUsageBonus:
    def test_zero_uses_returns_one(self):
        assert usage_bonus(0, 0.0) == 1.0

    def test_negative_uses_returns_one(self):
        assert usage_bonus(-5, 0.0) == 1.0

    def test_negative_age_returns_one(self):
        assert usage_bonus(10, -1.0) == 1.0

    def test_always_at_least_one(self):
        for uses in [1, 10, 100, 1000]:
            for age in [0, 30, 365, 730, 3650]:
                assert usage_bonus(uses, float(age)) >= 1.0

    def test_design_doc_bound_high_use_fresh(self):
        # times_used=100, age<30d → ≈ 1.46
        bonus = usage_bonus(100, 0.0)
        assert 1.40 < bonus < 1.50, f"Expected ~1.46, got {bonus}"

    def test_design_doc_bound_high_use_stale(self):
        # times_used=100, age>2y → ≈ 1.06
        bonus = usage_bonus(100, 730.0)
        assert 1.0 < bonus < 1.10, f"Expected ~1.06, got {bonus}"

    def test_bonus_decays_with_age(self):
        fresh = usage_bonus(50, 0.0)
        aged = usage_bonus(50, 365.0)
        very_old = usage_bonus(50, 730.0)
        assert fresh > aged > very_old > 1.0

    def test_bonus_increases_with_uses(self):
        low = usage_bonus(1, 30.0)
        mid = usage_bonus(10, 30.0)
        high = usage_bonus(100, 30.0)
        assert high > mid > low > 1.0


# ───── TestCorroborationFactor (M2) ─────

class TestCorroborationFactor:
    def test_zero_count_returns_one(self):
        assert corroboration_factor(0) == 1.0

    def test_negative_count_returns_one(self):
        assert corroboration_factor(-3) == 1.0

    def test_always_at_least_one(self):
        for c in range(0, 200):
            assert corroboration_factor(c) >= 1.0

    def test_sqrt_growth(self):
        # count=1 → 1 + 0.3 * 1 = 1.3
        assert corroboration_factor(1) == pytest.approx(1.3)
        # count=4 → 1 + 0.3 * 2 = 1.6
        assert corroboration_factor(4) == pytest.approx(1.6)
        # count=9 → 1 + 0.3 * 3 = 1.9
        assert corroboration_factor(9) == pytest.approx(1.9)

    def test_practical_max(self):
        # count=10 → 1 + 0.3 * sqrt(10) ≈ 1.949
        f = corroboration_factor(10)
        assert 1.9 < f < 2.0

    def test_theoretical_max_count_100(self):
        # count=100 → 1 + 0.3 * 10 = 4.0
        assert corroboration_factor(100) == pytest.approx(4.0)

    def test_sublinear_growth(self):
        # Growth from 1→4 (4x input) should be less than 4x output
        f1 = corroboration_factor(1)
        f4 = corroboration_factor(4)
        ratio = (f4 - 1.0) / (f1 - 1.0)
        assert ratio < 4.0  # sqrt makes it sublinear


# ───── TestContradictionPenalty (M3) ─────

class TestContradictionPenalty:
    def test_no_contradiction_returns_one(self):
        assert contradiction_penalty(False) == 1.0

    def test_contradiction_returns_07(self):
        assert contradiction_penalty(True) == pytest.approx(0.7)


# ───── TestUploadGravityBoost (M4) ─────

class TestUploadGravityBoost:
    def test_non_upload_returns_one(self):
        assert upload_gravity_boost(False) == 1.0

    def test_upload_returns_13(self):
        assert upload_gravity_boost(True) == pytest.approx(1.3)


# ───── TestLethalSnowballScore ─────

class TestLethalSnowballScore:
    def test_baseline_only(self):
        # No snowball factors → just the base score
        assert compute_snowball_score(base_score=0.8) == pytest.approx(0.8)

    def test_all_factors_combined(self):
        score = compute_snowball_score(
            base_score=1.0,
            times_used=50,
            age_days=30.0,
            corroboration_count=4,
            has_contradiction=False,
            is_upload=True,
        )
        expected = (
            1.0
            * usage_bonus(50, 30.0)
            * corroboration_factor(4)
            * contradiction_penalty(False)
            * upload_gravity_boost(True)
        )
        assert score == pytest.approx(expected)

    def test_contradiction_reduces_score(self):
        no_c = compute_snowball_score(base_score=1.0, has_contradiction=False)
        with_c = compute_snowball_score(base_score=1.0, has_contradiction=True)
        assert with_c < no_c
        assert with_c == pytest.approx(0.7)

    def test_upload_boosts_score(self):
        web = compute_snowball_score(base_score=1.0, is_upload=False)
        upload = compute_snowball_score(base_score=1.0, is_upload=True)
        assert upload > web
        assert upload == pytest.approx(1.3)

    def test_zero_base_stays_zero(self):
        # All factors are multiplicative → 0 * anything = 0
        score = compute_snowball_score(
            base_score=0.0,
            times_used=100,
            corroboration_count=50,
            is_upload=True,
        )
        assert score == 0.0

    def test_worst_case_maximum_bounded(self):
        # All factors at practical max:
        #   M1: times_used=100, age=0 → ~1.46
        #   M2: count=100 → 4.0
        #   M3: no contradiction → 1.0
        #   M4: upload → 1.3
        # Total: 1.0 * 1.46 * 4.0 * 1.0 * 1.3 ≈ 7.6
        score = compute_snowball_score(
            base_score=1.0,
            times_used=100,
            age_days=0.0,
            corroboration_count=100,
            has_contradiction=False,
            is_upload=True,
        )
        assert score < 10.0, f"Snowball score {score} exceeds expected max"
        assert score > 5.0, f"Snowball score {score} is suspiciously low"
