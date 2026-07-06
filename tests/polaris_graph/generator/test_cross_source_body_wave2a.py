"""I-deepfix-001 Wave-2a (#1344) behavioral test — cross-source analysis into the body.

ISOLATED + OFFLINE: no paid API, no GPU, no model. The pairing / relation / comparator logic is driven
with a DETERMINISTIC stub clause-builder (the ``_first_verified_clause`` seam is monkeypatched) and a
stub NLI ``entail_fn``; the per-clause-verify invariant is driven through the REAL
``verified_compose._compose_one_basket`` path with a RECORDING stub ``verify_fn`` so we prove — against
the real scoping code — that each clause is verified against its OWN basket-scoped pool, NEVER the union.

Asserts:
  1. OFF byte-identical: ``PG_CROSS_SOURCE_BODY`` unset => anchor-equality pairing (same subject|predicate
     pairs unit; a different-predicate same-subject pair does NOT pair). The comparator / plan-driven
     predicate are never consulted.
  2. ON plan-driven: same-facet (same subject, differing predicate) => a unit forms (it did NOT under OFF);
     a ContradictionEdge => the conflict connective; a bidirectional NLI verdict => the agreement connective.
  3. ON per-clause own pool: every ``verify_fn`` call receives a single basket's OWN scoped pool (never the
     {A,B} union); a foreign-cited token is rejected (fails closed) and never leaks into a unit.
  4. ON numeric comparator: a full match-key with differing values licenses the ``comparison`` connective;
     any differing/unknown/ambiguous discriminator (or equal values) fails CLOSED to neutral.
  5. ON canary: candidate pairs exist yet 0 units survive => the loud failed-validation WARNING fires.
"""
from __future__ import annotations

import logging
import os
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
from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: E402
    LICENSED_CONNECTIVES,
    compose_cross_source_analytical_units,
)
from src.polaris_graph.generator.numeric_comparator import (  # noqa: E402
    build_numeric_key_lookup,
    license_numeric_comparison,
    numeric_comparator_enabled,
    _numeric_comparability_key,
)
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402


# ── tiny builders ────────────────────────────────────────────────────────────────────────────────
def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url="", source_tier="",
        origin_cluster_id=f"origin::{eid}", credibility_weight=1.0, authority_score=1.0,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, subject: str, predicate: str, eids, *, quotes=None, refuters=()) -> ClaimBasket:
    quotes = quotes or {}
    members = [_member(e, quotes.get(e, f"{subject} {predicate} finding.")) for e in eids]
    return ClaimBasket(
        claim_cluster_id=cluster_id, claim_text=f"{subject} {predicate}", subject=subject,
        predicate=predicate, supporting_members=members, refuter_cluster_ids=tuple(refuters),
        weight_mass=1.0, total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members), basket_verdict="full",
    )


class _Edge:
    """A ContradictionEdge stand-in read by ``_edge_between`` (only ``claim_cluster_ids`` is inspected)."""
    def __init__(self, ca: str, cb: str):
        self.claim_cluster_ids = (ca, cb)


def _stub_clause_builder(clause_by_cluster: dict):
    """A deterministic ``_first_verified_clause`` seam: one tokened clause per cluster id."""
    def _stub(basket, _pool, *, writer_fn, verify_fn):  # signature matches the real helper
        return clause_by_cluster.get(str(getattr(basket, "claim_cluster_id", "") or ""))
    return _stub


def _connective_in(units, connective: str) -> bool:
    return any(connective in u for u in units)


# clause text per cluster (each cites a DISTINCT evidence_id so pairs are real cross-SOURCE units).
_CLAUSES = {
    "cA": "Study A reported an effect [#ev:eA:0-5].",
    "cB": "Study B reported an effect [#ev:eB:0-5].",
    "cC": "Study C reported a side effect [#ev:eC:0-5].",
}


# ── 1. OFF byte-identical (anchor equality; different-predicate does NOT pair) ─────────────────────
def test_off_is_anchor_equality_pairing(monkeypatch):
    monkeypatch.delenv("PG_CROSS_SOURCE_BODY", raising=False)
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    b = _basket("cB", "drug x", "reduces a1c", ["eB"])   # SAME anchor as A
    c = _basket("cC", "drug x", "causes nausea", ["eC"])  # same subject, DIFFERENT predicate
    units = compose_cross_source_analytical_units(
        [a, b, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        entail_fn=lambda *_: None,
    )
    # ONLY the same subject|predicate anchor pair (A-B) forms a unit; C never pairs (different predicate).
    assert len(units) == 1
    assert _connective_in(units, LICENSED_CONNECTIVES["neutral"])
    assert not any("eC" in u for u in units)


# ── 2. ON plan-driven pairing: same-facet forms a unit OFF did not; edge => conflict; NLI => agreement
def test_on_same_facet_pairs_that_off_did_not(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])  # same subject, different predicate
    units = compose_cross_source_analytical_units(
        [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        entail_fn=lambda *_: None,
    )
    # Same-facet (subject) pair NOW forms a neutral unit — the self-annulment fix.
    assert len(units) == 1
    assert _connective_in(units, LICENSED_CONNECTIVES["neutral"])
    assert any("eA" in u for u in units) and any("eC" in u for u in units)


def test_on_contradiction_edge_licenses_conflict(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    # Different subjects => only the edge admits the pair (proves edge candidacy, not facet).
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    b = _basket("cB", "drug y", "reduces ldl", ["eB"])
    units = compose_cross_source_analytical_units(
        [a, b], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        edges=[_Edge("cA", "cB")], entail_fn=lambda *_: None,
    )
    assert len(units) == 1
    assert _connective_in(units, LICENSED_CONNECTIVES["conflict"])


def test_on_bidirectional_nli_licenses_agreement(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    b = _basket("cB", "drug x", "lowers hba1c", ["eB"])  # same subject facet
    # Both-directions-entail stub => bidirectional equivalence => agreement.
    units = compose_cross_source_analytical_units(
        [a, b], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        entail_fn=lambda _p, _h: True,
    )
    assert len(units) == 1
    assert _connective_in(units, LICENSED_CONNECTIVES["agreement"])


# ── 3. per-clause OWN pool (real _compose_one_basket path) — never a union pool; foreign fails closed
def _make_writer(foreign_eid=None):
    """A deterministic writer: emit the member's verbatim quote + a token. ``foreign_eid`` cites a source
    OUTSIDE this basket (to prove foreign fail-closed)."""
    def _w(basket, _scoped_pool):
        m = basket.supporting_members[0]
        q = m.direct_quote
        eid = foreign_eid or m.evidence_id
        return f"{q} [#ev:{eid}:0-{len(q)}]"
    return _w


class _VR:
    def __init__(self, sentence, is_verified):
        self.sentence = sentence
        self.is_verified = is_verified
        self.failure_reasons = [] if is_verified else ["stub_reject"]


def _make_recording_verify(seen_pools: list):
    """A verify_fn that RECORDS the pool it is handed and passes iff the sentence's cited ev_id is in
    THAT pool (emulates strict_verify's own-pool gate). Proves the composer never verifies against a
    union pool."""
    import re
    _tok = re.compile(r"\[#ev:([A-Za-z0-9_]+):")

    def _verify(sentence, scoped_pool):
        seen_pools.append(set(scoped_pool.keys()))
        cited = {m.group(1) for m in _tok.finditer(sentence or "")}
        ok = bool(cited) and cited <= set(scoped_pool.keys())
        return _VR(sentence, ok)
    return _verify


def test_on_each_clause_verified_against_own_pool_never_union(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")  # keep the synthetic sentence deterministic
    # NOTE: no _first_verified_clause monkeypatch — drive the REAL verified_compose path.
    qa, qb = "Alpha wages rose three percent.", "Beta output grew four percent."
    a = _basket("cA", "labor", "wages", ["eA"], quotes={"eA": qa})
    b = _basket("cB", "labor", "wages", ["eB"], quotes={"eB": qb})  # same anchor => a candidate pair
    pool = {"eA": {"direct_quote": qa}, "eB": {"direct_quote": qb}}
    seen_pools: list = []
    units = compose_cross_source_analytical_units(
        [a, b], pool, writer_fn=_make_writer(), verify_fn=_make_recording_verify(seen_pools),
        entail_fn=lambda *_: None,
    )
    assert len(units) == 1  # both own-cited clauses verify against their own pool -> one cross-source unit
    assert seen_pools, "verify_fn must have been called on the real per-basket path"
    # THE INVARIANT: every verify call saw a SINGLE basket's own scoped pool, NEVER the {eA, eB} union.
    for pool_keys in seen_pools:
        assert pool_keys in ({"eA"}, {"eB"}), f"union/foreign pool leaked into verify: {pool_keys}"
        assert not {"eA", "eB"} <= pool_keys


def test_on_foreign_cited_clause_fails_closed(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    monkeypatch.setenv("PG_SUBTOPIC_DECOMPOSITION", "0")  # simplest K-span fallback path
    q = "Alpha wages rose three percent."
    a = _basket("cA", "labor", "wages", ["eA"], quotes={"eA": q})
    b = _basket("cB", "labor", "wages", ["eB"], quotes={"eB": "Beta output grew four percent."})
    pool = {"eA": {"direct_quote": q}, "eB": {"direct_quote": "Beta output grew four percent."}}
    seen_pools: list = []
    verify = _make_recording_verify(seen_pools)
    # Basket A's writer cites a FOREIGN source (eZ) absent from A's scoped pool => fails closed.
    def _writer(basket, scoped_pool):
        return _make_writer(foreign_eid="eZ" if basket.claim_cluster_id == "cA" else None)(basket, scoped_pool)
    units = compose_cross_source_analytical_units(
        [a, b], pool, writer_fn=_writer, verify_fn=verify, entail_fn=lambda *_: None,
    )
    # The foreign token was verified against A's OWN pool ({eA}) and rejected — it can NEVER render.
    assert not any("eZ" in u for u in units), "a foreign citation leaked into a rendered unit"
    for pool_keys in seen_pools:
        assert "eZ" not in pool_keys  # the foreign source is never in any basket's scoped pool


# ── 4. numeric comparator: full match-key + differing values => comparison; else fail-closed neutral ─
def _num_key(subject, predicate, value, unit="percent", dose="10mg", arm="active", endpoint="hba1c"):
    """A legacy ``_normalized_key_numeric``-shaped tuple (value at index 3). Defaults are FULLY populated
    (every discriminator positively known) so a match licenses a comparison; a test that wants the
    fail-closed path passes a blank field explicitly."""
    return ("numeric", subject, predicate, float(value), unit, dose, arm, endpoint)


def test_numeric_comparator_licenses_only_on_full_match():
    a = _num_key("drug x", "reduces a1c", 1.5)
    b = _num_key("drug x", "reduces a1c", 1.1)  # differs ONLY in value
    assert license_numeric_comparison(a, b) == "comparison"
    # differing unit => fail-closed to neutral
    assert license_numeric_comparison(a, _num_key("drug x", "reduces a1c", 1.1, unit="mmol")) is None
    # differing subject / predicate => fail-closed
    assert license_numeric_comparison(a, _num_key("drug y", "reduces a1c", 1.1)) is None
    assert license_numeric_comparison(a, _num_key("drug x", "raises a1c", 1.1)) is None
    # equal values => not a comparison (same claim)
    assert license_numeric_comparison(a, _num_key("drug x", "reduces a1c", 1.5)) is None


def test_numeric_comparator_fails_closed_on_sentinel_or_qualitative():
    good = _num_key("drug x", "reduces a1c", 1.5)
    assert _numeric_comparability_key(good) is not None
    # legacy unknown-subject sentinel
    assert license_numeric_comparison(good, ("__numeric_unknown__", "eid", 3)) is None
    # redesign fail-closed singleton
    assert license_numeric_comparison(good, ("__unresolved__", "numeric", "clinical", "eid", "uid")) is None
    # qualitative key
    assert license_numeric_comparison(good, ("qualitative", "drug x", "causation", "", "", "")) is None
    # non-tuple / short / non-numeric value
    assert _numeric_comparability_key(None) is None
    assert _numeric_comparability_key(("numeric", "s", "p")) is None
    assert _numeric_comparability_key(("numeric", "s", "p", "not-a-number", "u")) is None
    assert _numeric_comparability_key(("numeric", "s", "p", True, "u")) is None  # bool is not a value


def test_numeric_comparator_fails_closed_on_blank_legacy_discriminator():
    """Fable P1 (clinical-safety): the legacy _normalized_key_numeric sentinels ONLY on a blank subject, so
    a blank unit/predicate/dose/arm/endpoint would slip through as "". Blank is UNKNOWN — comparing values
    whose unit was never established (%-points vs mmol/mol) is the lethal over-relax. Must fail closed."""
    good = _num_key("drug x", "reduces a1c", 1.5)   # fully populated
    assert license_numeric_comparison(good, _num_key("drug x", "reduces a1c", 1.1)) == "comparison"
    # A blank UNIT on both keys => still NOT comparable (unit never positively known) => neutral.
    blank_unit_a = _num_key("drug x", "reduces a1c", 1.5, unit="")
    blank_unit_b = _num_key("drug x", "reduces a1c", 1.1, unit="")
    assert _numeric_comparability_key(blank_unit_a) is None
    assert license_numeric_comparison(blank_unit_a, blank_unit_b) is None
    # A blank in ANY discriminator slot (unit / dose / arm / endpoint / whitespace) fails closed.
    for field in ("unit", "dose", "arm", "endpoint"):
        blanked = _num_key("drug x", "reduces a1c", 1.5, **{field: ""})
        assert _numeric_comparability_key(blanked) is None, f"blank {field} must fail closed"
        assert license_numeric_comparison(blanked, good) is None
    # blank predicate / subject (the positional fields) also fail closed.
    assert _numeric_comparability_key(_num_key("drug x", "", 1.5)) is None       # blank predicate
    assert _numeric_comparability_key(_num_key("", "reduces a1c", 1.5)) is None  # blank subject
    assert _numeric_comparability_key(_num_key("drug x", "reduces a1c", 1.5, unit="   ")) is None  # whitespace


def test_numeric_comparator_wires_into_composer(monkeypatch):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    b = _basket("cB", "drug x", "reduces a1c", ["eB"])  # same facet, neutral by NLI/edge
    keys = {"cA": _num_key("drug x", "reduces a1c", 1.5), "cB": _num_key("drug x", "reduces a1c", 1.1)}
    # comparator OFF => neutral connective (byte-identical relation set).
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    assert not numeric_comparator_enabled()
    off_units = compose_cross_source_analytical_units(
        [a, b], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        entail_fn=lambda *_: None, numeric_key_by_cluster=keys,
    )
    assert _connective_in(off_units, LICENSED_CONNECTIVES["neutral"])
    assert not _connective_in(off_units, LICENSED_CONNECTIVES["comparison"])
    # comparator ON => the neutral pair upgrades to the comparison connective.
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    on_units = compose_cross_source_analytical_units(
        [a, b], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        entail_fn=lambda *_: None, numeric_key_by_cluster=keys,
    )
    assert _connective_in(on_units, LICENSED_CONNECTIVES["comparison"])


def test_build_numeric_key_lookup_selects_numeric_only():
    class _Claim:
        def __init__(self, kind, ccid, key):
            self.kind, self.claim_cluster_id, self.normalized_key = kind, ccid, key
    claims = [
        _Claim("numeric", "c1", _num_key("drug x", "reduces a1c", 1.5)),
        _Claim("qualitative", "c2", ("qualitative", "drug x", "causation", "", "", "")),
        _Claim("numeric", "", _num_key("drug y", "x", 2.0)),  # no cluster id -> skipped
    ]
    out = build_numeric_key_lookup(claims)
    assert set(out) == {"c1"}


# ── 5. canary: candidate pairs but 0 units => loud failed-validation warning ───────────────────────
def test_canary_fires_when_candidates_but_zero_units(monkeypatch, caplog):
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    # A clause builder that yields NOTHING => every candidate pair fails to build a unit.
    monkeypatch.setattr(css, "_first_verified_clause", lambda *a, **k: None)
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    b = _basket("cB", "drug x", "reduces a1c", ["eB"])  # a real candidate pair (same facet)
    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.generator.cross_source_synthesis"):
        units = compose_cross_source_analytical_units(
            [a, b], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
        )
    assert units == []
    assert any(
        "candidate cross-source pair" in r.getMessage() and "0 analytical units" in r.getMessage()
        for r in caplog.records
    ), "the failed-validation canary must fire loudly"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
