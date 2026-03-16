# POLARIS Benchmarks Module
# =========================
# Industry-standard benchmarks for evaluating deep research quality.
#
# Includes:
# - HLE (Humanity's Last Exam) - Expert-level academic questions
# - DeepSearchQA - Research synthesis evaluation
# - RAGAS - Retrieval-Augmented Generation Assessment
#
# SOTA Validation Framework (2026-02-05):
# - Strict auditor without gaming mechanisms
# - Strict metrics with real atomic decomposition
# - Statistical analysis for publication-grade claims
# - Report generator for comparison documentation

from .hle_benchmark import HLEBenchmarkRunner, HLEResult
from .hle_dataset import HLEDataset, HLEQuestion

# SOTA Validation Framework
from .auditor_strict import StrictAuditor, StrictAuditResult, StrictAuditSummary, run_strict_audit
from .metrics_strict import StrictMetrics, StrictMetricsCalculator, calculate_strict_metrics
from .stats_analysis import (
    StatisticalAnalyzer,
    StatisticalTestResult,
    ComparisonResult,
    run_sota_comparison,
    calculate_confidence_interval,
)
from .report_generator import (
    SOTAReportGenerator,
    SOTAComparisonReport,
    BenchmarkRun,
    generate_sota_report,
)

__all__ = [
    # HLE Benchmark
    "HLEBenchmarkRunner",
    "HLEResult",
    "HLEDataset",
    "HLEQuestion",
    # Strict Auditor
    "StrictAuditor",
    "StrictAuditResult",
    "StrictAuditSummary",
    "run_strict_audit",
    # Strict Metrics
    "StrictMetrics",
    "StrictMetricsCalculator",
    "calculate_strict_metrics",
    # Statistical Analysis
    "StatisticalAnalyzer",
    "StatisticalTestResult",
    "ComparisonResult",
    "run_sota_comparison",
    "calculate_confidence_interval",
    # Report Generator
    "SOTAReportGenerator",
    "SOTAComparisonReport",
    "BenchmarkRun",
    "generate_sota_report",
]
