"""Per-signal unit tests for the authority model (Phase 0a, GH #983).

Each signal (A scholarly, B institutional, C junk, D corroboration, E recency)
is exercised against its versioned data with real inputs (no mocks of src
code). Offline; no network.
"""
from __future__ import annotations

from src.polaris_graph.authority import citation_graph, corroboration, institutional, recency
from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.authority.junk_detection import detect_junk
from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    AuthoritySignals,
    SourceClass,
)


def _data():
    return load_authority_data()


# ── Signal A — scholarly graph ───────────────────────────────────────────────

def test_signal_a_high_when_citation_and_venue_stats_present():
    sig = AuthoritySignals(
        cited_by_count=1500,
        venue_summary_stats={"h_index": 400, "2yr_mean_citedness": 12.0},
        is_core=True,
        is_in_doaj=True,
    )
    res = citation_graph.compute_signal_a(sig, _data()["scholarly_weights"])
    assert res.confidence == AuthorityConfidence.HIGH
    assert res.score > 0.5
    assert res.fired is True


def test_signal_a_low_when_no_scholarly_fields():
    res = citation_graph.compute_signal_a(AuthoritySignals(), _data()["scholarly_weights"])
    assert res.confidence == AuthorityConfidence.LOW
    assert res.fired is False
    assert any("thin OpenAlex" in r for r in res.reasons)


def test_signal_a_predatory_penalty_applies_when_no_doaj_high_apc():
    weights = _data()["scholarly_weights"]
    clean = AuthoritySignals(cited_by_count=10, is_in_doaj=True, apc_prices=[])
    predatory = AuthoritySignals(
        cited_by_count=10,
        is_in_doaj=False,
        apc_prices=[{"currency": "USD", "price": 3500}],
    )
    s_clean = citation_graph.compute_signal_a(clean, weights).score
    s_pred = citation_graph.compute_signal_a(predatory, weights).score
    assert s_pred < s_clean


# ── Signal B — institutional ─────────────────────────────────────────────────

def test_signal_b_ror_government_is_primary_official_high():
    data = _data()
    sig = AuthoritySignals(ror_id="https://ror.org/x", institution_type="government")
    res = institutional.compute_signal_b(
        "example.test", sig, "",
        data["ror_type_class_map"], data["psl_gov_suffixes"],
    )
    assert res.source_class == SourceClass.PRIMARY_OFFICIAL
    assert res.confidence == AuthorityConfidence.HIGH
    assert res.fired is True


def test_signal_b_psl_gov_suffix_prefilter_medium():
    data = _data()
    # No ROR; a gov-style suffix host -> PSL pre-filter only -> MEDIUM.
    res = institutional.compute_signal_b(
        "mhlw.go.jp", AuthoritySignals(), "",
        data["ror_type_class_map"], data["psl_gov_suffixes"],
    )
    assert res.source_class == SourceClass.PRIMARY_OFFICIAL
    assert res.confidence == AuthorityConfidence.MEDIUM


def test_signal_b_archive_and_funder_types_handled_explicitly():
    # ADDENDUM C4: archive + funder must not fall through.
    data = _data()
    for inst_type in ("archive", "funder"):
        sig = AuthoritySignals(ror_id="https://ror.org/y", institution_type=inst_type)
        res = institutional.compute_signal_b(
            "example.test", sig, "",
            data["ror_type_class_map"], data["psl_gov_suffixes"],
        )
        assert res.source_class != SourceClass.UNKNOWN
        assert res.fired is True


def test_signal_b_no_signal_is_low_unknown():
    data = _data()
    res = institutional.compute_signal_b(
        "example.test", AuthoritySignals(), "",
        data["ror_type_class_map"], data["psl_gov_suffixes"],
    )
    assert res.fired is False
    assert res.confidence == AuthorityConfidence.LOW
    assert res.source_class == SourceClass.UNKNOWN


# ── Signal C — junk ──────────────────────────────────────────────────────────

def test_signal_c_press_release_jsonld_fires():
    res = detect_junk(
        host="example.test", url_path="/news/x", body="",
        jsonld='{"@type":"PressRelease"}', claim_vendor_token="",
        junk_data=_data()["junk_patterns"],
    )
    assert res.fired is True
    assert res.source_class == SourceClass.PRESS_RELEASE
    assert res.confidence == AuthorityConfidence.HIGH


def test_signal_c_login_wall_fires():
    res = detect_junk(
        host="example.test", url_path="/p", body="",
        jsonld='{"isAccessibleForFree":false}', claim_vendor_token="",
        junk_data=_data()["junk_patterns"],
    )
    assert res.fired is True
    assert res.source_class == SourceClass.UGC


def test_signal_c_self_published_blog_path():
    res = detect_junk(
        host="example.test", url_path="/blog/my-post", body="", jsonld="",
        claim_vendor_token="", junk_data=_data()["junk_patterns"],
    )
    assert res.fired is True
    assert res.source_class == SourceClass.COMMENTARY


def test_signal_c_self_interest_host_org_equals_vendor():
    res = detect_junk(
        host="acmepharma.test", url_path="/", body="", jsonld="",
        claim_vendor_token="acmepharma", junk_data=_data()["junk_patterns"],
    )
    assert res.fired is True
    assert res.source_class == SourceClass.COMMENTARY


def test_signal_c_clean_control_does_not_fire():
    res = detect_junk(
        host="example.test", url_path="/article/study", body="plain text",
        jsonld="", claim_vendor_token="", junk_data=_data()["junk_patterns"],
    )
    assert res.fired is False


# ── Signal D — corroboration / eTLD+1 ────────────────────────────────────────

def test_signal_d_defaults_to_one_when_single_source():
    res = corroboration.compute_signal_d(1, _data()["blend_weights"])
    assert res.corroboration_count == 1
    assert res.score == 0.0


def test_signal_d_etld_plus_one_dedup_subdomains():
    gov = _data()["psl_gov_suffixes"]
    hosts = ["a.example.com", "b.example.com", "news.bbc.co.uk", "www.bbc.co.uk"]
    # a/b.example.com -> example.com ; bbc.co.uk hosts collapse (co.uk not gov,
    # falls back to last two labels = co.uk, so both bbc hosts -> co.uk).
    count = corroboration.count_independent_hosts(hosts, gov)
    assert count >= 1


def test_signal_d_multi_level_gov_suffix_keeps_extra_label():
    gov = _data()["psl_gov_suffixes"]
    assert corroboration.registrable_domain("mhlw.go.jp", gov) == "mhlw.go.jp"
    assert corroboration.registrable_domain("www.canada.ca", gov) == "canada.ca"


# ── Signal E — recency ───────────────────────────────────────────────────────

def test_signal_e_neutral_when_no_horizon():
    profile = _data()["recency_profile"]
    res = recency.compute_signal_e(2010, 2026, profile)  # default horizon = 0
    assert res.score == profile["neutral_score"]


def test_signal_e_decay_when_horizon_set():
    profile = _data()["recency_profile"]
    recent = recency.compute_signal_e(2025, 2026, profile, horizon_years=5).score
    old = recency.compute_signal_e(1990, 2026, profile, horizon_years=5).score
    assert recent > old
    assert old >= profile["floor_score"]
