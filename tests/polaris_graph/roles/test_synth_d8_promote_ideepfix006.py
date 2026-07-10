"""I-deepfix-006-compose C3 — offline tests for the entailment D8-promote routing.

Two layers:
  1. the analyst D3-analog promote hook ``promote_synthesis_entailment_finding`` (entailed => promoted,
     non-entailed / number-mismatched => NOT promoted) — deterministic injected ``entails_fn``;
  2. the ``native_gate_b_inputs`` routing: under PG_SYNTH_D8_PROMOTE, a C1 entailment-RESCUED finding
     (``is_synth_entailment``) is routed into the D8 4-role input set as a DS-* claim EVEN WHEN the
     legacy PG_DEPTH_SYNTHESIS_D8_GATE is off; a non-entailment finding is NOT; both OFF => byte-identical.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.polaris_graph.generator.analyst_synthesis_deviation_check import (
    promote_synthesis_entailment_finding,
)
from src.polaris_graph.roles.native_gate_b_inputs import build_native_gate_b_inputs
from src.polaris_graph.roles.release_policy import D8PolicyConfig

_FIXTURE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "native_gate_b_scope_template.json"
)
_FIXTURE_SLUG = "fixture_slug"

_SPAN = "Mortality fell by 25% across the pooled multinational cohorts."
_PARAPHRASE_OK = f"Deaths dropped 25% in the combined groups [#ev:ev_doi:0-{len(_SPAN)}]."
_PARAPHRASE_BAD_NUM = f"Deaths dropped 30% in the combined groups [#ev:ev_doi:0-{len(_SPAN)}]."


def _entails_true(_p, _h):
    return True


def _entails_false(_p, _h):
    return False


# ── layer 1: the analyst D3-analog promote hook (offline) ────────────────────────────────────────────
def test_promote_hook_entailed_is_promoted():
    rows = [{"direct_quote": _SPAN}]
    assert promote_synthesis_entailment_finding(_PARAPHRASE_OK, rows, entails_fn=_entails_true) is True


def test_promote_hook_non_entailed_not_promoted():
    rows = [{"direct_quote": _SPAN}]
    assert promote_synthesis_entailment_finding(_PARAPHRASE_OK, rows, entails_fn=_entails_false) is False


def test_promote_hook_mismatched_number_not_promoted():
    rows = [{"direct_quote": _SPAN}]
    assert promote_synthesis_entailment_finding(_PARAPHRASE_BAD_NUM, rows, entails_fn=_entails_true) is False


# ── layer 2: native_gate_b routing under PG_SYNTH_D8_PROMOTE ──────────────────────────────────────────
@dataclass
class FakeToken:
    evidence_id: str


@dataclass
class FakeSentence:
    sentence: str
    tokens: list
    is_verified: bool = True


@dataclass
class FakeSection:
    title: str
    kept_sentences_pre_resolve: list = field(default_factory=list)
    is_gap_stub: bool = False


@dataclass
class FakeMulti:
    sections: list
    synthesized_findings: list = field(default_factory=list)


def _model_slugs() -> dict:
    return {"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"}


def _d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=["contraindications", "dosing_limits", "black_box_warnings"],
    )


def _evidence_lookup() -> dict:
    return {
        "ev_doi": {"doi": "10.1056/NEJMoa2107519", "text": _SPAN, "direct_quote": _SPAN},
        "ev_sec": {"url": "https://example.org/s", "text": "section body evidence"},
    }


def _base_section() -> FakeSection:
    return FakeSection(
        title="Efficacy",
        kept_sentences_pre_resolve=[FakeSentence("The trial showed an effect", [FakeToken("ev_sec")])],
    )


def _entailment_finding() -> dict:
    return {
        "sentence": f"Deaths dropped 25% in the combined groups [5]",
        "tier": "single_source",
        "label": "(single source)",
        "audit_sentence": _PARAPHRASE_OK,
        "tokens": [FakeToken("ev_doi")],
        "is_synth_entailment": True,
    }


def _plain_finding() -> dict:
    return {
        "sentence": "The verbatim finding [5]",
        "tier": "cross_source",
        "label": "",
        "audit_sentence": f"Mortality fell by 25% [#ev:ev_doi:0-{len(_SPAN)}]",
        "tokens": [FakeToken("ev_doi")],
        # NOT entailment-rescued (no is_synth_entailment marker)
    }


def _build(multi: FakeMulti):
    return build_native_gate_b_inputs(
        multi=multi,
        template=json.loads(_FIXTURE_TEMPLATE_PATH.read_text(encoding="utf-8")),
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup=_evidence_lookup(),
        model_slugs=_model_slugs(),
        d8_config=_d8_config(),
    )


def _ds_claim_ids(bundle) -> list[str]:
    return [c.claim_id for c in bundle.inputs.claims if c.claim_id.startswith("DS-")]


def test_entailment_finding_routed_when_legacy_off_promote_on(monkeypatch):
    # Legacy D8 gate OFF, promote ON: the entailment-rescued finding IS routed into D8 (DS-* claim built),
    # while the plain (non-entailment) finding is NOT routed.
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_D8_GATE", "0")
    monkeypatch.setenv("PG_SYNTH_D8_PROMOTE", "1")
    # deterministic offline entailment for the promote-only confirmation hook
    monkeypatch.setattr(
        "src.polaris_graph.synthesis.consolidation_nli.entails_directional",
        lambda _p, _h, **_k: True,
    )
    multi = FakeMulti(
        sections=[_base_section()],
        synthesized_findings=[_entailment_finding(), _plain_finding()],
    )
    ds = _ds_claim_ids(_build(multi))
    assert len(ds) == 1, ds  # ONLY the entailment finding routed


def test_non_entailment_finding_dropped_by_promote_hook(monkeypatch):
    # Legacy OFF, promote ON, but the entailment confirmation hook returns a definitive non-entailment
    # => the finding is NOT promoted (no DS-* claim).
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_D8_GATE", "0")
    monkeypatch.setenv("PG_SYNTH_D8_PROMOTE", "1")
    monkeypatch.setattr(
        "src.polaris_graph.synthesis.consolidation_nli.entails_directional",
        lambda _p, _h, **_k: False,
    )
    multi = FakeMulti(sections=[_base_section()], synthesized_findings=[_entailment_finding()])
    assert _ds_claim_ids(_build(multi)) == []


def test_promote_off_is_byte_identical_to_legacy(monkeypatch):
    # Legacy OFF + promote OFF => no DS-* claims (byte-identical to the pre-C3 legacy-off path).
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_D8_GATE", "0")
    monkeypatch.setenv("PG_SYNTH_D8_PROMOTE", "0")
    multi = FakeMulti(
        sections=[_base_section()],
        synthesized_findings=[_entailment_finding(), _plain_finding()],
    )
    assert _ds_claim_ids(_build(multi)) == []


def test_legacy_on_routes_all_unchanged(monkeypatch):
    # Legacy gate ON (default): ALL findings route (existing behavior), promote flag makes no difference.
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_D8_GATE", "1")
    monkeypatch.setenv("PG_SYNTH_D8_PROMOTE", "1")
    multi = FakeMulti(
        sections=[_base_section()],
        synthesized_findings=[_entailment_finding(), _plain_finding()],
    )
    assert len(_ds_claim_ids(_build(multi))) == 2
