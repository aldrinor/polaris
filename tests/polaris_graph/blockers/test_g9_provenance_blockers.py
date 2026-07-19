"""Blocker tests for provenance-generator token/empty-sentence honesty.

Forensic findings (dual Claude+Codex 2026-06-12, drb_72 ; tracker
`.codex/I-bench-veracity-003-forensic/BLOCKER_TRACKER.md`):

I-pipe-015 (#1240) — malformed cross-ref tokens silently dropped. The
fact_dedup rewrite prompt example (cross-file, fact_dedup.py:411) lacks the
leading '#', so the model emits `[ev:<id>:<start>-<end>]` instead of the
canonical `[#ev:<id>:<start>-<end>]`. `_PROVENANCE_TOKEN_RE` requires the '#',
so these tokens vanished with no telemetry — a dropped citation lost silently.
FIX (kill-switch default-ON, PG_PROVENANCE_TOKEN_HONEST_DROP=0 reverts): a
malformed-but-recognizable token is either canonicalized to `[#ev:...]` (then
run through the SAME full validation) OR counted as a dropped-malformed token —
NEVER silently lost. Canonicalization only fixes the bracket FORMAT; it never
bypasses the evidence-id / span / numeric / content-overlap / entailment checks.

I-pipe-016 (#1241) — content-empty sentences counted as verified (telemetry
inflation). The lightweight splitter emits orphaned citation-only fragments as
their own "sentence"; the Limitations PASS-THROUGH branch counted them as
is_verified=True, inflating the verified numerator AND total_in denominator.
FIX (default-ON, PG_PROVENANCE_SKIP_EMPTY=0 reverts): a content-empty sentence
is excluded from BOTH numerator and denominator. This does NOT change which
REAL sentences pass strict_verify.

These tests assert:
  (a) flag-OFF == current behavior (identity) for both fixes.
  (b) `[ev:..]` malformed token canonicalized to `[#ev:..]` (not silently lost),
      AND a valid-id wrong-bracket token, once canonicalized, STILL passes the
      full validation (canonicalization does not bypass any check).
  (c) an unfixable `[ev:...]` attempt is COUNTED as dropped-malformed (telemetry),
      never silent.
  (d) a content-empty sentence is excluded from the verified count.
  (e) a REAL verified sentence still counts.
  (f) faithfulness is untouched — a token that fails the real evidence-id/span
      check is STILL dropped even after bracket canonicalization.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import provenance_generator as pg
from src.polaris_graph.generator.provenance_generator import (
    _canonicalize_malformed_ev_tokens,
    _is_content_empty_sentence,
    get_token_honesty_telemetry,
    parse_provenance_tokens,
    reset_token_accounting_telemetry,
    strict_verify,
    verify_sentence_provenance,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    reset_token_accounting_telemetry()
    yield
    reset_token_accounting_telemetry()


def _pool() -> dict[str, dict[str, object]]:
    # direct_quote long enough that span 0-58 is in-bounds and shares >=2
    # content words ("semaglutide", "weight", "loss") with the sentence.
    return {
        "ev_a": {
            "direct_quote": (
                "Semaglutide produced clinically meaningful weight loss across "
                "the treated cohort in the trial."
            ),
            "statement": "Semaglutide weight-loss finding.",
            "source_url": "https://example.org/a",
            "tier": "T1",
        }
    }


# ─────────────────────────────────────────────────────────────────────────
# I-pipe-015 (#1240) — malformed token honesty
# ─────────────────────────────────────────────────────────────────────────

def test_malformed_ev_token_canonicalized_not_silent():
    """`[ev:id:s-e]` (no '#') is rewritten to canonical `[#ev:id:s-e]` and the
    canonical token is now parseable — the citation is NOT silently lost."""
    s = "Semaglutide produced weight loss [ev:ev_a:0-58]."
    # Before: the canonical parser sees nothing.
    assert parse_provenance_tokens(s) == []
    out = _canonicalize_malformed_ev_tokens(s)
    assert "[#ev:ev_a:0-58]" in out
    assert "[ev:ev_a:0-58]" not in out
    toks = parse_provenance_tokens(out)
    assert len(toks) == 1
    assert toks[0].evidence_id == "ev_a"
    assert toks[0].start == 0 and toks[0].end == 58
    tel = get_token_honesty_telemetry()
    assert tel["malformed_canonicalized"] == 1
    assert tel["malformed_dropped"] == 0


def test_valid_id_wrong_bracket_still_passes_full_validation():
    """A valid-id wrong-bracket token, once canonicalized, STILL goes through
    the full verifier and PASSES on a genuinely-supporting span. Canonicalizing
    the bracket does not bypass validation — it only stops the silent loss."""
    pool = _pool()
    # entailment off keeps the test hermetic (no NLI/network); strict_verify's
    # numeric + content-overlap + span checks are unchanged.
    canon = _canonicalize_malformed_ev_tokens(
        "Semaglutide produced weight loss [ev:ev_a:0-58]."
    )
    v = verify_sentence_provenance(canon, pool, require_number_match=True)
    assert v.is_verified is True


def test_wrong_bracket_invalid_span_STILL_DROPS():
    """Faithfulness lock: bracket canonicalization NEVER accepts a token that
    fails the real span check. An out-of-bounds span still fails verification."""
    pool = _pool()
    canon = _canonicalize_malformed_ev_tokens(
        "Semaglutide produced weight loss [ev:ev_a:0-99999]."
    )
    v = verify_sentence_provenance(canon, pool, require_number_match=True)
    assert v.is_verified is False
    assert any("span_out_of_bounds" in f for f in v.failure_reasons)


def test_unfixable_ev_attempt_counted_dropped_not_silent():
    """A recognizable `[ev:...]` attempt that cannot be canonicalized (no span)
    is COUNTED as dropped-malformed — it is not silently ignored."""
    out = _canonicalize_malformed_ev_tokens("A claim with a broken ref [ev:abc].")
    # unfixable: left in place (not a valid token), but counted.
    assert "[ev:abc]" in out
    tel = get_token_honesty_telemetry()
    assert tel["malformed_canonicalized"] == 0
    assert tel["malformed_dropped"] == 1


def test_canonical_token_untouched_and_uncounted():
    """A canonical `[#ev:...]` token is never matched/rewritten/counted."""
    s = "Semaglutide produced weight loss [#ev:ev_a:0-58]."
    out = _canonicalize_malformed_ev_tokens(s)
    assert out == s
    tel = get_token_honesty_telemetry()
    assert tel["malformed_canonicalized"] == 0
    assert tel["malformed_dropped"] == 0


def test_flag_off_malformed_token_silently_dropped_identity(monkeypatch):
    """OFF (PG_PROVENANCE_TOKEN_HONEST_DROP=0): strict_verify does NOT
    canonicalize — the malformed token stays unrecognized (legacy silent drop),
    and the telemetry counters are untouched (byte-identical to pre-#1240)."""
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "0")
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    draft = "Semaglutide produced weight loss [ev:ev_a:0-58]."
    rep = strict_verify(draft, pool, require_number_match=True)
    # Malformed token invisible -> no provenance token -> sentence dropped.
    assert rep.total_kept == 0
    assert rep.total_dropped == 1
    tel = get_token_honesty_telemetry()
    assert tel["malformed_canonicalized"] == 0
    assert tel["malformed_dropped"] == 0


def test_flag_on_malformed_token_recovered_in_strict_verify(monkeypatch):
    """ON (default): strict_verify canonicalizes the malformed token so a real
    supporting citation is recovered and the sentence verifies."""
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "1")
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    draft = "Semaglutide produced weight loss [ev:ev_a:0-58]."
    rep = strict_verify(draft, pool, require_number_match=True)
    assert rep.total_kept == 1
    assert rep.total_dropped == 0
    tel = get_token_honesty_telemetry()
    assert tel["malformed_canonicalized"] == 1


# ─────────────────────────────────────────────────────────────────────────
# I-pipe-016 (#1241) — content-empty sentence honesty
# ─────────────────────────────────────────────────────────────────────────

def test_is_content_empty_detector():
    """Helper: token-only / punctuation residue is content-empty; a sentence
    with a content word or a number is NOT."""
    assert _is_content_empty_sentence("[#ev:ev_a:0-58]") is True
    assert _is_content_empty_sentence("[#ev:ev_a:0-58] [#ev:ev_b:0-5]") is True
    assert _is_content_empty_sentence("   ") is True
    assert _is_content_empty_sentence("Semaglutide reduced weight.") is False
    assert _is_content_empty_sentence("The value was 14.9 percent.") is False
    # A numbered citation marker `[1]` carries a number, so it is NOT treated as
    # content-empty (conservative: never exclude something that has a number).
    assert _is_content_empty_sentence(".[1]") is False


def test_empty_sentence_excluded_from_verified_count(monkeypatch):
    """ON (default): a content-empty Limitations pass-through fragment is
    excluded from BOTH numerator (kept) and denominator (total_in)."""
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "1")
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    # One real limitations sentence + one orphaned token-only fragment.
    draft = (
        "Limitations: The corpus skews toward tier T1 sources. [#ev:ev_a:0-58]"
    )
    rep = strict_verify(draft, pool, require_number_match=True)
    # The orphaned token fragment is excluded; only the real limitations
    # sentence remains in the count.
    kept_texts = [sv.sentence for sv in rep.kept_sentences]
    assert any("corpus skews" in t for t in kept_texts)
    assert all(t.strip() != "[#ev:ev_a:0-58]" for t in kept_texts)
    # denominator excludes the empty fragment.
    assert rep.total_in == rep.total_kept + rep.total_dropped
    assert rep.total_kept == 1


def test_flag_off_empty_sentence_still_counted_identity(monkeypatch):
    """OFF (PG_PROVENANCE_SKIP_EMPTY=0): the content-empty pass-through fragment
    is counted as verified again (legacy behavior, byte-identical to pre-#1241)."""
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "0")
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    draft = (
        "Limitations: The corpus skews toward tier T1 sources. [#ev:ev_a:0-58]"
    )
    rep = strict_verify(draft, pool, require_number_match=True)
    # OFF: the orphaned fragment is counted in BOTH total_in and kept.
    kept_texts = [sv.sentence for sv in rep.kept_sentences]
    assert any(t.strip() == "[#ev:ev_a:0-58]" for t in kept_texts)
    assert rep.total_kept == 2
    assert rep.total_in == 2


def test_real_verified_sentence_still_counts(monkeypatch):
    """A real sentence with content (and provenance) still counts as verified
    under the default-ON flags — the empty-skip never drops a real sentence."""
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "1")
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    draft = "Semaglutide produced weight loss [#ev:ev_a:0-58]."
    rep = strict_verify(draft, pool, require_number_match=True)
    assert rep.total_kept == 1
    assert rep.total_dropped == 0
    assert rep.total_in == 1


def test_empty_skip_does_not_change_real_drop(monkeypatch):
    """A REAL but unsupported sentence is still DROPPED (not silently excluded)
    under the empty-skip flag — the flag excludes only content-empty noise."""
    monkeypatch.setenv("PG_PROVENANCE_SKIP_EMPTY", "1")
    monkeypatch.setenv("PG_PROVENANCE_TOKEN_HONEST_DROP", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool()
    # Number 88.8 is NOT in the cited span -> real drop, not an exclusion.
    draft = "Semaglutide produced 88.8 percent weight loss [#ev:ev_a:0-58]."
    rep = strict_verify(draft, pool, require_number_match=True)
    assert rep.total_kept == 0
    assert rep.total_dropped == 1
    assert rep.total_in == 1
