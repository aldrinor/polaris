"""I-deepfix-001 U28 (#1344) — contradiction-detector noise guards.

Offline, deterministic, no GPU / network / paid-LLM. Exercises three validity
guards added to ``detect_contradictions``:

  1. cap absurd rel-diff — a 772,700% relative difference is NOT "low severity";
  2. drop stopword subjects — a stopword subject is not a contradiction subject
     (relabeled not_comparable, kept out of the headline count, still disclosed);
  3. ignore 0.0% clusters — a zero-spread cluster is never a contradiction.

Each guard's RED (pre-fix) behavior is documented inline. The OFF path
(``PG_CONTRADICTION_NOISE_GUARD=0``) restores the pre-fix behavior byte-for-byte,
which is asserted so the escape hatch is real.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    detect_contradictions,
    format_contradictions_for_user,
)


def _claim(
    ev_id: str,
    subject: str,
    predicate: str,
    value: float,
    *,
    unit: str = "",
    url: str | None = None,
) -> ExtractedNumericClaim:
    return ExtractedNumericClaim(
        evidence_id=ev_id,
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        context_snippet=f"{subject} {predicate} {value}{unit}",
        source_url=url if url is not None else f"https://example.com/{ev_id}",
        source_tier="T1",
    )


# ── Guard 1: an absurd rel-diff is NOT low-severity ──────────────────────────
def test_absurd_rel_diff_is_not_low_severity() -> None:
    # vmin=0.01, vmax=77.28 -> rel = 77.27/0.01 = 7727.0 -> 772,700%.
    # Two distinct sources (so the same-source guard does not fire first), a
    # non-drug / non-stopword subject, unit-less, no confirmed shared scope axes
    # -> routes to the possible_metric_mismatch branch (is_clinical=False).
    claims = [
        _claim("ev_a", "widget", "rate", 0.01, url="https://a.example/1"),
        _claim("ev_b", "widget", "rate", 77.28, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=False)
    assert len(records) == 1
    r = records[0]
    # Pre-fix RED: severity was hardcoded "low" in the metric_mismatch branch, so a
    # 772,700% rel_diff rendered as a benign "low"-severity signal.
    assert r.severity != "low"
    # The surfaced magnitude is capped so the junk 772,700% never leaks downstream.
    assert r.relative_difference <= 50.0
    assert r.relative_difference * 100 < 772700.0


def test_absurd_rel_diff_off_flag_restores_low_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_CONTRADICTION_NOISE_GUARD", "0")
    claims = [
        _claim("ev_a", "widget", "rate", 0.01, url="https://a.example/1"),
        _claim("ev_b", "widget", "rate", 77.28, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=False)
    assert len(records) == 1
    r = records[0]
    # OFF path is byte-identical to the pre-fix output: "low" + uncapped magnitude.
    assert r.severity == "low"
    assert r.relative_difference == pytest.approx(7727.0, rel=1e-3)


def test_moderate_metric_mismatch_stays_low(monkeypatch: pytest.MonkeyPatch) -> None:
    # A modest (non-absurd) unconfirmed-scope gap stays a low-severity possible
    # metric mismatch — the absurd guard only fires on a genuinely absurd magnitude.
    claims = [
        _claim("ev_a", "widget", "rate", 5.0, url="https://a.example/1"),
        _claim("ev_b", "widget", "rate", 7.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=False)
    assert len(records) == 1
    assert records[0].severity == "low"


# ── Guard 2: a stopword subject is not a contradiction subject ───────────────
def test_stopword_subject_is_not_a_contradiction() -> None:
    # Subject "the" is a generic filler word — a failed entity extraction that
    # collapsed two unrelated claims under a non-entity key.
    claims = [
        _claim("ev_a", "the", "rate", 5.0, url="https://a.example/1"),
        _claim("ev_b", "the", "rate", 12.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=False)
    assert len(records) == 1
    r = records[0]
    # Pre-fix RED: this surfaced as a real (marker-bearing) contradiction with
    # not_comparable=False; now it is relabeled not_comparable + disclosed.
    assert r.not_comparable is True
    assert "stopword_subject" in r.incommensurable_reason
    # And it is NOT counted in the human-readable headline contradiction count.
    summary = format_contradictions_for_user(records)
    assert "Detected 0 contradiction(s)" in summary
    # But it is still DISCLOSED (never dropped — §-1.3).
    assert "not-comparable bucket" in summary


def test_stopword_subject_clinical_path_also_guarded() -> None:
    # The guard fires regardless of the is_clinical routing flag: a stopword
    # subject is never a real drug/entity subject.
    claims = [
        _claim("ev_a", "mean", "reduction", 5.0, url="https://a.example/1"),
        _claim("ev_b", "mean", "reduction", 12.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=True)
    assert len(records) == 1
    assert records[0].not_comparable is True


def test_real_subject_still_contradicts() -> None:
    # A REAL entity subject with a genuine same-unit disagreement is NOT
    # suppressed — the guard only drops stopword subjects.
    claims = [
        _claim("ev_a", "semaglutide", "weight loss", 14.9, unit="%",
               url="https://a.example/1"),
        _claim("ev_b", "semaglutide", "weight loss", 17.4, unit="%",
               url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=True)
    assert len(records) == 1
    r = records[0]
    assert r.not_comparable is False
    assert r.severity in {"medium", "high"}


def test_stopword_subject_off_flag_restores_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_CONTRADICTION_NOISE_GUARD", "0")
    claims = [
        _claim("ev_a", "the", "rate", 5.0, url="https://a.example/1"),
        _claim("ev_b", "the", "rate", 12.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(claims, is_clinical=False)
    assert len(records) == 1
    # OFF path: the pre-fix behavior (a possible_metric_mismatch marker record,
    # not the new stopword not_comparable relabel).
    assert records[0].not_comparable is False
    assert "stopword_subject" not in records[0].incommensurable_reason


# ── Guard 3: ignore a zero-spread "0.0%" cluster ─────────────────────────────
def test_zero_spread_cluster_ignored() -> None:
    # Identical values -> rel == 0.0. Only reaches the emit path when a caller
    # sets a 0 threshold; the guard drops it as a non-contradiction.
    claims = [
        _claim("ev_a", "widget", "rate", 5.0, url="https://a.example/1"),
        _claim("ev_b", "widget", "rate", 5.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(
        claims, is_clinical=False, rel_threshold=0.0, abs_threshold=0.0,
    )
    assert records == []


def test_zero_spread_off_flag_would_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-fix RED: with a 0 threshold and the guard OFF, a zero-spread cluster
    # slipped through as a 0.0% "contradiction".
    monkeypatch.setenv("PG_CONTRADICTION_NOISE_GUARD", "0")
    claims = [
        _claim("ev_a", "widget", "rate", 5.0, url="https://a.example/1"),
        _claim("ev_b", "widget", "rate", 5.0, url="https://b.example/2"),
    ]
    records = detect_contradictions(
        claims, is_clinical=False, rel_threshold=0.0, abs_threshold=0.0,
    )
    assert len(records) == 1
    assert records[0].relative_difference == 0.0
