#!/usr/bin/env python3
"""
POLARIS Audit Collector - Complete Pipeline Quality Assurance
==============================================================
Comprehensive audit system capturing EVERY detail during pipeline runs.

Covers ALL phases (P0-P13):
- P0: Vector parsing, constraint extraction
- P1: Constraint decomposition
- P2: Query generation with diversity
- P3: Search execution per engine/query/result
- P4: URL fetching and chunk creation
- P5: Memory registration (VWM/LTM)
- P6: NLI integrity checking
- P7: RAG synthesis with retrieval tracking
- P8: Claim verification
- P9: Adversarial QA
- P10: Gating decisions
- P11: Knowledge integration / Gap analysis
- P12: Citation resolution / Research packaging
- P13: Narrative synthesis / Final output quality

Plus cross-cutting concerns:
- Token costs per call/phase/vector
- Memory usage (VWM/LTM/cache)
- Timing and bottleneck identification
- Error tracking with stack traces
- Data lineage (chunk→citation flow)
"""

import json
import sys
import os
import hashlib
import traceback
import psutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, OUTPUTS_DIR

# Import benchmark auditor for RAGAS evaluation
from src.audit.benchmark_audit import (
    BenchmarkAuditor,
    BenchmarkResult,
    RAGASMetrics,
    ClaimVerification,
    HallucinationResult,
)


# =============================================================================
# DATA CLASSES FOR ALL AUDIT RECORDS
# =============================================================================

# -----------------------------------------------------------------------------
# P0: Vector Parsing / Constraint Extraction
# -----------------------------------------------------------------------------

@dataclass
class ConstraintRecord:
    """Record of a single constraint extracted from vector definition."""
    constraint_id: str
    constraint_type: str  # hard, soft, context
    constraint_text: str
    source_field: str  # which field it came from
    extraction_method: str  # regex, llm, manual
    confidence: float
    parsed_values: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VectorParseRecord:
    """Record of vector parsing in P0."""
    vector_id: str
    timestamp: str
    raw_input_size: int
    constraints_extracted: int
    hard_constraints: int
    soft_constraints: int
    context_constraints: int
    parse_errors: List[str] = field(default_factory=list)
    constraints: List[ConstraintRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["constraints"] = [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.constraints]
        return d


# -----------------------------------------------------------------------------
# P1: Constraint Decomposition
# -----------------------------------------------------------------------------

@dataclass
class DecompositionRecord:
    """Record of constraint decomposition in P1."""
    original_constraint_id: str
    original_text: str
    decomposed_constraints: List[Dict[str, Any]]  # {id, type, text, priority}
    decomposition_method: str  # llm, rule_based
    llm_reasoning: Optional[str]
    decomposition_count: int

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# P2: Query Generation
# -----------------------------------------------------------------------------

@dataclass
class QueryRecord:
    """Record of a single generated query."""
    query_id: str
    query_text: str
    query_type: str  # primary, follow_up, gap_fill
    target_constraint_ids: List[str]
    generation_method: str  # llm, template
    diversity_score: float  # semantic diversity from other queries
    expected_engines: List[str]  # google, pubmed, semantic_scholar
    llm_reasoning: Optional[str]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class QueryGenerationRecord:
    """Record of P2 query generation phase."""
    timestamp: str
    total_queries: int
    queries_by_type: Dict[str, int]
    avg_diversity_score: float
    constraint_coverage: float  # % of constraints with queries
    queries: List[QueryRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["queries"] = [q.to_dict() if hasattr(q, 'to_dict') else q for q in self.queries]
        return d


# -----------------------------------------------------------------------------
# P3: Search Execution
# -----------------------------------------------------------------------------

@dataclass
class SearchResultRecord:
    """Record of a single search result."""
    result_id: str
    query_id: str
    engine: str  # google, pubmed, semantic_scholar
    rank: int
    url: str
    title: str
    snippet: str
    relevance_score: float  # estimated by engine or computed
    domain: str
    is_academic: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SearchExecutionRecord:
    """Record of search execution for a single query."""
    query_id: str
    query_text: str
    timestamp: str
    engines_used: List[str]
    results_per_engine: Dict[str, int]
    total_results: int
    unique_urls: int
    duplicate_urls: int
    avg_relevance: float
    elapsed_ms: float
    errors: List[Dict[str, str]] = field(default_factory=list)
    results: List[SearchResultRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["results"] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.results]
        return d


# -----------------------------------------------------------------------------
# P4: URL Fetching and Chunk Creation (existing, enhanced)
# -----------------------------------------------------------------------------

@dataclass
class URLFetchRecord:
    """Record of a single URL fetch attempt."""
    url: str
    domain: str
    timestamp: str
    attempt_number: int
    method: str  # requests, jina, pubmed_api, pdf_extract
    status_code: Optional[int]
    success: bool
    error_type: Optional[str]  # timeout, dns, 403, 404
    error_detail: Optional[str]
    error_traceback: Optional[str]  # Full stack trace
    raw_content_length: int
    extracted_text_length: int
    extraction_method: str  # trafilatura, pdfminer, jina
    content_type: str
    is_garbage: bool
    garbage_reason: Optional[str]
    chunks_created: int
    elapsed_ms: float
    retry_count: int = 0
    fallback_methods_tried: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ChunkRecord:
    """Record of a single chunk."""
    chunk_id: str
    source_url: str
    source_domain: str
    source_title: str
    fetch_method: str
    text_preview: str  # First 500 chars
    text_full: str  # Full text for inspection
    text_hash: str  # MD5 for deduplication
    char_count: int
    word_count: int
    relevance_score: float
    hard_score: float
    soft_score: float
    domain_adjustment: float
    tier: str  # gold, silver, bronze, rejected
    is_garbage: bool
    garbage_reason: Optional[str]
    registered_to_vwm: bool
    memory_tier: str = ""  # vwm, ltm_stage, ltm_global
    embedding_id: Optional[str] = None
    used_in_citations: List[str] = field(default_factory=list)
    lineage: Dict[str, Any] = field(default_factory=dict)  # Full provenance

    def to_dict(self) -> Dict:
        d = asdict(self)
        if len(d["text_full"]) > 2000:
            d["text_full"] = d["text_full"][:2000] + "..."
        return d


# -----------------------------------------------------------------------------
# P5: Memory Registration
# -----------------------------------------------------------------------------

@dataclass
class MemoryOperationRecord:
    """Record of a memory operation (VWM/LTM)."""
    operation_id: str
    timestamp: str
    operation_type: str  # register, retrieve, promote, evict
    memory_tier: str  # vwm, ltm_stage, ltm_global
    chunk_id: str
    embedding_model: str
    embedding_dimensions: int
    similarity_score: Optional[float]  # For retrieval
    elapsed_ms: float
    success: bool
    error: Optional[str]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MemoryStateRecord:
    """Record of memory state at a point in time."""
    timestamp: str
    vwm_chunk_count: int
    vwm_total_chars: int
    vwm_capacity_used: float  # percentage
    ltm_stage_chunk_count: int
    ltm_global_chunk_count: int
    ltm_total_embeddings: int
    cache_hit_rate: float
    cache_size_mb: float
    memory_rss_mb: float  # Process memory
    memory_vms_mb: float

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# P6: NLI Integrity Check
# -----------------------------------------------------------------------------

@dataclass
class NLICheckRecord:
    """Record of NLI check between chunk pair."""
    check_id: str
    chunk_a_id: str
    chunk_b_id: str
    chunk_a_preview: str
    chunk_b_preview: str
    entailment_score: float
    contradiction_score: float
    neutral_score: float
    verdict: str  # consistent, contradictory, neutral
    model_used: str
    elapsed_ms: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class IntegrityCheckRecord:
    """Record of P6 integrity check phase."""
    timestamp: str
    total_pairs_checked: int
    contradictions_found: int
    consistency_score: float
    chunks_flagged: List[str]
    nli_checks: List[NLICheckRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["nli_checks"] = [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.nli_checks]
        return d


# -----------------------------------------------------------------------------
# P7: RAG Synthesis
# -----------------------------------------------------------------------------

@dataclass
class RetrievalRecord:
    """Record of a single retrieval from memory."""
    retrieval_id: str
    query_text: str
    memory_tier: str
    chunks_retrieved: int
    top_chunk_ids: List[str]
    top_scores: List[float]
    elapsed_ms: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GenerationRecord:
    """Record of a single generation in RAG."""
    generation_id: str
    timestamp: str
    prompt_type: str  # synthesis, refinement, expansion
    context_chunks: List[str]  # chunk IDs used
    context_char_count: int
    model: str
    input_tokens: int
    output_tokens: int
    output_char_count: int
    citations_generated: int
    elapsed_ms: float
    output_preview: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RAGRecord:
    """Record of P7 RAG synthesis."""
    timestamp: str
    total_retrievals: int
    total_generations: int
    unique_chunks_used: int
    total_citations: int
    analysis_word_count: int
    context_utilization: float
    retrievals: List[RetrievalRecord] = field(default_factory=list)
    generations: List[GenerationRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["retrievals"] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.retrievals]
        d["generations"] = [g.to_dict() if hasattr(g, 'to_dict') else g for g in self.generations]
        return d


# -----------------------------------------------------------------------------
# P8: Claim Verification
# -----------------------------------------------------------------------------

@dataclass
class ClaimRecord:
    """Record of a single claim verification."""
    claim_id: str
    claim_text: str
    claim_text_cleaned: str
    source_section: str
    cited_chunk_ids: List[str]
    verification_attempts: List[Dict]
    best_evidence_chunk_id: Optional[str]
    best_evidence_text: Optional[str]
    best_entailment_score: float
    verdict: str  # supported, unsupported, contradiction
    was_blocked: bool
    block_reason: Optional[str]
    lineage: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# P9: Adversarial QA
# -----------------------------------------------------------------------------

@dataclass
class QARecord:
    """Record of a single adversarial QA exchange."""
    qa_id: str
    question_type: str  # factual, counterfactual, edge_case
    question_text: str
    target_claim_ids: List[str]
    answer_text: str
    answer_sources: List[str]  # chunk IDs used
    confidence_score: float
    is_answerable: bool
    resolution_status: str  # resolved, unresolved, partial
    model_used: str
    elapsed_ms: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AdversarialQARecord:
    """Record of P9 adversarial QA phase."""
    timestamp: str
    total_questions: int
    questions_resolved: int
    questions_unresolved: int
    resolution_rate: float
    signal_novelty: float
    qa_exchanges: List[QARecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["qa_exchanges"] = [q.to_dict() if hasattr(q, 'to_dict') else q for q in self.qa_exchanges]
        return d


# -----------------------------------------------------------------------------
# P10: Gating Decision
# -----------------------------------------------------------------------------

@dataclass
class GatingDecisionRecord:
    """Record of P10 gating decision."""
    timestamp: str
    gating_case: str  # CASE_1, CASE_2, CASE_3, CASE_4
    sufficiency_score: float
    confidence_score: float
    integrity_score: float
    iteration_number: int
    reasoning_trace: str  # Full LLM reasoning
    contributing_factors: Dict[str, float]
    decision_threshold: float
    metrics_snapshot: Dict[str, Any]
    recommendation: str

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# P11: Knowledge Integration / Gap Analysis
# -----------------------------------------------------------------------------

@dataclass
class IdentifiedGapRecord:
    """Record of a single identified gap."""
    gap_id: str
    gap_type: str  # content, source, evidence, coverage
    description: str
    severity: str  # critical, high, medium, low
    affected_constraints: List[str]
    suggested_queries: List[str]
    estimated_effort: str
    auto_fillable: bool

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GapAnalysisRecord:
    """Record of P11 knowledge integration / gap analysis."""
    timestamp: str
    total_gaps_found: int
    critical_gaps: int
    high_gaps: int
    medium_gaps: int
    low_gaps: int
    coverage_score: float
    completeness_score: float
    gaps: List[IdentifiedGapRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["gaps"] = [g.to_dict() if hasattr(g, 'to_dict') else g for g in self.gaps]
        return d


# -----------------------------------------------------------------------------
# P12: Research Packaging / Citation Resolution
# -----------------------------------------------------------------------------

@dataclass
class CitationResolutionRecord:
    """Record of a single citation resolution."""
    citation_token: str  # [CITE:chunk_xxxx]
    chunk_id: str
    resolved_url: str
    resolved_title: str
    resolved_authors: List[str]
    resolved_date: str
    section_used_in: str
    context_text: str  # surrounding text
    resolution_success: bool
    resolution_error: Optional[str]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ReportSectionRecord:
    """Record of a report section in P12."""
    section_id: str
    section_title: str
    word_count: int
    citation_count: int
    citation_tokens: List[str]
    claims_in_section: int

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CitationPackagingRecord:
    """Record of P12 research packaging / citation packaging."""
    timestamp: str
    total_sections: int
    total_word_count: int
    total_citations: int
    unique_sources: int
    citation_density: float  # citations per 1000 words
    unresolved_citations: int
    sections: List[ReportSectionRecord] = field(default_factory=list)
    resolutions: List[CitationResolutionRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["sections"] = [s.to_dict() if hasattr(s, 'to_dict') else s for s in self.sections]
        d["resolutions"] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.resolutions]
        return d


# -----------------------------------------------------------------------------
# P13: Narrative Synthesis / Final Output Quality
# -----------------------------------------------------------------------------

@dataclass
class FinalOutputRecord:
    """Record of P13 narrative synthesis / final output quality metrics."""
    timestamp: str
    output_type: str  # full_report, gap_report, failure_report
    total_word_count: int
    total_sections: int
    total_citations: int
    unique_sources: int
    hallucination_rate: float
    faithfulness_score: float
    citation_accuracy: float
    readability_score: float
    completeness_score: float
    overall_quality_score: float
    sota_compliant: bool
    quality_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# LLM Call Record (existing, enhanced)
# -----------------------------------------------------------------------------

@dataclass
class LLMCallRecord:
    """Record of a single LLM API call."""
    call_id: str
    timestamp: str
    phase: int
    purpose: str  # query_generation, synthesis, verification, etc.
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    prompt_preview: str
    response_preview: str
    prompt_template: str  # which template was used
    error: Optional[str]
    error_traceback: Optional[str]
    retry_count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# Phase Record (existing, enhanced)
# -----------------------------------------------------------------------------

@dataclass
class PhaseRecord:
    """Record of a phase execution."""
    phase_number: int
    phase_name: str
    start_time: str
    end_time: Optional[str]
    duration_seconds: float
    status: str  # running, completed, failed
    input_file: Optional[str]
    output_file: Optional[str]
    input_count: int
    output_count: int
    quality_gate_passed: bool
    quality_gate_details: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    error_tracebacks: List[str]
    custom_metrics: Dict[str, Any]
    memory_before_mb: float = 0.0
    memory_after_mb: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# Cost Record
# -----------------------------------------------------------------------------

@dataclass
class CostRecord:
    """Record of cost tracking."""
    timestamp: str
    phase: int
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_cost_usd: float
    budget_remaining_usd: float
    budget_utilization: float

    def to_dict(self) -> Dict:
        return asdict(self)


# -----------------------------------------------------------------------------
# Cache Record
# -----------------------------------------------------------------------------

@dataclass
class CacheOperationRecord:
    """Record of cache operation."""
    timestamp: str
    operation: str  # hit, miss, set, evict
    cache_type: str  # embedding, llm, url
    key_preview: str
    hit: bool
    size_bytes: int
    elapsed_ms: float

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# GEMINI CONTENT ANALYZER
# =============================================================================

class GeminiContentAnalyzer:
    """Uses Gemini 2.5 Flash for content analysis."""

    MODEL_ID = "gemini-2.5-flash-preview-04-17"

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_AI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.MODEL_ID)
            except ImportError:
                print("[AUDIT] google-generativeai not installed")
            except Exception as e:
                print(f"[AUDIT] Gemini init failed: {e}")
        return self._client

    def analyze_chunk_quality(self, chunks: List[ChunkRecord]) -> Dict[str, Any]:
        client = self._get_client()
        if not client or not chunks:
            return {"status": "skipped", "reason": "no_client_or_chunks"}

        sample_size = min(20, len(chunks))
        sample = chunks[:sample_size]

        prompt = f"""Analyze these {sample_size} research chunks for quality issues.

For each chunk, evaluate:
1. Is the content relevant to research? (yes/no)
2. Is there garbage/boilerplate content? (yes/no, describe if yes)
3. Is the text coherent and complete? (yes/no)
4. Quality score (1-10)

Chunks:
"""
        for i, chunk in enumerate(sample):
            prompt += f"\n--- Chunk {i+1} ({chunk.chunk_id}) ---\n"
            prompt += f"Source: {chunk.source_url[:80]}\n"
            prompt += f"Text: {chunk.text_preview[:400]}\n"

        prompt += '\n\nProvide analysis as JSON: {"chunks": [{"id": ..., "relevant": bool, "garbage": bool, "garbage_reason": str|null, "coherent": bool, "quality": int}], "overall_quality": float, "issues": [str]}'

        try:
            response = client.generate_content(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return {"status": "success", "analysis": json.loads(text.strip()), "sample_size": sample_size}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def generate_gap_analysis(self, audit_summary: Dict) -> Dict[str, Any]:
        client = self._get_client()
        if not client:
            return {"status": "skipped", "reason": "no_client"}

        prompt = f"""Analyze this research pipeline audit summary and identify quality gaps.

AUDIT SUMMARY:
{json.dumps(audit_summary, indent=2, default=str)[:8000]}

Provide detailed gap analysis as JSON:
{{
    "critical_gaps": [{{"gap": str, "severity": "critical"|"high"|"medium", "impact": str, "recommendation": str}}],
    "quality_score": float (0-1),
    "top_3_recommendations": [str],
    "strengths": [str],
    "weaknesses": [str]
}}
"""
        try:
            response = client.generate_content(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return {"status": "success", "analysis": json.loads(text.strip())}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# =============================================================================
# AUDIT COLLECTOR - COMPLETE IMPLEMENTATION
# =============================================================================

class AuditCollector:
    """
    Complete audit collector for POLARIS pipeline.
    Captures data from ALL phases (P0-P13) plus cross-cutting concerns.
    """

    SOTA_TARGETS = {
        "max_hallucination_rate": 0.05,
        "min_faithfulness": 0.80,
        "min_citation_accuracy": 0.95,
        "min_source_diversity": 10,
        "min_content_coverage": 0.80,
        "min_word_count": 2000,
        "min_verified_claims": 30,
        "min_url_success_rate": 0.60,
        "min_chunks_passed": 100,
        "max_cost_usd": 5.00,
    }

    def __init__(self, vector_id: str, budget_usd: float = 5.0):
        self.vector_id = vector_id
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.budget_usd = budget_usd

        # Audit output directory
        self.audit_dir = OUTPUTS_DIR / "audit" / vector_id / self.run_id
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        # Real-time stream file
        self.stream_file = self.audit_dir / "audit_stream.jsonl"

        # === ALL RECORD COLLECTIONS ===
        # P0
        self.vector_parse: Optional[VectorParseRecord] = None
        self.constraints: List[ConstraintRecord] = []

        # P1
        self.decompositions: List[DecompositionRecord] = []

        # P2
        self.query_generation: Optional[QueryGenerationRecord] = None
        self.queries: List[QueryRecord] = []

        # P3
        self.search_executions: List[SearchExecutionRecord] = []
        self.search_results: List[SearchResultRecord] = []

        # P4
        self.url_fetches: List[URLFetchRecord] = []
        self.chunks: List[ChunkRecord] = []

        # P5
        self.memory_operations: List[MemoryOperationRecord] = []
        self.memory_states: List[MemoryStateRecord] = []

        # P6
        self.integrity_check: Optional[IntegrityCheckRecord] = None
        self.nli_checks: List[NLICheckRecord] = []

        # P7
        self.rag_record: Optional[RAGRecord] = None
        self.retrievals: List[RetrievalRecord] = []
        self.generations: List[GenerationRecord] = []

        # P8: Claim Verification
        self.claims: List[ClaimRecord] = []

        # P9: Adversarial QA
        self.adversarial_qa: Optional[AdversarialQARecord] = None
        self.qa_exchanges: List[QARecord] = []

        # P10: Gating
        self.gating_decisions: List[GatingDecisionRecord] = []

        # P11: Knowledge Integration / Gap Analysis
        self.gap_analysis: Optional[GapAnalysisRecord] = None
        self.identified_gaps: List[IdentifiedGapRecord] = []

        # P12: Research Packaging
        self.citation_packaging: Optional[CitationPackagingRecord] = None
        self.citation_resolutions: List[CitationResolutionRecord] = []
        self.report_sections: List[ReportSectionRecord] = []

        # P13: Narrative Synthesis / Final Output
        self.final_output: Optional[FinalOutputRecord] = None

        # Cross-cutting
        self.llm_calls: List[LLMCallRecord] = []
        self.phases: Dict[int, PhaseRecord] = {}
        self.cost_records: List[CostRecord] = []
        self.cache_operations: List[CacheOperationRecord] = []

        # Aggregates
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None

        # Counters
        self._counters = defaultdict(int)

        # Analyzers
        self.gemini = GeminiContentAnalyzer()
        self.benchmark_auditor: Optional[BenchmarkAuditor] = None

    def _next_id(self, prefix: str) -> str:
        """Generate next ID for a record type."""
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]:05d}"

    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Write event to real-time stream."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vector_id": self.vector_id,
            "run_id": self.run_id,
            "event_type": event_type,
            "data": data,
        }
        with open(self.stream_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def _get_memory_usage(self) -> Tuple[float, float]:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process()
            mem = process.memory_info()
            return mem.rss / 1024 / 1024, mem.vms / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            # psutil may fail on some systems - return zeros as fallback
            return 0.0, 0.0

    # =========================================================================
    # RUN LIFECYCLE
    # =========================================================================

    def start_run(self) -> None:
        """Mark run start."""
        self.start_time = datetime.now(timezone.utc).isoformat()
        rss, vms = self._get_memory_usage()
        self._log_event("run_start", {
            "vector_id": self.vector_id,
            "budget_usd": self.budget_usd,
            "memory_rss_mb": rss,
            "memory_vms_mb": vms,
        })
        print(f"[AUDIT] Started for {self.vector_id}")
        print(f"[AUDIT] Stream: {self.stream_file}")

    def end_run(self) -> None:
        """Mark run end."""
        self.end_time = datetime.now(timezone.utc).isoformat()
        rss, vms = self._get_memory_usage()
        self._log_event("run_end", {
            "total_urls": len(self.url_fetches),
            "total_chunks": len(self.chunks),
            "total_claims": len(self.claims),
            "total_llm_calls": len(self.llm_calls),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "memory_rss_mb": rss,
            "memory_vms_mb": vms,
        })
        print(f"[AUDIT] Completed for {self.vector_id}")

    # =========================================================================
    # P0: VECTOR PARSING
    # =========================================================================

    def log_constraint(
        self,
        constraint_type: str,
        constraint_text: str,
        source_field: str,
        extraction_method: str = "llm",
        confidence: float = 1.0,
        parsed_values: Optional[Dict] = None,
    ) -> str:
        """Log a single extracted constraint."""
        cid = self._next_id("constraint")
        record = ConstraintRecord(
            constraint_id=cid,
            constraint_type=constraint_type,
            constraint_text=constraint_text,
            source_field=source_field,
            extraction_method=extraction_method,
            confidence=confidence,
            parsed_values=parsed_values or {},
        )
        self.constraints.append(record)
        self._log_event("constraint_extracted", record.to_dict())
        return cid

    def log_vector_parse(
        self,
        raw_input_size: int,
        hard_constraints: int,
        soft_constraints: int,
        context_constraints: int,
        parse_errors: Optional[List[str]] = None,
    ) -> None:
        """Log P0 vector parsing completion."""
        self.vector_parse = VectorParseRecord(
            vector_id=self.vector_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_input_size=raw_input_size,
            constraints_extracted=len(self.constraints),
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            context_constraints=context_constraints,
            parse_errors=parse_errors or [],
            constraints=self.constraints.copy(),
        )
        self._log_event("vector_parse_complete", self.vector_parse.to_dict())

    # =========================================================================
    # P1: CONSTRAINT DECOMPOSITION
    # =========================================================================

    def log_decomposition(
        self,
        original_constraint_id: str,
        original_text: str,
        decomposed_constraints: List[Dict],
        decomposition_method: str = "llm",
        llm_reasoning: Optional[str] = None,
    ) -> None:
        """Log constraint decomposition."""
        record = DecompositionRecord(
            original_constraint_id=original_constraint_id,
            original_text=original_text,
            decomposed_constraints=decomposed_constraints,
            decomposition_method=decomposition_method,
            llm_reasoning=llm_reasoning,
            decomposition_count=len(decomposed_constraints),
        )
        self.decompositions.append(record)
        self._log_event("constraint_decomposed", record.to_dict())

    # =========================================================================
    # P2: QUERY GENERATION
    # =========================================================================

    def log_query(
        self,
        query_text: str,
        query_type: str,
        target_constraint_ids: List[str],
        generation_method: str = "llm",
        diversity_score: float = 0.0,
        expected_engines: Optional[List[str]] = None,
        llm_reasoning: Optional[str] = None,
    ) -> str:
        """Log a single generated query."""
        qid = self._next_id("query")
        record = QueryRecord(
            query_id=qid,
            query_text=query_text,
            query_type=query_type,
            target_constraint_ids=target_constraint_ids,
            generation_method=generation_method,
            diversity_score=diversity_score,
            expected_engines=expected_engines or ["google", "pubmed"],
            llm_reasoning=llm_reasoning,
        )
        self.queries.append(record)
        self._log_event("query_generated", {"query_id": qid, "query_text": query_text[:100]})
        return qid

    def log_query_generation_complete(
        self,
        constraint_coverage: float = 0.0,
    ) -> None:
        """Log P2 query generation completion."""
        queries_by_type = defaultdict(int)
        diversity_scores = []
        for q in self.queries:
            queries_by_type[q.query_type] += 1
            diversity_scores.append(q.diversity_score)

        self.query_generation = QueryGenerationRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_queries=len(self.queries),
            queries_by_type=dict(queries_by_type),
            avg_diversity_score=sum(diversity_scores) / len(diversity_scores) if diversity_scores else 0,
            constraint_coverage=constraint_coverage,
            queries=self.queries.copy(),
        )
        self._log_event("query_generation_complete", {
            "total_queries": len(self.queries),
            "constraint_coverage": constraint_coverage,
        })

    # =========================================================================
    # P3: SEARCH EXECUTION
    # =========================================================================

    def log_search_result(
        self,
        query_id: str,
        engine: str,
        rank: int,
        url: str,
        title: str,
        snippet: str,
        relevance_score: float = 0.0,
        is_academic: bool = False,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Log a single search result."""
        from urllib.parse import urlparse
        rid = self._next_id("result")
        record = SearchResultRecord(
            result_id=rid,
            query_id=query_id,
            engine=engine,
            rank=rank,
            url=url,
            title=title,
            snippet=snippet,
            relevance_score=relevance_score,
            domain=urlparse(url).netloc,
            is_academic=is_academic,
            metadata=metadata or {},
        )
        self.search_results.append(record)
        return rid

    def log_search_execution(
        self,
        query_id: str,
        query_text: str,
        engines_used: List[str],
        results_per_engine: Dict[str, int],
        elapsed_ms: float,
        errors: Optional[List[Dict]] = None,
    ) -> None:
        """Log search execution for a query."""
        query_results = [r for r in self.search_results if r.query_id == query_id]
        urls = [r.url for r in query_results]
        unique_urls = set(urls)

        record = SearchExecutionRecord(
            query_id=query_id,
            query_text=query_text,
            timestamp=datetime.now(timezone.utc).isoformat(),
            engines_used=engines_used,
            results_per_engine=results_per_engine,
            total_results=len(query_results),
            unique_urls=len(unique_urls),
            duplicate_urls=len(urls) - len(unique_urls),
            avg_relevance=sum(r.relevance_score for r in query_results) / len(query_results) if query_results else 0,
            elapsed_ms=elapsed_ms,
            errors=errors or [],
            results=query_results,
        )
        self.search_executions.append(record)
        self._log_event("search_executed", {
            "query_id": query_id,
            "total_results": len(query_results),
            "engines": engines_used,
        })

    # =========================================================================
    # P4: URL FETCHING AND CHUNKS
    # =========================================================================

    def log_url_fetch(
        self,
        url: str,
        method: str,
        status_code: Optional[int],
        success: bool,
        error_type: Optional[str] = None,
        error_detail: Optional[str] = None,
        raw_content_length: int = 0,
        extracted_text_length: int = 0,
        extraction_method: str = "",
        content_type: str = "",
        is_garbage: bool = False,
        garbage_reason: Optional[str] = None,
        chunks_created: int = 0,
        elapsed_ms: float = 0,
        attempt_number: int = 1,
        retry_count: int = 0,
        fallback_methods_tried: Optional[List[str]] = None,
    ) -> None:
        """Log a URL fetch attempt."""
        from urllib.parse import urlparse

        record = URLFetchRecord(
            url=url,
            domain=urlparse(url).netloc,
            timestamp=datetime.now(timezone.utc).isoformat(),
            attempt_number=attempt_number,
            method=method,
            status_code=status_code,
            success=success,
            error_type=error_type,
            error_detail=error_detail,
            error_traceback=traceback.format_exc() if error_type else None,
            raw_content_length=raw_content_length,
            extracted_text_length=extracted_text_length,
            extraction_method=extraction_method,
            content_type=content_type,
            is_garbage=is_garbage,
            garbage_reason=garbage_reason,
            chunks_created=chunks_created,
            elapsed_ms=elapsed_ms,
            retry_count=retry_count,
            fallback_methods_tried=fallback_methods_tried or [],
        )
        self.url_fetches.append(record)
        self._log_event("url_fetch", {
            "url": url[:80],
            "success": success,
            "method": method,
            "status": status_code,
        })

    def log_chunk(
        self,
        chunk_id: str,
        source_url: str,
        source_title: str,
        fetch_method: str,
        text: str,
        relevance_score: float,
        hard_score: float = 0.0,
        soft_score: float = 0.0,
        domain_adjustment: float = 0.0,
        tier: str = "unknown",
        is_garbage: bool = False,
        garbage_reason: Optional[str] = None,
        registered_to_vwm: bool = False,
        memory_tier: str = "",
        embedding_id: Optional[str] = None,
        lineage: Optional[Dict] = None,
    ) -> None:
        """Log a chunk."""
        from urllib.parse import urlparse

        record = ChunkRecord(
            chunk_id=chunk_id,
            source_url=source_url,
            source_domain=urlparse(source_url).netloc,
            source_title=source_title,
            fetch_method=fetch_method,
            text_preview=text[:500] if text else "",
            text_full=text,
            text_hash=hashlib.md5(text.encode()).hexdigest() if text else "",
            char_count=len(text) if text else 0,
            word_count=len(text.split()) if text else 0,
            relevance_score=relevance_score,
            hard_score=hard_score,
            soft_score=soft_score,
            domain_adjustment=domain_adjustment,
            tier=tier,
            is_garbage=is_garbage,
            garbage_reason=garbage_reason,
            registered_to_vwm=registered_to_vwm,
            memory_tier=memory_tier,
            embedding_id=embedding_id,
            lineage=lineage or {},
        )
        self.chunks.append(record)
        self._log_event("chunk_created", {
            "chunk_id": chunk_id,
            "score": relevance_score,
            "tier": tier,
        })

    # =========================================================================
    # P5: MEMORY OPERATIONS
    # =========================================================================

    def log_memory_operation(
        self,
        operation_type: str,
        memory_tier: str,
        chunk_id: str,
        embedding_model: str = "",
        embedding_dimensions: int = 0,
        similarity_score: Optional[float] = None,
        elapsed_ms: float = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> str:
        """Log a memory operation."""
        oid = self._next_id("memop")
        record = MemoryOperationRecord(
            operation_id=oid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation_type=operation_type,
            memory_tier=memory_tier,
            chunk_id=chunk_id,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            similarity_score=similarity_score,
            elapsed_ms=elapsed_ms,
            success=success,
            error=error,
        )
        self.memory_operations.append(record)
        self._log_event("memory_operation", {
            "operation": operation_type,
            "tier": memory_tier,
            "chunk_id": chunk_id,
        })
        return oid

    def log_memory_state(
        self,
        vwm_chunk_count: int,
        vwm_total_chars: int,
        vwm_capacity_used: float,
        ltm_stage_chunk_count: int = 0,
        ltm_global_chunk_count: int = 0,
        ltm_total_embeddings: int = 0,
        cache_hit_rate: float = 0.0,
        cache_size_mb: float = 0.0,
    ) -> None:
        """Log memory state snapshot."""
        rss, vms = self._get_memory_usage()
        record = MemoryStateRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            vwm_chunk_count=vwm_chunk_count,
            vwm_total_chars=vwm_total_chars,
            vwm_capacity_used=vwm_capacity_used,
            ltm_stage_chunk_count=ltm_stage_chunk_count,
            ltm_global_chunk_count=ltm_global_chunk_count,
            ltm_total_embeddings=ltm_total_embeddings,
            cache_hit_rate=cache_hit_rate,
            cache_size_mb=cache_size_mb,
            memory_rss_mb=rss,
            memory_vms_mb=vms,
        )
        self.memory_states.append(record)
        self._log_event("memory_state", record.to_dict())

    # =========================================================================
    # P6: NLI INTEGRITY CHECK
    # =========================================================================

    def log_nli_check(
        self,
        chunk_a_id: str,
        chunk_b_id: str,
        chunk_a_preview: str,
        chunk_b_preview: str,
        entailment_score: float,
        contradiction_score: float,
        neutral_score: float,
        verdict: str,
        model_used: str = "",
        elapsed_ms: float = 0,
    ) -> str:
        """Log NLI check between chunks."""
        cid = self._next_id("nli")
        record = NLICheckRecord(
            check_id=cid,
            chunk_a_id=chunk_a_id,
            chunk_b_id=chunk_b_id,
            chunk_a_preview=chunk_a_preview[:200],
            chunk_b_preview=chunk_b_preview[:200],
            entailment_score=entailment_score,
            contradiction_score=contradiction_score,
            neutral_score=neutral_score,
            verdict=verdict,
            model_used=model_used,
            elapsed_ms=elapsed_ms,
        )
        self.nli_checks.append(record)
        if verdict == "contradictory":
            self._log_event("nli_contradiction", {
                "chunk_a": chunk_a_id,
                "chunk_b": chunk_b_id,
                "score": contradiction_score,
            })
        return cid

    def log_integrity_check_complete(
        self,
        consistency_score: float,
        chunks_flagged: List[str],
    ) -> None:
        """Log P6 integrity check completion."""
        contradictions = [c for c in self.nli_checks if c.verdict == "contradictory"]
        self.integrity_check = IntegrityCheckRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_pairs_checked=len(self.nli_checks),
            contradictions_found=len(contradictions),
            consistency_score=consistency_score,
            chunks_flagged=chunks_flagged,
            nli_checks=self.nli_checks.copy(),
        )
        self._log_event("integrity_check_complete", {
            "pairs_checked": len(self.nli_checks),
            "contradictions": len(contradictions),
            "consistency": consistency_score,
        })

    # =========================================================================
    # P7: RAG SYNTHESIS
    # =========================================================================

    def log_retrieval(
        self,
        query_text: str,
        memory_tier: str,
        chunks_retrieved: int,
        top_chunk_ids: List[str],
        top_scores: List[float],
        elapsed_ms: float = 0,
    ) -> str:
        """Log a retrieval from memory."""
        rid = self._next_id("retrieval")
        record = RetrievalRecord(
            retrieval_id=rid,
            query_text=query_text,
            memory_tier=memory_tier,
            chunks_retrieved=chunks_retrieved,
            top_chunk_ids=top_chunk_ids,
            top_scores=top_scores,
            elapsed_ms=elapsed_ms,
        )
        self.retrievals.append(record)
        self._log_event("retrieval", {
            "retrieval_id": rid,
            "chunks": chunks_retrieved,
            "tier": memory_tier,
        })
        return rid

    def log_generation(
        self,
        prompt_type: str,
        context_chunks: List[str],
        context_char_count: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        output_char_count: int,
        citations_generated: int,
        elapsed_ms: float,
        output_preview: str = "",
    ) -> str:
        """Log a generation in RAG."""
        gid = self._next_id("generation")
        record = GenerationRecord(
            generation_id=gid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            prompt_type=prompt_type,
            context_chunks=context_chunks,
            context_char_count=context_char_count,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            output_char_count=output_char_count,
            citations_generated=citations_generated,
            elapsed_ms=elapsed_ms,
            output_preview=output_preview[:500],
        )
        self.generations.append(record)
        self._log_event("generation", {
            "generation_id": gid,
            "type": prompt_type,
            "citations": citations_generated,
        })
        return gid

    def log_rag_complete(
        self,
        analysis_word_count: int,
        context_utilization: float,
    ) -> None:
        """Log P7 RAG completion."""
        unique_chunks = set()
        for g in self.generations:
            unique_chunks.update(g.context_chunks)

        self.rag_record = RAGRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_retrievals=len(self.retrievals),
            total_generations=len(self.generations),
            unique_chunks_used=len(unique_chunks),
            total_citations=sum(g.citations_generated for g in self.generations),
            analysis_word_count=analysis_word_count,
            context_utilization=context_utilization,
            retrievals=self.retrievals.copy(),
            generations=self.generations.copy(),
        )
        self._log_event("rag_complete", {
            "retrievals": len(self.retrievals),
            "generations": len(self.generations),
            "word_count": analysis_word_count,
        })

    # =========================================================================
    # P8: CLAIM VERIFICATION
    # =========================================================================

    def log_claim(
        self,
        claim_id: str,
        claim_text: str,
        claim_text_cleaned: str,
        source_section: str,
        cited_chunk_ids: List[str],
        verification_attempts: List[Dict],
        best_evidence_chunk_id: Optional[str],
        best_evidence_text: Optional[str],
        best_entailment_score: float,
        verdict: str,
        was_blocked: bool = False,
        block_reason: Optional[str] = None,
        lineage: Optional[Dict] = None,
    ) -> None:
        """Log claim verification."""
        record = ClaimRecord(
            claim_id=claim_id,
            claim_text=claim_text,
            claim_text_cleaned=claim_text_cleaned,
            source_section=source_section,
            cited_chunk_ids=cited_chunk_ids,
            verification_attempts=verification_attempts,
            best_evidence_chunk_id=best_evidence_chunk_id,
            best_evidence_text=best_evidence_text,
            best_entailment_score=best_entailment_score,
            verdict=verdict,
            was_blocked=was_blocked,
            block_reason=block_reason,
            lineage=lineage or {},
        )
        self.claims.append(record)
        self._log_event("claim_verified", {
            "claim_id": claim_id,
            "verdict": verdict,
            "score": best_entailment_score,
            "blocked": was_blocked,
        })

    # =========================================================================
    # P9: ADVERSARIAL QA
    # =========================================================================

    def log_qa_exchange(
        self,
        question_type: str,
        question_text: str,
        target_claim_ids: List[str],
        answer_text: str,
        answer_sources: List[str],
        confidence_score: float,
        is_answerable: bool,
        resolution_status: str,
        model_used: str = "",
        elapsed_ms: float = 0,
    ) -> str:
        """Log adversarial QA exchange."""
        qid = self._next_id("qa")
        record = QARecord(
            qa_id=qid,
            question_type=question_type,
            question_text=question_text,
            target_claim_ids=target_claim_ids,
            answer_text=answer_text,
            answer_sources=answer_sources,
            confidence_score=confidence_score,
            is_answerable=is_answerable,
            resolution_status=resolution_status,
            model_used=model_used,
            elapsed_ms=elapsed_ms,
        )
        self.qa_exchanges.append(record)
        self._log_event("qa_exchange", {
            "qa_id": qid,
            "type": question_type,
            "resolved": resolution_status == "resolved",
        })
        return qid

    def log_adversarial_qa_complete(
        self,
        signal_novelty: float = 0.0,
    ) -> None:
        """Log P8 adversarial QA completion."""
        resolved = [q for q in self.qa_exchanges if q.resolution_status == "resolved"]
        unresolved = [q for q in self.qa_exchanges if q.resolution_status != "resolved"]

        self.adversarial_qa = AdversarialQARecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_questions=len(self.qa_exchanges),
            questions_resolved=len(resolved),
            questions_unresolved=len(unresolved),
            resolution_rate=len(resolved) / len(self.qa_exchanges) if self.qa_exchanges else 0,
            signal_novelty=signal_novelty,
            qa_exchanges=self.qa_exchanges.copy(),
        )
        self._log_event("adversarial_qa_complete", {
            "total": len(self.qa_exchanges),
            "resolved": len(resolved),
            "novelty": signal_novelty,
        })

    # =========================================================================
    # P10: GATING DECISION
    # =========================================================================

    def log_gating_decision(
        self,
        gating_case: str,
        sufficiency_score: float,
        confidence_score: float,
        integrity_score: float,
        iteration_number: int,
        reasoning_trace: str,
        contributing_factors: Dict[str, float],
        decision_threshold: float,
        metrics_snapshot: Dict[str, Any],
        recommendation: str,
    ) -> None:
        """Log P9 gating decision."""
        record = GatingDecisionRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            gating_case=gating_case,
            sufficiency_score=sufficiency_score,
            confidence_score=confidence_score,
            integrity_score=integrity_score,
            iteration_number=iteration_number,
            reasoning_trace=reasoning_trace,
            contributing_factors=contributing_factors,
            decision_threshold=decision_threshold,
            metrics_snapshot=metrics_snapshot,
            recommendation=recommendation,
        )
        self.gating_decisions.append(record)
        self._log_event("gating_decision", {
            "case": gating_case,
            "iteration": iteration_number,
            "sufficiency": sufficiency_score,
            "confidence": confidence_score,
        })

    # =========================================================================
    # P11: KNOWLEDGE INTEGRATION / GAP ANALYSIS
    # =========================================================================

    def log_identified_gap(
        self,
        gap_type: str,
        description: str,
        severity: str,
        affected_constraints: List[str],
        suggested_queries: List[str],
        estimated_effort: str = "",
        auto_fillable: bool = False,
    ) -> str:
        """Log an identified gap."""
        gid = self._next_id("gap")
        record = IdentifiedGapRecord(
            gap_id=gid,
            gap_type=gap_type,
            description=description,
            severity=severity,
            affected_constraints=affected_constraints,
            suggested_queries=suggested_queries,
            estimated_effort=estimated_effort,
            auto_fillable=auto_fillable,
        )
        self.identified_gaps.append(record)
        self._log_event("gap_identified", {
            "gap_id": gid,
            "type": gap_type,
            "severity": severity,
        })
        return gid

    def log_gap_analysis_complete(
        self,
        coverage_score: float,
        completeness_score: float,
    ) -> None:
        """Log P10 gap analysis completion."""
        severity_counts = defaultdict(int)
        for g in self.identified_gaps:
            severity_counts[g.severity] += 1

        self.gap_analysis = GapAnalysisRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_gaps_found=len(self.identified_gaps),
            critical_gaps=severity_counts["critical"],
            high_gaps=severity_counts["high"],
            medium_gaps=severity_counts["medium"],
            low_gaps=severity_counts["low"],
            coverage_score=coverage_score,
            completeness_score=completeness_score,
            gaps=self.identified_gaps.copy(),
        )
        self._log_event("gap_analysis_complete", {
            "total_gaps": len(self.identified_gaps),
            "critical": severity_counts["critical"],
            "coverage": coverage_score,
        })

    # =========================================================================
    # P12: RESEARCH PACKAGING / CITATION RESOLUTION
    # =========================================================================

    def log_citation_resolution(
        self,
        citation_token: str,
        chunk_id: str,
        resolved_url: str,
        resolved_title: str,
        resolved_authors: List[str],
        resolved_date: str,
        section_used_in: str,
        context_text: str,
        resolution_success: bool = True,
        resolution_error: Optional[str] = None,
    ) -> None:
        """Log citation resolution."""
        record = CitationResolutionRecord(
            citation_token=citation_token,
            chunk_id=chunk_id,
            resolved_url=resolved_url,
            resolved_title=resolved_title,
            resolved_authors=resolved_authors,
            resolved_date=resolved_date,
            section_used_in=section_used_in,
            context_text=context_text[:200],
            resolution_success=resolution_success,
            resolution_error=resolution_error,
        )
        self.citation_resolutions.append(record)
        self._log_event("citation_resolved", {
            "token": citation_token,
            "success": resolution_success,
            "url": resolved_url[:60],
        })

    def log_report_section(
        self,
        section_title: str,
        word_count: int,
        citation_count: int,
        citation_tokens: List[str],
        claims_in_section: int,
    ) -> str:
        """Log a report section."""
        sid = self._next_id("section")
        record = ReportSectionRecord(
            section_id=sid,
            section_title=section_title,
            word_count=word_count,
            citation_count=citation_count,
            citation_tokens=citation_tokens,
            claims_in_section=claims_in_section,
        )
        self.report_sections.append(record)
        self._log_event("section_created", {
            "section_id": sid,
            "title": section_title,
            "words": word_count,
            "citations": citation_count,
        })
        return sid

    def log_citation_packaging_complete(
        self,
        total_word_count: int,
        unique_sources: int,
    ) -> None:
        """Log P11 citation packaging completion."""
        unresolved = [c for c in self.citation_resolutions if not c.resolution_success]

        self.citation_packaging = CitationPackagingRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_sections=len(self.report_sections),
            total_word_count=total_word_count,
            total_citations=len(self.citation_resolutions),
            unique_sources=unique_sources,
            citation_density=len(self.citation_resolutions) / (total_word_count / 1000) if total_word_count > 0 else 0,
            unresolved_citations=len(unresolved),
            sections=self.report_sections.copy(),
            resolutions=self.citation_resolutions.copy(),
        )
        self._log_event("citation_packaging_complete", {
            "sections": len(self.report_sections),
            "citations": len(self.citation_resolutions),
            "unresolved": len(unresolved),
        })

    # =========================================================================
    # P13: NARRATIVE SYNTHESIS / FINAL OUTPUT
    # =========================================================================

    def log_final_output(
        self,
        output_type: str,
        total_word_count: int,
        total_sections: int,
        total_citations: int,
        unique_sources: int,
        hallucination_rate: float,
        faithfulness_score: float,
        citation_accuracy: float,
        readability_score: float = 0.0,
        completeness_score: float = 0.0,
        quality_issues: Optional[List[str]] = None,
    ) -> None:
        """Log P12 final output quality."""
        overall = (
            (1 - hallucination_rate) * 0.3 +
            faithfulness_score * 0.3 +
            citation_accuracy * 0.2 +
            completeness_score * 0.2
        )
        sota_compliant = (
            hallucination_rate <= self.SOTA_TARGETS["max_hallucination_rate"] and
            faithfulness_score >= self.SOTA_TARGETS["min_faithfulness"] and
            total_word_count >= self.SOTA_TARGETS["min_word_count"] and
            unique_sources >= self.SOTA_TARGETS["min_source_diversity"]
        )

        self.final_output = FinalOutputRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            output_type=output_type,
            total_word_count=total_word_count,
            total_sections=total_sections,
            total_citations=total_citations,
            unique_sources=unique_sources,
            hallucination_rate=hallucination_rate,
            faithfulness_score=faithfulness_score,
            citation_accuracy=citation_accuracy,
            readability_score=readability_score,
            completeness_score=completeness_score,
            overall_quality_score=overall,
            sota_compliant=sota_compliant,
            quality_issues=quality_issues or [],
        )
        self._log_event("final_output", {
            "type": output_type,
            "words": total_word_count,
            "quality": overall,
            "sota_compliant": sota_compliant,
        })

    # =========================================================================
    # LLM CALLS
    # =========================================================================

    def log_llm_call(
        self,
        phase: int,
        purpose: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
        prompt_preview: str = "",
        response_preview: str = "",
        prompt_template: str = "",
        error: Optional[str] = None,
        retry_count: int = 0,
    ) -> str:
        """Log an LLM API call."""
        cid = self._next_id("llm")
        total_tokens = input_tokens + output_tokens

        record = LLMCallRecord(
            call_id=cid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            phase=phase,
            purpose=purpose,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            prompt_preview=prompt_preview[:500] if prompt_preview else "",
            response_preview=response_preview[:500] if response_preview else "",
            prompt_template=prompt_template,
            error=error,
            error_traceback=traceback.format_exc() if error else None,
            retry_count=retry_count,
        )

        self.llm_calls.append(record)
        self.total_tokens += total_tokens
        self.total_cost_usd += cost_usd

        # Log cost record
        self.cost_records.append(CostRecord(
            timestamp=record.timestamp,
            phase=phase,
            purpose=purpose,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cumulative_cost_usd=self.total_cost_usd,
            budget_remaining_usd=self.budget_usd - self.total_cost_usd,
            budget_utilization=self.total_cost_usd / self.budget_usd if self.budget_usd > 0 else 0,
        ))

        self._log_event("llm_call", {
            "call_id": cid,
            "phase": phase,
            "purpose": purpose,
            "model": model,
            "tokens": total_tokens,
            "cost_usd": cost_usd,
            "cumulative_cost": self.total_cost_usd,
        })

        return cid

    # =========================================================================
    # CACHE OPERATIONS
    # =========================================================================

    def log_cache_operation(
        self,
        operation: str,
        cache_type: str,
        key_preview: str,
        hit: bool,
        size_bytes: int = 0,
        elapsed_ms: float = 0,
    ) -> None:
        """Log cache operation."""
        record = CacheOperationRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation=operation,
            cache_type=cache_type,
            key_preview=key_preview[:100],
            hit=hit,
            size_bytes=size_bytes,
            elapsed_ms=elapsed_ms,
        )
        self.cache_operations.append(record)

    # =========================================================================
    # PHASE LOGGING
    # =========================================================================

    def start_phase(
        self,
        phase_number: int,
        phase_name: str,
        input_file: Optional[str] = None,
        input_count: int = 0,
    ) -> None:
        """Mark phase start."""
        rss, _ = self._get_memory_usage()
        record = PhaseRecord(
            phase_number=phase_number,
            phase_name=phase_name,
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=None,
            duration_seconds=0,
            status="running",
            input_file=input_file,
            output_file=None,
            input_count=input_count,
            output_count=0,
            quality_gate_passed=False,
            quality_gate_details={},
            errors=[],
            warnings=[],
            error_tracebacks=[],
            custom_metrics={},
            memory_before_mb=rss,
        )
        self.phases[phase_number] = record
        self._log_event("phase_start", {
            "phase": phase_number,
            "name": phase_name,
            "input_count": input_count,
            "memory_mb": rss,
        })

    def end_phase(
        self,
        phase_number: int,
        status: str = "completed",
        output_file: Optional[str] = None,
        output_count: int = 0,
        quality_gate_passed: bool = True,
        quality_gate_details: Optional[Dict] = None,
        custom_metrics: Optional[Dict] = None,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        """Mark phase end."""
        if phase_number not in self.phases:
            return

        record = self.phases[phase_number]
        record.end_time = datetime.now(timezone.utc).isoformat()
        record.status = status
        record.output_file = output_file
        record.output_count = output_count
        record.quality_gate_passed = quality_gate_passed
        record.quality_gate_details = quality_gate_details or {}
        record.custom_metrics = custom_metrics or {}
        record.errors = errors or []
        record.warnings = warnings or []

        rss, _ = self._get_memory_usage()
        record.memory_after_mb = rss

        # Calculate duration
        try:
            start = datetime.fromisoformat(record.start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(record.end_time.replace('Z', '+00:00'))
            record.duration_seconds = (end - start).total_seconds()
        except (ValueError, TypeError) as e:
            # Log parsing errors but don't fail - duration will remain at default 0.0
            self._log_event("duration_parse_error", {"phase": phase_number, "error": str(e)})

        # Calculate phase tokens and cost
        phase_calls = [c for c in self.llm_calls if c.phase == phase_number]
        record.tokens_used = sum(c.total_tokens for c in phase_calls)
        record.cost_usd = sum(c.cost_usd for c in phase_calls)

        self._log_event("phase_end", {
            "phase": phase_number,
            "status": status,
            "duration": record.duration_seconds,
            "output_count": output_count,
            "quality_gate": quality_gate_passed,
            "tokens": record.tokens_used,
            "cost_usd": record.cost_usd,
            "memory_mb": rss,
        })

    # =========================================================================
    # REPORT GENERATION
    # =========================================================================

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report."""
        # Analyze all data
        url_analysis = self._analyze_url_fetches()
        chunk_analysis = self._analyze_chunks()
        claim_analysis = self._analyze_claims()
        cost_analysis = self._analyze_costs()
        memory_analysis = self._analyze_memory()
        phase_analysis = self._analyze_phases()

        # Identify gaps
        gaps = self._identify_gaps(url_analysis, chunk_analysis, claim_analysis, cost_analysis)

        # Build summary for Gemini
        summary = {
            "url_success_rate": url_analysis.get("success_rate", 0),
            "chunks_passed": chunk_analysis.get("passed", 0),
            "chunk_tiers": chunk_analysis.get("tier_distribution", {}),
            "unique_sources": chunk_analysis.get("unique_sources", 0),
            "claims_total": claim_analysis.get("total", 0),
            "hallucination_rate": claim_analysis.get("hallucination_rate", 0),
            "total_tokens": cost_analysis.get("total_tokens", 0),
            "total_cost_usd": cost_analysis.get("total_cost_usd", 0),
            "gaps_count": len(gaps),
        }

        # Gemini analysis
        gemini_chunk_analysis = self.gemini.analyze_chunk_quality(self.chunks)
        gemini_gap_analysis = self.gemini.generate_gap_analysis(summary)

        report = {
            "meta": {
                "vector_id": self.vector_id,
                "run_id": self.run_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "start_time": self.start_time,
                "end_time": self.end_time,
                "audit_dir": str(self.audit_dir),
            },
            "summary": {
                "total_constraints": len(self.constraints),
                "total_queries": len(self.queries),
                "total_search_results": len(self.search_results),
                "total_urls_attempted": len(self.url_fetches),
                "total_urls_successful": sum(1 for u in self.url_fetches if u.success),
                "total_chunks_created": len(self.chunks),
                "total_chunks_passed": sum(1 for c in self.chunks if c.tier != "rejected"),
                "total_memory_operations": len(self.memory_operations),
                "total_nli_checks": len(self.nli_checks),
                "total_retrievals": len(self.retrievals),
                "total_generations": len(self.generations),
                "total_claims_verified": len(self.claims),
                "total_claims_supported": sum(1 for c in self.claims if c.verdict == "supported"),
                "total_qa_exchanges": len(self.qa_exchanges),
                "total_gaps_identified": len(self.identified_gaps),
                "total_citations_resolved": len(self.citation_resolutions),
                "total_llm_calls": len(self.llm_calls),
                "total_tokens": self.total_tokens,
                "total_cost_usd": round(self.total_cost_usd, 4),
                "budget_utilization": round(self.total_cost_usd / self.budget_usd, 4) if self.budget_usd > 0 else 0,
            },
            "url_analysis": url_analysis,
            "chunk_analysis": chunk_analysis,
            "claim_analysis": claim_analysis,
            "cost_analysis": cost_analysis,
            "memory_analysis": memory_analysis,
            "phase_analysis": phase_analysis,
            "gaps": gaps,
            "recommendations": self._generate_recommendations(gaps),
            "gemini_analysis": {
                "chunk_quality": gemini_chunk_analysis,
                "gap_analysis": gemini_gap_analysis,
            },
            "sota_targets": self.SOTA_TARGETS,
            "final_output": self.final_output.to_dict() if self.final_output else None,
        }

        # Save report
        report_file = self.audit_dir / "audit_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        # Save all ledgers
        self._save_all_ledgers()

        # Generate markdown report
        self._generate_markdown_report(report)

        print(f"[AUDIT] Report saved: {report_file}")
        return report

    def _analyze_url_fetches(self) -> Dict[str, Any]:
        if not self.url_fetches:
            return {"total": 0}

        by_status = defaultdict(list)
        for u in self.url_fetches:
            if u.success:
                by_status["success"].append(u)
            else:
                by_status[u.error_type or "unknown"].append(u)

        by_method = defaultdict(int)
        for u in self.url_fetches:
            if u.success:
                by_method[u.method] += 1

        total = len(self.url_fetches)
        success = len(by_status["success"])

        failed_domains = {}
        for u in self.url_fetches:
            if not u.success:
                if u.domain not in failed_domains:
                    failed_domains[u.domain] = {"count": 0, "errors": []}
                failed_domains[u.domain]["count"] += 1
                if len(failed_domains[u.domain]["errors"]) < 3:
                    failed_domains[u.domain]["errors"].append({
                        "url": u.url[:80],
                        "error": u.error_type,
                    })

        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "success_rate": round(success / total, 4) if total > 0 else 0,
            "by_error_type": {k: len(v) for k, v in by_status.items() if k != "success"},
            "by_method": dict(by_method),
            "top_failed_domains": dict(sorted(failed_domains.items(), key=lambda x: -x[1]["count"])[:10]),
        }

    def _analyze_chunks(self) -> Dict[str, Any]:
        if not self.chunks:
            return {"total": 0}

        tiers = defaultdict(int)
        for c in self.chunks:
            tiers[c.tier] += 1

        scores = [c.relevance_score for c in self.chunks]
        by_domain = defaultdict(int)
        for c in self.chunks:
            by_domain[c.source_domain] += 1

        return {
            "total": len(self.chunks),
            "passed": sum(1 for c in self.chunks if c.tier != "rejected"),
            "tier_distribution": dict(tiers),
            "avg_relevance_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "unique_sources": len(by_domain),
            "top_sources": dict(sorted(by_domain.items(), key=lambda x: -x[1])[:10]),
        }

    def _analyze_claims(self) -> Dict[str, Any]:
        if not self.claims:
            return {"total": 0}

        verdicts = defaultdict(int)
        for c in self.claims:
            verdicts[c.verdict] += 1

        blocked = len([c for c in self.claims if c.was_blocked])
        scores = [c.best_entailment_score for c in self.claims]

        return {
            "total": len(self.claims),
            "supported": verdicts["supported"],
            "unsupported": verdicts["unsupported"],
            "contradiction": verdicts["contradiction"],
            "blocked": blocked,
            "hallucination_rate": round(
                (verdicts["unsupported"] + verdicts["contradiction"]) / len(self.claims), 4
            ) if self.claims else 0,
            "avg_entailment_score": round(sum(scores) / len(scores), 4) if scores else 0,
        }

    def _analyze_costs(self) -> Dict[str, Any]:
        if not self.llm_calls:
            return {"total_tokens": 0, "total_cost_usd": 0}

        by_phase = defaultdict(lambda: {"tokens": 0, "cost": 0, "calls": 0})
        for call in self.llm_calls:
            by_phase[call.phase]["tokens"] += call.total_tokens
            by_phase[call.phase]["cost"] += call.cost_usd
            by_phase[call.phase]["calls"] += 1

        by_purpose = defaultdict(lambda: {"tokens": 0, "cost": 0, "calls": 0})
        for call in self.llm_calls:
            by_purpose[call.purpose]["tokens"] += call.total_tokens
            by_purpose[call.purpose]["cost"] += call.cost_usd
            by_purpose[call.purpose]["calls"] += 1

        by_model = defaultdict(lambda: {"tokens": 0, "cost": 0, "calls": 0})
        for call in self.llm_calls:
            by_model[call.model]["tokens"] += call.total_tokens
            by_model[call.model]["cost"] += call.cost_usd
            by_model[call.model]["calls"] += 1

        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_calls": len(self.llm_calls),
            "budget_usd": self.budget_usd,
            "budget_remaining_usd": round(self.budget_usd - self.total_cost_usd, 4),
            "budget_utilization": round(self.total_cost_usd / self.budget_usd, 4) if self.budget_usd > 0 else 0,
            "by_phase": {k: {"tokens": v["tokens"], "cost_usd": round(v["cost"], 4), "calls": v["calls"]} for k, v in sorted(by_phase.items())},
            "by_purpose": {k: {"tokens": v["tokens"], "cost_usd": round(v["cost"], 4), "calls": v["calls"]} for k, v in sorted(by_purpose.items(), key=lambda x: -x[1]["cost"])},
            "by_model": {k: {"tokens": v["tokens"], "cost_usd": round(v["cost"], 4), "calls": v["calls"]} for k, v in by_model.items()},
        }

    def _analyze_memory(self) -> Dict[str, Any]:
        if not self.memory_states:
            return {}

        latest = self.memory_states[-1] if self.memory_states else None
        ops_by_type = defaultdict(int)
        for op in self.memory_operations:
            ops_by_type[op.operation_type] += 1

        cache_hits = len([c for c in self.cache_operations if c.hit])
        cache_total = len(self.cache_operations)

        return {
            "total_memory_operations": len(self.memory_operations),
            "operations_by_type": dict(ops_by_type),
            "latest_state": latest.to_dict() if latest else None,
            "cache_operations": cache_total,
            "cache_hit_rate": round(cache_hits / cache_total, 4) if cache_total > 0 else 0,
        }

    def _analyze_phases(self) -> Dict[str, Any]:
        phase_data = {}
        for k, v in sorted(self.phases.items()):
            phase_data[str(k)] = v.to_dict()

        # Find bottleneck
        bottleneck = None
        max_duration = 0
        for k, v in self.phases.items():
            if v.duration_seconds > max_duration:
                max_duration = v.duration_seconds
                bottleneck = k

        return {
            "phases": phase_data,
            "bottleneck_phase": bottleneck,
            "bottleneck_duration_seconds": max_duration,
            "total_duration_seconds": sum(p.duration_seconds for p in self.phases.values()),
        }

    def _identify_gaps(self, url_analysis, chunk_analysis, claim_analysis, cost_analysis) -> List[Dict]:
        gaps = []
        gap_id = 0

        # URL fetch gaps
        if url_analysis.get("success_rate", 0) < self.SOTA_TARGETS["min_url_success_rate"]:
            gap_id += 1
            gaps.append({
                "gap_id": f"GAP-{gap_id:03d}",
                "severity": "HIGH",
                "category": "url_fetch",
                "description": f"URL fetch success rate {url_analysis['success_rate']:.1%} below {self.SOTA_TARGETS['min_url_success_rate']:.0%}",
                "current_value": url_analysis["success_rate"],
                "target_value": self.SOTA_TARGETS["min_url_success_rate"],
                "recommendation": "Add fallback strategies for failed domains",
            })

        # Chunk gaps
        if chunk_analysis.get("passed", 0) < self.SOTA_TARGETS["min_chunks_passed"]:
            gap_id += 1
            gaps.append({
                "gap_id": f"GAP-{gap_id:03d}",
                "severity": "MEDIUM",
                "category": "chunk_quality",
                "description": f"Only {chunk_analysis.get('passed', 0)} chunks passed (target: {self.SOTA_TARGETS['min_chunks_passed']})",
                "current_value": chunk_analysis.get("passed", 0),
                "target_value": self.SOTA_TARGETS["min_chunks_passed"],
                "recommendation": "Improve search query diversity",
            })

        # Hallucination gaps
        hallucination_rate = claim_analysis.get("hallucination_rate", 1.0)
        if hallucination_rate > self.SOTA_TARGETS["max_hallucination_rate"]:
            gap_id += 1
            gaps.append({
                "gap_id": f"GAP-{gap_id:03d}",
                "severity": "CRITICAL",
                "category": "hallucination",
                "description": f"Hallucination rate {hallucination_rate:.1%} exceeds {self.SOTA_TARGETS['max_hallucination_rate']:.0%}",
                "current_value": hallucination_rate,
                "target_value": self.SOTA_TARGETS["max_hallucination_rate"],
                "recommendation": "Run P8 claim verification",
            })

        # Source diversity gaps
        unique_sources = chunk_analysis.get("unique_sources", 0)
        if unique_sources < self.SOTA_TARGETS["min_source_diversity"]:
            gap_id += 1
            gaps.append({
                "gap_id": f"GAP-{gap_id:03d}",
                "severity": "MEDIUM",
                "category": "source_diversity",
                "description": f"Only {unique_sources} unique sources (target: {self.SOTA_TARGETS['min_source_diversity']}+)",
                "current_value": unique_sources,
                "target_value": self.SOTA_TARGETS["min_source_diversity"],
                "recommendation": "Diversify search queries",
            })

        # Cost gaps
        if cost_analysis.get("total_cost_usd", 0) > self.SOTA_TARGETS["max_cost_usd"]:
            gap_id += 1
            gaps.append({
                "gap_id": f"GAP-{gap_id:03d}",
                "severity": "HIGH",
                "category": "cost",
                "description": f"Cost ${cost_analysis['total_cost_usd']:.2f} exceeds budget ${self.SOTA_TARGETS['max_cost_usd']:.2f}",
                "current_value": cost_analysis["total_cost_usd"],
                "target_value": self.SOTA_TARGETS["max_cost_usd"],
                "recommendation": "Optimize token usage or use cheaper models",
            })

        return gaps

    def _generate_recommendations(self, gaps: List[Dict]) -> List[str]:
        recommendations = []
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_gaps = sorted(gaps, key=lambda g: severity_order.get(g.get("severity", "LOW"), 99))

        for gap in sorted_gaps[:5]:
            recommendations.append(f"[{gap['severity']}] {gap['recommendation']}")

        if not recommendations:
            recommendations.append("All quality targets met.")

        return recommendations

    def _save_all_ledgers(self) -> None:
        """Save all detailed ledgers."""
        ledgers = {
            "constraints": [c.to_dict() for c in self.constraints],
            "decompositions": [d.to_dict() for d in self.decompositions],
            "queries": [q.to_dict() for q in self.queries],
            "search_results": [s.to_dict() for s in self.search_results],
            "url_fetches": [u.to_dict() for u in self.url_fetches],
            "chunks": [c.to_dict() for c in self.chunks],
            "memory_operations": [m.to_dict() for m in self.memory_operations],
            "memory_states": [m.to_dict() for m in self.memory_states],
            "nli_checks": [n.to_dict() for n in self.nli_checks],
            "retrievals": [r.to_dict() for r in self.retrievals],
            "generations": [g.to_dict() for g in self.generations],
            "claims": [c.to_dict() for c in self.claims],
            "qa_exchanges": [q.to_dict() for q in self.qa_exchanges],
            "gating_decisions": [g.to_dict() for g in self.gating_decisions],
            "identified_gaps": [g.to_dict() for g in self.identified_gaps],
            "citation_resolutions": [c.to_dict() for c in self.citation_resolutions],
            "report_sections": [s.to_dict() for s in self.report_sections],
            "llm_calls": [l.to_dict() for l in self.llm_calls],
            "cost_records": [c.to_dict() for c in self.cost_records],
            "cache_operations": [c.to_dict() for c in self.cache_operations],
        }

        for name, data in ledgers.items():
            if data:
                ledger_file = self.audit_dir / f"{name}_ledger.json"
                with open(ledger_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)

        print(f"[AUDIT] Ledgers saved to {self.audit_dir}")

    def _generate_markdown_report(self, report: Dict) -> None:
        """Generate comprehensive markdown audit report with full details."""
        md_lines = [
            f"# POLARIS Comprehensive Audit Report",
            f"",
            f"**Vector ID:** {self.vector_id}",
            f"**Run ID:** {self.run_id}",
            f"**Generated:** {report['meta']['generated_at']}",
            f"",
            f"---",
            f"",
            f"## 1. Executive Summary",
            f"",
        ]

        summary = report["summary"]
        md_lines.extend([
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Constraints | {summary.get('total_constraints', 0)} |",
            f"| Total Queries | {summary.get('total_queries', 0)} |",
            f"| URLs Attempted | {summary.get('total_urls_attempted', 0)} |",
            f"| URLs Successful | {summary.get('total_urls_successful', 0)} |",
            f"| Chunks Created | {summary.get('total_chunks_created', 0)} |",
            f"| Chunks Passed | {summary.get('total_chunks_passed', 0)} |",
            f"| Claims Verified | {summary.get('total_claims_verified', 0)} |",
            f"| Claims Supported | {summary.get('total_claims_supported', 0)} |",
            f"| Total Tokens | {summary.get('total_tokens', 0):,} |",
            f"| Total Cost | ${summary.get('total_cost_usd', 0):.4f} |",
            f"| Budget Utilization | {summary.get('budget_utilization', 0):.1%} |",
            f"",
        ])

        # Phase-by-Phase Breakdown
        md_lines.extend([
            f"---",
            f"",
            f"## 2. Phase-by-Phase Breakdown",
            f"",
        ])

        for phase_num, phase_data in sorted(self.phases.items()):
            phase_name = phase_data.phase_name or f"Phase {phase_num}"
            duration = (phase_data.duration_ms or 0) / 1000.0
            status = phase_data.status or "unknown"
            md_lines.extend([
                f"### Phase {phase_num}: {phase_name}",
                f"",
                f"- **Status:** {status}",
                f"- **Duration:** {duration:.2f}s",
            ])
            if phase_data.notes:
                md_lines.append(f"- **Notes:** {phase_data.notes}")
            md_lines.append(f"")

        # Chunk Analysis
        md_lines.extend([
            f"---",
            f"",
            f"## 3. Chunk Analysis",
            f"",
            f"### Summary",
            f"",
            f"| Tier | Count |",
            f"|------|-------|",
        ])

        tier_counts = {}
        for chunk in self.chunks:
            tier = chunk.tier or "unknown"
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        for tier, count in sorted(tier_counts.items()):
            md_lines.append(f"| {tier} | {count} |")

        md_lines.append(f"")

        if self.chunks:
            md_lines.extend([
                f"### Top Chunks by Relevance Score",
                f"",
                f"| Chunk ID | Source | Score | Tier |",
                f"|----------|--------|-------|------|",
            ])
            sorted_chunks = sorted(self.chunks, key=lambda c: c.score or 0, reverse=True)[:10]
            for chunk in sorted_chunks:
                url_short = (chunk.source_url[:40] + "...") if len(chunk.source_url or "") > 40 else (chunk.source_url or "N/A")
                md_lines.append(f"| {chunk.chunk_id} | {url_short} | {chunk.score or 0:.3f} | {chunk.tier or 'N/A'} |")
            md_lines.append(f"")

        # Claim Verification Details
        md_lines.extend([
            f"---",
            f"",
            f"## 4. Claim Verification Details",
            f"",
        ])

        if self.claims:
            supported = sum(1 for c in self.claims if c.verdict == "supported")
            partial = sum(1 for c in self.claims if c.verdict == "partial")
            rejected = sum(1 for c in self.claims if c.verdict in ("rejected", "unsupported", "contradiction"))
            blocked = sum(1 for c in self.claims if c.was_blocked)

            md_lines.extend([
                f"| Status | Count |",
                f"|--------|-------|",
                f"| Supported | {supported} |",
                f"| Partial | {partial} |",
                f"| Rejected | {rejected} |",
                f"| Blocked | {blocked} |",
                f"| **Total** | **{len(self.claims)}** |",
                f"",
            ])

            # Show rejected claims
            rejected_claims = [c for c in self.claims if c.verdict in ("rejected", "unsupported", "contradiction")]
            if rejected_claims:
                md_lines.extend([
                    f"### Rejected Claims",
                    f"",
                ])
                for claim in rejected_claims[:5]:  # Limit to 5
                    md_lines.append(f"- **{claim.claim_id}:** {claim.claim_text[:100]}...")
                    if claim.block_reason:
                        md_lines.append(f"  - Reason: {claim.block_reason}")
                md_lines.append(f"")
        else:
            md_lines.append(f"No claims verified.")
            md_lines.append(f"")

        # Cost Breakdown
        md_lines.extend([
            f"---",
            f"",
            f"## 5. Cost Breakdown",
            f"",
        ])

        if self.llm_calls:
            # Group by phase
            cost_by_phase = {}
            tokens_by_phase = {}
            for call in self.llm_calls:
                phase = call.phase
                cost_by_phase[phase] = cost_by_phase.get(phase, 0) + call.cost_usd
                tokens_by_phase[phase] = tokens_by_phase.get(phase, 0) + call.input_tokens + call.output_tokens

            md_lines.extend([
                f"### Cost by Phase",
                f"",
                f"| Phase | Tokens | Cost (USD) |",
                f"|-------|--------|------------|",
            ])
            for phase in sorted(cost_by_phase.keys()):
                md_lines.append(f"| P{phase} | {tokens_by_phase.get(phase, 0):,} | ${cost_by_phase[phase]:.4f} |")

            total_cost = sum(cost_by_phase.values())
            total_tokens = sum(tokens_by_phase.values())
            md_lines.append(f"| **Total** | **{total_tokens:,}** | **${total_cost:.4f}** |")
            md_lines.append(f"")

            # Top LLM calls by cost
            md_lines.extend([
                f"### Top LLM Calls by Cost",
                f"",
                f"| Phase | Purpose | Model | Tokens | Cost |",
                f"|-------|---------|-------|--------|------|",
            ])
            sorted_calls = sorted(self.llm_calls, key=lambda c: c.cost_usd, reverse=True)[:10]
            for call in sorted_calls:
                md_lines.append(f"| P{call.phase} | {call.purpose[:20]} | {call.model} | {call.input_tokens + call.output_tokens:,} | ${call.cost_usd:.4f} |")
            md_lines.append(f"")

        # Data Lineage
        md_lines.extend([
            f"---",
            f"",
            f"## 6. Data Lineage",
            f"",
        ])

        if self.citation_resolutions:
            md_lines.extend([
                f"### Citation Resolution Summary",
                f"",
                f"- **Total Citations Resolved:** {len(self.citation_resolutions)}",
                f"- **Successful:** {sum(1 for c in self.citation_resolutions if c.resolution_success)}",
                f"- **Failed:** {sum(1 for c in self.citation_resolutions if not c.resolution_success)}",
                f"",
            ])
        else:
            md_lines.append(f"No citation resolutions recorded.")
            md_lines.append(f"")

        # Memory Utilization
        md_lines.extend([
            f"---",
            f"",
            f"## 7. Memory Utilization",
            f"",
        ])

        if self.memory_operations:
            ops_by_tier = {}
            for op in self.memory_operations:
                tier = op.memory_tier
                ops_by_tier[tier] = ops_by_tier.get(tier, 0) + 1

            md_lines.extend([
                f"| Memory Tier | Operations |",
                f"|-------------|------------|",
            ])
            for tier, count in sorted(ops_by_tier.items()):
                md_lines.append(f"| {tier} | {count} |")
            md_lines.append(f"")

            if self.memory_states:
                latest_state = self.memory_states[-1]
                md_lines.extend([
                    f"### Final Memory State",
                    f"",
                    f"- **VWM Chunks:** {latest_state.vwm_chunks}",
                    f"- **LTM-Stage Chunks:** {latest_state.ltm_stage_chunks}",
                    f"- **LTM-Global Queries:** {latest_state.ltm_global_queries}",
                    f"- **Total Size:** {latest_state.total_size_mb:.2f} MB",
                    f"",
                ])
        else:
            md_lines.append(f"No memory operations recorded.")
            md_lines.append(f"")

        # Retrieval Analysis
        md_lines.extend([
            f"---",
            f"",
            f"## 8. Retrieval Analysis",
            f"",
        ])

        if self.retrievals:
            md_lines.extend([
                f"- **Total Retrievals:** {len(self.retrievals)}",
                f"- **Average Chunks Retrieved:** {sum(r.chunks_retrieved for r in self.retrievals) / len(self.retrievals):.1f}",
            ])
            if any(r.top_scores for r in self.retrievals):
                all_top_scores = [s for r in self.retrievals for s in (r.top_scores or [])]
                if all_top_scores:
                    md_lines.append(f"- **Average Top Score:** {sum(all_top_scores) / len(all_top_scores):.3f}")
            md_lines.append(f"")
        else:
            md_lines.append(f"No retrievals recorded.")
            md_lines.append(f"")

        # Gaps section
        gaps = report.get("gaps", [])
        if gaps:
            md_lines.extend([
                f"---",
                f"",
                f"## 9. Identified Gaps ({len(gaps)})",
                f"",
            ])
            for gap in gaps:
                md_lines.append(f"### [{gap['severity']}] {gap['gap_id']}: {gap['category']}")
                md_lines.append(f"")
                md_lines.append(f"**Description:** {gap['description']}")
                md_lines.append(f"")
                md_lines.append(f"**Current:** {gap['current_value']} | **Target:** {gap['target_value']}")
                md_lines.append(f"")
                md_lines.append(f"**Recommendation:** {gap['recommendation']}")
                md_lines.append(f"")

        # Recommendations
        recommendations = report.get("recommendations", [])
        if recommendations:
            md_lines.extend([
                f"---",
                f"",
                f"## 10. Recommendations",
                f"",
            ])
            for i, rec in enumerate(recommendations, 1):
                md_lines.append(f"{i}. {rec}")
            md_lines.append(f"")

        # Appendix: Error Log
        if self.errors:
            md_lines.extend([
                f"---",
                f"",
                f"## Appendix A: Errors ({len(self.errors)})",
                f"",
            ])
            for error in self.errors[:10]:  # Limit to 10
                md_lines.append(f"### Error at {error.timestamp}")
                md_lines.append(f"")
                md_lines.append(f"- **Phase:** {error.phase}")
                md_lines.append(f"- **Type:** {error.error_type}")
                md_lines.append(f"- **Message:** {error.message}")
                if error.stack_trace:
                    md_lines.append(f"")
                    md_lines.append(f"```")
                    md_lines.append(error.stack_trace[:500])
                    md_lines.append(f"```")
                md_lines.append(f"")

        # Footer
        md_lines.extend([
            f"---",
            f"",
            f"*Report generated by POLARIS Audit System v2.0*",
            f"",
        ])

        # Write markdown file
        md_file = self.audit_dir / "audit_report.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        print(f"[AUDIT] Comprehensive markdown report: {md_file}")

    def print_summary(self) -> None:
        """Print human-readable summary."""
        print(f"\n{'='*70}")
        print("AUDIT SUMMARY")
        print(f"Vector: {self.vector_id}")
        print(f"Run ID: {self.run_id}")
        print(f"{'='*70}")

        print(f"\n  PIPELINE COVERAGE")
        print(f"    Constraints: {len(self.constraints)}")
        print(f"    Queries: {len(self.queries)}")
        print(f"    Search Results: {len(self.search_results)}")
        print(f"    URL Fetches: {len(self.url_fetches)} ({sum(1 for u in self.url_fetches if u.success)} success)")
        print(f"    Chunks: {len(self.chunks)} ({sum(1 for c in self.chunks if c.tier != 'rejected')} passed)")
        print(f"    Memory Ops: {len(self.memory_operations)}")
        print(f"    NLI Checks: {len(self.nli_checks)}")
        print(f"    Retrievals: {len(self.retrievals)}")
        print(f"    Generations: {len(self.generations)}")
        print(f"    Claims: {len(self.claims)} ({sum(1 for c in self.claims if c.verdict == 'supported')} supported)")
        print(f"    QA Exchanges: {len(self.qa_exchanges)}")
        print(f"    Gaps Identified: {len(self.identified_gaps)}")
        print(f"    Citations Resolved: {len(self.citation_resolutions)}")

        print(f"\n  COSTS")
        print(f"    LLM Calls: {len(self.llm_calls)}")
        print(f"    Total Tokens: {self.total_tokens:,}")
        print(f"    Total Cost: ${self.total_cost_usd:.4f}")
        print(f"    Budget Remaining: ${self.budget_usd - self.total_cost_usd:.4f}")

        print(f"\n  AUDIT FILES: {self.audit_dir}")
        print(f"{'='*70}")


# =============================================================================
# GLOBAL AUDIT INSTANCE
# =============================================================================

_global_audit: Optional[AuditCollector] = None


def get_audit() -> Optional[AuditCollector]:
    """Get the global audit collector instance."""
    return _global_audit


def set_audit(audit: AuditCollector) -> None:
    """Set the global audit collector instance."""
    global _global_audit
    _global_audit = audit


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def run_audit(vector_id: str, save: bool = True) -> Dict[str, Any]:
    """Run audit from existing phase outputs."""
    from src.audit.runner_audit import RunnerAuditor

    auditor = RunnerAuditor(vector_id)
    auditor.load_all_phase_outputs()
    report = auditor.generate_comprehensive_report()
    auditor.print_summary()

    if save:
        output_path = auditor.save_report()
        print(f"\n  Report saved: {output_path}")

    return report


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="POLARIS Audit Collector")
    parser.add_argument("--vector-id", required=True, help="Vector ID to audit")
    parser.add_argument("--post-run", action="store_true", help="Run post-run analysis")

    args = parser.parse_args()

    if args.post_run:
        run_audit(args.vector_id)
    else:
        audit = AuditCollector(args.vector_id)
        print(f"Audit collector initialized for {args.vector_id}")
        print(f"Audit directory: {audit.audit_dir}")
