"""I-cred-008 (Phase 8) — disclosure population. Offline, deterministic, no network.

Uses the REAL SentenceVerification dataclass (the actual population target) with duck-typed tokens."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.provenance_generator import SentenceVerification
from src.polaris_graph.synthesis.disclosure_population import (
    credibility_disclosure_enabled,
    populate_disclosure,
)


def _sv(sentence, eids, is_verified):
    return SentenceVerification(
        sentence=sentence,
        tokens=[SimpleNamespace(evidence_id=e) for e in eids],
        is_verified=is_verified,
    )


# ── AC-1 ──────────────────────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_DISCLOSURE", raising=False)
    assert credibility_disclosure_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_DISCLOSURE", on)
    assert credibility_disclosure_enabled() is True


# ── AC-2: never changes verifier fields; pure (inputs untouched) ─────────────
def test_population_never_changes_verifier_fields_and_is_pure():
    sv = _sv("The rate was 5 percent.", ["e0"], True)
    out = populate_disclosure([sv], {"e0": 0.8}, {"e0": "o1"})
    assert out[0].span_verdict == "SUPPORTS"
    # verifier-owned fields unchanged on the OUTPUT...
    assert out[0].is_verified is True
    assert out[0].sentence == sv.sentence and out[0].tokens == sv.tokens
    # ...and the INPUT sv is NOT mutated (disclosure fields still at their inert defaults).
    assert sv.span_verdict == "" and sv.credibility_weight is None
    assert sv.independent_origin_count is None and sv.certainty_label == ""


# ── AC-3: span_verdict SUPPORTS / UNSUPPORTED ────────────────────────────────
def test_span_verdict_supports_vs_unsupported():
    out = populate_disclosure([_sv("s", ["e0"], True), _sv("s", ["e0"], False)], {}, {})
    assert out[0].span_verdict == "SUPPORTS"
    assert out[1].span_verdict == "UNSUPPORTED"


# ── AC-4: independent_origin_count = distinct origins among cited evidence ────
def test_independent_origin_count():
    one = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o1"})
    assert one[0].independent_origin_count == 1
    two = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o2"})
    assert two[0].independent_origin_count == 2
    unmapped = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1"})
    assert unmapped[0].independent_origin_count == 2  # e1 unmapped -> its own origin


# ── AC-5: credibility_weight = MIN over cited evidence; absent -> None ────────
def test_credibility_weight_min_and_none():
    out = populate_disclosure([_sv("s", ["e0", "e1"], True)], {"e0": 0.9, "e1": 0.3}, {})
    assert abs(out[0].credibility_weight - 0.3) < 1e-9  # weakest cited source
    out2 = populate_disclosure([_sv("s", ["e0"], True)], {}, {})
    assert out2[0].credibility_weight is None


# ── AC-6: certainty buckets; None -> low; env knob ───────────────────────────
def test_certainty_label_buckets(monkeypatch):
    hi = populate_disclosure([_sv("s", ["e0", "e1"], True)],
                             {"e0": 0.9, "e1": 0.9}, {"e0": "o1", "e1": "o2"})
    assert hi[0].certainty_label == "high"
    unknown = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o2"})
    assert unknown[0].certainty_label == "low"  # unknown credibility must NOT inflate certainty
    unverified = populate_disclosure([_sv("s", ["e0"], False)], {"e0": 0.9}, {"e0": "o1"})
    assert unverified[0].certainty_label == "low"
    monkeypatch.setenv("PG_DISCLOSURE_HIGH_CRED", "0.2")
    monkeypatch.setenv("PG_DISCLOSURE_HIGH_MIN_ORIGINS", "1")
    boosted = populate_disclosure([_sv("s", ["e0"], True)], {"e0": 0.3}, {"e0": "o1"})
    assert boosted[0].certainty_label == "high"


# ── AC-7: a sentence with no tokens -> safe defaults, no crash ────────────────
def test_no_tokens_safe_defaults():
    out = populate_disclosure([_sv("s", [], True)], {"e0": 0.9}, {"e0": "o1"})
    assert out[0].span_verdict == "SUPPORTS"
    assert out[0].independent_origin_count == 0
    assert out[0].credibility_weight is None
    assert out[0].certainty_label == "low"
