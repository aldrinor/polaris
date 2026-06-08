"""I-cred-006 (Phase 6) — origin-cluster weight-mass aggregator. Offline, deterministic, no network.
Each test maps to a brief acceptance criterion (AC-1..AC-8)."""
from __future__ import annotations

import copy

import pytest

from src.polaris_graph.synthesis.weight_mass import (
    ClaimWeightMass,
    OriginContribution,
    aggregate_weight_mass,
    weight_mass_enabled,
)


def _claim(ccid, eid):
    return type("C", (), {"claim_cluster_id": ccid, "evidence_id": eid})()


def _judg(eid, weight):
    return type("J", (), {"evidence_id": eid, "credibility_weight": weight})()


def _row(eid, ocid, canonical, authority):
    return {
        "evidence_id": eid,
        "origin_cluster_id": ocid,
        "is_canonical_origin": canonical,
        "authority_score": authority,
    }


# ── AC-1 ──────────────────────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_WEIGHT_MASS", raising=False)
    assert weight_mass_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_WEIGHT_MASS", on)
    assert weight_mass_enabled() is True


# ── AC-2: single origin + the vax invariant (copies cannot inflate) ───────────
def test_single_origin_copies_uninflatable():
    rows = [
        _row("e0", "o1", True, 0.8),    # canonical
        _row("e1", "o1", False, 0.3),   # copy
        _row("e2", "o1", False, 0.9),   # copy with HIGHER authority
    ]
    claims = [_claim("c1", "e0"), _claim("c1", "e1"), _claim("c1", "e2")]
    out = aggregate_weight_mass(claims, rows, [_judg("e0", 0.5)])
    assert len(out) == 1
    cm = out[0]
    assert cm.independent_origin_count == 1
    assert abs(cm.weight_mass - 0.8) < 1e-9   # = authority(canonical) ONLY (plan §148)
    assert cm.contributions[0].credibility_weight == 0.5  # credibility is DISCLOSED, not in the mass
    assert cm.contributions[0].copy_count == 2

    # Add MORE copies of ANY authority -> weight_mass is UNCHANGED (the vax-defense).
    rows2 = rows + [_row("e3", "o1", False, 0.99), _row("e4", "o1", False, 0.99)]
    claims2 = claims + [_claim("c1", "e3"), _claim("c1", "e4")]
    out2 = aggregate_weight_mass(claims2, rows2, [_judg("e0", 0.5)])
    assert abs(out2[0].weight_mass - 0.8) < 1e-9
    assert out2[0].independent_origin_count == 1


# ── AC-3: two independent origins sum ─────────────────────────────────────────
def test_two_independent_origins_sum():
    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o2", True, 0.6)]
    claims = [_claim("c1", "e0"), _claim("c1", "e1")]
    cm = aggregate_weight_mass(claims, rows, [])[0]
    assert cm.independent_origin_count == 2
    assert abs(cm.weight_mass - 1.4) < 1e-9  # 0.8*1.0 + 0.6*1.0


# ── AC-4: a higher-authority copy contributes ZERO ────────────────────────────
def test_higher_authority_copy_contributes_zero():
    rows = [_row("e0", "o1", True, 0.2), _row("e1", "o1", False, 0.99)]
    claims = [_claim("c1", "e0"), _claim("c1", "e1")]
    cm = aggregate_weight_mass(claims, rows, [])[0]
    assert abs(cm.weight_mass - 0.2) < 1e-9  # canonical 0.2, never the 0.99 copy


# ── AC-5: canonical with no judgment uses neutral 1.0 ─────────────────────────
def test_canonical_no_judgment_uses_neutral_one():
    cm = aggregate_weight_mass([_claim("c1", "e0")], [_row("e0", "o1", True, 0.7)], [])[0]
    assert abs(cm.weight_mass - 0.7) < 1e-9  # 0.7 * 1.0


# ── AC-6: distinct claim clusters aggregate independently ─────────────────────
def test_distinct_claim_clusters_independent():
    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o2", True, 0.6)]
    claims = [_claim("c1", "e0"), _claim("c2", "e1")]
    by = {c.claim_cluster_id: c for c in aggregate_weight_mass(claims, rows, [])}
    assert abs(by["c1"].weight_mass - 0.8) < 1e-9
    assert abs(by["c2"].weight_mass - 0.6) < 1e-9


# ── AC-7: missing authority on the canonical -> 0.0, no crash ─────────────────
def test_missing_authority_is_zero_no_crash():
    rows = [{"evidence_id": "e0", "origin_cluster_id": "o1", "is_canonical_origin": True}]
    cm = aggregate_weight_mass([_claim("c1", "e0")], rows, [])[0]
    assert cm.weight_mass == 0.0


# ── AC-8: purity — no row mutation ────────────────────────────────────────────
def test_no_row_mutation():
    rows = [_row("e0", "o1", True, 0.8)]
    before = copy.deepcopy(rows)
    aggregate_weight_mass([_claim("c1", "e0")], rows, [_judg("e0", 0.5)])
    assert rows == before


def test_uncollapsed_row_is_its_own_origin():
    """A row with no origin_cluster_id is treated as its OWN independent origin (never a copy)."""
    rows = [{"evidence_id": "e0", "authority_score": 0.5, "is_canonical_origin": False}]
    cm = aggregate_weight_mass([_claim("c1", "e0")], rows, [])[0]
    assert cm.independent_origin_count == 1
    assert abs(cm.weight_mass - 0.5) < 1e-9


# ── Codex #1155 P2-1: the binding invariant is NO INFLATION (monotonic non-increase) ──
def test_lower_authority_copy_becoming_canonical_lowers_mass_never_inflates():
    """If Phase-4's conservative-min re-marks a LOWER-authority member as canonical (all-undated
    case), the mass DROPS — monotonically non-increasing under copy additions, never inflating."""
    high = aggregate_weight_mass([_claim("c1", "e0")], [_row("e0", "o1", True, 0.8)], [])[0]
    assert abs(high.weight_mass - 0.8) < 1e-9
    # A lower-authority copy is added AND marked canonical (Phase-4 conservative-min); e0 demoted.
    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", True, 0.3)]
    low = aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])[0]
    assert low.weight_mass <= high.weight_mass        # never increases
    assert abs(low.weight_mass - 0.3) < 1e-9


def test_credibility_is_disclosed_not_a_mass_factor_no_inflation():
    """Codex #1155 iter-2 P1: cluster_mass = authority(canonical) ONLY. A high-authority / LOW-
    credibility origin must NOT be overtaken (inflated) by adding a lower-authority copy with no
    judgment — the bug that folding credibility into the mass would cause (0.8*0.1=0.08 < 0.3)."""
    before = aggregate_weight_mass(
        [_claim("c1", "e0")], [_row("e0", "o1", True, 0.8)], [_judg("e0", 0.1)])[0]
    assert abs(before.weight_mass - 0.8) < 1e-9   # authority ONLY, never 0.8*0.1
    # A lower-authority copy with NO judgment is re-marked canonical (Phase-4 conservative-min).
    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", True, 0.3)]
    after = aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [_judg("e0", 0.1)])[0]
    assert after.weight_mass <= before.weight_mass  # NO inflation
    assert abs(after.weight_mass - 0.3) < 1e-9


# ── Codex #1155 P2-2: copy-only support uses the GLOBAL canonical, not the copy ──
def test_copy_only_support_uses_global_canonical():
    """A claim cluster supported ONLY by a derivative copy uses the GLOBAL Phase-4 canonical row's
    authority for that origin, not the copy's own."""
    rows = [_row("e0", "o1", True, 0.9), _row("e1", "o1", False, 0.1)]  # canonical e0 supports c2 only
    claims = [_claim("c2", "e0"), _claim("c1", "e1")]
    by = {c.claim_cluster_id: c for c in aggregate_weight_mass(claims, rows, [])}
    assert abs(by["c1"].weight_mass - 0.9) < 1e-9  # uses canonical e0's 0.9, NOT copy e1's 0.1
    assert by["c1"].contributions[0].copy_count == 1  # e1 is a derivative copy backing c1 (no undercount)


# ── Codex #1155 P1-1: canonical metadata is a required, validated precondition (fail-loud) ──
def test_duplicate_canonical_fails_loud():
    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o1", True, 0.6)]  # TWO canonicals for one origin
    raised = False
    try:
        aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])
    except ValueError as exc:
        raised = True
        assert "EXACTLY ONE" in str(exc)
    assert raised, "duplicate canonical must fail loud"


def test_missing_canonical_fails_loud():
    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", False, 0.6)]  # NO canonical for a collapsed origin
    raised = False
    try:
        aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])
    except ValueError:
        raised = True
    assert raised, "a collapsed origin with no canonical must fail loud, never fail-soft to a copy"
