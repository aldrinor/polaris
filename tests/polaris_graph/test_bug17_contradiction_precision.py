"""BUG-17 (#1262) — contradiction-detector precision regression suite.

The pre-fix contradiction detector exploded into tens of thousands of FALSE
entries on a general corpus for two compounding reasons:

  1. It conflated the CLINICAL ROUTING string with a TRUE drug subject. When the
     run was routed ``domain == "clinical"`` (``is_clinical_domain`` returns
     True unconditionally), the no-shared-metric-guard drug-trial schema fired
     on EVERY numeric group — including clinical-routed but NON-drug claims (an
     ADAS yaw-angle ``accuracy`` figure). A pair with differing scope was then
     asserted as a hard contradiction with no shared-metric check.

  2. It grouped UNRELATED numbers under ``subject == "unknown"`` (entity
     extraction failed) and, on that same no-guard clinical path, flagged the
     pair (PCA variance vs CRC prevalence vs mouse weight) as one hard
     contradiction.

The fix (``contradiction_detector.detect_contradictions`` + the
``_group_has_real_drug_subject`` / ``_is_unknown_subject`` helpers) SEPARATES
the routing string from a real drug subject: the no-guard clinical schema fires
only for a group keyed on a recognised drug/intervention name; otherwise the
group falls through to the same-metric-axes guard, which DISCLOSES the pair as a
``possible_metric_mismatch`` — never silently drops it.

FAITHFULNESS (the binding constraint): this must NEVER delete a true
contradiction. The regression tests below prove three things in tandem:
  (a) two unrelated blank/unknown-subject numbers are NOT emitted as a hard
      contradiction;
  (b) a genuine same-subject numeric contradiction (real drug) IS still emitted
      as a hard contradiction (clinical schema unchanged, byte-identical);
  (c) an unknown-subject pair that is GENUINELY conflicting (scope confirmed
      shared) is surfaced — as a real contradiction — NOT silently dropped.

Mandatory regression coverage per the BUG-17 spec.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    detect_contradictions,
    _group_has_real_drug_subject,
    _is_unknown_subject,
)


def _claim(
    evidence_id: str,
    subject: str,
    predicate: str,
    value: float,
    unit: str,
    **kw: object,
) -> ExtractedNumericClaim:
    return ExtractedNumericClaim(
        evidence_id=evidence_id,
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        context_snippet=f"{subject} {value}{unit}",
        **kw,
    )


# ─────────────────────────────────────────────────────────────────────────────
# (a) REGRESSION — two UNRELATED blank/unknown-subject numbers are NOT a hard
#     contradiction, even on the clinical-routed (is_clinical=True) path.
# ─────────────────────────────────────────────────────────────────────────────

def test_bug17_unknown_subject_unrelated_numbers_not_hard_contradiction() -> None:
    """PCA variance (92%) vs CRC prevalence (4%) share subject="unknown" only
    because entity extraction failed; they measure DIFFERENT things. The old
    clinical no-guard path flagged this as a HIGH hard contradiction. After the
    fix it must NOT be a hard contradiction — it is disclosed as a possible
    metric mismatch (downgraded), never asserted."""
    a = _claim("e1", "unknown", "accuracy", 92.0, "percent")  # PCA variance
    b = _claim("e2", "unknown", "accuracy", 4.0, "percent")   # CRC prevalence
    recs = detect_contradictions([a, b], is_clinical=True)
    # Exactly one group; it must be labelled a mismatch, NOT a hard contradiction.
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate
    assert recs[0].severity == "low"


def test_bug17_blank_subject_unrelated_numbers_not_hard_contradiction() -> None:
    """Same as above but the subject is the empty string (blank sentinel).

    Values are chosen so the numeric gap clears the rel + abs thresholds (the
    pair would have been a HIGH hard contradiction pre-fix) — the point under
    test is the SUBJECT handling, not the numeric filter."""
    a = _claim("e1", "", "rate", 92.0, "percent")
    b = _claim("e2", "", "rate", 4.0, "percent")
    recs = detect_contradictions([a, b], is_clinical=True)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate


def test_bug17_clinical_routed_nondrug_pair_falls_through_to_metric_guard() -> None:
    """A clinical-ROUTED but NON-drug pair (ADAS yaw-angle accuracy) with
    DIFFERING scope must NOT inherit the drug-trial no-guard schema. The
    routing string is True but there is no real drug subject -> the shared-
    metric-axes guard applies and labels the pair a possible_metric_mismatch."""
    a = _claim("e1", "unknown", "accuracy", 92.0, "percent", population="highway driving")
    b = _claim("e2", "unknown", "accuracy", 4.0, "percent", population="urban driving")
    recs = detect_contradictions([a, b], is_clinical=True)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate


# ─────────────────────────────────────────────────────────────────────────────
# (b) FAITHFULNESS — a genuine same-DRUG numeric contradiction IS still emitted
#     as a hard contradiction (clinical drug-trial schema unchanged).
# ─────────────────────────────────────────────────────────────────────────────

def test_bug17_genuine_same_drug_contradiction_still_hard_flagged() -> None:
    """semaglutide weight loss 14.9% vs 17.4% — the canonical real clinical
    contradiction (Section E-06). It has a real drug subject, so it keeps the
    full clinical schema and is emitted as a HARD contradiction (no mismatch
    label). Proves the fix did not relax the drug-trial path."""
    a = _claim("e3", "semaglutide", "weight loss", 14.9, "%")
    b = _claim("e4", "semaglutide", "weight loss", 17.4, "%")
    recs = detect_contradictions([a, b], is_clinical=True)
    assert len(recs) == 1
    assert "possible_metric_mismatch" not in recs[0].predicate
    assert recs[0].subject == "semaglutide"
    # A real drug subject is recognised as the positive licensing signal.
    assert _group_has_real_drug_subject([a, b]) is True


def test_bug17_real_drug_group_skips_metric_guard_even_with_differing_scope() -> None:
    """A real-drug clinical contradiction must keep the no-guard clinical
    schema: even with NO positively-confirmed shared scope axis, a same-drug
    same-predicate numeric gap is still a hard contradiction (the clinical
    rule is intentionally stricter / does not require scope confirmation)."""
    a = _claim("e5", "tirzepatide", "weight loss", 20.9, "%")
    b = _claim("e6", "tirzepatide", "weight loss", 25.5, "%")
    recs = detect_contradictions([a, b], is_clinical=True)
    assert len(recs) == 1
    assert "possible_metric_mismatch" not in recs[0].predicate


# ─────────────────────────────────────────────────────────────────────────────
# (c) FAITHFULNESS — an unknown-subject pair that is GENUINELY conflicting
#     (scope confirmed shared) is surfaced, NOT silently dropped.
# ─────────────────────────────────────────────────────────────────────────────

def test_bug17_unknown_subject_confirmed_shared_scope_still_surfaced() -> None:
    """When entity extraction FAILED (subject="unknown") but the two numbers DO
    share a positively-confirmed scope axis (same population), they genuinely
    conflict. This MUST still be surfaced as a real contradiction — a blanket
    skip of unknown-subject groups would DROP it (a faithfulness loss). The fix
    routes it through the same-metric-axes guard, which CONFIRMS the shared
    metric and emits a hard contradiction (no mismatch label)."""
    a = _claim("e7", "unknown", "accuracy", 92.0, "percent", population="highway driving")
    b = _claim("e8", "unknown", "accuracy", 70.0, "percent", population="highway driving")
    recs = detect_contradictions([a, b], is_clinical=True)
    assert len(recs) == 1, "a genuine unknown-subject conflict must NOT be dropped"
    assert "possible_metric_mismatch" not in recs[0].predicate
    assert recs[0].severity in ("medium", "high")


# ─────────────────────────────────────────────────────────────────────────────
# Helper unit coverage.
# ─────────────────────────────────────────────────────────────────────────────

def test_bug17_is_unknown_subject_sentinels() -> None:
    assert _is_unknown_subject("unknown") is True
    assert _is_unknown_subject("UNKNOWN") is True
    assert _is_unknown_subject("") is True
    assert _is_unknown_subject("   ") is True
    assert _is_unknown_subject(None) is True  # type: ignore[arg-type]
    assert _is_unknown_subject("semaglutide") is False


def test_bug17_group_has_real_drug_subject() -> None:
    drug = [_claim("e1", "semaglutide", "weight loss", 14.9, "%")]
    assert _group_has_real_drug_subject(drug) is True
    nondrug = [_claim("e2", "unemployment", "rate", 4.0, "percent")]
    assert _group_has_real_drug_subject(nondrug) is False
    unknown = [_claim("e3", "unknown", "accuracy", 92.0, "percent")]
    assert _group_has_real_drug_subject(unknown) is False
    assert _group_has_real_drug_subject([]) is False


def test_bug17_non_clinical_path_behaviour_unchanged() -> None:
    """The non-clinical (is_clinical=False) path already applied the metric
    guard; the fix must leave it untouched. Differing scope -> mismatch."""
    a = _claim("e1", "gdp", "growth", 3.2, "percent", population="g7 economies")
    b = _claim("e2", "gdp", "growth", 1.1, "percent", population="emerging markets")
    recs = detect_contradictions([a, b], is_clinical=False)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate
