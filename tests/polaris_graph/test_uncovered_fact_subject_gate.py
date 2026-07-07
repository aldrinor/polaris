"""I-deepfix-001 UNIT-5 (#1344) — SYNTH_PRIMARY uncovered-fact SUBJECT/SPAN quality gate.

Forensic (drb_72 report lines 52/63/65): ``_synth_primary_fallback_unit`` shipped marker-less junk
"[uncovered supporting evidence for: {subject}] {span}" blocks whose subject was a lone stopword-ish
token ("because"/"reuse"/"estimate") and whose span was markdown-link / masthead chrome
("13 [blog post](url)..."). The ``PG_UNCOVERED_FACT_SUBJECT_GATE`` (default ON) WITHHOLDS such
disclosures: it ships the real authored body when one survived, else "" so the partition/render drops
the unit. Faithfulness-NEUTRAL (the SOURCE stays in the pool; only whether THIS labeled block renders
changes).

RED before the patch (the junk disclosure ships), GREEN after (it is withheld). Targeted, offline, no
GPU/model (§8.4): every heavy span-derivation helper is monkeypatched to a controlled string.
"""
from __future__ import annotations

import logging
import types

import pytest

from src.polaris_graph.generator import verified_compose


_GATE_ENV = "PG_UNCOVERED_FACT_SUBJECT_GATE"
_PREFIX = "[uncovered supporting evidence for:"


def _basket(subject: str) -> types.SimpleNamespace:
    """Minimal duck-typed basket — the disclosure path only reads ``.subject`` / ``.claim_text``."""
    return types.SimpleNamespace(subject=subject, claim_text=subject, predicate="")


@pytest.fixture
def controlled_span(monkeypatch):
    """Force the SYNTH_PRIMARY fallback span to a caller-chosen string and neutralise the chrome-screen
    path so the raw span reaches the disclosure builder deterministically (isolates THIS gate)."""

    def _install(span: str) -> None:
        monkeypatch.setattr(verified_compose, "_subtopic_decomposition_enabled", lambda: False)
        monkeypatch.setattr(
            verified_compose, "build_verified_span_draft", lambda basket, pool: span
        )
        # Skip _screen_fallback_chrome so on UNPATCHED code the junk span deterministically reaches
        # _uncovered_fact_disclosure (proves RED is the gate, not the pre-existing chrome screen).
        monkeypatch.setattr(verified_compose, "_compose_render_chrome_enabled", lambda: False)

    return _install


def test_stopword_subject_markdown_span_is_withheld(monkeypatch, controlled_span, caplog):
    """(1) subject="because" + span "13 [blog post](http://x)..." -> NO disclosure block emitted, and the
    anti-dark activation marker fires."""
    monkeypatch.delenv(_GATE_ENV, raising=False)  # default ON
    controlled_span("13 [blog post](http://x/renewables) about the estimate")
    basket = _basket("because")
    with caplog.at_level(logging.INFO, logger=verified_compose.logger.name):
        result = verified_compose._synth_primary_fallback_unit(basket, {}, body="")
    assert _PREFIX not in result
    assert result == ""  # no body survived -> render drops the unit
    assert any(
        "[activation] uncovered_fact_subject_gate" in rec.getMessage() for rec in caplog.records
    )


def test_real_subject_substantive_span_still_discloses(monkeypatch, controlled_span):
    """(2) real multi-word subject + substantive span -> disclosure IS emitted (no regression)."""
    monkeypatch.delenv(_GATE_ENV, raising=False)  # default ON
    controlled_span(
        "Global renewable energy capacity expanded across multiple regions during the reporting period."
    )
    basket = _basket("renewable energy adoption")
    result = verified_compose._synth_primary_fallback_unit(basket, {}, body="")
    assert _PREFIX in result
    assert "renewable energy adoption" in result


def test_gate_off_is_byte_identical(monkeypatch, controlled_span):
    """(3) gate OFF -> byte-identical legacy emission (the junk disclosure still ships)."""
    monkeypatch.setenv(_GATE_ENV, "0")
    span = "13 [blog post](http://x/renewables) about the estimate"
    controlled_span(span)
    basket = _basket("because")
    result = verified_compose._synth_primary_fallback_unit(basket, {}, body="")
    legacy = verified_compose._uncovered_fact_disclosure(basket, span)
    assert result == legacy
    assert _PREFIX in result
