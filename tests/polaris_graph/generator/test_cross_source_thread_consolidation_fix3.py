"""I-deepfix-001 FIX 3 (#1344) — cross-source consolidation AGREEMENT-MAP threading.

ROOT (composition_collapse_fix_plan.md FIX 3): cross_source_body fired plan_driven but
``input_threaded=False degraded=True pairs=0`` — the caller
(``verified_compose._compose_section_per_basket``) threaded ONLY ``edges`` and never an ``agree_map`` /
``equiv_clusters``, so two DISTINCT baskets carrying the SAME corroborated claim could not admit a
plan-driven candidate from consolidation. FIX 3 builds a per-section bidirectional-equivalence
``agree_map`` (``build_basket_agreement_map``) from the SAME certified NLI merge predicate the
consolidation leg uses and threads it, so ``input_threaded=True`` and real pairs form.

ISOLATED + OFFLINE: no paid API, no GPU, no model. The certified NLI is driven with a DETERMINISTIC stub
``entail_fn``; the per-clause re-verify invariant runs through the REAL
``verified_compose._compose_one_basket`` path with a RECORDING stub ``verify_fn`` (the SAME own-pool gate
the composer uses), so the P1#2 re-pass asserts on the ACTUAL rendered atoms from ``units[0]`` — never a
reconstructed span.

Asserts:
  1. build map OFF (flag unset) => {} (byte-identical: no map threaded, ``input_threaded`` stays False).
  2. build map ON + bidirectional agree => a real ``cluster -> {cluster}`` map (the threading input).
  3. build map ON + one-way entail => {} (fail-closed: a one-way entailment is NOT an agreement).
  4. FAIL-CLOSED (Codex #1344 iter-1 P1#1): a RAISED entail_fn exception => {} and NO propagation.
  5. CORE: with the built map threaded, the composer logs ``input_threaded=True`` + ``pairs>=1`` and
     the surviving ``units[0]`` two OUTPUT atoms re-pass the SAME strict_verify gate (Codex iter-1 P1#2).
  6. CALLER SEAM: ``_compose_section_per_basket`` under the three flags builds + threads the map so the
     composer logs ``input_threaded=True`` end-to-end at the real fix site.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import pytest

# Repo root on path.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no judge calls, no network entailment, deterministic render-chrome behavior.
os.environ.setdefault("PG_VERIFICATION_MODE", "off")
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

from src.polaris_graph.generator import cross_source_synthesis as css  # noqa: E402
from src.polaris_graph.generator import verified_compose as vc  # noqa: E402
from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: E402
    LICENSED_CONNECTIVES,
    build_basket_agreement_map,
    compose_cross_source_analytical_units,
    cross_source_thread_consolidation_enabled,
)
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402

_CONSOLIDATION_FLAG = "PG_CROSS_SOURCE_THREAD_CONSOLIDATION"
_TOK = re.compile(r"\[#ev:([A-Za-z0-9_]+):")


# ── tiny builders (mirror test_cross_source_body_wave2a.py) ────────────────────────────────────────
def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url="", source_tier="",
        origin_cluster_id=f"origin::{eid}", credibility_weight=1.0, authority_score=1.0,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, subject: str, predicate: str, eids, *, quotes=None, claim_text=None) -> ClaimBasket:
    quotes = quotes or {}
    members = [_member(e, quotes.get(e, f"{subject} {predicate} finding.")) for e in eids]
    return ClaimBasket(
        claim_cluster_id=cluster_id, claim_text=claim_text if claim_text is not None else f"{subject} {predicate}",
        subject=subject, predicate=predicate, supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.0, total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members), basket_verdict="full",
    )


def _both_true(_p, _h):
    return True


def _forward_only(premise, hypothesis):
    # entails A->B only (premise is text_a, hypothesis is text_b); the reverse is a confident non-entail.
    return premise.startswith("Study A")


def _raiser(_p, _h):
    raise RuntimeError("simulated NLI infra fault")


# ── 1-3. build_basket_agreement_map decision table ─────────────────────────────────────────────────
def test_build_map_off_returns_empty(monkeypatch):
    monkeypatch.delenv(_CONSOLIDATION_FLAG, raising=False)
    assert not cross_source_thread_consolidation_enabled()
    a = _basket("cA", "drug x", "reduces a1c", ["eA"], claim_text="Study A reported an effect")
    b = _basket("cB", "drug x", "reduces a1c", ["eB"], claim_text="Study B reported an effect")
    assert build_basket_agreement_map([a, b], entail_fn=_both_true) == {}


def test_build_map_on_bidirectional_agrees(monkeypatch):
    monkeypatch.setenv(_CONSOLIDATION_FLAG, "1")
    a = _basket("cA", "drug x", "reduces a1c", ["eA"], claim_text="Study A reported an effect")
    b = _basket("cB", "drug x", "reduces a1c", ["eB"], claim_text="Study B reported an effect")
    out = build_basket_agreement_map([a, b], entail_fn=_both_true)
    assert out == {"cA": {"cB"}, "cB": {"cA"}}


def test_build_map_on_one_way_no_entry(monkeypatch):
    monkeypatch.setenv(_CONSOLIDATION_FLAG, "1")
    a = _basket("cA", "drug x", "reduces a1c", ["eA"], claim_text="Study A reported an effect")
    b = _basket("cB", "drug x", "reduces a1c", ["eB"], claim_text="Study B reported an effect")
    # forward-only (A entails B, B does NOT entail A) is a one-way entailment, NOT a bidirectional
    # equivalence => fail-closed to no agreement (never a fabricated "consistent with").
    assert build_basket_agreement_map([a, b], entail_fn=_forward_only) == {}


# ── 4. FAIL-CLOSED (Codex #1344 iter-1 P1#1): a raised entail_fn exception must not abort ────────────
def test_build_map_fail_closed_on_entail_exception(monkeypatch, caplog):
    monkeypatch.setenv(_CONSOLIDATION_FLAG, "1")
    a = _basket("cA", "drug x", "reduces a1c", ["eA"], claim_text="Study A reported an effect")
    b = _basket("cB", "drug x", "reduces a1c", ["eB"], claim_text="Study B reported an effect")
    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.generator.cross_source_synthesis"):
        # Must NOT raise (before FIX 3 iter-2 this propagated and aborted the composer).
        out = build_basket_agreement_map([a, b], entail_fn=_raiser)
    assert out == {}, "a raised NLI exception must fail closed to an empty map, never a fabricated entry"
    assert any("fails closed" in r.getMessage() for r in caplog.records), "fail-closed must be logged loud"


# ── helpers for the composer output-atom re-verify (P1#2) ──────────────────────────────────────────
def _make_writer():
    def _w(basket, _scoped_pool):
        m = basket.supporting_members[0]
        q = m.direct_quote
        return f"{q} [#ev:{m.evidence_id}:0-{len(q)}]"
    return _w


class _VR:
    def __init__(self, sentence, is_verified):
        self.sentence = sentence
        self.is_verified = is_verified
        self.failure_reasons = [] if is_verified else ["stub_reject"]


def _make_recording_verify(seen_pools: list):
    """The SAME own-pool gate the composer uses: passes iff the sentence's cited ev_id is in THAT scoped
    pool (emulates strict_verify's own-pool gate). Re-used for the P1#2 re-pass on rendered atoms."""
    def _verify(sentence, scoped_pool):
        seen_pools.append(set(scoped_pool.keys()))
        cited = {m.group(1) for m in _TOK.finditer(sentence or "")}
        ok = bool(cited) and cited <= set(scoped_pool.keys())
        return _VR(sentence, ok)
    return _verify


def _split_rendered_atoms(unit: str) -> list[str]:
    """Split a rendered analytical sentence into its two OUTPUT atoms on the licensed connective — so the
    re-verify runs on the ACTUAL rendered clause text from ``units[0]`` (Codex iter-1 P1#2), NOT a
    reconstruction from the pool."""
    for conn in LICENSED_CONNECTIVES.values():
        if conn in unit:
            return [part.strip() for part in unit.split(conn) if part.strip()]
    return [unit.strip()]


# ── 5. CORE: threaded map => input_threaded=True + pairs>=1 + output atoms re-pass strict_verify ────
def test_composer_input_threaded_true_and_output_atoms_reverify(monkeypatch, caplog):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv(_CONSOLIDATION_FLAG, "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")  # keep the synthetic sentence deterministic
    # Two DISTINCT-cluster baskets carrying the SAME corroborated claim (same facet, distinct sources).
    qa, qb = "Study A reported a fifteen percent gain.", "Study B reported a fifteen percent gain."
    a = _basket("cA", "productivity", "rose", ["eA"], quotes={"eA": qa}, claim_text="productivity rose fifteen percent")
    b = _basket("cB", "productivity", "rose", ["eB"], quotes={"eB": qb}, claim_text="productivity rose fifteen percent")
    pool = {"eA": {"direct_quote": qa}, "eB": {"direct_quote": qb}}
    # The threaded agree_map (built exactly as the caller builds it) — non-empty => input_threaded=True.
    agree_map = build_basket_agreement_map([a, b], entail_fn=_both_true)
    assert agree_map, "precondition: the corroborating pair must produce a non-empty agree_map"

    seen_pools: list = []
    with caplog.at_level(logging.INFO, logger="src.polaris_graph.generator.cross_source_synthesis"):
        units = compose_cross_source_analytical_units(
            [a, b], pool, writer_fn=_make_writer(), verify_fn=_make_recording_verify(seen_pools),
            agree_map=agree_map, entail_fn=_both_true,
        )
    # (a) the activation marker proves input_threaded=True + pairs>=1 (the FIX 3 acceptance criterion).
    marker = next(
        (r.getMessage() for r in caplog.records if "cross_source_body: plan_driven" in r.getMessage()), "",
    )
    assert "input_threaded=True" in marker, f"expected input_threaded=True, got: {marker!r}"
    assert "degraded=False" in marker, f"expected degraded=False, got: {marker!r}"
    assert re.search(r"pairs=[1-9]", marker), f"expected pairs>=1, got: {marker!r}"
    # (b) a real cross-source unit formed and used the agreement connective (both-True NLI + agree_map).
    assert len(units) == 1
    assert LICENSED_CONNECTIVES["agreement"] in units[0]
    # (c) Codex iter-1 P1#2: the TWO OUTPUT atoms rendered in units[0] each re-pass the SAME strict_verify
    # own-pool gate — asserted on the RENDERED clause text, not a reconstructed span+token.
    atoms = _split_rendered_atoms(units[0])
    assert len(atoms) == 2, f"expected two rendered atoms, got {atoms!r}"
    reverify = _make_recording_verify([])
    for atom in atoms:
        cited = {m.group(1) for m in _TOK.finditer(atom)}
        assert len(cited) == 1, f"each rendered atom must carry exactly one provenance token: {atom!r}"
        eid = next(iter(cited))
        scoped = {eid: pool[eid]}  # the atom's OWN source pool
        res = reverify(atom, scoped)
        assert res.is_verified, f"rendered output atom failed strict_verify re-pass: {atom!r}"


# ── 6. CALLER SEAM: _compose_section_per_basket builds + threads the map end-to-end ────────────────
def test_caller_seam_builds_and_threads_map(monkeypatch, caplog):
    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "1")
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv(_CONSOLIDATION_FLAG, "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")   # keep the per-basket loop minimal/deterministic
    monkeypatch.delenv("PG_VERIFIED_COMPOSE_MULTICITED", raising=False)
    monkeypatch.delenv("PG_SUBTOPIC_ADDITIVE_FACTS", raising=False)
    monkeypatch.delenv("PG_QUALIFIER_ELABORATION", raising=False)
    # Fix 2 (2026-07-10): PG_ABSTRACTIVE_WRITER / PG_SYNTH_PRIMARY now DEFAULT-ON; this offline test
    # exercises the deterministic legacy body (no model), so pin BOTH flags OFF explicitly.
    monkeypatch.setenv("PG_ABSTRACTIVE_WRITER", "0")
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "0")
    # The caller builds the map with NO entail_fn => it uses _default_entail_fn; stub that to both-True so
    # the section's corroborating pair agrees OFFLINE (no model load).
    monkeypatch.setattr(css, "_default_entail_fn", lambda: _both_true)

    qa, qb = "Study A reported a fifteen percent gain.", "Study B reported a fifteen percent gain."
    a = _basket("cA", "productivity", "rose", ["eA"], quotes={"eA": qa}, claim_text="productivity rose fifteen percent")
    b = _basket("cB", "productivity", "rose", ["eB"], quotes={"eB": qb}, claim_text="productivity rose fifteen percent")
    pool = {"eA": {"direct_quote": qa}, "eB": {"direct_quote": qb}}
    seen_pools: list = []
    with caplog.at_level(logging.INFO, logger="src.polaris_graph.generator.cross_source_synthesis"):
        vc._compose_section_per_basket(
            [a, b], pool, writer_fn=_make_writer(), verify_fn=_make_recording_verify(seen_pools),
        )
    marker = next(
        (r.getMessage() for r in caplog.records if "cross_source_body: plan_driven" in r.getMessage()), "",
    )
    assert "input_threaded=True" in marker, (
        f"the caller must BUILD + THREAD the agree_map so the composer sees input_threaded=True; got: {marker!r}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
