"""Strict verifier per CLAUDE.md §9.1 invariant 3.

Per-sentence check enforcing:
  (a) at least one provenance token present
  (b) every token references an evidence_id in the pool
  (c) span bounds are valid (0 <= start <= end <= len(text))
  (d) every decimal in the sentence appears in the cited spans
  (e) sentence and span share >= MIN_CONTENT_OVERLAP content words

Returns a (verifier_pass: bool, drop_reason: str | None) pair, or directly
constructs a VerifiedSentence for use by the generator orchestrator.

Pure-functions module: no I/O, no LLM, no network.

Tunables (read at call time so tests can override):
  PG_PROVENANCE_MIN_CONTENT_OVERLAP — minimum shared content words (default 2)
"""

from __future__ import annotations

import os
import re

from polaris_graph.generator2.provenance import (
    ProvenanceToken,
    extract_tokens,
    get_span_text,
    strip_tokens,
    validate_token_against_pool,
)
from polaris_graph.generator2.verified_report import (
    DropReason,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DEFAULT_MIN_CONTENT_OVERLAP = 2

# Minimal English stopword list. Strict-verify's content-word overlap should
# count substantive vocabulary, not function words. This is intentionally
# small — the rule is conservative ("at least 2 shared content words")
# so even a short stoplist yields the right behavior.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "with", "as", "by", "from", "into", "through", "during",
    "before", "after", "above", "below", "between", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "should", "could", "may",
    "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "their", "there", "they", "them", "we", "us", "our", "you",
    "your", "i", "me", "my", "he", "she", "his", "her",
})

_DECIMAL_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")


def _min_overlap_threshold() -> int:
    raw = os.environ.get("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "")
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MIN_CONTENT_OVERLAP


def _content_words(text: str) -> set[str]:
    """Lowercase content words (>=3 chars, not stopwords) from `text`."""
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _STOPWORDS
    }


def _decimals(text: str) -> set[str]:
    """Numeric tokens (integers + decimals) from `text`."""
    return {m.group(0) for m in _DECIMAL_RE.finditer(text)}


# ---------------------------------------------------------------------------
# Per-sentence verifier
# ---------------------------------------------------------------------------

def verify_sentence(
    sentence_text: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
) -> tuple[bool, DropReason | None]:
    """Return (verifier_pass, drop_reason) for `sentence_text` against `pool`.

    Pass: returns (True, None).
    Fail: returns (False, drop_reason) with reason from DropReason literal.

    Implements CLAUDE.md §9.1 invariant 3 in order:
      1. at least one well-formed token        → no_provenance_token
      2. every token references known source_id → invalid_token
      3. spans within source bounds            → span_out_of_range
      4. every decimal in sentence in spans    → numeric_mismatch
      5. >=N shared content words              → overlap_too_low
    """
    threshold = (
        min_content_overlap
        if min_content_overlap is not None
        else _min_overlap_threshold()
    )

    tokens = extract_tokens(sentence_text)
    if not tokens:
        return False, "no_provenance_token"

    # Validate each token against the pool. Collect span texts for
    # later numeric + overlap checks.
    span_texts: list[str] = []
    for token in tokens:
        reason = validate_token_against_pool(token, pool)
        if reason == "invalid_token":
            return False, "invalid_token"
        if reason == "span_out_of_range":
            return False, "span_out_of_range"
        # Token valid — fetch its span text
        span = get_span_text(token, pool)
        if span is None:
            # Belt-and-suspenders: token validated but get_span_text said no.
            return False, "span_out_of_range"
        span_texts.append(span)

    sentence_clean = strip_tokens(sentence_text)
    combined_span = " ".join(span_texts)

    # Decimal match: every decimal in sentence must appear in the combined
    # span text. Permits the spans to contain MORE decimals than the
    # sentence cites — that's fine; the constraint is one-way.
    sentence_decimals = _decimals(sentence_clean)
    span_decimals = _decimals(combined_span)
    if not sentence_decimals.issubset(span_decimals):
        return False, "numeric_mismatch"

    # Content-word overlap
    sentence_words = _content_words(sentence_clean)
    span_words = _content_words(combined_span)
    overlap = len(sentence_words & span_words)
    if overlap < threshold:
        return False, "overlap_too_low"

    return True, None


def verify_sentence_to_record(
    sentence_text: str,
    section_id: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
) -> VerifiedSentence:
    """Convenience: wrap verify_sentence into a VerifiedSentence record.

    Used by the generator orchestrator to build Section.verified_sentences.
    """
    passed, reason = verify_sentence(
        sentence_text, pool, min_content_overlap=min_content_overlap
    )
    tokens = [t.raw for t in extract_tokens(sentence_text)]
    return VerifiedSentence(
        section_id=section_id,
        sentence_text=sentence_text,
        provenance_tokens=tokens,
        verifier_pass=passed,
        drop_reason=reason,
    )


# ---------------------------------------------------------------------------
# Section-level rollup
# ---------------------------------------------------------------------------

def section_pass_rate(sentences: list[VerifiedSentence]) -> float:
    """Fraction of sentences that passed verify, in [0.0, 1.0].

    Empty list returns 0.0 (vacuously below any threshold).
    """
    if not sentences:
        return 0.0
    passed = sum(1 for s in sentences if s.verifier_pass)
    return passed / len(sentences)
