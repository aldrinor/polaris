"""I-deepfix-001 WS-8 (D4) — publication-year recency leg for the journal-only genre re-rank.

Behavioral, offline, fixture-driven (no model/GPU/network). Proves:
  1. a very-old source (1986) is DEMOTED below a recent journal source in the display re-rank weight,
     so it no longer HEADLINES a recent-topic review;
  2. the old source STAYS in the list (never dropped — WEIGHT-and-DISCLOSE, §-1.3);
  3. the reference year is CORPUS-RELATIVE (newest source in the set), deterministic (no wall-clock);
  4. an unknown/absent year gets NO penalty (factor 1.0 — never guessed);
  5. kill-switch OFF (PG_M2_RECENCY_RERANK=0) => factor 1.0 => byte-identical pre-WS-8 ordering.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.run_honest_sweep_r3 import (  # noqa: E402
    _m2_publication_year,
    _m2_recency_factor,
    _m2_reference_year,
)


def _clear_env(monkeypatch):
    for k in (
        "PG_M2_RECENCY_RERANK",
        "PG_M2_RECENCY_DECAY_PER_YEAR",
        "PG_M2_RECENCY_GRACE_YEARS",
        "PG_M2_RECENCY_FLOOR",
    ):
        monkeypatch.delenv(k, raising=False)


def test_publication_year_explicit_field_first(monkeypatch):
    _clear_env(monkeypatch)
    assert _m2_publication_year({"year": 2019}) == 2019
    assert _m2_publication_year({"publication_year": "2011"}) == 2011


def test_publication_year_parsed_from_statement(monkeypatch):
    _clear_env(monkeypatch)
    assert _m2_publication_year({"statement": "Morrar et al. (2017) surveyed …"}) == 2017
    assert _m2_publication_year({"url": "https://x.org/j.jom.1986.05.003"}) == 1986


def test_publication_year_none_when_absent(monkeypatch):
    _clear_env(monkeypatch)
    assert _m2_publication_year({"statement": "no year here", "url": "https://x.org/abc"}) is None


def test_reference_year_is_corpus_newest(monkeypatch):
    _clear_env(monkeypatch)
    biblio = [{"year": 1986}, {"year": 2024}, {"year": 2011}, {"statement": "no year"}]
    assert _m2_reference_year(biblio) == 2024
    assert _m2_reference_year([{"statement": "no year"}]) is None


def test_old_source_demoted_but_recent_full_weight(monkeypatch):
    _clear_env(monkeypatch)
    ref = 2024
    recent = _m2_recency_factor({"year": 2023}, ref)  # within grace of 2024
    old = _m2_recency_factor({"year": 1986}, ref)      # 38y old
    assert recent == 1.0, "a within-grace recent source keeps full weight"
    assert 0.0 < old < recent, "a 1986 source is DEMOTED below a recent source (but never zero)"


def test_old_source_never_dropped_floored(monkeypatch):
    _clear_env(monkeypatch)
    # A pathologically old source is FLOORED, never 0 (demote-not-drop, §-1.3).
    f = _m2_recency_factor({"year": 1500}, 2024)
    assert f >= 0.25, "recency factor is floored (default 0.25) — the source stays rankable, never dropped"
    assert f > 0.0


def test_unknown_year_no_penalty(monkeypatch):
    _clear_env(monkeypatch)
    assert _m2_recency_factor({"statement": "no year"}, 2024) == 1.0, "unknown year => no penalty (never guess)"


def test_none_reference_year_no_penalty(monkeypatch):
    _clear_env(monkeypatch)
    assert _m2_recency_factor({"year": 1986}, None) == 1.0, "no corpus reference year => factor 1.0"


def test_killswitch_off_is_byte_identical(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PG_M2_RECENCY_RERANK", "0")
    # OFF => every source (even a 1986 one against a 2024 corpus) gets factor 1.0 = the pre-WS-8 weight.
    assert _m2_recency_factor({"year": 1986}, 2024) == 1.0
    assert _m2_recency_factor({"year": 2024}, 2024) == 1.0


def test_env_constants_tune_the_curve(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PG_M2_RECENCY_GRACE_YEARS", "0")
    monkeypatch.setenv("PG_M2_RECENCY_DECAY_PER_YEAR", "0.10")
    monkeypatch.setenv("PG_M2_RECENCY_FLOOR", "0.10")
    # 1986 vs 2024 = 38y, decay 0.10 => 1 - 3.8 => floored at 0.10.
    assert _m2_recency_factor({"year": 1986}, 2024) == 0.10
    # 2020 vs 2024 = 4y, decay 0.10 => 1 - 0.4 = 0.60.
    assert abs(_m2_recency_factor({"year": 2020}, 2024) - 0.60) < 1e-9


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
