"""I-wire-003 B4 (#1317): quantified_analysis fires on a representative basket + the
silent-no-op canary trips on a forced no-op.

Context — the no-op the B4 canary caught on the I-wire-002 VM replay preflight: the prod
``_q_spec_provider`` closure (scripts/run_honest_sweep_r3.py) called the GLM-5.2 generator with
``max_tokens=4000``. GLM-5.2 is an _ALWAYS_REASON model that routes a ~17K-char reasoning
prelude into reasoning_content before any output; at the GLM 4096 floor the whole budget is
consumed by reasoning, content comes back empty, the reasoning stream itself truncates before
the JSON spec closes, the ``{.*}`` recovery finds no complete object ->
SpecProviderTransportError -> spec_provider_error -> spec_produced=False -> fired=False. The fix
raises the closure budget (PG_QUANTIFIED_SPEC_MAX_TOKENS, default 32768) so the reasoning-first
generator can finish BOTH its prelude AND emit the closing-brace JSON spec.

SPEND-FREE: no live LLM. ``run_quantified_section`` takes an injectable async ``spec_provider``
(the Writer in prod; a fake here). The deterministic render + sandbox + Regime-C verify run
unchanged. These tests prove:

  (1) FIRE   — a Writer that returns a valid ModelSpec over a representative sourced basket
               produces a NON-EMPTY verified "Quantified Trade-off" section (fired=True).
  (2) CANARY — a forced no-op (a Writer transport fault) produces fired=False with a BROKE
               typed status, which the readiness gate trips on; an explicit decline produces
               fired=False with an HONEST-EMPTY status, which the gate does NOT trip on.

Honest scope (LAW II): a fake spec_provider does NOT exercise the real GLM token budget, so it
does not by itself prove the budget fix. The budget fix's only end-to-end proof is the
I-wire-002 back-half replay on a real GLM corpus_snapshot showing spec_produced/fired=True. What
THIS suite proves deterministically: the orchestrator FIRES given a good spec, and the canary
correctly separates broke-vs-honest-empty (the durable B4 deliverable).
"""
from __future__ import annotations

import asyncio

import pytest

import scripts.run_honest_sweep_r3 as sweep
from src.polaris_graph.generator.quantified_analysis import (
    QUANTIFIED_STATUS_DECLINED_NO_SPEC,
    QUANTIFIED_STATUS_OK,
    QUANTIFIED_STATUS_PARSE_ERROR,
    run_quantified_section,
)


# ── representative basket: real-shaped evidence rows carrying sourced numbers ────────
def _representative_basket() -> dict[str, dict]:
    return {
        "ev_1": {
            "direct_quote": "The total program cost was $2.0 billion in fiscal 2024.",
            "statement": "The total program cost was $2.0 billion in fiscal 2024.",
            "source_url": "https://example.org/x", "tier": "T1",
        },
    }


def _good_spec_provider():
    """A Writer that returns a valid ModelSpec over the $2.0B sourced number — the shape the
    fixed (un-starved) GLM-5.2 call recovers from its reasoning stream in prod."""
    async def spec_provider(_q, sourced):
        dp = next(d for d in sourced if abs(float(d["value"]) - 2_000_000_000.0) < 1)
        return {
            "model_id": "tco", "title": "TCO",
            "inputs": [
                {"name": "cost", "datapoint_ref": {
                    "ev_id": dp["evidence_id"], "label": dp["label"],
                    "context": dp["context"], "value": dp["value"], "unit": dp["unit"]}},
                {"name": "years", "base": 3.0, "unit": "years",
                 "sweep": [1.0, 5.0, 1.0], "modeled": True},
            ],
            "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
                         "formula": "cost * years"}],
            "sensitivity": [{"input": "years", "output": "tco"}],
        }
    return spec_provider


# ── (1) FIRE: a good spec over a representative basket -> non-empty verified section ──
def test_b4_quantified_fires_non_empty_on_representative_basket():
    rows = _representative_basket()
    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=_good_spec_provider())
    )
    # the differentiator actually FIRED (>=1 verified quantified sentence)
    assert telem["spec_produced"] is True
    assert telem["execution_success"] is True
    assert telem["verified_sentences"] >= 1
    assert telem["firing_status"] == "fired"
    assert telem.get("quantified_status") == QUANTIFIED_STATUS_OK
    assert section is not None and "Quantified Trade-off" in section
    assert "$6,000,000,000.00" in section          # 2e9 * 3
    # normalized fired boolean is True -> the readiness canary does NOT trip on a fired run
    norm = sweep._normalize_quantified_telemetry(dict(telem))
    assert norm["fired"] is True
    assert sweep._quantified_readiness_failed(True, True, norm) is False


# ── (2) CANARY: forced transport no-op -> broke status -> readiness gate trips ────────
def test_b4_forced_transport_no_op_trips_canary():
    rows = _representative_basket()

    async def broken_provider(_q, _s):
        # Mirror the prod SpecProviderTransportError (empty/no-JSON body / truncated spec) the
        # starved GLM-5.2 call raised — a TRANSPORT fault, not a benign decline.
        raise sweep.SpecProviderTransportError("simulated empty/no-JSON GLM body")

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=broken_provider)
    )
    assert section is None
    assert telem["spec_produced"] is False
    assert telem["firing_status"] == "spec_provider_error"
    assert telem.get("quantified_status") == QUANTIFIED_STATUS_PARSE_ERROR
    norm = sweep._normalize_quantified_telemetry(dict(telem))
    assert norm["fired"] is False
    # the silent-no-op canary FAILS readiness loudly on a broke status under strict+force-on
    assert sweep._quantified_readiness_failed(True, True, norm) is True


# ── (2b) HONEST-EMPTY: an explicit decline -> ran-legitimately-empty -> gate does NOT trip ──
def test_b4_explicit_decline_is_honest_empty_not_canary():
    rows = {"ev_1": {"direct_quote": "Qualitative finding with no usable numbers here.",
                     "statement": "Qualitative finding with no usable numbers here."}}

    async def declining_provider(_q, _s):
        return None  # the Writer honestly declines to model

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=declining_provider)
    )
    assert section is None
    assert telem["spec_produced"] is False
    assert telem["firing_status"] == "no_spec_returned"
    assert telem.get("quantified_status") == QUANTIFIED_STATUS_DECLINED_NO_SPEC
    norm = sweep._normalize_quantified_telemetry(dict(telem))
    assert norm["fired"] is False
    # a RAN-AND-HONESTLY-EMPTY decline must NOT trip the readiness abort (the B4 split): the
    # run discloses it via quantified_degradation_disclosure, never aborts.
    assert sweep._quantified_readiness_failed(True, True, norm) is False


# ── parse_quantified_spec_response: the transport-vs-decline split (extracted, testable) ──
def test_b4_parse_valid_spec_returns_dict():
    # a well-formed spec JSON (even embedded in reasoning prose) is returned as the dict.
    text = 'reasoning... here is the spec {"model_id": "tco", "title": "T"} done'
    obj = sweep.parse_quantified_spec_response(text, sourced_count=3)
    assert obj == {"model_id": "tco", "title": "T"}


def test_b4_parse_explicit_decline_returns_none():
    # an EXPLICIT Writer decline (model_id none/''/None) is a benign decline -> None.
    for decline in ('{"model_id": "none"}', '{"model_id": ""}', '{"model_id": null}'):
        assert sweep.parse_quantified_spec_response(decline) is None


def test_b4_parse_no_json_raises_transport_error():
    # empty / no-JSON body (the starved-GLM symptom) -> RAISE, not a silent decline.
    with pytest.raises(sweep.SpecProviderTransportError):
        sweep.parse_quantified_spec_response("", sourced_count=111)
    with pytest.raises(sweep.SpecProviderTransportError):
        sweep.parse_quantified_spec_response("prose with no json object at all")


def test_b4_parse_malformed_json_raises_transport_error():
    # a `{...}`-shaped but unparseable body -> RAISE (JSONDecodeError -> transport error).
    with pytest.raises(sweep.SpecProviderTransportError):
        sweep.parse_quantified_spec_response('{"model_id": "tco", bad json}')


def test_b4_parse_missing_model_id_raises_not_masquerade_decline():
    # THE masquerade gap: a TRUNCATED-but-parseable dict missing model_id must RAISE (parse
    # fault), NOT be laundered as a benign decline. This is the branch the closure-only path
    # left uncovered.
    with pytest.raises(sweep.SpecProviderTransportError):
        sweep.parse_quantified_spec_response('{"title": "T", "inputs": []}')


def test_b4_parse_non_dict_json_raises_transport_error():
    # a JSON value that parses to a non-dict (list/number) is not a spec -> RAISE.
    with pytest.raises(sweep.SpecProviderTransportError):
        sweep.parse_quantified_spec_response('[1, 2, 3]')
