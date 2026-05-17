"""Provenance token format + parser for slice 003 generator output.

Per `.codex/slices/slice_003/architecture_proposal.md` §"provenance.py" and
CLAUDE.md §9.1 invariant 2 ('every generated sentence carries
[#ev:<evidence_id>:<start>-<end>] tokens').

Token format: `[#ev:<source_id>:<start>-<end>]` where:
- source_id is a UUID-shaped string (lowercase hex with optional dashes)
  matching the source_id field of `polaris_graph.retrieval2.evidence_pool.Source`
- start, end are non-negative integer character offsets into the source's
  full_text (or snippet, when full_text is unavailable)
- start <= end is enforced; start == end is allowed for empty-span citations
  (rare but valid for short citations like punctuation marks)

Pure-functions module: no I/O, no LLM, no network. Suitable for fast tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from polaris_graph.retrieval2.evidence_pool import EvidencePool, Source


# Source.source_id defaults to uuid.uuid4() (lowercase hex + dashes) but is
# typed as `str`, so callers may supply any reasonable identifier (e.g.
# 'src-1', 'pubmed_12345'). Token regex accepts the broader alphanumeric
# + dash + underscore form. Bounded to 100 chars so a runaway token can't
# DoS the parser.
PROVENANCE_TOKEN_RE = re.compile(
    r"\[#ev:([A-Za-z0-9_][A-Za-z0-9_\-]{0,99}):(\d+)-(\d+)\]"
)


@dataclass(frozen=True)
class ProvenanceToken:
    """A parsed `[#ev:src:s-e]` token with bounds extracted as ints."""

    source_id: str
    span_start: int
    span_end: int
    raw: str

    def __str__(self) -> str:
        return self.raw


def extract_tokens(sentence: str) -> list[ProvenanceToken]:
    """Find every well-formed provenance token in `sentence`.

    Returns parsed ProvenanceToken instances in left-to-right order. A
    sentence with no tokens returns []. Malformed candidates that LOOK
    like tokens but don't match the regex (e.g. uppercase hex,
    `[#ev:abc:bad-bounds]`) are silently skipped — strict_verify is the
    layer that rejects sentences for missing/invalid tokens.
    """
    out: list[ProvenanceToken] = []
    for match in PROVENANCE_TOKEN_RE.finditer(sentence):
        try:
            start = int(match.group(2))
            end = int(match.group(3))
        except ValueError:
            continue
        out.append(
            ProvenanceToken(
                source_id=match.group(1),
                span_start=start,
                span_end=end,
                raw=match.group(0),
            )
        )
    return out


def strip_tokens(sentence: str) -> str:
    """Return `sentence` with every well-formed token removed.

    Whitespace around removed tokens is collapsed; leading/trailing
    whitespace is stripped. Useful for comparing the human-prose part of
    a sentence against the cited span (per CLAUDE.md §9.1 invariant 3-4).
    """
    stripped = PROVENANCE_TOKEN_RE.sub("", sentence)
    # Collapse internal runs of whitespace introduced by token removal
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def has_any_token(sentence: str) -> bool:
    """True iff at least one well-formed provenance token is present."""
    return PROVENANCE_TOKEN_RE.search(sentence) is not None


# ---------------------------------------------------------------------------
# Validation against EvidencePool
# ---------------------------------------------------------------------------

class TokenValidationError(str):
    """Reason a token failed validation against the pool. Plain string
    enum; used in strict_verify drop_reason mapping."""

    UNKNOWN_SOURCE_ID = "invalid_token"
    SPAN_OUT_OF_RANGE = "span_out_of_range"


def _source_text_length(source: Source) -> int:
    """Return the length of the text the token is allowed to reference.

    Prefers full_text when available; falls back to snippet length.
    """
    if source.full_text is not None:
        return len(source.full_text)
    return len(source.snippet)


def validate_token_against_pool(
    token: ProvenanceToken,
    pool: EvidencePool,
) -> str | None:
    """Validate a single token against the pool.

    Returns:
        None — token is valid (CLAUDE.md §9.1 invariants 1+2 met)
        TokenValidationError.UNKNOWN_SOURCE_ID — source_id not in pool
        TokenValidationError.SPAN_OUT_OF_RANGE — span bounds invalid
    """
    source = _find_source(pool, token.source_id)
    if source is None:
        return TokenValidationError.UNKNOWN_SOURCE_ID

    if token.span_start < 0:
        return TokenValidationError.SPAN_OUT_OF_RANGE
    if token.span_start > token.span_end:
        return TokenValidationError.SPAN_OUT_OF_RANGE

    text_len = _source_text_length(source)
    if token.span_end > text_len:
        return TokenValidationError.SPAN_OUT_OF_RANGE

    return None


def _find_source(pool: EvidencePool, source_id: str) -> Source | None:
    for source in pool.sources:
        if source.source_id == source_id:
            return source
    return None


def get_span_text(token: ProvenanceToken, pool: EvidencePool) -> str | None:
    """Return the text of the cited span, or None if token is invalid.

    Used by strict_verify to compare sentence content against span content.
    Prefers source.full_text; falls back to source.snippet.
    """
    source = _find_source(pool, token.source_id)
    if source is None:
        return None
    text = source.full_text if source.full_text is not None else source.snippet
    if token.span_start < 0 or token.span_end > len(text):
        return None
    return text[token.span_start : token.span_end]
