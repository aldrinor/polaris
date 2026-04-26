"""Audit Graph IR — canonical claim-evidence-contradiction representation.

The Audit IR is the single source of truth that the Evidence Inspector
renders. Every derivative renderer (PDF, DOCX, CSV, charts, brief, deck)
must project from this IR and retain back-links to claim IDs.

This module loads a V30 Phase-2 run artifact directory and emits a
unified, immutable AuditIR object.
"""

from src.polaris_graph.audit_ir.loader import (
    IR_SCHEMA_VERSION,
    AdequacyGate,
    AuditIR,
    AuditIRSchemaError,
    BibliographyEntry,
    ContradictionClaim,
    ContradictionCluster,
    CorpusApprovalGate,
    EvaluatorGate,
    EvidenceSpanToken,
    FrameCoverageEntry,
    FrameCoverageReport,
    ModelProvenance,
    ProtocolMetadata,
    ReportSection,
    ReportSentence,
    RetrievalAttempt,
    RetrievalStats,
    RuleCheck,
    RunManifest,
    TierExpectation,
    TierMix,
    VerifiedReport,
    load_audit_ir,
)

__all__ = [
    "IR_SCHEMA_VERSION",
    "AdequacyGate",
    "AuditIR",
    "AuditIRSchemaError",
    "BibliographyEntry",
    "ContradictionClaim",
    "ContradictionCluster",
    "CorpusApprovalGate",
    "EvaluatorGate",
    "EvidenceSpanToken",
    "FrameCoverageEntry",
    "FrameCoverageReport",
    "ModelProvenance",
    "ProtocolMetadata",
    "ReportSection",
    "ReportSentence",
    "RetrievalAttempt",
    "RetrievalStats",
    "RuleCheck",
    "RunManifest",
    "TierExpectation",
    "TierMix",
    "VerifiedReport",
    "load_audit_ir",
]
