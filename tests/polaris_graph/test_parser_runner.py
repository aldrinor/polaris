"""Tests for src/polaris_graph/audit_ir/parser_runner.py (M-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.parser_runner import (
    DEFAULT_TEXT_CHUNK_CHARS,
    ParserError,
    PdfParser,
    TextParser,
    parse_result_to_chunk_dicts,
    select_parser,
)
from src.polaris_graph.audit_ir.provenance import TextSpan


# ---------------------------------------------------------------------------
# TextParser
# ---------------------------------------------------------------------------


def test_text_parser_can_handle_plain_text() -> None:
    p = TextParser()
    assert p.can_handle("notes.txt", "text/plain") is True
    assert p.can_handle("notes.md", "text/markdown") is True
    assert p.can_handle("by_extension.txt", None) is True
    assert p.can_handle("by_extension.md", None) is True
    assert p.can_handle("doc.pdf", "application/pdf") is False


def test_text_parser_rejects_csv_and_tsv() -> None:
    """Codex M-11 review fix: TextParser must NOT accept sheet-like
    formats (text/csv, text/tab-separated-values). Those need
    SheetCell provenance, not TextSpan, so the Phase B safe rule
    is to leave them as 'no parser' → status pending until Phase
    C ships a SheetParser."""
    p = TextParser()
    assert p.can_handle("data.csv", "text/csv") is False
    assert p.can_handle("data.tsv", "text/tab-separated-values") is False
    # By extension only — same rejection.
    assert p.can_handle("data.csv", None) is False
    assert p.can_handle("data.tsv", None) is False


def test_text_parser_rejects_unrecognized_text_mime() -> None:
    """text/anything should NOT auto-claim — only the explicit
    plain-text MIME allowlist routes through TextParser."""
    p = TextParser()
    assert p.can_handle("ambiguous", "text/anything") is False
    assert p.can_handle("page.html", "text/html") is False


@pytest.mark.parametrize(
    "mime",
    [
        "text/plain; charset=utf-8",
        "text/plain;charset=ascii",
        "text/markdown; charset=utf-8",
        "text/x-markdown ; charset=us-ascii",
        "TEXT/PLAIN; CHARSET=UTF-8",  # case-insensitive
    ],
)
def test_text_parser_accepts_parameterized_plain_text_mimes(mime: str) -> None:
    """Codex M-11 v2 review fix: real upload headers often include
    "; charset=..." parameters. Exact-match rejected those legitimate
    plain-text uploads."""
    p = TextParser()
    assert p.can_handle("notes.txt", mime) is True


def test_text_parser_emits_text_span_chunks(tmp_path: Path) -> None:
    p = TextParser(chunk_chars=10)
    f = tmp_path / "x.txt"
    f.write_text("hello world this is a longer text", encoding="utf-8")
    result = p.parse(upload_id="up_1", storage_path=f)
    assert len(result.chunks) > 1
    for text, prov in result.chunks:
        assert isinstance(prov, TextSpan)
        assert prov.upload_id == "up_1"
        assert prov.char_end - prov.char_start == len(text)


def test_text_parser_chunk_offsets_are_contiguous(tmp_path: Path) -> None:
    p = TextParser(chunk_chars=5)
    f = tmp_path / "x.txt"
    f.write_text("abcdefghijklmnop", encoding="utf-8")  # 16 chars
    result = p.parse("up_1", f)
    offsets = [(prov.char_start, prov.char_end) for _, prov in result.chunks]
    # First chunk starts at 0; each subsequent chunk picks up where
    # the previous left off; last chunk ends at len(text).
    assert offsets[0][0] == 0
    for (_, prev_end), (curr_start, _) in zip(offsets, offsets[1:]):
        assert curr_start == prev_end
    assert offsets[-1][1] == 16


def test_text_parser_empty_file_returns_no_chunks(tmp_path: Path) -> None:
    p = TextParser()
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    result = p.parse("up_1", f)
    assert result.chunks == ()


def test_text_parser_missing_file_raises_parser_error(tmp_path: Path) -> None:
    p = TextParser()
    with pytest.raises(ParserError, match="missing"):
        p.parse("up_1", tmp_path / "nope.txt")


def test_text_parser_chunk_chars_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PG_TEXT_CHUNK_CHARS", "200")
    p = TextParser()
    assert p._chunk_chars == 200


def test_text_parser_chunk_chars_garbage_env_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("PG_TEXT_CHUNK_CHARS", "garbage")
    p = TextParser()
    assert p._chunk_chars == DEFAULT_TEXT_CHUNK_CHARS


# ---------------------------------------------------------------------------
# PdfParser stub
# ---------------------------------------------------------------------------


def test_pdf_parser_can_handle_pdfs() -> None:
    p = PdfParser()
    assert p.can_handle("doc.pdf", "application/pdf") is True
    assert p.can_handle("doc.PDF", None) is True
    assert p.can_handle("doc.txt", "text/plain") is False


def test_pdf_parser_raises_not_yet_supported(tmp_path: Path) -> None:
    """Phase B stub: PDF parsing must FAIL LOUD per LAW II so the
    operator sees 'not supported' rather than an empty parse."""
    p = PdfParser()
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.4 stub")
    with pytest.raises(ParserError, match="not yet supported"):
        p.parse("up_1", f)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_select_parser_picks_text_for_text_files() -> None:
    p = select_parser("notes.txt", "text/plain")
    assert isinstance(p, TextParser)


def test_select_parser_picks_pdf_for_pdf_files() -> None:
    p = select_parser("doc.pdf", "application/pdf")
    assert isinstance(p, PdfParser)


def test_select_parser_returns_none_for_unsupported() -> None:
    p = select_parser("video.mp4", "video/mp4")
    assert p is None


# ---------------------------------------------------------------------------
# parse_result_to_chunk_dicts helper
# ---------------------------------------------------------------------------


def test_parse_result_to_chunk_dicts_round_trip(tmp_path: Path) -> None:
    p = TextParser(chunk_chars=20)
    f = tmp_path / "x.txt"
    f.write_text("the quick brown fox jumps", encoding="utf-8")
    result = p.parse("up_1", f)
    dicts = parse_result_to_chunk_dicts(result)
    assert len(dicts) == len(result.chunks)
    for (text, prov_dict) in dicts:
        assert isinstance(text, str)
        assert prov_dict["kind"] == "text_span"
        assert prov_dict["upload_id"] == "up_1"
