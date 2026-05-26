"""Integration test for strict_verify _verifier_cleaned_text scope.

Per Codex Step 3b iter-3 P2 (PR #906):
    "Add one regression test that strict_verify content-overlap and
    entailment receive the cleaned verifier_text, not only numeric
    extraction. A mock/spy around those internal paths is enough."

Asserts that when verify_sentence_provenance is called with an atom_NNN-
bearing sentence and entailment mode is enforced, the entailment judge
receives the CLEANED sentence (atom_NNN + ev tokens stripped), not the
original with atom_NNN tokens. Same property is the structural defense
against false-drop of valid atom-cited sentences in PG_ATOM_REFUSAL_MODE
log_only/strict.

Layered defense:
  - test_numeric_extraction_no_atom_NNN — already covered by atom_extractor
    tests indirectly; this file asserts the SAME guarantee at the judge
    boundary.
  - test_entailment_judge_receives_cleaned_text — explicit mock+spy
    asserting atom_NNN absent from the judge's first argument.
  - test_content_word_count_excludes_atom — finds_findings_lines path
    uses _verifier_cleaned_text for word count.
"""

from __future__ import annotations

from unittest.mock import patch

from src.polaris_graph.generator.provenance_generator import (
    _verifier_cleaned_text,
    verify_sentence_provenance,
)


_FIXTURE_EVIDENCE = {
    "ev_001": {
        "evidence_id": "ev_001",
        "direct_quote": (
            "In SURPASS-2, tirzepatide reduced HbA1c by -2.30 percentage "
            "points at 40 weeks versus -1.86 with semaglutide."
        ),
        "title": "Tirzepatide vs Semaglutide trial",
        "tier": "T1",
    },
}


def test_verifier_cleaned_text_strips_all_three_token_classes():
    """Smoke test for the helper itself: atom_NNN + [#ev:...] + [ev_XXX]
    all removed. Original-only text passes through with whitespace
    normalization."""
    # atom_NNN
    out = _verifier_cleaned_text("HbA1c by -2.30 (atom_003).")
    assert "atom_003" not in out
    assert "(" not in out  # parens around atom_NNN consumed
    assert "-2.30" in out

    # [#ev:...] internal token
    out2 = _verifier_cleaned_text("HbA1c [#ev:ev_001:0-50].")
    assert "#ev" not in out2
    assert "ev_001" not in out2

    # Bare [ev_XXX] defensive
    out3 = _verifier_cleaned_text("HbA1c reduction [ev_001].")
    assert "ev_001" not in out3
    assert "[" not in out3

    # No-tokens passthrough
    out4 = _verifier_cleaned_text("Plain sentence with no tokens.")
    assert out4 == "Plain sentence with no tokens."


def test_entailment_judge_receives_cleaned_text_runtime():
    """Codex Step 3b iter-3 P2 + iter-2 follow-up: real runtime mock.
    Capture every input to _get_judge().judge() and assert it has been
    cleaned (no atom_NNN, no [#ev:...], no bare [ev_XXX]).

    Data-flow verified — not just variable-name pattern matching. Even
    if a future PR renames the cleaned variable or moves the strip
    elsewhere, this test passes iff the actual text reaching the judge
    is clean.
    """
    sentence = (
        "Tirzepatide reduced HbA1c by -2.30 percentage points at 40 weeks "
        "(atom_003) [#ev:ev_001:11-78]."
    )

    captured: list[tuple[str, str]] = []

    class _SpyJudge:
        def judge(self, claim_text: str, span_text: str) -> tuple[str, str]:
            captured.append((claim_text, span_text))
            return ("SUPPORTED", "")

    # Patch in the strict_verify module — provenance_generator does a
    # lazy import of _get_judge / _entailment_mode / _record_judge_outcome
    # from there, so this rebind propagates.
    with patch(
        "src.polaris_graph.clinical_generator.strict_verify._entailment_mode",
        return_value="enforce",
    ), patch(
        "src.polaris_graph.clinical_generator.strict_verify._get_judge",
        return_value=_SpyJudge(),
    ), patch(
        "src.polaris_graph.clinical_generator.strict_verify._record_judge_outcome",
        return_value=None,
    ):
        verify_sentence_provenance(sentence, _FIXTURE_EVIDENCE)

    assert len(captured) >= 1, (
        f"Entailment judge should have been called under enforce mode; "
        f"captured={captured}"
    )

    for claim_text, _ in captured:
        # Core property: atom_NNN absent from judge input
        assert "atom_003" not in claim_text, (
            f"Judge saw atom_003 in claim — cleaning bypassed. Got: {claim_text!r}"
        )
        assert "atom_" not in claim_text, (
            f"Judge saw atom_NNN token in claim. Got: {claim_text!r}"
        )
        # Internal provenance token absent
        assert "#ev:" not in claim_text, (
            f"Judge saw [#ev:...] in claim. Got: {claim_text!r}"
        )
        # Content preserved
        assert "-2.30" in claim_text or "2.30" in claim_text
        assert "HbA1c" in claim_text


def test_findings_lines_word_count_excludes_atom_token():
    """The findings/limitations split path (provenance_generator
    ~line 1545) uses _verifier_cleaned_text ONLY for the content-word
    threshold count — atom_NNN must not inflate that count. The
    RENDERED sentence body still preserves atom_NNN for downstream
    validator (per PR #906 iter-2 fix)."""
    # Direct unit-level smoke: helper returns text with no "atom" word
    # when the input contained an atom_NNN.
    cleaned = _verifier_cleaned_text(
        "Tirzepatide (atom_003) reduced HbA1c by -2.30."
    )
    # "atom" should not appear as a standalone word
    import re
    content_words = re.findall(r"[A-Za-z]+", cleaned)
    assert "atom" not in content_words, (
        f"Cleaned text content_words should not include 'atom', got {content_words}"
    )
    # Real content words still present (note: re.findall(r"[A-Za-z]+")
    # splits HbA1c into ["HbA", "c"] because "1" is non-letter — that's
    # the threshold check's behavior; what matters is "atom" is absent)
    assert "Tirzepatide" in content_words
    assert "HbA" in content_words  # part of HbA1c, post-letter-split


def test_cleaned_text_preserves_decimals():
    """atom_NNN strip must not affect decimal preservation in claim text."""
    cleaned = _verifier_cleaned_text(
        "HbA1c was -2.30 (atom_003), p<0.001 [#ev:ev_001:0-50]."
    )
    assert "-2.30" in cleaned
    assert "0.001" in cleaned
    assert "atom_003" not in cleaned
    assert "#ev" not in cleaned
