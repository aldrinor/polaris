"""I-perm-004 (#1198) slice 3 — gap-#18 ACCEPT-path token RE-POINT.

When the bounded local-window rescue accepts a sentence whose narrow cited span did NOT directly
entail, the [#ev] token is RE-POINTED to the genuinely-entailing rescue window (instead of shipping
the original mis-pointed span — the idx-9 "bound to a badge span" bug). Gated by PG_SPAN_RESOLVER
(default OFF -> the claim still passes but the token is unchanged, byte-identical); SINGLE-token only.

The accept SEMANTICS never change (the sentence was already passing via the rescue) — only WHICH span
the surviving token cites. No new pass is created.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.clinical_generator import strict_verify as sv
from src.polaris_graph.generator import provenance_generator as pg


class MarkerJudge:
    """ENTAILS iff the marker substring is in the judged span (NEUTRAL on the narrow span, ENTAILED
    on the wider local content window)."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.marker in span.lower():
            return "ENTAILED", "window grounds the predicate"
        return "NEUTRAL", "narrow span lacks the predicate"


def _install_judge(monkeypatch, judge) -> None:
    monkeypatch.setattr(sv, "_get_judge", lambda: judge)


# Narrow cited span [0-37] = "Regional industry data summary table." -> 2 content words overlap
# (regional, industry) so it clears the content floor and reaches the judge, but lacks the marker
# "structural change" -> NEUTRAL. The wider local content window contains the marker -> ENTAILED.
_ROW = (
    "Regional industry data summary table. "
    "The carbon levy produced structural change in regional industry output."
)
_POOL = {"a": {"direct_quote": _ROW}}
_NARROW_END = len("Regional industry data summary table.")
_SENTENCE = f"Structural change occurred in the regional industry [#ev:a:0-{_NARROW_END}]."


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("PG_VERIFICATION_MODE", "PG_STRICT_VERIFY_ENTAILMENT", "PG_SPAN_RESOLVER"):
        monkeypatch.delenv(var, raising=False)
    yield


def _enforce(monkeypatch):
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, MarkerJudge("structural change"))


def test_rescue_fires_and_accepts(monkeypatch):
    """Sanity: the gap-#18 local-window rescue accepts this sentence (precondition for the test)."""
    _enforce(monkeypatch)
    res = pg.verify_sentence_provenance(_SENTENCE, _POOL)
    assert res.is_verified is True


def test_off_keeps_original_span_byte_identical(monkeypatch):
    """PG_SPAN_RESOLVER OFF: accepted, but the token is UNCHANGED (no re-point)."""
    _enforce(monkeypatch)  # PG_SPAN_RESOLVER left unset
    res = pg.verify_sentence_provenance(_SENTENCE, _POOL)
    assert res.is_verified is True
    assert f"[#ev:a:0-{_NARROW_END}]" in res.sentence  # original narrow span intact
    assert not any(w.startswith("reanchored_local_window:") for w in res.soft_warnings)


def test_on_repoints_token_to_rescue_window(monkeypatch):
    """PG_SPAN_RESOLVER ON: the surviving token is RE-POINTED to the rescue window (a DIFFERENT span
    than the original narrow one) and a `reanchored_local_window:` soft-warning records it."""
    _enforce(monkeypatch)
    monkeypatch.setenv("PG_SPAN_RESOLVER", "1")
    res = pg.verify_sentence_provenance(_SENTENCE, _POOL)
    assert res.is_verified is True
    warn = [w for w in res.soft_warnings if w.startswith("reanchored_local_window:")]
    assert warn, res.soft_warnings
    # The original narrow span is no longer the bound span.
    assert f"[#ev:a:0-{_NARROW_END}]" not in res.sentence
    assert len(res.tokens) == 1
    new_tok = res.tokens[0]
    assert new_tok.evidence_id == "a"
    assert (new_tok.start, new_tok.end) != (0, _NARROW_END)
    # The re-pointed span genuinely contains the marker the judge entailed.
    assert "structural change" in _ROW[new_tok.start:new_tok.end].lower()
