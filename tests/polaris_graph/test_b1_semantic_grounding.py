"""
Codex round 1 B-1 regression tests: strict_verify must drop non-numeric
claims with no content-word overlap to the cited span.
"""
from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    _content_words,
    strict_verify,
    verify_sentence_provenance,
)


def test_b1_content_word_extraction_removes_stopwords() -> None:
    assert _content_words("the the a and of") == set()
    words = _content_words("Semaglutide improved sleep quality in adults.")
    assert "semaglutide" in words
    assert "improved" in words
    assert "sleep" in words
    assert "quality" in words
    assert "adults" in words
    assert "the" not in words
    assert "in" not in words


def test_b1_unrelated_claim_with_valid_token_dropped() -> None:
    """Codex reproducer: sentence cites a span that contains completely
    different content. Verifier must drop."""
    ev_pool = {
        "ev_a": {
            "direct_quote": (
                "In adults with overweight or obesity, semaglutide 2.4 mg "
                "achieved a mean weight loss of 14.9% at week 68."
            ),
        }
    }
    # Sentence has NO content word in common with the cited span
    sentence = (
        "Blockchain improved agricultural supply chain traceability "
        "[#ev:ev_a:0-50]."
    )
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is False
    assert any("no_content_word_overlap" in r for r in v.failure_reasons)


def test_b1_sleep_quality_fabrication_dropped() -> None:
    """Exact Codex reproducer: 'Semaglutide improved sleep quality' citing
    a span about weight loss."""
    ev_pool = {
        "ev1": {
            "direct_quote": "14.9% weight loss at week 68.",
        }
    }
    # "sleep" and "quality" don't appear in the cited span
    sentence = "Semaglutide improved sleep quality [#ev:ev1:0-20]."
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is False, (
        f"Expected drop, got verified with failures={v.failure_reasons}"
    )


def test_b1_related_claim_with_overlap_still_passes() -> None:
    """A sentence that IS grounded in the span should still pass."""
    ev_pool = {
        "ev_a": {
            "direct_quote": (
                "In adults with obesity, semaglutide produced mean weight "
                "loss of 14.9% at week 68."
            ),
        }
    }
    # ev_a length is 82; use a valid in-bounds span that covers the
    # semaglutide + weight + loss content words.
    sentence = "Semaglutide produced significant weight loss [#ev:ev_a:0-80]."
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is True, (
        f"Expected pass, got failures={v.failure_reasons}"
    )


def test_b1_numeric_sentence_already_verified_not_broken() -> None:
    """Pre-existing numeric check should still work. Adding B-1 shouldn't
    regress numeric-match behavior."""
    ev_pool = {
        "ev_a": {
            "direct_quote": "Mean weight loss was 14.9% at week 68.",
        }
    }
    # Span covers "weight loss was 14.9%" — has content words AND the number
    sentence = "Weight loss was 14.9% [#ev:ev_a:5-26]."
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is True, (
        f"Expected pass, got failures={v.failure_reasons}"
    )


def test_b1_strict_verify_drops_unrelated_sentence() -> None:
    ev_pool = {
        "ev_step1": {
            "direct_quote": "STEP 1 showed 14.9% weight loss at week 68.",
        }
    }
    # span must cover both 14.9 and content words (weight, loss)
    draft = (
        "Weight loss was 14.9% [#ev:ev_step1:14-35]. "
        "Blockchain democratizes supply chains [#ev:ev_step1:0-30]."
    )
    report = strict_verify(draft, ev_pool)
    assert report.total_kept == 1
    assert report.total_dropped == 1
    # The dropped one is the blockchain sentence
    dropped_texts = [sv.sentence for sv in report.dropped_sentences]
    assert any("Blockchain" in s for s in dropped_texts)


def test_b1_env_override_relaxed_overlap() -> None:
    """If PG_PROVENANCE_MIN_CONTENT_OVERLAP=0, the check is effectively
    disabled (but we still require numeric match when applicable)."""
    import importlib
    import os
    os.environ["PG_PROVENANCE_MIN_CONTENT_OVERLAP"] = "0"
    import src.polaris_graph.generator.provenance_generator as mod
    importlib.reload(mod)
    try:
        ev_pool = {
            "ev_a": {"direct_quote": "14.9% weight loss."},
        }
        sentence = "Unrelated claim [#ev:ev_a:0-10]."
        v = mod.verify_sentence_provenance(sentence, ev_pool)
        # With override=0, the content-word check is skipped
        assert v.is_verified is True
    finally:
        del os.environ["PG_PROVENANCE_MIN_CONTENT_OVERLAP"]
        importlib.reload(mod)


# ─────────────────────────────────────────────────────────────────────────
# Codex round 2 re-raised tests: the default threshold must prevent
# single-token-overlap fabrications from passing.
# ─────────────────────────────────────────────────────────────────────────

def test_b1_default_threshold_is_at_least_two() -> None:
    """Codex round 2 re-raise: default=1 was exploitable. Pin default>=2
    so single-noun-overlap fabrications are rejected."""
    import importlib
    import os
    # Ensure no stale env var from a prior test
    os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)
    import src.polaris_graph.generator.provenance_generator as mod
    importlib.reload(mod)
    assert mod.MIN_CONTENT_WORD_OVERLAP >= 2, (
        f"Default MIN_CONTENT_WORD_OVERLAP={mod.MIN_CONTENT_WORD_OVERLAP} is "
        f"too low; Codex round 2 showed <2 lets 'Aspirin reduced pain' "
        f"verify against 'Aspirin caused bleeding' (single overlap='aspirin')."
    )


def test_b1_codex_round2_aspirin_reproducer_rejected() -> None:
    """Exact Codex round 2 reproducer: fabricated predicate sharing
    one anchor noun with cited span must be rejected at default config."""
    import importlib
    import os
    os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)
    import src.polaris_graph.generator.provenance_generator as mod
    importlib.reload(mod)
    ev = {"ev1": {"direct_quote": "Aspirin caused bleeding"}}
    res = mod.verify_sentence_provenance(
        "Aspirin reduced pain [#ev:ev1:0-23].", ev,
    )
    assert res.is_verified is False, (
        "Codex round 2: 'Aspirin reduced pain' must NOT verify against "
        "'Aspirin caused bleeding' (single shared token 'aspirin')"
    )
    assert any("no_content_word_overlap" in r for r in res.failure_reasons)


def test_b1_codex_round2_drug_effective_reproducer_rejected() -> None:
    """The milder Codex round 2 reproducer: 'The drug was effective'
    cited to 'The drug was prescribed' (shared: 'drug'). Must reject."""
    import importlib
    import os
    os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)
    import src.polaris_graph.generator.provenance_generator as mod
    importlib.reload(mod)
    ev = {"ev1": {"direct_quote": "The drug was prescribed"}}
    res = mod.verify_sentence_provenance(
        "The drug was effective [#ev:ev1:0-23].", ev,
    )
    assert res.is_verified is False


def test_b1_overlap_of_two_genuine_content_words_still_passes() -> None:
    """With default=2, a sentence that genuinely shares 2+ content words
    with the span should still pass — we're not over-blocking."""
    import importlib
    import os
    os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)
    import src.polaris_graph.generator.provenance_generator as mod
    importlib.reload(mod)
    ev = {"ev1": {"direct_quote": "Aspirin inhibits platelet aggregation"}}
    # Sentence shares {aspirin, inhibits, platelet} with span — three
    # content words overlap, well above the default of 2.
    res = mod.verify_sentence_provenance(
        "Aspirin inhibits platelet function [#ev:ev1:0-36].", ev,
    )
    assert res.is_verified is True, (
        f"Expected pass, got failures={res.failure_reasons}"
    )
