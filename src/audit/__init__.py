"""
POLARIS Audit Module - Complete Quality Assurance
==================================================
Comprehensive audit system covering ALL phases (P0-P12).

Record Types:
- P0: ConstraintRecord, VectorParseRecord
- P1: DecompositionRecord
- P2: QueryRecord, QueryGenerationRecord
- P3: SearchResultRecord, SearchExecutionRecord
- P4: URLFetchRecord, ChunkRecord
- P5: MemoryOperationRecord, MemoryStateRecord
- P6: NLICheckRecord, IntegrityCheckRecord
- P7: RetrievalRecord, GenerationRecord, RAGRecord
- P7.5: ClaimRecord
- P8: QARecord, AdversarialQARecord
- P9: GatingDecisionRecord
- P10: IdentifiedGapRecord, GapAnalysisRecord
- P11: CitationResolutionRecord, ReportSectionRecord, CitationPackagingRecord
- P12: FinalOutputRecord
- Cross-cutting: LLMCallRecord, PhaseRecord, CostRecord, CacheOperationRecord

Usage:
    from src.audit import AuditCollector, get_audit, set_audit

    audit = AuditCollector(vector_id)
    set_audit(audit)
    audit.start_run()

    # P0: Log constraints
    audit.log_constraint(type, text, source, ...)
    audit.log_vector_parse(...)

    # P2: Log queries
    audit.log_query(text, type, constraints, ...)
    audit.log_query_generation_complete(...)

    # P3: Log search results
    audit.log_search_result(query_id, engine, url, ...)
    audit.log_search_execution(query_id, ...)

    # P4: Log URL fetches and chunks
    audit.log_url_fetch(url, method, status, success, ...)
    audit.log_chunk(chunk_id, source_url, text, score, ...)

    # P5: Log memory operations
    audit.log_memory_operation(type, tier, chunk_id, ...)
    audit.log_memory_state(vwm_count, ...)

    # P6: Log NLI checks
    audit.log_nli_check(chunk_a, chunk_b, scores, ...)
    audit.log_integrity_check_complete(...)

    # P7: Log RAG operations
    audit.log_retrieval(query, tier, chunks, ...)
    audit.log_generation(type, chunks, tokens, ...)
    audit.log_rag_complete(...)

    # P7.5: Log claims
    audit.log_claim(claim_id, text, verdict, ...)

    # P8: Log QA
    audit.log_qa_exchange(type, question, answer, ...)
    audit.log_adversarial_qa_complete(...)

    # P9: Log gating
    audit.log_gating_decision(case, scores, reasoning, ...)

    # P10: Log gaps
    audit.log_identified_gap(type, description, severity, ...)
    audit.log_gap_analysis_complete(...)

    # P11: Log citations
    audit.log_citation_resolution(token, chunk_id, url, ...)
    audit.log_report_section(title, word_count, ...)
    audit.log_citation_packaging_complete(...)

    # P12: Log final output
    audit.log_final_output(type, metrics, ...)

    # Cross-cutting
    audit.log_llm_call(phase, purpose, model, tokens, cost, ...)
    audit.log_cache_operation(operation, type, key, hit, ...)
    audit.start_phase(phase_num, name, ...)
    audit.end_phase(phase_num, status, ...)

    audit.end_run()
    report = audit.generate_report()
"""

from src.audit.benchmark_audit import (
    BenchmarkAuditor,
    BenchmarkResult,
    RAGASMetrics,
    ClaimVerification,
    HallucinationResult,
    run_benchmark_audit,
)

from src.audit.collector import (
    # Main collector
    AuditCollector,
    GeminiContentAnalyzer,
    get_audit,
    set_audit,
    run_audit,
    # P0 records
    ConstraintRecord,
    VectorParseRecord,
    # P1 records
    DecompositionRecord,
    # P2 records
    QueryRecord,
    QueryGenerationRecord,
    # P3 records
    SearchResultRecord,
    SearchExecutionRecord,
    # P4 records
    URLFetchRecord,
    ChunkRecord,
    # P5 records
    MemoryOperationRecord,
    MemoryStateRecord,
    # P6 records
    NLICheckRecord,
    IntegrityCheckRecord,
    # P7 records
    RetrievalRecord,
    GenerationRecord,
    RAGRecord,
    # P7.5 records
    ClaimRecord,
    # P8 records
    QARecord,
    AdversarialQARecord,
    # P9 records
    GatingDecisionRecord,
    # P10 records
    IdentifiedGapRecord,
    GapAnalysisRecord,
    # P11 records
    CitationResolutionRecord,
    ReportSectionRecord,
    CitationPackagingRecord,
    # P12 records
    FinalOutputRecord,
    # Cross-cutting records
    LLMCallRecord,
    PhaseRecord,
    CostRecord,
    CacheOperationRecord,
)

from src.audit.runner_audit import (
    RunnerAuditor,
)

from src.audit.automated_deep_audit import (
    AutomatedDeepAudit,
)

__all__ = [
    # Main collector
    "AuditCollector",
    "GeminiContentAnalyzer",
    "get_audit",
    "set_audit",
    "run_audit",
    # P0 records
    "ConstraintRecord",
    "VectorParseRecord",
    # P1 records
    "DecompositionRecord",
    # P2 records
    "QueryRecord",
    "QueryGenerationRecord",
    # P3 records
    "SearchResultRecord",
    "SearchExecutionRecord",
    # P4 records
    "URLFetchRecord",
    "ChunkRecord",
    # P5 records
    "MemoryOperationRecord",
    "MemoryStateRecord",
    # P6 records
    "NLICheckRecord",
    "IntegrityCheckRecord",
    # P7 records
    "RetrievalRecord",
    "GenerationRecord",
    "RAGRecord",
    # P7.5 records
    "ClaimRecord",
    # P8 records
    "QARecord",
    "AdversarialQARecord",
    # P9 records
    "GatingDecisionRecord",
    # P10 records
    "IdentifiedGapRecord",
    "GapAnalysisRecord",
    # P11 records
    "CitationResolutionRecord",
    "ReportSectionRecord",
    "CitationPackagingRecord",
    # P12 records
    "FinalOutputRecord",
    # Cross-cutting records
    "LLMCallRecord",
    "PhaseRecord",
    "CostRecord",
    "CacheOperationRecord",
    # Benchmark audit
    "BenchmarkAuditor",
    "BenchmarkResult",
    "RAGASMetrics",
    "ClaimVerification",
    "HallucinationResult",
    "run_benchmark_audit",
    # Runner audit
    "RunnerAuditor",
    # Automated deep audit
    "AutomatedDeepAudit",
]
