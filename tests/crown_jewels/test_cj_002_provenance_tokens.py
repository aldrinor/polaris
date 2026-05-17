"""Crown Jewel I-cj-002 — Provenance token format invariant.

Per CLAUDE.md §9.1.2: every generated sentence carries
[#ev:<source_id>:<start>-<end>] tokens. Sentences without valid tokens
are dropped by strict_verify.

These tests are the binding registry: a future PR that weakens the
parser or accepts malformed tokens causes one of these tests to fail
under a clearly named 'test_cj_002_*' identifier.
"""

from __future__ import annotations

from src.polaris_graph.clinical_generator.provenance import (
    extract_tokens,
    has_any_token,
    strip_tokens,
)


def test_cj_002_canonical_format_accepts() -> None:
    tokens = extract_tokens("foo [#ev:src_001:10-25] bar")
    assert len(tokens) == 1
    t = tokens[0]
    assert t.source_id == "src_001"
    assert t.span_start == 10 and t.span_end == 25
    assert t.raw == "[#ev:src_001:10-25]"


def test_cj_002_uuid_shaped_source_id_accepts() -> None:
    tokens = extract_tokens("[#ev:abc-1234-def-5678:0-12]")
    assert len(tokens) == 1 and tokens[0].source_id == "abc-1234-def-5678"


def test_cj_002_multiple_tokens_in_sentence() -> None:
    tokens = extract_tokens("[#ev:s1:0-5] and [#ev:s2:10-20] together")
    assert [(t.source_id, t.span_start, t.span_end) for t in tokens] == [
        ("s1", 0, 5),
        ("s2", 10, 20),
    ]


def test_cj_002_malformed_tokens_rejected() -> None:
    bad = [
        "[#ev:src:abc-def]",
        "[#ev::0-5]",
        "[#xx:src:0-5]",
        "[ev:src:0-5]",
        "[#ev:src:5]",
    ]
    for sentence in bad:
        assert extract_tokens(sentence) == []
        assert not has_any_token(sentence)


def test_cj_002_strip_tokens_removes_all() -> None:
    out = strip_tokens("hello [#ev:s1:0-5] world [#ev:s2:6-11]")
    assert "[#ev:" not in out and "hello" in out and "world" in out


def test_cj_002_no_token_sentence_is_droppable() -> None:
    assert not has_any_token("This claim has no provenance.")
    assert not has_any_token("")
