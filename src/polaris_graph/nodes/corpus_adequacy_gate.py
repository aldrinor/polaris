"""
Corpus-adequacy gate — HONEST-REBUILD R-6 Gap-1.

Decides whether the retrieved+classified corpus is strong enough for
synthesis. Prevents the silent failure mode where the pipeline ships a
150-word report with a "13/13 rule checks pass" badge even though the
corpus had 3 T1 sources and a 400-word report is misleadingly brief.

DECISION SPACE:
    PROCEED: corpus meets domain thresholds; synthesize normally
    EXPAND:  corpus short of thresholds but close; run a second
             retrieval round with broader queries (caller decides)
    ABORT:   corpus is too thin for confident synthesis; caller should
             either abort, ask the user to approve a short report, or
             widen retrieval significantly

DOES NOT MAKE NETWORK CALLS. Pure function — tier counts + thresholds.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger("polaris_graph.corpus_adequacy_gate")


AdequacyDecision = Literal["proceed", "expand", "abort"]


@dataclass
class AdequacyThresholds:
    """Per-domain thresholds for corpus adequacy.

    Loaded from the scope template's `corpus_adequacy` block. Callers
    can also provide overrides.
    """
    min_total_sources: int = 8
    min_t1_count: int = 2            # at least 2 peer-reviewed primary
    min_t1_plus_t2: int = 3          # or 3 combined T1+T2+T3
    min_t1_plus_t2_plus_t3: int = 3
    min_evidence_rows: int = 5       # after content-starved filter
    max_t5_plus_t6_fraction: float = 0.70   # too much industry/commentary = abort
    max_t7_fraction: float = 0.50           # too many stubs = abort
    # Fraction-of-threshold below which we ABORT instead of EXPAND
    abort_if_below_fraction: float = 0.5


@dataclass
class AdequacyFinding:
    name: str
    ok: bool
    observed: float
    threshold: float
    severity: str   # "ok" | "warn" | "critical"


@dataclass
class CorpusAdequacyReport:
    decision: AdequacyDecision
    findings: list[AdequacyFinding] = field(default_factory=list)
    total_sources: int = 0
    tier_counts: dict[str, int] = field(default_factory=dict)
    evidence_rows: int = 0
    notes: list[str] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)


_DEFAULT_DOMAIN_THRESHOLDS: dict[str, AdequacyThresholds] = {
    "clinical": AdequacyThresholds(
        min_total_sources=10, min_t1_count=3,
        min_t1_plus_t2=5, min_t1_plus_t2_plus_t3=6,
        min_evidence_rows=6,
        max_t5_plus_t6_fraction=0.50,
        max_t7_fraction=0.40,
    ),
    "policy": AdequacyThresholds(
        min_total_sources=8, min_t1_count=1,
        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=5,  # T3 regulatory dominates
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.60,
        max_t7_fraction=0.40,
    ),
    "tech": AdequacyThresholds(
        min_total_sources=6, min_t1_count=1,
        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=2,
        min_evidence_rows=4,
        max_t5_plus_t6_fraction=0.60,
        max_t7_fraction=0.50,
    ),
    "due_diligence": AdequacyThresholds(
        min_total_sources=8, min_t1_count=1,
        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=3,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.70,
        max_t7_fraction=0.40,
    ),
}


def _get_thresholds(
    domain: str,
    protocol: dict[str, Any] | None = None,
    override: AdequacyThresholds | None = None,
) -> AdequacyThresholds:
    """Resolve adequacy thresholds with override > protocol > default."""
    if override is not None:
        return override
    # Protocol may carry a corpus_adequacy block
    if protocol:
        ca = protocol.get("corpus_adequacy") or {}
        if ca:
            base = _DEFAULT_DOMAIN_THRESHOLDS.get(domain, AdequacyThresholds())
            # Merge: take protocol values where present
            return AdequacyThresholds(
                min_total_sources=int(ca.get("min_total_sources", base.min_total_sources)),
                min_t1_count=int(ca.get("min_t1_count", base.min_t1_count)),
                min_t1_plus_t2=int(ca.get("min_t1_plus_t2", base.min_t1_plus_t2)),
                min_t1_plus_t2_plus_t3=int(ca.get("min_t1_plus_t2_plus_t3", base.min_t1_plus_t2_plus_t3)),
                min_evidence_rows=int(ca.get("min_evidence_rows", base.min_evidence_rows)),
                max_t5_plus_t6_fraction=float(ca.get("max_t5_plus_t6_fraction", base.max_t5_plus_t6_fraction)),
                max_t7_fraction=float(ca.get("max_t7_fraction", base.max_t7_fraction)),
                abort_if_below_fraction=float(ca.get("abort_if_below_fraction", base.abort_if_below_fraction)),
            )
    return _DEFAULT_DOMAIN_THRESHOLDS.get(domain, AdequacyThresholds())


def assess_corpus_adequacy(
    *,
    tier_counts: dict[str, int],
    evidence_row_count: int,
    domain: str,
    protocol: dict[str, Any] | None = None,
    override: AdequacyThresholds | None = None,
) -> CorpusAdequacyReport:
    """Return an AdequacyReport for the retrieved corpus.

    Args:
        tier_counts: dict mapping "T1"/"T2"/.../"T7"/"UNKNOWN" -> count.
        evidence_row_count: number of evidence rows AFTER content-starved
            filtering (Fix-D).
        domain: clinical / policy / tech / due_diligence.
        protocol: dict form of protocol.json (may carry adequacy overrides).
        override: explicit AdequacyThresholds, wins over all else.
    """
    thr = _get_thresholds(domain, protocol, override)

    total = sum(tier_counts.values())
    t1 = tier_counts.get("T1", 0)
    t2 = tier_counts.get("T2", 0)
    t3 = tier_counts.get("T3", 0)
    t5 = tier_counts.get("T5", 0)
    t6 = tier_counts.get("T6", 0)
    t7 = tier_counts.get("T7", 0)

    findings: list[AdequacyFinding] = []

    def _record(name: str, observed: float, threshold: float,
                direction: str, critical_at: float | None = None) -> None:
        if direction == "min":
            ok = observed >= threshold
            # below 50% of threshold = critical
            if critical_at is None:
                critical_at = threshold * thr.abort_if_below_fraction
            severity = ("ok" if ok else
                        "critical" if observed <= critical_at else
                        "warn")
        else:  # "max"
            ok = observed <= threshold
            # 1.5x over = critical
            if critical_at is None:
                critical_at = threshold * 1.5
            severity = ("ok" if ok else
                        "critical" if observed >= critical_at else
                        "warn")
        findings.append(AdequacyFinding(
            name=name, ok=ok, observed=observed,
            threshold=threshold, severity=severity,
        ))

    _record("total_sources", total, thr.min_total_sources, "min")
    _record("t1_count", t1, thr.min_t1_count, "min")
    _record("t1_plus_t2", t1 + t2, thr.min_t1_plus_t2, "min")
    _record("t1_plus_t2_plus_t3", t1 + t2 + t3,
            thr.min_t1_plus_t2_plus_t3, "min")
    _record("evidence_rows", evidence_row_count,
            thr.min_evidence_rows, "min")

    low_quality_fraction = (t5 + t6) / max(total, 1)
    _record("low_quality_fraction",
            low_quality_fraction, thr.max_t5_plus_t6_fraction, "max")

    t7_fraction = t7 / max(total, 1)
    _record("t7_fraction", t7_fraction, thr.max_t7_fraction, "max")

    critical_count = sum(1 for f in findings if f.severity == "critical")
    warn_count = sum(1 for f in findings if f.severity == "warn")

    if critical_count > 0:
        decision: AdequacyDecision = "abort"
    elif warn_count > 0:
        decision = "expand"
    else:
        decision = "proceed"

    notes: list[str] = []
    if decision == "abort":
        failing = [f.name for f in findings if f.severity == "critical"]
        notes.append(
            f"Corpus fails {len(failing)} critical threshold(s): {failing}. "
            f"Refusing to synthesize a confident report; caller should "
            f"expand retrieval substantially or ABORT."
        )
    elif decision == "expand":
        warning = [f.name for f in findings if f.severity == "warn"]
        notes.append(
            f"Corpus below nominal on {len(warning)} threshold(s): {warning}. "
            f"Synthesis possible but caller is encouraged to trigger a "
            f"second retrieval round before proceeding."
        )

    return CorpusAdequacyReport(
        decision=decision,
        findings=findings,
        total_sources=total,
        tier_counts=dict(tier_counts),
        evidence_rows=evidence_row_count,
        notes=notes,
        thresholds=asdict(thr),
    )
