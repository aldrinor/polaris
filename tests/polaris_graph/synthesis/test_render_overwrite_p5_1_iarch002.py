"""I-arch-002 (#1246) [10] / P5.1 — Reading-A OVERWRITE of the single
``independent_origin_count`` render field with the basket
``verified_support_origin_count``, at BOTH render surfaces.

Offline, deterministic, no network. These are §8 tests #10 (both_sides mixed basket
rendered count == verified count) and #18 (the operator-visible ``claim_disclosure.json``
emit carries the verified count, not the clustered/unverified one), plus the
default-OFF byte-identity guard.

THE TRAP these tests pin (advisor): a mixed basket has clustered (``total_clustered_origin_count``)
= 2 but isolated-verified (``verified_support_origin_count``) = 1. The overwrite MUST surface 1
— grabbing the adjacent ``total_clustered_origin_count`` would silently re-surface the clustered
count P5.1 exists to kill, so every assertion below is ``== 1`` against a clustered-2 basket.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.synthesis.credibility_pass import ClaimBasket
from src.polaris_graph.synthesis.both_sides import (
    compose_both_sides,
    render_both_sides,
)
from src.polaris_graph.synthesis.disclosure_population import populate_disclosure
from src.polaris_graph.generator.provenance_generator import SentenceVerification
from scripts.run_honest_sweep_r3 import _build_claim_disclosure_doc


def _basket(ccid, *, clustered, verified):
    """A MIXED basket: clustered (advisory, not-verified) count != isolated-verified count.

    clustered=2 / verified=1 is the laundering-bait case — surfacing 2 would re-leak the
    clustered count; the overwrite must surface 1.
    """
    return ClaimBasket(
        claim_cluster_id=ccid,
        claim_text="drug X reduced the rate by 30 percent",
        subject="drug X",
        predicate="reduced the rate",
        supporting_members=[],
        refuter_cluster_ids=(),
        weight_mass=0.8,
        total_clustered_origin_count=clustered,
        verified_support_origin_count=verified,
        basket_verdict="partial",
    )


def _sv(sentence, eids, is_verified=True):
    return SentenceVerification(
        sentence=sentence,
        tokens=[SimpleNamespace(evidence_id=e, start=0, end=1) for e in eids],
        is_verified=is_verified,
    )


def _edge(ccids, subject="drug X", predicate="rate", source="numeric", severity="review"):
    return type("E", (), {"claim_cluster_ids": tuple(ccids), "subject": subject,
                          "predicate": predicate, "source": source, "severity": severity})()


def _cwm(ccid, weight, clustered_origins):
    """A Phase-6 weight-mass row whose independent_origin_count is the CLUSTERED count."""
    return type("W", (), {"claim_cluster_id": ccid, "weight_mass": weight,
                          "independent_origin_count": clustered_origins})()


def _claim(ccid, eid, subject="drug X", predicate="rate", text=""):
    return type("C", (), {"claim_cluster_id": ccid, "evidence_id": eid,
                          "subject": subject, "predicate": predicate, "text": text})()


# ── §8 test #10 — both_sides mixed basket: rendered count == verified count ───────
def test_both_sides_rendered_count_equals_verified_count():
    """A side whose basket is clustered=2 / verified=1 renders 1 independent origin, not 2.

    The cwm carries the CLUSTERED count (2); the threaded basket carries the isolated-verified
    count (1). Reading-A overwrite => SidePosition.independent_origin_count == 1, and the
    rendered markdown says "1 independent origin(s)" — never the clustered 2.
    """
    verified_by_cluster = {"cA": 1, "cB": 1}  # both baskets verified=1 (clustered would be 2)
    blocks = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 2), _cwm("cB", 0.2, 2)],  # clustered origins = 2 on BOTH
        [_claim("cA", "e0", text="rate fell 30%"), _claim("cB", "e1", text="rate rose 30%")],
        verified_count_by_cluster=verified_by_cluster,
    )
    assert len(blocks) == 1
    sides = blocks[0].sides
    # Each side surfaces ITS OWN basket's verified count (1), NOT the clustered 2.
    for side in sides:
        assert side.independent_origin_count == 1, (
            f"side {side.claim_cluster_id} surfaced {side.independent_origin_count}; "
            "expected the isolated-verified 1, not the clustered 2"
        )
    rendered = render_both_sides(blocks)
    assert "1 independent origin(s)" in rendered
    assert "2 independent origin(s)" not in rendered  # the clustered count must NOT leak


def test_both_sides_overwrites_per_side_not_other_sides_count():
    """The overwrite is per-side: side cA surfaces cA's basket count, cB surfaces cB's — never
    a cross-side / sentence-wide count (multi-cluster invariant for the contested case)."""
    blocks = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 5), _cwm("cB", 0.2, 5)],
        [_claim("cA", "e0"), _claim("cB", "e1")],
        verified_count_by_cluster={"cA": 3, "cB": 1},
    )
    by_id = {s.claim_cluster_id: s for s in blocks[0].sides}
    assert by_id["cA"].independent_origin_count == 3
    assert by_id["cB"].independent_origin_count == 1


# ── §8 test #18 — operator-visible claim_disclosure.json emit carries verified count ──
def test_claim_disclosure_emit_surfaces_verified_not_clustered_count():
    """#18: assert against the OPERATOR-VISIBLE emit (_build_claim_disclosure_doc), not
    populate_disclosure's bare return.

    Build SVs populated WITH the threaded basket (clustered=2 / verified=1), hang them off a
    SectionResult-shaped ``multi`` with credibility_analysis non-None, then run the runner's
    emit builder and assert the JSON row's ``independent_origin_count`` == the verified 1.
    """
    # Two cited sources in one cluster cA: clustered origin count would be 2, basket verified = 1.
    origin_by_evidence = {"e0": "o1", "e1": "o2"}      # 2 distinct origin clusters => clustered=2
    cluster_id_by_evidence = {"e0": ["cA"], "e1": ["cA"]}
    baskets = [_basket("cA", clustered=2, verified=1)]

    populated = populate_disclosure(
        [_sv("drug X reduced the rate by 30 percent", ["e0", "e1"], is_verified=True)],
        {"e0": 0.9, "e1": 0.9},
        origin_by_evidence,
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )
    # The populate-layer overwrite already fired: clustered would be 2, verified is 1.
    assert populated[0].independent_origin_count == 1

    multi = SimpleNamespace(
        credibility_analysis=SimpleNamespace(),   # non-None => emit builder runs
        sections=[SimpleNamespace(
            title="Findings",
            dropped_due_to_failure=False,
            kept_sentences_pre_resolve=populated,
        )],
    )
    doc = _build_claim_disclosure_doc(multi, {})
    assert doc is not None
    row = doc["sections"][0]["claims"][0]
    assert row["independent_origin_count"] == 1, (
        "the operator-visible emit must carry the basket verified_support_origin_count (1), "
        "never the clustered/unverified count (2)"
    )
    # certainty is bucketed on the SAME surfaced verified count (advisor trap #2): verified=1 < the
    # default high_min_origins=2, so a single verified origin cannot read "high".
    assert row["certainty_label"] != "high"


def test_multi_cluster_sentence_surfaces_conservative_single_basket_count():
    """Multi-cluster-sentence rule (design §5 FIX-4): a sentence citing tokens across >1 cluster
    surfaces a CONSERVATIVE single-basket value (MIN of the cited clusters' verified counts) —
    never a sum/union, never the larger cluster's count. e0->cA(verified=3), e1->cB(verified=1):
    one sentence citing both surfaces 1 (the weakest), proving the branch is single-basket and
    safety-down, with the invariant surfaced(1) <= max single-basket(3) and != sum(4).
    """
    populated = populate_disclosure(
        [_sv("a sentence spanning two distinct claim clusters", ["e0", "e1"], is_verified=True)],
        {"e0": 0.9, "e1": 0.9},
        {"e0": "o1", "e1": "o2"},
        baskets=[
            _basket("cA", clustered=4, verified=3),
            _basket("cB", clustered=4, verified=1),
        ],
        cluster_id_by_evidence={"e0": ["cA"], "e1": ["cB"]},
    )
    surfaced = populated[0].independent_origin_count
    assert surfaced == 1, f"multi-cluster sentence surfaced {surfaced}; expected conservative MIN 1"
    assert surfaced != 4   # never the sum/union across clusters
    assert surfaced <= 3   # invariant: <= max single-basket verified count


def test_certainty_routed_through_verified_count_not_clustered():
    """Advisor trap #2: certainty_label must bucket on the SURFACED (verified) count.

    Clustered=2 would clear the default high_min_origins=2 threshold and (with high credibility)
    read "high"; the basket verified count is 1, so the row must NOT read "high".
    """
    populated = populate_disclosure(
        [_sv("s", ["e0", "e1"], is_verified=True)],
        {"e0": 0.95, "e1": 0.95},                 # high credibility
        {"e0": "o1", "e1": "o2"},                 # clustered origins = 2
        baskets=[_basket("cA", clustered=2, verified=1)],
        cluster_id_by_evidence={"e0": ["cA"], "e1": ["cA"]},
    )
    assert populated[0].independent_origin_count == 1
    assert populated[0].certainty_label != "high"  # 1 verified origin < high_min_origins(2)


# ── default-OFF byte-identity guard (checklist: test_contract_site_flag_off_byte_identical) ──
def test_contract_site_flag_off_byte_identical():
    """No basket threaded (the OFF default) => BOTH surfaces emit exactly the legacy clustered count.

    This is the byte-identity contract: omitting the new optional params reproduces the pre-P5.1
    behaviour at both render surfaces, sentence-for-sentence and side-for-side.
    """
    # populate_disclosure: legacy clustered origin count (2 distinct origins) preserved.
    off = populate_disclosure(
        [_sv("s", ["e0", "e1"], is_verified=True)],
        {"e0": 0.9, "e1": 0.9},
        {"e0": "o1", "e1": "o2"},
    )
    assert off[0].independent_origin_count == 2  # the clustered count, unchanged

    # And passing baskets=None / cluster_id_by_evidence=None explicitly is identical.
    off_explicit = populate_disclosure(
        [_sv("s", ["e0", "e1"], is_verified=True)],
        {"e0": 0.9, "e1": 0.9},
        {"e0": "o1", "e1": "o2"},
        baskets=None,
        cluster_id_by_evidence=None,
    )
    assert off_explicit[0].independent_origin_count == 2

    # compose_both_sides: legacy cwm.independent_origin_count (clustered) preserved when no map.
    block = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
        [_claim("cA", "e0"), _claim("cB", "e1")],
    )[0]
    by_id = {s.claim_cluster_id: s for s in block.sides}
    assert by_id["cA"].independent_origin_count == 3  # clustered, unchanged
    assert by_id["cB"].independent_origin_count == 1


def test_unmapped_sentence_keeps_legacy_count_when_basket_threaded():
    """A row whose cited evidence maps to NO threaded basket keeps the legacy clustered count
    (the overwrite returns None for it) — even while OTHER rows in the same call are overwritten.
    Never fabricates a zero for an unmapped sentence."""
    populated = populate_disclosure(
        [
            _sv("mapped", ["e0"], is_verified=True),      # maps to basket cA (verified=1)
            _sv("unmapped", ["eX"], is_verified=True),    # no basket -> legacy clustered count
        ],
        {},
        {"e0": "o1", "eX": "oZ"},
        baskets=[_basket("cA", clustered=2, verified=1)],
        cluster_id_by_evidence={"e0": ["cA"]},            # eX absent from the binding
    )
    assert populated[0].independent_origin_count == 1     # overwritten to verified
    assert populated[1].independent_origin_count == 1     # legacy: 1 distinct origin (oZ), unchanged
