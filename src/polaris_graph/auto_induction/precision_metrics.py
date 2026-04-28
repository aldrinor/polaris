"""M-D1 precision metrics + benchmark runner.

Given an InductorProtocol implementation + a ValidationSet, run the
inductor against every case and aggregate five metrics:

  precision: in-scope cases where match_score >= tau / total in-scope
    accepted decisions
  silent_disagreement_rate: in-scope cases accepted by inductor where
    match_score < tau / total in-scope (this is the dangerous case —
    inductor confidently produced a wrong contract)
  abstain_recall: cases the inductor correctly abstained on
    (ambiguous + out_of_scope where inductor abstained) / total
    cases that should abstain
  abstain_precision (Codex round-1 fix): correct abstentions /
    total abstentions — high precision means few in-scope cases
    are needlessly routed to operator review.
  operator_review_load: total abstains / total cases (the "human-
    review load" the system places on operators)

Acceptance per M-D1:
  precision >= 0.8
  silent_disagreement_rate <= 0.05
  abstain_recall >= 0.95
  abstain_precision >= 0.80
  operator_review_load <= 0.30
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import yaml

from src.polaris_graph.auto_induction.benchmark_loader import (
    ValidationCase,
    ValidationSet,
)
from src.polaris_graph.auto_induction.contract_compare import (
    ContractComparison,
    compare_contracts,
)


# Codex round-1 review fix: decision was an unvalidated str. Now a
# Literal so type-checkers + runtime validation enforce the contract.
DecisionLiteral = Literal["accept", "abstain"]


class InductorVerdictError(ValueError):
    """Raised when an InductorVerdict is malformed."""


@dataclass(frozen=True)
class InductorVerdict:
    """One inductor's response to one query.

    `decision` is either:
      - "accept": inductor produced a contract (`induced_contract`
        non-None), implying it had high enough confidence.
      - "abstain": inductor declined to produce a contract; the
        runtime should fall back to operator review.

    Codex round-1 review fix: validate decision + enforce shape
    invariants. Previously any non-'abstain' string was treated as
    accept silently.
    """

    decision: str
    induced_contract: Any | None = None
    confidence: float | None = None
    abstain_reason: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in ("accept", "abstain"):
            raise InductorVerdictError(
                f"InductorVerdict.decision must be 'accept' or 'abstain', "
                f"got {self.decision!r}"
            )
        if self.decision == "accept" and self.induced_contract is None:
            raise InductorVerdictError(
                "InductorVerdict.decision='accept' requires non-None "
                "induced_contract"
            )
        if self.decision == "abstain" and self.induced_contract is not None:
            raise InductorVerdictError(
                "InductorVerdict.decision='abstain' must have None "
                "induced_contract (got an object)"
            )
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise InductorVerdictError(
                f"InductorVerdict.confidence must be in [0,1] when set; "
                f"got {self.confidence}"
            )


class InductorProtocol(Protocol):
    """The inductor contract M-D2 will implement.

    M-D1 ships only the harness; M-D2 will provide the actual
    implementation.
    """

    def induce(self, query: str) -> InductorVerdict:
        ...


@dataclass(frozen=True)
class PrecisionMetrics:
    """Aggregated benchmark metrics.

    Codex round-1 review fix: added abstain_precision to the metric
    pack. Phase D plan requires it; round-1 of M-D1 acceptance
    explicitly listed both abstain precision AND recall.
    """

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
    def abstain_precision(self) -> float:
        """Of all abstentions, how many were correct?

        Low abstain_precision means the inductor over-abstains —
        routing in-scope cases to operator review needlessly. The
        Phase D round-1 acceptance explicitly named abstain
        precision/recall as separate metrics; this implements the
        precision side.
        """
        if self.abstain_total == 0:
            return 1.0  # vacuous (no abstentions, all correct trivially)
        return self.abstain_correct / self.abstain_total

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
        abstain_precision_floor: float = 0.80,
        operator_review_ceiling: float = 0.30,
    ) -> bool:
        return (
            self.precision >= precision_floor
            and self.silent_disagreement_rate <= silent_disagreement_ceiling
            and self.abstain_recall >= abstain_recall_floor
            and self.abstain_precision >= abstain_precision_floor
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
    that substrate isn't on the import path.

    Codex round-1 review fix: previously passed `Path` to
    `load_report_contract_for_slug` but the M-54 loader expects a
    parsed dict (see report_contract.py:181-201 — it returns None
    on non-dict template). Result: every in-scope case crashed.
    Fix: load the YAML to a dict first.
    """
    from pathlib import Path

    from src.polaris_graph.nodes.report_contract import (
        load_report_contract_for_slug,
    )

    config_root = (
        Path(__file__).resolve().parents[3]
        / "config" / "scope_templates"
    )
    # Try each known scope-template file; first hit wins.
    for domain_yaml in config_root.glob("*.yaml"):
        try:
            with domain_yaml.open("r", encoding="utf-8") as fp:
                template_dict = yaml.safe_load(fp)
        except Exception:
            continue
        contract = load_report_contract_for_slug(template_dict, slug)
        if contract is not None:
            return contract
    raise ValueError(
        f"curator contract slug not found in any template under "
        f"{config_root}: {slug!r}"
    )


def run_benchmark(
    inductor: InductorProtocol,
    validation_set: ValidationSet,
    *,
    tau: float = 0.80,
    confidence_threshold: float | None = None,
) -> BenchmarkResult:
    """Run an inductor against the validation set, aggregate metrics.

    Codex round-1 review fix: confidence is now actionable. If
    `confidence_threshold` is set and the inductor's verdict has
    `confidence < threshold`, the verdict is treated as `abstain`
    even if `decision='accept'`. This makes M-D2 calibration
    sweepable: try threshold=0.5, 0.7, 0.9 and pick whichever
    minimizes silent-disagreement-rate without exceeding the
    operator-review-load ceiling.
    """
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
        raw_verdict = inductor.induce(case.query)

        # Codex round-1: confidence threshold downgrades accept to abstain.
        # Codex M-D2 round-1: store the EFFECTIVE verdict in
        # case_results when downgrading, so downstream consumers see
        # consistent (verdict.decision, comparison) tuples. Previously
        # case_results stored raw verdict (decision='accept') alongside
        # comparison=None for downgraded cases, which was confusing.
        effective_decision = raw_verdict.decision
        if (
            raw_verdict.decision == "accept"
            and confidence_threshold is not None
            and raw_verdict.confidence is not None
            and raw_verdict.confidence < confidence_threshold
        ):
            effective_decision = "abstain"

        if effective_decision == "abstain":
            abstain_total += 1
            if case.expected_action == "abstain":
                abstain_correct += 1
            # If raw was accept but downgraded, build a synthetic
            # abstain verdict so case_results reflects what was
            # actually counted in the metrics.
            if raw_verdict.decision != "abstain":
                effective_verdict = InductorVerdict(
                    decision="abstain",
                    confidence=raw_verdict.confidence,
                    abstain_reason=(
                        f"confidence_threshold downgrade: "
                        f"{raw_verdict.confidence:.3f} < "
                        f"{confidence_threshold}"
                    ),
                )
            else:
                effective_verdict = raw_verdict
            case_results.append((case, effective_verdict, None))
            continue

        # decision == "accept"
        if case.group == "in_scope":
            in_scope_accepted += 1
            assert case.curator_contract_slug is not None
            curator = _load_curator_contract(case.curator_contract_slug)
            cmp = compare_contracts(
                curator, raw_verdict.induced_contract,
            )
            if cmp.match_score >= tau:
                in_scope_match_at_tau += 1
            else:
                in_scope_silent_disagreements += 1
            case_results.append((case, raw_verdict, cmp))
        else:
            # Inductor accepted a case it should have abstained on.
            # No comparison meaningful (no curator contract for
            # ambiguous/out_of_scope).
            case_results.append((case, raw_verdict, None))

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
