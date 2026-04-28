"""M-D1 (Phase D): Auto-induction precision benchmark + abstain criterion.

Phase D auto-induction is the highest-risk milestone in the FINAL_PLAN.
Before any inductor (M-D2) is built, we need a validation harness that
measures whether a candidate inductor reproduces curator-reviewed
contracts. Per the M-D1 acceptance criteria (Codex review revised):

  Precision: induced_contract.match_score(curator_contract) >= tau
    on in-scope validation queries (>= 80%, <= 5% silent disagreement).

  Abstain recall: correct_abstains / queries_that_should_abstain
    on out-of-scope validation queries (>= 95%).

  Operator-review load: queries_routed_to_humans / total
    on a representative query mix (<= 30%).

The validation set must include AMBIGUOUS queries (intent unclear)
and OUT-OF-SCOPE queries (not clinical, not in supported template
space) as negatives — the failure mode is silent misframing, not
just low contract-match score.

This package contains:
  - benchmark_loader: load + validate the M-D1 validation set
  - contract_compare: structural contract-match scoring
  - precision_metrics: precision / abstain-precision / abstain-recall /
    operator-review-load aggregation
  - cli: `python -m src.polaris_graph.auto_induction.cli`

The inductor itself (M-D2) plugs into this package via the
InductorProtocol. M-D1 ships only the harness — no inductor yet.
"""

from __future__ import annotations

from src.polaris_graph.auto_induction.benchmark_loader import (
    ValidationCase,
    ValidationSet,
    load_validation_set,
)
from src.polaris_graph.auto_induction.contract_compare import (
    ContractComparison,
    compare_contracts,
)
from src.polaris_graph.auto_induction.precision_metrics import (
    BenchmarkResult,
    InductorProtocol,
    InductorVerdict,
    InductorVerdictError,
    PrecisionMetrics,
    run_benchmark,
)

__all__ = [
    "BenchmarkResult",
    "ContractComparison",
    "InductorProtocol",
    "InductorVerdict",
    "InductorVerdictError",
    "PrecisionMetrics",
    "ValidationCase",
    "ValidationSet",
    "compare_contracts",
    "load_validation_set",
    "run_benchmark",
]
