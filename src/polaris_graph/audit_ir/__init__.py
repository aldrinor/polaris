"""Audit Graph IR — canonical claim-evidence-contradiction representation.

The Audit IR is the single source of truth that the Evidence Inspector
renders. Every derivative renderer (PDF, DOCX, CSV, charts, brief, deck)
must project from this IR and retain back-links to claim IDs.

This module loads a V30 Phase-2 run artifact directory and emits a
unified, immutable AuditIR object.
"""

from src.polaris_graph.audit_ir.job_queue import (
    ALLOWED_TRANSITIONS,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    Job,
    JobQueue,
    JobQueueError,
    job_to_dict,
)
from src.polaris_graph.audit_ir.job_runner import (
    JobControl,
    JobRunner,
    MockJobRunner,
    get_runner,
    list_runners,
    register_runner,
)
from src.polaris_graph.audit_ir.job_worker import JobWorker
from src.polaris_graph.audit_ir.v30_runner import (
    V30JobRunner,
    V30RunnerConfig,
    make_default_v30_runner,
)
from src.polaris_graph.audit_ir.template_catalog import (
    CuratedTemplate,
    TEMPLATE_CATALOG,
    get_template,
    list_catalog,
)
from src.polaris_graph.audit_ir.template_classifier import (
    DEFAULT_FLOOR_HIGH,
    DEFAULT_FLOOR_REVIEW,
    RouterConfig,
    RoutingCandidate,
    RoutingResult,
    RoutingVerdict,
    classify_query,
)
from src.polaris_graph.audit_ir.provenance import (
    PdfSpan,
    SheetCell,
    SlideRegion,
    TextSpan,
    Timecode,
    UploadProvenance,
)
from src.polaris_graph.audit_ir.workspace_store import (
    BoundedError,
    DEFAULT_MAX_DOCS_PER_WORKSPACE,
    Upload,
    Workspace,
    WorkspaceStateError,
    WorkspaceStore,
    WorkspaceStoreError,
    upload_to_dict,
    workspace_to_dict,
)
from src.polaris_graph.audit_ir.parser_runner import (
    ParserError,
    ParserRunner,
    ParseResult,
    PdfParser,
    TextParser,
    select_parser,
)
from src.polaris_graph.audit_ir.corpus_retriever import (
    DEFAULT_TOP_K,
    DEFAULT_MIN_SCORE,
    RetrievedChunk,
    retrieve_chunks,
)
from src.polaris_graph.audit_ir.corpus_brief import (
    BriefCitation,
    BriefParagraph,
    CorpusBrief,
    LlmClient,
    OpenRouterBriefClient,
    brief_to_dict,
    compose_brief,
)
from src.polaris_graph.audit_ir.progress_surfaces import (
    SurfaceBus,
    SurfaceEvent,
    SurfaceKind,
    get_surface_bus,
)
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
    "ALLOWED_TRANSITIONS",
    "DEFAULT_FLOOR_HIGH",
    "DEFAULT_FLOOR_REVIEW",
    "IR_SCHEMA_VERSION",
    "JOB_STATUSES",
    "TEMPLATE_CATALOG",
    "TERMINAL_STATUSES",
    "CuratedTemplate",
    "Job",
    "JobControl",
    "JobQueue",
    "JobQueueError",
    "JobRunner",
    "JobWorker",
    "MockJobRunner",
    "RouterConfig",
    "RoutingCandidate",
    "RoutingResult",
    "RoutingVerdict",
    "V30JobRunner",
    "V30RunnerConfig",
    "classify_query",
    "get_template",
    "list_catalog",
    "make_default_v30_runner",
    "get_runner",
    "job_to_dict",
    "list_runners",
    "register_runner",
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
