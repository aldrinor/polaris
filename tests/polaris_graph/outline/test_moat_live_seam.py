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


# ============================================================================================
# DETERMINISTIC EMISSION: prove the number reaches the composer on a LIVE-shaped path where the
# writer LLM does NOT (cannot) emit the unguessable [#calc:] token. This is the gap Fable flagged:
# the two tests above stub _call_section to emit the composed token, but a real writer never sees
# the spec_hash. Here the writer emits ordinary prose with NO calc token, and the number reaches
# the body ONLY via the deterministic calc_claims emission channel.
# ============================================================================================

# A writer draft a real LLM would plausibly produce for this section — it carries NO [#calc:]
# token and does NOT contain the gold number (the writer cannot know the exact derived value).
_WRITER_DRAFT_NO_TOKEN = "Overall market conditions were favorable during the reporting period."


def _run_section_emission(writer_draft: str, *, quantified_models, calc_claims):
    """Drive ``_run_section`` with ``_call_section`` stubbed to emit a TOKEN-FREE writer draft;
    the [#calc:] sentence can reach the body only through the ``calc_claims`` emission channel."""
    section = SectionPlan(
        title="Efficacy",
        focus="Operating income trajectory",
        ev_ids=["ev_2016", "ev_2015"],
    )

    async def _stub_call_section(*_a, **_k):
        return writer_draft, 0, 0, {}

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
            calc_claims=calc_claims,
        ))
    finally:
        msg._call_section = orig


def test_calc_number_RENDERS_via_emission_when_writer_omits_token():
    """LIVE-shaped proof: the writer emits token-free prose; the deterministic emission channel
    (calc_claims threaded from the outline agent) appends the verified [#calc:] sentence, and the
    registry lets strict_verify keep it — so the derived number renders."""
    registry, calc_sentence = _registry_and_calc_sentence()
    calc_claims = {"Efficacy": [calc_sentence]}

    # sanity: the writer draft genuinely lacks the token and the number.
    assert "[#calc:" not in _WRITER_DRAFT_NO_TOKEN
    assert _GOLD_DISPLAY not in _WRITER_DRAFT_NO_TOKEN

    result = _run_section_emission(
        _WRITER_DRAFT_NO_TOKEN, quantified_models=registry, calc_claims=calc_claims,
    )

    assert _GOLD_DISPLAY in result.verified_text, (
        "the derived number must render via the deterministic emission channel even though the "
        f"writer omitted the token; verified_text={result.verified_text!r} "
        f"(kept={result.sentences_verified} dropped={result.sentences_dropped})"
    )
    assert result.sentences_verified >= 1


def test_calc_number_ABSENT_when_writer_omits_token_and_NO_emission():
    """The exact same token-free writer draft WITHOUT the emission channel (calc_claims=None) —
    the pre-fix live behavior — renders ZERO computed numbers. This is the differential."""
    registry, _calc_sentence = _registry_and_calc_sentence()

    result = _run_section_emission(
        _WRITER_DRAFT_NO_TOKEN, quantified_models=registry, calc_claims=None,
    )

    assert _GOLD_DISPLAY not in result.verified_text, (
        "without the emission channel a real writer never produces the token, so the number must "
        f"NOT appear; verified_text={result.verified_text!r}"
    )


def test_emission_channel_cannot_launder_unbacked_token():
    """FAITHFULNESS: a calc sentence whose token is NOT in the registry is DROPPED even when it is
    deterministically appended — emission never widens the faithfulness surface."""
    # Registry is EMPTY (None) but we still deterministically append the calc sentence.
    _registry, calc_sentence = _registry_and_calc_sentence()
    calc_claims = {"Efficacy": [calc_sentence]}

    result = _run_section_emission(
        _WRITER_DRAFT_NO_TOKEN, quantified_models=None, calc_claims=calc_claims,
    )

    assert _GOLD_DISPLAY not in result.verified_text, (
        "an appended [#calc:] sentence with no backing model MUST be dropped (fail-closed emission); "
        f"verified_text={result.verified_text!r}"
    )


def test_FULL_CHAIN_tool_to_map_to_composer_renders_number():
    """END-TO-END: exercise the ACTUAL seam. The agent's ``verified_compute`` tool records the claim
    on the workspace; ``_build_calc_claims_map`` produces the section-keyed emission map exactly as
    the seam exports it; that MAP (not a hand-built one) is threaded into ``_run_section`` and the
    number renders. Proves there is no key-shape mismatch between seam output and composer input."""
    from src.polaris_graph.outline.outline_agent import _build_calc_claims_map
    from src.polaris_graph.outline.outline_toolkit import _tool_verified_compute

    class _Plan:
        def __init__(self, title, ev_ids):
            self.title = title
            self.ev_ids = ev_ids

    ws = OutlineWorkspace(research_question=_QUESTION, ev_store=dict(_EV))
    ws.outline_draft = [_Plan("Efficacy", ["ev_2016", "ev_2015"])]

    r = asyncio.run(_tool_verified_compute(
        ws, question=_QUESTION, datapoints=_DATAPOINTS, spec=_RAW_SPEC,
        lead="Adobe's operating income rose by", section="Efficacy",
    ))
    assert r.success

    # The map the SEAM would export (auto-homing + dedup), not a hand-built dict.
    calc_claims = _build_calc_claims_map(ws)
    assert calc_claims.get("Efficacy"), f"seam map must carry the Efficacy claim: {calc_claims!r}"

    result = _run_section_emission(
        _WRITER_DRAFT_NO_TOKEN, quantified_models=dict(ws.quantified_models),
        calc_claims=calc_claims,
    )
    assert _GOLD_DISPLAY in result.verified_text, (
        "the seam-produced emission map must render the number in the composer section body; "
        f"verified_text={result.verified_text!r}"
    )


def test_calc_claims_duplicate_section_title_uniqueness_guard():
    """Duplicate-section-title uniqueness guard in ``_build_calc_claims_map``: two draft plans carry
    the SAME title with SPLIT ev_ids. A claim whose evidence is spread across BOTH halves must home
    to that title — not to a competing section that overlaps more of EITHER half alone. The union
    fold makes the shared title win on its full evidence set (deterministic first-max)."""
    from types import SimpleNamespace
    from src.polaris_graph.outline.outline_agent import _build_calc_claims_map

    ws = SimpleNamespace(
        outline_draft=[
            {"title": "Efficacy", "ev_ids": ["ev_a"]},   # duplicate title, first half of its evidence
            {"title": "Efficacy", "ev_ids": ["ev_b"]},   # duplicate title, second half
            {"title": "Costs", "ev_ids": ["ev_a", "ev_b", "ev_c"]},  # competitor that overlaps each half
        ],
        computed_claims=[
            {"sentence": "The lift was 12%.", "calc_token": "#calc:tok1",
             "section": "", "input_ev_ids": ["ev_a", "ev_b"]},
        ],
    )
    out = _build_calc_claims_map(ws)
    # Split across two "Efficacy" plans, the OLD list keying under-counted each half (overlap 1)
    # and mis-homed to "Costs" (overlap 2). The union guard homes to "Efficacy" on its full set.
    assert out.get("Efficacy") == ["The lift was 12%."]
    assert "Costs" not in out
