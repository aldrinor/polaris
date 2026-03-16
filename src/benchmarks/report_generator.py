"""
POLARIS SOTA Validation Framework - Report Generator

Created: 2026-02-05
Purpose: Generate publication-grade SOTA comparison reports

This module generates comprehensive comparison reports that include:
1. Methodology documentation
2. Statistical analysis results
3. Metric breakdowns
4. Honest limitation acknowledgment
5. Reproducibility information
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkRun:
    """Results from a single benchmark run."""

    question_id: str
    """Unique identifier for the question."""

    question: str
    """The question text."""

    polaris_output: str
    """POLARIS generated output."""

    metrics: Dict[str, float]
    """Calculated metrics for this run."""

    execution_time: float
    """Time taken in seconds."""

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SOTAComparisonReport:
    """Complete SOTA comparison report."""

    title: str
    """Report title."""

    date: str
    """Report generation date."""

    summary: Dict[str, Any]
    """Executive summary."""

    methodology: Dict[str, Any]
    """Methodology details."""

    results: Dict[str, Any]
    """Detailed results."""

    statistical_analysis: Dict[str, Any]
    """Statistical analysis results."""

    limitations: List[str]
    """Acknowledged limitations."""

    reproducibility: Dict[str, Any]
    """Reproducibility information."""


class SOTAReportGenerator:
    """
    Generate publication-grade SOTA comparison reports.

    Reports include:
    - Methodology documentation
    - Per-metric results with CI
    - Statistical significance tests
    - Honest limitations
    - Reproducibility details
    """

    def __init__(self, output_dir: str = "docs"):
        """
        Initialize report generator.

        Args:
            output_dir: Directory for output reports.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        polaris_runs: List[BenchmarkRun],
        baselines: Dict[str, float],
        methodology: Dict[str, Any],
        title: str = "POLARIS vs SOTA Deep Research Systems",
    ) -> SOTAComparisonReport:
        """
        Generate a complete comparison report.

        Args:
            polaris_runs: List of benchmark run results.
            baselines: Dict mapping system name to published score.
            methodology: Methodology details.
            title: Report title.

        Returns:
            SOTAComparisonReport with all sections.
        """
        # Calculate aggregate metrics
        metrics = self._aggregate_metrics(polaris_runs)

        # Run statistical analysis
        from src.benchmarks.stats_analysis import StatisticalAnalyzer
        analyzer = StatisticalAnalyzer()

        polaris_scores = [r.metrics.get("accuracy", 0.0) for r in polaris_runs]
        stat_results = analyzer.run_full_comparison(polaris_scores, baselines)

        # Build report
        report = SOTAComparisonReport(
            title=title,
            date=datetime.now().strftime("%Y-%m-%d"),
            summary=self._build_summary(metrics, stat_results, len(polaris_runs)),
            methodology=methodology,
            results=self._build_results(metrics, polaris_runs),
            statistical_analysis=self._build_stat_section(stat_results),
            limitations=self._build_limitations(len(polaris_runs), methodology),
            reproducibility=self._build_reproducibility(methodology),
        )

        return report

    def write_markdown_report(
        self,
        report: SOTAComparisonReport,
        filename: str = "sota_comparison_report.md",
    ) -> Path:
        """
        Write report to markdown file.

        Args:
            report: The report to write.
            filename: Output filename.

        Returns:
            Path to written file.
        """
        output_path = self.output_dir / filename

        md = self._render_markdown(report)

        output_path.write_text(md, encoding="utf-8")
        logger.info(f"Report written to {output_path}")

        return output_path

    def _aggregate_metrics(self, runs: List[BenchmarkRun]) -> Dict[str, Dict[str, float]]:
        """Aggregate metrics across runs."""
        from src.benchmarks.stats_analysis import StatisticalAnalyzer
        analyzer = StatisticalAnalyzer()

        metrics = {}

        # Collect all metric names
        metric_names = set()
        for run in runs:
            metric_names.update(run.metrics.keys())

        # Calculate stats for each metric
        for metric in metric_names:
            values = [r.metrics.get(metric, 0.0) for r in runs]

            mean, lower, upper = analyzer.bootstrap_confidence_interval(values)

            metrics[metric] = {
                "mean": mean,
                "ci_lower": lower,
                "ci_upper": upper,
                "n": len(values),
            }

        return metrics

    def _build_summary(
        self,
        metrics: Dict[str, Dict[str, float]],
        stat_results: Dict[str, Any],
        n_samples: int,
    ) -> Dict[str, Any]:
        """Build executive summary."""
        # Determine overall SOTA status
        sota_claims = []
        for name, result in stat_results.items():
            if hasattr(result, 'is_sota') and result.is_sota:
                sota_claims.append(name)

        if sota_claims:
            overall = f"POLARIS demonstrates SOTA performance compared to: {', '.join(sota_claims)}"
            is_sota = True
        else:
            overall = "POLARIS does not demonstrate statistically significant SOTA performance"
            is_sota = False

        return {
            "is_sota": is_sota,
            "sota_vs": sota_claims,
            "overall_statement": overall,
            "sample_size": n_samples,
            "primary_metric": metrics.get("accuracy", metrics.get("faithfulness", {})),
            "confidence_level": 0.95,
        }

    def _build_results(
        self,
        metrics: Dict[str, Dict[str, float]],
        runs: List[BenchmarkRun],
    ) -> Dict[str, Any]:
        """Build detailed results section."""
        return {
            "aggregate_metrics": metrics,
            "per_question_summary": [
                {
                    "question_id": r.question_id,
                    "metrics": r.metrics,
                    "execution_time": r.execution_time,
                }
                for r in runs
            ],
            "execution_stats": {
                "total_questions": len(runs),
                "mean_execution_time": sum(r.execution_time for r in runs) / len(runs) if runs else 0,
                "total_execution_time": sum(r.execution_time for r in runs),
            },
        }

    def _build_stat_section(self, stat_results: Dict[str, Any]) -> Dict[str, Any]:
        """Build statistical analysis section."""
        comparisons = {}

        for name, result in stat_results.items():
            if hasattr(result, 'test_result'):
                tr = result.test_result
                comparisons[name] = {
                    "polaris_mean": result.polaris_mean,
                    "baseline_mean": result.baseline_mean,
                    "difference": result.difference,
                    "test": tr.test_name,
                    "p_value": tr.p_value,
                    "significant": tr.significant,
                    "effect_size": tr.effect_size,
                    "effect_interpretation": tr.effect_interpretation,
                    "is_sota": result.is_sota,
                    "interpretation": result.interpretation,
                }

        return {
            "comparisons": comparisons,
            "correction_method": "Bonferroni",
            "alpha": 0.05,
        }

    def _build_limitations(
        self,
        sample_size: int,
        methodology: Dict[str, Any],
    ) -> List[str]:
        """Build honest limitations section."""
        limitations = []

        # Sample size limitations
        if sample_size < 100:
            limitations.append(
                f"Sample size ({sample_size}) is below recommended minimum (100). "
                f"Results may not generalize."
            )
        if sample_size < 200:
            limitations.append(
                f"Sample size ({sample_size}) provides ~{10 if sample_size < 100 else 7}% margin of error. "
                f"Publication-grade confidence requires 500+ samples."
            )

        # Methodology limitations
        if not methodology.get("blind_evaluation", False):
            limitations.append(
                "Evaluation was not blind. Evaluator knew which system produced each output."
            )

        if methodology.get("evaluator_count", 1) < 2:
            limitations.append(
                "Single evaluator used. Inter-rater reliability could not be calculated."
            )

        if methodology.get("llm_decomposition", True):
            limitations.append(
                "Atomic decomposition used LLM, which may introduce model-dependent bias."
            )

        # Self-evaluation caveat
        limitations.append(
            "POLARIS was evaluated by its own metrics system. External validation recommended."
        )

        # Gaming mechanisms
        if methodology.get("honest_mode", False):
            limitations.append(
                "Honest evaluation mode was used, disabling gaming mechanisms. "
                "Results may differ from default configuration."
            )
        else:
            limitations.append(
                "Default evaluation mode was used. Some gaming mechanisms may inflate scores."
            )

        return limitations

    def _build_reproducibility(self, methodology: Dict[str, Any]) -> Dict[str, Any]:
        """Build reproducibility section."""
        return {
            "random_seed": methodology.get("seed", 42),
            "config_file": methodology.get("config_file", "config/evaluation_strict.env"),
            "command": methodology.get("command", "python -m src.benchmarks.hle_benchmark --honest-mode"),
            "environment": {
                "python_version": "3.10+",
                "key_dependencies": [
                    "transformers>=4.30.0",
                    "sentence-transformers>=2.2.0",
                    "torch>=2.0.0",
                ],
            },
            "data_sources": methodology.get("data_sources", ["HLE benchmark dataset"]),
        }

    def _render_markdown(self, report: SOTAComparisonReport) -> str:
        """Render report as markdown."""
        md = []

        # Title
        md.append(f"# {report.title}")
        md.append(f"\n**Date:** {report.date}")
        md.append("")

        # Summary
        md.append("## Executive Summary")
        md.append("")
        md.append(f"**SOTA Status:** {'YES' if report.summary['is_sota'] else 'NO'}")
        md.append("")
        md.append(report.summary['overall_statement'])
        md.append("")
        md.append(f"- Sample Size: {report.summary['sample_size']}")
        md.append(f"- Confidence Level: {report.summary['confidence_level']:.0%}")
        if report.summary['sota_vs']:
            md.append(f"- Beats: {', '.join(report.summary['sota_vs'])}")
        md.append("")

        # Methodology
        md.append("## Methodology")
        md.append("")
        for key, value in report.methodology.items():
            if not key.startswith("_"):
                md.append(f"- **{key.replace('_', ' ').title()}:** {value}")
        md.append("")

        # Results
        md.append("## Results")
        md.append("")
        md.append("### Aggregate Metrics")
        md.append("")
        md.append("| Metric | POLARIS | 95% CI |")
        md.append("|--------|---------|--------|")
        for metric, stats in report.results['aggregate_metrics'].items():
            mean = stats.get('mean', 0)
            lower = stats.get('ci_lower', 0)
            upper = stats.get('ci_upper', 0)
            md.append(f"| {metric} | {mean:.2%} | [{lower:.2%}, {upper:.2%}] |")
        md.append("")

        # Statistical Analysis
        md.append("## Statistical Analysis")
        md.append("")
        md.append("### Comparison to Baselines")
        md.append("")
        md.append("| System | POLARIS | Baseline | Diff | p-value | Effect | SOTA? |")
        md.append("|--------|---------|----------|------|---------|--------|-------|")
        for name, comp in report.statistical_analysis['comparisons'].items():
            md.append(
                f"| {name} | {comp['polaris_mean']:.2%} | {comp['baseline_mean']:.2%} | "
                f"{comp['difference']:+.2%} | {comp['p_value']:.4f} | "
                f"{comp['effect_interpretation']} | {'YES' if comp['is_sota'] else 'NO'} |"
            )
        md.append("")

        # Limitations
        md.append("## Limitations")
        md.append("")
        for i, limitation in enumerate(report.limitations, 1):
            md.append(f"{i}. {limitation}")
        md.append("")

        # Reproducibility
        md.append("## Reproducibility")
        md.append("")
        md.append("```bash")
        md.append(f"# Random seed: {report.reproducibility['random_seed']}")
        md.append(f"# Config: {report.reproducibility['config_file']}")
        md.append(report.reproducibility['command'])
        md.append("```")
        md.append("")

        # Footer
        md.append("---")
        md.append("")
        md.append("*Generated by POLARIS SOTA Validation Framework*")

        return "\n".join(md)


# Convenience function
def generate_sota_report(
    polaris_runs: List[BenchmarkRun],
    baselines: Dict[str, float],
    methodology: Dict[str, Any],
    output_file: str = "docs/sota_comparison_report.md",
) -> Path:
    """
    Generate and write a SOTA comparison report.

    Args:
        polaris_runs: Benchmark run results.
        baselines: Baseline scores to compare against.
        methodology: Methodology details.
        output_file: Output file path.

    Returns:
        Path to written report.
    """
    generator = SOTAReportGenerator()
    report = generator.generate_report(polaris_runs, baselines, methodology)
    return generator.write_markdown_report(report, Path(output_file).name)
