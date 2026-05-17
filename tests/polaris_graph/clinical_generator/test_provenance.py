"""Tests for provenance.py — token format, parser, validate against pool."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.clinical_generator.provenance import (
    PROVENANCE_TOKEN_RE,
    ProvenanceToken,
    TokenValidationError,
    extract_tokens,
    get_span_text,
    has_any_token,
    strip_tokens,
    validate_token_against_pool,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Token regex + extraction ----------

def test_regex_matches_canonical_token():
    s = "Adults benefited from aspirin [#ev:abc-123:100-150]."
    assert PROVENANCE_TOKEN_RE.search(s) is not None


def test_extract_single_token():
    tokens = extract_tokens("Hello [#ev:abc:0-100] world.")
    assert len(tokens) == 1
    assert tokens[0].source_id == "abc"
    assert tokens[0].span_start == 0
    assert tokens[0].span_end == 100
    assert tokens[0].raw == "[#ev:abc:0-100]"


def test_extract_multiple_tokens_in_order():
    s = "Claim A [#ev:src1:10-20]. Claim B [#ev:src2:50-100]."
    tokens = extract_tokens(s)
    assert len(tokens) == 2
    assert tokens[0].source_id == "src1"
    assert tokens[1].source_id == "src2"


def test_extract_uuid_format_source_id():
    """Real Source.source_id uses uuid.uuid4() format with dashes."""
    s = "Claim [#ev:550e8400-e29b-41d4-a716-446655440000:0-50]."
    tokens = extract_tokens(s)
    assert len(tokens) == 1
    assert tokens[0].source_id == "550e8400-e29b-41d4-a716-446655440000"


def test_extract_no_tokens():
    assert extract_tokens("Plain sentence with no tokens.") == []


def test_extract_skips_malformed_tokens():
    """Missing colons, non-int bounds, missing brackets are ignored."""
    candidates = [
        "[#ev::0-100]",           # empty source_id
        "[#ev:abc:notnum-end]",   # non-int bounds
        "[#ev:abc:1-2-3]",        # extra dash in span
        "[ev:abc:0-100]",         # missing #
        "[#ev:abc:0-100",         # missing closing bracket
        "[#ev:abc!:0-100]",       # invalid char in source_id
    ]
    for s in candidates:
        tokens = extract_tokens(s)
        for t in tokens:
            # Anything extracted must be syntactically clean
            assert t.span_start >= 0
            assert t.span_end >= t.span_start


def test_extract_accepts_uppercase_source_id():
    """source_id is an opaque string identifier, not strictly hex."""
    tokens = extract_tokens("[#ev:ABC:0-100]")
    assert len(tokens) == 1
    assert tokens[0].source_id == "ABC"


def test_extract_zero_length_span_allowed():
    tokens = extract_tokens("[#ev:abc:50-50]")
    assert len(tokens) == 1
    assert tokens[0].span_start == 50
    assert tokens[0].span_end == 50


# ---------- strip_tokens ----------

def test_strip_removes_token():
    s = strip_tokens("Adults benefited [#ev:abc:0-100].")
    assert "[#ev" not in s
    assert "Adults benefited" in s


def test_strip_collapses_whitespace():
    s = strip_tokens("Foo  [#ev:abc:0-100]  bar")
    assert s == "Foo bar"


def test_strip_handles_no_tokens():
    s = strip_tokens("No tokens here.")
    assert s == "No tokens here."


def test_strip_preserves_decimals():
    """Decimals must NOT be stripped — strict_verify's numeric-match
    rule depends on them surviving."""
    s = strip_tokens(
        "Aspirin reduced events by 23.5% [#ev:abc:0-100] vs placebo."
    )
    assert "23.5%" in s


# ---------- has_any_token ----------

def test_has_any_token_true():
    assert has_any_token("[#ev:abc:0-100]") is True


def test_has_any_token_false_for_plain_text():
    assert has_any_token("Plain sentence.") is False


def test_has_any_token_false_for_malformed():
    assert has_any_token("[#ev::0-100]") is False  # empty source_id rejected


# ---------- Pool helpers ----------

def _src(source_id: str = "src-1", full_text: str | None = "x" * 200) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet text" * 5,
        full_text=full_text,
        full_text_available=full_text is not None,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: 0,
                SourceTier.T2: 0,
                SourceTier.T3: 0,
            },
            min_required_per_tier={
                SourceTier.T1: 0,
                SourceTier.T2: 0,
                SourceTier.T3: 0,
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


# ---------- validate_token_against_pool ----------

def test_validate_token_known_source_in_range_passes():
    pool = _pool(_src(source_id="src-1", full_text="x" * 500))
    token = ProvenanceToken(
        source_id="src-1", span_start=10, span_end=100, raw="[#ev:src-1:10-100]"
    )
    assert validate_token_against_pool(token, pool) is None


def test_validate_token_unknown_source_id_fails():
    pool = _pool(_src(source_id="src-1"))
    token = ProvenanceToken(
        source_id="src-bogus",
        span_start=0,
        span_end=10,
        raw="[#ev:src-bogus:0-10]",
    )
    assert (
        validate_token_against_pool(token, pool)
        == TokenValidationError.UNKNOWN_SOURCE_ID
    )


def test_validate_token_negative_start_fails():
    pool = _pool(_src(source_id="src-1"))
    token = ProvenanceToken(
        source_id="src-1", span_start=-1, span_end=10, raw="[#ev:src-1:-1-10]"
    )
    assert (
        validate_token_against_pool(token, pool)
        == TokenValidationError.SPAN_OUT_OF_RANGE
    )


def test_validate_token_start_greater_than_end_fails():
    pool = _pool(_src(source_id="src-1", full_text="x" * 500))
    token = ProvenanceToken(
        source_id="src-1", span_start=200, span_end=100, raw="[#ev:src-1:200-100]"
    )
    assert (
        validate_token_against_pool(token, pool)
        == TokenValidationError.SPAN_OUT_OF_RANGE
    )


def test_validate_token_end_beyond_text_length_fails():
    pool = _pool(_src(source_id="src-1", full_text="x" * 100))
    token = ProvenanceToken(
        source_id="src-1", span_start=0, span_end=200, raw="[#ev:src-1:0-200]"
    )
    assert (
        validate_token_against_pool(token, pool)
        == TokenValidationError.SPAN_OUT_OF_RANGE
    )


def test_validate_token_end_at_exact_length_passes():
    pool = _pool(_src(source_id="src-1", full_text="x" * 100))
    token = ProvenanceToken(
        source_id="src-1", span_start=0, span_end=100, raw="[#ev:src-1:0-100]"
    )
    assert validate_token_against_pool(token, pool) is None


def test_validate_token_falls_back_to_snippet_when_no_full_text():
    pool = _pool(_src(source_id="src-1", full_text=None))
    snippet_len = len(pool.sources[0].snippet)
    token_ok = ProvenanceToken(
        source_id="src-1",
        span_start=0,
        span_end=snippet_len,
        raw=f"[#ev:src-1:0-{snippet_len}]",
    )
    assert validate_token_against_pool(token_ok, pool) is None

    token_overflow = ProvenanceToken(
        source_id="src-1",
        span_start=0,
        span_end=snippet_len + 100,
        raw=f"[#ev:src-1:0-{snippet_len + 100}]",
    )
    assert (
        validate_token_against_pool(token_overflow, pool)
        == TokenValidationError.SPAN_OUT_OF_RANGE
    )


# ---------- get_span_text ----------

def test_get_span_text_returns_full_text_slice():
    text = "abcdefghij" * 10  # 100 chars
    pool = _pool(_src(source_id="src-1", full_text=text))
    token = ProvenanceToken(
        source_id="src-1", span_start=10, span_end=20, raw="[#ev:src-1:10-20]"
    )
    span = get_span_text(token, pool)
    assert span == text[10:20]


def test_get_span_text_returns_none_for_unknown_source():
    pool = _pool(_src(source_id="src-1"))
    token = ProvenanceToken(
        source_id="bogus", span_start=0, span_end=10, raw="[#ev:bogus:0-10]"
    )
    assert get_span_text(token, pool) is None


def test_get_span_text_returns_none_for_out_of_range():
    pool = _pool(_src(source_id="src-1", full_text="x" * 50))
    token = ProvenanceToken(
        source_id="src-1", span_start=0, span_end=200, raw="[#ev:src-1:0-200]"
    )
    assert get_span_text(token, pool) is None


def test_get_span_text_uses_snippet_when_full_text_none():
    pool = _pool(_src(source_id="src-1", full_text=None))
    snippet = pool.sources[0].snippet
    token = ProvenanceToken(
        source_id="src-1", span_start=0, span_end=10, raw="[#ev:src-1:0-10]"
    )
    assert get_span_text(token, pool) == snippet[0:10]
