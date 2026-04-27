"""M-D1 precision metrics + benchmark runner.

Given an InductorProtocol implementation + a ValidationSet, run the
inductor against every case and aggregate four metrics:

  precision: in-scope cases where match_score >= tau / total in-scope
    accepted decisions
  silent_disagreement_rate: in-scope cases accepted by inductor where
    match_score < tau / total in-scope (this is the dangerous case —
    inductor confidently produced a wrong contract)
  abstain_recall: cases the inductor correctly abstained on
    (ambiguous + out_of_scope where inductor abstained) / total
    cases that should abstain
  operator_review_load: total abstains / total cases (the "human-
    review load" the system places on operators)

Acceptance per M-D1:
  precision >= 0.8
  silent_disagreement_rate <= 0.05
  abstain_recall >= 0.95
  operator_review_load <= 0.30
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.polaris_graph.auto_induction.benchmark_loader import (
    ValidationCase,
    ValidationSet,
)
from src.polaris_graph.auto_induction.contract_compare import (
    ContractComparison,
    compare_contracts,
)


@dataclass(frozen=True)
class InductorVerdict:
    """One inductor's response to one query.

    `decision` is either:
      - "accept": inductor produced a contract (`induced_contract`
        non-None), implying it had high enough confidence.
      - "abstain": inductor declined to produce a contract; the
        runtime should fall back to operator review.
    """

    decision: str  # "accept" or "abstain"
    induced_contract: Any | None  # ReportContract or compatible
    confidence: float | None = None
    abstain_reason: str | None = None


class InductorProtocol(Protocol):
    """The inductor contract M-D2 will implement.

    M-D1 ships only the harness; M-D2 will provide the actual
    implementation.
    """

    def induce(self, query: str) -> InductorVerdict:
        ...


@dataclass(frozen=True)
class PrecisionMetrics:
    """Aggregated benchmark metrics."""

    total_cases: int
    in_scope_total: int
    in_scope_accepted: int
    in_scope_match_at_tau: int
    in_scope_silent_disagreements: int
    abstain_should_abstain_total: int
    abstain_correct: int
    abstain_total: int

    @property
    def precision(self) -> float:
        if self.in_scope_accepted == 0:
            return 0.0
        return self.in_scope_match_at_tau / self.in_scope_accepted

    @property
    def silent_disagreement_rate(self) -> float:
        if self.in_scope_total == 0:
            return 0.0
        return self.in_scope_silent_disagreements / self.in_scope_total

    @property
    def abstain_recall(self) -> float:
        if self.abstain_should_abstain_total == 0:
            return 1.0  # vacuous
        return self.abstain_correct / self.abstain_should_abstain_total

    @property
    def operator_review_load(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.abstain_total / self.total_cases

    def passes_acceptance(
        self,
        *,
        precision_floor: float = 0.80,
        silent_disagreement_ceiling: float = 0.05,
        abstain_recall_floor: float = 0.95,
        operator_review_ceiling: float = 0.30,
    ) -> bool:
        return (
            self.precision >= precision_floor
            and self.silent_disagreement_rate <= silent_disagreement_ceiling
            and self.abstain_recall >= abstain_recall_floor
            and self.operator_review_load <= operator_review_ceiling
        )


@dataclass(frozen=True)
class BenchmarkResult:
    """One full run of the benchmark."""

    metrics: PrecisionMetrics
    case_results: tuple[
        tuple[ValidationCase, InductorVerdict, ContractComparison | None],
        ...,
    ] = field(default_factory=tuple)


def _load_curator_contract(slug: str) -> Any:
    """Load a curator-reviewed contract by slug. Lazy import to keep
    the auto_induction package decoupled from the V30 substrate when
    that substrate isn't on the import path."""
    from pathlib import Path

    from src.polaris_graph.nodes.report_contract import (
        load_report_contract_for_slug,
    )

    template_path = (
        Path(__file__).resolve().parents[3]
        / "config" / "scope_templates" / "clinical.yaml"
    )
    contract = load_report_contract_for_slug(template_path, slug)
    if contract is None:
        # Try other domains.
        for domain in ("policy", "tech", "due_diligence", "custom"):
            alt = (
                Path(__file__).resolve().parents[3]
                / "config" / "scope_templates" / f"{domain}.yaml"
            )
            if alt.exists():
                contract = load_report_contract_for_slug(alt, slug)
                if contract is not None:
                    return contract
        raise ValueError(
            f"curator contract slug not found in any template: {slug!r}"
        )
    return contract


def run_benchmark(
    inductor: InductorProtocol,
    validation_set: ValidationSet,
    *,
    tau: float = 0.80,
) -> BenchmarkResult:
    """Run an inductor against the validation set, aggregate metrics."""
    case_results: list[
        tuple[ValidationCase, InductorVerdict, ContractComparison | None]
    ] = []

    in_scope_total = len(validation_set.in_scope)
    in_scope_accepted = 0
    in_scope_match_at_tau = 0
    in_scope_silent_disagreements = 0
    abstain_should_abstain_total = (
        len(validation_set.ambiguous) + len(validation_set.out_of_scope)
    )
    abstain_correct = 0
    abstain_total = 0

    for case in validation_set.all_cases:
        verdict = inductor.induce(case.query)

        if verdict.decision == "abstain":
            abstain_total += 1
            if case.expected_action == "abstain":
                abstain_correct += 1
            case_results.append((case, verdict, None))
            continue

        # decision == "accept"
        if case.group == "in_scope":
            in_scope_accepted += 1
            assert case.curator_contract_slug is not None
            curator = _load_curator_contract(case.curator_contract_slug)
            cmp = compare_contracts(
                curator, verdict.induced_contract,
            )
            if cmp.match_score >= tau:
                in_scope_match_at_tau += 1
            else:
                in_scope_silent_disagreements += 1
            case_results.append((case, verdict, cmp))
        else:
            # Inductor accepted a case it should have abstained on.
            # No comparison meaningful (no curator contract for
            # ambiguous/out_of_scope).
            case_results.append((case, verdict, None))

    metrics = PrecisionMetrics(
        total_cases=validation_set.total,
        in_scope_total=in_scope_total,
        in_scope_accepted=in_scope_accepted,
        in_scope_match_at_tau=in_scope_match_at_tau,
        in_scope_silent_disagreements=in_scope_silent_disagreements,
        abstain_should_abstain_total=abstain_should_abstain_total,
        abstain_correct=abstain_correct,
        abstain_total=abstain_total,
    )

    return BenchmarkResult(
        metrics=metrics,
        case_results=tuple(case_results),
    )
