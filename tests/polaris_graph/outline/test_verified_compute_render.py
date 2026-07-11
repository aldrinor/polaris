"""W3-render: the compute-reachability P1, render half — CLOSED and PROVED end-to-end.

This is the load-bearing faithfulness proof for the agentic outliner's moat (COMPUTE-and-PROVE
numbers). It exercises the REAL machinery — no mocks of the verifier, spec builder, sandbox, or
canonical formatter — on ONE real FinanceBench case (Adobe operating income change
FY2015->FY2016, gold delta ≈ $590 million).

Two invariants, proven together:
  (A) RENDER LANE: a number the agent DERIVED ($590,507,000.00 = (1,493,602 - 903,095) * 1000
      thousands USD) renders through ``strict_verify`` via its ``[#calc:...]`` token —
      kept=1, dropped=0 — and the exact canonical display string survives.
  (D) DROP GUARD: the SAME derived number, routed instead through the ``[#ev:...]`` / ``[CITE:...]``
      evidence-span path, is DROPPED (``number_not_in_any_cited_span``) — because a derived value
      appears in no single source span. This is the faithfulness invariant: a derived/unverified
      number can NEVER reach the citation render path (a P0 breach if it could).

REAL DATA: the evidence spans carry the actual 10-K operating-income literals; the span is
DERIVED by the tool (``literal_span_is_faithful``), not asserted by the test.
"""
from __future__ import annotations

import asyncio

from src.polaris_graph.generator.provenance_generator import strict_verify
from src.polaris_graph.outline.outline_agent import OutlineWorkspace
from src.polaris_graph.outline.verified_compute import ComputedClaim, run_verified_compute

# Adobe 10-K, thousands USD: FY2016 operating income = 1,493,602 ; FY2015 = 903,095.
# delta = 590,507 (thousands) = $590,507,000  (FinanceBench gold ≈ $590 million).
_EV = {
    "ev_2016": {
        "evidence_id": "ev_2016",
        "direct_quote": "Adobe reported operating income of 1,493,602 for fiscal 2016.",
    },
    "ev_2015": {
        "evidence_id": "ev_2015",
        "direct_quote": "Adobe reported operating income of 903,095 for fiscal 2015.",
    },
}
_DATAPOINTS = [
    {"evidence_id": "ev_2016", "label": "opinc_2016", "context": "fiscal 2016",
     "value": "1493602", "unit": "kUSD"},
    {"evidence_id": "ev_2015", "label": "opinc_2015", "context": "fiscal 2015",
     "value": "903095", "unit": "kUSD"},
]
_RAW_SPEC = {
    "model_id": "opinc_delta",
    "title": "Adobe operating income change FY2015->FY2016",
    "inputs": [
        {"name": "opinc_2016", "datapoint_ref": {
            "ev_id": "ev_2016", "label": "opinc_2016", "context": "fiscal 2016",
            "value": "1493602", "unit": "kUSD"}},
        {"name": "opinc_2015", "datapoint_ref": {
            "ev_id": "ev_2015", "label": "opinc_2015", "context": "fiscal 2015",
            "value": "903095", "unit": "kUSD"}},
    ],
    # *1000 converts the thousands-denominated literals to dollars; the scale is a formula
    # constant (disclosed), the INPUT literals stay verbatim-cited.
    "outputs": [
        {"name": "delta", "formula": "(opinc_2016 - opinc_2015) * 1000",
         "unit": "USD", "display_kind": "currency"},
    ],
}
_QUESTION = "What was Adobe's operating income change from FY2015 to FY2016?"
_GOLD_DISPLAY = "$590,507,000.00"


def _workspace() -> OutlineWorkspace:
    return OutlineWorkspace(research_question=_QUESTION, ev_store=dict(_EV))


def _compute(ws: OutlineWorkspace) -> ComputedClaim:
    claim = asyncio.run(run_verified_compute(
        ws, question=_QUESTION, datapoints=_DATAPOINTS, raw_spec=_RAW_SPEC,
    ))
    assert claim is not None, "verified_compute returned None — the Adobe spec must build+execute"
    return claim


# --------------------------------------------------------------------------- build/register


def test_verified_compute_produces_gold_display_and_registers_model():
    ws = _workspace()
    claim = _compute(ws)

    assert claim.display_value == _GOLD_DISPLAY, (
        f"gold delta must be {_GOLD_DISPLAY}, got {claim.display_value}"
    )
    assert claim.model_id == "opinc_delta"
    assert claim.field_id == "delta"
    assert claim.calc_token == f"[#calc:opinc_delta:{claim.spec_hash}:delta]"
    # The verified model is registered EXACTLY as strict_verify consumes it.
    assert (claim.model_id, claim.spec_hash) in ws.quantified_models
    # ...and this is a SEPARATE surface from exploratory execute_python output.
    assert ws.compute_results == []


# --------------------------------------------------------------------------- (A) render lane


def test_derived_number_RENDERS_through_the_calc_lane_kept1_dropped0():
    ws = _workspace()
    claim = _compute(ws)

    sentence = claim.render_sentence("Adobe's operating income rose by")
    assert _GOLD_DISPLAY in sentence and claim.calc_token in sentence

    report = strict_verify(sentence, ws.ev_store, quantified_models=ws.quantified_models)

    assert report.total_kept == 1 and report.total_dropped == 0, (
        f"CALC LANE must keep the computed sentence, got "
        f"kept={report.total_kept} dropped={report.total_dropped} "
        f"reasons={[d.failure_reasons for d in report.dropped_sentences]}"
    )
    kept = report.kept_sentences[0]
    # The kept sentence's provenance tokens are the SOURCE INPUTS (the calc token strips to the
    # inputs it was derived from), so the rendered number is traceable to the two 10-K spans.
    cited = {t.evidence_id for t in kept.tokens}
    assert cited == {"ev_2016", "ev_2015"}, f"computed number must cite BOTH inputs, got {cited}"


# --------------------------------------------------------------------------- (D) drop guard


def test_derived_number_via_CITE_evidence_span_is_DROPPED():
    """The faithfulness invariant: a derived number can NEVER render through [#ev:]/[CITE:].

    Route the SAME $590,507,000.00 through an evidence-span citation over a VALID in-bounds span
    of a real source. It is dropped because the derived digits appear in no single source span.
    """
    ws = _workspace()
    claim = _compute(ws)

    span_len = len(_EV["ev_2016"]["direct_quote"])
    bad = f"Adobe's operating income rose by {claim.display_value} [#ev:ev_2016:0-{span_len}]."

    report = strict_verify(bad, ws.ev_store, quantified_models=ws.quantified_models)

    assert report.total_kept == 0 and report.total_dropped == 1, (
        f"a derived number cited via an evidence span MUST be dropped, got "
        f"kept={report.total_kept} dropped={report.total_dropped}"
    )
    reasons = report.dropped_sentences[0].failure_reasons
    assert any("number_not_in_any_cited_span" in r for r in reasons), (
        f"drop must be the number-not-in-span faithfulness guard, got {reasons}"
    )


def test_a_wrong_number_next_to_the_calc_token_is_DROPPED():
    """Regime-C adjacency (check c): the calc token cannot be reused to bless a DIFFERENT number.

    If the outline text places a wrong figure immediately before the (valid, registered) calc
    token, strict_verify drops it — the token proves ONLY its own canonical display value.
    """
    ws = _workspace()
    claim = _compute(ws)

    wrong = f"Adobe's operating income rose by $999,999,999.00 {claim.calc_token}."
    report = strict_verify(wrong, ws.ev_store, quantified_models=ws.quantified_models)

    assert report.total_kept == 0 and report.total_dropped == 1, (
        "a wrong number adjacent to a real calc token must be dropped"
    )
    reasons = report.dropped_sentences[0].failure_reasons
    assert any("calc_number_mismatch" in r for r in reasons), reasons


# --------------------------------------------------------------------------- fail-closed build


def test_unfaithful_literal_span_fails_closed_and_renders_nothing():
    """If the claimed input value is NOT present in the cited evidence, no model is built and no
    number becomes render-eligible (fail-closed). The registry stays empty."""
    ws = _workspace()
    bad_dps = [
        # value 9999999 is nowhere in ev_2016's text -> no unique literal span.
        {"evidence_id": "ev_2016", "label": "opinc_2016", "context": "fiscal 2016",
         "value": "9999999", "unit": "kUSD"},
        _DATAPOINTS[1],
    ]
    bad_spec = dict(_RAW_SPEC)
    bad_spec["inputs"] = [
        {"name": "opinc_2016", "datapoint_ref": {
            "ev_id": "ev_2016", "label": "opinc_2016", "context": "fiscal 2016",
            "value": "9999999", "unit": "kUSD"}},
        _RAW_SPEC["inputs"][1],
    ]

    claim = asyncio.run(run_verified_compute(
        ws, question=_QUESTION, datapoints=bad_dps, raw_spec=bad_spec,
    ))
    assert claim is None, "an unfaithful input must fail-closed (no render-eligible number)"
    assert ws.quantified_models == {}, "no model may be registered on a fail-closed build"
    assert any("REJECTED" in d for d in ws.disclosures), "the reject must be disclosed"
