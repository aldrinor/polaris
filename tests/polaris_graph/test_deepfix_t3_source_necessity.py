"""T3 (I-deepfix-001 #1344) — source-necessity min-vertex-cover behavioral tests.

FAIL-LOUD: each test asserts a REAL EFFECT on rendered output / a real graph computation, not a
flag read. RED before src/polaris_graph/synthesis/source_necessity.py existed; GREEN after.
Offline, $0.
"""
from __future__ import annotations

import importlib

import pytest

sn = importlib.import_module("src.polaris_graph.synthesis.source_necessity")


def test_min_vertex_cover_matches_konig_on_known_graph():
    """König: |min vertex cover| == |max matching|. A path graph s1-a, s1-b, s2-b has a matching of
    size 2 and a min cover of size 2 ({s1,b} or {a,s2}); the cover must hit every edge."""
    # left = statements, right = sources
    adjacency = {
        ("stmt", "s1"): [("src", "a"), ("src", "b")],
        ("stmt", "s2"): [("src", "b")],
    }
    left = [("stmt", "s1"), ("stmt", "s2")]
    right = [("src", "a"), ("src", "b")]
    cover_left, cover_right = sn.min_vertex_cover(left, right, adjacency)
    cover = cover_left | cover_right
    # every edge is covered
    for u, vs in adjacency.items():
        for v in vs:
            assert (u in cover) or (v in cover), f"edge {u}-{v} uncovered by {cover}"
    # König optimality: cover size == max matching size (2 here)
    match = sn.hopcroft_karp_matching(adjacency, left)
    assert len(cover) == len(match) == 2


def test_sole_supporter_is_necessary_corroborated_is_redundant():
    """A source that is the ONLY supporter of a statement is NECESSARY; a statement supported by two
    sources makes neither of those two necessary (corroborated = redundant, kept at full weight)."""
    support_by_source = {
        "A": ["claim_1"],            # sole supporter of claim_1 -> necessary
        "B": ["claim_2"],            # co-supporter of claim_2
        "C": ["claim_2"],            # co-supporter of claim_2 -> both redundant
        "D": [],                     # supports nothing -> zero_support
    }
    result = sn.compute_source_necessity(support_by_source, ["A", "B", "C", "D"])
    assert result.listed_sources == 4
    assert "A" in result.necessary_ids
    assert result.necessary_sources == 1
    assert set(result.redundant_ids) == {"B", "C"}
    assert set(result.zero_support_ids) == {"D"}
    # ratio = 1 necessary / 4 listed
    assert result.necessity_ratio == pytest.approx(0.25)


def test_zero_support_bib_nums_only_flags_cited_unsupported():
    support_by_num = {1: ["c1"], 2: ["c2"]}
    # 3 is cited but supports nothing -> zero-support; 1,2 supported; 4 is NOT cited (T2 handles it)
    cited = [1, 2, 3]
    zero = sn.zero_support_bib_nums(support_by_num, cited)
    assert zero == {3}


def test_retype_quarantines_zero_support_entry_and_discloses_necessity():
    """REAL rendered-output effect: a cited but zero-factual-support reference is MOVED out of the
    reference list into the source-necessity audit ledger, load-bearing references STAY, and the
    necessity disclosure line is appended. Nothing is dropped."""
    biblio_section = (
        "\n\n## Bibliography\n"
        "[1] Load-bearing study — https://example.org/a (tier T1)\n"
        "[2] Corroborating study — https://example.org/b (tier T2)\n"
        "[3] Padding source cited but supporting nothing — https://example.org/c (tier T5)\n"
    )
    necessity = sn.compute_source_necessity(
        {1: ["c1"], 2: ["c1"], 3: []}, [1, 2, 3]
    )
    zero = sn.zero_support_bib_nums({1: ["c1"], 2: ["c1"], 3: []}, [1, 2, 3])
    assert zero == {3}
    out = sn.retype_bibliography_by_source_necessity(biblio_section, zero, necessity)

    assert out != biblio_section, "expected the render to change"
    assert sn._LEDGER_HEADER in out, "expected the source-necessity audit ledger header"
    # the padding entry must live UNDER the ledger header, not the reference list
    head, _, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[3] Padding source" in ledger
    assert "[3] Padding source" not in head
    # load-bearing entries stay in the reference list (above the ledger)
    assert "[1] Load-bearing study" in head
    assert "[2] Corroborating study" in head
    # necessity disclosure surfaced with the min-vertex-cover number
    assert "Source necessity (DeepTRACE metric VI" in out
    # nothing dropped: all three entries still present somewhere
    for n in ("[1]", "[2]", "[3]"):
        assert n in out


def test_no_quarantine_still_discloses_necessity_without_moving_entries():
    """When every cited source is load-bearing, no entry moves, but the necessity number is still
    disclosed inline (kept references only) — and no audit-ledger header is emitted."""
    biblio_section = (
        "\n\n## Bibliography\n"
        "[1] Study A — https://example.org/a (tier T1)\n"
        "[2] Study B — https://example.org/b (tier T2)\n"
    )
    necessity = sn.compute_source_necessity({1: ["c1"], 2: ["c2"]}, [1, 2])
    out = sn.retype_bibliography_by_source_necessity(biblio_section, set(), necessity)
    assert sn._LEDGER_HEADER not in out
    assert "Source necessity (DeepTRACE metric VI" in out
    assert "[1] Study A" in out and "[2] Study B" in out


def test_faithfulness_neutral_quarantine_never_touches_necessary_source():
    """A necessary (sole-supporter) source can NEVER be in the zero-support quarantine set — the
    quarantine can only ever raise the honest necessity ratio, never remove a load-bearing source."""
    support_by_num = {1: ["c1"], 2: []}  # 1 sole-supports c1; 2 supports nothing
    necessity = sn.compute_source_necessity(
        {1: ["c1"], 2: []}, [1, 2]
    )
    zero = sn.zero_support_bib_nums(support_by_num, [1, 2])
    # the necessary source (1) is never quarantined (ids surface stringified for disclosure)
    assert "1" in necessity.necessary_ids
    assert 1 not in zero
    assert zero == {2}
