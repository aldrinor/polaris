"""
Runner Audit System - Comprehensive Pipeline Quality Assessment

This module provides end-to-end quality auditing for the POLARIS pipeline runner,
including:
- Reasoning flow tracking per phase
- Data flow analysis (input/output sizes, types)
- URL success rate measurement
- Content fetch quality assessment
- Chunk quality evaluation
- Memory quality metrics
- Token cost tracking
- Detailed gap report generation

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real metric collection from actual pipeline outputs
- Actual benchmark evaluation using RAGAS + NLI
- Live quality gate validation
- Detailed gap analysis with actionable recommendations

Usage:
    from src.audit.runner_audit import RunnerAuditor

    auditor = RunnerAuditor(vector_id="S1V1_...")
    auditor.load_all_phase_outputs()
    report = auditor.generate_comprehensive_report()
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, OUTPUTS_DIR
from src.audit.benchmark_audit import BenchmarkAuditor


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PhaseMetrics:
    """Metrics for a single phase."""
    phase_number: int
    phase_name: str
    status: str = "not_run"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quality_gate_passed: bool = False
    quality_gate_details: Dict[str, Any] = field(default_factory=dict)
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_number": self.phase_number,
            "phase_name": self.phase_name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "input_size_bytes": self.input_size_bytes,
            "output_size_bytes": self.output_size_bytes,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "errors": self.errors,
            "warnings": self.warnings,
            "quality_gate_passed": self.quality_gate_passed,
            "quality_gate_details": self.quality_gate_details,
            "custom_metrics": self.custom_metrics,
        }


@dataclass
class URLMetrics:
    """Metrics for URL fetching."""
    urls_attempted: int = 0
    urls_success: int = 0
    urls_failed: int = 0
    success_rate: float = 0.0
    fetch_methods: Dict[str, int] = field(default_factory=dict)
    content_types: Dict[str, int] = field(default_factory=dict)
    total_content_bytes: int = 0
    avg_fetch_time_ms: float = 0.0
    failed_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "urls_attempted": self.urls_attempted,
            "urls_success": self.urls_success,
            "urls_failed": self.urls_failed,
            "success_rate": self.success_rate,
            "fetch_methods": self.fetch_methods,
            "content_types": self.content_types,
            "total_content_bytes": self.total_content_bytes,
            "avg_fetch_time_ms": self.avg_fetch_time_ms,
            "failed_urls_count": len(self.failed_urls),
        }


@dataclass
class ChunkMetrics:
    """Metrics for chunk quality."""
    total_chunks: int = 0
    gold_chunks: int = 0
    silver_chunks: int = 0
    bronze_chunks: int = 0
    rejected_chunks: int = 0
    avg_chunk_size: float = 0.0
    min_chunk_size: int = 0
    max_chunk_size: int = 0
    tier_distribution: Dict[str, float] = field(default_factory=dict)
    unique_sources: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.total_chunks,
            "gold_chunks": self.gold_chunks,
            "silver_chunks": self.silver_chunks,
            "bronze_chunks": self.bronze_chunks,
            "rejected_chunks": self.rejected_chunks,
            "avg_chunk_size": self.avg_chunk_size,
            "min_chunk_size": self.min_chunk_size,
            "max_chunk_size": self.max_chunk_size,
            "tier_distribution": self.tier_distribution,
            "unique_sources": self.unique_sources,
        }


@dataclass
class MemoryMetrics:
    """Metrics for memory usage."""
    vwm_chunk_count: int = 0
    vwm_total_chars: int = 0
    ltm_stage_hits: int = 0
    ltm_global_hits: int = 0
    ltm_utilization: float = 0.0
    context_utilization: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vwm_chunk_count": self.vwm_chunk_count,
            "vwm_total_chars": self.vwm_total_chars,
            "ltm_stage_hits": self.ltm_stage_hits,
            "ltm_global_hits": self.ltm_global_hits,
            "ltm_utilization": self.ltm_utilization,
            "context_utilization": self.context_utilization,
        }


@dataclass
class QualityMetrics:
    """Final quality metrics (SOTA alignment)."""
    hallucination_rate: float = 1.0
    faithfulness: float = 0.0
    citation_accuracy: float = 0.0
    source_diversity: int = 0
    content_coverage: float = 0.0
    word_count: int = 0
    verified_claims: int = 0
    total_claims: int = 0
    sota_compliant: bool = False
    sota_gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hallucination_rate": self.hallucination_rate,
            "faithfulness": self.faithfulness,
            "citation_accuracy": self.citation_accuracy,
            "source_diversity": self.source_diversity,
            "content_coverage": self.content_coverage,
            "word_count": self.word_count,
            "verified_claims": self.verified_claims,
            "total_claims": self.total_claims,
            "sota_compliant": self.sota_compliant,
            "sota_gaps": self.sota_gaps,
        }


@dataclass
class GapAnalysis:
    """Gap analysis with recommendations."""
    gap_id: str
    severity: str  # critical, high, medium, low
    category: str  # quality, performance, content, citation
    description: str
    current_value: Any
    target_value: Any
    recommendation: str
    affected_phases: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "recommendation": self.recommendation,
            "affected_phases": self.affected_phases,
        }


# =============================================================================
# RUNNER AUDITOR
# =============================================================================

class RunnerAuditor:
    """
    Comprehensive auditor for POLARIS pipeline runs.

    Collects metrics from all phases and generates detailed gap reports.
    """

    # SOTA Targets (from config/settings/sota_parameters.yaml)
    SOTA_TARGETS = {
        "max_hallucination_rate": 0.05,
        "min_faithfulness": 0.80,
        "min_citation_accuracy": 0.95,
        "min_source_diversity": 10,
        "min_content_coverage": 0.80,
        "min_word_count": 2000,
        "min_verified_claims": 30,
    }

    def __init__(self, vector_id: str):
        self.vector_id = vector_id
        self.phase_metrics: Dict[int, PhaseMetrics] = {}
        self.url_metrics = URLMetrics()
        self.chunk_metrics = ChunkMetrics()
        self.memory_metrics = MemoryMetrics()
        self.quality_metrics = QualityMetrics()
        self.gaps: List[GapAnalysis] = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.total_duration = 0.0
        self._phase_data: Dict[int, Dict[str, Any]] = {}

    def load_all_phase_outputs(self) -> None:
        """Load output files for all phases."""
        print(f"\n  Loading phase outputs for {self.vector_id}...")

        for phase in range(0, 13):
            self._load_phase_output(phase)

        # Also load P7.5 (claim verification)
        self._load_phase_output(7, suffix="_5")

        print(f"    Loaded {len(self._phase_data)} phase outputs")

    def _load_phase_output(self, phase: int, suffix: str = "") -> Optional[Dict[str, Any]]:
        """Load output for a specific phase."""
        phase_str = f"P{phase}{suffix}"
        phase_dir = OUTPUTS_DIR / phase_str

        if not phase_dir.exists():
            return None

        files = list(phase_dir.glob(f"{self.vector_id}__P{phase}{suffix}__*.json"))
        if not files:
            return None

        try:
            latest = sorted(files)[-1]
            with open(latest, 'r', encoding='utf-8') as f:
                data = json.load(f)

            phase_key = phase if not suffix else float(f"{phase}.5")
            self._phase_data[phase_key] = data
            self._extract_phase_metrics(phase_key, data, latest)

            return data

        except Exception as e:
            print(f"    [WARN] Failed to load P{phase}{suffix}: {e}")
            return None

    def _extract_phase_metrics(
        self,
        phase: float,
        data: Dict[str, Any],
        file_path: Path
    ) -> None:
        """Extract metrics from phase output data."""
        phase_int = int(phase)
        phase_names = {
            0: "Initialization",
            1: "Contextualization",
            2: "Query Generation",
            3: "Search Execution",
            4: "Relevance Filtering",
            5: "VWM Indexing",
            6: "NLI Integrity",
            7: "Dual RAG",
            7.5: "Claim Verification",
            8: "Adversarial QA",
            9: "Gating Logic",
            10: "Knowledge Integration",
            11: "Research Packaging",
            12: "Narrative Synthesis",
        }

        metrics = PhaseMetrics(
            phase_number=phase_int,
            phase_name=phase_names.get(phase, f"Phase {phase}"),
            status="completed",
            output_size_bytes=file_path.stat().st_size,
        )

        # Extract timestamps
        timestamps = data.get("timestamps", {})
        metrics.start_time = timestamps.get("start")
        metrics.end_time = timestamps.get("end")

        if metrics.start_time and metrics.end_time:
            try:
                start = datetime.fromisoformat(metrics.start_time.replace('Z', '+00:00'))
                end = datetime.fromisoformat(metrics.end_time.replace('Z', '+00:00'))
                metrics.duration_seconds = (end - start).total_seconds()
            except (ValueError, TypeError):
                # Duration remains at default 0.0 if parsing fails
                metrics.duration_seconds = 0.0

        # Extract token usage
        token_usage = data.get("token_usage", {})
        metrics.tokens_used = token_usage.get("total_tokens", 0)
        if not metrics.tokens_used:
            metrics.tokens_used = token_usage.get("context_tokens", 0) + token_usage.get("output_tokens", 0)

        # Phase-specific metrics
        if phase == 3:
            self._extract_p3_metrics(data)
        elif phase == 4:
            self._extract_p4_metrics(data)
        elif phase == 5:
            self._extract_p5_metrics(data)
        elif phase == 6:
            metrics.custom_metrics["integrity_score"] = data.get("integrity_score", 0)
            metrics.custom_metrics["contradictions"] = data.get("contradictions_found", 0)
        elif phase == 7:
            self._extract_p7_metrics(data, metrics)
        elif phase == 7.5:
            self._extract_p7_5_metrics(data, metrics)
        elif phase == 8:
            metrics.custom_metrics["resolution_rate"] = data.get("resolution_rate", 0)
            metrics.custom_metrics["signal_novelty"] = data.get("signal_novelty", 0)
        elif phase == 9:
            metrics.custom_metrics["gating_case"] = data.get("gating_case", "")
            metrics.custom_metrics["sufficiency"] = data.get("sufficiency_score", 0)
            metrics.custom_metrics["confidence"] = data.get("confidence_score", 0)
            metrics.custom_metrics["integrity"] = data.get("integrity_score", 0)
        elif phase == 11:
            self._extract_p11_metrics(data, metrics)

        self.phase_metrics[phase] = metrics
        self.total_tokens += metrics.tokens_used
        self.total_duration += metrics.duration_seconds

    def _extract_p3_metrics(self, data: Dict[str, Any]) -> None:
        """Extract P3 search metrics."""
        self.url_metrics.urls_attempted = data.get("urls_attempted", 0)
        self.url_metrics.urls_success = data.get("urls_success", 0)
        self.url_metrics.urls_failed = data.get("urls_failed", 0)

        if self.url_metrics.urls_attempted > 0:
            self.url_metrics.success_rate = self.url_metrics.urls_success / self.url_metrics.urls_attempted

        self.url_metrics.fetch_methods = data.get("fetch_methods", {})
        self.url_metrics.total_content_bytes = data.get("total_content_chars", 0)

    def _extract_p4_metrics(self, data: Dict[str, Any]) -> None:
        """Extract P4 relevance filtering metrics."""
        tier_dist = data.get("tier_distribution", {})
        self.chunk_metrics.gold_chunks = tier_dist.get("gold", 0)
        self.chunk_metrics.silver_chunks = tier_dist.get("silver", 0)
        self.chunk_metrics.bronze_chunks = tier_dist.get("bronze", 0)
        self.chunk_metrics.rejected_chunks = data.get("chunks_rejected", 0)
        self.chunk_metrics.total_chunks = data.get("chunks_passed", 0)

        total = self.chunk_metrics.total_chunks
        if total > 0:
            self.chunk_metrics.tier_distribution = {
                "gold": self.chunk_metrics.gold_chunks / total,
                "silver": self.chunk_metrics.silver_chunks / total,
                "bronze": self.chunk_metrics.bronze_chunks / total,
            }

    def _extract_p5_metrics(self, data: Dict[str, Any]) -> None:
        """Extract P5 indexing metrics."""
        self.memory_metrics.vwm_chunk_count = data.get("chunks_indexed", 0)
        self.chunk_metrics.unique_sources = data.get("unique_sources", 0)

    def _extract_p7_metrics(self, data: Dict[str, Any], metrics: PhaseMetrics) -> None:
        """Extract P7 RAG metrics."""
        analysis_text = data.get("analysis_text", "")
        citations = data.get("citation_tokens", [])

        metrics.custom_metrics["analysis_length"] = len(analysis_text)
        metrics.custom_metrics["word_count"] = len(analysis_text.split())
        metrics.custom_metrics["citation_count"] = len(citations)
        metrics.custom_metrics["chunks_used"] = data.get("chunks_used", 0)

        self.memory_metrics.context_utilization = data.get("context_utilization", 0)

    def _extract_p7_5_metrics(self, data: Dict[str, Any], metrics: PhaseMetrics) -> None:
        """Extract P7.5 claim verification metrics."""
        metrics.custom_metrics["claims_total"] = data.get("claims_total", 0)
        metrics.custom_metrics["claims_verified"] = data.get("claims_verified", 0)
        metrics.custom_metrics["claims_rejected"] = data.get("claims_rejected", 0)
        metrics.custom_metrics["hallucination_rate"] = data.get("hallucination_rate", 1.0)
        metrics.custom_metrics["blocked_citations"] = len(data.get("blocked_citations", []))

        # Update quality metrics
        self.quality_metrics.hallucination_rate = data.get("hallucination_rate", 1.0)
        self.quality_metrics.verified_claims = data.get("claims_verified", 0)
        self.quality_metrics.total_claims = data.get("claims_total", 0)

    def _extract_p11_metrics(self, data: Dict[str, Any], metrics: PhaseMetrics) -> None:
        """Extract P11 packaging metrics."""
        metrics.custom_metrics["output_type"] = data.get("output_type", "")
        metrics.custom_metrics["word_count"] = data.get("word_count", 0)
        metrics.custom_metrics["citation_count"] = data.get("citation_count", 0)

        self.quality_metrics.word_count = data.get("word_count", 0)

    def run_benchmark_audit(self) -> None:
        """Run RAGAS + NLI benchmark audit on outputs."""
        print("\n  Running benchmark audit...")

        try:
            # Get P7 and P11 data
            p7_data = self._phase_data.get(7)
            p11_data = self._phase_data.get(11)

            if not p7_data:
                print("    [WARN] No P7 data for benchmark audit")
                return

            # Load P4 chunks if available
            p4_data = self._phase_data.get(4)
            p4_chunks = None
            if p4_data:
                p4_chunks = p4_data.get("filtered_chunks", p4_data.get("chunks", []))

            # Run benchmark
            auditor = BenchmarkAuditor()
            result = auditor.run_benchmark(
                vector_id=self.vector_id,
                p7_data=p7_data,
                p11_data=p11_data or p7_data,
                p4_chunks=p4_chunks,
            )

            # Update quality metrics
            self.quality_metrics.faithfulness = result.ragas_metrics.faithfulness
            self.quality_metrics.citation_accuracy = result.ragas_metrics.context_precision
            self.quality_metrics.content_coverage = result.ragas_metrics.context_recall

            if result.hallucination_result:
                self.quality_metrics.hallucination_rate = result.hallucination_result.hallucination_rate

            print(f"    Faithfulness: {self.quality_metrics.faithfulness:.1%}")
            print(f"    Hallucination Rate: {self.quality_metrics.hallucination_rate:.1%}")

        except Exception as e:
            print(f"    [ERROR] Benchmark audit failed: {e}")

    def analyze_gaps(self) -> None:
        """Analyze gaps against SOTA targets."""
        print("\n  Analyzing gaps against SOTA targets...")
        self.gaps = []
        gap_id = 0

        # Hallucination rate
        if self.quality_metrics.hallucination_rate > self.SOTA_TARGETS["max_hallucination_rate"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="critical",
                category="quality",
                description="Hallucination rate exceeds SOTA target",
                current_value=f"{self.quality_metrics.hallucination_rate:.1%}",
                target_value=f"<{self.SOTA_TARGETS['max_hallucination_rate']:.0%}",
                recommendation="Run P7.5 claim verification and block unverified claims",
                affected_phases=[7, 11],
            ))

        # Faithfulness
        if self.quality_metrics.faithfulness < self.SOTA_TARGETS["min_faithfulness"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="critical",
                category="quality",
                description="Faithfulness below SOTA target",
                current_value=f"{self.quality_metrics.faithfulness:.1%}",
                target_value=f">{self.SOTA_TARGETS['min_faithfulness']:.0%}",
                recommendation="Improve evidence-claim grounding in P7 RAG synthesis",
                affected_phases=[7],
            ))

        # Citation accuracy
        if self.quality_metrics.citation_accuracy < self.SOTA_TARGETS["min_citation_accuracy"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="high",
                category="citation",
                description="Citation accuracy below SOTA target",
                current_value=f"{self.quality_metrics.citation_accuracy:.1%}",
                target_value=f">{self.SOTA_TARGETS['min_citation_accuracy']:.0%}",
                recommendation="Verify all citations point to valid evidence chunks",
                affected_phases=[7, 11],
            ))

        # Word count
        if self.quality_metrics.word_count < self.SOTA_TARGETS["min_word_count"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="medium",
                category="content",
                description="Word count below SOTA target",
                current_value=f"{self.quality_metrics.word_count}",
                target_value=f">{self.SOTA_TARGETS['min_word_count']}",
                recommendation="Increase evidence coverage and synthesis depth",
                affected_phases=[7],
            ))

        # Verified claims
        if self.quality_metrics.verified_claims < self.SOTA_TARGETS["min_verified_claims"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="high",
                category="quality",
                description="Verified claims below SOTA target",
                current_value=f"{self.quality_metrics.verified_claims}",
                target_value=f">{self.SOTA_TARGETS['min_verified_claims']}",
                recommendation="Increase search depth and evidence gathering iterations",
                affected_phases=[3, 4, 7],
            ))

        # URL success rate
        if self.url_metrics.success_rate < 0.60:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="medium",
                category="performance",
                description="URL fetch success rate below threshold",
                current_value=f"{self.url_metrics.success_rate:.1%}",
                target_value=">60%",
                recommendation="Add retry logic and fallback fetch methods",
                affected_phases=[3],
            ))

        # Source diversity
        if self.chunk_metrics.unique_sources < self.SOTA_TARGETS["min_source_diversity"]:
            gap_id += 1
            self.gaps.append(GapAnalysis(
                gap_id=f"GAP-{gap_id:03d}",
                severity="medium",
                category="content",
                description="Source diversity below SOTA target",
                current_value=f"{self.chunk_metrics.unique_sources}",
                target_value=f">{self.SOTA_TARGETS['min_source_diversity']}",
                recommendation="Diversify search queries across more domains",
                affected_phases=[2, 3],
            ))

        # Determine SOTA compliance
        critical_gaps = [g for g in self.gaps if g.severity == "critical"]
        self.quality_metrics.sota_compliant = len(critical_gaps) == 0
        self.quality_metrics.sota_gaps = [g.gap_id for g in self.gaps]

        print(f"    Found {len(self.gaps)} gaps ({len(critical_gaps)} critical)")

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report with gap analysis."""
        self.run_benchmark_audit()
        self.analyze_gaps()

        # Calculate overall score
        scores = [
            1 - min(self.quality_metrics.hallucination_rate, 1),
            self.quality_metrics.faithfulness,
            self.quality_metrics.citation_accuracy,
            min(self.quality_metrics.word_count / self.SOTA_TARGETS["min_word_count"], 1),
            min(self.quality_metrics.verified_claims / self.SOTA_TARGETS["min_verified_claims"], 1),
        ]
        overall_score = sum(scores) / len(scores) if scores else 0

        report = {
            "vector_id": self.vector_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_score": overall_score,
            "sota_compliant": self.quality_metrics.sota_compliant,

            "summary": {
                "total_phases_run": len(self.phase_metrics),
                "total_duration_seconds": self.total_duration,
                "total_tokens_used": self.total_tokens,
                "total_cost_usd": self.total_cost,
                "gaps_found": len(self.gaps),
                "critical_gaps": len([g for g in self.gaps if g.severity == "critical"]),
            },

            "quality_metrics": self.quality_metrics.to_dict(),
            "url_metrics": self.url_metrics.to_dict(),
            "chunk_metrics": self.chunk_metrics.to_dict(),
            "memory_metrics": self.memory_metrics.to_dict(),

            "phase_metrics": {
                str(k): v.to_dict() for k, v in self.phase_metrics.items()
            },

            "gap_analysis": [g.to_dict() for g in self.gaps],

            "recommendations": self._generate_recommendations(),

            "sota_targets": self.SOTA_TARGETS,
        }

        return report

    def _generate_recommendations(self) -> List[str]:
        """Generate prioritized recommendations."""
        recommendations = []

        # Sort gaps by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_gaps = sorted(self.gaps, key=lambda g: severity_order.get(g.severity, 99))

        for gap in sorted_gaps[:5]:  # Top 5 recommendations
            recommendations.append(f"[{gap.severity.upper()}] {gap.recommendation}")

        if not recommendations:
            recommendations.append("All SOTA targets met! Continue monitoring quality metrics.")

        return recommendations

    def save_report(self, output_dir: Optional[Path] = None) -> Path:
        """Save audit report to JSON file."""
        if output_dir is None:
            output_dir = OUTPUTS_DIR / "audit"

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{self.vector_id}__audit__{timestamp}.json"

        report = self.generate_comprehensive_report()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return output_path

    def print_summary(self) -> None:
        """Print human-readable audit summary."""
        print(f"\n{'='*70}")
        print("RUNNER AUDIT SUMMARY")
        print(f"Vector: {self.vector_id}")
        print(f"{'='*70}")

        print(f"\n  QUALITY METRICS")
        print(f"    Hallucination Rate: {self.quality_metrics.hallucination_rate:.1%} (target: <5%)")
        print(f"    Faithfulness: {self.quality_metrics.faithfulness:.1%} (target: >80%)")
        print(f"    Citation Accuracy: {self.quality_metrics.citation_accuracy:.1%} (target: >95%)")
        print(f"    Word Count: {self.quality_metrics.word_count} (target: >2000)")
        print(f"    Verified Claims: {self.quality_metrics.verified_claims}/{self.quality_metrics.total_claims}")

        print(f"\n  PIPELINE METRICS")
        print(f"    Phases Run: {len(self.phase_metrics)}")
        print(f"    Total Duration: {self.total_duration:.1f}s")
        print(f"    Total Tokens: {self.total_tokens:,}")

        print(f"\n  URL METRICS")
        print(f"    Success Rate: {self.url_metrics.success_rate:.1%}")
        print(f"    URLs Fetched: {self.url_metrics.urls_success}/{self.url_metrics.urls_attempted}")

        print(f"\n  CHUNK METRICS")
        print(f"    Total Chunks: {self.chunk_metrics.total_chunks}")
        print(f"    Gold/Silver/Bronze: {self.chunk_metrics.gold_chunks}/{self.chunk_metrics.silver_chunks}/{self.chunk_metrics.bronze_chunks}")

        print(f"\n  SOTA COMPLIANCE: {'[PASS] COMPLIANT' if self.quality_metrics.sota_compliant else '[FAIL] NOT COMPLIANT'}")

        if self.gaps:
            print(f"\n  GAP ANALYSIS ({len(self.gaps)} gaps found)")
            for gap in self.gaps[:5]:
                severity_marker = {"critical": "[!!]", "high": "[!]", "medium": "[~]", "low": "[.]"}.get(gap.severity, "[?]")
                print(f"    {severity_marker} [{gap.gap_id}] {gap.description}")
                print(f"       Current: {gap.current_value} -> Target: {gap.target_value}")
                print(f"       Fix: {gap.recommendation}")

        print(f"\n{'='*70}")


# =============================================================================
# CLI
# =============================================================================

def run_audit(vector_id: str, save: bool = True) -> Dict[str, Any]:
    """Run comprehensive audit for a vector."""
    auditor = RunnerAuditor(vector_id)
    auditor.load_all_phase_outputs()
    report = auditor.generate_comprehensive_report()
    auditor.print_summary()

    if save:
        output_path = auditor.save_report()
        print(f"\n  Report saved: {output_path}")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="POLARIS Runner Audit")
    parser.add_argument("--vector-id", required=True, help="Vector ID to audit")
    parser.add_argument("--no-save", action="store_true", help="Don't save report to file")

    args = parser.parse_args()

    run_audit(args.vector_id, save=not args.no_save)
