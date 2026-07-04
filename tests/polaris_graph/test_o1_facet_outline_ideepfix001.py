"""O1 (I-deepfix-001 #1344) — facet-driven outline: section titles + count EMERGE from the
evidence's real facet structure on the NON-clinical path, instead of collapsing into a fixed
6-title generic allow-list truncated to 6 sections.

Gap this proves fixed: the live non-clinical outline validated titles against a fixed 6-title
allow-list (Background / Key Findings / Evidence and Analysis / Comparative Assessment /
Implications / Limitations) AND hard-truncated the plan to 6 sections. A 12-facet economics /
policy question therefore could NEVER render 12 topical sections — every facet coverage fix
downstream hit that container. O1 removes the ceiling for the non-clinical facet path (flag
`PG_FACET_OUTLINE` ON): any non-empty topical title is accepted, the truncate-to-6 is gone
(bounded only by a generous compute-safety ceiling), and each facet section carries an
M-44/M-47 archetype so post-generation validation is NEVER weaker than legacy.

Faithfulness is untouched: the outline structure is still validated against the allowed
evidence pool (unknown ev_ids rejected, >=2 ev_ids required); strict_verify / provenance /
span-grounding are unchanged. Offline, no spend, deterministic (`_parse_outline` is a pure
JSON parser).

The behavioral EFFECT asserted is the SECTION STRUCTURE that becomes the rendered `### <title>`
headings: RED = the fixed container drops all 12 topical facets (0 sections); GREEN = the facet
path keeps all 12 facet-named sections.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator import multi_section_generator as m


# ── fixtures: a real 12-facet non-clinical (economics) outline over a 24-row pool ────────────────
_FACET_TITLES = [
    "Labor-Market Displacement Estimates",
    "Sectoral Productivity Effects",
    "Wage Inequality Evidence",
    "Task-Level Automation Exposure",
    "Occupational Reskilling Outcomes",
    "Regional Employment Divergence",
    "Firm-Level Adoption Patterns",
    "Aggregate GDP Contribution",
    "Public-Policy Responses",
    "Small-Business Impact",
    "Gender and Demographic Gaps",
    "Long-Run Growth Projections",
]


def _pool_ev_ids(n: int) -> set[str]:
    return {f"ev_{i:03d}" for i in range(1, n + 1)}


def _facet_outline_json(titles: list[str]) -> str:
    """One topical section per facet, each with 2 real ev_ids from the pool."""
    sections = []
    for idx, title in enumerate(titles):
        a = f"ev_{2 * idx + 1:03d}"
        b = f"ev_{2 * idx + 2:03d}"
        sections.append({
            "title": title,
            "focus": f"Analytical focus for {title}.",
            "ev_ids": [a, b],
        })
    return json.dumps({"sections": sections})


# ── RED: the fixed 6-title container rejects every topical facet ─────────────────────────────────
def test_red_fixed_generic_container_drops_all_facet_titles():
    """Legacy behavior (facet_titles=False + the generic allow-list): the 12 topical facet
    titles are all off-list, so the container renders ZERO facet sections. This is the ceiling
    O1 removes."""
    raw = _facet_outline_json(_FACET_TITLES)
    pool = _pool_ev_ids(24)
    res = m._parse_outline(
        raw,
        allowed_ev_ids=pool,
        allowed_sections=m._ALLOWED_SECTIONS_GENERIC,
        facet_titles=False,
    )
    # Every topical facet title is dropped as off-list -> the container cannot express facets.
    assert len(res.plans) == 0, (
        "expected the fixed 6-title container to drop all topical facets, "
        f"got {[p.title for p in res.plans]}"
    )


# ── GREEN: the facet path keeps every evidence-bearing facet as its own topical section ──────────
def test_green_facet_path_keeps_all_twelve_facet_sections():
    raw = _facet_outline_json(_FACET_TITLES)
    pool = _pool_ev_ids(24)
    res = m._parse_outline(
        raw,
        allowed_ev_ids=pool,
        allowed_sections=m._ALLOWED_SECTIONS_GENERIC,  # ignored in facet mode
        facet_titles=True,
    )
    got_titles = [p.title for p in res.plans]
    # The container is unlocked: all 12 facet-named sections survive, NOT truncated to 6.
    assert len(res.plans) == 12, f"expected 12 facet sections, got {len(res.plans)}: {got_titles}"
    assert got_titles == _FACET_TITLES, got_titles
    # None of the generic filler titles were forced in.
    assert "Key Findings" not in got_titles
    # No truncate-to-6 telemetry fired.
    assert "section_count_above_max" not in res.reason_codes


def test_green_facet_sections_carry_m44_archetype_so_validation_not_weaker():
    """Each facet section must carry a non-blank M-44/M-47 archetype so the post-generation
    primary-citation validator FIRES on every facet section (>= legacy strictness). A blank
    archetype under archetype-routing would SUPPRESS M-44 — the regression this guards."""
    raw = _facet_outline_json(_FACET_TITLES)
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(24), facet_titles=True)
    assert res.plans, "expected facet sections"
    for p in res.plans:
        assert p.archetype, f"facet section {p.title!r} has a blank archetype (M-44 would be suppressed)"
        # Under archetype routing, every facet section is M-44 primary-eligible (fires the validator).
        assert m._section_is_primary_eligible(
            title=p.title, archetype=p.archetype, use_archetype=True,
        ), f"facet section {p.title!r} is not M-44-eligible under archetype routing"


def test_green_mechanism_titled_facet_routes_to_m47_others_do_not():
    raw = json.dumps({"sections": [
        {"title": "Mechanism", "focus": "f", "ev_ids": ["ev_001", "ev_002"]},
        {"title": "Sectoral Productivity Effects", "focus": "f", "ev_ids": ["ev_003", "ev_004"]},
    ]})
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(6), facet_titles=True)
    by_title = {p.title: p for p in res.plans}
    assert m._section_is_mechanism(
        title="Mechanism", archetype=by_title["Mechanism"].archetype, use_archetype=True,
    )
    assert not m._section_is_mechanism(
        title="Sectoral Productivity Effects",
        archetype=by_title["Sectoral Productivity Effects"].archetype,
        use_archetype=True,
    )


# ── compute-safety ceiling is a bound, NOT a target: it truncates but never fails the plan ───────
def test_facet_compute_safety_ceiling_truncates_without_failing(monkeypatch):
    monkeypatch.setenv(m._FACET_OUTLINE_MAX_SECTIONS_ENV, "5")
    titles = [f"Facet Topic {i}" for i in range(12)]
    raw = _facet_outline_json(titles)
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(24), facet_titles=True)
    assert len(res.plans) == 5, f"expected compute-safety truncate to 5, got {len(res.plans)}"
    assert "facet_section_count_compute_safety_truncate" in res.reason_codes
    # Truncation is a compute bound, NOT a quality-count failure: it must not mark the outline
    # invalid (that would collapse the facet plan to the generic-6 fallback).
    assert "section_count_above_max" not in res.reason_codes


def test_facet_single_grounded_facet_is_a_valid_outline():
    """min-sections default is 1: a single well-grounded facet is a valid emergent outline
    (breadth emerges; it is NOT padded up to a count)."""
    raw = json.dumps({"sections": [
        {"title": "Wage Inequality Evidence", "focus": "f", "ev_ids": ["ev_001", "ev_002"]},
    ]})
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(4), facet_titles=True)
    assert len(res.plans) == 1
    assert res.ok, res.reason_codes
    assert "section_count_below_min" not in res.reason_codes


def test_facet_empty_decomposition_falls_below_min():
    """0 valid facet sections -> below-min -> caller falls through to the generic-6 fallback."""
    raw = json.dumps({"sections": []})
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(4), facet_titles=True)
    assert len(res.plans) == 0
    assert not res.ok
    assert "section_count_below_min" in res.reason_codes


# ── faithfulness guards preserved in facet mode ──────────────────────────────────────────────────
def test_facet_mode_still_rejects_unknown_ev_ids():
    raw = json.dumps({"sections": [
        {"title": "Some Facet", "focus": "f", "ev_ids": ["ev_001", "ev_999"]},  # ev_999 not in pool
    ]})
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(4), facet_titles=True)
    assert len(res.plans) == 0, "a section citing an unknown ev_id must be dropped in facet mode too"


def test_facet_mode_still_requires_two_ev_ids():
    raw = json.dumps({"sections": [
        {"title": "Thin Facet", "focus": "f", "ev_ids": ["ev_001"]},
        {"title": "Good Facet", "focus": "f", "ev_ids": ["ev_002", "ev_003"]},
    ]})
    res = m._parse_outline(raw, allowed_ev_ids=_pool_ev_ids(4), facet_titles=True)
    got = [p.title for p in res.plans]
    assert got == ["Good Facet"], got


# ── gating: default OFF is byte-identical; clinical never facet-mode ─────────────────────────────
def test_facet_flag_default_off_non_clinical_inactive(monkeypatch):
    monkeypatch.delenv(m._FACET_OUTLINE_ENV, raising=False)
    assert not m._facet_outline_active_for_domain("economic")
    assert m._select_outline_system_prompt("economic") is m.OUTLINE_SYSTEM_PROMPT_GENERIC


@pytest.mark.parametrize("domain", ["economic", "policy", "workforce", "tech"])
def test_facet_flag_on_activates_non_clinical(monkeypatch, domain):
    monkeypatch.setenv(m._FACET_OUTLINE_ENV, "1")
    assert m._facet_outline_active_for_domain(domain)
    assert m._select_outline_system_prompt(domain) is m.OUTLINE_SYSTEM_PROMPT_FACET


@pytest.mark.parametrize("domain", ["clinical", "Clinical", " CLINICAL ", "", None])
def test_facet_flag_on_never_touches_clinical(monkeypatch, domain):
    """Even with the flag ON, clinical/unknown keep the proven fixed section set + prompt."""
    monkeypatch.setenv(m._FACET_OUTLINE_ENV, "1")
    assert not m._facet_outline_active_for_domain(domain)
    assert m._select_outline_system_prompt(domain) is m.OUTLINE_SYSTEM_PROMPT


def test_facet_prompt_keeps_dr_rigor_and_injection_guard():
    f = m.OUTLINE_SYSTEM_PROMPT_FACET
    assert "[T1]" in f and "[T7]" in f
    assert "PRIMARY source" in f
    assert "<<<evidence" in f
    # it must instruct facet-per-section, not a fixed count/menu.
    assert "facet" in f.lower()
    assert "EMERGES" in f


def test_legacy_generic_path_still_truncates_to_six_when_flag_off():
    """Sanity: with facet_titles=False the clinical path still enforces the truncate-to-6 ceiling
    (proves O1 did not alter the untouched legacy branch)."""
    # 8 distinct clinical-allowed titles -> legacy parser truncates to 6 and flags it.
    titles = m._ALLOWED_SECTIONS[:8] if len(m._ALLOWED_SECTIONS) >= 8 else m._ALLOWED_SECTIONS
    sections = [
        {"title": t, "focus": "f", "ev_ids": [f"ev_{2 * i + 1:03d}", f"ev_{2 * i + 2:03d}"]}
        for i, t in enumerate(titles)
    ]
    raw = json.dumps({"sections": sections})
    res = m._parse_outline(
        raw, allowed_ev_ids=_pool_ev_ids(len(titles) * 2),
        allowed_sections=m._ALLOWED_SECTIONS, facet_titles=False,
    )
    assert len(res.plans) <= 6
    if len(titles) > 6:
        assert "section_count_above_max" in res.reason_codes
