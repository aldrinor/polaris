"""I-deepfix-001 WS-8 (D4) part 2 — composition-ordering recency leg.

Codex iter-1 on the bib re-rank: insufficient alone — the 1986 source headlines from the composition/
selection ordering (diagnose_unbound_supports_selection). This leg demotes an OLD source in the weight_mass
ordering term so it no longer anchors a top finding — a WEIGHT on the sort key, NEVER a filter (the full list
is kept). Journal-class only; byte-identical when off / non-journal-class / unknown year.

Behavioral, offline. Proves the helper curve + that the selection sort key actually USES it (wiring guard).
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.generator import weighted_enrichment as we  # noqa: E402


def _clear(monkeypatch):
    for k in (
        "PG_DOCUMENT_TYPE_WEIGHT", "PG_COMPOSITION_RECENCY",
        "PG_M2_RECENCY_GRACE_YEARS", "PG_M2_RECENCY_DECAY_PER_YEAR", "PG_M2_RECENCY_FLOOR",
    ):
        monkeypatch.delenv(k, raising=False)


def test_enabled_only_for_journal_class(monkeypatch):
    _clear(monkeypatch)
    assert we._composition_recency_enabled() is False, "OFF without PG_DOCUMENT_TYPE_WEIGHT (non-journal run)"
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    assert we._composition_recency_enabled() is True, "ON for a journal-class run"
    monkeypatch.setenv("PG_COMPOSITION_RECENCY", "0")
    assert we._composition_recency_enabled() is False, "kill-switch OFF disables it even journal-class"


def test_publication_year_parse(monkeypatch):
    _clear(monkeypatch)
    assert we._we_publication_year({"year": 2024}) == 2024
    assert we._we_publication_year({"title": "Robotics, J. Operations Mgmt (1986)"}) == 1986
    assert we._we_publication_year({"statement": "no year"}) is None
    assert we._we_publication_year(None) is None


def test_old_source_demoted_recent_full(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    old = we._we_recency_factor(1986, 2024)
    recent = we._we_recency_factor(2023, 2024)
    assert recent == 1.0
    assert 0.0 < old < recent, "a 1986 source is demoted in the ordering (never zero)"
    assert we._we_recency_factor(1500, 2024) >= 0.25, "floored — never dropped"


def test_byte_identical_when_off_or_unknown(monkeypatch):
    _clear(monkeypatch)
    # non-journal run => factor 1.0 regardless of age.
    assert we._we_recency_factor(1986, 2024) == 1.0
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    # journal-class but unknown year => 1.0 (never guessed).
    assert we._we_recency_factor(None, 2024) == 1.0
    # journal-class but no corpus reference year => 1.0.
    assert we._we_recency_factor(1986, None) == 1.0


def test_selection_sort_key_uses_recency_factor():
    """Wiring guard: a future un-wiring (removing the factor from the sort key) FAILS here."""
    src = inspect.getsource(we.diagnose_unbound_supports_selection)
    assert "_we_recency_factor(_year_by_eid" in src, (
        "the unbound-supports selection sort key must multiply weight_mass by the recency factor"
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
