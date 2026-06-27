"""I-wire-013 (#1327) iter-3b — offline self-tests for the LANE C quantified silent-no-op canary
and the two iter-3a gate P1 fixes (render-seam ``[#ev:..]`` split + one-letter boundary completion).

Fully offline; every unit under test is PURE.

  * LANE C — ``quantified_silent_no_op_canary``: a quantified block that RAN but did NOT fire
    (verified_sentences=0) yields a machine-assertable signal dict (the caller stamps it as the
    top-level ``manifest.quantified_silent_no_op`` key); a fired block / a non-dict yields None.
  * D-P1-1 — ``_CITATION_SPLIT_RE`` / ``_sanitize_report_line`` now split on the provenance
    ``[#ev:<id>:<start>-<end>]`` token AS WELL as the numeric ``[N]`` marker, so a clean unit cited
    after a dropped chrome unit's ``[#ev:..]`` marker is no longer collateral-dropped. A numeric-only
    line is byte-identical (no regression on the drb_72-style report).
  * D-P1-2 — ``_boundary_token_is_span_cut``: a one-letter boundary token is a cut ONLY when a
    LONGER corpus-word completion exists; a one-letter token with NO completion is preserved.
"""
from __future__ import annotations

from scripts.run_honest_sweep_r3 import quantified_silent_no_op_canary
from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator import weighted_enrichment as we

# corpus vocabulary: "share"/"research"/"methodology" are completions; no word starts with "q".
_KNOWN = {
    "share", "research", "researchers", "methodology", "labor", "market",
    "manufacturing", "routine", "workers",
}


# ── LANE C: quantified silent-no-op canary ───────────────────────────────────
def test_quantified_canary_flags_unfired_block():
    canary = quantified_silent_no_op_canary(
        {"fired": False, "verified_sentences": 0, "firing_status": "parse_error"}
    )
    assert canary is not None
    assert canary["silent_no_op"] is True
    assert canary["fired"] is False
    assert canary["feature"] == "quantified_analysis"
    assert canary["firing_status"] == "parse_error"


def test_quantified_canary_none_when_fired():
    assert quantified_silent_no_op_canary(
        {"fired": True, "verified_sentences": 3}
    ) is None


def test_quantified_canary_none_when_block_absent():
    # no telemetry (block never ran) -> no canary; OFF/byte-identical manifest path.
    assert quantified_silent_no_op_canary(None) is None


def test_quantified_canary_firing_status_falls_back():
    # falls back through quantified_status -> "unknown" when firing_status is absent.
    canary = quantified_silent_no_op_canary({"verified_sentences": 0})
    assert canary is not None and canary["firing_status"] == "unknown"


# ── D-P1-1: render-seam citation splitter handles [#ev:..] + [N] ──────────────
def test_citation_split_re_captures_ev_and_numeric():
    parts = we._CITATION_SPLIT_RE.split("foo[2] bar[#ev:1:2-5] baz")
    assert "[2]" in parts            # numeric marker still captured
    assert "[#ev:1:2-5]" in parts    # provenance marker now captured as ONE segment


def test_sanitize_report_line_ev_split_preserves_following_clean_unit():
    # a glued chrome ToC unit cited with an [#ev:..] token, then a clean [N]-cited finding.
    chrome = "1 Introduction 1.1 Research background to the study 1.2 Methodology"
    clean = "Robots displaced routine workers in manufacturing labor markets."
    out, dropped = we._sanitize_report_line(f"{chrome}[#ev:9:0-3] {clean}[2]", _KNOWN)
    assert dropped >= 1
    assert clean + "[2]" in out                          # clean [N] finding survives the ev-split
    assert "1.1 Research background to the study" not in out  # chrome unit dropped
    assert "[#ev:9:0-3]" not in out                       # its provenance marker dropped with it


def test_sanitize_report_line_numeric_only_is_byte_identical():
    # drb_72 banked report has only [N] -> no regression: byte-identical, nothing dropped.
    line = "Automation reduced the employment-to-population ratio by 0.2 percentage points.[1]"
    out, dropped = we._sanitize_report_line(line, _KNOWN)
    assert out == line and dropped == 0


# ── D-P1-2: one-letter boundary cut requires a corpus-word completion ─────────
def test_one_letter_boundary_with_completion_is_flagged():
    # "s" is absent from the corpus but "share" completes it -> a real span cut.
    assert kf._boundary_token_is_span_cut("s", _KNOWN, mode="end") is True


def test_one_letter_boundary_without_completion_is_not_flagged():
    # "q" has NO longer corpus completion -> a legit one-letter finding, NOT a cut.
    assert kf._boundary_token_is_span_cut("q", _KNOWN, mode="end") is False


def test_one_letter_a_and_i_still_never_flagged():
    # the {a,i} allowlist is preserved even when a completion exists ("about" completes "a").
    assert kf._boundary_token_is_span_cut("a", {"about"}, mode="end") is False
