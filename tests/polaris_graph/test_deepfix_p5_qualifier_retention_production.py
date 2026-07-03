"""I-deepfix-001 P5_hedge_preservation (#1344) — PRODUCTION-PATH port of the
epistemic-QUALIFIER RETENTION gate.

Codex P5 diff-gate P1 (BLOCKER): the first P5 diff added the gate only to
``clinical_generator.strict_verify.verify_sentence``, but the BeatBoth composer /
abstractive-writer path runs ``provenance_generator.verify_sentence_provenance``
(via ``verified_compose._compose_one_basket`` -> ``multi_section_generator``). A
hedge-stripped sentence on the ACTUAL fresh-run path therefore escaped the gate.
This suite proves the ported gate on the production verifier AND on the real
verified-compose K-span fallback, with NO model spend (a deterministic writer_fn
stands in for the LLM).

The composer can copy a numeral's VALUE but drop the epistemic / scope qualifier
the cited span binds to it — "some estimates suggest 46% of workers could be
affected under a complementary-software scenario" restated as a flat "46% of
workers are affected". Every mechanical leg (decimal / integer / percent-role /
content-overlap) PASSES the stripped restatement and the NLI leg is systematically
lenient to hedge-dropping, so the defect needs its OWN completeness gate. The gate
is strictly ADDITIVE, default-ON, with a byte-identical-OFF kill-switch
PG_STRICT_VERIFY_QUALIFIER_RETENTION=0.

Fail-loud, offline (entailment leg forced OFF; deterministic writer). It proves:

  (1) POSITIVE (RED->GREEN) on verify_sentence_provenance: a span that binds an
      epistemic marker to a SHARED substantive numeral, restated by a sentence
      carrying NO marker, DROPS with failure ``binding_qualifier_dropped``. Before
      the port this sentence was is_verified=True on this verifier — the RED anchor.
  (2) BYTE-IDENTICAL-OFF: PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 reverts the SAME
      sentence to is_verified=True (the pre-port production leak).
  (3) NEGATIVE OVER-FIRE guards: a bare count, a flat decimal finding, and a flat
      percent finding get NO new drop on the production verifier.
  (4) SAFE UNDER-DROP: a sentence that itself retains the hedge passes.
  (5) PROXIMITY WINDOW is real + env-configurable on the production verifier.
  (6) LEXICON is env-driven (LAW VI) on the production verifier.
  (7) REAL VERIFIED-COMPOSE + K-SPAN FALLBACK: driving ``_compose_one_basket`` with a
      deterministic writer that emits the hedge-stripped restatement, the bad
      sentence DROPS and the basket falls back to its own verbatim K-span — which
      RETAINS the qualifier by construction. With the gate OFF, the SAME writer
      output SHIPS the flat restatement (the production certainty-distortion leak).
      A genuinely hedged writer output ships as-is (no over-drop).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.clinical_generator import strict_verify
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)
from src.polaris_graph.generator.verified_compose import (
    _compose_one_basket,
    build_verified_span_draft,
)


# The audited box1 span: a hedged, conditional 46% figure (an epistemic marker —
# "estimates"/"suggest"/"could" — sits within a few tokens of the shared "46%").
_HEDGED_SPAN = (
    "Some estimates suggest 46% of workers could be affected under a "
    "complementary-software scenario."
)
# The certainty-distorted restatement the composer might produce: same VALUE, no hedge.
_STRIPPED_RESTATEMENT = "46% of workers are affected"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Force the entailment leg OFF (no network) and clear any inherited P5 env so
    every test runs against the DEFAULT gate config unless it overrides explicitly."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    for var in (
        "PG_STRICT_VERIFY_QUALIFIER_RETENTION",
        "PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS",
        "PG_STRICT_VERIFY_QUALIFIER_LEXICON",
    ):
        monkeypatch.delenv(var, raising=False)
    strict_verify._qualifier_marker_re.cache_clear()
    yield
    strict_verify._qualifier_marker_re.cache_clear()


def _pool(span: str, eid: str = "evA") -> dict:
    return {eid: {"direct_quote": span, "statement": span}}


def _token(span: str, eid: str = "evA") -> str:
    return f"[#ev:{eid}:0-{len(span)}]"


# ── (1) POSITIVE (RED->GREEN) on verify_sentence_provenance ───────────────────

def test_production_verifier_stripped_qualifier_drops():
    """RED anchor: before the port this passed is_verified=True on the production
    verifier. After the port it drops as ``binding_qualifier_dropped``."""
    span = _HEDGED_SPAN
    sentence = f"{_STRIPPED_RESTATEMENT} {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is False, v.failure_reasons
    assert any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


# ── (2) BYTE-IDENTICAL-OFF kill-switch (the pre-port production leak) ──────────

def test_production_verifier_kill_switch_reverts(monkeypatch):
    """PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 -> the SAME sentence passes on the
    production verifier (byte-identical to the pre-port behavior)."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_RETENTION", "0")
    strict_verify._qualifier_marker_re.cache_clear()
    span = _HEDGED_SPAN
    sentence = f"{_STRIPPED_RESTATEMENT} {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is True, (
        f"gate OFF must revert the production verifier; failure_reasons={v.failure_reasons}"
    )
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


# ── (3) NEGATIVE OVER-FIRE guards on the production verifier ───────────────────

def test_production_negative_bare_count_no_drop():
    """A bare integer count (N=1879) is not a substantive numeral -> no drop."""
    span = "The cohort enrolled N=1879 participants across 12 sites."
    sentence = f"The cohort enrolled 1879 participants across sites {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


def test_production_negative_flat_decimal_no_drop():
    """A flat decimal finding whose span carries no nearby marker -> no drop."""
    span = "HbA1c was reduced by 2.3 points in the treatment arm."
    sentence = f"HbA1c was reduced by 2.3 points in treatment {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is True, v.failure_reasons
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


def test_production_negative_flat_percent_no_drop():
    """A flat percent finding whose span carries no nearby marker -> no drop."""
    span = "Adoption reached 46% of firms in 2024 across the region."
    sentence = f"Adoption reached 46% of firms across the region {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is True, v.failure_reasons
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


# ── (4) SAFE UNDER-DROP: sentence retains a marker ────────────────────────────

def test_production_sentence_retaining_marker_passes():
    """When the sentence keeps a hedge, the qualifier survived -> pass."""
    span = _HEDGED_SPAN
    sentence = f"Approximately 46% of workers could be affected {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is True, v.failure_reasons


# ── (5) PROXIMITY WINDOW is real + env-configurable ───────────────────────────

def test_production_proximity_window_zero_does_not_bind(monkeypatch):
    """window=0 binds a marker only in the numeral's own token -> positive stops firing."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS", "0")
    strict_verify._qualifier_marker_re.cache_clear()
    span = _HEDGED_SPAN
    sentence = f"{_STRIPPED_RESTATEMENT} {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


# ── (6) LEXICON is env-driven (LAW VI) ────────────────────────────────────────

def test_production_custom_lexicon_replaces_default(monkeypatch):
    """A custom lexicon that omits the default markers -> the hedged span no longer fires."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_LEXICON", "wibble,frobnicate")
    strict_verify._qualifier_marker_re.cache_clear()
    span = _HEDGED_SPAN
    sentence = f"{_STRIPPED_RESTATEMENT} {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert not any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


def test_production_custom_lexicon_marker_fires(monkeypatch):
    """The custom marker itself, bound to a shared numeral in the span, DOES fire."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_LEXICON", "wibble,frobnicate")
    strict_verify._qualifier_marker_re.cache_clear()
    span = "The 46% figure is wibble across all reporting firms in 2024."
    sentence = f"The 46% figure holds across all reporting firms {_token(span)}."
    v = verify_sentence_provenance(sentence, _pool(span))
    assert v.is_verified is False, v.failure_reasons
    assert any(
        str(r).startswith("binding_qualifier_dropped") for r in v.failure_reasons
    ), v.failure_reasons


# ── (7) REAL VERIFIED-COMPOSE PATH + K-SPAN FALLBACK ──────────────────────────
#
# Drive the actual composer entry point ``_compose_one_basket`` with a DETERMINISTIC
# writer (no LLM spend). The writer emits the hedge-stripped restatement; the gate
# drops it; the basket falls back to its OWN verbatim K-span, which retains the
# qualifier by construction. This is the execution path Codex flagged (P1).

_EID = "ev_span_1"


def _member(eid: str, span: str):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=span,
        span_verdict="SUPPORTS",
        credibility_weight=1.0,
    )


def _basket(eid: str, span: str):
    return SimpleNamespace(
        supporting_members=[_member(eid, span)],
        subject="AI exposure of the workforce",
        claim_text="AI exposure of the workforce",
    )


def _stripped_writer(basket, scoped_pool) -> str:
    """A deterministic writer standing in for the LLM: it copies the VALUE but drops
    the hedge — the certainty-distortion the gate must catch."""
    return f"{_STRIPPED_RESTATEMENT} {_token(_HEDGED_SPAN, _EID)}."


def _hedged_writer(basket, scoped_pool) -> str:
    """A deterministic writer that KEEPS the hedge — the safe, correct output."""
    return f"Approximately 46% of workers could be affected {_token(_HEDGED_SPAN, _EID)}."


def test_compose_path_drops_stripped_and_falls_back_to_kspan():
    """GREEN: the composer's hedge-stripped draft drops and the basket ships its own
    verbatim K-span (the qualifier is retained). The flat restatement never ships."""
    pool = _pool(_HEDGED_SPAN, _EID)
    basket = _basket(_EID, _HEDGED_SPAN)
    composed = _compose_one_basket(
        basket, pool, writer_fn=_stripped_writer, verify_fn=verify_sentence_provenance,
    )
    # the verbatim K-span retains the hedge ...
    assert "some estimates suggest" in composed.lower(), composed
    assert "could be affected" in composed.lower(), composed
    # ... and the flat certainty-distorted restatement did NOT ship.
    assert not composed.startswith(_STRIPPED_RESTATEMENT), composed
    # the fallback carries the member's own provenance token.
    assert f"[#ev:{_EID}:" in composed, composed


def test_compose_path_kill_switch_ships_stripped_restatement(monkeypatch):
    """RED reproduction on the REAL composer: with the gate OFF, the SAME writer
    output ships the flat restatement — the production certainty-distortion leak the
    default-ON port closes."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_RETENTION", "0")
    strict_verify._qualifier_marker_re.cache_clear()
    pool = _pool(_HEDGED_SPAN, _EID)
    basket = _basket(_EID, _HEDGED_SPAN)
    composed = _compose_one_basket(
        basket, pool, writer_fn=_stripped_writer, verify_fn=verify_sentence_provenance,
    )
    assert composed.startswith(_STRIPPED_RESTATEMENT), (
        f"gate OFF must ship the flat restatement (the leak); got: {composed!r}"
    )


def test_compose_path_hedged_writer_ships_as_is():
    """NEGATIVE-CONTROL: a writer that keeps the hedge ships its own prose (no
    over-drop to the K-span) — a genuine hedged finding is not disturbed."""
    pool = _pool(_HEDGED_SPAN, _EID)
    basket = _basket(_EID, _HEDGED_SPAN)
    composed = _compose_one_basket(
        basket, pool, writer_fn=_hedged_writer, verify_fn=verify_sentence_provenance,
    )
    assert composed.lower().startswith("approximately 46% of workers could be affected"), composed
