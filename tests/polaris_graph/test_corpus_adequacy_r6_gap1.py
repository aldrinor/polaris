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


# ---------------------------------------------------------------------------
# GH#405 I-tpl-009: corpus-threshold calibration for emerging-policy domains.
# ---------------------------------------------------------------------------

def test_ai_sovereignty_emerging_policy_proceeds() -> None:
    """Q1 actual tier counts (from outputs/I-beat-001_round_q1) used to
    pass under emerging-policy thresholds (min_t1=0, T3+T4+T6 floor=4)."""
    r = assess_corpus_adequacy(
        tier_counts={"T3": 2, "T4": 5, "T6": 5, "UNKNOWN": 1},
        evidence_row_count=13,
        domain="ai_sovereignty",
    )
    assert r.decision in ("proceed", "expand"), (
        f"expected proceed/expand for ai_sovereignty emerging-policy, "
        f"got {r.decision}: {r.notes}"
    )
    finding_names = {f.name for f in r.findings}
    assert "t3_plus_t4_plus_t6" in finding_names, (
        "new GH#405 finding must be emitted"
    )


def test_canada_us_emerging_policy_proceeds() -> None:
    """Q2 actual tier counts used to verify canada_us domain."""
    r = assess_corpus_adequacy(
        tier_counts={"T3": 1, "T4": 7, "T5": 2, "T6": 4, "T7": 2, "UNKNOWN": 4},
        evidence_row_count=19,
        domain="canada_us",
    )
    assert r.decision in ("proceed", "expand"), (
        f"expected proceed/expand for canada_us, got {r.decision}: {r.notes}"
    )


def test_workforce_t4_only_proceeds() -> None:
    """Q3 actual: T4=7, UNKNOWN=1 (no T1/T2/T3). Must proceed for
    workforce because gov-stats agencies (StatsCan, OECD) surface as T4
    in current classifier — see GH#406 follow-up."""
    r = assess_corpus_adequacy(
        tier_counts={"T4": 7, "UNKNOWN": 1},
        evidence_row_count=8,
        domain="workforce",
    )
    assert r.decision in ("proceed", "expand"), (
        f"T4-only workforce evidence must pass, got {r.decision}: {r.notes}"
    )


def test_housing_policy_proceeds_after_relax() -> None:
    """Q4 housing/policy actual counts. Pre-GH#405 this aborted on
    min_t1=1 + min_t1_plus_t2_plus_t3=5. After relax: passes via
    min_t3_plus_t4_plus_t6=5 floor."""
    r = assess_corpus_adequacy(
        tier_counts={"T3": 1, "T4": 13, "T6": 2, "T7": 3, "UNKNOWN": 1},
        evidence_row_count=19,
        domain="policy",
    )
    assert r.decision in ("proceed", "expand"), (
        f"housing/policy must pass after GH#405 relax, got {r.decision}: {r.notes}"
    )


def test_clinical_still_strict_regression() -> None:
    """Regression: clinical domain must still demand T1+T2 even after
    the GH#405 changes."""
    r = assess_corpus_adequacy(
        tier_counts={"T3": 5, "T4": 5},  # 10 sources but T1=0, T2=0
        evidence_row_count=10,
        domain="clinical",
    )
    assert r.decision == "abort", (
        "clinical T1=0/T2=0 must still abort (regression check)"
    )
    failing = {f.name for f in r.findings if f.severity == "critical"}
    assert "t1_count" in failing


def test_protocol_override_t3_plus_t4_plus_t6() -> None:
    """Protocol passthrough for the new field."""
    r = assess_corpus_adequacy(
        tier_counts={"T4": 10},
        evidence_row_count=10,
        domain="ai_sovereignty",
        protocol={"corpus_adequacy": {"min_t3_plus_t4_plus_t6": 20}},
    )
    finding = next(
        f for f in r.findings if f.name == "t3_plus_t4_plus_t6"
    )
    assert finding.threshold == 20, (
        f"protocol override should set threshold=20, got {finding.threshold}"
    )
