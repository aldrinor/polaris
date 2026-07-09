"""Codex+Fable gate-fix P1-4 — furniture-aware span picker WIRED into the direct_quote seam.

``shell_detector.select_real_content_span`` was DEAD CODE (zero production call sites). It is now wired
into ``live_retriever._build_provenance_quote`` (the seam that builds every cited direct_quote) behind
``PG_SPAN_SELECT_FURNITURE_AWARE`` (default OFF). Proof:

  * flag ON + furniture head => the quote LEADS with the real-content span (a furniture span loses),
    and the furniture text is KEPT in the quote body (§-1.3 never a drop);
  * flag OFF (default) => the quote leads with the original head span (byte-identical).

Pure Python, no network / GPU. ``_is_furniture_segment`` is monkeypatched deterministically so the
test does not depend on the render-side chrome predicate's exact thresholds.
"""

from __future__ import annotations

import importlib

import pytest

lr = importlib.import_module("src.polaris_graph.retrieval.live_retriever")
sd = importlib.import_module("src.polaris_graph.retrieval.shell_detector")

_FLAG = "PG_SPAN_SELECT_FURNITURE_AWARE"

# A furniture head (all CHROME, no decimal) longer than head_chars, then real content carrying a
# decimal so _build_provenance_quote emits a SECOND (real-content) chunk after the head.
_FURNITURE_HEAD = (
    "CHROME MASTHEAD CHROME NAVIGATION CHROME DOI 10.1/x CHROME LICENSE CHROME TERMS OF USE CHROME "
)
_REAL_TAIL = (
    "Robots measurably reduced the employment to population ratio by 0.42 percent across many local "
    "labor markets analysed in the study of automation over the period."
)
_CONTENT = _FURNITURE_HEAD + _REAL_TAIL


@pytest.fixture(autouse=True)
def _furniture_predicate(monkeypatch):
    # Deterministic: any segment containing 'CHROME' is furniture; real prose is not.
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: "CHROME" in (s or ""))
    yield


def _quote(**over):
    kwargs = dict(head_chars=60, window_chars=40, max_total_chars=12000, max_windows=20)
    kwargs.update(over)
    return lr._build_provenance_quote(_CONTENT, **kwargs)


def test_flag_off_leads_with_furniture_head_byte_identical(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    q = _quote()
    assert q.startswith("CHROME")          # original head leads => byte-identical (no re-lead)
    assert "0.42 percent" in q             # the decimal window is still present


def test_flag_on_real_content_span_wins(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    q = _quote()
    # A real-content span now LEADS the quote (a furniture span lost the direct_quote).
    assert not q.startswith("CHROME")
    assert q.lstrip().startswith(("Robots", "ment ratio", "0.42")) or "0.42 percent" in q.split("[...]")[0]
    # §-1.3: the furniture text is KEPT in the quote body, never dropped.
    assert "CHROME" in q
    # and it differs from the flag-OFF (byte-identical) quote.
    monkeypatch.delenv(_FLAG, raising=False)
    assert q != _quote()


def test_flag_on_non_furniture_head_unchanged(monkeypatch):
    """Flag ON but the head is real content (picker returns index 0) => chunks unchanged =>
    identical to the flag-OFF quote (minimal blast radius)."""
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: False)  # nothing is furniture
    monkeypatch.setenv(_FLAG, "1")
    on = _quote()
    monkeypatch.delenv(_FLAG, raising=False)
    off = _quote()
    assert on == off


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
