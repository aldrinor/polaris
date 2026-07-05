"""I-deepfix-001 tail batch B3 (#1344) — composition honesty fixes RED/GREEN.

Three independent, kill-switched HONESTY fixes; each has a RED (the defect) and a
GREEN (the legitimate case still renders / measures correctly), plus an OFF-switch
byte-identity check. NONE touches the faithfulness engine (strict_verify / NLI /
4-role D8 / provenance); all are render/assignment/disclosure honesty.

FINDING #4  quantified_analysis.should_withhold_composed_output
            - a unit-mismatched ratio (percent / percentage-point) is NOT rendered
            - a dimensionless ratio mixing a cited + an uncited (modeled) operand
              is NOT rendered
            - a valid same-unit cited ratio IS rendered
FINDING #5  multi_section_generator._drop_offtopic_rows_for_assignment
            - a SEMANTIC confirmed-off-topic row is NOT slotted into any aspect
            - an on-topic row IS slotted into its aspect
FINDING #6b completeness_checker.check_completeness(coverage_text=...)
            - an aspect covered only in the CORPUS (not the rendered report) is
              honestly reported UNCOVERED
            - an aspect present in the rendered report IS reported covered
"""
from __future__ import annotations

import asyncio
import types

from src.polaris_graph.generator import quantified_analysis as qa
from src.polaris_graph.generator.quantified_analysis import (
    QuantifiedResult,
    bind_calc_tokens,
    execute_quantified_model,
    formula_is_same_unit_cancelling_ratio,
    formula_units_incompatible,
    is_low_value_filler_output,
    is_valid_cited_ratio,
    render_decision_matrix_prose,
    should_withhold_composed_output,
    _ratio_incompatible,
    _unit_class,
)
from src.polaris_graph.synthesis.tradeoff_modeler import (
    ModeledInput,
    ModelSpec,
    OutputField,
    SourcedInput,
)


# ─────────────────────────────────────────────────────────────────────────────
# FINDING #4 — unit-compatibility + cited-operand gate
# ─────────────────────────────────────────────────────────────────────────────
def _si(name: str, unit: str) -> SourcedInput:
    return SourcedInput(
        name=name, value=1.0, unit=unit, ev_id="ev_1", label=name,
        context="ctx", raw_literal="1", literal_start=0, literal_end=1,
    )


def _mi(name: str, unit: str) -> ModeledInput:
    return ModeledInput(
        name=name, base=1.0, unit=unit, sweep_lo=0.0, sweep_hi=2.0, sweep_step=1.0,
    )


def _out(name: str, formula: str, unit: str = "", kind: str = "number") -> OutputField:
    return OutputField(name=name, unit=unit, display_kind=kind, formula=formula)


def _spec(sourced, modeled, outputs) -> ModelSpec:
    return ModelSpec(
        model_id="m", title="t", sourced_inputs=sourced,
        modeled_inputs=modeled, outputs=outputs, spec_hash="h",
    )


def _result(spec: ModelSpec, field_name: str) -> QuantifiedResult:
    fields = {
        field_name: {
            "value": 2.1, "display_value": "2.1", "display_kind": "number",
            "unit": "", "modeled_used": [], "sourced_tokens": [],
        }
    }
    return QuantifiedResult(spec.model_id, spec.spec_hash, spec, "script", fields=fields)


def _real_result(spec: ModelSpec) -> QuantifiedResult:
    """Build a QuantifiedResult through the PRODUCTION ``execute_quantified_model`` path.

    The deterministic offline sandbox (no network) renders + executes the spec's FIXED
    script and populates each field's REAL ``sourced_tokens`` from the spec's cited
    inputs — exactly the >=2-sourced signature the coarse FIX-2 filler-suppressor keys on.
    This lets the GREEN case prove a valid cited ratio renders on the REAL production path
    (not a hand-built field with ``sourced_tokens=[]`` that never trips FIX-2)."""
    result = asyncio.run(execute_quantified_model(spec, {}))
    assert result is not None, "execute_quantified_model failed (offline sandbox)"
    return result


def _isolate_gate(monkeypatch, *, unit_compat: bool) -> None:
    # Isolate the FINDING #4 gate from the pre-existing FIX-2 filler suppressor so the
    # GREEN same-unit-ratio case is decided by THIS gate alone.
    monkeypatch.setattr(qa, "_FILLER_SUPPRESS_ENABLED", False)
    monkeypatch.setattr(qa, "_UNIT_COMPAT_ENABLED", unit_compat)


def test_f4_red_unit_mismatched_ratio_not_rendered(monkeypatch) -> None:
    _isolate_gate(monkeypatch, unit_compat=True)
    # The drb_72 defect: 0.42% / 0.2 percentage-points -> a dimensionless "impact ratio".
    spec = _spec(
        sourced=[_si("wage", "%"), _si("emp", "percentage points")],
        modeled=[],
        outputs=[_out("wage_to_employment_impact_ratio", "wage / emp")],
    )
    assert should_withhold_composed_output(spec.outputs[0], spec) is True
    prose = render_decision_matrix_prose(spec, _result(spec, "wage_to_employment_impact_ratio"))
    assert "wage to employment impact ratio" not in prose
    assert prose.strip() == ""


def test_f4_red_noncited_ratio_mixing_modeled_operand_not_rendered(monkeypatch) -> None:
    _isolate_gate(monkeypatch, unit_compat=True)
    # A ratio that divides a CITED (sourced) number by an UNCITED (modeled) assumption,
    # rendered dimensionless as if source-grounded -> withheld ("non-cited ratio").
    spec = _spec(
        sourced=[_si("a", "USD")],
        modeled=[_mi("b", "USD")],
        outputs=[_out("cost_ratio", "a / b", kind="ratio")],
    )
    assert should_withhold_composed_output(spec.outputs[0], spec) is True
    prose = render_decision_matrix_prose(spec, _result(spec, "cost_ratio"))
    assert "cost ratio" not in prose


def test_f4_green_same_unit_cited_ratio_renders_under_production_defaults() -> None:
    # ITER-2 P1 (drb_72 regression): under PRODUCTION DEFAULTS — the FIX-2 filler
    # suppressor AND the FINDING #4 unit-compat gate BOTH ON, no monkeypatch — a valid
    # same-unit (USD/USD) ratio over two CITED operands MUST render. The result is built
    # through the production ``execute_quantified_model`` path so the field carries REAL
    # sourced_tokens (2), the exact >=2-sourced signature the coarse FIX-2 suppressor keys
    # on. This proves the unit-compat gate GOVERNS the valid-cited-ratio path and FIX-2
    # never blanks it — the iter-1 green test used sourced_tokens=[] and so never trod the
    # production path.
    assert qa._FILLER_SUPPRESS_ENABLED is True   # production default: FIX-2 suppressor ON
    assert qa._UNIT_COMPAT_ENABLED is True       # production default: unit-compat gate ON
    spec = _spec(
        sourced=[_si("a", "USD"), _si("b", "USD")],
        modeled=[],
        outputs=[_out("cost_ratio", "a / b", kind="ratio")],
    )
    result = _real_result(spec)
    # the production executor populated real sourced_tokens for BOTH cited operands.
    assert len(result.fields["cost_ratio"]["sourced_tokens"]) == 2
    # FIX-2 alone WOULD blank it (unit-free ratio over >=2 sourced inputs) ...
    assert is_low_value_filler_output(result.fields["cost_ratio"]) is True
    # ... but the unit-compat gate affirmatively CLEARS it as a valid same-unit cited ratio.
    assert should_withhold_composed_output(spec.outputs[0], spec) is False
    assert is_valid_cited_ratio(spec.outputs[0], spec) is True
    prose = render_decision_matrix_prose(spec, result)
    assert "cost ratio" in prose                 # GREEN: renders under production defaults
    assert bind_calc_tokens(prose, result).strip() != ""


def test_f4_red_dimensionless_sum_over_cited_operands_suppressed_under_production_defaults() -> None:
    # ITER-3 P1 (Codex): the iter-2 exemption was too broad — it cleared ANY dimensionless
    # output over cited-only operands, so a plain SUM ``a + b`` of two CITED USD amounts,
    # declared dimensionless (empty unit, display_kind="number"), earned the same-unit-ratio
    # exemption and RENDERED — reopening the FIX-2 filler hole. A sum is NOT a units-cancel
    # division, so ``is_valid_cited_ratio`` must return False and FIX-2 must STILL suppress
    # it. Proven on the PRODUCTION path (real sourced_tokens) under PRODUCTION DEFAULTS
    # (FIX-2 suppressor AND the unit-compat gate BOTH ON, no monkeypatch).
    assert qa._FILLER_SUPPRESS_ENABLED is True   # production default: FIX-2 suppressor ON
    assert qa._UNIT_COMPAT_ENABLED is True       # production default: unit-compat gate ON
    spec = _spec(
        sourced=[_si("a", "USD"), _si("b", "USD")],
        modeled=[],
        outputs=[_out("sum_ab", "a + b", kind="number")],
    )
    result = _real_result(spec)
    # the production executor populated real sourced_tokens for BOTH cited operands ...
    assert len(result.fields["sum_ab"]["sourced_tokens"]) == 2
    # ... so the coarse FIX-2 suppressor flags it (dimensionless number over >=2 sourced) ...
    assert is_low_value_filler_output(result.fields["sum_ab"]) is True
    # ... FINDING #4 does NOT withhold it (units compatible, no cited+modeled mix) ...
    assert should_withhold_composed_output(spec.outputs[0], spec) is False
    # ... but it is NOT a same-unit cancelling ratio, so the exemption does NOT fire ...
    assert is_valid_cited_ratio(spec.outputs[0], spec) is False
    prose = render_decision_matrix_prose(spec, result)
    assert "sum ab" not in prose                 # RED: FIX-2 STILL suppresses the sum
    assert prose.strip() == ""


def test_f4_formula_is_same_unit_cancelling_ratio_cases() -> None:
    # ITER-3 P1 predicate: ONLY a Div of two operands sharing ONE non-neutral class qualifies.
    usd = {"a": "currency_usd", "b": "currency_usd", "c": "currency_usd"}
    # GENUINE same-unit cancelling division -> qualifies.
    assert formula_is_same_unit_cancelling_ratio("a / b", usd) is True
    # Sum / difference / product over the SAME cited unit -> NOT a cancelling ratio.
    assert formula_is_same_unit_cancelling_ratio("a + b", usd) is False
    assert formula_is_same_unit_cancelling_ratio("a - b", usd) is False
    assert formula_is_same_unit_cancelling_ratio("a * b", usd) is False
    # A division whose numerator compounds dimensions (a*b/c) -> NOT a simple cancelling ratio.
    assert formula_is_same_unit_cancelling_ratio("a * b / c", usd) is False
    # Cross-family division (currency / years) is a RATE, not a dimensionless cancel.
    assert formula_is_same_unit_cancelling_ratio(
        "a / b", {"a": "currency_usd", "b": "years"}
    ) is False
    # Same-family DIFFERENT member (percent / percentage-point) does not cancel.
    assert formula_is_same_unit_cancelling_ratio(
        "a / b", {"a": "percent", "b": "percentage_point"}
    ) is False
    # A division of a cited unit by a neutral/constant operand stays dimensioned.
    assert formula_is_same_unit_cancelling_ratio("a / 2", {"a": "currency_usd"}) is False
    # Unparseable formula -> fail-closed for the exemption (defer to FIX-2).
    assert formula_is_same_unit_cancelling_ratio("a / / b", usd) is False


def test_f4_offswitch_byte_identical_ratio_renders(monkeypatch) -> None:
    # Kill-switch OFF: the unit-mismatched ratio renders exactly as before (byte-identical).
    _isolate_gate(monkeypatch, unit_compat=False)
    spec = _spec(
        sourced=[_si("wage", "%"), _si("emp", "percentage points")],
        modeled=[],
        outputs=[_out("wage_to_employment_impact_ratio", "wage / emp")],
    )
    assert should_withhold_composed_output(spec.outputs[0], spec) is False
    prose = render_decision_matrix_prose(spec, _result(spec, "wage_to_employment_impact_ratio"))
    assert "wage to employment impact ratio" in prose


def test_f4_unit_class_and_ratio_incompatible_helpers() -> None:
    assert _unit_class("%") == "percent"
    assert _unit_class("percentage points") == "percentage_point"
    assert _unit_class("USD") == "currency_usd"
    assert _unit_class("") is None
    assert _unit_class("apples") == "apples"
    # percent / percentage-point: same family, different member -> incompatible ratio.
    assert _ratio_incompatible("percent", "percentage_point") is True
    # same class cancels; cross-family (currency / percent) is a legit rate.
    assert _ratio_incompatible("percent", "percent") is False
    assert _ratio_incompatible("currency_usd", "percent") is False


def test_f4_formula_units_incompatible_cases() -> None:
    # Div of same-family different members -> incompatible.
    assert formula_units_incompatible(
        "wage / emp", {"wage": "percent", "emp": "percentage_point"}
    ) is True
    # Add/Sub across ANY two classes -> incompatible (cannot add dollars to years).
    assert formula_units_incompatible(
        "a - b", {"a": "currency_usd", "b": "percent"}
    ) is True
    # Multiplication may mix units (rate * quantity) -> allowed.
    assert formula_units_incompatible(
        "a * b", {"a": "currency_usd", "b": "years"}
    ) is False
    # Cross-family division (currency / time = a rate) -> allowed.
    assert formula_units_incompatible(
        "a / b", {"a": "currency_usd", "b": "years"}
    ) is False
    # Same-unit ratio cancels -> allowed.
    assert formula_units_incompatible(
        "a / b", {"a": "currency_usd", "b": "currency_usd"}
    ) is False
    # Unparseable formula -> fail-open (never a false drop).
    assert formula_units_incompatible("a / / b", {"a": "percent"}) is False


# ─────────────────────────────────────────────────────────────────────────────
# FINDING #5 — aspect off-topic slot guard
# ─────────────────────────────────────────────────────────────────────────────
def _section(title: str):
    return types.SimpleNamespace(archetype="", title=title, evidence_target=0)


def _assign(outline, evidence):
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    return _assign_evidence_to_planned_outline(outline, evidence, sub_queries=None)


def test_f5_red_offtopic_row_not_slotted(monkeypatch) -> None:
    monkeypatch.setenv("PG_ASPECT_OFFTOPIC_SLOT_GUARD", "1")
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")  # deterministic row clamp (no char budget)
    outline = [_section("Negative aspect")]
    evidence = [
        {"evidence_id": "ev_on", "direct_quote": "AI displaced 14% of postings."},
        # SEMANTIC confirmed-off-topic (DEFER-1 label) — must NOT be slotted.
        {"evidence_id": "ev_off", "direct_quote": "Unrelated bankruptcy filing.",
         "content_relevance_label": "demoted"},
    ]
    plans = _assign(outline, evidence)
    slotted = {e for p in plans for e in p.ev_ids}
    assert "ev_off" not in slotted          # RED: off-topic backfill blocked
    assert "ev_on" in slotted               # GREEN: on-topic surfaces in its aspect


def test_f5_offswitch_byte_identical_offtopic_still_slotted(monkeypatch) -> None:
    monkeypatch.setenv("PG_ASPECT_OFFTOPIC_SLOT_GUARD", "0")
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    outline = [_section("Negative aspect")]
    evidence = [
        {"evidence_id": "ev_on", "direct_quote": "AI displaced 14% of postings."},
        {"evidence_id": "ev_off", "direct_quote": "Unrelated bankruptcy filing.",
         "content_relevance_label": "demoted"},
    ]
    plans = _assign(outline, evidence)
    slotted = {e for p in plans for e in p.ev_ids}
    assert "ev_off" in slotted and "ev_on" in slotted   # OFF: pre-fix behaviour


def test_f5_topic_offtopic_demoted_flag_also_blocked(monkeypatch) -> None:
    monkeypatch.setenv("PG_ASPECT_OFFTOPIC_SLOT_GUARD", "1")
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    outline = [_section("Opportunities")]
    evidence = [
        {"evidence_id": "ev_keep", "direct_quote": "New AI-augmentation roles emerged."},
        {"evidence_id": "ev_drop", "direct_quote": "Food-industry robotics case.",
         "topic_offtopic_demoted": True},
    ]
    plans = _assign(outline, evidence)
    slotted = {e for p in plans for e in p.ev_ids}
    assert "ev_drop" not in slotted and "ev_keep" in slotted


# ─────────────────────────────────────────────────────────────────────────────
# FINDING #6b — completeness coverage-against-OUTPUT honesty
# ─────────────────────────────────────────────────────────────────────────────
def _controlled_checklist(monkeypatch):
    from src.polaris_graph.nodes import completeness_checker as cc
    topics = [
        cc.ChecklistTopic(id="displacement", label="Displacement",
                          keywords=["displacement"], applies_if=[]),
        cc.ChecklistTopic(id="wages", label="Wages",
                          keywords=["wage"], applies_if=[]),
    ]
    monkeypatch.setattr(cc, "load_checklist", lambda domain: list(topics))
    return cc


def test_f6b_red_corpus_only_aspect_reported_uncovered(monkeypatch) -> None:
    cc = _controlled_checklist(monkeypatch)
    monkeypatch.setenv("PG_COMPLETENESS_COVERAGE_AGAINST_OUTPUT", "1")
    evidence = [{"direct_quote": "AI drives job displacement and wage change.",
                 "statement": ""}]
    # The RENDERED report only actually discusses wages, NOT displacement.
    coverage_text = "The report discusses AI wage premiums in detail."
    report = cc.check_completeness(
        domain="workforce", research_question="AI impact on labor",
        evidence_rows=evidence, coverage_text=coverage_text,
    )
    assert report.total_applicable == 2
    assert report.total_covered == 1                     # honest: only wages
    assert "displacement" in report.uncovered_topic_ids()  # RED: gap, not false-complete


def test_f6b_green_rendered_aspect_reported_covered(monkeypatch) -> None:
    cc = _controlled_checklist(monkeypatch)
    monkeypatch.setenv("PG_COMPLETENESS_COVERAGE_AGAINST_OUTPUT", "1")
    evidence = [{"direct_quote": "AI drives job displacement and wage change.",
                 "statement": ""}]
    coverage_text = "The report covers job displacement AND wage premiums."
    report = cc.check_completeness(
        domain="workforce", research_question="AI impact on labor",
        evidence_rows=evidence, coverage_text=coverage_text,
    )
    assert report.total_covered == 2                     # both actually presented
    assert report.uncovered_topic_ids() == []


def test_f6b_baseline_corpus_coverage_when_no_coverage_text(monkeypatch) -> None:
    cc = _controlled_checklist(monkeypatch)
    evidence = [{"direct_quote": "AI drives job displacement and wage change.",
                 "statement": ""}]
    # No coverage_text -> byte-identical legacy corpus-based coverage (both covered).
    report = cc.check_completeness(
        domain="workforce", research_question="AI impact on labor",
        evidence_rows=evidence,
    )
    assert report.total_covered == 2 and report.uncovered_topic_ids() == []


def test_f6b_offswitch_ignores_coverage_text(monkeypatch) -> None:
    cc = _controlled_checklist(monkeypatch)
    monkeypatch.setenv("PG_COMPLETENESS_COVERAGE_AGAINST_OUTPUT", "0")
    evidence = [{"direct_quote": "AI drives job displacement and wage change.",
                 "statement": ""}]
    coverage_text = "The report discusses AI wage premiums in detail."  # no displacement
    report = cc.check_completeness(
        domain="workforce", research_question="AI impact on labor",
        evidence_rows=evidence, coverage_text=coverage_text,
    )
    # Kill-switch OFF: coverage_text ignored -> corpus-based -> both covered (byte-identical).
    assert report.total_covered == 2 and report.uncovered_topic_ids() == []
