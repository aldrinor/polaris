"""I-deepfix-001 WS-10 — Source Necessity SURFACING disclosure builder.

The DeepTRACE metric VI algorithm (minimum source cover, greedy set cover) is verified in
``test_ws14_deeptrace_scorer.py``. These tests verify the PURE surfacing wrapper: that it reuses
``minimum_source_cover_size`` from the WS-14 scorer for the primary necessity ratio, retains the
sole-supporter count as the SECONDARY ``n_sole_supporter`` field, computes the cover/redundant split
and ratio correctly, honours the default-ON ``PG_SOURCE_NECESSITY_DISCLOSURE`` kill switch
(OFF => None), and NEVER drops a source (``listed_sources`` always equals ``n_sources``).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.dr_benchmark.deeptrace_scorer import (  # noqa: E402
    minimum_source_cover_size,
    necessary_source_count,
)
from src.polaris_graph.audit.source_necessity_disclosure import (  # noqa: E402
    build_source_necessity_disclosure,
)

_FLAG = "PG_SOURCE_NECESSITY_DISCLOSURE"


def _on(monkeypatch):
    """Force the kill switch ON regardless of ambient environment."""
    monkeypatch.setenv(_FLAG, "1")


def test_redundant_support_min_cover_is_one(monkeypatch):
    # One relevant statement supported by BOTH sources -> minimum cover is ONE source (not 0).
    _on(monkeypatch)
    citation = [[1, 1]]
    support = [[1, 1]]
    relevant = [True]
    out = build_source_necessity_disclosure(citation, support, relevant, n_sources=2)
    assert out is not None
    assert out["necessary_sources"] == 1  # min-cover size, was 0 under sole-supporter
    assert out["redundant_sources"] == 1
    assert out["source_necessity_ratio"] == 0.5
    assert out["n_sole_supporter"] == 0  # SECONDARY: neither source is a sole supporter
    assert out["listed_sources"] == 2  # no source dropped


def test_disjoint_support_yields_all_necessary(monkeypatch):
    # Two relevant statements, each with a distinct sole supporter -> cover needs both.
    _on(monkeypatch)
    citation = [[1, 0], [0, 1]]
    support = [[1, 0], [0, 1]]
    relevant = [True, True]
    out = build_source_necessity_disclosure(citation, support, relevant, n_sources=2)
    assert out["necessary_sources"] == 2
    assert out["redundant_sources"] == 0
    assert out["source_necessity_ratio"] == 1.0
    assert out["n_sole_supporter"] == 2  # both are also sole supporters here


def test_ratio_is_correct_for_mixed_case(monkeypatch):
    # 3 sources: src0 covers s0; src1 & src2 co-support s1 (cover picks one of them).
    # Minimum cover = {src0, one of src1/src2} => size 2 of 3 listed.
    _on(monkeypatch)
    citation = [[1, 0, 0], [0, 1, 1]]
    support = [[1, 0, 0], [0, 1, 1]]
    relevant = [True, True]
    out = build_source_necessity_disclosure(citation, support, relevant, n_sources=3)
    assert out["necessary_sources"] == 2
    assert out["redundant_sources"] == 1
    assert out["source_necessity_ratio"] == round(2 / 3, 4)  # 0.6667
    assert out["n_sole_supporter"] == 1  # SECONDARY: only src0 is a sole supporter


def test_irrelevant_statement_creates_no_necessary_source(monkeypatch):
    # A statement with a single supporter but relevant=False must NOT make that source necessary.
    _on(monkeypatch)
    citation = [[1, 0]]
    support = [[1, 0]]
    relevant = [False]
    out = build_source_necessity_disclosure(citation, support, relevant, n_sources=2)
    assert out["necessary_sources"] == 0
    assert out["redundant_sources"] == 2


def test_zero_sources_no_divide_by_zero(monkeypatch):
    _on(monkeypatch)
    out = build_source_necessity_disclosure([], [], [], n_sources=0)
    assert out["necessary_sources"] == 0
    assert out["listed_sources"] == 0
    assert out["redundant_sources"] == 0
    assert out["source_necessity_ratio"] == 0.0


def test_flag_off_returns_none(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    citation = [[1, 0], [0, 1]]
    support = [[1, 0], [0, 1]]
    relevant = [True, True]
    assert build_source_necessity_disclosure(citation, support, relevant, n_sources=2) is None


def test_flag_off_variants_return_none(monkeypatch):
    for off in ("0", "false", "off", "no", "", "FALSE", "Off"):
        monkeypatch.setenv(_FLAG, off)
        assert (
            build_source_necessity_disclosure([[1, 0]], [[1, 0]], [True], n_sources=2) is None
        ), f"OFF value {off!r} should return None"


def test_default_is_on_when_flag_unset(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    out = build_source_necessity_disclosure([[1, 0]], [[1, 0]], [True], n_sources=2)
    assert out is not None
    assert out["necessary_sources"] == 1


def test_disclosure_string_present_and_human_readable(monkeypatch):
    _on(monkeypatch)
    out = build_source_necessity_disclosure([[1, 0]], [[1, 0]], [True], n_sources=2)
    disc = out["disclosure"]
    assert isinstance(disc, str) and disc
    # Must state the cover/listed split and the no-drop guarantee (§-1.3).
    assert "1 of 2" in disc
    assert "MINIMUM COVER" in disc
    assert "not dropped" in disc


def test_reuses_scorer_result(monkeypatch):
    # The wrapper's necessary count MUST equal the WS-14 scorer's min-cover result (no re-impl drift);
    # the secondary field MUST equal the scorer's sole-supporter count.
    _on(monkeypatch)
    support = [[1, 0, 0], [1, 1, 0], [0, 0, 1]]
    relevant = [True, True, True]
    n_sources = 3
    direct_cover = minimum_source_cover_size(support, relevant, n_sources)
    direct_sole = necessary_source_count(support, relevant, n_sources)
    out = build_source_necessity_disclosure(support, support, relevant, n_sources)
    assert out["necessary_sources"] == direct_cover
    assert out["n_sole_supporter"] == direct_sole


def test_no_source_dropped_listed_equals_input(monkeypatch):
    # SURFACING contract: listed_sources always equals n_sources — the builder never filters.
    _on(monkeypatch)
    for n in (1, 2, 5, 9):
        support = [[0] * n]  # zero support -> zero necessary, but every source stays listed
        out = build_source_necessity_disclosure([[0] * n], support, [True], n_sources=n)
        assert out["listed_sources"] == n
        assert out["necessary_sources"] + out["redundant_sources"] == n
