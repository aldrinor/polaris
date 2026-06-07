"""I-ready-018 FIX-RENDER (#1100) — report-renderer disclosures: BP (domain-neutral contradiction
boilerplate), A9 (quantified-analysis silent-degradation disclosure), A10 (retrieval fetch-failure
disclosure + over-threshold loud warning). Pure-helper unit tests + a BP source-presence guard.
No run, no spend.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.run_honest_sweep_r3 import (  # noqa: E402
    quantified_degradation_disclosure,
    retrieval_failure_warning,
    retrieval_fetch_disclosure,
)


# ---- A10: retrieval fetch disclosure + loud warning ----
def test_a10_fetch_disclosure_line_reports_real_counts():
    line = retrieval_fetch_disclosure(26, 129, 155)  # the frozen drb_72 values
    assert "26 of 155" in line and "129 failed or timed out" in line


def test_a10_warning_fires_over_threshold():
    # drb_72: 129/155 = 83% failed -> over the 0.5 default -> loud warning.
    w = retrieval_failure_warning(26, 129, 155, 0.5)
    assert w is not None and "129/155" in w and "upstream-starved" in w


def test_a10_warning_silent_under_threshold_and_on_zero():
    assert retrieval_failure_warning(150, 5, 155, 0.5) is None
    assert retrieval_failure_warning(0, 0, 0, 0.5) is None  # no candidates -> no div-by-zero, no warn


# ---- A9: quantified-analysis silent-degradation disclosure ----
def test_a9_discloses_enabled_but_not_fired():
    # drb_72 shape: enabled, 0 verified sentences, 111 sourced numbers extracted.
    block = quantified_degradation_disclosure(
        {"enabled": True, "verified_sentences": 0, "firing_status": "attempted_empty",
         "sourced_numbers_extracted": 111}
    )
    assert "## Capability disclosures" in block
    assert "ENABLED but did not contribute" in block
    assert "111 sourced numbers" in block


def test_a9_silent_when_fired_or_disabled():
    assert quantified_degradation_disclosure({"enabled": True, "verified_sentences": 5}) == ""
    assert quantified_degradation_disclosure({"enabled": False}) == ""
    assert quantified_degradation_disclosure(None) == ""


# ---- BP: domain-neutral contradiction disclosure (no clinical boilerplate leaks) ----
def test_bp_contradiction_disclosure_has_no_clinical_boilerplate():
    src = (_REPO / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8")
    # The clinical examples that leaked into the AI-labor report must be gone.
    assert "HbA1c % vs body-weight" not in src
    assert "T2D vs obesity-without-diabetes" not in src
    # The domain-neutral replacement is present.
    assert "measured endpoints, units, sub-populations, time windows" in src
