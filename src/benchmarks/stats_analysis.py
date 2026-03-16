"""
POLARIS SOTA Validation Framework - Statistical Analysis

Created: 2026-02-05
Purpose: Rigorous statistical analysis for SOTA comparison claims

This module provides:
1. Bootstrap confidence intervals
2. Paired t-test / Wilcoxon signed-rank
3. Effect size (Cohen's d)
4. Bonferroni correction for multiple comparisons
5. Power analysis

Required for publication-grade SOTA claims.
"""

import math
import random
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class StatisticalTestResult:
    """Result of a statistical test."""

    test_name: str
    """Name of the statistical test."""

    statistic: float
    """Test statistic value."""

    p_value: float
    """P-value of the test."""

    significant: bool
    """Whether the result is significant at alpha level."""

    alpha: float
    """Significance level used."""

    effect_size: Optional[float] = None
    """Effect size (Cohen's d or similar)."""

    effect_interpretation: Optional[str] = None
    """Interpretation of effect size (small/medium/large)."""

    confidence_interval: Optional[Tuple[float, float]] = None
    """95% confidence interval."""

    sample_size: int = 0
    """Sample size used."""

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    """Result of comparing POLARIS to a baseline."""

    polaris_mean: float
    """Mean score for POLARIS."""

    baseline_mean: float
    """Mean score for baseline."""

    difference: float
    """Difference (POLARIS - baseline)."""

    test_result: StatisticalTestResult
    """Statistical test result."""

    is_sota: bool
    """Whether POLARIS beats baseline with significance."""

    interpretation: str
    """Human-readable interpretation."""


class StatisticalAnalyzer:
    """
    Statistical analysis for SOTA validation.

    Provides rigorous tests required for publication-grade claims:
    - Bootstrap CI (10,000 iterations)
    - Paired comparisons (t-test or Wilcoxon)
    - Effect size with interpretation
    - Multiple comparison correction
    """

    DEFAULT_ALPHA = 0.05
    BOOTSTRAP_ITERATIONS = 10000
    RANDOM_SEED = 42

    def __init__(self, alpha: float = DEFAULT_ALPHA, seed: int = RANDOM_SEED):
        """
        Initialize analyzer.

        Args:
            alpha: Significance level (default 0.05).
            seed: Random seed for reproducibility.
        """
        self.alpha = alpha
        random.seed(seed)

    def bootstrap_confidence_interval(
        self,
        scores: List[float],
        confidence: float = 0.95,
        n_iterations: int = BOOTSTRAP_ITERATIONS,
    ) -> Tuple[float, float, float]:
        """
        Calculate bootstrap confidence interval for mean.

        Args:
            scores: List of scores.
            confidence: Confidence level (default 0.95).
            n_iterations: Number of bootstrap iterations.

        Returns:
            Tuple of (mean, lower_bound, upper_bound).
        """
        n = len(scores)
        if n == 0:
            return 0.0, 0.0, 0.0

        # Bootstrap resampling
        bootstrap_means = []
        for _ in range(n_iterations):
            sample = [random.choice(scores) for _ in range(n)]
            bootstrap_means.append(sum(sample) / len(sample))

        # Sort and find percentiles
        bootstrap_means.sort()
        alpha_half = (1 - confidence) / 2

        lower_idx = int(alpha_half * n_iterations)
        upper_idx = int((1 - alpha_half) * n_iterations)

        mean = sum(scores) / n
        lower = bootstrap_means[lower_idx]
        upper = bootstrap_means[min(upper_idx, n_iterations - 1)]

        return mean, lower, upper

    def paired_t_test(
        self,
        polaris_scores: List[float],
        baseline_scores: List[float],
    ) -> StatisticalTestResult:
        """
        Perform paired t-test comparing POLARIS to baseline.

        Args:
            polaris_scores: Scores for POLARIS (per question).
            baseline_scores: Scores for baseline (per question).

        Returns:
            StatisticalTestResult with test details.
        """
        n = len(polaris_scores)
        if n != len(baseline_scores):
            raise ValueError("Score lists must have equal length for paired test")

        if n < 2:
            return StatisticalTestResult(
                test_name="paired_t_test",
                statistic=0.0,
                p_value=1.0,
                significant=False,
                alpha=self.alpha,
                sample_size=n,
                metadata={"error": "Insufficient sample size"},
            )

        # Calculate differences
        differences = [p - b for p, b in zip(polaris_scores, baseline_scores)]
        mean_diff = sum(differences) / n

        # Calculate standard error
        variance = sum((d - mean_diff) ** 2 for d in differences) / (n - 1)
        std_error = math.sqrt(variance / n)

        if std_error == 0:
            t_statistic = float('inf') if mean_diff > 0 else float('-inf') if mean_diff < 0 else 0.0
            p_value = 0.0 if mean_diff != 0 else 1.0
        else:
            t_statistic = mean_diff / std_error
            # Two-tailed p-value approximation
            p_value = self._t_distribution_p_value(t_statistic, n - 1)

        # Effect size (Cohen's d for paired samples)
        if variance > 0:
            cohens_d = mean_diff / math.sqrt(variance)
        else:
            cohens_d = 0.0

        return StatisticalTestResult(
            test_name="paired_t_test",
            statistic=t_statistic,
            p_value=p_value,
            significant=p_value < self.alpha,
            alpha=self.alpha,
            effect_size=cohens_d,
            effect_interpretation=self._interpret_effect_size(cohens_d),
            sample_size=n,
            metadata={
                "mean_difference": mean_diff,
                "std_error": std_error,
                "degrees_freedom": n - 1,
            },
        )

    def wilcoxon_signed_rank(
        self,
        polaris_scores: List[float],
        baseline_scores: List[float],
    ) -> StatisticalTestResult:
        """
        Perform Wilcoxon signed-rank test (non-parametric alternative).

        Use when normality assumption is violated.

        Args:
            polaris_scores: Scores for POLARIS.
            baseline_scores: Scores for baseline.

        Returns:
            StatisticalTestResult with test details.
        """
        n = len(polaris_scores)
        if n != len(baseline_scores):
            raise ValueError("Score lists must have equal length")

        # Calculate differences
        differences = [p - b for p, b in zip(polaris_scores, baseline_scores)]

        # Remove zeros
        nonzero = [(abs(d), 1 if d > 0 else -1, d) for d in differences if d != 0]

        if len(nonzero) < 5:
            return StatisticalTestResult(
                test_name="wilcoxon_signed_rank",
                statistic=0.0,
                p_value=1.0,
                significant=False,
                alpha=self.alpha,
                sample_size=n,
                metadata={"error": "Too few non-zero differences"},
            )

        # Rank by absolute value
        nonzero.sort(key=lambda x: x[0])
        ranks = {}
        i = 0
        while i < len(nonzero):
            # Handle ties by averaging ranks
            j = i
            while j < len(nonzero) and nonzero[j][0] == nonzero[i][0]:
                j += 1
            avg_rank = (i + j + 1) / 2  # 1-indexed
            for k in range(i, j):
                ranks[k] = avg_rank
            i = j

        # Calculate W+ and W-
        w_plus = sum(ranks[i] for i in range(len(nonzero)) if nonzero[i][1] > 0)
        w_minus = sum(ranks[i] for i in range(len(nonzero)) if nonzero[i][1] < 0)

        # Test statistic is the smaller of W+ and W-
        w = min(w_plus, w_minus)

        # Normal approximation for p-value (n > 20)
        n_eff = len(nonzero)
        mean_w = n_eff * (n_eff + 1) / 4
        std_w = math.sqrt(n_eff * (n_eff + 1) * (2 * n_eff + 1) / 24)

        if std_w > 0:
            z = (w - mean_w) / std_w
            p_value = 2 * self._normal_cdf(-abs(z))  # Two-tailed
        else:
            p_value = 1.0

        # Effect size: r = Z / sqrt(N)
        effect_r = abs(z) / math.sqrt(n_eff) if n_eff > 0 else 0.0

        return StatisticalTestResult(
            test_name="wilcoxon_signed_rank",
            statistic=w,
            p_value=p_value,
            significant=p_value < self.alpha,
            alpha=self.alpha,
            effect_size=effect_r,
            effect_interpretation=self._interpret_r_effect_size(effect_r),
            sample_size=n,
            metadata={
                "w_plus": w_plus,
                "w_minus": w_minus,
                "n_nonzero": n_eff,
                "z_score": z if std_w > 0 else 0.0,
            },
        )

    def bonferroni_correction(
        self,
        p_values: List[float],
        alpha: Optional[float] = None,
    ) -> Tuple[List[bool], float]:
        """
        Apply Bonferroni correction for multiple comparisons.

        Args:
            p_values: List of p-values from multiple tests.
            alpha: Significance level (uses instance default if None).

        Returns:
            Tuple of (list of significant results, corrected alpha).
        """
        alpha = alpha or self.alpha
        n_tests = len(p_values)

        if n_tests == 0:
            return [], alpha

        corrected_alpha = alpha / n_tests
        significant = [p < corrected_alpha for p in p_values]

        return significant, corrected_alpha

    def compare_to_baseline(
        self,
        polaris_scores: List[float],
        baseline_score: float,
        baseline_name: str = "baseline",
    ) -> ComparisonResult:
        """
        Compare POLARIS scores to a fixed baseline (e.g., published SOTA).

        Args:
            polaris_scores: Per-question scores for POLARIS.
            baseline_score: Published baseline score (fixed value).
            baseline_name: Name of baseline system.

        Returns:
            ComparisonResult with statistical analysis.
        """
        n = len(polaris_scores)
        polaris_mean = sum(polaris_scores) / n if n > 0 else 0.0

        # Create synthetic baseline scores (all equal to published score)
        baseline_scores = [baseline_score] * n

        # Run statistical test
        test_result = self.paired_t_test(polaris_scores, baseline_scores)

        # Determine SOTA status
        is_sota = (
            polaris_mean > baseline_score and
            test_result.significant and
            (test_result.effect_size or 0.0) > 0.2  # At least small effect
        )

        # Build interpretation
        if is_sota:
            interpretation = (
                f"POLARIS ({polaris_mean:.2%}) significantly outperforms "
                f"{baseline_name} ({baseline_score:.2%}) with "
                f"p={test_result.p_value:.4f}, d={test_result.effect_size:.2f}"
            )
        elif polaris_mean > baseline_score:
            interpretation = (
                f"POLARIS ({polaris_mean:.2%}) scores higher than "
                f"{baseline_name} ({baseline_score:.2%}), but the difference "
                f"is not statistically significant (p={test_result.p_value:.4f})"
            )
        else:
            interpretation = (
                f"POLARIS ({polaris_mean:.2%}) does not outperform "
                f"{baseline_name} ({baseline_score:.2%})"
            )

        return ComparisonResult(
            polaris_mean=polaris_mean,
            baseline_mean=baseline_score,
            difference=polaris_mean - baseline_score,
            test_result=test_result,
            is_sota=is_sota,
            interpretation=interpretation,
        )

    def run_full_comparison(
        self,
        polaris_scores: List[float],
        baselines: Dict[str, float],
    ) -> Dict[str, ComparisonResult]:
        """
        Compare POLARIS to multiple baselines with correction.

        Args:
            polaris_scores: Per-question scores for POLARIS.
            baselines: Dict mapping baseline name to score.

        Returns:
            Dict mapping baseline name to comparison result.
        """
        results = {}
        p_values = []

        # First pass: run all comparisons
        for name, score in baselines.items():
            result = self.compare_to_baseline(polaris_scores, score, name)
            results[name] = result
            p_values.append(result.test_result.p_value)

        # Apply Bonferroni correction
        significant, corrected_alpha = self.bonferroni_correction(p_values)

        # Update significance based on correction
        for i, (name, result) in enumerate(results.items()):
            if not significant[i] and result.is_sota:
                result.is_sota = False
                result.interpretation += (
                    f" (Note: not significant after Bonferroni correction, "
                    f"corrected alpha={corrected_alpha:.4f})"
                )
            result.test_result.metadata["bonferroni_corrected"] = True
            result.test_result.metadata["corrected_alpha"] = corrected_alpha

        return results

    def calculate_required_sample_size(
        self,
        expected_difference: float,
        expected_std: float,
        power: float = 0.80,
        alpha: float = 0.05,
    ) -> int:
        """
        Calculate required sample size for desired power.

        Args:
            expected_difference: Expected mean difference.
            expected_std: Expected standard deviation.
            power: Desired statistical power (default 0.80).
            alpha: Significance level (default 0.05).

        Returns:
            Required sample size.
        """
        # Effect size
        if expected_std == 0:
            return 10  # Minimum

        d = abs(expected_difference) / expected_std

        # Use normal approximation for sample size
        z_alpha = self._normal_quantile(1 - alpha / 2)
        z_beta = self._normal_quantile(power)

        n = 2 * ((z_alpha + z_beta) / d) ** 2

        return max(10, math.ceil(n))

    def _interpret_effect_size(self, d: float) -> str:
        """Interpret Cohen's d effect size."""
        d = abs(d)
        if d < 0.2:
            return "negligible"
        elif d < 0.5:
            return "small"
        elif d < 0.8:
            return "medium"
        else:
            return "large"

    def _interpret_r_effect_size(self, r: float) -> str:
        """Interpret r effect size (Wilcoxon)."""
        r = abs(r)
        if r < 0.1:
            return "negligible"
        elif r < 0.3:
            return "small"
        elif r < 0.5:
            return "medium"
        else:
            return "large"

    def _t_distribution_p_value(self, t: float, df: int) -> float:
        """Approximate p-value for t-distribution (two-tailed)."""
        # Use normal approximation for large df
        if df > 30:
            return 2 * self._normal_cdf(-abs(t))

        # Simple approximation for small df
        x = abs(t) / math.sqrt(df + t ** 2)
        p = 1 - x
        return 2 * min(p, 1 - p)

    def _normal_cdf(self, z: float) -> float:
        """Standard normal CDF approximation."""
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))

    def _normal_quantile(self, p: float) -> float:
        """Inverse normal CDF approximation."""
        # Simple approximation using inverse error function
        if p <= 0:
            return float('-inf')
        if p >= 1:
            return float('inf')

        # Rational approximation
        t = math.sqrt(-2 * math.log(min(p, 1 - p)))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308

        z = t - (c0 + c1 * t + c2 * t ** 2) / (1 + d1 * t + d2 * t ** 2 + d3 * t ** 3)

        return z if p > 0.5 else -z


# Convenience functions
def run_sota_comparison(
    polaris_scores: List[float],
    baselines: Dict[str, float],
    alpha: float = 0.05,
) -> Dict[str, ComparisonResult]:
    """Run full SOTA comparison with multiple baselines."""
    analyzer = StatisticalAnalyzer(alpha=alpha)
    return analyzer.run_full_comparison(polaris_scores, baselines)


def calculate_confidence_interval(
    scores: List[float],
    confidence: float = 0.95,
) -> Tuple[float, float, float]:
    """Calculate bootstrap confidence interval."""
    analyzer = StatisticalAnalyzer()
    return analyzer.bootstrap_confidence_interval(scores, confidence)
