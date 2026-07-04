"""I-deepfix-001 deferred-fix E (#1344) — unit-stripped quantified-attribution regression.

Item 13b: a quantified attribution that carries a ``trillion``-magnitude figure (e.g.
"Generative AI could add $2.6 trillion") was rendered with its unit stripped ("$2.6" / a bare
2.6) because ``trillion`` was omitted from the scale-word handling in BOTH:

  * ``evidence_extractor`` — the "Currency" pattern's scale alternation AND the value
    multiplier block. The multiplier block also never fired for the currency pattern at all
    (its ``default_unit="USD"`` blocked the scale word from ever reaching ``unit``), so even
    "$1.548 billion" emitted a unit-stripped 1.548-USD cost datapoint ALONGSIDE the correct
    1.548e9. ``trillion`` was simply the case with NO correct value at all.
  * ``tradeoff_modeler`` — ``_LITERAL_RE`` + ``_SCALE_MULTIPLIERS`` (needed so a 2.6e12 value
    can be located back to its "$2.6 trillion" source literal).

FAITHFULNESS: this STRENGTHENS fidelity — the magnitude is preserved end-to-end (value scales
to 2.6e12 with USD attached, the located literal keeps "$2.6 trillion") and the spurious
unit-stripped mantissa is no longer emitted. No faithfulness gate is relaxed; the literal-span
invariant (``_locate_unique_literal`` fail-closed on non-unique/absent match) is untouched.
§-1.3: no source is dropped, nothing is filtered.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence
from src.polaris_graph.synthesis.tradeoff_modeler import (
    _locate_unique_literal,
    _normalize_literal,
)

_TRILLION_QUOTE = "Generative AI could add $2.6 trillion to the global economy by 2030."


def _extract(quote: str) -> list[dict]:
    store = {"ev_1": {"direct_quote": quote, "statement": quote, "source_url": "u"}}
    return extract_numbers_from_evidence(store)


# ── RED-before / GREEN-after: trillion magnitude must survive extraction ──────────────────
def test_trillion_value_is_scaled_not_stripped():
    """"$2.6 trillion" must extract as 2.6e12 (a real quantity), not the unitless 2.6."""
    dps = _extract(_TRILLION_QUOTE)
    values = [float(dp["value"]) for dp in dps]
    assert any(abs(v - 2.6e12) < 1.0 for v in values), (
        f"trillion magnitude lost: extracted values={values} (expected one == 2.6e12)"
    )


def test_trillion_no_unit_stripped_mantissa_emitted():
    """P2 test-gap fix: '$2.6 trillion' must NOT ALSO emit a unit-stripped ~2.6 mantissa
    datapoint (the pre-fix currency pattern did). EVERY emitted datapoint for the trillion
    figure must carry the full 2.6e12 magnitude — never the bare 2.6 nor a "2.6 trillion"
    unit-label that hides the magnitude in the unit string."""
    dps = _extract(_TRILLION_QUOTE)
    # No datapoint may sit at the bare mantissa (2.6e12 is orders of magnitude away, safe).
    stripped = [
        dp for dp in dps if abs(float(dp["value"]) - 2.6) < 1.0
    ]
    assert not stripped, (
        "unit-stripped mantissa datapoint(s) emitted for '$2.6 trillion': "
        f"{[(dp['data_type'], dp['value'], dp['unit']) for dp in stripped]}"
    )
    # No datapoint may bury the magnitude in a raw 'trillion' unit label either.
    scale_labelled = [dp for dp in dps if dp["unit"].lower() == "trillion"]
    assert not scale_labelled, (
        f"scale word left in unit field: {[(dp['value'], dp['unit']) for dp in scale_labelled]}"
    )


def test_trillion_datapoint_is_usd_at_full_magnitude():
    """'$2.6 trillion' -> a 2.6e12 datapoint whose unit is USD (currency attached)."""
    dps = _extract(_TRILLION_QUOTE)
    usd = [
        dp for dp in dps
        if abs(float(dp["value"]) - 2.6e12) < 1.0 and dp["unit"] == "USD"
    ]
    assert usd, (
        "no 2.6e12-USD datapoint produced: "
        f"{[(dp['value'], dp['unit']) for dp in dps]}"
    )


def test_trillion_literal_locates_with_unit_attached():
    """The located literal for the trillion figure keeps '$2.6 trillion' (unit attached)."""
    located = _locate_unique_literal(_TRILLION_QUOTE, 2.6e12)
    assert located is not None, "trillion literal could not be located at its true value 2.6e12"
    literal, _start, _end = located
    assert "trillion" in literal.lower(), f"unit stripped from located literal: {literal!r}"
    assert "2.6" in literal, f"quantity missing from located literal: {literal!r}"


def test_trillion_normalize_literal_scales():
    """_normalize_literal must parse the trillion scale word (was None before the fix)."""
    assert _normalize_literal("$2.6 trillion") == pytest.approx(2.6e12)
    assert _normalize_literal("4.4 trillion") == pytest.approx(4.4e12)


# ── Controls: existing billion/million/percent behaviour is unchanged ─────────────────────
def test_billion_control_full_magnitude_no_stripped_mantissa():
    quote = "The program cost was $1.548 billion in fiscal 2024."
    dps = _extract(quote)
    assert any(abs(float(dp["value"]) - 1.548e9) < 1.0 for dp in dps)
    # The base bug also stripped billion in the currency pattern; assert it's gone too.
    assert not [dp for dp in dps if abs(float(dp["value"]) - 1.548) < 0.5], (
        f"currency pattern still emits stripped 1.548: "
        f"{[(dp['data_type'], dp['value'], dp['unit']) for dp in dps]}"
    )
    located = _locate_unique_literal(quote, 1.548e9)
    assert located is not None and "billion" in located[0].lower()


def test_million_control_full_magnitude():
    quote = "Annual maintenance is $120 million per year."
    dps = _extract(quote)
    assert any(abs(float(dp["value"]) - 120e6) < 1.0 for dp in dps)
    assert not [dp for dp in dps if abs(float(dp["value"]) - 120.0) < 0.5], (
        "currency pattern still emits stripped 120 million mantissa"
    )


def test_percent_control_unit_preserved():
    quote = "AI assistance increases worker productivity by 14% on average."
    located = _locate_unique_literal(quote, 14.0)
    assert located is not None and "%" in located[0]
