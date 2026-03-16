"""
POLARIS Schemas - The Law
=========================
Pydantic models that define the contract between phases.
"""

from src.schemas.phase_models import (
    # Enums
    PhaseStatus,
    GatingCase,
    RelevanceTier,
    ConfidenceBand,
    OutputType,
    VerificationStatus,

    # Common models
    Citation,
    Claim,
    SearchResult,
    ChunkMetadata,

    # Phase outputs
    Phase0Input,
    Phase0Output,
    Phase1Output,
    Phase2Output,
    Phase3Output,
    Phase4Output,
    Phase5Output,
    Phase6Output,
    Phase7Output,
    Phase9Output,
    Phase10Output,
    Phase11Output,
    Phase12Output,
    Phase13Output,

    # Other models
    LedgerEntry,
    ResearchReport,
    Vector,
    WorkQueueItem,
    WorkQueue,
)

__all__ = [
    "PhaseStatus",
    "GatingCase",
    "RelevanceTier",
    "ConfidenceBand",
    "OutputType",
    "VerificationStatus",
    "Citation",
    "Claim",
    "SearchResult",
    "ChunkMetadata",
    "Phase0Input",
    "Phase0Output",
    "Phase1Output",
    "Phase2Output",
    "Phase3Output",
    "Phase4Output",
    "Phase5Output",
    "Phase6Output",
    "Phase7Output",
    "Phase9Output",
    "Phase10Output",
    "Phase11Output",
    "Phase12Output",
    "Phase13Output",
    "LedgerEntry",
    "ResearchReport",
    "Vector",
    "WorkQueueItem",
    "WorkQueue",
]
