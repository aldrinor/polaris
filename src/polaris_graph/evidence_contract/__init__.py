"""Evidence Contract Gate (ECG) — pre-generation expectation contract.

This module defines what an operator expects a research run to address
BEFORE generation runs. Distinct from `polaris_v6.schemas.evidence_contract`
which describes the post-run artifact (run output).
"""

from polaris_graph.evidence_contract.gate import (
    ContractRequiredError,
    GateVerdict,
    JURISDICTION_DOMAINS,
    assert_generation_has_contract,
    evaluate_contract,
)
from polaris_graph.evidence_contract.schema import (
    EvidenceContract,
    EvidenceContractError,
    ExpectedClaim,
    ExpectedEntity,
    ExpectedSourceCoverage,
    Jurisdiction,
)

__all__ = [
    "ContractRequiredError",
    "EvidenceContract",
    "EvidenceContractError",
    "ExpectedClaim",
    "ExpectedEntity",
    "ExpectedSourceCoverage",
    "GateVerdict",
    "JURISDICTION_DOMAINS",
    "Jurisdiction",
    "assert_generation_has_contract",
    "evaluate_contract",
]
