"""I-perm-020 (#1212) S0 coverage binder — credit a VERIFIED contraindication to s0_categories.

The D8/S0 safety-floor was the measured drb_76 TOP blocker: a VERIFIED contraindication claim ("not
recommended"/"should be avoided" for an immunocompromised population, citing the exact CDC source)
carried ``s0_categories=[]`` because its text never used the literal token "contraindicated", so D8
coverage stayed below threshold and the run safety-floored as
``released_insufficient_safety_evidence`` despite a faithful safety claim.

``coverage_binder.bind_s0_coverage`` credits the required ``contraindications`` category to such an
ALREADY-VERIFIED claim AFTER verification, behind the default-OFF ``PG_S0_COVERAGE_BINDER`` flag. It
reuses the WHOLE I-perm-002 conjunction (canonical evidence match + literal population anchor +
contraindication DIRECTION + negation guard, semantic recognition forced ON), so it credits the
faithful warning while a negated/inverted/wrong-population/uncited claim earns NOTHING.

Direction of error (binding, §-1.1): over-crediting a contraindication is LETHAL; under-crediting is
a SAFE disclosed gap. Every refusal assertion below proves over-credit is impossible.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.polaris_graph.roles import coverage_binder as cb
from src.polaris_graph.roles import native_gate_b_inputs as ng
from src.polaris_graph.roles.native_gate_b_inputs import build_native_gate_b_inputs
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    D8PolicyConfig,
    apply_d8_release_policy,
)

_BINDER_FLAG = "PG_S0_COVERAGE_BINDER"
_SEMANTIC_FLAG = "PG_SWEEP_SEMANTIC_CONTRAINDICATION"

# The real drb_76 S0 entity (config/scope_templates/clinical.yaml
# `probiotic_immunocompromised_contraindication`): canonical identity is the CDC EID url, the literal
# concept token + the literal population anchor, severity S0, category contraindications.
_CDC_URL = "https://wwwnc.cdc.gov/eid/article/27/8/21-0018_article"
_ENTITY = {
    ng._KEY_ENTITY_ID: "probiotic_immunocompromised_contraindication",
    "severity": "S0",
    "s0_category": "contraindications",
    "url_pattern": _CDC_URL,
    ng._KEY_ENTITY_CONTENT_REQS: ["contraindicated", "immunocompromised"],
}
# The validated-entity tuple the binder consumes: (entity, severity, s0_category).
_VALIDATED = [(_ENTITY, "S0", "contraindications")]
# A record whose canonical url EXACTLY matches the entity (the claim cited the CDC source).
_CITING_RECORD = {"text": "probiotic use should be avoided ...", "url": _CDC_URL}
# A record citing a DIFFERENT source (canonical match must fail).
_OTHER_RECORD = {"text": "unrelated fiber meta-analysis", "url": "https://example.org/other"}

# The REAL drb_76 claim 03-001 text — VERIFIED, a genuine warning lacking the literal token.
_REAL_WARNING = (
    "On the basis of these data, the authors explicitly advise that probiotics are not "
    "recommended for patients who are immunocompromised, critically ill, or have indwelling "
    "catheters."
)


@pytest.fixture(autouse=True)
def _clear_flags():
    for flag in (_BINDER_FLAG, _SEMANTIC_FLAG):
        os.environ.pop(flag, None)
    yield
    for flag in (_BINDER_FLAG, _SEMANTIC_FLAG):
        os.environ.pop(flag, None)


# --- the flag reader: default OFF, explicit-truthy ON ----------------------------------------


def test_flag_default_off():
    os.environ.pop(_BINDER_FLAG, None)
    assert cb.s0_coverage_binder_enabled() is False
    assert ng._s0_coverage_binder_enabled() is False


@pytest.mark.parametrize("falsey", ["", "0", "false", "no", "off", "garbage", "  "])
def test_flag_off_for_non_truthy(falsey):
    os.environ[_BINDER_FLAG] = falsey
    assert cb.s0_coverage_binder_enabled() is False
    # The native-seam reader and the binder reader agree on every value (one flag, two readers).
    assert ng._s0_coverage_binder_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_flag_on_for_truthy(truthy):
    os.environ[_BINDER_FLAG] = truthy
    assert cb.s0_coverage_binder_enabled() is True
    assert ng._s0_coverage_binder_enabled() is True


# --- ON: the faithful drb_76 warning credits the contraindications category ------------------


@pytest.mark.parametrize(
    "claim",
    [
        _REAL_WARNING,  # the real drb_76 warning
        "live probiotics should be avoided in immunocompromised hosts",
        "this product should not be used in immunocompromised patients",
        "probiotics are contraindicated in immunocompromised patients",  # literal still credits
    ],
)
def test_credits_faithful_contraindication(claim):
    categories, element_ids = cb.bind_s0_coverage(
        claim_text=claim,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=_VALIDATED,
    )
    assert categories == {"contraindications"}
    assert element_ids == {"probiotic_immunocompromised_contraindication"}


def test_binder_forces_semantic_independent_of_semantic_flag():
    """The binder credits the faithful warning even when PG_SWEEP_SEMANTIC_CONTRAINDICATION is OFF —
    it forces semantic recognition ON internally (semantic=True), not via the global flag."""
    os.environ.pop(_SEMANTIC_FLAG, None)  # semantic global OFF
    categories, _ = cb.bind_s0_coverage(
        claim_text=_REAL_WARNING,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=_VALIDATED,
    )
    assert categories == {"contraindications"}
    # And it does NOT leak the global flag on (it never writes the environment).
    assert _SEMANTIC_FLAG not in os.environ


# --- ON: over-credit is impossible (the lethal direction) ------------------------------------


def test_refuses_when_canonical_evidence_not_cited():
    """A faithful warning that does NOT cite the entity's canonical source earns NO credit."""
    categories, element_ids = cb.bind_s0_coverage(
        claim_text=_REAL_WARNING,
        claim_evidence_records=[_OTHER_RECORD],
        validated_entities=_VALIDATED,
    )
    assert categories == set()
    assert element_ids == set()


@pytest.mark.parametrize(
    "claim",
    [
        # Negated / inverted — MUST refuse (the §-1.1-lethal case).
        "probiotics are not contraindicated in immunocompromised patients",
        "cdc reports no known contraindications to probiotics in immunocompromised patients",
        "probiotics are safe in immunocompromised patients",
        "probiotics are well tolerated in immunocompromised patients",
        "probiotics should not be avoided in immunocompromised patients",
        # contraction + curly apostrophe negation.
        "probiotics aren’t contraindicated in immunocompromised patients",
    ],
)
def test_refuses_negated_or_inverted(claim):
    categories, element_ids = cb.bind_s0_coverage(
        claim_text=claim,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=_VALIDATED,
    )
    assert categories == set()
    assert element_ids == set()


@pytest.mark.parametrize(
    "claim",
    [
        "probiotics are not recommended for pregnant women",  # wrong population
        "probiotics should be avoided in patients with short bowel syndrome",  # wrong population
        "probiotic use was strongly associated with fungemia",  # no population, no direction
    ],
)
def test_refuses_when_population_anchor_absent(claim):
    """The population token ("immunocompromised") is NEVER relaxed — a contraindication direction for
    the WRONG/absent population earns no credit."""
    categories, _ = cb.bind_s0_coverage(
        claim_text=claim,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=_VALIDATED,
    )
    assert categories == set()


def test_only_s0_entities_are_credit_eligible():
    """A non-S0 entity (severity != S0 / s0_category None) is skipped — the binder only credits S0."""
    non_s0 = [
        (dict(_ENTITY, severity="S1", s0_category=None), "S1", None),
    ]
    categories, element_ids = cb.bind_s0_coverage(
        claim_text=_REAL_WARNING,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=non_s0,
    )
    assert categories == set()
    assert element_ids == set()


def test_empty_inputs_credit_nothing():
    categories, element_ids = cb.bind_s0_coverage(
        claim_text=_REAL_WARNING,
        claim_evidence_records=[],
        validated_entities=_VALIDATED,
    )
    assert categories == set()
    assert element_ids == set()
    categories2, _ = cb.bind_s0_coverage(
        claim_text=_REAL_WARNING,
        claim_evidence_records=[_CITING_RECORD],
        validated_entities=[],
    )
    assert categories2 == set()


# --- refactor equivalence: the public matcher is byte-identical across BOTH semantic states ---


@pytest.mark.parametrize("semantic_value", [None, "0", "false", "1", "true"])
@pytest.mark.parametrize(
    "claim, expected_off, expected_on",
    [
        # genuine warning: OFF refuses (no literal token), ON credits (direction synonym).
        (_REAL_WARNING, False, True),
        # both literal tokens present: credits under both.
        ("probiotics are contraindicated in immunocompromised patients", True, True),
        # negated: OFF (bare substring) wrongly credits, ON refuses.
        ("probiotics are not contraindicated in immunocompromised patients", True, False),
    ],
)
def test_public_matcher_unchanged_by_refactor(
    semantic_value, claim, expected_off, expected_on
):
    """`_content_requirements_satisfied` still derives `semantic` from PG_SWEEP_SEMANTIC_CONTRAINDICATION
    exactly as before the I-perm-020 refactor (impl delegation did not change behavior)."""
    if semantic_value is None:
        os.environ.pop(_SEMANTIC_FLAG, None)
    else:
        os.environ[_SEMANTIC_FLAG] = semantic_value
    semantic_on = ng._semantic_contraindication_enabled()
    expected = expected_on if semantic_on else expected_off
    assert ng._content_requirements_satisfied(claim, _ENTITY) is expected
    # the impl with an EXPLICIT flag matches the public function's derived decision.
    assert (
        ng._content_requirements_satisfied_impl(claim, _ENTITY, semantic=semantic_on)
        is expected
    )


# --- seam-level: build_native_gate_b_inputs credits at the coverage-computation seam ---------
# These exercise the REAL production seam (the per-claim s0_categories / covered_element_ids
# computation in build_native_gate_b_inputs) end to end, using the same fixture scope template the
# existing builder tests use (tests/fixtures/native_gate_b_scope_template.json). The S0 entity there
# (`label_url_entity`) is `s0_category=contraindications` with content requirements
# ["contraindicated", "hypersensitivity"] and a canonical FDA-label url — a faithful drb_76-shape
# analog: a verified warning that cites the label and names the population ("hypersensitivity") with a
# contraindication DIRECTION ("should not be used") but lacks the literal "contraindicated".

_FIXTURE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "native_gate_b_scope_template.json"
)
_FIXTURE_SLUG = "fixture_slug"
_FDA_LABEL_URL = (
    "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/217806s000lbl.pdf"
)
# A faithful semantic contraindication warning: cites the label, names the population, asserts a
# contraindication DIRECTION, but never uses the literal token "contraindicated".
_SEAM_SEMANTIC_WARNING = (
    "the agent should not be used in patients with hypersensitivity per the label"
)
# The literal-token claim that credits under BOTH flag states (legacy behavior must not change).
_SEAM_LITERAL_WARNING = (
    "the agent is contraindicated in hypersensitivity per the label"
)


@dataclass
class _FakeToken:
    evidence_id: str


@dataclass
class _FakeSentence:
    sentence: str
    tokens: list
    is_verified: bool = True


@dataclass
class _FakeSection:
    title: str
    kept_sentences_pre_resolve: list = field(default_factory=list)


@dataclass
class _FakeMulti:
    sections: list


def _seam_template() -> dict:
    return json.loads(_FIXTURE_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _seam_evidence_lookup() -> dict:
    return {"ev_label": {"url": _FDA_LABEL_URL, "text": "label contraindications section"}}


def _seam_d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=["contraindications", "dosing_limits", "black_box_warnings"],
    )


def _build_seam(sentence: str):
    multi = _FakeMulti(
        sections=[
            _FakeSection(
                title="Regulatory",
                kept_sentences_pre_resolve=[_FakeSentence(sentence, [_FakeToken("ev_label")])],
            )
        ]
    )
    return build_native_gate_b_inputs(
        multi=multi,
        template=_seam_template(),
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup=_seam_evidence_lookup(),
        model_slugs={"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"},
        d8_config=_seam_d8_config(),
    )


def test_seam_off_semantic_warning_uncredited_with_semantic_global_off():
    """The concrete legacy behavior: binder OFF + semantic global OFF -> the faithful warning is NOT
    credited (the exact drb_76 false-hold input)."""
    os.environ.pop(_BINDER_FLAG, None)
    os.environ.pop(_SEMANTIC_FLAG, None)
    claim = _build_seam(_SEAM_SEMANTIC_WARNING).inputs.claims[0]
    assert claim.s0_categories == []
    assert claim.covered_element_ids == []
    assert claim.severity == "S3"


@pytest.mark.parametrize("semantic_value", [None, "0", "1"])
def test_seam_binder_off_equals_no_binder_baseline(semantic_value):
    """Flag OFF: the seam result is byte-identical to the legacy no-binder result REGARDLESS of the
    PG_SWEEP_SEMANTIC_CONTRAINDICATION state. (Both branches here have the binder OFF, so the binder
    contributes nothing — proven by the seam producing the SAME claim shape the legacy seam produced
    for every semantic-flag value.)"""
    if semantic_value is None:
        os.environ.pop(_SEMANTIC_FLAG, None)
    else:
        os.environ[_SEMANTIC_FLAG] = semantic_value
    os.environ.pop(_BINDER_FLAG, None)
    claim = _build_seam(_SEAM_SEMANTIC_WARNING).inputs.claims[0]
    # When the semantic global is ON ("1"), the EXISTING _content_requirements_satisfied path credits
    # the warning even with the binder OFF — that is legacy I-perm-002 behavior, untouched. When it is
    # OFF/absent, the warning is un-credited. The binder being OFF must reproduce exactly that.
    semantic_on = ng._semantic_contraindication_enabled()
    if semantic_on:
        assert claim.s0_categories == ["contraindications"]
    else:
        assert claim.s0_categories == []


def test_seam_on_credits_semantic_warning_with_semantic_global_off():
    """Flag ON: the binder credits the contraindications category + the label element at the seam,
    forcing semantic recognition internally — even with PG_SWEEP_SEMANTIC_CONTRAINDICATION OFF."""
    os.environ.pop(_SEMANTIC_FLAG, None)
    os.environ[_BINDER_FLAG] = "1"
    claim = _build_seam(_SEAM_SEMANTIC_WARNING).inputs.claims[0]
    assert claim.s0_categories == ["contraindications"]
    assert "label_url_entity" in claim.covered_element_ids
    assert claim.severity == "S0"


def test_seam_literal_warning_credits_under_both_flag_states():
    """A literal-token contraindication credits identically whether the binder is OFF or ON (the
    binder only ADDS the semantic path; it never removes the literal credit)."""
    os.environ.pop(_SEMANTIC_FLAG, None)
    os.environ.pop(_BINDER_FLAG, None)
    off = _build_seam(_SEAM_LITERAL_WARNING).inputs.claims[0]
    assert off.s0_categories == ["contraindications"]
    os.environ[_BINDER_FLAG] = "1"
    on = _build_seam(_SEAM_LITERAL_WARNING).inputs.claims[0]
    assert on.s0_categories == ["contraindications"]
    assert on.covered_element_ids == off.covered_element_ids


def test_seam_on_does_not_credit_uncited_or_wrong_population():
    """Flag ON: the binder still refuses when the canonical evidence is uncited (here it IS cited but
    the population anchor is absent) — over-credit stays impossible at the seam."""
    os.environ.pop(_SEMANTIC_FLAG, None)
    os.environ[_BINDER_FLAG] = "1"
    # Cites the label + a direction, but names the WRONG population (no "hypersensitivity").
    claim = _build_seam(
        "the agent should not be used in pregnant women per the label"
    ).inputs.claims[0]
    assert claim.s0_categories == []
    assert "label_url_entity" not in claim.covered_element_ids


# --- D8-layer: a binder-credited category is STILL gated by the 4-role VERIFIED verdict --------
# THE lethal-direction property: the binder credits at build time, but release_policy's S0 must-cover
# gate counts an s0_category ONLY from a row whose downstream 4-role verdict == VERIFIED. So a claim
# the 4-role rejects (PARTIAL / UNSUPPORTED / FABRICATED) earns NO S0 credit even if it carried a
# binder-credited category. This is what makes the binder ADDITIVE credit, not a gate relaxation.
# (release_policy.py is byte-untouched by this PR — this test asserts the property end-to-end through
# the unchanged gate using a binder-credited category.)


@pytest.mark.parametrize("non_verified_verdict", ["PARTIAL", "UNSUPPORTED", "FABRICATED"])
def test_binder_credited_category_does_not_satisfy_must_cover_unless_verified(
    non_verified_verdict,
):
    # A row carrying the binder-credited category but a NON-VERIFIED 4-role verdict must NOT clear the
    # S0 must-cover gate — the required category is still held missing.
    row = D8ClaimRow(
        claim_id="c1",
        severity="S0",
        verdict=non_verified_verdict,
        s0_categories=["contraindications"],
    )
    decision = apply_d8_release_policy(
        [row],
        required_s0_categories=["contraindications"],
        coverage_ledger=CoverageLedger(required_element_ids=["e1"], covered_element_ids={"e1"}),
        coverage_threshold=0.70,
        rewrite_already_attempted=True,
    )
    assert "d8_s0_must_cover_missing:contraindications" in decision.held_reasons


def test_binder_credited_category_satisfies_must_cover_when_verified():
    # The SAME credited category on a VERIFIED row clears the gate (the credit is real when the claim
    # survives the 4-role) — proving the binder credit reaches D8 end-to-end.
    row = D8ClaimRow(
        claim_id="c1",
        severity="S0",
        verdict="VERIFIED",
        s0_categories=["contraindications"],
    )
    decision = apply_d8_release_policy(
        [row],
        required_s0_categories=["contraindications"],
        coverage_ledger=CoverageLedger(required_element_ids=["e1"], covered_element_ids={"e1"}),
        coverage_threshold=0.70,
        rewrite_already_attempted=True,
    )
    assert "d8_s0_must_cover_missing:contraindications" not in decision.held_reasons
