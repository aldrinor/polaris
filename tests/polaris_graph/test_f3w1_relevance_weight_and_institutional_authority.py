"""I-deepfix-001 (#1344) F3 + W1 — fail-loud BEHAVIORAL tests (offline, $0).

Each test asserts the EFFECT appears in real composed / weighted output (§-1.4 FULLY-WIRED gate),
not a flag read.

F3 — the compose-time relevance FLOOR-DROP is replaced by a WEIGHT:
  * a lexically-low but NOT-confirmed-off-topic source is COMPOSED (the banned lexical floor is
    deleted — it used to drop it); only a SEMANTIC confirmed-off-topic row is demoted from the
    findings (kept in the pool); the legacy lexical floor is still reachable via the kill-switch.

W1 — a positive institutional-authority WEIGHT:
  * a recognized institution (WEF/OECD/BLS/Brookings/NYTimes) is RAISED to its calibrated band;
  * the raise is RAISE-ONLY (a real higher weight is never lowered);
  * the join feeds weight_mass so an institution's cluster_mass is the institutional band, NOT the
    old 0.20 UNKNOWN band — i.e. it stops being soft-filtered;
  * the UNKNOWN/no-match prior is raised off 0.20 to 0.45.

OFFLINE: no network, no model, no paid LLM.
"""
from __future__ import annotations

import importlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# F3 — compose-time relevance WEIGHT (delete the banned lexical floor-drop)
# ─────────────────────────────────────────────────────────────────────────────
def _fresh_msg(monkeypatch, weight_flag: str):
    monkeypatch.setenv("PG_COMPOSE_RELEVANCE_WEIGHT", weight_flag)
    from src.polaris_graph.generator import multi_section_generator as msg
    importlib.reload(msg)
    return msg


def test_f3_lexically_low_ontopic_source_is_composed(monkeypatch):
    """The banned lexical floor is DELETED: a real on-topic source scoring 0.02 lexically (far
    below the old 0.10 compose floor) with NO confirmed-off-topic label is now COMPOSED."""
    msg = _fresh_msg(monkeypatch, "1")
    pool = {
        # lexically 0.02 (WAY below the old 0.10 floor) but on-topic (no off-topic label)
        "ev_low": {"selection_relevance": 0.02, "direct_quote": "real on-topic finding"},
        "ev_hi": {"selection_relevance": 0.90, "direct_quote": "clearly on-topic"},
    }
    kept = msg._compose_relevance_floored_ev_ids(["ev_low", "ev_hi"], pool)
    assert kept == ["ev_low", "ev_hi"], (
        "F3: a lexically-low on-topic source MUST be composed (banned lexical floor deleted)"
    )


def test_f3_semantic_confirmed_offtopic_is_demoted_but_kept_in_pool(monkeypatch):
    """A SEMANTIC confirmed-off-topic row (DEFER-1 label) is held from the composed findings while
    it STAYS in the evidence_pool (demote-and-disclose, never a source drop)."""
    msg = _fresh_msg(monkeypatch, "1")
    pool = {
        "ev_ok": {"selection_relevance": 0.55, "direct_quote": "on-topic"},
        # confirmed off-topic via the topic-gate sidecar
        "ev_off1": {"selection_relevance": 0.80, "topic_offtopic_demoted": True},
        # confirmed off-topic via the W2 content-relevance label
        "ev_off2": {"selection_relevance": 0.80, "content_relevance_label": "demoted"},
    }
    kept = msg._compose_relevance_floored_ev_ids(["ev_ok", "ev_off1", "ev_off2"], pool)
    assert kept == ["ev_ok"], "F3: confirmed-off-topic rows MUST be demoted from the findings"
    # DISCLOSE-not-DROP: the source objects are untouched in the pool.
    assert "ev_off1" in pool and "ev_off2" in pool
    assert pool["ev_off1"]["topic_offtopic_demoted"] is True


def test_f3_high_lexical_but_offtopic_still_demoted(monkeypatch):
    """The discriminator is the SEMANTIC verdict, NOT the lexical score: an off-topic row can score
    HIGH lexically (a fluent off-topic supply-chain blog) yet is still demoted."""
    msg = _fresh_msg(monkeypatch, "1")
    pool = {"ev_x": {"selection_relevance": 0.99, "content_relevance_label": "escalated_demoted"}}
    assert msg._compose_relevance_floored_ev_ids(["ev_x"], pool) == []


def test_f3_legacy_kill_switch_restores_lexical_floor_drop(monkeypatch):
    """PG_COMPOSE_RELEVANCE_WEIGHT=0 restores the byte-identical legacy lexical floor: the same
    lexically-low on-topic source is DROPPED again (proving the WEIGHT path changed real behavior)."""
    msg = _fresh_msg(monkeypatch, "0")
    pool = {
        "ev_low": {"selection_relevance": 0.02, "direct_quote": "real on-topic finding"},
        "ev_hi": {"selection_relevance": 0.90, "direct_quote": "clearly on-topic"},
    }
    kept = msg._compose_relevance_floored_ev_ids(["ev_low", "ev_hi"], pool)
    assert kept == ["ev_hi"], "legacy path must still drop the below-0.10 lexical row"


def test_f3_missing_relevance_is_kept_neutral(monkeypatch):
    """A row with no relevance score and no off-topic label is keep-NEUTRAL under the WEIGHT path."""
    msg = _fresh_msg(monkeypatch, "1")
    pool = {"ev_none": {"direct_quote": "no score at all"}}
    assert msg._compose_relevance_floored_ev_ids(["ev_none"], pool) == ["ev_none"]


# ─────────────────────────────────────────────────────────────────────────────
# W1 — positive institutional-authority WEIGHT registry
# ─────────────────────────────────────────────────────────────────────────────
def test_w1_registry_recognizes_credible_institutions(monkeypatch):
    from src.polaris_graph.synthesis import institutional_authority as ia
    importlib.reload(ia)
    # IGOs + statistical agencies -> highest institutional band
    assert ia.institutional_authority_for_url("https://www.weforum.org/reports/x") == pytest.approx(0.72)
    assert ia.institutional_authority_for_url("https://www.bls.gov/news.release/x.htm") == pytest.approx(0.72)
    # think-tank band
    assert ia.institutional_authority_for_url("https://www.brookings.edu/articles/y") == pytest.approx(0.65)
    # news masthead band
    assert ia.institutional_authority_for_url("https://www.nytimes.com/2025/z.html") == pytest.approx(0.60)
    # parent-domain (subdomain) match
    assert ia.institutional_authority_for_url("https://data.oecd.org/y") == pytest.approx(0.72)
    # a non-institution blog is NOT raised
    assert ia.institutional_authority_for_url("https://someone.wordpress.com/post") is None


def test_w1_kill_switch_off_is_inert(monkeypatch):
    monkeypatch.setenv("PG_INSTITUTIONAL_AUTHORITY_WEIGHT", "0")
    from src.polaris_graph.synthesis import institutional_authority as ia
    importlib.reload(ia)
    assert ia.institutional_authority_for_url("https://www.weforum.org/reports/x") is None


def test_w1_env_registry_override_extends(monkeypatch):
    """LAW VI: the operator can add an institution + a raw-float band via the env JSON override."""
    monkeypatch.setenv(
        "PG_INSTITUTIONAL_AUTHORITY_REGISTRY",
        '{"myinstitute.example": 0.7, "another.example": "think_tank"}',
    )
    from src.polaris_graph.synthesis import institutional_authority as ia
    importlib.reload(ia)
    assert ia.institutional_authority_for_url("https://myinstitute.example/x") == pytest.approx(0.7)
    assert ia.institutional_authority_for_url("https://another.example/y") == pytest.approx(0.65)


def test_w1_join_raises_institution_off_unknown_band(monkeypatch):
    """An UNKNOWN-tier institution row with no authority_score is RAISED to its institutional band
    (0.72) instead of the low UNKNOWN prior — the soft-filter correction."""
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    rows = [
        {"evidence_id": "ev_wef", "tier": "UNKNOWN", "source_url": "https://www.weforum.org/r/x"},
        {"evidence_id": "ev_blog", "tier": "UNKNOWN", "source_url": "https://blah.blogspot.com/p"},
    ]
    out = cp._join_tier_authority_prior(rows)
    by_eid = {r["evidence_id"]: r for r in out}
    assert by_eid["ev_wef"]["authority_score"] == pytest.approx(0.72)
    assert by_eid["ev_wef"]["authority_score_source"] == "institutional_registry"
    # a non-institution UNKNOWN row falls to the RAISED UNKNOWN prior (0.45), not the old 0.20
    assert by_eid["ev_blog"]["authority_score"] == pytest.approx(0.45)
    assert by_eid["ev_blog"]["authority_score_source"] == "tier_prior"


def test_w1_raise_only_never_lowers_a_real_higher_weight(monkeypatch):
    """RAISE-ONLY: a WEF row that already carries a computed authority_score ABOVE the band keeps
    its real higher weight (the institutional floor never lowers a source)."""
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    rows = [
        {"evidence_id": "ev_wef_hi", "tier": "T2", "source_url": "https://www.weforum.org/r",
         "authority_score": 0.90},
        {"evidence_id": "ev_wef_lo", "tier": "T6", "source_url": "https://www.weforum.org/r2",
         "authority_score": 0.30},
    ]
    out = cp._join_tier_authority_prior(rows)
    by_eid = {r["evidence_id"]: r for r in out}
    # 0.90 > 0.72 band -> untouched
    assert by_eid["ev_wef_hi"]["authority_score"] == pytest.approx(0.90)
    assert by_eid["ev_wef_hi"].get("authority_score_source") != "institutional_registry"
    # 0.30 < 0.72 band -> RAISED to the band
    assert by_eid["ev_wef_lo"]["authority_score"] == pytest.approx(0.72)
    assert by_eid["ev_wef_lo"]["authority_score_source"] == "institutional_registry"


def test_w1_institution_feeds_institutional_weight_mass(monkeypatch):
    """END-TO-END: the raised institutional authority_score flows to weight_mass so a WEF-only
    claim's weight_mass is the institutional band (0.72), NOT the old 0.20 UNKNOWN band. This is
    the 'stop being soft-filtered' effect in real weighted output."""
    from src.polaris_graph.synthesis import credibility_pass as cp
    from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass
    importlib.reload(cp)

    class _Claim:
        def __init__(self, ccid, eid):
            self.claim_cluster_id = ccid
            self.evidence_id = eid

    rows = [{"evidence_id": "ev_wef", "tier": "UNKNOWN",
             "source_url": "https://www.weforum.org/reports/future-of-jobs"}]
    joined = cp._join_tier_authority_prior(rows)
    masses = aggregate_weight_mass([_Claim("c1", "ev_wef")], joined, [])
    assert masses, "weight_mass produced no claims"
    assert masses[0].weight_mass == pytest.approx(0.72), (
        "W1: a WEF source's weight_mass must be the institutional band, not the 0.20 soft-filter band"
    )


def test_w1_unknown_prior_raised_to_045():
    """The UNKNOWN/no-match prior is raised off 0.20 to 0.45 (disclosed 'unclassified')."""
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    assert cp._DEFAULT_TIER_AUTHORITY_PRIOR["UNKNOWN"] == pytest.approx(0.45)


def test_w1_caller_rows_never_mutated(monkeypatch):
    """The join returns COPIES: the caller's institution row is never mutated in place."""
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    rows = [{"evidence_id": "ev_wef", "tier": "UNKNOWN", "source_url": "https://www.weforum.org/r"}]
    cp._join_tier_authority_prior(rows)
    assert "authority_score" not in rows[0]
