"""BUG-M-8 (Codex pass 9): drop degenerate sentence fragments
during resolve_provenance_to_citations so malformed artifacts like
".[4]", "Morgan analysts.[12]", ".[14]" don't appear in released
reports.

Root cause seen in the Novo sweep report: strict_verify kept a
sentence whose meaningful content was lost earlier, leaving only
punctuation + citation. The resolver used to emit those as-is.
"""

from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    resolve_provenance_to_citations,
)


def _sv(sentence, ev_id, start=0, end=50, warnings=None):
    raw = f"[#ev:{ev_id}:{start}-{end}]"
    return SentenceVerification(
        sentence=sentence,
        tokens=[ProvenanceToken(
            evidence_id=ev_id, start=start, end=end, raw=raw,
        )],
        is_verified=True,
        failure_reasons=[],
        soft_warnings=warnings or [],
    )


def _pool():
    return {
        "ev_001": {
            "source_url": "https://example.com/a",
            "tier": "T1",
            "statement": "Some source statement.",
        },
        "ev_002": {
            "source_url": "https://example.com/b",
            "tier": "T4",
            "statement": "Another source.",
        },
    }


def test_bare_citation_fragment_is_dropped():
    """A ".[4]" style fragment with only a token and no content
    words must be dropped by the resolver."""
    kept = [
        _sv("Normal research sentence describing findings [#ev:ev_001:0-50].", "ev_001"),
        _sv(". [#ev:ev_002:0-40]", "ev_002"),  # degenerate
        _sv("Another legitimate observation [#ev:ev_001:0-50].", "ev_001"),
    ]
    text, biblio = resolve_provenance_to_citations(kept, _pool())
    assert ".[2]" not in text, f"bare-citation fragment leaked: {text}"
    assert "describing findings" in text
    assert "legitimate observation" in text


def test_two_word_sentence_is_dropped():
    """A 'Morgan analysts.[12]' style 2-word fragment must be
    dropped. Threshold: need >=3 content words."""
    kept = [
        _sv("First sentence has substantive content [#ev:ev_001:0-50].", "ev_001"),
        _sv("Morgan analysts [#ev:ev_002:0-40].", "ev_002"),  # too short
        _sv("Third sentence describes detailed analysis [#ev:ev_001:0-50].", "ev_001"),
    ]
    text, biblio = resolve_provenance_to_citations(kept, _pool())
    assert "Morgan analysts" not in text, f"2-word fragment leaked: {text}"
    assert "First sentence" in text
    assert "Third sentence" in text


def test_legitimate_short_sentence_survives():
    """Regression guard: legitimate short sentences like 'No
    contradictions detected.' (3 words + 'detected' verb) must
    survive the filter."""
    kept = [
        _sv("No contradictions detected in this analysis [#ev:ev_001:0-50].", "ev_001"),
    ]
    text, biblio = resolve_provenance_to_citations(kept, _pool())
    assert "No contradictions detected" in text, (
        f"legitimate short sentence was dropped: {text}"
    )


def test_limitations_fragment_also_filtered():
    """The same guard applies to limitations-section sentences —
    a degenerate ".[5]" limitations line shouldn't ship either."""
    kept = [
        _sv(
            "The evidence horizon spans 2020 to 2025 [#ev:ev_001:0-50].",
            "ev_001",
            warnings=["limitations_paragraph_pass_through"],
        ),
        _sv(
            ". [#ev:ev_002:0-40]",
            "ev_002",
            warnings=["limitations_paragraph_pass_through"],
        ),
    ]
    text, biblio = resolve_provenance_to_citations(kept, _pool())
    assert "evidence horizon spans" in text
    # Limitations paragraph should not have a bare .[N] artifact
    assert ".[2]" not in text


def test_filter_does_not_affect_bibliography_numbering():
    """When a dropped sentence is the only one citing a given
    evidence_id, that evidence shouldn't wind up in the bibliography
    with a dangling number."""
    kept = [
        _sv("Legitimate research observation at length [#ev:ev_001:0-50].", "ev_001"),
        _sv(". [#ev:ev_002:0-40]", "ev_002"),  # only cites ev_002, degenerate
    ]
    text, biblio = resolve_provenance_to_citations(kept, _pool())
    # Only ev_001 should appear — ev_002's sole citing sentence was dropped
    evidence_ids = {b["evidence_id"] for b in biblio}
    assert "ev_001" in evidence_ids
    assert "ev_002" not in evidence_ids, (
        f"ev_002 should be pruned when its only citing sentence was "
        f"degenerate; got biblio: {biblio}"
    )
