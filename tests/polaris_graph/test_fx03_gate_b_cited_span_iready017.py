"""I-ready-017 FX-03 (#1107) — the 4-role seam evaluates the cited [start:end] span, not the whole doc.

BUG-02 (confirmed out-of-span false-accept, claim 06-004): the four-role verifier (Sentinel
decomposition + Judge) joined each EvidenceDocument.text as the SPAN the claim is checked against,
but `_resolve_evidence` handed it the WHOLE record text. A claim whose specifics live ANYWHERE in
the document could be graded VERIFIED even when the cited [start:end] window does not support it.

FX-03 slices each EvidenceDocument.text to a BOUNDED window around the cited [start:end] range
(±PG_GATE_B_SPAN_WINDOW_BYTES, default 400) when PG_GATE_B_CITED_SPAN=1 — the same tolerance
strict_verify's local-window rescue uses (ONE shared windowing policy). Bounded (not exact-slice) is
deliberate: it tolerates the 06-004-shape imprecise-but-real citation AND is robust to the
leading-whitespace strip in `_row_text` (token offsets index the raw direct_quote). Flag off
(default) returns the whole text unchanged (byte-identical).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.roles.native_gate_b_inputs import (
    _cited_window_text,
    _resolve_evidence,
)


def _tok(evidence_id: str, start: int, end: int) -> SimpleNamespace:
    return SimpleNamespace(evidence_id=evidence_id, start=start, end=end)


# ---------------------------------------------------------------------------
# _cited_window_text — the windowing primitive
# ---------------------------------------------------------------------------
def test_flag_off_returns_whole_text_byte_unchanged(monkeypatch) -> None:
    monkeypatch.delenv("PG_GATE_B_CITED_SPAN", raising=False)
    full = "x" * 50 + "tirzepatide reduced HbA1c" + "y" * 6000 + "semaglutide raised weight"
    assert _cited_window_text(full, _tok("ev1", 50, 75)) == full


def test_flag_on_window_excludes_far_away_content(monkeypatch) -> None:
    """The §-1.1 anti-false-accept assertion: with the flag on, content 6000 bytes away from the
    cited window is NOT in the span the judge sees, so it cannot support the claim."""
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    monkeypatch.setenv("PG_GATE_B_SPAN_WINDOW_BYTES", "400")
    cited = "tirzepatide reduced HbA1c by about 2 percent"
    full = ("PAD " * 25) + cited + (" FILLER" * 1000) + " semaglutide raised weight elsewhere"
    start = full.index(cited)
    end = start + len(cited)
    win = _cited_window_text(full, _tok("ev1", start, end))
    assert "tirzepatide reduced HbA1c" in win, "cited content must be IN the window"
    assert "semaglutide raised weight" not in win, "far-away content must be EXCLUDED (no false-accept)"
    assert len(win) < len(full)


def test_flag_on_robust_to_leading_whitespace_strip(monkeypatch) -> None:
    """token.start/end index the RAW direct_quote; the record text was _row_text-STRIPPED. A bounded
    window absorbs the leading-strip offset shift so the cited content is still in-window."""
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    monkeypatch.setenv("PG_GATE_B_SPAN_WINDOW_BYTES", "400")
    lead = "   \n  \t  "  # leading whitespace that _row_text.strip() would remove
    cited = "tirzepatide reduced HbA1c by about 2 percent"
    raw = lead + ("PAD " * 30) + cited + (" TAIL" * 2000)
    stripped = raw.strip()  # what record["text"] actually holds
    # token offsets index the RAW text:
    start = raw.index(cited)
    end = start + len(cited)
    win = _cited_window_text(stripped, _tok("ev1", start, end))
    assert "tirzepatide reduced HbA1c" in win, "bounded window must still contain the cited content"


def test_flag_on_degenerate_range_falls_back_to_full(monkeypatch) -> None:
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    full = "tirzepatide reduced HbA1c by about 2 percent in SURPASS-2."
    assert _cited_window_text(full, _tok("ev1", 10, 10)) == full  # end<=start -> fail-safe
    assert _cited_window_text(full, _tok("ev1", 5, 3)) == full


def test_flag_on_window_never_blank(monkeypatch) -> None:
    """A window that would strip to empty falls back to the whole text (never hand the judge blank)."""
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    monkeypatch.setenv("PG_GATE_B_SPAN_WINDOW_BYTES", "0")
    full = "ab    cd"  # indices 2..6 are whitespace
    # window [2:6] over whitespace with W=0 -> strip()='' -> fall back to full (never blank)
    assert _cited_window_text(full, _tok("ev1", 2, 6)) == full


# ---------------------------------------------------------------------------
# _resolve_evidence — per-token windowed EvidenceDocument
# ---------------------------------------------------------------------------
def test_resolve_evidence_windows_per_token_when_on(monkeypatch) -> None:
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    monkeypatch.setenv("PG_GATE_B_SPAN_WINDOW_BYTES", "100")
    cited = "tirzepatide reduced HbA1c"
    full = ("PAD " * 50) + cited + (" FILLER" * 500) + " distant_unrelated_term"
    start = full.index(cited)
    end = start + len(cited)
    lookup = {"ev1": {"text": full}}
    docs, records = _resolve_evidence([_tok("ev1", start, end)], lookup)
    assert len(docs) == 1
    assert "tirzepatide reduced HbA1c" in docs[0].text
    assert "distant_unrelated_term" not in docs[0].text
    assert records[0]["text"] == full  # records keep the FULL record (for entity coverage)


def test_resolve_evidence_whole_doc_when_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_GATE_B_CITED_SPAN", raising=False)
    full = ("PAD " * 50) + "tirzepatide reduced HbA1c" + (" FILLER" * 500) + " distant_term"
    lookup = {"ev1": {"text": full}}
    docs, _ = _resolve_evidence([_tok("ev1", 200, 225)], lookup)
    assert docs[0].text == full.strip() or docs[0].text == full  # off -> whole text (modulo caller strip)


def test_resolve_evidence_unknown_id_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("PG_GATE_B_CITED_SPAN", "1")
    with pytest.raises(ValueError, match="unknown evidence_id"):
        _resolve_evidence([_tok("missing", 0, 10)], {"ev1": {"text": "x" * 50}})
