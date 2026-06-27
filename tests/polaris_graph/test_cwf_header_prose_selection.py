"""I-wire-014 (#1334) FIX-A — CWF corroboration header renders a real claim sentence /
clean source title, never a clm_<hash> or a broken 2-word stub.

Pins the header-selection chain in scripts/run_honest_sweep_r3.py against small fixtures
mirroring the real bibliography.json shapes that produced the 154/155 hash-dump defect.
"""
import pytest

from scripts.run_honest_sweep_r3 import (
    _complete_sentence_prefix,
    _best_corroboration_header,
    _title_candidate_is_renderable,
)


# ── _complete_sentence_prefix ────────────────────────────────────────────────

def test_complete_sentence_prefix_strips_doc_label_and_returns_first_sentence():
    raw = "Abstract We study the staggered introduction of a generative AI assistant. Access to AI assis"
    out = _complete_sentence_prefix(raw)
    assert out.startswith("We study the staggered introduction")
    assert out.endswith("AI assistant.")
    assert "Access to AI assis" not in out  # the truncated tail is dropped


def test_complete_sentence_prefix_empty_when_no_complete_sentence():
    # END-truncated single clause, no sentence-final punctuation
    raw = "We present a framework for understanding the effects of automation and use it to interpret changes in "
    assert _complete_sentence_prefix(raw) == ""


def test_complete_sentence_prefix_midword_start_yields_nothing():
    assert _complete_sentence_prefix("usand workers reduces the ratio by 0.2 percentage points") != \
        "usand workers reduces the ratio by 0.2 percentage points"  # a complete sentence here is fine
    # a genuinely fragmentary start with no sentence end:
    assert _complete_sentence_prefix("hodology to estimate the probability of computerisation for jobs") == ""


def test_complete_sentence_prefix_does_not_treat_ellipsis_as_sentence_end():
    # #1334 Codex P1: a clause terminated by a truncation marker must NOT yield a header.
    assert _complete_sentence_prefix("This representative span is incomplete and cut ...") == ""
    assert _complete_sentence_prefix("A clause cut mid thought …") == ""
    # an internal ellipsis glued before a real sentence must not produce a marker-bearing header
    out = _complete_sentence_prefix("fragment ... Then a full clean sentence appears here clearly.")
    assert "..." not in out


def test_complete_sentence_prefix_does_not_split_on_abbreviation():
    raw = "Adoption reached 35.9% of U.S. workers by 2025 and rose further the next year. Tail tail tail"
    out = _complete_sentence_prefix(raw)
    # must NOT cut at "U.S." — the first real sentence ends at "next year."
    assert "U.S. workers" in out
    assert out.endswith("the next year.")


# ── _title_candidate_is_renderable ───────────────────────────────────────────

def test_title_renderable_accepts_noun_phrase_title():
    assert _title_candidate_is_renderable("Robots and Jobs: Evidence from US Labor Markets") is True


def test_title_renderable_rejects_lowercase_slug():
    assert _title_candidate_is_renderable("fourth_industrial_revolution_framing") is False


# ── _best_corroboration_header (the full chain) ──────────────────────────────

def _basket(claim_text="", members=None, subject="", predicate="", ccid="clm_deadbeef"):
    return {
        "claim_cluster_id": ccid,
        "claim_text": claim_text,
        "subject": subject,
        "predicate": predicate,
        "supporting_members": members or [],
    }


def test_header_prefers_complete_sentence_from_claim_text():
    bk = _basket(
        claim_text="We study the staggered introduction of a generative AI assistant. Access to AI assis",
    )
    h = _best_corroboration_header(bk, statement="Some Source Title")
    assert h.startswith("We study the staggered introduction")
    assert "clm_" not in h


def test_header_falls_back_to_member_quote_sentence():
    bk = _basket(
        claim_text="usand workers reduces the ratio by ",  # midword start, no sentence
        members=[{"member_tier": "ENTAILMENT_VERIFIED",
                  "direct_quote": "One more robot per thousand workers reduces the employment ratio by 0.2 points."}],
    )
    h = _best_corroboration_header(bk, statement="")
    assert h.startswith("One more robot per thousand workers")


def test_header_falls_back_to_source_title_with_trailing_ellipsis_stripped():
    bk = _basket(claim_text="hodology to estimate the probability of ")  # no sentence
    h = _best_corroboration_header(
        bk, statement="A systematic review of Artificial Intelligence and Automation ..."
    )
    assert h == "A systematic review of Artificial Intelligence and Automation"
    assert "clm_" not in h and "..." not in h


def test_header_never_returns_hash_when_a_title_exists():
    bk = _basket(claim_text="", ccid="clm_abc123")
    h = _best_corroboration_header(bk, statement="The Future of Employment")
    assert "clm_abc123" not in h
    assert h == "The Future of Employment"


def test_header_returns_empty_only_when_truly_titleless():
    bk = _basket(claim_text="atch out mid word", members=[], subject="", predicate="")
    h = _best_corroboration_header(bk, statement="")
    assert h == ""  # caller applies the subject+predicate/ccid last resort


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
