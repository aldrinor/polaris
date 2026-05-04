"""EvidencePool schema for slice 002 (clinical retrieval).

Per `.codex/slices/slice_002/architecture_proposal.md` §"Data contracts".
Defines the canonical Pydantic types produced by the slice 002 clinical
retriever and consumed by future slice 003 generation:

    ScopeDecision (slice 001)
        ↓
    process_retrieval()  (slice 002 — orchestrator, later PR)
        ↓
    EvidencePool (this module)
        ↓
    [slice 003 generator — future]

Pure-types module: no I/O, no network, no LLM calls. Validation only.

Slice 002 lives in `polaris_graph.retrieval2` (note the `2`) to keep
clear separation from the heritage `polaris_graph.retrieval` substrate
(live_retriever, source_registry, etc.) which serves the legacy honest-
rebuild pipeline. The two coexist by design per PLAN.md §4.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ---------------------------------------------------------------------------
# Source tier enum
# ---------------------------------------------------------------------------

class SourceTier(str, Enum):
    """Three-tier source classification per architecture proposal.

    T1 — regulatory + Cochrane systematic reviews. Highest evidentiary weight.
    T2 — peer-reviewed primary research (RCTs, cohort studies, meta-analyses).
    T3 — registries, clinical guidelines, government health agencies.
    """

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

class Source(BaseModel):
    """A single retrieved clinical source.

    `full_text` is None at retrieval time and populated lazily by the
    fetcher when downstream stages need the body. `snippet` is always
    populated (first ~500 chars of relevant section) so quick adequacy
    + tier classification can run without a second HTTP round-trip.
    """

    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: HttpUrl
    domain: str = Field(min_length=1, max_length=255)
    tier: SourceTier
    title: str = Field(min_length=1, max_length=1000)
    publication_date: date | None = None
    authors: list[str] = Field(default_factory=list, max_length=200)
    snippet: str = Field(min_length=0, max_length=2000)
    full_text_available: bool = False
    full_text: str | None = None
    fetched_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domain")
    @classmethod
    def _domain_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("authors")
    @classmethod
    def _authors_no_blanks(cls, v: list[str]) -> list[str]:
        return [a.strip() for a in v if a and a.strip()]


# ---------------------------------------------------------------------------
# Adequacy verdict
# ---------------------------------------------------------------------------

class AdequacyVerdict(BaseModel):
    """Output of the corpus adequacy gate.

    `is_adequate=True` ⇒ pool may flow to slice 003 generation.
    `is_adequate=False` + `failure_reason` populated ⇒ pipeline aborts
    upstream of generation; UI surfaces the failure_reason verbatim.
    """

    is_adequate: bool
    sources_per_tier: dict[SourceTier, int] = Field(default_factory=dict)
    min_required_per_tier: dict[SourceTier, int] = Field(default_factory=dict)
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _check_failure_reason_consistency(self) -> "AdequacyVerdict":
        if self.is_adequate is False and not self.failure_reason:
            raise ValueError(
                "failure_reason is required when is_adequate=False"
            )
        if self.is_adequate is True and self.failure_reason:
            raise ValueError(
                "failure_reason must be None when is_adequate=True"
            )
        return self


# ---------------------------------------------------------------------------
# EvidencePool
# ---------------------------------------------------------------------------

class EvidencePool(BaseModel):
    """The slice 002 output. Bound to a specific ScopeDecision via decision_id.

    `pool_id` is fresh per retrieval run; `decision_id` is the FK back to
    the slice 001 ScopeDecision that triggered retrieval. Same decision +
    same retrieval call may produce different pools across runs (sources
    move, registries update); pool_id distinguishes them.
    """

    pool_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str = Field(min_length=1)
    sources: list[Source] = Field(default_factory=list)
    adequacy: AdequacyVerdict
    queries_executed: list[str] = Field(default_factory=list, max_length=50)
    retrieval_started_at_utc: datetime
    retrieval_finished_at_utc: datetime
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)

    @field_validator("retrieval_finished_at_utc")
    @classmethod
    def _finished_after_started(cls, v: datetime, info) -> datetime:
        started = info.data.get("retrieval_started_at_utc")
        if started is not None and v < started:
            raise ValueError(
                "retrieval_finished_at_utc must be >= retrieval_started_at_utc"
            )
        return v

    def sources_by_tier(self, tier: SourceTier) -> list[Source]:
        return [s for s in self.sources if s.tier == tier]


# ---------------------------------------------------------------------------
# Retrieval error (parallel to slice 001's IntakeError)
# ---------------------------------------------------------------------------

class RetrievalError(BaseModel):
    """Returned when retrieval cannot run (e.g. ScopeDecision rejects it).

    Distinct from `EvidencePool { adequacy: { is_adequate: False } }`,
    which signals retrieval ran but produced an inadequate corpus.
    """

    error: bool = True
    code: str  # 'wrong_status' | 'wrong_scope_class' | 'fetch_backend_unavailable'
    message: str
    decision_id: str | None = None
