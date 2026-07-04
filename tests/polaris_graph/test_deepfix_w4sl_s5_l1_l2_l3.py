"""I-deepfix-001 group w4-SL (#1344) — behavioral RED->GREEN proof of the four
faithfulness-TIGHTENING drop legs on the PRODUCTION verifier
``provenance_generator.verify_sentence_provenance`` (the BeatBoth composer /
abstractive-writer strict-verify path):

  S5 — span-faithful qualifier retention on HEADLINE numerics: a headline number
       re-lifted while its cited span binds it to a governing CONDITIONAL/THRESHOLD
       antecedent the claim drops -> DROP ``headline_numeric_qualifier_dropped``.
  L2 — numeric-fidelity VALUE-AND-ROLE re-check (currency + multiplier): a printed
       "$14 billion" / "14-fold" not grounded by the SAME value+role in the span
       (only a bare digit) -> DROP ``numeric_role_mismatch``.
  L1 — clinical qualifier as a UNIT: a shared number bound in the span to a clinical
       population/indication the claim drops or contradicts -> DROP
       ``clinical_qualifier_unit_dropped``.
  L3 — negation/contraindication semantic guard: a clinical relation stem whose
       polarity in the claim disagrees with the cited span ("not contraindicated"
       from a "contraindicated" span, or vice-versa) -> DROP
       ``clinical_polarity_mismatch``.

Every leg is STRICTLY ADDITIVE, DEFAULT-ON, with a byte-identical-OFF kill-switch.
Each test proves: (1) POSITIVE RED->GREEN on the production verifier (the sentence
passes today, drops with the leg); (2) BYTE-IDENTICAL-OFF via the kill-switch; plus
NEGATIVE over-fire / safe-under-drop controls. Fail-loud, fully offline (entailment
leg forced OFF; $0 spend). DNA §-1.3: these TIGHTEN the only hard gate, never relax
it — under-drop is safe, over-drop only trims breadth (the composer's verbatim
K-span fallback still ships the faithful, qualifier-carrying source text).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)

_S5_FLAG = "PG_STRICT_VERIFY_NUMERIC_QUALIFIER_RETENTION"
_L2_FLAG = "PG_PROVENANCE_NUMERIC_ROLE_MATCH"
_L1_FLAG = "PG_STRICT_VERIFY_CLINICAL_QUALIFIER_UNIT"
_L3_FLAG = "PG_STRICT_VERIFY_CLINICAL_POLARITY"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Force the entailment leg OFF (no network) and clear every w4-SL flag so each
    test runs against the DEFAULT (ON) config unless it overrides explicitly."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    for var in (_S5_FLAG, _L2_FLAG, _L1_FLAG, _L3_FLAG):
        monkeypatch.delenv(var, raising=False)
    yield


def _pool(span: str, eid: str = "evA") -> dict:
    return {eid: {"direct_quote": span, "statement": span}}


def _token(span: str, eid: str = "evA") -> str:
    return f"[#ev:{eid}:0-{len(span)}]"


def _verify(claim: str, span: str):
    return verify_sentence_provenance(f"{claim} {_token(span)}.", _pool(span))


def _has(reasons, prefix: str) -> bool:
    return any(str(r).startswith(prefix) for r in reasons)


# ════════════════════════════════════════════════════════════════════════════
# S5 — HEADLINE numeric conditional/threshold retention
# ════════════════════════════════════════════════════════════════════════════
# A unit-bearing INTEGER headline number (P5's epistemic gate excludes bare
# integers, so this case is the genuine S5 gap): the span binds "46 (million)" to
# the "up to ... if ..." threshold; the claim re-lifts it as a flat future fact.
_S5_SPAN = (
    "Up to 46 million jobs could be automated if firms accelerate adoption "
    "at the current pace."
)
_S5_STRIPPED = "Some 46 million jobs will be automated"


def test_s5_stripped_conditional_drops():
    """RED->GREEN: the flat re-lift drops ``headline_numeric_qualifier_dropped``."""
    v = _verify(_S5_STRIPPED, _S5_SPAN)
    assert v.is_verified is False, v.failure_reasons
    assert _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


def test_s5_kill_switch_reverts(monkeypatch):
    """Byte-identical-OFF: the SAME sentence passes with the leg disabled (the leak
    the default-ON leg closes)."""
    monkeypatch.setenv(_S5_FLAG, "0")
    v = _verify(_S5_STRIPPED, _S5_SPAN)
    assert v.is_verified is True, v.failure_reasons
    assert not _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


def test_s5_carried_condition_passes():
    """SAFE UNDER-DROP: a claim that CARRIES the governing antecedent passes."""
    v = _verify("Up to 46 million jobs could be automated", _S5_SPAN)
    assert v.is_verified is True, v.failure_reasons


def test_s5_bare_modal_does_not_retain_qualifier():
    """Codex P1 (iter 1): a claim that keeps ONLY a bare epistemic modal ("could")
    while dropping BOTH the span's "up to" threshold AND its "if ..." condition is an
    overstatement — a modal is neither a threshold nor a conditional, so it must NOT
    count as retaining the qualifier. Before the fix, ``could`` short-circuited the leg
    and this flat re-lift slipped through as verified."""
    v = _verify("46 million jobs could be automated", _S5_SPAN)
    assert v.is_verified is False, v.failure_reasons
    assert _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


def test_s5_bare_modal_may_also_drops():
    """The same holds for the other bare modals ("may"): a modal-only re-lift that
    strips the threshold/condition drops."""
    v = _verify("Some 46 million jobs may be automated", _S5_SPAN)
    assert _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


def test_s5_bare_modal_kill_switch_reverts(monkeypatch):
    """Byte-identical-OFF: the modal-only re-lift passes with the leg disabled — the
    leak the default-ON fix closes."""
    monkeypatch.setenv(_S5_FLAG, "0")
    v = _verify("46 million jobs could be automated", _S5_SPAN)
    assert v.is_verified is True, v.failure_reasons
    assert not _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


def test_s5_unconditional_span_no_drop():
    """OVER-FIRE guard: a span with NO governing conditional never fires."""
    span = "Adoption reached 46 million jobs across the region in 2024."
    v = _verify("Adoption reached 46 million jobs across the region", span)
    assert not _has(v.failure_reasons, "headline_numeric_qualifier_dropped"), v.failure_reasons


# ════════════════════════════════════════════════════════════════════════════
# L2 — VALUE-AND-ROLE (currency + multiplier)
# ════════════════════════════════════════════════════════════════════════════
_L2_CURRENCY_CLAIM = "The savings program delivered $14 billion in value"
# The value "14" is present in the span ONLY as bare digits (a page ref + a count),
# never as a currency figure -> role confusion.
_L2_ROLECONFUSED_SPAN = (
    "The savings program is described on page 14 and lists 14 review measures."
)


def test_l2_currency_role_confusion_drops():
    """RED->GREEN: a printed currency figure grounded only by bare digits drops."""
    v = _verify(_L2_CURRENCY_CLAIM, _L2_ROLECONFUSED_SPAN)
    assert v.is_verified is False, v.failure_reasons
    assert _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


def test_l2_kill_switch_reverts(monkeypatch):
    """Byte-identical-OFF: the SAME sentence passes with the leg disabled."""
    monkeypatch.setenv(_L2_FLAG, "0")
    v = _verify(_L2_CURRENCY_CLAIM, _L2_ROLECONFUSED_SPAN)
    assert v.is_verified is True, v.failure_reasons


def test_l2_currency_scale_mismatch_drops():
    """VALUE present as currency but the SCALE conflicts (billion vs million)."""
    span = "The savings program delivered $14 million in value this year."
    v = _verify(_L2_CURRENCY_CLAIM, span)
    assert _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


def test_l2_currency_cross_form_passes():
    """SAFE: same value+role expressed differently ("$14 billion" vs "14 billion
    dollars") is grounded -> no drop."""
    span = "The savings program delivered 14 billion dollars in cumulative value."
    v = _verify(_L2_CURRENCY_CLAIM, span)
    assert v.is_verified is True, v.failure_reasons


def test_l2_currency_no_scale_claim_is_lenient():
    """FAIL-OPEN: a claim currency with NO scale is satisfied by any same-value
    currency in the span (never a false scale conflict)."""
    span = "The fee was $14 billion under the revised structure."
    v = _verify("The fee was $14 in the base case", span)
    assert not _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


def test_l2_multiplier_role_confusion_drops():
    """A printed multiplier ("14-fold") grounded only by bare digits drops."""
    claim = "Risk was 14-fold higher in the exposed group"
    span = "The exposed group is discussed across 14 sites on page 14."
    v = _verify(claim, span)
    assert _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


def test_l2_multiplier_grounded_passes():
    """SAFE: a multiplier grounded by the same-value multiplier in the span passes."""
    claim = "Risk was 14-fold higher in the exposed group"
    span = "Risk was 14-fold higher among exposed participants than controls."
    v = _verify(claim, span)
    assert not _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


def test_l2_no_currency_claim_inert():
    """A bare-percent claim (no currency/multiplier role) is inert for L2."""
    span = "Adoption reached 46% of firms in 2024 across the region."
    v = _verify("Adoption reached 46% of firms across the region", span)
    assert not _has(v.failure_reasons, "numeric_role_mismatch"), v.failure_reasons


# ════════════════════════════════════════════════════════════════════════════
# L1 — clinical qualifier as a UNIT (number + population/indication)
# ════════════════════════════════════════════════════════════════════════════
_L1_SPAN = (
    "In immunocompromised patients, the infection rate was 30% higher than in "
    "controls."
)


def test_l1_dropped_population_drops():
    """RED->GREEN: the claim keeps the number but drops the governing population."""
    v = _verify("The infection rate was 30% higher", _L1_SPAN)
    assert v.is_verified is False, v.failure_reasons
    assert _has(v.failure_reasons, "clinical_qualifier_unit_dropped"), v.failure_reasons


def test_l1_kill_switch_reverts(monkeypatch):
    """Byte-identical-OFF: the SAME sentence passes with the leg disabled."""
    monkeypatch.setenv(_L1_FLAG, "0")
    v = _verify("The infection rate was 30% higher", _L1_SPAN)
    assert v.is_verified is True, v.failure_reasons


def test_l1_wrong_population_drops():
    """The number bound to the WRONG population (healthy adults vs the span's
    immunocompromised) drops — the lethal mis-population."""
    v = _verify("In healthy adults the infection rate was 30% higher", _L1_SPAN)
    assert _has(v.failure_reasons, "clinical_qualifier_unit_dropped"), v.failure_reasons


def test_l1_carried_population_passes():
    """SAFE: the claim carries the governing population -> the qualifier travelled."""
    v = _verify(
        "In immunocompromised patients the infection rate was 30% higher", _L1_SPAN
    )
    assert v.is_verified is True, v.failure_reasons


def test_l1_no_population_span_inert():
    """OVER-FIRE guard: a span with no clinical population near the number is inert."""
    span = "Across the cohort, the infection rate was 30% higher than baseline."
    v = _verify("The infection rate was 30% higher", span)
    assert not _has(v.failure_reasons, "clinical_qualifier_unit_dropped"), v.failure_reasons


def test_l1_no_number_inert():
    """A claim with no number cannot mis-bind -> L1 inert."""
    span = "Probiotics are used in immunocompromised patients under supervision."
    v = _verify("Probiotics are used under supervision", span)
    assert not _has(v.failure_reasons, "clinical_qualifier_unit_dropped"), v.failure_reasons


# ════════════════════════════════════════════════════════════════════════════
# L3 — clinical negation / contraindication polarity
# ════════════════════════════════════════════════════════════════════════════
_L3_POS_SPAN = "Probiotics are contraindicated in immunocompromised patients per CDC."


def test_l3_negation_inversion_drops():
    """RED->GREEN: "not contraindicated" rendered from a "contraindicated" span drops."""
    v = _verify(
        "Probiotics are not contraindicated in immunocompromised patients",
        _L3_POS_SPAN,
    )
    assert v.is_verified is False, v.failure_reasons
    assert _has(v.failure_reasons, "clinical_polarity_mismatch"), v.failure_reasons


def test_l3_kill_switch_reverts(monkeypatch):
    """Byte-identical-OFF: the SAME sentence passes with the leg disabled."""
    monkeypatch.setenv(_L3_FLAG, "0")
    v = _verify(
        "Probiotics are not contraindicated in immunocompromised patients",
        _L3_POS_SPAN,
    )
    assert v.is_verified is True, v.failure_reasons


def test_l3_reverse_inversion_drops():
    """The reverse inversion also drops: a positive claim from a negated span."""
    span = "The drug is not recommended for children under twelve."
    v = _verify("The drug is recommended for children", span)
    assert _has(v.failure_reasons, "clinical_polarity_mismatch"), v.failure_reasons


def test_l3_contraction_negation_drops():
    """A negative CONTRACTION ("isn't recommended") is normalized and still fires."""
    span = "The regimen is recommended as first-line therapy."
    v = _verify("The regimen isn't recommended as first-line therapy", span)
    assert _has(v.failure_reasons, "clinical_polarity_mismatch"), v.failure_reasons


def test_l3_same_polarity_passes():
    """SAFE: matching polarity (both asserted) -> no drop."""
    v = _verify(
        "Probiotics are contraindicated in immunocompromised patients", _L3_POS_SPAN
    )
    assert v.is_verified is True, v.failure_reasons


def test_l3_both_negated_passes():
    """SAFE: both negated ("not recommended") -> no polarity conflict."""
    span = "The drug is not recommended for children under twelve."
    v = _verify("The drug is not recommended for children", span)
    assert not _has(v.failure_reasons, "clinical_polarity_mismatch"), v.failure_reasons
