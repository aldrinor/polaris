"""MOAT LIVE-SEAM: the [#calc:] calc-lane render proven on the FULL-CORPUS composer path.

STEP-4 proved the moat through ``run_honest_pipeline`` (the honest-full-cycle path). But the
REAL 346-basket ``cp4_used=agentic`` corpus run composes section bodies through
``generate_multi_section_report`` -> ``_run_section``, and there the outline agent's run-scoped
verified-compute registry was DISCARDED at the seam: every section-body ``strict_verify`` was
called with ``quantified_models=None``, so a ``[#calc:]`` body sentence was fail-closed DROPPED
(faithfulness safe, but the moat absent).

This test drives ``_run_section`` DIRECTLY (the exact composer the corpus run uses) with the
registry the outline agent produces, and proves — on the REAL Adobe FinanceBench delta
($590,507,000.00) — that:

  (A) WITH the registry threaded across the live seam, the DERIVED number RENDERS in the section
      ``verified_text`` (kept), traceable to its two 10-K input spans; and
  (D) WITHOUT the registry (quantified_models=None — the legacy default), the SAME body sentence
      is DROPPED and the number never reaches the report.

The verifier, spec builder, sandbox, canonical formatter, rewrite tail and strict_verify are all
REAL — only ``_call_section`` (the LLM writer) is stubbed to emit the composed [#calc:] draft, so
the test is deterministic and offline.
"""
from __future__ import annotations

import asyncio

import src.polaris_graph.generator.multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _run_section,
)
from src.polaris_graph.outline.outline_agent import OutlineWorkspace
from src.polaris_graph.outline.verified_compute import run_verified_compute

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
    "outputs": [
        {"name": "delta", "formula": "(opinc_2016 - opinc_2015) * 1000",
         "unit": "USD", "display_kind": "currency"},
    ],
}
_QUESTION = "What was Adobe's operating income change from FY2015 to FY2016?"
_GOLD_DISPLAY = "$590,507,000.00"


def _registry_and_calc_sentence():
    """Build the run-scoped registry via the REAL verified-compute path; return
    (registry, composed [#calc:] body sentence)."""
    ws = OutlineWorkspace(research_question=_QUESTION, ev_store=dict(_EV))
    claim = asyncio.run(run_verified_compute(
        ws, question=_QUESTION, datapoints=_DATAPOINTS, raw_spec=_RAW_SPEC,
    ))
    assert claim is not None, "the Adobe spec must build+execute"
    assert claim.display_value == _GOLD_DISPLAY
    sentence = claim.render_sentence("Adobe's operating income rose by")
    assert _GOLD_DISPLAY in sentence and claim.calc_token in sentence
    return dict(ws.quantified_models), sentence


def _run_section_over(calc_sentence: str, quantified_models):
    """Drive the FULL-CORPUS composer (``_run_section``) with ``_call_section`` stubbed to emit
    the composed [#calc:] draft; return the resulting SectionResult."""
    section = SectionPlan(
        title="Efficacy",
        focus="Operating income trajectory",
        ev_ids=["ev_2016", "ev_2015"],
    )

    async def _stub_call_section(*_a, **_k):
        # (raw_draft, in_tok, out_tok, atom_catalog) — the real _call_section shape.
        return calc_sentence, 0, 0, {}

    orig = msg._call_section
    msg._call_section = _stub_call_section
    try:
        return asyncio.run(_run_section(
            section, dict(_EV),
            model="stub-model",
            temperature=0.0,
            max_tokens_per_section=512,
            min_kept_fraction=0.0,
            quantified_models=quantified_models,
        ))
    finally:
        msg._call_section = orig


# ------------------------------------------------------------------ (A) render across the seam


def test_calc_number_RENDERS_in_section_body_WITH_registry():
    registry, calc_sentence = _registry_and_calc_sentence()

    result = _run_section_over(calc_sentence, quantified_models=registry)

    assert _GOLD_DISPLAY in result.verified_text, (
        f"the DERIVED number must render in the section body when the agentic registry is threaded "
        f"across the seam; verified_text={result.verified_text!r} "
        f"(kept={result.sentences_verified} dropped={result.sentences_dropped})"
    )
    assert result.sentences_verified >= 1
    assert result.sentences_dropped == 0


# ------------------------------------------------------------------ (D) drop guard without seam


def test_calc_number_is_DROPPED_in_section_body_WITHOUT_registry():
    _registry, calc_sentence = _registry_and_calc_sentence()

    # quantified_models=None is the LEGACY default (the pre-seam state). The [#calc:] token has no
    # evidence-span provenance, so strict_verify drops it no_provenance_token.
    result = _run_section_over(calc_sentence, quantified_models=None)

    assert _GOLD_DISPLAY not in result.verified_text, (
        "without the registry the derived number MUST NOT reach the body (fail-closed). "
        f"verified_text={result.verified_text!r}"
    )
    assert result.sentences_verified == 0
