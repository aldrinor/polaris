"""I-f12-004 — jurisdictional diff. Pairwise compute_claim_diff across
EvidenceContract bundles for the SAME question run in different
jurisdictions; surfaces per-pair claim diffs labeled by jurisdiction."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from polaris_v6.compare.claim_diff import ClaimDiffReport, compute_claim_diff
from polaris_v6.schemas.evidence_contract import EvidenceContract


@dataclass(frozen=True)
class JurisdictionalDiffPair:
    left_jurisdiction: str
    right_jurisdiction: str
    claim_diff: ClaimDiffReport


@dataclass(frozen=True)
class JurisdictionalDiffReport:
    question: str
    jurisdictions: list[str]
    pairs: list[JurisdictionalDiffPair]


def compute_jurisdictional_diff(
    contracts: dict[str, EvidenceContract],
) -> JurisdictionalDiffReport:
    if len(contracts) < 2:
        raise ValueError("jurisdictional diff requires >= 2 contracts")
    questions = {c.question.strip() for c in contracts.values()}
    if len(questions) != 1:
        raise ValueError(
            "jurisdictional diff requires identical question across contracts; "
            f"got {len(questions)} distinct"
        )
    jurisdictions = sorted(contracts.keys())
    pairs: list[JurisdictionalDiffPair] = []
    for left, right in combinations(jurisdictions, 2):
        pairs.append(
            JurisdictionalDiffPair(
                left_jurisdiction=left,
                right_jurisdiction=right,
                claim_diff=compute_claim_diff(contracts[left], contracts[right]),
            )
        )
    return JurisdictionalDiffReport(
        question=next(iter(questions)),
        jurisdictions=jurisdictions,
        pairs=pairs,
    )
