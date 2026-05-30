"""Edge-fixture suite for the scenario-family relation-builder.

Exercises the §3 fixture spec from the LOCKED 0a.-1.C-schema deliverable, each
with hand-computed expected (per-stratum P, N, DEFF). Run under 0a.-1.E custody
(this is the post-E "C-fixture dry-run" half).
"""

from __future__ import annotations

import math

import pytest

from src.polaris_safety.relation_builder import (
    DEFAULT_ICC_CEILING,
    RelationInputError,
    build_relations,
    jaccard_ge_half,
    jaccard_in_criterion5_band,
)

WINDOW = 24 * 60 * 60
BASE_TS = 1_700_000_000  # arbitrary fixed UTC epoch for fixtures


def _claim(
    claim_id,
    *,
    report="r-unique",
    cited=None,
    template="t-unique",
    constructor="sme-unique",
    window=BASE_TS,
    gen_family="gf-unique",
    ver_family="vf-unique",
    packet="p-unique",
    microtopics=None,
):
    """Construction row factory. Defaults are deliberately UNIQUE so a field
    only creates a relation when a test explicitly makes it match."""
    return {
        "claim_id": claim_id,
        "source_report_id": f"{report}-{claim_id}" if report == "r-unique" else report,
        "claim_cited_source_ids": list(cited) if cited is not None else [f"src-{claim_id}"],
        "sme_template_id": f"{template}-{claim_id}" if template == "t-unique" else template,
        "constructor_sme_id": f"{constructor}-{claim_id}" if constructor == "sme-unique" else constructor,
        "construction_window_start": window,
        "generator_prompt_family_id": f"{gen_family}-{claim_id}" if gen_family == "gf-unique" else gen_family,
        "verifier_prompt_family_id": f"{ver_family}-{claim_id}" if ver_family == "vf-unique" else ver_family,
        "evidence_packet_id": f"{packet}-{claim_id}" if packet == "p-unique" else packet,
        "microtopic_tags": list(microtopics) if microtopics is not None else [],
    }


def _packets_for(rows, packet_class="pc-unique"):
    """One packet per distinct evidence_packet_id; unique class unless shared."""
    pids = {r["evidence_packet_id"] for r in rows}
    return [
        {
            "evidence_packet_id": pid,
            "canonical_source_ids": ["x"],
            "packet_class": f"{packet_class}-{pid}" if packet_class == "pc-unique" else packet_class,
        }
        for pid in pids
    ]


def _strata(rows, stratum="S1"):
    if isinstance(stratum, dict):
        return [{"claim_id": r["claim_id"], "severity_stratum": stratum[r["claim_id"]]} for r in rows]
    return [{"claim_id": r["claim_id"], "severity_stratum": stratum} for r in rows]


def _summary(result, stratum):
    return next(s for s in result.stratum_summaries if s.stratum == stratum)


# --------------------------------------------------------------------------
# Float-free Jaccard primitives
# --------------------------------------------------------------------------

def test_jaccard_ge_half_exact_boundary():
    # |∩|=1, |∪|=2 -> 0.5 exactly -> 2*1 >= 2 -> related
    assert jaccard_ge_half({"a"}, {"a", "b"}) is True


def test_jaccard_ge_half_just_below():
    # |∩|=1, |∪|=3 -> 0.333 -> 2*1 >= 3 false
    assert jaccard_ge_half({"a"}, {"a", "b", "c"}) is False


def test_jaccard_ge_half_empty_union_is_zero():
    assert jaccard_ge_half(set(), set()) is False


def test_criterion5_band_lower_boundary_included():
    # |∩|=1, |∪|=5 -> 0.2 exactly -> 5*1>=5 and 2*1<5 -> in band
    assert jaccard_in_criterion5_band({"a"}, {"a", "b", "c", "d", "e"}) is True


def test_criterion5_band_just_below_lower():
    # |∩|=1, |∪|=6 -> 0.1667 -> 5*1>=6 false
    assert jaccard_in_criterion5_band({"a"}, {"a", "b", "c", "d", "e", "f"}) is False


def test_criterion5_band_upper_excluded_at_half():
    # |∩|=1, |∪|=2 -> 0.5 -> 2*1<2 false (0.5 not in [0.2,0.5))
    assert jaccard_in_criterion5_band({"a"}, {"a", "b"}) is False


# --------------------------------------------------------------------------
# Per-stratum P/N/DEFF fixtures
# --------------------------------------------------------------------------

def test_p_zero_deff_is_one():
    rows = [_claim("c1"), _claim("c2"), _claim("c3")]  # all unique -> no relations
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    s = _summary(res, "S1")
    assert s.n == 3 and s.p == 0
    assert s.deff == 1.0
    assert s.n_eff == 3.0
    assert all(pr["related"] is False for pr in res.pairwise_relations)


def test_saturation_deff_matches_exchangeable_cluster():
    # all 4 share the same report -> every pair related -> P = 4*3/2 = 6
    rows = [_claim(f"c{i}", report="shared-report") for i in range(4)]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"), rho=0.10)
    s = _summary(res, "S1")
    assert s.n == 4 and s.p == 6
    # DEFF = 1 + 2*P*rho/N = 1 + 2*6*0.1/4 = 1.3 ; exchangeable check 1+(N-1)rho = 1.3
    assert math.isclose(s.deff, 1.3)
    assert math.isclose(s.deff, 1 + (s.n - 1) * 0.10)
    assert s.max_claim_degree == 3  # each related to the other 3


def test_default_rho_is_contract_010():
    rows = [_claim(f"c{i}", report="shared-report") for i in range(2)]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert _summary(res, "S1").rho == DEFAULT_ICC_CEILING == 0.10


# --------------------------------------------------------------------------
# Each criterion firing ALONE
# --------------------------------------------------------------------------

def test_criterion1_same_report_alone():
    rows = [_claim("a", report="R"), _claim("b", report="R")]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    pr = res.pairwise_relations[0]
    assert pr["related"] and pr["criteria_matched"] == ["same_report"]


def test_criterion2_jaccard_alone():
    rows = [_claim("a", cited=["s1", "s2"]), _claim("b", cited=["s1", "s2"])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["evidence_jaccard_ge_0.5"]


def test_criterion3_template_sme_24h_alone():
    rows = [
        _claim("a", template="T", constructor="SME", window=BASE_TS),
        _claim("b", template="T", constructor="SME", window=BASE_TS + WINDOW),  # exactly 24h
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["same_template_sme_24h"]


def test_criterion3_exact_24h_boundary_inclusive():
    rows = [
        _claim("a", template="T", constructor="SME", window=BASE_TS),
        _claim("b", template="T", constructor="SME", window=BASE_TS + WINDOW),
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is True


def test_criterion3_just_over_24h_not_related():
    rows = [
        _claim("a", template="T", constructor="SME", window=BASE_TS),
        _claim("b", template="T", constructor="SME", window=BASE_TS + WINDOW + 60),
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is False


def test_criterion4_generator_family_alone():
    rows = [_claim("a", gen_family="GF"), _claim("b", gen_family="GF")]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["same_prompt_family"]


def test_criterion4_verifier_family_alone():
    rows = [_claim("a", ver_family="VF"), _claim("b", ver_family="VF")]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["same_prompt_family"]


def test_criterion5_microtopic_plus_shared_template_same_stratum():
    rows = [
        _claim("a", template="T", microtopics=["mt1"]),
        _claim("b", template="T", microtopics=["mt1"]),
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    matched = res.pairwise_relations[0]["criteria_matched"]
    # shared template fires BOTH criterion-3-without-sme? No: constructor unique.
    # criterion 3 needs same constructor too -> here constructors differ -> only criterion 5.
    assert matched == ["microtopic_stratum_plus"]


def test_criterion5_requires_same_stratum():
    # shared microtopic + shared template but DIFFERENT strata -> criterion 5 must NOT fire
    rows = [
        _claim("a", template="T", microtopics=["mt1"]),
        _claim("b", template="T", microtopics=["mt1"]),
    ]
    strata = _strata(rows, {"a": "S1", "b": "S2"})
    res = build_relations(rows, _packets_for(rows), strata)
    pr = res.pairwise_relations[0]
    assert "microtopic_stratum_plus" not in pr["criteria_matched"]
    assert pr["related"] is False  # nothing else matches


def test_criterion5_microtopic_alone_insufficient():
    # shared microtopic + same stratum but NO additional correlation -> not related
    rows = [_claim("a", microtopics=["mt1"]), _claim("b", microtopics=["mt1"])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is False


# --------------------------------------------------------------------------
# Dedup, multi-criterion, transitivity, cross-stratum
# --------------------------------------------------------------------------

def test_duplicate_cited_ids_dedup_to_one_member():
    # claim cites the same canonical id twice; partner cites it once -> Jaccard 1.0
    rows = [_claim("a", cited=["s1", "s1"]), _claim("b", cited=["s1"])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is True


def test_alias_resolved_ids_one_member():
    # upstream canonicalizer resolved PMID+DOI to the SAME canonical id -> dedup
    rows = [_claim("a", cited=["doi:10.x/y", "doi:10.x/y"]), _claim("b", cited=["doi:10.x/y"])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["evidence_jaccard_ge_0.5"]


def test_empty_cited_sets_no_jaccard_relation():
    rows = [_claim("a", cited=[]), _claim("b", cited=[])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is False


def test_multi_criterion_pair_counts_once_lists_all():
    # same report AND same generator family -> ONE related pair, two criteria
    rows = [_claim("a", report="R", gen_family="GF"), _claim("b", report="R", gen_family="GF")]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    pr = res.pairwise_relations[0]
    assert pr["related"] is True
    assert pr["criteria_matched"] == ["same_prompt_family", "same_report"]
    assert _summary(res, "S1").p == 1  # counted once


def test_transitive_trap_no_merge():
    # a-b related (report R1), b-c related (report R2), a-c NOT related -> P=2 not 3
    rows = [
        _claim("a", report="R1"),
        _claim("b", report="R1"),  # a-b via report R1... but b must also share R2 with c
    ]
    # build explicitly: a&b share report R1; b&c share generator family GF; a&c share nothing
    a = _claim("a", report="R1", gen_family="GFa")
    b = _claim("b", report="R1", gen_family="GF")
    c = _claim("c", report="R2", gen_family="GF")
    rows = [a, b, c]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    rel = {(p["claim_id_i"], p["claim_id_j"]): p["related"] for p in res.pairwise_relations}
    assert rel[("a", "b")] is True   # same report R1
    assert rel[("b", "c")] is True   # same generator family GF
    assert rel[("a", "c")] is False  # nothing shared -> NO transitive merge
    assert _summary(res, "S1").p == 2


def test_cross_stratum_pair_in_base_not_in_any_P_S():
    # a (S1) and b (S2) share a report -> related in base manifest, but counts in
    # NEITHER stratum's P_S (both-in-S filter).
    rows = [_claim("a", report="R"), _claim("b", report="R")]
    strata = _strata(rows, {"a": "S1", "b": "S2"})
    res = build_relations(rows, _packets_for(rows), strata)
    pr = res.pairwise_relations[0]
    assert pr["related"] is True and pr["stratum_i"] != pr["stratum_j"]
    assert _summary(res, "S1").p == 0
    assert _summary(res, "S2").p == 0


def test_unordered_pair_determinism():
    rows = [_claim("zebra", report="R"), _claim("alpha", report="R")]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    # canonical i<j ordering by claim_id sort -> alpha before zebra
    pr = res.pairwise_relations[0]
    assert pr["claim_id_i"] == "alpha" and pr["claim_id_j"] == "zebra"


def test_reordering_inputs_gives_identical_output():
    a = _claim("a", report="R")
    b = _claim("b", report="R")
    c = _claim("c")
    r1 = build_relations([a, b, c], _packets_for([a, b, c]), _strata([a, b, c], "S1"))
    r2 = build_relations([c, b, a], _packets_for([a, b, c]), _strata([a, b, c], "S1"))
    assert r1.pairwise_relations == r2.pairwise_relations
    assert r1.stratum_summaries == r2.stratum_summaries


# --------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------

def test_null_relation_field_raises():
    rows = [_claim("a"), _claim("b")]
    rows[0]["microtopic_tags"] = None
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), _strata(rows, "S1"))


def test_missing_field_raises():
    rows = [_claim("a"), _claim("b")]
    del rows[0]["sme_template_id"]
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), _strata(rows, "S1"))


def test_claim_without_stratum_raises():
    rows = [_claim("a"), _claim("b")]
    strata = [{"claim_id": "a", "severity_stratum": "S1"}]  # b missing
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), strata)


def test_unknown_packet_reference_raises():
    rows = [_claim("a", packet="known"), _claim("b", packet="known")]
    packets = [{"evidence_packet_id": "wrong", "canonical_source_ids": ["x"], "packet_class": "pc"}]
    with pytest.raises(RelationInputError):
        build_relations(rows, packets, _strata(rows, "S1"))


def test_rho_out_of_range_raises():
    rows = [_claim("a"), _claim("b")]
    with pytest.raises(ValueError):
        build_relations(rows, _packets_for(rows), _strata(rows, "S1"), rho=1.5)


# --------------------------------------------------------------------------
# Degree statistics (contract §3.4 audit)
# --------------------------------------------------------------------------

def test_criterion5_via_shared_packet_class():
    # shared microtopic + same stratum + shared packet class (template+constructor differ,
    # packets differ but SAME class) -> criterion 5 alone.
    rows = [_claim("a", microtopics=["mt1"]), _claim("b", microtopics=["mt1"])]
    packets = [
        {"evidence_packet_id": rows[0]["evidence_packet_id"], "canonical_source_ids": ["x"], "packet_class": "SHARED"},
        {"evidence_packet_id": rows[1]["evidence_packet_id"], "canonical_source_ids": ["y"], "packet_class": "SHARED"},
    ]
    res = build_relations(rows, packets, _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["microtopic_stratum_plus"]


def test_criterion5_via_jaccard_band_pair_level():
    # shared microtopic + same stratum + evidence Jaccard in [0.2,0.5):
    # |∩|=1,|∪|=4 -> 0.25 -> in band; NOT >=0.5 so criterion-2 must NOT fire.
    rows = [
        _claim("a", microtopics=["mt1"], cited=["s1", "s2"]),
        _claim("b", microtopics=["mt1"], cited=["s1", "s3", "s4"]),
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["microtopic_stratum_plus"]


def test_duplicate_canonical_ids_in_packet_manifest_accepted():
    # dup ids WITHIN a packet's canonical_source_ids list are allowed (set dedup);
    # the builder uses claim_cited_source_ids for Jaccard, packets only for class.
    rows = [_claim("a"), _claim("b")]
    packets = [
        {"evidence_packet_id": rows[0]["evidence_packet_id"], "canonical_source_ids": ["s1", "s1"], "packet_class": "c0"},
        {"evidence_packet_id": rows[1]["evidence_packet_id"], "canonical_source_ids": ["s2"], "packet_class": "c1"},
    ]
    res = build_relations(rows, packets, _strata(rows, "S1"))
    assert res.stratum_summaries  # builds without error


def test_jaccard_just_above_half_related():
    # |∩|=2, |∪|=3 -> 0.667 -> related (criterion 2)
    rows = [_claim("a", cited=["s1", "s2"]), _claim("b", cited=["s1", "s2", "s3"])]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["criteria_matched"] == ["evidence_jaccard_ge_0.5"]


def test_criterion3_23h59m_related():
    rows = [
        _claim("a", template="T", constructor="SME", window=BASE_TS),
        _claim("b", template="T", constructor="SME", window=BASE_TS + WINDOW - 60),
    ]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    assert res.pairwise_relations[0]["related"] is True


def test_packet_null_field_raises():
    rows = [_claim("a"), _claim("b")]
    packets = _packets_for(rows)
    packets[0]["packet_class"] = None
    with pytest.raises(RelationInputError):
        build_relations(rows, packets, _strata(rows, "S1"))


def test_packet_empty_packet_class_raises():
    rows = [_claim("a"), _claim("b")]
    packets = _packets_for(rows)
    packets[0]["packet_class"] = ""
    with pytest.raises(RelationInputError):
        build_relations(rows, packets, _strata(rows, "S1"))


def test_severity_null_field_raises():
    rows = [_claim("a"), _claim("b")]
    strata = _strata(rows, "S1")
    strata[0]["severity_stratum"] = None
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), strata)


def test_invalid_severity_stratum_enum_raises():
    rows = [_claim("a"), _claim("b")]
    strata = _strata(rows, {"a": "S9_BOGUS", "b": "S1"})
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), strata)


def test_window_must_be_int_raises():
    rows = [_claim("a"), _claim("b")]
    rows[0]["construction_window_start"] = "not-an-int"
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), _strata(rows, "S1"))


def test_duplicate_construction_claim_id_raises():
    rows = [_claim("dup"), _claim("dup")]
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), _strata(rows, "S1"))


def test_duplicate_packet_id_raises():
    rows = [_claim("a", packet="P"), _claim("b", packet="P")]
    packets = [
        {"evidence_packet_id": "P", "canonical_source_ids": ["x"], "packet_class": "c0"},
        {"evidence_packet_id": "P", "canonical_source_ids": ["y"], "packet_class": "c1"},
    ]
    with pytest.raises(RelationInputError):
        build_relations(rows, packets, _strata(rows, "S1"))


def test_duplicate_severity_claim_id_raises():
    rows = [_claim("a"), _claim("b")]
    strata = _strata(rows, "S1") + [{"claim_id": "a", "severity_stratum": "S2"}]
    with pytest.raises(RelationInputError):
        build_relations(rows, _packets_for(rows), strata)


def test_custody_hash_fields_present_and_stable():
    rows = [_claim("a", report="R"), _claim("b", report="R")]
    r1 = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    r2 = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    s = _summary(r1, "S1")
    assert len(s.relation_table_sha256) == 64
    names = [n for n, _ in s.input_manifest_sha256s]
    assert names == ["construction_manifest", "severity_stratum_manifest", "source_packet_manifest"]
    # deterministic across runs
    assert _summary(r2, "S1").relation_table_sha256 == s.relation_table_sha256
    assert _summary(r2, "S1").input_manifest_sha256s == s.input_manifest_sha256s


def test_p95_degree_nearest_rank():
    # 10 claims all sharing one report -> clique -> every claim degree = 9.
    rows = [_claim(f"c{i}", report="R") for i in range(10)]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    s = _summary(res, "S1")
    assert s.max_claim_degree == 9
    assert s.p95_claim_degree == 9  # all degrees equal -> p95 = 9


def test_nominal_multi_stratum_integration():
    # S1: 4 claims all share report RA -> clique, P_S1 = 6, DEFF = 1+2*6*0.1/4 = 1.3
    # S2: 3 claims, none related -> P_S2 = 0, DEFF = 1.0
    s1 = [_claim(f"a{i}", report="RA") for i in range(4)]
    s2 = [_claim(f"b{i}") for i in range(3)]
    rows = s1 + s2
    strata = _strata(rows, {**{r["claim_id"]: "S1" for r in s1}, **{r["claim_id"]: "S2" for r in s2}})
    res = build_relations(rows, _packets_for(rows), strata, rho=0.10)
    su1, su2 = _summary(res, "S1"), _summary(res, "S2")
    assert su1.n == 4 and su1.p == 6 and math.isclose(su1.deff, 1.3)
    assert su2.n == 3 and su2.p == 0 and su2.deff == 1.0
    assert math.isclose(su1.n_eff, 4 / 1.3)


def test_within_stratum_degree_stats():
    # star: hub h related to 3 leaves via shared report; leaves not related to each other
    h = _claim("h", report="R")
    leaves = [_claim(f"l{i}", report="R") for i in range(3)]
    # but shared report makes ALL of them mutually related (saturation). To make a
    # star, use generator family per-leaf with the hub:
    h = _claim("h", gen_family="GFh")
    l0 = _claim("l0", gen_family="GFh")  # related to h via GFh
    l1 = _claim("l1", gen_family="GFh")  # related to h AND l0 via GFh... still clique.
    # generator-family is transitive-by-shared-value, so use distinct mechanisms:
    # h-l0 share report RA; h-l1 share report RB; l0-l1 share nothing.
    h = _claim("h", report="RA", gen_family="GFh")
    l0 = _claim("l0", report="RA", gen_family="GF0")
    l1 = _claim("l1", report="RB", gen_family="GFh")
    rows = [h, l0, l1]
    res = build_relations(rows, _packets_for(rows), _strata(rows, "S1"))
    rel = {(p["claim_id_i"], p["claim_id_j"]): p["related"] for p in res.pairwise_relations}
    assert rel[("h", "l0")] is True   # report RA
    assert rel[("h", "l1")] is True   # generator family GFh
    assert rel[("l0", "l1")] is False
    s = _summary(res, "S1")
    assert s.p == 2
    assert s.max_claim_degree == 2  # hub h
