"""RACE-FLOOR lever 2 — WRITER-menu top-N ev-density cap (faithfulness-contract tests).

The cap FOCUSES the per-section WRITER prompt menu (``ev_subset``) to the top-N highest-ranked
rows so a route_all/facet-route-crammed section composes deep step3-like prose instead of a
65%-dropped shallow spread. These tests pin the faithfulness contract on the REAL helper
(``_apply_writer_menu_cap`` / ``_writer_topn_ev_per_section``):

  * OFF by default => byte-identical (menu unchanged, same object).
  * ON => the menu is the deterministic HEAD-N of the ranked list.
  * The cap NEVER mutates its input list (so the caller's ``section.ev_ids`` and ``evidence_pool``
    are untouched — bibliography + credibility disclosure + the strict_verify pool all keep every
    withheld row).
"""
import importlib

import pytest

msg = importlib.import_module("src.polaris_graph.generator.multi_section_generator")


def test_cap_off_by_default_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_WRITER_TOPN_EV_PER_SECTION", raising=False)
    assert msg._writer_topn_ev_per_section() == 0
    menu = [{"evidence_id": f"e{i}"} for i in range(50)]
    out = msg._apply_writer_menu_cap(menu, section_title="S", total_assigned=50)
    assert out is menu  # same object — no copy, no slice, byte-identical


@pytest.mark.parametrize("bad", ["0", "-4", "notint", ""])
def test_nonpositive_or_bad_env_disables_cap(monkeypatch, bad):
    monkeypatch.setenv("PG_WRITER_TOPN_EV_PER_SECTION", bad)
    assert msg._writer_topn_ev_per_section() == 0
    menu = [{"evidence_id": f"e{i}"} for i in range(30)]
    assert msg._apply_writer_menu_cap(menu, total_assigned=30) is menu


def test_cap_keeps_deterministic_head_n(monkeypatch):
    monkeypatch.setenv("PG_WRITER_TOPN_EV_PER_SECTION", "24")
    assert msg._writer_topn_ev_per_section() == 24
    menu = [{"evidence_id": f"e{i}"} for i in range(103)]  # a crammed drb_72-scale section
    out = msg._apply_writer_menu_cap(menu, section_title="Crammed", total_assigned=103)
    assert len(out) == 24
    # HEAD-N, in order — the highest-ranked primaries (route_all orphans are appended to the tail).
    assert [r["evidence_id"] for r in out] == [f"e{i}" for i in range(24)]


def test_cap_does_not_mutate_input_or_drop_rows_from_pool(monkeypatch):
    """The withheld tail must remain reachable to the caller: the cap returns a NEW list and never
    mutates the input, so ``section.ev_ids`` / ``evidence_pool`` (bibliography + disclosure + the
    strict_verify pool) keep every row."""
    monkeypatch.setenv("PG_WRITER_TOPN_EV_PER_SECTION", "10")
    menu = [{"evidence_id": f"e{i}"} for i in range(40)]
    original_ids = [r["evidence_id"] for r in menu]
    out = msg._apply_writer_menu_cap(menu, total_assigned=40)
    # input list untouched (identity + contents), so nothing is deleted from the caller's state
    assert len(menu) == 40
    assert [r["evidence_id"] for r in menu] == original_ids
    assert out is not menu
    # every withheld row is still present in the (untouched) source list the pool/bib are built from
    withheld = [r["evidence_id"] for r in menu[10:]]
    assert len(withheld) == 30
    assert set(withheld).isdisjoint({r["evidence_id"] for r in out})


def test_menu_shorter_than_cap_is_untouched(monkeypatch):
    monkeypatch.setenv("PG_WRITER_TOPN_EV_PER_SECTION", "24")
    menu = [{"evidence_id": f"e{i}"} for i in range(9)]  # a deep step3-scale section already < cap
    out = msg._apply_writer_menu_cap(menu, total_assigned=9)
    assert out is menu  # no-op — never grows or reorders a small section
