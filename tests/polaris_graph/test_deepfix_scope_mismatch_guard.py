"""I-deepfix-001 (item 13a) — numeric-contradiction SCOPE-MISMATCH guard.

Fixes the mislabel where two claims about the SAME drug / predicate / unit / dose
measured at DIFFERENT time-windows (or in different populations) were asserted as a
HARD numeric contradiction. That is an expected time-course range, not a
cross-source disagreement, and it dragged the benchmark score with meaningless
high-severity "contradictions".

The guard (``PG_CONTRADICTION_SCOPE_MISMATCH_GUARD``, default-OFF) downgrades such a
group to ``possible_metric_mismatch`` (disclosed, both sides + sources kept — §-1.3),
but ONLY on POSITIVE scope divergence — a genuine same-scope disagreement (both
claims at the same time-window, different sources) still surfaces as a real
contradiction. RED (flag off) vs GREEN (flag on) below prove exactly that.

Faithfulness is NEVER relaxed: the detector only becomes MORE conservative (fewer
fabricated contradictions); strict_verify / NLI / 4-role / provenance are untouched.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    detect_contradictions,
    extract_numeric_claims,
)

_FLAG = "PG_CONTRADICTION_SCOPE_MISMATCH_GUARD"


def _ev(ev_id: str, quote: str, url: str, tier: str = "T1") -> dict:
    return {
        "evidence_id": ev_id,
        "direct_quote": quote,
        "tier": tier,
        "source_url": url,
    }


# The real drb/clinical repro: tirzepatide 15 mg weight loss reported at two
# DIFFERENT time-windows (week 26 vs week 88) by two different sources.
_DIVERGENT_ENDPOINT_EVIDENCE = [
    _ev("ev1", "Tirzepatide 15 mg produced a mean weight loss of 7.0% at week 26.",
        "https://a.example/1"),
    _ev("ev2", "Tirzepatide 15 mg achieved a mean weight loss of 20.9% at week 88.",
        "https://b.example/2"),
]

# Negative control: tirzepatide 5 mg weight loss BOTH at 40 weeks, two different
# sources reporting 2.7% vs 6.5% — a genuine same-scope disagreement that MUST stay
# a real contradiction.
_SHARED_ENDPOINT_EVIDENCE = [
    _ev("ev3", "Tirzepatide 5 mg produced a mean weight loss of 2.7% at 40 weeks.",
        "https://c.example/3"),
    _ev("ev4", "Tirzepatide 5 mg achieved a mean weight loss of 6.5% at 40 weeks.",
        "https://d.example/4"),
]


def _only_record(evidence):
    claims = extract_numeric_claims(evidence, domain="clinical")
    records = detect_contradictions(claims, is_clinical=True)
    assert len(records) == 1, [(r.subject, r.predicate) for r in records]
    return records[0]


def _is_hard_contradiction(record) -> bool:
    """A hard contradiction: not downgraded (no mismatch marker) and not not_comparable."""
    return (
        POSSIBLE_METRIC_MISMATCH_MARKER not in record.predicate
        and not getattr(record, "not_comparable", False)
    )


def test_red_divergent_endpoint_is_hard_contradiction_when_flag_off(monkeypatch) -> None:
    """RED (default / flag OFF): the different-time-window pair is asserted as a HARD
    contradiction — the exact mislabel this fix targets. Also proves the OFF path is
    byte-identical to the pre-fix behaviour."""
    monkeypatch.delenv(_FLAG, raising=False)
    record = _only_record(_DIVERGENT_ENDPOINT_EVIDENCE)
    assert _is_hard_contradiction(record)
    assert record.predicate.startswith("weight loss")
    assert record.severity in {"medium", "high"}


def test_green_divergent_endpoint_downgraded_when_flag_on(monkeypatch) -> None:
    """GREEN (flag ON): the different-time-window pair is downgraded to a
    possible_metric_mismatch — NOT a hard contradiction — while both values and their
    sources stay disclosed (§-1.3: never dropped)."""
    monkeypatch.setenv(_FLAG, "1")
    record = _only_record(_DIVERGENT_ENDPOINT_EVIDENCE)
    assert not _is_hard_contradiction(record)
    assert POSSIBLE_METRIC_MISMATCH_MARKER in record.predicate
    assert not getattr(record, "not_comparable", False)
    # §-1.3: both sources still disclosed in the record (nothing dropped).
    assert {c.evidence_id for c in record.claims} == {"ev1", "ev2"}


def test_shared_endpoint_stays_a_real_contradiction_flag_off(monkeypatch) -> None:
    """Negative control (flag OFF): same-time-window, different-source disagreement is a
    real contradiction."""
    monkeypatch.delenv(_FLAG, raising=False)
    record = _only_record(_SHARED_ENDPOINT_EVIDENCE)
    assert _is_hard_contradiction(record)


def test_shared_endpoint_still_a_real_contradiction_when_flag_on(monkeypatch) -> None:
    """Faithfulness-SAFE: even with the guard ON, a genuine same-scope disagreement
    (both at 40 weeks) is UNAFFECTED and still surfaces as a real contradiction — the
    guard only suppresses POSITIVE scope divergence, never real-contradiction recall."""
    monkeypatch.setenv(_FLAG, "1")
    record = _only_record(_SHARED_ENDPOINT_EVIDENCE)
    assert _is_hard_contradiction(record)
    assert POSSIBLE_METRIC_MISMATCH_MARKER not in record.predicate


def test_divergent_population_downgraded_when_flag_on(monkeypatch) -> None:
    """The guard also covers the 'different populations' mislabel class (not only
    time-windows): same drug/predicate, two different cohorts -> possible_metric_mismatch."""
    monkeypatch.setenv(_FLAG, "1")
    from src.polaris_graph.retrieval.contradiction_detector import (
        ExtractedNumericClaim,
    )
    # Positive population divergence on the same subject/predicate/unit.
    claims = [
        ExtractedNumericClaim(
            evidence_id="ev_a", subject="tirzepatide", predicate="weight loss",
            value=12.0, unit="%", context_snippet="", source_url="https://a.example/a",
            source_tier="T1", population="patients with type 2 diabetes",
        ),
        ExtractedNumericClaim(
            evidence_id="ev_b", subject="tirzepatide", predicate="weight loss",
            value=20.0, unit="%", context_snippet="", source_url="https://b.example/b",
            source_tier="T1", population="patients without diabetes",
        ),
    ]
    records = detect_contradictions(claims, is_clinical=True)
    assert len(records) == 1
    assert POSSIBLE_METRIC_MISMATCH_MARKER in records[0].predicate
    assert {c.evidence_id for c in records[0].claims} == {"ev_a", "ev_b"}
