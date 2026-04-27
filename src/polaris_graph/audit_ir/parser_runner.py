"""Parser runner abstraction (M-11 — Phase B).

Per FINAL_PLAN.md: each upload type needs an extractor that
preserves location-aware provenance. Phase B ships:
  - `ParserRunner` ABC: standard interface for any file type.
  - `TextParser`: real implementation for plain-text uploads
    (.txt / .md). Emits TextSpan provenance.
  - `PdfParser`: stub that raises NotImplementedError until Phase
    C wires PyMuPDF / pdfplumber. Reserved as a placeholder so the
    state machine + API can be exercised end-to-end without
    blocking on the heavy dep.

The abstraction is the deliverable; only TextParser is wired into
the inspector_router for Phase B.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.polaris_graph.audit_ir.provenance import (
    PdfSpan,
    TextSpan,
    UploadProvenance,
    to_dict,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseResult:
    """Output of `ParserRunner.parse`. Each chunk pairs a slice of
    extracted text with its provenance."""

    chunks: tuple[tuple[str, UploadProvenance], ...]


def parse_result_to_chunk_dicts(
    result: ParseResult,
) -> list[tuple[str, dict[str, Any]]]:
    """Convert ParseResult to the (text, provenance_dict) tuples
    that WorkspaceStore.insert_chunks expects."""
    return [(text, to_dict(prov)) for text, prov in result.chunks]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ParserError(Exception):
    """Raised when parsing fails. Caller catches this and
    transitions the upload to status='failed'."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ParserRunner(ABC):
    """One parser per file family. Stateless — instances can be
    shared across requests."""

    parser_id: str  # subclass must set

    @abstractmethod
    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True if this parser handles the given upload."""

    @abstractmethod
    def parse(self, upload_id: str, storage_path: Path) -> ParseResult:
        """Parse the file at `storage_path` into provenance-tagged
        chunks. Raises ParserError on any failure."""


# ---------------------------------------------------------------------------
# TextParser — Phase B real implementation
# ---------------------------------------------------------------------------


# Default chunking parameters. Env-overridable per LAW VI.
DEFAULT_TEXT_CHUNK_CHARS = 1500


class TextParser(ParserRunner):
    """Plain-text parser for .txt / .md uploads.

    Splits the file into fixed-size character chunks. Each chunk
    carries a TextSpan provenance with char offsets relative to the
    full upload text. Chunk size is env-configurable via
    `PG_TEXT_CHUNK_CHARS` (per LAW VI).
    """

    parser_id = "text"

    # Codex M-11 review fix: narrow to plain-text only. Originally
    # any `text/*` MIME claimed by TextParser, which silently
    # absorbed `text/csv` / `text/tab-separated-values` and stored
    # spreadsheet-shaped uploads as TextSpan provenance. M-12 would
    # then need re-upload to get SheetCell. The Phase B safe rule:
    # only accept extensions and MIMEs that are unambiguously plain
    # text. Sheet-like formats fall through to "no parser" → status
    # `pending` until Phase C ships a SheetParser.
    _SUPPORTED_EXT: frozenset[str] = frozenset({".txt", ".md", ".text"})
    _SUPPORTED_MIMES: frozenset[str] = frozenset({
        "text/plain", "text/markdown", "text/x-markdown",
    })

    def __init__(self, chunk_chars: int | None = None) -> None:
        self._chunk_chars = chunk_chars or self._env_chunk_chars()

    @staticmethod
    def _env_chunk_chars() -> int:
        import os
        raw = os.environ.get("PG_TEXT_CHUNK_CHARS")
        if raw is None:
            return DEFAULT_TEXT_CHUNK_CHARS
        try:
            return max(100, int(raw))
        except ValueError:
            return DEFAULT_TEXT_CHUNK_CHARS

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        if content_type and content_type in self._SUPPORTED_MIMES:
            return True
        ext = Path(filename).suffix.lower()
        return ext in self._SUPPORTED_EXT

    def parse(self, upload_id: str, storage_path: Path) -> ParseResult:
        try:
            text = storage_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise ParserError(f"upload file missing: {storage_path}") from exc
        except OSError as exc:
            raise ParserError(f"could not read upload: {exc}") from exc

        if not text:
            return ParseResult(chunks=())

        chunks: list[tuple[str, UploadProvenance]] = []
        n = self._chunk_chars
        for start in range(0, len(text), n):
            end = min(start + n, len(text))
            chunk_text = text[start:end]
            prov = TextSpan(
                upload_id=upload_id, char_start=start, char_end=end,
            )
            chunks.append((chunk_text, prov))
        return ParseResult(chunks=tuple(chunks))


# ---------------------------------------------------------------------------
# PdfParser — Phase B stub
# ---------------------------------------------------------------------------


class PdfParser(ParserRunner):
    """Phase B stub. Phase C will wire a real extractor (PyMuPDF /
    pdfplumber) and emit PdfSpan provenance with page-relative
    char offsets.

    Marked as not-yet-implemented so the upload pipeline can route
    PDFs to operator review rather than silently mis-parsing them.
    """

    parser_id = "pdf"

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        if content_type == "application/pdf":
            return True
        return Path(filename).suffix.lower() == ".pdf"

    def parse(self, upload_id: str, storage_path: Path) -> ParseResult:
        # Reserve the PdfSpan symbol so the schema is reachable even
        # while the parser is stubbed (linters won't drop the import).
        _ = PdfSpan
        raise ParserError(
            "PDF parsing not yet supported in Phase B; the schema reserves "
            "PdfSpan provenance for Phase C M-11.5 (PyMuPDF/pdfplumber)."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_DEFAULT_PARSERS: tuple[ParserRunner, ...] = (TextParser(), PdfParser())


def select_parser(
    filename: str,
    content_type: str | None,
    parsers: tuple[ParserRunner, ...] = _DEFAULT_PARSERS,
) -> ParserRunner | None:
    """Pick the first parser that claims it can handle this upload,
    or None if no registered parser matches."""
    for p in parsers:
        if p.can_handle(filename, content_type):
            return p
    return None
