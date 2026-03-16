"""POLARIS Quality Gates Module."""

from src.quality.gates import (
    QualityGate,
    QualityGateResult,
    CheckResult,
    measure_source_diversity,
    measure_hallucination_rate,
    measure_citation_accuracy,
    measure_content_coverage,
    measure_word_count,
    run_quality_gate,
)

from src.quality.output_quality_gate import (
    OutputQualityResult,
    QualityIssue,
    check_output_quality,
    repair_output_quality,
)

from src.quality.bias_detector import (
    BiasDetector,
    BiasConfig,
    BiasReport,
    BiasCategory,
    ViewpointType,
    BiasIndicator,
    SourceBiasProfile,
    ViewpointDistribution,
    analyze_source_bias,
    check_balance,
    get_balancing_suggestions,
    classify_source_bias,
)

__all__ = [
    # Quality gates
    "QualityGate",
    "QualityGateResult",
    "CheckResult",
    "measure_source_diversity",
    "measure_hallucination_rate",
    "measure_citation_accuracy",
    "measure_content_coverage",
    "measure_word_count",
    "run_quality_gate",
    # Output quality gate (FIX-138)
    "OutputQualityResult",
    "QualityIssue",
    "check_output_quality",
    "repair_output_quality",
    # Bias detection
    "BiasDetector",
    "BiasConfig",
    "BiasReport",
    "BiasCategory",
    "ViewpointType",
    "BiasIndicator",
    "SourceBiasProfile",
    "ViewpointDistribution",
    "analyze_source_bias",
    "check_balance",
    "get_balancing_suggestions",
    "classify_source_bias",
]
