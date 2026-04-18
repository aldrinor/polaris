"""
BUG-M-204 regression tests: Limitations paragraph telemetry-grounded
verification.

Pre-fix: every Limitations sentence was marked is_verified=True with
a pass-through soft_warning, regardless of whether its numbers matched
the pipeline telemetry block. A fabricated "only 3% of sources are T1
primary studies" would ship even if telemetry said "T1: 9%".

Post-fix (deep-dive R10): when strict_verify is called with a
telemetry_block, Limitations sentences are checked — every decimal/
percentage in the sentence must appear verbatim in the telemetry.
"""
from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    strict_verify,
    verify_limitations_sentence_against_telemetry,
)


TELEMETRY_EXAMPLE = """
tier_distribution:
  T1: 9%
  T2: 21%
  T3: 15%
  T6: 18%
contradictions_detected: 2
  - semaglutide / weight_loss: rel_diff 16.8%, severity=medium
  - semaglutide / adverse_events: rel_diff 8.2%, severity=low
date_range: 2010-01-01 to current
"""


# ─────────────────────────────────────────────────────────────────
# Sentence-level verifier
# ─────────────────────────────────────────────────────────────────

def test_m204_sentence_with_matching_number_verifies() -> None:
    """9% appears in telemetry → verified."""
    v = verify_limitations_sentence_against_telemetry(
        "Only 9% of sources are T1 primary studies.",
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is True
    assert v.failure_reasons == []


def test_m204_sentence_with_unmatched_number_rejects() -> None:
    """5% not in telemetry → rejected."""
    v = verify_limitations_sentence_against_telemetry(
        "Only 5% of sources are T1 primary studies.",
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is False
    assert any("limitations_number_not_in_telemetry" in r
               for r in v.failure_reasons)


def test_m204_multiple_numbers_any_unmatched_rejects() -> None:
    """Two numbers: 21% matches, 99% does not → rejected."""
    v = verify_limitations_sentence_against_telemetry(
        "Sources are 21% T2 and 99% industry reports.",
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is False


def test_m204_no_numbers_in_sentence_verifies() -> None:
    """A sentence with no numeric claims is always verified (nothing
    to check)."""
    v = verify_limitations_sentence_against_telemetry(
        "The corpus is skewed toward industry reports.",
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is True


def test_m204_contradiction_rel_diff_quoted_verifies() -> None:
    """rel_diff 16.8% is in telemetry → quotable."""
    v = verify_limitations_sentence_against_telemetry(
        "Sources disagree on weight loss with rel_diff 16.8%.",
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is True


def test_m204_bare_number_matches_percentage_in_telemetry() -> None:
    """'9' appears in 'T1: 9%' — matches via bare stripping."""
    v = verify_limitations_sentence_against_telemetry(
        "Only 9 percent are T1.",  # '9' without '%' should still match
        TELEMETRY_EXAMPLE,
    )
    assert v.is_verified is True


def test_m204_no_telemetry_falls_back_to_passthrough() -> None:
    """If no telemetry block is provided, preserve backward-compat
    pass-through so old callers don't break."""
    v = verify_limitations_sentence_against_telemetry(
        "Only 99% of sources are fabricated.",  # nothing would match
        "",  # no telemetry
    )
    assert v.is_verified is True
    assert any("no_telemetry" in w for w in v.soft_warnings)


# ─────────────────────────────────────────────────────────────────
# strict_verify integration
# ─────────────────────────────────────────────────────────────────

def test_m204_strict_verify_without_telemetry_preserves_passthrough() -> None:
    """Backward compat: no telemetry_block → limitations pass through."""
    draft = (
        "Semaglutide achieved 14.9% weight loss [#ev:ev_a:0-26].\n\n"
        "Limitations: The corpus is thin at only 3% T1 primary studies."
    )
    evidence_pool = {
        "ev_a": {"direct_quote": "Semaglutide achieved 14.9% weight loss."},
    }
    report = strict_verify(draft, evidence_pool, telemetry_block=None)
    # Limitations sentence kept as-is (pass-through)
    kept_texts = [sv.sentence for sv in report.kept_sentences]
    assert any("3% T1" in s for s in kept_texts), (
        "Pass-through mode should keep even unverified limitations sentences"
    )


def test_m204_strict_verify_with_telemetry_drops_bad_limitations() -> None:
    """When telemetry_block is provided, limitations with unmatched
    numbers are dropped."""
    draft = (
        "Semaglutide achieved 14.9% weight loss [#ev:ev_a:0-26].\n\n"
        "Limitations: The corpus is thin at only 3% T1 primary studies."
    )
    evidence_pool = {
        "ev_a": {"direct_quote": "Semaglutide achieved 14.9% weight loss."},
    }
    # Telemetry says T1 is 9%, not 3%
    telemetry = "tier_distribution:\n  T1: 9%\n"
    report = strict_verify(draft, evidence_pool, telemetry_block=telemetry)
    # Fabricated "3%" limitations sentence should be in DROPPED
    dropped_texts = [sv.sentence for sv in report.dropped_sentences]
    assert any("3% T1" in s for s in dropped_texts), (
        f"Fabricated 3% claim should be dropped. Got dropped: {dropped_texts}"
    )


def test_m204_strict_verify_with_telemetry_keeps_honest_limitations() -> None:
    """Honest limitations claim (matches telemetry) survives."""
    draft = (
        "Semaglutide achieved 14.9% weight loss [#ev:ev_a:0-26].\n\n"
        "Limitations: The corpus has only 9% T1 primary studies."
    )
    evidence_pool = {
        "ev_a": {"direct_quote": "Semaglutide achieved 14.9% weight loss."},
    }
    telemetry = "tier_distribution:\n  T1: 9%\n"
    report = strict_verify(draft, evidence_pool, telemetry_block=telemetry)
    kept_texts = [sv.sentence for sv in report.kept_sentences]
    assert any("9% T1" in s for s in kept_texts)
