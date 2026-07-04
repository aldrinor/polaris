"""Behavioral tests for I-deepfix B16 (#1360) overstatement guards.

These assert the fix via the PRODUCTION code path
(`verify_sentence_provenance` in `provenance_generator`), not just the leaf
module: a paraphrase that upgrades a modeling ASSUMPTION to an empirical finding,
or that merges/widens a time-horizon, must DROP even though the numeric leg
passes; while a faithful, hedge-preserving / horizon-matching paraphrase still
passes; and disabling the env flags reverts to the pre-B16 (passing) behaviour
so the legs are proven ADDITIVE (only ever add drops, never relax).

Entailment is forced OFF so these tests isolate the B16 legs offline (the
entailment judge needs the network); the B16 legs are deterministic + stdlib.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.overstatement_guard import (
    epistemic_overstatement_reason,
    temporal_scope_reason,
)
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)


@pytest.fixture(autouse=True)
def _entailment_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate the B16 legs: no network entailment call in these offline tests.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    # Isolate the B16 epistemic + temporal legs from the LATER w4-SL drop legs
    # (S5/L1/L2/L3, added default-ON in group w4-SL). Those legs are strictly
    # additive too, so with the B16 flag OFF a B16 test that expects "reverts to
    # pass" must not be re-dropped by a sibling w4-SL leg firing on the same
    # overstatement (e.g. S5 also drops the "we assumed 60%" -> "the data show 60%"
    # shape as defense-in-depth). Disabling them here keeps each B16 additive-proof
    # test a clean single-leg isolation; their own coverage lives in
    # test_deepfix_w4sl_s5_l1_l2_l3.py.
    monkeypatch.setenv("PG_STRICT_VERIFY_NUMERIC_QUALIFIER_RETENTION", "0")
    monkeypatch.setenv("PG_PROVENANCE_NUMERIC_ROLE_MATCH", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_CLINICAL_QUALIFIER_UNIT", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_CLINICAL_POLARITY", "0")
    # Also hold OFF the deployed P5 epistemic-qualifier gate
    # (``binding_qualifier_dropped`` in provenance_generator / clinical strict_verify).
    # P5 is the SAME overstatement family as the B16 epistemic leg and, being an
    # independent additive drop, also drops "we assumed 60%" -> "the data show 60%".
    # In production all legs stay ON (defense-in-depth); to prove the B16 leg is
    # additive in ISOLATION its "reverts-to-pass" test must hold every sibling
    # epistemic gate off. P5's own coverage lives in
    # test_deepfix_p5_qualifier_retention_production.py.
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_RETENTION", "0")


# ─────────────────────────────────────────────────────────────────────────────
# Leg 1: epistemic-marker preservation
# ─────────────────────────────────────────────────────────────────────────────
def test_assumption_rendered_as_finding_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    """CBRE-style: span states an ASSUMPTION; paraphrase asserts it as a finding.

    The number (60%) is IN the cited span, so the numeric leg passes — the
    sentence would survive pre-B16. The epistemic leg must drop it.
    """
    monkeypatch.setenv("PG_EPISTEMIC_MARKER_GUARD", "1")
    direct_quote = "In our model we assumed 60% of relocations create new positions."
    evidence_pool = {"ev_cbre": {"direct_quote": direct_quote}}
    # Cited span covers "we assumed 60% of relocations" (assumption framing + number).
    # The CLAIM, however, asserts it empirically with no hedge.
    sentence = "The data show 60% of relocations create new positions [#ev:ev_cbre:13-63]."
    v = verify_sentence_provenance(sentence, evidence_pool)
    assert v.is_verified is False
    assert any(
        f.startswith("epistemic_overstatement_assumption_as_finding")
        for f in v.failure_reasons
    ), v.failure_reasons


def test_assumption_preserved_as_hedge_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same span, but the paraphrase KEEPS the modeling hedge -> passes."""
    monkeypatch.setenv("PG_EPISTEMIC_MARKER_GUARD", "1")
    direct_quote = "In our model we assumed 60% of relocations create new positions."
    evidence_pool = {"ev_cbre": {"direct_quote": direct_quote}}
    sentence = "The model assumes 60% of relocations create new positions [#ev:ev_cbre:13-63]."
    v = verify_sentence_provenance(sentence, evidence_pool)
    assert v.is_verified is True, v.failure_reasons


def test_epistemic_guard_off_reverts_to_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADDITIVE proof: with the flag OFF, the overstated claim passes again
    (the leg only ADDS a drop; it never relaxes an existing check)."""
    monkeypatch.setenv("PG_EPISTEMIC_MARKER_GUARD", "0")
    direct_quote = "In our model we assumed 60% of relocations create new positions."
    evidence_pool = {"ev_cbre": {"direct_quote": direct_quote}}
    sentence = "The data show 60% of relocations create new positions [#ev:ev_cbre:13-63]."
    v = verify_sentence_provenance(sentence, evidence_pool)
    assert v.is_verified is True, v.failure_reasons


def test_empirical_span_not_falsely_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuinely EMPIRICAL span (no assumption framing) reported as a finding
    must NOT be dropped by the epistemic leg (no false positive)."""
    monkeypatch.setenv("PG_EPISTEMIC_MARKER_GUARD", "1")
    direct_quote = "The trial found a mean weight loss of 14.9% at week 68."
    evidence_pool = {"ev_trial": {"direct_quote": direct_quote}}
    # span 11-55 = "found a mean weight loss of 14.9% at week 68"
    sentence = "The trial found a mean weight loss of 14.9% at week 68 [#ev:ev_trial:10-54]."
    v = verify_sentence_provenance(sentence, evidence_pool)
    assert v.is_verified is True, v.failure_reasons


# ─────────────────────────────────────────────────────────────────────────────
# Leg 2: temporal-scope match
# ─────────────────────────────────────────────────────────────────────────────
# Full span (0-59) covers the number, the span's own horizon ("five years"),
# AND content words ("employment"/"shrank"/"automation") — so the numeric AND
# content-overlap legs pass on their own; the temporal leg is the deciding factor.
_AUTO_DQ = "Employment shrank 2.5% over five years following automation."
# Widened claim shares >=2 content words with the span ("employment", "shrank",
# "automation") so it ONLY trips the temporal leg, not the content-overlap leg.
_AUTO_WIDENED = "Employment shrank 2.5% over the 2010-2023 automation window [#ev:ev_auto:0-59]."
_AUTO_FAITHFUL = "Employment shrank 2.5% over five years after automation [#ev:ev_auto:0-59]."


def test_widened_year_range_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Span reports an effect 'over five years'; paraphrase restates it under a
    different '2010-2023' window. The shrinkage number AND >=2 content words
    match, so the numeric + content legs pass — the temporal leg must drop the
    merged horizon."""
    monkeypatch.setenv("PG_TEMPORAL_SCOPE_GUARD", "1")
    evidence_pool = {"ev_auto": {"direct_quote": _AUTO_DQ}}
    v = verify_sentence_provenance(_AUTO_WIDENED, evidence_pool)
    assert v.is_verified is False
    assert any(
        f.startswith("temporal_scope_mismatch") for f in v.failure_reasons
    ), v.failure_reasons


def test_matching_horizon_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same span, but the paraphrase reports the SAME horizon -> passes."""
    monkeypatch.setenv("PG_TEMPORAL_SCOPE_GUARD", "1")
    evidence_pool = {"ev_auto": {"direct_quote": _AUTO_DQ}}
    v = verify_sentence_provenance(_AUTO_FAITHFUL, evidence_pool)
    assert v.is_verified is True, v.failure_reasons


def test_temporal_guard_off_reverts_to_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADDITIVE proof: flag OFF -> the widened-horizon claim passes again
    (the same claim that the temporal leg drops when ON)."""
    monkeypatch.setenv("PG_TEMPORAL_SCOPE_GUARD", "0")
    evidence_pool = {"ev_auto": {"direct_quote": _AUTO_DQ}}
    v = verify_sentence_provenance(_AUTO_WIDENED, evidence_pool)
    assert v.is_verified is True, v.failure_reasons


def test_span_without_horizon_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the cited span names NO horizon, the temporal leg must not fire
    (no false drop) even when the claim names a period."""
    monkeypatch.setenv("PG_TEMPORAL_SCOPE_GUARD", "1")
    direct_quote = "Employment shrank 2.5% following automation in the sector."
    evidence_pool = {"ev_auto": {"direct_quote": direct_quote}}
    # span 11-22 = "shrank 2.5%"
    sentence = "Employment shrank 2.5% over five years [#ev:ev_auto:11-22]."
    v = verify_sentence_provenance(sentence, evidence_pool)
    # Temporal leg inert (span has no horizon); no temporal_scope_mismatch.
    assert not any(
        f.startswith("temporal_scope_mismatch") for f in v.failure_reasons
    ), v.failure_reasons


# ─────────────────────────────────────────────────────────────────────────────
# Leaf-unit sanity (pure functions, no pool plumbing)
# ─────────────────────────────────────────────────────────────────────────────
def test_leaf_epistemic_reason() -> None:
    assert (
        epistemic_overstatement_reason(
            "Data show 60% create new positions",
            "we assumed 60% create new positions",
        )
        == "epistemic_overstatement_assumption_as_finding"
    )
    # Hedge preserved -> None.
    assert (
        epistemic_overstatement_reason(
            "The model assumes 60% create new positions",
            "we assumed 60% create new positions",
        )
        is None
    )
    # Empirical span -> None.
    assert (
        epistemic_overstatement_reason(
            "Data show 60% create new positions",
            "the study found 60% create new positions",
        )
        is None
    )


def test_leaf_epistemic_no_false_drop_on_statistical_method_prose() -> None:
    """I-deepfix-001 Codex P1 (iter 2): EMPIRICAL statistical-method spice that
    merely MENTIONS 'assumption'/'modeled' is NOT a value-level modeling
    assumption — an empirical claim cited to it must NOT drop.
    """
    # Cox-model diagnostic — "the proportional hazards assumption".
    assert (
        epistemic_overstatement_reason(
            "Mortality was 12.3% lower in the treatment arm",
            "We tested the proportional hazards assumption before fitting the Cox model.",
        )
        is None
    )
    # First-person empirical analysis method — "we modeled ... using regression".
    assert (
        epistemic_overstatement_reason(
            "Survival was longer in the intervention group",
            "We modeled survival using a Cox proportional-hazards regression.",
        )
        is None
    )
    # Passive empirical method — "outcomes were modeled using logistic regression".
    assert (
        epistemic_overstatement_reason(
            "The infection rate was 4.2%",
            "Outcomes were modeled using logistic regression with robust standard errors.",
        )
        is None
    )
    # Test diagnostic — "the normality assumption held".
    assert (
        epistemic_overstatement_reason(
            "The mean difference was 2.1 points",
            "The normality assumption held for all outcome measures.",
        )
        is None
    )
    # TRUE positive still fires: a value-level "we assumed X" rendered as a finding.
    assert (
        epistemic_overstatement_reason(
            "Data show 60% of relocations create new positions",
            "In our model we assumed 60% of relocations create new positions.",
        )
        == "epistemic_overstatement_assumption_as_finding"
    )


def test_leaf_epistemic_value_anchored() -> None:
    """I-deepfix-001 Codex P1 (iter 3): a methodological 'assuming that <non-numeric
    condition>' clause that governs an empirical RESULT must NOT drop, and the leg
    fires only when the claim ECHOES the assumed value.
    """
    # "assuming that <condition>, ... 12.3% result" -> the in-clause has no number
    # (the 12.3% is in the downstream result clause) -> inert.
    assert (
        epistemic_overstatement_reason(
            "The adjusted analysis showed a 12.3% reduction",
            "Assuming that censoring was non-informative, the adjusted analysis showed a 12.3% reduction.",
        )
        is None
    )
    # Value-anchored TP with a DECIMAL assumed value still fires.
    assert (
        epistemic_overstatement_reason(
            "Uptake was 14.9% among eligible patients",
            "In the base case we assumed 14.9% uptake among eligible patients.",
        )
        == "epistemic_overstatement_assumption_as_finding"
    )
    # Claim does NOT report the assumed value (no echo) -> inert.
    assert (
        epistemic_overstatement_reason(
            "Mortality was 8% in the cohort",
            "We assumed 60% uptake among eligible patients.",
        )
        is None
    )


def test_leaf_temporal_reason() -> None:
    assert temporal_scope_reason(
        "shrank 2.5% over the 2010-2023 period",
        "shrank 2.5% over five years",
    ) == "temporal_scope_mismatch:ranges=2010-2023"
    # Matching horizon -> None.
    assert (
        temporal_scope_reason(
            "shrank 2.5% over five years",
            "shrank 2.5% over five years",
        )
        is None
    )
    # Span has no horizon -> None.
    assert (
        temporal_scope_reason(
            "shrank 2.5% over five years",
            "shrank 2.5% after automation",
        )
        is None
    )
