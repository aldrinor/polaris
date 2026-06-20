"""I-arch-011 PR-a (#1268) — STORM-outline section-scaffold adapter.

The STORM outline was produced and provably discarded on the benchmark path (the
generator's section list came from `research_plan` / `_call_outline` / contracts,
never from `storm_outline`). PR-a wires the STORM outline as the report's section
SCAFFOLD (titles + order ONLY) behind a DEFAULT-OFF flag `PG_STORM_OUTLINE_SECTIONS`.

These tests are the wiring gate:
  - flag-ON  => the section plan's TITLES + ORDER map to the STORM outline.
  - flag-OFF => the helper returns None so the chooser is byte-identical legacy.
  - faithfulness: ev_ids come from the REAL evidence pool, NO STORM-authored text
    (description / evidence_summary) reaches the plan (focus == title only).
  - the adapter is actually CALLED at the live section-planning chooser site
    (static read), ABOVE `research_plan is not None` — proving it is not a dead flag.

PR-a v2 (Codex diff-gate) adds the faithfulness + uniqueness regression gates:
  - P1 (archetype): every STORM section carries a NON-BLANK archetype so the M-44
    primary-citation validator (`_section_is_primary_eligible`) STILL FIRES — and a
    Mechanism-titled section also makes the M-47 mechanism validator
    (`_section_is_mechanism`) fire, while a non-mechanism section does NOT (so M-47's
    transformative clamp/PK regen never misfires on a Background/Cost section). Both
    validators are therefore AT LEAST AS STRICT as the legacy path, NEVER weaker.
  - P1 (routing): with the STORM scaffold active the post-gen `_use_archetype` flag
    is forced True even when `research_plan is None`, so M-44/M-47 archetype-route
    (not title-route) for STORM's free-form titles.
  - P2 (uniqueness): duplicate STORM titles are deduped (case-insensitive) mirroring
    the legacy parser `seen_titles` guard.

Offline, no spend, no torch/embedder, no strict_verify, no tier classifier.
"""
from __future__ import annotations

import inspect

import pytest

from src.polaris_graph.generator import multi_section_generator as m


# ── fixtures ─────────────────────────────────────────────────────────────────────
def _ev(n: int) -> list[dict]:
    return [{"evidence_id": f"ev_{i}", "statement": "s", "tier": "T1"} for i in range(n)]


class _StormSec:
    """Stand-in for the producer's `StormOutlineSection` pydantic object: the helper
    reads ONLY `.title` / `.order` via getattr, plus carries STORM-authored text the
    adapter must NOT propagate (description / evidence_summary)."""

    def __init__(self, title, order, description="LEAKED DESC", evidence_summary="LEAKED SUMMARY"):
        self.title = title
        self.order = order
        self.description = description
        self.evidence_summary = evidence_summary


# ── flag-OFF: byte-identical legacy (helper returns None even with a NON-empty outline)
def test_flag_off_with_nonempty_outline_returns_none(monkeypatch):
    monkeypatch.delenv(m._STORM_OUTLINE_SECTIONS_ENV, raising=False)
    outline = [_StormSec("Background", 1), _StormSec("Findings", 2)]
    assert m._build_storm_outline_section_plans(outline, _ev(6)) is None


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_flag_off_values_return_none(monkeypatch, val):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, val)
    outline = [_StormSec("Background", 1)]
    assert m._build_storm_outline_section_plans(outline, _ev(6)) is None


# ── flag-ON + empty / None outline => None (enabling the flag alone is inert) ──────
@pytest.mark.parametrize("outline", [None, [], [_StormSec("", 1)], [_StormSec("   ", 1)]])
def test_flag_on_but_no_usable_outline_returns_none(monkeypatch, outline):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    assert m._build_storm_outline_section_plans(outline, _ev(6)) is None


# ── flag-ON: STORM titles + ORDER become the scaffold (the only non-trivial logic) ─
def test_flag_on_maps_titles_in_storm_order(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    # deliberately OUT OF ORDER in the list; `order` must drive the final sequence.
    outline = [
        _StormSec("Implications", 3),
        _StormSec("Background", 1),
        _StormSec("Evidence and Analysis", 2),
    ]
    plans = m._build_storm_outline_section_plans(outline, _ev(9))
    assert plans is not None
    assert [p.title for p in plans] == ["Background", "Evidence and Analysis", "Implications"]


def test_partial_mode_suppresses_storm_scaffold(monkeypatch):
    """I-arch-011 PR-a v3 (Codex re-land P1): under partial_saturation (partial_mode=True),
    the breadth-WIDENING STORM scaffold MUST defer to the pruned sufficient plan — else it
    resurrects sections saturation pruned as under-covered while the manifest claims a pruned
    partial report. Flag-ON + non-empty outline + partial_mode=True => None (suppressed)."""
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [_StormSec("Background", 1), _StormSec("Findings", 2)]
    # Non-vacuous companion: SAME inputs WITHOUT partial_mode DO produce a scaffold.
    assert m._build_storm_outline_section_plans(outline, _ev(6)) is not None
    # partial_mode=True suppresses the scaffold (the pruned plan governs the structure).
    assert m._build_storm_outline_section_plans(outline, _ev(6), partial_mode=True) is None


def test_flag_on_ties_preserve_list_order(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    # equal `order` -> stable on the original list index.
    outline = [_StormSec("First", 0), _StormSec("Second", 0), _StormSec("Third", 0)]
    plans = m._build_storm_outline_section_plans(outline, _ev(9))
    assert [p.title for p in plans] == ["First", "Second", "Third"]


def test_flag_on_accepts_dict_shaped_outline(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [{"title": "B", "order": 2}, {"title": "A", "order": 1}]
    plans = m._build_storm_outline_section_plans(outline, _ev(6))
    assert [p.title for p in plans] == ["A", "B"]


# ── FAITHFULNESS: structure-only — ev_ids from the real pool, NO STORM text leaks ──
def test_flag_on_ev_ids_come_from_evidence_pool_only(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [_StormSec("Background", 1), _StormSec("Findings", 2)]
    evidence = _ev(8)
    pool_ids = {e["evidence_id"] for e in evidence}
    plans = m._build_storm_outline_section_plans(outline, evidence)
    assigned = {eid for p in plans for eid in p.ev_ids}
    assert assigned, "expected the round-robin arm to assign rows from the real pool"
    assert assigned <= pool_ids  # every assigned id is a REAL evidence id


def test_flag_on_no_storm_text_reaches_the_plan(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [_StormSec("Background", 1, description="LEAKED DESC", evidence_summary="LEAKED SUMMARY")]
    plans = m._build_storm_outline_section_plans(outline, _ev(6))
    p = plans[0]
    # focus mirrors the TITLE (round-robin arm), never the STORM description/summary.
    assert p.title == "Background"
    assert p.focus == "Background"
    assert "LEAKED" not in p.title and "LEAKED" not in p.focus


# ── WIRING: the chooser actually CALLS the adapter, ABOVE research_plan (live site) ─
def test_generate_multi_section_report_has_storm_outline_param():
    sig = inspect.signature(m.generate_multi_section_report)
    assert "storm_outline" in sig.parameters
    assert sig.parameters["storm_outline"].default is None


def test_chooser_calls_adapter_above_research_plan_branch():
    src = inspect.getsource(m.generate_multi_section_report)
    call = "_build_storm_outline_section_plans("
    research_branch = "elif research_plan is not None:"
    assert call in src, "the chooser must CALL the STORM adapter (not a dead flag)"
    # I-arch-011 PR-a v3 (Codex re-land P1): the call MUST thread partial_mode so the
    # partial-saturation contract suppresses the breadth-widening STORM scaffold.
    assert "partial_mode=partial_mode" in src, "the STORM adapter call must thread partial_mode"
    assert research_branch in src, "expected the legacy branch to become an elif"
    # the STORM call must precede the legacy research_plan branch -> STORM wins.
    assert src.index(call) < src.index(research_branch)


# ── PR-a v2 P1 (FAITHFULNESS): STORM sections carry a non-blank archetype so the
#    M-44/M-47 validators are NEVER suppressed (the Codex diff-gate P1). ───────────
def test_every_storm_section_carries_a_nonblank_archetype(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [
        _StormSec("Background and Context", 1),
        _StormSec("Cost and Economics", 2),
        _StormSec("Stakeholder Perspectives", 3),
    ]
    plans = m._build_storm_outline_section_plans(outline, _ev(9))
    assert plans, "expected non-empty STORM scaffold plans"
    # A BLANK archetype is exactly what made `_section_is_primary_eligible` False in
    # on-mode (the suppression Codex flagged). None may be blank.
    assert all((p.archetype or "").strip() for p in plans)


def test_m44_primary_validator_fires_for_every_storm_section(monkeypatch):
    """M-44 (`_section_is_primary_eligible`, archetype-route) must be True for EVERY
    STORM section -> the primary-citation validator is never weaker than legacy."""
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [
        _StormSec("Background and Context", 1),
        _StormSec("Mechanism of Action", 2),
        _StormSec("Cost and Economics", 3),
    ]
    plans = m._build_storm_outline_section_plans(outline, _ev(9))
    for p in plans:
        assert m._section_is_primary_eligible(
            title=p.title, archetype=p.archetype, use_archetype=True,
        ), f"M-44 must fire for STORM section {p.title!r}"


def test_m47_mechanism_validator_fires_only_for_mechanism_titled_section(monkeypatch):
    """M-47 (`_section_is_mechanism`) REGENERATES a section when its cited subset
    holds a clamp/PK paper -> it must fire ONLY on a Mechanism-titled section (= legacy
    title routing + on-mode planner tagging), NEVER on a Background/Cost section, else
    the transformative regen could misfire on non-mechanism content."""
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [
        _StormSec("Background", 1),
        _StormSec("Mechanism", 2),   # exact mechanism title
        _StormSec("Cost-Economics", 3),
    ]
    plans = m._build_storm_outline_section_plans(outline, _ev(9))
    by_title = {p.title: p for p in plans}
    # Mechanism-titled -> M-47 fires (archetype == _M47_ARCHETYPE).
    mech = by_title["Mechanism"]
    assert m._section_is_mechanism(
        title=mech.title, archetype=mech.archetype, use_archetype=True,
    ), "M-47 must fire on a Mechanism-titled STORM section"
    # Non-mechanism titles -> M-47 must NOT fire (avoids the misfire regression).
    for title in ("Background", "Cost-Economics"):
        sec = by_title[title]
        assert not m._section_is_mechanism(
            title=sec.title, archetype=sec.archetype, use_archetype=True,
        ), f"M-47 must NOT fire on the non-mechanism STORM section {title!r}"


def test_m47_does_not_misfire_on_non_mechanism_section_with_clamp_evidence(monkeypatch):
    """Misfire guard: even when a NON-mechanism STORM section is round-robin assigned
    clamp/PK-shaped evidence, M-47 must NOT become eligible for it (the routing keys
    on the archetype, not on the assigned evidence)."""
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    # A single non-mechanism section -> it WILL be assigned every evidence row,
    # including the clamp/PK-shaped one, by the round-robin arm.
    outline = [_StormSec("Background", 1)]
    evidence = [
        {"evidence_id": "ev_clamp", "statement": "hyperinsulinemic-euglycemic clamp M-value",
         "tier": "T1", "direct_quote": "M-value 8.2 mg/kg/min half-life 13 min"},
        {"evidence_id": "ev_plain", "statement": "s", "tier": "T2"},
    ]
    plans = m._build_storm_outline_section_plans(outline, evidence)
    bg = plans[0]
    assert "ev_clamp" in bg.ev_ids, "round-robin should assign the clamp row to the sole section"
    # Despite carrying clamp evidence, the Background section is NOT mechanism-eligible.
    assert not m._section_is_mechanism(
        title=bg.title, archetype=bg.archetype, use_archetype=True,
    ), "M-47 must NOT fire on a non-mechanism section merely because it holds clamp evidence"


# ── PR-a v2 P2 (UNIQUENESS): duplicate STORM titles are deduped (case-insensitive) ─
def test_duplicate_titles_are_deduped(monkeypatch):
    monkeypatch.setenv(m._STORM_OUTLINE_SECTIONS_ENV, "1")
    outline = [
        _StormSec("Background", 1),
        _StormSec("background", 2),   # case-insensitive duplicate
        _StormSec("Findings", 3),
        _StormSec("Background", 4),    # exact duplicate
    ]
    plans = m._build_storm_outline_section_plans(outline, _ev(8))
    titles = [p.title for p in plans]
    assert titles == ["Background", "Findings"]
    # case-insensitive uniqueness held.
    assert len({t.lower() for t in titles}) == len(titles)


def test_use_archetype_or_in_present_in_source():
    """The post-gen M-44/M-47 routing flag must OR-in the STORM scaffold so it routes
    on archetype (not free-form title) even when `research_plan is None` (the P1 mode
    gap). Static read of the function source."""
    src = inspect.getsource(m.generate_multi_section_report)
    assert (
        "(research_plan is not None) or (_storm_scaffold_plans is not None)" in src
    ), "the _use_archetype flag must OR-in the STORM scaffold (P1 mode-gap fix)"
