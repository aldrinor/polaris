"""S0 calc-lane battery cases — the moat: COMPUTE-and-PROVE a number, faithfully.

Every case here exercises the REAL machinery (build_quantified_spec -> execute_quantified_model ->
strict_verify), no mocks. They are the deterministic core of metric (a)+(c): a derived number must
render ONLY through the verified ``[#calc:]`` lane, never through ``[#ev:]``/``[CITE:]``, and must
ship through the DOWNSTREAM production strict_verify handoff.

Fixture: the Adobe FY2015->FY2016 operating-income case (FinanceBench H01). The evidence spans
carry the actual 10-K literals; the span is DERIVED by the tool, not asserted here.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile

from tests.battery.harness import Assertion, BatteryCase

_EV = {
    "ev_2016": {
        "evidence_id": "ev_2016", "source_url": "http://a", "tier": "T1",
        "statement": "operating income fiscal 2016",
        "direct_quote": "Adobe reported operating income of 1,493,602 for fiscal 2016.",
    },
    "ev_2015": {
        "evidence_id": "ev_2015", "source_url": "http://b", "tier": "T1",
        "statement": "operating income fiscal 2015",
        "direct_quote": "Adobe reported operating income of 903,095 for fiscal 2015.",
    },
    # A third, unrelated literal used by the wrong-pair semantic case.
    "ev_rev": {
        "evidence_id": "ev_rev", "source_url": "http://c", "tier": "T1",
        "statement": "revenue fiscal 2016",
        "direct_quote": "Adobe reported revenue of 5,854,858 for fiscal 2016.",
    },
}
_QUESTION = "What was Adobe's operating income change from FY2015 to FY2016?"
_GOLD = "$590,507,000.00"


def _dp(ev_id, label, ctx, value):
    return {"evidence_id": ev_id, "label": label, "context": ctx, "value": value, "unit": "kUSD"}


def _spec(model_id, out_name, formula, inputs):
    return {
        "model_id": model_id, "title": "Adobe operating income change",
        "inputs": [{"name": n, "datapoint_ref": {
            "ev_id": e, "label": n, "context": c, "value": v, "unit": "kUSD"}}
            for (n, e, c, v) in inputs],
        "outputs": [{"name": out_name, "formula": formula, "unit": "USD",
                     "display_kind": "currency"}],
    }


def _workspace():
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace
    return OutlineWorkspace(research_question=_QUESTION, ev_store=dict(_EV))


async def _compute(ws, datapoints, spec):
    from src.polaris_graph.outline.verified_compute import run_verified_compute
    return await run_verified_compute(ws, question=_QUESTION, datapoints=datapoints, raw_spec=spec)


# ── H01a: the derived number renders through the [#calc:] lane ────────────────
async def _case_calc_render() -> list[Assertion]:
    from src.polaris_graph.generator.provenance_generator import strict_verify

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    out: list[Assertion] = []
    out.append(Assertion(
        "spec_built_and_executed", claim is not None, "ComputedClaim",
        type(claim).__name__, severity="S0"))
    if claim is None:
        return out
    out.append(Assertion(
        "gold_display_value", claim.display_value == _GOLD, _GOLD, claim.display_value,
        severity="S1"))
    out.append(Assertion(
        "model_registered", (claim.model_id, claim.spec_hash) in ws.quantified_models,
        True, (claim.model_id, claim.spec_hash) in ws.quantified_models, severity="S0"))

    sentence = claim.render_sentence("Adobe operating income rose by")
    rep = strict_verify(sentence, ws.ev_store, quantified_models=ws.quantified_models)
    out.append(Assertion(
        "calc_lane_kept1_dropped0", rep.total_kept == 1 and rep.total_dropped == 0,
        "kept=1 dropped=0", f"kept={rep.total_kept} dropped={rep.total_dropped}", severity="S0"))
    if rep.kept_sentences:
        cited = {t.evidence_id for t in rep.kept_sentences[0].tokens}
        out.append(Assertion(
            "computed_number_traces_to_both_inputs", cited == {"ev_2016", "ev_2015"},
            {"ev_2016", "ev_2015"}, cited, severity="S0"))
    return out


# ── H01b DROP GUARD: the same derived number via [#ev:] MUST be dropped ───────
async def _case_calc_dropguard() -> list[Assertion]:
    from src.polaris_graph.generator.provenance_generator import strict_verify

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    if claim is None:
        return [Assertion("precondition_compute", False, "claim", None, severity="S0")]
    span_len = len(_EV["ev_2016"]["direct_quote"])
    bad = f"Adobe operating income rose by {claim.display_value} [#ev:ev_2016:0-{span_len}]."
    rep = strict_verify(bad, ws.ev_store, quantified_models=ws.quantified_models)
    reasons = rep.dropped_sentences[0].failure_reasons if rep.dropped_sentences else []
    return [
        Assertion("derived_number_via_CITE_is_dropped",
                  rep.total_kept == 0 and rep.total_dropped == 1,
                  "kept=0 dropped=1", f"kept={rep.total_kept} dropped={rep.total_dropped}",
                  severity="S0"),
        Assertion("drop_reason_is_number_not_in_span",
                  any("number_not_in_any_cited_span" in r for r in reasons),
                  "number_not_in_any_cited_span", reasons, severity="S0"),
    ]


# ── H01c: a WRONG number adjacent to a real calc token MUST be dropped ────────
async def _case_calc_wrong_number_adjacency() -> list[Assertion]:
    from src.polaris_graph.generator.provenance_generator import strict_verify

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    if claim is None:
        return [Assertion("precondition_compute", False, "claim", None, severity="S0")]
    wrong = f"Adobe operating income rose by $999,999,999.00 {claim.calc_token}."
    rep = strict_verify(wrong, ws.ev_store, quantified_models=ws.quantified_models)
    reasons = rep.dropped_sentences[0].failure_reasons if rep.dropped_sentences else []
    return [
        Assertion("wrong_number_next_to_calc_token_dropped",
                  rep.total_kept == 0 and rep.total_dropped == 1,
                  "kept=0 dropped=1", f"kept={rep.total_kept} dropped={rep.total_dropped}",
                  severity="S0"),
        Assertion("drop_reason_is_calc_number_mismatch",
                  any("calc_number_mismatch" in r for r in reasons),
                  "calc_number_mismatch", reasons, severity="S0"),
    ]


# ── H01d WRONG-PAIR SEMANTIC: a semantically-wrong subtraction is still FAITHFUL ─
async def _case_wrong_pair_subtraction() -> list[Assertion]:
    """The agent subtracts the WRONG pair (opinc_2016 - revenue_2016) — a number that answers a
    different question than asked. This probes whether the fail-closed gate can be TRICKED into an
    UNFAITHFUL number, and whether the deferred mirror-model question<->formula entailment check
    would need to fire.

    Measured invariant: the wrong-pair result is arithmetically consistent over its two REAL cited
    spans, so it is FAITHFUL (it traces to exactly the inputs it used) — NOT an S0 breach. And the
    SAME wrong number still cannot launder through the [#ev:] span path. Therefore the hard gate is
    a FAITHFULNESS gate, not a semantic-correctness gate; a fail-OPEN LLM mirror check could not
    strengthen it (it can only add a soft advisory). This CONFIRMS Fable's defer decision: the
    mirror-check 'mode' does not fire as a faithfulness protection here.
    """
    from src.polaris_graph.generator.provenance_generator import strict_verify

    ws = _workspace()
    # Wrong pair: operating income 2016 minus REVENUE 2016 (nonsense as a YoY opinc change).
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_rev", "rev16", "fiscal 2016 revenue", "5854858")],
        _spec("wrong_pair_delta", "delta", "(o16 - rev16) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("rev16", "ev_rev", "fiscal 2016 revenue", "5854858")]),
    )
    out: list[Assertion] = []
    out.append(Assertion("wrong_pair_computes", claim is not None,
                         "ComputedClaim", type(claim).__name__, severity="S1"))
    if claim is None:
        return out
    # It is NOT the gold answer — a wrong pairing gives a different (negative) number.
    out.append(Assertion("wrong_pair_is_not_gold", claim.display_value != _GOLD,
                         f"!= {_GOLD}", claim.display_value, severity="S2"))

    sentence = claim.render_sentence("The (wrongly paired) figure is")
    rep = strict_verify(sentence, ws.ev_store, quantified_models=ws.quantified_models)
    # FAITHFULNESS invariant: the rendered number traces to exactly the two spans it was computed
    # from — no unfaithful number is blessed. (Kept because it is faithful to its inputs.)
    out.append(Assertion("wrong_pair_number_is_faithful_to_its_inputs",
                         rep.total_kept == 1 and rep.total_dropped == 0,
                         "kept=1 (faithful to cited inputs)",
                         f"kept={rep.total_kept} dropped={rep.total_dropped}", severity="S0"))
    if rep.kept_sentences:
        cited = {t.evidence_id for t in rep.kept_sentences[0].tokens}
        out.append(Assertion("wrong_pair_traces_to_the_inputs_it_used",
                             cited == {"ev_2016", "ev_rev"}, {"ev_2016", "ev_rev"}, cited,
                             severity="S0"))
    # And the same wrong number STILL cannot launder through a [#ev:] citation.
    span_len = len(_EV["ev_2016"]["direct_quote"])
    bad = f"The figure is {claim.display_value} [#ev:ev_2016:0-{span_len}]."
    rep2 = strict_verify(bad, ws.ev_store, quantified_models=ws.quantified_models)
    out.append(Assertion("wrong_pair_cannot_launder_via_CITE",
                         rep2.total_kept == 0 and rep2.total_dropped == 1,
                         "kept=0 dropped=1", f"kept={rep2.total_kept} dropped={rep2.total_dropped}",
                         severity="S0"))
    return out


# ── H01e PRODUCTION HANDOFF: the calc number ships through run_honest_pipeline ─
@contextlib.contextmanager
def _scoped_env(**kv):
    """Set env vars for the duration of the block, restoring exactly (parent env is never left
    mutated). Safe because battery compute cases run sequentially (no concurrent env readers)."""
    saved = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


async def _case_production_handoff() -> list[Assertion]:
    """Drive an outline-emitted [#calc:] sentence + the quantified_models registry through the
    REAL run_honest_pipeline downstream strict_verify handoff (honest_pipeline.py:336). Proves the
    moat number SHIPS in production, not just in the probe.

    Guard: run WITHOUT the registry (legacy prod default) => the calc sentence is DROPPED and the
    number is absent from the report; WITH the registry => kept and present. Both directions asserted
    so a regression that drops the plumbing is caught.
    """
    from src.polaris_graph.honest_pipeline import run_honest_pipeline

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    if claim is None:
        return [Assertion("precondition_compute", False, "claim", None, severity="S0")]
    sentence = claim.render_sentence("Adobe operating income rose by")
    srcs = [{"url": "http://a", "title": "10-K 2016", "domain": "due_diligence"},
            {"url": "http://b", "title": "10-K 2015", "domain": "due_diligence"}]
    evl = [dict(_EV["ev_2016"]), dict(_EV["ev_2015"])]

    def _run(qm):
        d = tempfile.mkdtemp(prefix="battery_h01e_")
        return run_honest_pipeline(
            research_question=_QUESTION, domain="due_diligence", run_id="battery_h01e",
            run_dir=d, retrieved_sources=srcs, evidence=evl, draft_text=sentence,
            quantified_models=qm,
        )

    # The two env seats are unrelated to the moat: they only let the offline pipeline reach the
    # strict_verify phase (corpus auto-approval) and past the two-family live-evaluator gate (which
    # never calls an LLM here — enable_llm_judge=False). Both are read at RUNTIME (os.getenv), so a
    # scoped set/restore takes effect; the faithfulness engine under test is untouched.
    with _scoped_env(PG_AUTHORIZED_SWEEP_APPROVAL="1",
                     PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY="1"):
        r_no = await asyncio.to_thread(_run, None)
        r_yes = await asyncio.to_thread(_run, ws.quantified_models)

    return [
        Assertion("legacy_no_registry_drops_calc_sentence",
                  r_no.sentences_verified == 0 and _GOLD not in r_no.final_report_text,
                  "verified=0, number absent",
                  f"verified={r_no.sentences_verified} in_report={_GOLD in r_no.final_report_text}",
                  severity="S1",
                  detail="proves the plumbing is load-bearing (without it the moat number is lost)"),
        Assertion("with_registry_calc_number_ships_in_report",
                  r_yes.sentences_verified == 1 and _GOLD in r_yes.final_report_text,
                  "verified=1, number present in final_report_text",
                  f"verified={r_yes.sentences_verified} in_report={_GOLD in r_yes.final_report_text}",
                  severity="S0"),
    ]


# ── H01f COMPOSER HANDOFF: the calc number ships through the FULL-CORPUS composer ─
async def _case_composer_handoff() -> list[Assertion]:
    """Drive the outline-emitted [#calc:] sentence + the quantified_models registry through the
    REAL full-corpus composer ``_run_section`` (the path ``generate_multi_section_report`` uses in
    the cp4_used=agentic 346-basket run — NOT run_honest_pipeline). Proves the moat number renders
    in the SECTION BODY on the pipeline that actually composes section bodies in the corpus run.

    Guard: WITHOUT the registry (legacy prod default) => the calc sentence is DROPPED (section
    renders its gap stub, number absent); WITH the registry => kept and present in verified_text.
    Only ``_call_section`` (the LLM writer) is stubbed to emit the composed draft — the rewrite
    tail, strict_verify, and citation resolution are all REAL.
    """
    import src.polaris_graph.generator.multi_section_generator as _msg
    from src.polaris_graph.generator.multi_section_generator import SectionPlan, _run_section

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    if claim is None:
        return [Assertion("precondition_compute", False, "claim", None, severity="S0")]
    sentence = claim.render_sentence("Adobe operating income rose by")

    async def _stub_call_section(*_a, **_k):
        return sentence, 0, 0, {}

    async def _run(qm):
        section = SectionPlan(title="Efficacy", focus="Operating income trajectory",
                              ev_ids=["ev_2016", "ev_2015"])
        orig = _msg._call_section
        _msg._call_section = _stub_call_section
        try:
            return await _run_section(
                section, dict(_EV), model="stub-model", temperature=0.0,
                max_tokens_per_section=512, min_kept_fraction=0.0, quantified_models=qm)
        finally:
            _msg._call_section = orig

    r_no = await _run(None)
    r_yes = await _run(ws.quantified_models)
    return [
        Assertion("legacy_no_registry_drops_calc_body_sentence",
                  r_no.sentences_verified == 0 and _GOLD not in r_no.verified_text,
                  "verified=0, number absent from body",
                  f"verified={r_no.sentences_verified} in_body={_GOLD in r_no.verified_text}",
                  severity="S1",
                  detail="proves the composer seam is load-bearing (without it the moat is dropped)"),
        Assertion("with_registry_calc_number_renders_in_section_body",
                  r_yes.sentences_verified >= 1 and _GOLD in r_yes.verified_text,
                  "verified>=1, number present in section verified_text",
                  f"verified={r_yes.sentences_verified} in_body={_GOLD in r_yes.verified_text}",
                  severity="S0"),
    ]


# ── H01g EMISSION CHANNEL: number reaches the composer when the WRITER omits the token ─
async def _case_emission_channel() -> list[Assertion]:
    """LIVE-shaped proof of the deterministic EMISSION channel. In a real corpus run the writer LLM
    NEVER emits the ``[#calc:model:hash:field]`` token (the spec_hash is unguessable), so the moat
    number can reach the section body ONLY if the composer appends the agent's render-ready sentence
    DETERMINISTICALLY. Here ``_call_section`` returns token-free prose (as a real writer would); the
    number reaches ``verified_text`` only through the ``calc_claims`` emission channel.

    Three directions asserted:
      (A) writer-omits-token + emission ON  => number RENDERS (via verified_compute + registry);
      (D) writer-omits-token + emission OFF => number ABSENT (the pre-fix live behavior);
      (F) FAITHFULNESS: emission ON but NO backing registry => appended sentence is DROPPED
          (emission never widens the faithfulness surface — an unbacked token cannot render).
    """
    import src.polaris_graph.generator.multi_section_generator as _msg
    from src.polaris_graph.generator.multi_section_generator import SectionPlan, _run_section

    ws = _workspace()
    claim = await _compute(
        ws,
        [_dp("ev_2016", "o16", "fiscal 2016", "1493602"),
         _dp("ev_2015", "o15", "fiscal 2015", "903095")],
        _spec("opinc_delta", "delta", "(o16 - o15) * 1000",
              [("o16", "ev_2016", "fiscal 2016", "1493602"),
               ("o15", "ev_2015", "fiscal 2015", "903095")]),
    )
    if claim is None:
        return [Assertion("precondition_compute", False, "claim", None, severity="S0")]
    calc_sentence = claim.render_sentence("Adobe operating income rose by")
    calc_claims = {"Efficacy": [calc_sentence]}
    # A token-free writer draft (a real LLM would produce this; it cannot know the exact number).
    writer_draft = "Overall market conditions were favorable during the reporting period."
    assert "[#calc:" not in writer_draft and _GOLD not in writer_draft

    async def _stub_call_section(*_a, **_k):
        return writer_draft, 0, 0, {}

    async def _run(qm, cc):
        section = SectionPlan(title="Efficacy", focus="Operating income trajectory",
                              ev_ids=["ev_2016", "ev_2015"])
        orig = _msg._call_section
        _msg._call_section = _stub_call_section
        try:
            return await _run_section(
                section, dict(_EV), model="stub-model", temperature=0.0,
                max_tokens_per_section=512, min_kept_fraction=0.0,
                quantified_models=qm, calc_claims=cc)
        finally:
            _msg._call_section = orig

    r_on = await _run(ws.quantified_models, calc_claims)      # (A)
    r_off = await _run(ws.quantified_models, None)            # (D)
    r_unbacked = await _run(None, calc_claims)                # (F)
    return [
        Assertion("emission_ON_renders_number_when_writer_omits_token",
                  r_on.sentences_verified >= 1 and _GOLD in r_on.verified_text,
                  "verified>=1, number present via emission channel",
                  f"verified={r_on.sentences_verified} in_body={_GOLD in r_on.verified_text}",
                  severity="S0",
                  detail="the LIVE gap Fable flagged: writer never emits the hash; emission closes it"),
        Assertion("emission_OFF_number_absent_prefix_live_behavior",
                  _GOLD not in r_off.verified_text,
                  "number absent (pre-fix live behavior)",
                  f"in_body={_GOLD in r_off.verified_text}", severity="S1"),
        Assertion("emission_cannot_launder_unbacked_token",
                  _GOLD not in r_unbacked.verified_text,
                  "unbacked appended token DROPPED (fail-closed emission)",
                  f"in_body={_GOLD in r_unbacked.verified_text}", severity="S0",
                  detail="faithfulness: deterministic append never bypasses strict_verify"),
    ]


BATTERY_CASES = [
    BatteryCase("h01a_calc_render", "finance", "verified_compute+calc_lane", _case_calc_render),
    BatteryCase("h01b_calc_dropguard", "finance", "faithfulness_drop_guard", _case_calc_dropguard),
    BatteryCase("h01c_wrong_number_adjacency", "finance", "regime_c_adjacency",
                _case_calc_wrong_number_adjacency),
    BatteryCase("h01d_wrong_pair_subtraction", "finance", "semantic_faithfulness_probe",
                _case_wrong_pair_subtraction,
                note="probes whether the deferred mirror-model check is needed (it is not)"),
    BatteryCase("h01e_production_handoff", "finance", "downstream_strict_verify_handoff",
                _case_production_handoff),
    BatteryCase("h01f_composer_handoff", "finance", "full_corpus_composer_handoff",
                _case_composer_handoff,
                note="drives _run_section (generate_multi_section_report path), not honest_pipeline"),
    BatteryCase("h01g_emission_channel", "finance", "deterministic_calc_emission",
                _case_emission_channel,
                note="LIVE-shaped: writer omits the token; emission channel appends it (Fable's gap)"),
]
