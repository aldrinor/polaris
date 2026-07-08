"""I-deepfix-001 (#1369) DEPTH Step 4 — two-sided debate block (both_sides composer + renderer).

Proves compose_both_sides turns a ContradictionEdge + two ClaimWeightMass + two AtomicClaims into ONE
BothSidesBlock with two SidePositions ordered by evidence weight DESC (never by "correctness"), each
carrying its own evidence_ids and origin count; and that render_both_sides emits NEUTRAL framing (no
"fringe/debunked/discredited" labels), showing both positions. Pure/offline: SimpleNamespace inputs,
zero network. (The render-seam wiring into the assembler is a separate integration; the composer + its
kill-switch PG_SWEEP_BOTHSIDES_DISCLOSURE are proven here.)
"""

import types

import pytest

from src.polaris_graph.synthesis.both_sides import compose_both_sides, render_both_sides


def _edge(ids, subject, source="qualitative", severity="review"):
    return types.SimpleNamespace(
        claim_cluster_ids=tuple(ids), subject=subject, predicate="", source=source, severity=severity,
    )


def _wm(ccid, weight, origins):
    return types.SimpleNamespace(
        claim_cluster_id=ccid, weight_mass=weight, independent_origin_count=origins,
    )


def _claim(ccid, subject, predicate, text, eid):
    return types.SimpleNamespace(
        claim_cluster_id=ccid, subject=subject, predicate=predicate, text=text, evidence_id=eid,
    )


def test_compose_two_sides_ordered_by_weight_desc():
    edge = _edge(("cA", "cB"), "automation net effect on labor")
    wms = [_wm("cA", 0.8, 3), _wm("cB", 0.4, 2)]
    claims = [
        _claim("cA", "automation", "displaces labor", "Automation displaces labor in exposed tasks", "e1"),
        _claim("cB", "automation", "complements labor", "Automation complements labor and raises demand", "e2"),
    ]
    blocks = compose_both_sides([edge], wms, claims)
    assert len(blocks) == 1
    b = blocks[0]
    assert len(b.sides) == 2
    # ordered by evidence weight DESC (0.8 before 0.4) — discloses weight, never asserts correctness
    assert b.sides[0].claim_cluster_id == "cA"
    assert b.sides[0].weight_mass >= b.sides[1].weight_mass
    # each side carries its OWN evidence ids + origin count (one-click provenance)
    assert b.sides[0].evidence_ids == ("e1",)
    assert b.sides[1].evidence_ids == ("e2",)
    assert b.sides[0].independent_origin_count == 3
    assert b.sides[1].independent_origin_count == 2


def test_verified_count_overwrite_uses_own_basket():
    edge = _edge(("cA", "cB"), "x")
    wms = [_wm("cA", 0.9, 1), _wm("cB", 0.5, 1)]
    claims = [_claim("cA", "a", "p", "A stmt", "e1"), _claim("cB", "a", "p", "B stmt", "e2")]
    blocks = compose_both_sides([edge], wms, claims, verified_count_by_cluster={"cA": 4, "cB": 2})
    side_a = next(s for s in blocks[0].sides if s.claim_cluster_id == "cA")
    assert side_a.independent_origin_count == 4  # own basket verified count overwrites legacy


def test_edge_with_one_cluster_is_skipped():
    edge = _edge(("cA",), "only one side")
    assert compose_both_sides([edge], [], []) == []


def test_render_is_neutral_and_shows_both_positions():
    edge = _edge(("cA", "cB"), "automation net effect on labor")
    wms = [_wm("cA", 0.8, 3), _wm("cB", 0.4, 2)]
    claims = [
        _claim("cA", "a", "displaces", "Automation displaces labor", "e1"),
        _claim("cB", "a", "complements", "Automation complements labor", "e2"),
    ]
    out = render_both_sides(compose_both_sides([edge], wms, claims))
    low = out.lower()
    for banned in ("fringe", "debunked", "discredited", "conspiracy", "correct", "wrong"):
        assert banned not in low, f"non-neutral framing leaked: {banned!r}"
    assert "Automation displaces labor" in out
    assert "Automation complements labor" in out
    assert "evidence weight" in low  # discloses weight, not a verdict


def test_render_empty_is_byte_identical_empty():
    assert render_both_sides([]) == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
