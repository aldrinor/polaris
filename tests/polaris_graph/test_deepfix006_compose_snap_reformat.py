"""I-deepfix-006 F + C3 (#1376) — full-quote-window snap + uncovered-disclosure reformat (verified_compose).

F (PG_FULL_QUOTE_WINDOW_SNAP): the verified-span window is snapped against the row's FULL direct_quote at
window-mining time so a number/word is never cut mid-value (the P0 truncated-number fix). Extend-only
within the same row (a SUPERSET of the verified span), so it stays grounded by construction.

C3 (PG_UNCOVERED_DISCLOSURE_REFORMAT): the intentional "[uncovered supporting evidence for: …]" honest
disclosure is REFORMATTED into human prose at render time — NEVER deleted.
"""
import os

import pytest

from src.polaris_graph.generator import verified_compose as vc


# ── F: full-quote-window snap (PG_FULL_QUOTE_WINDOW_SNAP) ─────────────────────

_HAY = "Task exposure rises to 46% of jobs over the coming decade."


def test_window_end_cut_number_is_completed():
    # The window END lands inside "46%" (cut to "...4") — F must extend it to the whole "46%".
    q = "Task exposure rises to 4"
    start = _HAY.find(q)
    end = start + len(q)
    ns, ne = vc._snap_window_to_whole_value(_HAY, start, end)
    assert _HAY[ns:ne] == "Task exposure rises to 46%"


def test_window_start_cut_number_is_completed():
    # The window START lands inside "46%" (cut to "6% of jobs...") — F must extend back to "46%".
    q = "6% of jobs over the coming decade."
    start = _HAY.find(q)
    end = start + len(q)
    ns, ne = vc._snap_window_to_whole_value(_HAY, start, end)
    assert _HAY[ns:ne].startswith("46% of jobs")


def test_decimal_number_not_cut_mid_value():
    hay = "The share rose to 3.75 percent across the sector."
    q = "The share rose to 3."  # window cuts "3.75" after the "3."
    start = hay.find(q)
    end = start + len(q)
    ns, ne = vc._snap_window_to_whole_value(hay, start, end)
    assert "3.75" in hay[ns:ne]
    assert not hay[ns:ne].rstrip().endswith("3.")


def test_whole_value_window_is_unchanged():
    q = "Task exposure rises to 46%"
    start = _HAY.find(q)
    end = start + len(q)
    assert vc._snap_window_to_whole_value(_HAY, start, end) == (start, end)


def test_word_not_cut_mid_value():
    hay = "Automation reshapes reinstatement of labor markets."
    q = "Automation reshapes reinst"  # cuts the word "reinstatement"
    start = hay.find(q)
    end = start + len(q)
    ns, ne = vc._snap_window_to_whole_value(hay, start, end)
    assert hay[ns:ne].endswith("reinstatement")


def test_window_snap_extension_is_bounded():
    # A pathological run of value chars longer than the cap must NOT extend past the bound.
    hay = "x" + "a" * 500 + " end."
    start, end = 0, 1  # cuts inside the huge token
    ns, ne = vc._snap_window_to_whole_value(hay, start, end)
    assert ne - end <= vc._MAX_WHOLE_VALUE_EXTEND


def test_full_quote_window_snap_default_on():
    os.environ.pop("PG_FULL_QUOTE_WINDOW_SNAP", None)
    assert vc._full_quote_window_snap_enabled() is True
    os.environ["PG_FULL_QUOTE_WINDOW_SNAP"] = "0"
    try:
        assert vc._full_quote_window_snap_enabled() is False
    finally:
        os.environ.pop("PG_FULL_QUOTE_WINDOW_SNAP", None)


# ── C3: uncovered-disclosure reformat (PG_UNCOVERED_DISCLOSURE_REFORMAT) ──────

def test_uncovered_block_reformatted_to_human_prose():
    blk = "[uncovered supporting evidence for: wage effects of automation] Robots cut wages by 0.42%."
    out = vc._reformat_uncovered_disclosure(blk)
    assert not out.startswith("[uncovered supporting evidence for:")
    assert out.startswith("Evidence was retrieved for the following claims but no span met the verification floor:")
    # NEVER deleted — subject + span preserved verbatim.
    assert "wage effects of automation" in out
    assert "Robots cut wages by 0.42%." in out


def test_non_uncovered_disclosure_is_unchanged():
    other = "[verification incomplete: numeric mismatch on one span]"
    assert vc._reformat_uncovered_disclosure(other) == other


def test_render_degraded_disclosures_reformats_uncovered_block():
    blk = "[uncovered supporting evidence for: automation exposure] Exposure reached 46% of tasks."
    out = vc.render_degraded_disclosures("Body prose.", [blk])
    assert "Body prose." in out
    assert "[uncovered supporting evidence for:" not in out
    assert "no span met the verification floor" in out
    assert "Exposure reached 46% of tasks." in out


def test_uncovered_reformat_off_is_byte_identical():
    os.environ["PG_UNCOVERED_DISCLOSURE_REFORMAT"] = "0"
    try:
        blk = "[uncovered supporting evidence for: x] span here."
        assert vc._reformat_uncovered_disclosure(blk) == blk
        assert vc.render_degraded_disclosures("B", [blk]) == "B\n\n" + blk
    finally:
        os.environ.pop("PG_UNCOVERED_DISCLOSURE_REFORMAT", None)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
