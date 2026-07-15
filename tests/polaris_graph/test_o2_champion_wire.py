"""feat/intake-contract — O2 CHAMPION-PATH wire (multi_section_generator).

The champion compose path (compose_agentic_report_s3gear329 ->
generate_multi_section_report) does NOT route through scope_gate/blueprint_node, so
the instruction-slot consumer is wired at the section-plan convergence point via the
pure helper ``_compute_instruction_slot_coverage``. These tests prove:

  (a) FLAG OFF  -> helper returns [] and does ZERO work: the slot extractor is never
      invoked and the finalized SectionPlan list is byte-identical to today;
  (b) FLAG ON   -> per-slot ``satisfied`` coverage is computed against plan
      title+focus (covered => True, uncovered => False), while EVERY SectionPlan
      (title/focus/ev_ids/archetype/undersupplied/basket_ids) is UNCHANGED — the
      wire annotates, it never reorganizes or drops;
  (c) the plan->throwaway-SectionSpec adapter maps focus -> description and does not
      raise (SectionPlan lacks .description/.search_keywords);
  (d) MultiSectionResult carries the observe-only field default-empty (OFF byte-id);
  (e) faithfulness firewall: the helper's module imports no strict_verify/provenance.

Fully offline/deterministic: regex slot extractor with llm_fn=None, pure bind. No
generator run, no network, no LLM, no compose.
"""
from __future__ import annotations

import copy
import dataclasses

from src.polaris_graph.generator.multi_section_generator import (
    MultiSectionResult,
    SectionPlan,
    _compute_instruction_slot_coverage,
)

# A synthetic champion research_question with an explicit comparison instruction.
# (Kept trailing-clause-free so the regex yields the clean entities
# ['remote work', 'office work'] rather than folding an adverbial tail into an entity.)
_Q_COVERED = "Compare remote work versus office work."
# Same question; the outline below covers ONLY 'remote work' -> uncovered slot.
_Q_UNCOVERED = "Compare remote work versus office work."


def _covered_plans() -> list[SectionPlan]:
    """A finalized outline where BOTH comparison entities appear in title/focus."""
    return [
        SectionPlan(
            title="Remote work productivity",
            focus="Evidence on remote work output and focus time.",
            ev_ids=["ev1", "ev2"],
            archetype="",
            undersupplied=False,
            basket_ids=["b1"],
        ),
        SectionPlan(
            title="Office work dynamics",
            focus="Evidence on office work collaboration and overhead.",
            ev_ids=["ev3", "ev4"],
            archetype="",
            undersupplied=False,
            basket_ids=["b2"],
        ),
    ]


def _uncovered_plans() -> list[SectionPlan]:
    """A finalized outline covering ONLY 'remote work' -> 'office work' uncovered."""
    return [
        SectionPlan(
            title="Remote work productivity",
            focus="Evidence on remote work output.",
            ev_ids=["ev1", "ev2"],
        ),
    ]


def _snapshot(plans: list[SectionPlan]):
    """A deep, order-preserving structural snapshot of every plan field."""
    return [dataclasses.astuple(p) for p in plans]


# ── (a) FLAG OFF: zero work, plans byte-identical, extractor never called ─────

def test_flag_off_returns_empty_and_never_calls_extractor(monkeypatch) -> None:
    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)

    calls = {"n": 0}
    import src.polaris_graph.retrieval.intake_constraint_extractor as ice

    def _spy(*a, **k):  # pragma: no cover - must never run when flag is OFF
        calls["n"] += 1
        raise AssertionError("extract_instruction_slots called on flag-OFF path")

    monkeypatch.setattr(ice, "extract_instruction_slots", _spy)

    plans = _covered_plans()
    before = _snapshot(plans)
    out = _compute_instruction_slot_coverage(_Q_COVERED, plans)

    assert out == []
    assert calls["n"] == 0
    assert _snapshot(plans) == before  # plans untouched, byte-identical


def test_flag_off_is_byte_identical_across_calls(monkeypatch) -> None:
    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)
    plans = _covered_plans()
    baseline = copy.deepcopy(plans)
    _compute_instruction_slot_coverage(_Q_COVERED, plans)
    assert _snapshot(plans) == _snapshot(baseline)


# ── (b) FLAG ON: satisfied computed, plans still unchanged ────────────────────

def test_flag_on_covered_slot_satisfied_and_plans_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("PG_EXTRACT_INSTRUCTION_SLOTS", "1")
    plans = _covered_plans()
    before = _snapshot(plans)

    cov = _compute_instruction_slot_coverage(_Q_COVERED, plans)

    assert cov, "expected instruction-slot telemetry with the flag on"
    comparison = [s for s in cov if s["kind"] == "comparison"]
    assert comparison, f"expected a comparison slot, got {[s['kind'] for s in cov]}"
    # Both entities ('remote work', 'office work') appear in the plans -> satisfied.
    assert comparison[0]["satisfied"] is True
    # ADD-ONLY: every SectionPlan field is byte-identical (no undersupplied flip,
    # no ev_ids drop, no reorder).
    assert _snapshot(plans) == before
    assert all(p.undersupplied is False for p in plans)


def test_flag_on_uncovered_slot_unsatisfied_and_plans_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("PG_EXTRACT_INSTRUCTION_SLOTS", "1")
    plans = _uncovered_plans()
    before = _snapshot(plans)

    cov = _compute_instruction_slot_coverage(_Q_UNCOVERED, plans)

    comparison = [s for s in cov if s["kind"] == "comparison"]
    assert comparison, "expected a comparison slot"
    # 'office work' is not covered by the single remote-only section -> unsatisfied.
    assert comparison[0]["satisfied"] is False
    # The THIN side effect lands on the throwaway specs, NOT on the plan:
    # SectionPlan.undersupplied must remain False (no auto-flip).
    assert _snapshot(plans) == before
    assert plans[0].undersupplied is False


# ── (c) adapter: SectionPlan (no .description) -> throwaway SectionSpec ────────

def test_adapter_maps_focus_to_description_without_raising(monkeypatch) -> None:
    monkeypatch.setenv("PG_EXTRACT_INSTRUCTION_SLOTS", "1")
    # SectionPlan has no `.description` / `.search_keywords`; a satisfied comparison
    # can ONLY be computed if focus text was mapped into the spec haystack. The
    # 'office work' entity appears ONLY in a plan's focus, not its title.
    plans = [
        SectionPlan(title="Section A", focus="covers remote work here", ev_ids=["e1"]),
        SectionPlan(title="Section B", focus="covers office work here", ev_ids=["e2"]),
    ]
    cov = _compute_instruction_slot_coverage(
        "Compare remote work versus office work.", plans,
    )
    comparison = [s for s in cov if s["kind"] == "comparison"]
    assert comparison and comparison[0]["satisfied"] is True


# ── (d) MultiSectionResult default-empty field (OFF byte-identity) ────────────

def test_result_field_defaults_empty() -> None:
    r = MultiSectionResult(
        sections=[],
        outline=[],
        bibliography=[],
        total_words=0,
        total_sentences_verified=0,
        total_sentences_dropped=0,
        total_input_tokens=0,
        total_output_tokens=0,
    )
    assert r.instruction_slot_coverage == []


# ── (e) faithfulness firewall: helper source imports no verify/provenance ─────

def test_helper_touches_no_faithfulness_module() -> None:
    import inspect

    import src.polaris_graph.generator.multi_section_generator as msg

    src = inspect.getsource(msg._compute_instruction_slot_coverage)
    for forbidden in ("strict_verify", "provenance", "_audit_citations"):
        assert forbidden not in src
