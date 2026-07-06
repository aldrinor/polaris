"""I-deepfix-001 Wave 2b (#1344) — offline tests for the minimal-citation-set module.

Design: ``.codex/I-deepfix-001/wave2b_brief.md``. Fully offline — the entailment cross-encoder is
INJECTED via a deterministic ``entail_fn`` stub keyed on span text; NO GPU, NO model download, NO
OpenRouter spend. Asserts cover: OFF identity no-op; ON prune-non-entailing; ON None-verdict => KEEP
(fail-open); ON MVC-redundant demotion (redundant corroborator -> weight, load-bearing -> inline);
and the keep-all partition invariant (``inline ⊎ weight == input``) across every ON scenario.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.generator import citation_set_minimizer as csm
from src.polaris_graph.generator.citation_set_minimizer import (
    ENV_FLAG,
    ENV_MARGIN,
    ENV_MAX_INLINE,
    ENV_PRUNE,
    MinCiteResult,
    min_cite_set_enabled,
    minimize_citation_set,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────
def _member(ev_id: str, quote: str, weight: float) -> SimpleNamespace:
    """One basket member (object shape): evidence_id + direct_quote (its verified span) + weight."""
    return SimpleNamespace(
        evidence_id=ev_id,
        origin_cluster_id=ev_id,
        direct_quote=quote,
        credibility_weight=weight,
    )


def _ids(members: list) -> list[str]:
    return [getattr(m, "evidence_id", None) or m.get("evidence_id") for m in members]


def _assert_keep_all(result: MinCiteResult, input_members: list) -> None:
    """The HARD keep-all invariant: inline ⊎ weight == input (by object identity), disjoint."""
    inline_ids = {id(m) for m in result.inline_members}
    weight_ids = {id(m) for m in result.weight_members}
    input_ids = {id(m) for m in input_members}
    # partition: no overlap, union == input, and the multiset counts match (nothing duplicated/lost)
    assert inline_ids.isdisjoint(weight_ids), "inline and weight must be disjoint"
    assert inline_ids | weight_ids == input_ids, "inline ∪ weight must equal the input members"
    assert len(result.inline_members) + len(result.weight_members) == len(input_members)
    # weight_members is exactly pruned ++ demoted
    assert {id(m) for m in result.weight_members} == (
        {id(m) for m in result.pruned_members} | {id(m) for m in result.demoted_members}
    )


# A span-keyed entailment stub. Spans containing "OFFTOPIC" do NOT entail; spans containing
# "UNKNOWN" return the None infra sentinel; everything else entails. Records calls so OFF can assert
# the stub was never touched.
class _EntailStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, premise: str, hypothesis: str):
        self.calls.append((premise, hypothesis))
        if "OFFTOPIC" in premise:
            return False
        if "UNKNOWN" in premise:
            return None
        return True


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Every test starts from a clean slate (no leaked flags)."""
    for var in (ENV_FLAG, ENV_PRUNE, ENV_MAX_INLINE, ENV_MARGIN):
        monkeypatch.delenv(var, raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# 1. OFF => identity no-op (byte-identical wiring when OFF)
# ─────────────────────────────────────────────────────────────────────────────
def test_off_is_identity_no_op(monkeypatch):
    # master flag unset (default OFF)
    assert min_cite_set_enabled() is False
    stub = _EntailStub()
    members = [_member("e1", "some span", 3.0), _member("e2", "OFFTOPIC span", 1.0)]
    result = minimize_citation_set("a claim sentence", members, entail_fn=stub)

    assert result.enabled is False
    # identity: every input member inline, same objects, same order; empty weight channel
    assert result.inline_members == members
    assert result.weight_members == []
    assert result.pruned_members == [] and result.demoted_members == []
    # OFF must not touch the entailment model at all
    assert stub.calls == []
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ON prune-non-entailing: False-span demoted to weight, entailing span kept inline
# ─────────────────────────────────────────────────────────────────────────────
def test_on_prunes_non_entailing_span(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")  # master ON; MAX_INLINE default 0 => prune-only
    stub = _EntailStub()
    keep = _member("e_keep", "span that supports the claim", 2.0)
    drop = _member("e_drop", "OFFTOPIC generic vocabulary span", 2.0)
    members = [keep, drop]

    result = minimize_citation_set("displace fourteen percent of jobs", members, entail_fn=stub)

    assert result.enabled is True
    assert _ids(result.inline_members) == ["e_keep"]
    assert _ids(result.pruned_members) == ["e_drop"]
    assert _ids(result.weight_members) == ["e_drop"]  # pruned -> weight channel, not deleted
    assert result.demoted_members == []               # MAX_INLINE=0 => no MVC demotion
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ON None-verdict => KEEP (fail-open on infra uncertainty)
# ─────────────────────────────────────────────────────────────────────────────
def test_on_none_verdict_keeps_member(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    stub = _EntailStub()
    entailing = _member("e_true", "span that supports the claim", 2.0)
    unknown = _member("e_unknown", "UNKNOWN infra-unavailable span", 2.0)
    offtopic = _member("e_off", "OFFTOPIC span", 2.0)
    members = [entailing, unknown, offtopic]

    result = minimize_citation_set("the claim sentence", members, entail_fn=stub)

    # True => inline; None => KEEP inline (fail-open); False => pruned
    assert set(_ids(result.inline_members)) == {"e_true", "e_unknown"}
    assert _ids(result.pruned_members) == ["e_off"]
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ON MVC-redundant demotion: load-bearing cover stays inline, redundant corroborator -> weight
# ─────────────────────────────────────────────────────────────────────────────
def test_on_mvc_redundant_demotion(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    monkeypatch.setenv(ENV_MAX_INLINE, "2")  # keep 2 inline; demote redundant beyond
    stub = _EntailStub()
    # three entailing same-statement corroborators; single-atom default => cover size 1 (top weight)
    hi = _member("e_hi", "load-bearing span", 3.0)
    mid = _member("e_mid", "corroborating span", 2.0)
    lo = _member("e_lo", "redundant corroborating span", 1.0)
    members = [hi, mid, lo]

    result = minimize_citation_set("the shared statement", members, entail_fn=stub)

    # cover = top-weight load-bearing (e_hi) stays inline; cap=2 keeps the next-weight corroborator
    # (e_mid) inline; the lowest-weight MVC-redundant corroborator (e_lo) demotes to the weight channel
    assert set(_ids(result.inline_members)) == {"e_hi", "e_mid"}
    assert _ids(result.demoted_members) == ["e_lo"]
    assert _ids(result.weight_members) == ["e_lo"]   # demoted -> weight, nothing pruned here
    assert result.pruned_members == []
    _assert_keep_all(result, members)


def test_on_mvc_strict_singleton_keeps_only_cover(monkeypatch):
    """MAX_INLINE=1 => strict-ish: only the load-bearing cover inline, all corroborators demoted."""
    monkeypatch.setenv(ENV_FLAG, "1")
    monkeypatch.setenv(ENV_MAX_INLINE, "1")
    stub = _EntailStub()
    hi = _member("e_hi", "load-bearing span", 3.0)
    mid = _member("e_mid", "corroborating span", 2.0)
    lo = _member("e_lo", "corroborating span", 1.0)
    members = [hi, mid, lo]

    result = minimize_citation_set("the shared statement", members, entail_fn=stub)

    assert _ids(result.inline_members) == ["e_hi"]           # cover only
    assert set(_ids(result.demoted_members)) == {"e_mid", "e_lo"}
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Combined: prune AND demote together, keep-all still holds; dict members supported
# ─────────────────────────────────────────────────────────────────────────────
def test_on_prune_and_demote_combined_dict_members(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    monkeypatch.setenv(ENV_MAX_INLINE, "1")
    stub = _EntailStub()
    # dict-shaped members (the bibliography row['baskets'] shape) + explicit per-member spans map
    members = [
        {"evidence_id": "e_hi", "credibility_weight": 3.0},
        {"evidence_id": "e_mid", "credibility_weight": 2.0},
        {"evidence_id": "e_off", "credibility_weight": 2.0},
    ]
    spans = {
        "e_hi": "load-bearing span",
        "e_mid": "corroborating span",
        "e_off": "OFFTOPIC span",
    }
    result = minimize_citation_set("the claim", members, spans=spans, entail_fn=stub)

    # e_off pruned (non-entailing); of the two survivors cap=1 keeps e_hi inline, e_mid demoted
    assert _ids(result.inline_members) == ["e_hi"]
    assert _ids(result.pruned_members) == ["e_off"]
    assert set(_ids(result.demoted_members)) == {"e_mid"}
    assert set(_ids(result.weight_members)) == {"e_off", "e_mid"}
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 6. support_of multi-atom cover: two load-bearing sources both stay inline even at cap=...
# ─────────────────────────────────────────────────────────────────────────────
def test_on_multi_atom_cover_keeps_both_load_bearing(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    monkeypatch.setenv(ENV_MAX_INLINE, "1")  # even a strict cap can't drop a uniquely-covering source
    stub = _EntailStub()
    a = _member("e_a", "span a", 3.0)   # covers atom x
    b = _member("e_b", "span b", 2.0)   # covers atom y (unique) => load-bearing
    c = _member("e_c", "span c", 1.0)   # covers atom x (redundant vs a)
    members = [a, b, c]
    support = {"e_a": frozenset({"x"}), "e_b": frozenset({"y"}), "e_c": frozenset({"x"})}

    result = minimize_citation_set(
        "the statement", members,
        support_of=lambda m: support[m.evidence_id],
        entail_fn=stub,
    )

    # cover must include BOTH e_a and e_b (each uniquely covers an atom); cap=1 cannot demote a
    # load-bearing source, so inline == {e_a, e_b} (effective inline > cap by necessity), e_c demoted
    assert set(_ids(result.inline_members)) == {"e_a", "e_b"}
    assert _ids(result.demoted_members) == ["e_c"]
    _assert_keep_all(result, members)


# ─────────────────────────────────────────────────────────────────────────────
# 7. FAIL-OPEN on a RAISING entail seam (P1 — never crash the prune loop)
# ─────────────────────────────────────────────────────────────────────────────
def test_on_raising_injected_entail_fn_keeps_member(monkeypatch):
    """A RAISING injected entail_fn must degrade to KEEP (fail-open), never propagate the crash.
    Guards the ``efn(span, sentence)`` call site in the prune loop."""
    monkeypatch.setenv(ENV_FLAG, "1")

    def _boom(premise, hypothesis):
        raise RuntimeError("simulated cross-encoder malformed-logits IndexError")

    m1 = _member("e1", "some span", 2.0)
    m2 = _member("e2", "another span", 1.0)
    members = [m1, m2]

    # must NOT raise
    result = minimize_citation_set("the claim", members, entail_fn=_boom)

    # every member kept inline (verdict treated as None => KEEP), nothing pruned/demoted
    assert set(_ids(result.inline_members)) == {"e1", "e2"}
    assert result.pruned_members == [] and result.demoted_members == []
    _assert_keep_all(result, members)


def test_default_entail_seam_swallows_runtime_fault(monkeypatch):
    """The DEFAULT seam (no injected entail_fn): a runtime fault escaping ``entails_directional``
    returns None => KEEP. Covers the previously-uncovered ``_default_entail_fn`` call path."""
    monkeypatch.setenv(ENV_FLAG, "1")

    # Patch the resident primitive so the lazy import inside _default_entail_fn resolves to a raiser.
    import src.polaris_graph.synthesis.consolidation_nli as cnli

    def _raise(premise, hypothesis, *, margin=None):
        raise RuntimeError("simulated runtime fault inside entails_directional")

    monkeypatch.setattr(cnli, "entails_directional", _raise)

    # Also assert the seam wrapper itself returns None (KEEP) directly.
    seam = csm._default_entail_fn(None)
    assert seam("a span", "a claim") is None

    m1 = _member("e1", "some span", 2.0)
    members = [m1]
    # no entail_fn => uses the default seam => must NOT raise, member kept inline
    result = minimize_citation_set("the claim", members)
    assert _ids(result.inline_members) == ["e1"]
    assert result.pruned_members == []
    _assert_keep_all(result, members)
