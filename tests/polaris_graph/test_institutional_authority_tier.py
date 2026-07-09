"""I-deepfix-003 (#1374) — recognized-institution TIER FLOOR + explicit label (offline, $0).

STEP 3 of the drb_72 fix: the tier classifier buries credible NON-journal institutions at
T6/UNKNOWN, and the downstream anchor-to-strong-source signal reads the TIER label — so a
WEF/BLS/think-tank/university/`*.gov` source is not seen as a valid anchor even though its
authority WEIGHT is high.

These BEHAVIORAL tests assert the EFFECT on the real ``_join_tier_authority_prior`` output
(§-1.1 / §-1.4 fully-wired), not a flag read:
  * a recognized institution (registry OR the ``*.gov`` / ``*.edu`` rule) gets a RAISED weight
    AND a RAISE-ONLY T3/T4 anchor-eligible tier AND an explicit ``authority_note`` label;
  * a genuine T1 journal is NEVER lowered — including a T1 row whose host IS a recognized band
    (the case that actually exercises the raise-only guard);
  * the two kill-switches are INDEPENDENT: ``PG_INSTITUTIONAL_AUTHORITY_TIER=0`` leaves the tier
    (and the note) untouched while the WEIGHT leg still runs, and ``PG_INSTITUTIONAL_AUTHORITY_WEIGHT=0``
    leaves the weight at the tier prior while the TIER floor still runs.

OFFLINE: no network, no model, no paid LLM.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis.credibility_pass import _join_tier_authority_prior
from src.polaris_graph.synthesis.institutional_authority import (
    institutional_authority_for_url,
    institutional_band_for_url,
)

# Calibrated weight bands (mirror institutional_authority._DEFAULT_BANDS).
_W_NEWS = 0.60
_W_UNIVERSITY = 0.62
_W_THINK_TANK = 0.65
_W_GOVERNMENT = 0.68
_W_IGO = 0.72

# Tier priors used as the WEIGHT base when a row lacks an authority_score
# (mirror credibility_pass._DEFAULT_TIER_AUTHORITY_PRIOR).
_PRIOR_T6 = 0.30
_PRIOR_UNKNOWN = 0.45


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts from the DEFAULT (all switches ON) env so a polluted shell can't hide a
    regression. Individual tests set only the switch they exercise; monkeypatch auto-reverts."""
    for var in (
        "PG_INSTITUTIONAL_AUTHORITY_TIER",
        "PG_INSTITUTIONAL_AUTHORITY_WEIGHT",
        "PG_CREDIBILITY_TIER_AUTHORITY_JOIN",
        "PG_CREDIBILITY_TIER_AUTHORITY_PRIOR",
        "PG_INSTITUTIONAL_AUTHORITY_BANDS",
        "PG_INSTITUTIONAL_AUTHORITY_REGISTRY",
    ):
        monkeypatch.delenv(var, raising=False)


def _row(eid: str, url: str, tier: str, **extra) -> dict:
    row = {"evidence_id": eid, "url": url, "tier": tier}
    row.update(extra)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Recognized institutions: raised weight AND T3/T4 anchor-eligible tier AND label.
# ─────────────────────────────────────────────────────────────────────────────
def test_hbr_news_masthead_raised_weight_and_t4_and_label():
    """hbr.org (Harvard Business Review, news_masthead) buried at T6 -> weight raised to the
    masthead band, tier floored to T4 (anchor-eligible), explicit institutional label stamped."""
    out = _join_tier_authority_prior([_row("e_hbr", "https://hbr.org/2023/01/reskilling", "T6")])
    got = out[0]
    assert got["authority_score"] == pytest.approx(_W_NEWS)
    assert got["tier"] == "T3"
    assert got["authority_note"] == "institutional authority: news_masthead"
    assert got["institutional_authority_band"] == pytest.approx(_W_NEWS)
    assert got["tier_before_institutional_floor"] == "T6"
    assert got["institutional_authority_tier_floor"] == "T3"


def test_institute_global_think_tank_raised_weight_and_t4():
    """institute.global (Tony Blair Institute, think_tank) at UNKNOWN -> weight raised to the
    think-tank band, tier floored to T4."""
    out = _join_tier_authority_prior(
        [_row("e_tbi", "https://institute.global/insights/economic-prosperity", "UNKNOWN")]
    )
    got = out[0]
    assert got["authority_score"] == pytest.approx(_W_THINK_TANK)
    assert got["tier"] == "T3"
    assert got["authority_note"] == "institutional authority: think_tank"


def test_mitsloan_university_raised_weight_and_t4():
    """mitsloan.mit.edu (MIT Sloan, university) at T6 -> weight raised to the university band,
    tier floored to T4, explicit label."""
    out = _join_tier_authority_prior(
        [_row("e_mit", "https://mitsloan.mit.edu/ideas/the-future-of-work", "T6")]
    )
    got = out[0]
    assert got["authority_score"] == pytest.approx(_W_UNIVERSITY)
    assert got["tier"] == "T3"
    assert got["authority_note"] == "institutional authority: university"


def test_calaborfed_think_tank_raised_from_t7():
    """calaborfed.org (California Labor Federation, think_tank) at T7 -> raised weight + T4."""
    out = _join_tier_authority_prior([_row("e_cal", "https://calaborfed.org/report/2024", "T7")])
    got = out[0]
    assert got["authority_score"] == pytest.approx(_W_THINK_TANK)
    assert got["tier"] == "T3"
    assert got["authority_note"] == "institutional authority: think_tank"


def test_rule_based_gov_host_raised_weight_and_t3():
    """A ``*.gov`` host NOT individually enumerated (dol.gov) is recognised by the additive rule ->
    government band weight + a T3 (anchor-eligible) tier floor + label."""
    out = _join_tier_authority_prior(
        [_row("e_gov", "https://www.dol.gov/agencies/eta/data", "UNKNOWN")]
    )
    got = out[0]
    assert got["authority_score"] == pytest.approx(_W_GOVERNMENT)
    assert got["tier"] == "T3"
    assert got["authority_note"] == "institutional authority: government"
    assert got["institutional_authority_tier_floor"] == "T3"


# ─────────────────────────────────────────────────────────────────────────────
# RAISE-ONLY: a genuine T1 journal is NEVER lowered.
# ─────────────────────────────────────────────────────────────────────────────
def test_t1_journal_with_recognized_band_is_never_lowered():
    """The case that actually exercises the raise-only guard: a host that IS a recognized band
    (nature.com -> news_masthead, floor T4) but whose row is already T1 keeps T1 and keeps its
    higher weight — the floor is applied ONLY when strictly stronger."""
    out = _join_tier_authority_prior(
        [_row("e_nat", "https://www.nature.com/articles/s41586-024-00000-0", "T1", authority_score=0.95)]
    )
    got = out[0]
    assert got["tier"] == "T1", "a genuine T1 row MUST NOT be lowered by an institutional floor"
    assert got["authority_score"] == pytest.approx(0.95), "a higher real weight is never lowered"
    # No tier was raised, so the tier-change disclosure fields are absent.
    assert "institutional_authority_tier_floor" not in got
    assert "tier_before_institutional_floor" not in got


def test_non_institution_row_is_passed_through_verbatim():
    """A T1 journal whose host is NOT a recognised institution (thelancet.com) is returned VERBATIM
    (same object) — no weight change, no tier change, no note."""
    rows = [
        _row("e_lan", "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736", "T1",
             authority_score=0.95)
    ]
    out = _join_tier_authority_prior(rows)
    assert out[0] is rows[0], "a non-institution row with a real weight must pass through unchanged"
    assert "authority_note" not in out[0]
    assert out[0]["tier"] == "T1"


# ─────────────────────────────────────────────────────────────────────────────
# Kill-switch independence.
# ─────────────────────────────────────────────────────────────────────────────
def test_tier_switch_off_leaves_tier_unchanged_but_weight_still_raised(monkeypatch):
    """PG_INSTITUTIONAL_AUTHORITY_TIER=0 => tier (and note) untouched; the WEIGHT leg still runs."""
    monkeypatch.setenv("PG_INSTITUTIONAL_AUTHORITY_TIER", "0")
    out = _join_tier_authority_prior([_row("e_hbr", "https://hbr.org/2023/01/reskilling", "T6")])
    got = out[0]
    assert got["tier"] == "T6", "TIER switch OFF must leave the tier unchanged"
    assert got["authority_score"] == pytest.approx(_W_NEWS), "the WEIGHT leg still runs when TIER is OFF"
    assert "authority_note" not in got, "the note is part of the TIER leg — absent when TIER is OFF"


def test_weight_switch_off_leaves_weight_at_prior_but_tier_still_floored(monkeypatch):
    """PG_INSTITUTIONAL_AUTHORITY_WEIGHT=0 => the institutional weight raise is inert (weight stays
    at the tier prior) while the independent TIER floor + label still run."""
    monkeypatch.setenv("PG_INSTITUTIONAL_AUTHORITY_WEIGHT", "0")
    out = _join_tier_authority_prior([_row("e_hbr", "https://hbr.org/2023/01/reskilling", "T6")])
    got = out[0]
    assert got["tier"] == "T3", "the TIER floor runs independently of the WEIGHT switch"
    assert got["authority_note"] == "institutional authority: news_masthead"
    assert got["authority_score"] == pytest.approx(_PRIOR_T6), (
        "WEIGHT switch OFF => no institutional weight raise; weight stays at the T6 tier prior"
    )
    assert got["authority_score_source"] == "tier_prior"


def test_join_switch_off_is_verbatim_noop(monkeypatch):
    """PG_CREDIBILITY_TIER_AUTHORITY_JOIN=0 => the whole join is a byte-identical no-op (the same
    list object is returned)."""
    monkeypatch.setenv("PG_CREDIBILITY_TIER_AUTHORITY_JOIN", "0")
    rows = [_row("e_hbr", "https://hbr.org/x", "T6")]
    out = _join_tier_authority_prior(rows)
    assert out is rows


# ─────────────────────────────────────────────────────────────────────────────
# The band/weight resolvers directly (registry, rule, precedence, non-institution).
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url, band",
    [
        ("https://hbr.org/2023/01/x", "news_masthead"),
        ("https://institute.global/insights/x", "think_tank"),
        ("https://mitsloan.mit.edu/ideas/x", "university"),
        ("https://reports.weforum.org/future-of-jobs", "igo"),
        ("https://www.voced.edu.au/content/ngv-1", "think_tank"),   # .edu.au registry entry
        ("https://www.dol.gov/agencies/eta", "government"),          # *.gov rule
        ("https://ed.gov/about", "government"),                      # explicit + rule
        ("https://catalog.somewhere.edu/x", "university"),           # *.edu rule
        ("https://brookings.edu/research/x", "think_tank"),          # registry WINS over the .edu rule
        ("https://randomblog.example.com/post", None),               # not an institution
    ],
)
def test_institutional_band_for_url(url, band):
    assert institutional_band_for_url(url) == band


def test_institutional_authority_weight_matches_band():
    assert institutional_authority_for_url("https://hbr.org/x") == pytest.approx(_W_NEWS)
    assert institutional_authority_for_url("https://www.dol.gov/x") == pytest.approx(_W_GOVERNMENT)
    assert institutional_authority_for_url("https://mitsloan.mit.edu/x") == pytest.approx(_W_UNIVERSITY)
    assert institutional_authority_for_url("https://randomblog.example.com/x") is None


def test_weight_accessor_respects_weight_kill_switch(monkeypatch):
    """institutional_authority_for_url returns None under PG_INSTITUTIONAL_AUTHORITY_WEIGHT=0, but
    the pure band classifier still resolves (the TIER leg gates it separately)."""
    monkeypatch.setenv("PG_INSTITUTIONAL_AUTHORITY_WEIGHT", "0")
    assert institutional_authority_for_url("https://hbr.org/x") is None
    assert institutional_band_for_url("https://hbr.org/x") == "news_masthead"
