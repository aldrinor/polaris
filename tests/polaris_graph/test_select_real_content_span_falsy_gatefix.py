"""Fable P2a gate-fix — ``select_real_content_span`` index contract vs a falsy candidate.

The picker filtered falsy spans then returned an index into the FILTERED copy, but the caller
(``live_retriever._build_provenance_quote``) applies that index to its UNFILTERED ``chunks`` list.
A falsy span preceding the real-content span shifted the index, so the caller re-led the
direct_quote with the WRONG chunk (an empty span). The fix returns an index into the ORIGINAL
unfiltered list.

NO network / NO spend / NO GPU: pure predicate. GREEN =
``python -m pytest tests/polaris_graph/test_select_real_content_span_falsy_gatefix.py -q``.
"""
from __future__ import annotations

import src.polaris_graph.retrieval.shell_detector as sd


def test_falsy_candidate_returns_unfiltered_index(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    # A falsy ("") candidate precedes the real-content span. The returned index MUST index the
    # ORIGINAL unfiltered list so the caller lands on the real span, not the shifted furniture one.
    spans = ["CHROME masthead", "", "Real article sentence about robots."]
    idx, span = sd.select_real_content_span(spans)
    assert (idx, span) == (2, "Real article sentence about robots.")
    # The index is valid against the UNFILTERED input the caller reorders.
    assert spans[idx] == span


def test_falsy_candidate_caller_reorder_leads_real_content(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    chunks = ["CHROME masthead", "", "Real article sentence about robots."]
    idx, _ = sd.select_real_content_span(chunks)
    # Reproduce the caller's reorder (live_retriever._build_provenance_quote).
    assert idx > 0
    reordered = [chunks[idx], *chunks[:idx], *chunks[idx + 1:]]
    assert reordered[0] == "Real article sentence about robots."


def test_multiple_falsy_before_real_content(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    spans = ["", "CHROME nav", "", "Real content here."]
    idx, span = sd.select_real_content_span(spans)
    assert (idx, span) == (3, "Real content here.")
    assert spans[idx] == span


def test_all_furniture_with_leading_falsy_signals_no_reorder(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: True)
    # All furniture => fallback to the first NON-FALSY span; index 0 signals "no reorder" (caller
    # gates on ``_idx > 0``) so the all-furniture disclose/down-weight path stays owner.
    idx, span = sd.select_real_content_span(["", "CHROME a", "CHROME b"])
    assert idx == 0
    assert span == "CHROME a"


def test_no_falsy_unchanged_behaviour(monkeypatch):
    # Regression: with no falsy candidate the returned index is unchanged from the legacy contract.
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    spans = ["CHROME masthead", "CHROME nav", "Real article sentence about robots."]
    assert sd.select_real_content_span(spans) == (2, "Real article sentence about robots.")


def test_empty_and_none_inputs():
    assert sd.select_real_content_span([]) == (0, "")
    assert sd.select_real_content_span(None) == (0, "")
