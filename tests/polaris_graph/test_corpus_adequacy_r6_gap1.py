"""
R-6 Gap-1 regression tests: corpus-adequacy gate.
"""
from __future__ import annotations

from src.polaris_graph.nodes.corpus_adequacy_gate import (
    AdequacyThresholds,
    assess_corpus_adequacy,
)


def test_adequate_clinical_corpus_proceeds() -> None:
    r = assess_corpus_adequacy(
        tier_counts={"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 1, "T6": 1},
        evidence_row_count=9,
        domain="clinical",
    )
    assert r.decision == "proceed"


def test_t1_deficient_clinical_corpus_aborts() -> None:
    # 0 T1 is critically below the min of 3
    r = assess_corpus_adequacy(
        tier_counts={"T4": 5, "T5": 3, "T6": 2},
        evidence_row_count=6,
        domain="clinical",
    )
    assert r.decision == "abort"
    failing = [f.name for f in r.findings if f.severity == "critical"]
    assert "t1_count" in failing


def test_industry_dominated_corpus_aborts() -> None:
    # 80% T5/T6 — far over the 50% cap
    r = assess_corpus_adequacy(
        tier_counts={"T1": 1, "T5": 5, "T6": 3},
        evidence_row_count=9,
        domain="clinical",
    )
    # low_quality_fraction = 8/9 ≈ 0.89, > 0.50 * 1.5 = 0.75 → critical
    assert r.decision == "abort"


def test_borderline_corpus_expands() -> None:
    # T1=2 (min is 3, so warn-but-not-critical since >= 1.5)
    # ... but 2 is between 1.5 (critical threshold) and 3 (the target), so warn.
    r = assess_corpus_adequacy(
        tier_counts={"T1": 2, "T2": 2, "T3": 3, "T4": 2, "T5": 1},
        evidence_row_count=10,
        domain="clinical",
    )
    # Expect expand (warns but no critical)
    assert r.decision == "expand"


def test_policy_corpus_with_t3_dominance_proceeds() -> None:
    # Policy template values regulatory (T3) heavily
    r = assess_corpus_adequacy(
        tier_counts={"T3": 6, "T1": 1, "T2": 1, "T6": 2},
        evidence_row_count=10,
        domain="policy",
    )
    assert r.decision == "proceed"


def test_tech_has_looser_thresholds() -> None:
    # Tech should proceed with T1+T2 >= 2 even if T4 dominates;
    # clinical would fail the same corpus because it demands more T1+T2.
    tier_counts = {"T1": 2, "T2": 0, "T4": 3, "T6": 2}
    clinical_r = assess_corpus_adequacy(
        tier_counts=tier_counts, evidence_row_count=6, domain="clinical",
    )
    tech_r = assess_corpus_adequacy(
        tier_counts=tier_counts, evidence_row_count=6, domain="tech",
    )
    # Clinical: T1=2 (below min 3), T1+T2=2 (below min 5) → expand or abort
    assert clinical_r.decision in ("abort", "expand")
    # Tech: T1=2 >= min 1, T1+T2=2 >= min 2, total=7 >= min 6 → proceed
    assert tech_r.decision == "proceed"


def test_evidence_row_count_below_threshold() -> None:
    # Enough sources but evidence filtered down below min_evidence_rows
    r = assess_corpus_adequacy(
        tier_counts={"T1": 3, "T2": 3, "T3": 2, "T4": 2},
        evidence_row_count=2,
        domain="clinical",
    )
    # Thin evidence (2 < min 6 → warn or critical)
    assert r.decision in ("abort", "expand")
    ev_finding = next(f for f in r.findings if f.name == "evidence_rows")
    assert ev_finding.ok is False


def test_override_thresholds_honored() -> None:
    thr = AdequacyThresholds(
        min_total_sources=2, min_t1_count=0,
        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
        min_evidence_rows=1,
        max_t5_plus_t6_fraction=1.0, max_t7_fraction=1.0,
    )
    r = assess_corpus_adequacy(
        tier_counts={"T5": 3, "T6": 2},
        evidence_row_count=1,
        domain="clinical",
        override=thr,
    )
    assert r.decision == "proceed"


def test_protocol_override_honored() -> None:
    protocol = {
        "corpus_adequacy": {
            "min_total_sources": 4,
            "min_t1_count": 1,
        }
    }
    r = assess_corpus_adequacy(
        tier_counts={"T1": 1, "T2": 1, "T4": 2},
        evidence_row_count=4,
        domain="clinical",
        protocol=protocol,
    )
    # Below default clinical thresholds but within protocol override
    # Should PROCEED on the overridden thresholds
    # (though other thresholds might still warn)
    # At minimum, t1_count and min_total_sources should be OK
    t1_finding = next(f for f in r.findings if f.name == "t1_count")
    assert t1_finding.ok is True
    total_finding = next(f for f in r.findings if f.name == "total_sources")
    assert total_finding.ok is True


def test_adequate_corpus_has_no_notes() -> None:
    r = assess_corpus_adequacy(
        tier_counts={"T1": 5, "T2": 5, "T3": 3},
        evidence_row_count=12,
        domain="clinical",
    )
    assert r.decision == "proceed"
    assert r.notes == []


def test_aborted_corpus_has_helpful_note() -> None:
    r = assess_corpus_adequacy(
        tier_counts={"T7": 5},
        evidence_row_count=2,
        domain="clinical",
    )
    assert r.decision == "abort"
    assert len(r.notes) >= 1
    assert "critical" in r.notes[0].lower()
