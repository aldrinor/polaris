"""I-deepfix-001 cov C2 (ANALYSIS) — activate the built-but-dark cross-source synthesis by default.

Two things this proves:

  1. THE DEFAULT FLIP (the code change): ``PG_CROSS_SOURCE_SYNTHESIS`` (M6 between-basket relation
     composer, verified_compose) and ``PG_SWEEP_DEPTH_LAYER`` (the depth_synthesis DS-* live
     synthesizer injected on the cert render path, key_findings) are now DEFAULT-ON, so the DRB-II
     analysis dimension fires on EVERY render path — not only when the benchmark slate force-pins the
     flags. Each has a LAW-VI kill-switch (``=0``) that reverts to the pre-cov byte-identical path.

  2. THE EFFECT (faithfulness-safe): a 2-basket fixture with an NLI-/edge-LICENSED relation renders a
     compare/contrast/agreement/extension sentence that carries TWO distinct ``[#ev]`` tokens and whose
     every atom clause RE-PASSES the FROZEN strict_verify; an UNLICENSED pair stays neutral (never a
     fabricated relation word) and an UNANCHORED pair is ABSENT (zero units). A clause that cannot
     ground is DROPPED — faithfulness NEVER relaxed.

OFFLINE — deterministic short writer (no LLM) + the production ``verify_sentence_provenance`` with
``PG_STRICT_VERIFY_ENTAILMENT=off`` (mechanical checks only; no network judge, no key, no GPU). §-1.3:
this is a WEIGHT/CONSOLIDATE analysis lever (more synthesized relations = honest emergent depth),
never a cap/target/thinner.
"""
from __future__ import annotations

import re

import pytest

from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.generator.cross_source_synthesis import (
    LICENSED_CONNECTIVES,
    compose_cross_source_analytical_units,
    license_relation,
)
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)
from src.polaris_graph.generator.verified_compose import build_short_member_sentence
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket

_TOK_RE = re.compile(r"\[#ev:(?P<ev>[A-Za-z0-9_]+):(?P<s>\d+)-(?P<e>\d+)\]")


# Offline: scope the entailment/verification mode to THIS module's tests and restore it after each
# test via monkeypatch's auto-undo, so no process-global PG_* env leaks into later test files in a
# combined pytest run (the prior module-level ``os.environ[...] = "off"`` never restored -> leak; the
# Codex test-hygiene P1). The network judge singleton is constructed LAZILY inside
# ``verify_sentence_provenance`` at CALL time (only under warn/enforce) and module import constructs
# no judge, so setting the mode OFF per-test before any verify call keeps this suite hermetic — no
# network judge, no key, no GPU — exactly as the module-level assignment did, minus the leak.
@pytest.fixture(autouse=True)
def _offline_entailment_env(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")


# ── hermetic 2-basket fixture (no banked artifacts) ───────────────────────────────────────────────

def _member(evidence_id: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://src/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"origin::{evidence_id}",
        credibility_weight=0.8,
        authority_score=0.8,
        span=(0, len(quote)),
        direct_quote=quote,
        span_verdict="SUPPORTS",
        member_tier="primary",
    )


def _basket(cluster_id: str, quote: str, evidence_id: str) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text=quote,
        subject="ai labor impact",     # SHARED anchor subject ...
        predicate="reshapes",          # ... and predicate -> the two baskets are a pairing candidate
        supporting_members=[_member(evidence_id, quote)],
        refuter_cluster_ids=(),
        weight_mass=1.0,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict="supported",
    )


# Two DISTINCT-cluster baskets, each a groundable ASCII sentence (no digits -> numeric check trivially
# passes; the composed clause is a verbatim prefix of its own span -> mechanical strict_verify passes).
_QUOTE_A = "Automation reshaped factory assembly employment across many manufacturing firms"
_QUOTE_B = "Automation reshaped factory assembly employment throughout numerous production sectors"
_CID_A, _CID_B = "cluster_a", "cluster_b"
_EV_A, _EV_B = "ev_alpha", "ev_beta"


def _fixture():
    a = _basket(_CID_A, _QUOTE_A, _EV_A)
    b = _basket(_CID_B, _QUOTE_B, _EV_B)
    pool = {
        _EV_A: {"direct_quote": _QUOTE_A, "statement": _QUOTE_A},
        _EV_B: {"direct_quote": _QUOTE_B, "statement": _QUOTE_B},
    }
    return [a, b], pool


def _writer(basket, pool):
    return build_short_member_sentence(basket, pool)


def _make_edge(a, b):
    class _E:
        claim_cluster_ids = (a, b)
        source = "semantic"
        severity = "review"
    return _E()


def _entail_none(_p, _h):
    return None


# ── 1) THE DEFAULT FLIP + kill-switch (the code change) ───────────────────────────────────────────

def test_c2_cross_source_synthesis_default_on(monkeypatch):
    monkeypatch.delenv("PG_CROSS_SOURCE_SYNTHESIS", raising=False)
    assert vc._cross_source_synthesis_enabled() is True, "M6 must be DEFAULT-ON (cov C2)"
    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "0")
    assert vc._cross_source_synthesis_enabled() is False, "kill-switch =0 must revert (byte-identical)"
    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "1")
    assert vc._cross_source_synthesis_enabled() is True


def test_c2_depth_layer_default_on(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_DEPTH_LAYER", raising=False)
    assert kf.depth_layer_enabled() is True, "depth_synthesis DS-* layer must be DEFAULT-ON (cov C2)"
    monkeypatch.setenv("PG_SWEEP_DEPTH_LAYER", "0")
    assert kf.depth_layer_enabled() is False, "kill-switch =0 must revert (byte-identical)"


# ── 2) GREEN — a LICENSED relation renders a verified compare/contrast/agreement/extension sentence ─

def _assert_two_verified_atoms(unit: str, pool: dict):
    """Each [#ev] atom in the composed relation sentence re-passes the FROZEN strict_verify."""
    toks = list(_TOK_RE.finditer(unit))
    assert len(toks) >= 2, f"relation sentence must carry >=2 distinct [#ev] tokens: {unit!r}"
    evids = {m.group("ev") for m in toks}
    assert evids >= {_EV_A, _EV_B}, f"two distinct sources cited: {sorted(evids)}"
    for m in toks:
        ev, s, e = m.group("ev"), int(m.group("s")), int(m.group("e"))
        span = str(pool[ev]["direct_quote"])[s:e]
        clause = f"{span.strip()} [#ev:{ev}:{s}-{e}]."
        res = verify_sentence_provenance(clause, pool)
        assert bool(getattr(res, "is_verified", False)), f"atom clause must re-pass strict_verify: {clause!r}"


def test_c2_green_agreement_relation_renders_and_verifies():
    section, pool = _fixture()
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        agree_map={_CID_A: {_CID_B}}, entail_fn=_entail_none,
    )
    assert units, "an agree_map-licensed pair must render an analytical unit"
    assert LICENSED_CONNECTIVES["agreement"].strip() in units[0], units[0]
    _assert_two_verified_atoms(units[0], pool)


def test_c2_green_conflict_relation_renders_and_verifies():
    section, pool = _fixture()
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        edges=[_make_edge(_CID_A, _CID_B)], entail_fn=_entail_none,
    )
    assert units, "a ContradictionEdge-licensed pair must render an analytical unit"
    assert LICENSED_CONNECTIVES["conflict"].strip() in units[0], units[0]
    _assert_two_verified_atoms(units[0], pool)


def test_c2_green_extension_relation_renders_and_verifies():
    """A CERTIFIED directional-entailment verdict (B entails A, A does NOT entail B) licenses the
    'extending this' relation. entail_fn keyed on a marker word only in clause B (a proper superset)."""
    section, pool = _fixture()
    # Give B a proper superset so the directional signal is realistic.
    section[1].supporting_members[0].direct_quote += " and also expanded logistics coordination roles"
    _qb = section[1].supporting_members[0].direct_quote
    pool[_EV_B] = {"direct_quote": _qb, "statement": _qb}

    def _entail_extension(premise, hypothesis):
        # b_entails_a: premise carries the superset marker, hypothesis does not -> True.
        # a_entails_b: premise lacks the marker, hypothesis has it -> False (confident non-entailment).
        p_has, h_has = "logistics" in premise, "logistics" in hypothesis
        if p_has and not h_has:
            return True
        if h_has and not p_has:
            return False
        return None

    # license_relation resolves extension from the two directional verdicts directly.
    assert license_relation(
        _CID_A, _CID_B, directional_entails=True, bidirectional_entails=None,
    ) == "extension"

    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        entail_fn=_entail_extension,
    )
    assert units, "a directional-entailment-licensed pair must render an analytical unit"
    assert LICENSED_CONNECTIVES["extension"].strip() in units[0], units[0]
    _assert_two_verified_atoms(units[0], pool)


# ── 3) RED / control — an UNLICENSED pair stays neutral, an UNANCHORED pair is ABSENT ──────────────

def test_c2_unlicensed_pair_stays_neutral():
    """No edge, no agree_map, no entailment signal -> the composer NEVER fabricates a relation word;
    an anchored pair renders only the neutral juxtaposition connective."""
    section, pool = _fixture()
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        edges=None, agree_map=None, entail_fn=_entail_none,
    )
    assert units, "an anchored distinct-cluster pair still composes (as neutral juxtaposition)"
    u = units[0]
    assert LICENSED_CONNECTIVES["neutral"].strip() in u, u
    for rel in ("agreement", "conflict", "extension"):
        assert LICENSED_CONNECTIVES[rel].strip() not in u, f"no fabricated {rel} word: {u!r}"


def test_c2_unanchored_pair_is_absent():
    """No shared subject/predicate anchor -> the pair is not a synthesis candidate -> ZERO units
    (analytical yield EMERGES from real anchored pairs; it is never forced)."""
    section, pool = _fixture()
    for b in section:
        b.subject = ""   # remove the anchor
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        agree_map={_CID_A: {_CID_B}}, entail_fn=_entail_none,
    )
    assert units == [], "an unanchored pair must yield ZERO analytical units (absent)"


# ── 4) Faithfulness still gates — an unresolvable span drops the pair (never forced) ───────────────

def test_c2_unresolvable_span_drops_the_unit():
    """If a basket's member span cannot ground in the pool, its clause fails to build/verify and the
    analytical pair is DROPPED (the two atoms would survive via the per-basket path) — verify still bites."""
    section, pool = _fixture()
    # Corrupt basket B's pool row so its verbatim span is NOT locatable -> clause_b cannot build.
    pool[_EV_B] = {"direct_quote": "totally unrelated text with no overlap", "statement": "totally unrelated"}
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
        agree_map={_CID_A: {_CID_B}}, entail_fn=_entail_none,
    )
    assert units == [], "a pair whose clause cannot ground must be dropped (faithfulness never relaxed)"
