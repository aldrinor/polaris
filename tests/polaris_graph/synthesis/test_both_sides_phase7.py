"""I-cred-007 (Phase 7) — neutral both-sides composer. Offline, deterministic, no network."""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis.both_sides import (
    BothSidesBlock,
    SidePosition,
    bothsides_disclosure_enabled,
    compose_both_sides,
    render_both_sides,
)

_BANNED = ["fringe", "misinformation", "debunked", "conspiracy", "warning",
           "unreliable", "false claim", "discredited"]


def _edge(ccids, subject="vaccine safety", predicate="rate", source="numeric", severity="review"):
    return type("E", (), {"claim_cluster_ids": tuple(ccids), "subject": subject,
                          "predicate": predicate, "source": source, "severity": severity})()


def _cwm(ccid, weight, origins):
    return type("W", (), {"claim_cluster_id": ccid, "weight_mass": weight,
                          "independent_origin_count": origins})()


def _claim(ccid, eid, subject="vaccine safety", predicate="rate", text=""):
    return type("C", (), {"claim_cluster_id": ccid, "evidence_id": eid,
                          "subject": subject, "predicate": predicate, "text": text})()


# ── AC-1 ──────────────────────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_BOTHSIDES_DISCLOSURE", raising=False)
    assert bothsides_disclosure_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_BOTHSIDES_DISCLOSURE", on)
    assert bothsides_disclosure_enabled() is True


# ── AC-2: single edge, two sides ordered by weight DESC ──────────────────────
def test_single_edge_two_sides_ordered_by_weight():
    blocks = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
        [_claim("cA", "e0"), _claim("cB", "e1")],
    )
    assert len(blocks) == 1
    b = blocks[0]
    assert len(b.sides) == 2
    assert b.sides[0].claim_cluster_id == "cA"  # higher weight first
    assert abs(b.sides[0].weight_mass - 0.9) < 1e-9 and b.sides[0].independent_origin_count == 3
    assert abs(b.sides[1].weight_mass - 0.2) < 1e-9 and b.sides[1].independent_origin_count == 1
    assert b.sides[0].evidence_ids == ("e0",)


# ── AC-3: render([]) is byte-empty (default-OFF byte-identity) ───────────────
def test_render_empty_is_byte_empty():
    assert render_both_sides([]) == ""
    assert compose_both_sides([], [], []) == []


# ── AC-4: neutral language + both weights shown ──────────────────────────────
def test_render_is_neutral_and_shows_both_weights():
    text = render_both_sides(compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
        [_claim("cA", "e0"), _claim("cB", "e1")],
    )).lower()
    for banned in _BANNED:
        assert banned not in text, f"neutral-language guardrail: '{banned}' must not appear"
    assert "0.90" in text and "0.20" in text  # BOTH sides' weights are disclosed
    assert "diverge" in text and "weigh" in text  # neutral frame, user judges


# ── AC-5: a claim with no contradiction edge produces no block ───────────────
def test_claim_with_no_edge_no_block():
    assert compose_both_sides([], [_cwm("cA", 0.9, 3)],
                              [_claim("cA", "e0"), _claim("cB", "e1")]) == []


# ── AC-6: the low-weight side is shown, never dropped ────────────────────────
def test_low_weight_side_not_dropped():
    b = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.99, 5), _cwm("cB", 0.01, 1)],
        [_claim("cA", "e0"), _claim("cB", "e1")],
    )[0]
    assert len(b.sides) == 2
    assert any(s.claim_cluster_id == "cB" for s in b.sides)  # low-weight side present
    assert "0.01" in render_both_sides([b])


# ── AC-7: missing weight_mass -> 0.0 / 0 fail-soft (no crash, no fabrication) ─
def test_missing_weight_is_fail_soft():
    b = compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 3)],  # cB has NO weight entry
        [_claim("cA", "e0"), _claim("cB", "e1")],
    )[0]
    side_b = next(s for s in b.sides if s.claim_cluster_id == "cB")
    assert side_b.weight_mass == 0.0 and side_b.independent_origin_count == 0


# ── AC-8: purity — inputs not mutated ────────────────────────────────────────
def test_no_input_mutation():
    weights = [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)]
    claims = [_claim("cA", "e0"), _claim("cB", "e1")]
    compose_both_sides([_edge(["cA", "cB"])], weights, claims)
    assert weights[0].weight_mass == 0.9 and claims[0].evidence_id == "e0"


def test_edge_with_one_cluster_is_skipped():
    """An edge with fewer than two claim_cluster_ids produces no block (needs two positions)."""
    assert compose_both_sides([_edge(["cA"])], [_cwm("cA", 0.9, 3)], [_claim("cA", "e0")]) == []


def test_render_includes_each_sides_claim_statement():
    """Codex #1156 P1: the disclosure must state WHAT each side asserts (its claim text), not just its
    weight, so the user can actually judge between the two positions (plan §9.3)."""
    text = render_both_sides(compose_both_sides(
        [_edge(["cA", "cB"])],
        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
        [
            _claim("cA", "e0", text="The vaccine reduced hospitalization by 80 percent."),
            _claim("cB", "e1", text="The vaccine showed no significant effect on hospitalization."),
        ],
    ))
    assert "reduced hospitalization by 80 percent" in text
    assert "no significant effect on hospitalization" in text
