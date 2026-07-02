"""Offline unit test for the one-sidedness PRIMACY advisory (I-deepfix-001 Wave-2).

FORCED-POSITIVE: a claim that headlines "1.8%" while the cited basket also carries a
materially-different same-kind companion "46% of tasks exposed" MUST fire the
advisory. NEGATIVE-CONTROL: a claim whose basket holds only bare sample sizes /
years (no percent unit) MUST NOT fire — bare digits are never companions.

Offline logic test only (NOT a wiring proof): it confirms the leaf logic acts, not
that the advisory renders in a real report (a fresh render validates that later).

Run: PYTHONPATH=. python -m pytest tests/polaris_graph/test_primacy_frame_advisory.py -q
"""

from src.polaris_graph.generator.overstatement_guard import (
    primacy_frame_annotate_enabled,
    primacy_frame_reason,
)

# The Eloundou-style exposure basket: the claim leads with the small "1.8%" figure
# while the SAME "% of jobs/tasks exposed" measure also carries a far-larger "46%".
_BASKET_ONE_SIDED = (
    "Our findings indicate that around 1.8% of jobs could have over half their "
    "tasks affected by large language models. When accounting for current and "
    "likely future software developments, this share jumps to just over 46% of "
    "tasks exposed."
)


def test_forced_positive_headline_omits_larger_same_kind_companion(monkeypatch):
    # Default ON (flag unset).
    monkeypatch.delenv("PG_PRIMACY_FRAME_ANNOTATE", raising=False)
    reason = primacy_frame_reason("exposure is 1.8%", _BASKET_ONE_SIDED)
    assert reason is not None
    assert reason.startswith("primacy_frame_companion_omitted:")
    assert "headline=1.8%" in reason
    assert "companion=46%" in reason


def test_negative_control_bare_sample_sizes_and_years_do_not_fire(monkeypatch):
    monkeypatch.delenv("PG_PRIMACY_FRAME_ANNOTATE", raising=False)
    # Claim HAS a headline percent, but the basket holds ONLY bare digits (sample
    # size + year) — no percent unit, so nothing can pair as a companion.
    basket_bare = (
        "The trial enrolled n=1200 patients across sites in 2019; 1200 completed "
        "the protocol through 2019."
    )
    reason = primacy_frame_reason(
        "adverse events occurred in 4% of patients", basket_bare
    )
    assert reason is None


def test_negative_control_different_measure_context_does_not_fire(monkeypatch):
    monkeypatch.delenv("PG_PRIMACY_FRAME_ANNOTATE", raising=False)
    # Two percents of DIFFERENT measure kinds (no shared context stem) must not pair:
    # a jobs-exposure headline vs an unrelated survey-support percentage.
    basket = (
        "About 1.8% of jobs are exposed to automation. Separately, 62% of survey "
        "respondents supported the policy."
    )
    reason = primacy_frame_reason("exposure is 1.8%", basket)
    assert reason is None


def test_negative_control_rounding_neighbour_not_material(monkeypatch):
    monkeypatch.delenv("PG_PRIMACY_FRAME_ANNOTATE", raising=False)
    # Same measure kind but a tiny (non-material) magnitude gap must not fire.
    basket = (
        "Around 1.8% of jobs are exposed; a robustness check put the figure at "
        "1.9% of jobs exposed."
    )
    reason = primacy_frame_reason("exposure is 1.8%", basket)
    assert reason is None


def test_off_flag_is_byte_identical_inert(monkeypatch):
    monkeypatch.setenv("PG_PRIMACY_FRAME_ANNOTATE", "0")
    assert primacy_frame_annotate_enabled() is False
    # The exact forced-positive case returns None when the leg is OFF.
    assert primacy_frame_reason("exposure is 1.8%", _BASKET_ONE_SIDED) is None
