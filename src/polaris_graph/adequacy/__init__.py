"""Plan-sufficiency gate package (I-meta-005 Phase 3, #987).

The MONEY-TRAP fix: the legacy `nodes/corpus_adequacy_gate.py` gate is
domain-keyed AND aggregate-count only, so a broad-but-shallow corpus PASSES,
BILLS the generator, then leaves planned sub-questions uncovered. This package
re-defines adequacy as "does the corpus cover EVERY planned sub-question to its
per-section evidence target, at the numeric authority floor?" — held at
EXPAND/abort BEFORE a single generator token is billed.

Behind `PG_USE_RESEARCH_PLANNER` (default off); OFF is byte-identical (the
legacy `assess_corpus_adequacy` domain-keyed gate is retained + selected when
off). The gate is a PURE function over already-retrieved rows + the pinned plan
+ the per-row authority sidecar — no network, no LLM, spend-free.
"""
from src.polaris_graph.adequacy.plan_sufficiency_gate import (
    PlanSufficiencyReport,
    UnitCoverage,
    assess_plan_sufficiency,
    relevant_section_indices,
)

__all__ = [
    "PlanSufficiencyReport",
    "UnitCoverage",
    "assess_plan_sufficiency",
    "relevant_section_indices",
]
