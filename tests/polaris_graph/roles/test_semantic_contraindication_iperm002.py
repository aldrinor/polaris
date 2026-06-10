"""I-perm-002 (#1196) semantic contraindication credit — matcher + behavioral flip.

The CDC contraindication source for the probiotic safety entity says probiotics "should be avoided
for patients who ... are immunocompromised" — it NEVER uses the word "contraindicated". So a
FAITHFUL claim grounded in it (drb_76 claim 03-001, "not recommended for patients who are
immunocompromised", VERIFIED) can never contain the literal token, and the S0 ``contraindications``
category went un-credited -> ``released_insufficient_safety_evidence`` even though the report DID
warn. ``PG_SWEEP_SEMANTIC_CONTRAINDICATION`` (default OFF) relaxes ONLY the contraindication CONCEPT
token to a high-precision DIRECTION synonym set, keeps the population token literal, and refuses
credit on any negated / opposite-direction phrase.

Direction of error (binding): over-crediting a contraindication is §-1.1-LETHAL; under-crediting is
a SAFE disclosed gap under always-release (I-perm-001). Every assertion below checks that the
negation guard makes over-credit impossible while the genuine warning credits.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.polaris_graph.roles import native_gate_b_inputs as ng

_FLAG = "PG_SWEEP_SEMANTIC_CONTRAINDICATION"

# Inline synthetic entity mirroring config/scope_templates/clinical.yaml
# `probiotic_immunocompromised_contraindication` — kept inline so the unit tests are robust to
# config edits. The literal concept token + the literal population anchor.
_ENTITY = {
    ng._KEY_ENTITY_ID: "probiotic_immunocompromised_contraindication",
    ng._KEY_ENTITY_CONTENT_REQS: ["contraindicated", "immunocompromised"],
}

# The REAL drb_76 claim 03-001 text (VERIFIED, cites the CDC contraindication source). A genuine
# warning that lacks the literal token "contraindicated".
_REAL_WARNING = (
    "On the basis of these data, the authors explicitly advise that probiotics are not "
    "recommended for patients who are immunocompromised, critically ill, or have indwelling "
    "catheters."
)


@pytest.fixture(autouse=True)
def _clear_flag():
    os.environ.pop(_FLAG, None)
    yield
    os.environ.pop(_FLAG, None)


# --- OFF: byte-identical literal-exact match (the genuine warning is NOT credited) -----------


def test_off_is_literal_exact_unchanged():
    os.environ.pop(_FLAG, None)
    # The genuine warning lacks the literal "contraindicated" -> NOT credited (pre-fix behavior).
    assert ng._content_requirements_satisfied(_REAL_WARNING, _ENTITY) is False
    # A claim with BOTH literal tokens still credits exactly as before.
    assert (
        ng._content_requirements_satisfied(
            "probiotics are contraindicated in immunocompromised patients", _ENTITY
        )
        is True
    )
    for falsey in ("0", "false", "no", "off", ""):
        os.environ[_FLAG] = falsey
        assert ng._content_requirements_satisfied(_REAL_WARNING, _ENTITY) is False


# --- ON: high-precision contraindication-DIRECTION synonyms credit (population stays literal) -


@pytest.mark.parametrize(
    "claim",
    [
        _REAL_WARNING,  # "not recommended ... immunocompromised" — the real drb_76 warning
        "live probiotics should be avoided in immunocompromised hosts",
        "this product should not be used in immunocompromised patients",
        "the agent must not be given to immunocompromised individuals",
        "probiotics are contraindicated in immunocompromised patients",  # literal still works
        # a DISTANT negator (>20 chars from the stem) must NOT suppress a genuine warning.
        "there is no doubt probiotics are contraindicated in immunocompromised patients",
        # Codex P2 fix: a contrastive warning ("safe for most adults, BUT not recommended for the
        # population") must credit — the old whole-claim "are safe" scan wrongly refused it.
        "although probiotics are safe for most adults, they are not recommended "
        "for immunocompromised patients",
    ],
)
def test_on_credits_direction_synonyms_with_population(claim):
    os.environ[_FLAG] = "1"
    assert ng._content_requirements_satisfied(claim, _ENTITY) is True


# --- ON: the negation guard makes over-credit impossible (§-1.1-lethal direction) ------------


@pytest.mark.parametrize(
    "claim",
    [
        # Negated contraindication — the pathological case. MUST refuse.
        "probiotics are not contraindicated in immunocompromised patients",
        "there is no contraindication to probiotics in immunocompromised hosts",
        "probiotics should not be avoided in immunocompromised patients",
        # Opposite direction — safe/recommended for the population. MUST refuse.
        "probiotics are well tolerated in immunocompromised patients",
        "probiotics are safe in immunocompromised patients",
        "probiotics are considered safe for immunocompromised patients",
        # Codex P0-1 (iter-1): interposed-qualifier negations the brittle contiguous list MISSED.
        "cdc reports no known contraindications to s. boulardii probiotics in immunocompromised patients",
        "s. boulardii is not generally contraindicated in immunocompromised patients",
        "it is not clearly contraindicated in immunocompromised patients",
        "the product need not be contraindicated in immunocompromised patients",
        # the in-place "against" inverter of a directional imperative.
        "probiotics are not recommended against use in immunocompromised patients",
        # post-stem absence predicate.
        "contraindications are unknown in immunocompromised patients",
        "contraindications have not been established in immunocompromised patients",
        # Codex P0-2 (iter-2): contraction negations the expanded-only regex missed.
        "s. boulardii probiotics aren't contraindicated in immunocompromised patients",
        "it isn't contraindicated in immunocompromised patients",
        "there aren't contraindications for probiotics in immunocompromised patients",
        "contraindications haven't been established in immunocompromised patients",
        # curly apostrophe (U+2019) must not defeat contraction expansion.
        "probiotics aren’t contraindicated in immunocompromised patients",
        # short absence forms.
        "probiotics are free of contraindications in immunocompromised patients",
        "there are zero contraindications for probiotics in immunocompromised patients",
        # Codex P0-3 (iter-3): the "recommend against" inverter INTERPOSED beyond a fixed window.
        "probiotics are not recommended by the cdc source against use in immunocompromised patients",
        "probiotics are not recommended, per the 2021 report, against use in immunocompromised hosts",
    ],
)
def test_on_negation_guard_refuses_inverted(claim):
    os.environ[_FLAG] = "1"
    assert ng._content_requirements_satisfied(claim, _ENTITY) is False


def test_on_relaxes_plural_concept_token():
    """Codex iter-3 P2: a future config token "contraindications" (plural) is also relaxed."""
    os.environ[_FLAG] = "1"
    plural_entity = {
        ng._KEY_ENTITY_ID: "x",
        ng._KEY_ENTITY_CONTENT_REQS: ["contraindications", "immunocompromised"],
    }
    assert (
        ng._content_requirements_satisfied(
            "probiotics are not recommended for immunocompromised patients", plural_entity
        )
        is True
    )
    # and it still refuses an inverted claim under the plural token.
    assert (
        ng._content_requirements_satisfied(
            "there are no contraindications for probiotics in immunocompromised patients",
            plural_entity,
        )
        is False
    )


def test_on_is_strictly_safer_than_off_for_negated_contraindicated():
    """The bare-substring OFF path WRONGLY credits "not contraindicated"; the ON negation guard
    refuses it. ON is therefore not a pure superset — it ADDS the faithful-warning path and
    SUBTRACTS this latent over-credit."""
    inverted = "probiotics are not contraindicated in immunocompromised patients"
    os.environ.pop(_FLAG, None)
    assert ng._content_requirements_satisfied(inverted, _ENTITY) is True  # latent OFF over-credit
    os.environ[_FLAG] = "1"
    assert ng._content_requirements_satisfied(inverted, _ENTITY) is False  # ON refuses it


# --- ON: the population token is NEVER relaxed (wrong population / missing population refuse) --


@pytest.mark.parametrize(
    "claim",
    [
        "probiotics are not recommended for pregnant women",  # wrong population
        "probiotics should be avoided in patients with short bowel syndrome",  # wrong population
        "probiotic use was strongly associated with fungemia compared with controls",  # no pop, no dir
    ],
)
def test_on_population_anchor_stays_literal(claim):
    os.environ[_FLAG] = "1"
    assert ng._content_requirements_satisfied(claim, _ENTITY) is False


def test_on_empty_requirements_fail_closed():
    os.environ[_FLAG] = "1"
    empty = {ng._KEY_ENTITY_ID: "x", ng._KEY_ENTITY_CONTENT_REQS: []}
    assert ng._content_requirements_satisfied(_REAL_WARNING, empty) is False
    blank = {ng._KEY_ENTITY_ID: "x", ng._KEY_ENTITY_CONTENT_REQS: ["   ", ""]}
    assert ng._content_requirements_satisfied(_REAL_WARNING, blank) is False


# --- behavioral: drb_76 flips insufficient-safety -> caveated release WITHOUT fabricating ------


_SAVED_POOL = (
    Path(__file__).resolve().parents[3]
    / "outputs/audits/beatboth8/drb_76/four_role_claim_audit.json"
)


@pytest.mark.skipif(
    not _SAVED_POOL.is_file(),
    reason="saved beatboth8 drb_76 run not present (gitignored) — unit matcher tests cover CI",
)
def test_drb76_flips_to_released_with_disclosed_gaps():
    from tests.polaris_graph.replay.d8_replay_harness import (
        replay_d8,
        replay_release_outcome,
    )
    from tests.polaris_graph.replay.saved_run_loader import (
        default_run_dir,
        load_saved_run,
    )

    run = load_saved_run(default_run_dir())

    # OFF: the literal-era safety floor reports insufficient (the genuine warning is un-credited).
    os.environ.pop(_FLAG, None)
    d_off = replay_d8(run, corpus_satisfaction=True)
    assert "contraindications" not in d_off.credited_categories
    out_off = replay_release_outcome(run, always_release=True, corpus_satisfaction=True)
    assert out_off.status == "released_insufficient_safety_evidence"
    assert out_off.safety_floor == "insufficient"
    assert out_off.normal_release_blocked is True

    # ON: the contraindication category credits from the faithful warning -> safety floor clears ->
    # caveated-normal release. The credit comes from a VERIFIED claim that genuinely warned; nothing
    # is fabricated, and coverage rises by exactly the one contraindication element.
    os.environ[_FLAG] = "1"
    d_on = replay_d8(run, corpus_satisfaction=True)
    assert "contraindications" in d_on.credited_categories
    assert d_on.covered_element_ids > d_off.covered_element_ids
    out_on = replay_release_outcome(run, always_release=True, corpus_satisfaction=True)
    assert out_on.status == "released_with_disclosed_gaps"
    assert out_on.safety_floor == "ok"
    assert out_on.normal_release_blocked is False
    assert out_on.released is True
