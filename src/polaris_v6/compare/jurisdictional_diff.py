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
    """Claim diff between two jurisdictions' runs of the same question.

    Labels a single ``ClaimDiffReport`` with the pair of jurisdictions it
    compares.
    """

    left_jurisdiction: str
    right_jurisdiction: str
    claim_diff: ClaimDiffReport


@dataclass(frozen=True)
class JurisdictionalDiffReport:
    """All pairwise jurisdictional claim diffs for one question.

    Carries the shared ``question``, the sorted list of ``jurisdictions``, and
    one ``JurisdictionalDiffPair`` per unordered jurisdiction pair.
    """

    question: str
    jurisdictions: list[str]
    pairs: list[JurisdictionalDiffPair]


def compute_jurisdictional_diff(
    contracts: dict[str, EvidenceContract],
) -> JurisdictionalDiffReport:
    """Compute pairwise claim diffs across jurisdictions of one question.

    Runs :func:`compute_claim_diff` on every unordered pair of the given
    jurisdiction-keyed contracts. All contracts must answer the identical
    question (compared after stripping whitespace).

    Args:
        contracts: Map of jurisdiction label to its EvidenceContract.

    Returns:
        A ``JurisdictionalDiffReport`` with one pair per jurisdiction
        combination, ordered by sorted jurisdiction keys.

    Raises:
        ValueError: If fewer than two contracts are given, or if the contracts
            do not all share an identical question.
    """
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
