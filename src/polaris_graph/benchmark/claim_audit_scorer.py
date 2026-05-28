"""Two-lane claim-audit scorer for the DR head-to-head (I-safety-002b / #925).

REPLACES the §-1.1-banned/rigged `beat_both_scorer.py` + `dimension_scorers.py` (count /
pattern / string-match scoring + POLARIS auto-win dimensions). This scorer is a PURE
AGGREGATOR over the reconciled per-claim audit LEDGER produced by the Claude+Codex dual
§-1.1 line-by-line audit (claim → fetched cited span → verdict). It assigns NO verdicts
itself and gives POLARIS no free pass — every system's ledger is scored identically.

Lane 1 = claim faithfulness (against the FETCHED cited span).
Lane 2 = pre-registered gold-rubric coverage (independent sources), each covered point
         itself citation-supported — so a terse report cannot win on faithfulness alone.

Pure logic; fixture-tested with no model. Per plan `.codex/I-safety-002b/execution_plan_pathB.md`
§5/§6 (Codex APPROVE iter 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["VERIFIED", "PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE"]
Severity = Literal["S0", "S1", "S2", "S3"]
UnreachableSubtype = Literal["paywall", "robots", "fetch_failure", "source_missing"]

# Material = decision-relevant (S0-S2). S3 is observe-only, NOT scored (plan §5).
_MATERIAL_SEVERITIES = ("S0", "S1", "S2")
# "unsupported-or-worse" verdicts that count against faithfulness.
_BAD_VERDICTS = ("PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE")
_PARTIAL_WEIGHT = 0.5  # pre-registered (plan §5)
_COVERAGE_THRESHOLD = 0.70  # literal, frozen (plan §5)


@dataclass
class ClaimRow:
    """One reconciled audit verdict for one atomic claim (from the dual line-by-line)."""

    claim_id: str
    severity: Severity
    verdict: Verdict
    citation_id: str | None        # the citation the claim attaches to (None = uncited)
    span_quote: str | None         # exact supporting/refuting span from the FETCHED source
    unreachable_subtype: UnreachableSubtype | None = None

    def __post_init__(self) -> None:
        if self.verdict == "UNREACHABLE" and self.unreachable_subtype is None:
            raise ValueError(f"{self.claim_id}: UNREACHABLE requires an unreachable_subtype")
        if self.verdict != "UNREACHABLE" and self.unreachable_subtype is not None:
            raise ValueError(f"{self.claim_id}: unreachable_subtype only valid for UNREACHABLE")
        # every non-VERIFIED material verdict must carry span evidence or an uncited marker
        if self.verdict in ("FABRICATED", "PARTIAL") and not self.span_quote:
            raise ValueError(f"{self.claim_id}: {self.verdict} requires a span_quote (evidence)")

    @property
    def is_material(self) -> bool:
        return self.severity in _MATERIAL_SEVERITIES


@dataclass
class RubricElement:
    """One pre-registered gold-rubric required element (from independent sources)."""

    element_id: str
    covered: bool             # did the report cover this required element?
    citation_supported: bool  # AND is the covered point itself citation-supported?


def lane1_faithfulness(rows: list[ClaimRow]) -> dict:
    """S0-S2 material unsupported-or-worse rate + per-verdict breakdown. Positive = bad."""
    material = [r for r in rows if r.is_material]
    denom = len(material)
    counts: dict[str, int] = {v: 0 for v in ("VERIFIED", *_BAD_VERDICTS)}
    for r in material:
        counts[r.verdict] += 1
    # PARTIAL weighted 0.5; UNSUPPORTED/FABRICATED/UNREACHABLE full weight.
    weighted_bad = (
        counts["UNSUPPORTED"] + counts["FABRICATED"] + counts["UNREACHABLE"]
        + _PARTIAL_WEIGHT * counts["PARTIAL"]
    )
    rate = (weighted_bad / denom) if denom else 0.0
    return {
        "material_atoms": denom,
        "verdict_counts": counts,
        "weighted_unsupported_or_worse": weighted_bad,
        "unsupported_or_worse_rate": rate,
        "hard_fail_count": counts["UNSUPPORTED"] + counts["FABRICATED"],  # the gating verdicts
        "observed_S3_excluded": sum(1 for r in rows if r.severity == "S3"),
    }


def lane2_coverage(rubric: list[RubricElement]) -> dict:
    """Covered-AND-citation-supported / total required elements (plan §5/§6)."""
    total = len(rubric)
    covered_supported = sum(1 for e in rubric if e.covered and e.citation_supported)
    covered_only = sum(1 for e in rubric if e.covered)
    frac = (covered_supported / total) if total else 0.0
    return {
        "total_required": total,
        "covered": covered_only,
        "covered_and_citation_supported": covered_supported,
        "coverage_fraction": frac,
        "missing": [e.element_id for e in rubric if not (e.covered and e.citation_supported)],
    }


def system_passes_question(rows: list[ClaimRow], rubric: list[RubricElement]) -> dict:
    """A system PASSES a question iff zero S0-S2 FABRICATED/UNSUPPORTED material claims AND
    coverage >= 0.70 (plan §5). Returns the verdict + the reasons (every gate explicit)."""
    l1 = lane1_faithfulness(rows)
    l2 = lane2_coverage(rubric)
    zero_hard_fail = l1["hard_fail_count"] == 0
    meets_coverage = l2["coverage_fraction"] >= _COVERAGE_THRESHOLD
    passed = zero_hard_fail and meets_coverage
    reasons = []
    if not zero_hard_fail:
        reasons.append(f"{l1['hard_fail_count']} S0-S2 FABRICATED/UNSUPPORTED material claim(s)")
    if not meets_coverage:
        reasons.append(f"coverage {l2['coverage_fraction']:.2f} < {_COVERAGE_THRESHOLD}")
    return {"passed": passed, "reasons": reasons, "lane1": l1, "lane2": l2}


@dataclass
class SystemQuestionLedger:
    """The scored audit ledger for one (system × question). NOT a 'BEAT-BOTH' scoreboard."""

    system: str         # "polaris" | "chatgpt" | "gemini" | "perplexity"
    question_id: str
    rows: list[ClaimRow]
    rubric: list[RubricElement]
    result: dict = field(init=False)

    def __post_init__(self) -> None:
        self.result = system_passes_question(self.rows, self.rubric)


def aggregate(ledgers: list[SystemQuestionLedger]) -> dict:
    """Per-system aggregate across questions. Every number traces to claim/span evidence in
    the per-(system×question) ledgers; NO cross-system 'wins' headline (plan §8)."""
    by_system: dict[str, dict] = {}
    for lg in ledgers:
        s = by_system.setdefault(lg.system, {"questions": 0, "passed": 0, "rates": [], "hard_fails": 0})
        s["questions"] += 1
        s["passed"] += int(lg.result["passed"])
        s["rates"].append(lg.result["lane1"]["unsupported_or_worse_rate"])
        s["hard_fails"] += lg.result["lane1"]["hard_fail_count"]
    for s in by_system.values():
        s["mean_unsupported_or_worse_rate"] = (sum(s["rates"]) / len(s["rates"])) if s["rates"] else 0.0
    return {"by_system": by_system, "n_ledgers": len(ledgers), "note": "pilot; per-claim traceable; not a superiority claim"}
