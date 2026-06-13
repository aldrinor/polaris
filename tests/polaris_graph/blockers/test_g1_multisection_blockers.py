"""G1 multi-section breadth-augmentation blockers (I-pipe-004/006/008 = #1229/#1231/#1233).

Drives the REAL ``_augment_legacy_section_breadth`` / ``_breadth_content_tokens`` /
``_breadth_row_is_marquee`` helpers in
``src/polaris_graph/generator/multi_section_generator.py``.

Each fix is env-gated and DEFAULT-OFF, so with every new flag unset the function is
behaviourally byte-identical to the historical augmentation. The tests assert:

  * #1229 PG_BREADTH_AUGMENT_MIN_OVERLAP / PG_BREADTH_AUGMENT_REQUIRE_SECTION_OVERLAP:
    flag-off selects the SAME rows as the historical >=2 bar; flag-on (tighter bar or
    section-overlap requirement) REJECTS an off-topic row that the weak bar admitted.
  * #1231 PG_BREADTH_MARQUEE_PRIORITY: flag-off ordering is the historical order; flag-on
    ranks required-entity / marquee anchor rows FIRST so they reach the writers.
  * #1233 PG_BREADTH_CANARY_MIN: 0 (default) never raises; > target RAISES a loud
    RuntimeError; <= achieved breadth passes.

FAITHFULNESS: these are SELECTION-STAGE / FAIL-LOUD changes only. They never touch
strict_verify / NLI-enforce / the 4-role D8 audit and never fabricate or relax a verdict.

Offline, no network, no heavy ML. The ``authority_score`` field is set directly on each
fixture row so ``_enrich_authority_if_missing`` returns it without the heavy authority-model
import path; the default floor is 0.3 (PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _augment_legacy_section_breadth,
    _breadth_row_is_marquee,
    enforce_breadth_canary,
)

_FLAG_MIN_OVERLAP = "PG_BREADTH_AUGMENT_MIN_OVERLAP"
_FLAG_SECTION_OVERLAP = "PG_BREADTH_AUGMENT_REQUIRE_SECTION_OVERLAP"
_FLAG_MARQUEE = "PG_BREADTH_MARQUEE_PRIORITY"
_FLAG_CANARY = "PG_BREADTH_CANARY_MIN"
_FLAG_FLOOR = "PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR"

_ALL_FLAGS = (
    _FLAG_MIN_OVERLAP,
    _FLAG_SECTION_OVERLAP,
    _FLAG_MARQUEE,
    _FLAG_CANARY,
)


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts with the new flags UNSET (default-off path) and a known
    authority floor so fixture rows with authority_score=0.9 always pass it."""
    for flag in _ALL_FLAGS:
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv(_FLAG_FLOOR, "0.3")


def _row(eid, url, text, *, authority=0.9, **extra):
    row = {
        "evidence_id": eid,
        "source_url": url,
        "direct_quote": text,
        "authority_score": authority,
    }
    row.update(extra)
    return row


def _plan(title, focus, ev_ids):
    return SectionPlan(title=title, focus=focus, ev_ids=list(ev_ids))


# The research question + section focus share these AI/labor domain anchors.
_RESEARCH_Q = "How does generative artificial intelligence automation affect labor employment wages?"
_SECTION_FOCUS = "automation employment wages labor market displacement effects"


def _make_evidence():
    """One already-assigned row + four candidates:
      - ev_on1 / ev_on2: clearly on-topic (share many AI/labor tokens).
      - ev_offtopic: a generic METHODS paper that shares exactly 2 generic tokens
        ('labor', 'employment') with the question via boilerplate, but NOTHING with a
        narrow section focus — the weak >=2 bar admits it (the #1229 bug).
      - ev_marquee: an on-topic required-entity/anchor row (seed_source flag set).
    """
    return [
        _row("ev_seed", "https://seed.example/a", "generative artificial intelligence automation"),
        _row(
            "ev_on1",
            "https://journal.example/on1",
            "generative artificial intelligence automation reshapes labor employment and wages",
        ),
        _row(
            "ev_on2",
            "https://journal.example/on2",
            "automation of employment tasks lowers wages across the labor market",
        ),
        _row(
            "ev_offtopic",
            "https://methods.example/bias",
            "systematic review english language publication bias in labor employment "
            "studies methodology",
        ),
        # marquee row: on-topic enough to pass the q>=2 bar (shares 'automation',
        # 'labor') but with LOWER section/question overlap than the generic on-topic
        # rows, so it ranks LOW by the historical key and only floats to the top when
        # PG_BREADTH_MARQUEE_PRIORITY is on. Stamped with the required-entity lane.
        _row(
            "ev_marquee",
            "https://nber.example/anchor",
            "automation reshapes labor productivity in firms",
            seed_source="required_entity_lane",
            query_origin="required_entity_targeted_search",
        ),
    ]


# --------------------------------------------------------------------------- #1229
def test_flag_off_identity_selects_offtopic_like_historical_bar():
    """Flag-OFF: the historical >=2 question-overlap bar admits the off-topic methods
    row (the exact #1229 bug). This pins current behaviour so the fix is provably
    off-by-default identical."""
    evidence = _make_evidence()
    plans = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    assigned = set(plans[0].ev_ids)
    # weak bar admits the off-topic methods row
    assert "ev_offtopic" in assigned
    assert {"ev_on1", "ev_on2"} <= assigned


def test_min_overlap_flag_rejects_offtopic_row(monkeypatch):
    """#1229 flag-ON: a higher PG_BREADTH_AUGMENT_MIN_OVERLAP rejects the off-topic
    methods row (which only shares 2 generic tokens) while keeping the on-topic rows."""
    monkeypatch.setenv(_FLAG_MIN_OVERLAP, "3")
    evidence = _make_evidence()
    plans = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    assigned = set(plans[0].ev_ids)
    assert "ev_offtopic" not in assigned, "tighter bar must drop the off-topic methods row"
    assert {"ev_on1", "ev_on2"} <= assigned, "on-topic rows still admitted"


def test_min_overlap_below_two_is_clamped_to_historical_floor(monkeypatch):
    """A value < 2 must clamp to 2 (never loosen below the historical bar)."""
    monkeypatch.setenv(_FLAG_MIN_OVERLAP, "0")
    evidence = _make_evidence()
    plans_clamped = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_clamped, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    # identical to flag-off
    plans_default = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_default, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    assert set(plans_clamped[0].ev_ids) == set(plans_default[0].ev_ids)


def test_require_section_overlap_rejects_topically_off_row(monkeypatch):
    """#1229 flag-ON: requiring >=1 section-focus content token drops a row that passes
    the question bar but shares nothing topical with the section."""
    # Off-topic row shares 'labor'/'employment' with the QUESTION; craft a section
    # title + focus that contain NEITHER (the title contributes tokens too, so use a
    # neutral 'Outlook' title) to isolate the section-overlap effect.
    narrow_focus = "wages displacement productivity"
    evidence = _make_evidence()
    plans = [_plan("Outlook", narrow_focus, ["ev_seed"])]
    monkeypatch.setenv(_FLAG_SECTION_OVERLAP, "1")
    _augment_legacy_section_breadth(
        plans, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    assigned = set(plans[0].ev_ids)
    # ev_offtopic shares no token with 'wages displacement productivity'
    assert "ev_offtopic" not in assigned
    # ev_on2 mentions 'wages' -> shares a section token, stays
    assert "ev_on2" in assigned


# --------------------------------------------------------------------------- #1231
def test_breadth_row_is_marquee_detects_existing_fields():
    """The marquee detector recognises required-entity-lane stamps and anchor flags
    using ONLY existing row fields (no schema invention)."""
    assert _breadth_row_is_marquee({"seed_source": "required_entity_lane"})
    assert _breadth_row_is_marquee({"query_origin": "required_entity_targeted_search"})
    assert _breadth_row_is_marquee({"anchor_seed": True})
    assert _breadth_row_is_marquee({"is_marquee": True})
    assert not _breadth_row_is_marquee({"seed_source": "serper"})
    assert not _breadth_row_is_marquee({})


def test_marquee_priority_orders_anchor_first(monkeypatch):
    """#1231 flag-ON: with a target that admits only ONE extra row, the marquee anchor
    is selected FIRST; flag-OFF it is NOT (historical order admits a generic row first)."""
    evidence = _make_evidence()

    # target = current(1) + 1 => exactly one augmentation slot.
    # Flag OFF: historical (fresh, sec_overlap, auth, q_overlap) order -> the marquee row
    # is NOT guaranteed first. Capture the off-result.
    plans_off = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_off, evidence, _RESEARCH_Q, skip_titles=set(), target=2
    )
    off_added = [e for e in plans_off[0].ev_ids if e != "ev_seed"]

    # Flag ON: the marquee row MUST be the one added.
    monkeypatch.setenv(_FLAG_MARQUEE, "1")
    plans_on = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_on, evidence, _RESEARCH_Q, skip_titles=set(), target=2
    )
    on_added = [e for e in plans_on[0].ev_ids if e != "ev_seed"]

    assert on_added == ["ev_marquee"], (
        f"marquee priority must add the anchor first, got {on_added}"
    )
    # And it changes the outcome vs the off path (off did not pick the marquee first).
    assert off_added != ["ev_marquee"], (
        "fixture must be constructed so the off-path does NOT pick the marquee first"
    )


def test_marquee_priority_off_is_identity(monkeypatch):
    """#1231 flag-OFF: the marquee flag unset yields the SAME selection set as never
    touching the flag (default-off identity for a wide target)."""
    evidence = _make_evidence()
    plans_a = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_a, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    monkeypatch.setenv(_FLAG_MARQUEE, "0")
    plans_b = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    _augment_legacy_section_breadth(
        plans_b, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )
    assert set(plans_a[0].ev_ids) == set(plans_b[0].ev_ids)


# --------------------------------------------------------------------------- #1233
# Codex iter-1 REQUEST_CHANGES: the canary NO LONGER lives in _augment_legacy_section_breadth
# (that measured the pre-generation candidate MENU breadth, not the cited count, and could pass
# while the rendered report cited too few). _augment now only DISCLOSES the menu breadth and never
# raises; the binding canary is the pure `enforce_breadth_canary`, called by the sweep runner
# AFTER the bibliography (= distinct CITED sources) is built. These tests cover both.
def test_augment_never_raises_on_thin_breadth_even_with_flag_set(monkeypatch):
    """#1233 (post-fix): _augment_legacy_section_breadth NEVER raises on thin breadth, even when
    PG_BREADTH_CANARY_MIN is set to an unreachable value — the canary moved to the post-bibliography
    site. _augment only logs the candidate-menu breadth now."""
    evidence = _make_evidence()  # at most ~5 distinct sources reachable
    plans = [_plan("Labor Effects", _SECTION_FOCUS, ["ev_seed"])]
    monkeypatch.setenv(_FLAG_CANARY, "999")  # would have raised under the old in-_augment canary
    # no exception — _augment no longer enforces the canary
    _augment_legacy_section_breadth(
        plans, evidence, _RESEARCH_Q, skip_titles=set(), target=10
    )


def test_enforce_breadth_canary_noop_when_minimum_zero():
    """#1233: minimum <= 0 (default PG_BREADTH_CANARY_MIN unset) is a no-op — never raises."""
    enforce_breadth_canary(0, 0)
    enforce_breadth_canary(0, -5)
    enforce_breadth_canary(3, 0)


def test_enforce_breadth_canary_raises_below_minimum():
    """#1233: when the distinct CITED-source count is below the minimum, FAIL LOUD with a clear
    RuntimeError. This is the real breadth canary, measured against the rendered bibliography."""
    with pytest.raises(RuntimeError, match="breadth canary FAILED"):
        enforce_breadth_canary(2, 5)
    with pytest.raises(RuntimeError, match="breadth canary FAILED"):
        enforce_breadth_canary(0, 1)


def test_enforce_breadth_canary_passes_at_or_above_minimum():
    """#1233: at or above the minimum cited-source count, no raise."""
    enforce_breadth_canary(5, 5)   # exactly at the floor
    enforce_breadth_canary(8, 5)   # above the floor
