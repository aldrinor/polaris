"""Pre-generation evidence-expectation contract (I-ecg-001).

Operator declares, BEFORE a research run starts, what entities + claims
+ jurisdictions + source-coverage the eventual report MUST address.
I-ecg-002 enforces (gates generation against this contract).

DO NOT confuse with `polaris_v6.schemas.evidence_contract.EvidenceContract`
which is the post-run artifact (run output). Different concepts; same
class name acceptable since import paths disambiguate.

Jurisdiction is geographic (CA / US / EU / UK / GLOBAL). The mapping
from regulatory-agency codes (FDA / EMA / NICE / HC / MHRA / TGA) to
these jurisdictions is owned by I-ecg-002 (gate enforcement layer).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Jurisdiction(str, Enum):
    CA = "CA"
    US = "US"
    EU = "EU"
    UK = "UK"
    GLOBAL = "GLOBAL"


EntityType = Literal["drug", "condition", "intervention", "population", "outcome"]


class ExpectedEntity(BaseModel):
    """A named entity (drug, condition, intervention, etc.) the report MUST address."""

    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    entity_type: EntityType


class ExpectedClaim(BaseModel):
    """A claim the report MUST make a verdict on."""

    claim_id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1, max_length=1000)
    expected_entities: list[str] = Field(min_length=1, max_length=20)
    required_jurisdictions: list[Jurisdiction] = Field(min_length=1)


class ExpectedSourceCoverage(BaseModel):
    """Minimum source counts per evidence-tier the report MUST cite."""

    tier_t1_min: int = Field(ge=0, le=100)
    tier_t2_min: int = Field(ge=0, le=100)
    tier_t3_min: int = Field(ge=0, le=100)


class EvidenceContract(BaseModel):
    """Top-level expectation contract bound to one research question."""

    contract_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contract_version: Literal["1.0"] = "1.0"
    research_question: str = Field(min_length=1, max_length=2000)
    expected_entities: list[ExpectedEntity] = Field(min_length=1, max_length=50)
    expected_claims: list[ExpectedClaim] = Field(min_length=1, max_length=50)
    expected_source_coverage: ExpectedSourceCoverage
    jurisdictions: list[Jurisdiction] = Field(min_length=1, max_length=10)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _internal_consistency(self) -> "EvidenceContract":
        names = [e.name for e in self.expected_entities]
        if len(set(names)) != len(names):
            dups = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate entity name(s): {dups}")
        ids = [c.claim_id for c in self.expected_claims]
        if len(set(ids)) != len(ids):
            dups = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate claim_id(s): {dups}")
        declared = set(names)
        contract_jurs = set(self.jurisdictions)
        for claim in self.expected_claims:
            for ref in claim.expected_entities:
                if ref not in declared:
                    raise ValueError(
                        f"claim {claim.claim_id!r} references undeclared entity {ref!r}"
                    )
            extra = set(claim.required_jurisdictions) - contract_jurs
            if extra:
                raise ValueError(
                    f"claim {claim.claim_id!r} required_jurisdictions {sorted(j.value for j in extra)} "
                    f"not in contract jurisdictions"
                )
        return self


class EvidenceContractError(BaseModel):
    """Returned when a contract fails validation (parallel to other slice errors)."""

    error: bool = True
    code: str
    message: str
    contract_id: str | None = None
