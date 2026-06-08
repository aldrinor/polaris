"""I-cred-003 (Phase 3) — temporal / supersession + retraction. Pure-function unit tests.

No network, no fixtures, no live data. Deterministic via an explicit now_year.
"""

from __future__ import annotations

import os

from src.polaris_graph.authority.supersession import (
    supersession_adjustment,
    supersession_enabled,
)


def test_flag_default_off():
    prev = os.environ.pop("PG_SWEEP_SUPERSESSION", None)
    try:
        assert supersession_enabled() is False
        os.environ["PG_SWEEP_SUPERSESSION"] = "1"
        assert supersession_enabled() is True
    finally:
        if prev is None:
            os.environ.pop("PG_SWEEP_SUPERSESSION", None)
        else:
            os.environ["PG_SWEEP_SUPERSESSION"] = prev


def test_retraction_is_hard_penalty():
    r = supersession_adjustment(
        {"is_retracted": True, "source_type": "journal", "year": 2024}, now_year=2026
    )
    assert r.hard_penalty is True
    assert r.multiplier < 0.2
    assert r.certainty_downgrade is True
    assert r.soft_warning and "retract" in r.soft_warning.lower()


def test_retraction_overrides_freshness():
    # Even a fresh retracted source is hard-penalized.
    r = supersession_adjustment({"retracted": "true", "year": 2026}, now_year=2026)
    assert r.hard_penalty is True
    assert r.multiplier < 0.2


def test_superseded_is_downgraded_not_hard():
    r = supersession_adjustment(
        {"superseded_by": "doi:newer", "source_type": "guideline", "year": 2020}, now_year=2026
    )
    assert r.hard_penalty is False
    assert 0.0 < r.multiplier < 1.0
    assert r.certainty_downgrade is True
    assert r.soft_warning and "supersed" in r.soft_warning.lower()


def test_stale_time_sensitive_is_downgraded():
    r = supersession_adjustment({"source_type": "guideline", "year": 2010}, now_year=2026)  # 16y > 7y
    assert r.multiplier < 1.0
    assert r.certainty_downgrade is True
    assert r.soft_warning and "out-of-date" in r.soft_warning.lower()


def test_old_but_not_time_sensitive_is_not_downgraded():
    # A foundational-theory paper is NOT downgraded for age alone.
    r = supersession_adjustment({"source_type": "theory", "year": 1990}, now_year=2026)
    assert r.multiplier == 1.0
    assert r.soft_warning is None
    assert r.certainty_downgrade is False


def test_fresh_time_sensitive_no_adjustment():
    r = supersession_adjustment({"source_type": "guideline", "year": 2025}, now_year=2026)
    assert r.multiplier == 1.0
    assert r.hard_penalty is False
    assert r.soft_warning is None


def test_env_thresholds_override(monkeypatch):
    monkeypatch.setenv("PG_SUPERSESSION_STALE_YEARS", "2")
    monkeypatch.setenv("PG_SUPERSESSION_STALE_MULTIPLIER", "0.3")
    r = supersession_adjustment({"source_type": "news", "year": 2022}, now_year=2026)  # 4y > 2y
    assert r.multiplier == 0.3
    assert r.soft_warning is not None


def test_missing_date_no_age_downgrade():
    # Missing date -> cannot judge staleness -> no fabricated age penalty.
    r = supersession_adjustment({"source_type": "guideline"}, now_year=2026)
    assert r.multiplier == 1.0
    assert r.soft_warning is None


def test_iso_date_string_year_extraction():
    r = supersession_adjustment(
        {"source_type": "regulation", "date": "2009-03-01"}, now_year=2026
    )  # 17y > 7y
    assert r.multiplier < 1.0
    assert r.soft_warning is not None
