"""I-bench-veracity-003 PR-1 (#1225): subtraction-safe source-breadth anti-concentration.

Unit tests for the within-tier distinct-source interleave + per-source saturation cap
helpers in `multi_section_generator`. These test the PURE reorder logic that decides
WHICH candidate spans the generator sees first — every faithfulness gate (strict_verify,
NLI-enforce, 4-role) is downstream and unchanged, so these tests assert the selection
invariants Codex's brief review locked: default-off byte-identity, tier preservation,
reserved-aware distinctness, soft cap with within-tier backfill, and source-key fallback.
"""

# Third-Party
import pytest

# Local
from src.polaris_graph.generator.multi_section_generator import (
    _build_source_key_fn,
    _normalize_source_key,
    _spread_within_tier,
)


def _evidence(specs):
    """specs: list of (ev_id, source_url) -> evidence rows."""
    return [{"evidence_id": e, "source_url": u} for e, u in specs]


def test_normalize_source_key():
    assert _normalize_source_key("https://A.com/") == "a.com"
    assert _normalize_source_key("http://a.com/p") == "a.com/p"
    assert _normalize_source_key("HTTPS://Example.com/Path/") == "example.com/path"
    assert _normalize_source_key("") is None
    assert _normalize_source_key(None) is None


def test_source_key_fallback_to_evidence_id():
    key = _build_source_key_fn(_evidence([("x", "https://e.com/a"), ("y", "")]))
    assert key("x") == "e.com/a"
    assert key("y").startswith("__evid__:")  # missing url -> its own source
    assert key("unknown").startswith("__evid__:")  # unmapped id -> its own source


def test_off_is_byte_identical():
    seq = ["a1", "a2", "b1", "c1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("b1", "http://B"), ("c1", "http://C")])
    )
    # both knobs off => input returned unchanged (default-off byte-identity)
    assert _spread_within_tier(seq, key, set(), 0, False) == seq


def test_interleave_surfaces_distinct_sources_first():
    seq = ["a1", "a2", "a3", "b1", "c1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("a3", "http://A"),
                   ("b1", "http://B"), ("c1", "http://C")])
    )
    out = _spread_within_tier(seq, key, set(), 0, True)
    # first three rows are three DISTINCT sources, not three of A
    assert {key(out[0]), key(out[1]), key(out[2])} == {"a", "b", "c"}
    # pure reorder: the SET of ev_ids is invariant
    assert sorted(out) == sorted(seq)


def test_reserved_aware_does_not_resurface_reserved_source_first():
    seq = ["a1", "b1", "b2"]
    key = _build_source_key_fn(_evidence([("a1", "http://A"), ("b1", "http://B"), ("b2", "http://B")]))
    # source A already represented in `reserved` (seen={"a"}) -> a fresh source leads
    out = _spread_within_tier(seq, key, {"a"}, 0, True)
    assert key(out[0]) == "b"
    assert sorted(out) == sorted(seq)


def test_per_source_cap_pushes_overflow_to_back_no_interleave():
    seq = ["a1", "a2", "a3", "b1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("a3", "http://A"), ("b1", "http://B")])
    )
    out = _spread_within_tier(seq, key, set(), 2, False)  # cap 2/source
    # a3 (3rd A) is pushed to the back (soft cap: moved, NOT dropped)
    assert out[-1] == "a3"
    assert sorted(out) == sorted(seq)  # nothing dropped


def test_per_source_cap_with_interleave_overflow_after_primary():
    seq = ["a1", "a2", "a3", "b1", "b2"]
    key = _build_source_key_fn(
        _evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A"), ("b1", "u/B"), ("b2", "u/B")])
    )
    out = _spread_within_tier(seq, key, set(), 2, True)  # cap 2, interleave
    # the cap-exceeding 3rd A row is last (overflow); first rows alternate sources
    assert out[-1] == "a3"
    assert key(out[0]) != key(out[1])  # distinct sources lead
    assert sorted(out) == sorted(seq)


def test_cap_backfill_within_tier_below_never_promoted():
    """Caller pattern: spread above-tier, then below-tier with above's keys seen.
    A capped-out ABOVE-floor row must still precede any below-floor row."""
    above = ["a1", "a2", "a3"]   # source A x3
    below = ["d1"]               # source D (below floor)
    key = _build_source_key_fn(
        _evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A"), ("d1", "u/D")])
    )
    sa = _spread_within_tier(above, key, set(), 2, True)
    sb = _spread_within_tier(below, key, {key(e) for e in sa}, 2, True)
    rest = sa + sb
    # a3 is the above-floor overflow (cap 2) — it MUST come before the below-floor d1
    assert rest.index("a3") < rest.index("d1")
    assert sorted(rest) == sorted(above + below)


def test_cap_does_not_strand_capacity_single_source():
    # one source, cap 1: overflow is moved back but NOT dropped, so truncation can
    # still backfill from it if capacity remains.
    seq = ["a1", "a2", "a3"]
    key = _build_source_key_fn(_evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A")]))
    out = _spread_within_tier(seq, key, set(), 1, True)
    assert sorted(out) == sorted(seq)  # all three retained (backfill, not stranded)
    assert out[0] == "a1"  # primary first


# ---------------------------------------------------------------------------
# I-bench-veracity-003 (forensic 2026-06-12): LEGACY-PATH breadth augmentation
# (the keystone fix — the planner-OFF shipping path the prior knobs never touched).
# ---------------------------------------------------------------------------

# Local
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    SectionPlan,
    _augment_legacy_section_breadth,
    _breadth_content_tokens,
)


def _ev(eid, url, text, auth=0.95):
    return {
        "evidence_id": eid, "source_url": url, "text": text,
        "authority_score": auth, "tier": "T1",
    }


_Q = "the restructuring impact of artificial intelligence on the labor market and employment"
_EV = [
    _ev("e1", "http://a.com", "artificial intelligence labor market employment restructuring effects"),
    _ev("e2", "http://b.com", "artificial intelligence employment displacement labor productivity"),
    _ev("e3", "http://c.com", "labor market automation artificial intelligence wages restructuring"),
    _ev("e4", "http://d.com", "employment artificial intelligence productivity labor skills"),
    _ev("e5", "http://e.com", "artificial intelligence jobs labor market employment skills"),
    _ev("e6", "http://f.com", "artificial intelligence labor market restructuring employment policy"),
]


def test_breadth_content_tokens_drops_stopwords():
    toks = _breadth_content_tokens("The impact of AI on the labor market")
    assert "impact" in toks and "labor" in toks and "market" in toks
    assert "the" not in toks and "of" not in toks and "on" not in toks


def test_augment_widens_distinct_sources_up_to_target():
    plans = [SectionPlan(title="Background", focus="ai labor employment", ev_ids=["e1"], archetype="")]
    counts = _augment_legacy_section_breadth(plans, _EV, _Q, set(), target=4)
    assert counts["Background"] >= 4                      # widened to >= target distinct sources
    assert len({u for u in plans[0].ev_ids}) >= 4
    assert "e1" in plans[0].ev_ids                        # original pick retained, never dropped


def test_augment_target_already_met_is_noop():
    plans = [SectionPlan(title="Background", focus="ai labor", ev_ids=["e1", "e2", "e3"], archetype="")]
    before = list(plans[0].ev_ids)
    _augment_legacy_section_breadth(plans, _EV, _Q, set(), target=3)
    assert plans[0].ev_ids == before                     # already >= target -> untouched


def test_augment_skips_contract_sections():
    plans = [SectionPlan(title="Foundational_Theory", focus="x", ev_ids=["e1"], archetype="contract")]
    _augment_legacy_section_breadth(plans, _EV, _Q, {"Foundational_Theory"}, target=5)
    assert plans[0].ev_ids == ["e1"]                     # contract sections left untouched


def test_augment_adds_only_distinct_sources_no_dupes():
    # e1 and e1dup share the same source_url -> count as ONE source
    ev = list(_EV) + [_ev("e1dup", "http://a.com", "artificial intelligence labor market employment")]
    plans = [SectionPlan(title="Background", focus="ai labor", ev_ids=["e1"], archetype="")]
    _augment_legacy_section_breadth(plans, ev, _Q, set(), target=4)
    srcs = {u.split("//")[-1] for u in
            ["http://a.com" if e in ("e1", "e1dup") else f"x{e}" for e in plans[0].ev_ids]}
    # a.com appears at most once as a distinct source in the kept set
    assert plans[0].ev_ids.count("e1dup") == 0 or "e1" not in plans[0].ev_ids


def test_augment_spreads_fresh_sources_across_sections():
    # two sections, each starting from e1; augmentation should give them DIFFERENT fresh sources
    plans = [
        SectionPlan(title="Background", focus="ai labor employment", ev_ids=["e1"], archetype=""),
        SectionPlan(title="Implications", focus="ai labor policy", ev_ids=["e1"], archetype=""),
    ]
    _augment_legacy_section_breadth(plans, _EV, _Q, set(), target=3)
    s0 = set(plans[0].ev_ids) - {"e1"}
    s1 = set(plans[1].ev_ids) - {"e1"}
    # the fresh additions should not be identical sets (cross-section spreading)
    assert s0 != s1 or (len(s0) == 0 and len(s1) == 0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
