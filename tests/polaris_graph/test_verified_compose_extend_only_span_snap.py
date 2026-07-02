"""I-deepfix-001 FIX-D (truncation) — the EXTEND-ONLY SUPERSET span snap at the span-emit seam.

The rendered defect: a cited span cut mid-clause, e.g.
    "Poland's National Research Institute found that 3.5% of men's jobs in
     high-income countries are defined by the[12]"
— ends on a trailing determiner/preposition with no sentence-final punctuation.

The Codex-approved fix EXTENDS the emitted span forward to the next sentence
boundary IN THE SAME SOURCE ROW (a SUPERSET of the verified span — never shrink,
never fabricate). If it cannot be cleanly extended within the source row, the span
is kept AS-IS (fail-open, never dropped). Because the widened slice is drawn from
the SAME evidence row, the unchanged strict_verify re-verifies it and it stays
grounded. The faithfulness engine (strict_verify / NLI / D8 / provenance) is NEVER
touched — only WHAT TEXT is emitted for the cited span.

This locks BOTH span-emit seams:
  * the pure core ``_snap_span_end_to_sentence`` (the extend-only primitive), and
  * ``build_short_member_sentence`` — the DEFAULT (non-abstractive) section
    producer's primary writer_fn, whose verbatim output is emitted directly (the
    snapped K-span fallback never runs on that path), so it must apply the snap
    itself.

Negative controls (each asserted below):
  (1) a span already ending at a sentence boundary is UNCHANGED;
  (2) the Poland span extends to include its predicate, or (when the source has no
      continuation) stays intact — NEVER truncated mid-"by the";
  (3) the snap never emits text beyond the source span's OWN sentence.
"""
from types import SimpleNamespace

from src.polaris_graph.generator.verified_compose import (
    _ends_at_sentence_boundary,
    _snap_span_end_to_sentence,
    build_short_member_sentence,
)

# The full source-row sentence the extractor cut. The member's verified quote is the
# truncated PREFIX ("... are defined by the"); the row carries the whole sentence plus
# a following sentence (to prove the snap stops at the FIRST boundary, control (3)).
_POLAND_FULL = (
    "Poland's National Research Institute found that 3.5% of men's jobs in high-income "
    "countries are defined by the routine cognitive tasks that automation now performs. "
    "The displacement accelerated after 2015."
)
_POLAND_CUT = (
    "Poland's National Research Institute found that 3.5% of men's jobs in high-income "
    "countries are defined by the"
)
_POLAND_SENTENCE_END = (
    "Poland's National Research Institute found that 3.5% of men's jobs in high-income "
    "countries are defined by the routine cognitive tasks that automation now performs."
)


# ── core primitive: forced-positive ──────────────────────────────────────────

def test_core_snap_extends_trailing_determiner_to_sentence_end():
    # The cut span ends on the determiner "the" with no terminal punctuation.
    end = len(_POLAND_CUT)
    assert not _ends_at_sentence_boundary(_POLAND_FULL, end)
    snapped = _snap_span_end_to_sentence(_POLAND_FULL, 0, end)
    # Extended forward (SUPERSET) to the real sentence end — never left at "by the".
    assert snapped > end
    assert _POLAND_FULL[:snapped] == _POLAND_SENTENCE_END
    # Control (3): stops at the FIRST terminator — never swallows the next sentence.
    assert "displacement accelerated" not in _POLAND_FULL[:snapped]


# ── core primitive: negative controls ────────────────────────────────────────

def test_core_span_already_at_boundary_is_unchanged():
    # Control (1): a span that already ends at a real sentence boundary is untouched.
    text = "Automation displaces labor. New tasks reinstate it."
    end = text.index(" New")  # right after "labor." — a real boundary
    assert _ends_at_sentence_boundary(text, end)
    assert _snap_span_end_to_sentence(text, 0, end) == end


def test_core_fail_open_when_no_continuation_in_source():
    # Control (2)/fail-open: the source row itself ends mid-clause (no terminator to
    # snap to) -> the span is kept AS-IS, never fabricated, never truncated further.
    assert _snap_span_end_to_sentence(_POLAND_CUT, 0, len(_POLAND_CUT)) == len(_POLAND_CUT)


def test_core_never_snaps_a_decimal_to_its_integer_part():
    # Control (3) corollary: a decimal point is NOT a sentence terminator, so "3.5%"
    # is never truncated to "3." by the snap.
    text = "The share rose to 3.5% of all roles across the sector overall."
    end = text.index("3.5%") + len("3.")  # a span that cuts right after "3."
    snapped = _snap_span_end_to_sentence(text, 0, end)
    assert text[:snapped].rstrip().endswith("sector overall.")
    assert "3.5%" in text[:snapped]


# ── integration seam: build_short_member_sentence ────────────────────────────

def _basket(direct_quote: str):
    """A one-member SUPPORTS basket whose member verified quote is ``direct_quote``."""
    member = SimpleNamespace(
        evidence_id="ev_poland",
        direct_quote=direct_quote,
        span_verdict="SUPPORTS",
        credibility_weight=0.9,
    )
    return SimpleNamespace(supporting_members=[member])


def test_emit_seam_extends_cut_member_span_into_source_row():
    # The member's verified quote is the TRUNCATED prefix; the evidence row carries the
    # whole sentence. The default short writer must emit the WIDENED (superset) clause.
    basket = _basket(_POLAND_CUT)
    pool = {"ev_poland": {"direct_quote": _POLAND_FULL}}
    out = build_short_member_sentence(basket, pool)
    assert out, "seam must always release a sentence, never empty"
    # The dangling "defined by the" tail is completed with its predicate.
    assert "routine cognitive tasks that automation now performs" in out
    assert not out.rstrip().split("[#ev:")[0].rstrip().endswith("by the")
    # Control (3): the following sentence is never pulled in.
    assert "displacement accelerated" not in out
    # The provenance token END is widened to match exactly the emitted text (grounded
    # by construction): [#ev:ev_poland:0-<len of the completed sentence>].
    expected_end = len(_POLAND_SENTENCE_END)
    assert f"[#ev:ev_poland:0-{expected_end}]" in out


def test_emit_seam_already_whole_sentence_is_unchanged():
    # Control (1): a member quote that is already a whole sentence emits byte-identically
    # to the pre-snap behavior (token end == first-sentence length, no widening).
    whole = "Automation displaces labor. New tasks reinstate it."
    basket = _basket(whole)
    pool = {"ev_poland": {"direct_quote": whole}}
    out = build_short_member_sentence(basket, pool)
    assert out.startswith("Automation displaces labor [#ev:ev_poland:0-")
    # First sentence is "Automation displaces labor." (len incl. the period).
    first_len = len("Automation displaces labor.")
    assert f"[#ev:ev_poland:0-{first_len}]" in out


def test_emit_seam_fail_open_when_source_row_has_no_continuation():
    # Control (2)/fail-open: the row itself ends mid-clause -> emit the cut span AS-IS
    # (never fabricate a completion), still a valid released sentence with a token.
    basket = _basket(_POLAND_CUT)
    pool = {"ev_poland": {"direct_quote": _POLAND_CUT}}  # row == cut, nothing to snap to
    out = build_short_member_sentence(basket, pool)
    assert out, "fail-open must still release the span, never drop it"
    cut_end = len(_POLAND_CUT)
    assert f"[#ev:ev_poland:0-{cut_end}]" in out
    # No fabricated predicate was appended.
    assert "routine cognitive tasks" not in out
