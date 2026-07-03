"""I-deepfix-001 P5_hedge_preservation (#1344) — the epistemic-QUALIFIER RETENTION gate.

RED→GREEN behavioral proof for the P5 additive gate in ``strict_verify.verify_sentence``.

The composer copies a numeral's VALUE but can drop the epistemic / scope qualifier the
cited span binds to it — "some estimates suggest 46% of workers could be affected under a
complementary-software scenario" restated as a flat "46% of workers are affected". Every
mechanical leg (decimal / percent / overlap) PASSES the stripped restatement and the NLI
leg is systematically lenient to hedge-dropping, so the defect needs its OWN completeness
gate. This mirrors the Wave-2 PERCENT-role machinery: strictly ADDITIVE, default-ON, with a
byte-identical-OFF kill-switch PG_STRICT_VERIFY_QUALIFIER_RETENTION=0.

This suite is fail-loud and proves:

  (1) POSITIVE (RED→GREEN): a span that binds an epistemic marker to a SHARED substantive
      numeral, restated by a sentence carrying NO marker, drops as
      ``binding_qualifier_dropped``. Before the P5 edit this sentence PASSED (True, None) —
      that is the RED anchor.
  (2) BYTE-IDENTICAL-OFF: with PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 the SAME sentence
      reverts to (True, None) — the kill-switch proves the gate is the only new behavior.
  (3) NEGATIVE OVER-FIRE (mandatory calibration guard): plain short findings get NO new
      drop — a bare count ("N=1879"), a flat decimal finding ("HbA1c reduced 2.3 points"),
      and a flat percent finding — because their spans carry no marker near the numeral and
      bare integers are not substantive numerals.
  (4) SAFE UNDER-DROP: when the SENTENCE itself retains a marker, it passes (the hedge
      survived — the safe direction).
  (5) PROXIMITY WINDOW is real and configurable: PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS=0
      binds a marker only in the numeral's own token, so the positive case no longer fires.
  (6) LEXICON is env-driven (LAW VI): a custom PG_STRICT_VERIFY_QUALIFIER_LEXICON replaces the
      default markers — the default markers stop firing and only the custom marker fires.

Pure offline unit test; no network, no model spend (entailment leg forced OFF).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.clinical_generator import strict_verify
from polaris_graph.clinical_generator.strict_verify import verify_sentence
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Pool builders (mirror test_strict_verify.py) ----------

def _src(source_id: str = "src-1", full_text: str = "") -> Source:
    return Source(
        url="https://www.oecd.org/report",
        domain="oecd.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=full_text[:80] or "snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(full_text: str, source_id: str = "src-1") -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=[_src(source_id=source_id, full_text=full_text)],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _token(full_text: str, source_id: str = "src-1") -> str:
    """A whole-span provenance token for `full_text`."""
    return f"[#ev:{source_id}:0-{len(full_text)}]"


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


# The audited box1 span: a hedged, conditional 46% figure.
_HEDGED_SPAN = (
    "Some estimates suggest 46% of workers could be affected under a "
    "complementary-software scenario."
)


# ---------- (1) POSITIVE: the qualifier-stripped restatement drops ----------

def test_stripped_qualifier_restatement_drops():
    """RED anchor: before P5 this passed (True, None). After P5 it drops."""
    pool = _pool(_HEDGED_SPAN)
    sentence = f"46% of workers are affected {_token(_HEDGED_SPAN)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False, "hedge-stripped restatement must be dropped"
    assert reason == "binding_qualifier_dropped", f"got reason={reason!r}"


# ---------- (2) BYTE-IDENTICAL-OFF kill-switch ----------

def test_kill_switch_reverts_byte_identical(monkeypatch):
    """PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 -> the SAME sentence passes."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_RETENTION", "0")
    strict_verify._qualifier_marker_re.cache_clear()
    pool = _pool(_HEDGED_SPAN)
    sentence = f"46% of workers are affected {_token(_HEDGED_SPAN)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"kill-switch OFF must revert; got reason={reason!r}"
    assert reason is None


# ---------- (3) NEGATIVE OVER-FIRE guard (mandatory calibration) ----------

def test_negative_bare_count_no_drop():
    """A bare integer count (N=1879) is not a substantive numeral -> no drop."""
    span = "The cohort enrolled N=1879 participants across 12 sites."
    pool = _pool(span)
    sentence = f"The cohort enrolled 1879 participants across sites {_token(span)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"bare count must not over-fire; got reason={reason!r}"
    assert reason is None


def test_negative_flat_decimal_finding_no_drop():
    """A flat decimal finding whose span carries no nearby marker -> no drop."""
    span = "HbA1c was reduced by 2.3 points in the treatment arm."
    pool = _pool(span)
    sentence = f"HbA1c was reduced by 2.3 points in treatment {_token(span)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"plain decimal finding must not over-fire; got reason={reason!r}"
    assert reason is None


def test_negative_flat_percent_finding_no_drop():
    """A flat percent finding whose span carries no nearby marker -> no drop."""
    span = "Adoption reached 46% of firms in 2024 across the region."
    pool = _pool(span)
    sentence = f"Adoption reached 46% of firms across the region {_token(span)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"plain percent finding must not over-fire; got reason={reason!r}"
    assert reason is None


# ---------- (4) SAFE UNDER-DROP: sentence retains a marker ----------

def test_sentence_retaining_marker_passes():
    """When the sentence keeps a hedge, the qualifier survived -> pass."""
    pool = _pool(_HEDGED_SPAN)
    sentence = (
        f"Approximately 46% of workers could be affected {_token(_HEDGED_SPAN)}."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"retained-hedge sentence must pass; got reason={reason!r}"
    assert reason is None


# ---------- (5) PROXIMITY WINDOW is real + configurable ----------

def test_proximity_window_zero_does_not_bind(monkeypatch):
    """window=0 binds a marker only in the numeral's own token -> positive stops firing."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS", "0")
    strict_verify._qualifier_marker_re.cache_clear()
    pool = _pool(_HEDGED_SPAN)
    sentence = f"46% of workers are affected {_token(_HEDGED_SPAN)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"window=0 must not bind a distant marker; got reason={reason!r}"
    assert reason is None


# ---------- (6) LEXICON is env-driven (LAW VI) ----------

def test_custom_lexicon_replaces_default_markers(monkeypatch):
    """A custom lexicon that omits the default markers -> the hedged span no longer fires."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_LEXICON", "wibble,frobnicate")
    strict_verify._qualifier_marker_re.cache_clear()
    pool = _pool(_HEDGED_SPAN)
    sentence = f"46% of workers are affected {_token(_HEDGED_SPAN)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, (
        f"default markers must not fire under a custom lexicon; got reason={reason!r}"
    )
    assert reason is None


def test_custom_lexicon_marker_fires(monkeypatch):
    """The custom marker itself, bound to a shared numeral in the span, DOES fire."""
    monkeypatch.setenv("PG_STRICT_VERIFY_QUALIFIER_LEXICON", "wibble,frobnicate")
    strict_verify._qualifier_marker_re.cache_clear()
    span = "The 46% figure is wibble across all reporting firms in 2024."
    pool = _pool(span)
    sentence = f"The 46% figure holds across all reporting firms {_token(span)}."
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False, "custom marker bound to a shared numeral must fire"
    assert reason == "binding_qualifier_dropped", f"got reason={reason!r}"
