"""I-deepfix-001 (#1369) DEPTH Step 2 — the D3 fail-closed PROMOTE gate for analyst synthesis.

Proves the safety property that lets the interpretive layer turn on: in PROMOTE mode every
synthesis sentence that is NOT grounded (no resolvable cited span, or the judge says
unsupported, or a judge fault) is DROPPED from the scored body — never rendered as a hedged
claim. In legacy advisory mode (promote OFF) nothing is dropped (byte-identical keep-and-label).
Pure/offline: an injected ``judge_fn`` replaces the Sentinel call; zero network.
"""

import os

import pytest

from src.polaris_graph.generator.analyst_synthesis_deviation_check import (
    screen_synthesis_against_baskets,
)


def _promote_env(monkeypatch, *, deviation: str, promote: str) -> None:
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", deviation)
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", promote)


def test_promote_drops_no_source_sentence(monkeypatch):
    """PROMOTE ON: a synthesis sentence with NO resolvable [N] citation is DROPPED (fail-closed)."""
    _promote_env(monkeypatch, deviation="1", promote="1")
    text = "Automation reshapes labor demand across every skill tier."  # no [N] -> no span
    out, tel = screen_synthesis_against_baskets(
        text, bibliography=[], evidence_rows=[], judge_fn=lambda claim, span: True
    )
    assert "Automation reshapes labor demand" not in out
    assert tel["synthesis_deviation_dropped_count"] == 1
    assert tel["synthesis_deviation_promoted_count"] == 0


def test_promote_drops_when_judge_unsupported(monkeypatch):
    """PROMOTE ON: even a cited sentence is DROPPED when the groundedness judge says unsupported."""
    _promote_env(monkeypatch, deviation="1", promote="1")
    biblio = [{"index": 1, "url": "https://example.org/a", "source_title": "A"}]
    rows = [{
        "evidence_id": "ev1", "url": "https://example.org/a",
        "span_text": "Robots reduced the employment-to-population ratio by 0.2 percentage points.",
    }]
    text = "Robots reduced the employment-to-population ratio by 0.2 percentage points [1]."
    out, tel = screen_synthesis_against_baskets(
        text, bibliography=biblio, evidence_rows=rows, judge_fn=lambda claim, span: False
    )
    # judge=False fails the support leg -> dropped regardless of span overlap
    assert tel["synthesis_deviation_dropped_count"] == 1
    assert tel["synthesis_deviation_promoted_count"] == 0
    assert "0.2 percentage points" not in out


def test_promote_drops_on_judge_fault(monkeypatch):
    """PROMOTE ON: a judge that RAISES fails closed to DROP, never admits the sentence."""
    _promote_env(monkeypatch, deviation="1", promote="1")
    biblio = [{"index": 1, "url": "https://example.org/a", "source_title": "A"}]
    rows = [{"evidence_id": "ev1", "url": "https://example.org/a", "span_text": "some span text here"}]

    def _boom(claim, span):
        raise RuntimeError("judge transport flap")

    text = "A cross-source mechanism links exposure to wage compression [1]."
    out, tel = screen_synthesis_against_baskets(
        text, bibliography=biblio, evidence_rows=rows, judge_fn=_boom
    )
    assert tel["synthesis_deviation_dropped_count"] == 1
    assert "cross-source mechanism" not in out


def test_legacy_advisory_keeps_and_labels(monkeypatch):
    """PROMOTE OFF (legacy): a no-source sentence is KEPT with a marker — nothing is dropped."""
    _promote_env(monkeypatch, deviation="1", promote="0")
    text = "Automation reshapes labor demand across every skill tier."
    out, tel = screen_synthesis_against_baskets(
        text, bibliography=[], evidence_rows=[], judge_fn=lambda claim, span: True
    )
    assert "Automation reshapes labor demand" in out  # kept
    assert tel["synthesis_deviation_dropped_count"] == 0
    assert tel["synthesis_deviation_unresolved_count"] == 1


def test_disabled_is_passthrough(monkeypatch):
    """Deviation check OFF: input returned unchanged, telemetry zeroed."""
    _promote_env(monkeypatch, deviation="0", promote="1")
    text = "Some synthesis sentence [1]."
    out, tel = screen_synthesis_against_baskets(text, bibliography=[], evidence_rows=[])
    assert out == text
    assert tel["synthesis_deviation_dropped_count"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
