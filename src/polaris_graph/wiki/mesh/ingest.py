"""
Mesh ingest — the L1 write path.

Takes uploaded files or web-fetched content, extracts clean text, writes
it to `workspace_dir/sources/{src_id}.md`, and inserts a `source_pages`
row via the MeshStore. After this module runs, the claim extractor
(`claim_extract.py`) can read the markdown and turn it into L2 claims.

Design (per advisor CP-A):
  - File I/O happens OUTSIDE the transaction context. Write the markdown
    first, insert the row second. If the insert fails, an orphan file is
    harmless — next ingest of the same content (same hash → same src_id →
    same filename) is idempotent. If the file write fails, no row is
    inserted, so the mesh is never left in a "row exists but file
    missing" state.
  - Dedup happens via content_hash BEFORE writing anything new. Same
    content → return existing src_id without touching disk twice.
  - `_extract_text` dispatches on file suffix. PDF uses docling,
    HTML/HTM uses trafilatura, markdown/text are read as UTF-8.
  - Unsupported formats raise MeshStoreError. No silent fallbacks (LAW II).

Return signature: (src_id, was_new) so callers can tell dedup hits
from fresh inserts without a second query.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

from .store import MeshStore, MeshStoreError

logger = logging.getLogger(__name__)


# ───── constants ─────

# Minimum extracted-text length. Anything below this is treated as a
# corrupt/empty source and rejected loudly — upstream is expected to fix
# the input, not have the mesh silently accept garbage.
MIN_EXTRACTED_TEXT_LEN = 50

_SUPPORTED_SUFFIXES = frozenset({
    ".pdf", ".html", ".htm", ".md", ".markdown", ".txt",
})

# The header written into every ingested markdown file. Char offsets
# recorded in the mesh (claims.char_start / claims.char_end) are relative
# to the SOURCE BODY — the text AFTER this header — NOT the raw file
# bytes. Downstream code (claim_extract, drill-down tools) must call
# `read_source_text()` to get the body, not `Path.read_text()` directly.
# If they use raw file reads, every offset will be shifted by the header
# length and provenance drill-down will point at the wrong paragraph.
_HEADER_TERMINATOR = "-->\n\n"


# ───── public API ─────

def ingest_file(
    store: MeshStore,
    *,
    workspace_id: str,
    file_path: str | Path,
    kind: str = "upload",
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    venue: str | None = None,
    sig_authority: float | None = None,
    url: str | None = None,
) -> tuple[str, bool]:
    """
    Ingest a single file into the workspace mesh.

    Returns (src_id, was_new). `was_new=False` means the file's content
    (by sha256 hash) was already present — the existing src_id is returned
    and no disk write happened.

    Parameters:
        store           — open MeshStore for the target workspace
        workspace_id    — workspace that owns this source
        file_path       — filesystem path to the file to ingest
        kind            — 'upload' (default), 'web', or 'api'
        sig_authority   — authority score 0..1. If None, defaults to 0.95
                          for uploads, 0.5 for everything else.
        title/authors/year/doi/venue — optional metadata recorded on the
                          source_page row. Callers should pass whatever
                          the upstream parser (e.g. PDF metadata) provides.
        url             — optional original URL for non-upload sources

    Raises MeshStoreError on:
        - missing file
        - unsupported file extension
        - text extraction failure
        - extracted text shorter than MIN_EXTRACTED_TEXT_LEN
        - invalid workspace_id
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise MeshStoreError(f"Ingest file not found: {file_path}")
    if file_path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise MeshStoreError(
            f"Unsupported file extension: {file_path.suffix!r}. "
            f"Supported: {sorted(_SUPPORTED_SUFFIXES)}"
        )

    if store.get_workspace(workspace_id) is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")

    # 1. Extract text (may raise)
    text = _extract_text(file_path)
    if len(text) < MIN_EXTRACTED_TEXT_LEN:
        raise MeshStoreError(
            f"Extracted text too short ({len(text)} chars < {MIN_EXTRACTED_TEXT_LEN}). "
            f"Source likely corrupt or empty: {file_path}"
        )
    word_count = len(text.split())

    # 2. Hash the cleaned text
    content_hash = _compute_content_hash(text)

    # 3. Dedup — if the same content was already ingested, return early
    existing = store.source_id_by_hash(workspace_id, content_hash)
    if existing is not None:
        logger.info(
            "ingest_file dedup hit: %s already in workspace %s as %s",
            file_path.name, workspace_id, existing,
        )
        return existing, False

    # 4. Default sig_authority if not provided
    if sig_authority is None:
        sig_authority = 0.95 if kind == "upload" else 0.5
    if not (0.0 <= sig_authority <= 1.0):
        raise MeshStoreError(
            f"sig_authority must be in [0, 1], got {sig_authority}"
        )

    # 5. Compute the src_id deterministically — must match what the store
    #    will compute inside insert_source, so the on-disk filename lines
    #    up with the row id. This is the same formula as _make_id in
    #    store.py (prefix + sha256[:16] of f"{workspace_id}:{content_hash}").
    src_id = _predicted_src_id(workspace_id, content_hash)

    # 6. Write the markdown file BEFORE the row insert. An orphan file is
    #    harmless (same hash → same filename on next ingest); a row without
    #    a file is not.
    sources_dir = store.sources_dir
    sources_dir.mkdir(parents=True, exist_ok=True)
    md_path = _write_source_markdown(
        sources_dir=sources_dir,
        src_id=src_id,
        text=text,
        original_name=file_path.name,
    )
    relative_path = str(md_path.relative_to(store.workspace_dir)).replace("\\", "/")

    # 7. Insert the row. If this races another process and loses, fall
    #    back to the existing row's id.
    try:
        actual_src_id = store.insert_source(
            workspace_id=workspace_id,
            kind=kind,
            filepath=relative_path,
            content_hash=content_hash,
            sig_authority=sig_authority,
            title=title or _default_title(file_path, text),
            url=url,
            authors=authors,
            year=year,
            doi=doi,
            venue=venue,
            word_count=word_count,
        )
    except MeshStoreError as e:
        # Race: another writer got in between the dedup check and our
        # insert. Re-query and use whichever id won.
        if "already exists" in str(e):
            existing2 = store.source_id_by_hash(workspace_id, content_hash)
            if existing2 is not None:
                return existing2, False
        raise

    # The predicted and actual src_ids should match because both use the
    # same deterministic formula — verify loudly if they don't. A mismatch
    # means store._make_id changed and ingest.py wasn't updated in sync.
    if actual_src_id != src_id:
        logger.error(
            "src_id mismatch: predicted=%s, actual=%s — renaming markdown file",
            src_id, actual_src_id,
        )
        new_path = sources_dir / f"{actual_src_id}.md"
        md_path.rename(new_path)

    return actual_src_id, True


def ingest_web_content(
    store: MeshStore,
    *,
    workspace_id: str,
    url: str,
    raw_content: str,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    venue: str | None = None,
    sig_authority: float = 0.5,
    is_markdown: bool = False,
) -> tuple[str, bool]:
    """
    Ingest web-fetched content.

    The caller has already done the HTTP fetch; this function takes the
    raw content (HTML or pre-cleaned markdown) and writes it into the
    mesh. Use `is_markdown=True` if `raw_content` is already clean
    markdown (e.g. from Jina Reader or Firecrawl), otherwise trafilatura
    will strip boilerplate.
    """
    if store.get_workspace(workspace_id) is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")
    if not url:
        raise MeshStoreError("ingest_web_content requires a non-empty url")
    if not raw_content or not raw_content.strip():
        raise MeshStoreError("ingest_web_content requires non-empty raw_content")

    if is_markdown:
        text = raw_content.strip()
    else:
        text = _extract_html_text(raw_content)

    if len(text) < MIN_EXTRACTED_TEXT_LEN:
        raise MeshStoreError(
            f"Cleaned text too short ({len(text)} chars) for url={url}"
        )

    content_hash = _compute_content_hash(text)
    existing = store.source_id_by_hash(workspace_id, content_hash)
    if existing is not None:
        return existing, False

    src_id = _predicted_src_id(workspace_id, content_hash)
    sources_dir = store.sources_dir
    sources_dir.mkdir(parents=True, exist_ok=True)
    md_path = _write_source_markdown(
        sources_dir=sources_dir,
        src_id=src_id,
        text=text,
        original_name=url,
    )
    relative_path = str(md_path.relative_to(store.workspace_dir)).replace("\\", "/")

    try:
        actual_src_id = store.insert_source(
            workspace_id=workspace_id,
            kind="web",
            filepath=relative_path,
            content_hash=content_hash,
            sig_authority=sig_authority,
            title=title,
            url=url,
            authors=authors,
            year=year,
            doi=doi,
            venue=venue,
            word_count=len(text.split()),
        )
    except MeshStoreError as e:
        if "already exists" in str(e):
            existing2 = store.source_id_by_hash(workspace_id, content_hash)
            if existing2 is not None:
                return existing2, False
        raise

    if actual_src_id != src_id:
        new_path = sources_dir / f"{actual_src_id}.md"
        md_path.rename(new_path)

    return actual_src_id, True


# ───── reading back ingested sources ─────

def read_source_text(file_path: str | Path) -> str:
    """
    Read an ingested source markdown file and return just the BODY text
    — the content after the header that `_write_source_markdown` prepends.

    Downstream code that does char-span lookup against a claim's
    direct_quote MUST use this helper, not `Path.read_text()`. The
    mesh's `claims.char_start` / `char_end` are relative to the body,
    not to raw file bytes, so skipping the header strip would shift
    every offset by ~55-80 characters and silently corrupt provenance.

    If a file happens to have no header (e.g. written by a different
    tool, or a file from before the header convention), the whole file
    is returned unchanged.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise MeshStoreError(f"Source file not found: {file_path}")
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    if raw.startswith("<!--") and _HEADER_TERMINATOR in raw:
        return raw.split(_HEADER_TERMINATOR, 1)[1]
    return raw


# ───── text extraction dispatch ─────

def _extract_text(path: Path) -> str:
    """Dispatch text extraction on file suffix. Fails loudly on error."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace").strip()
    if suffix in (".html", ".htm"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _extract_html_text(raw)
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    raise MeshStoreError(f"Internal: unsupported suffix {suffix} reached _extract_text")


def _extract_html_text(raw_html: str) -> str:
    """Use trafilatura to extract the main article text from HTML."""
    try:
        import trafilatura  # noqa: F401 — presence check for the clear error below
    except ImportError as e:
        raise MeshStoreError("trafilatura is required for HTML ingest") from e

    # GH #1260: route through the ONE SIGSEGV-guarded door (size gate + optional
    # hard-killable subprocess) instead of a bare `trafilatura.extract`. A
    # libxml2 C-crash on a pathological doc is NOT a catchable Python exception;
    # the guard returns None on a contained crash, which maps to the existing
    # "could not extract" error path below.
    from src.tools.access_bypass import safe_trafilatura_extract

    extracted = safe_trafilatura_extract(
        raw_html,
        favor_precision=True,
        include_comments=False,
        include_tables=True,
        output_format="markdown",
    )
    if not extracted:
        raise MeshStoreError(
            "trafilatura could not extract main content from HTML"
        )
    return extracted.strip()


def _extract_pdf_text(path: Path) -> str:
    """Use docling to convert a PDF to markdown."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:
        raise MeshStoreError("docling is required for PDF ingest") from e

    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        text = result.document.export_to_markdown()
    except Exception as e:
        raise MeshStoreError(
            f"docling PDF conversion failed for {path.name}: {type(e).__name__}: {e}"
        ) from e

    if not text:
        raise MeshStoreError(
            f"docling returned empty text for PDF {path.name}"
        )
    return text.strip()


# ───── helpers ─────

def _compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _predicted_src_id(workspace_id: str, content_hash: str) -> str:
    """
    Mirror of `MeshStore._make_id("src", f"{workspace_id}:{content_hash}")`.

    We need this BEFORE calling insert_source so we can write the
    markdown file to `sources/{src_id}.md` before inserting the row.
    If `_make_id` ever changes, the post-insert consistency check in
    ingest_file catches the drift and renames the file.
    """
    h = hashlib.sha256(f"{workspace_id}:{content_hash}".encode("utf-8")).hexdigest()[:16]
    return f"src_{h}"


def _write_source_markdown(
    *,
    sources_dir: Path,
    src_id: str,
    text: str,
    original_name: str,
) -> Path:
    """
    Write `text` to `sources_dir/{src_id}.md` atomically.

    Atomic = write to a sibling `.tmp` file, then rename. If the process
    crashes mid-write, there is never a half-written `{src_id}.md`.
    """
    target = sources_dir / f"{src_id}.md"
    # Header ends with `-->\n\n` — the _HEADER_TERMINATOR that
    # `read_source_text` splits on. Keep them in sync.
    header = (
        f"<!--\n"
        f"src_id: {src_id}\n"
        f"original: {original_name}\n"
        f"-->\n\n"
    )
    # If the extracted text happens to start with a comment of its own,
    # still prepend our header — `read_source_text` splits on the FIRST
    # terminator, which will be ours, so body offsets stay correct.
    payload = header + text

    # Atomic write: temp file in same dir, then rename
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(sources_dir),
        prefix=f".{src_id}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(target)
    return target


def _default_title(file_path: Path, text: str) -> str:
    """
    Best-effort title from the file or its first non-empty line.

    If the markdown starts with an H1 (`# Title`), use that. Otherwise
    fall back to the filename stem.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped and not stripped.startswith("<!--"):
            # First non-empty, non-comment line is a reasonable fallback
            return stripped[:200]
        if stripped.startswith("<!--"):
            continue
    return file_path.stem
